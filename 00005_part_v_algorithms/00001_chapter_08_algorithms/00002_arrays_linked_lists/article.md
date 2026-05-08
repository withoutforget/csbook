# Массивы и связные списки: базовые структуры хранения данных

Массив и связный список — это два фундаментальных способа организовать коллекцию данных. Казалось бы, оба хранят последовательности элементов. Но их физическая организация в памяти кардинально различается, и это определяет всё: скорость доступа, стоимость вставки, поведение процессорного кеша. Понимание этих структур — основа для всего, что строится поверх.

## Массив: непрерывная память

Массив — это последовательность элементов одного типа, расположенных в памяти **непрерывно**. Каждый элемент занимает одинаковое количество байт.

```
Массив int32 [10, 20, 30, 40, 50]:

Адрес: 0x100  0x104  0x108  0x10C  0x110
       ┌─────┬─────┬─────┬─────┬─────┐
Данные:│  10 │  20 │  30 │  40 │  50 │
       └─────┴─────┴─────┴─────┴─────┘
         [0]   [1]   [2]   [3]   [4]
```

### O(1) доступ: магия адресной арифметики

Адрес элемента с индексом i вычисляется за константное время:

```
address(arr[i]) = base_address + i * element_size
```

```c
// В C: прямое обращение к памяти
int arr[5] = {10, 20, 30, 40, 50};
int *p = arr;  // base_address

// arr[3] то же самое, что:
// *(p + 3) = *(адрес + 3 * sizeof(int))
printf("%d\n", arr[3]);   // 40
printf("%d\n", *(p + 3)); // 40 — идентично!

// Время доступа O(1) — одна операция умножения и сложения
```

```python
# В Python: list — это массив указателей (не сам тип данных!)
arr = [10, 20, 30, 40, 50]
print(arr[3])    # O(1) — доступ по индексу

# CPython list хранит указатели на объекты PyObject
# arr[i] → *(base + i * sizeof(pointer)) → объект Python
```

### Локальность кеша — главное преимущество массивов

Современные CPU имеют кеш (L1/L2/L3). При обращении к памяти загружается целая **кеш-линия** (64 байта на x86). Если массив с элементами по 8 байт — за одно обращение загружаются 8 элементов сразу!

```
Массив: [1][2][3][4][5][6][7][8][9]...
                    ↑
            CPU читает [5]
            Кеш загружает линию: [1..8] — 64 байта
            Следующие 7 обращений — из кеша!
```

```c
// Демонстрация: разница между последовательным и случайным доступом
#include <time.h>
#define N 10000000

int arr[N];

// Последовательный проход — кеш-дружественный
double sequential_sum() {
    long sum = 0;
    for (int i = 0; i < N; i++) sum += arr[i];  // кеш горячий
    return sum;
}

// Случайный доступ — кеш miss на каждом шаге
double random_access(int *indices) {
    long sum = 0;
    for (int i = 0; i < N; i++) sum += arr[indices[i]];  // кеш промах!
    return sum;
}

// Разница в скорости: 10-100x в пользу последовательного!
```

### Операции с массивом: время и место

| Операция | Время | Комментарий |
|----------|-------|-------------|
| Доступ по индексу | O(1) | Адресная арифметика |
| Поиск (неотсортированный) | O(n) | Линейный перебор |
| Поиск (отсортированный) | O(log n) | Бинарный поиск |
| Вставка в конец | O(1) амортизированно | Для динамического массива |
| Вставка в начало/середину | O(n) | Нужно сдвигать элементы |
| Удаление в конец | O(1) | |
| Удаление в начало/середину | O(n) | Нужно сдвигать элементы |

## Динамический массив: амортизированное добавление

Статический массив имеет фиксированный размер. Динамический массив (ArrayList в Java, vector в C++, list в Python) автоматически растёт.

### Стратегия удвоения

```python
class DynamicArray:
    def __init__(self):
        self._data = [None] * 1   # начальная ёмкость
        self._size = 0            # реальное количество элементов
        self._capacity = 1
    
    def append(self, value):
        if self._size == self._capacity:
            self._grow()          # выделяем новый массив
        self._data[self._size] = value
        self._size += 1
    
    def _grow(self):
        """Удваиваем ёмкость"""
        new_capacity = self._capacity * 2
        new_data = [None] * new_capacity
        for i in range(self._size):
            new_data[i] = self._data[i]  # копируем все элементы
        self._data = new_data
        self._capacity = new_capacity
        print(f"Выросли: capacity={new_capacity}")
    
    def __getitem__(self, index):
        if not 0 <= index < self._size:
            raise IndexError("Index out of range")
        return self._data[index]
    
    def __len__(self):
        return self._size

# Демонстрация
arr = DynamicArray()
for i in range(10):
    arr.append(i)
    print(f"  После добавления {i}: size={arr._size}, capacity={arr._capacity}")
# Выросли: capacity=2
# Выросли: capacity=4
# Выросли: capacity=8
# Выросли: capacity=16
```

### Амортизированный анализ O(1)

Почему добавление в конец — O(1) амортизированно, несмотря на периодические копирования?

```
Добавляем n элементов:
- Большинство добавлений: 1 операция
- Редкие расширения: 1+2+4+8+...+n/2+n = 2n операций суммарно

Всего: n + 2n = 3n операций для n добавлений
Среднее: 3 операции на добавление → O(1) амортизированно
```

```python
import sys

# Python list реально ведёт себя так:
import timeit

def time_append(n):
    arr = []
    for i in range(n):
        arr.append(i)

# append() — O(1) амортизированно
print(timeit.timeit(lambda: time_append(10000), number=100))
```

### CPython list internals

В CPython список — это массив указателей (PyObject**). Стратегия роста не "чистое удвоение", а нелинейная для экономии памяти у маленьких списков:

```c
// CPython listobject.c — стратегия роста:
// new_allocated = ((size_t)newsize + (newsize >> 3) + (newsize < 9 ? 3 : 6));
// Для малых: 0→4→8→16→25→35→46→...
// Для больших: примерно +12.5% каждый раз
```

## Связный список: O(1) вставка, O(n) доступ

Связный список хранит элементы в узлах (nodes), рассыпанных по памяти. Каждый узел содержит данные и указатель(и) на соседей.

```
Однонаправленный список [10→20→30→40→None]:

┌─────────┐    ┌─────────┐    ┌─────────┐
│ data:10 │    │ data:20 │    │ data:30 │
│ next: ──┼──> │ next: ──┼──> │ next:None│
└─────────┘    └─────────┘    └─────────┘
     ↑
    head
```

```python
from typing import Optional, TypeVar, Generic

T = TypeVar('T')

class Node(Generic[T]):
    def __init__(self, data: T):
        self.data: T = data
        self.next: Optional['Node[T]'] = None

class LinkedList(Generic[T]):
    def __init__(self):
        self.head: Optional[Node[T]] = None
        self._size = 0
    
    def prepend(self, value: T) -> None:
        """O(1): вставить в начало"""
        new_node = Node(value)
        new_node.next = self.head
        self.head = new_node
        self._size += 1
    
    def append(self, value: T) -> None:
        """O(n): вставить в конец (без tail pointer)"""
        new_node = Node(value)
        if self.head is None:
            self.head = new_node
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_node
        self._size += 1
    
    def remove_head(self) -> Optional[T]:
        """O(1): удалить с начала"""
        if self.head is None:
            return None
        value = self.head.data
        self.head = self.head.next
        self._size -= 1
        return value
    
    def get(self, index: int) -> T:
        """O(n): доступ по индексу"""
        current = self.head
        for _ in range(index):
            if current is None:
                raise IndexError("Index out of range")
            current = current.next
        if current is None:
            raise IndexError("Index out of range")
        return current.data
    
    def __len__(self):
        return self._size
    
    def __iter__(self):
        current = self.head
        while current:
            yield current.data
            current = current.next

# Тест
ll = LinkedList()
for val in [1, 2, 3, 4, 5]:
    ll.append(val)
print(list(ll))   # [1, 2, 3, 4, 5]
print(ll.get(2))  # 3 — O(n)!
```

### O(1) вставка/удаление в середину — правда и ложь

Часто говорят, что у связного списка O(1) вставка/удаление. Это **правда**, но с оговоркой: **если у вас есть указатель на нужный узел**.

```python
def insert_after(node: Node, value) -> Node:
    """O(1): вставить ПОСЛЕ известного узла"""
    new_node = Node(value)
    new_node.next = node.next
    node.next = new_node
    return new_node

def remove_after(node: Node) -> None:
    """O(1): удалить узел ПОСЛЕ известного узла"""
    if node.next:
        node.next = node.next.next

# Но нахождение нужного узла — O(n)!
# Итого: "вставить третий элемент" = O(n) найти + O(1) вставить = O(n)
```

## Двусвязный список

Двусвязный список добавляет указатель `prev`:

```python
class DNode:
    def __init__(self, data):
        self.data = data
        self.next = None
        self.prev = None

class DoublyLinkedList:
    def __init__(self):
        self.head = None
        self.tail = None  # tail pointer для O(1) append/pop
    
    def append(self, value):
        """O(1)"""
        node = DNode(value)
        if self.tail is None:
            self.head = self.tail = node
        else:
            node.prev = self.tail
            self.tail.next = node
            self.tail = node
    
    def pop(self):
        """O(1): удалить с конца"""
        if self.tail is None:
            return None
        value = self.tail.data
        if self.tail.prev:
            self.tail = self.tail.prev
            self.tail.next = None
        else:
            self.head = self.tail = None
        return value
    
    def remove_node(self, node: DNode):
        """O(1): удалить конкретный узел (имея на него указатель)"""
        if node.prev:
            node.prev.next = node.next
        else:
            self.head = node.next
        
        if node.next:
            node.next.prev = node.prev
        else:
            self.tail = node.prev
```

Двусвязный список используется в:
- `collections.deque` в Python
- LRU Cache (добавить к хвосту, удалить с головы или произвольный)
- Браузерная история (назад/вперёд)

## XOR-список: экзотическая оптимизация памяти

XOR-список — трюк для хранения двусвязного списка с одним полем вместо двух:

```python
# Каждый узел хранит XOR предыдущего и следующего адресов
# prev XOR next

# Для обхода вперёд: next = addr(prev) XOR xor_link
# Для обхода назад:  prev = addr(next) XOR xor_link

# Это использует свойство XOR: A XOR B XOR A = B
```

На практике не используется из-за проблем с GC (garbage collector не видит ссылки). Но интересен концептуально.

## Skip List: O(log n) в связном списке

Skip list — вероятностная структура данных, обеспечивающая O(log n) поиск в связном списке.

```
Уровень 3: head ─────────────────────────────────────> 50 → None
Уровень 2: head ──────────> 20 ──────────────────────> 50 → None
Уровень 1: head ─> 10 ─────> 20 ──────> 30 ─────────> 50 → None
Уровень 0: head ─> 10 ─> 15 ─> 20 ─> 25 ─> 30 ─> 40 ─> 50 → None
```

```python
import random

class SkipNode:
    def __init__(self, key, value, level):
        self.key = key
        self.value = value
        self.forward = [None] * (level + 1)

class SkipList:
    MAX_LEVEL = 16
    P = 0.5
    
    def __init__(self):
        self.header = SkipNode(float('-inf'), None, self.MAX_LEVEL)
        self.level = 0
    
    def _random_level(self):
        level = 0
        while random.random() < self.P and level < self.MAX_LEVEL:
            level += 1
        return level
    
    def search(self, key):
        """O(log n) в среднем"""
        current = self.header
        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
        current = current.forward[0]
        if current and current.key == key:
            return current.value
        return None
    
    def insert(self, key, value):
        """O(log n) в среднем"""
        update = [None] * (self.MAX_LEVEL + 1)
        current = self.header
        
        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current
        
        current = current.forward[0]
        
        if current and current.key == key:
            current.value = value
        else:
            new_level = self._random_level()
            if new_level > self.level:
                for i in range(self.level + 1, new_level + 1):
                    update[i] = self.header
                self.level = new_level
            
            new_node = SkipNode(key, value, new_level)
            for i in range(new_level + 1):
                new_node.forward[i] = update[i].forward[i]
                update[i].forward[i] = new_node

# Skip list используется в: Redis Sorted Sets, LevelDB
sl = SkipList()
for k in [3, 6, 7, 9, 12, 19, 21, 25]:
    sl.insert(k, f"val_{k}")
print(sl.search(12))  # val_12
```

## Кольцевой буфер (Ring Buffer / Circular Buffer)

Кольцевой буфер — массив, используемый как очередь FIFO с wrap-around:

```python
class RingBuffer:
    """
    Массив фиксированного размера, используемый как очередь.
    Голова и хвост "бегут по кругу".
    """
    def __init__(self, capacity: int):
        self.buffer = [None] * capacity
        self.capacity = capacity
        self.head = 0  # следующая позиция для чтения
        self.tail = 0  # следующая позиция для записи
        self.size = 0
    
    def enqueue(self, item) -> bool:
        """O(1)"""
        if self.size == self.capacity:
            return False  # буфер заполнен
        self.buffer[self.tail] = item
        self.tail = (self.tail + 1) % self.capacity  # wrap-around!
        self.size += 1
        return True
    
    def dequeue(self):
        """O(1)"""
        if self.size == 0:
            return None
        item = self.buffer[self.head]
        self.head = (self.head + 1) % self.capacity  # wrap-around!
        self.size -= 1
        return item

# Пример: логирование последних N событий
log_buffer = RingBuffer(5)
for i in range(8):
    if not log_buffer.enqueue(f"event_{i}"):
        print(f"Буфер полон, event_{i} потеряно")
    print(f"  Буфер: head={log_buffer.head}, tail={log_buffer.tail}")
```

Кольцевой буфер используется в:
- Сетевые буферы (ядро Linux)
- Аудио буферы
- Логирование с ограниченным размером (`collections.deque(maxlen=N)`)
- Lock-free очереди (single producer/consumer)

## Сравнение производительности: массив vs список

```python
import time
import sys

def benchmark():
    n = 100000
    
    # 1. Последовательный доступ
    arr = list(range(n))
    
    start = time.perf_counter()
    total = sum(arr[i] for i in range(n))  # последовательно
    print(f"Array sequential: {(time.perf_counter()-start)*1000:.2f}ms")
    
    # 2. Случайный доступ — массив быстрее
    import random
    indices = list(range(n))
    random.shuffle(indices)
    
    start = time.perf_counter()
    total = sum(arr[i] for i in indices)
    arr_time = time.perf_counter() - start
    
    # 3. Вставка в начало — список быстрее
    # Python list.insert(0, x) — O(n): все элементы сдвигаются!
    from collections import deque
    
    arr = []
    start = time.perf_counter()
    for i in range(10000):
        arr.insert(0, i)  # O(n) каждый раз!
    arr_insert_time = time.perf_counter() - start
    
    # deque: O(1) вставка с обоих концов
    d = deque()
    start = time.perf_counter()
    for i in range(10000):
        d.appendleft(i)   # O(1)!
    deque_insert_time = time.perf_counter() - start
    
    print(f"list.insert(0, x) x10000: {arr_insert_time*1000:.2f}ms")
    print(f"deque.appendleft x10000:  {deque_insert_time*1000:.2f}ms")

benchmark()
```

### Реальные benchmark: локальность кеша

```c
// C: сравнение array vs linked list traversal
// На типичном процессоре с кешем L1 32KB:

// Array traversal (1M integers):
// ~ 2ms — почти всё из кеша!

// Linked list traversal (1M узлов):
// ~ 20-50ms — каждый узел — потенциальный cache miss!

// Разница: 10-25x в пользу массива даже при одинаковой Big-O!
```

### Когда использовать что

```
Массив/dynamic array (list в Python, ArrayList/Vec):
✓ Частый случайный доступ по индексу
✓ Итерация по всем элементам
✓ Компактное хранение
✓ Бинарный поиск (для отсортированных)
✗ Частая вставка/удаление в середину

Связный список:
✓ O(1) вставка/удаление с концов (с tail pointer)
✓ LRU Cache (быстрое удаление любого узла с известным указателем)
✓ Реализация очередей и дек
✗ Случайный доступ по индексу
✗ Бинарный поиск невозможен

deque (двусвязный на массивах в Python):
✓ O(1) с обоих концов
✓ Кеш-дружественнее чистого связного списка
Используется для BFS, sliding window
```

## Итоги

Массивы и связные списки — два полюса:

- **Массивы:** непрерывная память, O(1) произвольный доступ, кеш-дружественные, O(n) вставка в середину
- **Связные списки:** рассыпанная память, O(1) вставка/удаление (при наличии указателя), O(n) доступ, плохая локальность кеша

На практике **массивы побеждают чаще**, чем ожидается из теоретической сложности — из-за кеша. Связные списки применяются там, где нужно O(1) вставка/удаление по известному указателю: LRU кеш, реализации дек, интрузивные структуры данных.

## Литература

1. Knuth, D. E. (1997). *The Art of Computer Programming, Vol. 1: Fundamental Algorithms* (3rd ed.). Addison-Wesley. Глава 2 — Information Structures (массивы, списки).

2. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Глава 10 — Elementary Data Structures.

3. Drepper, U. (2007). *What Every Programmer Should Know About Memory*. Red Hat. https://people.freedesktop.org/~ajax/nm/cpumemory.pdf — кеш и его влияние на производительность

4. CPython `listobject.c` — реализация Python list. https://github.com/python/cpython/blob/main/Objects/listobject.c

5. Pugh, W. (1990). Skip lists: a probabilistic alternative to balanced trees. *Communications of the ACM*, 33(6), 668–676. https://dl.acm.org/doi/10.1145/78973.78977

6. Sedgewick, R., & Wayne, K. (2011). *Algorithms* (4th ed.). Addison-Wesley. Глава 1.3 — Bags, Queues, and Stacks.

7. Bently, J. L. (2000). *Programming Pearls* (2nd ed.). ACM Press. — практические советы по массивам и производительности

8. Herlihy, M., & Shavit, N. (2012). *The Art of Multiprocessor Programming*. Elsevier. Глава 3 — Concurrent Objects (lock-free кольцевые буферы).

9. Python `collections.deque` documentation. https://docs.python.org/3/library/collections.html#collections.deque

10. Stroustrup, B. (2012). Software Development for Infrastructure. *Computer*, 45(1), 47–58. https://ieeexplore.ieee.org/document/6117416 — сравнение vector vs list на практике
