# Кучи (heap) и приоритетные очереди

Куча (heap) — элегантная структура данных, скрывающая сложность за простым интерфейсом: вставить элемент и извлечь минимум (или максимум) за O(log n). Эта возможность лежит в основе алгоритма Дейкстры, сортировки heapsort, систем планирования задач и обработки событий. Понимание кучи — понимание того, как из простого массива получается мощная структура.

## Приоритетная очередь: абстракция

Приоритетная очередь (priority queue) — абстрактный тип данных с операциями:
- **insert(key, value)** — вставить элемент с приоритетом key
- **find_min()** — найти элемент с минимальным приоритетом (O(1))
- **extract_min()** — извлечь элемент с минимальным приоритетом (O(log n))
- **decrease_key(element, new_key)** — уменьшить приоритет элемента

Аналогия: "очередь к врачу" не в порядке прихода, а по тяжести состояния. Всегда следующий — самый тяжёлый пациент.

## Бинарная куча: представление в массиве

Бинарная куча — специальное бинарное дерево, хранимое в массиве. Два ключевых свойства:

1. **Свойство кучи (heap property):** Для min-heap — ключ каждого узла $\leq$ ключей его потомков. Корень = минимум.

2. **Полнота дерева:** Все уровни заполнены, кроме последнего (который заполняется слева направо).

```
Min-heap:
          1
        /   \
       3     2
      / \   / \
     7   4 5   6
    / \
   8   9

Представление в массиве:
индекс: 0  1  2  3  4  5  6  7  8
значение: 1  3  2  7  4  5  6  8  9
```

### Арифметика индексов

Ключевой трюк: для узла с индексом i:
- Левый потомок: 2i + 1
- Правый потомок: 2i + 2
- Родитель: (i - 1) // 2

```python
# 0-based indexing
def parent(i): return (i - 1) // 2
def left(i):   return 2 * i + 1
def right(i):  return 2 * i + 2

# 1-based indexing (удобнее математически)
def parent1(i): return i // 2
def left1(i):   return 2 * i
def right1(i):  return 2 * i + 1
```

Это позволяет хранить "дерево" в обычном массиве без указателей — отличная локальность кеша!

## Операции кучи

### heapify_up (sift up): после вставки

После вставки в конец массива нужно "всплыть" до правильной позиции:

```python
class MinHeap:
    def __init__(self):
        self.heap = []
    
    def push(self, val):
        """O(log n)"""
        self.heap.append(val)
        self._sift_up(len(self.heap) - 1)
    
    def _sift_up(self, i):
        """Восстанавливаем свойство кучи снизу вверх"""
        while i > 0:
            p = (i - 1) // 2  # индекс родителя
            if self.heap[p] > self.heap[i]:
                self.heap[p], self.heap[i] = self.heap[i], self.heap[p]
                i = p
            else:
                break  # свойство кучи выполнено
    
    def peek(self):
        """O(1): минимальный элемент"""
        return self.heap[0] if self.heap else None
    
    def pop(self):
        """O(log n): извлечь минимум"""
        if not self.heap:
            return None
        
        # Перемещаем последний элемент на место минимума
        self.heap[0] = self.heap[-1]
        self.heap.pop()
        
        if self.heap:
            self._sift_down(0)
        
        return self.heap[0] if self.heap else None
    
    def _sift_down(self, i):
        """Восстанавливаем свойство кучи сверху вниз"""
        n = len(self.heap)
        
        while True:
            smallest = i
            l, r = 2*i + 1, 2*i + 2
            
            if l < n and self.heap[l] < self.heap[smallest]:
                smallest = l
            if r < n and self.heap[r] < self.heap[smallest]:
                smallest = r
            
            if smallest == i:
                break  # свойство кучи выполнено
            
            self.heap[i], self.heap[smallest] = self.heap[smallest], self.heap[i]
            i = smallest
    
    def __len__(self):
        return len(self.heap)

# Пример
heap = MinHeap()
for v in [5, 3, 8, 1, 4, 2]:
    heap.push(v)

results = []
while heap:
    results.append(heap.pop())
# [1, 2, 3, 4, 5, 8] — отсортировано!
```

### O(n) построение кучи: heapify

Наивное построение — n раз вставить, каждый раз O(log n) = O(n log n). Но есть лучший способ!

**Ключевое наблюдение:** Листья уже являются корректными кучами. Нужно sift_down только для внутренних узлов, снизу вверх.

```python
def build_heap(arr):
    """O(n) — линейное построение кучи"""
    n = len(arr)
    
    # Начинаем с последнего внутреннего узла: (n//2 - 1)
    # Листья (индексы n//2 ... n-1) уже корректны
    for i in range(n // 2 - 1, -1, -1):
        sift_down(arr, i, n)
    
    return arr

def sift_down(arr, i, n):
    while True:
        smallest = i
        l, r = 2*i + 1, 2*i + 2
        if l < n and arr[l] < arr[smallest]: smallest = l
        if r < n and arr[r] < arr[smallest]: smallest = r
        if smallest == i: break
        arr[i], arr[smallest] = arr[smallest], arr[i]
        i = smallest

# Доказательство O(n):
# Высота h: 2^(h-1) листьев — 0 работы
#            2^(h-2) узлов — 1 sift_down шаг
#            2^(h-3) узлов — 2 sift_down шага
#            ...
#            1 корень — h sift_down шагов
# Σ k * n/2^k = O(n) по формуле геометрической прогрессии

arr = [5, 3, 8, 1, 4, 2, 7, 6]
build_heap(arr)
print(arr)  # [1, 3, 2, 6, 4, 5, 7, 8] — корректная min-heap!
```

## Heapsort

Heapsort использует кучу для сортировки за O(n log n) с O(1) дополнительной памяти:

```python
def heapsort(arr):
    """O(n log n), O(1) доп. памяти, in-place"""
    n = len(arr)
    
    # 1. Построить max-heap: O(n)
    for i in range(n // 2 - 1, -1, -1):
        _sift_down_max(arr, i, n)
    
    # 2. Извлекать максимум n раз: O(n log n)
    for i in range(n-1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]  # максимум в конец
        _sift_down_max(arr, 0, i)        # восстановить heap для [0..i-1]

def _sift_down_max(arr, i, n):
    """Max-heap sift down"""
    while True:
        largest = i
        l, r = 2*i + 1, 2*i + 2
        if l < n and arr[l] > arr[largest]: largest = l
        if r < n and arr[r] > arr[largest]: largest = r
        if largest == i: break
        arr[i], arr[largest] = arr[largest], arr[i]
        i = largest

# Тест
arr = [64, 25, 12, 22, 11]
heapsort(arr)
print(arr)  # [11, 12, 22, 25, 64]
```

Heapsort гарантирует O(n log n) в любом случае, в отличие от quicksort. Но на практике медленнее quicksort из-за плохой локальности кеша.

## Python heapq: стандартная библиотека

```python
import heapq

# Python heapq — минимальная куча
heap = []
for val in [5, 3, 8, 1, 4]:
    heapq.heappush(heap, val)

print(heap[0])            # 1 — минимум O(1)
print(heapq.heappop(heap))  # 1 — O(log n)

# Построение кучи из списка O(n):
arr = [5, 3, 8, 1, 4, 2]
heapq.heapify(arr)

# nlargest и nsmallest — эффективно!
print(heapq.nlargest(3, arr))   # [8, 5, 4]
print(heapq.nsmallest(3, arr))  # [1, 2, 3]
# Эффективнее sorted()[:k] при k << n

# Max-heap через отрицание:
max_heap = []
for val in [5, 3, 8, 1, 4]:
    heapq.heappush(max_heap, -val)

print(-heapq.heappop(max_heap))  # 8 — максимум!

# Элементы с приоритетами:
import time
tasks = []
heapq.heappush(tasks, (1, "critical task"))
heapq.heappush(tasks, (3, "low priority"))
heapq.heappush(tasks, (2, "medium task"))

while tasks:
    priority, task = heapq.heappop(tasks)
    print(f"Executing: {task} (priority {priority})")
# critical task (1), medium task (2), low priority (3)
```

## Приоритетные очереди: применения

### Алгоритм Дейкстры

```python
import heapq
from collections import defaultdict

def dijkstra(graph, start):
    """Кратчайший путь от start до всех вершин"""
    # graph = {vertex: [(weight, neighbor), ...]}
    
    distances = defaultdict(lambda: float('inf'))
    distances[start] = 0
    
    # Куча: (расстояние, вершина)
    pq = [(0, start)]
    visited = set()
    
    while pq:
        dist, vertex = heapq.heappop(pq)
        
        if vertex in visited:
            continue
        visited.add(vertex)
        
        for weight, neighbor in graph[vertex]:
            new_dist = dist + weight
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                heapq.heappush(pq, (new_dist, neighbor))
    
    return dict(distances)

# Пример: граф городов
graph = {
    'A': [(4, 'B'), (2, 'C')],
    'B': [(3, 'D'), (1, 'C')],
    'C': [(5, 'D'), (3, 'E')],
    'D': [(1, 'E')],
    'E': []
}

distances = dijkstra(graph, 'A')
print(distances)
# {'A': 0, 'C': 2, 'B': 3, 'E': 5, 'D': 6}
```

### Event-driven simulation

```python
import heapq
from dataclasses import dataclass, field
from typing import Any

@dataclass(order=True)
class Event:
    time: float
    callback: Any = field(compare=False)

class EventSimulator:
    def __init__(self):
        self.events = []
        self.current_time = 0
    
    def schedule(self, delay, callback):
        """Запланировать событие через delay единиц времени"""
        event_time = self.current_time + delay
        heapq.heappush(self.events, Event(event_time, callback))
    
    def run_until(self, end_time):
        """Запустить симуляцию до end_time"""
        while self.events and self.events[0].time <= end_time:
            event = heapq.heappop(self.events)
            self.current_time = event.time
            event.callback(self)

# Симуляция сети пакетов
sim = EventSimulator()

def packet_arrives(sim):
    print(f"t={sim.current_time:.1f}: Пакет прибыл")
    sim.schedule(2.5, packet_arrives)  # следующий пакет

sim.schedule(0.1, packet_arrives)
sim.run_until(10)
```

### Планировщик задач ОС

```python
class ProcessScheduler:
    """Простой priority-based scheduler"""
    
    def __init__(self):
        self.ready_queue = []  # min-heap по (priority, arrival_time, pid)
        self.time = 0
    
    def add_process(self, pid, priority):
        heapq.heappush(self.ready_queue, (priority, self.time, pid))
        self.time += 1
    
    def next_process(self):
        """Выбрать следующий процесс для выполнения"""
        if self.ready_queue:
            _, _, pid = heapq.heappop(self.ready_queue)
            return pid
        return None

scheduler = ProcessScheduler()
scheduler.add_process("process_A", priority=3)
scheduler.add_process("process_B", priority=1)  # высший приоритет
scheduler.add_process("process_C", priority=2)

# Выполняем в порядке приоритетов:
while True:
    pid = scheduler.next_process()
    if not pid: break
    print(f"Running: {pid}")
# process_B, process_C, process_A
```

## d-ary heap: обобщение

Вместо бинарной кучи (2 потомка) можно использовать d-ary heap с d потомками:

```python
class DAryHeap:
    def __init__(self, d=4):  # 4-ary heap
        self.d = d
        self.heap = []
    
    def _parent(self, i): return (i - 1) // self.d
    def _children(self, i): return range(i*self.d + 1, i*self.d + self.d + 1)
    
    def push(self, val):
        self.heap.append(val)
        i = len(self.heap) - 1
        while i > 0:
            p = self._parent(i)
            if self.heap[p] > self.heap[i]:
                self.heap[p], self.heap[i] = self.heap[i], self.heap[p]
                i = p
            else:
                break
    
    # sift_down теперь выбирает из d потомков

# d=4 быстрее при:
# - Меньше уровней дерева → меньше sift_up шагов
# - Но sift_down требует сравнения d детей

# Оптимальный d зависит от соотношения insert/extract
# Для Dijkstra (много insert, мало extract) d > 2 выгодно
```

## Fibonacci Heap: теоретически O(1) decrease_key

Fibonacci heap (Fredman и Tarjan, 1984) — сложная структура с амортизированными гарантиями:

| Операция | Fibonacci heap | Binary heap |
|----------|---------------|-------------|
| insert | O(1) amortized | O(log n) |
| find_min | O(1) | O(1) |
| extract_min | O(log n) amortized | O(log n) |
| decrease_key | **O(1) amortized** | O(log n) |
| merge | O(1) | O(n) |

decrease_key за O(1) делает Dijkstra с Fibonacci heap теоретически O(V log V + E) против O((V + E) log V) с binary heap.

```python
# Fibonacci heap сложна в реализации
# На практике константы настолько велики, что binary heap быстрее
# для типичных задач

# Используется в: CLRS как теоретический инструмент
# На практике: почти нигде (splay tree иногда конкурирует)
```

## Binomial Heap: слияние за O(log n)

Binomial heap — коллекция биномиальных деревьев, поддерживающая слияние за O(log n):

```
Слияние двух min-heap по O(log n):
Fibonacci heap: O(1)
Binomial heap:  O(log n)
Binary heap:    O(n)

Применение: алгоритм Прима для MST, очереди с приоритетами в функциональных языках
```

## k-я наибольшего элемент: классическая задача

```python
import heapq

def find_kth_largest(nums, k):
    """O(n log k) — лучше чем O(n log n) полной сортировки"""
    # Поддерживаем min-heap размера k
    # Минимум в куче = k-й наибольший!
    heap = nums[:k]
    heapq.heapify(heap)  # O(k)
    
    for num in nums[k:]:
        if num > heap[0]:  # больше текущего k-го
            heapq.heapreplace(heap, num)  # O(log k)
    
    return heap[0]  # k-й наибольший

print(find_kth_largest([3, 2, 1, 5, 6, 4], k=2))  # 5 (2-й наибольший)
print(find_kth_largest([3, 2, 3, 1, 2, 4, 5, 5, 6], k=4))  # 4

# Альтернатива: quickselect O(n) в среднем
import random

def quickselect(arr, k):
    """O(n) в среднем для k-го наименьшего"""
    if len(arr) == 1:
        return arr[0]
    
    pivot = random.choice(arr)
    left = [x for x in arr if x < pivot]
    right = [x for x in arr if x > pivot]
    equal = [x for x in arr if x == pivot]
    
    if k <= len(left):
        return quickselect(left, k)
    elif k <= len(left) + len(equal):
        return pivot
    else:
        return quickselect(right, k - len(left) - len(equal))
```

## Итоги

Бинарная куча — эффективная реализация приоритетной очереди:

- **O(1) find_min:** Корень дерева всегда минимум
- **O(log n) insert/extract_min:** Sift up/down по высоте
- **O(n) build_heap:** Линейное построение из массива
- **Хранение в массиве:** Нет указателей, отличная локальность кеша

Приоритетные очереди — основа для Dijkstra, A*, event simulation, OS schedulers, heapsort и многих других алгоритмов.

## Литература

1. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Глава 6 — Heapsort; Глава 19 — Fibonacci Heaps.

2. Williams, J. W. J. (1964). Algorithm 232: Heapsort. *Communications of the ACM*, 7(6), 347–348. — оригинальная статья о heapsort и куче

3. Fredman, M. L., & Tarjan, R. E. (1987). Fibonacci heaps and their uses in improved network optimization algorithms. *Journal of the ACM*, 34(3), 596–615. https://dl.acm.org/doi/10.1145/28869.28874

4. Floyd, R. W. (1964). Algorithm 245: TREESORT. *Communications of the ACM*, 7(12). — O(n) heapify

5. Python `heapq` documentation. https://docs.python.org/3/library/heapq.html

6. Vuillemin, J. (1978). A data structure for manipulating priority queues. *Communications of the ACM*, 21(4), 309–315. — Binomial Heap

7. Sedgewick, R., & Wayne, K. (2011). *Algorithms* (4th ed.). Addison-Wesley. Глава 2.4 — Priority Queues.

8. Dijkstra, E. W. (1959). A note on two problems in connexion with graphs. *Numerische Mathematik*, 1, 269–271. — оригинальный алгоритм Дейкстры

9. Knuth, D. E. (1998). *The Art of Computer Programming, Vol. 3*, Section 5.2.3. — Heapsort analysis.

10. Brodal, G. S., & Lagogiannis, G., & Tarjan, R. E. (2012). Strict Fibonacci heaps. *STOC 2012*. https://dl.acm.org/doi/10.1145/2213977.2214082 — worst-case O(1) decrease_key
