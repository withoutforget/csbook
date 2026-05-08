# Графы: BFS, DFS, Dijkstra, A*, топологическая сортировка

Граф — универсальная абстракция для представления отношений. Социальные сети, карты городов, зависимости пакетов, расписания, молекулярные структуры — всё это графы. Алгоритмы на графах решают задачи маршрутизации, планирования, обнаружения зависимостей и многое другое. Умение думать в терминах графов и знать базовые алгоритмы — это один из главных скиллов алгоритмиста.

## Представления графов

Граф G = (V, E), где V — вершины (vertices), E — рёбра (edges).

### Матрица смежности (Adjacency Matrix)

```python
# Матрица смежности для 5 вершин
n = 5
adj_matrix = [[0] * n for _ in range(n)]

# Добавление рёбер:
adj_matrix[0][1] = 1  # 0→1
adj_matrix[0][2] = 1  # 0→2
adj_matrix[1][3] = 1  # 1→3

# Для взвешенного графа:
adj_matrix[0][1] = 4   # вес 4
adj_matrix[1][3] = 2   # вес 2

# Свойства:
# Хранение: O(V²) — плохо для разрежённых графов
# Проверка ребра: O(1)
# Перебор соседей: O(V)
# Плотные графы: V ≈ E → оправдано
```

### Список смежности (Adjacency List)

```python
from collections import defaultdict

# Список смежности — стандартное представление
graph = defaultdict(list)

# Ненаправленный граф:
def add_edge(g, u, v, weight=1):
    g[u].append((v, weight))
    g[v].append((u, weight))

# Направленный граф:
def add_directed_edge(g, u, v, weight=1):
    g[u].append((v, weight))

g = defaultdict(list)
edges = [(0,1,4), (0,2,2), (1,3,1), (2,3,5), (2,4,3), (3,4,2)]
for u, v, w in edges:
    add_directed_edge(g, u, v, w)

# Свойства:
# Хранение: O(V + E)
# Проверка ребра: O(degree)
# Перебор соседей: O(degree)
# Разрежённые графы: E << V² → оправдано
```

### Выбор представления

| | Матрица смежности | Список смежности |
|---|---|---|
| Хранение | O(V²) | O(V + E) |
| Проверка ребра (u,v) | O(1) | O(degree(u)) |
| Перебор соседей | O(V) | O(degree(u)) |
| Когда выбирать | Плотные графы, E ≈ V² | Разрежённые графы |

## BFS (Breadth-First Search): обход в ширину

BFS обходит граф уровень за уровнем, используя очередь. Сначала все соседи на расстоянии 1, затем на расстоянии 2, и т.д.

**Гарантия:** BFS находит кратчайший путь в **невзвешенном** графе.

```python
from collections import deque

def bfs(graph, start):
    """Обход в ширину"""
    visited = {start}
    queue = deque([start])
    order = []
    
    while queue:
        vertex = queue.popleft()
        order.append(vertex)
        
        for neighbor, _ in graph[vertex]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    
    return order

def bfs_shortest_path(graph, start, end):
    """Кратчайший путь в невзвешенном графе"""
    if start == end:
        return [start]
    
    visited = {start}
    queue = deque([(start, [start])])  # (вершина, путь до неё)
    
    while queue:
        vertex, path = queue.popleft()
        
        for neighbor, _ in graph[vertex]:
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    
    return None  # пути нет

def bfs_distances(graph, start):
    """Расстояния от start до всех вершин"""
    distances = {start: 0}
    queue = deque([start])
    
    while queue:
        vertex = queue.popleft()
        for neighbor, _ in graph[vertex]:
            if neighbor not in distances:
                distances[neighbor] = distances[vertex] + 1
                queue.append(neighbor)
    
    return distances

# Пример: карта метро
metro = defaultdict(list)
connections = [
    ("Москва", "Тверская"), ("Тверская", "Чеховская"),
    ("Москва", "Охотный ряд"), ("Охотный ряд", "Театральная"),
    ("Тверская", "Пушкинская"), ("Пушкинская", "Кузнецкий мост")
]
for u, v in connections:
    add_edge(metro, u, v)

path = bfs_shortest_path(metro, "Москва", "Кузнецкий мост")
print(path)  # ['Москва', 'Тверская', 'Пушкинская', 'Кузнецкий мост']

dist = bfs_distances(metro, "Москва")
print(dist)  # {'Москва': 0, 'Тверская': 1, 'Охотный ряд': 1, ...}
```

## DFS (Depth-First Search): обход в глубину

DFS идёт как можно глубже, используя стек (явный или стек рекурсии).

```python
def dfs_recursive(graph, start, visited=None, order=None):
    """Рекурсивный DFS"""
    if visited is None: visited = set()
    if order is None: order = []
    
    visited.add(start)
    order.append(start)
    
    for neighbor, _ in graph[start]:
        if neighbor not in visited:
            dfs_recursive(graph, neighbor, visited, order)
    
    return order

def dfs_iterative(graph, start):
    """Итеративный DFS с явным стеком"""
    visited = set()
    stack = [start]
    order = []
    
    while stack:
        vertex = stack.pop()
        if vertex not in visited:
            visited.add(vertex)
            order.append(vertex)
            # Добавляем соседей в обратном порядке
            # (чтобы первый сосед обрабатывался первым)
            for neighbor, _ in reversed(graph[vertex]):
                if neighbor not in visited:
                    stack.append(neighbor)
    
    return order

def has_cycle_undirected(graph, n):
    """Обнаружение цикла в ненаправленном графе"""
    visited = set()
    
    def dfs(v, parent):
        visited.add(v)
        for neighbor, _ in graph[v]:
            if neighbor not in visited:
                if dfs(neighbor, v):
                    return True
            elif neighbor != parent:
                return True  # нашли цикл!
        return False
    
    for v in range(n):
        if v not in visited:
            if dfs(v, -1):
                return True
    return False

def connected_components(graph, vertices):
    """Компоненты связности через DFS"""
    visited = set()
    components = []
    
    for v in vertices:
        if v not in visited:
            component = []
            dfs_recursive(graph, v, visited, component)
            components.append(component)
    
    return components
```

### DFS для обнаружения циклов в направленном графе

```python
def has_cycle_directed(graph, n):
    """Цикл в направленном графе через трёхцветное DFS"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {v: WHITE for v in range(n)}
    
    def dfs(v):
        color[v] = GRAY  # в процессе обработки
        
        for neighbor, _ in graph[v]:
            if color[neighbor] == GRAY:
                return True   # нашли обратное ребро → цикл!
            if color[neighbor] == WHITE:
                if dfs(neighbor):
                    return True
        
        color[v] = BLACK  # обработан
        return False
    
    for v in range(n):
        if color[v] == WHITE:
            if dfs(v):
                return True
    return False
```

## Топологическая сортировка

Топологическая сортировка — упорядочивание вершин DAG (Directed Acyclic Graph) так, что для каждого ребра u→v вершина u стоит перед v.

**Применения:** порядок сборки проекта, разрешение зависимостей пакетов, планирование задач.

### Алгоритм Кана (BFS-based)

```python
from collections import deque

def topological_sort_kahn(graph, vertices):
    """
    Алгоритм Кана: итеративная топологическая сортировка.
    Сложность: O(V + E)
    """
    # Вычисляем in-degree (количество входящих рёбер) для каждой вершины
    in_degree = {v: 0 for v in vertices}
    for v in vertices:
        for neighbor, _ in graph[v]:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1
    
    # Начинаем с вершин без входящих рёбер
    queue = deque([v for v in vertices if in_degree[v] == 0])
    result = []
    
    while queue:
        v = queue.popleft()
        result.append(v)
        
        for neighbor, _ in graph[v]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    if len(result) != len(vertices):
        raise ValueError("Граф содержит цикл!")
    
    return result

# Пример: зависимости пакетов
deps = defaultdict(list)
# A зависит от B и C, B зависит от D
packages = ['A', 'B', 'C', 'D', 'E']
add_directed_edge(deps, 'A', 'B')
add_directed_edge(deps, 'A', 'C')
add_directed_edge(deps, 'B', 'D')
add_directed_edge(deps, 'C', 'D')

order = topological_sort_kahn(deps, packages)
print(order)  # ['E', 'D', 'B', 'C', 'A'] или похожий порядок
```

### DFS-based топологическая сортировка

```python
def topological_sort_dfs(graph, vertices):
    """DFS + стек: O(V+E)"""
    visited = set()
    stack = []
    
    def dfs(v):
        visited.add(v)
        for neighbor, _ in graph[v]:
            if neighbor not in visited:
                dfs(neighbor)
        stack.append(v)  # добавляем ПОСЛЕ обработки всех потомков
    
    for v in vertices:
        if v not in visited:
            dfs(v)
    
    return stack[::-1]  # переворачиваем: последние добавленные = первые в порядке
```

## Алгоритм Дейкстры

Кратчайшие пути от одной вершины во взвешенном графе с **неотрицательными** весами.

**Жадная стратегия:** на каждом шаге выбираем непосещённую вершину с минимальным текущим расстоянием.

```python
import heapq
from collections import defaultdict

def dijkstra(graph, start):
    """
    Алгоритм Дейкстры.
    O((V + E) log V) с бинарной кучей
    """
    distances = defaultdict(lambda: float('inf'))
    distances[start] = 0
    
    # Куча: (расстояние, вершина)
    pq = [(0, start)]
    visited = set()
    prev = {start: None}  # для восстановления пути
    
    while pq:
        dist, vertex = heapq.heappop(pq)
        
        if vertex in visited:
            continue  # уже нашли кратчайший путь
        visited.add(vertex)
        
        for neighbor, weight in graph[vertex]:
            if neighbor in visited:
                continue
            new_dist = dist + weight
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                prev[neighbor] = vertex
                heapq.heappush(pq, (new_dist, neighbor))
    
    return dict(distances), prev

def reconstruct_path(prev, start, end):
    """Восстанавливаем путь из словаря предшественников"""
    path = []
    current = end
    while current is not None:
        path.append(current)
        current = prev.get(current)
    path.reverse()
    return path if path[0] == start else []

# Пример: карта города
city = defaultdict(list)
roads = [
    ('A', 'B', 4), ('A', 'C', 2),
    ('B', 'C', 1), ('B', 'D', 5),
    ('C', 'D', 8), ('C', 'E', 10),
    ('D', 'E', 2), ('D', 'F', 6),
    ('E', 'F', 3)
]
for u, v, w in roads:
    add_edge(city, u, v, w)

dists, prev = dijkstra(city, 'A')
print(f"Расстояние A→F: {dists['F']}")    # 13
path = reconstruct_path(prev, 'A', 'F')
print(f"Путь A→F: {' → '.join(path)}")   # A → C → B → D → E → F
```

### Почему Дейкстра не работает с отрицательными весами

```
Граф с отрицательным ребром:
A → B: 3
A → C: 5
C → B: -10

Дейкстра:
- Выбирает A (dist=0)
- Обновляет B: dist=3, C: dist=5
- Выбирает B (dist=3) — помечает как посещённую
- Выбирает C (dist=5)
- C→B: новое расстояние = 5 + (-10) = -5, но B уже посещена!
- Дейкстра пропустит это обновление → неправильный ответ!
```

## Bellman-Ford: отрицательные рёбра

Bellman-Ford работает с отрицательными весами и обнаруживает отрицательные циклы.

**Принцип:** V-1 раз "расслабляем" все рёбра. После V-1 итерации кратчайшие пути найдены (если нет отрицательных циклов).

```python
def bellman_ford(edges, vertices, start):
    """
    Bellman-Ford: O(V*E)
    edges: [(u, v, weight), ...]
    """
    distances = {v: float('inf') for v in vertices}
    distances[start] = 0
    prev = {v: None for v in vertices}
    
    # V-1 итераций
    for _ in range(len(vertices) - 1):
        changed = False
        for u, v, weight in edges:
            if distances[u] != float('inf') and distances[u] + weight < distances[v]:
                distances[v] = distances[u] + weight
                prev[v] = u
                changed = True
        
        if not changed:
            break  # ранний выход: стабилизировалось
    
    # Проверяем на отрицательные циклы
    for u, v, weight in edges:
        if distances[u] != float('inf') and distances[u] + weight < distances[v]:
            raise ValueError("Граф содержит отрицательный цикл!")
    
    return distances, prev

# Применение Bellman-Ford: арбитраж валют
# Если в цикле: курс обмена A→B→C→A > 1 → профит (отрицательный цикл!)
import math

def find_arbitrage(currencies, exchange_rates):
    """Обнаружение арбитражных возможностей"""
    n = len(currencies)
    # Преобразуем: максимизация произведений = минимизация суммы логарифмов
    log_edges = []
    for i in range(n):
        for j in range(n):
            if exchange_rates[i][j] > 0:
                log_edges.append((i, j, -math.log(exchange_rates[i][j])))
    
    try:
        bellman_ford(log_edges, range(n), 0)
        return False  # нет арбитража
    except ValueError:
        return True   # есть отрицательный цикл = арбитраж!
```

## A*: эвристический поиск

A* — обобщение Дейкстры с эвристической функцией h(v), оценивающей расстояние от v до цели. При h(v) = 0 получаем Дейкстру.

**Условие корректности:** h должна быть **допустимой** (admissible): никогда не переоценивает реальное расстояние.

```python
import heapq
import math

def astar(graph, start, goal, heuristic):
    """
    A* алгоритм.
    f(n) = g(n) + h(n)
    g(n) — реальная стоимость пути до n
    h(n) — оценка стоимости от n до цели
    """
    # Куча: (f_score, vertex)
    open_set = [(heuristic(start, goal), start)]
    came_from = {}
    
    g_score = defaultdict(lambda: float('inf'))
    g_score[start] = 0
    
    f_score = defaultdict(lambda: float('inf'))
    f_score[start] = heuristic(start, goal)
    
    in_open = {start}
    
    while open_set:
        _, current = heapq.heappop(open_set)
        
        if current not in in_open:
            continue
        in_open.discard(current)
        
        if current == goal:
            # Восстанавливаем путь
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            return path[::-1], g_score[goal]
        
        for neighbor, weight in graph[current]:
            tentative_g = g_score[current] + weight
            
            if tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + heuristic(neighbor, goal)
                in_open.add(neighbor)
                heapq.heappush(open_set, (f_score[neighbor], neighbor))
    
    return None, float('inf')

# Применение: поиск пути на сетке (игры, роботы)
def grid_heuristic(a, b):
    """Манхэттенское расстояние для 4-направленного движения"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def euclidean_heuristic(a, b):
    """Евклидово расстояние для 8-направленного движения"""
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

# A* находит оптимальный путь быстрее Дейкстры благодаря эвристике
# На практике: в 10-100 раз меньше вершин исследуется
```

## Floyd-Warshall: кратчайшие пути между всеми парами

```python
def floyd_warshall(n, edges):
    """
    Floyd-Warshall: O(V³)
    Все пары кратчайших путей.
    """
    INF = float('inf')
    dist = [[INF] * n for _ in range(n)]
    
    for i in range(n):
        dist[i][i] = 0
    for u, v, w in edges:
        dist[u][v] = w
    
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]
    
    # Проверка отрицательных циклов: dist[i][i] < 0
    for i in range(n):
        if dist[i][i] < 0:
            raise ValueError("Отрицательный цикл")
    
    return dist

# Применение: анализ достижимости, транзитивное замыкание
```

## Минимальное остовное дерево

### Алгоритм Прима (жадный)

```python
def prim_mst(graph, start, vertices):
    """
    Алгоритм Прима: O((V+E) log V)
    MST = минимальное остовное дерево
    """
    in_mst = {start}
    edges_heap = []
    mst_edges = []
    total_weight = 0
    
    # Добавляем все рёбра из start
    for neighbor, weight in graph[start]:
        heapq.heappush(edges_heap, (weight, start, neighbor))
    
    while edges_heap and len(in_mst) < len(vertices):
        weight, u, v = heapq.heappop(edges_heap)
        
        if v in in_mst:
            continue  # уже в MST
        
        in_mst.add(v)
        mst_edges.append((u, v, weight))
        total_weight += weight
        
        for neighbor, w in graph[v]:
            if neighbor not in in_mst:
                heapq.heappush(edges_heap, (w, v, neighbor))
    
    return mst_edges, total_weight

### Алгоритм Крускала (Union-Find)

def kruskal_mst(edges, n):
    """
    Алгоритм Крускала: O(E log E)
    edges: [(weight, u, v), ...]
    """
    # Union-Find (Disjoint Set Union)
    parent = list(range(n))
    rank = [0] * n
    
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x
    
    def union(x, y):
        px, py = find(x), find(y)
        if px == py: return False
        if rank[px] < rank[py]: px, py = py, px
        parent[py] = px
        if rank[px] == rank[py]: rank[px] += 1
        return True
    
    sorted_edges = sorted(edges)
    mst = []
    total = 0
    
    for weight, u, v in sorted_edges:
        if union(u, v):
            mst.append((u, v, weight))
            total += weight
            if len(mst) == n - 1:
                break
    
    return mst, total
```

## Применения: зависимости пакетов

```python
import json

# Граф зависимостей Python пакетов (упрощённо)
def build_dependency_graph(packages):
    """
    packages = {
        "django": ["asgiref>=3.4.1", "sqlparse>=0.2.2"],
        "asgiref": [],
        "sqlparse": [],
        ...
    }
    """
    graph = defaultdict(list)
    all_packages = set(packages.keys())
    
    for pkg, deps in packages.items():
        for dep in deps:
            dep_name = dep.split(">=")[0].split("==")[0].strip()
            add_directed_edge(graph, pkg, dep_name)
            all_packages.add(dep_name)
    
    try:
        order = topological_sort_kahn(graph, list(all_packages))
        return order  # порядок установки: сначала зависимости!
    except ValueError as e:
        print(f"Circular dependency detected: {e}")
        return None

packages = {
    "myapp": ["django", "requests"],
    "django": ["asgiref", "sqlparse"],
    "asgiref": [],
    "sqlparse": [],
    "requests": ["urllib3", "certifi"],
    "urllib3": [],
    "certifi": []
}

install_order = build_dependency_graph(packages)
print("Порядок установки:")
for pkg in install_order:
    print(f"  pip install {pkg}")
```

## Итоги

Графовые алгоритмы — один из самых богатых разделов алгоритмики:

- **BFS:** Кратчайший путь в невзвешенном графе, компоненты связности
- **DFS:** Обнаружение циклов, топологическая сортировка, компоненты
- **Топологическая сортировка:** DAG, зависимости, планирование
- **Дейкстра:** Кратчайший путь с неотрицательными весами; O((V+E) log V)
- **Bellman-Ford:** Отрицательные веса; O(VE)
- **A*:** Быстрее Дейкстры с эвристикой; применение в играх, навигации
- **Floyd-Warshall:** Все пары; O(V³)
- **Prim/Kruskal:** Минимальное остовное дерево

## Литература

1. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Главы 22-25 — Graph Algorithms.

2. Dijkstra, E. W. (1959). A note on two problems in connexion with graphs. *Numerische Mathematik*, 1, 269–271.

3. Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A Formal Basis for the Heuristic Determination of Minimum Cost Paths. *IEEE Transactions on Systems Science and Cybernetics*, 4(2). https://ieeexplore.ieee.org/document/4082128

4. Bellman, R. (1958). On a routing problem. *Quarterly of Applied Mathematics*, 16(1). — Bellman-Ford

5. Floyd, R. W. (1962). Algorithm 97: Shortest path. *Communications of the ACM*, 5(6). — Floyd-Warshall

6. Kruskal, J. B. (1956). On the Shortest Spanning Subtree of a Graph. *Proceedings of the AMS*, 7(1).

7. Prim, R. C. (1957). Shortest connection networks and some generalizations. *Bell System Technical Journal*, 36(6).

8. Sedgewick, R., & Wayne, K. (2011). *Algorithms* (4th ed.). Addison-Wesley. Глава 4 — Graphs.

9. Tarjan, R. E. (1972). Depth-first search and linear graph algorithms. *SIAM Journal on Computing*, 1(2), 146–160. — DFS и его приложения

10. Skiena, S. S. (2008). *The Algorithm Design Manual* (2nd ed.). Springer. Глава 5 — Graph Traversal.
