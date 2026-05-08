# CUDA, OpenCL, Metal, Vulkan: API доступа к GPU

GPU — мощный вычислительный ресурс, но без правильного API его не использовать. Семейство API для GPU включает графические (OpenGL, Vulkan, DirectX, Metal) и вычислительные (CUDA, OpenCL, SYCL, ROCm) интерфейсы. Понимание различий между ними объясняет, почему ML-фреймворки "привязаны" к NVIDIA, и когда стоит рассмотреть альтернативы.

## CUDA: доминирование NVIDIA

CUDA (Compute Unified Device Architecture) — проприетарная платформа NVIDIA для GPU-вычислений. Несмотря на проприетарность, CUDA стала де-факто стандартом для научных вычислений, ML и HPC.

### Архитектура CUDA

```
Приложение (C++/Python)
    ↓
CUDA Runtime API (libcudart)
    ↓
CUDA Driver API (libcuda)
    ↓
NVIDIA Driver
    ↓
GPU Hardware
```

### Grid, Block, Thread

CUDA организует параллельные вычисления иерархически:

```
Grid (вся задача)
└── Blocks (подзадачи, выполняются на SM)
    └── Threads (отдельные потоки, по 32 в warp)

threadIdx.x/.y/.z — индекс внутри block'а
blockIdx.x/.y/.z  — индекс block'а внутри grid'а
blockDim.x/.y/.z  — размер block'а
gridDim.x/.y/.z   — размер grid'а

Глобальный индекс потока:
int i = blockIdx.x * blockDim.x + threadIdx.x;
```

```cuda
// Базовый CUDA kernel: сложение векторов
#include <cuda_runtime.h>
#include <stdio.h>

__global__ void vectorAdd(float* a, float* b, float* c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {  // Защита от выхода за границы
        c[i] = a[i] + b[i];
    }
}

int main() {
    int n = 1 << 20;  // 1M элементов
    size_t size = n * sizeof(float);
    
    // Аллоцируем на CPU (host)
    float *h_a = (float*)malloc(size);
    float *h_b = (float*)malloc(size);
    float *h_c = (float*)malloc(size);
    
    // Инициализируем
    for (int i = 0; i < n; i++) { h_a[i] = i; h_b[i] = i * 2; }
    
    // Аллоцируем на GPU (device)
    float *d_a, *d_b, *d_c;
    cudaMalloc(&d_a, size);
    cudaMalloc(&d_b, size);
    cudaMalloc(&d_c, size);
    
    // Копируем CPU → GPU
    cudaMemcpy(d_a, h_a, size, cudaMemcpyHostToDevice);
    cudaMemcpy(d_b, h_b, size, cudaMemcpyHostToDevice);
    
    // Запускаем kernel: 256 потоков на блок, ceil(n/256) блоков
    int threadsPerBlock = 256;
    int blocksPerGrid = (n + threadsPerBlock - 1) / threadsPerBlock;
    
    vectorAdd<<<blocksPerGrid, threadsPerBlock>>>(d_a, d_b, d_c, n);
    
    // Ждём завершения
    cudaDeviceSynchronize();
    
    // Копируем GPU → CPU
    cudaMemcpy(h_c, d_c, size, cudaMemcpyDeviceToHost);
    
    // Проверяем
    printf("c[0]=%f, c[1]=%f\n", h_c[0], h_c[1]); // 0.0, 3.0
    
    // Освобождаем
    cudaFree(d_a); cudaFree(d_b); cudaFree(d_c);
    free(h_a); free(h_b); free(h_c);
}
```

### CUDA Memory Model

```cuda
// Явная работа с разными типами памяти
__global__ void memoryDemo() {
    // Global memory: медленная, доступна всем
    // (выделяется через cudaMalloc)
    
    // Shared memory: быстрая, общая для всего block'а
    __shared__ float sharedData[256];
    sharedData[threadIdx.x] = threadIdx.x;
    __syncthreads();  // Барьер — все потоки block'а здесь
    float val = sharedData[255 - threadIdx.x];  // Чтение от другого потока
    
    // Local memory: в регистрах, при overflow — в global (медленно)
    float localVar = threadIdx.x * 2.0f;  // В регистре
    
    // Constant memory: только чтение, кешируется
    // (объявляется в глобальном scope: __constant__ float params[256])
}

// Constant memory
__constant__ float filterKernel[25];  // 5×5 kernel

void setFilter(float* hostKernel) {
    cudaMemcpyToSymbol(filterKernel, hostKernel, 25 * sizeof(float));
}
```

### CUDA Streams: асинхронность

```cuda
// Перекрытие вычислений и передачи данных
cudaStream_t stream1, stream2;
cudaStreamCreate(&stream1);
cudaStreamCreate(&stream2);

// Разделяем данные на две части
// Stream 1: копирует первую половину + вычисляет
cudaMemcpyAsync(d_a1, h_a, size/2, cudaMemcpyHostToDevice, stream1);
kernel<<<blocks/2, threads, 0, stream1>>>(d_a1, d_b1, n/2);
cudaMemcpyAsync(h_c1, d_c1, size/2, cudaMemcpyDeviceToHost, stream1);

// Stream 2: копирует вторую половину + вычисляет (параллельно!)
cudaMemcpyAsync(d_a2, h_a+n/2, size/2, cudaMemcpyHostToDevice, stream2);
kernel<<<blocks/2, threads, 0, stream2>>>(d_a2, d_b2, n/2);
cudaMemcpyAsync(h_c2, d_c2, size/2, cudaMemcpyDeviceToHost, stream2);

// Ждём обоих
cudaStreamSynchronize(stream1);
cudaStreamSynchronize(stream2);
```

### cuBLAS и cuDNN

```python
# PyTorch использует cuBLAS/cuDNN под капотом
import torch

# Все эти операции выполняются через cuBLAS/cuDNN
a = torch.randn(4096, 4096, device='cuda')
b = torch.randn(4096, 4096, device='cuda')
c = torch.matmul(a, b)  # cuBLAS SGEMM

# Свёрточный слой через cuDNN
conv = torch.nn.Conv2d(64, 128, 3, padding=1).cuda()
x = torch.randn(16, 64, 224, 224, device='cuda')
y = conv(x)  # cuDNN конволюция
```

cuBLAS — CUDA Basic Linear Algebra Subprograms (матричные умножения, векторные операции).
cuDNN — CUDA Deep Neural Networks (свёртки, LSTM, attention, batch normalization).

## OpenCL: кроссплатформенная альтернатива

OpenCL (Open Computing Language) — открытый стандарт Khronos Group для GPU/CPU вычислений. Работает на NVIDIA, AMD, Intel, Apple.

```c
// OpenCL код: аналог CUDA vectorAdd
const char* kernelSource = 
    "__kernel void vectorAdd(__global float* a, __global float* b, "
    "                        __global float* c, int n) {"
    "    int i = get_global_id(0);"  // аналог blockIdx.x*blockDim.x + threadIdx.x
    "    if (i < n) c[i] = a[i] + b[i];"
    "}";

// OpenCL setup (значительно более многословный, чем CUDA)
cl_platform_id platform;
clGetPlatformIDs(1, &platform, NULL);

cl_device_id device;
clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 1, &device, NULL);

cl_context context = clCreateContext(NULL, 1, &device, NULL, NULL, NULL);
cl_command_queue queue = clCreateCommandQueue(context, device, 0, NULL);

// Компиляция kernel'а в runtime!
cl_program program = clCreateProgramWithSource(context, 1, &kernelSource, NULL, NULL);
clBuildProgram(program, 1, &device, NULL, NULL, NULL);
cl_kernel kernel = clCreateKernel(program, "vectorAdd", NULL);

// Создание буферов
cl_mem d_a = clCreateBuffer(context, CL_MEM_READ_ONLY, size, NULL, NULL);
cl_mem d_b = clCreateBuffer(context, CL_MEM_READ_ONLY, size, NULL, NULL);
cl_mem d_c = clCreateBuffer(context, CL_MEM_WRITE_ONLY, size, NULL, NULL);

// Копирование данных
clEnqueueWriteBuffer(queue, d_a, CL_TRUE, 0, size, h_a, 0, NULL, NULL);
clEnqueueWriteBuffer(queue, d_b, CL_TRUE, 0, size, h_b, 0, NULL, NULL);

// Запуск
clSetKernelArg(kernel, 0, sizeof(cl_mem), &d_a);
clSetKernelArg(kernel, 1, sizeof(cl_mem), &d_b);
clSetKernelArg(kernel, 2, sizeof(cl_mem), &d_c);
clSetKernelArg(kernel, 3, sizeof(int), &n);

size_t globalSize = n, localSize = 256;
clEnqueueNDRangeKernel(queue, kernel, 1, NULL, &globalSize, &localSize, 0, NULL, NULL);
clFinish(queue);
```

**Проблема OpenCL**: несмотря на стандарт, производительность сильно различается на разных устройствах. NVIDIA реализует OpenCL без энтузиазма (продвигая CUDA). AMD имеет хорошую поддержку. Экосистема ML-библиотек значительно меньше, чем у CUDA.

### SYCL / DPC++

SYCL — современный OpenCL на C++17, разработанный Khronos и Intel:

```cpp
// SYCL (значительно удобнее OpenCL)
#include <sycl/sycl.hpp>
using namespace sycl;

int main() {
    queue q;  // Автоматически выбирает GPU
    
    buffer<float> a_buf(h_a, range<1>(n));
    buffer<float> b_buf(h_b, range<1>(n));
    buffer<float> c_buf(h_c, range<1>(n));
    
    q.submit([&](handler& h) {
        auto a = a_buf.get_access<access::mode::read>(h);
        auto b = b_buf.get_access<access::mode::read>(h);
        auto c = c_buf.get_access<access::mode::write>(h);
        
        h.parallel_for(range<1>(n), [=](id<1> i) {
            c[i] = a[i] + b[i];
        });
    });
    q.wait();
}
```

Intel DPC++ (Data Parallel C++) — компилятор SYCL с оптимизациями для Intel GPU и CPU.

## Metal: Apple GPU API

Metal — низкоуровневый GPU API Apple для macOS/iOS. Единый API для графики и вычислений.

```swift
// Metal Compute Shader (Swift + Metal Shading Language)
import Metal

let device = MTLCreateSystemDefaultDevice()!
let library = device.makeDefaultLibrary()!

// Компилируем kernel из файла .metal
let function = library.makeFunction(name: "vectorAdd")!
let pipeline = try! device.makeComputePipelineState(function: function)

let commandQueue = device.makeCommandQueue()!
```

```metal
// Metal Shading Language kernel (файл .metal)
#include <metal_stdlib>
using namespace metal;

kernel void vectorAdd(
    device const float* a [[buffer(0)]],
    device const float* b [[buffer(1)]],
    device float* c [[buffer(2)]],
    uint i [[thread_position_in_grid]]
) {
    c[i] = a[i] + b[i];
}
```

Metal используется:
- MPS (Metal Performance Shaders) — оптимизированные ML-примитивы Apple
- Core ML — фреймворк машинного обучения Apple
- Final Cut Pro, Logic Pro, Games на Apple Silicon

## Vulkan: низкоуровневый Graphics + Compute

Vulkan — низкоуровневый API от Khronos, заменивший OpenGL. Предоставляет полный контроль над GPU с минимальными накладными расходами.

```
OpenGL: Много магии за кулисами, удобно, но медленно
Vulkan: Вы контролируете всё, быстро, но много кода
```

### Ключевые концепции Vulkan

**Command Buffers** — записываем команды заранее, отправляем пачкой:

```cpp
// Запись команд в Command Buffer
VkCommandBuffer cmdBuf = ...;

VkCommandBufferBeginInfo beginInfo{};
vkBeginCommandBuffer(cmdBuf, &beginInfo);

// Начало render pass
vkCmdBeginRenderPass(cmdBuf, &renderPassInfo, VK_SUBPASS_CONTENTS_INLINE);

// Привязываем pipeline (шейдеры, состояние)
vkCmdBindPipeline(cmdBuf, VK_PIPELINE_BIND_POINT_GRAPHICS, graphicsPipeline);

// Bind vertex buffers
vkCmdBindVertexBuffers(cmdBuf, 0, 1, vertexBuffers, offsets);

// Draw call
vkCmdDraw(cmdBuf, vertexCount, 1, 0, 0);

vkCmdEndRenderPass(cmdBuf);
vkEndCommandBuffer(cmdBuf);

// Отправка на GPU
vkQueueSubmit(graphicsQueue, 1, &submitInfo, fence);
```

**Render Passes** — явное описание операций рендеринга:

```cpp
// Описываем что происходит с фреймбуфером
VkAttachmentDescription colorAttachment{};
colorAttachment.format = VK_FORMAT_B8G8R8A8_SRGB;
colorAttachment.samples = VK_SAMPLE_COUNT_1_BIT;
colorAttachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;   // Очищаем в начале
colorAttachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE; // Сохраняем в конце
// ...

// Явная синхронизация (subpass dependencies)
VkSubpassDependency dependency{};
dependency.srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
dependency.dstStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
dependency.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
```

### Vulkan для вычислений (Compute)

```glsl
// Compute shader в SPIR-V (GLSL источник)
#version 450

layout(local_size_x = 64) in;

layout(std430, binding = 0) buffer Data {
    float[] data;
};

void main() {
    uint i = gl_GlobalInvocationID.x;
    data[i] = data[i] * 2.0;
}
```

```cpp
// Dispatch compute в Vulkan
vkCmdBindPipeline(cmdBuf, VK_PIPELINE_BIND_POINT_COMPUTE, computePipeline);
vkCmdBindDescriptorSets(cmdBuf, VK_PIPELINE_BIND_POINT_COMPUTE, ...);
vkCmdDispatch(cmdBuf, groupCountX, 1, 1);  // аналог CUDA <<<grid, block>>>
```

Vulkan используется в: Doom Eternal, Dota 2, Android games, Zink (OpenGL поверх Vulkan).

## ROCm: AMD Open Ecosystem

ROCm (Radeon Open Compute) — платформа AMD, аналог CUDA для их GPU. HIP (Heterogeneous-compute Interface for Portability) — API, совместимый с CUDA:

```cpp
// HIP: почти идентичен CUDA!
#include <hip/hip_runtime.h>

__global__ void vectorAdd(float* a, float* b, float* c, int n) {
    int i = hipBlockIdx_x * hipBlockDim_x + hipThreadIdx_x;
    if (i < n) c[i] = a[i] + b[i];
}

// Переход с CUDA на HIP:
// cudaMalloc  → hipMalloc
// cudaMemcpy  → hipMemcpy
// __device__  → __device__ (то же самое)
// <<<>>>      → hipLaunchKernelGGL(...)
```

Инструмент HIPIFY автоматически конвертирует CUDA код в HIP:

```bash
# Конвертация CUDA → HIP
hipify-clang my_cuda_code.cu -o my_hip_code.hip
# Или
hipify-perl my_cuda_code.cu > my_hip_code.cpp
```

ROCm поддерживает TensorFlow, PyTorch (через torch-rocm). Основное применение — вычислительные кластеры, не требующие GPU рендеринга.

## WebGPU: будущий стандарт для веба

WebGPU — новый W3C стандарт, приходящий на смену WebGL. Основан на идеях Vulkan/Metal/DirectX 12:

```javascript
// WebGPU compute shader
const shaderCode = `
@group(0) @binding(0) var<storage, read_write> data: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
    data[gid.x] = data[gid.x] * 2.0;
}
`;

// JavaScript: настройка и запуск
const adapter = await navigator.gpu.requestAdapter();
const device = await adapter.requestDevice();

const module = device.createShaderModule({ code: shaderCode });
const pipeline = device.createComputePipeline({
    layout: 'auto',
    compute: { module, entryPoint: 'main' }
});

const buffer = device.createBuffer({
    size: data.byteLength,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST
});
device.queue.writeBuffer(buffer, 0, data);

const cmdEncoder = device.createCommandEncoder();
const pass = cmdEncoder.beginComputePass();
pass.setPipeline(pipeline);
pass.setBindGroup(0, bindGroup);
pass.dispatchWorkgroups(Math.ceil(n / 64));
pass.end();
device.queue.submit([cmdEncoder.finish()]);
```

WebGPU открывает возможности для ML inference в браузере без плагинов. Библиотека transformers.js (Hugging Face) использует WebGPU для запуска BERT/GPT в браузере.

## Сравнение и выбор API

| API | Платформы | Язык | Граф. | Вычисл. | ML |
|---|---|---|---|---|---|
| CUDA | NVIDIA only | C++/Python | Нет | Да | Доминирует |
| OpenCL | Везде | C-kernel | Частично | Да | Устарел |
| SYCL | Intel, AMD, CPU | C++17 | Нет | Да | Растёт |
| Metal | Apple only | MSL/Swift | Да | Да | Core ML |
| Vulkan | Везде | GLSL/HLSL | Да | Да | Не распр. |
| DirectX 12 | Windows/Xbox | HLSL | Да | Да | DirectML |
| ROCm/HIP | AMD | C++ | Нет | Да | PyTorch |
| WebGPU | Браузер | WGSL | Да | Да | Растёт |

### Почему CUDA доминирует в ML

1. **Экосистема**: cuDNN, cuBLAS, NCCL, cuGraph — оптимизированные примитивы
2. **Зрелость**: более 15 лет разработки и оптимизаций
3. **Tensor Cores**: специализированное железо для матричных операций
4. **Сообщество**: 99% ML-кода написано под CUDA
5. **Инвестиции NVIDIA**: $10B+ в экосистему ежегодно

**Почему переход сложен:**
- Сотни тысяч строк оптимизированного CUDA кода в PyTorch/TensorFlow
- Кастомные CUDA kernels в исследовательском коде
- Разрыв в производительности (AMD ROCm ближе, но не равен)
- Сетевые эффекты: разработчики знают CUDA

## Итог

GPU-программирование — специализированная область с богатым выбором API:

1. **CUDA** — для ML, научных вычислений, только NVIDIA
2. **OpenCL/SYCL** — кроссплатформенные альтернативы, меньше экосистема
3. **Metal** — для Apple платформ (macOS/iOS)
4. **Vulkan** — низкоуровневый портабельный graphics + compute
5. **ROCm/HIP** — AMD экосистема, совместимость с CUDA
6. **WebGPU** — будущее GPU в браузере

## Литература

1. Kirk, D., Hwu, W.M. (2022). *Programming Massively Parallel Processors, 4th Edition*. Morgan Kaufmann.

2. NVIDIA. *CUDA C++ Programming Guide*. https://docs.nvidia.com/cuda/cuda-c-programming-guide/

3. Khronos Group. *OpenCL 3.0 Specification*. https://www.khronos.org/opencl/

4. Khronos Group. *Vulkan 1.3 Specification*. https://registry.khronos.org/vulkan/specs/1.3/

5. Apple. *Metal Programming Guide*. https://developer.apple.com/documentation/metal

6. Reinders, J., Ashbaugh, B., et al. (2021). *Data Parallel C++: Mastering DPC++ for Programming of Heterogeneous Systems using C++ and SYCL*. Apress.

7. AMD. *ROCm Documentation*. https://rocm.docs.amd.com/

8. W3C. *WebGPU Specification*. https://www.w3.org/TR/webgpu/

9. Microsoft. *DirectX 12 programming guide*. https://docs.microsoft.com/en-us/windows/win32/direct3d12/

10. Peng, L., et al. (2022). *FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness*. NeurIPS 2022.
