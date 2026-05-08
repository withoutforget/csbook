# Hexagonal / Clean Architecture — изоляция бизнес-логики от инфраструктуры

Одна из самых устойчивых проблем в разработке — бизнес-логика, перемешанная с инфраструктурным кодом. SQL-запросы в контроллерах, HTTP-клиенты в сервисах, конфигурация базы данных в доменных объектах. Такой код невозможно тестировать без реальной БД, невозможно рефакторить без страха что-то сломать, невозможно понять без знания конкретного фреймворка. Hexagonal Architecture и Clean Architecture — два связанных подхода к решению этой проблемы.

## Проблема: бизнес-логика знает о технологиях

Рассмотрим типичный «сервис» без архитектурных принципов:

```python
# Классический anti-pattern: бизнес-логика знает о HTTP, SQL, SMTP
from flask import request, jsonify
import psycopg2
import smtplib

@app.route('/orders', methods=['POST'])
def create_order():
    # HTTP-специфичный код смешан с бизнес-логикой
    data = request.json
    user_id = data['user_id']
    items = data['items']
    
    # Прямой SQL — бизнес-логика знает о структуре БД
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Бизнес-правило: скидка для VIP клиентов
    cur.execute("SELECT is_vip FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    
    total = sum(item['price'] * item['quantity'] for item in items)
    if user and user[0]:  # is_vip
        total *= 0.9  # 10% скидка
    
    # Опять SQL
    cur.execute(
        "INSERT INTO orders (user_id, total, status) VALUES (%s, %s, 'pending') RETURNING id",
        (user_id, total)
    )
    order_id = cur.fetchone()[0]
    conn.commit()
    
    # Email прямо здесь — бизнес-логика знает о SMTP
    with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
        smtp.sendmail('noreply@app.com', data['email'], 
                     f'Your order {order_id} has been placed!')
    
    return jsonify({'order_id': order_id})

# Проблемы:
# 1. Нельзя тестировать без реальной БД и SMTP
# 2. Сменить Flask на FastAPI? Переписывать всё.
# 3. Сменить PostgreSQL на MySQL? Переписывать всё.
# 4. Понять бизнес-логику? Нужно читать SQL и HTTP код.
```

## Hexagonal Architecture: Ports and Adapters

**Hexagonal Architecture** (Гексагональная архитектура), предложенная Алистером Кокберном в 2005 году, строится на двух концепциях:

- **Порты** (Ports) — интерфейсы, через которые приложение общается с внешним миром
- **Адаптеры** (Adapters) — конкретные реализации портов для конкретных технологий

**Два типа портов:**
- **Primary Ports** (входящие/driving) — интерфейсы, через которые внешний мир управляет приложением (HTTP API, CLI, тесты)
- **Secondary Ports** (исходящие/driven) — интерфейсы, через которые приложение взаимодействует с внешними системами (БД, email, внешние API)

```
                    HEXAGONAL ARCHITECTURE

    ┌───────────────────────────────────────────────────────┐
    │                                                       │
    │   Primary Adapters          Secondary Adapters        │
    │   (Driving)                 (Driven)                  │
    │                                                       │
    │   HTTP Controller ──→  ┌──────────────┐  →── DB Adapter
    │   CLI Command     ──→  │              │  →── Email Adapter
    │   Tests           ──→  │  Application │  →── S3 Adapter
    │                        │  Core        │  →── Payment Gateway
    │                        │  (Domain     │
    │                        │   Logic)     │
    │                        └──────────────┘
    │                                                       │
    │        Primary Ports ──┘              └── Secondary Ports
    │        (Use Case Interfaces)         (Repository Interfaces)
    └───────────────────────────────────────────────────────┘
```

**Ключевая идея:** Application Core ничего не знает об адаптерах. Зависимости направлены ВНУТРЬ: адаптеры зависят от ядра, но не наоборот.

### Реализация Hexagonal Architecture

```python
# === DOMAIN LAYER (центр гексагона) ===
# Чистые доменные объекты — никаких зависимостей от фреймворков

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
from abc import ABC, abstractmethod

@dataclass
class OrderItem:
    product_id: UUID
    product_name: str
    unit_price: Decimal
    quantity: int

@dataclass
class Order:
    order_id: UUID = field(default_factory=uuid4)
    customer_id: UUID = None
    items: list[OrderItem] = field(default_factory=list)
    total: Decimal = Decimal("0")
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_item(self, item: OrderItem) -> None:
        self.items.append(item)
        self.total += item.unit_price * item.quantity
    
    def apply_vip_discount(self) -> None:
        self.total *= Decimal("0.9")
    
    def confirm(self) -> None:
        if not self.items:
            raise ValueError("Cannot confirm empty order")
        self.status = "confirmed"


# === SECONDARY PORTS (интерфейсы исходящих зависимостей) ===
# Определены в доменном слое, реализованы в инфраструктурном

class OrderRepository(ABC):
    @abstractmethod
    def save(self, order: Order) -> None: ...
    
    @abstractmethod
    def find_by_id(self, order_id: UUID) -> Optional[Order]: ...

class CustomerRepository(ABC):
    @abstractmethod
    def find_by_id(self, customer_id: UUID) -> Optional['Customer']: ...

class NotificationPort(ABC):
    @abstractmethod
    def send_order_confirmation(self, customer_email: str, order: Order) -> None: ...

class PaymentPort(ABC):
    @abstractmethod
    def charge(self, customer_id: UUID, amount: Decimal) -> str: ...  # returns payment_id


# === APPLICATION LAYER (use cases) ===
# Оркестрирует через порты — не знает о конкретных адаптерах

@dataclass(frozen=True)
class CreateOrderCommand:
    customer_id: UUID
    items: list[dict]  # [{'product_id': ..., 'name': ..., 'price': ..., 'qty': ...}]

@dataclass(frozen=True)
class CreateOrderResult:
    order_id: UUID
    total: Decimal
    status: str

class CreateOrderUseCase:
    """Primary Port: интерфейс для входящих запросов."""
    
    def __init__(
        self,
        order_repo: OrderRepository,       # Secondary Port
        customer_repo: CustomerRepository,  # Secondary Port
        notification: NotificationPort,     # Secondary Port
        payment: PaymentPort,              # Secondary Port
    ):
        # Инверсия зависимостей: получаем интерфейсы, не конкретные классы
        self._order_repo = order_repo
        self._customer_repo = customer_repo
        self._notification = notification
        self._payment = payment
    
    def execute(self, command: CreateOrderCommand) -> CreateOrderResult:
        """
        Use case логика — никаких Flask, psycopg2, smtplib!
        Только бизнес-правила.
        """
        customer = self._customer_repo.find_by_id(command.customer_id)
        if not customer:
            raise ValueError(f"Customer {command.customer_id} not found")
        
        order = Order(customer_id=command.customer_id)
        
        for item_data in command.items:
            order.add_item(OrderItem(
                product_id=UUID(item_data['product_id']),
                product_name=item_data['name'],
                unit_price=Decimal(str(item_data['price'])),
                quantity=int(item_data['qty'])
            ))
        
        # Бизнес-правило: VIP скидка
        if customer.is_vip:
            order.apply_vip_discount()
        
        # Оплата через порт
        payment_id = self._payment.charge(command.customer_id, order.total)
        
        # Подтверждаем заказ
        order.confirm()
        
        # Сохраняем через порт
        self._order_repo.save(order)
        
        # Уведомляем через порт
        self._notification.send_order_confirmation(customer.email, order)
        
        return CreateOrderResult(
            order_id=order.order_id,
            total=order.total,
            status=order.status
        )


# === SECONDARY ADAPTERS (реализации портов) ===
# В Infrastructure Layer — знают о конкретных технологиях

class PostgresOrderRepository(OrderRepository):
    """Адаптер: реализует OrderRepository через PostgreSQL."""
    
    def __init__(self, connection_string: str):
        self._conn_str = connection_string
    
    def save(self, order: Order) -> None:
        import psycopg2
        with psycopg2.connect(self._conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO orders (id, customer_id, total, status) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET total=EXCLUDED.total, status=EXCLUDED.status",
                    (str(order.order_id), str(order.customer_id), 
                     order.total, order.status)
                )
    
    def find_by_id(self, order_id: UUID) -> Optional[Order]:
        import psycopg2
        with psycopg2.connect(self._conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM orders WHERE id = %s", (str(order_id),))
                row = cur.fetchone()
                return self._to_domain(row) if row else None

class EmailNotificationAdapter(NotificationPort):
    """Адаптер: реализует NotificationPort через SMTP."""
    
    def __init__(self, smtp_host: str, smtp_port: int):
        self._host = smtp_host
        self._port = smtp_port
    
    def send_order_confirmation(self, customer_email: str, order: Order) -> None:
        import smtplib
        with smtplib.SMTP(self._host, self._port) as smtp:
            smtp.sendmail(
                'noreply@app.com',
                customer_email,
                f'Order {order.order_id} confirmed. Total: {order.total}'
            )

class StripePaymentAdapter(PaymentPort):
    """Адаптер: реализует PaymentPort через Stripe."""
    
    def __init__(self, api_key: str):
        self._api_key = api_key
    
    def charge(self, customer_id: UUID, amount: Decimal) -> str:
        import stripe
        stripe.api_key = self._api_key
        charge = stripe.Charge.create(
            amount=int(amount * 100),
            currency="usd",
            customer=str(customer_id)
        )
        return charge.id


# === PRIMARY ADAPTERS (входящие) ===

# HTTP Adapter (FastAPI)
from fastapi import FastAPI, HTTPException

app = FastAPI()

def get_use_case() -> CreateOrderUseCase:
    """Dependency injection — сборка адаптеров."""
    return CreateOrderUseCase(
        order_repo=PostgresOrderRepository(DATABASE_URL),
        customer_repo=PostgresCustomerRepository(DATABASE_URL),
        notification=EmailNotificationAdapter('smtp.gmail.com', 587),
        payment=StripePaymentAdapter(STRIPE_KEY)
    )

@app.post("/orders")
def create_order_endpoint(body: CreateOrderRequest):
    """HTTP Adapter: преобразует HTTP запрос в команду use case."""
    try:
        result = get_use_case().execute(CreateOrderCommand(
            customer_id=UUID(body.customer_id),
            items=body.items
        ))
        return {'order_id': str(result.order_id), 'total': float(result.total)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# CLI Adapter
import click

@click.command()
@click.argument('customer_id')
@click.argument('product_id')
def create_order_cli(customer_id: str, product_id: str):
    """CLI Adapter: та же логика, другой входной канал."""
    result = get_use_case().execute(CreateOrderCommand(
        customer_id=UUID(customer_id),
        items=[{'product_id': product_id, 'name': 'CLI Product', 'price': '10', 'qty': 1}]
    ))
    click.echo(f"Order created: {result.order_id}")
```

### Тестируемость: главное преимущество

```python
# Test Adapters (In-memory) — нет реальной БД, нет SMTP, нет Stripe!
import pytest

class InMemoryOrderRepository(OrderRepository):
    def __init__(self):
        self._storage: dict[UUID, Order] = {}
    
    def save(self, order: Order) -> None:
        self._storage[order.order_id] = order
    
    def find_by_id(self, order_id: UUID) -> Optional[Order]:
        return self._storage.get(order_id)

class InMemoryNotification(NotificationPort):
    def __init__(self):
        self.sent_notifications: list[dict] = []
    
    def send_order_confirmation(self, customer_email: str, order: Order) -> None:
        self.sent_notifications.append({
            'email': customer_email,
            'order_id': order.order_id,
            'total': order.total
        })

class FakePaymentPort(PaymentPort):
    def charge(self, customer_id: UUID, amount: Decimal) -> str:
        return f"fake-payment-{uuid4()}"

# Тест — запускается за миллисекунды, нет зависимостей!
def test_vip_customer_gets_discount():
    order_repo = InMemoryOrderRepository()
    customer_repo = InMemoryCustomerRepository()
    notification = InMemoryNotification()
    payment = FakePaymentPort()
    
    # Добавляем VIP клиента
    customer_repo.add(Customer(
        customer_id=uuid4(),
        name="VIP User",
        email="vip@test.com",
        is_vip=True
    ))
    
    use_case = CreateOrderUseCase(order_repo, customer_repo, notification, payment)
    
    result = use_case.execute(CreateOrderCommand(
        customer_id=customer_repo.customers[0].customer_id,
        items=[{'product_id': str(uuid4()), 'name': 'Product', 'price': '100', 'qty': 1}]
    ))
    
    # VIP получает 10% скидку: 100 * 0.9 = 90
    assert result.total == Decimal("90")
    
    # Уведомление было отправлено
    assert len(notification.sent_notifications) == 1
    assert notification.sent_notifications[0]['email'] == "vip@test.com"
```

## Clean Architecture: концентрические кольца

**Clean Architecture** Роберта Мартина (Uncle Bob) — развитие идей Hexagonal Architecture, представленное в виде концентрических колец.

```
              Clean Architecture

     ┌─────────────────────────────────────────────────┐
     │  Frameworks & Drivers (Внешнее кольцо)          │
     │  ┌───────────────────────────────────────────┐  │
     │  │  Interface Adapters                        │  │
     │  │  ┌─────────────────────────────────────┐  │  │
     │  │  │  Application Business Rules          │  │  │
     │  │  │  (Use Cases)                         │  │  │
     │  │  │  ┌───────────────────────────────┐   │  │  │
     │  │  │  │  Enterprise Business Rules     │   │  │  │
     │  │  │  │  (Entities)                    │   │  │  │
     │  │  │  │                               │   │  │  │
     │  │  │  └───────────────────────────────┘   │  │  │
     │  │  └─────────────────────────────────────┘  │  │
     │  └───────────────────────────────────────────┘  │
     └─────────────────────────────────────────────────┘
```

**Dependency Rule:** зависимости могут указывать только внутрь. Entities не зависят ни от чего. Use Cases зависят только от Entities. Interface Adapters зависят от Use Cases. Frameworks & Drivers зависят от всего.

**Четыре слоя (снаружи внутрь):**

1. **Entities** — Enterprise Business Rules: доменные объекты, правила бизнеса которые неизменны независимо от платформы
2. **Use Cases** — Application Business Rules: специфичная логика приложения
3. **Interface Adapters** — Presenters, Controllers, Gateways: преобразование данных между форматами
4. **Frameworks & Drivers** — UI, Database, External Interfaces: конкретные технологии

### Структура проекта по Clean Architecture

```
myapp/
├── domain/                     # Entities
│   ├── models/
│   │   ├── order.py
│   │   ├── customer.py
│   │   └── product.py
│   ├── value_objects/
│   │   ├── money.py
│   │   └── address.py
│   └── exceptions.py
│
├── application/                # Use Cases
│   ├── ports/                  # Interfaces (Secondary Ports)
│   │   ├── repositories.py
│   │   ├── notification_port.py
│   │   └── payment_port.py
│   ├── use_cases/
│   │   ├── create_order.py
│   │   ├── cancel_order.py
│   │   └── get_order.py
│   └── dto.py                  # Data Transfer Objects (в/из use cases)
│
├── adapters/                   # Interface Adapters
│   ├── primary/               # Входящие адаптеры
│   │   ├── http/
│   │   │   ├── order_controller.py
│   │   │   └── schemas.py      # Pydantic models для HTTP
│   │   └── cli/
│   │       └── commands.py
│   └── secondary/             # Исходящие адаптеры
│       ├── persistence/
│       │   ├── postgres_order_repo.py
│       │   └── redis_cache_repo.py
│       ├── notifications/
│       │   └── email_adapter.py
│       └── payments/
│           └── stripe_adapter.py
│
└── infrastructure/             # Frameworks & Drivers
    ├── config.py
    ├── database.py             # SQLAlchemy setup
    ├── container.py            # Dependency injection container
    └── app.py                  # FastAPI application factory
```

## Onion Architecture

Луковая архитектура (Onion Architecture) Джеффри Палермо — ещё один вариант той же идеи с акцентом на инверсию зависимостей:

```python
# Onion Architecture: каждый слой знает только о внутренних слоях

# Layer 1 (Core): Domain Model — Entity и Value Objects
# Зависимостей нет вообще

# Layer 2: Domain Services
# Зависит только от Layer 1

# Layer 3: Application Services (Use Cases)
# Зависит от Layer 1 и Layer 2

# Layer 4: Infrastructure
# Зависит от всех внутренних слоёв (через интерфейсы)

# Разница от Hexagonal: Onion более детален в разделении Domain Services
# и Application Services
```

## Сравнение трёх архитектур

| Аспект | Hexagonal | Clean | Onion |
|--------|-----------|-------|-------|
| Автор | Cockburn (2005) | Martin (2012) | Palermo (2008) |
| Центральная метафора | Шестиугольник с портами | Концентрические кольца | Слои лука |
| Терминология | Ports & Adapters | Entities, Use Cases, Interface Adapters | Domain, Application, Infrastructure |
| Акцент | Тестируемость, изоляция | Правило зависимостей | Инверсия зависимостей |
| Практическое отличие | Минимальное | Минимальное | Минимальное |

По сути все три архитектуры реализуют одну идею: **изолируй бизнес-логику от инфраструктуры через инверсию зависимостей**.

## Практический пример на Go

```go
// === domain/order.go ===
package domain

import (
    "errors"
    "github.com/google/uuid"
    "time"
    "math/big"
)

type OrderStatus string

const (
    Pending   OrderStatus = "pending"
    Confirmed OrderStatus = "confirmed"
)

type Order struct {
    ID         uuid.UUID
    CustomerID uuid.UUID
    Items      []OrderItem
    Total      *big.Float
    Status     OrderStatus
    CreatedAt  time.Time
}

func NewOrder(customerID uuid.UUID) *Order {
    return &Order{
        ID:         uuid.New(),
        CustomerID: customerID,
        Total:      big.NewFloat(0),
        Status:     Pending,
        CreatedAt:  time.Now(),
    }
}

func (o *Order) AddItem(item OrderItem) {
    o.Items = append(o.Items, item)
    itemTotal := new(big.Float).Mul(item.UnitPrice, big.NewFloat(float64(item.Quantity)))
    o.Total.Add(o.Total, itemTotal)
}

func (o *Order) Confirm() error {
    if len(o.Items) == 0 {
        return errors.New("cannot confirm empty order")
    }
    o.Status = Confirmed
    return nil
}


// === application/ports/order_repository.go ===
package ports

import "github.com/google/uuid"

type OrderRepository interface {
    Save(order *domain.Order) error
    FindByID(id uuid.UUID) (*domain.Order, error)
}

type CustomerRepository interface {
    FindByID(id uuid.UUID) (*domain.Customer, error)
}

type NotificationService interface {
    SendOrderConfirmation(email string, order *domain.Order) error
}


// === application/use_cases/create_order.go ===
package usecases

type CreateOrderCommand struct {
    CustomerID string
    Items      []ItemData
}

type CreateOrderUseCase struct {
    orderRepo    ports.OrderRepository
    customerRepo ports.CustomerRepository
    notification ports.NotificationService
}

func NewCreateOrderUseCase(
    orderRepo ports.OrderRepository,
    customerRepo ports.CustomerRepository,
    notification ports.NotificationService,
) *CreateOrderUseCase {
    return &CreateOrderUseCase{orderRepo, customerRepo, notification}
}

func (uc *CreateOrderUseCase) Execute(cmd CreateOrderCommand) (*CreateOrderResult, error) {
    customerID, _ := uuid.Parse(cmd.CustomerID)
    customer, err := uc.customerRepo.FindByID(customerID)
    if err != nil {
        return nil, err
    }
    
    order := domain.NewOrder(customerID)
    for _, item := range cmd.Items {
        order.AddItem(domain.OrderItem{/* ... */})
    }
    
    if customer.IsVIP {
        order.Total.Mul(order.Total, big.NewFloat(0.9))
    }
    
    if err := order.Confirm(); err != nil {
        return nil, err
    }
    
    if err := uc.orderRepo.Save(order); err != nil {
        return nil, err
    }
    
    uc.notification.SendOrderConfirmation(customer.Email, order)
    
    return &CreateOrderResult{OrderID: order.ID}, nil
}


// === adapters/secondary/postgres_order_repo.go ===
package adapters

import "database/sql"

// Реализует ports.OrderRepository
type PostgresOrderRepository struct {
    db *sql.DB
}

func (r *PostgresOrderRepository) Save(order *domain.Order) error {
    _, err := r.db.Exec(
        "INSERT INTO orders (id, customer_id, total, status) VALUES ($1, $2, $3, $4)",
        order.ID, order.CustomerID, order.Total.Text('f', 2), string(order.Status),
    )
    return err
}


// === adapters/primary/http/order_handler.go ===
package http

import "net/http"

type OrderHandler struct {
    createOrder *usecases.CreateOrderUseCase
}

func (h *OrderHandler) Create(w http.ResponseWriter, r *http.Request) {
    var body CreateOrderRequest
    json.NewDecoder(r.Body).Decode(&body)
    
    result, err := h.createOrder.Execute(usecases.CreateOrderCommand{
        CustomerID: body.CustomerID,
        Items:      body.Items,
    })
    
    if err != nil {
        http.Error(w, err.Error(), http.StatusBadRequest)
        return
    }
    
    json.NewEncoder(w).Encode(map[string]string{"order_id": result.OrderID.String()})
}
```

## Dependency Injection Container

```python
# infrastructure/container.py — сборка всего приложения
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    
    # Secondary Adapters
    order_repository = providers.Factory(
        PostgresOrderRepository,
        connection_string=config.database.url
    )
    
    customer_repository = providers.Factory(
        PostgresCustomerRepository,
        connection_string=config.database.url
    )
    
    notification_service = providers.Factory(
        EmailNotificationAdapter,
        smtp_host=config.smtp.host,
        smtp_port=config.smtp.port
    )
    
    payment_service = providers.Factory(
        StripePaymentAdapter,
        api_key=config.stripe.api_key
    )
    
    # Use Cases
    create_order_use_case = providers.Factory(
        CreateOrderUseCase,
        order_repo=order_repository,
        customer_repo=customer_repository,
        notification=notification_service,
        payment=payment_service
    )
    
    # Для тестирования — переопределяем провайдеры
    # container.order_repository.override(InMemoryOrderRepository)
```

## Когда это избыточно

Clean Architecture добавляет значительный слой абстракции. Для простых приложений это overkill:

```python
# Простой CRUD сервис — Clean Architecture overkill:
# Нет сложной бизнес-логики
# Один разработчик
# Живёт 6 месяцев
# 10 endpoints для CRUD операций

# Достаточно:
@app.get("/users/{id}")
async def get_user(id: int, db: Session = Depends(get_db)):
    return db.query(User).filter(User.id == id).first()

# Clean Architecture нужна когда:
# - Нужно тестировать бизнес-логику без инфраструктуры
# - Несколько входных каналов (HTTP + CLI + jobs)
# - Смена технологий (переезд с PostgreSQL на MongoDB)
# - Команда 5+ разработчиков
# - Долгоживущий проект
```

## Заключение

Hexagonal Architecture, Clean Architecture и Onion Architecture — разные имена одной идеи: **бизнес-логика не должна зависеть от технологий**. Инверсия зависимостей (Dependency Inversion Principle из SOLID) — главный механизм достижения этой цели.

Практические выгоды:
- **Тестируемость:** бизнес-логику можно тестировать без реальной БД, HTTP, SMTP
- **Изменяемость:** замена PostgreSQL на MySQL — только новый адаптер
- **Понятность:** бизнес-логика читается без знания конкретных технологий

Главное предупреждение: не применяйте эту архитектуру везде. Для простых CRUD-приложений она создаёт ненужную сложность. Применяйте там, где есть реальная бизнес-логика, которую нужно изолировать и тестировать.

## Литература

1. **Cockburn, Alistair** — «Hexagonal Architecture» (2005): https://alistair.cockburn.us/hexagonal-architecture/
2. **Martin, Robert C.** — «Clean Architecture: A Craftsman's Guide to Software Structure and Design». Prentice Hall, 2017. ISBN: 978-0134494166
3. **Palermo, Jeffrey** — «The Onion Architecture» (2008): https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/
4. **Martin, Robert C.** — «The Clean Code Blog: The Clean Architecture» (2012): https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
5. **Evans, Eric** — «Domain-Driven Design». Addison-Wesley, 2003. ISBN: 978-0321125217
6. **Fowler, Martin** — «Patterns of Enterprise Application Architecture», Chapter 9: Domain Logic Patterns. Addison-Wesley, 2002
7. **Martin, Robert C.** — «Agile Software Development, Principles, Patterns, and Practices». Prentice Hall, 2002. ISBN: 978-0135974445
8. **Brandolini, Alberto** — «Strategic Domain-Driven Design with Context Mapping»: https://www.infoq.com/articles/ddd-contextmapping/
9. **Wlaschin, Scott** — «Domain Modeling Made Functional». Pragmatic Bookshelf, 2018. ISBN: 978-1680502541
10. **Khorikov, Vladimir** — «Unit Testing: Principles, Practices, and Patterns». Manning, 2020. ISBN: 978-1617296277
