# Saga и двухфазная фиксация: управление распределёнными транзакциями

Транзакция — одна из фундаментальных абстракций программирования. «Всё или ничего»: либо все шаги выполнились и данные согласованы, либо всё откатилось назад. В монолитном приложении с одной базой данных это работает через встроенный менеджер транзакций. Но что делать, когда бизнес-операция затрагивает три разных сервиса с разными базами данных?

Это один из сложнейших паттернов в распределённых системах. Ни одно из решений не идеально — каждое делает компромисс между согласованностью, доступностью и сложностью.

## Проблема распределённых транзакций

Представьте интернет-магазин. Оформление заказа включает:
1. Создать заказ в Order Service (база PostgreSQL)
2. Списать деньги в Payment Service (база MySQL)
3. Зарезервировать товар в Inventory Service (база MongoDB)
4. Отправить подтверждение в Notification Service

Каждый сервис имеет свою независимую базу данных. Классическая ACID-транзакция невозможна — нет единого менеджера транзакций. Если шаг 2 прошёл, но шаг 3 упал — деньги списаны, но товара нет. Нужен механизм обеспечения согласованности между сервисами.

```
Классическая транзакция (монолит):
BEGIN;
  INSERT INTO orders (...);
  UPDATE payments SET balance = balance - 100;
  UPDATE inventory SET quantity = quantity - 1;
COMMIT; -- атомарно!

Распределённая система:
Service A: INSERT INTO orders
Service B: UPDATE payments (разная БД!)  
Service C: UPDATE inventory (ещё одна БД!)
-- Как гарантировать "всё или ничего"?
```

## Двухфазная фиксация (2PC)

Двухфазная фиксация — классический протокол для распределённых транзакций, предложенный в 1970-х годах. Он вводит роль **координатора** (coordinator), который управляет участниками (participants/resource managers).

### Протокол

**Фаза 1 — Prepare (голосование):**
1. Координатор отправляет всем участникам команду PREPARE с данными транзакции
2. Каждый участник выполняет операцию, записывает её в Write-Ahead Log (WAL), но НЕ фиксирует
3. Участник отвечает READY (готов) или ABORT (отказ)

**Фаза 2 — Commit или Rollback:**
1. Если все ответили READY: координатор записывает решение COMMIT в свой WAL и отправляет COMMIT всем участникам
2. Если хоть один ABORT или timeout: координатор отправляет ROLLBACK всем

```python
import threading
import time
import logging
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field

class TxState(Enum):
    INIT = "init"
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTING = "aborting"
    ABORTED = "aborted"

@dataclass
class ParticipantVote:
    participant_id: str
    vote: str  # 'READY' or 'ABORT'
    error: Optional[str] = None

class TwoPhaseCommitCoordinator:
    """
    Реализация 2PC координатора.
    В продакшн требует persistent WAL для восстановления после сбоя.
    """
    
    def __init__(self, coordinator_id: str, wal):
        self.id = coordinator_id
        self.wal = wal  # Write-Ahead Log для durability
        self.logger = logging.getLogger(f"2PC.Coordinator.{coordinator_id}")
    
    def execute(self, transaction_id: str, participants: List,
                operations: Dict) -> bool:
        """
        Выполнить распределённую транзакцию.
        Возвращает True при успехе, False при откате.
        """
        
        # Записываем начало в WAL (для восстановления)
        self.wal.write({
            "phase": "BEGIN",
            "tx_id": transaction_id,
            "participants": [p.id for p in participants],
            "timestamp": time.time()
        })
        
        # === ФАЗА 1: PREPARE ===
        votes: List[ParticipantVote] = []
        self.logger.info(f"[{transaction_id}] Phase 1: PREPARE")
        
        prepare_threads = []
        votes_lock = threading.Lock()
        
        def prepare_participant(participant, operation):
            try:
                vote_result = participant.prepare(transaction_id, operation)
                with votes_lock:
                    votes.append(ParticipantVote(
                        participant_id=participant.id,
                        vote=vote_result
                    ))
            except Exception as e:
                self.logger.error(f"Prepare failed for {participant.id}: {e}")
                with votes_lock:
                    votes.append(ParticipantVote(
                        participant_id=participant.id,
                        vote='ABORT',
                        error=str(e)
                    ))
        
        for participant in participants:
            operation = operations.get(participant.id, {})
            t = threading.Thread(
                target=prepare_participant,
                args=(participant, operation)
            )
            prepare_threads.append(t)
            t.start()
        
        # Ждём голосов с таймаутом
        for t in prepare_threads:
            t.join(timeout=30.0)
        
        # Анализ голосов
        all_ready = (
            len(votes) == len(participants) and
            all(v.vote == 'READY' for v in votes)
        )
        
        if all_ready:
            # === ФАЗА 2: COMMIT ===
            self.logger.info(f"[{transaction_id}] Phase 2: COMMIT")
            
            # КРИТИЧНО: записать решение до отправки COMMIT
            # После этого точки нет возврата — ДОЛЖНЫ зафиксировать
            self.wal.write({
                "phase": "COMMIT_DECISION",
                "tx_id": transaction_id,
                "timestamp": time.time()
            })
            
            self._send_commit(transaction_id, participants)
            return True
        
        else:
            # === ФАЗА 2: ABORT ===
            failed = [v for v in votes if v.vote == 'ABORT']
            self.logger.warning(
                f"[{transaction_id}] Phase 2: ABORT. Failed: {failed}"
            )
            
            self.wal.write({
                "phase": "ABORT_DECISION",
                "tx_id": transaction_id,
                "timestamp": time.time()
            })
            
            self._send_abort(transaction_id, participants)
            return False
    
    def _send_commit(self, tx_id: str, participants: List):
        """Отправить COMMIT с повторными попытками (бесконечно!)."""
        for participant in participants:
            while True:  # MUST commit eventually
                try:
                    participant.commit(tx_id)
                    self.logger.info(f"Committed on {participant.id}")
                    break
                except Exception as e:
                    self.logger.error(
                        f"Commit failed on {participant.id}: {e}. Retrying..."
                    )
                    time.sleep(1.0)  # retry indefinitely
    
    def _send_abort(self, tx_id: str, participants: List):
        """Отправить ROLLBACK."""
        for participant in participants:
            try:
                participant.rollback(tx_id)
            except Exception as e:
                self.logger.error(f"Rollback failed on {participant.id}: {e}")


class TwoPhaseCommitParticipant:
    """Участник 2PC транзакции."""
    
    def __init__(self, participant_id: str, db, wal):
        self.id = participant_id
        self.db = db
        self.wal = wal
        self.prepared_txs: Dict[str, dict] = {}  # подготовленные транзакции
    
    def prepare(self, tx_id: str, operation: dict) -> str:
        """
        Выполнить операцию, но не фиксировать.
        Записать в WAL для восстановления.
        """
        try:
            # Выполняем операцию в локальной БД (но не commit!)
            self.db.begin()
            result = self.db.execute(operation)
            
            # Записываем в WAL: «готов зафиксировать tx_id»
            self.wal.write({
                "phase": "PREPARED",
                "tx_id": tx_id,
                "operation": operation,
                "result": result
            })
            
            # Сохраняем незафиксированную транзакцию
            self.prepared_txs[tx_id] = {
                "tx": self.db.get_current_transaction(),
                "operation": operation
            }
            
            return 'READY'
        
        except Exception as e:
            self.db.rollback()
            return 'ABORT'
    
    def commit(self, tx_id: str):
        """Зафиксировать подготовленную транзакцию."""
        if tx_id not in self.prepared_txs:
            # Уже зафиксировали (идемпотентность)
            return
        
        tx_data = self.prepared_txs[tx_id]
        tx_data['tx'].commit()
        
        self.wal.write({
            "phase": "COMMITTED",
            "tx_id": tx_id,
            "timestamp": time.time()
        })
        
        del self.prepared_txs[tx_id]
    
    def rollback(self, tx_id: str):
        """Откатить подготовленную транзакцию."""
        if tx_id not in self.prepared_txs:
            return  # уже откатили
        
        tx_data = self.prepared_txs[tx_id]
        tx_data['tx'].rollback()
        
        self.wal.write({
            "phase": "ABORTED",
            "tx_id": tx_id,
            "timestamp": time.time()
        })
        
        del self.prepared_txs[tx_id]
```

### Проблема блокировки при сбое координатора

Главная слабость 2PC — блокирующий протокол. Если координатор упал **после** того, как все участники ответили READY, но **до** отправки решения COMMIT/ABORT — участники заблокированы.

Они находятся в состоянии «подготовлено» и не могут ни зафиксировать, ни откатить самостоятельно: решение должен принять координатор. Ресурсы заблокированы до восстановления координатора.

```
Сценарий сбоя:

Coordinator: PREPARE P1 P2 P3
P1: READY ✓
P2: READY ✓
P3: READY ✓
Coordinator: [CRASH!] ← упал до отправки COMMIT
             
P1, P2, P3: ждут... ждут... таймаут?
             Нельзя принять решение без координатора!
             Ресурсы заблокированы.

Восстановление: координатор читает WAL
  Если COMMIT_DECISION записан → отправить COMMIT всем
  Если только BEGIN → отправить ABORT всем
```

Это делает 2PC **неподходящим** для микросервисных архитектур с частыми обновлениями и разнородными системами. Используется преимущественно в традиционных базах данных и X/Open XA стандарте.

### XA транзакции в Java

```java
// Java EE XA пример (концептуально)
import javax.transaction.*;
import javax.sql.*;

UserTransaction utx = (UserTransaction) ctx.lookup("java:comp/UserTransaction");

try {
    utx.begin();
    
    // Обращаемся к двум XA-compatible источникам
    Connection conn1 = xaDataSource1.getConnection(); // PostgreSQL
    Connection conn2 = xaDataSource2.getConnection(); // MySQL
    
    // Обычные SQL операции...
    conn1.prepareStatement("INSERT INTO orders VALUES (?)").executeUpdate(...);
    conn2.prepareStatement("UPDATE payments SET balance = balance - ?").executeUpdate(...);
    
    utx.commit(); // JTA координирует 2PC между двумя БД
} catch (Exception e) {
    utx.rollback();
}
```

## Паттерн Saga

Saga — альтернатива 2PC для длинных, многошаговых бизнес-транзакций. Вместо попытки создать единую распределённую транзакцию, Saga разбивает её на последовательность локальных транзакций с **компенсирующими операциями** для отката.

Идея впервые описана в статье Гарсия-Молины и Салема (1987) в контексте «длинных транзакций», которые не могут держать блокировки часами.

### Choreography Saga (хореография)

Каждый сервис слушает события и выполняет свою часть. Нет центрального координатора.

```
Order Service       Payment Service      Inventory Service
     |                    |                     |
OrderCreated ──────────►  |                     |
                          |                     |
                     PaymentCharged ──────────► |
                                                |
                                          InventoryReserved ──► Order Confirmed
                                                
При ошибке Inventory:
                                          InventoryFailed ─────────────────────►
                                                                PaymentRefunded ◄────
                                                          OrderCancelled ◄───────────
```

```python
from confluent_kafka import Producer, Consumer
import json
import uuid

class OrderService:
    """Choreography-based Saga. Сервис заказов."""
    
    def __init__(self, producer: Producer, consumer: Consumer):
        self.producer = producer
        self.consumer = consumer
    
    def create_order(self, user_id: str, items: list, total: float) -> str:
        """Начать сагу: создать заказ и опубликовать событие."""
        order_id = str(uuid.uuid4())
        
        # Локальная транзакция: создать заказ
        with self.db.transaction():
            self.db.insert("orders", {
                "id": order_id,
                "user_id": user_id,
                "items": items,
                "total": total,
                "status": "pending_payment"
            })
        
        # Публикуем событие — запускаем сагу
        self.producer.produce(
            topic='order-events',
            key=order_id.encode(),
            value=json.dumps({
                "event_type": "OrderCreated",
                "order_id": order_id,
                "user_id": user_id,
                "total": total,
                "items": items
            }).encode()
        )
        
        return order_id
    
    def handle_events(self):
        """Слушаем события от других сервисов."""
        self.consumer.subscribe(['payment-events', 'inventory-events'])
        
        for msg in self.consumer:
            event = json.loads(msg.value().decode())
            event_type = event['event_type']
            order_id = event['order_id']
            
            if event_type == 'PaymentFailed':
                # Компенсируем: отменяем заказ
                self._cancel_order(order_id, reason=event.get('reason'))
            
            elif event_type == 'InventoryReserved':
                # Всё готово — подтверждаем
                self._confirm_order(order_id)
            
            elif event_type == 'InventoryFailed':
                # Нет товара — нужно вернуть деньги
                self.producer.produce(
                    topic='order-events',
                    key=order_id.encode(),
                    value=json.dumps({
                        "event_type": "PaymentRefundRequested",
                        "order_id": order_id
                    }).encode()
                )
                self._cancel_order(order_id, reason="inventory_failed")
    
    def _cancel_order(self, order_id: str, reason: str):
        with self.db.transaction():
            self.db.update(
                "orders",
                where={"id": order_id},
                set={"status": "cancelled", "cancel_reason": reason}
            )
        
        self.producer.produce(
            topic='order-events',
            key=order_id.encode(),
            value=json.dumps({
                "event_type": "OrderCancelled",
                "order_id": order_id,
                "reason": reason
            }).encode()
        )
    
    def _confirm_order(self, order_id: str):
        with self.db.transaction():
            self.db.update(
                "orders",
                where={"id": order_id},
                set={"status": "confirmed"}
            )
        
        self.producer.produce(
            topic='order-events',
            key=order_id.encode(),
            value=json.dumps({
                "event_type": "OrderConfirmed",
                "order_id": order_id
            }).encode()
        )
```

**Проблемы хореографии**: трудно отследить состояние саги в целом, сложно понять полную картину из разрозненных событий. При увеличении числа сервисов граф зависимостей становится трудночитаемым.

### Orchestration Saga (оркестрация)

Центральный координатор (оркестратор) управляет шагами саги. Он знает о всей последовательности и явно вызывает каждый сервис.

```python
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from enum import Enum
import json
import uuid

class StepStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"

@dataclass
class SagaStep:
    name: str
    execute_fn: Callable
    compensate_fn: Callable
    status: StepStatus = StepStatus.PENDING
    result: Optional[dict] = None
    error: Optional[str] = None

@dataclass
class SagaInstance:
    saga_id: str
    saga_type: str
    context: dict
    steps: List[SagaStep] = field(default_factory=list)
    current_step_index: int = 0
    status: str = "running"
    
    def to_dict(self) -> dict:
        return {
            "saga_id": self.saga_id,
            "saga_type": self.saga_type,
            "context": self.context,
            "current_step": self.current_step_index,
            "status": self.status,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error
                }
                for s in self.steps
            ]
        }


class SagaOrchestrator:
    """
    Оркестратор саги.
    Состояние персистируется в БД для восстановления после сбоев.
    """
    
    def __init__(self, saga_store):
        self.saga_store = saga_store  # персистентное хранилище
    
    def execute(self, saga: SagaInstance) -> bool:
        """Выполнить сагу, начиная с текущего шага."""
        
        # Сохраняем начальное состояние
        self.saga_store.save(saga)
        
        while saga.current_step_index < len(saga.steps):
            step = saga.steps[saga.current_step_index]
            step.status = StepStatus.EXECUTING
            self.saga_store.save(saga)
            
            try:
                # Выполняем шаг с idempotency key
                idem_key = f"{saga.saga_id}:{step.name}:execute"
                step.result = step.execute_fn(
                    context=saga.context,
                    idempotency_key=idem_key
                )
                step.status = StepStatus.COMPLETED
                saga.current_step_index += 1
                self.saga_store.save(saga)
                
                print(f"[{saga.saga_id}] Step '{step.name}' completed")
            
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)
                self.saga_store.save(saga)
                
                print(f"[{saga.saga_id}] Step '{step.name}' FAILED: {e}")
                
                # Запускаем компенсацию
                return self._compensate(saga)
        
        saga.status = "completed"
        self.saga_store.save(saga)
        return True
    
    def _compensate(self, saga: SagaInstance) -> bool:
        """
        Откатить выполненные шаги в обратном порядке.
        Компенсация должна быть идемпотентной!
        """
        saga.status = "compensating"
        self.saga_store.save(saga)
        
        # Компенсируем в обратном порядке
        for i in range(saga.current_step_index - 1, -1, -1):
            step = saga.steps[i]
            
            if step.status == StepStatus.COMPLETED:
                step.status = StepStatus.COMPENSATING
                self.saga_store.save(saga)
                
                try:
                    idem_key = f"{saga.saga_id}:{step.name}:compensate"
                    step.compensate_fn(
                        context=saga.context,
                        step_result=step.result,
                        idempotency_key=idem_key
                    )
                    step.status = StepStatus.COMPENSATED
                    self.saga_store.save(saga)
                    print(f"[{saga.saga_id}] Compensated '{step.name}'")
                
                except Exception as e:
                    step.error = f"Compensation failed: {e}"
                    self.saga_store.save(saga)
                    
                    # Критично! Компенсация упала.
                    # Нужна ручная интервенция или retry
                    print(f"CRITICAL: Compensation of '{step.name}' failed!")
                    saga.status = "compensation_failed"
                    self.saga_store.save(saga)
                    return False
        
        saga.status = "compensated"
        self.saga_store.save(saga)
        return False


def build_order_saga(order_data: dict,
                     order_svc, payment_svc, inventory_svc, notification_svc) -> SagaInstance:
    """Построить сагу оформления заказа."""
    
    steps = [
        SagaStep(
            name="create_order",
            execute_fn=lambda context, idempotency_key: order_svc.create(
                user_id=context['user_id'],
                items=context['items'],
                total=context['total'],
                idempotency_key=idempotency_key
            ),
            compensate_fn=lambda context, step_result, idempotency_key: order_svc.cancel(
                order_id=step_result['order_id'],
                reason="saga_rollback",
                idempotency_key=idempotency_key
            )
        ),
        SagaStep(
            name="reserve_inventory",
            execute_fn=lambda context, idempotency_key: inventory_svc.reserve(
                items=context['items'],
                idempotency_key=idempotency_key
            ),
            compensate_fn=lambda context, step_result, idempotency_key: inventory_svc.release(
                reservation_id=step_result['reservation_id'],
                idempotency_key=idempotency_key
            )
        ),
        SagaStep(
            name="charge_payment",
            execute_fn=lambda context, idempotency_key: payment_svc.charge(
                user_id=context['user_id'],
                amount=context['total'],
                idempotency_key=idempotency_key
            ),
            compensate_fn=lambda context, step_result, idempotency_key: payment_svc.refund(
                transaction_id=step_result['transaction_id'],
                amount=context['total'],
                idempotency_key=idempotency_key
            )
        ),
        SagaStep(
            name="notify_customer",
            execute_fn=lambda context, idempotency_key: notification_svc.send_confirmation(
                user_id=context['user_id'],
                order_id=context.get('order_id'),
                idempotency_key=idempotency_key
            ),
            compensate_fn=lambda context, step_result, idempotency_key: notification_svc.send_cancellation(
                user_id=context['user_id'],
                idempotency_key=idempotency_key
            )
        )
    ]
    
    return SagaInstance(
        saga_id=str(uuid.uuid4()),
        saga_type="CreateOrder",
        context=order_data,
        steps=steps
    )
```

## Трёхфазная фиксация (3PC)

Трёхфазная фиксация (3PC) — попытка решить проблему блокировки 2PC путём добавления промежуточной фазы PRE-COMMIT.

```
Coordinator:  PREPARE → все READY →  PRE-COMMIT → все ACK →  COMMIT
                                          ↑
                              Новая промежуточная фаза
```

В фазе PRE-COMMIT участники знают, что все остальные тоже готовы (или нет). Если координатор упал после PRE-COMMIT, участники могут самостоятельно принять решение COMMIT по таймауту.

На практике 3PC используется редко из-за:
- Усложнённой реализации
- По-прежнему некорректен при network partition (теорема CAP)
- Три RTT вместо двух = ещё выше задержка

```python
# Схема 3PC (псевдокод)
class ThreePhaseCommitCoordinator:
    
    def execute(self, tx_id, participants, operations):
        # ФАЗА 1: PREPARE (то же, что в 2PC)
        votes = self._prepare_all(tx_id, participants, operations)
        if not all(v == 'READY' for v in votes):
            self._abort_all(tx_id, participants)
            return False
        
        # ФАЗА 2: PRE-COMMIT (новая!)
        # Участники узнают, что ВСЕ готовы
        pre_commit_acks = self._pre_commit_all(tx_id, participants)
        if not all(a == 'ACK' for a in pre_commit_acks):
            self._abort_all(tx_id, participants)
            return False
        
        # ФАЗА 3: COMMIT
        # Теперь участники могут самостоятельно решить при сбое координатора
        self._commit_all(tx_id, participants)
        return True
```

## Сравнительный анализ

| Критерий | 2PC | Saga (хореография) | Saga (оркестрация) | 3PC |
|----------|-----|-------------------|-------------------|-----|
| ACID | Полный | Eventual consistency | Eventual consistency | Полный* |
| Блокировка | Да | Нет | Нет | Минимальная |
| Задержка | Высокая | Низкая | Средняя | Очень высокая |
| Отказоустойчивость | Плохая | Хорошая | Хорошая | Лучше 2PC |
| Сложность | Средняя | Высокая (граф событий) | Средняя (центр) | Высокая |
| Масштабируемость | Плохая | Отличная | Хорошая | Плохая |

*3PC некорректен при network partition

## Практические паттерны

### Состояние саги в базе данных

```sql
-- Таблица для персистирования состояния саги
CREATE TABLE saga_instances (
    saga_id UUID PRIMARY KEY,
    saga_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- running, completed, compensating, failed
    context JSONB NOT NULL,
    current_step_index INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE saga_steps (
    id BIGSERIAL PRIMARY KEY,
    saga_id UUID NOT NULL REFERENCES saga_instances(saga_id),
    step_index INT NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- pending, executing, completed, compensated, failed
    result JSONB,
    error_message TEXT,
    idempotency_key VARCHAR(255),  -- для дедупликации
    executed_at TIMESTAMP,
    compensated_at TIMESTAMP,
    UNIQUE(saga_id, step_index)
);

-- Индекс для поиска незавершённых саг (для восстановления)
CREATE INDEX idx_saga_status ON saga_instances(status, updated_at)
WHERE status IN ('running', 'compensating');
```

### Восстановление после сбоя

```python
class SagaRecoveryService:
    """Восстановление незавершённых саг при рестарте."""
    
    def __init__(self, orchestrator: SagaOrchestrator, saga_store):
        self.orchestrator = orchestrator
        self.saga_store = saga_store
    
    def recover_incomplete_sagas(self):
        """Найти и продолжить незавершённые саги."""
        
        # Саги, остановленные более 5 минут назад (likely crashed)
        incomplete = self.saga_store.find_incomplete(
            older_than_minutes=5
        )
        
        for saga_instance in incomplete:
            status = saga_instance.status
            
            print(f"Recovering saga {saga_instance.saga_id} "
                  f"(status: {status}, step: {saga_instance.current_step_index})")
            
            if status == "running":
                # Продолжаем с текущего шага
                # Шаг мог быть выполнен частично — idempotency key защитит
                self.orchestrator.execute(saga_instance)
            
            elif status == "compensating":
                # Продолжаем компенсацию
                self.orchestrator._compensate(saga_instance)
            
            elif status == "compensation_failed":
                # Требует ручного вмешательства
                self._alert_ops(saga_instance)
    
    def _alert_ops(self, saga: SagaInstance):
        """Уведомить команду о проблеме."""
        print(f"ALERT: Manual intervention required for saga {saga.saga_id}")
```

### Temporal Coupling Problem в хореографии

Главная проблема хореографии — цикличные зависимости и сложность отладки. Решение — использовать Saga State Machine с явными переходами:

```python
from enum import Enum

class OrderSagaState(Enum):
    CREATED = "created"
    PAYMENT_PENDING = "payment_pending"
    INVENTORY_PENDING = "inventory_pending"
    COMPLETED = "completed"
    PAYMENT_REFUND_PENDING = "payment_refund_pending"
    CANCELLED = "cancelled"

# Таблица переходов состояний
ORDER_SAGA_TRANSITIONS = {
    (OrderSagaState.CREATED, "PaymentCharged"): 
        OrderSagaState.INVENTORY_PENDING,
    
    (OrderSagaState.CREATED, "PaymentFailed"): 
        OrderSagaState.CANCELLED,
    
    (OrderSagaState.INVENTORY_PENDING, "InventoryReserved"): 
        OrderSagaState.COMPLETED,
    
    (OrderSagaState.INVENTORY_PENDING, "InventoryFailed"): 
        OrderSagaState.PAYMENT_REFUND_PENDING,
    
    (OrderSagaState.PAYMENT_REFUND_PENDING, "PaymentRefunded"): 
        OrderSagaState.CANCELLED,
}

def transition_state(current_state: OrderSagaState, 
                     event: str) -> Optional[OrderSagaState]:
    """Вычислить следующее состояние саги."""
    return ORDER_SAGA_TRANSITIONS.get((current_state, event))
```

## Когда использовать что

**2PC/XA:**
- Традиционные enterprise-приложения с XA-совместимыми БД
- Когда нужны строгие ACID гарантии и допустима высокая задержка
- Внутри одного дата-центра с надёжной сетью
- Пример: банковские системы с синхронной репликацией

**Saga с хореографией:**
- Небольшое количество сервисов (3-5)
- Относительно простые бизнес-процессы
- Когда хочется максимальной независимости сервисов
- Хорошо подходит для event-driven архитектур

**Saga с оркестрацией:**
- Сложные бизнес-процессы с множеством ветвлений
- Когда важна видимость состояния транзакции
- Долгоживущие транзакции (минуты, часы)
- Когда нужна возможность ручного вмешательства
- Пример: процессинг заказа в e-commerce, onboarding пользователя

**Practical advice**: большинство современных микросервисных систем выбирают Saga с оркестрацией через dedicated workflow engine (Temporal, Conductor, Camunda). Это даёт визуализацию, retry логику, persistence и monitoring «из коробки».

## Заключение

Управление распределёнными транзакциями — один из самых сложных аспектов микросервисной архитектуры. Не существует серебряной пули: 2PC даёт ACID гарантии ценой доступности и масштабируемости; Saga даёт масштабируемость и отказоустойчивость ценой усложнения логики и eventual consistency.

Выбор зависит от требований бизнеса: насколько критична немедленная согласованность? Как часто происходят сбои? Насколько сложен откат? Понимание компромиссов каждого подхода — ключ к правильному проектированию.

## Литература

1. Gray, J. (1978). **Notes on Database Operating Systems**. *Operating Systems: An Advanced Course*, Springer. (оригинальное описание 2PC)
2. Garcia-Molina, H., Salem, K. (1987). **Sagas**. *ACM SIGMOD Record*, 16(3), 249–259.
3. Bernstein, P., Hadzilacos, V., Goodman, N. (1987). **Concurrency Control and Recovery in Database Systems**. Addison-Wesley.
4. Lamport, L. (1998). **The Part-Time Parliament**. *ACM TOCS*, 16(2). (Paxos для 2PC без блокировки)
5. Richardson, C. (2018). **Microservices Patterns**. Manning Publications. Chapter 4 (Managing Transactions with Sagas).
6. Kleppmann, M. (2017). **Designing Data-Intensive Applications**. O'Reilly. Chapter 9 (Consistency and Consensus).
7. Vogels, W. (2009). **Eventually Consistent**. *Communications of the ACM*, 52(1).
8. Temporal Technologies (2023). **Temporal Documentation**. https://docs.temporal.io
9. Skeen, D. (1981). **Nonblocking Commit Protocols**. *ACM SIGMOD*. (описание 3PC)
10. Helland, P. (2007). **Life beyond Distributed Transactions: an Apostate's Opinion**. *CIDR 2007*.
