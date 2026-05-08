# SIMD и векторные инструкции (SSE, AVX, NEON)

## Введение

Когда мы умножаем две матрицы 1000×1000, мы выполняем миллиард операций умножения и сложения. Если процессор обрабатывает по одному числу за такт, это займёт секунду при частоте 1 ГГц. Но реальные процессоры делают это в десятки раз быстрее — благодаря SIMD.

SIMD (Single Instruction, Multiple Data) — принцип, при котором одна инструкция применяется одновременно к нескольким значениям данных. Вместо того чтобы складывать 8 пар чисел восемью инструкциями, SIMD складывает их одной. Это принципиальное расширение классической скалярной модели процессора.

Векторные инструкции появились ещё в суперкомпьютерах 1970-х (Cray-1), но в массовых процессорах утвердились с появлением Intel MMX (1997), SSE (1999), а сегодня достигли AVX-512 — 512-битных векторов. SIMD лежит в основе машинного обучения, обработки видео, криптографии, научных вычислений. Без понимания SIMD невозможно писать код, конкурирующий по скорости с библиотеками типа NumPy, OpenCV или TensorFlow.

---

## 1. Принцип SIMD

### 1.1 Скалярное vs Векторное выполнение

**Скалярное** (классическое):
```
a[0] + b[0] → c[0]   (такт 1)
a[1] + b[1] → c[1]   (такт 2)
a[2] + b[2] → c[2]   (такт 3)
...
a[7] + b[7] → c[7]   (такт 8)
```

**Векторное** (SIMD):
```
[a[0], a[1], a[2], ..., a[7]] + [b[0], b[1], ..., b[7]] → [c[0], c[1], ..., c[7]]  (такт 1)
```

Одна инструкция, 8 результатов. Ускорение 8× при той же частоте. Это прямое следствие закона Флинна: векторный процессор относится к классу SIMD в таксономии вычислительных архитектур.

### 1.2 Таксономия SIMD инструкций

| Архитектура | Ширина вектора | Название |
|-------------|----------------|---------- |
| x86: MMX | 64 бит (8×8 или 4×16 или 2×32) | 1997 |
| x86: SSE/SSE2 | 128 бит (4×float или 2×double) | 1999/2001 |
| x86: AVX/AVX2 | 256 бит (8×float или 4×double) | 2011/2013 |
| x86: AVX-512 | 512 бит (16×float или 8×double) | 2016 |
| ARM: NEON | 128 бит | 2004 |
| ARM: SVE | масштабируемый (128-2048 бит) | 2016 |
| RISC-V: V | масштабируемый | 2021 |
| PowerPC: AltiVec/VMX | 128 бит | 1999 |

---

## 2. Регистры SIMD: XMM, YMM, ZMM

### 2.1 x86 Регистровый файл

```
ZMM0  [511...0]  512 бит  — AVX-512
YMM0  [255...0]  256 бит  — AVX/AVX2  (нижняя половина ZMM0)
XMM0  [127...0]  128 бит  — SSE       (нижняя четверть ZMM0)
```

В 32-битном режиме: XMM0-XMM7 (8 регистров).  
В 64-битном режиме: XMM0-XMM15 (16 регистров).  
С AVX-512: ZMM0-ZMM31 (32 регистра).

Каждый регистр может интерпретироваться как массив различных типов:

```
XMM0 (128 бит):
  16 × 8-bit integers   (pcmpeqb, paddб и т.д.)
   8 × 16-bit integers  (paddw, pmullw)
   4 × 32-bit integers  (paddd, pmulld)
   2 × 64-bit integers  (paddq)
   4 × 32-bit float     (addps, mulps)
   2 × 64-bit double    (addpd, mulpd)
```

Суффиксы инструкций x86 SIMD:
- `ps` — packed single precision (float)
- `pd` — packed double precision (double)
- `epi8/16/32/64` — packed integer
- `ss/sd` — scalar single/double (операция над нижним элементом)

### 2.2 Пример: SSE инструкции

```asm
; Сложение 4 float (SSE):
movaps   xmm0, [a]      ; загрузить 4 float из a (aligned)
movaps   xmm1, [b]      ; загрузить 4 float из b
addps    xmm0, xmm1     ; xmm0 = {a[0]+b[0], a[1]+b[1], a[2]+b[2], a[3]+b[3]}
movaps   [c],  xmm0     ; сохранить результат

; AVX: 8 float одновременно:
vmovaps  ymm0, [a]
vmovaps  ymm1, [b]
vaddps   ymm0, ymm0, ymm1
vmovaps  [c],  ymm0
```

---

## 3. Intrinsics — C/C++ интерфейс к SIMD

Писать SIMD-код на ассемблере — возможно, но неудобно. Intel предоставляет **intrinsics** — C-функции, которые отображаются один-в-один на SIMD инструкции:

### 3.1 Подключение заголовков

```c
#include <immintrin.h>  // AVX, AVX2, AVX-512
#include <nmmintrin.h>  // SSE4.2
#include <smmintrin.h>  // SSE4.1
#include <tmmintrin.h>  // SSSE3
#include <pmmintrin.h>  // SSE3
#include <emmintrin.h>  // SSE2
#include <xmmintrin.h>  // SSE
```

Или просто `#include <immintrin.h>` — включает всё.

### 3.2 Типы данных

```c
__m128   // 4 × float  (SSE)
__m128d  // 2 × double (SSE2)
__m128i  // 128-bit integer vector (SSE2)

__m256   // 8 × float  (AVX)
__m256d  // 4 × double (AVX)
__m256i  // 256-bit integer (AVX2)

__m512   // 16 × float  (AVX-512)
__m512d  // 8 × double  (AVX-512)
__m512i  // 512-bit integer (AVX-512)
```

### 3.3 Пример: сложение массивов через AVX vs скалярно

```c
#include <immintrin.h>
#include <stdio.h>
#include <time.h>

#define N (1 << 24)  // 16 миллионов элементов

// Скалярная версия
void add_scalar(float *a, float *b, float *c, int n) {
    for (int i = 0; i < n; i++) {
        c[i] = a[i] + b[i];
    }
}

// AVX версия (8 float за такт)
void add_avx(float *a, float *b, float *c, int n) {
    int i = 0;
    for (; i <= n - 8; i += 8) {
        __m256 va = _mm256_loadu_ps(a + i);   // load 8 float (unaligned)
        __m256 vb = _mm256_loadu_ps(b + i);
        __m256 vc = _mm256_add_ps(va, vb);     // 8 сложений за раз
        _mm256_storeu_ps(c + i, vc);           // store 8 float
    }
    // Обработка хвоста (элементов меньше 8)
    for (; i < n; i++) {
        c[i] = a[i] + b[i];
    }
}

// AVX с выровненными данными (выровненная нагрузка быстрее):
void add_avx_aligned(float *a, float *b, float *c, int n) {
    // a, b, c должны быть выровнены на 32 байта
    int i = 0;
    for (; i <= n - 8; i += 8) {
        __m256 va = _mm256_load_ps(a + i);    // aligned load
        __m256 vb = _mm256_load_ps(b + i);
        __m256 vc = _mm256_add_ps(va, vb);
        _mm256_store_ps(c + i, vc);           // aligned store
    }
}

// Выделение выровненной памяти:
// float *a = (float *)_mm_malloc(N * sizeof(float), 32);
// free: _mm_free(a);
```

Компиляция: `gcc -O2 -mavx2 -o simd_example simd_example.c`

Практические результаты на Core i7 (8 × float за итерацию при AVX):
- Скалярная: ~60 мс
- AVX: ~12 мс (ускорение ~5×, не 8× из-за накладных расходов памяти)

### 3.4 Frequently Used Intrinsics

```c
// Загрузка/сохранение
__m256 _mm256_load_ps(float const* mem_addr);      // выровненная
__m256 _mm256_loadu_ps(float const* mem_addr);     // невыровненная
void   _mm256_store_ps(float* mem_addr, __m256 a);
void   _mm256_storeu_ps(float* mem_addr, __m256 a);

// Арифметика
__m256 _mm256_add_ps(__m256 a, __m256 b);   // a + b
__m256 _mm256_sub_ps(__m256 a, __m256 b);   // a - b
__m256 _mm256_mul_ps(__m256 a, __m256 b);   // a * b
__m256 _mm256_div_ps(__m256 a, __m256 b);   // a / b
__m256 _mm256_fmadd_ps(__m256 a, __m256 b, __m256 c); // a*b + c (FMA)

// Сравнения
__m256 _mm256_cmp_ps(__m256 a, __m256 b, int imm8);  // имм: _CMP_LT_OS и т.д.

// Перемешивание
__m256 _mm256_blend_ps(__m256 a, __m256 b, int imm8); // выбор элементов
__m256 _mm256_permute_ps(__m256 a, int imm8);          // перестановка

// Инициализация
__m256 _mm256_setzero_ps();                   // нули
__m256 _mm256_set1_ps(float a);               // broadcast одного значения
__m256 _mm256_set_ps(float e7, ..., float e0); // установка каждого элемента
```

---

## 4. Автовекторизация компилятором

### 4.1 Что такое автовекторизация

Компиляторы GCC, Clang, MSVC умеют автоматически заменять скалярные циклы на SIMD-инструкции. Это называется автовекторизацией (auto-vectorization).

```c
// Этот цикл:
void add(float *a, float *b, float *c, int n) {
    for (int i = 0; i < n; i++)
        c[i] = a[i] + b[i];
}

// GCC -O3 -march=native компилирует в:
.loop:
    vmovups  ymm0, [rsi + rax]   ; загрузить 8 float из b
    vaddps   ymm0, ymm0, [rdi + rax]  ; добавить 8 float из a
    vmovups  [rdx + rax], ymm0   ; сохранить 8 float в c
    add      rax, 32
    cmp      rax, rcx
    jl       .loop
```

### 4.2 Условия для автовекторизации

Компилятор векторизует цикл, только если:
1. Нет **зависимостей** между итерациями (c[i] не зависит от c[i-1])
2. Нет **псевдонимов указателей** (a и c не перекрываются)
3. Число итераций **известно** или можно вычислить
4. **Тип данных** поддерживается (обычно int32/int64, float, double)

```c
// НЕ векторизуется: зависимость через c
void prefix_sum(int *c, int n) {
    for (int i = 1; i < n; i++)
        c[i] = c[i-1] + c[i];  // c[i] зависит от c[i-1]
}

// НЕ векторизуется без подсказок: псевдонимы
void copy(float *a, float *b, int n) {
    for (int i = 0; i < n; i++)
        a[i] = b[i];  // компилятор не знает, перекрываются ли a и b
}

// Векторизуется с restrict:
void copy_noalias(float * restrict a, float * restrict b, int n) {
    for (int i = 0; i < n; i++)
        a[i] = b[i];  // __restrict__ говорит: a и b не перекрываются
}
```

### 4.3 Диагностика автовекторизации

```bash
# GCC: отчёт о векторизации
gcc -O3 -fopt-info-vec-optimized -o prog prog.c

# Clang: report
clang -O3 -Rpass=loop-vectorize prog.c

# Пример вывода GCC:
# prog.c:5:5: optimized: loop vectorized using 32-byte vectors
```

### 4.4 Подсказки компилятору

```c
// OpenMP SIMD directive:
#pragma omp simd
for (int i = 0; i < n; i++)
    c[i] = a[i] + b[i];

// GCC vector hint:
#pragma GCC ivdep  // игнорировать зависимости (программист гарантирует)
for (int i = 0; i < n; i++)
    c[i] = a[i+k] + b[i];

// C++17 std::execution::par_unseq (параллельно + векторно):
#include <algorithm>
#include <execution>
std::transform(std::execution::par_unseq, a, a+n, b, c,
               [](float x, float y) { return x + y; });
```

---

## 5. Применения SIMD

### 5.1 Машинное обучение

SIMD — основа высокопроизводительных ML-библиотек. Умножение матриц (GEMM) — ключевая операция нейросетей, полностью реализована через AVX-512/NEON.

```c
// Наивный matmul (scalar):
void matmul_naive(float *A, float *B, float *C, int N) {
    for (int i = 0; i < N; i++)
        for (int j = 0; j < N; j++) {
            float sum = 0.f;
            for (int k = 0; k < N; k++)
                sum += A[i*N+k] * B[k*N+j];
            C[i*N+j] = sum;
        }
}

// SIMD с FMA (Fused Multiply-Add) через AVX2+FMA:
void matmul_simd(float *A, float *B, float *C, int N) {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j += 8) {
            __m256 sum = _mm256_setzero_ps();
            for (int k = 0; k < N; k++) {
                __m256 a = _mm256_set1_ps(A[i*N+k]);     // broadcast
                __m256 b = _mm256_loadu_ps(&B[k*N+j]);
                sum = _mm256_fmadd_ps(a, b, sum);         // sum += a * b
            }
            _mm256_storeu_ps(&C[i*N+j], sum);
        }
    }
}
```

OpenBLAS, MKL, cuBLAS — все построены на таких оптимизациях плюс blocking для кеша.

### 5.2 Криптография

AES-NI — аппаратные инструкции для AES (Advanced Encryption Standard), доступные с Sandy Bridge (2010):

```c
#include <wmmintrin.h>

// Один раунд AES с помощью aesenc:
__m128i aes_encrypt_block(__m128i plaintext, __m128i key) {
    return _mm_aesenc_si128(plaintext, key);
}

// 10 раундов AES-128:
__m128i aes128_encrypt(__m128i plaintext, __m128i *round_keys) {
    __m128i state = _mm_xor_si128(plaintext, round_keys[0]);
    for (int i = 1; i < 10; i++)
        state = _mm_aesenc_si128(state, round_keys[i]);
    return _mm_aesenclast_si128(state, round_keys[10]);
}
```

Скорость AES с AES-NI: ~1-2 цикла/байт вместо ~20-50 без SIMD.

### 5.3 Обработка изображений

```c
// Конвертация RGB → Grayscale через SIMD:
// Y = 0.299*R + 0.587*G + 0.114*B

void rgb_to_gray_avx(uint8_t *rgb, uint8_t *gray, int n_pixels) {
    // Веса в fixed-point (умножаем на 256 для целочисленной арифметики):
    // R: 77 (0.299 * 256), G: 150 (0.587 * 256), B: 29 (0.114 * 256)
    __m256i wr = _mm256_set1_epi16(77);
    __m256i wg = _mm256_set1_epi16(150);
    __m256i wb = _mm256_set1_epi16(29);
    
    for (int i = 0; i < n_pixels; i += 16) {
        // Загружаем 16 пикселей RGB (48 байт) и раскладываем по каналам
        // ... (реальная реализация требует shuffle/unpack)
        // Упрощённый вариант:
        __m256i r = ...; // 16 × R (16-bit)
        __m256i g = ...; // 16 × G (16-bit)
        __m256i b = ...; // 16 × B (16-bit)
        
        __m256i y = _mm256_add_epi16(
            _mm256_add_epi16(
                _mm256_mullo_epi16(r, wr),
                _mm256_mullo_epi16(g, wg)),
            _mm256_mullo_epi16(b, wb));
        
        // Сдвиг вправо на 8 бит (делим на 256) и упаковка в uint8:
        y = _mm256_srli_epi16(y, 8);
        // ... pack и store
    }
}
```

OpenCV использует аналогичные SIMD-оптимизации для большинства функций обработки изображений.

### 5.4 Поиск в строках

```c
// Поиск байта в строке через SSE4.2 PCMPESTRI:
int find_byte_sse42(const char *str, char target, int len) {
    __m128i vtarget = _mm_set1_epi8(target);
    for (int i = 0; i < len - 15; i += 16) {
        __m128i chunk = _mm_loadu_si128((__m128i*)(str + i));
        __m128i cmp = _mm_cmpeq_epi8(chunk, vtarget);
        int mask = _mm_movemask_epi8(cmp);  // 16-bit маска совпадений
        if (mask) {
            return i + __builtin_ctz(mask);  // позиция первого совпадения
        }
    }
    // Обработка хвоста...
    return -1;
}
```

`strlen`, `memcpy`, `memset` в glibc реализованы через SIMD и обрабатывают 16-32 байта за итерацию.

---

## 6. ARM NEON

### 6.1 Архитектура NEON

ARM NEON (ARMv7, обязателен в AArch64) — 128-битные векторные регистры, 32 регистра q0-q31 (каждый = два 64-битных d-регистра).

```c
#include <arm_neon.h>

// Типы данных:
float32x4_t  // 4 × float32
float64x2_t  // 2 × float64  (AArch64)
int32x4_t    // 4 × int32
uint8x16_t   // 16 × uint8

// Сложение 4 float:
float32x4_t a = vld1q_f32(ptr_a);   // загрузить 4 float
float32x4_t b = vld1q_f32(ptr_b);
float32x4_t c = vaddq_f32(a, b);    // a + b
vst1q_f32(ptr_c, c);                 // сохранить
```

### 6.2 Пример: dot product на NEON

```c
float dot_product_neon(float *a, float *b, int n) {
    float32x4_t sum = vdupq_n_f32(0.0f);  // 4 нуля
    
    int i = 0;
    for (; i <= n - 4; i += 4) {
        float32x4_t va = vld1q_f32(a + i);
        float32x4_t vb = vld1q_f32(b + i);
        sum = vmlaq_f32(sum, va, vb);  // sum += va * vb (multiply-accumulate)
    }
    
    // Горизонтальное сложение 4 элементов:
    float32x2_t sum2 = vadd_f32(vget_low_f32(sum), vget_high_f32(sum));
    sum2 = vpadd_f32(sum2, sum2);  // попарное сложение
    float result = vget_lane_f32(sum2, 0);
    
    // Обработка хвоста:
    for (; i < n; i++)
        result += a[i] * b[i];
    
    return result;
}
```

### 6.3 NEON vs AVX — сравнение

| Характеристика | ARM NEON | x86 AVX2 | x86 AVX-512 |
|---------------|----------|----------|-------------|
| Ширина вектора | 128 бит | 256 бит | 512 бит |
| Float/инструкцию | 4 | 8 | 16 |
| Double/инструкцию | 2 | 4 | 8 |
| FMA | Да (vmlaq) | Да (_mm256_fmadd) | Да |
| Маскирование | Нет (в базовом) | Нет | Да (k-регистры) |
| Масштабируемый | ARM SVE | Нет | Нет |

Apple M-серия использует расширенный NEON с поддержкой более широких внутренних шин и агрессивной реализацией FMA.

---

## 7. AVX-512 — следующий уровень

### 7.1 Особенности AVX-512

AVX-512 — не просто расширение AVX на 512 бит. Это семейство расширений с новыми возможностями:

**Маскирование:** каждая инструкция может работать только с выбранными элементами:
```c
// AVX-512 с маской k1:
__m512 a = _mm512_load_ps(ptr);
__mmask16 mask = _mm512_cmplt_ps_mask(a, _mm512_set1_ps(0.0f));
// Занулить отрицательные элементы:
__m512 result = _mm512_mask_blend_ps(mask, a, _mm512_setzero_ps());
```

**Embedded broadcasts:** умножение вектора на скаляр без явного broadcast:
```c
// Скаляр загружается один раз и применяется к вектору:
float *ptr_scalar;
__m512 vec = _mm512_loadu_ps(ptr_vec);
__m512 result = _mm512_mul_ps(vec, _mm512_set1_ps(*ptr_scalar)); // broadcast из памяти
```

**Gather/Scatter:** невозможные до AVX-512 операции с indirect indexing:
```c
// Gather: загрузить a[indices[0]], a[indices[1]], ...
__m256i indices = _mm256_loadu_si256(ptr_indices);
__m256 gathered = _mm256_i32gather_ps(a, indices, 4);  // scale = 4 (sizeof float)
```

### 7.2 Проблема AVX-512: частота

На процессорах Intel (до Ice Lake) активация AVX-512 снижала тактовую частоту (frequency throttling). Причина: 512-битные блоки требуют больше мощности, что вызывает снижение частоты на 200-400 МГц.

Это привело к тому, что на некоторых рабочих нагрузках AVX2 (256-бит) оказывался быстрее AVX-512 на Intel! Ситуация улучшилась на Ice Lake и Sapphire Rapids.

Apple M-серия и AMD Zen 4 не имеют этой проблемы.

---

## 8. Выравнивание данных

### 8.1 Требования к выравниванию

SIMD-инструкции работают быстрее с выровненными данными. Неверное выравнивание на старых SSE-инструкциях вызывало SEGFAULT (`movaps` требует 16-байтового выравнивания).

| Инструкция | Суффикс | Требование |
|------------|---------|------------|
| SSE aligned load | `movaps`, `movapd` | 16 байт |
| SSE unaligned | `movups`, `movupd` | нет |
| AVX aligned | `vmovaps` | 32 байта |
| AVX unaligned | `vmovups` | нет |

На современных (Haswell+) процессорах неверное выравнивание для AVX не вызывает исключения и медленнее лишь незначительно. Тем не менее выравнивание остаётся хорошей практикой.

### 8.2 Выделение выровненной памяти

```c
#include <stdlib.h>
#include <stddef.h>

// C11:
float *aligned = aligned_alloc(32, N * sizeof(float));  // выравнивание 32 байта
free(aligned);

// POSIX:
float *ptr;
posix_memalign((void**)&ptr, 32, N * sizeof(float));

// Intel intrinsics:
float *ptr = (float *)_mm_malloc(N * sizeof(float), 32);
_mm_free(ptr);

// C++:
#include <memory>
// alignas в struct:
struct alignas(32) AlignedBuffer {
    float data[8];
};
```

---

## 9. Паттерны оптимизации

### 9.1 Horizontal Reduction

«Горизонтальная» операция — применить операцию ко всем элементам вектора и получить скаляр:

```c
// Сумма 8 float в YMM регистре:
float horizontal_sum_avx(__m256 v) {
    // Шаг 1: сложить попарно верхние/нижние 4 элемента
    __m128 lo = _mm256_castps256_ps128(v);    // нижние 4
    __m128 hi = _mm256_extractf128_ps(v, 1);  // верхние 4
    __m128 sum4 = _mm_add_ps(lo, hi);          // 4 элемента

    // Шаг 2: horizontal add для 4→2→1
    __m128 sum2 = _mm_hadd_ps(sum4, sum4);
    __m128 sum1 = _mm_hadd_ps(sum2, sum2);
    return _mm_cvtss_f32(sum1);
}
```

### 9.2 AOS vs SOA (Array of Structures vs Structure of Arrays)

```c
// AOS (Array of Structures) — плохо для SIMD:
struct Particle {
    float x, y, z, w;  // 4 числа, но разные компоненты
};
Particle particles[N];  // x[0],y[0],z[0],w[0], x[1],y[1],...

// SOA (Structure of Arrays) — хорошо для SIMD:
struct Particles {
    float *x;  // все x подряд
    float *y;  // все y подряд
    float *z;
    float *w;
} particles;

// SOA: обновление x с помощью AVX:
for (int i = 0; i < N; i += 8) {
    __m256 px = _mm256_loadu_ps(particles.x + i);
    __m256 vx = _mm256_loadu_ps(velocity_x + i);
    px = _mm256_add_ps(px, vx);
    _mm256_storeu_ps(particles.x + i, px);
}
// AOS: для этого нужны gather/scatter — дорого!
```

### 9.3 Prefetching

```c
// Подсказка CPU загрузить данные в кеш заранее:
for (int i = 0; i < n - 16; i += 8) {
    _mm_prefetch((char*)(a + i + 16), _MM_HINT_T0);  // предзагрузить a[i+16]
    __m256 va = _mm256_loadu_ps(a + i);
    // ... обработка
}
```

---

## 10. Сравнение производительности

### 10.1 Бенчмарк: сложение массивов

```python
# Python + NumPy (под капотом — SIMD via OpenBLAS/MKL):
import numpy as np
import time

N = 10_000_000
a = np.random.rand(N).astype(np.float32)
b = np.random.rand(N).astype(np.float32)

# Измерение:
start = time.perf_counter()
c = a + b    # NumPy использует AVX внутри
elapsed = time.perf_counter() - start
print(f"NumPy: {elapsed*1000:.1f} ms")

# Чистый Python (скалярно):
start = time.perf_counter()
c = [a[i] + b[i] for i in range(N)]
elapsed = time.perf_counter() - start
print(f"Python loop: {elapsed*1000:.1f} ms")

# Типичные результаты:
# NumPy:       ~5 ms
# Python loop: ~2000 ms
# Ускорение: ~400× (NumPy выигрывает за счёт SIMD + нет интерпретации)
```

### 10.2 Теоретический пик SIMD

Флопс (float operations per second) при различных SIMD уровнях:

```
Частота:        3 GHz
Скалярно:       3 × 10⁹ × 1 floats × 2 (FMA)    = 6 GFlops
SSE (128-bit):  3 × 10⁹ × 4 floats × 2 (FMA)    = 24 GFlops
AVX2 (256-bit): 3 × 10⁹ × 8 floats × 2 (FMA)    = 48 GFlops
AVX-512(512-bit): 3 × 10⁹ × 16 floats × 2 (FMA) = 96 GFlops

(×2 за FMA — умножение + сложение считаем за 2 операции)
```

Реальная производительность обычно 30-70% от теоретического пика из-за memory bandwidth ограничений.

---

## Заключение

SIMD — это не просто оптимизация, это изменение парадигмы. Вместо «обработки одного элемента за раз» думаем «обработка вектора данных». Это требует другого подхода к структуре данных (SOA вместо AOS), другого понимания кеш-эффектов и умения выражать алгоритмы в терминах параллельных операций.

Ключевые выводы:

1. **Автовекторизация** — первый шаг. Правильно написанный цикл (без псевдонимов, без зависимостей между итерациями) компилятор векторизует автоматически.

2. **Intrinsics** нужны, когда автовекторизация не справляется или нужна максимальная производительность (криптография, ML inference).

3. **Структура данных** важнее самого SIMD: SOA вместо AOS, выровненная память, непрерывный доступ.

4. **NumPy, OpenCV, BLAS** — уже используют SIMD. Если задача решается ими — не нужно писать intrinsics вручную.

5. **Портируемость:** `#pragma omp simd` и `std::execution::par_unseq` — более портируемые альтернативы явным intrinsics.

---

## Литература и источники

1. Intel Corporation. *Intel Intrinsics Guide*. — https://www.intel.com/content/www/us/en/docs/intrinsics-guide/ — интерактивный справочник всех SIMD intrinsics.

2. Agner Fog. (2024). *Optimizing subroutines in assembly language*. — https://agner.org/optimize/optimizing_assembly.pdf — глава о SIMD оптимизациях.

3. Leis, V. et al. (2018). *Scalable and Robust Latches and Barriers for Database Systems*. — пример SIMD в базах данных.

4. ARM Holdings. *ARM NEON Programmer's Guide*. — https://developer.arm.com/documentation/den0018/a/

5. Wikipedia. *SIMD*. — https://en.wikipedia.org/wiki/Single_instruction,_multiple_data

6. Wikipedia. *Advanced Vector Extensions*. — https://en.wikipedia.org/wiki/Advanced_Vector_Extensions

7. Fog, A. (2024). *Instruction tables*. — https://agner.org/optimize/instruction_tables.pdf — задержки и пропускная способность SIMD инструкций.

8. Lemire, D. (2019). *Parsing Gigabytes of JSON per Second*. VLDB. — https://arxiv.org/abs/1902.08318 — пример высокопроизводительного SIMD-парсинга (simdjson).

9. NumPy documentation. *Universal Functions (ufunc)*. — https://numpy.org/doc/stable/reference/ufuncs.html

10. GCC documentation. *Auto-vectorization in GCC*. — https://gcc.gnu.org/projects/tree-ssa/vectorization.html
