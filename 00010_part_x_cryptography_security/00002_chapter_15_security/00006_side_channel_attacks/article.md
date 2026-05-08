# Side-channel атаки: Spectre, Meltdown, timing attacks

## Введение

Side-channel атаки (атаки по побочным каналам) используют информацию, утекающую не через прямые программные интерфейсы, а через физические или архитектурные характеристики: время выполнения, потребление энергии, электромагнитное излучение, кэш процессора. Это принципиально иной класс атак: уязвимость не в логике программы, а в том, как «железо» выполняет код.

Meltdown и Spectre (2018) показали, что фундаментальные оптимизации CPU — out-of-order execution и speculative execution — создают уязвимости, позволяющие одному процессу читать память другого. Эти уязвимости повлияли на все процессоры последних 20 лет и потребовали дорогостоящих программных исправлений.

---

## 1. Timing Attacks — атаки по времени

### Принцип

Если время выполнения операции зависит от секретных данных — атакующий, измеряя время, может извлечь информацию о секрете.

### Небезопасное сравнение строк

```python
import time
import statistics

# УЯЗВИМЫЙ КОД: обычное сравнение
def vulnerable_check_password(stored_hash: str, provided_hash: str) -> bool:
    return stored_hash == provided_hash
    # Python string == возвращает False при первом несовпадении!
    # Время зависит от количества совпавших байт

# Демонстрация timing leak
def measure_comparison_time(expected: str, actual: str, n_runs: int = 10000) -> float:
    times = []
    for _ in range(n_runs):
        start = time.perf_counter_ns()
        expected == actual
        elapsed = time.perf_counter_ns() - start
        times.append(elapsed)
    return statistics.median(times)

expected = "correct_hmac_value_here_abcdef12"

# Разные "угадываемые" значения
wrong_first = "Xcorrect_hmac_value_here_abcdef12"[1:]   # Первый символ неверный
wrong_mid = "correct_hmac_Xalue_here_abcdef12"           # Середина неверная
wrong_last = "correct_hmac_value_here_abcdef1X"          # Последний символ неверный

# В теории wrong_first должен быть чуть быстрее (меньше совпавших байт)
# На практике с современными CPU и кешированием разница мала
# но при многократных измерениях наблюдаема

print("Концептуальная демонстрация (реальные числа зависят от платформы):")
print(f"wrong_first: {measure_comparison_time(expected, wrong_first):.0f} нс")
print(f"wrong_last: {measure_comparison_time(expected, wrong_last):.0f} нс")
```

### Constant-time сравнение

```python
import hmac
import secrets

# БЕЗОПАСНО: constant-time сравнение
def safe_compare(a: bytes, b: bytes) -> bool:
    """Сравнение за постоянное время независимо от содержимого"""
    return hmac.compare_digest(a, b)
    # XOR всех байт попарно, всегда проходит все N байт

# Реализация constant-time compare:
def constant_time_compare(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return False
    
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y  # XOR каждой пары байт, накапливаем разницу
    
    return result == 0  # 0 только если все байты одинаковы

# Тест
a = b"correct_token_12345678901234"
b = b"correct_token_12345678901234"
c = b"wrong___token_12345678901234"

print(f"a == b: {constant_time_compare(a, b)}")   # True
print(f"a == c: {constant_time_compare(a, c)}")   # False
print(f"hmac: {hmac.compare_digest(a, b)}")       # True
```

### Timing attack на RSA (Bleichenbacher / Kocher 1996)

Классическая атака Пола Кочера (Paul Kocher, 1996): измеряя время операции `d = c^d mod n`, можно побитово восстановить `d`.

Bit-by-bit: для каждого бита `d_i` время операции различается — если в алгоритме возведения в степень есть branch по биту.

**Защита:** Montgomery ladder — алгоритм возведения в степень без branching по секретным битам; Blind RSA (рандомизация перед операцией).

---

## 2. Cache Timing Attacks

### Cache Side Channel

Современные CPU имеют иерархию кешей (L1/L2/L3). Доступ к данным в кеше: ~4-10 тактов. К RAM: ~200 тактов. Разница измерима.

```python
import time

# Демонстрация разницы кеш/RAM доступа
def demonstrate_cache_timing():
    import array
    
    # Создаём массив на несколько страниц
    data = array.array('B', [0] * (4 * 1024 * 1024))  # 4 МБ
    
    # Прогреваем кеш: читаем начало
    warmup = data[0]
    
    # Измеряем доступ к данным В кеше
    start = time.perf_counter_ns()
    for _ in range(1000):
        x = data[0]  # В кеше
    cached_time = (time.perf_counter_ns() - start) / 1000
    
    # Сброс кеша через чтение большого объёма
    for i in range(0, len(data), 64):
        _ = data[i]
    
    # Измеряем доступ к данным вне кеша
    # (в реальной атаке нужно точно сбросить кеш через clflush или eviction)
    start = time.perf_counter_ns()
    x = data[2 * 1024 * 1024]  # Давно не в кеше
    uncached_time = time.perf_counter_ns() - start
    
    print(f"Доступ (в кеше): ~{cached_time:.1f} нс")
    print(f"Доступ (не в кеше): ~{uncached_time:.1f} нс")
    print("Разница измерима → cache timing side channel!")

demonstrate_cache_timing()
```

### Flush+Reload

Технология Flush+Reload используется в атаках Spectre и множестве других:

```
Атака Flush+Reload:
1. Flush: злоумышленник принудительно выгружает целевую строку кеша (clflush)
2. Wait: жертва выполняет операцию, которая (возможно) читает секретные данные
3. Reload: злоумышленник читает ту же строку кеша и измеряет время
   - Быстро (~4 нс) → жертва читала эти данные → кеш прогрет
   - Медленно (~200 нс) → жертва не читала → кеш холодный

Пример: жертва делает table[secret_byte * 4096]
Злоумышленник: проверяет каждый из 256 слотов table[]
Быстрый слот → secret_byte = index
```

### AES S-box Timing Attack

```python
# Почему AES S-box уязвим к timing attack на CPU без AES-NI:

# Программная реализация AES использует таблицу S_BOX[256]
# Обращение: S_BOX[plaintext[i] ^ key[i]]
# Таблица может не поместиться в кеш (256 байт × 4 таблицы = 1 KB)
# 
# Если secret_byte → S_BOX[x] попадает в определённую строку кеша,
# злоумышленник, измеряя время AES операции и имея доступ к кешу,
# может восстановить ключ

# РЕШЕНИЕ: AES-NI (аппаратные инструкции)
# Intel AESENC, AESDEC выполняются за постоянное время, без table lookups
# В Python cryptography lib используются AES-NI автоматически если доступны

import subprocess
result = subprocess.run(
    ['python3', '-c', '''
from cryptography.hazmat.bindings._rust import openssl as _openssl
print("AES-NI:", "SUPPORTED" if hasattr(_openssl, "AES") else "NOT DETECTED")
'''], capture_output=True, text=True
)
print(result.stdout.strip())
```

---

## 3. Meltdown (2018)

### Принцип

Meltdown — уязвимость в Intel CPU (и некоторых ARM), опубликована в январе 2018 года командами Google Project Zero, Cyberus Technology и TU Graz.

Эксплуатирует **out-of-order execution** (выполнение инструкций не по порядку для ускорения):

```
Нормальное поведение:
  mov rax, [kernel_address]  ; чтение kernel памяти
  ; Исключение! (пользователь не имеет доступа)
  ; rax никогда не получает значение

Out-of-order execution реально делает:
  1. Спекулятивно загружает kernel_address в rax (до проверки прав!)
  2. Использует rax в следующих инструкциях СПЕКУЛЯТИВНО
  3. Обнаруживает нарушение прав → откатывает состояние регистров
  4. Генерирует исключение

Но! Спекулятивные инструкции оставили СЛЕД в кеше:
  ; Speculative load оставляет след в кеше!
  movzx rcx, byte [rax]        ; Загружаем байт из kernel (спекулятивно!)
  shl rcx, 12                   ; Умножаем на 4096 (размер страницы)
  mov rbx, [probe_array + rcx] ; Обращаемся к probe_array[byte * 4096]
                                ; ЭТОТ СЛЕД ОСТАЁТСЯ В КЕШЕ!

Атакующий Flush+Reload: измеряет время для каждого probe_array[i*4096]
  Быстрый = этот индекс i = значение секретного байта!
```

### Исправление: KPTI (Kernel Page-Table Isolation)

До Meltdown: kernel memory всегда маппировалась в address space процессов (для быстрых syscall). После Meltdown: KPTI разделяет таблицы страниц:

```
До KPTI:
  Процесс видит: user pages + kernel pages (недоступны, но маппированы)
  Переключение в kernel: просто меняем protection bits (быстро)

После KPTI (Linux 4.15+):
  Два набора таблиц страниц:
  - User mode: только user pages, NO kernel pages вообще
  - Kernel mode: kernel + user pages
  Переключение user↔kernel: смена cr3 (дорогая операция!)

Цена KPTI: 5-30% замедление для syscall-интенсивных нагрузок
  Для OLTP баз данных на старых Intel: значительный регресс
```

---

## 4. Spectre (2018)

### Принцип — Отравление предсказателя переходов

Spectre эксплуатирует **branch predictor** (предсказатель ветвления). CPU предсказывает направление условного перехода и спекулятивно выполняет инструкции до проверки условия.

```
Spectre Variant 1 (bounds check bypass):

Нормальный код:
  if (index < array_size):      // bounds check
      return array[index]       // safe access

Spectre атака:
  1. "Тренируем" предсказатель: много раз вызываем функцию с in-bounds index
     → предсказатель ожидает: index < array_size ВСЕГДА True
  
  2. Вызываем с out-of-bounds secret_index (index >= array_size)
     → предсказатель спекулятивно выполняет array[secret_index] до проверки!
     
  3. Утечка через кеш (Flush+Reload):
     value = array[secret_index]          // спекулятивно
     tmp = probe_array[value * 4096]      // оставляет след в кеше
  
  4. Bounds check обнаруживает ошибку → откат
     НО! Кеш уже "загрязнён" → атакующий читает secret_index
```

### Почему Spectre труднее исправить

Meltdown — конкретная hardware ошибка Intel, исправляется KPTI.

Spectre — это фундаментальное свойство branch prediction + speculative execution. Полное исправление потребовало бы отключения этих оптимизаций — огромная потеря производительности.

```bash
# Проверить статус mitigation на Linux
cat /sys/devices/system/cpu/vulnerabilities/*
# meltdown: Mitigation: PTI
# spectre_v1: Mitigation: usercopy/swapgs barriers and __user pointer sanitization
# spectre_v2: Mitigation: Retpolines, IBPB: conditional, IBRS_FW, STIBP: conditional, RSB filling

# Каждая mitigation имеет свою цену производительности
```

### Retpoline — митигация Spectre V2

```
Обычный indirect call (уязвим):
  call [rax]    ; Какой адрес в rax? Предсказатель не знает, угадывает
                ; → спекулятивно выполняет инструкции по угаданному адресу

Retpoline (Return Trampoline, Google):
  call setup_retpoline
  capture_spec:
    pause               ; Задержка спекуляции
    jmp capture_spec    ; Бесконечный цикл — предсказатель «уходит» сюда
  setup_retpoline:
    mov [rsp], rax      ; Подменяем адрес возврата на настоящую цель
    ret                 ; ret → спекулятивно идёт в capture_spec (безопасно!)
                        ; реально → идёт по rax (правильная цель)
```

---

## 5. Power Analysis Attacks

Атаки по энергопотреблению (Paul Kocher et al., 1999):

- **SPA (Simple Power Analysis):** измерение потребляемой мощности при одном выполнении криптоопераций
- **DPA (Differential Power Analysis):** статистический анализ многих измерений для извлечения ключа

Применяется к смарт-картам, FPGA. Защита: рандомизация операций (mask), балансировка мощности.

---

## 6. Защиты от side-channel атак

### Constant-time программирование

```c
// Constant-time select (без branching):
// Вернуть a если mask == 0xFFFFFFFF, b если mask == 0x00000000
uint32_t ct_select(uint32_t mask, uint32_t a, uint32_t b) {
    return (a & mask) | (b & ~mask);
    // Нет if/else → нет branching → нет cache/timing leak
}

// Constant-time compare:
int ct_memcmp(const void *a, const void *b, size_t len) {
    const uint8_t *ua = a, *ub = b;
    uint8_t result = 0;
    for (size_t i = 0; i < len; i++) {
        result |= ua[i] ^ ub[i];  // XOR все байты
    }
    return result == 0;  // Всегда проходим все len байт!
}
```

```python
# Python: используйте hmac.compare_digest() — это constant-time сравнение
import hmac

def safe_token_verify(expected: bytes, received: bytes) -> bool:
    return hmac.compare_digest(expected, received)

# Для AES используйте cryptography library с AES-NI поддержкой
# Не пишите AES вручную на Python!
```

### LFENCE — барьер для спекуляции

```c
// Prevent speculative execution past LFENCE
static inline void lfence(void) {
    __asm__ volatile("lfence" : : : "memory");
}

// Патч для Spectre V1:
if (index < array_size) {
    lfence();  // Барьер: ждём завершения bounds check до спекуляции
    return array[index];
}
```

### Retpoline в компиляторе

```bash
# GCC/Clang поддерживают retpoline:
gcc -mindirect-branch=thunk -mfunction-return=thunk myprogram.c
# или для всего ядра:
# CONFIG_RETPOLINE=y в Linux kernel config
```

---

## 7. Проверка уязвимостей

```python
import subprocess

def check_cpu_vulnerabilities() -> dict:
    """Проверка статуса mitigation на Linux"""
    vuln_path = "/sys/devices/system/cpu/vulnerabilities/"
    
    try:
        result = subprocess.run(
            ['find', vuln_path, '-type', 'f', '-exec', 'echo', '{}:', ';',
             '-exec', 'cat', '{}', ';'],
            capture_output=True, text=True
        )
        
        vulnerabilities = {}
        for line in result.stdout.split('\n'):
            if ':' in line and vuln_path in line:
                name = line.replace(vuln_path, '').rstrip(':')
                vulnerabilities[name] = next(
                    (l for l in result.stdout.split('\n') if vuln_path not in l and l.strip()),
                    "unknown"
                )
        return vulnerabilities
    except Exception:
        # Более простой вариант
        import os
        vuln_dir = "/sys/devices/system/cpu/vulnerabilities/"
        if os.path.exists(vuln_dir):
            return {
                f: open(f"{vuln_dir}{f}").read().strip()
                for f in os.listdir(vuln_dir)
            }
        return {}

vulns = check_cpu_vulnerabilities()
for name, status in sorted(vulns.items()):
    print(f"  {name}: {status}")
```

---

## Заключение

Side-channel атаки показывают: безопасность — это не только о логике программы, но и о физических характеристиках её выполнения.

**Ключевые выводы:**
1. **Timing attacks реальны**: используйте `hmac.compare_digest()` для сравнения секретов
2. **Cache timing attacks** используются в Spectre — изоляция процессов недостаточна
3. **Meltdown** (2018) — пропатчен KPTI с ценой 5-30% на syscall-heavy нагрузки
4. **Spectre** (2018) — более сложный, частично исправлен retpoline и LFENCE
5. **AES-NI обязателен** — программная AES уязвима к cache timing attacks
6. Для криптографических операций используйте **constant-time реализации** из trusted библиотек
7. **Следите за security advisories** вашего CPU производителя и обновляйте microcode

---

## Литература и источники

1. Kocher, P., et al. (2019). *Spectre Attacks: Exploiting Speculative Execution*. IEEE S&P 2019. https://spectreattack.com/spectre.pdf
2. Lipp, M., et al. (2018). *Meltdown: Reading Kernel Memory from User Space*. USENIX Security 2018. https://meltdownattack.com/meltdown.pdf
3. Kocher, P. (1996). *Timing Attacks on Implementations of Diffie-Hellman, RSA, DSS, and Other Systems*. CRYPTO 1996. https://link.springer.com/chapter/10.1007/3-540-68697-5_9
4. Yarom, Y., Falkner, K. (2014). *FLUSH+RELOAD: a High Resolution, Low Noise, L3 Cache Side-Channel Attack*. USENIX Security 2014.
5. Google. *Retpoline: A Branch Target Injection Mitigation*. https://support.google.com/faqs/answer/7625886
6. Kocher, P., Jaffe, J., Jun, B. (1999). *Differential Power Analysis*. CRYPTO 1999.
7. CERT. *Spectre and Meltdown Vulnerabilities FAQ*. https://www.kb.cert.org/vuls/id/584653/
8. Wikipedia: Spectre (security vulnerability). https://en.wikipedia.org/wiki/Spectre_(security_vulnerability)
9. Wikipedia: Meltdown (security vulnerability). https://en.wikipedia.org/wiki/Meltdown_(security_vulnerability)
10. Wikipedia: Side-channel attack. https://en.wikipedia.org/wiki/Side-channel_attack
