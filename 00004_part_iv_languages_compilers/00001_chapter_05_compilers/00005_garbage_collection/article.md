# Сборка мусора

Управление памятью — одна из фундаментальных задач языков программирования. В языках без автоматической сборки мусора (C, C++) разработчик сам выделяет и освобождает память; ошибки приводят к утечкам, use-after-free и двойному освобождению. Сборка мусора (Garbage Collection, GC) автоматизирует освобождение памяти: среда выполнения отслеживает доступность объектов и освобождает недостижимые.

GC используется в Java, Python, Go, C#, JavaScript, Ruby, Haskell и большинстве современных языков. Существуют принципиально разные подходы к реализации — трассировка (tracing), подсчёт ссылок, региональная память — каждый с уникальными компромиссами по задержке, пропускной способности и паузам. Понимание работы GC критично для написания кода с предсказуемой производительностью и диагностики утечек памяти.

В этой статье мы рассмотрим основные алгоритмы сборки мусора, реализации в популярных средах выполнения (JVM, V8, CPython, Go), влияние GC на производительность и практические рекомендации по работе с управляемой памятью.

## 1. Основные алгоритмы сборки мусора

### 1.1 Reference Counting (подсчёт ссылок)

Простейший алгоритм: каждый объект хранит счётчик ссылок — сколько других объектов/переменных указывают на него. При достижении нуля объект немедленно освобождается.

```c
// Структура объекта с reference counting
typedef struct Object {
    int ref_count;
    // ... данные ...
} Object;

Object *obj_retain(Object *obj) {
    if (obj) obj->ref_count++;
    return obj;
}

void obj_release(Object *obj) {
    if (!obj) return;
    obj->ref_count--;
    if (obj->ref_count == 0) {
        // Освобождаем дочерние ссылки рекурсивно
        for (int i = 0; i < obj->child_count; i++) {
            obj_release(obj->children[i]);
        }
        free(obj);
    }
}
```

**Преимущества**: немедленное освобождение, детерминированное время жизни, нет пауз, малый overhead.

**Главный недостаток**: **циклические ссылки** не освобождаются никогда:

```python
# Python: циклические ссылки не освобождаются чистым ref-counting
class Node:
    def __init__(self):
        self.parent = None

a = Node()
b = Node()
a.child = b   # a → b (ref_count b = 1)
b.parent = a  # b → a (ref_count a = 1)

del a  # ref_count a = 1 (всё ещё указывает b.parent)
del b  # ref_count b = 1 (всё ещё указывает a.child)
# Оба объекта недостижимы, но ref_count != 0 → утечка!
```

CPython использует подсчёт ссылок как основной механизм, дополняя его трассирующим GC для обнаружения циклов.

### 1.2 Mark-and-Sweep (маркировка и очистка)

Классический трассирующий GC. Работает в два прохода:

1. **Mark** (маркировка): начиная с корней (стек, глобальные переменные, регистры), рекурсивно помечает все достижимые объекты
2. **Sweep** (очистка): линейно просматривает кучу, освобождая непомеченные объекты

```python
# Псевдокод Mark-and-Sweep
def garbage_collect():
    # Фаза маркировки
    marked = set()
    roots = get_roots()  # стек, глобальные переменные
    
    def mark(obj):
        if obj in marked: return
        marked.add(obj)
        for ref in obj.references():
            mark(ref)
    
    for root in roots:
        mark(root)
    
    # Фаза очистки
    for obj in heap:
        if obj not in marked:
            heap.free(obj)
        else:
            obj.unmark()  # сбросить флаг для следующего цикла
```

**Stop-the-world**: классический Mark-and-Sweep останавливает все потоки приложения. На больших кучах пауза может достигать секунд — неприемлемо для интерактивных приложений.

**Фрагментация**: после многих циклов куча фрагментируется — много маленьких свободных блоков между занятыми. Решение — уплотнение (compaction).

### 1.3 Mark-and-Compact (маркировка и уплотнение)

После маркировки живые объекты перемещаются в начало кучи, устраняя фрагментацию:

```
До уплотнения:
[A] [   ] [B] [   ] [   ] [C] [D] [   ]
 alive  dead  alive  dead  dead  alive  alive  dead

После уплотнения:
[A] [B] [C] [D] [   ] [   ] [   ] [   ]
                 ← свободное место

Все указатели на A, B, C, D должны быть обновлены!
```

Уплотнение требует обновления **всех указателей** — дорогая операция. Используется в JVM (Serial GC, G1 в фазе evacuation).

### 1.4 Copying GC (копирующий GC)

Делит кучу на два полупространства (semi-spaces). Сборщик копирует живые объекты из "от" (from-space) в "к" (to-space), затем меняет пространства местами:

```
From-space:  [A] [   ] [B] [   ] [C]  ← текущее размещение
To-space:    [   ] [   ] [   ] [   ]  ← пусто

После GC:
From-space:  [   ] [   ] [   ] [   ]  ← теперь пусто (станет to-space)
To-space:    [A] [B] [C] [   ] [   ]  ← живые объекты скопированы
```

**Преимущества**: автоматическое уплотнение (объекты рядом в памяти), allocation bump pointer (очень быстрое выделение).

**Недостатки**: использует только половину кучи, копирование дорого для больших объектов.

Используется в JVM young generation (Eden → Survivor).

## 2. Поколенческая сборка мусора (Generational GC)

Гипотеза поколений (generational hypothesis): большинство объектов умирают молодыми. Профили показывают, что 80-90% объектов недостижимы через несколько мегабайт аллокаций.

### 2.1 Поколения в JVM

JVM heap делится на поколения:

```
┌─────────────────────────────────────────────────────────┐
│                        Heap                             │
├──────────────────────────┬──────────────────────────────┤
│    Young Generation      │    Old Generation            │
├──────────┬───────┬───────┤    (Tenured)                 │
│  Eden    │  S0   │  S1   │                              │
│  (8/10)  │ (1/10)│ (1/10)│                              │
└──────────┴───────┴───────┴──────────────────────────────┘
                                      ↑
                              PermGen/Metaspace (Java 8+)
                              (классы, метаданные)
```

**Young GC (Minor GC)**: собирает только young generation. Быстро (< 100 мс), часто.

```
Аллокация в Eden:
1. Объект создаётся в Eden
2. Minor GC: живые объекты из Eden копируются в S0, возраст = 1
3. Следующий Minor GC: из Eden и S0 в S1, возраст++
4. После tenuring_threshold (по умолчанию 15): объект перемещается в Old Gen

Old GC (Major GC): собирает Old Gen. Медленно, редко.
Full GC: собирает всё. Stop-the-world, очень медленно.
```

### 2.2 Write barriers

Если старый объект ссылается на молодой, Minor GC должен об этом знать (иначе пропустит живые молодые объекты). Это отслеживается через **write barrier** — небольшой код, вставляемый JIT при каждой записи ссылки:

```java
// В байт-коде: obj.field = value
// JIT добавляет:
// 1. Запись: obj.field = value
// 2. Write barrier:
//    if (old_gen(obj) && young_gen(value)) {
//        card_table[addr_to_card(obj)] = dirty; // отметить карточку
//    }
```

**Card table**: куча делится на карточки (512 байт). "Грязная" карточка означает: в этой области есть ссылка из старого поколения в молодое. При Minor GC сканируются только грязные карточки.

### 2.3 Remembered sets

Более точный вариант: для каждой области (region) хранится список внешних ссылок в неё. Используется в G1 GC.

## 3. Современные GC в JVM

### 3.1 G1 GC (Garbage First)

G1 (Java 9 по умолчанию) делит кучу на регионы фиксированного размера (1-32 МБ). Каждый регион может быть Eden, Survivor, Old или Humongous (для больших объектов).

```
┌───┬───┬───┬───┬───┬───┬───┬───┐
│ E │ E │ S │ O │ O │ H │ E │ S │  E=Eden, S=Survivor, O=Old, H=Humongous
└───┴───┴───┴───┴───┴───┴───┴───┘

G1 собирает регионы с наибольшим % мусора (отсюда "Garbage First")
Цель: предсказуемые паузы (-XX:MaxGCPauseMillis=200)
```

G1 комбинирует concurrent marking (параллельно с приложением) и evacuation (stop-the-world).

### 3.2 ZGC и Shenandoah

Для приложений, требующих sub-millisecond паузы:

**ZGC** (Java 15+): паузы < 1 мс независимо от размера кучи (тера-байт масштаб). Работает конкурентно почти на всех фазах. Использует цветные указатели (colored pointers) для отслеживания состояния объекта в самом указателе:

```
64-битный указатель в ZGC:
Биты 0-41:  адрес объекта
Бит  42:    Finalizable (только для финализации)
Бит  43:    Remapped (перемещён ли объект)
Бит  44:    Marked1 (отмечен в текущем цикле)
Бит  45:    Marked0 (отмечен в предыдущем цикле)
```

**Shenandoah**: похож на ZGC, разработан Red Hat, доступен в OpenJDK 12+.

```bash
# Включение ZGC
java -XX:+UseZGC -Xmx4g MyApp

# Включение G1
java -XX:+UseG1GC -Xmx4g -XX:MaxGCPauseMillis=100 MyApp

# Мониторинг GC
java -Xlog:gc*:file=gc.log -Xmx4g MyApp
```

## 4. V8 и JavaScript GC

### 4.1 Orinoco: V8 GC

V8 использует поколенческий GC с двумя пространствами:

- **Young space** (несколько МБ): новые объекты. Minor GC (Scavenge) копирующий, < 1 мс.
- **Old space** (десятки МБ - ГБ): долгоживущие объекты. Major GC (Mark-Sweep-Compact).

```javascript
// Демонстрация GC в V8
function createGarbage() {
    let arr = [];
    for (let i = 0; i < 1000000; i++) {
        arr.push({ value: i, data: new Array(10).fill(0) });
    }
    // arr выходит из scope → объекты становятся мусором
}

// Измерение
const used1 = process.memoryUsage().heapUsed;
createGarbage();
global.gc(); // явный вызов (нужно --expose-gc)
const used2 = process.memoryUsage().heapUsed;
console.log(`Memory freed: ${(used1 - used2) / 1024 / 1024} MB`);
```

### 4.2 Incremental и Concurrent GC

V8 реализует несколько техник для снижения пауз:

- **Incremental marking**: маркировка разбивается на инкременты, выполняемые между задачами JavaScript
- **Concurrent marking**: маркировка на фоновых потоках параллельно с JavaScript
- **Idle-time GC**: GC выполняется в простое браузера

```
Без incremental:        |----STOP-THE-WORLD-GC----|----JS----|
С incremental:   |--JS--|GC|--JS--|GC|--JS--|GC|--JS--|GC|--JS--|
```

## 5. Go GC

### 5.1 Трёхцветный Mark-and-Sweep

Go использует нон-поколенческий (до Go 1.22 — без поколений) конкурентный Mark-and-Sweep с трёхцветной инвариантностью.

Три цвета объектов:
- **Белый**: не посещён (мусор по умолчанию)
- **Серый**: посещён, но дети не обработаны
- **Чёрный**: посещён, все дочерние объекты обработаны

Инвариант: чёрный объект никогда не ссылается на белый (пока GC работает). Write barrier поддерживает инвариант.

```
Начало GC:
  Корни → серые
  
Итерация:
  Берём серый объект:
    Помечаем в чёрный
    Все его белые дочерние → серые
  
До тех пор пока серых нет.
Оставшиеся белые → мусор, освобождаем.
```

### 5.2 GOGC и настройка

```go
package main

import (
    "runtime"
    "runtime/debug"
    "fmt"
)

func main() {
    // Установить порог GC: собирать когда куча увеличилась на 100%
    debug.SetGCPercent(100) // по умолчанию 100

    // Установить мягкое ограничение памяти (Go 1.19+)
    debug.SetMemoryLimit(512 * 1024 * 1024) // 512 МБ

    var stats runtime.MemStats
    runtime.ReadMemStats(&stats)
    fmt.Printf("HeapAlloc: %d KB\n", stats.HeapAlloc/1024)
    fmt.Printf("NumGC: %d\n", stats.NumGC)
    fmt.Printf("PauseTotalNs: %d ms\n", stats.PauseTotalNs/1e6)
}
```

```bash
# Переменная окружения для управления GC
GOGC=200 ./myapp    # GC реже (меньше CPU, больше памяти)
GOGC=50  ./myapp    # GC чаще (больше CPU, меньше памяти)
GOGC=off ./myapp    # GC отключён (не рекомендуется)
```

Go 1.22 добавил экспериментальную поддержку поколений (`GOEXPERIMENT=rangefunc`, а поколенческий GC планируется в будущих версиях).

## 6. CPython GC

### 6.1 Reference Counting + Cyclic GC

CPython комбинирует два механизма:

1. **Reference counting**: основной. Объект освобождается немедленно при refcount=0.
2. **Cyclic GC**: дополнительный. Находит циклические ссылки. Запускается периодически.

```python
import gc
import sys

a = [1, 2, 3]
print(sys.getrefcount(a))  # 2: переменная a + аргумент getrefcount

b = a
print(sys.getrefcount(a))  # 3: a + b + аргумент

del b
print(sys.getrefcount(a))  # 2: a + аргумент

# Явная сборка мусора
gc.collect()

# Диагностика
print(gc.get_count())      # (869, 3, 0) — счётчики поколений
print(gc.get_threshold())  # (700, 10, 10) — пороги для GC

# Поиск циклов вручную
class Node:
    pass

a = Node()
b = Node()
a.ref = b
b.ref = a
del a, b

gc.collect()  # освобождает цикл
```

### 6.2 Поколения в CPython

CPython GC имеет три поколения (generation 0, 1, 2):

```
generation 0: молодые объекты, порог 700 аллокаций
generation 1: выжившие после gen0 GC, порог 10 gen0-сборок
generation 2: долгоживущие, порог 10 gen1-сборок

# gc.get_count() → (gen0_count, gen1_count, gen2_count)
```

Алгоритм нахождения циклов в CPython: каждый объект с `tp_traverse` (может ссылаться на другие объекты) помещается в список отслеживаемых. GC находит объекты с ненулевым refcount только от внешних ссылок (не от других отслеживаемых) — они достижимы. Остальные — цикличный мусор.

## 7. Финализаторы и деструкторы

### 7.1 Java finalize() и Cleaner

`finalize()` устарел в Java 9 и удалён в Java 18. Его главный недостаток — недетерминированность: GC вызывает `finalize()` когда угодно, и объект может воскреснуть.

Современная альтернатива — `java.lang.ref.Cleaner`:

```java
import java.lang.ref.*;

public class Resource implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();
    
    private final Cleaner.Cleanable cleanable;
    private final NativeHandle handle;  // нативный ресурс
    
    public Resource() {
        handle = allocateNativeResource();
        // Регистрируем cleanup action
        // ВАЖНО: не захватываем this в лямбду!
        NativeHandle h = handle;
        cleanable = CLEANER.register(this, () -> h.free());
    }
    
    @Override
    public void close() {
        cleanable.clean(); // явное освобождение
    }
}

// Использование с try-with-resources
try (Resource r = new Resource()) {
    r.doWork();
} // close() вызывается автоматически
```

Cleaner гарантирует вызов cleanup при GC, даже если `close()` не вызван — но не немедленно.

### 7.2 Python __del__

```python
class Resource:
    def __init__(self):
        self.handle = open_resource()
    
    def __del__(self):
        # Вызывается при освобождении объекта
        # Проблема: не вызывается немедленно для объектов с циклами
        # Проблема: не вызывается при выходе интерпретатора (глобальные объекты)
        close_resource(self.handle)
    
    def close(self):
        close_resource(self.handle)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()  # предпочтительный способ

# Всегда используйте context manager
with Resource() as r:
    r.use()
```

## 8. Weak References (слабые ссылки)

Слабые ссылки не увеличивают refcount и не предотвращают GC. Используются для кэшей и наблюдателей:

```python
import weakref

class Cache:
    def __init__(self):
        self._cache = {}
    
    def set(self, key, value):
        # Слабая ссылка: объект будет GC если нет других ссылок
        self._cache[key] = weakref.ref(value)
    
    def get(self, key):
        ref = self._cache.get(key)
        if ref is None:
            return None
        value = ref()  # разыменовываем
        if value is None:
            del self._cache[key]  # объект собран GC
        return value
```

```java
// Java WeakReference
import java.lang.ref.*;

WeakReference<ExpensiveObject> weakRef = new WeakReference<>(new ExpensiveObject());

// Позже:
ExpensiveObject obj = weakRef.get(); // null если GC собрал объект
if (obj != null) {
    obj.use();
}

// SoftReference: собирается только при нехватке памяти (хорошо для кэшей)
SoftReference<byte[]> softRef = new SoftReference<>(new byte[1024 * 1024]);
```

## 9. Производительность и настройка

### 9.1 GC pressure и allocation rate

Высокая скорость аллокации (allocation rate) — основная причина частых GC. Пути снижения:

```java
// ПЛОХО: лишние аллокации в hot path
List<String> processData(List<String> input) {
    List<String> result = new ArrayList<>();
    for (String s : input) {
        result.add(s.toUpperCase()); // новая строка на каждой итерации
    }
    return result;
}

// ЛУЧШЕ: переиспользование объектов
StringBuilder sb = new StringBuilder(); // переиспользуется
void processLine(String line, StringBuilder output) {
    output.setLength(0); // сброс без аллокации
    for (char c : line.toCharArray()) {
        output.append(Character.toUpperCase(c));
    }
}

// Object pooling для тяжёлых объектов
Pool<Connection> connectionPool = new Pool<>(100, Connection::new, Connection::reset);
```

### 9.2 Анализ GC с помощью инструментов

```bash
# Java: включение GC-логирования
java -Xlog:gc*:gc.log:time,uptime,pid,level,tags \
     -XX:+PrintGCDateStamps \
     MyApp

# Анализ GC-логов через GCViewer
# https://github.com/chewiebug/GCViewer

# Heap dump и анализ
jmap -dump:live,format=b,file=heap.hprof PID
jhat heap.hprof  # встроенный анализатор
# или Eclipse MAT: https://eclipse.dev/mat/

# Go: трассировка GC
GODEBUG=gctrace=1 ./myapp
# gc 1 @0.012s 2%: 0.019+1.2+0.003 ms clock, ...
# gc 2 @0.050s 3%: 0.012+0.89+0.002 ms clock, ...
```

### 9.3 GC-friendly паттерны

```java
// Избегайте финализаторов — замедляют GC
// Используйте AutoCloseable + try-with-resources

// Избегайте object graph с глубокими циклами
// GC хуже работает с длинными цепочками

// Предпочитайте примитивные массивы вместо коллекций объектов
// int[] vs Integer[] vs ArrayList<Integer>
// int[] — нет boxing, один объект
// Integer[] — boxing каждого элемента
// ArrayList<Integer> — boxing + object overhead

// Используйте правильный размер буфера
// new byte[1024] vs new byte[1024 * 1024]
// Большие буферы попадают в old gen сразу (если > TLAB_SIZE)
```

## 10. Сравнение подходов к управлению памятью

| Подход | Языки | Задержка | Throughput | Безопасность | Сложность |
|--------|-------|---------|-----------|-------------|---------|
| Ручное управление | C, C++ | Детерминировано | Высокий | Небезопасно | Высокая |
| Reference counting | Python, Swift, ObjC | Почти детерминировано | Средний | Безопасно* | Средняя |
| Tracing GC | Java, Go, JS | Паузы | Высокий (JIT) | Безопасно | Низкая |
| Ownership (Rust) | Rust | Детерминировано | Высокий | Безопасно | Высокая |
| Region-based | RAII C++ | Детерминировано | Высокий | Частично | Средняя |

*Без циклических ссылок; Swift ARC с weak references безопасен

## Заключение

Сборка мусора — не "серебряная пуля". Она решает проблему ручного управления памятью (утечки, dangling pointers, double-free), но вводит новые: паузы, overhead, непредсказуемость. Современные GC (ZGC, G1, Go GC) снизили паузы до долей миллисекунды, но не до нуля.

Для разработчика практически важно: понимать, что именно в коде создаёт нагрузку на GC (высокая скорость аллокации, долгоживущие объекты, циклические ссылки), уметь читать GC-логи и настраивать параметры. Для задач с жёсткими требованиями по задержке (real-time, игры, HFT) может потребоваться Rust или C++, где GC нет вовсе.

## Литература и ссылки

1. Jones, R., Hosking, A., Moss, E. *The Garbage Collection Handbook*. CRC Press, 2011. [https://www.gchandbook.org/](https://www.gchandbook.org/)
2. Wilson, P. R. *Uniprocessor Garbage Collection Techniques*. IWMM 1992. [https://dl.acm.org/doi/10.5555/645648.664824](https://dl.acm.org/doi/10.5555/645648.664824)
3. Oracle JVM GC Tuning Guide. [https://docs.oracle.com/en/java/javase/17/gctuning/](https://docs.oracle.com/en/java/javase/17/gctuning/)
4. Go GC Guide. [https://tip.golang.org/doc/gc-guide](https://tip.golang.org/doc/gc-guide)
5. V8 Blog: Orinoco: young generation garbage collection. [https://v8.dev/blog/orinoco-parallel-scavenger](https://v8.dev/blog/orinoco-parallel-scavenger)
6. CPython garbage collector design. [https://devguide.python.org/internals/garbage-collector/](https://devguide.python.org/internals/garbage-collector/)
7. Lins, R. D. *Cyclic Reference Counting with Lazy Mark-Scan*. IPL, 1992.
8. Wikipedia: Garbage collection (computer science). [https://en.wikipedia.org/wiki/Garbage_collection_(computer_science)](https://en.wikipedia.org/wiki/Garbage_collection_(computer_science))
9. Azul Systems: C4 Algorithm (Continuously Concurrent Compacting Collector). [https://www.azul.com/resources/azul-technology/azul-c4-garbage-collector/](https://www.azul.com/resources/azul-technology/azul-c4-garbage-collector/)
