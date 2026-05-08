# CAP, PACELC и FLP: фундаментальные ограничения распределённых систем

Иногда в Computer Science появляются результаты, которые доказывают: некоторые вещи *невозможны* в принципе. Не сложно реализовать, не дорого — а именно невозможны математически. Это меняет то, как мы проектируем системы: вместо поиска идеального решения мы начинаем искать правильный компромисс.

В этой статье — три таких фундаментальных ограничения. CAP-теорема говорит, что нельзя иметь всё в распределённой системе при разделении сети. PACELC уточняет: даже без разделения приходится выбирать. FLP доказывает, что в асинхронной сети с единственным отказавшим узлом консенсус математически невозможен.

## CAP-теорема

### История

В 2000 году Эрик Брюер (Eric Brewer) из UC Berkeley сформулировал гипотезу на конференции PODC. В 2002 году Сет Гилберт и Нэнси Линч из MIT дали строгое математическое доказательство. Теорема стала одной из самых известных в области распределённых систем.

**Теорема**: в распределённой системе нельзя одновременно гарантировать все три свойства:
- **C** — Consistency (Согласованность)
- **A** — Availability (Доступность)
- **P** — Partition tolerance (Устойчивость к разделению)

### Три свойства

**Согласованность (Consistency)**: каждое чтение возвращает последнюю запись или ошибку. Это не согласованность транзакций ACID — это линеаризуемость: система ведёт себя как если бы операции выполнялись на одном узле в строгом порядке.

```
Узел A: write(x=1)
Узел B: read(x) → должно вернуть 1 (а не старое значение)
```

**Доступность (Availability)**: каждый запрос получает ответ (не ошибку) — хотя не гарантированно актуальные данные.

**Устойчивость к разделению (Partition tolerance)**: система продолжает работать даже если сеть между узлами разорвана (partition).

### Почему P нельзя отказаться

В реальных сетях разделения (partitions) случаются: кабель обрывается, коммутатор перегружается, датацентр теряет связность. **Разработчик не контролирует сеть**.

Значит, отказ от P — это иллюзия. В распределённой системе P всегда должна быть обеспечена. Реальный выбор:

**При возникновении partition: C или A?**

```
Сценарий: два узла (A и B) потеряли связь

Узел A: write(x=1)          Узел B: ещё не получил обновление
        ...partition...
        read(x) на B возвращает ?

Если C: B отвечает ошибкой "не могу гарантировать актуальность"
        (отказываемся от Availability)

Если A: B отвечает x=0 (старое значение)
        (отказываемся от Consistency)
```

### CP-системы

CP-системы жертвуют доступностью ради согласованности. При partition они отказывают обслуживать запросы, если не могут гарантировать актуальность.

**ZooKeeper**: при partition leader изолирован от кворума — ZooKeeper перестаёт отвечать на записи до восстановления связи.

**etcd**: ключ-значение хранилище для Kubernetes. При partition: запросы на запись блокируются, пока не восстановится кворум.

**HBase, Spanner**: базы с сильной согласованностью.

```python
# ZooKeeper: при partition клиент получает исключение
import kazoo.client

zk = kazoo.client.KazooClient(hosts="zk1:2181,zk2:2181,zk3:2181")
try:
    zk.ensure_path("/config")
    zk.set("/config/feature_flag", b"enabled")
except kazoo.exceptions.ConnectionLoss:
    # Partition! Запрос не выполнен — лучше ошибка, чем неактуальные данные
    logger.error("ZooKeeper unavailable during partition")
    raise ServiceUnavailableError()
```

### AP-системы

AP-системы жертвуют согласованностью ради доступности. При partition они продолжают обслуживать запросы, но могут вернуть устаревшие данные.

**Cassandra**: каждый узел может принять запись независимо. При partition данные рассинхронизируются, но система работает. После восстановления — **eventual consistency** (в конечном счёте согласованность).

**DynamoDB**: настраиваемая согласованность. По умолчанию — eventually consistent (быстро). По запросу — strongly consistent (медленнее).

**DNS**: AP-система. Обновление DNS может занять часы, но DNS никогда не падает из-за partition.

```python
# DynamoDB: выбор уровня согласованности
import boto3

dynamo = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamo.Table("users")

# AP: быстро, но может вернуть устаревшее
response = table.get_item(
    Key={"user_id": "123"},
    ConsistentRead=False  # Eventual consistency (default)
)

# CP: медленнее, всегда актуально
response = table.get_item(
    Key={"user_id": "123"},
    ConsistentRead=True   # Strong consistency
)
```

### Nuances: теорема шире, чем кажется

Брюер впоследствии признал, что CAP был "чрезмерно упрощён". Настоящая реальность:

1. **Partition — редкость, не норма**: большинство времени сеть работает. CAP ничего не говорит о поведении в нормальных условиях.

2. **Согласованность — спектр**: существуют модели слабее линеаризуемости но сильнее eventual consistency (causal consistency, session consistency).

3. **Доступность — не бинарна**: система может отвечать с деградированной функциональностью.

4. **"2 из 3" вводит в заблуждение**: реальный выбор только при partition.

Именно для заполнения этих пробелов создали PACELC.

## PACELC: полная картина

В 2012 году Даниэль Абади (Daniel Abadi) из Yale предложил расширение: **PACELC**.

```
Если Partition:
  выбор между Availability и Consistency
Else (нет partition):
  выбор между Latency и Consistency
```

Это более реалистичная модель: даже без partition есть компромисс. Чтобы гарантировать согласованность, нужно координировать узлы — это добавляет задержку.

### Квадранты PACELC

| Система | При Partition | Без Partition | Итог |
|---------|--------------|---------------|------|
| Cassandra | Availability | Latency | PA/EL |
| DynamoDB (default) | Availability | Latency | PA/EL |
| MongoDB (default) | Availability | Consistency | PA/EC |
| Spanner | Consistency | Consistency | PC/EC |
| Zookeeper | Consistency | Consistency | PC/EC |
| CRDT | Availability | Latency | PA/EL |

**PA/EL системы**: приоритет доступности и скорости. Для большинства социальных сетей, счётчиков, корзин покупок.

**PC/EC системы**: приоритет корректности. Для финансовых транзакций, систем координации.

### Настройка согласованности в Cassandra

Cassandra — PA/EL по умолчанию, но позволяет настроить "уровень кворума":

```python
from cassandra.cluster import Cluster
from cassandra.policies import ConsistencyLevel
from cassandra import ConsistencyLevel as CL

cluster = Cluster(["cassandra1", "cassandra2", "cassandra3"])
session = cluster.connect("my_keyspace")

# Eventual Consistency: запись на 1 узел, быстро, AP
session.default_consistency_level = CL.ONE

# Strong Consistency: кворум (N/2+1 узлов), медленнее, CP
session.default_consistency_level = CL.QUORUM

# Maximum Consistency: все узлы, медленно
session.default_consistency_level = CL.ALL

# Запись с кворумом + чтение с кворумом = strong consistency
# Правило: write_consistency + read_consistency > replication_factor
insert = session.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
insert.consistency_level = CL.QUORUM
session.execute(insert, (user_id, name))
```

### Causal Consistency: золотая середина

Между eventual и strong consistency есть промежуточная модель — **causal consistency**: операции сохраняют причинно-следственную связь.

```
Иван: write(post="Hello")
Мария: read(post="Hello") → write(comment="Hi Ivan!")
Пётр: должен увидеть post ДО comment (причинно-следственная связь)
```

Amazon DynamoDB Transactions, MongoDB Causal Consistency, CockroachDB — используют различные варианты.

## FLP-невозможность

### Проблема консенсуса

**Консенсус** — это задача: несколько узлов должны договориться об одном значении.

Требования:
1. **Завершение (Termination)**: каждый правильный узел в конечном счёте принимает решение
2. **Соглашение (Agreement)**: все правильные узлы принимают одинаковое решение
3. **Валидность (Validity)**: принятое значение было предложено кем-то из узлов

Консенсус критичен для: выборов лидера в кластере, транзакций, координированного деплоя.

### Теорема FLP

В 1985 году Фишер, Линч и Патерсон (Fischer, Lynch, Patterson) доказали теорему в статье "Impossibility of Distributed Consensus with One Faulty Process":

**В полностью асинхронной сети нельзя достичь консенсуса, если хотя бы один процесс может отказать.**

Это поразило сообщество: казалось, что это просто инженерная задача — поставить больше узлов, лучшие алгоритмы. Оказалось — математически невозможно.

### Почему это так

Интуиция: в асинхронной сети нельзя отличить **медленный процесс** от **упавшего**.

```
Узел A отправляет запрос узлу B.
Ответа нет.

Варианты:
  1. B упал → нужно принять решение без B
  2. B просто медленный → нужно подождать B

Мы не можем знать, который из вариантов верен.
```

Если ждём бесконечно — нарушаем Termination (никогда не принимаем решение).
Если не ждём — рискуем нарушить Agreement (если B жив и ответит позже с другим мнением).

### Обход FLP: что делают реальные системы

FLP говорит о *полностью* асинхронных системах. На практике используют:

**1. Таймауты (Weakly Synchronous Model)**

Если у нас есть хоть какие-то временные предположения (timeout), то "асинхронность" нарушена, и FLP не применима строго.

```python
# Raft: лидер отправляет heartbeat каждые 150ms
# Если 300ms нет heartbeat — начинаем выборы (таймаут)
HEARTBEAT_INTERVAL = 0.150
ELECTION_TIMEOUT = random.uniform(0.3, 0.6)  # Randomized
```

**2. Randomization**

Если узел делает случайный выбор при неопределённости, теорема FLP тоже не применима (она про *детерминированные* алгоритмы).

**3. FLP не запрещает вероятностный консенсус**

Алгоритмы могут гарантировать: консенсус достигается с вероятностью 1 при определённых условиях.

### Алгоритмы консенсуса

#### Paxos

Разработан Лесли Лэмпортом (Leslie Lamport) в 1989 году (опубликован в 1998). Базовый алгоритм консенсуса.

```
Фазы Paxos:
  Phase 1 (Prepare):
    Proposer → все Acceptors: "Prepare(n=5)"  // n = номер предложения
    Acceptor → Proposer: "Promise(n=5, accepted=3, value='x')"
    // Обещаем не принимать предложения с n < 5
  
  Phase 2 (Accept):
    Proposer → Acceptors: "Accept(n=5, value='x')"
    Acceptors → Proposer: "Accepted(n=5)"
  
  Phase 3 (Learn):
    Proposer → Learners: "Decided(value='x')"
```

Paxos сложен в понимании и реализации ("кошмарно сложен" — слова самого Лэмпорта). Multi-Paxos (для серии решений) ещё сложнее.

#### Raft: Paxos для людей

В 2013 году Diego Ongaro и John Ousterhout разработали Raft с явной целью: быть понятнее Paxos. Статья называлась "In Search of an Understandable Consensus Algorithm".

Raft разделяет проблему консенсуса на:
1. **Leader election**: выбор одного лидера
2. **Log replication**: лидер реплицирует log на followers
3. **Safety**: гарантии корректности

```
Состояния узла в Raft:
  - Follower: пассивный, принимает команды от лидера
  - Candidate: претендует на лидерство (при отсутствии heartbeat)
  - Leader: обрабатывает запросы, реплицирует log
```

```python
# Упрощённая реализация Raft Election
import random
import asyncio
from enum import Enum

class State(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

class RaftNode:
    def __init__(self, node_id: str, peers: list):
        self.id = node_id
        self.peers = peers
        self.state = State.FOLLOWER
        self.current_term = 0
        self.voted_for = None
        self.leader_id = None
        
        # Randomized election timeout: 150-300ms
        self.election_timeout = random.uniform(0.15, 0.30)
        self.last_heartbeat = asyncio.get_event_loop().time()
    
    async def run(self):
        while True:
            if self.state == State.FOLLOWER:
                await self._follower_loop()
            elif self.state == State.CANDIDATE:
                await self._candidate_loop()
            elif self.state == State.LEADER:
                await self._leader_loop()
    
    async def _follower_loop(self):
        """Ждём heartbeat. Если нет — становимся кандидатом."""
        timeout = self.election_timeout
        await asyncio.sleep(timeout)
        
        now = asyncio.get_event_loop().time()
        if now - self.last_heartbeat > self.election_timeout:
            print(f"{self.id}: No heartbeat from leader, starting election")
            self.state = State.CANDIDATE
    
    async def _candidate_loop(self):
        """Запрашиваем голоса у peers."""
        self.current_term += 1
        self.voted_for = self.id
        votes = 1  # Голосуем за себя
        
        print(f"{self.id}: Starting election for term {self.current_term}")
        
        # Запрашиваем голоса параллельно
        tasks = [self._request_vote(peer) for peer in self.peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for granted in results:
            if granted is True:
                votes += 1
        
        # Нужен кворум (majority)
        if votes > len(self.peers) // 2:
            print(f"{self.id}: Won election with {votes} votes!")
            self.state = State.LEADER
        else:
            print(f"{self.id}: Lost election, going back to follower")
            self.state = State.FOLLOWER
            await asyncio.sleep(random.uniform(0.15, 0.30))
    
    async def _leader_loop(self):
        """Отправляем heartbeat всем peers каждые 50ms."""
        print(f"{self.id}: I am the leader for term {self.current_term}")
        while self.state == State.LEADER:
            tasks = [self._send_heartbeat(peer) for peer in self.peers]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.05)  # 50ms heartbeat interval
    
    async def _request_vote(self, peer_id: str) -> bool:
        # В реальности - RPC вызов
        # Возвращает True если peer голосует за нас
        return True  # Заглушка
    
    async def _send_heartbeat(self, peer_id: str):
        # В реальности - AppendEntries RPC с пустыми записями
        pass
    
    def receive_heartbeat(self, leader_id: str, term: int):
        """Получили heartbeat от лидера."""
        if term >= self.current_term:
            self.current_term = term
            self.leader_id = leader_id
            self.state = State.FOLLOWER
            self.last_heartbeat = asyncio.get_event_loop().time()
```

**Реальные реализации Raft**:
- etcd: используется в Kubernetes
- CockroachDB: распределённая SQL база
- TiKV: key-value слой TiDB
- Consul: service discovery

#### Byzantine Fault Tolerance (BFT)

Raft и Paxos предполагают **crash fault tolerance**: узел либо работает корректно, либо падает. 

**Byzantine fault** (Задача о Византийских генералах, Лэмпорт, 1982): узел может работать некорректно и отправлять *противоречивые* сообщения разным узлам (сбой оборудования, взлом, баг).

**PBFT** (Practical Byzantine Fault Tolerance, 1999): достигает консенсуса при $n \geq 3f+1$ узлах, где f — число Byzantine-узлов. Требует $n \geq 4$ для f=1.

**Blockchain консенсус**: Bitcoin использует Proof-of-Work (не BFT в строгом смысле), Ethereum перешёл на Proof-of-Stake. Оба предполагают Byzantine fault tolerance в открытой сети с неизвестными участниками.

## Практическое применение

### Выбор базы данных

```
Финансовые транзакции, платежи:
  Нужна: Strong Consistency
  Выбор: PostgreSQL, CockroachDB, Google Spanner
  PACELC: PC/EC

Лента социальной сети, счётчики лайков:
  Нужна: High Availability, Eventual Consistency OK
  Выбор: Cassandra, DynamoDB (eventually consistent)
  PACELC: PA/EL

Распределённая конфигурация, лидер-выборы:
  Нужна: Strong Consistency, Partition Tolerance
  Выбор: ZooKeeper, etcd, Consul
  PACELC: PC/EC
  
Корзина покупок в e-commerce:
  Amazon Dynamo paper: выбрали AP
  "Lost update" (купить товар дважды) лучше, чем "корзина недоступна"
```

### Когда можно принять eventual consistency

```python
# Счётчик просмотров статьи: eventual consistency OK
# Пользователь не заметит, что счётчик показывает 1000 вместо 1002

from cassandra.cluster import Cluster
from cassandra import ConsistencyLevel as CL

session = cluster.connect()
session.default_consistency_level = CL.ONE  # Быстро, AP

session.execute(
    "UPDATE articles SET views = views + 1 WHERE id = ?",
    (article_id,)
)

# Баланс банковского счёта: strong consistency обязательна
# Два списания одновременно НЕ должны оба видеть "баланс = 100"

from sqlalchemy import create_engine
engine = create_engine("postgresql://...")

with engine.begin() as conn:  # SERIALIZABLE транзакция
    balance = conn.execute(
        "SELECT balance FROM accounts WHERE id = ? FOR UPDATE",
        (account_id,)
    ).scalar()
    
    if balance < amount:
        raise InsufficientFundsError()
    
    conn.execute(
        "UPDATE accounts SET balance = balance - ? WHERE id = ?",
        (amount, account_id)
    )
```

### Conflict Resolution в AP-системах

При eventual consistency возникают конфликты: два узла одновременно обновили одну запись. Нужна стратегия разрешения.

**Last Write Wins (LWW)**: выигрывает запись с большим timestamp. Простейший, но данные могут потеряться.

**Vector Clocks**: каждая запись несёт вектор логических часов. Cassandra использует для обнаружения причинно-следственных зависимостей между версиями.

```python
# Пример Vector Clock
class VectorClock:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.clocks: dict[str, int] = {}
    
    def increment(self):
        self.clocks[self.node_id] = self.clocks.get(self.node_id, 0) + 1
    
    def merge(self, other: 'VectorClock'):
        """Объединяем векторные часы при получении сообщения."""
        for node, time in other.clocks.items():
            self.clocks[node] = max(self.clocks.get(node, 0), time)
    
    def is_concurrent(self, other: 'VectorClock') -> bool:
        """Конфликт: ни одни не доминируют над другими."""
        a_dominates_b = any(
            self.clocks.get(n, 0) > other.clocks.get(n, 0)
            for n in set(self.clocks) | set(other.clocks)
        )
        b_dominates_a = any(
            other.clocks.get(n, 0) > self.clocks.get(n, 0)
            for n in set(self.clocks) | set(other.clocks)
        )
        return a_dominates_b and b_dominates_a
```

**CRDT** (Conflict-free Replicated Data Types): специальные структуры данных, где конфликты разрешаются автоматически математически корректно. Используются в Redis, Riak, real-time collaborative editors (Figma, Google Docs).

```python
# G-Counter CRDT: только инкремент, merge = max по каждому узлу
class GCounter:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self._counts: dict[str, int] = {}
    
    def increment(self, amount: int = 1):
        self._counts[self.node_id] = self._counts.get(self.node_id, 0) + amount
    
    def value(self) -> int:
        return sum(self._counts.values())
    
    def merge(self, other: 'GCounter') -> 'GCounter':
        """Конфликтов нет — берём максимум по каждому узлу."""
        result = GCounter(self.node_id)
        all_nodes = set(self._counts) | set(other._counts)
        for node in all_nodes:
            result._counts[node] = max(
                self._counts.get(node, 0),
                other._counts.get(node, 0)
            )
        return result
```

## Резюме

Три теоремы формируют интеллектуальный фундамент для работы с распределёнными системами:

1. **CAP**: при partition выбирайте между согласованностью и доступностью. Partition толерантность обязательна. Это не "выбор навсегда" — можно настраивать per-запрос (DynamoDB ConsistentRead).

2. **PACELC**: даже без partition — выбор между задержкой и согласованностью. Кворумные операции медленнее, но консистентнее. Проектируйте зная этот компромисс.

3. **FLP**: в асинхронной сети с одним отказавшим узлом консенсус невозможен. Реальные системы обходят это через таймауты (частичная синхронность) и рандомизацию. Если Raft/Paxos медленно сходятся — возможно, проблема в сети, а не в алгоритме.

Знание этих ограничений не мешает строить надёжные системы. Оно помогает задавать правильные вопросы: "Какой уровень согласованности нужен для этой операции? Что произойдёт при partition? Готовы ли мы к задержкам ради корректности?"

## Литература

1. Gilbert S., Lynch N. **Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services** // ACM SIGACT News, 2002. — Формальное доказательство CAP.

2. Brewer E. **CAP Twelve Years Later: How the "Rules" Have Changed** // IEEE Computer, 2012. — Сам Брюер уточняет CAP.

3. Abadi D. **Consistency Tradeoffs in Modern Distributed Database System Design: CAP is Only Part of the Story** // IEEE Computer, 2012. — Статья, вводящая PACELC.

4. Fischer M.J., Lynch N.A., Paterson M.S. **Impossibility of Distributed Consensus with One Faulty Process** // Journal of the ACM, 1985. — Оригинальное доказательство FLP.

5. Ongaro D., Ousterhout J. **In Search of an Understandable Consensus Algorithm (Extended Version)** // USENIX ATC, 2014. — Статья о Raft. https://raft.github.io/raft.pdf

6. Lamport L. **Paxos Made Simple** // ACM SIGACT News, 2001. — Лэмпорт объясняет Paxos.

7. DeCandia G. et al. **Dynamo: Amazon's Highly Available Key-value Store** // SOSP, 2007. — Ключевая статья о AP-системах.

8. Shapiro M. et al. **Conflict-free Replicated Data Types** // Lecture Notes in Computer Science, 2011. — CRDT.

9. Lamport L., Shostak R., Pease M. **The Byzantine Generals Problem** // ACM TOPLAS, 1982.

10. Kleppmann M. **Designing Data-Intensive Applications**. O'Reilly Media, 2017. — Главы 8-9: фундаментальные ограничения распределённых систем.
