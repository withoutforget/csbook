# Цифровые подписи: RSA-PSS, ECDSA, Ed25519

## Введение

Цифровая подпись решает две задачи одновременно: она доказывает, что документ создал конкретный человек (аутентичность), и что содержимое не было изменено после подписи (целостность). В отличие от MAC, цифровые подписи используют асимметричную криптографию: подписывает тот, кто владеет закрытым ключом, а проверить может любой, у кого есть открытый ключ.

Цифровые подписи лежат в основе PKI и TLS-сертификатов, подписей кода, Git-коммитов, PDF-документов, JWT-токенов и криптовалют. В этой статье мы разберём три основных алгоритма: **RSA-PSS**, **ECDSA** и **Ed25519**, рассмотрим их математику, практические примеры и критические аспекты безопасности.

---

## 1. Принципы цифровой подписи

### Концепция

```
Подписание:
  signature = Sign(private_key, hash(message))

Верификация:
  valid = Verify(public_key, signature, hash(message))
```

Схема:
1. **Хеширование:** вычисляется хеш сообщения (SHA-256, SHA-3)
2. **Подписание:** хеш обрабатывается закрытым ключом
3. **Передача:** отправляется (message, signature)
4. **Верификация:** получатель хеширует message и проверяет подпись открытым ключом

### Свойства цифровой подписи

| Свойство          | Описание                                           |
|-------------------|----------------------------------------------------|
| Аутентичность     | Только владелец закрытого ключа мог создать подпись|
| Целостность       | Любое изменение документа инвалидирует подпись     |
| Неотрекаемость    | Подписавший не может отрицать факт подписания      |
| Верифицируемость  | Любой с открытым ключом может проверить            |

### Разница с MAC

MAC обеспечивает только аутентичность и целостность, но не неотрекаемость: любой обладатель симметричного ключа мог создать MAC. В цифровой подписи только владелец закрытого ключа мог создать подпись, а проверить может любой.

---

## 2. RSA-PSS

### RSA-PKCS1 v1.5 (устаревший)

Исторически RSA подписи использовали схему PKCS#1 v1.5: перед RSA операцией хеш дополняется padding PKCS1.5.

**Проблема:** PKCS1 v1.5 доказательно не является безопасной схемой подписи в рамках стандартных криптографических моделей. Существуют теоретические атаки (Bleichenbacher, атака на конкретные реализации Manger).

### RSA-PSS

**PSS** (Probabilistic Signature Scheme) — современный, доказательно безопасный padding для RSA подписей:

1. Хешируется сообщение: `mHash = H(m)`
2. Генерируется случайная соль (salt)
3. Из `mHash + salt` создаётся маска через MGF (Mask Generation Function)
4. Образуется блок encoding, который подписывается RSA

Рандомизация (соль) делает PSS доказательно безопасным в random oracle model.

```python
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

# Генерация ключей RSA-2048
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)
public_key = private_key.public_key()

# Документ для подписи
document = b"""
ДОГОВОР № 2024-001
Сторона А: ООО «Альфа»
Сторона Б: ООО «Бета»
Сумма: 1 000 000 руб.
"""

# Подписание с RSA-PSS
signature = private_key.sign(
    document,
    padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.MAX_LENGTH  # Максимальная длина соли
    ),
    hashes.SHA256()
)

print(f"Размер подписи RSA-2048: {len(signature)} байт")  # 256 байт

# Верификация
try:
    public_key.verify(
        signature,
        document,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    print("Подпись верна!")
except Exception as e:
    print(f"Подпись недействительна: {e}")

# Проверка изменённого документа
tampered = document + b"\n(изменено после подписи)"
try:
    public_key.verify(signature, tampered,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
except Exception:
    print("Изменение документа обнаружено!")
```

### Сериализация ключей

```python
# Сохранение закрытого ключа (PEM формат)
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.BestAvailableEncryption(b"password123")
)

# Сохранение открытого ключа
public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

print(public_pem.decode())
# -----BEGIN PUBLIC KEY-----
# MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
# -----END PUBLIC KEY-----
```

---

## 3. ECDSA — подписи на эллиптических кривых

### Математика ECDSA

ECDSA (Elliptic Curve Digital Signature Algorithm) использует пару ключей на эллиптической кривой:

**Параметры:** кривая E, базовая точка G, порядок группы n

**Подписание:**
1. Хешируем сообщение: `z = hash(m)` (берём первые n бит)
2. Генерируем **случайный nonce** `k` ($1 \leq k \leq n-1$)
3. Вычисляем точку: `(x₁, y₁) = k × G`
4. `r = x₁ mod n`; если r = 0, начинаем заново
5. `s = k⁻¹ × (z + r × d) mod n`, где d — закрытый ключ; если s = 0, начинаем заново
6. Подпись: `(r, s)`

**Верификация:**
1. Хешируем: `z = hash(m)`
2. `w = s⁻¹ mod n`
3. `u₁ = z × w mod n`, `u₂ = r × w mod n`
4. `(x₁, y₁) = u₁ × G + u₂ × Q`, где Q — открытый ключ
5. Подпись верна если `r ≡ x₁ (mod n)`

### Критическая уязвимость: повторное использование nonce

**Самая опасная ошибка ECDSA** — использование одного и того же nonce `k` для двух разных сообщений.

Если `k` повторяется:
```
s₁ = k⁻¹ × (z₁ + r × d) mod n
s₂ = k⁻¹ × (z₂ + r × d) mod n

s₁ - s₂ = k⁻¹ × (z₁ - z₂) mod n
k = (z₁ - z₂) × (s₁ - s₂)⁻¹ mod n

d = (s₁ × k - z₁) × r⁻¹ mod n  ← закрытый ключ восстановлен!
```

### Реальный случай: взлом PlayStation 3 (2010)

Sony подписывала прошивки PS3 с помощью ECDSA, но использовала **константный nonce** (одно и то же значение k для всех подписей). Команда fail0verflow обнаружила это и восстановила закрытый ключ Sony, что позволило подписывать произвольный код для PS3.

Аналогичные уязвимости найдены в Bitcoin кошельках (несколько транзакций с одним k → украдены средства).

### Deterministic ECDSA (RFC 6979)

Решение: вместо случайного k генерировать его **детерминированно** из закрытого ключа и хеша сообщения через HMAC-DRBG:

```
k = HMAC-DRBG(key=private_key, data=hash(message))
```

Преимущества:
- k всегда уникален для разных сообщений (разные хеши → разный k)
- k всегда один и тот же для одинаковых (message, key) — подписание тестируемо
- Нет зависимости от качества PRNG

RFC 6979 стал стандартом: все современные ECDSA библиотеки используют детерминированный nonce.

```python
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

# ECDSA с P-256
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

message = b"Contract signed by Alice"

# Подписание (детерминированный nonce через RFC 6979 автоматически)
signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
print(f"Размер подписи ECDSA P-256: {len(signature)} байт")  # ~70-72 байт (DER)

# Верификация
try:
    public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    print("ECDSA подпись верна!")
except Exception:
    print("Подпись недействительна!")

# Детерминированность: одно и то же сообщение → одна и та же подпись
sig1 = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
sig2 = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
print(f"Детерминированность: {sig1 == sig2}")  # True (RFC 6979)

# Разные сообщения → разные подписи
sig3 = private_key.sign(b"Different message", ec.ECDSA(hashes.SHA256()))
print(f"Разные сообщения — разные подписи: {sig1 != sig3}")  # True

# Размер в сравнении с RSA
print(f"\nSравнение размеров подписей:")
from cryptography.hazmat.primitives.asymmetric import rsa, padding
rsa_key = rsa.generate_private_key(65537, 2048)
rsa_sig = rsa_key.sign(message, padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
print(f"RSA-2048 подпись: {len(rsa_sig)} байт")    # 256 байт
print(f"ECDSA P-256 подпись: {len(signature)} байт") # ~72 байта
```

---

## 4. Ed25519 — Edwards-curve подписи

### Что такое Ed25519

Ed25519 — алгоритм подписи на **кривой Эдвардса** (Edwards curve) **Curve25519/Ed25519**, разработанный Дэниелом Бернштейном. Технически это реализация **схемы подписи Шнорра** (Schnorr signature).

Кривая Ed25519: `x² + y² = 1 - (121665/121666)x²y²` над полем $\mathrm{GF}(2^{255} - 19)$.

### Ключевые особенности Ed25519

1. **Безопасность от реализационных ошибок:** Ed25519 не требует уникального nonce — он встроен детерминированно в алгоритм (nonce = H(private_key_second_half, message)). Нет риска повторного nonce.

2. **Малый размер:** подпись — 64 байта, открытый ключ — 32 байта.

3. **Высокая скорость:** быстрее P-256 ECDSA в среднем в 2-3 раза.

4. **Batch verification:** несколько подписей можно верифицировать быстрее, чем по одной (актуально для блокчейна).

5. **Нет уязвимостей к timing attacks** в эталонной реализации.

### Математика Ed25519 (упрощённо)

**Генерация ключей:**
1. Закрытый ключ `sk` — 32 случайных байта
2. `H = SHA-512(sk)` → два блока по 32 байта: `a` и `prefix`
3. Модифицируем `a` (clamping): установить/сбросить определённые биты
4. Открытый ключ `pk = a × B` (точка на кривой, encoded как 32 байта)

**Подписание:**
1. `r = H(prefix || message) mod ℓ` (детерминированный nonce!)
2. `R = r × B`
3. `S = (r + H(R || pk || message) × a) mod ℓ`
4. Подпись = `R || S` (64 байта)

**Верификация:**
1. `8 × S × B == 8 × R + 8 × H(R || pk || message) × pk`

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)

# Генерация ключей Ed25519
private_key = Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# Сериализация
priv_bytes = private_key.private_bytes(
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption()
)
pub_bytes = public_key.public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw
)
print(f"Ed25519 закрытый ключ: {len(priv_bytes)} байт")  # 32 байта
print(f"Ed25519 открытый ключ: {len(pub_bytes)} байт")   # 32 байта

# Подписание
message = b"Ed25519 signature example"
signature = private_key.sign(message)
print(f"Ed25519 подпись: {len(signature)} байт")  # 64 байта

# Верификация
try:
    public_key.verify(signature, message)
    print("Ed25519 подпись верна!")
except Exception:
    print("Подпись недействительна!")

# Детерминированность
sig1 = private_key.sign(message)
sig2 = private_key.sign(message)
print(f"Детерминированность Ed25519: {sig1 == sig2}")  # True

# Восстановление ключа из байт
restored_priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
restored_pub = Ed25519PublicKey.from_public_bytes(pub_bytes)

# Verify с восстановленным ключом
restored_pub.verify(signature, message)
print("Верификация с восстановленным ключом успешна!")
```

---

## 5. Применения цифровых подписей

### Git-подписи

```bash
# Настройка Git для использования GPG/SSH подписей
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global gpg.format ssh

# Подписание коммита
git commit -S -m "Signed commit"

# Подписание тегов
git tag -s v1.0 -m "Signed release v1.0"

# Верификация
git log --show-signature
git verify-commit HEAD
```

### TLS-сертификаты

TLS-сертификат — это открытый ключ, подписанный Certificate Authority (CA):

```python
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import datetime

# Создание самоподписанного сертификата Ed25519
private_key = Ed25519PrivateKey.generate()
public_key = private_key.public_key()

subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My Company"),
    x509.NameAttribute(NameOID.COMMON_NAME, "mycompany.ru"),
])

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(public_key)
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
    .add_extension(
        x509.SubjectAlternativeName([x509.DNSName("mycompany.ru")]),
        critical=False
    )
    .sign(private_key, None)  # Ed25519 не нужен отдельный hash алгоритм
)

cert_pem = cert.public_bytes(serialization.Encoding.PEM)
print(f"Сертификат: {len(cert_pem)} байт")
print(cert_pem.decode()[:100] + "...")
```

### JWT с RS256/ES256/EdDSA

```python
import base64
import json
import hashlib
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def create_jwt_es256(payload: dict, private_key) -> str:
    """JWT с ECDSA P-256 подписью (ES256)"""
    header = {"alg": "ES256", "typ": "JWT"}
    h = b64url(json.dumps(header, separators=(',',':')).encode())
    p = b64url(json.dumps(payload, separators=(',',':')).encode())
    
    signing_input = f"{h}.{p}".encode()
    
    # Подпись ECDSA P-256
    der_sig = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    
    # DER → raw (r || s, каждый 32 байта)
    # В реальных JWT библиотеках это делается автоматически
    import cryptography.hazmat.primitives.asymmetric.utils as asym_utils
    r, s = asym_utils.decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
    
    return f"{h}.{p}.{b64url(raw_sig)}"

def create_jwt_eddsa(payload: dict, private_key) -> str:
    """JWT с Ed25519 подписью (EdDSA)"""
    header = {"alg": "EdDSA", "crv": "Ed25519", "typ": "JWT"}
    h = b64url(json.dumps(header, separators=(',',':')).encode())
    p = b64url(json.dumps(payload, separators=(',',':')).encode())
    
    signing_input = f"{h}.{p}".encode()
    signature = private_key.sign(signing_input)
    
    return f"{h}.{p}.{b64url(signature)}"

# Примеры использования
ec_key = ec.generate_private_key(ec.SECP256R1())
ed_key = Ed25519PrivateKey.generate()

import time
payload = {"sub": "user_123", "exp": int(time.time()) + 3600, "role": "admin"}

jwt_es256 = create_jwt_es256(payload, ec_key)
jwt_eddsa = create_jwt_eddsa(payload, ed_key)

print(f"JWT ES256: {jwt_es256[:80]}...")
print(f"JWT EdDSA: {jwt_eddsa[:80]}...")
```

---

## 6. Сравнение алгоритмов подписи

| Характеристика        | RSA-2048 PSS | ECDSA P-256  | Ed25519      |
|-----------------------|-------------|-------------|-------------|
| Размер закрытого ключа| ~1800 байт  | ~32 байта   | 32 байта    |
| Размер открытого ключа| 256 байт    | 33/65 байт  | 32 байта    |
| Размер подписи        | 256 байт    | ~72 байта   | 64 байта    |
| Скорость подписания   | Медленно    | Быстро      | Очень быстро|
| Скорость верификации  | Быстро      | Быстро      | Очень быстро|
| Детерминированность   | Нет (PSS)   | RFC 6979    | Всегда      |
| Timing attack риск    | Умеренный   | Умеренный   | Минимальный |
| Batch verification    | Нет         | Нет         | Да          |
| Стандарт              | PKCS#1/FIPS | FIPS 186-4  | RFC 8032    |
| Применение            | TLS cert, PKI| TLS, Bitcoin| SSH, Signal |

---

## 7. Что выбрать

**Ed25519** — лучший выбор для новых систем:
- SSH ключи (`ssh-keygen -t ed25519`)
- JWT подписи
- API токены
- Мессенджеры

**ECDSA P-256** — выбор при требовании FIPS-совместимости или для Web (WebCrypto API поддерживает P-256 нативно):
- TLS сертификаты
- Code signing
- Bitcoin/Ethereum

**RSA-PSS** — только при legacy-совместимости:
- Взаимодействие со старыми системами
- FIPS-среды, ещё не поддерживающие ECC
- PGP/GPG (хотя и там ECC поддерживается)

---

## Заключение

Цифровые подписи — неотъемлемый элемент современной инфраструктуры доверия. Правильный выбор алгоритма и его безопасная реализация критически важны.

Ключевые выводы:
1. **RSA-PSS** безопаснее PKCS#1 v1.5 — используйте его при работе с RSA
2. **ECDSA требует уникального nonce** — повторный nonce раскрывает закрытый ключ (помните PS3)
3. **Deterministic ECDSA (RFC 6979)** устраняет эту угрозу
4. **Ed25519** — самый безопасный и быстрый выбор; детерминирован по конструкции
5. Всегда подписывайте **хеш** документа, а не сам документ напрямую
6. Используйте проверенные библиотеки — самостоятельная реализация опасна

---

## Литература и источники

1. RFC 8032. (2017). *Edwards-Curve Digital Signature Algorithm (EdDSA)*. IETF. https://www.rfc-editor.org/rfc/rfc8032
2. RFC 6979. (2013). *Deterministic Usage of the Digital Signature Algorithm (DSA) and Elliptic Curve Digital Signature Algorithm (ECDSA)*. IETF. https://www.rfc-editor.org/rfc/rfc6979
3. Bernstein, D.J., et al. (2012). *High-speed high-security signatures (Ed25519)*. https://ed25519.cr.yp.to/ed25519-20110926.pdf
4. NIST FIPS 186-5. (2023). *Digital Signature Standard (DSS)*. https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.186-5.pdf
5. fail0verflow. (2010). *PS3 Epic Fail* (PS3 ECDSA key recovery). https://events.ccc.de/congress/2010/Fahrplan/events/4087.en.html
6. Nakamoto, S. (Bitcoin). *Weak ECDSA nonces in the wild*. https://bitcoin.stackexchange.com/questions/35848
7. RFC 3447. (2003). *Public-Key Cryptography Standards (PKCS) #1: RSA Cryptography Specifications Version 2.1*. IETF. https://www.rfc-editor.org/rfc/rfc3447
8. Wikipedia: Digital Signature Algorithm. https://en.wikipedia.org/wiki/Digital_Signature_Algorithm
9. Wikipedia: EdDSA. https://en.wikipedia.org/wiki/EdDSA
10. Aumasson, J.P. (2017). *Serious Cryptography*. No Starch Press. https://nostarch.com/seriouscrypto
