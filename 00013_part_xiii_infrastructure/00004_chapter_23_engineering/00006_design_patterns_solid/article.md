# Паттерны проектирования и принципы SOLID

В 1994 году вышла книга "Design Patterns: Elements of Reusable Object-Oriented Software" за авторством четырёх авторов: Gamma, Helm, Johnson, Vlissides — известных как **Gang of Four (GoF)**. Книга изменила то, как программисты думают о структуре кода. Впервые была создана общая терминология для решения повторяющихся задач.

Паттерны проектирования — это не библиотеки и не готовый код. Это описания решений, которые сработали в разных контекстах. Знание паттернов даёт два преимущества: вы находите решение быстрее, и вы можете назвать его коллегам одним словом вместо пятиминутного объяснения.

## Принципы SOLID

SOLID — это пять принципов объектно-ориентированного проектирования, сформулированных Робертом Мартином (Uncle Bob). Это фундамент, на котором строятся паттерны.

### S — Single Responsibility Principle

**Класс должен иметь только одну причину для изменения.**

Это не значит "делать одно действие". Это значит: у класса должен быть один владелец — одна команда или один бизнес-домен, который определяет, как он меняется.

```python
# ПЛОХО: класс с несколькими обязанностями
class User:
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email
    
    def save_to_database(self):  # Обязанность: хранение данных
        db.execute("INSERT INTO users VALUES (?, ?)", self.name, self.email)
    
    def send_welcome_email(self):  # Обязанность: уведомления
        smtp.send(to=self.email, subject="Welcome!", body=f"Hello, {self.name}")
    
    def generate_report(self):  # Обязанность: отчёты
        return f"User: {self.name}, Email: {self.email}"
```

Если меняется схема БД — меняется User. Если меняется SMTP — меняется User. Если меняется формат отчёта — меняется User. Три разные причины для изменения.

```python
# ХОРОШО: каждый класс — одна ответственность
class User:
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

class UserRepository:
    def save(self, user: User) -> None:
        db.execute("INSERT INTO users VALUES (?, ?)", user.name, user.email)

class UserNotifier:
    def send_welcome(self, user: User) -> None:
        smtp.send(to=user.email, subject="Welcome!", body=f"Hello, {user.name}")

class UserReporter:
    def generate(self, user: User) -> str:
        return f"User: {user.name}, Email: {user.email}"
```

### O — Open/Closed Principle

**Код должен быть открыт для расширения, но закрыт для изменения.**

Добавление новой функциональности не должно требовать изменения существующего кода.

```python
# ПЛОХО: добавление нового типа платежа требует изменения ProcessPayment
class PaymentProcessor:
    def process(self, payment_type: str, amount: float):
        if payment_type == "credit_card":
            self._charge_card(amount)
        elif payment_type == "paypal":
            self._charge_paypal(amount)
        elif payment_type == "crypto":  # Новый тип — изменяем существующий код
            self._charge_crypto(amount)
        else:
            raise ValueError(f"Unknown payment type: {payment_type}")
```

```python
# ХОРОШО: добавляем новый класс, не изменяем существующий
from abc import ABC, abstractmethod

class PaymentMethod(ABC):
    @abstractmethod
    def charge(self, amount: float) -> bool:
        pass

class CreditCardPayment(PaymentMethod):
    def charge(self, amount: float) -> bool:
        return stripe.charge(amount)

class PayPalPayment(PaymentMethod):
    def charge(self, amount: float) -> bool:
        return paypal.create_payment(amount)

class CryptoPayment(PaymentMethod):  # Новый тип — новый класс, старый код не трогаем
    def charge(self, amount: float) -> bool:
        return bitcoin.broadcast_transaction(amount)

class PaymentProcessor:
    def process(self, method: PaymentMethod, amount: float) -> bool:
        return method.charge(amount)
```

### L — Liskov Substitution Principle

**Подтипы должны быть заменяемы своими базовыми типами.**

Если функция принимает `Bird`, то любой наследник `Bird` должен работать корректно. Этот принцип нарушается чаще, чем кажется.

```python
# ПЛОХО: классический пример нарушения LSP
class Bird:
    def fly(self) -> None:
        print("Flying")

class Penguin(Bird):  # Пингвин — птица, но не летает
    def fly(self) -> None:
        raise NotImplementedError("Penguins can't fly!")

def make_bird_fly(bird: Bird) -> None:
    bird.fly()  # Взорвётся с Penguin!

make_bird_fly(Penguin())  # NotImplementedError
```

```python
# ХОРОШО: иерархия отражает реальные возможности
class Bird:
    def breathe(self) -> None:
        print("Breathing")

class FlyingBird(Bird):
    def fly(self) -> None:
        print("Flying")

class Penguin(Bird):  # Правильное место в иерархии
    def swim(self) -> None:
        print("Swimming")

class Sparrow(FlyingBird):
    pass

def make_fly(bird: FlyingBird) -> None:
    bird.fly()  # Работает только с реальными летающими птицами
```

### I — Interface Segregation Principle

**Клиенты не должны зависеть от интерфейсов, которые они не используют.**

```python
# ПЛОХО: толстый интерфейс
from abc import ABC, abstractmethod

class Worker(ABC):
    @abstractmethod
    def work(self): pass
    
    @abstractmethod
    def eat(self): pass  # Роботы не едят!
    
    @abstractmethod
    def sleep(self): pass  # Роботы не спят!

class RobotWorker(Worker):
    def work(self):
        print("Robot working")
    
    def eat(self):
        raise NotImplementedError("I'm a robot!")  # Нарушение!
    
    def sleep(self):
        raise NotImplementedError("I'm a robot!")  # Нарушение!
```

```python
# ХОРОШО: разделённые интерфейсы
class Workable(ABC):
    @abstractmethod
    def work(self): pass

class Eatable(ABC):
    @abstractmethod
    def eat(self): pass

class Sleepable(ABC):
    @abstractmethod
    def sleep(self): pass

class HumanWorker(Workable, Eatable, Sleepable):
    def work(self): print("Human working")
    def eat(self): print("Human eating")
    def sleep(self): print("Human sleeping")

class RobotWorker(Workable):  # Только то, что нужно
    def work(self): print("Robot working")
```

### D — Dependency Inversion Principle

**Модули высокого уровня не должны зависеть от модулей низкого уровня. Оба должны зависеть от абстракций.**

```python
# ПЛОХО: высокоуровневый OrderService зависит от конкретной реализации
class MySQLOrderRepository:
    def save(self, order): 
        mysql.execute("INSERT INTO orders ...")

class OrderService:
    def __init__(self):
        self.repo = MySQLOrderRepository()  # Жёсткая зависимость!
    
    def create_order(self, order):
        self.repo.save(order)

# Нельзя протестировать без реальной MySQL!
# Нельзя переключиться на PostgreSQL без изменения OrderService!
```

```python
# ХОРОШО: зависим от абстракции
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Order:
    id: str
    user_id: int
    items: list

class OrderRepository(ABC):
    @abstractmethod
    def save(self, order: Order) -> None: pass
    
    @abstractmethod
    def find_by_id(self, order_id: str) -> Order | None: pass

class MySQLOrderRepository(OrderRepository):
    def save(self, order: Order) -> None:
        mysql.execute("INSERT INTO orders ...")
    
    def find_by_id(self, order_id: str) -> Order | None:
        row = mysql.fetchone("SELECT * FROM orders WHERE id = ?", order_id)
        return Order(**row) if row else None

class InMemoryOrderRepository(OrderRepository):  # Для тестов!
    def __init__(self):
        self._storage: dict[str, Order] = {}
    
    def save(self, order: Order) -> None:
        self._storage[order.id] = order
    
    def find_by_id(self, order_id: str) -> Order | None:
        return self._storage.get(order_id)

class OrderService:
    def __init__(self, repo: OrderRepository):  # Dependency Injection
        self._repo = repo
    
    def create_order(self, order: Order) -> None:
        # Бизнес-логика...
        self._repo.save(order)

# Продакшн
service = OrderService(MySQLOrderRepository())

# Тест
service = OrderService(InMemoryOrderRepository())
```

## Паттерны GoF: систематизация

GoF разделил паттерны на три категории:
- **Порождающие (Creational)**: как создавать объекты
- **Структурные (Structural)**: как компоновать объекты
- **Поведенческие (Behavioral)**: как организовать взаимодействие

### Порождающие паттерны

#### Singleton

Гарантирует один экземпляр класса. Один из самых критикуемых паттернов — часто является антипаттерном из-за скрытых зависимостей.

```python
import threading

class DatabaseConnection:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # Double-checked locking
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._conn = create_db_connection()
        self._initialized = True

# Лучший способ в Python — модульный singleton
# database.py
_connection = None

def get_connection():
    global _connection
    if _connection is None:
        _connection = create_db_connection()
    return _connection
```

#### Factory Method

Делегирует создание объектов подклассам:

```python
from abc import ABC, abstractmethod

class Notification(ABC):
    @abstractmethod
    def send(self, message: str, recipient: str) -> bool:
        pass

class EmailNotification(Notification):
    def send(self, message: str, recipient: str) -> bool:
        return smtp.send(to=recipient, body=message)

class SMSNotification(Notification):
    def send(self, message: str, recipient: str) -> bool:
        return twilio.send(to=recipient, body=message)

class PushNotification(Notification):
    def send(self, message: str, recipient: str) -> bool:
        return fcm.send(token=recipient, body=message)

class NotificationFactory:
    _registry: dict[str, type[Notification]] = {}
    
    @classmethod
    def register(cls, name: str, notification_class: type[Notification]):
        cls._registry[name] = notification_class
    
    @classmethod
    def create(cls, channel: str) -> Notification:
        if channel not in cls._registry:
            raise ValueError(f"Unknown channel: {channel}")
        return cls._registry[channel]()

# Регистрация
NotificationFactory.register("email", EmailNotification)
NotificationFactory.register("sms", SMSNotification)
NotificationFactory.register("push", PushNotification)

# Использование
notifier = NotificationFactory.create("email")
notifier.send("Your order is ready!", "user@example.com")
```

#### Builder

Для создания сложных объектов шаг за шагом:

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class QueryBuilder:
    _table: str = ""
    _conditions: list[str] = field(default_factory=list)
    _columns: list[str] = field(default_factory=list)
    _order_by: Optional[str] = None
    _limit: Optional[int] = None
    _offset: int = 0
    
    def table(self, name: str) -> 'QueryBuilder':
        self._table = name
        return self  # Fluent interface
    
    def select(self, *columns: str) -> 'QueryBuilder':
        self._columns.extend(columns)
        return self
    
    def where(self, condition: str) -> 'QueryBuilder':
        self._conditions.append(condition)
        return self
    
    def order_by(self, column: str, direction: str = "ASC") -> 'QueryBuilder':
        self._order_by = f"{column} {direction}"
        return self
    
    def limit(self, n: int) -> 'QueryBuilder':
        self._limit = n
        return self
    
    def build(self) -> str:
        columns = ", ".join(self._columns) if self._columns else "*"
        query = f"SELECT {columns} FROM {self._table}"
        
        if self._conditions:
            query += " WHERE " + " AND ".join(self._conditions)
        if self._order_by:
            query += f" ORDER BY {self._order_by}"
        if self._limit:
            query += f" LIMIT {self._limit}"
        if self._offset:
            query += f" OFFSET {self._offset}"
        
        return query

# Использование
query = (QueryBuilder()
    .table("orders")
    .select("id", "user_id", "total", "status")
    .where("status = 'pending'")
    .where("created_at > NOW() - INTERVAL '7 days'")
    .order_by("created_at", "DESC")
    .limit(50)
    .build())
# SELECT id, user_id, total, status FROM orders 
# WHERE status = 'pending' AND created_at > NOW() - INTERVAL '7 days' 
# ORDER BY created_at DESC LIMIT 50
```

### Структурные паттерны

#### Decorator

Добавляет поведение к объектам динамически, без изменения класса:

```python
from functools import wraps
import time
import logging

# Python декоратор — по сути и есть паттерн Decorator

def retry(max_attempts: int = 3, delay: float = 1.0, exceptions=(Exception,)):
    """Декоратор для повторных попыток"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        time.sleep(delay * (2 ** attempt))
                        logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
            raise last_exception
        return wrapper
    return decorator

def cache(ttl_seconds: int = 60):
    """Декоратор кэширования"""
    def decorator(func):
        _cache = {}
        
        @wraps(func)
        def wrapper(*args):
            key = args
            now = time.time()
            
            if key in _cache:
                value, timestamp = _cache[key]
                if now - timestamp < ttl_seconds:
                    return value
            
            result = func(*args)
            _cache[key] = (result, now)
            return result
        
        return wrapper
    return decorator

@retry(max_attempts=3, exceptions=(ConnectionError, TimeoutError))
@cache(ttl_seconds=300)
def fetch_user_profile(user_id: int) -> dict:
    return http.get(f"/users/{user_id}")
```

OOP-вариант декоратора:

```python
class Logger:
    def log(self, message: str) -> None:
        print(f"LOG: {message}")

class LoggerDecorator(Logger):
    def __init__(self, logger: Logger, prefix: str):
        self._logger = logger
        self._prefix = prefix
    
    def log(self, message: str) -> None:
        self._logger.log(f"[{self._prefix}] {message}")

class TimestampDecorator(Logger):
    def __init__(self, logger: Logger):
        self._logger = logger
    
    def log(self, message: str) -> None:
        self._logger.log(f"[{time.strftime('%H:%M:%S')}] {message}")

# Стекируем декораторы
logger = TimestampDecorator(LoggerDecorator(Logger(), "SERVICE"))
logger.log("Server started")  # LOG: [08:15:30] [SERVICE] Server started
```

#### Adapter

Конвертирует интерфейс класса в другой интерфейс:

```python
# Устаревший класс с неудобным интерфейсом
class LegacyPaymentGateway:
    def make_payment(self, amount_cents: int, card_number: str, 
                     exp_month: int, exp_year: int, cvv: str) -> dict:
        return {"status": "ok", "transaction_id": "txn_123"}

# Новый интерфейс, которого ожидает наш код
class PaymentGateway(ABC):
    @abstractmethod
    def charge(self, amount_dollars: float, card: 'Card') -> 'PaymentResult':
        pass

@dataclass
class Card:
    number: str
    exp_month: int
    exp_year: int
    cvv: str

@dataclass
class PaymentResult:
    success: bool
    transaction_id: str

# Адаптер: оборачивает Legacy, предоставляет новый интерфейс
class LegacyGatewayAdapter(PaymentGateway):
    def __init__(self, legacy: LegacyPaymentGateway):
        self._legacy = legacy
    
    def charge(self, amount_dollars: float, card: Card) -> PaymentResult:
        # Конвертируем доллары → центы
        amount_cents = int(amount_dollars * 100)
        
        result = self._legacy.make_payment(
            amount_cents, card.number,
            card.exp_month, card.exp_year, card.cvv
        )
        
        return PaymentResult(
            success=result["status"] == "ok",
            transaction_id=result["transaction_id"]
        )
```

#### Facade

Упрощённый интерфейс для сложной подсистемы:

```python
class OrderFacade:
    """Единый интерфейс для оформления заказа"""
    
    def __init__(self):
        self._inventory = InventoryService()
        self._payment = PaymentService()
        self._shipping = ShippingService()
        self._notification = NotificationService()
        self._audit = AuditService()
    
    def place_order(self, user_id: int, items: list, 
                    payment_info: dict) -> OrderResult:
        # Клиент вызывает один метод вместо шести
        with transaction():
            # 1. Проверяем наличие
            for item in items:
                if not self._inventory.check_availability(item.sku, item.qty):
                    return OrderResult(success=False, error="Out of stock")
            
            # 2. Резервируем товар
            reservation = self._inventory.reserve(items)
            
            # 3. Проводим оплату
            payment = self._payment.charge(payment_info, total_amount(items))
            if not payment.success:
                self._inventory.release_reservation(reservation)
                return OrderResult(success=False, error="Payment failed")
            
            # 4. Создаём заявку на доставку
            shipment = self._shipping.create_shipment(user_id, items)
            
            # 5. Уведомляем пользователя
            self._notification.send_confirmation(user_id, shipment)
            
            # 6. Аудит
            self._audit.log_order(user_id, items, payment, shipment)
            
            return OrderResult(success=True, order_id=shipment.order_id)
```

### Поведенческие паттерны

#### Observer (Publish-Subscribe)

Объект уведомляет зависимых о своих изменениях:

```python
from typing import Callable
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class Event:
    type: str
    payload: dict

class EventBus:
    """Простая реализация Event Bus / Observer"""
    
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
    
    def subscribe(self, event_type: str, handler: Callable[[Event], None]):
        self._handlers[event_type].append(handler)
        return lambda: self._handlers[event_type].remove(handler)  # Unsubscribe
    
    def publish(self, event: Event):
        for handler in self._handlers[event.type]:
            try:
                handler(event)
            except Exception as e:
                logging.error(f"Handler {handler.__name__} failed: {e}")

# Использование
bus = EventBus()

def send_confirmation_email(event: Event):
    email_service.send(event.payload["user_email"], "Order confirmed!")

def update_inventory(event: Event):
    inventory.decrease(event.payload["items"])

def trigger_analytics(event: Event):
    analytics.track("order_created", event.payload)

# Подписываемся
bus.subscribe("order.created", send_confirmation_email)
bus.subscribe("order.created", update_inventory)
bus.subscribe("order.created", trigger_analytics)

# Публикуем
bus.publish(Event(
    type="order.created",
    payload={"user_email": "user@example.com", "items": [...]}
))
```

#### Strategy

Инкапсулирует алгоритмы, делая их взаимозаменяемыми:

```python
from typing import Protocol

class SortStrategy(Protocol):
    def sort(self, data: list) -> list:
        ...

class BubbleSort:
    def sort(self, data: list) -> list:
        arr = data.copy()
        n = len(arr)
        for i in range(n):
            for j in range(0, n - i - 1):
                if arr[j] > arr[j + 1]:
                    arr[j], arr[j + 1] = arr[j + 1], arr[j]
        return arr

class QuickSort:
    def sort(self, data: list) -> list:
        if len(data) <= 1:
            return data
        pivot = data[len(data) // 2]
        left = [x for x in data if x < pivot]
        middle = [x for x in data if x == pivot]
        right = [x for x in data if x > pivot]
        return self.sort(left) + middle + self.sort(right)

class Sorter:
    def __init__(self, strategy: SortStrategy):
        self._strategy = strategy
    
    def sort(self, data: list) -> list:
        return self._strategy.sort(data)
    
    def set_strategy(self, strategy: SortStrategy):
        self._strategy = strategy

# Реальный пример: стратегия ценообразования
class PricingStrategy(Protocol):
    def calculate(self, base_price: float, user: 'User') -> float:
        ...

class RegularPricing:
    def calculate(self, base_price: float, user: 'User') -> float:
        return base_price

class PremiumPricing:
    def calculate(self, base_price: float, user: 'User') -> float:
        return base_price * 0.85  # 15% скидка

class BlackFridayPricing:
    def calculate(self, base_price: float, user: 'User') -> float:
        return base_price * 0.5  # 50% скидка
```

#### Command

Инкапсулирует запрос как объект. Позволяет откладывать выполнение, отменять операции, вести лог:

```python
from abc import ABC, abstractmethod
from typing import Optional

class Command(ABC):
    @abstractmethod
    def execute(self) -> None: pass
    
    @abstractmethod
    def undo(self) -> None: pass

class CreateOrderCommand(Command):
    def __init__(self, order_service, order_data: dict):
        self._service = order_service
        self._data = order_data
        self._created_order = None
    
    def execute(self) -> None:
        self._created_order = self._service.create(self._data)
    
    def undo(self) -> None:
        if self._created_order:
            self._service.cancel(self._created_order.id)

class CommandHistory:
    def __init__(self):
        self._history: list[Command] = []
        self._redo_stack: list[Command] = []
    
    def execute(self, command: Command) -> None:
        command.execute()
        self._history.append(command)
        self._redo_stack.clear()  # После выполнения redo недоступен
    
    def undo(self) -> Optional[Command]:
        if not self._history:
            return None
        command = self._history.pop()
        command.undo()
        self._redo_stack.append(command)
        return command
    
    def redo(self) -> Optional[Command]:
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.execute()
        self._history.append(command)
        return command
```

#### Template Method

Определяет скелет алгоритма, оставляя детали подклассам:

```python
from abc import ABC, abstractmethod

class DataMigration(ABC):
    """Шаблонный метод для миграции данных"""
    
    def run(self) -> None:
        """Фиксированный алгоритм — нельзя переопределить"""
        self._validate_source()
        records = self._extract()
        transformed = self._transform(records)
        self._load(transformed)
        self._verify()
        self._cleanup()
    
    @abstractmethod
    def _extract(self) -> list: pass
    
    @abstractmethod
    def _transform(self, records: list) -> list: pass
    
    @abstractmethod
    def _load(self, records: list) -> None: pass
    
    # Опциональные хуки с реализацией по умолчанию
    def _validate_source(self) -> None:
        pass
    
    def _verify(self) -> None:
        pass
    
    def _cleanup(self) -> None:
        pass

class UsersMigration(DataMigration):
    def _extract(self) -> list:
        return old_db.query("SELECT * FROM legacy_users")
    
    def _transform(self, records: list) -> list:
        return [
            {"id": r["uid"], "email": r["email_addr"], 
             "name": r["full_name"]}
            for r in records
        ]
    
    def _load(self, records: list) -> None:
        new_db.bulk_insert("users", records)
    
    def _verify(self) -> None:
        old_count = old_db.count("legacy_users")
        new_count = new_db.count("users")
        assert old_count == new_count, f"Count mismatch: {old_count} vs {new_count}"
```

#### State

Объект меняет поведение при изменении внутреннего состояния:

```python
from abc import ABC, abstractmethod
from enum import Enum

class OrderState(ABC):
    @abstractmethod
    def confirm(self, order: 'Order') -> None: pass
    
    @abstractmethod
    def ship(self, order: 'Order') -> None: pass
    
    @abstractmethod
    def cancel(self, order: 'Order') -> None: pass
    
    @abstractmethod
    def name(self) -> str: pass

class PendingState(OrderState):
    def confirm(self, order: 'Order') -> None:
        print("Order confirmed!")
        order.state = ConfirmedState()
    
    def ship(self, order: 'Order') -> None:
        raise ValueError("Cannot ship unconfirmed order")
    
    def cancel(self, order: 'Order') -> None:
        print("Order cancelled")
        order.state = CancelledState()
    
    def name(self) -> str: return "PENDING"

class ConfirmedState(OrderState):
    def confirm(self, order: 'Order') -> None:
        raise ValueError("Order already confirmed")
    
    def ship(self, order: 'Order') -> None:
        print("Order shipped!")
        order.state = ShippedState()
    
    def cancel(self, order: 'Order') -> None:
        print("Order cancelled after confirmation")
        order.state = CancelledState()
    
    def name(self) -> str: return "CONFIRMED"

class ShippedState(OrderState):
    def confirm(self, order: 'Order') -> None:
        raise ValueError("Order already shipped")
    
    def ship(self, order: 'Order') -> None:
        raise ValueError("Order already shipped")
    
    def cancel(self, order: 'Order') -> None:
        raise ValueError("Cannot cancel shipped order")
    
    def name(self) -> str: return "SHIPPED"

class CancelledState(OrderState):
    def confirm(self, order): raise ValueError("Order is cancelled")
    def ship(self, order): raise ValueError("Order is cancelled")
    def cancel(self, order): raise ValueError("Already cancelled")
    def name(self) -> str: return "CANCELLED"

class Order:
    def __init__(self, id: str):
        self.id = id
        self.state: OrderState = PendingState()
    
    def confirm(self): self.state.confirm(self)
    def ship(self): self.state.ship(self)
    def cancel(self): self.state.cancel(self)
    def status(self): return self.state.name()
```

## Антипаттерны: что не надо делать

**God Object** — один класс знает и делает всё:
```python
# ПЛОХО
class Application:
    def handle_http_request(self): ...
    def query_database(self): ...
    def send_email(self): ...
    def process_payment(self): ...
    def generate_pdf(self): ...
    # 200 методов...
```

**Anemic Domain Model** — классы только с полями, без логики (нарушение OOP):
```python
# ПЛОХО: Order — простой data container
class Order:
    status: str
    items: list
    total: float

class OrderService:
    def place_order(self, order): ...  # Вся логика здесь
    def cancel_order(self, order): ...
    def calculate_total(self, order): ...
```

**Premature Optimization** — оптимизировать до измерения:
```python
# ПЛОХО: сложный код ради "скорости" без профилирования
def get_user(user_id: int):
    # Битовые операции вместо читаемого кода
    return _user_cache[user_id >> 3 & 0xFF] if user_id in _user_cache else db.get(user_id)
```

**Magic Numbers** — числа без объяснения:
```python
# ПЛОХО
if user.age > 18 and order.total > 10000:
    apply_discount(0.15)

# ХОРОШО
ADULT_AGE_THRESHOLD = 18
VIP_ORDER_THRESHOLD = 10_000
VIP_DISCOUNT_RATE = 0.15

if user.age > ADULT_AGE_THRESHOLD and order.total > VIP_ORDER_THRESHOLD:
    apply_discount(VIP_DISCOUNT_RATE)
```

## Паттерны в Go

Go не имеет классов и наследования, но паттерны применимы через интерфейсы и композицию:

```go
// Functional Options Pattern — идиоматичный Go
package server

type Server struct {
    host    string
    port    int
    timeout time.Duration
    maxConn int
}

type Option func(*Server)

func WithHost(host string) Option {
    return func(s *Server) {
        s.host = host
    }
}

func WithPort(port int) Option {
    return func(s *Server) {
        s.port = port
    }
}

func WithTimeout(d time.Duration) Option {
    return func(s *Server) {
        s.timeout = d
    }
}

func NewServer(opts ...Option) *Server {
    s := &Server{
        host:    "localhost",  // Defaults
        port:    8080,
        timeout: 30 * time.Second,
        maxConn: 100,
    }
    for _, opt := range opts {
        opt(s)
    }
    return s
}

// Использование
srv := NewServer(
    WithHost("0.0.0.0"),
    WithPort(9090),
    WithTimeout(60 * time.Second),
)
```

```go
// Middleware Pattern в Go — паттерн Decorator
type Handler func(ctx context.Context, req Request) (Response, error)

type Middleware func(Handler) Handler

func WithLogging(logger *slog.Logger) Middleware {
    return func(next Handler) Handler {
        return func(ctx context.Context, req Request) (Response, error) {
            start := time.Now()
            resp, err := next(ctx, req)
            logger.Info("request",
                "method", req.Method,
                "path", req.Path,
                "duration_ms", time.Since(start).Milliseconds(),
                "error", err,
            )
            return resp, err
        }
    }
}

func WithAuth(tokenValidator TokenValidator) Middleware {
    return func(next Handler) Handler {
        return func(ctx context.Context, req Request) (Response, error) {
            token := req.Header.Get("Authorization")
            claims, err := tokenValidator.Validate(token)
            if err != nil {
                return Response{Status: 401}, nil
            }
            ctx = context.WithValue(ctx, userClaimsKey, claims)
            return next(ctx, req)
        }
    }
}

func Chain(h Handler, middlewares ...Middleware) Handler {
    for i := len(middlewares) - 1; i >= 0; i-- {
        h = middlewares[i](h)
    }
    return h
}

// Использование
handler := Chain(
    processOrderHandler,
    WithLogging(logger),
    WithAuth(validator),
    WithMetrics(meter),
)
```

## Когда применять паттерны

Паттерны — это инструменты, а не цель. Применяйте их когда:

1. **Есть реальная проблема**: не "на будущее", а сегодня
2. **Проблема известная**: паттерн — решение повторяющейся проблемы
3. **Стоимость абстракции оправдана**: простой if/else лучше лишнего класса

Признаки того, что пора применить паттерн:
- Дублируется одна и та же логика в разных местах → Strategy / Template Method
- Нужно менять поведение объекта в runtime → Strategy / State
- Создание объектов становится сложным → Factory / Builder
- Зависимости мешают тестированию → Dependency Injection / Repository
- Нужно уведомлять многих при изменении → Observer

Признаки over-engineering:
- Паттерн добавляет сложности, но не решает проблемы
- Для понимания нужно читать 5 файлов вместо 1
- "Это может понадобиться" — без конкретного требования

## Литература

1. Gamma E., Helm R., Johnson R., Vlissides J. **Design Patterns: Elements of Reusable Object-Oriented Software**. Addison-Wesley, 1994. — Оригинальная книга GoF.

2. Martin R. **Clean Code: A Handbook of Agile Software Craftsmanship**. Prentice Hall, 2008. — Практические советы по написанию читаемого кода.

3. Martin R. **Agile Software Development, Principles, Patterns, and Practices**. Prentice Hall, 2002. — Исходный источник принципов SOLID.

4. Freeman E., Robson E. **Head First Design Patterns**, 2nd Edition. O'Reilly Media, 2020. — Лучший учебник для начинающих с визуальными примерами.

5. Fowler M. **Refactoring: Improving the Design of Existing Code**, 2nd Edition. Addison-Wesley, 2018. — Как улучшать дизайн кода постепенно.

6. Vlissides J. **Pattern Hatching: Design Patterns Applied**. Addison-Wesley, 1998. — Практическое применение паттернов GoF.

7. Kerievsky J. **Refactoring to Patterns**. Addison-Wesley, 2004. — Как переходить к паттернам через рефакторинг.

8. Buschmann F. et al. **Pattern-Oriented Software Architecture, Volume 1**. Wiley, 1996. — Паттерны для архитектурного уровня.

9. Martin R. **The Clean Architecture**. Uncle Bob Blog, 2012. — https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html

10. Nystrom R. **Game Programming Patterns**. Genever Benning, 2014. — https://gameprogrammingpatterns.com/ — Доступно онлайн, отличные примеры паттернов в контексте игр.
