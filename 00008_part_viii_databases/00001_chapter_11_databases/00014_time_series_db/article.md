# Базы данных временных рядов: InfluxDB, TimescaleDB, Prometheus

## Введение

Современные системы мониторинга и IoT-устройства генерируют данные непрерывно: температура сервера каждую секунду, курс акций каждые 100 миллисекунд, метрики HTTP-запросов с тегами по эндпоинтам. Это **временны́е ряды** (time series) — последовательности значений, упорядоченных по времени.

Реляционные СУБД справятся с хранением таких данных, но неэффективно: INSERT на каждое измерение — дорогой. Запрос «среднее по минутам за последние 6 часов» с GROUP BY по миллионам строк — медленный. Для временны́х рядов существуют специализированные СУБД с оптимизированным хранением и богатыми операторами агрегации по временным окнам.

---

## 1. Характеристики данных временных рядов

### 1.1 Паттерны доступа

Временны́е ряды имеют специфические свойства:

1. **Immutability**: измерения не редактируются. Запись к прошлому не изменяется (кроме исправления ошибок).
2. **Append-heavy**: новые данные всегда добавляются, старые не изменяются.
3. **Time-based queries**: почти все запросы фильтруются по временно́му диапазону.
4. **High write rate**: тысячи-миллионы точек в секунду.
5. **Bulk read**: чтение больших диапазонов для агрегации.
6. **Temporal locality**: недавние данные запрашиваются намного чаще.
7. **Data retention**: старые данные можно удалять или downsample-ить.

### 1.2 Модель данных

**Метрика (metric)**: именованная последовательность значений. Например, `cpu_usage`.

**Теги (tags/labels)**: неизменяемые строковые метки для группировки и фильтрации. Например, `host=server01, region=eu-west`.

**Поле (field)**: числовое значение в момент времени. Например, `value=84.5`.

```
Точка временного ряда:
  timestamp: 2024-03-15T14:23:45.123Z
  metric:    cpu_usage
  tags:      {host: "server01", region: "eu-west", cpu: "0"}
  fields:    {value: 84.5, user: 71.2, system: 13.3}
```

### 1.3 Challenges для реляционных СУБД

```sql
-- В PostgreSQL: 1 миллиард строк в таблице metrics
CREATE TABLE metrics (
    ts     TIMESTAMPTZ NOT NULL,
    metric VARCHAR(100),
    host   VARCHAR(100),
    value  FLOAT
);

-- Запрос медленный без специализированных оптимизаций:
SELECT 
    time_bucket('1 minute', ts) AS minute,
    avg(value) AS avg_cpu
FROM metrics
WHERE metric = 'cpu_usage'
  AND host = 'server01'
  AND ts > NOW() - INTERVAL '1 hour'
GROUP BY minute
ORDER BY minute;
-- Без партиционирования: full scan 1B строк
```

---

## 2. InfluxDB: специализированная TSDB

### 2.1 Архитектура InfluxDB

InfluxDB (InfluxData, 2013) — написана на Go, специализируется на TSDB. Версии 1.x и 2.x используют TSM (Time-Structured Merge Tree) движок — вариант LSM-tree, оптимизированный для временны́х рядов.

**TSM Tree:**
1. WAL (Write-Ahead Log) + in-memory Cache
2. При заполнении Cache → flush в TSM file (иммутабельный)
3. Фоновый compaction: несколько TSM → один, с удалением устаревших данных

**Хранение в TSM**:
- Данные сортированы по (series key, timestamp)
- Каждая series = уникальная комбинация (metric + tags)
- Внутри series → delta + RLE encoding для временных меток + gorilla encoding для float значений

### 2.2 InfluxDB 2.x: Flux query language

```python
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
import time

client = InfluxDBClient(
    url="http://localhost:8086",
    token="my-token",
    org="my-org"
)

write_api = client.write_api(write_options=SYNCHRONOUS)
query_api = client.query_api()

# Запись точек данных
def record_metrics(host: str, cpu: float, memory: float):
    points = [
        Point("system_metrics")
        .tag("host", host)
        .tag("region", "eu-west")
        .field("cpu_percent", cpu)
        .field("memory_percent", memory)
        .time(datetime.utcnow(), WritePrecision.MILLISECONDS)
    ]
    write_api.write(bucket="monitoring", record=points)

# Симуляция записи метрик
import random
for i in range(100):
    record_metrics(
        host=f"server-{i % 5 + 1:02d}",
        cpu=random.uniform(10, 90),
        memory=random.uniform(30, 95)
    )

# Flux запрос: среднее CPU по хостам за последний час
flux_query = '''
from(bucket: "monitoring")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "system_metrics")
  |> filter(fn: (r) => r._field == "cpu_percent")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
  |> yield(name: "mean_cpu")
'''

tables = query_api.query(flux_query, org="my-org")
for table in tables:
    for record in table.records:
        print(f"Host: {record.values.get('host')}, "
              f"Time: {record.get_time()}, "
              f"CPU: {record.get_value():.1f}%")

# Аномалия-детекция: значения выше порога
anomaly_query = '''
from(bucket: "monitoring")
  |> range(start: -6h)
  |> filter(fn: (r) => r._measurement == "system_metrics" and r._field == "cpu_percent")
  |> map(fn: (r) => ({ r with is_anomaly: r._value > 80.0 }))
  |> filter(fn: (r) => r.is_anomaly == true)
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 20)
'''

# Downsampling: hourly averages сохраняются в отдельный bucket
downsample_task = '''
option task = {
    name: "hourly_downsample",
    every: 1h,
}

from(bucket: "monitoring")
  |> range(start: -task.every)
  |> filter(fn: (r) => r._measurement == "system_metrics")
  |> aggregateWindow(every: 1h, fn: mean)
  |> to(bucket: "monitoring_hourly", org: "my-org")
'''

client.close()
```

### 2.3 Line Protocol: формат вставки

InfluxDB Line Protocol — компактный текстовый формат:
```
<measurement>[,<tag_key>=<tag_value>...] <field_key>=<field_value>[,<field_key>=<field_value>...] [<timestamp>]

cpu,host=server01,region=eu cpu_percent=84.5,user=71.2,system=13.3 1709823625000000000
```

Timestamp в наносекундах (или другой precision). Поддерживается batch-вставка: несколько строк через `\n`.

---

## 3. TimescaleDB: PostgreSQL для временных рядов

### 3.1 Расширение PostgreSQL

TimescaleDB (2017) — расширение PostgreSQL, добавляющее hypertable — автоматически партиционированную таблицу по времени.

```sql
-- Создание hypertable
CREATE TABLE metrics (
    ts          TIMESTAMPTZ NOT NULL,
    host        TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value       DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('metrics', 'ts', 
                          chunk_time_interval => INTERVAL '1 day');

-- Автоматически создаются chunks (партиции) по дням
-- Запрос за вчера читает ТОЛЬКО вчерашний chunk

-- Вставка данных (стандартный INSERT)
INSERT INTO metrics (ts, host, metric_name, value)
VALUES 
    (NOW(), 'server01', 'cpu_percent', 84.5),
    (NOW(), 'server01', 'memory_percent', 67.3),
    (NOW(), 'server02', 'cpu_percent', 23.1);

-- time_bucket: агрегация по временным окнам (killer feature)
SELECT 
    time_bucket('5 minutes', ts) AS bucket,
    host,
    AVG(value)      AS avg_cpu,
    MAX(value)      AS max_cpu,
    MIN(value)      AS min_cpu,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY value) AS p95_cpu
FROM metrics
WHERE metric_name = 'cpu_percent'
  AND ts > NOW() - INTERVAL '1 hour'
GROUP BY bucket, host
ORDER BY bucket, host;

-- first/last: получить первое/последнее значение в окне
SELECT 
    time_bucket('1 hour', ts) AS hour,
    host,
    first(value, ts) AS opening_cpu,
    last(value, ts)  AS closing_cpu
FROM metrics
WHERE metric_name = 'cpu_percent'
GROUP BY hour, host;

-- Непрерывные агрегаты (Continuous Aggregates)
-- Автоматически обновляемые материализованные представления
CREATE MATERIALIZED VIEW metrics_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', ts) AS hour,
    host,
    metric_name,
    AVG(value) AS avg_value,
    MAX(value) AS max_value,
    COUNT(*) AS samples
FROM metrics
GROUP BY hour, host, metric_name
WITH NO DATA;

-- Политика обновления
SELECT add_continuous_aggregate_policy('metrics_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- Запрос к материализованному представлению (мгновенный)
SELECT * FROM metrics_hourly
WHERE hour > NOW() - INTERVAL '7 days'
  AND metric_name = 'cpu_percent'
ORDER BY hour;

-- Data retention policy: автоматическое удаление старых данных
SELECT add_retention_policy('metrics', INTERVAL '90 days');

-- Compression: автоматическое сжатие старых chunks
ALTER TABLE metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'host, metric_name',
    timescaledb.compress_orderby = 'ts DESC'
);

SELECT add_compression_policy('metrics', INTERVAL '7 days');
-- Chunks старше 7 дней сжимаются автоматически: 90-98% сжатие
```

### 3.2 Преимущества TimescaleDB

- Полная совместимость с PostgreSQL: JOIN с любыми реляционными таблицами
- Стандартный SQL, инструменты PostgreSQL (pg_dump, EXPLAIN, etc.)
- Сжатие с columnar компрессией: 90-97% для типичных TSDB данных
- Continuous aggregates: инкрементальная агрегация без ETL
- Иерархические непрерывные агрегаты: минута → час → день

```python
import psycopg2
from datetime import datetime, timedelta
import random

conn = psycopg2.connect("postgresql://user:pass@localhost/metrics_db")
cur = conn.cursor()

# Пакетная вставка через COPY для максимальной скорости
from io import StringIO
import csv

def bulk_insert_metrics(measurements: list):
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter='\t')
    for ts, host, metric, value in measurements:
        writer.writerow([ts.isoformat(), host, metric, value])
    buffer.seek(0)
    
    cur.copy_from(
        buffer, 
        'metrics',
        columns=('ts', 'host', 'metric_name', 'value'),
        sep='\t'
    )
    conn.commit()

# Генерация тестовых данных: 1 миллион точек
now = datetime.utcnow()
measurements = [
    (
        now - timedelta(seconds=i),
        f'server-{i % 10 + 1:02d}',
        random.choice(['cpu_percent', 'memory_percent', 'disk_io']),
        random.uniform(0, 100)
    )
    for i in range(1_000_000)
]

bulk_insert_metrics(measurements)
print(f"Inserted {len(measurements)} measurements")
```

---

## 4. Prometheus: метрики для мониторинга

### 4.1 Pull-модель и service discovery

Prometheus (SoundCloud → CNCF, 2012) — система мониторинга с pull-моделью: Prometheus сам опрашивает метрики у сервисов через HTTP endpoint `/metrics`.

```python
# Экспортёр метрик на Python с prometheus_client
from prometheus_client import start_http_server, Gauge, Counter, Histogram
import random
import time

# Определение метрик
REQUEST_COUNT = Counter('http_requests_total',
                        'Total HTTP request count',
                        labelnames=['method', 'endpoint', 'status_code'])

REQUEST_DURATION = Histogram('http_request_duration_seconds',
                             'HTTP request duration in seconds',
                             labelnames=['method', 'endpoint'],
                             buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0])

ACTIVE_CONNECTIONS = Gauge('active_connections',
                           'Number of active connections')

QUEUE_SIZE = Gauge('queue_size', 'Current queue size',
                   labelnames=['queue_name'])

def process_request(method: str, endpoint: str):
    start = time.time()
    
    ACTIVE_CONNECTIONS.inc()
    try:
        # Симуляция обработки запроса
        time.sleep(random.expovariate(10))  # exponential ~100ms
        status = '200' if random.random() > 0.05 else '500'
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, 
                             status_code=status).inc()
        return status
    finally:
        duration = time.time() - start
        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
        ACTIVE_CONNECTIONS.dec()

# Запуск HTTP-сервера для scraping
start_http_server(8000)

# Симуляция нагрузки
while True:
    for endpoint in ['/api/users', '/api/products', '/api/orders']:
        for method in ['GET', 'POST']:
            process_request(method, endpoint)
            QUEUE_SIZE.labels(queue_name='orders').set(random.randint(0, 50))
    time.sleep(0.1)
```

### 4.2 PromQL: язык запросов

```promql
# Мгновенные векторы
http_requests_total  # последнее значение всех метрик

# Rate: скорость изменения счётчика за 5 минут
rate(http_requests_total[5m])

# Процент ошибок
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
* 100

# P95 latency из гистограммы
histogram_quantile(0.95, 
    rate(http_request_duration_seconds_bucket[5m]))

# Запросы по эндпоинту, топ-5
topk(5, sum by(endpoint) (rate(http_requests_total[5m])))

# Алерт: p99 > 1 секунды
histogram_quantile(0.99, 
    sum by(le, endpoint) (
        rate(http_request_duration_seconds_bucket[5m])
    )
) > 1

# irate: instant rate (последние два sample)
irate(http_requests_total{status_code="200"}[5m])

# Прогноз через linear_prediction
predict_linear(disk_usage_bytes[1h], 4 * 3600) > disk_total_bytes
# "Через 4 часа диск заполнится"
```

### 4.3 Архитектура Prometheus

```
Prometheus Server
├── Scrape Engine: периодически опрашивает targets
├── TSDB: локальное хранение (по умолчанию 15 дней)
│   ├── WAL (2 часа в памяти)
│   └── Chunks (2 часа → disk block)
├── Rule Engine: вычисление recording rules и alerting rules
└── HTTP API: запросы PromQL

Targets (экспортёры):
├── node_exporter: CPU, memory, disk, network OS-метрики
├── blackbox_exporter: HTTP, TCP, DNS probes
├── mysqld_exporter, postgres_exporter
└── Кастомные экспортёры (/metrics endpoint)

AlertManager:
├── Получает алерты от Prometheus
├── Группировка, подавление дублей (inhibition)
└── Роутинг → Slack, PagerDuty, email
```

### 4.4 Хранение Prometheus: Thanos/Cortex для long-term

TSDB Prometheus хранит данные локально, по умолчанию 15 дней. Для долгосрочного хранения используются:

**Thanos**: загружает Prometheus-блоки в объектное хранилище (S3/GCS), обеспечивает глобальный view нескольких Prometheus-инстансов.

**Cortex / Mimir**: горизонтально масштабируемый Prometheus-совместимый backend с object storage.

**VictoriaMetrics**: более эффективная альтернатива с высокой скоростью вставки и меньшим потреблением памяти.

---

## 5. Gorilla encoding: сжатие временных рядов

### 5.1 Алгоритм Gorilla (Facebook/Meta, 2015)

Gorilla — специализированное сжатие для TSDB, обеспечивающее коэффициент сжатия ~12x при скорости декомпрессии CPU-bound.

**Сжатие timestamps (delta-of-delta)**:
- Первый timestamp: полное значение (64 бит)
- Каждый следующий: разность (delta) от предыдущего
- Разности разностей (delta-of-delta): для регулярных рядов = 0 → кодируется 1 битом!

```
Timestamps: [1700000000, 1700000060, 1700000120, 1700000180]
Deltas:     [1700000000, 60, 60, 60]
Δ-of-Δ:    [1700000000, 60, 0, 0]  ← большинство = 0 → 1 бит каждый
```

**Сжатие float values (XOR encoding)**:
- XOR текущего и предыдущего значения
- Если XOR = 0 → 1 бит '0'
- Если XOR != 0 → хранить только значимые биты XOR (leading zeros + trailing zeros опускаются)

```python
import struct

def gorilla_encode_doubles(values: list) -> bytes:
    """Упрощённая реализация Gorilla float encoding"""
    if not values:
        return b''
    
    result_bits = []
    prev_bits = struct.unpack('Q', struct.pack('d', values[0]))[0]
    
    # Первое значение — полностью
    result_bits.extend(f'{prev_bits:064b}')
    
    for v in values[1:]:
        curr_bits = struct.unpack('Q', struct.pack('d', v))[0]
        xor = prev_bits ^ curr_bits
        
        if xor == 0:
            result_bits.append('0')  # 1 бит
        else:
            xor_str = f'{xor:064b}'
            leading = len(xor_str) - len(xor_str.lstrip('0'))
            trailing = len(xor_str) - len(xor_str.rstrip('0'))
            meaningful = 64 - leading - trailing
            
            # Флаг + leading zeros (6 бит) + meaningful bits count (6 бит) + данные
            result_bits.append('1')
            result_bits.extend(f'{leading:06b}')
            result_bits.extend(f'{meaningful:06b}')
            result_bits.extend(xor_str[leading:leading+meaningful])
        
        prev_bits = curr_bits
    
    # Упаковка в байты
    bit_string = ''.join(result_bits)
    padded = bit_string + '0' * (8 - len(bit_string) % 8)
    return bytes(int(padded[i:i+8], 2) for i in range(0, len(padded), 8))

# Типичные метрики CPU: значения меняются мало
cpu_values = [84.5 + i * 0.01 for i in range(1000)]
encoded = gorilla_encode_doubles(cpu_values)
original_size = len(cpu_values) * 8  # 8 байт на float64
print(f"Original: {original_size} bytes")
print(f"Encoded: {len(encoded)} bytes")
print(f"Ratio: {original_size/len(encoded):.1f}x")
```

---

## 6. Сравнение TSDB-решений

| Параметр | InfluxDB | TimescaleDB | Prometheus | VictoriaMetrics |
|---------|---------|-------------|------------|----------------|
| Язык запросов | Flux/InfluxQL | SQL | PromQL | MetricsQL |
| Хранение | TSM | PostgreSQL chunks | local TSDB | custom |
| Масштабирование | Clustering (платно) | Горизонтальное (платно) | Thanos/Cortex | встроенное |
| Совместимость SQL | Нет | Полная | Нет | Нет |
| Cardinality limit | Средняя | Высокая | Ограниченная | Высокая |
| Лучше для | IoT, high write | SQL + TSDB вместе | K8s monitoring | Prometheus-совместимость |
| Open Source | Ограниченно (v1) | Ядро OSS | Полностью | Полностью |

---

## 7. Паттерны проектирования TSDB-систем

### 7.1 Cardinality: главная опасность

**Cardinality** — количество уникальных series (уникальных комбинаций тегов). Cardinality explosion — основная причина OOM в Prometheus.

```
Плохо: метрика с userId как тегом
http_requests_total{user_id="u-1001", endpoint="/api/products"}
# 1M пользователей × 100 эндпоинтов = 100M series → OOM

Хорошо: userId в recording rule или агрегировать заранее
http_requests_total{endpoint="/api/products"}  # только 100 series
```

### 7.2 Retention тиерирование

```
Hot tier (0-7 дней):   SSD, полное разрешение (1s)
Warm tier (7-90 дней): HDD, downsampled (1m averages)
Cold tier (90d+):      Object storage (S3), 1h averages

InfluxDB Flux:
// Записываем в downsampled bucket
option task = {name: "downsample_1m", every: 1m}
from(bucket: "metrics_raw")
  |> range(start: -task.every)
  |> aggregateWindow(every: 1m, fn: mean)
  |> to(bucket: "metrics_1m")
```

---

## Заключение

Базы данных временных рядов решают фундаментальную проблему: как эффективно хранить и запрашивать миллиарды измерений с временными метками. Специализированные структуры данных (TSM, columnar chunks, Gorilla encoding) дают 10-100x выигрыш против реляционных СУБД для этого специфического паттерна доступа.

TimescaleDB — выбор, когда нужна совместимость с SQL и JOIN с реляционными данными. InfluxDB — для IoT с высокой частотой записи. Prometheus — стандарт де-факто для мониторинга Kubernetes/микросервисов.

Ключевые инсайты: cardinality — главный враг производительности TSDB; downsampling позволяет долго хранить агрегированные исторические данные; Gorilla encoding даёт ~12x сжатие при работе с реальными метриками.

---

## Библиография

1. Pelkonen, T., et al. (2015). Gorilla: A Fast, Scalable, In-Memory Time Series Database. *VLDB 2015*.
2. TimescaleDB. (2017). *Timescale: Scale PostgreSQL for Time-Series Data*. https://www.timescale.com/
3. Prometheus Authors. (2015). *Prometheus: Monitoring System & Time Series Database*. https://prometheus.io/
4. Beyer, B., et al. (Eds.) (2016). *Site Reliability Engineering*. O'Reilly Media. Chapter 10 (Practical Alerting).
5. Bjornsson, B. (2022). *Database Internals*. O'Reilly. Chapter 7 (Log-Structured Storage).
6. Turnbull, J. (2018). *Monitoring with Prometheus*. Turnbull Press.
7. InfluxData. (2023). *The Time Series Data Platform*. https://www.influxdata.com/
