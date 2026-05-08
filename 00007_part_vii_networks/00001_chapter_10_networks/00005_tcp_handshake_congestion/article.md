# TCP handshake и congestion control

## Введение

TCP обеспечивает надёжную передачу данных через ненадёжные сети — это звучит как волшебство. Магия раскрывается в двух механизмах: процедуре установки и завершения соединения (handshake/teardown) и управлении перегрузкой (congestion control). Оба механизма тесно связаны и определяют производительность TCP в реальных условиях.

Three-way handshake устанавливает начальные порядковые номера и параметры соединения. Four-way teardown гарантирует, что оба конца корректно завершили передачу. Состояние TIME_WAIT — источник многих вопросов на собеседованиях и производственных проблем.

Congestion control — более тонкий механизм. Сеть не сообщает явно о своей нагрузке (как правило). TCP должен «угадывать» состояние сети по косвенным признакам: потерям пакетов и задержкам. Алгоритмы congestion control — от классического Reno до Google BBR — постоянно эволюционируют и существенно влияют на реальную пропускную способность.

---

## 1. Three-Way Handshake

### 1.1 Процесс установки соединения

```
Клиент                              Сервер
  |                                   |
  |------- SYN (seq=ISN_c) ---------->|  1. SYN: клиент выбирает Initial Sequence Number
  |                                   |     SYN флаг = 1, seq = случайный ISN_c
  |                                   |
  |<-- SYN-ACK (seq=ISN_s, ack=ISN_c+1)|  2. SYN-ACK: сервер выбирает свой ISN_s
  |                                   |     ACK = ISN_c + 1 (подтверждает SYN клиента)
  |                                   |
  |------- ACK (ack=ISN_s+1) -------->|  3. ACK: клиент подтверждает SYN сервера
  |                                   |     ACK = ISN_s + 1
  |                                   |
  |======= Connection Established ====|
  |                                   |
  |------- DATA ------------------------|
```

Зачем три шага:
- SYN: клиент сообщает свой ISN
- SYN-ACK: сервер подтверждает ISN клиента и сообщает свой ISN
- ACK: клиент подтверждает ISN сервера

**Почему ISN случайный?** Защита от атак: если ISN предсказуем, атакующий может подделать пакеты «от лица» клиента без перехвата трафика (TCP spoofing).

### 1.2 SYN flood атака

```
Атакующий заваливает сервер SYN-пакетами с поддельными IP.
Сервер создаёт half-open соединение для каждого SYN.
SYN-ACK уходит на поддельные адреса → никогда не получит ACK.
SYN backlog заполняется → сервер не может принимать новые соединения.

Защита: SYN cookies (RFC 4987)
- Сервер кодирует информацию о соединении в ISN (crypto hash)
- Не хранит состояние до получения ACK
- При ACK: проверяет cookie, восстанавливает параметры соединения
```

```bash
# Включение SYN cookies на Linux
sysctl net.ipv4.tcp_syncookies=1

# Размер SYN backlog
sysctl net.ipv4.tcp_max_syn_backlog=4096
```

---

## 2. Four-Way Teardown

### 2.1 Завершение соединения

TCP — full-duplex, поэтому каждая сторона завершает свою половину соединения независимо:

```
Клиент (active close)              Сервер (passive close)
  |                                   |
  |-------- FIN (seq=M) ------------->|  Клиент: "Я закончил отправку"
  |                                   |
  |<-------- ACK (ack=M+1) -----------|  Сервер: "Получил твой FIN"
  |                                   |  [Сервер может ещё отправлять данные]
  |                                   |
  |<-------- FIN (seq=N) -------------|  Сервер: "Я тоже закончил"
  |                                   |
  |--------- ACK (ack=N+1) ---------->|  Клиент: "Получил"
  |                                   |
  [Клиент → TIME_WAIT → CLOSED]
  [Сервер → CLOSED]
```

На практике FIN и ACK сервера часто объединяются в один пакет (FIN-ACK) — три шага вместо четырёх.

### 2.2 TIME_WAIT состояние

После отправки финального ACK клиент входит в TIME_WAIT на **$2 \times \text{MSL}$** (Maximum Segment Lifetime, обычно 60 секунд → TIME_WAIT = 120 секунд).

**Зачем TIME_WAIT?**
1. Гарантия что финальный ACK дошёл до сервера (если потерян — сервер повторит FIN)
2. Предотвращение повторного использования той же пары (src_ip, src_port, dst_ip, dst_port) с «старыми» пакетами в сети

```bash
# Посмотреть TIME_WAIT соединения
ss -tn state time-wait
# или
netstat -tn | grep TIME_WAIT

# Количество TIME_WAIT:
ss -tn state time-wait | wc -l

# Проблема: при высокой нагрузке могут заканчиваться ephemeral ports
# Решение: SO_REUSEADDR, SO_REUSEPORT, или TCP_FASTOPEN
```

**SO_REUSEADDR**: позволяет серверу сразу rebind на порт после рестарта (даже если TIME_WAIT):

```python
server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
```

### 2.3 RST (Reset)

RST — немедленное прерывание соединения без graceful teardown:

```python
# Принудительный сброс через SO_LINGER с l_linger=0
import struct

server_sock.setsockopt(
    socket.SOL_SOCKET, socket.SO_LINGER,
    struct.pack('ii', 1, 0)  # l_onoff=1, l_linger=0
)
server_sock.close()  # Отправит RST вместо FIN
```

RST используется при:
- Неожиданном пакете (нет соединения по этому порту)
- Немедленном закрытии (SO_LINGER с нулём)
- Приложение не успело прочитать данные из буфера при закрытии

---

## 3. Congestion Control

### 3.1 Проблема перегрузки

TCP может «перегрузить» сеть: отправитель продолжает посылать, роутеры переполняют очереди, начинаются потери. Без congestion control TCP «жаден» — займёт всю доступную полосу, что разрушает работу других соединений.

Индикаторы перегрузки:
- **Packet loss** (традиционный): роутер отбросил пакет → его не подтвердят → таймаут или дублированные ACK
- **Delay increase** (BBR): задержка растёт → очереди заполняются

### 3.2 Ключевые переменные

- **cwnd** (congestion window): сколько байт отправитель может отправить без подтверждения
- **rwnd** (receive window): сколько получатель готов принять
- **Effective window** = min(cwnd, rwnd)
- **ssthresh** (slow start threshold): порог переключения из slow start в congestion avoidance

### 3.3 Slow Start

При установке нового соединения cwnd начинается маленьким (обычно $10 \times \text{MSS}$ на современном Linux):

```
Начало: cwnd = IW (Initial Window = 10 MSS ≈ 14480 байт на Linux)
Каждый подтверждённый ACK: cwnd += MSS (удвоение за RTT)

RTT 0: cwnd = 1 MSS,  отправляем 1 сегмент
RTT 1: cwnd = 2 MSS,  отправляем 2 сегмента
RTT 2: cwnd = 4 MSS,  отправляем 4 сегмента
RTT 3: cwnd = 8 MSS   ...
...
До ssthresh → переходим в Congestion Avoidance
```

```python
class TCPCongestionControl:
    """Упрощённая симуляция congestion control (для иллюстрации)."""
    
    MSS = 1460  # Maximum Segment Size (байт)
    
    def __init__(self, initial_cwnd: int = 10):
        self.cwnd = initial_cwnd * self.MSS
        self.ssthresh = 65535  # Начальный порог
        self.in_slow_start = True
    
    def on_ack(self):
        """Обработка подтверждения."""
        if self.in_slow_start:
            # Slow Start: экспоненциальный рост
            self.cwnd += self.MSS
            if self.cwnd >= self.ssthresh:
                self.in_slow_start = False
        else:
            # Congestion Avoidance: линейный рост
            # cwnd += MSS * MSS / cwnd (примерно MSS за RTT)
            self.cwnd += self.MSS * self.MSS // self.cwnd
    
    def on_triple_dup_ack(self):
        """Fast Retransmit: 3 дублированных ACK."""
        self.ssthresh = max(self.cwnd // 2, 2 * self.MSS)
        self.cwnd = self.ssthresh  # Fast Recovery
        self.in_slow_start = False
    
    def on_timeout(self):
        """Таймаут — серьёзная потеря."""
        self.ssthresh = max(self.cwnd // 2, 2 * self.MSS)
        self.cwnd = self.MSS  # Начинаем с начала!
        self.in_slow_start = True
    
    @property
    def in_flight_limit(self) -> int:
        return self.cwnd
```

### 3.4 Congestion Avoidance (AIMD)

AIMD — Additive Increase / Multiplicative Decrease:

- **Additive Increase**: когда нет потерь — медленно увеличиваем cwnd (+MSS за RTT)
- **Multiplicative Decrease**: при потере — резко уменьшаем (/ 2)

```
cwnd
 ^
 |         /\
 |        /  \
 |       /    \  ← Потеря: cwnd/2
 |      /      \_______/\
 |     /                 \
 |    /                   \_____...
 |   /                          ← Slow Start
 +---+----------------------------> время
     |
   ssthresh
```

### 3.5 TCP Reno

Классический алгоритм (1990):

1. **Slow Start** до ssthresh
2. **Congestion Avoidance** (AIMD) выше ssthresh
3. **Fast Retransmit**: 3 дублированных ACK → немедленно повторить без ожидания таймаута
4. **Fast Recovery**: после fast retransmit → cwnd = ssthresh, продолжить congestion avoidance

### 3.6 TCP CUBIC (Linux default)

CUBIC (Linux 2.6.19+, 2006) — доминирующий алгоритм в интернете:

```
cwnd(t) = C × (t - K)³ + W_max

где:
- W_max: cwnd при последнем обнаружении перегрузки
- K: время до достижения W_max
- C: масштабирующая константа (0.4)
```

CUBIC быстрее восстанавливает cwnd после потери на высоких RTT и больших скоростях. На локальных сетях (низкий RTT) ведёт себя как Reno.

```bash
# Текущий алгоритм congestion control
sysctl net.ipv4.tcp_congestion_control
# cubic

# Доступные алгоритмы:
sysctl net.ipv4.tcp_available_congestion_control
# reno cubic bbr

# Изменить (нужен root):
sysctl -w net.ipv4.tcp_congestion_control=bbr
```

### 3.7 BBR (Bottleneck Bandwidth and RTT)

BBR (Google, 2016) — революционный подход. Вместо «угадывания» перегрузки по потерям, BBR оценивает реальную пропускную способность бутылочного горлышка и RTT:

```
Классический TCP:        BBR:
Потери → перегрузка      Bandwidth estimation → оптимальная скорость
                         RTT estimation → не заполнять очереди сверх нужного
```

BBR работает лучше на:
- Высоких RTT (WiFi, спутник, межконтинентальные соединения)
- Сетях с потерями не из-за перегрузки (беспроводные сети)
- Буферных роутерах (bufferbloat)

```
Пример: 100 Мбит/с, RTT = 100 мс
CUBIC: ~50-70 Мбит/с (из-за буфферных потерь и медленного восстановления)
BBR:   ~90-95 Мбит/с (точная оценка bandwidth)
```

```bash
# Включить BBR (Linux 4.9+):
sysctl -w net.ipv4.tcp_congestion_control=bbr

# Также нужен Fair Queue scheduler для BBR:
sysctl -w net.core.default_qdisc=fq

# Проверить:
ss -tin | grep bbr
```

---

## 4. Практические измерения

### 4.1 ss и tcp_info

```bash
# Детальная информация о TCP соединении
ss -tin dst 8.8.8.8

# Вывод включает:
# cwnd:10 ssthresh:7 bytes_sent:1000 bytes_retrans:0
# rtt:12.5/5.2 ato:40 mss:1460 pmtu:1500 rcvmss:1460

# Все TCP соединения с подробностями
ss -tnp -o state established

# Ожидающие соединения (SYN backlog)
ss -tn state syn-recv
```

```python
import socket
import struct

# Получение tcp_info через getsockopt (Linux)
TCP_INFO = 11  # номер опции

def get_tcp_info(sock: socket.socket) -> dict:
    """Получить детальную информацию о TCP соединении."""
    # Структура tcp_info (упрощённая, первые 7 полей)
    fmt = 'B' * 7 + 'I' * 24  # state + 23 uint32
    size = struct.calcsize(fmt)
    
    raw = sock.getsockopt(socket.IPPROTO_TCP, TCP_INFO, size)
    fields = struct.unpack(fmt, raw[:size])
    
    state_names = {
        1: 'ESTABLISHED', 2: 'SYN_SENT', 3: 'SYN_RECV',
        4: 'FIN_WAIT1', 5: 'FIN_WAIT2', 6: 'TIME_WAIT',
        7: 'CLOSE', 8: 'CLOSE_WAIT', 9: 'LAST_ACK',
        10: 'LISTEN', 11: 'CLOSING'
    }
    
    return {
        'state': state_names.get(fields[0], f'UNKNOWN({fields[0]})'),
        'rtt_us': fields[7 + 5],      # Smoothed RTT в микросекундах
        'rttvar_us': fields[7 + 6],   # RTT variance
        'snd_cwnd': fields[7 + 9],    # Congestion window
        'snd_ssthresh': fields[7 + 10],  # Slow start threshold
    }

# Пример использования:
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(('8.8.8.8', 80))
    info = get_tcp_info(s)
    print(f"State: {info['state']}, RTT: {info['rtt_us']/1000:.2f}ms, cwnd: {info['snd_cwnd']}")
```

### 4.2 Измерение throughput

```python
import socket
import time
import threading

def throughput_server(host: str, port: int, duration: int = 10):
    """Сервер для измерения throughput."""
    total_bytes = 0
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(1)
        
        conn, addr = s.accept()
        start = time.time()
        
        while time.time() - start < duration:
            data = conn.recv(65536)
            if not data:
                break
            total_bytes += len(data)
        
        elapsed = time.time() - start
        throughput_mbps = (total_bytes * 8) / (elapsed * 1_000_000)
        print(f"Throughput: {throughput_mbps:.1f} Mbit/s")

def throughput_client(host: str, port: int, duration: int = 10):
    """Клиент для измерения throughput."""
    buffer = b'x' * 65536  # 64 КБ буфер
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        
        start = time.time()
        sent = 0
        
        while time.time() - start < duration:
            n = s.send(buffer)
            sent += n
        
        elapsed = time.time() - start
        print(f"Sent: {sent / 1_000_000:.1f} MB in {elapsed:.1f}s")
```

---

## 5. Важные TCP настройки Linux

```bash
# Размер сокетных буферов
sysctl net.core.rmem_max          # Max receive buffer
sysctl net.core.wmem_max          # Max send buffer
sysctl net.ipv4.tcp_rmem          # Min, default, max receive buffer
sysctl net.ipv4.tcp_wmem          # Min, default, max send buffer

# Рекомендации для high-throughput:
sysctl -w net.core.rmem_max=134217728        # 128 МБ
sysctl -w net.core.wmem_max=134217728        # 128 МБ
sysctl -w net.ipv4.tcp_rmem="4096 87380 134217728"
sysctl -w net.ipv4.tcp_wmem="4096 65536 134217728"

# TCP fast open (TFO) - данные в SYN (сокращение RTT)
sysctl -w net.ipv4.tcp_fastopen=3  # 1=client, 2=server, 3=both

# TIME_WAIT recycling (осторожно!)
sysctl net.ipv4.tcp_tw_reuse=1  # Позволить reuse TIME_WAIT для новых соединений

# Maximum segment lifetime
sysctl net.ipv4.tcp_fin_timeout=60  # FIN_WAIT_2 timeout
```

---

## Заключение

Three-way handshake и congestion control — два столпа, на которых держится надёжность и производительность TCP. Понимание этих механизмов критично для диагностики производительности, настройки серверов и проектирования сетевых приложений.

**Ключевые выводы**:

1. **Three-way handshake**: SYN → SYN-ACK → ACK. Устанавливает начальные ISN обоих сторон. SYN cookies защищают от SYN flood.

2. **TIME_WAIT**: $2 \times \text{MSL}$ (120 секунд) после активного закрытия. Нормально — не «лишние» соединения. `SO_REUSEADDR` для серверов.

3. **Slow Start**: начинаем с маленького cwnd, экспоненциально растём до ssthresh.

4. **AIMD**: линейный рост + резкое уменьшение при потере. Основа всех алгоритмов.

5. **CUBIC** (Linux default): кубическая функция восстановления — быстрее при большом RTT.

6. **BBR**: оценка bandwidth вместо реакции на потери. Значительно лучше на связях с задержками.

---

## Литература и источники

1. RFC 793. Transmission Control Protocol. IETF. https://tools.ietf.org/html/rfc793
2. RFC 5681. TCP Congestion Control. IETF. https://tools.ietf.org/html/rfc5681
3. Cardwell, N. et al. (2016). BBR: Congestion-Based Congestion Control. *ACM Queue*. https://queue.acm.org/detail.cfm?id=3022184
4. Ha, S., Rhee, I., & Xu, L. (2008). CUBIC: A New TCP-Friendly High-Speed TCP Variant. *ACM SIGOPS*.
5. RFC 4987. TCP SYN Flooding Attacks and Common Mitigations. IETF. https://tools.ietf.org/html/rfc4987
6. Stevens, W. R. (1994). *TCP/IP Illustrated, Volume 1*. Addison-Wesley.
7. Linux tcp(7) man page. https://man7.org/linux/man-pages/man7/tcp.7.html
8. Grigorik, I. (2013). *High Performance Browser Networking*. O'Reilly. https://hpbn.co/
9. Wikipedia. TCP congestion control. https://en.wikipedia.org/wiki/TCP_congestion_control
10. Jacobson, V. (1988). Congestion avoidance and control. *ACM SIGCOMM*.
