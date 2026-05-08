# Индексы: B-tree, hash, GIN, GiST

## Введение

Без индекса база данных при поиске строки вынуждена прочитать каждую строку таблицы (sequential scan). Для таблицы с 100 миллионами строк это означает сканирование нескольких гигабайт данных для одного SELECT. Индекс — это отдельная структура данных, позволяющая быстро найти нужные строки по значению определённых столбцов.

Индекс — не бесплатная оптимизация. Каждый INSERT, UPDATE, DELETE должен обновлять все индексы таблицы. Слишком много индексов замедляют запись и потребляют память. Правильный выбор индексов — один из важнейших навыков для работы с базами данных.

PostgreSQL предоставляет несколько типов индексов, каждый оптимизирован для своего паттерна использования: B-tree для общего случая, Hash для точного равенства, GIN для массивов и полнотекстового поиска, GiST для геоданных и диапазонов.

---

## 1. Зачем нужны индексы: Sequential Scan vs Index Scan

```sql
-- Таблица без индекса
CREATE TABLE events (
    id        BIGSERIAL PRIMARY KEY,
    user_id   INTEGER NOT NULL,
    event_type VARCHAR(50),
    created_at TIMESTAMP,
    metadata  JSONB
);

-- Вставим 10 миллионов строк
INSERT INTO events (user_id, event_type, created_at)
SELECT 
    (random() * 1000000)::int,
    CASE (random() * 3)::int WHEN 0 THEN 'click' WHEN 1 THEN 'view' ELSE 'purchase' END,
    NOW() - (random() * INTERVAL '365 days')
FROM generate_series(1, 10000000);

-- Запрос без индекса:
EXPLAIN ANALYZE SELECT * FROM events WHERE user_id = 42;
-- Seq Scan on events (cost=0.00..254032.72 rows=10 width=100)
--                     (actual time=1234.567..1234.589 rows=10 loops=1)
-- Rows Removed by Filter: 9999990

-- С индексом:
CREATE INDEX idx_events_user_id ON events(user_id);

EXPLAIN ANALYZE SELECT * FROM events WHERE user_id = 42;
-- Index Scan using idx_events_user_id on events
--   (cost=0.56..35.89 rows=10 width=100) (actual time=0.045..0.057 rows=10 loops=1)
-- В 20,000 раз быстрее!
```

---

## 2. B-tree Index — основной тип

### 2.1 Структура B-tree

B-tree (Balanced tree) — самый распространённый тип индекса. В PostgreSQL используется B+-tree:

```
                [50 | 100 | 150]          ← Внутренний узел
               /    |     |    \
          [20,35] [60,80] [110,130] [160,200]  ← Листовые узлы
          (ptr)   (ptr)   (ptr)    (ptr)       с указателями на heap
```

Свойства:
- Сбалансированное дерево: все пути от корня до листа одинаковы
- Каждый узел = одна страница (8KB по умолчанию)
- Глубина: для 100 млн строк $\approx$ 4-5 уровней
- Поиск O(log N), диапазонный поиск O(log N + K)

### 2.2 Когда B-tree используется

```sql
-- Равенство
WHERE user_id = 42

-- Диапазон
WHERE created_at BETWEEN '2024-01-01' AND '2024-12-31'
WHERE salary > 100000
WHERE salary >= 50000 AND salary <= 150000

-- LIKE с префиксом (можно использовать B-tree)
WHERE name LIKE 'Alice%'  -- Да, B-tree помогает
WHERE name LIKE '%Alice'  -- Нет, B-tree не помогает

-- ORDER BY (если совпадает с порядком индекса)
ORDER BY created_at DESC  -- Index scan с reverse traversal

-- IS NULL / IS NOT NULL
WHERE deleted_at IS NULL  -- Если partial index не нужен
```

### 2.3 Selectivity — важный фактор

Оптимизатор использует индекс только если selectivity достаточная:

```sql
-- Высокая selectivity: user_id = 42 из 10 млн строк → 10 строк (0.0001%)
-- → Используем индекс

-- Низкая selectivity: status IN ('active', 'inactive') → 90% строк
-- → Sequential scan быстрее!

-- Статистика selectivity:
SELECT 
    attname,
    n_distinct,
    correlation
FROM pg_stats
WHERE tablename = 'events' AND attname = 'user_id';
```

### 2.4 Covering Index и Index-Only Scan

```sql
-- Covering index: включает все необходимые столбцы
-- Позволяет Index-Only Scan (нет обращений к heap!)

CREATE INDEX idx_events_user_covering 
ON events(user_id, created_at, event_type);

-- Index-only scan (нет доступа к heap):
EXPLAIN ANALYZE
SELECT user_id, created_at, event_type 
FROM events 
WHERE user_id = 42;
-- Index Only Scan using idx_events_user_covering

-- INCLUDE: добавить столбцы в индекс без изменения порядка сортировки
CREATE INDEX idx_events_user_id_inc 
ON events(user_id) INCLUDE (created_at, event_type);
-- user_id — для поиска, created_at/event_type — для покрытия
```

### 2.5 Составной индекс и порядок столбцов

```sql
-- Составной индекс (user_id, event_type):
CREATE INDEX idx_events_composite ON events(user_id, event_type);

-- Использует полностью:
WHERE user_id = 42 AND event_type = 'purchase'

-- Использует только первый столбец (leading column):
WHERE user_id = 42
-- PostgreSQL может использовать этот индекс для поиска по user_id

-- НЕ использует:
WHERE event_type = 'purchase'  -- Нет leading column!
-- Нужен отдельный индекс на event_type

-- Правило: наиболее селективный столбец первым,
-- если не нужен range scan по первому
```

---

## 3. Hash Index

```sql
-- Hash index: только для равенства, O(1)
CREATE INDEX idx_events_user_hash ON events USING hash(user_id);

-- Использует:
WHERE user_id = 42  -- O(1) lookup

-- НЕ использует:
WHERE user_id > 42  -- Hash не поддерживает range
ORDER BY user_id    -- Hash не поддерживает сортировку
```

**Когда Hash лучше B-tree**:
- Строго только операции равенства
- Очень большой ключ (хэш компактнее B-tree с большими ключами)
- Хороший хэш с хорошей distribucей

На практике B-tree часто используют даже для равенства — он поддерживает и range queries, а разница в производительности небольшая.

---

## 4. GIN — для массивов и JSONB

GIN (Generalized Inverted Index) — инвертированный индекс. Каждый элемент массива/документа → список строк, содержащих этот элемент.

### 4.1 GIN для массивов

```sql
CREATE TABLE articles (
    id   SERIAL PRIMARY KEY,
    tags TEXT[] NOT NULL
);

INSERT INTO articles (tags) VALUES
    ('{postgresql,database,performance}'),
    ('{postgresql,indexing}'),
    ('{mysql,database}'),
    ('{redis,caching,performance}');

-- GIN индекс на массив
CREATE INDEX idx_articles_tags ON articles USING gin(tags);

-- Запросы с GIN:
-- @> : contains (массив содержит все элементы)
SELECT * FROM articles WHERE tags @> ARRAY['postgresql'];
SELECT * FROM articles WHERE tags @> ARRAY['postgresql', 'database'];

-- && : overlap (есть хотя бы один общий элемент)
SELECT * FROM articles WHERE tags && ARRAY['performance', 'caching'];

-- Без GIN — Seq Scan
-- С GIN — Bitmap Index Scan (очень быстро)
```

### 4.2 GIN для JSONB

```sql
-- Поиск по содержимому JSONB
CREATE TABLE products (
    id       SERIAL PRIMARY KEY,
    data     JSONB NOT NULL
);

INSERT INTO products (data) VALUES
    ('{"name": "Widget", "price": 9.99, "tags": ["sale", "featured"]}'),
    ('{"name": "Gadget", "price": 29.99, "tags": ["new"]}');

-- GIN на весь JSONB документ
CREATE INDEX idx_products_data ON products USING gin(data);

-- Поиск по ключу
SELECT * FROM products WHERE data ? 'price';       -- Есть ключ 'price'?
SELECT * FROM products WHERE data @> '{"price": 9.99}';  -- Contains

-- GIN для jsonb_path_ops (только @> оператор, меньший размер)
CREATE INDEX idx_products_data_ops ON products USING gin(data jsonb_path_ops);

-- Специфические выражения в GIN:
CREATE INDEX idx_products_name ON products USING gin((data->'name'));
```

### 4.3 GIN для Full-Text Search

```sql
-- Полнотекстовый поиск
CREATE TABLE documents (
    id      SERIAL PRIMARY KEY,
    content TEXT,
    tsv     TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, ''))
    ) STORED
);

CREATE INDEX idx_documents_fts ON documents USING gin(tsv);

INSERT INTO documents (content) VALUES
    ('PostgreSQL is a powerful open source object-relational database system'),
    ('MySQL is another popular relational database management system'),
    ('Redis is an in-memory data structure store used as a database, cache');

-- Full-text поиск
SELECT * FROM documents 
WHERE tsv @@ to_tsquery('english', 'database & open');

-- Ранжирование
SELECT content, ts_rank(tsv, query) AS rank
FROM documents, to_tsquery('english', 'database') AS query
WHERE tsv @@ query
ORDER BY rank DESC;
```

---

## 5. GiST — для геоданных и диапазонов

GiST (Generalized Search Tree) — расширяемая структура для сложных типов данных.

### 5.1 GiST для геоданных (PostGIS)

```sql
-- Требует: CREATE EXTENSION postgis;

CREATE TABLE locations (
    id    SERIAL PRIMARY KEY,
    name  TEXT,
    point GEOMETRY(POINT, 4326)  -- WGS84 координаты
);

INSERT INTO locations (name, point) VALUES
    ('Moscow', ST_SetSRID(ST_MakePoint(37.6, 55.75), 4326)),
    ('Berlin', ST_SetSRID(ST_MakePoint(13.4, 52.52), 4326));

-- GiST индекс для пространственных запросов
CREATE INDEX idx_locations_geom ON locations USING gist(point);

-- Найти объекты в радиусе 100 км от точки
SELECT name, ST_Distance(point::geography, 'POINT(37.6 55.75)'::geography) / 1000 AS km
FROM locations
WHERE ST_DWithin(point::geography, 'POINT(37.6 55.75)'::geography, 100000)
ORDER BY km;
```

### 5.2 GiST для диапазонов

```sql
-- Диапазоны дат/чисел
CREATE TABLE reservations (
    id       SERIAL PRIMARY KEY,
    room     INTEGER,
    period   DATERANGE
);

INSERT INTO reservations (room, period) VALUES
    (101, '[2024-01-10, 2024-01-15)'),
    (101, '[2024-02-01, 2024-02-05)'),
    (102, '[2024-01-10, 2024-01-20)');

-- GiST для диапазонов
CREATE INDEX idx_reservations_period ON reservations USING gist(period);

-- Найти пересечения
SELECT * FROM reservations
WHERE period && '[2024-01-12, 2024-01-14]'::daterange;

-- Найти свободные номера
SELECT room FROM reservations
WHERE room = 101 
  AND period && '[2024-01-08, 2024-01-12]'::daterange;
-- Если есть строки — комната занята
```

---

## 6. Partial Index

Частичный индекс: индексирует только подмножество строк. Меньше размер, быстрее обновление:

```sql
-- Индекс только на 'active' записи
CREATE INDEX idx_users_email_active 
ON users(email) 
WHERE status = 'active';

-- Использует только для: WHERE email = '...' AND status = 'active'

-- Очень эффективно для "hot" данных (недавние строки):
CREATE INDEX idx_events_recent 
ON events(user_id, created_at) 
WHERE created_at > NOW() - INTERVAL '30 days';

-- Индекс только для ненулевых значений:
CREATE INDEX idx_employees_manager 
ON employees(manager_id) 
WHERE manager_id IS NOT NULL;
-- Экономит место: NULL значения не индексируются
```

---

## 7. Expression Index

Индекс по выражению — индексирует результат функции/выражения:

```sql
-- Поиск без учёта регистра
CREATE INDEX idx_users_email_lower ON users(lower(email));

-- Теперь этот запрос использует индекс:
SELECT * FROM users WHERE lower(email) = 'alice@example.com';

-- Индекс по дате (без времени):
CREATE INDEX idx_events_date ON events(DATE(created_at));
SELECT * FROM events WHERE DATE(created_at) = '2024-01-15';

-- Индекс по JSON полю:
CREATE INDEX idx_products_price ON products((data->>'price')::numeric);
SELECT * FROM products WHERE (data->>'price')::numeric > 100;
```

---

## 8. Когда индексы НЕ помогают

```sql
-- 1. Низкая селективность (много строк)
-- status IN ('active', 'inactive') → 90% таблицы
-- Лучше: seq scan

-- 2. Маленькие таблицы
-- < 1000 строк → seq scan часто быстрее

-- 3. Агрегаты без фильтрации
-- SELECT COUNT(*) FROM big_table;
-- → нужно читать всё равно всё

-- 4. Большие UPDATE (много строк):
-- Индекс замедляет bulk UPDATE
-- Лучше: DROP INDEX → массовый UPDATE → CREATE INDEX

-- 5. LIKE с wildcards в начале:
-- WHERE name LIKE '%alice%'  → Index не поможет
-- Решение: GIN с pg_trgm

-- pg_trgm для LIKE с wildcards:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_users_name_trgm ON users USING gin(name gin_trgm_ops);
SELECT * FROM users WHERE name LIKE '%alice%';  -- Теперь быстро!
```

---

## 9. Мониторинг индексов

```sql
-- Использование индексов
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,       -- Сколько раз использовался
    idx_tup_read,   -- Строк прочитано через индекс
    idx_tup_fetch   -- Строк fetch из heap
FROM pg_stat_user_indexes
ORDER BY idx_scan;

-- Неиспользуемые индексы (кандидаты на удаление):
SELECT 
    schemaname || '.' || tablename AS table,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND schemaname != 'pg_catalog'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Размер всех индексов:
SELECT 
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

## Заключение

Правильные индексы — одно из наиболее мощных средств оптимизации производительности базы данных. Но они не бесплатны.

**Ключевые выводы**:

1. **B-tree** — универсальный тип для equality и range queries. Supports `=`, `<`, `>`, `BETWEEN`, `LIKE 'prefix%'`, `ORDER BY`.

2. **Hash** — только equality, O(1). На практике B-tree почти всегда достаточен.

3. **GIN** — для массивов, JSONB, full-text search. Быстро для `@>`, `&&`, `@@`.

4. **GiST** — для геоданных (PostGIS), диапазонов, перекрытий. Extensible.

5. **Partial index**: индексируй только нужные строки. **Expression index**: по результату функции.

6. **Covering index / INCLUDE**: включи все нужные столбцы → Index-Only Scan без доступа к heap.

7. **Не злоупотребляй**: каждый индекс — overhead на INSERT/UPDATE/DELETE.

---

## Литература и источники

1. PostgreSQL Documentation. Indexes. https://www.postgresql.org/docs/current/indexes.html
2. Winand, M. (2012). *SQL Performance Explained*. https://use-the-index-luke.com/
3. PostgreSQL Documentation. Index Types. https://www.postgresql.org/docs/current/indexes-types.html
4. Comer, D. (1979). The Ubiquitous B-Tree. *ACM Computing Surveys*, 11(2), 121-137.
5. Hellerstein, J., Naughton, J., & Pfeffer, A. (1995). Generalized Search Trees for Database Systems. *VLDB 1995*.
6. Wikipedia. B-tree. https://en.wikipedia.org/wiki/B-tree
7. Wikipedia. GIN (PostgreSQL). https://en.wikipedia.org/wiki/GIN_(PostgreSQL)
8. pg_trgm Documentation. https://www.postgresql.org/docs/current/pgtrgm.html
9. PostGIS Documentation. https://postgis.net/docs/
10. PostgreSQL Documentation. pg_stat_user_indexes. https://www.postgresql.org/docs/current/monitoring-stats.html
