# Конечные автоматы и иерархия Хомского

## Введение

Теория формальных языков изучает языки как множества строк и автоматы — устройства, которые их распознают. Ноам Хомский в 1956–1959 годах разработал иерархию формальных грамматик (иерархию Хомского), разделив языки на четыре класса по их сложности. Эта иерархия объясняет, почему регулярные выражения не могут парсить HTML, почему контекстно-свободные грамматики используются для большинства языков программирования, и какова природа естественных языков.

Для разработчика понимание этой иерархии критично: оно определяет, что можно решить с помощью regex, что требует парсера, а что — полноценного интерпретатора.

---

## 1. Регулярные языки и конечные автоматы

### Детерминированный конечный автомат (DFA)

DFA — простейшая модель вычисления. Он имеет конечный набор состояний и, находясь в каждом состоянии, однозначно переходит в новое, читая очередной символ.

$\mathrm{DFA} = (Q, \Sigma, \delta, q_0, F)$, где:
- $Q$: конечное множество состояний
- $\Sigma$: входной алфавит
- $\delta\colon Q \times \Sigma \to Q$ — функция переходов
- $q_0 \in Q$: начальное состояние
- $F \subseteq Q$: допускающие состояния

```python
class DFA:
    """Детерминированный конечный автомат"""
    
    def __init__(self, states, alphabet, transitions, initial, accepting):
        self.states = states
        self.alphabet = alphabet
        self.transitions = transitions  # {(state, symbol): new_state}
        self.initial = initial
        self.accepting = accepting
    
    def accepts(self, input_string):
        state = self.initial
        for symbol in input_string:
            if symbol not in self.alphabet:
                return False
            state = self.transitions.get((state, symbol))
            if state is None:
                return False  # нет перехода = попали в «мусорное» состояние
        return state in self.accepting

# DFA, принимающий строки над {0,1}, оканчивающиеся на "01"
dfa_ends_01 = DFA(
    states={'q0', 'q1', 'q2'},
    alphabet={'0', '1'},
    transitions={
        ('q0', '0'): 'q1',
        ('q0', '1'): 'q0',
        ('q1', '0'): 'q1',
        ('q1', '1'): 'q2',
        ('q2', '0'): 'q1',
        ('q2', '1'): 'q0',
    },
    initial='q0',
    accepting={'q2'}
)

tests = ['01', '101', '001', '1001', '0', '1', '1010']
for t in tests:
    print(f"'{t}': {'принято' if dfa_ends_01.accepts(t) else 'отвергнуто'}")
```

### Недетерминированный конечный автомат (NFA)

NFA позволяет несколько переходов по одному символу и $\varepsilon$-переходы (переходы без чтения символа). Мощность распознавания — та же, что у DFA.

**Теорема (конструкция подмножеств)**: для любого NFA с $n$ состояниями существует эквивалентный DFA с не более чем $2^n$ состояниями.

```python
class NFA:
    """Недетерминированный конечный автомат с ε-переходами"""
    
    def __init__(self, states, alphabet, transitions, initial, accepting):
        self.states = states
        self.alphabet = alphabet
        self.transitions = transitions  # {(state, symbol): {set of states}}, symbol может быть 'ε'
        self.initial = initial
        self.accepting = accepting
    
    def epsilon_closure(self, states):
        """Множество всех состояний, достижимых через ε-переходы"""
        closure = set(states)
        stack = list(states)
        while stack:
            s = stack.pop()
            for t in self.transitions.get((s, 'ε'), set()):
                if t not in closure:
                    closure.add(t)
                    stack.append(t)
        return frozenset(closure)
    
    def accepts(self, input_string):
        current = self.epsilon_closure({self.initial})
        for symbol in input_string:
            next_states = set()
            for state in current:
                next_states |= self.transitions.get((state, symbol), set())
            current = self.epsilon_closure(next_states)
        return bool(current & self.accepting)

# NFA, принимающий строки, содержащие "aba" или "bb"
nfa = NFA(
    states={'q0', 'q1', 'q2', 'q3', 'q4', 'q5'},
    alphabet={'a', 'b'},
    transitions={
        # Петля в начале — можно начать в любой момент
        ('q0', 'a'): {'q0', 'q1'},
        ('q0', 'b'): {'q0', 'q4'},
        # Ветка "aba"
        ('q1', 'b'): {'q2'},
        ('q2', 'a'): {'q3'},
        # Ветка "bb"
        ('q4', 'b'): {'q5'},
        # Петли в принимающих состояниях
        ('q3', 'a'): {'q3'}, ('q3', 'b'): {'q3'},
        ('q5', 'a'): {'q5'}, ('q5', 'b'): {'q5'},
    },
    initial='q0',
    accepting={'q3', 'q5'}
)

print(nfa.accepts("aba"))    # True
print(nfa.accepts("bb"))     # True
print(nfa.accepts("abcaba")) # False (нет 'c')
print(nfa.accepts("xaba"))   # False
```

---

## 2. Регулярные выражения

Регулярные выражения — алгебраическая нотация для регулярных языков. Для алфавита $\Sigma$:

- $\emptyset$: пустой язык
- $\varepsilon$: язык, содержащий только пустую строку
- $a \in \Sigma$: язык $\{a\}$
- $R_1 \mid R_2$: объединение языков
- $R_1 R_2$: конкатенация
- $R^*$: клини-звезда (ноль или более повторений)

**Теорема Клини**: класс регулярных языков совпадает с классом языков, описываемых регулярными выражениями, и с классом языков, распознаваемых конечными автоматами.

```python
import re

# Регулярные выражения в Python
# Простые паттерны
pattern_email = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
pattern_ip = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')

# Что регулярные выражения УМЕЮТ:
tests = ['user@example.com', 'invalid-email', 'a@b.io']
for t in tests:
    print(f"'{t}': {'email' if pattern_email.match(t) else 'не email'}")

# Что регулярные выражения НЕ УМЕЮТ:
# Проверить, что все три части IP-адреса в диапазоне 0-255
# Это требует большего контекста, чем может хранить DFA
# pattern_ip выше принимает "999.999.999.999"
print(pattern_ip.match("999.999.999.999"))  # Совпадает! (ложноположительный)

# Для корректной валидации IP нужна дополнительная логика:
def is_valid_ip(s):
    match = pattern_ip.match(s)
    if not match:
        return False
    parts = s.split('.')
    return all(0 <= int(p) <= 255 for p in parts)

print(is_valid_ip("192.168.1.1"))  # True
print(is_valid_ip("999.999.999.999"))  # False
```

### Ограничения регулярных выражений

**Лемма о накачке (для регулярных языков)**: если $L$ — регулярный язык, то существует $p$ (длина накачки), такое что любая строка $w \in L$ с $|w| \geq p$ может быть представлена как $w = xyz$, где:
1. $|y| > 0$
2. $|xy| \leq p$
3. для всех $k \geq 0$: $xy^k z \in L$

**Следствие**: язык $\{a^n b^n \mid n \geq 0\}$ **нерегулярен**: он требует «запоминать» количество $a$, а DFA имеет лишь конечную память.

```python
# Классический пример: парный счётчик скобок не является регулярным
import re

def check_balanced_regex_attempt(s):
    """Попытка регулярного выражения для сбалансированных скобок"""
    # Это работает только для ФИКСИРОВАННОЙ глубины вложенности
    pattern = re.compile(r'^\(([^()]*|\(([^()]*|\([^()]*\))*\))*\)$')
    return bool(pattern.match(s))

def check_balanced_correct(s):
    """Правильная проверка через стек (контекстно-свободная грамматика)"""
    depth = 0
    for c in s:
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0

tests = ['()', '(())', '((()))', '()()', '((()', '())']
for t in tests:
    correct = check_balanced_correct(t)
    regex_result = check_balanced_regex_attempt(t)
    print(f"'{t}': корректно={correct}, regex={'да' if regex_result else 'нет'}")
```

**Вывод**: HTML — это не регулярный язык (есть вложенность тегов). Regex не может правильно парсить HTML. Именно это объясняет знаменитый ответ на Stack Overflow о попытке парсить HTML с regex.

---

## 3. Контекстно-свободные языки (КС-языки)

### Контекстно-свободные грамматики (КСГ)

$\mathrm{КСГ}\ G = (V, \Sigma, R, S)$, где:
- $V$: нетерминалы
- $\Sigma$: терминалы (алфавит)
- $R$: правила вывода вида $A \to \alpha$
- $S$: стартовый нетерминал

```python
class CFG:
    """Упрощённая контекстно-свободная грамматика"""
    
    def __init__(self, rules, start):
        self.rules = rules  # {'S': [['(', 'S', ')'], ['S', 'S'], []], ...}
        self.start = start
    
    def generate(self, symbol, max_depth=5):
        """Генерирует случайные строки из языка"""
        import random
        
        if max_depth == 0:
            return ''
        
        if symbol not in self.rules:
            return symbol  # Терминал
        
        production = random.choice(self.rules[symbol])
        return ''.join(self.generate(s, max_depth - 1) for s in production)

# КСГ для сбалансированных скобок
# S → (S) | SS | ε
balanced_cfg = CFG(
    rules={
        'S': [['(', 'S', ')'], ['S', 'S'], ['']]
    },
    start='S'
)

# Генерируем несколько строк
for _ in range(5):
    s = balanced_cfg.generate('S')
    s = s.replace('', '')  # убираем пустые строки
    print(f"Сгенерировано: '{s}', сбалансировано: {check_balanced_correct(s)}")
```

### КС-языки и языки программирования

Синтаксис большинства языков программирования описывается КСГ (более конкретно — подклассами КСГ: LL(k) или LR(k)).

Пример: упрощённая грамматика арифметических выражений:

```
E  → E + T | T
T  → T * F | F
F  → ( E ) | id | num
```

```python
# Алгоритм CYK (Cocke-Younger-Kasami) для КСГ в форме Хомского
# Форма Хомского: каждое правило A → BC или A → a

def cyk_parse(grammar_cnf, start, word):
    """
    grammar_cnf: правила в форме Хомского
      {'A': [('B', 'C'), ('D', 'E'), ...], ...}  — для бинарных правил
      {'A': ['a', 'b', ...]}  — для терминальных правил
    """
    n = len(word)
    if n == 0:
        return start in grammar_cnf.get('_epsilon', set())
    
    # Таблица DP: table[l][r] = множество нетерминалов, порождающих word[l..r]
    table = [[set() for _ in range(n)] for _ in range(n)]
    
    # Заполняем диагональ (подстроки длины 1)
    for i, c in enumerate(word):
        for nt, productions in grammar_cnf.items():
            if isinstance(productions, list):
                for prod in productions:
                    if isinstance(prod, str) and prod == c:
                        table[i][i].add(nt)
    
    # Заполняем для длин 2..n
    for length in range(2, n + 1):
        for start_idx in range(n - length + 1):
            end_idx = start_idx + length - 1
            for split in range(start_idx, end_idx):
                for nt, productions in grammar_cnf.items():
                    if isinstance(productions, list):
                        for prod in productions:
                            if isinstance(prod, tuple) and len(prod) == 2:
                                B, C = prod
                                if B in table[start_idx][split] and C in table[split+1][end_idx]:
                                    table[start_idx][end_idx].add(nt)
    
    return start in table[0][n-1]

# Грамматика для {aⁿbⁿ | n ≥ 1} в форме Хомского:
# S → AB | AX, X → SB
grammar = {
    'S': [('A', 'B'), ('A', 'X')],
    'X': [('S', 'B')],
    'A': ['a'],
    'B': ['b'],
}

print(cyk_parse(grammar, 'S', 'ab'))    # True
print(cyk_parse(grammar, 'S', 'aabb'))  # True
print(cyk_parse(grammar, 'S', 'aaabbb')) # True
print(cyk_parse(grammar, 'S', 'aab'))   # False
print(cyk_parse(grammar, 'S', 'ba'))    # False
```

---

## 4. Иерархия Хомского

Хомский выделил четыре класса языков:

| Уровень | Класс | Автомат | Грамматика |
|---|---|---|---|
| 0 | Рекурсивно перечислимые | Машина Тьюринга | Неограниченные |
| 1 | Контекстно-зависимые | Линейно ограниченный автомат | Контекстно-зависимые |
| 2 | Контекстно-свободные | Автомат с магазинной памятью (стек) | КСГ |
| 3 | Регулярные | Конечный автомат | Регулярные |

Включение строгое: Уровень 3 $\subset$ Уровень 2 $\subset$ Уровень 1 $\subset$ Уровень 0.

$$\text{Регулярные} \subset \text{КС} \subset \text{КЗ} \subset \text{РП}$$

### Какие языки к какому уровню относятся?

**Регулярные (Уровень 3)**:
- Целые числа: `[0-9]+`
- Email-адреса (упрощённо)
- Ключевые слова языков программирования
- Лексемы (tokens) в лексическом анализе

**Контекстно-свободные (Уровень 2)**:
- Синтаксис большинства языков программирования (C, Java, Python)
- HTML (без ссылок между атрибутами)
- XML (без схемы)
- Арифметические выражения с произвольной вложенностью скобок

**Контекстно-зависимые (Уровень 1)**:
- Синтаксис C++ с учётом шаблонов
- Некоторые аспекты C (идентификаторы должны быть объявлены до использования)
- Некоторые аспекты Python (правила отступов)

**Рекурсивно перечислимые (Уровень 0)**:
- Языки программирования как вычислительные системы
- Задача остановки

---

## 5. Автомат с магазинной памятью (PDA)

PDA — автомат с дополнительным стеком (магазином). Он мощнее DFA, так как может хранить произвольное количество символов на стеке.

```python
class PDA:
    """Недетерминированный автомат с магазинной памятью"""
    
    def __init__(self, transitions, initial_state, initial_stack, accepting_states):
        self.transitions = transitions
        # {(state, input_symbol_or_ε, stack_top): [(new_state, stack_push)]}
        # stack_push: список символов, которые кладём на стек (пустой = pop)
        self.initial_state = initial_state
        self.initial_stack = initial_stack  # начальный символ стека
        self.accepting_states = accepting_states
    
    def accepts(self, input_string):
        """BFS по конфигурациям (state, remaining_input, stack)"""
        from collections import deque
        
        initial_config = (self.initial_state, input_string, [self.initial_stack])
        queue = deque([initial_config])
        visited = set()
        
        while queue:
            state, remaining, stack = queue.popleft()
            config_key = (state, remaining, tuple(stack))
            
            if config_key in visited:
                continue
            visited.add(config_key)
            
            # Проверяем допускание
            if not remaining and state in self.accepting_states:
                return True
            
            stack_top = stack[-1] if stack else None
            
            # Переходы по текущему символу
            if remaining:
                symbol = remaining[0]
                for (q, a, z), moves in self.transitions.items():
                    if q == state and a == symbol and z == stack_top:
                        for new_state, push in moves:
                            new_stack = stack[:-1] + list(push)  # pop + push
                            queue.append((new_state, remaining[1:], new_stack))
            
            # ε-переходы
            for (q, a, z), moves in self.transitions.items():
                if q == state and a == 'ε' and z == stack_top:
                    for new_state, push in moves:
                        new_stack = stack[:-1] + list(push)
                        queue.append((new_state, remaining, new_stack))
        
        return False
```

---

## 6. Применения в компиляторах

### Лексический анализ (Lexer)

Лексер разбивает входной текст на лексемы (tokens). Каждый тип лексемы описывается регулярным выражением. Лексер — это фактически ДКА.

```python
import re

TOKEN_PATTERNS = [
    ('NUMBER',    r'\d+(\.\d+)?'),
    ('PLUS',      r'\+'),
    ('MINUS',     r'-'),
    ('TIMES',     r'\*'),
    ('DIVIDE',    r'/'),
    ('LPAREN',    r'\('),
    ('RPAREN',    r'\)'),
    ('SKIP',      r'[ \t]+'),
    ('MISMATCH',  r'.'),
]

MASTER_PATTERN = re.compile('|'.join(f'(?P<{name}>{pattern})' 
                                     for name, pattern in TOKEN_PATTERNS))

def tokenize(code):
    tokens = []
    for match in MASTER_PATTERN.finditer(code):
        kind = match.lastgroup
        value = match.group()
        if kind == 'SKIP':
            continue
        elif kind == 'MISMATCH':
            raise SyntaxError(f'Unexpected character: {value!r}')
        else:
            if kind == 'NUMBER':
                value = float(value) if '.' in value else int(value)
            tokens.append((kind, value))
    return tokens

code = "3 + (4 * 2)"
tokens = tokenize(code)
for token in tokens:
    print(token)
# ('NUMBER', 3)
# ('PLUS', '+')
# ('LPAREN', '(')
# ('NUMBER', 4)
# ('TIMES', '*')
# ('NUMBER', 2)
# ('RPAREN', ')')
```

### Синтаксический анализ (Parser)

Парсер принимает список токенов и строит дерево разбора (AST). Использует КСГ.

```python
class SimpleParser:
    """Рекурсивно-нисходящий парсер для арифметики"""
    
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
    
    def current(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return ('EOF', None)
    
    def eat(self, kind):
        token = self.current()
        if token[0] != kind:
            raise SyntaxError(f"Ожидалось {kind}, получено {token[0]}")
        self.pos += 1
        return token
    
    # E → T ((+ | -) T)*
    def expr(self):
        node = self.term()
        while self.current()[0] in ('PLUS', 'MINUS'):
            op = self.current()[0]
            self.eat(op)
            right = self.term()
            node = ('binop', op, node, right)
        return node
    
    # T → F ((* | /) F)*
    def term(self):
        node = self.factor()
        while self.current()[0] in ('TIMES', 'DIVIDE'):
            op = self.current()[0]
            self.eat(op)
            right = self.factor()
            node = ('binop', op, node, right)
        return node
    
    # F → NUMBER | ( E )
    def factor(self):
        token = self.current()
        if token[0] == 'NUMBER':
            self.eat('NUMBER')
            return ('num', token[1])
        elif token[0] == 'LPAREN':
            self.eat('LPAREN')
            node = self.expr()
            self.eat('RPAREN')
            return node
        raise SyntaxError(f"Неожиданный токен: {token}")

tokens = tokenize("3 + 4 * 2")
parser = SimpleParser(tokens)
ast = parser.expr()
print(ast)  # ('binop', 'PLUS', ('num', 3), ('binop', 'TIMES', ('num', 4), ('num', 2)))
```

---

## 7. Почему Python — не регулярный язык

Python использует отступы для обозначения блоков кода. Это делает его синтаксис **не** КС-языком в строгом смысле: глубина вложенности отступов должна соответствовать структуре, а это требует «памяти» о предыдущих уровнях.

На практике Python-компилятор использует специальный обработчик отступов (INDENT/DEDENT токены) как препроцессор перед КС-парсером.

---

## Заключение

Иерархия Хомского — карта «сложности» формальных языков:

- **Regex** — мощный, но ограниченный инструмент для регулярных паттернов: лексемы, простые форматы
- **КСГ и парсеры** — основа компиляторов для языков программирования
- **Машина Тьюринга** — полная вычислительная мощность, необходимая для интерпретаторов

Ключевое практическое правило: **используйте правильный инструмент для правильного уровня сложности**. Попытка парсить HTML с regex или реализовать парсер языка программирования без грамматики — типичные ошибки, которые исчезают при понимании иерархии.

---

## Литература и источники

1. Chomsky, N. (1956). Three models for the description of language. *IRE Transactions on Information Theory*, 2(3), 113–124. — Оригинальная статья иерархии Хомского.

2. Hopcroft, J. E., Motwani, R., & Ullman, J. D. (2006). *Introduction to Automata Theory, Languages, and Computation* (3rd ed.). Addison-Wesley. — Стандартный учебник.

3. Sipser, M. (2012). *Introduction to the Theory of Computation* (3rd ed.). Cengage Learning. — Доступное изложение теории формальных языков.

4. Aho, A. V., Lam, M. S., Sethi, R., & Ullman, J. D. (2006). *Compilers: Principles, Techniques, and Tools* (2nd ed.). Addison-Wesley. — «Книга дракона», классика компиляторов.

5. Parr, T. (2013). *The Definitive ANTLR 4 Reference*. Pragmatic Bookshelf. — ANTLR — генератор парсеров.

6. Friedl, J. E. F. (2006). *Mastering Regular Expressions* (3rd ed.). O'Reilly. — Практика регулярных выражений.

7. Python Language Reference. https://docs.python.org/3/reference/grammar.html — Официальная грамматика Python в BNF-форме.
