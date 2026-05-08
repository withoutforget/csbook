# Деревья: BST, AVL, Red-Black, B-tree, B+ tree

Деревья — одна из самых универсальных структур данных. Бинарные деревья поиска обеспечивают O(log n) операции; AVL и Red-Black деревья гарантируют этот предел даже в худшем случае; B+ деревья лежат в основе индексов каждой реляционной базы данных. Понимание деревьев — понимание того, как устроена вся иерархическая обработка данных.

## Бинарное дерево поиска (BST)

BST — бинарное дерево, удовлетворяющее **свойству BST**: для каждого узла все ключи в левом поддереве меньше ключа узла, все в правом — больше.

```
        8
       / \
      3   10
     / \    \
    1   6    14
       / \   /
      4   7  13
```

```python
from typing import Optional, Generic, TypeVar
from dataclasses import dataclass

K = TypeVar('K')
V = TypeVar('V')

@dataclass
class BSTNode:
    key: int
    value: object
    left: Optional['BSTNode'] = None
    right: Optional['BSTNode'] = None

class BST:
    def __init__(self):
        self.root: Optional[BSTNode] = None
    
    def search(self, key: int) -> Optional[object]:
        """O(h) — h высота дерева"""
        node = self.root
        while node:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return node.value
        return None
    
    def insert(self, key: int, value: object):
        """O(h)"""
        if not self.root:
            self.root = BSTNode(key, value)
            return
        
        node = self.root
        while True:
            if key < node.key:
                if node.left is None:
                    node.left = BSTNode(key, value)
                    return
                node = node.left
            elif key > node.key:
                if node.right is None:
                    node.right = BSTNode(key, value)
                    return
                node = node.right
            else:
                node.value = value  # обновляем
                return
    
    def inorder(self) -> list:
        """Обход в отсортированном порядке: O(n)"""
        result = []
        def _inorder(node):
            if node:
                _inorder(node.left)
                result.append((node.key, node.value))
                _inorder(node.right)
        _inorder(self.root)
        return result

# Тест
bst = BST()
for key in [8, 3, 10, 1, 6, 14, 4, 7, 13]:
    bst.insert(key, f"val_{key}")
print(bst.inorder())  # [(1,...), (3,...), (4,...), ...] — отсортировано!
print(bst.search(6))   # val_6
```

### Удаление из BST

Удаление — самая сложная операция BST. Три случая:

```python
def delete(self, key: int):
    """O(h)"""
    self.root = self._delete(self.root, key)

def _delete(self, node: Optional[BSTNode], key: int) -> Optional[BSTNode]:
    if node is None:
        return None
    
    if key < node.key:
        node.left = self._delete(node.left, key)
    elif key > node.key:
        node.right = self._delete(node.right, key)
    else:
        # Нашли узел для удаления
        if node.left is None:
            return node.right     # случай 1: нет левого поддерева
        elif node.right is None:
            return node.left      # случай 2: нет правого поддерева
        else:
            # Случай 3: два потомка
            # Находим inorder successor (минимум в правом поддереве)
            min_node = self._find_min(node.right)
            node.key = min_node.key
            node.value = min_node.value
            node.right = self._delete(node.right, min_node.key)
    
    return node

def _find_min(self, node: BSTNode) -> BSTNode:
    while node.left:
        node = node.left
    return node
```

### Проблема деградации BST

BST в худшем случае превращается в список:

```
Вставка в порядке: 1, 2, 3, 4, 5, 6, 7

1
 \
  2
   \
    3
     \
      4
       \
        5
...высота = n, поиск = O(n)!
```

## AVL деревья: строгая балансировка

AVL-дерево (Адельсон-Вельский и Ландис, 1962) — первое самобалансирующееся BST. Инвариант: **разница высот левого и правого поддеревьев любого узла ≤ 1**.

Высота AVL-дерева: O(log n). Точнее: h ≤ 1.44 · log₂(n+2) − 0.328.

### Балансировочный фактор

```python
@dataclass
class AVLNode:
    key: int
    value: object
    height: int = 1
    left: Optional['AVLNode'] = None
    right: Optional['AVLNode'] = None

def height(node):
    return node.height if node else 0

def balance_factor(node):
    return height(node.left) - height(node.right)

def update_height(node):
    node.height = 1 + max(height(node.left), height(node.right))
```

### Вращения в AVL

При нарушении баланса выполняем одно из четырёх вращений:

```python
def rotate_right(y):
    """
        y              x
       / \            / \
      x   T3   →    T1   y
     / \                / \
    T1  T2            T2   T3
    """
    x = y.left
    T2 = x.right
    
    x.right = y
    y.left = T2
    
    update_height(y)
    update_height(x)
    
    return x  # новый корень поддерева

def rotate_left(x):
    """Зеркальное rotate_right"""
    y = x.right
    T2 = y.left
    
    y.left = x
    x.right = T2
    
    update_height(x)
    update_height(y)
    
    return y

def rebalance(node):
    update_height(node)
    bf = balance_factor(node)
    
    # Случай 1: Left-Left (право-вращение)
    if bf > 1 and balance_factor(node.left) >= 0:
        return rotate_right(node)
    
    # Случай 2: Right-Right (лево-вращение)
    if bf < -1 and balance_factor(node.right) <= 0:
        return rotate_left(node)
    
    # Случай 3: Left-Right (двойное: сначала лево, потом право)
    if bf > 1 and balance_factor(node.left) < 0:
        node.left = rotate_left(node.left)
        return rotate_right(node)
    
    # Случай 4: Right-Left (двойное: сначала право, потом лево)
    if bf < -1 and balance_factor(node.right) > 0:
        node.right = rotate_right(node.right)
        return rotate_left(node)
    
    return node  # узел уже сбалансирован
```

### Когда использовать AVL

AVL строже балансирован чем Red-Black → быстрее поиск, медленнее вставка/удаление (больше вращений).

**Хорошо для:** read-heavy рабочих нагрузок, где поиск критичен.

## Red-Black деревья: менее строгая балансировка

Red-Black tree (Гийо и Седжвик, 1978) — балансирующееся BST с менее строгим инвариантом. Ключевые правила:

1. Каждый узел — красный или чёрный
2. Корень — чёрный
3. Красный узел не может иметь красного потомка
4. Все пути от узла до NIL-листа имеют одинаковое количество чёрных узлов

Гарантия: высота ≤ 2·log₂(n+1) — O(log n), но с большей константой чем AVL.

```python
RED = True
BLACK = False

@dataclass
class RBNode:
    key: int
    value: object
    color: bool = RED
    left: Optional['RBNode'] = None
    right: Optional['RBNode'] = None
    parent: Optional['RBNode'] = None
```

### Использование RB деревьев

Red-Black деревья — стандарт для реализаций `std::map` (C++), `TreeMap` (Java), `BTreeMap` (Rust).

```java
// Java TreeMap — это Red-Black дерево
TreeMap<String, Integer> map = new TreeMap<>();
map.put("banana", 2);
map.put("apple", 1);
map.put("cherry", 3);

// Итерация в отсортированном порядке:
for (Map.Entry<String, Integer> e : map.entrySet()) {
    System.out.println(e.getKey() + ": " + e.getValue());
}
// apple: 1, banana: 2, cherry: 3

// Range queries:
map.subMap("apple", "cherry")  // все между apple и cherry
map.headMap("banana")          // все < banana
map.tailMap("banana")          // все >= banana
```

## B-tree: деревья для дисковых структур

B-tree (Bayer и McCreight, 1972) — сбалансированное дерево с большим ветвлением, специально разработанное для эффективной работы с дисковым хранилищем.

### Мотивация: дисковые операции дороги

Чтение с диска в тысячи раз медленнее, чем из памяти. Каждое обращение к диску читает целую **страницу** (обычно 4 КБ или 16 КБ). Значит, нужно минимизировать число обращений к диску = минимизировать высоту дерева.

BST с 1 миллионом элементов: высота ~20, каждый узел — возможно отдельный дисковый блок = 20 операций чтения.

B-tree со степенью t=100: каждый узел содержит до 199 ключей. Высота ≤ log₁₀₀(1 000 000) = 3. Всего 3 операции чтения!

### Структура B-tree

B-tree степени t (minimum degree):
- Каждый узел содержит t-1 до 2t-1 ключей
- Каждый внутренний узел содержит t до 2t потомков
- Все листья на одном уровне
- Корень: минимум 1 ключ, до 2t-1 ключей

```python
@dataclass
class BTreeNode:
    keys: list       # ключи узла
    values: list     # значения (для листьев)
    children: list   # дочерние узлы (для внутренних)
    is_leaf: bool    # является ли листом
    n: int = 0       # текущее количество ключей

class BTree:
    def __init__(self, t: int = 3):  # minimum degree
        self.t = t  # каждый узел: t-1 до 2t-1 ключей
        self.root = BTreeNode([], [], [], True)
    
    def search(self, key: int, node=None):
        """O(log_t n) дисковых операций"""
        if node is None:
            node = self.root
        
        # Ищем позицию ключа в узле
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1
        
        if i < len(node.keys) and key == node.keys[i]:
            return node.values[i]  # нашли!
        
        if node.is_leaf:
            return None  # не нашли
        
        # Рекурсивно в нужное поддерево (= 1 дисковая операция!)
        return self.search(key, node.children[i])
    
    def _split_child(self, parent: BTreeNode, i: int):
        """Разбивает переполненного потомка parent.children[i]"""
        t = self.t
        child = parent.children[i]
        
        # Создаём новый правый узел
        new_node = BTreeNode(
            keys=child.keys[t:],          # правая половина ключей
            values=child.values[t:] if child.is_leaf else [],
            children=child.children[t:] if not child.is_leaf else [],
            is_leaf=child.is_leaf
        )
        
        # Медианный ключ поднимается в родителя
        median_key = child.keys[t-1]
        
        # Обрезаем оригинальный узел
        child.keys = child.keys[:t-1]
        if child.is_leaf:
            child.values = child.values[:t-1]
        else:
            child.children = child.children[:t]
        
        # Вставляем в родителя
        parent.keys.insert(i, median_key)
        parent.children.insert(i+1, new_node)
```

### Почему B-tree хорош для дисков

1. **Высокая степень ветвления:** Тысячи ключей в одном узле = один дисковый блок
2. **Узлы = страницы:** Размер узла ≈ размер страницы диска
3. **Минимальная глубина:** O(log_t n) дисковых операций
4. **Полная балансировка:** Все листья на одной глубине

## B+ дерево: индексы баз данных

B+ дерево — вариация B-tree, где **все данные хранятся только в листьях**. Внутренние узлы содержат только ключи-разделители.

```
B+ tree (степень 3):

Внутренние узлы (только ключи!):
           [10|20]
          /   |   \
      [5|8] [12|15] [22|25]
      /|\ ...

Листья (содержат данные + указатели на соседей):
[1,2,3] → [5,6,8] → [10,11,12] → [15,16] → [20,21,22] → [25,26]
```

### Ключевые отличия B+ от B

1. **Все данные в листьях:** Внутренние узлы — только "указатели", не данные
2. **Листья связаны:** Связный список листьев для range queries
3. **Ключи могут дублироваться:** Ключ из внутреннего узла повторяется в листе

### Преимущества B+ для БД индексов

```sql
-- Range query в SQL:
SELECT * FROM orders WHERE price BETWEEN 100 AND 500;

-- B+ tree: 
-- 1. Найти лист с price=100 (O(log n) сравнений)
-- 2. Пройти по связному списку листьев до price=500
-- Линейно по РЕЗУЛЬТАТУ, а не по всей таблице!

-- B tree НЕ может эффективно делать range queries:
-- нужно посещать внутренние узлы для полного обхода
```

```python
# Концептуальная реализация B+ tree поиска диапазона
def range_query(self, low, high):
    """O(log n + k) где k — количество результатов"""
    # 1. Находим лист, содержащий low
    leaf = self._find_leaf(low)
    
    results = []
    current = leaf
    
    # 2. Идём по связному списку листьев
    while current:
        for key, value in zip(current.keys, current.values):
            if key > high:
                return results  # вышли за диапазон
            if key >= low:
                results.append((key, value))
        current = current.next_leaf  # связный список!
    
    return results
```

### B+ tree в PostgreSQL, MySQL, SQLite

```sql
-- В PostgreSQL: CREATE INDEX использует B-tree по умолчанию
CREATE INDEX idx_orders_price ON orders (price);

-- EXPLAIN показывает использование индекса:
EXPLAIN SELECT * FROM orders WHERE price = 250;
-- Index Scan using idx_orders_price on orders
--   Index Cond: (price = 250)

-- Range query через индекс:
EXPLAIN SELECT * FROM orders WHERE price BETWEEN 100 AND 500;
-- Bitmap Index Scan on idx_orders_price
--   Index Cond: ((price >= 100) AND (price <= 500))
```

## 2-3 tree: простая альтернатива

2-3 дерево — каждый узел имеет 2 или 3 потомка:
- 2-узел: 1 ключ, 2 потомка
- 3-узел: 2 ключа, 3 потомка

Высота строго O(log n). Проще для понимания, чем Red-Black tree. Красно-чёрные деревья — это в некотором смысле "изоморфизм" 2-3-4 деревьев.

## LSM Tree: для write-heavy нагрузок

LSM (Log-Structured Merge-tree) — альтернатива B-tree для систем с высокой интенсивностью записи (Cassandra, LevelDB, RocksDB).

```
Архитектура LSM:

Memory (MemTable): быстрая запись в память
    │ При переполнении → flush
    ▼
L0: SSTable (immutable файл на диске)
    │ При слиянии
    ▼
L1: Более крупные SSTables
    │ При слиянии
    ▼
L2: Ещё более крупные SSTables
    ...
```

```python
# Концептуальный LSM Tree

class MemTable:
    """Память: Red-Black tree или skiplist"""
    def __init__(self, size_limit=1_000_000):
        self.data = {}  # упрощённо
        self.size_limit = size_limit
    
    def put(self, key, value):
        self.data[key] = value
        return len(self.data) >= self.size_limit  # нужен ли flush?
    
    def get(self, key):
        return self.data.get(key)

class LSMTree:
    def __init__(self):
        self.memtable = MemTable()
        self.l0_sstables = []    # уровень 0
        self.l1_sstables = []    # уровень 1
    
    def put(self, key, value):
        need_flush = self.memtable.put(key, value)
        if need_flush:
            self._flush_memtable()
    
    def get(self, key):
        # Ищем в памяти сначала (самые свежие данные)
        value = self.memtable.get(key)
        if value is not None:
            return value
        
        # Затем в L0 (от новых к старым)
        for sstable in reversed(self.l0_sstables):
            value = sstable.get(key)
            if value is not None:
                return value
        
        # Затем в L1, L2...
        return None
    
    def _flush_memtable(self):
        """Flush MemTable в новый SSTable на L0"""
        sstable = SSTable(sorted(self.memtable.data.items()))
        self.l0_sstables.append(sstable)
        self.memtable = MemTable()
        
        if len(self.l0_sstables) >= 4:
            self._compact()  # слияние L0 в L1
```

### B-tree vs LSM: trade-offs

| | B-tree | LSM tree |
|---|--------|---------|
| Запись | Обновление на месте | Всегда append (быстро!) |
| Чтение | O(log n) — быстро | Возможно несколько SSTables |
| Write amplification | Низкое | Высокое (compaction) |
| Read amplification | Низкое | Выше (поиск в нескольких уровнях) |
| Применение | Общее использование | Write-heavy, TimeSeries, KV stores |

## Treap и Splay tree

### Treap

Treap = Tree + Heap. Каждый узел имеет ключ (BST) и приоритет (случайный, min-heap). Это рандомизированное BST с ожидаемой высотой O(log n).

```python
import random
from dataclasses import dataclass

@dataclass
class TreapNode:
    key: int
    value: object
    priority: int = None  # случайный
    left: 'TreapNode' = None
    right: 'TreapNode' = None
    
    def __post_init__(self):
        if self.priority is None:
            self.priority = random.randint(0, 10**9)

# Treap прост в реализации и обеспечивает O(log n) с высокой вероятностью
# Используется в: некоторых реализациях ordered set
```

### Splay tree

Splay tree (Sleator и Tarjan, 1985) — самоорганизующееся BST. При каждом доступе к узлу он "поднимается" к корню через серию вращений. Амортизированная стоимость O(log n).

Преимущество: недавно использованные элементы — у корня = кеш-дружественно для рабочих наборов с локальностью.

## Практический выбор дерева

```
Задача → Структура данных:

Ordered map/set в памяти → Red-Black tree (std::map, TreeMap, BTreeMap)
Поиск-тяжёлые операции → AVL tree
Файловые системы (ext4, NTFS) → B-tree
Индексы БД (PostgreSQL, MySQL) → B+ tree
Write-heavy KV store → LSM tree (RocksDB, LevelDB)
Range queries без DB → Skip list или Sorted array + binary search
Случайные ключи, простота → Treap
```

## Итоги

От простого BST до B+ дерева — прогресс в решении одной проблемы: как обеспечить O(log n) операции при любом порядке вставки и при работе с диском.

- **BST:** Простейший, но O(n) в худшем случае
- **AVL:** Строгая балансировка, O(log n) гарантировано, быстрый поиск
- **Red-Black:** Менее строгий, амортизированно O(log n), стандарт для map/set
- **B-tree:** Высокая степень ветвления для дисков, O(log_t n)
- **B+ tree:** Все данные в листьях + связный список = идеален для range queries
- **LSM tree:** Write-optimized альтернатива для append-heavy нагрузок

## Литература

1. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Главы 12-13 (BST, Red-Black), 18 (B-tree).

2. Adelson-Velsky, G. M., & Landis, E. M. (1962). An algorithm for the organization of information. *Soviet Mathematics Doklady*, 3, 1259–1263. — оригинальная статья об AVL деревьях

3. Bayer, R., & McCreight, E. M. (1972). Organization and maintenance of large ordered indexes. *Acta Informatica*, 1(3), 173–189. — оригинальная статья о B-tree

4. Knuth, D. E. (1998). *The Art of Computer Programming, Vol. 3: Sorting and Searching*. Addison-Wesley. Раздел 6.2.3 — Balanced Trees.

5. Sedgewick, R. (1998). *Algorithms in C++, Part 4: Graph Algorithms* (3rd ed.). Addison-Wesley. — Red-Black trees.

6. O'Neil, P., Cheng, E., Gawlick, D., & O'Neil, E. (1996). The log-structured merge-tree (LSM-tree). *Acta Informatica*, 33(4). https://link.springer.com/article/10.1007/s002360050048

7. PostgreSQL Documentation — Index Types. https://www.postgresql.org/docs/current/indexes-types.html

8. Sleator, D. D., & Tarjan, R. E. (1985). Self-adjusting binary search trees. *Journal of the ACM*, 32(3), 652–686. — splay tree

9. Guibas, L. J., & Sedgewick, R. (1978). A dichromatic framework for balanced trees. *FOCS 1978*. — Red-Black tree

10. LevelDB — LSM Tree implementation. https://github.com/google/leveldb
