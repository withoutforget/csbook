# TCP vs UDP

## Введение

Транспортный уровень интернета представлен двумя фундаментально разными протоколами: TCP (Transmission Control Protocol) и UDP (User Datagram Protocol). Они предлагают принципиально разные компромиссы, и выбор между ними определяет характеристики приложения — надёжность, задержка, overhead, масштабируемость.

TCP (RFC 793, 1981) — это гарантированная, упорядоченная доставка с управлением потоком. Браузер, электронная почта, SSH, базы данных — всё это TCP. UDP (RFC 768, 1980) — это лёгкий протокол «отправил и забыл» с минимальным заголовком (8 байт против 20 байт у TCP). DNS, VoIP, игры, стриминг, NTP, QUIC — UDP.

Важно понимать: UDP — не «сломанный TCP». Это намеренно простой протокол, дающий разработчику полный контроль над тем, как обрабатывать потери и упорядочивание. Когда потеря пакета важнее задержки (VoIP: лучше пропустить фрагмент речи, чем замолчать на секунду для повторной передачи) — UDP правильный выбор.

---

## 1. TCP: Transmission Control Protocol

### 1.1 Заголовок TCP

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├───────────────────────────────────┬───────────────────────────────┤
│         Source Port (16)          │      Destination Port (16)    │
├───────────────────────────────────┴───────────────────────────────┤
│                       Sequence Number (32)                        │
├───────────────────────────────────────────────────────────────────┤
│                    Acknowledgment Number (32)                     │
├───────┬───────┬─────────────────────┬───────────────────────────────┤
│Data   │  Rsrv │C E U A P R S F      │         Window Size         │
│Offset │  (3)  │W C R C S S Y I      │            (16)             │
│  (4)  │       │R E G K H T N N      │                             │
├───────┴───────┴─────────────────────┴───────────────────────────────┤
│           Checksum (16)           │      Urgent Pointer (16)      │
├───────────────────────────────────┴───────────────────────────────┤
│                    Options (0-40 bytes) + Padding                 │
└───────────────────────────────────────────────────────────────────┘
```

**Sequence Number** (32 бит): порядковый номер первого байта данных в этом сегменте. При установке соединения — Initial Sequence Number (ISN), выбирается случайно.

**Acknowledgment Number** (32 бит): следующий ожидаемый порядковый номер (ACK подтверждает все байты до этого числа).

**Data Offset** (4 бита): длина заголовка в 32-битных словах (минимум 5 = 20 байт).

**Флаги**:
- **SYN**: синхронизация (handshake)
- **ACK**: подтверждение
- **FIN**: завершение соединения
- **RST**: сброс соединения (ошибка)
- **PSH**: немедленно передать данные приложению
- **URG**: urgent data (практически не используется)
- **CWR/ECE**: Explicit Congestion Notification (ECN)

**Window Size** (16 бит): размер receive window — сколько байт готов принять получатель без ACK. Основа flow control.

### 1.2 Основные характеристики TCP

**Connection-oriented**: перед передачей данных устанавливается соединение (three-way handshake).

**Reliable delivery**: каждый байт подтверждается, потерянные сегменты повторно передаются.

**In-order delivery**: данные приложению доставляются в правильном порядке (TCP буферизует пришедшие не по порядку сегменты).

**Flow control**: получатель сообщает отправителю, сколько он готов принять (Window Size).

**Congestion control**: TCP снижает скорость при признаках перегрузки сети.

**Full-duplex**: данные передаются в обоих направлениях независимо.

### 1.3 Управление потоком (Flow Control)

Получатель объявляет `rwnd` (receive window) — свободное место в его receive buffer. Отправитель не должен иметь более `rwnd` байт неподтверждённых данных:

```python
# Упрощённая иллюстрация flow control
class TCPFlowControl:
    def __init__(self, buffer_size: int = 65535):
        self.receive_buffer = bytearray(buffer_size)
        self.buffer_used = 0
    
    @property
    def advertised_window(self) -> int:
        """Объявляем в ACK: сколько готовы принять."""
        return len(self.receive_buffer) - self.buffer_used
    
    def receive(self, data: bytes) -> bool:
        if len(data) > self.advertised_window:
            return False  # Нет места — DROP
        self.buffer_used += len(data)
        # ... приложение читает из буфера, освобождая место ...
        return True

# Нулевое окно (zero window probe):
# Если rwnd = 0, отправитель периодически отправляет 1-байтовые зонды
# Когда получатель освободит буфер → пришлёт ACK с новым rwnd
```

### 1.4 Socket API: TCP в Python

```python
import socket
import threading
from typing import Optional

class TCPServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
    
    def start(self):
        self.server_socket = socket.socket(
            socket.AF_INET,     # IPv4
            socket.SOCK_STREAM  # TCP
        )
        # SO_REUSEADDR: позволяет rebind сразу после закрытия
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)  # backlog = 5 соединений в очереди
        
        print(f"Server listening on {self.host}:{self.port}")
        
        while True:
            conn, addr = self.server_socket.accept()  # Блокируется
            print(f"New connection from {addr}")
            thread = threading.Thread(target=self.handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()
    
    def handle_client(self, conn: socket.socket, addr):
        try:
            while True:
                # recv() блокируется — ждёт данных
                data = conn.recv(4096)
                if not data:  # Пустые данные = клиент закрыл соединение
                    break
                print(f"Received from {addr}: {data.decode()}")
                conn.send(data)  # Echo
        finally:
            conn.close()

class TCPClient:
    def send_receive(self, host: str, port: int, message: str) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # TCP опции:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Отключить Nagle
            s.settimeout(5.0)
            
            s.connect((host, port))
            s.send(message.encode())
            
            # Получаем ответ — может прийти несколькими recv()
            response = b''
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                response += chunk
                if len(response) >= len(message):  # Получили ожидаемое
                    break
            
            return response.decode()

# TCP keepalive — обнаружение мёртвых соединений
def configure_keepalive(sock: socket.socket):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # Linux-специфичные настройки:
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)   # Начать через 60с
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)  # Интервал 10с
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)     # 5 попыток
```

### 1.5 Nagle Algorithm

Алгоритм Нагля (RFC 896, 1984): буферизует маленькие данные до накопления MSS (Maximum Segment Size) или прихода ACK. Цель — избежать отправки множества маленьких пакетов («silly window syndrome»).

Проблема: для интерактивных приложений (SSH, telnet, игры) добавляет задержку до 200 мс. Решение: `TCP_NODELAY`:

```python
# Отключение алгоритма Нагля:
socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

# Когда отключать: interactive протоколы, real-time
# Когда оставлять: bulk transfer (файлы, бэкапы)
```

---

## 2. UDP: User Datagram Protocol

### 2.1 Заголовок UDP

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├───────────────────────────────────┬───────────────────────────────┤
│         Source Port (16)          │      Destination Port (16)    │
├───────────────────────────────────┬───────────────────────────────┤
│             Length (16)           │         Checksum (16)         │
└───────────────────────────────────┴───────────────────────────────┘
│                         Data ...                                  │
```

Всего **8 байт** заголовка — минимально возможно для мультиплексирования по портам.

- **Length**: длина UDP-датаграммы (заголовок + данные), минимум 8
- **Checksum**: опциональный в IPv4, обязательный в IPv6

### 2.2 Характеристики UDP

**Connectionless**: нет установки соединения — данные отправляются немедленно.

**Unreliable**: нет подтверждений. Потеря пакетов — молчаливая.

**Unordered**: датаграммы могут прийти не по порядку.

**No flow/congestion control**: отправитель не учитывает возможности получателя или состояние сети.

**Preserves message boundaries**: recv() всегда получает ровно одну датаграмму.

### 2.3 UDP в Python

```python
import socket
import struct
import time

class UDPServer:
    def __init__(self, host: str, port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        print(f"UDP Server on {host}:{port}")
    
    def run(self):
        while True:
            data, addr = self.sock.recvfrom(65535)  # Max UDP payload
            print(f"Received {len(data)} bytes from {addr}")
            self.sock.sendto(data, addr)  # Echo

class UDPClient:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)
    
    def send(self, host: str, port: int, data: bytes):
        """Отправка без гарантий."""
        self.sock.sendto(data, (host, port))
    
    def ping_udp(self, host: str, port: int) -> Optional[float]:
        """UDP ping с измерением RTT."""
        payload = struct.pack('!d', time.time())
        self.sock.sendto(payload, (host, port))
        
        try:
            response, addr = self.sock.recvfrom(1024)
            sent_time = struct.unpack('!d', response[:8])[0]
            return (time.time() - sent_time) * 1000  # RTT в миллисекундах
        except socket.timeout:
            return None  # Пакет потерян!

# Multicast с UDP — отправить группе получателей
def udp_multicast_sender(group: str, port: int, message: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.sendto(message.encode(), (group, port))  # 224.0.0.1-239.255.255.255
```

---

## 3. Сравнение TCP и UDP

| Характеристика | TCP | UDP |
|---------------|-----|-----|
| Тип соединения | Connection-oriented | Connectionless |
| Надёжность | Гарантированная доставка | Best-effort |
| Порядок | Гарантированный | Не гарантирован |
| Flow control | Да (receive window) | Нет |
| Congestion control | Да | Нет |
| Overhead заголовка | 20-60 байт | 8 байт |
| Задержка | Выше (handshake, ACK) | Ниже |
| Скорость | Ниже при потерях | Постоянная |
| Сохранение границ сообщений | Нет (stream) | Да (datagram) |
| Multicast | Нет | Да |
| Примеры | HTTP, SMTP, SSH, DB | DNS, VoIP, Gaming, NTP, QUIC |

### 3.1 Когда UDP лучше

**DNS**: небольшой запрос + небольшой ответ. RTT важен. Если пакет потерян — просто повторить запрос. TCP overhead нецелесообразен для 99% запросов (ответ умещается в один UDP пакет).

**VoIP (SIP/RTP)**: лучше пропустить 20 мс звука, чем остановить воспроизведение на 100-200 мс для повторной передачи. Потери до 5% практически незаметны.

**Online gaming**: позиция игрока устаревает через 50 мс. Повторять старые пакеты бессмысленно. Нужны только самые свежие данные.

**QUIC**: Google разработал QUIC поверх UDP, преодолевая ограничения TCP (head-of-line blocking) при сохранении надёжности. UDP здесь — способ избежать ограничений TCP в стеке ОС.

**NTP**: синхронизация времени — запрос + ответ, нет смысла в TCP.

**DHCP**: клиент без IP не может установить TCP соединение!

### 3.2 Реализация надёжности поверх UDP

Когда нужны надёжность но не все ограничения TCP — реализуют своё решение поверх UDP:

```python
import socket
import struct
import time
import threading
from collections import defaultdict

class ReliableUDP:
    """
    Упрощённая надёжная передача поверх UDP.
    Демонстрация концепции (не production код).
    """
    
    HEADER_FORMAT = '!HHH'   # sequence_num (16), ack_num (16), flags (16)
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    
    FLAG_ACK = 0x0001
    FLAG_FIN = 0x0002
    
    def __init__(self, sock: socket.socket, remote_addr):
        self.sock = sock
        self.remote_addr = remote_addr
        self.seq_num = 0
        self.expected_ack = defaultdict(lambda: None)
        self.timeout = 0.1  # 100мс RTO
        self.lock = threading.Lock()
    
    def send_reliable(self, data: bytes) -> bool:
        """Отправить с подтверждением и повторной попыткой."""
        seq = self.seq_num
        self.seq_num += 1
        
        header = struct.pack(self.HEADER_FORMAT, seq, 0, 0)
        packet = header + data
        
        # Повторные попытки (simplified stop-and-wait)
        for attempt in range(5):
            self.sock.sendto(packet, self.remote_addr)
            
            # Ждём ACK
            self.sock.settimeout(self.timeout * (2 ** attempt))  # Exponential backoff
            try:
                response, _ = self.sock.recvfrom(1024)
                ack_seq, _, flags = struct.unpack(
                    self.HEADER_FORMAT, response[:self.HEADER_SIZE])
                
                if flags & self.FLAG_ACK and ack_seq == seq:
                    return True  # Доставлено!
            except socket.timeout:
                continue  # Повторяем
        
        return False  # Не удалось доставить
    
    def receive(self) -> tuple:
        """Получить пакет и отправить ACK."""
        while True:
            packet, addr = self.sock.recvfrom(65535)
            seq, _, flags = struct.unpack(
                self.HEADER_FORMAT, packet[:self.HEADER_SIZE])
            data = packet[self.HEADER_SIZE:]
            
            # Отправляем ACK
            ack = struct.pack(self.HEADER_FORMAT, seq, 0, self.FLAG_ACK)
            self.sock.sendto(ack, addr)
            
            return data, addr
```

---

## 4. Практические примеры

### 4.1 HTTP через TCP (низкий уровень)

```python
import socket

def http_request_raw(host: str, path: str = '/', port: int = 80) -> tuple:
    """HTTP/1.1 запрос через raw TCP socket."""
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # TCP установит соединение (SYN/SYN-ACK/ACK)
        s.settimeout(10.0)
        s.connect((socket.gethostbyname(host), port))
        
        # Отправляем HTTP запрос
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Connection: close\r\n"
            f"User-Agent: raw-socket/1.0\r\n"
            f"\r\n"
        ).encode()
        
        s.sendall(request)  # sendall гарантирует отправку всего буфера
        
        # Читаем ответ частями (TCP — stream protocol!)
        response = b''
        while True:
            chunk = s.recv(8192)
            if not chunk:
                break
            response += chunk
    
    # Разбираем HTTP ответ
    header_end = response.find(b'\r\n\r\n')
    if header_end == -1:
        return {}, b''
    
    headers_raw = response[:header_end].decode()
    body = response[header_end + 4:]
    
    # Парсим заголовки
    lines = headers_raw.split('\r\n')
    status_line = lines[0]  # "HTTP/1.1 200 OK"
    headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
    
    return headers, body

headers, body = http_request_raw('example.com', '/')
print(f"Content-Length: {headers.get('Content-Length')}")
print(f"Body: {body[:100]}...")
```

### 4.2 DNS через UDP

```python
import socket
import struct
import random

def dns_query(domain: str, dns_server: str = '8.8.8.8') -> list:
    """DNS A запрос через UDP."""
    
    # DNS Query ID (случайный)
    query_id = random.randint(0, 65535)
    
    # DNS заголовок: ID, Flags, QDCOUNT, ANCOUNT, NSCOUNT, ARCOUNT
    header = struct.pack('!HHHHHH', query_id, 0x0100, 1, 0, 0, 0)
    # Flags: 0x0100 = Standard query, Recursion Desired
    
    # Кодируем доменное имя (www.example.com → \x03www\x07example\x03com\x00)
    question = b''
    for part in domain.split('.'):
        question += bytes([len(part)]) + part.encode()
    question += b'\x00'  # Конец имени
    question += struct.pack('!HH', 1, 1)  # QTYPE=A(1), QCLASS=IN(1)
    
    packet = header + question
    
    # Отправляем через UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)
    sock.sendto(packet, (dns_server, 53))
    
    # Получаем ответ
    response, _ = sock.recvfrom(512)
    sock.close()
    
    # Парсим ответ (упрощённо — только IP адреса)
    ips = []
    # Ответы начинаются после вопроса...
    # Полный парсинг DNS требует обработки compression pointers
    # Для простоты используем dnspython или socket.getaddrinfo()
    
    return ips

# Правильный способ — через OS resolver:
def dns_lookup(domain: str) -> list:
    """DNS lookup через системный resolver."""
    try:
        results = socket.getaddrinfo(domain, None, socket.AF_INET)
        return list(set(r[4][0] for r in results))
    except socket.gaierror as e:
        print(f"DNS lookup failed: {e}")
        return []

ips = dns_lookup('google.com')
print(f"google.com → {ips}")
```

---

## 5. TCP vs UDP на практике: выбор протокола

```
Нужна ли надёжная доставка?
├── ДА → TCP
│   └── Примеры: HTTP, SSH, SMTP, PostgreSQL, MySQL
│
└── НЕТ → Смотри дальше
    │
    ├── Важна минимальная задержка (old data = useless)?
    │   └── ДА → UDP
    │       └── Примеры: VoIP, gaming, live video, market data
    │
    ├── Нужна надёжность но без ограничений TCP?
    │   └── ДА → UDP + custom reliability layer
    │       └── Примеры: QUIC (HTTP/3), WebRTC, DCCP
    │
    ├── Маленький request-response (< 512 байт)?
    │   └── ДА → UDP (если retry прост)
    │       └── Примеры: DNS, NTP, SNMP
    │
    └── Нужен multicast/broadcast?
        └── ДА → UDP
            └── Примеры: mDNS, SSDP, PTP (IEEE 1588)
```

---

## Заключение

TCP и UDP — два инструмента с разными назначениями. TCP даёт надёжность ценой задержки и overhead. UDP даёт скорость и гибкость ценой отсутствия гарантий.

**Ключевые выводы**:

1. **TCP** = надёжность + порядок + flow/congestion control. 20+ байт заголовка. Для большинства приложений.

2. **UDP** = минимальный overhead (8 байт). Без гарантий. Для latency-sensitive или multicast.

3. **TCP — stream протокол**: данные — непрерывный поток байт. Граница сообщений — ответственность приложения.

4. **UDP — datagram протокол**: каждый `recvfrom()` = одна датаграмма.

5. **Nagle Algorithm**: буферизация маленьких данных. Отключайте `TCP_NODELAY` для интерактивных протоколов.

6. **QUIC** = надёжность поверх UDP. Позволяет обойти ограничения TCP в ОС (head-of-line blocking, медленное изменение алгоритмов congestion control).

---

## Литература и источники

1. RFC 793. Transmission Control Protocol. J. Postel. IETF. https://tools.ietf.org/html/rfc793
2. RFC 768. User Datagram Protocol. J. Postel. IETF. https://tools.ietf.org/html/rfc768
3. RFC 896. Congestion Control in IP/TCP. J. Nagle. IETF. https://tools.ietf.org/html/rfc896
4. Stevens, W. R. (1994). *TCP/IP Illustrated, Volume 1: The Protocols*. Addison-Wesley.
5. Stevens, W. R., Fenner, B., & Rudoff, A. M. (2003). *UNIX Network Programming, Volume 1*, 3rd Edition. Addison-Wesley.
6. Fall, K. R., & Stevens, W. R. (2011). *TCP/IP Illustrated, Volume 1*, 2nd Edition. Addison-Wesley.
7. Python Documentation. socket — Low-level networking interface. https://docs.python.org/3/library/socket.html
8. Wikipedia. Transmission Control Protocol. https://en.wikipedia.org/wiki/Transmission_Control_Protocol
9. Wikipedia. User Datagram Protocol. https://en.wikipedia.org/wiki/User_Datagram_Protocol
10. Tanenbaum, A. S. (2010). *Computer Networks*, 5th Edition. Prentice Hall.
