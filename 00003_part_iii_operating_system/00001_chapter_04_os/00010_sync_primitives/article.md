# Примитивы синхронизации: мьютекс, семафор, condvar, spinlock, RW-lock

Многопоточное программирование даёт возможность использовать несколько ядер процессора одновременно, но за это приходится платить — потоки могут обращаться к одним и тем же данным конкурентно, что порождает гонки, некорректные состояния и трудноуловимые ошибки. Примитивы синхронизации — это строительные блоки, позволяющие скоординировать потоки: защитить критические секции, сигнализировать о событиях, организовать ожидание без активного опроса. Понимание их устройства на уровне ядра и процессора необходимо для написания корректного и эффективного параллельного кода.

В этой статье мы рассмотрим фундаментальные примитивы — мьютекс, семафор, условную переменную, спинлок и RW-блокировку. Для каждого примитива разберём семантику, реализацию на уровне ОС и оборудования, типичные сценарии применения и ловушки. Примеры будут приведены на C с использованием POSIX API, а также затронем реализации в Linux и glibc.

Сквозная тема статьи — компромисс между корректностью и производительностью. Блокирующие примитивы безопасны, но дороги при высоком contention. Спинлоки быстры при коротких ожиданиях, но расточительны при длинных. Lock-free структуры масштабируются превосходно, но требуют глубокого понимания модели памяти. Грамотный выбор примитива — это инженерное решение, а не интуиция.

## 1. Атомарные операции — фундамент всего

Прежде чем говорить о высокоуровневых примитивах, необходимо понять, на чём они строятся. Все примитивы синхронизации в конечном счёте опираются на атомарные операции процессора, которые гарантируют неделимость чтения-модификации-записи.

### 1.1 CAS и TAS

Две ключевые атомарные операции:

- **Test-and-Set (TAS)**: атомарно записывает 1 в ячейку памяти и возвращает старое значение
- **Compare-and-Swap (CAS)**: атомарно сравнивает значение с ожидаемым и, если совпадает, заменяет новым

На x86 CAS реализован инструкцией `LOCK CMPXCHG`. Префикс `LOCK` блокирует шину памяти на время операции, обеспечивая видимость изменений всем ядрам.

```c
#include <stdatomic.h>
#include <stdio.h>
#include <stdbool.h>

// CAS через стандарт C11
bool cas(atomic_int *ptr, int expected, int desired) {
    return atomic_compare_exchange_strong(ptr, &expected, desired);
}

// Атомарный счётчик
atomic_int counter = 0;

void increment_safe(void) {
    int old, new;
    do {
        old = atomic_load(&counter);
        new = old + 1;
    } while (!atomic_compare_exchange_weak(&counter, &old, new));
}

// fetch_add — быстрее, когда не нужен CAS
void increment_fast(void) {
    atomic_fetch_add(&counter, 1);
}
```

В C11 и C++11 атомарные операции стандартизированы. На уровне x86 `atomic_fetch_add` транслируется в `LOCK XADD`, что дешевле цикла CAS для простого инкремента.

### 1.2 Барьеры памяти и атомарность

Атомарная операция гарантирует неделимость на уровне процессора, но не обязательно полный барьер памяти. В C11 каждая атомарная операция имеет параметр `memory_order`:

```c
// Приобретение (acquire) — все последующие операции видят записи до release
int val = atomic_load_explicit(&flag, memory_order_acquire);

// Освобождение (release) — все предыдущие записи видны после acquire
atomic_store_explicit(&flag, 1, memory_order_release);

// Relaxed — только атомарность, без гарантий порядка
atomic_fetch_add_explicit(&counter, 1, memory_order_relaxed);
```

Без барьеров компилятор и процессор могут переставлять операции. Примитивы синхронизации всегда включают нужные барьеры — именно поэтому mutex.lock() является точкой acquire, а mutex.unlock() — release.

## 2. Мьютекс (Mutex)

Мьютекс (mutual exclusion — взаимное исключение) — самый распространённый примитив. Он обеспечивает, что в любой момент времени критическую секцию выполняет не более одного потока.

### 2.1 Семантика

Мьютекс имеет два состояния: захвачен (locked) и свободен (unlocked). Поток, вызывающий `lock()` на уже захваченном мьютексе, блокируется до его освобождения. Только захвативший поток может освободить мьютекс — это отличает мьютекс от семафора.

```c
#include <pthread.h>
#include <stdio.h>

pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
int shared_counter = 0;

void *worker(void *arg) {
    for (int i = 0; i < 1000000; i++) {
        pthread_mutex_lock(&mutex);
        shared_counter++;           // критическая секция
        pthread_mutex_unlock(&mutex);
    }
    return NULL;
}

int main(void) {
    pthread_t t1, t2;
    pthread_create(&t1, NULL, worker, NULL);
    pthread_create(&t2, NULL, worker, NULL);
    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    printf("Counter: %d\n", shared_counter); // всегда 2000000
    return 0;
}
```

### 2.2 Futex — быстрый мьютекс в Linux

Наивная реализация мьютекса через системный вызов работала бы медленно: каждый lock/unlock требовал бы перехода в режим ядра. Linux решил эту проблему с помощью **futex** (Fast Userspace muTEX), введённого в ядро 2.5.7.

Ключевая идея: в отсутствие конкуренции (uncontended path) мьютекс захватывается и освобождается полностью в пространстве пользователя через CAS, без системного вызова. Только при конкуренции поток обращается к ядру для ожидания.

```c
// Упрощённая реализация мьютекса на futex
#include <linux/futex.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <stdatomic.h>

// Состояния: 0 = свободен, 1 = захвачен без ждущих, 2 = захвачен со ждущими
typedef struct {
    atomic_int state;
} my_mutex_t;

static int futex_wait(atomic_int *addr, int expected) {
    return syscall(SYS_futex, addr, FUTEX_WAIT_PRIVATE, expected, NULL, NULL, 0);
}

static int futex_wake(atomic_int *addr, int count) {
    return syscall(SYS_futex, addr, FUTEX_WAKE_PRIVATE, count, NULL, NULL, 0);
}

void my_mutex_lock(my_mutex_t *m) {
    int c = 0;
    // Быстрый путь: CAS 0 -> 1 (нет конкуренции)
    if (atomic_compare_exchange_strong(&m->state, &c, 1)) {
        return; // захватили без syscall!
    }
    // Медленный путь: есть конкуренция
    do {
        if (c == 2 || atomic_compare_exchange_strong(&m->state, &c, 2)) {
            futex_wait(&m->state, 2); // ждём в ядре
        }
        c = 0;
    } while (!atomic_compare_exchange_strong(&m->state, &c, 2));
}

void my_mutex_unlock(my_mutex_t *m) {
    if (atomic_fetch_sub(&m->state, 1) != 1) {
        // Были ждущие потоки (state было 2)
        atomic_store(&m->state, 0);
        futex_wake(&m->state, 1); // будим одного
    }
}
```

Реальная реализация `pthread_mutex_t` в glibc (NPTL — Native POSIX Thread Library) использует именно этот механизм. На незагруженном мьютексе lock/unlock занимает несколько наносекунд, что сопоставимо с атомарной операцией.

### 2.3 Типы мьютексов POSIX

| Тип | Рекурсивный | Проверка ошибок | Применение |
|-----|------------|-----------------|-----------|
| `PTHREAD_MUTEX_NORMAL` | Нет (дедлок!) | Нет | Максимальная скорость |
| `PTHREAD_MUTEX_ERRORCHECK` | Нет | Да | Отладка |
| `PTHREAD_MUTEX_RECURSIVE` | Да | Да | Рекурсивные функции |
| `PTHREAD_MUTEX_DEFAULT` | Нет | UB | POSIX-совместимость |

```c
// Создание рекурсивного мьютекса
pthread_mutex_t rmutex;
pthread_mutexattr_t attr;
pthread_mutexattr_init(&attr);
pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE);
pthread_mutex_init(&rmutex, &attr);
pthread_mutexattr_destroy(&attr);
```

### 2.4 Priority Inversion и Priority Inheritance

Классическая проблема: высокоприоритетный поток H ждёт мьютекс, захваченный низкоприоритетным потоком L. Если средний по приоритету поток M не даёт L работать — H ждёт бесконечно. Именно это привело к зависанию Mars Pathfinder в 1997 году.

Решение — **Priority Inheritance**: пока низкоприоритетный поток держит мьютекс, ему временно повышают приоритет до уровня наивысшего ждущего. В POSIX это `PTHREAD_PRIO_INHERIT`:

```c
pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT);
```

## 3. Семафор

Семафор — примитив, предложенный Эдсгером Дейкстрой в 1965 году. В отличие от мьютекса, семафор имеет счётчик и может быть освобождён другим потоком. Операции называются P (proberen — проверить, декремент) и V (verhogen — увеличить, инкремент), в POSIX — `sem_wait` и `sem_post`.

### 3.1 Бинарный и счётный семафор

**Бинарный семафор** имеет счётчик 0 или 1 и схож с мьютексом, но без семантики владения. Полезен для сигнализации между потоками.

**Счётный семафор** позволяет N потокам одновременно войти в секцию. Классический пример — пул ресурсов (соединений с БД, буферов):

```c
#include <semaphore.h>
#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

#define POOL_SIZE 3
#define WORKERS   8

sem_t pool_sem;

void *use_resource(void *arg) {
    int id = *(int*)arg;
    
    printf("Worker %d: ожидает ресурс\n", id);
    sem_wait(&pool_sem);   // P: захватить слот (блокирует если 0)
    
    printf("Worker %d: использует ресурс\n", id);
    sleep(1); // имитация работы
    
    printf("Worker %d: освобождает ресурс\n", id);
    sem_post(&pool_sem);   // V: освободить слот
    
    return NULL;
}

int main(void) {
    sem_init(&pool_sem, 0, POOL_SIZE); // инициализация счётчиком 3
    
    pthread_t threads[WORKERS];
    int ids[WORKERS];
    for (int i = 0; i < WORKERS; i++) {
        ids[i] = i;
        pthread_create(&threads[i], NULL, use_resource, &ids[i]);
    }
    for (int i = 0; i < WORKERS; i++) {
        pthread_join(threads[i], NULL);
    }
    sem_destroy(&pool_sem);
    return 0;
}
```

### 3.2 Именованные семафоры

POSIX предоставляет именованные семафоры для синхронизации между процессами:

```c
// Создание (в первом процессе)
sem_t *sem = sem_open("/my_semaphore", O_CREAT, 0644, 1);

// Использование (в любом процессе)
sem_wait(sem);
// ... критическая секция ...
sem_post(sem);

// Закрытие (в каждом процессе)
sem_close(sem);

// Удаление (один раз)
sem_unlink("/my_semaphore");
```

### 3.3 Semaphore vs Mutex

| Характеристика | Mutex | Semaphore |
|---------------|-------|-----------|
| Владение | Только захвативший может освободить | Любой поток может post |
| Счётчик | 0 или 1 | 0 до N |
| Сигнализация | Нет | Да (бинарный sem) |
| Priority Inheritance | Да (POSIX) | Нет (обычно) |
| Применение | Взаимное исключение | Контроль ресурсов, события |

Главное правило: для защиты данных используйте мьютекс, для сигнализации о событиях — семафор или условную переменную.

## 4. Условная переменная (Condition Variable)

Условная переменная решает задачу ожидания условия. Без неё поток вынужден постоянно опрашивать флаг в цикле (busy-wait), расходуя CPU. Условная переменная позволяет атомарно освободить мьютекс и заснуть до сигнала.

### 4.1 Паттерн producer-consumer

```c
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

#define QUEUE_SIZE 10

int queue[QUEUE_SIZE];
int head = 0, tail = 0, count = 0;

pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t not_full  = PTHREAD_COND_INITIALIZER;
pthread_cond_t not_empty = PTHREAD_COND_INITIALIZER;

void enqueue(int item) {
    pthread_mutex_lock(&mutex);
    while (count == QUEUE_SIZE) {
        // Атомарно: освобождаем мьютекс и спим
        pthread_cond_wait(&not_full, &mutex);
        // После пробуждения: мьютекс снова захвачен
    }
    queue[tail] = item;
    tail = (tail + 1) % QUEUE_SIZE;
    count++;
    pthread_cond_signal(&not_empty); // будим одного потребителя
    pthread_mutex_unlock(&mutex);
}

int dequeue(void) {
    pthread_mutex_lock(&mutex);
    while (count == 0) {
        pthread_cond_wait(&not_empty, &mutex);
    }
    int item = queue[head];
    head = (head + 1) % QUEUE_SIZE;
    count--;
    pthread_cond_signal(&not_full); // будим одного производителя
    pthread_mutex_unlock(&mutex);
    return item;
}

void *producer(void *arg) {
    for (int i = 0; i < 100; i++) {
        enqueue(i);
        printf("Произведено: %d\n", i);
    }
    return NULL;
}

void *consumer(void *arg) {
    for (int i = 0; i < 100; i++) {
        int item = dequeue();
        printf("Потреблено: %d\n", item);
    }
    return NULL;
}
```

### 4.2 Spurious wakeups

Условная переменная может разбудить поток без сигнала — это называется **spurious wakeup** (ложное пробуждение). POSIX допускает такое поведение. Именно поэтому ожидание всегда должно быть в цикле `while`, а не `if`:

```c
// НЕПРАВИЛЬНО — можно проспать сигнал или получить spurious wakeup
pthread_cond_wait(&cond, &mutex);
if (condition) { /* ... */ }

// ПРАВИЛЬНО — проверяем условие после каждого пробуждения
while (!condition) {
    pthread_cond_wait(&cond, &mutex);
}
```

### 4.3 Signal vs Broadcast

- `pthread_cond_signal()` — будит один ждущий поток (если несколько, выбор не определён)
- `pthread_cond_broadcast()` — будит все ждущие потоки

Используйте signal, когда любой ждущий поток может обработать событие. Используйте broadcast при изменении состояния, которое может разблокировать нескольких (например, resize буфера).

### 4.4 Ожидание с таймаутом

```c
#include <time.h>

struct timespec ts;
clock_gettime(CLOCK_REALTIME, &ts);
ts.tv_sec += 5; // ждём не более 5 секунд

pthread_mutex_lock(&mutex);
while (!condition) {
    int rc = pthread_cond_timedwait(&cond, &mutex, &ts);
    if (rc == ETIMEDOUT) {
        printf("Таймаут ожидания\n");
        break;
    }
}
pthread_mutex_unlock(&mutex);
```

## 5. Спинлок (Spinlock)

Спинлок — примитив, при котором поток не засыпает, а крутится в цикле, проверяя условие освобождения. Это активное ожидание (busy-wait).

### 5.1 Реализация

```c
#include <stdatomic.h>

typedef struct {
    atomic_flag locked;
} spinlock_t;

#define SPINLOCK_INIT { ATOMIC_FLAG_INIT }

void spin_lock(spinlock_t *lock) {
    while (atomic_flag_test_and_set_explicit(&lock->locked, memory_order_acquire)) {
        // Подсказка процессору: мы в цикле spin-wait
        // На x86 снижает энергопотребление и освобождает ресурсы для HT-потока
        __asm__ volatile("pause" ::: "memory");
    }
}

void spin_unlock(spinlock_t *lock) {
    atomic_flag_clear_explicit(&lock->locked, memory_order_release);
}
```

Инструкция `PAUSE` на x86 сигнализирует процессору, что идёт spin-wait, позволяя снизить энергопотребление и улучшить производительность Hyper-Threading (второй логический поток получает больше ресурсов).

### 5.2 Когда использовать спинлок

Спинлок оправдан только при коротком времени ожидания. Сравнение:

| Характеристика | Mutex (futex) | Spinlock |
|---------------|---------------|----------|
| Uncontended lock | ~5 нс | ~3 нс |
| Короткое ожидание (<1 мкс) | ~5-10 мкс (syscall) | ~50-200 нс |
| Длинное ожидание | Спит, не тратит CPU | Жжёт CPU впустую |
| Однопроцессорная система | Ок | Никогда! |

На однопроцессорной системе спинлок бесполезен: если поток держит блокировку, а другой крутится в спин — никто не двигается. Только вытесняющий планировщик (preemption) разрулит ситуацию, что хуже простого mutex.

В ядре Linux `spinlock_t` отключает вытеснение на SMP-системах. Это значит: внутри spin_lock нельзя засыпать, делать syscall или выполнять долгие операции. Нарушение приводит к deadlock.

### 5.3 Ticket spinlock

Простой спинлок несправедлив (unfair): один поток может захватывать блокировку снова и снова, уморив остальных голодом. Ticket spinlock обеспечивает FIFO-порядок:

```c
typedef struct {
    atomic_uint ticket;  // следующий номер (для ожидающих)
    atomic_uint serving; // обслуживаемый номер
} ticket_lock_t;

void ticket_lock(ticket_lock_t *lock) {
    unsigned my_ticket = atomic_fetch_add(&lock->ticket, 1);
    while (atomic_load_explicit(&lock->serving, memory_order_acquire) != my_ticket) {
        __asm__ volatile("pause");
    }
}

void ticket_unlock(ticket_lock_t *lock) {
    atomic_fetch_add_explicit(&lock->serving, 1, memory_order_release);
}
```

Этот механизм аналогичен очереди в банке с номерками: каждый получает свой номер и ждёт, пока его не вызовут.

## 6. RW-блокировка (Read-Write Lock)

Когда данные часто читаются, но редко пишутся, мьютекс создаёт лишнее сериализацию: множество читателей могут работать параллельно безопасно. RW-блокировка позволяет нескольким читателям одновременно, но эксклюзивно для писателя.

### 6.1 POSIX API

```c
#include <pthread.h>

pthread_rwlock_t rwlock = PTHREAD_RWLOCK_INITIALIZER;

// Читатели: могут работать параллельно
void *reader(void *arg) {
    pthread_rwlock_rdlock(&rwlock);
    // ... читаем данные ...
    printf("Читаем: %d\n", shared_data);
    pthread_rwlock_unlock(&rwlock);
    return NULL;
}

// Писатель: эксклюзивный доступ
void *writer(void *arg) {
    pthread_rwlock_wrlock(&rwlock);
    // ... изменяем данные ...
    shared_data++;
    pthread_rwlock_unlock(&rwlock);
    return NULL;
}
```

### 6.2 Проблема голодания писателей

Наивная реализация RW-блокировки страдает от голодания (writer starvation): поток читателей непрерывно захватывает блокировку, не давая писателю возможности войти. Решения:

1. **Writer preference**: новые читатели блокируются, если есть ждущий писатель
2. **Фаза чтения/записи**: блокировка переключается между фазами
3. **Ticket RW-lock**: FIFO-порядок для всех запросов

В Linux ядре используется `rwsem` (read-write semaphore) с поддержкой FIFO.

### 6.3 Когда RW-блокировка не нужна

RW-блокировки сложнее и дороже мьютекса при низком параллелизме чтения. Рекомендации:

- Если критическая секция короткая (< 1 мкс) — обычный мьютекс быстрее из-за меньших накладных расходов на захват RW-блокировки
- Если соотношение читателей к писателям < 10:1 — преимущество RW незначительно
- Если данные обновляются часто — RW-блокировка вырождается в мьютекс

```
# Пример: сравнение производительности (условные числа)
Мьютекс (uncontended):    ~5 нс
RW rdlock (uncontended):  ~8 нс
RW wrlock (uncontended): ~10 нс

При 8 читателях / 0 писателей:
  Mutex:    ~1.2 мкс на операцию (сериализованы)
  RW-lock:  ~0.15 мкс (параллельно)
```

## 7. Продвинутые паттерны

### 7.1 Seqlock (Sequential Lock)

Seqlock используется в ядре Linux для данных, читаемых часто и записываемых редко, где читатели не должны блокировать писателей (например, системное время `jiffies`).

```c
typedef struct {
    atomic_uint seq;
    // ... данные ...
    unsigned long timestamp;
} seqlock_t;

// Писатель захватывает блокировку
void write_seqlock(seqlock_t *sl) {
    atomic_fetch_add(&sl->seq, 1); // нечётное = запись
    // полный барьер
    __sync_synchronize();
}

void write_sequnlock(seqlock_t *sl) {
    __sync_synchronize();
    atomic_fetch_add(&sl->seq, 1); // чётное = не пишем
}

// Читатель: без блокировки, но перечитывает при конкуренции
unsigned long read_timestamp(seqlock_t *sl) {
    unsigned seq;
    unsigned long ts;
    do {
        seq = atomic_load(&sl->seq);
        if (seq & 1) continue; // нечётное — идёт запись
        ts = sl->timestamp;
        __sync_synchronize();
    } while (atomic_load(&sl->seq) != seq); // перечитать если изменился
    return ts;
}
```

Читатели никогда не блокируются и не препятствуют писателям. При конкуренции читатели просто перечитывают данные. Отлично работает для небольших данных (несколько слов), читаемых очень часто.

### 7.2 MCS Lock (Mellor-Crummey & Scott)

Проблема обычных спинлоков: при освобождении все ждущие потоки начинают читать одну ячейку памяти — это создаёт шторм аннуляций кэш-линий (cache coherence storm). MCS lock устраняет это: каждый поток крутится на своей локальной переменной.

```c
typedef struct mcs_node {
    struct mcs_node *next;
    atomic_int locked;
} mcs_node_t;

typedef atomic_uintptr_t mcs_lock_t;

void mcs_lock(mcs_lock_t *lock, mcs_node_t *node) {
    node->next = NULL;
    atomic_store(&node->locked, 1);
    
    mcs_node_t *prev = (mcs_node_t*)atomic_exchange(lock, (uintptr_t)node);
    if (prev != NULL) {
        prev->next = node;
        // Крутимся на СВОЕЙ переменной — нет cache storm
        while (atomic_load(&node->locked)) {
            __asm__ volatile("pause");
        }
    }
}

void mcs_unlock(mcs_lock_t *lock, mcs_node_t *node) {
    if (node->next == NULL) {
        mcs_node_t *n = node;
        if (atomic_compare_exchange_strong(lock, (uintptr_t*)&n, 0)) {
            return;
        }
        while (node->next == NULL) {} // ждём, пока следующий запишет указатель
    }
    atomic_store(&node->next->locked, 0); // будим следующего
}
```

MCS Lock масштабируется линейно с числом процессоров, тогда как наивный спинлок деградирует квадратично.

### 7.3 Lock-free vs Lock-based

Lock-free структуры не используют блокировок — прогресс гарантируется для системы в целом (хотя отдельный поток может застрять). Реализуются через CAS-циклы.

```c
// Lock-free стек на C11
typedef struct node {
    int value;
    struct node *next;
} node_t;

typedef struct {
    atomic_uintptr_t top;
} lf_stack_t;

void push(lf_stack_t *stack, node_t *node) {
    node_t *old_top;
    do {
        old_top = (node_t*)atomic_load(&stack->top);
        node->next = old_top;
    } while (!atomic_compare_exchange_weak(&stack->top,
                                           (uintptr_t*)&old_top,
                                           (uintptr_t)node));
}

node_t *pop(lf_stack_t *stack) {
    node_t *old_top;
    do {
        old_top = (node_t*)atomic_load(&stack->top);
        if (old_top == NULL) return NULL;
    } while (!atomic_compare_exchange_weak(&stack->top,
                                           (uintptr_t*)&old_top,
                                           (uintptr_t)old_top->next));
    return old_top;
}
```

**Проблема ABA**: поток читает значение A, другой меняет на B, затем обратно на A — первый поток не замечает изменения. Решение — тегирование указателей или hazard pointers.

| Свойство | Lock-free | Lock-based |
|---------|-----------|-----------|
| Прогресс при сбоях потока | Гарантирован | Нет (дедлок) |
| Накладные расходы | Низкие без конкуренции | Overhead мьютекса |
| Сложность | Высокая | Умеренная |
| Инверсия приоритетов | Невозможна | Возможна |
| Голодание | Возможно | Возможно (Fair mutex) |

## 8. Диагностика и отладка

### 8.1 Helgrind и Thread Sanitizer

**Valgrind Helgrind** обнаруживает гонки данных, нарушения порядка захвата блокировок и использование неинициализированных мьютексов:

```bash
valgrind --tool=helgrind ./my_program
```

**ThreadSanitizer (TSan)** — инструментация компилятора, обнаруживает гонки при выполнении:

```bash
gcc -fsanitize=thread -g -O1 -o my_program my_program.c -lpthread
./my_program
# При наличии гонки:
# WARNING: ThreadSanitizer: data race (pid=1234)
#   Write of size 4 at 0x... by thread T1:
#     #0 worker race.c:12 (./my_program)
```

### 8.2 Профилирование contention

`perf` позволяет измерить время, проведённое в ожидании блокировок:

```bash
# Запись событий ожидания
perf lock record ./my_program

# Анализ
perf lock report
# Name         acquired  contended  total-wait  avg-wait  max-wait
# &mutex            1000        500    5.00 ms   10.0 us  100.0 us
```

Высокое значение contended относительно acquired означает узкое место в блокировке.

### 8.3 Мониторинг через /proc

```bash
# Просмотр мьютексов процесса (Linux с MUTEX_ROBUST)
cat /proc/PID/status | grep -i thread

# Futex статистика
cat /proc/sys/kernel/perf_event_paranoid
strace -e futex ./my_program 2>&1 | grep futex
```

## 9. Практические рекомендации

### 9.1 Иерархия блокировок для предотвращения дедлока

Главное правило: все потоки должны захватывать несколько мьютексов в одном и том же порядке. Документируйте порядок захвата:

```
Уровень 1: global_lock
Уровень 2: account_lock
Уровень 3: transaction_lock

Всегда: 1 -> 2 -> 3. Никогда не в обратном порядке.
```

Нарушение порядка — гарантированный путь к дедлоку.

### 9.2 Критическая секция должна быть минимальной

```c
// ПЛОХО: длинная критическая секция
pthread_mutex_lock(&mutex);
data = fetch_from_database();  // долго!
process(data);                  // долго!
store_result(result);
pthread_mutex_unlock(&mutex);

// ХОРОШО: только то, что действительно требует защиты
data_t local_copy;
pthread_mutex_lock(&mutex);
local_copy = shared_data;      // быстрая копия
pthread_mutex_unlock(&mutex);

result = process(local_copy);  // без блокировки

pthread_mutex_lock(&mutex);
shared_result = result;
pthread_mutex_unlock(&mutex);
```

### 9.3 Избегайте вызова callback под блокировкой

Вызов функции, предоставленной пользователем, под мьютексом — рецепт дедлока, если колбэк сам захватывает мьютексы. Паттерн: освободить блокировку перед вызовом, или использовать очередь событий.

### 9.4 Таблица выбора примитива

| Ситуация | Рекомендуемый примитив |
|---------|----------------------|
| Защита разделяемых данных | Mutex |
| Сигнализация о событии между потоками | Condition Variable + Mutex |
| Ограничение пула ресурсов | Semaphore |
| Между процессами | Named Semaphore / Shared Memory + Mutex (pshared) |
| Часто читается, редко пишется | RW-Lock (если > 10 читателей) |
| Очень короткая критическая секция | Spinlock (только ядро/RT) |
| Максимальная масштабируемость | Lock-free / MCS Lock |

## 10. Реализации в различных языках и платформах

### 10.1 C++

C++11 предоставляет стандартизированные примитивы:

```cpp
#include <mutex>
#include <shared_mutex>
#include <condition_variable>
#include <atomic>

// RAII-обёртка — мьютекс освобождается автоматически
std::mutex mtx;
std::unique_lock<std::mutex> lock(mtx);
// ... критическая секция ...
// lock уничтожается при выходе из scope

// Shared mutex (RW-lock)
std::shared_mutex rw_mutex;
{
    std::shared_lock<std::shared_mutex> r(rw_mutex); // read lock
    // несколько читателей одновременно
}
{
    std::unique_lock<std::shared_mutex> w(rw_mutex); // write lock
    // эксклюзивный доступ
}

// Condition variable
std::condition_variable cv;
std::mutex cv_mutex;
bool ready = false;

// Ожидание с предикатом (безопасно от spurious wakeup)
std::unique_lock<std::mutex> lk(cv_mutex);
cv.wait(lk, []{ return ready; }); // эквивалентно while(!ready) cv.wait(lk);
```

### 10.2 Go

Go предоставляет `sync.Mutex`, `sync.RWMutex`, `sync.Cond`, а также каналы как средство синхронизации:

```go
package main

import (
    "sync"
    "fmt"
)

type SafeCounter struct {
    mu sync.Mutex
    v  map[string]int
}

func (c *SafeCounter) Inc(key string) {
    c.mu.Lock()
    defer c.mu.Unlock()  // RAII-стиль через defer
    c.v[key]++
}

// Каналы как семафоры
func workerPool(n int) {
    sem := make(chan struct{}, n) // буферизованный канал = семафор
    sem <- struct{}{}             // acquire
    go func() {
        defer func() { <-sem }() // release
        // работа
    }()
}
```

### 10.3 Java

Java использует монитор на каждом объекте (`synchronized`) и явные `java.util.concurrent.locks`:

```java
import java.util.concurrent.locks.*;

// Synchronized — монитор объекта
class Counter {
    private int value = 0;
    
    public synchronized void increment() {
        value++; // неявный lock/unlock
    }
}

// Explicit ReentrantReadWriteLock
ReadWriteLock rwLock = new ReentrantReadWriteLock();
Lock readLock = rwLock.readLock();
Lock writeLock = rwLock.writeLock();

readLock.lock();
try {
    // ... чтение ...
} finally {
    readLock.unlock(); // всегда в finally!
}
```

## Заключение

Примитивы синхронизации — это не просто API, а воплощение тонкого взаимодействия между программой, операционной системой и процессором. Мьютекс через futex избегает системного вызова в отсутствие конкуренции, условная переменная атомарно объединяет освобождение блокировки с засыпанием, спинлок жертвует CPU ради минимальной задержки, MCS lock масштабируется за счёт локальности данных.

Правильный выбор примитива определяется характером нагрузки: как долго удерживается блокировка, сколько потоков конкурируют, насколько важна справедливость, допустима ли инверсия приоритетов. Не существует универсального ответа — только инженерный анализ конкретной ситуации, подкреплённый измерениями.

Параллельное программирование — сложная дисциплина, где ошибки проявляются редко и нестабильно. Инструменты (TSan, Helgrind, perf lock) и дисциплина (иерархия блокировок, минимальные критические секции, RAII) позволяют строить надёжные многопоточные системы, избегая классических ловушек — дедлоков, гонок и инверсии приоритетов.

## Литература и ссылки

1. Butenhof, D. R. *Programming with POSIX Threads*. Addison-Wesley, 1997. [https://www.informit.com/store/programming-with-posix-threads-9780201633924](https://www.informit.com/store/programming-with-posix-threads-9780201633924)
2. Michael, M. M., Scott, M. L. *Simple, Fast, and Practical Non-Blocking and Blocking Concurrent Queue Algorithms*. PODC 1996. [https://dl.acm.org/doi/10.1145/248052.248106](https://dl.acm.org/doi/10.1145/248052.248106)
3. Mellor-Crummey, J. M., Scott, M. L. *Algorithms for Scalable Synchronization on Shared-Memory Multiprocessors*. ACM TOCS, 1991. [https://dl.acm.org/doi/10.1145/103727.103729](https://dl.acm.org/doi/10.1145/103727.103729)
4. Franke, H., Russell, R., Kirwood, M. *Fuss, Futexes and Furwocks: Fast Userlevel Locking in Linux*. Ottawa Linux Symposium 2002. [https://www.kernel.org/doc/ols/2002/ols2002-pages-479-495.pdf](https://www.kernel.org/doc/ols/2002/ols2002-pages-479-495.pdf)
5. Linux Kernel Documentation: Locking. [https://www.kernel.org/doc/html/latest/locking/](https://www.kernel.org/doc/html/latest/locking/)
6. cppreference.com: std::mutex. [https://en.cppreference.com/w/cpp/thread/mutex](https://en.cppreference.com/w/cpp/thread/mutex)
7. POSIX.1-2017: pthread_mutex_lock. [https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_mutex_lock.html](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_mutex_lock.html)
8. Wikipedia: Spinlock. [https://en.wikipedia.org/wiki/Spinlock](https://en.wikipedia.org/wiki/Spinlock)
9. Williams, A. *C++ Concurrency in Action*. Manning, 2019. [https://www.manning.com/books/c-plus-plus-concurrency-in-action-second-edition](https://www.manning.com/books/c-plus-plus-concurrency-in-action-second-edition)
