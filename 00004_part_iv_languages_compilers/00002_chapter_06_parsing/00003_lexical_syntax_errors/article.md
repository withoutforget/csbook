# Лексические и синтаксические ошибки: восстановление и диагностика

Компилятор — это не просто переводчик кода. Это первый собеседник разработчика, с которым он разговаривает через текст программы. Качество сообщений об ошибках прямо влияет на продуктивность — плохие сообщения превращают отладку в мучение, хорошие — направляют к решению. Но прежде чем выдавать хорошее сообщение, компилятор должен уметь восстанавливаться после ошибки и продолжить анализ.

## Фазы компилятора и типы ошибок

Ошибки в программе обнаруживаются на разных этапах компиляции:

```
Исходный код
    │
    ▼
Лексический анализ (лексер/токенизатор)
    │ Лексические ошибки: недопустимые символы, незакрытые строки
    ▼
Синтаксический анализ (парсер)
    │ Синтаксические ошибки: нарушение грамматики, пропущенные {}, ;
    ▼
Семантический анализ
    │ Семантические ошибки: несовместимые типы, необъявленные переменные
    ▼
Кодогенерация
    │ (обычно без ошибок на этом этапе)
    ▼
Объектный код
```

### Лексические ошибки

Лексический анализатор (лексер) превращает поток символов в поток токенов. Лексические ошибки — это ситуации, когда лексер не может распознать токен.

**Типичные лексические ошибки:**

```python
# 1. Недопустимый символ
x = 5 @ 3    # @ не является допустимым оператором (в C/Java)

# 2. Незакрытая строка
s = "hello
# Строка не закрыта — лексер "поглотит" всё до конца файла или следующей строки

# 3. Незакрытый комментарий
/* это комментарий
  он не закрыт!
  
# 4. Некорректный числовой литерал
x = 123abc    # число не может содержать буквы (в большинстве языков)
x = 0x1G2F    # G — недопустимая hex цифра

# 5. Слишком длинный идентификатор
verylongidentifierthatexceedsthemaximumallowedlengthspecified = 5
```

### Синтаксические ошибки

Синтаксические ошибки возникают, когда парсер получает токены, не соответствующие грамматике.

```c
// 1. Пропущенная точка с запятой
int x = 5
int y = 10;   // error: expected ';'

// 2. Несбалансированные скобки
if (x > 0 {   // error: expected ')'
    return x;
}

// 3. Неожиданный токен
int[] arr = {1, 2, 3}    // error в Java: нужно new int[]
int[] arr = new int[] {1, 2, 3};  // правильно

// 4. Неправильный порядок
void return int myFunc() {}  // error: типы не в том порядке
```

## Паника (panic mode recovery): простейший метод восстановления

Самый распространённый метод восстановления после ошибок — **паника** (panic mode recovery). Когда парсер обнаруживает ошибку, он выбрасывает токены до тех пор, пока не найдёт "якорный" токен (synchronization token) — токен, который позволяет продолжить разбор.

### Синхронизирующие токены

В большинстве языков хорошими синхронизаторами являются:
- Точка с запятой `;` — конец инструкции
- Закрывающая скобка `}` — конец блока
- Ключевые слова `class`, `function`, `def`, `if`, `for` — начало конструкции

```python
# Псевдокод panic mode recovery в парсере
def parse_statement(self):
    try:
        return self._parse_statement_impl()
    except SyntaxError as e:
        self.report_error(e)
        self.synchronize()   # паника: выбрасываем токены
        return ErrorNode()   # возвращаем узел-ошибку
        
def synchronize(self):
    """Выбрасываем токены до следующего "якоря" """
    SYNC_TOKENS = {TokenType.SEMICOLON, TokenType.RBRACE, 
                   TokenType.IF, TokenType.WHILE, TokenType.FOR,
                   TokenType.RETURN, TokenType.CLASS}
    
    while not self.is_at_end():
        if self.previous().type == TokenType.SEMICOLON:
            return  # ; найдена — восстановились
        if self.peek().type in SYNC_TOKENS:
            return  # ключевое слово найдено
        self.advance()  # выбрасываем токен
```

### Плюсы и минусы panic mode

**Плюсы:**
- Простота реализации
- Никогда не "застревает" в бесконечном цикле
- Продолжает компиляцию после первой ошибки

**Минусы:**
- Может пропустить значительную часть кода
- Может привести к "каскадным ошибкам" — ложным ошибкам, вызванным первой
- Плохо работает для вложенных структур

```
Пример каскадных ошибок (C):
if (x > 0 {     // ошибка 1: пропущена ')'
    x = 5;
}

Парсер в панике выбросит токены до '}' — 
пропустит "x = 5" и может неправильно интерпретировать следующий код!
```

## Фразово-уровневое восстановление (phrase-level recovery)

Более умный метод: когда ошибка обнаружена, парсер **вставляет или удаляет** токены, чтобы продолжить разбор.

```python
# Пример: восстановление после пропущенной точки с запятой
def expect_semicolon(self):
    if self.peek() == SEMICOLON:
        self.advance()
    else:
        # Вставляем виртуальную ';' — продолжаем без неё
        self.report_error(
            f"Missing ';' after statement at line {self.line}"
        )
        # Не потребляем текущий токен — продолжаем с ним
```

### Insertion и deletion

**Token insertion (вставка):** Парсер предполагает, что нужный токен "отсутствует" и продолжает, как если бы он был.

```
Ошибка: if x > 0) { ... }
        ^— пропущена открывающая скобка

Восстановление: вставить '(' перед x
Продолжить: if (x > 0) { ... }
```

**Token deletion (удаление):** Парсер предполагает, что текущий токен лишний.

```
Ошибка: int x = ,, 5;
               ^— лишняя запятая

Восстановление: удалить первую ','
Продолжить: int x = , 5;
            ^— ещё одна, но хотя бы продолжили
```

### Minimum-cost recovery

Оптимальный подход — найти минимальное количество вставок/удалений для восстановления. Это NP-полная задача в общем случае, поэтому используются эвристики.

GCC, например, использует несколько десятков специализированных эвристик восстановления, написанных вручную для типичных случаев.

## Error productions в грамматике

**Error productions** — правила грамматики, явно описывающие типичные ошибки:

```yacc
/* Обычное правило: */
expr : expr '+' term

/* Error production: ловим пропущенный оператор */
expr : expr error term {
    yyerrok;
    yyerror("Missing operator between expressions");
    $$ = new ErrorNode();
}

/* Восстановление после незакрытой скобки */
paren_expr : '(' expr ')' 
           | '(' expr error {   /* нет ')' */
               yyerror("Missing closing parenthesis");
               yyerrok;
               $$ = $2;
           }
```

В yacc/bison специальный токен `error` позволяет указывать точки синхронизации:

```c
/* Яркий пример из практики — recovery в блоке */
statement_list
    : statement
    | statement_list statement
    | error ';'    /* при ошибке — синхронизируемся по ';' */
        { yyerrok; }
    ;
```

## Как работают современные компиляторы

### GCC: несколько десятилетий эволюции

GCC начинался с простого panic-mode recovery. За десятилетия накопились сотни специализированных эвристик.

Примеры диагностик GCC:

```c
// Ошибка:
int main() {
    if x > 0 {   // отсутствие скобок
        return 1;
    }
}

// GCC выдаёт:
// error: expected '(' before 'x'
// Но продолжает компиляцию!

// Ещё один пример:
void foo() {
    int x = 5
    int y = 10;
}

// GCC:
// error: expected ';' before 'int'
// Указывает точную позицию!
```

### Clang: диагностика нового уровня

Clang (LLVM C/C++ frontend) поставил качество диагностики в приоритет с самого начала. Авторы Clang писали: "Хорошие диагностики важнее скорости компиляции".

```c
// Clang vs GCC — сравнение сообщений

// Код с ошибкой:
#include <vector>
std::vector<int> v;
v.push_back("hello");

// GCC (старые версии):
// error: no matching function for call to 'std::vector<int>::push_back(const char [6])'
// (очень длинное сообщение про шаблоны)

// Clang:
// error: no matching member function for call to 'push_back'
// note: candidate function not viable: no known conversion from 
//       'const char [6]' to 'const int &' for 1st argument
//       void push_back(const value_type &__x)
//                      ~~~~~~~~~~~~~~~~~~~~^
```

Clang показывает **стрелку** на проблемное место:

```
test.c:3:5: error: use of undeclared identifier 'x'
    x = 5;
    ^
1 error generated.
```

### Roslyn (C# компилятор): Error Recovery как feature

Roslyn — Microsoft компилятор для C# и Visual Basic, предназначенный для использования в IDE. Поэтому восстановление после ошибок — это *основная* функция, а не дополнение.

Roslyn создаёт **зелёные/красные узлы** (green/red nodes):

```
Green tree (immutable, shared): полное AST
Red tree (contextual): производная от зелёного

При ошибке:
- Создаётся ErrorNode с информацией о пропущенных токенах
- Соседние узлы остаются корректными
- IDE показывает подчёркивания только под реально проблемными местами
- Остальной код продолжает анализироваться корректно
```

```csharp
// Roslyn: даже при синтаксических ошибках работает IntelliSense!
public class MyClass {
    public void MyMethod() {
        int x =    // незавершённое выражение
        // Roslyn создаёт: AssignmentStatement(x, MissingToken)
        // IntelliSense всё ещё работает для следующих строк!
        Console.WriteLine("hello");
    }
}
```

## LSP (Language Server Protocol) и диагностика

LSP (Language Server Protocol) — стандарт Microsoft для общения между редакторами и language servers. Диагностика — один из ключевых элементов.

### Протокол диагностики

```json
// Сервер отправляет редактору диагностику (textDocument/publishDiagnostics):
{
  "uri": "file:///path/to/file.py",
  "diagnostics": [
    {
      "range": {
        "start": {"line": 10, "character": 5},
        "end": {"line": 10, "character": 15}
      },
      "severity": 1,  // 1=Error, 2=Warning, 3=Info, 4=Hint
      "code": "E0001",
      "source": "mycompiler",
      "message": "Undefined variable 'myVar'",
      "relatedInformation": [
        {
          "location": {
            "uri": "file:///path/to/file.py",
            "range": {"start": {"line": 5, "character": 0}, ...}
          },
          "message": "Did you mean 'myVariable' declared here?"
        }
      ]
    }
  ]
}
```

### Инкрементальный парсинг для LSP

LSP-серверы перепарсируют файл при каждом нажатии клавиши. Для больших файлов это дорого. Решение — **инкрементальный парсинг**.

Tree-sitter — популярная библиотека для инкрементального парсинга:

```javascript
// tree-sitter: парсит только изменённую часть файла
const Parser = require('tree-sitter');
const Python = require('tree-sitter-python');

const parser = new Parser();
parser.setLanguage(Python);

// Первый парс
let tree = parser.parse('def foo():\n    return 1\n');

// Инкрементальный апдейт: изменили "1" на "42"
const newTree = parser.parse('def foo():\n    return 42\n', tree, [{
    startIndex: 27,
    oldEndIndex: 28,
    newEndIndex: 29,
    startPosition: {row: 1, column: 11},
    oldEndPosition: {row: 1, column: 12},
    newEndPosition: {row: 1, column: 13}
}]);
// tree-sitter перепарсит только изменённую часть
```

## Дизайн качественных сообщений об ошибках

Это отдельное искусство. Haskell компилятор GHC в своё время имел репутацию нечитаемых ошибок для новичков. Rust пошёл в другую сторону и сделал ставку на педагогические сообщения.

### Принципы хороших сообщений

**1. Точная локализация:** Покажи, где именно ошибка.

```
# Плохо:
SyntaxError: invalid syntax

# Хорошо:
  File "test.py", line 5, column 12
      x = foo(1, 2
                  ^
SyntaxError: ',' or ')' expected (got EOF)
```

**2. Описание проблемы:** Что именно не так?

```
# Плохо:
error: type mismatch

# Хорошо:
error[E0308]: mismatched types
 --> src/main.rs:5:9
  |
5 |     let x: i32 = "hello";
  |            ---   ^^^^^^^ expected `i32`, found `&str`
  |            |
  |            expected due to this
```

**3. Предложение решения:** Что сделать, чтобы исправить?

```
# Rust — "cannot borrow as mutable" с предложением fix
error[E0596]: cannot borrow `v` as mutable, as it is not declared as mutable
 --> src/main.rs:3:5
  |
2 |     let v = Vec::new();
  |         - help: consider changing this to be mutable: `mut v`
3 |     v.push(1);
  |     ^^^^^^^^^ cannot borrow as mutable
```

**4. Не показывать слишком много:** Первые N ошибок важны, остальные — шум.

```c
// Одна синтаксическая ошибка может вызвать сотни "вторичных"
// Умные компиляторы ограничивают вывод (--max-errors=10 в GCC)
```

**5. Учитывать опечатки:** Levenshtein distance для предложений.

```
error: unresolved import `std::collectons`
      |               ^^^^^^^^^^^^^^^^^^
      | help: a similar path exists: `std::collections`
```

### Примеры хороших vs плохих сообщений

```python
# Python 3.10+ улучшил сообщения об ошибках

# До 3.10:
# SyntaxError: invalid syntax
# (и указывает на строку ПОСЛЕ ошибки)

# После 3.10:
x = {1: 'one', 2: 'two'
# SyntaxError: '{' was never closed
#   File "test.py", line 1
#     x = {1: 'one', 2: 'two'
#         ^
# Указывает НА ОТКРЫВАЮЩУЮ скобку!
```

```javascript
// Node.js vs Deno — качество ошибок

// Node.js (старый):
// ReferenceError: x is not defined

// Deno (современный):
// error: Uncaught ReferenceError: x is not defined
//     at foo (file:///test.js:3:12)
//     at file:///test.js:6:1
// + ссылка на документацию
```

### Rust: эталон качества диагностики

Rust компилятор известен исключительно хорошими сообщениями об ошибках. Примеры:

```rust
// Ошибка заимствования:
fn main() {
    let s = String::from("hello");
    let r1 = &s;
    let r2 = &s;
    let r3 = &mut s;  // ошибка!
    println!("{}, {}, {}", r1, r2, r3);
}

// rustc:
// error[E0502]: cannot borrow `s` as mutable because it is 
// also borrowed as immutable
//  --> src/main.rs:5:14
//   |
// 3 |     let r1 = &s;
//   |               - immutable borrow occurs here
// 4 |     let r2 = &s;
// 5 |     let r3 = &mut s;
//   |              ^^^^^^ mutable borrow occurs here
// 6 |     println!("{}, {}, {}", r1, r2, r3);
//   |                            -- immutable borrow later used here
```

Это не просто "ошибка" — это **полная история**: где произошло immutable borrow, где mutable, где используется.

## Диагностика в IDE: подсвечивание в реальном времени

Современные IDE используют Language Servers для диагностики по мере набора текста.

```typescript
// VS Code + TypeScript Language Server
// Ошибки показываются без компиляции!

function greet(name: string) {
    return "Hello, " + name;
}

greet(42);  // Красная волнистая линия:
// Argument of type 'number' is not assignable to parameter of type 'string'.
```

### Quick fixes

LSP поддерживает "quick fixes" — автоматические исправления:

```
// При ошибке "variable might be undefined":
let x = possiblyUndefined;
x.toString();
          ^^
// Quick fix: "Add null check"
// Применяет: if (x !== null && x !== undefined) { x.toString(); }
```

## Восстановление при лексических ошибках

Лексер тоже должен восстанавливаться:

### Незакрытые строки

```python
# Python лексер при незакрытой строке:
s = "hello   # нет закрывающей кавычки
world"

# Стратегия: взять всё до конца строки как строку
# Выдать предупреждение: "string literal unterminated"
# Продолжить со следующей строки
```

### Недопустимые символы

```python
class Lexer:
    def next_token(self):
        ch = self.current_char()
        
        if ch in VALID_CHARS:
            return self._lex_token(ch)
        else:
            # Восстановление: пропустить символ, выдать ошибку
            self.report_error(
                LexError(f"Invalid character '{ch}'", self.position)
            )
            self.advance()   # пропустить проблемный символ
            return self.next_token()   # продолжить
```

## Стратегии для продолжения после множественных ошибок

### Подавление вторичных ошибок

```
// Пример: одна ошибка объявления вызывает множество "use of undeclared":
int foo() {
    int x = bar();  // ошибка: bar не объявлена
    return x + 1;   // это нормально!
}

bar(1);  // ошибка: bar не объявлена
bar(2);  // ошибка: bar не объявлена (вторичная!)
```

Умный компилятор запоминает "проблемные" символы и подавляет повторные ошибки о них:

```python
class ErrorTracker:
    def __init__(self):
        self.reported_undefined = set()
    
    def report_undefined_variable(self, name, location):
        if name not in self.reported_undefined:
            self.report_error(f"Undefined variable '{name}'", location)
            self.reported_undefined.add(name)
        # Не дублируем ошибку для того же имени!
```

### Error nodes в AST

Вместо того чтобы прерывать парсинг, хорошие парсеры создают **error nodes** — специальные узлы AST, помечающие проблемные места:

```python
# Узел ошибки несёт информацию, но не препятствует разбору
class ErrorNode:
    def __init__(self, message, location, children=None):
        self.message = message
        self.location = location
        self.children = children or []  # что удалось распарсить
        self.is_error = True

# Семантический анализ пропускает поддеревья с ErrorNode
def analyze_node(node):
    if node.is_error:
        return ErrorType()  # продолжаем, но тип — "ошибка"
    # ...обычный анализ
```

## Практическая реализация: простой парсер с recovery

```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, List

class TokenType(Enum):
    NUM = auto(); PLUS = auto(); MINUS = auto()
    STAR = auto(); SLASH = auto()
    LPAREN = auto(); RPAREN = auto()
    SEMICOLON = auto(); EOF = auto()
    ERROR = auto()  # токен-ошибка

@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int

@dataclass
class Error:
    message: str
    line: int
    col: int

class RecoveringParser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.errors: List[Error] = []
    
    def peek(self) -> Token:
        return self.tokens[self.pos]
    
    def advance(self) -> Token:
        t = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return t
    
    def expect(self, ttype: TokenType) -> Optional[Token]:
        if self.peek().type == ttype:
            return self.advance()
        else:
            t = self.peek()
            self.errors.append(Error(
                f"Expected {ttype.name}, got {t.value!r}",
                t.line, t.col
            ))
            return None  # восстанавливаемся без потребления
    
    def synchronize(self, sync_types):
        """Panic mode: пропускаем до синхронизирующего токена"""
        while self.peek().type != TokenType.EOF:
            if self.peek().type in sync_types:
                return
            self.advance()
    
    def parse_expr(self):
        """expr → term (('+' | '-') term)*"""
        left = self.parse_term()
        while self.peek().type in (TokenType.PLUS, TokenType.MINUS):
            op = self.advance()
            right = self.parse_term()
            left = ('binop', op.value, left, right)
        return left
    
    def parse_term(self):
        """term → factor (('*' | '/') factor)*"""
        left = self.parse_factor()
        if left is None:
            return None
        while self.peek().type in (TokenType.STAR, TokenType.SLASH):
            op = self.advance()
            right = self.parse_factor()
            if right is None:
                # Восстановление: оператор без правого операнда
                self.errors.append(Error(
                    f"Missing right operand after '{op.value}'",
                    op.line, op.col
                ))
                break
            left = ('binop', op.value, left, right)
        return left
    
    def parse_factor(self):
        """factor → num | '(' expr ')'"""
        t = self.peek()
        if t.type == TokenType.NUM:
            return ('num', self.advance().value)
        elif t.type == TokenType.LPAREN:
            self.advance()
            expr = self.parse_expr()
            if not self.expect(TokenType.RPAREN):
                # Восстановление: продолжаем без ')'
                self.errors.append(Error(
                    "Missing closing ')'", t.line, t.col
                ))
            return expr
        else:
            self.errors.append(Error(
                f"Expected number or '(', got {t.value!r}",
                t.line, t.col
            ))
            return ('error',)
```

## Итоги

Обработка ошибок в компиляторах — баланс между несколькими целями:
- Найти как можно больше ошибок за один проход
- Не показывать ложные "каскадные" ошибки
- Давать точные, понятные и actionable сообщения
- Восстанавливаться быстро для IDE-интеграции

Эволюция шла от panic mode (1970-е) → error productions (1980-е) → smart heuristics (1990-е) → педагогические сообщения с suggestions (Clang, Rust, 2010-е) → LSP и инкрементальный парсинг для IDE (2016-настоящее).

## Литература

1. Aho, A. V., Lam, M. S., Sethi, R., & Ullman, J. D. (2006). *Compilers: Principles, Techniques, and Tools* (2nd ed.). Addison-Wesley. Раздел 4.8 — Error recovery.

2. Horspol, R. N., & Zosel, M. (1980). Practical methods for error recovery in operator-precedence parsers. *ACM SIGPLAN Notices*, 15(6). https://dl.acm.org/doi/10.1145/947977.947990

3. Clang Diagnostic Reference. https://clang.llvm.org/docs/DiagnosticsReference.html

4. Rust Compiler Error Index. https://doc.rust-lang.org/error_codes/error-index.html

5. Microsoft — Language Server Protocol Specification. https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/

6. Ohlsson, M., & Rydner, P. (1996). Error recovery in operator precedence parsers. *Software: Practice and Experience*, 26(11). https://onlinelibrary.wiley.com/doi/10.1002/(SICI)1097-024X(199611)26:11

7. Roslyn (C# compiler) design documentation. https://github.com/dotnet/roslyn/blob/main/docs/wiki/Roslyn-Overview.md

8. Tree-sitter — Error recovery documentation. https://tree-sitter.github.io/tree-sitter/

9. Aho, A. V., & Ullman, J. D. (1977). *Principles of Compiler Design*. Addison-Wesley. Глава 5 — Error handling.

10. Bison Manual — Error Recovery. https://www.gnu.org/software/bison/manual/html_node/Error-Recovery.html
