# Cache Coherence и протокол MESI

## Введение

Представьте, что в компании есть несколько сотрудников, каждый из которых сделал себе копию важного документа. Один из них исправил ошибку в своей копии. Что происходит с копиями остальных? Они содержат старые данные. Если никто не знает об изменении — решения, принятые на основе устаревших копий, будут неверными.

Именно такая ситуация возникает в многоядерных процессорах. Каждое ядро имеет свой L1 и L2 кеш. Если два ядра читают одну и ту же ячейку памяти, каждое загружает её копию к себе. Когда одно ядро изменяет значение, кеши другого ядра содержат устаревшие данные. Без механизма синхронизации многопоточные программы будут работать непредсказуемо.

Протокол когерентности кеша (cache coherence protocol) — аппаратный механизм, который гарантирует, что все ядра «видят» согласованное состояние памяти. MESI — наиболее распространённый протокол, используемый в большинстве современных x86 процессоров. Понимание MESI необходимо для понимания производительности многопоточных программ, проблемы false sharing и корректности атомарных операций.

---

## 1. Проблема когерентности кеша

### 1.1 Пример несогласованности

```
Время 1: Ядро 0 читает x → кеш ядра 0: x=5
Время 2: Ядро 1 читает x → кеш ядра 1: x=5
Время 3: Ядро 0 пишет x=10 → кеш ядра 0: x=10, RAM: x=5 (не обновлено)
Время 4: Ядро 1 читает x  → кеш ядра 1 отдаёт: x=5 (устаревшее!)
```

Без когерентности ядро 1 не знает об изменении ядра 0. Это классическая проблема **stale read** (чтение устаревших данных).

### 1.2 Определение когерентности

Кеш-система является когерентной, если выполняются три условия:

1. **Coherence:** запись одного процессора в конечном итоге становится видимой всем остальным.
2. **Coherence order:** все записи в одну ячейку памяти видны всем процессорам в одном и том же порядке.
3. **Write propagation:** изменение, сделанное одним процессором, должно распространиться ко всем остальным (не обязательно немедленно, но до следующего чтения).

### 1.3 Инварианты Single-Writer/Multiple-Reader (SWMR)

Когерентность часто описывается через инвариант SWMR:
- В любой момент времени для каждой ячейки памяти либо одно ядро может писать (и читать), либо несколько ядер могут только читать.
- Никогда не может быть одновременно один записывающий и один читающий.

Именно этот инвариант обеспечивает MESI.

---

## 2. Протокол MESI

### 2.1 Четыре состояния

Каждая кеш-строка находится в одном из четырёх состояний (аббревиатура MESI):

| Состояние | Название | Смысл |
|-----------|----------|-------|
| **M** | Modified (Изменённое) | Строка изменена в данном кеше. Другие кеши не имеют копии. Данные в RAM устарели. |
| **E** | Exclusive (Эксклюзивное) | Только этот кеш имеет копию строки. Данные совпадают с RAM. |
| **S** | Shared (Разделённое) | Строка присутствует в нескольких кешах. Данные совпадают с RAM. |
| **I** | Invalid (Недействительное) | Строка либо отсутствует в кеше, либо была инвалидирована. |

### 2.2 Диаграмма переходов

Состояния переходят друг в друга при событиях двух типов:
- **Processor events:** инструкции чтения/записи данного ядра
- **Bus events:** сигналы от других ядер (BusRd, BusRdX, BusUpgr)

```
         Pr:Read(Hit)
           ←──────────┐
                       │
           BusRd       │
           ──────────→ │
                       │
    ┌──────────────────┤
    │       Shared (S) │◄────────── Pr:Read (Miss) → BusRd, данные от другого кеша
    └──────────────────┘
    │ BusRdX/BusUpgr    │ Pr:Write → BusUpgr (если M у другого)
    ↓ → Invalid         ↓
    │              Exclusive (E)    ← Pr:Read (Miss) → BusRd, нет других копий
    │              │  Pr:Write → M
    │              │  BusRd → S
    │              ↓
    │          Modified (M)         ← Pr:Write (в S или I) → BusRdX
    │          │  BusRd → S (flush → RAM, BusRd gets data)
    │          │  BusRdX → I (flush → RAM)
    │          ↓
    └───────► Invalid (I)
```

### 2.3 Детальные переходы

**Из состояния Invalid (I):**
- Processor Read → BusRd (запросить строку). Если другие кеши имеют M → они делают flush в RAM, переходят в S. Если E → переходят в S. Текущий кеш переходит в E (если никто не имел) или S (если были другие).
- Processor Write → BusRdX (запросить строку и инвалидировать других). Все другие кеши переходят в I. Текущий кеш переходит в M.

**Из состояния Shared (S):**
- Processor Read → Hit, остаётся S.
- Processor Write → BusUpgr (upgrade: инвалидировать других). Другие кеши S→I. Текущий S→M.
- BusRd (от другого ядра) → остаётся S.
- BusRdX (от другого ядра) → S→I.

**Из состояния Exclusive (E):**
- Processor Read → Hit, остаётся E.
- Processor Write → нет bus transaction (только этот кеш имеет копию) → E→M. Это оптимизация: избегаем шины если точно знаем, что монопольно владеем строкой.
- BusRd → E→S (другое ядро запросило чтение).
- BusRdX → E→I.

**Из состояния Modified (M):**
- Processor Read → Hit, остаётся M.
- Processor Write → Hit, остаётся M.
- BusRd → M→S, флаш данных в RAM (сначала данные в RAM, затем оба в S).
- BusRdX → M→I, флаш данных в RAM.

### 2.4 Пример работы протокола

Предположим, два ядра: Core 0 и Core 1. Начальное состояние: x=5 в RAM.

```
Шаг 1: Core 0 читает x
  Core 0: BusRd(x) → получает x=5 из RAM
  Core 0 L1: x=5, состояние E (никто другой не читал)
  Core 1 L1: — (нет строки)

Шаг 2: Core 1 читает x
  Core 1: BusRd(x)
  Core 0 замечает BusRd на шине: E → S
  Core 1 получает x=5 (от Core 0 или RAM)
  Core 0 L1: x=5, состояние S
  Core 1 L1: x=5, состояние S

Шаг 3: Core 0 пишет x=10
  Core 0: BusUpgr(x) (у нас S, надо перейти в M)
  Core 1 замечает BusUpgr на шине: S → I
  Core 0 L1: x=10, состояние M
  Core 1 L1: Invalid
  RAM: x=5 (устарело! но это нормально — M-строка в Core 0)

Шаг 4: Core 1 читает x
  Core 1: BusRd(x) — промах (I)
  Core 0 замечает BusRd: M → S, сначала пишет x=10 в RAM (flush)
  Core 1 получает x=10 из RAM (или от Core 0)
  Core 0 L1: x=10, состояние S
  Core 1 L1: x=10, состояние S
  RAM: x=10 (обновлено)
```

---

## 3. Реализации: Snooping vs Directory

### 3.1 Snooping (Прослушивание шины)

В системах с общей шиной каждый контроллер кеша «прослушивает» (snoops) все транзакции на шине и реагирует на те, которые касаются его строк.

```
Core 0 L1 ←──┐
Core 1 L1 ←──┤── Shared Bus ──── RAM
Core 2 L1 ←──┤
Core 3 L1 ←──┘
```

Плюсы: простота, низкая задержка для небольшого числа ядер.
Минусы: шина — узкое место. Bandwidth шины ограничена. Не масштабируется выше 8-16 ядер.

Используется в: Intel Sandy Bridge/Ivy Bridge (кольцевая шина к L3).

### 3.2 Directory-Based (На основе директории)

Для большого числа ядер — централизованный каталог, знающий, у кого какие строки:

```
  Core 0    Core 1    Core 2    ...    Core N
  L1 L2     L1 L2     L1 L2           L1 L2
    \          |          |    ...       /
     └─────────┴──────────┴─────────────┘
                         │
                    Directory
                  (знает, у кого какие строки)
                         │
                        RAM
```

При чтении/записи: Core обращается к Directory. Directory знает состояние строки (кто её имеет) и отправляет сообщения нужным Core.

Плюсы: масштабируется до сотен и тысяч ядер (HPC, многопроцессорные серверы).
Минусы: дополнительная задержка (2 hop вместо 1), хранилище директории.

Используется в: AMD EPYC (Infinity Fabric), Intel Xeon (Quick Path Interconnect / UPI), крупные NUMA-системы.

### 3.3 Гибридные решения

Современные многоядерные чипы используют гибриды: snooping внутри одного NUMA-узла (tile), directory между узлами.

Intel Core i9 (20+ ядер): кольцо (ring bus) с snoop-фильтром в L3. L3 выступает как централизованный фильтр: знает, у каких ядер какие строки, предотвращая лишние широковещательные запросы.

---

## 4. False Sharing (Ложное разделение)

### 4.1 Проблема

False sharing — одна из наиболее коварных проблем производительности в многопоточном коде. Она возникает, когда два потока работают с **разными переменными**, находящимися в **одной кеш-строке**.

```c
// Типичный пример: два счётчика
struct Counter {
    volatile long a;  // поток 0 инкрементирует
    volatile long b;  // поток 1 инкрементирует
};

Counter c;

void thread_0() {
    for (int i = 0; i < 1000000; i++)
        c.a++;
}

void thread_1() {
    for (int i = 0; i < 1000000; i++)
        c.b++;
}
```

`a` и `b` — разные переменные, логически независимые. Но они лежат рядом в памяти (смещения 0 и 8 в структуре) — в одной кеш-строке (64 байта).

Что происходит:
1. Поток 0 (Core 0) инкрементирует `a`. Строка в M-состоянии в кеше Core 0.
2. Поток 1 (Core 1) хочет инкрементировать `b`. BusRdX — инвалидирует строку Core 0 (M→I), получает строку.
3. Строка теперь в M у Core 1.
4. Поток 0 снова инкрементирует `a`. BusRdX — инвалидирует Core 1, получает строку обратно.
5. Повторяется миллион раз...

Хотя `a` и `b` независимы, протокол MESI не знает о логическом разделении — он работает на уровне кеш-строк. Каждый инкремент вызывает инвалидацию у другого ядра.

### 4.2 Измерение

```bash
# perf stat для измерения cache invalidations:
perf stat -e LLC-load-misses,LLC-store-misses,\
             cache-misses,cache-references ./false_sharing_prog

# Хорошая производительность: LLC-load-misses ≪ LLC-loads
# False sharing: высокое число LLC misses при нечастом обращении к данным
```

Замер производительности:

```c
#include <pthread.h>
#include <time.h>
#include <stdio.h>

// С false sharing:
struct Shared { volatile long a, b; } shared = {0, 0};
// Без false sharing:
struct Padded {
    volatile long a;
    char _pad[56];   // заполнить до 64 байт
    volatile long b;
} padded = {0, {0}, 0};
```

Типичные результаты (2 потока, 10^8 инкрементов каждый):
- С false sharing: ~2.5 секунды
- Без false sharing: ~0.25 секунды
- Замедление: 10× из-за false sharing!

### 4.3 Решения

**Padding (заполнение до размера кеш-строки):**

```c
// Способ 1: явный padding
struct Counter {
    volatile long value;
    char _padding[56];  // 8 + 56 = 64 байта = 1 кеш-строка
};

// Способ 2: alignas (C++11/C11)
struct alignas(64) Counter {
    volatile long value;
};

// Способ 3: GCC attribute
struct Counter {
    volatile long value;
} __attribute__((aligned(64)));
```

**Thread-Local Storage (TLS):**

```c
// Каждый поток имеет свою переменную:
__thread long local_counter = 0;

void thread_func(void *arg) {
    for (int i = 0; i < N; i++)
        local_counter++;
    // В конце — объединяем все локальные значения
    pthread_mutex_lock(&mutex);
    global_sum += local_counter;
    pthread_mutex_unlock(&mutex);
}
```

**Использование атомиков с правильным padding:**

```c
#include <stdatomic.h>

struct alignas(64) AlignedAtomic {
    _Atomic long value;
};

AlignedAtomic counters[NUM_THREADS];  // каждый поток — своя строка кеша
```

### 4.4 Обнаружение false sharing

```bash
# Intel VTune: профиль "Memory Access"
vtune -collect memory-access ./program
# Показывает hot spots с high "DRAM bound" и "L3 bound" метриками

# perf c2c (cache-to-cache):
perf c2c record ./program
perf c2c report
# Показывает "Contested Accesses" — строки с частыми invalidations между ядрами
```

---

## 5. MESIF, MOESI и другие расширения

### 5.1 MESIF (Intel)

Intel добавил пятое состояние **F (Forward)** в протокол, используемый в многопроцессорных системах (Intel QPI/UPI):

- **F (Forward):** вариант S, обозначающий, что данный кеш «отвечает за» ответы на запросы BusRd от других кешей. Вместо того чтобы каждый кеш в состоянии S отвечал на запрос, только один (F) отвечает — уменьшает трафик.

### 5.2 MOESI (AMD)

AMD использует протокол MOESI с пятым состоянием **O (Owned)**:

- **O (Owned):** строка изменена (как M), но разрешено её разделять с другими кешами (они получают состояние S). Данные в RAM устарели, кеш в состоянии O отвечает за предоставление актуальных данных.

Это позволяет избежать необходимости записывать данные в RAM при переходе M→S (как в MESI). Вместо этого: M→O (без записи в RAM), другие кеши S. При вытеснении O-строки — тогда пишем в RAM.

Плюс: меньше write-backs в RAM → меньше трафик.
Минус: сложность реализации.

### 5.3 Write Invalidate vs Write Update

MESI использует **write invalidate** стратегию: при записи инвалидировать все другие копии.

Альтернатива — **write update**: при записи обновить все другие копии. Звучит лучше, но на практике хуже из-за:
1. Высокий трафик: каждая запись → широковещательное обновление.
2. Waste: обновляем данные, которые больше не будут прочитаны.
3. Сложность ordering: сложнее обеспечить строгий порядок обновлений.

Исторически: некоторые процессоры 1990-х использовали write update (DEC Alpha 21264 поддерживал оба режима). Современные процессоры — только write invalidate.

---

## 6. MESI и производительность многопоточного кода

### 6.1 Ping-pong (Пинг-понг)

```c
// Классический ping-pong: два потока поочерёдно изменяют одну переменную
volatile int shared_var = 0;

void producer() {
    while (1) {
        shared_var = 1;  // M у producer
    }
}

void consumer() {
    while (1) {
        int v = shared_var;  // BusRd: M→S, строка уходит в consumer
        // ...использование v...
    }
}
```

Каждый обмен данными — смена владельца кеш-строки, минимум 2 cache miss-перехода. Это неизбежно при коммуникации между потоками, но можно минимизировать частоту.

### 6.2 Read-Mostly Data (Данные только для чтения)

Если данные часто читаются и редко изменяются, MESI работает хорошо: все кеши имеют S-копии, BusRd не вызывает инвалидации, чтение не конкурирует.

```c
// Конфигурация: часто читается, редко изменяется
// → все ядра будут иметь S-копию → быстрое чтение без синхронизации

const int config_value = 42;  // compile-time constant — идеально
// или
__attribute__((section(".rodata"))) int read_only_data = 100;
```

### 6.3 Атомарные операции и MESI

Атомарные операции (CAS, fetch-add) требуют монопольного доступа к кеш-строке:

```c
// fetch_add на x86 компилируется в:
// lock xadd [mem], reg
// LOCK-префикс: CPU получает эксклюзивный доступ к кеш-строке (M)
// Аналогично CAS: lock cmpxchg [mem], reg

atomic_fetch_add(&counter, 1);
// Протокол: BusRdX (если не M) → строка в M → инкремент → остаётся M
// Если другой поток тоже делает atomic_add → конкуренция за строку
```

Высокая конкуренция на одной атомарной переменной — производительная проблема, даже без data race. Решение: сегрегировать счётчики по потокам (padded per-thread counter, объединять в конце).

---

## 7. Практический пример: параллельная сортировка с false sharing

### 7.1 Код с проблемой

```c
#include <pthread.h>
#include <stdlib.h>

#define N 8
#define ELEMENTS_PER_THREAD 1000000

typedef struct {
    int thread_id;
    int *data;
    long sum;   // результат каждого потока
} ThreadArg;

// Все результаты в одном массиве — false sharing!
long results[N];  // 8 * 8 байт = 64 байта = ровно одна строка кеша!

void* compute_sum(void *arg) {
    ThreadArg *a = (ThreadArg*)arg;
    long s = 0;
    for (int i = 0; i < ELEMENTS_PER_THREAD; i++)
        s += a->data[i];
    results[a->thread_id] = s;  // запись в общий массив!
    return NULL;
}
```

`results[0]` и `results[7]` — в одной кеш-строке. Когда все 8 потоков одновременно пишут в `results[]` — massive false sharing.

### 7.2 Исправленный код

```c
// Вариант 1: padding каждого результата
struct alignas(64) PaddedResult {
    long value;
};
PaddedResult results[N];  // каждый результат — своя строка кеша

void* compute_sum_fixed(void *arg) {
    ThreadArg *a = (ThreadArg*)arg;
    long s = 0;
    for (int i = 0; i < ELEMENTS_PER_THREAD; i++)
        s += a->data[i];
    results[a->thread_id].value = s;  // No false sharing!
    return NULL;
}

// Вариант 2: хранить в локальной переменной, записать один раз
void* compute_sum_local(void *arg) {
    ThreadArg *a = (ThreadArg*)arg;
    long s = 0;
    for (int i = 0; i < ELEMENTS_PER_THREAD; i++)
        s += a->data[i];
    // Записываем в структуру аргумента (не в общий массив):
    a->sum = s;
    return NULL;
}
```

### 7.3 Измерение разницы на практике

```python
# Имитация в Python с многопроцессорностью (GIL не даёт показать это для threads,
# поэтому используем multiprocessing для демонстрации)
import multiprocessing
import time
import numpy as np

def sum_chunk(data_chunk, result_queue):
    s = sum(data_chunk)
    result_queue.put(s)

N = 8
data = list(range(10_000_000))
chunks = [data[i::N] for i in range(N)]

start = time.perf_counter()
with multiprocessing.Pool(N) as pool:
    results = pool.map(sum, chunks)
total = sum(results)
print(f"Parallel: {time.perf_counter()-start:.3f}s, sum={total}")
```

В реальном C/C++ коде разница между версиями с и без false sharing — 5-10× для интенсивно конкурирующих потоков.

---

## 8. Когерентность и Memory Model

### 8.1 Отличие когерентности от консистентности

Важно разделять два понятия:

**Cache Coherence** (когерентность) — гарантирует, что для **одной** ячейки памяти все ядра в конечном итоге видят одно значение.

**Memory Consistency** (согласованность памяти) — гарантирует порядок, в котором **разные** операции с **разными** ячейками видны разным ядрам.

MESI обеспечивает когерентность, но не консистентность. Например, x86 имеет «TSO» (Total Store Order) — более строгую модель, чем arm/RISC-V «weak ordering». Это тема следующей статьи.

### 8.2 Когерентность и барьеры памяти

```c
// Без барьера:
// Поток 0:             Поток 1:
data = 42;             while (!ready) {}  // spin
ready = 1;             use(data);
// Проблема: CPU может переупорядочить store(data) и store(ready)
// → поток 1 видит ready=1 но data ещё не обновлено

// С барьером:
data = 42;
__sync_synchronize();  // memory barrier (fence)
ready = 1;
// После барьера: store(data) видна раньше store(ready)
```

MESI гарантирует, что изменение распространится, но не когда и в каком порядке относительно других изменений — для этого нужны явные барьеры.

---

## 9. Диагностика и профилирование когерентности

### 9.1 perf c2c — специализированный инструмент

```bash
# perf c2c (cache-to-cache contention) — версия Linux ≥ 4.14:
perf c2c record -a -g -- ./multithreaded_program
perf c2c report --stdio

# Пример вывода:
# =================================================
# Trace Event Information
# =================================================
#           Total records  :       42350
#          Locked Access   :           0
#         Remote LLC Misses:        8512  ← inter-core cache transfers
#
# =================================================
# Hot Cachelines
# =================================================
# Cacheline    ....  RmtHitm  Local%  PID      Sym                DSO
# ----------------------------------------------------------------
# 0x7f3a40     .    5123    51.2%   1234     counter             ./a.out
#  ↑ эта строка кеша — источник проблемы
```

`RmtHitm` (Remote HIT Modified) — число случаев, когда строка была запрошена у другого ядра в M-состоянии. Высокое значение → false sharing или реальная конкуренция.

### 9.2 Intel PCM (Performance Counter Monitor)

```bash
# Intel PCM для мониторинга QPI/UPI трафика (между сокетами):
pcm-memory.x

# Показывает:
# Memory bandwidth per socket
# QPI bandwidth (трафик между процессорами)
# Высокий QPI bandwidth при низком Memory bandwidth → false sharing между сокетами
```

### 9.3 Valgrind Helgrind

Helgrind обнаруживает data races (логические ошибки), которые часто сопровождают false sharing:

```bash
valgrind --tool=helgrind ./program

# Вывод:
# ==1234== Possible data race during write of size 8 at 0x...
# ==1234==    at counter increment
# ==1234== This conflicts with a previous write of size 8
# ==1234==    in thread #2
```

---

## Заключение

MESI — аппаратный фундамент, на котором строится вся многопоточная работа. Его понимание раскрывает «физику» таких явлений:

1. **Почему атомарные операции медленнее обычных** — они требуют монопольного доступа (M-состояние), что при конкуренции вызывает bus transaction.

2. **Почему false sharing так дорог** — каждая запись одного ядра инвалидирует строку у другого, превращая O(1) операцию в серию bus transactions.

3. **Почему padding до размера кеш-строки работает** — разные переменные попадают в разные строки, и протокол MESI не мешает их независимой модификации.

4. **Почему read-heavy данные дешевле write-heavy** — в состоянии S множество кешей могут параллельно читать без синхронизации.

5. **Почему масштабирование до большого числа ядер сложно** — shared bus не масштабируется, directory-based протоколы добавляют задержку.

Практический совет: при профилировании многопоточного кода всегда проверяйте `perf c2c` на наличие `RmtHitm` — это прямой индикатор проблем с когерентностью кеша.

---

## Литература и источники

1. Sorin, D. J., Hill, M. D., & Wood, D. A. (2011). *A Primer on Memory Consistency and Cache Coherence*. Synthesis Lectures on Computer Architecture. Morgan & Claypool. — https://www.morganclaypool.com/doi/abs/10.2200/S00346ED1V01Y201104CAC016

2. Hennessy, J. L., & Patterson, D. A. (2019). *Computer Architecture: A Quantitative Approach* (6th ed.). Morgan Kaufmann. — Appendix I: Cache Coherence.

3. Wikipedia. *MESI protocol*. — https://en.wikipedia.org/wiki/MESI_protocol

4. Wikipedia. *Cache coherence*. — https://en.wikipedia.org/wiki/Cache_coherence

5. Drepper, U. (2007). *What Every Programmer Should Know About Memory*. — https://people.freebsd.org/~lstewart/articles/cpumemory.pdf — раздел о многопроцессорных системах.

6. Leis, V., et al. (2019). *False Sharing in CPU Caches*. Database Architectures. — практический анализ false sharing в СУБД.

7. Intel. *perf c2c — False sharing detection*. — https://joemario.github.io/blog/2016/09/01/c2c-blog/

8. Torvalds, L. (2006). *Re: Linux 2.6.17-rc3*, LKML — классическое письмо Торвальдса о memory ordering и cache coherence. — https://lkml.org/lkml/2006/5/3/66

9. McKenney, P. E. (2017). *Is Parallel Programming Hard, And If So, What Can You Do About It?* — https://mirrors.edge.kernel.org/pub/linux/kernel/people/paulmck/perfbook/perfbook.html

10. AMD. *AMD EPYC NUMA Architecture and Performance Optimization*. — https://developer.amd.com/resources/epyc-resources/epyc-tuning-guides/
