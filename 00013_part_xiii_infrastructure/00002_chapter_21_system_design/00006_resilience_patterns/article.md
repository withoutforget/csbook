# Идемпотентные API, Retry с экспоненциальным backoff, Circuit Breaker — паттерны устойчивости

В распределённых системах отказы неизбежны. Сети теряют пакеты, серверы перезагружаются, базы данных временно недоступны, upstream-сервисы деградируют. Выбор не в том, будут ли отказы — они будут. Выбор в том, как ваша система на них реагирует: graceful degradation или каскадный сбой, затрагивающий всех пользователей. Паттерны устойчивости (resilience patterns) — это систематический подход к проектированию систем, которые переживают частичные отказы.

## Что такое устойчивость в распределённых системах

**Resilience** (устойчивость) — способность системы продолжать работу при частичных отказах, восстанавливаясь с минимальным влиянием на пользователей.

Иерархия отказов в распределённых системах (по частоте):
1. Временные сбои сети (network blip) — пакет потерян, TCP reset
2. Высокая latency downstream-сервиса (под нагрузкой)
3. Временная недоступность (restart, деплой)
4. Полный отказ сервиса (crash, OOM)
5. Отказ датацентра / зоны доступности

```python
# Без паттернов устойчивости — каскадный сбой
async def get_product_page(product_id: str) -> dict:
    # Если inventory_service лежит — весь запрос падает
    inventory = await inventory_service.get_stock(product_id)  # TimeoutError!
    product = await catalog_service.get_product(product_id)
    price = await pricing_service.get_price(product_id)
    
    return {'product': product, 'price': price, 'in_stock': inventory > 0}
    # Пользователь видит 500 Error, хотя каталог и цены работают нормально
```

## Retry: когда и как повторять запрос

**Retry** — повторная попытка выполнить операцию после временного сбоя.

**Важное правило:** Retry полезен только для временных (transient) ошибок:
- `503 Service Unavailable` — ✅ временная перегрузка, имеет смысл retry
- `429 Too Many Requests` — ✅ rate limiting, retry после паузы
- `500 Internal Server Error` — ❓ может быть временным, осторожно
- `400 Bad Request` — ❌ retry бесполезен (запрос невалидный)
- `404 Not Found` — ❌ retry бесполезен
- `401 Unauthorized` — ❌ retry бесполезен

```python
import asyncio
import random
from typing import TypeVar, Callable, Any

T = TypeVar('T')

class RetryError(Exception):
    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(f"Failed after {attempts} attempts: {last_exception}")

# Перечень ошибок, которые стоит ретраить
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,  # includes network errors
)

async def retry_async(
    func: Callable[..., Any],
    *args,
    max_attempts: int = 3,
    transient_exceptions: tuple = TRANSIENT_EXCEPTIONS,
    **kwargs
) -> Any:
    """Простой retry без backoff."""
    last_exception = None
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except transient_exceptions as e:
            last_exception = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(0.1)
    
    raise RetryError(last_exception, max_attempts)
```

## Exponential Backoff: как ждать между попытками

**Exponential Backoff** — стратегия ожидания перед следующей попыткой. Задержка удваивается с каждой попыткой:

```
delay = min(cap, base * 2^attempt)

Attempt 0: delay = min(60, 1 * 2^0) = 1s
Attempt 1: delay = min(60, 1 * 2^1) = 2s
Attempt 2: delay = min(60, 1 * 2^2) = 4s
Attempt 3: delay = min(60, 1 * 2^3) = 8s
Attempt 4: delay = min(60, 1 * 2^4) = 16s
Attempt 5: delay = min(60, 1 * 2^5) = 32s
Attempt 6: delay = min(60, 1 * 2^6) = 60s  ← cap
```

**Параметры:**
- `base` — начальная задержка (1 секунда)
- `cap` — максимальная задержка (например, 60 секунд)
- `max_attempts` — максимальное количество попыток

```python
import math
import asyncio
import random

async def retry_with_exponential_backoff(
    func: Callable,
    *args,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    multiplier: float = 2.0,
    **kwargs
) -> Any:
    """
    Retry с экспоненциальным backoff.
    delay = min(max_delay, base_delay * multiplier^attempt)
    """
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except TRANSIENT_EXCEPTIONS as e:
            last_exception = e
            
            if attempt == max_attempts - 1:
                break
            
            # Вычисляем задержку
            delay = min(max_delay, base_delay * (multiplier ** attempt))
            
            print(f"Attempt {attempt + 1} failed: {e}. "
                  f"Retrying in {delay:.1f}s...")
            
            await asyncio.sleep(delay)
    
    raise RetryError(last_exception, max_attempts)


# Использование:
result = await retry_with_exponential_backoff(
    inventory_service.get_stock,
    product_id="123",
    max_attempts=4,
    base_delay=0.5,
    max_delay=30.0
)
```

## Jitter: предотвращение Thundering Herd

**Thundering Herd** (гром стада) — проблема, когда много клиентов одновременно делают retry после одного и того же сбоя. Все клиенты ждут одинаковое время и атакуют сервер одновременно снова.

```
Без jitter: 1000 клиентов ждут 2 секунды → 1000 запросов одновременно (DDos собственного сервиса)
С jitter:   1000 клиентов ждут 1.7-2.3 секунды → равномерно распределённая нагрузка
```

**Два популярных подхода к jitter:**

```python
import random

# Full Jitter: случайное число в диапазоне [0, backoff]
def full_jitter(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """Полный jitter — наилучшее распределение нагрузки."""
    backoff = min(cap, base * (2 ** attempt))
    return random.uniform(0, backoff)

# Equal Jitter: backoff/2 + случайное [0, backoff/2]
def equal_jitter(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """Равный jitter — гарантирует минимальное время ожидания."""
    backoff = min(cap, base * (2 ** attempt))
    return (backoff / 2) + random.uniform(0, backoff / 2)

# Decorrelated Jitter (AWS recommendation)
def decorrelated_jitter(
    attempt: int, 
    prev_delay: float,
    base: float = 1.0,
    cap: float = 60.0
) -> float:
    """Декоррелированный jitter — рекомендован AWS."""
    return min(cap, random.uniform(base, prev_delay * 3))

async def retry_with_decorrelated_jitter(func, *args, max_attempts=5, **kwargs):
    delay = 1.0
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except TRANSIENT_EXCEPTIONS as e:
            if attempt == max_attempts - 1:
                raise
            delay = decorrelated_jitter(attempt, delay)
            await asyncio.sleep(delay)
```

## Retry Budget: глобальное ограничение retry

**Retry Budget** предотвращает ситуацию, когда массовые ретраи при системном сбое многократно увеличивают нагрузку.

```python
import time
from collections import deque
import threading

class RetryBudget:
    """
    Ограничение на количество retry в единицу времени.
    Если retry > 10% от нормального трафика — прекращаем retry.
    """
    
    def __init__(
        self, 
        window_seconds: float = 60.0,
        max_retry_ratio: float = 0.1  # Не более 10% запросов могут быть retry
    ):
        self._window = window_seconds
        self._max_ratio = max_retry_ratio
        self._requests = deque()  # (timestamp, is_retry)
        self._lock = threading.Lock()
    
    def record_request(self, is_retry: bool) -> None:
        now = time.time()
        with self._lock:
            self._requests.append((now, is_retry))
            # Удаляем старые запросы за пределами окна
            while self._requests and self._requests[0][0] < now - self._window:
                self._requests.popleft()
    
    def can_retry(self) -> bool:
        now = time.time()
        with self._lock:
            window_requests = [r for r in self._requests 
                             if r[0] >= now - self._window]
            if not window_requests:
                return True
            
            retry_count = sum(1 for _, is_retry in window_requests if is_retry)
            total_count = len(window_requests)
            
            return (retry_count / total_count) < self._max_ratio

# Глобальный бюджет retry для сервиса
_retry_budget = RetryBudget(window_seconds=60, max_retry_ratio=0.1)

async def resilient_request(func, *args, **kwargs):
    _retry_budget.record_request(is_retry=False)
    
    try:
        return await func(*args, **kwargs)
    except TRANSIENT_EXCEPTIONS:
        if not _retry_budget.can_retry():
            raise  # Бюджет исчерпан — не ретраим
        
        _retry_budget.record_request(is_retry=True)
        await asyncio.sleep(1.0)
        return await func(*args, **kwargs)
```

## Circuit Breaker: прерыватель цепи

**Circuit Breaker** — электрический термин: если ток слишком высокий — выключатель размыкает цепь, предотвращая повреждение оборудования.

В программировании: если downstream-сервис регулярно падает — останавливаем запросы к нему, возвращая ошибку немедленно (без ожидания timeout).

**Три состояния:**
- **Closed** (замкнут) — нормальная работа, запросы проходят
- **Open** (разомкнут) — сервис упал, запросы блокируются немедленно
- **Half-Open** (полуоткрыт) — пробный режим, пропускаем часть запросов для проверки

```python
import asyncio
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable

class CircuitState(Enum):
    CLOSED = "closed"       # Нормальная работа
    OPEN = "open"           # Заблокирован
    HALF_OPEN = "half_open" # Проверочный режим

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5        # N последовательных ошибок → Open
    success_threshold: int = 2        # N успешных в Half-Open → Closed
    timeout: float = 30.0             # Секунд в Open перед переходом в Half-Open
    half_open_max_calls: int = 3      # Максимум вызовов в Half-Open

class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs):
        async with self._lock:
            if self._state == CircuitState.OPEN:
                # Проверяем, не пора ли перейти в Half-Open
                if time.monotonic() - self._last_failure_time >= self._config.timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is open. "
                        f"Next retry in "
                        f"{self._config.timeout - (time.monotonic() - self._last_failure_time):.1f}s"
                    )
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is half-open, max probe calls reached"
                    )
                self._half_open_calls += 1
        
        # Выполняем запрос ВНЕ лока (чтобы не блокировать)
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Сброс при успехе
    
    async def _on_failure(self):
        async with self._lock:
            self._last_failure_time = time.monotonic()
            
            if self._state == CircuitState.HALF_OPEN:
                # Провальная проверка — возвращаемся в Open
                self._state = CircuitState.OPEN
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self._config.failure_threshold:
                    self._state = CircuitState.OPEN


# Использование с декоратором
from functools import wraps

def circuit_breaker(name: str, **config_kwargs):
    cb = CircuitBreaker(name, CircuitBreakerConfig(**config_kwargs))
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        return wrapper
    
    return decorator

@circuit_breaker("inventory-service", failure_threshold=5, timeout=30.0)
async def get_stock(product_id: str) -> int:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.get(f"http://inventory-service/stock/{product_id}")
        response.raise_for_status()
        return response.json()['stock']
```

## Популярные библиотеки Circuit Breaker

### Resilience4j (Java)

```java
// Resilience4j — наследник Netflix Hystrix
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .failureRateThreshold(50)          // % ошибок для открытия
    .waitDurationInOpenState(Duration.ofSeconds(30))
    .permittedNumberOfCallsInHalfOpenState(5)
    .slidingWindowSize(10)             // Окно наблюдения
    .build();

CircuitBreaker cb = CircuitBreakerRegistry.of(config).circuitBreaker("inventory");

// Wrapping calls
Supplier<String> decoratedSupplier = CircuitBreaker.decorateSupplier(
    cb, 
    () -> inventoryService.getStock(productId)
);

Try<String> result = Try.ofSupplier(decoratedSupplier)
    .recover(CircuitBreakerOpenException.class, throwable -> "default-value");
```

### Polly (C#/.NET)

```csharp
// Polly — для .NET
var circuitBreakerPolicy = Policy
    .Handle<HttpRequestException>()
    .CircuitBreakerAsync(
        exceptionsAllowedBeforeBreaking: 5,
        durationOfBreak: TimeSpan.FromSeconds(30),
        onBreak: (exception, duration) => 
            logger.LogWarning($"Circuit breaker opened for {duration}"),
        onReset: () => logger.LogInformation("Circuit breaker reset")
    );

var retryPolicy = Policy
    .Handle<HttpRequestException>()
    .WaitAndRetryAsync(
        retryCount: 3,
        sleepDurationProvider: retryAttempt => 
            TimeSpan.FromSeconds(Math.Pow(2, retryAttempt)),
        onRetry: (exception, timeSpan, retryCount, context) =>
            logger.LogWarning($"Retry {retryCount} after {timeSpan}")
    );

// Комбинируем: retry + circuit breaker
var policy = Policy.WrapAsync(retryPolicy, circuitBreakerPolicy);

var result = await policy.ExecuteAsync(() => httpClient.GetStringAsync(url));
```

## Timeout: всегда устанавливай таймауты

**Timeout** — одно из самых важных правил устойчивости. Без таймаутов зависший upstream-сервис занимает все потоки/соединения в пуле, и сервис перестаёт отвечать.

```python
# Никогда не делай HTTP запросы без таймаута!
import httpx

# ПЛОХО: нет таймаута — соединение может зависнуть навсегда
async with httpx.AsyncClient() as client:
    response = await client.get("http://slow-service/data")  # Может ждать вечно!

# ХОРОШО: explicit timeout
async with httpx.AsyncClient(timeout=5.0) as client:
    response = await client.get("http://slow-service/data")

# Ещё лучше: разные таймауты для разных фаз
timeout = httpx.Timeout(
    connect=1.0,    # Установка соединения: 1 секунда
    read=5.0,       # Чтение ответа: 5 секунд
    write=2.0,      # Отправка запроса: 2 секунды
    pool=1.0        # Ожидание свободного соединения из пула: 1 секунда
)

async with httpx.AsyncClient(timeout=timeout) as client:
    response = await client.get("http://slow-service/data")
```

**Cascade Timeout:** При цепочке вызовов A → B → C:
- A даёт timeout 10s B
- B должен дать timeout < 10s C (например 7s), чтобы успеть обработать ошибку и ответить A
- C должен дать timeout < 7s следующему сервису

```python
# Передача deadline через контекст (gRPC подход)
import time

class RequestContext:
    def __init__(self, deadline: float):
        self.deadline = deadline
    
    def remaining_time(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Request deadline exceeded")
        return remaining

async def handle_request(ctx: RequestContext):
    # Из 10 секунд дедлайна оставляем 7 секунд для upstream
    upstream_timeout = min(ctx.remaining_time() * 0.7, 7.0)
    
    async with httpx.AsyncClient(timeout=upstream_timeout) as client:
        return await client.get("http://upstream/data")
```

## Bulkhead: изоляция пулов ресурсов

**Bulkhead** (переборка) — изоляция ресурсов, чтобы сбой в одной части не затронул другую. Термин из кораблестроения: переборки разделяют корпус на отсеки — если один затоплен, корабль не тонет.

```python
import asyncio
from asyncio import Semaphore

class BulkheadedService:
    """
    Разные пулы для критичных и некритичных операций.
    Сбой в некритичных не затронет критичные.
    """
    
    def __init__(self):
        # Критичные операции: максимум 20 параллельных запросов
        self._critical_semaphore = Semaphore(20)
        # Некритичные операции: максимум 5 параллельных запросов
        self._non_critical_semaphore = Semaphore(5)
    
    async def get_user_profile(self, user_id: str) -> dict:
        """Критичная операция — нужна для авторизации."""
        async with self._critical_semaphore:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"http://users/{user_id}")
                return response.json()
    
    async def get_recommendations(self, user_id: str) -> list:
        """Некритичная операция — можно деградировать."""
        try:
            async with asyncio.wait_for(
                self._non_critical_semaphore.acquire(), 
                timeout=0.1  # Если нет свободного слота — сразу fallback
            ):
                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        response = await client.get(f"http://recommendations/{user_id}")
                        return response.json()
                finally:
                    self._non_critical_semaphore.release()
        except (asyncio.TimeoutError, Exception):
            return []  # Fallback: пустой список рекомендаций
```

## Fallback: деградация функциональности

**Fallback** — возвращение альтернативного результата при недоступности сервиса. Ключевой принцип: лучше показать частичные данные, чем полный сбой.

```python
class ProductPageService:
    async def get_product_page(self, product_id: str) -> dict:
        """Получить данные для страницы продукта с fallback."""
        
        # Параллельно получаем все данные
        results = await asyncio.gather(
            self._get_product_info(product_id),
            self._get_inventory(product_id),
            self._get_recommendations(product_id),
            self._get_reviews(product_id),
            return_exceptions=True  # Не падаем при ошибке одного источника
        )
        
        product_info, inventory, recommendations, reviews = results
        
        # Fallback для каждого компонента
        return {
            'product': product_info if not isinstance(product_info, Exception) 
                       else {'error': 'Product info unavailable'},
            
            'in_stock': (inventory > 0) if not isinstance(inventory, Exception)
                        else True,  # Предполагаем что есть (лучше показать чем скрыть)
            
            'recommendations': recommendations if not isinstance(recommendations, Exception)
                               else [],  # Просто не показываем
            
            'reviews': reviews if not isinstance(reviews, Exception)
                       else {'count': 0, 'items': [], 'cached': False},
        }
    
    async def _get_inventory(self, product_id: str) -> int:
        """С кешированием как fallback."""
        try:
            stock = await inventory_service.get_stock(product_id)
            # Кешируем успешный результат
            await cache.set(f"inventory:{product_id}", stock, ttl=300)
            return stock
        except Exception:
            # При сбое инвентаря — берём из кеша
            cached = await cache.get(f"inventory:{product_id}")
            if cached is not None:
                return cached
            raise  # Если нет кеша — пробрасываем исключение
```

## Идемпотентные API

**Идемпотентность** — свойство операции возвращать одинаковый результат при повторном выполнении. `f(f(x)) = f(x)`.

Это критично для retry: если мы повторяем запрос, нужно быть уверены, что деньги не спишутся дважды.

```python
# GET запросы идемпотентны по определению
# PUT идемпотентен (установить значение X — всегда результат X)
# DELETE идемпотентен (удалить уже удалённое — результат тот же)
# POST НЕ идемпотентен по умолчанию (создаёт новый ресурс каждый раз)

# Паттерн: Idempotency Key для non-idempotent операций
import hashlib

@app.post("/payments")
async def create_payment(
    request: PaymentRequest,
    idempotency_key: str = Header(...)  # Клиент отправляет уникальный ключ
):
    """
    Оплата с гарантией идемпотентности.
    Клиент может безопасно повторять запрос с тем же ключом.
    """
    # Проверяем, был ли уже обработан этот запрос
    cached_result = await idempotency_store.get(idempotency_key)
    if cached_result:
        # Возвращаем тот же результат без повторной обработки
        return cached_result
    
    # Блокируем ключ (distributed lock) для защиты от race condition
    async with distributed_lock(f"idempotency:{idempotency_key}", timeout=30):
        # Снова проверяем (double-checked locking)
        cached_result = await idempotency_store.get(idempotency_key)
        if cached_result:
            return cached_result
        
        # Выполняем оплату
        payment = await payment_service.charge(
            request.amount, 
            request.currency,
            request.customer_id
        )
        
        result = {'payment_id': payment.id, 'status': 'completed'}
        
        # Сохраняем результат для будущих повторных запросов
        await idempotency_store.set(
            idempotency_key, 
            result, 
            ttl=86400  # 24 часа
        )
        
        return result
```

```python
# Клиентская сторона: retry с idempotency key
import uuid
import asyncio
import httpx

async def create_payment_with_retry(amount: float, currency: str) -> dict:
    """Безопасный retry оплаты с idempotency key."""
    
    # Генерируем ключ один раз для всей операции
    idempotency_key = str(uuid.uuid4())
    
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.payment-service.com/payments",
                    json={'amount': amount, 'currency': currency},
                    headers={'Idempotency-Key': idempotency_key}
                    # Тот же ключ при каждом retry!
                )
                
                if response.status_code in (200, 201):
                    return response.json()
                elif response.status_code == 409:
                    # Конфликт — платёж уже существует с другим состоянием
                    raise PaymentConflictError()
                elif response.status_code >= 500:
                    # Серверная ошибка — retry
                    raise httpx.HTTPStatusError("Server error", request=None, response=response)
                else:
                    # Клиентская ошибка — не retry
                    response.raise_for_status()
        
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            if attempt == 2:
                raise
            delay = min(30, 1.0 * (2 ** attempt))
            await asyncio.sleep(delay)
```

## Hedged Requests: параллельные резервные запросы

**Hedged Requests** — техника снижения хвостовой latency: если запрос не вернулся за определённое время, отправляем второй параллельный запрос и берём тот, что ответит первым.

```python
import asyncio

async def hedged_request(
    func,
    *args,
    hedge_delay: float = 0.1,  # 100ms: если не ответил — отправляем дублирующий запрос
    **kwargs
):
    """
    Если первый запрос занимает > hedge_delay, отправляем второй.
    Берём ответ от того, кто ответит первым.
    Отменяем второй запрос, если первый ответил.
    """
    result_queue = asyncio.Queue(maxsize=1)
    tasks = []
    
    async def attempt():
        try:
            result = await func(*args, **kwargs)
            try:
                result_queue.put_nowait(result)
            except asyncio.QueueFull:
                pass  # Другой запрос уже ответил
        except Exception as e:
            pass  # Игнорируем ошибки (другой запрос может успешно ответить)
    
    # Запускаем первый запрос
    task1 = asyncio.create_task(attempt())
    tasks.append(task1)
    
    # Ждём hedge_delay, потом запускаем второй
    await asyncio.sleep(hedge_delay)
    
    if result_queue.empty():
        task2 = asyncio.create_task(attempt())
        tasks.append(task2)
    
    # Ждём первого результата
    result = await result_queue.get()
    
    # Отменяем оставшиеся задачи
    for task in tasks:
        task.cancel()
    
    return result

# Использование:
# Вместо ожидания p99 latency — ждём примерно p50 latency
response = await hedged_request(
    get_product,
    product_id,
    hedge_delay=0.05  # 50ms: если не ответил за 50ms — дублируем
)
```

## Chaos Engineering

**Chaos Engineering** — намеренное введение отказов в production для проверки устойчивости системы. Принцип: лучше найти уязвимости в контролируемом эксперименте, чем в критичный момент.

```python
# Netflix Chaos Monkey concept: случайно убиваем инстансы
import random
import asyncio

class ChaosMiddleware:
    """
    Middleware для внедрения хаоса в тестовых окружениях.
    НИКОГДА не включать в продакшне без контроля!
    """
    
    def __init__(
        self,
        error_rate: float = 0.0,    # % запросов с ошибкой
        latency_rate: float = 0.0,  # % запросов с дополнительной задержкой
        latency_ms: float = 500.0,  # Дополнительная задержка в мс
    ):
        self.error_rate = error_rate
        self.latency_rate = latency_rate
        self.latency_ms = latency_ms
    
    async def __call__(self, request, call_next):
        # Вводим задержку
        if random.random() < self.latency_rate:
            await asyncio.sleep(self.latency_ms / 1000)
        
        # Вводим ошибку
        if random.random() < self.error_rate:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=503,
                content={'error': 'Chaos monkey struck!'}
            )
        
        return await call_next(request)

# Настройка для load testing:
# chaos = ChaosMiddleware(error_rate=0.05, latency_rate=0.1, latency_ms=200)
# Это позволяет проверить работу retry и circuit breaker под нагрузкой
```

## Полная картина: комбинирование паттернов

```python
# Реальный пример: все паттерны вместе

class ResilientInventoryClient:
    def __init__(self):
        self._cb = CircuitBreaker(
            "inventory",
            CircuitBreakerConfig(failure_threshold=5, timeout=30.0)
        )
        self._semaphore = asyncio.Semaphore(50)  # Bulkhead: 50 параллельных запросов
    
    async def get_stock(self, product_id: str) -> int:
        async with self._semaphore:
            try:
                return await self._cb.call(
                    self._get_with_retry,
                    product_id
                )
            except CircuitBreakerOpenError:
                # Circuit breaker открыт — берём из кеша
                cached = await cache.get(f"stock:{product_id}")
                return cached if cached is not None else 0  # Fallback
    
    async def _get_with_retry(self, product_id: str) -> int:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(
                        f"http://inventory-service/api/stock/{product_id}"
                    )
                    response.raise_for_status()
                    result = response.json()['stock']
                    
                    # Кешируем успешный результат
                    await cache.set(f"stock:{product_id}", result, ttl=60)
                    return result
            
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt == 2:
                    raise
                delay = equal_jitter(attempt, base=0.5, cap=10.0)
                await asyncio.sleep(delay)
            
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (400, 404):
                    raise  # Не ретраим клиентские ошибки
                if attempt == 2:
                    raise
                delay = equal_jitter(attempt, base=0.5, cap=10.0)
                await asyncio.sleep(delay)
```

## Заключение

Паттерны устойчивости — не опциональные украшения, а обязательные компоненты production-систем:

- **Retry + Jitter** — для временных сбоев с предотвращением thundering herd
- **Circuit Breaker** — для защиты от каскадных сбоев при системных проблемах
- **Timeout** — всегда, без исключений, для всех внешних вызовов
- **Bulkhead** — для изоляции критичных путей от некритичных
- **Fallback** — для graceful degradation
- **Idempotency** — для безопасного retry с гарантиями

Главный принцип: **проектируй системы в расчёте на отказы, не надеясь на надёжность**. Любой внешний вызов может зависнуть, вернуть ошибку или занять вдесятеро больше времени чем обычно.

## Литература

1. **Nygard, Michael T.** — «Release It! Design and Deploy Production-Ready Software», 2nd ed. Pragmatic Bookshelf, 2018. ISBN: 978-1680502398
2. **Netflix Blog** — «Making Netflix API More Resilient» (Hystrix): https://netflixtechblog.com/making-the-netflix-api-more-resilient-a8ec62159c2d
3. **Resilience4j Documentation** — https://resilience4j.readme.io/docs
4. **Polly Documentation** (.NET) — https://www.thepollyproject.org/
5. **Amazon Builders' Library** — «Timeouts, retries, and backoff with jitter»: https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
6. **Fowler, Martin** — «Circuit Breaker» (2014): https://martinfowler.com/bliki/CircuitBreaker.html
7. **Google SRE Book** — «Handling Overload», Chapter 21. O'Reilly, 2016: https://sre.google/sre-book/handling-overload/
8. **Bailis, Peter et al.** — «Highly Available Transactions: Virtues and Limitations». VLDB 2014
9. **Stripe Engineering** — «Idempotency Keys»: https://stripe.com/docs/api/idempotent_requests
10. **Principles of Chaos Engineering** — https://principlesofchaos.org/
