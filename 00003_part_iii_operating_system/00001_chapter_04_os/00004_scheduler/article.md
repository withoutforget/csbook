# Планировщик ОС

## Введение

На вашем компьютере одновременно «работают» десятки программ: браузер, музыкальный плеер, редактор, фоновые сервисы. Но физических CPU-ядер, например, 8. Как 8 ядер обслуживают 200 процессов? Ответ — планировщик (scheduler).

Планировщик — одна из ключевых подсистем ОС, решающая: какой процесс/поток выполняется прямо сейчас, и когда его сменить? От качества планировщика зависит отзывчивость системы (пользователь не видит «зависания»), справедливость (ни один процесс не голодает), эффективность (высокая утилизация CPU), и предсказуемость (для real-time задач).

---

## 1. Основные концепции

### 1.1 Вытесняющее vs Кооперативное планирование

**Кооперативное (cooperative) планирование:** процесс сам решает, когда отдать CPU. Используется `yield()` или обращение к ОС. Если процесс не уступает — он монополизирует CPU.

Проблема: один «нехороший» процесс зависает — вся система зависает. Использовалось в Windows 3.x, ранних версиях macOS (Mac OS 9).

**Вытесняющее (preemptive) планирование:** ОС принудительно снимает процесс с CPU через таймерное прерывание. Процесс не может «захватить» CPU навсегда.

Все современные ОС используют вытесняющее планирование. Частота timer interrupt: типично 100-1000 Hz (10мс — 1мс), настраивается `CONFIG_HZ` в Linux.

### 1.2 Квант времени (Time Quantum / Time Slice)

Квант — максимальное время непрерывного выполнения одного процесса до принудительного снятия. После кванта процесс может быть снят (если есть более приоритетные задачи) или продолжить (если очередь пуста).

Выбор кванта — компромисс:
- **Большой квант** (100мс+): меньше overhead от context switch, но хуже отзывчивость (между нажатием кнопки и реакцией может пройти 100мс).
- **Маленький квант** (1-10мс): высокая отзывчивость, но больше overhead (context switch несколько мкс, при очень малом кванте теряем 10%+ на переключения).

### 1.3 CPU-bound vs IO-bound процессы

**CPU-bound:** большую часть времени использует CPU (научные вычисления, компиляция, рендеринг). Редко блокируется на IO.

**IO-bound:** часто ждёт IO (сетевые серверы, GUI, БД). Большую часть времени в blocked состоянии.

Хороший планировщик должен:
- IO-bound процессы: давать CPU быстро после завершения IO (хорошая интерактивность)
- CPU-bound процессы: давать большие кванты (минимум overhead от переключений)

---

## 2. Алгоритмы планирования

### 2.1 FIFO / FCFS (First-Come, First-Served)

Процессы выполняются в порядке поступления. Без приоритетов, без вытеснения.

```
Очередь: P1(burst=8), P2(burst=4), P3(burst=2)

Timeline:
|  P1(8)  |P2(4)|P3(2)|
0         8    12    14

Среднее время ожидания: (0 + 8 + 12) / 3 = 6.67
```

Проблема — **convoy effect**: длинный процесс в начале очереди задерживает все короткие. Практически не используется для интерактивных задач.

### 2.2 Shortest Job First / Shortest Job Next (SJF)

Выбираем процесс с наименьшим burst time. Теоретически оптимален по среднему времени ожидания.

```
Очередь: P1(burst=8), P2(burst=4), P3(burst=2)

FIFO: avg wait = 6.67
SJF:  P3(2), P2(4), P1(8)
      avg wait = (0 + 2 + 6) / 3 = 2.67  ← лучше!
```

Проблема: **starvation** (голодание) длинных процессов при постоянном поступлении коротких. И — невозможно точно знать burst time заранее.

### 2.3 Round Robin (RR)

Каждый процесс получает квант q. После кванта — вытесняется и помещается в конец очереди.

```
Процессы: P1(burst=8), P2(burst=4), P3(burst=2), квант q=4

Timeline:
|P1(4)|P2(4)|P3(2)|P1(4)|
0     4     8    10    14

P1 заканчивает в 14, P2 в 8, P3 в 10
Среднее завершение: (14+8+10)/3 = 10.67
Среднее ожидание: (6+4+8)/3 = 6  (считая с конца последнего кванта)
```

Round Robin — основа большинства реальных планировщиков. Хороший баланс между отзывчивостью и справедливостью.

### 2.4 Priority Scheduling

Каждый процесс имеет приоритет. CPU получает процесс с наивысшим приоритетом.

**Проблема: starvation.** Низкоприоритетные процессы могут ждать вечно.

**Решение: Aging (старение).** Приоритет процесса постепенно растёт с ожиданием:

```
Каждую секунду в очереди: priority += 1
Через 20 секунд даже низкоприоритетный получает высокий приоритет
```

### 2.5 Multilevel Queue (MLQ)

Несколько очередей с разными приоритетами и алгоритмами:

```
Очередь 0 (Real-time):  FIFO, приоритет 99
Очередь 1 (System):     RR(10ms), приоритет 50
Очередь 2 (Interactive): RR(20ms), приоритет 20
Очередь 3 (Batch):      FCFS, приоритет 0

Процессы не перемещаются между очередями.
```

**Multilevel Feedback Queue (MLFQ):** процессы перемещаются между очередями в зависимости от поведения:

```
Новый процесс → Очередь 0 (q=8ms)
Исчерпал q в очереди 0 → понизить до очереди 1 (q=16ms)
Исчерпал q в очереди 1 → понизить до очереди 2 (q=32ms)
Заблокировался до исчерпания q → повысить

Идея: CPU-bound процессы опускаются вниз (медленные очереди)
      IO-bound процессы остаются наверху (быстрый отклик)
```

MLFQ используется в Windows (Priority Boost для форгрунд-приложений).

---

## 3. CFS — Completely Fair Scheduler (Linux)

Начиная с Linux 2.6.23 (2007), Linux использует CFS — революционный подход, отказавшийся от фиксированных квантов.

### 3.1 Идея: Virtual Runtime

CFS отслеживает `vruntime` — «виртуальное время выполнения» каждой задачи. Планировщик всегда выбирает задачу с наименьшим vruntime:

```
vruntime += actual_runtime * (NICE_0_LOAD / task_weight)
```

Задача с более высоким приоритетом (меньший nice или выше weight) — её vruntime растёт медленнее → она дольше считается «нуждающейся в CPU».

Процесс с nice = -20: weight = 88761, vruntime растёт медленно (бо́льшая доля)
Процесс с nice = 0:   weight = 1024, vruntime растёт нормально
Процесс с nice = +19: weight = 15, vruntime растёт быстро (маленькая доля)

### 3.2 Red-Black Tree

Все runnable задачи хранятся в красно-чёрном дереве, упорядоченном по vruntime:

```
         vruntime=100
        /             \
   vruntime=80     vruntime=120
   /     \           /       \
 v=70   v=90      v=110    v=140

Левый узел (v=70) = следующая задача для выполнения
Insert/Delete/Find-min: O(log n)
```

### 3.3 Scheduling Latency и Min Granularity

**Scheduling latency:** гарантированное время, через которое каждый runnable процесс получит CPU хоть раз. По умолчанию 6мс (SCHED_LATENCY_NS = 6,000,000 нс).

Если N процессов runnable, каждый получает `6мс / N` времени за период.

**Min granularity:** минимальный квант = 0.75мс (не разрезать бесконечно мелко при большом N).

```
N=1:   квант = 6мс
N=4:   квант = 1.5мс
N=8:   квант = 0.75мс (min granularity)
N=100: квант = 0.75мс (min granularity, не 0.06мс)
```

### 3.4 Idle и Wakeup

Когда задача просыпается (после IO, блокировки), её vruntime может устареть. CFS «компенсирует»: устанавливает vruntime = max(task_vruntime, min_vruntime - latency_target). Это даёт проснувшимся задачам приоритет без полного игнорирования времени.

### 3.5 CFS Groups и Bandwidth Control

cgroups v2 позволяет ограничить CPU для группы задач:

```bash
# Ограничить containerized process до 50% одного CPU:
echo "50000 100000" > /sys/fs/cgroup/mygroup/cpu.max
# 50000 = quota мкс за 100000 мкс период = 50% CPU

# Вес (пропорциональное распределение при конкуренции):
echo 512 > /sys/fs/cgroup/mygroup/cpu.weight  # в два раза меньше чем default (1024)
```

---

## 4. Real-Time Scheduling

### 4.1 SCHED_FIFO и SCHED_RR

Linux поддерживает RT политики:

```c
#include <sched.h>

// Установить RT приоритет:
struct sched_param param;
param.sched_priority = 50;  // 1 (низкий) ... 99 (высокий)

// SCHED_FIFO: выполняется пока не заблокируется или не уступит
pthread_setschedparam(tid, SCHED_FIFO, &param);

// SCHED_RR: RT + Round Robin (квант 0.1 секунды)
pthread_setschedparam(tid, SCHED_RR, &param);

// Приоритет: RT > Normal (CFS)
// RT процессы с приоритетом 1+ предвытесняют все normal процессы
```

**Опасность:** RT процесс с SCHED_FIFO и бесконечным циклом → система зависает.

**Защита:** CPU throttling для RT (`/proc/sys/kernel/sched_rt_budget_us`):

```bash
cat /proc/sys/kernel/sched_rt_period_us
# 1000000 (1 секунда)
cat /proc/sys/kernel/sched_rt_runtime_us
# 950000 (950мс из каждой секунды — 5% остаётся для normal задач)
```

### 4.2 SCHED_DEADLINE

Самый современный RT механизм в Linux (3.14+):

```c
// Параметры: runtime, deadline, period
struct sched_attr attr = {
    .sched_policy   = SCHED_DEADLINE,
    .sched_runtime  =  5 * 1000 * 1000,  // 5мс обработки
    .sched_deadline = 10 * 1000 * 1000,  // до 10мс
    .sched_period   = 20 * 1000 * 1000,  // каждые 20мс
};
syscall(SYS_sched_setattr, 0, &attr, 0);
```

Алгоритм EDF (Earliest Deadline First): всегда выполняется задача с ближайшим дедлайном.

### 4.3 Практическое применение RT

```c
// Аудио рендеринг (pulseaudio, JACK):
// - Нужно заполнить аудио буфер каждые 5мс (44100Hz, 256 samples)
// - Задержка > 5мс → слышимый артефакт (glitch)
// Решение: SCHED_FIFO, приоритет 70

// Промышленное управление (роботы, ЧПУ станки):
// - Обновление управляющих сигналов каждые 1мс
// - Пропуск → механическое повреждение
// Решение: SCHED_DEADLINE, PREEMPT_RT ядро
```

---

## 5. Context Switch — что происходит

### 5.1 Механизм context switch

```
Текущая задача (Task A):           Следующая задача (Task B):
Выполняется...                     В очереди

Timer interrupt:
  1. CPU сохраняет RFLAGS, RIP → в kernel stack Task A
     (аппаратно, при входе в ISR)
  
  2. Ядро входит в scheduler_tick()
  
  3. Решает: снять Task A? (квант исчерпан? есть более приоритетные?)
  
  4. Если да: context_switch(Task_A, Task_B):
  
     a. switch_mm(): Task_A.mm → Task_B.mm
        - Меняем page table base register (CR3 на x86)
        - CR3 change → TLB flush (если нет PCID оптимизации)
     
     b. switch_to():
        - Сохраняем caller-saved регистры Task A (rbx, rbp, r12-r15)
        - Сохраняем RSP Task A в task_struct
        - Загружаем RSP Task B из task_struct
        - Восстанавливаем регистры Task B
        - ret → Task B продолжает с места где остановился
```

### 5.2 TLB Flush при переключении

Смена address space (CR3) аннулирует весь TLB — дорогая операция:

```bash
# Измерить overhead context switch:
perf stat -e context-switches,tlb-flushes,tlb:tlb_flush -a ./workload

# Оптимизация: PCID (Process Context ID) — Linux 4.14+
# Каждый address space получает 12-bit ID
# TLB записи помечены PCID → смена CR3 не нужна TLB flush!
cat /proc/cpuinfo | grep pcid
# flags: ... pcid ...
```

### 5.3 Измерение стоимости context switch

```c
// Измерение через pipe (каждый pass = 2 context switch):
#include <unistd.h>
#include <time.h>

#define N 100000

int main() {
    int pipe1[2], pipe2[2];
    pipe(pipe1); pipe(pipe2);
    
    struct timespec start, end;
    
    if (fork() == 0) {
        // Дочерний: читает из pipe1, пишет в pipe2
        char buf;
        for (int i = 0; i < N; i++) {
            read(pipe1[0], &buf, 1);
            write(pipe2[1], &buf, 1);
        }
        exit(0);
    }
    
    // Родительский:
    clock_gettime(CLOCK_MONOTONIC, &start);
    char buf = 'x';
    for (int i = 0; i < N; i++) {
        write(pipe1[1], &buf, 1);
        read(pipe2[0], &buf, 1);
    }
    clock_gettime(CLOCK_MONOTONIC, &end);
    
    long ns = (end.tv_sec - start.tv_sec) * 1000000000L 
              + (end.tv_nsec - start.tv_nsec);
    printf("Context switch overhead: %ld ns\n", ns / (2 * N));
    // Типично: 1000-5000 нс (1-5 мкс)
    return 0;
}
```

---

## 6. Load Balancing в многоядерных системах

### 6.1 Per-CPU Run Queues

Linux использует отдельную run queue для каждого CPU (для scalability):

```
CPU 0 Run Queue:   [Task A] → [Task B] → [Task C]
CPU 1 Run Queue:   [Task D] → [Task E]
CPU 2 Run Queue:   [Task F] → [Task G] → [Task H] → [Task I]
CPU 3 Run Queue:   []  ← пустая!
```

Без балансировки: CPU 2 перегружен, CPU 3 простаивает.

### 6.2 Work Stealing

CFS реализует load balancing через периодическую проверку и «воровство» задач:

1. Каждые ~4мс: loadavg проверяет баланс между ядрами
2. Если CPU перегружен → другое ядро «крадёт» часть задач
3. NUMA-aware: сначала кражи внутри NUMA-узла (дешевле), потом между узлами

```bash
# Принудительная привязка процесса к ядру (без балансировки):
taskset -c 0,1 ./myprogram      # запустить на ядрах 0 и 1
taskset -c 2 -p 1234            # привязать PID 1234 к ядру 2

# Просмотр affinity:
taskset -p 1234
# pid 1234's current affinity mask: ff (все 8 ядер)

# numactl для NUMA:
numactl --cpunodebind=0 --membind=0 ./myprogram  # NUMA node 0
```

### 6.3 Scheduler Domains

Linux строит иерархию «scheduler domains» — уровней балансировки:

```
Уровень 0: SMT (Hyper-Threading) — 2 логических CPU на одном физическом
Уровень 1: MC (Multi-Core) — ядра внутри одного процессора
Уровень 2: DIE (NUMA node) — NUMA-узел
Уровень 3: NUMA — между NUMA-узлами
```

Балансировка сначала пытается «переселить» задачу на ближайший уровень (SMT), затем выше.

---

## 7. Планировщик в Linux: диагностика

### 7.1 procfs и sysfs

```bash
# Политика планировщика процесса:
chrt -p 1234
# pid 1234's current scheduling policy: SCHED_OTHER
# pid 1234's current scheduling priority: 0

# Статистика планировщика:
cat /proc/schedstat
# version 15
# timestamp 1234567890
# cpu0 0 0 0 0 0 0 56789 12345 100  ← [run, wait, nr_switches...]

# CFS tuning:
cat /proc/sys/kernel/sched_latency_ns
# 6000000 (6мс)
cat /proc/sys/kernel/sched_min_granularity_ns
# 750000 (0.75мс)
cat /proc/sys/kernel/sched_wakeup_granularity_ns
# 1000000 (1мс)
```

### 7.2 perf sched

```bash
# Запись событий планировщика:
perf sched record -a sleep 10   # записать 10 секунд

# Анализ задержек:
perf sched latency
# -------------------------------------------------
#  Task                  |   Runtime ms  | Switches |
# -------------------------------------------------
#  firefox               |  1234.56 ms   | 5678     |
#  (noise):              |    12.34 ms   |  345     |

# Тепловая карта scheduling:
perf sched timehist

# Поиск runqueue latency:
perf sched script | awk '/sched:sched_stat_wait/ {print $5}' | sort -n | tail
```

### 7.3 stress-ng для тестирования

```bash
# Нагрузить планировщик:
stress-ng --cpu 8 --io 4 --vm 2 --vm-bytes 256M --timeout 60s

# Измерить scheduler latency:
stress-ng --cpu 4 --metrics --perf --timeout 10s 2>&1 | grep sched
```

---

## 8. Windows Scheduler

Для сравнения — кратко о Windows:

**Priority Classes:**
- IDLE (4), BELOW_NORMAL (6), NORMAL (8), ABOVE_NORMAL (10), HIGH (13), REALTIME (24)

**Priority Boost:**
- Windows повышает приоритет потоков в форгрунд-окне (+2)
- После IO completion (+2)
- После долгого ожидания (anti-starvation aging)

**DFSS (Dispatcher Fair Share Scheduling):**
Начиная с Vista — аналог CFS, распределяет CPU по процессам «честно».

---

## Заключение

Планировщик — это сердце операционной системы. Его задача — справедливо и эффективно распределить ограниченный ресурс CPU между конкурирующими задачами.

Ключевые выводы:

1. **CFS** в Linux — элегантное решение через virtual runtime + red-black tree. Не нужны фиксированные кванты — fairness обеспечивается математически.

2. **RT Scheduling** (SCHED_FIFO, SCHED_RR, SCHED_DEADLINE) — для задач с жёсткими временными требованиями. Используйте с осторожностью.

3. **Context switch** стоит 1-5 мкс, в основном из-за TLB flush. PCID снижает эту стоимость.

4. **Load balancing** через work stealing автоматически распределяет нагрузку, но NUMA-aware аффинити может дать лучшие результаты для конкретных задач.

5. **Диагностика:** `perf sched`, `chrt`, `/proc/schedstat` помогают понять поведение планировщика.

---

## Литература и источники

1. Love, R. (2010). *Linux Kernel Development* (3rd ed.). Addison-Wesley. — Глава 4: Process Scheduling.

2. Con Kolivas. (2004). *Staircase Scheduler* (предшественник CFS, исторический контекст). — https://lwn.net/Articles/90050/

3. Molnar, I. (2007). *Modular Scheduler Core and Completely Fair Scheduler*. — https://lwn.net/Articles/230501/

4. Wikipedia. *Completely Fair Scheduler*. — https://en.wikipedia.org/wiki/Completely_Fair_Scheduler

5. Wikipedia. *Scheduling (computing)*. — https://en.wikipedia.org/wiki/Scheduling_(computing)

6. Linux Kernel Documentation. *CFS Scheduler*. — https://www.kernel.org/doc/html/latest/scheduler/sched-design-CFS.html

7. Linux Kernel Documentation. *Real-Time Scheduler*. — https://www.kernel.org/doc/html/latest/scheduler/sched-rt-group.html

8. Aas, J. (2005). *Understanding the Linux 2.6.8.1 CPU Scheduler*. — https://joshaas.net/linux/linux_cpu_scheduler.pdf

9. Perf Wiki. *Tutorial: perf sched*. — https://perf.wiki.kernel.org/index.php/Tutorial#Scheduler_statistics

10. Silberschatz, A., Galvin, P. B., & Gagne, G. (2018). *Operating System Concepts* (10th ed.). Wiley. — Глава 5: CPU Scheduling.
