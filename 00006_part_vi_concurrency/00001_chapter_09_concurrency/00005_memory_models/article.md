# Memory models языков (Java, C++, Go)

## Введение

Разработчик пишет код и интуитивно ожидает: инструкции выполняются в том порядке, в каком написаны. Эта интуиция ломается в многопоточном контексте — и ломается незаметно, приводя к нейтрализующим ошибкам, которые проявляются лишь под нагрузкой на production-серверах.

Компилятор и CPU имеют право переставлять инструкции, если это не меняет наблюдаемого поведения в однопоточном контексте. Компилятор может удалить «лишнюю» запись в переменную. CPU может переупорядочить обращения к памяти для лучшей загрузки pipeline. Кэши разных ядер могут содержать устаревшие данные. Всё это корректно для одного потока — и катастрофично при shared state между потоками.

**Memory model** языка программирования — это формальная спецификация, определяющая, какие значения поток может наблюдать при чтении shared переменной. Memory model устанавливает отношение **happens-before**: если операция A happens-before операции B, то все эффекты A видны в B. Без явной happens-before цепочки значение прочитанного — неопределено.

---

## 1. Что происходит без memory model

### 1.1 Проблема видимости

```java
// Java — пример проблемы видимости (без volatile)
public class VisibilityProblem {
    static boolean flag = false;
    static int data = 0;
    
    public static void main(String[] args) throws InterruptedException {
        Thread writer = new Thread(() -> {
            data = 42;          // (1) Пишем данные
            flag = true;        // (2) Устанавливаем флаг
        });
        
        Thread reader = new Thread(() -> {
            while (!flag) {}    // (3) Ждём флага
            System.out.println(data);  // (4) Ожидаем: 42
            // Реальность: может напечатать 0!
        });
        
        reader.start();
        writer.start();
    }
}
```

Без `volatile` на `flag`, JIT компилятор может:
- Кешировать значение `flag` в регистре (reader никогда не увидит изменение)
- Переставить записи (2) и (1) (reader увидит `flag=true` но `data=0`)

### 1.2 Reordering на уровне CPU

```c
// C — пример reordering
int x = 0, y = 0;
int r1, r2;

// Поток 1          // Поток 2
x = 1;             y = 1;
r1 = y;            r2 = x;

// На x86 маловероятно, но на ARM/Power возможен итог:
// r1 == 0 && r2 == 0
// CPU переставил Store и Load для оптимизации
```

Intel x86 имеет относительно строгую модель (Total Store Order), но ARM и POWER — значительно слабее. Код без явных барьеров может вести себя по-разному на разных архитектурах.

---

## 2. Java Memory Model (JMM)

JMM был введён в Java 5 (JSR-133, 2004). До этого Java имела broken memory model — programs compiled under early JLS were likely incorrect in multithreaded environments.

### 2.1 Happens-Before в Java

Отношение happens-before (hb) в JMM гарантирует видимость и порядок:

**Правило 1: Program Order** — каждая операция в потоке hb каждой следующей операции в том же потоке.

**Правило 2: Monitor Lock** — разблокировка монитора hb каждой последующей блокировки того же монитора.

**Правило 3: Volatile** — запись в volatile переменную hb каждому последующему чтению той же переменной.

**Правило 4: Thread Start** — `Thread.start()` hb первой операции запускаемого потока.

**Правило 5: Thread Join** — последняя операция потока hb возврату из `join()`.

**Правило 6: Транзитивность** — если A hb B и B hb C, то A hb C.

### 2.2 Volatile

```java
public class VolatileExample {
    // volatile: 
    // 1. Запись видна другим потокам немедленно (нет кеширования в регистрах)
    // 2. Все предшествующие записи flush в память перед volatile write
    // 3. Все последующие чтения не перемещаются до volatile read
    private volatile boolean ready = false;
    private int value = 0;
    
    public void write() {
        value = 42;          // (1)
        ready = true;        // (2) volatile write — happens-before read
    }
    
    public void read() {
        if (ready) {         // (3) volatile read
            // Гарантированно видим value = 42 (1 hb 2 hb 3 hb 4)
            System.out.println(value);  // (4) ВСЕГДА 42
        }
    }
}
```

**volatile НЕ обеспечивает атомарность сложных операций**:

```java
volatile int counter = 0;

// НЕПРАВИЛЬНО — volatile не делает ++ атомарным
// Это всё ещё read-modify-write
counter++;  // Гонка данных!

// ПРАВИЛЬНО — атомарные классы
AtomicInteger atomicCounter = new AtomicInteger(0);
atomicCounter.incrementAndGet();  // Атомарно
```

### 2.3 synchronized

`synchronized` создаёт happens-before при входе/выходе из монитора:

```java
public class SynchronizedCounter {
    private int count = 0;
    
    // synchronized method — lock на this
    public synchronized void increment() {
        count++;
    }
    
    // synchronized block — explicit lock
    public void addIfPositive(int delta) {
        synchronized (this) {
            if (delta > 0) {
                count += delta;
            }
        }
    }
    
    public synchronized int getCount() {
        return count;
    }
}
```

### 2.4 java.util.concurrent.Lock

```java
import java.util.concurrent.locks.*;

public class ReadWriteCache {
    private final Map<String, Object> cache = new HashMap<>();
    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    private final Lock readLock = lock.readLock();
    private final Lock writeLock = lock.writeLock();
    
    public Object get(String key) {
        readLock.lock();
        try {
            return cache.get(key);
        } finally {
            readLock.unlock();
        }
    }
    
    public void put(String key, Object value) {
        writeLock.lock();
        try {
            cache.put(key, value);
        } finally {
            writeLock.unlock();
        }
    }
}
```

### 2.5 Double-Checked Locking — правильно

Классический пример, демонстрирующий важность JMM:

```java
// НЕПРАВИЛЬНО (до Java 5)
public class Singleton {
    private static Singleton instance;
    
    public static Singleton getInstance() {
        if (instance == null) {        // Первая проверка без блокировки
            synchronized (Singleton.class) {
                if (instance == null) { // Вторая проверка с блокировкой
                    instance = new Singleton(); // Создание не атомарно!
                    // JVM может: 1. выделить память, 2. вернуть ссылку, 3. инициализировать
                    // Другой поток может увидеть instance != null до инициализации!
                }
            }
        }
        return instance;
    }
}

// ПРАВИЛЬНО (Java 5+, с volatile)
public class SafeSingleton {
    private volatile static SafeSingleton instance;  // volatile!
    
    public static SafeSingleton getInstance() {
        if (instance == null) {
            synchronized (SafeSingleton.class) {
                if (instance == null) {
                    instance = new SafeSingleton();
                    // volatile гарантирует: полная инициализация visible до ссылки
                }
            }
        }
        return instance;
    }
}

// Ещё лучше — через holder class
public class HolderSingleton {
    private static class Holder {
        static final HolderSingleton INSTANCE = new HolderSingleton();
    }
    
    public static HolderSingleton getInstance() {
        return Holder.INSTANCE;  // ClassLoader гарантирует thread-safety
    }
}
```

---

## 3. C++ Memory Model (C++11)

C++11 ввёл первую стандартизированную memory model для C++. До этого C++ был «написан для однопроцессорных машин» — любой многопоточный код был технически undefined behavior.

### 3.1 std::atomic и memory_order

```cpp
#include <atomic>
#include <thread>
#include <cassert>

std::atomic<int> data{0};
std::atomic<bool> ready{false};

void producer() {
    data.store(42, std::memory_order_relaxed);    // (1)
    ready.store(true, std::memory_order_release); // (2) release fence
}

void consumer() {
    while (!ready.load(std::memory_order_acquire)) {}  // (3) acquire fence
    // Всё что было до (2) visible после (3)
    assert(data.load(std::memory_order_relaxed) == 42);  // (4) всегда true
}

int main() {
    std::thread t1(producer);
    std::thread t2(consumer);
    t1.join();
    t2.join();
}
```

### 3.2 Data Race — Undefined Behavior

В C++ data race — это **undefined behavior**. Не «непредсказуемое поведение», а literally UB: компилятор может делать что угодно:

```cpp
int x = 0;

// Поток 1
x = 1;  // Без атомарности и без синхронизации

// Поток 2
int y = x;  // Одновременная запись и чтение = DATA RACE = UB

// Компилятор может:
// - Удалить чтение (оптимизировать)
// - Переупорядочить
// - Внести бесконечный цикл (UB allows anything)
```

```cpp
// ПРАВИЛЬНО — используем atomic
std::atomic<int> safe_x{0};

// Поток 1
safe_x.store(1, std::memory_order_relaxed);

// Поток 2
int y = safe_x.load(std::memory_order_relaxed);  // Безопасно
```

### 3.3 Memory Fences (барьеры)

```cpp
#include <atomic>

// Явные барьеры памяти
std::atomic<int> counter{0};

void thread_func() {
    counter.fetch_add(1, std::memory_order_relaxed);
    
    // Барьер: все расслабленные операции до барьера
    // видны до операций после барьера в других потоках
    std::atomic_thread_fence(std::memory_order_release);
}

// Или с seq_cst (самый строгий):
void strict_func() {
    // Все операции видны всем потокам в одном глобальном порядке
    counter.fetch_add(1, std::memory_order_seq_cst);
}
```

### 3.4 Relaxed — пример корректного использования

```cpp
#include <atomic>
#include <thread>

// Счётчик статистики — нам важна только атомарность, не порядок
std::atomic<uint64_t> request_count{0};
std::atomic<uint64_t> error_count{0};

void handle_request(bool success) {
    request_count.fetch_add(1, std::memory_order_relaxed);
    if (!success) {
        error_count.fetch_add(1, std::memory_order_relaxed);
    }
    // Порядок относительно других операций нас не волнует
}

void print_stats() {
    // Для статистики relaxed допустим — не нужна точная синхронизация
    printf("Requests: %lu, Errors: %lu\n",
           request_count.load(std::memory_order_relaxed),
           error_count.load(std::memory_order_relaxed));
}
```

---

## 4. Go Memory Model

Go Memory Model (официально задокументирован в 2022 году, хотя существовал с начала) определяет happens-before через:
- Инициализация горутины (`go` statement)
- Канальные операции
- `sync` примитивы
- `sync/atomic`

### 4.1 Горутины и happens-before

```go
package main

import (
    "fmt"
    "sync"
)

var (
    x    = 0
    done = false
    mu   sync.Mutex
)

func setup() {
    x = 42          // (1)
    mu.Lock()
    done = true     // (2)
    mu.Unlock()     // (3) unlock hb lock
}

func main() {
    go setup()
    
    mu.Lock()       // (4) lock — гарантирует видимость (1) и (2) если (3) hb (4)
    for !done {
        mu.Unlock()
        mu.Lock()
    }
    fmt.Println(x)  // Гарантированно 42 — благодаря mu
    mu.Unlock()
}
```

### 4.2 Каналы и happens-before

```go
package main

import "fmt"

var c = make(chan int, 10)
var x int

func f() {
    x = 42             // (1) — происходит до отправки в канал
    c <- 0             // (2) send hb receive
}

func main() {
    go f()
    <-c                // (3) receive
    fmt.Println(x)     // (4) Гарантированно 42: (1) hb (2) hb (3) hb (4)
}
```

**Важное правило** для небуферизованных каналов:
- Send hb Receive (для небуферизованных)
- Receive hb Return (для небуферизованных)

**Для буферизованных каналов**:
- Receive hb Send (заполнение буфера, capacity(ch) < k-ый send)

```go
// Буферизованный канал как семафор
// Гарантирует не более N параллельных операций
var sem = make(chan struct{}, 3)  // Семафор ёмкостью 3

func limited() {
    sem <- struct{}{}  // Захватываем "токен"
    defer func() { <-sem }()  // Освобождаем при выходе
    
    // Критическая секция — не более 3 горутин одновременно
    doWork()
}
```

### 4.3 sync.WaitGroup, sync.Once

```go
package main

import (
    "fmt"
    "sync"
)

// sync.WaitGroup — happens-before
func main() {
    var wg sync.WaitGroup
    data := make([]int, 5)
    
    for i := range data {
        wg.Add(1)
        go func(i int) {
            defer wg.Done()
            data[i] = i * i  // Каждая горутина пишет в свой элемент — нет гонки
        }(i)
    }
    
    wg.Wait()  // wg.Done() hb wg.Wait() return
    fmt.Println(data)  // Гарантированно видим все записи
}

// sync.Once — безопасная одноразовая инициализация
var (
    once sync.Once
    db   *Database
)

func getDB() *Database {
    once.Do(func() {
        db = &Database{/* init */}
    })
    return db  // Гарантированно инициализирована
}
```

### 4.4 sync/atomic в Go

```go
package main

import (
    "fmt"
    "sync/atomic"
)

func main() {
    var counter int64
    
    // Атомарные операции без блокировок
    atomic.AddInt64(&counter, 1)
    atomic.AddInt64(&counter, -1)
    
    // LoadInt64 — атомарное чтение
    val := atomic.LoadInt64(&counter)
    fmt.Println(val)
    
    // CompareAndSwap
    old := int64(0)
    new := int64(1)
    success := atomic.CompareAndSwapInt64(&counter, old, new)
    fmt.Println("CAS success:", success)
    
    // atomic.Value для произвольных типов
    var config atomic.Value
    config.Store(map[string]string{"key": "value"})
    // ... позже ...
    current := config.Load().(map[string]string)
    fmt.Println(current["key"])
}
```

---

## 5. Data Race — невидимые баги

### 5.1 Классический Go data race

```go
package main

import (
    "fmt"
    "sync"
)

// НЕПРАВИЛЬНО — data race
var counter int

func badIncrement() {
    var wg sync.WaitGroup
    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            counter++  // DATA RACE!
        }()
    }
    wg.Wait()
    fmt.Println(counter)  // Меньше 1000
}

// ПРАВИЛЬНО — atomic
var atomicCounter int64

func goodIncrement() {
    var wg sync.WaitGroup
    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            atomic.AddInt64(&atomicCounter, 1)
        }()
    }
    wg.Wait()
    fmt.Println(atomic.LoadInt64(&atomicCounter))  // Всегда 1000
}
```

### 5.2 Обнаружение: Race Detector

Go имеет встроенный race detector (основан на ThreadSanitizer):

```bash
# Запуск с race detector
go run -race main.go
go test -race ./...

# Вывод при обнаружении гонки:
# ==================
# WARNING: DATA RACE
# Write at 0x00c0000b4010 by goroutine 7:
#   main.badIncrement.func1()
#       /path/to/main.go:15 +0x38
#
# Previous read at 0x00c0000b4010 by goroutine 6:
#   main.badIncrement.func1()
#       /path/to/main.go:15 +0x30
# ==================
```

### 5.3 ThreadSanitizer для C++

```bash
# Компиляция с TSan
clang++ -fsanitize=thread -g -O1 -o program program.cpp
./program

# Обнаруживает:
# - Data races
# - Use of uninitialized mutex
# - Deadlocks
# - Thread leak
```

---

## 6. Сравнение Memory Models

| Характеристика | Java (JMM) | C++ (C++11) | Go |
|---------------|-----------|-------------|-----|
| Год введения | 2004 (Java 5) | 2011 | 2009 (doc 2022) |
| Data race | Undefined behavior | Undefined behavior | Defined (but wrong) |
| Базовый примитив | volatile, synchronized | std::atomic | sync, chan |
| Seq-cst по умолчанию | synchronized | std::atomic (seq_cst) | sync primitives |
| Relaxed операции | Нет (есть VarHandle) | std::memory_order_relaxed | sync/atomic |
| Race detector | FindBugs, tools | ThreadSanitizer | встроенный |
| Формализация | JSR-133 | ISO C++ | Go spec |

### 6.1 Общие принципы

1. **Всегда устанавливайте happens-before** для shared state между потоками
2. **Не полагайтесь на интуицию** — компилятор и CPU хитрее
3. **Используйте высокоуровневые примитивы**: `synchronized`, `Lock`, `channel` — правильно реализуют нужные барьеры
4. **Минимизируйте shared mutable state** — лучшая защита от data race
5. **Запускайте race detector** в CI

---

## Заключение

Memory model — это контракт между программистом, компилятором и процессором. Без понимания этого контракта многопоточный код содержит невидимые баги, которые проявляются редко, нерепродуцируемо и катастрофически.

**Ключевые выводы**:

1. **Happens-before** — единственная гарантия видимости между потоками. Без него — undefined behavior (C++) или непредсказуемость (Java, Go).

2. **Java**: `volatile` для флагов видимости, `synchronized`/`Lock` для атомарных секций, `java.util.concurrent.atomic` для атомарных операций.

3. **C++**: `std::atomic` с правильным `memory_order`. `relaxed` — только для независимых счётчиков. `acquire/release` — для передачи данных. `seq_cst` — по умолчанию когда не уверены.

4. **Go**: каналы и `sync` примитивы автоматически устанавливают happens-before. Запускайте `go test -race` в CI.

5. **Data race в C++ — UB**. Это не «иногда неправильное значение», это «компилятор может делать всё что угодно». Относитесь серьёзно.

---

## Литература и источники

1. Manson, J., Pugh, W., & Adve, S. (2005). The Java Memory Model. *ACM SIGPLAN Notices*, 40(1), 378-391.
2. Boehm, H., & Adve, S. (2008). Foundations of the C++ Concurrency Memory Model. *ACM SIGPLAN Notices*.
3. The Go Memory Model. https://go.dev/ref/mem
4. JSR-133: Java Memory Model and Thread Specification. https://jcp.org/en/jsr/detail?id=133
5. ISO/IEC 14882:2011 (C++11). §29 Atomic operations library.
6. Preshing, J. (2013). The Happens-Before Relation. https://preshing.com/20130702/the-happens-before-relation/
7. Williams, A. (2019). *C++ Concurrency in Action*, 2nd Edition. Manning.
8. Goetz, B. et al. (2006). *Java Concurrency in Practice*. Addison-Wesley.
9. McKenney, P. E. (2017). *Is Parallel Programming Hard, And, If So, What Can You Do About It?* (2nd edition). https://mirrors.edge.kernel.org/pub/linux/kernel/people/paulmck/perfbook/perfbook.html
10. Wikipedia. Memory model (programming). https://en.wikipedia.org/wiki/Memory_model_(programming)
