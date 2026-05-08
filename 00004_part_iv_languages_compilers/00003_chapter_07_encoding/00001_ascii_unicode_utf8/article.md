# ASCII, Unicode, UTF-8/UTF-16: почему длина строки — это сложный вопрос

Казалось бы, что может быть проще строки? Это просто последовательность символов. Но за этой простотой скрывается богатый слой истории, математики и инженерных компромиссов. Разработчики регулярно сталкиваются с "сюрпризами": `len("é")` возвращает разные значения в зависимости от метода ввода, эмодзи занимают два "символа" в строке, а сортировка по-русски ведёт себя неожиданно. Всё это — следствие той самой сложности.

## История: как появился ASCII

В начале компьютерной эры каждый производитель придумывал свою кодировку символов. IBM использовала EBCDIC, другие — свои системы. Это создавало хаос при обмене данными.

В 1963 году американские организации по стандартизации разработали ASCII (American Standard Code for Information Interchange). Ключевые решения:

**7 бит, а не 8** — ASCII использует 7 бит, позволяя закодировать 128 символов (0-127). Восьмой бит изначально использовался как бит чётности (parity bit) для обнаружения ошибок при передаче по ненадёжным каналам. Позднее, когда надёжность каналов выросла, 8-й бит стал использоваться для расширений (extended ASCII, CP1252, etc.).

```
ASCII таблица (выборка):
Код | Символ | Описание
----|--------|----------
 32 |   ' '  | Пробел
 48 |   '0'  | Цифра 0
 65 |   'A'  | Заглавная A
 97 |   'a'  | Строчная a
 65 + 32 = 97 — XOR с 32 переключает регистр (элегантный факт!)
```

**Структура ASCII:**
- 0-31: Управляющие символы (LF, CR, TAB, NUL, BEL, etc.)
- 32-126: Печатные символы
- 127: DEL (Delete)

```python
# ASCII в Python
print(ord('A'))     # 65
print(chr(65))      # 'A'
print(ord('a'))     # 97
print(65 ^ 32)      # 97 — смена регистра через XOR!

# Проверка ASCII
'hello'.isascii()   # True
'héllo'.isascii()   # False
```

## Кодовые страницы и хаос многобайтовых кодировок

7-битный ASCII не охватывал ни кириллицу, ни китайские иероглифы. Решение было простым и привело к долгосрочному хаосу: 8-й бит отдавался под "национальные" символы.

Так появились кодовые страницы (code pages):
- **CP1252 (Windows Western)** — западноевропейские языки
- **CP1251 (Windows Cyrillic)** — кириллица (русский, украинский, болгарский)
- **KOI8-R** — кодировка советской разработки, ASCII + кириллица
- **ISO-8859-1 (Latin-1)** — стандарт ISO для западноевропейских
- **GB2312, Big5** — китайские иероглифы (многобайтовые!)

Проблемы кодовых страниц:
1. Один и тот же байт `0xE0` — это `à` в CP1252 и `а` (кириллица) в CP1251
2. Нельзя одновременно использовать кириллицу и греческий в одном документе
3. Японские, китайские языки требуют многобайтовых схем (ShiftJIS, GB2312)
4. Email "кракозябры" — классическая проблема несовпадения кодировок

```python
# Иллюстрация хаоса кодовых страниц
text = "Привет"
cp1251_bytes = text.encode('cp1251')
koi8_bytes = text.encode('koi8-r')

# Те же русские слова — разные байты!
print(cp1251_bytes)    # b'\xcf\xf0\xe8\xe2\xe5\xf2'
print(koi8_bytes)      # b'\xf0\xd2\xc9\xd7\xc5\xd4'

# Декодировать не той кодировкой — мусор
try:
    print(cp1251_bytes.decode('koi8-r'))  # "рТЙЧЕФ" — мусор!
except Exception:
    pass
```

## Unicode: одна кодировка для всех

Unicode решает проблему радикально: единая таблица для ВСЕХ символов всех языков мира. Версия 15.1 (2023) содержит 149 813 символов.

### Кодовые точки (Code Points)

Unicode работает с абстракцией **кодовой точки (code point)** — целым числом, однозначно идентифицирующим символ. Обозначаются как `U+XXXX` в шестнадцатеричном формате.

Примеры:
- `U+0041` = 'A' (Latin Capital Letter A)
- `U+043F` = 'п' (Cyrillic Small Letter Pe)
- `U+4E2D` = '中' (CJK Unified Ideograph)
- `U+1F600` = '😀' (Grinning Face)
- `U+200D` = Zero Width Joiner (невидимый!)

Диапазон: U+0000 до U+10FFFF — всего 1 114 112 возможных кодовых точек (из которых используются не все).

### Плоскости Unicode

Unicode разбит на **17 плоскостей** (planes), каждая по 65 536 кодовых точек:

| Плоскость | Диапазон | Название |
|-----------|---------|---------|
| 0 | U+0000–U+FFFF | Basic Multilingual Plane (BMP) |
| 1 | U+10000–U+1FFFF | Supplementary Multilingual Plane |
| 2 | U+20000–U+2FFFF | Supplementary Ideographic Plane |
| 14 | U+E0000–U+EFFFF | Supplementary Special-purpose Plane |
| 15-16 | U+F0000–U+10FFFF | Private Use Area |

BMP содержит почти все обычно используемые символы. За BMP — дополнительные символы: редкие иероглифы, музыкальные нотации, математические символы, и эмодзи.

## UTF-8: переменная длина, обратная совместимость

UTF-8 (Unicode Transformation Format, 8-bit) — самая популярная кодировка Unicode. Разработана Кеном Томпсоном и Робом Пайком в 1992 году.

### Схема кодирования

UTF-8 кодирует кодовую точку в 1-4 байта:

```
Диапазон кодовой точки | Байты | Битовый шаблон
U+0000 – U+007F        |   1   | 0xxxxxxx
U+0080 – U+07FF        |   2   | 110xxxxx 10xxxxxx
U+0800 – U+FFFF        |   3   | 1110xxxx 10xxxxxx 10xxxxxx
U+10000 – U+10FFFF     |   4   | 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx
```

**Ключевые свойства UTF-8:**
1. **Обратная совместимость с ASCII:** U+0000–U+007F кодируются ровно одним байтом — тем же, что в ASCII. Любой валидный ASCII текст — валидный UTF-8.
2. **Самосинхронизация:** Начало многобайтовой последовательности всегда начинается с `11xxxxxx`, продолжения — `10xxxxxx`. Можно войти в поток в произвольном месте и найти границу символа.
3. **Отсутствие нулевых байт** для не-NUL символов: C-строки (null-terminated) совместимы.

### Пример кодирования UTF-8

```python
# Закодируем символ 'п' (U+043F)
char = 'п'
print(hex(ord(char)))   # 0x43f

# U+043F = 0x43F = 0b 0100 0011 1111
# Попадает в диапазон U+0080 – U+07FF (2 байта):
# 110xxxxx 10xxxxxx
# Берём биты: 1 0000 | 11 1111
# Первый байт:  110 + 10000 = 11010000 = 0xD0
# Второй байт: 10  + 111111 = 10111111 = 0xBF

encoded = char.encode('utf-8')
print(encoded)          # b'\xd0\xbf'
print(list(encoded))    # [208, 191]

# Декодирование
print(bytes([0xD0, 0xBF]).decode('utf-8'))  # 'п'

# Ещё примеры
print('A'.encode('utf-8'))        # b'A'    (1 байт, ASCII)
print('é'.encode('utf-8'))        # b'\xc3\xa9' (2 байта)
print('中'.encode('utf-8'))       # b'\xe4\xb8\xad' (3 байта)
print('😀'.encode('utf-8'))       # b'\xf0\x9f\x98\x80' (4 байта)
```

### UTF-8 и самосинхронизация

```python
# Демонстрация самосинхронизации
data = "Привет, мир!".encode('utf-8')
print(data.hex())
# cfd180d0b8d0b2d0b5d1822c20d0bcd0b8d18021
# d0 bf — 'П' (U+041F) 
# d1 80 — 'р' (U+0440)
# ...

# Заходим с середины — можно найти начало следующего символа
pos = 3  # середина байт-последовательности
while (data[pos] & 0xC0) == 0x80:  # 10xxxxxx — это continuation byte
    pos += 1
print(data[pos:].decode('utf-8'))  # нашли начало следующего символа
```

## UTF-16: суррогатные пары

UTF-16 — другая кодировка Unicode, использующая 16-битные единицы (code units).

### Базовая структура

- Символы BMP (U+0000–U+FFFF): кодируются **одной** 16-битной единицей
- Символы за BMP (U+10000–U+10FFFF): кодируются **двумя** 16-битными единицами — **суррогатной парой**

### Суррогатные пары

Для кодирования символов за BMP выделен специальный диапазон кодовых точек:
- U+D800–U+DBFF — высокий суррогат (high surrogate, 1024 значения)
- U+DC00–U+DFFF — низкий суррогат (low surrogate, 1024 значения)

Вместе: $1024 \times 1024 = 1\,048\,576$ дополнительных символов.

```python
# UTF-16 в Python
char = '😀'  # U+1F600
print(hex(ord(char)))  # 0x1f600

# UTF-16 кодирование
utf16 = char.encode('utf-16-le')  # LE = little-endian
print(utf16.hex())     # 3dd800de (суррогатная пара!)
print(list(utf16))     # [0x3D, 0xD8, 0x00, 0xDE]

# Вычисление суррогатной пары вручную:
# U+1F600 = 0x1F600
# Subtract 0x10000: 0xF600
# High 10 bits: 0x03D → High surrogate: 0xD800 + 0x03D = 0xD83D
# Low 10 bits:  0x200 → Low surrogate:  0xDC00 + 0x200 = 0xDE00
# Немного другой символ, принцип тот же

# JavaScript использует UTF-16 для строк:
# "😀".length === 2  (два code units, не один символ!)
# "😀".codePointAt(0)  === 0x1F600  (правильно)
# "😀".charCodeAt(0)   === 0xD83D   (высокий суррогат)
# "😀".charCodeAt(1)   === 0xDE00   (низкий суррогат)
```

### Проблемы UTF-16

1. **BOM (Byte Order Mark):** Из-за двухбайтовых единиц нужно указывать порядок байт. UTF-16-LE (little-endian) или UTF-16-BE (big-endian). BOM (U+FEFF) в начале файла указывает порядок.

2. **Суррогаты разрывают "наивную" обработку:** Если считать `length` как число 16-битных единиц, символы за BMP считаются как два "символа".

3. **Нет совместимости с ASCII:** Символ 'A' в UTF-16 — это два байта `0x41 0x00` (LE), а не один.

UTF-16 используется в Java (char), JavaScript/TypeScript, Windows API (WCHAR), C# (string). Все эти системы "унаследовали" проблему суррогатных пар.

## BOM (Byte Order Mark)

BOM — символ U+FEFF в начале файла, используемый для определения порядка байт и кодировки.

```
UTF-8 BOM:    EF BB BF
UTF-16 LE:    FF FE
UTF-16 BE:    FE FF
UTF-32 LE:    FF FE 00 00
UTF-32 BE:    00 00 FE FF
```

BOM в UTF-8 технически не нужен (нет проблемы порядка байт), но Windows-инструменты часто добавляют его. Это иногда вызывает проблемы с инструментами, не ожидающими BOM.

```python
# Чтение файла с BOM
with open('file_with_bom.txt', encoding='utf-8-sig') as f:
    content = f.read()  # utf-8-sig автоматически убирает BOM

# Запись без BOM (правильно для Unix):
with open('file.txt', 'w', encoding='utf-8') as f:
    f.write(content)
```

## Нормализация Unicode: NFC, NFD, NFKC, NFKD

Один из самых неожиданных аспектов Unicode: один и тот же **визуально одинаковый** символ может быть представлен несколькими способами.

### Составные vs разложенные символы

Буква 'é' может быть представлена двумя способами:

1. **Precomposed (составной):** U+00E9 — один символ "e с акутом"
2. **Decomposed (разложенный):** U+0065 (e) + U+0301 (combining acute accent) — два кодовых точки

```python
import unicodedata

# Два визуально одинаковых способа записать 'é':
e_composed   = 'é'    # составной
e_decomposed = 'é'  # разложенный

print(e_composed == e_decomposed)  # False !
print(len(e_composed))             # 1
print(len(e_decomposed))           # 2

# Но визуально они одинаковы:
print(e_composed)    # é
print(e_decomposed)  # é
```

### Формы нормализации

Unicode определяет четыре формы нормализации:

**NFD (Canonical Decomposition):** Разложить все составные символы на базовые + combining marks.

**NFC (Canonical Decomposition + Canonical Composition):** Разложить, затем вновь сложить в составные символы там, где это возможно. Это самая компактная форма для большинства случаев.

**NFKD (Compatibility Decomposition):** Разложить также символы совместимости (например, ﬁ → fi, ² → 2).

**NFKC (Compatibility Decomposition + Canonical Composition):** NFKD + повторная сборка.

```python
import unicodedata

e_decomposed = 'é'  # e + combining acute

# Нормализация
nfc = unicodedata.normalize('NFC', e_decomposed)
nfd = unicodedata.normalize('NFD', 'é')

print(len(nfc))          # 1 (составной символ)
print(len(nfd))          # 2 (разложен)
print(nfc == 'é')   # True

# Сравнение строк должно использовать нормализацию:
def unicode_equal(a, b):
    return unicodedata.normalize('NFC', a) == unicodedata.normalize('NFC', b)

print(unicode_equal('é', 'é'))  # True

# NFKC — нормализация для поиска:
ff = 'ﬁ'  # лигатура fi (один символ!)
print(unicodedata.normalize('NFKC', ff))   # 'fi' (два символа)
print(unicodedata.normalize('NFKC', '²'))  # '2'
```

### Когда использовать какую нормализацию

- **NFC** — для хранения, передачи, большинства случаев. Компактно.
- **NFD** — для обработки символов (легче извлечь base character + diacritics).
- **NFKC** — для сравнения без учёта вариантов написания (поиск).
- **NFKD** — для лингвистического анализа.

## Графемные кластеры: что такое "один символ" для пользователя

Вот тут начинается настоящая сложность. **Графемный кластер** (grapheme cluster) — это то, что пользователь воспринимает как один символ. Он может состоять из нескольких кодовых точек!

### Combining marks

```python
# Один "символ" для пользователя:
# ā (a + macron) — буква в латышском языке
a_macron = 'ā'  # a + combining macron
print(a_macron)        # ā
print(len(a_macron))   # 2 (Python считает кодовые точки!)

# Буква с несколькими диакритиками:
# ȩ̌ = e + cedilla + caron (три кодовых точки!)
```

### Эмодзи и модификаторы

Эмодзи — яркий пример сложности графемных кластеров:

```python
# Один видимый эмодзи — несколько кодовых точек!

# 1. Простой эмодзи:
emoji = '😀'  # U+1F600
print(len(emoji))              # 1 кодовая точка

# 2. Семья: Man + ZWJ + Woman + ZWJ + Girl
family = '👨‍👩‍👧'
print(len(family))             # 8 кодовых точек!
# U+1F468 + U+200D + U+1F469 + U+200D + U+1F467

# 3. Эмодзи с модификатором цвета кожи:
wave_dark = '👋🏿'  # wave + dark skin tone modifier
print(len(wave_dark))          # 2 кодовых точки

# 4. Флаги — последовательности региональных индикаторов:
flag_ru = '🇷🇺'  # Regional Indicator R + Regional Indicator U
print(len(flag_ru))            # 2 кодовых точки

# Правильный подсчёт графемных кластеров требует библиотеки:
import grapheme  # pip install grapheme
print(grapheme.length('👨‍👩‍👧'))  # 1
print(grapheme.length('👋🏿'))   # 1
print(grapheme.length('🇷🇺'))   # 1
```

### Разбивка на графемные кластеры в разных языках

```python
# Python без библиотеки:
# len() считает кодовые точки, НЕ графемные кластеры!

# Правильная работа с графемами:
import grapheme

text = "Hello, 👋🏿 мир!"

# Подсчёт
print(len(text))                    # 17 (кодовые точки)
print(grapheme.length(text))        # 13 (графемные кластеры)

# Срез на графемные кластеры
print(grapheme.slice(text, 0, 7))   # "Hello, "
print(grapheme.slice(text, 7, 8))   # "👋🏿" (весь эмодзи!)
```

### JavaScript и Unicode

```javascript
// JavaScript: length = количество UTF-16 code units!
'é'.length           // 1 (BMP символ)
'😀'.length          // 2 (суррогатная пара = 2 code units!)
'👨‍👩‍👧'.length       // 8 (8 code units)

// Правильный итератор по символам Unicode (ES2015+):
[...'😀'].length      // 1 — итератор по кодовым точкам
[...'👨‍👩‍👧'].length  // 5 — по кодовым точкам, не графемам!

// Для графемных кластеров нужен Intl.Segmenter (ES2022):
const segmenter = new Intl.Segmenter();
const segments = [...segmenter.segment('👨‍👩‍👧')];
console.log(segments.length); // 1 — правильно!

// Реверс строки с Unicode (наивный подход ломается!):
const text = 'Hello, 😀!';
const naive_reverse = text.split('').reverse().join('');
// Ломает суррогатные пары: '!', 'corrupted emoji', ',', ...

// Правильный реверс:
const correct_reverse = [...text].reverse().join('');
// '!😀 ,olleH' — правильно для кодовых точек
// Но эмодзи с модификаторами всё равно сломаются!
```

## Практическое руководство

### Правила работы с Unicode в Python

```python
import unicodedata

# Правило 1: всегда работайте в Unicode, конвертируйте только на границах
# (файл/сеть/БД)

# Правило 2: нормализуйте при сравнении
def normalize_for_compare(s):
    return unicodedata.normalize('NFC', s)

# Правило 3: используйте casefold() для case-insensitive сравнения
print('Straße'.lower())     # 'straße'   — неполно
print('Straße'.casefold())  # 'strasse'  — правильно для German!
print('Ω'.casefold())       # 'ω'

# Правило 4: encode/decode явно с указанием кодировки
data = open('file.txt', encoding='utf-8', errors='replace').read()
# errors='strict' (default) — исключение
# errors='replace' — заменить ? 
# errors='ignore' — пропустить
# errors='backslashreplace' — показать как \xNN

# Правило 5: будьте осторожны с len()
text = 'café'  # может быть NFC или NFD!
print(len(unicodedata.normalize('NFC', text)))   # 4
print(len(unicodedata.normalize('NFD', text)))   # 5 (e + combining)

# Правило 6: используйте str.encode().decode() для round-trip check
def is_valid_utf8(data: bytes) -> bool:
    try:
        data.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False
```

### Полезные функции unicodedata

```python
import unicodedata

# Категория символа
print(unicodedata.category('A'))    # 'Lu' (Uppercase Letter)
print(unicodedata.category('a'))    # 'Ll' (Lowercase Letter)
print(unicodedata.category('5'))    # 'Nd' (Decimal Number)
print(unicodedata.category(' '))    # 'Zs' (Space Separator)
print(unicodedata.category('\n'))   # 'Cc' (Control)
print(unicodedata.category('😀'))   # 'So' (Other Symbol)

# Имя символа
print(unicodedata.name('A'))        # 'LATIN CAPITAL LETTER A'
print(unicodedata.name('😀'))       # 'GRINNING FACE'
print(unicodedata.name('‍'))   # 'ZERO WIDTH JOINER'

# Числовое значение
print(unicodedata.numeric('½'))     # 0.5
print(unicodedata.digit('5'))       # 5
```

## Итоги

Строки — не простые последовательности символов. Полная картина:

1. **ASCII (7 бит, 128 символов)** — фундамент, обратно совместим с UTF-8
2. **Кодовые страницы** — исторический хаос, уходит в прошлое
3. **Unicode** — единая таблица для всех символов (149 813+)
4. **UTF-8** — переменная длина 1-4 байта, обратно совместима с ASCII, стандарт для веба
5. **UTF-16** — 2 или 4 байта, используется в Java/JS/Windows, страдает от суррогатных пар
6. **Нормализация (NFC/NFD/NFKC/NFKD)** — один символ можно записать по-разному
7. **Графемные кластеры** — один "видимый символ" = несколько кодовых точек

Ответ на вопрос "какова длина строки" зависит от того, что именно измеряется: байты, кодовые единицы, кодовые точки, или графемные кластеры.

## Литература

1. Unicode Consortium. *The Unicode Standard, Version 15.1.0*. https://www.unicode.org/versions/Unicode15.1.0/ — основная спецификация

2. Unicode Technical Report #15 — Unicode Normalization Forms. https://www.unicode.org/reports/tr15/

3. Unicode Technical Standard #29 — Unicode Text Segmentation (Grapheme Clusters). https://www.unicode.org/reports/tr29/

4. UTF-8 and Unicode — The Secret Relationship. https://web.archive.org/web/20090204091524/http://www.cl.cam.ac.uk/~mgk25/unicode.html

5. Pike, R., & Thompson, K. (1993). Hello World or Καλημέρα κόσμε or こんにちは 世界 — Plan 9 and UTF-8. *Proceedings of the Winter 1993 USENIX Conference*. https://www.cl.cam.ac.uk/~mgk25/ucs/utf-8-history.txt

6. RFC 3629 — UTF-8, a transformation format of ISO 10646. https://tools.ietf.org/html/rfc3629

7. Python `unicodedata` module documentation. https://docs.python.org/3/library/unicodedata.html

8. Spolsky, J. (2003). The Absolute Minimum Every Software Developer Absolutely, Positively Must Know About Unicode and Character Sets (No Excuses!). https://www.joelonsoftware.com/2003/10/08/the-absolute-minimum/

9. ECMAScript 2022 — Intl.Segmenter. https://tc39.es/ecma402/#intl-segmenter-objects

10. Muller, E. (2020). Unicode Demystified: A Practical Programmer's Guide to the Encoding Standard. Addison-Wesley.
