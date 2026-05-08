# Reflow, Repaint: почему они дорогие и как их избежать

Бывает так: страница выглядит правильно, но при прокрутке подтормаживает. Или анимация кнопки не плавная. Или добавление элементов в список ощущается "тяжёлым". Причина почти всегда одна — лишние reflow и repaint. Понимание того, что это такое и почему дорого, позволяет писать UI, работающий на 60 кадрах в секунду даже на слабых устройствах.

## Три уровня стоимости обновления

Не все изменения в DOM одинаково дороги. Browser rendering pipeline имеет три уровня:

```
Изменение геометрии (размер, позиция):
JS → Style → Layout → Paint → Composite
                ^^^
            (reflow — самый дорогой)

Изменение внешнего вида (цвет, фон):
JS → Style → Paint → Composite
              ^^^
          (repaint — дороже composite, дешевле layout)

Изменение transform/opacity:
JS → Composite
      ^^^
  (только compositor — самый дешёвый)
```

Каждый уровень включает все следующие: layout включает paint и composite. Поэтому минимизация количества reflow — приоритет оптимизации.

## Reflow (Layout): вычисление геометрии

Reflow (также называют Layout) происходит, когда браузер должен пересчитать позиции и размеры элементов. Это вычислительно дорогая операция, потому что:

1. Браузер проходит по дереву DOM сверху вниз
2. Размер родителя зависит от детей, дети зависят от родителя — рекурсивный процесс
3. Изменение одного элемента может потребовать пересчёта всего дерева

### Что вызывает reflow

**Изменение CSS-свойств, влияющих на геометрию:**
```javascript
// Все эти свойства вызовут reflow:
element.style.width = '200px';
element.style.height = '100px';
element.style.padding = '10px';
element.style.margin = '5px';
element.style.border = '1px solid black';
element.style.fontSize = '16px';
element.style.display = 'block'; // или none
element.style.position = 'absolute';
element.style.top = '50px';
element.style.left = '100px';
```

**Чтение геометрических свойств:**

Это самый неочевидный триггер. Браузер "ленив" — откладывает reflow до последнего. Но когда вы читаете геометрические свойства, браузер обязан выполнить reflow немедленно:

```javascript
// Чтение этих свойств запускает reflow:
element.offsetTop;
element.offsetLeft;
element.offsetWidth;
element.offsetHeight;
element.scrollTop;
element.scrollLeft;
element.scrollWidth;
element.scrollHeight;
element.clientTop;
element.clientLeft;
element.clientWidth;
element.clientHeight;
element.getBoundingClientRect();
element.getComputedStyle();
window.innerWidth;
window.innerHeight;
```

**Добавление/удаление DOM-элементов:**
```javascript
document.body.appendChild(newElement); // reflow
document.body.removeChild(element);   // reflow
```

**Изменение текста:**
```javascript
element.textContent = 'New text'; // может изменить высоту → reflow
```

**Изменение классов:**
```javascript
element.classList.add('big-font'); // если класс меняет геометрию → reflow
```

## Layout Thrashing: чередование чтения и записи

Layout Thrashing (мотание layout) — главная антипаттерн в DOM-манипуляциях. Он возникает при чередовании чтений и записей геометрических свойств.

```javascript
// ПЛОХО: Layout Thrashing (10 reflow!)
for (let i = 0; i < 10; i++) {
    const width = boxes[i].offsetWidth;  // ЧТЕНИЕ → принудительный reflow
    boxes[i].style.width = width + 10 + 'px';  // ЗАПИСЬ → инвалидирует layout
    // На следующей итерации: снова чтение → снова reflow
}
```

```
Timeline:
Write ───→ Layout stale
Read  ───→ Forced Reflow #1  ← дорого
Write ───→ Layout stale
Read  ───→ Forced Reflow #2  ← дорого
Write ───→ Layout stale
Read  ───→ Forced Reflow #3  ← дорого
...
```

**Правильный подход — сначала все чтения, потом все записи:**

```javascript
// ХОРОШО: Batching reads and writes (1 reflow!)
const widths = boxes.map(box => box.offsetWidth); // Все чтения сразу
boxes.forEach((box, i) => {                        // Все записи сразу
    box.style.width = widths[i] + 10 + 'px';
}); // Браузер выполнит reflow один раз
```

```
Timeline:
Read Read Read Read Read  ───→ Single Reflow
Write Write Write Write Write ───→ No reflow (до следующего кадра)
```

### Forced Synchronous Layout

Чтение геометрии сразу после записи называется "forced synchronous layout":

```javascript
// Запись → немедленно чтение → принудительный синхронный layout
element.style.width = '200px';     // Запись, layout "стал устаревшим"
const height = element.offsetHeight; // ЧТЕНИЕ — браузер вынужден пересчитать прямо сейчас!
```

Chrome DevTools покажет это как предупреждение "Forced reflow is a likely performance bottleneck".

## Repaint: перерисовка внешнего вида

Repaint происходит при изменении визуальных свойств без изменения геометрии:

```javascript
// Эти изменения вызовут repaint, но НЕ reflow:
element.style.color = 'red';
element.style.backgroundColor = '#fff';
element.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)';
element.style.borderColor = 'blue';
element.style.outlineColor = 'red';
element.style.visibility = 'hidden'; // скрыт, но место занимает
element.style.textDecoration = 'underline';
```

Repaint дешевле reflow, но всё ещё требует:
1. Пройти по дереву рендеринга для определения повреждённых областей
2. Перерисовать пиксели на GPU

## Compositing: только GPU

Compositing — самый дешёвый вид обновления. Браузер просто перемещает или трансформирует уже нарисованные текстуры на GPU:

```javascript
// Только compositor (нет ни reflow, ни repaint):
element.style.transform = 'translateX(100px)';
element.style.opacity = '0.5';
```

**Это ключевой принцип**: анимируйте transform и opacity, а не top/left, width, height, background.

## Обнаружение проблем в Chrome DevTools

### Performance Timeline

```
1. Откройте DevTools (F12)
2. Вкладка Performance
3. Нажмите Record (или Ctrl+Shift+E)
4. Воспроизведите проблему
5. Остановите запись

Что смотреть:
- Long Tasks (красные прямоугольники > 50ms)
- Layout events (фиолетовые полосы)
- Paint events (зелёные полосы)
- Forced Reflow warnings
```

### Rendering Flags

```
1. DevTools → Rendering (через три точки или Ctrl+Shift+P → "Show Rendering")
2. Включить:
   - "Paint Flashing" — зелёные вспышки при repaint
   - "Layout Shift Regions" — синие регионы при layout
   - "FPS Meter" — счётчик FPS в углу
```

### Lighthouse

Lighthouse автоматически находит проблемы:
- "Avoid large layout shifts" (CLS)
- "Reduce JavaScript execution time"
- "Avoid chaining critical requests"

## Оптимизации

### 1. requestAnimationFrame

Избегайте изменения DOM вне requestAnimationFrame. rAF гарантирует, что изменения произойдут в начале следующего кадра:

```javascript
// ПЛОХО: изменение DOM вне кадра
function updatePositions() {
    items.forEach(item => {
        item.style.left = getNewPosition(item) + 'px';
    });
    // Если вызывается часто — много reflow вне синхронизации с кадрами
}

// ХОРОШО: синхронизация с кадром
function updatePositions() {
    requestAnimationFrame(() => {
        // Читаем всё
        const positions = items.map(item => ({
            item,
            newPos: getNewPosition(item)
        }));
        // Пишем всё
        positions.forEach(({ item, newPos }) => {
            item.style.left = newPos + 'px';
        });
    });
}
```

### 2. DocumentFragment

```javascript
// ПЛОХО: много reflow
const list = document.getElementById('list');
for (let i = 0; i < 1000; i++) {
    const li = document.createElement('li');
    li.textContent = `Item ${i}`;
    list.appendChild(li); // reflow на каждой итерации!
}

// ХОРОШО: один reflow
const fragment = document.createDocumentFragment();
for (let i = 0; i < 1000; i++) {
    const li = document.createElement('li');
    li.textContent = `Item ${i}`;
    fragment.appendChild(li); // фрагмент не в DOM, нет reflow
}
list.appendChild(fragment); // один reflow
```

### 3. CSS transform вместо top/left

```css
/* ПЛОХО: вызывает layout при каждом кадре */
@keyframes slide-bad {
    from { left: 0; }
    to { left: 300px; }
}

/* ХОРОШО: только compositor, 60fps на слабом железе */
@keyframes slide-good {
    from { transform: translateX(0); }
    to { transform: translateX(300px); }
}
```

Это критически важно: CSS-анимации с `transform` и `opacity` могут выполняться на **отдельном потоке compositor**, не блокируя main thread JavaScript.

### 4. will-change: подсказка браузеру

```css
.animated-element {
    will-change: transform;  /* Браузер заранее создаст отдельный слой */
}

/* После анимации убрать (освободить ресурсы) */
element.addEventListener('transitionend', () => {
    element.style.willChange = 'auto';
});
```

`will-change` заставляет браузер создать compositor layer заранее. Это предотвращает "флеш" при первом запуске анимации. Но не злоупотребляйте — каждый дополнительный слой занимает память GPU.

### 5. CSS Containment

CSS Containment позволяет "изолировать" дерево элементов, ограничивая масштаб reflow:

```css
.isolated-widget {
    contain: layout;  /* изменения внутри не вызывают reflow снаружи */
    /* contain: style; — CSS-счётчики не текут наружу */
    /* contain: size;  — размер не зависит от содержимого */
    /* contain: paint; — контент не рисуется за пределами */
    /* contain: strict; — всё перечисленное */
    /* contain: content; — layout + style + paint */
}
```

```css
/* Практический пример: список с containment */
.list-item {
    contain: layout style;
    /* Изменение одного элемента не требует reflow соседей */
}
```

### 6. Виртуализация длинных списков

Для списков с тысячами элементов отрисовка всех сразу убьёт производительность. Виртуализация рендерит только видимые элементы:

```javascript
// Упрощённая виртуализация
class VirtualList {
    constructor(container, items, itemHeight) {
        this.container = container;
        this.items = items;
        this.itemHeight = itemHeight;
        
        // Создаём "прокручиваемый" контейнер нужной высоты
        this.scrollContainer = document.createElement('div');
        this.scrollContainer.style.height = items.length * itemHeight + 'px';
        this.scrollContainer.style.position = 'relative';
        container.appendChild(this.scrollContainer);
        
        container.addEventListener('scroll', () => this.render());
        this.render();
    }
    
    render() {
        const scrollTop = this.container.scrollTop;
        const containerHeight = this.container.clientHeight;
        
        const firstVisible = Math.floor(scrollTop / this.itemHeight);
        const lastVisible = Math.ceil((scrollTop + containerHeight) / this.itemHeight);
        
        // Рендерим только видимые + небольшой буфер
        const buffer = 5;
        const start = Math.max(0, firstVisible - buffer);
        const end = Math.min(this.items.length, lastVisible + buffer);
        
        // Очищаем и перерисовываем только видимый диапазон
        this.scrollContainer.innerHTML = '';
        
        const fragment = document.createDocumentFragment();
        for (let i = start; i < end; i++) {
            const el = document.createElement('div');
            el.style.position = 'absolute';
            el.style.top = i * this.itemHeight + 'px';
            el.style.height = this.itemHeight + 'px';
            el.textContent = this.items[i];
            fragment.appendChild(el);
        }
        this.scrollContainer.appendChild(fragment);
    }
}
```

В production используйте библиотеки: `react-window`, `react-virtual`, `@tanstack/virtual`.

## Пример до/после оптимизации

### Исходный код (проблемный)

```javascript
function updateItemWidths(items) {
    // Классический Layout Thrashing
    for (const item of items) {
        // Чтение → reflow
        const containerWidth = item.parentElement.offsetWidth;
        // Запись → layout dirty
        item.style.width = (containerWidth * 0.8) + 'px';
        
        // Чтение → снова reflow!
        const height = item.offsetHeight;
        // Запись
        item.style.marginTop = (height * 0.1) + 'px';
    }
}
```

Для 100 элементов это **200 reflow** (2 на элемент).

### Оптимизированный код

```javascript
function updateItemWidths(items) {
    // Шаг 1: Все чтения (1 reflow)
    const containerWidth = items[0].parentElement.offsetWidth;
    const heights = items.map(item => item.offsetHeight);
    
    // Шаг 2: Все записи (0 reflow до следующего кадра)
    requestAnimationFrame(() => {
        items.forEach((item, i) => {
            item.style.width = (containerWidth * 0.8) + 'px';
            item.style.marginTop = (heights[i] * 0.1) + 'px';
        });
    });
}
```

Итого: **1 reflow** вместо 200.

## Избегание layout shifts (CLS)

Cumulative Layout Shift (CLS) — метрика Core Web Vitals, измеряющая, насколько элементы "прыгают" при загрузке. Плохой CLS > 0.1.

```html
<!-- ПЛОХО: изображение без размеров → layout shift при загрузке -->
<img src="hero.jpg" alt="Hero">

<!-- ХОРОШО: явные размеры предотвращают shift -->
<img src="hero.jpg" width="800" height="400" alt="Hero">

<!-- Или через CSS (aspect-ratio) -->
<img src="hero.jpg" style="aspect-ratio: 2/1; width: 100%;" alt="Hero">
```

```css
/* Skeleton screens предотвращают CLS */
.card-skeleton {
    background: #e0e0e0;
    border-radius: 4px;
    animation: pulse 1.5s infinite;
    height: 200px;  /* явная высота = нет сдвига при загрузке */
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
```

## Итог

Понимание reflow и repaint позволяет принимать правильные архитектурные решения:

1. **Reflow** дороже всего — пересчитывает геометрию всего поддерева
2. **Repaint** — дешевле reflow, но всё равно нагружает CPU
3. **Composite only** — идеал для анимаций; используйте `transform` и `opacity`
4. **Батчите** чтения и записи — все чтения, потом все записи
5. **requestAnimationFrame** — синхронизируйтесь с кадрами рендеринга
6. **will-change** — заранее выделяйте слои для анимируемых элементов
7. **CSS containment** — изолируйте независимые компоненты
8. **Виртуализация** — рендерьте только видимое для длинных списков

## Литература

1. Grigorik, I. (2013). *Rendering Performance*. Google Developers. https://developers.google.com/web/fundamentals/performance/rendering/

2. Archibald, J. (2013). *requestAnimationFrame for smart animating*. https://www.html5rocks.com/en/tutorials/speed/animations/

3. Heyes, P. *CSS Triggers*. https://csstriggers.com/ (какие свойства вызывают какой уровень)

4. MDN Web Docs. *CSS Containment*. https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment

5. Google Developers. *Avoid Large, Complex Layouts and Layout Thrashing*. https://developers.google.com/web/fundamentals/performance/rendering/avoid-large-complex-layouts-and-layout-thrashing

6. Google Developers. *Cumulative Layout Shift (CLS)*. https://web.dev/cls/

7. Google Developers. *Stick to Compositor-Only Properties and Manage Layer Count*. https://developers.google.com/web/fundamentals/performance/rendering/stick-to-compositor-only-properties-and-manage-layer-count

8. Chrome DevTools. *Analyze rendering performance with the Rendering tab*. https://developer.chrome.com/docs/devtools/rendering/

9. Osmani, A. (2012). *Performance-Optimizing Animations using requestAnimationFrame*. https://www.html5rocks.com/en/tutorials/speed/mo-vs-rAF/

10. W3C. *CSS Will Change Module Level 1*. https://www.w3.org/TR/css-will-change-1/
