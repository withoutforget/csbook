# Стек вызовов, соглашения о вызовах и ABI

Каждый вызов функции в программе — это не просто передача управления по адресу. За ним скрывается детально регламентированный протокол: какие регистры сохранять, как передавать аргументы, где хранить локальные переменные, как возвращать значение. Этот протокол называется **соглашением о вызовах** (calling convention), а совокупность всех правил взаимодействия между скомпилированными модулями — **ABI** (Application Binary Interface). Понимание стека вызовов необходимо для отладки, написания ассемблерных вставок, разработки JIT-компиляторов и понимания уязвимостей типа stack overflow.

ABI — это "невидимый контракт" платформы. Программа на C, скомпилированная clang, должна корректно вызывать функции из библиотеки, скомпилированной gcc, и C++ код. Нарушение ABI-совместимости — источник трудновоспроизводимых ошибок, особенно в системах с плагинами и общими библиотеками. Знаменитая проблема "бинарной несовместимости C++" при обновлении компилятора — это именно нарушение ABI.

В этой статье мы детально разберём организацию стека на x86-64, соглашения о вызовах System V AMD64 ABI (Linux, macOS) и Windows x64 ABI, управление фреймами, исключения и унwind, а также практические аспекты: от чтения стектрейсов до реализации функций-оберток на ассемблере.

## 1. Архитектура стека вызовов

### 1.1 Стек как регион памяти

Стек — непрерывный регион виртуальной памяти, растущий вниз (к меньшим адресам на x86). Регистр `RSP` (Stack Pointer) всегда указывает на вершину стека — последнее записанное значение.

```
Высокие адреса
┌─────────────────────┐ ← начало стека (при запуске)
│    argc, argv, env  │   аргументы и переменные окружения
├─────────────────────┤
│    main frame       │
├─────────────────────┤
│    func1 frame      │
├─────────────────────┤
│    func2 frame      │ ← текущий фрейм
├─────────────────────┤
│    (свободно)       │ ← RSP указывает сюда
│                     │
└─────────────────────┘ ← лимит стека (обычно 8 МБ на Linux)
Низкие адреса
```

По умолчанию Linux выделяет 8 МБ на стек (`ulimit -s`). При превышении — stack overflow: попытка записи ниже guard page вызывает SIGSEGV.

### 1.2 Структура фрейма

Каждый вызов функции создаёт **стековый фрейм** (stack frame, activation record) — регион стека для этой функции:

```
До вызова func(a, b):
┌────────────────────┐ ← RBP (frame pointer) вызывающей функции
│  saved registers   │
│  local variables   │
│  arg7+             │ ← аргументы 7 и далее (если > 6 аргументов)
└────────────────────┘ ← RSP после push аргументов

CALL func:
  → push RIP (адрес возврата)
  → jmp func

Пролог func:
  push RBP              ; сохранить frame pointer вызывающей функции
  mov  RBP, RSP         ; установить новый frame pointer
  sub  RSP, N           ; выделить место для локальных переменных

Фрейм func:
┌────────────────────┐ ← старый RSP (= новый RBP)
│ saved RBP          │ ← [RBP + 0]
│ return address     │ ← [RBP + 8] (сохранён CALL)
│ arg7, arg8...      │ ← [RBP + 16], [RBP + 24]...
├────────────────────┤ ← RBP (базовый указатель фрейма)
│ local variable 1   │ ← [RBP - 8]
│ local variable 2   │ ← [RBP - 16]
│ ...                │
└────────────────────┘ ← RSP (вершина стека)
```

### 1.3 Пример на ассемблере

```c
// Исходный C-код
int add(int a, int b) {
    int result = a + b;
    return result;
}

int main(void) {
    return add(3, 4);
}
```

```asm
; Скомпилировано gcc -O0 -m64 (без оптимизаций, чтобы показать фрейм)
add:
    push   rbp              ; сохранить RBP вызывающего
    mov    rbp, rsp         ; установить новый RBP
    mov    DWORD PTR [rbp-4], edi   ; a → локальная копия
    mov    DWORD PTR [rbp-8], esi   ; b → локальная копия
    mov    edx, DWORD PTR [rbp-4]
    mov    eax, DWORD PTR [rbp-8]
    add    eax, edx
    mov    DWORD PTR [rbp-12], eax  ; result
    mov    eax, DWORD PTR [rbp-12]  ; возвращаемое значение в RAX
    pop    rbp              ; восстановить RBP
    ret                     ; pop RIP, jmp RIP

main:
    push   rbp
    mov    rbp, rsp
    mov    esi, 4           ; второй аргумент (b=4) в RSI
    mov    edi, 3           ; первый аргумент (a=3) в RDI
    call   add              ; push RIP, jmp add
    pop    rbp
    ret
```

С оптимизацией (`-O2`) компилятор встраивает (inlines) вызов:

```asm
main:
    mov    eax, 7   ; просто константа — стека нет
    ret
```

## 2. System V AMD64 ABI (Linux, macOS)

### 2.1 Передача аргументов

System V AMD64 ABI регламентирует передачу аргументов через регистры:

| Позиция | Целые/указатели | Числа с плавающей точкой |
|---------|----------------|--------------------------|
| 1-й аргумент | RDI | XMM0 |
| 2-й | RSI | XMM1 |
| 3-й | RDX | XMM2 |
| 4-й | RCX | XMM3 |
| 5-й | R8 | XMM4 |
| 6-й | R9 | XMM5 |
| 7-й и далее | Стек (справа налево) | Стек |

Возвращаемое значение: RAX (целые/указатели), XMM0 (float/double), RAX+RDX (128-битные значения).

```c
// Пример с 8 аргументами
long test(long a, long b, long c, long d, long e, long f, long g, long h) {
    return a + b + c + d + e + f + g + h;
}

// ABI: a→RDI, b→RSI, c→RDX, d→RCX, e→R8, f→R9
//      g → [RSP+8], h → [RSP+16] (после CALL, адрес возврата на RSP)
```

### 2.2 Caller-saved и callee-saved регистры

Регистры делятся на две категории:

**Caller-saved** (volatile): вызывающая функция должна сохранить их до вызова, если нужны после:
- RAX, RCX, RDX, RSI, RDI, R8, R9, R10, R11
- XMM0-XMM15

**Callee-saved** (non-volatile): вызываемая функция обязана восстановить их перед возвратом:
- RBX, RBP, R12, R13, R14, R15

```asm
; Функция, использующая callee-saved регистры
my_func:
    push rbx            ; сохраняем RBX (callee-saved)
    push r12            ; сохраняем R12
    
    ; ... используем rbx, r12 ...
    
    pop r12             ; восстанавливаем в обратном порядке
    pop rbx
    ret
```

### 2.3 Выравнивание стека

System V ABI требует выравнивания RSP по 16 байт **перед** инструкцией CALL. После CALL RSP выровнен по 16 байт - 8 (минус адрес возврата). Поэтому пролог функции часто содержит `sub rsp, 8` или использует другое количество `push` для поддержания выравнивания.

Нарушение выравнивания приводит к штрафу производительности при работе с SSE/AVX инструкциями (или SIGSEGV для movaps).

```asm
; Проверка выравнивания
my_func:
    push rbp        ; RSP теперь выровнен по 16 (был -8, плюс push = -8)
    mov rbp, rsp
    ; На этом этапе RSP выровнен по 16 байт ✓
    
    ; Если нужен вызов подфункции с нечётным числом push:
    sub rsp, 8      ; восстанавливаем выравнивание
    call another_func
```

## 3. Windows x64 ABI

Windows использует другое соглашение, несовместимое с System V:

### 3.1 Отличия от System V

| Аспект | System V AMD64 | Windows x64 |
|--------|---------------|-------------|
| Первые 4 целых аргумента | RDI, RSI, RDX, RCX | RCX, RDX, R8, R9 |
| Первые 4 float аргумента | XMM0-XMM3 | XMM0-XMM3 |
| 5+ аргументов | Стек | Стек |
| Shadow space | Нет | 32 байта (обязательно!) |
| Callee-saved | RBX, RBP, R12-R15 | RBX, RBP, RDI, RSI, R12-R15, XMM6-XMM15 |

**Shadow space** (home space) — Windows требует, чтобы вызывающая функция зарезервировала 32 байта выше адреса возврата. Это место для сохранения регистровых аргументов (хотя это не обязательно делать).

```c
// Windows: вызов с 3 аргументами
int func(int a, int b, int c);
// a → RCX, b → RDX, c → R8

// На уровне ассемблера:
; sub rsp, 32      ; выделяем shadow space (ОБЯЗАТЕЛЬНО!)
; mov ecx, 1
; mov edx, 2
; mov r8d, 3
; call func
; add rsp, 32      ; освобождаем shadow space
```

Эта несовместимость — причина, почему нельзя вызывать Linux-скомпилированные .so из Windows DLL напрямую.

## 4. Фреймы и отладочная информация

### 4.1 Frame pointer omission (FPO)

Современные компиляторы по умолчанию включают `-fomit-frame-pointer`: не используют RBP как frame pointer, освобождая его для использования как обычного регистра. Это ускоряет код, но затрудняет построение стектрейсов.

Без frame pointer для анализа стека нужны таблицы `.eh_frame` / DWARF unwind info:

```bash
# Добавить frame pointer (для профилирования, отладки)
gcc -fno-omit-frame-pointer -g -O2 prog.c

# perf требует frame pointers для точных стектрейсов
perf record -g fp ./prog
perf report --stdio
```

### 4.2 DWARF Call Frame Information

ELF-файлы содержат секцию `.eh_frame` (exception handling frame) с таблицами, описывающими, как восстановить регистры и найти фрейм вызывающей функции в любой точке программы.

```bash
# Просмотр .eh_frame
objdump --dwarf=frames program | head -50

# Содержимое выглядит примерно так:
# DW_CFA_advance_loc: 1
# DW_CFA_def_cfa_offset: 16
# DW_CFA_offset: r6 (rbp) at cfa-16
```

gdb, perf, libunwind используют эти таблицы для построения стектрейсов без frame pointer.

### 4.3 backtrace() в C

```c
#include <execinfo.h>
#include <stdio.h>

void print_stack_trace(void) {
    void *array[20];
    int size = backtrace(array, 20);
    char **strings = backtrace_symbols(array, size);
    
    fprintf(stderr, "=== Stack trace ===\n");
    for (int i = 0; i < size; i++) {
        fprintf(stderr, "[%d] %s\n", i, strings[i]);
    }
    free(strings);
}

// Вывод (символы читаемы только с -g и без strip):
// [0] ./prog(print_stack_trace+0x1c) [0x400...]
// [1] ./prog(crash+0x11) [0x400...]
// [2] ./prog(main+0x2a) [0x400...]
```

Для получения имён функций в продакшен-бинарнике нужны либо DWARF-символы (`-g`), либо таблица символов (без `strip`).

## 5. Передача структур и больших объектов

### 5.1 Правила передачи структур в System V

Структура передаётся через регистры, если она ≤ 16 байт и состоит только из целочисленных/pointer полей. Иначе — через стек, с копированием:

```c
// Передаётся в регистрах (8 байт → 1 регистр)
typedef struct { int x; int y; } Point2D;
// Передаётся в RDI

// Передаётся в регистрах (16 байт → 2 регистра)
typedef struct { long a; long b; } TwoLongs;
// Передаётся в RDI, RSI

// Слишком большая — через стек
typedef struct { long a, b, c; } ThreeLongs;
// Вызывающая функция копирует структуру на стек,
// передаёт указатель в RDI (hidden first parameter)
```

### 5.2 Return value optimization (RVO) и NRVO

В C++ компилятор может конструировать возвращаемый объект непосредственно в памяти вызывающей функции, избегая копирования:

```cpp
std::vector<int> create_vector() {
    std::vector<int> v = {1, 2, 3, 4, 5};
    return v; // RVO: конструируется прямо в месте назначения
}

std::vector<int> result = create_vector();
// Без RVO: v создана в фрейме create_vector, скопирована в result
// С RVO (C++17 guaranteed copy elision): v создана прямо в result
```

На уровне ABI это реализовано как скрытый первый аргумент — указатель на место в стеке вызывающей функции.

## 6. Переполнение стека и защита

### 6.1 Stack canary

GCC/Clang могут добавлять **стековый канарей** (stack canary) — случайное значение между локальными переменными и адресом возврата. Перед возвратом из функции проверяется, что канарей не изменился. Если изменился — переполнение буфера:

```c
// Код с -fstack-protector:
void vulnerable(char *input) {
    char buffer[16];
    // Компилятор добавляет:
    // long __canary = __stack_chk_guard;  // случайное значение
    
    strcpy(buffer, input);  // переполнение перезапишет канарей
    
    // Перед ret компилятор добавляет:
    // if (__canary != __stack_chk_guard)
    //     __stack_chk_fail(); // abort()
}
```

```asm
; Скомпилировано с -fstack-protector
vulnerable:
    push   rbp
    mov    rbp, rsp
    sub    rsp, 48
    mov    QWORD PTR [rbp-8], rdi      ; сохраняем input
    mov    rax, QWORD PTR fs:40        ; читаем __stack_chk_guard
    mov    QWORD PTR [rbp-24], rax     ; сохраняем канарей
    ; ... код функции ...
    mov    rax, QWORD PTR [rbp-24]     ; читаем канарей
    xor    rax, QWORD PTR fs:40        ; сравниваем с исходным
    jne    .L_stack_fail               ; если изменился — abort
    leave
    ret
```

### 6.2 Shadow stack (Intel CET)

Intel Control-flow Enforcement Technology (CET) вводит hardware shadow stack: при CALL процессор параллельно записывает адрес возврата в защищённый теневой стек. При RET адреса сравниваются — если не совпадают, исключение.

Shadow stack доступен на процессорах Intel Rocket Lake (2021) и требует поддержки в ОС (Linux 6.x) и компиляторе (`-fcf-protection=return`).

### 6.3 ASAN stack detection

AddressSanitizer добавляет красные зоны (red zones) вокруг локальных переменных и определяет выход за границы буфера:

```c
// Компиляция: gcc -fsanitize=address -g
void test(void) {
    char buf[10];
    buf[15] = 'X';  // выход за границу
}
// Вывод при запуске:
// ERROR: AddressSanitizer: stack-buffer-overflow on address 0x...
// WRITE of size 1 at 0x... thread T0
//     #0 test stack_test.c:3
```

## 7. Хвостовая рекурсия и TCO

### 7.1 Tail Call Optimization

Если последнее действие функции — вызов другой функции (хвостовой вызов), компилятор может заменить CALL+RET на JMP, повторно используя текущий фрейм:

```c
// Хвостово-рекурсивный factorial
long fact_tail(long n, long acc) {
    if (n == 0) return acc;
    return fact_tail(n - 1, n * acc); // хвостовой вызов!
}

// С -O2 компилятор превращает это в цикл:
// fact_tail:
//     test edi, edi
//     je .done
// .loop:
//     imul rsi, rdi
//     dec rdi
//     jnz .loop
// .done:
//     mov rax, rsi
//     ret
```

Без TCO рекурсия на глубину N создаёт N фреймов. С TCO — один фрейм для любой глубины.

GCC и Clang выполняют TCO с `-O2`. Обязательная TCO требуется стандартом только в Scheme; JavaScript ES2015 обязал TCO, но V8 и другие движки его не реализуют из-за сложности с отладкой.

### 7.2 Trampolining

Если TCO не поддерживается компилятором, можно реализовать через трамплин:

```python
# Python не оптимизирует хвостовую рекурсию (лимит ~1000)
# Трамплин: возвращаем замыкание вместо рекурсивного вызова

def trampoline(f, *args):
    result = f(*args)
    while callable(result):
        result = result()
    return result

def fact_tramp(n, acc=1):
    if n == 0:
        return acc
    return lambda: fact_tramp(n - 1, n * acc)  # НЕ вызываем, возвращаем

# Теперь можно вычислить факториал 10000 без рекурсии
print(trampoline(fact_tramp, 10000))  # работает!
```

## 8. Вариадические функции (varargs)

### 8.1 va_list и System V ABI

`printf(char *fmt, ...)` принимает переменное число аргументов. В System V AMD64 ABI это реализовано через специальную структуру `va_list`:

```c
// Упрощённо: что хранит va_list в System V AMD64
typedef struct {
    unsigned int gp_offset;    // смещение в area регистровых целых аргументов
    unsigned int fp_offset;    // смещение в area регистровых float аргументов
    void *overflow_arg_area;   // указатель на стек (7+ аргумент)
    void *reg_save_area;       // базовый адрес области сохранения регистров
} va_list[1];

// Пример функции с varargs
#include <stdarg.h>

double sum_doubles(int count, ...) {
    va_list args;
    va_start(args, count);
    
    double total = 0.0;
    for (int i = 0; i < count; i++) {
        total += va_arg(args, double); // получить следующий double
    }
    
    va_end(args);
    return total;
}

double result = sum_doubles(3, 1.5, 2.5, 3.0); // → 7.0
```

Компилятор при вызове вариадической функции сохраняет регистровые аргументы в стек (reg save area), что позволяет `va_arg` итерировать через них.

## 9. ABI и бинарная совместимость

### 9.1 C++ ABI и mangling

C++ усложняет ABI из-за перегрузки функций. Для уникальности имён компилятор применяет **name mangling** — преобразование имён:

```cpp
// Исходные C++ функции
int add(int a, int b) { return a + b; }
float add(float a, float b) { return a + b; }
int add(int a, int b, int c) { return a + b + c; }

// После GCC mangling (можно проверить: nm binary | c++filt):
// _Z3addii    → add(int, int)
// _Z3addff    → add(float, float)
// _Z3addiii   → add(int, int, int)
```

```bash
# Деманглинг
nm binary | c++filt
# _Z3addii → add(int, int)

echo '_Z3addii' | c++filt
# add(int, int)
```

Схема mangling не стандартизирована, но на практике GCC, Clang и Intel ICC используют Itanium C++ ABI на Linux/macOS. MSVC использует собственный mangling.

### 9.2 Нарушение ABI при обновлении библиотек

```cpp
// Версия 1.0 библиотеки
class Widget {
    int x_, y_;
public:
    int getX() const { return x_; }
};
// sizeof(Widget) = 8

// Версия 1.1 — добавляем поле
class Widget {
    int x_, y_;
    int z_; // НОВОЕ ПОЛЕ — нарушает ABI!
public:
    int getX() const { return x_; }
    int getZ() const { return z_; }
};
// sizeof(Widget) = 12
```

Программа, скомпилированная с версией 1.0 и работающая с библиотекой 1.1, будет обращаться к неверным смещениям. Это приводит к некорректному поведению — не к ошибке компиляции.

Решение — **PImpl idiom** (pointer to implementation) или использование абстрактных интерфейсов:

```cpp
// Widget с PImpl — ABI-стабильна
class Widget {
    struct Impl;
    std::unique_ptr<Impl> pimpl_; // указатель фиксированного размера
public:
    int getX() const;
    // sizeof(Widget) = 8 (один указатель) — не меняется при добавлении полей
};
```

### 9.3 Symbol versioning

Linux shared libraries поддерживают символьные версии (symbol versioning) для ABI-совместимости:

```c
// В исходнике библиотеки
__asm__(".symver old_func,func@@LIBFOO_1.0");
__asm__(".symver new_func,func@LIBFOO_2.0");

// В map-файле
LIBFOO_1.0 { global: func; };
LIBFOO_2.0 { global: func; } LIBFOO_1.0;
```

Программы, собранные против версии 1.0, продолжают использовать старую реализацию даже после обновления библиотеки.

## 10. Интероп и FFI

### 10.1 Вызов C из Python (ctypes)

```python
import ctypes

# Загружаем C-библиотеку
libc = ctypes.CDLL("libc.so.6")

# Объявляем сигнатуру
libc.printf.restype = ctypes.c_int
libc.printf.argtypes = [ctypes.c_char_p, ctypes.c_int]

# Вызываем
libc.printf(b"Value: %d\n", 42)

# Своя функция из .so
lib = ctypes.CDLL("./mylib.so")
lib.compute.restype = ctypes.c_double
lib.compute.argtypes = [ctypes.c_double, ctypes.c_int]
result = lib.compute(3.14, 10)
```

ctypes следует System V ABI при передаче аргументов — именно поэтому нужно явно указывать типы аргументов и возврата.

### 10.2 JNI: вызов Java из C

Java Native Interface (JNI) определяет ABI для взаимодействия Java Virtual Machine с нативным кодом:

```c
// Нативная реализация Java метода
// public native long computeHash(byte[] data);

JNIEXPORT jlong JNICALL
Java_com_example_Hasher_computeHash(JNIEnv *env, jobject this, jbyteArray data) {
    jsize len = (*env)->GetArrayLength(env, data);
    jbyte *bytes = (*env)->GetByteArrayElements(env, data, NULL);
    
    jlong hash = 0;
    for (jsize i = 0; i < len; i++) {
        hash = hash * 31 + bytes[i];
    }
    
    (*env)->ReleaseByteArrayElements(env, data, bytes, JNI_ABORT);
    return hash;
}
```

JNI использует vtable-like таблицу методов `JNIEnv *` — все операции через указатели на функции, что обеспечивает совместимость с разными JVM.

## Заключение

Стек вызовов — это не просто техническая деталь; это фундамент, на котором строятся все уровни программного стека. ABI определяет протокол взаимодействия между языками, библиотеками и ОС. Нарушение ABI — источник ошибок, которые не обнаруживаются при компиляции и проявляются непредсказуемо.

Для практической работы: знание соглашений о вызовах помогает читать ассемблерный вывод компилятора, понимать профили производительности, писать корректные FFI-обёртки и разбираться в security-уязвимостях типа stack overflow. Frame pointer, canaries, shadow stack и ASAN — это многоуровневая защита от одного из старейших классов уязвимостей.

## Литература и ссылки

1. System V Application Binary Interface AMD64 Architecture Processor Supplement. [https://refspecs.linuxbase.org/elf/x86_64-abi-0.99.pdf](https://refspecs.linuxbase.org/elf/x86_64-abi-0.99.pdf)
2. Microsoft x64 Calling Convention. [https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention)
3. Itanium C++ ABI. [https://itanium-cxx-abi.github.io/cxx-abi/abi.html](https://itanium-cxx-abi.github.io/cxx-abi/abi.html)
4. DWARF Debugging Standard. [https://dwarfstd.org/](https://dwarfstd.org/)
5. Intel CET Shadow Stack. [https://www.intel.com/content/www/us/en/developer/articles/technical/technical-look-control-flow-enforcement-technology.html](https://www.intel.com/content/www/us/en/developer/articles/technical/technical-look-control-flow-enforcement-technology.html)
6. Drepper, U. *How to Write Shared Libraries*. Red Hat, 2011. [https://www.akkadia.org/drepper/dsohowto.pdf](https://www.akkadia.org/drepper/dsohowto.pdf)
7. GCC internals: Stack Layout. [https://gcc.gnu.org/onlinedocs/gccint/Stack-Layout.html](https://gcc.gnu.org/onlinedocs/gccint/Stack-Layout.html)
8. Wikipedia: Call stack. [https://en.wikipedia.org/wiki/Call_stack](https://en.wikipedia.org/wiki/Call_stack)
9. Wikipedia: Name mangling. [https://en.wikipedia.org/wiki/Name_mangling](https://en.wikipedia.org/wiki/Name_mangling)
