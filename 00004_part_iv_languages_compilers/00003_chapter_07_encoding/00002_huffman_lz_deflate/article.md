# Huffman, LZ77/LZ78, DEFLATE, Brotli, Zstd: как работают gzip и zip изнутри

Сжатие данных — это одна из самых практичных областей информатики. Файлы ZIP, GZIP, сжатые HTTP ответы, архивы — всё это использует алгоритмы, основанные на нескольких фундаментальных идеях. Понимание этих идей помогает выбирать правильный инструмент для конкретной задачи и понимать, почему текстовые файлы сжимаются в 5-10 раз, а JPEG-картинки — почти нет.

## Основы: энтропия и теория информации

Перед тем как рассматривать алгоритмы, нужно понять, зачем вообще сжатие работает. Ответ — в теории информации Клода Шеннона (1948).

**Энтропия** H — это мера "непредсказуемости" или "информационного содержания" источника:

```
H(X) = -Σ p(x) · log₂(p(x))
```

где p(x) — вероятность символа x. Единица — бит.

Аналогия: если монетка всегда выпадает орлом, нет смысла её бросать — информации ноль. Если она идеально честная — каждый бросок даёт ровно 1 бит информации.

```python
import math
from collections import Counter

def entropy(text):
    """Вычисляет энтропию текста в битах на символ"""
    n = len(text)
    counts = Counter(text)
    probs = [c/n for c in counts.values()]
    return -sum(p * math.log2(p) for p in probs)

# Примеры
text1 = "aaaaaaaaaa"      # 10 одинаковых букв
text2 = "abcdefghij"      # 10 разных букв
text3 = "hello world"     # реальный текст

print(f"Энтропия '{text1}': {entropy(text1):.2f} бит/символ")  # 0.00
print(f"Энтропия '{text2}': {entropy(text2):.2f} бит/символ")  # 3.32 (log2(10))
print(f"Энтропия '{text3}': {entropy(text3):.2f} бит/символ")  # ~3.18
```

Теорема Шеннона: невозможно сжать данные без потерь ниже их энтропии. Это **теоретический предел** сжатия.

Практический вывод: английский текст имеет энтропию около 1-1.5 бит/символ (с учётом контекста), хотя ASCII кодирует его 7-8 битами. Значит, хороший компрессор может сжать текст в 5-8 раз!

## Кодирование Хаффмана: оптимальные коды переменной длины

### Идея

Хаффман (1952): назначим частым символам короткие коды, редким — длинные. Простое, но гениальное.

В ASCII буква 'e' (самая частая в английском, ~13%) и 'z' (редкая, ~0.07%) кодируются одинаково — 8 битами. Расточительство!

### Построение дерева Хаффмана

Алгоритм жадный:

1. Подсчитать частоты всех символов
2. Создать листовые узлы для каждого символа с весом = частота
3. Повторять: взять два узла с наименьшим весом, создать родительский узел с весом = сумма
4. Пока не останется один узел (корень дерева)
5. Обходом слева (0) и справа (1) назначить коды

```python
import heapq
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

@dataclass(order=True)
class HuffNode:
    weight: int
    symbol: Optional[str] = field(default=None, compare=False)
    left: Optional['HuffNode'] = field(default=None, compare=False)
    right: Optional['HuffNode'] = field(default=None, compare=False)

def build_huffman_tree(text: str) -> HuffNode:
    """Строим дерево Хаффмана для текста"""
    counts = Counter(text)
    
    # Создаём кучу из листовых узлов
    heap = [HuffNode(weight=count, symbol=char) 
            for char, count in counts.items()]
    heapq.heapify(heap)
    
    # Строим дерево
    while len(heap) > 1:
        # Берём два минимальных
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        
        # Создаём родительский узел
        parent = HuffNode(
            weight=left.weight + right.weight,
            left=left,
            right=right
        )
        heapq.heappush(heap, parent)
    
    return heap[0]  # корень

def get_codes(node: HuffNode, prefix="", codes=None):
    """Обходом дерева получаем коды"""
    if codes is None:
        codes = {}
    
    if node.symbol is not None:
        # Листовой узел
        codes[node.symbol] = prefix or "0"  # одиночный символ
    else:
        if node.left:
            get_codes(node.left, prefix + "0", codes)
        if node.right:
            get_codes(node.right, prefix + "1", codes)
    
    return codes

# Пример
text = "hello huffman"
tree = build_huffman_tree(text)
codes = get_codes(tree)

print("Коды Хаффмана:")
for char, code in sorted(codes.items(), key=lambda x: len(x[1])):
    count = text.count(char)
    print(f"  '{char}' (×{count}): {code} ({len(code)} бит)")

# Вычислим эффективность
original_bits = len(text) * 8
compressed_bits = sum(text.count(c) * len(code) for c, code in codes.items())
print(f"\nОригинал: {original_bits} бит")
print(f"После Хаффмана: {compressed_bits} бит")
print(f"Коэффициент сжатия: {original_bits/compressed_bits:.2f}x")
```

### Пример дерева для "ABRACADABRA"

```
Частоты: A=5, B=2, R=2, C=1, D=1

Построение:
1. heap: [C(1), D(1), B(2), R(2), A(5)]
2. Берём C(1), D(1) → CD(2)
   heap: [B(2), R(2), CD(2), A(5)]
3. Берём B(2), R(2) → BR(4)
   heap: [CD(2), A(5), BR(4)]
4. Берём CD(2), BR(4) → CDBR(6)  
   heap: [A(5), CDBR(6)]
5. Берём A(5), CDBR(6) → root(11)

Дерево:
        root(11)
        /        \
      A(5)      CDBR(6)
               /       \
            CD(2)      BR(4)
            /  \       /  \
           C    D     B    R

Коды:
A  = 0          (1 бит, самая частая)
C  = 100        (3 бита)
D  = 101        (3 бита)
B  = 110        (3 бита)
R  = 111        (3 бита)

"ABRACADABRA" = 0 110 111 0 100 0 101 0 110 111 0
= 22 бита (vs 11*8=88 бит ASCII!)
```

### Канонический код Хаффмана

Стандартные форматы (zlib, PNG, gzip) используют "канонический" код Хаффмана — символы с одинаковой длиной кода упорядочены лексикографически. Это позволяет хранить только длины кодов, а не сами коды.

## LZ77: скользящее окно и обратные ссылки

Алгоритм Лемпеля-Зива 1977 года — основа большинства современных компрессоров.

### Идея

Текст часто повторяется. Вместо хранения повторяющейся подстроки — храним ссылку: "посмотри назад на X байт, возьми Y символов".

```
Входная строка:
"abracadabrabrabra"

Скользящее окно (буфер поиска) и lookahead буфер:

Позиция 0: 'a' → выход: literal 'a'
Позиция 1: 'b' → выход: literal 'b'
Позиция 2: 'r' → выход: literal 'r'
Позиция 3: 'a' → совпадение "a" на позиции 0 (offset=3, len=1)
                  или literal 'a' (зависит от min_match)
Позиция 4: 'c' → literal 'c'
Позиция 5: 'a' → совпадение с pos 0 (offset=5, len=1)
Позиция 6: 'd' → literal 'd'
Позиция 7: 'a' → совпадение с pos 0 (offset=7, len=1)
Позиция 8: 'b' → совпадение с pos 1 (offset=7, len=7) "bracadab"!
...
```

### Формат LZ77

Выходной поток LZ77 состоит из токенов трёх видов:
- Литерал: `(0, 0, symbol)` — буквальный символ
- Ссылка: `(offset, length, next_symbol)` — взять length символов, начиная с текущей позиции - offset

```python
def lz77_compress(data: str, window_size=255, lookahead_size=15):
    """Упрощённая реализация LZ77"""
    result = []
    pos = 0
    
    while pos < len(data):
        best_offset = 0
        best_length = 0
        
        # Ищем лучшее совпадение в окне
        search_start = max(0, pos - window_size)
        
        for offset in range(1, pos - search_start + 1):
            match_start = pos - offset
            length = 0
            
            while (length < lookahead_size and 
                   pos + length < len(data) and
                   data[match_start + length] == data[pos + length]):
                length += 1
            
            if length > best_length:
                best_length = length
                best_offset = offset
        
        next_char = data[pos + best_length] if pos + best_length < len(data) else ''
        result.append((best_offset, best_length, next_char))
        pos += best_length + 1
    
    return result

# Пример
text = "abracadabra"
compressed = lz77_compress(text)
print("LZ77 результат:")
for token in compressed:
    offset, length, char = token
    if length == 0:
        print(f"  literal: '{char}'")
    else:
        print(f"  ref: offset={offset}, len={length}, next='{char}'")
```

### Преимущество LZ77

LZ77 находит **произвольные** повторения в пределах окна. Это принципиально отличается от словарного подхода: не нужно заранее знать, что будет повторяться.

Размер окна (window_size) — ключевой параметр:
- gzip использует 32 КБ окно
- Большее окно → лучшее сжатие, больше памяти и CPU

## LZ78 и LZW: словарный подход

Алгоритм LZ78 (1978) строит словарь фраз на лету.

**LZW** (Welch, 1984) — улучшение LZ78, используемое в GIF и (ранее) TIFF.

```
LZW кодирование (упрощённо):
Начальный словарь: {'a':0, 'b':1, 'c':2, ...}

Вход: "abab"

1. Читаем 'a'. w='a', выводим 0
2. Читаем 'b'. w='ab'→ не в словаре! 
   - добавляем 'ab'→3 в словарь
   - выводим код 'a'=0
   - w = 'b'
3. Читаем 'a'. w='ba'→ не в словаре!
   - добавляем 'ba'→4 в словарь
   - выводим код 'b'=1
   - w = 'a'
4. Читаем 'b'. w='ab'→ ЕСТЬ в словаре! w='ab'
5. EOF: выводим код 'ab'=3

Выход: [0, 1, 3]  (вместо 4 символов — 3 кода)
```

Проблема LZW: патент Unisys вызвал отказ от GIF в 1990-х и создание PNG.

## DEFLATE = LZ77 + Хаффман

DEFLATE — алгоритм, используемый в gzip и ZIP. Это комбинация:

1. **LZ77** — находит повторения, создаёт поток литералов и back-references
2. **Хаффман** — кодирует поток LZ77 с минимальным числом бит

### Структура DEFLATE потока

```
DEFLATE stream состоит из блоков:
┌──────────────────┐
│ Block header     │  3 бита: тип блока и признак последнего
├──────────────────┤
│ Huffman trees    │  (для dynamic blocks) — описание кодов
├──────────────────┤
│ Compressed data  │  коды литералов (0-255) + ссылки (length, distance)
│                  │  + специальный код 256 = конец блока
└──────────────────┘
```

Типы блоков:
- **Type 0:** Несжатый — просто копирует данные (для случаев, когда сжатие не помогает)
- **Type 1:** Фиксированные коды Хаффмана (предопределённые)
- **Type 2:** Динамические коды Хаффмана (оптимальные для блока)

```python
import zlib

# zlib — реализация DEFLATE/zlib в Python
data = b"hello hello hello world " * 100

# DEFLATE (без заголовков zlib):
deflate = zlib.compress(data, level=9)  # level 1-9
print(f"Оригинал: {len(data)} байт")
print(f"После DEFLATE: {len(deflate)} байт")
print(f"Коэффициент: {len(data)/len(deflate):.1f}x")

# Декомпрессия
restored = zlib.decompress(deflate)
assert restored == data

# gzip — DEFLATE + gzip заголовок
import gzip
gzipped = gzip.compress(data)
print(f"После gzip: {len(gzipped)} байт")
```

### gzip и ZIP форматы

**gzip** (RFC 1952): DEFLATE данные + заголовок (имя файла, время изменения, OS) + CRC-32 контрольная сумма + размер оригинала. Сжимает **один** файл.

**ZIP** (PKZIP format): контейнер для нескольких файлов. Каждый файл сжимается DEFLATE отдельно. Поддерживает также Store (без сжатия), BZIP2, LZMA.

```python
import zipfile

# Создание ZIP архива
with zipfile.ZipFile('archive.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write('file1.txt')
    zf.write('file2.txt')
    zf.writestr('inline.txt', 'Контент прямо из строки')

# Просмотр содержимого
with zipfile.ZipFile('archive.zip', 'r') as zf:
    for info in zf.infolist():
        ratio = info.file_size / info.compress_size if info.compress_size > 0 else 0
        print(f"{info.filename}: {info.file_size}B → {info.compress_size}B ({ratio:.1f}x)")
```

## LZ4: скорость как приоритет

LZ4 (Yann Collet, 2011) — алгоритм, оптимизированный для **скорости**, а не максимального сжатия.

Принципы:
- Очень простой формат back-reference: offset и length
- Нет Хаффман-кодирования (только LZ)
- Оптимизирован для современных CPU с SIMD

```
LZ4 скорость:
- Компрессия: ~500 MB/s (vs ~100 MB/s у zlib уровень 6)
- Декомпрессия: ~3-5 GB/s (очень быстро!)

Сжатие: обычно хуже gzip на 20-30%
Применение: real-time сжатие, базы данных (InnoDB), network protocols
```

## Brotli: предобученный словарь

Brotli (Google, 2015) — алгоритм, оптимизированный для сжатия веб-контента.

**Ключевое отличие:** Brotli содержит **встроенный статический словарь** (~120 КБ) с типичными фрагментами HTML, JS, CSS, URI. Это позволяет ссылаться на строки из словаря даже при кодировании первых байт файла.

```
Встроенный словарь Brotli содержит:
- "content-type", "application/json", "text/html" — HTTP заголовки
- "function ", "return ", "var " — JavaScript ключевые слова
- "class=", "href=", "<div>" — HTML атрибуты

При кодировании "Content-Type: application/json":
LZ77/gzip: нет совпадений в окне → литералы (плохо)
Brotli: ссылка в статический словарь → 2-3 байта!
```

Результат: Brotli сжимает веб-контент на 20-30% лучше gzip при том же уровне.

```python
# Brotli в Python (pip install brotli)
import brotli

data = b"<html><body>Hello World</body></html>" * 100

br = brotli.compress(data)
gz = __import__('gzip').compress(data)

print(f"Оригинал: {len(data)} байт")
print(f"gzip: {len(gz)} байт ({len(data)/len(gz):.1f}x)")
print(f"brotli: {len(br)} байт ({len(data)/len(br):.1f}x)")
# brotli обычно лучше gzip

# HTTP сервер отправляет Content-Encoding: br
# curl -H "Accept-Encoding: br" https://example.com
```

Ограничение Brotli: компрессия **медленнее** gzip (особенно на высоких уровнях). Поэтому часто сжимают заранее и отдают готовый .br файл.

## Zstandard (Zstd): современный стандарт

Zstd (Facebook/Meta, 2016) — алгоритм нового поколения, предназначенный заменить gzip в большинстве случаев.

**Архитектура Zstd:**
- LZ (специализированный алгоритм) для нахождения повторений
- Finite State Entropy (FSE) — вместо Хаффмана (быстрее)
- Обучаемые словари (как Brotli, но настраиваемые под данные)

```
Уровни сжатия Zstd (1-22):
Уровень 1: ~300 MB/s компрессия, лучше чем gzip level 1
Уровень 3: баланс скорость/сжатие (умолчание)
Уровень 19: медленно, максимальное сжатие

Сравнение (на реальных данных):
           Compress  Decompress  Ratio
gzip -6:   ~25 MB/s  ~300 MB/s   2.9x
zstd -3:  ~350 MB/s  ~1200 MB/s  3.1x
brotli -4: ~40 MB/s  ~450 MB/s   3.3x
```

```python
# Zstd в Python (pip install zstandard)
import zstandard as zstd

data = b"Hello, World! " * 10000

# Обычное сжатие
cctx = zstd.ZstdCompressor(level=3)
compressed = cctx.compress(data)

dctx = zstd.ZstdDecompressor()
restored = dctx.decompress(compressed)

print(f"{len(data)} → {len(compressed)} bytes ({len(data)/len(compressed):.1f}x)")

# Обучение словаря на маленьких объектах (очень мощная функция!)
samples = [b"user_id:12345,name:Alice,role:admin"] * 100
samples += [b"user_id:67890,name:Bob,role:user"] * 100

dict_data = zstd.train_dictionary(1024, samples)

# Сжатие с обученным словарём:
cctx_dict = zstd.ZstdCompressor(level=3, dict_data=dict_data)
small_data = b"user_id:11111,name:Charlie,role:user"
compressed_dict = cctx_dict.compress(small_data)

# Без словаря маленькие объекты сжимаются плохо;
# со словарём — значительно лучше!
```

### Когда что выбирать

| Алгоритм | Скорость | Степень сжатия | Применение |
|----------|---------|---------------|-----------|
| LZ4 | Очень высокая | Низкая | Real-time, кэш, IPC |
| Snappy (Google) | Высокая | Средняя | BigTable, Hadoop |
| gzip/zlib | Средняя | Хорошая | HTTP, файлы, legacy |
| Brotli | Средняя (slow compress) | Отличная | Веб, статика |
| Zstd | Высокая | Отличная | Универсальное использование |
| LZMA/XZ | Медленная | Максимальная | Дистрибутивы ОС, архивы |
| BZIP2 | Медленная | Хорошая | Legacy Unix |

## Пример: ручное сжатие текста методом Хаффмана

Сожмём строку "MISSISSIPPI":

```python
text = "MISSISSIPPI"

# 1. Подсчёт частот
from collections import Counter
freqs = Counter(text)
print("Частоты:", dict(freqs))
# {'M': 1, 'I': 4, 'S': 4, 'P': 2}

# 2. Строим дерево
tree = build_huffman_tree(text)  # функция из начала статьи
codes = get_codes(tree)
print("Коды Хаффмана:", codes)
# Возможный результат: {'I': '0', 'S': '10', 'P': '110', 'M': '111'}

# 3. Кодируем
encoded = ''.join(codes[c] for c in text)
print(f"Закодировано: {encoded}")
print(f"Длина: {len(encoded)} бит (исходно {len(text)*8} бит)")

# MISSISSIPPI → 111 0 10 10 0 10 10 0 110 110 0
# = 25 бит (vs 88 бит в ASCII) = 3.5x сжатие!

# 4. Сохраняем дерево + данные
# (в реальных форматах дерево кодируется канонически)
```

## Итоги

Сжатие без потерь строится на двух фундаментальных идеях:

1. **Статистическое кодирование (Хаффман, ANS/FSE):** частые символы — короткие коды. Идеально для энтропийного сжатия после предварительной обработки.

2. **Словарное/LZ сжатие:** повторяющиеся подстроки заменяются ссылками. Работает хорошо для структурированных данных.

Большинство практических алгоритмов — **комбинация обоих** подходов:
- DEFLATE = LZ77 + Huffman
- Brotli = LZ + Huffman + статический словарь
- Zstd = LZ + FSE + обучаемый словарь

## Литература

1. Ziv, J., & Lempel, A. (1977). A universal algorithm for sequential data compression. *IEEE Transactions on Information Theory*, 23(3), 337–343. https://ieeexplore.ieee.org/document/1055714

2. Huffman, D. A. (1952). A method for the construction of minimum-redundancy codes. *Proceedings of the IRE*, 40(9), 1098–1101. https://ieeexplore.ieee.org/document/4051119

3. Deutsch, P. (1996). DEFLATE Compressed Data Format Specification. *RFC 1951*. https://www.rfc-editor.org/rfc/rfc1951

4. Shannon, C. E. (1948). A Mathematical Theory of Communication. *Bell System Technical Journal*, 27(3-4). https://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf

5. Collet, Y. (2022). Zstandard Compression. *RFC 8878*. https://www.rfc-editor.org/rfc/rfc8878

6. Alakuijala, J. et al. (2016). Brotli: A General-Purpose Data Compressor. https://github.com/google/brotli/blob/master/docs/brotli-format.md

7. Salomon, D. (2007). *Data Compression: The Complete Reference* (4th ed.). Springer.

8. Welch, T. A. (1984). A technique for high-performance data compression. *Computer*, 17(6), 8–19. https://ieeexplore.ieee.org/document/1659158

9. Collet, Y., & Kucherawy, M. (2018). Zstandard Compression and the application/zstd Media Type. *RFC 8478*. https://www.rfc-editor.org/rfc/rfc8478

10. Python `zlib` documentation. https://docs.python.org/3/library/zlib.html
