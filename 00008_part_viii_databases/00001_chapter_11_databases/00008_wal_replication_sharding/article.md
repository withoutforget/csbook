# WAL, репликация и шардирование

## Введение

По мере роста приложения один сервер базы данных перестаёт справляться. Отказ сервера не должен означать потерю данных (durability). Один сервер не может обслуживать миллионы запросов в секунду (scalability). Один сервер — единая точка отказа (availability).

Write-Ahead Log (WAL) — фундаментальный механизм надёжности PostgreSQL, лежащий в основе как восстановления после сбоев, так и репликации. Репликация обеспечивает высокую доступность: при отказе primary быстро поднимается replica. Шардирование позволяет горизонтально масштабировать запись и хранение данных.

В этой главе мы разберём устройство WAL, оба типа репликации PostgreSQL (физическая и логическая), и архитектурные подходы к горизонтальному масштабированию.

---

## 1. WAL (Write-Ahead Log)

### 1.1 Зачем WAL

Проблема без WAL: если база данных обновляет страницы данных напрямую и система теряет питание в середине операции — данные на диске повреждены.

WAL решает это через принцип: **сначала запишем намерение в журнал, потом выполним**. Журнал (WAL) записывается последовательно (быстро). При сбое — воспроизводим WAL записи.

```
Транзакция: UPDATE accounts SET balance=900 WHERE id=1

Без WAL:                            С WAL:
1. Изменяем страницу в памяти      1. Пишем WAL запись: "изменить accounts, id=1, balance=900"
2. Пишем страницу на диск          2. fsync WAL записи (sequential write - быстро)
   [СБОЙ ПИТАНИЯ]                  3. Отвечаем клиенту COMMIT (durability!)
   → Данные потеряны!              4. Изменяем страницу в памяти (асинхронно)
                                   5. Через checkpoint - пишем страницу на диск
                                   [СБОЙ ПИТАНИЯ]
                                   → При рестарте: replay WAL → данные восстановлены!
```

### 1.2 Структура WAL

WAL хранится в `$PGDATA/pg_wal/` как набор сегментных файлов по 16 МБ (настраивается):

```bash
ls -la $PGDATA/pg_wal/
# 000000010000000000000001
# 000000010000000000000002
# ...
# Формат: timeline / high 32 bits / low 32 bits of LSN

# LSN (Log Sequence Number) - позиция в WAL
# Показать текущую позицию:
SELECT pg_current_wal_lsn();
-- 0/15C4F828

# Разность LSN (сколько WAL сгенерировано):
SELECT pg_current_wal_lsn() - '0/15C4F000'::pg_lsn AS bytes_generated;
```

### 1.3 Checkpoint

Checkpoint — момент когда все грязные страницы записаны из shared_buffers на диск. После checkpoint старые WAL файлы можно удалить (если нет replica которая их ещё не получила):

```
Timeline WAL:
... [checkpoint] ... [WAL записи] ... [checkpoint] ...
                ↑                ↑
           Всё до               Всё до следующего checkpoint
           написано на диск     написано на диск

При crash recovery:
- Находим последний checkpoint
- Replay WAL от checkpoint до конца
```

```bash
# Настройки checkpoint (postgresql.conf):
# checkpoint_timeout = 5min      # Максимальный интервал
# max_wal_size = 1GB             # При превышении — checkpoint
# checkpoint_completion_target = 0.9  # 90% времени до следующего checkpoint

# Мониторинг:
SELECT * FROM pg_stat_bgwriter;
-- checkpoints_timed: запущенных по таймеру
-- checkpoints_req: запущенных из-за max_wal_size
-- checkpoint_write_time: время записи в мс
-- checkpoint_sync_time: время fsync в мс
```

---

## 2. Физическая репликация

### 2.1 Streaming Replication

Streaming Replication — основной тип репликации PostgreSQL. WAL записи передаются от primary к standby в реальном времени:

```
Primary                          Standby
┌────────────────────┐           ┌────────────────────┐
│                    │           │                    │
│  Client            │           │  WAL Receiver      │
│  ↓                 │           │  ↑                 │
│  Transactions      │  TCP      │  Apply WAL         │
│  ↓                 ├──────────>│  ↓                 │
│  WAL files         │  WAL      │  Update pages      │
│  ↓                 │  stream   │                    │
│  WAL Sender        │           └────────────────────┘
│                    │
└────────────────────┘
```

Настройка:

```bash
# primary (postgresql.conf):
wal_level = replica          # Минимум для репликации
max_wal_senders = 5          # Максимум standby
wal_keep_size = 256MB        # Хранить WAL даже после checkpoint
hot_standby = on             # Разрешить чтение на standby

# primary (pg_hba.conf):
host replication replicator standby_ip/32 md5

# Создать пользователя для репликации:
CREATE USER replicator REPLICATION PASSWORD 'secret';

# Запустить standby (на standby сервере):
pg_basebackup -h primary_ip -U replicator -D /var/lib/postgresql/data -P -Xs -R
# -Xs: включить streaming
# -R: записать recovery.conf

# postgresql.conf на standby:
hot_standby = on   # Разрешить SELECT запросы на standby
```

Проверка репликации:

```sql
-- На Primary:
SELECT 
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;

-- На Standby:
SELECT pg_is_in_recovery();  -- true = мы standby
SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;
```

### 2.2 WAL Shipping

Альтернатива streaming: primary копирует готовые WAL файлы на standby через archive_command:

```bash
# postgresql.conf на primary:
archive_mode = on
archive_command = 'scp %p standby:/archive/%f'
# %p = полный путь WAL файла
# %f = имя файла

# На standby (recovery.conf):
restore_command = 'scp standby:/archive/%f %p'
```

Преимущество: WAL файлы можно хранить S3/GCS для point-in-time recovery.

### 2.3 Synchronous vs Asynchronous Replication

```sql
-- Асинхронная (по умолчанию):
-- Primary сразу отвечает COMMIT, не ожидая подтверждения standby
-- Риск: при падении primary и failover на standby — потеря транзакций

-- Синхронная: primary ждёт подтверждения от standby
synchronous_standby_names = 'standby1'
-- или для N из M:
synchronous_standby_names = '2 (standby1, standby2, standby3)'

-- Уровни подтверждения:
synchronous_commit = remote_apply  -- Ждём применения WAL на standby (надёжно)
synchronous_commit = remote_write  -- Ждём записи в OS buffer на standby (промежуточно)
synchronous_commit = on            -- Ждём fsync на primary (local durability)
synchronous_commit = off           -- Async (fast, риск потери до 200ms данных)
```

---

## 3. Логическая репликация

### 3.1 Чем отличается от физической

| | Физическая | Логическая |
|-|-----------|-----------|
| Уровень | Побитовая копия страниц | Логические изменения (INSERT/UPDATE/DELETE) |
| Гранулярность | Вся БД | Отдельные таблицы |
| Версии | Одинаковые | Разные (PostgreSQL 12→16) |
| Платформа | Одинаковая | Разные |
| Фильтрация | Нет | По строкам/столбцам |
| Начальная синхронизация | pg_basebackup | Постепенная |
| Primary ключ | Нет требований | Требуется |

### 3.2 Настройка логической репликации

```sql
-- postgresql.conf:
-- wal_level = logical  (нужен для logical replication)
-- max_replication_slots = 10

-- На Publisher (source):
CREATE PUBLICATION my_publication 
FOR TABLE orders, products;
-- или все таблицы:
-- FOR ALL TABLES;

-- Проверить:
SELECT * FROM pg_publication;
SELECT * FROM pg_publication_tables WHERE pubname = 'my_publication';

-- На Subscriber (target):
CREATE SUBSCRIPTION my_subscription
CONNECTION 'host=publisher_ip dbname=mydb user=replicator password=secret'
PUBLICATION my_publication;

-- Проверить статус:
SELECT * FROM pg_subscription;
SELECT * FROM pg_stat_subscription;
-- last_msg_receipt_time: когда последний раз получили данные
-- latest_end_lsn: до какого LSN применили
```

### 3.3 Случаи использования логической репликации

```sql
-- 1. Репликация в другую версию PostgreSQL (нулевой downtime upgrade)
-- 2. Репликация в другую БД (MySQL, Kafka, DWH)
-- 3. Разгрузка primary: только нужные таблицы на аналитическом сервере
-- 4. Multi-master (bi-directional) через pglogical
-- 5. CDC (Change Data Capture) для event streaming

-- Debezium - популярный CDC tool:
-- Читает PostgreSQL WAL через logical replication slot
-- Отправляет изменения в Kafka
-- Kafka → Elasticsearch/ClickHouse/любой sink
```

---

## 4. Шардирование

### 4.1 Когда нужно шардирование

Вертикальное масштабирование (больше CPU/RAM/SSD) имеет пределы. Шардирование (горизонтальное партиционирование) распределяет данные по нескольким серверам:

```
Без шардирования:
Server 1: users = [1, 2, 3, ..., 100M]

С шардированием (по user_id % 4):
Shard 0: users с user_id % 4 = 0: [4, 8, 12, ...]
Shard 1: users с user_id % 4 = 1: [1, 5, 9, ...]
Shard 2: users с user_id % 4 = 2: [2, 6, 10, ...]
Shard 3: users с user_id % 4 = 3: [3, 7, 11, ...]
```

### 4.2 Выбор шардирующего ключа

**Shard key** — критическое архитектурное решение. Требования:
- Высокая кардинальность (много значений) → равномерное распределение
- Запросы часто фильтруют по этому ключу → избегаем cross-shard queries
- Значение не меняется (иначе нужно перемещать данные)

Хорошие ключи: `user_id`, `tenant_id`, `order_id`  
Плохие ключи: `status` (мало значений), `created_at` (hotspot на новом времени)

### 4.3 Consistent Hashing

Простой `hash(key) % N` проблематичен: при добавлении/удалении шарда — перераспределение 75-100% данных.

Consistent hashing: шарды и ключи размещаются на «кольце» хэшей. При добавлении шарда — перераспределяется только 1/N данных:

```python
import hashlib
from sortedcontainers import SortedDict

class ConsistentHashRing:
    def __init__(self, replicas: int = 150):
        self.replicas = replicas
        self.ring: SortedDict = SortedDict()
        self.nodes = set()
    
    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node: str):
        """Добавить шард в кольцо."""
        self.nodes.add(node)
        for i in range(self.replicas):
            virtual_node = f"{node}#{i}"
            self.ring[self._hash(virtual_node)] = node
    
    def remove_node(self, node: str):
        """Удалить шард (данные нужно перенести!)."""
        self.nodes.discard(node)
        for i in range(self.replicas):
            virtual_node = f"{node}#{i}"
            h = self._hash(virtual_node)
            if h in self.ring:
                del self.ring[h]
    
    def get_node(self, key: str) -> str:
        """Найти шард для ключа."""
        if not self.ring:
            raise ValueError("No nodes in ring")
        
        h = self._hash(key)
        # Находим ближайший узел по часовой стрелке
        idx = self.ring.bisect_right(h)
        if idx == len(self.ring):
            idx = 0  # Wrap around
        
        return self.ring.peekitem(idx)[1]

# Использование:
ring = ConsistentHashRing(replicas=150)
ring.add_node("shard-1")
ring.add_node("shard-2")
ring.add_node("shard-3")

# Распределение ключей:
for user_id in [1, 42, 100, 999, 12345]:
    shard = ring.get_node(str(user_id))
    print(f"user_id={user_id} → {shard}")
```

### 4.4 Citus — шардирование PostgreSQL

Citus — расширение PostgreSQL, превращающее его в distributed SQL:

```sql
-- Установка Citus (managed или self-hosted):
CREATE EXTENSION citus;

-- Добавить worker nodes:
SELECT citus_add_node('worker-1', 5432);
SELECT citus_add_node('worker-2', 5432);
SELECT citus_add_node('worker-3', 5432);

-- Создать шардированную таблицу:
CREATE TABLE orders (
    id         BIGINT,
    user_id    BIGINT NOT NULL,
    total      DECIMAL(10,2),
    created_at TIMESTAMP
);

-- Распределить по user_id (shard key):
SELECT create_distributed_table('orders', 'user_id');
-- Автоматически создаёт 32 shard'а на worker'ах

-- Запросы работают прозрачно:
SELECT * FROM orders WHERE user_id = 42;
-- Citus роутит запрос на нужный shard

-- Cross-shard query (медленнее, но работает):
SELECT COUNT(*), SUM(total) FROM orders 
WHERE created_at > NOW() - INTERVAL '30 days';
-- Citus выполняет на всех shards и агрегирует результат

-- Статус шардов:
SELECT * FROM citus_shards;
```

### 4.5 Vitess — шардирование MySQL (Kubernetes-native)

Vitess (от YouTube, 2011) — solution для шардирования MySQL:

```yaml
# Vitess VSchema (определение шардирования):
{
  "keyspaces": {
    "main": {
      "sharded": true,
      "vindexes": {
        "hash": {
          "type": "hash"
        }
      },
      "tables": {
        "orders": {
          "column_vindexes": [
            {
              "column": "user_id",
              "name": "hash"
            }
          ]
        }
      }
    }
  }
}
```

```python
# Подключение к Vitess через стандартный MySQL клиент:
import pymysql

conn = pymysql.connect(
    host='vtgate',  # Vitess gateway
    port=3306,
    user='app',
    password='secret',
    database='main@master'  # @master = primary shard
)

with conn.cursor() as cur:
    # Vitess роутит автоматически:
    cur.execute("SELECT * FROM orders WHERE user_id = %s", (42,))
    rows = cur.fetchall()
```

---

## 5. Проблемы шардирования

### 5.1 Cross-Shard Queries

```sql
-- Простой запрос (один шард):
SELECT * FROM orders WHERE user_id = 42;  -- Только shard-1

-- Cross-shard (медленно):
SELECT COUNT(*) FROM orders WHERE status = 'pending';  -- Все шарды!
-- Нужно опросить все шарды и агрегировать → overhead

-- Решение: денормализация, сводные таблицы, precomputed aggregates
```

### 5.2 Distributed Transactions

```sql
-- Перевод денег между пользователями на разных шардах:
-- User 1 (shard-1): -$100
-- User 2 (shard-3): +$100

-- Проблема: ACID транзакция через несколько шардов требует 2PC
-- 2PC медленный и блокирующий
-- Решение: Saga pattern, eventual consistency (см. главу про Saga)
```

### 5.3 Resharding

При добавлении шарда или неравномерном распределении нужен resharding:

```
Было: 4 шарда
Стало: 8 шардов

Consistent hashing: перемещается ~50% данных с 4 на 8 новых шардов
(не 100% как в naive hash)

Реализация: фоновое копирование + двойная запись
1. Новые данные пишем в старый и новый шард
2. Копируем исторические данные
3. Переключаем на новый шард
```

---

## 6. Мониторинг репликации

```python
import psycopg2

def check_replication_lag(primary_dsn: str, standby_dsn: str) -> dict:
    """Мониторинг lag репликации."""
    
    # На primary: проверяем connected standbys
    with psycopg2.connect(primary_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    application_name,
                    client_addr,
                    state,
                    replay_lag,
                    pg_wal_lsn_diff(sent_lsn, replay_lsn) AS bytes_behind
                FROM pg_stat_replication
            """)
            standbys = cur.fetchall()
    
    # На standby: проверяем lag
    with psycopg2.connect(standby_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    pg_is_in_recovery() AS is_replica,
                    EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds,
                    pg_last_wal_receive_lsn() AS receive_lsn,
                    pg_last_wal_replay_lsn() AS replay_lsn
            """)
            standby_info = cur.fetchone()
    
    return {
        'standbys': standbys,
        'lag_seconds': standby_info[1],
        'is_replica': standby_info[0]
    }
```

---

## Заключение

WAL, репликация и шардирование — три уровня масштабирования PostgreSQL: надёжность через WAL, доступность через репликацию, масштабирование записи через шардирование.

**Ключевые выводы**:

1. **WAL** гарантирует durability: сначала журнал (sequential write), потом данные. При сбое — replay WAL от последнего checkpoint.

2. **Физическая репликация** — точная копия binary на уровне страниц. Быстро, просто, только для PostgreSQL той же версии.

3. **Логическая репликация** — передача SQL-level изменений. Гибко (фильтрация, разные версии), сложнее настроить.

4. **Шардирование** нужно только когда вертикальное масштабирование исчерпано. Выбор shard key — критическое решение.

5. **Consistent hashing** минимизирует перераспределение данных при добавлении/удалении шардов.

---

## Литература и источники

1. PostgreSQL Documentation. Write Ahead Logging (WAL). https://www.postgresql.org/docs/current/wal.html
2. PostgreSQL Documentation. High Availability, Load Balancing, and Replication. https://www.postgresql.org/docs/current/high-availability.html
3. PostgreSQL Documentation. Logical Replication. https://www.postgresql.org/docs/current/logical-replication.html
4. Citus Data. Citus Documentation. https://docs.citusdata.com/
5. Vitess Documentation. https://vitess.io/docs/
6. DeCandia, G. et al. (2007). Dynamo: Amazon's Highly Available Key-Value Store. *SOSP 2007*.
7. Karger, D. et al. (1997). Consistent Hashing and Random Trees. *STOC 1997*.
8. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly. Chapter 6: Partitioning.
9. Mohan, C. et al. (1992). ARIES: A Transaction Recovery Method. *ACM TODS*, 17(1).
10. Wikipedia. Write-ahead logging. https://en.wikipedia.org/wiki/Write-ahead_logging
