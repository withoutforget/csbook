# Page Fault и Swap

## Введение

Когда программа обращается к странице памяти, которой нет в RAM, происходит page fault — особый тип исключения, который ядро обрабатывает незаметно для приложения. Это один из самых частых механизмов в ОС: каждое новое выделение памяти, каждый mmap, каждый stack frame — всё начинается с page fault.

Swap — механизм расширения «виртуальной» RAM за счёт дискового пространства. Когда RAM полна, ядро выгружает редко используемые страницы на диск, освобождая место. Это позволяет системе работать даже при нехватке физической памяти — но ценой производительности: доступ к swap в тысячи раз медленнее RAM.

Понимание page fault и swap критично для: оптимизации потребления памяти, диагностики проблем производительности, настройки серверов (swap или нет?), понимания OOM killer.

---

## 1. Minor и Major Page Fault

### 1.1 Minor Page Fault (мягкий промах)

Страница не присутствует в page table данного процесса, но **находится в памяти** (в page cache или ещё не выделена):

**Случаи minor fault:**
1. **Первое обращение к анонимной странице** (heap, stack): ядро выделяет физическую страницу, заполняет нулями, устанавливает PTE.
2. **CoW (Copy-on-Write)**: запись в shared страницу → ядро копирует страницу, даёт процессу собственную копию.
3. **Страница в page cache** (shared library, mmap'd file): страница уже в RAM (другой процесс загрузил), просто добавить mapping.

Minor fault — быстрый (< 1 мкс): никакого I/O, только выделение страницы и изменение page table.

### 1.2 Major Page Fault (жёсткий промах)

Страница не присутствует ни в page table, **ни в памяти** — нужно загрузить с диска:

**Случаи major fault:**
1. **Demand paging при первом запуске**: ядро не загружает всю программу сразу — страницы загружаются по мере обращения.
2. **Swap-in**: страница была выгружена в swap → нужно загрузить обратно.
3. **mmap'd file, первое обращение**: страница файла не в page cache → читаем с диска.

Major fault — медленный (1-10 мс): I/O с диска.

```bash
# Подсчёт page faults:
/usr/bin/time -v ./program
# ...
# Major (requiring I/O) page faults: 12
# Minor (reclaiming a frame) page faults: 4521

# С perf:
perf stat -e page-faults,major-faults,minor-faults ./program

# Для конкретного PID:
cat /proc/1234/stat | awk '{print "minor:", $10, "major:", $12}'
```

---

## 2. Demand Paging

### 2.1 Принцип

Когда ядро выполняет `execve()` или `mmap()`, оно **не** загружает страницы немедленно. Вместо этого:

1. Создаются VMA (Virtual Memory Areas) — записи, описывающие диапазоны адресов
2. Page table остаётся **пустой** (PTE = not present)
3. При первом обращении к любому адресу → page fault → ядро загружает именно эту страницу

```python
# Демонстрация demand paging в Python:
import mmap
import time

# Создать файл 1 GB:
with open('/tmp/large.bin', 'wb') as f:
    f.write(b'\x00' * 1024 * 1024 * 1024)

start = time.perf_counter()

# mmap всего файла — МГНОВЕННО (нет реального чтения):
with open('/tmp/large.bin', 'rb') as f:
    data = mmap.mmap(f.fileno(), 0, mmap.ACCESS_READ)
    mmap_time = time.perf_counter() - start
    print(f"mmap: {mmap_time*1000:.1f} ms")  # ~0 ms
    
    # Читать страницы — вот тут происходят major faults:
    start = time.perf_counter()
    checksum = sum(data[i*4096] for i in range(1024))  # 1024 страницы
    read_time = time.perf_counter() - start
    print(f"Read 4 MB: {read_time*1000:.1f} ms")  # ~несколько мс (disk I/O)
```

### 2.2 Prepopulate и mlock

```c
// Принудительно загрузить страницы сейчас (для real-time, чтобы избежать fault позже):
#include <sys/mman.h>

// madvise: подсказать ядру о паттерне доступа:
madvise(ptr, size, MADV_WILLNEED);     // загрузи заранее
madvise(ptr, size, MADV_SEQUENTIAL);   // последовательный доступ → prefetch
madvise(ptr, size, MADV_DONTNEED);     // можешь выгрузить (free уже не нужное)
madvise(ptr, size, MADV_HUGEPAGE);     // использовать huge pages

// mlock: заблокировать страницы в RAM (не выгружать в swap):
mlock(ptr, size);    // заблокировать
munlock(ptr, size);  // разблокировать

// Заблокировать весь процесс:
mlockall(MCL_CURRENT | MCL_FUTURE);
// MCL_CURRENT: все текущие страницы
// MCL_FUTURE: все будущие страницы (не будут выгружаться)
// Нужны root или CAP_IPC_LOCK
```

---

## 3. Swap

### 3.1 Что такое swap

Swap (подкачка) — дисковое пространство, используемое для хранения страниц памяти, выгруженных из RAM:

```
RAM: 8 GB
Swap: 8 GB
Итого "доступно": 16 GB (но swap в 100-1000× медленнее RAM!)
```

Swap может быть:
- **Swap partition**: отдельный раздел диска (быстрее, нет overhead ФС)
- **Swap file**: файл в существующей ФС (гибче, можно изменить размер)

```bash
# Создать swap файл:
dd if=/dev/zero of=/swapfile bs=1M count=4096  # 4 GB
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# Статус swap:
swapon --show
# NAME      TYPE  SIZE   USED PRIO
# /dev/sda2 partition 8G  1.2G  -2
# /swapfile file    4G   0     -3

free -h
#              total   used    free    shared  buff/cache  available
# Mem:         15Gi    4.2Gi   8.1Gi   342Mi   2.8Gi       10Gi
# Swap:        12Gi    1.2Gi   10Gi
```

### 3.2 Swappiness

`vm.swappiness` — параметр ядра, определяющий агрессивность выгрузки страниц:

```bash
# Текущее значение:
cat /proc/sys/vm/swappiness
# 60 (значение по умолчанию)

# Значения:
# 0   = не использовать swap пока есть хоть немного RAM (но не "никогда")
# 10  = агрессивно использовать page cache, мало swap
# 60  = баланс (по умолчанию для десктопов/серверов)
# 100 = агрессивно свопировать, активно освобождать RAM для page cache

# Для сервера БД (хотим минимизировать latency):
echo 10 > /proc/sys/vm/swappiness
# Или через sysctl:
sysctl -w vm.swappiness=10

# Постоянно (через /etc/sysctl.conf):
echo "vm.swappiness=10" >> /etc/sysctl.conf
```

---

## 4. Алгоритмы замещения страниц

При нехватке RAM ядро должно выгрузить какую-то страницу. Какую?

### 4.1 OPT (Optimal) — теоретический оптимум

Выгружать страницу, которая дольше всего не будет нужна. Нереализуем (нужно знать будущее), но служит эталоном для сравнения.

### 4.2 LRU (Least Recently Used)

Выгружать страницу, к которой дольше всего не обращались. Хорошо аппроксимирует оптимальный.

Проблема: точный LRU требует обновления «временной метки» при **каждом** обращении к странице — слишком дорого.

### 4.3 Clock Algorithm (NFU, NRU)

Приближение LRU через бит Accessed (A) в PTE:

```
Страницы организованы в кольцо с указателем ("часовая стрелка"):

┌─[A=1]─[A=0]─[A=1]─[A=1]─[A=0]─┐
│  ↑ указатель                    │
└─────────────────────────────────┘

Алгоритм при нехватке страниц:
1. Посмотреть на страницу под указателем
2. Если A=0 → выгрузить эту страницу
3. Если A=1 → установить A=0, переместить указатель
4. Повторять
```

MMU автоматически устанавливает A=1 при обращении к странице. Ядро периодически сбрасывает A=0, чтобы определить «холодные» страницы.

### 4.4 Linux: LRU-2 Lists (Active + Inactive)

Linux использует двухуровневый LRU:

```
Active List:   "горячие" страницы (много обращений)
Inactive List: "холодные" страницы (кандидаты на выгрузку)

Новая страница → Inactive (пробный период)
Повторное обращение к Inactive → переместить в Active
Активных слишком много → "деградировать" часть Active → Inactive
Inactive освобождается при нехватке памяти
```

```bash
# Статистика LRU:
cat /proc/meminfo | grep -E 'Active|Inactive'
# Active(anon):    2345678 kB  ← анонимные (heap, stack) в active
# Inactive(anon):   456789 kB  ← анонимные в inactive (кандидаты на swap)
# Active(file):    1234567 kB  ← file-backed в active (page cache)
# Inactive(file):   345678 kB  ← file-backed в inactive (можно дропнуть)
```

### 4.5 Thrashing (Пробуксовка)

**Thrashing** — ситуация, когда система проводит больше времени на свопировании, чем на полезной работе:

```
Процесс нужно N страниц, но RAM только N/2:
→ Половина страниц всегда в swap
→ Каждое обращение → swap-in → нужно освободить место → swap-out другой страницы
→ 100% времени на IO с диском, 0% на вычисления
```

Решение: меньше процессов, больше RAM, или kill большие процессы (OOM killer).

---

## 5. OOM Killer

### 5.1 Когда срабатывает OOM Killer

Out-of-Memory Killer — последняя линия обороны Linux. Запускается когда:
- RAM исчерпана
- Swap исчерпан
- Невозможно выгрузить ещё страниц

Вместо kernel panic — убиваем один (или несколько) процессов.

### 5.2 Алгоритм выбора жертвы

Каждому процессу ядро вычисляет **oom_score** (0-1000):

```
oom_score ≈ (RAM use + swap use) * adjustment factors
```

**Факторы:**
- Большое потребление памяти → высокий score → вероятная жертва
- Долго работающий процесс → штраф (жалко убивать)
- Дочерний процесс → учитывается память родителя

```bash
# Просмотр oom_score:
cat /proc/1234/oom_score
# 856  ← высокий → будет убит первым

# Настройка приоритета OOM:
# oom_score_adj: -1000 до 1000
# -1000 = никогда не убивать (init, критические сервисы)
# 0     = по умолчанию
# 1000  = убивать первым

# Защитить важный процесс от OOM killer:
echo -1000 > /proc/$(pidof my_critical_service)/oom_score_adj

# Или через systemd:
[Service]
OOMScoreAdjust=-500
```

### 5.3 Диагностика OOM событий

```bash
# Найти OOM события в системном журнале:
dmesg | grep -i "oom\|killed process\|out of memory"

# Пример вывода при OOM kill:
# [12345.678] oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),
#             cpuset=/,mems_allowed=0,global_oom,
#             task_memcg=/user.slice/user-1000.slice,
#             task=chrome,pid=1234,uid=1000
# [12345.679] Out of memory: Killed process 1234 (chrome) total-vm:8234560kB,
#             anon-rss:4123456kB, file-rss:234567kB, shmem-rss:0kB,
#             UID:1000 pgtables:12345kB oom_score_adj:300

journalctl -k | grep -i oom | tail -20
```

---

## 6. Memory Overcommit

### 6.1 Принцип overcommit

Linux по умолчанию «обещает» больше памяти, чем есть физически. Когда процесс делает `malloc(1GB)`, ядро сразу возвращает успех — физические страницы выделяются позже (demand paging).

Это работает потому что:
- Многие процессы делают `malloc(large)` но реально используют мало
- fork() + exec() создаёт CoW копию — не нужно реальной памяти для кода

```bash
# Параметр overcommit:
cat /proc/sys/vm/overcommit_memory
# 0 = эвристика (по умолчанию): разрешить "разумный" overcommit
# 1 = всегда разрешать (malloc никогда не вернёт NULL)
# 2 = не разрешать сверх (RAM + swap * overcommit_ratio)

cat /proc/sys/vm/overcommit_ratio
# 50 = при mode 2: max commit = RAM + 50% swap

# Просмотр committed memory:
cat /proc/meminfo | grep Commit
# CommitLimit:    15678920 kB  ← максимум при mode 2
# Committed_AS:   12345678 kB  ← текущее обещание
```

### 6.2 Проблемы overcommit

```c
// Ложное ощущение безопасности:
void *p = malloc(4 * 1024 * 1024 * 1024LL);  // 4 GB
if (!p) { handle_error(); }
// При overcommit: p != NULL, даже если RAM только 2 GB!
// Ошибка возникнет позже при реальном использовании → OOM killer

// Решение для критических приложений:
// 1. vm.overcommit_memory = 2 (строгий режим)
// 2. mlock() для гарантии что страницы в RAM
// 3. Явная проверка /proc/meminfo перед большими аллокациями
```

---

## 7. Производительность swap

### 7.1 Swap убивает latency

Для сервисов с требованиями к latency (базы данных, real-time обработка) swap — враг:

```
HDD swap: seek time ~5мс, sequential ~100 MB/s
SSD swap: ~100 мкс, ~500 MB/s
NVMe swap: ~20 мкс, ~3000 MB/s

RAM: ~100 нс, ~50 GB/s

Даже NVMe swap в 200× медленнее RAM по latency!
```

### 7.2 Zswap и Zram

**zram** — сжатие страниц в RAM (вместо выгрузки на диск):

```bash
# Создать zram устройство (блок-устройство с сжатием):
modprobe zram
echo lz4 > /sys/block/zram0/comp_algorithm  # быстрый алгоритм
echo 4G  > /sys/block/zram0/disksize
mkswap /dev/zram0
swapon --priority 100 /dev/zram0  # высокий приоритет (предпочитаем zram над диском)

# Статистика сжатия:
cat /sys/block/zram0/mm_stat
# orig_data_size compr_data_size mem_used_total ...
# 4123456789    1234567890    1300000000    → 70% сжатие!
```

**zswap** — прозрачный кеш для swap в сжатой форме в RAM:

```bash
echo 1 > /sys/module/zswap/parameters/enabled
cat /sys/kernel/debug/zswap/stored_pages   # число страниц в zswap кеше
```

---

## 8. Практические рекомендации

### 8.1 Когда использовать swap

| Сценарий | Рекомендация |
|----------|-------------|
| Десктоп/ноутбук | Swap полезен: дает возможность продолжить при нехватке |
| Сервер БД (PostgreSQL, MySQL) | Минимальный swap или нет, vm.swappiness=1-10 |
| Контейнеры/K8s | Обычно отключают swap; Kubernetes требует это по умолчанию |
| Аудио/real-time | mlock, swappiness=0 |
| Cloud VM с 1 GB RAM | Swap необходим для базовой работы ОС |

### 8.2 Мониторинг swap активности

```bash
# Активность swap в реальном времени:
vmstat 1
# procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
#  r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
#  2  0      0 4567890 123456 2345678   0    0     5    12  456  789  5  2 93  0  0
# si = swap in (КБ/с), so = swap out (КБ/с)
# si>0 или so>0 → идёт свопирование!

# Топ процессов по swap:
for pid in /proc/[0-9]*; do
    pid_num="${pid##*/}"
    swap=$(grep VmSwap "${pid}/status" 2>/dev/null | awk '{print $2}')
    name=$(grep Name "${pid}/status" 2>/dev/null | awk '{print $2}')
    if [ -n "$swap" ] && [ "$swap" -gt 0 ]; then
        echo "${swap} kB - ${name} (PID ${pid_num})"
    fi
done | sort -rn | head -10
```

---

## Заключение

Page fault и swap — механизмы, делающие виртуальную память полноценной:

1. **Minor faults** — дешёвые, неизбежны при первом использовании памяти, CoW. Не стоит беспокоиться.

2. **Major faults** — дорогие (IO с диска). При warmup фазе нормальны, во время работы — признак проблем.

3. **Swap** — расширяет доступную память, но убивает latency. Для серверов с жёсткими требованиями к времени отклика: отключить или использовать только zram/NVMe swap.

4. **OOM killer** — последняя линия обороны. Настройте `oom_score_adj` для критических сервисов.

5. **Thrashing** — симптом недостаточности RAM. Решение: больше RAM, меньше процессов, cgroup memory limits.

---

## Литература и источники

1. Gorman, M. (2004). *Understanding the Linux Virtual Memory Manager*. — https://www.kernel.org/doc/gorman/

2. Linux Kernel Documentation. *Memory Management*. — https://www.kernel.org/doc/html/latest/admin-guide/mm/index.html

3. Kerrisk, M. (2010). *The Linux Programming Interface*. — Глава 50: Virtual Memory Operations.

4. Wikipedia. *Page replacement algorithm*. — https://en.wikipedia.org/wiki/Page_replacement_algorithm

5. Wikipedia. *Thrashing (computer science)*. — https://en.wikipedia.org/wiki/Thrashing_(computer_science)

6. Linux. *vm.swappiness documentation*. — https://www.kernel.org/doc/html/latest/admin-guide/sysctl/vm.html

7. Oracle. *zswap documentation*. — https://www.kernel.org/doc/html/latest/admin-guide/mm/zswap.html

8. Brendan Gregg. *Linux Performance: Memory*. — https://www.brendangregg.com/linuxperf.html

9. Silberschatz, A., Galvin, P. B., & Gagne, G. (2018). *Operating System Concepts* (10th ed.). — Chapter 10: Virtual Memory.

10. Facebook. *zram for Android*. — https://source.android.com/docs/core/perf/zram
