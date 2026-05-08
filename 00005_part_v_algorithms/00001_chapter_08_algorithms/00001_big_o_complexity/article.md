# Big-O нотация и анализ сложности алгоритмов

## Введение

Когда мы разрабатываем алгоритм, нам необходимо понимать, как он будет вести себя при увеличении объёма входных данных. Программа, которая прекрасно работает на сотне элементов, может оказаться совершенно непригодной на миллионе. Для того чтобы описывать эту зависимость формально и однозначно, в информатике используется асимптотический анализ — инструментарий, позволяющий классифицировать алгоритмы по их скорости роста относительно размера входных данных.

Асимптотический анализ абстрагируется от конкретного железа, языка программирования и компилятора. Нас интересует не точное количество операций, а то, как это количество растёт с ростом n. Именно это делает теорию сложности универсальным языком для сравнения алгоритмов.

## Математические основы: пять нотаций

Формально все нотации определяются через существование констант и порогового значения. Рассмотрим каждую из них.

### O (большое О) — верхняя граница

Говорят, что f(n) = O(g(n)), если существуют константы c > 0 и $n_0 \geq 0$, такие что для всех $n \geq n_0$ выполняется:

```
f(n) ≤ c · g(n)
```

Иными словами, начиная с некоторого $n_0$, функция f не превышает g, умноженную на константу. Это **верхняя** асимптотическая граница. Когда мы говорим, что алгоритм имеет сложность $O(n^2)$, мы утверждаем, что он растёт не хуже, чем квадрат от n — хотя может быть и лучше.

Пример: $3n^2 + 5n + 7 = O(n^2)$, поскольку при c = 4 и $n_0 = 10$ неравенство выполняется.

### $\Omega$ (большая омега) — нижняя граница

f(n) = $\Omega$(g(n)), если существуют c > 0 и $n_0 \geq 0$, такие что для всех $n \geq n_0$:

```
f(n) ≥ c · g(n)
```

Это **нижняя** граница. Если алгоритм имеет сложность $\Omega(n \log n)$, значит, он не может быть быстрее, чем n log n, начиная с некоторого n. Сортировка сравнением имеет нижнюю границу $\Omega(n \log n)$ — это фундаментальный результат теории информации.

### $\Theta$ (тета) — точная граница

f(n) = $\Theta$(g(n)), если f(n) = O(g(n)) и f(n) = $\Omega$(g(n)) одновременно. Это означает, что алгоритм растёт **точно** как g(n) с точностью до константы. Например, merge sort — $\Theta(n \log n)$ в любом случае.

### o (малое о) и $\omega$ (малая омега)

Малые нотации означают **строгие** границы без равенства:

- f(n) = o(g(n)): $\lim_{n \to \infty} f(n)/g(n) = 0$ (f растёт строго медленнее g)
- f(n) = $\omega$(g(n)): $\lim_{n \to \infty} f(n)/g(n) = \infty$ (f растёт строго быстрее g)

Эти нотации используются реже, но важны в теоретических доказательствах.

## Практическое использование: игнорирование констант и младших членов

Главный практический принцип асимптотического анализа: мы отбрасываем константные множители и слагаемые более низкого порядка, потому что при достаточно большом n они перестают иметь значение.

```python
# Эта функция имеет O(n) сложность, несмотря на константы
def example(arr):
    total = 0                    # O(1)
    for x in arr:                # n итераций
        total += x * 2 + 1       # O(1) на каждой
    for x in arr:                # ещё n итераций
        total -= x               # O(1) на каждой
    return total                 # O(1)
# Итого: 1 + 2n + 1 = 2n + 2 = O(n)
```

Почему это работает? При $n = 10^6$ разница между n и 100n составляет множитель 100, но разница между n и $n^2$ составляет $10^6$ раз. На масштабе это несравнимо важнее.

Правила упрощения:
1. $O(c \cdot f(n)) = O(f(n))$ для любой константы c
2. $O(f(n) + g(n)) = O(\max(f(n), g(n)))$
3. $O(f(n)) \cdot O(g(n)) = O(f(n) \cdot g(n))$

## Классы сложности

### O(1) — константное время

Алгоритм выполняется за одно и то же время независимо от размера входных данных.

```python
def get_first(arr):
    return arr[0]  # O(1) — прямой доступ по индексу

def is_even(n):
    return n % 2 == 0  # O(1) — одна операция

# Хеш-таблица: поиск в среднем O(1)
cache = {}
cache['key'] = 'value'
value = cache.get('key')  # O(1) в среднем
```

Примеры: доступ к элементу массива по индексу, push/pop в стеке, вставка/удаление в хеш-таблице (в среднем).

### O(log n) — логарифмическое время

На каждом шаге задача делится пополам (или на константную долю). Даже при n = 10⁹ потребуется лишь около 30 шагов.

```python
def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1  # O(log n)

# Целочисленная степень — O(log n)
def fast_pow(base, exp):
    if exp == 0:
        return 1
    if exp % 2 == 0:
        half = fast_pow(base, exp // 2)
        return half * half
    return base * fast_pow(base, exp - 1)
```

Примеры: бинарный поиск, поиск в сбалансированном BST, операции с кучей.

### O(n) — линейное время

Каждый элемент входных данных обрабатывается константное число раз.

```python
def find_max(arr):
    max_val = arr[0]
    for x in arr:       # n итераций
        if x > max_val:
            max_val = x
    return max_val  # O(n)

def has_duplicate(arr):
    seen = set()
    for x in arr:       # n итераций
        if x in seen:   # O(1) в среднем
            return True
        seen.add(x)
    return False  # O(n)
```

Примеры: линейный поиск, подсчёт суммы, проход по списку.

### O(n log n) — квазилинейное время

Типичная сложность эффективных алгоритмов сортировки. Это лучшее, что можно достичь для сортировки сравнением в общем случае.

```python
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])   # T(n/2)
    right = merge_sort(arr[mid:])  # T(n/2)
    return merge(left, right)      # O(n)
# T(n) = 2T(n/2) + O(n) → T(n) = O(n log n) по мастер-теореме

def merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i]); i += 1
        else:
            result.append(right[j]); j += 1
    return result + left[i:] + right[j:]
```

Примеры: merge sort, heap sort, quicksort (в среднем), построение суффиксного массива.

### $O(n^2)$ — квадратичное время

Вложенные циклы по всем элементам. При n = 10⁴ уже 10⁸ операций — заметная задержка.

```python
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):           # n итераций
        for j in range(n - i - 1):  # до n итераций
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr  # O(n²)

def has_pair_sum(arr, target):
    n = len(arr)
    for i in range(n):          # O(n)
        for j in range(i+1, n): # O(n)
            if arr[i] + arr[j] == target:
                return True
    return False  # O(n²) — есть решение за O(n) с хеш-сетом
```

Примеры: пузырьковая сортировка, сортировка выбором, наивный поиск пар.

### O(2^n) — экспоненциальное время

Типично для задач, где рассматриваются все подмножества. При n = 30 это уже миллиард операций.

```python
def fibonacci_naive(n):
    if n <= 1:
        return n
    return fibonacci_naive(n - 1) + fibonacci_naive(n - 2)
# Каждый вызов порождает 2 подзадачи, всего ~2^n вызовов

def all_subsets(arr):
    if not arr:
        return [[]]
    rest = all_subsets(arr[1:])   # рекурсия на n-1 элементах
    return rest + [[arr[0]] + s for s in rest]
# Всего 2^n подмножеств — O(2^n)
```

### O(n!) — факториальное время

Перебор всех перестановок. При n = 20 количество перестановок — $2{,}4 \times 10^{18}$.

```python
from itertools import permutations

def brute_force_tsp(cities, distances):
    """Naive решение задачи коммивояжёра"""
    best_cost = float('inf')
    best_route = None
    for perm in permutations(range(len(cities))):  # n! перестановок
        cost = sum(distances[perm[i]][perm[i+1]] 
                   for i in range(len(perm)-1))
        if cost < best_cost:
            best_cost = cost
            best_route = perm
    return best_route, best_cost
```

## Лучший, средний и худший случай

Важно понимать, что Big-O сам по себе не говорит о том, для какого случая указана сложность. Это нужно оговаривать отдельно.

**Пример: quicksort**

- Лучший случай: O(n log n) — опорный элемент всегда делит массив пополам
- Средний случай: O(n log n) — при случайном выборе опорного
- Худший случай: $O(n^2)$ — опорный всегда оказывается минимумом или максимумом (отсортированный массив с pivot = первый элемент)

```python
import random

def quicksort(arr):
    if len(arr) <= 1:
        return arr
    # Случайный выбор опорного улучшает средний случай
    pivot = random.choice(arr)
    less = [x for x in arr if x < pivot]
    equal = [x for x in arr if x == pivot]
    greater = [x for x in arr if x > pivot]
    return quicksort(less) + equal + quicksort(greater)
```

**Пример: поиск в несортированном массиве**

- Лучший случай: O(1) — элемент стоит первым
- Средний случай: O(n/2) = O(n) — элемент находится в середине
- Худший случай: O(n) — элемент последний или отсутствует

## Амортизированный анализ

Амортизированный анализ применяется, когда отдельные операции иногда дорогие, но в среднем по серии операций стоимость невелика. Ключевой пример — динамический массив.

### Динамический массив: амортизированное O(1) для append

При заполнении массива мы удваиваем его ёмкость. Операция копирования O(n) происходит редко.

```python
class DynamicArray:
    def __init__(self):
        self.data = [None]  # начальная ёмкость = 1
        self.size = 0
        self.capacity = 1
    
    def append(self, value):
        if self.size == self.capacity:
            # Дорогая операция: O(n), но редкая
            self._resize()
        self.data[self.size] = value
        self.size += 1
    
    def _resize(self):
        new_capacity = self.capacity * 2
        new_data = [None] * new_capacity
        for i in range(self.size):
            new_data[i] = self.data[i]
        self.data = new_data
        self.capacity = new_capacity
    
    def __getitem__(self, idx):
        return self.data[idx]
```

**Анализ стоимости n операций append:**

Операции вставки без копирования: n штук по 1 операции = n.
Операции копирования при resize: при ёмкостях 1, 2, 4, 8, ..., 2^k:
```
1 + 2 + 4 + ... + 2^k = 2^(k+1) - 1 < 2n
```
Итого: n + 2n = 3n операций за n вставок → **амортизированное O(1)** на вставку.

### Метод банкира (Banker's method)

Представим, что каждая операция append «платит» 3 монеты:
- 1 монета — за саму вставку
- 1 монета — за будущее копирование этого элемента при следующем resize
- 1 монета — за копирование одного «старого» элемента при следующем resize

При каждом resize в массиве ровно n/2 новых элементов (добавленных с предыдущего resize) и n/2 старых. Каждый новый элемент имеет 2 накопленные монеты: одну для себя и одну для старого элемента. Итого все копирования покрыты — амортизированная стоимость O(1).

### Потенциальный метод

Более формальный подход: определяем потенциальную функцию Φ(S), которая характеризует состояние структуры данных S. Амортизированная стоимость операции:

```
â_i = c_i + Φ(S_i) - Φ(S_{i-1})
```

где c_i — реальная стоимость, Φ(S_i) — потенциал после операции.

Для динамического массива: $\Phi = 2 \cdot \text{size} - \text{capacity}$.

- До resize: size = capacity, Φ = 2n - n = n
- После resize: size = n+1, capacity = 2n, Φ = 2(n+1) - 2n = 2
- Амортизированная стоимость resize = n (копирование) + 2 - n = 2 = O(1)

### Другие примеры амортизации

**Бинарный счётчик**: инкрементирование счётчика в двоичной записи. Иногда переносится много битов, но в среднем — O(1).

```python
def increment_binary(bits):
    """bits — список битов от младшего к старшему"""
    i = 0
    while i < len(bits) and bits[i] == 1:
        bits[i] = 0  # сброс бита (иногда много, но редко)
        i += 1
    if i < len(bits):
        bits[i] = 1
    else:
        bits.append(1)
    return bits

# За n операций суммарно перевернётся:
# n/2 * 1 + n/4 * 2 + n/8 * 3 + ... ≤ 2n битов → O(1) амортизированно
```

**Splay tree**: самобалансирующееся BST, где каждый доступ перемещает узел в корень. Отдельная операция — O(n), но амортизированно — O(log n).

## Пространственная сложность

Помимо временной сложности, важна **пространственная** — сколько дополнительной памяти требует алгоритм.

```python
# O(1) пространство — in-place алгоритм
def reverse_in_place(arr):
    left, right = 0, len(arr) - 1
    while left < right:
        arr[left], arr[right] = arr[right], arr[left]
        left += 1
        right -= 1

# O(n) пространство — новый массив
def reverse_copy(arr):
    return arr[::-1]  # создаёт копию

# O(n) пространство — рекурсия (стек вызовов)
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)  # стек глубины n

# O(log n) пространство — рекурсия бинарного поиска
def binary_search_recursive(arr, target, lo=0, hi=None):
    if hi is None:
        hi = len(arr) - 1
    if lo > hi:
        return -1
    mid = (lo + hi) // 2
    if arr[mid] == target:
        return mid
    elif arr[mid] < target:
        return binary_search_recursive(arr, target, mid + 1, hi)
    else:
        return binary_search_recursive(arr, target, lo, mid - 1)
```

Различают **вспомогательную** пространственную сложность (без учёта входных данных) и **полную** (включая вход). Merge sort требует O(n) вспомогательной памяти, heap sort — O(1).

## Анализ реальных алгоритмов

### Пример 1: поиск всех пар с заданной суммой

```python
# Наивный подход: O(n²) время, O(1) пространство
def pairs_naive(arr, target):
    pairs = []
    for i in range(len(arr)):
        for j in range(i+1, len(arr)):
            if arr[i] + arr[j] == target:
                pairs.append((arr[i], arr[j]))
    return pairs

# Оптимальный подход: O(n) время, O(n) пространство
def pairs_optimal(arr, target):
    seen = set()
    pairs = []
    for x in arr:
        complement = target - x
        if complement in seen:
            pairs.append((complement, x))
        seen.add(x)
    return pairs
```

### Пример 2: матричное умножение

```python
# Наивный: O(n³) — три вложенных цикла
def matrix_multiply_naive(A, B):
    n = len(A)
    C = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            for k in range(n):  # O(n³)
                C[i][j] += A[i][k] * B[k][j]
    return C

# Алгоритм Штрассена: O(n^2.807) — 7 умножений вместо 8
# (реализация опущена для краткости, но важен факт улучшения)
```

### Пример 3: наибольшая общая подпоследовательность (LCS)

```python
from functools import lru_cache

# Наивная рекурсия: O(2^(m+n)) — экспоненциально
def lcs_naive(s1, s2, i, j):
    if i == 0 or j == 0:
        return 0
    if s1[i-1] == s2[j-1]:
        return 1 + lcs_naive(s1, s2, i-1, j-1)
    return max(lcs_naive(s1, s2, i-1, j), lcs_naive(s1, s2, i, j-1))

# С мемоизацией: O(m·n) время и пространство
@lru_cache(maxsize=None)
def lcs_memo(s1, s2, i, j):
    if i == 0 or j == 0:
        return 0
    if s1[i-1] == s2[j-1]:
        return 1 + lcs_memo(s1, s2, i-1, j-1)
    return max(lcs_memo(s1, s2, i-1, j), lcs_memo(s1, s2, i, j-1))
```

## Мастер-теорема

Для рекуррентных соотношений вида T(n) = aT(n/b) + f(n) мастер-теорема даёт ответ:

Пусть c_crit = log_b(a):
1. Если $f(n) = O(n^{c_{\text{crit}} - \varepsilon})$, то $T(n) = \Theta(n^{c_{\text{crit}}})$
2. Если $f(n) = \Theta(n^{c_{\text{crit}}} \cdot \log^k(n))$, то $T(n) = \Theta(n^{c_{\text{crit}}} \cdot \log^{k+1}(n))$
3. Если $f(n) = \Omega(n^{c_{\text{crit}} + \varepsilon})$, то $T(n) = \Theta(f(n))$

```python
# Примеры применения мастер-теоремы:

# Merge sort: T(n) = 2T(n/2) + O(n)
# a=2, b=2, c_crit=log_2(2)=1, f(n)=O(n^1) → случай 2 → O(n log n)

# Binary search: T(n) = T(n/2) + O(1)
# a=1, b=2, c_crit=0, f(n)=O(1)=O(n^0) → случай 2 → O(log n)

# Karatsuba умножение: T(n) = 3T(n/2) + O(n)
# a=3, b=2, c_crit=log_2(3)≈1.585, f(n)=O(n^1) → случай 1 → O(n^1.585)
```

## Практические замечания

Асимптотический анализ — это теоретический инструмент, и у него есть ограничения:

1. **Константы важны на практике**: алгоритм O(n log n) с большой константой может проигрывать $O(n^2)$ при малых n. Вот почему интросорт использует insertion sort для маленьких подмассивов.

2. **Cache-locality имеет значение**: два алгоритма с одинаковой нотацией могут существенно различаться по реальной скорости из-за паттернов обращения к памяти.

3. **Средний случай часто важнее**: quicksort используется повсеместно, несмотря на теоретический $O(n^2)$ в худшем случае, потому что средний O(n log n) — прекрасен на практике.

```python
import timeit

# Демонстрация: разница между O(n) и O(n²)
def sum_linear(n):
    return sum(range(n))

def sum_quadratic(n):
    total = 0
    for i in range(n):
        for j in range(n):
            total += 1  # бессмысленно, но демонстрирует O(n²)
    return total

n = 1000
t_linear = timeit.timeit(lambda: sum_linear(n), number=100)
t_quad = timeit.timeit(lambda: sum_quadratic(n), number=100)

print(f"O(n):  {t_linear:.4f}s")
print(f"O(n²): {t_quad:.4f}s")
print(f"Ratio: {t_quad/t_linear:.1f}x")
# При n=1000 квадратичный примерно в 1000 раз медленнее
```

## Итоговая таблица сложностей

| Нотация | Название | n=10 | n=100 | n=1000 | Пример |
|---------|----------|------|-------|--------|--------|
| O(1) | Константная | 1 | 1 | 1 | Хеш-таблица |
| O(log n) | Логарифмическая | 3 | 7 | 10 | Бинарный поиск |
| O(n) | Линейная | 10 | 100 | 1000 | Линейный поиск |
| O(n log n) | Квазилинейная | 33 | 664 | 9966 | Merge sort |
| $O(n^2)$ | Квадратичная | 100 | 10000 | $10^6$ | Пузырьковая сортировка |
| O(2^n) | Экспоненциальная | 1024 | $10^{30}$ | $10^{301}$ | Перебор подмножеств |
| O(n!) | Факториальная | 3628800 | $9 \times 10^{157}$ | — | Перебор перестановок |

## Заключение

Анализ сложности алгоритмов — фундаментальный инструмент каждого разработчика. Big-O даёт верхнюю оценку, $\Omega$ — нижнюю, $\Theta$ — точную. Амортизированный анализ позволяет корректно оценивать структуры данных с редкими дорогостоящими операциями, такие как динамические массивы. Пространственная сложность дополняет временную, особенно когда памяти мало. Понимание этих концепций позволяет принимать обоснованные решения о выборе алгоритмов и структур данных.

## Литература и источники

1. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. — Главы 3–4: асимптотические обозначения, мастер-теорема.

2. Knuth, D. E. (1997). *The Art of Computer Programming, Vol. 1: Fundamental Algorithms* (3rd ed.). Addison-Wesley. — Основополагающий труд по анализу алгоритмов.

3. Sedgewick, R., & Wayne, K. (2011). *Algorithms* (4th ed.). Addison-Wesley. — Доступное изложение с примерами.

4. Skiena, S. S. (2020). *The Algorithm Design Manual* (3rd ed.). Springer. — Практический подход к анализу и проектированию алгоритмов.

5. Tarjan, R. E. (1985). Amortized computational complexity. *SIAM Journal on Algebraic and Discrete Methods*, 6(2), 306–318. — Оригинальная статья об амортизированном анализе.

6. Sleator, D. D., & Tarjan, R. E. (1985). Self-adjusting binary search trees. *Journal of the ACM*, 32(3), 652–686. — Потенциальный метод и splay trees.

7. Roughgarden, T. (2017). *Algorithms Illuminated, Part 1*. Soundlikeyourself Publishing. — Современное введение с акцентом на анализ.

8. Документация Python: https://wiki.python.org/moin/TimeComplexity — Сложность операций встроенных структур данных Python.
