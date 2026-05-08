# Процессы и потоки

## Введение

Когда вы открываете браузер, запускается не одна, а множество «задач»: основной процесс браузера, отдельный процесс для каждой вкладки (Chrome), рендеринговый движок, аудио-декодер, сетевой стек. Каждая вкладка изолирована: баг в одной не затрагивает другие. Внутри каждого процесса работают несколько потоков — один обрабатывает пользовательский ввод, другой загружает изображения, третий парсит JavaScript. Это классическое использование двух фундаментальных абстракций ОС: процессов и потоков.

Процесс — изолированная «коробка» с собственным адресным пространством, файловыми дескрипторами, правами. Поток — «нить выполнения» внутри этой коробки, разделяющая память с другими потоками того же процесса. Разница в изоляции и накладных расходах: создание процесса — дороже (нужно новое адресное пространство), но надёжнее. Создание потока — дешевле, но ошибка в одном может уничтожить всю программу.

---

## 1. Процессы

### 1.1 Process Control Block (PCB)

Ядро хранит информацию о каждом процессе в структуре **PCB (Process Control Block)** — в Linux это `struct task_struct` (более 700 полей!):

```c
// Упрощённая версия task_struct:
struct task_struct {
    // Состояние
    volatile long   state;       // TASK_RUNNING, TASK_INTERRUPTIBLE...
    int             exit_state;
    int             exit_code;
    
    // Идентификация
    pid_t           pid;         // Process ID
    pid_t           tgid;        // Thread Group ID (= PID группы)
    
    // Иерархия
    struct task_struct *parent;
    struct list_head   children;
    struct list_head   sibling;
    
    // Адресное пространство
    struct mm_struct   *mm;      // NULL для kernel threads
    struct mm_struct   *active_mm;
    
    // Файловые дескрипторы
    struct files_struct *files;
    
    // Сигналы
    struct signal_struct *signal;
    sigset_t blocked;
    
    // Приоритеты и планирование
    int prio;          // динамический приоритет
    int static_prio;   // заданный приоритет (-20..19, nice value)
    struct sched_entity se; // сущность планировщика (для CFS)
    
    // Использование ресурсов
    struct task_cputime cputime_expires;
    u64 utime, stime; // user и system CPU time
    
    // Credentials
    const struct cred *cred;  // UID, GID, capabilities
    
    // Стек ядра
    void *stack;  // указатель на kernel stack (8KB)
    
    // Имя процесса
    char comm[TASK_COMM_LEN];  // 16 байт
    
    // ... и ещё 700+ полей
};
```

### 1.2 Адресное пространство процесса

```
Виртуальное адресное пространство процесса (x86-64 Linux):

0xFFFFFFFFFFFFFFFF
        ...
0xFFFF800000000000 ← Kernel Space (128 TB) — недоступно из user space
        
        ...
0x00007FFFFFFFFFFF
        ←── stack (растёт вниз)
        ←── mmap region (разделяемые библиотеки, анонимные маппинги)
        
        ↑── heap (растёт вверх, через brk/sbrk)
        ↑── BSS (неинициализированные данные)
        ↑── Data (инициализированные данные)
        ↑── Text (код, read-only)
0x0000000000400000 ← начало кода для non-PIE (или случайный адрес для PIE)
0x0000000000000000
```

```bash
# Просмотр карты памяти процесса:
cat /proc/self/maps

# Вывод:
# 555555400000-555555401000 r-xp 00000000 08:01 123456 /bin/cat   ← .text
# 555555600000-555555601000 r--p 00000000 08:01 123456 /bin/cat   ← .rodata
# 555555601000-555555602000 rw-p 00001000 08:01 123456 /bin/cat   ← .data
# 7ffff7a00000-7ffff7b50000 r-xp 00000000 08:01 789012 libc.so.6 ← libc .text
# 7ffffffde000-7ffffffff000 rwxp 00000000 00:00 0 [stack]
```

### 1.3 Fork — создание процесса

`fork()` — системный вызов, создающий точную копию текущего процесса:

```c
#include <unistd.h>
#include <stdio.h>
#include <sys/types.h>

int main() {
    printf("Before fork: PID=%d\n", getpid());
    
    pid_t pid = fork();
    
    if (pid < 0) {
        perror("fork failed");
        return 1;
    }
    else if (pid == 0) {
        // Дочерний процесс: pid == 0
        printf("Child: PID=%d, PPID=%d\n", getpid(), getppid());
    }
    else {
        // Родительский процесс: pid == PID дочернего
        printf("Parent: PID=%d, child PID=%d\n", getpid(), pid);
    }
    
    return 0;
}

// Вывод:
// Before fork: PID=1234
// Parent: PID=1234, child PID=1235
// Child: PID=1235, PPID=1234
```

### 1.4 Copy-on-Write (CoW) при fork

Наивная реализация fork копировала бы всё адресное пространство (гигабайты) — очень медленно. Оптимизация: **Copy-on-Write**.

```
После fork():
Parent Address Space    Child Address Space
┌──────────────┐       ┌──────────────┐
│  page 0x1000 │──────▶│ Physical Page│◀──│  page 0x1000 │
│  (read-only) │       │  A (shared)  │   │  (read-only) │
├──────────────┤       └──────────────┘   ├──────────────┤
│  page 0x2000 │──────▶│ Physical Page│◀──│  page 0x2000 │
│  (read-only) │       │  B (shared)  │   │  (read-only) │
└──────────────┘       └──────────────┘   └──────────────┘

Когда Parent пишет в page 0x1000:
→ Page fault! ОС копирует страницу
→ Parent получает свою копию
→ Child остаётся с оригиналом

Parent Address Space    Child Address Space
┌──────────────┐       ┌──────────────┐
│  page 0x1000 │──────▶│ Physical Page│   │  page 0x1000 │──▶│ Orig Page A │
│  (read-write)│       │  A' (copy)   │   │  (read-only) │   └─────────────┘
└──────────────┘       └──────────────┘   └──────────────┘
```

Большинство страниц никогда не изменяются после fork (код, read-only данные) — они всегда разделяются. Копируются только те страницы, в которые действительно пишут.

### 1.5 Exec — замена образа процесса

После fork обычно следует `exec*()` — замена образа процесса новой программой:

```c
// execve — низкоуровневый примитив:
execve("/usr/bin/ls", argv, envp);

// Более удобные обёртки:
execlp("ls", "ls", "-la", NULL);    // использует PATH
execvp("ls", args);                  // использует PATH + argv[]
execle("/bin/ls", "ls", NULL, env); // полный путь + env

// Что делает exec:
// 1. Загружает новый ELF из файла
// 2. Заменяет виртуальное адресное пространство
// 3. Сбрасывает сигналы, закрывает O_CLOEXEC файлы
// 4. Устанавливает новый stack, heap
// 5. Передаёт управление в новую точку входа
// PID остаётся тем же!
```

```c
// Классический shell pattern: fork + exec
pid_t child = fork();
if (child == 0) {
    // Дочерний — запустить команду
    execvp(argv[0], argv);
    perror("exec failed");  // сюда попадаем только если exec завершился с ошибкой
    exit(1);
}
// Родительский — ждать результата
int status;
waitpid(child, &status, 0);
printf("Command exited with: %d\n", WEXITSTATUS(status));
```

---

## 2. Потоки

### 2.1 POSIX Threads (pthreads)

```c
#include <pthread.h>
#include <stdio.h>

// Функция потока:
void *thread_func(void *arg) {
    int id = *(int *)arg;
    printf("Thread %d: running\n", id);
    // Возвращаем значение через указатель или NULL:
    return NULL;
}

int main() {
    pthread_t threads[4];
    int ids[4] = {0, 1, 2, 3};
    
    // Создать потоки:
    for (int i = 0; i < 4; i++) {
        int ret = pthread_create(&threads[i], NULL, thread_func, &ids[i]);
        if (ret != 0) {
            fprintf(stderr, "pthread_create failed: %d\n", ret);
            return 1;
        }
    }
    
    // Ждать завершения всех потоков:
    for (int i = 0; i < 4; i++) {
        void *retval;
        pthread_join(threads[i], &retval);
        printf("Thread %d joined\n", i);
    }
    
    return 0;
}
```

```bash
gcc -o threads threads.c -lpthread
./threads
```

### 2.2 Что разделяют потоки

Все потоки одного процесса разделяют:
- **Виртуальное адресное пространство** (код, данные, heap)
- **Открытые файловые дескрипторы**
- **Сигнальные обработчики** (но маски сигналов — индивидуальные)
- **PID (Thread Group ID)**
- **Рабочий каталог**

Каждый поток имеет своё:
- **Стек** (stack) — обычно 8MB на POSIX
- **TLS (Thread-Local Storage)**
- **Регистры процессора** (сохраняются при context switch)
- **errno** (на самом деле TLS переменная)
- **Thread ID (TID)** = Linux PID (да, в Linux каждый поток — отдельная task_struct!)

```c
#include <sys/syscall.h>
#include <unistd.h>

pid_t tid = syscall(SYS_gettid);   // Linux Thread ID
pid_t pid = getpid();               // Process ID (TGID)
// В однопоточном процессе: tid == pid
// В многопоточном: tid разные для каждого потока, pid одинаковый
```

### 2.3 Атрибуты потока

```c
pthread_attr_t attr;
pthread_attr_init(&attr);

// Размер стека:
pthread_attr_setstacksize(&attr, 2 * 1024 * 1024);  // 2MB

// Detached state (поток не нужно join-ить):
pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);

// Scheduling policy и приоритет:
pthread_attr_setschedpolicy(&attr, SCHED_FIFO);
struct sched_param param = { .sched_priority = 50 };
pthread_attr_setschedparam(&attr, &param);

pthread_create(&tid, &attr, thread_func, arg);
pthread_attr_destroy(&attr);
```

### 2.4 Thread-Local Storage (TLS)

```c
// C11/GCC: __thread или _Thread_local
__thread int per_thread_counter = 0;

void increment_local() {
    per_thread_counter++;  // каждый поток имеет свою копию
}

// C++11:
thread_local int cpp_counter = 0;

// Python:
import threading
local = threading.local()
local.counter = 0  # каждый поток видит свой local.counter
```

---

## 3. Сравнение: Процесс vs Поток

### 3.1 Стоимость создания

```c
// Измерение времени создания (Linux, x86-64):
// fork():   ~30-50 мкс (клонирование page tables, копирование PCB)
// pthread_create(): ~10-15 мкс (создание stack, новая task_struct)
// clone() с CLONE_VM: ~5-10 мкс (минимальное клонирование)
```

```python
# Python: сравнение времени создания
import time
import multiprocessing
import threading

N = 1000

# Процессы:
start = time.perf_counter()
for _ in range(N):
    p = multiprocessing.Process(target=lambda: None)
    p.start()
    p.join()
process_time = time.perf_counter() - start
print(f"Process creation: {process_time*1000/N:.2f} ms each")

# Потоки:
start = time.perf_counter()
for _ in range(N):
    t = threading.Thread(target=lambda: None)
    t.start()
    t.join()
thread_time = time.perf_counter() - start
print(f"Thread creation: {thread_time*1000/N:.2f} ms each")

# Типичные результаты:
# Process creation: ~2-5 ms each
# Thread creation: ~0.1-0.3 ms each
# (Процессы медленнее в 10-50 раз)
```

### 3.2 Сравнительная таблица

| Характеристика | Process | Thread |
|---------------|---------|--------|
| Адресное пространство | Отдельное | Разделяемое |
| Изоляция | Полная | Нет (сбой убивает все потоки) |
| Создание | ~50 мкс | ~15 мкс |
| Context switch | ~2-5 мкс (TLB flush) | ~0.5-2 мкс (нет TLB flush) |
| IPC | Slow (pipe, socket, shm) | Fast (общая память) |
| Масштабируемость | Хорошая (до 100-1000) | Отличная (до 10000) |
| GIL (Python) | Нет | Есть (обходится multiprocessing) |
| Применение | Изолированные задачи, безопасность | Параллельные задачи в одной программе |

---

## 4. Green Threads и Goroutines

### 4.1 OS Threads vs Green Threads

**OS Thread (1:1 mapping):**
- Каждый thread = отдельная OS thread (task_struct в Linux)
- Планировщик ОС управляет
- Context switch — через ядро (~мкс)
- Стек: обычно 8MB (зарезервировано)
- Предел: обычно ~10,000 потоков (ограничение памяти и pid_max)

**Green Threads (M:N или N:1):**
- N «зелёных» потоков → M OS threads (M << N)
- Runtime управляет зелёными потоками в user space
- Context switch — без ядра (~нс для кооперативных)
- Стек: маленький, растущий (начинается с 2-8 KB)
- Предел: миллионы (нет ресурсов ядра)

### 4.2 Goroutines в Go

Go реализует самую успешную версию green threads — goroutines:

```go
package main

import (
    "fmt"
    "sync"
    "runtime"
)

func worker(id int, wg *sync.WaitGroup) {
    defer wg.Done()
    fmt.Printf("Worker %d running on OS thread %d\n", 
               id, runtime.NumCPU())
}

func main() {
    // Число OS потоков = числу CPU:
    runtime.GOMAXPROCS(runtime.NumCPU())
    
    var wg sync.WaitGroup
    
    // Создать 100,000 goroutines:
    for i := 0; i < 100000; i++ {
        wg.Add(1)
        go worker(i, &wg)  // дешевле чем thread!
    }
    
    wg.Wait()
    fmt.Println("All done")
}
```

```bash
# Запустить:
go run goroutines.go
# 100,000 goroutines на ~8 OS threads
# Память: ~100,000 * 2KB = ~200 MB (vs 100,000 * 8MB = 800 GB для OS threads!)
```

**Почему goroutines дешевле:**
1. **Маленький стек** — начинается с 2-8 KB (растёт при необходимости, максимум 1GB)
2. **M:N scheduler** — Go runtime планирует N goroutines на M OS потоках (обычно M = GOMAXPROCS = число CPU)
3. **Work stealing** — если OS поток простаивает, «ворует» goroutines от занятых
4. **Cooperative + preemptive** — goroutine снимается при IO, channel operations или функциях-check-точках

### 4.3 Async/Await как альтернатива

```python
# Python asyncio: coroutines (кооперативные зелёные потоки)
import asyncio

async def worker(id: int) -> str:
    await asyncio.sleep(0.001)  # yield: позволить другим работать
    return f"Worker {id} done"

async def main():
    # Запустить 1000 "concurrent" задач в одном OS thread:
    tasks = [worker(i) for i in range(1000)]
    results = await asyncio.gather(*tasks)
    print(f"Completed {len(results)} tasks")

asyncio.run(main())
```

Ограничение asyncio: **одноядерный** (один OS thread). CPU-intensive задачи нужно выносить в ProcessPoolExecutor.

---

## 5. Python: GIL и его обходы

### 5.1 Global Interpreter Lock

Python (CPython) имеет GIL — мьютекс, который разрешает выполнять Python bytecode только одному потоку в один момент:

```python
import threading
import time

counter = 0

def increment_counter(n):
    global counter
    for _ in range(n):
        counter += 1  # не атомарна! но GIL защищает байткод

threads = [threading.Thread(target=increment_counter, args=(1_000_000,))
           for _ in range(4)]

[t.start() for t in threads]
[t.join() for t in threads]

print(counter)  # может быть меньше 4,000,000 без GIL, но с GIL ≈ правильно
```

**GIL и IO:**

GIL освобождается при I/O операциях! Поэтому threading в Python отлично работает для IO-bound задач:

```python
import threading
import urllib.request
import time

urls = ["http://example.com"] * 10

def fetch(url):
    urllib.request.urlopen(url).read()  # GIL освобождается во время сетевого IO!

# Параллельные HTTP запросы:
start = time.perf_counter()
threads = [threading.Thread(target=fetch, args=(url,)) for url in urls]
[t.start() for t in threads]
[t.join() for t in threads]
print(f"Threading: {time.perf_counter()-start:.2f}s")

# Последовательно — намного медленнее:
start = time.perf_counter()
for url in urls: fetch(url)
print(f"Sequential: {time.perf_counter()-start:.2f}s")
```

### 5.2 CPU-bound: используем multiprocessing

```python
import multiprocessing
import time

def cpu_intensive(n):
    return sum(i*i for i in range(n))

# Многопроцессорно (обходит GIL):
with multiprocessing.Pool(4) as pool:
    start = time.perf_counter()
    results = pool.map(cpu_intensive, [10_000_000] * 4)
    print(f"Multiprocessing: {time.perf_counter()-start:.2f}s")
```

---

## 6. Process Lifecycle

### 6.1 Состояния процесса

```
            fork()              schedule()
              │                     │
              ▼                     ▼
          Created ─────────────▶ Running ──────────────▶ Terminated
                                   │                         │
                    I/O, wait()    │ preempt, yield()        │ exit()
                         │         │                         │
                         ▼         ▼                         ▼
                     Blocked    Ready (Runnable)          Zombie
                         │         │                    (ждёт wait())
                         └─────────┘
                        I/O complete
```

**Zombie (defunct) процесс:**

После `exit()` процесс становится зомби — он завершился, но PCB остаётся пока родитель не вызовет `wait()`:

```c
#include <sys/wait.h>

pid_t child = fork();
if (child == 0) {
    exit(42);  // дочерний завершается → становится zombie
}

// Родительский должен вызвать wait():
int status;
pid_t dead = waitpid(child, &status, 0);
if (WIFEXITED(status))
    printf("Child exited: %d\n", WEXITSTATUS(status));  // 42

// Без wait() → zombie накапливаются, занимают PID
// Если родитель умирает раньше → дети усыновляются init (PID 1)
// init регулярно вызывает wait() → не даёт накапливаться зомби
```

### 6.2 Daemon процессы

```c
// Превратить процесс в daemon (background):
int daemonize() {
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid > 0) exit(0);   // родитель завершается
    
    // Дочерний становится session leader:
    if (setsid() < 0) return -1;
    
    // Fork ещё раз (не может получить терминал):
    pid = fork();
    if (pid < 0) return -1;
    if (pid > 0) exit(0);
    
    // Изменить рабочую директорию:
    chdir("/");
    
    // Закрыть стандартные FD:
    close(STDIN_FILENO);
    close(STDOUT_FILENO);
    close(STDERR_FILENO);
    
    // Открыть /dev/null для stdin/stdout/stderr:
    open("/dev/null", O_RDONLY);  // stdin
    open("/dev/null", O_WRONLY);  // stdout
    open("/dev/null", O_RDWR);    // stderr
    
    return 0;
}
```

---

## 7. Практические примеры

### 7.1 Thread Pool

```c
// Простой thread pool на pthreads:
#include <pthread.h>
#include <stdlib.h>
#include <stdio.h>

#define POOL_SIZE 4
#define QUEUE_SIZE 100

typedef void (*task_fn)(void *);

struct task {
    task_fn fn;
    void *arg;
};

struct thread_pool {
    pthread_t threads[POOL_SIZE];
    struct task queue[QUEUE_SIZE];
    int head, tail, count;
    pthread_mutex_t mutex;
    pthread_cond_t  not_empty;
    pthread_cond_t  not_full;
    int shutdown;
};

void *worker_thread(void *arg) {
    struct thread_pool *pool = (struct thread_pool *)arg;
    
    while (1) {
        pthread_mutex_lock(&pool->mutex);
        
        while (pool->count == 0 && !pool->shutdown)
            pthread_cond_wait(&pool->not_empty, &pool->mutex);
        
        if (pool->shutdown && pool->count == 0) {
            pthread_mutex_unlock(&pool->mutex);
            break;
        }
        
        struct task t = pool->queue[pool->head];
        pool->head = (pool->head + 1) % QUEUE_SIZE;
        pool->count--;
        
        pthread_cond_signal(&pool->not_full);
        pthread_mutex_unlock(&pool->mutex);
        
        t.fn(t.arg);  // Выполнить задачу
    }
    return NULL;
}
```

### 7.2 Измерение overhead context switch

```python
import time
import threading

# Измерение overhead переключения между потоками:
N = 100_000
barrier = threading.Barrier(2)
times = []

def thread_a():
    for i in range(N):
        start = time.perf_counter_ns()
        barrier.wait()  # синхронизация → context switch
        times.append(time.perf_counter_ns() - start)

def thread_b():
    for _ in range(N):
        barrier.wait()

t_a = threading.Thread(target=thread_a)
t_b = threading.Thread(target=thread_b)
t_a.start(); t_b.start()
t_a.join(); t_b.join()

import statistics
print(f"Context switch overhead:")
print(f"  Median: {statistics.median(times)/1000:.1f} µs")
print(f"  P99:    {sorted(times)[int(N*0.99)]/1000:.1f} µs")
# Типично: ~1-5 µs median, ~10-50 µs P99
```

---

## Заключение

Процессы и потоки — фундаментальные строительные блоки многозадачных систем. Ключевые выводы:

1. **Процесс = изоляция + адресное пространство.** Используйте процессы там, где нужна надёжная изоляция: браузер, веб-сервер, контейнеры.

2. **Поток = параллельность + разделяемая память.** Используйте потоки для параллельных вычислений в одном контексте: парсинг, web scraping, GUI-приложения.

3. **CoW при fork** — делает fork дешёвым даже для больших процессов.

4. **Goroutines** (и аналоги) — золотая середина: дешевизна green threads + параллельность через work stealing.

5. **Python GIL** — не проблема для IO-bound, но CPU-bound требует multiprocessing или других языков/модулей (NumPy освобождает GIL).

---

## Литература и источники

1. Kerrisk, M. (2010). *The Linux Programming Interface*. No Starch Press. — Части 24-28: Processes, Memory layout, fork/exec.

2. Stevens, W. R., & Rago, S. A. (2013). *Advanced Programming in the UNIX Environment* (3rd ed.). Addison-Wesley.

3. Go documentation. *Effective Go: Goroutines*. — https://go.dev/doc/effective_go#goroutines

4. Wikipedia. *Process (computing)*. — https://en.wikipedia.org/wiki/Process_(computing)

5. Wikipedia. *Thread (computing)*. — https://en.wikipedia.org/wiki/Thread_(computing)

6. Wikipedia. *Green thread*. — https://en.wikipedia.org/wiki/Green_thread

7. Python docs. *threading — Thread-based parallelism*. — https://docs.python.org/3/library/threading.html

8. Beazley, D. (2010). *Inside the Python GIL*. PyCon 2010. — https://www.dabeaz.com/python/GIL.pdf

9. Linux Kernel Source. `include/linux/sched.h` (task_struct). — https://github.com/torvalds/linux/blob/master/include/linux/sched.h

10. POSIX.1-2017. *pthread_create*. — https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_create.html
