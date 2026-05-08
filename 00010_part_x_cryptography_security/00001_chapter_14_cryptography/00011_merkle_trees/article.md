# Деревья Меркла: Git, блокчейн, верификация данных

## Введение

Дерево Меркла (Merkle tree) — криптографическая структура данных, изобретённая Ральфом Меркелем (Ralph Merkle) в 1979 году. Это бинарное дерево, в котором каждый листовой узел содержит хеш блока данных, а каждый нелистовой узел — хеш своих дочерних узлов. Корень дерева (Merkle root) является «подписью» всего набора данных: он криптографически аутентифицирует всю коллекцию.

Деревья Меркла широко применяются: в Git для хранения объектов репозитория, в блокчейне Bitcoin и Ethereum для хеширования транзакций в блоке, в Certificate Transparency для верификации сертификатов, в BitTorrent для верификации файловых частей, в AWS DynamoDB для anti-entropy репликации. Главное преимущество — доказательство включения элемента за O(log n) без скачивания всего набора данных.

---

## 1. Структура дерева Меркла

### Построение

Дерево Меркла строится снизу вверх:

1. Разбиваем данные на блоки (листья)
2. Хешируем каждый блок: `L_i = H(data_i)`
3. Родительские узлы: `P = H(left_child || right_child)`
4. Продолжаем до корня

```
Данные: [D₁, D₂, D₃, D₄]

Листья:    H(D₁)    H(D₂)    H(D₃)    H(D₄)

Уровень 1: H(H(D₁) || H(D₂))    H(H(D₃) || H(D₄))

Корень:    H( H(H(D₁)||H(D₂)) || H(H(D₃)||H(D₄)) )
```

Если число элементов нечётное — последний элемент дублируется (или используются специальные схемы для нечётных деревьев).

```python
import hashlib
from typing import List, Optional

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def sha256_pair(left: bytes, right: bytes) -> bytes:
    return sha256(left + right)

class MerkleTree:
    """Реализация дерева Меркла"""
    
    def __init__(self, data_blocks: List[bytes]):
        if not data_blocks:
            raise ValueError("Нужен хотя бы один блок данных")
        
        # Листья — хеши данных
        self.leaves = [sha256(block) for block in data_blocks]
        self.data = data_blocks
        
        # Строим дерево
        self.layers = self._build_tree(self.leaves)
        self.root = self.layers[-1][0]
    
    def _build_tree(self, leaves: List[bytes]) -> List[List[bytes]]:
        """Строим все уровни дерева"""
        layers = [leaves[:]]  # Сохраняем каждый уровень
        
        current_layer = leaves[:]
        
        while len(current_layer) > 1:
            next_layer = []
            
            # Если нечётное количество — дублируем последний
            if len(current_layer) % 2 == 1:
                current_layer.append(current_layer[-1])
            
            # Попарно хешируем
            for i in range(0, len(current_layer), 2):
                parent = sha256_pair(current_layer[i], current_layer[i+1])
                next_layer.append(parent)
            
            layers.append(next_layer)
            current_layer = next_layer
        
        return layers
    
    def get_root(self) -> bytes:
        return self.root
    
    def get_proof(self, index: int) -> List[tuple[bytes, str]]:
        """Merkle proof для элемента с данным индексом"""
        proof = []
        
        for layer_idx, layer in enumerate(self.layers[:-1]):
            # Определяем sibling (соседний узел)
            if index % 2 == 0:  # Текущий узел — левый
                sibling_idx = index + 1
                if sibling_idx >= len(layer):
                    sibling_idx = index  # Дублированный
                proof.append((layer[sibling_idx], 'right'))
            else:  # Текущий узел — правый
                sibling_idx = index - 1
                proof.append((layer[sibling_idx], 'left'))
            
            index = index // 2  # Переходим на уровень выше
        
        return proof
    
    def verify_proof(
        self, data: bytes, index: int,
        proof: List[tuple[bytes, str]], root: bytes
    ) -> bool:
        """Верификация Merkle proof"""
        current = sha256(data)
        
        for sibling, direction in proof:
            if direction == 'right':
                current = sha256_pair(current, sibling)
            else:
                current = sha256_pair(sibling, current)
        
        return current == root

# Демонстрация
data_blocks = [
    b"transaction 1: Alice sends 10 BTC to Bob",
    b"transaction 2: Bob sends 5 BTC to Carol",
    b"transaction 3: Carol sends 2 BTC to Dave",
    b"transaction 4: Dave sends 1 BTC to Eve",
]

tree = MerkleTree(data_blocks)
print(f"Merkle root: {tree.get_root().hex()[:32]}...")

# Доказательство включения для транзакции 1 (index=1)
proof = tree.get_proof(1)
print(f"\nMerkle proof для транзакции 2:")
for sibling, direction in proof:
    print(f"  {direction}: {sibling.hex()[:16]}...")

# Верификация
is_valid = tree.verify_proof(data_blocks[1], 1, proof, tree.get_root())
print(f"\nДоказательство верно: {is_valid}")

# Попытка с изменёнными данными
is_invalid = tree.verify_proof(b"FAKE TRANSACTION", 1, proof, tree.get_root())
print(f"Поддельные данные: {is_invalid}")  # False
```

---

## 2. Merkle Proof — доказательство включения

### Принцип

Merkle proof позволяет доказать, что элемент `D_i` включён в дерево с корнем `R`, предоставив только O(log n) хешей (путь от листа до корня).

```
Дерево из 8 элементов:
                    ROOT
                /           \
           H₀₁₂₃           H₄₅₆₇
          /       \         /      \
        H₀₁      H₂₃    H₄₅      H₆₇
       /   \    /   \   /   \    /   \
      H₀  H₁  H₂  H₃  H₄  H₅  H₆  H₇

Proof для H₂ (index=2):
  1. Предоставляем: H₃ (sibling)
  2. Предоставляем: H₀₁ (sibling уровнем выше)
  3. Предоставляем: H₄₅₆₇ (sibling корневого уровня)

Верификация:
  H₂₃ = H(H₂ || H₃)
  H₀₁₂₃ = H(H₀₁ || H₂₃)
  ROOT' = H(H₀₁₂₃ || H₄₅₆₇)
  Проверяем: ROOT' == ROOT?
```

Для дерева из n листьев:
- Размер proof: O(log n) хешей
- Время верификации: O(log n) операций хеширования
- Нет необходимости скачивать все n элементов!

### Практическое применение

```python
def demo_light_client_verification():
    """
    Демонстрация верификации отдельной транзакции без скачивания
    всего блока (light client / SPV)
    """
    # "Сервер" имеет полный блок
    transactions = [
        f"tx_{i}: user_{i} sends {i*10} coins".encode()
        for i in range(1024)  # 1024 транзакции
    ]
    
    full_tree = MerkleTree(transactions)
    merkle_root = full_tree.get_root()
    
    print(f"Полный блок: {len(transactions)} транзакций")
    print(f"Merkle root: {merkle_root.hex()[:16]}...")
    
    # "Лёгкий клиент" (light client/SPV wallet) хочет проверить конкретную транзакцию
    tx_index = 42
    target_tx = transactions[tx_index]
    
    # Сервер предоставляет только Merkle proof (log2(1024) = 10 хешей)
    proof = full_tree.get_proof(tx_index)
    print(f"\nLight client получил {len(proof)} хешей вместо {len(transactions)}")
    print(f"Размер proof: {len(proof) * 32} байт (vs {len(transactions) * 32} байт)")
    
    # Клиент самостоятельно верифицирует транзакцию
    is_valid = full_tree.verify_proof(target_tx, tx_index, proof, merkle_root)
    print(f"Транзакция #{tx_index} включена в блок: {is_valid}")

demo_light_client_verification()
```

---

## 3. Git и деревья Меркла

### Объектная модель Git

Git хранит данные как **content-addressable storage**: каждый объект идентифицируется SHA-1 (или SHA-256) хешем своего содержимого. Четыре типа объектов:

1. **blob** — содержимое файла: `sha1("blob " + len + "\0" + content)`
2. **tree** — содержимое директории: список записей `(mode, filename, sha1_of_child)`
3. **commit** — снимок с метаданными: ссылки на tree + parent commit + автор + сообщение
4. **tag** — аннотированный тег

```python
import hashlib
import struct
import os
from typing import List, Tuple

def git_hash_object(content: bytes, obj_type: str = "blob") -> str:
    """Вычисление Git SHA-1 для объекта"""
    header = f"{obj_type} {len(content)}\0".encode()
    full_content = header + content
    return hashlib.sha1(full_content).hexdigest()

# Демонстрация
file_content = b"Hello, Git!\n"
blob_sha = git_hash_object(file_content)
print(f"blob SHA1: {blob_sha}")
# Совпадёт с `git hash-object` для того же содержимого!

# Commit содержит дерево (Merkle tree директорий) + родительский коммит
commit_content = f"""tree {blob_sha}
parent 0000000000000000000000000000000000000000
author Alice <alice@example.com> 1704067200 +0000
committer Alice <alice@example.com> 1704067200 +0000

Initial commit
""".encode()

commit_sha = git_hash_object(commit_content, "commit")
print(f"commit SHA1: {commit_sha}")
```

### DAG коммитов — дерево Меркла репозитория

Каждый коммит ссылается на:
- tree объект (снимок файловой системы)
- parent commit(ы) (предыдущие снимки)

Это образует DAG (Directed Acyclic Graph) — по сути дерево Меркла коммитов. Свойства:

1. **Целостность:** изменение любого файла изменяет tree хеш, что изменяет commit хеш, что изменяет все дочерние коммиты
2. **История неизменяема:** нельзя тайно изменить прошлый коммит — изменится весь дальнейший граф
3. **Distributed verification:** любой клон репозитория может независимо верифицировать историю

```bash
# Просмотр объектов Git
git cat-file -t HEAD          # Тип объекта
git cat-file -p HEAD          # Содержимое коммита
git cat-file -p HEAD^{tree}   # Дерево файлов
git cat-file -p HEAD:filename # Содержимое файла

# Граф коммитов
git log --graph --oneline
git log --format="%H %T %P"  # commit_hash tree_hash parent_hash
```

---

## 4. Блокчейн и деревья Меркла

### Bitcoin Block Structure

В Bitcoin каждый блок содержит:

```
Block Header (80 байт):
├── version (4 байт)
├── prev_block_hash (32 байт) — хеш предыдущего блока
├── merkle_root (32 байт) — корень дерева Меркла транзакций
├── timestamp (4 байт)
├── bits (4 байт) — цель сложности
└── nonce (4 байт) — для Proof-of-Work

Block Body:
└── transactions[...] — список транзакций
```

Merkle root в заголовке блока аутентифицирует все транзакции. Майнеры хешируют только заголовок (80 байт) при PoW, но Merkle root в нём включает все транзакции.

```python
def bitcoin_merkle_root(txids: List[bytes]) -> bytes:
    """Вычисление Bitcoin Merkle root"""
    def double_sha256(data: bytes) -> bytes:
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()
    
    if not txids:
        return bytes(32)
    
    # Bitcoin uses little-endian txids
    hashes = [txid for txid in txids]
    
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])  # Дублируем последний
        
        next_level = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i] + hashes[i+1]
            next_level.append(double_sha256(combined))
        
        hashes = next_level
    
    return hashes[0]

# SPV (Simplified Payment Verification) в Bitcoin
# Лёгкий кошелёк загружает только заголовки блоков (~80 МБ всей цепочки)
# и Merkle proofs для интересующих транзакций
# Не нужно скачивать весь blockchain (~500 ГБ)
```

### Ethereum: Patricia-Merkle Trie

Ethereum использует более сложную структуру — **Merkle Patricia Trie** (Hexary Trie), которая объединяет:
- Хеш-дерево Меркла (для верификации)
- Patricia trie (для эффективного поиска по ключу)

Корни Patricia Tries хранятся в заголовке блока:
- `stateRoot` — состояние всех аккаунтов
- `transactionsRoot` — дерево транзакций
- `receiptsRoot` — дерево квитанций транзакций

---

## 5. Certificate Transparency Logs

Certificate Transparency (RFC 9162) — публичный, append-only лог, основанный на Merkle дереве:

```
CT Log: постоянно растущее Merkle tree сертификатов

Когда CA выдаёт сертификат:
1. Отправляет его в CT log
2. CT log добавляет сертификат в дерево
3. CT log возвращает SCT (Signed Certificate Timestamp):
   - Хеш включения (Merkle proof)
   - Подпись log сервера
   - Timestamp

Браузер проверяет:
1. Сертификат содержит SCT от ≥ 2 различных CT логов
2. Merkle proof корректен → сертификат действительно в логе
```

**Consistency proof** — CT logs используют Merkle дерево для доказательства того, что лог только добавляет записи, но не модифицирует существующие.

```
Дерево в момент t1: корень R1 (n1 листьев)
Дерево в момент t2: корень R2 (n2 > n1 листьев)

Consistency proof: доказательство того, что 
первые n1 листьев в t2 идентичны всем листьям в t1
(т.е. данные не были изменены/удалены)
```

---

## 6. BitTorrent и верификация частей

BitTorrent использует Merkle tree (в BitTorrent v2, BEP 52) для верификации частей файла:

```python
def torrent_piece_hash(piece_data: bytes) -> bytes:
    """Bitcoin-style SHA1 хеш части в BitTorrent v1"""
    return hashlib.sha1(piece_data).digest()

class TorrentFile:
    """Упрощённая модель torrent файла"""
    
    def __init__(self, file_path: str, piece_size: int = 512 * 1024):
        self.piece_size = piece_size
        self.pieces = []
        
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(piece_size)
                if not chunk:
                    break
                self.pieces.append(chunk)
        
        # В BitTorrent v2: Merkle tree хешей 16KB блоков
        # Позволяет верифицировать маленькие блоки, не весь piece
        self.piece_hashes = [torrent_piece_hash(p) for p in self.pieces]
    
    def verify_piece(self, index: int, received_data: bytes) -> bool:
        """Верификация полученной части"""
        computed_hash = torrent_piece_hash(received_data)
        return computed_hash == self.piece_hashes[index]
```

---

## 7. Amazon DynamoDB: Anti-entropy через деревья Меркла

В распределённых NoSQL базах данных реплики могут расходиться. DynamoDB (и Apache Cassandra) используют деревья Меркла для **anti-entropy** — процесса обнаружения и исправления расхождений между репликами:

1. Каждая реплика строит Merkle tree своих данных для конкретного key range
2. Реплики обмениваются **корнями** деревьев (1 хеш)
3. Если корни совпадают — реплики синхронизированы
4. Если различаются — бинарный поиск по дереву для нахождения расходящегося поддиапазона
5. Только расходящиеся данные передаются для синхронизации

```python
class AntiEntropyMerkle:
    """
    Демонстрация Anti-entropy через Merkle tree
    """
    
    def __init__(self, key_value_store: dict):
        self.store = key_value_store
        self._build_tree()
    
    def _build_tree(self):
        """Строим Merkle tree из key-value хранилища"""
        sorted_items = sorted(self.store.items())
        
        if not sorted_items:
            self.root = bytes(32)
            self.leaf_hashes = []
            return
        
        self.leaf_hashes = [
            sha256(k.encode() + v.encode())
            for k, v in sorted_items
        ]
        
        self.tree = MerkleTree([k.encode() + v.encode() for k, v in sorted_items])
        self.root = self.tree.get_root()
    
    def sync_needed(self, other_root: bytes) -> bool:
        """Быстрая проверка: нужна ли синхронизация?"""
        return self.root != other_root
    
    def find_differences(self, other: 'AntiEntropyMerkle') -> List[str]:
        """Находим различающиеся ключи"""
        if self.root == other.root:
            return []
        
        diffs = []
        sorted_keys = sorted(self.store.keys())
        
        for i, (key, value) in enumerate(sorted(self.store.items())):
            if i < len(other.leaf_hashes):
                if self.leaf_hashes[i] != other.leaf_hashes[i]:
                    diffs.append(key)
            else:
                diffs.append(key)  # Ключ есть только у нас
        
        return diffs

# Демонстрация
replica1 = AntiEntropyMerkle({
    "user:1": "Alice",
    "user:2": "Bob",
    "user:3": "Carol",
    "user:4": "Dave",
})

replica2 = AntiEntropyMerkle({
    "user:1": "Alice",
    "user:2": "Bob_MODIFIED",  # Расходится!
    "user:3": "Carol",
    "user:4": "Dave",
})

print(f"Корень реплики 1: {replica1.root.hex()[:16]}...")
print(f"Корень реплики 2: {replica2.root.hex()[:16]}...")
print(f"Синхронизация нужна: {replica1.sync_needed(replica2.root)}")
print(f"Различающиеся ключи: {replica1.find_differences(replica2)}")
```

---

## 8. Уязвимости деревьев Меркла

### Second preimage attack

Если хеш узла может совпасть с хешем листа, атакующий может сконструировать поддельное дерево:

```
Атака:
Лист L = H(data)
Внутренний узел N = H(left || right)

Если N == L для каких-то значений → можно подменить лист на узел!
```

**Защита:** Используйте разные prefix для листов и внутренних узлов:
- Лист: `H(0x00 || data)`
- Узел: `H(0x01 || left || right)`

```python
def safe_leaf_hash(data: bytes) -> bytes:
    return sha256(b'\x00' + data)

def safe_node_hash(left: bytes, right: bytes) -> bytes:
    return sha256(b'\x01' + left + right)
```

---

## Заключение

Деревья Меркла — элегантная структура данных, объединяющая криптографические хеши с бинарным деревом. Они обеспечивают эффективную (O(log n)) верификацию данных без необходимости хранить или передавать весь набор данных.

Ключевые применения:
1. **Git:** content-addressable storage, неизменяемая история
2. **Блокчейн:** аутентификация транзакций в блоке, SPV-клиенты
3. **Certificate Transparency:** публичный append-only лог сертификатов
4. **BitTorrent:** верификация частей при скачивании
5. **Распределённые БД:** anti-entropy синхронизация реплик

---

## Литература и источники

1. Merkle, R.C. (1979). *Secrecy, Authentication, and Public Key Systems*. Stanford Ph.D. thesis. http://www.merkle.com/papers/Thesis1979.pdf
2. Nakamoto, S. (2008). *Bitcoin: A Peer-to-Peer Electronic Cash System*. https://bitcoin.org/bitcoin.pdf
3. RFC 9162. (2021). *Certificate Transparency Version 2.0*. IETF. https://www.rfc-editor.org/rfc/rfc9162
4. DeCandia, G., et al. (2007). *Dynamo: Amazon's Highly Available Key-value Store*. ACM SOSP 2007. https://dl.acm.org/doi/10.1145/1294261.1294281
5. Laurie, B., et al. RFC 6962. (2013). *Certificate Transparency*. IETF. https://www.rfc-editor.org/rfc/rfc6962
6. BEP 52. *The BitTorrent Protocol Specification v2*. https://www.bittorrent.org/beps/bep_0052.html
7. Git internals. *Git Objects*. https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
8. Wikipedia: Merkle tree. https://en.wikipedia.org/wiki/Merkle_tree
9. Wood, G. (2014). *Ethereum: A Secure Decentralised Generalised Transaction Ledger*. https://ethereum.github.io/yellowpaper/paper.pdf
