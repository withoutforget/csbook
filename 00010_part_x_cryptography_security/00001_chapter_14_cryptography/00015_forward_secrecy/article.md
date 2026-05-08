# Forward Secrecy — защита прошлого трафика

## Введение

Представьте: ваш сервер работал несколько лет, обрабатывая HTTPS-трафик. Затем злоумышленник украл ваш долгосрочный RSA ключ. Если в вашем TLS не было Perfect Forward Secrecy — весь записанный трафик за все годы теперь может быть расшифрован. Каждый HTTPS-запрос, каждая транзакция, каждое сообщение.

**Perfect Forward Secrecy (PFS)** — свойство протокола, при котором компрометация долгосрочного ключа не позволяет расшифровать прошлые сессии. Это достигается через **эфемерные** (временные) ключи: для каждой сессии генерируются новые ключи ECDH, которые уничтожаются после завершения сессии. Долгосрочный ключ используется только для аутентификации, но не для шифрования.

В этой статье мы разберём механизм PFS, протокол Double Ratchet из Signal (обеспечивающий ещё более сильные гарантии), HKDF для вывода ключей и практическое применение.

---

## 1. Без Forward Secrecy: уязвимость статического RSA

### RSA Key Exchange в TLS 1.2 (небезопасный режим)

В старом TLS 1.2 с RSA key exchange:

```
Клиент → Сервер: ClientHello
Сервер → Клиент: ServerHello + Certificate (RSA публичный ключ)
Клиент: Генерирует pre_master_secret (48 байт случайных)
Клиент → Сервер: Encrypted pre_master_secret (RSA-PKCS1-v1.5)
Обе стороны: Выводят master_secret из pre_master_secret
```

**Проблема:** Весь секрет сессии = RSA-зашифрованный pre_master_secret. Если долгосрочный RSA-ключ сервера скомпрометирован сейчас или в будущем — любой, кто записал трафик, может расшифровать все прошлые сессии.

```python
# Иллюстрация проблемы (НЕ реальный TLS код)
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
import os

# Серверный долгосрочный ключ (используется годами)
server_static_key = rsa.generate_private_key(65537, 2048)
server_static_pub = server_static_key.public_key()

# Первая сессия (год 1)
pre_master_1 = os.urandom(48)
# Клиент шифрует pre_master_secret статическим публичным ключом сервера
encrypted_1 = server_static_pub.encrypt(
    pre_master_1,
    padding.PKCS1v15()
)

# Вторая сессия (год 2)
pre_master_2 = os.urandom(48)
encrypted_2 = server_static_pub.encrypt(pre_master_2, padding.PKCS1v15())

# Атакующий записывает encrypted_1 и encrypted_2 (год 1-2)
# Год 3: сервер взломан, получен server_static_key

# Расшифровка ВСЕГО прошлого трафика!
recovered_1 = server_static_key.decrypt(encrypted_1, padding.PKCS1v15())
recovered_2 = server_static_key.decrypt(encrypted_2, padding.PKCS1v15())

print(f"Год 1 pre_master_secret восстановлен: {pre_master_1 == recovered_1}")
print(f"Год 2 pre_master_secret восстановлен: {pre_master_2 == recovered_2}")
print("Весь трафик за 2 года расшифрован!")
```

---

## 2. ECDHE — эфемерные ключи и PFS

### Принцип Perfect Forward Secrecy

С ECDHE (Ephemeral ECDH):

1. Сервер для каждой сессии генерирует **новую** пару ключей ECDH
2. Долгосрочный ключ подписывает только эфемерный публичный ключ (аутентификация)
3. Симметричный ключ сессии = результат ECDHE
4. После сессии эфемерный ключ **удаляется**

```python
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

class ForwardSecureServer:
    """Сервер с Perfect Forward Secrecy"""
    
    def __init__(self):
        # Долгосрочный ключ — только для аутентификации
        self.long_term_key = Ed25519PrivateKey.generate()
        self.long_term_pub = self.long_term_key.public_key()
    
    def start_session(self) -> dict:
        """Начало новой сессии: генерация ЭФЕМЕРНЫХ ключей"""
        # Новые ключи для каждой сессии!
        self.ephemeral_priv = X25519PrivateKey.generate()
        eph_pub = self.ephemeral_priv.public_key()
        
        # Подписываем эфемерный публичный ключ долгосрочным ключом
        eph_pub_bytes = eph_pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )
        signature = self.long_term_key.sign(eph_pub_bytes)
        
        return {
            "ephemeral_pub": eph_pub_bytes,
            "signature": signature,
            "long_term_pub": self.long_term_pub.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw
            )
        }
    
    def complete_session(self, client_ephemeral_pub_bytes: bytes) -> bytes:
        """Завершение handshake, получение общего секрета"""
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        
        client_pub = X25519PublicKey.from_public_bytes(client_ephemeral_pub_bytes)
        
        # ECDHE
        shared_secret = self.ephemeral_priv.exchange(client_pub)
        
        # Вывод ключа сессии
        session_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"session_key"
        ).derive(shared_secret)
        
        # КРИТИЧЕСКИ ВАЖНО: удаляем эфемерный ключ!
        del self.ephemeral_priv
        self.ephemeral_priv = None
        
        return session_key

class ForwardSecureClient:
    """Клиент с верификацией PFS сервера"""
    
    def connect(self, server_params: dict) -> tuple:
        """Подключение к серверу с проверкой PFS"""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        
        # Верификация подписи эфемерного ключа
        server_lt_pub = Ed25519PublicKey.from_public_bytes(
            server_params["long_term_pub"]
        )
        server_lt_pub.verify(
            server_params["signature"],
            server_params["ephemeral_pub"]
        )
        print("Аутентификация сервера успешна!")
        
        # Генерация клиентских эфемерных ключей
        client_eph_priv = X25519PrivateKey.generate()
        client_eph_pub = client_eph_priv.public_key()
        
        # ECDHE
        server_eph_pub = X25519PublicKey.from_public_bytes(
            server_params["ephemeral_pub"]
        )
        shared_secret = client_eph_priv.exchange(server_eph_pub)
        
        # Вывод ключа сессии
        session_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"session_key"
        ).derive(shared_secret)
        
        # Удаляем эфемерный ключ
        del client_eph_priv
        
        client_eph_pub_bytes = client_eph_pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )
        
        return client_eph_pub_bytes, session_key

# Демонстрация PFS
server = ForwardSecureServer()
client = ForwardSecureClient()

# Сессия 1
server_params1 = server.start_session()
client_pub1, client_key1 = client.connect(server_params1)
server_key1 = server.complete_session(client_pub1)
assert client_key1 == server_key1
print(f"Сессия 1 ключ: {client_key1.hex()[:16]}...")

# Сессия 2 (новые эфемерные ключи!)
server_params2 = server.start_session()
client_pub2, client_key2 = client.connect(server_params2)
server_key2 = server.complete_session(client_pub2)
assert client_key2 == server_key2
print(f"Сессия 2 ключ: {client_key2.hex()[:16]}...")

print(f"Ключи сессий разные: {client_key1 != client_key2}")

# Даже при компрометации долгосрочного ключа сервера —
# прошлые сессии нельзя расшифровать (ключи удалены)
```

---

## 3. HKDF — вывод ключей сессий

HKDF (HMAC-based Key Derivation Function, RFC 5869) — стандартный способ вывода нескольких ключей из одного shared secret:

```python
from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand
from cryptography.hazmat.primitives import hashes
import os

def derive_session_keys(shared_secret: bytes, client_hello: bytes, server_hello: bytes) -> dict:
    """
    Вывод всех ключей сессии из shared_secret (как в TLS 1.3)
    """
    # Extract: смешиваем shared_secret с солью
    salt = client_hello + server_hello  # Уникальна для каждой сессии
    
    # HKDF-Extract: prk = HMAC(salt, shared_secret)
    import hmac
    import hashlib
    prk = hmac.new(salt, shared_secret, hashlib.sha256).digest()
    
    def expand(prk: bytes, info: bytes, length: int) -> bytes:
        """HKDF-Expand"""
        return HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=None,
            info=info
        ).derive(prk)
    
    # Выводим разные ключи для разных целей
    client_write_key = expand(prk, b"client write key", 32)
    server_write_key = expand(prk, b"server write key", 32)
    client_write_iv  = expand(prk, b"client write IV",  12)
    server_write_iv  = expand(prk, b"server write IV",  12)
    
    return {
        "client_write_key": client_write_key,
        "server_write_key": server_write_key,
        "client_write_iv": client_write_iv,
        "server_write_iv": server_write_iv
    }

shared_secret = os.urandom(32)
client_hello = os.urandom(32)
server_hello = os.urandom(32)

keys = derive_session_keys(shared_secret, client_hello, server_hello)
print(f"Client write key: {keys['client_write_key'].hex()[:16]}...")
print(f"Server write key: {keys['server_write_key'].hex()[:16]}...")
```

---

## 4. Signal Protocol — Double Ratchet Algorithm

Signal Protocol обеспечивает более сильные гарантии чем PFS: не только **Forward Secrecy** (прошлые сообщения защищены при компрометации), но и **Break-in Recovery** (future secrecy/backward secrecy): компрометация одного сообщения не компрометирует все будущие.

### X3DH — Extended Triple Diffie-Hellman

Инициализация Signal Session:

```
Долгосрочные ключи Боба: IK_B (Identity Key)
Подписанные прекеи: SPK_B (Signed PreKey)  
Одноразовые прекеи: OPK_B (One-Time PreKey)

Алиса хочет написать Бобу:
1. Генерирует эфемерный ключ EK_A
2. 4 DH операции:
   DH1 = DH(IK_A, SPK_B)
   DH2 = DH(EK_A, IK_B)
   DH3 = DH(EK_A, SPK_B)
   DH4 = DH(EK_A, OPK_B)  // опционально
3. Master secret = KDF(DH1 || DH2 || DH3 || DH4)
```

Каждый раз используется новый одноразовый прекей → каждая сессия уникальна.

### Double Ratchet

После X3DH инициализации Double Ratchet управляет ключами для каждого сообщения:

```python
import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import Optional

def hkdf(input_key: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """Упрощённый HKDF"""
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(input_key)

def kdf_rk(rk: bytes, dh_output: bytes) -> tuple:
    """KDF для Root Key (Ratchet Key)"""
    output = hkdf(dh_output, rk, b"WhisperRatchet", 64)
    return output[:32], output[32:]  # (new_root_key, chain_key)

def kdf_ck(ck: bytes) -> tuple:
    """KDF для Chain Key"""
    message_key = hmac.new(ck, b'\x01', hashlib.sha256).digest()
    new_chain_key = hmac.new(ck, b'\x02', hashlib.sha256).digest()
    return new_chain_key, message_key  # (new_chain_key, message_key)

@dataclass
class RatchetState:
    """Состояние Double Ratchet"""
    DHs: bytes  # Текущая пара ключей DH (отправляющий)
    DHr: Optional[bytes]  # Публичный ключ DH получателя
    RK: bytes   # Root Key
    CKs: Optional[bytes]  # Chain Key отправки
    CKr: Optional[bytes]  # Chain Key получения
    Ns: int = 0  # Счётчик отправленных сообщений
    Nr: int = 0  # Счётчик полученных сообщений
    PN: int = 0  # Предыдущий размер цепочки
    MKSKIPPED: dict = field(default_factory=dict)  # Пропущенные ключи

class DoubleRatchet:
    """
    Упрощённая реализация Double Ratchet Algorithm
    (Signal Protocol / WhatsApp)
    """
    
    @staticmethod
    def init_alice(sk: bytes, bob_public_key: bytes) -> 'RatchetState':
        """Инициализация для Алисы (инициатора)"""
        # Генерируем начальную пару DH ключей
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey, X25519PublicKey
        )
        
        alice_ratchet_priv = X25519PrivateKey.generate()
        alice_ratchet_pub = alice_ratchet_priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        
        # DH с ключом Боба
        bob_pub = X25519PublicKey.from_public_bytes(bob_public_key)
        dh_out = alice_ratchet_priv.exchange(bob_pub)
        
        # Инициализация Root Key
        rk, cks = kdf_rk(sk, dh_out)
        
        alice_dh_bytes = alice_ratchet_priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption()
        )
        
        return RatchetState(
            DHs=alice_dh_bytes,
            DHr=bob_public_key,
            RK=rk,
            CKs=cks,
            CKr=None
        )
    
    @staticmethod
    def ratchet_encrypt(state: RatchetState, plaintext: bytes) -> tuple:
        """Шифрование с продвижением симметричного ratchet"""
        # Продвигаем цепочку ключей
        state.CKs, mk = kdf_ck(state.CKs)
        
        # Шифруем сообщение ключом mk
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        ciphertext = AESGCM(mk).encrypt(nonce, plaintext, None)
        
        header = {
            "dh": state.DHs[-8:].hex(),  # Упрощение: часть public key
            "n": state.Ns,
            "pn": state.PN
        }
        state.Ns += 1
        
        return header, nonce, ciphertext

# Демонстрация Double Ratchet принципа
print("=== Double Ratchet: защита каждого сообщения ===")

# Начальный общий секрет (из X3DH)
initial_secret = os.urandom(32)

# Алиса инициирует сессию
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
bob_ratchet_priv = X25519PrivateKey.generate()
bob_ratchet_pub = bob_ratchet_priv.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw
)

state = DoubleRatchet.init_alice(initial_secret, bob_ratchet_pub)

# Каждое сообщение использует уникальный ключ
for i in range(3):
    msg = f"Сообщение {i+1}".encode()
    header, nonce, ct = DoubleRatchet.ratchet_encrypt(state, msg)
    print(f"Сообщение {i+1}: ключ производный от цепочки #{header['n']}")
    print(f"  Шифротекст: {ct.hex()[:16]}...")
```

### Свойства Double Ratchet

| Свойство            | Без DR       | С Double Ratchet   |
|--------------------|-------------|-------------------|
| Forward Secrecy    | Нет          | Да                |
| Break-in Recovery  | Нет          | Да                |
| Per-message keys   | Нет          | Да                |
| Out-of-order msgs  | Проблема     | Поддерживается    |
| Key compromise     | Все сообщения| Только текущие    |

---

## 5. Forward Secrecy в TLS 1.3

TLS 1.3 делает PFS обязательным. Cipher suites без PFS (RSA key exchange) удалены.

Все поддерживаемые key exchange в TLS 1.3:
- `x25519` (рекомендован)
- `secp256r1` (P-256)
- `secp384r1` (P-384)
- `x448`
- `secp521r1`
- `ffdhe2048`, `ffdhe3072` (finite field DH)
- Hybrid PQC: `X25519Kyber768`

```bash
# Проверка Forward Secrecy для сайта
openssl s_client -connect example.com:443 -status 2>&1 | \
  grep -E "Protocol|Cipher|Ephemeral"

# Проверить что используется ECDHE (не RSA key exchange)
# В TLS 1.3 - всегда ECDHE

# Через nmap
nmap --script ssl-enum-ciphers -p 443 example.com 2>/dev/null | \
  grep -E "FS|forward|ECDHE|DHE"
```

---

## 6. Backward Secrecy (Break-in Recovery)

PFS защищает прошлые сообщения. Но есть и противоположная задача: если ключ скомпрометирован **сейчас** — защита **будущих** сообщений после «исцеления» системы.

**Signal Double Ratchet** обеспечивает это: DH ratchet периодически обновляет корневой ключ через новый DH обмен. После нескольких сообщений, ключ сессии полностью обновляется от компрометированного состояния.

```
Компрометация: атакующий знает состояние ключей в момент T

С Double Ratchet:
T: компрометация
T+1: DH ratchet обновляет Root Key через ECDH
     → новый Chain Key, никак не связанный с T
T+1+: Атакующий не знает новый DH ключ → не может расшифровать
```

---

## 7. Проверка Forward Secrecy в продакшене

```python
import ssl
import socket

def check_forward_secrecy(hostname: str, port: int = 443) -> dict:
    """Проверка поддержки Forward Secrecy"""
    context = ssl.create_default_context()
    
    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cipher_info = ssock.cipher()
                cipher_name = cipher_info[0] if cipher_info else ""
                tls_version = ssock.version()
                
                # Признаки Forward Secrecy в cipher name
                has_fs = any(x in cipher_name for x in ['ECDHE', 'DHE', 'ECDH_anon'])
                # TLS 1.3 всегда имеет FS
                if tls_version == 'TLSv1.3':
                    has_fs = True
                
                return {
                    "hostname": hostname,
                    "tls_version": tls_version,
                    "cipher": cipher_name,
                    "forward_secrecy": has_fs,
                    "status": "OK" if has_fs else "WARNING: No FS!"
                }
    except Exception as e:
        return {"hostname": hostname, "error": str(e)}

# Проверка нескольких серверов
servers = ["www.google.com", "www.github.com"]
for server in servers:
    result = check_forward_secrecy(server)
    fs = result.get("forward_secrecy", False)
    version = result.get("tls_version", "?")
    cipher = result.get("cipher", "?")
    print(f"{server}: TLS={version}, FS={fs}, cipher={cipher}")
```

---

## Заключение

Forward Secrecy — обязательная характеристика безопасных современных протоколов. Компрометация долгосрочных ключей не должна раскрывать прошлую коммуникацию.

**Ключевые выводы:**
1. **TLS 1.3 обязывает PFS** — RSA key exchange удалён. Обновите сервер, если используете TLS 1.2 с не-DHE cipher suites
2. **ECDHE X25519** — стандартный выбор для TLS
3. **Double Ratchet (Signal)** — усиление: каждое сообщение имеет свой ключ + Break-in Recovery
4. **HKDF** — правильный способ вывода нескольких ключей из shared secret
5. **Проверяйте** ваши серверы на наличие FS (nmap, ssllabs.com, testssl.sh)
6. **Ephemeral ключи уничтожайте** немедленно после использования — не логируйте, не сохраняйте

---

## Литература и источники

1. RFC 8446. (2018). *The Transport Layer Security (TLS) Protocol Version 1.3*. IETF. https://www.rfc-editor.org/rfc/rfc8446
2. Marlinspike, M., Perrin, T. (2016). *The Double Ratchet Algorithm*. https://signal.org/docs/specifications/doubleratchet/
3. Marlinspike, M., Perrin, T. (2016). *The X3DH Key Agreement Protocol*. https://signal.org/docs/specifications/x3dh/
4. RFC 5869. (2010). *HMAC-based Key Derivation Function (HKDF)*. IETF. https://www.rfc-editor.org/rfc/rfc5869
5. Diffie, W., Van Oorschot, P., Wiener, M. (1992). *Authentication and Authenticated Key Exchanges*. Designs, Codes and Cryptography. (Forward Secrecy concept)
6. Cohn-Gordon, K., et al. (2019). *A Formal Security Analysis of the Signal Messaging Protocol*. IEEE European Symposium on Security and Privacy.
7. Rescorla, E. (2018). *The TLS 1.3 Security Analysis*. https://www.rfc-editor.org/rfc/rfc8446#appendix-E
8. Wikipedia: Forward secrecy. https://en.wikipedia.org/wiki/Forward_secrecy
9. Wikipedia: Double Ratchet Algorithm. https://en.wikipedia.org/wiki/Double_Ratchet_Algorithm
10. SSL Labs. *SSL Server Test*. https://www.ssllabs.com/ssltest/
