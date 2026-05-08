# Асимметричная криптография: RSA и ECC

## Введение

Симметричная криптография решает задачу шифрования, но требует, чтобы обе стороны заранее обменялись секретным ключом. Как это сделать безопасно по открытому каналу? Именно эту проблему решает **асимметричная криптография**, также называемая криптографией с открытым ключом (public-key cryptography).

Идея, предложенная Диффи и Хеллманом в 1976 году, революционна: каждый участник имеет пару ключей — **открытый** (public key) и **закрытый** (private key). Открытый ключ можно публиковать свободно; закрытый — хранится в тайне. Сообщение, зашифрованное открытым ключом, можно расшифровать только закрытым. И наоборот — подпись, созданная закрытым ключом, проверяется открытым.

Два главных алгоритма асимметричной криптографии — **RSA** (Rivest-Shamir-Adleman, 1977) и **ECC** (Elliptic Curve Cryptography). RSA — классика, широко применяемая и сегодня; ECC — современная альтернатива, обеспечивающая тот же уровень безопасности при значительно меньших ключах.

---

## 1. RSA — криптография на основе факторизации

### Математическая основа

Безопасность RSA основана на вычислительной сложности задачи **факторизации больших чисел**: легко перемножить два больших простых числа, но трудно разложить произведение обратно на множители.

Например:
- Найти произведение: p = 61, q = 53 → n = $p \times q = 3233$ (тривиально)
- Обратная задача: дано n = 3233, найти p и q (для маленьких чисел легко, для 2048-битных — неосуществимо за разумное время)

### Генерация ключей RSA

Алгоритм генерации ключей RSA:

1. **Выбор простых чисел:** Выбираем два больших случайных простых числа `p` и `q` (примерно одного размера)
2. **Вычисление модуля:** `n = p × q`
3. **Функция Эйлера:** `φ(n) = (p-1) × (q-1)`
4. **Выбор открытой экспоненты:** Выбираем `e` такое, что `1 < e < φ(n)` и `gcd(e, φ(n)) = 1`. Обычно используют `e = 65537 = 2¹⁶ + 1` (простое число, удобное для быстрого возведения в степень)
5. **Вычисление закрытой экспоненты:** `d = e⁻¹ mod φ(n)` (модульный обратный элемент, находится расширенным алгоритмом Евклида)

**Открытый ключ:** `(n, e)`  
**Закрытый ключ:** `(n, d)` (или полная форма: `(p, q, d, dp, dq, qinv)` для ускорения через CRT)

```python
from math import gcd
from sympy import isprime, randprime
import random

def generate_rsa_keys(bits=512):  # В реальности используйте >= 2048!
    """Демонстрационная генерация ключей RSA"""
    
    # Генерация простых чисел
    p = randprime(2**(bits//2 - 1), 2**(bits//2))
    q = randprime(2**(bits//2 - 1), 2**(bits//2))
    while p == q:
        q = randprime(2**(bits//2 - 1), 2**(bits//2))
    
    n = p * q
    phi_n = (p - 1) * (q - 1)
    
    # Открытая экспонента
    e = 65537
    assert gcd(e, phi_n) == 1
    
    # Закрытая экспонента через расширенный алгоритм Евклида
    d = pow(e, -1, phi_n)  # Python 3.8+
    
    return (n, e), (n, d)  # (public_key, private_key)

# Шифрование и дешифрование (учебный пример - без padding!)
def rsa_encrypt_raw(message: int, public_key) -> int:
    n, e = public_key
    return pow(message, e, n)  # m^e mod n

def rsa_decrypt_raw(ciphertext: int, private_key) -> int:
    n, d = private_key
    return pow(ciphertext, d, n)  # c^d mod n

pub, priv = generate_rsa_keys(bits=512)
m = 42
c = rsa_encrypt_raw(m, pub)
recovered = rsa_decrypt_raw(c, priv)
print(f"Исходное: {m}, Расшифровано: {recovered}, Совпадает: {m == recovered}")
```

### Шифрование и дешифрование RSA

**Шифрование:** `c = mᵉ mod n`  
**Дешифрование:** `m = cᵈ mod n`

Математическая корректность обеспечивается теоремой Эйлера: `(mᵉ)ᵈ mod n = m` при условии `e·d ≡ 1 (mod φ(n))`.

### Почему RSA медленный

RSA требует модульного возведения в степень с большими числами (2048+ бит). Операция `mᵉ mod n` для `e = 65537` требует около 17 умножений (быстрое возведение в степень), но каждое умножение — это операция с 2048-битными числами. В итоге:

- RSA шифрование (с маленьким e) — около 10 000 умножений на 2048-битных числах
- RSA расшифрование (с d) — порядка 300 000 умножений

Для сравнения, AES шифрует данные в 1000+ раз быстрее. Поэтому RSA **никогда не шифрует сами данные** — он шифрует только симметричный ключ сессии.

### OAEP padding

Голое RSA (textbook RSA, без padding) уязвимо к различным атакам. На практике используются схемы padding:

- **PKCS#1 v1.5** — старый стандарт, уязвим к атаке Блейхенбахера (1998). Использование нежелательно, но встречается в legacy системах
- **OAEP** (Optimal Asymmetric Encryption Padding) — современный стандарт, PKCS#1 v2.x. Использует случайные данные и хеш-функцию для рандомизации

```python
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

# Генерация ключевой пары (используйте 4096 для максимальной безопасности)
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)
public_key = private_key.public_key()

# Шифрование с OAEP
plaintext = b"Secret symmetric key: " + b'\x42' * 32

ciphertext = public_key.encrypt(
    plaintext,
    padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None
    )
)
print(f"Шифротекст RSA-2048: {len(ciphertext)} байт")  # 256 байт

# Расшифровка
recovered = private_key.decrypt(
    ciphertext,
    padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None
    )
)
assert recovered == plaintext
print("Расшифровка успешна!")
```

### Размер ключей RSA и безопасность

| Размер ключа RSA | Аналог ECC | Бит безопасности | Статус               |
|-----------------|-----------|-----------------|----------------------|
| 512 бит         | —         | ~56             | Небезопасен (взломан)|
| 1024 бит        | 160 бит   | ~80             | Небезопасен          |
| 2048 бит        | 224 бит   | ~112            | Минимум до ~2030     |
| 3072 бит        | 256 бит   | ~128            | Рекомендован         |
| 4096 бит        | 384 бит   | ~140            | Для долгосрочной защиты |

NIST рекомендует минимум **2048 бит** для RSA и переход на 3072 бит к 2030 году.

---

## 2. ECC — криптография на эллиптических кривых

### Математическая основа

ECC основана на задаче **дискретного логарифма на эллиптической кривой** (ECDLP). Группа точек на эллиптической кривой над конечным полем образует математическую структуру, в которой операции просты в одном направлении и вычислительно нереализуемы в обратном.

**Эллиптическая кривая** задаётся уравнением вида (форма Вейерштрасса):
```
y² = x³ + ax + b (mod p)
```

где `p` — большое простое число, а `4a³ + 27b² ≠ 0 (mod p)` (кривая невырождена).

Точки кривой вместе с воображаемой «точкой на бесконечности» O образуют **абелеву группу**:

**Сложение точек:** По двум точкам P и Q на кривой определяется операция сложения P + Q (геометрически — провести прямую через P и Q, найти третью точку пересечения с кривой, отразить по x-оси).

**Скалярное умножение:** `kP = P + P + ... + P` (k раз). Это операция в одну сторону — вычислить `Q = kP` легко (используя алгоритм double-and-add), найти `k` по известным P и Q — вычислительно неосуществимо.

### Генерация ключей ECC

1. Выбираем кривую (например, P-256)
2. У кривой есть публично известная **базовая точка** G
3. **Закрытый ключ:** случайное целое число `k` (256 бит для P-256)
4. **Открытый ключ:** точка `Q = k × G`

Безопасность: зная G и Q, нельзя восстановить k.

```python
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

# Генерация ключевой пары ECC на кривой P-256
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

# Размер ключей
priv_bytes = private_key.private_bytes(
    serialization.Encoding.DER,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()
)
pub_bytes = public_key.public_bytes(
    serialization.Encoding.DER,
    serialization.PublicFormat.SubjectPublicKeyInfo
)
print(f"Закрытый ключ: {len(priv_bytes)} байт")  # ~138 байт
print(f"Открытый ключ: {len(pub_bytes)} байт")   # ~91 байт
# Для RSA-2048: ~1218 и ~294 байт соответственно
```

### Популярные кривые

| Кривая           | Поле     | Размер | Разработчик | Примечание                  |
|-----------------|----------|--------|------------|----------------------------|
| P-256 (secp256r1)| GF(p)   | 256    | NIST       | TLS, JWT ES256, Android    |
| P-384 (secp384r1)| GF(p)   | 384    | NIST       | Высокая безопасность       |
| secp256k1       | GF(p)   | 256    | Certicom   | Bitcoin, Ethereum          |
| Curve25519      | GF(p)   | 255    | Bernstein  | X25519, самая быстрая      |
| Ed25519         | GF(p)   | 255    | Bernstein  | Подписи, SSH, Signal       |

**Curve25519** разработана Бернштейном специально для максимальной скорости и устойчивости к timing attacks. Используется в X25519 (обмен ключами) и Ed25519 (подписи).

Кривые NIST P-256/P-384 критикуются за непрозрачный способ выбора констант («ничего в рукаве» не доказано), тогда как Curve25519 имеет полностью верифицируемые параметры.

---

## 3. ECDH — обмен ключами на эллиптических кривых

ECDH (Elliptic Curve Diffie-Hellman) — это протокол согласования общего секрета:

1. Алиса генерирует `(a, A = a×G)`; Боб генерирует `(b, B = b×G)`
2. Обмениваются открытыми ключами: Алиса отдаёт A, Боб отдаёт B
3. Алиса вычисляет `S = a × B = a × b × G`
4. Боб вычисляет `S = b × A = b × a × G`
5. S — общий секрет (только его координата x используется как pre-master secret)

```python
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# Алиса
alice_private = X25519PrivateKey.generate()
alice_public = alice_private.public_key()

# Боб
bob_private = X25519PrivateKey.generate()
bob_public = bob_private.public_key()

# Обмен открытыми ключами (по открытому каналу)
# Алиса получает открытый ключ Боба:
alice_shared = alice_private.exchange(bob_public)

# Боб получает открытый ключ Алисы:
bob_shared = bob_private.exchange(alice_public)

# Оба получили одинаковый секрет
assert alice_shared == bob_shared

# Из shared secret выводим реальный ключ через HKDF
def derive_key(shared_secret: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    ).derive(shared_secret)

session_key = derive_key(alice_shared, salt=b"session_salt_2024", info=b"aes-key")
print(f"Сессионный ключ AES-256: {session_key.hex()}")
```

---

## 4. Сравнение RSA и ECC

### Производительность

| Операция                 | RSA-2048     | ECC P-256    | Преимущество |
|--------------------------|-------------|-------------|--------------|
| Генерация ключей         | ~100 мс     | ~0.1 мс     | ECC в 1000x  |
| Шифрование/Вер. подписи  | ~1 мс       | ~0.5 мс     | Сопоставимо  |
| Расшифровка/Подпись      | ~10 мс      | ~1 мс       | ECC в 10x    |
| Размер открытого ключа   | 256 байт    | 33 байта    | ECC в 8x     |
| Размер подписи           | 256 байт    | 64 байта    | ECC в 4x     |

### Уровень безопасности

| Биты безопасности | RSA/DH    | ECC    |
|------------------|-----------|--------|
| 80 бит           | 1024 бит  | 160 бит|
| 112 бит          | 2048 бит  | 224 бит|
| 128 бит          | 3072 бит  | 256 бит|
| 192 бит          | 7680 бит  | 384 бит|
| 256 бит          | 15360 бит | 512 бит|

ECC обеспечивает тот же уровень безопасности при значительно меньшем размере ключа. Это особенно важно для:
- IoT устройств с ограниченной памятью
- Смарт-карт и аппаратных токенов
- Мобильных устройств
- Высоконагруженных серверов (TLS handshake)

---

## 5. Практическое применение

### Гибридное шифрование (реальная схема)

Асимметричная криптография на практике всегда используется в **гибридной схеме**: асимметричный алгоритм шифрует только симметричный ключ, а симметричный шифрует сами данные.

```
1. Генерируем случайный AES ключ K (32 байта)
2. Шифруем данные: C = AES-GCM(K, данные)
3. Шифруем ключ: EK = RSA-OAEP(публичный_ключ_получателя, K)
4. Передаём: (EK, C)

Получатель:
1. K = RSA-OAEP.decrypt(закрытый_ключ, EK)
2. данные = AES-GCM.decrypt(K, C)
```

```python
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
import os

def hybrid_encrypt(recipient_public_key, plaintext: bytes) -> dict:
    """Гибридное шифрование: RSA-OAEP + AES-256-GCM"""
    
    # 1. Генерация случайного симметричного ключа
    sym_key = os.urandom(32)  # AES-256
    
    # 2. Шифрование данных симметричным ключом
    nonce = os.urandom(12)
    aesgcm = AESGCM(sym_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    # 3. Шифрование симметричного ключа открытым ключом получателя
    encrypted_key = recipient_public_key.encrypt(
        sym_key,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    return {
        "encrypted_key": encrypted_key,  # RSA шифротекст ключа
        "nonce": nonce,
        "ciphertext": ciphertext          # AES шифротекст данных
    }

def hybrid_decrypt(recipient_private_key, encrypted_data: dict) -> bytes:
    """Расшифровка гибридного шифротекста"""
    
    # 1. Расшифровка симметричного ключа
    sym_key = recipient_private_key.decrypt(
        encrypted_data["encrypted_key"],
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # 2. Расшифровка данных
    aesgcm = AESGCM(sym_key)
    return aesgcm.decrypt(
        encrypted_data["nonce"],
        encrypted_data["ciphertext"],
        None
    )

# Демонстрация
recipient_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
recipient_public = recipient_private.public_key()

secret_message = b"This is a large secret document..." * 100

encrypted = hybrid_encrypt(recipient_public, secret_message)
print(f"Зашифрованный ключ: {len(encrypted['encrypted_key'])} байт")
print(f"Зашифрованные данные: {len(encrypted['ciphertext'])} байт")

decrypted = hybrid_decrypt(recipient_private, encrypted)
assert decrypted == secret_message
print("Гибридное шифрование/расшифровка успешна!")
```

### ECC и ECIES

Аналог гибридного шифрования для ECC называется **ECIES** (Elliptic Curve Integrated Encryption Scheme):

1. Генерируем временную пару ключей (ephemeral keypair)
2. ECDH с открытым ключом получателя → shared secret
3. KDF из shared secret → симметричный ключ
4. AES-GCM шифрование данных
5. Передаём ephemeral public key + шифротекст

```python
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
import os

def ecies_encrypt(recipient_public_key, plaintext: bytes) -> dict:
    """ECIES: X25519 + HKDF + AES-256-GCM"""
    
    # Временная пара ключей
    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()
    
    # ECDH с ключом получателя
    shared_secret = ephemeral_private.exchange(recipient_public_key)
    
    # KDF
    sym_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"ecies-encryption"
    ).derive(shared_secret)
    
    # Шифрование
    nonce = os.urandom(12)
    ciphertext = AESGCM(sym_key).encrypt(nonce, plaintext, None)
    
    return {
        "ephemeral_public": ephemeral_public.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        ),
        "nonce": nonce,
        "ciphertext": ciphertext
    }

# Пример использования
recipient_priv = X25519PrivateKey.generate()
recipient_pub = recipient_priv.public_key()

encrypted = ecies_encrypt(recipient_pub, b"Secret message via ECIES")
print(f"Ephemeral public key: {len(encrypted['ephemeral_public'])} байт")
print(f"Nonce: {len(encrypted['nonce'])} байт")
print(f"Ciphertext+tag: {len(encrypted['ciphertext'])} байт")
```

---

## 6. RSA vs ECC: когда что выбирать

**Используйте RSA, если:**
- Нужна совместимость с legacy системами
- Требования FIPS/государственные стандарты, указывающие на RSA
- Программное обеспечение не поддерживает ECC
- Размер 2048-4096 бит приемлем

**Используйте ECC, если:**
- Производительность критична (TLS handshakes на нагруженном сервере)
- Ограниченные ресурсы (IoT, смарт-карты, мобильные)
- Маленький размер ключей и подписей важен
- Новый проект без legacy-ограничений

**В современном TLS 1.3:** RSA для обмена ключами полностью удалён (только ECDHE/DHE). RSA используется только для аутентификации через сертификаты.

---

## 7. Атаки на RSA

### Маленькая экспонента (low exponent attack)

Если e = 3 и одно сообщение шифруется тремя разными модулями `n₁, n₂, n₃`, атакующий через CRT (Китайскую теорему об остатках) восстанавливает `m³ mod (n₁n₂n₃)` и берёт кубический корень.

**Защита:** OAEP padding рандомизирует сообщение, исключая такую атаку.

### Атака Блейхенбахера (1998)

На PKCS#1 v1.5 padding: oracle, говорящий "padding корректен/нет", позволяет адаптивно подобрать открытый текст. Требует ~10⁶ запросов к oracle.

**Защита:** OAEP padding, постоянное время обработки ошибок.

### Faktorizatsiya через слабую генерацию p и q

Если p и q близки (|p - q| мало), или числа сгенерированы слабым PRNG — возможна факторизация. Известный случай: ключи Debian 2008 года, сгенерированные с уязвимым RNG.

---

## Заключение

Асимметричная криптография позволяет решить фундаментальную задачу обмена ключами по открытому каналу и обеспечить нотариальную функцию цифровой подписи.

**RSA** — надёжный, хорошо изученный алгоритм с 1977 года. Требует ключей 2048+ бит, работает медленно, размер шифротекста и подписи велик. Подходит для legacy-совместимости и сертификатов в PKI.

**ECC** — современный стандарт, обеспечивающий тот же уровень безопасности при меньших ключах (P-256, Curve25519). Значительно быстрее в генерации ключей и при вычислениях. Рекомендован для новых систем.

Ключевые практические выводы:
1. Никогда не шифруйте данные напрямую асимметричным алгоритмом — используйте гибридное шифрование
2. RSA требует OAEP padding — PKCS#1 v1.5 небезопасен
3. Размер ключа RSA: минимум 2048 бит, рекомендовано 3072+
4. Для новых систем ECC (P-256 или Curve25519) предпочтительнее RSA

---

## Литература и источники

1. Rivest, R.L., Shamir, A., Adleman, L. (1978). *A Method for Obtaining Digital Signatures and Public-Key Cryptosystems*. Communications of the ACM, 21(2). https://dl.acm.org/doi/10.1145/359340.359342
2. Diffie, W., Hellman, M. (1976). *New Directions in Cryptography*. IEEE Transactions on Information Theory. https://ee.stanford.edu/~hellman/publications/24.pdf
3. RFC 8017. (2016). *PKCS #1: RSA Cryptography Specifications Version 2.2*. IETF. https://www.rfc-editor.org/rfc/rfc8017
4. NIST SP 800-56A. *Recommendation for Pair-Wise Key-Establishment Schemes Using Discrete Logarithm Cryptography*. https://csrc.nist.gov/publications/detail/sp/800-56a/rev-3/final
5. Hankerson, D., Menezes, A., Vanstone, S. (2004). *Guide to Elliptic Curve Cryptography*. Springer. https://link.springer.com/book/10.1007/b97644
6. Bernstein, D.J. (2006). *Curve25519: new Diffie-Hellman speed records*. https://cr.yp.to/ecdh/curve25519-20060209.pdf
7. Bleichenbacher, D. (1998). *Chosen Ciphertext Attacks Against Protocols Based on the RSA Encryption Standard PKCS#1*. CRYPTO 1998.
8. Wikipedia: RSA (cryptosystem). https://en.wikipedia.org/wiki/RSA_(cryptosystem)
9. Wikipedia: Elliptic-curve cryptography. https://en.wikipedia.org/wiki/Elliptic-curve_cryptography
10. Aumasson, J.P. (2017). *Serious Cryptography*. No Starch Press. https://nostarch.com/seriouscrypto
