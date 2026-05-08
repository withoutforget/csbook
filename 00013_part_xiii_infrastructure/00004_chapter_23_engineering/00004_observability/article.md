# Логи, метрики и трассировки: три столпа observability

Представьте: в 3 ночи ваша система начинает отвечать медленно. Дашборд Grafana показывает рост latency, но не говорит почему. Вы лезете в логи — их миллионы строк в разных сервисах. Как найти тот единственный запрос, который разбудил вас среди ночи?

Ответ на этот вопрос — это observability. Не просто мониторинг ("работает или нет"), а способность задавать системе произвольные вопросы о её состоянии. Разница принципиальная: мониторинг говорит вам о заранее известных проблемах, observability позволяет исследовать неизвестные.

## Мониторинг vs Observability

**Мониторинг** — это наблюдение за заранее определёнными метриками: CPU > 80%, latency > 500ms, error rate > 1%. Вы знаете, что измерять заранее.

**Observability** — это свойство системы, позволяющее понять её внутреннее состояние по внешним выходным данным. Термин пришёл из теории управления: система observable, если её внутреннее состояние можно вывести из наблюдаемых выходов.

Практически это означает:
- Мониторинг: "API отвечает медленно" (ответ: да/нет)
- Observability: "Почему запросы пользователя Ивана медленно обрабатываются только при обращении к сервису оплаты через мобильное приложение с iOS 17.2?"

Для второго вопроса нужны три столпа: **логи, метрики и трассировки**.

```
              ┌─────────────────────────────────────┐
              │          Observability               │
              │                                      │
              │  ┌────────┐ ┌────────┐ ┌─────────┐  │
              │  │  Logs  │ │Metrics │ │ Traces  │  │
              │  │        │ │        │ │         │  │
              │  │ Что    │ │ Как    │ │  Где    │  │
              │  │произош-│ │ часто  │ │именно   │  │
              │  │  ло    │ │        │ │          │  │
              │  └────────┘ └────────┘ └─────────┘  │
              └─────────────────────────────────────┘
```

## Первый столп: логи

### Plain text vs Structured logging

Традиционный лог выглядит так:
```
2024-01-15 14:23:45 ERROR Failed to process payment for user 42: timeout after 5000ms
```

Это читаемо для человека, но неудобно для машины. Попробуйте написать запрос "найди все ошибки для user_id=42 за последний час в сервисе payment" — придётся разбирать строку регулярными выражениями.

**Structured logging** решает эту проблему, записывая лог как структурированный документ (чаще всего JSON):

```json
{
  "timestamp": "2024-01-15T14:23:45.123Z",
  "level": "ERROR",
  "service": "payment-service",
  "message": "Failed to process payment",
  "user_id": 42,
  "payment_id": "pay_abc123",
  "duration_ms": 5000,
  "error": "timeout",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

Теперь запрос к Elasticsearch или Loki — это просто фильтр по полям.

### Реализация structured logging

**Python с structlog:**

```python
import structlog
import logging
from datetime import datetime

# Настройка structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()  # Вывод в JSON
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()

def process_payment(user_id: int, amount: float, payment_id: str):
    # Привязываем контекст к логгеру
    logger = log.bind(
        user_id=user_id,
        payment_id=payment_id,
        service="payment-service"
    )
    
    logger.info("payment.started", amount=amount)
    
    try:
        result = charge_credit_card(user_id, amount)
        logger.info("payment.completed", 
                   transaction_id=result.transaction_id,
                   duration_ms=result.duration_ms)
        return result
    except TimeoutError as e:
        logger.error("payment.timeout", 
                    duration_ms=5000,
                    error=str(e))
        raise
    except Exception as e:
        logger.exception("payment.failed", error_type=type(e).__name__)
        raise
```

**Go с zerolog:**

```go
package main

import (
    "os"
    "time"
    
    "github.com/rs/zerolog"
    "github.com/rs/zerolog/log"
)

func init() {
    // JSON вывод с метаданными
    zerolog.SetGlobalLevel(zerolog.InfoLevel)
    log.Logger = zerolog.New(os.Stdout).
        With().
        Timestamp().
        Str("service", "payment-service").
        Str("version", "1.2.3").
        Logger()
}

func processPayment(userID int64, amount float64, paymentID string) error {
    start := time.Now()
    logger := log.With().
        Int64("user_id", userID).
        Str("payment_id", paymentID).
        Logger()
    
    logger.Info().Msg("payment.started")
    
    err := chargeCard(userID, amount)
    duration := time.Since(start).Milliseconds()
    
    if err != nil {
        logger.Error().
            Err(err).
            Int64("duration_ms", duration).
            Msg("payment.failed")
        return err
    }
    
    logger.Info().
        Int64("duration_ms", duration).
        Msg("payment.completed")
    return nil
}
```

### Уровни логирования

| Уровень | Когда использовать | Пример |
|---------|-------------------|--------|
| DEBUG | Детальная отладочная информация | SQL-запросы, HTTP-заголовки |
| INFO | Нормальные события бизнес-логики | Пользователь залогинился, заказ создан |
| WARN | Нештатная ситуация, но система работает | Retry #2, deprecated API вызван |
| ERROR | Ошибка, требующая внимания | Не удалось сохранить заказ |
| CRITICAL/FATAL | Система не может продолжать работу | Нет подключения к БД |

Ключевое правило: **уровни должны быть actionable**. Если на WARN не нужно ничего делать — это INFO. Если на ERROR не нужно никого будить — это WARN.

### Log aggregation

В распределённой системе из 50 сервисов с 100 инстансами каждый пишет логи в свой файл. Нужна централизованная система.

**ELK Stack (Elasticsearch, Logstash, Kibana):**

```
Сервисы → Filebeat/Fluentd → Logstash → Elasticsearch → Kibana
```

Logstash pipeline:
```ruby
# /etc/logstash/conf.d/pipeline.conf
input {
  beats {
    port => 5044
  }
}

filter {
  # Парсим JSON-логи
  json {
    source => "message"
  }
  
  # Добавляем геолокацию по IP
  geoip {
    source => "client_ip"
    target => "geoip"
  }
  
  # Вычисляем тип запроса
  mutate {
    add_field => {
      "is_error" => "%{[level]}" == "ERROR" ? "true" : "false"
    }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "app-logs-%{+YYYY.MM.dd}"
  }
}
```

**Grafana Loki** — более легковесная альтернатива, специально для логов (не полнотекстовый индекс как Elasticsearch):

```yaml
# docker-compose.yml для локального стека
version: '3'
services:
  loki:
    image: grafana/loki:2.9.0
    ports: ["3100:3100"]
    command: -config.file=/etc/loki/local-config.yaml
    
  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - /var/log:/var/log
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    
  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
```

```yaml
# promtail-config.yml
scrape_configs:
  - job_name: application
    static_configs:
      - targets:
          - localhost
        labels:
          job: app-logs
          __path__: /var/log/app/*.log
    pipeline_stages:
      - json:
          expressions:
            level: level
            trace_id: trace_id
            user_id: user_id
      - labels:
          level:
          trace_id:
```

LogQL запрос в Loki:
```logql
# Все ошибки сервиса оплаты за последний час
{job="app-logs"} 
  | json 
  | level = "ERROR" 
  | service = "payment-service"
  | line_format "{{.timestamp}} {{.message}} user={{.user_id}}"

# Количество ошибок по сервисам
sum by (service) (
  rate({job="app-logs"} | json | level = "ERROR" [5m])
)
```

## Второй столп: метрики

### Типы метрик

**Counter** — только растёт, никогда не уменьшается. Подходит для счётчиков событий.
```python
requests_total = Counter('http_requests_total', 
                          'Total HTTP requests',
                          ['method', 'endpoint', 'status'])

requests_total.labels(method='GET', endpoint='/api/users', status='200').inc()
```

**Gauge** — может расти и убывать. Для текущих значений.
```python
active_connections = Gauge('db_connections_active', 
                            'Active database connections')
active_connections.set(42)
active_connections.inc()  # +1
active_connections.dec()  # -1
```

**Histogram** — распределение значений по bucket-ам. Для latency.
```python
request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]
)

with request_duration.labels(method='POST', endpoint='/api/orders').time():
    process_order(order)
```

**Summary** — похож на Histogram, но вычисляет квантили на клиенте. Не масштабируется (нельзя агрегировать Summary из разных инстансов). Используйте Histogram.

### Prometheus: pull-модель

Prometheus работает по pull-модели: он сам опрашивает (`scrape`) endpoints метрик. Это даёт преимущества:
- Легко обнаружить "мёртвые" сервисы (нет ответа = проблема)
- Нет необходимости настраивать push в каждом сервисе
- Централизованное управление частотой опроса

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

rule_files:
  - "alerts/*.yml"

scrape_configs:
  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
```

### PromQL запросы

```promql
# Request rate (запросов в секунду за последние 5 минут)
rate(http_requests_total[5m])

# Error rate (доля ошибок)
sum(rate(http_requests_total{status=~"5.."}[5m])) 
  / sum(rate(http_requests_total[5m]))

# 99-й перцентиль latency
histogram_quantile(0.99, 
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service)
)

# Saturation: использование CPU
1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))

# Алёртинг: latency > 500ms
histogram_quantile(0.95, 
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
) > 0.5
```

### Cardinality: главная ловушка метрик

**Cardinality** — это количество уникальных комбинаций label values. Она убивает Prometheus при неправильном использовании.

```python
# ПЛОХО: высокая cardinality
request_duration.labels(
    user_id=user_id,      # миллионы пользователей!
    url=request.url,      # параметры URL уникальны
    ip=client_ip          # миллионы IP
).observe(duration)

# ХОРОШО: низкая cardinality
request_duration.labels(
    service="payment",
    endpoint="/api/orders",  # нормализованный путь, без ID
    method="POST",
    status_class="2xx"
).observe(duration)
```

Правило: **labels должны иметь ограниченное число возможных значений** (десятки, максимум сотни, не тысячи и не миллионы).

Для высокой cardinality данных (user_id, trace_id) используйте трассировки и логи.

## Третий столп: распределённые трассировки

### Проблема: откуда взялась эта задержка?

Запрос в микросервисной архитектуре проходит через десятки сервисов:

```
Клиент → API Gateway → Auth Service → Order Service → Inventory Service
                                           ↓
                                      Payment Service → Fraud Detection
                                           ↓
                                      Notification Service
```

Если итоговый ответ занял 2 секунды, какой именно сервис виноват? Трассировки отвечают на этот вопрос.

### Span и Trace

**Trace** — полный путь одного запроса через систему, идентифицируется `trace_id`.

**Span** — единица работы в рамках трассировки (один HTTP-запрос, один SQL-запрос, одна операция). У каждого span есть:
- `trace_id` — к какой трассировке принадлежит
- `span_id` — уникальный ID
- `parent_span_id` — родительский span (или null для root)
- `operation_name` — что делает span
- `start_time`, `end_time`
- **tags** — пары ключ-значение (HTTP method, status code, DB table)
- **logs** — временные события внутри span

```
trace_id: 4bf92f3577b34da6a3ce929d0e0e4736

span: API-Gateway (0ms - 250ms)
├── span: Auth-Service (5ms - 45ms)  [parent: API-Gateway]
└── span: Order-Service (50ms - 240ms)  [parent: API-Gateway]
    ├── span: DB-query (55ms - 80ms)  [parent: Order-Service]
    ├── span: Inventory-RPC (90ms - 130ms)  [parent: Order-Service]
    └── span: Payment-RPC (140ms - 235ms)  [parent: Order-Service]
        └── span: Fraud-Check (145ms - 220ms)  [parent: Payment-RPC]
```

### Context Propagation

Чтобы связать span-ы в разных сервисах, нужно передавать context через все границы:

**W3C Trace Context** (стандарт):
```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             version  trace-id (128-bit hex)     span-id (64-bit) flags

tracestate: vendor1=value1,vendor2=value2
```

В HTTP-запросах эти заголовки передаются автоматически при использовании OpenTelemetry.

## OpenTelemetry: единый стандарт

До 2019 года каждый vendor (Jaeger, Zipkin, Datadog, Lightstep) имел свой SDK. Переход с одного на другой требовал переписывания кода. OpenTelemetry (OTEL) решил эту проблему: единый API и SDK для всех трёх столпов.

```
Ваш код → OpenTelemetry SDK → OTEL Collector → Jaeger/Tempo/Datadog/...
                                             → Prometheus
                                             → Loki/Elasticsearch
```

### Инструментация с OpenTelemetry (Python)

```python
# requirements.txt
# opentelemetry-api
# opentelemetry-sdk
# opentelemetry-instrumentation-fastapi
# opentelemetry-instrumentation-sqlalchemy
# opentelemetry-exporter-otlp

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
import fastapi

# Настройка Tracer
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint="http://otel-collector:4317")
    )
)
trace.set_tracer_provider(tracer_provider)

# Настройка Metrics
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint="http://otel-collector:4317"),
    export_interval_millis=15000
)
meter_provider = MeterProvider(metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)

# Получаем инструменты
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Метрики
order_counter = meter.create_counter(
    "orders.created",
    description="Number of orders created",
    unit="1"
)
order_duration = meter.create_histogram(
    "order.processing.duration",
    description="Order processing duration",
    unit="ms"
)

app = fastapi.FastAPI()

# Автоматическая инструментация FastAPI (создаёт spans для каждого endpoint)
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)

@app.post("/api/orders")
async def create_order(order: OrderRequest):
    # Получаем текущий span (созданный FastAPIInstrumentor)
    current_span = trace.get_current_span()
    current_span.set_attribute("user.id", order.user_id)
    current_span.set_attribute("order.items_count", len(order.items))
    
    start_time = time.monotonic()
    
    # Создаём дочерний span для бизнес-логики
    with tracer.start_as_current_span("validate_inventory") as span:
        for item in order.items:
            span.set_attribute(f"item.{item.sku}.quantity", item.quantity)
        available = await check_inventory(order.items)
        if not available:
            span.set_status(trace.StatusCode.ERROR, "Insufficient inventory")
            raise HTTPException(status_code=409, detail="Out of stock")
    
    with tracer.start_as_current_span("charge_payment") as span:
        span.set_attribute("payment.amount", order.total_amount)
        try:
            payment = await process_payment(order)
            span.set_attribute("payment.transaction_id", payment.id)
        except PaymentError as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR)
            raise
    
    # Сохраняем в БД (SQLAlchemyInstrumentor создаст span автоматически)
    saved_order = await save_order(order, payment)
    
    duration_ms = (time.monotonic() - start_time) * 1000
    order_counter.add(1, {"status": "created", "region": order.region})
    order_duration.record(duration_ms, {"region": order.region})
    
    return saved_order
```

### OpenTelemetry Collector

OTEL Collector — это центральный компонент: принимает телеметрию от сервисов и отправляет в несколько backends.

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 1s
    send_batch_size: 1024
  
  # Фильтруем health check spans
  filter:
    spans:
      exclude:
        match_type: regexp
        attributes:
          - key: http.url
            value: ".*/health.*"
  
  # Добавляем атрибуты окружения
  resource:
    attributes:
      - key: environment
        value: production
        action: insert

exporters:
  # Трассировки → Jaeger
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true
  
  # Метрики → Prometheus
  prometheus:
    endpoint: "0.0.0.0:8889"
  
  # Логи → Loki
  loki:
    endpoint: http://loki:3100/loki/api/v1/push

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, filter, resource]
      exporters: [jaeger]
    
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
    
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [loki]
```

### Инструментация Go-сервиса

```go
package main

import (
    "context"
    "time"
    
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/codes"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
    "go.opentelemetry.io/otel/sdk/trace"
    semconv "go.opentelemetry.io/otel/semconv/v1.21.0"
)

var tracer = otel.Tracer("payment-service")

func initTracer(ctx context.Context) (*trace.TracerProvider, error) {
    exporter, err := otlptracegrpc.New(ctx,
        otlptracegrpc.WithEndpoint("otel-collector:4317"),
        otlptracegrpc.WithInsecure(),
    )
    if err != nil {
        return nil, err
    }
    
    tp := trace.NewTracerProvider(
        trace.WithBatcher(exporter),
        trace.WithResource(resource.NewWithAttributes(
            semconv.SchemaURL,
            semconv.ServiceName("payment-service"),
            semconv.ServiceVersion("1.2.3"),
            attribute.String("environment", "production"),
        )),
    )
    otel.SetTracerProvider(tp)
    return tp, nil
}

func (s *PaymentService) ProcessPayment(ctx context.Context, req *PaymentRequest) (*PaymentResponse, error) {
    ctx, span := tracer.Start(ctx, "payment.process",
        trace.WithAttributes(
            attribute.Int64("user.id", req.UserID),
            attribute.Float64("payment.amount", req.Amount),
            attribute.String("payment.currency", req.Currency),
        ),
    )
    defer span.End()
    
    // Вызов внешнего fraud detection
    ctx, fraudSpan := tracer.Start(ctx, "fraud.check")
    fraudResult, err := s.fraudDetector.Check(ctx, req)
    if err != nil {
        fraudSpan.RecordError(err)
        fraudSpan.SetStatus(codes.Error, err.Error())
        fraudSpan.End()
        return nil, fmt.Errorf("fraud check failed: %w", err)
    }
    fraudSpan.SetAttributes(attribute.Bool("fraud.detected", fraudResult.IsFraud))
    fraudSpan.End()
    
    if fraudResult.IsFraud {
        span.SetStatus(codes.Error, "fraud detected")
        return nil, ErrFraudDetected
    }
    
    // Вызов банка
    ctx, bankSpan := tracer.Start(ctx, "bank.charge",
        trace.WithSpanKind(trace.SpanKindClient),
    )
    bankSpan.SetAttributes(
        semconv.RPCSystem("grpc"),
        semconv.RPCService("BankService"),
        semconv.RPCMethod("ChargeCard"),
    )
    
    resp, err := s.bankClient.Charge(ctx, req)
    if err != nil {
        bankSpan.RecordError(err)
        bankSpan.SetStatus(codes.Error, err.Error())
        bankSpan.End()
        return nil, err
    }
    bankSpan.SetAttributes(attribute.String("bank.transaction_id", resp.TransactionID))
    bankSpan.End()
    
    span.SetStatus(codes.Ok, "")
    return resp, nil
}
```

## Correlation ID: связываем все три столпа

Главная сила observability — когда логи, метрики и трассировки связаны между собой через `trace_id`.

```python
import logging
from opentelemetry import trace

class TraceContextFilter(logging.Filter):
    """Добавляет trace_id и span_id в каждую лог-запись"""
    
    def filter(self, record):
        span = trace.get_current_span()
        ctx = span.get_span_context()
        
        if ctx.is_valid:
            record.trace_id = format(ctx.trace_id, '032x')
            record.span_id = format(ctx.span_id, '016x')
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16
        
        return True

# Настройка logging для JSON-вывода с trace_id
import structlog

structlog.configure(
    processors=[
        # Извлекаем trace_id из OpenTelemetry context
        lambda _, __, event_dict: {
            **event_dict,
            "trace_id": format(
                trace.get_current_span().get_span_context().trace_id, '032x'
            )
        },
        structlog.processors.JSONRenderer()
    ]
)
```

Теперь в Grafana можно:
1. Видеть метрику с высоким latency
2. Перейти к трассировке (через exemplar)
3. Из трассировки перейти к логам того же запроса

### Exemplars: связь метрик и трассировок

Prometheus Exemplar — это запись trace_id рядом с метрикой:

```python
from prometheus_client import Histogram
from opentelemetry import trace

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

def record_request(method, endpoint, duration):
    span_ctx = trace.get_current_span().get_span_context()
    
    # Добавляем exemplar - указатель на конкретную трассировку
    request_duration.labels(
        method=method, endpoint=endpoint
    ).observe(
        duration,
        exemplar={
            'traceID': format(span_ctx.trace_id, '032x'),
            'spanID': format(span_ctx.span_id, '016x')
        }
    )
```

В Grafana Explore при клике на "медленную точку" гистограммы автоматически откроется Jaeger с соответствующей трассировкой.

## Jaeger и Zipkin: визуализация трассировок

**Jaeger** (CNCF проект, разработан Uber) — наиболее распространённый open-source бэкенд для трассировок.

```yaml
# docker-compose.yml для локальной разработки
services:
  jaeger:
    image: jaegertracing/all-in-one:1.50
    ports:
      - "16686:16686"   # Jaeger UI
      - "14250:14250"   # gRPC для collector
      - "4317:4317"     # OTLP gRPC
    environment:
      - COLLECTOR_OTLP_ENABLED=true
```

**Grafana Tempo** — альтернатива, интегрируется напрямую в Grafana без отдельного UI:

```yaml
# tempo.yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:

ingester:
  max_block_duration: 5m

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/blocks
```

## SLO Alerting: когда будить инженера

SLO (Service Level Objective) — это конкретная цель по надёжности. Например: 99.9% запросов должны выполняться быстрее 500ms.

### Multi-window, Multi-burn-rate alerts

Простой alert "если latency > 500ms" плохо работает: слишком много false positives. Google SRE Book предлагает "multi-burn-rate" алёртинг.

**Error Budget**: при SLO 99.9% за 30 дней error budget = 0.1% = 43.2 минуты.

**Burn rate**: скорость сжигания бюджета. Burn rate 1 = точно укладываемся. Burn rate 14.4 = исчерпаем бюджет за 2 часа.

```yaml
# alerts/slo.yml
groups:
  - name: slo-payment-service
    rules:
      # КРИТИЧНЫЙ: сжигаем быстро (страница инженера)
      - alert: PaymentSLOHighBurnRate
        expr: |
          (
            sum(rate(http_requests_total{service="payment", status=~"5.."}[1h]))
            / sum(rate(http_requests_total{service="payment"}[1h]))
          ) > (14.4 * 0.001)
          AND
          (
            sum(rate(http_requests_total{service="payment", status=~"5.."}[5m]))
            / sum(rate(http_requests_total{service="payment"}[5m]))
          ) > (14.4 * 0.001)
        for: 2m
        labels:
          severity: critical
          team: payments
        annotations:
          summary: "Payment service burning error budget at 14.4x rate"
          runbook_url: "https://wiki/runbooks/payment-high-burn"
          
      # ПРЕДУПРЕЖДЕНИЕ: медленное сжигание (тикет, не звонок)
      - alert: PaymentSLOLowBurnRate
        expr: |
          (
            sum(rate(http_requests_total{service="payment", status=~"5.."}[6h]))
            / sum(rate(http_requests_total{service="payment"}[6h]))
          ) > (3 * 0.001)
          AND
          (
            sum(rate(http_requests_total{service="payment", status=~"5.."}[30m]))
            / sum(rate(http_requests_total{service="payment"}[30m]))
          ) > (3 * 0.001)
        for: 15m
        labels:
          severity: warning
          team: payments
        annotations:
          summary: "Payment service burning error budget at 3x rate"
```

### Error Budget Policy

```python
# Автоматический подсчёт error budget
def calculate_error_budget(service: str, slo_target: float, window_days: int = 30):
    """
    slo_target: например 0.999 для 99.9%
    """
    total_minutes = window_days * 24 * 60
    budget_minutes = total_minutes * (1 - slo_target)
    
    # Запрашиваем из Prometheus
    error_rate = query_prometheus(
        f'sum(rate(http_requests_total{{service="{service}", status=~"5.."}}[{window_days}d]))'
        f'/ sum(rate(http_requests_total{{service="{service}"}}[{window_days}d]))'
    )
    
    consumed_minutes = total_minutes * error_rate
    remaining_minutes = budget_minutes - consumed_minutes
    remaining_percent = (remaining_minutes / budget_minutes) * 100
    
    return {
        "total_budget_minutes": budget_minutes,
        "consumed_minutes": consumed_minutes,
        "remaining_minutes": remaining_minutes,
        "remaining_percent": remaining_percent,
        "status": "healthy" if remaining_percent > 50 else 
                  "at_risk" if remaining_percent > 10 else "exhausted"
    }
```

## Observability-driven Development

**Observability-driven development (ODD)** — это практика, при которой инструментация кода идёт вместе с разработкой фичи, а не добавляется постфактум.

Принципы:

1. **Instrument before deploy**: каждая новая фича должна иметь метрики и трассировки до выхода в прод

2. **Unknown unknowns**: проектируйте для вопросов, которые ещё не знаете. Структурированные логи с богатым контекстом лучше, чем метрики для каждого мыслимого вопроса

3. **High cardinality data**: используйте трассировки для данных с высокой cardinality (user_id, session_id, request_id)

4. **Observability in PR review**: при code review проверяйте — понятно ли будет, что происходит в этом коде в проде?

### Пример: полный путь диагностики

Сценарий: пользователи жалуются на медленные заказы.

**Шаг 1: Метрики** — видим в Grafana: P99 latency для /api/orders выросло с 200ms до 2s начиная с 14:30.

```promql
histogram_quantile(0.99, 
  sum(rate(http_request_duration_seconds_bucket{endpoint="/api/orders"}[5m])) by (le)
)
```

**Шаг 2: Трассировки** — в Jaeger ищем медленные трассировки для /api/orders с 14:30.

Обнаруживаем: span `inventory.check` занимает 1.8s из 2s. В атрибутах видим `db.statement = "SELECT * FROM products WHERE sku IN (...)"`.

**Шаг 3: Логи** — берём `trace_id` из медленной трассировки, ищем в Loki:

```logql
{service="inventory-service"} | json | trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
```

Находим: `"message": "full table scan detected", "table": "products", "rows_examined": 2500000`.

**Диагноз**: в 14:28 был деплой который дропнул индекс на колонке `sku`. Без observability поиск причины занял бы часы.

## Grafana: дашборды для всего

Grafana — де-факто стандарт для визуализации метрик, логов и трассировок.

```json
{
  "dashboard": {
    "title": "Payment Service SLO",
    "panels": [
      {
        "title": "Request Rate",
        "type": "stat",
        "targets": [{
          "expr": "sum(rate(http_requests_total{service=\"payment\"}[5m]))",
          "legendFormat": "req/s"
        }]
      },
      {
        "title": "Error Rate",
        "type": "timeseries",
        "targets": [{
          "expr": "sum(rate(http_requests_total{service=\"payment\",status=~\"5..\"}[5m])) / sum(rate(http_requests_total{service=\"payment\"}[5m]))",
          "legendFormat": "error rate"
        }],
        "fieldConfig": {
          "defaults": {
            "unit": "percentunit",
            "thresholds": {
              "steps": [
                {"color": "green", "value": 0},
                {"color": "yellow", "value": 0.001},
                {"color": "red", "value": 0.01}
              ]
            }
          }
        }
      },
      {
        "title": "Latency Percentiles",
        "type": "timeseries",
        "targets": [
          {
            "expr": "histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{service=\"payment\"}[5m])) by (le))",
            "legendFormat": "P50"
          },
          {
            "expr": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service=\"payment\"}[5m])) by (le))",
            "legendFormat": "P95"
          },
          {
            "expr": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service=\"payment\"}[5m])) by (le))",
            "legendFormat": "P99"
          }
        ]
      }
    ]
  }
}
```

## Практические советы

### Что логировать на каждом уровне

```python
# INFO: бизнес-события
log.info("order.created", order_id=order.id, user_id=user.id, 
         total=order.total, items_count=len(order.items))

# WARN: нештатные, но ожидаемые ситуации
log.warning("payment.retry", attempt=2, error="timeout", 
            next_retry_ms=1000, payment_id=payment.id)

# ERROR: нужно расследование
log.error("payment.permanent_failure", payment_id=payment.id,
          error_code="CARD_DECLINED", user_id=user.id)

# Никогда не логируйте PII в ошибках!
# ПЛОХО:
log.error("auth.failed", email=user.email, password_hash=pwd_hash)

# ХОРОШО:
log.error("auth.failed", user_id=user.id, 
          masked_email="j***@example.com")
```

### Стоимость наблюдаемости

Инструментация не бесплатна:
- Каждый span: ~1-5μs overhead
- JSON-логи: в 3-5 раз больше байт, чем plain text
- Metrics scrape: ~1-10ms на инстанс при 15s интервале

Стратегии оптимизации:
```python
# Tail-based sampling: сохраняем 100% ошибок, 1% успешных
class TailSampler(trace.sampling.Sampler):
    def should_sample(self, context, trace_id, name, kind, attributes, links):
        # Всегда сохраняем ошибки
        if attributes.get("http.status_code", 200) >= 500:
            return SamplingResult(Decision.RECORD_AND_SAMPLE)
        
        # 1% успешных
        if trace_id % 100 < 1:
            return SamplingResult(Decision.RECORD_AND_SAMPLE)
        
        return SamplingResult(Decision.DROP)
```

## Итог: observability как культура

Observability — это не набор инструментов, а культура и практика. Команды, которые её практикуют:
- Выявляют инциденты на 60-80% быстрее (данные Google DORA)
- Могут ответить на вопрос "что происходит прямо сейчас" без деплоя дополнительного кода
- Имеют объективные данные для capacity planning

Стек с нуля:
1. **Начните с логов**: добавьте structlog/zerolog, отправьте в Loki
2. **Добавьте метрики**: Prometheus + Grafana, минимум RED
3. **Добавьте трассировки**: OpenTelemetry + Jaeger
4. **Свяжите через trace_id**: добавьте в логи, используйте exemplars в метриках
5. **SLO и alerting**: определите SLO, настройте burn-rate алёрты

Инвестиции в observability окупаются при первом же серьёзном инциденте в проде.

## Литература

1. Beyer B. et al. **Site Reliability Engineering**. O'Reilly Media, 2016. Chapter 4: Service Level Objectives. — https://sre.google/sre-book/service-level-objectives/

2. Majors C., Fong-Jones L., Miranda G. **Observability Engineering**. O'Reilly Media, 2022. — Фундаментальная книга о observability от авторов Honeycomb.

3. **OpenTelemetry Documentation**. — https://opentelemetry.io/docs/

4. **Prometheus Documentation: Writing exporters**. — https://prometheus.io/docs/instrumenting/writing_exporters/

5. **Google SRE Workbook: Alerting on SLOs**. — https://sre.google/workbook/alerting-on-slos/

6. Turnbull J. **The Art of Monitoring**. Turnbull Press, 2016. — Практическое руководство по мониторингу и логированию.

7. **Jaeger Documentation**. CNCF. — https://www.jaegertracing.io/docs/

8. **Grafana Loki Documentation**. — https://grafana.com/docs/loki/

9. Sigelman B. et al. **Dapper, a Large-Scale Distributed Systems Tracing Infrastructure**. Google Technical Report, 2010. — Оригинальная статья, вдохновившая OpenTracing и Zipkin.

10. **W3C Trace Context Specification**. — https://www.w3.org/TR/trace-context/
