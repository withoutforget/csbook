# Шейдеры: вершинные, фрагментные, вычислительные — программируемые стадии конвейера

До начала 2000-х графический конвейер был фиксированным (fixed-function pipeline): разработчик мог настроить параметры освещения, текстурирования, туман — но не мог заменить саму логику. GeForce 3 (2001) изменила всё, введя программируемые вершинные и пиксельные шейдеры. Сегодня шейдеры — сердце современной графики и GPU-вычислений.

## Фиксированный vs программируемый конвейер

### Фиксированный конвейер (OpenGL 1.x / DirectX 7)

```
Вершины → Transform → Lighting → Rasterize → Texture → Output
          (fixed!)     (fixed!)              (fixed!)
```

Можно было:
- Включить/выключить освещение Phong
- Выбрать тип текстурирования
- Настроить параметры тумана

Нельзя было:
- Реализовать собственную модель освещения
- Деформировать меш в реальном времени на GPU
- Применить нестандартные post-effects

### Программируемый конвейер (OpenGL 2.0+ / DirectX 9+)

```
Вершины → [Vertex Shader] → Rasterize → [Fragment Shader] → Output
               ↑ Ваш код!                     ↑ Ваш код!
```

Шейдер — это программа, написанная на специальном языке (GLSL, HLSL, MSL), которая выполняется на GPU для каждой вершины или каждого фрагмента.

## Vertex Shader: обработка вершин

Vertex shader выполняется **один раз для каждой вершины** модели. Главная задача: трансформировать вершину из модельного пространства в экранное.

```glsl
// GLSL vertex shader (WebGL/OpenGL)
#version 300 es
precision highp float;

// Атрибуты вершины (входные данные из буфера)
in vec3 a_position;  // позиция вершины в object space
in vec3 a_normal;    // нормаль вершины
in vec2 a_texCoord;  // UV-координаты

// Uniforms (одинаковые для всех вершин)
uniform mat4 u_modelMatrix;       // Model matrix
uniform mat4 u_viewMatrix;        // View matrix  
uniform mat4 u_projectionMatrix;  // Projection matrix
uniform mat3 u_normalMatrix;      // Для корректной трансформации нормалей

// Varyings (передаются во fragment shader)
out vec3 v_worldPosition;
out vec3 v_worldNormal;
out vec2 v_texCoord;

void main() {
    // MVP трансформация
    vec4 worldPos = u_modelMatrix * vec4(a_position, 1.0);
    vec4 viewPos = u_viewMatrix * worldPos;
    
    // gl_Position — ОБЯЗАТЕЛЬНЫЙ выход: clip-space позиция
    gl_Position = u_projectionMatrix * viewPos;
    
    // Передаём данные во fragment shader
    v_worldPosition = worldPos.xyz;
    v_worldNormal = normalize(u_normalMatrix * a_normal);
    v_texCoord = a_texCoord;
}
```

### Деформация меша (vertex displacement)

```glsl
// Волны воды — вершина двигается по синусоиде
uniform float u_time;
uniform float u_waveHeight;
uniform float u_waveFrequency;

void main() {
    vec3 pos = a_position;
    
    // Вертикальное смещение по волнам
    float wave = sin(pos.x * u_waveFrequency + u_time) 
               * cos(pos.z * u_waveFrequency * 0.7 + u_time * 1.3);
    pos.y += wave * u_waveHeight;
    
    gl_Position = u_projectionMatrix * u_viewMatrix * u_modelMatrix * vec4(pos, 1.0);
}
```

## Primitive Assembly и Rasterization

После vertex shader следуют фиксированные стадии конвейера:

1. **Primitive Assembly**: вершины объединяются в примитивы (треугольники, линии, точки)
2. **Clipping**: примитивы обрезаются по clip planes (frustum culling)
3. **Perspective Division**: координаты делятся на w (перспективная проекция)
4. **Viewport Transform**: из NDC в экранные координаты
5. **Rasterization**: треугольники → фрагменты с интерполированными атрибутами

Интерполяция атрибутов (varyings) происходит автоматически:

```
Вершина A: v_color = (1,0,0) — красная
Вершина B: v_color = (0,1,0) — зелёная
Вершина C: v_color = (0,0,1) — синяя

Центр треугольника: v_color ≈ (0.33, 0.33, 0.33) — серый
(barycentric interpolation)
```

## Fragment Shader (Pixel Shader): цвет пикселя

Fragment shader выполняется для каждого фрагмента (потенциального пикселя). Получает интерполированные данные от vertex shader и должен вывести цвет.

```glsl
// GLSL fragment shader
#version 300 es
precision highp float;

// Входные данные от vertex shader (интерполированные)
in vec3 v_worldPosition;
in vec3 v_worldNormal;
in vec2 v_texCoord;

// Uniforms
uniform sampler2D u_albedoTexture;    // цветовая текстура
uniform sampler2D u_normalMap;        // карта нормалей
uniform vec3 u_lightPosition;
uniform vec3 u_lightColor;
uniform vec3 u_cameraPosition;

// Обязательный выход: цвет фрагмента
out vec4 fragColor;

void main() {
    // Читаем текстуру
    vec4 albedo = texture(u_albedoTexture, v_texCoord);
    
    // Читаем карту нормалей и преобразуем из [0,1] в [-1,1]
    vec3 normalMap = texture(u_normalMap, v_texCoord).rgb * 2.0 - 1.0;
    // (упрощённо: используем нормаль вершины)
    vec3 normal = normalize(v_worldNormal);
    
    // Phong освещение
    vec3 lightDir = normalize(u_lightPosition - v_worldPosition);
    vec3 viewDir = normalize(u_cameraPosition - v_worldPosition);
    vec3 reflectDir = reflect(-lightDir, normal);
    
    // Ambient
    float ambientStrength = 0.1;
    vec3 ambient = ambientStrength * u_lightColor;
    
    // Diffuse
    float diff = max(dot(normal, lightDir), 0.0);
    vec3 diffuse = diff * u_lightColor;
    
    // Specular (Phong)
    float specularStrength = 0.5;
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 32.0);
    vec3 specular = specularStrength * spec * u_lightColor;
    
    // Финальный цвет
    vec3 result = (ambient + diffuse + specular) * albedo.rgb;
    fragColor = vec4(result, albedo.a);
}
```

### Normal Mapping

Normal mapping позволяет имитировать высокую детализацию поверхности без дополнительных полигонов:

```glsl
// TBN матрица для преобразования нормалей из tangent space
// (требует tangent/bitangent данных от vertex shader)
in vec3 v_tangent;
in vec3 v_bitangent;
in vec3 v_normal;

void main() {
    // TBN матрица: world space ← tangent space
    mat3 TBN = mat3(
        normalize(v_tangent),
        normalize(v_bitangent),
        normalize(v_normal)
    );
    
    // Читаем нормаль из карты (tangent space)
    vec3 normalTS = texture(u_normalMap, v_texCoord).rgb * 2.0 - 1.0;
    
    // Переводим в world space
    vec3 worldNormal = normalize(TBN * normalTS);
    
    // Используем worldNormal для освещения
}
```

### Post-processing: blur и bloom

```glsl
// Gaussian blur (horizontal pass)
uniform sampler2D u_texture;
uniform float u_texelWidth; // 1.0 / screenWidth

float weights[5] = float[](0.227027, 0.316216, 0.070270, 0.316216, 0.227027);

void main() {
    vec2 tex_offset = vec2(u_texelWidth, 0.0);
    vec3 result = texture(u_texture, v_texCoord).rgb * weights[2];
    
    for (int i = 1; i < 5; i++) {
        result += texture(u_texture, v_texCoord + tex_offset * float(i)).rgb * weights[i];
        result += texture(u_texture, v_texCoord - tex_offset * float(i)).rgb * weights[i];
    }
    
    fragColor = vec4(result, 1.0);
}

// Bloom: яркие области размываются и накладываются поверх
// 1. Отрисовать сцену в HDR буфер
// 2. Извлечь яркие области (threshold)
// 3. Размыть (gaussian blur, несколько проходов)
// 4. Смешать с оригиналом (additive blending)
```

## Языки шейдеров

### GLSL (OpenGL Shading Language)

Используется в OpenGL и WebGL. C-подобный синтаксис, встроенные типы и функции для 3D:

```glsl
// Встроенные типы
float, double, int, uint, bool
vec2, vec3, vec4        // float vector
ivec2, ivec3, ivec4     // int vector
uvec2, uvec3, uvec4     // uint vector
bvec2, bvec3, bvec4     // bool vector
mat2, mat3, mat4        // матрицы
mat2x3, mat3x2...       // прямоугольные матрицы
sampler2D, samplerCube  // текстурные семплеры

// Встроенные функции
sin, cos, tan, atan
sqrt, pow, exp, log
abs, sign, floor, ceil, fract, mod
min, max, clamp, mix, smoothstep
length, normalize, dot, cross, reflect, refract
texture, textureLod

// Swizzling
vec4 color = vec4(1.0, 0.5, 0.0, 1.0);
vec3 rgb = color.rgb;     // (1.0, 0.5, 0.0)
vec2 yx  = color.yx;      // (0.5, 1.0) — переставляем!
float b  = color.b;       // 0.0
vec4 aaaa = color.aaaa;   // (1.0, 1.0, 1.0, 1.0)
```

### HLSL (High-Level Shading Language)

Используется в DirectX:

```hlsl
// HLSL — похож на GLSL, но другие ключевые слова
struct VSInput {
    float3 position : POSITION;
    float3 normal   : NORMAL;
    float2 texCoord : TEXCOORD0;
};

struct PSInput {
    float4 position : SV_POSITION;  // System Value
    float3 worldPos : TEXCOORD0;
    float3 normal   : TEXCOORD1;
    float2 texCoord : TEXCOORD2;
};

// Uniforms в HLSL — в cbuffer (constant buffer)
cbuffer PerFrame : register(b0) {
    float4x4 viewMatrix;
    float4x4 projMatrix;
    float3 cameraPos;
};

PSInput VSMain(VSInput input) {
    PSInput output;
    // ...
    return output;
}

float4 PSMain(PSInput input) : SV_TARGET {
    // ...
    return float4(color, 1.0);
}
```

### MSL (Metal Shading Language)

Язык Apple для Metal API:

```metal
#include <metal_stdlib>
using namespace metal;

struct VertexIn {
    float3 position [[attribute(0)]];
    float3 normal   [[attribute(1)]];
    float2 texCoord [[attribute(2)]];
};

vertex VertexOut vertex_main(
    VertexIn in [[stage_in]],
    constant Uniforms& uniforms [[buffer(0)]]
) {
    VertexOut out;
    out.position = uniforms.mvpMatrix * float4(in.position, 1.0);
    return out;
}

fragment float4 fragment_main(
    VertexOut in [[stage_in]],
    texture2d<float> tex [[texture(0)]],
    sampler samp [[sampler(0)]]
) {
    return tex.sample(samp, in.texCoord);
}
```

## Compute Shaders: GPU вне графики

Compute shaders позволяют использовать GPU для произвольных вычислений, не связанных с рендерингом.

```glsl
// GLSL compute shader
#version 430
layout(local_size_x = 64, local_size_y = 1, local_size_z = 1) in;

// Буферы данных
layout(std430, binding = 0) buffer InputBuffer {
    float inputData[];
};

layout(std430, binding = 1) buffer OutputBuffer {
    float outputData[];
};

void main() {
    // Индекс текущего инвоканта
    uint index = gl_GlobalInvocationID.x;
    
    // Параллельная обработка элемента массива
    outputData[index] = inputData[index] * 2.0 + 1.0;
}
```

```glsl
// Параллельная сумматорная редукция с shared memory
layout(local_size_x = 256) in;

layout(std430, binding = 0) buffer Data { float data[]; };
layout(std430, binding = 1) buffer Result { float result[]; };

shared float localSum[256];

void main() {
    uint tid = gl_LocalInvocationID.x;
    uint gid = gl_GlobalInvocationID.x;
    
    // Загружаем данные в shared memory
    localSum[tid] = data[gid];
    barrier(); // Синхронизация всей workgroup
    
    // Дерево редукции
    for (uint stride = 128; stride > 0; stride >>= 1) {
        if (tid < stride) {
            localSum[tid] += localSum[tid + stride];
        }
        barrier();
    }
    
    // Только первый тред записывает результат
    if (tid == 0) {
        result[gl_WorkGroupID.x] = localSum[0];
    }
}
```

## SPIR-V: промежуточный байткод

SPIR-V (Standard Portable Intermediate Representation) — промежуточный формат, используемый в Vulkan, OpenCL и WebGPU.

```
GLSL    ─┐
HLSL    ─┤ → [glslangValidator / DXC] → SPIR-V → [Vulkan Runtime] → GPU
MSL     ─┘
```

Преимущества SPIR-V:
- Драйвер получает более простой для компиляции код
- Меньше вариаций поведения между производителями GPU
- Можно компилировать шейдеры offline (до запуска игры)
- Поддержка нескольких языков

```bash
# Компиляция GLSL в SPIR-V
glslangValidator -V shader.vert -o shader.vert.spv
glslangValidator -V shader.frag -o shader.frag.spv

# Оптимизация SPIR-V
spirv-opt --O shader.vert.spv -o shader.vert.opt.spv

# Декомпиляция для отладки
spirv-cross shader.vert.spv --output shader_out.vert
```

## WebGL и WebGPU

### WebGL: GLSL в браузере

```javascript
// WebGL: создание и использование шейдеров
const canvas = document.getElementById('canvas');
const gl = canvas.getContext('webgl2');

const vertexShaderSource = `#version 300 es
    in vec4 a_position;
    void main() {
        gl_Position = a_position;
    }
`;

const fragmentShaderSource = `#version 300 es
    precision highp float;
    out vec4 outColor;
    void main() {
        outColor = vec4(1.0, 0.5, 0.0, 1.0); // оранжевый
    }
`;

function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error(gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
    }
    return shader;
}

const vert = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
const frag = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);

const program = gl.createProgram();
gl.attachShader(program, vert);
gl.attachShader(program, frag);
gl.linkProgram(program);
```

### WebGPU: новый стандарт

WebGPU — современный web API для GPU, поддерживающий compute shaders и WGSL:

```wgsl
// WGSL (WebGPU Shading Language)
struct VertexOutput {
    @builtin(position) position: vec4f,
    @location(0) color: vec3f,
}

@vertex
fn vs_main(@location(0) pos: vec2f) -> VertexOutput {
    var out: VertexOutput;
    out.position = vec4f(pos, 0.0, 1.0);
    out.color = vec3f(1.0, 0.5, 0.0);
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    return vec4f(in.color, 1.0);
}
```

```javascript
// WebGPU API
const adapter = await navigator.gpu.requestAdapter();
const device = await adapter.requestDevice();

const shaderModule = device.createShaderModule({ code: wgslCode });

const pipeline = device.createRenderPipeline({
    vertex: { module: shaderModule, entryPoint: 'vs_main', buffers: [...] },
    fragment: { module: shaderModule, entryPoint: 'fs_main', targets: [...] },
    primitive: { topology: 'triangle-list' }
});
```

## Отладка шейдеров

Шейдеры сложно отлаживать: нет классического debugger, нет console.log.

```glsl
// Техника 1: Визуализация через цвет
// Показать нормали:
fragColor = vec4(worldNormal * 0.5 + 0.5, 1.0);

// Показать UV:
fragColor = vec4(v_texCoord.x, v_texCoord.y, 0.0, 1.0);

// Показать глубину:
float d = (gl_FragCoord.z / gl_FragCoord.w) / farPlane;
fragColor = vec4(d, d, d, 1.0);
```

```javascript
// RenderDoc — главный инструмент отладки GPU
// Позволяет:
// - Захватить кадр
// - Просмотреть все draw calls
// - Посмотреть буферы (vertex, index, uniform)
// - Шагать по пикселям (pixel debugger)
// - Просмотреть текстуры, rendertargets

// SpectorJS — аналог для WebGL в браузере
// (расширение Chrome/Firefox)
```

## Итог

Шейдеры — программируемые ядра графического конвейера, давшие разработчикам полный контроль над каждым пикселем:

1. **Vertex shader** — трансформирует вершины, передаёт данные фрагментному
2. **Fragment shader** — вычисляет цвет каждого пикселя (освещение, текстуры, эффекты)
3. **Compute shader** — GPU-вычисления вне рендеринга (физика, ML, параллельные алгоритмы)
4. **GLSL/HLSL/MSL** — языки шейдеров с векторными типами и встроенными функциями
5. **SPIR-V** — промежуточный байткод для портабельности
6. **WebGL/WebGPU** — шейдеры в браузере

## Литература

1. Rost, R.J., Licea-Kane, B. (2009). *OpenGL Shading Language, 3rd Edition*. Addison-Wesley Professional.

2. Luna, F. (2016). *Introduction to 3D Game Programming with DirectX 12*. Mercury Learning.

3. Khronos Group. *GLSL 4.60 Specification*. https://www.khronos.org/registry/OpenGL/specs/gl/GLSLangSpec.4.60.pdf

4. Microsoft. *HLSL Reference*. https://docs.microsoft.com/en-us/windows/win32/direct3dhlsl/

5. Khronos Group. *SPIR-V Specification*. https://www.khronos.org/registry/SPIR-V/

6. GPU Gems 1, 2, 3. NVIDIA. https://developer.nvidia.com/gpugems/

7. W3C. *WebGPU Shading Language (WGSL)*. https://www.w3.org/TR/WGSL/

8. Apple. *Metal Shading Language Specification*. https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf

9. Pharr, M., Jakob, W., Humphreys, G. (2023). *Physically Based Rendering*. MIT Press.

10. Bjorge, M. *Normal Mapping Without Precomputed Tangents*. ShaderX5.
