# P50/P95/P99 Latency — среднее почти всегда врёт; смотреть надо хвосты

«Средняя задержка нашего API — 50 миллисекунд». Звучит хорошо. Но что если 1% пользователей ждёт 10 секунд? При миллионе запросов в день это 10,000 пользователей с ужасным опытом — каждый день. Именно поэтому среднее — плохая метрика для latency. Нужно смотреть на перцентили, особенно на хвосты распределения.

## Почему среднее врёт

Рассмотрим реальный сценарий:

```python
import statistics
import random

# Симуляция задержек API (в миллисекундах)
latencies = [
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,  # Быстрые запросы: 90%
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    10, 12, 11, 13, 10, 11, 12, 10, 11, 13,
    # Медленные запросы: 10% — обращение к БД без кеша
    500, 450, 600, 800, 1200, 1500, 2000, 900, 3000, 10000,
]

mean = statistics.mean(latencies)
median = statistics.median(latencies)
latencies_sorted = sorted(latencies)
p95 = latencies_sorted[int(len(latencies) * 0.95)]
p99 = latencies_sorted[int(len(latencies) * 0.99)]

print(f"Mean (среднее):   {mean:.0f}ms")    # 134ms — выглядит прилично
print(f"P50 (медиана):    {median:.0f}ms")  # 11ms — быстро!
print(f"P95:              {p95:.0f}ms")     # 1200ms — проблема
print(f"P99:              {p99:.0f}ms")     # 5500ms — катастрофа

# Среднее 134ms звучит как "небольшая задержка"
# На самом деле 10% пользователей ждут более секунды!
```

**Почему среднее скрывает проблемы:**
- Среднее чувствительно к outliers: одно значение 10,000ms «тянет» среднее вверх
- При бимодальном распределении среднее не соответствует ни одному из режимов
- Среднее не показывает форму распределения

## Что такое перцентиль

**Перцентиль P(n)** — значение, ниже которого находится n% наблюдений.

- **P50 (медиана)** — 50% запросов выполнены за это время или быстрее
- **P95** — 95% запросов выполнены за это время; 5% медленнее
- **P99** — 99% запросов выполнены за это время; 1% медленнее
- **P99.9 (three-nines)** — 99.9% запросов выполнены; 0.1% медленнее

```python
def calculate_percentiles(latencies: list[float]) -> dict:
    """Вычислить ключевые перцентили."""
    sorted_lat = sorted(latencies)
    n = len(sorted_lat)
    
    def percentile(p: float) -> float:
        index = int(n * p / 100)
        return sorted_lat[min(index, n-1)]
    
    return {
        'p50':   percentile(50),
        'p75':   percentile(75),
        'p90':   percentile(90),
        'p95':   percentile(95),
        'p99':   percentile(99),
        'p99.9': percentile(99.9),
        'p100':  sorted_lat[-1],
        'mean':  sum(sorted_lat) / n,
    }
```

## Tail Latency и почему она важна

**Tail latency** — задержки в "хвосте" распределения (P99, P99.9, P99.99). Исследования Google и Amazon показывают, что хвостовая задержка значительно влияет на пользовательский опыт.

**Причины tail latency:**
1. **JVM GC паузы** — stop-the-world garbage collection
2. **Конкуренция за блокировки** — lock contention при высокой нагрузке
3. **Context switches** — ОС переключает процесс в неудачный момент
4. **Cache misses** — данные вытеснены из L1/L2/L3 кеша
5. **Network jitter** — переменная задержка в сети
6. **Disk I/O** — случайный обмен данными с медленным диском

```python
# Пример: GC пауза в Python (аналог JVM)
import gc
import time

def measure_gc_impact():
    """Демонстрация влияния GC на tail latency."""
    
    latencies = []
    
    for i in range(10000):
        start = time.perf_counter_ns()
        
        # Аллоцируем много объектов
        data = [{'key': j, 'value': j * 2} for j in range(100)]
        result = sum(d['value'] for d in data)
        
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies.append(elapsed_us)
        
        # GC иногда срабатывает во время этих операций
        if i % 1000 == 0:
            gc.collect()  # Принудительный GC для демонстрации
    
    percs = calculate_percentiles(latencies)
    for k, v in percs.items():
        print(f"{k:8}: {v:.1f} мкс")
    
    # P50 может быть 50мкс, P99 — 5000мкс (100x разница из-за GC)
```

## Fan-Out Amplification

Критически важная концепция для микросервисной архитектуры: если страница делает N параллельных запросов, итоговая задержка определяется медленным из них.

```python
import asyncio
import random
import time

async def simulate_request(service_name: str, p99_ms: float) -> float:
    """Симулируем запрос к сервису с реалистичным распределением."""
    r = random.random()
    if r < 0.99:
        delay = random.uniform(5, 15)  # Быстрые запросы
    else:
        delay = p99_ms  # 1% медленных
    
    await asyncio.sleep(delay / 1000)
    return delay

async def page_load_fanout(num_services: int = 10) -> dict:
    """
    Загрузка страницы = N параллельных запросов.
    Итоговая latency = max(all responses).
    """
    start = time.perf_counter()
    
    # Параллельно делаем N запросов
    tasks = [
        simulate_request(f"service_{i}", p99_ms=100.0)
        for i in range(num_services)
    ]
    results = await asyncio.gather(*tasks)
    
    total_ms = (time.perf_counter() - start) * 1000
    
    return {
        'total_ms': total_ms,        # max(all), не sum
        'individual': results,
        'max': max(results),
        'min': min(results),
    }

# Теоретический анализ:
# Если каждый из N сервисов имеет P99 = 100ms,
# вероятность что хотя бы один медленный:
# P(at least one slow) = 1 - P(all fast) = 1 - (0.99)^N

import math
for n in [1, 5, 10, 20, 50]:
    p_slow = 1 - (0.99 ** n)
    print(f"N={n:2d} сервисов: P(страница медленная) = {p_slow:.1%}")

# N=1:  P = 1.0%
# N=5:  P = 4.9%
# N=10: P = 9.6%
# N=20: P = 18.2%
# N=50: P = 39.5% (!!)
```

Вывод: при 50 параллельных запросах почти половина страниц будет медленной, даже если каждый отдельный сервис работает нормально!

## Coordinated Omission: ошибка бенчмарков

**Coordinated Omission** — систематическая ошибка при нагрузочном тестировании, описанная Гилом Тене (Gil Tene). Большинство инструментов бенчмаркинга её допускают.

```
Проблема:
Сценарий: клиент отправляет 1 запрос в секунду
Клиент ждёт ответа перед отправкой следующего

Timeline:
  t=0.0s: Send request → Server busy (1.0s latency) → Receive at 1.0s
  t=1.0s: Send request → Server fast  (0.01s)       → Receive at 1.01s
  t=1.01s: Send next...

Что записывает naive benchmark:
  Request 1: latency = 1.0s
  Request 2: latency = 0.01s
  
Что на самом деле:
  Если клиент хотел отправить запрос в t=1.0s, но ждал ответа,
  то реальная latency запроса 2 = 1.01s (не 0.01s!)
  Потому что пользователь ждал с t=1.0s по t=1.01s.

Naive benchmark: P99 = 1.0s
Correct benchmark: P99 = 1.01s (но паттерн задержек другой)
```

**Правильные инструменты для нагрузочного тестирования:**

```bash
# wrk2 — учитывает coordinated omission
# -R 1000: 1000 req/sec (независимо от latency)
wrk2 -t 4 -c 100 -d 60s -R 1000 http://api.example.com/

# Вывод:
#   Latency Distribution
#      50%    12.05ms
#      75%    18.32ms
#      90%    45.12ms
#      99%   523.45ms
#    99.9%  2134.12ms

# vegeta — ещё один правильный инструмент
echo "GET http://api.example.com/" | vegeta attack -rate=1000 -duration=60s | \
    vegeta report -type=hdrplot | tee report.txt
```

## HDR Histogram: эффективное хранение перцентилей

**HDR Histogram (High Dynamic Range Histogram)** — структура данных для эффективного хранения распределений с широким диапазоном значений.

Проблема наивного подхода: хранить все значения latency в списке — дорого по памяти при высоком трафике ($1000\ \text{req/s} \times 24$ часа = 86,400,000 значений).

```python
# Упрощённая концепция HDR Histogram
# Хранит значения с точностью 3 значимых цифры,
# но не все значения подряд

class SimpleHDRHistogram:
    """
    Упрощённая версия HDR Histogram концепции.
    Реальная реализация: https://github.com/HdrHistogram/HdrHistogram
    """
    
    def __init__(self, max_value: int, significant_figures: int = 3):
        self._data = {}
        self._max = max_value
        self._sig_figs = significant_figures
        self._count = 0
        self._total = 0
    
    def record_value(self, value: float) -> None:
        """Записать значение с округлением до significant_figures."""
        # Округляем до нужной точности
        magnitude = len(str(int(value)))
        factor = 10 ** max(0, magnitude - self._sig_figs)
        bucket = int(value / factor) * factor
        
        self._data[bucket] = self._data.get(bucket, 0) + 1
        self._count += 1
        self._total += value
    
    def percentile(self, p: float) -> float:
        """Получить перцентиль."""
        target = self._count * p / 100
        cumulative = 0
        
        for bucket in sorted(self._data.keys()):
            cumulative += self._data[bucket]
            if cumulative >= target:
                return bucket
        
        return max(self._data.keys())
    
    def mean(self) -> float:
        return self._total / self._count if self._count > 0 else 0

# Реальное использование: библиотека HdrHistogram
# pip install hdrh
from hdrh.histogram import HdrHistogram

hist = HdrHistogram(1, 3600000, 3)  # 1мкс - 1час, 3 significant figures

# Записываем latency в микросекундах
import time
for _ in range(100000):
    start = time.perf_counter_ns()
    # ... ваш код ...
    elapsed_us = (time.perf_counter_ns() - start) // 1000
    hist.record_value(elapsed_us)

print(f"P50:   {hist.get_value_at_percentile(50)} мкс")
print(f"P99:   {hist.get_value_at_percentile(99)} мкс")
print(f"P99.9: {hist.get_value_at_percentile(99.9)} мкс")
print(f"Max:   {hist.get_max_value()} мкс")
```

**Преимущества HDR Histogram:**
- Фиксированный размер в памяти (~40KB для диапазона 1мс-1ч)
- Точность 3 значимые цифры (0.1% ошибка)
- Быстрое добавление и чтение (O(1))
- Поддержка merge гистограмм (для агрегации по инстансам)

## SLI, SLO, SLA: формализация требований к latency

```yaml
# SLI (Service Level Indicator): измеримая метрика
# "Процент запросов с latency < 100ms"

# SLO (Service Level Objective): цель
# "99% запросов должны выполняться за < 100ms"
# "P99 latency должна быть < 500ms"

# SLA (Service Level Agreement): юридическое соглашение
# "Если SLO нарушены > X часов в месяц → возврат денег"

# Пример SLO документа:
slo:
  service: "order-api"
  window: "30d"
  
  indicators:
    - name: "availability"
      description: "Процент успешных запросов"
      threshold: 99.9%  # Error budget: 0.1% = 43.2 мин/мес
    
    - name: "latency_p50"
      description: "Медианная latency"
      threshold_ms: 50
    
    - name: "latency_p99"
      description: "99-й перцентиль latency"
      threshold_ms: 500
      
    - name: "latency_p999"
      description: "99.9-й перцентиль latency"
      threshold_ms: 2000
```

## RED Метод: Rate, Errors, Duration

**RED метод** (Tom Wilkie) — простой фреймворк для мониторинга сервисов через три ключевых метрики:

- **Rate** — количество запросов в секунду
- **Errors** — количество ошибочных запросов (% ошибок)
- **Duration** — latency запросов (распределение, не среднее!)

```promql
# Prometheus: RED метрики для API сервиса

# Rate (запросов/секунду)
rate(http_requests_total{service="order-api"}[5m])

# Error rate (% ошибок)
rate(http_requests_total{service="order-api", status=~"5.."}[5m])
/
rate(http_requests_total{service="order-api"}[5m]) * 100

# Duration (latency перцентили)
# ВАЖНО: используем histogram, не summary!
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{service="order-api"}[5m]))
  by (le)
)

# P50
histogram_quantile(0.50,
  sum(rate(http_request_duration_seconds_bucket{service="order-api"}[5m]))
  by (le)
)
```

```python
# Правильная инструментация HTTP сервиса для перцентилей
from prometheus_client import Histogram, Counter, start_http_server
import time

# Используем histogram (не summary!) — поддерживает federation и агрегацию
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    labelnames=['method', 'endpoint', 'status'],
    buckets=[
        0.005, 0.01, 0.025, 0.05, 0.075,  # 5ms - 75ms
        0.1, 0.25, 0.5, 0.75,              # 100ms - 750ms
        1.0, 2.5, 5.0, 7.5, 10.0          # 1s - 10s
    ]
)

REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    labelnames=['method', 'endpoint', 'status']
)

class LatencyMiddleware:
    async def __call__(self, request, call_next):
        start = time.perf_counter()
        status_code = 500
        
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            labels = {
                'method': request.method,
                'endpoint': request.url.path,
                'status': str(status_code)
            }
            REQUEST_LATENCY.labels(**labels).observe(duration)
            REQUEST_COUNT.labels(**labels).inc()
```

## Как измерять latency правильно

### wrk2: правильный нагрузочный тест

```bash
# wrk2 учитывает coordinated omission
# -R: target request rate (requests/second) — независимо от latency!
wrk2 -t 4 -c 100 -d 60s -R 1000 \
    --latency \
    http://api.example.com/

# Вывод с перцентилями:
#   Latency Distribution (HdrHistogram)
#      50%    12.05ms
#      75%    18.32ms
#      90%    45.12ms
#      95%    89.23ms
#      99%   523.45ms
#    99.9%  2134.12ms
#   99.99%  8432.00ms
```

### vegeta: нагрузочный тест с правильными перцентилями

```bash
# vegeta: attack + report с HDR Histogram
echo "GET http://api.example.com/products" | \
    vegeta attack -rate=500 -duration=30s | \
    tee results.bin | \
    vegeta report

# Детальный отчёт:
vegeta report -type=json results.bin | jq '{
  latencies: .latencies,
  success: .success,
  status_codes: .status_codes
}'

# Сохранить HDR гистограмму для анализа
vegeta report -type=hdrplot < results.bin > latency.hdrplot
```

### gatling: нагрузочное тестирование с правильной статистикой

```scala
// Gatling simulation
class MySimulation extends Simulation {
  val httpProtocol = http.baseUrl("http://api.example.com")
  
  val scn = scenario("API Load Test")
    .exec(http("Get products")
      .get("/products")
      .check(status.is(200))
    )
  
  setUp(
    scn.inject(
      constantUsersPerSec(100) during (60 seconds)  // 100 req/s
    )
  ).protocols(httpProtocol)
    .assertions(
      global.successfulRequests.percent.is(99),
      global.responseTime.percentile3.lt(500),  // P99 < 500ms
      global.responseTime.percentile4.lt(2000)  // P99.9 < 2s
    )
}
```

## Практический пример: SLO alerting в Prometheus

```yaml
# Alerting rules для нарушения SLO
groups:
  - name: latency_slo
    interval: 1m
    rules:
      # P99 latency превысила 500ms
      - alert: HighP99Latency
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket{
              service="order-api"
            }[5m])) by (le)
          ) > 0.5
        for: 5m  # Алерт если нарушение > 5 минут
        labels:
          severity: warning
        annotations:
          summary: "P99 latency exceeds SLO"
          description: "P99 latency is {{ $value | humanizeDuration }}, SLO is 500ms"
      
      # Нарастающее нарушение error budget
      - alert: ErrorBudgetBurnRateTooHigh
        expr: |
          (
            rate(http_requests_total{service="order-api", status=~"5.."}[1h])
            /
            rate(http_requests_total{service="order-api"}[1h])
          ) > 0.001  # > 0.1% error rate
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Error budget burn rate too high"
```

## Гистограмма vs Summary в Prometheus

```python
# Summary: вычисляет перцентили локально, нельзя агрегировать
from prometheus_client import Summary

# НЕ используйте для latency если несколько инстансов!
REQUEST_SUMMARY = Summary(
    'request_latency_seconds',
    'Request latency',
    ['endpoint']
)

# Проблема: P99 инстанса A и P99 инстанса B нельзя сложить для получения
# суммарного P99 по всем инстансам

# Histogram: агрегируется правильно
REQUEST_HISTOGRAM = Histogram(
    'request_duration_seconds',
    'Request duration',
    ['endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# PromQL: histogram_quantile агрегирует корректно
# histogram_quantile(0.99, sum(rate(request_duration_seconds_bucket[5m])) by (le))
```

## Заключение

Перцентили — единственный правильный способ анализа latency:

- **P50 (медиана)** — типичный опыт пользователя
- **P95/P99** — опыт "везучих" медленных пользователей
- **P99.9/P99.99** — worst-case сценарии, важны для SLO

**Ключевые правила:**
1. Никогда не используйте только среднее для latency
2. Всегда смотрите на хвосты: P99, P99.9
3. При fan-out: итоговый P99 = 1 - (1-P99)^N
4. Избегайте Coordinated Omission в бенчмарках (используйте wrk2, vegeta)
5. Используйте HDR Histogram или Prometheus Histogram (не Summary)
6. Формализуйте требования в SLO

Правильное измерение latency — это разница между «API работает нормально» и «99% пользователей счастливы, а 1% смотрит на таймаут».

## Литература

1. **Tene, Gil** — «How NOT to Measure Latency» (talk): https://www.youtube.com/watch?v=lJ8ydIuPFeU
2. **HdrHistogram** — «A High Dynamic Range Histogram»: https://hdrhistogram.github.io/HdrHistogram/
3. **Gregg, Brendan** — «Latency SLOs Done Right». Netflix Tech Blog
4. **Google SRE Book** — «Service Level Objectives», Chapter 4: https://sre.google/sre-book/service-level-objectives/
5. **Wilkie, Tom** — «The RED Method: How to instrument your services» (2018): https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/
6. **Prometheus Documentation** — «Histograms and summaries»: https://prometheus.io/docs/practices/histograms/
7. **Dean, Jeff; Barroso, Luiz André** — «The Tail at Scale». Communications of the ACM, 2013
8. **wrk2** — «A constant throughput, correct latency recording variant of wrk»: https://github.com/giltene/wrk2
9. **Vegeta** — «HTTP load testing tool»: https://github.com/tsenart/vegeta
10. **Gatling** — «Gatling Open-Source Load Testing»: https://gatling.io/docs/
