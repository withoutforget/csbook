# Service Mesh (Envoy, Istio) — sidecar-паттерн, mTLS и observability на уровне сети

По мере того как монолиты разбиваются на десятки и сотни микросервисов, возникает новая проблема: каждый сервис должен уметь безопасно общаться с другими, устойчиво работать при сетевых сбоях, собирать метрики и трейсы. Если реализовывать это в каждом сервисе отдельно — это тысячи строк дублирующегося кода на разных языках. Service mesh решает эту проблему, вынося сетевую логику из приложений в инфраструктурный слой.

## Проблема: сетевая логика в каждом сервисе

Представьте микросервисную архитектуру: OrderService вызывает InventoryService, PaymentService, NotificationService. Каждый вызов должен:
- Быть зашифрован (TLS)
- Иметь retry при временных ошибках
- Иметь circuit breaker при системных ошибках
- Отправлять метрики (количество запросов, задержки, ошибки)
- Распространять трейсы (correlation ID для distributed tracing)
- Применять timeout политики

```python
# Без service mesh — это всё нужно писать в каждом сервисе
import httpx
import opentelemetry
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
async def call_inventory_service(product_id: int) -> dict:
    """
    Кажется простым вызовом, но на самом деле:
    - TLS конфигурация
    - Retry с backoff
    - Circuit breaker
    - Timeout
    - Tracing headers
    - Metrics
    """
    tracer = opentelemetry.trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("inventory.get") as span:
        span.set_attribute("product.id", product_id)
        
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    verify="/etc/ssl/certs/ca-bundle.crt",  # mTLS
                    cert=("/etc/ssl/client.crt", "/etc/ssl/client.key"),
                    timeout=5.0
                ) as client:
                    response = await client.get(
                        f"https://inventory-service/api/products/{product_id}",
                        headers={
                            "X-Trace-ID": span.get_span_context().trace_id,
                            "X-Span-ID": span.get_span_context().span_id,
                        }
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.TransientError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff
```

Этот код надо написать для каждого сервиса, на каждом языке (Python, Go, Java, Node.js...). И при изменении политик — обновлять все сервисы. Service mesh решает это иначе.

## Что такое Service Mesh

Service mesh — это выделенный инфраструктурный слой для управления коммуникацией между сервисами. Он состоит из:

1. **Data plane** — прокси (обычно Envoy), работающий рядом с каждым сервисом
2. **Control plane** — централизованный компонент, управляющий конфигурацией всех прокси

```
┌────────────────────────────────────────────────────────┐
│                   Control Plane                        │
│              (Istiod / Linkerd Controller)              │
│   Политики │ Сертификаты │ Конфигурация маршрутов      │
└────────────────────────────────────────────────────────┘
         │              │              │
    ┌────▼────┐    ┌────▼────┐   ┌────▼────┐
    │ Envoy   │    │ Envoy   │   │ Envoy   │
    │ sidecar │    │ sidecar │   │ sidecar │
    │┌───────┐│    │┌───────┐│   │┌───────┐│
    ││Service││    ││Service││   ││Service││
    ││  A    ││    ││  B    ││   ││  C    ││
    │└───────┘│    │└───────┘│   │└───────┘│
    └─────────┘    └─────────┘   └─────────┘
         │              │              │
         └──────────────┼──────────────┘
                   Data Plane
```

**Ключевая идея:** Ни один пакет не идёт напрямую между сервисами. Каждый пакет проходит через sidecar-прокси. Прокси перехватывает весь трафик прозрачно, без изменения кода приложения.

## Sidecar Proxy Pattern

Sidecar — дополнительный контейнер, разворачивающийся рядом с основным контейнером приложения в одном Pod (в терминах Kubernetes). Они разделяют network namespace, поэтому sidecar может перехватывать весь сетевой трафик через iptables rules.

```yaml
# Kubernetes Pod с sidecar Envoy (упрощённо — в Istio это происходит автоматически)
apiVersion: v1
kind: Pod
metadata:
  name: order-service
spec:
  initContainers:
  # Init container настраивает iptables для перехвата трафика
  - name: istio-init
    image: istio/proxyv2:1.19.0
    command: ["pilot-agent", "istio-iptables"]
    securityContext:
      capabilities:
        add: ["NET_ADMIN"]
  
  containers:
  # Основное приложение
  - name: order-service
    image: mycompany/order-service:v1.2.0
    ports:
    - containerPort: 8080
    # Приложение ничего не знает о service mesh!
  
  # Sidecar прокси
  - name: istio-proxy
    image: istio/proxyv2:1.19.0
    args:
    - proxy
    - sidecar
    env:
    - name: PILOT_CERT_PROVIDER
      value: "istiod"
```

На практике в Istio это происходит автоматически через **MutatingWebhookConfiguration**: при создании Pod в namespace с лейблом `istio-injection: enabled` Kubernetes автоматически добавляет sidecar контейнер.

```bash
# Включить автоматическую инъекцию sidecar для namespace
kubectl label namespace production istio-injection=enabled
```

## Envoy: сердце data plane

Envoy — высокопроизводительный прокси-сервер, разработанный в Lyft в 2016 году и переданный в CNCF. Написан на C++, обрабатывает миллионы запросов в секунду с минимальными накладными расходами.

### Ключевые концепции Envoy

**Listeners** — принимают входящие соединения  
**Clusters** — upstream сервисы (к которым Envoy проксирует)  
**Routes** — правила маршрутизации от listener к cluster  
**Filters** — цепочка обработки запросов (HTTP, TCP, gRPC фильтры)

```json
// Конфигурация Envoy (упрощённо)
{
  "static_resources": {
    "listeners": [{
      "name": "listener_0",
      "address": {"socket_address": {"address": "0.0.0.0", "port_value": 15006}},
      "filter_chains": [{
        "filters": [{
          "name": "envoy.filters.network.http_connection_manager",
          "typed_config": {
            "@type": "type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager",
            "http_filters": [
              {"name": "envoy.filters.http.jwt_authn"},     // JWT аутентификация
              {"name": "envoy.filters.http.rbac"},           // Авторизация
              {"name": "envoy.filters.http.router"}          // Маршрутизация
            ],
            "route_config": {
              "virtual_hosts": [{
                "domains": ["*"],
                "routes": [{
                  "match": {"prefix": "/"},
                  "route": {
                    "cluster": "inventory-service",
                    "timeout": "5s",
                    "retry_policy": {
                      "retry_on": "5xx,connect-failure",
                      "num_retries": 3,
                      "per_try_timeout": "2s"
                    }
                  }
                }]
              }]
            }
          }
        }]
      }]
    }],
    "clusters": [{
      "name": "inventory-service",
      "connect_timeout": "1s",
      "type": "STRICT_DNS",
      "load_assignment": {
        "cluster_name": "inventory-service",
        "endpoints": [{
          "lb_endpoints": [{
            "endpoint": {"address": {"socket_address": {"address": "inventory-service", "port_value": 8080}}}
          }]
        }]
      }
    }]
  }
}
```

В режиме service mesh конфигурацию Envoy генерирует control plane через xDS (x Discovery Service) API — стандартный API для динамического обновления конфигурации.

## mTLS: взаимная аутентификация между сервисами

Обычный TLS аутентифицирует только сервер (клиент проверяет сертификат сервера). mTLS (mutual TLS) — оба участника предъявляют сертификаты и аутентифицируют друг друга.

```
                    mTLS Handshake
OrderService ────────────────────────────── InventoryService
    │                                              │
    │── Client Hello ──────────────────────────→  │
    │← Server Hello + Certificate ─────────────── │
    │← Certificate Request ──────────────────────  │
    │── Client Certificate ──────────────────────→ │
    │── Certificate Verify ──────────────────────→ │
    │── Finished ────────────────────────────────→ │
    │← Finished ──────────────────────────────────  │
    │                                              │
    ├────── Encrypted Application Data ───────────┤
```

**Зачем mTLS в service mesh:**
- **Аутентификация** — каждый сервис имеет уникальный сертификат (SVID — SPIFFE Verifiable Identity Document)
- **Авторизация** — можно запретить OrderService напрямую обращаться к UserService (только через ApiGateway)
- **Шифрование** — даже если злоумышленник попал в кластер, он не может читать трафик между сервисами

### SPIFFE и SPIRE

SPIFFE (Secure Production Identity Framework for Everyone) — стандарт идентификации сервисов в cloud-native окружениях.

```
# SPIFFE Identity формат:
spiffe://trust-domain/path

# Примеры:
spiffe://example.com/ns/production/sa/order-service
spiffe://example.com/ns/production/sa/inventory-service
```

В Istio каждому Pod выдаётся сертификат с SPIFFE ID на основе Kubernetes Service Account. Istiod (control plane) выступает CA (Certificate Authority) и автоматически выдаёт/ротирует сертификаты.

```yaml
# Istio PeerAuthentication: требовать mTLS для всего namespace
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: production
spec:
  mtls:
    mode: STRICT  # Отклонять незашифрованный трафик
```

```yaml
# Istio AuthorizationPolicy: разрешить OrderService обращаться к InventoryService
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: inventory-access
  namespace: production
spec:
  selector:
    matchLabels:
      app: inventory-service
  rules:
  - from:
    - source:
        principals:
          - "cluster.local/ns/production/sa/order-service"  # Только этот сервис
    to:
    - operation:
        methods: ["GET"]
        paths: ["/api/inventory/*"]
```

## Istio: архитектура control plane

Istio — наиболее популярный service mesh для Kubernetes. Начиная с версии 1.5, весь control plane объединён в один компонент — **Istiod**.

### Компоненты Istiod

**Pilot** — управление трафиком (Traffic Management):
- Преобразует высокоуровневые правила (VirtualService, DestinationRule) в конфигурацию Envoy
- Распространяет конфигурацию через xDS API

**Citadel** — управление сертификатами (Certificate Authority):
- Выдаёт и ротирует TLS сертификаты для каждого сервиса
- Реализует SPIFFE стандарт

**Galley** — валидация конфигурации:
- Проверяет корректность Istio ресурсов перед применением

### VirtualService и DestinationRule

```yaml
# VirtualService: правила маршрутизации на уровне HTTP
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: reviews-vs
spec:
  hosts:
  - reviews  # Сервис Kubernetes
  http:
  # Canary: 10% трафика на v2
  - match:
    - headers:
        end-user:
          exact: "test-user"
    route:
    - destination:
        host: reviews
        subset: v2
      weight: 100
  
  # Остальной трафик: 90% v1, 10% v2
  - route:
    - destination:
        host: reviews
        subset: v1
      weight: 90
    - destination:
        host: reviews
        subset: v2
      weight: 10
    
    # Timeout и retry прямо в mesh политике
    timeout: 5s
    retries:
      attempts: 3
      perTryTimeout: 2s
      retryOn: "5xx,connect-failure"
    
    # Fault injection для тестирования
    fault:
      delay:
        percentage:
          value: 5.0  # 5% запросов получат задержку 3 секунды
        fixedDelay: 3s
```

```yaml
# DestinationRule: политики для конкретного upstream сервиса
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: reviews-dr
spec:
  host: reviews
  
  trafficPolicy:
    # Connection pool settings
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        http2MaxRequests: 1000
        pendingRequests: 100
    
    # Circuit breaker (outlier detection в терминах Istio)
    outlierDetection:
      consecutiveGatewayErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
  
  # Subset определения для canary
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
    trafficPolicy:
      connectionPool:
        http:
          http2MaxRequests: 500  # v2 получает меньше параллельных запросов
```

### Istio Gateway: входящий трафик

```yaml
# Gateway: принимает трафик снаружи кластера
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: main-gateway
spec:
  selector:
    istio: ingressgateway  # Envoy запущенный как ingress
  servers:
  - port:
      number: 443
      name: https
      protocol: HTTPS
    tls:
      mode: SIMPLE
      credentialName: example-com-tls  # Kubernetes Secret с сертификатом
    hosts:
    - "example.com"

# VirtualService привязан к Gateway
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: main-vs
spec:
  hosts:
  - "example.com"
  gateways:
  - main-gateway
  http:
  - match:
    - uri:
        prefix: "/api/"
    route:
    - destination:
        host: api-service
        port:
          number: 8080
```

## Traffic Management: Canary и Blue-Green через Istio

### Canary Deployment

```bash
# Шаг 1: Деплоим v2 без трафика
kubectl apply -f deployment-v2.yaml

# Шаг 2: Проверяем что v2 работает (health checks зелёные)
kubectl get pods -l version=v2

# Шаг 3: Начинаем направлять 5% трафика
kubectl apply -f - <<EOF
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: my-service
spec:
  hosts:
  - my-service
  http:
  - route:
    - destination:
        host: my-service
        subset: v1
      weight: 95
    - destination:
        host: my-service
        subset: v2
      weight: 5
EOF

# Шаг 4: Мониторим метрики в Grafana/Kiali
# Шаг 5: Если всё ок — увеличиваем до 50%
# Шаг 6: Полный rollout — 0%/100%
```

### Blue-Green Deployment

```yaml
# Blue-Green: переключение 100% трафика
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: my-service
spec:
  hosts:
  - my-service
  http:
  - route:
    - destination:
        host: my-service
        subset: green  # Переключились с blue на green
      weight: 100
```

## Circuit Breaking в Envoy

Circuit breaker в service mesh работает на уровне прокси, не требуя изменений кода приложения.

```yaml
# Envoy circuit breaker через Istio DestinationRule
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: payment-service-dr
spec:
  host: payment-service
  trafficPolicy:
    # Circuit Breaker: outlier detection
    outlierDetection:
      # Если 5 последовательных ошибок → исключить инстанс на 30 секунд
      consecutiveGatewayErrors: 5
      consecutiveLocalOriginFailures: 5
      interval: 10s              # Анализ за 10 секунд
      baseEjectionTime: 30s      # Минимальное время исключения
      maxEjectionPercent: 100    # До 100% инстансов могут быть исключены
      minHealthPercent: 0        # Даже если все excluded, продолжать пробовать
    
    # Connection Pool limits (предотвращают перегрузку)
    connectionPool:
      http:
        http1MaxPendingRequests: 100   # Очередь ожидающих соединений
        http2MaxRequests: 1000         # Максимум параллельных запросов
      tcp:
        maxConnections: 100
        connectTimeout: 1s
```

**Три состояния circuit breaker:**
- **Closed** (нормальная работа) — запросы проходят
- **Open** (сервис упал) — запросы блокируются немедленно с ошибкой
- **Half-Open** (проверка восстановления) — небольшой процент запросов пропускается

## Observability: телеметрия из коробки

Одно из главных преимуществ service mesh — автоматическая observability без изменения кода приложений.

### Метрики

Envoy экспортирует сотни метрик в формате Prometheus:

```promql
# Количество запросов к сервису
sum(rate(istio_requests_total{destination_service="inventory-service"}[5m]))

# Error rate (процент ошибок 5xx)
sum(rate(istio_requests_total{
  destination_service="inventory-service",
  response_code=~"5.*"
}[5m])) /
sum(rate(istio_requests_total{
  destination_service="inventory-service"
}[5m])) * 100

# P99 latency
histogram_quantile(0.99, 
  sum(rate(istio_request_duration_milliseconds_bucket{
    destination_service="inventory-service"
  }[5m])) by (le)
)
```

### Distributed Tracing

Istio автоматически создаёт spans для каждого запроса. Требование: приложение должно пробрасывать несколько HTTP заголовков (b3 или W3C TraceContext format).

```python
# Приложение должно пробрасывать заголовки трейсинга
from flask import Flask, request
import httpx

app = Flask(__name__)

TRACE_HEADERS = [
    'x-request-id',
    'x-b3-traceid',
    'x-b3-spanid',
    'x-b3-parentspanid',
    'x-b3-sampled',
    'x-b3-flags',
    'traceparent',   # W3C TraceContext
    'tracestate',
]

@app.route('/api/orders/<order_id>')
def get_order(order_id):
    # Пробрасываем заголовки трейсинга к downstream сервисам
    trace_headers = {
        key: request.headers[key]
        for key in TRACE_HEADERS
        if key in request.headers
    }
    
    # Envoy добавит свой span автоматически
    with httpx.Client() as client:
        inventory = client.get(
            f"http://inventory-service/api/stock/{order_id}",
            headers=trace_headers  # Передаём контекст трейса
        )
    
    return {"order_id": order_id, "inventory": inventory.json()}
```

### Kiali: визуализация service mesh

Kiali — дашборд для Istio, показывающий граф зависимостей между сервисами с метриками в реальном времени.

```bash
# Установка Kiali
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/kiali.yaml

# Открыть дашборд
istioctl dashboard kiali
```

## Linkerd: лёгкая альтернатива

Linkerd — другой популярный service mesh, написанный на Rust (data plane proxy — Linkerd2-proxy). Менее функциональный, но значительно проще в установке и эксплуатации.

**Отличия Linkerd от Istio:**

| Характеристика | Istio | Linkerd |
|----------------|-------|---------|
| Сложность установки | Высокая | Низкая |
| Потребление ресурсов | ~300MB на Pod | ~10MB на Pod |
| Proxy | Envoy (C++) | Linkerd2-proxy (Rust) |
| Функциональность | Богатая | Базовая |
| Кривая обучения | Крутая | Пологая |

```bash
# Установка Linkerd (значительно проще Istio)
curl -sL run.linkerd.io/install | sh
linkerd install --crds | kubectl apply -f -
linkerd install | kubectl apply -f -

# Проверка
linkerd check

# Инъекция sidecar в существующий deployment
kubectl get deployment -n production | \
  linkerd inject - | \
  kubectl apply -f -
```

## Consul Connect

HashiCorp Consul предоставляет service mesh не только для Kubernetes, но и для bare metal, VMs, любых окружений.

```hcl
# Consul service definition с Connect (service mesh)
service {
  name = "inventory-service"
  port = 8080
  
  connect {
    sidecar_service {
      proxy {
        upstreams = [
          {
            destination_name = "database"
            local_bind_port  = 5432
          }
        ]
      }
    }
  }
  
  check {
    http     = "http://localhost:8080/health"
    interval = "10s"
  }
}
```

## eBPF-based Service Mesh: Cilium

Cilium использует eBPF для реализации network policy и observability непосредственно в ядре Linux, что позволяет достичь значительно меньших накладных расходов по сравнению с sidecar-подходом.

```bash
# Установка Cilium как CNI + service mesh
helm install cilium cilium/cilium --version 1.14.0 \
  --namespace kube-system \
  --set kubeProxyReplacement=strict \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=true

# Hubble: observability для Cilium
cilium hubble port-forward &
hubble observe --namespace production
```

**Преимущество eBPF-подхода:**
- Нет sidecar контейнера — меньше ресурсов, меньше задержка
- Политики применяются в ядре — более высокая производительность
- Поддержка Layer 3/4/7 без отдельного прокси

**Недостаток:** меньшая функциональность в Traffic Management (нет таких гибких правил как в Istio VirtualService).

## Когда Service Mesh нужен, а когда — overengineering

### Когда service mesh оправдан

✅ **Много микросервисов** (20+) на разных технологических стеках  
✅ **Строгие требования безопасности** — mTLS обязателен по compliance  
✅ **Нужна centralized observability** — трейсы, метрики без изменений в коде  
✅ **Частые canary deployments** — Istio Traffic Management упрощает процесс  
✅ **Zero Trust Network** — каждый сервис должен аутентифицироваться  

### Когда service mesh — overengineering

❌ **Маленькая команда / мало сервисов** (< 10) — overhead не оправдан  
❌ **Монолит** — нет смысла  
❌ **Высокая чувствительность к задержке** — sidecar добавляет 1-5ms на hop  
❌ **Нет экспертизы** — неправильно настроенный Istio хуже чем его отсутствие  

```python
# Сравнение: service mesh vs библиотечный подход

# Service mesh: логика в инфраструктуре
async def call_inventory(product_id: int) -> dict:
    """Просто HTTP вызов — всё остальное делает Envoy sidecar"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://inventory-service/api/products/{product_id}"
        )
        return response.json()

# Библиотечный подход (Netflix OSS: Hystrix, Ribbon)
@circuit_breaker(threshold=5, timeout=30)
@retry(max_attempts=3, backoff=exponential)
@timeout(seconds=5)
async def call_inventory(product_id: int) -> dict:
    """Вся логика — в коде приложения"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://inventory-service/api/products/{product_id}"
        )
        return response.json()
```

Библиотечный подход (как у Netflix OSS) работал хорошо, когда все сервисы были на Java. С полиглотной архитектурой (Go, Python, Rust, Node.js) service mesh — более управляемое решение.

## Производительность и накладные расходы

Реальные измерения (Linkerd benchmark, Istio performance testing):

| Компонент | Накладные расходы |
|-----------|------------------|
| Latency (p50) | +0.5ms - 2ms на hop |
| Latency (p99) | +2ms - 5ms на hop |
| CPU per sidecar | 50-200m cores (idle) |
| Memory per sidecar | 50-350MB |
| Throughput overhead | 5-20% |

Для большинства бизнес-сервисов это приемлемо. Для систем с очень строгими требованиями к latency (HFT, real-time gaming) — использовать eBPF-подход (Cilium) или отказаться от service mesh.

## Заключение

Service mesh — мощный инструмент, решающий реальные проблемы в микросервисных архитектурах. Он переносит cross-cutting concerns (безопасность, observability, resilience) из кода приложений в инфраструктурный слой.

Istio — полнофункциональное, но сложное решение. Linkerd — проще и легче, подходит как отправная точка. Cilium с eBPF — будущее, предлагающее производительность без накладных расходов sidecar.

Главный принцип: **не начинайте с service mesh**. Начните с хороших библиотек и простых паттернов. Переходите к service mesh, когда полиглотная среда и количество сервисов делают library-based подход неуправляемым.

## Литература

1. **Envoy Proxy Documentation** — «Envoy Architecture Overview»: https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/arch_overview
2. **Istio Documentation** — «Istio Architecture»: https://istio.io/latest/docs/ops/deployment/architecture/
3. **Burns, Brendan et al.** — «Kubernetes: Up and Running», 3rd ed. O'Reilly Media, 2022. ISBN: 978-1098110208
4. **Li, Wubin et al.** — «Service Mesh: A Microservices Infrastructure Technology». ICSE 2019
5. **Linkerd Documentation** — «Linkerd Architecture»: https://linkerd.io/2.14/reference/architecture/
6. **Cilium Documentation** — «eBPF-based Service Mesh»: https://docs.cilium.io/en/stable/network/servicemesh/
7. **SPIFFE/SPIRE Documentation** — «SPIFFE Overview»: https://spiffe.io/docs/latest/spiffe-about/overview/
8. **Zack Butcher et al.** — «Istio: Up and Running». O'Reilly Media, 2019. ISBN: 978-1492043782
9. **Greenberg, Albert et al.** — «VL2: A Scalable and Flexible Data Center Network». ACM SIGCOMM, 2009
10. **Gregg, Brendan** — «BPF Performance Tools». Pearson, 2019. ISBN: 978-0136554820
