# PKI и сертификаты X.509

## Введение

Асимметричная криптография решает задачу шифрования и подписи, но оставляет открытым вопрос: как убедиться, что открытый ключ, который вы получили, действительно принадлежит тому, кому вы доверяете? Когда вы заходите на сайт вашего банка, браузер получает открытый ключ — но откуда он знает, что это именно ключ банка, а не ключ злоумышленника?

Ответ — **PKI (Public Key Infrastructure)**: инфраструктура открытых ключей, основанная на иерархии доверия. Сертификаты X.509 — это стандартизированные цифровые документы, связывающие открытый ключ с личностью (доменным именем, организацией, пользователем) и подписанные доверенным удостоверяющим центром (CA, Certificate Authority).

Понимание PKI критически важно для любого разработчика, работающего с HTTPS, микросервисами, Code Signing или VPN.

---

## 1. Проблема доверия публичным ключам

### Сценарий без PKI

Допустим, вы хотите зашифровать сообщение для Алисы. Вы нашли её «открытый ключ» в интернете. Но:
- Откуда вы знаете, что это ключ именно Алисы?
- Что если злоумышленник подменил ключ на свой?
- Как установить связь «ключ → личность»?

Без PKI возможны два подхода:
1. **Web of Trust (GPG/PGP):** участники лично верифицируют ключи друг друга и подписывают их. Хорошо работает для небольших сообществ, не масштабируется для интернета.
2. **PKI с Certificate Authority:** иерархия доверенных организаций, подписывающих ключи.

### Certificate Authority (CA)

CA — это организация, которой мы доверяем удостоверять чужие ключи. CA:
1. Проверяет личность заявителя (что domain.com действительно принадлежит этой организации)
2. Подписывает сертификат (связку открытый ключ + личность) своим закрытым ключом
3. Все, кто доверяет CA, могут верифицировать подписанные ею сертификаты

Браузеры и ОС поставляются с предустановленным **хранилищем доверенных корневых CA** (~100-150 CA организаций).

---

## 2. Иерархия доверия

### Root CA → Intermediate CA → Leaf Certificate

Иерархия PKI для HTTPS:

```
Root CA (корневой)
  ├── Offline, хранится в защищённых HSM
  ├── Самоподписан (issuer == subject)
  └── Подписывает только Intermediate CA

    Intermediate CA (промежуточный)
      ├── Связан с Root CA через цепочку подписей
      ├── Используется для подписи конечных сертификатов
      └── При компрометации: отозвать можно быстрее, чем Root CA

        Leaf Certificate (конечный, сертификат сайта)
          ├── Содержит открытый ключ сервера
          ├── Subject: domain.com
          └── Подписан Intermediate CA
```

**Почему несколько уровней?**
- Root CA хранится офлайн в сверхзащищённых условиях (ceremony с видеозаписью, несколько ответственных лиц, физически изолированные машины)
- Компрометация Root CA — катастрофа (нужно обновлять ОС/браузеры по всему миру)
- Intermediate CA можно оперативно отозвать при компрометации

### Примеры публичных CA

| CA                  | Рыночная доля | Особенности               |
|---------------------|--------------|--------------------------|
| Let's Encrypt       | ~50%         | Бесплатный, автоматический (ACME)|
| DigiCert            | ~20%         | Enterprise, EV сертификаты|
| Sectigo (Comodo)    | ~15%         | Широкий ассортимент       |
| GlobalSign          | ~5%          | Enterprise                |
| Amazon Trust Services| ~5%         | AWS интеграция            |

---

## 3. Структура сертификата X.509

Сертификат X.509 v3 содержит:

```
X.509 Certificate
├── tbsCertificate (to-be-signed)
│   ├── Version: 3
│   ├── SerialNumber: 12345678 (уникальный у CA)
│   ├── Signature Algorithm: sha256WithRSAEncryption
│   ├── Issuer: C=US, O=DigiCert Inc, CN=DigiCert TLS RSA SHA256 2020 CA1
│   ├── Validity:
│   │   ├── Not Before: 2024-01-01 00:00:00
│   │   └── Not After: 2025-01-01 23:59:59
│   ├── Subject: C=RU, O=My Company LLC, CN=mysite.com
│   ├── Subject Public Key Info:
│   │   ├── Algorithm: id-ecPublicKey (P-256)
│   │   └── Public Key: 0430a1b2... (65 bytes)
│   └── Extensions (v3):
│       ├── Subject Alternative Names: DNS:mysite.com, DNS:www.mysite.com
│       ├── Key Usage: digitalSignature, keyEncipherment
│       ├── Extended Key Usage: serverAuth, clientAuth
│       ├── CRL Distribution Points: http://crl.digicert.com/...
│       ├── Authority Information Access (OCSP): http://ocsp.digicert.com
│       ├── Certificate Policies: ...
│       └── Basic Constraints: CA=FALSE
└── Signature: (hash(tbsCertificate) подписан закрытым ключом CA)
```

### Чтение сертификата в Python

```python
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
import datetime

# Загрузка сертификата из PEM
with open("/etc/ssl/certs/ca-certificates.crt", "rb") as f:
    pem_data = f.read()

# Парсинг первого сертификата из bundle
from cryptography.x509 import load_pem_x509_certificate
# Берём первый сертификат из файла
import re
pem_certs = re.findall(b"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", pem_data, re.DOTALL)

if pem_certs:
    cert = x509.load_pem_x509_certificate(pem_certs[0])
    
    print(f"Subject: {cert.subject.rfc4514_string()}")
    print(f"Issuer: {cert.issuer.rfc4514_string()}")
    print(f"Serial: {cert.serial_number}")
    print(f"Valid from: {cert.not_valid_before_utc}")
    print(f"Valid until: {cert.not_valid_after_utc}")
    print(f"Signature alg: {cert.signature_algorithm_oid.dotted_string}")
    
    # Extensions
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        print(f"SANs: {[name.value for name in san.value]}")
    except x509.ExtensionNotFound:
        pass
    
    try:
        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        print(f"Is CA: {bc.value.ca}")
    except x509.ExtensionNotFound:
        pass
```

### Проверка сертификата сайта через openssl

```bash
# Получить сертификат сайта
echo | openssl s_client -connect google.com:443 -servername google.com 2>/dev/null | \
  openssl x509 -noout -text | head -50

# Проверить цепочку
echo | openssl s_client -connect google.com:443 -showcerts 2>/dev/null | \
  grep "subject\|issuer"

# Проверить срок действия
echo | openssl s_client -connect google.com:443 2>/dev/null | \
  openssl x509 -noout -dates

# Показать Subject Alternative Names
echo | openssl s_client -connect google.com:443 2>/dev/null | \
  openssl x509 -noout -ext subjectAltName
```

---

## 4. Цепочка сертификатов и её верификация

### Chain of Trust

При TLS handshake сервер отправляет цепочку сертификатов: свой leaf + intermediate(s).

```
Клиент проверяет:
1. Leaf cert подписан Intermediate CA? → verify(Intermediate.pubkey, Leaf.signature) = OK?
2. Intermediate CA подписан Root CA? → verify(Root.pubkey, Intermediate.signature) = OK?
3. Root CA есть в доверенном хранилище? → YES (встроен в ОС/браузер)
4. Все сертификаты в цепочке не истекли?
5. Все сертификаты не отозваны?
6. Subject/SAN в Leaf сертификате совпадает с hostname?
```

```python
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509

def verify_cert_chain(cert: x509.Certificate, issuer_cert: x509.Certificate) -> bool:
    """Проверка, что cert подписан issuer_cert"""
    try:
        issuer_pub_key = issuer_cert.public_key()
        issuer_pub_key.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),  # Для RSA
            cert.signature_hash_algorithm
        )
        return True
    except Exception:
        return False

def check_cert_validity(cert: x509.Certificate) -> bool:
    """Проверка срока действия"""
    now = datetime.datetime.now(datetime.timezone.utc)
    return cert.not_valid_before_utc <= now <= cert.not_valid_after_utc

def check_hostname(cert: x509.Certificate, hostname: str) -> bool:
    """Проверка hostname против Subject Alternative Names"""
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns_names = san.value.get_values_for_type(x509.DNSName)
        
        for name in dns_names:
            if name.startswith("*."):
                # Wildcard: *.example.com совпадает с www.example.com, но не с sub.www.example.com
                suffix = name[1:]  # .example.com
                if hostname.endswith(suffix) and "." not in hostname[:-len(suffix)]:
                    return True
            elif name == hostname:
                return True
    except x509.ExtensionNotFound:
        pass
    return False
```

---

## 5. Отзыв сертификатов: CRL и OCSP

### CRL — Certificate Revocation List

CA публикует список серийных номеров отозванных сертификатов в формате CRL:

```bash
# Скачать CRL для сертификата
openssl x509 -in cert.pem -noout -text | grep crlDistributionPoints -A3
# Скачать и проверить
curl -s http://crl.digicert.com/DigiCertTLSRSASHA2562020CA1-4.crl -o /tmp/crl.der
openssl crl -inform DER -in /tmp/crl.der -noout -text | head -30
```

**Недостатки CRL:**
- Файл CRL может быть большим (десятки МБ для крупных CA)
- Кеширование → задержка обновления
- Клиент должен скачивать и проверять весь список

### OCSP — Online Certificate Status Protocol

OCSP (RFC 6960) — запрос статуса конкретного сертификата у OCSP responder:

```
Клиент → OCSP запрос: SerialNumber + IssuerNameHash + IssuerKeyHash
Сервер → OCSP ответ: good / revoked / unknown + timestamp + подпись
```

**OCSP Stapling:** сервер кешировал OCSP ответ и отправляет его клиенту в TLS handshake, избавляя клиента от отдельного запроса.

```python
import ssl
import socket

def check_ocsp_stapling(hostname: str, port: int = 443) -> None:
    """Проверка OCSP stapling для сайта"""
    context = ssl.create_default_context()
    
    with socket.create_connection((hostname, port)) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            # Получаем stapled OCSP response
            ocsp_response = ssock.get_raw_ocsp_response()
            if ocsp_response:
                print(f"OCSP stapling поддерживается: {len(ocsp_response)} байт")
            else:
                print("OCSP stapling не поддерживается")

# Пример (требует интернет-соединения)
# check_ocsp_stapling("www.google.com")
```

---

## 6. Certificate Transparency (CT Logs)

Certificate Transparency (RFC 9162) — это публичный, append-only журнал всех выданных сертификатов. Введён Google в 2013 году после инцидента с DigiNotar.

**Как работает:**
1. CA перед выдачей сертификата отправляет его в CT log
2. CT log возвращает SCT (Signed Certificate Timestamp) — доказательство включения
3. Сертификат содержит SCT в расширении
4. Браузер (Chrome) требует наличия минимум 2 SCT от разных логов

**Зачем это нужно:**
- Любой может следить за выдачей сертификатов для своих доменов
- Мошеннически выданный сертификат будет виден в логах
- Инструменты мониторинга: crt.sh, Google Certificate Transparency

```python
import requests

def search_ct_logs(domain: str) -> list:
    """Поиск всех сертификатов для домена в CT логах через crt.sh"""
    url = f"https://crt.sh/?q={domain}&output=json"
    try:
        r = requests.get(url, timeout=10)
        certs = r.json()
        return [
            {
                "id": c["id"],
                "logged_at": c["entry_timestamp"],
                "not_after": c["not_after"],
                "cn": c["common_name"],
                "issuer": c["issuer_name"]
            }
            for c in certs[:10]  # Первые 10
        ]
    except Exception as e:
        return [{"error": str(e)}]

# Использование (требует интернет)
# certs = search_ct_logs("example.com")
# for cert in certs:
#     print(cert)
```

---

## 7. Let's Encrypt и протокол ACME

Let's Encrypt — CA, основанный в 2015 году, предоставляющий бесплатные DV (Domain Validation) сертификаты с 90-дневным сроком действия и полной автоматизацией через ACME.

### Протокол ACME (RFC 8555)

```
1. Клиент → ACME сервер: запрос авторизации для example.com
2. ACME сервер → клиент: challenge (http-01, dns-01, или tls-alpn-01)
3. http-01 challenge: поместить токен по URL http://example.com/.well-known/acme-challenge/{token}
4. ACME сервер проверяет URL → домен подтверждён
5. Клиент → генерирует CSR (Certificate Signing Request) с публичным ключом
6. ACME сервер → выдаёт подписанный сертификат
```

**Certbot** — наиболее популярный ACME клиент:
```bash
# Получение сертификата для nginx
certbot --nginx -d example.com -d www.example.com

# Standalone (certbot сам открывает порт 80)
certbot certonly --standalone -d example.com

# DNS challenge (для wildcard)
certbot certonly --dns-cloudflare -d *.example.com

# Автоматическое обновление
certbot renew --dry-run
```

---

## 8. Атаки на PKI и инциденты

### DigiNotar (2011)

Нидерландский CA DigiNotar был взломан, атакующие выпустили ~500 поддельных сертификатов, включая `*.google.com`. Использовались для перехвата трафика иранских пользователей Gmail. DigiNotar был немедленно исключён из доверенных CA во всех браузерах и обанкротился.

**Урок:** Один скомпрометированный CA может атаковать любой домен.

### Comodo 2011

Взломан аффилиат Comodo, выпущены сертификаты для Google, Yahoo, Skype, Mozilla. Обнаружены быстро благодаря публичным ключам (Certificate Transparency ещё не существовал).

### Мошенническое использование промежуточных CA

Symantec выдавал тестовые сертификаты без согласия владельцев доменов. Google Chrome начал постепенно удалять доверие к Symantec CA, что в конечном счёте привело к продаже CA бизнеса DigiCert.

### Реакция на инциденты

- Certificate Transparency (CT Logs) — мониторинг всех выданных сертификатов
- Accountability требования — CA/Browser Forum правила
- HPKP (HTTP Public Key Pinning) — был введён, но затем отменён из-за риска самоблокировки
- CAA DNS записи — указывают, каким CA разрешено выдавать сертификаты для домена

```bash
# CAA записи в DNS
dig CAA example.com

# Результат:
# example.com. 3600 IN CAA 0 issue "letsencrypt.org"
# example.com. 3600 IN CAA 0 issuewild ";"  # запрет wildcard
```

---

## 9. Создание собственного CA (для внутреннего использования)

```bash
# Создание корневого CA
openssl genrsa -out ca_key.pem 4096
openssl req -x509 -new -nodes -key ca_key.pem -sha256 -days 3650 \
  -subj "/C=RU/O=MyCompany/CN=MyCompany Root CA" \
  -out ca_cert.pem

# Создание промежуточного CA
openssl genrsa -out intermediate_key.pem 2048
openssl req -new -key intermediate_key.pem \
  -subj "/C=RU/O=MyCompany/CN=MyCompany Intermediate CA" \
  -out intermediate_csr.pem
openssl x509 -req -in intermediate_csr.pem -CA ca_cert.pem -CAkey ca_key.pem \
  -CAcreateserial -out intermediate_cert.pem -days 1825 -sha256

# Создание сертификата сервера
openssl genrsa -out server_key.pem 2048
openssl req -new -key server_key.pem \
  -subj "/C=RU/O=MyCompany/CN=myservice.internal" \
  -out server_csr.pem

# Создание файла расширений
cat > server_ext.cnf << EOF
[req]
req_extensions = v3_req
[v3_req]
subjectAltName = DNS:myservice.internal, DNS:localhost, IP:127.0.0.1
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF

openssl x509 -req -in server_csr.pem -CA intermediate_cert.pem \
  -CAkey intermediate_key.pem -CAcreateserial \
  -out server_cert.pem -days 365 -sha256 -extfile server_ext.cnf

# Создание chain bundle для сервера
cat server_cert.pem intermediate_cert.pem > server_chain.pem

# Верификация цепочки
openssl verify -CAfile ca_cert.pem -untrusted intermediate_cert.pem server_cert.pem
```

---

## 10. mTLS — взаимная аутентификация

В микросервисной архитектуре серверы могут требовать клиентский сертификат (mTLS):

```python
import ssl

# Сервер требует клиентский сертификат
server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
server_context.load_cert_chain('server_cert.pem', 'server_key.pem')
server_context.load_verify_locations('ca_cert.pem')
server_context.verify_mode = ssl.CERT_REQUIRED  # mTLS!

# Клиент предоставляет свой сертификат
client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
client_context.load_cert_chain('client_cert.pem', 'client_key.pem')
client_context.load_verify_locations('ca_cert.pem')
```

---

## Заключение

PKI — это инфраструктура доверия, которая делает возможным безопасный интернет. Сертификаты X.509 связывают открытые ключи с идентичностями через иерархию удостоверяющих центров.

Ключевые выводы:
1. **Root CA** хранится строго офлайн; компрометация катастрофична
2. **Цепочка сертификатов** должна проверяться до доверенного Root CA
3. **OCSP Stapling** предпочтительнее CRL — быстрее и приватнее
4. **Certificate Transparency** обязателен для публичных CA с 2018 года
5. **Let's Encrypt + ACME** позволяют автоматизировать весь жизненный цикл сертификатов
6. Для внутренних систем создавайте собственный CA, для публичных — Let's Encrypt или коммерческий CA
7. **mTLS** для сервис-к-сервис аутентификации в микросервисах

---

## Литература и источники

1. RFC 5280. (2008). *Internet X.509 Public Key Infrastructure Certificate and CRL Profile*. IETF. https://www.rfc-editor.org/rfc/rfc5280
2. RFC 6960. (2013). *X.509 Internet Public Key Infrastructure Online Certificate Status Protocol — OCSP*. IETF. https://www.rfc-editor.org/rfc/rfc6960
3. RFC 9162. (2021). *Certificate Transparency Version 2.0*. IETF. https://www.rfc-editor.org/rfc/rfc9162
4. RFC 8555. (2019). *Automatic Certificate Management Environment (ACME)*. IETF. https://www.rfc-editor.org/rfc/rfc8555
5. Sleevi, R. (2017). *Distrust of Symantec PKI*. Google Chrome Blog. https://security.googleblog.com/2017/09/chromes-plan-to-distrust-symantec.html
6. Let's Encrypt. *How it works*. https://letsencrypt.org/how-it-works/
7. crt.sh Certificate Transparency Search. https://crt.sh/
8. CA/Browser Forum. *Baseline Requirements*. https://cabforum.org/
9. Wikipedia: X.509. https://en.wikipedia.org/wiki/X.509
10. Wikipedia: Certificate authority. https://en.wikipedia.org/wiki/Certificate_authority
