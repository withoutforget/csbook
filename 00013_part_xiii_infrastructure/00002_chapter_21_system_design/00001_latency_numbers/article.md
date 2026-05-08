# Latency Numbers Every Programmer Should Know — числа, без которых нельзя проектировать системы

Существует одна таблица, которую должен знать каждый разработчик, проектирующий системы. Это таблица latency чисел, популяризированная Джеффом Дином (Google) и Питером Норвигом. Она отвечает на вопрос: сколько времени занимают фундаментальные операции в вычислительных системах? Без этих чисел невозможно принимать обоснованные архитектурные решения.

## Что такое latency и почему она важна

**Latency** (задержка) — время между инициацией операции и получением ответа. Это не пропускная способность (throughput), не bandwidth — это именно время ожидания.

Аналогия для понимания разницы:
- Трамвай везёт 200 пассажиров (высокий throughput)
- Но он идёт 30 минут (высокая latency)
- Такси везёт 1 пассажира (низкий throughput)
- Но приезжает за 5 минут (низкая latency)

Для разработчиков важны оба параметра, но latency часто более критична для пользовательского опыта: исследования показывают, что задержка более 100ms воспринимается пользователем как «тормоза», а более 1 секунды — как «сломано».

## Таблица latency чисел

Ниже приведены актуальные числа с учётом современного железа (2024):

```
Операция                              Время        Примечание
──────────────────────────────────────────────────────────────────
L1 cache hit (CPU кеш 1-го уровня)    0.5  нс
Ветвление (branch misprediction)      5    нс
L2 cache hit (CPU кеш 2-го уровня)    7    нс
Mutex lock/unlock                     25   нс
RAM access (основная память)          100  нс      ~200x медленнее L1
──────────────────────────────────────────────────────────────────
Чтение 1MB из памяти                  3    мкс      3,000 нс
Сжатие 1KB (Snappy/LZ4)              3    мкс
Системный вызов (syscall)             1-5  мкс
──────────────────────────────────────────────────────────────────
SSD random read (NVMe)                20   мкс      NVMe vs SATA SSD
SSD sequential read (NVMe, 1MB)       200  мкс
SATA SSD random read                  100  мкс
Чтение 1MB из SSD                     1    мс
──────────────────────────────────────────────────────────────────
HDD seek (произвольный доступ)        10   мс       10,000x медленнее RAM!
Чтение 1MB из HDD                     20   мс
──────────────────────────────────────────────────────────────────
Round trip в одном датацентре         500  мкс      0.5ms
Round trip через Cloudflare/CDN       1-5  мс
Round trip на другой конец страны     30   мс       US East → US West
Трансатлантический round trip         150  мс       US → Europe
Транстихоокеанский round trip         250  мс       US → Asia
Кругосветный ping                     ~400 мс
──────────────────────────────────────────────────────────────────
```

**Исторические числа (Jeff Dean, 2012) vs современные (2024):**

```
Операция                     2012        2024
──────────────────────────────────────────────────────
L1 cache hit                 0.5 нс      0.5 нс       (без изменений)
RAM access                   100 нс      100 нс        (без изменений)
SSD random 4K read           150 мкс     20-100 мкс   (NVMe революция)
HDD seek                     10 мс       10 мс         (без изменений)
Датацентр round trip         500 мкс     500 мкс      (физика неизменна)
```

Ключевое наблюдение: скорость передачи данных между компонентами (RAM → CPU, SSD → RAM) практически не изменилась за 10 лет. Изменился только SSD с появлением NVMe.

## Визуализация порядков величин

Чтобы прочувствовать масштаб, представьте L1 cache = 1 секунда:

```
L1 cache      1 сек         — вы открыли ящик стола
L2 cache      14 сек        — вы встали и взяли книгу с полки
RAM           3.5 мин       — вы сходили на другой этаж
NVMe SSD      11 часов      — вы поехали в другой город
SATA SSD      32 часа       — вы сходили пешком из Москвы в Петербург
HDD seek      12 дней       — вы съездили в кругосветное путешествие
Датацентр     6 дней        — вы поехали в Европу
Трансатлантик ~6 лет        — вы ждали пока ваш ребёнок пойдёт в школу
```

Теперь понятно, почему «просто добавить один вызов к базе данных» может стоить дорого, если база данных в другом датацентре.

## Принцип 1: Prefer Local — предпочитай локальные данные

Если данные нужны часто — держи их как можно ближе к CPU:

```python
# Плохо: каждый запрос = обращение к Redis (сеть)
def get_user_permissions(user_id: int) -> list[str]:
    return redis.smembers(f"user:{user_id}:permissions")
    # ~1ms (сеть + Redis операция)

# Хорошо: кешировать в памяти процесса
from functools import lru_cache

@lru_cache(maxsize=10000)
def get_user_permissions(user_id: int) -> frozenset[str]:
    permissions = redis.smembers(f"user:{user_id}:permissions")
    return frozenset(permissions)
    # Первый вызов: ~1ms
    # Повторные вызовы: ~100нс (L1/L2 cache hit)

# Ещё лучше: предзагрузить всё в памяти при старте
PERMISSIONS_CACHE: dict[int, frozenset[str]] = {}

async def preload_permissions():
    """Загружаем при старте — потом только память"""
    all_users = await db.fetch("SELECT user_id, permission FROM permissions")
    for user_id, permission in all_users:
        if user_id not in PERMISSIONS_CACHE:
            PERMISSIONS_CACHE[user_id] = set()
        PERMISSIONS_CACHE[user_id].add(permission)
    # После этого: get_user_permissions → 100нс, не 1ms
```

**Разница в 10,000x** между обращением к памяти (~100нс) и обращением к Redis в другом процессе (~1мс).

## Принцип 2: Avoid Disk When Possible — избегай диска

```python
# Плохо: читаем конфигурацию из файла при каждом запросе
def handle_request(request):
    config = json.loads(open('/etc/app/config.json').read())  # ~20мкс+ SSD
    # ... обработка

# Хорошо: загружаем один раз
_config = None

def get_config() -> dict:
    global _config
    if _config is None:
        _config = json.loads(open('/etc/app/config.json').read())
    return _config  # После первого вызова: ~100нс (RAM)

# Для высоконагруженных систем: mmap
import mmap

with open('large_lookup_table.bin', 'rb') as f:
    # mmap позволяет обращаться к файлу как к памяти
    # ОС подкачивает нужные страницы по запросу
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    # Случайный доступ: ~20мкс (NVMe) или ~100нс если закешировано ОС
```

**Особый случай — Write-Ahead Log:**
Несмотря на медленность диска, последовательная запись намного быстрее случайного доступа. PostgreSQL, MySQL, Kafka используют WAL: данные записываются последовательно в лог (быстро), а потом применяются к основным структурам. Последовательная запись на NVMe: ~1GB/s, случайная запись: ~0.1GB/s.

## Принцип 3: Batch Small Operations — группируй мелкие операции

```python
# Плохо: N запросов к БД (N+1 problem)
users = db.query("SELECT id FROM users WHERE active = true")
for user in users:
    orders = db.query(f"SELECT * FROM orders WHERE user_id = {user.id}")
    # N+1 запросов = N * 1ms = может быть 10 секунд для 10,000 пользователей!

# Хорошо: один JOIN запрос
result = db.query("""
    SELECT u.id, o.*
    FROM users u
    LEFT JOIN orders o ON o.user_id = u.id
    WHERE u.active = true
""")
# 1 запрос = 1ms (вместо N ms)

# Для Redis: использовать pipeline вместо отдельных команд
# Плохо: N отдельных GET команд = N * 1ms round-trip
results = [redis.get(f"key:{i}") for i in range(1000)]

# Хорошо: pipeline = 1 round-trip
pipeline = redis.pipeline()
for i in range(1000):
    pipeline.get(f"key:{i}")
results = pipeline.execute()
# 1ms вместо 1000ms!
```

## NVMe SSD: революция в хранилищах

SATA SSD имеют ограничение интерфейса SATA (~600 MB/s). NVMe (Non-Volatile Memory Express) подключается через PCIe и даёт:
- Последовательное чтение: до 7,000 MB/s (vs 500 MB/s SATA)
- Случайный доступ (4K): 20-40мкс (vs 100-150мкс SATA)
- IOPS: 500,000-1,000,000 (vs 100,000 SATA)

```bash
# Измерение latency диска
fio --name=latency-test \
    --rw=randread \
    --bs=4k \
    --numjobs=1 \
    --iodepth=1 \  # Важно: iodepth=1 для измерения latency, не throughput
    --runtime=30 \
    --filename=/dev/nvme0n1 \
    --output-format=normal

# Ожидаемый результат для NVMe:
# read: IOPS=250k, lat (usec): avg=4.0, p99=8.0, p99.9=20.0
```

**Persistent Memory (PMEM/Optane):** Intel Optane DC Persistent Memory обеспечивает ~300нс для случайного доступа — между RAM (100нс) и NVMe (20мкс). Технология не получила широкого распространения, но показала направление.

## Что изменилось с появлением облаков

В облачных окружениях latency числа могут существенно отличаться от bare metal:

```
Операция                          Bare Metal    AWS EC2
──────────────────────────────────────────────────────────────
Внутрисетевой вызов (same AZ)     50 мкс        200-500 мкс
Вызов в другую AZ                 500 мкс       2-5 мс
RDS PostgreSQL запрос (same AZ)   N/A           1-5 мс
DynamoDB GetItem                  N/A           1-10 мс
S3 GetObject (<1MB)               N/A           5-50 мс
```

**Причины overhead в облаке:**
- Сетевая виртуализация (virtual switching, SR-IOV)
- Storage виртуализация (EBS — сетевые диски!)
- Многоарендная среда (noisy neighbors)

Важный нюанс: **EBS (Elastic Block Store) в AWS — это сетевые диски**. Операция чтения с EBS = сетевой вызов в другую машину, не локальный disk I/O!

```python
# Это важно при дизайне на AWS:

# На EC2 с EBS: каждый disk read = ~1ms (сетевой I/O)
# Решение: использовать instance store (NVMe диск в той же машине)
# Или: размещать горячие данные в ElastiCache (Redis)

# Проверить тип хранилища:
# aws ec2 describe-instances --query "...StorageInfo..."
```

## Практический анализ: оцени latency вашего запроса

Пример: пользователь открывает страницу интернет-магазина, что происходит?

```
Запрос: GET /products/catalog?category=electronics

Шаг 1: DNS lookup
  - Браузер обращается к DNS: ~50ms (первый раз, потом кеш)
  
Шаг 2: TCP + TLS handshake
  - TCP: 1 RTT = ~30ms (пользователь в Европе, сервер в США)
  - TLS 1.3: 1 RTT = ~30ms (TLS 1.2: 2 RTT = ~60ms)
  - Итого: ~60ms до первого байта
  
Шаг 3: Application Layer (сервер обрабатывает запрос)
  - Nginx получает запрос: ~0.1ms
  - Nginx → App Server (локальный): ~0.5ms (loopback)
  - App Server: проверяет Auth
    - JWT verify (CPU): ~0.1ms
    - Redis: check token blacklist: ~1ms
  - App Server: запрос к PostgreSQL
    - Connection pool (уже открыто): ~0.1ms
    - SQL query + network: ~2ms (same datacenter)
    - PostgreSQL execution: ~5ms (index scan на 1M товаров)
  - App Server: обогащение данными из Redis (цены, остатки)
    - Pipeline 50 ключей: ~1ms
  - App Server: сериализация JSON (1000 товаров): ~2ms
  - App Server → Nginx: ~0.5ms
  - Итого на сервере: ~12ms
  
Шаг 4: Передача ответа
  - JSON response 500KB: 500KB / (50Mbps / 8) = ~80ms transfer time
  
Итого end-to-end: ~200ms
```

Теперь посмотрим, как улучшить:
- CDN Edge Cache: HTML/статика отдаётся из Нью-Йорка (30ms RTT) вместо 150ms
- Сжатие gzip: 500KB → 50KB = 8ms transfer time вместо 80ms
- Redis кеш для товаров: 5ms SQL → 1ms Redis
- **Итого: ~50ms** вместо ~200ms

## Latency числа для баз данных

```
База данных          Операция           Latency      Примечание
──────────────────────────────────────────────────────────────────
PostgreSQL           Primary key GET    0.5-2 мс     Index lookup
PostgreSQL           Full table scan    10-1000 мс   Зависит от размера
Redis                GET (RAM)          0.3-1 мс     In-memory
Redis Cluster        GET                1-2 мс       Extra hop
Cassandra            Single row read    0.5-5 мс     Local replica
Cassandra            Cross-DC read      100+ мс      Quorum
MongoDB              FindOne (indexed)  1-5 мс
Elasticsearch        Term query         5-50 мс      Зависит от индекса
DynamoDB             GetItem            1-10 мс      AWS managed
BigTable             Row read           1-10 мс      Row key lookup
```

```python
# Benchmark: измерение реальной latency PostgreSQL
import time
import psycopg2
import statistics

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Тест 1: Primary Key lookup (должно быть < 2ms)
latencies = []
for i in range(1000):
    start = time.perf_counter_ns()
    cur.execute("SELECT * FROM users WHERE id = %s", (12345,))
    cur.fetchone()
    end = time.perf_counter_ns()
    latencies.append((end - start) / 1_000_000)  # в миллисекундах

print(f"PostgreSQL Primary Key Lookup:")
print(f"  p50: {statistics.median(latencies):.2f}ms")
print(f"  p99: {sorted(latencies)[int(len(latencies) * 0.99)]:.2f}ms")
print(f"  p99.9: {sorted(latencies)[int(len(latencies) * 0.999)]:.2f}ms")

# Тест 2: Без индекса (должно быть намного хуже!)
latencies_no_index = []
for i in range(100):
    start = time.perf_counter_ns()
    cur.execute("SELECT * FROM orders WHERE status = 'pending'")
    cur.fetchall()
    end = time.perf_counter_ns()
    latencies_no_index.append((end - start) / 1_000_000)

print(f"\nPostgreSQL Full Scan (нет индекса):")
print(f"  p50: {statistics.median(latencies_no_index):.2f}ms")
```

## Latency числа для сетевых вызовов

```python
import time
import socket
import statistics

def measure_tcp_latency(host: str, port: int, count: int = 100) -> dict:
    """Измеряет TCP round-trip time."""
    latencies = []
    
    for _ in range(count):
        start = time.perf_counter_ns()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        sock.close()
        
        end = time.perf_counter_ns()
        latencies.append((end - start) / 1_000_000)
    
    sorted_lat = sorted(latencies)
    return {
        'p50': statistics.median(latencies),
        'p95': sorted_lat[int(count * 0.95)],
        'p99': sorted_lat[int(count * 0.99)],
        'min': min(latencies),
        'max': max(latencies),
    }

# Типичные результаты:
# loopback (127.0.0.1): p50 = 0.05ms
# same host, different process: p50 = 0.1ms  
# same datacenter: p50 = 0.5ms
# same region, different AZ: p50 = 2ms
# US East to US West: p50 = 60ms
# US to Europe: p50 = 150ms
```

## Latency и закон Little's

**Закон Литтла (Little's Law):** $N = \lambda \times W$

Где:
- N = среднее количество задач в системе (очередь + обрабатываемые)
- $\lambda$ = throughput (задач в секунду)
- W = среднее время в системе (latency)

```python
# Практическое применение закона Литтла
# Вопрос: сколько параллельных запросов нужно поддерживать?

# Если:
throughput = 1000  # запросов/секунду
latency_seconds = 0.1  # 100ms

# То:
# N = λ × W = 1000 * 0.1 = 100 параллельных запросов
concurrent_requests = throughput * latency_seconds
print(f"Нужно поддерживать: {concurrent_requests} параллельных запросов")

# Если latency растёт до 1 секунды при пиковой нагрузке:
peak_latency = 1.0
peak_concurrent = throughput * peak_latency
print(f"При деградации: {peak_concurrent} concurrent")
# = 1000 параллельных запросов!

# Вывод для дизайна: connection pool должен иметь минимум 100 соединений,
# при деградации — выдерживать 1000.
```

## NUMA и влияние на latency

На многопроцессорных серверах (NUMA — Non-Uniform Memory Access) доступ к памяти своего сокета быстрее:

```
NUMA Node 0 (CPU 0-15, RAM 0-64GB):  Local memory: 100нс
NUMA Node 1 (CPU 16-31, RAM 64-128GB): Remote memory: 150-200нс

# Проверить NUMA топологию
numactl --hardware

# Привязать процесс к NUMA node
numactl --cpunodebind=0 --membind=0 ./myapp
```

Для баз данных с большим объёмом RAM (PostgreSQL shared_buffers, Redis) NUMA имеет значение. Неправильная привязка может замедлить memory-intensive операции на 30-50%.

## Практические выводы для проектирования

### 1. Кешируй агрессивно, но с умом

```python
from cachetools import TTLCache
import threading

class UserProfileCache:
    """
    Трёхуровневый кеш:
    L1: в-процессный (100нс) - для горячих данных
    L2: Redis (1мс) - для общего состояния между инстансами  
    L3: PostgreSQL (5мс) - источник истины
    """
    
    def __init__(self):
        # L1: 1000 профилей, TTL 60 секунд
        self._local_cache = TTLCache(maxsize=1000, ttl=60)
        self._lock = threading.Lock()
    
    def get(self, user_id: int) -> dict:
        # L1 hit: ~100нс
        if user_id in self._local_cache:
            return self._local_cache[user_id]
        
        # L2 hit: ~1мс
        cached = redis.get(f"user:{user_id}")
        if cached:
            profile = json.loads(cached)
            with self._lock:
                self._local_cache[user_id] = profile
            return profile
        
        # L3 miss: ~5мс
        profile = db.query("SELECT * FROM users WHERE id = ?", user_id)
        redis.setex(f"user:{user_id}", 300, json.dumps(profile))
        with self._lock:
            self._local_cache[user_id] = profile
        return profile
```

### 2. Размещай сервисы близко друг к другу

Если сервис A вызывает сервис B 100 раз на один пользовательский запрос:
- В одном датацентре: $100 \times 0.5$ мс = 50мс overhead
- В разных датацентрах: $100 \times 150$ мс = 15 секунд! Запрос упадёт по timeout.

**Вывод:** Сервисы с высокочастотным взаимодействием должны быть в одной AZ.

### 3. Оценивай перед реализацией

```python
def estimate_api_latency(
    hops: list[dict]  # [{type: 'db|redis|rpc|disk', count: int}]
) -> float:
    """
    Быстрая оценка latency API endpoint.
    """
    LATENCIES = {
        'l1_cache': 0.0001,  # 100нс
        'redis': 1.0,         # 1мс
        'db_indexed': 2.0,    # 2мс
        'db_scan': 50.0,      # 50мс
        'http_local': 0.5,    # 0.5мс
        'http_same_dc': 1.0,  # 1мс
        'http_cross_dc': 150.0, # 150мс
        'ssd_read': 0.1,      # 100мкс NVMe
        'cpu_ms': 0.1,        # 100мкс CPU work
    }
    
    total = 0.0
    for hop in hops:
        total += LATENCIES.get(hop['type'], 0) * hop.get('count', 1)
    
    return total

# Оцениваем endpoint:
latency = estimate_api_latency([
    {'type': 'redis', 'count': 1},      # auth check
    {'type': 'db_indexed', 'count': 1}, # main query
    {'type': 'redis', 'count': 3},      # enrichment
    {'type': 'cpu_ms', 'count': 2},     # processing
])
print(f"Ожидаемая latency: ~{latency}ms")  # ~7.1ms
```

### 4. Думай о хвостовой latency

**Fan-out amplification:** если страница делает 10 параллельных запросов, итоговая latency = max(all 10 requests), не average. Если p99 каждого запроса = 50ms, то страница с 10 параллельными запросами имеет p99 $\approx$ 50ms (max из 10 независимых p99).

Но при зависимых (последовательных) запросах: итоговый p99 $\approx$ sum(individual p99).

## Заключение

Таблица latency чисел — это не просто справочник. Это инструмент мышления. Каждый раз, когда вы проектируете функцию или систему, задайте себе вопросы:

1. Сколько раз эта операция будет вызываться на один пользовательский запрос?
2. Где хранятся данные — в RAM, на SSD, в сети?
3. Есть ли возможность закешировать на более быстром уровне?
4. Как это масштабируется с ростом трафика?

Разработчик, который держит эти числа в голове, принимает принципиально лучшие решения при проектировании систем. Разница между «я думаю это будет быстро» и «я посчитал — это займёт 5мс» — это разница между интуицией и инженерией.

## Литература

1. **Dean, Jeff; Ghemawat, Sanjay** — «MapReduce: Simplified Data Processing on Large Clusters». OSDI 2004. (Содержит оригинальную таблицу latency)
2. **Norvig, Peter** — «Teach Yourself Programming in Ten Years»: http://norvig.com/21-days.html (упоминает таблицу)
3. **Gregg, Brendan** — «Systems Performance: Enterprise and the Cloud», 2nd ed. Pearson, 2020. ISBN: 978-0136820154
4. **Gregg, Brendan** — «Latency Numbers Every Programmer Should Know» (интерактивная): https://colin-scott.github.io/personal_website/research/interactive_latency.html
5. **Kleppmann, Martin** — «Designing Data-Intensive Applications». O'Reilly Media, 2017. ISBN: 978-1449373320
6. **Little, John D.C.** — «A Proof for the Queuing Formula: $L = \lambda W$». Operations Research, 1961
7. **Gunther, Neil J.** — «Guerrilla Capacity Planning». Springer, 2007. ISBN: 978-3540261384
8. **NVMe Express Specification** — https://nvmexpress.org/specifications/
9. **Intel** — «Optane Persistent Memory Technical Brief»: https://www.intel.com/content/www/us/en/products/docs/memory-storage/optane-persistent-memory/
10. **Google SRE Book** — «Handling Overload», Chapter 21: https://sre.google/sre-book/handling-overload/
