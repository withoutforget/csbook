# CQRS и Event Sourcing — разделение чтения/записи и хранение как поток событий

CQRS и Event Sourcing — два паттерна, часто применяемых вместе, но независимых по своей природе. Каждый решает конкретную проблему, и понимание этих проблем важнее знания самих паттернов. Чрезмерное применение CQRS и Event Sourcing — одна из самых распространённых причин ненужного усложнения архитектуры.

## Проблема: одна модель для чтения и записи

Традиционная архитектура использует одну модель данных для записи (создание, изменение) и для чтения (отображение, отчёты). Это работает хорошо для простых систем, но создаёт трение по мере роста.

```python
# Классический подход: одна модель для всего
class Order:
    id: UUID
    customer_id: UUID
    items: list[OrderItem]
    status: OrderStatus
    total: Decimal
    shipping_address: Address
    payment_method: PaymentMethod
    created_at: datetime
    updated_at: datetime

# Запись: нужна вся модель с инвариантами
def process_order(order: Order, payment: Payment):
    order.validate()
    order.calculate_total()
    order.status = OrderStatus.CONFIRMED
    db.save(order)

# Чтение #1: список заказов пользователя (нужны только id, total, status, date)
def get_user_orders(user_id: UUID) -> list[OrderSummary]:
    return db.query("SELECT id, total, status, created_at FROM orders WHERE customer_id = ?")

# Чтение #2: детали заказа для отображения (нужны все поля + имя клиента + названия продуктов)
def get_order_detail(order_id: UUID) -> OrderDetailView:
    return db.query("""
        SELECT o.*, c.name as customer_name, p.name as product_name
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        WHERE o.id = ?
    """)

# Чтение #3: дашборд аналитики (агрегаты, не отдельные записи)
def get_sales_analytics() -> SalesDashboard:
    return db.query("""
        SELECT date_trunc('day', created_at), SUM(total), COUNT(*)
        FROM orders WHERE status = 'confirmed'
        GROUP BY 1 ORDER BY 1
    """)
```

**Проблемы одной модели:**
- Модель для записи оптимизирована под инварианты бизнес-логики
- Модели для чтения нужны разные проекции, JOIN-ы, агрегаты
- Нагрузка на запись и чтение часто разная: 1 write → 100 reads
- При масштабировании приходится компромиссировать

## CQRS: Command Query Responsibility Segregation

**CQRS** разделяет операции на две категории:
- **Commands** — изменяют состояние, не возвращают данные (кроме идентификатора)
- **Queries** — читают данные, не изменяют состояние

Принцип сформулирован Бертраном Мейером как CQS (Command Query Separation). CQRS — его расширение на уровне архитектуры.

```python
# CQRS: разделяем модели команд и запросов

# === WRITE SIDE (Command Model) ===

# Команды — описывают намерение изменить состояние
@dataclass(frozen=True)
class PlaceOrderCommand:
    customer_id: UUID
    items: tuple[OrderItemData, ...]
    shipping_address: AddressData

@dataclass(frozen=True)
class CancelOrderCommand:
    order_id: UUID
    reason: str

# Command Handlers — обрабатывают команды
class OrderCommandHandler:
    def __init__(self, order_repo: OrderRepository, event_bus: EventBus):
        self._repo = order_repo
        self._event_bus = event_bus
    
    def handle_place_order(self, cmd: PlaceOrderCommand) -> UUID:
        order = Order.create(cmd.customer_id)
        for item in cmd.items:
            order.add_item(item.product_id, item.name, item.price, item.qty)
        order.place()
        
        self._repo.save(order)
        for event in order.collect_events():
            self._event_bus.publish(event)
        
        return order.id  # Возвращаем только ID

    def handle_cancel_order(self, cmd: CancelOrderCommand) -> None:
        order = self._repo.find_by_id(cmd.order_id)
        if not order:
            raise OrderNotFoundError(cmd.order_id)
        
        order.cancel(cmd.reason)
        self._repo.save(order)
        for event in order.collect_events():
            self._event_bus.publish(event)

# === READ SIDE (Query Model) ===

# Read models — плоские, денормализованные, оптимизированные под запрос
@dataclass
class OrderSummaryView:
    order_id: UUID
    customer_name: str  # Уже денормализовано
    total: Decimal
    status: str
    item_count: int
    created_at: datetime

@dataclass
class OrderDetailView:
    order_id: UUID
    customer_name: str
    customer_email: str
    shipping_address: str
    items: list[OrderItemView]
    total: Decimal
    status: str
    payment_method: str
    created_at: datetime

# Query Handlers — читают из оптимизированного хранилища
class OrderQueryHandler:
    def __init__(self, read_db):
        self._db = read_db
    
    def get_user_orders(self, user_id: UUID) -> list[OrderSummaryView]:
        # Читаем из денормализованной таблицы — быстро!
        rows = self._db.fetchall(
            "SELECT * FROM order_summaries WHERE customer_id = ?",
            (str(user_id),)
        )
        return [OrderSummaryView(**row) for row in rows]
    
    def get_order_detail(self, order_id: UUID) -> Optional[OrderDetailView]:
        # Всё уже денормализовано в read model — один SELECT без JOIN
        row = self._db.fetchone(
            "SELECT * FROM order_details WHERE order_id = ?",
            (str(order_id),)
        )
        return OrderDetailView(**row) if row else None
```

## Синхронизация Read и Write моделей

Главный вопрос CQRS: как поддерживать read model в актуальном состоянии?

### Синхронная проекция

```python
# Обновление read model в той же транзакции — нет eventual consistency
class OrderCommandHandler:
    def handle_place_order(self, cmd: PlaceOrderCommand) -> UUID:
        with transaction():
            # Write model
            order = Order.create(...)
            self._order_repo.save(order)
            
            # Синхронно обновляем read model
            self._read_db.execute(
                """INSERT INTO order_summaries 
                   (order_id, customer_id, customer_name, total, status, item_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(order.id), str(cmd.customer_id), 
                 self._get_customer_name(cmd.customer_id),
                 order.total, 'pending', len(cmd.items))
            )
        
        return order.id
```

### Асинхронная проекция через события

```python
# Обновление read model через Domain Events
# Read model = eventual consistent (слегка запаздывает)

class OrderProjection:
    """Обновляет read model на основе Domain Events."""
    
    def __init__(self, read_db):
        self._db = read_db
    
    def on_order_placed(self, event: OrderPlaced) -> None:
        """Создать запись в read model при размещении заказа."""
        self._db.execute(
            """INSERT INTO order_summaries 
               (order_id, customer_id, total, status, item_count, created_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (str(event.order_id), str(event.customer_id),
             event.total, len(event.items), event.occurred_at)
        )
    
    def on_order_confirmed(self, event: OrderConfirmed) -> None:
        """Обновить статус в read model."""
        self._db.execute(
            "UPDATE order_summaries SET status = 'confirmed' WHERE order_id = ?",
            (str(event.order_id),)
        )
    
    def on_order_cancelled(self, event: OrderCancelled) -> None:
        self._db.execute(
            "UPDATE order_summaries SET status = 'cancelled' WHERE order_id = ?",
            (str(event.order_id),)
        )
```

### Разные хранилища для read и write

Для высоких нагрузок можно использовать разные БД:

```python
# Write model: PostgreSQL (ACID, инварианты, транзакции)
# Read model: 
#   - Elasticsearch (для поиска)
#   - Redis (для кеша и быстрых запросов)
#   - Dedicated read replica (для сложных отчётов)

class OrderElasticProjection:
    """Синхронизируем с Elasticsearch для поиска."""
    
    def __init__(self, es_client):
        self._es = es_client
    
    def on_order_placed(self, event: OrderPlaced) -> None:
        self._es.index(
            index='orders',
            id=str(event.order_id),
            body={
                'order_id': str(event.order_id),
                'customer_id': str(event.customer_id),
                'total': float(event.total.amount),
                'status': 'pending',
                'item_names': [item.name for item in event.items],
                'created_at': event.occurred_at.isoformat()
            }
        )

# Теперь поиск по заказам — быстрый full-text search в Elasticsearch
# Создание заказа — надёжно в PostgreSQL
```

## Event Sourcing: хранение как поток событий

**Event Sourcing** — паттерн, при котором состояние системы хранится не как текущий snapshot, а как полная последовательность событий.

Аналогия: бухгалтерский учёт. Банк не хранит «текущий баланс» в вакууме — он хранит каждую транзакцию. Баланс — это сумма всех транзакций.

```python
# Традиционный подход: хранить текущее состояние
# accounts table: id=123, balance=1500.00
# При каждом изменении — перезаписываем balance

# Event Sourcing: хранить поток событий
# events table:
# {account_id: 123, type: "MoneyDeposited", amount: 1000, at: 2024-01-01}
# {account_id: 123, type: "MoneyDeposited", amount: 500,  at: 2024-01-15}
# {account_id: 123, type: "MoneyWithdrawn", amount: 200,  at: 2024-01-20}
# Текущий баланс = 1000 + 500 - 200 = 1300
```

### Реализация Event Sourcing

```python
from typing import Protocol
import json

# Events — неизменяемые факты
@dataclass(frozen=True)
class AccountOpened:
    account_id: UUID
    owner_id: UUID
    initial_balance: Decimal
    occurred_at: datetime = field(default_factory=datetime.utcnow)

@dataclass(frozen=True)  
class MoneyDeposited:
    account_id: UUID
    amount: Decimal
    description: str
    occurred_at: datetime = field(default_factory=datetime.utcnow)

@dataclass(frozen=True)
class MoneyWithdrawn:
    account_id: UUID
    amount: Decimal
    description: str
    occurred_at: datetime = field(default_factory=datetime.utcnow)

@dataclass(frozen=True)
class AccountFrozen:
    account_id: UUID
    reason: str
    occurred_at: datetime = field(default_factory=datetime.utcnow)

# Aggregate восстанавливается из событий
class BankAccount:
    def __init__(self):
        self._id: UUID = None
        self._balance: Decimal = Decimal("0")
        self._is_frozen: bool = False
        self._events: list = []  # новые события для сохранения
        self._version: int = 0
    
    # === Команды (изменяют состояние) ===
    
    @classmethod
    def open(cls, owner_id: UUID, initial_balance: Decimal) -> 'BankAccount':
        account = cls()
        account._raise_event(AccountOpened(
            account_id=uuid4(),
            owner_id=owner_id,
            initial_balance=initial_balance
        ))
        return account
    
    def deposit(self, amount: Decimal, description: str) -> None:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        if self._is_frozen:
            raise AccountFrozenError("Cannot deposit to frozen account")
        
        self._raise_event(MoneyDeposited(
            account_id=self._id,
            amount=amount,
            description=description
        ))
    
    def withdraw(self, amount: Decimal, description: str) -> None:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if self._is_frozen:
            raise AccountFrozenError("Cannot withdraw from frozen account")
        if self._balance < amount:
            raise InsufficientFundsError(f"Balance: {self._balance}, requested: {amount}")
        
        self._raise_event(MoneyWithdrawn(
            account_id=self._id,
            amount=amount,
            description=description
        ))
    
    def freeze(self, reason: str) -> None:
        if self._is_frozen:
            return  # Already frozen, idempotent
        self._raise_event(AccountFrozen(account_id=self._id, reason=reason))
    
    # === Apply методы (изменяют внутреннее состояние) ===
    
    def _apply(self, event) -> None:
        """Применяет событие к текущему состоянию."""
        if isinstance(event, AccountOpened):
            self._id = event.account_id
            self._balance = event.initial_balance
        elif isinstance(event, MoneyDeposited):
            self._balance += event.amount
        elif isinstance(event, MoneyWithdrawn):
            self._balance -= event.amount
        elif isinstance(event, AccountFrozen):
            self._is_frozen = True
        
        self._version += 1
    
    def _raise_event(self, event) -> None:
        """Генерировать новое событие."""
        self._apply(event)      # Немедленно меняем состояние
        self._events.append(event)  # Запоминаем для сохранения
    
    # === Восстановление из истории ===
    
    @classmethod
    def restore(cls, events: list) -> 'BankAccount':
        """Восстановить агрегат из потока событий."""
        account = cls()
        for event in events:
            account._apply(event)
        return account
    
    def collect_events(self) -> list:
        events = self._events.copy()
        self._events.clear()
        return events
```

### Event Store

```python
class EventStore:
    """Хранилище событий — append-only."""
    
    def __init__(self, db):
        self._db = db
    
    def save_events(
        self, 
        aggregate_id: UUID, 
        events: list, 
        expected_version: int
    ) -> None:
        """
        Сохранить новые события.
        expected_version — optimistic concurrency control.
        """
        current_version = self._get_version(aggregate_id)
        
        if current_version != expected_version:
            raise ConcurrencyConflictError(
                f"Expected version {expected_version}, got {current_version}"
            )
        
        for i, event in enumerate(events):
            self._db.execute(
                """INSERT INTO events 
                   (aggregate_id, aggregate_type, event_type, event_data, 
                    version, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(aggregate_id),
                    event.__class__.__module__ + '.' + type(event).__name__.split('.')[0],
                    type(event).__name__,
                    json.dumps(event.__dict__, default=str),
                    current_version + i + 1,
                    event.occurred_at.isoformat()
                )
            )
    
    def load_events(self, aggregate_id: UUID) -> list:
        """Загрузить все события для агрегата."""
        rows = self._db.fetchall(
            """SELECT event_type, event_data, version, occurred_at 
               FROM events 
               WHERE aggregate_id = ? 
               ORDER BY version ASC""",
            (str(aggregate_id),)
        )
        return [self._deserialize(row) for row in rows]
    
    def load_events_from_version(self, aggregate_id: UUID, from_version: int) -> list:
        """Загрузить события начиная с версии (для snapshot recovery)."""
        rows = self._db.fetchall(
            """SELECT event_type, event_data, version, occurred_at
               FROM events
               WHERE aggregate_id = ? AND version > ?
               ORDER BY version ASC""",
            (str(aggregate_id), from_version)
        )
        return [self._deserialize(row) for row in rows]
    
    def _deserialize(self, row: dict):
        """Восстановить событие из JSON."""
        EVENT_TYPES = {
            'AccountOpened': AccountOpened,
            'MoneyDeposited': MoneyDeposited,
            'MoneyWithdrawn': MoneyWithdrawn,
            'AccountFrozen': AccountFrozen,
        }
        event_class = EVENT_TYPES[row['event_type']]
        data = json.loads(row['event_data'])
        return event_class(**data)

# Repository для Event Sourcing
class EventSourcedAccountRepository:
    def __init__(self, event_store: EventStore):
        self._store = event_store
    
    def save(self, account: BankAccount) -> None:
        new_events = account.collect_events()
        self._store.save_events(
            account._id,
            new_events,
            expected_version=account._version - len(new_events)
        )
    
    def find_by_id(self, account_id: UUID) -> Optional[BankAccount]:
        events = self._store.load_events(account_id)
        if not events:
            return None
        return BankAccount.restore(events)
```

## Snapshot для производительности

Если у агрегата тысячи событий, восстановление становится медленным. Snapshot решает эту проблему:

```python
@dataclass
class AccountSnapshot:
    account_id: UUID
    balance: Decimal
    is_frozen: bool
    version: int
    taken_at: datetime

class SnapshotStore:
    def save_snapshot(self, snapshot: AccountSnapshot) -> None:
        self._db.execute(
            """INSERT INTO snapshots (account_id, data, version, taken_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (account_id) DO UPDATE SET 
                 data = EXCLUDED.data, version = EXCLUDED.version""",
            (str(snapshot.account_id), json.dumps(snapshot.__dict__, default=str),
             snapshot.version, snapshot.taken_at.isoformat())
        )
    
    def find_latest(self, account_id: UUID) -> Optional[AccountSnapshot]:
        row = self._db.fetchone(
            "SELECT * FROM snapshots WHERE account_id = ?",
            (str(account_id),)
        )
        return AccountSnapshot(**json.loads(row['data'])) if row else None

class OptimizedAccountRepository:
    def find_by_id(self, account_id: UUID) -> Optional[BankAccount]:
        # 1. Ищем snapshot
        snapshot = self._snapshot_store.find_latest(account_id)
        
        if snapshot:
            # 2. Загружаем только события ПОСЛЕ snapshot
            events = self._event_store.load_events_from_version(
                account_id, 
                from_version=snapshot.version
            )
            # 3. Восстанавливаем из snapshot + новые события
            return BankAccount.restore_from_snapshot(snapshot, events)
        else:
            # Snapshot нет — загружаем всю историю
            events = self._event_store.load_events(account_id)
            return BankAccount.restore(events) if events else None
    
    def save(self, account: BankAccount) -> None:
        new_events = account.collect_events()
        self._event_store.save_events(account._id, new_events, ...)
        
        # Создаём snapshot каждые 50 событий
        if account._version % 50 == 0:
            snapshot = AccountSnapshot(
                account_id=account._id,
                balance=account._balance,
                is_frozen=account._is_frozen,
                version=account._version,
                taken_at=datetime.utcnow()
            )
            self._snapshot_store.save_snapshot(snapshot)
```

## Projections и Read Models

**Projection** — процесс трансформации потока событий в read model. Проекции можно пересчитать в любой момент, воспроизведя (replay) все события.

```python
class AccountBalanceProjection:
    """Проекция: текущий баланс каждого счёта для быстрого чтения."""
    
    def __init__(self, read_db):
        self._db = read_db
    
    def on_account_opened(self, event: AccountOpened) -> None:
        self._db.execute(
            "INSERT INTO account_balances (account_id, balance) VALUES (?, ?)",
            (str(event.account_id), str(event.initial_balance))
        )
    
    def on_money_deposited(self, event: MoneyDeposited) -> None:
        self._db.execute(
            "UPDATE account_balances SET balance = balance + ? WHERE account_id = ?",
            (str(event.amount), str(event.account_id))
        )
    
    def on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        self._db.execute(
            "UPDATE account_balances SET balance = balance - ? WHERE account_id = ?",
            (str(event.amount), str(event.account_id))
        )

class TransactionHistoryProjection:
    """Другая проекция: история транзакций для выписки."""
    
    def on_money_deposited(self, event: MoneyDeposited) -> None:
        self._db.execute(
            """INSERT INTO transaction_history 
               (account_id, type, amount, description, occurred_at)
               VALUES (?, 'deposit', ?, ?, ?)""",
            (str(event.account_id), str(event.amount), 
             event.description, event.occurred_at)
        )
    
    def on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        self._db.execute(
            """INSERT INTO transaction_history 
               (account_id, type, amount, description, occurred_at)
               VALUES (?, 'withdrawal', ?, ?, ?)""",
            (str(event.account_id), str(event.amount),
             event.description, event.occurred_at)
        )

# Пересчёт проекций (при добавлении новой или исправлении бага):
async def rebuild_projection(projection, event_store: EventStore):
    """Пересчитать проекцию с нуля из всех событий."""
    # Очищаем проекцию
    projection.reset()
    
    # Загружаем все события в хронологическом порядке
    async for event in event_store.stream_all_events():
        projection.apply(event)
    
    print("Projection rebuilt successfully")
```

## Преимущества Event Sourcing

### 1. Полный аудит-лог из коробки

```python
# Традиционный подход: нужно отдельно писать audit log
def update_user(user_id, new_data, changed_by):
    db.execute("UPDATE users SET ... WHERE id = ?", ...)
    audit_log.insert({
        'entity': 'user', 'entity_id': user_id,
        'changed_by': changed_by, 'changes': diff(old_data, new_data)
    })
    # Забыть записать в audit_log = дыра в аудите

# Event Sourcing: события — это и есть audit log
# Нельзя "забыть" записать событие — без события нет изменения
```

### 2. Отладка по времени (Time Travel)

```python
# Восстановить состояние счёта на конкретную дату
def get_account_at(account_id: UUID, at: datetime) -> BankAccount:
    events = event_store.load_events_up_to(account_id, at)
    return BankAccount.restore(events)

# "Что было у клиента 3 января прошлого года?"
account_jan_3 = get_account_at(account_id, datetime(2024, 1, 3))
print(f"Balance on Jan 3: {account_jan_3._balance}")
```

### 3. Новые read models ретроспективно

```python
# Через год понадобился новый отчёт: "Среднее время между транзакциями"
# При традиционном подходе: исторических данных нет
# При Event Sourcing: пересчитываем все события за всё время

class AvgTimeBetweenTransactionsProjection:
    def __init__(self, analytics_db):
        self._db = analytics_db
    
    def on_money_deposited(self, event: MoneyDeposited) -> None:
        self._update_timing(event.account_id, event.occurred_at)
    
    def on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        self._update_timing(event.account_id, event.occurred_at)
    
    # ... и запускаем rebuild на всей исторической базе событий
```

## Сложности Event Sourcing

### 1. Изменение схемы событий

```python
# Версия 1 события:
@dataclass(frozen=True)
class MoneyWithdrawn_v1:
    account_id: UUID
    amount: Decimal

# Версия 2: добавили поле description
@dataclass(frozen=True)
class MoneyWithdrawn_v2:
    account_id: UUID
    amount: Decimal
    description: str  # НОВОЕ ПОЛЕ

# Проблема: в event store миллионы событий v1 без description
# Решение 1: Upcasting — при загрузке старых событий конвертируем
def deserialize_event(row: dict):
    if row['event_type'] == 'MoneyWithdrawn':
        data = json.loads(row['event_data'])
        if 'description' not in data:
            data['description'] = 'N/A'  # default для старых событий
        return MoneyWithdrawn(**data)
```

### 2. Eventual Consistency

При асинхронных проекциях — пользователь может не сразу увидеть результат своего действия.

```python
# Пользователь снял деньги. Читает баланс.
# Проекция ещё не успела обновиться.
# Пользователь видит старый баланс. Это нормально — eventual consistency.

# Решение: readYourWrites — читать из write model для критичных операций
def get_my_current_balance(account_id: UUID, user_session) -> Decimal:
    # Если пользователь только что делал транзакции
    if user_session.has_recent_writes:
        # Читать из write side (медленнее, но консистентно)
        account = account_repo.find_by_id(account_id)
        return account._balance
    else:
        # Читать из fast read model
        return balance_projection.get_balance(account_id)
```

## Связь с Kafka и Domain Events

Event Sourcing хорошо сочетается с Kafka как event log:

```python
# Kafka как event store + message bus
from kafka import KafkaProducer, KafkaConsumer
import json

class KafkaEventBus:
    def __init__(self, bootstrap_servers: list[str]):
        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',         # Подтверждение от всех реплик
            enable_idempotence=True  # Exactly-once semantics
        )
    
    def publish(self, event, topic: str) -> None:
        """Публикуем событие в Kafka."""
        self._producer.send(
            topic,
            key=str(event.account_id).encode('utf-8'),  # По ключу — партиционирование
            value={
                'event_type': type(event).__name__,
                'event_data': event.__dict__,
                'schema_version': 2
            }
        )

# Projection потребляет события из Kafka
class ProjectionConsumer:
    def run(self):
        consumer = KafkaConsumer(
            'bank-events',
            bootstrap_servers=['kafka:9092'],
            group_id='balance-projection',
            auto_offset_reset='earliest',  # Читаем с начала (для rebuild)
            enable_auto_commit=False
        )
        
        for message in consumer:
            event = deserialize(message.value)
            self._projection.apply(event)
            consumer.commit()  # Commit только после успешной обработки
```

## Axon Framework: пример реализации

Axon Framework (Java) — популярный фреймворк для CQRS + Event Sourcing:

```java
// Axon: Aggregate с Event Sourcing
@Aggregate
public class BankAccount {
    @AggregateIdentifier
    private String accountId;
    private BigDecimal balance;
    
    // Command handler
    @CommandHandler
    public BankAccount(OpenAccountCommand cmd) {
        apply(new AccountOpenedEvent(cmd.getAccountId(), cmd.getInitialBalance()));
    }
    
    @CommandHandler
    public void handle(WithdrawMoneyCommand cmd) {
        if (balance.compareTo(cmd.getAmount()) < 0) {
            throw new InsufficientFundsException();
        }
        apply(new MoneyWithdrawnEvent(accountId, cmd.getAmount()));
    }
    
    // Event sourcing handlers (восстановление состояния)
    @EventSourcingHandler
    public void on(AccountOpenedEvent event) {
        this.accountId = event.getAccountId();
        this.balance = event.getInitialBalance();
    }
    
    @EventSourcingHandler
    public void on(MoneyWithdrawnEvent event) {
        this.balance = this.balance.subtract(event.getAmount());
    }
}

// Query Handler
@Component
public class AccountQueryHandler {
    @QueryHandler
    public AccountView handle(GetAccountQuery query) {
        return accountViewRepository.findById(query.getAccountId())
            .orElseThrow(() -> new AccountNotFoundException(query.getAccountId()));
    }
}
```

## Когда применять CQRS и Event Sourcing

**CQRS без Event Sourcing** — хорошее решение когда:
- Нагрузка на чтение >> нагрузка на запись (нужна separate read model)
- Нужны разные модели данных для разных представлений
- Начальный шаг перед Event Sourcing

**Event Sourcing без CQRS** — редко встречается, но возможно для систем, где нужен audit trail.

**CQRS + Event Sourcing** — для:
- Финансовые системы (банк, платежи) — полная история обязательна
- Системы, где важен аудит (медицина, юриспруденция)
- Комплексные доменные модели с богатой бизнес-логикой
- Системы с высокими требованиями к eventual consistency

**Не использовать CQRS/ES для:**
- Простых CRUD операций
- Маленьких систем без сложной бизнес-логики
- Команды без экспертизы в этих паттернах

## Заключение

CQRS решает задачу масштабируемости чтения и оптимизации моделей под разные use cases. Event Sourcing решает задачу хранения полной истории изменений и возможности построения новых проекций ретроспективно.

Вместе они обеспечивают мощную архитектуру для сложных доменов, но несут значительный overhead в сложности. Ключевой вопрос перед применением: «Какую проблему я решаю?» Если ответ — «это выглядит архитектурно красиво», то лучше остаться на простом CRUD.

## Литература

1. **Young, Greg** — «CQRS Documents» (2010): https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
2. **Fowler, Martin** — «CQRS» (2011): https://martinfowler.com/bliki/CQRS.html
3. **Fowler, Martin** — «Event Sourcing» (2005): https://martinfowler.com/eaaDev/EventSourcing.html
4. **Evans, Eric** — «Domain-Driven Design». Addison-Wesley, 2003. ISBN: 978-0321125217
5. **Vernon, Vaughn** — «Implementing Domain-Driven Design», Chapters 4-7. Addison-Wesley, 2013
6. **Richardson, Chris** — «Microservices Patterns», Chapter 7: Implementing queries in a microservice architecture. Manning, 2018
7. **Kleppmann, Martin** — «Designing Data-Intensive Applications», Chapter 11: Stream Processing. O'Reilly, 2017
8. **Axon Framework Documentation** — https://docs.axoniq.io/reference-guide/
9. **Microsoft Azure Architecture Center** — «CQRS pattern»: https://docs.microsoft.com/en-us/azure/architecture/patterns/cqrs
10. **Betts, Dominic et al.** — «Exploring CQRS and Event Sourcing». Microsoft patterns & practices, 2013: https://docs.microsoft.com/en-us/previous-versions/msp-n-p/jj554200(v=pandp.10)
