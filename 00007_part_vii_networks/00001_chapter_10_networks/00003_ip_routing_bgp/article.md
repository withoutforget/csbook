# IP, маршрутизация, BGP

## Введение

Когда вы отправляете HTTP-запрос с ноутбука в Москве на сервер в Сан-Франциско, IP-пакет преодолевает тысячи километров, проходя через десятки маршрутизаторов. Каждый из них принимает самостоятельное решение: «куда отправить этот пакет дальше?» — не зная всего пути целиком. Это и есть маршрутизация.

IP (Internet Protocol) — главный протокол сетевого уровня интернета. IPv4 (1981) работает с 32-битными адресами, IPv6 (1998) — с 128-битными. IP обеспечивает best-effort доставку: пакеты могут быть потеряны, дублированы, доставлены не по порядку. Надёжность — задача TCP на транспортном уровне.

BGP (Border Gateway Protocol) — протокол, делающий интернет интернетом. Это «клей», соединяющий тысячи независимых сетей (Autonomous Systems) в единую глобальную инфраструктуру. Без BGP не было бы маршрутизации между провайдерами. И именно BGP — источник нескольких самых громких сетевых инцидентов в истории.

---

## 1. IPv4 заголовок

### 1.1 Детальная структура

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├───────┬───────┬───────────────────────┬───────────────────────────┤
│Version│  IHL  │    DSCP        ECN    │          Total Length     │
│  (4)  │  (4)  │    (6)         (2)    │           (16)            │
├───────┴───────┴───────────────────────┴───────────────────────────┤
│          Identification (16)          │DF│MF│   Fragment Offset   │
│                                       │  │  │       (13)          │
├───────────────────────────────────────┴──┴──┴───────────────────────┤
│    TTL (8)    │  Protocol (8)         │    Header Checksum (16)   │
├───────────────┴───────────────────────┴───────────────────────────┤
│                    Source IP Address (32)                         │
├───────────────────────────────────────────────────────────────────┤
│                 Destination IP Address (32)                       │
├───────────────────────────────────────────────────────────────────┤
│                   Options (variable) + Padding                    │
└───────────────────────────────────────────────────────────────────┘
```

Ключевые поля:
- **DSCP** (Differentiated Services Code Point): приоритет трафика (QoS)
- **Total Length**: общий размер пакета (заголовок + данные), макс 65535 байт
- **Identification + Fragment Offset + DF/MF**: фрагментация
- **TTL** (Time To Live): уменьшается на 1 на каждом хопе. 0 → пакет отброшен, ICMP Time Exceeded отправителю
- **Protocol**: 6=TCP, 17=UDP, 1=ICMP, 41=IPv6-in-IPv4

### 1.2 Фрагментация

Если пакет больше MTU интерфейса (обычно 1500 байт для Ethernet), IP может фрагментировать его:

```
Пакет 4096 байт → Ethernet MTU = 1500 байт

Fragment 1: offset=0,   MF=1 (More Fragments)
Fragment 2: offset=185, MF=1  (185 × 8 = 1480 байт)
Fragment 3: offset=370, MF=0  (последний)
```

Флаги:
- **DF** (Don't Fragment): не фрагментировать. Если пакет не помещается — отправить ICMP «Fragmentation Needed» (используется в Path MTU Discovery)
- **MF** (More Fragments): есть ещё фрагменты. 0 = последний или единственный

Фрагментация — плохо для производительности. Современные системы используют Path MTU Discovery (PMTUD) для определения оптимального MTU:

```bash
# Path MTU Discovery: пробуем большой пакет с DF=1
ping -M do -s 1472 192.168.1.1
# 1472 + 8 (ICMP) + 20 (IP) = 1500 байт
# Если PMTUD не работает → black hole (пакеты теряются молча)

# Проверка MTU пути
tracepath 8.8.8.8
```

### 1.3 IPv6 — упрощённый заголовок

IPv6 (RFC 2460) значительно упростил заголовок:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├───────┬───────────────────┬─────────────────────────────────────┤
│Version│  Traffic Class    │            Flow Label               │
│  (4)  │      (8)          │               (20)                  │
├───────┴───────────────────┴─────────────────────────────────────┤
│       Payload Length (16)         │ Next Header (8)│  Hop Limit  │
│                                   │                │    (8)      │
├───────────────────────────────────┴────────────────┴────────────┤
│                  Source Address (128 bits)                       │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│               Destination Address (128 bits)                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Ключевые отличия от IPv4:
- Фиксированный заголовок 40 байт (нет опций в основном заголовке, extension headers отдельно)
- **Нет фрагментации на промежуточных узлах** — только отправитель
- **Нет Header Checksum** — TCP/UDP уже считают checksum
- **Hop Limit** вместо TTL (принципиально то же)
- **Flow Label** — для QoS в маршрутизаторах
- **Next Header** вместо Protocol — может указывать на extension header или вышестоящий протокол

---

## 2. Маршрутизация

### 2.1 Longest Prefix Match

Маршрутизатор хранит таблицу маршрутов. При получении пакета ищет наиболее специфичный (longest prefix) маршрут:

```
Routing table:
Destination      Gateway        Interface
0.0.0.0/0        10.0.0.1       eth0    ← Default route
10.0.0.0/8       directly       eth0    ← Локальная сеть
10.1.0.0/16      10.0.0.254     eth0    ← Более специфичный
10.1.2.0/24      10.0.0.100     eth0    ← Ещё специфичнее

Пакет на 10.1.2.5:
- Подходит 0.0.0.0/0 (0 бит совпадает)
- Подходит 10.0.0.0/8 (8 бит)
- Подходит 10.1.0.0/16 (16 бит)
- Подходит 10.1.2.0/24 (24 бита) ← WINNER: самый длинный prefix
```

Реализация: Hardware маршрутизаторы используют TCAM (Ternary Content-Addressable Memory) для O(1) поиска. Linux kernel использует Patricia Trie (radix tree).

```bash
# Просмотр таблицы маршрутизации Linux
ip route show
# default via 192.168.1.1 dev eth0 proto dhcp
# 192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.100

# Куда уйдёт пакет для конкретного IP
ip route get 8.8.8.8
# 8.8.8.8 via 192.168.1.1 dev eth0 src 192.168.1.100

# Windows
route print
```

### 2.2 Статическая маршрутизация

```bash
# Добавить статический маршрут
ip route add 10.5.0.0/16 via 192.168.1.254
ip route add 0.0.0.0/0 via 192.168.1.1  # Default route

# Сохранить в /etc/network/interfaces (Debian/Ubuntu):
# up ip route add 10.5.0.0/16 via 192.168.1.254

# Маршрут через конкретный интерфейс
ip route add 10.5.0.0/16 dev eth1
```

### 2.3 Traceroute — видим путь пакета

```bash
traceroute 8.8.8.8
# traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets
#  1  192.168.1.1 (192.168.1.1)  1.234 ms  1.123 ms  1.456 ms   ← Local router
#  2  10.0.0.1 (10.0.0.1)  12.345 ms                            ← ISP hop 1
#  3  172.16.0.1 (172.16.0.1)  15.678 ms                        ← ISP hop 2
#  ...
# 12  8.8.8.8 (8.8.8.8)  30.123 ms                             ← Google DNS

# Принцип работы:
# Отправляем пакеты с TTL=1, 2, 3, ...
# При TTL=0 маршрутизатор возвращает ICMP Time Exceeded (с своим IP)
# Так мы узнаём каждый hop
```

---

## 3. Протоколы динамической маршрутизации

### 3.1 Distance-Vector: RIP

RIP (Routing Information Protocol) — простейший IGP. Каждый маршрутизатор периодически рассылает свою таблицу соседям. Метрика = hop count (максимум 15, 16 = infinity):

```
R1 знает: до R3 = 2 хопа (через R2)
R2 сообщает R1: "Я знаю путь до R3 за 1 хоп"
R1 обновляет: до R3 = 1 + 1 = 2 хопа (через R2)
```

Недостатки RIP:
- Медленная конвергенция (30 секунд цикл)
- Count-to-infinity проблема
- Максимум 15 хопов — не для больших сетей

### 3.2 Link-State: OSPF

OSPF (Open Shortest Path First, RFC 2328) — более сложный и эффективный IGP:

1. Каждый маршрутизатор строит топологию всей сети (LSDB — Link State Database)
2. Каждый маршрутизатор рассылает LSA (Link State Advertisement) — информацию о своих соединениях
3. Используется алгоритм Дейкстры для нахождения кратчайшего пути

```
Метрики OSPF:
- Cost = 10^8 / bandwidth (100 Mbit/s → cost 1, 10 Mbit/s → cost 10)

Пример топологии:
   R1 ──1── R2 ──1── R3
    \                /
     ───────5───────
     
OSPF найдёт: R1 → R2 → R3 (cost=2) вместо R1 → R3 (cost=5)
```

```bash
# Просмотр OSPF (на Cisco IOS):
# show ip ospf neighbor
# show ip ospf database
# show ip route ospf

# Quagga/FRR (Linux):
# vtysh
# show ip ospf neighbor
```

OSPF области (areas) позволяют масштабироваться:
- **Area 0** (backbone): обязательная, все другие области подключаются к ней
- **ABR** (Area Border Router): соединяет области
- Маршрутизаторы в одной области имеют полную топологию, между областями — только суммарные маршруты

---

## 4. BGP — Internet Routing

### 4.1 Autonomous Systems

Интернет состоит из тысяч независимых сетей — **Autonomous Systems (AS)**. Каждая AS — это набор IP-сетей под единым административным управлением с единой политикой маршрутизации.

Каждой AS присвоен номер **ASN** (Autonomous System Number):
- 16-битные (1-65535): старые, скоро закончатся
- 32-битные (до 4 294 967 295): RFC 4893
- Приватные AS: 64512-65535 (16-bit), 4200000000-4294967294 (32-bit)

Примеры:
- AS15169 — Google
- AS32934 — Meta
- AS714 — Apple
- AS8359 — МТС (Россия)

```bash
# Узнать ASN для IP
whois 8.8.8.8 | grep -i origin
# Или через bgp.he.net

# Инструмент bgpq4 — получить prefix-list для AS
bgpq4 -A AS15169
```

### 4.2 BGP сессии

BGP (Border Gateway Protocol, RFC 4271) — протокол обмена маршрутами между AS:

- **iBGP** (internal BGP): между маршрутизаторами внутри одной AS
- **eBGP** (external BGP): между маршрутизаторами разных AS

BGP работает поверх TCP (порт 179). Сессия устанавливается вручную (не автоматически):

```
AS15169 (Google)          AS1234 (Some ISP)
┌─────────────────┐        ┌─────────────────┐
│  BGP Router     │ eBGP   │  BGP Router     │
│  8.8.8.8/32     │───────→│                 │
│  2001:4860::/32 │        │                 │
└─────────────────┘        └─────────────────┘
         "Я анонсирую эти префиксы"
```

### 4.3 Атрибуты BGP

BGP использует path attributes для описания маршрутов:

| Атрибут | Тип | Описание |
|---------|-----|----------|
| AS_PATH | Well-known mandatory | Список AS через которые прошёл маршрут |
| NEXT_HOP | Well-known mandatory | IP следующего хопа |
| LOCAL_PREF | Well-known discretionary | Предпочтение для исходящего трафика (iBGP) |
| MED | Optional | Multi-Exit Discriminator — подсказка соседу для входящего трафика |
| ORIGIN | Well-known mandatory | Источник: IGP, EGP, INCOMPLETE |
| COMMUNITY | Optional transitive | Метки для политик |

Выбор лучшего маршрута (упрощённо):
1. Highest Weight (Cisco proprietary)
2. Highest LOCAL_PREF
3. Locally originated
4. Shortest AS_PATH
5. Lowest ORIGIN (IGP < EGP < INCOMPLETE)
6. Lowest MED
7. eBGP > iBGP
8. Lowest IGP metric to NEXT_HOP
9. Lowest Router ID

### 4.4 BGP Hijacking — когда кто-то «крадёт» ваши адреса

BGP не аутентифицирован. Любая AS может объявить любой IP-префикс. Это приводит к инцидентам:

**2008 год**: Pakistan Telecom (AS17557) по ошибке объявила более специфичный маршрут для YouTube (208.65.153.0/24 вместо /22). Из-за longest prefix match весь трафик YouTube шёл через Пакистан. 75 минут YouTube был недоступен по всему миру.

**2010 год**: China Telecom объявила ~40 000 маршрутов, включая сети DoD, NASA и других. Трафик шёл через Китай ~18 минут.

**Механизм hijacking**:
```
Легитимный анонс: AS15169 анонсирует 8.8.8.0/24
Атакующий: AS-BAD анонсирует 8.8.8.0/25 (более специфичный!)
Результат: трафик на 8.8.8.0/25 → AS-BAD (MITM или blackhole)
```

**Защита**:
- **RPKI** (Resource Public Key Infrastructure): криптографическое подтверждение что AS имеет право анонсировать префикс
- **IRR** (Internet Routing Registry): Базы данных авторизованных маршрутов
- **BGPsec**: криптографическая подпись AS_PATH (RFC 8205)

```bash
# Проверка RPKI для префикса
whois -h whois.ripe.net "8.8.8.0/24"

# Инструменты мониторинга BGP:
# https://bgpmon.net/
# https://bgpstream.caida.org/
```

### 4.5 Anycast

Anycast — одному IP-адресу соответствует несколько серверов в разных местах. Маршрутизаторы BGP находят ближайший (в смысле метрики BGP):

```
8.8.8.8 анонсируется из:
- Google PoP в Москве (AS15169)
- Google PoP в Амстердаме (AS15169)
- Google PoP в Лондоне (AS15169)

Пользователь в Москве → BGP выбирает ближайший PoP → Москва
Пользователь во Франции → BGP выбирает → Амстердам
```

Применяется:
- DNS (8.8.8.8, 1.1.1.1) — сотни PoP по всему миру
- CDN-серверы
- DDoS mitigation (нагрузка распределяется)

---

## 5. Практика: анализ маршрутов

```python
import socket
import subprocess

def get_route_to(host: str) -> dict:
    """Получить информацию о маршруте до хоста."""
    ip = socket.gethostbyname(host)
    
    # ip route get возвращает маршрут
    result = subprocess.run(
        ['ip', 'route', 'get', ip],
        capture_output=True, text=True
    )
    
    return {
        'target': host,
        'ip': ip,
        'route': result.stdout.strip()
    }

def traceroute_parse(host: str, max_hops: int = 15) -> list:
    """Traceroute с парсингом результатов."""
    result = subprocess.run(
        ['traceroute', '-n', '-m', str(max_hops), host],
        capture_output=True, text=True, timeout=60
    )
    
    hops = []
    for line in result.stdout.split('\n')[1:]:  # Пропускаем заголовок
        parts = line.split()
        if len(parts) >= 3:
            hop_num = parts[0]
            ip = parts[1] if parts[1] != '*' else None
            rtts = [float(p.replace('ms', '')) 
                    for p in parts[2:] if p.replace('.', '').isdigit()]
            hops.append({
                'hop': int(hop_num),
                'ip': ip,
                'rtts_ms': rtts,
                'avg_rtt': sum(rtts) / len(rtts) if rtts else None
            })
    
    return hops

# Использование
route = get_route_to('8.8.8.8')
print(route)

hops = traceroute_parse('8.8.8.8')
for h in hops:
    print(f"Hop {h['hop']:2d}: {h['ip'] or '*':20s} {h['avg_rtt']:.1f}ms" 
          if h['avg_rtt'] else f"Hop {h['hop']:2d}: *")
```

### 5.1 Анализ BGP данных (публичные источники)

```python
import requests

def get_bgp_info(ip: str) -> dict:
    """Получить информацию об AS и маршрутах для IP."""
    # RIPE STAT API (публичный, без ключа)
    response = requests.get(
        f"https://stat.ripe.net/data/prefix-overview/data.json",
        params={"resource": ip}
    )
    data = response.json()
    
    return {
        'ip': ip,
        'asns': data['data']['asns'],
        'prefixes': [p['prefix'] for p in data['data'].get('announcing', {}).get('prefixes', [])]
    }

# Пример
info = get_bgp_info('8.8.8.8')
print(f"ASNs: {info['asns']}")  # [{'asn': 15169, 'holder': 'GOOGLE'}]
```

---

## Заключение

IP и BGP — основа глобальной сети. IP обеспечивает адресацию и best-effort доставку. Маршрутизация через longest prefix match и протоколы (OSPF для внутренних сетей, BGP для межАС) обеспечивает достижимость любого узла интернета.

**Ключевые выводы**:

1. **IPv4** — 32-битная адресация, TTL ограничивает «вечные» пакеты, фрагментация при превышении MTU.

2. **IPv6** — 128-битные адреса, упрощённый заголовок, нет фрагментации на промежуточных узлах.

3. **Longest Prefix Match** — правило выбора маршрута: побеждает наиболее специфичный префикс.

4. **OSPF** — link-state IGP для внутренней маршрутизации AS (алгоритм Дейкстры).

5. **BGP** — EGP для маршрутизации между AS. Не аутентифицирован → BGP hijacking. Решение: RPKI.

6. **Anycast** — один IP → несколько серверов → BGP выбирает ближайший. Основа DNS и CDN.

---

## Литература и источники

1. RFC 791. Internet Protocol. J. Postel. IETF. https://tools.ietf.org/html/rfc791
2. RFC 2460. Internet Protocol, Version 6 (IPv6) Specification. IETF. https://tools.ietf.org/html/rfc2460
3. RFC 4271. A Border Gateway Protocol 4 (BGP-4). IETF. https://tools.ietf.org/html/rfc4271
4. RFC 2328. OSPF Version 2. IETF. https://tools.ietf.org/html/rfc2328
5. RFC 6480. An Infrastructure to Support Secure Internet Routing (RPKI). IETF. https://tools.ietf.org/html/rfc6480
6. Halabi, S. (2000). *Internet Routing Architectures*, 2nd Edition. Cisco Press.
7. Stewart, J. W. (1998). *BGP4: Inter-Domain Routing in the Internet*. Addison-Wesley.
8. Wikipedia. Border Gateway Protocol. https://en.wikipedia.org/wiki/Border_Gateway_Protocol
9. RIPE NCC. BGP Routing Information. https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris
10. Rekhter, Y. et al. Pakistan Telecom BGP Incident 2008. https://www.ripe.net/publications/docs/ripe-399
