# ASLR, DEP/NX, Stack Canaries и CFI

## Введение

Атаки на память — переполнения буфера, use-after-free, format string — существуют с 1980-х годов. Но отрасль не стояла на месте: каждое новое поколение атак порождало новое поколение защит. ASLR появился в 2001 году. NX/DEP — около 2004. Stack canaries — ещё раньше, в StackGuard (1998). CFI — в 2010-е годы. Intel CET с аппаратной поддержкой — с 2020.

Понимание этих механизмов защиты важно с двух сторон: с точки зрения разработчика, чтобы правильно использовать их при компиляции; с точки зрения исследователя безопасности, чтобы понимать, что они дают и какие у них ограничения.

---

## 1. NX/DEP — Non-Executable Pages

### Концепция

**NX** (No-eXecute, AMD) / **XD** (eXecute Disable, Intel) — аппаратный бит в таблицах страниц, запрещающий исполнение кода из страниц, помеченных как не-исполняемые.

**DEP** (Data Execution Prevention) — название в контексте Windows для той же концепции.

До NX: стек и куча были одновременно записываемыми **и** исполняемыми. Классический shellcode в стеке работал именно так.

После NX: стек и куча — не-исполняемые (NX бит = 1). Попытка исполнить код там → SIGSEGV / #PF (Page Fault).

```
+------+--------+---------+----------+
| Сегм | Read   | Write   | Execute  |
+------+--------+---------+----------+
| .text | Yes   | No      | Yes      | ← код программы
| .data | Yes   | Yes     | No (NX)  | ← глобальные переменные
| stack | Yes   | Yes     | No (NX)  | ← стек
| heap  | Yes   | Yes     | No (NX)  | ← динамическая память
+------+--------+---------+----------+
```

### Проверка NX в Linux

```bash
# Проверить NX в бинарнике
readelf -l ./program | grep GNU_STACK
# GNU_STACK   RW    → NX включён (нет флага E = Execute)
# GNU_STACK   RWE   → NX выключен (небезопасно!)

# Проверить активность NX у работающего процесса
cat /proc/$(pidof my_program)/maps | grep stack
# 7ffffffde000-7ffffffff000 rw-p  → rw- без 'x' = NX активен

# checksec
checksec --file=./program
# NX:  NX enabled  ← хорошо
# NX:  NX disabled ← плохо
```

### Включение/выключение NX при компиляции

```bash
# NX включён по умолчанию в современных gcc/clang
gcc -o program program.c  # NX активен

# Явное включение (обычно не нужно)
gcc -o program program.c -Wl,-z,noexecstack

# ВЫКЛЮЧЕНИЕ NX (только для исследований/обучения!)
gcc -o program program.c -z execstack
```

```c
// В некоторых случаях NX нужно отключить легитимно:
// JIT-компиляторы (V8, LuaJIT, PyPy) — генерируют код в runtime
// и нуждаются в rwx-страницах

#include <sys/mman.h>

void* jit_compile_and_run(void* code, size_t size) {
    // Выделяем страницу с правами rwx
    void *exec_mem = mmap(NULL, size,
                          PROT_READ | PROT_WRITE | PROT_EXEC,
                          MAP_PRIVATE | MAP_ANONYMOUS,
                          -1, 0);
    
    if (exec_mem == MAP_FAILED) return NULL;
    
    // Копируем машинный код
    memcpy(exec_mem, code, size);
    
    // W^X (Write XOR Execute): лучшая практика —
    // сначала записать, потом переключить права
    mprotect(exec_mem, size, PROT_READ | PROT_EXEC);
    //        ↑ теперь только RX, не W
    
    // Вызываем скомпилированный код
    typedef int (*func_t)(void);
    func_t f = (func_t)exec_mem;
    int result = f();
    
    munmap(exec_mem, size);
    return NULL;
}
```

---

## 2. Stack Canaries — защита стека

### Принцип работы

Stack canary — случайное значение, вставляемое компилятором между локальными переменными и адресом возврата. Перед выполнением `ret` проверяется целостность значения.

```
Стек БЕЗ канарейки:       Стек С канарейкой:
+-----------------+        +-----------------+
|  адрес возврата |        |  адрес возврата |
+-----------------+        +-----------------+
|  сохранённый    |        |  сохранённый    |
|  rbp            |        |  rbp            |
+-----------------+        +-----------------+
|  ...            |        |  CANARY ← проверяется  |
+-----------------+        +-----------------+
|  buffer[64]     |        |  ...            |
+-----------------+        +-----------------+
                            |  buffer[64]     |
                            +-----------------+
```

### Ассемблерный вывод с канарейкой

```bash
# Компиляция с канарейкой
gcc -fstack-protector-strong -g -o protected protected.c

# Дизассемблирование
objdump -d protected | grep -A 30 "<vulnerable_function>"
```

```asm
; Пролог функции с канарейкой (x86-64)
push   rbp
mov    rbp, rsp
sub    rsp, 0x50           ; выделение места на стеке

; Загрузка канарейки
mov    rax, QWORD PTR fs:0x28    ; читаем из TLS (thread local storage)
mov    QWORD PTR [rbp-0x8], rax  ; сохраняем на стеке

; ... тело функции ...

; Эпилог: проверка канарейки
mov    rax, QWORD PTR [rbp-0x8]       ; читаем канарейку со стека
xor    rax, QWORD PTR fs:0x28         ; сравниваем с оригиналом
je     .return_ok                      ; если равны — всё в порядке
call   __stack_chk_fail               ; если нет — abort()!

.return_ok:
leave
ret
```

### Хранение канарейки

В Linux канарейка хранится в `fs:0x28` — специальном сегментном регистре (TLS, Thread Local Storage). Каждый поток имеет своё значение. Значение устанавливается при загрузке программы через `/dev/urandom`.

```c
// Как устанавливается канарейка (упрощённо, из glibc)
// security_init() в elf/dl-support.c

#include <sys/auxv.h>

void initialize_canary(void) {
    // Получаем случайные байты от ядра (через auxiliary vector)
    const uint64_t *random_bytes = (uint64_t *)getauxval(AT_RANDOM);
    
    // Канарейка — 8 байт случайных данных
    // Младший байт всегда 0x00 (защита от strcpy, которая копирует до '\0')
    uint64_t canary = *random_bytes;
    canary &= ~0xFFUL;  // Обнуляем младший байт: 0x...........00
    
    // Записываем в TLS (упрощённо)
    // В реальности: arch_prctl(ARCH_SET_FS, tls_base) + смещение 0x28
    __stack_chk_guard = canary;
}
```

### Уровни защиты канарейкой в GCC

```bash
# -fstack-protector: только функции с буфером > 8 байт или адресом локальной переменной
gcc -fstack-protector program.c

# -fstack-protector-all: все функции (большой overhead)
gcc -fstack-protector-all program.c

# -fstack-protector-strong (рекомендуется): функции с:
# - локальным массивом
# - адресом локальной переменной передаётся наружу
# - функция вызывает alloca()
gcc -fstack-protector-strong program.c

# -fstack-protector-explicit: только функции с __attribute__((stack_protect))
gcc -fstack-protector-explicit program.c
```

---

## 3. ASLR — Address Space Layout Randomization

### Концепция

ASLR рандомизирует базовые адреса загрузки при каждом запуске:
- Стек
- Куча
- Код программы (если PIE)
- Разделяемые библиотеки (libc, libm и т.д.)

Это делает адреса непредсказуемыми для атакующего.

```bash
# Уровни ASLR в Linux (/proc/sys/kernel/randomize_va_space):
# 0 — ASLR выключен
# 1 — Рандомизация стека, динамических библиотек, VDSO
# 2 — Также рандомизация кучи (значение по умолчанию)

cat /proc/sys/kernel/randomize_va_space
# → 2

# Временно отключить ASLR (для отладки):
echo 0 | sudo tee /proc/sys/kernel/randomize_va_space

# Запустить с отключённым ASLR только для одного процесса:
setarch $(uname -m) -R ./program
```

```python
# Демонстрация рандомизации адресов
import subprocess

def show_aslr_effect():
    """Запустить программу несколько раз и сравнить адреса"""
    script = '''
import ctypes
libc = ctypes.CDLL("libc.so.6")
import sys

# Адрес функции в libc
printf_addr = ctypes.cast(libc.printf, ctypes.c_void_p).value
print(f"printf @ {printf_addr:#x}")
    '''
    
    print("Адреса printf при трёх запусках:")
    for i in range(3):
        result = subprocess.run(
            ['python3', '-c', script],
            capture_output=True, text=True
        )
        print(f"  Запуск {i+1}: {result.stdout.strip()}")
    
    # Пример вывода (с ASLR):
    # Запуск 1: printf @ 0x7f8a1b2c3d4e
    # Запуск 2: printf @ 0x7f3d9a8b7c6d
    # Запуск 3: printf @ 0x7f12c4e5f6a7
    # Каждый раз разные!
```

### Энтропия ASLR

Количество бит энтропии определяет надёжность ASLR:

```bash
# Проверить энтропию ASLR
cat /proc/sys/kernel/kptr_restrict
# Биты энтропии для разных областей:

# На 64-bit Linux (примерные значения):
# Стек:         28 бит (~268 млн позиций)
# Куча:         13 бит (~8192 позиции) — МАЛО!
# mmap/libc:    28 бит
# PIE:          28 бит

# На 32-bit Linux — всего ~16 бит = 65536 позиций
# → brute force атака реальна (за несколько минут)
```

### PIE — Position-Independent Executable

```bash
# Без PIE: код программы всегда загружается по фиксированному адресу
readelf -h ./no_pie_program | grep Type
# Type: EXEC  ← фиксированный адрес (0x400000)

# С PIE: код программы рандомизирован вместе с ASLR
gcc -pie -fPIE -o pie_program program.c
readelf -h ./pie_program | grep Type
# Type: DYN  ← позиционно-независимый

# Современные дистрибутивы включают PIE по умолчанию
```

```python
# Демонстрация: PIE vs. no-PIE
# Без PIE: адрес main фиксирован
# С PIE: адрес main рандомизирован

import subprocess, re

def get_main_address(binary_path: str) -> list[str]:
    """Получить адрес main при нескольких запусках"""
    script = f'''
import ctypes, sys

# Загружаем сам бинарник через ptrace/proc (концептуально)
# На практике: смотрим /proc/self/maps
with open('/proc/self/maps') as f:
    maps = f.read()
    
for line in maps.split('\\n'):
    if 'r-xp' in line and '{binary_path.split("/")[-1]}' in line:
        base = int(line.split('-')[0], 16)
        print(f"code base: {{base:#x}}")
        break
    '''
    
    results = []
    for i in range(3):
        r = subprocess.run(['python3', '-c', script], 
                          capture_output=True, text=True)
        results.append(r.stdout.strip())
    return results
```

---

## 4. RELRO — Relocation Read-Only

### GOT и PLT: краткое введение

```
Программа                   GOT (Global Offset Table)    libc
+-------------+             +--------------------+
| call puts@plt|──→ PLT ──→ | got[puts] = addr   |──→ puts()
+-------------+             +--------------------+
```

При запуске динамический компоновщик заполняет GOT реальными адресами функций. Если GOT перезаписать — вызовы библиотечных функций пойдут на адреса атакующего.

### Уровни RELRO

```bash
# Partial RELRO: только .got секция (не .got.plt) защищена
gcc -Wl,-z,relro -o partial_relro program.c
# .got.plt — writable (можно перезаписать!)
# .got — read-only (прочитать, не записать)

# Full RELRO: все символы разрешаются при запуске, GOT полностью read-only
gcc -Wl,-z,relro,-z,now -o full_relro program.c
# ВСЯ GOT — read-only
# Overhead: чуть дольше старт программы (все символы разрешаются сразу)

# Проверка:
checksec --file=./program
# Full RELRO:    GOT таблица полностью защищена
# Partial RELRO: .got.plt перезаписываема

# readelf для детального анализа:
readelf -S ./program | grep -E "\.got|\.rel"
```

---

## 5. FORTIFY_SOURCE — защита stdlib функций

```bash
# _FORTIFY_SOURCE=1: проверки в compile time
# _FORTIFY_SOURCE=2: проверки в compile time + runtime
# _FORTIFY_SOURCE=3: GCC 12+, более агрессивно

gcc -D_FORTIFY_SOURCE=2 -O2 -o program program.c
# (требует -O1 или выше для работы!)
```

```c
#include <string.h>

// Без FORTIFY_SOURCE:
char buf[10];
strcpy(buf, src);  // нет проверки

// С FORTIFY_SOURCE=2:
// Компилятор заменяет strcpy на __strcpy_chk(buf, src, sizeof(buf))
// Если strlen(src) >= sizeof(buf) → __chk_fail() → abort()

// Аналогично для:
// memcpy → __memcpy_chk
// sprintf → __sprintf_chk  
// gets → запрещена полностью (ошибка компиляции!)
// snprintf → __snprintf_chk

// Пример проверки:
char name[8];
sprintf(name, "%s", long_string);  // abort если long_string > 7 байт
```

---

## 6. Control Flow Integrity (CFI)

### Проблема косвенных переходов

ROP использует `ret` и косвенные `jmp/call [reg]`. CFI ограничивает допустимые цели этих инструкций.

```c
// Без CFI: указатель на функцию может быть перезаписан
typedef void (*handler_t)(const char *);

handler_t handlers[] = {log_event, send_alert, ignore_event};

// Атакующий перезаписывает handlers[0] адресом system()
handlers[index](user_message);  // → system(user_message)!

// С CFI: перед каждым indirect call проверяется тип целевой функции
// Если цель не соответствует типу handler_t → abort
```

### Clang CFI

```bash
# Компиляция с CFI (требует LTO)
clang -fsanitize=cfi \
      -fsanitize=cfi-icall \
      -fsanitize=cfi-vcall \
      -flto \
      -fvisibility=hidden \
      -o program program.c

# Типы CFI защит:
# cfi-icall:     проверка indirect call (по указателю на функцию)
# cfi-vcall:     проверка virtual call (vtable в C++)
# cfi-nvcall:    non-virtual call через указатель
# cfi-unrelated-cast: неверное приведение типов
# cfi-derived-cast:   неверное downcast

# Для shared libraries нужен -fsanitize=cfi-icall и -shared
```

```c
// Как Clang CFI работает внутри (упрощённо)
// Компилятор создаёт "type hash" для каждого типа указателя на функцию

// Оригинальный код:
void (*fn)(int, char*) = get_handler();
fn(42, "hello");  // indirect call

// После CFI (упрощённо):
void (*fn)(int, char*) = get_handler();

// Проверка типа перед вызовом:
if (!__cfi_check(fn, type_hash_of_void_int_charptr)) {
    __cfi_slowpath(fn, type_hash_of_void_int_charptr);
    // slowpath: детальная проверка или abort
}
fn(42, "hello");  // вызов только если проверка прошла
```

### Microsoft Control Flow Guard (CFG)

```c
// Windows: /guard:cf флаг компилятора MSVC
// При загрузке PE-файла создаётся bitmap допустимых адресов indirect call targets
// Каждый indirect call проверяется через _guard_check_icall

// В ассемблере (x64):
// mov rcx, <target>        ; целевой адрес
// call [__guard_check_icall_fptr]  ; проверка через bitmap
// call rcx                 ; вызов только если прошла проверка

// Для shellcode: всё сложнее, т.к. произвольный адрес не в bitmap
```

### Intel CET — аппаратная поддержка

```bash
# Проверить поддержку CET на процессоре
grep -o 'shstk\|ibt' /proc/cpuinfo | sort -u
# shstk = Shadow Stack (защита ret)
# ibt = Indirect Branch Tracking (защита call/jmp)

# Компиляция с CET
gcc -mcet -mshstk -mibt -o cet_program program.c
# или
gcc -fcf-protection=full -o cet_program program.c
```

```asm
; CET: Shadow Stack
; При вызове функции адрес возврата записывается И в обычный стек, И в Shadow Stack
; Shadow Stack хранится в отдельном регистре (SSP - Shadow Stack Pointer)
; При ret: адрес из обычного стека == адрес из Shadow Stack
; Если нет → #CP (Control Protection exception)

; CET: ENDBR64 (Indirect Branch Tracking)
; Каждая легитимная цель indirect call/jmp должна начинаться с ENDBR64
endbr64       ; F3 0F 1E FA — 4 байта, "End Branch 64-bit"
push rbp      ; нормальный пролог функции

; При indirect call: процессор проверяет наличие ENDBR64 на цели
; Если нет → #CP exception (в Protected mode)
```

```c
// Программная проверка поддержки CET
#include <sys/prctl.h>
#include <stdio.h>

#ifndef PR_GET_TAGGED_ADDR_CTRL
#define PR_GET_TAGGED_ADDR_CTRL  56
#endif

void check_cet_support(void) {
    // Проверка через CPUID (концептуально)
    unsigned int eax, ebx, ecx, edx;
    // cpuid(7, 0, &eax, &ebx, &ecx, &edx)
    // CET_SS: bit 7 of ECX (CPUID leaf 7, subleaf 0)
    // CET_IBT: bit 20 of EDX (CPUID leaf 7, subleaf 0)
    
    // Проверка через /proc/cpuinfo
    FILE *f = fopen("/proc/cpuinfo", "r");
    char line[256];
    int has_shstk = 0, has_ibt = 0;
    
    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, "shstk")) has_shstk = 1;
        if (strstr(line, "ibt"))   has_ibt = 1;
    }
    fclose(f);
    
    printf("Shadow Stack (shstk): %s\n", has_shstk ? "supported" : "not supported");
    printf("IBT (ibt):            %s\n", has_ibt   ? "supported" : "not supported");
}
```

---

## 7. ARM: PAC и BTI

На ARM64 (используется в Apple Silicon, мобильных устройствах) аналогичные защиты реализованы через PAC и BTI:

```asm
; PAC — Pointer Authentication Codes
; Подписывает указатели криптографически перед сохранением
; Проверяет подпись перед разыменованием

; Защита адреса возврата:
PACIASP     ; подписываем LR (link register) ключом A
push x29, lr ; сохраняем на стек (теперь LR подписан)
...
pop x29, lr  ; восстанавливаем
AUTIASP     ; проверяем подпись LR, abort если неверна
ret          ; возврат безопасен

; BTI — Branch Target Identification (аналог ENDBR64)
BTI c       ; "Branch Target Identification, callable"
; Цель call инструкции должна начинаться с BTI
```

```bash
# Компиляция с PAC/BTI для ARM64
gcc -mbranch-protection=standard program.c
# standard = pac-ret + bti
# pac-ret:  защита адресов возврата через PAC
# bti:      защита indirect branches через BTI
```

---

## 8. SafeStack

SafeStack — защита Clang, которая разделяет стек на два:

1. **Safe stack** — адреса возврата, указатели функций, неуязвимые переменные
2. **Unsafe stack** — все остальные переменные (буферы, массивы)

```bash
# Компиляция с SafeStack
clang -fsanitize=safe-stack -o program program.c
```

```c
// Как SafeStack работает (концептуально):

// Оригинальный код:
void function(char *input) {
    char buffer[64];      // небезопасный буфер
    void *saved_fp;       // указатель на функцию — безопасный
    char *name = "Alice"; // безопасный указатель
    
    strcpy(buffer, input);  // переполнение buffer
    ((void(*)(void))saved_fp)();  // вызов через указатель
}

// После SafeStack:
// buffer[64] → UNSAFE STACK (можно переполнить, но не достигнет ret addr)
// saved_fp   → SAFE STACK (отдельная область памяти)
// name       → SAFE STACK

// Адрес возврата на SAFE STACK, переполнение buffer его не достигает!
```

---

## 9. Shadow Stack в ядре Linux

```bash
# Linux 6.6+: поддержка shadow stack для пользовательских процессов
# Включается через ARCH_SHSTK_SHSTK флаг

# Проверка поддержки:
grep SHADOW_STACK /boot/config-$(uname -r)
# CONFIG_X86_USER_SHADOW_STACK=y

# Включение для процесса (через glibc 2.39+):
# устанавливается автоматически если процессор и ядро поддерживают CET
```

---

## 10. Совокупная защита: всё вместе

Ни одна защита сама по себе не является абсолютной. Правильная конфигурация использует все защиты совместно:

```makefile
# Рекомендованные флаги компиляции (2024)
CC = gcc
CFLAGS = \
    -Wall -Wextra -Werror \
    -O2 \
    -fstack-protector-strong \
    -D_FORTIFY_SOURCE=2 \
    -fPIE \
    -fcf-protection=full \
    -fstack-clash-protection \
    -Wformat -Wformat-security \
    -Werror=format-security

LDFLAGS = \
    -pie \
    -Wl,-z,relro \
    -Wl,-z,now \
    -Wl,-z,noexecstack \
    -Wl,-z,separate-code

# Для Clang также добавить:
CLANG_EXTRA = \
    -fsanitize=cfi \
    -fsanitize=safe-stack \
    -flto \
    -fvisibility=hidden
```

```python
# Скрипт проверки защит бинарника
import subprocess
import re
from dataclasses import dataclass

@dataclass
class BinarySecurityProfile:
    nx: bool
    pie: bool
    canary: bool
    relro: str  # 'none', 'partial', 'full'
    fortify: bool
    rpath: bool

def check_binary_security(path: str) -> BinarySecurityProfile:
    """Анализ защит бинарного файла"""
    result = subprocess.run(
        ['checksec', '--file', path, '--output', 'json'],
        capture_output=True, text=True
    )
    
    # Альтернативно — readelf анализ
    readelf_output = subprocess.run(
        ['readelf', '-a', path],
        capture_output=True, text=True
    ).stdout
    
    nx = 'GNU_STACK' in readelf_output and \
         re.search(r'GNU_STACK.*RW\b', readelf_output) is not None
    
    pie = 'DYN' in subprocess.run(
        ['readelf', '-h', path],
        capture_output=True, text=True
    ).stdout
    
    canary = '__stack_chk_fail' in subprocess.run(
        ['nm', '-D', path],
        capture_output=True, text=True
    ).stdout
    
    # RELRO: смотрим секции
    has_relro = '.got.plt' in readelf_output
    # Полный анализ требует проверки флагов секции
    relro = 'partial'  # упрощённо
    
    return BinarySecurityProfile(
        nx=nx,
        pie=pie,
        canary=canary,
        relro=relro,
        fortify='__printf_chk' in readelf_output or \
                '__memcpy_chk' in readelf_output,
        rpath='RPATH' not in readelf_output and \
              'RUNPATH' not in readelf_output
    )

def security_score(profile: BinarySecurityProfile) -> int:
    """Оценка защищённости от 0 до 5"""
    score = 0
    if profile.nx: score += 1
    if profile.pie: score += 1
    if profile.canary: score += 1
    if profile.relro == 'full': score += 1
    if profile.fortify: score += 1
    return score
```

---

## 11. Overhead защитных механизмов

Важный практический вопрос: какова цена защит в производительности?

```bash
# Измерение overhead на стандартных бенчмарках
# (результаты из академических работ и документации)
```

| Защита | Overhead памяти | Overhead CPU | Влияние на старт |
|--------|----------------|-------------|------------------|
| NX/DEP | 0 | ~0% | 0 |
| Stack canary (-fstack-protector-strong) | +8 байт/кадр | <1% | 0 |
| ASLR | 0 | ~0% | 0 |
| PIE | +код на reloc | <1% | +~1ms |
| Partial RELRO | 0 | ~0% | +~1ms |
| Full RELRO | 0 | ~0% | +~5-50ms (зависит от кол-ва символов) |
| FORTIFY_SOURCE=2 | 0 | <1% | 0 |
| Clang CFI | минимально | 1-5% | 0 |
| SafeStack | 2-й стек | 1-3% | 0 |
| CET (hardware) | shadow stack | <1% | 0 |

---

## 12. Обход защит и их комбинирование

Ни одна из защит не является непреодолимой в одиночку, но их сочетание существенно затрудняет атаку:

```
Атака на переполнение буфера:

Без защит:
  Переполнение → Shellcode в стеке → Выполнение
  Сложность: низкая

С NX:
  Переполнение → Shellcode в стеке → SIGSEGV (стек не исполняем)
  Обход: ROP (используем существующий код)

С NX + ASLR без PIE:
  Переполнение → ROP → Нужен адрес libc
  Обход: ret2plt утечка адреса libc

С NX + ASLR + PIE + Canary:
  Переполнение → нужно обойти канарейку → нужна утечка адресов
  Обход: format string/heap для утечки, затем ROP
  Сложность: высокая

С NX + ASLR + PIE + Canary + CFI + CET:
  Обход требует множества уязвимостей в цепочке
  Сложность: очень высокая
```

---

## Заключение

Защитные механизмы для бинарного кода — необходимый уровень обороны для любого C/C++ кода. Их правильная настройка не требует значительных усилий, но существенно повышает планку для атакующего.

**Чеклист для разработчика:**
1. Компилировать с `-fstack-protector-strong` — канарейки на стеке
2. `-D_FORTIFY_SOURCE=2` — проверки в stdlib
3. `-pie -fPIE` — рандомизация адресов программы
4. `-Wl,-z,relro,-z,now` — Full RELRO, GOT read-only
5. `-Wl,-z,noexecstack` — NX стек
6. `-fcf-protection=full` — CFI через Intel CET
7. Регулярно запускать `checksec` в CI/CD

**Системный выбор:** там где это возможно, переход на memory-safe языки (Rust, Go) устраняет целый класс уязвимостей на уровне языка — это надёжнее любого набора флагов компилятора.

---

## Литература и источники

1. Cowan, C., et al. (1998). *StackGuard: Automatic Adaptive Detection and Prevention of Buffer-Overflow Attacks*. USENIX Security 1998. https://www.usenix.org/conference/7th-usenix-security-symposium/stackguard-automatic-adaptive-detection-and-prevention
2. PaX Team. *PaX Address Space Layout Randomization*. https://pax.grsecurity.net/docs/aslr.txt
3. Intel. *Control-flow Enforcement Technology Specification*. https://www.intel.com/content/dam/www/public/us/en/documents/technical-reports/intel-cet-tech-report.pdf
4. Clang CFI documentation. https://clang.llvm.org/docs/ControlFlowIntegrity.html
5. Kuznetsov, V., et al. (2014). *Code-Pointer Integrity*. OSDI 2014. https://www.usenix.org/conference/osdi14/technical-sessions/presentation/kuznetsov
6. GCC Stack Smashing Protector. https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html#index-fstack-protector
7. Biondo, A. et al. (2018). *The Guard's Dilemma: Efficient Code-Reuse Attacks Against Intel MPX*. USENIX Security 2018.
8. Linux man page: mprotect(2). https://man7.org/linux/man-pages/man2/mprotect.2.html
9. ARM. *Architecture Reference Manual: Pointer Authentication*. https://developer.arm.com/documentation/ddi0487
10. checksec tool documentation. https://github.com/slimm609/checksec.sh
