# Bloom filter, HyperLogLog, Count-Min Sketch: вероятностные структуры данных

Когда данных очень много — миллиарды URL, терабайты логов, сотни миллионов пользователей — точные структуры данных просто не помещаются в память. Вероятностные структуры данных решают эту проблему изящно: они жертвуют точностью в обмен на колоссальную экономию памяти. Bloom filter скажет "возможно есть" или "точно нет". HyperLogLog оценит количество уникальных элементов с погрешностью 1-2% используя 12 КБ вместо гигабайт. Count-Min Sketch приблизительно подсчитает частоты элементов. Эти структуры используются в Cassandra, Redis, Kafka, Chrome, Bigtable.

## Зачем нужны вероятностные структуры

```python
# Проблема: подсчёт уникальных IP за день
# 1 миллиард запросов, IP адреса

# Точное решение: set или HashSet
import sys
visited_ips = set()
# IP в виде 4 байт = 4 байта на IP
# 300 миллионов уникальных IP × 4 байта ≈ 1.2 GB только данные
# Плюс overhead хеш-таблицы × 3 ≈ 3.6 GB

# HyperLogLog решение:
# 12 KB памяти, точность 1.04 / sqrt(m) ≈ 0.81%
# 3 600 000 000 байт vs 12 288 байт = в 293 000 раз меньше!
```

## Bloom Filter: "возможно есть" или "точно нет"

Bloom filter — вероятностная структура данных для проверки принадлежности множеству. Может давать **false positives** (сказать "есть", когда нет), но никогда не даёт **false negatives** (никогда не скажет "нет", когда элемент есть).

### Структура

Bloom filter — битовый массив размером m битов и k хеш-функций.

```
Вставка "hello":
h1("hello") = 2 → устанавливаем бит 2
h2("hello") = 5 → устанавливаем бит 5
h3("hello") = 8 → устанавливаем бит 8

Проверка "hello":
h1("hello") = 2 → бит 2 = 1 ✓
h2("hello") = 5 → бит 5 = 1 ✓
h3("hello") = 8 → бит 8 = 1 ✓
→ "Возможно есть" ✓ (правильно!)

Проверка "world" (не вставляли):
h1("world") = 3 → бит 3 = 0
→ "Точно нет" ✓ (правильно)

Проверка "rust" (не вставляли, но случайно биты = 1):
h1("rust") = 2 → бит 2 = 1
h2("rust") = 5 → бит 5 = 1
h3("rust") = 8 → бит 8 = 1
→ "Возможно есть" ← False Positive! (ошибка)
```

### Реализация Bloom Filter

```python
import math
import mmh3  # MurmurHash3: pip install mmh3
from bitarray import bitarray  # pip install bitarray

class BloomFilter:
    def __init__(self, capacity: int, false_positive_rate: float = 0.01):
        """
        capacity: ожидаемое количество элементов
        false_positive_rate: допустимый уровень ложных срабатываний
        """
        # Оптимальный размер битового массива:
        # m = -n * ln(p) / (ln(2))²
        self.m = math.ceil(
            -capacity * math.log(false_positive_rate) / (math.log(2) ** 2)
        )
        
        # Оптимальное количество хеш-функций:
        # k = (m/n) * ln(2)
        self.k = math.ceil((self.m / capacity) * math.log(2))
        
        self.bits = bitarray(self.m)
        self.bits.setall(0)
        
        self._count = 0
        
        print(f"Bloom Filter: m={self.m} бит ({self.m/8/1024:.1f} KB), k={self.k} хешей")
    
    def add(self, item: str) -> None:
        """O(k) — добавить элемент"""
        for seed in range(self.k):
            idx = mmh3.hash(item, seed) % self.m
            self.bits[idx] = 1
        self._count += 1
    
    def __contains__(self, item: str) -> bool:
        """
        O(k) — проверить принадлежность.
        False = точно нет. True = возможно есть.
        """
        for seed in range(self.k):
            idx = mmh3.hash(item, seed) % self.m
            if not self.bits[idx]:
                return False  # хотя бы один бит = 0 → точно нет
        return True
    
    def expected_fpr(self) -> float:
        """Ожидаемый уровень ложных срабатываний"""
        return (1 - math.exp(-self.k * self._count / self.m)) ** self.k
    
    def __len__(self):
        return self._count

# Тест
bf = BloomFilter(capacity=1000, false_positive_rate=0.01)
# Bloom Filter: m=9585 бит (1.2 KB), k=7 хешей

# Добавляем элементы
urls_visited = ["google.com", "github.com", "python.org", "openai.com"]
for url in urls_visited:
    bf.add(url)

# Проверка
print("google.com" in bf)    # True (был добавлен)
print("bing.com" in bf)      # False (не добавляли, скорее всего)
print("yahoo.com" in bf)     # False или True (FP с вероятностью 0.01%)

print(f"Ожидаемый FPR: {bf.expected_fpr():.4%}")
```

### Математика Bloom Filter

**Вероятность false positive:**

```
p = (1 - e^(-kn/m))^k

где:
  k = количество хеш-функций
  n = количество вставленных элементов  
  m = размер битового массива

Оптимальный k = (m/n) * ln(2) ≈ 0.693 * m/n
При оптимальном k: p = (1/2)^k = (1/2)^(m*ln(2)/n)
```

```python
def bloom_filter_params(n, p):
    """Вычислить оптимальные параметры"""
    m = math.ceil(-n * math.log(p) / (math.log(2) ** 2))
    k = math.ceil((m / n) * math.log(2))
    
    print(f"n={n:,}, p={p}")
    print(f"m={m:,} бит = {m/8/1024:.1f} KB")
    print(f"k={k} хеш-функций")
    print(f"Бит на элемент: {m/n:.1f}")
    print()

# Сравнение: Bloom filter vs хеш-сет
bloom_filter_params(1_000_000, 0.01)   # 1% FPR
# n=1,000,000, p=0.01
# m=9,585,059 бит = 1,169.6 KB ≈ 1.2 MB
# k=7 хеш-функций
# Бит на элемент: 9.6

bloom_filter_params(1_000_000, 0.001)  # 0.1% FPR
# m=14,377,589 бит ≈ 1.7 MB (только в 1.5 раз больше при 10x лучшем FPR!)

# Хеш-сет для 1 млн строк (avg 20 байт):
# 1,000,000 × 20 байт + overhead ≈ 40-80 MB
# Bloom filter экономит в 50-70 раз!
```

### Counting Bloom Filter

Стандартный Bloom filter не поддерживает удаление (нельзя обнулить бит — он мог быть установлен другим элементом).

Counting Bloom Filter заменяет биты счётчиками:

```python
class CountingBloomFilter:
    def __init__(self, m: int, k: int):
        self.m = m
        self.k = k
        self.counters = [0] * m  # счётчики вместо битов
    
    def add(self, item: str):
        for seed in range(self.k):
            idx = mmh3.hash(item, seed) % self.m
            self.counters[idx] += 1
    
    def remove(self, item: str):
        """Удаление: уменьшаем счётчики"""
        if item not in self:
            raise ValueError("Element not in filter")
        for seed in range(self.k):
            idx = mmh3.hash(item, seed) % self.m
            self.counters[idx] -= 1
    
    def __contains__(self, item: str) -> bool:
        for seed in range(self.k):
            if self.counters[mmh3.hash(item, seed) % self.m] == 0:
                return False
        return True
```

### Cuckoo Filter: лучшая альтернатива

Cuckoo filter (Fan et al., 2014) — усовершенствование, поддерживающее удаление и обычно более эффективное по памяти:

```
Преимущества Cuckoo filter над Bloom filter:
- Поддержка удаления
- Лучшая пространственная эффективность при FPR < 3%
- Более быстрая проверка (cache-friendly)

Используется в: некоторые версии Redis, ClickHouse
```

### Применения Bloom Filter

```python
# 1. Cassandra: избежание disk lookups для несуществующих ключей
# Каждый SSTable имеет Bloom filter
# Чтение: сначала проверяем BF → если нет → не читаем с диска!

# 2. Chrome: список вредоносных URL
# Браузер хранит BF с тысячами плохих URL
# Быстрая проверка локально, обращение к серверу только при FP

# 3. HBase, Bigtable: аналогично Cassandra

# 4. Синхронизация паролей
# Have I Been Pwned: Bloom filter с 600M взломанных паролей
# Проверяем локально перед отправкой хеша на сервер

# 5. Веб-краулеры: "посещали ли мы этот URL?"
class WebCrawler:
    def __init__(self):
        self.visited = BloomFilter(capacity=10_000_000, false_positive_rate=0.001)
    
    def should_visit(self, url: str) -> bool:
        if url in self.visited:
            return False  # False Positive возможен, но редко!
        return True
    
    def mark_visited(self, url: str):
        self.visited.add(url)
```

## HyperLogLog: оценка количества уникальных элементов

HyperLogLog решает задачу cardinality estimation — подсчёт числа уникальных элементов в потоке данных при минимальной памяти.

### Идея: Leading zeros trick

```
Наблюдение: для случайного хеша вероятность, что он начинается с k нулей,
равна 1/2^k.

Если мы видим хеш с 5 ведущими нулями (00000...), 
вероятно, мы обработали примерно 2^5 = 32 уникальных элемента.

Это очень грубая оценка! Но её можно улучшить:
1. Используем m регистров (bucket)
2. Элемент попадает в регистр по первым log₂(m) битам хеша
3. В каждом регистре храним максимальное число ведущих нулей остатка хеша
4. Оцениваем мощность по гармоническому среднему 2^(max_zeros) по регистрам
```

```python
import hashlib
import math
from typing import List

class HyperLogLog:
    def __init__(self, error_rate: float = 0.01):
        """
        error_rate: стандартная погрешность ≈ 1.04 / sqrt(m)
        m = количество регистров (степень двойки)
        """
        # m = (1.04 / error_rate)²
        self.m = 1 << math.ceil(math.log2((1.04 / error_rate) ** 2))
        self.b = int(math.log2(self.m))  # бит для выбора регистра
        self.registers: List[int] = [0] * self.m
        
        print(f"HyperLogLog: m={self.m} регистров, ~{self.m/8} байт памяти")
        print(f"Погрешность: ±{100 * 1.04 / math.sqrt(self.m):.1f}%")
    
    def _hash(self, item: str) -> int:
        """32-битный хеш"""
        h = hashlib.md5(item.encode()).digest()[:4]
        return int.from_bytes(h, 'big')
    
    def _leading_zeros_plus_1(self, bits: int) -> int:
        """Количество ведущих нулей в (32-b)-битном числе + 1"""
        if bits == 0:
            return 33 - self.b
        count = 1
        # Ищем первый 1-бит (позиция = ведущие нули + 1)
        for i in range(32 - self.b - 1, -1, -1):
            if bits & (1 << i):
                return 32 - self.b - i
            count += 1
        return count
    
    def add(self, item: str) -> None:
        """O(1) — добавить элемент"""
        h = self._hash(item)
        
        # Первые b бит → номер регистра
        register_idx = h >> (32 - self.b)
        
        # Оставшиеся биты → позиция первой единицы
        remaining = h & ((1 << (32 - self.b)) - 1)
        rho = self._leading_zeros_plus_1(remaining)
        
        # Обновляем регистр максимумом
        if rho > self.registers[register_idx]:
            self.registers[register_idx] = rho
    
    def count(self) -> float:
        """O(m) — оценить количество уникальных элементов"""
        # Коэффициент α для коррекции систематической ошибки
        alpha = {16: 0.673, 32: 0.697, 64: 0.709}.get(
            self.m, 0.7213 / (1 + 1.079 / self.m)
        )
        
        # Гармоническое среднее 2^register[j]
        raw_estimate = alpha * self.m ** 2 / sum(2 ** (-r) for r in self.registers)
        
        # Коррекции для маленьких и больших значений
        if raw_estimate <= 2.5 * self.m:
            # Small range correction: Linear Counting
            zeros = self.registers.count(0)
            if zeros > 0:
                return self.m * math.log(self.m / zeros)
        
        if raw_estimate > (1 << 32) / 30:
            # Large range correction
            return -(1 << 32) * math.log(1 - raw_estimate / (1 << 32))
        
        return raw_estimate

# Тест
hll = HyperLogLog(error_rate=0.01)
# HyperLogLog: m=16384 регистров, ~2048 байт памяти
# Погрешность: ±0.8%

import random
unique_count = 1_000_000
for i in range(unique_count):
    hll.add(f"user_{i}")
    # Добавляем дубли — не влияют на результат
    if random.random() < 0.5:
        hll.add(f"user_{i}")

estimate = hll.count()
print(f"Реальное: {unique_count:,}")
print(f"Оценка HLL: {estimate:,.0f}")
print(f"Погрешность: {abs(estimate - unique_count)/unique_count:.2%}")
```

### HyperLogLog в Redis

```bash
# Redis: HyperLogLog встроен как тип данных
# PFADD — добавить элементы
# PFCOUNT — получить оценку уникальных

PFADD page_views "user_1" "user_2" "user_3"
PFCOUNT page_views
# (integer) 3

# Миллион уникальных посетителей:
# Точный Set: ~50 MB
# HyperLogLog: 12 KB (фиксированный размер!)

# Слияние HyperLogLog для разных серверов:
PFMERGE total_views page_views_1 page_views_2 page_views_3
PFCOUNT total_views  # уникальные по всем серверам
```

## Count-Min Sketch: приближённый подсчёт частот

Count-Min Sketch (Cormode & Muthukrishnan, 2003) — структура для оценки частот элементов в потоке данных.

### Идея

```
d хеш-функций × w счётчиков = матрица d×w счётчиков.

Добавление элемента x:
  Для каждой строки i: increment cms[i][h_i(x)]

Оценка частоты элемента x:
  min(cms[i][h_i(x)]) по всем строкам i

Почему min? Коллизии могут только увеличивать счётчики, но не уменьшать.
min = наименьшее переоценённое значение ≈ истинное значение.
```

```python
import mmh3

class CountMinSketch:
    def __init__(self, width: int, depth: int):
        """
        width (w): ширина — точность
        depth (d): глубина — уверенность
        
        Ошибка ≤ ε * total_count с вероятностью 1 - δ
        Оптимально: w = ceil(e/ε), d = ceil(ln(1/δ))
        """
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]
        self.total = 0
    
    def add(self, item: str, count: int = 1) -> None:
        """O(d)"""
        for i in range(self.depth):
            idx = mmh3.hash(item, i) % self.width
            self.table[i][idx] += count
        self.total += count
    
    def estimate(self, item: str) -> int:
        """O(d) — оценка частоты элемента (может быть завышена!)"""
        return min(
            self.table[i][mmh3.hash(item, i) % self.width]
            for i in range(self.depth)
        )
    
    @classmethod
    def from_error_rate(cls, epsilon: float, delta: float) -> 'CountMinSketch':
        """
        Создать CMS с гарантиями:
        P(estimate > freq + ε * total) ≤ δ
        """
        import math
        width = math.ceil(math.e / epsilon)
        depth = math.ceil(math.log(1 / delta))
        return cls(width, depth)

# Пример: топ-K частых элементов в потоке
import heapq
from collections import defaultdict

def top_k_frequent(stream, k, epsilon=0.01, delta=0.01):
    """Приближённый Top-K с Count-Min Sketch"""
    cms = CountMinSketch.from_error_rate(epsilon, delta)
    
    # Первый проход: считаем частоты приближённо
    for item in stream:
        cms.add(item)
    
    # Второй проход: находим кандидатов
    candidates = set(stream)  # упрощённо
    
    # Топ-K по оценкам
    heap = []
    for item in candidates:
        freq = cms.estimate(item)
        if len(heap) < k:
            heapq.heappush(heap, (freq, item))
        elif freq > heap[0][0]:
            heapq.heapreplace(heap, (freq, item))
    
    return sorted(heap, reverse=True)

# Тест: поток с Zipfian распределением (реалистично)
import random

words = ["python", "java", "rust", "go", "c++", "javascript", "ruby", "swift"]
stream = []
for w in words:
    # Zipfian: первые слова встречаются чаще
    stream.extend([w] * (100 // (words.index(w) + 1)))

random.shuffle(stream)

top5 = top_k_frequent(stream, 5)
print("Топ-5 частых слов:")
for freq, word in top5:
    print(f"  {word}: ≈{freq} раз")
```

### Применения Count-Min Sketch

```python
# 1. DDoS обнаружение: топ-K исходных IP
# Kafka: счётчики сообщений по топику
# Monitoring: topmost frequent queries

# 2. Приближённый подсчёт в Apache Spark
# df.approx_count_distinct() использует HyperLogLog
# Spark SQL heavy hitters через CMS

# 3. Redis Streams: приближённые аналитики

# 4. Sliding window: частоты за последние N минут
class SlidingWindowCMS:
    def __init__(self, width, depth, window_size):
        self.windows = []
        self.current = CountMinSketch(width, depth)
        self.window_size = window_size
    
    def add(self, item, timestamp):
        # Упрощённая sliding window логика
        self.current.add(item)
    
    def estimate(self, item):
        return self.current.estimate(item)
```

## MinHash: Jaccard similarity приближённо

MinHash — алгоритм для приближённого вычисления сходства множеств через Jaccard similarity.

```python
import hashlib
import random

def minhash_similarity(set1, set2, num_hashes=100):
    """
    Приближённое сходство Жаккара через MinHash.
    Jaccard(A, B) = |A ∩ B| / |A ∪ B|
    """
    # Генерируем num_hashes хеш-функций (через universal hashing)
    params = [(random.randint(1, 2**31), random.randint(0, 2**31)) 
              for _ in range(num_hashes)]
    
    def minhash(s: set):
        """Вычислить MinHash сигнатуру множества"""
        signature = []
        for a, b in params:
            min_hash = float('inf')
            for elem in s:
                h = (a * hash(elem) + b) % (2**31)
                min_hash = min(min_hash, h)
            signature.append(min_hash)
        return signature
    
    sig1 = minhash(set1)
    sig2 = minhash(set2)
    
    # Доля совпадающих минимальных хешей ≈ Jaccard(set1, set2)
    matches = sum(1 for h1, h2 in zip(sig1, sig2) if h1 == h2)
    return matches / num_hashes

# Пример: обнаружение похожих документов
doc1 = {"python", "programming", "functions", "algorithms", "data"}
doc2 = {"python", "programming", "data", "analysis", "statistics"}
doc3 = {"java", "spring", "microservices", "api", "rest"}

print(f"doc1 vs doc2: {minhash_similarity(doc1, doc2):.2f}")  # ≈ 0.33 (3/9 общих)
print(f"doc1 vs doc3: {minhash_similarity(doc1, doc3):.2f}")  # ≈ 0.00
print(f"Точный Jaccard(1,2): {len(doc1&doc2)/len(doc1|doc2):.2f}")

# MinHash используется в:
# - Google: обнаружение дубликатов веб-страниц
# - Рекомендательные системы (похожие пользователи/товары)
# - Locality Sensitive Hashing (LSH)
```

## Практическое сравнение

```python
# Итоговая таблица вероятностных структур:

structures = {
    "Bloom Filter": {
        "задача": "Membership query (есть/нет)",
        "память": "~10 бит/элемент при FPR 1%",
        "ошибка": "False Positives (1-2%)",
        "гарантия": "Нет False Negatives",
        "применение": "Cassandra, Chrome, HBase"
    },
    "HyperLogLog": {
        "задача": "Cardinality estimation",
        "память": "12 KB для любого N",
        "ошибка": "~0.8% при m=16384",
        "применение": "Redis, BigQuery, Presto"
    },
    "Count-Min Sketch": {
        "задача": "Frequency estimation",
        "память": "Фиксированная (d×w счётчиков)",
        "ошибка": "Только переоценка (не занижение)",
        "применение": "Kafka, Apache Flink"
    },
    "MinHash": {
        "задача": "Set similarity (Jaccard)",
        "память": "O(num_hashes)",
        "ошибка": "±sqrt(1/num_hashes)",
        "применение": "Near-duplicate detection, LSH"
    }
}
```

## Итоги

Вероятностные структуры данных — мощный инструмент для работы с большими данными:

- **Bloom Filter:** Точная проверка "нет", приближённая "есть". 10-15 бит на элемент.
- **HyperLogLog:** Подсчёт уникальных элементов. 12 КБ для любого количества.
- **Count-Min Sketch:** Приближённые частоты в потоке. Фиксированная память.
- **MinHash:** Схожесть множеств без их полного хранения.

Ключевое свойство: **нет false negatives** (у Bloom filter и CMS). Это позволяет использовать их как первый быстрый фильтр.

## Литература

1. Bloom, B. H. (1970). Space/time trade-offs in hash coding with allowable errors. *Communications of the ACM*, 13(7), 422–426. https://dl.acm.org/doi/10.1145/362686.362692

2. Flajolet, P., & Martin, G. N. (1985). Probabilistic counting algorithms for data base applications. *Journal of Computer and System Sciences*, 31(2). https://doi.org/10.1016/0022-0000(85)90041-8 — прародитель HyperLogLog

3. Flajolet, P., Fusy, É., Gandouet, O., & Meunier, F. (2007). HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm. *AOFA 2007*. https://algo.inria.fr/flajolet/Publications/FlFuGaMe07.pdf

4. Cormode, G., & Muthukrishnan, S. (2005). An improved data stream summary: the count-min sketch and its applications. *Journal of Algorithms*, 55(1). https://dl.acm.org/doi/10.1016/j.jalgor.2003.12.001

5. Fan, B. et al. (2014). Cuckoo filter: Practically better than Bloom. *CoNEXT 2014*. https://dl.acm.org/doi/10.1145/2674005.2674994

6. Broder, A. Z. (1997). On the resemblance and containment of documents. *Compression and Complexity of Sequences*. — MinHash

7. Redis HyperLogLog documentation. https://redis.io/docs/data-types/probabilistic/hyperlogllog/

8. Cassandra Bloom Filter documentation. https://cassandra.apache.org/doc/latest/cassandra/operating/bloom_filters.html

9. Heule, S., Nunkesser, M., & Hall, A. (2013). HyperLogLog in Practice. *EDBT 2013*. https://research.google/pubs/pub40671/ — улучшенный HyperLogLog от Google

10. Mitzenmacher, M., & Eli Upfal. (2005). *Probability and Computing: Randomized Algorithms and Probabilistic Analysis*. Cambridge University Press. — теоретические основы
