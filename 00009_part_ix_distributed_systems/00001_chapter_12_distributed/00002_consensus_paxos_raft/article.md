# Консенсус в распределённых системах: Paxos и Raft

## Введение

Как группа узлов распределённой системы может договориться об одном значении, если любой из них может отказать, а сеть ненадёжна? Это задача **консенсуса** — одна из центральных в теории распределённых вычислений.

Теорема FLP (Fischer, Lynch, Paterson, 1985) доказывает: в **полностью асинхронной** системе с хотя бы одним возможным отказом консенсус невозможно достичь гарантированно. Это фундаментальный теоретический барьер. Практические алгоритмы обходят его, предполагая частичную синхронность (bounded delays в нормальных условиях) или ограниченные типы отказов.

Алгоритм **Paxos** (Лесли Лэмпорт, 1989/1998) — теоретически элегантный, но на практике сложный для реализации. **Raft** (Ongaro & Ousterhout, 2014) создан как «Paxos для людей» — более понятный и практичный алгоритм с теми же гарантиями.

---

## 1. Задача консенсуса: формальное определение

### 1.1 Требования к алгоритму консенсуса

Алгоритм консенсуса должен удовлетворять трём свойствам:

1. **Agreement (Согласованность)**: все правильно работающие узлы принимают одно и то же решение
2. **Validity (Корректность)**: принятое решение было предложено одним из узлов
3. **Termination (Завершённость)**: каждый правильно работающий узел в конечном счёте принимает решение

Задача: N узлов, каждый предлагает значение. Нужно выбрать ровно одно.

### 1.2 Практическое применение

Консенсус лежит в основе:
- **Replicated State Machine**: лог команд, одинаковый на всех репликах → детерминированный state machine приходит к одному состоянию
- **Distributed Lock Service**: Zookeeper, etcd
- **Leader Election**: выбор единственного лидера в кластере
- **Distributed Transactions**: 2PC (Two-Phase Commit) как вырожденный консенсус
- **Distributed Databases**: CockroachDB, TiDB, Google Spanner

---

## 2. Paxos: классический алгоритм консенсуса

### 2.1 Роли в Paxos

- **Proposer**: инициирует голосование, предлагает значение
- **Acceptor**: голосует за предложения (quorum из N/2+1 acceptors)
- **Learner**: узнаёт принятое значение

Один физический узел может играть все роли.

### 2.2 Протокол Single-Decree Paxos

**Фаза 1 (Prepare/Promise):**

```
Proposer → Acceptors: Prepare(n)  [n = уникальный номер раунда]
Acceptors → Proposer: Promise(n, (n_accepted, v_accepted))
  - обещают не принимать запросы с номером < n
  - сообщают последнее принятое значение (если есть)
```

**Фаза 2 (Accept/Accepted):**

```
Proposer → Acceptors: Accept(n, v)
  - v = предложенное значение
  - если кто-то из Acceptors уже принял значение v', то v = v' (не наше!)
Acceptors → Proposer: Accepted(n, v)
  - принимают, если не давали Promise с большим номером
Learners: узнают значение после кворума Accepted
```

```python
import random
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple

@dataclass
class AcceptorState:
    """Состояние узла-Acceptor"""
    min_proposal: int = 0         # минимальный номер Prepare, обещанный принять
    accepted_proposal: int = 0    # номер последнего принятого предложения
    accepted_value: Optional[str] = None  # принятое значение

class PaxosAcceptor:
    def __init__(self, acceptor_id: int):
        self.id = acceptor_id
        self.state = AcceptorState()
    
    def prepare(self, proposal_num: int) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Обрабатывает Prepare(n).
        Возвращает: (promise_granted, last_accepted_n, last_accepted_v)
        """
        if proposal_num > self.state.min_proposal:
            self.state.min_proposal = proposal_num
            # Promise: не будем принимать предложения с n < proposal_num
            return True, self.state.accepted_proposal, self.state.accepted_value
        else:
            return False, None, None
    
    def accept(self, proposal_num: int, value: str) -> bool:
        """
        Обрабатывает Accept(n, v).
        Возвращает: принято ли предложение.
        """
        if proposal_num >= self.state.min_proposal:
            self.state.min_proposal = proposal_num
            self.state.accepted_proposal = proposal_num
            self.state.accepted_value = value
            return True
        return False

class PaxosProposer:
    def __init__(self, proposer_id: int, acceptors: list):
        self.id = proposer_id
        self.acceptors = acceptors
        self.proposal_counter = proposer_id  # уникальность через ID
    
    def next_proposal_num(self) -> int:
        self.proposal_counter += len(self.acceptors) + 1
        return self.proposal_counter
    
    async def propose(self, value: str) -> Optional[str]:
        """Полный Paxos протокол для предложения значения"""
        quorum = len(self.acceptors) // 2 + 1
        
        while True:
            n = self.next_proposal_num()
            
            # Фаза 1: Prepare
            promises = []
            for acceptor in self.acceptors:
                granted, acc_n, acc_v = acceptor.prepare(n)
                if granted:
                    promises.append((acc_n, acc_v))
            
            if len(promises) < quorum:
                print(f"Proposer {self.id}: не набрали кворум в Phase 1, retry")
                await asyncio.sleep(random.uniform(0.01, 0.1))
                continue
            
            # Определяем значение для Phase 2
            # Если кто-то уже принял значение — используем его!
            highest_accepted = max(promises, key=lambda x: x[0] or 0)
            if highest_accepted[1] is not None:
                chosen_value = highest_accepted[1]  # не можем изменить
                print(f"Proposer {self.id}: узнали принятое значение '{chosen_value}'")
            else:
                chosen_value = value  # наше значение
            
            # Фаза 2: Accept
            acceptances = 0
            for acceptor in self.acceptors:
                if acceptor.accept(n, chosen_value):
                    acceptances += 1
            
            if acceptances >= quorum:
                print(f"Proposer {self.id}: консенсус достигнут: '{chosen_value}'")
                return chosen_value
            else:
                print(f"Proposer {self.id}: не набрали кворум в Phase 2, retry")
                await asyncio.sleep(random.uniform(0.01, 0.1))

# Демонстрация
async def demo_paxos():
    acceptors = [PaxosAcceptor(i) for i in range(5)]  # 5 acceptors
    
    # Два конкурентных Proposer
    p1 = PaxosProposer(1, acceptors)
    p2 = PaxosProposer(2, acceptors)
    
    results = await asyncio.gather(
        p1.propose("value_A"),
        p2.propose("value_B"),
        return_exceptions=True
    )
    
    print(f"Results: {results}")
    # Оба должны прийти к одному значению

asyncio.run(demo_paxos())
```

### 2.3 Multi-Paxos: репликация лога команд

Single-Decree Paxos выбирает одно значение. Для репликации лога (Replicated State Machine) нужен Multi-Paxos:

- Одна Фаза 1 (Prepare) для нескольких последовательных раундов
- Лидер выполняет только Фазу 2 (Accept) для каждой команды, пока не потерял лидерство

Это значительно сокращает число сетевых roundtrips в нормальном режиме.

---

## 3. Raft: Paxos для людей

### 3.1 Почему Raft?

Ongaro & Ousterhout (2014) в своей диссертации провели исследование: Paxos сложно понять и правильно реализовать. Raft спроектирован с явным приоритетом **understandability**.

Raft разбивает консенсус на три относительно независимых задачи:
1. **Leader Election**: выбор единственного лидера через majority vote
2. **Log Replication**: лидер принимает запросы и реплицирует лог
3. **Safety**: гарантии корректности даже при перевыборах

### 3.2 Термы (Terms) в Raft

Время в Raft разделено на **термы** (terms) — монотонно возрастающие целые числа. Каждый терм начинается с выборов. В одном терме может быть не более одного лидера.

```
     Term 1        Term 2    Term 3       Term 4
  ─────────────┬──────────┬──────────┬──────────────►
  Leader: A    │ Election │ Leader: B │   Leader: B
               │ (failed) │           │
```

### 3.3 Leader Election

```python
import asyncio
import random
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict

class NodeState(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

@dataclass
class LogEntry:
    term: int
    index: int
    command: str

@dataclass
class RaftNode:
    node_id: int
    peers: List[int]
    
    # Persistent state (на диске)
    current_term: int = 0
    voted_for: Optional[int] = None
    log: List[LogEntry] = field(default_factory=list)
    
    # Volatile state
    state: NodeState = NodeState.FOLLOWER
    commit_index: int = 0
    last_applied: int = 0
    
    # Leader volatile state
    next_index: Dict[int, int] = field(default_factory=dict)
    match_index: Dict[int, int] = field(default_factory=dict)
    
    # Таймер
    last_heartbeat: float = field(default_factory=time.monotonic)
    election_timeout: float = field(default_factory=lambda: random.uniform(0.15, 0.3))
    
    def get_last_log_info(self) -> tuple:
        if not self.log:
            return 0, 0
        last = self.log[-1]
        return last.index, last.term
    
    def is_log_up_to_date(self, last_log_index: int, last_log_term: int) -> bool:
        """Является ли кандидат таким же up-to-date как мы?"""
        my_last_index, my_last_term = self.get_last_log_info()
        if last_log_term != my_last_term:
            return last_log_term > my_last_term
        return last_log_index >= my_last_index
    
    async def run_election(self, cluster: 'RaftCluster'):
        """Начать выборы"""
        self.current_term += 1
        self.state = NodeState.CANDIDATE
        self.voted_for = self.node_id
        votes = 1  # голосуем за себя
        
        last_log_index, last_log_term = self.get_last_log_info()
        
        print(f"Node {self.node_id}: начинаем выборы, term={self.current_term}")
        
        # Запрашиваем голоса от всех других узлов
        vote_tasks = [
            cluster.request_vote(
                peer_id=peer,
                term=self.current_term,
                candidate_id=self.node_id,
                last_log_index=last_log_index,
                last_log_term=last_log_term
            )
            for peer in self.peers
        ]
        
        results = await asyncio.gather(*vote_tasks, return_exceptions=True)
        
        for vote_granted in results:
            if vote_granted == True:
                votes += 1
        
        quorum = (len(self.peers) + 1) // 2 + 1
        
        if votes >= quorum and self.state == NodeState.CANDIDATE:
            self.become_leader(cluster)
        else:
            self.state = NodeState.FOLLOWER
    
    def become_leader(self, cluster: 'RaftCluster'):
        self.state = NodeState.LEADER
        print(f"Node {self.node_id}: стал лидером, term={self.current_term}")
        
        # Инициализируем next_index и match_index
        last_idx, _ = self.get_last_log_info()
        for peer in self.peers:
            self.next_index[peer] = last_idx + 1
            self.match_index[peer] = 0

class RaftCluster:
    def __init__(self, num_nodes: int):
        self.nodes: Dict[int, RaftNode] = {}
        node_ids = list(range(num_nodes))
        
        for node_id in node_ids:
            peers = [i for i in node_ids if i != node_id]
            self.nodes[node_id] = RaftNode(node_id=node_id, peers=peers)
    
    async def request_vote(
        self, 
        peer_id: int,
        term: int,
        candidate_id: int,
        last_log_index: int,
        last_log_term: int
    ) -> bool:
        node = self.nodes[peer_id]
        
        # Отклоняем если наш терм больше
        if term < node.current_term:
            return False
        
        if term > node.current_term:
            node.current_term = term
            node.state = NodeState.FOLLOWER
            node.voted_for = None
        
        # Голосуем только раз за терм и только за up-to-date кандидата
        vote_granted = (
            (node.voted_for is None or node.voted_for == candidate_id) and
            node.is_log_up_to_date(last_log_index, last_log_term)
        )
        
        if vote_granted:
            node.voted_for = candidate_id
            node.last_heartbeat = time.monotonic()
        
        return vote_granted
```

### 3.4 Log Replication

```python
async def append_entries(
    self,
    cluster: 'RaftCluster',
    peer_id: int,
    entries: List[LogEntry]
) -> bool:
    """AppendEntries RPC от лидера к фолловеру"""
    peer = cluster.nodes[peer_id]
    
    prev_log_index = self.next_index[peer_id] - 1
    prev_log_term = 0
    if prev_log_index > 0 and len(self.log) >= prev_log_index:
        prev_log_term = self.log[prev_log_index - 1].term
    
    # Отправляем AppendEntries
    success = await peer.handle_append_entries(
        term=self.current_term,
        leader_id=self.node_id,
        prev_log_index=prev_log_index,
        prev_log_term=prev_log_term,
        entries=entries,
        leader_commit=self.commit_index
    )
    
    if success:
        if entries:
            self.match_index[peer_id] = entries[-1].index
            self.next_index[peer_id] = entries[-1].index + 1
        
        # Проверяем можно ли advance commit_index
        await self.maybe_advance_commit()
    else:
        # Log inconsistency: уменьшаем next_index и повторяем
        self.next_index[peer_id] = max(1, self.next_index[peer_id] - 1)
    
    return success

async def maybe_advance_commit(self, cluster: 'RaftCluster'):
    """Advance commit index если большинство реплицировало"""
    quorum = (len(self.peers) + 1) // 2 + 1
    
    for n in range(self.commit_index + 1, len(self.log) + 1):
        if self.log[n-1].term != self.current_term:
            continue  # Raft не коммитит записи предыдущих термов напрямую
        
        replicated = 1  # мы сами
        for peer in self.peers:
            if self.match_index.get(peer, 0) >= n:
                replicated += 1
        
        if replicated >= quorum:
            self.commit_index = n
            print(f"Leader {self.node_id}: commit_index advanced to {n}")
```

### 3.5 Гарантия безопасности Raft

Ключевое свойство: **Log Matching Property**: если два лога содержат запись с одинаковым index и term, то все записи до этой — идентичны.

Это гарантирует:
- **Election Safety**: в одном терме не более одного лидера
- **Leader Append-Only**: лидер только добавляет в лог, никогда не перезаписывает
- **Log Matching**: см. выше
- **Leader Completeness**: если запись зафиксирована в терме t, она будет в логах всех будущих лидеров
- **State Machine Safety**: все state machines применяют одни и те же команды в одном порядке

---

## 4. Сравнение Paxos и Raft

| Аспект | Paxos (Multi-Paxos) | Raft |
|--------|---------------------|------|
| Читаемость | Сложный | Простой |
| Выборы лидера | Неявные | Явные (RandomTimeout) |
| Репликация лога | Через rounds | Явный лог с nextIndex |
| Конфигурация | Не описана | joint consensus |
| Membership changes | Сложно | Описано в статье |
| Реализации | Zab (ZooKeeper), Viewstamped | etcd, CockroachDB, TiKV, Consul |

---

## 5. Raft в реальных системах

### 5.1 etcd: хранилище состояния Kubernetes

etcd использует Raft для обеспечения сильной согласованности:

```python
import etcd3

client = etcd3.client(host='localhost', port=2379)

# Запись с lease (TTL)
lease = client.lease(30)  # TTL = 30 секунд
client.put('/services/my-service/host', 'server01', lease=lease)

# Распределённая блокировка через etcd
lock = client.lock('/locks/resource-123', ttl=30)
with lock:
    print("Критическая секция — только один процесс в кластере")
    # ...

# Watch: реактивное обновление при изменениях
events_iterator, cancel = client.watch_prefix('/services/')
for event in events_iterator:
    print(f"Changed: {event.key} = {event.value}")
    if should_stop:
        cancel()
        break

# Транзакции (Compare-And-Swap)
# Атомарно: если value == expected, то put new_value
succeed, responses = client.transaction(
    compare=[
        client.transactions.value('/config/version') == b'v1',
    ],
    success=[
        client.transactions.put('/config/version', 'v2'),
        client.transactions.put('/config/data', 'new_config'),
    ],
    failure=[]
)
```

### 5.2 Производительность Raft

Узкое место — roundtrip между лидером и follower'ами:

```
Запись в CockroachDB/TiDB:
Client → Leader: proposal
Leader → Followers: AppendEntries
Followers → Leader: Acked
Leader: commit
Leader → Client: success

Задержка $= 2 \times \text{RTT}$ (leader $\leftrightarrow$ followers)
Для inter-DC: $2 \times 10\text{ms} = 20\text{ms}$ минимум

Оптимизации:
1. Pipeline: не ждать ack перед следующей записью
2. Batching: несколько записей в один AppendEntries
3. Leader lease: оптимистические read без roundtrip
```

---

## 6. Проблема FLP и её практическое значение

### 6.1 Теорема FLP

Fischer, Lynch & Paterson (1985): в **полностью асинхронной** системе с хотя бы одним возможным отказом процесса достичь консенсуса с гарантированным завершением **невозможно**.

Интуиция: в асинхронной системе нет способа отличить медленный процесс от упавшего. Если мы ждём ответа — мы можем ждать вечно. Если не ждём — можем принять решение без учёта живого, но медленного процесса.

### 6.2 Как Raft обходит FLP

Raft предполагает **partial synchrony** (частичную синхронность): сеть в конечном счёте доставляет сообщения за конечное (но неизвестное) время. В нормальных условиях задержки ограничены.

Randomized election timeout предотвращает бесконечные разделённые выборы: с высокой вероятностью только один узел начнёт выборы раньше остальных.

---

## Заключение

Консенсус — краеугольный камень распределённых систем. Paxos и Raft решают одну задачу разными методами: Paxos элегантен теоретически, Raft практичен для реализации.

Raft разделяет проблему на три части: leader election через randomized timeouts, log replication через AppendEntries, safety через строгие инварианты лога. Это позволило создать понятные и корректные реализации в etcd, CockroachDB, TiKV, HashiCorp Consul.

Практический вывод: не нужно реализовывать Raft с нуля — используйте etcd как distributed lock service или CockroachDB как distributed SQL. Понимание алгоритма важно для правильного использования и диагностики проблем.

---

## Библиография

1. Lamport, L. (1998). The Part-Time Parliament. *ACM Transactions on Computer Systems*, 16(2), 133–169.
2. Ongaro, D., & Ousterhout, J. (2014). In Search of an Understandable Consensus Algorithm. *USENIX ATC 2014*.
3. Fischer, M.J., Lynch, N.A., & Paterson, M.S. (1985). Impossibility of Distributed Consensus with One Faulty Process. *Journal of the ACM*, 32(2), 374–382.
4. Lamport, L., Shostak, R., & Pease, M. (1982). The Byzantine Generals Problem. *ACM TPLS*, 4(3), 382–401.
5. Howard, H., et al. (2016). Flexible Paxos: Quorum Intersection Revisited. *arXiv*.
6. etcd documentation. (2024). https://etcd.io/docs/
7. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media. Chapter 9.
8. Raft visualization. (2024). https://raft.github.io/
