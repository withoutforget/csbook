# MVCC — как Postgres читает без блокировок

## Введение

Одна из самых мощных особенностей PostgreSQL — читатели никогда не блокируют писателей, а писатели никогда не блокируют читателей. Это означает: SELECT запрос никогда не ждёт UPDATE, и UPDATE никогда не ждёт SELECT. В системах с высокой нагрузкой это критически важно для производительности.

Это волшебство называется MVCC — Multi-Version Concurrency Control. Идея проста и элегантна: вместо того чтобы хранить одну версию строки и блокировать её при изменении, СУБД хранит несколько версий. Каждая транзакция видит «snapshot» — согласованную картину базы данных на определённый момент времени.

MVCC — не изобретение PostgreSQL. Oracle использует схожий подход через UNDO tablespace, MySQL InnoDB — через undo logs. Но PostgreSQL реализует MVCC особенно наглядно: системные поля `xmin`/`xmax` прямо в каждой строке.

---

## 1. Основная идея MVCC

### 1.1 Проблема с блокировками

Традиционный подход — блокировки:
```
Reader: Lock(row) → Read → Unlock
Writer: Lock(row) → Write → Unlock

Если Writer держит блокировку → Reader ждёт
Если Reader держит блокировку → Writer ждёт
```

Это создаёт контention — конкуренцию за блокировки. При высокой нагрузке OLTP-система деградирует.

### 1.2 MVCC: несколько версий

MVCC хранит несколько версий каждой строки:

```
Строка accounts, id=1:
Версия 1: xmin=100, xmax=200, balance=1000  (создана T100, устарела T200)
Версия 2: xmin=200, xmax=0,   balance=900   (текущая, создана T200)

T300 (snapshot txid_xmax=250):
→ Видит версию 2 (xmin=200 < 250, xmax=0 — не удалена)

T150 (snapshot txid_xmax=190):
→ Видит версию 1 (xmin=100 < 190, xmax=200 > 190 — ещё актуальна)
```

Читатели видят старые версии — не блокируются писателями. Писатели создают новые версии — не блокируются читателями.

---

## 2. Системные поля PostgreSQL

### 2.1 xmin и xmax

Каждая строка в PostgreSQL имеет скрытые системные поля:

```sql
-- Посмотреть системные поля
SELECT xmin, xmax, ctid, id, name 
FROM employees;
--  xmin | xmax | ctid  | id | name
--   523 |    0 | (0,1) |  1 | Alice
--   523 |    0 | (0,2) |  2 | Bob
--   524 |    0 | (0,3) |  3 | Carol
```

- **xmin**: transaction ID, создавший эту версию строки (INSERT или UPDATE)
- **xmax**: transaction ID, удаливший/обновивший эту версию (0 = строка актуальна)
- **ctid**: физическое местоположение (номер страницы, позиция в странице). Изменяется при UPDATE!

### 2.2 Как UPDATE работает в MVCC

```sql
-- ПЕРЕД UPDATE:
-- xmin=523, xmax=0, ctid=(0,1), name='Alice', salary=100000

UPDATE employees SET salary = 110000 WHERE id = 1;

-- ПОСЛЕ UPDATE (в транзакции с txid=600):
-- Старая версия: xmin=523, xmax=600, ctid=(0,1), name='Alice', salary=100000
-- Новая версия:  xmin=600, xmax=0,   ctid=(0,5), name='Alice', salary=110000
```

Старая версия не удаляется немедленно — она становится «мёртвой строкой» (dead tuple). Новая версия добавляется в конец страницы (heap).

```sql
-- Увидеть это в действии:
BEGIN;
SELECT xmin, xmax, ctid, salary FROM employees WHERE id=1;
-- 523 | 0 | (0,1) | 100000

UPDATE employees SET salary = 110000 WHERE id=1;

SELECT xmin, xmax, ctid, salary FROM employees WHERE id=1;
-- 600 | 0 | (0,5) | 110000  ← новая версия
-- Старая (0,1) всё ещё существует в heap!
COMMIT;
```

---

## 3. Visibility Check: какую версию видит транзакция

### 3.1 Snapshot транзакции

При начале транзакции PostgreSQL получает snapshot:

```
Snapshot = {
    xmin: минимальный active txid (все с меньшим ID завершены)
    xmax: следующий txid (ещё не использован)
    xip_list: список активных транзакций между xmin и xmax
}
```

Строка **видима** транзакции если:
- `xmin < snapshot.xmin` ИЛИ `xmin` NOT IN `xip_list` (создатель завершён)
- `xmax = 0` ИЛИ `xmax >= snapshot.xmax` ИЛИ `xmax` IN `xip_list` (удалитель не завершён)

```python
def is_visible(row, snapshot):
    """Упрощённая логика visibility check."""
    # Проверяем создателя строки (xmin)
    if row.xmin > snapshot.xmax:
        return False  # Создана после нашего snapshot
    if row.xmin in snapshot.xip_list:
        return False  # Создатель ещё работает
    
    # Проверяем удалителя (xmax)
    if row.xmax == 0:
        return True   # Строка не удалена
    if row.xmax > snapshot.xmax:
        return True   # Удалена после нашего snapshot
    if row.xmax in snapshot.xip_list:
        return True   # Удалитель ещё работает
    
    return False  # Строка удалена до snapshot
```

### 3.2 Визуализация snapshot isolation

```
Время:  T=1    T=2    T=3    T=4    T=5
TxID:   100    200    300    400    500

T300: BEGIN → snapshot = {xmin=100, xmax=400, xip=[200]}
                          (T200 ещё работает!)

Строки:
row1: xmin=100, xmax=0   → видима (100 < 400, xmax=0)
row2: xmin=200, xmax=0   → НЕ видима (200 in xip=[200])
row3: xmin=100, xmax=200 → видима? (xmax=200 in xip → удалитель работает → видима!)
row4: xmin=400, xmax=0   → НЕ видима (400 >= 400)
row5: xmin=100, xmax=350 → НЕ видима (350 завершён, < 400)
```

---

## 4. VACUUM и мёртвые строки

### 4.1 Проблема: накопление мёртвых строк

Каждый UPDATE создаёт мёртвую строку (dead tuple). Каждый DELETE создаёт мёртвую строку. Они занимают место на диске и в памяти — это **bloat** (раздувание):

```sql
-- Увидеть bloat:
SELECT 
    relname AS table,
    n_live_tup AS live_tuples,
    n_dead_tup AS dead_tuples,
    ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_pct
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

### 4.2 VACUUM — уборщик мёртвых строк

VACUUM — процесс, удаляющий мёртвые строки, которые больше не нужны никакому snapshot:

```sql
-- Ручной VACUUM
VACUUM employees;

-- VACUUM ANALYZE: убирает + обновляет статистику
VACUUM ANALYZE employees;

-- VACUUM FULL: перестраивает таблицу (блокирует на время!)
VACUUM FULL employees;

-- Просмотр прогресса VACUUM
SELECT pid, relid::regclass, phase, blocks_done, blocks_total
FROM pg_stat_progress_vacuum;
```

### 4.3 Autovacuum — автоматическая уборка

PostgreSQL запускает autovacuum автоматически при достижении порога мёртвых строк:

```sql
-- Настройки autovacuum (postgresql.conf):
-- autovacuum = on
-- autovacuum_vacuum_threshold = 50        -- min dead tuples
-- autovacuum_vacuum_scale_factor = 0.2    -- 20% от размера таблицы

-- Для горячих таблиц — снизить пороги:
ALTER TABLE hot_table SET (
    autovacuum_vacuum_scale_factor = 0.05,  -- Чаще vacuum
    autovacuum_analyze_scale_factor = 0.02
);

-- Просмотр когда последний autovacuum:
SELECT 
    relname,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'hot_table';
```

### 4.4 Transaction ID Wraparound — критическая проблема

Transaction IDs в PostgreSQL — 32-битные числа (около 4 миллиарда). При wraparound старые данные могут стать «будущими»:

```
Текущий txid: 2,147,483,648 (2^31)
Wraparound: ещё 2 млрд транзакций → txid снова с 0
Строки с xmin > 0 (старые) → внезапно кажутся "будущими"!
Результат: потеря данных или corrupted database
```

VACUUM freeze предотвращает wraparound, помечая старые строки как «всегда видимые»:

```sql
-- Просмотр опасности wraparound
SELECT 
    relname,
    age(relfrozenxid) AS xid_age,
    pg_size_pretty(pg_total_relation_size(oid)) AS size
FROM pg_class
WHERE relkind = 'r'
ORDER BY age(relfrozenxid) DESC
LIMIT 10;
-- Если age > 1.5 млрд — срочно VACUUM FREEZE!

-- Глобальная статистика:
SELECT 
    max(age(datfrozenxid)) AS max_xid_age,
    current_setting('autovacuum_freeze_max_age') AS freeze_limit
FROM pg_database;
```

---

## 5. HOT Updates (Heap Only Tuple)

MVCC создаёт новую версию строки в конце heap при UPDATE. Если индекс есть — нужно обновить и индекс. Это дорого.

**HOT** (Heap Only Tuple) — оптимизация: если обновляемые столбцы не индексированы И в старой странице есть место → новая версия помещается в ту же страницу. Индексы не обновляются, используется chain pointer:

```
Индекс:  key=1 → (page=0, slot=1)
                           ↓
Страница 0: [slot=1: xmin=523, xmax=600] → [slot=5: xmin=600, xmax=0]
                                              HOT chain!

Старый слот помечен как redirected to slot 5.
Индекс не нужно обновлять — он всё ещё указывает на slot=1,
СУБД автоматически следует по chain.
```

Условие HOT:
1. Все изменённые столбцы не входят ни в один индекс
2. В той же странице есть свободное место (`fillfactor`)

```sql
-- fillfactor: сколько % страницы заполнять при INSERT
-- Оставить место для HOT
ALTER TABLE hot_table SET (fillfactor = 70);  -- 30% для HOT updates
-- Перестройка: VACUUM FULL или pg_repack
```

---

## 6. MVCC в других СУБД

### 6.1 MySQL InnoDB

MySQL InnoDB также использует MVCC, но через UNDO tablespace:

```sql
-- В InnoDB строка хранит только одну версию
-- Старые версии хранятся в UNDO log
-- При чтении: "undo" последние изменения до нужного snapshot

-- Просмотр UNDO tablespace:
SELECT * FROM information_schema.INNODB_TABLESPACES 
WHERE SPACE_TYPE = 'Undo';

-- Мониторинг UNDO lag:
SHOW ENGINE INNODB STATUS;
-- Ищем: "History list length" — количество незачищенных UNDO записей
```

Отличие от PostgreSQL: строка не хранит историю (экономия heap), но UNDO tablespace нужно чистить (purge thread).

### 6.2 Oracle

Oracle также использует UNDO tablespace, но с настраиваемым UNDO retention:

```sql
-- Oracle: настройка времени хранения UNDO
ALTER SYSTEM SET UNDO_RETENTION = 900;  -- 900 секунд

-- ORA-01555: Snapshot too old — UNDO уже удалён, нельзя построить snapshot
-- Решение: увеличить UNDO tablespace или UNDO_RETENTION
```

### 6.3 MongoDB (WiredTiger)

MongoDB с WiredTiger engine использует MVCC для snapshot isolation:

```javascript
// MongoDB: сессия с causalConsistency
const session = client.startSession({ causalConsistency: true });
const collection = db.collection('orders');

// Транзакция
session.startTransaction({
    readConcern: { level: 'snapshot' },  // MVCC snapshot
    writeConcern: { w: 'majority' }
});

try {
    const order = await collection.findOne({ _id: orderId }, { session });
    await collection.updateOne(
        { _id: orderId },
        { $set: { status: 'processed' } },
        { session }
    );
    await session.commitTransaction();
} catch (e) {
    await session.abortTransaction();
}
```

---

## 7. Мониторинг MVCC в PostgreSQL

```sql
-- Размер таблицы vs реальный размер (bloat)
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT * FROM pgstattuple('employees');
-- table_len: общий размер
-- dead_tuple_percent: % мёртвых строк

-- Оценка bloat без pgstattuple (только чтение каталога):
SELECT
    current_database(), schemaname, tablename,
    (n_dead_tup::float / NULLIF(n_live_tup, 0)) * 100 AS dead_ratio
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY dead_ratio DESC;

-- VACUUM работает прямо сейчас:
SELECT pid, relid::regclass, phase, heap_blks_scanned, heap_blks_vacuumed
FROM pg_stat_progress_vacuum;

-- Transaction ID age (опасность wraparound):
SELECT 
    datname,
    age(datfrozenxid) AS xid_age,
    ROUND(100.0 * age(datfrozenxid) / 2000000000, 2) AS pct_towards_wraparound
FROM pg_database
ORDER BY xid_age DESC;
```

---

## Заключение

MVCC — элегантное решение проблемы конкурентного доступа. Вместо блокировок — версии. Вместо ожидания — snapshot.

**Ключевые выводы**:

1. **MVCC**: у каждой строки — `xmin` (кто создал) и `xmax` (кто удалил). Читатели видят snapshot, не блокируя писателей.

2. **UPDATE** = логическое удаление старой версии (`xmax = txid`) + INSERT новой версии. Старая версия — dead tuple.

3. **VACUUM** убирает dead tuples. **Autovacuum** делает это автоматически. Мониторьте `n_dead_tup` и `age(relfrozenxid)`.

4. **HOT** оптимизация: UPDATE без изменения индексируемых столбцов → нет overhead на обновление индекса.

5. **Transaction ID Wraparound**: 32-битный счётчик. `VACUUM FREEZE` предотвращает катастрофу. Следите за `age(datfrozenxid)`.

---

## Литература и источники

1. PostgreSQL Documentation. Concurrency Control. https://www.postgresql.org/docs/current/mvcc.html
2. PostgreSQL Documentation. Routine Vacuuming. https://www.postgresql.org/docs/current/routine-vacuuming.html
3. Momjian, B. MVCC Unmasked. https://momjian.us/main/writings/pgsql/mvcc.pdf
4. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly. Chapter 7.
5. Weiss, C. (2020). PostgreSQL 14 Internals. https://postgrespro.com/community/books/internals
6. Wikipedia. Multiversion concurrency control. https://en.wikipedia.org/wiki/Multiversion_concurrency_control
7. Ports, D. R. K., & Grittner, K. (2012). Serializable Snapshot Isolation in PostgreSQL. *VLDB Endowment*.
8. Bernstein, P. A., & Goodman, N. (1983). Multiversion Concurrency Control - Theory and Algorithms. *ACM TODS*.
9. pgstattuple. https://www.postgresql.org/docs/current/pgstattuple.html
10. pg_repack. https://github.com/reorg/pg_repack
