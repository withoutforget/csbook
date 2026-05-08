# CRC и контрольные суммы: быстрая проверка целостности

Когда файл копируется на жёсткий диск, передаётся по сети или записывается на CD — данные могут повреждаться. Битые сектора, помехи в канале связи, ошибки оперативной памяти — всё это реально. Контрольные суммы (checksums) — механизм быстрого обнаружения таких повреждений. CRC-32 встроен в Ethernet, ZIP, gzip, PNG. Понимание того, как работают эти механизмы, помогает выбрать правильный инструмент для задачи.

## Зачем нужны контрольные суммы

Суть проста: перед отправкой/хранением вычисляем некое число из данных (контрольная сумма). При получении/чтении — вычисляем снова и сравниваем. Не совпало — данные повреждены.

**Требования к хорошей контрольной сумме:**
1. Вычисляется быстро
2. Разные данные → разные суммы (низкая вероятность коллизий)
3. Маленькое изменение → другая сумма (чувствительность к изменениям)
4. Небольшой размер (обычно 4-8 байт)

## Простые схемы

### Простое суммирование

```python
def simple_checksum(data: bytes) -> int:
    """Сумма всех байт по модулю 256"""
    return sum(data) % 256

data = b"Hello, World!"
print(simple_checksum(data))  # 231

# Проблема: переставление байт не обнаруживается!
data2 = b"Hello, dlroW!"  # переставлены байты
print(simple_checksum(data2))  # тоже 231!
```

Простая сумма — плохая защита: не обнаруживает перестановку байт и "взаимокомпенсирующие" ошибки (один байт +1, другой -1).

### XOR checksum

```python
def xor_checksum(data: bytes) -> int:
    """XOR всех байт"""
    result = 0
    for byte in data:
        result ^= byte
    return result

# Проблема: если два одинаковых байта изменились — не обнаружим
# XOR нечувствителен к парным изменениям
```

### Adler-32

Adler-32 используется в zlib (внутри PNG). Быстрее CRC, но слабее для малых данных:

```python
def adler32(data: bytes) -> int:
    MOD_ADLER = 65521
    a, b = 1, 0
    for byte in data:
        a = (a + byte) % MOD_ADLER
        b = (b + a) % MOD_ADLER
    return (b << 16) | a

import zlib
print(hex(adler32(b"Hello")))      # 0x52b0073
print(hex(zlib.adler32(b"Hello"))) # то же самое

# Adler-32 слаб для коротких строк (e.g., все нулевые байты → 1)
# Но быстрый для больших данных
```

## CRC (Cyclic Redundancy Check): деление на полином

CRC — значительно более надёжный метод, основанный на арифметике полиномов в поле GF(2).

### Математическая основа

Данные интерпретируются как двоичный полином. CRC — это остаток от деления этого полинома на **образующий полином** (generator polynomial) в GF(2) — поле из двух элементов {0, 1}.

Арифметика GF(2):
- Сложение = XOR (0+0=0, 0+1=1, 1+1=0 — без переноса!)
- Умножение = AND
- Деления нет переноса и займа

```
Пример CRC-4 с образующим полиномом x⁴ + x + 1 = 10011₂

Данные: 10110011₂ (один байт)
Дополняем 4 нулями: 101100110000₂

Делим на 10011₂ в GF(2) (XOR вместо вычитания):
101100110000 ÷ 10011 = ?

101100110000
10011
-----------  XOR
 01111110000
  10011
  ---------
  01100110000
   10011
   --------
   01011010000
    10011
    -------
    01000010000
     10011
     ------
     00011110000
      10011
      -----
      00100100000
       10011
       ------
       000111...

CRC = остаток (последние 4 бита)
```

На практике CRC вычисляется через **таблицы** (lookup tables) — предвычисленные значения для каждого байта.

### CRC-32: стандарт де-факто

CRC-32 — 32-битная CRC с образующим полиномом:

```
x³² + x²⁶ + x²³ + x²² + x¹⁶ + x¹² + x¹¹ + x¹⁰ + x⁸ + x⁷ + x⁵ + x⁴ + x² + x + 1
= 0x04C11DB7 (прямое представление)
= 0xEDB88320 (обратное битовое — именно это используется в Ethernet/ZIP)
```

```python
import zlib

# CRC-32 в Python (использует zlib)
data = b"Hello, World!"
crc = zlib.crc32(data) & 0xFFFFFFFF
print(f"CRC-32: 0x{crc:08X}")  # 0xEC4AC3D0

# Инкрементальное вычисление (для потоков):
crc_state = 0
for chunk in [b"Hello", b", ", b"World!"]:
    crc_state = zlib.crc32(chunk, crc_state)
final_crc = crc_state & 0xFFFFFFFF
print(f"CRC-32 (incremental): 0x{final_crc:08X}")  # То же самое!

# Проверка целостности:
def verify_file(filename, expected_crc):
    crc = 0
    with open(filename, 'rb') as f:
        while chunk := f.read(65536):
            crc = zlib.crc32(chunk, crc)
    return (crc & 0xFFFFFFFF) == expected_crc
```

### Таблица для быстрого вычисления CRC-32

```python
def make_crc32_table():
    """Предвычисляем таблицу для быстрого CRC-32"""
    POLYNOMIAL = 0xEDB88320  # reversed poly
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ POLYNOMIAL
            else:
                crc >>= 1
        table.append(crc)
    return table

CRC_TABLE = make_crc32_table()

def crc32(data: bytes, crc: int = 0xFFFFFFFF) -> int:
    """CRC-32 через таблицу (быстро!)"""
    for byte in data:
        crc = (crc >> 8) ^ CRC_TABLE[(crc ^ byte) & 0xFF]
    return crc ^ 0xFFFFFFFF

print(f"CRC-32: 0x{crc32(b'Hello, World!'):08X}")
```

Табличный метод: один проход по данным, 256 операций lookup вместо битовых операций.

Современные CPU (x86 с SSE4.2) имеют аппаратную инструкцию `CRC32` — вычисление за единицы тактов на байт.

### Где используется CRC-32

- **Ethernet (IEEE 802.3):** Каждый кадр заканчивается 4-байтовым FCS (Frame Check Sequence) = CRC-32. Повреждённые кадры молча отбрасываются.
- **ZIP, gzip, zlib:** Проверка целостности после распаковки.
- **PNG:** CRC-32 каждого чанка.
- **SATA:** CRC-32 для проверки данных при передаче.
- **USB:** CRC-5 или CRC-16 для пакетов.

## Как проверяется TCP checksum

TCP использует не CRC, а более простую 16-битную checksum.

```
TCP checksum = однократное дополнение суммы 16-битных слов
(one's complement sum of all 16-bit words)
```

```python
def tcp_checksum(pseudo_header: bytes, tcp_segment: bytes) -> int:
    """
    Вычисляет TCP checksum.
    pseudo_header содержит src IP, dst IP, protocol, TCP length.
    """
    data = pseudo_header + tcp_segment
    
    # Дополнить до чётного числа байт
    if len(data) % 2:
        data += b'\x00'
    
    total = 0
    # Суммируем 16-битные слова
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i+1]
        total += word
    
    # Одиночное дополнение: свёртка переносов
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    
    # Инвертируем биты
    checksum = ~total & 0xFFFF
    return checksum

# Проверка: сумма сегмента с checksum должна дать 0xFFFF
```

TCP checksum — слабее CRC: плохо обнаруживает всплески ошибок. Поэтому защита данных в TCP/IP обеспечивается на уровне Ethernet (CRC-32) и/или уровня приложения.

## MD5 и SHA как checksums

MD5 и SHA-1/SHA-256 — криптографические хеш-функции, которые иногда используются как checksums для проверки целостности файлов. Важно понять: **это не одно и то же**.

```python
import hashlib

data = open('ubuntu.iso', 'rb').read()  # гипотетически

md5 = hashlib.md5(data).hexdigest()
sha256 = hashlib.sha256(data).hexdigest()

print(f"MD5:    {md5}")
print(f"SHA-256: {sha256}")

# Практичный способ:
def file_checksum(filepath, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

print(file_checksum('ubuntu.iso'))
```

### CRC vs MD5/SHA: когда что использовать

| | CRC-32 | MD5 | SHA-256 |
|---|-------|-----|---------|
| Скорость | Очень быстро | Быстро | Медленнее |
| Размер | 4 байта | 16 байт | 32 байта |
| Защита от случайных ошибок | Отлично | Отлично | Отлично |
| Защита от намеренной модификации | Нет! | Нет (MD5 сломан) | Да |
| Использование | Сети, архивы | Deprecated | Верификация загрузок, подписи |

**MD5 сломан для безопасности:** В 2004-2005 годах найдены коллизии (два разных файла с одинаковым MD5). MD5 нельзя использовать для криптографических целей.

```bash
# Примеры проверки загрузок в Unix
# Скачиваем файл и проверяем sha256:
sha256sum ubuntu-22.04-desktop-amd64.iso
# Сравниваем с опубликованным значением
```

## xxHash: сверхбыстрая некриптографическая хеш-функция

xxHash (Yann Collet, 2012) — специально разработан для максимальной скорости при хорошем качестве.

```python
# pip install xxhash
import xxhash

data = b"Hello, World!" * 10000

# xxHash64 — основная версия
h = xxhash.xxh64()
h.update(data)
print(f"xxHash64: {h.hexdigest()}")

# Сравнение скорости (приблизительно):
# CRC-32 (hardware): ~8 GB/s
# MD5:               ~700 MB/s
# SHA-256:           ~400 MB/s
# xxHash64:          ~35 GB/s (!)
# xxHash3 (AVX2):    ~100+ GB/s

# xxHash используется в:
# LZ4, Zstd, ClickHouse, RocksDB, etc.
```

## SipHash: защита от HashDoS

SipHash (2012, Bernstein & Aumasson) — "умная" хеш-функция: быстрая, но устойчивая к атакам на хеш-таблицы.

**Атака HashDoS:** Злоумышленник, зная алгоритм хеширования веб-сервера, отправляет HTTP запросы с параметрами, хеш-коллизии которых заполняют одну корзину хеш-таблицы → $O(n^2)$ вместо $O(n)$ → DoS.

SipHash использует **секретный ключ** — без знания ключа невозможно предсказать значения хеша и создать коллизии намеренно.

```python
# Python использует SipHash для хеширования строк
# (со случайным seed при каждом запуске!)
import os
import sys

print(hash("hello"))  # разный при каждом запуске Python!
# Это защита от HashDoS

# PYTHONHASHSEED=0 python -c "print(hash('hello'))"  # детерминированный хеш
```

## Многоуровневая защита целостности данных

На практике используется несколько слоёв:

```
Приложение (SHA-256) → если важна защита от подмены
         │
         ▼
zlib/gzip (Adler-32 или CRC-32) → если важна защита от повреждения
         │
         ▼
Сеть (TCP checksum) → базовая проверка
         │
         ▼
Ethernet (CRC-32) → обнаружение ошибок в кадре
         │
         ▼
Физический уровень (Forward Error Correction) → исправление ошибок
```

## Практический пример: проверка ZIP архива

```python
import zipfile
import zlib

def verify_zip(filename):
    """Полная проверка целостности ZIP архива"""
    errors = []
    
    with zipfile.ZipFile(filename, 'r') as zf:
        # zipfile.testzip() проверяет CRC-32 всех файлов
        bad_file = zf.testzip()
        if bad_file:
            errors.append(f"Bad file in archive: {bad_file}")
        else:
            print("ZIP integrity check: OK")
        
        # Детальная проверка
        for info in zf.infolist():
            with zf.open(info) as f:
                data = f.read()
            
            # Вычисляем CRC-32 вручную
            actual_crc = zlib.crc32(data) & 0xFFFFFFFF
            stored_crc = info.CRC
            
            if actual_crc != stored_crc:
                errors.append(
                    f"CRC mismatch for {info.filename}: "
                    f"expected 0x{stored_crc:08X}, got 0x{actual_crc:08X}"
                )
            else:
                print(f"  {info.filename}: OK (CRC=0x{actual_crc:08X})")
    
    return errors

# verify_zip("archive.zip")
```

## Итоги

Контрольные суммы — простой и быстрый механизм обнаружения ошибок:

1. **Простые суммы** — дёшево, но слабо
2. **CRC** — математически обоснованный метод; CRC-32 — стандарт де-факто для сетей и файловых форматов
3. **MD5/SHA** — используются для верификации загрузок, но SHA-2/3 предпочтительнее MD5
4. **xxHash** — максимальная скорость без криптографических гарантий
5. **SipHash** — для хеш-таблиц: защита от HashDoS

Главное различие: **CRC/xxHash** защищают от **случайных** повреждений, **криптографические хеши (SHA-256)** — от **намеренной** модификации.

## Литература

1. Peterson, W. W., & Brown, D. T. (1961). Cyclic codes for error detection. *Proceedings of the IRE*, 49(1), 228–235. https://ieeexplore.ieee.org/document/4065510

2. Koopman, P., & Chakravarty, T. (2004). Cyclic Redundancy Code (CRC) Polynomial Selection For Embedded Networks. *IEEE DSN 2004*. https://users.ece.cmu.edu/~koopman/roses/dsn04/koopman04_crc_poly_embedded.pdf

3. RFC 1951 — DEFLATE (CRC-32 в gzip). https://www.rfc-editor.org/rfc/rfc1951

4. IEEE 802.3 Ethernet Standard (CRC-32 в Ethernet). https://standards.ieee.org/

5. RFC 793 — Transmission Control Protocol (TCP checksum). https://www.rfc-editor.org/rfc/rfc793

6. Bernstein, D. J., & Aumasson, J.-P. (2012). SipHash: a fast short-input PRF. https://cr.yp.to/siphash/siphash-20120918.pdf

7. Collet, Y. (2012). xxHash — Extremely fast non-cryptographic hash algorithm. https://xxhash.com/

8. Python `zlib` documentation. https://docs.python.org/3/library/zlib.html

9. PNG Specification — CRC algorithm. https://www.w3.org/TR/PNG/#5CRC-algorithm

10. Rivest, R. (1992). The MD5 Message-Digest Algorithm. *RFC 1321*. https://www.rfc-editor.org/rfc/rfc1321
