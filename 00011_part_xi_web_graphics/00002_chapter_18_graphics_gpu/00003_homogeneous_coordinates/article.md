# Однородные координаты и матрицы трансформаций: Model → View → Projection → Screen

Математика за трёхмерной графикой пугает многих начинающих: матрицы $4 \times 4$, однородные координаты, MVP-трансформация... Но за этим аппаратом стоит элегантная идея, позволяющая описать любую трансформацию — перенос, масштаб, поворот, перспективу — единым матричным умножением. Понимание этого — ключ к написанию собственных шейдеров и работе с 3D-движками.

## Зачем нужны матрицы $4 \times 4$

В 3D-пространстве есть три основных аффинных трансформации:

- **Масштаб** (scale): умножение координат
- **Поворот** (rotation): линейное преобразование
- **Перенос** (translation): сложение векторов

Масштаб и поворот — линейные преобразования, которые выражаются матрицей $3 \times 3$:

```
Масштаб (2x по всем осям):
[2 0 0]   [x]   [2x]
[0 2 0] × [y] = [2y]
[0 0 2]   [z]   [2z]

Поворот на угол θ вокруг Z:
[cos θ  -sin θ  0]   [x]   [x·cos θ - y·sin θ]
[sin θ   cos θ  0] × [y] = [x·sin θ + y·cos θ]
[  0       0    1]   [z]   [z]
```

Но перенос — это НЕ линейное преобразование. Его нельзя выразить матрицей $3 \times 3$:

```
Перенос на (tx, ty, tz):
x' = x + tx
y' = y + ty
z' = z + tz
```

Нет матрицы $3 \times 3$, такой что $M \times [x,y,z]^\top = [x+tx, y+ty, z+tz]^\top$ для произвольных tx, ty, tz.

### Однородные координаты: решение

Однородные координаты решают проблему добавлением четвёртого компонента `w`:

```
Точка в 3D: (x, y, z)
В однородных координатах: (x·w, y·w, z·w, w) = (X, Y, Z, W)

Обычно w = 1:
Точка (3, 4, 5) → (3, 4, 5, 1)

Обратное преобразование:
(X, Y, Z, W) → (X/W, Y/W, Z/W)
```

Теперь перенос выражается матрицей $4 \times 4$:

```
Перенос на (tx, ty, tz):
[1  0  0  tx]   [x]   [x + tx·1]   [x + tx]
[0  1  0  ty] × [y] = [y + ty·1] = [y + ty]
[0  0  1  tz]   [z]   [z + tz·1]   [z + tz]
[0  0  0   1]   [1]   [1         ]  [1     ]
```

## Основные трансформации в матричном виде

### Перенос (Translation)

```
T(tx, ty, tz) = 
[1  0  0  tx]
[0  1  0  ty]
[0  0  1  tz]
[0  0  0   1]
```

### Масштаб (Scale)

```
S(sx, sy, sz) = 
[sx  0   0   0]
[0   sy  0   0]
[0   0   sz  0]
[0   0   0   1]
```

Равномерный масштаб: `S(s, s, s)`.

### Поворот (Rotation)

Поворот вокруг оси X на угол $\theta$:

```
Rx(θ) = 
[1    0       0    0]
[0   cos θ  -sin θ  0]
[0   sin θ   cos θ  0]
[0    0       0    1]
```

Поворот вокруг оси Y на угол $\theta$:

```
Ry(θ) = 
[cos θ   0   sin θ  0]
[  0     1     0    0]
[-sin θ  0   cos θ  0]
[  0     0     0    1]
```

Поворот вокруг оси Z на угол $\theta$:

```
Rz(θ) = 
[cos θ  -sin θ  0  0]
[sin θ   cos θ  0  0]
[  0       0    1  0]
[  0       0    0  1]
```

## Составление трансформаций

Главная сила матриц — возможность **перемножать** их для создания составных трансформаций:

```
Применить масштаб, затем поворот, затем перенос:
M = T × R × S

Трансформировать точку:
p' = M × p = T × R × S × p

Умножить один раз заранее, применить много раз к вершинам!
```

Внимание: порядок важен! `T × R ≠ R × T`.

```glsl
// В шейдере: одна матрица содержит все трансформации
mat4 model = translation * rotation * scale;
gl_Position = projection * view * model * vec4(position, 1.0);
```

```python
import numpy as np

def translation_matrix(tx, ty, tz):
    return np.array([
        [1, 0, 0, tx],
        [0, 1, 0, ty],
        [0, 0, 1, tz],
        [0, 0, 0,  1]
    ], dtype=float)

def scale_matrix(sx, sy, sz):
    return np.array([
        [sx,  0,  0, 0],
        [ 0, sy,  0, 0],
        [ 0,  0, sz, 0],
        [ 0,  0,  0, 1]
    ], dtype=float)

def rotation_z_matrix(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([
        [c, -s, 0, 0],
        [s,  c, 0, 0],
        [0,  0, 1, 0],
        [0,  0, 0, 1]
    ], dtype=float)

# Составная трансформация: масштаб → поворот → перенос
T = translation_matrix(3, 0, 0)
R = rotation_z_matrix(np.pi / 4)  # 45 градусов
S = scale_matrix(2, 2, 1)

model = T @ R @ S  # @ — умножение матриц в numpy

# Применяем к точке
point = np.array([1, 0, 0, 1])
transformed = model @ point
print(transformed[:3])  # [x, y, z]
```

## MVP: Model-View-Projection

В 3D-рендеринге вершина проходит через три пространства:

```
Object Space         → Model Matrix   →  World Space
World Space          → View Matrix    →  View/Camera Space
View/Camera Space    → Projection     →  Clip Space
Clip Space           → Perspective    →  NDC (Normalized Device Coordinates)
NDC                  → Viewport       →  Screen Space
```

### Model Matrix: объект → мировое пространство

Model matrix определяет, где, с каким поворотом и масштабом объект расположен в мировом пространстве:

```python
# Создаём дерево: масштаб ×2, поворот 30°, перемещение на (5, 0, 10)
def create_tree_model_matrix():
    T = translation_matrix(5, 0, 10)   # Позиция в мире
    R = rotation_y_matrix(np.radians(30))  # Поворот
    S = scale_matrix(2, 2, 2)          # Масштаб
    return T @ R @ S

model_matrix = create_tree_model_matrix()
```

### View Matrix: мировое → пространство камеры

View matrix переводит мир в систему координат камеры. Вычисляется через `lookAt`:

```python
def look_at(eye, center, up):
    """
    eye: позиция камеры
    center: куда смотрит камера
    up: вектор "вверх"
    """
    f = normalize(center - eye)  # forward
    r = normalize(np.cross(f, up))  # right
    u = np.cross(r, f)             # up (пересчитанный)
    
    # Матрица поворота (inverse = transpose для ортогональной матрицы)
    rotation = np.array([
        [r[0], r[1], r[2], 0],
        [u[0], u[1], u[2], 0],
        [-f[0], -f[1], -f[2], 0],
        [0, 0, 0, 1]
    ])
    
    # Матрица переноса (двигаем мир, а не камеру)
    translation = translation_matrix(-eye[0], -eye[1], -eye[2])
    
    return rotation @ translation

view = look_at(
    eye=np.array([0, 5, 10]),     # Камера
    center=np.array([0, 0, 0]),   # Смотрит на начало координат
    up=np.array([0, 1, 0])        # "Вверх" — ось Y
)
```

### Projection Matrix: перспективная проекция

Перспективная проекция создаёт иллюзию глубины: далёкие объекты кажутся меньше.

```python
def perspective_matrix(fov_y, aspect, near, far):
    """
    fov_y: вертикальный угол обзора в радианах
    aspect: ширина / высота
    near: ближняя плоскость отсечения
    far: дальняя плоскость отсечения
    """
    f = 1.0 / np.tan(fov_y / 2)
    
    return np.array([
        [f / aspect, 0,           0,                       0],
        [0,          f,           0,                       0],
        [0,          0, (far + near) / (near - far),      2 * far * near / (near - far)],
        [0,          0,          -1,                       0]
    ])

projection = perspective_matrix(
    fov_y=np.radians(45),  # 45° FOV
    aspect=16/9,           # Широкоэкранный
    near=0.1,
    far=1000.0
)
```

После умножения на projection matrix, w-компонент вершины != 1. GPU автоматически делит x, y, z на w (перспективное деление):

```
Если w = 5:
(5x, 5y, 5z, 5) → (x, y, z, 1) — после perspective division

Далёкие объекты имеют большее w → координаты делятся на большее число → объект меньше
```

### Ортографическая проекция

```python
def orthographic_matrix(left, right, bottom, top, near, far):
    """Параллельная проекция, нет перспективного уменьшения"""
    return np.array([
        [2/(right-left), 0, 0, -(right+left)/(right-left)],
        [0, 2/(top-bottom), 0, -(top+bottom)/(top-bottom)],
        [0, 0, -2/(far-near), -(far+near)/(far-near)],
        [0, 0, 0, 1]
    ])
```

Ортографическая проекция используется для: 2D-игр, UI-рендеринга, технических чертежей, shadow map (для направленного света).

## Frustum Culling: отброс невидимой геометрии

Frustum (усечённая пирамида) — видимый объём камеры. Всё вне frustum видеть нельзя → не нужно рендерить.

```
     near plane
    /─────────\
   /   Camera  \
  /─────────────\
 /               \
/─────────────────\ far plane
```

Frustum culling проверяет, пересекается ли bounding box объекта с frustum. Если нет — объект пропускается целиком (экономим vertex shader на тысячах вершин).

```python
def is_in_frustum(point_world, mvp_matrix):
    """Проверка точки на видимость через clip space"""
    clip = mvp_matrix @ np.append(point_world, 1)
    
    # В clip space точка видима если:
    # -w <= x <= w, -w <= y <= w, 0 <= z <= w (DirectX / -w <= z <= w в OpenGL)
    w = clip[3]
    return (
        -w <= clip[0] <= w and
        -w <= clip[1] <= w and
        0 <= clip[2] <= w  # DirectX стиль
    )
```

## Near/Far Planes и Z-precision

Near и far planes определяют диапазон глубин. Слишком большой диапазон вызывает "z-fighting":

```
near = 0.01, far = 10000.0:
Z-precision у near plane: хорошая
Z-precision у far plane:  очень плохая (z-fighting!)

Причина: Z-buffer хранит z/w, а не линейный z
Большинство Z-bits расходуется на ближние объекты
```

```
near = 0.1, far = 1000.0:
far/near = 10000 — разумный диапазон

near = 0.01, far = 100000.0:
far/near = 10000000 — слишком много, артефакты
```

**Обратный Z-buffer (Reverse Z)**: вместо стандартного диапазона [0,1] для близких объектов, использовать [1,0] — ближние объекты = 1, дальние = 0. Это улучшает точность, поскольку в float числах точность выше у чисел, близких к нулю.

## Gimbal Lock и кватернионы

Поворот через Euler angles (yaw, pitch, roll) страдает от gimbal lock — потери степени свободы при выравнивании осей:

```
Pitch = 90°: ось X поворота выровнялась с осью Z
→ Yaw и Roll теперь делают одно и то же!
→ Потеряна одна степень свободы
```

Кватернионы (quaternions) — математический объект для поворотов, избегающий gimbal lock:

```python
# Кватернион: q = w + xi + yj + zk
# |q| = 1 для поворота
# w = cos(θ/2), [x,y,z] = sin(θ/2) × axis

import numpy as np

def quaternion_from_axis_angle(axis, angle):
    """Создать кватернион из оси и угла"""
    axis = normalize(axis)
    half_angle = angle / 2
    return np.array([
        np.cos(half_angle),
        np.sin(half_angle) * axis[0],
        np.sin(half_angle) * axis[1],
        np.sin(half_angle) * axis[2]
    ])

def quaternion_multiply(q1, q2):
    """Перемножение кватернионов (составление поворотов)"""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array([
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2
    ])

def quaternion_to_matrix(q):
    """Конвертация кватерниона в матрицу 4×4"""
    w, x, y, z = q
    return np.array([
        [1-2*y*y-2*z*z,  2*x*y-2*z*w,   2*x*z+2*y*w, 0],
        [2*x*y+2*z*w,   1-2*x*x-2*z*z,  2*y*z-2*x*w, 0],
        [2*x*z-2*y*w,    2*y*z+2*x*w,  1-2*x*x-2*y*y, 0],
        [0,              0,              0,            1]
    ])
```

### SLERP: интерполяция поворотов

SLERP (Spherical Linear Interpolation) — правильный способ интерполировать между двумя поворотами:

```python
def slerp(q1, q2, t):
    """Сферическая линейная интерполяция кватернионов"""
    # Угол между кватернионами
    dot = np.dot(q1, q2)
    
    # Убедиться, что идём по кратчайшей дуге
    if dot < 0:
        q2 = -q2
        dot = -dot
    
    if dot > 0.9995:
        # Угол очень мал — линейная интерполяция
        result = q1 + t * (q2 - q1)
        return normalize(result)
    
    theta_0 = np.arccos(dot)    # угол начала
    theta = theta_0 * t          # текущий угол
    
    sin_theta = np.sin(theta)
    sin_theta_0 = np.sin(theta_0)
    
    s1 = np.cos(theta) - dot * sin_theta / sin_theta_0
    s2 = sin_theta / sin_theta_0
    
    return s1 * q1 + s2 * q2
```

## Viewport Transform: NDC → экран

После perspective division координаты в NDC (Normalized Device Coordinates):
- $x \in [-1, 1]$
- $y \in [-1, 1]$
- $z \in [0, 1]$ (DirectX) или $z \in [-1, 1]$ (OpenGL)

Viewport transform конвертирует в экранные пиксели:

```
x_screen = (x_ndc + 1) / 2 × screenWidth  + viewportX
y_screen = (1 - y_ndc) / 2 × screenHeight + viewportY
```

```c
// OpenGL viewport
glViewport(0, 0, 1920, 1080);  // x, y, width, height

// DirectX viewport
D3D11_VIEWPORT vp = {0, 0, 1920, 1080, 0.0f, 1.0f};
```

## Полный пример в GLSL

```glsl
// Vertex shader с полным MVP
#version 300 es
precision highp float;

in vec3 a_position;
in vec3 a_normal;
in vec2 a_uv;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

out vec3 v_fragPos;
out vec3 v_normal;
out vec2 v_uv;

void main() {
    // Мировая позиция (для освещения)
    vec4 worldPos = u_model * vec4(a_position, 1.0);
    v_fragPos = worldPos.xyz;
    
    // Нормаль в мировом пространстве
    // Используем transpose(inverse(model)) для корректного масштабирования
    mat3 normalMatrix = mat3(transpose(inverse(u_model)));
    v_normal = normalize(normalMatrix * a_normal);
    
    v_uv = a_uv;
    
    // Clip space позиция
    gl_Position = u_projection * u_view * worldPos;
}
```

## Итог

Математика 3D-трансформаций строится на нескольких ключевых идеях:

1. **Однородные координаты** (4D) позволяют выразить перенос как матричное умножение
2. **Матрицы $4 \times 4$** объединяют все аффинные трансформации в единый формат
3. **Составление** трансформаций через умножение матриц (порядок важен!)
4. **MVP pipeline**: Object → World → Camera → Clip → NDC → Screen
5. **Frustum culling** позволяет не рендерить невидимые объекты
6. **Кватернионы** избегают gimbal lock и обеспечивают корректную интерполяцию поворотов

## Литература

1. Akenine-Möller, T., Haines, E., Hoffman, N. (2018). *Real-Time Rendering, 4th Edition*. A K Peters/CRC Press.

2. Shirley, P., Marschner, S. (2009). *Fundamentals of Computer Graphics, 3rd Edition*. A K Peters.

3. Foley, J.D., van Dam, A., Feiner, S.K., Hughes, J.F. (1990). *Computer Graphics: Principles and Practice*. Addison-Wesley.

4. Lengyel, E. (2011). *Mathematics for 3D Game Programming and Computer Graphics, 3rd Edition*. Cengage Learning.

5. Goldman, R. (2009). *An Integrated Introduction to Computer Graphics and Geometric Modeling*. CRC Press.

6. Vince, J. (2011). *Quaternions for Computer Graphics*. Springer.

7. Scratchapixel. *The Perspective and Orthographic Projection Matrix*. https://www.scratchapixel.com/lessons/3d-basic-rendering/perspective-and-orthographic-projection-matrix

8. LearnOpenGL. *Transformations*. https://learnopengl.com/Getting-started/Transformations

9. Khronos Group. *OpenGL Mathematics (GLM)*. https://glm.g-truc.net/

10. Engel, W., et al. (2008). *ShaderX6: Advanced Rendering Techniques*. Charles River Media.
