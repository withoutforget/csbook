# Лямбда-исчисление: корни функционального программирования

## Введение

Лямбда-исчисление (λ-исчисление) — формальная система, разработанная Алонзо Чёрчем в 1930-х годах для изучения вычислимости. Параллельно с машиной Тьюринга, λ-исчисление определяет, что значит «вычислить». Оба формализма эквивалентны (тезис Чёрча–Тьюринга), но λ-исчисление обладает исключительной элегантностью: всего три конструкции — и полная вычислительная мощность.

Для разработчика λ-исчисление — это не историческая курьёзность. Это теоретический фундамент функционального программирования (Haskell, Clojure, Erlang), систем типов (Hindley–Milner), реализации функций высшего порядка, замыканий и currying.

---

## 1. Синтаксис λ-исчисления

Язык λ-исчисления чрезвычайно прост. Существуют только три типа выражений (λ-термов):

```
M ::= x          — переменная
    | λx.M       — абстракция (анонимная функция)
    | M N        — применение (вызов функции)
```

Примеры λ-термов:
- $x$ — переменная $x$
- $\lambda x.\, x$ — тождественная функция (identity)
- $\lambda x.\,\lambda y.\, x$ — функция двух аргументов, возвращающая первый
- $(\lambda x.\, x)\, y$ — применение identity к $y$

```python
# Лямбда в Python — прямое воплощение λ-исчисления
identity = lambda x: x
const = lambda x: (lambda y: x)  # λx.λy.x
apply = lambda f: (lambda x: f(x))  # λf.λx.f x

print(identity(42))       # 42
print(const(10)(20))      # 10 — возвращает первый аргумент
print(apply(identity)(5)) # 5
```

---

## 2. Редукция: вычисление в λ-исчислении

Вычисление в λ-исчислении — это применение правил редукции.

### α-редукция (переименование)

Переменные в λ-абстракции можно переименовывать:

$$\lambda x.\, x \;\equiv_\alpha\; \lambda y.\, y \;\equiv_\alpha\; \lambda z.\, z$$

Все эти термы — одна и та же тождественная функция.

### β-редукция (вычисление)

Применение функции к аргументу:

$$(\lambda x.\, M)\, N \;\to_\beta\; M[x := N]$$

Подставляем $N$ вместо свободных вхождений $x$ в $M$.

$$(\lambda x.\, x + 1)\, 5 \;\to_\beta\; 5 + 1 \;\to\; 6$$

$$(\lambda x.\,\lambda y.\, x + y)\, 3\, 4 \;\to_\beta\; (\lambda y.\, 3 + y)\, 4 \;\to_\beta\; 3 + 4 \;\to\; 7$$

### η-редукция (экстенсиональность)

$$\lambda x.\, f\, x \;=_\eta\; f \quad \text{(если } x \text{ не входит свободно в } f\text{)}$$

«Функция, которая применяет $f$ к своему аргументу» эквивалентна $f$ самой.

```python
# В Python:
f = lambda x: x * 2

# eta-эквивалентны:
eta_expanded = lambda x: f(x)
eta_reduced = f

print(eta_expanded(5))  # 10
print(eta_reduced(5))   # 10

# Это объясняет, почему в Haskell можно писать:
# map double list
# вместо:
# map (\x -> double x) list
```

---

## 3. Комбинаторы и чистое λ-исчисление

Комбинатор — λ-терм без свободных переменных.

### Базовые комбинаторы

```python
# I (Identity): λx.x
I = lambda x: x

# K (Kestrel / Constant): λx.λy.x
K = lambda x: lambda y: x

# S (Starling / Substitution): λx.λy.λz.x z (y z)
S = lambda x: lambda y: lambda z: x(z)(y(z))

# KI = K I: λx.λy.y — возвращает второй аргумент
KI = K(I)

print(I(42))       # 42
print(K(1)(2))     # 1
print(KI(1)(2))    # 2

# SKK = I (это можно доказать через β-редукцию)
SKK = S(K)(K)
print(SKK(42))     # 42 — тоже identity!
```

**Теорема**: комбинаторы S и K образуют **полный базис** — любой λ-терм может быть выражен через S и K.

Это означает, что если у языка есть только два примитива — S и K — он вычислительно полный. Это ставит под сомнение «необходимость» большинства синтаксического сахара.

### Комбинаторы B, C, W

```python
# B (Bluebird / Composition): λf.λg.λx.f(g x) — компоновка функций
B = lambda f: lambda g: lambda x: f(g(x))

# C (Cardinal / Flip): λf.λa.λb.f b a — меняет аргументы местами
C = lambda f: lambda a: lambda b: f(b)(a)

# W (Warbler / Duplicate): λf.λx.f x x — дублирует аргумент
W = lambda f: lambda x: f(x)(x)

# Пример B — компоновка:
add1 = lambda x: x + 1
times2 = lambda x: x * 2
add1_then_times2 = B(times2)(add1)
print(add1_then_times2(5))  # (5+1)*2 = 12

# Пример C — flip:
subtract = lambda x: lambda y: x - y
flipped_subtract = C(subtract)
print(subtract(10)(3))        # 7 (10 - 3)
print(flipped_subtract(3)(10)) # 7 (10 - 3)  — аргументы поменялись местами
```

---

## 4. Числа Чёрча

В λ-исчислении нет встроенных чисел — их можно закодировать. Числа Чёрча кодируют натуральное число $n$ как функцию, применяющую другую функцию $n$ раз:

- $0 = \lambda f.\,\lambda x.\, x$ — применить $f$ ноль раз
- $1 = \lambda f.\,\lambda x.\, f\, x$ — применить $f$ один раз
- $2 = \lambda f.\,\lambda x.\, f(f\, x)$ — применить $f$ дважды
- $n = \lambda f.\,\lambda x.\, f^n\, x$ — применить $f$ $n$ раз

```python
# Числа Чёрча
zero  = lambda f: lambda x: x
one   = lambda f: lambda x: f(x)
two   = lambda f: lambda x: f(f(x))
three = lambda f: lambda x: f(f(f(x)))

# Интерпретация: применить f к x n раз
def church_to_int(n):
    return n(lambda x: x + 1)(0)

print(church_to_int(zero))   # 0
print(church_to_int(one))    # 1
print(church_to_int(three))  # 3

# Следующее число: succ n = λf.λx.f(n f x)
succ = lambda n: lambda f: lambda x: f(n(f)(x))

four = succ(three)
print(church_to_int(four))   # 4

# Сложение: plus m n = λf.λx.m f (n f x)
plus = lambda m: lambda n: lambda f: lambda x: m(f)(n(f)(x))
five = plus(two)(three)
print(church_to_int(five))   # 5

# Умножение: mult m n = λf.m(n f)
mult = lambda m: lambda n: lambda f: m(n(f))
six = mult(two)(three)
print(church_to_int(six))    # 6
```

---

## 5. Булевы значения и условные выражения

Чёрч закодировал булевы значения как функции выбора:

- $\mathrm{True} = \lambda x.\,\lambda y.\, x$ — выбирает первый аргумент
- $\mathrm{False} = \lambda x.\,\lambda y.\, y$ — выбирает второй аргумент
- $\mathrm{If\text{-}Then\text{-}Else} = \lambda b.\,\lambda t.\,\lambda f.\, b\, t\, f$

```python
TRUE  = lambda x: lambda y: x
FALSE = lambda x: lambda y: y
IF    = lambda b: lambda t: lambda f: b(t)(f)
NOT   = lambda b: b(FALSE)(TRUE)
AND   = lambda p: lambda q: p(q)(FALSE)
OR    = lambda p: lambda q: p(TRUE)(q)

# Преобразование в обычный bool
to_bool = lambda b: b(True)(False)

print(to_bool(TRUE))            # True
print(to_bool(FALSE))           # False
print(to_bool(NOT(TRUE)))       # False
print(to_bool(AND(TRUE)(FALSE))) # False
print(to_bool(OR(TRUE)(FALSE)))  # True

# Условное выражение
result = IF(TRUE)(lambda: "then branch")(lambda: "else branch")
print(result())  # "then branch"
```

Это не просто упражнение. В таких языках как Haskell булевы значения могут быть реализованы как тип данных, а `if/then/else` — как функция:

```haskell
-- В Haskell:
data Bool = True | False

ifthenelse :: Bool -> a -> a -> a
ifthenelse True  t _ = t
ifthenelse False _ f = f
```

---

## 6. Рекурсия и Y-комбинатор

В λ-исчислении нет именованных функций — как реализовать рекурсию?

**Y-комбинатор** (комбинатор неподвижной точки):

$$Y = \lambda f.\,(\lambda x.\, f(x\, x))\,(\lambda x.\, f(x\, x))$$

$$Y\, f = f(Y\, f) \quad \text{— } Y\, f \text{ является неподвижной точкой } f$$

```python
# Y-комбинатор в Python (ленивая версия через lambda):
Y = lambda f: (lambda x: f(lambda v: x(x)(v)))(lambda x: f(lambda v: x(x)(v)))

# Факториал через Y-комбинатор
factorial_gen = lambda self: lambda n: 1 if n == 0 else n * self(n - 1)
factorial = Y(factorial_gen)

print(factorial(0))  # 1
print(factorial(5))  # 120
print(factorial(10)) # 3628800

# Фибоначчи через Y-комбинатор
fib_gen = lambda self: lambda n: n if n <= 1 else self(n-1) + self(n-2)
fib = Y(fib_gen)

print([fib(i) for i in range(10)])  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
```

Y-комбинатор объясняет, как рекурсия может быть реализована без специального синтаксиса — только через функции первого класса.

---

## 7. Типизированное λ-исчисление

Нетипизированное λ-исчисление вычислительно полно, но допускает бессмысленные выражения (например, применение числа к числу). Типизированные версии добавляют систему типов.

### Просто типизированное λ-исчисление (STLC)

Каждое выражение имеет тип. Базовые типы: `int`, `bool`. Составные: $A \to B$ (функция из $A$ в $B$).

$$\frac{}{\Gamma \vdash x : A} \quad \frac{\Gamma,\, x{:}A \vdash M : B}{\Gamma \vdash \lambda x.\,M : A \to B} \quad \frac{\Gamma \vdash M : A \to B \quad \Gamma \vdash N : A}{\Gamma \vdash M\,N : B}$$

```python
# В Python с аннотациями типов:
from typing import Callable, TypeVar

A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')

def compose(f: Callable[[B], C], g: Callable[[A], B]) -> Callable[[A], C]:
    """λf.λg.λx.f(g x) — B-комбинатор с типами"""
    return lambda x: f(g(x))

def identity(x: A) -> A:
    """λx.x — I-комбинатор с типами"""
    return x

# Компилятор проверяет типы!
add1: Callable[[int], int] = lambda x: x + 1
is_positive: Callable[[int], bool] = lambda x: x > 0

# compose принимает f: int -> bool и g: int -> int, даёт int -> bool
check_add1_positive = compose(is_positive, add1)
print(check_add1_positive(-1))  # True ((-1)+1=0 > 0? False) = False
print(check_add1_positive(0))   # True (0+1=1 > 0)
```

### Система Хиндли–Милнера

Система Хиндли–Милнера (1969–1978) — расширение STLC с параметрическим полиморфизмом (дженериками). Используется в Haskell, OCaml, SML, Rust.

Ключевое свойство: **вывод типов работает автоматически** — программист не обязан аннотировать типы, компилятор выводит их сам.

```haskell
-- В Haskell — компилятор выводит типы:
identity x = x
-- Выведенный тип: identity :: a -> a (для любого типа a)

map f [] = []
map f (x:xs) = f x : map f xs
-- Выведенный тип: map :: (a -> b) -> [a] -> [b]
```

```python
# В Python 3.12+ с TypeVar и генериками:
from typing import Generic, TypeVar

T = TypeVar('T')
U = TypeVar('U')

def map_list(f: Callable[[T], U], lst: list[T]) -> list[U]:
    return [f(x) for x in lst]

result = map_list(str, [1, 2, 3])  # ['1', '2', '3']
```

---

## 8. λ-исчисление в языках программирования

### Замыкания

Замыкание — функция вместе с её лексическим окружением. Это прямое воплощение λ-абстракции:

```python
def make_adder(n):
    # n становится свободной переменной в лямбде ниже
    return lambda x: x + n  # замыкание «захватывает» n

add5 = make_adder(5)
add10 = make_adder(10)

print(add5(3))   # 8
print(add10(3))  # 13

# Каждое замыкание — независимая «среда»
print(add5.__closure__[0].cell_contents)  # 5
print(add10.__closure__[0].cell_contents) # 10
```

### Currying (карринг)

Преобразование функции нескольких аргументов в цепочку функций одного аргумента:

```python
# Некаррированная функция
def add_uncurried(x, y):
    return x + y

# Каррированная версия (как в λ-исчислении!)
def add_curried(x):
    return lambda y: x + y

# Частичное применение становится естественным
add5 = add_curried(5)     # специализированная функция
print(add5(3))            # 8
print(add5(10))           # 15

# В Haskell ВСЕ функции каррированы по умолчанию
# add :: Int -> Int -> Int
# add 5 :: Int -> Int
# add 5 3 :: Int
```

### Функции высшего порядка

Функции, принимающие или возвращающие функции:

```python
# map, filter, reduce — это λ-комбинаторы в чистом виде
from functools import reduce

numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# map: λf.λxs.[f x | x ∈ xs]
squares = list(map(lambda x: x**2, numbers))

# filter: λp.λxs.[x | x ∈ xs, p x]
evens = list(filter(lambda x: x % 2 == 0, numbers))

# reduce: λf.λacc.λxs.foldl f acc xs
total = reduce(lambda acc, x: acc + x, numbers, 0)

print(squares)  # [1, 4, 9, 16, 25, 36, 49, 64, 81, 100]
print(evens)    # [2, 4, 6, 8, 10]
print(total)    # 55

# Компоновка функций — B-комбинатор:
pipeline = (
    lambda xs: filter(lambda x: x % 2 == 0, xs)  # только чётные
)

result = list(pipeline(numbers))
print(result)  # [2, 4, 6, 8, 10]
```

---

## 9. λ-исчисление и системы типов

Соответствие Карри–Ховарда (Curry–Howard correspondence) устанавливает, что:

| λ-исчисление | Логика | Типы |
|---|---|---|
| Терм $M$ | Доказательство $\varphi$ | Программа типа $A$ |
| Тип $A \to B$ | Импликация $A \Rightarrow B$ | Функциональный тип |
| Тип $A \times B$ | Конъюнкция $A \land B$ | Тип пары |
| Тип $A + B$ | Дизъюнкция $A \lor B$ | Тип суммы (Either) |
| Тип $\bot$ | Ложь | Необитаемый тип (Never) |

```haskell
-- В Haskell:
-- Функция типа A -> B — это «доказательство» A ⟹ B
-- Составить пару — это «доказать» конъюнкцию
-- Either — это «доказать» дизъюнкцию

-- Если программа типизируется — она является доказательством!
-- absurd :: Void -> a — из лжи следует что угодно
absurd :: Void -> a
absurd x = case x of {}  -- нет случаев, потому что Void необитаем
```

---

## Заключение

λ-исчисление — это:

1. **Теоретическая основа** функционального программирования (Haskell, OCaml, Clojure)
2. **Объяснение** того, почему замыкания, currying и функции высшего порядка работают так, как они работают
3. **Основа** систем типов (Hindley–Milner, System F)
4. **Корень** соответствия Карри–Ховарда: программы = доказательства

Каждый раз, когда вы пишете `lambda x: x + 1` в Python или `x => x + 1` в JavaScript, вы используете прямой потомок идеи Алонзо Чёрча 1936 года.

---

## Литература и источники

1. Church, A. (1936). An unsolvable problem of elementary number theory. *American Journal of Mathematics*, 58(2), 345–363. — Оригинальная работа по λ-исчислению.

2. Barendregt, H. P. (1985). *The Lambda Calculus: Its Syntax and Semantics* (Revised ed.). North-Holland. — Фундаментальная монография.

3. Pierce, B. C. (2002). *Types and Programming Languages*. MIT Press. — λ-исчисление и системы типов. Доступно: https://www.cis.upenn.edu/~bcpierce/tapl/

4. Hindley, J. R. (1969). The principal type-scheme of an object in combinatory logic. *Transactions of the American Mathematical Society*, 146, 29–60. — Вывод типов Хиндли–Милнера.

5. Wadler, P. (2015). Propositions as types. *Communications of the ACM*, 58(12), 75–84. — Соответствие Карри–Ховарда. https://dl.acm.org/doi/10.1145/2699407

6. 3Blue1Brown и Gabriel Lebec. Lambda Calculus. https://www.youtube.com/watch?v=3VQ382QG-y4 — Визуальное объяснение λ-исчисления.

7. Hutton, G. (2016). *Programming in Haskell* (2nd ed.). Cambridge University Press. — Практика функционального программирования.
