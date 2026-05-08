# Rate Limiting, Throttling, Backpressure — как не утонуть в нагрузке

Любой публичный API рано или поздно сталкивается с избыточным трафиком: боты, некорректно написанные клиенты, DDoS-атаки, внезапный вирусный рост аудитории. Без механизмов управления нагрузкой один перегруженный сервис может вызвать каскадный сбой всей системы. Rate limiting, throttling и backpressure — три взаимосвязанных механизма, которые обеспечивают справедливое использование ресурсов и защиту от перегрузки.

## Зачем нужен Rate Limiting

**Основные задачи:**

1. **Защита от DoS/DDoS** — предотвращение намеренных атак или случайных «бомбардировок»
2. **Справедливое использование** (fairness) — один клиент не должен монополизировать ресурсы
3. **Экономическая защита** — при pay-per-use облачных сервисах неконтролируемый трафик = деньги
4. **Стабильность сервиса** — защита от случайного перегруза (баг в клиенте, runaway job)
5. **Монетизация** — разные тарифные планы с разными лимитами (Free: 1000 req/day, Pro: 100,000 req/day)

```
HTTP 429 Too Many Requests — стандартный ответ при превышении лимита

HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-RateLimit-Limit: 1000        # Лимит в окне
X-RateLimit-Remaining: 0        # Осталось запросов
X-RateLimit-Reset: 1735689600   # Unix timestamp когда сбросится лимит
Retry-After: 3600               # Секунд до возможности повторить

{"error": "Rate limit exceeded", "retry_after": 3600}
```

## Алгоритм 1: Fixed Window Counter

Самый простой алгоритм: счётчик в фиксированном временном окне.

```
Лимит: 5 запросов в минуту
Окно: 13:00:00 - 13:01:00

Запрос в 13:00:01 → Counter=1 (allowed)
Запрос в 13:00:15 → Counter=2 (allowed)
Запрос в 13:00:30 → Counter=3 (allowed)
Запрос в 13:00:45 → Counter=4 (allowed)
Запрос в 13:00:59 → Counter=5 (allowed)
Запрос в 13:00:59.5 → Counter=6 → REJECTED (429)

Сброс в 13:01:00 → Counter=0
Запрос в 13:01:00 → Counter=1 (allowed)
```

**Проблема: Thundering Herd на границе окна**

```
Запросы в конце окна:    13:00:58 → 5 запросов (allowed, last in window)
Запросы в начале окна:   13:01:00 → 5 запросов (allowed, new window)
= 10 запросов за 2 секунды! Лимит 5/мин нарушен.
```

```python
import redis
import time

class FixedWindowRateLimiter:
    def __init__(self, redis_client, limit: int, window_seconds: int):
        self._redis = redis_client
        self._limit = limit
        self._window = window_seconds
    
    def is_allowed(self, key: str) -> tuple[bool, dict]:
        """
        Проверить и зарегистрировать запрос.
        Returns: (is_allowed, metadata)
        """
        # Ключ включает временное окно (округлённое до начала)
        window_start = int(time.time() // self._window) * self._window
        redis_key = f"rate_limit:{key}:{window_start}"
        
        # Атомарное увеличение счётчика
        count = self._redis.incr(redis_key)
        
        # Устанавливаем TTL только при первом обращении
        if count == 1:
            self._redis.expire(redis_key, self._window)
        
        reset_at = window_start + self._window
        remaining = max(0, self._limit - count)
        
        return count <= self._limit, {
            'limit': self._limit,
            'remaining': remaining,
            'reset': reset_at
        }

# Использование в FastAPI
from fastapi import Request, HTTPException

limiter = FixedWindowRateLimiter(redis_client, limit=100, window_seconds=60)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    
    allowed, meta = limiter.is_allowed(f"ip:{client_ip}")
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(meta['limit']),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(meta['reset']),
                "Retry-After": str(meta['reset'] - int(time.time()))
            }
        )
    
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(meta['limit'])
    response.headers["X-RateLimit-Remaining"] = str(meta['remaining'])
    response.headers["X-RateLimit-Reset"] = str(meta['reset'])
    
    return response
```

## Алгоритм 2: Sliding Window Log

Точный алгоритм: храним временные метки всех запросов.

```python
class SlidingWindowLogRateLimiter:
    def __init__(self, redis_client, limit: int, window_seconds: int):
        self._redis = redis_client
        self._limit = limit
        self._window = window_seconds
    
    def is_allowed(self, key: str) -> tuple[bool, dict]:
        now = time.time()
        window_start = now - self._window
        redis_key = f"rate_log:{key}"
        
        pipe = self._redis.pipeline()
        
        # Удаляем записи старее окна
        pipe.zremrangebyscore(redis_key, '-inf', window_start)
        
        # Добавляем текущий запрос (score=timestamp, member=timestamp:random)
        import random
        member = f"{now}:{random.random()}"
        pipe.zadd(redis_key, {member: now})
        
        # Считаем запросы в окне
        pipe.zcard(redis_key)
        
        # Устанавливаем TTL
        pipe.expire(redis_key, self._window + 1)
        
        results = pipe.execute()
        count = results[2]
        
        return count <= self._limit, {
            'limit': self._limit,
            'remaining': max(0, self._limit - count),
            'reset': int(now + self._window)
        }
```

**Преимущества:** точный — нет проблемы с границами окон.

**Недостатки:** дорогой по памяти — храним каждый запрос. Для $1000\ \text{req/min} \times 1000$ пользователей = 1,000,000 записей в Redis.

## Алгоритм 3: Sliding Window Counter

Компромисс между Fixed Window (дёшево, не точно) и Sliding Window Log (точно, дорого):

```
Идея: комбинируем текущее и предыдущее окно с весовым коэффициентом

current_rate = 
    prev_window_count * ((window_end - now) / window_size) +  # "старый" вклад
    current_window_count

Пример:
  window_size = 60s
  Сейчас: 13:01:40 (40 секунд прошло в текущем окне)
  prev_window (13:00-13:01): 80 запросов
  current_window (13:01-13:02): 30 запросов
  
  remaining_prev = (60 - 40) / 60 = 0.33 (33% предыдущего окна ещё "действует")
  estimated_rate = 80 * 0.33 + 30 = 56.4 запроса
```

```python
class SlidingWindowCounterRateLimiter:
    def __init__(self, redis_client, limit: int, window_seconds: int):
        self._redis = redis_client
        self._limit = limit
        self._window = window_seconds
    
    def is_allowed(self, key: str) -> tuple[bool, dict]:
        now = time.time()
        current_window = int(now // self._window) * self._window
        prev_window = current_window - self._window
        elapsed = now - current_window  # Прошло секунд в текущем окне
        
        current_key = f"rate:{key}:{current_window}"
        prev_key = f"rate:{key}:{prev_window}"
        
        pipe = self._redis.pipeline()
        pipe.get(prev_key)
        pipe.incr(current_key)
        pipe.expire(current_key, self._window * 2)
        results = pipe.execute()
        
        prev_count = int(results[0] or 0)
        current_count = results[1]
        
        # Взвешенная оценка
        prev_weight = (self._window - elapsed) / self._window
        estimated_count = prev_count * prev_weight + current_count
        
        return estimated_count <= self._limit, {
            'limit': self._limit,
            'remaining': max(0, int(self._limit - estimated_count)),
            'reset': current_window + self._window
        }
```

## Алгоритм 4: Token Bucket

**Token Bucket** — самый популярный алгоритм для rate limiting с поддержкой burst.

```
Представьте ведро:
- Вместимость: 100 токенов (max burst)
- Скорость пополнения: 10 токенов/секунда (1000 req/min = 10/s)

Запрос приходит → берём 1 токен из ведра
Ведро пополняется постоянно со скоростью 10 токенов/секунду
Если ведро пусто → 429

Burst: если клиент молчал 10 секунд → накопилось 100 токенов (max)
       может сделать 100 запросов подряд "бесплатно"
```

```python
import time
import threading

class TokenBucketRateLimiter:
    def __init__(
        self,
        capacity: int,       # Максимальный размер ведра
        refill_rate: float,  # Токенов в секунду
    ):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = capacity  # Начинаем с полным ведром
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            
            # Пополняем ведро
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed * self._refill_rate
            )
            self._last_refill = now
            
            # Пробуем взять токены
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False
    
    def tokens_remaining(self) -> float:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            return min(self._capacity, self._tokens + elapsed * self._refill_rate)


# Redis-based Token Bucket (для distributed rate limiting)
LUA_TOKEN_BUCKET = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local tokens_requested = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

-- Пополняем ведро
local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= tokens_requested then
    tokens = tokens - tokens_requested
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) * 2)
    return {1, math.floor(tokens)}  -- allowed, remaining
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    return {0, math.floor(tokens)}  -- denied, remaining
end
"""

class RedisTokenBucket:
    def __init__(self, redis_client, capacity: int, refill_rate: float):
        self._redis = redis_client
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._script = redis_client.register_script(LUA_TOKEN_BUCKET)
    
    def is_allowed(self, key: str, tokens: int = 1) -> tuple[bool, int]:
        result = self._script(
            keys=[f"tb:{key}"],
            args=[self._capacity, self._refill_rate, time.time(), tokens]
        )
        return bool(result[0]), int(result[1])
```

## Алгоритм 5: Leaky Bucket

**Leaky Bucket** (дырявое ведро) — обеспечивает строго постоянную скорость обработки запросов, независимо от burst.

```
Ведро с дыркой внизу:
- Запросы попадают в ведро (очередь)
- Обрабатываются с постоянной скоростью (например, 100 req/s)
- Если ведро переполнено → отклоняем запрос

Отличие от Token Bucket:
- Token Bucket: burst разрешён (100 запросов сразу, если есть токены)
- Leaky Bucket: строго 100 req/s, буфер только для выравнивания
```

```python
import asyncio
import time
from collections import deque

class LeakyBucket:
    def __init__(
        self,
        capacity: int,       # Размер очереди (буфер)
        drain_rate: float,   # Скорость обработки (запросов/секунда)
    ):
        self._capacity = capacity
        self._drain_interval = 1.0 / drain_rate  # Секунд на один запрос
        self._queue: deque = deque()
        self._last_drain = time.monotonic()
    
    async def submit(self, request_func) -> bool:
        """
        Добавить запрос в очередь.
        Returns False если очередь полна (429).
        """
        if len(self._queue) >= self._capacity:
            return False
        
        self._queue.append(request_func)
        return True
    
    async def drain(self):
        """Обрабатываем запросы с постоянной скоростью."""
        while True:
            if self._queue:
                request_func = self._queue.popleft()
                await request_func()
            await asyncio.sleep(self._drain_interval)
```

## Rate Limiting по различным ключам

```python
from enum import Enum

class RateLimitScope(Enum):
    IP = "ip"
    USER_ID = "user"
    API_KEY = "api_key"
    GLOBAL = "global"

class MultiScopeRateLimiter:
    """Rate limiting по нескольким ключам одновременно."""
    
    def __init__(self, redis_client):
        self._redis = redis_client
        
        # Разные лимиты для разных уровней
        self._limiters = {
            RateLimitScope.IP: SlidingWindowCounterRateLimiter(
                redis_client, limit=100, window_seconds=60
            ),
            RateLimitScope.USER_ID: SlidingWindowCounterRateLimiter(
                redis_client, limit=1000, window_seconds=60
            ),
            RateLimitScope.API_KEY: {
                'free': SlidingWindowCounterRateLimiter(redis_client, limit=100, window_seconds=3600),
                'pro': SlidingWindowCounterRateLimiter(redis_client, limit=10000, window_seconds=3600),
                'enterprise': SlidingWindowCounterRateLimiter(redis_client, limit=1000000, window_seconds=3600),
            }
        }
    
    def check_all(
        self,
        ip: str,
        user_id: str = None,
        api_key: str = None,
        api_tier: str = 'free'
    ) -> tuple[bool, str]:
        """
        Проверяем все применимые лимиты.
        Возвращаем False при превышении любого из них.
        """
        
        # IP лимит (защита от ботов)
        allowed, meta = self._limiters[RateLimitScope.IP].is_allowed(ip)
        if not allowed:
            return False, f"IP rate limit exceeded ({meta['limit']}/min)"
        
        # User лимит (если аутентифицирован)
        if user_id:
            allowed, meta = self._limiters[RateLimitScope.USER_ID].is_allowed(user_id)
            if not allowed:
                return False, f"User rate limit exceeded ({meta['limit']}/min)"
        
        # API key лимит
        if api_key:
            tier_limiter = self._limiters[RateLimitScope.API_KEY][api_tier]
            allowed, meta = tier_limiter.is_allowed(api_key)
            if not allowed:
                return False, f"API key rate limit exceeded for {api_tier} tier"
        
        return True, "OK"
```

## Distributed Rate Limiting: синхронизация между инстансами

При горизонтальном масштабировании (несколько инстансов API) локальные счётчики не работают — каждый инстанс видит только свой трафик.

```
┌──────────────────────────────────────────────────────────┐
│                    Load Balancer                          │
└──────────────────────────────────────────────────────────┘
        │              │              │
   ┌────▼────┐    ┌────▼────┐   ┌────▼────┐
   │ API #1  │    │ API #2  │   │ API #3  │
   │         │    │         │   │         │
   │ local   │    │ local   │   │ local   │
   │ counter │    │ counter │   │ counter │
   │ = 30    │    │ = 35    │   │ = 35    │
   └────────-┘    └─────────┘   └─────────┘
                                 ↑
                          Проблема: клиент сделал 100 запросов,
                          но счётчик видит только 35 на одном инстансе!

Решение: централизованный Redis
   ┌────────┐    ┌────────┐   ┌────────┐
   │ API #1 │    │ API #2 │   │ API #3 │
   └────────┘    └────────┘   └────────┘
        │              │            │
        └──────────────┼────────────┘
                       │
              ┌────────▼────────┐
              │   Redis Cluster  │
              │  (centralized    │
              │   counters)      │
              └─────────────────┘
```

```python
# Lua script для атомарного distributed rate limiting в Redis
# (все операции атомарны — нет race condition)
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Удаляем старые записи
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)

-- Добавляем текущий запрос
redis.call('ZADD', key, now, now .. ':' .. math.random())

-- Считаем
local count = redis.call('ZCARD', key)
redis.call('EXPIRE', key, window)

return {count, count <= limit}
"""
```

**Проблема с distributed rate limiting:** каждый запрос к API = запрос к Redis (дополнительная latency ~0.5-2ms). При очень высоких нагрузках это может стать узким местом.

**Решение: Local + Global Счётчики**

```python
class HybridRateLimiter:
    """
    Комбинирует локальный и Redis счётчик для производительности.
    Локальный счётчик: быстрый (~0нс), неточный
    Redis счётчик: точный, но медленный (~1ms)
    
    Стратегия: проверяем локальный (быстро) → при приближении к лимиту
    синхронизируем с Redis (точно)
    """
    
    def __init__(self, redis_client, limit: int, window: int, sync_threshold: float = 0.8):
        self._redis = redis_client
        self._limit = limit
        self._window = window
        self._sync_threshold = sync_threshold  # Синхронизируем при 80% лимита
        
        # Локальный счётчик (thread-safe)
        self._local_count = 0
        self._local_window_start = time.time()
        self._lock = threading.Lock()
    
    def is_allowed(self, key: str) -> bool:
        with self._lock:
            now = time.time()
            
            # Сброс при новом окне
            if now - self._local_window_start >= self._window:
                self._local_count = 0
                self._local_window_start = now
            
            self._local_count += 1
            local_ratio = self._local_count / self._limit
        
        # Если далеко от лимита — только локальная проверка (быстро)
        if local_ratio < self._sync_threshold:
            return True
        
        # При приближении к лимиту — синхронизируем с Redis
        redis_count = self._sync_with_redis(key)
        return redis_count <= self._limit
    
    def _sync_with_redis(self, key: str) -> int:
        # Записываем локальный вклад в Redis
        # ... (аналогично предыдущим примерам)
        pass
```

## HTTP 429 и Retry-After заголовки

```python
# Стандартные заголовки по RFC 6585
from fastapi import HTTPException
from fastapi.responses import JSONResponse

def rate_limit_response(
    limit: int, 
    remaining: int, 
    reset_at: int,
    retry_after: int
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": "Too Many Requests",
            "message": f"Rate limit of {limit} requests exceeded. Retry after {retry_after} seconds.",
            "retry_after": retry_after
        },
        headers={
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
            "Retry-After": str(retry_after),  # RFC 7231 — либо секунды, либо HTTP-date
        }
    )

# Клиентская сторона: обрабатываем Retry-After
import httpx
import asyncio

async def api_call_with_respect(url: str, **kwargs) -> dict:
    """Клиент, уважающий rate limit заголовки."""
    response = await client.get(url, **kwargs)
    
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 60))
        print(f"Rate limited. Waiting {retry_after} seconds...")
        await asyncio.sleep(retry_after)
        return await api_call_with_respect(url, **kwargs)  # Повторяем
    
    return response.json()
```

## Nginx Rate Limiting

```nginx
# nginx.conf — rate limiting на уровне веб-сервера

http {
    # Зоны для rate limiting
    # zone=api_limit:10m — 10MB памяти для хранения состояния
    # rate=10r/s — 10 запросов в секунду
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $http_x_api_key zone=apikey_limit:10m rate=100r/s;
    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=1r/s;
    
    server {
        location /api/ {
            # burst=20: разрешаем burst до 20 запросов
            # nodelay: не задерживать burst запросы, обрабатывать сразу
            limit_req zone=api_limit burst=20 nodelay;
            limit_req zone=apikey_limit burst=200 nodelay;
            
            # Код ответа при превышении лимита
            limit_req_status 429;
            
            proxy_pass http://backend;
        }
        
        location /auth/login {
            # Строгий лимит для предотвращения brute force
            limit_req zone=login_limit;
            limit_req_status 429;
            proxy_pass http://auth_service;
        }
    }
}
```

## Cloudflare Rate Limiting

```yaml
# Cloudflare Workers KV для distributed rate limiting
# (через CF API или Terraform)

# Конфигурация Cloudflare Rate Limiting Rule (через API)
{
  "description": "API Rate Limit",
  "expression": "(http.request.uri.path matches \"^/api/\")",
  "action": "block",
  "ratelimit": {
    "characteristics": ["ip.src"],
    "period": 60,
    "requests_per_period": 100,
    "mitigation_timeout": 600
  }
}
```

## Backpressure в потоковых системах

**Backpressure** (обратное давление) — механизм, при котором потребитель сообщает производителю о своей перегрузке, замедляя поток данных.

Аналогия: кран и раковина. Если раковина переполнена — закрываем кран. В системах: если очередь полна — останавливаем производителя.

```python
# Backpressure в asyncio (Producer-Consumer pattern)
import asyncio

async def producer(queue: asyncio.Queue, data_source):
    """Производитель с backpressure через Queue."""
    async for item in data_source:
        # asyncio.Queue блокирует при заполнении (maxsize)
        # Это и есть backpressure — производитель ждёт потребителя
        await queue.put(item)

async def consumer(queue: asyncio.Queue):
    """Потребитель."""
    while True:
        item = await queue.get()
        await process_item(item)
        queue.task_done()

async def main():
    # maxsize=100: при 100 элементах в очереди producer начнёт ждать
    queue = asyncio.Queue(maxsize=100)
    
    producer_task = asyncio.create_task(producer(queue, data_source))
    consumer_tasks = [
        asyncio.create_task(consumer(queue))
        for _ in range(5)  # 5 параллельных потребителей
    ]
    
    await producer_task
    await queue.join()
```

### TCP Backpressure

TCP имеет встроенный механизм backpressure через **receive window**:

```
Клиент                              Сервер
   │                                    │
   │── ACK (window_size=65535) ─────────│
   │                                    │
   │← Data (32KB) ──────────────────────│
   │── ACK (window_size=33535) ─────────│  ← Буфер заполняется
   │                                    │
   │← Data (32KB) ──────────────────────│
   │── ACK (window_size=1535) ──────────│  ← "Медленнее!"
   │                                    │
   │← Data (1KB) ───────────────────────│  ← Сервер замедлился
   │── ACK (window_size=535) ───────────│
   │                                    │
   │── ACK (window_size=0) ─────────────│  ← "Стоп!" (Zero Window)
   ...приложение читает данные из буфера...
   │── ACK (window_size=65535) ─────────│  ← "Можно продолжать"
```

### Reactive Streams Backpressure

**Reactive Streams** (RxJava, Project Reactor, Akka Streams) — стандарт для асинхронных потоков с backpressure.

```java
// Project Reactor: backpressure через Flux
Flux.range(1, 1000000)
    .onBackpressureBuffer(100)     // Буфер 100 элементов
    .publishOn(Schedulers.parallel())
    .flatMap(i -> processItem(i), 5)  // 5 параллельных задач
    .subscribe(
        result -> System.out.println("Processed: " + result),
        error -> System.err.println("Error: " + error),
        () -> System.out.println("Done"),
        subscription -> subscription.request(10)  // Запросить 10 элементов
    );
```

## Сравнение алгоритмов

| Алгоритм | Burst | Точность | Память | Сложность |
|----------|-------|----------|--------|-----------|
| Fixed Window | Нет (граница окна) | Средняя | O(1) | Низкая |
| Sliding Window Log | Нет | Высокая | O(requests) | Средняя |
| Sliding Window Counter | Частично | Высокая | O(1) | Средняя |
| Token Bucket | Да | Средняя | O(1) | Средняя |
| Leaky Bucket | Нет | Высокая | O(capacity) | Средняя |

**Рекомендации по выбору:**
- **API защита (общий случай)** → Sliding Window Counter + Redis
- **Поддержка burst (CDN, публичный API)** → Token Bucket
- **Строгая постоянная скорость (очереди)** → Leaky Bucket
- **Простота и скорость** → Fixed Window (с осознанием ограничений)

## Заключение

Rate limiting — это не просто защита от DDoS. Это фундаментальный механизм обеспечения справедливости, стабильности и предсказуемости вашего сервиса. Без него один плохо написанный клиент может обрушить сервис для всех остальных.

Ключевые принципы:
- **Всегда возвращайте Retry-After** — уважайте клиентов
- **Используйте Redis для distributed rate limiting** — локальные счётчики не работают при масштабировании
- **Разные лимиты для разных tier** — не штрафуйте Pro пользователей как Free
- **Backpressure > dropped requests** — лучше замедлить производителя, чем терять данные

## Литература

1. **Kleppmann, Martin** — «Designing Data-Intensive Applications», Chapter 12. O'Reilly, 2017. ISBN: 978-1449373320
2. **RFC 6585** — «Additional HTTP Status Codes» (429 Too Many Requests): https://www.rfc-editor.org/rfc/rfc6585
3. **RFC 7231** — «HTTP/1.1 Semantics and Content» (Retry-After header): https://www.rfc-editor.org/rfc/rfc7231
4. **Amazon Builders' Library** — «Using load shedding to avoid overload»: https://aws.amazon.com/builders-library/using-load-shedding-to-avoid-overload/
5. **Cloudflare Blog** — «How we built rate limiting capable of scaling to millions of domains»: https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
6. **Nginx Documentation** — «ngx_http_limit_req_module»: https://nginx.org/en/docs/http/ngx_http_limit_req_module.html
7. **Reactive Streams Specification** — https://www.reactive-streams.org/
8. **Google SRE Book** — «Handling Overload», Chapter 21: https://sre.google/sre-book/handling-overload/
9. **Kong** — «Rate Limiting in API Gateways»: https://konghq.com/blog/engineering/how-to-design-a-scalable-rate-limiting-algorithm
10. **Stripe Engineering** — «Rate Limiting, Cells, and GCRA»: https://stripe.com/blog/rate-limiters
