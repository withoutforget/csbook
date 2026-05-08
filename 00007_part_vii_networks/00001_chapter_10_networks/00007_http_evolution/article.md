# HTTP/1.1, HTTP/2, HTTP/3 (QUIC)

## Введение

HTTP (HyperText Transfer Protocol) — протокол прикладного уровня, на котором построен весь веб. С момента появления в 1991 году он прошёл путь от простейшего текстового протокола до сложной бинарной системы с мультиплексированием, серверным push и встроенным шифрованием.

Каждое поколение HTTP решало ограничения предыдущего. HTTP/1.0 устанавливал новое TCP-соединение на каждый запрос. HTTP/1.1 добавил keep-alive, но head-of-line blocking остался. HTTP/2 решил HOL blocking через мультиплексирование, но столкнулся с HOL blocking на уровне TCP. HTTP/3 радикально решил эту проблему, перейдя с TCP на QUIC (поверх UDP).

Понимание эволюции HTTP важно не только для исторического контекста: разные версии активно используются сегодня, их характеристики влияют на производительность ваших приложений, и выбор правильного протокола — инженерное решение с реальными последствиями.

---

## 1. HTTP/1.0 и HTTP/1.1

### 1.1 HTTP/1.0: одно соединение — один запрос

HTTP/1.0 (RFC 1945, 1996): каждый запрос — отдельное TCP соединение:

```
TCP connect → HTTP Request → HTTP Response → TCP close
```

Для страницы с 30 ресурсами (HTML + 20 картинок + 9 JS/CSS файлов):
- $30 \times$ TCP handshake ($3 \times$ RTT каждый)
- $30 \times$ HTTP request-response
- $30 \times$ TCP teardown

Даже при RTT = 50 мс: $30 \times 3 \times 50$ мс = 4.5 секунды только на handshakes!

### 1.2 HTTP/1.1: keep-alive и pipelining

HTTP/1.1 (RFC 2616, 1997 → RFC 7230-7235, 2014) ввёл:

**Keep-alive (persistent connections)**: одно TCP соединение для нескольких запросов. Заголовок `Connection: keep-alive` (по умолчанию в HTTP/1.1).

```
TCP connect
  → Request 1 → Response 1
  → Request 2 → Response 2
  → Request 3 → Response 3
TCP close (или timeout)
```

**Pipelining**: отправка нескольких запросов без ожидания ответов:

```
Request 1 → Request 2 → Request 3 (не ждём ответа)
                               ↓ ↓ ↓
                   Response 1 → Response 2 → Response 3
```

**Почему pipelining не работал**: **Head-of-Line Blocking (HOL)**. Ответы должны приходить в том же порядке, что запросы. Если Response 1 медленный (большой файл, долгий расчёт) — все остальные ждут, хотя давно готовы:

```
Request:  [1] → [2] → [3]

Server:   Response 1 (медленный) ─────────────────→
          Response 2 (быстрый)                     ─→
          Response 3 (быстрый)                       ─→

Client:   [1 .................... ] → [2] → [3]
               Ждём 1, хотя 2 и 3 готовы!
```

Результат: pipelining отключён в большинстве браузеров. Браузеры открывают 6 параллельных TCP соединений на домен — «domain sharding».

### 1.3 Структура HTTP/1.1 сообщений

**Request**:
```http
GET /path?query=value HTTP/1.1
Host: www.example.com
User-Agent: Mozilla/5.0
Accept: text/html,application/xhtml+xml
Accept-Encoding: gzip, deflate, br
Connection: keep-alive
Cookie: session=abc123

[Body для POST/PUT]
```

**Response**:
```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Length: 1234
Cache-Control: max-age=3600
ETag: "abc123"
Vary: Accept-Encoding
Connection: keep-alive

<!DOCTYPE html>...
```

**Коды статусов**:
| Диапазон | Значение | Примеры |
|---------|---------|---------|
| 1xx | Informational | 101 Switching Protocols |
| 2xx | Success | 200 OK, 201 Created, 204 No Content |
| 3xx | Redirect | 301 Moved Permanently, 304 Not Modified |
| 4xx | Client Error | 400 Bad Request, 401, 403, 404, 429 |
| 5xx | Server Error | 500 Internal Server Error, 502 Bad Gateway, 503 |

---

## 2. HTTP/2

### 2.1 Мультиплексирование и binary framing

HTTP/2 (RFC 7540, 2015) полностью переработал транспортный уровень:

**Бинарный протокол**: вместо текста — бинарные фреймы. Эффективнее парсить, меньше ошибок:

```
HTTP/1.1 (текст):           HTTP/2 (бинарные фреймы):
GET /path HTTP/1.1           ┌──────────────────────────┐
Host: example.com            │ Length │ Type │ Flags │ ID│
Accept: text/html            │  0x...  │ 0x01 │ 0x25  │ 1 │
...                          ├──────────────────────────┤
                             │         Payload          │
                             └──────────────────────────┘
```

**Streams и мультиплексирование**: одно TCP соединение содержит множество streams. Каждый stream — независимый «виртуальный канал» для одного запрос-ответ. Нет HOL blocking на уровне приложения:

```
Одно TCP соединение HTTP/2:

Stream 1: [Request 1] ──── [Response 1] (медленный)
Stream 3: [Request 2] - [Response 2] (быстрый, приходит раньше)
Stream 5: [Request 3] -- [Response 3]
Stream 7: [Request 4] [Response 4]

Клиент получает ответы по мере готовности — нет очереди!
```

Фреймы разных streams перемежаются (interleaved):
```
Поток байт по TCP: [S1:HEADERS][S3:HEADERS][S1:DATA][S3:DATA][S5:HEADERS]...
```

### 2.2 Header Compression (HPACK)

HTTP/1.1: заголовки — текст, повторяются в каждом запросе. Для 30 запросов: `Cookie: <большой>` $\times$ 30 = много лишних данных.

HTTP/2 HPACK (RFC 7541): таблица часто используемых заголовков + delta compression:

```python
# HPACK упрощённо:
# Статическая таблица: 61 предопределённый заголовок
# [:method GET], [:status 200], [content-type text/html], ...

# Динамическая таблица: заголовки которые видели раньше
# Если заголовок уже в таблице → передаём только индекс (1 байт)
# Если новый → добавляем в таблицу, передаём значение

# Пример:
# Request 1: Передаём полный User-Agent (добавляем в таблицу)
# Request 2: Передаём только индекс "62" (ссылка на таблицу)
# Экономия: 50-90% размера заголовков
```

### 2.3 Server Push

Сервер может отправить ресурсы клиенту без запроса, если предвидит нужду:

```
Браузер: GET /index.html
Сервер:  ← index.html
         ← (push) style.css     // Сервер знает: HTML нуждается в CSS
         ← (push) script.js     // Отправляем заранее

Браузер получает CSS и JS раньше, чем HTML их запросит
```

На практике Server Push оказался менее полезным, чем ожидалось:
- Сервер не знает что уже в кеше браузера
- Может «толкнуть» то что уже закешировано
- HTTP/3 получит `103 Early Hints` как замену

### 2.4 HTTP/2 HOL Blocking на уровне TCP

HTTP/2 решил HOL blocking на уровне приложения, но остался уязвим к HOL blocking TCP:

```
Stream 1: frame1 frame2 frame3
Stream 3: frame4 frame5 frame6

TCP пакет потерян (содержал frame1):
Все фреймы (1-6) застревают — TCP ждёт повторной передачи frame1!

Даже frame4, frame5 Stream 3 (независимый) — ждут!
```

На сетях с потерями: HTTP/2 хуже HTTP/1.1 (несколько параллельных TCP лучше одного с losses).

---

## 3. HTTP/3 и QUIC

### 3.1 QUIC — переосмысление транспорта

QUIC (Quick UDP Internet Connections) изначально разработан Google (2012), стандартизирован IETF (RFC 9000, 2021). HTTP/3 (RFC 9114, 2022) — HTTP поверх QUIC.

**Фундаментальное изменение**: QUIC работает поверх UDP, а не TCP:

```
HTTP/1.1, HTTP/2:               HTTP/3:
┌──────────────────┐           ┌──────────────────┐
│   HTTP/1.1 или   │           │      HTTP/3       │
│     HTTP/2       │           ├──────────────────┤
├──────────────────┤           │      QUIC         │
│       TLS        │           │  (includes TLS)   │
├──────────────────┤           ├──────────────────┤
│       TCP        │           │       UDP         │
├──────────────────┤           ├──────────────────┤
│       IP         │           │       IP          │
└──────────────────┘           └──────────────────┘
```

### 3.2 Преимущества QUIC

**Нет HOL blocking**: QUIC реализует мультиплексирование потоков на транспортном уровне. Потеря пакета блокирует только один stream, а не все:

```
Stream 1: frame1 frame2
Stream 3: frame3 frame4

UDP пакет потерян (frame1):
QUIC ретранслирует frame1 только для Stream 1
Stream 3 продолжает работать! ← Ключевое отличие от TCP
```

**Быстрое установление соединения (0-RTT)**:

```
TCP + TLS 1.2:               TCP + TLS 1.3:           QUIC:
TCP SYN →                    TCP SYN →                UDP + Initial →
← SYN-ACK                   ← SYN-ACK                ← Handshake
→ ACK                        → Client Hello           → 0-RTT Request
→ Client Hello               ← Server Hello           ← Response
← Server Hello               (TLS 1.3: 1 RTT)         
→ Certificate Verify                                  
← Change Cipher Spec         Total: 1.5 RTT           Total: 1 RTT
→ HTTP Request               (vs 2.5 для TLS 1.2)     (0-RTT: 0 RTT!)
2.5 RTT                      
```

При повторном подключении (0-RTT): клиент сохраняет session ticket → первый пакет содержит данные приложения.

**Connection Migration**: QUIC connection привязан не к IP:Port, а к Connection ID. При смене сети (WiFi → 4G) соединение продолжается без переустановки:

```
Телефон переключился WiFi→4G:
TCP: соединение разорвано, нужно reconnect + повторить запросы
QUIC: Connection ID не изменился → продолжаем seamlessly
```

**Встроенный TLS 1.3**: QUIC не может работать без шифрования. TLS интегрирован в протокол, нет возможности отключить.

### 3.3 QPACK — сжатие заголовков

HTTP/3 использует QPACK вместо HPACK. HPACK не работает с QUIC (динамическая таблица предполагает порядок — QUIC не гарантирует порядок):

- QPACK: одна декодирующая таблица, но с explicit sequencing
- Отдельные QUIC streams для кодирования/декодирования таблицы

---

## 4. Сравнение версий

| Характеристика | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---------------|---------|--------|--------|
| Протокол | Текстовый | Бинарный | Бинарный |
| Транспорт | TCP | TCP | QUIC (UDP) |
| Мультиплексирование | Нет (domain sharding) | Да | Да |
| HOL Blocking | Да (app + TCP) | Нет app, TCP есть | Нет |
| Header Compression | Нет | HPACK | QPACK |
| TLS | Опционально | Опционально | Обязательно |
| Connection setup | TCP: 1 RTT, TLS: +1-2 RTT | То же | 1 RTT (0-RTT повторно) |
| Server Push | Нет | Да | Нет (103 Early Hints) |
| Connection Migration | Нет | Нет | Да |
| Deployment | Везде | ~97% браузеров | ~90% браузеров (2024) |

### 4.1 Распространённость (2024)

```bash
# Проверить какой HTTP использует сайт:
curl -s -I --http2 https://google.com | head -1
# HTTP/2 200

curl -s -I --http3 https://cloudflare.com | head -1
# HTTP/3 200

# Проверить поддержку HTTP/3 (Alt-Svc заголовок):
curl -I https://cloudflare.com 2>&1 | grep alt-svc
# alt-svc: h3=":443"; ma=86400
# h3 = HTTP/3, ma = max-age
```

---

## 5. Практика: Python примеры

### 5.1 HTTP/1.1 запрос

```python
import http.client
import socket

def http11_request(host: str, path: str = '/', use_ssl: bool = False) -> dict:
    """HTTP/1.1 запрос через http.client."""
    if use_ssl:
        import ssl
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(host, context=context)
    else:
        conn = http.client.HTTPConnection(host)
    
    try:
        conn.request('GET', path, headers={
            'User-Agent': 'Python-http-client/1.0',
            'Accept': 'text/html',
            'Connection': 'keep-alive'
        })
        response = conn.getresponse()
        
        return {
            'status': response.status,
            'reason': response.reason,
            'headers': dict(response.getheaders()),
            'body_length': len(response.read())
        }
    finally:
        conn.close()

result = http11_request('example.com', '/')
print(f"Status: {result['status']} {result['reason']}")
print(f"Server: {result['headers'].get('Server')}")
```

### 5.2 HTTP/2 с httpx

```python
import asyncio
import httpx
import time

async def http2_requests():
    """HTTP/2 с мультиплексированием через httpx."""
    
    urls = [
        'https://httpbin.org/delay/1',
        'https://httpbin.org/delay/1',
        'https://httpbin.org/delay/1',
        'https://httpbin.org/delay/1',
        'https://httpbin.org/delay/1',
    ]
    
    # HTTP/2 клиент
    async with httpx.AsyncClient(http2=True) as client:
        start = time.time()
        
        # Параллельные запросы через одно HTTP/2 соединение
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start
        
        for r in responses:
            print(f"Status: {r.status_code}, HTTP version: {r.http_version}")
        
        print(f"\nTotal time: {elapsed:.2f}s")
        # HTTP/2: ~1с (мультиплексирование)
        # HTTP/1.1: ~5с (последовательно) или ~2с (6 параллельных соединений)

asyncio.run(http2_requests())
```

### 5.3 QUIC/HTTP/3 с aioquic

```python
# Требует: pip install aioquic
import asyncio
from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import HeadersReceived, DataReceived

async def http3_request(host: str, port: int = 443, path: str = '/'):
    """HTTP/3 запрос через QUIC."""
    config = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN)
    config.verify_mode = None  # Для тестирования, в prod не использовать!
    
    async with connect(host, port, configuration=config) as connection:
        http = H3Connection(connection._quic)
        
        # Отправляем HTTP/3 запрос
        stream_id = connection._quic.get_next_available_stream_id()
        http.send_headers(
            stream_id=stream_id,
            headers=[
                (b':method', b'GET'),
                (b':scheme', b'https'),
                (b':authority', host.encode()),
                (b':path', path.encode()),
                (b'user-agent', b'aioquic'),
            ]
        )
        connection._quic.send_stream_data(stream_id, b'', end_stream=True)
        
        # Ждём ответа
        response_headers = {}
        response_body = b''
        
        # Читаем события...
        return response_headers, response_body
```

---

## 6. Оптимизация HTTP производительности

### 6.1 Кеширование

```http
# Cache-Control директивы
Cache-Control: max-age=3600          # Кешировать 1 час
Cache-Control: no-cache              # Можно кешировать, но проверять с сервером
Cache-Control: no-store              # Не кешировать
Cache-Control: private               # Только в браузерном кеше
Cache-Control: public, max-age=31536000, immutable  # Долгое кеширование (контент с хэшем)

# Условные запросы (не перекачивать если не изменился)
Last-Modified: Wed, 21 Oct 2024 07:28:00 GMT
ETag: "abc123def456"

# Клиент при повторном запросе:
If-Modified-Since: Wed, 21 Oct 2024 07:28:00 GMT
If-None-Match: "abc123def456"

# Если не изменился: 304 Not Modified (без тела)
```

### 6.2 Connection управление

```python
# Правильно: переиспользуем сессию (keep-alive)
import requests

session = requests.Session()  # Один pool соединений
session.headers.update({'User-Agent': 'MyApp/1.0'})

urls = ['https://api.example.com/users', 
        'https://api.example.com/orders',
        'https://api.example.com/products']

# Все запросы идут через существующие соединения
for url in urls:
    response = session.get(url)

# Неправильно: новое соединение на каждый запрос
for url in urls:
    response = requests.get(url)  # Создаёт новую сессию!
```

---

## Заключение

Эволюция HTTP отражает непрерывную борьбу с одной проблемой — latency. Каждое поколение решало конкретный bottleneck своего времени.

**Ключевые выводы**:

1. **HTTP/1.1**: keep-alive решил проблему overhead соединений. Pipelining сломан из-за HOL blocking. Браузеры используют 6 параллельных соединений как обходной путь.

2. **HTTP/2**: бинарный протокол + мультиплексирование устранили HOL blocking на уровне приложения. HPACK экономит заголовки. Остался HOL blocking TCP.

3. **HTTP/3 + QUIC**: UDP-based, независимые streams без TCP HOL blocking, 0-RTT, Connection Migration. Встроенный TLS 1.3.

4. Используйте HTTP/2 или HTTP/3 для современных API. HTTP/1.1 — только для legacy совместимости.

5. Правильное кеширование (`Cache-Control`, `ETag`) снижает задержку и трафик эффективнее любой оптимизации протокола.

---

## Литература и источники

1. RFC 7230-7235. Hypertext Transfer Protocol (HTTP/1.1). IETF. https://tools.ietf.org/html/rfc7230
2. RFC 7540. Hypertext Transfer Protocol Version 2 (HTTP/2). IETF. https://tools.ietf.org/html/rfc7540
3. RFC 9000. QUIC: A UDP-Based Multiplexed and Secure Transport. IETF. https://tools.ietf.org/html/rfc9000
4. RFC 9114. HTTP/3. IETF. https://tools.ietf.org/html/rfc9114
5. Grigorik, I. (2013). *High Performance Browser Networking*. O'Reilly. https://hpbn.co/
6. Langley, A. et al. (2017). The QUIC Transport Protocol: Design and Internet-Scale Deployment. *ACM SIGCOMM*.
7. MDN Web Docs. HTTP. https://developer.mozilla.org/en-US/docs/Web/HTTP
8. Wikipedia. HTTP/2. https://en.wikipedia.org/wiki/HTTP/2
9. Wikipedia. HTTP/3. https://en.wikipedia.org/wiki/HTTP/3
10. httpx Documentation. https://www.python-httpx.org/http2/
