# Дедлоки и гонки данных

Дедлоки и гонки данных — две наиболее коварные категории ошибок параллельного программирования. Их объединяет одно свойство: они проявляются нестабильно, зависят от планировщика и состояния кэш-памяти, а воспроизведение в отладчике бывает невозможным. Программа, работающая корректно тысячи раз, ломается на производстве под нагрузкой — в самый неудачный момент. Понимание природы этих ошибок, условий их возникновения и инструментов обнаружения является фундаментальным требованием к разработчику, пишущему многопоточный код.

Гонка данных (data race) возникает, когда два потока обращаются к одной ячейке памяти без синхронизации, хотя бы одно обращение является записью. Результат непредсказуем: значение может потеряться, считаться частично перезаписанным или вызвать undefined behavior по стандарту C/C++. Дедлок — зависание системы, при котором набор потоков ждёт ресурсов, удерживаемых друг другом, образуя циклическую зависимость без выхода.

В этой статье мы разберём оба явления: формальные условия их возникновения, классические примеры, методы обнаружения через статический анализ и динамическую инструментацию, а также стратегии предотвращения — от порядка захвата блокировок до алгоритма банкира.

## 1. Гонки данных: природа и последствия

### 1.1 Определение гонки

В стандартах C11 и C++11 дано формальное определение: **data race** происходит тогда, когда два выражения обращаются к одному объекту, хотя бы одно из них является записью, и они не упорядочены отношением happens-before. Любая программа с data race имеет **undefined behavior** — компилятор вправе генерировать любой код.

На практике это означает, что компилятор может:
- Переставить операции
- Убрать "лишние" чтения (результат всегда одинаков в однопоточном взгляде)
- Считать, что конкретная переменная не изменяется между двумя точками кода

```c
// Классическая гонка: два потока инкрементируют счётчик
int counter = 0; // глобальная переменная

void *worker(void *arg) {
    for (int i = 0; i < 1000000; i++) {
        counter++; // НЕ атомарно! Это read-modify-write
    }
    return NULL;
}
```

На x86 `counter++` транслируется примерно в:
```asm
MOV EAX, [counter]   ; чтение
ADD EAX, 1           ; инкремент
MOV [counter], EAX   ; запись
```

Если два потока выполняют эти три инструкции в переплетении (interleaving), запись одного потока может перезаписать запись другого. Итоговое значение будет меньше ожидаемого 2,000,000 — типично 1,000,000–1,800,000 в зависимости от планировщика.

### 1.2 Torn write и tearing

На 32-битных системах при записи 64-битного значения может произойти **torn write**: одно 32-битное слово записано, другое ещё нет. Другой поток прочитает химерическое значение — старшие биты от нового, младшие от старого.

```c
// Пример torn write на 32-битной платформе
int64_t value = 0;

// Поток 1 пишет 0x0102030405060708
value = 0x0102030405060708LL;

// Поток 2 читает в промежутке
// Может прочитать: 0x0102030400000000 (старшие новые, младшие нули)
// или:             0x0000000005060708 (старшие нули, младшие новые)
```

На x86-64 выровненные 64-битные операции атомарны по архитектурной гарантии, но это не обязательно для других платформ и не обязательно для SIMD-типов.

### 1.3 Видимость изменений и memory ordering

Даже если операция атомарна по записи, другой поток может не увидеть изменение из-за буферов записи процессора и слабой модели памяти:

```c
// Поток 1:
data = 42;     // (1) запись данных
flag = 1;      // (2) сигнал

// Поток 2:
while (!flag); // ждём сигнала
use(data);     // используем данные — но видим ли 42?
```

На x86 (TSO — Total Store Order) это работает из-за гарантии: записи видны другим процессорам в порядке выполнения. На ARM или POWER запись data может прийти к другому ядру после flag — поток 2 увидит flag=1, но data=0. Без барьеров памяти (acquire/release) такой код некорректен на слабоупорядоченных архитектурах.

### 1.4 Gist примеры известных гонок

**Therac-25 (1985–1987)**: программно-аппаратный комплекс лучевой терапии. Гонка между потоком ввода команд и потоком управления дозой привела к тому, что режим защитного ограничения дозы не успевал активироваться. Результат: шесть пациентов получили смертельные дозы радиации. [Leveson, Turner, 1993]

**Heartbleed (CVE-2014-0160)**: не гонка в классическом смысле, но некорректная работа с памятью в OpenSSL при обработке TLS heartbeat позволяла читать память сервера. Пример того, как отсутствие синхронизации + ошибки работы с памятью сочетаются катастрофически.

## 2. Обнаружение гонок

### 2.1 ThreadSanitizer (TSan)

TSan — инструментация компилятора от Google, доступная в GCC и Clang. При запуске программа выполняется с тенями для каждой ячейки памяти, отслеживающими историю обращений и синхронизации.

```bash
# Компиляция с TSan
clang -fsanitize=thread -g -O1 -o prog prog.c -lpthread
# или
gcc -fsanitize=thread -g -O1 -o prog prog.c -lpthread

./prog
```

Пример вывода при гонке:

```
==================
WARNING: ThreadSanitizer: data race (pid=12345)
  Write of size 4 at 0x7f8b2c0b0060 by thread T2:
    #0 worker /home/user/race.c:8 (prog+0x401a2b)
    
  Previous write of size 4 at 0x7f8b2c0b0060 by thread T1:
    #0 worker /home/user/race.c:8 (prog+0x401a2b)
    
  Location is global 'counter' of size 4 at 0x7f8b2c0b0060
  
Thread T2 (tid=12347, running) created by main thread at:
    #0 pthread_create /race.c:20
==================
```

TSan замедляет выполнение в 5–20 раз и увеличивает потребление памяти примерно в 5 раз. Это приемлемо для тестирования, но не для продакшена.

### 2.2 Valgrind Helgrind

Helgrind обнаруживает гонки через анализ синхронизации на основе happen-before:

```bash
valgrind --tool=helgrind --history-level=approx ./prog
```

Helgrind также обнаруживает нарушения порядка захвата блокировок — потенциальные дедлоки, даже если они не произошли в данном запуске.

### 2.3 Статический анализ: Clang Thread Safety Analysis

Clang поддерживает аннотации для статического анализа в compile-time:

```cpp
#include <mutex>
#include <thread>

class __attribute__((lockable)) Mutex {
public:
    void lock() __attribute__((exclusive_lock_function));
    void unlock() __attribute__((unlock_function));
};

class BankAccount {
    Mutex mu;
    int balance __attribute__((guarded_by(mu)));
    
public:
    void deposit(int amount) __attribute__((exclusive_locks_required(mu))) {
        balance += amount; // OK: под блокировкой
    }
    
    int getBalance() {
        return balance; // ОШИБКА КОМПИЛЯТОРА: нет блокировки
    }
};
```

Эта техника используется в Google Chrome и позволяет обнаруживать часть ошибок без запуска программы.

### 2.4 Динамический анализ: Lockset Algorithm

Алгоритм lockset (Eraser) отслеживает для каждой переменной множество блокировок, удерживаемых при каждом обращении. Гонка обнаруживается, если пересечение множеств становится пустым:

```
Переменная x:
  Поток 1, запись: held_locks = {mutex_A}      → lockset(x) = {mutex_A}
  Поток 2, запись: held_locks = {mutex_B}      → lockset(x) ∩ {mutex_B} = {}
  → Гонка! Нет общей блокировки
```

TSan использует более сложный алгоритм на основе векторных часов (Lamport vector clocks), что снижает false positive.

## 3. Дедлок: условия возникновения

### 3.1 Четыре условия Коффмана

В 1971 году Эдвард Коффман с коллегами сформулировал необходимые и достаточные условия дедлока. Дедлок возможен тогда и только тогда, когда выполняются все четыре условия:

1. **Взаимное исключение** (Mutual Exclusion): ресурс может использоваться только одним процессом одновременно
2. **Удержание и ожидание** (Hold and Wait): процесс, удерживающий ресурс, ждёт другого ресурса
3. **Отсутствие вытеснения** (No Preemption): ресурс нельзя принудительно отобрать
4. **Кольцевое ожидание** (Circular Wait): существует цикл в графе ожидания ресурсов

Для предотвращения дедлока достаточно нарушить любое из этих условий.

### 3.2 Классический дедлок: два мьютекса

```c
#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

pthread_mutex_t mutex_A = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t mutex_B = PTHREAD_MUTEX_INITIALIZER;

void *thread1(void *arg) {
    pthread_mutex_lock(&mutex_A);
    printf("Thread1: захватил A\n");
    sleep(1); // даём времени для переключения
    
    pthread_mutex_lock(&mutex_B); // ждёт B, которую держит thread2
    printf("Thread1: захватил B\n"); // никогда не выполнится
    
    pthread_mutex_unlock(&mutex_B);
    pthread_mutex_unlock(&mutex_A);
    return NULL;
}

void *thread2(void *arg) {
    pthread_mutex_lock(&mutex_B);
    printf("Thread2: захватил B\n");
    sleep(1);
    
    pthread_mutex_lock(&mutex_A); // ждёт A, которую держит thread1
    printf("Thread2: захватил A\n"); // никогда не выполнится
    
    pthread_mutex_unlock(&mutex_A);
    pthread_mutex_unlock(&mutex_B);
    return NULL;
}
```

Граф ожидания ресурсов:
```
Thread1 → mutex_B → Thread2 → mutex_A → Thread1  (цикл!)
```

### 3.3 Дедлок с самоблокировкой (самодедлок)

Рекурсивный захват немьютекса с `PTHREAD_MUTEX_NORMAL`:

```c
pthread_mutex_lock(&mutex);
some_function(); // внутри тоже вызывает pthread_mutex_lock(&mutex)
// → дедлок! Один поток ждёт сам себя
```

Это проявляется в библиотеках, вызывающих callback под блокировкой, если пользователь в callback вызывает метод той же библиотеки.

### 3.4 Livelock

Livelock — ситуация, схожая с дедлоком, но потоки не заблокированы: они активно работают, но не двигаются вперёд, реагируя на действия друг друга:

```c
// Два вежливых потока: каждый уступает другому
void *polite_thread(void *arg) {
    while (true) {
        if (pthread_mutex_trylock(&resource) == 0) {
            use_resource();
            pthread_mutex_unlock(&resource);
            break;
        }
        // "Уступаю тебе"
        sched_yield();
        // Оба потока выполняют это одновременно → никто не получает ресурс
    }
}
```

Livelock сложнее дедлока: процессы используют CPU, но не прогрессируют. Диагностируется мониторингом прогресса, а не только наличием ожидания.

### 3.5 Голодание (Starvation)

Голодание — низкоприоритетный поток никогда не получает ресурс, потому что высокоприоритетные постоянно его захватывают. Технически не дедлок (все потоки работают), но функционально не лучше для пострадавшего потока.

## 4. Обнаружение дедлоков

### 4.1 Граф распределения ресурсов

Операционная система может строить **граф распределения ресурсов** (Resource Allocation Graph, RAG) и обнаруживать циклы:

```
Узлы: {P1, P2, P3, R1, R2}

Рёбра:
P1 → R1 (P1 запрашивает R1)
R1 → P2 (R1 держит P2)
P2 → R2 (P2 запрашивает R2)
R2 → P1 (R2 держит P1)

Цикл: P1 → R1 → P2 → R2 → P1 → дедлок!
```

Алгоритм обнаружения цикла — DFS с пометкой состояний (WHITE/GRAY/BLACK). Обнаружение GRAY-узла при возврате — цикл.

### 4.2 Watchdog и timeout

Практический подход для продакшена — таймаут на захват блокировки:

```c
struct timespec ts;
clock_gettime(CLOCK_REALTIME, &ts);
ts.tv_sec += 5; // 5 секунд таймаут

int rc = pthread_mutex_timedlock(&mutex, &ts);
if (rc == ETIMEDOUT) {
    // Вероятный дедлок — логируем стек, аварийно завершаем
    log_deadlock_info();
    abort(); // или graceful shutdown
}
```

### 4.3 Cycle detection в Valgrind Helgrind

Helgrind строит граф порядка захвата блокировок. Если поток A захватывал mutex1 перед mutex2, а поток B — mutex2 перед mutex1, Helgrind предупреждает:

```
==12345== Thread #1: lock order "mutex_A before mutex_B" violated
==12345==    Observed (incorrect) order is:
==12345==    acquisition of lock mutex_B
==12345==      by thread #1 at
==12345==        0x... pthread_mutex_lock (helgrind.c:...)
==12345==        0x... thread2 race.c:25
==12345==    followed by a later acquisition of lock mutex_A
```

Это позволяет обнаружить потенциальный дедлок до его фактического возникновения.

### 4.4 Deadlock detection в базах данных

СУБД активно применяют обнаружение дедлоков. PostgreSQL проверяет граф ожидания раз в `deadlock_timeout` (по умолчанию 1 секунда). При обнаружении цикла один из участников получает ошибку `ERROR: deadlock detected` и откатывает транзакцию.

InnoDB (MySQL) использует алгоритм wait-for graph: при обнаружении цикла транзакция с наименьшим весом (число изменённых строк) откатывается.

## 5. Стратегии предотвращения дедлоков

### 5.1 Упорядочение блокировок (Lock Ordering)

Самый простой и надёжный подход: все потоки захватывают несколько блокировок в одном и том же порядке.

```c
// ПЛОХО: разный порядок в разных функциях
void transfer_A_to_B(Account *a, Account *b, int amount) {
    pthread_mutex_lock(&a->mutex);  // сначала A
    pthread_mutex_lock(&b->mutex);  // потом B
    a->balance -= amount;
    b->balance += amount;
    pthread_mutex_unlock(&b->mutex);
    pthread_mutex_unlock(&a->mutex);
}

void transfer_B_to_A(Account *a, Account *b, int amount) {
    pthread_mutex_lock(&b->mutex);  // сначала B — противоположный порядок!
    pthread_mutex_lock(&a->mutex);
    // ...
}

// ХОРОШО: порядок по адресу (или id) мьютекса
void transfer(Account *from, Account *to, int amount) {
    Account *first  = (from < to) ? from : to;
    Account *second = (from < to) ? to : from;
    
    pthread_mutex_lock(&first->mutex);
    pthread_mutex_lock(&second->mutex);
    
    from->balance -= amount;
    to->balance += amount;
    
    pthread_mutex_unlock(&second->mutex);
    pthread_mutex_unlock(&first->mutex);
}
```

Сравнение адресов как способ установить порядок работает, если мьютексы встроены в объекты. Иначе можно использовать уникальные ID.

### 5.2 Try-lock с откатом

Попытаться захватить вторую блокировку без блокировки; при неудаче освободить первую и попробовать снова:

```c
bool transfer_trylock(Account *from, Account *to, int amount) {
    pthread_mutex_lock(&from->mutex);
    
    if (pthread_mutex_trylock(&to->mutex) != 0) {
        // Не удалось — освобождаем первую и повторяем позже
        pthread_mutex_unlock(&from->mutex);
        sched_yield(); // уступаем CPU
        return false;  // вызывающий повторит попытку
    }
    
    from->balance -= amount;
    to->balance += amount;
    
    pthread_mutex_unlock(&to->mutex);
    pthread_mutex_unlock(&from->mutex);
    return true;
}

// Повторяем до успеха
while (!transfer_trylock(a, b, 100)) {}
```

Минус: может привести к livelock, если оба потока постоянно проигрывают. Решение — случайный backoff:

```c
usleep(rand() % 1000); // случайная задержка 0-1 мс
```

### 5.3 Алгоритм банкира (Banker's Algorithm)

Предложен Дейкстрой в 1965 году. Перед выделением ресурса проверяется, остаётся ли система в "безопасном состоянии" — существует ли порядок завершения всех процессов при текущем распределении.

```python
def is_safe(available, allocation, need):
    """
    available: список доступных ресурсов каждого типа
    allocation[i]: ресурсы, выделенные процессу i
    need[i]: ресурсы, необходимые процессу i
    Возвращает True если система в безопасном состоянии
    """
    n = len(allocation)    # число процессов
    m = len(available)     # число типов ресурсов
    work = available[:]
    finish = [False] * n
    
    while True:
        found = False
        for i in range(n):
            if not finish[i] and all(need[i][j] <= work[j] for j in range(m)):
                # Процесс i может завершиться
                work = [work[j] + allocation[i][j] for j in range(m)]
                finish[i] = True
                found = True
        if not found:
            break
    
    return all(finish)  # безопасно если все завершатся

# Пример: 5 процессов, 3 типа ресурсов (A, B, C)
available   = [3, 3, 2]
allocation  = [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]]
need        = [[7,4,3],[1,2,2],[6,0,0],[0,1,1],[4,3,2]]

print(is_safe(available, allocation, need))  # True — безопасно
```

Алгоритм банкира применяется в СУБД и планировщиках реального времени. В общем случае он полиномиальный (O(n²m)), что приемлемо при небольшом числе ресурсов.

### 5.4 Применение одного мьютекса

Если возможно, использовать один мьютекс для всех операций с разделяемым состоянием. Это исключает кольцевое ожидание:

```c
// Один глобальный мьютекс для всех счетов
pthread_mutex_t global_account_lock = PTHREAD_MUTEX_INITIALIZER;

void transfer(Account *from, Account *to, int amount) {
    pthread_mutex_lock(&global_account_lock);
    from->balance -= amount;
    to->balance += amount;
    pthread_mutex_unlock(&global_account_lock);
}
```

Минус: снижение параллелизма. Это компромисс: простота vs производительность.

### 5.5 Иерархическое лишение возможности ожидания (Wait-free / Lock-free)

Полностью избежать дедлоков можно, отказавшись от блокирующих операций — через lock-free алгоритмы. Дедлок невозможен, если нет блокировок.

```c
// Lock-free transfer через CAS — нет дедлока по определению
// Но сложность возрастает, появляется ABA-проблема
bool lf_transfer(atomic_int *from, atomic_int *to, int amount) {
    int old_from;
    do {
        old_from = atomic_load(from);
        if (old_from < amount) return false; // недостаточно средств
    } while (!atomic_compare_exchange_weak(from, &old_from, old_from - amount));
    
    atomic_fetch_add(to, amount);
    return true;
}
// Проблема: между двумя CAS возможны некорректные промежуточные состояния
```

## 6. Паттерны корректного параллельного программирования

### 6.1 RAII для блокировок

В C++ автоматическое освобождение блокировки при выходе из scope:

```cpp
#include <mutex>

class BankAccount {
    mutable std::mutex mu_;
    int balance_;
    
public:
    BankAccount(int initial) : balance_(initial) {}
    
    bool transfer_to(BankAccount &other, int amount) {
        // Порядок захвата по адресу — предотвращает дедлок
        std::scoped_lock lock(mu_, other.mu_); // C++17: атомарно захватывает оба
        if (balance_ < amount) return false;
        balance_ -= amount;
        other.balance_ += amount;
        return true;
        // lock автоматически освобождается при выходе
    }
    
    int balance() const {
        std::lock_guard<std::mutex> lock(mu_);
        return balance_;
    }
};
```

`std::scoped_lock` в C++17 захватывает несколько мьютексов атомарно с использованием алгоритма, предотвращающего дедлок (аналог try-lock с откатом).

### 6.2 Immutable Data (неизменяемые данные)

Данные, не изменяющиеся после создания, не требуют синхронизации при чтении:

```python
from typing import NamedTuple

class Config(NamedTuple):
    host: str
    port: int
    timeout: float

# Создаём один раз, передаём в потоки без блокировок
config = Config(host='localhost', port=8080, timeout=5.0)

import threading
def worker(cfg):
    # Безопасно читать cfg из множества потоков
    connect(cfg.host, cfg.port)

threads = [threading.Thread(target=worker, args=(config,)) for _ in range(10)]
```

### 6.3 Thread-local storage

Хранение данных, специфичных для потока, в thread-local переменных — нет разделения, нет гонок:

```c
#include <pthread.h>

// thread-local буфер для каждого потока — нет синхронизации
__thread char tl_buffer[4096];
__thread int  tl_errno;

// POSIX вариант
pthread_key_t tl_key;

void destructor(void *data) { free(data); }

void init_tls(void) {
    pthread_key_create(&tl_key, destructor);
}

void *get_thread_data(void) {
    void *data = pthread_getspecific(tl_key);
    if (data == NULL) {
        data = malloc(sizeof(MyData));
        pthread_setspecific(tl_key, data);
    }
    return data;
}
```

В C11: `_Thread_local`. В C++11: `thread_local`. Примеры: `errno` в libc, per-thread аллокатор в jemalloc.

### 6.4 Message Passing вместо Shared State

Потоки обмениваются сообщениями через каналы — нет разделяемого состояния, нет гонок. Философия Go: "Don't communicate by sharing memory; share memory by communicating."

```go
package main

import (
    "fmt"
    "sync"
)

func counter(requests <-chan struct{}, responses chan<- int, wg *sync.WaitGroup) {
    defer wg.Done()
    count := 0
    for range requests {
        count++
        responses <- count
    }
}

func main() {
    requests := make(chan struct{}, 100)
    responses := make(chan int, 100)
    var wg sync.WaitGroup
    
    wg.Add(1)
    go counter(requests, responses, &wg)
    
    // Отправляем запросы
    for i := 0; i < 10; i++ {
        requests <- struct{}{}
        fmt.Println(<-responses)
    }
    close(requests)
    wg.Wait()
}
```

### 6.5 Software Transactional Memory (STM)

STM — альтернативная модель синхронизации, заимствованная из баз данных. Потоки выполняют транзакции; при конфликте транзакция автоматически откатывается и повторяется. Нет явных блокировок, нет дедлоков:

```haskell
-- Haskell с библиотекой STM
import Control.Concurrent.STM

transfer :: TVar Int -> TVar Int -> Int -> STM ()
transfer from to amount = do
    fromBal <- readTVar from
    if fromBal < amount
        then error "Insufficient funds"
        else do
            writeTVar from (fromBal - amount)
            modifyTVar to (+amount)

main :: IO ()
main = do
    acc1 <- newTVarIO 1000
    acc2 <- newTVarIO 500
    atomically $ transfer acc1 acc2 200
    -- Нет дедлоков! При конфликте транзакция повторяется
```

STM есть в GHC Haskell, Clojure (`ref`, `dosync`), и как эксперимент в C++ (GCC transactional memory). Основная проблема — производительность при высоком конфликте.

## 7. Специфика гонок в конкретных языках

### 7.1 Java Memory Model

Java имеет чётко определённую модель памяти (JMM) с отношением happens-before. Volatile гарантирует видимость, synchronized — атомарность и видимость:

```java
// НЕПРАВИЛЬНО: double-checked locking без volatile (до Java 5)
class Singleton {
    private static Singleton instance = null;
    
    public static Singleton getInstance() {
        if (instance == null) {              // гонка!
            synchronized (Singleton.class) {
                if (instance == null) {
                    instance = new Singleton(); // частично инициализированный объект
                }
            }
        }
        return instance;
    }
}

// ПРАВИЛЬНО: volatile обеспечивает happens-before для записи
class Singleton {
    private static volatile Singleton instance = null;
    
    public static Singleton getInstance() {
        if (instance == null) {
            synchronized (Singleton.class) {
                if (instance == null) {
                    instance = new Singleton();
                }
            }
        }
        return instance;
    }
}

// ЕЩЁ ЛУЧШЕ: initialization-on-demand holder
class Singleton {
    private static class Holder {
        static final Singleton INSTANCE = new Singleton();
    }
    
    public static Singleton getInstance() {
        return Holder.INSTANCE; // ClassLoader гарантирует безопасность
    }
}
```

### 7.2 Python GIL и "иллюзия безопасности"

Python CPython имеет GIL (Global Interpreter Lock) — единую блокировку интерпретатора. Это защищает от гонок при работе с объектами CPython, но не защищает от логических гонок:

```python
import threading

shared_list = []

def worker(n):
    # list.append атомарен в CPython (GIL), но:
    for i in range(n):
        val = len(shared_list)      # (1) читаем длину
        shared_list.append(val)    # (2) добавляем — GIL может освободиться между 1 и 2

threads = [threading.Thread(target=worker, args=(100,)) for _ in range(10)]
# Результат может быть некорректен: дублирующиеся значения

# Также: GIL не защищает при работе с файлами, сокетами, расширениями C
import ctypes
counter = ctypes.c_int(0)
def increment():
    for _ in range(100000):
        counter.value += 1  # ГОНКА! ctypes обходит GIL
```

### 7.3 Rust: гарантии компилятора

Rust предотвращает гонки данных на уровне системы типов — в корректной программе (без `unsafe`) гонки невозможны по построению:

```rust
use std::sync::{Arc, Mutex};
use std::thread;

fn main() {
    let counter = Arc::new(Mutex::new(0));
    
    let handles: Vec<_> = (0..10).map(|_| {
        let counter = Arc::clone(&counter);
        thread::spawn(move || {
            let mut num = counter.lock().unwrap();
            *num += 1;
            // MutexGuard освобождается автоматически (RAII)
        })
    }).collect();
    
    for handle in handles {
        handle.join().unwrap();
    }
    
    println!("Result: {}", *counter.lock().unwrap()); // всегда 10
}

// Компилятор не позволит поделиться &mut без синхронизации:
// error[E0502]: cannot borrow `data` as mutable because it is also borrowed as immutable
```

## 8. Диагностика в продакшене

### 8.1 Core dump при дедлоке

При подозрении на дедлок — снимаем core dump без убийства процесса:

```bash
# Получить core dump работающего процесса
gcore PID

# Или с помощью gdb
gdb -p PID -batch -ex "thread apply all bt" -ex quit > threads.txt

# Анализ: ищем потоки, ждущие futex
grep -A 5 "futex_wait\|pthread_mutex_lock" threads.txt
```

### 8.2 /proc/PID/stack и sysrq

В Linux можно посмотреть стек ядра потока через `/proc`:

```bash
cat /proc/PID/task/TID/stack
# [<ffffffff>] futex_wait_queue+0x... [kernel]
# [<ffffffff>] do_futex+0x...
# [<ffffffff>] __x64_sys_futex+0x...
```

### 8.3 Mago-Deadlock detector

Промышленный подход: каждый поток периодически обновляет "heartbeat" в разделяемой структуре. Watchdog-поток проверяет heartbeats. Если поток не обновлял heartbeat N секунд — возможен дедлок. Такой подход применяется в PostgreSQL (`pg_stat_activity`), JVM и других средах выполнения.

## Заключение

Гонки данных и дедлоки — принципиально разные, но одинаково опасные классы ошибок параллельного программирования. Гонки возникают из-за недостаточной синхронизации и могут приводить к тихому повреждению данных. Дедлоки — из-за чрезмерной или неправильной синхронизации и останавливают систему явно.

Предотвращение гонок требует дисциплины: атомарные операции для счётчиков, мьютексы для составных операций, acquire/release для межпоточных сигналов. Помощники — ThreadSanitizer и Helgrind — обнаруживают ошибки, которые не воспроизводятся вручную. Предотвращение дедлоков — строгий порядок захвата блокировок, минимизация числа одновременно удерживаемых ресурсов, и в идеале — уменьшение разделяемого изменяемого состояния через иммутабельность, thread-local storage или передачу сообщений.

Самое надёжное решение — писать меньше разделяемого изменяемого состояния. Каждая единица данных, доступная только одному потоку или только для чтения, не может участвовать в гонке или дедлоке. Когда же без разделения не обойтись — измерения, аннотации и инструменты статического анализа превращают вероятностные ошибки в детерминированные предупреждения компилятора.

## Литература и ссылки

1. Coffman, E. G., Elphick, M., Shoshani, A. *System Deadlocks*. ACM Computing Surveys, 1971. [https://dl.acm.org/doi/10.1145/356586.356588](https://dl.acm.org/doi/10.1145/356586.356588)
2. Dijkstra, E. W. *The Banker's Algorithm*. EWD-623, 1979. [https://www.cs.utexas.edu/users/EWD/ewd06xx/EWD623.PDF](https://www.cs.utexas.edu/users/EWD/ewd06xx/EWD623.PDF)
3. Leveson, N. G., Turner, C. S. *An Investigation of the Therac-25 Accidents*. IEEE Computer, 1993. [https://ieeexplore.ieee.org/document/274940](https://ieeexplore.ieee.org/document/274940)
4. Savage, S. et al. *Eraser: A Dynamic Data Race Detector for Multi-Threaded Programs*. ACM TOCS, 1997. [https://dl.acm.org/doi/10.1145/265924.265927](https://dl.acm.org/doi/10.1145/265924.265927)
5. Serebry, K. *ThreadSanitizer — data race detection in practice*. Google, 2009. [https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/35604.pdf](https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/35604.pdf)
6. Boehm, H-J. *Threads Cannot Be Implemented as a Library*. PLDI 2005. [https://dl.acm.org/doi/10.1145/1065010.1065042](https://dl.acm.org/doi/10.1145/1065010.1065042)
7. Oracle Java Documentation: Java Memory Model. [https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
8. Wikipedia: Deadlock. [https://en.wikipedia.org/wiki/Deadlock](https://en.wikipedia.org/wiki/Deadlock)
9. Wikipedia: Race condition. [https://en.wikipedia.org/wiki/Race_condition](https://en.wikipedia.org/wiki/Race_condition)
10. Rust Reference: Send and Sync. [https://doc.rust-lang.org/reference/special-types-and-traits.html](https://doc.rust-lang.org/reference/special-types-and-traits.html)
