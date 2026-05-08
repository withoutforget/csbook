# CSS Box Model, Flexbox и Grid: три способа разложить элементы

CSS-раскладка (layout) — одна из самых обсуждаемых тем в frontend разработке. Ещё несколько лет назад расположить элементы по горизонтали было нетривиальной задачей. Сегодня у нас есть три мощных инструмента: классический box model с нормальным потоком, Flexbox для одномерных раскладок и Grid для двумерных. Знание всех трёх и умение выбрать подходящий инструмент — признак профессионала.

## CSS Box Model: основа всего

Каждый HTML-элемент — это прямоугольник. Box model описывает, из чего он состоит.

### Структура бокса

```
┌─────────────── margin ───────────────┐
│   ┌──────────── border ────────────┐  │
│   │   ┌──────── padding ─────────┐ │  │
│   │   │                          │ │  │
│   │   │        content           │ │  │
│   │   │    (width × height)      │ │  │
│   │   │                          │ │  │
│   │   └──────────────────────────┘ │  │
│   └────────────────────────────────┘  │
└───────────────────────────────────────┘
```

- **content** — область для текста, изображений, дочерних элементов
- **padding** — внутренний отступ, между content и border; имеет фоновый цвет элемента
- **border** — граница, может иметь стиль, цвет, радиус
- **margin** — внешний отступ, между border и соседними элементами; прозрачный

```css
.box {
    width: 200px;        /* ширина content */
    height: 100px;       /* высота content */
    padding: 20px;       /* со всех сторон */
    border: 2px solid #333;
    margin: 10px;
    background: lightblue; /* покрывает content + padding */
}
```

### box-sizing: content-box vs border-box

Историческая проблема: что означает `width: 200px`?

```css
/* content-box (default, legacy) */
.content-box {
    box-sizing: content-box;
    width: 200px;
    padding: 20px;
    border: 2px solid black;
    /* РЕАЛЬНАЯ ширина = 200 + 20*2 + 2*2 = 244px */
}

/* border-box (рекомендуется) */
.border-box {
    box-sizing: border-box;
    width: 200px;
    padding: 20px;
    border: 2px solid black;
    /* РЕАЛЬНАЯ ширина = 200px (content = 200 - 20*2 - 2*2 = 156px) */
}
```

`border-box` гораздо интуитивнее: "я хочу, чтобы элемент занимал 200px" — и он занимает ровно 200px. Большинство современных CSS-фреймворков и reset'ов устанавливают `border-box` для всех элементов:

```css
/* Универсальный reset */
*,
*::before,
*::after {
    box-sizing: border-box;
}
```

### Схлопывание margins (Margin Collapsing)

Вертикальные margins между блочными элементами "схлопываются":

```css
.paragraph-1 { margin-bottom: 20px; }
.paragraph-2 { margin-top: 30px; }

/* Расстояние между ними = max(20, 30) = 30px, НЕ 50px! */
```

Схлопывание происходит при:
- Adjacent siblings (соседние элементы)
- Parent и первый/последний child (если нет padding/border/overflow между ними)
- Пустые блоки (margin-top и margin-bottom схлопываются)

Схлопывание **не** происходит для:
- Horizontal margins
- Flex/Grid items
- Overflow: hidden/auto
- Float elements

```css
/* Предотвращение схлопывания: */
.parent {
    overflow: hidden;     /* создаёт BFC */
    /* или */
    padding-top: 1px;     /* разделяет margins */
    /* или */
    border-top: 1px solid transparent;
}
```

## Нормальный поток и режимы отображения

По умолчанию элементы находятся в "нормальном потоке" (normal flow). Режим отображения определяется свойством `display`:

### Block

```css
.block { display: block; }
/* - Занимает всю доступную ширину
   - Начинается с новой строки
   - margin/padding работают со всех сторон
   Примеры: div, p, h1-h6, ul, li */
```

### Inline

```css
.inline { display: inline; }
/* - Ширина = ширина содержимого
   - Не начинается с новой строки
   - margin/padding работают только горизонтально!
   - width/height ИГНОРИРУЮТСЯ
   Примеры: span, a, strong, em */
```

### Inline-block

```css
.inline-block { display: inline-block; }
/* - Ширина = ширина содержимого (но можно задать явно)
   - Не начинается с новой строки (как inline)
   - margin/padding работают со всех сторон (как block)
   - width/height работают
   Типичное использование: кнопки, иконки в строке */
```

```html
<!-- Проблема inline-block: пробелы между элементами -->
<ul class="nav">
    <li class="nav-item">Главная</li>
    <li class="nav-item">О нас</li>
    <li class="nav-item">Контакты</li>
</ul>
```

```css
/* "Пробел" появляется из-за whitespace в HTML */
.nav-item { display: inline-block; }

/* Исправление */
.nav { font-size: 0; }  /* убираем размер пробела */
.nav-item { font-size: 16px; }  /* возвращаем нормальный */
```

### Float: старый способ раскладки

Float изначально предназначался для обтекания изображений текстом. Его использовали для создания колонок, но это приводило к багам:

```css
.image { float: left; margin-right: 10px; }
/* Текст обтекает изображение слева */

/* Проблема: контейнер "коллапсирует" */
.container {
    /* Если все дети float, высота = 0 */
}

/* Фикс: clearfix */
.clearfix::after {
    content: '';
    display: table;
    clear: both;
}
```

Сегодня Float используется только для своей первоначальной задачи — обтекания. Для раскладки используйте Flexbox или Grid.

## Flexbox: одномерная раскладка

Flexbox (Flexible Box Layout) решает задачу одномерного расположения элементов — либо по горизонтали, либо по вертикали.

### Основные концепции

```css
.container {
    display: flex;           /* или inline-flex */
    flex-direction: row;     /* главная ось (main axis) */
    /* row | row-reverse | column | column-reverse */
}
```

В Flexbox различают:
- **Main axis** — главная ось (направление flex-direction)
- **Cross axis** — поперечная ось (перпендикулярно)
- **Flex container** — элемент с `display: flex`
- **Flex items** — прямые дочерние элементы контейнера

```
flex-direction: row (default)
Main axis →
┌────────────────────────────────────┐
│  [item1]  [item2]  [item3]         │
│                                    │
│                         Cross axis │
│                                ↓   │
└────────────────────────────────────┘

flex-direction: column
Cross axis →
┌─────────────┐
│  [item1]    │
│  [item2]    │  Main axis ↓
│  [item3]    │
└─────────────┘
```

### Выравнивание по главной оси: justify-content

```css
.container {
    display: flex;
    justify-content: flex-start;    /* по умолчанию */
    /* justify-content: center; */
    /* justify-content: flex-end; */
    /* justify-content: space-between; — пространство между items */
    /* justify-content: space-around; — пространство вокруг items */
    /* justify-content: space-evenly; — равные промежутки */
}
```

```
space-between:  [A]      [B]      [C]
space-around:   [A]  [B]  [C]
space-evenly:  [A]   [B]   [C]
```

### Выравнивание по поперечной оси: align-items

```css
.container {
    display: flex;
    align-items: stretch;    /* по умолчанию — растянуть */
    /* align-items: flex-start; */
    /* align-items: center; — вертикальное центрирование! */
    /* align-items: flex-end; */
    /* align-items: baseline; — выравнивание по базовой линии текста */
}
```

Вертикальное центрирование — то, что годами делалось с трудом, теперь одна строка:

```css
.centered {
    display: flex;
    justify-content: center;  /* горизонтально */
    align-items: center;      /* вертикально */
    height: 100vh;
}
```

### Свойства flex-items: grow, shrink, basis

```css
.item {
    /* flex: grow shrink basis */
    flex: 1 1 0%;    /* сокращённая запись */
    
    /* Или по отдельности: */
    flex-grow: 1;    /* насколько вырастет относительно других */
    flex-shrink: 1;  /* насколько уменьшится при нехватке места */
    flex-basis: 0%;  /* начальный размер до grow/shrink */
}
```

```html
<!-- Пример: три колонки 1:2:1 -->
<div style="display: flex">
    <div style="flex: 1">Боковая панель</div>
    <div style="flex: 2">Контент</div>
    <div style="flex: 1">Боковая панель</div>
</div>
```

```css
/* Распространённые значения flex */
flex: 1      /* flex: 1 1 0% — равные доли */
flex: auto   /* flex: 1 1 auto — равные доли от реального размера */
flex: none   /* flex: 0 0 auto — не растягивается и не сжимается */
flex: 0 auto /* flex: 0 1 auto — по умолчанию */
```

### Перенос строк: flex-wrap

```css
.container {
    display: flex;
    flex-wrap: nowrap;   /* по умолчанию — не переносить */
    /* flex-wrap: wrap; — переносить при нехватке места */
    /* flex-wrap: wrap-reverse; */
}
```

### Выравнивание многострочного flex: align-content

Работает только при `flex-wrap: wrap`:

```css
.container {
    display: flex;
    flex-wrap: wrap;
    align-content: flex-start;
    /* stretch | flex-start | flex-end | center |
       space-between | space-around | space-evenly */
}
```

### align-self: индивидуальное выравнивание

```css
.special-item {
    align-self: flex-end;  /* перекрывает align-items для этого элемента */
}
```

## CSS Grid: двумерная раскладка

CSS Grid — это мощная система двумерной раскладки, позволяющая управлять одновременно строками и столбцами.

### Основы Grid

```css
.container {
    display: grid;
    grid-template-columns: 200px 1fr 200px;  /* 3 колонки */
    grid-template-rows: 80px auto 50px;       /* 3 строки */
    gap: 20px;  /* отступы между ячейками */
}
```

### fr unit: дробные единицы

`fr` (fraction unit) — доля свободного пространства:

```css
/* 3 равные колонки */
grid-template-columns: 1fr 1fr 1fr;
/* или */
grid-template-columns: repeat(3, 1fr);

/* 2 боковых по 200px, центр занимает остаток */
grid-template-columns: 200px 1fr 200px;

/* 25%, 50%, 25% */
grid-template-columns: 1fr 2fr 1fr;
```

### auto-fill и auto-fit: адаптивные колонки

```css
/* Создаёт столько колонок, сколько помещается */
.responsive-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 16px;
}
/* При ширине 800px: 4 колонки по 200px
   При ширине 500px: 2 колонки по 250px
   При ширине 300px: 1 колонка */
```

`auto-fill` vs `auto-fit`:
- `auto-fill` — создаёт пустые "следы" для ненаполненных колонок
- `auto-fit` — схлопывает пустые следы, давая больше места занятым

```css
/* auto-fit растягивает последний элемент */
grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
```

### Grid Areas: именованные зоны

```css
.layout {
    display: grid;
    grid-template-areas:
        "header header header"
        "sidebar main aside"
        "footer footer footer";
    grid-template-columns: 200px 1fr 200px;
    grid-template-rows: 80px 1fr 50px;
}

.header  { grid-area: header; }
.sidebar { grid-area: sidebar; }
.main    { grid-area: main; }
.aside   { grid-area: aside; }
.footer  { grid-area: footer; }
```

### Явное размещение элементов

```css
.item {
    /* По линиям (от 1, отрицательные — с конца) */
    grid-column: 1 / 3;  /* от линии 1 до линии 3 */
    grid-row: 2 / 4;
    
    /* Или span */
    grid-column: 2 / span 2;  /* начиная с колонки 2, занять 2 */
    grid-row: span 3;          /* занять 3 строки */
}

/* Элемент, занимающий всю ширину */
.full-width {
    grid-column: 1 / -1;  /* от первой до последней линии */
}
```

### Выравнивание в Grid

```css
.container {
    /* Выравнивание всех items */
    justify-items: stretch;   /* горизонтально внутри ячейки */
    align-items: stretch;     /* вертикально внутри ячейки */
    
    /* Выравнивание всего grid внутри контейнера */
    justify-content: start;
    align-content: start;
}

.item {
    /* Индивидуальное выравнивание */
    justify-self: center;
    align-self: end;
}
```

## Сравнение: Flexbox vs Grid

| Аспект | Flexbox | Grid |
|---|---|---|
| Измерение | 1D (строка ИЛИ колонка) | 2D (строки И колонки) |
| Подход | Content-first | Layout-first |
| Элементы | Сами определяют размер | Сетка определяет размер |
| Когда использовать | Навигация, кнопки, компоненты | Страничный layout, карточки |
| Поддержка браузеров | Отличная | Отличная (IE11 с ограничениями) |

**Практическое правило:**
- Есть ряд/колонка элементов → Flexbox
- Есть и строки, и колонки → Grid
- Нужна адаптивная сетка карточек → Grid с auto-fill

Их можно и нужно комбинировать:

```css
/* Grid для общего layout страницы */
.page {
    display: grid;
    grid-template-areas:
        "header"
        "main"
        "footer";
}

/* Flexbox для навигации внутри header */
.navigation {
    display: flex;
    gap: 16px;
    align-items: center;
}
```

## Позиционирование

### static (default)
```css
position: static; /* нормальный поток, top/left/right/bottom не работают */
```

### relative
```css
position: relative;
top: 10px;    /* смещение относительно нормальной позиции */
left: 20px;
/* Занимает место в потоке! Соседи не сдвигаются. */
```

### absolute
```css
position: absolute;
top: 0;
right: 0;
/* Исключается из потока (не занимает место)
   Позиционируется относительно ближайшего positioned ancestor
   (relative/absolute/fixed/sticky) */
```

### fixed
```css
position: fixed;
top: 0;
width: 100%;
/* Позиционируется относительно viewport
   Остаётся на месте при прокрутке */
```

### sticky
```css
position: sticky;
top: 0;
/* Комбинация relative и fixed:
   - relative пока в области видимости
   - "прилипает" к указанной позиции при прокрутке */
```

```html
<!-- Пример sticky header -->
<header style="position: sticky; top: 0; background: white; z-index: 100;">
    Навигация
</header>
```

## Stacking Context и z-index

Z-index работает только в пределах одного stacking context:

```css
.container {
    position: relative;
    z-index: 1;  /* создаёт stacking context */
}

/* z-index дочерних элементов ограничен контейнером */
.child-with-high-z {
    position: absolute;
    z-index: 9999;  /* но не "перепрыгнет" выше .container */
}

/* Другой элемент НА ТОМ ЖЕ уровне, что .container */
.sibling {
    position: relative;
    z-index: 2;  /* будет поверх .container и всех его детей */
}
```

Новый stacking context создаётся при (список не исчерпывающий):
- `position: relative/absolute` + `z-index` != auto
- `opacity < 1`
- `transform` (не none)
- `filter` (не none)
- `isolation: isolate`
- `will-change` (для перечисленных выше)

## Практические примеры

### Навигационное меню

```css
.navbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 24px;
    height: 64px;
}

.nav-logo { font-weight: bold; }

.nav-links {
    display: flex;
    gap: 24px;
    list-style: none;
    margin: 0;
    padding: 0;
}

.nav-cta {
    margin-left: auto;  /* прижать к правому краю */
}
```

### Карточная сетка

```css
.cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 24px;
    padding: 24px;
}

.card {
    display: flex;
    flex-direction: column;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    overflow: hidden;
}

.card-body { flex: 1; padding: 16px; }
.card-footer { padding: 16px; border-top: 1px solid #e0e0e0; }
```

### Модальное окно (центрирование)

```css
.modal-overlay {
    position: fixed;
    inset: 0;  /* top: 0; right: 0; bottom: 0; left: 0; */
    background: rgba(0, 0, 0, 0.5);
    display: grid;
    place-items: center;  /* grid: justify-items + align-items в одну строку */
}

.modal {
    background: white;
    padding: 24px;
    border-radius: 8px;
    max-width: 500px;
    width: 90%;
}
```

## Итог

CSS предлагает три основных подхода к раскладке:

1. **Box Model** — основа: content, padding, border, margin; `border-box` практичнее
2. **Flexbox** — одномерный; для рядов и колонок компонентов; отличное выравнивание
3. **Grid** — двумерный; для страничных раскладок и сеток; мощное управление пространством

Используйте оба вместе: Grid для общей структуры страницы, Flexbox для выравнивания компонентов внутри ячеек.

## Литература

1. W3C. *CSS Flexible Box Layout Module Level 1*. https://www.w3.org/TR/css-flexbox-1/

2. W3C. *CSS Grid Layout Module Level 1*. https://www.w3.org/TR/css-grid-1/

3. W3C. *CSS Box Model Module Level 3*. https://www.w3.org/TR/css-box-3/

4. MDN Web Docs. *CSS Flexbox*. https://developer.mozilla.org/en-US/docs/Learn/CSS/CSS_layout/Flexbox

5. MDN Web Docs. *CSS Grid Layout*. https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout

6. Weyl, E. (2015). *CSS: The Missing Manual, 4th Edition*. O'Reilly Media.

7. Coyier, C. *A Complete Guide to Flexbox*. CSS-Tricks. https://css-tricks.com/snippets/css/a-guide-to-flexbox/

8. Coyier, C. *A Complete Guide to CSS Grid*. CSS-Tricks. https://css-tricks.com/snippets/css/complete-guide-grid/

9. W3C. *CSS Positioned Layout Module Level 3*. https://www.w3.org/TR/css-position-3/

10. Adam Argyle. *Building a Responsive Mega Menu with CSS Grid*. web.dev. https://web.dev/patterns/layout/
