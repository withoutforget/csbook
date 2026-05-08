# DDD (Domain-Driven Design), Bounded Contexts — как делить большую систему по смыслу, а не по слоям

В 2003 году Эрик Эванс опубликовал книгу «Domain-Driven Design», которая изменила способ мышления о сложных программных системах. До DDD разработчики привыкли делить системы по технологическим слоям: база данных, бизнес-логика, представление. DDD предлагает делить по смыслу — по бизнес-доменам. Эта идея кажется очевидной, но её последовательное применение требует пересмотра многих привычных подходов.

## Что такое Domain-Driven Design

DDD — это подход к разработке программного обеспечения, при котором модель предметной области (domain model) является центральным элементом дизайна системы. Вся архитектура строится вокруг бизнес-логики, а не технической инфраструктуры.

**Центральная идея:** Код должен говорить на языке бизнеса. Если бизнес-аналитик говорит «оформление заказа», в коде должен быть класс `Order` с методом `place()`, а не `OrderEntity` с методом `insertIntoOrderTable()`.

**Два уровня DDD:**
- **Стратегический DDD** — как делить большую систему на части (Bounded Contexts, Context Map)
- **Тактический DDD** — как строить модель внутри каждой части (Entities, Value Objects, Aggregates, Domain Services)

## Ubiquitous Language: единый словарь

**Ubiquitous Language** (повсеместный язык) — общий словарь, используемый всеми участниками проекта: разработчиками, бизнес-аналитиками, менеджерами, тестировщиками.

Проблема без Ubiquitous Language:
```
Бизнес говорит: "Клиент оформляет заказ на товар из каталога"
Разработчик пишет: UserEntity.createTransaction(ProductItem[], CartService)
Аналитик пишет: "Пользователь совершает покупку позиций из корзины"
В БД: purchases, users, cart_items, product_catalogue

У всех — разные названия для одних и тех же концепций!
```

С Ubiquitous Language все используют одни термины:

```python
# Ubiquitous Language воплощён в коде
class Customer:            # не User, не Client — именно Customer
    def place_order(       # не createTransaction, не makePurchase
        self, 
        items: list[OrderItem],   # не CartItem, не ProductEntry
        shipping_address: Address
    ) -> Order:
        """
        Клиент оформляет заказ.
        
        Это именно то, что бизнес называет 'оформлением заказа'.
        Каждый может прочитать этот код и понять бизнес-логику.
        """
        if not items:
            raise EmptyOrderError("Нельзя оформить пустой заказ")
        
        order = Order(
            customer=self,
            items=items,
            shipping_address=shipping_address,
            status=OrderStatus.PENDING
        )
        return order
```

**Как создать Ubiquitous Language:**
1. Собрать совместные сессии (EventStorming — отличный инструмент)
2. Создать глоссарий домена
3. Использовать термины везде: в коде, тестах, документации, коммуникации
4. Беспощадно рефакторить код, когда язык уточняется

## Entity: объект с идентичностью

**Entity** (сущность) — объект, который определяется своей уникальной идентичностью, а не набором атрибутов. Два объекта с одинаковыми данными, но разными ID — это разные сущности.

```python
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

@dataclass
class Order:
    """Entity: идентифицируется по order_id."""
    
    order_id: UUID = field(default_factory=uuid4)
    customer_id: UUID = None
    status: OrderStatus = OrderStatus.PENDING
    items: list = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Order):
            return False
        # Равенство определяется ТОЛЬКО по ID
        return self.order_id == other.order_id
    
    def __hash__(self) -> int:
        return hash(self.order_id)
    
    # Бизнес-методы на Entity
    def confirm(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise InvalidOrderStateError(
                f"Нельзя подтвердить заказ в состоянии {self.status}"
            )
        self.status = OrderStatus.CONFIRMED
    
    def cancel(self, reason: str) -> 'OrderCancelled':
        """Отмена заказа — возвращает Domain Event."""
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise InvalidOrderStateError("Нельзя отменить отправленный заказ")
        
        self.status = OrderStatus.CANCELLED
        return OrderCancelled(
            order_id=self.order_id,
            reason=reason,
            occurred_at=datetime.utcnow()
        )
```

**Ключевое свойство Entity:** Даже если изменились все атрибуты (имя клиента, адрес), объект остаётся тем же заказом, пока у него тот же ID.

## Value Object: объект-значение

**Value Object** (объект-значение) — неизменяемый объект без собственной идентичности. Два Value Object с одинаковыми данными — это одно и то же.

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)  # frozen=True делает его неизменяемым
class Money:
    """Value Object: деньги определяются суммой и валютой."""
    
    amount: Decimal
    currency: str
    
    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Сумма не может быть отрицательной")
        if len(self.currency) != 3:
            raise ValueError("Валюта должна быть в формате ISO 4217 (USD, EUR, RUB)")
    
    def __add__(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Нельзя складывать {self.currency} и {other.currency}"
            )
        return Money(self.amount + other.amount, self.currency)
    
    def __mul__(self, factor: int) -> 'Money':
        return Money(self.amount * factor, self.currency)

@dataclass(frozen=True)
class Address:
    """Value Object: адрес определяется своими полями."""
    
    country: str
    city: str
    street: str
    postal_code: str
    
    def is_domestic(self) -> bool:
        return self.country == "RU"

# Использование:
price = Money(Decimal("99.99"), "USD")
quantity = 3
total = price * quantity  # Money(299.97, "USD")

# Сравнение по значению:
addr1 = Address("RU", "Moscow", "Arbat 1", "119002")
addr2 = Address("RU", "Moscow", "Arbat 1", "119002")
assert addr1 == addr2  # True! Value Objects сравниваются по значению
```

**Когда Entity, когда Value Object:**
- **Entity:** Заказ, Пользователь, Продукт (важна уникальность)
- **Value Object:** Деньги, Адрес, Координаты, Дата рождения, Email (важно только значение)

## Aggregate: граница консистентности

**Aggregate** — кластер связанных объектов (Entity и Value Objects), которые рассматриваются как единица изменений. **Aggregate Root** — Entity, через которую происходит доступ ко всем объектам внутри агрегата.

**Правила агрегата:**
1. Изменения только через Aggregate Root
2. Нельзя хранить прямые ссылки на внутренние Entity агрегата снаружи
3. Агрегат должен быть сохранён как единое целое (атомарность)
4. Агрегат определяет границы транзакции

```python
@dataclass
class OrderItem:
    """Внутренняя Entity агрегата Order — не доступна снаружи напрямую."""
    
    product_id: UUID
    product_name: str
    unit_price: Money
    quantity: int
    
    @property
    def total_price(self) -> Money:
        return self.unit_price * self.quantity

class Order:
    """Aggregate Root: управляет целостностью всего заказа."""
    
    def __init__(self, customer_id: UUID):
        self._order_id = uuid4()
        self._customer_id = customer_id
        self._items: list[OrderItem] = []
        self._status = OrderStatus.PENDING
        self._domain_events: list = []
    
    def add_item(self, product_id: UUID, name: str, price: Money, qty: int) -> None:
        """Добавить позицию. Проверяет инварианты агрегата."""
        
        if self._status != OrderStatus.PENDING:
            raise InvalidOrderStateError("Нельзя изменить подтверждённый заказ")
        
        if qty <= 0:
            raise ValueError("Количество должно быть положительным")
        
        # Проверяем нет ли уже такого продукта
        existing = next(
            (item for item in self._items if item.product_id == product_id),
            None
        )
        
        if existing:
            # Увеличиваем количество (не создаём дубликат)
            self._items.remove(existing)
            self._items.append(OrderItem(product_id, name, price, existing.quantity + qty))
        else:
            self._items.append(OrderItem(product_id, name, price, qty))
    
    def remove_item(self, product_id: UUID) -> None:
        """Удалить позицию через Aggregate Root, не напрямую."""
        self._items = [i for i in self._items if i.product_id != product_id]
    
    @property
    def total(self) -> Money:
        """Инвариант: total всегда согласован с items."""
        if not self._items:
            return Money(Decimal("0"), "USD")
        return sum(
            (item.total_price for item in self._items),
            Money(Decimal("0"), self._items[0].unit_price.currency)
        )
    
    def place(self) -> None:
        """Разместить заказ — переход состояния с публикацией события."""
        if not self._items:
            raise EmptyOrderError()
        if self.total.amount < Decimal("10"):
            raise MinimumOrderError("Минимальная сумма заказа: 10 USD")
        
        self._status = OrderStatus.CONFIRMED
        self._domain_events.append(
            OrderPlaced(order_id=self._order_id, total=self.total)
        )
    
    def collect_events(self) -> list:
        """Получить и очистить накопленные Domain Events."""
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events
```

**Правило одного агрегата на транзакцию:** В одной транзакции должен изменяться только один агрегат. Если бизнес-логика требует изменить два агрегата — использовать Domain Events и eventual consistency.

## Domain Events

**Domain Events** (доменные события) — запись о том, что произошло что-то важное в домене. События именуются в прошедшем времени.

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

@dataclass(frozen=True)
class DomainEvent:
    """Базовый класс для всех Domain Events."""
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=datetime.utcnow)

@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    order_id: UUID = None
    customer_id: UUID = None
    total: Money = None
    items: tuple = ()  # tuple вместо list — для неизменяемости

@dataclass(frozen=True)
class PaymentReceived(DomainEvent):
    order_id: UUID = None
    payment_id: UUID = None
    amount: Money = None

@dataclass(frozen=True)
class ItemShipped(DomainEvent):
    order_id: UUID = None
    tracking_number: str = None
    carrier: str = None

# Обработчики событий — в Application Layer
class NotificationService:
    def on_order_placed(self, event: OrderPlaced) -> None:
        """Реагируем на событие OrderPlaced — отправляем подтверждение."""
        customer = self.customer_repo.find_by_id(event.customer_id)
        self.email_service.send_order_confirmation(
            email=customer.email,
            order_id=event.order_id,
            total=event.total
        )

class InventoryService:
    def on_order_placed(self, event: OrderPlaced) -> None:
        """Резервируем товары при размещении заказа."""
        for item in event.items:
            self.reserve_stock(item.product_id, item.quantity)
```

## Repository Pattern

**Repository** — абстракция над хранилищем данных. Domain layer не знает о PostgreSQL, MongoDB, Redis — только об интерфейсе репозитория.

```python
from abc import ABC, abstractmethod
from typing import Optional

class OrderRepository(ABC):
    """Интерфейс репозитория — часть Domain Layer."""
    
    @abstractmethod
    def save(self, order: Order) -> None:
        ...
    
    @abstractmethod
    def find_by_id(self, order_id: UUID) -> Optional[Order]:
        ...
    
    @abstractmethod
    def find_by_customer_id(self, customer_id: UUID) -> list[Order]:
        ...

# Реализация — в Infrastructure Layer
class PostgresOrderRepository(OrderRepository):
    def __init__(self, db_connection):
        self._db = db_connection
    
    def save(self, order: Order) -> None:
        """Сохранить агрегат в PostgreSQL."""
        with self._db.transaction():
            # Удаляем старые items и пишем новые (простейший подход)
            self._db.execute(
                "DELETE FROM order_items WHERE order_id = %s",
                (str(order.order_id),)
            )
            self._db.execute(
                """INSERT INTO orders (id, customer_id, status, created_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status""",
                (str(order.order_id), str(order._customer_id),
                 order._status.value, order._created_at)
            )
            for item in order._items:
                self._db.execute(
                    """INSERT INTO order_items 
                       (order_id, product_id, product_name, unit_price, quantity)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (str(order.order_id), str(item.product_id),
                     item.product_name, str(item.unit_price.amount), item.quantity)
                )
    
    def find_by_id(self, order_id: UUID) -> Optional[Order]:
        """Восстановить агрегат из PostgreSQL."""
        row = self._db.fetchone(
            "SELECT * FROM orders WHERE id = %s",
            (str(order_id),)
        )
        if not row:
            return None
        
        items = self._db.fetchall(
            "SELECT * FROM order_items WHERE order_id = %s",
            (str(order_id),)
        )
        
        return self._reconstruct_order(row, items)
```

## Domain Service vs Application Service

**Domain Service:** бизнес-логика, которая не принадлежит конкретной Entity или Value Object.

**Application Service:** координирует Domain Objects для выполнения use case. Не содержит бизнес-логики.

```python
# Domain Service: бизнес-логика ценообразования
class PricingService:
    """Domain Service — бизнес-логика, не привязанная к конкретной Entity."""
    
    def calculate_order_total(
        self,
        order: Order,
        customer: Customer,
        promotions: list[Promotion]
    ) -> Money:
        base_total = order.total
        
        # Бизнес-правило: VIP клиент получает 10% скидку
        if customer.is_vip:
            base_total = base_total * Decimal("0.9")
        
        # Применяем промокоды
        for promotion in promotions:
            if promotion.is_applicable(order):
                base_total = promotion.apply(base_total)
        
        return base_total


# Application Service: координация
class PlaceOrderUseCase:
    """Application Service: оркестрирует бизнес-операцию."""
    
    def __init__(
        self,
        order_repo: OrderRepository,
        customer_repo: CustomerRepository,
        inventory_service: InventoryDomainService,
        pricing_service: PricingService,
        event_bus: EventBus,
    ):
        self._order_repo = order_repo
        self._customer_repo = customer_repo
        self._inventory_service = inventory_service
        self._pricing_service = pricing_service
        self._event_bus = event_bus
    
    def execute(self, command: PlaceOrderCommand) -> PlaceOrderResult:
        """
        Use case: размещение заказа.
        Координирует без бизнес-логики.
        """
        # Загружаем необходимые агрегаты
        customer = self._customer_repo.find_by_id(command.customer_id)
        if not customer:
            raise CustomerNotFoundError(command.customer_id)
        
        # Создаём агрегат
        order = Order(customer_id=customer.customer_id)
        
        for item_cmd in command.items:
            # Domain Service проверяет наличие
            available = self._inventory_service.check_availability(
                item_cmd.product_id, item_cmd.quantity
            )
            if not available:
                raise InsufficientStockError(item_cmd.product_id)
            
            order.add_item(
                product_id=item_cmd.product_id,
                name=item_cmd.product_name,
                price=item_cmd.price,
                qty=item_cmd.quantity
            )
        
        # Domain Service для ценообразования
        final_total = self._pricing_service.calculate_order_total(
            order, customer, command.promotions
        )
        
        # Размещаем заказ (изменение состояния агрегата)
        order.place()
        
        # Сохраняем
        self._order_repo.save(order)
        
        # Публикуем Domain Events
        for event in order.collect_events():
            self._event_bus.publish(event)
        
        return PlaceOrderResult(order_id=order.order_id, total=final_total)
```

## Bounded Context: граница модели

**Bounded Context** — явная граница, внутри которой определённая модель домена применяется и остаётся согласованной. Один и тот же термин в разных Bounded Context может иметь разный смысл.

```
                    "Продукт" в разных контекстах:

Catalog Context:          Ordering Context:       Shipping Context:
┌────────────────┐        ┌────────────────┐     ┌────────────────┐
│ Product        │        │ OrderItem      │     │ ShipmentItem   │
│ - id           │        │ - product_id   │     │ - sku          │
│ - name         │        │ - name         │     │ - weight       │
│ - description  │        │ - unit_price   │     │ - dimensions   │
│ - images       │        │ - quantity     │     │ - is_fragile   │
│ - category     │        └────────────────┘     └────────────────┘
│ - ratings      │
│ - reviews      │
└────────────────┘

"Product" в Catalog — богатая модель с описанием и отзывами.
"Product" в Ordering — только то что нужно для заказа.
"Product" в Shipping — только то что нужно для доставки.

Одна модель для всех трёх — взаимные компромиссы и coupling.
```

**Пример e-commerce с Bounded Contexts:**

```
┌──────────────────────────────────────────────────────────────┐
│                     E-Commerce System                        │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │  Catalog BC     │  │  Ordering BC    │  │ Shipping BC │  │
│  │                 │  │                 │  │             │  │
│  │  Product        │  │  Order          │  │ Shipment    │  │
│  │  Category       │  │  OrderItem      │  │ Package     │  │
│  │  Review         │  │  Customer       │  │ Carrier     │  │
│  │  Inventory      │  │  Payment        │  │ Tracking    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │  Identity BC    │  │  Analytics BC   │                   │
│  │                 │  │                 │                   │
│  │  User           │  │  OrderReport    │                   │
│  │  Role           │  │  RevenueMetric  │                   │
│  │  Permission     │  │  ProductSales   │                   │
│  └─────────────────┘  └─────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

## Context Map: отношения между контекстами

**Context Map** — схема, показывающая как Bounded Contexts взаимодействуют друг с другом.

### Shared Kernel

Два контекста разделяют небольшой общий код:

```python
# shared_kernel/money.py — используется и в Ordering BC, и в Billing BC
@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

# Изменение Shared Kernel требует согласования обеих команд!
# Поэтому Shared Kernel должен быть минимальным.
```

### Customer-Supplier

Один контекст (Supplier) предоставляет данные другому (Customer):

```python
# Ordering BC — Supplier (поставщик)
# Analytics BC — Customer (потребитель)

# Analytics BC не диктует структуру данных Ordering BC,
# но Ordering BC должен учитывать потребности Analytics BC

# Ordering BC публикует события в удобном для Analytics формате
class OrderPlacedForAnalytics:
    order_id: UUID
    customer_segment: str   # Analytics хочет именно это поле
    product_categories: list[str]
    revenue: Decimal
    timestamp: datetime
```

### Anti-Corruption Layer (ACL)

Защитный слой, переводящий концепции от внешней системы во внутренние:

```python
# Integrating with legacy ERP system
class ERPProductCatalogAdapter:
    """
    Anti-Corruption Layer: переводит ERP модель в нашу модель.
    Наш код не знает о ERP концепциях.
    """
    
    def __init__(self, erp_client: ERPClient):
        self._erp = erp_client
    
    def get_product(self, product_id: str) -> Product:
        """Получить наш Product из ERP 'ITEM_MASTER'."""
        # ERP использует совсем другие концепции
        erp_item = self._erp.get_item_master(
            item_code=f"ITEM-{product_id}",  # ERP формат
            warehouse="MAIN"
        )
        
        # ACL переводит ERP модель в нашу
        return Product(
            id=UUID(product_id),
            name=erp_item['ITEM_DESC'],          # ERP поле
            price=Money(
                Decimal(str(erp_item['UNIT_PRICE'])),
                erp_item['CURRENCY_CODE']
            ),
            stock=erp_item['QTY_ON_HAND']
        )
```

### Open Host Service (OHS) + Published Language

Контекст предоставляет открытый API с формализованным протоколом:

```python
# Catalog BC: Open Host Service
# Публикует стабильный REST API для других контекстов
# Внутренняя модель может меняться, но API — нет

@app.get("/api/v2/products/{product_id}")
def get_product(product_id: UUID) -> ProductPublicDTO:
    """
    Published Language: стабильный формат для внешних потребителей.
    Внутренняя модель Product может меняться,
    но этот DTO изменяется только в major версиях API.
    """
    product = product_service.get_by_id(product_id)
    return ProductPublicDTO(
        id=product.id,
        name=product.name,
        price=product.current_price.amount,
        currency=product.current_price.currency,
        available=product.is_available()
    )
```

## Стратегический vs Тактический DDD

**Стратегический DDD** — макро-уровень:
- Определить Bounded Contexts
- Нарисовать Context Map
- Решить отношения между контекстами
- Принять решение: какие контексты — ядро (Core Domain), а какие — вспомогательные (Supporting/Generic Subdomain)

**Core Domain vs Supporting/Generic:**
```
E-Commerce:
  Core Domain (конкурентное преимущество):
    - Recommendation Engine (уникальный алгоритм рекомендаций)
    - Dynamic Pricing (уникальная модель ценообразования)
    → Вкладывать лучших разработчиков, разрабатывать собственное ПО

  Supporting Subdomain (нужно, но не уникально):
    - Order Management
    - Customer Service
    → Можно использовать готовые решения или аутсорс

  Generic Subdomain (стандартное):
    - Email уведомления
    - PDF генерация
    - Authentication
    → Использовать готовые решения (SendGrid, Auth0)
```

**Тактический DDD** — микро-уровень:
- Entities, Value Objects, Aggregates
- Domain Services, Application Services
- Repositories, Factories
- Domain Events

## Когда DDD избыточен

DDD имеет высокий overhead при входе в проект. Для простых CRUD-приложений это overkill.

```python
# Простое CRUD приложение — DDD overkill:
class Blog:
    # Entity: Article
    # Value Objects: Tag, Author
    # Aggregate: Article (с Comment как внутренней Entity)
    # Domain Service: ArticlePublicationService
    # ...
    # Это всё ради create/read/update/delete статей?
    # Нет, достаточно Django или FastAPI + SQLAlchemy

# DDD оправдан когда:
# - Сложные бизнес-правила (нельзя разместить заказ, если customer заблокирован
#   И сумма > 10000 ИЛИ нет истории покупок И способ оплаты не проверен)
# - Много доменных экспертов с нюансами
# - Команды 10+ разработчиков в одном домене
# - Система живёт и развивается 5-10+ лет
```

## Связь с микросервисами

DDD Bounded Contexts — естественные границы для микросервисов. Но важно: не каждый BC должен быть отдельным сервисом.

```
Bounded Context = граница модели (всегда)
Microservice = граница деплоя (при необходимости)

Catalog BC может быть:
- Модулем в монолите (на ранней стадии)
- Отдельным сервисом (при росте нагрузки или команды)

Правило: один микросервис = один BC (или часть BC)
Антипаттерн: несколько BC в одном сервисе (нечёткие границы)
Антипаттерн: один BC разделён на несколько сервисов без причины
```

## Практический пример: DDD в Go

```go
// domain/order/order.go — Aggregate Root
package order

import (
    "errors"
    "time"
    "github.com/google/uuid"
)

type Status string

const (
    StatusPending   Status = "pending"
    StatusConfirmed Status = "confirmed"
    StatusCancelled Status = "cancelled"
)

type Order struct {
    id        uuid.UUID
    customerID uuid.UUID
    items     []Item
    status    Status
    createdAt time.Time
    events    []DomainEvent
}

func NewOrder(customerID uuid.UUID) *Order {
    return &Order{
        id:        uuid.New(),
        customerID: customerID,
        status:    StatusPending,
        createdAt: time.Now(),
    }
}

func (o *Order) AddItem(productID uuid.UUID, name string, price Money, qty int) error {
    if o.status != StatusPending {
        return errors.New("cannot modify confirmed order")
    }
    if qty <= 0 {
        return errors.New("quantity must be positive")
    }
    
    o.items = append(o.items, Item{
        ProductID: productID,
        Name:      name,
        UnitPrice: price,
        Quantity:  qty,
    })
    return nil
}

func (o *Order) Place() error {
    if len(o.items) == 0 {
        return errors.New("cannot place empty order")
    }
    o.status = StatusConfirmed
    o.events = append(o.events, OrderPlaced{
        OrderID:    o.id,
        CustomerID: o.customerID,
        Total:      o.Total(),
        OccurredAt: time.Now(),
    })
    return nil
}

func (o *Order) CollectEvents() []DomainEvent {
    events := make([]DomainEvent, len(o.events))
    copy(events, o.events)
    o.events = nil
    return events
}
```

## Заключение

DDD — это не просто набор паттернов. Это способ мышления: система должна отражать реальный бизнес-домен, а не технические ограничения. Ubiquitous Language делает код понятным бизнесу. Bounded Contexts дают возможность командам работать независимо. Тактические паттерны (Entity, Value Object, Aggregate) обеспечивают правильное моделирование инвариантов домена.

Главный вывод из опыта применения DDD: **начинай со стратегического DDD** (контекстные карты, Language), а тактические паттерны применяй только там, где есть реальная сложность бизнес-логики. Не превращай простые CRUD-операции в сложные агрегаты ради «правильной архитектуры».

## Литература

1. **Evans, Eric** — «Domain-Driven Design: Tackling Complexity in the Heart of Software». Addison-Wesley, 2003. ISBN: 978-0321125217
2. **Vernon, Vaughn** — «Implementing Domain-Driven Design». Addison-Wesley, 2013. ISBN: 978-0321834577
3. **Vernon, Vaughn** — «Domain-Driven Design Distilled». Addison-Wesley, 2016. ISBN: 978-0134434421
4. **Millett, Scott; Tune, Nick** — «Patterns, Principles, and Practices of Domain-Driven Design». Wrox, 2015. ISBN: 978-1118714706
5. **Brandolini, Alberto** — «Introducing EventStorming». Leanpub, 2021: https://www.eventstorming.com/book/
6. **Fowler, Martin** — «Patterns of Enterprise Application Architecture». Addison-Wesley, 2002. ISBN: 978-0321127426
7. **Richardson, Chris** — «Microservices Patterns» (глава о DDD и Bounded Contexts). Manning, 2018. ISBN: 978-1617294549
8. **Young, Greg** — «CQRS Documents» (2010): https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
9. **Cockburn, Alistair** — «Hexagonal Architecture»: https://alistair.cockburn.us/hexagonal-architecture/
10. **Fowler, Martin** — «Bounded Context»: https://martinfowler.com/bliki/BoundedContext.html
