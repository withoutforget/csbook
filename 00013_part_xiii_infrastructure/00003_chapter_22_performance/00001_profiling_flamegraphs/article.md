# Профилирование: CPU, память, аллокации; flame graphs

«Преждевременная оптимизация — корень всех зол» — эта цитата Кнута часто трактуется неправильно. Кнут не говорил «никогда не оптимизируй». Он говорил: не оптимизируй без данных. Профилирование — это инструмент получения этих данных. Без профилировщика вы гадаете. С профилировщиком — вы знаете, где реально тратится время и память.

## Зачем профилировать: интуиция обманывает

Исследования показывают, что разработчики неверно угадывают узкие места в производительности примерно в 90% случаев. Код, который «выглядит медленным», часто не является узким местом. А реальный bottleneck находится в неожиданном месте.

```python
# Угадайте: какая операция занимает больше всего времени?

def process_data(records: list[dict]) -> list[dict]:
    results = []
    
    for record in records:
        # Операция 1: форматирование строки
        formatted = f"ID={record['id']}, Name={record['name']}"
        
        # Операция 2: парсинг JSON
        parsed = json.loads(record['extra_data'])
        
        # Операция 3: обращение к БД
        user = db.query(f"SELECT * FROM users WHERE id = {record['user_id']}")
        
        # Операция 4: вычисление хеша
        hash_val = hashlib.sha256(formatted.encode()).hexdigest()
        
        results.append({...})
    
    return results

# Большинство скажет: операция 2 (JSON парсинг) или 4 (SHA-256)
# Реальность: операция 3 (SQL запрос) занимает 99% времени
# И её можно заменить одним batch-запросом
```

## Два типа профилировщиков

### Sampling Profilers (семплирующие)

Прерывают программу через фиксированные интервалы (например, каждые 1мс) и записывают текущий стек вызовов. Низкий overhead (~1-5%), но не фиксируют короткие функции.

```
Каждые 1мс прерываем программу:
    Sample 1: main → process_data → db.query → psycopg2.execute
    Sample 2: main → process_data → db.query → psycopg2.execute
    Sample 3: main → process_data → db.query → psycopg2.execute
    Sample 4: main → process_data → json.loads
    Sample 5: main → process_data → db.query → psycopg2.execute
    ...
    
db.query встречается в 80% семплов → 80% времени программы
```

### Instrumentation Profilers (инструментальные)

Добавляют код замера времени вокруг каждой функции. Точные, но overhead может быть значительным (до 10x замедление).

```python
# Пример инструментального профилирования вручную
import time
import functools

def profile(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter_ns()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter_ns() - start
        print(f"{func.__name__}: {elapsed / 1_000_000:.3f}ms")
        return result
    return wrapper

@profile
def slow_function():
    time.sleep(0.1)
```

## CPU Профилирование

### Linux perf

`perf` — мощный системный профилировщик для Linux. Работает с любыми программами без изменения кода.

```bash
# Запуск профилирования Python приложения
perf record -F 99 -g python myapp.py
# -F 99: 99 семплов в секунду
# -g: записываем стек вызовов (call graph)

# Просмотр результатов
perf report

# Генерация данных для flame graph
perf script > out.perf
```

### cProfile (Python — встроенный)

```python
import cProfile
import pstats
import io

# Профилирование функции
def profile_code():
    pr = cProfile.Profile()
    pr.enable()
    
    # Ваш код здесь
    result = your_function_to_profile()
    
    pr.disable()
    
    # Вывод результатов
    stream = io.StringIO()
    stats = pstats.Stats(pr, stream=stream)
    stats.sort_stats('cumulative')  # Сортировка по суммарному времени
    stats.print_stats(20)  # Top 20 функций
    print(stream.getvalue())
    
    return result

# Или через командную строку:
# python -m cProfile -s cumulative myapp.py

# Пример вывода cProfile:
#    ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#         1    0.001    0.001   10.432   10.432 myapp.py:1(main)
#     10000    0.052    0.000   10.430    0.001 myapp.py:15(process_record)
#     10000    9.876    0.001    9.876    0.001 db.py:45(query)
#     10000    0.234    0.000    0.234    0.000 json.py:312(loads)
```

### py-spy (Python — sampling, без остановки)

```bash
# Установка
pip install py-spy

# Профилировать запущенный процесс (не нужно перезапускать!)
py-spy record -o profile.svg --pid 12345

# Профилировать с запуском
py-spy record -o profile.svg -- python myapp.py

# Top-like интерфейс (real-time)
py-spy top --pid 12345
```

Py-spy работает с запущенными production процессами без остановки и без изменения кода.

### async-profiler (JVM)

```bash
# Для Java/Kotlin/Scala приложений
./profiler.sh -d 30 -f profile.html <PID>
# -d 30: профилировать 30 секунд
# -f profile.html: сохранить как HTML с интерактивным flame graph

# Wall-clock профилирование (включает time.sleep и I/O wait)
./profiler.sh -e wall -d 30 <PID>

# Профилирование аллокаций
./profiler.sh -e alloc -d 30 <PID>
```

### pprof (Go)

Go имеет встроенную поддержку pprof:

```go
import (
    "net/http"
    _ "net/http/pprof"  // Регистрирует /debug/pprof endpoints
)

func main() {
    // Запустить pprof HTTP сервер
    go http.ListenAndServe(":6060", nil)
    
    // Ваш код...
}
```

```bash
# Снять CPU профиль на 30 секунд
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30

# Интерактивный анализ
(pprof) top 10
(pprof) web          # Открыть flame graph в браузере
(pprof) list myFunc  # Показать аннотированный исходный код
```

## Flame Graphs: визуализация профилей

**Flame Graph** (граф пламени) — визуализация производительности, изобретённая Бренданом Греггом. Позволяет за секунды увидеть где тратится время.

```
Как читать Flame Graph:

  ▲ Y-ось: глубина стека вызовов (каждый уровень = вызов функции)
  ← X-ось: суммарное время (ширина = процент времени)
  
  Цвет: произвольный (для различения), не несёт смыслового значения
  
       ┌──────────────────────────────────────────────────────┐
   4   │        small_func  │  hash_func  │                   │
   3   │      json_parse    │   encode()  │                   │
   2   │      process()     │             │                   │
   1   │              main()              │        idle       │
   0   └──────────────────────────────────────────────────────┘
       ←───────────── 100% времени ──────────────────────────→
       
  Интерпретация:
  - main() занимает ~60% времени (в process) + 30% в другом коде
  - process() → json_parse: 20% времени
  - process() → hash_func: 10% времени  
  - idle: 30% (ничего не делает - ждёт I/O или заблокирован)
  
  Узкое место: самый широкий "плоский" элемент наверху стека
```

**Icicle Graph** — перевёрнутый flame graph, где корень дерева вверху (удобнее для чтения сверху вниз).

### Генерация Flame Graphs

```bash
# Brendan Gregg's FlameGraph tools (https://github.com/brendangregg/FlameGraph)

# Для Linux perf:
perf record -F 99 -ag -- sleep 30
perf script | ./stackcollapse-perf.pl | ./flamegraph.pl > perf.svg

# Для Python с py-spy:
py-spy record -o flame.svg --format flamegraph -- python myapp.py

# Для Go pprof:
go tool pprof -http=:8080 http://localhost:6060/debug/pprof/profile?seconds=30
# Открывает браузер с flame graph

# Для JVM async-profiler:
./profiler.sh -d 30 -o flamegraph -f output.html <PID>
```

```python
# Python: генерация flame graph данных программно
# (для встроенного в код профилирования)

import tracemalloc
import linecache

def display_top_allocations(snapshot, key_type='lineno', limit=10):
    """Показать топ аллокаций памяти."""
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<unknown>"),
    ))
    
    top_stats = snapshot.statistics(key_type)
    print(f"\nTop {limit} memory allocations:")
    
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        print(f"\n#{index}: {frame.filename}:{frame.lineno}")
        print(f"  Size: {stat.size / 1024:.1f} KB")
        
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            print(f"  Code: {line}")
    
    other = top_stats[limit:]
    if other:
        size = sum(stat.size for stat in other)
        print(f"\n{len(other)} other: {size / 1024:.0f} KB")
    
    total = sum(stat.size for stat in top_stats)
    print(f"\nTotal allocated size: {total / 1024:.0f} KB")

# Использование
tracemalloc.start()

# Ваш код
result = your_memory_intensive_function()

snapshot = tracemalloc.take_snapshot()
display_top_allocations(snapshot)
```

## Memory Profiling: поиск утечек памяти

### Valgrind Massif (C/C++)

```bash
# Профилирование heap памяти
valgrind --tool=massif ./myprogram

# Визуализация
ms_print massif.out.* | head -100

# Вывод показывает пиковое использование памяти
# и стек вызовов для каждой аллокации
```

### memory_profiler (Python)

```python
# pip install memory-profiler

from memory_profiler import profile

@profile
def my_func():
    a = [1] * (10 ** 6)
    b = [2] * (2 * 10 ** 7)
    del b
    return a

if __name__ == '__main__':
    my_func()

# Вывод:
# Line #    Mem usage    Increment   Line Contents
# ================================================
#      3   21.938 MiB   21.938 MiB   @profile
#      4                             def my_func():
#      5   29.559 MiB    7.621 MiB       a = [1] * (10 ** 6)
#      6  182.754 MiB  153.195 MiB       b = [2] * (2 * 10 ** 7)
#      7   29.754 MiB -153.000 MiB       del b
#      8   29.754 MiB    0.000 MiB       return a
```

```bash
# Профилирование по времени (мониторинг памяти процесса)
mprof run myprogram.py
mprof plot  # Построить график использования памяти во времени
```

### heaptrack (C/C++)

```bash
# Heaptrack: детальный heap profiler
heaptrack ./myprogram
heaptrack_print heaptrack.myprogram.12345.gz | head -50
heaptrack_gui heaptrack.myprogram.12345.gz  # GUI анализ
```

### Утечки памяти в Python: objgraph

```python
import objgraph
import gc

def find_memory_leaks():
    # Принудительный GC
    gc.collect()
    
    # Показать типы объектов с наибольшим количеством
    objgraph.show_most_common_types(limit=20)
    
    # Найти объекты, которые не должны существовать
    # (например, незакрытые соединения)
    connections = objgraph.by_type('psycopg2.extensions.connection')
    print(f"Open DB connections: {len(connections)}")
    
    # Построить граф ссылок для конкретного объекта
    # (помогает понять почему объект не удаляется GC)
    if connections:
        objgraph.show_backrefs(connections[0], max_depth=3, 
                               filename='refs.png')

# Сравнение снапшотов для поиска утечек
snapshot1 = objgraph.typestats()
do_some_work()
snapshot2 = objgraph.typestats()

# Что увеличилось?
increased = {
    k: snapshot2.get(k, 0) - snapshot1.get(k, 0)
    for k in set(snapshot1) | set(snapshot2)
    if snapshot2.get(k, 0) > snapshot1.get(k, 0)
}
```

## Allocation Tracking: где аллоцируется память

```python
# Python: tracemalloc для трекинга аллокаций
import tracemalloc

tracemalloc.start(25)  # 25 кадров в стеке

# ... ваш код ...

snapshot = tracemalloc.take_snapshot()

# Топ аллокаций с полным стеком
stats = snapshot.statistics('traceback')
for stat in stats[:3]:
    print(f"\nTotal allocated: {stat.size / 1024:.1f} KB")
    print("Stack trace:")
    for frame in stat.traceback:
        print(f"  File {frame.filename}, line {frame.lineno}")
```

```go
// Go: runtime/pprof для heap профилирования
package main

import (
    "os"
    "runtime/pprof"
)

func main() {
    // CPU профиль
    f, _ := os.Create("cpu.prof")
    pprof.StartCPUProfile(f)
    defer pprof.StopCPUProfile()
    
    // Heap профиль в конце
    defer func() {
        mf, _ := os.Create("mem.prof")
        pprof.WriteHeapProfile(mf)
    }()
    
    // Ваш код...
}

// Анализ:
// go tool pprof -http=:8080 mem.prof
// Показывает: inuse_space, inuse_objects, alloc_space, alloc_objects
```

## I/O Профилирование

```bash
# Linux: iostat — производительность дисков
iostat -x 1
# Ключевые метрики:
# util%: 90%+ = диск saturated
# await: среднее время I/O операции (мс)
# r/s, w/s: IOPS

# strace: системные вызовы (I/O)
strace -p <PID> -e trace=read,write,open,close
# Показывает каждый файловый вызов

# iotop: процессы с наибольшим disk I/O
iotop -o  # Только активные процессы
```

```python
# Python: профилирование I/O через аудит хуков
import sys

class IOAudit:
    def __init__(self):
        self.calls = {}
    
    def audit_hook(self, event, args):
        if event in ('open', 'io.open'):
            filename = args[0] if args else 'unknown'
            self.calls[filename] = self.calls.get(filename, 0) + 1

auditor = IOAudit()
sys.addaudithook(auditor.audit_hook)
```

## Непрерывное профилирование в продакшне (Continuous Profiling)

Профилирование не только для разработки — профилирование в production позволяет:
- Находить регрессии производительности до жалоб пользователей
- Мониторить потребление ресурсов в реальных условиях нагрузки
- Понимать производительность под реальным трафиком (не синтетическими тестами)

### Pyroscope (open source, поддерживает Python, Go, Java, .NET)

```python
# pip install pyroscope-io

import pyroscope

pyroscope.configure(
    application_name="my-python-app",
    server_address="http://pyroscope:4040",
    auth_token="",
    tags={
        "region": "us-east-1",
        "environment": "production",
        "version": "1.2.3"
    }
)

# Pyroscope автоматически семплирует CPU и отправляет данные
# Веб-интерфейс: сравнение flame graphs за разные временные периоды
```

```go
// Go: интеграция с Pyroscope
import (
    "github.com/grafana/pyroscope-go"
)

func main() {
    pyroscope.Start(pyroscope.Config{
        ApplicationName: "my-go-app",
        ServerAddress:   "http://pyroscope:4040",
        ProfileTypes: []pyroscope.ProfileType{
            pyroscope.ProfileCPU,
            pyroscope.ProfileAllocObjects,
            pyroscope.ProfileAllocSpace,
            pyroscope.ProfileInuseObjects,
            pyroscope.ProfileInuseSpace,
            pyroscope.ProfileGoroutines,
        },
    })
}
```

### Parca (CNCF Project)

```yaml
# Parca: eBPF-based continuous profiling
# Не требует изменений в коде приложения!

# parca.yaml
object_storage:
  bucket:
    type: "FILESYSTEM"
    config:
      directory: "./data"

# Parca агент собирает профили через eBPF
# Минимальный overhead: 0.1-1% CPU
```

### Google Cloud Profiler

```python
# Для приложений на GCP
import googlecloudprofiler

googlecloudprofiler.start(
    service='my-service',
    service_version='1.0.0',
    # verbose=1 для отладки
)
# Профили автоматически отправляются в GCP Cloud Profiler
```

## Практический пример: нахождение узкого места

```python
# Задача: API endpoint отвечает за 3 секунды. Найти причину.

# Шаг 1: Запустить py-spy
# py-spy record -o profile.svg -- python api.py

# Шаг 2: Запустить несколько запросов к endpoint
# wrk -t 4 -c 10 -d 30s http://localhost:8000/api/products

# Шаг 3: Анализируем flame graph
# Видим: 85% времени в 'psycopg2.execute' → 'select_from_db'
# Это N+1 запрос!

# Диагностика:
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
# Теперь видим каждый SQL запрос в логах

# Находим проблему:
def get_products_with_sellers(category_id: int) -> list:
    products = db.query("SELECT * FROM products WHERE category_id = ?", category_id)
    
    result = []
    for product in products:
        # N+1! Для каждого продукта — отдельный запрос
        seller = db.query("SELECT * FROM sellers WHERE id = ?", product.seller_id)
        result.append({...})
    
    return result  # 100 продуктов = 101 запрос к БД

# Исправление: JOIN или batch loading
def get_products_with_sellers_optimized(category_id: int) -> list:
    # Один запрос вместо N+1
    rows = db.query("""
        SELECT p.*, s.name as seller_name, s.rating as seller_rating
        FROM products p
        JOIN sellers s ON s.id = p.seller_id
        WHERE p.category_id = ?
    """, category_id)
    
    return [{...} for row in rows]  # 100 продуктов = 1 запрос

# Результат: 3 секунды → 50ms (60x ускорение!)
```

## Heap Dump Анализ (JVM)

```bash
# Получить heap dump
jmap -dump:format=b,file=heapdump.hprof <PID>

# Анализ в VisualVM (GUI)
visualvm --openfile heapdump.hprof

# Или Eclipse MAT (Memory Analyzer Tool)
./mat heapdump.hprof

# Командная строка: jhat
jhat heapdump.hprof
# Открывает веб-интерфейс на порту 7000
```

В Eclipse MAT ищите:
- **Leak Suspects Report** — автоматически находит потенциальные утечки
- **Dominator Tree** — объекты, удерживающие больше всего памяти
- **Retained Heap** — сколько памяти освободится, если удалить объект

## Заключение

Профилирование — это инженерная дисциплина, не гадание. Ключевые принципы:

1. **Меряй, не угадывай** — интуиция обманывает в 90% случаев
2. **Профилируй в реальных условиях** — синтетические тесты могут не воспроизводить production bottlenecks
3. **Начинай с системного профилирования** — perf/py-spy дают общую картину
4. **Ищи самый широкий пик на flame graph** — это ваш bottleneck
5. **Непрерывное профилирование** — не только для debugging, но и для мониторинга регрессий

Flame graphs — революционный инструмент визуализации, позволяющий за секунды понять поведение программы, которое иначе заняло бы часы анализа. Освойте их — это один из самых ценных навыков при работе с производительностью.

## Литература

1. **Gregg, Brendan** — «Systems Performance: Enterprise and the Cloud», 2nd ed. Pearson, 2020. ISBN: 978-0136820154
2. **Gregg, Brendan** — «The Flame Graph». ACM Queue, 2016: https://queue.acm.org/detail.cfm?id=2927301
3. **Gregg, Brendan** — «FlameGraph» (GitHub): https://github.com/brendangregg/FlameGraph
4. **Knuth, Donald** — «Structured Programming with go to Statements». ACM Computing Surveys, 1974 (оригинальная цитата об оптимизации)
5. **Python Documentation** — «The Python Profilers»: https://docs.python.org/3/library/profile.html
6. **Go Blog** — «Profiling Go Programs»: https://go.dev/blog/pprof
7. **async-profiler Documentation** — https://github.com/async-profiler/async-profiler
8. **py-spy Documentation** — https://github.com/benfred/py-spy
9. **Pyroscope Documentation** — https://pyroscope.io/docs/
10. **Nethercote, Nicholas; Seward, Julian** — «Valgrind: A Framework for Heavyweight Dynamic Binary Instrumentation». ACM SIGPLAN 2007
