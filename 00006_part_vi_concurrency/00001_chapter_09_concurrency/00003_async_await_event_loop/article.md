# Async/await и event loop

## Введение

Проблема масштабируемости сетевых серверов десятилетиями была одной из ключевых в системном программировании. Традиционный подход «один поток на соединение» (thread-per-connection) имеет фундаментальное ограничение: потоки ОС дороги — каждый занимает 1-8 МБ памяти для стека и требует переключения контекста при блокировке. Сервер с 10 000 одновременных соединений потреблял бы 10-80 ГБ только на стеки потоков.

В 1999 году Дэн Кегель в статье «The C10K problem» сформулировал задачу: как обрабатывать 10 000 одновременных соединений на одном сервере? Решение оказалось в событийно-ориентированном вводе/выводе: вместо блокирующих syscall — неблокирующий I/O + уведомления о готовности дескрипторов. Nginx, Node.js, asyncio — все они построены на этой идее.

В этой главе мы проследим эволюцию от callback-hell к Promise и async/await, разберём устройство event loop в JavaScript и Python asyncio, и поймём, почему async/await — это синтаксический сахар, а не новая модель исполнения.

---

## 1. Проблема блокирующего I/O

### 1.1 Что происходит при blocking I/O

Когда программа читает из сокета или файла, она выполняет системный вызов (`read()`), и ОС переводит поток в состояние ожидания до получения данных:

```python
import socket
import time

def handle_request_blocking(conn):
    """Блокирующий обработчик — поток ждёт все время."""
    start = time.time()
    
    # БЛОКИРУЕТСЯ: поток спит пока данные не придут
    data = conn.recv(4096)  
    
    # CPU простаивает пока мы ждём ответа от БД
    result = db_query("SELECT * FROM users")  # ~5мс ожидания
    
    conn.send(result.encode())
    print(f"Handled in {time.time()-start:.3f}s")
```

Поток спит. CPU мог бы обрабатывать другие запросы, но не делает этого — он ждёт завершения syscall.

### 1.2 Накладные расходы thread-per-connection

```python
# Традиционный подход: ThreadingTCPServer
import socketserver

class ThreadedHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = self.request.recv(1024)
        # ~1-5 мс на запрос, поток заблокирован всё это время
        response = process_request(data)
        self.request.send(response)

server = socketserver.ThreadingTCPServer(("", 8080), ThreadedHandler)
# 10 000 соединений = 10 000 потоков = ~10 ГБ памяти на стеки
server.serve_forever()
```

Проблемы:
- Каждый поток: 1-8 МБ стека
- Context switch: 1-10 мкс накладные расходы
- Кэш-промахи при переключении
- Scheduling overhead при тысячах потоков

---

## 2. Non-blocking I/O и системные вызовы

### 2.1 select(), poll(), epoll()

ОС предоставляет механизмы ожидания готовности сразу нескольких дескрипторов:

```python
import select
import socket

server = socket.socket()
server.bind(('', 8080))
server.listen(100)
server.setblocking(False)  # Non-blocking!

clients = []
inputs = [server]

while True:
    # select() блокируется, НО отслеживает ВСЕ дескрипторы сразу
    readable, _, _ = select.select(inputs, [], [], timeout=1.0)
    
    for s in readable:
        if s is server:
            conn, addr = server.accept()
            conn.setblocking(False)
            inputs.append(conn)
        else:
            data = s.recv(1024)
            if data:
                s.send(data)  # Echo
            else:
                inputs.remove(s)
                s.close()
```

`select()` — O(N) по числу дескрипторов, ограничен `FD_SETSIZE` (1024 на Linux).

`epoll()` (Linux) — O(1) уведомления, масштабируется до миллионов дескрипторов:

```python
import select
import socket

server = socket.socket()
server.bind(('', 8080))
server.listen(1000)
server.setblocking(False)

epoll = select.epoll()
epoll.register(server.fileno(), select.EPOLLIN)

fd_to_socket = {server.fileno(): server}

while True:
    events = epoll.poll(timeout=1)  # Ждём событий
    for fileno, event in events:
        if fileno == server.fileno():
            conn, addr = server.accept()
            conn.setblocking(False)
            epoll.register(conn.fileno(), select.EPOLLIN)
            fd_to_socket[conn.fileno()] = conn
        elif event & select.EPOLLIN:
            data = fd_to_socket[fileno].recv(1024)
            if data:
                fd_to_socket[fileno].send(data)
            else:
                epoll.unregister(fileno)
                fd_to_socket[fileno].close()
                del fd_to_socket[fileno]
```

---

## 3. Эволюция: Callbacks → Promises → Async/Await

### 3.1 Callbacks — первое поколение

JavaScript Node.js изначально строился на callbacks:

```javascript
const fs = require('fs');
const http = require('http');

// Callback-based код — «callback hell»
function processRequest(userId, callback) {
    db.getUser(userId, function(err, user) {       // уровень 1
        if (err) return callback(err);
        db.getPermissions(user.id, function(err, perms) {  // уровень 2
            if (err) return callback(err);
            fs.readFile('/config.json', function(err, config) {  // уровень 3
                if (err) return callback(err);
                http.get(user.profileUrl, function(err, profile) {  // уровень 4
                    if (err) return callback(err);
                    callback(null, {user, perms, config, profile});
                });
            });
        });
    });
}
```

Проблемы callbacks:
- «Pyramid of doom» — глубокая вложенность
- Сложная обработка ошибок
- Невозможно использовать try/catch
- Нельзя легко параллелизовать

### 3.2 Promises — второе поколение

```javascript
// Promise-based код
function processRequest(userId) {
    return db.getUser(userId)
        .then(user => db.getPermissions(user.id))
        .then(perms => fs.promises.readFile('/config.json')
            .then(config => ({perms, config})))
        .then(({perms, config}) => 
            http.get(user.profileUrl)
                .then(profile => ({user, perms, config, profile})));
}

// Promise.all для параллельного выполнения
function fetchMultiple(ids) {
    const promises = ids.map(id => db.getUser(id));
    return Promise.all(promises);  // Все запросы параллельно!
}
```

Promise — объект, представляющий будущий результат. Состояния: `pending → fulfilled | rejected`.

### 3.3 Async/Await — синтаксический сахар

`async/await` — это синтаксический сахар над Promise. Компилятор/интерпретатор трансформирует `async` функцию в функцию, возвращающую Promise:

```javascript
// Async/await — выглядит как синхронный код
async function processRequest(userId) {
    try {
        const user = await db.getUser(userId);         // Promise
        const perms = await db.getPermissions(user.id); // Promise
        const config = await fs.promises.readFile('/config.json');
        const profile = await http.get(user.profileUrl);
        
        return {user, perms, config, profile};
    } catch (err) {
        console.error('Error:', err);
        throw err;
    }
}

// Параллельное выполнение с async/await
async function fetchParallel(ids) {
    // Запускаем все параллельно
    const promises = ids.map(id => db.getUser(id));
    const users = await Promise.all(promises);  // Ждём всех
    return users;
}
```

**Трансформация**: `async function f() { const x = await expr; return x + 1; }` примерно равно:
```javascript
function f() {
    return expr.then(x => x + 1);
}
```

---

## 4. Event Loop в JavaScript (Node.js)

### 4.1 Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        Node.js Event Loop                        │
│                                                                  │
│  Call Stack          Microtask Queue        Macro Task Queue     │
│  ┌─────────┐         ┌─────────────┐       ┌─────────────────┐  │
│  │         │  ───→   │ Promise     │  ───→ │ setTimeout      │  │
│  │  main() │         │ callbacks   │       │ setInterval     │  │
│  │ func1() │         │             │       │ I/O callbacks   │  │
│  │ func2() │         │ queueMicro- │       │ setImmediate    │  │
│  └─────────┘         │ task()      │       └─────────────────┘  │
│                      └─────────────┘                             │
│                                                                  │
│  libuv Thread Pool (по умолчанию 4 потока для I/O)               │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Thread 1: file I/O    Thread 3: DNS                     │    │
│  │  Thread 2: crypto      Thread 4: другие blocking ops     │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Фазы Event Loop (libuv)

Event loop Node.js проходит через фазы в каждой итерации:

```
timers → pending callbacks → idle/prepare → poll → check → close callbacks
```

1. **timers**: выполняются setTimeout/setInterval коллбеки
2. **pending callbacks**: I/O коллбеки из предыдущей итерации
3. **poll**: ждёт новых I/O событий, выполняет их коллбеки
4. **check**: setImmediate() коллбеки
5. **close callbacks**: socket.on('close') и т.п.

**Microtasks** (Promise, queueMicrotask) выполняются после КАЖДОЙ фазы, до следующей:

```javascript
console.log('start');

setTimeout(() => console.log('setTimeout'), 0);
setImmediate(() => console.log('setImmediate'));

Promise.resolve()
    .then(() => console.log('promise 1'))
    .then(() => console.log('promise 2'));

queueMicrotask(() => console.log('queueMicrotask'));

console.log('end');

// Вывод (гарантированный):
// start
// end
// promise 1       ← microtask
// promise 2       ← microtask (добавлена во время обработки promise 1)
// queueMicrotask  ← microtask
// setTimeout      ← macrotask (или setImmediate — порядок не гарантирован)
// setImmediate
```

### 4.3 Блокировка Event Loop — критическая ошибка

```javascript
// ПЛОХО: блокируем event loop
app.get('/slow', (req, res) => {
    // CPU-bound задача блокирует event loop!
    const result = fibonacci(45);  // ~5 секунд
    res.json({result});
    // Все другие запросы ждут эти 5 секунд
});

// ХОРОШО: вынести CPU-bound в worker thread
const { Worker } = require('worker_threads');

app.get('/slow', (req, res) => {
    const worker = new Worker('./fibonacci-worker.js', {
        workerData: { n: 45 }
    });
    worker.on('message', result => res.json({result}));
});
```

---

## 5. Python asyncio

### 5.1 Event Loop и корутины

Python asyncio реализует event loop на базе `selectors` (epoll/kqueue/IOCP):

```python
import asyncio
import aiohttp
import time

# Корутина — функция с async def, может await'ить
async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Неблокирующий HTTP-запрос."""
    async with session.get(url) as response:
        return await response.text()

async def main():
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/1",
    ]
    
    start = time.perf_counter()
    
    async with aiohttp.ClientSession() as session:
        # Запускаем все запросы конкурентно
        tasks = [asyncio.create_task(fetch_page(session, url)) for url in urls]
        results = await asyncio.gather(*tasks)
    
    elapsed = time.perf_counter() - start
    print(f"Fetched {len(results)} pages in {elapsed:.2f}s")
    # ~1 секунда, а не 3! (конкурентный I/O)

asyncio.run(main())
```

### 5.2 Архитектура asyncio

```
asyncio Event Loop
┌────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Coroutines         Tasks              selectors (epoll)         │
│  ┌──────────┐      ┌──────────────┐   ┌───────────────────────┐ │
│  │ async def│ ──→  │ Task wraps   │   │ fd 5: readable → cb1  │ │
│  │ f():     │      │ coroutine    │   │ fd 7: readable → cb2  │ │
│  │  await X │      │             │   │ fd 9: writable → cb3  │ │
│  └──────────┘      └──────────────┘   └───────────────────────┘ │
│                                                                  │
│  Ready Queue                                                     │
│  [task1_resume, task3_resume, callback4]                        │
│                                                                  │
└────────────────────────────────────────────────────────────────┘
```

Когда корутина вызывает `await asyncio.sleep(1)`, она:
1. Регистрирует таймер в event loop
2. Возвращает управление event loop
3. Event loop запускает другие готовые задачи
4. Через 1 секунду event loop возобновляет корутину

### 5.3 Tasks и конкурентность

```python
import asyncio

async def worker(name: str, delay: float):
    print(f"{name}: start")
    await asyncio.sleep(delay)
    print(f"{name}: done after {delay}s")
    return name

async def demo_concurrency():
    # asyncio.gather — запускает корутины конкурентно
    results = await asyncio.gather(
        worker("A", 1.0),
        worker("B", 0.5),
        worker("C", 1.5),
    )
    print(f"All done: {results}")
    # Вывод:
    # A: start
    # B: start  
    # C: start
    # B: done after 0.5s
    # A: done after 1.0s
    # C: done after 1.5s
    # All done: ['A', 'B', 'C']
    # Общее время ~1.5с, а не 3.0с

async def demo_tasks():
    # create_task — немедленно планирует выполнение
    task_a = asyncio.create_task(worker("A", 1.0))
    task_b = asyncio.create_task(worker("B", 0.5))
    
    # Делаем что-то ещё пока задачи выполняются
    await asyncio.sleep(0.1)
    print("Both tasks are running concurrently!")
    
    # Ждём завершения
    result_a = await task_a
    result_b = await task_b

asyncio.run(demo_concurrency())
```

### 5.4 Синхронизация в asyncio

```python
import asyncio

# asyncio.Lock — не блокирует поток ОС, только корутину
lock = asyncio.Lock()
shared_state = {}

async def update_shared(key: str, value: int):
    async with lock:
        # Критическая секция — только одна корутина одновременно
        old = shared_state.get(key, 0)
        await asyncio.sleep(0)  # Имитируем асинхронную работу
        shared_state[key] = old + value

# asyncio.Queue — безопасная очередь
async def producer(queue: asyncio.Queue):
    for i in range(5):
        await queue.put(i)
        await asyncio.sleep(0.1)
    await queue.put(None)  # Sentinel

async def consumer(queue: asyncio.Queue):
    while True:
        item = await queue.get()
        if item is None:
            break
        print(f"Processing: {item}")

async def pipeline():
    queue = asyncio.Queue(maxsize=3)  # Буфер 3 элемента
    await asyncio.gather(
        producer(queue),
        consumer(queue)
    )

asyncio.run(pipeline())
```

### 5.5 Ограничения asyncio

```python
import asyncio
import time

async def bad_blocking():
    """НЕПРАВИЛЬНО: блокируем event loop синхронным кодом."""
    time.sleep(2)  # Блокирует весь event loop!
    return "done"

async def good_async():
    """ПРАВИЛЬНО: используем run_in_executor для блокирующего кода."""
    loop = asyncio.get_event_loop()
    # Запускаем блокирующий код в thread pool
    result = await loop.run_in_executor(None, time.sleep, 2)
    return "done"

async def cpu_bound_task():
    """CPU-bound: нужен ProcessPoolExecutor."""
    from concurrent.futures import ProcessPoolExecutor
    import math
    
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, math.factorial, 10000)
    return result
```

---

## 6. Сравнение: async vs threads

```python
import asyncio
import threading
import time
import aiohttp
import requests

N_REQUESTS = 100
URL = "https://httpbin.org/uuid"

# Вариант 1: Синхронный (последовательный)
def sync_requests():
    results = []
    for _ in range(N_REQUESTS):
        r = requests.get(URL)
        results.append(r.json())
    return results

# Вариант 2: Многопоточный
def threaded_requests():
    results = [None] * N_REQUESTS
    threads = []
    
    def fetch(i):
        results[i] = requests.get(URL).json()
    
    for i in range(N_REQUESTS):
        t = threading.Thread(target=fetch, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    return results

# Вариант 3: Asyncio
async def async_requests():
    async with aiohttp.ClientSession() as session:
        async def fetch():
            async with session.get(URL) as r:
                return await r.json()
        
        tasks = [asyncio.create_task(fetch()) for _ in range(N_REQUESTS)]
        return await asyncio.gather(*tasks)

# Сравнение производительности
# Sync:    ~N * RTT  (напр., 100 * 200ms = 20 сек)
# Threads: ~RTT      (напр., 200ms) + overhead потоков
# Async:   ~RTT      (напр., 200ms) + минимальный overhead
```

| Характеристика | Синхронный | Threads | Asyncio |
|---------------|-----------|---------|---------|
| I/O-bound производительность | Плохая | Хорошая | Отличная |
| CPU-bound производительность | Хорошая | Средняя (GIL) | Плохая |
| Память на 10K задач | Нет | ~10 ГБ | ~МБ |
| Сложность кода | Простой | Средняя | Средняя |
| Отладка | Простая | Сложная | Средняя |
| Гонки данных | Нет | Есть риск | Минимальный |

---

## 7. Практические паттерны

### 7.1 Таймаут

```python
import asyncio

async def fetch_with_timeout(url: str, timeout: float):
    try:
        async with asyncio.timeout(timeout):  # Python 3.11+
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.text()
    except asyncio.TimeoutError:
        print(f"Timeout after {timeout}s for {url}")
        return None

# Или через wait_for:
async def fetch_safe(url: str):
    try:
        result = await asyncio.wait_for(
            some_coroutine(url),
            timeout=5.0
        )
        return result
    except asyncio.TimeoutError:
        return None
```

### 7.2 Семафор для ограничения конкурентности

```python
import asyncio
import aiohttp

async def fetch_with_semaphore(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore
) -> dict:
    async with semaphore:  # Максимум N одновременных запросов
        async with session.get(url) as response:
            return await response.json()

async def fetch_all_limited(urls: list[str], max_concurrent: int = 10):
    semaphore = asyncio.Semaphore(max_concurrent)
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_with_semaphore(session, url, semaphore)
            for url in urls
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### 7.3 Стриминг (asyncio generator)

```python
import asyncio

async def stream_lines(filepath: str):
    """Асинхронный генератор — yield строки файла."""
    async with aioopen(filepath) as f:
        async for line in f:
            yield line.strip()

async def process_stream():
    async for line in stream_lines('/var/log/app.log'):
        if 'ERROR' in line:
            await send_alert(line)
```

---

## Заключение

Async/await — это не магия, а синтаксическое преобразование, делающее асинхронный код читаемым как синхронный. Под капотом всегда работает event loop и неблокирующий I/O.

**Ключевые выводы**:

1. **Event loop** — один поток обрабатывает тысячи I/O событий через epoll/kqueue, переключаясь между корутинами при ожидании I/O.

2. **async/await — синтаксический сахар** над Promise/Future. Каждый `await` — это точка, где корутина может уступить управление event loop.

3. **Никогда не блокируйте event loop** синхронным I/O или CPU-bound кодом. Используйте `run_in_executor` для legacy блокирующего кода.

4. **asyncio не ускоряет CPU-bound задачи** — для них нужны потоки или процессы.

5. **Микрозадачи** (Promise callbacks) имеют приоритет над макрозадачами (setTimeout) — важно для понимания порядка исполнения.

---

## Литература и источники

1. Kegel, D. (1999). The C10K Problem. http://www.kegel.com/c10k.html
2. Python Documentation. asyncio — Asynchronous I/O. https://docs.python.org/3/library/asyncio.html
3. Node.js Documentation. The Node.js Event Loop, Timers, and process.nextTick(). https://nodejs.org/en/docs/guides/event-loop-timers-and-nexttick
4. MDN Web Docs. Using Promises. https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Using_promises
5. MDN Web Docs. async function. https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function
6. Grigorik, I. (2013). *High Performance Browser Networking*. O'Reilly. https://hpbn.co/
7. libuv Documentation. Design overview. https://docs.libuv.org/en/v1.x/design.html
8. Wikipedia. Event loop. https://en.wikipedia.org/wiki/Event_loop
9. PEP 492 — Coroutines with async and await syntax. https://peps.python.org/pep-0492/
10. Beazley, D. (2015). Python Concurrency from the Ground Up (PyCon talk). https://www.youtube.com/watch?v=MCs5OvhV9S4
