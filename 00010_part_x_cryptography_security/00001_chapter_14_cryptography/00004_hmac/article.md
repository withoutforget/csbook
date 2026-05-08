# HMAC — аутентификация сообщений

## Введение

Криптографические хеш-функции обеспечивают целостность данных: изменение любого бита меняет хеш. Но хеш сам по себе не защищает от злоумышленника, который может изменить данные и пересчитать хеш. Для защиты и целостности, и подлинности сообщения (то есть убедиться, что сообщение создал именно законный отправитель) нужен **MAC** — Message Authentication Code (код аутентификации сообщения).

**HMAC** (Hash-based Message Authentication Code) — это стандартный способ построения MAC на основе криптографической хеш-функции с использованием секретного ключа. HMAC применяется в JWT-токенах, TOTP/HOTP кодах двухфакторной аутентификации, API-подписях, подписях куки и сотнях других мест.

В этой статье мы разберём математическую конструкцию HMAC, поймём, почему наивная реализация небезопасна, рассмотрим практические применения и критический вопрос timing-safe сравнения.

---

## 1. MAC — код аутентификации сообщения

### Задача

Алиса и Боб разделяют секретный ключ `K`. Алиса отправляет Бобу сообщение `m`. Боб хочет убедиться, что:
1. Сообщение не было изменено (целостность)
2. Сообщение создала именно Алиса, а не посторонний (подлинность)

### Принцип работы MAC

```
Алиса: tag = MAC(K, m)
Алиса отправляет: (m, tag)

Боб: tag' = MAC(K, m)
Боб проверяет: tag' == tag (timing-safe!)
```

Злоумышленник без ключа `K` не может создать корректный tag для изменённого сообщения. Даже если он видит пары `(m, tag)` для многих сообщений, вычислить tag для нового сообщения без ключа должно быть вычислительно нереализуемо.

### MAC vs цифровая подпись

| Характеристика   | MAC              | Цифровая подпись |
|-----------------|-----------------|-----------------|
| Ключ            | Симметричный     | Асимметричный    |
| Неотрекаемость  | Нет              | Да               |
| Скорость        | Очень быстро     | Медленно         |
| Проверяет       | Любой с ключом   | Любой с pub ключом|
| Применение      | API, сессии      | Документы, TLS   |

---

## 2. Наивный подход и его уязвимость

### H(key || message) — length extension attack

Первый наивный вариант MAC: просто хешировать конкатенацию ключа и сообщения.

```python
import hashlib

def naive_mac_v1(key: bytes, message: bytes) -> str:
    """НЕБЕЗОПАСНО! Уязвимо к length extension attack"""
    return hashlib.sha256(key + message).hexdigest()
```

**Проблема — атака расширения длины (length extension attack):**

SHA-256 построен на конструкции Меркла-Дамгора. Зная `H(key || message)`, атакующий может вычислить `H(key || message || padding || extension)` для любого `extension`, не зная ключа.

```
Известно: tag = SHA256(key || "amount=100")
Атака: Вычислить SHA256(key || "amount=100" || padding || "&bonus=9999")
без знания key!
```

Это возможно потому, что хеш SHA-256 — это и есть внутреннее состояние функции после обработки `key || message || padding`. Атакующий просто «продолжает» вычисление с этого состояния.

### H(message || key) — тоже небезопасно

```python
def naive_mac_v2(key: bytes, message: bytes) -> str:
    """Тоже небезопасно! Уязвимо к collision attack"""
    return hashlib.sha256(message + key).hexdigest()
```

Если хеш-функция уязвима к коллизиям (SHA-1, MD5), то атакующий, нашедший `m₁` и `m₂` с `H(m₁) = H(m₂)`, получает `H(m₁ || key) = H(m₂ || key)` — одинаковые MAC для разных сообщений.

---

## 3. HMAC — правильная конструкция

### Формула HMAC

HMAC (RFC 2104, 1997) разработан Михаэлем Беллари (Mihir Bellare), Ран Канетти (Ran Canetti) и Хьюго Кравчик (Hugo Krawczyk):

```
HMAC(K, m) = H((K' XOR opad) || H((K' XOR ipad) || m))
```

Где:
- `H` — хеш-функция (SHA-256, SHA-512 и т.д.)
- `K'` — ключ, дополненный нулями до длины блока хеша (512 бит для SHA-256), или хешированный если длиннее
- `ipad` = байт 0x36, повторённый до длины блока
- `opad` = байт 0x5C, повторённый до длины блока

### Почему это работает

Двойной хеш с разными константами (ipad, opad):
1. **Внутренний хеш** `H(K' XOR ipad || m)` — смешивает ключ и сообщение
2. **Внешний хеш** `H(K' XOR opad || ...)` — применяет ключ снова к результату

Атака расширения длины невозможна: атакующий мог бы расширить внутренний хеш, но не знает его значения (оно спрятано под внешним хешем).

### Ручная реализация HMAC

```python
import hashlib
import hmac

def hmac_sha256_manual(key: bytes, message: bytes) -> bytes:
    """Ручная реализация HMAC-SHA256 (для понимания)"""
    block_size = 64  # 512 бит для SHA-256
    
    # Если ключ длиннее блока — хешируем его
    if len(key) > block_size:
        key = hashlib.sha256(key).digest()
    
    # Дополняем ключ до длины блока
    key = key.ljust(block_size, b'\x00')
    
    # Вычисляем opad и ipad маски
    ipad = bytes(b ^ 0x36 for b in key)
    opad = bytes(b ^ 0x5c for b in key)
    
    # Вычисляем HMAC
    inner = hashlib.sha256(ipad + message).digest()
    outer = hashlib.sha256(opad + inner).digest()
    
    return outer

# Проверка совпадения со стандартной библиотекой
key = b"super_secret_key"
message = b"Important message"

manual_result = hmac_sha256_manual(key, message)
stdlib_result = hmac.new(key, message, hashlib.sha256).digest()

print(f"Ручной HMAC: {manual_result.hex()}")
print(f"stdlib HMAC: {stdlib_result.hex()}")
print(f"Совпадают: {manual_result == stdlib_result}")
```

---

## 4. HMAC в Python (стандартная библиотека)

```python
import hmac
import hashlib
import os

# HMAC-SHA256
key = os.urandom(32)  # 256-битный ключ
message = b"Transfer $1000 to account 12345"

# Создание MAC
mac = hmac.new(key, message, hashlib.sha256).hexdigest()
print(f"HMAC-SHA256: {mac}")

# HMAC-SHA512 (более высокая безопасность)
mac_512 = hmac.new(key, message, hashlib.sha512).hexdigest()
print(f"HMAC-SHA512: {mac_512[:64]}...")

# Верификация — ОБЯЗАТЕЛЬНО используйте compare_digest!
def verify_mac(key: bytes, message: bytes, received_mac: str) -> bool:
    computed = hmac.new(key, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received_mac)  # Timing-safe!

print(f"Верификация: {verify_mac(key, message, mac)}")
print(f"Подмена сообщения: {verify_mac(key, b'Transfer $9999 to account 99999', mac)}")
```

---

## 5. Timing-safe сравнение

### Почему нельзя использовать ==

Обычное сравнение строк/байтов `a == b` или `tag1 == tag2` в большинстве языков прекращает проверку при первом несовпадающем байте. Это создаёт **timing side channel**:

```python
# Демонстрация (не реальные числа, но концепция)
correct_mac = "aabbccddeeff..."
# Запрос 1: "00bbccddeeff..." → несовпадение на байте 0 → быстрый возврат
# Запрос 2: "aabbccddeeff..." → все байты совпали → медленный возврат

# Измеряя время ответа, атакующий угадывает MAC байт за байтом
```

На практике атака требует тысяч измерений из-за сетевого джиттера, но в лабораторных условиях или при атаке на локальный API она реализуема.

### Constant-time сравнение

```python
import hmac
import secrets

# ПРАВИЛЬНО: timing-safe сравнение
def safe_compare(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)
    # Эквивалент: secrets.compare_digest(a, b) (Python 3.10+)

# hmac.compare_digest реализует XOR всех байт и возвращает True только если XOR == 0
# Время выполнения не зависит от позиции первого несовпадения

# НЕПРАВИЛЬНО:
def unsafe_compare(a: bytes, b: bytes) -> bool:
    return a == b  # Прекращает при первом несовпадении!

# Пример использования в web API
def validate_webhook_signature(
    secret: bytes,
    payload: bytes,
    received_signature: str
) -> bool:
    """Проверка подписи вебхука (например, GitHub Webhooks)"""
    expected = hmac.new(secret, payload, "sha256").hexdigest()
    received = received_signature.removeprefix("sha256=")
    
    # Timing-safe сравнение
    return hmac.compare_digest(expected, received)
```

---

## 6. TOTP и HOTP — коды двухфакторной аутентификации

HMAC лежит в основе одноразовых паролей (OTP), используемых в Google Authenticator, Authy и других 2FA приложениях.

### HOTP (HMAC-based OTP, RFC 4226)

```
HOTP(K, C) = Truncate(HMAC-SHA1(K, C))
```

- `K` — секретный ключ (разделяется между сервером и устройством)
- `C` — счётчик (инкрементируется при каждом использовании)
- `Truncate` — извлечение 6-8 цифр из 160-битного HMAC

```python
import hmac
import hashlib
import struct
import time

def hotp(secret: bytes, counter: int, digits: int = 6) -> str:
    """HOTP (RFC 4226)"""
    # HMAC-SHA1 над 8-байтовым счётчиком в big-endian
    counter_bytes = struct.pack(">Q", counter)  # 8 байт big-endian
    h = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    
    # Dynamic Truncation: берём последние 4 бита последнего байта как offset
    offset = h[-1] & 0x0F
    
    # Берём 4 байта начиная с offset, маскируем MSB
    code = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    
    # Берём digits цифр
    return str(code % (10 ** digits)).zfill(digits)

def totp(secret: bytes, digits: int = 6, period: int = 30) -> str:
    """TOTP (RFC 6238) — временной счётчик вместо инкрементного"""
    # Счётчик = Unix время / период (обычно 30 секунд)
    counter = int(time.time()) // period
    return hotp(secret, counter, digits)

# Пример
import base64
secret = base64.b32decode("JBSWY3DPEHPK3PXP")  # Типичный формат QR-кода 2FA
code = totp(secret)
print(f"Текущий TOTP: {code}")

# Проверка (server-side): проверяем текущий и соседние временные окна
def verify_totp(secret: bytes, user_code: str, window: int = 1) -> bool:
    """Верификация TOTP с окном tolerance"""
    counter = int(time.time()) // 30
    for delta in range(-window, window + 1):
        if hmac.compare_digest(totp(secret), user_code):
            return True
        # Следующий/предыдущий период
    return False
```

### TOTP vs HOTP

| Характеристика | HOTP                    | TOTP                      |
|---------------|-------------------------|---------------------------|
| Счётчик       | Инкрементный            | Unix время / 30 сек       |
| Синхронизация | Нужна (счётчик)         | По времени                |
| Срок действия | Бессрочный (до use)     | ~30 секунд                |
| Применение    | Аппаратные токены (YubiKey OTP) | Google Authenticator, SMS |

---

## 7. Применение HMAC в API

### Подпись API-запросов

```python
import hmac
import hashlib
import time
import json

class APIClient:
    """Клиент с HMAC-подписью запросов (AWS SigV4-подобный подход)"""
    
    def __init__(self, api_key: str, api_secret: bytes):
        self.api_key = api_key
        self.api_secret = api_secret
    
    def sign_request(self, method: str, path: str, body: dict) -> dict:
        """Создание подписанных заголовков"""
        timestamp = str(int(time.time()))
        body_json = json.dumps(body, sort_keys=True)
        
        # Создаём строку для подписи
        string_to_sign = f"{method}\n{path}\n{timestamp}\n{body_json}"
        
        # HMAC-SHA256
        signature = hmac.new(
            self.api_secret,
            string_to_sign.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "X-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": f"sha256={signature}",
            "Content-Type": "application/json"
        }

class APIServer:
    """Серверная проверка подписи"""
    
    def __init__(self, secrets: dict):
        self.secrets = secrets  # {api_key: secret}
    
    def verify_request(
        self, method: str, path: str, body: dict, headers: dict,
        max_age_seconds: int = 300
    ) -> bool:
        api_key = headers.get("X-API-Key")
        if api_key not in self.secrets:
            return False
        
        # Проверка временного окна (защита от replay attack)
        timestamp = int(headers.get("X-Timestamp", 0))
        if abs(time.time() - timestamp) > max_age_seconds:
            return False
        
        # Воссоздаём строку для подписи
        body_json = json.dumps(body, sort_keys=True)
        string_to_sign = f"{method}\n{path}\n{headers['X-Timestamp']}\n{body_json}"
        
        # Вычисляем ожидаемую подпись
        secret = self.secrets[api_key]
        expected_sig = hmac.new(
            secret, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        
        received_sig = headers["X-Signature"].removeprefix("sha256=")
        
        return hmac.compare_digest(expected_sig, received_sig)

# Демонстрация
secret = os.urandom(32)
client = APIClient("client_id_123", secret)
server = APIServer({"client_id_123": secret})

headers = client.sign_request("POST", "/api/transfer", {"amount": 100})
result = server.verify_request("POST", "/api/transfer", {"amount": 100}, headers)
print(f"Запрос подлинный: {result}")

# Атака: изменение суммы
headers_tampered = headers.copy()
result_tampered = server.verify_request("POST", "/api/transfer", {"amount": 9999}, headers_tampered)
print(f"Атака с изменением суммы: {result_tampered}")  # False
```

### HMAC для подписи сессионных куки

```python
import hmac
import hashlib
import json
import time
import os

class SecureCookie:
    """Защищённые куки с HMAC-подписью"""
    
    def __init__(self, secret_key: bytes):
        self.secret_key = secret_key
    
    def _sign(self, data: str) -> str:
        return hmac.new(
            self.secret_key, data.encode(), hashlib.sha256
        ).hexdigest()
    
    def create(self, payload: dict, max_age: int = 3600) -> str:
        """Создание подписанной куки"""
        payload["exp"] = int(time.time()) + max_age
        data = json.dumps(payload)
        import base64
        encoded = base64.urlsafe_b64encode(data.encode()).decode()
        signature = self._sign(encoded)
        return f"{encoded}.{signature}"
    
    def verify(self, cookie: str) -> dict | None:
        """Верификация куки"""
        try:
            encoded, signature = cookie.rsplit(".", 1)
        except ValueError:
            return None
        
        # Timing-safe верификация подписи
        expected_sig = self._sign(encoded)
        if not hmac.compare_digest(expected_sig, signature):
            return None
        
        # Декодирование
        import base64
        data = json.loads(base64.urlsafe_b64decode(encoded.encode()))
        
        # Проверка срока действия
        if time.time() > data.get("exp", 0):
            return None
        
        return data

# Использование
secret = os.urandom(32)
cookies = SecureCookie(secret)

cookie_value = cookies.create({"user_id": 42, "role": "admin"})
print(f"Куки: {cookie_value[:50]}...")

payload = cookies.verify(cookie_value)
print(f"Данные куки: {payload}")

# Попытка подделки
tampered = cookie_value.replace("admin", "superadmin")
print(f"Поддельные куки: {cookies.verify(tampered)}")  # None
```

---

## 8. CMAC, GMAC и другие MAC

### CMAC (Cipher-based MAC)

CMAC построен на блочном шифре (AES) вместо хеш-функции. Удобен в контекстах, где уже используется AES (аппаратное ускорение).

```python
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.ciphers import algorithms

key = os.urandom(16)  # AES-128
message = b"Authenticate this message"

# AES-CMAC
c = CMAC(algorithms.AES(key))
c.update(message)
mac = c.finalize()
print(f"AES-CMAC: {mac.hex()}")
```

### GMAC (Galois MAC)

GMAC — это AES-GCM без шифрования (только аутентификация). По сути, тег GCM для пустого plaintext с AAD.

### Poly1305

Используется в ChaCha20-Poly1305 как MAC. Однократный MAC (one-time MAC) — ключ должен быть уникальным для каждого сообщения (что обеспечивается автоматически при использовании ChaCha20-Poly1305).

### Сравнение MAC алгоритмов

| MAC       | Основа         | Скорость  | Применение                    |
|-----------|---------------|-----------|-------------------------------|
| HMAC-SHA256 | SHA-256     | Высокая   | JWT, TOTP, API подписи        |
| HMAC-SHA512 | SHA-512     | Высокая   | Высокая безопасность          |
| AES-CMAC  | AES           | Высокая   | IoT, карты, hardware          |
| Poly1305  | GF(2¹³⁰-5)  | Очень высокая | ChaCha20-Poly1305           |
| GMAC      | AES-GCM      | Высокая   | Network packets               |

---

## 9. JWT и HMAC

JWT (JSON Web Token) широко используют HMAC для подписи токенов:

```python
import base64
import json
import hmac
import hashlib

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + '=' * padding)

def create_jwt_hs256(payload: dict, secret: bytes) -> str:
    """Создание JWT с HMAC-SHA256 подписью"""
    header = {"alg": "HS256", "typ": "JWT"}
    
    header_b64 = b64url_encode(json.dumps(header).encode())
    payload_b64 = b64url_encode(json.dumps(payload).encode())
    
    signing_input = f"{header_b64}.{payload_b64}"
    
    signature = hmac.new(
        secret, signing_input.encode(), hashlib.sha256
    ).digest()
    signature_b64 = b64url_encode(signature)
    
    return f"{signing_input}.{signature_b64}"

def verify_jwt_hs256(token: str, secret: bytes) -> dict | None:
    """Верификация JWT"""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        return None
    
    signing_input = f"{header_b64}.{payload_b64}"
    
    expected_sig = hmac.new(
        secret, signing_input.encode(), hashlib.sha256
    ).digest()
    received_sig = b64url_decode(signature_b64)
    
    if not hmac.compare_digest(expected_sig, received_sig):
        return None
    
    return json.loads(b64url_decode(payload_b64))

# Пример
secret = b"super_secret_jwt_key_min_256_bits_!"
payload = {"sub": "user123", "role": "admin", "exp": int(time.time()) + 3600}

token = create_jwt_hs256(payload, secret)
print(f"JWT: {token[:50]}...")

verified = verify_jwt_hs256(token, secret)
print(f"Верифицированные данные: {verified}")
```

**Внимание:** JWT с алгоритмом `alg: none` — известная уязвимость. Всегда проверяйте алгоритм в заголовке и никогда не принимайте `alg=none`.

---

## Заключение

HMAC — это стандартный, хорошо изученный способ аутентификации сообщений с симметричным ключом. Ключевые выводы:

1. **Никогда не используйте `H(key || message)`** — уязвимо к length extension attack
2. **HMAC = H((key XOR opad) || H((key XOR ipad) || message))** — математически обоснованная конструкция
3. **Timing-safe сравнение обязательно:** `hmac.compare_digest()`, никогда `==`
4. **TOTP/HOTP** — приложения двухфакторной аутентификации базируются на HMAC
5. **Размер ключа:** минимум 256 бит (32 байта) для HMAC-SHA256
6. **Для JWT:** HMAC-SHA256 (HS256) подходит для монолитов; RSA/ECDSA (RS256/ES256) — если нужна публичная верификация

---

## Литература и источники

1. RFC 2104. (1997). *HMAC: Keyed-Hashing for Message Authentication*. IETF. https://www.rfc-editor.org/rfc/rfc2104
2. RFC 4226. (2005). *HOTP: An HMAC-Based One-Time Password Algorithm*. IETF. https://www.rfc-editor.org/rfc/rfc4226
3. RFC 6238. (2011). *TOTP: Time-Based One-Time Password Algorithm*. IETF. https://www.rfc-editor.org/rfc/rfc6238
4. Bellare, M., Canetti, R., Krawczyk, H. (1996). *Keying Hash Functions for Message Authentication*. CRYPTO 1996. https://cseweb.ucsd.edu/~mihir/papers/kmd5.pdf
5. NIST FIPS 198-1. (2008). *The Keyed-Hash Message Authentication Code (HMAC)*. https://csrc.nist.gov/publications/detail/fips/198/1/final
6. RFC 7519. (2015). *JSON Web Token (JWT)*. IETF. https://www.rfc-editor.org/rfc/rfc7519
7. Boneh, D. (2014). *Timing Attacks on Web Privacy*. https://crypto.stanford.edu/~dabo/papers/webtiming.pdf
8. Wikipedia: HMAC. https://en.wikipedia.org/wiki/HMAC
9. Python docs: hmac module. https://docs.python.org/3/library/hmac.html
