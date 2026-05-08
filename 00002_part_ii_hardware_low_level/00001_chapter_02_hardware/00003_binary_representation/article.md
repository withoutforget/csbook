# Двоичное представление и дополнительный код

## Введение

Всё, что обрабатывает компьютер, — числа, текст, изображения, звук — в конечном счёте хранится как последовательности нулей и единиц. Понимание того, как именно числа представлены в двоичной системе, критически важно для программиста: переполнения, знаковые числа, битовые операции — всё это становится ясным, когда знаешь, как устроено хранение чисел.

---

## 1. Позиционные системы счисления

В позиционной системе счисления с основанием b значение числа:

```
(dₙdₙ₋₁...d₁d₀)_b = Σᵢ dᵢ × bⁱ
```

| Система | Основание | Символы |
|---|---|---|
| Двоичная | 2 | 0, 1 |
| Восьмеричная | 8 | 0–7 |
| Десятичная | 10 | 0–9 |
| Шестнадцатеричная | 16 | 0–9, A–F |

```python
# Перевод числа в разные системы
n = 255

print(f"Decimal: {n}")
print(f"Binary:  {bin(n)}")    # 0b11111111
print(f"Octal:   {oct(n)}")    # 0o377
print(f"Hex:     {hex(n)}")    # 0xff

# Перевод вручную
def to_binary(n):
    if n == 0:
        return '0'
    bits = []
    while n > 0:
        bits.append(str(n % 2))
        n //= 2
    return ''.join(reversed(bits))

print(to_binary(42))   # 101010
print(to_binary(255))  # 11111111

# Перевод из двоичного
def from_binary(s):
    return sum(int(bit) * (2**i) for i, bit in enumerate(reversed(s)))

print(from_binary('101010'))   # 42
print(from_binary('11111111')) # 255

# Шестнадцатеричное — удобно для работы с байтами
# 1 шестнадцатеричная цифра = 4 бита (ниббл)
# 2 шестнадцатеричные цифры = 1 байт

print(f"0xFF = {0xFF}")        # 255 = 11111111
print(f"0xDEADBEEF = {0xDEADBEEF:b}")  # 32-битное «магическое число»
```

---

## 2. Беззнаковые целые числа

Беззнаковое целое n-битное число хранит значения от 0 до 2^n - 1.

| Тип | Размер | Диапазон |
|---|---|---|
| uint8  | 8 бит | 0 ... 255 |
| uint16 | 16 бит | 0 ... 65 535 |
| uint32 | 32 бит | 0 ... 4 294 967 295 |
| uint64 | 64 бит | 0 ... 18 446 744 073 709 551 615 |

```python
import struct

# Упаковка/распаковка чисел в байты (big-endian)
n = 256
packed_be = struct.pack('>H', n)   # big-endian unsigned short
packed_le = struct.pack('<H', n)   # little-endian unsigned short

print(f"{n} (big-endian):    {packed_be.hex()}")    # 0100
print(f"{n} (little-endian): {packed_le.hex()}")    # 0001

# Big-endian: старший байт первый (сетевой порядок)
# Little-endian: младший байт первый (x86, ARM)
```

### Переполнение беззнаковых чисел

При превышении максимального значения число «оборачивается» (wrap around):

```python
# В Python нет переполнения (BigInteger), но моделируем:
MAX_UINT8 = 255

def uint8_add(a, b):
    return (a + b) % 256

print(uint8_add(200, 100))  # 44  (300 % 256 = 44)
print(uint8_add(255, 1))    # 0   (255 + 1 переполняется в 0)

# В C/C++ это определённое поведение (defined behavior) для unsigned
# В Rust паника в debug-режиме, wrap в release
```

---

## 3. Знаковые числа: дополнительный код

Для хранения отрицательных чисел используются три возможные кодировки:

1. **Знак-модуль** (Sign-Magnitude): старший бит — знак, остальные — модуль
2. **Прямой код с дополнением до 1** (Ones' Complement)
3. **Дополнительный код** (Two's Complement) — используется в современных компьютерах

### Почему дополнительный код

Главное преимущество дополнительного кода: одна и та же схема сложения работает для знаковых и беззнаковых чисел. Никаких специальных команд вычитания — только сложение.

### Дополнительный код: определение

Для n-битного числа:
- Положительные числа: как в беззнаковом (от 0 до 2^(n-1) - 1)
- Отрицательное число -k: представляется как 2^n - k

Или иначе: инвертировать все биты и прибавить 1.

```python
def to_twos_complement(n, bits=8):
    """Представление n в дополнительном коде (bits бит)"""
    if n >= 0:
        return n
    return (1 << bits) + n  # 2^bits + n для отрицательных

def from_twos_complement(value, bits=8):
    """Интерпретация двоичного числа как знакового"""
    if value >= (1 << (bits - 1)):  # старший бит = 1
        return value - (1 << bits)
    return value

# Примеры для 8 бит
for n in [0, 1, 127, -1, -128]:
    encoded = to_twos_complement(n, 8)
    decoded = from_twos_complement(encoded, 8)
    print(f"{n:4d} → {encoded:08b} ({encoded:3d}) → {decoded:4d}")
```

```
   0 → 00000000 (  0) →    0
   1 → 00000001 (  1) →    1
 127 → 01111111 (127) →  127
  -1 → 11111111 (255) →   -1
-128 → 10000000 (128) → -128
```

### Инверсия + 1

```python
def negate_twos_complement(n, bits=8):
    """Нахождение -n в дополнительном коде"""
    mask = (1 << bits) - 1
    return (~n & mask) + 1

print(negate_twos_complement(5))   # 251 = -5 в двоичном
print(negate_twos_complement(1))   # 255 = -1 в двоичном
print(negate_twos_complement(0))   # 0 (0 = -0 в дополнительном коде!)
print(negate_twos_complement(128)) # 128 = -128 (особый случай: MIN_INT8 не имеет позитивного аналога)
```

### Диапазоны знаковых типов

| Тип | Размер | Диапазон |
|---|---|---|
| int8  | 8 бит | -128 ... 127 |
| int16 | 16 бит | -32 768 ... 32 767 |
| int32 | 32 бит | -2 147 483 648 ... 2 147 483 647 |
| int64 | 64 бит | $-9.2 \times 10^{18}$ ... $9.2 \times 10^{18}$ |

---

## 4. Арифметика в дополнительном коде

Ключевое свойство: сложение и вычитание работают одинаково для знаковых и беззнаковых чисел!

```python
# 8-битная арифметика в дополнительном коде
def twos_add(a, b, bits=8):
    """Сложение двух 8-битных чисел (signed)"""
    mask = (1 << bits) - 1
    result = (a + b) & mask
    return from_twos_complement(result, bits)

# Сложение:
print(twos_add(3, 5))    # 8
print(twos_add(5, -3))   # 2 (вычитание через сложение!)
print(twos_add(-5, -3))  # -8
print(twos_add(100, 50)) # -106 (переполнение: 150 > 127)

# Переполнение знакового числа:
# + + + = - (положительное переполнение)
# - + - = + (отрицательное переполнение)
print(twos_add(127, 1))  # -128 (переполнение!)
print(twos_add(-128, -1)) # 127 (переполнение!)

# Детектирование переполнения:
def twos_add_overflow(a, b, bits=8):
    """Сложение с детектированием переполнения"""
    result = a + b
    min_val = -(1 << (bits - 1))
    max_val = (1 << (bits - 1)) - 1
    overflow = result < min_val or result > max_val
    return result & ((1 << bits) - 1), overflow

result, overflow = twos_add_overflow(127, 1)
print(f"127 + 1 = {result} (overflow={overflow})")
```

---

## 5. Сдвиги для знаковых чисел

```python
# Логический сдвиг вправо (>>): заполняет нулями слева
# Арифметический сдвиг вправо: заполняет знаковым битом

def logical_shift_right(n, bits, shift):
    """Логический сдвиг вправо"""
    mask = (1 << bits) - 1
    return (n & mask) >> shift

def arithmetic_shift_right(n, bits, shift):
    """Арифметический сдвиг вправо (деление на 2^shift с округлением к -∞)"""
    # В Python >> для отрицательных чисел — арифметический
    return n >> shift

n = -8  # 11111000 в дополнительном коде (8 бит)
print(f"-8 >> 1 (arithmetic): {arithmetic_shift_right(n, 8, 1)}")  # -4
print(f"-8 >> 2 (arithmetic): {arithmetic_shift_right(n, 8, 2)}")  # -2

# Умножение на степень двойки (сдвиг влево):
n = 3
print(f"3 << 4 = {n << 4}")  # 48 (3 × 16)

# Деление на степень двойки (арифметический сдвиг вправо):
n = -7
print(f"-7 >> 1 = {n >> 1}")  # -4 (не -3! округление к -∞)
print(f"-7 // 2 = {n // 2}")  # -4 (Python // тоже округляет к -∞)
```

---

## 6. Хранение чисел в памяти: endianness

Для многобайтовых чисел важен порядок байт в памяти.

**Big-Endian** (сетевой порядок): старший байт по меньшему адресу.  
**Little-Endian** (x86/ARM): младший байт по меньшему адресу.

```python
import struct, sys

# Определение порядка байт системы
print(f"Порядок байт: {sys.byteorder}")  # 'little' на x86

n = 0x01020304  # 16909060

# Little-endian: 04 03 02 01
packed_le = struct.pack('<I', n)
print(f"Little-endian: {packed_le.hex()}")  # 04030201

# Big-endian: 01 02 03 04
packed_be = struct.pack('>I', n)
print(f"Big-endian:    {packed_be.hex()}")  # 01020304

# Конвертация порядка байт
def swap_bytes_32(n):
    """Смена порядка байт для 32-битного числа"""
    b = [(n >> (8 * i)) & 0xFF for i in range(4)]
    return sum(b[i] << (8 * (3 - i)) for i in range(4))

print(hex(swap_bytes_32(0x01020304)))  # 0x4030201

# htons, htonl — host to network short/long (используется в сетевом программировании)
import socket
print(hex(socket.htons(0x1234)))  # На little-endian: 0x3412
```

---

## 7. Числа с фиксированной точкой

До появления аппаратной поддержки FPU широко использовались числа с фиксированной точкой: часть бит — целая часть, часть — дробная.

```python
# Q16.16: 16 бит — целая часть, 16 бит — дробная
# Значение = raw_value / 2^16

FRAC_BITS = 16
FRAC_MULT = 1 << FRAC_BITS  # 65536

def float_to_q16_16(f):
    return int(f * FRAC_MULT)

def q16_16_to_float(q):
    return q / FRAC_MULT

# Умножение двух Q16.16 чисел:
def q16_16_mul(a, b):
    return (a * b) >> FRAC_BITS  # Результат нужно сдвинуть

pi_q = float_to_q16_16(3.14159)
e_q  = float_to_q16_16(2.71828)

product = q16_16_mul(pi_q, e_q)
print(f"π × e ≈ {q16_16_to_float(product):.5f}")  # ≈ 8.53973

# Применяется в: игровых движках (Unity использует Fixed<Q31>),
# DSP-процессорах, embedded-системах без FPU
```

---

## 8. Специальные значения и битовые паттерны

```python
import struct

# Максимальные и минимальные значения стандартных типов (C-совместимые)
import ctypes

INT8_MAX  = 2**7  - 1    # 127
INT8_MIN  = -(2**7)      # -128
INT16_MAX = 2**15 - 1    # 32767
INT32_MAX = 2**31 - 1    # 2147483647
INT64_MAX = 2**63 - 1    # 9223372036854775807

UINT8_MAX  = 2**8  - 1   # 255
UINT32_MAX = 2**32 - 1   # 4294967295

# Битовые паттерны-маркеры (magic numbers)
# 0xDEADBEEF — «мёртвая» память (используется в отладчиках)
# 0xCAFEBABE — заголовок Java class-файла
# 0x0A0D = '\r\n' — перенос строки Windows
DEAD_BEEF = 0xDEADBEEF
CAFE_BABE = 0xCAFEBABE

print(f"DEADBEEF = {DEAD_BEEF:032b}")
print(f"CAFEBABE = {CAFE_BABE:032b}")

# Проверка знака без ветвлений (branchless)
def sign_no_branch(x):
    """Возвращает 1 для x>0, 0 для x=0, -1 для x<0 без if"""
    # (x > 0) - (x < 0) — стандартный трюк
    return (x > 0) - (x < 0)

print([sign_no_branch(x) for x in [-5, -1, 0, 1, 5]])  # [-1, -1, 0, 1, 1]

# Абсолютное значение знакового числа без ветвлений:
def abs_no_branch(x, bits=32):
    mask = x >> (bits - 1)  # Все 1 для отрицательных, все 0 для положительных
    return (x + mask) ^ mask

print(abs_no_branch(-42))  # 42
print(abs_no_branch(42))   # 42
```

---

## 9. Подводные камни и распространённые ошибки

```python
# 1. Неопределённое поведение знаковых переполнений в C/C++
# В Python нет переполнения — числа BigInteger

# Эмуляция C-поведения:
def c_int32_add(a, b):
    """Эмуляция 32-битного знакового сложения C"""
    import ctypes
    return ctypes.c_int32(a + b).value

print(c_int32_add(2**31 - 1, 1))  # В C — UB, в ctypes — -2147483648

# 2. Нет точного MIN_INT для отрицания
# В 8-битном представлении: -(-128) = -128 (переполнение!)
print(c_int32_add(-(2**31), -1))  # UB в C — осторожно!

# 3. Сдвиг отрицательных чисел в C — UB
# В Python -- безопасно (арифметический сдвиг)
print(-1 >> 1)  # -1 в Python (арифметический)
# В C: (-1 >> 1) — implementation-defined behavior до C++20

# 4. Операторы сравнения со знаковыми/беззнаковыми
# В C: (int)-1 < (unsigned int)0 — FALSE! -1 конвертируется в UINT_MAX
import ctypes
a = ctypes.c_int32(-1).value
b = ctypes.c_uint32(0).value
# В C++ это сравнение промоутит -1 к unsigned!
```

---

## Заключение

Двоичное представление и дополнительный код — это фундамент целочисленной арифметики в компьютерах:

- **Дополнительный код** позволяет использовать одну схему сложения для знаковых и беззнаковых чисел
- **Endianness** определяет совместимость при обмене данными по сети и между системами
- **Переполнение** — корень большого числа уязвимостей (integer overflow → buffer overflow)
- **Битовые операции** — наиболее эффективный способ работы с флагами и масками

Понимание двоичного представления объясняет, почему `int8_max + 1 = -128`, почему беззнаковое `-1 > 0` и почему сетевой порядок байт называется «big-endian».

---

## Литература и источники

1. IEEE 754-2008. *IEEE Standard for Floating-Point Arithmetic*. IEEE. — Стандарт чисел с плавающей точкой.

2. Warren, H. S. (2012). *Hacker's Delight* (2nd ed.). Addison-Wesley. — Битовые трюки и целочисленная арифметика.

3. Goldberg, D. (1991). What every computer scientist should know about floating-point arithmetic. *ACM Computing Surveys*, 23(1), 5–48. https://dl.acm.org/doi/10.1145/103162.103163

4. Bryant, R. E., & O'Hallaron, D. R. (2015). *Computer Systems: A Programmer's Perspective* (3rd ed.). Pearson. Глава 2: Representing and Manipulating Information.

5. Patterson, D. A., & Hennessy, J. L. (2017). *Computer Organization and Design RISC-V Edition*. Morgan Kaufmann. Appendix B.

6. ISO/IEC 9899:2018. *C18 Standard*. — Спецификация языка C и поведение целочисленных операций.
