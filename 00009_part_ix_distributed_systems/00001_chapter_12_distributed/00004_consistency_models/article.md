# Модели согласованности: от линеаризуемости до eventual consistency

Когда несколько пользователей одновременно читают и пишут данные в распределённой системе, возникает фундаментальный вопрос: что они видят? Всегда ли читатель видит последнюю запись? Видят ли два читателя одно и то же? Может ли система показывать «старые» данные? Ответы на эти вопросы формируют **модель согласованности** — контракт между системой и её пользователями о том, как выглядят данные.

Моделей согласованности много, они образуют иерархию от самой строгой (linearizability) до самой слабой (eventual consistency). Выбор модели — это компромисс между корректностью, производительностью и доступностью, закреплённый теоремой CAP.

## Зачем нужны модели согласованности

Представьте банковский счёт. Алиса имеет $100 и снимает $50. Одновременно Боб читает баланс на другом узле. Что он увидит? Это зависит от модели:

- **Строгая согласованность**: Боб видит либо $100 (до снятия), либо $50 (после). Никакого промежуточного состояния.
- **Последовательная согласованность**: все наблюдают операции в одном и том же порядке, но не обязательно в реальном времени.
- **Слабая/eventual согласованность**: Боб может на секунду увидеть $100, потом обновление дойдёт до его узла.

В монолитном приложении с одной базой данных это тривиально. В распределённой системе с репликацией — нет. Когда мастер-узел получает запись и сразу отвечает клиенту, реплики ещё не обновились. Если читатель идёт на реплику — он видит старые данные.

## Теорема CAP и её интерпретация

Эрик Брюэр в 2000 году сформулировал (и Гилберт с Линчем в 2002 году доказали) теорему CAP: в присутствии сетевого раздела (Network Partition) система не может одновременно обеспечить Consistency и Availability.

- **C (Consistency)** — каждое чтение видит последнюю запись или ошибку (по сути, линеаризуемость)
- **A (Availability)** — каждый запрос получает ответ (не ошибку), пусть и не самый свежий
- **P (Partition tolerance)** — система продолжает работать при разрыве сети между узлами

Поскольку сетевые разделы в реальных распределённых системах неизбежны (P нельзя отключить), выбор стоит между CP и AP:
- **CP**: при разделе отвергаем запросы или возвращаем ошибку (выбираем согласованность)
- **AP**: при разделе отвечаем, пусть и устаревшими данными (выбираем доступность)

```
Примеры систем:
CP: HBase, Zookeeper, etcd, Spanner
AP: Cassandra, DynamoDB, CouchDB, Riak
```

Однако CAP — упрощение. Реальность богаче: «согласованность» в CAP — конкретная (линеаризуемость), а не все модели; «доступность» означает ответ от любого живого узла; P не бинарное, а вопрос задержек и вероятностей. Более точная модель — **PACELC** (Abadi, 2012): даже без раздела существует компромисс между latency и consistency.

## Линеаризуемость (Linearizability)

Самая строгая модель для одиночных операций. Система линеаризуема, если каждая операция выглядит так, будто она выполнилась атомарно в некоторый момент между началом и концом вызова, и этот момент согласован для всех наблюдателей.

Иными словами: если операция A завершилась до начала операции B, то B видит результат A.

```
Временная шкала:
Клиент 1: [Write X=1]------|
Клиент 2:          [Read X] -> должен вернуть 1

Клиент 1: [Write X=1]
Клиент 2:    [Read X]  -> может вернуть 0 или 1 (перекрываются во времени)
```

Линеаризуемость эквивалентна атомарному регистру — самой простой абстракции параллельных вычислений. Она является основой для реализации более сложных примитивов: distributed lock, compare-and-swap, лидерных выборов.

```python
# Проверка линеаризуемости истории операций
from dataclasses import dataclass
from typing import List, Optional, Any
from itertools import permutations

@dataclass
class Operation:
    """Одна операция в истории."""
    client_id: str
    op_type: str      # 'write' или 'read'
    key: str
    value: Any        # для write — что писали, для read — что вернули
    start_time: float
    end_time: float

def check_linearizable(history: List[Operation]) -> bool:
    """
    Наивная проверка линеаризуемости за O(n! * n).
    На практике используется более эффективный алгоритм (Wing & Gong).
    """
    n = len(history)
    
    # Пробуем все возможные линейные упорядочивания
    for perm in permutations(range(n)):
        # Проверяем, что порядок совместим с real-time порядком
        valid_order = True
        for i in range(n):
            for j in range(i + 1, n):
                op_i = history[perm[i]]
                op_j = history[perm[j]]
                # Если op_i закончилась до начала op_j, op_j не может быть раньше
                if op_i.end_time < op_j.start_time:
                    if perm.index(history.index(op_i)) > perm.index(history.index(op_j)):
                        valid_order = False
                        break
            if not valid_order:
                break
        
        if not valid_order:
            continue
        
        # Проверяем семантику: read должен видеть последний write в этом порядке
        state = {}
        semantically_valid = True
        for idx in perm:
            op = history[idx]
            if op.op_type == 'write':
                state[op.key] = op.value
            elif op.op_type == 'read':
                expected = state.get(op.key)
                if op.value != expected:
                    semantically_valid = False
                    break
        
        if semantically_valid:
            return True
    
    return False
```

**Реализация**: достигается через consensus-протоколы (Paxos, Raft). Zookeeper, etcd, Consul предоставляют линеаризуемые операции. PostgreSQL с synchronous_commit=on и репликацией тоже линеаризуем.

**Цена**: высокая задержка (RTT для записи на кворум) и недоступность при сетевом разделе.

## Последовательная согласованность (Sequential Consistency)

Слабее линеаризуемости: операции можно переставить, пока каждый клиент видит свои операции в порядке выдачи, и все клиенты видят одну и ту же «историю».

Ключевое отличие от линеаризуемости: нет привязки к реальному времени. Если клиент 1 написал X=1 и закончил раньше, чем клиент 2 начал читать X, последовательная согласованность всё равно может вернуть X=0 (если реплика ещё не обновилась). Линеаризуемость это запрещает.

```
Пример нарушения линеаризуемости, но соблюдения sequential consistency:

Реальное время:
P1: Write(x, 1) ----
P2:               ---- Read(x) → 0  // нарушает linearizability!

Но если все узлы согласны, что операции шли в порядке [Read(x), Write(x,1)],
это sequential consistency: P2 прочитал до записи в «логическом» порядке.
```

Последовательную согласованность сложно обеспечить эффективно в распределённых системах. На практике её часто заменяют линеаризуемостью (строже, но понятнее) или причинной согласованностью (слабее, но эффективнее).

## Причинная согласованность (Causal Consistency)

Ещё слабее: система гарантирует только, что причинно-связанные операции видны всем в правильном порядке. Конкурентные операции могут наблюдаться в разном порядке разными клиентами.

Это именно то, что отслеживают векторные часы из предыдущей главы.

```python
class CausallyConsistentStore:
    """
    Упрощённая демонстрация causally consistent хранилища.
    Каждая запись несёт свой вектор зависимостей.
    """
    def __init__(self, node_id: str, nodes: list):
        self.node_id = node_id
        self.nodes = nodes
        self.data = {}
        self.version_vector = {n: 0 for n in nodes}
        self.pending_writes = []  # ждём зависимостей
    
    def write(self, key: str, value, dependencies: dict = None):
        """Запись с явным указанием зависимостей."""
        self.version_vector[self.node_id] += 1
        write_vc = dict(self.version_vector)
        
        record = {
            'key': key,
            'value': value,
            'vc': write_vc,
            'deps': dependencies or {}
        }
        self.data[key] = record
        return write_vc
    
    def receive_write(self, record: dict):
        """Получить запись с другого узла."""
        # Применяем только если все зависимости уже видны
        if self._deps_satisfied(record['deps']):
            self._apply_write(record)
            # Попробуем применить ожидающие записи
            self._process_pending()
        else:
            self.pending_writes.append(record)
    
    def _deps_satisfied(self, deps: dict) -> bool:
        """Проверить, видели ли мы все зависимости."""
        return all(
            self.version_vector.get(node, 0) >= count
            for node, count in deps.items()
        )
    
    def _apply_write(self, record: dict):
        """Применить запись и обновить вектор."""
        self.data[record['key']] = record
        for node, count in record['vc'].items():
            self.version_vector[node] = max(
                self.version_vector.get(node, 0), count
            )
    
    def _process_pending(self):
        """Обработать записи, чьи зависимости теперь выполнены."""
        changed = True
        while changed:
            changed = False
            still_pending = []
            for record in self.pending_writes:
                if self._deps_satisfied(record['deps']):
                    self._apply_write(record)
                    changed = True
                else:
                    still_pending.append(record)
            self.pending_writes = still_pending
    
    def read(self, key: str):
        record = self.data.get(key)
        return record['value'] if record else None
```

MongoDB с readConcern "majority" обеспечивает что-то близкое к причинной согласованности. CosmosDB явно предлагает «Consistent Prefix» и «Session» уровни, которые приближаются к причинной.

## Монотонное чтение (Monotonic Reads)

Более слабая гарантия: если клиент прочитал значение X=v, он никогда не прочитает более старое значение (X=v', где v' было записано раньше v).

Кажется очевидным, но в системах с репликацией нарушается легко: если клиент читает с реплики A (которая обновилась), а потом с реплики B (которая отстаёт) — он увидит «откат».

```python
class MonotonicReadSession:
    """
    Обеспечивает монотонное чтение через sticky sessions.
    Клиент всегда читает с одного узла (или с узла, который видел
    хотя бы то же самое, что мы уже видели).
    """
    def __init__(self):
        self.read_version = {}  # key -> min version we've seen
    
    def read(self, key: str, replicas: list):
        min_version = self.read_version.get(key, 0)
        
        # Найти реплику, которая видела хотя бы min_version
        for replica in replicas:
            version, value = replica.read(key)
            if version >= min_version:
                self.read_version[key] = version
                return value
        
        # Нет подходящей реплики — вернуть ошибку или заблокироваться
        raise Exception(f"No replica has version >= {min_version} for {key}")
```

## Read-Your-Writes (Read-My-Writes)

Гарантия: клиент всегда видит свои собственные записи. Если я записал X=1, моё следующее чтение X вернёт как минимум 1.

Нарушается, если: я пишу на мастер, читаю с реплики, реплика ещё не синхронизировалась.

Типичные решения:
1. **Sticky routing**: клиент читает с того же узла, куда писал
2. **Version tracking**: клиент помнит версию своей последней записи, читает только с реплик, которые её видели
3. **Read from primary**: всегда читать с мастера (дорого)

```python
class ReadYourWritesSession:
    def __init__(self, client_id: str, db_cluster):
        self.client_id = client_id
        self.cluster = db_cluster
        self.my_writes = {}  # key -> timestamp of my last write
    
    def write(self, key: str, value):
        timestamp = self.cluster.write(key, value)
        self.my_writes[key] = timestamp
        return timestamp
    
    def read(self, key: str):
        min_ts = self.my_writes.get(key, 0)
        
        if min_ts == 0:
            # Я не писал этот ключ — читаю с любой реплики
            return self.cluster.read_any(key)
        else:
            # Жду, пока реплика увидит мою запись
            return self.cluster.read_after(key, min_ts)
```

## Eventual Consistency (Согласованность в конечном счёте)

Самая слабая гарантия из рассматриваемых: если прекратятся все обновления, в конечном счёте все реплики сойдутся к одному значению. Когда — не гарантируется.

Это звучит слабо, но для многих приложений достаточно. Счётчик просмотров видео, профиль пользователя, настройки приложения — небольшая «отсталость» реплик некритична.

```python
import time
import random
from threading import Thread, Lock
from collections import defaultdict

class EventuallyConsistentStore:
    """
    Симуляция eventual consistency:
    - Записи применяются локально сразу
    - Синхронизация с другими узлами асинхронна
    - Конфликты разрешаются через last-writer-wins (LWW)
    """
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.data = {}          # key -> (value, timestamp)
        self.lock = Lock()
        self.peers = []
        self._running = True
        
        # Фоновый поток синхронизации
        Thread(target=self._gossip, daemon=True).start()
    
    def write(self, key: str, value) -> float:
        """Запись — немедленно применяется локально."""
        ts = time.time()
        with self.lock:
            current = self.data.get(key)
            if current is None or current[1] < ts:
                self.data[key] = (value, ts)
        return ts
    
    def read(self, key: str):
        """Чтение — возвращает текущее (возможно, устаревшее) значение."""
        with self.lock:
            record = self.data.get(key)
        return record[0] if record else None
    
    def _apply_remote(self, key: str, value, timestamp: float):
        """Применить обновление от другого узла — LWW."""
        with self.lock:
            current = self.data.get(key)
            if current is None or current[1] < timestamp:
                self.data[key] = (value, timestamp)
    
    def _gossip(self):
        """Периодически синхронизироваться с соседями."""
        while self._running:
            time.sleep(random.uniform(0.1, 0.5))  # случайная задержка
            if self.peers:
                peer = random.choice(self.peers)
                with self.lock:
                    snapshot = dict(self.data)
                # Отправляем весь снапшот (на практике — дельта)
                for key, (value, ts) in snapshot.items():
                    peer._apply_remote(key, value, ts)
```

**Проблемы eventual consistency**:
- **Последовательность обновлений**: операции A потом B на одном узле могут дойти до другого как B, A
- **Phantom reads**: клиент видит объект, которого на его реплике уже нет (удалён)
- **Zombie tombstones**: удалённые записи нельзя сразу убрать — нужно хранить «надгробие» (tombstone)

## Модели согласованности баз данных

В контексте транзакций используется другая терминология, основанная на аномалиях SQL:

```
Уровни изоляции ANSI SQL (от слабого к строгому):
  Read Uncommitted — видим незафиксированные данные (dirty reads)
  Read Committed   — видим только зафиксированные (no dirty reads)
  Repeatable Read  — одно чтение одного ряда всегда одинаково
  Serializable     — транзакции эквивалентны последовательному выполнению
```

Но ANSI SQL не охватывает все аномалии. Адья (Adi Adya) в 1999 году формализовал более полный список:

- **Dirty Write**: транзакция перезаписывает незафиксированные данные другой транзакции
- **Dirty Read**: читаем незафиксированные данные
- **Non-repeatable Read / Fuzzy Read**: два чтения одной строки дают разные результаты
- **Phantom Read**: повторный диапазонный запрос возвращает другие строки
- **Lost Update**: два concurrent update, один перезаписывает другой незаметно
- **Write Skew**: две транзакции читают одни данные, пишут в разные, нарушая инвариант

```python
# Демонстрация write skew
# Инвариант: total(A) + total(B) >= 0

# PostgreSQL с Repeatable Read НЕ защищает от write skew!
# Нужен Serializable или ручная блокировка

# Пример: врачи на дежурстве (нужен хотя бы один)
# Транзакция 1 (врач A): видит A=on, B=on → выходит A=off
# Транзакция 2 (врач B): видит A=on, B=on → выходит B=off
# Результат: оба ушли, никого нет — нарушение инварианта!

def demonstrate_write_skew(db):
    def doctor_go_off_duty(doctor_id):
        with db.transaction(isolation='repeatable_read') as tx:
            # Проверяем: есть ли другой дежурный врач?
            other_on_duty = tx.query(
                "SELECT COUNT(*) FROM doctors WHERE on_call=true AND id != ?",
                doctor_id
            )
            if other_on_duty > 0:
                # Можно уходить
                tx.execute(
                    "UPDATE doctors SET on_call=false WHERE id=?",
                    doctor_id
                )
    
    # Обе транзакции выполняются concurrently — write skew!
    # Защита: serializable isolation или SELECT FOR UPDATE на всех дежурных
```

## Snapshot Isolation и MVCC

Большинство современных БД (PostgreSQL, MySQL InnoDB, Oracle, SQL Server) реализуют **Snapshot Isolation** через MVCC (Multi-Version Concurrency Control). Каждая транзакция видит согласованный снапшот данных на момент начала транзакции.

```
Временная шкала:
T=100: Begin TX1 (snapshot @ T=100)
T=101: TX2 writes Row X = "new"
T=102: TX2 commits
T=103: TX1 reads Row X → видит "old" (snapshot @ T=100!)
T=104: TX1 commits
```

MVCC позволяет читателям не блокировать писателей и наоборот. Но требует очистки старых версий (vacuum в PostgreSQL).

```python
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

@dataclass
class Version:
    value: any
    created_at: int   # transaction id создавший версию
    deleted_at: Optional[int]  # transaction id удаливший, None если жива

class MVCCStore:
    def __init__(self):
        self.data: Dict[str, List[Version]] = {}
        self.tx_counter = 0
        self.active_transactions: Dict[int, int] = {}  # tx_id -> snapshot_ts
    
    def begin(self) -> int:
        """Начать транзакцию, получить snapshot timestamp."""
        self.tx_counter += 1
        tx_id = self.tx_counter
        # Snapshot: видим всё зафиксированное до этого момента
        self.active_transactions[tx_id] = tx_id
        return tx_id
    
    def write(self, tx_id: int, key: str, value):
        """Записать новую версию."""
        if key not in self.data:
            self.data[key] = []
        
        # Помечаем старую версию как удалённую
        for version in self.data[key]:
            if version.deleted_at is None:
                version.deleted_at = tx_id
        
        self.data[key].append(Version(value, tx_id, None))
    
    def read(self, tx_id: int, key: str) -> Optional[any]:
        """Читать версию, видимую на момент snapshot."""
        snapshot_ts = self.active_transactions.get(tx_id, tx_id)
        versions = self.data.get(key, [])
        
        # Ищем версию, созданную до snapshot и не удалённую до snapshot
        for version in reversed(versions):
            if version.created_at <= snapshot_ts:
                if version.deleted_at is None or version.deleted_at > snapshot_ts:
                    return version.value
        return None
    
    def commit(self, tx_id: int):
        """Зафиксировать транзакцию."""
        self.active_transactions.pop(tx_id, None)
    
    def vacuum(self, oldest_active_tx: int):
        """Удалить версии, невидимые ни одной активной транзакции."""
        for key in self.data:
            self.data[key] = [
                v for v in self.data[key]
                if v.deleted_at is None or v.deleted_at > oldest_active_tx
            ]
```

## Согласованность в NewSQL и распределённых базах

Современные распределённые базы предлагают разные уровни:

**Google Spanner**: внешняя согласованность (external consistency) — строже линеаризуемости для транзакций. Глобально сериализуемые транзакции.

**CockroachDB**: сериализуемая изоляция через hybrid logical clocks + Raft. Serializable by default.

**Amazon Aurora**: в single-region — linearizable для replica lag < RPO. Multi-region — eventual consistency для cross-region реплик.

**MongoDB**: с версии 4.0 поддерживает multi-document ACID транзакции. ReadConcern "majority" + WriteConcern "majority" = линеаризуемость.

```python
# Уровни согласованности MongoDB
from pymongo import MongoClient, ReadPreference
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

client = MongoClient("mongodb://...")
db = client.mydb

# Linearizable reads (самый строгий)
collection = db.get_collection(
    "orders",
    read_preference=ReadPreference.PRIMARY,
    read_concern=ReadConcern("linearizable"),
    write_concern=WriteConcern("majority")
)

# Eventual consistency (самый быстрый, но может читать устаревшее)
collection_fast = db.get_collection(
    "analytics",
    read_preference=ReadPreference.SECONDARY,
    read_concern=ReadConcern("local"),
    write_concern=WriteConcern(1)
)
```

## Практические рекомендации

**Когда нужна строгая согласованность (linearizability):**
- Финансовые операции, балансы счетов
- Distributed locks, leader election
- Генерация уникальных последовательных ID
- Inventory management (не допускать oversell)

Инструменты: etcd, Zookeeper, Consul, PostgreSQL с sync replication, Spanner.

**Когда достаточно причинной согласованности:**
- Комментарии к посту (ответы всегда после родительского комментария)
- Сессии пользователей (все операции одного пользователя упорядочены)
- Версионирование конфигурации

Инструменты: MongoDB с causal sessions, систематическое использование векторных часов.

**Когда достаточно eventual consistency:**
- Счётчики просмотров, лайков
- Полнотекстовый поиск
- Аналитические витрины данных
- DNS-записи
- CDN кэширование

Инструменты: Cassandra, DynamoDB, Redis с async replication.

**Ловушки:**
1. **Не путайте уровни изоляции транзакций с моделями согласованности** — это два ортогональных измерения. Serializable isolation $\neq$ linearizability.
2. **Read-your-writes не гарантирует read-your-writes для другого клиента** — это per-session гарантия.
3. **Eventual consistency без дополнительных гарантий опасна** — добавляйте monotonic reads и read-your-writes как минимум.
4. **Не все CRDTs безопасны** — логика разрешения конфликтов должна быть семантически корректной для вашего приложения.

## Иерархия моделей согласованности

```
Строже ─────────────────────────────────── Слабее

Strict Serializability (Linearizable + Serializable)
        |
   Linearizability ──── Sequential Consistency
        |                       |
   Causal Consistency          |
        |                       |
   PRAM (Pipeline)             |
        |                       |
   Read-Your-Writes            |
        |                       |
   Monotonic Reads             |
        |                       |
   Eventual Consistency ────────┘
```

Верхние уровни дают разработчику больше гарантий, но стоят дороже в latency и availability. Нижние — дешевле, но требуют от разработчика больше внимания к race conditions и корректности.

## Заключение

Не существует «лучшей» модели согласованности — существует правильная для конкретного случая. Линеаризуемость покупается ценой задержки и сниженной доступности при сетевых разделах. Eventual consistency быстра и доступна, но переносит сложность разрешения конфликтов на разработчика или систему.

Понимание этих компромиссов критично при выборе базы данных, проектировании API, и отладке тонких проблем с данными. Многие «мистические» баги в распределённых системах — это нарушения ожидаемой модели согласованности, которые разработчик не осознавал явно.

## Литература

1. Gilbert, S., Lynch, N. (2002). **Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services**. *ACM SIGACT News*, 33(2).
2. Adya, A. (1999). **Weak Consistency: A Generalized Theory and Optimistic Implementations for Distributed Transactions**. PhD Thesis, MIT.
3. Herlihy, M., Wing, J. (1990). **Linearizability: A Correctness Condition for Concurrent Objects**. *ACM TOPLAS*, 12(3), 463–492.
4. Lamport, L. (1979). **How to Make a Multiprocessor Computer That Correctly Executes Multiprocess Programs**. *IEEE Transactions on Computers*, C-28(9).
5. Vogels, W. (2009). **Eventually Consistent**. *Communications of the ACM*, 52(1), 40–44.
6. Abadi, D. (2012). **Consistency Tradeoffs in Modern Distributed Database System Design: CAP is Only Part of the Story**. *IEEE Computer*, 45(2).
7. Corbett, J., et al. (2013). **Spanner: Google's Globally Distributed Database**. *ACM TODS*.
8. Bernstein, P., Newcomer, E. (2009). **Principles of Transaction Processing**, 2nd ed. Morgan Kaufmann.
9. Kleppmann, M. (2017). **Designing Data-Intensive Applications**. O'Reilly. Chapters 5, 7, 9.
10. Jepsen (2023). **Consistency Models** [online]. https://jepsen.io/consistency
