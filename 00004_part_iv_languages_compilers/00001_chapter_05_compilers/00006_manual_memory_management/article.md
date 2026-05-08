# Ручное управление памятью, RAII и владение в Rust

Языки с ручным управлением памятью дают разработчику полный контроль над временем жизни объектов: когда выделяется память, сколько она занимает, когда освобождается. Это открывает возможности для детерминированной производительности и минимального overhead, недостижимых при сборке мусора. Но та же свобода является источником целого класса уязвимостей: use-after-free, double-free, buffer overflow, утечки памяти — все они возможны при ручном управлении и недопустимы в автоматически управляемых средах.

Идиома RAII (Resource Acquisition Is Initialization), разработанная Бьярне Страуструпом для C++, изменила подход к управлению ресурсами: привязать время жизни ресурса к объекту на стеке, автоматически освобождая его при выходе из области видимости. Rust пошёл дальше — превратил владение и заимствование в систему типов, гарантируя корректность управления памятью на этапе компиляции без сборщика мусора.

В этой статье мы разберём механику `malloc`/`free` в C, аллокаторы памяти, идиому RAII в C++, а затем систему владения Rust — наиболее значимый прогресс в безопасном управлении памятью за последние десятилетия.

## 1. malloc/free: нижний уровень

### 1.1 Системные вызовы и аллокатор

Программа на C работает с памятью через аллокатор — библиотечный уровень над системными вызовами `brk` и `mmap`:

```c
// Упрощённая схема работы malloc
// 1. При первом вызове malloc инициализирует арену памяти через brk/mmap
// 2. Управляет свободными блоками через free list
// 3. При больших запросах (> MMAP_THRESHOLD, обычно 128 КБ) использует mmap

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

void basic_usage(void) {
    // Выделение памяти
    int *arr = malloc(100 * sizeof(int));
    if (!arr) {
        perror("malloc");
        exit(EXIT_FAILURE);
    }
    
    // Использование
    for (int i = 0; i < 100; i++) arr[i] = i;
    
    // Изменение размера
    arr = realloc(arr, 200 * sizeof(int));
    if (!arr) {
        // Исходный блок НЕ освобождён при ошибке — утечка!
        // Правильно: сохранить указатель до realloc
        exit(EXIT_FAILURE);
    }
    
    // Обнуление при выделении
    int *zeroed = calloc(50, sizeof(int));  // malloc + memset(0)
    
    // Освобождение
    free(arr);
    free(zeroed);
    
    // arr и zeroed теперь dangling pointers!
    // Хороший тон: arr = NULL; zeroed = NULL;
}
```

### 1.2 Типичные ошибки

**Use-after-free**: обращение к памяти после `free`:

```c
int *p = malloc(sizeof(int));
*p = 42;
free(p);
printf("%d\n", *p); // UNDEFINED BEHAVIOR: p — dangling pointer
// На практике: может вывести 42, 0, random, или SIGSEGV
```

**Double-free**: освобождение уже освобождённой памяти:

```c
int *p = malloc(sizeof(int));
free(p);
free(p); // Undefined behavior: искажает внутренние структуры аллокатора
         // Эксплуатируется в heap exploitation
```

**Buffer overflow**: запись за границы буфера:

```c
char buf[10];
strcpy(buf, "Hello, World!"); // 13 символов + \0 в буфер из 10 — overflow!
// Перезаписывает соседние переменные или адрес возврата
```

**Memory leak**: забыта `free`:

```c
void process(void) {
    char *buf = malloc(1024);
    if (parse_header(buf) < 0) {
        return; // утечка! free(buf) забыта
    }
    // ... работа ...
    free(buf);
}
```

### 1.3 Внутреннее устройство malloc (glibc ptmalloc)

glibc использует реализацию ptmalloc2, основанную на Doug Lea malloc. Ключевые концепции:

**Chunk** — единица аллокации. Каждый выделенный или свободный блок имеет заголовок:

```
Выделенный chunk:
┌───────────────────┐ ← prev_size (если prev chunk свободен)
│ size | flags      │ ← размер + флаги (prev_in_use, is_mmap, non_main_arena)
├───────────────────┤ ← указатель, возвращаемый malloc
│ user data         │
│ ...               │
└───────────────────┘

Свободный chunk:
┌───────────────────┐
│ prev_size         │
│ size | flags      │
├───────────────────┤
│ fd (forward ptr)  │ ← указатель на следующий свободный chunk (free list)
│ bk (backward ptr) │ ← указатель на предыдущий свободный chunk
│ (fd_nextsize)     │ ← для больших chunks: по размеру
│ (bk_nextsize)     │
└───────────────────┘
```

**Bins** — списки свободных блоков по размеру:
- `fastbins` (16-80 байт): LIFO-список для мелких блоков без объединения
- `smallbins` (< 512 байт): точные размеры, doubly-linked list
- `largebins` ($\geq$ 512 байт): диапазоны размеров
- `unsorted bin`: блоки только что освобождённые, до сортировки

```c
// Мониторинг состояния кучи
#include <malloc.h>

struct mallinfo2 info = mallinfo2();
printf("Arena size:    %zu bytes\n", info.arena);
printf("Allocated:     %zu bytes\n", info.uordblks);
printf("Free:          %zu bytes\n", info.fordblks);
printf("mmap regions:  %zu\n", info.hblks);
```

### 1.4 jemalloc и tcmalloc

Альтернативные аллокаторы используются для лучшей многопоточной производительности:

```bash
# Замена аллокатора через LD_PRELOAD
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 ./myapp

# tcmalloc (Google)
LD_PRELOAD=/usr/lib/libtcmalloc.so ./myapp

# jemalloc — профилирование
MALLOC_CONF="prof:true,prof_leak:true,lg_prof_interval:25" ./myapp
jeprof --pdf ./myapp jeprof.*.heap > heap.pdf
```

**jemalloc** (Firefox, Redis) использует арены per-CPU, устраняя конкуренцию за лок при многопоточной аллокации.

**tcmalloc** (Google Chrome, многие Google сервисы) использует thread-local cache (TC = Thread Cache) для быстрых аллокаций без блокировок.

## 2. Умные указатели в C++

### 2.1 unique_ptr

`std::unique_ptr` выражает единоличное владение: один объект, один владелец, автоматическое удаление при выходе из scope.

```cpp
#include <memory>
#include <iostream>

struct Resource {
    int data;
    Resource(int d) : data(d) { std::cout << "Created " << data << "\n"; }
    ~Resource() { std::cout << "Destroyed " << data << "\n"; }
};

void use_unique_ptr() {
    auto p = std::make_unique<Resource>(42); // выделяет и конструирует
    std::cout << "Using " << p->data << "\n";
    // деструктор вызывается автоматически при выходе из scope
}

// Передача владения
std::unique_ptr<Resource> create() {
    return std::make_unique<Resource>(100); // move semantics, не копирование
}

void consume(std::unique_ptr<Resource> p) {
    // p владеет ресурсом
} // ресурс освобождается здесь

int main() {
    auto p = create();
    consume(std::move(p)); // передаём владение
    // p теперь nullptr — владение передано
    if (!p) std::cout << "p is null\n";
}
```

### 2.2 shared_ptr и weak_ptr

`std::shared_ptr` — разделяемое владение через подсчёт ссылок. `std::weak_ptr` — ссылка без владения (избегает циклов).

```cpp
#include <memory>
#include <iostream>

struct Node {
    int value;
    std::shared_ptr<Node> next;  // сильная ссылка
    std::weak_ptr<Node> prev;    // слабая ссылка (для избежания циклов)
    
    Node(int v) : value(v) {}
    ~Node() { std::cout << "~Node(" << value << ")\n"; }
};

void shared_ptr_demo() {
    auto n1 = std::make_shared<Node>(1);
    auto n2 = std::make_shared<Node>(2);
    
    n1->next = n2;   // n2.use_count = 2
    n2->prev = n1;   // n1.use_count = 1 (weak не увеличивает!)
    
    // Доступ через weak_ptr
    if (auto locked = n2->prev.lock()) {
        std::cout << "prev value: " << locked->value << "\n";
    }
    
    std::cout << "n1 use_count: " << n1.use_count() << "\n"; // 1
    std::cout << "n2 use_count: " << n2.use_count() << "\n"; // 2
}
// При выходе: n1 уничтожается → n2.use_count = 1 → n2 уничтожается
```

**Overhead shared_ptr**: управляющий блок (control block) хранит strong count и weak count. Инкремент/декремент — атомарные операции, что создаёт overhead на многопоточных системах.

```cpp
// Измерение overhead
// unique_ptr: sizeof = 8 (просто указатель)
// shared_ptr: sizeof = 16 (указатель + указатель на control block)
// control block: ~32 байт (ref count + weak count + deleter + allocator)

static_assert(sizeof(std::unique_ptr<int>) == 8);
static_assert(sizeof(std::shared_ptr<int>) == 16);
```

### 2.3 RAII для произвольных ресурсов

RAII применим не только к памяти — к любому ресурсу (файлы, сокеты, мьютексы, транзакции):

```cpp
// RAII обёртка для FILE*
class FileGuard {
    FILE *file_;
public:
    explicit FileGuard(const char *path, const char *mode) 
        : file_(fopen(path, mode)) {
        if (!file_) throw std::runtime_error("Cannot open file");
    }
    
    ~FileGuard() { if (file_) fclose(file_); }
    
    // Запрет копирования (как unique_ptr)
    FileGuard(const FileGuard&) = delete;
    FileGuard& operator=(const FileGuard&) = delete;
    
    // Разрешение перемещения
    FileGuard(FileGuard&& other) noexcept : file_(other.file_) {
        other.file_ = nullptr;
    }
    
    FILE *get() { return file_; }
};

// Использование
void process_file(const char *path) {
    FileGuard f(path, "r");     // открытие
    char buf[1024];
    while (fgets(buf, sizeof(buf), f.get())) {
        process_line(buf);
        // если здесь исключение — деструктор FileGuard всё равно вызовется!
    }
    // f.~FileGuard() закроет файл автоматически
}
```

## 3. Move semantics в C++

### 3.1 Rvalue references и std::move

C++11 ввёл **семантику перемещения** — передачу ресурсов без копирования. Это ключевой механизм для эффективного использования RAII-объектов.

```cpp
#include <vector>
#include <string>
#include <utility>

// Без move: копирование вектора (O(n))
std::vector<int> copy_vector(std::vector<int> v) {
    return v; // копирование
}

// С move: перемещение (O(1))
std::vector<int> move_vector(std::vector<int>&& v) {
    return std::move(v); // передаём внутренний буфер без копирования
    // v после move в "неопределённом, но валидном" состоянии
}

// Move constructor в пользовательском классе
class Buffer {
    size_t size_;
    char *data_;
public:
    Buffer(size_t n) : size_(n), data_(new char[n]) {}
    
    // Copy constructor (дорого)
    Buffer(const Buffer& other) : size_(other.size_), data_(new char[other.size_]) {
        memcpy(data_, other.data_, size_);
    }
    
    // Move constructor (дёшево: O(1))
    Buffer(Buffer&& other) noexcept 
        : size_(other.size_), data_(other.data_) {
        other.size_ = 0;
        other.data_ = nullptr;  // "ограбленный" объект
    }
    
    ~Buffer() { delete[] data_; }
};
```

### 3.2 Rule of Five

Если класс определяет один из пяти специальных методов — нужно определить все пять:

```cpp
class Resource {
public:
    Resource();                                    // constructor
    ~Resource();                                   // destructor
    Resource(const Resource&);                     // copy constructor
    Resource& operator=(const Resource&);          // copy assignment
    Resource(Resource&&) noexcept;                 // move constructor
    Resource& operator=(Resource&&) noexcept;      // move assignment
};

// Или используйте Rule of Zero: не объявляйте ни одного,
// пусть компилятор генерирует их через умные указатели
class ModernResource {
    std::unique_ptr<Data> data_;    // автоматический move, no copy
    std::string name_;              // автоматический copy + move
    // Компилятор генерирует правильные конструкторы/деструктор
};
```

## 4. Система владения Rust

### 4.1 Три правила владения

Rust обеспечивает управление памятью без GC через систему типов:

1. У каждого значения есть ровно один **владелец** (owner)
2. Когда владелец выходит из scope, значение **сбрасывается** (drop)
3. Значение может быть **перемещено** (move) к новому владельцу или **заимствовано** (borrow)

```rust
fn main() {
    let s1 = String::from("hello"); // s1 владеет строкой
    
    let s2 = s1;  // ПЕРЕМЕЩЕНИЕ: s1 больше не действителен!
    
    // println!("{}", s1);  // Ошибка компиляции:
    // error[E0382]: borrow of moved value: `s1`
    
    println!("{}", s2); // OK: s2 — владелец
    
    // s2 выходит из scope → String::drop() → free()
}
```

```rust
fn takes_ownership(s: String) {
    println!("{}", s);
}  // s сбрасывается здесь

fn main() {
    let s = String::from("world");
    takes_ownership(s);
    // println!("{}", s);  // Ошибка: s перемещён в функцию
}
```

### 4.2 Заимствование (Borrowing)

Вместо передачи владения — заимствование через ссылки:

```rust
fn calculate_length(s: &String) -> usize {  // &String = ссылка (immutable borrow)
    s.len()
}

fn main() {
    let s = String::from("hello");
    let len = calculate_length(&s);  // передаём ссылку, не владение
    println!("Длина '{}' = {}", s, len);  // s всё ещё доступен!
}
```

**Mutable borrow**: изменяемая ссылка — в один момент только одна:

```rust
fn change(s: &mut String) {
    s.push_str(", world");
}

fn main() {
    let mut s = String::from("hello");
    
    change(&mut s);  // изменяемое заимствование
    
    // Нельзя иметь два изменяемых заимствования одновременно:
    let r1 = &mut s;
    // let r2 = &mut s;  // Ошибка: cannot borrow `s` as mutable more than once
    
    // Можно несколько неизменяемых:
    let r1 = &s;
    let r2 = &s;  // OK
    // let r3 = &mut s;  // Ошибка: изменяемое не может сосуществовать с неизменяемым
}
```

### 4.3 Времена жизни (Lifetimes)

Компилятор Rust отслеживает, что ссылка не переживёт значение, на которое указывает:

```rust
// Ошибка: ссылка на локальную переменную уходит наружу
fn dangle() -> &String {  // Ошибка компиляции
    let s = String::from("hello");
    &s  // s удаляется при выходе из функции, ссылка становится dangling!
}

// Правильно: возвращаем владение, не ссылку
fn no_dangle() -> String {
    String::from("hello")
}
```

Явные аннотации времён жизни нужны, когда компилятор не может вывести их автоматически:

```rust
// 'a — время жизни: результат живёт не дольше наименьшего из x и y
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

fn main() {
    let s1 = String::from("long string");
    let result;
    {
        let s2 = String::from("xyz");
        result = longest(s1.as_str(), s2.as_str());
        println!("Longest: {}", result);  // OK: оба живы
    }
    // println!("{}", result);  // Ошибка: s2 больше не жив
}
```

### 4.4 Box, Rc, Arc

Rust предоставляет умные указатели, аналогичные C++:

```rust
use std::rc::Rc;
use std::sync::Arc;
use std::cell::RefCell;

fn main() {
    // Box: единоличное владение на куче (как unique_ptr)
    let boxed = Box::new(42);
    println!("{}", boxed);  // разыменование автоматически
    // boxed освобождается при выходе из scope
    
    // Rc: разделяемое владение (однопоточное, как shared_ptr без thread-safety)
    let shared = Rc::new(String::from("hello"));
    let shared2 = Rc::clone(&shared);  // count = 2
    println!("{} copies: {}", Rc::strong_count(&shared), shared);
    
    // Arc: разделяемое владение (атомарный ref count, многопоточное)
    let arc = Arc::new(42);
    let arc2 = Arc::clone(&arc);
    std::thread::spawn(move || {
        println!("Thread: {}", arc2);  // arc2 перемещён в поток
    }).join().unwrap();
    
    // RefCell: изменяемость через runtime borrow checking (для Rc)
    let shared_mut = Rc::new(RefCell::new(vec![1, 2, 3]));
    shared_mut.borrow_mut().push(4);  // runtime panic вместо compile error
    println!("{:?}", shared_mut.borrow());
}
```

### 4.5 Пример: безопасный парсер

```rust
// Rust гарантирует: нет buffer overflow, нет dangling pointers
fn parse_headers(data: &[u8]) -> Option<Vec<(&str, &str)>> {
    let text = std::str::from_utf8(data).ok()?;  // безопасное преобразование
    let mut headers = Vec::new();
    
    for line in text.split('\n') {
        if line.is_empty() { break; }
        let mut parts = line.splitn(2, ':');
        let name = parts.next()?.trim();
        let value = parts.next()?.trim();
        headers.push((name, value));
    }
    
    Some(headers)
    // Ссылки в headers указывают на data — время жизни привязано
    // Если data освободится, headers использовать нельзя (компилятор запретит)
}
```

## 5. Арены и region-based allocation

### 5.1 Arena Allocator

Арена (bump allocator) — выделяет память последовательно из заранее зарезервированного буфера. Освобождение — сброс указателя к началу:

```c
// Простейший arena allocator
typedef struct Arena {
    char *base;
    size_t used;
    size_t capacity;
} Arena;

Arena arena_create(size_t capacity) {
    Arena a;
    a.base = malloc(capacity);
    a.used = 0;
    a.capacity = capacity;
    return a;
}

void *arena_alloc(Arena *a, size_t size) {
    // Выравнивание по 8 байт
    size = (size + 7) & ~7;
    
    if (a->used + size > a->capacity) return NULL;
    void *ptr = a->base + a->used;
    a->used += size;
    return ptr;
}

void arena_reset(Arena *a) {
    a->used = 0;  // "освобождаем" всё за O(1)
}

void arena_destroy(Arena *a) {
    free(a->base);
}
```

Арены идеальны для задач с понятным временем жизни: парсинг запроса (арена живёт один запрос), игровой фрейм (арена сбрасывается каждый кадр).

```c
// Пример: парсинг JSON-запроса
void handle_request(Arena *request_arena, const char *json) {
    // Все аллокации при парсинге из arena
    JsonNode *root = json_parse(request_arena, json);
    process(root);
    // По завершении запроса сбрасываем arena — O(1), нет free для каждого объекта
    arena_reset(request_arena);
}
```

### 5.2 Pool Allocator

Пул аллоцирует объекты фиксированного размера — нет фрагментации:

```c
typedef struct PoolBlock {
    struct PoolBlock *next;
} PoolBlock;

typedef struct Pool {
    char *memory;
    PoolBlock *free_list;
    size_t object_size;
    size_t count;
} Pool;

Pool pool_create(size_t object_size, size_t count) {
    Pool p;
    p.object_size = (object_size + sizeof(void*) - 1) & ~(sizeof(void*) - 1);
    p.count = count;
    p.memory = malloc(p.object_size * count);
    p.free_list = NULL;
    
    // Инициализируем free list
    char *ptr = p.memory;
    for (size_t i = 0; i < count; i++) {
        PoolBlock *block = (PoolBlock *)ptr;
        block->next = p.free_list;
        p.free_list = block;
        ptr += p.object_size;
    }
    return p;
}

void *pool_alloc(Pool *p) {
    if (!p->free_list) return NULL;
    PoolBlock *block = p->free_list;
    p->free_list = block->next;
    return block;
}

void pool_free(Pool *p, void *ptr) {
    PoolBlock *block = (PoolBlock *)ptr;
    block->next = p->free_list;
    p->free_list = block;
}
```

Пул используется в игровых движках (объекты частиц, пули), серверах (connection objects), везде, где часто создаются/удаляются объекты одного типа.

## 6. AddressSanitizer и Valgrind

### 6.1 AddressSanitizer (ASan)

ASan обнаруживает ошибки работы с памятью с минимальным overhead (2x замедление):

```bash
gcc -fsanitize=address -fno-omit-frame-pointer -g -O1 prog.c -o prog
./prog

# Типичный вывод при use-after-free:
# ==12345==ERROR: AddressSanitizer: heap-use-after-free on address 0x602000000010
# READ of size 4 at 0x602000000010 thread T0
#     #0 0x40057d in main /home/user/prog.c:10
# 0x602000000010 was freed here:
#     #0 0x7f1234567890 in __interceptor_free
#     #1 0x400567 in main /home/user/prog.c:8
# Previously allocated here:
#     #0 0x7f1234567891 in __interceptor_malloc
#     #1 0x400551 in main /home/user/prog.c:6
```

ASan инструментирует каждый доступ к памяти: вставляет red zones вокруг буферов и проверяет shadow memory при каждом чтении/записи.

### 6.2 Valgrind Memcheck

```bash
valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes ./prog

# ==12345== LEAK SUMMARY:
# ==12345==    definitely lost: 1,024 bytes in 1 blocks
# ==12345==    indirectly lost: 512 bytes in 3 blocks
# ==12345==      possibly lost: 0 bytes in 0 blocks
# ==12345==    still reachable: 0 bytes in 0 blocks
# ==12345==         suppressed: 0 bytes in 0 blocks

# Для детального отчёта:
valgrind --tool=massif ./prog  # heap profiling
ms_print massif.out.PID | head -30
```

## 7. Сравнение подходов

| Подход | Производительность | Безопасность | Сложность | Применение |
|--------|-------------------|-------------|---------|----------|
| C malloc/free | Максимум | Низкая | Высокая | Системное ПО, ОС |
| C++ RAII | Почти максимум | Высокая* | Средняя | Приложения, движки |
| Rust ownership | Максимум | Очень высокая | Высокая | Системное + безопасное ПО |
| GC (Java/Go) | Хорошая | Высокая | Низкая | Приложения, сервисы |
| ARC (Swift) | Хорошая | Высокая* | Низкая | iOS/macOS приложения |

*C++ RAII безопасен при корректном использовании, но не принудителен; Swift ARC безопасен без `unsafe`

## Заключение

Путь от `malloc`/`free` к RAII C++ и системе владения Rust отражает три десятилетия прогресса в безопасном управлении памятью. Каждый подход — компромисс: C даёт абсолютный контроль ценой безопасности, RAII C++ добавляет детерминированность деструкторов, но не мешает написать `use-after-move`, Rust делает целый класс ошибок невозможным на уровне компилятора ценой кривой обучения.

Системы владения Rust повлияли на другие языки: Swift использует ARC с аналогичными концепциями, C++ рабочая группа обсуждает lifetime annotations, а research languages исследуют ownership в разных формах. Тренд ясен: управление памятью уходит от ручного контроля к системно-верифицированным гарантиям.

## Литература и ссылки

1. Stroustrup, B. *The C++ Programming Language*, 4th ed. Addison-Wesley, 2013. [https://www.stroustrup.com/4th.html](https://www.stroustrup.com/4th.html)
2. Klabnik, S., Nichols, C. *The Rust Programming Language*. No Starch Press, 2019. [https://doc.rust-lang.org/book/](https://doc.rust-lang.org/book/)
3. Drepper, U. *What Every Programmer Should Know About Memory*. 2007. [https://www.akkadia.org/drepper/cpumemory.pdf](https://www.akkadia.org/drepper/cpumemory.pdf)
4. Doug Lea malloc. [http://gee.cs.oswego.edu/dl/html/malloc.html](http://gee.cs.oswego.edu/dl/html/malloc.html)
5. AddressSanitizer: A Fast Address Sanity Checker. USENIX ATC 2012. [https://www.usenix.org/system/files/conference/atc12/atc12-final39.pdf](https://www.usenix.org/system/files/conference/atc12/atc12-final39.pdf)
6. Rust Reference: Ownership. [https://doc.rust-lang.org/reference/ownership.html](https://doc.rust-lang.org/reference/ownership.html)
7. jemalloc documentation. [https://jemalloc.net/](https://jemalloc.net/)
8. Wikipedia: RAII. [https://en.wikipedia.org/wiki/Resource_acquisition_is_initialization](https://en.wikipedia.org/wiki/Resource_acquisition_is_initialization)
9. Wikipedia: Smart pointer. [https://en.wikipedia.org/wiki/Smart_pointer](https://en.wikipedia.org/wiki/Smart_pointer)
