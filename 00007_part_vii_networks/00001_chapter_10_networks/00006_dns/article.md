# DNS — телефонная книга интернета

## Введение

Каждый раз когда вы открываете браузер и вводите «google.com», происходит невидимый, но критически важный процесс: система должна преобразовать имя в IP-адрес. DNS (Domain Name System) — распределённая база данных, выполняющая это преобразование миллиарды раз в день. Без DNS вам пришлось бы запоминать IP-адреса всех сайтов.

DNS разработал Пол Мокапетрис в 1983 году (RFC 882, 883), заменив простой файл `/etc/hosts`, который рассылался всем узлам ARPANET. Сегодня DNS — одна из наиболее критических инфраструктур интернета: его атаки могут «уронить» целые сегменты сети, а правильная конфигурация критична для производительности и безопасности.

В этой главе мы разберём всю иерархию DNS — от корневых серверов до рекурсивных резолверов, изучим типы записей, механизмы кеширования, DNSSEC и современные разработки DNS over HTTPS/TLS.

---

## 1. Иерархия DNS

### 1.1 Структура доменного пространства имён

DNS — иерархическое дерево. Полное доменное имя (FQDN — Fully Qualified Domain Name) читается справа налево:

```
www.example.com.
│   │       │  └── Root (.) — неявная точка в конце
│   │       └──── TLD (Top-Level Domain)
│   └──────────── Second-Level Domain
└──────────────── Subdomain (Third-Level Domain)
```

**Уровни иерархии**:

```
Root (.) ──→ org ──→ wikipedia ──→ en
          ──→ com ──→ google ──→ mail
          ──→ ru  ──→ yandex ──→ www
          ──→ ...
```

### 1.2 Типы серверов имён

**Root Name Servers** (корневые серверы): 13 наборов серверов (a.root-servers.net через m.root-servers.net), фактически — сотни серверов по всему миру через Anycast. Знают только адреса серверов TLD.

**TLD Name Servers** (серверы верхнего уровня): обслуживают `.com`, `.org`, `.ru` и т.д. Управляются ICANN и региональными регистраторами. Знают адреса authoritative серверов для доменов в своей зоне.

**Authoritative Name Servers** (авторитетные серверы): финальный ответ. Для `example.com` — это серверы, у которых есть реальная запись об `example.com`. Обычно их минимум два (primary + secondary) для отказоустойчивости.

**Recursive Resolvers** (рекурсивные резолверы): сервер, который делает всю работу по разрешению имён от имени клиента. Ваш домашний роутер, 8.8.8.8 (Google), 1.1.1.1 (Cloudflare).

---

## 2. Процесс разрешения имён

### 2.1 Рекурсивный vs итерационный запрос

**Рекурсивный запрос**: клиент просит резолвер «найди мне ответ». Резолвер делает всю работу.

**Итерационный запрос**: каждый сервер отвечает «я не знаю, спроси вон того» — референс к следующему серверу.

На практике: клиент → рекурсивный запрос → резолвер → итерационные запросы → ...

```
Клиент                    Recursive       Root        .com TLD    example.com
(192.168.1.100)           Resolver        Server      Server      Authoritative
    |                        |               |            |            |
    |--Query: www.example.com→|               |            |            |
    |                        |--Query: www.example.com→|  |            |
    |                        |               |            |            |
    |                        |←--Referral: .com TLD--|    |            |
    |                        |                        |            |
    |                        |--Query: www.example.com-→|            |
    |                        |                        |            |
    |                        |←------Referral: ns1.example.com-------|
    |                        |                                    |
    |                        |--Query: www.example.com----------→|
    |                        |                                    |
    |                        |←---------Answer: 93.184.216.34----|
    |                        |                                    |
    |←--Answer: 93.184.216.34|
```

### 2.2 TTL и кеширование

**TTL** (Time To Live) — время в секундах, на которое запись кешируется резолвером. Баланс:
- **Маленький TTL** (60-300с): быстрое обновление (для failover, миграции), но больше запросов
- **Большой TTL** (3600-86400с): меньше запросов, быстрее ответ, но медленное обновление

```bash
# Проверить TTL записи
dig www.example.com
# www.example.com.   3600  IN  A  93.184.216.34
#                    ^^^^
#                    TTL = 3600 секунд = 1 час

# Следить за уменьшением TTL в кеше:
dig @8.8.8.8 www.example.com +noall +answer  # Первый запрос: 3600
# Подождать 10 секунд
dig @8.8.8.8 www.example.com +noall +answer  # Второй: 3590
```

---

## 3. Типы DNS записей

| Тип | Полное название | Описание | Пример |
|-----|----------------|----------|--------|
| A | Address | IPv4 адрес | `example.com → 93.184.216.34` |
| AAAA | IPv6 Address | IPv6 адрес | `example.com → 2606:2800::1` |
| CNAME | Canonical Name | Алиас для другого имени | `www → example.com` |
| MX | Mail Exchange | Почтовый сервер | `example.com → 10 mail.example.com` |
| NS | Name Server | Авторитетный сервер | `example.com → ns1.example.com` |
| TXT | Text | Произвольный текст | SPF, DKIM, domain verification |
| SRV | Service | Местонахождение сервиса | `_http._tcp.example.com → 10 0 80 www` |
| PTR | Pointer | Обратный DNS (IP → имя) | `34.216.184.93.in-addr.arpa → example.com` |
| SOA | Start of Authority | Метаданные зоны | Serial, refresh, retry, expire |
| CAA | Certification Authority Auth | Разрешённые CA для SSL | `example.com → letsencrypt.org` |

### 3.1 A и AAAA записи

```bash
# Запрос A записи
dig A example.com
# example.com.  86400  IN  A  93.184.216.34

# Запрос AAAA (IPv6)
dig AAAA google.com
# google.com.  298  IN  AAAA  2a00:1450:4010:c0b::66

# Запрос обоих типов
dig example.com ANY
```

### 3.2 CNAME — алиасы

```bash
# www часто является CNAME
dig www.example.com
# www.example.com.  3600  IN  CNAME  example.com.
# example.com.      86400  IN  A     93.184.216.34

# Важно: CNAME нельзя использовать для домена верхнего уровня (apex domain)
# example.com НЕ МОЖЕТ быть CNAME — ломает MX, NS записи
# Решение: ALIAS/ANAME запись (не стандарт, реализация у разных DNS-провайдеров)
```

### 3.3 MX — почтовые серверы

```bash
dig MX gmail.com
# gmail.com.  3600  IN  MX  5 gmail-smtp-in.l.google.com.
# gmail.com.  3600  IN  MX  10 alt1.gmail-smtp-in.l.google.com.
# Число = приоритет (меньше = выше приоритет)
```

### 3.4 TXT — многоцелевые записи

```bash
# SPF (Sender Policy Framework) — авторизованные серверы отправки почты
dig TXT example.com
# "v=spf1 include:_spf.google.com ~all"

# DKIM — подпись почты
dig TXT default._domainkey.example.com
# "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA..."

# DMARC — политика обработки почты
dig TXT _dmarc.example.com
# "v=DMARC1; p=reject; rua=mailto:dmarc@example.com"

# Верификация домена (Google Search Console, etc.)
# "google-site-verification=abc123..."
```

### 3.5 SRV — обнаружение сервисов

```bash
# Формат: _service._proto.domain  →  priority weight port target
dig SRV _http._tcp.example.com
# _http._tcp.example.com  300  IN  SRV  10 5 80 www.example.com.

# Kubernetes использует SRV для service discovery:
dig SRV _mysql._tcp.default.svc.cluster.local
```

### 3.6 PTR — обратный DNS

```bash
# PTR запись: IP → hostname
# IP адрес записывается в обратном порядке в домене in-addr.arpa

dig -x 8.8.8.8
# Эквивалентно: dig PTR 8.8.8.8.in-addr.arpa
# 8.8.8.8.in-addr.arpa.  21599  IN  PTR  dns.google.

# IPv6 обратный DNS:
dig -x 2001:4860:4860::8888
# Использует домен ip6.arpa
```

---

## 4. Инструменты DNS диагностики

### 4.1 dig — основной инструмент

```bash
# Базовый запрос
dig google.com

# Конкретный тип записи
dig MX google.com
dig AAAA google.com

# Запрос к конкретному DNS серверу
dig @8.8.8.8 google.com
dig @1.1.1.1 google.com  # Cloudflare

# Трассировка разрешения (итерационный вручную)
dig +trace google.com

# Краткий вывод
dig +short google.com

# Без рекурсии (спросить authoritative напрямую)
dig +norec @ns1.google.com google.com

# Проверка DNSSEC
dig +dnssec google.com

# Запрос за определённое время (таймаут)
dig +time=2 +tries=1 google.com
```

### 4.2 nslookup

```bash
# Простые запросы
nslookup google.com
nslookup -type=MX google.com
nslookup -type=NS google.com

# Интерактивный режим
nslookup
> server 8.8.8.8
> set type=MX
> gmail.com
```

### 4.3 DNS в Python

```python
import dns.resolver
import dns.reversename
import socket

def dns_lookup_all(domain: str) -> dict:
    """Получить все основные DNS записи для домена."""
    results = {}
    
    record_types = ['A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME']
    
    for rtype in record_types:
        try:
            answers = dns.resolver.resolve(domain, rtype)
            results[rtype] = [str(rdata) for rdata in answers]
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, 
                dns.resolver.NoNameservers):
            pass
    
    return results

def reverse_dns(ip: str) -> str:
    """Обратный DNS lookup."""
    try:
        reverse_name = dns.reversename.from_address(ip)
        answer = dns.resolver.resolve(reverse_name, 'PTR')
        return str(answer[0])
    except Exception:
        return None

def check_spf(domain: str) -> str:
    """Получить SPF запись."""
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        for rdata in answers:
            txt = str(rdata).strip('"')
            if txt.startswith('v=spf1'):
                return txt
    except Exception:
        pass
    return None

# Использование
info = dns_lookup_all('example.com')
for rtype, records in info.items():
    print(f"{rtype}: {records}")

# Без dnspython — стандартная библиотека:
hostname, aliases, ips = socket.gethostbyname_ex('google.com')
print(f"IPs: {ips}")
```

---

## 5. Anycast DNS

Крупные DNS провайдеры используют Anycast: одному IP-адресу соответствуют серверы в сотнях точек присутствия. BGP маршрутизирует запросы к ближайшему:

```
8.8.8.8 анонсируется из:
- Google Moscow PoP → ответит для пользователей России
- Google Frankfurt PoP → ответит для Европы
- Google Silicon Valley PoP → ответит для США

Для пользователя в Москве: RTT к 8.8.8.8 ≈ 5-10мс
Для пользователя в Лондоне: RTT к 8.8.8.8 ≈ 5мс (другой сервер!)
```

```bash
# Проверить откуда приходит ответ:
dig +short hostname.bind chaos txt @8.8.8.8
# lds01 (internal Google identifier)

mtr 8.8.8.8
# Видим путь к ближайшему Anycast PoP
```

---

## 6. DNSSEC

### 6.1 Проблема: DNS Spoofing / Cache Poisoning

Атака Kaminsky (2008): атакующий наполняет кеш DNS резолвера поддельными записями, перенаправляя трафик. Без DNSSEC DNS ответ не аутентифицирован — любой может подделать.

### 6.2 DNSSEC: криптографическая подпись

DNSSEC добавляет цифровые подписи к DNS записям:

```
Иерархия доверия DNSSEC:
Root (.) ← Root зона подписана DNSS Trust Anchor
  ↓
.com ← Подписана ключом .com, доверие через корень
  ↓
example.com ← Подписана ключом example.com, доверие через .com
```

Новые типы записей:
- **DNSKEY**: публичный ключ зоны
- **RRSIG**: цифровая подпись для набора записей
- **DS**: хэш DNSKEY дочерней зоны (связь в иерархии)
- **NSEC/NSEC3**: доказательство отсутствия записи

```bash
# Проверить DNSSEC подписи
dig +dnssec A cloudflare.com
# cloudflare.com.  300  IN  A  104.16.132.229
# cloudflare.com.  300  IN  RRSIG  A 13 2 300 ...

# Проверить цепочку доверия
dig +sigchase +trusted-key=/etc/trusted-key.key cloudflare.com
# Или используем dnssec-verify, delv

delv @8.8.8.8 cloudflare.com A +rtrace
```

---

## 7. DNS over HTTPS (DoH) и DNS over TLS (DoT)

### 7.1 Проблема незащищённого DNS

Классический DNS — plaintext UDP/TCP на порту 53. Уязвим для:
- **Перехвата**: ваш ISP видит все DNS запросы
- **Подмены**: MITM может вернуть поддельный ответ (без DNSSEC)
- **Цензуры**: блокировка запросов на уровне DNS провайдером

### 7.2 DNS over TLS (DoT)

DoT (RFC 7858): DNS поверх TLS, порт 853. Шифрование, но отдельный порт — легко блокируется:

```python
import ssl
import socket
import struct

def dns_over_tls(domain: str, server: str = '1.1.1.1', port: int = 853) -> list:
    """DNS запрос через DoT (Cloudflare 1.1.1.1)."""
    import dns.message
    import dns.query
    
    # dns.query.tls делает всё за нас
    q = dns.message.make_query(domain, dns.rdatatype.A)
    
    with socket.create_connection((server, port)) as sock:
        context = ssl.create_default_context()
        with context.wrap_socket(sock, server_hostname=server) as tls_sock:
            # DNS over TLS добавляет 2-байтовый length prefixed message
            data = q.to_wire()
            tls_sock.send(struct.pack('!H', len(data)) + data)
            
            # Читаем ответ
            length_bytes = tls_sock.recv(2)
            length = struct.unpack('!H', length_bytes)[0]
            response_data = tls_sock.recv(length)
    
    response = dns.message.from_wire(response_data)
    return [str(rr) for rr in response.answer[0] if hasattr(rr, 'address')]
```

### 7.3 DNS over HTTPS (DoH)

DoH (RFC 8484): DNS поверх HTTPS, порт 443. Неотличим от обычного HTTPS трафика:

```python
import requests
import base64
import struct

def dns_over_https(domain: str, server: str = 'https://cloudflare-dns.com/dns-query') -> list:
    """DNS запрос через DoH (Cloudflare)."""
    import dns.message
    
    # Создаём DNS запрос
    q = dns.message.make_query(domain, dns.rdatatype.A)
    wire = q.to_wire()
    
    # GET запрос с base64url кодировкой
    response = requests.get(
        server,
        params={'dns': base64.urlsafe_b64encode(wire).rstrip(b'=').decode()},
        headers={'Accept': 'application/dns-message'}
    )
    
    # Или POST:
    # response = requests.post(
    #     server,
    #     data=wire,
    #     headers={'Content-Type': 'application/dns-message',
    #              'Accept': 'application/dns-message'}
    # )
    
    dns_response = dns.message.from_wire(response.content)
    results = []
    for answer in dns_response.answer:
        for rr in answer:
            if hasattr(rr, 'address'):
                results.append(rr.address)
    return results

# Использование:
ips = dns_over_https('example.com')
print(f"example.com → {ips}")
```

### 7.4 Настройка DoH/DoT в клиентах

```bash
# Firefox: about:preferences → Network Settings → Enable DNS over HTTPS

# Linux systemd-resolved:
# /etc/systemd/resolved.conf
# [Resolve]
# DNS=1.1.1.1#cloudflare-dns.com
# DNSOverTLS=yes

# Перезапуск
systemctl restart systemd-resolved

# Проверка
resolvectl status
```

---

## 8. Проблемы безопасности DNS

### 8.1 DNS Cache Poisoning

```
Атака на рекурсивный резолвер:
1. Атакующий инициирует DNS запрос (например, через свой сайт)
2. Пока резолвер ждёт ответа, атакующий отправляет множество
   поддельных ответов с разными Tx ID
3. Один из Tx ID совпадает → поддельная запись в кеш
4. Следующие пользователи получают поддельный IP

Защита:
- DNSSEC (криптографическая подпись)
- 0x20 encoding (рандомизация регистра, RFC 8145)
- Randomized source port (RFC 5452)
```

### 8.2 DDoS на DNS

DNS серверы — привлекательная цель: положить DNS = положить все сервисы:

```
Dyn DNS атака, октябрь 2016:
- Massive DDoS (Mirai botnet, ~1.2 Тбит/с)
- Положили Dyn DNS провайдера
- Недоступны: Twitter, GitHub, Reddit, Netflix, PayPal, Airbnb...
- Несколько часов для восстановления
```

Защита:
- Anycast (распределение нагрузки)
- Rate limiting
- IP reputation filtering
- Multiple DNS providers (не полагайтесь на одного)

---

## Заключение

DNS — невидимый, но критический сервис интернета. Каждый интернет-запрос начинается с DNS, и его производительность и надёжность напрямую влияют на ваш продукт.

**Ключевые выводы**:

1. **Иерархия**: Root → TLD → Authoritative → Recursive resolver. Каждый уровень знает только «своих».

2. **TTL** — баланс между актуальностью и нагрузкой. Для failover — низкий TTL заранее, для стабильных сервисов — высокий.

3. **Типы записей**: A/AAAA (адреса), CNAME (алиасы), MX (почта), TXT (верификация, SPF/DKIM), SRV (сервисы), PTR (обратный DNS).

4. **DNSSEC** — криптографическая защита от cache poisoning. Реализована у крупных провайдеров.

5. **DoH/DoT** — зашифрованный DNS. DoH удобнее (порт 443), DoT надёжнее (явный протокол).

6. **Anycast** — основа масштабирования DNS. 8.8.8.8 — сотни физических серверов.

---

## Литература и источники

1. RFC 1034. Domain Names - Concepts and Facilities. P. Mockapetris. IETF. https://tools.ietf.org/html/rfc1034
2. RFC 1035. Domain Names - Implementation and Specification. P. Mockapetris. IETF. https://tools.ietf.org/html/rfc1035
3. RFC 4033, 4034, 4035. DNS Security Introduction and Requirements (DNSSEC). IETF. https://tools.ietf.org/html/rfc4033
4. RFC 8484. DNS Queries over HTTPS (DoH). IETF. https://tools.ietf.org/html/rfc8484
5. RFC 7858. Specification for DNS over Transport Layer Security (TLS). IETF. https://tools.ietf.org/html/rfc7858
6. Kaminsky, D. (2008). Black Ops 2008: It's The End of the Cache As We Know It. DEF CON 16. https://www.defcon.org/images/defcon-16/dc16-presentations/defcon-16-kaminsky.pdf
7. Wikipedia. Domain Name System. https://en.wikipedia.org/wiki/Domain_Name_System
8. Cloudflare. Learning DNS. https://www.cloudflare.com/learning/dns/what-is-dns/
9. Krishnaswamy, R. (2015). *DNS and BIND*, 5th Edition. O'Reilly Media.
10. dnspython Documentation. https://www.dnspython.org/
