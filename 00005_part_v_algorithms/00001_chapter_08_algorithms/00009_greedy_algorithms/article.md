# Жадные алгоритмы: когда они вообще корректны

Жадный алгоритм делает на каждом шаге локально оптимальный выбор, надеясь, что это приведёт к глобальному оптимуму. Это самая интуитивная идея в алгоритмике — и одна из самых обманчивых. Иногда жадный подход даёт идеально правильный ответ (алгоритмы Кана, Прима, Дейкстры, Хаффмана). Иногда — катастрофически ошибочный. Знать разницу и уметь доказывать корректность жадного алгоритма — это искусство.

## Что такое жадная стратегия

Жадный алгоритм строит решение поэтапно. На каждом этапе:
1. Рассматривает доступные варианты
2. Выбирает "наилучший" по некоторому критерию
3. **Не пересматривает** сделанный выбор

Аналогия: жадный человек на шведском столе — берёт самое большое блюдо, не думая о том, влезет ли в него всё остальное.

## Exchange Argument: доказательство корректности

Самый распространённый метод доказательства корректности жадного алгоритма — **exchange argument** (аргумент обмена).

**Идея:** Предположим, существует оптимальное решение OPT, отличающееся от жадного GREEDY. Покажем, что мы можем преобразовать OPT в GREEDY, обменяв элементы, без ухудшения качества. Значит, GREEDY не хуже OPT.

### Пример: покрытие интервалов

Задача: есть n занятий, каждое занимает отрезок [sᵢ, fᵢ]. Выбрать максимальное количество занятий, которые можно посетить (без пересечений).

**Жадная стратегия:** Всегда выбираем занятие с наименьшим временем завершения.

```python
def activity_selection(activities):
    """
    Максимальное независимое множество интервалов.
    activities = [(start, finish), ...]
    O(n log n) из-за сортировки
    """
    # Сортируем по времени завершения
    sorted_acts = sorted(activities, key=lambda x: x[1])
    
    selected = [sorted_acts[0]]
    last_finish = sorted_acts[0][1]
    
    for start, finish in sorted_acts[1:]:
        if start >= last_finish:  # не пересекается с последним выбранным
            selected.append((start, finish))
            last_finish = finish
    
    return selected

activities = [(1,4), (3,5), (0,6), (5,7), (3,8), (5,9), (6,10), (8,11), (8,12), (2,13), (12,14)]
result = activity_selection(activities)
print(result)  # [(1, 4), (5, 7), (8, 11), (12, 14)] — 4 занятия

# Доказательство Exchange Argument:
# Пусть OPT ≠ GREEDY.
# Рассмотрим первый шаг, где они различаются:
# GREEDY выбрал a_g (наименьшее f_g)
# OPT выбрал a_o (другое занятие, f_o >= f_g)
# Заменим a_o на a_g в OPT:
# - f_g <= f_o → a_g не конфликтует с последующими элементами OPT (даже лучше!)
# - Количество занятий не уменьшилось
# Итерируя, превращаем OPT в GREEDY → GREEDY не хуже OPT!
```

## Матроиды и жадные алгоритмы

Математическое объяснение, когда жадный алгоритм корректен, — **теория матроидов**.

**Матроид** (M = (S, I)) — пара "основное множество S" + "независимые подмножества I", удовлетворяющая:
1. $\emptyset \in I$
2. Наследственность: $A \in I,\, B \subseteq A \to B \in I$
3. Обмен: $A, B \in I,\, |A| < |B| \to \exists\, x \in B \setminus A : A \cup \{x\} \in I$

**Теорема:** Для матроида с весовой функцией жадный алгоритм (добавляем элемент с максимальным весом, если можно) находит максимальное независимое множество оптимального веса.

```python
# Пример графового матроида: леса графа
# S = рёбра графа
# I = подмножества рёбер, не образующих цикл (леса)
# Это матроид! → Жадный алгоритм (Kruskal) оптимален

# Алгоритм Крускала = жадный на графовом матроиде
def kruskal_greedy(edges, n):
    """
    Минимальное остовное дерево = жадный на матроиде.
    edges: [(weight, u, v), ...]
    Жадно добавляем рёбра с минимальным весом, не создающие цикл.
    """
    parent = list(range(n))
    
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    
    def union(x, y):
        px, py = find(x), find(y)
        if px == py: return False
        parent[py] = px
        return True
    
    mst = []
    for weight, u, v in sorted(edges):
        if union(u, v):   # жадно добавляем наименьшее ребро без цикла
            mst.append((u, v, weight))
    
    return mst
```

## Классические жадные задачи

### Задача о расписании (Job Scheduling)

**Вариант 1:** Минимизировать суммарное взвешенное время завершения.

```python
def weighted_scheduling(jobs):
    """
    jobs = [(weight, time), ...] — (вес/приоритет, время выполнения)
    Минимизировать: Σ wᵢ * Cᵢ, где Cᵢ — время завершения задачи i
    
    Жадная стратегия: сортируем по w/t (убыв.)
    Обоснование: exchange argument показывает, что любая перестановка
    соседних задач с ratio w1/t1 < w2/t2 ухудшает результат.
    """
    # Сортируем по w/t в порядке убывания
    sorted_jobs = sorted(jobs, key=lambda j: -j[0]/j[1])
    
    completion_time = 0
    total_weighted = 0
    
    for weight, time in sorted_jobs:
        completion_time += time
        total_weighted += weight * completion_time
    
    return total_weighted, sorted_jobs

jobs = [(3, 5), (1, 2), (4, 3), (2, 6)]  # (weight, time)
cost, order = weighted_scheduling(jobs)
print(f"Оптимальный порядок: {order}")
print(f"Суммарное взвешенное время: {cost}")
```

**Вариант 2:** Максимальное количество задач до дедлайна.

```python
def deadline_scheduling(jobs):
    """
    jobs = [(profit, deadline), ...]
    Максимизировать прибыль: каждая задача занимает 1 единицу времени.
    
    Жадная стратегия: сортируем по прибыли (убыв.),
    каждую задачу ставим на последний свободный слот до её дедлайна.
    """
    sorted_jobs = sorted(jobs, key=lambda j: -j[0])
    max_deadline = max(d for _, d in jobs)
    
    schedule = [None] * (max_deadline + 1)  # schedule[t] = задача в момент t
    
    total_profit = 0
    chosen = []
    
    for profit, deadline in sorted_jobs:
        # Ищем последний свободный слот до deadline
        slot = min(deadline, max_deadline)
        while slot > 0 and schedule[slot] is not None:
            slot -= 1
        
        if slot > 0:
            schedule[slot] = profit
            total_profit += profit
            chosen.append((profit, deadline))
    
    return total_profit, chosen

jobs = [(100, 2), (27, 1), (15, 2), (10, 1)]
profit, chosen = deadline_scheduling(jobs)
print(f"Прибыль: {profit}")  # 127 (100+27)
```

### Алгоритм Хаффмана: жадный DP?

Алгоритм Хаффмана — классический жадный алгоритм. На каждом шаге объединяем два узла с наименьшими частотами.

```python
import heapq
from dataclasses import dataclass, field
from typing import Optional

@dataclass(order=True)
class HuffNode:
    freq: int
    char: Optional[str] = field(default=None, compare=False)
    left: Optional['HuffNode'] = field(default=None, compare=False)
    right: Optional['HuffNode'] = field(default=None, compare=False)

def huffman(frequencies: dict) -> dict:
    """
    Жадный алгоритм Хаффмана.
    Доказательство корректности: матроидная структура
    (через обмен двух узлов с наименьшими частотами).
    """
    heap = [HuffNode(freq=f, char=c) for c, f in frequencies.items()]
    heapq.heapify(heap)
    
    while len(heap) > 1:
        left = heapq.heappop(heap)   # минимальная частота
        right = heapq.heappop(heap)  # вторая минимальная
        
        # Жадно объединяем два наименьших
        parent = HuffNode(
            freq=left.freq + right.freq,
            left=left, right=right
        )
        heapq.heappush(heap, parent)
    
    root = heap[0]
    
    # Генерируем коды
    codes = {}
    def traverse(node, code=""):
        if node.char:
            codes[node.char] = code or "0"
        else:
            traverse(node.left, code + "0")
            traverse(node.right, code + "1")
    
    traverse(root)
    return codes

freq = {'a': 5, 'b': 9, 'c': 12, 'd': 13, 'e': 16, 'f': 45}
codes = huffman(freq)

# Вычислим среднюю длину кода
total_chars = sum(freq.values())
avg_len = sum(freq[c] * len(codes[c]) for c in codes) / total_chars
print(f"Коды: {codes}")
print(f"Средняя длина: {avg_len:.2f} бит/символ")

# Хаффман оптимален! Любой другой prefix code даст большую/равную среднюю длину.
```

### Задача о сдаче монет

Классический пример, где жадный **иногда** работает:

```python
def change_greedy(coins, amount):
    """Жадный: берём наибольшую монету, которая помещается"""
    coins = sorted(coins, reverse=True)
    result = []
    for coin in coins:
        while amount >= coin:
            result.append(coin)
            amount -= coin
    return result if amount == 0 else None

# Когда жадный правильный (евро/доллары):
coins_eu = [25, 10, 5, 1]
print(change_greedy(coins_eu, 41))  # [25, 10, 5, 1] — 4 монеты, правильно!

# Когда жадный НЕПРАВИЛЬНЫЙ:
coins_broken = [1, 3, 4]
greedy_result = change_greedy(coins_broken, 6)  # [4, 1, 1] — 3 монеты
dp_result = coin_change(coins_broken, 6)         # 2 (3+3) — лучше!

print(f"Жадный для 6 с {coins_broken}: {greedy_result} ({len(greedy_result)} монеты)")
print(f"DP для 6 с {coins_broken}: {dp_result} монеты")
```

## Задача о покрытии множествами (Set Cover)

Одна из самых важных задач, где жадный даёт приближённое (не точное!) решение.

```python
def set_cover_greedy(universe, subsets):
    """
    Приближённое покрытие множествами.
    universe — все элементы которые нужно покрыть
    subsets — список подмножеств
    
    Жадно: выбираем подмножество с максимальным числом непокрытых элементов.
    
    Гарантия: жадный даёт O(log n) приближение — это оптимально!
    (Set Cover NP-hard → нет polynomial точного алгоритма, если P ≠ NP)
    """
    uncovered = set(universe)
    chosen = []
    
    while uncovered:
        best = max(subsets, key=lambda s: len(s & uncovered))
        if not (best & uncovered):
            return None  # невозможно покрыть
        chosen.append(best)
        uncovered -= best
    
    return chosen

universe = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
subsets = [
    {1, 2, 3, 4},    # покрывает 4 элемента
    {2, 3, 5, 6},
    {1, 4, 7, 8},
    {3, 6, 9, 10},
    {5, 7, 8, 9},
]

cover = set_cover_greedy(universe, subsets)
print(f"Покрытие: {len(cover)} подмножеств")
```

## Жадный vs DP: сравнение

```python
# Задача о рюкзаке:

# Целочисленный (0/1) рюкзак: жадный НЕ оптимален
# Нужен DP: O(n*W)
items_wv = [(2, 3), (3, 4), (4, 5), (5, 6)]  # (weight, value)
capacity = 8

def fractional_knapsack(items, capacity):
    """
    ДРОБНЫЙ рюкзак: жадный ОПТИМАЛЕН!
    Каждый предмет можно взять частично.
    Жадная стратегия: берём по убыванию value/weight ratio
    """
    # Сортируем по value/weight
    sorted_items = sorted(items, key=lambda x: x[1]/x[0], reverse=True)
    
    total_value = 0
    remaining = capacity
    taken = []
    
    for weight, value in sorted_items:
        if remaining <= 0:
            break
        fraction = min(1.0, remaining / weight)
        total_value += fraction * value
        taken.append((weight, value, fraction))
        remaining -= weight * fraction
    
    return total_value, taken

frac_val, frac_items = fractional_knapsack(items_wv, capacity)
print(f"Дробный рюкзак: {frac_val:.2f}")  # оптимально!

# Целочисленный: нужен DP
from functools import lru_cache
weights = [w for w,v in items_wv]
values = [v for w,v in items_wv]

@lru_cache(maxsize=None)
def knapsack_01(i, w):
    if i == 0 or w == 0: return 0
    if weights[i-1] > w:
        return knapsack_01(i-1, w)
    return max(knapsack_01(i-1, w),
               knapsack_01(i-1, w-weights[i-1]) + values[i-1])

print(f"0/1 рюкзак: {knapsack_01(len(weights), capacity)}")
```

## Контрпримеры: когда жадный ошибается

```python
# 1. Задача о рюкзаке
items = [(10, 60), (20, 100), (30, 120)]  # (weight, value)
capacity = 50
# Жадный (по value/weight): берёт (10,60) и (20,100) = 160
# DP: берёт (20,100) и (30,120) = 220! — жадный ошибся

# 2. Кратчайший путь с "разворотами":
# 
#     1  →  2  →  3  →  цель
#           ↓              ↑
#           4  ──────────── 
# Цена 1→2→3→цель = 100 (по 1 за шаг, но 3→цель стоит 97)
# Цена 1→2→4→цель = 100 (2→4=1, 4→цель=98)
# Жадный берёт 1 шаг, Дейкстра найдёт правильно.

# 3. Задача о размене монет (уже видели)

# 4. Maximum Cut: в общем случае NP-hard
# Жадный: добавляй рёбра в разрез пока можно — не оптимален

# 5. Задача коммивояжёра (TSP): жадный nearest neighbor
# Иногда в 2x хуже оптимума!
def tsp_greedy_nearest(dist, start=0):
    """Жадный TSP: всегда идём в ближайший непосещённый город"""
    n = len(dist)
    visited = [False] * n
    tour = [start]
    visited[start] = True
    
    for _ in range(n - 1):
        last = tour[-1]
        nearest = min(
            (j for j in range(n) if not visited[j]),
            key=lambda j: dist[last][j]
        )
        tour.append(nearest)
        visited[nearest] = True
    
    return tour + [start]  # возврат в начало

# Это не оптимальное решение TSP!
# TSP NP-hard → нет polynomial exact алгоритма
```

## Алгоритм Прима: жадный для MST

```python
def prim_greedy(graph, start, vertices):
    """
    Жадный: всегда добавляем наименьшее ребро в MST.
    Доказательство: cut property матроидов.
    O((V + E) log V)
    """
    import heapq
    in_mst = {start}
    heap = []
    
    for neighbor, w in graph[start]:
        heapq.heappush(heap, (w, start, neighbor))
    
    mst_edges = []
    total = 0
    
    while heap and len(in_mst) < len(vertices):
        w, u, v = heapq.heappop(heap)
        if v in in_mst:
            continue
        in_mst.add(v)
        mst_edges.append((u, v, w))
        total += w
        for neighbor, weight in graph[v]:
            if neighbor not in in_mst:
                heapq.heappush(heap, (weight, v, neighbor))
    
    return mst_edges, total
```

## Доказательство через матроиды: почему Хаффман жаден и правильно

Формальное доказательство Хаффмана как жадного алгоритма на матроиде:

**Лемма (Exchange):** Пусть x и y — два символа с наименьшими частотами. Существует оптимальный код, в котором x и y имеют одинаковую глубину и отличаются только последним битом.

**Доказательство:** Рассмотрим произвольный оптимальный код T. Найдём в нём два символа a и b на наибольшей глубине. Обменяем a и x, b и y. Стоимость:
- cost(T) - freq(x)*depth(x) - freq(a)*depth(a) + freq(x)*depth(a) + freq(a)*depth(x)
- = cost(T) + (freq(a) - freq(x))*(depth(x) - depth(a))
- $\leq$ cost(T), так как depth(a) $\geq$ depth(x) и freq(a) $\geq$ freq(x)

Значит, новый код не хуже T, и в нём x и y на максимальной глубине.

## Итоги

Жадные алгоритмы правильны тогда, когда:
1. **Exchange argument** доказывает, что локальный выбор — глобально оптимален
2. Задача имеет **матроидную структуру** (Kruskal, Huffman)
3. Задача имеет **greedy-choice property** + **optimal substructure**

Жадный НЕ правилен для: общей задачи о рюкзаке, TSP, Set Cover (точно), задачи о монетах с произвольными номиналами.

**Золотое правило:** всегда проверяйте жадный контрпримером перед использованием!

## Литература

1. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Глава 16 — Greedy Algorithms.

2. Huffman, D. A. (1952). A method for the construction of minimum-redundancy codes. *Proceedings of the IRE*, 40(9), 1098–1101.

3. Kruskal, J. B. (1956). On the Shortest Spanning Subtree of a Graph. *Proceedings of the AMS*, 7(1).

4. Lawler, E. L. (1973). Optimal Sequencing of a Single Machine Subject to Precedence Constraints. *Management Science*, 19(5). — задача о расписании

5. Edmonds, J. (1971). Matroids and the greedy algorithm. *Mathematical Programming*, 1(1), 127–136. https://link.springer.com/article/10.1007/BF01584082 — теория матроидов

6. Johnson, D. S. (1974). Approximation algorithms for combinatorial problems. *Journal of Computer and System Sciences*, 9(3). — жадный для Set Cover

7. Dasgupta, S., Papadimitriou, C., & Vazirani, U. (2006). *Algorithms*. McGraw-Hill. Глава 5 — Greedy Algorithms.

8. Sedgewick, R., & Wayne, K. (2011). *Algorithms* (4th ed.). Addison-Wesley. Раздел 4.3 — Minimum Spanning Trees.

9. Skiena, S. S. (2008). *The Algorithm Design Manual* (2nd ed.). Springer. Глава 16 — Greedy Algorithms.

10. Oxley, J. G. (2011). *Matroid Theory* (2nd ed.). Oxford University Press. — математические основы матроидов
