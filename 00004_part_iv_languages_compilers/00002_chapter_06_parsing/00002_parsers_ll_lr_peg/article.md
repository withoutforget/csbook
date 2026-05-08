# Парсеры: LL, LR, PEG, recursive descent — от текста к AST

Парсинг — это фундаментальная задача в информатике: взять последовательность токенов (лексем) и построить из них структурированное дерево, отражающее синтаксическую структуру входа. Этот процесс лежит в основе каждого компилятора, интерпретатора, редактора кода и любого инструмента, работающего с языками. Понимание алгоритмов парсинга позволяет создавать собственные языки, лучше понимать сообщения об ошибках и писать эффективный код.

## От токенов до AST: общая картина

Прежде чем говорить о парсерах, нужно понять место парсинга в общем pipeline обработки текста.

```
Исходный код:
"2 + 3 * 4"
      │
      ▼
  Лексер (Lexer/Scanner)
      │
      ▼
Поток токенов:
[INT(2), PLUS, INT(3), STAR, INT(4), EOF]
      │
      ▼
  Парсер (Parser)
      │
      ▼
AST (Abstract Syntax Tree):
      +
     / \
    2   *
       / \
      3   4
```

**Лексер** (также: токенизатор, сканер) читает поток символов и группирует их в токены. Регулярные выражения справляются с этой задачей идеально.

**Парсер** принимает поток токенов и строит дерево, отражающее грамматическую структуру. Здесь нужно что-то более мощное — контекстно-свободные грамматики.

### Abstract Syntax Tree vs Concrete Syntax Tree

**CST (Concrete Syntax Tree / Parse Tree)** — полное дерево разбора, включающее все токены, в том числе скобки, запятые, ключевые слова. Отражает конкретный синтаксис.

**AST (Abstract Syntax Tree)** — абстрактное дерево, опускающее детали синтаксиса (скобки для приоритета, точки с запятой). Отражает семантику.

```
Для выражения: (2 + 3)

CST:                    AST:
   expr                   +
   /|\                   / \
  ( + )                 2   3
 / |   \
2  +   3

CST сохраняет скобки.    AST — только суть.
```

## Контекстно-свободные грамматики (CFG)

Парсеры работают с контекстно-свободными грамматиками (CFG). CFG — это набор правил продукции:

```
G = (V, Σ, R, S)
где:
  V — нетерминалы (имена правил)
  Σ — терминалы (токены)
  R — правила продукции
  S — стартовый нетерминал
```

Пример — арифметические выражения:

```
E  → E '+' T    // E плюс T
   | E '-' T
   | T

T  → T '*' F    // T умноженное на F
   | T '/' F
   | F

F  → '(' E ')'  // скобочное выражение
   | num        // число
```

Эта грамматика кодирует **приоритет операций**: умножение (`*`) связывает сильнее, чем сложение (`+`), потому что `*` находится ниже в иерархии нетерминалов.

## LL(k) парсеры: нисходящий разбор

### Принцип работы LL

LL(k) парсер работает **сверху вниз (top-down)**: начинает со стартового нетерминала и раскрывает его правила, пока не совпадёт с входом. Первая буква L — Left-to-right (читает слева направо), вторая L — Leftmost derivation (раскрывает самый левый нетерминал), k — количество токенов предпросмотра (lookahead).

Аналогия: LL-парсер — это детектив, который смотрит вперёд и предугадывает, какое правило нужно применить.

### Предсказательный разбор

Ключевой вопрос для LL: "Зная текущий нетерминал и следующие k токенов, какое правило применить?"

```
Грамматика:
stmt → 'if' expr 'then' stmt 'else' stmt
     | 'while' expr 'do' stmt
     | assign

assign → id ':=' expr

Если текущий токен — 'if', выбираем первое правило.
Если 'while' — второе.
Если id — третье.
```

Это возможно, когда грамматика **детерминирована** — каждый нетерминал для каждого токена имеет не более одного применимого правила.

### Таблицы FIRST и FOLLOW

Для построения LL-парсера нужны две функции:

**FIRST($\alpha$)** — множество терминалов, которыми может начинаться строка, выводимая из $\alpha$:

```
Для грамматики:
E → '+' T E'
E'→ '+' T E' | ε
T → id

FIRST(E)  = FIRST('+' T E') = {'+'}
FIRST(E') = {'+', ε}  (может быть пустым)
FIRST(T)  = {'id'}
```

**FOLLOW(A)** — множество терминалов, которые могут следовать за нетерминалом A в любой сентенциальной форме:

```
FOLLOW(E)  = {EOF, ')'}
FOLLOW(E') = {EOF, ')'}  (E' исчезает — берём FOLLOW(E))
FOLLOW(T)  = {'+', EOF, ')'}
```

### LL(1) таблица разбора

По FIRST и FOLLOW строится таблица M[A, a] — какое правило применить для нетерминала A при токене a:

```
        |  id   |  +   |  (   |  )   | $
--------+-------+------+------+------+----
E       |  E→T E'|     | E→T E'|     |
E'      |       |E'→+TE'|     |E'→ε  |E'→ε
T       |  T→id |      | T→(E)|     |
```

Если таблица имеет конфликты (два правила в одной клетке) — грамматика **не** LL(1).

### Рекурсивный спуск (Recursive Descent)

Recursive descent — это ручная реализация LL-парсера. Каждый нетерминал — отдельная функция:

```python
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
    
    def peek(self):
        return self.tokens[self.pos]
    
    def consume(self, expected=None):
        token = self.tokens[self.pos]
        if expected and token.type != expected:
            raise SyntaxError(f"Expected {expected}, got {token.type}")
        self.pos += 1
        return token
    
    # E → T ('+' T)*
    def parse_expr(self):
        left = self.parse_term()
        while self.peek().type == 'PLUS':
            self.consume('PLUS')
            right = self.parse_term()
            left = AddNode(left, right)
        return left
    
    # T → F ('*' F)*
    def parse_term(self):
        left = self.parse_factor()
        while self.peek().type == 'STAR':
            self.consume('STAR')
            right = self.parse_factor()
            left = MulNode(left, right)
        return left
    
    # F → num | '(' E ')'
    def parse_factor(self):
        if self.peek().type == 'NUM':
            token = self.consume('NUM')
            return NumNode(token.value)
        elif self.peek().type == 'LPAREN':
            self.consume('LPAREN')
            node = self.parse_expr()
            self.consume('RPAREN')
            return node
        else:
            raise SyntaxError(f"Unexpected token: {self.peek()}")

# Использование
tokens = tokenize("2 + 3 * 4")
parser = Parser(tokens)
ast = parser.parse_expr()
# AST: AddNode(NumNode(2), MulNode(NumNode(3), NumNode(4)))
```

### Левая рекурсия — враг LL

LL-парсеры не могут обрабатывать левую рекурсию:

```
E → E '+' T | T   # левая рекурсия!

Если вызвать parse_E(), она вызовет parse_E() бесконечно...
```

Нужно устранить левую рекурсию — трансформировать грамматику:

```
# Было (левая рекурсия):
E → E '+' T | T

# Стало (правая рекурсия, эквивалентно):
E  → T E'
E' → '+' T E' | ε
```

## LR(k) парсеры: восходящий разбор

### Принцип работы LR

LR(k) парсер работает **снизу вверх (bottom-up)**: накапливает токены, и когда накопил достаточно для правой части правила — применяет его (reduce). L — Left-to-right, R — Rightmost derivation, k — lookahead.

Аналогия: LR-парсер — это рабочий на конвейере, который складывает детали в стопку (стек) и, когда набралось нужное количество, собирает из них узел.

### Shift-Reduce парсинг

LR-парсер поддерживает **стек** и выполняет две операции:

- **Shift** — перенести следующий токен с входа в стек
- **Reduce** — заменить верхушку стека правой частью правила на левую часть

```
Разбор "2 + 3 * 4" с грамматикой E→E+T|T, T→T*F|F, F→num

Стек          | Вход          | Действие
--------------+---------------+----------
              | 2 + 3 * 4 $   | shift
2             | + 3 * 4 $     | reduce F→num
F             | + 3 * 4 $     | reduce T→F
T             | + 3 * 4 $     | reduce E→T
E             | + 3 * 4 $     | shift
E +           | 3 * 4 $       | shift
E + 3         | * 4 $         | reduce F→num
E + F         | * 4 $         | reduce T→F
E + T         | * 4 $         | shift
E + T *       | 4 $           | shift
E + T * 4     | $             | reduce F→num
E + T * F     | $             | reduce T→T*F
E + T         | $             | reduce E→E+T
E             | $             | accept!
```

### LR(0), SLR(1), LALR(1)

**LR(0)** — самый простой: lookahead 0 (решения только по стеку). Очень мало реальных грамматик.

**SLR(1)** — Simple LR(1). Использует FOLLOW для разрешения конфликтов. Чуть мощнее LR(0).

**LALR(1)** — Lookahead LR(1). Это и есть то, что используют yacc/bison. Почти такой же мощный как LR(1), но таблицы значительно меньше.

**LR(1)** — полный: отдельный lookahead для каждого состояния. Максимальная мощность, но огромные таблицы.

```
Мощность (возрастает):
LR(0) < SLR(1) < LALR(1) < LR(1) < LR(k)

Размер таблиц (возрастает):
LR(0) < SLR(1) < LALR(1) << LR(1)
```

### LALR(1): как работает yacc/bison

yacc (Yet Another Compiler Compiler) — инструмент от AT&T Bell Labs, bison — GNU аналог. Они генерируют LALR(1) парсеры из описания грамматики.

```
/* Грамматика для yacc/bison */
%token NUM PLUS MINUS TIMES DIVIDE LPAREN RPAREN

%%

expr:   expr PLUS   term   { $$ = $1 + $3; }
      | expr MINUS  term   { $$ = $1 - $3; }
      | term               { $$ = $1; }
      ;

term:   term TIMES  factor { $$ = $1 * $3; }
      | term DIVIDE factor { $$ = $1 / $3; }
      | factor             { $$ = $1; }
      ;

factor: LPAREN expr RPAREN { $$ = $2; }
      | NUM                 { $$ = $1; }
      ;
%%
```

Bison генерирует C-код с таблицами переходов. `$$` — значение левой части, `$1`, `$3` — значения элементов правой части.

### Конфликты в LR-парсерах

LR-парсеры могут иметь конфликты:

**Shift/Reduce конфликт:** Парсер не знает — перенести следующий токен или применить свёртку.

Классический пример — "dangling else" (висящий else):

```
stmt → 'if' expr 'then' stmt
     | 'if' expr 'then' stmt 'else' stmt

Для "if e then if e then s else s":
Стек: "if e then [if e then s]"
Входной: "else s"

Shift: else относится к внутреннему if (правильно!)
Reduce: else относится к внешнему if (неправильно)
```

yacc/bison разрешает этот конфликт shift: `else` всегда идёт к ближайшему `if`.

**Reduce/Reduce конфликт:** Два разных правила можно применить к одной верхушке стека. Серьёзная проблема — обычно указывает на ошибку в грамматике.

## PEG (Parsing Expression Grammar) и Packrat Parsing

### Что такое PEG

PEG (Bryan Ford, 2004) — альтернативный формализм для описания грамматик, изначально предназначенный для парсинга, а не для описания языков.

Ключевое отличие от CFG: в PEG нет неоднозначности. Оператор `/` — это приоритетный выбор (ordered choice): если первая альтернатива успешна, вторая даже не пробуется.

```
# PEG грамматика для арифметики
Expr    ← Term (('+'/'−') Term)*
Term    ← Factor (('*'/'/') Factor)*
Factor  ← '(' Expr ')' / Number
Number  ← [0-9]+

# Заметьте: [0-9]+ — это "один или более цифр"
# '*' — ноль или более (Kleene star)
# '?' — ноль или один
# '!' — отрицательный lookahead (не потребляет ввод)
```

### Операторы PEG

```
e1 e2     — последовательность (сначала e1, затем e2)
e1 / e2   — выбор (e1, и если не совпало — e2)
e*        — ноль или более
e+        — один или более
e?        — ноль или один
!e        — NOT (следующий ввод НЕ соответствует e)
&e        — AND (следующий ввод соответствует e, но не потребляется)
```

### Packrat Parsing: O(n) для PEG

Наивная PEG-симуляция — backtracking с экспоненциальным временем в худшем случае. Packrat parsing решает это мемоизацией: каждый результат разбора каждого правила для каждой позиции кешируется.

```python
class PackratParser:
    def __init__(self, text):
        self.text = text
        self.memo = {}   # (rule_name, position) -> result
    
    def parse_rule(self, rule_name, pos):
        key = (rule_name, pos)
        if key in self.memo:
            return self.memo[key]   # кеш!
        
        # Вычислить результат...
        result = self._apply_rule(rule_name, pos)
        self.memo[key] = result
        return result
```

Packrat гарантирует O(n) время — каждое правило для каждой позиции вычисляется не более одного раза. Цена — O(n * |rules|) памяти.

### PEG vs CFG: ключевые отличия

| Характеристика | CFG | PEG |
|---------------|-----|-----|
| Неоднозначность | Возможна | Отсутствует по определению |
| Рекурсия | Левая проблематична для LL | Левая рекурсия — проблема |
| Производительность | Разная | O(n) с packrat |
| Выразительность | Контекстно-свободные | Те же + некоторые КЗ |
| Инструменты | yacc, bison, ANTLR | PEG.js, Lark, pest (Rust) |

### Лень vs жадность в PEG

В PEG квантификаторы жадны (greedy) — потребляют максимум. Это отличается от CFG:

```
# PEG: a* b
Input: "aaab"
a* захватит "aaa", затем b совпадёт — OK

# PEG: a* a  
Input: "aaa"
a* захватит "aaa", затем a больше нет — FAIL
# В CFG такая грамматика могла бы парситься, в PEG нет!
```

## GLR: обобщённый LR для неоднозначных грамматик

Некоторые грамматики (особенно естественных языков) неоднозначны. **GLR (Generalized LR)** — алгоритм Томиты (1985), расширяющий LALR до произвольных CFG.

GLR при конфликтах не выбирает одно действие — он **ветвится**: исследует все возможности параллельно, используя общий стек (Graph-Structured Stack, GSS). Совпадающие части разных ветвей разделяются.

```
Применения GLR:
- GCC использует (использовал) LR(1) с ручными расширениями
- GHC (Haskell) использует Alex + Happy (LALR(1))
- Elkhound — GLR парсер для C++
- SGLR — основа для Spoofax language workbench
```

## ANTLR: мощный генератор парсеров

ANTLR (ANother Tool for Language Recognition) — популярный генератор парсеров на базе LL(*) алгоритма (расширение LL с произвольным lookahead через предикаты).

```antlr
// ANTLR4 грамматика для арифметики
grammar Calc;

// Правила парсера
expr:   expr ('*'|'/') expr    # MulDiv
    |   expr ('+'|'-') expr    # AddSub
    |   INT                    # Int
    |   '(' expr ')'           # Parens
    ;

// Правила лексера
INT:    [0-9]+;
WS:     [ \t\n\r]+ -> skip;
```

ANTLR генерирует парсер на Java/Python/C++/C#/Go/Swift. Широко используется в Apache Spark (Catalyst SQL), Groovy, Thrift.

## Полный пример: рекурсивный спуск для JSON

Реализуем настоящий парсер для подмножества JSON:

```python
import json
from dataclasses import dataclass
from typing import Any, List, Tuple, Dict

class JSONParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
    
    def skip_whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] in ' \t\n\r':
            self.pos += 1
    
    def peek(self) -> str:
        self.skip_whitespace()
        if self.pos >= len(self.text):
            return ''
        return self.text[self.pos]
    
    def consume(self, expected: str):
        self.skip_whitespace()
        if self.text[self.pos:self.pos+len(expected)] != expected:
            raise SyntaxError(
                f"Expected '{expected}' at pos {self.pos}, "
                f"got '{self.text[self.pos:self.pos+10]}...'"
            )
        self.pos += len(expected)
    
    def parse_value(self) -> Any:
        """value → object | array | string | number | 'true' | 'false' | 'null'"""
        ch = self.peek()
        if ch == '{':
            return self.parse_object()
        elif ch == '[':
            return self.parse_array()
        elif ch == '"':
            return self.parse_string()
        elif ch in '-0123456789':
            return self.parse_number()
        elif self.text[self.pos:self.pos+4] == 'true':
            self.pos += 4
            return True
        elif self.text[self.pos:self.pos+5] == 'false':
            self.pos += 5
            return False
        elif self.text[self.pos:self.pos+4] == 'null':
            self.pos += 4
            return None
        else:
            raise SyntaxError(f"Unexpected character '{ch}' at pos {self.pos}")
    
    def parse_object(self) -> Dict:
        """object → '{' (string ':' value (',' string ':' value)*)? '}'"""
        self.consume('{')
        obj = {}
        if self.peek() == '}':
            self.consume('}')
            return obj
        while True:
            self.skip_whitespace()
            key = self.parse_string()
            self.skip_whitespace()
            self.consume(':')
            value = self.parse_value()
            obj[key] = value
            self.skip_whitespace()
            if self.peek() == ',':
                self.consume(',')
            else:
                break
        self.consume('}')
        return obj
    
    def parse_array(self) -> List:
        """array → '[' (value (',' value)*)? ']'"""
        self.consume('[')
        arr = []
        if self.peek() == ']':
            self.consume(']')
            return arr
        while True:
            arr.append(self.parse_value())
            self.skip_whitespace()
            if self.peek() == ',':
                self.consume(',')
            else:
                break
        self.consume(']')
        return arr
    
    def parse_string(self) -> str:
        """Упрощённый парсер строк"""
        self.skip_whitespace()
        self.consume('"')
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] != '"':
            if self.text[self.pos] == '\\':
                self.pos += 2  # escape sequence
            else:
                self.pos += 1
        result = self.text[start:self.pos]
        self.consume('"')
        return result
    
    def parse_number(self) -> float:
        """Упрощённый парсер чисел"""
        self.skip_whitespace()
        start = self.pos
        if self.text[self.pos] == '-':
            self.pos += 1
        while self.pos < len(self.text) and self.text[self.pos].isdigit():
            self.pos += 1
        if self.pos < len(self.text) and self.text[self.pos] == '.':
            self.pos += 1
            while self.pos < len(self.text) and self.text[self.pos].isdigit():
                self.pos += 1
        num_str = self.text[start:self.pos]
        return float(num_str) if '.' in num_str else int(num_str)

# Тест
parser = JSONParser('{"name": "Alice", "age": 30, "scores": [95, 87, 92]}')
result = parser.parse_value()
print(result)
# {'name': 'Alice', 'age': 30, 'scores': [95, 87, 92]}
```

## Pratt Parsing: элегантный разбор выражений

Pratt parsing (Top-Down Operator Precedence, Vaughan Pratt, 1973) — изящный подход для разбора выражений с операторами.

Идея: каждый токен имеет **binding power** (силу связывания). Парсер принимает решения о приоритете на основе этих значений.

```python
class PrattParser:
    """
    Разбор инфиксных выражений с приоритетами оператором.
    Каждый токен имеет:
    - nud (null denotation): как разбирать без левого операнда (prefix)
    - led (left denotation): как разбирать с левым операндом (infix)
    - lbp (left binding power): приоритет как инфикса
    """
    
    def __init__(self, tokens):
        self.tokens = iter(tokens)
        self.token = next(self.tokens)
    
    def advance(self):
        prev = self.token
        self.token = next(self.tokens)
        return prev
    
    def expression(self, rbp=0):
        """
        rbp = right binding power (минимальный приоритет)
        Пока следующий оператор привязан сильнее rbp — поглощаем его
        """
        t = self.advance()
        left = t.nud(self)  # разбираем как prefix
        
        while rbp < self.token.lbp:
            t = self.advance()
            left = t.led(self, left)  # разбираем как infix
        
        return left

# Для '+' с приоритетом 10 и '*' с приоритетом 20:
# expression("2+3*4"):
#   left = 2
#   "+" lbp=10 > rbp=0: left = Add(2, expression(10))
#     expression(10) -> left=3
#       "*" lbp=20 > rbp=10: left = Mul(3, expression(20))
#         expression(20) -> left=4, ")" lbp=0 <= 20, return 4
#       left = Mul(3, 4)
#     ")" lbp=0 <= 10, return Mul(3,4)
#   left = Add(2, Mul(3,4))
```

Pratt parsing используется в clang C parser, V8's parser, и ruffparser для Python.

## Сравнение подходов

| Метод | Направление | Примеры инструментов | Когда выбрать |
|-------|-------------|---------------------|---------------|
| Recursive Descent | Top-down | Clang, GCC (ручной), Python | Простые языки, полный контроль |
| LL(k) + таблица | Top-down | ANTLR | Чистые LL грамматики |
| LALR(1) | Bottom-up | yacc, bison, PLY | Классические ЯП, широкий класс грамматик |
| GLR | Bottom-up | Bison --glr, Spoofax | Неоднозначные грамматики |
| PEG + Packrat | Top-down | PEG.js, Lark, pest | Нет неоднозначностей, O(n) |
| Pratt Parsing | Top-down | Clang, V8 | Выражения с операторами |

## Итоги

Парсинг — богатая область с множеством алгоритмов, каждый со своими trade-off:

- **LL** — интуитивен, легко реализовать вручную (recursive descent), но ограничен левой рекурсией
- **LR** — мощнее LL, LALR(1) используется в yacc/bison, но таблицы нечитаемы
- **PEG** — детерминирован, O(n) с packrat, но расходует память
- **GLR** — для неоднозначных грамматик
- **Pratt** — элегантен для выражений

Реальные компиляторы (GCC, Clang, rustc) обычно используют **рукописный recursive descent** — это даёт максимальный контроль над сообщениями об ошибках и восстановлением после них.

## Литература

1. Aho, A. V., Lam, M. S., Sethi, R., & Ullman, J. D. (2006). *Compilers: Principles, Techniques, and Tools* (2nd ed.). Addison-Wesley. — Главы 4-5: LL, LR, LALR. "Книга Дракона".

2. Ford, B. (2004). Parsing Expression Grammars: A Recognition-Based Syntactic Foundation. *POPL '04*. https://bford.info/pub/lang/peg/

3. Ford, B. (2002). Packrat Parsing: Simple, Powerful, Lazy, Linear Time. *ICFP 2002*. https://bford.info/pub/lang/packrat-icfp02.pdf

4. Pratt, V. R. (1973). Top down operator precedence. *Proceedings of POPL 1973*. https://dl.acm.org/doi/10.1145/512927.512931

5. Tomita, M. (1986). *Efficient Parsing for Natural Language*. Kluwer Academic Publishers. — GLR алгоритм.

6. ANTLR4 Documentation. https://www.antlr.org/

7. Grune, D., & Jacobs, C. J. H. (2008). *Parsing Techniques: A Practical Guide* (2nd ed.). Springer. https://dickgrune.com/Books/PTAPG_2nd_Edition/

8. Johnson, S. C. (1975). Yacc: Yet Another Compiler-Compiler. *Bell Labs Technical Memorandum*. https://minnie.tuhs.org/cgi-bin/utree.pl?file=V6/usr/doc/yacc

9. Nystrom, R. (2021). *Crafting Interpreters*. https://craftinginterpreters.com/ — прекрасное руководство по recursive descent и Pratt parsing

10. Earley, J. (1970). An efficient context-free parsing algorithm. *Communications of the ACM*, 13(2), 94–102. https://dl.acm.org/doi/10.1145/362007.362035 — алгоритм Эрли для произвольных CFG
