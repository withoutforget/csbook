# Булева алгебра: математика цифровой логики

## Введение

Булева алгебра — алгебраическая система, оперирующая двумя значениями: 0 (ложь) и 1 (истина). Разработанная Джорджем Булем в 1847 году как исчисление логики, она приобрела инженерное значение в 1937 году, когда Клод Шеннон в своей магистерской диссертации показал, что булева алгебра описывает поведение электрических реле и переключательных схем.

Сегодня булева алгебра является математическим фундаментом всей цифровой электроники: проектирование процессоров, оптимизация логических схем, минимизация логических функций — всё это задачи булевой алгебры.

---

## 1. Аксиомы булевой алгебры

Булева алгебра $(B, +, \cdot, ', 0, 1)$ — это множество $B$ с двумя бинарными операциями ($+$, OR и $\cdot$, AND), унарной операцией ($'$, NOT) и двумя выделенными элементами (0 и 1), удовлетворяющими аксиомам Хантингтона:

### Аксиомы

```
Коммутативность:    a + b = b + a       a · b = b · a
Дистрибутивность:  a·(b+c) = a·b + a·c  a+(b·c) = (a+b)·(a+c)
Единица:            a + 0 = a           a · 1 = a
Дополнение:         a + a' = 1          a · a' = 0
```

Из этих аксиом выводятся все остальные законы.

---

## 2. Теоремы булевой алгебры

```python
# Эмуляция для проверки теорем:
def verify_identity(f, g, n_vars=3):
    """Проверяет, что f и g дают одинаковые результаты для всех наборов входов"""
    for values in range(2**n_vars):
        bits = [(values >> i) & 1 for i in range(n_vars)]
        if f(*bits) != g(*bits):
            return False, bits
    return True, None

# Законы де Моргана:
# (a AND b)' = a' OR b'
# (a OR b)'  = a' AND b'
ok, _ = verify_identity(
    lambda a, b, c: int(not (a and b)),  # (a AND b)'
    lambda a, b, c: int((not a) or (not b)),  # a' OR b'
    n_vars=2
)
print(f"Де Морган: (a·b)' = a'+b': {ok}")  # True

# Идемпотентность: a + a = a
ok, _ = verify_identity(
    lambda a, b, c: a | a,
    lambda a, b, c: a,
    n_vars=1
)
print(f"Идемпотентность: a+a=a: {ok}")  # True
```

### Полный список теорем

| Закон | OR-форма | AND-форма |
|---|---|---|
| Идемпотентность | $a + a = a$ | $a \cdot a = a$ |
| Ноль/единица | $a + 1 = 1$ | $a \cdot 0 = 0$ |
| Поглощение | $a + (a \cdot b) = a$ | $a \cdot (a + b) = a$ |
| Ассоциативность | $(a+b)+c = a+(b+c)$ | $(a \cdot b) \cdot c = a \cdot (b \cdot c)$ |
| Двойное дополнение | $(a')' = a$ | — |
| Де Морган | $(a+b)' = a' \cdot b'$ | $(a \cdot b)' = a'+b'$ |

```python
# Закон поглощения: a + (a·b) = a
ok, _ = verify_identity(
    lambda a, b, c: a | (a & b),
    lambda a, b, c: a,
    n_vars=2
)
print(f"Поглощение: a+(a·b)=a: {ok}")  # True

# Двойное дополнение: (a')' = a
ok, _ = verify_identity(
    lambda a, b, c: int(not not a),  # (a')'
    lambda a, b, c: a,
    n_vars=1
)
print(f"Двойное дополнение: (a')'=a: {ok}")  # True

# Закон де Моргана 2: (a+b)' = a'·b'
ok, _ = verify_identity(
    lambda a, b, c: int(not (a or b)),
    lambda a, b, c: int((not a) and (not b)),
    n_vars=2
)
print(f"Де Морган: (a+b)'=a'·b': {ok}")  # True
```

---

## 3. Функции булевой алгебры и таблицы истинности

Любая логическая функция n переменных принимает 2^n различных наборов входных значений. Всего существует 2^(2^n) различных функций n переменных.

```python
# Для 2 переменных: 16 различных функций
print("Все функции двух переменных:")
functions_2var = {}
for func_num in range(16):
    f = []
    for (a, b) in [(0,0), (0,1), (1,0), (1,1)]:
        idx = (a << 1) | b  # a*2 + b
        bit = (func_num >> idx) & 1
        f.append(bit)
    functions_2var[func_num] = f

named = {
    0b0000: "FALSE", 0b0001: "AND",  0b0010: "A∧¬B", 0b0011: "A",
    0b0100: "¬A∧B", 0b0101: "B",    0b0110: "XOR",  0b0111: "OR",
    0b1000: "NOR",  0b1001: "XNOR", 0b1010: "¬B",   0b1011: "A→B",
    0b1100: "¬A",   0b1101: "B→A",  0b1110: "NAND", 0b1111: "TRUE"
}

for num, name in named.items():
    print(f"  {num:04b} ({name}): {functions_2var[num]}")
```

---

## 4. Нормальные формы

Любую булеву функцию можно представить в стандартных формах.

### Минтерм и макстерм

**Минтерм** (minterms) — произведение (AND) всех переменных, где каждая переменная входит либо прямо, либо в дополненном виде. Минтерм mᵢ соответствует единственному набору входов, при котором он равен 1.

**Макстерм** (maxterms) — сумма (OR) всех переменных. Макстерм Mᵢ равен 0 только при одном наборе входов.

### ДНФ (Disjunctive Normal Form)

Дизъюнкция минтермов для всех наборов входов, при которых функция равна 1:

```
f(a,b,c) = Σm(1, 3, 5, 7) = m₁ + m₃ + m₅ + m₇
```

```python
def build_dnf(truth_table):
    """
    truth_table: список значений функции для входов 00, 01, 10, 11...
    Возвращает ДНФ как список минтермов.
    """
    n_vars = int(len(truth_table) ** 0.5 + 0.5).bit_length() - 1
    # Точнее:
    import math
    n_vars = int(math.log2(len(truth_table)))
    
    minterms = []
    for i, val in enumerate(truth_table):
        if val == 1:
            # Формируем минтерм: для каждой переменной
            term = []
            for j in range(n_vars - 1, -1, -1):
                bit = (i >> j) & 1
                var = chr(ord('a') + (n_vars - 1 - j))
                term.append(var if bit else f"¬{var}")
            minterms.append("·".join(term))
    
    return " + ".join(minterms) if minterms else "0"

# Функция XOR для двух переменных
truth_table_xor = [0, 1, 1, 0]  # для (a=0,b=0), (a=0,b=1), (a=1,b=0), (a=1,b=1)
print(f"XOR = {build_dnf(truth_table_xor)}")
# XOR = ¬a·b + a·¬b
```

### КНФ (Conjunctive Normal Form)

Конъюнкция макстермов для всех наборов входов, при которых функция равна 0.

---

## 5. Минимизация: карты Карно

Карта Карно (K-map) — метод визуальной минимизации булевых функций. Для n переменных карта имеет 2^n клеток, расположенных так, что соседние клетки отличаются ровно одним битом (код Грея).

```python
# Минимизация функции 4 переменных через карту Карно
# (примитивная реализация для демонстрации)

def karnaugh_group_2(f, a, b):
    """Находит группы из 2 клеток (пары) в карте Карно 2x2"""
    groups = []
    # Горизонтальные пары
    if f[a][b] == 1 and f[a][(b+1)%2] == 1:
        groups.append(((a,b), (a,(b+1)%2)))
    # Вертикальные пары
    if f[a][b] == 1 and f[(a+1)%2][b] == 1:
        groups.append(((a,b), ((a+1)%2,b)))
    return groups

# Карта Карно для 3 переменных (a, bc):
# ab\c | 0 | 1
#  00  | 0 | 0
#  01  | 0 | 1
#  11  | 1 | 1
#  10  | 1 | 1
# Функция: a'·b·c + a·b·c + a·b'·c + a·b'·c' = a + bc

# Алгоритм Quine–McCluskey для более сложных случаев
def quine_mccluskey(minterms, n_vars):
    """
    Упрощённый алгоритм Куайна-МакКласки.
    Находит простые импликанты и минимальное покрытие.
    """
    def count_ones(n):
        return bin(n).count('1')
    
    def combine(a, b):
        """Объединяет два минтерма, если они отличаются ровно в 1 бите"""
        diff = a ^ b
        if diff & (diff - 1) == 0:  # diff — степень двойки (один бит)
            return a & b, diff  # результат и позиция отличия
        return None, None
    
    # Группируем по числу единиц
    groups = {}
    for m in minterms:
        k = count_ones(m)
        groups.setdefault(k, []).append(m)
    
    # Объединяем соседние группы
    prime_implicants = set()
    current_groups = {k: set(v) for k, v in groups.items()}
    
    while True:
        next_groups = {}
        combined = set()
        
        for k in sorted(current_groups.keys()):
            if k + 1 in current_groups:
                for a in current_groups[k]:
                    for b in current_groups[k+1]:
                        result, pos = combine(a & ((1<<n_vars)-1), b & ((1<<n_vars)-1))
                        if result is not None:
                            # Помечаем комбинацию с маской
                            combined.add(a)
                            combined.add(b)
                            next_groups.setdefault(k, set()).add(result | (pos << n_vars))
        
        # Простые импликанты — не участвующие в объединении
        for k, group in current_groups.items():
            for m in group:
                if m not in combined:
                    prime_implicants.add(m)
        
        if not next_groups:
            break
        current_groups = next_groups
    
    return prime_implicants

# Пример: f = Σm(0, 1, 3, 7) для 3 переменных
minterms = [0, 1, 3, 7]
pis = quine_mccluskey(minterms, 3)
print(f"Простые импликанты: {[bin(p) for p in pis]}")
```

---

## 6. Булева алгебра в программировании

### Битовые операции

```python
a = 0b10110100  # 180
b = 0b01101110  # 110

# Побитовое И (AND)
print(f"a & b  = {a & b:08b}  ({a & b})")   # 00100100 = 36

# Побитовое ИЛИ (OR)
print(f"a | b  = {a | b:08b}  ({a | b})")   # 11111110 = 254

# Побитовое XOR
print(f"a ^ b  = {a ^ b:08b}  ({a ^ b})")   # 11011010 = 218

# Побитовое НЕ
print(f"~a     = {(~a) & 0xFF:08b}  ({(~a) & 0xFF})")  # 01001011 = 75

# Сдвиги
print(f"a >> 2 = {a >> 2:08b}  ({a >> 2})")  # 00101101 = 45
print(f"a << 1 = {(a << 1) & 0xFF:08b}  ({(a << 1) & 0xFF})")  # 01101000
```

### Практические паттерны

```python
# 1. Проверка конкретного бита
def bit_is_set(value, bit_pos):
    return bool(value & (1 << bit_pos))

# 2. Установка бита
def set_bit(value, bit_pos):
    return value | (1 << bit_pos)

# 3. Сброс бита
def clear_bit(value, bit_pos):
    return value & ~(1 << bit_pos)

# 4. Переключение бита
def toggle_bit(value, bit_pos):
    return value ^ (1 << bit_pos)

# Пример: флаги разрешений (как в Unix chmod)
READ  = 0b100  # 4
WRITE = 0b010  # 2
EXEC  = 0b001  # 1

def permissions_str(perms):
    return (
        ('r' if perms & READ else '-') +
        ('w' if perms & WRITE else '-') +
        ('x' if perms & EXEC else '-')
    )

user_perms = READ | WRITE | EXEC  # 7 = rwx
group_perms = READ | EXEC          # 5 = r-x
other_perms = READ                 # 4 = r--

print(f"User:  {permissions_str(user_perms)}")   # rwx
print(f"Group: {permissions_str(group_perms)}")  # r-x
print(f"Other: {permissions_str(other_perms)}")  # r--
print(f"chmod {user_perms}{group_perms}{other_perms}")  # chmod 754

# XOR для обмена без временной переменной (классический трюк)
x, y = 10, 20
x ^= y  # x = x XOR y
y ^= x  # y = y XOR (x XOR y) = old_x
x ^= y  # x = (x XOR y) XOR old_x = old_y
print(f"x={x}, y={y}")  # x=20, y=10

# Проверка чётности числа единичных бит
def parity(n):
    """XOR всех бит — чётность"""
    result = 0
    while n:
        result ^= n & 1
        n >>= 1
    return result

# Или быстро:
def parity_fast(n):
    n ^= n >> 16
    n ^= n >> 8
    n ^= n >> 4
    n ^= n >> 2
    n ^= n >> 1
    return n & 1

print(parity(0b10110001))  # 4 единицы — чётность 0
print(parity(0b10110011))  # 5 единиц — чётность 1
```

### Битовые маски для работы с флагами

```python
# Битовые поля: эффективное хранение множества флагов
import enum

class Permission(enum.IntFlag):
    NONE    = 0
    READ    = 1 << 0   # 1
    WRITE   = 1 << 1   # 2
    EXECUTE = 1 << 2   # 4
    ADMIN   = 1 << 3   # 8

# Комбинирование флагов
user = Permission.READ | Permission.WRITE
print(user)                  # Permission.READ|WRITE
print(user & Permission.EXECUTE)  # Permission.NONE — нет права выполнения
print(bool(user & Permission.READ))  # True — есть право чтения

# Добавление права
user |= Permission.EXECUTE
print(user)  # Permission.READ|WRITE|EXECUTE

# Снятие права
user &= ~Permission.WRITE
print(user)  # Permission.READ|EXECUTE
```

---

## 7. Синтез и анализ схем

### Синтез: от функции к схеме

Задача синтеза: по заданной таблице истинности или алгебраическому выражению получить минимальную логическую схему.

```python
# Пример: синтез мультиплексора 2-к-1 через булеву алгебру
# MUX(sel, a, b) = (NOT sel AND a) OR (sel AND b)
# = ¬sel·a + sel·b

def mux_synthesis(sel, a, b):
    not_sel = NOT(sel)
    term1 = AND(not_sel, a)
    term2 = AND(sel, b)
    return OR(term1, term2)

# Проверка
for sel in [0, 1]:
    for a in [0, 1]:
        for b in [0, 1]:
            expected = a if sel == 0 else b
            result = mux_synthesis(sel, a, b)
            assert result == expected

print("Мультиплексор синтезирован корректно!")
```

---

## 8. Булева алгебра в оптимизации компилятора

Компиляторы используют законы булевой алгебры для оптимизации кода:

```python
# Примеры оптимизаций компилятора:

# 1. Замена умножения на степень двойки сдвигом
# x * 8 → x << 3 (быстрее на большинстве CPU)
x = 10
print(x * 8 == x << 3)  # True

# 2. Замена деления на степень двойки сдвигом (для беззнаковых)
# x / 4 → x >> 2
print(20 // 4 == 20 >> 2)  # True

# 3. Проверка на чётность: x % 2 == 0 → (x & 1) == 0
def is_even_slow(x): return x % 2 == 0
def is_even_fast(x): return (x & 1) == 0
print(all(is_even_slow(x) == is_even_fast(x) for x in range(100)))  # True

# 4. Вычисление x mod 2^n: x % (2^n) → x & (2^n - 1)
def mod_power_of_2(x, n):
    return x & ((1 << n) - 1)  # быстрее чем x % (1 << n)

print(100 % 16 == mod_power_of_2(100, 4))  # True (100 mod 16 = 4)

# 5. Deadcode elimination через константный булев анализ
# if (x & 0) != 0: ...  → всегда false, блок удаляется
# if (x | ~0) != 0: ... → всегда true, блок всегда выполняется
```

---

## Заключение

Булева алгебра — это язык цифровых систем. Её практические применения охватывают:

- **Схемотехнику**: проектирование процессоров и FPGA
- **Оптимизацию компилятора**: замена операций на эквивалентные, более быстрые
- **Системное программирование**: битовые флаги, маски, флаги разрешений
- **Сетевое программирование**: IP-маски, CIDR, фильтрация пакетов
- **Крипотографию**: логические операции в блочных шифрах (AES использует XOR)

Законы де Моргана, поглощения, дистрибутивность — это не просто теория, а инструменты упрощения выражений в реальном коде.

---

## Литература и источники

1. Boole, G. (1847). *The Mathematical Analysis of Logic*. Cambridge. — Оригинальный труд Буля.

2. Shannon, C. E. (1938). A symbolic analysis of relay and switching circuits. *Transactions of the American Institute of Electrical Engineers*, 57(12), 713–723. — Применение булевой алгебры к электронике.

3. Mano, M. M., & Ciletti, M. D. (2012). *Digital Design* (5th ed.). Pearson. — Детальное изложение булевой алгебры в схемотехнике.

4. Roth, C. H., & Kinney, L. L. (2013). *Fundamentals of Logic Design* (7th ed.). Cengage. — Карты Карно, алгоритм Куайна-МакКласки.

5. Warren, H. S. (2012). *Hacker's Delight* (2nd ed.). Addison-Wesley. — Битовые трюки и оптимизации.

6. Knuth, D. E. (2011). *The Art of Computer Programming*, Vol. 4A. Addison-Wesley. — Алгоритмы на битах и булевых функциях.

7. Intel 64 and IA-32 Architectures Software Developer's Manual. Intel Corporation. — Реальные битовые инструкции процессора.
