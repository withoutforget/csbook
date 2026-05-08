# Concurrency vs Parallelism

## Введение

Два термина — «конкурентность» (concurrency) и «параллелизм» (parallelism) — часто используют как синонимы, и это приводит к фундаментальным ошибкам при проектировании систем. Роб Пайк, один из создателей языка Go, в своём знаменитом докладе 2012 года сформулировал ключевое различие: «Concurrency is not parallelism». Конкурентность — это свойство программы, способность структурировать задачу как набор независимо выполняющихся частей. Параллелизм — это свойство исполнения, физическое одновременное выполнение нескольких вычислений на нескольких процессорных ядрах.

Понимание этого различия критично для каждого инженера. Конкурентная программа может выполняться на одном ядре — просто переключаясь между задачами. Параллельная программа требует нескольких ядер. При этом хорошо структурированная конкурентная программа легко масштабируется до параллельного исполнения, тогда как добавление параллелизма к плохо спроектированной программе лишь умножает проблемы синхронизации.

В этой главе мы разберём все основные модели конкурентности — от потоков до корутин и акторов, изучим, как закон Амдала ограничивает ускорение от параллелизма, и посмотрим на конкретные примеры систем, где конкурентность и параллелизм применяются по-разному.

---

## 1. Что такое конкурентность

Конкурентность (concurrency) — это способность программы управлять несколькими задачами, которые могут выполняться в перекрывающиеся промежутки времени. Ключевое слово — «управлять», а не «выполнять одновременно».

Рассмотрим классический пример: повар на кухне. Он ставит суп вариться, пока суп варится — нарезает овощи, пока овощи тушатся — готовит соус. Повар — один, но задачи выполняются конкурентно: он переключается между ними, используя промежутки ожидания. Это конкурентность без параллелизма.

### 1.1 Конкурентность как структура программы

С точки зрения программирования, конкурентность — это декомпозиция программы на независимые «логические потоки выполнения», каждый из которых прогрессирует независимо. Эти потоки могут быть:

- Потоками ОС (threads)
- Корутинами (coroutines, goroutines)
- Акторами (actors)
- Обработчиками событий в event loop

Пример конкурентного веб-сервера на Python (однопоточный, но конкурентный):

```python
import asyncio
import aiohttp

async def fetch_url(session, url):
    """Конкурентная задача — ожидает I/O без блокировки потока."""
    async with session.get(url) as response:
        return await response.text()

async def main():
    urls = [
        "https://example.com",
        "https://python.org", 
        "https://github.com",
    ]
    
    async with aiohttp.ClientSession() as session:
        # Все три запроса выполняются конкурентно на ОДНОМ потоке
        tasks = [fetch_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
    
    for url, result in zip(urls, results):
        print(f"{url}: {len(result)} bytes")

asyncio.run(main())
```

Этот код конкурентен, но не параллелен. Пока один запрос ждёт ответа от сети, event loop переключается на следующий.

### 1.2 Зачем нужна конкурентность

Конкурентность решает две проблемы:

**I/O-bound задачи**: программа проводит большую часть времени в ожидании — сети, диска, базы данных. CPU при этом простаивает. Конкурентность позволяет CPU обрабатывать другие задачи во время ожидания.

**Отзывчивость**: UI-приложение должно реагировать на ввод пользователя, пока в фоне выполняется длинная операция. Конкурентность обеспечивает это без дополнительных ядер.

---

## 2. Что такое параллелизм

Параллелизм — это физическое одновременное выполнение нескольких вычислений. Для параллелизма нужно несколько процессорных ядер (или несколько машин).

Наш пример с поваром: если на кухне работают два повара — это параллелизм. Оба физически делают разные вещи в один момент времени.

### 2.1 CPU-bound задачи и параллелизм

Параллелизм максимально полезен для CPU-bound задач — когда узкое место именно в вычислениях, а не в I/O.

Пример: рендеринг изображений. Каждый пиксель можно вычислять независимо — идеальная задача для параллелизма.

```python
import multiprocessing
import numpy as np
from PIL import Image

def render_chunk(args):
    """Рендеринг части фрактала Мандельброта."""
    y_start, y_end, width, height, max_iter = args
    result = np.zeros((y_end - y_start, width), dtype=np.int32)
    
    for py in range(y_start, y_end):
        for px in range(width):
            # Преобразование пикселя в комплексное число
            c = complex(
                (px / width) * 3.5 - 2.5,
                (py / height) * 2.0 - 1.0
            )
            z = 0
            for i in range(max_iter):
                if abs(z) > 2:
                    result[py - y_start, px] = i
                    break
                z = z * z + c
    return result

def render_parallel(width=800, height=600, max_iter=100):
    num_cores = multiprocessing.cpu_count()
    chunk_size = height // num_cores
    
    chunks = [
        (i * chunk_size, (i + 1) * chunk_size, width, height, max_iter)
        for i in range(num_cores)
    ]
    
    # Параллельное выполнение на всех ядрах
    with multiprocessing.Pool(num_cores) as pool:
        results = pool.map(render_chunk, chunks)
    
    return np.vstack(results)

if __name__ == "__main__":
    image_data = render_parallel()
    img = Image.fromarray(image_data.astype(np.uint8) * 2)
    img.save("mandelbrot.png")
```

Здесь каждое ядро обрабатывает свою часть изображения — чистый параллелизм.

### 2.2 Параллелизм данных и задач

Различают два вида параллелизма:

| Вид | Описание | Пример |
|-----|----------|--------|
| Data parallelism | Одна операция над разными данными | Применить фильтр к каждому пикселю |
| Task parallelism | Разные операции одновременно | Компилировать разные файлы |

SIMD (Single Instruction Multiple Data) — аппаратный data parallelism. Одна инструкция процессора обрабатывает несколько элементов одновременно (SSE, AVX):

```c
#include <immintrin.h>

// Сложение 8 float одновременно с AVX
void add_arrays_avx(float* a, float* b, float* result, int n) {
    for (int i = 0; i < n; i += 8) {
        __m256 va = _mm256_loadu_ps(&a[i]);
        __m256 vb = _mm256_loadu_ps(&b[i]);
        __m256 vc = _mm256_add_ps(va, vb);
        _mm256_storeu_ps(&result[i], vc);
    }
}
```

---

## 3. Модели конкурентности

Существует несколько фундаментальных моделей конкурентности, каждая со своими компромиссами.

### 3.1 Многопоточность (Shared Memory + Locks)

Традиционная модель: несколько потоков (threads) работают в общем адресном пространстве. Синхронизация через мьютексы, семафоры, условные переменные.

```python
import threading
import time

shared_counter = 0
lock = threading.Lock()

def increment(n):
    global shared_counter
    for _ in range(n):
        with lock:  # Критическая секция
            shared_counter += 1

threads = [threading.Thread(target=increment, args=(100000,)) for _ in range(4)]

for t in threads:
    t.start()
for t in threads:
    t.join()

print(f"Counter: {shared_counter}")  # Должно быть 400000
```

**Плюсы**: привычная модель, хорошая поддержка в ОС, прямой доступ к данным.

**Минусы**: race conditions, deadlocks, трудно рассуждать о корректности, GIL в CPython ограничивает истинный параллелизм.

**Классическая проблема — гонка данных**:

```python
# НЕПРАВИЛЬНО — без блокировки
def increment_racy(n):
    global shared_counter
    for _ in range(n):
        # read-modify-write — НЕ атомарно!
        shared_counter += 1  
        # Эквивалентно:
        # temp = shared_counter  # 1. читаем
        # temp = temp + 1         # 2. модифицируем
        # shared_counter = temp   # 3. пишем
        # Между шагами 1 и 3 другой поток может изменить shared_counter
```

### 3.2 Event-Driven (Событийная модель)

Один поток обрабатывает события в цикле (event loop). Вместо блокирующих вызовов — регистрация обработчиков.

```javascript
// Node.js — event-driven, однопоточный
const http = require('http');

const server = http.createServer((req, res) => {
    // Этот callback вызывается для каждого запроса
    // НЕ блокирует event loop
    setTimeout(() => {
        res.writeHead(200);
        res.end('Hello World\n');
    }, 100); // имитация задержки
});

server.listen(3000);
// Один поток обрабатывает тысячи соединений
```

Event loop — это цикл, который:
1. Берёт событие из очереди
2. Вызывает обработчик (callback)
3. Возвращается к очереди

**Плюсы**: нет проблем с shared state, высокая производительность для I/O-bound задач, низкое потребление памяти.

**Минусы**: нельзя блокировать event loop (нет длинных синхронных операций), сложность с CPU-bound задачами.

### 3.3 Корутины (Coroutines)

Корутины — функции, которые могут приостанавливать выполнение и передавать управление другим корутинам, а затем возобновляться.

```python
import asyncio

async def task_a():
    print("Task A: start")
    await asyncio.sleep(1)  # Уступаем управление
    print("Task A: end")

async def task_b():
    print("Task B: start")
    await asyncio.sleep(0.5)
    print("Task B: end")

async def main():
    # Запускаем конкурентно на одном потоке
    await asyncio.gather(task_a(), task_b())

asyncio.run(main())
# Вывод:
# Task A: start
# Task B: start
# Task B: end   (через 0.5с)
# Task A: end   (через 1с)
```

Корутины в Go называются goroutines и управляются Go runtime с M:N планировщиком (M горутин на N потоков ОС):

```go
package main

import (
    "fmt"
    "sync"
    "time"
)

func worker(id int, wg *sync.WaitGroup) {
    defer wg.Done()
    fmt.Printf("Worker %d starting\n", id)
    time.Sleep(time.Second)
    fmt.Printf("Worker %d done\n", id)
}

func main() {
    var wg sync.WaitGroup
    
    for i := 1; i <= 5; i++ {
        wg.Add(1)
        go worker(i, &wg)  // Запускаем 5 горутин
    }
    
    wg.Wait()
}
```

### 3.4 CSP (Communicating Sequential Processes)

CSP — модель, предложенная Хоаром в 1978 году: независимые процессы общаются через синхронные каналы. Go реализует CSP через goroutines + channels:

```go
func producer(ch chan<- int) {
    for i := 0; i < 10; i++ {
        ch <- i  // Отправляем в канал
    }
    close(ch)
}

func consumer(ch <-chan int, results chan<- int) {
    sum := 0
    for v := range ch {
        sum += v
    }
    results <- sum
}

func main() {
    ch := make(chan int, 5)       // Буферизованный канал
    results := make(chan int, 1)
    
    go producer(ch)
    go consumer(ch, results)
    
    fmt.Println("Sum:", <-results)
}
```

### 3.5 Actor Model (Модель акторов)

Акторы — независимые единицы с приватным состоянием, общающиеся только через сообщения. Erlang и Elixir — классические реализации.

```elixir
defmodule Counter do
  def start(initial \\ 0) do
    spawn(fn -> loop(initial) end)
  end

  defp loop(count) do
    receive do
      {:increment, from} ->
        send(from, {:ok, count + 1})
        loop(count + 1)
      {:get, from} ->
        send(from, {:count, count})
        loop(count)
    end
  end
end

# Использование
pid = Counter.start(0)
send(pid, {:increment, self()})
receive do {:ok, new_count} -> IO.puts("New count: #{new_count}") end
```

---

## 4. Закон Амдала и пределы параллелизма

Закон Амдала (1967) формализует фундаментальное ограничение: не всю программу можно распараллелить.

### 4.1 Формула

Пусть `p` — доля программы, которая может выполняться параллельно (0 ≤ p ≤ 1). Тогда максимальное ускорение при использовании `n` процессоров:

```
S(n) = 1 / ((1 - p) + p/n)
```

При `n → ∞`: `S(∞) = 1 / (1 - p)`

Это значит: если 5% программы последовательны, максимальное ускорение — в 20 раз, сколько бы ядер вы ни добавили.

```python
def amdahl_speedup(parallel_fraction: float, num_processors: int) -> float:
    """
    Вычисляет теоретическое ускорение по закону Амдала.
    
    Args:
        parallel_fraction: доля параллельного кода (0.0 - 1.0)
        num_processors: количество процессоров
    
    Returns:
        Коэффициент ускорения
    """
    sequential_fraction = 1 - parallel_fraction
    return 1 / (sequential_fraction + parallel_fraction / num_processors)

# Анализ для разных значений p
print("Процессоров | p=50%  | p=75%  | p=90%  | p=95%")
print("-" * 55)
for n in [1, 2, 4, 8, 16, 32, 64, 128, 256]:
    speedups = [amdahl_speedup(p, n) for p in [0.5, 0.75, 0.9, 0.95]]
    print(f"{n:11d} | {speedups[0]:5.1f}x | {speedups[1]:5.1f}x | "
          f"{speedups[2]:5.1f}x | {speedups[3]:5.1f}x")
```

Вывод:
```
Процессоров | p=50%  | p=75%  | p=90%  | p=95%
-------------------------------------------------------
          1 |   1.0x |   1.0x |   1.0x |   1.0x
          2 |   1.3x |   1.6x |   1.8x |   1.9x
          4 |   1.6x |   2.3x |   3.1x |   3.5x
          8 |   1.8x |   2.9x |   4.7x |   5.9x
         16 |   1.9x |   3.4x |   6.4x |   9.1x
         32 |   2.0x |   3.7x |   7.8x |  12.6x
         64 |   2.0x |   3.8x |   8.8x |  15.8x
        128 |   2.0x |   3.9x |   9.3x |  17.9x
        256 |   2.0x |   3.9x |   9.6x |  18.9x
```

Максимально достижимое ускорение при p=90% — около 10x, при p=95% — около 20x.

### 4.2 Закон Густафсона (модификация Амдала)

Амдал предполагал фиксированный размер задачи. Густафсон (1988) указал: на практике с ростом ресурсов растёт и размер задачи (мы решаем более сложные проблемы).

```
S(n) = n - (1 - p) * (n - 1)
```

По Густафсону, ускорение масштабируется лучше, если задача «растёт» вместе с числом процессоров.

### 4.3 Практические последствия

```python
import time
import concurrent.futures

def cpu_bound_task(n: int) -> int:
    """Имитация CPU-bound работы."""
    result = 0
    for i in range(n):
        result += i * i
    return result

def measure_speedup(task_count: int, work_per_task: int):
    # Последовательное выполнение
    start = time.perf_counter()
    [cpu_bound_task(work_per_task) for _ in range(task_count)]
    sequential_time = time.perf_counter() - start
    
    print(f"Sequential: {sequential_time:.3f}s")
    
    for workers in [2, 4, 8]:
        start = time.perf_counter()
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            list(executor.map(cpu_bound_task, [work_per_task] * task_count))
        parallel_time = time.perf_counter() - start
        speedup = sequential_time / parallel_time
        print(f"{workers} workers: {parallel_time:.3f}s (speedup: {speedup:.2f}x)")

measure_speedup(task_count=8, work_per_task=1_000_000)
```

---

## 5. Когда что использовать

### 5.1 Веб-сервер — конкурентность важнее параллелизма

Типичный веб-запрос: принять TCP-соединение → прочитать HTTP-заголовки → запросить БД (ожидание 5-50 мс) → сформировать ответ → отправить. 90% времени — ожидание I/O.

```
nginx: 1 worker process = 1 event loop
       обрабатывает тысячи соединений конкурентно
       использует epoll()/kqueue() для non-blocking I/O
```

nginx использует конкурентность. Параллелизм — несколько worker процессов (по числу ядер).

### 5.2 Рендеринг видео — параллелизм важнее конкурентности

Каждый кадр независим. Задача CPU-bound. Оптимально — столько параллельных потоков, сколько ядер.

```python
from concurrent.futures import ProcessPoolExecutor
import os

def render_frame(frame_number: int) -> str:
    # CPU-bound: вычисляем освещение, тени, etc.
    result = expensive_render_computation(frame_number)
    return f"frame_{frame_number:04d}.png"

def render_video(total_frames: int):
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = [executor.submit(render_frame, i) 
                   for i in range(total_frames)]
        return [f.result() for f in futures]
```

### 5.3 Матрица выбора модели

| Тип задачи | Модель | Инструменты |
|------------|--------|-------------|
| I/O-bound, много соединений | Event Loop / Async | asyncio, Node.js, nginx |
| I/O-bound, независимые задачи | Thread Pool / Goroutines | Go, Java threads |
| CPU-bound, разные данные | Process Pool / SIMD | multiprocessing, OpenMP |
| CPU-bound, зависимые задачи | Параллельные алгоритмы | CUDA, MPI, OpenMP |
| Надёжность, изоляция | Actor Model | Erlang, Akka |
| Пайплайны данных | CSP / Channels | Go channels, Kotlin Flow |

---

## 6. Практические примеры

### 6.1 Python: GIL и его последствия

Global Interpreter Lock (GIL) в CPython — мьютекс, позволяющий только одному потоку выполнять Python-байткод в один момент. Это делает многопоточность неэффективной для CPU-bound задач в CPython.

```python
import threading
import multiprocessing
import time

def count_to_billion():
    x = 0
    for _ in range(10**8):
        x += 1
    return x

# Многопоточность (GIL ограничивает — не ускоряет CPU-bound задачи)
start = time.perf_counter()
threads = [threading.Thread(target=count_to_billion) for _ in range(4)]
for t in threads: t.start()
for t in threads: t.join()
threaded_time = time.perf_counter() - start

# Многопроцессность (обходим GIL)
start = time.perf_counter()
with multiprocessing.Pool(4) as pool:
    pool.map(count_to_billion, range(4))
mp_time = time.perf_counter() - start

print(f"Threading: {threaded_time:.2f}s")      # ~медленнее из-за GIL
print(f"Multiprocessing: {mp_time:.2f}s")      # ~быстрее
```

Решение в Python 3.13+: экспериментальный режим без GIL (`python -X gil=0`).

### 6.2 Go: горутины как легковесные потоки

Go runtime запускает N горутин на M потоках ОС (M:N мультиплексирование). Горутина стартует со стеком 2-4 КБ (поток ОС — 1-8 МБ).

```go
package main

import (
    "fmt"
    "net/http"
    "sync"
)

func fetchURL(url string, wg *sync.WaitGroup, results chan<- string) {
    defer wg.Done()
    resp, err := http.Get(url)
    if err != nil {
        results <- fmt.Sprintf("%s: error", url)
        return
    }
    defer resp.Body.Close()
    results <- fmt.Sprintf("%s: %d", url, resp.StatusCode)
}

func main() {
    urls := []string{
        "https://google.com",
        "https://github.com",
        "https://stackoverflow.com",
    }
    
    var wg sync.WaitGroup
    results := make(chan string, len(urls))
    
    for _, url := range urls {
        wg.Add(1)
        go fetchURL(url, &wg, results)
    }
    
    // Закрываем канал когда все горутины завершились
    go func() {
        wg.Wait()
        close(results)
    }()
    
    for result := range results {
        fmt.Println(result)
    }
}
```

### 6.3 Конкурентность в JavaScript: event loop

```javascript
// Демонстрация event loop: что выполняется когда
console.log('1: synchronous');

setTimeout(() => console.log('2: setTimeout (macro-task)'), 0);

Promise.resolve().then(() => console.log('3: Promise (micro-task)'));

queueMicrotask(() => console.log('4: queueMicrotask'));

console.log('5: synchronous');

// Порядок вывода:
// 1: synchronous
// 5: synchronous
// 3: Promise (micro-task)
// 4: queueMicrotask
// 2: setTimeout (macro-task)
```

Микрозадачи (Promise callbacks) выполняются до следующей итерации event loop, макрозадачи (setTimeout) — в следующей итерации.

---

## 7. Rob Pike: «Concurrency is not Parallelism»

В докладе 2012 года Роб Пайк привёл наглядный пример: сжигание книг в печи. 

**Параллельное решение**: несколько печей, несколько человек — каждый сжигает свою книгу.

**Конкурентное решение**: один человек, но с умной организацией — разделить книги на части, конвейерная обработка: один несёт стопку к печи, второй рубит страницы, третий сжигает.

Конкурентное решение лучше масштабируется — можно добавить физических исполнителей (параллелизм), и программа уже готова к этому благодаря правильной структуре.

Ключевой тезис: **конкурентность — это инструмент проектирования, параллелизм — это результат исполнения**.

```go
// Конкурентная структура позволяет лёгкий параллелизм
// Пайплайн в Go — конкурентен по структуре
func pipeline() {
    naturals := make(chan int)
    squares := make(chan int)
    
    // Генератор
    go func() {
        for i := 0; ; i++ {
            naturals <- i
        }
    }()
    
    // Возведение в квадрат
    go func() {
        for v := range naturals {
            squares <- v * v
        }
    }()
    
    // Вывод
    for v := range squares {
        fmt.Println(v)
        if v > 1000 { break }
    }
}
```

---

## Заключение

Разграничение между конкурентностью и параллелизмом — не просто академическое: от правильного понимания зависит выбор архитектуры системы.

**Практические выводы**:

1. **I/O-bound задачи** (сеть, диск, БД): используйте конкурентность — async/await, event loop, goroutines. Параллелизм здесь даёт меньше выгоды, чем правильная модель конкурентности.

2. **CPU-bound задачи** (вычисления, компрессия, шифрование): нужен параллелизм — несколько процессов или потоков на разных ядрах.

3. **Закон Амдала** ограничивает ускорение. Найдите последовательный «узкое горлышко» и минимизируйте его прежде, чем добавлять ядра.

4. **Начинайте с правильной модели конкурентности** — CSP, actors, async/await — и параллелизм придёт «бесплатно».

5. **GIL в Python** означает, что многопоточность не даёт CPU-параллелизма. Для CPU-bound задач — multiprocessing или C-расширения.

---

## Литература и источники

1. Pike, R. (2012). *Concurrency is not Parallelism*. Google I/O. https://go.dev/blog/waza-talk
2. Amdahl, G. M. (1967). Validity of the single processor approach to achieving large scale computing capabilities. *AFIPS Conference Proceedings*.
3. Gustafson, J. L. (1988). Reevaluating Amdahl's law. *Communications of the ACM*, 31(5), 532-533.
4. Hoare, C. A. R. (1978). Communicating sequential processes. *Communications of the ACM*, 21(8), 666-677.
5. Hewitt, C., Bishop, P., Steiger, R. (1973). A universal modular ACTOR formalism for artificial intelligence. *IJCAI*.
6. Python Documentation. asyncio — Asynchronous I/O. https://docs.python.org/3/library/asyncio.html
7. The Go Programming Language Specification. Goroutines. https://go.dev/ref/spec#Go_statements
8. Wikipedia. Amdahl's law. https://en.wikipedia.org/wiki/Amdahl%27s_law
9. Wikipedia. Concurrency (computer science). https://en.wikipedia.org/wiki/Concurrency_(computer_science)
10. Burns, B., & Tracey, B. (2022). *Designing Distributed Systems*. O'Reilly Media.
