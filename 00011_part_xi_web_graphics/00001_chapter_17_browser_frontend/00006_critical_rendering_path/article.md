# Critical Rendering Path, Lazy Loading, Code Splitting: производительность фронтенда

Скорость загрузки сайта напрямую влияет на бизнес-метрики. Amazon подсчитал, что каждые 100 мс задержки обходятся в 1% конверсии. Google учитывает Core Web Vitals в ранжировании. Для пользователей мобильных устройств с 3G-соединением разница между 2 и 5 секундами загрузки — это уход с сайта. В этой статье рассмотрим, как сделать загрузку максимально быстрой.

## Critical Rendering Path: что блокирует первый экран

Critical Rendering Path (CRP) — это минимальный набор ресурсов, необходимых для отображения содержимого над сгибом ("above the fold") — того, что пользователь видит без прокрутки.

```
Браузер получает HTML
    ↓
Парсит HTML → Находит <link rel="stylesheet">
    ↓
Загружает CSS → Блокирует рендеринг!
    ↓
CSSOM построен
    ↓
Находит <script> → Блокирует парсинг!
    ↓
JavaScript выполнен
    ↓
Render Tree → Layout → Paint → Первый кадр
```

Для оптимизации CRP нужно минимизировать количество и размер блокирующих ресурсов.

## Core Web Vitals: метрики Google

Google определил набор метрик (Core Web Vitals), измеряющих пользовательский опыт:

### TTFB (Time to First Byte)

Время от отправки запроса до получения первого байта ответа. Включает DNS, TCP, TLS handshake, обработку на сервере.

```
Хорошо: < 800 мс
Улучшить: 800 мс — 1800 мс
Плохо: > 1800 мс
```

Улучшения: CDN, кеширование на сервере, оптимизация запросов к БД.

### FCP (First Contentful Paint)

Время до появления первого контента — текста, изображения, canvas.

```
Хорошо: < 1.8 с
Улучшить: 1.8 — 3.0 с
Плохо: > 3.0 с
```

### LCP (Largest Contentful Paint)

Время до загрузки наибольшего видимого элемента (hero изображение, заголовок). **Ключевая метрика**.

```
Хорошо: < 2.5 с
Улучшить: 2.5 — 4.0 с
Плохо: > 4.0 с
```

Улучшения: оптимизация изображений, предзагрузка hero image, устранение render-blocking ресурсов.

### FID (First Input Delay) / INP (Interaction to Next Paint)

Задержка между первым взаимодействием пользователя (клик, тап) и реакцией браузера. FID заменяется на INP как основная метрика.

```
INP хорошо: < 200 мс
INP улучшить: 200 — 500 мс
INP плохо: > 500 мс
```

Улучшения: дробление long tasks, Web Workers для тяжёлых вычислений.

### CLS (Cumulative Layout Shift)

Суммарный сдвиг содержимого при загрузке. Подробнее в предыдущей статье.

```
Хорошо: < 0.1
Улучшить: 0.1 — 0.25
Плохо: > 0.25
```

## Минификация и сжатие

### Минификация

Удаление пробелов, комментариев, переименование переменных:

```javascript
// До минификации (250 символов)
function calculateDiscount(price, percentage) {
    // Вычисляем скидку
    if (percentage > 100) {
        throw new Error('Скидка не может превышать 100%');
    }
    return price * (1 - percentage / 100);
}

// После минификации (73 символа)
function a(b,c){if(c>100)throw new Error("...");return b*(1-c/100)}
```

Инструменты: Terser (JS), cssnano (CSS), html-minifier (HTML).

### Сжатие (gzip/Brotli)

Сжатие в разы уменьшает объём передаваемых данных:

```
Файл          | Оригинал | gzip  | Brotli
react.js      |  113 KB  | 36 KB | 31 KB
tailwind.css  |  350 KB  | 56 KB | 48 KB
bootstrap.js  |  176 KB  | 61 KB | 53 KB
```

Brotli (разработан Google) даёт ~15-20% лучшее сжатие, чем gzip, при примерно одинаковой скорости декомпрессии.

```nginx
# Nginx: включение Brotli и gzip
brotli on;
brotli_comp_level 6;
brotli_types text/plain text/css application/json application/javascript;

gzip on;
gzip_comp_level 6;
gzip_types text/plain text/css application/json application/javascript;
```

### HTTP заголовки кеширования

```
Статичные ресурсы с хешем в имени (bundle.abc123.js):
    Cache-Control: public, max-age=31536000, immutable
    (кешировать на год, содержимое не изменится)

HTML страницы:
    Cache-Control: no-cache
    (всегда проверять актуальность)

API ответы:
    Cache-Control: private, max-age=60
    (кешировать 60 секунд, только в браузере)
```

## Lazy Loading изображений

До HTML 5.2 lazy loading требовал JavaScript. Теперь это нативный атрибут:

```html
<!-- Нативный lazy loading (все современные браузеры) -->
<img 
    src="photo.jpg" 
    loading="lazy"
    width="800" 
    height="600"
    alt="Description"
>

<!-- loading="eager" — загрузить немедленно (default для большинства) -->
<!-- loading="lazy"  — загрузить при приближении к viewport -->
```

Браузер сам определяет "порог" (обычно ~1200px до viewport) и начинает загрузку заранее.

### IntersectionObserver для более сложных случаев

```javascript
// Для нестандартных контейнеров или анимаций
const imageObserver = new IntersectionObserver(
    (entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src; // lazy load
                img.classList.remove('lazy');
                observer.unobserve(img);   // прекращаем наблюдение
            }
        });
    },
    {
        rootMargin: '50px 0px',  // начинать загрузку за 50px до viewport
        threshold: 0.01          // достаточно 1% видимости
    }
);

document.querySelectorAll('img[data-src]').forEach(img => {
    imageObserver.observe(img);
});
```

```html
<!-- HTML для IntersectionObserver lazy loading -->
<img 
    src="placeholder-tiny.jpg"  <!-- маленький placeholder -->
    data-src="full-image.jpg"   <!-- реальное изображение -->
    class="lazy"
    width="800" 
    height="600"
    alt="Description"
>
```

### Форматы изображений

```html
<!-- Современные форматы с fallback -->
<picture>
    <source srcset="image.avif" type="image/avif">
    <source srcset="image.webp" type="image/webp">
    <img src="image.jpg" alt="Description" width="800" height="600">
</picture>
```

Сравнение форматов (одно изображение):
```
JPEG:  120 KB
WebP:   78 KB (-35%)
AVIF:   52 KB (-57%)
```

AVIF — наилучшее сжатие, но медленнее кодируется. WebP — хороший компромисс. Оба значительно лучше JPEG.

## Code Splitting: разбивка бандла

Code splitting позволяет загружать только тот JavaScript, который нужен для текущей страницы.

### Route-based splitting

```javascript
// React Router с lazy loading
import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Switch } from 'react-router-dom';

// Каждый маршрут загружается отдельным чанком
const Home = lazy(() => import('./pages/Home'));
const About = lazy(() => import('./pages/About'));
const Dashboard = lazy(() => import('./pages/Dashboard'));

function App() {
    return (
        <BrowserRouter>
            <Suspense fallback={<div>Loading...</div>}>
                <Switch>
                    <Route path="/" exact component={Home} />
                    <Route path="/about" component={About} />
                    <Route path="/dashboard" component={Dashboard} />
                </Switch>
            </Suspense>
        </BrowserRouter>
    );
}
```

Теперь пользователь, открывающий главную страницу, не загружает код Dashboard.

### Dynamic imports

```javascript
// Загрузка тяжёлой библиотеки по требованию
async function exportToPDF(data) {
    // jsPDF загружается только при клике на "Экспорт"
    const { jsPDF } = await import('jspdf');
    const doc = new jsPDF();
    doc.text(data.title, 10, 10);
    doc.save('document.pdf');
}

// С именованными чанками (webpack magic comment)
const HeavyChart = await import(
    /* webpackChunkName: "charts" */
    /* webpackPrefetch: true */
    './components/HeavyChart'
);
```

### Webpack Bundle Analysis

```bash
# Анализ бандла для поиска "толстых" зависимостей
npm install --save-dev webpack-bundle-analyzer

# webpack.config.js
const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin;
module.exports = {
    plugins: [new BundleAnalyzerPlugin()]
};

# Запуск анализа
npm run build
# Откроется интерактивная treemap в браузере
```

### Tree Shaking

Tree shaking (встряхивание дерева) удаляет неиспользуемый код из ES-модулей:

```javascript
// ПЛОХО: импорт всей библиотеки
import _ from 'lodash';
const result = _.chunk([1,2,3,4], 2); // Тянет ~70 KB!

// ХОРОШО: именованный импорт (tree shaking работает)
import chunk from 'lodash/chunk';      // ~2 KB
const result = chunk([1,2,3,4], 2);

// Или через ES modules (если пакет поддерживает)
import { chunk } from 'lodash-es';    // tree-shaking уберёт остальное
```

Tree shaking работает только с ES modules (`import/export`), не с CommonJS (`require`).

## Resource Hints: подсказки браузеру

```html
<!-- preconnect: DNS + TCP + TLS заранее для критичных доменов -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://cdn.example.com" crossorigin>

<!-- dns-prefetch: только DNS (более легковесно) -->
<link rel="dns-prefetch" href="https://api.example.com">

<!-- preload: загрузить ресурс высокого приоритета (используется на текущей странице) -->
<link rel="preload" href="hero.jpg" as="image">
<link rel="preload" href="critical.css" as="style">
<link rel="preload" href="main.js" as="script">

<!-- prefetch: загрузить ресурс для следующей навигации (низкий приоритет) -->
<link rel="prefetch" href="/next-page.js">

<!-- modulepreload: preload ES-модуль и его зависимости -->
<link rel="modulepreload" href="/app.mjs">
```

Практическое применение:

```html
<!-- Hero image: preload для LCP -->
<head>
    <link rel="preload" href="hero-image.jpg" as="image" fetchpriority="high">
</head>

<!-- Шрифты Google: preconnect + preload дескриптора -->
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" href="https://fonts.gstatic.com/s/roboto/v30/KFOmCnq.woff2" 
      as="font" type="font/woff2" crossorigin>
```

## Service Workers: оффлайн-кеширование

Service Worker — это скрипт, работающий в фоне, который может перехватывать сетевые запросы.

```javascript
// service-worker.js
const CACHE_NAME = 'my-app-v1';
const ASSETS_TO_CACHE = [
    '/',
    '/styles/main.css',
    '/scripts/app.js',
    '/images/logo.png'
];

// Установка: кеширование статики
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

// Стратегия: Cache First (статика), Network First (API)
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    if (url.pathname.startsWith('/api/')) {
        // Для API: сначала сеть, при ошибке — кеш
        event.respondWith(
            fetch(request)
                .then(response => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
                    return response;
                })
                .catch(() => caches.match(request))
        );
    } else {
        // Для статики: сначала кеш
        event.respondWith(
            caches.match(request).then(response => {
                return response || fetch(request);
            })
        );
    }
});
```

```javascript
// Регистрация Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/service-worker.js')
            .then(reg => console.log('SW registered:', reg.scope))
            .catch(err => console.error('SW registration failed:', err));
    });
}
```

В production используйте Workbox (библиотека от Google):

```javascript
// workbox-config.js
module.exports = {
    globDirectory: 'dist/',
    globPatterns: ['**/*.{html,js,css,png,webp}'],
    swDest: 'dist/sw.js',
    runtimeCaching: [
        {
            urlPattern: /^https:\/\/api\.example\.com\//,
            handler: 'NetworkFirst',
            options: { cacheName: 'api-cache', expiration: { maxAgeSeconds: 300 } }
        }
    ]
};
```

## Lighthouse: автоматический аудит

Google Lighthouse — инструмент для аудита производительности, доступности, SEO:

```bash
# CLI
npm install -g lighthouse
lighthouse https://example.com --output html --output-path report.html

# Или через Chrome DevTools → Lighthouse → Generate report
```

Типичный отчёт Lighthouse:

```
Performance: 73
  First Contentful Paint: 1.8s ✓
  Largest Contentful Paint: 3.2s ⚠
  Total Blocking Time: 450ms ⚠
  Cumulative Layout Shift: 0.12 ⚠
  Speed Index: 2.1s ✓

Opportunities:
  - Eliminate render-blocking resources (800ms savings)
  - Properly size images (340KB savings)
  - Defer offscreen images (200KB savings)
  - Remove unused JavaScript (120KB savings)
```

### Waterfall diagram

Network waterfall показывает загрузку ресурсов в хронологическом порядке:

```
Ресурс              | Время
─────────────────────────────────────────────
index.html          |████ 200ms
main.css            |    ████ 150ms     (blocking!)
normalize.css       |    ████ 100ms     (blocking!)
app.js              |        ████████ 400ms (blocking!)
hero.jpg            |                ████ 500ms
logo.svg            |                  ████ 100ms
analytics.js        |                    ██ 50ms (async)
─────────────────────────────────────────────
FCP                                ↑ 850ms
LCP                                        ↑ 1350ms
```

Цель: сдвинуть FCP и LCP как можно левее.

## Практический чеклист оптимизации

### Критический путь
```
☑ Минифицировать и сжать HTML/CSS/JS
☑ Инлайн critical CSS (выше сгиба)
☑ Defer все JS скрипты
☑ Предзагрузить LCP изображение (preload)
☑ Preconnect к критичным доменам
```

### Изображения
```
☑ Использовать WebP/AVIF
☑ Lazy load всё ниже сгиба (loading="lazy")
☑ Указывать width/height для предотвращения CLS
☑ Responsive images (srcset + sizes)
☑ Сжать изображения (squoosh, imagemin)
```

### JavaScript
```
☑ Code splitting по маршрутам
☑ Tree shaking (ES modules)
☑ Не загружать неиспользуемые библиотеки
☑ Дробить long tasks (> 50ms)
```

### Кеширование
```
☑ Хеши в именах бандлов (content hash)
☑ Cache-Control: immutable для статики
☑ Service Worker для оффлайн
☑ CDN для статики
```

## Итог

Производительность фронтенда — не одна оптимизация, а система решений. Ключевые принципы:

1. **Измеряйте сначала**: используйте Lighthouse, WebPageTest, Chrome DevTools
2. **LCP — приоритет**: предзагружайте hero-изображения, убирайте render-blocking ресурсы
3. **Lazy loading по умолчанию**: `loading="lazy"` для всего ниже сгиба
4. **Code splitting**: не грузите то, что не нужно прямо сейчас
5. **Modern formats**: WebP/AVIF, Brotli, ES modules
6. **HTTP кеширование**: content-addressed URLs + длинный max-age
7. **Service Worker**: оффлайн и повторные загрузки

## Литература

1. Grigorik, I. (2013). *High Performance Browser Networking*. O'Reilly Media. https://hpbn.co/

2. Google. *Core Web Vitals*. https://web.dev/vitals/

3. Google. *Optimize Largest Contentful Paint*. https://web.dev/optimize-lcp/

4. MDN Web Docs. *Lazy loading*. https://developer.mozilla.org/en-US/docs/Web/Performance/Lazy_loading

5. Google Developers. *Service Workers: an Introduction*. https://developers.google.com/web/fundamentals/primers/service-workers

6. Google. *Tree shaking with webpack*. https://webpack.js.org/guides/tree-shaking/

7. Mozilla. *HTTP caching*. https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching

8. Google Lighthouse. *Performance scoring*. https://developer.chrome.com/docs/lighthouse/performance/performance-scoring/

9. Wagner, J. (2020). *Workbox — JavaScript Libraries for Progressive Web Apps*. https://developers.google.com/web/tools/workbox

10. Leggett, J. (2019). *Resource Hints*. W3C Working Draft. https://www.w3.org/TR/resource-hints/

11. Sobers, R. (2019). *WPO Stats: Performance case studies*. https://wpostats.com/
