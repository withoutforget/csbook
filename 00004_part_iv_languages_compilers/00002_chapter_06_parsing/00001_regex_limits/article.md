# Регулярные выражения и их пределы: когда regex не справляется

Регулярные выражения — один из самых мощных инструментов в арсенале программиста. Они встроены во все современные языки, операционные системы и редакторы. Однако есть фундаментальная причина, по которой regex нельзя использовать для парсинга HTML, вложенных структур и многих других задач — это не просто сложно, это математически невозможно. Понимание этих ограничений спасает от огромного класса ошибок и уязвимостей.

## Теория формальных языков: иерархия Хомского

Чтобы понять пределы regex, нужно познакомиться с иерархией Хомского — классификацией формальных языков по их вычислительной мощности.

Ноам Хомский в 1956 году описал четыре уровня формальных языков:

| Тип | Название | Автомат | Примеры |
|-----|----------|---------|---------|
| Type-3 | Регулярные | Конечный автомат (DFA/NFA) | email-адреса, IP-адреса (без семантики), идентификаторы |
| Type-2 | Контекстно-свободные | Стековый автомат (PDA) | большинство ЯП, HTML, XML, арифметические выражения |
| Type-1 | Контекстно-зависимые | Линейно-ограниченный автомат | некоторые естественные языки |
| Type-0 | Рекурсивно-перечислимые | Машина Тьюринга | всё что можно вычислить |

**Регулярные языки (Type-3)** — самые ограниченные. Они распознаются конечными автоматами (finite automata), у которых фиксированное количество состояний и нет памяти кроме текущего состояния.

Ключевое ограничение: **конечный автомат не умеет считать**. Точнее, он умеет считать только до фиксированного предела (до числа состояний).

## Конечные автоматы: DFA и NFA

### Детерминированный конечный автомат (DFA)

DFA — это математическая модель с:
- Конечным множеством состояний Q
- Алфавитом Σ
- Функцией переходов δ: Q × Σ → Q
- Начальным состоянием q₀
- Множеством допускающих состояний F

Пример DFA для распознавания строк, начинающихся с "ab":

```
     a          b
→ [q0] ──> [q1] ──> [q2] ← принимающее
    │         │
    └── другой символ ──> [qerr]
```

DFA обрабатывает входную строку за один проход слева направо, в каждый момент находясь ровно в одном состоянии. Нет стека, нет памяти — только текущее состояние.

### Недетерминированный конечный автомат (NFA)

NFA допускает:
- Несколько переходов по одному символу
- ε-переходы (без чтения символа)
- Одновременное "нахождение" в нескольких состояниях

NFA и DFA эквивалентны по выразительности (теорема Рабина-Скотта). Но NFA может быть экспоненциально компактнее, чем эквивалентный DFA.

### Алгоритм Томпсона: от regex к NFA

Кен Томпсон в 1968 году опубликовал классическую статью, описывающую алгоритм построения NFA из регулярного выражения.

Основные правила:
- Символ `a` → NFA с двумя состояниями и переходом по `a`
- Конкатенация `AB` → соединить конечные NFA_A с начальными NFA_B
- Альтернатива `A|B` → добавить начальное состояние с ε-переходами в оба
- Повторение `A*` → добавить ε-петлю

```
Regex: (a|b)*c

NFA (упрощённо):
     ε        ε
q0 ──────> q1 ──────> q2
    ┌─────────────────────┐
    │  a                  │
    │ q1 ──> q3 ──> q4   │
    │   ε        ε        │
    │  b                  │
    │ q1 ──> q5 ──> q6   │
    └─────────────────────┘
    c
q_last ──> q_accept
```

### Алгоритм Томпсона для симуляции NFA

Ключевое преимущество алгоритма Томпсона — симуляция NFA за O(mn) где m — длина паттерна, n — длина входа. Это линейное время!

```python
# Псевдокод симуляции NFA по Томпсону
def match(nfa, text):
    # Начинаем с ε-closure начального состояния
    current_states = epsilon_closure({nfa.start})
    
    for char in text:
        # Для каждого текущего состояния — все переходы по char
        next_states = set()
        for state in current_states:
            next_states |= move(state, char)
        # Берём ε-closure
        current_states = epsilon_closure(next_states)
        
        if not current_states:
            return False
    
    # Принимаем, если хотя бы одно принимающее состояние достигнуто
    return bool(current_states & nfa.accept_states)
```

## Что регулярные выражения не могут сделать

### Почему нельзя парсить HTML/XML

Знаменитый ответ на StackOverflow от bobince 2009 года стал мемом, но за ним стоит математическая истина:

HTML с вложенными тегами — это **контекстно-свободный язык** (Type-2). Например, нужно проверить, что каждый открывающий тег `<div>` соответствует закрывающему `</div>`, и что вложенность корректна:

```html
<div>
    <p>текст <span>здесь</span></p>
    <div>вложенный</div>
</div>
```

Для распознавания такой структуры нужен **счётчик глубины вложенности** — а конечный автомат не умеет считать произвольные числа (только до фиксированного предела).

**Формальное доказательство (лемма о накачке):**

Предположим, что язык `{aⁿbⁿ | n ≥ 1}` (n букв 'a' и n букв 'b') регулярен. Тогда существует "накачивающая длина" p. Рассмотрим строку `aᵖbᵖ`. По лемме о накачке, её можно разбить на xyz где |xy| ≤ p, |y| ≥ 1, и для всех k ≥ 0 строка xyᵏz также должна быть в языке. Но если накачивать y (которое целиком состоит из 'a'), получим строку с разным числом 'a' и 'b' — противоречие!

Корреляция для HTML: вложенные теги требуют помнить, сколько открытых тегов ещё не закрыто — это аналог `aⁿbⁿ`.

### Примеры невозможного с regex

```python
import re

# 1. НЕЛЬЗЯ: сбалансированные скобки произвольной глубины
# re.match(r'\(+\)+', text) — неправильно: не проверяет вложенность
# Нет способа написать regex для ((((...)))) произвольной глубины

# 2. НЕЛЬЗЯ: правильный HTML/XML  
# <div><p></p></div> — нужен парсер

# 3. НЕЛЬЗЯ: палиндромы произвольной длины
# "abcba" — нет regex для произвольных палиндромов

# 4. НЕЛЬЗЯ: проверка что число пар скобок совпадает
text = "((a)(b(c)))"
# Regexp не может проверить, что все скобки закрыты

# ЧТО МОЖНО: паттерны с конечной структурой
ip_pattern = r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
```

## ReDoS: катастрофический backtracking

Это одна из самых опасных уязвимостей в веб-приложениях. ReDoS (Regular Expression Denial of Service) — атака, при которой специально составленная строка заставляет движок regex работать экспоненциальное время.

### Как работает backtracking в PCRE

В отличие от алгоритма Томпсона (NFA-симуляция за O(mn)), большинство современных движков (PCRE, Python re, JavaScript RegExp) реализуют **backtracking NFA**. Это позволяет использовать backreferences и lookahead, но открывает дверь для катастрофического поведения.

```python
import re
import time

# ОПАСНЫЙ паттерн: (a+)+ b
pattern = r'^(a+)+$'

# Короткие строки — быстро
re.match(pattern, 'aaa' + 'b')   # ~мгновенно

# Чуть длиннее без 'b' в конце — экспоненциальный взрыв!
start = time.time()
# re.match(pattern, 'a' * 25)  # займёт секунды или минуты!
# print(f"Took: {time.time() - start:.2f}s")
```

### Почему это экспоненциально

Паттерн `(a+)+$` на строке `aaaa...a` (без завершающего символа) вынуждает движок перебирать все возможные разбиения:

```
"aaaa" (4 буквы) — способы разбить (a+)+:
1. (aaaa)       — (a+)₁ = "aaaa"
2. (aaa)(a)     — (a+)₁ = "aaa", (a+)₂ = "a"  
3. (aa)(aa)     — (a+)₁ = "aa",  (a+)₂ = "aa"
4. (aa)(a)(a)   — и так далее
5. (a)(aaa)
6. (a)(aa)(a)
7. (a)(a)(aa)
8. (a)(a)(a)(a)

Количество разбиений для n символов = 2^(n-1)
```

### Реальные инциденты ReDoS

- **Cloudflare 2019**: простой из-за regex в WAF — следующий паттерн вызвал полный откат CPU:

  ```
  (?:(?:\"|'|\]|\}|\\|\d|(?:nan|infinity|true|false|null|undefined|symbol|math)|`|\-|\+)+[)]*;?((?:\s|-|~|!|{}|\|\||\+)*.*(?:.*=.*))
  ```
- **Stack Overflow 2016**: 34-минутный простой из-за ReDoS в markdown парсере

### Уязвимые паттерны

```python
# Уязвимые (catastrophic backtracking) паттерны:

# 1. Nested quantifiers (вложенные квантификаторы)
r'(a+)+'          # ReDoS!
r'(a*)*'          # ReDoS!
r'(a|aa)+'        # ReDoS!

# 2. Альтернативы с общим префиксом
r'(a|a)+b'        # DANGER
r'(\w|\w)+b'      # DANGER

# 3. Оверлаппинг альтернативы
r'(a+|b+)*c'      # ReDoS на строке aaaaaa...!
```

### Защита от ReDoS

```python
# 1. Использовать re2 — библиотека Google (O(n) гарантировано)
import re2  # pip install re2

# re2 использует NFA-симуляцию без backtracking
# НО: не поддерживает lookahead/lookbehind/backreferences

# 2. Ограничение длины входа
MAX_INPUT_LENGTH = 1000

def safe_match(pattern, text):
    if len(text) > MAX_INPUT_LENGTH:
        raise ValueError("Input too long")
    return re.match(pattern, text)

# 3. Использовать timeout (Python 3.11+)
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Regex timeout")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(1)  # 1 секунда
try:
    result = re.match(dangerous_pattern, text)
finally:
    signal.alarm(0)
```

## POSIX vs PCRE: разные семантики

Существуют два основных диалекта regex с разными подходами.

### POSIX Extended Regular Expressions (ERE)

```bash
# POSIX: используется в grep, sed, awk
echo "hello world" | grep -E '[a-z]+'
echo "test123" | grep -E '^[a-z]+[0-9]+$'
```

Особенности POSIX:
- **Leftmost-longest match**: при нескольких совпадениях выбирается самое левое и самое длинное
- Нет lookahead/lookbehind
- Нет backreferences в ERE (есть в BRE для `\1`)
- Строгая семантика — поведение предсказуемо

```bash
echo "aabab" | grep -oE 'a(a|b)+'
# POSIX выдаст: "aabab" (самое длинное совпадение)
```

### PCRE (Perl-Compatible Regular Expressions)

PCRE — значительно мощнее и используется в PHP, Python (модуль `re`), JavaScript, Ruby, большинстве современных инструментов.

```python
import re

# 1. Backreferences — ссылки на группы
re.match(r'(\w+)\s\1', 'hello hello')  # Match! \1 = "hello"

# 2. Non-greedy quantifiers
re.match(r'<.+?>', '<div><p>')  # '<div>' (не жадный)

# 3. Lookahead — утверждение (assertion) без захвата
re.findall(r'\w+(?=\s)', 'hello world')  # ['hello'] — слово перед пробелом

# 4. Lookbehind
re.findall(r'(?<=\$)\d+', '$100 and $200')  # ['100', '200']

# 5. Named groups
m = re.match(r'(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})', '2024-01-15')
print(m.group('year'))   # '2024'
print(m.group('month'))  # '01'

# 6. Non-capturing groups
re.match(r'(?:foo|bar)baz', 'foobaz')  # Match, группа не захватывается

# 7. Условные паттерны (advanced)
re.match(r'(a)?(?(1)b|c)', 'ab')  # если группа 1 совпала — ожидаем b, иначе c
```

## Lookahead и Lookbehind: выход за пределы регулярных языков?

Lookahead и lookbehind — это "assertions" (утверждения): они проверяют контекст, не захватывая символы. Математически это расширяет возможности regex за пределы Type-3.

### Positive lookahead `(?=...)`

```python
import re

# Найти слова, за которыми следует число
text = "price100 name title200 label"
re.findall(r'\w+(?=\d)', text)  # ['price', 'title']

# Валидация пароля (несколько lookahead):
# - минимум 8 символов
# - хотя бы одна цифра
# - хотя бы одна заглавная буква
password_re = r'^(?=.*\d)(?=.*[A-Z]).{8,}$'
re.match(password_re, 'Password1')  # Match
re.match(password_re, 'password1')  # No match (нет заглавной)
```

### Negative lookbehind `(?<!...)`

```python
# Найти "foo" не предшествующий "bar"
re.findall(r'(?<!bar)foo', 'barfoo foo')  # ['foo'] (второй)

# Реальный пример: числа, не являющиеся ценой
re.findall(r'(?<!\$)\b\d+\b', 'I have $100 and 200 items')  # ['200']
```

### Backreferences: настоящий выход за Type-3

```python
# Это уже НЕ регулярный язык!
# Повторяющиеся слова:
re.search(r'\b(\w+)\b.*\b\1\b', 'the cat sat on the mat')
# Нашёл "the" которое повторяется

# HTML теги (очень ограниченно!):
re.match(r'<(\w+)>.*</\1>', '<div>content</div>')  # Match!
# НО: это не парсит вложенность!
re.match(r'<(\w+)>.*</\1>', '<div><p></p></div>')  # Тоже Match — неправильно!
```

Backreferences позволяют выразить некоторые контекстно-зависимые языки, но делают matching потенциально NP-трудным.

## Практические паттерны и советы

### Email валидация

```python
# Реальная regex для email (RFC 5321 упрощённо)
# ПЛОХАЯ идея: пытаться охватить все случаи RFC
email_perfect = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"

# ХОРОШАЯ идея: простая проверка + подтверждение по email
email_simple = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'

# Лучшая практика: использовать специализированные библиотеки
# pip install email-validator
from email_validator import validate_email, EmailNotValidError
try:
    validate_email("user@example.com")
except EmailNotValidError as e:
    print(str(e))
```

### URL parsing

```python
# НЕ НАДО использовать regex для парсинга URL!
# Используйте urllib.parse

from urllib.parse import urlparse, urlunparse

url = "https://user:pass@example.com:8080/path?query=1#fragment"
parsed = urlparse(url)
print(parsed.scheme)    # https
print(parsed.netloc)    # user:pass@example.com:8080
print(parsed.path)      # /path
print(parsed.query)     # query=1
print(parsed.fragment)  # fragment
```

### Производительность regex в Python

```python
import re

# Компилируйте regex, если используете многократно
pattern = re.compile(r'\d+')  # один раз
for line in big_file:
    pattern.findall(line)      # быстро

# НЕ ТАК:
for line in big_file:
    re.findall(r'\d+', line)  # компилирует при каждом вызове
    # (на практике re кеширует последние паттерны, но явный compile лучше)

# Используйте re.VERBOSE для читаемости сложных паттернов
date_pattern = re.compile(r'''
    (?P<year>  \d{4} )  # год: 4 цифры
    -
    (?P<month> \d{2} )  # месяц: 2 цифры
    -
    (?P<day>   \d{2} )  # день: 2 цифры
''', re.VERBOSE)
```

### Примеры в JavaScript

```javascript
// JavaScript regex — PCRE-подобный
const email = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Named groups (ES2018+)
const dateRe = /(?<year>\d{4})-(?<month>\d{2})-(?<day>\d{2})/;
const match = '2024-01-15'.match(dateRe);
console.log(match.groups.year);  // '2024'

// Lookahead для валидации пароля
const strongPassword = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d]{8,}$/;
console.log(strongPassword.test('Password1'));  // true

// Replace с функцией — мощный инструмент
const result = 'hello world'.replace(/(\w+)/g, (match, p1) => p1.toUpperCase());
console.log(result);  // 'HELLO WORLD'

// Флаги
const multiline = /^start/m;  // ^ соответствует началу каждой строки
const dotall = /a.b/s;        // . соответствует \n тоже (ES2018)
const unicode = /\p{Script=Greek}/u;  // Unicode property escapes (ES2018)
```

## Когда использовать regex, а когда — нет

### Используйте regex

- Простые паттерны без вложенности: email, IP, даты, идентификаторы
- Поиск/замена в тексте
- Извлечение данных из строк с фиксированной структурой
- Валидация ввода (как первый фильтр, не единственный)
- Обработка логов
- Lexical analysis (токенизация)

### НЕ используйте regex

- Парсинг HTML/XML — используйте lxml, BeautifulSoup, html.parser
- Парсинг JSON — используйте json.loads
- Парсинг URL — используйте urllib.parse
- Парсинг CSV — используйте csv модуль
- Парсинг SQL — используйте специализированные парсеры
- Любые вложенные структуры неограниченной глубины

```python
# ПЛОХО: парсинг HTML regex
import re
# Никогда не делайте так!
html = '<div class="test"><p>Hello</p></div>'
title = re.search(r'<div[^>]*>(.*?)</div>', html, re.DOTALL)

# ХОРОШО: используйте BeautifulSoup
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'html.parser')
div = soup.find('div', class_='test')
print(div.find('p').text)  # 'Hello'
```

## Альтернативы: когда regex недостаточно

### Parser Combinators

```python
# pyparsing — DSL для описания грамматик
from pyparsing import Word, alphas, nums, Literal, ZeroOrMore

# Грамматика для простых арифметических выражений
integer = Word(nums)
plus = Literal('+')
expr = integer + ZeroOrMore(plus + integer)

result = expr.parseString("1+2+3")
print(result.asList())  # ['1', '+', '2', '+', '3']
```

### Грамматика PEG для вложенных структур

```
# Пример PEG грамматики для сбалансированных скобок
Expr   ← '(' Expr* ')'
       / [^()]+
       
# Это невозможно выразить регулярным выражением!
```

## Итоги

Регулярные выражения — мощный инструмент для распознавания **регулярных языков** (Type-3 в иерархии Хомского). Их ограничения фундаментальны:

1. **Не могут считать** произвольные вложенности (HTML, JSON, скобки)
2. **ReDoS** — опасная уязвимость при использовании backtracking-движков
3. **POSIX** и **PCRE** — разные семантики с разными trade-off
4. **Lookahead/lookbehind** расширяют возможности, но усложняют анализ сложности

Правило большого пальца: если паттерн выглядит как `(a+)+`, `(a|ab)*` или имеет вложенные квантификаторы над альтернативами — это потенциальный ReDoS.

## Литература

1. Thompson, K. (1968). Regular expression search algorithm. *Communications of the ACM*, 11(6), 419–422. https://dl.acm.org/doi/10.1145/363347.363387 — оригинальный алгоритм NFA-симуляции

2. Chomsky, N. (1956). Three models for the description of language. *IRE Transactions on Information Theory*, 2(3), 113–124. — иерархия формальных языков

3. Cox, R. (2007). Regular Expression Matching Can Be Simple And Fast. https://swtch.com/~rsc/regexp/regexp1.html — отличный анализ NFA vs backtracking

4. Friedl, J. E. F. (2006). *Mastering Regular Expressions* (3rd ed.). O'Reilly Media. — практическое руководство, включая backtracking

5. Hopcroft, J. E., Motwani, R., & Ullman, J. D. (2006). *Introduction to Automata Theory, Languages, and Computation* (3rd ed.). Addison-Wesley. Глава 3 — конечные автоматы и регулярные языки.

6. PCRE2 Documentation. https://www.pcre.org/current/doc/html/

7. Python `re` module documentation. https://docs.python.org/3/library/re.html

8. OWASP — ReDoS. https://owasp.org/www-community/attacks/ReDoS

9. Davis, J. C. et al. (2018). The Impact of Regular Expression Denial of Service (ReDoS) in Practice. *FSE 2018*. https://dl.acm.org/doi/10.1145/3236024.3236027

10. Sipser, M. (2012). *Introduction to the Theory of Computation* (3rd ed.). Cengage Learning. Главы 1-2 — теория конечных автоматов и регулярных языков.
