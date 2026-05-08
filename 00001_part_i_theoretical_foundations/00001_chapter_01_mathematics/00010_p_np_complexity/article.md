# P, NP и NP-полнота: почему «найти оптимально» часто невозможно

## Введение

Теория сложности вычислений изучает, сколько ресурсов (времени, памяти) нужно для решения задач. Вопрос «P = NP?» — центральный нерешённый вопрос теоретической информатики и один из семи «Задач тысячелетия» Математического института Клея с призом в $1 000 000. Но практическое значение теории сложности выходит далеко за рамки этого вопроса: она объясняет, почему одни задачи решаются за секунды, а другие — за время, превышающее возраст вселенной.

---

## 1. Временная сложность

Временная сложность алгоритма — функция T(n), описывающая количество элементарных операций в зависимости от размера входа n.

### Классы O-нотации

| Класс | Обозначение | Пример |
|---|---|---|
| Константная | O(1) | Доступ к элементу массива |
| Логарифмическая | O(log n) | Бинарный поиск |
| Линейная | O(n) | Линейный поиск |
| Линейно-логарифмическая | O(n log n) | Merge Sort |
| Квадратичная | O(n²) | Bubble Sort |
| Кубическая | O(n³) | Наивное умножение матриц |
| Полиномиальная | O(nᵏ) | k-фиксировано |
| Экспоненциальная | O(2^n) | Перебор всех подмножеств |
| Факториальная | O(n!) | Перебор всех перестановок |

```python
import time

def measure_time(func, *args):
    start = time.perf_counter()
    result = func(*args)
    elapsed = time.perf_counter() - start
    return result, elapsed

# Демонстрация роста сложности
def linear_search(arr, target):
    for x in arr:
        if x == target:
            return True
    return False

def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return True
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return False

# Сравним на больших массивах
import random
arr = sorted(random.sample(range(10**7), 10**6))

_, t_linear = measure_time(linear_search, arr, -1)  # худший случай
_, t_binary = measure_time(binary_search, arr, -1)

print(f"Линейный поиск (n=10^6): {t_linear*1000:.2f} мс")
print(f"Бинарный поиск (n=10^6): {t_binary*1000:.4f} мс")
print(f"Ускорение: {t_linear/t_binary:.0f}x")
```

---

## 2. Класс P

**P** (Polynomial time) — класс задач принятия решений, решаемых детерминированной машиной Тьюринга за полиномиальное время O(nᵏ) для некоторого k.

«Полиномиальное время» = «практически решаемо». Это условное соглашение: O(n^100) технически полиномиально, но неприменимо. На практике все полезные алгоритмы в P имеют небольшую степень.

### Примеры задач в P

- **Сортировка**: O(n log n) — merge sort
- **Кратчайший путь**: O((V + E) log V) — алгоритм Дейкстры
- **Линейное программирование**: O(n³) — симплекс-метод (в среднем), алгоритм Хачияна (полиномиально в худшем случае)
- **Простота числа**: O((log n)^6) — алгоритм AKS (2002)
- **Проверка простоты**: вероятностно — O(k × (log n)²) — Миллер–Рабин

```python
# Задача из P: достижимость в графе (BFS/DFS — O(V+E))
from collections import deque

def is_reachable(graph, source, target):
    """Есть ли путь от source до target в графе? O(V+E)"""
    visited = {source}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if node == target:
            return True
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return False

graph = {'A': ['B', 'C'], 'B': ['D'], 'C': ['D', 'E'], 'D': [], 'E': []}
print(is_reachable(graph, 'A', 'E'))  # True
print(is_reachable(graph, 'D', 'A'))  # False
```

---

## 3. Класс NP

**NP** (Nondeterministic Polynomial time) — класс задач принятия решений, для которых предложенное решение («свидетель») можно **проверить** за полиномиальное время.

Эквивалентное определение: задача решается недетерминированной машиной Тьюринга за полиномиальное время.

**Ключевое различие**: для P — существует алгоритм, находящий решение за полиномиальное время. Для NP — существует алгоритм, **проверяющий** решение за полиномиальное время.

### Примеры задач в NP

**Задача о выполнимости (SAT)**: дана булева формула в КНФ, существует ли набор значений переменных, при котором она истинна?

- Найти решение: возможно, требует экспоненциального времени
- Проверить предложенное решение: O(n) — просто подставить значения

```python
def verify_sat(formula_cnf, assignment):
    """
    Проверяет, удовлетворяет ли assignment формуле formula_cnf.
    formula_cnf: список клоз (списков литералов)
    assignment: словарь {переменная: bool}
    
    Это O(n) — проверка эффективна!
    """
    for clause in formula_cnf:
        # Каждая клоза должна иметь хотя бы один истинный литерал
        clause_satisfied = False
        for literal in clause:
            var = abs(literal)
            positive = literal > 0
            if assignment.get(var, False) == positive:
                clause_satisfied = True
                break
        if not clause_satisfied:
            return False
    return True

# Формула: (x1 ∨ ¬x2 ∨ x3) ∧ (¬x1 ∨ x2) ∧ (x2 ∨ ¬x3)
formula = [
    [1, -2, 3],    # x1 ∨ ¬x2 ∨ x3
    [-1, 2],       # ¬x1 ∨ x2
    [2, -3],       # x2 ∨ ¬x3
]

# Проверяем предложенное решение: x1=True, x2=True, x3=False
assignment = {1: True, 2: True, 3: False}
print(f"Решение верно: {verify_sat(formula, assignment)}")  # True

# Наивное нахождение: перебор 2^n вариантов
def naive_sat_solver(formula, n_vars):
    for i in range(2**n_vars):
        assignment = {j+1: bool(i >> j & 1) for j in range(n_vars)}
        if verify_sat(formula, assignment):
            return assignment
    return None

solution = naive_sat_solver(formula, 3)
print(f"Найденное решение: {solution}")  # Какое-то из верных
```

**Задача о гамильтоновом цикле**: существует ли цикл, проходящий через каждую вершину ровно один раз?

```python
def verify_hamiltonian_cycle(graph, cycle):
    """
    Проверяет, является ли cycle гамильтоновым циклом в graph.
    Это O(n) — проверка эффективна!
    """
    n = len(graph)
    if len(cycle) != n + 1:  # n вершин + возврат в начало
        return False
    if cycle[0] != cycle[-1]:  # цикл должен замкнуться
        return False
    if len(set(cycle[:-1])) != n:  # каждая вершина ровно раз
        return False
    # Проверяем наличие каждого ребра
    for i in range(n):
        u, v = cycle[i], cycle[i+1]
        if v not in graph.get(u, []):
            return False
    return True

# Граф K4 (полный граф на 4 вершинах)
graph = {0: [1,2,3], 1: [0,2,3], 2: [0,1,3], 3: [0,1,2]}
cycle = [0, 1, 2, 3, 0]
print(f"Гамильтонов цикл: {verify_hamiltonian_cycle(graph, cycle)}")  # True
```

---

## 4. NP-полнота

Задача X является **NP-трудной** (NP-hard), если любая задача из NP полиномиально сводится к X.

Задача X является **NP-полной** (NP-complete), если:
1. X ∈ NP (решение можно проверить за полиномиальное время)
2. X является NP-трудной

NP-полные задачи — «самые трудные в NP». Если бы для любой из них нашёлся полиномиальный алгоритм, он бы решил все задачи из NP — и тогда P = NP.

### Теорема Кука–Левина (1971)

SAT является NP-полной задачей. Это первый доказанный результат о NP-полноте.

**Смысл**: способность решить SAT за полиномиальное время означает способность решить любую задачу из NP за полиномиальное время.

### Список NP-полных задач

NP-полных задач тысячи. Вот классические:

```python
# Задача о рюкзаке (Knapsack Problem)
# Дан рюкзак вместимости W и n предметов с весами w_i и ценностями v_i.
# Можно ли набрать предметы суммарным весом ≤ W с суммарной ценностью ≥ V?

def verify_knapsack(items, capacity, target_value, selected):
    """Проверка решения задачи о рюкзаке — O(n)"""
    total_weight = sum(items[i][0] for i in selected)
    total_value = sum(items[i][1] for i in selected)
    return total_weight <= capacity and total_value >= target_value

# items: [(weight, value), ...]
items = [(2, 3), (3, 4), (4, 5), (5, 6)]
capacity = 8
target_value = 10

# Решение (проверка): берём предметы 0 и 2 (веса 2+4=6, ценности 3+5=8 < 10)
# Берём предметы 1 и 2 (3+4=7, 4+5=9 < 10)
# Берём предметы 0, 1, 2 (2+3+4=9>8) — не помещается
# Берём предметы 0, 1 (2+3=5, 3+4=7 < 10)
# Берём предметы 1, 2 (3+4=7, 4+5=9 < 10) — всё ещё мало
# Это задача оптимизации...

# DP-решение: псевдополиномиальное O(nW)
def knapsack_dp(items, capacity):
    n = len(items)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    
    for i in range(1, n + 1):
        w, v = items[i-1]
        for c in range(capacity + 1):
            dp[i][c] = dp[i-1][c]
            if w <= c:
                dp[i][c] = max(dp[i][c], dp[i-1][c-w] + v)
    
    return dp[n][capacity]

print(f"Максимальная ценность: {knapsack_dp(items, capacity)}")  # 10
```

Задача о рюкзаке NP-полна в общем случае. DP-решение работает за O(nW) — это **псевдополиномиальное** время: если W экспоненциально большое, то это тоже экспоненциально.

### Классические NP-полные задачи:

1. **3-SAT**: выполнимость формулы с клозами размера 3
2. **Гамильтонов цикл**: цикл через все вершины
3. **Задача коммивояжёра (TSP)**: оптимальный обход всех городов
4. **Раскраска графа**: раскраска k красками без одноцветных соседей
5. **Задача о клике**: существует ли клика размера k?
6. **Задача о вершинном покрытии**: существует ли покрытие размера k?
7. **Задача о рюкзаке**: наилучший набор предметов

---

## 5. Почему P = NP имеет значение

Если бы оказалось, что P = NP:
- Криптография RSA была бы взломана: нахождение простых делителей числа стало бы полиномиальным
- Белковые структуры стали бы предсказуемы тривиально
- Оптимизация маршрутов стала бы точной, а не приближённой
- Логические задачи планирования решались бы мгновенно

```python
# Пример: если P = NP, то RSA небезопасен
# RSA основан на трудности факторизации
# Задача факторизации FACTOR: "есть ли у n нетривиальный делитель ≤ k?"
# FACTOR ∈ NP: проверка делителя — O(log n)
# Неизвестно, FACTOR ∈ P или нет

# Если P = NP, то существует полиномиальный алгоритм факторизации
# Это сломало бы всю публичную криптографию RSA/DH

import random

def trial_division(n, limit=10000):
    """Пробное деление — O(√n), медленно для больших n"""
    if n < 2:
        return None
    for p in range(2, min(limit, int(n**0.5) + 1)):
        if n % p == 0:
            return p
    return None

# Маленькое число — быстро
n_small = 12345
factor = trial_division(n_small)
print(f"{n_small} = {factor} × {n_small // factor}")  # Быстро

# Большое число — очень медленно без специальных алгоритмов
n_large = 2**61 - 1  # простое число Мерсенна
# Для криптографических чисел (1024+ бит) пробное деление неприменимо
```

---

## 6. Работа с NP-трудными задачами на практике

Поскольку большинство практических задач NP-трудны, разработчики используют:

### Приближённые алгоритмы

Находят решение с гарантированным отношением к оптимуму.

```python
# Жадный алгоритм для задачи покрытия множеств (Set Cover)
# Оптимальное решение — NP-трудная задача
# Жадный алгоритм даёт O(ln n)-приближение

def greedy_set_cover(universe, subsets):
    """
    universe: множество элементов для покрытия
    subsets: список подмножеств
    """
    covered = set()
    selected = []
    remaining_subsets = list(subsets)
    
    while covered != universe:
        # Выбираем подмножество с наибольшим числом непокрытых элементов
        best = max(remaining_subsets, key=lambda s: len(s - covered))
        if not (best - covered):
            break  # Не можем покрыть все
        selected.append(best)
        covered |= best
        remaining_subsets.remove(best)
    
    return selected

universe = {1, 2, 3, 4, 5, 6, 7}
subsets = [{1,2,3}, {2,4}, {3,4,5}, {5,6,7}, {1,4,6}]
cover = greedy_set_cover(universe, subsets)
print(f"Покрытие: {cover}")  # Не обязательно оптимальное, но ≤ ln(n) × OPT
```

### Эвристики и метаэвристики

- **Симулированный отжиг**: случайный поиск с уменьшающейся «температурой»
- **Генетические алгоритмы**: эволюционный поиск
- **Муравьиные алгоритмы**: коллективная эвристика

### Параметрическая сложность

Некоторые NP-трудные задачи легко решаются, если «трудный параметр» мал:

```python
# Задача о вершинном покрытии: NP-трудная в общем случае
# Но если покрытие имеет размер k, можно решить за O(2^k × n)

def bounded_vertex_cover(graph, k):
    """
    Ищет вершинное покрытие размера ≤ k.
    FPT-алгоритм: O(2^k × (V+E))
    """
    if k < 0:
        return None
    
    # Берём любое ребро (u, v)
    for u in graph:
        for v in graph[u]:
            # Либо u, либо v должна быть в покрытии
            # Пробуем оба варианта (2^k веток)
            for chosen in [u, v]:
                new_graph = {
                    node: [w for w in neighbors if w != chosen]
                    for node, neighbors in graph.items()
                    if node != chosen
                }
                result = bounded_vertex_cover(new_graph, k - 1)
                if result is not None:
                    return {chosen} | result
            return None
    
    return set()  # Нет рёбер — пустое покрытие

# Для малых k это быстро даже при большом графе!
graph = {0: [1, 2], 1: [0, 2], 2: [0, 1, 3], 3: [2]}
cover = bounded_vertex_cover(graph, 2)
print(f"Вершинное покрытие размера ≤ 2: {cover}")  # {1, 2} или {0, 2}
```

---

## 7. Иерархия классов сложности

```
P ⊆ NP ⊆ PSPACE ⊆ EXPTIME

P:      полиномиальное время (детерминированно)
NP:     проверяемо за полиномиальное время
co-NP:  дополнение NP
PSPACE: полиномиальная память (время неограничено)
EXPTIME: экспоненциальное время
```

```
P ⊆ NP ∩ co-NP
NP ⊆ PSPACE
PSPACE = co-PSPACE
PSPACE ⊆ EXPTIME
```

Большинство включений предположительно строгие, но не доказаны (кроме P ⊆ EXPTIME).

### Задачи вне NP

- **PSPACE-полные**: выигрышная стратегия в шахматах на n×n доске
- **EXPTIME-полные**: игра «Жизнь» Конвея
- **Неразрешимые**: проблема остановки, задача о соответствии Поста

---

## Заключение

Теория сложности даёт разработчику критически важный инструмент: **классификацию трудности задач**. Знание о том, является ли задача NP-трудной, позволяет:

1. **Не тратить время** на поиск идеального решения, которого не существует за разумное время
2. **Выбирать правильный подход**: приближение, эвристика, параметрическая сложность
3. **Понимать безопасность**: криптография основана на трудности NP-задач
4. **Оценивать масштабируемость**: O(2^n) алгоритм не запустить на n=100

Вопрос P = NP — один из самых глубоких открытых вопросов математики. Большинство специалистов считают, что P ≠ NP, но это не доказано.

---

## Литература и источники

1. Cook, S. A. (1971). The complexity of theorem proving procedures. *Proceedings of the 3rd Annual ACM Symposium on Theory of Computing*, 151–158. — Теорема Кука (NP-полнота SAT).

2. Karp, R. M. (1972). Reducibility among combinatorial problems. In R. E. Miller & J. W. Thatcher (Eds.), *Complexity of Computer Computations*, 85–103. — 21 NP-полная задача.

3. Sipser, M. (2012). *Introduction to the Theory of Computation* (3rd ed.). Cengage Learning. — Лучшее введение в теорию сложности.

4. Garey, M. R., & Johnson, D. S. (1979). *Computers and Intractability: A Guide to the Theory of NP-Completeness*. Freeman. — Классика, каталог NP-полных задач.

5. Arora, S., & Barak, B. (2009). *Computational Complexity: A Modern Approach*. Cambridge University Press. Доступно онлайн: https://theory.cs.princeton.edu/complexity/

6. Aaronson, S. Why Philosophers Should Care About Computational Complexity. https://arxiv.org/abs/1108.1791 — Доступная статья о значении P vs NP.

7. Смейлс, С. (2000). Математические задачи на следующее тысячелетие. *Russian Mathematical Surveys*. — Контекст задач тысячелетия.
