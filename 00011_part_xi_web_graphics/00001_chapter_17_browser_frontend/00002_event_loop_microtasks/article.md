# Event Loop, Microtasks и Macrotasks: почему setTimeout(fn, 0) не «сразу»

Новички в JavaScript часто натыкаются на один и тот же сюрприз: код, написанный первым, выполняется последним. Почему `console.log` после `setTimeout(fn, 0)` печатается раньше, чем сам callback? Почему Promise выполняется раньше setTimeout? Ответы на эти вопросы лежат в архитектуре JavaScript runtime — Event Loop с очередями macrotask и microtask.

## Однопоточность JavaScript

JavaScript является однопоточным языком. Это означает, что в один момент времени выполняется только один кусок кода. Нет параллельных потоков (если не считать Web Workers), нет race conditions на уровне JS-кода.

Это радикально упрощает программирование: не нужны мьютексы, не нужно думать о синхронизации общих данных. Но есть цена — любая долгая операция блокирует всё.

```javascript
// Блокировка event loop — ПЛОХО
function fibonacci(n) {
    if (n <= 1) return n;
    return fibonacci(n - 1) + fibonacci(n - 2);
}

// Это заблокирует браузер на несколько секунд!
console.log(fibonacci(45)); // ~3.5 миллиарда рекурсивных вызовов
```

## Call Stack: стек вызовов

Call stack (стек вызовов) — это структура данных, отслеживающая, какая функция выполняется прямо сейчас.

```javascript
function greet(name) {
    return `Hello, ${name}!`;
}

function main() {
    const result = greet('World');
    console.log(result);
}

main();
```

```
Состояния стека:
1. []                    → main() вызван
2. [main]               → greet() вызван из main()  
3. [main, greet]        → greet завершился, возвращает значение
4. [main]               → console.log() вызван
5. [main, console.log]  → console.log завершился
6. [main]               → main завершился
7. []                   → стек пуст
```

Когда стек пуст, JavaScript не делает ничего. Именно здесь в игру вступает Event Loop.

## Web APIs: операции вне JavaScript

Браузер предоставляет Web APIs — интерфейсы для асинхронных операций. Они реализованы на C++ внутри браузера, а не в JavaScript. Когда вы вызываете:

```javascript
setTimeout(callback, 1000);
fetch('https://api.example.com/data');
element.addEventListener('click', handler);
```

— вы передаёте браузеру задачу. JavaScript не ждёт — он продолжает выполнение следующих строк. Когда Web API завершает работу, он помещает callback в очередь.

```
JavaScript Engine                  Browser Web APIs
┌─────────────────┐               ┌──────────────────┐
│   Call Stack    │               │  setTimeout      │
│   ─────────     │               │  fetch           │
│   main()        │──────────────>│  DOM Events      │
│                 │               │  Geolocation     │
└─────────────────┘               └──────────────────┘
         ↑                                 │
         │                                 ▼
┌─────────────────┐               ┌──────────────────┐
│   Event Loop    │               │  Callback Queue  │
│                 │<──────────────│  (Macrotask)     │
└─────────────────┘               └──────────────────┘
```

## Macrotask Queue (Callback Queue)

Macrotask queue — это очередь FIFO (First In, First Out), в которую помещаются:
- Callbacks из `setTimeout` и `setInterval`
- DOM события (click, load, etc.)
- I/O callbacks
- `MessageChannel` messages

Event Loop работает просто: когда call stack пуст, берёт **одну** macrotask из очереди и выполняет её.

```javascript
console.log('1'); // Синхронно, сразу в стек

setTimeout(() => {
    console.log('3'); // Macrotask, выполнится позже
}, 0);

console.log('2'); // Синхронно, сразу в стек

// Вывод:
// 1
// 2
// 3
```

Почему `3` последним, если таймаут 0 миллисекунд? Потому что `setTimeout` помещает callback в macrotask queue. Прежде чем Event Loop возьмёт его оттуда, текущий синхронный код (строки 1 и 4) должен завершиться полностью.

## Microtask Queue: высокоприоритетная очередь

Microtask queue — вторая очередь с более высоким приоритетом, чем macrotask. В неё попадают:
- `Promise.then()`, `Promise.catch()`, `Promise.finally()`
- `queueMicrotask(fn)`
- `MutationObserver` callbacks
- `await` в async функциях (раскрывается в `.then()`)

**Ключевое правило**: после каждой macrotask (и после синхронного кода) браузер **полностью опустошает** microtask queue, прежде чем взять следующую macrotask.

```
Event Loop цикл:
1. Выполнить текущий synchronous код
2. Опустошить microtask queue (все microtasks!)
3. Взять ОДНУ macrotask из macrotask queue
4. Снова опустошить microtask queue
5. Render (если нужно)
6. GOTO 1
```

```javascript
console.log('1'); // Sync

setTimeout(() => console.log('Macrotask'), 0);

Promise.resolve()
    .then(() => console.log('Microtask 1'))
    .then(() => console.log('Microtask 2'));

queueMicrotask(() => console.log('Microtask 3'));

console.log('2'); // Sync

// Вывод:
// 1
// 2
// Microtask 1  ← microtasks выполняются до macrotask
// Microtask 2  ← "цепочка" тоже microtask (второй .then)
// Microtask 3  ← queueMicrotask
// Macrotask    ← setTimeout выполняется последним
```

## Детальный разбор Promise и async/await

```javascript
console.log('start');

async function asyncFunction() {
    console.log('async start');      // Синхронно!
    
    await Promise.resolve();         // Создаёт microtask
    
    console.log('after await 1');    // В microtask queue
    
    await new Promise(resolve => {
        setTimeout(resolve, 0);      // Macrotask!
    });
    
    console.log('after await 2');    // В microtask queue после macrotask
}

asyncFunction();

console.log('end');

// Вывод:
// start
// async start    ← синхронная часть async функции
// end            ← продолжение синхронного кода после вызова asyncFunction()
// after await 1  ← microtask (await Promise.resolve())
// after await 2  ← microtask, но ПОСЛЕ macrotask от setTimeout
```

### Разбор async/await через Promise

`async/await` — синтаксический сахар над Promise. Вот как это раскрывается:

```javascript
// Оригинал
async function fetchData() {
    const response = await fetch('/api/data');
    const json = await response.json();
    return json;
}

// Эквивалент (упрощённо)
function fetchData() {
    return fetch('/api/data')
        .then(response => response.json())
        .then(json => json);
}
```

Каждый `await` разрезает функцию на части. Всё после `await` становится `.then()` callback — microtask.

## Порядок выполнения: детальный пример

```javascript
// Сложный пример — предсказайте порядок вывода

console.log('1');

setTimeout(() => {
    console.log('2');
    Promise.resolve().then(() => console.log('3'));
}, 0);

Promise.resolve()
    .then(() => {
        console.log('4');
        setTimeout(() => console.log('5'), 0);
    })
    .then(() => console.log('6'));

console.log('7');

// Вывод:
// 1  — sync
// 7  — sync
// 4  — microtask (первый .then)
// 6  — microtask (второй .then, добавился в очередь после выполнения 4)
// 2  — macrotask (первый setTimeout)
// 3  — microtask внутри macrotask (опустошается перед следующей macrotask)
// 5  — macrotask (второй setTimeout, добавлен в шаге 4)
```

Разбор:
1. `1`, `7` — синхронный код
2. Microtask queue: `[then(4)]`
3. Выполняем `then(4)` → печатаем `4`, добавляем `setTimeout(5)` в macrotask queue, добавляем `then(6)` в microtask queue
4. Microtask queue: `[then(6)]`  
5. Выполняем `then(6)` → печатаем `6`
6. Microtask queue пуста. Берём macrotask: `setTimeout(2)`
7. Печатаем `2`, добавляем `then(3)` в microtask queue
8. Opустошаем microtask: печатаем `3`
9. Берём macrotask: `setTimeout(5)`, печатаем `5`

## requestAnimationFrame

`requestAnimationFrame` (rAF) — особый тип callback для анимаций. Он не является ни macrotask, ни microtask в строгом смысле — он выполняется перед каждым кадром отрисовки.

```
Event Loop с рендерингом:
1. Microtask queue (опустошить)
2. Macrotask (одну)
3. Microtask queue (опустошить)
4. requestAnimationFrame callbacks
5. Layout → Paint → Composite (если нужно)
6. GOTO 1
```

```javascript
// requestAnimationFrame для плавной анимации
let start;
function animate(timestamp) {
    if (!start) start = timestamp;
    const elapsed = timestamp - start;
    
    // Перемещаем элемент
    element.style.transform = `translateX(${elapsed * 0.1}px)`;
    
    // Регистрируем следующий кадр
    if (elapsed < 2000) {
        requestAnimationFrame(animate);
    }
}

requestAnimationFrame(animate);
```

rAF гарантирует синхронизацию с частотой экрана (60 fps = каждые ~16.67 мс, 144 fps = каждые ~6.94 мс).

## Блокировка Event Loop: реальные последствия

```javascript
// Симуляция тяжёлой работы, блокирующей UI
function blockEventLoop() {
    const end = Date.now() + 5000; // 5 секунд
    while (Date.now() < end) {
        // Занимаемся ничегонеделанием
    }
}

document.getElementById('btn').addEventListener('click', () => {
    blockEventLoop();
    // Всё время выполнения: UI заморожен, клики не обрабатываются,
    // анимации остановлены, fetch callbacks не вызываются
});
```

Симптомы заблокированного event loop:
- Браузер "зависает", не реагирует на клики
- Анимации замирают
- `setTimeout` callbacks не выполняются
- Chrome DevTools показывает "Long Task" (задача > 50 мс)

## Решение: дробление тяжёлой работы

```javascript
// Плохо: блокирует UI
function processItems(items) {
    for (const item of items) {
        heavyProcess(item);
    }
}

// Хорошо: разбиваем на чанки
async function processItemsAsync(items) {
    const CHUNK_SIZE = 100;
    
    for (let i = 0; i < items.length; i += CHUNK_SIZE) {
        const chunk = items.slice(i, i + CHUNK_SIZE);
        
        // Обрабатываем чанк
        for (const item of chunk) {
            heavyProcess(item);
        }
        
        // Отдаём управление event loop (macrotask)
        await new Promise(resolve => setTimeout(resolve, 0));
        // Или через scheduler API (более правильно)
        // await scheduler.yield();
    }
}

// scheduler.yield() — современный API (Chrome 115+)
async function processWithScheduler(items) {
    for (const item of items) {
        heavyProcess(item);
        
        // Каждую итерацию спрашиваем: "нужно ли уступить?"
        if (navigator.scheduling?.isInputPending()) {
            await scheduler.yield();
        }
    }
}
```

## Web Workers: параллельность без Event Loop

Web Workers — единственный способ истинной параллельности в JavaScript. Worker выполняется в отдельном потоке со своим event loop.

```javascript
// main.js
const worker = new Worker('worker.js');

worker.postMessage({ 
    type: 'HEAVY_CALCULATION', 
    data: largeArray 
});

worker.onmessage = (event) => {
    console.log('Результат:', event.data.result);
    // UI не был заблокирован!
};

// worker.js
self.onmessage = (event) => {
    if (event.data.type === 'HEAVY_CALCULATION') {
        // Тяжёлые вычисления — не блокируют основной поток
        const result = fibonacci(event.data.data);
        
        // Отправляем результат обратно
        self.postMessage({ result });
    }
};
```

Worker не имеет доступа к DOM. Коммуникация только через `postMessage` — копирование данных (или передача через Transferable для нулевого копирования).

```javascript
// SharedArrayBuffer: разделяемая память между потоками
// Требует COOP/COEP заголовки безопасности

const buffer = new SharedArrayBuffer(1024);
const array = new Int32Array(buffer);

// В Worker'е можно безопасно читать и писать через Atomics
Atomics.add(array, 0, 1);   // Атомарное сложение
Atomics.load(array, 0);     // Атомарное чтение
Atomics.wait(array, 0, 0);  // Ожидание изменения
```

## Node.js Event Loop: отличия от браузера

Node.js использует libuv для реализации event loop. Он более сложен, чем браузерный, с несколькими очередями:

```
Node.js Event Loop (упрощённо):

Phase 1: timers        → setTimeout, setInterval callbacks
Phase 2: I/O callbacks → большинство async I/O callbacks
Phase 3: idle, prepare → internal use
Phase 4: poll          → ожидание новых I/O событий
Phase 5: check         → setImmediate callbacks
Phase 6: close callbacks → 'close' events

После каждой фазы: microtasks (Promise.then) + process.nextTick()
```

```javascript
// Node.js: порядок выполнения
const { setImmediate } = require('timers');

setTimeout(() => console.log('setTimeout'), 0);
setImmediate(() => console.log('setImmediate'));
process.nextTick(() => console.log('nextTick'));
Promise.resolve().then(() => console.log('Promise'));

// Вывод (в Node.js):
// nextTick     ← process.nextTick имеет НАИВЫСШИЙ приоритет
// Promise      ← microtask
// setTimeout   ← macrotask (timers phase)
// setImmediate ← check phase
```

`process.nextTick` — это специфика Node.js. Он выполняется ещё до microtask queue! Это может привести к бесконечному циклу:

```javascript
// ОПАСНО: бесконечный цикл microtasks, не даёт I/O работать
function infiniteRecursion() {
    process.nextTick(infiniteRecursion);
}
infiniteRecursion(); // Node никогда не перейдёт к I/O
```

## MutationObserver

MutationObserver — механизм наблюдения за изменениями DOM, выполняющийся как microtask:

```javascript
const observer = new MutationObserver((mutations) => {
    // Выполняется как MICROTASK после изменения DOM
    console.log('DOM изменился!', mutations);
});

observer.observe(document.body, {
    childList: true,    // Изменения дочерних элементов
    subtree: true,      // Включая вложенные
    attributes: true,   // Изменения атрибутов
    characterData: true // Изменения текста
});

document.body.appendChild(document.createElement('div'));
// MutationObserver callback будет вызван как microtask
```

## Практические паттерны

### Паттерн: правильный debounce

```javascript
function debounce(fn, delay) {
    let timeoutId;
    return (...args) => {
        // Отменяем предыдущий таймер (macrotask)
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn(...args), delay);
    };
}

// Вызывается максимум раз в 300ms
const onSearch = debounce((query) => {
    fetch(`/api/search?q=${query}`).then(/* ... */);
}, 300);

input.addEventListener('input', (e) => onSearch(e.target.value));
```

### Паттерн: батчинг DOM-операций

```javascript
// ПЛОХО: много reflow (подробнее в следующей статье)
items.forEach(item => {
    document.getElementById('list').appendChild(createItem(item));
});

// ХОРОШО: один reflow
const fragment = document.createDocumentFragment();
items.forEach(item => fragment.appendChild(createItem(item)));
document.getElementById('list').appendChild(fragment);

// ТАКЖЕ ХОРОШО: отложить до следующего кадра
requestAnimationFrame(() => {
    const fragment = document.createDocumentFragment();
    items.forEach(item => fragment.appendChild(createItem(item)));
    document.getElementById('list').appendChild(fragment);
});
```

## Итог

Event Loop — сердце JavaScript runtime. Ключевые выводы:

1. **Call Stack** выполняет синхронный код; при пустом стеке Event Loop берёт следующую задачу
2. **Macrotask queue** (setTimeout, DOM events) — по одной задаче за раз
3. **Microtask queue** (Promise.then, queueMicrotask) — выполняется ЦЕЛИКОМ после каждой macrotask
4. **Порядок**: синхронный код → microtasks → macrotask → microtasks → rAF → render → ...
5. **Web Workers** — единственная настоящая параллельность в JS
6. **Node.js** отличается наличием `process.nextTick` (супер-microtask) и `setImmediate`

Понимание этого объясняет все "загадки" с порядком выполнения промисов, setTimeout и async/await.

## Литература

1. WHATWG. *HTML Living Standard — Event loops*. https://html.spec.whatwg.org/multipage/webappapis.html#event-loops

2. MDN Web Docs. *The event loop*. https://developer.mozilla.org/en-US/docs/Web/JavaScript/Event_loop

3. Archibald, J. (2015). *Tasks, microtasks, queues and schedules*. https://jakearchibald.com/2015/tasks-microtasks-queues-and-schedules/

4. Stefanov, S. (2010). *JavaScript Patterns*. O'Reilly Media.

5. MDN Web Docs. *Using Web Workers*. https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Using_web_workers

6. Node.js. *The Node.js Event Loop, Timers, and process.nextTick()*. https://nodejs.org/en/docs/guides/event-loop-timers-and-nexttick

7. libuv. *Design overview*. https://docs.libuv.org/en/v1.x/design.html

8. TC39. *ECMAScript 2024 Language Specification — Jobs and Host Operations*. https://tc39.es/ecma262/#sec-jobs

9. MDN Web Docs. *MutationObserver*. https://developer.mozilla.org/en-US/docs/Web/API/MutationObserver

10. Google Chrome Team. *Scheduler API (scheduler.yield)*. https://developer.chrome.com/blog/introducing-scheduler-yield-origin-trial
