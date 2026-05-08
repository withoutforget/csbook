# IEEE 754: числа с плавающей точкой

## Введение

«0.1 + 0.2 ≠ 0.3» — это, пожалуй, самый знаменитый «баг» в программировании, с которым сталкиваются все разработчики. На самом деле это не баг, а следствие строгого стандарта — IEEE 754, принятого в 1985 году. Понимание IEEE 754 необходимо для грамотной работы с числами: финансовые вычисления, научные расчёты, машинное обучение — везде важно понимать, что float не является точным числом, и знать, когда это имеет значение.

---

## 1. Проблема представления вещественных чисел

Вещественных чисел несчётно много. Памяти компьютера конечно. Следовательно, мы можем точно представить лишь конечное подмножество вещественных чисел. Стандарт IEEE 754 определяет, какое именно подмножество.

```python
# Знаменитая проблема:
print(0.1 + 0.2)        # 0.30000000000000004
print(0.1 + 0.2 == 0.3) # False!

# Почему? 0.1 в двоичной системе — бесконечная периодическая дробь:
# 0.1 = 0.0001100110011001100... (2)
# Примерно как 1/3 = 0.333... в десятичной

from decimal import Decimal
print(Decimal(0.1))  # Точное значение, которое хранится
# 0.1000000000000000055511151231257827021181583404541015625

print(Decimal(0.2))  # Тоже не точно!
# 0.200000000000000011102230246251565404236316680908203125

# Решение для финансовых расчётов: использовать Decimal или int (в центах)
from decimal import Decimal
d1 = Decimal('0.1')  # Строка, не float!
d2 = Decimal('0.2')
print(d1 + d2)        # 0.3 (точно!)
print(d1 + d2 == Decimal('0.3'))  # True
```

---

## 2. Формат IEEE 754

### Структура числа с плавающей точкой

Число с плавающей точкой представляется в нормализованной научной нотации с основанием 2:

```
(-1)^знак × 1.мантисса × 2^(экспонента - смещение)
```

#### Форматы:

| Тип | Бит | Знак | Экспонента | Мантисса | Смещение |
|---|---|---|---|---|---|
| float16 (half) | 16 | 1 | 5 | 10 | 15 |
| float32 (single) | 32 | 1 | 8 | 23 | 127 |
| float64 (double) | 64 | 1 | 11 | 52 | 1023 |
| float128 (extended) | 128 | 1 | 15 | 112 | 16383 |

```python
import struct

def float_to_bits(f):
    """Возвращает двоичное представление float32"""
    packed = struct.pack('>f', f)
    bits = int.from_bytes(packed, 'big')
    return f"{bits:032b}"

def decode_float32(f):
    """Декодирует float32 в компоненты"""
    packed = struct.pack('>f', f)
    bits = int.from_bytes(packed, 'big')
    
    sign_bit = (bits >> 31) & 1
    exponent_bits = (bits >> 23) & 0xFF
    mantissa_bits = bits & 0x7FFFFF
    
    sign = (-1) ** sign_bit
    
    if exponent_bits == 0:
        # Денормализованное число
        exponent = 1 - 127  # = -126
        mantissa = mantissa_bits / (1 << 23)  # без неявной 1
    elif exponent_bits == 0xFF:
        # NaN или Infinity
        if mantissa_bits == 0:
            return f"{'+'  if sign_bit == 0 else '-'}Infinity"
        else:
            return "NaN"
    else:
        exponent = exponent_bits - 127
        mantissa = 1 + mantissa_bits / (1 << 23)  # неявная 1
    
    return {
        'sign': sign,
        'exponent': exponent,
        'mantissa': mantissa,
        'value': sign * mantissa * (2 ** exponent)
    }

# Разбор числа 0.1
f = 0.1
print(f"0.1 = {float_to_bits(f)}")
# 0 01111011 10011001100110011001101
# ^   ^           ^
# Знак Экспонента Мантисса
info = decode_float32(f)
print(f"Знак: {info['sign']}, Экспонента: {info['exponent']}, Мантисса: {info['mantissa']:.20f}")
print(f"Реальное значение: {info['value']:.20f}")
```

### Неявная единица (implicit leading 1)

Для нормализованных чисел (экспонента ≠ 0 и ≠ 255) мантисса всегда начинается с 1. Эта единица не хранится — она подразумевается. Это позволяет использовать один дополнительный бит точности.

```python
def float_to_components_verbose(f):
    """Подробное описание компонентов float64"""
    packed = struct.pack('>d', f)
    bits = int.from_bytes(packed, 'big')
    
    sign = (bits >> 63) & 1
    exp = (bits >> 52) & 0x7FF
    mantissa = bits & ((1 << 52) - 1)
    
    print(f"Число: {f}")
    print(f"Биты: {bits:064b}")
    print(f"  Знак:      {'+'  if sign == 0 else '-'}")
    print(f"  Экспонента: {exp} (смещённая), {exp - 1023} (реальная)")
    print(f"  Мантисса:  {mantissa:052b}")
    print(f"  Мантисса:  1.{mantissa:052b} (с неявной 1)")
    
    # Реконструкция
    mantissa_val = 1.0 + mantissa / (1 << 52)
    value = (-1)**sign * mantissa_val * (2**(exp - 1023))
    print(f"  Реконструкция: {(-1)**sign} × {mantissa_val:.20f} × 2^{exp-1023}")
    print(f"  = {value:.20f}")

float_to_components_verbose(3.14159265358979)
```

---

## 3. Специальные значения

IEEE 754 резервирует специальные битовые паттерны для особых случаев.

### Infinity

```python
import math

pos_inf = float('inf')
neg_inf = float('-inf')

print(pos_inf + 1)     # inf
print(pos_inf * -1)    # -inf
print(1 / pos_inf)     # 0.0
print(pos_inf - pos_inf)  # nan (!) — неопределённость ∞ - ∞

# Проверка:
print(math.isinf(pos_inf))  # True
print(math.isinf(1.0))      # False
```

### NaN (Not a Number)

NaN — результат неопределённых операций: 0/0, √(-1), ∞-∞, ∞×0.

Ключевое свойство: **NaN не равен ничему, в том числе самому себе**.

```python
nan = float('nan')

print(nan == nan)     # False (!) — единственная такая ситуация в Python
print(nan != nan)     # True
print(nan < 0)        # False
print(nan > 0)        # False
print(nan == 0)       # False

# Правильная проверка на NaN:
print(math.isnan(nan))  # True
import numpy as np
print(np.isnan(nan))    # True

# NaN «заразен»: любая операция с NaN даёт NaN
print(nan + 1)    # nan
print(nan * 0)    # nan (не 0!)
print(nan > -float('inf'))  # False

# Практический пример: NaN в данных ML
import numpy as np
data = np.array([1.0, 2.0, float('nan'), 4.0, 5.0])
print(f"Среднее: {np.mean(data)}")      # nan — NaN «заражает» среднее!
print(f"Без NaN: {np.nanmean(data)}")   # 3.0 — функция ignores NaN
```

### Денормализованные числа (Subnormals)

Когда экспонента = 0, число денормализовано: нет неявной единицы, экспонента фиксирована на -126 (для float32). Это позволяет представлять очень маленькие числа около нуля.

```python
# Самое маленькое нормализованное float32:
import sys
print(sys.float_info.min)    # ≈ 2.2e-308 (для float64)

# Самое маленькое положительное float64:
print(sys.float_info.min * sys.float_info.epsilon)  # ≈ 5e-324 (subnormal)

# Денормализованные числа работают медленнее!
# На некоторых архитектурах обработка суббнормальных даёт x100 замедление
# В ML: флеш-в-ноль (Flush-to-Zero, FTZ) режим процессора
```

---

## 4. Точность и машинный эпсилон

**Машинный эпсилон (ε)** — наименьшее число, такое что `1.0 + ε ≠ 1.0`.

```python
# Машинный эпсилон для float64:
eps = sys.float_info.epsilon
print(f"Машинный эпсилон float64: {eps}")  # ≈ 2.22e-16

print(1.0 + eps == 1.0)       # False
print(1.0 + eps/2 == 1.0)     # True (половина эпсилона «исчезает»)

# Для float32:
import numpy as np
eps32 = np.finfo(np.float32).eps
print(f"Машинный эпсилон float32: {eps32}")  # ≈ 1.19e-7

# Примерная точность:
# float32: ~7 десятичных цифр
# float64: ~15-16 десятичных цифр

# Пример накопления ошибки:
n = 10000000
s1 = sum(0.1 for _ in range(n))
s2 = 0.1 * n
print(f"Сумма 10^7 раз 0.1: {s1:.10f}")    # накопилась ошибка
print(f"0.1 × 10^7:          {s2:.10f}")
print(f"Разница:             {abs(s1 - s2):.2e}")
```

---

## 5. Проблемы и паттерны правильного использования

### Сравнение float-чисел

```python
import math

# НЕПРАВИЛЬНО:
def bad_equal(a, b):
    return a == b

print(bad_equal(0.1 + 0.2, 0.3))  # False

# ПРАВИЛЬНО: сравнение с допуском
def nearly_equal(a, b, rel_tol=1e-9, abs_tol=1e-12):
    """
    rel_tol: относительный допуск (для больших чисел)
    abs_tol: абсолютный допуск (для чисел около нуля)
    """
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)

print(nearly_equal(0.1 + 0.2, 0.3))         # True
print(math.isclose(0.1 + 0.2, 0.3))         # True
print(math.isclose(1e10 + 1, 1e10))         # True (rel_tol=1e-9)
print(math.isclose(1e10 + 1, 1e10, rel_tol=0, abs_tol=0.5))  # False
```

### Потеря значимости (Catastrophic Cancellation)

```python
# Вычитание близких чисел теряет значимые биты
a = 1.000000001
b = 1.000000000
diff = a - b
print(f"a - b = {diff:.20f}")  # Правильно: 1e-9
print(f"Но точность: {diff:.6e}")  # Теряем 9 из 15 цифр!

# Пример: квадратное уравнение
import math

def quadratic_unstable(a, b, c):
    """Числено нестабильная формула"""
    D = b**2 - 4*a*c
    if D < 0:
        return None
    x1 = (-b + math.sqrt(D)) / (2*a)
    x2 = (-b - math.sqrt(D)) / (2*a)
    return x1, x2

def quadratic_stable(a, b, c):
    """Числено стабильная формула (без вычитания близких чисел)"""
    D = b**2 - 4*a*c
    if D < 0:
        return None
    sqrt_D = math.sqrt(D)
    if b >= 0:
        x1 = (-b - sqrt_D) / (2*a)
        x2 = c / (a * x1)  # Избегаем вычитания через теорему Виета
    else:
        x1 = (-b + sqrt_D) / (2*a)
        x2 = c / (a * x1)
    return x1, x2

# Тестируем с b большим и c маленьким (d близок к b):
a, b, c = 1, -10000000, 1
x_unstable = quadratic_unstable(a, b, c)
x_stable = quadratic_stable(a, b, c)
print(f"Нестабильное: {x_unstable}")
print(f"Стабильное:   {x_stable}")
```

### Ассоциативность нарушена!

```python
# float не ассоциативны!
a, b, c = 1e15, -1e15, 1

print((a + b) + c)  # 1.0 (правильно!)
print(a + (b + c))  # 0.0 (неправильно!)

# Это важно для распараллеливания: результат суммы зависит от порядка
# Поэтому параллельное reduce(+) на float может давать другой результат!
```

### Суммирование: алгоритм Кехана

```python
def kahan_sum(values):
    """
    Алгоритм Кехана: компенсационное суммирование.
    Значительно снижает накопленную ошибку при сложении многих чисел.
    """
    total = 0.0
    compensation = 0.0  # Накопленная ошибка
    for x in values:
        y = x - compensation        # Компенсируем предыдущую ошибку
        t = total + y               # Складываем
        compensation = (t - total) - y  # Вычисляем новую ошибку
        total = t
    return total

# Сравнение точности:
n = 1000000
data = [0.1] * n

naive = sum(data)                # Наивное суммирование
kahan = kahan_sum(data)         # Суммирование Кехана
exact = n * 0.1                  # «Точное» значение

print(f"Наивное: {naive:.10f}")  # Накопилась ошибка
print(f"Кехан:   {kahan:.10f}") # Более точно
print(f"Ожидаем: {exact:.10f}") # 100000.0
```

---

## 6. Числа с плавающей точкой в ML

В машинном обучении используются форматы пониженной точности для ускорения вычислений:

```python
import numpy as np

# Сравнение форматов:
formats = [
    ('float64', np.float64, np.finfo(np.float64)),
    ('float32', np.float32, np.finfo(np.float32)),
    ('float16', np.float16, np.finfo(np.float16)),
]

for name, dtype, info in formats:
    print(f"\n{name}:")
    print(f"  Размер: {info.bits} бит")
    print(f"  Эпсилон: {info.eps:.2e}")
    print(f"  Диапазон: [{info.min:.2e}, {info.max:.2e}]")
    print(f"  Мантисса: ~{info.precision} десятичных цифр")

# bfloat16: специальный формат ML (1 знак + 8 бит экспоненты + 7 мантисса)
# Тот же диапазон, что float32, но меньше точность
# Используется в TPU (Google) и многих GPU

# float8 (E4M3, E5M2): совсем новый формат для LLM-инференса
```

---

## 7. Специфика аппаратного вычисления

### FMA (Fused Multiply-Add)

Операция `a*b + c` вычисляется без промежуточного округления:

```python
import math

a, b, c = 1.0000001, 1.0000001, -1.0000002

# Без FMA: две операции, два округления
result_nofma = a * b + c
print(f"Без FMA: {result_nofma:.2e}")  # Может быть 0 (потеря значимости)

# С FMA: одно вычисление, одно округление
result_fma = math.fma(a, b, c)  # Python 3.13+
# В numpy:
result_fma_np = np.float64(a) * np.float64(b) + np.float64(c)
print(f"С FMA: {result_fma_np:.2e}")  # Более точно
```

### Режимы округления

IEEE 754 определяет 4 режима округления:

```python
import decimal

# Round Half to Even (банковское округление, по умолчанию):
decimal.getcontext().rounding = decimal.ROUND_HALF_EVEN
print(decimal.Decimal('2.5').to_integral_value())  # 2 (к чётному!)
print(decimal.Decimal('3.5').to_integral_value())  # 4 (к чётному!)

# Round Half Up (обычное):
decimal.getcontext().rounding = decimal.ROUND_HALF_UP
print(decimal.Decimal('2.5').to_integral_value())  # 3

# Round Toward Zero (truncation):
decimal.getcontext().rounding = decimal.ROUND_DOWN
print(decimal.Decimal('-2.7').to_integral_value())  # -2

# Round Toward +Infinity:
decimal.getcontext().rounding = decimal.ROUND_CEILING
print(decimal.Decimal('-2.3').to_integral_value())  # -2

# Round Toward -Infinity (floor):
decimal.getcontext().rounding = decimal.ROUND_FLOOR
print(decimal.Decimal('-2.3').to_integral_value())  # -3
```

---

## 8. Когда использовать float, когда — нет

```python
# НЕ используйте float для:
# 1. Финансовых вычислений (деньги, налоги)
from decimal import Decimal, ROUND_HALF_UP

price = Decimal('9.99')
tax_rate = Decimal('0.08')
tax = (price * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
print(f"Цена: {price}, Налог: {tax}, Итого: {price + tax}")
# Цена: 9.99, Налог: 0.80, Итого: 10.79

# 2. Точных дискретных количеств
# Считайте в копейках/центах (int), не в рублях/долларах (float)
price_cents = 999    # 9.99 рублей в копейках
tax_cents = (price_cents * 8) // 100  # 8% налог, без float
total_cents = price_cents + tax_cents
print(f"Итого: {total_cents // 100}.{total_cents % 100:02d} руб.")

# ИСПОЛЬЗУЙТЕ float для:
# 1. Физических измерений (до 15 значимых цифр достаточно)
# 2. Машинного обучения (float32 достаточно, float16 — часто)
# 3. Компьютерной графики
# 4. Научных вычислений
import numpy as np

# float64 достаточен для большинства научных расчётов
G = 6.674e-11  # гравитационная постоянная
M_earth = 5.972e24  # масса Земли
R_earth = 6.371e6  # радиус Земли

g_surface = G * M_earth / R_earth**2
print(f"Ускорение свободного падения: {g_surface:.4f} м/с²")  # 9.8196
```

---

## Заключение

IEEE 754 — это тонко сбалансированный компромисс между точностью, диапазоном, скоростью и аппаратной сложностью. Ключевые выводы:

1. **Float — не действительные числа**: они представляют конечное подмножество рациональных
2. **Сравнение float**: всегда через допуск (`math.isclose`), никогда через `==`
3. **Деньги**: никогда float, только `Decimal` или целые в минимальных единицах
4. **Порядок операций важен**: суммирование не ассоциативно, это влияет на параллельные вычисления
5. **NaN заразен**: одно NaN в данных заражает все вычисления — всегда проверяйте

---

## Литература и источники

1. IEEE 754-2008. *IEEE Standard for Floating-Point Arithmetic*. IEEE. — Официальный стандарт.

2. Goldberg, D. (1991). What every computer scientist should know about floating-point arithmetic. *ACM Computing Surveys*, 23(1), 5–48. https://dl.acm.org/doi/10.1145/103162.103163 — Обязательное чтение.

3. Muller, J.-M., et al. (2018). *Handbook of Floating-Point Arithmetic* (2nd ed.). Birkhäuser. — Фундаментальная монография.

4. Kahan, W. (1965). Further remarks on reducing truncation errors. *Communications of the ACM*, 8(1), 40. — Алгоритм компенсационного суммирования Кехана.

5. Higham, N. J. (2002). *Accuracy and Stability of Numerical Algorithms* (2nd ed.). SIAM. — Численная устойчивость алгоритмов.

6. Overton, M. L. (2001). *Numerical Computing with IEEE Floating Point Arithmetic*. SIAM. — Практика IEEE 754.

7. The Floating-Point Guide. https://floating-point-gui.de/ — Доступный онлайн-ресурс о плавающей точке.
