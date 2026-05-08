# Base64, percent-encoding: как пихать бинарь в текстовые протоколы

Интернет вырос из систем, которые работали только с ASCII. SMTP (электронная почта), HTTP, HTML, JSON — все они текстовые. Но реальные данные — изображения, файлы, бинарные протоколы — содержат произвольные байты. Как передать бинарные данные через текстовый канал? Ответ: закодировать их в подмножество ASCII. Base64 и percent-encoding — два наиболее распространённых способа сделать это.

## Исторический контекст: почему вообще нужен Base64

### Проблема SMTP

Первоначальный SMTP (Simple Mail Transfer Protocol) был разработан в 1982 году (RFC 821). Он работал только с 7-битными ASCII символами — исторически так устроились телефонные линии и ранние протоколы.

Когда люди захотели прикреплять файлы к письмам, возникла проблема: файл — это произвольные байты, SMTP — только 7-битный текст. Более того, некоторые управляющие символы (0x00, 0x0A, 0x0D, 0x2E в начале строки) имели специальное значение в SMTP.

Решение — MIME (Multipurpose Internet Mail Extensions, RFC 2045, 1996) с кодировкой Base64.

### Другие применения

Base64 сейчас используется везде, где нужно передать бинарные данные через текстовый канал:
- `data:` URI в HTML (встроенные изображения)
- JSON Web Tokens (JWT)
- HTTP Basic Authentication
- Встроенные изображения в CSS
- XML-подписи
- Публичные ключи в SSH/TLS сертификатах

## Алгоритм Base64

### Алфавит Base64

Base64 кодирует каждые **3 байта** (24 бита) в **4 символа** (каждый несёт 6 бит):

```
Алфавит Base64 (64 символа + padding):
Index | Char | Index | Char | Index | Char | Index | Char
  0   |  A   |  16   |  Q   |  32   |  g   |  48   |  w
  1   |  B   |  17   |  R   |  33   |  h   |  49   |  x
  2   |  C   |  18   |  S   |  34   |  i   |  50   |  y
  3   |  D   |  19   |  T   |  35   |  j   |  51   |  z
  4   |  E   |  20   |  U   |  36   |  k   |  52   |  0
  ...
 25   |  Z   |  51   |  z   |  62   |  +   |  63   |  /
 
Символы: A-Z (0-25), a-z (26-51), 0-9 (52-61), + (62), / (63)
Padding: = (для выравнивания)
```

### Как работает кодирование

```python
import base64

# Шаг за шагом покажем кодирование "Man"

text = "Man"
raw_bytes = text.encode('ascii')
print(f"Байты: {list(raw_bytes)} = {[bin(b) for b in raw_bytes]}")
# [77, 97, 110] = ['0b1001101', '0b1100001', '0b1101110']

# 3 байта = 24 бита, разбиваем на 4 группы по 6 бит:
# 01001101 01100001 01101110
# └──M──┘  └──a──┘  └──n──┘
# 
# Группируем по 6 бит:
# 010011 | 010110 | 000101 | 101110
#   19   |   22   |    5   |  46
#    T   |    W   |    F   |   u
# → "TWFu"

encoded = base64.b64encode(raw_bytes)
print(f"Base64: {encoded}")  # b'TWFu'
```

### Реализация Base64 с нуля

```python
BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

def base64_encode(data: bytes) -> str:
    """Кодирование Base64 вручную"""
    result = []
    
    # Обрабатываем по 3 байта
    for i in range(0, len(data), 3):
        chunk = data[i:i+3]
        
        # Преобразуем 3 байта в 24-битное целое
        if len(chunk) == 3:
            n = (chunk[0] << 16) | (chunk[1] << 8) | chunk[2]
            # Извлекаем 4 группы по 6 бит
            result.append(BASE64_CHARS[(n >> 18) & 0x3F])
            result.append(BASE64_CHARS[(n >> 12) & 0x3F])
            result.append(BASE64_CHARS[(n >> 6)  & 0x3F])
            result.append(BASE64_CHARS[ n        & 0x3F])
        elif len(chunk) == 2:
            # Остаток 2 байта → 3 символа + 1 padding
            n = (chunk[0] << 16) | (chunk[1] << 8)
            result.append(BASE64_CHARS[(n >> 18) & 0x3F])
            result.append(BASE64_CHARS[(n >> 12) & 0x3F])
            result.append(BASE64_CHARS[(n >> 6)  & 0x3F])
            result.append('=')
        elif len(chunk) == 1:
            # Остаток 1 байт → 2 символа + 2 padding
            n = chunk[0] << 16
            result.append(BASE64_CHARS[(n >> 18) & 0x3F])
            result.append(BASE64_CHARS[(n >> 12) & 0x3F])
            result.append('==')
    
    return ''.join(result)

def base64_decode(encoded: str) -> bytes:
    """Декодирование Base64"""
    # Создаём обратную таблицу
    DECODE_TABLE = {c: i for i, c in enumerate(BASE64_CHARS)}
    
    result = []
    # Убираем padding
    encoded = encoded.rstrip('=')
    
    for i in range(0, len(encoded), 4):
        chunk = encoded[i:i+4]
        
        # Каждый символ → 6 бит
        values = [DECODE_TABLE[c] for c in chunk if c in DECODE_TABLE]
        
        if len(values) >= 2:
            n = (values[0] << 18) | (values[1] << 12)
            if len(values) >= 3:
                n |= (values[2] << 6)
            if len(values) == 4:
                n |= values[3]
            
            result.append((n >> 16) & 0xFF)
            if len(values) >= 3:
                result.append((n >> 8) & 0xFF)
            if len(values) == 4:
                result.append(n & 0xFF)
    
    return bytes(result)

# Тест
data = b"Hello, World!"
encoded = base64_encode(data)
decoded = base64_decode(encoded)

print(f"Original: {data}")
print(f"Encoded:  {encoded}")
print(f"Decoded:  {decoded}")
assert data == decoded

import base64
print(f"stdlib:   {base64.b64encode(data).decode()}")
```

### Padding с символом `=`

Если длина данных не кратна 3, добавляются символы `=`:

```
Без padding:   "M"    → 1 байт  → "TQ=="  (2 полезных + 2 padding)
               "Ma"   → 2 байта → "TWE="  (3 полезных + 1 padding)
               "Man"  → 3 байта → "TWFu"  (4 полезных + 0 padding)

"=" обозначает отсутствующие байты. Максимум 2 символа padding.
```

### Эффективность Base64

Base64 увеличивает размер данных ровно на **33.3%**:
- 3 входных байта → 4 выходных символа
- Плюс перевод строки каждые 76 символов (в MIME Base64)

```python
import sys

original = b"x" * 1000
encoded = base64.b64encode(original)
print(f"Оригинал: {len(original)} байт")
print(f"Base64: {len(encoded)} байт")
print(f"Накладные расходы: {(len(encoded)/len(original) - 1)*100:.1f}%")
# Накладные расходы: 33.3%
```

## Base64URL: безопасный для URL вариант

Стандартный Base64 содержит символы `+` и `/`, которые имеют специальный смысл в URL. Base64URL заменяет их:

```
Base64:    + → Base64URL: -
Base64:    / → Base64URL: _
Base64URL обычно не добавляет padding (=)
```

```python
# Base64URL в Python
import base64

data = b"\xfb\xff\xfe"  # байты с 11111011 11111111 11111110
standard = base64.b64encode(data).decode()   # "+//+"
url_safe  = base64.urlsafe_b64encode(data).decode()  # "-__-"

print(f"Standard: {standard}")   # +//+
print(f"URL-safe: {url_safe}")   # -__-

# JWT использует Base64URL без padding
def jwt_base64url_decode(s):
    # Добавляем padding если нужно
    padding = 4 - len(s) % 4
    if padding != 4:
        s += '=' * padding
    return base64.urlsafe_b64decode(s)
```

### JWT (JSON Web Token)

JWT широко использует Base64URL:

```
JWT формат: header.payload.signature

header (Base64URL):
{"alg":"HS256","typ":"JWT"}
→ eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9

payload (Base64URL):
{"sub":"1234567890","name":"John Doe","iat":1516239022}
→ eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ

signature: HMACSHA256(header + "." + payload, secret)
→ SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c

Полный JWT:
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U
```

```python
import base64
import json
import hmac
import hashlib

def decode_jwt(token: str):
    """Декодирование JWT (без верификации подписи)"""
    parts = token.split('.')
    
    def decode_part(s):
        # Добавляем padding
        s += '=' * (4 - len(s) % 4)
        return json.loads(base64.urlsafe_b64decode(s))
    
    header = decode_part(parts[0])
    payload = decode_part(parts[1])
    return header, payload

# Пример
jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.xxx"
header, payload = decode_jwt(jwt)
print(f"Header: {header}")   # {'alg': 'HS256', 'typ': 'JWT'}
print(f"Payload: {payload}")  # {'sub': '1234'}
```

## Data URIs: встроенные изображения в HTML

```html
<!-- Традиционный подход: отдельный HTTP запрос -->
<img src="/images/logo.png">

<!-- Data URI: изображение встроено в HTML/CSS -->
<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
```

```python
import base64

# Встраивание изображения в HTML
with open('icon.png', 'rb') as f:
    img_data = f.read()

b64_data = base64.b64encode(img_data).decode('ascii')
data_uri = f"data:image/png;base64,{b64_data}"

html = f'<img src="{data_uri}">'
print(f"Data URI длина: {len(data_uri)} символов")
```

Использование Data URI уменьшает количество HTTP запросов, но увеличивает размер HTML/CSS на 33%.

## Percent-encoding (URL encoding)

### Проблема URL

URL (Uniform Resource Locator) содержит только ASCII символы с ограниченным набором. Специальные символы (пробел, `#`, `?`, `&`) имеют синтаксическое значение в URL. Не-ASCII символы (кириллица, китайский) вообще не допустимы в сырой форме.

**Percent-encoding** (также URL encoding) — механизм кодирования символов в URL.

### Какие символы кодируются

**Зарезервированные символы** (имеют специальный смысл в URL):
```
: / ? # [ ] @ ! $ & ' ( ) * + , ; =
```

**Незарезервированные символы** (не кодируются):
```
A-Z a-z 0-9 - _ . ~
```

**Всё остальное** должно быть закодировано.

### Алгоритм percent-encoding

Символ заменяется на `%XX`, где XX — шестнадцатеричный код байта в UTF-8.

```python
def percent_encode(text: str, safe: str = '') -> str:
    """
    Кодирует строку для использования в URL.
    safe: символы, которые не нужно кодировать.
    """
    UNRESERVED = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~')
    safe_chars = UNRESERVED | set(safe)
    
    result = []
    for char in text:
        if char in safe_chars:
            result.append(char)
        else:
            # Кодируем каждый байт UTF-8 отдельно
            for byte in char.encode('utf-8'):
                result.append(f'%{byte:02X}')
    
    return ''.join(result)

# Примеры
print(percent_encode("Hello, World!"))       # Hello%2C%20World%21
print(percent_encode("Привет мир"))          # %D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82%20%D0%BC%D0%B8%D1%80
print(percent_encode("price=100&tax=20"))    # price%3D100%26tax%3D20
print(percent_encode("a+b=c", safe='+/='))  # a+b=c (не трогаем +, /, =)

# Python стандартная библиотека:
from urllib.parse import quote, unquote, quote_plus, urlencode

print(quote("Hello, World!"))              # Hello%2C%20World%21
print(quote("/path/to/file"))              # %2Fpath%2Fto%2Ffile
print(quote("/path/to/file", safe='/'))    # /path/to/file (/ не трогаем)

# Декодирование
print(unquote("%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82"))  # Привет
```

### `%20` vs `+`: два стиля кодирования пробела

Исторически сложилось два стандарта:

**RFC 3986 (URI):** Пробел = `%20`
**application/x-www-form-urlencoded (HTML формы):** Пробел = `+`

```python
from urllib.parse import quote, quote_plus, urlencode

# RFC 3986 кодирование (для URL):
print(quote("hello world"))       # hello%20world

# HTML form encoding (для form данных):
print(quote_plus("hello world"))  # hello+world

# urlencode для query string:
params = {'name': 'John Doe', 'age': '30', 'city': 'New York'}
print(urlencode(params))
# name=John+Doe&age=30&city=New+York

# Декодирование
from urllib.parse import unquote, unquote_plus
print(unquote("hello%20world"))    # hello world
print(unquote_plus("hello+world")) # hello world
```

### Кодирование формы: практический пример

```python
from urllib.parse import urlencode, parse_qs, urlparse, urljoin

# Построение URL с параметрами
base_url = "https://api.example.com/search"
params = {
    'q': 'Python замыкания',  # кириллица!
    'lang': 'ru',
    'page': '1',
    'filter': 'type:article,date:2024'
}

full_url = f"{base_url}?{urlencode(params)}"
print(full_url)
# https://api.example.com/search?q=Python+%D0%B7%D0%B0%D0%BC%D1%8B%D0%BA%D0%B0%D0%BD%D0%B8%D1%8F&lang=ru&page=1&filter=type%3Aarticle%2Cdate%3A2024

# Парсинг URL
parsed = urlparse(full_url)
query_params = parse_qs(parsed.query)
print(query_params)
# {'q': ['Python замыкания'], 'lang': ['ru'], 'page': ['1'], ...}

# Правильное построение URL запроса API
import requests
# Правильно: requests сам кодирует params
response = requests.get(base_url, params=params)  # безопасно!
# Неправильно: ручная конкатенация строк
# НЕ ДЕЛАЙТЕ: base_url + "?q=" + user_input  (SQL injection аналог!)
```

## Punycode: интернационализированные доменные имена

Как кодировать кириллические или китайские доменные имена? Для этого существует **Punycode** (RFC 3492) и система **IDN** (Internationalized Domain Names).

```python
import encodings.idna

# Punycode: преобразует Unicode домен в ASCII
domain = "пример.рф"  # кириллический домен
ascii_domain = domain.encode('idna').decode('ascii')
print(ascii_domain)  # xn--e1afmapc.xn--p1acf

# Обратное преобразование
print(ascii_domain.encode('ascii').decode('idna'))  # пример.рф

# Структура Punycode:
# xn-- — ACE (ASCII Compatible Encoding) prefix
# e1afmapc — Punycode для "пример"
# xn--p1acf — Punycode для "рф"
```

Punycode используется для защиты: браузеры отображают `xn--` домены в IDN форме, что помогает обнаружить phishing с похожими символами.

## Итоги

Base64 и percent-encoding — адаптеры между бинарным миром и текстовыми протоколами:

| | Base64 | Percent-encoding |
|---|--------|-----------------|
| Применение | Бинарные данные в текстовых протоколах | Специальные символы в URL |
| Алфавит | A-Z, a-z, 0-9, +, / | Любые символы через %XX |
| Overhead | +33% размера | Переменный (ASCII: +0%, Кириллица: +2/3) |
| Стандарт | RFC 4648 | RFC 3986 |

**Главные правила практики:**
1. Всегда используйте стандартные библиотеки — `base64`, `urllib.parse`
2. Никогда не конкатенируйте user input в URL вручную — используйте `urlencode`
3. Для URL в HTML используйте `quote` (RFC 3986), для form data — `quote_plus`
4. JWT — это Base64URL (без padding, с `-` и `_`)

## Литература

1. RFC 4648 — The Base16, Base32, and Base64 Data Encodings. https://www.rfc-editor.org/rfc/rfc4648

2. RFC 2045 — MIME Part One: Format of Internet Message Bodies (Base64 в email). https://www.rfc-editor.org/rfc/rfc2045

3. RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax. https://www.rfc-editor.org/rfc/rfc3986

4. RFC 3492 — Punycode: A Bootstring encoding of Unicode for Internationalized Domain Names in Applications. https://www.rfc-editor.org/rfc/rfc3492

5. RFC 7519 — JSON Web Token (JWT). https://www.rfc-editor.org/rfc/rfc7519

6. W3C — HTML5 form urlencoded. https://html.spec.whatwg.org/multipage/form-elements.html

7. MDN Web Docs — Base64. https://developer.mozilla.org/en-US/docs/Glossary/Base64

8. MDN Web Docs — URL encoding. https://developer.mozilla.org/en-US/docs/Glossary/percent-encoding

9. Python `urllib.parse` documentation. https://docs.python.org/3/library/urllib.parse.html

10. Python `base64` documentation. https://docs.python.org/3/library/base64.html
