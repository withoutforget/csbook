# Trie и суффиксные структуры: строковые задачи и автодополнение

Когда нужно хранить тысячи слов и мгновенно отвечать на вопросы "есть ли такое слово?", "какие слова начинаются на 'pre'?", "где встречается эта подстрока?" — хеш-таблицы и B-деревья уже не так элегантны. Trie (произносится как "try") и суффиксные структуры — специализированные деревья для строковых задач, обеспечивающие O(m) поиск независимо от количества слов, где m — длина строки.

## Trie (Префиксное дерево)

Trie — дерево, где каждый узел представляет символ, путь от корня до узла — это строка. Узлы с флагом "конец слова" — это хранимые слова.

```
Trie для слов: ["car", "cat", "can", "dog", "do"]:

        root
       /    \
      c      d
      |      |
      a      o
     /|\     |\ 
    r  t  n  g  (end)
   (e)(e)(e)(e)

(e) — конец слова
```

### Реализация Trie

```python
from typing import Optional, Dict, List

class TrieNode:
    def __init__(self):
        self.children: Dict[str, TrieNode] = {}
        self.is_end: bool = False
        self.value: object = None  # для хранения произвольных значений

class Trie:
    def __init__(self):
        self.root = TrieNode()
    
    def insert(self, word: str, value=True) -> None:
        """O(m) — m длина слова"""
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.value = value
    
    def search(self, word: str) -> bool:
        """O(m) — точное совпадение"""
        node = self._find_node(word)
        return node is not None and node.is_end
    
    def starts_with(self, prefix: str) -> bool:
        """O(m) — проверить наличие слов с префиксом"""
        return self._find_node(prefix) is not None
    
    def get_words_with_prefix(self, prefix: str) -> List[str]:
        """O(m + k) — все слова с данным префиксом, k слов всего"""
        node = self._find_node(prefix)
        if node is None:
            return []
        
        results = []
        self._collect_words(node, prefix, results)
        return results
    
    def _find_node(self, prefix: str) -> Optional[TrieNode]:
        node = self.root
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node
    
    def _collect_words(self, node: TrieNode, current: str, results: list):
        if node.is_end:
            results.append(current)
        for char, child in sorted(node.children.items()):
            self._collect_words(child, current + char, results)
    
    def delete(self, word: str) -> bool:
        """O(m)"""
        return self._delete(self.root, word, 0)
    
    def _delete(self, node: TrieNode, word: str, depth: int) -> bool:
        if depth == len(word):
            if not node.is_end:
                return False
            node.is_end = False
            return len(node.children) == 0  # можно удалить узел
        
        char = word[depth]
        if char not in node.children:
            return False
        
        should_delete_child = self._delete(node.children[char], word, depth + 1)
        
        if should_delete_child:
            del node.children[char]
            return not node.is_end and len(node.children) == 0
        
        return False

# Тест: автодополнение
trie = Trie()
words = ["apple", "app", "application", "apply", "apt", "banana", "band"]
for w in words: trie.insert(w)

print(trie.search("app"))           # True
print(trie.search("ap"))            # False (не вставляли)
print(trie.starts_with("ap"))       # True

completions = trie.get_words_with_prefix("app")
print(completions)   # ['app', 'apple', 'application', 'apply']
```

### Сложность Trie

| Операция | Время | Память |
|----------|-------|--------|
| Вставка слова длины m | O(m) | $O(m \cdot |\Sigma|)$ |
| Поиск слова длины m | O(m) | — |
| Все слова с префиксом | O(m + k) | — |
| Память | — | $O(N \cdot |\Sigma|)$ |

Где N — суммарная длина всех слов, $|\Sigma|$ — размер алфавита (26 для латиницы).

**Главное преимущество Trie перед хеш-таблицей:** поиск по префиксу — O(m + k). В хеш-таблице это потребовало бы O(n) полного перебора.

## Compressed Trie: Patricia/Radix Tree

Обычный Trie тратит узлы на "вытянутые" пути. Compressed trie (Patricia tree, Radix tree) объединяет одиночные ребра в одну дугу:

```
Обычный Trie для ["car", "cat"]:
root → c → a → r (end)
                └─ t (end)

Radix Tree:
root → "ca" → "r" (end)
                └─ "t" (end)
```

```python
class RadixNode:
    def __init__(self):
        self.children = {}   # первый символ → (prefix, RadixNode)
        self.is_end = False
    
    def find_common_prefix_length(self, s1, s2):
        length = min(len(s1), len(s2))
        for i in range(length):
            if s1[i] != s2[i]:
                return i
        return length

# Radix tree используется в:
# - Linux VFS (inode cache)
# - IP routing tables (longest prefix match!)
# - nginx URL routing
```

### Применение в IP-маршрутизации

Radix tree идеален для маршрутизации IP: нужно найти "наиболее конкретный" (longest matching prefix) маршрут:

```
Таблица маршрутизации (как Radix Tree):
192.168.0.0/16 → gateway A
192.168.1.0/24 → gateway B
192.168.1.128/25 → gateway C

Запрос: куда отправить пакет для 192.168.1.200?
→ Longest prefix match: 192.168.1.128/25 → gateway C
```

## Ternary Search Tree

TST — компромисс между Trie (быстро, много памяти) и BST (медленнее, меньше памяти). Каждый узел хранит один символ и три потомка: меньше, равно, больше.

```python
class TSTNode:
    def __init__(self, char):
        self.char = char
        self.left = None   # символы < char
        self.equal = None  # следующий символ строки
        self.right = None  # символы > char
        self.is_end = False

class TST:
    def __init__(self):
        self.root = None
    
    def insert(self, word):
        self.root = self._insert(self.root, word, 0)
    
    def _insert(self, node, word, idx):
        if idx >= len(word):
            return node
        char = word[idx]
        
        if node is None:
            node = TSTNode(char)
        
        if char < node.char:
            node.left = self._insert(node.left, word, idx)
        elif char > node.char:
            node.right = self._insert(node.right, word, idx)
        else:
            if idx + 1 == len(word):
                node.is_end = True
            else:
                node.equal = self._insert(node.equal, word, idx + 1)
        
        return node

# TST используется для: spell checkers, autocomplete с меньшей памятью
```

## Суффиксный массив

Суффиксный массив (suffix array) — мощная структура для поиска подстрок в строке.

**Суффикс** строки S от позиции i — это S[i..n-1].

Для строки "banana":
```
Суффиксы:
0: banana
1: anana
2: nana
3: ana
4: na
5: a

Отсортированные суффиксы (суффиксный массив SA):
SA[0]=5: a
SA[1]=3: ana
SA[2]=1: anana
SA[3]=0: banana
SA[4]=4: na
SA[5]=2: nana
```

```python
def build_suffix_array(s: str) -> list:
    """Строим суффиксный массив за O(n log² n)"""
    n = len(s)
    
    # Создаём суффиксы как (строка, индекс) и сортируем
    suffixes = sorted(range(n), key=lambda i: s[i:])
    return suffixes

def search_pattern(s: str, pattern: str, sa: list) -> list:
    """O(m log n) поиск паттерна с помощью бинарного поиска"""
    n = len(s)
    m = len(pattern)
    
    # Бинарный поиск первого вхождения
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if s[sa[mid]:sa[mid]+m] < pattern:
            lo = mid + 1
        else:
            hi = mid
    left = lo
    
    # Бинарный поиск последнего вхождения
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if s[sa[mid]:sa[mid]+m] <= pattern:
            lo = mid + 1
        else:
            hi = mid
    right = lo
    
    return [sa[i] for i in range(left, right)]

# Пример
s = "abracadabra"
sa = build_suffix_array(s)
print(sa)  # [10, 7, 0, 3, 5, 8, 1, 4, 6, 9, 2]

positions = search_pattern(s, "abr", sa)
print(sorted(positions))  # [0, 7] — "abr" встречается на позициях 0 и 7
```

### LCP массив (Longest Common Prefix)

SA + LCP (массив длин наибольших общих префиксов соседних суффиксов) позволяет решать сложные задачи эффективно:

```python
def build_lcp(s: str, sa: list) -> list:
    """Строим LCP массив за O(n) по алгоритму Касаи"""
    n = len(s)
    rank = [0] * n
    lcp = [0] * n
    
    # rank[i] = позиция суффикса s[i:] в суффиксном массиве
    for i, suffix_idx in enumerate(sa):
        rank[suffix_idx] = i
    
    k = 0  # текущая LCP длина
    for i in range(n):
        if rank[i] == 0:
            k = 0
            continue
        j = sa[rank[i] - 1]  # предыдущий суффикс в SA
        while i+k < n and j+k < n and s[i+k] == s[j+k]:
            k += 1
        lcp[rank[i]] = k
        if k > 0:
            k -= 1
    
    return lcp

# Применение: подсчёт различных подстрок
# Количество различных подстрок = n*(n+1)/2 - sum(LCP)
```

## Суффиксное дерево Уккона

Суффиксное дерево — compressed trie всех суффиксов строки. Уккона (1995) показал, как построить его за O(n).

```
Суффиксное дерево для "xabxac":

root
├── 'x' → [xa, xabxac]
│   └── 'a' → ...
│       ├── 'b' → "xac$"  (суффикс xabxac)
│       └── 'c' → '$'     (суффикс xac)
├── 'a' → [abxac, ac]
│   └── ...
└── 'c' → '$'
```

```python
# Алгоритм Уккона сложен в реализации (~300 строк)
# Используем библиотеку для демонстрации:
# pip install suffix-trees

# Применения суффиксного дерева:
# - Поиск всех вхождений паттерна: O(m + k)
# - Longest Common Substring двух строк
# - Largest repeated substring
# - Palindrome detection

def longest_common_substring_naive(s1, s2):
    """O(n*m) наивный подход — для демонстрации"""
    m, n = len(s1), len(s2)
    best = ""
    for i in range(m):
        for j in range(n):
            k = 0
            while i+k < m and j+k < n and s1[i+k] == s2[j+k]:
                k += 1
            if k > len(best):
                best = s1[i:i+k]
    return best

# С суффиксным деревом: O(n+m)
print(longest_common_substring_naive("ABABC", "BABCAB"))  # "BABC"
```

## Алгоритм Aho-Corasick: поиск множества паттернов

Aho-Corasick (1975) — алгоритм для одновременного поиска нескольких паттернов в тексте за $O(n + \Sigma k + \text{выходы})$.

**Применение:** антивирусное сканирование (тысячи сигнатур), обнаружение вредоносных URL, фильтрация спама.

```python
from collections import deque, defaultdict

class AhoCorasick:
    def __init__(self):
        self.goto = [{}]    # функция переходов
        self.fail = [0]     # функция отказа
        self.output = [[]]  # слова, заканчивающиеся в состоянии
    
    def add_pattern(self, pattern: str) -> None:
        """Добавляем паттерн в автомат"""
        state = 0
        for char in pattern:
            if char not in self.goto[state]:
                self.goto.append({})
                self.fail.append(0)
                self.output.append([])
                self.goto[state][char] = len(self.goto) - 1
            state = self.goto[state][char]
        self.output[state].append(pattern)
    
    def build(self):
        """Строим fail links через BFS: O(суммарная длина паттернов)"""
        queue = deque()
        
        # Первый уровень: fail ссылки на корень
        for char, next_state in self.goto[0].items():
            queue.append(next_state)
        
        while queue:
            r = queue.popleft()
            for char, s in self.goto[r].items():
                queue.append(s)
                state = self.fail[r]
                
                while state != 0 and char not in self.goto[state]:
                    state = self.fail[state]
                
                self.fail[s] = self.goto[state].get(char, 0)
                if self.fail[s] == s:
                    self.fail[s] = 0
                
                # Объединяем выходы
                self.output[s] += self.output[self.fail[s]]
    
    def search(self, text: str):
        """Поиск всех паттернов в тексте: O(n + |совпадений|)"""
        state = 0
        results = []
        
        for i, char in enumerate(text):
            while state != 0 and char not in self.goto[state]:
                state = self.fail[state]
            
            state = self.goto[state].get(char, 0)
            
            for pattern in self.output[state]:
                pos = i - len(pattern) + 1
                results.append((pos, pattern))
        
        return results

# Тест
ac = AhoCorasick()
patterns = ["he", "she", "his", "hers"]
for p in patterns:
    ac.add_pattern(p)
ac.build()

text = "ushers"
matches = ac.search(text)
print(matches)
# [(1, 'she'), (2, 'he'), (3, 'hers'), (0, 'his')] — но порядок может быть другим
# На самом деле: (1, 'she'), (2, 'he'), (2, 'hers')
```

## Практический пример: автодополнение поисковика

```python
class Autocomplete:
    """
    Autocomplete с приоритетами (популярность запроса).
    Использует Trie для поиска по префиксу.
    """
    
    def __init__(self):
        self.trie = Trie()
        self.word_scores = {}  # слово → количество поисков
    
    def record_search(self, query: str):
        """Записываем поиск, увеличиваем счётчик"""
        self.word_scores[query] = self.word_scores.get(query, 0) + 1
        self.trie.insert(query, self.word_scores[query])
    
    def autocomplete(self, prefix: str, max_results: int = 10) -> list:
        """Возвращает топ-N предложений для prefix"""
        candidates = self.trie.get_words_with_prefix(prefix)
        
        # Сортируем по популярности
        ranked = sorted(
            candidates,
            key=lambda w: self.word_scores.get(w, 0),
            reverse=True
        )
        
        return ranked[:max_results]

# Симуляция
ac = Autocomplete()
searches = [
    "python programming", "python tutorial", "python list",
    "python programming", "python tutorial", "python dict",
    "python programming", "pytorch", "python set",
    "java programming", "javascript"
]

for s in searches:
    ac.record_search(s)

print("Предложения для 'py':")
for suggestion in ac.autocomplete("py"):
    print(f"  {suggestion} ({ac.word_scores[suggestion]})")

# python programming (3)
# python tutorial (2)
# python list (1)
# python dict (1)
# ...
```

## Сравнение строковых структур данных

| Структура | Вставка | Поиск | Prefix | Память | Применение |
|-----------|---------|-------|--------|--------|-----------|
| Hash table | O(m) | O(m) | O(n) | O(N) | Точный поиск |
| Trie | O(m) | O(m) | O(m+k) | $O(N \cdot |\Sigma|)$ | Автодополнение, словари |
| Radix Tree | O(m) | O(m) | O(m+k) | O(N) | IP routing, сжатый Trie |
| TST | $O(m \log|\Sigma|)$ | $O(m \log|\Sigma|)$ | O(m+k) | O(N) | Балансировка памяти/скорости |
| Suffix Array | — | O(m log n) | — | O(n) | Поиск подстрок |
| Suffix Tree | — | O(m) | — | O(n) | Сложные строковые задачи |
| Aho-Corasick | $O(\Sigma P)$ build | O(n+k) | — | $O(\Sigma P)$ | Multi-pattern search |

## Итоги

Строковые структуры данных — специализированный инструментарий:

- **Trie** — быстрый O(m) поиск и автодополнение; дорог по памяти
- **Radix Tree** — сжатый Trie; идеален для IP-маршрутизации
- **TST** — компромисс между Trie и BST
- **Суффиксный массив + LCP** — практичный инструмент для поиска подстрок, требует O(n log n) построения
- **Суффиксное дерево** — мощнее, но сложнее; O(n) построение по Уккону
- **Aho-Corasick** — поиск многих паттернов одновременно

## Литература

1. de la Briandais, R. (1959). File searching using variable length keys. *AFIPS Spring Joint Computer Conference*, 295–298. — оригинальная идея Trie

2. Knuth, D. E. (1998). *The Art of Computer Programming, Vol. 3*, Section 6.3. — Tries and Multiway Trees.

3. Manber, U., & Myers, G. (1993). Suffix arrays: a new method for on-line string searches. *SIAM Journal on Computing*, 22(5), 935–948. https://dl.acm.org/doi/10.1145/320176.320218

4. Ukkonen, E. (1995). On-line construction of suffix trees. *Algorithmica*, 14(3), 249–260. https://link.springer.com/article/10.1007/BF01206331

5. Aho, A. V., & Corasick, M. J. (1975). Efficient string matching: An aid to bibliographic search. *Communications of the ACM*, 18(6), 333–340. https://dl.acm.org/doi/10.1145/360825.360855

6. Bentley, J. L., & Sedgewick, R. (1997). Fast Algorithms for Sorting and Searching Strings. *SODA 1997*. — Ternary Search Tree

7. Kasai, T. et al. (2001). Linear-time longest-common-prefix computation in suffix arrays and its applications. *CPM 2001*. — O(n) LCP array construction

8. Sedgewick, R., & Wayne, K. (2011). *Algorithms* (4th ed.). Addison-Wesley. Глава 5 — Strings.

9. Gusfield, D. (1997). *Algorithms on Strings, Trees, and Sequences*. Cambridge University Press. — суффиксные деревья и массивы.

10. Python `pyahocorasick` library documentation. https://pyahocorasick.readthedocs.io/
