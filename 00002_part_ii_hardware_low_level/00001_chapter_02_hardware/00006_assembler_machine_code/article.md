# Ассемблер и машинный код — язык процессора

## Введение

Когда разработчик пишет программу на Python или Java, между его кодом и процессором существует несколько слоёв абстракции: интерпретатор, виртуальная машина, компилятор, компоновщик. Но в самом конце этой цепочки всегда находится машинный код — последовательность байтов, которую процессор непосредственно исполняет. Ассемблер — это текстовое представление машинного кода, в котором числовые коды операций заменены мнемониками: `mov`, `add`, `jmp`, `call`.

Понимание ассемблера необходимо не только системным программистам. Разработчики высоконагруженных систем используют его для анализа производительности, специалисты по безопасности — для реверс-инжиниринга и поиска уязвимостей, авторы компиляторов — для генерации оптимального кода. Даже при разработке на высокоуровневых языках знание ассемблера позволяет понять, что именно делает процессор с вашим кодом.

В этой статье мы рассмотрим архитектуру x86-64 — доминирующую архитектуру для серверов и персональных компьютеров. Мы изучим базовый набор инструкций, регистры, режимы адресации, соглашения о вызовах и научимся читать машинный код, генерируемый компиляторами.

## 1. Регистры x86-64

Процессор x86-64 имеет шестнадцать регистров общего назначения, каждый из которых хранит 64-битное значение. Их исторические имена унаследованы от 16-битной эпохи (8086), расширены до 32 бит в эпоху 386 (с префиксом E) и до 64 бит в x86-64 (с префиксом R):

```
Регистр  | 64-бит | 32-бит | 16-бит | 8-бит (низш.)
---------|--------|--------|--------|---------------
RAX      | RAX    | EAX    | AX     | AL
RBX      | RBX    | EBX    | BX     | BL
RCX      | RCX    | ECX    | CX     | CL
RDX      | RDX    | EDX    | DX     | DL
RSI      | RSI    | ESI    | SI     | SIL
RDI      | RDI    | EDI    | DI     | DIL
RBP      | RBP    | EBP    | BP     | BPL
RSP      | RSP    | ESP    | SP     | SPL
R8-R15   | Rn     | RnD    | RnW    | RnB
```

Помимо регистров общего назначения, существуют специальные регистры:

- **RIP** (Instruction Pointer) — указатель на следующую инструкцию. Нельзя изменить напрямую; обновляется инструкциями `jmp`, `call`, `ret`.
- **RFLAGS** — регистр флагов. Содержит результаты арифметических операций: ZF (zero flag), CF (carry flag), SF (sign flag), OF (overflow flag), IF (interrupt flag) и другие.
- **RSP** (Stack Pointer) — указатель вершины стека. Всегда указывает на последний занятый элемент стека.
- **RBP** (Base Pointer) — базовый указатель фрейма. По соглашению, указывает на начало текущего фрейма стека.

Кроме того, в x86-64 присутствуют:
- **XMM0-XMM15** — 128-битные регистры для операций SSE/SSE2
- **YMM0-YMM15** — 256-битные регистры для операций AVX
- **ZMM0-ZMM31** — 512-битные регистры для операций AVX-512
- **Сегментные регистры**: CS, DS, ES, FS, GS, SS (в 64-битном режиме почти не используются, кроме FS и GS для thread-local storage)

## 2. Базовые инструкции x86-64

### Инструкция MOV — пересылка данных

`MOV` — самая используемая инструкция. Она копирует данные из источника в назначение:

```asm
; Intel-синтаксис: MOV назначение, источник
mov rax, 42          ; загрузить константу 42 в RAX
mov rbx, rax         ; скопировать RAX в RBX
mov rax, [rbx]       ; загрузить из памяти по адресу в RBX
mov [rbx], rax       ; сохранить RAX в память по адресу в RBX
mov rax, [rbx + 8]   ; загрузить из памяти по адресу RBX+8
```

Важное ограничение: нельзя перемещать данные напрямую между двумя ячейками памяти — всегда нужен промежуточный регистр.

### Арифметические инструкции

```asm
add rax, rbx         ; RAX = RAX + RBX
sub rax, rbx         ; RAX = RAX - RBX
imul rax, rbx        ; RAX = RAX * RBX (знаковое умножение)
idiv rcx             ; RAX = RDX:RAX / RCX, RDX = остаток
inc rax              ; RAX = RAX + 1
dec rax              ; RAX = RAX - 1
neg rax              ; RAX = -RAX
```

Умножение и деление — особые случаи. `IDIV rcx` делит 128-битное число, хранящееся в паре регистров RDX:RAX, на RCX. Частное помещается в RAX, остаток — в RDX. Перед делением необходимо обнулить или расширить знак RDX с помощью инструкции `CQO` (Convert Quadword to Octaword).

### Логические инструкции

```asm
and rax, rbx         ; RAX = RAX & RBX (поразрядное И)
or  rax, rbx         ; RAX = RAX | RBX (поразрядное ИЛИ)
xor rax, rbx         ; RAX = RAX ^ RBX (поразрядное исключающее ИЛИ)
not rax              ; RAX = ~RAX (поразрядное НЕ)
shl rax, 3           ; RAX = RAX << 3 (сдвиг влево на 3)
shr rax, 3           ; RAX = RAX >> 3 (логический сдвиг вправо)
sar rax, 3           ; RAX = RAX >> 3 (арифметический сдвиг вправо)
```

Классический приём: `xor eax, eax` — обнуление регистра EAX (и автоматически старших 32 бит RAX). Это короче и быстрее, чем `mov eax, 0`.

### Инструкции сравнения и переходов

```asm
cmp rax, rbx         ; вычислить RAX - RBX, установить флаги, результат не сохранять
test rax, rax        ; вычислить RAX & RAX, установить флаги (проверка на ноль)

; Условные переходы (после cmp/test):
je  label            ; прыжок если равно (ZF=1)
jne label            ; прыжок если не равно (ZF=0)
jl  label            ; прыжок если меньше (знаковое)
jg  label            ; прыжок если больше (знаковое)
jle label            ; прыжок если меньше или равно
jge label            ; прыжок если больше или равно
jb  label            ; прыжок если ниже (беззнаковое)
ja  label            ; прыжок если выше (беззнаковое)

; Безусловный переход:
jmp label            ; безусловный прыжок
jmp rax              ; прыжок по адресу в RAX (косвенный)
```

### Инструкции работы со стеком

```asm
push rax             ; RSP -= 8; [RSP] = RAX
pop  rbx             ; RBX = [RSP]; RSP += 8
```

## 3. Режимы адресации

Режим адресации определяет, как вычисляется адрес операнда в памяти. В x86-64 поддерживается общая формула:

```
[база + индекс * масштаб + смещение]
```

где:
- **база** — любой регистр общего назначения
- **индекс** — любой регистр, кроме RSP
- **масштаб** — 1, 2, 4 или 8
- **смещение** — константа в диапазоне -2³¹ до 2³¹-1

Примеры:

```asm
mov rax, [rbx]           ; прямая косвенная адресация
mov rax, [rbx + 16]      ; база + смещение
mov rax, [rbx + rcx]     ; база + индекс
mov rax, [rbx + rcx*8]   ; база + индекс*масштаб (для массива int64)
mov rax, [rbx + rcx*8 + 32] ; полная форма

; Адресация относительно RIP (Position Independent Code):
mov rax, [rip + offset]  ; RIP-relative (для глобальных переменных в PIE)
```

RIP-relative адресация критически важна для создания позиционно-независимого кода (PIC/PIE), используемого в разделяемых библиотеках (.so, .dll) и в современных исполняемых файлах с ASLR.

## 4. Вызов функций: CALL и RET

Инструкции `CALL` и `RET` обеспечивают механизм вызова и возврата из функций:

```asm
; CALL label:
;   RSP -= 8
;   [RSP] = RIP (адрес следующей инструкции)
;   RIP = адрес label

; RET:
;   RIP = [RSP]
;   RSP += 8
```

Пример простой функции сложения:

```asm
section .text
global _start

; int64_t add(int64_t a, int64_t b)
; a передаётся в RDI, b — в RSI (System V AMD64 ABI)
add_func:
    mov rax, rdi     ; RAX = a
    add rax, rsi     ; RAX = a + b
    ret              ; вернуть значение в RAX

_start:
    mov rdi, 10      ; первый аргумент = 10
    mov rsi, 32      ; второй аргумент = 32
    call add_func    ; вызов функции
    ; теперь RAX = 42
```

## 5. Соглашения о вызовах: System V AMD64 ABI

Соглашение о вызовах (calling convention) определяет, как аргументы передаются функции и как возвращается результат. В Linux, macOS и других UNIX-совместимых системах на x86-64 используется **System V AMD64 ABI**.

### Передача аргументов

**Целочисленные аргументы и указатели** (первые 6):
1. RDI
2. RSI
3. RDX
4. RCX
5. R8
6. R9

Начиная с 7-го аргумента, они передаются через стек в обратном порядке.

**Аргументы с плавающей точкой** (первые 8): XMM0-XMM7

**Возвращаемое значение**: RAX (целое), XMM0 (float/double)

### Сохраняемые регистры (callee-saved)

Функция обязана сохранить и восстановить: **RBX, RBP, R12, R13, R14, R15**.

### Регистры, которые можно свободно использовать (caller-saved)

**RAX, RCX, RDX, RSI, RDI, R8, R9, R10, R11** — вызываемая функция может их изменить, вызывающая должна сохранить их сама, если они ей нужны.

### Пример полной функции с прологом и эпилогом

```asm
; int64_t compute(int64_t x, int64_t y, int64_t z)
; x -> RDI, y -> RSI, z -> RDX
compute:
    ; Пролог функции
    push rbp            ; сохранить старый базовый указатель
    mov  rbp, rsp       ; установить новый базовый указатель
    sub  rsp, 32        ; выделить 32 байта для локальных переменных
    push rbx            ; сохранить callee-saved регистр

    ; Тело функции
    mov  rbx, rdi       ; rbx = x
    imul rbx, rsi       ; rbx = x * y
    add  rbx, rdx       ; rbx = x*y + z
    mov  rax, rbx       ; возвращаемое значение = x*y + z

    ; Эпилог функции
    pop  rbx            ; восстановить callee-saved регистр
    mov  rsp, rbp       ; восстановить указатель стека
    pop  rbp            ; восстановить базовый указатель
    ret
```

Пролог и эпилог можно заменить псевдоинструкциями (NASM поддерживает `ENTER` и `LEAVE`, хотя они медленнее ручного кода):

```asm
compute:
    push rbp
    mov  rbp, rsp
    ; ...
    leave            ; эквивалентно: mov rsp, rbp; pop rbp
    ret
```

## 6. Как компилятор генерирует код

Рассмотрим простую функцию на C и её трансляцию в ассемблер:

```c
// sum.c
long sum_array(long *arr, int n) {
    long total = 0;
    for (int i = 0; i < n; i++) {
        total += arr[i];
    }
    return total;
}
```

Компиляция с GCC без оптимизаций (`-O0`) и с оптимизацией (`-O2`):

```bash
gcc -O0 -S -masm=intel sum.c -o sum_O0.asm
gcc -O2 -S -masm=intel sum.c -o sum_O2.asm
```

**Результат без оптимизации (-O0)**:

```asm
sum_array:
    push    rbp
    mov     rbp, rsp
    mov     QWORD PTR [rbp-24], rdi   ; сохранить arr
    mov     DWORD PTR [rbp-28], esi   ; сохранить n
    mov     QWORD PTR [rbp-8], 0      ; total = 0
    mov     DWORD PTR [rbp-12], 0     ; i = 0
.L2:
    mov     eax, DWORD PTR [rbp-12]   ; eax = i
    cmp     eax, DWORD PTR [rbp-28]   ; сравнить i с n
    jge     .L3                        ; если i >= n, выход
    mov     eax, DWORD PTR [rbp-12]   ; eax = i
    cdqe                               ; знаковое расширение eax -> rax
    lea     rdx, [0+rax*8]            ; rdx = i * 8
    mov     rax, QWORD PTR [rbp-24]   ; rax = arr
    add     rax, rdx                   ; rax = arr + i*8
    mov     rax, QWORD PTR [rax]       ; rax = arr[i]
    add     QWORD PTR [rbp-8], rax    ; total += arr[i]
    add     DWORD PTR [rbp-12], 1     ; i++
    jmp     .L2
.L3:
    mov     rax, QWORD PTR [rbp-8]   ; возврат total
    pop     rbp
    ret
```

**Результат с оптимизацией (-O2)**:

```asm
sum_array:
    test    esi, esi                   ; if (n == 0)
    jle     .L4
    lea     eax, [rsi-1]               ; eax = n-1
    xor     edx, edx                   ; total = 0
    xor     ecx, ecx                   ; i = 0
    lea     rax, [rdi+rax*8+8]        ; указатель на конец
.L3:
    add     rdx, QWORD PTR [rdi+rcx*8] ; total += arr[i]
    add     rcx, 1                      ; i++
    cmp     rdi, rax                   ; проверка конца
    jne     .L3
    mov     rax, rdx                   ; возврат
    ret
.L4:
    xor     eax, eax
    ret
```

Оптимизированный вариант: нет доступа к памяти для локальных переменных, переменная `i` и `total` хранятся в регистрах, проверка условия переработана для лучшей предсказуемости переходов.

## 7. Инструменты анализа: objdump и Godbolt

### objdump — дизассемблирование бинарников

```bash
# Скомпилировать:
gcc -O2 -o sum sum.c

# Дизассемблировать все секции:
objdump -d -M intel sum

# Дизассемблировать конкретную функцию:
objdump -d -M intel --disassemble=sum_array sum

# Показать машинный код (байты) рядом с ассемблером:
objdump -d -M intel sum | head -50
```

Пример вывода `objdump`:

```
0000000000001149 <sum_array>:
    1149:   85 f6                   test   esi,esi
    114b:   7e 1b                   jle    1168 <sum_array+0x1f>
    114d:   8d 46 ff                lea    eax,[rsi-0x1]
    1150:   31 d2                   xor    edx,edx
    1152:   31 c9                   xor    ecx,ecx
    1154:   48 8d 44 c7 08          lea    rax,[rdi+rax*8+0x8]
    1159:   48 03 14 cf             add    rdx,QWORD PTR [rdi+rcx*8]
    115d:   48 83 c1 01             add    rcx,0x1
    1161:   48 39 c7                cmp    rdi,rax
    1164:   75 f3                   jne    1159 <sum_array+0x10>
    1166:   48 89 d0                mov    rax,rdx
    1169:   c3                      ret
    116a:   31 c0                   xor    eax,eax
    116c:   c3                      ret
```

Каждая строка содержит: адрес, байты машинного кода, мнемонику ассемблера. Видно, что `jle` кодируется двумя байтами (`7e 1b`), а `add rdx, [rdi+rcx*8]` — четырьмя байтами (`48 03 14 cf`).

### nm — просмотр таблицы символов

```bash
nm sum                    # все символы
nm -D sum.so              # динамические символы разделяемой библиотеки
nm --demangle sum          # C++ demangling
```

### readelf — разбор ELF-файла

```bash
readelf -h sum             # заголовок ELF
readelf -S sum             # секции
readelf -s sum             # таблица символов
readelf -d sum.so          # динамические секции (зависимости)
```

### Compiler Explorer (Godbolt)

Онлайн-инструмент **Compiler Explorer** (godbolt.org) позволяет в реальном времени наблюдать, какой ассемблер генерирует компилятор. Особенно полезен для сравнения разных уровней оптимизации и разных компиляторов (GCC, Clang, MSVC, ICC).

Пример использования: введите код на C в левой панели, выберите компилятор и флаги оптимизации — в правой панели сразу появится ассемблерный вывод с подсветкой синтаксиса и стрелками, указывающими на соответствующие строки исходного кода.

## 8. Машинный код: кодирование инструкций x86-64

Машинный код x86-64 использует переменную длину инструкций — от 1 до 15 байт. Формат инструкции (упрощённо):

```
[Префиксы] [REX] Opcode [ModR/M] [SIB] [Displacement] [Immediate]
```

- **Префиксы** (0-4 байта): изменяют поведение инструкции (размер операнда, сегмент, lock, rep)
- **REX-префикс** (0-1 байт): расширение для 64-битных операндов и новых регистров R8-R15
- **Opcode** (1-3 байта): код операции
- **ModR/M** (0-1 байт): определяет режим адресации, регистры источника и назначения
- **SIB** (0-1 байт): Scale-Index-Base для сложных режимов адресации
- **Displacement** (0, 1, 2 или 4 байта): смещение в адресе памяти
- **Immediate** (0, 1, 2, 4 или 8 байт): непосредственный операнд

Пример декодирования: `48 03 14 cf` — это `add rdx, [rdi + rcx*8]`:
- `48` — REX.W (операнд 64-битный)
- `03` — опкод ADD r64, r/m64
- `14` — ModR/M: mod=00 (адресация через память), reg=010 (RDX), r/m=100 (SIB следует)
- `cf` — SIB: scale=11 (множитель 8), index=001 (RCX), base=111 (RDI)

## 9. Пример: реализация strlen на ассемблере

Разберём нетривиальный пример — функцию `strlen`, считающую длину строки:

```asm
section .text
global my_strlen

; size_t my_strlen(const char *s)
; Аргумент: RDI = указатель на строку
; Возврат: RAX = длина строки
my_strlen:
    xor  eax, eax          ; счётчик длины = 0
.loop:
    cmp  byte [rdi + rax], 0  ; сравнить текущий байт с '\0'
    je   .done                ; если ноль — конец строки
    inc  rax                  ; длина++
    jmp  .loop
.done:
    ret
```

Это наивная реализация. Оптимизированная версия из glibc работает с 16-байтовыми блоками через SSE2:

```asm
; Оптимизированный strlen с SSE2 (упрощённо)
my_strlen_sse2:
    mov  rax, rdi
    and  rax, -16              ; выровнять вниз до 16 байт
    pxor xmm0, xmm0           ; xmm0 = все нули (маска '\0')
    
    ; Загрузить 16 байт и сравнить все сразу
    movdqa  xmm1, [rax]       ; загрузить 16 байт
    pcmpeqb xmm1, xmm0        ; xmm1[i] = 0xFF если byte[i] == '\0'
    pmovmskb ecx, xmm1        ; ecx = битовая маска из старших битов xmm1
    ; если ecx != 0, нашли '\0' в первом блоке
    ; ... (дальнейшая обработка)
    ret
```

## 10. Пример полной программы на NASM

```asm
; hello.asm — вывод "Hello, World!" через системный вызов
; nasm -f elf64 hello.asm && ld hello.o -o hello

section .data
    msg     db "Hello, World!", 10   ; строка + символ новой строки
    msg_len equ $ - msg              ; длина строки (вычисляется ассемблером)

section .text
    global _start

_start:
    ; write(1, msg, msg_len)
    mov rax, 1          ; системный вызов 1 = write
    mov rdi, 1          ; файловый дескриптор 1 = stdout
    mov rsi, msg        ; адрес строки
    mov rdx, msg_len    ; длина строки
    syscall             ; вызов ядра

    ; exit(0)
    mov rax, 60         ; системный вызов 60 = exit
    xor rdi, rdi        ; код возврата = 0
    syscall
```

Системные вызовы Linux x86-64 передают аргументы через RDI, RSI, RDX, R10, R8, R9 (не RCX, как в ABI функций C!), а номер вызова — через RAX. Возврат из `syscall` происходит в следующую инструкцию, результат в RAX.

## 11. Связь с языками высокого уровня

Понимание ассемблера позволяет грамотно использовать инструменты профилирования. Рассмотрим, как `__attribute__((noinline))` в GCC влияет на генерируемый код:

```c
__attribute__((noinline))
int square(int x) {
    return x * x;
}

int main() {
    return square(5);
}
```

Без `noinline` компилятор встроит функцию (inlining) и результат окажется константой `25`, вычисленной во время компиляции. С `noinline` будет настоящий вызов через `call`.

Для точного контроля над ассемблером в C можно использовать встроенный ассемблер (inline assembly):

```c
#include <stdint.h>

// Быстрый подсчёт числа единичных битов (popcount)
static inline int popcount_manual(uint64_t x) {
    int result;
    __asm__ volatile (
        "popcnt %1, %0"
        : "=r"(result)    // выходной операнд
        : "r"(x)          // входной операнд
    );
    return result;
}

// Применение rdtsc для измерения времени
static inline uint64_t rdtsc(void) {
    uint32_t lo, hi;
    __asm__ volatile (
        "rdtsc"
        : "=a"(lo), "=d"(hi)
    );
    return ((uint64_t)hi << 32) | lo;
}
```

Встроенный ассемблер GCC использует синтаксис AT&T (операнды в обратном порядке: источник, назначение), что отличается от Intel-синтаксиса NASM/MASM.

## 12. Отладка на уровне ассемблера

При использовании GDB можно переключиться на ассемблерное представление:

```bash
gdb ./program
(gdb) disassemble main          # дизассемблировать функцию main
(gdb) set disassembly-flavor intel  # переключиться на Intel-синтаксис
(gdb) x/10i $rip               # показать 10 инструкций от RIP
(gdb) info registers           # показать все регистры
(gdb) stepi                    # шаг на одну машинную инструкцию
(gdb) nexti                    # шаг через call (не входить внутрь)
```

Для профилирования с привязкой к ассемблеру используется `perf`:

```bash
perf record ./program          # запись профиля
perf report --stdio            # отчёт в текстовом виде
perf annotate sum_array        # ассемблер с процентами времени
```

`perf annotate` показывает, сколько процентов времени тратится на каждую инструкцию — незаменимый инструмент для микрооптимизации.

## Заключение

Ассемблер и машинный код — фундамент, на котором строится вся программная экосистема. Регистры x86-64 (RAX, RBX, RSP, RBP, RIP и другие), базовые инструкции (MOV, ADD, JMP, CALL, RET), режимы адресации и соглашения о вызовах (System V AMD64 ABI) — всё это знания, которые помогают разработчику понять реальное поведение программы.

Умение читать вывод `objdump` и пользоваться Compiler Explorer превращает оптимизацию с гадания в инженерную задачу. Видя, что компилятор сгенерировал для вашего горячего цикла, вы можете принять обоснованное решение: написать более чистый код, подсказать компилятору нужные оптимизации или, в редких случаях, прибегнуть к ручному ассемблеру.

В последующих статьях мы рассмотрим, как стек вызовов организует локальные переменные и как конвейер процессора исполняет эти инструкции параллельно.

## Литература и источники

1. Intel Corporation (2023). *Intel 64 and IA-32 Architectures Software Developer's Manual*. Volumes 1-3. Intel Corporation. https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html

2. AMD (2023). *AMD64 Architecture Programmer's Manual*. AMD. https://developer.amd.com/resources/developer-guides-manuals/

3. Matz M., Hubicka J., Jaeger A., Mitchell M. (2013). *System V Application Binary Interface: AMD64 Architecture Processor Supplement*. https://gitlab.com/x86-psABIs/x86-64-ABI

4. Fog A. (2023). *Optimizing subroutines in assembly language: An optimization guide for x86 platforms*. Technical University of Denmark. https://www.agner.org/optimize/

5. Bryant R. E., O'Hallaron D. R. (2015). *Computer Systems: A Programmer's Perspective* (3rd ed.). Pearson. (Главы 3-4)

6. Kusswurm D. (2018). *Modern X86 Assembly Language Programming* (2nd ed.). Apress.

7. Doran R. W. (1979). Computer Architecture: A Structured Approach. Academic Press.

8. Blunden B. (2012). *The Rootkit Arsenal: Escape and Evasion in the Dark Corners of the System* (2nd ed.). Jones & Bartlett.

9. Godbolt M. Compiler Explorer. https://godbolt.org/ (интерактивный инструмент)

10. GNU Binutils Documentation. *objdump(1)*. https://sourceware.org/binutils/docs/binutils/objdump.html
