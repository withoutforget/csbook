# Идемпотентность и гарантии доставки: exactly-once в распределённых системах

Сеть ненадёжна. Это не баг, это фундаментальное свойство. Пакеты теряются, связь прерывается, узлы зависают и перезапускаются. Когда клиент отправляет запрос и не получает ответ — он не знает, что произошло: запрос потерялся по пути, сервер упал до обработки, сервер обработал и ответ потерялся. Во всех трёх случаях клиент видит одно и то же — тишину.

Что должен делать клиент? Повторить запрос, рискуя двойной обработкой? Или не повторять, рискуя потерей данных? Эта дилемма стоит в центре проектирования надёжных распределённых систем.

## Три гарантии доставки

Формально можно выделить три уровня гарантий доставки сообщений:

**At-most-once** (не более одного раза): сообщение доставляется 0 или 1 раз. Дубликатов нет, но возможна потеря. Подходит для: аналитика, метрики, UDP-трансляции.

**At-least-once** (не менее одного раза): сообщение доставляется 1 или более раз. Потери нет, но возможны дубликаты. Подходит для большинства систем при условии идемпотентных операций.

**Exactly-once** (ровно один раз): сообщение доставляется ровно 1 раз. Самая желанная, самая сложная. По факту достигается через at-least-once + дедупликацию или через транзакционные механизмы.

```
                 Сеть
Отправитель ─────────── Получатель

At-most-once:
  Send → [потеря?] → recv? → обработка
  Если потеря — сообщение утеряно навсегда

At-least-once:
  Send → recv → обработка
  При неудаче: retry → recv → обработка (дубликат!)
  
Exactly-once:
  Send + dedup_id → recv → check_seen → обработка → mark_seen
  При дубликате: check_seen → уже видели → пропустить
```

## Идемпотентность как фундамент

**Идемпотентная операция** — такая, которую можно выполнить несколько раз с тем же результатом, что и один раз. Математически: f(f(x)) = f(x).

HTTP-глаголы (по RFC 7231):
- GET — идемпотентен (чтение, нет побочных эффектов)
- PUT — идемпотентен (замена ресурса целиком)
- DELETE — идемпотентен (удаление уже удалённого — тот же результат)
- POST — **не** идемпотентен (создание новой сущности каждый раз)
- PATCH — зависит от реализации

```python
# Неидемпотентная операция
def charge_card_bad(user_id: str, amount: float):
    """Каждый вызов списывает деньги — двойной retry = двойное списание!"""
    transaction_id = db.insert("transactions", {
        "user_id": user_id,
        "amount": amount,
        "timestamp": time.time()
    })
    payment_gateway.charge(user_id, amount)
    return transaction_id

# Идемпотентная версия через idempotency key
def charge_card_idempotent(user_id: str, amount: float, idempotency_key: str):
    """
    Idempotency key — уникальный идентификатор попытки операции.
    Клиент генерирует его один раз и использует при ретраях.
    """
    # Проверяем, не обрабатывали ли уже этот запрос
    existing = db.find("transactions", {"idempotency_key": idempotency_key})
    if existing:
        return existing["transaction_id"]  # возвращаем предыдущий результат
    
    # Новая операция — выполняем
    with db.transaction():
        # Атомарно: записываем ключ + создаём транзакцию
        transaction_id = db.insert("transactions", {
            "user_id": user_id,
            "amount": amount,
            "idempotency_key": idempotency_key,
            "timestamp": time.time()
        })
        payment_gateway.charge(user_id, amount)
    
    return transaction_id
```

Stripe, AWS, Braintree — все крупные платёжные системы требуют передавать idempotency key при любых мутирующих операциях.

## Паттерны идемпотентного дизайна

### Условные обновления (Compare-and-Swap)

Вместо "увеличь баланс на 10" используйте "установи баланс в 110, если сейчас 100". Если операция выполняется дважды, второй раз CAS не пройдёт (баланс уже 110, не 100).

```python
class Account:
    def __init__(self, account_id: str, db):
        self.id = account_id
        self.db = db
    
    def deposit_idempotent(self, amount: float, idempotency_key: str) -> dict:
        """Идемпотентное пополнение через CAS + idempotency key."""
        
        # Проверяем idempotency key
        existing = self.db.find_one(
            "operations",
            {"idempotency_key": idempotency_key}
        )
        if existing:
            return existing
        
        max_retries = 3
        for attempt in range(max_retries):
            # Читаем текущее состояние
            account = self.db.find_one("accounts", {"id": self.id})
            current_balance = account["balance"]
            current_version = account["version"]
            new_balance = current_balance + amount
            
            # CAS: обновляем только если версия не изменилась
            updated = self.db.update_one(
                "accounts",
                filter={"id": self.id, "version": current_version},
                update={"balance": new_balance, "version": current_version + 1}
            )
            
            if updated.modified_count == 1:
                # Успех — записываем результат для idempotency
                result = {
                    "idempotency_key": idempotency_key,
                    "account_id": self.id,
                    "amount": amount,
                    "new_balance": new_balance,
                    "timestamp": time.time()
                }
                self.db.insert("operations", result)
                return result
            
            # Конкурентное обновление — retry
            time.sleep(0.01 * (2 ** attempt))  # exponential backoff
        
        raise Exception("Failed after max retries — too much contention")
```

### Upsert вместо Insert + Update

```sql
-- Плохо: может создать дубликат при ретрае
INSERT INTO orders (id, user_id, status) VALUES (?, ?, 'pending');

-- Хорошо: идемпотентно
INSERT INTO orders (id, user_id, status) 
VALUES (?, ?, 'pending')
ON CONFLICT (id) DO NOTHING;  -- PostgreSQL

-- Или upsert
INSERT INTO order_status (order_id, status, updated_at)
VALUES (?, 'shipped', NOW())
ON CONFLICT (order_id) DO UPDATE SET
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at
WHERE order_status.updated_at < EXCLUDED.updated_at;  -- монотонное обновление
```

### Outbox Pattern (Transactional Outbox)

Классическая проблема: как атомарно обновить базу данных И отправить сообщение в очередь? Если мы сначала обновляем БД, потом отправляем сообщение — при краше между ними сообщение потеряно. Если наоборот — сообщение может отправиться, а транзакция откатиться.

```python
# Transactional Outbox Pattern
class OrderService:
    def create_order(self, user_id: str, items: list, idempotency_key: str):
        """
        Все изменения — в одной транзакции.
        Сообщения в очередь — через outbox таблицу.
        """
        with self.db.transaction():
            # Проверяем идемпотентность
            if self.db.find_one("orders", {"idempotency_key": idempotency_key}):
                return  # уже обработали
            
            # Создаём заказ
            order_id = str(uuid.uuid4())
            self.db.insert("orders", {
                "id": order_id,
                "user_id": user_id,
                "items": items,
                "status": "created",
                "idempotency_key": idempotency_key
            })
            
            # Записываем сообщение в outbox (НЕ в Kafka!)
            self.db.insert("outbox", {
                "id": str(uuid.uuid4()),
                "aggregate_type": "Order",
                "aggregate_id": order_id,
                "event_type": "OrderCreated",
                "payload": json.dumps({
                    "order_id": order_id,
                    "user_id": user_id,
                    "items": items
                }),
                "created_at": time.time(),
                "published": False
            })
        
        # Транзакция зафиксирована — outbox содержит запись

# Отдельный процесс (relay) читает outbox и публикует в Kafka
class OutboxRelay:
    def run(self):
        while True:
            # Читаем неопубликованные сообщения
            messages = self.db.find(
                "outbox",
                {"published": False},
                order_by="created_at",
                limit=100
            )
            
            for msg in messages:
                # Публикуем в Kafka
                self.kafka.produce(
                    topic=f"events.{msg['event_type']}",
                    key=msg['aggregate_id'],
                    value=msg['payload'],
                    headers={"event_id": msg['id']}
                )
                
                # Помечаем как опубликованное
                self.db.update_one(
                    "outbox",
                    {"id": msg['id']},
                    {"published": True, "published_at": time.time()}
                )
            
            time.sleep(0.1)
```

Outbox relay публикует at-least-once (при краше он перечитает и опубликует повторно). Потребитель должен быть готов к дубликатам.

## Дедупликация на стороне получателя

Если отправитель не может гарантировать exactly-once, получатель должен сам дедуплицировать.

```python
import hashlib
from datetime import datetime, timedelta

class DeduplicatingConsumer:
    def __init__(self, handler, redis_client, dedup_window_hours=24):
        self.handler = handler
        self.redis = redis_client
        self.window = timedelta(hours=dedup_window_hours)
    
    def process(self, message: dict):
        """
        Обработать сообщение с дедупликацией.
        Предполагаем, что каждое сообщение имеет уникальный message_id.
        """
        message_id = message.get("message_id")
        if not message_id:
            # Нет ID — нельзя дедуплицировать, обрабатываем
            return self.handler(message)
        
        dedup_key = f"dedup:{message_id}"
        
        # Атомарная операция SET NX (Set if Not eXists)
        was_set = self.redis.set(
            dedup_key,
            "1",
            nx=True,  # только если не существует
            ex=int(self.window.total_seconds())  # TTL
        )
        
        if not was_set:
            # Уже видели это сообщение — пропускаем
            print(f"Duplicate message {message_id}, skipping")
            return None
        
        # Первый раз видим — обрабатываем
        try:
            result = self.handler(message)
            return result
        except Exception:
            # Если обработка упала — нужно удалить ключ
            # чтобы позволить ретрай
            self.redis.delete(dedup_key)
            raise
```

Важный нюанс: что делать, если мы пометили сообщение как "видели", но обработка упала? Если мы удаляем ключ при ошибке — повторная попытка будет обработана. Если оставляем — потеряем сообщение. Правильный ответ зависит от семантики: для финансов лучше ретраи, чем потери; для аналитики наоборот.

## Exactly-Once в Apache Kafka

Kafka до версии 0.11 гарантировала только at-least-once. С версии 0.11 появились idempotent producer и транзакционные продюсеры.

### Idempotent Producer

Каждый продюсер получает уникальный Producer ID (PID). Каждое сообщение получает порядковый номер (sequence number). Брокер отслеживает последний принятый номер для каждого PID+partition и отбрасывает дубликаты.

```python
from confluent_kafka import Producer, Consumer, KafkaError
import json

# Idempotent producer
producer = Producer({
    'bootstrap.servers': 'localhost:9092',
    'enable.idempotence': True,  # включить идемпотентность
    # Автоматически устанавливает:
    # acks=all, retries=INT_MAX, max.in.flight.requests.per.connection=5
})

def send_idempotent(topic: str, key: str, value: dict):
    """Отправка с гарантией at-least-once + дедупликация = exactly-once."""
    producer.produce(
        topic,
        key=key.encode(),
        value=json.dumps(value).encode()
    )
    producer.flush()
```

### Транзакционный Producer для Exactly-Once

Для потребителей, которые читают из одного топика и пишут в другой (stream processing), Kafka предоставляет транзакции: read-process-write атомарно.

```python
# Exactly-once stream processing в Kafka
from confluent_kafka import Producer, Consumer, TopicPartition

class ExactlyOnceProcessor:
    def __init__(self, consumer_group: str, transactional_id: str):
        self.producer = Producer({
            'bootstrap.servers': 'localhost:9092',
            'transactional.id': transactional_id,  # уникальный ID продюсера
        })
        self.consumer = Consumer({
            'bootstrap.servers': 'localhost:9092',
            'group.id': consumer_group,
            'enable.auto.commit': False,  # ручной commit через транзакцию
            'isolation.level': 'read_committed',  # читаем только зафиксированное
        })
        self.producer.init_transactions()
    
    def process_batch(self, input_topic: str, output_topic: str):
        """Обработать пакет сообщений exactly-once."""
        messages = self.consumer.consume(num_messages=100, timeout=1.0)
        if not messages:
            return
        
        try:
            self.producer.begin_transaction()
            
            results = []
            offsets = {}
            
            for msg in messages:
                if msg.error():
                    continue
                
                # Обрабатываем сообщение
                value = json.loads(msg.value())
                processed = self.transform(value)
                
                # Записываем результат в выходной топик
                self.producer.produce(
                    output_topic,
                    key=msg.key(),
                    value=json.dumps(processed).encode()
                )
                
                # Собираем offsets для commit
                tp = TopicPartition(msg.topic(), msg.partition(), msg.offset() + 1)
                offsets[f"{msg.topic()}:{msg.partition()}"] = tp
            
            # Атомарно: commit offsets + publish results
            self.producer.send_offsets_to_transaction(
                list(offsets.values()),
                self.consumer.consumer_group_metadata()
            )
            self.producer.commit_transaction()
            
        except Exception as e:
            self.producer.abort_transaction()
            raise
    
    def transform(self, value: dict) -> dict:
        # Ваша бизнес-логика
        return {"processed": True, "original": value}
```

Именно так работает Kafka Streams и Apache Flink (с Kafka source/sink): exactly-once processing через транзакции.

## Saga Pattern и компенсирующие транзакции

В микросервисной архитектуре нет распределённых транзакций (или они очень дорогие). Паттерн Saga позволяет организовать длинные бизнес-транзакции через последовательность локальных транзакций с компенсациями.

```python
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional

class SagaStepStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"

@dataclass
class SagaStep:
    name: str
    execute: Callable      # основная операция
    compensate: Callable   # компенсирующая операция
    status: SagaStepStatus = SagaStepStatus.PENDING
    result: Optional[dict] = None

class SagaOrchestrator:
    """
    Choreography-based saga с оркестратором.
    Каждый шаг идемпотентен (имеет свой idempotency key).
    """
    def __init__(self, saga_id: str, steps: list):
        self.saga_id = saga_id
        self.steps = steps
        self.current_step = 0
    
    def execute(self):
        # Выполняем шаги вперёд
        while self.current_step < len(self.steps):
            step = self.steps[self.current_step]
            
            try:
                idem_key = f"{self.saga_id}:{step.name}"
                step.result = step.execute(idempotency_key=idem_key)
                step.status = SagaStepStatus.COMPLETED
                self.current_step += 1
                self._save_state()
                
            except Exception as e:
                print(f"Step {step.name} failed: {e}")
                step.status = SagaStepStatus.FAILED
                self._compensate()
                return False
        
        return True
    
    def _compensate(self):
        """Откатываем уже выполненные шаги в обратном порядке."""
        for i in range(self.current_step - 1, -1, -1):
            step = self.steps[i]
            if step.status == SagaStepStatus.COMPLETED:
                try:
                    step.status = SagaStepStatus.COMPENSATING
                    idem_key = f"{self.saga_id}:{step.name}:compensate"
                    step.compensate(
                        step.result,
                        idempotency_key=idem_key
                    )
                    step.status = SagaStepStatus.COMPENSATED
                    self._save_state()
                except Exception as e:
                    print(f"Compensation for {step.name} failed: {e}")
                    # Нужна ручная интервенция или retry
                    step.status = SagaStepStatus.FAILED
    
    def _save_state(self):
        """Персистируем состояние саги для возможности восстановления."""
        pass  # Сохраняем в БД


# Пример: заказ с оплатой и резервированием товара
def create_order_saga(order_data: dict) -> SagaOrchestrator:
    steps = [
        SagaStep(
            name="create_order",
            execute=lambda **kw: order_service.create(order_data, **kw),
            compensate=lambda result, **kw: order_service.cancel(
                result["order_id"], **kw
            )
        ),
        SagaStep(
            name="reserve_inventory",
            execute=lambda **kw: inventory_service.reserve(
                order_data["items"], **kw
            ),
            compensate=lambda result, **kw: inventory_service.release(
                result["reservation_id"], **kw
            )
        ),
        SagaStep(
            name="charge_payment",
            execute=lambda **kw: payment_service.charge(
                order_data["user_id"],
                order_data["total"],
                **kw
            ),
            compensate=lambda result, **kw: payment_service.refund(
                result["transaction_id"], **kw
            )
        ),
        SagaStep(
            name="confirm_order",
            execute=lambda **kw: order_service.confirm(
                order_data["order_id"], **kw
            ),
            compensate=lambda result, **kw: None  # нет компенсации для confirm
        )
    ]
    
    return SagaOrchestrator(
        saga_id=str(uuid.uuid4()),
        steps=steps
    )
```

## Retry-логика и экспоненциальный backoff

При реализации at-least-once доставки важна правильная стратегия повторов.

```python
import time
import random
from functools import wraps
from typing import Type, Tuple

class RetryConfig:
    def __init__(
        self,
        max_attempts: int = 5,
        initial_delay: float = 0.1,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: float = 0.1  # случайный разброс для предотвращения thundering herd
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Вычислить задержку перед attempt-й попыткой (0-indexed)."""
        delay = self.initial_delay * (self.multiplier ** attempt)
        delay = min(delay, self.max_delay)
        # Добавляем случайный джиттер: ±jitter*delay
        jitter_amount = delay * self.jitter * (2 * random.random() - 1)
        return delay + jitter_amount


def retry(
    config: RetryConfig,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    non_retryable_exceptions: Tuple[Type[Exception], ...] = ()
):
    """Декоратор для автоматического retry с exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                
                except non_retryable_exceptions as e:
                    # Не ретраим эти ошибки (400 Bad Request, ValidationError и т.д.)
                    raise
                
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < config.max_attempts - 1:
                        delay = config.get_delay(attempt)
                        print(f"Attempt {attempt + 1} failed: {e}. "
                              f"Retrying in {delay:.2f}s...")
                        time.sleep(delay)
                    else:
                        print(f"All {config.max_attempts} attempts failed.")
            
            raise last_exception
        
        return wrapper
    return decorator


# Использование
config = RetryConfig(
    max_attempts=5,
    initial_delay=0.1,
    max_delay=30.0,
    multiplier=2.0
)

@retry(
    config=config,
    retryable_exceptions=(ConnectionError, TimeoutError),
    non_retryable_exceptions=(ValueError, PermissionError)
)
def send_payment(amount: float, idempotency_key: str):
    """Отправить платёж с автоматическим ретраем."""
    response = payment_api.charge(amount, idempotency_key=idempotency_key)
    return response
```

Важно: ретрай всегда должен использовать **тот же** idempotency_key. Не генерировать новый при каждой попытке!

## Dead Letter Queue (DLQ)

Сообщения, которые не удаётся обработать после всех ретраев, должны попадать в Dead Letter Queue — специальную очередь для "мёртвых" сообщений.

```python
class MessageProcessor:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.dlq = DeadLetterQueue()
    
    def process(self, message: dict):
        retry_count = message.get("retry_count", 0)
        
        try:
            self._handle(message)
        
        except NonRetryableError as e:
            # Ошибка, при которой retry бессмысленен
            self.dlq.send(message, reason=str(e), error_type="non_retryable")
        
        except RetryableError as e:
            if retry_count >= self.max_retries:
                # Исчерпали попытки
                self.dlq.send(
                    message,
                    reason=f"Max retries exceeded: {e}",
                    error_type="max_retries"
                )
            else:
                # Повторная попытка с увеличенным счётчиком
                message["retry_count"] = retry_count + 1
                message["last_error"] = str(e)
                delay = 2 ** retry_count  # exponential backoff в секундах
                self.queue.send_with_delay(message, delay_seconds=delay)
    
    def _handle(self, message: dict):
        pass  # бизнес-логика


class DeadLetterQueue:
    def send(self, message: dict, reason: str, error_type: str):
        """Сохранить неудавшееся сообщение для анализа."""
        dlq_record = {
            **message,
            "dlq_timestamp": time.time(),
            "dlq_reason": reason,
            "dlq_error_type": error_type
        }
        # Сохраняем в хранилище для последующего анализа
        self.storage.insert("dead_letter_queue", dlq_record)
        # Опционально: уведомить команду
        self.alerting.send_alert(f"Message in DLQ: {reason}")
```

## Двухфазная фиксация (2PC) и её проблемы

Двухфазная фиксация (Two-Phase Commit, 2PC) — классический протокол для распределённых транзакций. Координатор управляет участниками.

**Фаза 1 (Prepare/Vote)**: координатор просит каждого участника подготовиться к транзакции и ответить «готов» или «отказ».

**Фаза 2 (Commit/Rollback)**: если все ответили «готов» — координатор отправляет Commit. Если хоть один «отказ» — Abort.

```python
class TwoPhaseCommitCoordinator:
    def __init__(self, participants: list):
        self.participants = participants
    
    def execute(self, transaction_id: str, operations: dict) -> bool:
        """
        Выполнить транзакцию через 2PC.
        operations: {participant_id: operation_data}
        """
        
        # === ФАЗА 1: PREPARE ===
        prepared = []
        for participant in self.participants:
            try:
                response = participant.prepare(
                    transaction_id,
                    operations.get(participant.id, {})
                )
                if response == "READY":
                    prepared.append(participant)
                else:
                    # Участник отказал — прерываем
                    self._abort(transaction_id, prepared)
                    return False
            except Exception as e:
                # Участник недоступен — прерываем
                print(f"Participant {participant.id} failed in prepare: {e}")
                self._abort(transaction_id, prepared)
                return False
        
        # Все готовы — записываем решение (persistently!)
        self._log_commit_decision(transaction_id)
        
        # === ФАЗА 2: COMMIT ===
        for participant in self.participants:
            retries = 0
            while True:
                try:
                    participant.commit(transaction_id)
                    break
                except Exception as e:
                    retries += 1
                    if retries > 10:
                        # Оставляем в незавершённом состоянии — нужна ручная интервенция
                        print(f"CRITICAL: Cannot commit {participant.id}")
                        break
                    time.sleep(2 ** retries)
        
        return True
    
    def _abort(self, transaction_id: str, prepared: list):
        """Отправить Abort всем, кто успел подготовиться."""
        for participant in prepared:
            try:
                participant.abort(transaction_id)
            except Exception:
                # Игнорируем ошибки при abort
                pass
```

**Проблемы 2PC:**
1. **Блокирующий протокол**: если координатор упал после Prepare, участники заблокированы — они не знают commit или abort
2. **Низкая производительность**: два RTT + диски для журналирования
3. **Single point of failure**: координатор — узкое место

Поэтому в современных системах 2PC используют редко. Вместо него — Saga паттерн для длинных транзакций и Raft/Paxos для короткой согласованности.

## Практические рекомендации

**Идемпотентность:**
- Всегда добавляйте idempotency key в мутирующие API (особенно платежи, уведомления)
- Храните idempotency keys с TTL (обычно 24 часа — 7 дней)
- Идемпотентный ответ должен возвращать тот же результат, что и первоначальный

**Доставка сообщений:**
- At-least-once + idempotent consumers — самый практичный подход
- Используйте outbox pattern для атомарной записи в БД + отправки сообщений
- DLQ обязателен для production систем

**Ретраи:**
- Всегда экспоненциальный backoff с jitter
- Разграничивайте retryable и non-retryable ошибки
- Ретрай с тем же idempotency key

**Мониторинг:**
- Метрики: количество ретраев, DLQ size, idempotency cache hit rate
- Алерты при росте DLQ

## Заключение

Надёжная обработка сообщений в распределённых системах строится на двух столпах: правильных гарантиях доставки и идемпотентных операциях. Exactly-once — это не магическая гарантия системы, а архитектурный результат: at-least-once доставка плюс идемпотентные получатели.

Проектируя систему, явно определяйте, какие гарантии нужны каждой операции. Денежные переводы требуют идемпотентности и deduplication на каждом уровне. Метрики продуктивности — нет. Понимание этих различий позволяет выбирать правильные инструменты и не переплачивать за сложность там, где она не нужна.

## Литература

1. Kleppmann, M. (2017). **Designing Data-Intensive Applications**. O'Reilly Media. Chapter 11 (Stream Processing), Chapter 9 (Consistency and Consensus).
2. Bernstein, P., Hadzilacos, V., Goodman, N. (1987). **Concurrency Control and Recovery in Database Systems**. Addison-Wesley.
3. Gray, J., Reuter, A. (1992). **Transaction Processing: Concepts and Techniques**. Morgan Kaufmann.
4. Hohpe, G., Woolf, B. (2004). **Enterprise Integration Patterns**. Addison-Wesley. (Idempotent Receiver, Dead Letter Channel patterns)
5. Garcia-Molina, H., Salem, K. (1987). **Sagas**. *ACM SIGMOD*, 249–259.
6. Confluent Documentation (2023). **Exactly-once Semantics in Apache Kafka**. https://docs.confluent.io/kafka/design/transactions.html
7. AWS Documentation (2023). **Idempotency** in AWS Lambda. https://docs.aws.amazon.com/lambda/latest/dg/invocation-idempotence.html
8. Stripe Engineering (2020). **Idempotency Keys**. https://stripe.com/blog/idempotency
9. Richardson, C. (2018). **Microservices Patterns**. Manning Publications. Chapter 4 (Saga Pattern).
10. Tanenbaum, A., Van Steen, M. (2017). **Distributed Systems**, 3rd ed. Chapter 7 (Consistency and Replication).
