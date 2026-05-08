# Сортировки: quicksort, mergesort, heapsort, radix — почему встроенный sort гибрид

Сортировка — один из самых изученных разделов алгоритмики. Существуют десятки алгоритмов сортировки, и каждый язык программирования вложил значительные усилия в выбор и реализацию своего стандартного `sort`. Понимание того, почему Python использует Timsort, а Rust — pdqsort, даёт глубокое понимание trade-off'ов в алгоритмическом дизайне.

## Нижняя граница: O(n log n) для сравнительных сортировок

Прежде чем рассматривать алгоритмы, зафиксируем теоретический предел.

**Теорема:** Любая сортировка, основанная на сравнениях, требует Ω(n log n) операций в худшем случае.

**Доказательство через дерево решений:** Алгоритм сортировки — это бинарное дерево, где каждый внутренний узел — сравнение, а листья — перестановки. Для n элементов есть n! перестановок, значит n! листьев. Высота дерева ≥ log₂(n!) = Θ(n log n) по формуле Стирлинга.

```python
import math

# Нижняя граница:
n = 10
print(f"n! = {math.factorial(n)}")          # 3628800
print(f"log2(n!) ≈ {math.log2(math.factorial(n)):.1f}")  # 21.8
print(f"n*log2(n) = {n * math.log2(n):.1f}")  # 33.2
# Оба O(n log n)

# Следствие: quicksort, mergesort, heapsort — все оптимальны!
# (по порядку роста)
```

## Quicksort: pivot, partitioning и рандомизация

Quicksort — алгоритм разработки Хоара (1959), и по сей день является одним из быстрейших на практике.

### Базовый quicksort

```python
def quicksort_simple(arr):
    """Простейший quicksort: O(n²) в худшем случае"""
    if len(arr) <= 1:
        return arr
    
    pivot = arr[len(arr) // 2]
    left   = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right  = [x for x in arr if x > pivot]
    
    return quicksort_simple(left) + middle + quicksort_simple(right)

print(quicksort_simple([3, 6, 8, 10, 1, 2, 1]))
```

### In-place quicksort с partition Ломуто

```python
def quicksort_lomuto(arr, lo=0, hi=None):
    """
    In-place quicksort, схема Lomuto.
    O(n log n) в среднем, O(n²) в худшем.
    """
    if hi is None:
        hi = len(arr) - 1
    
    if lo >= hi:
        return
    
    pivot_idx = partition_lomuto(arr, lo, hi)
    quicksort_lomuto(arr, lo, pivot_idx - 1)
    quicksort_lomuto(arr, pivot_idx + 1, hi)

def partition_lomuto(arr, lo, hi):
    """Схема разбиения Lomuto: pivot = последний элемент"""
    pivot = arr[hi]
    i = lo - 1  # граница "меньших" элементов
    
    for j in range(lo, hi):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    
    arr[i+1], arr[hi] = arr[hi], arr[i+1]
    return i + 1
```

### Схема разбиения Хоара (более быстрая)

```python
def partition_hoare(arr, lo, hi):
    """Схема разбиения Хоара: два указателя с краёв"""
    pivot = arr[(lo + hi) // 2]  # медиана из трёх лучше
    i, j = lo - 1, hi + 1
    
    while True:
        i += 1
        while arr[i] < pivot:
            i += 1
        
        j -= 1
        while arr[j] > pivot:
            j -= 1
        
        if i >= j:
            return j
        
        arr[i], arr[j] = arr[j], arr[i]
```

### Худший случай и рандомизация

```python
# Худший случай quicksort: уже отсортированный массив!
import random

def quicksort_randomized(arr, lo=0, hi=None):
    """
    Рандомизированный quicksort: O(n log n) ожидаемое
    Выбираем random pivot → не бывает худшего случая на конкретных данных
    """
    if hi is None:
        hi = len(arr) - 1
    
    if lo >= hi:
        return
    
    # Случайный pivot → обменяем с последним элементом
    pivot_idx = random.randint(lo, hi)
    arr[pivot_idx], arr[hi] = arr[hi], arr[pivot_idx]
    
    p = partition_lomuto(arr, lo, hi)
    quicksort_randomized(arr, lo, p - 1)
    quicksort_randomized(arr, p + 1, hi)

# Медиана трёх: популярная детерминированная эвристика
def median_of_three(arr, lo, hi):
    mid = (lo + hi) // 2
    candidates = [(arr[lo], lo), (arr[mid], mid), (arr[hi], hi)]
    candidates.sort()
    return candidates[1][1]  # медиана
```

### 3-way partition (Dutch National Flag)

```python
def quicksort_3way(arr, lo=0, hi=None):
    """
    3-way partition для массивов с повторяющимися элементами.
    O(n log n) в среднем, O(n) для массива из одинаковых элементов!
    Используется в стандартных библиотеках Java/Rust.
    """
    if hi is None:
        hi = len(arr) - 1
    if lo >= hi:
        return
    
    # Dutch National Flag partition
    pivot = arr[lo]
    lt, gt = lo, hi
    i = lo + 1
    
    while i <= gt:
        if arr[i] < pivot:
            arr[lt], arr[i] = arr[i], arr[lt]
            lt += 1; i += 1
        elif arr[i] > pivot:
            arr[i], arr[gt] = arr[gt], arr[i]
            gt -= 1
            # i не увеличиваем: нужно проверить arr[gt]
        else:
            i += 1
    
    # arr[lo..lt-1] < pivot, arr[lt..gt] == pivot, arr[gt+1..hi] > pivot
    quicksort_3way(arr, lo, lt - 1)
    quicksort_3way(arr, gt + 1, hi)
```

## Mergesort: стабильная O(n log n)

Mergesort — разделяй и властвуй. **Стабильный** (сохраняет порядок равных элементов), O(n log n) гарантировано.

```python
def mergesort(arr):
    """
    Top-down mergesort.
    O(n log n) всегда, O(n) доп. памяти.
    Стабильный.
    """
    if len(arr) <= 1:
        return arr
    
    mid = len(arr) // 2
    left = mergesort(arr[:mid])
    right = mergesort(arr[mid:])
    
    return merge(left, right)

def merge(left, right):
    """Слияние двух отсортированных массивов"""
    result = []
    i = j = 0
    
    while i < len(left) and j < len(right):
        # <= обеспечивает стабильность: равные из left идут первыми
        if left[i] <= right[j]:
            result.append(left[i]); i += 1
        else:
            result.append(right[j]); j += 1
    
    result.extend(left[i:])
    result.extend(right[j:])
    return result

def mergesort_inplace(arr, buf, lo, hi):
    """In-place (через вспомогательный буфер) mergesort"""
    if hi - lo <= 1:
        return
    
    mid = (lo + hi) // 2
    mergesort_inplace(arr, buf, lo, mid)
    mergesort_inplace(arr, buf, mid, hi)
    
    # Слияние arr[lo:mid] и arr[mid:hi] в buf[lo:hi]
    buf[lo:hi] = sorted(arr[lo:mid] + arr[mid:hi])  # упрощённо
    arr[lo:hi] = buf[lo:hi]
```

### Внешняя сортировка через mergesort

Mergesort идеален для внешней сортировки (sorting data that doesn't fit in memory):

```python
import os
import tempfile
import heapq

def external_sort(input_file, output_file, memory_limit=1024):
    """
    Внешняя сортировка через merge-sort.
    memory_limit — количество записей в памяти одновременно.
    """
    # Фаза 1: Создаём отсортированные "runs"
    runs = []
    with open(input_file) as f:
        buffer = []
        for line in f:
            buffer.append(int(line.strip()))
            if len(buffer) >= memory_limit:
                buffer.sort()
                tmp = tempfile.NamedTemporaryFile(mode='w', delete=False)
                tmp.write('\n'.join(map(str, buffer)))
                runs.append(tmp.name)
                buffer = []
        if buffer:
            buffer.sort()
            tmp = tempfile.NamedTemporaryFile(mode='w', delete=False)
            tmp.write('\n'.join(map(str, buffer)))
            runs.append(tmp.name)
    
    # Фаза 2: K-way merge через min-heap
    handles = [open(r) for r in runs]
    heap = []
    
    for i, h in enumerate(handles):
        val = h.readline().strip()
        if val:
            heapq.heappush(heap, (int(val), i))
    
    with open(output_file, 'w') as out:
        while heap:
            val, i = heapq.heappop(heap)
            out.write(f"{val}\n")
            next_val = handles[i].readline().strip()
            if next_val:
                heapq.heappush(heap, (int(next_val), i))
    
    for h in handles: h.close()
    for r in runs: os.unlink(r)
```

## Heapsort: O(n log n) без доп. памяти

Heapsort комбинирует построение кучи O(n) с n извлечениями максимума O(log n):

```python
def heapsort(arr):
    """
    In-place, O(n log n) всегда, O(1) доп. памяти.
    Нестабильный.
    Плохая локальность кеша → медленнее quicksort/timsort на практике.
    """
    n = len(arr)
    
    # Построение max-heap: O(n)
    for i in range(n // 2 - 1, -1, -1):
        _sift_down(arr, i, n)
    
    # Извлечение: n раз O(log n)
    for i in range(n - 1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]  # максимум в конец
        _sift_down(arr, 0, i)

def _sift_down(arr, i, n):
    while True:
        largest = i
        l, r = 2*i+1, 2*i+2
        if l < n and arr[l] > arr[largest]: largest = l
        if r < n and arr[r] > arr[largest]: largest = r
        if largest == i: break
        arr[i], arr[largest] = arr[largest], arr[i]
        i = largest
```

## Introsort: quicksort + heapsort + insertion sort

Introsort (Musser, 1997) — гибрид, обеспечивающий лучшее от всех трёх:

```
Introsort:
1. Начинаем с quicksort
2. Если глубина рекурсии > 2*log₂(n) → переключаемся на heapsort
   (защита от O(n²) худшего случая quicksort)
3. Для малых подмассивов (≤ 16-32) → insertion sort
   (лучшая константа для небольших n)
```

```python
def introsort(arr):
    max_depth = 2 * len(arr).bit_length()
    _introsort(arr, 0, len(arr), max_depth)
    insertion_sort(arr, 0, len(arr))

def _introsort(arr, lo, hi, depth):
    if hi - lo <= 16:  # малые: отдадим insertion sort в конце
        return
    
    if depth == 0:
        heapsort_range(arr, lo, hi)  # деградация → heapsort
        return
    
    # Quicksort шаг
    pivot = median_of_three_pivot(arr, lo, hi-1)
    p = partition_lomuto_range(arr, lo, hi-1, pivot)
    _introsort(arr, lo, p, depth - 1)
    _introsort(arr, p + 1, hi, depth - 1)

def insertion_sort(arr, lo=0, hi=None):
    """O(n) для почти отсортированных, O(n²) в худшем"""
    if hi is None: hi = len(arr)
    for i in range(lo + 1, hi):
        key = arr[i]
        j = i - 1
        while j >= lo and arr[j] > key:
            arr[j+1] = arr[j]
            j -= 1
        arr[j+1] = key

# Introsort используется в:
# - C++ std::sort (GCC/Clang/MSVC)
# - Ранний Rust std sort
```

## Timsort: Python и Java

Timsort (Tim Peters, 2002) — алгоритм, специально оптимизированный для **реальных данных**, которые часто частично отсортированы.

### Идея Timsort

```
Реальные данные часто содержат "runs" — уже отсортированные подмассивы!
[1,2,3,4,   10,8,6,   15,20,25,   12,11,9,   ...]
 run1 (asc) run2(desc) run3(asc)  run4(desc)

Timsort:
1. Находит натуральные runs (отсортированные подмассивы)
2. Разворачивает убывающие runs
3. Если run слишком мал — расширяет insertion sort'ом (до MIN_RUN)
4. Сливает runs попарно, сохраняя инварианты

MIN_RUN ≈ 32-64 (так что insertion sort на каждом run)
```

```python
MIN_RUN = 32

def timsort(arr):
    """Упрощённый Timsort"""
    n = len(arr)
    
    # Шаг 1: Сортируем runs длиной MIN_RUN через insertion sort
    for i in range(0, n, MIN_RUN):
        insertion_sort(arr, i, min(i + MIN_RUN, n))
    
    # Шаг 2: Сливаем runs попарно
    size = MIN_RUN
    while size < n:
        for left in range(0, n, size * 2):
            mid = min(left + size, n)
            right = min(left + size * 2, n)
            if mid < right:
                # Слияние arr[left:mid] и arr[mid:right]
                merged = merge(arr[left:mid], arr[mid:right])
                arr[left:right] = merged
        size *= 2

# Python использует настоящий Timsort в list.sort() и sorted()
# Java Arrays.sort() для объектов — также Timsort с Java 8
```

### Почему Timsort быстрее для реальных данных

```python
import random
import time

def benchmark_sort(name, sort_fn, data):
    arr = data.copy()
    start = time.perf_counter()
    sort_fn(arr)
    elapsed = time.perf_counter() - start
    print(f"{name}: {elapsed*1000:.2f}ms")

n = 100000

# Случайные данные
random_data = [random.randint(0, n) for _ in range(n)]
# Python sorted() — Timsort
benchmark_sort("sorted() random", lambda a: a.sort(), random_data)

# Почти отсортированные данные (реальный сценарий: лог-файлы)
nearly_sorted = list(range(n))
for _ in range(n // 100):  # 1% нарушений
    i, j = random.randint(0, n-1), random.randint(0, n-1)
    nearly_sorted[i], nearly_sorted[j] = nearly_sorted[j], nearly_sorted[i]

benchmark_sort("sorted() nearly sorted", lambda a: a.sort(), nearly_sorted)
# Timsort распознаёт runs → очень быстро!
```

## pdqsort (Pattern-Defeating Quicksort): Rust и C++

pdqsort (Orson Peters, 2021) — современный стандарт в Rust и C++23.

Ключевые улучшения над introsort:
1. **Быстрое обнаружение паттернов:** Обнаруживает уже отсортированные данные, одинаковые элементы, reverse-отсортированные
2. **Block partition:** Быстрый partition с branch-free swap
3. **Median of medians** для pivot при деградации

```
pdqsort performance:
- Случайные данные: ≈ quicksort
- Почти отсортированные: ≈ timsort
- Одинаковые элементы: O(n)
- Reverse-sorted: O(n log n) (не O(n²)!)

Используется в:
- Rust std::sort() (unstable)
- C++ (предложение P0639)
- Swift stdlib (вариация)
```

## Сортировки за O(n): не сравнительные

### Counting Sort: O(n + k)

```python
def counting_sort(arr, max_val=None):
    """
    Counting sort: O(n + k), где k = max_val.
    Только для целых неотрицательных чисел.
    """
    if not arr:
        return []
    
    if max_val is None:
        max_val = max(arr)
    
    count = [0] * (max_val + 1)
    for x in arr:
        count[x] += 1
    
    result = []
    for val, cnt in enumerate(count):
        result.extend([val] * cnt)
    
    return result

print(counting_sort([4, 2, 2, 8, 3, 3, 1]))  # [1, 2, 2, 3, 3, 4, 8]
```

### Radix Sort: O(n * d)

```python
def radix_sort(arr):
    """
    Radix LSD (Least Significant Digit) Sort.
    O(d * (n + k)) где d — количество цифр, k — основание.
    Стабильный!
    """
    if not arr:
        return arr
    
    max_val = max(arr)
    exp = 1
    
    while max_val // exp > 0:
        arr = counting_sort_by_digit(arr, exp)
        exp *= 10
    
    return arr

def counting_sort_by_digit(arr, exp):
    """Стабильная сортировка по одной цифре"""
    n = len(arr)
    output = [0] * n
    count = [0] * 10
    
    for num in arr:
        digit = (num // exp) % 10
        count[digit] += 1
    
    # Кумулятивные суммы
    for i in range(1, 10):
        count[i] += count[i-1]
    
    # Строим output с конца (для стабильности)
    for i in range(n-1, -1, -1):
        digit = (arr[i] // exp) % 10
        count[digit] -= 1
        output[count[digit]] = arr[i]
    
    return output

print(radix_sort([170, 45, 75, 90, 802, 24, 2, 66]))
# [2, 24, 45, 66, 75, 90, 170, 802]

# Radix sort используется в:
# - Сортировка целых чисел в GPU
# - Linux kernel (некоторые внутренние структуры)
# - Сортировка строк с фиксированной длиной
```

### Bucket Sort: O(n)

```python
def bucket_sort(arr, num_buckets=10):
    """
    Bucket sort: O(n) для равномерного распределения.
    """
    if not arr:
        return arr
    
    min_val, max_val = min(arr), max(arr)
    bucket_range = (max_val - min_val) / num_buckets + 1e-9
    
    buckets = [[] for _ in range(num_buckets)]
    
    for x in arr:
        idx = int((x - min_val) / bucket_range)
        buckets[idx].append(x)
    
    result = []
    for bucket in buckets:
        result.extend(sorted(bucket))  # insertion sort для малых bucket
    
    return result
```

## Практический выбор алгоритма

```python
# Когда что использовать:

# 1. Обычная сортировка Python/Java/Rust:
#    ПРОСТО ИСПОЛЬЗУЙТЕ ВСТРОЕННЫЙ SORT!
arr = [5, 3, 1, 4, 2]
arr.sort()             # Python Timsort — стабильный
sorted_arr = sorted(arr)  # создаёт новый список

# 2. Целые числа в известном диапазоне:
# Counting sort / Radix sort → O(n)

# 3. Данные не помещаются в память:
# External mergesort

# 4. Много одинаковых элементов:
# 3-way quicksort / pdqsort

# 5. Нужна стабильность + гарантия O(n log n):
# Mergesort или Timsort (если язык не гарантирует)

# 6. Нужна O(1) доп. память + O(n log n) гарантия:
# Heapsort (но медленнее на практике из-за кеша)

print(sorted([3, 1, 4, 1, 5, 9, 2, 6], key=lambda x: -x))
# [9, 6, 5, 4, 3, 2, 1, 1] — по убыванию
```

## Итоги

| Алгоритм | Время (avg) | Время (worst) | Память | Стабильный | Применение |
|----------|------------|--------------|--------|-----------|-----------|
| Quicksort | O(n log n) | O(n²) | O(log n) | Нет | Универсальная |
| Mergesort | O(n log n) | O(n log n) | O(n) | Да | Стабильная, внешняя |
| Heapsort | O(n log n) | O(n log n) | O(1) | Нет | Гарантия без доп. памяти |
| Introsort | O(n log n) | O(n log n) | O(log n) | Нет | C++ std::sort |
| Timsort | O(n log n) | O(n log n) | O(n) | Да | Python, Java |
| pdqsort | O(n log n) | O(n log n) | O(log n) | Нет | Rust, C++23 |
| Radix sort | O(d·n) | O(d·n) | O(n+k) | Да | Целые числа |

## Литература

1. Hoare, C. A. R. (1962). Quicksort. *Computer Journal*, 5(1), 10–16. https://academic.oup.com/comjnl/article/5/1/10/395338

2. Knuth, D. E. (1998). *The Art of Computer Programming, Vol. 3: Sorting and Searching* (2nd ed.). Addison-Wesley. — фундаментальная монография

3. Peters, T. (2002). Timsort description. https://bugs.python.org/file4451/timsort.txt

4. Musser, D. R. (1997). Introspective Sorting and Selection Algorithms. *Software: Practice and Experience*, 27(8). https://onlinelibrary.wiley.com/doi/10.1002/(SICI)1097-024X(199708)27:8

5. Peters, O. (2021). Pattern-defeating quicksort. https://github.com/orlp/pdqsort

6. Sedgewick, R., & Bentley, J. L. (2002). Quicksort is optimal. https://sedgewick.io/wp-content/themes/sedgewick/talks/2002QuicksortIsOptimal.pdf

7. Java Arrays.sort documentation (Timsort). https://docs.oracle.com/en/java/docs/java/util/Arrays.html#sort(java.lang.Object[])

8. Rust `std::sort` documentation. https://doc.rust-lang.org/std/primitive.slice.html#method.sort

9. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Главы 7-9 — Sorting.

10. McIlroy, P. (1993). Optimistic sorting and information theoretic complexity. *SODA 1993*. https://dl.acm.org/doi/10.5555/313559.313768 — основа Timsort
