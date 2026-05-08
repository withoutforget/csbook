# Virtual DOM, реактивность, Fiber: как React и Vue избегают лишних перерисовок

Прямая работа с DOM — медленная. В ранних JavaScript-приложениях это было нормой: каждое изменение данных → явная манипуляция DOM-элементами. React изменил парадигму, предложив декларативный подход: описывай желаемое состояние UI, а не инструкции по его изменению. Под капотом — виртуальный DOM и умный алгоритм обновлений. Но React — не единственный подход. Vue, Svelte и Solid предлагают принципиально разные решения той же проблемы.

## Проблема прямой работы с DOM

Почему прямая работа с DOM медленная? DOM — это "живые" объекты браузера. Каждое обращение к DOM API — это переход из JavaScript-мира в C++-мир браузера (через bridge). Любое изменение может потенциально запустить reflow и repaint.

```javascript
// Наивный подход: перерисовать весь список при изменении
function renderTodos(todos) {
    const list = document.getElementById('todo-list');
    list.innerHTML = ''; // Удаляем всё → reflow
    
    todos.forEach(todo => {
        const li = document.createElement('li');
        li.textContent = todo.text;
        li.style.textDecoration = todo.done ? 'line-through' : '';
        list.appendChild(li); // Отдельный reflow для каждого!
    });
}

// При изменении одного пункта — перерисовываем всё!
todos.push({ text: 'New task', done: false });
renderTodos(todos); // 100 reflow вместо 1
```

Проблема: при изменении одного элемента в списке из 100 элементов мы уничтожаем и создаём 100 DOM-узлов. Это медленно и разрушает state браузера (cursor position, scroll position, focus, CSS animations).

## Virtual DOM: концепция

Virtual DOM (VDOM) — это лёгкая JavaScript-копия DOM-дерева. Вместо работы с "тяжёлыми" DOM-объектами, React создаёт простые JavaScript-объекты:

```javascript
// Реальный DOM-объект: тысячи свойств, методы, связи с C++
const domElement = document.createElement('div');
// domElement имеет ~300+ свойств!

// Virtual DOM-объект: только то, что нужно
const vdomElement = {
    type: 'div',
    props: {
        className: 'container',
        children: [
            {
                type: 'h1',
                props: { children: 'Hello World' }
            },
            {
                type: 'p',
                props: { children: 'Paragraph' }
            }
        ]
    }
};
```

JSX — синтаксический сахар, компилирующийся в вызовы `React.createElement`:

```jsx
// JSX
const element = (
    <div className="container">
        <h1>Hello World</h1>
        <p>Paragraph</p>
    </div>
);

// Компилируется в:
const element = React.createElement(
    'div',
    { className: 'container' },
    React.createElement('h1', null, 'Hello World'),
    React.createElement('p', null, 'Paragraph')
);
```

## Reconciliation: алгоритм сравнения

Reconciliation — процесс сравнения старого и нового Virtual DOM и применения минимального набора изменений к реальному DOM.

### Наивный подход: $O(n^3)$

Теоретически оптимальный алгоритм сравнения двух деревьев имеет сложность $O(n^3)$. Для дерева из 1000 элементов это $10^9$ операций — катастрофически медленно.

### Алгоритм React: O(n) через эвристики

React использует две ключевые эвристики, снижающие сложность до O(n):

#### Эвристика 1: Разные типы → перестроить поддерево

Если тип элемента изменился (например, `<div>` стал `<span>`), React **не пытается** сохранить дочерние элементы — он уничтожает старое поддерево и создаёт новое:

```jsx
// Было:
<div className="box">
    <Counter /> {/* Это состояние будет уничтожено */}
</div>

// Стало:
<span className="box">
    <Counter /> {/* Это НОВЫЙ Counter, без предыдущего состояния */}
</span>
```

#### Эвристика 2: Дочерние элементы по индексу, если нет key

```jsx
// Без key — React сравнивает по позиции:
// Было:
<ul>
    <li>Apple</li>   {/* позиция 0 */}
    <li>Banana</li>  {/* позиция 1 */}
</ul>

// Стало (добавили в начало):
<ul>
    <li>Orange</li>  {/* позиция 0 — React думает, что Apple → Orange */}
    <li>Apple</li>   {/* позиция 1 — думает, что Banana → Apple */}
    <li>Banana</li>  {/* позиция 2 — думает, что это новый элемент */}
</ul>
// React изменит текст первых двух и добавит третий — неоптимально!
```

### Keys: помощь алгоритму

Keys позволяют React отслеживать идентичность элементов:

```jsx
// С key — React правильно понимает перемещение
<ul>
    {fruits.map(fruit => (
        <li key={fruit.id}>{fruit.name}</li>
    ))}
</ul>

// При добавлении в начало:
// React видит: fruit.id=2 переместился с позиции 1 на 2,
// fruit.id=1 переместился с 0 на 1, fruit.id=3 — новый элемент
// Результат: перемещение DOM-узлов + добавление одного нового
```

**Ошибки с keys:**

```jsx
// НЕПРАВИЛЬНО: key из индекса массива при перемещениях
{items.map((item, index) => (
    <Item key={index} {...item} />
))}
// При перестановке элементов — те же проблемы, что без key!

// ПРАВИЛЬНО: стабильный уникальный идентификатор
{items.map(item => (
    <Item key={item.id} {...item} />
))}
```

## React Fiber: incremental rendering

React 16 (2017) полностью переписал reconciliation алгоритм — представив React Fiber.

### Проблема старого стека

Старый React reconciler ("Stack Reconciler") работал как обычный рекурсивный обход дерева. Если дерево большое — вся работа делалась **синхронно**, блокируя event loop:

```
Старый React:
────────────────────────────────────────────────────
Reconcile начинается ────────────────────► Commit
   Нельзя прервать!   ~100ms синхронной работы
────────────────────────────────────────────────────
    ↑
    Браузер не может отрисовать кадр, обработать клик, запустить CSS-анимацию
```

### Fiber: делаем работу прерываемой

Fiber превращает reconciliation в прерываемый инкрементальный процесс. Ключевые концепции:

**Fiber node** — объект, представляющий единицу работы:

```javascript
// Упрощённая структура Fiber node
const fiber = {
    type: MyComponent,
    key: null,
    stateNode: null,    // DOM-узел или экземпляр компонента
    
    // Указатели для обхода
    child: firstChildFiber,
    sibling: nextSiblingFiber,
    return: parentFiber, // родительский fiber
    
    // Изменения для применения
    effectTag: UPDATE,  // что нужно сделать с DOM
    
    // Работа
    pendingProps: newProps,
    memoizedProps: oldProps,
    
    // Приоритет
    lanes: SomePriorityLane,
};
```

**Две фазы работы:**

```
Phase 1: Render/Reconciliation (прерываемая)
    → Строит "work-in-progress" дерево
    → Можно прервать в любой момент
    → Браузер может обработать высокоприоритетные события

Phase 2: Commit (синхронная, нельзя прерывать)
    → Применяет изменения к реальному DOM
    → Обычно очень быстрая (только минимальные изменения)
```

### Приоритеты в Fiber

Fiber назначает приоритеты обновлениям:

```javascript
// В React используется система "lanes" (дорожки)
// Упрощённые приоритеты:

// Немедленно (клики, вводимые символы)
flushSync(() => setState(value));  // Синхронно, нельзя прервать

// Нормальный приоритет (стандартные setState)
setState(value);

// Низкий приоритет (данные от сервера, не срочные)
startTransition(() => {
    setState(value);  // Может прерваться для более важного
});
```

### Concurrent Mode и Time Slicing

```jsx
// Concurrent Mode: React 18+
import { createRoot } from 'react-dom/client';
const root = createRoot(document.getElementById('root'));
root.render(<App />);

// startTransition: пометить обновление как "не срочное"
import { useState, startTransition } from 'react';

function SearchResults({ query }) {
    const [results, setResults] = useState([]);
    
    function handleInput(e) {
        // Обновление input — срочное (пользователь видит ввод)
        setInputValue(e.target.value);
        
        // Обновление результатов — несрочное
        startTransition(() => {
            setResults(filterResults(allItems, e.target.value));
        });
    }
    // ...
}
```

### Suspense

Suspense позволяет "приостановить" рендеринг компонента, пока не загрузятся данные:

```jsx
// Lazy loading компонента
const HeavyComponent = React.lazy(() => import('./HeavyComponent'));

function App() {
    return (
        <Suspense fallback={<div>Загрузка...</div>}>
            <HeavyComponent />
        </Suspense>
    );
}

// Data fetching с Suspense (React 18+ / Relay / SWR)
function UserProfile({ userId }) {
    // Этот хук "приостанавливает" рендеринг если данные не готовы
    const user = use(fetchUser(userId));
    return <div>{user.name}</div>;
}

function App() {
    return (
        <Suspense fallback={<Skeleton />}>
            <UserProfile userId={1} />
        </Suspense>
    );
}
```

## Vue 3: реактивность на основе Proxy

Vue 3 использует принципиально другой подход — fine-grained reactivity через JavaScript Proxy.

### Reactive объекты

```javascript
import { reactive, ref, computed, watch } from 'vue';

// reactive: для объектов
const state = reactive({
    count: 0,
    name: 'Vue'
});

// ref: для примитивов (оборачивает в { value })
const count = ref(0);
console.log(count.value); // 0
count.value++; // Изменение отслеживается!

// computed: кешированное вычисляемое значение
const doubled = computed(() => count.value * 2);

// watch: реакция на изменения
watch(count, (newVal, oldVal) => {
    console.log(`Изменилось с ${oldVal} до ${newVal}`);
});
```

### Как работает Proxy

Vue 3 использует ES Proxy для перехвата обращений к данным:

```javascript
// Упрощённая реализация реактивности Vue 3
function reactive(target) {
    return new Proxy(target, {
        get(obj, key, receiver) {
            track(obj, key);  // Запомнить: этот эффект зависит от obj[key]
            return Reflect.get(obj, key, receiver);
        },
        set(obj, key, value, receiver) {
            const result = Reflect.set(obj, key, value, receiver);
            trigger(obj, key);  // Уведомить: obj[key] изменился
            return result;
        }
    });
}

// Эффекты
let activeEffect = null;

function watchEffect(fn) {
    activeEffect = fn;
    fn();  // Запускаем, чтобы Proxy зафиксировал зависимости
    activeEffect = null;
}

function track(obj, key) {
    if (activeEffect) {
        // Добавляем текущий эффект в список подписчиков obj[key]
        getSubscribers(obj, key).add(activeEffect);
    }
}

function trigger(obj, key) {
    // Запускаем все эффекты, зависящие от obj[key]
    getSubscribers(obj, key).forEach(effect => effect());
}
```

### Отличие от React

```javascript
// React: нужно явно вызвать setState для запуска обновления
const [count, setCount] = useState(0);
setCount(count + 1); // Явный вызов

// Vue 3: прямое изменение объекта (Proxy перехватит)
const state = reactive({ count: 0 });
state.count++; // Proxy перехватит и вызовет обновление
```

Vue 3 точно знает, какой компонент зависит от какого куска данных, и перерисовывает только его. React без оптимизации (`memo`, `useMemo`, `useCallback`) перерисовывает все дочерние компоненты при изменении родителя.

## Svelte: compile-time реактивность

Svelte — радикально другой подход. Нет Virtual DOM вообще. Svelte компилирует компоненты в **нативный JavaScript**, который обновляет DOM напрямую.

```svelte
<!-- Svelte компонент -->
<script>
    let count = 0;
    
    function increment() {
        count++;  // Компилятор "знает", что это обновляет DOM
    }
    
    $: doubled = count * 2;  // Реактивное объявление
</script>

<button on:click={increment}>
    Clicked {count} times, doubled: {doubled}
</button>
```

Компилируется примерно в:

```javascript
// Упрощённый скомпилированный Svelte
function create_fragment(ctx) {
    let button;
    return {
        c() {  // create
            button = element('button');
        },
        m(target, anchor) {  // mount
            insert(target, button, anchor);
            button.textContent = `Clicked ${ctx[0]} times, doubled: ${ctx[1]}`;
        },
        p(ctx, dirty) {  // patch (update)
            if (dirty & 3) {  // bit mask: изменился count или doubled?
                button.textContent = `Clicked ${ctx[0]} times, doubled: ${ctx[1]}`;
            }
        }
    };
}
```

Компилятор Svelte знает на этапе компиляции, какие части DOM зависят от какого state, и генерирует точные обновления.

**Преимущества Svelte:**
- Нет overhead от Virtual DOM
- Меньше runtime кода (нет библиотеки reconciliation)
- Обычно быстрее на простых задачах

**Недостатки:**
- Нет runtime flexibility (нельзя "обойти" оптимизатор)
- Менее зрелая экосистема
- Сложнее метапрограммирование

## Solid.js: fine-grained reactivity без Virtual DOM

Solid.js — самый быстрый из популярных фреймворков. JSX-синтаксис как React, но под капотом — реактивность Vue + Svelte-компиляция:

```jsx
// Solid.js: синтаксис как React, но...
import { createSignal, createMemo } from 'solid-js';

function Counter() {
    const [count, setCount] = createSignal(0);
    const doubled = createMemo(() => count() * 2);
    
    return (
        <button onClick={() => setCount(c => c + 1)}>
            {count()} × 2 = {doubled()}
        </button>
    );
}
```

Ключевое отличие от React: компоненты в Solid выполняются **один раз** при монтировании. Обновления происходят через реактивные эффекты, которые точно знают, какой DOM-узел нужно обновить:

```javascript
// В React: функция-компонент вызывается при каждом рендере
function ReactComponent({ items }) {
    // Этот код выполняется при КАЖДОМ обновлении
    const processed = items.map(item => ({ ...item, processed: true }));
    return <ul>{processed.map(item => <li>{item.name}</li>)}</ul>;
}

// В Solid: функция вызывается ОДИН раз
function SolidComponent(props) {
    // Этот код выполняется ОДИН РАЗ при монтировании
    return (
        <ul>
            {/* Только JSX-выражения реактивны */}
            <For each={props.items}>
                {item => <li>{item.name}</li>}
            </For>
        </ul>
    );
}
```

## Signals: новый тренд реактивности

Angular, Preact, Qwik, Vue, Solid — все движутся к "сигналам" (signals) как базовому примитиву реактивности:

```javascript
// Concept "signals" (Vue ref, Solid createSignal, Angular signal)
const count = signal(0);      // Создаём сигнал

count();                       // Читаем значение (отслеживается!)
count.set(5);                  // Устанавливаем новое значение
count.update(v => v + 1);      // Обновляем относительно предыдущего

const doubled = computed(() => count() * 2); // Производный сигнал

effect(() => {
    console.log('Count changed:', count());  // Эффект с автоподпиской
});
```

Signals — это возвращение к observer-паттерну, но с автоматическим отслеживанием зависимостей (no explicit subscribe/unsubscribe).

## Сравнение подходов

| Фреймворк | Подход | Virtual DOM | Granularity | Bundle size |
|---|---|---|---|---|
| React | VDOM + Fiber | Да | Компонент | ~40 KB |
| Vue 3 | Proxy реактивность | Да (VDOM) | Компонент | ~35 KB |
| Svelte | Compile-time | Нет | Поле | ~10 KB runtime |
| Solid | Fine-grained signals | Нет | DOM-узел | ~14 KB |
| Angular | Signals (v17+) | Нет (Ivy) | Компонент | ~75 KB |

**Вывод:** Virtual DOM — элегантный компромисс для сложных приложений с непредсказуемыми изменениями. Fine-grained реактивность эффективнее, но требует более строгих правил. Compile-time фреймворки (Svelte) дают наименьший overhead, но ценой гибкости.

## Итог

1. **Virtual DOM** — легковесная JS-копия DOM для minimизации прямых обновлений
2. **Reconciliation** — O(n) алгоритм с эвристиками для сравнения VDOM-деревьев
3. **Keys** — помогают React отслеживать идентичность элементов при перестановках
4. **React Fiber** — прерываемый, приоритетный reconciler; основа Concurrent Mode
5. **Vue Proxy** — fine-grained реактивность, точно знает зависимости
6. **Svelte** — compile-time решение, нет runtime VDOM overhead
7. **Signals** — современный примитив реактивности, распространяющийся по всем фреймворкам

## Литература

1. Facebook Engineering. (2013). *React: A JavaScript library for building user interfaces*. https://reactjs.org/

2. Clark, A. (2017). *React Fiber Architecture*. https://github.com/acdlite/react-fiber-architecture

3. Facebook Engineering. (2022). *React 18 Release*. https://reactjs.org/blog/2022/03/29/react-v18.html

4. You, E. (2020). *Vue 3 Reactivity in Depth*. https://vuejs.org/guide/extras/reactivity-in-depth.html

5. Harris, R. (2019). *Virtual DOM is pure overhead*. https://svelte.dev/blog/virtual-dom-is-pure-overhead

6. Ryan Carniato. (2021). *Solid.js: Reactivity to Rendering*. https://dev.to/ryansolid/solid-js-reactivity-to-rendering-5ck4

7. Facebook Engineering. (2021). *Introducing Concurrent Mode*. https://reactjs.org/docs/concurrent-mode-intro.html

8. Myer, D. (2021). *The Story of React*. https://medium.com/@dan_abramov/youre-missing-the-point-of-react-a20e34a51e1a

9. Preact Team. (2023). *Signals — Reactive State Management*. https://preactjs.com/guide/v10/signals/

10. Angular Team. (2023). *Angular Signals Guide*. https://angular.io/guide/signals
