# Растеризация vs Ray Tracing: два подхода к рендерингу

В каждом видеоигре, в каждом 3D-приложении, в каждом CGI-фильме решается одна фундаментальная задача: как превратить описание трёхмерной сцены (объекты, источники света, камера) в двумерное изображение на экране? За 50 лет компьютерной графики сформировались два принципиально разных подхода — растеризация и трассировка лучей. Оба работают, оба дают красивые картинки, но делают это совершенно по-разному.

## Растеризация: проекция треугольников

Растеризация (rasterization) — доминирующий алгоритм рендеринга в реальном времени. Каждая видеокарта, от встроенной до топовой, оптимизирована именно под него.

### Основная идея

Всё в 3D-графике состоит из треугольников. Модель персонажа, дерево, здание — всё это набор тысяч (или миллионов) треугольников в пространстве. Алгоритм растеризации:

1. **Проецирует** каждую вершину треугольника из 3D-пространства в 2D-пространство экрана
2. **Определяет**, какие пиксели экрана перекрываются каждым треугольником
3. **Вычисляет** цвет каждого пикселя (шейдер)
4. **Разрешает перекрытия** через Z-buffer

```
3D Сцена (треугольники в пространстве)
        ↓  Vertex shader (преобразование)
    Clip Space (нормализованные координаты)
        ↓  Rasterization
    Фрагменты (потенциальные пиксели)
        ↓  Z-test
    Видимые фрагменты (прошедшие Z-тест)
        ↓  Fragment shader (цвет)
    Framebuffer (финальное изображение)
```

### Z-buffer (Depth Buffer)

Ключевая структура данных растеризации — Z-buffer (или depth buffer). Это массив размером с экран, хранящий "глубину" (удалённость от камеры) для каждого пикселя.

```
Алгоритм Z-buffer:
1. Инициализировать Z-buffer значением +∞ (бесконечная глубина)
2. Для каждого треугольника:
    а. Растеризировать (найти все покрываемые пиксели)
    б. Для каждого пикселя (x, y):
        - Вычислить z-значение данной точки треугольника
        - Если z < Z-buffer[x][y]:
            Z-buffer[x][y] = z          // обновить глубину
            Framebuffer[x][y] = color   // нарисовать цвет
        - Иначе: этот треугольник скрыт, пропустить
```

```c
// Псевдокод растеризации треугольника
for each triangle T in scene:
    project T vertices to screen space
    
    // Bounding box треугольника
    int xmin = min(T.v0.x, T.v1.x, T.v2.x);
    int xmax = max(T.v0.x, T.v1.x, T.v2.x);
    int ymin = min(T.v0.y, T.v1.y, T.v2.y);
    int ymax = max(T.v0.y, T.v1.y, T.v2.y);
    
    for y in [ymin, ymax]:
        for x in [xmin, xmax]:
            if point(x,y) inside triangle:
                float z = interpolate_depth(T, x, y);
                if z < zbuffer[y][x]:
                    zbuffer[y][x] = z;
                    framebuffer[y][x] = shade(T, x, y);
```

### Scan Conversion

Эффективная растеризация не перебирает все пиксели в bounding box. Scan conversion (скан-конверсия) использует алгоритм, основанный на горизонтальных линиях:

```
Треугольник:
    A(10, 5)
   /         \
  B(3, 15)   C(20, 15)
```

Для каждой строки Y (от 5 до 15) вычисляем интервал [x_left, x_right] по граням треугольника и закрашиваем все пиксели в этом интервале. Это эффективнее перебора bbox.

GPU делает это параллельно: тысячи пикселей обрабатываются одновременно в разных вычислительных ядрах.

## Ограничения растеризации и способы их обхода

Растеризация отлично работает для отдельных объектов, но имеет проблемы с глобальными оптическими эффектами.

### Shadow Mapping

Тени в растеризации делаются через "shadow map" — двухпроходный алгоритм:

```
Проход 1 (со стороны источника света):
    → Рендерить сцену из позиции источника света
    → Сохранить Z-buffer (это и есть shadow map)

Проход 2 (обычный рендер):
    → Для каждого фрагмента:
        1. Проецировать в пространство источника света
        2. Сравнить z-значение с shadow map
        3. Если z > shadow_map[uv]: фрагмент в тени
```

Проблема: "shadow acne" (артефакты лесенки), peter-panning (тень отрывается от объекта), лестничный эффект на краях тени. Требует тонкой настройки bias и использования PCF (Percentage Closer Filtering).

### Environment Mapping (Cube Maps)

Для отражений объекта окружение захватывается в 6 направлениях (cubemap):

```
     [Top]
[Left][Front][Right][Back]
    [Bottom]
```

При рендеринге отражающей поверхности вычисляется отражённый вектор и используется как UV для семплинга cubemap. Это быстро, но статично — динамические объекты не отражаются.

### Screen-Space Reflections (SSR)

SSR — компромисс: отражения вычисляются только из того, что видно на экране. Ray march'инг в экранном пространстве:

```glsl
// Упрощённый SSR
vec3 reflectionDir = reflect(viewDir, normal);
vec3 reflectedPos = fragPos;

for (int i = 0; i < MAX_STEPS; i++) {
    reflectedPos += reflectionDir * stepSize;
    
    // Проецируем в экранные координаты
    vec2 screenPos = projectToScreen(reflectedPos);
    
    // Сравниваем глубину
    float sceneDepth = texture(depthBuffer, screenPos).r;
    if (reflectedPos.z > sceneDepth) {
        // Нашли пересечение!
        return texture(colorBuffer, screenPos).rgb;
    }
}
return fallback; // Ничего не нашли — fallback на cubemap
```

Ограничение: не работает для того, что не видно камере. Персонаж не увидит отражение своей руки за кадром.

## Ray Tracing: физически корректный рендеринг

Ray tracing (трассировка лучей) — алгоритм, моделирующий физическое поведение света.

### Основная идея: обратная трассировка

В природе свет испускается источниками, отражается от поверхностей и попадает в глаз. Трассировать прямые лучи (от источника) — неэффективно: большинство лучей не попадут в камеру. Поэтому используется **обратная** трассировка:

```
Для каждого пикселя экрана:
    1. Выпустить луч из камеры через этот пиксель в сцену
    2. Найти первое пересечение с геометрией
    3. Вычислить освещение в точке пересечения:
        а. Выпустить "shadow rays" к каждому источнику света
           (если что-то перекрывает — точка в тени)
        б. Для отражающих поверхностей: рекурсивно выпустить отражённый луч
        в. Для прозрачных: выпустить преломлённый луч
    4. Скомбинировать результаты → цвет пикселя
```

```
Камера ──────ray──────► Точка P на поверхности
                              │
                              ├──shadow_ray──► Источник света (не перекрыт → освещена)
                              │
                              ├──reflected_ray──► Вторая поверхность → ...
                              │
                              └──refracted_ray──► Сквозь прозрачный объект → ...
```

### Ray-Triangle Intersection

Нахождение пересечения луча с треугольником — базовая операция ray tracing. Используется алгоритм Möller-Trumbore:

```c
// Алгоритм Möller-Trumbore
bool ray_triangle_intersect(
    vec3 origin, vec3 direction,  // луч
    vec3 v0, vec3 v1, vec3 v2,   // вершины треугольника
    float* t, float* u, float* v  // результат: расстояние и barycentric coords
) {
    vec3 edge1 = v1 - v0;
    vec3 edge2 = v2 - v0;
    vec3 h = cross(direction, edge2);
    float a = dot(edge1, h);
    
    if (a > -EPSILON && a < EPSILON) return false; // луч параллелен треугольнику
    
    float f = 1.0 / a;
    vec3 s = origin - v0;
    *u = f * dot(s, h);
    
    if (*u < 0.0 || *u > 1.0) return false;
    
    vec3 q = cross(s, edge1);
    *v = f * dot(direction, q);
    
    if (*v < 0.0 || *u + *v > 1.0) return false;
    
    *t = f * dot(edge2, q);
    return *t > EPSILON; // пересечение впереди луча
}
```

### BVH: ускорение поиска пересечений

Наивная ray tracing для сцены с 1 миллионом треугольников: каждый луч проверяет 1 миллион треугольников. Это O(n) на луч. Для экрана $1920 \times 1080$ = 2 миллиона пикселей — это $2 \times 10^{12}$ операций в секунду. Катастрофически медленно.

**BVH (Bounding Volume Hierarchy)** — дерево ограничивающих параллелепипедов, сводящее поиск к O(log n):

```
BVH Tree:
[Вся сцена (AABB)]
    ├── [Левая половина (AABB)]
    │       ├── [Объект A]
    │       └── [Объект B]
    └── [Правая половина (AABB)]
            ├── [Объект C]
            └── [Объект D]
```

Алгоритм обхода: если луч не пересекает AABB узла — всё поддерево пропускается. Если пересекает — рекурсивно проверяем детей. Реальные узлы проверяются только для пересечённых листьев.

```c
// Упрощённый обход BVH
float trace(Ray ray, BVHNode* node) {
    if (!ray_aabb_intersect(ray, node->aabb)) return INFINITY;
    
    if (node->is_leaf) {
        return ray_triangle_intersect(ray, node->triangle);
    }
    
    float left  = trace(ray, node->left);
    float right = trace(ray, node->right);
    return min(left, right);
}
```

NVIDIA RTX аппаратно ускоряет обход BVH — отдельные RT-ядра занимаются только этим.

## Path Tracing: физически корректный глобальный рендеринг

Path tracing — расширение ray tracing, которое моделирует **все** пути света через стохастическую выборку:

```
Для каждого пикселя: (много раз, например 1000 сэмплов)
    1. Луч из камеры
    2. При пересечении: случайно выбрать новое направление (по BRDF)
    3. Рекурсивно продолжать до источника света или максимальной глубины
    4. Усреднить результаты всех сэмплов → цвет пикселя
```

Path tracing даёт физически корректные:
- Глобальное освещение (light bleeding, colour bleeding)
- Мягкие тени (area lights)
- Каустики (преломление+отражение)
- Ambient occlusion (контактные тени)
- Subsurface scattering (кожа, воск, мрамор)

Цена: для одного кадра без шума нужны тысячи сэмплов на пиксель. Именно поэтому CGI-фильмы рендерятся часами на ферме серверов. Для реального времени с 1-4 сэмплами используют нейросетевое шумоподавление (DLSS, FSR).

## Гибридный рендеринг: лучшее из обоих миров

NVIDIA RTX, AMD RX 6000+ и PlayStation 5 используют гибридный подход:

```
Основная геометрия:  Растеризация (быстро!)
Тени:               Ray traced shadows (точные!)
Отражения:          Ray traced reflections (правильные!)
Глобальное освещение: Ray traced GI (реалистично!)
Ambient Occlusion:  Ray traced AO (качественно!)
```

Например, в Microsoft Flight Simulator: вся сцена растеризируется, но тени и отражения воды — ray traced.

## Будущее рендеринга

### Neural Rendering

Нейросети начинают заменять традиционный рендеринг:

- **DLSS (Deep Learning Super Sampling, NVIDIA)**: растеризация в низком разрешении + ИИ-апскейл до нативного
- **NeRF (Neural Radiance Fields)**: сцена представлена нейросетью, которая синтезирует вид с любого угла
- **Gaussian Splatting**: сцена представлена 3D-гауссианами, рендеринг через специализированный растеризатор

### Realtime Path Tracing

С приходом NVIDIA Ada (RTX 4000) и AMD RDNA 4 количество RT-ядер выросло настолько, что некоторые игры (Portal RTX, Cyberpunk 2077 Overdrive) используют полный path tracing в реальном времени (с шумоподавлением через DLSS/FSR).

## Итог

| Аспект | Растеризация | Ray Tracing |
|---|---|---|
| Алгоритм | Проецируем треугольники → пиксели | Лучи из камеры → пересечения |
| Тени | Shadow maps (артефакты) | Точные, мягкие |
| Отражения | Фейки (cubemap, SSR) | Физически корректные |
| Скорость | Очень быстро | Медленно (1 кадр минуты) |
| Realtime | Да | Гибрид с шумоподавлением |
| Применение | Игры, CAD, VR | Кино, архитектура, CAD |

Оба алгоритма имеют своё место. Растеризация ещё долго будет основой realtime графики, постепенно дополняясь ray tracing для конкретных эффектов.

## Литература

1. Möller, T., Trumbore, B. (1997). *Fast, Minimum Storage Ray-Triangle Intersection*. Journal of Graphics Tools, 2(1), 21-28.

2. Shirley, P., Morley, R.K. (2003). *Realistic Ray Tracing, 2nd Edition*. A K Peters/CRC Press.

3. Wald, I., et al. (2007). *Ray Tracing Deformable Scenes Using Dynamic Bounding Volume Hierarchies*. ACM Transactions on Graphics.

4. Pharr, M., Jakob, W., Humphreys, G. (2023). *Physically Based Rendering: From Theory to Implementation, 4th Edition*. MIT Press. https://pbrt.org/

5. Williams, L. (1978). *Casting Curved Shadows on Curved Surfaces*. SIGGRAPH '78 (оригинальная shadow map).

6. NVIDIA. (2018). *Introduction to NVIDIA RTX and DirectX Ray Tracing*. https://developer.nvidia.com/rtx

7. McGuire, M. (2017). *Computer Graphics Archive*. https://casual-effects.com/research/McGuire2017GraphicsArchive/index.html

8. Mildenhall, B., et al. (2020). *NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis*. ECCV 2020.

9. DirectX Raytracing (DXR). *DXR specification*. https://microsoft.github.io/DirectX-Specs/d3d/Raytracing.html

10. Heitz, E., et al. (2018). *Combining Analytic Direct Illumination and Stochastic Shadows*. ACM Symposium on Interactive 3D Graphics and Games.
