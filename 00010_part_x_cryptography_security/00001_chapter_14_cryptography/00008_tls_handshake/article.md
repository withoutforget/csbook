# TLS handshake — как собирается защищённое соединение

## Введение

Каждый раз, когда вы открываете страницу по HTTPS, происходит TLS handshake — сложный многошаговый протокол, устанавливающий защищённый канал. За долю секунды клиент и сервер согласовывают криптографические алгоритмы, обмениваются ключами, аутентифицируют сервер через сертификат и устанавливают шифрование для всех последующих данных.

TLS (Transport Layer Security) — это преемник SSL и наиболее широко используемый протокол защиты транспортного уровня. Разница между TLS 1.2 (2008) и TLS 1.3 (2018) огромна: 1.3 значительно быстрее (1-RTT вместо 2-RTT), безопаснее (удалены устаревшие алгоритмы) и требует Perfect Forward Secrecy по умолчанию.

---

## 1. TLS 1.2 Handshake

### Полная схема TLS 1.2

```
Клиент                                              Сервер
  |                                                    |
  |──── ClientHello ───────────────────────────────→  |
  |     (версии TLS, cipher suites, client random)    |
  |                                                    |
  |  ←── ServerHello ──────────────────────────────── |
  |     (выбранная cipher suite, server random)       |
  |  ←── Certificate ───────────────────────────────  |
  |     (сертификат сервера + цепочка)                |
  |  ←── ServerKeyExchange ─────────────────────────  |
  |     (DHE/ECDHE параметры, подписанные сервером)   |
  |  ←── ServerHelloDone ───────────────────────────  |
  |                                                    |
  |──── ClientKeyExchange ──────────────────────────→ |
  |     (ECDHE: client ephemeral public key)          |
  |──── ChangeCipherSpec ───────────────────────────→ |
  |──── Finished (encrypted) ───────────────────────→ |
  |                                                    |
  |  ←── ChangeCipherSpec ───────────────────────── - |
  |  ←── Finished (encrypted) ─────────────────────   |
  |                                                    |
  |════ Зашифрованные данные (HTTP/2, etc.) ═══════   |
```

Этот обмен занимает **2 RTT** (round-trip times) до начала передачи данных.

### ClientHello

Клиент отправляет:
- **Версия TLS:** предлагаемая версия (в TLS 1.2 это "1.2", хотя список версий был в другом поле)
- **Client Random:** 32 байта случайных данных (в т.ч. timestamp в старых реализациях)
- **Session ID:** для возобновления сессии (если есть)
- **Cipher Suites:** список поддерживаемых шифронаборов в порядке предпочтения
- **Extensions:** SNI (Server Name Indication), supported groups, signature algorithms, etc.

```
Пример cipher suite: TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
  - ECDHE: метод обмена ключами (Ephemeral ECDH)
  - RSA: алгоритм аутентификации (RSA сертификат)
  - AES_256_GCM: алгоритм шифрования с режимом GCM
  - SHA384: PRF алгоритм
```

### Master Secret и PRF

После завершения ECDHE обмена обе стороны имеют **pre-master secret**. Из него выводится **master secret**:

```
master_secret = PRF(pre_master_secret,
                    "master secret",
                    ClientHello.random || ServerHello.random)
```

PRF (Pseudorandom Function) в TLS 1.2 — это HMAC-SHA256 или HMAC-SHA384, применённый через конструкцию P_hash.

Из master secret выводятся 4 ключа:
1. Client write MAC key (HMAC для данных от клиента)
2. Server write MAC key (HMAC для данных от сервера)
3. Client write encryption key (симметричный ключ для шифрования данных клиента)
4. Server write encryption key (симметричный ключ для шифрования данных сервера)

---

## 2. TLS 1.3 — революционное упрощение

TLS 1.3 (RFC 8446, 2018) — значительный пересмотр протокола:

### Что удалено в TLS 1.3

| Удалённый элемент     | Причина                           |
|-----------------------|-----------------------------------|
| RSA key exchange      | Нет Forward Secrecy               |
| DHE со слабыми группами| < 2048 бит небезопасно           |
| RC4                   | Взломан                           |
| 3DES                  | SWEET32 атака                     |
| MD5, SHA-1 в хеше подписей| Устаревшие                   |
| CBC mode ciphers      | Lucky13, BEAST, POODLE атаки      |
| Renegotiation         | Уязвимости                        |
| Compression           | CRIME атака                       |
| ChangeCipherSpec      | Избыточно                         |

### TLS 1.3: 1-RTT Handshake

```
Клиент                                              Сервер
  |                                                    |
  |──── ClientHello ───────────────────────────────→  |
  |     (версии, cipher suites, key_share: ECDHE pub) |
  |                                                    |
  |  ←── ServerHello ──────────────────────────────── |
  |     (chosen cipher, key_share: ECDHE pub)         |
  |  ←── {EncryptedExtensions} ────────────────────── | ← шифруется!
  |  ←── {Certificate} ─────────────────────────────  |
  |  ←── {CertificateVerify} ───────────────────────  |
  |  ←── {Finished} ────────────────────────────────  |
  |                                                    |
  |──── {Finished} ─────────────────────────────────→ |
  |──── {HTTP request} ─────────────────────────────→ |
  |                                                    |
  |  ←── {HTTP response} ──────────────────────────── |
```

Теперь **1 RTT** до начала получения данных (против 2 RTT в TLS 1.2). Более того, сертификат и данные приложения шифруются практически сразу.

### Key Schedule в TLS 1.3

TLS 1.3 использует **HKDF** (HMAC-based Key Derivation Function, RFC 5869) для вывода всех ключей в детерминированной иерархии:

```
(EC)DHE → HKDF-Extract → Handshake Secret
                              ↓ HKDF-Expand
              handshake_traffic_secret_c/s (для шифрования handshake)
                              ↓
                          Master Secret
                              ↓ HKDF-Expand
              application_traffic_secret_c/s (для шифрования данных)
              resumption_master_secret (для 0-RTT)
              exporter_master_secret (для экспорта ключей)
```

### Поддерживаемые cipher suites в TLS 1.3

В TLS 1.3 cipher suite описывает только AEAD алгоритм и хеш для HKDF:

| Cipher Suite                        | AEAD          | Hash   |
|-------------------------------------|--------------|--------|
| TLS_AES_128_GCM_SHA256              | AES-128-GCM  | SHA-256|
| TLS_AES_256_GCM_SHA384              | AES-256-GCM  | SHA-384|
| TLS_CHACHA20_POLY1305_SHA256        | ChaCha20-Poly1305 | SHA-256|
| TLS_AES_128_CCM_SHA256              | AES-128-CCM  | SHA-256|
| TLS_AES_128_CCM_8_SHA256            | AES-128-CCM-8| SHA-256|

Метод обмена ключами (ECDHE/DHE) и аутентификация (RSA/ECDSA) теперь определяются отдельно от cipher suite.

---

## 3. 0-RTT Resumption (Early Data)

TLS 1.3 поддерживает **0-RTT** (Zero Round Trip Time): повторное соединение с уже известным сервером позволяет отправить данные приложения уже в первом пакете.

```
Клиент                                              Сервер
  |                                                    |
  |──── ClientHello + Early Data (HTTP запрос) ─────→ |
  |     (using resumption_master_secret из прошлой сессии) |
  |                                                    |
  |  ←── ServerHello + ... + Response ─────────────── |
```

Сервер отдаёт **session ticket** в конце успешного handshake. Клиент сохраняет его и при следующем подключении использует для восстановления сессии.

### Риски 0-RTT: Replay Attack

0-RTT не обеспечивает защиту от **replay атак**: злоумышленник, перехвативший первый пакет с early data, может отправить его повторно.

```
Атака:
1. Клиент отправляет 0-RTT: POST /transfer {"amount": 1000}
2. Злоумышленник копирует этот пакет
3. Повторная отправка → двойное списание?
```

**Решения:**
- Использовать 0-RTT только для идемпотентных запросов (GET, не POST с побочными эффектами)
- Серверная дедупликация (anti-replay tokens)
- TLS 1.3 spec рекомендует ограничение: 0-RTT только для записей типа early_data, ограниченного размера

---

## 4. Record Protocol

После установки ключей TLS использует **Record Protocol** для передачи данных:

### Структура TLS Record

```
TLS Record:
├── ContentType: 1 байт (handshake=22, application_data=23, alert=21)
├── Version: 2 байта (TLS 1.2: 0x0303, TLS 1.3: 0x0303)
├── Length: 2 байта (максимум 2^14 = 16384 байт данных)
└── Fragment: зашифрованные данные
    └── AEAD encrypted: (plaintext || padding)
        + auth_tag (16 байт для AES-GCM/ChaCha20-Poly1305)
```

В TLS 1.3 ContentType в открытом виде всегда `application_data = 23`; реальный тип записи шифруется внутри. Это защищает от анализа типов пакетов.

### Fragmentation

Большие данные разбиваются на TLS records не более 16KB. Это важно для streaming: каждый record расшифровывается независимо.

```python
import ssl
import socket

# Демонстрация TLS информации через Python
def tls_info(hostname: str, port: int = 443) -> dict:
    """Получение информации о TLS соединении"""
    context = ssl.create_default_context()
    
    with socket.create_connection((hostname, port), timeout=5) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            return {
                "version": ssock.version(),
                "cipher": ssock.cipher(),
                "compression": ssock.compression(),
                "peer_cert_subject": dict(ssock.getpeercert()["subject"][0]),
                "peer_cert_issuer": dict(ssock.getpeercert()["issuer"][0]),
                "peer_cert_expires": ssock.getpeercert()["notAfter"],
            }

# Использование (требует интернет)
# info = tls_info("www.google.com")
# print(f"Версия TLS: {info['version']}")  # TLSv1.3
# print(f"Cipher suite: {info['cipher']}")
```

---

## 5. Session Resumption

### Session ID (TLS 1.2)

Сервер сохраняет session state и выдаёт клиенту session ID. При следующем подключении клиент предъявляет ID, сервер восстанавливает состояние и пропускает полный handshake.

**Недостаток:** Сервер должен хранить состояние для каждой активной сессии → проблема масштабирования.

### Session Ticket (TLS 1.2 и 1.3)

Сервер шифрует session state своим секретным ключом и отправляет клиенту в виде **session ticket**. При следующем подключении клиент возвращает ticket, сервер расшифровывает его.

**Преимущество:** Сервер не хранит состояние, всё на клиенте.

**Проблема:** Session ticket ключ — долгосрочный симметричный ключ сервера. Его компрометация позволяет декодировать все session tickets → ослабление Forward Secrecy.

В TLS 1.3 session tickets используются как PSK (Pre-Shared Key), но ключи обновляются чаще и привязаны к конкретным сессиям.

---

## 6. SNI — Server Name Indication

SNI (расширение TLS, RFC 6066) позволяет клиенту указать желаемый hostname в ClientHello, до установки шифрования. Это необходимо для **виртуальных хостов** — один IP, много доменов.

**Проблема:** SNI передаётся в открытом виде, виден пассивному наблюдателю.

**Решение:** **ESNI/ECH** (Encrypted Client Hello, RFC в разработке) — шифрование ClientHello через открытый ключ сервера, опубликованный в DNS HTTPS записи.

```bash
# Проверить ECH поддержку через DNS
dig +short HTTPS cloudflare.com
# 1 . alpn="h2,h3" ipv4hint=104.16.X.X ech=<base64>
```

---

## 7. Атаки на TLS

### BEAST (2011) — CBC в TLS 1.0

Атака на CBC mode в TLS 1.0: предсказуемый IV позволял атакующему с MITM позицией угадывать plaintext.

**Защита:** TLS 1.1+ (непредсказуемый IV) или AEAD cipher suites. В TLS 1.3 CBC удалён.

### CRIME (2012) — Compression

Если TLS compression включён, размер сжатого шифротекста зависит от того, совпадает ли угадываемый текст с уже известными данными → атака на cookie.

**Защита:** Отключить TLS compression (по умолчанию отключено в современных реализациях).

### POODLE (2014) — CBC padding oracle в SSLv3

Атака на SSLv3 CBC padding. Позволяла расшифровать HTTP cookies.

**Защита:** Отключить SSLv3 и TLS 1.0 (что и сделано повсеместно).

### DROWN (2016) — Cross-protocol атака через SSLv2

Сервер, поддерживающий SSLv2 (даже для других портов), позволял атаковать TLS 1.2 RSA key exchange через SSLv2 oracle.

**Защита:** Полностью отключить SSLv2, не использовать RSA ключ для нескольких серверов.

---

## 8. Настройка безопасного TLS-сервера

```python
import ssl
from http.server import HTTPServer, SimpleHTTPRequestHandler

def create_secure_server_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    """Создание безопасного SSL контекста"""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    
    # Загрузка сертификата и ключа
    context.load_cert_chain(cert_file, key_file)
    
    # Минимальная версия TLS 1.2 (лучше 1.3)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    
    # Выбор cipher suites (только сильные)
    context.set_ciphers(
        "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20"
        ":!aNULL:!MD5:!DSS:!RC4"
    )
    
    # Forward Secrecy: предпочитать ECDHE
    context.options |= ssl.OP_CIPHER_SERVER_PREFERENCE
    
    # Отключить сжатие (CRIME attack)
    context.options |= ssl.OP_NO_COMPRESSION
    
    return context
```

### Проверка конфигурации TLS через openssl

```bash
# Какие версии TLS поддерживаются?
openssl s_client -connect server:443 -tls1_3 -brief 2>&1 | head -5
openssl s_client -connect server:443 -tls1_2 -brief 2>&1 | head -5

# Какие cipher suites поддерживаются?
nmap --script ssl-enum-ciphers -p 443 server

# Проверка HSTS
curl -sI https://example.com | grep -i strict-transport

# SSL Labs / testssl.sh
testssl.sh --fast example.com
```

---

## 9. HTTP/2 и TLS

HTTP/2 требует TLS 1.2+ (на практике все браузеры требуют TLS 1.2 с ALPN). ALPN (Application-Layer Protocol Negotiation) — расширение TLS для согласования протокола приложения (h2, http/1.1) в TLS handshake.

**HTTP/3 (QUIC):** работает поверх UDP, использует TLS 1.3 как неотъемлемую часть протокола. QUIC handshake = QUIC transport handshake + TLS 1.3 handshake одновременно, что даёт 1-RTT (или 0-RTT) с нуля.

---

## Заключение

TLS handshake — это элегантная инженерная конструкция, объединяющая все криптографические примитивы: асимметричное шифрование, PKI, ECDH, AEAD шифры, HMAC и KDF.

**TLS 1.2** был хорошим стандартом, но накопил уязвимости из-за поддержки устаревших алгоритмов. **TLS 1.3** решительно очистил протокол:
- Обязательный PFS (только ECDHE/DHE)
- 1-RTT вместо 2-RTT
- Удалены небезопасные алгоритмы
- Шифрование сертификата
- Более безопасный key schedule (HKDF)

Для практики: настраивайте серверы на TLS 1.2+, предпочтительно только TLS 1.3. Используйте инструменты testssl.sh и Mozilla SSL Config Generator для правильной конфигурации.

---

## Литература и источники

1. RFC 8446. (2018). *The Transport Layer Security (TLS) Protocol Version 1.3*. IETF. https://www.rfc-editor.org/rfc/rfc8446
2. RFC 5246. (2008). *The Transport Layer Security (TLS) Protocol Version 1.2*. IETF. https://www.rfc-editor.org/rfc/rfc5246
3. RFC 5869. (2010). *HMAC-based Extract-and-Expand Key Derivation Function (HKDF)*. IETF. https://www.rfc-editor.org/rfc/rfc5869
4. Rescorla, E. (2018). *The Transport Layer Security (TLS) Protocol Version 1.3 (tutorial)*. https://tlswg.org/tls13-spec/draft-ietf-tls-rfc8446bis.html
5. Mozilla SSL Configuration Generator. https://ssl-config.mozilla.org/
6. testssl.sh. *Testing TLS/SSL Encryption*. https://testssl.sh/
7. Bhargavan, K., et al. (2016). *DROWN: Breaking TLS Using SSLv2*. https://drownattack.com/
8. Möller, B., Duong, T., Kotowicz, K. (2014). *This POODLE bites*. https://www.openssl.org/~bodo/ssl-poodle.pdf
9. Wikipedia: Transport Layer Security. https://en.wikipedia.org/wiki/Transport_Layer_Security
10. Beurdouche, B., et al. (2015). *A Messy State of the Union: Taming the Composite State Machines of TLS*. IEEE S&P 2015.
