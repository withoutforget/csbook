# Пайплайн компилятора: от лексера до машинного кода

## Введение

Компилятор — одна из самых сложных и элегантных программных систем, созданных человечеством. Задача компилятора кажется простой: взять текст программы на языке высокого уровня и превратить его в набор машинных инструкций. Однако путь от строки `print("Hello, World!")` до последовательности байтов, которые процессор может исполнить, проходит через несколько принципиально различных этапов преобразования.

Понимание этих этапов важно не только для тех, кто пишет компиляторы. Знание внутреннего устройства компилятора позволяет писать более эффективный код, понимать сообщения об ошибках, осознанно использовать флаги оптимизации и, что особенно важно, — создавать инструменты для анализа и трансформации кода: линтеры, рефакторинговые инструменты, инструменты статического анализа.

В этой главе мы пройдём весь пайплайн компилятора на конкретных примерах, рассмотрим промежуточные представления и ключевые оптимизации.

---

## Общая архитектура компилятора

Классический компилятор делится на **фронтенд** (front-end), **мидлэнд** (middle-end) и **бэкенд** (back-end).

```
Исходный текст
      │
      ▼
┌─────────────┐
│   Лексер    │  ← Фронтенд
│  (Tokenizer)│
└──────┬──────┘
       │ Поток токенов
       ▼
┌─────────────┐
│   Парсер    │  ← Фронтенд
│  (Parser)   │
└──────┬──────┘
       │ AST
       ▼
┌─────────────┐
│ Семантика   │  ← Фронтенд
│  (Sema)     │
└──────┬──────┘
       │ Аннотированный AST
       ▼
┌─────────────┐
│ Генерация   │  ← Мидлэнд
│    IR       │
└──────┬──────┘
       │ IR (LLVM IR, Three-address code, ...)
       ▼
┌─────────────┐
│Оптимизатор │  ← Мидлэнд
│  (Passes)   │
└──────┬──────┘
       │ Оптимизированный IR
       ▼
┌─────────────┐
│  Бэкенд     │  ← Бэкенд
│  (CodeGen)  │
└──────┬──────┘
       │ Машинный код / ассемблер
       ▼
   Исполняемый файл
```

Такое разделение даёт важные архитектурные преимущества. LLVM, например, поддерживает десятки языков на фронтенде (C, C++, Rust, Swift, Julia, Kotlin/Native) и десятки целевых архитектур на бэкенде (x86, ARM, RISC-V, WASM). Мидлэнд при этом один — оптимизации применяются один раз для всех языков и всех платформ.

---

## Этап 1: Лексический анализ (Lexer / Tokenizer)

Лексер читает входной поток символов и разбивает его на **токены** — атомарные единицы синтаксиса языка. Токен — это пара (тип, значение), например `(NUMBER, "42")` или `(KEYWORD, "if")`.

### Пример простого лексера на Python

Рассмотрим маленький язык выражений с операциями `+`, `-`, `*`, `/`, скобками и числами.

```python
import re
from dataclasses import dataclass
from typing import List, Optional

# Определяем типы токенов
TOKEN_PATTERNS = [
    ('NUMBER',   r'\d+(\.\d+)?'),   # Целые и дробные числа
    ('PLUS',     r'\+'),
    ('MINUS',    r'-'),
    ('STAR',     r'\*'),
    ('SLASH',    r'/'),
    ('LPAREN',   r'\('),
    ('RPAREN',   r'\)'),
    ('SKIP',     r'[ \t\n]+'),      # Пробелы — пропускаем
    ('MISMATCH', r'.'),             # Всё остальное — ошибка
]

# Компилируем в один большой regex с именованными группами
master_pattern = re.compile(
    '|'.join(f'(?P<{name}>{pattern})' for name, pattern in TOKEN_PATTERNS)
)

@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int

def tokenize(text: str) -> List[Token]:
    tokens = []
    line = 1
    line_start = 0

    for mo in master_pattern.finditer(text):
        kind = mo.lastgroup
        value = mo.group()
        col = mo.start() - line_start

        if kind == 'NUMBER':
            tokens.append(Token(kind, value, line, col))
        elif kind == 'SKIP':
            # Подсчитываем переносы строк
            line += value.count('\n')
            if '\n' in value:
                line_start = mo.end()
        elif kind == 'MISMATCH':
            raise SyntaxError(f'Неожиданный символ {value!r} на строке {line}')
        else:
            tokens.append(Token(kind, value, line, col))

    return tokens

# Тест
code = "3.14 + (2 * 10) - 1"
for tok in tokenize(code):
    print(tok)
```

Вывод:
```
Token(type='NUMBER', value='3.14', line=1, col=0)
Token(type='PLUS',   value='+',    line=1, col=5)
Token(type='LPAREN', value='(',    line=1, col=7)
Token(type='NUMBER', value='2',    line=1, col=8)
Token(type='STAR',   value='*',    line=1, col=10)
Token(type='NUMBER', value='10',   line=1, col=12)
Token(type='RPAREN', value=')',    line=1, col=14)
Token(type='MINUS',  value='-',    line=1, col=16)
Token(type='NUMBER', value='1',    line=1, col=18)
```

Реальные лексеры используют конечные автоматы (DFA) вместо regex для максимальной производительности. Clang, например, обрабатывает миллионы строк C++ в секунду.

---

## Этап 2: Синтаксический анализ (Parser) и построение AST

Парсер получает поток токенов и строит **дерево разбора** (parse tree) или напрямую **абстрактное синтаксическое дерево** (AST). AST — упрощённая, семантически значимая версия дерева разбора: без лишних токенов (скобок, запятых, точек с запятой).

### Abstract Syntax Tree — структура

AST — это дерево, каждый узел которого представляет языковую конструкцию:

```python
from dataclasses import dataclass, field
from typing import Union

# Узлы AST для нашего языка выражений
@dataclass
class Num:
    value: float

@dataclass
class BinOp:
    op: str        # '+', '-', '*', '/'
    left: 'Expr'
    right: 'Expr'

Expr = Union[Num, BinOp]
```

Для выражения `3 + 2 * 10` AST выглядит так:

```
    BinOp('+')
   /          \
Num(3)      BinOp('*')
            /         \
          Num(2)     Num(10)
```

Обратите внимание: дерево уже кодирует приоритет операций! `2 * 10` — отдельное поддерево, вычисляемое первым.

### Рекурсивно-нисходящий парсер

```python
class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_type: str) -> Token:
        tok = self.current()
        if tok is None or tok.type != expected_type:
            raise SyntaxError(f'Ожидался {expected_type}, получен {tok}')
        self.pos += 1
        return tok

    def parse(self) -> Expr:
        return self.parse_expr()

    # expr = term (('+' | '-') term)*
    def parse_expr(self) -> Expr:
        left = self.parse_term()
        while self.current() and self.current().type in ('PLUS', 'MINUS'):
            op = self.current().value
            self.pos += 1
            right = self.parse_term()
            left = BinOp(op, left, right)
        return left

    # term = factor (('*' | '/') factor)*
    def parse_term(self) -> Expr:
        left = self.parse_factor()
        while self.current() and self.current().type in ('STAR', 'SLASH'):
            op = self.current().value
            self.pos += 1
            right = self.parse_factor()
            left = BinOp(op, left, right)
        return left

    # factor = NUMBER | '(' expr ')'
    def parse_factor(self) -> Expr:
        tok = self.current()
        if tok and tok.type == 'NUMBER':
            self.pos += 1
            return Num(float(tok.value))
        if tok and tok.type == 'LPAREN':
            self.pos += 1
            expr = self.parse_expr()
            self.consume('RPAREN')
            return expr
        raise SyntaxError(f'Неожиданный токен: {tok}')

# Тест
tokens = tokenize("3 + 2 * 10")
parser = Parser(tokens)
ast = parser.parse()
print(ast)
# BinOp(op='+', left=Num(value=3.0), right=BinOp(op='*', left=Num(value=2.0), right=Num(value=10.0)))
```

### Обходы AST

AST обходят по-разному в зависимости от задачи:

**Вычисление (Visitor pattern):**
```python
def evaluate(node: Expr) -> float:
    if isinstance(node, Num):
        return node.value
    if isinstance(node, BinOp):
        l = evaluate(node.left)
        r = evaluate(node.right)
        if node.op == '+': return l + r
        if node.op == '-': return l - r
        if node.op == '*': return l * r
        if node.op == '/': return l / r
    raise ValueError(f'Unknown node: {node}')

tokens = tokenize("3 + 2 * 10")
ast = Parser(tokens).parse()
print(evaluate(ast))  # 23.0
```

**Красивая печать (pretty-print):**
```python
def pretty(node: Expr, indent: int = 0) -> str:
    pad = '  ' * indent
    if isinstance(node, Num):
        return f'{pad}Num({node.value})'
    if isinstance(node, BinOp):
        return (f'{pad}BinOp({node.op!r})\n'
                f'{pretty(node.left, indent+1)}\n'
                f'{pretty(node.right, indent+1)}')
```

---

## Этап 3: Семантический анализ

После построения AST компилятор выполняет семантический анализ: проверяет, что программа **осмысленна**, даже если синтаксически корректна.

Типичные задачи:

- **Разрешение имён** (name resolution): к какому объявлению относится каждое имя
- **Проверка типов** (type checking): совместимы ли типы выражений
- **Проверка потока управления**: нет ли недостижимого кода, возвращает ли функция значение по всем путям
- **Проверка заимствований** (borrow checking) в Rust

```c
// Синтаксически корректно, но семантически нет:
int x = "hello";           // Ошибка типа
int y = undefined_var;     // Неразрешённое имя
```

Семантический анализ создаёт **таблицу символов** (symbol table) — структуру данных, хранящую информацию о каждом идентификаторе: тип, область видимости, расположение.

---

## Этап 4: Промежуточное представление (IR)

После семантического анализа компилятор преобразует AST в **промежуточное представление** (Intermediate Representation, IR). IR — это язык ниже уровнем, чем исходный, но выше машинного кода. IR удобен для оптимизаций: он более регулярен и явен.

### LLVM IR

LLVM IR — один из самых влиятельных форматов IR в современных компиляторах. Он используется в Clang, Rust, Swift, Julia и десятках других языков.

Пример C-функции и соответствующего LLVM IR:

```c
// Исходный C-код
int add(int a, int b) {
    return a + b;
}
```

```llvm
; LLVM IR (сгенерированный clang -S -emit-llvm)
define i32 @add(i32 %a, i32 %b) {
entry:
  %result = add i32 %a, %b
  ret i32 %result
}
```

Более сложный пример с условием:

```c
int max(int a, int b) {
    if (a > b) return a;
    else return b;
}
```

```llvm
define i32 @max(i32 %a, i32 %b) {
entry:
  %cmp = icmp sgt i32 %a, %b    ; signed greater than
  br i1 %cmp, label %then, label %else

then:
  ret i32 %a

else:
  ret i32 %b
}
```

Характеристики LLVM IR:
- **Типизирован**: `i32`, `i64`, `float`, `double`, `i8*` (указатель)
- **SSA форма** (Static Single Assignment): каждая переменная присваивается ровно один раз
- **Явные basic blocks**: блоки инструкций с явными переходами
- **Portable**: не привязан к конкретной архитектуре

### SSA форма (Static Single Assignment)

SSA — ключевое свойство современных IR. В SSA каждая переменная определяется ровно один раз. При слиянии потоков управления используется специальная инструкция **phi** ($\varphi$-функция).

```c
// C-код
int x = 1;
if (cond) {
    x = 2;
}
return x;
```

```llvm
; SSA форма
entry:
  br i1 %cond, label %if_true, label %merge

if_true:
  br label %merge

merge:
  ; x_3 = phi(x_1 из entry, x_2 из if_true)
  %x_3 = phi i32 [ 1, %entry ], [ 2, %if_true ]
  ret i32 %x_3
```

SSA упрощает многие оптимизации: легко отслеживать, где определяется и используется каждое значение, без анализа псевдонимов (aliasing).

---

## Этап 5: Оптимизации компилятора

Это сердце мидлэнда — серия **проходов** (passes), каждый из которых преобразует IR в более эффективный IR.

### Constant Folding (свёртка констант)

Вычисление константных выражений на этапе компиляции:

```c
// До оптимизации
int x = 2 + 3 * 4;  // 2 + 12

// После constant folding
int x = 14;          // вычислено компилятором
```

В LLVM IR:
```llvm
; До
%tmp = mul i32 3, 4
%x = add i32 2, %tmp

; После constant folding
%x = i32 14          ; константа!
```

### Dead Code Elimination (удаление мёртвого кода)

```c
// Мёртвый код: x никогда не используется
int x = expensive_computation();  // будет удалено

// Мёртвая ветка
if (0) {
    printf("never\n");  // будет удалено
}
```

### Function Inlining (подстановка функций)

```c
static inline int square(int x) { return x * x; }

// Вызов
int result = square(5);

// После inlining
int result = 5 * 5;  // без накладных расходов вызова
// Затем constant folding:
int result = 25;
```

Inlining позволяет компилятору видеть «через» границы функций и применять другие оптимизации.

### Loop Unrolling (разворачивание циклов)

```c
// До
for (int i = 0; i < 4; i++) {
    a[i] = b[i] + c[i];
}

// После loop unrolling (×4)
a[0] = b[0] + c[0];
a[1] = b[1] + c[1];
a[2] = b[2] + c[2];
a[3] = b[3] + c[3];
```

Уменьшается число проверок условия цикла и декрементов счётчика. При достаточно большом теле цикла это даёт заметный прирост производительности, а также открывает возможности для векторизации (SIMD).

### Loop Vectorization (векторизация)

```c
// Скалярный цикл
for (int i = 0; i < N; i++) {
    c[i] = a[i] + b[i];
}

// После автовекторизации: использует SSE/AVX
// Обрабатывает 4 или 8 элементов одновременно
```

### Посмотреть оптимизации: Godbolt Compiler Explorer

Сайт [godbolt.org](https://godbolt.org) позволяет в реальном времени видеть генерируемый ассемблер для разных компиляторов и уровней оптимизации.

```c
// Введите в godbolt.org:
int sum(int* a, int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += a[i];
    return s;
}
```

С флагом `-O0` (без оптимизаций) — подробный, дословный ассемблер.
С флагом `-O3` — развёрнутый, векторизованный цикл с инструкциями `vpaddq`.

---

## Этап 6: Генерация кода (Code Generation)

Бэкенд преобразует оптимизированный IR в машинные инструкции целевой архитектуры. Это многошаговый процесс:

1. **Instruction Selection** (выбор инструкций): сопоставление паттернов IR с машинными инструкциями
2. **Register Allocation** (распределение регистров): какие значения держать в регистрах
3. **Instruction Scheduling** (планирование инструкций): переупорядочивание инструкций для лучшего использования конвейера

### Распределение регистров

Это NP-полная задача (сводится к раскраске графа). Компиляторы используют эвристики. Граф **интерференции** регистров: два значения "конкурируют", если они живут одновременно.

```python
# Простой пример: три значения, два регистра
# a и b живут вместе → разные регистры
# b и c живут вместе → разные регистры
# a и c НЕ живут вместе → могут быть в одном регистре

a = 1      # a → R1
b = a + 2  # b → R2  (a ещё жив)
# a умирает
c = b + 3  # c → R1  (R1 свободен!)
```

Когда регистров не хватает, значения **выгружаются** (spill) в стек — это дорогостоящая операция.

---

## AOT vs JIT компиляция

### Ahead-of-Time (AOT)

Традиционная компиляция: весь код компилируется **до** выполнения. Примеры: GCC, Clang (C/C++/Rust), Go (по умолчанию).

**Плюсы:**
- Максимальная производительность выполнения (компилятор имеет всё время)
- Нет накладных расходов при запуске
- Результат — нативный бинарный файл

**Минусы:**
- Медленная сборка
- Нет адаптации к конкретным данным во время выполнения
- Нужен отдельный бинарник для каждой платформы

### Just-in-Time (JIT)

Компиляция **во время** выполнения. Примеры: JVM HotSpot, V8 (JavaScript), PyPy.

**Плюсы:**
- Адаптация к реальным данным (например, можно не проверять тип, если он всегда `int`)
- Один байткод — все платформы
- Может быть быстрее AOT для конкретной нагрузки

**Минусы:**
- Время «разогрева» (warm-up time)
- Накладные расходы на профилирование
- Сложнее предсказать поведение

```
Скорость:
Интерпретатор < JIT (холодный) < AOT < JIT (горячий, профилированный)

На практике JVM HotSpot нередко обгоняет C++ на долгоживущих серверных нагрузках,
потому что JIT оптимизирует под конкретный профиль вызовов.
```

### Полный пример: путь выражения `1 + 2 * 3` через пайплайн

```
Исходный код:  "1 + 2 * 3"

=== ЛЕКСЕР ===
[NUMBER(1), PLUS, NUMBER(2), STAR, NUMBER(3)]

=== ПАРСЕР → AST ===
BinOp('+',
  Num(1),
  BinOp('*', Num(2), Num(3))
)

=== СЕМАНТИКА ===
(все узлы имеют тип: float)

=== ГЕНЕРАЦИЯ IR (упрощённый three-address code) ===
t1 = 2 * 3
t2 = 1 + t1
return t2

=== CONSTANT FOLDING ===
t1 = 6        ; 2*3 → 6
t2 = 7        ; 1+6 → 7
return 7

=== DEAD CODE ELIMINATION ===
return 7      ; t1, t2 не нужны

=== ГЕНЕРАЦИЯ ASM (x86-64) ===
mov eax, 7
ret
```

---

## Дополнительные концепции

### Атрибутные грамматики

AST часто аннотируется **атрибутами** — вычисляемыми значениями (типы, константные значения, размеры). Атрибуты могут быть:
- **Синтезированными** (synthesized): вычисляются снизу вверх
- **Наследуемыми** (inherited): передаются сверху вниз

### Link-Time Optimization (LTO)

Современные компиляторы поддерживают LTO — оптимизацию на этапе линковки, когда видны все модули сразу. Это позволяет выполнять inlining через границы единиц компиляции.

```bash
gcc -O3 -flto -o program main.c utils.c  # LTO включён
```

### Profile-Guided Optimization (PGO)

Двухэтапная компиляция: сначала собрать инструментированный бинарник, запустить на реальной нагрузке, затем перекомпилировать с учётом профиля.

```bash
# Этап 1: компиляция с инструментацией
clang -O2 -fprofile-instr-generate -o program_instrumented main.c

# Этап 2: запуск для сбора профиля
./program_instrumented < real_workload.txt

# Этап 3: оптимизация по профилю
clang -O2 -fprofile-instr-use=default.profdata -o program_optimized main.c
```

PGO может давать 10–30% ускорения по сравнению с обычным `-O3`.

---

## Практика: исследование компилятора

### Посмотреть токены в Python (ast.parse)

```python
import ast, tokenize, io

code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""

# Токены
tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
for tok in tokens[:10]:
    print(tok)

# AST
tree = ast.parse(code)
print(ast.dump(tree, indent=2))
```

### Посмотреть LLVM IR

```bash
# Установите clang
clang -S -emit-llvm -O1 -o output.ll input.c

# Или в godbolt.org выберите "LLVM IR" в качестве компилятора
```

### Посмотреть оптимизации GCC

```bash
gcc -O3 -fopt-info-optimized -c main.c 2>&1 | head -20
# Покажет список применённых оптимизаций
```

---

## Резюме

Пайплайн компилятора — это серия семантических преобразований, каждое из которых переводит программу в более удобный для следующего этапа вид:

| Этап | Вход | Выход | Цель |
|------|------|-------|------|
| Лексер | Текст | Токены | Разбить на атомы |
| Парсер | Токены | AST | Построить структуру |
| Семантика | AST | Аннотированный AST | Проверить смысл |
| IR Gen | AST | IR | Нормализовать |
| Оптимизатор | IR | IR | Ускорить |
| CodeGen | IR | Asm/машинный код | Целевая платформа |

Понимание этих этапов позволяет осознанно использовать компилятор как инструмент: выбирать правильные флаги оптимизации, понимать сообщения об ошибках, писать код, удобный для оптимизации, и создавать собственные инструменты анализа кода.

---

## Литература и источники

1. Aho, A. V., Lam, M. S., Sethi, R., Ullman, J. D. *Compilers: Principles, Techniques, and Tools* (2nd ed.). Addison-Wesley, 2006. («Книга Дракона» — классический учебник по компиляторам.)

2. Cooper, K. D., Torczon, L. *Engineering a Compiler* (2nd ed.). Morgan Kaufmann, 2011. (Более современный и доступный учебник.)

3. Appel, A. W. *Modern Compiler Implementation in ML/Java/C*. Cambridge University Press, 1998.

4. Lattner, C., Adve, V. *LLVM: A Compilation Framework for Lifelong Program Analysis & Transformation*. CGO 2004. (Оригинальная статья о LLVM.)

5. LLVM Language Reference Manual. https://llvm.org/docs/LangRef.html

6. GCC Internals Manual. https://gcc.gnu.org/onlinedocs/gccint/

7. Godbolt Compiler Explorer. https://godbolt.org — незаменимый инструмент для изучения генерируемого кода.

8. Rosen, B. K., Wegman, M. N., Zadeck, F. K. *Global Value Numbers and Redundant Computations*. POPL 1988. (Оригинальная статья об SSA.)

9. Brandner, F. et al. *Computing Liveness Sets for SSA-Form Programs*. INRIA Research Report, 2011.

10. Muchnick, S. S. *Advanced Compiler Design and Implementation*. Morgan Kaufmann, 1997. (Углублённый материал по оптимизациям.)
