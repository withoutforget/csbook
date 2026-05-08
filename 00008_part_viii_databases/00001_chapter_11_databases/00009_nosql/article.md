# NoSQL: документные, key-value, колоночные и графовые базы данных

## Введение

Реляционные базы данных господствовали в мире хранения данных более четырёх десятилетий — и не без причины. ACID-гарантии, выразительный SQL, строгая схема и зрелая экосистема делают их первым выбором для большинства бизнес-приложений. Однако рост интернета в 2000-х годах обнажил ограничения реляционной модели при определённых сценариях: горизонтальное масштабирование на тысячи узлов, хранение документов с произвольной структурой, граф социальных связей с миллиардами рёбер или данные временных рядов с сотнями тысяч точек в секунду.

В ответ на эти вызовы появилось движение NoSQL — «Not Only SQL». Термин намеренно нечёткий: под ним объединяют системы с принципиально различными моделями данных. Понимание того, что именно предлагает каждое семейство NoSQL-баз и для каких задач оно оптимально, — критически важный навык архитектора систем.

---

## 1. Почему реляционная модель иногда не подходит

### 1.1 Ограничения схемы

Реляционная модель требует определить схему заранее. Если структура данных меняется часто или неоднородна между записями — миграции схемы становятся болью. Например, интернет-магазин хранит атрибуты товаров: у ноутбука — объём RAM и тактовая частота процессора, у обуви — размер и материал. В реляционной БД это или таблица EAV (Entity–Attribute–Value) с ужасной производительностью запросов, или отдельная таблица на каждый тип товара, или колонка JSONB.

### 1.2 Горизонтальное масштабирование

Реляционные СУБД традиционно масштабируются вертикально — более мощный сервер. Горизонтальное масштабирование (шардирование) добавляется через дополнительные инструменты (Citus, Vitess), но изначально не является частью дизайна.

NoSQL-системы изначально проектировались с расчётом на кластер из обычных серверов. Amazon DynamoDB управляет петабайтами данных на тысячах узлов; Apache Cassandra линейно масштабирует пропускную способность записи при добавлении узлов.

### 1.3 Специфические паттерны доступа

Некоторые задачи плохо ложатся на реляционную модель:

- **Поиск соседей в графе**: `SELECT * FROM friends WHERE user_id = X` — один запрос. Но «найти друзей друзей друзей» — это рекурсивные JOIN с экспоненциальным ростом сложности.
- **Запись телеметрии**: миллионы точек данных в секунду с агрегацией по временным окнам.
- **Полнотекстовый поиск**: PostgreSQL поддерживает FTS, но Elasticsearch оптимизирован именно под него.

### 1.4 Классификация NoSQL

| Семейство | Примеры | Ключевая структура |
|-----------|---------|-------------------|
| Key-Value | Redis, DynamoDB, Riak | Хеш-таблица: ключ → значение |
| Document | MongoDB, CouchDB, Couchbase | Ключ → JSON/BSON документ |
| Wide-Column | Cassandra, HBase, Bigtable | Строка → семейство → столбцы |
| Graph | Neo4j, Amazon Neptune, JanusGraph | Вершины + рёбра с атрибутами |
| Time-Series | InfluxDB, TimescaleDB, Prometheus | Метрика + метки + временна́я шкала |
| Search | Elasticsearch, OpenSearch, Solr | Инвертированный индекс |

---

## 2. Key-Value хранилища: простота и скорость O(1)

### 2.1 Модель данных

Key-Value — простейшая из NoSQL-моделей. Хранилище предоставляет три операции: `SET(key, value)`, `GET(key)`, `DELETE(key)`. Значение — непрозрачные байты; хранилище не знает о структуре данных внутри.

Сила модели — в предсказуемости: операции выполняются за O(1) при хранении в памяти (Redis) или O(log N) при хранении на диске (RocksDB, LevelDB, основанные на LSM-дереве).

### 2.2 Redis

Redis (Remote Dictionary Server) — хранилище структур данных в памяти с необязательной персистентностью. Помимо простых строк, Redis поддерживает:

- **Strings**: атомарные операции `INCR`/`DECR`, битовые операции
- **Lists**: двусвязный список, `LPUSH`/`RPOP` для очередей и стеков
- **Sets** и **Sorted Sets**: множества с уникальностью, ZSet с числовым score
- **Hashes**: вложенная хеш-таблица
- **Streams**: журнал событий с группами потребителей
- **HyperLogLog**: вероятностный подсчёт уникальных элементов
- **Geo**: хранение координат и радиусный поиск

```python
import redis

r = redis.Redis(host='localhost', port=6379, db=0)

# Кеширование с TTL
r.set('user:1001:profile', '{"name":"Alice","age":30}', ex=3600)
profile = r.get('user:1001:profile')

# Счётчик посещений
page_views = r.incr('page:homepage:views')

# Сортированное множество для лидерборда
r.zadd('leaderboard', {'alice': 9500, 'bob': 8200, 'charlie': 9750})
top3 = r.zrevrange('leaderboard', 0, 2, withscores=True)
# [('charlie', 9750.0), ('alice', 9500.0), ('bob', 8200.0)]

# Публикация/подписка
def handle_message(message):
    print(f"Получено: {message['data']}")

p = r.pubsub()
p.subscribe(**{'notifications': handle_message})

# Атомарная транзакция через MULTI/EXEC
pipe = r.pipeline()
pipe.multi()
pipe.incr('counter')
pipe.expire('counter', 60)
pipe.execute()
```

**Персистентность Redis:**

- **RDB (Redis Database)**: снапшот всей базы в двоичный файл через заданные интервалы. Быстрый рестарт, возможна потеря данных за последний интервал.
- **AOF (Append-Only File)**: запись каждой команды записи в журнал. Надёжнее, файл больше. `appendfsync always` — максимальная надёжность, `everysec` — компромисс.
- **RDB + AOF**: комбинированный режим в Redis 7.

**Кластерный Redis:**
Redis Cluster делит пространство из 16384 слотов между узлами. Ключ отображается в слот через `CRC16(key) % 16384`. Hashtag `{user:1001}` позволяет принудительно группировать ключи в одном слоте для атомарных multi-key операций.

### 2.3 Amazon DynamoDB

DynamoDB — полностью управляемое key-value/document хранилище AWS. Ключ состоит из обязательного **partition key** (определяет физический шард) и необязательного **sort key** (определяет порядок внутри шарда).

```python
import boto3
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('Orders')

# Запись
table.put_item(Item={
    'user_id': 'u-1001',       # partition key
    'order_id': 'ord-2024-001', # sort key
    'status': 'shipped',
    'total': '149.99',
    'items': ['sku-a', 'sku-b']
})

# Чтение по первичному ключу — O(1)
response = table.get_item(
    Key={'user_id': 'u-1001', 'order_id': 'ord-2024-001'}
)
order = response['Item']

# Запрос всех заказов пользователя
response = table.query(
    KeyConditionExpression=Key('user_id').eq('u-1001') &
                           Key('order_id').begins_with('ord-2024')
)
orders = response['Items']
```

DynamoDB предлагает две модели согласованности: **eventual consistency** (чтение из ближайшей реплики) и **strong consistency** (чтение из ведущего узла, вдвое дороже по capacity units).

---

## 3. Документные базы данных: гибкая схема и JSON

### 3.1 Модель данных

Документная БД хранит данные в виде самоописывающихся документов — обычно JSON или его двоичного варианта BSON. Документы группируются в коллекции (аналог таблиц). Каждый документ имеет уникальный `_id` и может содержать вложенные документы и массивы — без необходимости JOIN.

Преимущество: данные, которые всегда читаются вместе, хранятся вместе. Недостаток: дублирование при обновлении одного атрибута, упоминаемого в многих документах.

### 3.2 MongoDB

```python
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['ecommerce']
products = db['products']

# Вставка документа с произвольной структурой
laptop = {
    'name': 'ThinkPad X1 Carbon',
    'category': 'laptop',
    'price': 1299.99,
    'specs': {
        'ram_gb': 16,
        'cpu': 'Intel Core i7-1365U',
        'display_inch': 14.0,
        'weight_kg': 1.12
    },
    'tags': ['business', 'ultrabook', 'linux-compatible'],
    'created_at': datetime.utcnow()
}
result = products.insert_one(laptop)
laptop_id = result.inserted_id

# Гибкий запрос с проекцией
cheap_laptops = products.find(
    {'category': 'laptop', 'price': {'$lt': 1500}},
    {'name': 1, 'price': 1, 'specs.ram_gb': 1}
).sort('price', 1).limit(10)

# Агрегационный пайплайн — аналог SQL GROUP BY
pipeline = [
    {'$match': {'category': 'laptop'}},
    {'$group': {
        '_id': '$specs.ram_gb',
        'avg_price': {'$avg': '$price'},
        'count': {'$sum': 1}
    }},
    {'$sort': {'_id': 1}}
]
stats = list(products.aggregate(pipeline))

# $lookup — аналог JOIN (но работает медленнее embedded documents)
orders_with_products = db['orders'].aggregate([
    {'$lookup': {
        'from': 'products',
        'localField': 'product_id',
        'foreignField': '_id',
        'as': 'product_info'
    }}
])

# Атомарное обновление с операторами
products.update_one(
    {'_id': laptop_id},
    {
        '$set': {'price': 1199.99},
        '$push': {'tags': 'sale'},
        '$inc': {'view_count': 1}
    }
)
```

### 3.3 Индексы в MongoDB

MongoDB поддерживает индексы аналогичные PostgreSQL:

```python
# Одиночный индекс
products.create_index('category')

# Составной индекс
products.create_index([('category', 1), ('price', -1)])

# Индекс по вложенному полю
products.create_index('specs.ram_gb')

# Текстовый индекс для поиска
products.create_index([('name', 'text'), ('tags', 'text')])
results = products.find({'$text': {'$search': 'ultrabook business'}})

# TTL индекс для автоматического удаления
db['sessions'].create_index('created_at', expireAfterSeconds=3600)

# Просмотр плана запроса
explanation = products.find(
    {'category': 'laptop', 'price': {'$lt': 1500}}
).explain('executionStats')
print(explanation['executionStats']['totalDocsExamined'])
```

### 3.4 Схема документов: гибкость vs дисциплина

Отсутствие обязательной схемы — и сила, и слабость. В продакшн-системах рекомендуется использовать **JSON Schema validation** на уровне коллекции:

```javascript
db.createCollection('products', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['name', 'category', 'price'],
      properties: {
        price: { bsonType: 'double', minimum: 0 },
        category: { enum: ['laptop', 'phone', 'tablet'] }
      }
    }
  },
  validationAction: 'error'
})
```

---

## 4. Wide-Column: Cassandra и модель данных Bigtable

### 4.1 Происхождение модели

Google Bigtable (2006) и Amazon Dynamo (2007) — два влиятельных исследовательских документа, которые вдохновили Apache Cassandra. Cassandra объединила распределённую архитектуру Dynamo с моделью данных Bigtable.

Ключевое отличие wide-column от реляционной: строки в одной таблице могут иметь **разные наборы столбцов**. Физически данные хранятся с группировкой по строкам, и чтение всей строки очень эффективно.

### 4.2 Модель данных Cassandra

```
Keyspace (≈ database)
  └── Table
        ├── Partition Key → определяет физический узел (шард)
        ├── Clustering Key → порядок строк внутри партиции
        └── Regular Columns → данные
```

Запрос в Cassandra **почти всегда должен включать partition key** — иначе кластер вынужден опросить все узлы (full cluster scan).

```python
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from datetime import datetime, timedelta
import uuid

cluster = Cluster(['localhost'])
session = cluster.connect()

session.execute("""
    CREATE KEYSPACE IF NOT EXISTS iot
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3}
""")
session.set_keyspace('iot')

# Partition key: (device_id, date) — все данные устройства за день на одном узле
# Clustering key: timestamp DESC — новые данные первые при чтении
session.execute("""
    CREATE TABLE IF NOT EXISTS sensor_readings (
        device_id   UUID,
        date        DATE,
        ts          TIMESTAMP,
        temperature FLOAT,
        humidity    FLOAT,
        PRIMARY KEY ((device_id, date), ts)
    ) WITH CLUSTERING ORDER BY (ts DESC)
      AND default_time_to_live = 2592000
""")  # TTL 30 дней

# Запись — всегда по partition key, O(1)
device_id = uuid.UUID('550e8400-e29b-41d4-a716-446655440000')
session.execute("""
    INSERT INTO sensor_readings (device_id, date, ts, temperature, humidity)
    VALUES (%s, %s, %s, %s, %s)
    USING TTL 2592000
""", (device_id, datetime.today().date(), datetime.utcnow(), 23.5, 67.2))

# Запрос последних 100 измерений за сегодня
today = datetime.today().date()
rows = session.execute("""
    SELECT ts, temperature, humidity
    FROM sensor_readings
    WHERE device_id = %s AND date = %s
    LIMIT 100
""", (device_id, today))

for row in rows:
    print(f"{row.ts}: {row.temperature}°C, {row.humidity}%")
```

### 4.3 Согласованность в Cassandra: уровни кворума

Cassandra — AP-система (по CAP): она предпочитает доступность согласованности при разбиении сети. Уровень согласованности задаётся на уровне запроса:

| Уровень | Описание | Гарантия |
|---------|----------|---------|
| `ONE` | Ответ от одной реплики | Самый быстрый, возможны устаревшие данные |
| `QUORUM` | Ответ от большинства реплик | Строгая согласованность при RF=3 |
| `ALL` | Ответ от всех реплик | Максимальная согласованность, уязвим к отказам |
| `LOCAL_QUORUM` | Кворум в локальном датацентре | Оптимально для multi-DC |

Правило: при `WRITE=QUORUM` + `READ=QUORUM` и RF=3, запись подтверждают 2 реплики, чтение — 2 реплики. Суммарно 4 из 6 операций перекрываются — гарантируется, что хотя бы одна реплика видела последнюю запись.

### 4.4 LSM-дерево — основа быстрой записи

Cassandra использует Log-Structured Merge Tree (LSM-tree):

1. Запись идёт в **MemTable** (в памяти) + CommitLog (на диске для восстановления)
2. Когда MemTable заполнена, она сбрасывается в неизменяемый **SSTable** (Sorted Strings Table)
3. Фоновый **compaction** сливает SSTables, удаляя устаревшие версии и tombstone-записи

Это даёт исключительную скорость записи (O(1) амортизированно), но чтение может требовать обращения к нескольким SSTables. **Bloom filter** позволяет быстро определить, есть ли ключ в SSTable, избегая лишних дисковых I/O.

---

## 5. Графовые базы данных: Neo4j и язык Cypher

### 5.1 Когда граф лучше реляционной модели

Рассмотрим запрос «найди всех пользователей, с которыми у Алисы есть общие друзья»:

**SQL:**
```sql
SELECT DISTINCT u.name
FROM users u
JOIN friendships f1 ON f1.friend_b = u.id
JOIN friendships f2 ON f2.friend_b = f1.friend_a
WHERE f2.friend_a = (SELECT id FROM users WHERE name = 'Alice')
  AND u.id != (SELECT id FROM users WHERE name = 'Alice');
```

При миллионах пользователей этот JOIN взрывается. Графовая СУБД хранит рёбра вместе с вершинами — обход графа по рёбрам выполняется за O(степени вершины), не зависит от общего числа вершин.

### 5.2 Property Graph модель

Граф состоит из:
- **Nodes (вершины)**: метки + свойства (`Person{name, age}`)
- **Relationships (рёбра)**: тип + направление + свойства (`[:KNOWS{since: 2020}]`)

### 5.3 Cypher — декларативный язык запросов Neo4j

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687",
                               auth=("neo4j", "password"))

def create_social_graph(tx):
    tx.run("""
        MERGE (alice:Person {name: 'Alice', city: 'Moscow'})
        MERGE (bob:Person {name: 'Bob', city: 'SPb'})
        MERGE (charlie:Person {name: 'Charlie', city: 'Moscow'})
        MERGE (diana:Person {name: 'Diana', city: 'Kazan'})
        MERGE (alice)-[:KNOWS {since: 2020}]->(bob)
        MERGE (alice)-[:KNOWS {since: 2019}]->(charlie)
        MERGE (bob)-[:KNOWS {since: 2021}]->(diana)
        MERGE (charlie)-[:KNOWS {since: 2022}]->(diana)
    """)

def find_friends_of_friends(tx, name):
    result = tx.run("""
        MATCH (p:Person {name: $name})-[:KNOWS]->(friend)-[:KNOWS]->(fof)
        WHERE NOT (p)-[:KNOWS]->(fof) AND fof <> p
        RETURN DISTINCT fof.name AS name, count(*) AS mutual_friends
        ORDER BY mutual_friends DESC
    """, name=name)
    return [(r['name'], r['mutual_friends']) for r in result]

def shortest_path(tx, from_name, to_name):
    result = tx.run("""
        MATCH path = shortestPath(
            (a:Person {name: $from})-[:KNOWS*]-(b:Person {name: $to})
        )
        RETURN [node IN nodes(path) | node.name] AS path_names,
               length(path) AS hops
    """, from_=from_name, to=to_name)
    return result.single()

# PageRank через Graph Data Science library
def compute_pagerank(tx):
    # Создание проекции графа
    tx.run("""
        CALL gds.graph.project('social', 'Person', 'KNOWS')
    """)
    result = tx.run("""
        CALL gds.pageRank.stream('social')
        YIELD nodeId, score
        RETURN gds.util.asNode(nodeId).name AS name, score
        ORDER BY score DESC LIMIT 10
    """)
    return [(r['name'], r['score']) for r in result]

with driver.session() as session:
    session.execute_write(create_social_graph)
    fof = session.execute_read(find_friends_of_friends, 'Alice')
    print(f"Друзья друзей Алисы: {fof}")
```

### 5.4 Применения графовых баз данных

| Домен | Задача | Пример |
|-------|--------|--------|
| Социальные сети | Рекомендации, обход графа | LinkedIn, Twitter |
| Fraud detection | Выявление мошеннических паттернов | Сети транзакций |
| Knowledge graph | Связанные знания | Google Knowledge Graph |
| Supply chain | Отслеживание зависимостей | Цепочки поставок |
| Access control | RBAC/ABAC политики | Вычисление прав |
| Биоинформатика | Белково-белковые взаимодействия | PPI-сети |

---

## 6. Сравнение NoSQL-семейств с реляционными СУБД

### 6.1 Матрица выбора

| Критерий | Relational | Key-Value | Document | Wide-Column | Graph |
|----------|-----------|-----------|---------|-------------|-------|
| Схема | Жёсткая | Нет | Гибкая | Гибкая | Гибкая |
| JOIN | Да | Нет | Ограниченно | Нет | Нативно |
| ACID | Полный | Частично (Redis) | Частично | Eventual | Полный (Neo4j) |
| Горизонтальное масштабирование | Сложно | Легко | Легко | Нативно | Сложно |
| Сложные запросы | Отлично | Плохо | Хорошо | Ограниченно | Отлично для графов |
| Скорость записи | Средняя | Очень высокая | Высокая | Очень высокая | Средняя |
| Зрелость экосистемы | Высокая | Высокая | Высокая | Высокая | Средняя |

### 6.2 Правило выбора: паттерн доступа первичен

**Правило NoSQL**: проектирование схемы начинается с вопроса «как мы будем читать данные?», а не «как данные устроены». Это противоположность реляционного подхода (нормализация → JOIN).

Примеры:

- **Сессии пользователей**: key-value (Redis). Ключ = session_id, значение = JSON, TTL = 30 минут.
- **Профили пользователей с произвольными атрибутами**: документная БД (MongoDB).
- **Лента активности с временным окном**: wide-column (Cassandra). Partition key = user_id, clustering key = timestamp.
- **Рекомендации «похожие товары»**: графовая БД (Neo4j) или специализированный движок.
- **Транзакции переводов денег**: реляционная БД. ACID критичен.

### 6.3 Полиглот-персистентность

Крупные системы используют несколько типов баз данных одновременно:

```
Сервис заказов
├── PostgreSQL — заказы, платежи (ACID критично)
├── Redis — корзина покупок, сессии, кеш
├── MongoDB — каталог товаров (гибкая схема атрибутов)
├── Cassandra — история событий, аналитические потоки
├── Elasticsearch — полнотекстовый поиск по товарам
└── Neo4j — рекомендации ("с этим товаром покупают")
```

Цена: операционная сложность возрастает. Каждая система требует мониторинга, резервного копирования, экспертизы.

---

## 7. Согласованность в NoSQL: CAP и BASE

### 7.1 CAP теорема в контексте NoSQL

По теореме CAP (Brewer, 2000), распределённая система не может одновременно обеспечить:
- **C**onsistency (согласованность)
- **A**vailability (доступность)
- **P**artition tolerance (устойчивость к разбиению сети)

На практике разбиение сети происходит, поэтому выбор — между согласованностью и доступностью:
- **CP-системы** (MongoDB в режиме strong consistency, HBase): предпочитают согласованность
- **AP-системы** (Cassandra, DynamoDB с eventual consistency): предпочитают доступность

### 7.2 BASE — альтернатива ACID

| ACID | BASE |
|------|------|
| Atomicity | **B**asically **A**vailable |
| Consistency | **S**oft state |
| Isolation | **E**ventual consistency |
| Durability | |

**Eventual consistency**: при отсутствии новых записей система в конечном счёте достигает согласованного состояния. Для многих сценариев (счётчики лайков, рейтинги) это приемлемо.

### 7.3 Практические паттерны согласованности

**Read-your-writes**: после записи пользователь всегда видит своё изменение. Достигается через маршрутизацию чтений на ту же реплику или сессионные токены.

**Monotonic reads**: пользователь никогда не видит «откат» к более старым данным при повторных чтениях. Клиент отслеживает прочитанный версии/временную метку.

**Conflict resolution в Cassandra**: при конфликте (две записи в разделённом кластере) побеждает запись с более новым timestamp (Last Write Wins). Для счётчиков используются **CRDT** (Conflict-Free Replicated Data Types).

---

## 8. Практический кейс: выбор БД для системы уведомлений

### 8.1 Требования

- 50 млн пользователей
- 10 млн уведомлений в день
- Хранение за 90 дней
- Запрос: «непрочитанные уведомления пользователя», «все уведомления за период»
- Пометка «прочитано» атомарно

### 8.2 Анализ вариантов

**PostgreSQL**: при 900 млн строк ($10\text{M}/\text{день} \times 90\ \text{дней}$) запросы по user_id потребуют индекса. С партиционированием по месяцам — вполне рабочий вариант.

**Cassandra**: идеальная схема — partition key = (user_id, month), clustering key = (created_at DESC). Запрос за месяц по user_id — O(1). Масштабирование записи линейное.

**Redis**: хранить последние N уведомлений в List, счётчик непрочитанных — в String с INCR/DECR. Персистентность — проблема при больших объёмах.

### 8.3 Реализация на Cassandra

```python
from cassandra.cluster import Cluster
from cassandra.query import PreparedStatement
import uuid
from datetime import datetime

cluster = Cluster(['cassandra-1', 'cassandra-2', 'cassandra-3'])
session = cluster.connect('notifications')

# Схема таблицы
CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS user_notifications (
        user_id     UUID,
        year_month  TEXT,           -- '2024-01'
        created_at  TIMESTAMP,
        notif_id    UUID,
        type        TEXT,
        message     TEXT,
        is_read     BOOLEAN,
        PRIMARY KEY ((user_id, year_month), created_at, notif_id)
    ) WITH CLUSTERING ORDER BY (created_at DESC, notif_id ASC)
      AND default_time_to_live = 7776000  -- 90 дней
"""

insert_stmt = session.prepare("""
    INSERT INTO user_notifications
    (user_id, year_month, created_at, notif_id, type, message, is_read)
    VALUES (?, ?, ?, ?, ?, ?, false)
""")

get_unread_stmt = session.prepare("""
    SELECT notif_id, created_at, type, message
    FROM user_notifications
    WHERE user_id = ? AND year_month = ? AND is_read = false
    LIMIT 50
    ALLOW FILTERING
""")  # ALLOW FILTERING допустим, т.к. партиция уже отфильтрована

mark_read_stmt = session.prepare("""
    UPDATE user_notifications
    SET is_read = true
    WHERE user_id = ? AND year_month = ? AND created_at = ? AND notif_id = ?
""")

def send_notification(user_id, notif_type, message):
    now = datetime.utcnow()
    year_month = now.strftime('%Y-%m')
    notif_id = uuid.uuid4()
    session.execute(insert_stmt, (user_id, year_month, now, notif_id, notif_type, message))
    return notif_id

def get_unread(user_id):
    now = datetime.utcnow()
    year_month = now.strftime('%Y-%m')
    return list(session.execute(get_unread_stmt, (user_id, year_month)))
```

---

## 9. Антипаттерны NoSQL

### 9.1 Использование NoSQL там, где нужны JOIN

Если запросы часто требуют объединения данных из разных «коллекций», это сигнал, что либо нужна реляционная БД, либо данные нужно денормализовать (embedded documents).

### 9.2 Игнорирование паттернов доступа при проектировании

В Cassandra нельзя добавить новое условие WHERE после создания таблицы без создания новой таблицы и дублирования данных. Схема должна отражать запросы.

### 9.3 Отсутствие TTL для временных данных

Без TTL данные накапливаются бесконечно. В Redis — переполнение памяти и выселение по LRU. В Cassandra — tombstone-записи от удалений накапливаются без компакции.

### 9.4 Unbounded partitions в Cassandra

Если partition key = user_id без временного компонента, активный пользователь за годы накопит миллионы строк в одном разделе. Такой «горячий» раздел не масштабируется горизонтально и вызывает перегрузку одного узла.

---

## Заключение

NoSQL — не замена реляционным базам данных, а дополнение к ним. Каждое семейство решает конкретный класс задач:

- **Key-Value** (Redis) — кеш, сессии, счётчики, очереди сообщений
- **Document** (MongoDB) — каталоги, профили, контент с гибкой структурой
- **Wide-Column** (Cassandra) — временны́е ряды, ленты активности, IoT-данные
- **Graph** (Neo4j) — социальные графы, рекомендации, цепочки зависимостей

Ключевой вопрос: «каков паттерн доступа к данным?». Ответ на него определяет выбор модели данных, которая диктует выбор СУБД. Современные production-системы используют несколько типов баз (полиглот-персистентность), сочетая сильные стороны каждой из них.

---

## Библиография

1. DeCandia, G., et al. (2007). Dynamo: Amazon's Highly Available Key-value Store. *SOSP 2007*. ACM.
2. Chang, F., et al. (2006). Bigtable: A Distributed Storage System for Structured Data. *OSDI 2006*. USENIX.
3. Lakshman, A., & Malik, P. (2010). Cassandra: A Decentralized Structured Storage System. *ACM SIGOPS Operating Systems Review*, 44(2), 35–40.
4. Banker, K. (2011). *MongoDB in Action*. Manning Publications.
5. Robinson, I., Webber, J., & Eifrem, E. (2015). *Graph Databases: New Opportunities for Connected Data* (2nd ed.). O'Reilly Media.
6. Fowler, M. (2012). *NoSQL Distilled: A Brief Guide to the Emerging World of Polyglot Persistence*. Addison-Wesley.
7. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media.
8. Brewer, E. (2000). Towards Robust Distributed Systems. *PODC 2000*. ACM.
