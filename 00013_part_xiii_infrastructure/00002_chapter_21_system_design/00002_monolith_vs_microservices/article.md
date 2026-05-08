# Монолит vs Микросервисы — оба правильны, в зависимости от масштаба и команды

В индустрии существует устойчивый миф: монолиты — это плохо и устарело, микросервисы — это современно и правильно. Реальность сложнее. Amazon, Netflix, Uber переехали на микросервисы — и это правда. Но это была вынужденная мера при определённых масштабах и проблемах, а не идеологический выбор. Понимание, когда и зачем использовать каждый подход, — признак зрелого архитектора.

## Что такое монолит

Монолит — приложение, в котором все компоненты собраны и развёртываются вместе как единый процесс (или набор одинаковых процессов за балансировщиком).

```
┌─────────────────────────────────────────────────────────────┐
│                    Монолитное приложение                     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Catalog    │  │   Ordering   │  │    Shipping      │  │
│  │   Module     │  │   Module     │  │    Module        │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Payment    │  │    Users     │  │  Notifications   │  │
│  │   Module     │  │   Module     │  │    Module        │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│             ┌────────────────────────┐                     │
│             │  Shared Database       │                     │
│             │  (PostgreSQL)          │                     │
│             └────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
        ▲          Деплоится одним артефактом
```

Монолит не означает «плохой код». Хорошо организованный монолит может иметь чёткую модульную структуру, высокое покрытие тестами и хорошую архитектуру.

```python
# Структура хорошо организованного монолита (Django)
# myapp/
# ├── catalog/
# │   ├── models.py
# │   ├── views.py
# │   ├── services.py   # бизнес-логика
# │   └── tests/
# ├── ordering/
# │   ├── models.py
# │   ├── views.py
# │   ├── services.py
# │   └── tests/
# └── shipping/
#     ├── models.py
#     └── services.py

# В ordering/services.py — вызов catalog через код, не HTTP
from catalog.services import get_product_price
from shipping.services import calculate_shipping_cost

class OrderService:
    def create_order(self, user_id: int, items: list) -> Order:
        # Прямой вызов функции — 100нс, не 1ms HTTP!
        total = sum(
            get_product_price(item.product_id) * item.quantity
            for item in items
        )
        shipping = calculate_shipping_cost(user_id, items)
        
        order = Order.objects.create(
            user_id=user_id,
            total=total + shipping
        )
        return order
```

## Преимущества монолита

### 1. Простота развёртывания

```bash
# Деплой монолита
git push heroku main
# Всё. Одна команда, одна версия, один артефакт.

# Деплой 50 микросервисов:
# - Обновить service-a (но сначала проверить совместимость с service-b v1.2)
# - Обновить service-b (учесть breaking changes в API)
# - Запустить интеграционные тесты между сервисами
# - Координировать rollout
# - Следить за 50 дашбордами
```

### 2. Транзакции — бесплатно

В монолите с общей базой данных ACID-транзакции работают без усилий:

```python
# Монолит: транзакция через ORM — тривиально
from django.db import transaction

@transaction.atomic
def process_order(user_id: int, items: list, payment_data: dict):
    # Всё в одной транзакции — либо всё, либо ничего
    order = Order.objects.create(user_id=user_id, status='pending')
    
    for item in items:
        OrderItem.objects.create(
            order=order,
            product_id=item.product_id,
            quantity=item.quantity
        )
        # Уменьшаем остатки
        Product.objects.filter(id=item.product_id).update(
            stock=F('stock') - item.quantity
        )
    
    Payment.objects.create(
        order=order,
        amount=order.total,
        status='completed'
    )
    
    order.status = 'confirmed'
    order.save()
    # Если любое из вышеперечисленного упадёт — всё откатится
```

В микросервисах это становится распределённой транзакцией — одной из самых сложных проблем в CS.

### 3. Низкая latency внутренних вызовов

```
Вызов функции внутри монолита:     ~0.1 мкс
HTTP вызов между микросервисами:   ~1-5 мс (в одном датацентре)
Разница: 10,000x - 50,000x
```

Для интенсивно взаимодействующих модулей эта разница критична.

### 4. Простота разработки и дебаггинга

```bash
# Запустить весь стек локально:
python manage.py runserver
# Один процесс, один лог, один дебаггер

# Vs микросервисы локально:
docker-compose up --scale api=2  # 15 контейнеров
# Открыть 8 терминалов для логов разных сервисов
# Настроить distributed tracing
# Разобраться, почему запрос прошёл через 7 сервисов и упал на 8-м
```

## Проблемы монолита при росте

### 1. Конфликты между командами

При достаточно большой кодовой базе несколько команд работают в одном репозитории. Конфликты merge, непреднамеренные зависимости, риск случайно сломать чужой модуль:

```python
# Team A изменяет signature функции в shared utils:
def calculate_price(product_id: int, quantity: int) -> Decimal:  # было без quantity
    ...

# Team B и Team C сразу получают сломанные тесты
# Нужна координация → замедление разработки
```

### 2. Длинные циклы CI/CD

```bash
# При 1 000 000 строк кода:
git push
# Running tests... (запускаются ВСЕ тесты монолита)
# ... 45 minutes later ...
# Deploy started (перезапускается всё приложение)
# ... 10 minutes ...

# Изменение 10 строк кода занимает 55 минут pipeline
```

### 3. Невозможность масштабировать модули независимо

```
          ┌─────────────────────────────────────┐
          │           Монолит                    │
          │  [Catalog][Orders][Payments][Search] │
          └─────────────────────────────────────┘
                         × 5 (масштабирование)
          ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
          │ All │ │ All │ │ All │ │ All │ │ All │
          └─────┘ └─────┘ └─────┘ └─────┘ └─────┘

Проблема: Search нужно масштабировать x10,
но приходится масштабировать всё приложение вместе.
```

### 4. Технологический долг

Сложно мигрировать части приложения на новые технологии. Весь монолит написан на Python 2.7? Миграция на Python 3 — это задача для всей компании одновременно.

## Что такое микросервисы

Микросервисная архитектура — стиль, при котором приложение разбивается на маленькие, независимо развёртываемые сервисы, каждый из которых отвечает за свою бизнес-функцию.

```
┌────────────────────────────────────────────────────────────────┐
│                    API Gateway                                  │
└────────────────────────────────────────────────────────────────┘
         │            │            │            │
    ┌────▼───┐   ┌────▼───┐  ┌────▼───┐   ┌────▼────┐
    │Catalog │   │Ordering│  │Payments│   │Shipping │
    │Service │   │Service │  │Service │   │Service  │
    │        │   │        │  │        │   │         │
    │ Own DB │   │ Own DB │  │ Own DB │   │ Own DB  │
    └────────┘   └────────┘  └────────┘   └─────────┘
       MySQL      Postgres    Postgres       MongoDB
```

**Ключевые принципы микросервисов:**
- Каждый сервис имеет свою базу данных (database per service)
- Общение через API (HTTP/REST, gRPC, message queues)
- Независимый деплой каждого сервиса
- Маленький размер (команда из 2-8 человек может владеть сервисом)

## Закон Конвея

**Melvin Conway, 1967:** «Организации, которые проектируют системы, ограничены в том, что могут произвести дизайном, который копирует коммуникационную структуру организации».

```
Компания с тремя командами:

Команда UI → создаёт frontend
Команда API → создаёт backend
Команда DB → создаёт базу данных

Результат: трёхуровневая архитектура (UI → API → DB)

──────────────────────────────────────────────────────

Компания, организованная по доменам:

Команда Catalog → создаёт весь Catalog домен
Команда Orders → создаёт весь Orders домен
Команда Payments → создаёт весь Payments домен

Результат: доменно-ориентированная микросервисная архитектура
```

**Обратный манёвр Конвея (Reverse Conway Maneuver):** Если вы хотите изменить архитектуру — сначала измените структуру команд. Нельзя мигрировать на микросервисы, оставив централизованную командную структуру.

## Когда микросервисы НЕ нужны

Это важнейший раздел статьи. Большинство команд, переходящих на микросервисы, делают это преждевременно.

**Сигналы что вы ещё не готовы:**

1. **Маленькая команда (< 10 разработчиков)**
   ```
   Netflix: 1000+ инженеров, 700+ микросервисов
   Ваш стартап: 5 инженеров, переходите на микросервисы
   
   Проблема: вы получаете сложность Netflix без его масштаба.
   ```

2. **Нет DevOps/Platform команды**
   Микросервисы требуют: CI/CD для каждого сервиса, service discovery, distributed tracing, централизованные логи, health checks... Без инфраструктурной команды это ложится на разработчиков и убивает продуктивность.

3. **Неясные доменные границы**
   ```python
   # Если вы не уверены как разделить домены — не разделяйте!
   # "Что делает Checkout сервис?"
   # "Он... ну, обрабатывает заказы. И управляет корзиной. И иногда обновляет инвентарь."
   # Это НЕ чёткая граница. Делать отдельный сервис рано.
   ```

4. **Начальная стадия продукта**
   На MVP-стадии требования меняются еженедельно. Перемещать границы микросервисов при изменении требований — мучительно. Монолит позволяет рефакторить свободно.

## Strangler Fig Pattern: постепенная миграция

Strangler Fig (смоковница-паразит) — паттерн постепенной миграции с монолита на микросервисы без переписывания с нуля.

```
┌────────────────────────────────────────────────────────────┐
│                     API Gateway / Proxy                     │
└────────────────────────────────────────────────────────────┘
        │                                    │
        ▼ (старый код)                       ▼ (новый сервис)
┌──────────────┐                     ┌──────────────────────┐
│   Монолит    │◄─ всё ещё работает  │  Search Microservice │
│              │                     │  (выделен из монолита│
│  /search/* ──┼─────── прокси ─────►│   и работает         │
│  (старый)    │                     │   независимо)        │
└──────────────┘                     └──────────────────────┘
```

Шаги:
1. Выбрать один модуль с чёткими границами (например, Search)
2. Создать новый независимый сервис
3. Перенаправить трафик через прокси/API Gateway
4. Мигрировать данные
5. Удалить старый код из монолита
6. Повторить для следующего модуля

```python
# API Gateway: Strangler Fig — прокси для постепенной миграции
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

SERVICES = {
    '/api/search/': 'http://search-service:8001',
    '/api/payments/': 'http://payments-service:8002',
    # Всё остальное — идёт в монолит
}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str):
    """Прокси: новые сервисы или монолит."""
    
    # Ищем новый сервис
    for prefix, service_url in SERVICES.items():
        if f"/{path}".startswith(prefix):
            # Перенаправляем в новый микросервис
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=request.method,
                    url=f"{service_url}/{path}",
                    headers=dict(request.headers),
                    content=await request.body(),
                )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
    
    # Остальное — в монолит
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=f"http://monolith:8000/{path}",
            headers=dict(request.headers),
            content=await request.body(),
        )
    return Response(content=response.content, status_code=response.status_code)
```

## Распределённые транзакции: главная боль микросервисов

Когда бизнес-операция охватывает несколько сервисов с разными базами данных, ACID-транзакция невозможна. Приходится выбирать между несколькими паттернами.

### SAGA Pattern

```python
# SAGA: последовательность локальных транзакций с компенсирующими операциями
# Паттерн: Choreography (через события) или Orchestration (через orchestrator)

# Orchestration SAGA:
class OrderSaga:
    """
    Шаги:
    1. Зарезервировать товары (Inventory Service)
    2. Провести оплату (Payment Service)
    3. Подтвердить заказ (Order Service)
    
    При сбое на любом шаге — компенсирующие транзакции:
    - Отменить оплату (если payment прошёл, но order упал)
    - Освободить резерв (если inventory зарезервирован, но payment упал)
    """
    
    async def execute(self, order_data: dict) -> dict:
        steps = []
        
        try:
            # Шаг 1: резерв товаров
            reservation = await inventory_service.reserve(order_data['items'])
            steps.append(('inventory', reservation['id']))
            
            # Шаг 2: оплата
            payment = await payment_service.charge(
                order_data['user_id'],
                order_data['total']
            )
            steps.append(('payment', payment['id']))
            
            # Шаг 3: подтверждение
            order = await order_service.confirm(order_data)
            return order
        
        except Exception as e:
            # Откат в обратном порядке
            for step_type, step_id in reversed(steps):
                try:
                    if step_type == 'payment':
                        await payment_service.refund(step_id)
                    elif step_type == 'inventory':
                        await inventory_service.release_reservation(step_id)
                except Exception as compensation_error:
                    # Логируем и помещаем в очередь на повторную попытку
                    logger.error(f"Compensation failed: {compensation_error}")
                    await dead_letter_queue.publish({'step': step_type, 'id': step_id})
            
            raise e
```

### Eventual Consistency через события

```python
# Choreography SAGA через события (Kafka)
# Каждый сервис публикует события и реагирует на события других

# OrderService: создаёт заказ и публикует событие
async def create_order(order_data: dict):
    order = await db.create_order(order_data, status='pending')
    
    await kafka_producer.send('order.created', {
        'order_id': order.id,
        'items': order_data['items'],
        'user_id': order_data['user_id'],
        'total': order_data['total']
    })
    
    return order

# InventoryService: слушает order.created
@kafka_consumer('order.created')
async def on_order_created(event: dict):
    try:
        await reserve_stock(event['items'])
        await kafka_producer.send('inventory.reserved', {
            'order_id': event['order_id']
        })
    except InsufficientStockError:
        await kafka_producer.send('inventory.reservation_failed', {
            'order_id': event['order_id'],
            'reason': 'insufficient_stock'
        })

# PaymentService: слушает inventory.reserved
@kafka_consumer('inventory.reserved')
async def on_inventory_reserved(event: dict):
    order = await get_order_details(event['order_id'])
    try:
        await charge_payment(order)
        await kafka_producer.send('payment.completed', {
            'order_id': event['order_id']
        })
    except PaymentError:
        await kafka_producer.send('payment.failed', {'order_id': event['order_id']})

# OrderService: слушает payment.completed
@kafka_consumer('payment.completed')
async def on_payment_completed(event: dict):
    await update_order_status(event['order_id'], 'confirmed')
```

## Service Discovery

В микросервисной архитектуре сервисы должны находить друг друга. IP-адреса динамические (контейнеры пересоздаются), поэтому нужен реестр сервисов.

```python
# Client-Side Discovery с Consul
import consul

class ServiceDiscovery:
    def __init__(self):
        self.consul = consul.Consul(host='consul', port=8500)
    
    def get_service_url(self, service_name: str) -> str:
        """Получить адрес здорового инстанса сервиса."""
        _, services = self.consul.health.service(
            service_name,
            passing=True  # только здоровые
        )
        
        if not services:
            raise ServiceNotAvailableError(f"{service_name} unavailable")
        
        # Round-robin выбор
        service = random.choice(services)
        address = service['Service']['Address']
        port = service['Service']['Port']
        
        return f"http://{address}:{port}"

# В Kubernetes: service discovery встроен через DNS
# inventory-service → ClusterIP Service → healthy Pods
# Просто: http://inventory-service/api/...
```

## Majestic Monolith и Modular Monolith

Не все ситуации требуют выбора между «полным монолитом» и «полными микросервисами». Существуют промежуточные подходы.

### Majestic Monolith

Термин, популяризированный DHH (David Heinemeier Hansson, создатель Rails): единый хорошо структурированный монолит, который намеренно НЕ разбивается на микросервисы. Basecamp, GitHub долгое время работали именно так.

### Modular Monolith

Единый деплой, но чёткие модульные границы в коде с явно определёнными интерфейсами:

```python
# Modular Monolith: модули общаются только через публичные интерфейсы
# catalog/public.py — только этот файл доступен другим модулям
from typing import Protocol

class CatalogService(Protocol):
    def get_product(self, product_id: int) -> ProductDTO:
        ...
    
    def reserve_product(self, product_id: int, quantity: int) -> ReservationDTO:
        ...

# ordering/services.py — импортирует только публичный интерфейс
from catalog.public import CatalogService

class OrderingService:
    def __init__(self, catalog: CatalogService):
        self.catalog = catalog
    
    def create_order(self, items: list) -> Order:
        # Работает через абстракцию — не знает о внутренностях Catalog
        product = self.catalog.get_product(items[0].product_id)
        ...

# Преимущество: если позже нужно выделить Catalog в сервис —
# граница уже определена, нужно только добавить HTTP клиент
```

## Team Topologies и архитектура

Книга «Team Topologies» (Skelton & Pais, 2019) предлагает фреймворк для организации команд вокруг программных систем.

**Четыре типа команд:**
1. **Stream-aligned teams** — команды, выровненные по потоку создания ценности (владеют доменом от разработки до продакшна)
2. **Enabling teams** — помогают stream-aligned командам освоить новые технологии
3. **Complicated-subsystem teams** — владеют сложными подсистемами (ML, криптография)
4. **Platform teams** — создают внутреннюю платформу (инфраструктура, CI/CD)

```
Platform Team:
  - Kubernetes кластер
  - CI/CD pipelines
  - Observability (Prometheus + Grafana + Jaeger)
  - Service mesh
  - Developer portal

Stream-aligned Teams (по доменам):
  - Catalog Team: owns Catalog microservice
  - Orders Team: owns Orders microservice  
  - Payments Team: owns Payments microservice

Каждая Stream-aligned team:
  - Деплоит независимо
  - Ведёт свои метрики
  - On-call для своего сервиса
  - Принимает технические решения в своих границах
```

## Антипаттерны микросервисов

### Распределённый монолит

Самый опасный антипаттерн: архитектурно выглядит как микросервисы, но все сервисы жёстко связаны.

```python
# Признаки распределённого монолита:
# 1. Совместная база данных между сервисами
#    OrderService и InventoryService пишут в одну БД

# 2. Синхронные вызовы глубокой цепочкой
#    UserRequest → ServiceA → ServiceB → ServiceC → ServiceD
#    (задержка складывается, один сбой роняет всё)

# 3. Невозможность деплоить сервисы независимо
#    "Нельзя обновить ServiceA без синхронного обновления ServiceB"

# 4. Сервисы разделены технологически, но не по бизнес-логике
#    "UserService" и "ProfileService" — оба про пользователей,
#    постоянно вызывают друг друга
```

### Chatty Services (болтливые сервисы)

```python
# Плохо: слишком много вызовов для одной операции
async def get_order_details(order_id: int) -> dict:
    order = await order_service.get_order(order_id)       # RPC #1
    user = await user_service.get_user(order.user_id)     # RPC #2
    
    items = []
    for item in order.items:
        product = await catalog_service.get_product(item.product_id)  # RPC #N
        items.append({...})
    
    shipping = await shipping_service.get_status(order_id)  # RPC #N+2
    
    # N+3 сетевых вызовов для одной страницы!

# Хорошо: BFF (Backend for Frontend) или агрегирующий сервис
async def get_order_details_optimized(order_id: int) -> dict:
    # Параллельно получаем всё что можно параллельно
    order, shipping = await asyncio.gather(
        order_service.get_order(order_id),
        shipping_service.get_status(order_id)
    )
    
    # Batch запрос для продуктов
    product_ids = [item.product_id for item in order.items]
    products = await catalog_service.get_products_batch(product_ids)  # 1 запрос!
    
    user = await user_service.get_user(order.user_id)
    
    # Итого: 4 параллельных запроса вместо N+3 последовательных
```

## Реальный опыт: Amazon и Netflix

### Amazon

Amazon начал как монолит в 1990-х. К 2001 году кодовая база стала настолько запутанной, что Джефф Безос издал знаменитый «API Mandate»:

*«Все команды отныне должны общаться через service interfaces. Нет другого способа коммуникации. Нет прямых ссылок, нет прямых reads другого сервиса. Только через интерфейс. Несоблюдение — увольнение.»*

Это не просто технический, но организационный мандат. Переход занял несколько лет.

### Netflix

Netflix мигрировал с монолита на микросервисы с 2008 по 2012 год, после серьёзного инцидента. Результат — 700+ микросервисов, собственные инструменты (Hystrix, Eureka, Zuul, Ribbon), и Chaos Engineering (намеренные отказы в production для проверки устойчивости).

**Ключевой урок от Netflix:** Они не выбрали микросервисы потому что это «модно». Они были вынуждены масштабировать разные части системы независимо: streaming infrastructure нужно масштабировать в пиковые вечерние часы, а рекомендательный движок — при пакетных вычислениях.

## Как принять решение

```
Начни здесь: нужны ли нам микросервисы?
         │
         ▼
Есть ли у нас реальные проблемы с монолитом?
  - Команды мешают друг другу? Y/N
  - CI/CD занимает > 30 минут? Y/N
  - Нужно масштабировать части независимо? Y/N
         │
    Все N? → Остаёмся на монолите. Делаем его лучше.
         │
    Есть Y? → Сначала Modular Monolith
                    │
                    ▼
            Bounded Contexts чёткие? Y/N
                    │
               N? → DDD, определи границы. Потом решай.
                    │
               Y? → Есть Platform Team? Y/N
                         │
                    N? → Создай Platform Team сначала.
                         │
                    Y? → Strangler Fig: постепенная миграция
                         начни с одного домена
```

## Заключение

Ни монолит, ни микросервисы не являются «правильным» или «неправильным» выбором. Правильность определяется контекстом:

- **Монолит правилен** для: стартапов, небольших команд, неопределённых требований, продуктов на ранней стадии
- **Модульный монолит** правилен для: средних команд, стабильных требований, когда хочется чистоты архитектуры без сложности распределённых систем
- **Микросервисы правильны** для: больших организаций с независимыми командами, чётко определёнными доменами, реальной потребностью в независимом масштабировании

Самая дорогостоящая ошибка — преждевременное разбиение на микросервисы. Второй по частоте ошибкой является слишком долгое ожидание с разбиением, когда монолит уже стал «большой грязью».

## Литература

1. **Newman, Sam** — «Building Microservices», 2nd ed. O'Reilly Media, 2021. ISBN: 978-1492034025
2. **Fowler, Martin** — «Microservices» (2014): https://martinfowler.com/articles/microservices.html
3. **Fowler, Martin** — «MonolithFirst» (2015): https://martinfowler.com/bliki/MonolithFirst.html
4. **Skelton, Matthew; Pais, Manuel** — «Team Topologies». IT Revolution Press, 2019. ISBN: 978-1942788812
5. **Evans, Eric** — «Domain-Driven Design: Tackling Complexity in the Heart of Software». Addison-Wesley, 2003. ISBN: 978-0321125217
6. **Richardson, Chris** — «Microservices Patterns». Manning Publications, 2018. ISBN: 978-1617294549
7. **Conway, Melvin E.** — «How Do Committees Invent?». Datamation, 1968: http://www.melconway.com/Home/Committees_Paper.html
8. **Kleppmann, Martin** — «Designing Data-Intensive Applications». O'Reilly Media, 2017. ISBN: 978-1449373320
9. **Feathers, Michael C.** — «Working Effectively with Legacy Code». Prentice Hall, 2004. ISBN: 978-0131177055
10. **Brandolini, Alberto** — «Strategic Domain-Driven Design» (EventStorming): https://www.eventstorming.com/
