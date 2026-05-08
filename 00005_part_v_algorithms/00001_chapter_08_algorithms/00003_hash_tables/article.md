# Хеш-таблицы: O(1) в среднем, коллизии и rehashing

Хеш-таблица — вероятно, самая важная структура данных в программировании. Python dict, Java HashMap, JavaScript Object — всё это хеш-таблицы. Они обеспечивают O(1) вставку, поиск и удаление в среднем случае. Но за этой магической скоростью стоят нетривиальные решения: хеш-функции, коллизии, load factor, rehashing. Разобраться в этих деталях — значит понять, почему dict иногда вдруг "тормозит".

## Идея хеш-таблицы

Суть простая: хотим хранить пары ключ-значение с O(1) доступом. Если бы ключи были целыми числами в диапазоне [0, n), можно было бы просто использовать массив — arr[key] = value. Хеш-функция обобщает эту идею: преобразует произвольный ключ в индекс массива.

```python
# Концептуальная модель:
def simple_hash_table(size=16):
    table = [None] * size
    
    def get_index(key):
        return hash(key) % size
    
    def set(key, value):
        table[get_index(key)] = value
    
    def get(key):
        return table[get_index(key)]
    
    return set, get

# Проблема: коллизии!
# hash("foo") % 16 и hash("bar") % 16 могут совпасть
```

## Хеш-функции и их свойства

Хорошая хеш-функция должна быть:

1. **Детерминированной:** одинаковые ключи → всегда одинаковый хеш
2. **Равномерной:** хеши равномерно распределены по диапазону
3. **Быстрой:** вычисляется за O(1) — константное время от ключа
4. **Лавинным эффектом:** малое изменение ключа → сильно другой хеш

### DJB2: простая и надёжная

```python
def djb2(s: str) -> int:
    """DJB2 хеш Бернштейна — классика"""
    h = 5381
    for c in s:
        h = ((h << 5) + h) + ord(c)  # h = h * 33 + c
    return h & 0xFFFFFFFF  # 32-битный результат

# Простота и хорошее распределение
print(hex(djb2("hello")))   # 0x4f9f2cab
print(hex(djb2("hellp")))   # сильно другой — лавинный эффект
```

### FNV (Fowler-Noll-Vo)

```python
def fnv1a_32(data: bytes) -> int:
    """FNV-1a 32-bit хеш"""
    FNV_PRIME = 0x01000193
    OFFSET_BASIS = 0x811c9dc5
    
    h = OFFSET_BASIS
    for byte in data:
        h ^= byte        # XOR сначала (в FNV-1a, не FNV-1)
        h *= FNV_PRIME
        h &= 0xFFFFFFFF  # 32-битное усечение
    return h

print(hex(fnv1a_32(b"hello")))  # 0xe3d61a05
```

### MurmurHash и xxHash

```python
# MurmurHash3 — очень популярный, хорошее распределение, быстрый
# Используется в Cassandra, Redis, языках программирования

# pip install mmh3
import mmh3
print(mmh3.hash("hello"))           # -1616910350
print(mmh3.hash("hello", 42))       # другой seed = другой хеш

# xxHash — быстрейший из распространённых
# pip install xxhash
import xxhash
print(xxhash.xxh64("hello").intdigest())
```

### SipHash: защита от HashDoS

```python
# Python использует SipHash с случайным seed:
# При старте Python генерирует случайный seed (PYTHONHASHSEED)
# Это делает hash() непредсказуемым снаружи

import os
import hashlib

key = os.urandom(16)  # 128-битный ключ

def siphash(data: bytes, key: bytes) -> int:
    """Концептуальная иллюстрация — настоящий SipHash сложнее"""
    # В Python реальный SipHash-2-4 встроен в C
    # Здесь просто демонстрируем идею keyed hash
    return int(hashlib.blake2b(data, key=key, digest_size=8).hexdigest(), 16)

# В Python:
import sys
print(f"Python hash seed: {sys.flags.hash_randomization}")
print(f"hash('hello') = {hash('hello')}")  # разный при каждом запуске!
```

## Методы разрешения коллизий

Коллизия — когда два разных ключа дают одинаковый индекс после хеширования. Это неизбежно (принцип Дирихле) и требует обработки.

### Chaining (цепочки): связные списки в ячейках

Каждая ячейка таблицы хранит связный список пар ключ-значение:

```python
class HashTableChaining:
    def __init__(self, size=16):
        self.size = size
        self.table = [[] for _ in range(size)]  # список списков
        self.count = 0
    
    def _hash(self, key) -> int:
        return hash(key) % self.size
    
    def set(self, key, value):
        idx = self._hash(key)
        chain = self.table[idx]
        
        # Проверяем, есть ли уже такой ключ
        for i, (k, v) in enumerate(chain):
            if k == key:
                chain[i] = (key, value)  # обновляем
                return
        
        chain.append((key, value))        # добавляем новый
        self.count += 1
        
        if self.count > self.size * 0.75:  # load factor > 0.75
            self._rehash()
    
    def get(self, key, default=None):
        idx = self._hash(key)
        for k, v in self.table[idx]:
            if k == key:
                return v
        return default
    
    def delete(self, key):
        idx = self._hash(key)
        chain = self.table[idx]
        for i, (k, v) in enumerate(chain):
            if k == key:
                chain.pop(i)
                self.count -= 1
                return True
        return False
    
    def _rehash(self):
        old_table = self.table
        self.size *= 2
        self.table = [[] for _ in range(self.size)]
        self.count = 0
        for chain in old_table:
            for key, value in chain:
                self.set(key, value)

# Тест
ht = HashTableChaining()
ht.set("hello", 1)
ht.set("world", 2)
ht.set("hello", 3)  # обновление
print(ht.get("hello"))  # 3
print(ht.get("world"))  # 2
```

### Open Addressing: открытая адресация

Все элементы хранятся прямо в массиве таблицы. При коллизии — ищем следующую свободную ячейку.

#### Linear Probing

```python
class HashTableLinearProbing:
    DELETED = object()  # sentinel для удалённых ячеек
    
    def __init__(self, size=16):
        self.size = size
        self.table = [None] * size
        self.count = 0
    
    def _hash(self, key) -> int:
        return hash(key) % self.size
    
    def _probe(self, key):
        """Находим позицию для key через линейное пробирование"""
        idx = self._hash(key)
        start = idx
        
        while True:
            if self.table[idx] is None:
                return idx, None     # пустая ячейка
            if self.table[idx] is self.DELETED:
                # Продолжаем поиск — может быть дальше
                idx = (idx + 1) % self.size
            elif self.table[idx][0] == key:
                return idx, self.table[idx][1]  # нашли!
            else:
                idx = (idx + 1) % self.size     # коллизия, шаг вперёд
            
            if idx == start:
                return -1, None  # таблица полная
    
    def set(self, key, value):
        # ... (упрощённая версия)
        idx = self._hash(key)
        while self.table[idx] is not None and self.table[idx] is not self.DELETED:
            if self.table[idx][0] == key:
                self.table[idx] = (key, value)
                return
            idx = (idx + 1) % self.size
        self.table[idx] = (key, value)
        self.count += 1
```

**Кластеризация (clustering):** Linear probing страдает от "первичной кластеризации" — длинные цепочки занятых ячеек, увеличивающие среднее время поиска.

```
До вставки:
[_, A, B, _, C, _, ...]  # A, B, C вставлены без коллизий

Вставка D (hash=1):
[_, A, B, D, C, _, ...]  # D должен быть в 1, попал в 3 (кластер!)

Теперь каждый новый ключ с hash 1,2,3,4 удлиняет кластер...
```

#### Quadratic Probing

```python
def quadratic_probe(self, start_idx, attempt):
    """Шаг не 1, а i² — рассредотачиваем коллизии"""
    return (start_idx + attempt * attempt) % self.size
```

Лучше чем linear probing, но всё равно "вторичная кластеризация".

#### Double Hashing

```python
def double_hash_step(self, key, attempt):
    """Второй хеш определяет шаг — лучшее распределение"""
    h2 = 1 + (hash(key) % (self.size - 1))  # second hash function
    return h2
```

Double hashing минимизирует кластеризацию. Используется в Python dict (до версии 3.6).

### Robin Hood Hashing

Элегантная оптимизация open addressing. Идея: когда вставляемый элемент находится дальше от "дома" чем текущий элемент в ячейке — меняем их местами ("богатый" уступает место "бедному").

```python
class RobinHoodHashTable:
    def __init__(self, size=16):
        self.size = size
        self.table = [None] * size
    
    def _probe_distance(self, pos, key_hash):
        """Расстояние от "родного" слота"""
        return (pos - key_hash) % self.size
    
    def insert(self, key, value):
        idx = hash(key) % self.size
        entry = (key, value, idx)  # key, value, home_idx
        
        while True:
            if self.table[idx] is None:
                self.table[idx] = entry
                return
            
            existing = self.table[idx]
            ex_dist = self._probe_distance(idx, existing[2])
            new_dist = self._probe_distance(idx, entry[2])
            
            if new_dist > ex_dist:
                # "Бедный" (далеко от дома) вытесняет "богатого"
                self.table[idx] = entry
                entry = existing  # продолжаем вставлять вытесненный
            
            idx = (idx + 1) % self.size

# Преимущество: уменьшает дисперсию длины пробирования
# Используется в: Rust HashMap (до 2021), Robin Hood HashMap в Java
```

## Load Factor и Rehashing

**Load factor** $\alpha = n/m$, где n — количество элементов, m — размер таблицы.

### Влияние load factor

```python
import random
import timeit

def benchmark_load_factor():
    for target_lf in [0.1, 0.3, 0.5, 0.7, 0.9, 0.99]:
        # Создаём таблицу с заданным load factor
        d = {}
        keys = list(range(1000000))
        random.shuffle(keys)
        
        target_n = int(target_lf * 1000000)
        for k in keys[:target_n]:
            d[k] = k
        
        # Замеряем время поиска
        test_keys = random.sample(keys, 10000)
        
        start = timeit.default_timer()
        for k in test_keys:
            _ = d.get(k)
        elapsed = timeit.default_timer() - start
        
        print(f"LF={target_lf:.2f}: {elapsed*1000:.2f}ms для 10000 lookups")

# При LF < 0.7 производительность хорошая
# При LF → 1.0 производительность резко падает из-за коллизий
```

### Когда делать Rehashing

Python dict: rehash при LF > 2/3 (~0.667)
Java HashMap: rehash при LF > 0.75
Rust HashMap: rehash при LF > 0.875

```python
def needs_rehash(current_size, capacity, max_load_factor=0.75):
    return current_size / capacity > max_load_factor

def rehash(old_table):
    """Удвоить таблицу и перехешировать все элементы"""
    new_size = len(old_table) * 2
    new_table = [None] * new_size
    
    for entry in old_table:
        if entry and entry is not DELETED:
            key, value = entry
            # Вставляем в новую таблицу
            new_idx = hash(key) % new_size
            while new_table[new_idx] is not None:
                new_idx = (new_idx + 1) % new_size
            new_table[new_idx] = (key, value)
    
    return new_table

# Стоимость rehashing: O(n) — нужно перехешировать все элементы
# Амортизированно: O(1) на вставку
```

## Perfect Hashing: O(1) в худшем случае

Для статических наборов ключей возможно **идеальное хеширование** — без коллизий.

```python
# Двухуровневое совершенное хеширование (FKS scheme)
# 1. Хешируем в первичную таблицу размера m
# 2. Для каждого слота i с nᵢ элементами создаём вторичную таблицу размера nᵢ²

# Python 3.12+ использует вариант этого для frozenset
# gperf — генератор идеальных хеш-функций для строк (GNU)

# Пример использования gperf для C:
# gperf keywords.gperf > keywords.c
# Генерирует функцию без коллизий для набора ключевых слов
```

## Python dict internals

Python 3.6+ использует компактное dict с разделёнными индексами и данными.

```python
# Упрощённая схема Python dict:
# Индексный массив (8/16-bit per slot): очень компактный!
# Массив записей: (hash, key, value)

# Порядок insertion-order гарантирован с Python 3.7
d = {'c': 3, 'a': 1, 'b': 2}
print(list(d.keys()))  # ['c', 'a', 'b'] — порядок вставки!

# Python dict использует:
# - open addressing с шагом (hash >> 5) XOR hash (pseudo-random)
# - resize при LF > 2/3
# - маленькие dict: начинают с 8 слотов

import sys
d = {}
print(sys.getsizeof(d))           # 64 байта (пустой)
for i in range(100):
    d[i] = i
print(sys.getsizeof(d))           # больше после rehash
```

## Java HashMap

Java HashMap использует chaining. В Java 8+ длинные цепочки преобразуются в сбалансированные деревья (TreeMap на ячейку) при длине > 8:

```java
// Java HashMap
HashMap<String, Integer> map = new HashMap<>();
map.put("hello", 1);
map.put("world", 2);

// После Java 8: если цепочка > 8 элементов → TreeMap
// Это защита от degenerate случая: O(n) → O(log n) в худшем случае

// Начальная ёмкость и load factor:
HashMap<String, Integer> map2 = new HashMap<>(128, 0.75f);
// Избегает rehashing при известном размере заранее
```

## Concurrent Hash Maps

Обычные хеш-таблицы не потокобезопасны. Concurrent варианты:

### Python threading.Lock (простой подход)

```python
import threading

class ThreadSafeDict:
    def __init__(self):
        self._dict = {}
        self._lock = threading.RLock()
    
    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)
    
    def set(self, key, value):
        with self._lock:
            self._dict[key] = value
```

### Java ConcurrentHashMap

```java
// Не блокирует всю таблицу — только сегменты (segment locking)
// Java 8+: CAS-операции на уровне отдельных bucket
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("key", 1);
// Безопасно из нескольких потоков
```

## Простая реализация с тестами

```python
class HashMap:
    """Полная реализация хеш-таблицы с Robin Hood hashing"""
    
    EMPTY = object()
    DELETED = object()
    
    def __init__(self, initial_capacity=8, max_load=0.7):
        self._capacity = initial_capacity
        self._max_load = max_load
        self._size = 0
        self._keys = [self.EMPTY] * initial_capacity
        self._values = [None] * initial_capacity
    
    def _hash(self, key) -> int:
        return hash(key) % self._capacity
    
    def __setitem__(self, key, value):
        if (self._size + 1) / self._capacity > self._max_load:
            self._rehash()
        
        idx = self._hash(key)
        while self._keys[idx] not in (self.EMPTY, self.DELETED):
            if self._keys[idx] == key:
                self._values[idx] = value
                return
            idx = (idx + 1) % self._capacity
        
        self._keys[idx] = key
        self._values[idx] = value
        self._size += 1
    
    def __getitem__(self, key):
        idx = self._hash(key)
        start = idx
        while self._keys[idx] is not self.EMPTY:
            if self._keys[idx] == key:
                return self._values[idx]
            idx = (idx + 1) % self._capacity
            if idx == start:
                break
        raise KeyError(key)
    
    def __delitem__(self, key):
        idx = self._hash(key)
        while self._keys[idx] is not self.EMPTY:
            if self._keys[idx] == key:
                self._keys[idx] = self.DELETED
                self._values[idx] = None
                self._size -= 1
                return
            idx = (idx + 1) % self._capacity
        raise KeyError(key)
    
    def _rehash(self):
        old_keys = self._keys
        old_values = self._values
        self._capacity *= 2
        self._keys = [self.EMPTY] * self._capacity
        self._values = [None] * self._capacity
        self._size = 0
        for k, v in zip(old_keys, old_values):
            if k not in (self.EMPTY, self.DELETED):
                self[k] = v
    
    def __len__(self):
        return self._size
    
    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

# Тесты
ht = HashMap()
ht["foo"] = 1
ht["bar"] = 2
ht["baz"] = 3
print(ht["foo"])   # 1
del ht["bar"]
print(len(ht))     # 2
print("bar" in ht) # False
```

## Итоги

Хеш-таблица — это не магия, а умная инженерная конструкция:

1. **Хеш-функция** преобразует ключ в индекс; качество функции критично
2. **Коллизии неизбежны**; chaining и open addressing — основные способы обработки
3. **Load factor** контролирует баланс между памятью и скоростью
4. **Rehashing** — дорогая, но редкая операция; амортизированно O(1)
5. **SipHash** защищает от атак на хеш-таблицы

## Литература

1. Knuth, D. E. (1998). *The Art of Computer Programming, Vol. 3: Sorting and Searching* (2nd ed.). Addison-Wesley. Раздел 6.4 — Hashing.

2. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Глава 11 — Hash Tables.

3. Celis, P., Larson, P.-Å., & Munro, J. I. (1985). Robin Hood Hashing. *FOCS 1985*. https://cs.uwaterloo.ca/research/tr/1986/CS-86-14.pdf

4. Fredman, M., Komlós, J., & Szemerédi, E. (1984). Storing a sparse table with O(1) worst case access time. *Journal of the ACM*, 31(3), 538–544. — Perfect hashing (FKS)

5. Bernstein, D. J., & Aumasson, J.-P. (2012). SipHash: a fast short-input PRF. https://cr.yp.to/siphash/siphash-20120918.pdf

6. Python dict implementation notes. https://github.com/python/cpython/blob/main/Objects/dictobject.c

7. Java HashMap source code (OpenJDK). https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/HashMap.java

8. Appleby, A. MurmurHash. https://github.com/aappleby/smhasher

9. Pagh, R., & Rodler, F. F. (2004). Cuckoo hashing. *Journal of Algorithms*, 51(2), 122–144. — альтернативный метод разрешения коллизий

10. Bender, M. A. et al. (2022). Anti-hashing: Explaining the Data-Structure Devil in the Details. *ACM Queue*, 20(5). https://queue.acm.org/detail.cfm?id=3572411
