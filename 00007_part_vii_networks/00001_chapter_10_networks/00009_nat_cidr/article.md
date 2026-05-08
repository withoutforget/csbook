# NAT, CIDR и подсети

## Введение

IPv4 имеет фундаментальное ограничение: всего около 4.3 миллиарда адресов (2³²). В 1990-х годах стало очевидно, что этого катастрофически мало для растущего интернета. IANA исчерпала последние блоки IPv4 адресов в феврале 2011 года. Региональные интернет-регистры (RIR) выдали свои последние блоки между 2011 и 2019 годами.

Как интернет продолжает работать при нехватке адресов? Благодаря двум механизмам: **CIDR** (Classless Inter-Domain Routing) для более эффективного использования адресного пространства, и **NAT** (Network Address Translation) — техника, позволяющая тысячам устройств разделять один публичный IP-адрес.

NAT — это костыль, решающий проблему адресного пространства ценой нарушения сквозной (end-to-end) модели интернета. IPv6 с 128-битными адресами (2¹²⁸ — астрономическое число) призван навсегда решить проблему без NAT.

---

## 1. CIDR нотация

### 1.1 Почему возникла потребность в CIDR

До 1993 года использовалась классовая адресация:
- Класс A: /8 (16 млн хостов) — огромные блоки, расточительно
- Класс B: /16 (65534 хоста) — компания из 1000 сотрудников «съедала» блок
- Класс C: /24 (254 хоста) — таблицы маршрутизации росли взрывным образом

CIDR (RFC 1519, 1993) позволил использовать произвольные длины префиксов.

### 1.2 CIDR нотация и маски

**CIDR нотация**: `IP/prefix_length`

```
192.168.1.0/24

IP:      11000000.10101000.00000001.00000000
Маска:   11111111.11111111.11111111.00000000  (/24 = 24 единицы)
                                              ↑ 8 бит для хостов

Network: 192.168.1.0  (все хостовые биты = 0)
Broadcast: 192.168.1.255 (все хостовые биты = 1)
Host range: 192.168.1.1 - 192.168.1.254
Usable hosts: 254 (2^8 - 2)
```

```python
import ipaddress

def analyze_network(cidr: str) -> dict:
    """Анализ сети по CIDR нотации."""
    net = ipaddress.ip_network(cidr, strict=False)
    
    return {
        'network': str(net.network_address),
        'broadcast': str(net.broadcast_address),
        'netmask': str(net.netmask),
        'prefix_length': net.prefixlen,
        'num_addresses': net.num_addresses,
        'num_hosts': net.num_addresses - 2 if net.prefixlen < 31 else net.num_addresses,
        'host_range': f"{net.network_address + 1} - {net.broadcast_address - 1}",
        'is_private': net.is_private,
        'is_global': net.is_global,
    }

examples = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 
            '192.168.1.0/24', '192.168.1.0/30', '10.0.0.0/22']

for cidr in examples:
    info = analyze_network(cidr)
    print(f"\n{cidr}:")
    for k, v in info.items():
        print(f"  {k}: {v}")
```

### 1.3 Таблица популярных префиксов

| Префикс | Маска | Хостов | Использование |
|---------|-------|--------|---------------|
| /8 | 255.0.0.0 | 16 777 214 | Большие ISP |
| /16 | 255.255.0.0 | 65 534 | Корпоративные сети |
| /24 | 255.255.255.0 | 254 | Офисные сети, VLAN |
| /28 | 255.255.255.240 | 14 | Малые подсети |
| /30 | 255.255.255.252 | 2 | Point-to-point каналы |
| /31 | 255.255.255.254 | 2 (RFC 3021) | P2P каналы (нет broadcast) |
| /32 | 255.255.255.255 | 1 | Loopback, Anycast, host routes |

### 1.4 Деление на подсети (Subnetting)

```python
def subnet_network(network_cidr: str, new_prefix: int) -> list:
    """Разделить сеть на подсети с новым префиксом."""
    net = ipaddress.ip_network(network_cidr, strict=False)
    subnets = list(net.subnets(new_prefix=new_prefix))
    return [(str(s), s.num_addresses - 2) for s in subnets]

# Делим 192.168.0.0/22 на 4 подсети /24
subnets = subnet_network('192.168.0.0/22', 24)
for subnet, hosts in subnets:
    print(f"{subnet}: {hosts} хостов")
# 192.168.0.0/24: 254 хоста
# 192.168.1.0/24: 254 хоста
# 192.168.2.0/24: 254 хоста
# 192.168.3.0/24: 254 хоста

# Проверить принадлежность IP к сети:
net = ipaddress.ip_network('10.0.0.0/8')
print(ipaddress.ip_address('10.5.6.7') in net)  # True
print(ipaddress.ip_address('172.16.0.1') in net)  # False
```

---

## 2. Частные адреса (RFC 1918)

RFC 1918 зарезервировал три блока для частных сетей — не маршрутизируются в интернете:

| Блок | Диапазон | Число адресов | Типичное использование |
|------|----------|--------------|----------------------|
| 10.0.0.0/8 | 10.0.0.0 — 10.255.255.255 | 16 777 216 | Корпоративные сети |
| 172.16.0.0/12 | 172.16.0.0 — 172.31.255.255 | 1 048 576 | Средние сети |
| 192.168.0.0/16 | 192.168.0.0 — 192.168.255.255 | 65 536 | Домашние сети |

Дополнительно:
- `127.0.0.0/8` — loopback
- `169.254.0.0/16` — link-local (APIPA, когда нет DHCP)
- `100.64.0.0/10` — Shared Address Space (RFC 6598), для ISP CGN

---

## 3. NAT (Network Address Translation)

### 3.1 Как работает NAT

NAT (RFC 1631, 1994) — механизм, позволяющий маршрутизатору подменять IP-адреса в заголовках пакетов. Позволяет множеству устройств с частными адресами выходить в интернет через один публичный IP:

```
Домашняя сеть (10.0.0.0/24)         Интернет
┌──────────────────────────────┐
│ 10.0.0.2 ─── Router ──────────── 203.0.113.1 (публичный IP)
│ 10.0.0.3 ──/                 │
│ 10.0.0.4 ──/                 │
└──────────────────────────────┘

10.0.0.2 → 8.8.8.8:53 (DNS):
NAT преобразует:
  Source: 10.0.0.2:54321  →  203.0.113.1:40001

Ответ 8.8.8.8:53 → 203.0.113.1:40001:
NAT преобразует обратно:
  Destination: 203.0.113.1:40001  →  10.0.0.2:54321
```

### 3.2 NAPT (NAT Overload / PAT)

PAT (Port Address Translation) — наиболее распространённая форма NAT. Тысячи устройств делят один IP, различаясь по портам:

```
NAT Translation Table:
Internal              External              Remote
10.0.0.2:54321   →   203.0.113.1:40001   →  8.8.8.8:53
10.0.0.3:54322   →   203.0.113.1:40002   →  8.8.8.8:80
10.0.0.2:54323   →   203.0.113.1:40003   →  1.1.1.1:443
10.0.0.4:12345   →   203.0.113.1:40004   →  github.com:443
```

```python
# Упрощённая симуляция NAT таблицы
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class NATEntry:
    internal_ip: str
    internal_port: int
    external_port: int
    remote_ip: str
    remote_port: int
    created_at: float = 0.0
    last_seen: float = 0.0

class NATTable:
    def __init__(self, external_ip: str, timeout: int = 120):
        self.external_ip = external_ip
        self.timeout = timeout
        self.table: dict[int, NATEntry] = {}  # external_port → entry
        self.reverse: dict[tuple, int] = {}   # (internal_ip, internal_port) → ext_port
        self.next_port = 40000
    
    def translate_outbound(
        self, 
        src_ip: str, src_port: int, 
        dst_ip: str, dst_port: int
    ) -> tuple[str, int]:
        """Транслировать исходящий пакет."""
        key = (src_ip, src_port)
        
        if key not in self.reverse:
            # Создаём новую запись
            ext_port = self.next_port
            self.next_port += 1
            
            entry = NATEntry(
                internal_ip=src_ip,
                internal_port=src_port,
                external_port=ext_port,
                remote_ip=dst_ip,
                remote_port=dst_port,
                created_at=time.time(),
                last_seen=time.time()
            )
            self.table[ext_port] = entry
            self.reverse[key] = ext_port
        else:
            ext_port = self.reverse[key]
            self.table[ext_port].last_seen = time.time()
        
        return self.external_ip, ext_port
    
    def translate_inbound(
        self,
        dst_ip: str, dst_port: int
    ) -> Optional[tuple[str, int]]:
        """Транслировать входящий пакет."""
        if dst_port not in self.table:
            return None  # Нет записи — отбрасываем
        
        entry = self.table[dst_port]
        entry.last_seen = time.time()
        return entry.internal_ip, entry.internal_port
    
    def cleanup_expired(self):
        """Удалить устаревшие записи."""
        now = time.time()
        expired = [
            port for port, entry in self.table.items()
            if now - entry.last_seen > self.timeout
        ]
        for port in expired:
            entry = self.table.pop(port)
            self.reverse.pop((entry.internal_ip, entry.internal_port), None)
```

### 3.3 Проблемы NAT

**Нарушение end-to-end принципа**: входящие соединения невозможны без явной настройки (Port Forwarding). Сервер за NAT недостижим из интернета напрямую.

**P2P соединения**: BitTorrent, WebRTC, игры — сложно установить прямое соединение между двумя NAT-клиентами.

**Port Forwarding**: ручная конфигурация маппинга порта публичного IP на внутренний адрес:

```bash
# На роутере (Linux iptables):
# Перенаправить входящий TCP порт 8080 на 192.168.1.10:80
iptables -t nat -A PREROUTING -p tcp --dport 8080 -j DNAT --to-destination 192.168.1.10:80
iptables -A FORWARD -p tcp -d 192.168.1.10 --dport 80 -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT
```

**Протоколы с IP в данных**: FTP active mode, SIP (VoIP) — содержат IP адреса в теле сообщения. NAT не подменяет их → сломано. Решение: ALG (Application Layer Gateway) — специальный NAT helper.

### 3.4 NAT Traversal

Техники для установления P2P соединения через NAT:

**STUN** (Session Traversal Utilities for NAT, RFC 5389): сервер за пределами NAT сообщает клиенту его внешний IP и порт:

```python
# Упрощённый STUN клиент
import socket
import struct
import os

def stun_request(stun_server: str = 'stun.l.google.com', port: int = 19302) -> tuple:
    """Получить внешний IP и порт через STUN."""
    
    # STUN Binding Request
    msg_type = 0x0001  # Binding Request
    msg_length = 0
    magic_cookie = 0x2112A442
    transaction_id = os.urandom(12)
    
    header = struct.pack('!HHI12s', 
                         msg_type, msg_length, 
                         magic_cookie, transaction_id)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)
    sock.sendto(header, (stun_server, port))
    
    response, _ = sock.recvfrom(1024)
    sock.close()
    
    # Парсим ответ (упрощённо)
    # Ищем XOR-MAPPED-ADDRESS attribute (0x0020)
    offset = 20  # Пропускаем заголовок
    while offset < len(response):
        attr_type, attr_length = struct.unpack('!HH', response[offset:offset+4])
        if attr_type == 0x0020:  # XOR-MAPPED-ADDRESS
            family = response[offset+5]
            if family == 0x01:  # IPv4
                port_bytes = struct.unpack('!H', response[offset+6:offset+8])[0]
                ext_port = port_bytes ^ 0x2112  # XOR с magic cookie
                ip_bytes = struct.unpack('!I', response[offset+8:offset+12])[0]
                ext_ip_int = ip_bytes ^ 0x2112A442  # XOR с magic cookie
                ext_ip = socket.inet_ntoa(struct.pack('!I', ext_ip_int))
                return ext_ip, ext_port
        offset += 4 + attr_length
    
    return None, None

external_ip, external_port = stun_request()
print(f"External: {external_ip}:{external_port}")
```

**TURN** (Traversal Using Relays around NAT): relay сервер передаёт трафик когда прямое соединение невозможно.

**ICE** (Interactive Connectivity Establishment, RFC 8445): фреймворк для WebRTC, использует STUN + TURN + direct connection.

**UPnP/NAT-PMP**: автоматическое открытие портов на роутере (если поддерживается и включено).

---

## 4. IPv6 — решение без NAT

IPv6 (RFC 2460) предоставляет 2¹²⁸ ≈ 3.4 × 10³⁸ адресов — по ~50 квадриллионов на каждый квадратный метр поверхности Земли.

```python
# Размер адресного пространства IPv6
ipv6_addresses = 2**128
earth_surface_m2 = 5.1e14  # квадратных метров
print(f"IPv6 addresses: {ipv6_addresses:.2e}")
print(f"Per m² of Earth: {ipv6_addresses / earth_surface_m2:.2e}")
```

### 4.1 IPv6 адреса

```
2001:0db8:85a3:0000:0000:8a2e:0370:7334
│    │    │    │    │    │    │    │
└────┴────┴────┴────┴────┴────┴────┘
     8 групп по 16 бит (= 128 бит)

Правила сокращения:
1. Ведущие нули в группе можно опустить: 0db8 → db8
2. Одну (самую длинную) последовательность нулевых групп → ::
   2001:db8::1 = 2001:db8:0:0:0:0:0:1
```

**Типы адресов IPv6**:
- `::1` — loopback (аналог 127.0.0.1)
- `fe80::/10` — link-local (автоматически на каждом интерфейсе)
- `2000::/3` — глобально маршрутизируемые (глобальные unicast)
- `fc00::/7` — Unique Local Address (аналог RFC 1918)
- `ff00::/8` — multicast

### 4.2 SLAAC — автоконфигурация без DHCP

```
Router Advertisement (RA) содержит:
- Prefix: 2001:db8::/64
- Flags: A=1 (Stateless Address Autoconfiguration)

Клиент формирует адрес:
- Берёт prefix из RA: 2001:db8::
- Добавляет Interface ID из MAC (EUI-64) или случайный
- Итог: 2001:db8::1a2b:3c4d:5e6f:7g8h/64

Без DHCP сервера! Просто подключился к сети — уже имеешь IPv6 адрес.
```

### 4.3 Переход на IPv6

```bash
# Проверить IPv6 подключение
ping6 2001:4860:4860::8888      # Google IPv6 DNS
curl -6 https://ipv6.google.com

# IPv6 маршруты
ip -6 route show

# Двойной стек (dual-stack): устройство имеет IPv4 и IPv6 одновременно
ip addr show  # Видим оба адреса
```

---

## 5. Практика: сетевые инструменты

```bash
# CIDR калькулятор
ipcalc 192.168.1.0/24
# Network:   192.168.1.0/24
# Broadcast: 192.168.1.255
# HostMin:   192.168.1.1
# HostMax:   192.168.1.254
# Hosts/Net: 254

# Найти принадлежность IP к сети
python3 -c "
import ipaddress
net = ipaddress.ip_network('10.0.0.0/8')
ip = ipaddress.ip_address('10.5.6.7')
print(f'{ip} in {net}: {ip in net}')
"

# Посмотреть NAT соединения на Linux роутере
conntrack -L  # Таблица отслеживания соединений NAT
iptables -t nat -L -n -v  # NAT правила

# Показать текущий внешний IP
curl -s https://api.ipify.org
# или
curl -s https://ifconfig.me
```

---

## Заключение

CIDR и NAT — инженерные решения, продлившие жизнь IPv4 на десятилетия. CIDR позволил эффективнее использовать адресное пространство. NAT — позволил миллиардам устройств выходить в интернет через небольшое число публичных адресов.

**Ключевые выводы**:

1. **CIDR** `/prefix` — сколько бит зафиксированы как сетевая часть. `/24` = 256 адресов, `/16` = 65536.

2. **RFC 1918**: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` — частные адреса, не маршрутизируемые в интернете.

3. **NAT/PAT**: один публичный IP → тысячи устройств. Таблица трансляции (IP:Port ↔ IP:Port).

4. **Проблемы NAT**: нарушает end-to-end, сложность P2P. Решение: NAT Traversal (STUN/TURN/ICE).

5. **IPv6**: 2¹²⁸ адресов — решение без NAT. SLAAC — автоконфигурация без DHCP.

---

## Литература и источники

1. RFC 1918. Address Allocation for Private Internets. IETF. https://tools.ietf.org/html/rfc1918
2. RFC 4632. Classless Inter-domain Routing (CIDR). IETF. https://tools.ietf.org/html/rfc4632
3. RFC 3022. Traditional IP Network Address Translator (NAT). IETF. https://tools.ietf.org/html/rfc3022
4. RFC 5389. Session Traversal Utilities for NAT (STUN). IETF. https://tools.ietf.org/html/rfc5389
5. RFC 8445. Interactive Connectivity Establishment (ICE). IETF. https://tools.ietf.org/html/rfc8445
6. RFC 2460. Internet Protocol, Version 6 (IPv6) Specification. IETF. https://tools.ietf.org/html/rfc2460
7. RFC 4291. IP Version 6 Addressing Architecture. IETF. https://tools.ietf.org/html/rfc4291
8. Wikipedia. Classless Inter-Domain Routing. https://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing
9. Wikipedia. Network address translation. https://en.wikipedia.org/wiki/Network_address_translation
10. Python Documentation. ipaddress — IPv4/IPv6 manipulation library. https://docs.python.org/3/library/ipaddress.html
