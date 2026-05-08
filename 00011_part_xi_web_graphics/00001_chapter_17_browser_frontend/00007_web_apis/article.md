# Web APIs: Fetch, WebSocket, Web Workers, Service Workers, IndexedDB

Браузер — это не просто среда выполнения JavaScript. Это мощная платформа с богатым набором API: сетевые запросы, постоянное хранилище, фоновые вычисления, двусторонняя коммуникация, оффлайн-режим. В этой статье разберём ключевые Web API, которые должен знать каждый frontend-разработчик.

## Fetch API: современные HTTP-запросы

Fetch API заменил XMLHttpRequest (XHR) как основной инструмент для HTTP-запросов. Он основан на промисах и имеет чистый, эргономичный API.

### Основы Fetch

```javascript
// Простой GET запрос
const response = await fetch('https://api.example.com/users');
const users = await response.json();

// POST запрос с JSON
const response = await fetch('https://api.example.com/users', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer my-token'
    },
    body: JSON.stringify({ name: 'Alice', email: 'alice@example.com' })
});

if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
}
const user = await response.json();
```

### Request, Response, Headers

```javascript
// Создание Request объекта
const request = new Request('https://api.example.com/data', {
    method: 'GET',
    headers: new Headers({
        'Accept': 'application/json',
        'X-API-Key': 'secret'
    }),
    credentials: 'include',  // отправлять cookies
    cache: 'no-cache'
});

// Отправка Request объекта
const response = await fetch(request);

// Работа с Headers
const headers = response.headers;
console.log(headers.get('Content-Type'));  // 'application/json'
console.log(headers.get('X-Rate-Limit'));

for (const [key, value] of headers.entries()) {
    console.log(`${key}: ${value}`);
}
```

### Streaming тела ответа

```javascript
// Чтение большого ответа по чанкам (streaming)
async function downloadLargeFile(url) {
    const response = await fetch(url);
    const reader = response.body.getReader();
    const contentLength = response.headers.get('Content-Length');
    
    let receivedLength = 0;
    const chunks = [];
    
    while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        chunks.push(value);
        receivedLength += value.length;
        
        const progress = (receivedLength / contentLength * 100).toFixed(1);
        console.log(`Downloaded: ${progress}%`);
    }
    
    // Склеиваем чанки
    const blob = new Blob(chunks);
    return blob;
}

// Streaming ответа (Server-Sent Events через fetch)
async function* streamingFetch(url) {
    const response = await fetch(url);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Последняя незавершённая строка
        
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                yield JSON.parse(line.slice(6));
            }
        }
    }
}
```

### AbortController: отмена запросов

```javascript
// Отмена fetch запроса
const controller = new AbortController();
const { signal } = controller;

// Запрос с возможностью отмены
const promise = fetch('https://api.example.com/slow-endpoint', { signal });

// Отмена через 5 секунд
setTimeout(() => controller.abort(), 5000);

try {
    const response = await promise;
    const data = await response.json();
} catch (error) {
    if (error.name === 'AbortError') {
        console.log('Запрос отменён');
    } else {
        throw error;
    }
}

// Практическое использование: отмена при смене маршрута
class ApiClient {
    #currentController = null;
    
    async fetchData(url) {
        // Отменяем предыдущий запрос
        this.#currentController?.abort();
        this.#currentController = new AbortController();
        
        return fetch(url, { signal: this.#currentController.signal });
    }
}
```

### Fetch vs XHR

| Аспект | Fetch | XMLHttpRequest |
|---|---|---|
| API | Promise-based | Callback-based |
| Прогресс загрузки | Только через ReadableStream | Встроенный progress event |
| Отмена | AbortController | xhr.abort() |
| Credentials | Явное `credentials: 'include'` | По умолчанию включены |
| Service Workers | Да | Нет |
| Streaming | Да (ReadableStream) | Нет |

## CORS: Cross-Origin Resource Sharing

CORS — механизм безопасности, ограничивающий запросы к другому домену.

### Same-Origin Policy

```
Запрос с https://example.com:
    К https://example.com/api      → OK (same origin)
    К https://api.example.com/data → CORS! (другой subdomain)
    К https://other.com/data       → CORS! (другой домен)
    К http://example.com/api       → CORS! (другой протокол)
    К https://example.com:8080/api → CORS! (другой порт)
```

### Простые запросы vs Preflight

**Простые запросы** (GET, POST с определёнными Content-Type) отправляются напрямую с заголовком Origin:

```
Request:
GET /api/data HTTP/1.1
Host: api.otherdomain.com
Origin: https://example.com

Response (если сервер разрешает):
Access-Control-Allow-Origin: https://example.com
```

**Preflight** (сложные запросы — PUT, DELETE, нестандартные заголовки):

```
1. Preflight (OPTIONS):
OPTIONS /api/data HTTP/1.1
Host: api.otherdomain.com
Origin: https://example.com
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: X-Custom-Header

2. Ответ на preflight:
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://example.com
Access-Control-Allow-Methods: GET, POST, DELETE
Access-Control-Allow-Headers: X-Custom-Header
Access-Control-Max-Age: 86400  (кешировать preflight 24 часа)

3. Реальный запрос:
DELETE /api/data HTTP/1.1
...
```

```javascript
// На сервере (Node.js / Express):
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', 'https://example.com');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
    res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    
    if (req.method === 'OPTIONS') {
        res.status(204).end();
        return;
    }
    next();
});
```

## WebSocket: двусторонняя связь

WebSocket обеспечивает постоянное двустороннее соединение между браузером и сервером.

### Handshake

```
Клиент → Сервер:
GET /ws HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13

Сервер → Клиент:
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

После handshake соединение переходит в WebSocket-протокол (не HTTP!).

### WebSocket API

```javascript
// Создание WebSocket соединения
const ws = new WebSocket('wss://echo.websocket.org');
// ws:// — не шифрованный (не использовать в production!)
// wss:// — WebSocket Secure (TLS)

ws.onopen = () => {
    console.log('Соединение установлено');
    ws.send(JSON.stringify({ type: 'hello', message: 'World' }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Получено:', data);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
    console.log('Соединение закрыто:', event.code, event.reason);
    // Автоматическое переподключение
    setTimeout(connect, 1000);
};

// Закрытие
ws.close(1000, 'Normal closure');
```

### Heartbeat/Ping-Pong

```javascript
// Поддержание соединения и обнаружение разрывов
class WebSocketClient {
    #ws = null;
    #heartbeatInterval = null;
    
    connect(url) {
        this.#ws = new WebSocket(url);
        this.#ws.onopen = () => this.#startHeartbeat();
        this.#ws.onclose = () => this.#stopHeartbeat();
        this.#ws.onmessage = (e) => this.#handleMessage(e);
    }
    
    #startHeartbeat() {
        this.#heartbeatInterval = setInterval(() => {
            if (this.#ws.readyState === WebSocket.OPEN) {
                this.#ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000); // каждые 30 секунд
    }
    
    #stopHeartbeat() {
        clearInterval(this.#heartbeatInterval);
    }
    
    #handleMessage(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'pong') return; // Игнорируем pong
        // Обрабатываем реальные данные
    }
}
```

### WebSocket vs Server-Sent Events vs Polling

| Метод | Направление | Протокол | Когда использовать |
|---|---|---|---|
| Polling | Server→Client | HTTP | Устаревший, редко |
| Long Polling | Server→Client | HTTP | Совместимость |
| SSE | Server→Client | HTTP | Уведомления, feed |
| WebSocket | Двустороннее | WS | Чат, игры, коллаборация |

Server-Sent Events (SSE) — более простая альтернатива для однонаправленного потока:

```javascript
// Server-Sent Events
const eventSource = new EventSource('/api/events');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Event:', data);
};

eventSource.addEventListener('user_joined', (event) => {
    console.log('New user:', event.data);
});

eventSource.onerror = () => {
    // SSE автоматически переподключается!
};
```

## Web Workers: параллельные вычисления

Web Workers позволяют выполнять тяжёлые вычисления в фоновом потоке, не блокируя UI.

### Основы Web Workers

```javascript
// main.js: создаём Worker
const worker = new Worker('/worker.js');

// Отправляем задачу
worker.postMessage({
    type: 'COMPUTE_PRIMES',
    upTo: 1000000
});

// Получаем результат
worker.onmessage = (event) => {
    const { primes } = event.data;
    displayResults(primes);
};

worker.onerror = (error) => {
    console.error('Worker error:', error.message);
};

// worker.js: код воркера
self.onmessage = (event) => {
    const { type, upTo } = event.data;
    
    if (type === 'COMPUTE_PRIMES') {
        const primes = computePrimesUpTo(upTo); // может занять секунды
        
        // Отправляем результат обратно
        self.postMessage({ primes });
    }
};

function computePrimesUpTo(n) {
    const sieve = new Uint8Array(n + 1).fill(1);
    sieve[0] = sieve[1] = 0;
    for (let i = 2; i * i <= n; i++) {
        if (sieve[i]) {
            for (let j = i * i; j <= n; j += i) sieve[j] = 0;
        }
    }
    return Array.from(sieve.entries())
        .filter(([, isPrime]) => isPrime)
        .map(([n]) => n);
}
```

### Transferable Objects: передача без копирования

По умолчанию `postMessage` копирует данные. Для больших объектов используйте Transferable Objects:

```javascript
// Создаём большой ArrayBuffer
const buffer = new ArrayBuffer(100 * 1024 * 1024); // 100 MB

// МЕДЛЕННО: копирует 100 MB
worker.postMessage({ data: buffer });

// БЫСТРО: передаёт владение (buffer становится недоступен в main thread)
worker.postMessage({ data: buffer }, [buffer]);
// После этого: buffer.byteLength === 0 (передан воркеру)
```

### SharedArrayBuffer и Atomics

```javascript
// Разделяемая память между main thread и worker
const sharedBuffer = new SharedArrayBuffer(4);
const sharedArray = new Int32Array(sharedBuffer);

// Main thread
worker.postMessage({ buffer: sharedBuffer });

Atomics.store(sharedArray, 0, 42);  // Атомарная запись
const value = Atomics.load(sharedArray, 0);  // Атомарное чтение

// Worker может читать те же данные без копирования!

// Синхронизация (mutex-like через Atomics.wait/notify):
// Worker:
Atomics.wait(sharedArray, 0, 0);  // Ожидать пока sharedArray[0] != 0
// ...работа...

// Main thread:
Atomics.notify(sharedArray, 0, 1);  // Разбудить одного ожидающего
```

Важно: `SharedArrayBuffer` требует COOP/COEP HTTP-заголовков для безопасности (защита от Spectre):

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

## Service Workers

Service Worker — прокси между страницей и сетью. Он перехватывает запросы, кеширует ресурсы, работает оффлайн. (Подробнее в предыдущей статье о CRP.)

### Background Sync

```javascript
// service-worker.js
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-messages') {
        event.waitUntil(syncPendingMessages());
    }
});

async function syncPendingMessages() {
    const db = await openIndexedDB();
    const pending = await db.getAll('pending_messages');
    
    for (const message of pending) {
        await fetch('/api/messages', {
            method: 'POST',
            body: JSON.stringify(message)
        });
        await db.delete('pending_messages', message.id);
    }
}

// main.js: регистрация sync
async function sendMessage(message) {
    try {
        // Попробовать отправить сразу
        await fetch('/api/messages', { method: 'POST', body: JSON.stringify(message) });
    } catch {
        // Оффлайн: сохранить для синхронизации
        const db = await openIndexedDB();
        await db.put('pending_messages', message);
        
        const registration = await navigator.serviceWorker.ready;
        await registration.sync.register('sync-messages');
    }
}
```

### Push Notifications

```javascript
// main.js: подписка на push
const registration = await navigator.serviceWorker.ready;
const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
});

// Отправить subscription на сервер
await fetch('/api/push/subscribe', {
    method: 'POST',
    body: JSON.stringify(subscription)
});

// service-worker.js: обработка push
self.addEventListener('push', (event) => {
    const data = event.data.json();
    
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/icon.png',
            badge: '/badge.png',
            data: { url: data.url }
        })
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(clients.openWindow(event.notification.data.url));
});
```

## IndexedDB: клиентская база данных

IndexedDB — полноценная нереляционная база данных в браузере. Поддерживает транзакции, индексы, курсоры, несколько хранилищ объектов.

### Основы IndexedDB

```javascript
// Открытие / создание базы данных
function openDB(name, version, upgradeCallback) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(name, version);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
        
        // Вызывается при создании или обновлении версии
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            upgradeCallback(db, event.oldVersion, event.newVersion);
        };
    });
}

// Инициализация схемы
const db = await openDB('my-app', 1, (db, oldVersion, newVersion) => {
    if (oldVersion < 1) {
        // Создаём хранилище объектов (аналог таблицы)
        const userStore = db.createObjectStore('users', { 
            keyPath: 'id',
            autoIncrement: true 
        });
        
        // Создаём индексы для быстрого поиска
        userStore.createIndex('email', 'email', { unique: true });
        userStore.createIndex('age', 'age', { unique: false });
        
        db.createObjectStore('messages', { keyPath: 'id' });
    }
    
    if (oldVersion < 2) {
        // Миграция: добавить новое хранилище
        db.createObjectStore('settings', { keyPath: 'key' });
    }
});
```

### CRUD операции

```javascript
// Утилиты для работы с промисами
function dbRequest(request) {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// Create (добавить)
async function addUser(db, user) {
    const tx = db.transaction('users', 'readwrite');
    const store = tx.objectStore('users');
    const id = await dbRequest(store.add(user));
    return id;
}

// Read (получить по ключу)
async function getUser(db, id) {
    const tx = db.transaction('users', 'readonly');
    const store = tx.objectStore('users');
    return dbRequest(store.get(id));
}

// Read by index
async function getUserByEmail(db, email) {
    const tx = db.transaction('users', 'readonly');
    const index = tx.objectStore('users').index('email');
    return dbRequest(index.get(email));
}

// Update
async function updateUser(db, user) {
    const tx = db.transaction('users', 'readwrite');
    const store = tx.objectStore('users');
    await dbRequest(store.put(user)); // put = upsert
}

// Delete
async function deleteUser(db, id) {
    const tx = db.transaction('users', 'readwrite');
    const store = tx.objectStore('users');
    await dbRequest(store.delete(id));
}

// Get All
async function getAllUsers(db) {
    const tx = db.transaction('users', 'readonly');
    const store = tx.objectStore('users');
    return dbRequest(store.getAll());
}

// Range query (например, все пользователи с age >= 18)
async function getAdults(db) {
    const tx = db.transaction('users', 'readonly');
    const index = tx.objectStore('users').index('age');
    const range = IDBKeyRange.lowerBound(18); // age >= 18
    return dbRequest(index.getAll(range));
}
```

### Транзакции

```javascript
// Несколько операций в одной транзакции
async function transferCredits(db, fromUserId, toUserId, amount) {
    return new Promise((resolve, reject) => {
        const tx = db.transaction('users', 'readwrite');
        const store = tx.objectStore('users');
        
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(new Error('Transaction aborted'));
        
        const fromRequest = store.get(fromUserId);
        fromRequest.onsuccess = () => {
            const from = fromRequest.result;
            if (from.credits < amount) {
                tx.abort(); // Откатываем всю транзакцию
                return;
            }
            from.credits -= amount;
            store.put(from);
            
            const toRequest = store.get(toUserId);
            toRequest.onsuccess = () => {
                const to = toRequest.result;
                to.credits += amount;
                store.put(to);
            };
        };
    });
}
```

### idb: обёртка над IndexedDB

Работать с сырым IndexedDB громоздко. Библиотека `idb` (от Jake Archibald) делает API promise-based:

```javascript
import { openDB } from 'idb';

const db = await openDB('my-app', 1, {
    upgrade(db) {
        const store = db.createObjectStore('notes', { keyPath: 'id', autoIncrement: true });
        store.createIndex('timestamp', 'timestamp');
    }
});

// Намного чище!
await db.add('notes', { text: 'Hello', timestamp: Date.now() });
const note = await db.get('notes', 1);
const allNotes = await db.getAll('notes');
await db.delete('notes', 1);

// Транзакция
const tx = db.transaction('notes', 'readwrite');
await tx.store.add({ text: 'Note 1', timestamp: Date.now() });
await tx.store.add({ text: 'Note 2', timestamp: Date.now() });
await tx.done;
```

## Сравнение хранилищ

| Storage | Объём | Синхронный | Транзакции | Offline |
|---|---|---|---|---|
| localStorage | ~5 MB | Да (блокирует!) | Нет | Да |
| sessionStorage | ~5 MB | Да (блокирует!) | Нет | Сессия |
| Cookie | ~4 KB | Да | Нет | Да |
| IndexedDB | Сотни MB/GB | Нет (async) | Да | Да |
| Cache API | Зависит от диска | Нет (async) | Нет | Да |

**Рекомендации:**
- **localStorage**: простые строковые данные, синхронный доступ, малый объём
- **sessionStorage**: временные данные, только для текущей вкладки
- **IndexedDB**: структурированные данные, большой объём, оффлайн
- **Cache API**: HTTP-ответы (через Service Worker)

## Итог

Современные Web APIs превращают браузер в полноценную application platform:

1. **Fetch API** — чистый promise-based HTTP с streaming и отменой
2. **CORS** — браузерная защита same-origin, prelight для сложных запросов
3. **WebSocket** — full-duplex для реального времени (чат, игры)
4. **SSE** — однонаправленный поток событий сервера
5. **Web Workers** — параллельные CPU-heavy вычисления
6. **Service Workers** — оффлайн, кеширование, push-уведомления
7. **IndexedDB** — клиентская БД с транзакциями для больших объёмов данных

## Литература

1. MDN Web Docs. *Fetch API*. https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API

2. Archibald, J. (2015). *That's so fetch!* https://jakearchibald.com/2015/thats-so-fetch/

3. WHATWG. *Fetch Living Standard*. https://fetch.spec.whatwg.org/

4. MDN Web Docs. *WebSocket API*. https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

5. Fette, I., Melnikov, A. (2011). *The WebSocket Protocol*. RFC 6455. IETF. https://tools.ietf.org/html/rfc6455

6. MDN Web Docs. *Web Workers API*. https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API

7. MDN Web Docs. *IndexedDB API*. https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API

8. Archibald, J. *idb — A little wrapper that makes IndexedDB usable*. https://github.com/jakearchibald/idb

9. W3C. *IndexedDB 2.0 Specification*. https://www.w3.org/TR/IndexedDB-2/

10. MDN Web Docs. *Service Worker API*. https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API

11. W3C. *Cross-Origin Resource Sharing (CORS)*. https://fetch.spec.whatwg.org/#http-cors-protocol
