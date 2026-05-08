# Monotonic clock vs Wall clock: для измерения интервалов нужен первый

Представьте, что вы измеряете, сколько времени занимает запрос к базе данных. Вы записываете начальное время, выполняете запрос, записываете конечное время и вычитаете. Звучит просто. Но что если в момент выполнения запроса NTP-демон скорректировал системные часы на 100 миллисекунд назад? Ваш "таймаут" вдруг станет отрицательным. Или что если перевод на летнее время убрал час прямо в середине вашего измерения?

Это не теоретические сценарии — именно из-за подобных проблем упал Cloudflare в 2017 году. Понимание разницы между двумя видами часов — фундаментальный навык разработчика.

## Что такое Wall Clock (время на стене)

Wall clock (системное время, реальное время) — это то, что вы видите, когда смотрите на часы. В Unix это реализовано через `CLOCK_REALTIME`. Это время:

- Показывает текущую дату и время ("стенное время")
- Соответствует UTC (с учётом часового пояса для отображения)
- **Может идти назад** при NTP-коррекции
- **Может прыгать вперёд или назад** при ручном исправлении
- **Скачет при переводе часов** DST (для местного отображения)
- **Застывает на секунду** при добавлении высокосной секунды

```c
// POSIX C: wall clock
#include <time.h>

struct timespec ts;
clock_gettime(CLOCK_REALTIME, &ts);
// ts.tv_sec  — секунды с Unix epoch (может прыгать!)
// ts.tv_nsec — наносекунды (0–999999999)
```

```python
import time

# Python: wall clock
wall_time = time.time()          # float, секунды с epoch
wall_time2 = time.time_ns()      # int, наносекунды с epoch (Python 3.7+)
```

Wall clock идеален для:
- Отображения текущего времени пользователю
- Временны́х меток событий в логах
- Сравнения с абсолютными дедлайнами ("встреча в 15:00")
- Сериализации времени в базу данных

## Что такое Monotonic Clock (монотонные часы)

Monotonic clock (монотонное время) — это счётчик, который **всегда возрастает**. Он не знает, который сейчас час, не привязан к UTC, не коррелирует с календарём. Единственное его свойство — каждый следующий вызов вернёт значение не меньше предыдущего.

```c
// POSIX C: monotonic clock
#include <time.h>

struct timespec start, end;
clock_gettime(CLOCK_MONOTONIC, &start);
// ... выполняем операцию ...
clock_gettime(CLOCK_MONOTONIC, &end);

long elapsed_ns = (end.tv_sec - start.tv_sec) * 1000000000L 
                + (end.tv_nsec - start.tv_nsec);
// elapsed_ns ВСЕГДА >= 0!
```

Монотонные часы идеальны для:
- Измерения интервалов времени (profiling, таймауты)
- Реализации тайм-аутов в сетевом коде
- Анимации (сколько миллисекунд прошло с прошлого кадра)
- Вычисления времени выполнения функций

**Монотонные часы НЕЛЬЗЯ использовать для:**
- Хранения временны́х меток (они не знают "который час")
- Сравнения времён между разными машинами (начало отсчёта у каждой машины своё)
- Восстановления после перезагрузки (счётчик сбрасывается)

## NTP-коррекция и проблема wall clock

Когда ntpd или chronyd обнаруживает, что системные часы отклонились от истинного времени, он их корректирует. Корректировка может быть:

1. **Slewing** (постепенная): часы искусственно ускоряются или замедляются (до ±500 мкс/с). Wall clock идёт чуть быстрее или медленнее нормального.

2. **Stepping** (прыжок): при большом отклонении часы резко прыгают к правильному значению. Wall clock может пойти **назад**.

Монотонные часы NTP-коррекция не затрагивает (в большинстве реализаций). CLOCK_MONOTONIC продолжает равномерно отсчитывать секунды.

```python
import time

# Демонстрация проблемы (не запускайте в продакшн!)
# Если бы мы могли управлять NTP:

start_wall = time.time()        # 1000.000
start_mono = time.monotonic()   # 12345.678

# NTP корректирует часы назад на 100мс...

end_wall = time.time()          # 999.950 (прыжок назад!)
end_mono = time.monotonic()     # 12345.728 (всегда вперёд)

elapsed_wall = end_wall - start_wall   # -0.050 (ОТРИЦАТЕЛЬНО!)
elapsed_mono = end_mono - start_mono   # +0.050 (корректно: 50мс)
```

## POSIX CLOCK_MONOTONIC: детали

В Linux `CLOCK_MONOTONIC` имеет несколько вариантов:

```c
#include <time.h>

// CLOCK_MONOTONIC — не идёт назад, приостанавливается при suspend
clock_gettime(CLOCK_MONOTONIC, &ts);

// CLOCK_MONOTONIC_RAW — не корректируется NTP (чистый HW счётчик)
clock_gettime(CLOCK_MONOTONIC_RAW, &ts);

// CLOCK_BOOTTIME — включает время засыпания (suspend)
clock_gettime(CLOCK_BOOTTIME, &ts);

// CLOCK_MONOTONIC_COARSE — быстрее, но менее точен (гранулярность ~4мс)
clock_gettime(CLOCK_MONOTONIC_COARSE, &ts);
```

Важное различие:
- `CLOCK_MONOTONIC` не увеличивается во время suspend (когда ноутбук спит)
- `CLOCK_BOOTTIME` увеличивается и во время suspend

Для большинства целей используйте `CLOCK_MONOTONIC`. Для тайм-аутов, которые должны работать даже если система засыпает (например, запись в журнале аудита) — `CLOCK_BOOTTIME`.

```c
// Пример: измерение времени выполнения функции в C
#include <time.h>
#include <stdio.h>

void measure_function() {
    struct timespec start, end;
    
    clock_gettime(CLOCK_MONOTONIC, &start);
    
    // Выполняем измеряемую операцию
    expensive_operation();
    
    clock_gettime(CLOCK_MONOTONIC, &end);
    
    long elapsed_ns = (end.tv_sec - start.tv_sec) * 1000000000L 
                    + (end.tv_nsec - start.tv_nsec);
    double elapsed_ms = elapsed_ns / 1e6;
    
    printf("Elapsed: %.3f ms\n", elapsed_ms);
}
```

## Windows: QueryPerformanceCounter

В Windows аналогом `CLOCK_MONOTONIC` является `QueryPerformanceCounter` (QPC):

```c
#include <windows.h>

LARGE_INTEGER frequency, start, end;

// Получаем частоту счётчика (раз в секунду)
QueryPerformanceFrequency(&frequency);

// Начало измерения
QueryPerformanceCounter(&start);

// Выполняем работу
DoWork();

// Конец измерения
QueryPerformanceCounter(&end);

// Вычисляем elapsed в секундах
double elapsed = (double)(end.QuadPart - start.QuadPart) 
               / frequency.QuadPart;

printf("Elapsed: %.6f seconds\n", elapsed);
```

QPC основан на HPET (High Precision Event Timer) или TSC (Time Stamp Counter). Начиная с Windows 8, QPC гарантированно монотонен и работает корректно на многоядерных системах.

Для получения реального времени в Windows используется `GetSystemTimeAsFileTime` (wall clock) или `GetSystemTimePreciseAsFileTime` (более точный wall clock).

## Java: System.nanoTime() vs System.currentTimeMillis()

В Java два метода для получения времени:

```java
// Wall clock: возвращает миллисекунды с Unix epoch
// Может идти назад!
long wallClock = System.currentTimeMillis();

// Монотонный счётчик: наносекунды, не привязан к epoch
// Никогда не идёт назад (в рамках одной JVM)
long monotonic = System.nanoTime();
```

Правила использования в Java:

```java
// НЕПРАВИЛЬНО: измерение интервала с wall clock
long start = System.currentTimeMillis();
Thread.sleep(1000);
long elapsed = System.currentTimeMillis() - start;
// elapsed может быть != 1000 из-за NTP или DST!

// ПРАВИЛЬНО: измерение интервала с monotonic
long start = System.nanoTime();
Thread.sleep(1000);
long elapsedNs = System.nanoTime() - start;
long elapsedMs = elapsedNs / 1_000_000;
// elapsedMs ≈ 1000 (с погрешностью планировщика)

// ПРАВИЛЬНО: временна́я метка для базы данных
Instant timestamp = Instant.now(); // wall clock, aware
long epochMillis = System.currentTimeMillis(); // wall clock, число
```

Java `Instant.now()` (из `java.time`) лучше `System.currentTimeMillis()` — он является "aware" объектом с явной привязкой к UTC.

Важное предупреждение: `System.nanoTime()` **нельзя** использовать для сравнения значений между разными JVM-процессами или потоками, выполняющимися на разных CPU (теоретически, хотя на практике это редкая проблема).

## Go: time.Now() содержит оба

Go принял интересное решение: `time.Now()` возвращает структуру `Time`, которая внутри содержит **и wall clock, и monotonic clock**:

```go
package main

import (
    "fmt"
    "time"
)

func main() {
    // time.Now() захватывает оба значения одновременно
    start := time.Now()
    
    // Simulating work
    time.Sleep(100 * time.Millisecond)
    
    end := time.Now()
    
    // Sub() использует monotonic clock для вычисления разницы
    elapsed := end.Sub(start)
    fmt.Println(elapsed) // ≈ 100ms, даже если wall clock прыгнул
    
    // Явный wall clock (удаляет monotonic часть)
    wallOnly := start.Round(0)
    fmt.Println(wallOnly.UnixNano()) // обычный Unix timestamp
    
    // Проверка: содержит ли Time монотонную часть
    // (выводится "m=" в String())
    fmt.Println(start)       // 2024-05-06 15:30:00.123 m=+1234.567
    fmt.Println(wallOnly)    // 2024-05-06 15:30:00.123 (без m=)
}
```

Если структуру `Time` сериализовать и десериализовать (например, через JSON или в базу данных), монотонная часть теряется — остаётся только wall clock. Это корректное поведение.

```go
// Таймаут с context (использует monotonic под капотом)
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()

select {
case result := <-doWork(ctx):
    fmt.Println("Done:", result)
case <-ctx.Done():
    fmt.Println("Timeout!")
}
```

## Python: time.monotonic() vs time.time()

```python
import time

# Wall clock: секунды с Unix epoch
wall = time.time()              # float
wall_ns = time.time_ns()        # int, наносекунды (Python 3.7+)

# Monotonic: секунды с некоторой точки, только для измерения
mono = time.monotonic()         # float
mono_ns = time.monotonic_ns()   # int, наносекунды (Python 3.7+)

# Process time: CPU-время текущего процесса (не wall time)
cpu = time.process_time()

# Пример правильного измерения
import time

def benchmark(func, *args, **kwargs):
    start = time.monotonic_ns()
    result = func(*args, **kwargs)
    end = time.monotonic_ns()
    elapsed_us = (end - start) / 1000
    print(f"Elapsed: {elapsed_us:.1f} μs")
    return result

# Правильный таймаут
import time

def wait_with_timeout(condition, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError("Condition not met within timeout")
        time.sleep(0.01)
```

## TSC: Time Stamp Counter и его проблемы

На уровне процессора для монотонного счёта используется TSC (Time Stamp Counter) — регистр, который инкрементируется на каждый такт процессора.

```c
// Чтение TSC в x86 C
#include <stdint.h>
#include <x86intrin.h>

uint64_t rdtsc() {
    return __rdtsc();
}

// Или через asm
static inline uint64_t rdtsc_asm() {
    uint32_t lo, hi;
    __asm__ volatile ("rdtsc" : "=a"(lo), "=d"(hi));
    return ((uint64_t)hi << 32) | lo;
}
```

TSC имеет ряд исторических проблем:

### Проблема 1: Frequency Scaling

В эпоху до "Constant TSC" (до ~2008) TSC увеличивался с реальной частотой процессора. При включении режима экономии энергии (CPU throttling) процессор снижал частоту, и TSC начинал "отставать". Это делало его ненадёжным для измерения реального времени.

Современные процессоры (Nehalem и новее, Intel; Barcelona и новее, AMD) поддерживают **Constant TSC** — TSC увеличивается с постоянной частотой независимо от P-state процессора.

### Проблема 2: Multi-core несогласованность

На ранних многоядерных системах TSC каждого ядра мог начинаться в разное время (при включении ядра). Операция `rdtsc` читает TSC текущего ядра, и если поток мигрировал между ядрами — значения могли быть несравнимы.

Современные процессоры поддерживают **Invariant TSC** и **Synchronized TSC** — все ядра имеют одинаковый TSC.

```bash
# Проверка поддержки TSC в Linux
grep flags /proc/cpuinfo | head -1 | tr ' ' '\n' | grep -E '^(constant_tsc|nonstop_tsc|rdtscp|tsc_reliable)'
# constant_tsc — постоянная частота
# nonstop_tsc  — не останавливается при sleep/halted
# rdtscp       — поддержка RDTSCP (читает ID ядра вместе с TSC)
```

### vDSO и быстрые системные вызовы

В Linux `clock_gettime(CLOCK_MONOTONIC)` использует vDSO (virtual Dynamic Shared Object) — маппированный из ядра код, который можно вызвать без переключения в kernel mode. Это делает его очень быстрым:

```
Обычный syscall:    ~20-50 нс
clock_gettime vDSO: ~3-10 нс
rdtsc напрямую:     ~1-3 нс
```

Для подавляющего большинства задач накладные расходы `clock_gettime` пренебрежимо малы.

## Реальный баг: таймаут на wall clock

Рассмотрим классический баг в сетевом коде:

```python
import socket
import time

def connect_with_timeout_broken(host, port, timeout=5.0):
    """НЕПРАВИЛЬНО: использует wall clock"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    deadline = time.time() + timeout  # wall clock!
    
    while time.time() < deadline:  # BAD!
        try:
            sock.connect((host, port))
            return sock
        except ConnectionRefusedError:
            time.sleep(0.1)
    
    raise TimeoutError("Connection failed")

def connect_with_timeout_correct(host, port, timeout=5.0):
    """ПРАВИЛЬНО: использует монотонный clock"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout  # монотонный!
    
    while time.monotonic() < deadline:  # GOOD!
        try:
            sock.connect((host, port))
            return sock
        except ConnectionRefusedError:
            remaining = deadline - time.monotonic()
            time.sleep(min(0.1, max(0, remaining)))
    
    raise TimeoutError("Connection failed")
```

Что происходит в "неправильной" версии, если NTP корректирует часы назад на 10 секунд в момент ожидания? `time.time()` прыгает назад, deadline становится в "будущем", и функция будет ждать дополнительные 10 секунд. При прыжке вперёд — функция немедленно завершится с ошибкой, даже если прошло мало реального времени.

## Сводная таблица

| Аспект | Wall Clock | Monotonic Clock |
|---|---|---|
| Источник | UTC + системное время | Аппаратный счётчик |
| Идёт назад? | Да (NTP, ручная коррекция) | Никогда |
| При suspend | Продолжает идти (wall) | Останавливается (MONOTONIC) / продолжает (BOOTTIME) |
| Использование | Временны́е метки, логи, БД | Измерение интервалов, таймауты |
| Начало отсчёта | 1970-01-01 00:00:00 UTC | Неопределено (boot time) |
| Сравнение между машинами | Да (одинаковый UTC) | Нет! |
| Python | `time.time()` | `time.monotonic()` |
| Java | `System.currentTimeMillis()` | `System.nanoTime()` |
| C/POSIX | `CLOCK_REALTIME` | `CLOCK_MONOTONIC` |
| Go | `time.Now()` | `time.Now()` (автоматически для Sub()) |
| Windows | `GetSystemTimeAsFileTime` | `QueryPerformanceCounter` |

## Итог

Выбор между wall clock и monotonic clock — не мелочь. Правильное правило:

- Нужно знать **который сейчас час**? → Wall clock
- Нужно знать **сколько времени прошло**? → Monotonic clock

Большинство современных языков предоставляют оба варианта. Всегда используйте монотонные часы для таймаутов, измерений производительности, анимаций и любого кода, где важна продолжительность, а не абсолютное время.

## Литература

1. The Open Group. *POSIX.1-2017: clock_gettime*. https://pubs.opengroup.org/onlinepubs/9699919799/functions/clock_getres.html

2. Intel Corporation. *Intel® 64 and IA-32 Architectures Software Developer's Manual, Vol. 3B: System Programming Guide Part 2*. Chapter 17: RDTSC instruction.

3. Microsoft Docs. *QueryPerformanceCounter function*. https://docs.microsoft.com/en-us/windows/win32/api/profileapi/nf-profileapi-queryperformancecounter

4. Pike, R. (2011). *Go's time package*. https://pkg.go.dev/time

5. Python Software Foundation. *time — Time access and conversions*. https://docs.python.org/3/library/time.html

6. Graham-Cumming, J. (2017). *How and why the leap second affected Cloudflare DNS*. Cloudflare Blog. https://blog.cloudflare.com/how-and-why-the-leap-second-affected-cloudflare-dns/

7. Corbet, J. (2013). *A new API for the vDSO*. LWN.net. https://lwn.net/Articles/548302/

8. Linux kernel documentation. *POSIX clocks & timers*. https://www.kernel.org/doc/html/latest/core-api/timekeeping.html

9. Presotto, D., Pike, R. (1988). *Multiprocessor Spreadsheets*. Bell Labs Technical Journal.

10. Lamport, L. (1978). *Time, Clocks, and the Ordering of Events in a Distributed System*. Communications of the ACM, 21(7), 558-565.
