# Теорема CAP и PACELC: согласованность vs доступность в распределённых системах

## Введение

Когда мы проектируем распределённую систему, нас преследует фундаментальный вопрос: что произойдёт, если сеть между узлами перестанет работать? Два узла, считающие себя «живыми», дадут разные ответы на одни и те же запросы. Как должна вести себя система в этот момент?

Теорема CAP, сформулированная Эриком Брюэром в 2000 году и доказанная Гилбертом и Линчем в 2002 году, даёт чёткий ответ: в момент разбиения сети система вынуждена выбирать между согласованностью и доступностью. Это не технологическое ограничение — это математически доказанное фундаментальное свойство распределённых вычислений.

Однако с годами стало ясно, что CAP не охватывает всё важное. В 2012 году Дэниел Абади предложил расширение PACELC, которое учитывает компромиссы при нормальной работе системы (без разбиения сети) — задержку против согласованности.

---

## 1. Теорема CAP: формулировка и доказательство

### 1.1 Три свойства

**Consistency (Согласованность, C)**: каждое чтение возвращает результат самой последней успешной записи или ошибку. Все узлы видят одни и те же данные в одно и то же время. Это определение ближе к linearizability (линеаризуемости), чем к ACID-согласованности.

**Availability (Доступность, A)**: каждый запрос к неотказавшему узлу системы получает ответ (не ошибку). Система отвечает всегда, даже если ответ может быть устаревшим.

**Partition tolerance (Устойчивость к разбиению сети, P)**: система продолжает работать, даже если сообщения между узлами теряются или задерживаются произвольно долго.

### 1.2 Доказательство невозможности CAP

Гилберт и Линч доказали теорему через противоречие. Рассмотрим упрощённую версию:

Система из двух узлов A и B, хранящих переменную v с начальным значением $v_0$.

1. Клиент записывает $v_1$ в узел A
2. Между A и B происходит разбиение сети (A не может отправить $v_1$ в B)
3. Другой клиент читает с узла B

Возможны два сценария:
- **Узел B отвечает $v_0$**: согласованность нарушена (клиент прочитал устаревшее значение), но доступность сохранена
- **Узел B отвечает ошибкой**: согласованность сохранена (нет ответа = нет ошибочного ответа), но доступность нарушена

Третьего варианта нет: B не может знать актуальное $v_1$ без связи с A.

```python
# Симуляция CAP-дилеммы
import threading
import time
from dataclasses import dataclass
from typing import Optional

@dataclass
class Node:
    name: str
    value: int = 0
    version: int = 0
    
class DistributedSystem:
    def __init__(self):
        self.node_a = Node("A")
        self.node_b = Node("B")
        self.partition = False  # разбиение сети
        self.lock = threading.Lock()
    
    def write(self, node: Node, value: int) -> bool:
        """Запись с синхронизацией второго узла"""
        with self.lock:
            node.value = value
            node.version += 1
        
        # Попытка синхронизации с другим узлом
        other = self.node_b if node == self.node_a else self.node_a
        
        if not self.partition:
            # Синхронная репликация (CP-стратегия)
            with self.lock:
                other.value = value
                other.version = node.version
            return True
        else:
            # Разбиение: не можем синхронизировать
            # CP: отклонить запись
            # AP: принять, согласованность нарушится
            return False  # CP-стратегия
    
    def read_cp(self, node: Node) -> Optional[int]:
        """CP: отказать если не можем гарантировать свежесть данных"""
        if self.partition:
            return None  # ошибка — сохраняем согласованность
        return node.value
    
    def read_ap(self, node: Node) -> int:
        """AP: отдать что есть, даже если устаревшее"""
        return node.value  # всегда доступны, но может быть stale

# Демонстрация
system = DistributedSystem()
system.write(system.node_a, 42)
print(f"До разбиения: A={system.node_a.value}, B={system.node_b.value}")

system.partition = True  # разрыв сети
system.write(system.node_a, 100)  # CP-режим отклонит

print(f"CP read from B: {system.read_cp(system.node_b)}")  # None (ошибка)
print(f"AP read from B: {system.read_ap(system.node_b)}")  # 42 (устаревшее)
```

### 1.3 P — не выбор, а данность

Ключевое заблуждение: «P» — это не выбор, который мы делаем. Сетевые разбиения происходят в любой реальной распределённой системе: кабель перебит, датацентр теряет связь, пакеты теряются. Поэтому реальный выбор — между C и A **в момент разбиения**.

Системы, которые «отказываются от P» — это системы, работающие на одном узле (единая точка отказа). В контексте реального кластера P всегда должно быть гарантировано.

---

## 2. Классификация систем по CAP

### 2.1 CP-системы: согласованность важнее доступности

В момент разбиения CP-системы прекращают обслуживать запросы (или часть запросов) на недоступных узлах, чтобы не вернуть устаревшие данные.

**HBase**: сильная согласованность через единственный мастер-регион для каждого диапазона ключей. При отказе мастера — недоступность до выбора нового (секунды–минуты).

**Zookeeper**: гарантирует linearizability через протокол ZAB (Zookeeper Atomic Broadcast). Записи проходят через лидера; при потере кворума — отказ от обслуживания.

**etcd**: использует Raft; при потере кворума (менее N/2+1 узлов) — отклонение записей. Используется в Kubernetes для хранения состояния кластера.

**MongoDB с writeConcern: "majority"**: запись подтверждается только после достижения большинства реплик. При изоляции secondary — записи на primary продолжаются, secondary блокируются.

### 2.2 AP-системы: доступность важнее согласованности

AP-системы продолжают обслуживать запросы при разбиении, принимая возможность несогласованных ответов.

**Cassandra**: при разбиении продолжает принимать записи на все доступные узлы. После восстановления — конфликты разрешаются через Last Write Wins (LWW) по timestamp.

**Amazon DynamoDB** (по умолчанию): eventual consistency. Запрос к любой реплике — мгновенный ответ, но может быть устаревшим.

**CouchDB**: multi-master репликация. Конфликты хранятся явно и разрешаются приложением или через автоматические процедуры.

**Riak**: AP-система с CRDT для автоматического разрешения конфликтов без потери данных.

### 2.3 CA — теоретический случай для нераспределённых систем

CA-системы — это системы с единственным узлом (нет сети — нет разбиения). Традиционные реляционные СУБД на одном сервере (PostgreSQL, MySQL без репликации) относятся к этой категории. Как только добавляется репликация — система попадает в CP или AP.

| Система | Тип CAP | Объяснение |
|---------|---------|------------|
| Zookeeper | CP | Кворум, ZAB-протокол |
| etcd | CP | Raft, кворум |
| HBase | CP | Единый мастер на регион |
| MongoDB (w: majority) | CP | Кворумная запись |
| Cassandra | AP | Eventual consistency |
| DynamoDB (eventual) | AP | Eventual consistency |
| CouchDB | AP | Multi-master |
| Redis Cluster | AP | Async репликация |
| PostgreSQL (streaming replication) | CP | Реплика может отставать |

---

## 3. Критика CAP и уточнения

### 3.1 CAP слишком грубая классификация

Критики указывают, что CAP — бинарная классификация, тогда как реальность богаче:

- **Согласованность** варьируется: от linearizability до sequential consistency, causal consistency, read-your-writes, eventual consistency
- **Доступность** — не бинарная: система может деградировать частично
- **Разбиения** — разные по масштабу: временная задержка пакета vs полная изоляция датацентра

Например, Cassandra с `CONSISTENCY=QUORUM` при разбиении ведёт себя как CP-система для данного запроса, хотя обычно классифицируется как AP.

### 3.2 Linearizability vs Sequential Consistency

CAP использует понятие «согласованности», близкое к linearizability, — самой строгой форме. Но на практике многие системы используют более слабые, но достаточные гарантии:

**Sequential Consistency** (Lamport, 1979): операции каждого процесса происходят в программном порядке, но абсолютная временна́я упорядоченность между процессами не гарантируется.

**Causal Consistency**: если событие A причинно предшествует B, то все узлы видят A до B. Не-каузально связанные события могут наблюдаться в разном порядке.

**Eventual Consistency**: при отсутствии новых записей, все узлы в конечном счёте сойдутся к одному значению. Это слабейшая форма согласованности.

---

## 4. PACELC: расширение для нормального режима

### 4.1 Проблема с CAP

CAP описывает поведение только при разбиении сети. Но разбиения — редкое событие. В нормальном режиме работы что важнее: задержка ответа или согласованность?

Система может быть CP (отдавать предпочтение согласованности при разбиении), но при нормальной работе — жертвовать задержкой ради согласованности (синхронная репликация) или — задержкой ради скорости (асинхронная репликация с eventual consistency).

### 4.2 Формулировка PACELC

Дэниел Абади (2012) предложил PACELC:

> **If P** (partition): **A** or **C** (Availability or Consistency)  
> **Else** (нормальный режим): **L** or **C** (Latency or Consistency)

Полное название: **P**artition, **A**vailability, **C**onsistency, **E**lse, **L**atency, **C**onsistency.

```
┌─────────────────────────────────────────────────────────┐
│                    PACELC Matrix                         │
│                                                          │
│  При разбиении (P):        В нормальном режиме (EL+C):  │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────────┐  │
│  │  A: отвечать всегда  │  │  L: минимальная задержка  │  │
│  │  C: или согласованно │  │  C: или максимальная       │  │
│  └──────────────────────┘  │     согласованность        │  │
│                             └──────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 4.3 Классификация по PACELC

| Система | P→A/C | EL→L/C | Пояснение |
|---------|-------|---------|-----------|
| DynamoDB (eventual) | PA | EL | AP + низкая задержка через async replication |
| DynamoDB (strong) | PC | EC | Включает sync для strong reads |
| Cassandra | PA | EL | AP + очень низкая запись через LSM |
| Cassandra (QUORUM) | PC | EC | При QUORUM оба направления меняются |
| MongoDB (eventual) | PA | EL | AP + async secondary reads |
| MongoDB (majority) | PC | EC | CP + sync для гарантии |
| HBase | PC | EC | CP всегда, sync через ZooKeeper |
| Zookeeper | PC | EC | CP, ZAB-протокол синхронный |
| MySQL Cluster | PC | EC | Sync репликация |
| PNUTS (Yahoo!) | PC | EL | CP при разбиении, но async в норме |

### 4.4 Практический пример: репликация PostgreSQL

```
Async (PA/EL): 
  Клиент → PRIMARY → WAL отправляется асинхронно → SECONDARY
  Задержка: минимальная (нет ожидания secondary)
  Риск: при крашe primary, committed но не реплицированные транзакции теряются

Sync (PC/EC):
  Клиент → PRIMARY → ждёт подтверждения SECONDARY → ответ клиенту
  Задержка: RTT до secondary (~1ms в одном DC, ~10ms между DC)
  Гарантия: нет потери данных при crash primary
```

```python
# Демонстрация задержки sync vs async репликации
import asyncio
import time

async def async_replication_write(primary, secondary):
    """Асинхронная репликация: не ждём secondary"""
    start = time.monotonic()
    
    # Запись на primary
    await primary.write(key="x", value=42)
    ack_time = time.monotonic() - start
    
    # Репликация в фоне
    asyncio.create_task(secondary.replicate(key="x", value=42))
    
    return ack_time  # ~0.1ms

async def sync_replication_write(primary, secondary):
    """Синхронная репликация: ждём подтверждения secondary"""
    start = time.monotonic()
    
    # Запись на primary
    await primary.write(key="x", value=42)
    
    # Ждём подтверждения secondary (добавляет RTT)
    await secondary.replicate_and_ack(key="x", value=42)
    
    ack_time = time.monotonic() - start
    return ack_time  # ~1-10ms в зависимости от RTT
```

---

## 5. Уровни согласованности: иерархия гарантий

### 5.1 Спектр согласованности

Между linearizability (сильнейшая) и eventual consistency (слабейшая) существует целый спектр:

```
Сильнее ◄──────────────────────────────────────────► Слабее

Linearizability → Sequential → Causal → Read-your-writes → Eventual
     │                │           │              │               │
  Одна глобальная   Программный  Причинно-    Свои записи    В конечном
  линия порядка     порядок      следственная всегда видны   счёте всё
                    соблюдён     упорядочен               согласуется
```

### 5.2 Read-your-writes consistency

Практически важная гарантия: пользователь всегда видит результат своих собственных записей, даже если другие пользователи получают устаревшие данные.

```python
class SessionConsistency:
    """Read-your-writes через sticky sessions"""
    
    def __init__(self, cluster_nodes):
        self.nodes = cluster_nodes
        self.session_node = {}  # session_id → primary node
    
    def write(self, session_id: str, key: str, value):
        node = self.get_primary(session_id)
        node.write(key, value)
        self.session_node[session_id] = node
    
    def read(self, session_id: str, key: str):
        # Читаем с того же узла, куда писали
        node = self.session_node.get(session_id, self.get_any_node())
        return node.read(key)
    
    def get_primary(self, session_id: str):
        # Consistent hashing по session_id
        import hashlib
        h = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
        return self.nodes[h % len(self.nodes)]
```

### 5.3 Causal consistency через vector clocks

Причинная согласованность (causal consistency) гарантирует: если операция B зависит от A (B прочитала результат A), то любой узел, видящий B, видит и A.

```python
from dataclasses import dataclass, field
from typing import Dict

@dataclass 
class VectorClock:
    clocks: Dict[str, int] = field(default_factory=dict)
    
    def increment(self, node_id: str):
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1
        return VectorClock(dict(self.clocks))
    
    def merge(self, other: 'VectorClock') -> 'VectorClock':
        merged = {}
        all_nodes = set(self.clocks) | set(other.clocks)
        for node in all_nodes:
            merged[node] = max(
                self.clocks.get(node, 0),
                other.clocks.get(node, 0)
            )
        return VectorClock(merged)
    
    def happened_before(self, other: 'VectorClock') -> bool:
        """self → other (self causally precedes other)"""
        all_nodes = set(self.clocks) | set(other.clocks)
        return all(
            self.clocks.get(n, 0) <= other.clocks.get(n, 0)
            for n in all_nodes
        ) and any(
            self.clocks.get(n, 0) < other.clocks.get(n, 0)
            for n in all_nodes
        )
    
    def concurrent(self, other: 'VectorClock') -> bool:
        """Конкурентные события — ни одно не предшествует другому"""
        return not self.happened_before(other) and not other.happened_before(self)

# Пример
vc_a = VectorClock({'A': 1, 'B': 0})
vc_b = VectorClock({'A': 1, 'B': 1})
vc_c = VectorClock({'A': 2, 'B': 0})

print(vc_a.happened_before(vc_b))  # True: A→B
print(vc_b.concurrent(vc_c))       # True: конкурентны
```

---

## 6. Практические сценарии и выбор стратегии

### 6.1 Банковский перевод: CP обязателен

```
Требование: списание денег со счёта A и зачисление на счёт B — атомарно и согласованно
CAP: CP — при разбиении лучше отказать, чем допустить двойное списание
PACELC: PC/EC — готовы платить задержкой ради согласованности

Реализация: PostgreSQL с синхронной репликацией или распределённые транзакции
```

### 6.2 Счётчик лайков: AP допустим

```
Требование: подсчёт лайков поста, небольшое расхождение между серверами допустимо
CAP: AP — лучше показать «1023» вместо «1024», чем вернуть ошибку
PACELC: PA/EL — максимальная скорость записи

Реализация: Redis INCR с периодической синхронизацией, или Cassandra Counter
```

### 6.3 Корзина покупок: AP с разрешением конфликтов

Amazon использует DynamoDB (AP-система) для корзины покупок. При конфликте между двумя версиями корзины — объединяются все товары (CRDT-стратегия merge), теряя информацию об удалении.

```python
class ShoppingCart:
    """CRDT-based shopping cart: Add-wins strategy"""
    
    def __init__(self):
        self.items: Dict[str, int] = {}  # item_id → quantity
        self.removed: set = set()
    
    def add(self, item_id: str, quantity: int = 1):
        self.items[item_id] = self.items.get(item_id, 0) + quantity
        self.removed.discard(item_id)
    
    def remove(self, item_id: str):
        self.removed.add(item_id)
        self.items.pop(item_id, None)
    
    def merge(self, other: 'ShoppingCart') -> 'ShoppingCart':
        """Merge двух корзин после разбиения: Add wins"""
        result = ShoppingCart()
        all_items = set(self.items) | set(other.items)
        
        for item_id in all_items:
            qty = max(
                self.items.get(item_id, 0),
                other.items.get(item_id, 0)
            )
            if qty > 0 and item_id not in (self.removed & other.removed):
                result.items[item_id] = qty
        
        result.removed = self.removed & other.removed  # удалено в обоих
        return result

cart1 = ShoppingCart()
cart1.add('apple', 3)
cart1.add('bread', 1)

cart2 = ShoppingCart()  # изолированная реплика
cart2.add('milk', 2)
cart2.remove('bread')  # пользователь удалил в другой вкладке

merged = cart1.merge(cart2)
# items: {apple: 3, milk: 2, bread: 1}
# bread выжил! add-wins стратегия — при сомнении оставляем
```

### 6.4 DNS: AP система с TTL-based expiry

DNS — классический пример AP-системы. При разбиении DNS-серверы продолжают обслуживать запросы из кеша. Когда запись обновляется (например, смена IP-адреса), старые значения ещё живут в кешах по всему миру в течение TTL. Это eventual consistency с явным временем сходимости (TTL).

---

## 7. Практические инструменты оценки согласованности

### 7.1 Jepsen: тестирование распределённых систем

Jepsen — фреймворк от Kyle Kingsbury (aphyr) для проверки реальных баз данных на соответствие заявленным гарантиям согласованности. Принцип: инжектировать разбиения сети, убийства процессов, замедление часов — и проверять инварианты.

Исторические находки Jepsen:
- MongoDB 2.x терял данные при разбиении сети
- Cassandra 2.x нарушала linearizability даже при QUORUM
- Redis Sentinel не обеспечивал гарантированного failover
- VoltDB нарушала собственные гарантии serializable isolation

### 7.2 Модели согласованности в теоретических работах

**Sequential Consistency** (Lamport, 1979): операции выглядят так, как будто выполняются в некотором глобальном последовательном порядке, совместимом с программным порядком каждого процесса.

**Linearizability** (Herlihy & Wing, 1990): операции выглядят атомарными в реальном времени. Если операция A завершилась до начала B, то A предшествует B в глобальном порядке.

**Serializability**: все транзакции выполняются так, как если бы они выполнялись последовательно в некотором порядке.

**Strict Serializability** = Serializability + Linearizability: самая сильная гарантия, предоставляемая Google Spanner через TrueTime.

---

## 8. Google Spanner: CP + EL через физические часы

Google Spanner — интересное исключение: система утверждает, что обеспечивает external consistency ($\approx$ strict serializability) при масштабировании на тысячи узлов по всему миру.

Ключевая идея — **TrueTime API**: каждый датацентр оснащён атомными часами и GPS-приёмниками. TrueTime возвращает интервал `[t_earliest, t_latest]`, гарантируя, что реальное время находится в этом интервале. Ширина интервала — обычно < 7 мс.

При коммите транзакции Spanner ждёт `t_latest` (Commit Wait), гарантируя, что все будущие транзакции получат timestamp позже коммита. Это превращает физическое время в логическое — без Lamport-часов.

Цена: задержка коммита = ~14 мс (двойной TrueTime interval). Это PC/EC по PACELC с низкой задержкой благодаря физической инфраструктуре.

---

## 9. Итоговая схема принятия решений

```
Нужна ли распределённая система?
│
├─ Нет → Один сервер, PostgreSQL/MySQL (CA: ACID без сети)
│
└─ Да → Что важнее при разбиении сети?
        │
        ├─ Согласованность (CP) → HBase, etcd, Zookeeper, MongoDB(w:majority)
        │   Примеры: финансовые транзакции, критические конфигурации
        │
        └─ Доступность (AP) → Cassandra, DynamoDB, CouchDB
            Примеры: социальные сети, кеш, IoT-данные
            │
            └─ В нормальном режиме: задержка или согласованность?
                ├─ Задержка (EL) → Async репликация, local reads
                └─ Согласованность (EC) → Sync/quorum репликация
```

---

## Заключение

Теорема CAP и расширение PACELC — это не рецепты, а инструменты анализа. Они помогают формализовать компромиссы, которые неизбежны в любой распределённой системе.

CAP учит: при разбиении сети выбирай — согласованность или доступность. PACELC добавляет: даже без разбиений, синхронная согласованность стоит задержки.

Реальные системы не чёрно-белые: Cassandra с QUORUM ведёт себя как CP, DynamoDB с strong consistency — тоже. Выбор конкретной СУБД зависит от требований конкретного сервиса, и разные компоненты одного приложения могут использовать разные стратегии.

Важно понимать: не бывает «лучшей» системы — бывает система, соответствующая требованиям конкретного сценария использования.

---

## Библиография

1. Brewer, E. (2000). Towards Robust Distributed Systems (keynote). *PODC 2000*. ACM.
2. Gilbert, S., & Lynch, N. (2002). Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services. *ACM SIGACT News*, 33(2), 51–59.
3. Abadi, D. (2012). Consistency Tradeoffs in Modern Distributed Database System Design: CAP is Only Part of the Story. *IEEE Computer*, 45(2), 37–42.
4. Herlihy, M., & Wing, J. (1990). Linearizability: A Correctness Condition for Concurrent Objects. *ACM Transactions on Programming Languages and Systems*, 12(3), 463–492.
5. Corbett, J., et al. (2013). Spanner: Google's Globally Distributed Database. *ACM Transactions on Computer Systems*, 31(3), Article 8.
6. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media. Chapter 9.
7. Kingsbury, K. (2013–2024). Jepsen: Distributed Systems Safety Analysis. https://jepsen.io/
8. Vogels, W. (2009). Eventually Consistent. *Communications of the ACM*, 52(1), 40–44.
