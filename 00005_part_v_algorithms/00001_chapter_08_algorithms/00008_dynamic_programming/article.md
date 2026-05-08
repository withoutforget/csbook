# Динамическое программирование: мемоизация перекрывающихся подзадач

Динамическое программирование (DP) — одна из самых мощных техник алгоритмического мышления. Оно превращает экспоненциальные алгоритмы в полиномиальные, элегантно решая задачи оптимизации и подсчёта. Название немного вводит в заблуждение — "программирование" здесь не про код, а про процесс планирования (в духе Беллмана). Суть же простая: если задача разбивается на перекрывающиеся подзадачи, запоминай их результаты.

## Принцип оптимальности Беллмана

Ричард Беллман сформулировал основу DP: **оптимальное решение задачи содержит оптимальные решения подзадач**.

Аналогия: оптимальный маршрут из Москвы в Петербург через Тверь состоит из оптимального маршрута Москва→Тверь и оптимального маршрута Тверь→Петербург.

Два условия применимости DP:
1. **Optimal substructure (оптимальная подструктура):** Оптимальное решение задачи строится из оптимальных решений подзадач
2. **Overlapping subproblems (перекрывающиеся подзадачи):** Одни и те же подзадачи решаются многократно при рекурсивном разложении

## Два подхода: мемоизация vs табуляция

### Top-down (мемоизация)

Рекурсивное решение + кеш результатов:

```python
from functools import lru_cache
from typing import Dict

# Числа Фибоначчи: наглядный пример
def fib_naive(n):
    """O(2^n) — экспоненциальное! При n=50 — миллиарды операций"""
    if n <= 1: return n
    return fib_naive(n-1) + fib_naive(n-2)

# TOP-DOWN: добавляем мемоизацию
def fib_memo(n, memo={}):
    """O(n) с мемоизацией"""
    if n in memo: return memo[n]
    if n <= 1: return n
    memo[n] = fib_memo(n-1, memo) + fib_memo(n-2, memo)
    return memo[n]

# Или используя lru_cache:
@lru_cache(maxsize=None)
def fib(n: int) -> int:
    """O(n) время, O(n) память (стек рекурсии + кеш)"""
    if n <= 1: return n
    return fib(n-1) + fib(n-2)

print(fib(100))  # 354224848179261915075 — мгновенно!
```

### Bottom-up (табуляция)

Итеративное заполнение таблицы с малых подзадач к большим:

```python
def fib_tabulation(n: int) -> int:
    """O(n) время, O(n) память"""
    if n <= 1: return n
    dp = [0] * (n + 1)
    dp[0], dp[1] = 0, 1
    for i in range(2, n + 1):
        dp[i] = dp[i-1] + dp[i-2]
    return dp[n]

def fib_optimized(n: int) -> int:
    """O(n) время, O(1) память — rolling array!"""
    if n <= 1: return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

print(fib_optimized(1000))  # огромное число, мгновенно
```

### Сравнение подходов

| | Top-down | Bottom-up |
|---|---------|----------|
| Код | Ближе к математической формуле | Явный цикл |
| Подзадачи | Только нужные | Все (включая ненужные) |
| Память | Стек рекурсии + кеш | Таблица |
| Производительность | Хуже (overhead рекурсии) | Лучше (итерации) |
| Когда выбрать | Не все подзадачи нужны | Все подзадачи нужны |

## Задача о рюкзаке (0/1 Knapsack)

Классика DP: дан рюкзак вместимостью W и n предметов с весами и ценностями. Максимизировать суммарную ценность, не превысив вместимость.

```python
def knapsack(weights, values, capacity):
    """
    0/1 Knapsack: O(n*W) время и память
    weights[i], values[i] — характеристики i-го предмета
    """
    n = len(weights)
    
    # dp[i][j] = максимальная ценность для первых i предметов и вместимости j
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    
    for i in range(1, n + 1):
        for j in range(capacity + 1):
            # Не берём предмет i
            dp[i][j] = dp[i-1][j]
            
            # Берём предмет i (если помещается)
            if weights[i-1] <= j:
                take_value = dp[i-1][j - weights[i-1]] + values[i-1]
                dp[i][j] = max(dp[i][j], take_value)
    
    # Восстанавливаем, какие предметы взяли
    taken = []
    j = capacity
    for i in range(n, 0, -1):
        if dp[i][j] != dp[i-1][j]:
            taken.append(i - 1)  # индекс предмета
            j -= weights[i-1]
    
    return dp[n][capacity], taken

# Пример
weights = [2, 3, 4, 5]
values  = [3, 4, 5, 6]
capacity = 8

max_value, items = knapsack(weights, values, capacity)
print(f"Максимальная ценность: {max_value}")  # 10
print(f"Взятые предметы: {items}")              # [2, 0] (весы 4 и 2)

# Оптимизация памяти: O(W) через rolling array
def knapsack_optimized(weights, values, capacity):
    dp = [0] * (capacity + 1)
    for i in range(len(weights)):
        # Обходим СПРАВА НАЛЕВО — чтобы не использовать предмет дважды!
        for j in range(capacity, weights[i] - 1, -1):
            dp[j] = max(dp[j], dp[j - weights[i]] + values[i])
    return dp[capacity]
```

## Наибольшая общая подпоследовательность (LCS)

LCS — базовая задача биоинформатики (сравнение ДНК), diff-утилит (git diff), форматирования текста.

```python
def lcs(s1: str, s2: str) -> str:
    """
    Longest Common Subsequence: O(m*n)
    """
    m, n = len(s1), len(s2)
    
    # dp[i][j] = длина LCS для s1[:i] и s2[:j]
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1  # символы совпали
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
    # Восстанавливаем LCS (обратный проход)
    lcs_str = []
    i, j = m, n
    while i > 0 and j > 0:
        if s1[i-1] == s2[j-1]:
            lcs_str.append(s1[i-1])
            i -= 1; j -= 1
        elif dp[i-1][j] > dp[i][j-1]:
            i -= 1
        else:
            j -= 1
    
    return ''.join(reversed(lcs_str))

# Тест
print(lcs("ABCBDAB", "BDCAB"))  # BCAB (длина 4)

# git diff использует LCS:
def diff(old_lines, new_lines):
    """Упрощённый git diff через LCS"""
    lcs_lines = lcs(old_lines, new_lines)
    # ... (код удаления и добавления строк)
```

## Расстояние Левенштейна (Edit Distance)

Минимальное количество операций (вставка, удаление, замена), чтобы превратить одну строку в другую.

```python
def edit_distance(s1: str, s2: str) -> int:
    """
    Редакционное расстояние: O(m*n)
    Применение: spell checker, DNA alignment, fuzzy search
    """
    m, n = len(s1), len(s2)
    
    # dp[i][j] = edit distance для s1[:i] и s2[:j]
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    # Базовые случаи
    for i in range(m + 1): dp[i][0] = i  # удалить i символов из s1
    for j in range(n + 1): dp[0][j] = j  # вставить j символов
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1]  # символы совпали — ничего не делаем
            else:
                dp[i][j] = 1 + min(
                    dp[i-1][j],     # удалить символ из s1
                    dp[i][j-1],     # вставить символ в s1
                    dp[i-1][j-1]    # заменить символ
                )
    
    return dp[m][n]

# Примеры
print(edit_distance("kitten", "sitting"))  # 3
print(edit_distance("saturday", "sunday")) # 3

# Spell checker:
dictionary = ["hello", "world", "python", "algorithm"]
typo = "alogrithm"
closest = min(dictionary, key=lambda w: edit_distance(typo, w))
print(f"Возможно, вы имели в виду: {closest}")  # algorithm
```

## Умножение цепочки матриц

Порядок умножения матриц влияет на количество операций. DP помогает найти оптимальный порядок.

```python
def matrix_chain_order(dims):
    """
    Минимальное количество умножений для цепочки матриц.
    dims[i] x dims[i+1] — размер i-й матрицы.
    O(n³) время, O(n²) память.
    """
    n = len(dims) - 1  # количество матриц
    
    # dp[i][j] = минимальное количество умножений для матриц i..j
    dp = [[0] * n for _ in range(n)]
    split = [[0] * n for _ in range(n)]
    
    # length — длина цепочки
    for length in range(2, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1
            dp[i][j] = float('inf')
            
            for k in range(i, j):
                # Разбиваем: (M_i...M_k) * (M_{k+1}...M_j)
                cost = (dp[i][k] + dp[k+1][j] + 
                        dims[i] * dims[k+1] * dims[j+1])
                if cost < dp[i][j]:
                    dp[i][j] = cost
                    split[i][j] = k
    
    def print_order(i, j):
        if i == j:
            return f"M{i+1}"
        k = split[i][j]
        return f"({print_order(i, k)} × {print_order(k+1, j)})"
    
    return dp[0][n-1], print_order(0, n-1)

# Матрицы: 30×35, 35×15, 15×5, 5×10, 10×20, 20×25
dims = [30, 35, 15, 5, 10, 20, 25]
min_ops, order = matrix_chain_order(dims)
print(f"Минимум операций: {min_ops}")   # 15125
print(f"Порядок: {order}")
```

## Задача о монетах (Coin Change)

```python
def coin_change(coins: list, amount: int) -> int:
    """
    Минимальное количество монет для суммы amount.
    O(amount * n_coins)
    """
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0
    
    for coin in coins:
        for a in range(coin, amount + 1):
            if dp[a - coin] + 1 < dp[a]:
                dp[a] = dp[a - coin] + 1
    
    return dp[amount] if dp[amount] != float('inf') else -1

def coin_ways(coins: list, amount: int) -> int:
    """
    Количество способов набрать сумму (порядок не важен).
    O(amount * n_coins)
    """
    dp = [0] * (amount + 1)
    dp[0] = 1  # один способ набрать 0
    
    for coin in coins:
        for a in range(coin, amount + 1):
            dp[a] += dp[a - coin]
    
    return dp[amount]

print(coin_change([1, 5, 11], 15))   # 3 (11+1+1+1 = нет, 11+4? нет... 5+5+5=3!)
print(coin_change([1, 5, 10, 25], 36))  # 3 (25+10+1)
print(coin_ways([1, 2, 5], 5))       # 4 (5, 2+2+1, 2+1+1+1, 1+1+1+1+1)
```

## Оптимизация памяти: rolling array

Многие DP-задачи требуют только предыдущей строки таблицы:

```python
# LCS с O(min(m,n)) памятью вместо O(m*n)
def lcs_length_optimized(s1: str, s2: str) -> int:
    """O(min(m,n)) память через две строки"""
    if len(s1) < len(s2):
        s1, s2 = s2, s1  # s2 — короткая
    
    m, n = len(s1), len(s2)
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                curr[j] = prev[j-1] + 1
            else:
                curr[j] = max(prev[j], curr[j-1])
        prev, curr = curr, [0] * (n + 1)
    
    return prev[n]

# Числа Фибоначчи — предельная оптимизация O(1):
# Нужны только два предыдущих значения
```

## Когда DP применимо

DP подходит, когда задача:

1. **Optimal substructure:** f(n) строится из f(n-1), f(n-2), ... или f(подзадачи)
2. **Overlapping subproblems:** Те же подзадачи встречаются многократно (в отличие от divide and conquer)

### Как распознать DP-задачу

```python
# Признаки DP:
# "Найти оптимальный..." → optimization DP
# "Подсчитать количество способов..." → counting DP
# "Возможно ли..." → decision DP

# Шаги решения DP:
# 1. Определить состояние: dp[i] или dp[i][j] означает...
# 2. Написать рекуррентное соотношение
# 3. Определить базовые случаи
# 4. Определить порядок вычислений
# 5. (Опционально) Восстановить ответ

# Пример мышления:
# Задача: "Максимальная сумма непрерывного подмассива" (Kadane's algorithm)
# Состояние: dp[i] = максимальная сумма подмассива, ЗАКАНЧИВАЮЩЕГОСЯ на i
# Рекуррентность: dp[i] = max(arr[i], dp[i-1] + arr[i])
# Базовый случай: dp[0] = arr[0]
# Ответ: max(dp[0], dp[1], ..., dp[n-1])

def max_subarray(arr):
    """Максимальная сумма непрерывного подмассива O(n)"""
    max_sum = curr_sum = arr[0]
    for x in arr[1:]:
        curr_sum = max(x, curr_sum + x)
        max_sum = max(max_sum, curr_sum)
    return max_sum

print(max_subarray([-2, 1, -3, 4, -1, 2, 1, -5, 4]))  # 6 (подмассив [4,-1,2,1])
```

## Связь с жадными алгоритмами

DP и жадные алгоритмы — братья по духу. Оба используют optimal substructure. Разница:

- **DP:** Рассматривает все возможные решения подзадач, выбирает лучшее
- **Жадный:** Делает один выбор — локально оптимальный — и не пересматривает

Иногда жадный алгоритм даёт оптимальный ответ (задача Хаффмана, MST). Но часто нужен полный перебор через DP.

```python
# Задача о монетах: когда жадный НЕ работает
coins_eu = [1, 5, 10, 25]
coins_bad = [1, 3, 4]

# Жадный (всегда берём наибольшую монету):
def greedy_coins(coins, amount):
    coins = sorted(coins, reverse=True)
    count = 0
    for c in coins:
        count += amount // c
        amount %= c
    return count if amount == 0 else -1

print(greedy_coins(coins_eu, 6))   # 2 (5+1) — правильно!
print(greedy_coins(coins_bad, 6))  # 3 (4+1+1), но DP даст 2 (3+3)!

print(coin_change(coins_bad, 6))   # 2 — DP правильно
```

## Итоги

DP — методология решения задач:

1. Разбить задачу на подзадачи
2. Определить рекуррентное соотношение
3. Кешировать результаты (мемоизация или таблица)

Классические задачи: Fibonacci (учебный пример), Knapsack (выбор подмножества), LCS (diff, биоинформатика), Edit distance (spell check), Coin change (финансы), Matrix chain (матричные вычисления).

## Литература

1. Bellman, R. E. (1957). *Dynamic Programming*. Princeton University Press. — оригинальная монография

2. Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. (2009). *Introduction to Algorithms* (3rd ed.). MIT Press. Глава 15 — Dynamic Programming.

3. Knuth, D. E. (1973). The optimum binary search tree problem. *Acta Informatica*, 1(1). — DP для оптимальных деревьев поиска

4. Levenshtein, V. I. (1966). Binary codes capable of correcting deletions, insertions, and reversals. *Soviet Physics Doklady*, 10(8), 707–710. — редакционное расстояние

5. Sedgewick, R., & Wayne, K. (2011). *Algorithms* (4th ed.). Addison-Wesley. — практические примеры DP

6. Skiena, S. S. (2008). *The Algorithm Design Manual* (2nd ed.). Springer. Глава 8 — Dynamic Programming.

7. Miller, W. J., & Myers, E. W. (1988). Sequence Comparison with Concave Weighting Functions. *Bulletin of Mathematical Biology*. — оптимизации edit distance

8. Dasgupta, S., Papadimitriou, C., & Vazirani, U. (2006). *Algorithms*. McGraw-Hill. Глава 6 — Dynamic Programming. http://algorithmics.lsi.upc.edu/docs/Dasgupta-Papadimitriou-Vazirani.pdf

9. Python `functools.lru_cache` documentation. https://docs.python.org/3/library/functools.html#functools.lru_cache

10. Kadane, J. B. (1984). Maximum sum subarray problem. — алгоритм Кейдейна для максимального подмассива
