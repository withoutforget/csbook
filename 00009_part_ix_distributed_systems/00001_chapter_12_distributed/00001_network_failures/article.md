# Сетевые сбои в распределённых системах: классификация и обработка

## Введение

В распределённой системе каждый вызов удалённой функции пересекает сеть — ненадёжную среду передачи, где пакеты теряются, задерживаются, дублируются и прибывают в неправильном порядке. Разработчик монолита может игнорировать сбои памяти или CPU как редчайшие события. Разработчик распределённой системы не может игнорировать сетевые сбои — они являются нормой, а не исключением.

Питер Дойч и Джеймс Гослинг в 1994 году сформулировали «Восемь заблуждений распределённых вычислений» — ложные предположения, которые новички принимают как данность. Понимание природы сетевых сбоев и их классификация — фундамент проектирования надёжных распределённых систем.

---

## 1. Восемь заблуждений распределённых вычислений

Классический список Питера Дойча (1994), дополненный Дж. Гослингом:

1. **Сеть надёжна** *(Network is reliable)* — пакеты теряются, каналы рвутся
2. **Задержка нулевая** *(Latency is zero)* — RTT внутри датацентра ~0.5мс, между континентами ~150мс
3. **Пропускная способность бесконечна** *(Bandwidth is infinite)* — реальные ограничения от 100Мбит до 100Гбит
4. **Сеть безопасна** *(The network is secure)* — MITM-атаки, перехват трафика
5. **Топология не меняется** *(Topology doesn't change)* — серверы добавляются и удаляются
6. **Есть один администратор** *(There is one administrator)* — несколько команд, несогласованные конфигурации
7. **Стоимость транспорта нулевая** *(Transport cost is zero)* — сериализация, сетевые вызовы = CPU
8. **Сеть однородна** *(The network is homogeneous)* — разные оборудование, ОС, версии протоколов

---

## 2. Классификация сетевых сбоев

### 2.1 Fail-Stop vs Crash vs Byzantine

**Fail-stop failures**: узел останавливается и прекращает отвечать. Другие узлы могут определить отказ. Простейший случай для алгоритмов.

**Crash failures (Silent crash)**: узел останавливается, но не уведомляет об этом. Другие узлы не могут немедленно определить — узел упал или просто медленно отвечает.

**Byzantine failures** (Lamport et al., 1982): узел продолжает работать, но отвечает некорректно — случайными данными, устаревшими данными, или злонамеренно. Требует Byzantine Fault Tolerant (BFT) алгоритмов, 3f+1 узлов для f Byzantine отказов.

```python
from enum import Enum
from typing import Optional
import random
import time

class FailureType(Enum):
    NONE = "none"
    CRASH = "crash"
    SLOW = "slow"        # высокая задержка
    BYZANTINE = "byzantine"  # неправильный ответ

class UnreliableNode:
    """Симуляция узла с различными типами отказов"""
    
    def __init__(self, node_id: str, failure_rate: float = 0.1):
        self.node_id = node_id
        self.failure_rate = failure_rate
        self.crashed = False
        self.data = {}
    
    def inject_failure(self) -> FailureType:
        if self.crashed:
            return FailureType.CRASH
        r = random.random()
        if r < self.failure_rate * 0.3:
            self.crashed = True
            return FailureType.CRASH
        elif r < self.failure_rate * 0.6:
            return FailureType.SLOW
        elif r < self.failure_rate:
            return FailureType.BYZANTINE
        return FailureType.NONE
    
    def get(self, key: str) -> Optional[str]:
        failure = self.inject_failure()
        
        if failure == FailureType.CRASH:
            raise ConnectionError(f"Node {self.node_id} is down")
        
        if failure == FailureType.SLOW:
            time.sleep(random.uniform(5, 30))  # timeout
        
        if failure == FailureType.BYZANTINE:
            return "corrupted_value_xyz"  # неверный ответ
        
        return self.data.get(key)
    
    def put(self, key: str, value: str) -> bool:
        failure = self.inject_failure()
        
        if failure == FailureType.CRASH:
            raise ConnectionError(f"Node {self.node_id} is down")
        
        if failure == FailureType.BYZANTINE:
            # Делаем вид что записали, но не записываем
            return True
        
        self.data[key] = value
        return True
```

### 2.2 Частичные сбои (Partial Failures)

Ключевая особенность распределённых систем: **частичные сбои**. В отличие от однопроцессорной программы, где операция либо выполнилась, либо нет, в сети возможны промежуточные состояния:

- Запрос дошёл до сервера, сервер выполнил операцию, ответ потерялся → клиент не знает, выполнилась ли операция
- Запрос потерялся до прибытия → операция не выполнена, но клиент это не знает
- Запрос дошёл, операция выполнена частично (запись в базу — да, отправка уведомления — нет)

```python
import socket
import time
from contextlib import contextmanager

class NetworkException(Exception):
    pass

class TimeoutException(NetworkException):
    pass

class ConnectionRefusedException(NetworkException):
    pass

def classify_network_error(exception: Exception) -> str:
    """Классификация типа сетевой ошибки"""
    if isinstance(exception, socket.timeout):
        # Неизвестно: запрос мог выполниться, мог нет
        return "TIMEOUT: request outcome unknown"
    elif isinstance(exception, ConnectionRefusedError):
        # Сервер не принял соединение: запрос НЕ выполнен
        return "REFUSED: request definitely not executed"
    elif isinstance(exception, ConnectionResetError):
        # Соединение разорвано: запрос мог выполниться частично
        return "RESET: request may be partially executed"
    elif isinstance(exception, BrokenPipeError):
        # То же — непонятно
        return "BROKEN_PIPE: request outcome unknown"
    else:
        return f"UNKNOWN: {type(exception).__name__}"
```

### 2.3 Network Partition (Разбиение сети)

Разбиение сети — ситуация, когда группа узлов не может общаться с другой группой, но оба подмножества продолжают работать. Это не crash — узлы живы, но изолированы.

```
Нормальное состояние:
Node A ←──── Network ────→ Node B ←──── Network ────→ Node C

После разбиения:
Node A ←── Partition 1 ──→ Node B  |||  Node C (изолирован)
```

Разбиения происходят из-за: сбоя сетевого оборудования, перегрузки сети, неправильной конфигурации файервола, физического разреза кабеля.

---

## 3. Timeouts: как обнаружить отказ

### 3.1 Проблема детекции отказов

В асинхронной сети нет способа отличить медленный узел от упавшего. Единственный практический механизм — **таймауты**.

```python
import asyncio
import httpx
from typing import Optional

class CircuitBreakerState(Enum):
    CLOSED = "closed"    # нормальная работа
    OPEN = "open"        # отказы превысили порог, запросы блокируются
    HALF_OPEN = "half_open"  # тестируем восстановление

class RobustHTTPClient:
    def __init__(
        self,
        connect_timeout: float = 1.0,    # установка соединения
        read_timeout: float = 10.0,       # ожидание ответа
        write_timeout: float = 5.0,       # отправка запроса
        pool_timeout: float = 2.0         # ожидание соединения из пула
    ):
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout
        )
        self.client = httpx.AsyncClient(timeout=self.timeout)
    
    async def get_with_retry(
        self, 
        url: str, 
        max_retries: int = 3,
        backoff_base: float = 0.5
    ) -> Optional[dict]:
        """GET с экспоненциальным backoff"""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                return response.json()
            
            except httpx.TimeoutException as e:
                # Timeout: неизвестен исход предыдущего запроса
                last_exception = e
                wait_time = backoff_base * (2 ** attempt) + random.uniform(0, 0.1)
                print(f"Attempt {attempt+1} timed out, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
            
            except httpx.HTTPStatusError as e:
                if e.response.status_code in {500, 502, 503, 504}:
                    # Server error: может быть временным
                    last_exception = e
                    await asyncio.sleep(backoff_base * (2 ** attempt))
                else:
                    # Client error (4xx): retry не поможет
                    raise
        
        raise TimeoutError(f"Failed after {max_retries} retries: {last_exception}")
```

### 3.2 Выбор правильного таймаута

Таймаут слишком короткий → ложные срабатывания, нагрузка на систему от лишних retry.
Таймаут слишком длинный → медленная реакция на отказы, ресурсы заняты ожиданием.

```python
import numpy as np

def suggest_timeout(latency_samples: list[float], 
                    percentile: float = 99.9) -> float:
    """Рекомендовать таймаут на основе исторических задержек"""
    p = np.percentile(latency_samples, percentile)
    # Добавляем запас: 2x от p99.9 + небольшой буфер
    return p * 2 + 0.1

# Например: p99.9 = 500ms → timeout = 1100ms
latencies = np.random.exponential(scale=0.1, size=10000).tolist()
timeout = suggest_timeout(latencies)
print(f"Recommended timeout: {timeout*1000:.0f}ms")
```

---

## 4. Retry стратегии

### 4.1 Простой retry с backoff

```python
import asyncio
import random
from functools import wraps
from typing import Callable, TypeVar, Awaitable

T = TypeVar('T')

def with_retry(
    max_attempts: int = 3,
    exceptions: tuple = (Exception,),
    backoff_base: float = 1.0,
    backoff_max: float = 30.0,
    jitter: bool = True
):
    """Декоратор для автоматического retry с экспоненциальным backoff"""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    
                    # Exponential backoff with jitter (AWS рекомендация)
                    wait = min(backoff_base * (2 ** attempt), backoff_max)
                    if jitter:
                        wait *= (0.5 + random.random() * 0.5)
                    
                    print(f"{func.__name__}: attempt {attempt+1} failed: {e}. "
                          f"Retrying in {wait:.1f}s")
                    await asyncio.sleep(wait)
        return wrapper
    return decorator

@with_retry(max_attempts=5, backoff_base=0.5)
async def fetch_user(user_id: int) -> dict:
    # Имитация нестабильного API
    if random.random() < 0.3:
        raise ConnectionError("Temporary network error")
    return {"id": user_id, "name": "Alice"}
```

### 4.2 Идемпотентность и безопасность retry

**Критически важно**: retry безопасен только для **идемпотентных** операций.

- `GET /users/123` — идемпотентна: повторный вызов вернёт тот же результат
- `POST /payments` — НЕ идемпотентна: повторный вызов создаст дублирующий платёж
- `PUT /orders/123/status` — идемпотентна: установка статуса несколько раз = тот же результат

Для неидемпотентных операций нужен **idempotency key**:

```python
import uuid
import hashlib

class PaymentService:
    def __init__(self):
        self.processed_payments = set()  # idempotency keys
    
    async def create_payment(
        self, 
        user_id: str, 
        amount: float, 
        idempotency_key: str = None
    ) -> dict:
        if idempotency_key is None:
            idempotency_key = str(uuid.uuid4())
        
        # Если уже обрабатывали этот ключ — вернуть предыдущий результат
        if idempotency_key in self.processed_payments:
            print(f"Duplicate request with key {idempotency_key}, returning cached")
            return {"status": "already_processed", "idempotency_key": idempotency_key}
        
        # Обработка платежа
        result = await self._process_payment(user_id, amount)
        
        # Сохраняем ключ ТОЛЬКО при успехе
        self.processed_payments.add(idempotency_key)
        
        return {**result, "idempotency_key": idempotency_key}
    
    async def _process_payment(self, user_id: str, amount: float) -> dict:
        await asyncio.sleep(0.1)  # имитация обработки
        return {"payment_id": str(uuid.uuid4()), "amount": amount, "status": "success"}

# Клиент: детерминированный idempotency_key на основе параметров
def compute_idempotency_key(user_id: str, amount: float, order_id: str) -> str:
    payload = f"{user_id}:{amount}:{order_id}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

---

## 5. Circuit Breaker: автоматический выключатель

### 5.1 Паттерн Circuit Breaker

Circuit Breaker (Nygard, 2007) предотвращает каскадные отказы: если downstream-сервис часто падает, перестаём его дёргать на определённое время.

```python
import time
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Awaitable, TypeVar

T = TypeVar('T')

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5      # отказов для открытия
    success_threshold: int = 2      # успехов для закрытия (в HALF_OPEN)
    timeout: float = 60.0           # секунд в OPEN состоянии
    
class CircuitBreaker:
    """
    CLOSED: обычная работа, считаем отказы
    OPEN: запросы блокируются немедленно
    HALF_OPEN: пропускаем тестовые запросы
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
    
    def can_execute(self) -> bool:
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            # Проверяем, прошёл ли timeout для перехода в HALF_OPEN
            if time.monotonic() - self.last_failure_time > self.config.timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                print(f"Circuit {self.name}: OPEN → HALF_OPEN")
                return True
            return False
        
        # HALF_OPEN: пропускаем запрос
        return True
    
    def on_success(self):
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                print(f"Circuit {self.name}: HALF_OPEN → CLOSED")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        
        if self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                print(f"Circuit {self.name}: CLOSED → OPEN after {self.failure_count} failures")
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            print(f"Circuit {self.name}: HALF_OPEN → OPEN (test failed)")
    
    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        if not self.can_execute():
            raise Exception(f"Circuit {self.name} is OPEN — request blocked")
        
        try:
            result = await func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise

# Использование
cb = CircuitBreaker("user-service", CircuitBreakerConfig(failure_threshold=3))

async def get_user(user_id: int) -> dict:
    return await cb.call(fetch_user_from_service, user_id)
```

---

## 6. Bulkhead: изоляция ресурсов

### 6.1 Паттерн Bulkhead

Bulkhead (переборка корабля) — изолирование ресурсов для разных сервисов, чтобы отказ одного не поглощал ресурсы другого.

```python
import asyncio
from asyncio import Semaphore

class BulkheadPool:
    """Изолированный пул соединений для конкретного сервиса"""
    
    def __init__(self, name: str, max_concurrent: int = 10):
        self.name = name
        self.semaphore = Semaphore(max_concurrent)
        self.rejected_count = 0
    
    async def execute(self, func, *args, **kwargs):
        if self.semaphore.locked() and self.semaphore._value == 0:
            self.rejected_count += 1
            raise Exception(f"Bulkhead {self.name} is full — request rejected")
        
        async with self.semaphore:
            return await func(*args, **kwargs)

# Разные пулы для разных сервисов
payment_pool = BulkheadPool("payments", max_concurrent=20)
catalog_pool = BulkheadPool("catalog", max_concurrent=50)
notification_pool = BulkheadPool("notifications", max_concurrent=5)

# Если notifications зависли — payments не пострадают
```

---

## 7. Мониторинг и наблюдаемость сетевых сбоев

### 7.1 Ключевые метрики

```python
from prometheus_client import Counter, Histogram, Gauge

# Метрики для распределённых вызовов
RPC_REQUESTS = Counter(
    'rpc_requests_total',
    'Total RPC requests',
    labelnames=['service', 'method', 'status']  # status: success/timeout/error
)

RPC_DURATION = Histogram(
    'rpc_duration_seconds',
    'RPC request duration',
    labelnames=['service', 'method'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0]
)

CIRCUIT_BREAKER_STATE = Gauge(
    'circuit_breaker_state',
    'Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)',
    labelnames=['service']
)

RETRY_ATTEMPTS = Counter(
    'retry_attempts_total',
    'Total retry attempts',
    labelnames=['service', 'attempt_number']
)

# SLI (Service Level Indicator): availability = успешные / все запросы
async def rpc_call_with_metrics(service: str, method: str, func, *args):
    with RPC_DURATION.labels(service=service, method=method).time():
        try:
            result = await func(*args)
            RPC_REQUESTS.labels(service=service, method=method, status='success').inc()
            return result
        except TimeoutError:
            RPC_REQUESTS.labels(service=service, method=method, status='timeout').inc()
            raise
        except Exception:
            RPC_REQUESTS.labels(service=service, method=method, status='error').inc()
            raise
```

### 7.2 Distributed Tracing

Для понимания цепочки вызовов в распределённой системе:

```python
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

tracer = trace.get_tracer(__name__)

async def handle_order(order_id: str):
    with tracer.start_as_current_span("handle_order") as span:
        span.set_attribute("order.id", order_id)
        
        try:
            # Дочерний span для каждого downstream вызова
            with tracer.start_as_current_span("fetch_user") as child_span:
                user = await fetch_user_service(order_id)
                child_span.set_attribute("user.id", user['id'])
            
            with tracer.start_as_current_span("process_payment") as child_span:
                payment = await payment_service(order_id)
                child_span.set_attribute("payment.status", payment['status'])
            
            return {"order_id": order_id, "status": "processed"}
        
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
```

---

## 8. Graceful Degradation: деградация вместо отказа

### 8.1 Стратегии деградации

При недоступности зависимостей лучше отдать частичный результат, чем ошибку:

```python
from typing import Optional
import asyncio

class ProductService:
    def __init__(self, catalog_service, recommendation_service, inventory_service):
        self.catalog = catalog_service
        self.recommendations = recommendation_service
        self.inventory = inventory_service
    
    async def get_product_page(self, product_id: str) -> dict:
        # Критичные данные: не работаем без них
        product = await self.catalog.get(product_id)
        
        # Некритичные данные: деградируем gracefully
        recommendations, inventory = await asyncio.gather(
            self._safe_fetch(self.recommendations.get(product_id), default=[]),
            self._safe_fetch(self.inventory.get(product_id), default={"in_stock": None}),
            return_exceptions=False
        )
        
        return {
            "product": product,
            "recommendations": recommendations,  # [] если сервис недоступен
            "in_stock": inventory.get("in_stock")  # None = неизвестно
        }
    
    async def _safe_fetch(self, coro, default, timeout: float = 1.0):
        """Возвращает default при любой ошибке или таймауте"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except (asyncio.TimeoutError, Exception) as e:
            print(f"Non-critical service failed: {e}, using default")
            return default
```

---

## Заключение

Сетевые сбои — фундаментальная реальность распределённых систем, а не редкие исключения. Ключевые принципы:

1. **Classify failures**: distinguish crash, timeout (unknown outcome), byzantine
2. **Timeouts everywhere**: без таймаутов нет детекции отказов
3. **Retry with backoff + jitter**: только для идемпотентных операций
4. **Idempotency keys**: для безопасного retry неидемпотентных операций
5. **Circuit Breaker**: предотвращает каскадные отказы
6. **Bulkhead**: изолирует ресурсы разных сервисов
7. **Graceful degradation**: частичный результат лучше полного отказа
8. **Observe everything**: метрики, трейсинг, логи для понимания отказов

---

## Библиография

1. Deutsch, P. (1994). The Eight Fallacies of Distributed Computing. Sun Microsystems.
2. Lamport, L., Shostak, R., & Pease, M. (1982). The Byzantine Generals Problem. *ACM Transactions on Programming Languages and Systems*, 4(3), 382–401.
3. Nygard, M. (2018). *Release It!: Design and Deploy Production-Ready Software* (2nd ed.). Pragmatic Bookshelf.
4. Burns, B. (2018). *Designing Distributed Systems*. O'Reilly Media.
5. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media. Chapter 8.
6. Fowler, M. (2014). Circuit Breaker. https://martinfowler.com/bliki/CircuitBreaker.html
7. Amazon Web Services. (2022). *Exponential Backoff and Jitter*. https://aws.amazon.com/blogs/architecture/
8. Hohpe, G., & Woolf, B. (2003). *Enterprise Integration Patterns*. Addison-Wesley.
