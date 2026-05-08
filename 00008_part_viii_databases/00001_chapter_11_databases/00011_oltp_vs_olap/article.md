# OLTP против OLAP: транзакционные и аналитические системы

## Введение

В 1993 году Эдгар Кодд, создатель реляционной модели, ввёл термин OLAP (Online Analytical Processing), противопоставив его OLTP (Online Transaction Processing). Это разделение отражает фундаментальную дихотомию: одни системы оптимизированы для тысяч коротких транзакций в секунду, изменяющих небольшое количество строк; другие — для редких, но масштабных запросов, агрегирующих миллиарды записей.

Понимание разницы между OLTP и OLAP критично для выбора правильной архитектуры хранения данных. Попытка использовать одну систему для обоих сценариев приводит к деградации производительности в обоих направлениях.

---

## 1. OLTP: транзакционная обработка

### 1.1 Характеристики OLTP-нагрузки

OLTP-системы обслуживают оперативные бизнес-процессы:

| Характеристика | Типичное значение |
|---------------|-----------------|
| Транзакций в секунду | 100 – 100 000 |
| Строк на запрос | 1 – 100 |
| Размер транзакции | Малый |
| Тип операций | INSERT, UPDATE, DELETE, точечные SELECT |
| Время ответа | < 10 мс |
| Пользователи | Много (конкурентные) |
| Данные | Текущие, оперативные |
| Индексы | Много, на часто запрашиваемые колонки |

**Примеры OLTP-систем**: PostgreSQL, MySQL, Oracle, SQL Server, CockroachDB.

**Типичные запросы OLTP:**
```sql
-- Проверка баланса счёта
SELECT balance FROM accounts WHERE account_id = 12345;

-- Перевод средств
BEGIN;
UPDATE accounts SET balance = balance - 500 WHERE account_id = 12345;
UPDATE accounts SET balance = balance + 500 WHERE account_id = 67890;
INSERT INTO transactions (from_id, to_id, amount, ts) 
  VALUES (12345, 67890, 500, NOW());
COMMIT;

-- Получение заказов пользователя
SELECT o.id, o.status, o.total 
FROM orders o 
WHERE o.user_id = 42 
  AND o.created_at > NOW() - INTERVAL '30 days'
ORDER BY o.created_at DESC 
LIMIT 20;
```

### 1.2 Строковое хранение (Row-oriented storage)

OLTP-базы хранят данные **по строкам**: все поля одной записи расположены на диске рядом. Это оптимально для:
- Вставки новой записи (один I/O для всей строки)
- Обновления записи (находим строку, обновляем поля)
- Чтения полной записи по первичному ключу

```
Файл данных (строковое хранение):
┌──────────────────────────────────────────────┐
│ [id=1][name=Alice][age=30][salary=80000][...] │ ← строка 1
│ [id=2][name=Bob  ][age=25][salary=70000][...] │ ← строка 2  
│ [id=3][name=Carol][age=35][salary=90000][...] │ ← строка 3
└──────────────────────────────────────────────┘
```

При запросе `SELECT AVG(salary) FROM employees` с 10 миллионами строк — читаются **все данные**, включая name, age и другие ненужные поля. Это неэффективно для аналитики.

### 1.3 ACID-требования OLTP

OLTP требует полного ACID: каждая транзакция должна быть атомарной, корректной, изолированной от других и долговечной. Это достигается через WAL, MVCC и строгие механизмы блокировок — все они добавляют overhead к каждой операции.

---

## 2. OLAP: аналитическая обработка

### 2.1 Характеристики OLAP-нагрузки

OLAP-системы отвечают на аналитические вопросы бизнеса:

| Характеристика | Типичное значение |
|---------------|-----------------|
| Запросов в секунду | 1 – 100 |
| Строк на запрос | Миллионы – миллиарды |
| Тип операций | SELECT, GROUP BY, агрегации |
| Время ответа | Секунды – минуты |
| Пользователи | Немного (аналитики) |
| Данные | Исторические, immutable |
| Индексы | Мало или нет (columnar scan быстрее) |

**Примеры OLAP-систем**: ClickHouse, BigQuery, Redshift, Snowflake, DuckDB, Apache Druid.

**Типичные запросы OLAP:**
```sql
-- Выручка по категориям за квартал
SELECT 
    p.category,
    DATE_TRUNC('month', o.created_at) AS month,
    SUM(oi.quantity * oi.price) AS revenue,
    COUNT(DISTINCT o.user_id) AS unique_buyers
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.created_at BETWEEN '2024-01-01' AND '2024-03-31'
GROUP BY p.category, DATE_TRUNC('month', o.created_at)
ORDER BY revenue DESC;

-- Воронка конверсии
SELECT 
    step,
    COUNT(*) AS users,
    COUNT(*) * 100.0 / FIRST_VALUE(COUNT(*)) OVER (ORDER BY step_order) AS conversion_pct
FROM user_funnel_events
WHERE session_date = '2024-03-15'
GROUP BY step, step_order
ORDER BY step_order;
```

### 2.2 Колоночное хранение (Column-oriented storage)

OLAP-базы хранят данные **по столбцам**: все значения одного поля расположены последовательно на диске.

```
Колоночное хранение:
┌─────────────────────┐
│ id: [1, 2, 3, ...]  │ ← все id
│ name: [Alice, Bob]  │ ← все имена
│ salary: [80k,70k,90k│ ← все зарплаты ← ТОЛЬКО ЭТО читаем для AVG(salary)
└─────────────────────┘
```

**Преимущества колоночного хранения:**

1. **Проекция**: `SELECT AVG(salary)` читает только колонку salary, не касаясь остальных данных
2. **Сжатие**: однотипные значения в колонке сжимаются значительно лучше (run-length encoding, dictionary encoding, delta encoding)
3. **SIMD-векторизация**: процессор обрабатывает несколько значений за один такт
4. **Предсказание ветвлений**: линейный обход без прыжков

```python
import struct
import time

# Симуляция строкового vs колоночного хранения
def benchmark_row_vs_column():
    N = 1_000_000
    
    # Строковое хранение: (id, name, salary, city, age)
    row_data = [
        (i, f'user_{i}', 50000 + (i % 50000), f'city_{i%10}', 20 + i%50)
        for i in range(N)
    ]
    
    # Колоночное хранение: отдельные массивы
    import array
    col_salary = array.array('i', [50000 + (i % 50000) for i in range(N)])
    col_age = array.array('i', [20 + i % 50 for i in range(N)])
    
    # OLAP запрос: AVG(salary) WHERE age > 30
    
    # Строковое: читаем все поля каждой строки
    start = time.perf_counter()
    total = sum(r[2] for r in row_data if r[4] > 30)
    count = sum(1 for r in row_data if r[4] > 30)
    row_time = time.perf_counter() - start
    
    # Колоночное: читаем только salary и age
    start = time.perf_counter()
    total = sum(s for s, a in zip(col_salary, col_age) if a > 30)
    count = sum(1 for a in col_age if a > 30)
    col_time = time.perf_counter() - start
    
    print(f"Row scan: {row_time:.3f}s")
    print(f"Col scan: {col_time:.3f}s")
    print(f"Speedup: {row_time/col_time:.1f}x")

benchmark_row_vs_column()
```

---

## 3. Хранилища данных и архитектура ETL

### 3.1 Data Warehouse архитектура

Классическая корпоративная архитектура разделяет OLTP и OLAP через **ETL-процесс** (Extract, Transform, Load):

```
OLTP-источники           ETL              Data Warehouse
┌──────────────┐     ┌─────────┐        ┌──────────────┐
│ PostgreSQL   ├────►│         │        │              │
│ (заказы)     │     │ Extract │        │   Staging    │
├──────────────┤     │    ↓    ├───────►│      ↓       │
│ MySQL        ├────►│Transform│        │   DW layer   │
│ (продукты)   │     │    ↓    │        │      ↓       │
├──────────────┤     │  Load   │        │  Data Marts  │
│ MongoDB      ├────►│         │        │              │
│ (события)    │     └─────────┘        └──────┬───────┘
└──────────────┘                               │
                                               ▼
                                        BI-инструменты
                                     (Tableau, Metabase)
```

**Проблемы классического ETL:**
- Данные в warehouse отстают на часы или сутки
- Сложность трансформаций увеличивает хрупкость пайплайна
- Изменение схемы источника ломает ETL

### 3.2 Схемы Data Warehouse: Star и Snowflake

**Star Schema** (Звёздная схема): центральная таблица фактов (fact table) с числовыми метриками, окружённая таблицами измерений (dimension tables).

```sql
-- Факт-таблица: продажи
CREATE TABLE fact_sales (
    sale_id         BIGINT,
    date_key        INT REFERENCES dim_date(date_key),
    product_key     INT REFERENCES dim_product(product_key),
    store_key       INT REFERENCES dim_store(store_key),
    customer_key    INT REFERENCES dim_customer(customer_key),
    quantity        INT,
    unit_price      DECIMAL(10,2),
    discount        DECIMAL(5,2),
    net_revenue     DECIMAL(12,2)
);

-- Таблица измерения: дата
CREATE TABLE dim_date (
    date_key        INT PRIMARY KEY,
    full_date       DATE,
    year            INT,
    quarter         INT,
    month           INT,
    month_name      VARCHAR(20),
    week_of_year    INT,
    day_of_week     INT,
    is_holiday      BOOLEAN
);

-- Аналитический запрос по звёздной схеме
SELECT 
    d.year,
    d.quarter,
    p.category,
    SUM(f.net_revenue) AS revenue,
    SUM(f.quantity) AS units_sold
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
JOIN dim_product p ON f.product_key = p.product_key
WHERE d.year = 2024
GROUP BY d.year, d.quarter, p.category
ORDER BY revenue DESC;
```

**Snowflake Schema**: dimension-таблицы нормализованы — уменьшают дублирование, но требуют более сложных JOIN.

### 3.3 OLAP Cube: многомерный анализ

OLAP-куб — концептуальная модель данных с несколькими измерениями (время, продукт, регион) и мерами (продажи, выручка). Операции над кубом:

- **Slice**: фиксируем одно измерение (`WHERE year = 2024`)
- **Dice**: выбираем диапазон по нескольким измерениям
- **Drill-down**: детализируем (`год → квартал → месяц`)
- **Roll-up**: агрегируем (`город → регион → страна`)
- **Pivot**: транспонируем измерения

---

## 4. Modern Data Stack: Lambda и Kappa архитектуры

### 4.1 Проблема свежести данных

Классический ETL даёт данные с задержкой. Бизнес хочет видеть аналитику в реальном времени. Это привело к появлению стриминговых архитектур.

### 4.2 Lambda Architecture

Предложена Натаном Марцем (2011). Разделяет обработку на три слоя:

```
Входящие данные
       │
       ├──────────────────► Batch Layer (Hadoop/Spark)
       │                    - Полная переработка исторических данных
       │                    - Точность, но задержка часы/дни
       │
       └──────────────────► Speed Layer (Kafka Streams/Flink)
                            - Только свежие данные
                            - Низкая задержка, приближённые результаты
                                   │
                            Serving Layer (Druid/HBase)
                            - Объединяет результаты batch + speed
                            - Отвечает на запросы
```

**Проблема Lambda**: два разных кодовых пути для одной логики. Batch и streaming расходятся в семантике.

### 4.3 Kappa Architecture

Предложена Джеем Крепсом (Confluent, 2014). Единый путь — только стриминг:

```
Входящие данные → Kafka (retention: 90 дней)
                      │
                      ├──► Flink/Spark Streaming → Serving Layer
                      │    (реальное время)
                      │
                      └──► Reprocess при изменении логики
                           (replay из Kafka)
```

Kafka хранит данные достаточно долго для полной переработки при обновлении логики. Один путь кода — для real-time и для backfill.

### 4.4 Data Lakehouse: объединение Data Lake и DW

Modern архитектура 2020-х: **Lakehouse** объединяет дешёвое хранение объектного хранилища (S3/GCS) с ACID-транзакциями и схемой поверх него.

Форматы: **Apache Iceberg**, **Delta Lake**, **Apache Hudi** — добавляют транзакционность и schema evolution к Parquet-файлам в S3.

```python
# Работа с Delta Lake через PySpark
from delta import DeltaTable
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .config("spark.jars.packages", "io.delta:delta-core_2.12:2.4.0") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .getOrCreate()

# Запись с ACID-гарантиями
df = spark.read.parquet("s3://raw-data/sales/2024/")
df.write.format("delta").mode("overwrite").save("s3://lakehouse/sales/")

# Time travel — чтение предыдущей версии
dt = DeltaTable.forPath(spark, "s3://lakehouse/sales/")
df_v1 = spark.read.format("delta") \
    .option("versionAsOf", 1) \
    .load("s3://lakehouse/sales/")

# MERGE (upsert) — атомарная операция
dt.alias("target").merge(
    source=new_data.alias("source"),
    condition="target.sale_id = source.sale_id"
).whenMatchedUpdateAll() \
 .whenNotMatchedInsertAll() \
 .execute()
```

---

## 5. Сравнительная таблица OLTP vs OLAP

| Аспект | OLTP | OLAP |
|--------|------|------|
| Назначение | Оперативная обработка | Аналитика и отчётность |
| Запросы | Короткие, точечные | Длинные, агрегирующие |
| Объём данных на запрос | Строки | Миллионы-миллиарды строк |
| Тип операций | R/W | Преимущественно R |
| Актуальность данных | Текущие (секунды) | Исторические (часы-дни) |
| Хранение | Строковое (row) | Колоночное (columnar) |
| Нормализация | Высокая (3NF+) | Денормализация (star schema) |
| Индексы | Много индексов | Мало или нет |
| Параллельные пользователи | Тысячи | Десятки |
| ACID | Обязательно | Опционально |
| Примеры | PostgreSQL, MySQL | ClickHouse, BigQuery, Redshift |
| Backup стратегия | Frequent WAL + base | Weekly snapshots + ETL |

---

## 6. HTAP: Hybrid Transaction and Analytical Processing

### 6.1 Идея HTAP

В 2014 году Gartner ввёл термин HTAP: системы, способные обрабатывать как OLTP, так и OLAP нагрузки на одних и тех же данных без ETL.

**Преимущества**: аналитика на актуальных данных в реальном времени.
**Сложности**: разные оптимизации для OLTP (низкая задержка, точечный доступ) и OLAP (сканирование, агрегация) плохо совместимы.

### 6.2 Примеры HTAP-систем

**TiDB**: строковое хранилище TiKV (OLTP) + колоночное TiFlash (OLAP) с автоматической синхронизацией через Raft.

**SingleStore (MemSQL)**: in-memory строковые таблицы + дисковые колоночные, автоматический выбор.

**SAP HANA**: исторически первая коммерческая HTAP-система, работает целиком в оперативной памяти.

**PostgreSQL + TimescaleDB**: расширение добавляет compression и columnar storage для timeseries данных поверх обычного PostgreSQL.

### 6.3 Federated Query: аналитика без переноса данных

Альтернатива ETL — федеративные запросы: OLAP-движок запрашивает данные прямо из OLTP-источников в реальном времени.

```python
# Trino (бывший Presto): федеративный SQL-движок
# Запрос к PostgreSQL, MySQL и S3 одновременно

query = """
SELECT 
    pg.customer_name,
    mysql.order_count,
    s3.lifetime_value
FROM postgresql.prod.customers pg
JOIN mysql.orders.summary mysql 
    ON mysql.customer_id = pg.id
JOIN s3.analytics.ltv s3 
    ON s3.customer_id = pg.id
WHERE pg.country = 'RU'
    AND mysql.order_count > 5
ORDER BY s3.lifetime_value DESC
LIMIT 100
"""
# Trino строит план запроса с pushdown предикатов в каждую систему
```

---

## 7. Практический выбор: матрица решений

### 7.1 Когда использовать OLTP

- Веб-приложения с пользовательскими транзакциями
- ERP, CRM, финансовые системы
- Любые сценарии с частыми UPDATE/DELETE
- Требования к консистентности в реальном времени

**Рекомендация**: PostgreSQL для большинства случаев. CockroachDB для глобально распределённых OLTP.

### 7.2 Когда использовать OLAP

- Ежедневные/еженедельные бизнес-отчёты
- Машинное обучение на больших исторических данных
- Data exploration и ad-hoc аналитика
- Мониторинг с агрегацией метрик

**Рекомендация**: ClickHouse для высокой скорости на умеренных объёмах. BigQuery/Snowflake для serverless масштабирования. DuckDB для аналитики на ноутбуке или как in-process OLAP.

### 7.3 DuckDB: OLAP in-process

DuckDB — встраиваемая колоночная СУБД (как SQLite для OLAP). Работает прямо в Python-процессе, читает Parquet/CSV без ETL:

```python
import duckdb
import pandas as pd

# Создание in-memory БД
con = duckdb.connect(':memory:')

# Прямое чтение Parquet без загрузки в память
result = con.execute("""
    SELECT 
        year(sale_date) AS year,
        category,
        SUM(revenue) AS total_revenue,
        COUNT(*) AS transactions
    FROM read_parquet('sales_*.parquet')
    WHERE country = 'RU'
    GROUP BY year(sale_date), category
    ORDER BY total_revenue DESC
""").fetchdf()

print(result.head(10))

# Запрос к Pandas DataFrame без копирования данных
df = pd.read_csv('large_dataset.csv')
result = con.execute("""
    SELECT AVG(price), category 
    FROM df 
    GROUP BY category
""").fetchdf()

# Экспорт результата в Parquet
con.execute("""
    COPY (SELECT * FROM df WHERE price > 100) 
    TO 'output.parquet' (FORMAT PARQUET)
""")
```

DuckDB особенно популярен для локального анализа данных, тестирования аналитических запросов и замены Pandas для больших файлов.

---

## 8. Эволюция данных: schema evolution

### 8.1 Проблема изменения схемы

В OLTP изменение схемы — ALTER TABLE — может блокировать таблицу минутами (при большом размере). Online DDL в MySQL и PostgreSQL решают это, но требуют внимания.

В OLAP изменение схемы более сложное: исторические данные могут не иметь нового поля. Нужна обратная совместимость.

### 8.2 Schema-on-read vs Schema-on-write

**Schema-on-write** (традиционные СУБД): схема определена до записи данных, все данные валидируются при вставке. Ошибки обнаруживаются рано.

**Schema-on-read** (Data Lake, Parquet, JSON): схема применяется при чтении. Данные можно хранить «как есть» и интерпретировать по-разному при разных запросах. Гибкость ценой потенциальных ошибок.

```python
# Parquet: schema evolution без миграции
import pyarrow as pa
import pyarrow.parquet as pq

# Версия 1 схемы
schema_v1 = pa.schema([
    ('user_id', pa.int64()),
    ('event', pa.string()),
    ('timestamp', pa.timestamp('ms'))
])

# Версия 2: добавлено поле 'country' (nullable для совместимости)
schema_v2 = pa.schema([
    ('user_id', pa.int64()),
    ('event', pa.string()),
    ('timestamp', pa.timestamp('ms')),
    ('country', pa.string())  # новое поле
])

# Чтение старых файлов с новой схемой — автоматически country=None
dataset = pq.read_table('events/', schema=schema_v2)
```

---

## Заключение

Разделение на OLTP и OLAP отражает принципиальное различие требований: оперативность vs аналитическая мощь. Реляционные СУБД с строковым хранением оптимальны для транзакций; колоночные хранилища — для агрегаций над миллиардами строк.

Современная тенденция: Data Lakehouse объединяет дешёвое хранение S3 с ACID-транзакциями (Iceberg, Delta Lake) и открытым форматом Parquet. Это даёт гибкость Data Lake при структурированности Data Warehouse.

HTAP-системы (TiDB, SingleStore) пытаются объединить оба мира, но идеального решения не существует — физика хранения данных диктует разные оптимизации для точечного доступа и сканирования.

---

## Библиография

1. Codd, E.F. (1993). Providing OLAP (On-line Analytical Processing) to User-Analysts: An IT Mandate. Arbor Software.
2. Kimball, R., & Ross, M. (2013). *The Data Warehouse Toolkit: The Definitive Guide to Dimensional Modeling* (3rd ed.). Wiley.
3. Marz, N., & Warren, J. (2015). *Big Data: Principles and Best Practices of Scalable Real-Time Data Systems*. Manning.
4. Kreps, J. (2014). Questioning the Lambda Architecture. O'Reilly.
5. Abadi, D., et al. (2008). Column-Stores vs. Row-Stores: How Different Are They Really? *SIGMOD 2008*.
6. Armbrust, M., et al. (2021). Lakehouse: A New Generation of Open Platforms that Unify Data Warehousing and Advanced Analytics. *CIDR 2021*.
7. Raasveldt, M., & Mühleisen, H. (2019). DuckDB: an Embeddable Analytical Database. *SIGMOD 2019*.
8. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media. Chapter 3.
