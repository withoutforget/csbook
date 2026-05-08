# Уровни изоляции транзакций и их аномалии

## Введение

Полная изоляция транзакций (SERIALIZABLE) означает: каждая транзакция выполняется так, как будто она единственная в системе. Это идеально с точки зрения корректности, но катастрофически для производительности: мы получаем последовательное выполнение всех транзакций.

На практике системы предлагают несколько уровней изоляции — каждый допускает определённый класс аномалий в обмен на производительность. SQL стандарт определяет четыре уровня: READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE. Но реальные реализации (PostgreSQL, MySQL, Oracle) значительно отличаются от стандарта.

Понимание уровней изоляции и их аномалий критично для правильного проектирования транзакций. Неправильный выбор уровня — источник тонких, нечасто воспроизводимых, но разрушительных ошибок.

---

## 1. Аномалии параллельных транзакций

### 1.1 Dirty Read (грязное чтение)

Транзакция видит незафиксированные изменения другой транзакции:

```
T1:                               T2:
BEGIN;
UPDATE accounts SET balance=0     
WHERE id=1;
                                  BEGIN;
                                  SELECT balance FROM accounts WHERE id=1;
                                  -- Читает 0 (незафиксированное!)
                                  -- Решение: не давать кредит
                                  COMMIT;
ROLLBACK;
-- T1 откатывается, но T2 уже
-- приняла решение на основе грязных данных
```

### 1.2 Non-Repeatable Read (неповторяемое чтение)

В рамках одной транзакции два одинаковых чтения возвращают разный результат:

```
T1:                               T2:
BEGIN;
SELECT balance FROM accounts WHERE id=1;
-- 1000
                                  BEGIN;
                                  UPDATE accounts SET balance=500 WHERE id=1;
                                  COMMIT;
SELECT balance FROM accounts WHERE id=1;
-- 500 ← Другой результат!
COMMIT;
-- T1 видит несогласованное состояние
```

### 1.3 Phantom Read (фантомное чтение)

В рамках одной транзакции два одинаковых запроса возвращают разные НАБОРЫ строк:

```
T1:                               T2:
BEGIN;
SELECT COUNT(*) FROM orders 
WHERE user_id=1;
-- 5
                                  BEGIN;
                                  INSERT INTO orders (user_id) VALUES (1);
                                  COMMIT;
SELECT COUNT(*) FROM orders 
WHERE user_id=1;
-- 6 ← Фантомная строка появилась!
COMMIT;
```

### 1.4 Lost Update (потерянное обновление)

Два одновременных обновления, одно из которых теряется:

```
T1:                               T2:
BEGIN;                            BEGIN;
SELECT counter FROM stats;        SELECT counter FROM stats;
-- 10                             -- 10
counter = 10 + 1 = 11
                                  counter = 10 + 1 = 11
UPDATE stats SET counter=11;      UPDATE stats SET counter=11;
COMMIT;                           COMMIT;
-- Ожидаем 12, получаем 11 — одно обновление потеряно!
```

### 1.5 Write Skew (перекос записи)

Наиболее тонкая аномалия. Две транзакции читают перекрывающийся набор данных и вносят изменения, которые нарушают инвариант:

```
Инвариант: хотя бы один врач должен быть on-call в любой момент

Doctors on-call: Alice=true, Bob=true

T1 (Alice хочет уйти):          T2 (Bob хочет уйти):
BEGIN;                           BEGIN;
SELECT COUNT(*) FROM doctors     SELECT COUNT(*) FROM doctors
WHERE on_call=true;              WHERE on_call=true;
-- 2                             -- 2

-- Раз двое — безопасно уйти     -- Раз двое — безопасно уйти

UPDATE doctors SET on_call=false UPDATE doctors SET on_call=false
WHERE id='alice';                WHERE id='bob';
COMMIT;                          COMMIT;

-- Результат: НИКОГО на дежурстве! Инвариант нарушен!
-- При SERIALIZABLE этого бы не случилось
```

---

## 2. Уровни изоляции SQL Standard

| Уровень | Dirty Read | Non-Repeatable Read | Phantom Read |
|---------|-----------|---------------------|--------------|
| READ UNCOMMITTED | Возможен | Возможен | Возможен |
| READ COMMITTED | Нет | Возможен | Возможен |
| REPEATABLE READ | Нет | Нет | Возможен |
| SERIALIZABLE | Нет | Нет | Нет |

### 2.1 READ UNCOMMITTED

Самый слабый уровень. Видим незафиксированные данные. Практически не используется:

```sql
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
-- Или в PostgreSQL (нет реального dirty read, READ UNCOMMITTED = READ COMMITTED):
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
```

**Когда использовать**: практически никогда. Допустим для приблизительных агрегатов (если нам нужен примерный COUNT и не важна точность).

### 2.2 READ COMMITTED

Стандартный уровень для большинства СУБД (PostgreSQL, Oracle, SQL Server по умолчанию).

Каждый SELECT видит только зафиксированные данные на момент выполнения оператора:

```sql
-- PostgreSQL: default isolation level
SHOW transaction_isolation;
-- read committed

-- Пример:
BEGIN;  -- READ COMMITTED
SELECT balance FROM accounts WHERE id=1;  -- 1000

-- В этот момент другая транзакция COMMIT: balance=500

SELECT balance FROM accounts WHERE id=1;  -- 500 (Non-repeatable read!)
COMMIT;
```

**Когда использовать**: для большинства OLTP операций где non-repeatable read допустим.

### 2.3 REPEATABLE READ

Snapshot с момента первого READ в транзакции. Гарантирует repeatable reads, но допускает phantoms (по стандарту).

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM accounts WHERE id=1;  -- 1000 (snapshot зафиксирован)

-- Другая транзакция: UPDATE, COMMIT

SELECT balance FROM accounts WHERE id=1;  -- 1000 (тот же snapshot!)
COMMIT;
```

**PostgreSQL особенность**: REPEATABLE READ в PG также защищает от phantoms (благодаря MVCC). Но write skew всё ещё возможен.

**MySQL InnoDB**: REPEATABLE READ реализован через MVCC + gap locks (защита от phantoms через блокировки).

### 2.4 SERIALIZABLE

Наиболее строгий уровень. Транзакции выполняются так, как будто они последовательны.

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

-- PostgreSQL использует SSI (Serializable Snapshot Isolation)
-- Обнаруживает write skew и откатывает одну из транзакций

-- Пример с write skew:
SELECT COUNT(*) FROM doctors WHERE on_call=true;  -- 2
UPDATE doctors SET on_call=false WHERE id='alice';
COMMIT;
-- Параллельная транзакция (Bob) откатится с ошибкой:
-- ERROR: could not serialize access due to read/write dependencies among transactions
```

---

## 3. Реализации в PostgreSQL (MVCC)

PostgreSQL использует MVCC (Multi-Version Concurrency Control). Каждая строка имеет:
- `xmin`: transaction ID, создавший строку
- `xmax`: transaction ID, удаливший/обновивший строку (0 если активна)
- `ctid`: физическое расположение

```sql
-- Увидеть системные атрибуты:
SELECT xmin, xmax, ctid, * FROM employees WHERE id = 1;
-- xmin | xmax | ctid   | id | name
--  523 |    0 | (0,1)  |  1 | Alice
```

**Visibility check**: транзакция видит строку если:
- `xmin` завершён И видим для текущего snapshot
- `xmax` = 0 или ещё не завершён или не видим для snapshot

```
Snapshot транзакции T содержит:
- txid_snapshot: набор ID незавершённых транзакций на момент snapshot
- Строка видима если xmin < T.txid AND xmax не в snapshot
```

---

## 4. Write Skew и SSI

### 4.1 Detecting Write Skew

Write skew невозможно предотвратить на уровне REPEATABLE READ без дополнительных мер. Решения:

**SELECT FOR UPDATE**: явная блокировка читаемых строк:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

-- Блокируем строки перед проверкой
SELECT COUNT(*) FROM doctors 
WHERE on_call=true
FOR UPDATE;  -- Блокируем ВСЕ совпавшие строки!

-- Если COUNT(*) > 1 — безопасно обновить
UPDATE doctors SET on_call=false WHERE id='alice';
COMMIT;

-- Другая транзакция заблокируется на SELECT FOR UPDATE
-- Пока наша не завершится
```

**SERIALIZABLE**: PostgreSQL SSI (Serializable Snapshot Isolation) автоматически обнаруживает опасные циклы зависимостей:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
-- PostgreSQL отслеживает read-write зависимости
-- При обнаружении цикла откатывает транзакцию с:
-- ERROR 40001: could not serialize access due to read/write dependencies
```

Приложение должно повторить транзакцию:

```python
import asyncpg
from asyncpg.exceptions import SerializationFailureError

async def update_with_retry(pool, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                async with conn.transaction(isolation='serializable'):
                    # Ваши операции
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM doctors WHERE on_call=true FOR UPDATE"
                    )
                    if count > 1:
                        await conn.execute(
                            "UPDATE doctors SET on_call=false WHERE id='alice'"
                        )
            return True  # Успешно
            
        except SerializationFailureError:
            if attempt == max_retries - 1:
                raise
            # Exponential backoff
            await asyncio.sleep(0.1 * (2 ** attempt))
    
    return False
```

---

## 5. Практические примеры

### 5.1 Проверка текущего уровня изоляции

```sql
-- PostgreSQL
SHOW transaction_isolation;  -- Для сессии
SELECT current_setting('transaction_isolation');

-- Изменить уровень для сессии:
SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Изменить уровень для конкретной транзакции:
BEGIN ISOLATION LEVEL REPEATABLE READ;
-- ...
COMMIT;

-- MySQL
SELECT @@transaction_isolation;
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

### 5.2 Симуляция аномалий

```python
import psycopg2
import threading
import time

DSN = "postgresql://user:pass@localhost/test"

def simulate_lost_update():
    """Демонстрация потерянного обновления при READ COMMITTED."""
    
    results = {}
    
    def transaction_1():
        with psycopg2.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SELECT counter FROM test_counter WHERE id=1")
                val = cur.fetchone()[0]
                time.sleep(0.1)  # Пауза — T2 успевает выполниться
                cur.execute("UPDATE test_counter SET counter=%s WHERE id=1", (val + 1,))
                conn.commit()
                results['t1'] = val + 1
    
    def transaction_2():
        time.sleep(0.05)  # Немного после T1 начинает читать
        with psycopg2.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute("SELECT counter FROM test_counter WHERE id=1")
                val = cur.fetchone()[0]
                cur.execute("UPDATE test_counter SET counter=%s WHERE id=1", (val + 1,))
                conn.commit()
                results['t2'] = val + 1
    
    # Создаём начальное состояние
    with psycopg2.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO test_counter VALUES (1, 10) ON CONFLICT DO UPDATE SET counter=10")
            conn.commit()
    
    t1 = threading.Thread(target=transaction_1)
    t2 = threading.Thread(target=transaction_2)
    t1.start(); t2.start()
    t1.join(); t2.join()
    
    # Проверяем финальное значение
    with psycopg2.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT counter FROM test_counter WHERE id=1")
            final = cur.fetchone()[0]
    
    print(f"Expected: 12, Got: {final}")
    print(f"T1 result: {results.get('t1')}, T2 result: {results.get('t2')}")
    print(f"Lost update: {final != 12}")

# Решение: SELECT FOR UPDATE или atomic UPDATE
def atomic_increment():
    """Правильный способ — одна атомарная операция."""
    with psycopg2.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE test_counter SET counter = counter + 1 WHERE id=1")
            conn.commit()
```

---

## 6. Таблица аномалий vs уровни изоляции

```python
# Сводная таблица (стандарт SQL + реальность)

anomalies = {
    'Dirty Read': {
        'READ UNCOMMITTED': 'Possible',
        'READ COMMITTED': 'Not possible', 
        'REPEATABLE READ': 'Not possible',
        'SERIALIZABLE': 'Not possible',
    },
    'Non-Repeatable Read': {
        'READ UNCOMMITTED': 'Possible',
        'READ COMMITTED': 'Possible',
        'REPEATABLE READ': 'Not possible',
        'SERIALIZABLE': 'Not possible',
    },
    'Phantom Read': {
        'READ UNCOMMITTED': 'Possible',
        'READ COMMITTED': 'Possible',
        'REPEATABLE READ': 'Possible (standard) / Not in PG',
        'SERIALIZABLE': 'Not possible',
    },
    'Lost Update': {
        'READ UNCOMMITTED': 'Possible',
        'READ COMMITTED': 'Possible',
        'REPEATABLE READ': 'Not possible (with FOR UPDATE)',
        'SERIALIZABLE': 'Not possible',
    },
    'Write Skew': {
        'READ UNCOMMITTED': 'Possible',
        'READ COMMITTED': 'Possible',
        'REPEATABLE READ': 'Possible',
        'SERIALIZABLE': 'Not possible',
    },
}
```

---

## 7. Практические советы по выбору уровня

### 7.1 Когда READ COMMITTED (default)

- Большинство OLTP операций
- Операции, которые сами по себе атомарны (`UPDATE counter = counter + 1`)
- Когда non-repeatable read не важен

```sql
-- Это безопасно при READ COMMITTED
-- (атомарный UPDATE не требует транзакции)
UPDATE inventory 
SET quantity = quantity - 1 
WHERE id = 5 AND quantity > 0;

-- Проверяем affected rows
-- Если 0 — товара нет
```

### 7.2 Когда REPEATABLE READ

- Нужно несколько согласованных чтений в транзакции
- Отчёты и агрегаты (snapshot всей транзакции)
- Когда phantoms не важны

### 7.3 Когда SERIALIZABLE

- Write skew возможен (on-call пример выше)
- Финансовые операции с инвариантами на наборе строк
- Когда корректность важнее производительности

**Overhead SERIALIZABLE в PostgreSQL**: небольшой (5-10% при SSI). Намного меньше, чем при pessimistic locking.

---

## Заключение

Уровни изоляции — компромисс между корректностью и производительностью. Понимание аномалий помогает выбрать минимально необходимый уровень.

**Ключевые выводы**:

1. **Dirty Read** → READ COMMITTED. **Non-Repeatable Read** → REPEATABLE READ. **Phantom Read и Write Skew** → SERIALIZABLE.

2. **PostgreSQL** использует MVCC: READ COMMITTED = snapshot на момент оператора, REPEATABLE READ = snapshot на момент транзакции, SERIALIZABLE = SSI (автоматическое обнаружение конфликтов).

3. **Write Skew** — наиболее тонкая аномалия. SERIALIZABLE или SELECT FOR UPDATE.

4. **SELECT FOR UPDATE** блокирует строки для изменения — решение для lost update при READ COMMITTED.

5. При SERIALIZABLE ошибке сериализации (40001) — повторите транзакцию с exponential backoff.

---

## Литература и источники

1. ANSI/ISO SQL Standard. Transaction isolation levels. (SQL-92 and later)
2. Berenson, H. et al. (1995). A Critique of ANSI SQL Isolation Levels. *ACM SIGMOD*. https://dl.acm.org/doi/10.1145/568271.223785
3. Fekete, A. et al. (2005). Making Snapshot Isolation Serializable. *ACM TODS*, 30(2).
4. PostgreSQL Documentation. Transaction Isolation. https://www.postgresql.org/docs/current/transaction-iso.html
5. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly. Chapter 7.
6. MySQL Documentation. InnoDB and ACID Model. https://dev.mysql.com/doc/refman/8.0/en/innodb-transaction-isolation-levels.html
7. Cahill, M. J., Rőhm, U., & Fekete, A. D. (2008). Serializable Isolation for Snapshot Databases. *ACM SIGMOD*.
8. Wikipedia. Isolation (database systems). https://en.wikipedia.org/wiki/Isolation_(database_systems)
9. Adya, A. (1999). Weak Consistency: A Generalized Theory and Optimistic Implementations for Distributed Transactions. MIT PhD thesis.
10. Gray, J., & Reuter, A. (1992). *Transaction Processing: Concepts and Techniques*. Morgan Kaufmann.
