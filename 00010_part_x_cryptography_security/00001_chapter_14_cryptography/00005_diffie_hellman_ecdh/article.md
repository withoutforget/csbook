# Diffie-Hellman и ECDH — обмен ключами

## Введение

Представьте задачу: два человека хотят обменяться секретным ключом для шифрования переписки, но у них нет никакого предварительно согласованного секрета, а все их сообщения читает посторонний. Казалось бы, эта задача неразрешима — ведь для шифрования нужен общий ключ, а согласовать ключ можно только по защищённому каналу. Но в 1976 году Уитфилд Диффи (Whitfield Diffie) и Мартин Хеллман (Martin Hellman) опубликовали революционную работу, доказавшую, что решение существует.

Протокол **Diffie-Hellman Key Exchange (DH)** позволяет двум сторонам согласовать общий секрет по открытому каналу, опираясь на вычислительную сложность задачи дискретного логарифма. Это открытие заложило фундамент всей современной публичной криптографии. **ECDH** — его версия на эллиптических кривых — сегодня является стандартом в TLS, SSH и мессенджерах.

---

## 1. Протокол Диффи-Хеллмана (1976)

### Математическая основа

DH основан на задаче **дискретного логарифма**: для большого простого числа `p`, генератора `g` и числа `y = g^x mod p` — найти `x` вычислительно нереализуемо (при достаточно больших параметрах).

Легко: `y = g^x mod p` (быстрое возведение в степень, O(log x))  
Трудно: найти `x` по `g`, `p`, `y` (нет эффективного алгоритма для больших p)

### Протокол DH шаг за шагом

**Публичные параметры** (известны всем, включая атакующего):
- `p` — большое простое число (2048+ бит)
- `g` — генератор (обычно 2 или 5)

**Алиса:**
1. Выбирает случайное секретное число `a` (закрытый ключ)
2. Вычисляет `A = g^a mod p` (открытый ключ)
3. Отправляет `A` Бобу

**Боб:**
1. Выбирает случайное секретное число `b` (закрытый ключ)
2. Вычисляет `B = g^b mod p` (открытый ключ)
3. Отправляет `B` Алисе

**Вычисление общего секрета:**
- Алиса: `S = B^a mod p = (g^b)^a mod p = g^(ab) mod p`
- Боб: `S = A^b mod p = (g^a)^b mod p = g^(ab) mod p`

Оба вычислили `S = g^(ab) mod p` — одинаковый секрет!

Атакующий видит `g, p, A = g^a mod p, B = g^b mod p`, но не может найти `a` или `b` (задача дискретного логарифма), следовательно, не может вычислить `S`.

```python
# Демонстрация DH с малыми числами (НЕ для реального использования!)
def dh_demo():
    # Публичные параметры (очень маленькие для примера)
    p = 23  # Простое число (в реальности 2048+ бит)
    g = 5   # Генератор
    
    print(f"Публичные параметры: p={p}, g={g}")
    
    # Алиса
    a = 6  # Закрытый ключ Алисы (в реальности - случайное число)
    A = pow(g, a, p)  # g^a mod p
    print(f"Алиса: a={a} (секрет), A={A} (открытый)")
    
    # Боб
    b = 15  # Закрытый ключ Боба
    B = pow(g, b, p)  # g^b mod p
    print(f"Боб: b={b} (секрет), B={B} (открытый)")
    
    # Обмен: Алиса отдаёт A, Боб отдаёт B
    
    # Алиса вычисляет общий секрет
    S_alice = pow(B, a, p)  # B^a mod p
    
    # Боб вычисляет общий секрет
    S_bob = pow(A, b, p)    # A^b mod p
    
    print(f"Общий секрет Алисы: {S_alice}")
    print(f"Общий секрет Боба: {S_bob}")
    print(f"Совпадают: {S_alice == S_bob}")
    
    # Злоумышленник видит p=23, g=5, A=8, B=19 — задача DL: найти a или b

dh_demo()
```

### Реальные параметры DH

Для безопасности DH нужны тщательно выбранные параметры. Размер `p`:

| Биты безопасности | Размер p DH/DSA | Эквивалент RSA |
|------------------|----------------|---------------|
| 80 бит           | 1024 бит       | 1024 бит      |
| 112 бит          | 2048 бит       | 2048 бит      |
| 128 бит          | 3072 бит       | 3072 бит      |
| 192 бит          | 7680 бит       | 7680 бит      |

**Logjam attack (2015):** Исследователи показали, что оба наиболее популярных 1024-битных DH простых числа (используемых в TLS и IPsec) можно взломать ресурсами государственного уровня. В TLS 1.3 DH с фиксированными параметрами удалён.

Стандартизированные безопасные группы DH: RFC 3526 (Oakley Groups), RFC 7919.

---

## 2. ECDH — DH на эллиптических кривых

### От модульной арифметики к эллиптическим кривым

ECDH (Elliptic Curve Diffie-Hellman) — это тот же протокол DH, но вместо мультипликативной группы целых чисел по модулю p используется **группа точек на эллиптической кривой**.

Операция скалярного умножения точки `kP` (k-кратное сложение точки P с собой) является «односторонней»:
- Вычислить `Q = kP` — легко (double-and-add, O(log k))
- Найти `k` по `P` и `Q` (ECDLP) — нереализуемо

### Протокол ECDH

**Алиса:**
1. `a` — случайный скаляр (закрытый ключ, 256 бит для P-256)
2. `A = a × G` (открытый ключ, точка на кривой)

**Боб:**
1. `b` — случайный скаляр
2. `B = b × G`

**Общий секрет:**
- Алиса: `S = a × B = a × (b × G) = (ab) × G`
- Боб: `S = b × A = b × (a × G) = (ab) × G`

Из общего секрета S используется только x-координата как pre-master secret.

```python
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

# ECDH с Curve25519 (X25519)
def ecdh_x25519_example():
    """Демонстрация ECDH с X25519"""
    # Алиса
    alice_priv = X25519PrivateKey.generate()
    alice_pub = alice_priv.public_key()
    
    # Боб
    bob_priv = X25519PrivateKey.generate()
    bob_pub = bob_priv.public_key()
    
    # Публичные ключи (32 байта каждый)
    alice_pub_bytes = alice_pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    bob_pub_bytes = bob_pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print(f"Открытый ключ Алисы (X25519): {alice_pub_bytes.hex()[:32]}...")
    print(f"Открытый ключ Боба (X25519): {bob_pub_bytes.hex()[:32]}...")
    
    # Обмен: каждый получает открытый ключ другого
    
    # Алиса: shared = alice_priv × bob_pub
    alice_shared = alice_priv.exchange(bob_pub)
    
    # Боб: shared = bob_priv × alice_pub
    bob_shared = bob_priv.exchange(alice_pub)
    
    print(f"Общий секрет совпадает: {alice_shared == bob_shared}")
    
    # Выводим ключи сессии через HKDF
    session_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"session_keys"
    ).derive(alice_shared)
    
    print(f"Ключ сессии AES-256: {session_key.hex()}")
    return session_key

# ECDH с P-256
def ecdh_p256_example():
    """ECDH с NIST P-256"""
    alice_priv = ec.generate_private_key(ec.SECP256R1())
    bob_priv = ec.generate_private_key(ec.SECP256R1())
    
    # ECDH
    alice_shared = alice_priv.exchange(ec.ECDH(), bob_priv.public_key())
    bob_shared = bob_priv.exchange(ec.ECDH(), alice_priv.public_key())
    
    print(f"P-256 ECDH общий секрет: {alice_shared.hex()}")
    print(f"Совпадают: {alice_shared == bob_shared}")

ecdh_x25519_example()
ecdh_p256_example()
```

---

## 3. Ephemeral DH и Perfect Forward Secrecy

### Статический vs Эфемерный DH

**Статический DH (DH без прилагательного):**
- Долгосрочные ключи используются во всех сессиях
- Компрометация закрытого ключа → расшифровка всего прошлого трафика

**Эфемерный DH (DHE/ECDHE — Ephemeral):**
- Для каждой сессии генерируются **новые** временные пары ключей
- После завершения сессии — временные ключи уничтожаются
- Компрометация долгосрочного ключа **не даёт** расшифровать прошлые сессии

### Perfect Forward Secrecy (PFS)

PFS (также называемый Forward Secrecy, FS) — свойство протокола, при котором компрометация долгосрочного ключа не позволяет расшифровать прошлые сессии.

**Без PFS (RSA key exchange в TLS 1.2):**
```
Клиент выбирает pre-master secret → шифрует его RSA-публичным ключом сервера
Пассивный атакующий записывает трафик
Если сервер потом скомпрометирован → RSA закрытый ключ известен
→ Расшифровка всего записанного трафика
```

**С PFS (ECDHE в TLS 1.3):**
```
Каждая сессия: сервер + клиент генерируют новые временные ECDH ключи
Pre-master secret = ECDHE результат (временные ключи)
Долгосрочный ключ сервера используется только для аутентификации
→ Компрометация долгосрочного ключа не расшифровывает прошлые сессии
→ Временные ключи уже удалены
```

```python
class TLSLikeHandshake:
    """Упрощённая демонстрация TLS 1.3-подобного обмена с PFS"""
    
    def __init__(self):
        # Долгосрочные ключи (для аутентификации)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.server_long_term_key = Ed25519PrivateKey.generate()
        self.server_public_key = self.server_long_term_key.public_key()
    
    def server_hello(self):
        """Сервер создаёт ВРЕМЕННЫЙ ECDH ключ для сессии"""
        self.server_ephemeral_priv = X25519PrivateKey.generate()
        self.server_ephemeral_pub = self.server_ephemeral_priv.public_key()
        
        # Подписываем ephemeral ключ долгосрочным ключом (аутентификация)
        pub_bytes = self.server_ephemeral_pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        signature = self.server_long_term_key.sign(pub_bytes)
        
        return self.server_ephemeral_pub, signature
    
    def client_hello_and_derive_key(self, server_ephemeral_pub, signature):
        """Клиент создаёт свой ВРЕМЕННЫЙ ECDH ключ и выводит ключ сессии"""
        # Верификация подписи
        pub_bytes = server_ephemeral_pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.server_public_key.verify(signature, pub_bytes)
        print("Аутентификация сервера успешна!")
        
        # Временный ключ клиента
        client_ephemeral_priv = X25519PrivateKey.generate()
        client_ephemeral_pub = client_ephemeral_priv.public_key()
        
        # ECDH — общий секрет
        shared_secret = client_ephemeral_priv.exchange(server_ephemeral_pub)
        
        # Вывод ключей сессии (HKDF)
        session_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"tls13-session"
        ).derive(shared_secret)
        
        # Временные ключи удаляются после установки сессии!
        del client_ephemeral_priv
        
        return client_ephemeral_pub, session_key
    
    def server_derive_key(self, client_ephemeral_pub, session_id: str):
        """Сервер выводит тот же ключ"""
        shared_secret = self.server_ephemeral_priv.exchange(client_ephemeral_pub)
        
        session_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"tls13-session"
        ).derive(shared_secret)
        
        # Удаляем временный ключ сервера
        del self.server_ephemeral_priv
        
        return session_key

# Демонстрация
handshake = TLSLikeHandshake()
server_eph_pub, sig = handshake.server_hello()
client_eph_pub, client_key = handshake.client_hello_and_derive_key(server_eph_pub, sig)
server_key = handshake.server_derive_key(client_eph_pub, "session_1")

print(f"Ключ клиента: {client_key.hex()}")
print(f"Ключ сервера: {server_key.hex()}")
print(f"Ключи совпадают (PFS сессия установлена): {client_key == server_key}")
```

---

## 4. X25519 — Curve25519 для обмена ключами

X25519 — это протокол ECDH на кривой Curve25519, разработанный Дэниелом Бернштейном. Это рекомендованный алгоритм для современных систем.

### Преимущества X25519 перед P-256 ECDH

1. **Скорость:** Curve25519 оптимизирована для быстрого скалярного умножения
2. **Безопасность реализации:** Curve25519 использует формулу Монтгомери, позволяющую реализовать скалярное умножение за постоянное время без branch-зависимостей
3. **Прозрачность параметров:** Параметры Curve25519 выбраны с открытым обоснованием, без подозрений в backdoor
4. **Малый размер ключей:** 32 байта (256 бит) — открытый и закрытый ключи

```python
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey
)
import os

# Генерация пары ключей
private_key = X25519PrivateKey.generate()
public_key = private_key.public_key()

# Сериализация для хранения/передачи
priv_bytes = private_key.private_bytes(
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption()
)

pub_bytes = public_key.public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw
)

print(f"Закрытый ключ X25519: {len(priv_bytes)} байт = {priv_bytes.hex()[:32]}...")
print(f"Открытый ключ X25519: {len(pub_bytes)} байт = {pub_bytes.hex()}")

# Восстановление из байт
restored_priv = X25519PrivateKey.from_private_bytes(priv_bytes)
restored_pub = X25519PublicKey.from_public_bytes(pub_bytes)
```

---

## 5. MITM-атака на DH без аутентификации

DH/ECDH сам по себе не обеспечивает аутентификацию. Это открывает дверь для **Man-in-the-Middle (MITM) атаки**:

```
Без аутентификации:
Алиса ──A──→ [Злоумышленник] ──A'──→ Боб
Алиса ←──M──  [Злоумышленник]  ←──B── Боб

1. Алиса отправляет свой открытый ключ A
2. Злоумышленник перехватывает, создаёт СВОЙ ключ M для Алисы и A' для Боба
3. Алиса думает, что общается с Бобом, на самом деле — со Злоумышленником
4. Злоумышленник расшифровывает сообщения от Алисы, перешифровывает для Боба

→ Злоумышленник видит весь трафик!
```

**Защита:** Аутентификация открытых ключей через:
- **Цифровые подписи** (сервер подписывает свой ECDH ключ закрытым ключом RSA/ECDSA)
- **Сертификаты X.509** (PKI иерархия)
- **Public key pinning** (клиент доверяет только конкретному ключу)
- **Аутентификация SAS** (в Zfone/ZRTP — verbal confirmation)

В TLS:
- Сервер подписывает (server_hello, ECDHE public key, client_hello) своим RSA/ECDSA ключом из сертификата
- Клиент проверяет сертификат через цепочку CA
- → MITM невозможен без компрометации CA

```python
# Демонстрация MITM атаки (только для понимания уязвимости)
def demonstrate_mitm():
    """DH без аутентификации уязвим к MITM"""
    
    # Алиса и Боб
    alice_priv = X25519PrivateKey.generate()
    alice_pub = alice_priv.public_key()
    
    bob_priv = X25519PrivateKey.generate()
    bob_pub = bob_priv.public_key()
    
    # Злоумышленник создаёт ДВЕ пары ключей
    mitm_for_alice = X25519PrivateKey.generate()
    mitm_for_bob = X25519PrivateKey.generate()
    
    # Злоумышленник "посредничает":
    # Алиса думает, что общается с Бобом через mitm_for_alice.public_key()
    alice_shared = alice_priv.exchange(mitm_for_alice.public_key())
    
    # Боб думает, что общается с Алисой через mitm_for_bob.public_key()
    bob_shared = bob_priv.exchange(mitm_for_bob.public_key())
    
    # Злоумышленник знает оба секрета!
    mitm_alice_secret = mitm_for_alice.exchange(alice_pub)
    mitm_bob_secret = mitm_for_bob.exchange(bob_pub)
    
    print("=== MITM демонстрация (без аутентификации) ===")
    print(f"Секрет Алисы:          {alice_shared.hex()[:16]}...")
    print(f"Секрет Боба:           {bob_shared.hex()[:16]}...")
    print(f"MITM знает секрет Алисы: {alice_shared == mitm_alice_secret}")
    print(f"MITM знает секрет Боба:  {bob_shared == mitm_bob_secret}")
    print("→ Злоумышленник может расшифровать весь трафик!")

demonstrate_mitm()
```

---

## 6. DH в TLS

В TLS 1.3 используется исключительно **ECDHE** (Ephemeral ECDH). Поддерживаемые группы:

- x25519 (рекомендован)
- secp256r1 (P-256)
- secp384r1 (P-384)
- x448 (Curve448 — 224 бита безопасности)
- secp521r1 (P-521)
- ffdhe2048, ffdhe3072, ffdhe4096 (финитные поля DH)

TLS 1.2 поддерживал также RSA key exchange (без PFS) и статические DH — оба удалены в TLS 1.3.

```
TLS 1.3 Key Schedule (упрощённо):

1. ClientHello: поддерживаемые группы + ECDHE KeyShare для каждой
2. ServerHello: выбранная группа + server ECDHE KeyShare
3. ECDH → (EC)DHE секрет
4. HKDF: Early Secret → Handshake Secret → Master Secret → ключи записи
5. Расшифровка сертификата и Finished сообщения
6. Данные шифруются с ключами, выведенными из ECDHE+HKDF
```

Преимущество TLS 1.3: серверный сертификат передаётся уже зашифрованным (после установки ключей), что скрывает SNI от пассивного наблюдателя.

---

## 7. Signal Protocol и Double Ratchet (краткое введение)

Signal Protocol (используется в WhatsApp, Signal, Matrix) расширяет ECDH через **Тройной Диффи-Хеллман** (3DH, X3DH) и **Double Ratchet Algorithm**:

- **X3DH:** обмен ключами через 4 DH операции, включая долгосрочные и одноразовые ключи
- **Double Ratchet:** каждое сообщение получает свой ключ через цепной KDF ratchet

Это обеспечивает не только Forward Secrecy, но и **Break-in Recovery** (backward secrecy): компрометация одного сообщения не компрометирует все следующие.

---

## 8. Сравнение DH вариантов

| Параметр           | DHE (конечные поля) | ECDHE P-256   | X25519        |
|--------------------|---------------------|--------------|---------------|
| Размер ключа       | 2048-4096 бит       | 256 бит      | 256 бит       |
| Скорость           | Медленно            | Быстро       | Очень быстро  |
| Размер обмена      | 256-512 байт        | 65 байт      | 32 байта      |
| Стандартизация     | RFC 7919            | NIST/SEC2    | RFC 7748      |
| Timing attacks     | Риск                | Риск         | Безопасен     |
| Применение         | TLS (legacy)        | TLS, JWT     | TLS 1.3, SSH  |

---

## Заключение

Протокол Диффи-Хеллмана — одно из величайших открытий в криптографии: обмен ключами по открытому каналу, казавшийся невозможным, стал реальностью.

**DH** в конечных полях требует 2048+ бит для безопасности и используется для legacy-совместимости. **ECDHE** на современных кривых — стандарт для TLS, SSH и мессенджеров. **X25519** — рекомендованный выбор для новых систем.

Ключевые принципы:
1. Всегда используйте **Ephemeral DH** (DHE/ECDHE) для Perfect Forward Secrecy
2. DH без аутентификации уязвим к MITM — всегда верифицируйте открытые ключи через сертификаты или другие механизмы
3. X25519 предпочтительнее P-256: быстрее, безопаснее в реализации
4. В TLS 1.3 PFS обязателен — RSA key exchange удалён

---

## Литература и источники

1. Diffie, W., Hellman, M. (1976). *New Directions in Cryptography*. IEEE Transactions on Information Theory, 22(6). https://ee.stanford.edu/~hellman/publications/24.pdf
2. RFC 7748. (2016). *Elliptic Curves for Security (X25519/X448)*. IETF. https://www.rfc-editor.org/rfc/rfc7748
3. RFC 7919. (2016). *Negotiated Finite Field Diffie-Hellman Ephemeral Parameters for TLS*. IETF. https://www.rfc-editor.org/rfc/rfc7919
4. Adrian, D., et al. (2015). *Imperfect Forward Secrecy: How Diffie-Hellman Fails in Practice* (Logjam). https://weakdh.org/
5. Bernstein, D.J. (2006). *Curve25519: new Diffie-Hellman speed records*. https://cr.yp.to/ecdh/curve25519-20060209.pdf
6. Marlinspike, M., Perrin, T. (2016). *The X3DH Key Agreement Protocol*. https://signal.org/docs/specifications/x3dh/
7. RFC 8446. (2018). *The Transport Layer Security (TLS) Protocol Version 1.3*. IETF. https://www.rfc-editor.org/rfc/rfc8446
8. Wikipedia: Diffie-Hellman key exchange. https://en.wikipedia.org/wiki/Diffie%E2%80%93Hellman_key_exchange
9. Wikipedia: Elliptic-curve Diffie-Hellman. https://en.wikipedia.org/wiki/Elliptic-curve_Diffie%E2%80%93Hellman
