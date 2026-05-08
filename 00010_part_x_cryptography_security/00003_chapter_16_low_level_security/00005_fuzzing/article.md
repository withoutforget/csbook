# Fuzzing: AFL и libFuzzer

## Введение

В 1988 году профессор Бартон Миллер из Университета Висконсина случайно обнаружил, что Unix-программы можно «сломать» подачей случайного ввода по SSH в плохую линию связи. Он превратил это наблюдение в формальный эксперимент: написал программу, генерирующую случайные строки и подающую их в стандартные Unix-утилиты. Результат: около 25–33% программ падали. Метод получил название **fuzzing**.

Сегодня fuzzing — один из самых эффективных методов автоматического обнаружения уязвимостей. Google Project Zero использует fuzzing для анализа браузеров. Microsoft FuzzBench тестирует ОС. AFL (American Fuzzy Lop) нашёл тысячи уязвимостей в реальных программах. Только в Chrome за 2022 год fuzzing обнаружил более 27 000 ошибок.

---

## 1. Что такое fuzzing

**Fuzzing** (фаззинг) — метод тестирования программного обеспечения, при котором программа получает автоматически сгенерированные некорректные, неожиданные или случайные входные данные с целью обнаружения ошибок.

### Типы фаззеров

| Тип | Описание | Примеры |
|-----|----------|---------|
| **Black-box** | Нет доступа к исходнику, случайные мутации | Radamsa, Peach |
| **Grey-box** | Код не анализируется, но отслеживается покрытие | AFL, libFuzzer, honggfuzz |
| **White-box** | Анализ кода, символическое выполнение | KLEE, angr, Triton |
| **Generation-based** | Генерация по грамматике/формату | Sulley, boofuzz |
| **Mutation-based** | Мутация существующих корпусов | AFL, libFuzzer |

### Что ищет фаззер

```bash
# Критерии обнаружения ошибок:
# 1. Аварийное завершение (SIGSEGV, SIGABRT, SIGBUS)
# 2. Зависание (timeout)  
# 3. Memory corruption (при ASan/MSan)
# 4. Assertion failures
# 5. Неопределённое поведение (UBSan)
# 6. Логические ошибки (пользовательские оракулы)
```

---

## 2. AFL — American Fuzzy Lop

AFL создан Михалом Залевски (lcamtuf) в 2013 году. Это **coverage-guided** фаззер: он отслеживает, какие ветви кода были исполнены, и предпочитает мутации, открывающие новые пути выполнения.

### Принцип работы AFL

```
              ┌─────────────┐
              │  Corpus     │  ← начальные входные файлы
              │  (seeds)    │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │  Mutate     │  ← bit flip, byte flip, splice, ...
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │  Execute    │  ← запуск с инструментацией (fork server)
              │  program    │
              └──────┬──────┘
                     │
              ┌──────▼──────────────┐
              │  New coverage?      │
              │  YES → add to queue │  ← bitmap покрытия ветвей
              │  NO  → discard      │
              └─────────────────────┘
```

### Инструментация кода

AFL инструментирует программу при компиляции, добавляя в каждую ветвь кода обновление **coverage bitmap**:

```c
// Что AFL вставляет при компиляции (упрощённо):
// afl-gcc добавляет в каждую базовую блок (basic block):

// При переходе из блока A в блок B:
// cur_loc = <уникальный ID блока>
// shared_mem[cur_loc ^ prev_loc]++; // bitmap[A XOR B]++
// prev_loc = cur_loc >> 1;

// Если bitmap[A^B] увеличился → новый путь → интересный ввод!
```

### Установка и использование AFL++

```bash
# Установка AFL++ (форк AFL с многими улучшениями)
apt-get install afl++
# или из исходников:
git clone https://github.com/AFLplusplus/AFLplusplus
cd AFLplusplus && make && sudo make install

# 1. Компиляция с инструментацией AFL
export CC=afl-clang-fast
export CXX=afl-clang-fast++
./configure --prefix=/tmp/install
make && make install

# 2. Подготовка corpusа (начальных входных файлов)
mkdir -p corpus crashes
echo "valid input" > corpus/seed1
echo "another input" > corpus/seed2

# 3. Запуск фаззинга
afl-fuzz -i corpus -o findings -- /tmp/install/bin/my_program @@
# @@ — плейсхолдер для файла с тестовым вводом
# или через stdin:
afl-fuzz -i corpus -o findings -- /tmp/install/bin/my_program

# 4. Минимизация corpus
afl-cmin -i findings/queue -o minimized_corpus -- ./my_program @@
afl-tmin -i crash.txt -o minimized_crash -- ./my_program @@
```

### Мутации AFL

AFL применяет детерминированные и случайные мутации:

```python
# Концептуальная демонстрация мутаций AFL (не реальный код AFL)
import random
import struct
from typing import Generator

def afl_mutate(data: bytes) -> Generator[bytes, None, None]:
    """Демонстрация мутационных стратегий AFL"""
    
    # 1. Bit flips — переворот битов
    for i in range(len(data) * 8):
        mutated = bytearray(data)
        byte_idx = i // 8
        bit_idx = 7 - (i % 8)
        mutated[byte_idx] ^= (1 << bit_idx)
        yield bytes(mutated)
    
    # 2. Byte flips
    for i in range(len(data)):
        mutated = bytearray(data)
        mutated[i] ^= 0xFF
        yield bytes(mutated)
    
    # 3. Interesting values — особые значения
    interesting_8  = [0, 1, 0x7F, 0x80, 0xFF]
    interesting_16 = [0, 1, 0x7FFF, 0x8000, 0xFFFF]
    interesting_32 = [0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF]
    
    for i in range(len(data)):
        for val in interesting_8:
            mutated = bytearray(data)
            mutated[i] = val
            yield bytes(mutated)
    
    for i in range(len(data) - 1):
        for val in interesting_16:
            mutated = bytearray(data)
            struct.pack_into('<H', mutated, i, val)
            yield bytes(mutated)
    
    # 4. Random byte mutations (stochastic stage)
    for _ in range(len(data) * 4):
        mutated = bytearray(data)
        pos = random.randrange(len(data))
        mutated[pos] = random.randrange(256)
        yield bytes(mutated)
    
    # 5. Splicing — объединение двух разных входов
    # (требует corpus из нескольких файлов)
    
    # 6. Dictionary — вставка ключевых слов
    dictionary = [b"<script>", b"SELECT ", b"../", b"\x00\x00\x00\x00"]
    for i in range(len(data)):
        for keyword in dictionary:
            mutated = bytearray(data)
            end = min(i + len(keyword), len(data))
            mutated[i:end] = keyword[:end-i]
            yield bytes(mutated)
```

---

## 3. libFuzzer — in-process фаззинг

**libFuzzer** — часть проекта LLVM. Работает in-process: функция-цель вызывается тысячи раз в секунду без fork(), что гораздо быстрее AFL для многих задач.

### Написание fuzz target

```c
// fuzz_target.c — минимальный fuzz target для libFuzzer
#include <stdint.h>
#include <stddef.h>

// Это и есть "fuzz target" — функция, которую вызывает libFuzzer
// data: указатель на случайные/мутированные данные
// size: размер данных
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Тестируем нашу функцию на произвольных данных
    my_parse_function(data, size);
    
    // Возвращаем 0 (успех) или -1 (чтобы libFuzzer пропустил этот ввод)
    return 0;
    // НЕ возвращаем ненулевое значение для обозначения ошибки!
    // Ошибки = SIGSEGV, SIGABRT, assertion failure, ASan detection
}
```

### Практический пример: фаззинг парсера

```c
// Тестируем JSON-парсер (концептуально)
// fuzz_json.c

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>

// Подключаем тестируемую библиотеку
#include "json_parser.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Защита от слишком больших входов
    if (size > 64 * 1024) return 0;
    
    // Создаём нуль-терминированную копию
    char *input = malloc(size + 1);
    if (!input) return 0;
    
    memcpy(input, data, size);
    input[size] = '\0';
    
    // Тестируем парсер
    JsonValue *result = json_parse(input);
    
    // Если парсер вернул что-то — проверяем roundtrip
    if (result) {
        char *serialized = json_serialize(result);
        if (serialized) {
            // Парсим снова — должны получить то же самое
            JsonValue *result2 = json_parse(serialized);
            // Если result != result2 — ошибка логики!
            free(serialized);
            json_free(result2);
        }
        json_free(result);
    }
    
    free(input);
    return 0;
}
```

```bash
# Компиляция fuzz target с libFuzzer
clang -fsanitize=address,fuzzer \
      -fsanitize=undefined \
      -g -O1 \
      -o fuzz_json fuzz_json.c libjson.a

# Запуск
./fuzz_json corpus/                  # начать с corpus
./fuzz_json -max_total_time=3600     # фаззить 1 час
./fuzz_json -jobs=8 -workers=8      # параллельно 8 процессов

# Ключевые флаги libFuzzer:
# -max_len=N          максимальный размер ввода
# -timeout=N          таймаут на один запуск (секунды)
# -only_ascii=1       только ASCII символы
# -dict=dict.txt      словарь ключевых слов
# -runs=N             ограничить количество запусков
```

### Corpus: зачем нужны хорошие начальные данные

```python
# Создание минимального corpus для JSON фаззера
import json
import os

def create_json_corpus(output_dir: str):
    """Создание начального corpus для фаззинга JSON"""
    os.makedirs(output_dir, exist_ok=True)
    
    seeds = [
        # Валидные JSON
        {},
        [],
        {"key": "value"},
        [1, 2, 3],
        {"nested": {"a": [1, 2, {"b": null}]}},
        True,
        False,
        None,
        42,
        3.14,
        "hello",
        
        # Граничные случаи
        {"key": ""},
        {"": "value"},
        [None, None, None],
        {"n": 1e308},
        {"n": -1e308},
        {"n": 0.0},
        {"s": ""},  # нулевой символ в строке
        {"s": "\\" * 100},  # много escape символов
        
        # Большие структуры
        list(range(1000)),
        {"a" * i: i for i in range(100)},
    ]
    
    for i, seed in enumerate(seeds):
        filepath = os.path.join(output_dir, f"seed_{i:03d}")
        with open(filepath, 'w') as f:
            json.dump(seed, f)
    
    print(f"Created {len(seeds)} seed files in {output_dir}")

create_json_corpus('./json_corpus')
```

---

## 4. OSS-Fuzz: непрерывный фаззинг открытых проектов

Google OSS-Fuzz — платформа для непрерывного фаззинга открытых проектов. Запущена в 2016 году.

```bash
# Как добавить проект в OSS-Fuzz (упрощённо):
# 1. Создать директорию projects/your_project/
# 2. Написать build.sh с компиляцией fuzz targets
# 3. Создать Dockerfile
# 4. Отправить PR в https://github.com/google/oss-fuzz

# build.sh пример:
#!/bin/bash
cd $SRC/your_library
./configure
make -j$(nproc)

# Компиляция fuzz targets
for fuzz_target in $SRC/fuzz_*.c; do
    $CC $CFLAGS $LIB_FUZZING_ENGINE \
        -o $OUT/$(basename ${fuzz_target%.c}) \
        $fuzz_target libyourlibrary.a
done
```

### Статистика OSS-Fuzz

Как выглядят результаты OSS-Fuzz в реальности:

```python
# Статистика (данные из открытых источников на 2023 год):
oss_fuzz_stats = {
    "проектов_под_фаззингом": 1000,
    "найдено_ошибок_всего": 10000,  # по данным Google
    "критических_уязвимостей": 500,
    "среднее_время_до_обнаружения_дней": 2,
    "запусков_в_день": "billions",
    "процессорных_часов_в_день": 100000
}

# Проекты с наибольшим числом ошибок:
top_projects = {
    "chromium": 3000,
    "openssl": 100,
    "sqlite": 600,
    "libpng": 80,
    "ffmpeg": 300,
    "curl": 40,
    "opencv": 200
}
```

---

## 5. Структурный фаззинг с libprotobuf-mutator

Для сложных форматов (протоколов, языков) чисто случайные мутации неэффективны — большинство входов отбрасываются на ранней стадии парсинга. Решение — **структурный фаззинг**:

```cpp
// Использование protobuf для структурного фаззинга
// Определяем структуру ввода в .proto файле

// http_request.proto:
// message HttpRequest {
//   required string method = 1;
//   required string path = 2;
//   optional bytes body = 3;
//   repeated Header headers = 4;
// }

#include "libprotobuf-mutator/src/libfuzzer/libfuzzer_macro.h"
#include "http_request.pb.h"

// Вместо raw bytes получаем структурированный объект
DEFINE_PROTO_FUZZER(const HttpRequest& request) {
    // Конвертируем protobuf → сырые байты HTTP запроса
    std::string raw_request = serialize_http_request(request);
    
    // Тестируем HTTP парсер на сгенерированном запросе
    parse_http_request(raw_request.data(), raw_request.size());
}
```

### Grammars и генеративный фаззинг

```python
# Простой генератор на основе грамматики (для SQL fuzzing)
import random
from typing import Union

# BNF-подобная грамматика для SQL
SQL_GRAMMAR = {
    '<query>': [
        ['SELECT', ' ', '<select_list>', ' ', 'FROM', ' ', '<table_ref>'],
        ['SELECT', ' ', '<select_list>', ' ', 'FROM', ' ', '<table_ref>', 
         ' ', 'WHERE', ' ', '<condition>'],
        ['INSERT', ' ', 'INTO', ' ', '<identifier>', ' ', 
         'VALUES', ' ', '(', '<value_list>', ')'],
        ['DELETE', ' ', 'FROM', ' ', '<identifier>'],
    ],
    '<select_list>': [
        ['*'],
        ['<identifier>'],
        ['<identifier>', ', ', '<identifier>'],
    ],
    '<table_ref>': [
        ['<identifier>'],
        ['<identifier>', ' AS ', '<identifier>'],
    ],
    '<condition>': [
        ['<identifier>', ' = ', '<value>'],
        ['<identifier>', ' > ', '<value>'],
        ['<identifier>', ' IS NULL'],
        ['<condition>', ' AND ', '<condition>'],
        ['<condition>', ' OR ', '<condition>'],
        ['NOT ', '<condition>'],
    ],
    '<value>': [
        ["'<string>'"],
        ['<integer>'],
        ['NULL'],
        ["'", "'"],  # пустая строка
        ["' OR '1'='1"],  # SQL injection!
    ],
    '<identifier>': [
        ['users'], ['orders'], ['products'], ['admin'],
        ['id'], ['name'], ['email'], ['password'],
    ],
    '<integer>': [
        ['0'], ['1'], ['-1'], ['2147483647'], ['0; DROP TABLE users; --'],
    ],
    '<string>': [
        ['hello'], ['test'], ['a' * 100], ['\\x00\\x01\\x02'],
    ],
    '<value_list>': [
        ['<value>'],
        ['<value>', ', ', '<value>'],
    ],
}

def generate_from_grammar(symbol: str, grammar: dict, 
                           max_depth: int = 5) -> str:
    """Генерация строки из грамматики"""
    if max_depth <= 0:
        # Возвращаем терминал, чтобы прервать рекурсию
        return symbol
    
    if symbol not in grammar:
        return symbol  # терминал
    
    # Выбираем случайное правило
    production = random.choice(grammar[symbol])
    
    # Раскрываем каждый элемент правила
    result = ''
    for part in production:
        if part.startswith('<') and part.endswith('>'):
            result += generate_from_grammar(part, grammar, max_depth - 1)
        else:
            result += part
    
    return result

# Генерация случайных SQL запросов
for _ in range(10):
    query = generate_from_grammar('<query>', SQL_GRAMMAR)
    print(f"Testing: {query}")
    # Подаём в парсер для тестирования
```

---

## 6. honggfuzz — Google's fuzzer

```bash
# honggfuzz — многопоточный, быстрый фаззер от Google
git clone https://github.com/google/honggfuzz
cd honggfuzz && make

# Компиляция с honggfuzz инструментацией
hfuzz-clang -o target target.c

# Запуск
honggfuzz -i corpus -o findings -- ./target ___FILE___
# Ключевые преимущества:
# - Поддержка multiple coverage типов (bb, edge, sanitizers)
# - Персистентный режим (как libFuzzer, но через honggfuzz API)
# - Лучшая работа с бинарниками (без исходного кода)

# Персистентный режим:
#include "honggfuzz/libhfuzz/libhfuzz.h"
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    my_function(data, size);
    return 0;
}
```

---

## 7. Дифференциальный фаззинг

**Дифференциальный фаззинг** — сравнение двух реализаций одного API:

```python
# Тестирование нескольких JSON-парсеров на одинаковых входах
# Если они возвращают разный результат — потенциальная ошибка

import json
import sys

try:
    import ujson   # ультрабыстрый JSON
    import orjson  # ещё один быстрый JSON
    HAS_ALTERNATIVES = True
except ImportError:
    HAS_ALTERNATIVES = False

def differential_json_fuzz(data: bytes) -> None:
    """
    Сравнивает результаты нескольких JSON парсеров.
    Вызывается libFuzzer через Python bindings.
    """
    try:
        result_stdlib = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        result_stdlib = None
    
    if not HAS_ALTERNATIVES:
        return
    
    try:
        result_ujson = ujson.loads(data)
    except (ValueError, UnicodeDecodeError):
        result_ujson = None
    
    # Оба должны либо успешно распарсить с одинаковым результатом,
    # либо оба вернуть ошибку
    if (result_stdlib is None) != (result_ujson is None):
        # Расхождение! Один парсит, другой нет
        print(f"DIFFERENTIAL: stdlib={'ok' if result_stdlib else 'fail'}, "
              f"ujson={'ok' if result_ujson else 'fail'}")
        print(f"Input: {data[:100]!r}")
        # В реальном фаззере: сохранить этот ввод как интересный
    
    elif result_stdlib is not None and result_stdlib != result_ujson:
        # Оба парсят, но результат разный!
        print(f"DIFFERENTIAL RESULT: {result_stdlib!r} != {result_ujson!r}")
        print(f"Input: {data[:100]!r}")
```

---

## 8. Интеграция с CI/CD

```yaml
# .github/workflows/fuzzing.yml
name: Continuous Fuzzing

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # каждую ночь в 2:00

jobs:
  fuzz:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install dependencies
        run: |
          sudo apt-get install -y clang libclang-dev
          
      - name: Build fuzz targets
        run: |
          export CC=clang
          export CFLAGS="-fsanitize=address,fuzzer-no-link -g"
          make fuzz_targets
          
      - name: Run fuzzer (30 minutes)
        run: |
          ./fuzz_parser \
            -max_total_time=1800 \
            -max_len=4096 \
            corpus/
            
      - name: Check for crashes
        run: |
          if ls crashes/ 2>/dev/null | grep -q '.'; then
            echo "FUZZING FOUND CRASHES!"
            ls -la crashes/
            exit 1
          fi
          
      - name: Upload corpus
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: fuzzing-corpus
          path: corpus/
```

```python
# Скрипт запуска fuzzing и анализа результатов
import subprocess
import os
import json
from pathlib import Path
from datetime import datetime

def run_fuzzing_campaign(
    target: str,
    corpus_dir: str,
    max_time_seconds: int = 3600,
    max_len: int = 4096
) -> dict:
    """
    Запуск кампании fuzzing и сбор статистики.
    Возвращает словарь с результатами.
    """
    crashes_dir = './crashes'
    os.makedirs(crashes_dir, exist_ok=True)
    os.makedirs(corpus_dir, exist_ok=True)
    
    start_time = datetime.now()
    
    # Запуск libFuzzer
    cmd = [
        target,
        f'-max_total_time={max_time_seconds}',
        f'-max_len={max_len}',
        f'-artifact_prefix={crashes_dir}/',
        '-print_final_stats=1',
        corpus_dir
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max_time_seconds + 60
    )
    
    # Парсинг статистики libFuzzer из stderr
    stats = parse_libfuzzer_stats(result.stderr)
    
    # Сбор crash файлов
    crash_files = list(Path(crashes_dir).glob('crash-*'))
    oom_files = list(Path(crashes_dir).glob('oom-*'))
    timeout_files = list(Path(crashes_dir).glob('timeout-*'))
    
    return {
        'duration_seconds': (datetime.now() - start_time).seconds,
        'executions': stats.get('executions', 0),
        'exec_per_second': stats.get('exec_per_second', 0),
        'corpus_size': stats.get('corpus_size', 0),
        'crashes': len(crash_files),
        'ooms': len(oom_files),
        'timeouts': len(timeout_files),
        'crash_files': [str(f) for f in crash_files],
        'coverage_pct': stats.get('cov', 0),
    }

def parse_libfuzzer_stats(stderr: str) -> dict:
    """Извлечение статистики из вывода libFuzzer"""
    stats = {}
    
    # Строки вида: "stat::number_of_executed_units: 12345678"
    import re
    for line in stderr.split('\n'):
        match = re.match(r'stat::(\w+):\s+(\S+)', line)
        if match:
            key, value = match.groups()
            try:
                stats[key] = int(value)
            except ValueError:
                stats[key] = value
    
    # Парсим exec/s из строк вида "#123456 DONE  cov: 456 ft: 789 ..."
    done_match = re.search(r'#\d+.*exec/s:\s+(\d+)', stderr)
    if done_match:
        stats['exec_per_second'] = int(done_match.group(1))
    
    return stats
```

---

## 9. Символическое выполнение (теоретически)

Символическое выполнение — более мощный метод, дополняющий fuzzing:

```python
# Концептуальный пример с angr (Python framework для symbolic execution)

import angr

def find_crash_input(binary_path: str) -> bytes | None:
    """
    Использует символическое выполнение для поиска входа,
    вызывающего crash (SIGSEGV)
    """
    project = angr.Project(binary_path, auto_load_libs=False)
    
    # Символический аргумент длиной 100 байт
    argv1 = angr.PointerWrapper(
        angr.claripy.BVS('argv1', 100 * 8),  # 100 байт символических
        buffer=True
    )
    
    state = project.factory.entry_state(args=[binary_path, argv1])
    
    # Настройка симуляции
    simgr = project.factory.simulation_manager(state)
    
    # Ищем состояния, достигшие abort/crash
    simgr.run(until=lambda sm: sm.deadended or sm.errored)
    
    # Если нашли ошибочное состояние
    if simgr.errored:
        error_state = simgr.errored[0].state
        # Конкретизируем символический ввод
        concrete_input = error_state.solver.eval(argv1, cast_to=bytes)
        return concrete_input
    
    return None
```

### Сравнение методов

| Метод | Скорость | Покрытие | Сложность | Ложные срабатывания |
|-------|----------|---------- |-----------|---------------------|
| Random fuzzing | Высокая | Низкое | Низкая | Нет |
| Coverage-guided (AFL/libFuzzer) | Высокая | Хорошее | Средняя | Нет |
| Grammars-based | Средняя | Хорошее (semantic) | Высокая | Нет |
| Symbolic execution | Низкая | Теоретически полное | Очень высокая | Есть |
| Concolic (hybrid) | Средняя | Отличное | Высокая | Нет |

---

## 10. Реальные уязвимости, найденные fuzzing'ом

| Год | CVE | Программа | Метод | Описание |
|-----|-----|-----------|-------|----------|
| 2014 | CVE-2014-0160 | OpenSSL | Manual | Heartbleed (нашли вручную, но AFL бы тоже нашёл) |
| 2015 | — | libjpeg-turbo | AFL | 9 уязвимостей parсера JPEG |
| 2016 | CVE-2016-5180 | c-ares | AFL | Heap overflow в DNS парсере |
| 2017 | — | OpenSSH | libFuzzer | Множество ошибок парсера |
| 2018 | CVE-2018-* | Chrome | ClusterFuzz | 50+ уязвимостей в V8 |
| 2020 | CVE-2020-1971 | OpenSSL | OSS-Fuzz | NULL deref в X.509 |
| 2021 | CVE-2021-* | libpng, libxml2 | OSS-Fuzz | Десятки уязвимостей |
| 2022 | — | curl | OSS-Fuzz | 6 уязвимостей за год |
| 2023 | CVE-2023-* | libwebp | ClusterFuzz | Heap buffer overflow |

---

## 11. Best practices для fuzzing

```python
# Чеклист для эффективного fuzzing:

fuzzing_checklist = """
1. Corpus:
   - Начинать с реальных входных данных (не только random)
   - Включать граничные случаи: пустой ввод, максимальный размер
   - Использовать afl-cmin для минимизации corpus
   
2. Компиляция:
   - Всегда с ASan: -fsanitize=address
   - Добавить UBSan: -fsanitize=undefined
   - Оптимизация: -O1 (баланс скорости и качества инструментации)
   - Отладочные символы: -g
   
3. Fuzz target:
   - Минимальный setup/teardown
   - Избегать global state (или сбрасывать его)
   - Возвращать -1 для явно некорректных входов (short-circuit)
   - Не использовать exit() внутри target
   
4. Мониторинг:
   - Отслеживать exec/s (должно быть > 1000)
   - Смотреть на рост corpus (должен замедляться)
   - Анализировать coverage
   
5. Triaging (разбор крашей):
   - Минимизировать: afl-tmin / -min_crash_test
   - Анализировать: gdb, lldb с ASan output
   - Классифицировать: heap overflow? stack overflow? UAF?
   
6. Интеграция:
   - CI/CD: прогонять corpus каждый PR
   - Ночные прогоны: более длинные кампании
   - Хранить corpus в VCS
"""

print(fuzzing_checklist)
```

---

## Заключение

Fuzzing — один из наиболее практичных и экономически эффективных методов поиска уязвимостей. Coverage-guided инструменты (AFL++, libFuzzer) автоматически находят пути выполнения, которые человек не догадался бы проверить.

**Ключевые выводы:**
1. **AFL++ или libFuzzer** — начать с одного из них
2. **ASan обязателен** — без него fuzzer пропустит большинство ошибок памяти
3. **Хороший corpus** — основа эффективного fuzzing'а
4. **Структурный fuzzing** — для сложных форматов (XML, JSON, SQL, протоколы)
5. **OSS-Fuzz** — если ваш проект открытый, подключите его к Google OSS-Fuzz
6. **Интеграция в CI** — fuzzing должен быть непрерывным, не одноразовым

---

## Литература и источники

1. Miller, B.P., et al. (1990). *An Empirical Study of the Reliability of UNIX Utilities*. Communications of the ACM. https://dl.acm.org/doi/10.1145/96267.96279
2. Zalewski, M. *Technical "whitepaper" for afl-fuzz*. https://lcamtuf.coredump.cx/afl/technical_details.txt
3. AFL++ GitHub repository. https://github.com/AFLplusplus/AFLplusplus
4. LibFuzzer documentation. https://llvm.org/docs/LibFuzzer.html
5. Google OSS-Fuzz. https://github.com/google/oss-fuzz
6. Böhme, M., et al. (2017). *Coverage-based Greybox Fuzzing as Markov Chain*. CCS 2016. https://dl.acm.org/doi/10.1145/2976749.2978428
7. Klees, G., et al. (2018). *Evaluating Fuzz Testing*. CCS 2018. https://dl.acm.org/doi/10.1145/3243734.3243804
8. honggfuzz documentation. https://github.com/google/honggfuzz
9. Shoshitaishvili, Y., et al. (2016). *SoK: (State of) The Art of War: Offensive Techniques in Binary Analysis*. IEEE S&P 2016. (angr paper)
10. Serebryany, K. (2017). *libFuzzer – a library for coverage-guided fuzz testing*. LLVM Blog. https://llvm.org/blog/2015/04/libfuzzer-a-library-for-coverage-guided-fuzz-testing.html
