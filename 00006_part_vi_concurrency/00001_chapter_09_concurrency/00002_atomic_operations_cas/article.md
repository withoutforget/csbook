# Атомарные операции и CAS (Compare-And-Swap)

## Введение

В мире многопоточного программирования самая дорогая операция — это синхронизация. Мьютексы надёжны, но требуют системных вызовов, переключений контекста и могут привести к convoy problem (поток занял мьютекс, другие потоки ждут в очереди, давая CPU простаивать). Альтернатива — lock-free алгоритмы, построенные на атомарных операциях процессора.

Атомарная операция — это операция, которая выполняется как единое неделимое действие с точки зрения других процессоров. Никакой другой поток не может наблюдать промежуточное состояние. Процессоры предоставляют специальные инструкции для атомарных операций: LOCK XADD, CMPXCHG (x86), LDREX/STREX (ARM). Именно на этих инструкциях строятся мьютексы, спинлоки и все высокоуровневые примитивы синхронизации.

В этой главе мы разберём проблему неатомарного инкремента, изучим CAS (Compare-And-Swap) как фундаментальный строительный блок lock-free структур, рассмотрим ABA проблему и memory ordering — тонкие вопросы, без понимания которых lock-free код будет работать неправильно.

---

## 1. Проблема неатомарного инкремента

Рассмотрим простейшую операцию: `counter++`. Это выглядит как одно действие, но на уровне машинных инструкций это три отдельных шага:

```
1. LOAD:   регистр = *counter    // читаем из памяти
2. ADD:    регистр = регистр + 1 // прибавляем
3. STORE:  *counter = регистр   // записываем в память
```

Если два потока выполняют эти три шага, возможна интерливинг-ситуация:

```
Время  Поток 1                Поток 2           Значение counter
  0    LOAD: регистр1 = 0                       0
  1                           LOAD: регистр2=0  0
  2    ADD: регистр1 = 1                        0
  3                           ADD: регистр2=1   0
  4    STORE: counter = 1                       1
  5                           STORE: counter=1  1  ← ПОТЕРЯНО одно увеличение!
```

Итог: оба потока выполнили инкремент, но счётчик увеличился только на 1, а не на 2.

```c
#include <pthread.h>
#include <stdio.h>

long counter = 0;

void* increment(void* arg) {
    for (int i = 0; i < 1000000; i++) {
        counter++;  // Гонка данных! Не атомарно!
    }
    return NULL;
}

int main() {
    pthread_t t1, t2;
    pthread_create(&t1, NULL, increment, NULL);
    pthread_create(&t2, NULL, increment, NULL);
    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    
    printf("Expected: 2000000\n");
    printf("Got:      %ld\n", counter);  // Меньше 2000000!
    return 0;
}
```

На реальной машине результат будет случайным числом, меньшим 2 000 000 — из-за гонки данных.

---

## 2. Атомарные инструкции CPU

### 2.1 LOCK-префикс на x86

Архитектура x86 предоставляет префикс `LOCK`, который гарантирует, что следующая инструкция выполнится атомарно — с монопольным доступом к шине памяти:

```nasm
; Атомарный инкремент
LOCK INC [counter]      ; атомарно increment памяти

; Атомарное сложение с возвратом старого значения
LOCK XADD [counter], eax  ; eax = counter; counter += eax
```

Инструкция `LOCK XADD` (eXchange and ADD) атомарно считывает значение, прибавляет к нему регистр, и возвращает старое значение. Это основа для реализации атомарного инкремента.

### 2.2 CMPXCHG — Compare and Exchange

`CMPXCHG` (Compare and eXCHanGe) — ключевая инструкция для CAS:

```nasm
; Семантика:
; if ([mem] == eax) { [mem] = ecx; ZF = 1; }
; else { eax = [mem]; ZF = 0; }

LOCK CMPXCHG [mem], ecx
```

Это атомарная операция: сравнить значение в памяти с ожидаемым, и только если они совпадают — записать новое значение. Если нет — вернуть текущее значение памяти.

### 2.3 LL/SC на ARM (Load-Link / Store-Conditional)

ARM использует другой подход — пару инструкций LL/SC (Load-Link / Store-Conditional):

```asm
; ARMv8 (AArch64)
loop:
    LDAXR   x1, [x0]       ; Load-Acquire Exclusive Register
    ADD     x1, x1, #1     ; x1 = x1 + 1
    STLXR   w2, x1, [x0]   ; Store-Release Exclusive — устанавливает флаг если успешно
    CBNZ    w2, loop        ; Если не удалось — повторить
```

LDAXR помечает адрес памяти как «monitored». STLXR записывает только если с момента LDAXR никто другой не записал в этот адрес. Если кто-то записал — STLXR возвращает ненулевой флаг и операция повторяется.

---

## 3. CAS (Compare-And-Swap)

CAS — это атомарная операция с тремя параметрами:
- `address` — адрес памяти
- `expected` — ожидаемое текущее значение
- `new` — новое значение для записи

```
CAS(address, expected, new):
    atomic:
        current = *address
        if current == expected:
            *address = new
            return true
        return false
```

CAS — строительный блок для lock-free алгоритмов. Паттерн использования:

```c
// Псевдокод lock-free инкремента через CAS
void atomic_increment(atomic_int* counter) {
    int expected;
    int new_value;
    do {
        expected = *counter;           // Читаем текущее значение
        new_value = expected + 1;      // Вычисляем новое
    } while (!CAS(counter, expected, new_value));
    // CAS вернёт false если кто-то успел изменить counter
    // В таком случае повторяем с новым значением
}
```

### 3.1 Реализация CAS в C++ std::atomic

```cpp
#include <atomic>
#include <thread>
#include <vector>
#include <iostream>

std::atomic<long> counter{0};

void increment_atomic(int n) {
    for (int i = 0; i < n; i++) {
        counter.fetch_add(1, std::memory_order_relaxed);
    }
}

// Явный CAS — lock-free максимум
void push_max(std::atomic<int>& max_val, int new_val) {
    int current = max_val.load(std::memory_order_relaxed);
    while (new_val > current) {
        // CAS: если max_val == current, заменить на new_val
        if (max_val.compare_exchange_weak(
            current,    // expected — обновляется если CAS не удался
            new_val,    // desired
            std::memory_order_release,
            std::memory_order_relaxed)) {
            break;  // Успешно обновили
        }
        // current автоматически обновлён на актуальное значение
        // Повторяем цикл
    }
}

int main() {
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; i++) {
        threads.emplace_back(increment_atomic, 1000000);
    }
    for (auto& t : threads) t.join();
    
    std::cout << "Counter: " << counter.load() << std::endl;  // 4000000
    return 0;
}
```

### 3.2 compare_exchange_weak vs compare_exchange_strong

В C++ `std::atomic` предоставляет два варианта:

- `compare_exchange_strong` — гарантирует атомарность, может использовать тяжёлые lock
- `compare_exchange_weak` — может ложно возвращать false (spurious failure), но быстрее

На платформах с LL/SC (ARM) `compare_exchange_weak` более эффективна и позволяет реализовать LL/SC напрямую. В цикле используем `weak`:

```cpp
// Правильный паттерн с weak (в цикле)
int expected = current.load();
while (!current.compare_exchange_weak(expected, expected + 1)) {
    // expected автоматически обновлён
}

// strong — для одиночной попытки
int expected_val = 0;
bool success = flag.compare_exchange_strong(expected_val, 1);
```

---

## 4. ABA Problem

ABA — коварная проблема в lock-free алгоритмах при использовании CAS.

**Сценарий**:
1. Поток 1 читает значение `A`
2. Поток 1 приостанавливается
3. Поток 2 меняет значение `A → B → A` (значение снова стало A)
4. Поток 1 возобновляется, CAS видит `A` и считает, что ничего не изменилось
5. CAS успешен — но состояние системы изменилось!

**Классический пример** — lock-free стек:

```
Начальное состояние стека: A → B → C

Поток 1: хочет сделать pop A, читает head = A
Поток 1 приостанавливается

Поток 2: pop A (успешно)
Поток 2: pop B (успешно)  
Поток 2: push A (A снова наверху!)
Стек теперь: A → C

Поток 1 возобновляется:
Поток 1: CAS(head, A, B)  — A совпадает!
Стек теперь: B → ??? (B освобождён!)
```

Поток 1 ставит голову стека на `B`, но `B` уже был освобождён. Use-after-free!

### 4.1 Решение: Version Counter (Tagged Pointer)

Добавляем к указателю «версию», которая инкрементируется при каждом изменении. ABA становится невозможным:

```cpp
#include <atomic>
#include <cstdint>

// Упаковываем указатель и версию в одно 128-битное значение
struct TaggedPtr {
    uintptr_t ptr;
    uint64_t tag;  // Версия
};

template<typename T>
class LockFreeStack {
    std::atomic<TaggedPtr> head{TaggedPtr{0, 0}};
    
public:
    void push(T* node) {
        TaggedPtr old_head = head.load(std::memory_order_relaxed);
        TaggedPtr new_head;
        do {
            node->next = reinterpret_cast<T*>(old_head.ptr);
            new_head = TaggedPtr{reinterpret_cast<uintptr_t>(node), 
                                  old_head.tag + 1};  // Увеличиваем тег!
        } while (!head.compare_exchange_weak(old_head, new_head,
                                              std::memory_order_release,
                                              std::memory_order_relaxed));
    }
};
```

На x86-64 существует инструкция `CMPXCHG16B` — 16-байтовый CAS, позволяющий атомарно обновить пару (pointer, counter).

### 4.2 Hazard Pointers

Альтернатива tagged pointers — hazard pointers (опасные указатели). Поток «публикует» указатели, которые он сейчас использует. Другие потоки не освобождают память, если видят свой указатель в «опасном» списке.

```python
# Упрощённая иллюстрация hazard pointers (Python)
import threading

hazard_pointers = {}  # thread_id -> set of "dangerous" pointers

def read_node(ptr):
    tid = threading.get_ident()
    hazard_pointers[tid] = {ptr}  # Объявляем ptr "опасным"
    # ... работаем с ptr ...
    hazard_pointers[tid] = set()   # Снимаем защиту

def safe_free(ptr):
    # Проверяем, что никто сейчас не использует ptr
    for dangerous_set in hazard_pointers.values():
        if ptr in dangerous_set:
            return False  # Откладываем освобождение
    # Безопасно освобождать
    del ptr
    return True
```

---

## 5. Memory Ordering

Современные CPU и компиляторы переставляют инструкции для оптимизации. Для корректности lock-free кода нужно явно указывать порядок операций с памятью.

### 5.1 Модели упорядочивания (C++11)

```cpp
enum memory_order {
    memory_order_relaxed,  // Никаких гарантий порядка
    memory_order_consume,  // (устаревший, не используйте)
    memory_order_acquire,  // Видим все записи до release
    memory_order_release,  // Публикуем все записи перед release
    memory_order_acq_rel,  // Acquire + Release
    memory_order_seq_cst   // Полный порядок (по умолчанию)
};
```

**memory_order_relaxed**: только атомарность операции, без гарантий порядка. Самый быстрый. Применяется для независимых счётчиков:

```cpp
std::atomic<int> stats_counter{0};

void record_event() {
    // Нам не важен порядок — просто считаем
    stats_counter.fetch_add(1, std::memory_order_relaxed);
}
```

**acquire/release**: паттерн для передачи данных между потоками:

```cpp
#include <atomic>
#include <thread>
#include <cassert>

std::atomic<bool> ready{false};
int data = 0;

void producer() {
    data = 42;          // (1) запись данных
    // release: все записи до этой точки видны тем, кто сделал acquire на ready
    ready.store(true, std::memory_order_release);  // (2)
}

void consumer() {
    // acquire: видим все записи, которые произошли до release
    while (!ready.load(std::memory_order_acquire)) {}  // (3)
    assert(data == 42);  // (4) Гарантированно видим data=42
    // Без acquire/release: assert мог бы упасть!
}
```

**seq_cst (sequentially consistent)**: полная последовательная согласованность — все потоки видят операции в одном глобальном порядке. Самый медленный, но самый простой в понимании:

```cpp
// Проблема без seq_cst (Dekker-подобный сценарий)
std::atomic<bool> x{false}, y{false};
std::atomic<int> z{0};

void thread1() {
    x.store(true, std::memory_order_seq_cst);
    if (!y.load(std::memory_order_seq_cst)) z++;
}

void thread2() {
    y.store(true, std::memory_order_seq_cst);
    if (!x.load(std::memory_order_seq_cst)) z++;
}
// С seq_cst: z всегда будет 1 или 2, никогда 0
// Без seq_cst: возможен z == 0 (оба потока видят старые значения)
```

### 5.2 Таблица memory ordering

| Order | Предотвращает reorder | Производительность | Использование |
|-------|----------------------|-------------------|---------------|
| relaxed | Нет | Максимальная | Статистика, не связанные счётчики |
| acquire | Loads не уходят вверх | Хорошая | Чтение после проверки флага |
| release | Stores не уходят вниз | Хорошая | Запись перед установкой флага |
| acq_rel | acquire + release | Средняя | CAS в структурах данных |
| seq_cst | Полный барьер | Низкая | Простота и безопасность |

---

## 6. Реализация SpinLock через CAS

Спинлок — простейшее использование CAS. В отличие от мьютекса, не выполняет системный вызов — просто вращается в цикле:

```cpp
#include <atomic>

class SpinLock {
    std::atomic<bool> locked{false};
    
public:
    void lock() {
        bool expected = false;
        // Крутимся пока не захватим блокировку
        while (!locked.compare_exchange_weak(
            expected,
            true,
            std::memory_order_acquire,   // acquire при захвате
            std::memory_order_relaxed))  // relaxed если не удалось
        {
            expected = false;  // Сбрасываем expected для следующей попытки
            
            // Hint процессору что мы в spin-wait
            // На x86 снижает энергопотребление и помогает HT-потокам
            __builtin_ia32_pause();
        }
    }
    
    void unlock() {
        locked.store(false, std::memory_order_release);  // release при освобождении
    }
};

// RAII-обёртка
class SpinLockGuard {
    SpinLock& lock_;
public:
    explicit SpinLockGuard(SpinLock& lock) : lock_(lock) { lock_.lock(); }
    ~SpinLockGuard() { lock_.unlock(); }
};
```

**Когда использовать SpinLock**:
- Критическая секция очень короткая (< 100 нс)
- Блокировка не занята долго
- Нет смысла в syscall overhead мьютекса
- Используется в ядре ОС, планировщиках, высокочастотном трейдинге

---

## 7. Lock-free стек

Классический пример lock-free структуры данных:

```cpp
#include <atomic>
#include <memory>

template<typename T>
class LockFreeStack {
    struct Node {
        T data;
        Node* next;
        explicit Node(T data) : data(std::move(data)), next(nullptr) {}
    };
    
    std::atomic<Node*> head{nullptr};
    
public:
    void push(T data) {
        Node* new_node = new Node(std::move(data));
        // Пытаемся стать новой головой
        new_node->next = head.load(std::memory_order_relaxed);
        while (!head.compare_exchange_weak(
            new_node->next,  // expected — обновляется при неудаче
            new_node,        // desired
            std::memory_order_release,
            std::memory_order_relaxed)) {
            // new_node->next обновлён на актуальный head — повторяем
        }
    }
    
    bool pop(T& result) {
        Node* old_head = head.load(std::memory_order_relaxed);
        while (old_head) {
            if (head.compare_exchange_weak(
                old_head,
                old_head->next,
                std::memory_order_acquire,
                std::memory_order_relaxed)) {
                result = std::move(old_head->data);
                // ВНИМАНИЕ: не освобождаем сразу из-за ABA!
                // В реальном коде нужны hazard pointers или epoch-based reclamation
                delete old_head;
                return true;
            }
        }
        return false;  // Стек пуст
    }
};
```

**Важно**: в реальном коде немедленное `delete old_head` опасно из-за ABA проблемы. Нужен epoch-based reclamation (EBR) или hazard pointers.

### 7.1 Go: sync/atomic

```go
package main

import (
    "fmt"
    "sync/atomic"
)

func main() {
    var counter int64
    
    // Атомарный инкремент
    atomic.AddInt64(&counter, 1)
    
    // CAS
    old := atomic.LoadInt64(&counter)
    success := atomic.CompareAndSwapInt64(&counter, old, old*2)
    fmt.Printf("CAS success: %v, counter: %d\n", success, counter)
    
    // Загрузка/сохранение
    atomic.StoreInt64(&counter, 100)
    val := atomic.LoadInt64(&counter)
    fmt.Printf("Value: %d\n", val)
}
```

### 7.2 Python: threading и atomics

В Python атомарных операций нет в стандартной библиотеке — GIL обеспечивает некоторую атомарность, но не гарантирует её. Для истинных атомарных операций нужны C-расширения:

```python
import ctypes
import threading

# GIL делает некоторые операции де-факто атомарными в CPython
# Но это ДЕТАЛИ РЕАЛИЗАЦИИ, не гарантия языка

counter = 0
lock = threading.Lock()

# Правильно: используем явную синхронизацию
def safe_increment():
    global counter
    with lock:
        counter += 1

# Для Python 3.12+ есть experimental атомарные операции через atomics
# или используем multiprocessing.Value с lock=True (по умолчанию)
from multiprocessing import Value

shared = Value('i', 0)  # 'i' = signed int, lock=True по умолчанию

def process_increment(shared_val):
    with shared_val.get_lock():  # Явная блокировка
        shared_val.value += 1
```

---

## 8. Практические рекомендации

### 8.1 Когда применять атомарные операции

1. **Статистика и счётчики**: `fetch_add` с `relaxed` ordering — идеально.
2. **Флаги и одноразовая инициализация**: `std::once_flag`, `atomic<bool>` с acquire/release.
3. **Lock-free очереди**: в высоконагруженных системах (ядра ОС, HFT).

### 8.2 Когда НЕ применять

1. **Сложная бизнес-логика**: lock-free код сложно читать и тестировать. Используйте мьютексы.
2. **Длинные критические секции**: спинлок = трата CPU, лучше мьютекс с ожиданием.
3. **Многоступенчатые операции**: CAS решает проблему одного значения — для нескольких значений нужны транзакции или алгоритмы на основе MVCC.

### 8.3 Инструменты диагностики

```bash
# ThreadSanitizer — обнаружение гонок данных
gcc -fsanitize=thread -g -o program program.c
./program

# Valgrind Helgrind
valgrind --tool=helgrind ./program

# AddressSanitizer для памяти
gcc -fsanitize=address -g -o program program.c
```

---

## Заключение

Атомарные операции и CAS — фундамент всей синхронизации в современных системах. Мьютексы, RWLock, семафоры — всё это реализовано через атомарные инструкции на нижнем уровне.

**Ключевые выводы**:

1. `counter++` — не атомарна. Всегда используйте `std::atomic` или явные блокировки для shared state.

2. CAS — основа lock-free алгоритмов: читай → вычисляй → пробуй записать → повтори.

3. ABA проблема реальна. Решение: tagged pointers или hazard pointers.

4. Memory ordering критичен. Используйте acquire/release для передачи данных между потоками, seq_cst когда не уверены.

5. SpinLock хорош для очень коротких критических секций (<100 нс). Для остального — мьютекс.

6. Lock-free != без блокировок в коде. Lock-free означает, что система в целом всегда делает прогресс, даже если отдельные потоки задержались.

---

## Литература и источники

1. Herlihy, M., & Shavit, N. (2012). *The Art of Multiprocessor Programming*. Morgan Kaufmann. https://www.elsevier.com/books/the-art-of-multiprocessor-programming/herlihy/978-0-12-397337-5
2. C++ Reference. std::atomic. https://en.cppreference.com/w/cpp/atomic/atomic
3. Intel® 64 and IA-32 Architectures Software Developer's Manual. Vol. 2A: Instruction Set Reference. https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html
4. McKenney, P. E. (2007). *Memory Barriers: a Hardware View for Software Hackers*. https://www.rdrop.com/users/paulmck/scalability/paper/whymb.2010.07.23a.pdf
5. Michael, M. M. (2004). Hazard Pointers: Safe Memory Reclamation for Lock-Free Objects. *IEEE Transactions on Parallel and Distributed Systems*.
6. Wikipedia. Compare-and-swap. https://en.wikipedia.org/wiki/Compare-and-swap
7. Wikipedia. ABA problem. https://en.wikipedia.org/wiki/ABA_problem
8. Preshing, J. (2012). An Introduction to Lock-Free Programming. https://preshing.com/20120612/an-introduction-to-lock-free-programming/
9. Go Documentation. sync/atomic. https://pkg.go.dev/sync/atomic
10. Williams, A. (2019). *C++ Concurrency in Action*, 2nd Edition. Manning Publications.
