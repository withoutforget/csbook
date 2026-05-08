# EXPLAIN и планы запросов

## Введение

Медленный запрос — одна из самых частых производственных проблем. Таблица растёт, запрос который работал за 10 мс начинает занимать 10 секунд. Как найти причину? Инструмент номер один — `EXPLAIN ANALYZE`.

`EXPLAIN` показывает план выполнения запроса — иерархию операций, которые PostgreSQL планирует выполнить. `EXPLAIN ANALYZE` дополнительно фактически выполняет запрос и показывает реальное время и количество строк. Разница между `rows=1000` (ожидание планировщика) и `rows=1000000` (реальность) указывает на устаревшую статистику.

Понимание плана запросов — необходимый навык для каждого разработчика, работающего с базами данных. В этой главе мы разберём все ключевые узлы планов, научимся их читать и оптимизировать.

---

## 1. Базы: EXPLAIN и EXPLAIN ANALYZE

```sql
-- EXPLAIN: показывает план без выполнения
EXPLAIN SELECT * FROM employees WHERE department_id = 1;

-- EXPLAIN ANALYZE: выполняет запрос и показывает реальные метрики
EXPLAIN ANALYZE SELECT * FROM employees WHERE department_id = 1;

-- EXPLAIN с форматированием:
EXPLAIN (
    FORMAT TEXT,      -- TEXT (default), JSON, XML, YAML
    ANALYZE true,     -- Выполнить и измерить
    VERBOSE true,     -- Показать output columns
    COSTS true,       -- Показать cost estimates
    BUFFERS true,     -- Показать статистику buffer hits
    TIMING true,      -- Показать время (overhead ~10%)
    SUMMARY true      -- Показать Planning/Execution time
) 
SELECT e.name, d.name 
FROM employees e 
JOIN departments d ON e.department_id = d.id;
```

### 1.1 Чтение плана

```
Seq Scan on employees  (cost=0.00..1.08 rows=8 width=548) 
                       (actual time=0.012..0.019 rows=8 loops=1)
  Filter: (department_id = 1)
  Rows Removed by Filter: 0
Planning Time: 0.123 ms
Execution Time: 0.038 ms
```

**Структура строки**:
- `Seq Scan on employees` — тип операции и объект
- `cost=0.00..1.08` — расчётная стоимость: начальная..полная
- `rows=8` — ожидаемое количество строк
- `width=548` — средняя ширина строки в байтах
- `actual time=0.012..0.019` — реальное время: до первой строки..до последней (в мс)
- `rows=8` — реальное количество строк
- `loops=1` — сколько раз выполнялся узел (для nested loops > 1)

**Cost единицы**: не секунды, а условные единицы (sequential page read = 1.0 по умолчанию). Используются для сравнения планов между собой.

---

## 2. Методы доступа к данным

### 2.1 Sequential Scan

```
Seq Scan on big_table  (cost=0.00..25432.00 rows=1000000 width=100)
```

Читает всю таблицу, строку за строкой. Хорошо когда:
- Таблица маленькая
- Нужна большая часть строк (низкая selectivity)
- Нет подходящего индекса

### 2.2 Index Scan

```
Index Scan using idx_employees_dept on employees
   (cost=0.28..12.31 rows=4 width=548) (actual time=0.045..0.057 rows=4 loops=1)
  Index Cond: (department_id = 1)
```

Использует B-tree для нахождения строк, затем читает heap для каждой строки. Хорошо для:
- Высокая selectivity (мало строк)
- Сортировка совпадает с индексом (ORDER BY)

### 2.3 Index Only Scan

```
Index Only Scan using idx_covering on employees
   (cost=0.28..8.30 rows=4 width=100) (actual time=0.021..0.028 rows=4 loops=1)
  Index Cond: (department_id = 1)
  Heap Fetches: 0
```

Все нужные данные в индексе — heap не читается. `Heap Fetches: 0` = всё из индекса. Требует covering index.

### 2.4 Bitmap Index Scan + Bitmap Heap Scan

```
Bitmap Heap Scan on events  (cost=234.12..5678.90 rows=10000 width=100)
  Recheck Cond: (user_id = ANY ('{1,2,3}'::integer[]))
  ->  Bitmap Index Scan on idx_events_user_id
        (cost=0.00..231.62 rows=10000 width=0)
        Index Cond: (user_id = ANY ('{1,2,3}'::integer[]))
```

Двухфазный процесс:
1. **Bitmap Index Scan**: строим bitmap страниц (какие страницы heap содержат нужные строки)
2. **Bitmap Heap Scan**: читаем только нужные страницы в порядке физического расположения

Эффективен для средней selectivity (сотни/тысячи строк). Минимизирует random I/O.

---

## 3. Методы соединения (Join Algorithms)

### 3.1 Nested Loop Join

```
Nested Loop  (cost=0.28..45.67 rows=10 width=200)
  ->  Seq Scan on departments d  (cost=0.00..1.03 rows=3 width=50)
  ->  Index Scan using idx_employees_dept on employees e
        (cost=0.28..14.16 rows=4 width=150)
        Index Cond: (e.department_id = d.id)
```

Алгоритм:
```python
for row_outer in outer_table:      # departments
    for row_inner in inner_table:  # employees
        if join_condition(row_outer, row_inner):
            yield row_outer + row_inner
```

**Сложность**: O(N × M) в худшем случае. Но если inner имеет индекс → O(N × log M).

**Когда хорошо**:
- Outer table маленькая
- Inner имеет индекс по условию join
- Высокая selectivity

### 3.2 Hash Join

```
Hash Join  (cost=2.08..56.89 rows=100 width=200)
  Hash Cond: (e.department_id = d.id)
  ->  Seq Scan on employees e  (cost=0.00..1.08 rows=8 width=150)
  ->  Hash  (cost=1.03..1.03 rows=3 width=50)
        ->  Seq Scan on departments d  (cost=0.00..1.03 rows=3 width=50)
```

Алгоритм:
1. Build: читаем inner table, строим хэш-таблицу в памяти (по ключу join)
2. Probe: для каждой строки outer table ищем в хэш-таблице

**Сложность**: O(N + M) — линейная

**Когда хорошо**:
- Нет подходящего индекса
- Обе таблицы умеренного размера
- Equality join (hash работает только с =)

**Проблема**: если хэш-таблица не помещается в `work_mem` → spill to disk (медленно).

### 3.3 Merge Join

```
Merge Join  (cost=123.45..456.78 rows=1000 width=200)
  Merge Cond: (e.department_id = d.id)
  ->  Sort  (cost=56.89..58.89 rows=800 width=150)
        Sort Key: e.department_id
        ->  Seq Scan on employees e
  ->  Sort  (cost=3.45..3.70 rows=100 width=50)
        Sort Key: d.id
        ->  Seq Scan on departments d
```

Алгоритм:
1. Отсортировать обе таблицы по ключу join
2. Пройти синхронно по обеим

**Сложность**: O(N log N + M log M) — с сортировкой. O(N + M) — если уже отсортированы.

**Когда хорошо**:
- Обе таблицы уже отсортированы (индексы по join ключам)
- Equality join (как Hash Join)
- Большие таблицы без нужного индекса

---

## 4. Другие важные узлы

### 4.1 Sort

```
Sort  (cost=1234.56..1289.12 rows=21824 width=100)
  Sort Key: created_at DESC
  ->  Seq Scan on events
```

Сортировка в памяти (`work_mem`) или на диске (quicksort → external merge sort):

```bash
# Увеличить work_mem для уменьшения disk sort:
SET work_mem = '256MB';  -- Для текущей сессии

# В postgresql.conf для всех:
# work_mem = 64MB  (осторожно: N соединений × N sort операций)

# Проверить disk sort:
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM events ORDER BY created_at;
# Sort Method: external merge  Disk: 12345kB  ← spill to disk!
# Sort Method: quicksort  Memory: 1024kB      ← в памяти
```

### 4.2 Aggregate

```
Aggregate  (cost=45.67..45.68 rows=1 width=8)
  ->  Seq Scan on employees

HashAggregate  (cost=1234.56..1289.12 rows=10 width=16)
  Group Key: department_id
  ->  Seq Scan on employees

GroupAggregate  (cost=123.45..456.78 rows=10 width=16)
  Group Key: department_id
  ->  Sort
        Sort Key: department_id
        ->  Seq Scan on employees
```

- **Aggregate**: простые агрегаты без GROUP BY (COUNT(*), SUM())
- **HashAggregate**: GROUP BY с использованием хэш-таблицы в памяти
- **GroupAggregate**: GROUP BY после сортировки по ключу

### 4.3 Materialize

```
Materialize  (cost=0.00..1234.56 rows=100000 width=50)
  ->  Seq Scan on large_table
```

Материализует результат в памяти для повторного использования (например, в Nested Loop с несколькими обращениями к одному источнику).

---

## 5. Статистика и планировщик

### 5.1 Как планировщик принимает решения

PostgreSQL использует cost-based optimizer. Для оценки стоимости нужна статистика о данных:

```sql
-- Статистика в pg_statistics
SELECT 
    attname,
    n_distinct,    -- Уникальных значений (-X = доля от n)
    correlation,   -- Физический порядок vs логический (-1..1)
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE tablename = 'employees';
```

### 5.2 ANALYZE — обновление статистики

```sql
-- Обновить статистику для таблицы
ANALYZE employees;

-- Обновить статистику для столбца
ANALYZE employees(department_id);

-- Более детальная статистика для столбца:
ALTER TABLE employees ALTER COLUMN department_id SET STATISTICS 500;
-- По умолчанию: 100. Чем больше — точнее, но дольше ANALYZE
```

### 5.3 Расхождение rows в плане

Если `rows=100` а `actual rows=100000` — статистика устарела:

```sql
-- Плохой план из-за устаревшей статистики:
EXPLAIN ANALYZE SELECT * FROM events WHERE user_id = 1;
-- rows=10 (estimate)  actual rows=1000000  ← Estimate в 100,000 раз меньше!
-- Планировщик выбрал Index Scan вместо Seq Scan → катастрофически медленно

-- Решение:
ANALYZE events;  -- Обновить статистику
-- Теперь: rows=1000000 (estimate)  actual rows=1000000  ← Точно!
-- Планировщик выберет Seq Scan → быстро
```

---

## 6. Инструменты анализа медленных запросов

### 6.1 pg_stat_statements

Расширение для накопления статистики запросов:

```sql
-- Включить:
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- postgresql.conf:
-- shared_preload_libraries = 'pg_stat_statements'
-- pg_stat_statements.max = 10000
-- pg_stat_statements.track = all

-- Самые медленные запросы (по общему времени):
SELECT 
    query,
    calls,
    ROUND((total_exec_time / 1000)::numeric, 2) AS total_sec,
    ROUND((mean_exec_time)::numeric, 2) AS mean_ms,
    ROUND(stddev_exec_time::numeric, 2) AS stddev_ms,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- Самые медленные по среднему времени:
SELECT 
    SUBSTRING(query, 1, 80) AS query_short,
    calls,
    ROUND(mean_exec_time::numeric, 3) AS mean_ms
FROM pg_stat_statements
WHERE calls > 100
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### 6.2 auto_explain

Автоматически логировать планы медленных запросов:

```sql
-- Включить для сессии:
LOAD 'auto_explain';
SET auto_explain.log_min_duration = '1s';  -- Логировать запросы > 1 сек
SET auto_explain.log_analyze = true;

-- Или в postgresql.conf для всего сервера:
-- shared_preload_libraries = 'auto_explain'
-- auto_explain.log_min_duration = '1000'  -- 1000мс
-- auto_explain.log_analyze = true
-- auto_explain.log_buffers = true
```

### 6.3 pgBadger — анализ логов

```bash
# Настройка логирования в postgresql.conf:
# log_min_duration_statement = 1000  # Логировать запросы > 1с
# log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '

# Анализ логов:
pgbadger /var/log/postgresql/postgresql-2024-01-01.log -o report.html

# Откроем в браузере: report.html
# Показывает: топ медленных запросов, частоту, timing distribution
```

---

## 7. Практика: оптимизация реального запроса

```sql
-- Медленный запрос:
SELECT 
    u.name,
    COUNT(o.id) AS order_count,
    SUM(oi.quantity * oi.price) AS total_spent
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
LEFT JOIN order_items oi ON oi.order_id = o.id
WHERE u.country = 'RU'
  AND o.created_at >= '2024-01-01'
GROUP BY u.id, u.name
ORDER BY total_spent DESC
LIMIT 10;

-- Шаг 1: EXPLAIN ANALYZE
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) 
-- ... тот же запрос

-- Вывод (упрощённо):
-- Hash Join  (actual time=12345.678..12345.789 rows=10 loops=1)
--   ->  Hash Join  (actual time=...)
--         ->  Seq Scan on users  ← 10M строк, фильтр country='RU'
--               Filter: (country = 'RU')
--               Rows Removed by Filter: 9900000
--   ->  Seq Scan on orders  ← нет фильтрации по индексу на created_at!

-- Проблемы:
-- 1. Нет индекса на users.country
-- 2. Нет индекса на orders.created_at
-- 3. Hash Join с большими таблицами → много памяти

-- Решение:
CREATE INDEX idx_users_country ON users(country) 
WHERE country IS NOT NULL;

CREATE INDEX idx_orders_created_user 
ON orders(created_at, user_id) 
WHERE created_at >= '2024-01-01';
-- Partial index — только для 2024!

ANALYZE users;
ANALYZE orders;

-- Повторный EXPLAIN:
-- Index Scan using idx_users_country  (actual rows=100000 ← было 10M)
-- Index Scan using idx_orders_created_user  (actual rows=50000 ← было 100M)
-- Execution Time: 45.678 ms  ← было 12345 ms!
```

---

## 8. Советы по интерпретации EXPLAIN

```python
# Красные флаги в EXPLAIN ANALYZE:
flags = {
    'Seq Scan на большой таблице': 
        'Нет индекса или планировщик считает seq scan быстрее → проверь статистику',
    
    'rows estimate << actual rows':
        'Устаревшая статистика → ANALYZE',
    
    'Sort Method: external merge':
        'Сортировка на диске → увеличь work_mem',
    
    'Hash Batches > 1':
        'Hash таблица не поместилась в памяти → увеличь work_mem',
    
    'Heap Fetches >> 0 для Index Only Scan':
        'Таблица не достаточно vacuum-ирована (visibility map не обновлена)',
    
    'loops >> 1 в Inner узле':
        'Nested loop с повторными полными scan → нужен индекс',
    
    'cost >> actual time': 
        'Цена завышена → возможно устаревшая статистика или planner bug',
}
```

---

## Заключение

`EXPLAIN ANALYZE` — ваш главный инструмент отладки производительности запросов.

**Ключевые выводы**:

1. **Seq Scan**: читает всё. Нормально для маленьких таблиц или низкой selectivity.

2. **Index Scan**: B-tree + heap fetch. Для высокой selectivity.

3. **Bitmap Heap Scan**: промежуточный вариант для средней selectivity.

4. **Index Only Scan**: нет обращений к heap. Требует covering index + актуальный visibility map.

5. **Nested Loop**: лучший при маленьком outer + индекс на inner. **Hash Join**: для средних таблиц без индекса. **Merge Join**: когда данные уже отсортированы.

6. **Расхождение rows**: устаревшая статистика → `ANALYZE`. Регулярно запускайте autovacuum + autoanalyze.

7. **pg_stat_statements**: накапливает статистику запросов. Используйте для поиска медленных запросов.

---

## Литература и источники

1. PostgreSQL Documentation. Using EXPLAIN. https://www.postgresql.org/docs/current/using-explain.html
2. PostgreSQL Documentation. Planner/Optimizer. https://www.postgresql.org/docs/current/planner-optimizer.html
3. Winand, M. (2012). *SQL Performance Explained*. https://use-the-index-luke.com/
4. PostgreSQL Documentation. Statistics Used by the Planner. https://www.postgresql.org/docs/current/planner-stats.html
5. Explain Depesz. https://explain.depesz.com/ (онлайн визуализатор планов)
6. PEV2 (Plan Explorer Visualizer). https://explain.dalibo.com/
7. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly.
8. Momjian, B. PostgreSQL Performance. https://momjian.us/main/presentations/performance.html
9. pgBadger Documentation. https://pgbadger.darold.net/
10. auto_explain Documentation. https://www.postgresql.org/docs/current/auto-explain.html
