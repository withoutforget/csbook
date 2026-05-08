# Замыкания и функции первого класса: функция как значение с контекстом

Одна из самых мощных идей в программировании — функция как полноправное значение, которое можно передавать, хранить и возвращать. Когда такая функция несёт с собой своё лексическое окружение — рождается замыкание. Понимание этих концепций открывает дверь в функциональное программирование, позволяет писать элегантный и выразительный код, а также понять, что происходит "под капотом" языков от Python до Go.

## Функции первого класса

В языках программирования концепция "первоклассного объекта" (first-class citizen) означает, что с объектом можно делать всё то же, что и с обычными данными. Функции первого класса (first-class functions) — это функции, которые можно:

1. **Присваивать переменной**
2. **Передавать как аргумент**
3. **Возвращать из другой функции**
4. **Хранить в коллекции (массиве, словаре)**
5. **Создавать анонимно (lambda)**

Аналогия: в языках без функций первого класса функции — как стационарный телефон: он есть в доме, но его нельзя взять с собой. В языках с функциями первого класса функция — как мобильный телефон: её можно передать другу, положить в карман, получить обратно.

### Пример в Python

```python
# 1. Присваивание переменной
def greet(name):
    return f"Hello, {name}!"

say_hello = greet          # функция как значение
print(say_hello("Alice"))  # Hello, Alice!

# 2. Передача как аргумент
def apply(func, value):
    return func(value)

print(apply(greet, "Bob"))  # Hello, Bob!
print(apply(str.upper, "hello"))  # HELLO

# 3. Возврат из функции
def make_multiplier(n):
    def multiply(x):
        return x * n      # n захватывается из внешнего scope!
    return multiply

double = make_multiplier(2)
triple = make_multiplier(3)
print(double(5))   # 10
print(triple(5))   # 15

# 4. Хранение в коллекции
operations = {
    'add': lambda a, b: a + b,
    'sub': lambda a, b: a - b,
    'mul': lambda a, b: a * b,
}
print(operations['add'](3, 4))  # 7
```

### Пример в JavaScript

```javascript
// Стрелочные функции — лаконичный синтаксис для first-class functions
const square = x => x * x;
const cube = x => x * x * x;

const transform = (arr, func) => arr.map(func);

console.log(transform([1, 2, 3], square));  // [1, 4, 9]
console.log(transform([1, 2, 3], cube));    // [1, 8, 27]

// Higher-order functions встроены в язык
const numbers = [1, 2, 3, 4, 5, 6];
const result = numbers
    .filter(x => x % 2 === 0)    // [2, 4, 6]
    .map(x => x * x)              // [4, 16, 36]
    .reduce((acc, x) => acc + x, 0);  // 56
```

### Пример в Go

В Go функции тоже первоклассные, хотя язык не является функциональным:

```go
package main

import "fmt"

// Функция как тип
type Predicate func(int) bool

func filter(nums []int, pred Predicate) []int {
    result := []int{}
    for _, n := range nums {
        if pred(n) {
            result = append(result, n)
        }
    }
    return result
}

func main() {
    numbers := []int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
    
    // Функции как значения
    isEven := func(n int) bool { return n%2 == 0 }
    isOdd := func(n int) bool { return n%2 != 0 }
    
    fmt.Println(filter(numbers, isEven))  // [2 4 6 8 10]
    fmt.Println(filter(numbers, isOdd))   // [1 3 5 7 9]
    
    // Возврат функции
    greaterThan := func(threshold int) Predicate {
        return func(n int) bool { return n > threshold }
    }
    
    bigNumbers := filter(numbers, greaterThan(7))
    fmt.Println(bigNumbers)  // [8 9 10]
}
```

## Что такое замыкание

Замыкание (closure) — это функция, вместе с её лексическим окружением. Когда функция создаётся внутри другой функции, она "захватывает" переменные из внешней области видимости — даже если внешняя функция уже завершила работу.

Математически: замыкание — это пара (функция, окружение), где окружение — это отображение свободных переменных функции на их текущие значения.

**Свободная переменная** — переменная, которая использована в функции, но не определена в ней (не параметр и не локальная). В замыкании свободные переменные "закрыты" (closed over) — отсюда название.

### Простейший пример замыкания

```python
def make_counter():
    count = 0           # эта переменная "захватывается"
    
    def increment():
        nonlocal count  # говорим Python: count — внешняя
        count += 1
        return count
    
    return increment    # возвращаем функцию + её контекст

# make_counter завершил работу, но count живёт!
counter1 = make_counter()
counter2 = make_counter()

print(counter1())  # 1
print(counter1())  # 2
print(counter1())  # 3
print(counter2())  # 1 — своё независимое состояние!
```

После вызова `make_counter()` функция завершилась, но `count` не умерла. Она была "захвачена" функцией `increment` и продолжает жить до тех пор, пока жив объект `counter1`.

## Как замыкания реализованы: стек vs куча

Здесь начинается настоящая информатика.

### Обычные функции и стек вызовов

При вызове обычной функции создаётся кадр стека (stack frame) с локальными переменными. Когда функция возвращается — кадр уничтожается.

```
Стек:
┌─────────────────┐  <- Stack pointer
│ make_counter()  │
│   count = 0     │  <- будет уничтожено при возврате
└─────────────────┘
│ main()          │
└─────────────────┘
```

### Проблема замыканий

Если `increment` захватывает `count`, а мы возвращаем `increment` из `make_counter`, то что происходит с `count`? Стек `make_counter` уничтожается — `count` на стеке больше нет!

**Решение:** Переменные, захваченные замыканием, перемещаются с стека в кучу (heap). Они живут отдельным объектом, называемым:
- **Cell** в Python
- **Upvalue** в Lua  
- **Closure record/environment record** в разных теориях

```
Куча:
┌──────────────────────────────┐
│ closure object "counter1"    │
│  code: <адрес increment>     │
│  env: ──────────────────────>│──> Cell(count=3)
└──────────────────────────────┘
         
┌──────────────────────────────┐
│ closure object "counter2"    │
│  code: <адрес increment>     │
│  env: ──────────────────────>│──> Cell(count=1)  (отдельный Cell!)
└──────────────────────────────┘
```

### Upvalues в Lua

Lua имеет особенно элегантную реализацию замыканий. Каждая функция хранит список "upvalues" — ссылок на захваченные переменные.

Пока внешняя функция ещё выполняется, upvalue указывает прямо на стек. Когда внешняя функция завершается — upvalue "закрывается" (closed) и значение копируется в кучу.

```lua
function make_adder(n)
    -- n изначально на стеке
    return function(x)
        return x + n   -- n — upvalue
    end
end

-- Когда make_adder возвращается:
-- n с стека копируется в heap
-- upvalue теперь указывает в heap
local add5 = make_adder(5)
print(add5(3))  -- 8
```

Эта оптимизация называется "open upvalue" (пока функция жива) и "closed upvalue" (после завершения). Lua избегает лишних выделений в куче для переменных, которые не переживают внешнюю функцию.

### Cells в Python

CPython реализует замыкания через объекты `cell`. Каждая захваченная переменная оборачивается в `cell`-объект.

```python
import dis

def outer():
    x = 10
    def inner():
        return x
    return inner

# Изучим байт-код
f = outer()
print(f.__code__.co_freevars)  # ('x',) — свободные переменные
print(f.__closure__)           # (<cell at 0x...>,)
print(f.__closure__[0].cell_contents)  # 10
```

Когда `outer` создаёт `inner`, Python замечает, что `x` используется в `inner`. `x` оборачивается в `cell`-объект — контейнер с одним значением. И `outer`, и `inner` ссылаются на один и тот же `cell`.

```python
def make_adder(n):
    def add(x):
        return x + n
    return add

add3 = make_adder(3)
add5 = make_adder(5)

# Разные cell объекты
print(add3.__closure__[0].cell_contents)  # 3
print(add5.__closure__[0].cell_contents)  # 5
```

### Замыкания в JavaScript (heap-allocated frames)

JavaScript движки вроде V8 используют несколько стратегий:

1. **Контекстный объект (Context):** Захваченные переменные хранятся в специальном объекте `Context` в куче.

2. **Если переменная не захватывается** — она остаётся на стеке (оптимизация).

3. **Если несколько замыканий в одном scope** — они разделяют один Context.

```javascript
function makeCounter(start) {
    let count = start;   // count хранится в Context объекте
    
    return {
        increment: () => ++count,  // оба closure ссылаются
        decrement: () => --count,  // на один Context!
        value: () => count
    };
}

const c = makeCounter(0);
c.increment(); // 1
c.increment(); // 2
c.decrement(); // 1
console.log(c.value()); // 1 — count = 1 для обоих методов
```

## Классическая ловушка: замыкание в цикле

Одна из самых известных ловушек с замыканиями — это создание замыканий внутри цикла.

### JavaScript (до ES6)

```javascript
// ПЛОХО: классическая ошибка
var funcs = [];
for (var i = 0; i < 5; i++) {
    funcs.push(function() { return i; });
}

console.log(funcs[0]()); // 5 — не 0!
console.log(funcs[1]()); // 5 — не 1!
// Все функции захватили ОДНУ переменную i, которая стала 5
```

Проблема: все функции замыкаются на одну переменную `i` (объявленную через `var` с function scope). К моменту вызова цикл завершился и `i = 5`.

**Решение 1: let (block-scoped)**

```javascript
var funcs = [];
for (let i = 0; i < 5; i++) {  // let создаёт новую переменную на каждой итерации
    funcs.push(function() { return i; });
}

console.log(funcs[0]()); // 0
console.log(funcs[1]()); // 1
```

**Решение 2: IIFE (Immediately Invoked Function Expression)**

```javascript
var funcs = [];
for (var i = 0; i < 5; i++) {
    funcs.push((function(j) {  // j — локальная копия i
        return function() { return j; };
    })(i));
}
```

### Python — та же ловушка

```python
# ПЛОХО
funcs = []
for i in range(5):
    funcs.append(lambda: i)  # захватывается переменная i, не её значение!

print(funcs[0]())  # 4 — не 0!
print(funcs[4]())  # 4

# ХОРОШО: захватываем значение через дефолтный аргумент
funcs = []
for i in range(5):
    funcs.append(lambda i=i: i)  # i=i захватывает значение!

print(funcs[0]())  # 0
print(funcs[4]())  # 4
```

## Каррирование и частичное применение

Замыкания — основа каррирования и частичного применения.

### Каррирование (Currying)

Каррирование — преобразование функции от нескольких аргументов в цепочку функций от одного аргумента. Назван в честь математика Хаскелла Карри.

```
f(a, b, c) → g(a)(b)(c)
```

```python
# Обычная функция
def add(a, b):
    return a + b

# Каррированная версия
def add_curried(a):
    def inner(b):
        return a + b   # a захвачено замыканием
    return inner

add5 = add_curried(5)
print(add5(3))   # 8
print(add5(10))  # 15
```

В Haskell все функции каррированы по умолчанию:

```haskell
-- Тип: Int -> Int -> Int
-- Читается как: функция принимает Int, возвращает функцию Int -> Int
add :: Int -> Int -> Int
add a b = a + b

-- Частичное применение:
add5 :: Int -> Int
add5 = add 5

-- Использование:
add5 3   -- 8
add5 10  -- 15
```

### Частичное применение (Partial Application)

Частичное применение — фиксирование некоторых аргументов функции для создания функции с меньшей "арностью".

```python
from functools import partial

def power(base, exponent):
    return base ** exponent

square = partial(power, exponent=2)
cube = partial(power, exponent=3)

print(square(5))  # 25
print(cube(3))    # 27

# Пример с реальным использованием
from functools import partial

def log(level, message):
    print(f"[{level}] {message}")

error = partial(log, "ERROR")
info = partial(log, "INFO")

error("Connection failed")   # [ERROR] Connection failed
info("Server started")       # [INFO] Server started
```

### Разница: каррирование vs частичное применение

```python
# Частичное применение — применяем часть аргументов сейчас
def add3(a, b, c): return a + b + c

add_1 = partial(add3, 1)     # a=1 зафиксирован
print(add_1(2, 3))           # 6

# Каррирование — превращаем в цепочку унарных функций
def curry_add3(a):
    def inner1(b):
        def inner2(c):
            return a + b + c
        return inner2
    return inner1

print(curry_add3(1)(2)(3))   # 6
```

## Замыкания как объекты, объекты как замыкания

Есть глубокая эквивалентность: замыкания и объекты — это разные стороны одной монеты.

**Замыкание = данные + код, связанные вместе**
**Объект = данные + код, связанные вместе**

```python
# Вариант с объектом
class Counter:
    def __init__(self, start=0):
        self.count = start
    
    def increment(self):
        self.count += 1
        return self.count

# Вариант с замыканием
def make_counter(start=0):
    count = [start]  # список для изменяемости без nonlocal
    
    def increment():
        count[0] += 1
        return count[0]
    
    return increment

# Оба варианта функционально эквивалентны
obj_counter = Counter()
clos_counter = make_counter()

print(obj_counter.increment())  # 1
print(clos_counter())           # 1
```

Это наблюдение, известное как "The Closure/Object Duality", используется в языках без классов (Scheme, Clojure) для реализации объектно-ориентированного программирования через замыкания.

## Высокоуровневые паттерны с замыканиями

### Декораторы в Python

Декораторы — это функции, принимающие функцию и возвращающие новую функцию. Это замыкание!

```python
import time
from functools import wraps

def timer(func):
    @wraps(func)  # сохраняем метаданные func
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)   # func захвачено замыканием
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

@timer
def slow_function(n):
    return sum(range(n))

slow_function(10_000_000)  # slow_function took 0.2341s
```

### Мемоизация через замыкания

```python
def memoize(func):
    cache = {}  # cache захватывается замыканием
    
    def wrapper(*args):
        if args not in cache:
            cache[args] = func(*args)
        return cache[args]
    
    return wrapper

@memoize
def fibonacci(n):
    if n <= 1: return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(100))  # быстро, без переполнения стека
```

### Lazy evaluation через замыкания

```python
def lazy(func, *args, **kwargs):
    """Ленивое вычисление: вычислим только когда понадобится"""
    result = []  # список как контейнер для изменяемого значения
    
    def force():
        if not result:
            result.append(func(*args, **kwargs))
        return result[0]
    
    return force

# Дорогое вычисление откладывается
expensive = lazy(sum, range(1_000_000))

# ... другой код ...

value = expensive()  # вычисляется только здесь
value = expensive()  # берётся из кеша
```

## Замыкания в компилируемых языках

### Rust: замыкания и владение

Rust — интересный случай: язык со строгой системой владения и замыканиями.

```rust
fn main() {
    let x = 5;
    
    // FnOnce — может захватить по значению (move), вызывается один раз
    let consume = move || println!("x = {}", x);
    consume();
    
    // Fn — захватывает по ссылке, вызывается многократно
    let mut count = 0;
    let mut increment = || {
        count += 1;  // захват по мутабельной ссылке
        count
    };
    
    println!("{}", increment()); // 1
    println!("{}", increment()); // 2
}

// Функция принимающая замыкание
fn apply_twice<F: Fn(i32) -> i32>(f: F, x: i32) -> i32 {
    f(f(x))
}

let double = |x| x * 2;
println!("{}", apply_twice(double, 3)); // 12
```

В Rust замыкания реализованы как анонимные структуры, реализующие трейты `Fn`, `FnMut` или `FnOnce`. Захваченные переменные становятся полями структуры.

### C++: лямбды и захват

```cpp
#include <functional>
#include <vector>
#include <algorithm>

int main() {
    int threshold = 5;
    
    // [threshold] — захват по значению
    auto isAbove = [threshold](int x) { return x > threshold; };
    
    // [&threshold] — захват по ссылке
    auto isBelow = [&threshold](int x) { return x < threshold; };
    
    std::vector<int> nums = {1, 3, 5, 7, 9};
    
    // count_if принимает функцию как аргумент
    int count = std::count_if(nums.begin(), nums.end(), isAbove);
    // count = 2 (7 и 9)
    
    // [=] — захват всего по значению
    // [&] — захват всего по ссылке
    
    // std::function — тип для хранения замыканий
    std::function<int(int)> adder = [threshold](int x) {
        return x + threshold;
    };
    
    return 0;
}
```

### Go: функции-замыкания

```go
package main

import "fmt"

// makeAdder возвращает функцию — замыкание над n
func makeAdder(n int) func(int) int {
    return func(x int) int {
        return x + n   // n из внешнего scope живёт в куче
    }
}

// Замыкание с изменяемым состоянием
func makeAccumulator() func(int) int {
    sum := 0
    return func(x int) int {
        sum += x   // sum захвачена по ссылке
        return sum
    }
}

func main() {
    add10 := makeAdder(10)
    fmt.Println(add10(5))  // 15
    fmt.Println(add10(20)) // 30
    
    acc := makeAccumulator()
    fmt.Println(acc(1))   // 1
    fmt.Println(acc(5))   // 6
    fmt.Println(acc(10))  // 16
}
```

Go избегает утечек: переменная `sum` в `makeAccumulator` автоматически выделяется в куче компилятором (escape analysis), потому что она "убегает" из функции через замыкание.

## Оптимизации компилятора для замыканий

### Аллокация на стеке vs куче

Умные компиляторы делают escape analysis — анализируют, может ли объект "убежать" из функции. Если замыкание не убегает из своей функции, захваченные переменные могут остаться на стеке:

```java
// Java пример escape analysis
void doWork() {
    int[] counter = {0};     // массив для изменяемого захвата
    
    Runnable r = () -> counter[0]++;  // замыкание
    
    r.run();                 // вызвано здесь же
    r.run();
    
    System.out.println(counter[0]); // 2
}
// r не убегает из doWork — HotSpot может выделить counter на стеке!
```

### Lambda capturing cost

В Java лямбды и анонимные классы представлены как объекты. JVM использует invokedynamic для их создания — это даёт flexibility для JIT-компилятора.

```java
// Лямбда без захвата — может быть singleton
Comparator<String> comp = (a, b) -> a.compareTo(b);  // один объект для всех вызовов

// Лямбда с захватом — новый объект каждый раз
int x = getX();
Supplier<Integer> sup = () -> x + 1;  // новый объект при каждом создании
```

## Tail Call Optimization и замыкания

В функциональных языках, где рекурсия заменяет циклы, важна оптимизация хвостовых вызовов (TCO).

```scheme
;; Scheme: хвостовая рекурсия
;; Без TCO: переполнение стека при больших n
(define (fact-tco n acc)
  (if (= n 0)
      acc
      (fact-tco (- n 1) (* n acc))))  ; хвостовой вызов

;; С TCO: вызов заменяется переходом (goto), стек не растёт
(fact-tco 1000000 1)  ; работает!
```

TCO и замыкания взаимодействуют сложно: если хвостовой вызов захватывает переменные, компилятор должен убедиться, что замыкание правильно управляется.

## Итоги

Функции первого класса и замыкания — фундаментальная концепция, лежащая в основе:

- **Функционального программирования** (map, filter, reduce)
- **Декораторов и middleware** (обёртки вокруг функций)
- **Callbacks и event handlers** (async программирование)
- **Currying и partial application** (фабрики функций)
- **Модульного кода без глобального состояния**

Ключевые технические детали:
- Захваченные переменные перемещаются с **стека в кучу**
- В Python — **cells**, в Lua — **upvalues** (open/closed)
- Замыкание = функция + **окружение** (environment record)
- В Rust замыкания реализованы как **анонимные структуры**

## Литература

1. Abelson, H., & Sussman, G. J. (1996). *Structure and Interpretation of Computer Programs* (2nd ed.). MIT Press. https://mitpress.mit.edu/sicp/ — главы 1.3 и 3.2 о замыканиях и окружениях

2. Scott, M. L. (2015). *Programming Language Pragmatics* (4th ed.). Morgan Kaufmann. Глава 6 — First-class functions и их реализация.

3. Ierusalimschy, R., de Figueiredo, L. H., & Celes, W. (2005). The Implementation of Lua 5.0. *Journal of Universal Computer Science*, 11(7), 1159–1176. https://www.jucs.org/jucs_11_7/the_implementation_of_lua — реализация upvalues

4. Van Rossum, G. et al. Python Language Reference — Execution model, Closures. https://docs.python.org/3/reference/executionmodel.html

5. Ierusalimschy, R. (2016). *Programming in Lua* (4th ed.). PUC-Rio. Глава 6 — More about Functions (closures, upvalues).

6. Mozilla MDN Web Docs — Closures. https://developer.mozilla.org/en-US/docs/Web/JavaScript/Closures

7. The Rust Programming Language — Closures. https://doc.rust-lang.org/book/ch13-01-closures.html

8. Church, A. (1941). *The Calculi of Lambda Conversion*. Princeton University Press. — математические основы lambda calculus

9. Reynolds, J. C. (1972). Definitional Interpreters for Higher-Order Programming Languages. *Proceedings of the 25th ACM National Conference*. https://dl.acm.org/doi/10.1145/800194.805852 — раннее исследование closures

10. Appel, A. W. (1992). *Compiling with Continuations*. Cambridge University Press. — компиляция функциональных языков с замыканиями
