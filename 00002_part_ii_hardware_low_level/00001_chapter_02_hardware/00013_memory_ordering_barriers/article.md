# Memory Ordering и барьеры памяти

## Введение

Одна из самых неинтуитивных вещей в многопоточном программировании — то, что код выполняется не в том порядке, в котором вы его написали. И это не ошибка — это намеренное поведение как компилятора, так и процессора, оптимизирующих производительность. Проблема возникает только при многопоточности: то, что неощутимо в однопоточном коде, превращается в редкие, нерепродуцируемые ошибки в параллельных программах.

Рассмотрим классический пример:

```c
// Поток 0:         Поток 1:
data = 42;         while (!ready) {}
ready = 1;         use(data);
```

Кажется очевидным: поток 1 дождётся флага `ready`, а к тому моменту `data` уже будет установлен. Но это неверно на большинстве архитектур: компилятор может переставить `data` и `ready`, процессор может выполнить их не по порядку, и поток 1 увидит `ready=1`, но прочитает мусор вместо 42.

Memory ordering (упорядочение памяти) — это правила, определяющие, в каком порядке операции чтения и записи, выполненные одним потоком, становятся видимыми другим потокам. Барьеры памяти (memory barriers, fences) — инструкции, принудительно устанавливающие такой порядок.

---

## 1. Источники переупорядочивания

### 1.1 Переупорядочивание компилятором

Компилятор агрессивно оптимизирует код, переставляя инструкции, если это не нарушает зависимости **в рамках одного потока**. Он ничего не знает о других потоках, если вы явно не укажете.

```c
// Исходный код:
int data = 42;
int ready = 1;

// GCC -O2 может сгенерировать в любом порядке:
// либо: store(data=42), store(ready=1)
// либо: store(ready=1), store(data=42)  ← допустимо для однопоточного кода!
```

Компилятор видит два независимых присваивания (нет data dependency между ними) и вправе переставить их для лучшего использования регистров или кеш-строк.

**Запрет переупорядочивания компилятором:**

```c
// C++: volatile (частичный запрет — только для данной переменной)
volatile int ready = 0;

// C++11/C11: atomic (правильный способ)
#include <stdatomic.h>
_Atomic int ready = 0;

// GCC: compiler barrier (не CPU barrier!)
asm volatile ("" ::: "memory");
// Говорит компилятору: считай, что память изменилась — не переставляй

// C++: std::atomic_signal_fence
#include <atomic>
std::atomic_signal_fence(std::memory_order_seq_cst);
```

### 1.2 Переупорядочивание процессором

Современные процессоры используют несколько техник, которые меняют видимый порядок операций:

**Store Buffer (Буфер записи):** Записи не идут немедленно в кеш — они буферизируются. Это скрывает задержку кеш-промахов. Пока запись в буфере, другие ядра её не видят.

**Load Buffer:** CPU может «опережающе» загружать данные. Если загрузка выполнена спекулятивно — её результат используется до того, как соответствующая запись «пришла».

**Write Combining:** несколько записей в смежные адреса объединяются и записываются вместе.

**Out-of-Order Execution:** как описано в главе о конвейерах, инструкции выполняются не по порядку программы. Хотя COMMIT происходит in-order, промежуточные состояния видны другим ядрам.

### 1.3 Классификация переупорядочиваний

| Тип | Описание | Опасность |
|-----|----------|-----------|
| StoreStore | Запись A переставлена после записи B | Другой поток видит B до A |
| LoadLoad | Загрузка A переставлена после загрузки B | Устаревшее значение B |
| LoadStore | Загрузка после записи | Запись видна до чтения из старого значения |
| StoreLoad | Запись до загрузки | Наиболее частое и опасное |

---

## 2. Memory Models архитектур

Разные архитектуры имеют разные «модели памяти» — обязательства о том, какие переупорядочивания возможны.

### 2.1 x86: Total Store Order (TSO)

x86 — самая строгая архитектура из массовых. Использует «Total Store Order»:

**Разрешено:**
- Store → Load переупорядочивание (core может загрузить старое значение, если запись ещё в store buffer)

**Запрещено:**
- LoadLoad (загрузки не переставляются)
- StoreStore (записи не переставляются)
- LoadStore (загрузка не переставляется после записи)

```
x86 TSO гарантирует:
  - Записи от одного ядра видны всем в том же порядке
  - Загрузки видны всем в том же порядке
  - НО: загрузка может обогнать запись (StoreLoad hazard)
```

Практически: большинство «разумного» кода работает правильно на x86 без явных барьеров, потому что только StoreLoad разрешён, и он возникает в специфических ситуациях (Dekker's algorithm, например).

### 2.2 ARM: Weak Ordering

ARM (AArch64) — «слабая» модель памяти. Разрешены все четыре типа переупорядочивания, кроме явно упорядоченных операций:

- Нет гарантий порядка загрузок и записей между потоками
- Данные в кеше одного ядра не видны другому без явной синхронизации
- Значительно более агрессивная оптимизация

Это позволяет ARM достичь лучшей производительности и эффективности (особенно важно для мобильных устройств), но требует более тщательного использования барьеров.

### 2.3 Сравнение архитектур

| Архитектура | StoreStore | LoadLoad | LoadStore | StoreLoad | Модель |
|-------------|-----------|---------|----------|----------|--------|
| x86/x86-64 | Нет | Нет | Нет | **Да** | TSO |
| ARMv7/AArch64 | **Да** | **Да** | **Да** | **Да** | Weak |
| RISC-V (WMO) | **Да** | **Да** | **Да** | **Да** | Weak |
| RISC-V (TSO) | Нет | Нет | Нет | **Да** | TSO |
| IBM POWER | **Да** | **Да** | **Да** | **Да** | Weak |
| SPARC TSO | Нет | Нет | Нет | **Да** | TSO |

---

## 3. Барьеры памяти

### 3.1 Аппаратные барьеры

**x86:**

```asm
mfence    ; memory fence: все загрузки и записи до fence завершены перед
          ; любой загрузкой/записью после fence
lfence    ; load fence: все загрузки до завершены
sfence    ; store fence: все записи до завершены (для NT stores)
lock xchg ; или любая lock-инструкция — неявный mfence
```

`lock xchg` (используется в атомарных операциях) автоматически служит memory fence на x86, поэтому `std::atomic` операции часто не требуют отдельного mfence.

**ARM:**

```asm
dmb ish   ; data memory barrier: inner shareable domain
          ; все загрузки и записи завершены для всех ядер
dsb ish   ; data synchronization barrier: строже dmb
isb       ; instruction synchronization barrier: сброс конвейера

; Варианты:
dmb ishld  ; только загрузки (load-load, store-load ordering)
dmb ishst  ; только записи (store-store, load-store ordering)
```

**RISC-V:**

```asm
fence rw,rw   ; полный барьер: все R/W до перед всеми R/W после
fence r,r     ; только загрузки
fence w,w     ; только записи
fence.i       ; instruction fence (синхронизация кеша инструкций)
```

### 3.2 Барьеры в Linux kernel

```c
// include/asm/barrier.h (x86):

#define mb()   asm volatile("mfence":::"memory")
#define rmb()  asm volatile("lfence":::"memory")
#define wmb()  asm volatile("sfence":::"memory")

// На x86 smp_rmb() и smp_wmb() — просто compiler barriers (нет CPU fence):
#define smp_rmb() asm volatile("" ::: "memory")
#define smp_wmb() asm volatile("" ::: "memory")
// Потому что на TSO они не нужны!

// На ARM (include/asm-arm/barrier.h):
#define mb()  dsb(sy)
#define rmb() dsb(ld)
#define wmb() dsb(st)
#define smp_mb()  dmb(ish)
#define smp_rmb() dmb(ishld)
#define smp_wmb() dmb(ishst)
```

Ключевой принцип Linux: барьеры `smp_*` — только для синхронизации между процессорами. Барьеры `mb/rmb/wmb` — для взаимодействия с устройствами (MMIO, DMA).

---

## 4. C++ Memory Model (C++11)

### 4.1 Шесть порядков

C++11 формализовал модель памяти через `std::memory_order`:

```cpp
#include <atomic>

std::atomic<int> x;

// Порядки (от слабейшего к строжайшему):
x.load(std::memory_order_relaxed);   // нет гарантий порядка
x.load(std::memory_order_consume);   // data-dependency ordering (устарел в C++17)
x.load(std::memory_order_acquire);   // acquire fence
x.store(42, std::memory_order_release); // release fence
x.fetch_add(1, std::memory_order_acq_rel); // и acquire, и release
x.load(std::memory_order_seq_cst);   // последовательная согласованность (дефолт)
```

### 4.2 Relaxed Ordering

```cpp
// memory_order_relaxed: атомарность, но без гарантий порядка
// Подходит для счётчиков, где порядок неважен:

std::atomic<int> counter{0};

void increment() {
    counter.fetch_add(1, std::memory_order_relaxed);
    // Гарантия: инкремент атомарен (не потеряем ни одного +1)
    // Нет гарантии: порядок относительно других операций с памятью
}

// Хорошо для:
// - Счётчики статистики (hits, misses, events)
// - Flags без зависимостей данных
```

### 4.3 Acquire-Release Семантика

Наиболее важный паттерн — producer/consumer с acquire/release:

```cpp
std::atomic<bool> ready{false};
int data = 0;

// Producer:
void produce() {
    data = 42;                                    // (1)
    ready.store(true, std::memory_order_release); // (2) release
    // release: все записи ДО (1) видны потребителю после acquire
}

// Consumer:
void consume() {
    while (!ready.load(std::memory_order_acquire)) {} // (3) acquire
    // acquire: все записи producer до release видны нам
    assert(data == 42);  // (4) — гарантированно корректно!
}
```

Гарантия: если consumer видит `ready=true` (acquire), то все записи producer ДО `store(release)` видны consumer после `load(acquire)`.

Визуально:
```
Thread 0 (Producer):          Thread 1 (Consumer):
  data = 42           ─────────────────────────────┐
  ready.store(        release                        │ (synchronized-with)
    true,             barrier    ────────────────────│
    release)                                         │
                                while (!ready.load(  │
                                  acquire)) {}    acquire
                                // data видно = 42  ←┘
```

Acquire-release создаёт отношение «synchronizes-with», которое гарантирует «happens-before» для операций с данными.

### 4.4 Sequential Consistency (seq_cst)

Самый строгий и самый простой режим — все операции seq_cst видны всем потокам в одном общем порядке:

```cpp
std::atomic<int> x{0}, y{0};
std::atomic<int> r1{0}, r2{0};

// Поток 0:    Поток 1:
x.store(1);  y.store(1);
r1 = y.load(); r2 = x.load();

// С seq_cst: невозможна ситуация r1==0 && r2==0
// (хотя бы одна из записей x=1, y=1 видна)

// С relaxed: r1==0 && r2==0 возможно (переупорядочивание разрешено)
```

Цена seq_cst на x86: компилируется в `lock xchg` или `mfence` для stores — немного медленнее acquire/release, но обычно приемлемо.

Цена seq_cst на ARM: намного дороже! `stlr` + `ldar` vs `str` + `ldr`.

### 4.5 Happens-Before

Формальная основа C++ memory model — отношение **happens-before (HB)**:

- Если A и B в одном потоке и A до B в программном порядке → A HB B
- Если A `release`-хранит атомик, и B `acquire`-загружает то же значение → A synchronizes-with B → A HB B
- HB транзитивно: если A HB B и B HB C → A HB C

Если A HB B, то все эффекты A (записи в память) видны в B.

Если для двух операций нет HB в ни одну сторону → data race (если хотя бы одна — запись).

---

## 5. Java Memory Model (JMM)

### 5.1 Volatile в Java

В Java `volatile` даёт более сильные гарантии, чем `volatile` в C:

```java
class Example {
    volatile boolean ready = false;
    int data = 0;
    
    // Thread A:
    void produce() {
        data = 42;     // (1) — обычная запись
        ready = true;  // (2) — volatile запись (release)
    }
    
    // Thread B:
    void consume() {
        while (!ready) {}  // (3) — volatile чтение (acquire)
        System.out.println(data);  // (4) — гарантированно 42!
    }
}
```

Java volatile = C++ atomic acquire/release.

Важно: в Java до JSR-133 (Java 5, 2004) `volatile` имел слабую семантику. Это стало источником многих багов в коде с double-checked locking:

```java
// Сломанный Double-Checked Locking до Java 5:
class Singleton {
    private static Singleton instance;
    
    public static Singleton getInstance() {
        if (instance == null) {           // (1) — check без синхронизации
            synchronized (Singleton.class) {
                if (instance == null) {
                    instance = new Singleton();  // (2) — может быть видно частично!
                }
            }
        }
        return instance;
    }
}
// Проблема: (2) публикует ссылку на объект до завершения конструктора

// Исправление: volatile instance:
private static volatile Singleton instance;
```

### 5.2 synchronized и happens-before в Java

```java
// Java: монитор (synchronized) создаёт happens-before:
synchronized void write() {
    data = 42;    // видно после разблокировки монитора
}

synchronized void read() {
    // Захват того же монитора happens-after освобождения
    assert data == 42;  // гарантировано, если read вызван после write
}
```

JMM правила happens-before:
- Начало `synchronized` блока HB всем внутри
- Конец `synchronized` HB следующему захвату того же монитора
- Запись `volatile` HB чтению того же `volatile`
- `Thread.start()` HB любой операции в запущенном потоке
- Любая операция HB `Thread.join()` присоединённого потока

---

## 6. Практические примеры багов

### 6.1 Spinlock без барьеров

```c
// Неверно: спинлок без барьеров (может работать на x86, но не на ARM):
int lock = 0;

void bad_lock() {
    while (__sync_lock_test_and_set(&lock, 1)) {}
    // Нет acquire barrier! Данные под защитой могут быть прочитаны
    // до захвата блокировки.
}

void bad_unlock() {
    lock = 0;  // Нет release barrier! Данные под защитой могут быть
               // записаны после освобождения блокировки.
}

// Правильно: C11 атомики:
_Atomic int lock = 0;

void correct_lock() {
    int expected = 0;
    while (!atomic_compare_exchange_weak_explicit(
        &lock, &expected, 1,
        memory_order_acquire,   // acquire при успехе
        memory_order_relaxed    // relaxed при неудаче (retry)
    )) {
        expected = 0;
    }
}

void correct_unlock() {
    atomic_store_explicit(&lock, 0, memory_order_release);
}
```

### 6.2 Peterson's Algorithm (Academic example)

```c
// Алгоритм Петерсона для 2 потоков — требует StoreLoad barrier!
volatile int flag[2] = {0, 0};
volatile int turn = 0;

void enter_critical(int id) {
    int other = 1 - id;
    flag[id] = 1;         // (1) Объявляем намерение войти
    turn = other;         // (2) Уступаем другому
    
    // На x86: может быть переупорядочено как (2),(1) — нарушение!
    // НУЖЕН барьер между (1) и (3):
    __sync_synchronize();
    
    while (flag[other] && turn == other) {} // (3) Ждём
}

void exit_critical(int id) {
    flag[id] = 0;
}
```

Без барьера на ARM оба потока могут одновременно войти в критическую секцию! На x86 StoreLoad переупорядочивание тоже нарушает алгоритм (записи flag[id] и turn переставляются относительно загрузки flag[other]).

### 6.3 Publish/Subscribe паттерн

```cpp
// Паттерн: один поток создаёт объект, другие читают
struct Config {
    int workers;
    size_t buffer_size;
    bool debug_mode;
};

std::atomic<Config*> g_config{nullptr};

// Writer (initialization):
void init_config() {
    Config *cfg = new Config{4, 1024*1024, false};
    // КРИТИЧНО: store с release — гарантирует, что объект полностью
    // инициализирован перед тем как другие увидят указатель:
    g_config.store(cfg, std::memory_order_release);
}

// Readers:
void use_config() {
    Config *cfg;
    do {
        cfg = g_config.load(std::memory_order_acquire);
    } while (cfg == nullptr);
    
    // После acquire: гарантированно видим полностью инициализированный Config
    std::cout << cfg->workers;
}
```

### 6.4 Seqlock (Sequence Lock)

Seqlock — паттерн для high-read, low-write данных (например, системное время):

```c
struct Seqlock {
    unsigned seq;   // нечётное во время записи, чётное при устоявшемся
    // данные...
    int data;
};

void seqlock_write(struct Seqlock *sl, int new_data) {
    sl->seq++;                  // нечётное — сигнал что идёт запись
    smp_wmb();                  // store barrier
    sl->data = new_data;
    smp_wmb();                  // store barrier
    sl->seq++;                  // чётное снова
}

int seqlock_read(struct Seqlock *sl) {
    unsigned seq;
    int result;
    do {
        seq = sl->seq;
        smp_rmb();              // load barrier
        if (seq & 1) continue;  // нечётное — идёт запись, ждём
        result = sl->data;
        smp_rmb();              // load barrier
    } while (sl->seq != seq);  // если изменился — retry
    return result;
}
```

Linux kernel использует seqlock для `jiffies`, системного времени и других часто читаемых, редко изменяемых данных.

---

## 7. Volatile в C/C++ — распространённые заблуждения

### 7.1 Что volatile делает и не делает

```c
volatile int x = 0;

// Что гарантирует volatile в C/C++:
// 1. Каждый доступ к x — реальное обращение к памяти (нет кеширования в регистрах)
// 2. Порядок доступов к volatile переменным не переставляется компилятором
//    ОТНОСИТЕЛЬНО ДРУГИХ VOLATILE переменных

// Что НЕ гарантирует volatile в C/C++:
// 1. Атомарность (read-modify-write не атомарен!)
// 2. Видимость другим потокам (нет CPU-уровня барьеров)
// 3. Порядок относительно обычных (non-volatile) переменных

// Классический баг:
volatile int ready = 0;
int data = 0;  // НЕ volatile

void thread_0() {
    data = 42;    // обычная запись — компилятор/CPU могут переставить!
    ready = 1;    // volatile запись
}

// На ARM data=42 может быть виден ПОСЛЕ ready=1 — нет CPU barrier!
```

В C++ `volatile` предназначен для:
- Работы с MMIO (memory-mapped I/O)
- Общения с обработчиками сигналов
- Предотвращения оптимизации компилятором (например, в `sleep` loops)

Для многопоточности используйте `std::atomic`, а не `volatile`.

### 7.2 Java volatile vs C++ volatile

| Свойство | Java volatile | C/C++ volatile |
|----------|--------------|----------------|
| Атомарность (long/double) | Да | Нет |
| Видимость между потоками | Да (HB) | Нет (нет CPU barriers) |
| Запрет compiler reordering | Да | Частично |
| Запрет CPU reordering | Да (через barriers) | Нет |
| Применение | Межпоточная коммуникация | MMIO, сигналы |

---

## 8. Практика: анализ гонок

### 8.1 ThreadSanitizer

```bash
# Clang/GCC: компиляция с TSan
clang -fsanitize=thread -fPIE -g -O1 -o program program.c
./program

# Пример вывода при data race:
# WARNING: ThreadSanitizer: data race (pid=1234)
#   Write of size 4 at 0x... by thread T1:
#     #0 increment /path/to/program.c:15
#   Previous read of size 4 at 0x... by thread T2:
#     #0 read_value /path/to/program.c:25
```

### 8.2 Helgrind (Valgrind)

```bash
valgrind --tool=helgrind --history-level=full ./program
# Обнаруживает нарушения порядка lock/unlock,
# использование одних локов для разных данных,
# data races
```

### 8.3 Статический анализ

```bash
# Clang Static Analyzer не специализируется на races,
# но ThreadSafetyAnalysis аннотации помогают:

#include <thread>

class __attribute__((lockable)) Mutex;
class __attribute__((scoped_lockable)) MutexLock;

class Counter {
    mutable Mutex mu;
    int value __attribute__((guarded_by(mu))) = 0;
public:
    void increment() __attribute__((exclusive_locks_required(mu)));
};
```

---

## 9. Практические рекомендации

### 9.1 Правила

1. **Используйте `std::atomic`** для всех переменных, разделяемых между потоками. Это правильно и портируемо.

2. **Предпочитайте `seq_cst`** (умолчание для `std::atomic`), если не знаете точно что нужно. Да, немного медленнее, но правильно.

3. **Acquire/Release** для producer/consumer паттернов — после освоения seq_cst.

4. **Relaxed** только для независимых счётчиков/флагов без зависимостей данных.

5. **Никогда не используйте `volatile`** для межпоточной коммуникации в C++.

6. **Тестируйте с ThreadSanitizer** — это бесплатный инструмент, который ловит 95%+ гонок.

### 9.2 Типичные паттерны

```cpp
// Паттерн 1: Флаг завершения потока
std::atomic<bool> stop{false};
void worker() {
    while (!stop.load(std::memory_order_relaxed)) {
        // работа
    }
}
void main_thread() {
    stop.store(true, std::memory_order_relaxed);
}

// Паттерн 2: Передача данных между потоками (acquire/release)
std::atomic<Data*> shared_data{nullptr};
void producer() {
    Data *d = new Data(compute_something());
    shared_data.store(d, std::memory_order_release);
}
void consumer() {
    Data *d;
    while (!(d = shared_data.load(std::memory_order_acquire))) {}
    use(*d);
}

// Паттерн 3: Счётчик событий (relaxed — нет зависимости данных)
std::atomic<uint64_t> event_count{0};
void on_event() {
    event_count.fetch_add(1, std::memory_order_relaxed);
}
```

---

## Заключение

Memory ordering — один из самых трудных аспектов многопоточного программирования, потому что ошибки редко воспроизводимы, зависят от архитектуры и компилятора, и могут годами оставаться незамеченными. Ключевые выводы:

1. **Компилятор и CPU переставляют операции** — это нормально для однопоточного кода, но опасно при межпоточном взаимодействии.

2. **x86 строже ARM** — код, «случайно» работающий на x86, сломается на ARM/POWER при портировании.

3. **`std::atomic` с правильным `memory_order`** — правильный инструмент в C++. Не `volatile`, не голые глобальные переменные.

4. **Acquire/Release достаточно** для большинства producer/consumer паттернов — дешевле `seq_cst` на слабых архитектурах.

5. **ThreadSanitizer** — обязательный инструмент в арсенале разработчика.

---

## Литература и источники

1. Boehm, H.-J., & Adve, S. V. (2008). *Foundations of the C++ Concurrency Memory Model*. PLDI 2008. — https://dl.acm.org/doi/10.1145/1375581.1375591

2. McKenney, P. E. (2017). *Is Parallel Programming Hard, And If So, What Can You Do About It?* — https://mirrors.edge.kernel.org/pub/linux/kernel/people/paulmck/perfbook/perfbook.html

3. Preshing, J. *Memory Ordering at Compile Time*. — https://preshing.com/20120625/memory-ordering-at-compile-time/

4. Preshing, J. *Acquire and Release Semantics*. — https://preshing.com/20120913/acquire-and-release-semantics/

5. Wikipedia. *Memory ordering*. — https://en.wikipedia.org/wiki/Memory_ordering

6. Wikipedia. *Memory barrier*. — https://en.wikipedia.org/wiki/Memory_barrier

7. cppreference.com. *std::memory_order*. — https://en.cppreference.com/w/cpp/atomic/memory_order

8. ARM Architecture Reference Manual (ARMv8). *Memory model*. — https://developer.arm.com/documentation/ddi0487/latest

9. Intel® 64 and IA-32 Architectures Software Developer's Manual. *Chapter 8: Multiple-Processor Management*. — https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html

10. Linux Kernel Documentation. *Memory Barriers*. — https://www.kernel.org/doc/html/latest/core-api/wrappers/memory-barriers.html
