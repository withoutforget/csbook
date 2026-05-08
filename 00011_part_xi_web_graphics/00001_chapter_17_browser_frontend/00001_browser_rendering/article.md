# Как браузер рендерит страницу: от HTML до пикселей на экране

Когда вы открываете сайт, браузер за доли секунды превращает текстовые файлы HTML, CSS и JavaScript в интерактивное визуальное изображение. Этот процесс — один из самых сложных программных конвейеров, существующих в широком использовании. Понимание его деталей позволяет писать более быстрые сайты, находить причины "прыжков" контента, избегать дорогих перерисовок и использовать DevTools как профессионал.

## Шаг 1: Парсинг HTML — от байтов к DOM

Браузер получает HTML как последовательность байтов. Первая задача — превратить их в структурированное дерево объектов.

### Токенизация

HTML-парсер работает как конечный автомат. Он читает символы по одному и переходит между состояниями:

```
"<html><body><p>Hello</p></body></html>"

Токены:
StartTag: html
StartTag: body  
StartTag: p
Text: "Hello"
EndTag: p
EndTag: body
EndTag: html
```

Состояния парсера включают: Data, TagOpen, TagName, BeforeAttributeName, AttributeName, AttributeValue, и ещё десятки других. Спецификация HTML5 определяет 80+ состояний токенизера.

### Построение дерева (Tree Construction)

Из токенов строится DOM-дерево. Правила построения обрабатывают некорректный HTML — это ключевое требование: браузер не должен падать на неправильном HTML.

```html
<!-- Пример: некорректный HTML -->
<table>
  <b><td>Cell</td></b>
</table>

<!-- Браузер исправит это до: -->
<b></b>
<table>
  <tbody>
    <tr>
      <td><b>Cell</b></td>
    </tr>
  </tbody>
</table>
```

Спецификация HTML5 детально описывает алгоритм "tree construction" с "foster parenting" (усыновление элементов, попавших не на своё место) и другими механизмами восстановления после ошибок.

### DOM-дерево

В результате получается Document Object Model (DOM) — дерево объектов:

```
Document
└── html
    ├── head
    │   ├── meta
    │   └── link (stylesheet)
    └── body
        ├── h1 "Заголовок"
        ├── p "Параграф"
        │   └── a href="/link"
        └── script src="app.js"
```

DOM — это не просто структура данных. Каждый узел является живым объектом JavaScript, к которому можно обратиться через API:

```javascript
const heading = document.querySelector('h1');
heading.textContent = 'Новый заголовок'; // DOM обновляется мгновенно
```

## Шаг 2: Парсинг CSS — от текста к CSSOM

Параллельно с построением DOM браузер парсит CSS-файлы в CSSOM (CSS Object Model).

### Структура CSSOM

CSSOM — это дерево всех CSS-правил:

```css
body { font-size: 16px; }
h1 { color: blue; font-size: 2em; }
.highlight { background: yellow; }
```

```
CSSStyleSheet
├── Rule: body → { font-size: 16px }
├── Rule: h1 → { color: blue; font-size: 2em }
└── Rule: .highlight → { background: yellow }
```

### Каскад и специфичность

CSS означает "Cascading Style Sheets" — каскадность является сутью. При конфликте правил браузер использует алгоритм каскада:

**Приоритет источников (от высшего к низшему):**
1. `!important` объявления браузера
2. `!important` объявления пользователя  
3. `!important` объявления автора страницы
4. Анимации
5. Обычные объявления автора страницы
6. Обычные объявления пользователя
7. Обычные объявления браузера

**Специфичность (specificity)** — числовой вес селектора:

```
Формула: (a, b, c)
a = количество ID-селекторов (#id)
b = количество классов, атрибутов, псевдоклассов
c = количество тегов, псевдоэлементов

#nav .item a:hover
a = 1 (#nav)
b = 1+1 (.item, :hover)  
c = 1 (a)
Специфичность: (1, 2, 1) > (0, 1, 3)

Сравнение:
(0, 0, 1) < (0, 1, 0) < (1, 0, 0)

Inline styles: (1, 0, 0, 0) — всегда выигрывает у обычных
```

```javascript
// Чтение CSSOM через JavaScript
const sheets = document.styleSheets;
for (const sheet of sheets) {
    for (const rule of sheet.cssRules) {
        console.log(rule.selectorText, rule.style.cssText);
    }
}

// Computed style (финальное значение после каскада)
const el = document.querySelector('h1');
const computed = getComputedStyle(el);
console.log(computed.fontSize); // "32px"
```

### Наследование CSS

Некоторые свойства наследуются от родителей (font-family, color, line-height), другие — нет (border, margin, padding). Это часть каскада: если у элемента нет явно заданного свойства, проверяется наследование.

## Шаг 3: Render Tree — объединение DOM и CSSOM

Render Tree строится путём объединения DOM и CSSOM. Главное правило: в Render Tree включаются только **видимые** элементы.

```
DOM:                          CSSOM:
html                          html { display: block }
├── head (skip!)              head { display: none }
└── body                      body { display: block; font: 16px }
    ├── h1                    h1 { display: block; color: blue }
    ├── p                     p { display: block }
    │   └── span hidden       span#hidden { display: none }
    └── div                   div { display: block }
```

```
Render Tree:
RenderBox (body)
├── RenderBox (h1) "Заголовок"
├── RenderBox (p) 
└── RenderBox (div)
```

Элементы с `display: none` исключаются из Render Tree полностью. Элементы с `visibility: hidden` остаются (они занимают место, но не видны).

## Шаг 4: Layout (Reflow) — вычисление геометрии

На этапе layout браузер вычисляет точные позиции и размеры каждого элемента. Это вычислительно дорогая операция.

### Модель боксов

Каждый элемент — это прямоугольник ("бокс"). Layout вычисляет:

```
┌─────────── margin ───────────┐
│  ┌──────── border ────────┐  │
│  │  ┌───── padding ─────┐ │  │
│  │  │                   │ │  │
│  │  │    content        │ │  │
│  │  │                   │ │  │
│  │  └───────────────────┘ │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
```

### Нормальный поток (Normal Flow)

По умолчанию элементы расположены в нормальном потоке:
- **Block** элементы: занимают всю ширину, расположены вертикально
- **Inline** элементы: расположены горизонтально, переносятся по словам

Layout работает рекурсивно: размер родителя зависит от детей (если явно не задан), а позиции детей зависят от родителя.

```html
<!-- Изменение ширины этого элемента вызовет reflow всех потомков -->
<div id="container">
  <p>Текст первого параграфа</p>
  <p>Текст второго параграфа</p>
</div>
```

## Шаг 5: Paint — рисование пикселей

После layout браузер знает, где находится каждый элемент. Теперь нужно нарисовать его.

### Слои (Layers)

Браузер разбивает страницу на слои (layers). Каждый слой рисуется независимо и может кешироваться. Это ключевая оптимизация: если изменился только один слой, перерисовывается только он.

Элемент создаёт новый слой при:
```css
/* Явное создание слоя */
transform: translateZ(0);  /* или любой 3D transform */
will-change: transform;    /* подсказка браузеру */
position: fixed;           /* фиксированные элементы */
opacity: 0.5;              /* частичная прозрачность */
filter: blur(5px);         /* CSS-фильтры */
```

### Paint Records

Вместо немедленного рисования, браузер записывает список команд рисования ("paint records"):
```
DrawRect(x=0, y=0, w=1920, h=1080, color=white)
DrawText(x=20, y=50, text="Заголовок", font=32px bold)
DrawRect(x=20, y=100, w=880, h=2, color=#eee)
...
```

Эти записи затем воспроизводятся для каждого слоя.

### Порядок рисования (Stacking Context)

CSS определяет порядок рисования через stacking context. Новый stacking context создаётся при:
- `position: relative/absolute/fixed/sticky` + `z-index` (не auto)
- `opacity < 1`
- `transform` (любой)
- `filter`
- `isolation: isolate`

```css
.parent {
    position: relative;
    z-index: 1;  /* создаёт stacking context */
}

.child {
    position: absolute;
    z-index: 999; /* z-index работает только внутри stacking context родителя! */
}

/* Это НЕ поднимет .child выше элементов вне .parent */
```

## Шаг 6: Compositing — GPU-магия

Compositing — финальный этап. GPU берёт все нарисованные слои и "склеивает" их в финальное изображение.

### Почему compositing отдельно?

GPU превосходит CPU в операциях с изображениями. Перемещение элемента (например, анимация `transform`) требует только обновления позиции слоя в compositor — CPU и layout не нужны.

```css
/* МЕДЛЕННАЯ анимация: вызывает layout + paint на каждом кадре */
@keyframes slide-bad {
    from { left: 0; }
    to { left: 300px; }
}

/* БЫСТРАЯ анимация: только compositor */
@keyframes slide-good {
    from { transform: translateX(0); }
    to { transform: translateX(300px); }
}
```

`transform` и `opacity` — единственные свойства, которые браузер может анимировать без layout и paint. Это ключевое правило для производительной анимации.

## Как браузер обрабатывает `<script>`

Тег `<script>` особенный — он блокирует парсинг HTML.

### Parser blocking script

```html
<body>
  <p>Этот параграф виден сразу</p>
  
  <!-- Браузер останавливается здесь! -->
  <script src="heavy-script.js"></script>
  
  <!-- Это не будет обработано, пока скрипт не загрузится и не выполнится -->
  <p>Этот параграф ждёт скрипт</p>
</body>
```

Почему? Потому что скрипт может вызвать `document.write()`, что изменит структуру HTML. Браузер не может продолжить парсинг, не зная, что сделает скрипт.

### async и defer

```html
<!-- Загружается параллельно, выполняется немедленно после загрузки -->
<!-- Порядок выполнения не гарантирован! -->
<script async src="analytics.js"></script>

<!-- Загружается параллельно, выполняется после парсинга HTML -->
<!-- Порядок выполнения гарантирован (как появились в HTML) -->
<script defer src="app.js"></script>

<!-- Inline scripts всегда parser-blocking -->
<script>
  document.write("<p>Блокирует всё!</p>");
</script>
```

Рекомендация: почти всегда используйте `defer` для внешних скриптов; `async` подходит для независимых скриптов вроде аналитики.

### type="module"

```html
<!-- ES modules автоматически defer -->
<script type="module" src="app.mjs"></script>

<!-- Это эквивалентно -->
<script defer src="app.js"></script>
```

## DOMContentLoaded vs load

```javascript
// DOMContentLoaded: HTML-документ загружен и распарсен
// Не ждёт изображения, стили (если defer), iframe
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM готов!');
    // Можно безопасно работать с DOM
});

// load: ВСЕ ресурсы загружены (изображения, стили, скрипты)
window.addEventListener('load', () => {
    console.log('Всё загружено!');
});

// Проблема с DOMContentLoaded:
// CSS блокирует выполнение последующих скриптов!
// <link rel="stylesheet" href="styles.css">
// <script>/* ждёт загрузки styles.css */</script>
// Это косвенно блокирует DOMContentLoaded
```

### Preload Scanner

Браузер имеет оптимизацию — preload scanner (спекулятивный парсер). Пока основной парсер заблокирован на `<script>`, preload scanner смотрит вперёд в HTML и начинает загружать другие ресурсы (изображения, следующие скрипты).

```html
<!-- preload scanner увидит оба ресурса, даже если CSS заблокирован -->
<link rel="stylesheet" href="styles.css">
<script src="blocked.js"></script> <!-- блокирует парсер -->
<img src="hero.jpg">              <!-- preload scanner начнёт загрузку -->
```

## Chrome DevTools для визуализации

DevTools — незаменимый инструмент для понимания rendering pipeline.

### Performance профиль

```
Timeline (Performance panel):
─────────────────────────────────────────────────────
Network: ████ HTML ██ CSS ████ JS
Parsing: ████████████████ Parse HTML/CSS
Layout:  ██ Layout
Paint:   █ Paint
Composite: █ Composite
─────────────────────────────────────────────────────
DOMContentLoaded      Load event
```

### Viewing Layers

В DevTools → Rendering → Layer borders можно увидеть все compositor слои (раскрашены синими/оранжевыми рамками).

```javascript
// В Console DevTools можно профилировать rendering:
console.time('my-operation');
// ... код ...
console.timeEnd('my-operation');

// Или:
performance.mark('start');
// ... код ...
performance.mark('end');
performance.measure('my-op', 'start', 'end');
```

## Критический путь рендеринга

Critical Rendering Path — это минимальная цепочка шагов, необходимых для отображения первого содержимого.

```
HTML → Parse → DOM
CSS  → Parse → CSSOM  } → Render Tree → Layout → Paint → Composite
JS   → Execute
```

Для оптимизации критического пути:
1. **Минимизируйте размер HTML/CSS** — меньше байт для парсинга
2. **Не блокируйте рендеринг CSS** — CSS по умолчанию blocking; `media` атрибут помогает
3. **Используйте async/defer для JS** — убрать парсер-блокирующие скрипты
4. **Inline critical CSS** — вставить минимальный CSS прямо в `<head>`

```html
<!-- Пример: inline critical CSS + async загрузка остального -->
<head>
    <style>
        /* Только стили для above-the-fold контента */
        body { font-family: sans-serif; margin: 0; }
        .hero { background: #333; color: white; padding: 2rem; }
    </style>
    <!-- Загружаем полный CSS асинхронно -->
    <link rel="preload" href="full.css" as="style" onload="this.onload=null;this.rel='stylesheet'">
    <noscript><link rel="stylesheet" href="full.css"></noscript>
</head>
```

## Итог: от HTML до пикселей

Полный путь рендеринга:

1. **Получение байтов** → декодирование (UTF-8/ASCII/...)
2. **Токенизация HTML** → 80+ состояний парсера
3. **DOM Tree** → живые JavaScript объекты
4. **Загрузка CSS** → блокирует CSSOM построение
5. **CSSOM** → правила с каскадом и специфичностью
6. **Script blocking** → JS может изменить DOM/CSSOM
7. **Render Tree** → DOM + CSSOM, только видимые элементы
8. **Layout (Reflow)** → позиции и размеры каждого бокса
9. **Paint** → команды рисования для каждого слоя
10. **Composite** → GPU склеивает слои в финальную картинку

Понимание каждого шага — основа для написания производительных web-приложений и эффективного использования DevTools.

## Литература

1. WHATWG. *HTML Living Standard — Parsing HTML*. https://html.spec.whatwg.org/multipage/parsing.html

2. W3C. *CSS Cascading and Inheritance Level 4*. https://www.w3.org/TR/css-cascade-4/

3. Grigorik, I. (2013). *Critical Rendering Path*. Google Developers. https://developers.google.com/web/fundamentals/performance/critical-rendering-path

4. Grigorik, I. (2013). *High Performance Browser Networking*. O'Reilly Media.

5. MDN Web Docs. *How browsers work*. https://developer.mozilla.org/en-US/docs/Web/Performance/How_browsers_work

6. Tali Garsiel, Paul Irish. (2011). *How Browsers Work: Behind the scenes of modern web browsers*. https://www.html5rocks.com/en/tutorials/internals/howbrowserswork/

7. Chromium. *How Blink works*. https://docs.google.com/document/d/1aitSOucL0VHZa9Z2vbRJSyAIsAz24kX8ukDFfvSjQM0

8. W3C. *Compositing and Blending Level 1*. https://www.w3.org/TR/compositing-1/

9. MDN Web Docs. *Stacking context*. https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_positioned_layout/Understanding_z-index/Stacking_context

10. Chrome Developers. *Life of a Pixel*. https://docs.google.com/presentation/d/1boPxbgNe1JBOnFBL2vjrqxp1D4rKx0ZxvbUnNLa3Myg

11. W3C. *CSS 2.1 — Visual Formatting Model*. https://www.w3.org/TR/CSS21/visuren.html
