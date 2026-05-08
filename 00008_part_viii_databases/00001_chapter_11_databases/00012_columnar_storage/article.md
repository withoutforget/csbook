# Колоночное хранение: ClickHouse, BigQuery, DuckDB

## Введение

Когда аналитик запрашивает среднюю стоимость заказов по регионам за последний год из таблицы с миллиардом строк и сотней колонок — ему нужны всего несколько полей. Строковая СУБД всё равно прочитает с диска все сто колонок для каждой строки. Колоночная СУБД прочитает только нужные два-три столбца — и сделает это на скоростях, недостижимых для строковых движков.

Колоночное хранение (columnar storage) — это архитектурный принцип, в котором данные физически расположены на диске поколонно, а не построчно. Этот принцип известен с 1970-х (TAXIR, 1969; Cantor, 1975), но практического расцвета достиг в 2000-е с появлением C-Store (MIT, 2005), а затем коммерческих систем: Vertica, Amazon Redshift, Google BigQuery, ClickHouse.

---

## 1. Физика колоночного хранения

### 1.1 Почему это быстрее для аналитики

Рассмотрим таблицу 10 миллионов строк, 50 колонок, запрос выбирает 3 колонки:

```
Строковое хранение:
- Нужно прочитать: 10M строк × 50 колонок × 8 байт = 4 GB
- Реально нужно: 10M × 3 колонки × 8 байт = 240 MB
- КПД чтения: 6%

Колоночное хранение:
- Читаем только 3 колонки: 240 MB
- КПД чтения: 100%
- Выигрыш: 16.7x по объёму I/O
```

Но это только начало. Колоночные данные **лучше сжимаются**. В одной колонке — однотипные данные, которые часто повторяются или имеют небольшой диапазон.

```
Колонка "country" (строки):
RU, RU, RU, US, RU, DE, RU, RU, US, RU...

Dictionary encoding:
- Словарь: {0: "RU", 1: "US", 2: "DE"}
- Данные: [0,0,0,1,0,2,0,0,1,0...] → 2 бита на значение вместо 20 байт
- Сжатие: ~80x
```

### 1.2 Техники компрессии колонок

**Run-Length Encoding (RLE)**: последовательности одинаковых значений:
```
[5,5,5,5,5,3,3,7,7,7,7] → [(5,5), (3,2), (7,4)]
```

Особенно эффективно при сортировке по этой колонке.

**Dictionary Encoding**: замена часто встречающихся строк целыми числами. Для колонок с низкой кардинальностью (страна, статус, категория).

**Delta Encoding**: хранение разностей вместо абсолютных значений:
```
Timestamps: [1700000000, 1700000001, 1700000003, 1700000007]
Deltas:      [1700000000, +1, +2, +4] — меньше бит на каждое значение
```

**Bit-packing**: если значения в диапазоне 0-100, достаточно 7 бит вместо 64:
```python
import numpy as np

# Обычное int64: 8 байт на значение
values = np.array([45, 12, 87, 33, 66], dtype=np.int64)  # 40 байт

# Bit-packed в 7 бит: 35 бит на 5 значений = ~5 байт
# Реальное сжатие: ~8x
```

**FSST (Fast Static Symbol Table)**: для строковых колонок — сжатие через статическую таблицу символов, специфичную для данных.

### 1.3 Векторизованное исполнение запросов

Ключевой принцип: вместо обработки одной строки за итерацию — обрабатывать **вектор** (батч из 1024–8192 значений) за одну итерацию.

```python
# Строковая интерпретация: один кортеж за раз
def row_sum_filtered(table, threshold):
    total = 0
    for row in table:
        if row['salary'] > threshold:  # ветвление на каждой строке
            total += row['salary']
    return total

# Векторизованная: SIMD-операции над массивами
def vectorized_sum_filtered(salary_column, threshold):
    import numpy as np
    mask = salary_column > threshold  # векторное сравнение
    return salary_column[mask].sum()  # векторная сумма

# numpy использует SSE/AVX инструкции: обрабатывает 4-8 значений за такт
```

Vectorized execution engine — основа быстрых колоночных СУБД: DuckDB, Velox (Meta), Apache Arrow.

---

## 2. Apache Arrow: in-memory колоночный формат

### 2.1 Стандарт для обмена данными

Apache Arrow (2016) — открытый стандарт in-memory колоночного формата, позволяющий системам обмениваться данными без сериализации.

```python
import pyarrow as pa
import pyarrow.compute as pc

# Создание колоночного батча
arrays = [
    pa.array([1, 2, 3, 4, 5], type=pa.int64()),
    pa.array(['Alice', 'Bob', 'Carol', 'Dave', 'Eve']),
    pa.array([80000.0, 70000.0, 90000.0, 65000.0, 95000.0], type=pa.float64())
]
schema = pa.schema([('id', pa.int64()), ('name', pa.string()), ('salary', pa.float64())])
batch = pa.record_batch(arrays, schema=schema)

# Фильтрация без копирования (zero-copy через битовую маску)
mask = pc.greater(batch.column('salary'), 75000)
filtered = batch.filter(mask)

# Агрегации через Arrow compute
avg_salary = pc.mean(batch.column('salary'))
max_salary = pc.max(batch.column('salary'))
print(f"Avg: {avg_salary.as_py():.0f}, Max: {max_salary.as_py():.0f}")

# Нулевое копирование между Pandas и Arrow
import pandas as pd
df = batch.to_pandas()  # zero-copy где возможно
back = pa.Table.from_pandas(df)
```

Arrow Flight — RPC-протокол для передачи Arrow-данных между системами со скоростями ~10 Гбит/с.

---

## 3. ClickHouse: колоночная СУБД для реального времени

### 3.1 Архитектура ClickHouse

ClickHouse (Яндекс, 2016, open source) — колоночная СУБД, оптимизированная для аналитических запросов в реальном времени с высокой скоростью вставки.

**Ключевые особенности:**
- MergeTree движок: данные вставляются в «parts» и асинхронно сливаются (как LSM-tree)
- Сортировка по primary key внутри part: Range scan эффективен
- Sparse index: не полный индекс, а индекс с гранулярностью 8192 строк (granule)
- Параллельное исполнение: задействует все ядра CPU
- Материализованные представления: инкрементальная агрегация при вставке

### 3.2 MergeTree: основной движок

```sql
-- Создание таблицы на MergeTree движке
CREATE TABLE events (
    event_date  Date,
    event_time  DateTime,
    user_id     UInt64,
    event_type  LowCardinality(String),  -- dictionary encoding автоматически
    session_id  String,
    page_url    String,
    duration_ms UInt32,
    country     LowCardinality(String),
    device_type LowCardinality(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)   -- партиционирование по месяцам
ORDER BY (event_date, user_id, event_time)  -- сортировка = primary index
SETTINGS index_granularity = 8192;

-- Вставка в пакетах (не по одной строке!)
INSERT INTO events
SELECT
    today() AS event_date,
    now() AS event_time,
    number AS user_id,
    arrayElement(['click','view','purchase'], rand()%3+1) AS event_type,
    generateUUIDv4() AS session_id,
    concat('/page/', toString(rand()%100)) AS page_url,
    rand()%5000 AS duration_ms,
    arrayElement(['RU','US','DE','FR'], rand()%4+1) AS country,
    arrayElement(['mobile','desktop','tablet'], rand()%3+1) AS device_type
FROM numbers(10000000);
```

### 3.3 Запросы ClickHouse

```sql
-- Анализ воронки: clickhouse выполняет это за секунды на миллиардах строк
SELECT
    country,
    device_type,
    countIf(event_type = 'view')     AS views,
    countIf(event_type = 'click')    AS clicks,
    countIf(event_type = 'purchase') AS purchases,
    purchases * 100.0 / views        AS conversion_pct,
    avgIf(duration_ms, event_type = 'view') AS avg_view_duration
FROM events
WHERE event_date >= today() - 30
GROUP BY country, device_type
ORDER BY purchases DESC
LIMIT 20;

-- EXPLAIN для анализа плана
EXPLAIN indexes=1
SELECT count() FROM events WHERE user_id = 12345;
-- ClickHouse использует sparse index, читает только 1 granule (8192 строк)
-- вместо полного сканирования

-- Материализованное представление для предагрегации
CREATE MATERIALIZED VIEW events_daily_mv
ENGINE = SummingMergeTree()
PARTITION BY event_date
ORDER BY (event_date, country, event_type)
POPULATE
AS SELECT
    event_date,
    country,
    event_type,
    count()      AS event_count,
    uniq(user_id) AS unique_users
FROM events
GROUP BY event_date, country, event_type;

-- Запрос к MV мгновенный, данные уже агрегированы
SELECT * FROM events_daily_mv WHERE event_date = today() - 1;
```

### 3.4 Специальные функции ClickHouse

```sql
-- Probabilistic data structures
SELECT uniq(user_id) AS hll_count          -- HyperLogLog: быстрый approx count distinct
FROM events WHERE event_date = today();

-- Quantiles без сортировки всего датасета
SELECT quantilesTDigest(0.50, 0.90, 0.95, 0.99)(duration_ms) AS latency_percentiles
FROM events WHERE event_type = 'view';

-- arrayFunctions: работа с массивами в SQL
SELECT
    user_id,
    groupArray(event_type) AS event_sequence,  -- собираем в массив
    arrayFilter(x -> x = 'purchase', event_sequence) AS purchases
FROM events
WHERE event_date = today()
GROUP BY user_id
HAVING has(event_sequence, 'purchase')
LIMIT 10;

-- Window functions
SELECT
    user_id,
    event_time,
    event_type,
    lagInFrame(event_type) OVER (PARTITION BY user_id ORDER BY event_time) AS prev_event,
    dateDiff('second', lagInFrame(event_time) OVER (PARTITION BY user_id ORDER BY event_time), event_time) AS gap_seconds
FROM events
WHERE event_date = today()
ORDER BY user_id, event_time;
```

---

## 4. Google BigQuery: serverless OLAP

### 4.1 Архитектура Dremel

BigQuery основан на внутреннем движке Google Dremel (2010). Ключевые особенности архитектуры:

**Separation of compute and storage**: данные хранятся в Capacitor (колоночный формат в Colossus/GFS), вычисления выполняются на эластичном кластере из тысяч нод.

**Tree execution**: запрос выполняется деревом серверов: корень (mixer) → intermediate nodes → leaf nodes, каждая leaf читает свою порцию данных.

**Dremel nested model**: нативная поддержка вложенных структур (RECORD/ARRAY) без JOIN через Dremel's nested columnar encoding.

### 4.2 BigQuery Storage Format: Capacitor

Capacitor — проприетарный колоночный формат BigQuery:
- Хранит данные в зашифрованном виде на Colossus
- Автоматическая кластеризация по часто используемым фильтрам
- Автоматическое партиционирование по дате

```sql
-- BigQuery: партиционирование и кластеризация
CREATE TABLE project.dataset.events
PARTITION BY DATE(event_timestamp)
CLUSTER BY country, event_type
AS
SELECT * FROM project.dataset.raw_events;

-- Запрос с partition pruning и cluster pruning
SELECT COUNT(*) 
FROM project.dataset.events
WHERE DATE(event_timestamp) = '2024-03-15'  -- читает только одну партицию
  AND country = 'RU'                          -- cluster pruning в партиции
  AND event_type = 'purchase';

-- INFORMATION_SCHEMA для мониторинга
SELECT
    creation_time,
    query,
    total_bytes_processed,
    total_slot_ms,
    cache_hit
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE DATE(creation_time) = CURRENT_DATE
ORDER BY total_bytes_processed DESC
LIMIT 10;
```

### 4.3 BigQuery ML: SQL для машинного обучения

```sql
-- Обучение модели прямо в BigQuery без Python
CREATE OR REPLACE MODEL project.dataset.purchase_predictor
OPTIONS (
    model_type = 'LOGISTIC_REG',
    input_label_cols = ['will_purchase']
) AS
SELECT
    session_duration_sec,
    pages_viewed,
    device_type,
    country,
    hour_of_day,
    CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END AS will_purchase
FROM project.dataset.sessions
WHERE DATE(session_date) BETWEEN '2024-01-01' AND '2024-02-28';

-- Предсказания
SELECT
    user_id,
    predicted_will_purchase,
    predicted_will_purchase_probs
FROM ML.PREDICT(
    MODEL project.dataset.purchase_predictor,
    (SELECT * FROM project.dataset.sessions WHERE session_date = CURRENT_DATE)
);
```

---

## 5. DuckDB: in-process OLAP

### 5.1 Архитектура DuckDB

DuckDB (2019, CWI Amsterdam) — встраиваемая колоночная СУБД, работающая внутри процесса Python/R/Java без отдельного сервера. Аналог SQLite, но для OLAP.

**Внутреннее устройство:**
- Vectorized query engine (Morsel-Driven Parallelism)
- Adaptive radix tree (ART) индексы
- Execution engine на C++ с шаблонной специализацией под типы данных
- Прямое чтение Parquet, CSV, JSON, Arrow без загрузки в память

### 5.2 Возможности DuckDB

```python
import duckdb
import pandas as pd

con = duckdb.connect()

# Создание таблицы из CSV без загрузки в память
con.execute("""
    CREATE TABLE sales AS 
    SELECT * FROM read_csv_auto('sales_*.csv')
""")

# Запрос к нескольким Parquet файлам через glob
result = con.execute("""
    SELECT 
        year(sale_date) AS year,
        month(sale_date) AS month,
        category,
        SUM(revenue) AS total,
        AVG(revenue) AS avg_order
    FROM read_parquet('data/sales/year=*/month=*/*.parquet')
    WHERE country IN ('RU', 'DE', 'US')
    GROUP BY ALL
    ORDER BY year, month, total DESC
""").df()

# Window functions
result = con.execute("""
    SELECT 
        user_id,
        sale_date,
        revenue,
        SUM(revenue) OVER (
            PARTITION BY user_id 
            ORDER BY sale_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_revenue,
        revenue / SUM(revenue) OVER () AS share_of_total
    FROM sales
""").df()

# PIVOT (DuckDB 0.8+)
pivot_result = con.execute("""
    PIVOT sales
    ON category
    USING SUM(revenue)
    GROUP BY year(sale_date)
""").df()

# Экспорт в несколько форматов
con.execute("COPY sales TO 'output.parquet' (FORMAT PARQUET, CODEC 'ZSTD')")
con.execute("COPY sales TO 'output.json' (FORMAT JSON, ARRAY true)")
```

### 5.3 DuckDB vs Pandas для анализа данных

```python
import duckdb
import pandas as pd
import time

# Генерация тестовых данных
df = pd.DataFrame({
    'user_id': range(5_000_000),
    'category': ['A','B','C','D'] * 1_250_000,
    'revenue': [float(i % 1000) for i in range(5_000_000)],
    'date': pd.date_range('2020-01-01', periods=5_000_000, freq='1min')
})

# Pandas подход
start = time.perf_counter()
result_pandas = (
    df[df['revenue'] > 500]
    .groupby('category')
    .agg({'revenue': ['sum', 'mean', 'count']})
)
pandas_time = time.perf_counter() - start

# DuckDB подход
start = time.perf_counter()
result_duckdb = duckdb.execute("""
    SELECT category, 
           SUM(revenue) AS total, 
           AVG(revenue) AS avg, 
           COUNT(*) AS cnt
    FROM df  -- прямой доступ к Pandas DataFrame!
    WHERE revenue > 500
    GROUP BY category
""").df()
duckdb_time = time.perf_counter() - start

print(f"Pandas: {pandas_time:.3f}s, DuckDB: {duckdb_time:.3f}s")
# DuckDB обычно в 2-5x быстрее на агрегациях за счёт векторизации
```

---

## 6. Форматы хранения: Parquet и ORC

### 6.1 Apache Parquet

Parquet (2013, Twitter + Cloudera) — открытый колоночный формат для хранения на диске. Стал стандартом для Data Lake.

**Структура файла:**
```
Parquet File:
├── Row Group 0 (128MB по умолчанию)
│   ├── Column Chunk: user_id
│   │   ├── Page 0 (dictionary)
│   │   ├── Page 1 (data, RLE encoded)
│   │   └── Statistics: min/max/null_count
│   ├── Column Chunk: event_type
│   │   └── ...
│   └── Column Chunk: revenue
│       └── ...
├── Row Group 1
│   └── ...
└── File Footer (schema, row group metadata)
```

**Statistics для predicate pushdown:**
```python
import pyarrow.parquet as pq

# Чтение метаданных без загрузки данных
metadata = pq.read_metadata('sales.parquet')
for rg in range(metadata.num_row_groups):
    for col in range(metadata.num_columns):
        stats = metadata.row_group(rg).column(col).statistics
        print(f"Column {col}: min={stats.min}, max={stats.max}")

# Predicate pushdown: пропуск Row Groups не соответствующих фильтру
table = pq.read_table(
    'sales.parquet',
    filters=[
        ('sale_date', '>=', '2024-01-01'),
        ('country', '=', 'RU')
    ]
)
# Читаются только Row Groups, где min(sale_date) <= 2024-01-01
# и max(sale_date) >= 2024-01-01, и встречается 'RU'
```

### 6.2 Сравнение форматов

| Формат | Тип | Сжатие | Скорость записи | Скорость чтения | Поддержка |
|--------|-----|--------|----------------|----------------|-----------|
| CSV | Row | Нет | Высокая | Низкая | Везде |
| JSON | Row | Нет | Высокая | Низкая | Везде |
| Avro | Row | DEFLATE | Высокая | Средняя | Hadoop |
| Parquet | Column | SNAPPY/ZSTD | Средняя | Высокая | Широкая |
| ORC | Column | ZLIB | Средняя | Высокая | Hive/Spark |
| Arrow | Column | LZ4 | Очень высокая | Очень высокая | In-memory |

---

## 7. Сжатие и его влияние на производительность

### 7.1 Алгоритмы сжатия в OLAP-системах

```python
import zstandard as zstd
import snappy
import lz4.frame
import time
import os

# Симуляция типичных колоночных данных
import random
data = bytes(','.join(['RU' if random.random() > 0.3 else random.choice(['US','DE','FR'])
                       for _ in range(1_000_000)]).encode())

def benchmark_codec(name, compress_fn, decompress_fn, data):
    # Сжатие
    start = time.perf_counter()
    compressed = compress_fn(data)
    compress_time = time.perf_counter() - start
    
    # Декомпрессия
    start = time.perf_counter()
    decompressed = decompress_fn(compressed)
    decompress_time = time.perf_counter() - start
    
    ratio = len(data) / len(compressed)
    print(f"{name}: ratio={ratio:.1f}x, "
          f"compress={compress_time*1000:.1f}ms, "
          f"decompress={decompress_time*1000:.1f}ms")

# Parquet по умолчанию использует Snappy (баланс скорость/сжатие)
benchmark_codec("Snappy", snappy.compress, snappy.decompress, data)

# ZSTD: лучше сжимает, слабо медленнее
cctx = zstd.ZstdCompressor(level=3)
dctx = zstd.ZstdDecompressor()
benchmark_codec("ZSTD-3", cctx.compress, dctx.decompress, data)

# LZ4: максимальная скорость, меньшее сжатие
benchmark_codec("LZ4", lz4.frame.compress, lz4.frame.decompress, data)
```

### 7.2 Выбор кодека под задачу

- **Snappy** — баланс скорость/сжатие, по умолчанию в Parquet
- **ZSTD** — лучшее сжатие при сопоставимой скорости декомпрессии, рекомендуется для архивов
- **LZ4** — максимальная скорость декомпрессии, для горячих данных
- **GZIP** — максимальное сжатие, медленно, для холодного хранения

---

## 8. Сравнение ClickHouse, BigQuery и DuckDB

| Параметр | ClickHouse | BigQuery | DuckDB |
|---------|------------|----------|--------|
| Тип | Self-hosted СУБД | Serverless cloud | In-process |
| Масштабирование | Горизонтальное | Автоматическое | Вертикальное |
| Скорость вставки | Очень высокая | Средняя | Средняя |
| Скорость запросов | Очень высокая | Высокая | Высокая (1 узел) |
| Задержка запроса | Секунды | 1-10 секунд | Миллисекунды |
| Цена | Инфраструктура | По объёму данных | Бесплатно |
| Сложность операций | Средняя | Минимальная | Нет |
| Потоковая вставка | Да (Kafka, NATS) | Да (Pub/Sub) | Нет |
| Подходит для | Реальное время, Яндекс-масштаб | Аналитика, ML | Локальный анализ, ETL |

---

## Заключение

Колоночное хранение — не просто другой способ расположения байт на диске. Это изменение всей архитектуры обработки данных: от посекторного чтения к считыванию только нужных колонок, от интерпретирующего исполнения к векторизованному с SIMD, от отдельных значений к сжатым потокам однотипных данных.

ClickHouse демонстрирует, что можно обрабатывать миллиарды строк в секунду в реальном времени. BigQuery показывает, что колоночная аналитика может быть serverless и масштабироваться автоматически. DuckDB доказывает, что мощный OLAP-движок умещается в библиотеку и запускается прямо в Python-процессе.

Выбор инструмента определяется операционными требованиями: если нужна аналитика в реальном времени на собственном железе — ClickHouse; если нужна elasticity без операционной нагрузки — BigQuery или Snowflake; если нужен быстрый анализ файлов на ноутбуке — DuckDB.

---

## Библиография

1. Abadi, D., et al. (2008). Column-Stores vs. Row-Stores: How Different Are They Really? *SIGMOD 2008*. ACM.
2. Melnik, S., et al. (2010). Dremel: Interactive Analysis of Web-Scale Datasets. *VLDB 2010*.
3. Raasveldt, M., & Mühleisen, H. (2019). DuckDB: an Embeddable Analytical Database. *SIGMOD 2019*.
4. ClickHouse Documentation. (2024). ClickHouse Reference. https://clickhouse.com/docs
5. Vohra, D. (2016). *Apache Parquet: Columnar Storage for the People*. Apress.
6. Lamb, A., et al. (2012). The Vertica Analytic Database: C-Store 7 Years Later. *VLDB 2012*.
7. Zeng, K., et al. (2021). *Arrow: A Cross-Language Development Platform for In-Memory Data*. Apache Software Foundation.
8. Stonebraker, M., et al. (2005). C-Store: A Column-Oriented DBMS. *VLDB 2005*.
