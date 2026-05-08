# USE и RED методы — фреймворки для диагностики систем

Когда системный инженер получает алерт «API отвечает медленно», перед ним встаёт вопрос: с чего начать диагностику? CPU? Диск? Сеть? База данных? Без системного подхода диагностика превращается в случайный перебор. USE метод Брендана Грегга и RED метод Тома Уилки — структурированные фреймворки, которые превращают диагностику производительности из искусства в инженерию.

## Проблема диагностики без фреймворка

```bash
# Типичная «случайная» диагностика:
# 1. Смотрим CPU (первое что приходит в голову)
top
# CPU 30% — нормально. Ладно, смотрим память...

# 2. Смотрим память
free -h
# 8GB из 16GB — нормально. Смотрим диск...

# 3. Смотрим диск
df -h
# 60% использовано — нормально. Смотрим сеть...

# 4. Смотрим сеть
netstat -s
# Много пакетов, но ничего подозрительного...

# 5. Смотрим логи
tail -f /var/log/app.log
# "Connection timeout to database" — AHA! Вот оно!

# Потрачено: 30 минут. Нашли бы за 5 минут с фреймворком.
```

## USE Метод: Utilization, Saturation, Errors

**USE Method** разработан Бренданом Греггом (Brendan Gregg, Netflix). Суть: для каждого **ресурса** системы проверяем три метрики:

- **U (Utilization)** — насколько ресурс занят (% времени)
- **S (Saturation)** — есть ли очередь к ресурсу (работы больше, чем ресурс может обработать)
- **E (Errors)** — есть ли ошибки ресурса

### Ресурсы для анализа

```
┌─────────────────┬────────────────────────────┬───────────────────────────────────────────────────┐
│ Ресурс          │ Утилизация (U)             │ Насыщение (S)               │ Ошибки (E)          │
├─────────────────┼────────────────────────────┼─────────────────────────────┼─────────────────────┤
│ CPU             │ % времени не в idle        │ run queue length > #cores  │ machine check exceptions│
│ Память          │ % использованной RAM       │ swap I/O, page faults      │ OOM events           │
│ Сетевой интерфейс│ % пропускной способности  │ tx/rx queue drops          │ packet errors, drops │
│ Диск (I/O)      │ % времени в I/O операциях │ I/O queue depth (avgqu-sz) │ disk errors          │
│ File Descriptors│ % от max открытых FD       │ ожидание FD (rare)         │ EMFILE ошибки        │
└─────────────────┴────────────────────────────┴─────────────────────────────┴─────────────────────┘
```

### Checklist USE для быстрой диагностики

```bash
#!/bin/bash
# use_checklist.sh — систематическая проверка по USE методу

echo "=== USE Method Checklist ==="
echo ""
echo "--- CPU ---"
# Утилизация CPU (каждого ядра)
mpstat -P ALL 1 3
# Насыщение CPU (runqueue)
vmstat 1 3 | awk '{print $1, $2}'  # r (runqueue), b (blocked)
echo ""

echo "--- Memory ---"
# Утилизация памяти
free -h
# Насыщение (swap активность)
vmstat 1 3 | awk '{print $7, $8}'  # si (swap-in), so (swap-out)
# Если si/so > 0 регулярно — система под давлением памяти
echo ""

echo "--- Disk ---"
# Утилизация + насыщение
iostat -x 1 3
# Ключевые поля:
# %util: утилизация диска (> 90% — проблема)
# await: среднее время ожидания I/O (мс) — latency
# avgqu-sz: средняя длина очереди (насыщение)
# r_await, w_await: latency чтения/записи
echo ""

echo "--- Network ---"
# Утилизация сетевого интерфейса
sar -n DEV 1 3
# Насыщение (dropped packets)
cat /proc/net/dev
# Ошибки
ip -s link show eth0 | grep -A 3 "RX:\|TX:"
echo ""

echo "--- File Descriptors ---"
# Текущее/максимальное количество FD
cat /proc/sys/fs/file-nr
# Или для конкретного процесса:
ls /proc/<PID>/fd | wc -l
cat /proc/<PID>/limits | grep "open files"
```

### CPU: детальная диагностика по USE

```bash
# === UTILIZATION ===
# Общая утилизация CPU
top  # или htop

# Утилизация по процессам
pidstat 1 5

# Утилизация по типам работы
perf stat -a -e cycles,instructions,cache-misses sleep 5
# user%: время в user space
# sys%: время в kernel (может указывать на проблемы с syscalls)
# iowait%: ожидание I/O (если высокое — проблема с диском/сетью)

# === SATURATION ===
# Длина очереди на CPU (run queue)
vmstat 1 | head -5
# r = число процессов в run queue
# Если r > число CPU ядер постоянно — CPU насыщен

# Средняя нагрузка (load average)
uptime
# 1.00 = 100% одного ядра
# На 4-ядерной системе: нормально до 4.0

# === ERRORS ===
# MCE (Machine Check Exceptions) — аппаратные ошибки CPU
mcelog --client
# или
dmesg | grep -i "machine check\|mce"
```

### Memory: диагностика по USE

```bash
# === UTILIZATION ===
free -h
#              total  used   free  shared  buff/cache  available
# Mem:         15.5G  8.2G  2.1G   0.5G       5.2G       6.8G
# Важно: "available" (не "free") = реально доступно приложению

# Детально по типам
cat /proc/meminfo | grep -E "MemTotal|MemFree|Buffers|Cached|SwapTotal|SwapFree"

# === SATURATION ===
# Swap активность (главный признак давления памяти)
vmstat 1 | awk 'NR>2{print "swap_in="$7, "swap_out="$8}'
# si (swap-in) > 0 постоянно = память НАСЫЩЕНА

# Page fault statistics
sar -B 1 5
# majflt/s: major page faults (данные читаются с диска) = критично
# minflt/s: minor page faults (нормально)

# OOM events
dmesg | grep "Out of memory\|oom_kill"

# === ERRORS ===
# ECC ошибки памяти (если ECC RAM)
edac-util -s
```

### Disk: диагностика по USE

```bash
# === UTILIZATION + SATURATION ===
# iostat: основной инструмент
iostat -x 1 5

# Вывод:
# Device   r/s   w/s  rkB/s  wkB/s  await  r_await  w_await  %util
# sda      0.0  234.5   0.0   1874.0  2.34    2.10     2.35    45.3

# %util > 90%: диск утилизирован
# await > 20ms: диск перегружен
# avgqu-sz > 1: очередь к диску (насыщение)

# iotop: топ процессов по disk I/O
iotop -o  # -o = только активные процессы

# biolatency (eBPF): распределение latency I/O
sudo biolatency 10

# === ERRORS ===
# SMART данные (аппаратные ошибки диска)
smartctl -a /dev/sda | grep -E "Reallocated|Pending|Uncorrectable"
# Reallocated_Sector_Ct > 0 = диск начинает деградировать
# Current_Pending_Sector > 0 = нестабильные секторы

# Kernel ошибки диска
dmesg | grep -iE "error|failed|ata|scsi" | tail -20
```

### Network: диагностика по USE

```bash
# === UTILIZATION ===
# Использование пропускной способности
sar -n DEV 1 5
# rxkB/s, txkB/s: скорость приёма/передачи
# Например: 100Gbps = ~12,500 MB/s

# Или через ip:
ip -s link show eth0

# === SATURATION ===
# Dropped packets = очередь переполнена
netstat -s | grep "receive buffer errors\|dropped"

# TX queue drops
ip -s link show eth0 | grep -A 2 "TX:"

# Детальная статистика очередей
cat /proc/net/softnet_stat
# Колонка 2: dropped packets (насыщение входящей очереди)

# === ERRORS ===
# Физические ошибки (коллизии, CRC ошибки)
ethtool -S eth0 | grep -i "error\|drop\|miss"

# TCP ошибки
netstat -s | grep -E "segments retransmited|bad segments"
ss -s
```

## RED Метод: Rate, Errors, Duration

**RED Method** создан Томом Уилки (Tom Wilkie, Grafana Labs). В отличие от USE (для ресурсов), RED применяется для **сервисов** (микросервисов, API):

- **R (Rate)** — количество запросов в секунду
- **E (Errors)** — количество/процент ошибочных запросов
- **D (Duration)** — latency запросов (распределение)

### Реализация RED метрик

```python
# FastAPI + Prometheus: полная RED инструментация
from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time

app = FastAPI()

# Rate + Errors: Counter с лейблом status
HTTP_REQUESTS = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

# Duration: Histogram с правильными bucket'ами
HTTP_REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[
        0.001, 0.005, 0.01, 0.025, 0.05,   # 1ms - 50ms
        0.1, 0.25, 0.5, 0.75, 1.0,          # 100ms - 1s
        2.5, 5.0, 7.5, 10.0, float('inf')   # 2.5s - inf
    ]
)

# Middleware для автоматического сбора всех метрик
@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    start_time = time.perf_counter()
    
    # Нормализуем endpoint (убираем ID из пути)
    endpoint = _normalize_endpoint(request.url.path)
    
    response = None
    status_code = 500
    
    try:
        response = await call_next(request)
        status_code = response.status_code
    finally:
        duration = time.perf_counter() - start_time
        
        # Rate + Errors
        HTTP_REQUESTS.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
        
        # Duration
        HTTP_REQUEST_DURATION.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
    
    return response

def _normalize_endpoint(path: str) -> str:
    """Убираем ID из пути для группировки метрик."""
    import re
    # /api/orders/123 → /api/orders/:id
    path = re.sub(r'/\d+', '/:id', path)
    # /api/users/user-uuid-here → /api/users/:id
    path = re.sub(r'/[0-9a-f-]{36}', '/:uuid', path)
    return path

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### RED в PromQL

```promql
# === RATE ===
# Запросов в секунду (5-минутное скользящее окно)
rate(http_requests_total{service="order-api"}[5m])

# По endpoint
sum(rate(http_requests_total{service="order-api"}[5m])) by (endpoint)

# === ERRORS ===
# Процент ошибок (5xx)
sum(rate(http_requests_total{service="order-api", status_code=~"5.."}[5m]))
/
sum(rate(http_requests_total{service="order-api"}[5m]))
* 100

# Абсолютное количество ошибок
sum(rate(http_requests_total{service="order-api", status_code=~"[45].."}[5m]))

# === DURATION ===
# P50 latency
histogram_quantile(0.5,
  sum(rate(http_request_duration_seconds_bucket{service="order-api"}[5m]))
  by (le)
)

# P99 latency
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{service="order-api"}[5m]))
  by (le)
)

# Среднее время ответа (для сравнения с перцентилями)
sum(rate(http_request_duration_seconds_sum{service="order-api"}[5m]))
/
sum(rate(http_request_duration_seconds_count{service="order-api"}[5m]))
```

## Golden Signals (Google SRE)

Google SRE Book описывает четыре **Golden Signals** — основные метрики для мониторинга любого сервиса:

1. **Latency** — время обработки запроса (успешного и ошибочного отдельно!)
2. **Traffic** — нагрузка на систему (req/s, bytes/s, transactions/s)
3. **Errors** — процент ошибочных запросов
4. **Saturation** — насколько ресурсы близки к пределу

Сравнение с USE и RED:

```
Golden Signals ≈ RED + часть USE

USE (для ресурсов):
  Utilization = Saturation (в Golden Signals)
  Saturation = Saturation
  Errors = Errors

RED (для сервисов):
  Rate = Traffic (в Golden Signals)
  Errors = Errors
  Duration = Latency

Golden Signals:
  Latency = Duration (RED)
  Traffic = Rate (RED)
  Errors = Errors (RED/USE)
  Saturation = Saturation (USE)
```

```promql
# Полный набор Golden Signals алертов

# 1. Latency Alert
- alert: HighLatency
  expr: |
    histogram_quantile(0.99,
      sum(rate(http_request_duration_seconds_bucket[5m])) by (service, le)
    ) > 1.0
  for: 5m
  annotations:
    summary: "P99 latency > 1s for {{ $labels.service }}"

# 2. Traffic anomaly (внезапный рост или падение)
- alert: TrafficAnomaly
  expr: |
    abs(
      rate(http_requests_total[5m]) - 
      rate(http_requests_total[1h] offset 24h)  # Вчера в это время
    ) / rate(http_requests_total[1h] offset 24h) > 0.5
  for: 10m
  annotations:
    summary: "Traffic changed >50% compared to same time yesterday"

# 3. Error rate Alert
- alert: HighErrorRate
  expr: |
    sum(rate(http_requests_total{status_code=~"5.."}[5m])) by (service)
    /
    sum(rate(http_requests_total[5m])) by (service) > 0.01
  for: 5m
  annotations:
    summary: "Error rate > 1% for {{ $labels.service }}"

# 4. Saturation Alert (CPU)
- alert: CPUSaturation
  expr: |
    100 - (avg by (instance) (
      rate(node_cpu_seconds_total{mode="idle"}[5m])
    ) * 100) > 90
  for: 5m
  annotations:
    summary: "CPU utilization > 90%"
```

## Практический пример: диагностика медленного API

```bash
#!/bin/bash
# Систематическая диагностика по USE + RED

SERVICE="order-api"
PID=$(pgrep -f order-api)

echo "=== Диагностика $SERVICE ==="
echo ""

echo "=== RED: Состояние сервиса ==="
# Смотрим в Prometheus/Grafana или через API
curl -s "http://prometheus:9090/api/v1/query" \
    --data-urlencode 'query=rate(http_requests_total{service="order-api"}[5m])' | \
    python3 -c "import sys,json; d=json.load(sys.stdin); 
                print(f'Rate: {float(d[\"data\"][\"result\"][0][\"value\"][1]):.1f} req/s')"

echo ""
echo "=== USE: Ресурсы ==="

echo "--- CPU ---"
# Утилизация: простаивает ли CPU?
top -b -n 1 -p $PID | tail -3
# Насыщение: очередь к CPU
vmstat 1 3 | awk 'NR>2{print "run_queue="$1}'

echo ""
echo "--- Memory ---"
# Утилизация памяти процесса
cat /proc/$PID/status | grep VmRSS
# Насыщение: swap?
vmstat 1 3 | awk 'NR>2{print "swap_in="$7, "swap_out="$8}'

echo ""
echo "--- Network connections ---"
ss -p | grep $PID | awk '{print $1}' | sort | uniq -c | sort -rn

echo ""
echo "--- File descriptors ---"
ls /proc/$PID/fd | wc -l
cat /proc/$PID/limits | grep "open files"

echo ""
echo "--- Database connections ---"
# Сколько соединений к БД открыто?
ss -nt | grep :5432 | wc -l
# Насыщение пула соединений?
```

### Дашборд Grafana для RED метрик

```json
// Grafana dashboard: RED для микросервиса
{
  "panels": [
    {
      "title": "Rate (Requests per second)",
      "type": "graph",
      "targets": [{
        "expr": "sum(rate(http_requests_total{service=\"order-api\"}[5m])) by (endpoint)"
      }]
    },
    {
      "title": "Errors (%)",
      "type": "stat",
      "targets": [{
        "expr": "sum(rate(http_requests_total{service=\"order-api\",status_code=~\"5..\"}[5m])) / sum(rate(http_requests_total{service=\"order-api\"}[5m])) * 100",
        "thresholds": {"steps": [
          {"color": "green", "value": 0},
          {"color": "yellow", "value": 1},
          {"color": "red", "value": 5}
        ]}
      }]
    },
    {
      "title": "Duration (P50/P99 latency)",
      "type": "graph",
      "targets": [
        {
          "expr": "histogram_quantile(0.5, sum(rate(http_request_duration_seconds_bucket{service=\"order-api\"}[5m])) by (le))",
          "legendFormat": "P50"
        },
        {
          "expr": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service=\"order-api\"}[5m])) by (le))",
          "legendFormat": "P99"
        }
      ]
    }
  ]
}
```

## USE vs RED: когда что применять

```
┌──────────────────────────────────────────────────────────────────┐
│  Проблема с производительностью?                                 │
└──────────────────────────────────────────────────────────────────┘
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
    "API работает медленно"   "Диск / CPU / RAM перегружен"
            │                       │
       RED Method               USE Method
     (для сервиса)            (для ресурса)
            │                       │
    Rate: норм?            Utilization: < 70%? ✓
    Errors: норм?          Saturation: queue = 0? ✓
    Duration: P99?         Errors: 0? ✓
            │                       │
    ┌───────┘               ┌───────┘
    │                       │
    ▼                       ▼
Смотрим каждый             Нашли проблему:
сервис в цепочке           CPU сатурирован / swap активен
(через distributed         / диск перегружен
tracing)
```

## Интеграция с Distributed Tracing

USE и RED дают агрегированную картину. Для понимания **конкретного** медленного запроса нужен distributed tracing.

```python
# OpenTelemetry: связываем RED метрики с трейсами
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# После инструментации:
# 1. RED метрики: показывают что P99 = 2s (агрегированно)
# 2. Distributed trace: показывает КОНКРЕТНЫЙ запрос
#    order-api (50ms) → inventory-service (1800ms!) → db (1750ms!)
# Проблема найдена: медленный запрос в БД инвентаря

# Связываем метрику с трейсом через exemplars
HTTP_REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=[...]
)

@app.middleware("http")
async def collect_metrics_with_traces(request: Request, call_next):
    span = trace.get_current_span()
    
    # Exemplar: ссылка на конкретный трейс в гистограмме
    with HTTP_REQUEST_DURATION.labels(...).time() as timer:
        if span.is_recording():
            timer.exemplar = {
                'trace_id': format(span.get_span_context().trace_id, '032x'),
                'span_id': format(span.get_span_context().span_id, '016x'),
            }
        response = await call_next(request)
    
    return response
```

## Заключение

USE и RED — дополняющие друг друга фреймворки:

- **USE** — систематический анализ каждого ресурса (CPU, память, диск, сеть). Идеален для выявления насыщения ресурсов.
- **RED** — мониторинг каждого сервиса по трём ключевым метрикам. Идеален для сервис-ориентированной архитектуры.
- **Golden Signals** — более высокоуровневый взгляд, объединяющий оба подхода.

**Практический алгоритм диагностики:**
1. Проверить RED метрики через Grafana/Prometheus
2. Если проблема с конкретным сервисом → distributed tracing
3. Если системная проблема → USE checklist по ресурсам
4. Если нет очевидной причины → perf/eBPF для глубокого анализа

Систематический подход экономит часы случайного «тыкания в темноте» и даёт воспроизводимый процесс диагностики, которому может следовать любой инженер команды.

## Литература

1. **Gregg, Brendan** — «The USE Method»: https://www.brendangregg.com/usemethod.html
2. **Gregg, Brendan** — «Systems Performance: Enterprise and the Cloud», 2nd ed. Pearson, 2020. ISBN: 978-0136820154
3. **Wilkie, Tom** — «The RED Method: How to instrument your services» (2018): https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/
4. **Google SRE Book** — «Monitoring Distributed Systems», Chapter 6. O'Reilly, 2016: https://sre.google/sre-book/monitoring-distributed-systems/
5. **Prometheus Documentation** — «Metric types»: https://prometheus.io/docs/concepts/metric_types/
6. **Grafana Documentation** — «Best practices for alerting»: https://grafana.com/docs/grafana/latest/alerting/alerting-rules/
7. **OpenTelemetry** — «Observability Primer»: https://opentelemetry.io/docs/concepts/observability-primer/
8. **Beyer, Betsy et al.** — «Site Reliability Engineering: How Google Runs Production Systems». O'Reilly, 2016. ISBN: 978-1491929124
9. **Cindy Sridharan** — «Distributed Systems Observability». O'Reilly, 2018. ISBN: 978-1492033431
10. **Humble, Jez; Farley, David** — «Continuous Delivery». Addison-Wesley, 2010. ISBN: 978-0321601919
