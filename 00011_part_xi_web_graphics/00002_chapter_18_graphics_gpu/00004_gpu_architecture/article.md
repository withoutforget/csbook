# GPU Архитектура: тысячи простых ядер, SIMT, Warps

Почему нейросети обучаются на GPU, а не на CPU? Почему умножение матриц 4096×4096 на GPU занимает миллисекунды, а на CPU — секунды? Ответ в фундаментальном различии архитектур: CPU оптимизирован для последовательных вычислений с быстрым откликом, GPU — для максимальной параллельной пропускной способности.

## CPU vs GPU: философия проектирования

### CPU: несколько умных ядер

Современный процессор Intel Core i9 имеет 8-24 физических ядра. Каждое ядро может выполнять до ~4 инструкций за такт (суперскалярность) при частоте 3-5 GHz. Большую часть площади чипа занимают:

- Большие кеши L1/L2/L3 (до 64 MB)
- Сложный блок предсказания ветвлений
- Блоки внеочередного выполнения (OOO execution)
- Prefetcher для данных

Всё это нужно, чтобы один поток кода выполнялся как можно быстрее. CPU оптимизирован для **латентности** (задержки одной операции).

### GPU: тысячи простых ядер

NVIDIA RTX 4090 содержит 16 384 CUDA-ядра. Каждое ядро простое — никакого OOO execution, минимальные кеши. Но их тысячи, и они работают параллельно. GPU оптимизирован для **пропускной способности** (throughput).

```
CPU (Intel Core i9-13900K):
  24 ядра × 3.0 GHz × ~10 инструкций/такт = ~720 GFLOPS

GPU (NVIDIA RTX 4090):
  16384 ядра × 2.52 GHz × 2 (FMA) = ~82,000 GFLOPS (~82 TFLOPS)

Разница: ~114× по пиковой производительности на float32
```

```
CPU транзисторы: ~~70% — кеши и предсказание ветвлений
                  ~30% — вычислительные блоки

GPU транзисторы: ~~90% — вычислительные блоки и DRAM интерфейс
                  ~10% — небольшие кеши и управление
```

## SIMT: Single Instruction, Multiple Threads

SIMT (Single Instruction, Multiple Threads) — ключевая концепция GPU. В отличие от SIMD (Single Instruction, Multiple Data — как в CPU AVX), SIMT делает каждый поток независимым, но выполняет одну инструкцию для группы потоков одновременно.

### Warp (NVIDIA) / Wavefront (AMD)

На NVIDIA GPU потоки группируются в **warps** по 32 штуки. На AMD — **wavefronts** по 32 или 64 потока.

Все 32 потока в warp выполняют **одну и ту же инструкцию**, но над разными данными:

```
Warp 0:
  Thread 0: z[0] = x[0] + y[0]
  Thread 1: z[1] = x[1] + y[1]
  Thread 2: z[2] = x[2] + y[2]
  ...
  Thread 31: z[31] = x[31] + y[31]
← Все 32 потока выполняют ADD, но с разными адресами

Warp 1:
  Thread 32: z[32] = x[32] + y[32]
  Thread 33: z[33] = x[33] + y[33]
  ...
```

Это позволяет аппаратно упростить планировщик: вместо управления 16384 независимыми инструкциями, GPU управляет 512 warp'ами.

### Warp Divergence: проклятие ветвлений

Проблема SIMT возникает при **ветвлениях** в коде:

```cuda
// Ветвление в шейдере/CUDA kernel
if (threadIdx.x % 2 == 0) {
    result = expensiveComputation1();  // чётные потоки
} else {
    result = expensiveComputation2();  // нечётные потоки
}
```

Что происходит в warp'е из 32 потоков:

```
Шаг 1: Выполняем if-ветку (expensiveComputation1())
   Активны:   Thread 0, 2, 4, ..., 30 (16 потоков)
   Неактивны: Thread 1, 3, 5, ..., 31 (16 потоков, "маскированы")

Шаг 2: Выполняем else-ветку (expensiveComputation2())
   Активны:   Thread 1, 3, 5, ..., 31 (16 потоков)
   Неактивны: Thread 0, 2, 4, ..., 30 (16 потоков, "маскированы")

Итого: 2× медленнее, чем без ветвления!
```

Неактивные потоки "отмаскированы" — они ждут, пока выполняется ветвление для других потоков. Пропускная способность снижается.

**Как избегать warp divergence:**
```cuda
// Плохо: ветвление внутри warp
if (threadIdx.x < 16) { /* ... */ } else { /* ... */ }

// Лучше: ветвление по warp границам
if (threadIdx.x / 32 % 2 == 0) { /* ... */ } else { /* ... */ }

// Ещё лучше: избегать ветвлений в горячем коде
// Использовать branchless techniques:
float mask = (float)(threadIdx.x % 2 == 0);
result = mask * computation1() + (1 - mask) * computation2();
// Оба вычисления выполняются, но нет divergence
```

## Streaming Multiprocessor (SM): архитектурный блок

NVIDIA GPU состоит из нескольких Streaming Multiprocessors (SM). Например, RTX 4090 содержит 128 SM.

### Структура SM (NVIDIA Ampere/Ada)

```
Streaming Multiprocessor (SM):
┌──────────────────────────────────────────────┐
│  Warp Scheduler × 4  (управляет 4 warp'ами  │
│                        одновременно)          │
│                                              │
│  CUDA Cores: 128 (FP32)    64 (INT32)       │
│  Tensor Cores: 4 (матричные операции)        │
│  RT Core: 1 (ray tracing)                    │
│                                              │
│  Register File: 65536 × 32-bit регистров    │
│  L1 Cache / Shared Memory: 128 KB           │
│  L2 Cache (общий): 96 MB                    │
│                                              │
│  Load/Store Units × 32                       │
│  Special Function Units: 16                  │
└──────────────────────────────────────────────┘
```

Каждый SM может одновременно выполнять несколько warp'ов ("occupation"). Пока один warp ждёт данных из памяти, другой warp выполняется. Это латентность-скрывающая стратегия.

### Occupancy: заполненность SM

Occupancy — процент максимальных warp'ов, которые реально активны на SM:

```
RTX 4090 SM:
Максимум warp'ов на SM: 48
Если наш kernel запускает только 16 warp'ов → occupancy = 33%

Ограничения occupancy:
  - Регистры: если kernel использует 64 регистра/поток, 
               то max threads/SM = 65536/64 = 1024 = 32 warp'а
  - Shared memory: если kernel использует 64 KB/block,
                    то на SM может быть только 2 block'а
```

Высокий occupancy не всегда лучше — важна реальная пропускная способность. Иногда меньший occupancy с лучшим использованием регистров быстрее.

## Модель памяти GPU

GPU имеет несколько уровней памяти с разными характеристиками:

```
Иерархия памяти GPU (NVIDIA):

Регистры (register file):
  - Самая быстрая (~0 задержки)
  - 255 регистров на поток (65536 × 32-bit на SM)
  - Только для текущего потока

Shared Memory / L1 Cache:
  - ~32-128 KB на SM (настраиваемый split между L1 и Shared)
  - ~30-50 циклов задержки
  - Общая для всех потоков в block'е
  - Нужен явный контроль (в CUDA: __shared__)

L2 Cache:
  - ~20-96 MB (зависит от GPU)
  - ~200-400 циклов задержки
  - Общий для всего GPU

Global Memory (DRAM):
  - 16-80 GB (HBM или GDDR6X)
  - ~600-800 циклов задержки
  - Доступна всем потокам и CPU (через PCIe)

Constant Memory (только чтение):
  - 64 KB, кешируется в L1
  - Идеально для uniforms/параметров

Texture Memory (только чтение):
  - Кеш оптимизирован для 2D spatial locality
  - Аппаратная фильтрация (bilinear, trilinear)
```

### Coalescing: слияние обращений к памяти

Критичный принцип производительности: обращения к global memory от потоков в warp'е должны быть **последовательными** (coalesced).

```cuda
// ХОРОШО: coalesced access (128 байт = одна транзакция)
// Поток N обращается к data[N]
data[threadIdx.x] = value;  // Thread 0 → data[0], Thread 1 → data[1], ...

// ПЛОХО: strided access (32 отдельных транзакции)
// Поток N обращается к data[N × 32]
data[threadIdx.x * 32] = value;  // Thread 0 → data[0], Thread 1 → data[32], ...
```

```
Coalesced: 32 потока × 4 байта = 128 байт за 1 транзакцию
Strided:   32 потока × 4 байта = 128 байт за 32 транзакции!
Разница в пропускной способности: 32×
```

```cuda
// Матричное транспонирование: пример coalescing
// Задача: transposedMatrix = transpose(matrix)

// Плохо: запись неcoalesced (запись по столбцам)
__global__ void transpose_bad(float* out, float* in, int N) {
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    
    out[x * N + y] = in[y * N + x];  // out запись — strided!
}

// Хорошо: через shared memory (тайлинг)
__global__ void transpose_good(float* out, float* in, int N) {
    __shared__ float tile[32][33];  // +1 для padding (банки)
    
    int x = blockIdx.x * 32 + threadIdx.x;
    int y = blockIdx.y * 32 + threadIdx.y;
    
    // Coalesced чтение из global memory → shared memory
    tile[threadIdx.y][threadIdx.x] = in[y * N + x];
    __syncthreads();
    
    // Транспонируем блок
    x = blockIdx.y * 32 + threadIdx.x;
    y = blockIdx.x * 32 + threadIdx.y;
    
    // Coalesced запись в global memory ← shared memory
    out[y * N + x] = tile[threadIdx.x][threadIdx.y];
}
```

## Tensor Cores: матричные операции

Начиная с NVIDIA Volta (2017), GPU содержат **Tensor Cores** — специализированные блоки для матричного умножения.

```
Обычные CUDA cores:
  D = A × B + C   (одна операция FMA: float multiply-add)
  
Tensor Core (Ampere):
  D = A × B + C   (16×16×16 матрица за один тактовый цикл!)
  
  A: 16×16, FP16
  B: 16×16, FP16
  C: 16×16, FP32 (accumulate)
  D: 16×16, FP32
  
  Throughput: 256 TFLOPS (FP16) vs 82 TFLOPS (FP32) на RTX 4090
```

Tensor Cores используются:
- cuBLAS (общее матричное умножение)
- cuDNN (свёрточные нейросети)
- DLSS (нейросетевой апскейлинг)
- FlashAttention (transformer attention)

## Bandwidth vs FLOPS: реальные узкие места

Часто узким местом является не вычислительная мощность, а **пропускная способность памяти** (memory bandwidth):

```
RTX 4090:
  Пиковые FLOPS:    82 TFLOPS (FP32)
  Memory bandwidth: 1008 GB/s

Arithmetic Intensity = FLOPS / Bytes
  Матричное умножение (GEMM): ~O(N) FLOPS на O(N) bytes → высокая интенсивность
  Transpose: ~O(N) FLOPS на O(N) bytes → память ограничена

Roofline model:
  Если arithmetic intensity < peak_FLOPS / bandwidth — memory bound
  Иначе — compute bound
  
  RTX 4090 roof: 82 TFLOPS / 1008 GB/s = 81 FLOPS/byte
```

## Современные GPU архитектуры

### NVIDIA Ada Lovelace (RTX 40xx)

```
RTX 4090:
  128 SM × (128 CUDA + 4 Tensor + 1 RT) cores
  = 16384 CUDA cores
  82 TFLOPS FP32, 330 TFLOPS TF32, 1.3 PFLOPS FP8
  24 GB GDDR6X, 1008 GB/s
  5th gen Tensor Cores (Hopper) с sparse acceleration
  3rd gen RT Cores
```

### NVIDIA Hopper (H100): датацентрный GPU

```
H100 SXM5:
  132 SM
  80 GB HBM3, 3350 GB/s (3× больше Ada!)
  4th gen NVLink: 900 GB/s межузловой bandwidth
  Transformer Engine: FP8 + FP16 mixed precision
  
  67 TFLOPS FP32
  3958 TFLOPS FP8 (с sparsity)
  Специально оптимизирован для LLM inference/training
```

### AMD RDNA 3 / RDNA 4 (RX 7000/9000)

AMD использует термин **Compute Unit (CU)** вместо SM:

```
RX 7900 XTX (RDNA 3):
  96 CU × 64 stream processors = 6144 shaders
  Wavefront: 32 потока (был 64 в RDNA 1/2)
  24 GB GDDR6, 960 GB/s
  AI Accelerators (2nd gen)
  
RDNA 4 (RX 9070 XT):
  Улучшенный AI engine (4th gen)
  Поддержка ray tracing 2-й gen
```

### Apple M-series GPU

Apple M3 Ultra содержит до 80 GPU ядер — не в смысле CUDA cores, а в смысле полных SM-подобных блоков.

```
M3 Ultra GPU:
  80 GPU cores
  ~800 GFLOPS FP32 (скромно vs дискретные)
  Unified Memory (CPU и GPU делят одну DRAM!)
  
Преимущество Unified Memory:
  - Нет PCIe bottleneck при CPU-GPU transfer
  - GPU может работать с данными, загруженными CPU, без копирования
  - Bandwidth: до 800 GB/s (M2 Ultra)
```

## Заключение: когда использовать GPU

| Задача | CPU | GPU | Причина |
|---|---|---|---|
| Сортировка 1M элементов | Быстро | Сложно | Sequential, много зависимостей |
| Матрица 4096×4096 FP32 | ~100ms | ~1ms | Идеальная параллельность |
| Обучение CNN | Часы | Минуты | Свёртки = параллельные матричные умножения |
| HTTP сервер | Отлично | Не применимо | Сложная бизнес-логика, ветвления |
| Видео-кодирование | Хорошо | Отлично | NVENC/Quick Sync — специализированные блоки |
| Парсинг JSON | Отлично | Плохо | Сложные условия, нерегулярные данные |

GPU эффективен когда:
1. Одна операция применяется к тысячам элементов
2. Мало ветвлений (или ветвления когерентны)
3. Данные можно загрузить "пачками" (coalesced)
4. Операция имеет высокую arithmetic intensity

## Литература

1. Patterson, D., Hennessy, J. (2017). *Computer Organization and Design: ARM Edition*. Morgan Kaufmann.

2. Kirk, D., Hwu, W.M. (2022). *Programming Massively Parallel Processors: A Hands-on Approach, 4th Edition*. Morgan Kaufmann.

3. NVIDIA. *NVIDIA Ampere GA102 GPU Architecture Whitepaper*. https://www.nvidia.com/content/PDF/nvidia-ampere-ga-102-gpu-architecture-whitepaper-v2.pdf

4. NVIDIA. *CUDA C++ Best Practices Guide*. https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/

5. Williams, S., Waterman, A., Patterson, D. (2009). *Roofline: An Insightful Visual Performance Model for Multicore Architectures*. Communications of the ACM, 52(4), 65-76.

6. AMD. *RDNA 3 Architecture*. https://gpuopen.com/amd-rdna3-architecture/

7. Apple. *Apple M3 Chip*. https://www.apple.com/newsroom/2023/10/apple-unveils-m3-m3-pro-and-m3-max-the-most-advanced-chips-for-a-personal-computer/

8. Volkov, V. (2010). *Better Performance at Lower Occupancy*. GPU Technology Conference.

9. Harris, M. *CUDA Optimization: Memory Bandwidth and Arithmetic Intensity*. NVIDIA Developer Blog.

10. Fatahalian, K., Houston, M. (2008). *A Closer Look at GPUs*. Communications of the ACM, 51(10), 50-57.
