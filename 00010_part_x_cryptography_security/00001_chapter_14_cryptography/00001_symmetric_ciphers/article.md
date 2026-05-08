# Симметричные шифры: AES и ChaCha20

## Введение

Симметричная криптография — это фундамент защиты данных в современных системах. Один ключ используется и для шифрования, и для расшифровки: это делает алгоритмы быстрыми и практичными для защиты больших объёмов данных. Каждый раз, когда вы подключаетесь к сайту по HTTPS, читаете зашифрованный файл или отправляете сообщение в мессенджере — где-то в цепочке работает симметричный шифр.

В этой статье мы подробно рассмотрим два наиболее распространённых современных симметричных шифра: **AES** (Advanced Encryption Standard) и **ChaCha20**. Первый — блочный шифр с аппаратным ускорением, ставший промышленным стандартом; второй — поточный шифр, разработанный как быстрая и надёжная альтернатива на платформах без аппаратной поддержки AES. Мы также разберём режимы работы шифров, так как сам по себе блочный шифр — это лишь примитив, требующий правильного использования.

---

## 1. Блочные vs поточные шифры

Прежде чем погружаться в детали конкретных алгоритмов, необходимо понять принципиальное различие двух классов симметричных шифров.

### Блочный шифр

Блочный шифр работает с фиксированными порциями данных — **блоками**. AES, например, всегда шифрует ровно 128 бит (16 байт) за один раз. Если сообщение длиннее — его нужно разбить на блоки; если короче — дополнить (padding).

Ключевые характеристики:
- Фиксированный размер блока
- Детерминированность: одинаковый блок + одинаковый ключ = одинаковый шифротекст
- Требуют режима работы для реальных сценариев

### Поточный шифр

Поточный шифр генерирует псевдослучайный **ключевой поток** (keystream), который побайтово или побитово XOR-ится с открытым текстом. Шифрование и расшифровка — одна и та же операция.

Ключевые характеристики:
- Может работать с данными произвольной длины
- Шифрует ровно столько байт, сколько нужно
- Нет необходимости в padding
- Критически важно никогда не использовать один nonce дважды с одним ключом

```
Блочный шифр:
plaintext_block (128 бит) + key → ciphertext_block (128 бит)

Поточный шифр:
keystream = generate(key, nonce, counter)
ciphertext = plaintext XOR keystream
```

---

## 2. AES — Advanced Encryption Standard

### История и стандартизация

AES был выбран NIST (National Institute of Standards and Technology) в 2001 году по итогам открытого конкурса. Алгоритм под оригинальным названием **Rijndael** разработали бельгийские криптографы Йоан Даймен (Joan Daemen) и Винсент Рэймен (Vincent Rijmen). Он сменил устаревший DES (Data Encryption Standard, 1977), который стал уязвим к атакам перебором из-за слишком короткого ключа в 56 бит.

AES принят в качестве американского федерального стандарта (FIPS 197) и де-факто является мировым стандартом симметричного шифрования.

### Параметры AES

| Вариант    | Размер ключа | Число раундов |
|------------|-------------|---------------|
| AES-128    | 128 бит     | 10            |
| AES-192    | 192 бита    | 12            |
| AES-256    | 256 бит     | 14            |

Размер блока всегда фиксирован: **128 бит (16 байт)**.

### Структура AES: состояние и раунды

AES работает с 16-байтным блоком, представляя его как матрицу $4 \times 4$ байта, называемую **состоянием** (state):

```
state = [
  [b0,  b4,  b8,  b12],
  [b1,  b5,  b9,  b13],
  [b2,  b6,  b10, b14],
  [b3,  b7,  b11, b15]
]
```

Каждый раунд состоит из четырёх операций. Для AES-128 выполняется 10 раундов (последний не включает MixColumns).

#### SubBytes — нелинейная подстановка

Каждый байт заменяется по таблице замены **S-box** (Substitution Box). S-box AES — это не произвольная таблица, а математически обоснованная конструкция: для каждого байта вычисляется мультипликативный обратный элемент в поле $\mathrm{GF}(2^8)$, затем применяется аффинное преобразование.

S-box обеспечивает **нелинейность** (confusion) — без неё шифр был бы линейным и легко взламываемым.

```python
# Фрагмент S-box AES (первые 16 значений)
S_BOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5,
    0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    # ... (всего 256 значений)
]

def sub_bytes(state):
    return [[S_BOX[b] for b in row] for row in state]
```

#### ShiftRows — циклический сдвиг строк

Каждая строка матрицы состояния циклически сдвигается влево:
- Строка 0: без сдвига
- Строка 1: сдвиг на 1 байт
- Строка 2: сдвиг на 2 байта
- Строка 3: сдвиг на 3 байта

Это обеспечивает **диффузию** — смешивание байтов между столбцами.

```python
def shift_rows(state):
    return [
        state[0],                                      # строка 0: без сдвига
        state[1][1:] + state[1][:1],                  # строка 1: сдвиг 1
        state[2][2:] + state[2][:2],                  # строка 2: сдвиг 2
        state[3][3:] + state[3][:3],                  # строка 3: сдвиг 3
    ]
```

#### MixColumns — умножение в поле $\mathrm{GF}(2^8)$

Каждый столбец матрицы умножается на фиксированную матрицу в поле Галуа $\mathrm{GF}(2^8)$. Это максимизирует диффузию: каждый входной байт влияет на все 4 байта столбца.

Операция MixColumns пропускается в последнем раунде шифрования.

#### AddRoundKey — добавление раундового ключа

Состояние XOR-ится с 128-битным раундовым ключом, полученным из процедуры **расширения ключа** (key schedule). Для каждого раунда генерируется свой уникальный подключ.

```python
def add_round_key(state, round_key):
    return [[state[r][c] ^ round_key[r][c] for c in range(4)] for r in range(4)]
```

### AES на практике — Python с библиотекой cryptography

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

# Генерация ключа (256 бит = 32 байта)
key = os.urandom(32)

# Создание объекта шифра
aesgcm = AESGCM(key)

# Шифрование
nonce = os.urandom(12)  # 96-битный nonce для GCM
plaintext = b"Secret message: attack at dawn"
aad = b"authenticated but not encrypted"  # Additional Authenticated Data

ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
print(f"Шифротекст: {ciphertext.hex()}")
print(f"Длина: {len(ciphertext)} байт (plaintext + 16 байт тега)")

# Расшифровка
decrypted = aesgcm.decrypt(nonce, ciphertext, aad)
print(f"Расшифровано: {decrypted}")

# Попытка с неверным тегом аутентификации
try:
    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0xFF])
    aesgcm.decrypt(nonce, tampered, aad)
except Exception as e:
    print(f"Обнаружено изменение данных: {type(e).__name__}")
```

---

## 3. Режимы работы блочных шифров

Сам по себе блочный шифр шифрует один блок. Для реальных данных нужен **режим работы** (mode of operation).

### ECB — Electronic Codebook (почему это плохо)

Самый простой режим: каждый блок шифруется независимо одним и тем же ключом.

```
C₁ = E(K, P₁)
C₂ = E(K, P₂)
C₃ = E(K, P₃)
```

**Проблема:** одинаковые блоки открытого текста дают одинаковые блоки шифротекста. Это приводит к утечке информации о структуре данных. Классический пример — зашифрованный в ECB битмап: контуры изображения сохраняются в шифротексте.

ECB **никогда не следует использовать** для шифрования данных длиннее одного блока.

### CBC — Cipher Block Chaining

```
C₁ = E(K, P₁ XOR IV)
C₂ = E(K, P₂ XOR C₁)
C₃ = E(K, P₃ XOR C₂)
```

Каждый блок перед шифрованием XOR-ится с предыдущим шифрблоком. Первый блок XOR-ится с **IV** (Initialization Vector) — случайным значением.

**Требования к IV:** должен быть случайным и непредсказуемым (не обязательно секретным). IV передаётся вместе с шифротекстом.

**Недостатки CBC:**
- Последовательная обработка — нет параллелизма при шифровании
- Padding required (PKCS#7)
- Уязвимость к padding oracle атакам (POODLE, BEAST)
- Не обеспечивает аутентификацию

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import os

key = os.urandom(32)
iv = os.urandom(16)

# Шифрование в CBC
cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
encryptor = cipher.encryptor()

# PKCS7 padding
padder = padding.PKCS7(128).padder()
padded = padder.update(b"Hello, World!") + padder.finalize()

ciphertext = encryptor.update(padded) + encryptor.finalize()

# Расшифровка
decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
padded_plain = decryptor.update(ciphertext) + decryptor.finalize()

unpadder = padding.PKCS7(128).unpadder()
plaintext = unpadder.update(padded_plain) + unpadder.finalize()
print(plaintext)  # b"Hello, World!"
```

### CTR — Counter Mode

CTR превращает блочный шифр в поточный:

```
keystream_i = E(K, nonce || counter_i)
C_i = P_i XOR keystream_i
```

Шифруется не сам открытый текст, а счётчик с nonce. Полученный ключевой поток XOR-ится с открытым текстом.

**Преимущества CTR:**
- Полный параллелизм (независимые блоки)
- Нет необходимости в padding
- Произвольный доступ (можно расшифровать любой блок)
- Шифрование = расшифровка

**Недостаток:** как и в CBC, отсутствует аутентификация. Нужно добавлять MAC отдельно.

### GCM — Galois/Counter Mode (AEAD)

GCM = CTR + GHASH (полиномиальный хеш в поле $\mathrm{GF}(2^{128})$).

Это режим **AEAD** (Authenticated Encryption with Associated Data) — обеспечивает одновременно:
1. **Конфиденциальность** (через CTR-шифрование)
2. **Целостность и аутентичность** (через тег аутентификации)
3. **Аутентификацию дополнительных данных** (AAD — шифруются не, но аутентифицируются)

```
(ciphertext, tag) = AES-GCM(key, nonce, plaintext, aad)
```

**GCM — рекомендованный режим для большинства применений.**

| Режим | Конфиденциальность | Аутентификация | Параллелизм |
|-------|-------------------|----------------|-------------|
| ECB   | Слабая            | Нет            | Да          |
| CBC   | Да                | Нет            | Частично    |
| CTR   | Да                | Нет            | Да          |
| GCM   | Да                | Да (AEAD)      | Да          |
| CCM   | Да                | Да (AEAD)      | Нет         |

**Важно о nonce в GCM:** нельзя использовать один и тот же nonce дважды с одним ключом. При повторном использовании nonce в GCM атакующий может восстановить ключ аутентификации. Стандартный размер nonce — 96 бит (12 байт).

---

## 4. ChaCha20 — поточный шифр

### История и мотивация

ChaCha20 разработан Дэниелом Бернштейном (Daniel J. Bernstein) в 2008 году как улучшение более раннего шифра Salsa20. Основная мотивация создания ChaCha20:

1. **Скорость без аппаратного ускорения** — AES на некоторых платформах (старые ARM, IoT устройства) работает медленно без AES-NI инструкций
2. **Устойчивость к timing attacks** — операции ChaCha20 не зависят от секретных данных (нет таблиц подстановки)
3. **Простота реализации** — нет S-box, только ARX операции

### ARX операции

ChaCha20 основан исключительно на трёх простых операциях:
- **A**ddition (сложение по модулю $2^{32}$)
- **R**otation (циклический сдвиг битов)
- **X**OR (побитовое исключающее ИЛИ)

Эти операции выполняются за постоянное время на любой платформе — нет таблиц, нет ветвлений на основе секретных данных.

### Структура ChaCha20

ChaCha20 работает с **состоянием $4 \times 4$ матрицы 32-битных слов** (512 бит = 64 байта):

```
constant  constant  constant  constant   # "expand 32-byte k"
key[0]    key[1]    key[2]    key[3]
key[4]    key[5]    key[6]    key[7]
counter   nonce[0]  nonce[1]  nonce[2]
```

Ключ — 256 бит (8 слов по 32 бит), nonce — 96 бит (3 слова), counter — 32 бита.

**Quarter Round** — основная операция:

```python
def quarter_round(a, b, c, d):
    a = (a + b) & 0xFFFFFFFF; d ^= a; d = rotate_left(d, 16)
    c = (c + d) & 0xFFFFFFFF; b ^= c; b = rotate_left(b, 12)
    a = (a + b) & 0xFFFFFFFF; d ^= a; d = rotate_left(d, 8)
    c = (c + d) & 0xFFFFFFFF; b ^= c; b = rotate_left(b, 7)
    return a, b, c, d
```

Выполняется 20 раундов (10 пар column rounds + diagonal rounds), отсюда название «ChaCha**20**».

### ChaCha20 на практике (Python)

```python
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import os

# Генерация ключа (256 бит)
key = os.urandom(32)
nonce = os.urandom(12)  # 96 бит

chacha = ChaCha20Poly1305(key)

# Шифрование (ChaCha20 + Poly1305 = AEAD)
plaintext = b"Confidential data protected by ChaCha20-Poly1305"
aad = b"version=1"

ciphertext = chacha.encrypt(nonce, plaintext, aad)

# Расшифровка
decrypted = chacha.decrypt(nonce, ciphertext, aad)
assert decrypted == plaintext
print("Расшифровка успешна!")

# Для потоковых данных без AAD:
ciphertext2 = chacha.encrypt(nonce, plaintext, None)
```

### ChaCha20 vs AES: скорость

Сравнение производительности на типичных платформах:

| Платформа               | AES-256-GCM | ChaCha20-Poly1305 |
|-------------------------|------------|-------------------|
| x86-64 с AES-NI         | ~4 Гб/с    | ~1.5 Гб/с         |
| ARM без аппаратного AES | ~40 Мб/с   | ~300 Мб/с         |
| IoT (Cortex-M0)         | ~5 Мб/с    | ~25 Мб/с          |

На десктопных процессорах Intel/AMD с инструкцией AES-NI AES быстрее. На мобильных устройствах без аппаратной поддержки AES победа за ChaCha20.

**TLS 1.3** поддерживает оба алгоритма: браузер и сервер согласовывают, какой использовать, основываясь в том числе на наличии аппаратного ускорения.

---

## 5. Poly1305 — аутентификатор для ChaCha20

ChaCha20 сам по себе — поточный шифр без аутентификации. **Poly1305** — это MAC (Message Authentication Code), разработанный тем же Бернштейном.

Вместе они образуют **ChaCha20-Poly1305** — AEAD конструкцию, аналогичную AES-GCM.

- **ChaCha20** шифрует данные
- **Poly1305** аутентифицирует шифротекст и AAD

Poly1305 — это однократный MAC (one-time MAC): ключ для Poly1305 генерируется из первых 32 байт ключевого потока ChaCha20 с counter=0. Это означает, что ключ уникален для каждого nonce, и одноразовый ключ Poly1305 никогда не повторяется.

---

## 6. Сравнение AES и ChaCha20

| Характеристика       | AES-256-GCM           | ChaCha20-Poly1305     |
|---------------------|----------------------|----------------------|
| Тип шифра           | Блочный (CTR режим)  | Поточный             |
| Размер ключа        | 128/192/256 бит       | 256 бит              |
| Размер nonce        | 96 бит               | 96 бит               |
| Аутентификация      | GHASH                | Poly1305             |
| Скорость (с AES-NI) | Очень высокая        | Высокая              |
| Скорость (без AES-NI)| Низкая              | Очень высокая        |
| Timing attacks      | Риск (S-box)         | Безопасен (ARX)      |
| Стандартизация      | NIST FIPS 197        | RFC 8439             |
| Применение          | TLS, IPsec, диски    | TLS, QUIC, мобильные |

---

## 7. Практические рекомендации

### Что использовать

1. **Для шифрования данных на диске или в памяти** — AES-256-GCM (если есть AES-NI) или ChaCha20-Poly1305
2. **Для TLS/HTTPS** — оба алгоритма поддерживаются; браузер выбирает автоматически
3. **Для мобильных/IoT устройств** — ChaCha20-Poly1305
4. **Для совместимости (например, с HSM или FIPS-certified системами)** — AES-256-GCM

### Критические правила

```python
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

key = os.urandom(32)

# ПРАВИЛЬНО: уникальный nonce для каждого сообщения
def encrypt_message(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)  # Криптографически случайный nonce
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce, ciphertext  # Храним nonce вместе с шифротекстом

def decrypt_message(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)

nonce, ct = encrypt_message(key, b"Secret")
plain = decrypt_message(key, nonce, ct)

# НЕПРАВИЛЬНО: статический nonce
# НИКОГДА НЕ ДЕЛАЙТЕ ТАК:
# FIXED_NONCE = b'\x00' * 12
# ciphertext = aesgcm.encrypt(FIXED_NONCE, plaintext, None)
```

**Правило 1:** Nonce должен быть уникальным для каждого сообщения с данным ключом. В GCM повторное использование nonce катастрофично — атакующий может восстановить ключ аутентификации.

**Правило 2:** Всегда используйте AEAD-режим (GCM или ChaCha20-Poly1305). Шифрование без аутентификации открывает дверь для атак на целостность.

**Правило 3:** Никогда не реализуйте криптографические алгоритмы самостоятельно — используйте проверенные библиотеки (cryptography, libsodium, OpenSSL).

---

## 8. Примеры реальных применений

### Шифрование файла с AES-256-GCM

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
import os

def encrypt_file(password: str, input_path: str, output_path: str) -> None:
    """Шифрование файла паролем через AES-256-GCM"""
    # Генерация ключа из пароля через Scrypt KDF
    salt = os.urandom(16)
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    key = kdf.derive(password.encode())
    
    # Чтение файла
    with open(input_path, 'rb') as f:
        plaintext = f.read()
    
    # Шифрование
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    # Запись: salt(16) + nonce(12) + ciphertext
    with open(output_path, 'wb') as f:
        f.write(salt + nonce + ciphertext)

def decrypt_file(password: str, input_path: str, output_path: str) -> None:
    """Расшифровка файла"""
    with open(input_path, 'rb') as f:
        data = f.read()
    
    salt = data[:16]
    nonce = data[16:28]
    ciphertext = data[28:]
    
    # Восстановление ключа
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    key = kdf.derive(password.encode())
    
    # Расшифровка
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    
    with open(output_path, 'wb') as f:
        f.write(plaintext)

# Использование
encrypt_file("my_password_123", "secret.txt", "secret.txt.enc")
decrypt_file("my_password_123", "secret.txt.enc", "secret_decrypted.txt")
```

### Шифрование данных в API (ChaCha20-Poly1305)

```python
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import os
import json
import base64

class SecureStorage:
    """Пример безопасного хранилища чувствительных данных"""
    
    def __init__(self, master_key: bytes):
        assert len(master_key) == 32, "Ключ должен быть 256 бит"
        self.key = master_key
        self.cipher = ChaCha20Poly1305(master_key)
    
    def store(self, data: dict, context: str) -> dict:
        """Шифрует словарь с контекстом как AAD"""
        plaintext = json.dumps(data).encode()
        nonce = os.urandom(12)
        aad = context.encode()  # Контекст аутентифицируется, но не шифруется
        
        ciphertext = self.cipher.encrypt(nonce, plaintext, aad)
        
        return {
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "context": context
        }
    
    def retrieve(self, encrypted: dict) -> dict:
        """Расшифровывает и проверяет целостность"""
        nonce = base64.b64decode(encrypted["nonce"])
        ciphertext = base64.b64decode(encrypted["ciphertext"])
        aad = encrypted["context"].encode()
        
        plaintext = self.cipher.decrypt(nonce, ciphertext, aad)
        return json.loads(plaintext)

# Использование
key = os.urandom(32)
storage = SecureStorage(key)

user_data = {"user_id": 42, "credit_card": "4111111111111111"}
encrypted = storage.store(user_data, "user_payment_data")

# Успешное извлечение
data = storage.retrieve(encrypted)
print(data)

# Попытка подмены контекста
try:
    encrypted["context"] = "admin_override"
    storage.retrieve(encrypted)
except Exception:
    print("Атака отклонена: контекст не совпадает")
```

---

## Заключение

Симметричные шифры — это рабочие лошадки современной криптографии. AES-256-GCM и ChaCha20-Poly1305 — два главных выбора для практического применения:

- **AES-GCM** — стандарт де-факто, поддерживается аппаратно на современных x86 и ARM процессорах, обязателен для FIPS-совместимых систем
- **ChaCha20-Poly1305** — лучший выбор для платформ без AES-NI, более устойчив к реализационным ошибкам (timing attacks)

Оба алгоритма при правильном использовании обеспечивают надёжную защиту. Ключевые правила:

1. Всегда используйте AEAD (GCM или ChaCha20-Poly1305), а не голое шифрование
2. Генерируйте nonce криптографически случайно и никогда не повторяйте
3. Используйте проверенные библиотеки, не реализуйте алгоритмы самостоятельно
4. Размер ключа 256 бит — стандарт для большинства применений

---

## Литература и источники

1. Daemen, J., Rijmen, V. (2002). *The Design of Rijndael: AES — The Advanced Encryption Standard*. Springer. https://www.springer.com/gp/book/9783540425809
2. NIST FIPS 197. (2001). *Advanced Encryption Standard (AES)*. https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.197.pdf
3. Bernstein, D.J. (2008). *ChaCha, a variant of Salsa20*. https://cr.yp.to/chacha/chacha-20080128.pdf
4. RFC 8439. (2018). *ChaCha20 and Poly1305 for IETF Protocols*. IETF. https://www.rfc-editor.org/rfc/rfc8439
5. NIST SP 800-38D. (2007). *Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM)*. https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf
6. Aumasson, J.P. (2017). *Serious Cryptography: A Practical Introduction to Modern Encryption*. No Starch Press. https://nostarch.com/seriouscrypto
7. Cryptography (Python library). https://cryptography.io/en/latest/
8. Wikipedia: Advanced Encryption Standard. https://en.wikipedia.org/wiki/Advanced_Encryption_Standard
9. Wikipedia: ChaCha20-Poly1305. https://en.wikipedia.org/wiki/ChaCha20-Poly1305
