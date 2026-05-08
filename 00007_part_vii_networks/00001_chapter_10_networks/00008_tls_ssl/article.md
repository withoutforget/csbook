# TLS/SSL — защищённое соединение

## Введение

Когда вы видите замочек в адресной строке браузера, это означает что соединение защищено TLS. TLS (Transport Layer Security) обеспечивает три свойства: **конфиденциальность** (данные зашифрованы), **целостность** (данные не изменены в пути) и **аутентификацию** (сервер действительно тот, за кого себя выдаёт).

SSL (Secure Sockets Layer) — исторический предшественник TLS, разработанный Netscape в 1994 году. SSL 2.0, SSL 3.0 — давно устаревшие и небезопасные версии. TLS 1.0, 1.1 — также считаются устаревшими. Актуальны только TLS 1.2 (2008) и TLS 1.3 (2018). Тем не менее термин «SSL» до сих пор используется разговорно для обозначения TLS.

Понимание TLS критично для security-aware инженеров: неправильная конфигурация приводит к уязвимостям (POODLE, BEAST, HEARTBLEED), а правильная — к защите пользователей от перехвата данных.

---

## 1. Архитектура TLS

TLS работает поверх TCP и под HTTP (или другими протоколами приложений):

```
┌─────────────────────────────────────────┐
│          HTTP, FTP, SMTP, etc.           │
├─────────────────────────────────────────┤
│              TLS Record Protocol         │  ← Шифрование данных
├──────────────┬──────────────────────────┤
│  Handshake   │  Alert   │  Change Cipher │  ← Управляющие протоколы
│  Protocol    │ Protocol │  Spec          │
├─────────────────────────────────────────┤
│                   TCP                   │
└─────────────────────────────────────────┘
```

**Record Protocol**: разбивает данные на записи (records), сжимает (опционально), аутентифицирует (MAC), шифрует.

**Handshake Protocol**: согласование алгоритмов, аутентификация, установка ключей.

---

## 2. TLS 1.2 Handshake

### 2.1 Полный handshake

```
Клиент                                          Сервер
  |                                               |
  |---------- ClientHello ----------------------->|
  |   TLS version, random, cipher suites,         |
  |   compression methods, extensions             |
  |                                               |
  |<--------- ServerHello ------------------------|
  |   Chosen cipher suite, random, session_id     |
  |                                               |
  |<--------- Certificate ------------------------|
  |   Server's X.509 certificate (public key)     |
  |                                               |
  |<--------- ServerKeyExchange (опц.) ----------|
  |   DH parameters (если DHE/ECDHE)             |
  |                                               |
  |<--------- ServerHelloDone --------------------|
  |                                               |
  |---------- ClientKeyExchange ----------------->|
  |   Pre-master secret (encrypted with pub key)  |
  |   или DH public key                           |
  |                                               |
  |---------- ChangeCipherSpec ------------------>|
  |   "Переключаюсь на согласованный cipher"      |
  |                                               |
  |---------- Finished --------------------------->|
  |   PRF(master_secret, "client finished", hash) |
  |                                               |
  |<--------- ChangeCipherSpec -------------------|
  |<--------- Finished ----------------------------|
  |                                               |
  |============== Application Data ===============|
```

Полный handshake = **2 RTT** (+ TCP handshake = 3 RTT итого).

### 2.2 Что происходит при каждом шаге

**ClientHello**: клиент предлагает:
- Список поддерживаемых cipher suites (в порядке предпочтения)
- Случайное число (Client Random, 32 байта)
- Session ID (для возобновления сессии)
- Extensions: SNI, ALPN, EtherType

**ServerHello**: сервер выбирает:
- Один cipher suite из предложенных
- Server Random (32 байта)
- Session ID

**Certificate**: цепочка сертификатов — от leaf до CA (не включая root).

**ServerKeyExchange**: нужен при DHE/ECDHE. Сервер отправляет свои DH параметры, подписанные private key сертификата.

**ClientKeyExchange**: при RSA key exchange — pre-master secret зашифрован public key сервера. При DHE — public часть DH.

**Finished**: первое зашифрованное сообщение. Содержит хэш всего handshake — защита от подмены handshake сообщений.

### 2.3 Derivation ключей

Из Client Random, Server Random и pre-master secret вычисляется master secret:

```python
# Упрощённо (не реальный TLS код):
master_secret = PRF(pre_master_secret, 
                    "master secret",
                    client_random + server_random)

# Из master secret получаем:
key_material = PRF(master_secret,
                   "key expansion", 
                   server_random + client_random)

# Делим на ключи:
client_write_MAC_key = key_material[0:mac_length]
server_write_MAC_key = key_material[mac_length:2*mac_length]
client_write_key     = key_material[2*mac_length:2*mac_length+key_length]
server_write_key     = key_material[...]
client_write_IV      = key_material[...]
server_write_IV      = key_material[...]
```

---

## 3. TLS 1.3 — значительное упрощение

### 3.1 Сокращённый handshake (1 RTT)

TLS 1.3 (RFC 8446, 2018) радикально упростил handshake:

```
Клиент                                          Сервер
  |                                               |
  |---------- ClientHello ----------------------->|
  |   key_share (DHE/ECDHE публичная часть)        |
  |   supported_versions, cipher suites           |
  |                                               |
  |<--------- ServerHello ------------------------|
  |   key_share (серверная DHE/ECDHE часть)        |
  |<--------- {Certificate} ----------------------| ← уже зашифровано!
  |<--------- {CertificateVerify} ----------------| ← подпись transcript
  |<--------- {Finished} -------------------------|
  |                                               |
  |---------- {Finished} ------------------------->|
  |                                               |
  |============== Application Data ===============|
```

**1 RTT** против 2 RTT в TLS 1.2. Данные приложения можно отправлять сразу после Finished.

### 3.2 0-RTT (Early Data)

При повторном подключении клиент может отправить данные до завершения handshake:

```
Клиент                                          Сервер
  |---------- ClientHello + Early Data ---------->|
  |           (использует PSK из прошлой сессии)   |
  |<--------- ServerHello + ... ------------------|
  |<--------- {Finished} -------------------------|
  |---------- {Finished} ------------------------->|
  |============== Application Data ===============|
```

**Предупреждение**: 0-RTT не обеспечивает forward secrecy для early data. Уязвим к replay attacks. Использовать только для идемпотентных запросов (GET, не POST с деньгами).

### 3.3 Удалённые в TLS 1.3

| Удалено | Причина |
|---------|---------|
| RSA key exchange | Нет forward secrecy |
| DHE с конкретными группами | Слабые группы |
| RC4, DES, 3DES | Сломаны |
| MD5, SHA-1 в рукопожатии | Слабые хэши |
| Сжатие | CRIME атака |
| Пересогласование (renegotiation) | Сложность и уязвимости |

---

## 4. Cipher Suites

Cipher suite — набор алгоритмов для TLS:

```
TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
│   │          │    │       │   │
│   │          │    │       │   └── Hash (для PRF)
│   │          │    │       └────── Key length
│   │          │    └────────────── Block cipher mode
│   │          └─────────────────── Symmetric cipher
│   └────────────────────────────── Authentication (cert verification)
└────────────────────────────────── Key exchange
```

**TLS 1.2 cipher suites** (современные):
```
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256    ← ECDHE+RSA, AES-128-GCM
TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384  ← ECDHE+ECDSA, AES-256-GCM
TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256  ← для мобильных
```

**TLS 1.3 cipher suites** (только 5 вариантов, без key exchange — он всегда DHE/ECDHE):
```
TLS_AES_256_GCM_SHA384
TLS_CHACHA20_POLY1305_SHA256
TLS_AES_128_GCM_SHA256
TLS_AES_128_CCM_8_SHA256
TLS_AES_128_CCM_SHA256
```

### 4.1 Компоненты cipher suite

**Key Exchange** (обмен ключами):
- `RSA`: клиент шифрует pre-master secret RSA ключом сервера. **Нет forward secrecy** — если серверный приватный ключ скомпрометирован, можно расшифровать старые записанные сессии
- `DHE` (Diffie-Hellman Ephemeral): временные DH ключи. Forward secrecy
- `ECDHE` (Elliptic Curve DHE): то же но с эллиптическими кривыми. Быстрее, меньше ключи

**Forward Secrecy**: свойство, при котором компрометация долгосрочного ключа не позволяет расшифровать прошлые сессии. ECDHE/DHE обеспечивают PFS.

**Authentication**:
- `RSA`: подпись RSA ключом из сертификата
- `ECDSA`: подпись эллиптическими кривыми (быстрее, меньше ключ)

**Bulk cipher**:
- `AES-GCM`: AES с Galois/Counter Mode (AEAD — аутентификация + шифрование)
- `ChaCha20-Poly1305`: для CPU без AES-NI инструкций (мобильные, IoT)

---

## 5. Сертификаты X.509

### 5.1 Структура сертификата

```python
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import ssl
import datetime

def inspect_certificate(hostname: str, port: int = 443) -> dict:
    """Получить и разобрать TLS сертификат."""
    context = ssl.create_default_context()
    
    with socket.create_connection((hostname, port)) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
            cert_der = tls_sock.getpeercert(binary_form=True)
    
    cert = x509.load_der_x509_certificate(cert_der, default_backend())
    
    return {
        'subject': cert.subject.rfc4514_string(),
        'issuer': cert.issuer.rfc4514_string(),
        'valid_from': cert.not_valid_before_utc.isoformat(),
        'valid_until': cert.not_valid_after_utc.isoformat(),
        'serial_number': hex(cert.serial_number),
        'public_key_type': type(cert.public_key()).__name__,
        'san': [
            str(ext.value)
            for ext in cert.extensions
            if ext.oid == x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        ],
        'days_until_expiry': (cert.not_valid_after_utc - 
                              datetime.datetime.now(datetime.timezone.utc)).days
    }

import socket
info = inspect_certificate('google.com')
for key, value in info.items():
    print(f"{key}: {value}")
```

### 5.2 Certificate Chain

```
Root CA Certificate (предустановлен в ОС/браузере)
  └── Intermediate CA Certificate
        └── Server Certificate (leaf)

Browser проверяет:
1. Подпись leaf ← intermediate
2. Подпись intermediate ← root
3. Root находится в trusted store
4. Все сертификаты не просрочены
5. CN/SAN совпадает с hostname
6. Нет в CRL/OCSP (не отозван)
```

### 5.3 Certificate Pinning

Pinning — клиент хранит ожидаемый сертификат/ключ и отклоняет соединения с другим:

```python
import ssl
import hashlib
import socket
import base64

EXPECTED_PINS = {
    'google.com': [
        # SHA-256 хэш Subject Public Key Info
        'YZPgTZ+woNCCCIW3LH2CxQeLzB/1m42QcCTBSdgayjs=',
    ]
}

def connect_with_pinning(hostname: str, port: int = 443):
    context = ssl.create_default_context()
    
    with socket.create_connection((hostname, port)) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
            cert_der = tls_sock.getpeercert(binary_form=True)
            
            # Вычисляем SHA-256 SPKI pin
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            
            cert = x509.load_der_x509_certificate(cert_der, default_backend())
            pub_key_bytes = cert.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            pin = base64.b64encode(hashlib.sha256(pub_key_bytes).digest()).decode()
            
            expected = EXPECTED_PINS.get(hostname, [])
            if expected and pin not in expected:
                raise ssl.SSLError(f"Certificate pinning failure! Got: {pin}")
            
            return tls_sock.read(1024)
```

**Проблема pinning**: при ротации сертификата нужно обновлять клиент. HPKP (HTTP Public Key Pinning) признан плохой идеей для веба — несколько инцидентов где сайты блокировали себя навсегда. Используется в мобильных приложениях.

---

## 6. Практика: openssl и анализ TLS

### 6.1 openssl s_client

```bash
# Подключиться и показать сертификат
openssl s_client -connect google.com:443 -servername google.com

# Вывод включает:
# CONNECTED(00000003)
# depth=2 ... (Root CA)
# depth=1 ... (Intermediate CA)
# depth=0 ... (Server cert)
# ---
# Certificate chain
# ---
# Server certificate
# -----BEGIN CERTIFICATE-----
# ...

# Проверить TLS версию и cipher suite
openssl s_client -connect google.com:443 -tls1_3
openssl s_client -connect google.com:443 -cipher 'ECDHE-RSA-AES256-GCM-SHA384'

# Проверить поддержку TLS версий
for version in tls1 tls1_1 tls1_2 tls1_3; do
    result=$(echo | openssl s_client -connect google.com:443 -$version 2>&1)
    if echo "$result" | grep -q "CONNECTED"; then
        echo "$version: supported"
    else
        echo "$version: NOT supported"
    fi
done

# OCSP stapling проверка
openssl s_client -connect google.com:443 -status

# Certificate expiry
echo | openssl s_client -connect google.com:443 2>/dev/null | \
    openssl x509 -noout -dates
```

### 6.2 Python TLS клиент

```python
import ssl
import socket
import json

def tls_request(hostname: str, port: int = 443, path: str = '/') -> dict:
    """HTTPS запрос с детальной информацией о TLS сессии."""
    
    # Создаём контекст с современными настройками
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2  # Минимум TLS 1.2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_default_certs()
    
    # Опционально: ограничить cipher suites
    # context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:!RC4:!MD5:!aNULL')
    
    with socket.create_connection((hostname, port), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
            # Информация о TLS сессии
            session_info = {
                'tls_version': tls_sock.version(),
                'cipher': tls_sock.cipher(),  # (name, protocol, bits)
                'compression': tls_sock.compression(),
                'peername': tls_sock.getpeername(),
            }
            
            # Информация о сертификате
            cert = tls_sock.getpeercert()
            session_info['cert_subject'] = dict(x[0] for x in cert['subject'])
            session_info['cert_expiry'] = cert['notAfter']
            
            # Делаем HTTP запрос
            request = f"GET {path} HTTP/1.1\r\nHost: {hostname}\r\nConnection: close\r\n\r\n"
            tls_sock.send(request.encode())
            
            response = b''
            while chunk := tls_sock.recv(4096):
                response += chunk
    
    return session_info, response

session_info, response = tls_request('google.com')
print(f"TLS Version: {session_info['tls_version']}")
print(f"Cipher: {session_info['cipher'][0]}")
print(f"Bits: {session_info['cipher'][2]}")
```

---

## 7. Атаки на TLS и защита

| Атака | Версия | Описание | Защита |
|-------|--------|----------|--------|
| POODLE | SSL 3.0, TLS 1.0 | Padding oracle | Отключить SSL 3.0, TLS 1.0 |
| BEAST | TLS 1.0 | CBC атака | TLS 1.1+, ECDHE, RC4→AES-GCM |
| CRIME | TLS 1.0-1.2 | Compression oracle | Отключить сжатие |
| HEARTBLEED | OpenSSL 1.0.1 | Buffer over-read | Обновить OpenSSL |
| FREAK | TLS 1.0-1.2 | Export-grade ключи | Убрать export cipher suites |
| LOGJAM | TLS 1.0-1.2 | Слабые DH параметры | DH ≥ 2048 бит, ECDHE |
| MITM | Все | Поддельный сертификат | Certificate Transparency, CAA |

### 7.1 Certificate Transparency

CT (RFC 6962) — публичный лог всех выданных сертификатов. Браузеры требуют SCT (Signed Certificate Timestamp) — доказательство что сертификат занесён в CT лог:

```bash
# Проверить CT логи для домена:
# https://crt.sh/?q=google.com

# В сертификате должен быть extension:
# X509v3 CT Precertificate SCTs

openssl x509 -in cert.pem -text | grep -A 20 "CT Precertificate"
```

---

## Заключение

TLS — многоуровневый протокол, эволюционировавший через годы атак и исправлений. TLS 1.3 — значительный шаг вперёд: убраны устаревшие алгоритмы, сокращён handshake, добавлен 0-RTT.

**Ключевые выводы**:

1. **TLS 1.2 handshake** = 2 RTT. **TLS 1.3** = 1 RTT. **0-RTT** = 0 дополнительных RTT (но с ограничениями).

2. **Forward Secrecy**: ECDHE/DHE обеспечивают PFS. RSA key exchange — нет. Всегда используйте ECDHE.

3. **Cipher suite**: `TLS_AES_256_GCM_SHA384` (TLS 1.3) или `ECDHE-RSA-AES256-GCM-SHA384` (TLS 1.2).

4. **Проверяйте**: сертификат не просрочен, цепочка доверия, SNI, CT логи.

5. **Минимальная конфигурация**: TLS 1.2+, ECDHE, AES-GCM или ChaCha20-Poly1305. Отключить SSL 2.0, 3.0, TLS 1.0, 1.1.

---

## Литература и источники

1. RFC 8446. The Transport Layer Security (TLS) Protocol Version 1.3. IETF. https://tools.ietf.org/html/rfc8446
2. RFC 5246. The Transport Layer Security (TLS) Protocol Version 1.2. IETF. https://tools.ietf.org/html/rfc5246
3. RFC 6962. Certificate Transparency. IETF. https://tools.ietf.org/html/rfc6962
4. Rescorla, E. (2001). *SSL and TLS: Designing and Building Secure Systems*. Addison-Wesley.
5. Tarreau, W. et al. Recommendations for Secure Use of TLS. https://wiki.mozilla.org/Security/Server_Side_TLS
6. Vaudenay, S. (2002). Security Flaws Induced by CBC Padding. *EUROCRYPT 2002*. (BEAST/POODLE background)
7. OpenSSL Documentation. https://www.openssl.org/docs/
8. Python Documentation. ssl — TLS/SSL wrapper for socket objects. https://docs.python.org/3/library/ssl.html
9. Wikipedia. Transport Layer Security. https://en.wikipedia.org/wiki/Transport_Layer_Security
10. Qualys SSL Labs. SSL/TLS Best Practices. https://www.ssllabs.com/projects/best-practices/
