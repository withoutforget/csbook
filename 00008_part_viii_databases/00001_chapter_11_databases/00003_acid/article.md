# ACID — атомарность, согласованность, изоляция, долговечность

## Введение

До появления транзакций базы данных были непредсказуемы. Представьте перевод денег: вы снимаете $100 с одного счёта, и в этот момент происходит сбой — деньги ушли, но не поступили на другой счёт. Или два пользователя одновременно покупают последний билет на концерт, и оба получают подтверждение. Это не гипотетические сценарии — это реальные проблемы, с которыми сталкивались ранние базы данных.

ACID — акроним, описывающий четыре свойства транзакций, обеспечивающих надёжность и предсказуемость. Термин был предложен Андреасом Рейтером и Тео Хэрдером в 1983 году. ACID гарантирует, что транзакции выполняются корректно даже при сбоях системы, сетевых проблемах или конкурентных изменениях.

Важно понимать: ACID — это не просто академический концепт, а набор конкретных механизмов, каждый из которых реализован специфическими способами в каждой СУБД.

---

## 1. Atomicity (Атомарность)

### 1.1 Концепция

**Атомарность**: транзакция — неделимое действие. Либо все операции выполняются успешно, либо ни одна. Нет промежуточного состояния.

```sql
-- Банковский перевод: атомарная транзакция
BEGIN;
    UPDATE accounts SET balance = balance - 100 WHERE id = 1;
    UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;

-- Если второй UPDATE упадёт — откатывается и первый
-- Деньги не могут «исчезнуть»
```

Без атомарности:
```
Время t1: UPDATE accounts SET balance = 900 WHERE id = 1;  -- Успешно
Время t2: СБОЙ СИСТЕМЫ
Результат: $100 потеряны!
```

### 1.2 Реализация: WAL и UNDO log

**Write-Ahead Log (WAL)**: перед изменением данных, изменение записывается в журнал. При сбое — можно откатить незавершённую транзакцию:

```
Журнал WAL:
[LSN=1, TXN=101, BEGIN]
[LSN=2, TXN=101, UPDATE accounts SET balance=900 WHERE id=1, old_value=1000]
[LSN=3, TXN=101, UPDATE accounts SET balance=200 WHERE id=2, old_value=100]
[LSN=4, TXN=101, COMMIT]
← Только здесь транзакция считается завершённой

При сбое ПОСЛЕ LSN=2, ДО LSN=4:
Restore process находит TXN=101 без COMMIT → ROLLBACK:
- Восстанавливает balance=1000 для id=1
```

**Savepoints** — промежуточные точки откатa:

```sql
BEGIN;
    UPDATE orders SET status = 'processing' WHERE id = 1;
    
    SAVEPOINT after_status_update;  -- Точка сохранения
    
    UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 5;
    
    -- Проблема: остаток стал отрицательным
    -- Откатываемся до savepoint (не всю транзакцию)
    ROLLBACK TO SAVEPOINT after_status_update;
    
    -- Альтернативный план
    INSERT INTO backorder_requests (order_id, product_id) VALUES (1, 5);
    
COMMIT;  -- Первый UPDATE выполнен, backorder создан
```

---

## 2. Consistency (Согласованность)

### 2.1 Концепция

**Согласованность**: транзакция переводит базу из одного допустимого состояния в другое допустимое. Все инварианты (ограничения) должны соблюдаться после транзакции.

Источники инвариантов:
- **Constraints**: NOT NULL, UNIQUE, CHECK, FOREIGN KEY
- **Triggers**: автоматические проверки и действия
- **Application logic**: бизнес-правила в коде приложения

```sql
-- Constraints как инварианты
CREATE TABLE bank_accounts (
    id      INTEGER PRIMARY KEY,
    balance DECIMAL(12,2) NOT NULL CHECK (balance >= 0),  -- Нельзя уйти в минус
    owner   INTEGER REFERENCES users(id) NOT NULL
);

CREATE TABLE order_items (
    order_id   INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

-- FOREIGN KEY гарантирует ссылочную целостность
-- Нельзя создать order_item на несуществующий product
```

### 2.2 Consistency — ответственность приложения

Важный нюанс: СУБД гарантирует только соблюдение constraints. Более сложные инварианты — ответственность приложения:

```python
# Пример: при продаже акций остаток не может стать отрицательным
# Нет стандартного CHECK для этого, нужно application logic

async def transfer_shares(from_account: int, to_account: int, shares: int, conn):
    async with conn.transaction():
        # Читаем с блокировкой FOR UPDATE
        from_balance = await conn.fetchval(
            "SELECT shares FROM portfolios WHERE account_id = $1 FOR UPDATE",
            from_account
        )
        
        if from_balance < shares:
            raise ValueError("Insufficient shares")
        
        await conn.execute(
            "UPDATE portfolios SET shares = shares - $1 WHERE account_id = $2",
            shares, from_account
        )
        await conn.execute(
            "UPDATE portfolios SET shares = shares + $1 WHERE account_id = $2",
            shares, to_account
        )
```

---

## 3. Isolation (Изоляция)

### 3.1 Концепция

**Изоляция**: параллельные транзакции не влияют друг на друга. Каждая транзакция должна выглядеть как единственная работающая в системе.

Полная изоляция (SERIALIZABLE) — дорогостоящая. Поэтому существуют уровни изоляции с разными компромиссами между производительностью и строгостью (подробнее в следующей главе).

```sql
-- Пример проблемы без изоляции:
-- Транзакция T1:                  Транзакция T2:
BEGIN;                             BEGIN;
SELECT balance FROM accounts       
WHERE id = 1;  -- Читаем 1000     UPDATE accounts 
                                   SET balance = 900 
                                   WHERE id = 1;
                                   COMMIT;
                                   
-- T1 всё ещё видит 1000!?         
-- (в зависимости от уровня изоляции)
```

### 3.2 Реализация: MVCC vs Locking

PostgreSQL использует **MVCC** (Multi-Version Concurrency Control): каждая строка имеет версии. Читатели видят snapshot на момент начала транзакции, не блокируя писателей.

MySQL InnoDB использует комбинацию: MVCC для SELECT + shared/exclusive locks для INSERT/UPDATE/DELETE.

### 3.3 Практические примеры

```sql
-- Читаем данные в контексте изоляции

-- Session 1:
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT COUNT(*) FROM orders WHERE status = 'pending';
-- Возвращает 100

-- Session 2 (параллельно):
BEGIN;
INSERT INTO orders (status) VALUES ('pending');
COMMIT;

-- Session 1 (продолжение):
SELECT COUNT(*) FROM orders WHERE status = 'pending';
-- При READ COMMITTED: 101 (видим изменение Session 2)
-- При REPEATABLE READ: 100 (snapshot не обновился)
```

---

## 4. Durability (Долговечность)

### 4.1 Концепция

**Долговечность**: после COMMIT данные сохранены permanently. Сбой системы, потеря питания, restart — данные не потеряются.

### 4.2 Реализация: fsync и WAL

Ключевой механизм: перед возвратом клиенту подтверждения COMMIT, СУБД должна убедиться что журнал (WAL) записан на диск:

```python
# Упрощённая иллюстрация (PostgreSQL внутри):

def commit_transaction(txn_id: int, changes: list):
    # 1. Записываем все изменения в WAL буфер (в памяти)
    wal_record = {
        'txn_id': txn_id,
        'changes': changes,
        'commit_time': time.time()
    }
    wal_buffer.append(wal_record)
    
    # 2. КРИТИЧНО: fsync — ждём физической записи на диск
    # БЕЗ этого: потеря питания = потеря данных
    os.fsync(wal_file.fileno())  
    
    # 3. Только теперь отвечаем клиенту "OK"
    return "COMMIT OK"

# Настройки PostgreSQL, влияющие на durability:
# synchronous_commit = on  (default) — ждём fsync перед ответом
# synchronous_commit = off — НЕ ждём (быстрее, но риск потери до 200ms данных)
# synchronous_commit = remote_apply — для репликации
```

### 4.3 Checkpoint и восстановление

```
WAL поток:
... [TXN=99, data] [TXN=100, COMMIT] [TXN=101, data] [CHECKPOINT] [TXN=102, data] ...
                                                       ↑
                                                  Все данные до checkpoint
                                                  записаны в основные файлы

После сбоя, при старте:
1. Находим последний CHECKPOINT
2. Применяем все записи WAL после checkpoint
3. Откатываем незавершённые транзакции (нет COMMIT)
```

```bash
# PostgreSQL: настройки WAL и checkpoint
# postgresql.conf:
# wal_level = replica          # Минимальный уровень WAL
# checkpoint_timeout = 5min   # Checkpoint каждые 5 минут
# max_wal_size = 1GB           # Максимальный размер WAL
# fsync = on                   # НИКОГДА не отключайте в production!
# synchronous_commit = on      # Ждать fsync

# Просмотр WAL записей (pg_waldump):
pg_waldump -p /var/lib/postgresql/data/pg_wal -s 0/1000000 -e 0/2000000
```

---

## 5. Реализация транзакций в PostgreSQL

```python
import asyncpg
import asyncio

async def bank_transfer_acid(
    from_id: int, 
    to_id: int, 
    amount: float,
    pool: asyncpg.Pool
) -> bool:
    """
    ACID-корректный банковский перевод.
    Демонстрирует все 4 свойства.
    """
    async with pool.acquire() as conn:
        # Начинаем транзакцию
        async with conn.transaction():
            # I (Isolation): используем READ COMMITTED
            # A (Atomicity): BEGIN неявно
            
            # C (Consistency): проверяем бизнес-инварианты
            from_balance = await conn.fetchval(
                "SELECT balance FROM accounts WHERE id = $1 FOR UPDATE",
                from_id
                # FOR UPDATE: блокируем строку от других изменений
            )
            
            if from_balance is None:
                raise ValueError(f"Account {from_id} not found")
            
            if from_balance < amount:
                raise ValueError(f"Insufficient funds: {from_balance} < {amount}")
            
            # Выполняем операции
            await conn.execute(
                "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
                amount, from_id
            )
            
            await conn.execute(
                "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
                amount, to_id
            )
            
            # Логируем транзакцию
            await conn.execute(
                """INSERT INTO transfers (from_id, to_id, amount, created_at) 
                   VALUES ($1, $2, $3, NOW())""",
                from_id, to_id, amount
            )
            
            # D (Durability): при COMMIT WAL записывается на диск
            # A (Atomicity): если здесь упадём — всё откатится
            
        # COMMIT происходит при выходе из context manager без исключений
        return True
```

### 5.1 Обработка ошибок транзакций

```python
import psycopg2
from psycopg2 import OperationalError, IntegrityError

def safe_transfer(from_id: int, to_id: int, amount: float):
    """Обработка различных ошибок транзакции."""
    try:
        with psycopg2.connect(DSN) as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("BEGIN")
                    
                    cur.execute(
                        "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                        (amount, from_id)
                    )
                    
                    cur.execute(
                        "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                        (amount, to_id)
                    )
                    
                    conn.commit()
                    return True
                    
                except IntegrityError as e:
                    # Нарушение constraint (CHECK balance >= 0)
                    conn.rollback()
                    raise ValueError(f"Transfer violates constraints: {e}")
                    
                except OperationalError as e:
                    # Сетевая ошибка, deadlock, etc.
                    conn.rollback()
                    raise RuntimeError(f"Database error: {e}")
                    
    except Exception:
        # Соединение закрыто при выходе из with — гарантия rollback
        raise
```

---

## 6. InnoDB: ACID в MySQL

MySQL InnoDB реализует ACID через:
- **Undo logs**: для отката транзакций
- **Redo logs**: для восстановления после сбоя (аналог WAL)
- **Buffer Pool**: кеш страниц в памяти
- **Doublewrite Buffer**: защита от частичной записи страниц

```sql
-- MySQL: явное управление транзакциями
START TRANSACTION;
    -- или: BEGIN;

UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;

-- Проверяем условие
SELECT balance FROM accounts WHERE id = 1;
-- Если 0 → нужен дополнительный контроль

COMMIT;
-- или: ROLLBACK;

-- Проверить isolation level:
SELECT @@transaction_isolation;  -- REPEATABLE-READ (default in InnoDB)
```

---

## 7. Почему BASE — не противоположность ACID

Часто говорят что NoSQL системы следуют BASE (Basically Available, Soft State, Eventual Consistency) как альтернативу ACID. Это неточное утверждение:

**ACID и BASE — не противоположности**. ACID описывает свойства транзакций. BASE описывает стратегию для распределённых систем.

```
ACID (транзакция):
- Atomicity: всё или ничего
- Consistency: инварианты соблюдены
- Isolation: параллельные транзакции не мешают
- Durability: зафиксированное не теряется

BASE (распределённая система):
- Basically Available: система всегда доступна (возможно с устаревшими данными)
- Soft State: состояние может меняться со временем (репликация)
- Eventual Consistency: в конечном счёте все реплики сойдутся
```

MongoDB, например, сначала был «без транзакций», но с версии 4.0 поддерживает ACID транзакции (на уровне реплика-сет), а с 4.2 — на уровне шардированного кластера. Redis имеет транзакции (MULTI/EXEC) с ограниченной атомарностью.

---

## Заключение

ACID — не набор абстрактных свойств, а конкретные механизмы: WAL для атомарности и долговечности, constraints для согласованности, MVCC/locking для изоляции.

**Ключевые выводы**:

1. **Atomicity**: WAL записывает намерение до выполнения. При сбое — undo незавершённого. COMMIT = запись на диск.

2. **Consistency**: БД гарантирует constraints (CHECK, FK, UNIQUE). Бизнес-инварианты — ответственность приложения.

3. **Isolation**: MVCC (PostgreSQL) — читатели не блокируют писателей. Уровни изоляции — компромисс между строгостью и производительностью.

4. **Durability**: `fsync` перед ответом клиенту. `synchronous_commit=off` — быстрее, но риск потери данных. НИКОГДА не отключайте `fsync`.

5. **BASE $\neq$ NOT ACID**: BASE — стратегия для распределённых систем. Современные NoSQL (MongoDB 4.0+) поддерживают ACID.

---

## Литература и источники

1. Haerder, T., & Reuter, A. (1983). Principles of Transaction-Oriented Database Recovery. *ACM Computing Surveys*, 15(4), 287-317.
2. Gray, J., & Reuter, A. (1992). *Transaction Processing: Concepts and Techniques*. Morgan Kaufmann.
3. PostgreSQL Documentation. Reliability and the Write-Ahead Log. https://www.postgresql.org/docs/current/wal.html
4. MySQL Documentation. InnoDB and the ACID Model. https://dev.mysql.com/doc/refman/8.0/en/mysql-acid.html
5. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly. Chapter 7: Transactions.
6. Wikipedia. ACID. https://en.wikipedia.org/wiki/ACID
7. Brewer, E. (2012). CAP Twelve Years Later: How the "Rules" Have Changed. *IEEE Computer*, 45(2).
8. Pritchett, D. (2008). BASE: An Acid Alternative. *ACM Queue*, 6(3).
9. Mohan, C. et al. (1992). ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks. *ACM TODS*, 17(1).
10. asyncpg Documentation. https://magicstack.github.io/asyncpg/current/
