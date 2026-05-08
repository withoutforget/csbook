# perf, eBPF, DTrace — инструменты заглянуть внутрь работающей системы

Представьте, что вы можете остановить работающий авиалайнер в полёте, просканировать каждую деталь и продолжить полёт — без пассажиров, заметивших остановку. Именно такую возможность предоставляют современные инструменты динамической трассировки: perf, DTrace и eBPF. Они позволяют исследовать работающую систему с минимальным вмешательством и практически без влияния на производительность.

## Linux perf: швейцарский нож производительности

`perf` — основной инструмент профилирования в Linux, встроенный в ядро. Он использует hardware performance counters процессора (PMU — Performance Monitoring Unit) и программные tracepoints ядра.

### Аппаратные счётчики производительности

Современные процессоры Intel/AMD имеют встроенные счётчики, считающие аппаратные события:

```bash
# Посмотреть доступные события
perf list

# Ключевые аппаратные события:
# cpu-cycles: тактовые циклы
# instructions: выполненные инструкции
# cache-misses: промахи кеша
# branch-misses: неправильные предсказания ветвлений
# page-faults: страничные ошибки (major + minor)
# context-switches: переключения контекста
```

### perf stat: статистика выполнения

```bash
# Базовая статистика для команды
perf stat ls /tmp

# Вывод:
#  Performance counter stats for 'ls /tmp':
#
#           1.23 msec task-clock                #    0.847 CPUs utilized
#              1      context-switches          #    0.813 K/sec
#              0      cpu-migrations            #    0.000 K/sec
#             76      page-faults               #   61.707 K/sec
#      1,234,567      cycles                    #    1.003 GHz
#      2,345,678      instructions              #    1.90  insn per cycle
#        123,456      branches                  #  100.211 M/sec
#          1,234      branch-misses             #    1.00% of all branches
#
#       0.001456 seconds time elapsed

# Ключевые метрики:
# IPC (Instructions Per Cycle) = instructions / cycles
# IPC > 2: хорошо; IPC < 1: плохо (много stalls)
# branch-misses > 5%: проблемы с предсказателем ветвлений
# cache-misses: важно для data-intensive кода
```

```bash
# Детальная статистика по кешу
perf stat -e cache-misses,cache-references,instructions,cycles \
    ./my_program

# Анализ memory stalls (ожидания памяти)
perf stat -e mem-loads,mem-stores,LLC-loads,LLC-load-misses ./my_program
# LLC = Last Level Cache (обычно L3)
# LLC-load-misses > 10%: программа страдает от cache thrashing
```

### perf record & report: CPU профилирование

```bash
# Записать CPU профиль на 30 секунд (-g = call graph)
perf record -F 99 -g -p <PID> -- sleep 30
# -F 99: 99 семплов/секунду (не 100 — чтобы избежать синхронизации с таймерами 100Hz)

# Профилировать всю систему (-a) на 10 секунд
perf record -F 99 -ag -- sleep 10

# Интерактивный просмотр
perf report

# Просмотр в интерфейсе TUI
perf report --tui

# Генерация flame graph (требует FlameGraph scripts)
perf script | stackcollapse-perf.pl | flamegraph.pl > cpu_flame.svg
```

### perf top: мониторинг в реальном времени

```bash
# Топ функций по CPU в реальном времени
perf top

# Топ по конкретным событиям
perf top -e cache-misses

# Аннотированный дизасм (нажать Enter на функции в perf top)
# Показывает assembly с % времени для каждой инструкции
```

### perf trace: трейсинг системных вызовов

```bash
# Трассировка системных вызовов (альтернатива strace, намного быстрее)
perf trace -p <PID>

# Только определённые syscalls
perf trace -e read,write,open,close -p <PID>

# Статистика syscalls за 10 секунд
perf trace --summary -p <PID> -- sleep 10

# Вывод:
# syscall    calls    total       min       avg       max
# read       12345  1.234s     0.01ms    0.10ms    5.00ms
# write       5678  0.567s     0.02ms    0.10ms    2.00ms
# epoll_wait   234  9.876s     0.01ms   42.21ms  100.00ms
```

## DTrace: зонд-система на основе безопасных скриптов

DTrace создана в Sun Microsystems в 2003 году. Это первая система динамической трассировки, которая могла безопасно работать в production без перекомпиляции ядра. Доступна на Solaris, macOS, FreeBSD.

### Архитектура DTrace

DTrace работает на основе **провайдеров** (providers), которые предоставляют **пробы** (probes). Скрипт DTrace подписывается на пробы и выполняет действия при их срабатывании.

```dtrace
/* Базовый DTrace скрипт: считаем syscalls в секунду */
syscall:::entry
{
    @calls[probefunc] = count();
}

tick-1sec
{
    printa(@calls);
    clear(@calls);
}
```

```bash
# macOS: трейсинг системных вызовов конкретного процесса
sudo dtrace -n 'syscall:::entry /pid == $target/ { @[probefunc] = count(); }' \
    -c "python myapp.py"

# Трассировка файловых операций
sudo dtrace -n 'syscall::open*:entry { printf("%s\n", copyinstr(arg0)); }'

# Измерение latency системных вызовов
sudo dtrace -n '
syscall:::entry { self->ts = timestamp; }
syscall:::return /self->ts/ {
    @[probefunc] = quantize(timestamp - self->ts);
    self->ts = 0;
}'
```

### DTrace на macOS для профилирования

```bash
# Профилирование CPU на macOS (sampling)
sudo dtrace -n '
profile-997hz
/pid == $target/
{
    @[ustack()] = count();
}' -c "python myapp.py"

# Flame graph из DTrace (через Brendan Gregg scripts)
sudo dtrace -x ustackframes=100 \
    -n 'profile-97hz /execname == "python3"/ { @[ustack()] = count(); }' \
    -o out.user_stacks -- sleep 30

stackcollapse.pl out.user_stacks | flamegraph.pl > dtrace_flame.svg
```

## eBPF: революция в наблюдаемости Linux

**eBPF (extended Berkeley Packet Filter)** — технология, которую многие называют революционной. Это JIT-компилируемые программы, выполняющиеся непосредственно в ядре Linux, без изменения кода ядра и с гарантиями безопасности.

### История: от BPF к eBPF

```
1992: BPF (Berkeley Packet Filter) — tcpdump использует для фильтрации пакетов
2013: eBPF — расширение до universal kernel VM
2015: Включён в Linux mainline (kernel 3.18)
2016-2020: Революция инструментов — bcc, bpftrace
2020+: eBPF как замена kernel modules, networking (Cilium), security (Falco)
```

### Что делает eBPF уникальным

```
Традиционный подход:
  Проблема: "Хочу измерить latency каждого syscall"
  Решение: Добавить printk() в ядро → перекомпилировать ядро →
           перезагрузить сервер → потерять production доступность
  Стоимость: дни работы, недоступность сервиса

eBPF подход:
  bpftrace -e 'tracepoint:syscalls:sys_enter_read { @start[tid] = nsecs; }
               tracepoint:syscalls:sys_exit_read  { @ns = hist(nsecs - @start[tid]); }'
  Стоимость: 30 секунд, нулевой downtime
```

### eBPF Верификатор: гарантии безопасности

Перед загрузкой eBPF программы в ядро, верификатор проверяет:
1. Нет бесконечных циклов (ограниченное число инструкций)
2. Нет доступа за границы массивов
3. Нет использования неинициализированной памяти
4. Программа завершится (нет рекурсии)

```c
// Простая eBPF программа (C, компилируется через clang -target bpf)
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

// BPF map для хранения данных
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, u32);     // PID
    __type(value, u64);   // Timestamp
} start_times SEC(".maps");

// Прикрепляем к tracepoint sys_enter_read
SEC("tracepoint/syscalls/sys_enter_read")
int trace_enter_read(struct trace_event_raw_sys_enter *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 ts = bpf_ktime_get_ns();
    bpf_map_update_elem(&start_times, &pid, &ts, BPF_ANY);
    return 0;
}

// Прикрепляем к tracepoint sys_exit_read
SEC("tracepoint/syscalls/sys_exit_read")
int trace_exit_read(struct trace_event_raw_sys_exit *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 *start = bpf_map_lookup_elem(&start_times, &pid);
    
    if (start) {
        u64 duration_ns = bpf_ktime_get_ns() - *start;
        bpf_printk("read() latency: %llu ns\n", duration_ns);
        bpf_map_delete_elem(&start_times, &pid);
    }
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
```

## BCC Toolkit: готовые eBPF инструменты

BCC (BPF Compiler Collection) — набор готовых инструментов для анализа производительности:

```bash
# Установка
apt install bpfcc-tools  # Debian/Ubuntu
# или
pip install bcc

# === execsnoop: наблюдение за запуском процессов ===
sudo execsnoop
# PCOMM            PID    PPID RET ARGS
# python3          12345  1000   0 /usr/bin/python3 myapp.py

# === opensnoop: какие файлы открываются ===
sudo opensnoop -p <PID>
# PID    COMM               FD ERR PATH
# 12345  python3             4   0 /etc/hosts
# 12345  python3             5   0 /var/log/app.log

# === tcplife: lifecycle TCP соединений ===
sudo tcplife
# PID   COMM       LADDR           LPORT RADDR           RPORT TX_KB RX_KB MS
# 12345 python3    10.0.0.1        54321 10.0.0.2        80      1    10    52

# === biolatency: latency диска ===
sudo biolatency 10
# Historgram показывает распределение latency I/O операций

# === funclatency: latency произвольных функций ===
sudo funclatency -p 12345 'python3:dict_get'

# === profile: CPU flame graph ===
sudo profile -adf -F 99 30 > perf.data
# (затем конвертируем в flame graph)

# === tcptop: топ TCP потоков ===
sudo tcptop 1

# === softirqs: время в software interrupts ===
sudo softirqs 10
```

### BCC Python API

```python
# Собственные eBPF программы через Python BCC API
from bcc import BPF
import ctypes

# eBPF программа для измерения latency HTTP запросов
bpf_code = """
#include <uapi/linux/ptrace.h>

BPF_HASH(start, u32);
BPF_HISTOGRAM(dist);

int trace_entry(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid();
    u64 ts = bpf_ktime_get_ns();
    start.update(&pid, &ts);
    return 0;
}

int trace_return(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid();
    u64 *tsp = start.lookup(&pid);
    
    if (tsp != 0) {
        u64 delta = bpf_ktime_get_ns() - *tsp;
        dist.increment(bpf_log2l(delta));
        start.delete(&pid);
    }
    return 0;
}
"""

b = BPF(text=bpf_code)

# Прикрепляем к uprobe (user-space probe)
# Трассируем функцию handle_request в Python приложении
b.attach_uprobe(name="/usr/bin/python3", 
                sym="PyEval_EvalFrameEx",
                fn_name="trace_entry")
b.attach_uretprobe(name="/usr/bin/python3",
                   sym="PyEval_EvalFrameEx",
                   fn_name="trace_return")

import time
time.sleep(10)

# Вывод гистограммы latency
print("Distribution of function latency (nanoseconds):")
b["dist"].print_log2_hist("nsecs")
```

## bpftrace: высокоуровневый язык для eBPF

bpftrace — упрощённый язык (похожий на awk/DTrace) для быстрого написания eBPF программ.

```bash
# Синтаксис: probe /filter/ { action }

# === Базовые примеры ===

# Считать системные вызовы по имени
sudo bpftrace -e 'tracepoint:syscalls:sys_enter_* { @[probe] = count(); }'

# Latency read() в виде гистограммы
sudo bpftrace -e '
tracepoint:syscalls:sys_enter_read { @start[tid] = nsecs; }
tracepoint:syscalls:sys_exit_read  
/@start[tid]/
{
  @us = hist((nsecs - @start[tid]) / 1000);  // в микросекундах
  delete(@start[tid]);
}'

# Топ 10 process по CPU
sudo bpftrace -e 'profile:hz:99 { @[comm] = count(); } 
                  interval:s:10 { print(@); clear(@); exit(); }'

# Трассировка открытия файлов с путями
sudo bpftrace -e '
tracepoint:syscalls:sys_enter_openat 
{
  printf("%s opened: %s\n", comm, str(args->filename));
}'

# Измерение latency TCP соединений
sudo bpftrace -e '
kprobe:tcp_connect { @start[tid] = nsecs; }
kretprobe:tcp_connect 
/@start[tid]/
{
  printf("TCP connect latency: %d us\n", (nsecs - @start[tid]) / 1000);
  delete(@start[tid]);
}'
```

```bash
# === Более сложные скрипты ===

# Профилирование сетевого трафика по процессам
sudo bpftrace -e '
kprobe:tcp_sendmsg { @send[comm] += arg2; }
kprobe:tcp_recvmsg { @recv[comm] += arg2; }
interval:s:5 {
  printf("\n--- TCP Traffic (5s) ---\n");
  print(@send);
  print(@recv);
  clear(@send); clear(@recv);
}'

# Находим медленные block I/O операции (> 10ms)
sudo bpftrace -e '
kprobe:blk_account_io_start { @start[arg0] = nsecs; }
kprobe:blk_account_io_done 
/@start[arg0]/
{
  $latency_us = (nsecs - @start[arg0]) / 1000;
  if ($latency_us > 10000) {  // > 10ms
    printf("Slow I/O: %d us on device %d\n", $latency_us, arg0);
  }
  delete(@start[arg0]);
}'
```

## eBPF в Production: Cilium и Falco

### Cilium: сетевая безопасность на eBPF

```bash
# Cilium использует eBPF для:
# - Сетевые политики (L3/L4/L7)
# - Load balancing без kube-proxy
# - Observability (Hubble)

# Hubble: сетевая observability через eBPF
hubble observe --namespace production
# TIMESTAMP             SOURCE                     DESTINATION            TYPE
# 2024-01-15 10:00:01   production/order-service   production/db:5432     TCP SYN
# 2024-01-15 10:00:01   production/db:5432         production/order-service SYNACK

# Flow statistics
hubble observe --namespace production --type l7 --last 100
```

### Falco: security monitoring через eBPF

```yaml
# Falco: обнаружение аномального поведения через eBPF
# Правило: предупреждать если процесс открывает /etc/passwd

- rule: Read sensitive file
  desc: Process read a sensitive file
  condition: >
    (open_read and sensitive_files)
    and not proc.name in (known_readers)
  output: >
    Sensitive file opened for reading
    (user=%user.name command=%proc.cmdline file=%fd.name)
  priority: WARNING
```

## Практические примеры диагностики

### Диагностика: почему MySQL медленный?

```bash
# Шаг 1: Убедимся что проблема в MySQL, не в сети
perf stat -e instructions,cycles,cache-misses -p $(pgrep mysqld)

# Шаг 2: Какие функции занимают CPU?
perf record -F 99 -p $(pgrep mysqld) -g -- sleep 30
perf report --sort=dso,symbol | head -30

# Шаг 3: Есть ли lock contention?
sudo bpftrace -e '
kprobe:mutex_lock_slow { @[comm, kstack] = count(); }
interval:s:5 { print(@); }'

# Шаг 4: Latency disk I/O
sudo biolatency -Q 5
# Если диск: P99 > 10ms — это проблема
```

### Диагностика: утечка памяти в production

```bash
# Шаг 1: Мониторинг аллокаций через eBPF
sudo bpftrace -e '
uprobe:/lib/x86_64-linux-gnu/libc.so.6:malloc 
{
  @allocs[ustack()] = sum(arg0);
}
interval:s:10 {
  print(@allocs);
  clear(@allocs);
}'

# Шаг 2: Трассировка mmap (большие аллокации)
sudo bpftrace -e '
tracepoint:syscalls:sys_enter_mmap 
/args->len > 1024*1024/  // > 1MB
{
  printf("mmap %d MB by %s\n", args->len / 1024 / 1024, comm);
  print(ustack());
}'
```

### Диагностика: медленные сетевые вызовы

```bash
# Latency TCP соединений по dst IP
sudo bpftrace -e '
kprobe:tcp_v4_connect { @start[tid] = nsecs; }
kretprobe:tcp_v4_connect 
/@start[tid]/
{
  $us = (nsecs - @start[tid]) / 1000;
  if ($us > 1000) {  // > 1ms
    printf("Slow TCP connect: %d us from %s\n", $us, comm);
  }
  delete(@start[tid]);
}'

# Ретрансмиты TCP (потеря пакетов)
sudo bpftrace -e '
kprobe:tcp_retransmit_skb 
{
  @retransmits[comm] = count();
}'
```

## Сравнение инструментов

| Инструмент | ОС | Тип | Overhead | Use Case |
|------------|-----|-----|----------|----------|
| perf | Linux | Sampling + Tracing | Низкий | CPU profile, hardware counters |
| DTrace | Solaris/macOS/FreeBSD | Probe-based | Низкий | Universal tracing |
| eBPF/BCC | Linux 4.1+ | Dynamic | Минимальный | Production debugging |
| bpftrace | Linux 4.9+ | High-level eBPF | Минимальный | Quick investigation |
| strace | Linux | Ptrace | Очень высокий | Syscall debugging (dev only) |
| gprof | Linux | Instrumentation | Средний | C/C++ profiling |
| Valgrind | Linux/macOS | Full simulation | 10-50x | Memory debugging |

**Ключевое правило:** `strace` нельзя использовать в production под нагрузкой — overhead 100x. `perf trace` делает то же самое с overhead < 5%.

## Заключение

Возможность заглядывать внутрь работающей системы без остановки и без изменения кода — одно из величайших достижений системного программирования последних десятилетий.

- **perf** — для системного профилирования CPU и hardware counters на Linux
- **DTrace** — для probe-based трейсинга на Solaris/macOS/FreeBSD
- **eBPF** — революционная технология для production debugging, networking, security

eBPF заслуживает особого внимания: это не просто инструмент трассировки, это новая парадигма расширения ядра Linux без его изменения. Cilium, Falco, Pixie — всё это построено на eBPF. Понимание eBPF становится обязательным для системных программистов, SRE и инженеров по безопасности.

## Литература

1. **Gregg, Brendan** — «BPF Performance Tools: Linux System and Application Observability». Pearson, 2019. ISBN: 978-0136554820
2. **Gregg, Brendan** — «Systems Performance: Enterprise and the Cloud», 2nd ed. Pearson, 2020. ISBN: 978-0136820154
3. **Gregg, Brendan; Mauro, Jim** — «DTrace: Dynamic Tracing in Oracle Solaris, Mac OS X and FreeBSD». Prentice Hall, 2011. ISBN: 978-0132091510
4. **McCanne, Steven; Jacobson, Van** — «The BSD Packet Filter: A New Architecture for User-level Packet Capture». USENIX Winter 1993
5. **eBPF.io** — «What is eBPF?»: https://ebpf.io/what-is-ebpf/
6. **Linux Kernel Documentation** — «BPF Documentation»: https://www.kernel.org/doc/html/latest/bpf/
7. **bpftrace Reference Guide** — https://github.com/bpftrace/bpftrace/blob/master/docs/reference_guide.md
8. **Cilium Documentation** — «eBPF & Cilium»: https://docs.cilium.io/en/stable/overview/intro/
9. **Falco Documentation** — https://falco.org/docs/
10. **Calavera, David; Fontana, Lorenzo** — «Linux Observability with BPF». O'Reilly, 2019. ISBN: 978-1492050193
