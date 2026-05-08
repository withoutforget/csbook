# Статическая и динамическая компоновка

Компоновка (linking) — процесс объединения объектных файлов и библиотек в исполняемую программу. Этот этап часто остаётся в тени компиляции, но именно он определяет, как программа взаимодействует с системными библиотеками, сколько займёт на диске, как будет обновляться и разделять код с другими процессами. Выбор между статической и динамической компоновкой — архитектурное решение с долгосрочными последствиями.

Статическая компоновка копирует весь необходимый код в исполняемый файл. Динамическая компоновка откладывает разрешение символов на время выполнения, позволяя нескольким процессам разделять один экземпляр библиотеки в памяти. Каждый подход имеет свои преимущества, и реальные системы часто комбинируют оба.

В этой статье мы детально рассмотрим работу компоновщика, механизм PLT/GOT, загрузчик ELF, dlopen/dlsym для явной загрузки, а также специфику компоновки в различных ОС и проблемы совместимости. Примеры будут на C и Linux, но концепции применимы ко всем платформам.

## 1. Объектные файлы и символы

### 1.1 Объектный файл

Компилятор преобразует каждый .c файл в объектный файл (.o или .obj) — машинный код с нерешёнными ссылками на внешние символы.

```bash
# Компиляция без компоновки
gcc -c math_utils.c -o math_utils.o
gcc -c main.c -o main.o

# Просмотр символов
nm main.o
# 0000000000000000 T main        # T = текстовый сегмент (определён здесь)
# 0000000000000000 U sqrt        # U = undefined (нерешённая ссылка)
# 0000000000000000 U printf      # U = undefined
```

Символы бывают:
- **Defined (T, D, B)**: определены в этом объектном файле (код, инициализированные данные, BSS)
- **Undefined (U)**: упоминаются, но определены в другом файле
- **Weak (W)**: определены, но могут быть перекрыты сильными символами

### 1.2 Процесс компоновки

Компоновщик (ld, gold, lld) выполняет три основные задачи:

1. **Symbol resolution**: сопоставление неопределённых символов с их определениями
2. **Relocation**: обновление адресов в коде (во время компиляции адреса неизвестны)
3. **Section merging**: объединение одноимённых секций из разных объектных файлов

```
main.o: [.text: main, .text: helper]  → вызывает sqrt (U)
math.o: [.text: sqrt]                  → определяет sqrt

Компоновщик:
1. Symbol table: sqrt определён в math.o
2. Relocation: в main.o по смещению 0x20 стоит CALL ???? → заменить на CALL sqrt_addr
3. Merging: .text из main.o + .text из math.o → единая секция .text
```

### 1.3 Таблица релокаций

Объектный файл содержит таблицу релокаций — список мест, требующих исправления адресов:

```bash
objdump -r main.o
# main.o:     file format elf64-x86-64
# RELOCATION RECORDS FOR [.text]:
# OFFSET           TYPE              VALUE
# 0000000000000015 R_X86_64_PLT32    sqrt-0x0000000000000004
# 0000000000000020 R_X86_64_PLT32    printf-0x0000000000000004
```

Тип `R_X86_64_PLT32` означает: вставить адрес через PLT (Procedure Linkage Table) — механизм для динамически компонуемых функций.

## 2. Статическая компоновка

### 2.1 Создание статической библиотеки

```bash
# Компиляция объектных файлов
gcc -c utils.c -o utils.o
gcc -c math_ext.c -o math_ext.o

# Создание статической библиотеки (архив)
ar rcs libutils.a utils.o math_ext.o

# Содержимое архива
ar t libutils.a
# utils.o
# math_ext.o

# Статическая компоновка
gcc main.o -L. -lutils -lm -static -o program
# -L.     поиск библиотек в текущей директории
# -lutils ищет libutils.a (или libutils.so)
# -static принудительно статическая компоновка
```

### 2.2 Что делает компоновщик при статической компоновке

Из архива (.a) компоновщик включает только **нужные** объектные файлы — те, что разрешают ссылки. Это называется selective extraction:

```
main.o → нужна функция compute
libutils.a содержит:
  utils.o  → определяет compute, helper
  math.o   → определяет sqrt_fast, cbrt_fast (не нужны)

Компоновщик включает utils.o (нужен compute)
Не включает math.o (не нужен никому)
```

Отсюда правило: библиотеки указываются после объектных файлов, которые их используют:

```bash
gcc main.o -lutils   # ПРАВИЛЬНО: main.o → нужна lutils
gcc -lutils main.o   # НЕПРАВИЛЬНО: lutils уже обработана до main.o
```

### 2.3 Размер и автономность

Статически скомпилированная программа содержит всё необходимое:

```bash
# Статическая компоновка
gcc hello.c -static -o hello_static
ls -lh hello_static
# -rwxr-xr-x 1 user 900K hello_static  ← все библиотеки внутри

# Динамическая компоновка
gcc hello.c -o hello_dynamic
ls -lh hello_dynamic
# -rwxr-xr-x 1 user 16K hello_dynamic  ← только ссылки на библиотеки

ldd hello_static
# not a dynamic executable  ← нет зависимостей

ldd hello_dynamic
# linux-vdso.so.1
# libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6
# /lib64/ld-linux-x86-64.so.2
```

Статические бинарники — идеал для контейнеров (scratch image) и дистрибуции инструментов. Go по умолчанию компилирует статически (если нет cgo):

```bash
go build -o myapp main.go
ldd myapp  # not a dynamic executable
```

## 3. Динамическая компоновка и загрузка

### 3.1 ELF Dynamic Linker

При запуске ELF-файла ядро находит интерпретатор из секции `.interp` — это динамический компоновщик (ld-linux.so). Он выполняется до `main`:

```bash
objdump -p /bin/ls | grep INTERP
# INTERP        /lib64/ld-linux-x86-64.so.2
```

Последовательность загрузки:

```
1. Ядро загружает ELF-заголовок и PT_INTERP сегмент
2. Ядро загружает ld-linux.so.2 в адресное пространство процесса
3. ld-linux.so.2 получает управление:
   a. Читает PT_DYNAMIC секцию — список зависимостей (DT_NEEDED)
   b. Загружает каждую зависимую .so в память (mmap)
   c. Решает символы (symbol resolution)
   d. Выполняет релокации
   e. Вызывает конструкторы .init_array
4. Передаёт управление _start → main
```

### 3.2 PLT и GOT: ленивая привязка

Ключевой механизм динамической компоновки — PLT (Procedure Linkage Table) и GOT (Global Offset Table).

**Проблема**: при первом вызове `printf` её адрес неизвестен (зависит от базового адреса загрузки libc). Его можно разрешить немедленно (eager binding) или при первом обращении (lazy binding).

**Lazy binding** (по умолчанию): первый вызов разрешает адрес через PLT-заглушку, последующие — прямо через GOT.

```
Вызов printf из main:
  CALL printf@PLT      → прыгает в PLT[n]

PLT[n] (до первого вызова):
  JMP  *GOT[n]         → GOT[n] = адрес следующей инструкции в PLT
  PUSH n               → номер символа для разрешения
  JMP  PLT[0]          → вызываем resolver

PLT[0] (resolver):
  JMP  *GOT[1]         → вызываем _dl_runtime_resolve из ld.so
  
_dl_runtime_resolve:
  → ищет символ printf в таблице символов libc.so
  → записывает адрес printf в GOT[n]
  → вызывает printf

Второй вызов printf:
  CALL printf@PLT      → PLT[n]
  JMP  *GOT[n]         → GOT[n] = реальный адрес printf
  → немедленный переход, без resolver
```

```c
// Просмотр PLT/GOT
objdump -d -j .plt program
// 00000000004004b0 <printf@plt>:
//   4004b0:  jmpq   *0x200b62(%rip)   # GOT[n]
//   4004b6:  pushq  $0x0
//   4004bb:  jmpq   4004a0 <_init+0x28>

objdump -R program
// DYNAMIC RELOCATION RECORDS
// 0000000000601018 R_X86_64_JUMP_SLOT  printf
```

### 3.3 Отключение ленивой привязки (BIND_NOW)

```bash
# Eager binding: все символы разрешаются при загрузке
gcc -Wl,-z,now prog.c -o prog
# или
LD_BIND_NOW=1 ./prog

# Проверка
readelf -d prog | grep FLAGS
# (BIND_NOW) Не использовать ленивую привязку
```

Eager binding предпочтительна в security-чувствительных приложениях: нет PLT-trampolines, которые можно эксплуатировать через GOT overwrites.

### 3.4 Position-Independent Code (PIC)

Разделяемые библиотеки должны загружаться по произвольному адресу (ASLR). Для этого код должен быть позиционно-независимым (PIC):

```bash
# Создание разделяемой библиотеки
gcc -fPIC -c mylib.c -o mylib.o    # -fPIC = position-independent code
gcc -shared -o libmylib.so mylib.o
```

В PIC-коде все ссылки на глобальные переменные и функции идут через GOT. Смещение от PC до GOT известно в compile-time, но абсолютные адреса в GOT заполняются загрузчиком.

## 4. dlopen: явная загрузка

### 4.1 Загрузка библиотек во время выполнения

```c
#include <dlfcn.h>
#include <stdio.h>

int main(void) {
    // Открыть библиотеку
    void *handle = dlopen("libmylib.so", RTLD_LAZY);
    if (!handle) {
        fprintf(stderr, "dlopen: %s\n", dlerror());
        return 1;
    }
    
    // Получить указатель на функцию
    typedef int (*compute_t)(int, int);
    compute_t compute = (compute_t)dlsym(handle, "compute");
    
    char *error = dlerror();
    if (error) {
        fprintf(stderr, "dlsym: %s\n", error);
        dlclose(handle);
        return 1;
    }
    
    // Вызвать функцию
    int result = compute(10, 20);
    printf("Result: %d\n", result);
    
    // Закрыть библиотеку
    dlclose(handle);
    return 0;
}
```

```bash
gcc main.c -ldl -o main  # -ldl для dlopen/dlsym/dlclose
```

### 4.2 Паттерн плагинов

```c
// plugin.h — интерфейс плагина
typedef struct {
    const char *name;
    int (*init)(void);
    int (*process)(const char *input, char *output, size_t len);
    void (*cleanup)(void);
} Plugin;

// plugin_loader.c
#include <dirent.h>
#include <string.h>

Plugin *load_plugin(const char *path) {
    void *handle = dlopen(path, RTLD_LAZY | RTLD_LOCAL);
    if (!handle) return NULL;
    
    // Каждый плагин экспортирует единую точку входа
    Plugin *(*get_plugin)(void) = dlsym(handle, "get_plugin");
    if (!get_plugin) {
        dlclose(handle);
        return NULL;
    }
    
    return get_plugin();
}

// my_plugin.c — конкретный плагин
Plugin *get_plugin(void) {
    static Plugin plugin = {
        .name = "my_plugin",
        .init = my_init,
        .process = my_process,
        .cleanup = my_cleanup
    };
    return &plugin;
}
```

### 4.3 RTLD_GLOBAL vs RTLD_LOCAL

```c
// RTLD_GLOBAL: символы плагина видны другим плагинам
dlopen("plugin.so", RTLD_LAZY | RTLD_GLOBAL);

// RTLD_LOCAL (по умолчанию): символы изолированы
dlopen("plugin.so", RTLD_LAZY | RTLD_LOCAL);

// RTLD_DEEPBIND: плагин предпочитает собственные символы (изоляция версий)
dlopen("plugin.so", RTLD_LAZY | RTLD_DEEPBIND);
```

`RTLD_DEEPBIND` полезен, когда плагин собран с другой версией зависимости (например, другая libssl).

## 5. Поиск библиотек

### 5.1 Порядок поиска в Linux

```
1. DT_RPATH (устаревшее): путь, вшитый в ELF при компоновке
2. LD_LIBRARY_PATH: переменная окружения
3. DT_RUNPATH: путь в ELF (новый формат, после LD_LIBRARY_PATH)
4. /etc/ld.so.cache (из /etc/ld.so.conf)
5. /lib, /usr/lib
```

```bash
# Установка rpath при компоновке
gcc prog.c -L/opt/mylibs -lmylib -Wl,-rpath,/opt/mylibs -o prog

# Просмотр rpath
readelf -d prog | grep RPATH
# 0x000000000000000f (RPATH) Library rpath: [/opt/mylibs]

# Использование $ORIGIN (путь относительно бинарника)
gcc prog.c -Wl,-rpath,'$ORIGIN/../lib' -o prog
# Ищет библиотеки в ../lib относительно директории бинарника
```

### 5.2 ldconfig и кэш

```bash
# Обновление кэша библиотек
sudo ldconfig

# Просмотр кэша
ldconfig -p | grep libssl
# libssl.so.1.1 (libc6,x86-64) => /usr/lib/x86_64-linux-gnu/libssl.so.1.1
```

### 5.3 ldd — анализ зависимостей

```bash
ldd /usr/bin/python3
#   linux-vdso.so.1 (0x00007ffd...)
#   libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007f...)
#   libz.so.1 => /lib/x86_64-linux-gnu/libz.so.1 (0x00007f...)
#   libpthread.so.0 => /lib/x86_64-linux-gnu/libpthread.so.0 (0x00007f...)
#   libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f...)

# Транзитивные зависимости
ldd --verbose /usr/bin/python3

# Осторожно: ldd выполняет программу (через LD_TRACE_LOADED_OBJECTS)
# Для подозрительных бинарников используйте objdump -p:
objdump -p /usr/bin/python3 | grep NEEDED
```

## 6. Разделяемые библиотеки и память

### 6.1 Разделение текстовых страниц

Главное преимущество динамической компоновки — код библиотеки разделяется между процессами:

```
Процесс 1:
  [0x7f...1000] libc.so.6 .text  ←─┐ одна физическая страница
  [0x...A000]   heap               │
  [0x...8000]   main .text         │

Процесс 2:                         │
  [0x7f...2000] libc.so.6 .text  ←─┘ та же физическая страница
  [0x...B000]   heap
  [0x...8000]   main .text
```

```bash
# Посмотреть разделяемые страницы
pmap -d PID
# 00007f1234567000   1840K r-x-- libc-2.31.so   # r-x = только чтение + выполнение
# 00007f1234729000    ---  r---- libc-2.31.so   # gap
# 00007f1234729000    16K r---- libc-2.31.so   # read-only данные
# 00007f123472d000     8K rw--- libc-2.31.so   # read-write данные (не разделяются!)
```

Текстовые (.text) страницы разделяются. Данные (.data, .bss, GOT) — копируются при первой записи (copy-on-write).

### 6.2 Overhead динамической компоновки

```bash
# Сравнение времени запуска
time (for i in $(seq 1000); do ./hello_static > /dev/null; done)
# real    0m0.250s  # ~0.25 мс на запуск

time (for i in $(seq 1000); do ./hello_dynamic > /dev/null; done)
# real    0m0.450s  # ~0.45 мс на запуск (загрузка libc и ld.so)
```

Динамическая компоновка добавляет ~0.2 мс на загрузку в типичном случае. При большом числе зависимостей (Python: ~100 .so файлов) — до 100-500 мс.

## 7. Версионирование и совместимость

### 7.1 Soname и версии библиотек

Разделяемые библиотеки имеют трёхуровневое именование:

```
libssl.so.1.1.1    → реальное имя файла
libssl.so.1.1      → soname (major.minor) — вшит в ELF
libssl.so          → символическая ссылка для компоновки
```

```bash
# Создание библиотеки с soname
gcc -shared -fPIC -Wl,-soname,libmylib.so.1 -o libmylib.so.1.2.3 mylib.c

# Создание символических ссылок
ln -sf libmylib.so.1.2.3 libmylib.so.1
ln -sf libmylib.so.1 libmylib.so

# Soname вшит в программу при компоновке
readelf -d program | grep NEEDED
# (NEEDED)    Shared library: [libmylib.so.1]
# При обновлении libmylib.so.1.3.0 → libmylib.so.1 указывает на новую версию
# Программа получает обновление автоматически
```

### 7.2 Symbol versioning

Механизм symbol versioning в ELF позволяет библиотеке одновременно экспортировать старую и новую версию символа:

```c
// mylib.c — библиотека с версионированием
#include <stdio.h>

// Старая версия (совместимость)
__asm__(".symver func_v1,func@MYLIB_1.0");
int func_v1(int x) {
    return x * 2;  // старый алгоритм
}

// Новая версия (по умолчанию для новых программ)
__asm__(".symver func_v2,func@@MYLIB_2.0");
int func_v2(int x) {
    return x * x;  // новый алгоритм
}
```

```
# mylib.map — карта версий
MYLIB_1.0 {
    global: func;
    local: *;
};

MYLIB_2.0 {
    global: func;
} MYLIB_1.0;
```

```bash
gcc -shared -fPIC -Wl,--version-script=mylib.map -o libmylib.so.2 mylib.c
```

Старые программы, собранные против MYLIB_1.0, будут вызывать `func_v1`. Новые получат `func_v2`. Одна библиотека обслуживает оба случая.

### 7.3 Weak symbols

Слабые символы позволяют программе работать без библиотеки:

```c
// Объявление слабого символа
__attribute__((weak)) void optional_feature(void);

void main_func(void) {
    if (optional_feature) {    // проверяем наличие
        optional_feature();    // вызываем только если есть
    } else {
        // запасной вариант
    }
}
```

Это позволяет опционально использовать библиотеки без ошибок при их отсутствии.

## 8. Компоновка в других языках

### 8.1 Go и cgo

Go может вызывать C-код через cgo:

```go
package main

/*
#include <stdio.h>
#include <math.h>

double compute(double x) {
    return sqrt(x) + sin(x);
}
*/
import "C"
import "fmt"

func main() {
    result := C.compute(C.double(9.0))
    fmt.Printf("Result: %f\n", float64(result))
}
```

```bash
go build  # автоматически компилирует C-код и компонует
```

cgo имеет высокие накладные расходы (~100 нс на вызов) из-за переключения между Go и C runtime.

### 8.2 Rust и FFI

Rust может как вызывать C-библиотеки, так и создавать библиотеки для C:

```rust
// Вызов C из Rust
extern "C" {
    fn sqrt(x: f64) -> f64;
    fn strlen(s: *const i8) -> usize;
}

fn main() {
    let result = unsafe { sqrt(9.0) };
    println!("sqrt(9) = {}", result);
}
```

```rust
// Экспорт функции для C (создаём .so)
#[no_mangle]  // отключает name mangling
pub extern "C" fn compute(x: f64) -> f64 {
    x.sqrt() + x.sin()
}
```

```toml
# Cargo.toml
[lib]
crate-type = ["cdylib"]  # создаёт .so совместимую с C ABI
```

### 8.3 Python и C extensions

Python C extensions компонуются как обычные .so с определёнными соглашениями:

```c
// mymodule.c — Python C extension
#define PY_SSIZE_T_CLEAN
#include <Python.h>

static PyObject *py_compute(PyObject *self, PyObject *args) {
    double x;
    if (!PyArg_ParseTuple(args, "d", &x))
        return NULL;
    return PyFloat_FromDouble(x * x);
}

static PyMethodDef MyMethods[] = {
    {"compute", py_compute, METH_VARARGS, "Compute x squared."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mymodule = {
    PyModuleDef_HEAD_INIT, "mymodule", NULL, -1, MyMethods
};

PyMODINIT_FUNC PyInit_mymodule(void) {
    return PyModule_Create(&mymodule);
}
```

```bash
python3 setup.py build_ext --inplace
# Создаёт mymodule.cpython-39-x86_64-linux-gnu.so

python3 -c "import mymodule; print(mymodule.compute(5.0))"
# 25.0
```

## 9. Проблемы и антипаттерны

### 9.1 Dependency hell

"Ад зависимостей" — конфликт, когда разные компоненты требуют несовместимых версий одной библиотеки:

```
App требует: libssl.so.1.1 (OpenSSL 1.1.x)
Plugin A требует: libssl.so.3 (OpenSSL 3.x)
Конфликт: разные soname — оба можно загрузить
```

Решения:
- **Statically link** зависимости в каждый компонент (раздутие, но изоляция)
- **RTLD_DEEPBIND** при загрузке плагинов
- **Контейнеры** (Docker) для изоляции окружения
- **Nix/Guix** для детерминированного управления зависимостями

### 9.2 LD_PRELOAD атаки

`LD_PRELOAD` позволяет загружать .so перед остальными библиотеками, перекрывая символы:

```bash
# Легитимное использование: мониторинг malloc
LD_PRELOAD=/usr/lib/libmalloc_trace.so ./program

# Атака: перехват функций безопасности
cat > evil.c << 'EOF'
#include <stdio.h>
int verify_password(const char *pass) {
    printf("Stolen: %s\n", pass);
    return 1; // всегда успех
}
EOF
gcc -shared -fPIC evil.c -o evil.so
LD_PRELOAD=./evil.so ./secure_app
```

Защита: setuid/setgid программы игнорируют `LD_PRELOAD`. Также помогают now-binding и read-only GOT (`-Wl,-z,relro,-z,now`).

### 9.3 Symbol visibility

По умолчанию все символы в разделяемой библиотеке экспортируются. Это замедляет загрузку и создаёт риск конфликтов:

```c
// Скрыть все символы по умолчанию
// gcc -fvisibility=hidden mylib.c

// Явный экспорт нужных символов
__attribute__((visibility("default")))
int public_function(int x) {
    return x * 2;
}

static int private_helper(int x) {  // или __attribute__((visibility("hidden")))
    return x + 1;
}
```

```bash
gcc -fvisibility=hidden -shared -fPIC mylib.c -o libmylib.so
# Теперь экспортируется только public_function
```

Сокрытие символов ускоряет загрузку (меньше символов для разрешения) и улучшает инкапсуляцию.

## 10. Сравнение: статическая vs динамическая компоновка

| Критерий | Статическая | Динамическая |
|---------|------------|-------------|
| Размер исполняемого файла | Большой | Маленький |
| Разделение кода между процессами | Нет | Да (экономия RAM) |
| Скорость запуска | Быстрее | Медленнее (загрузка .so) |
| Обновление без перекомпиляции | Нет | Да (замена .so) |
| Зависимости | Нет внешних | Нужны .so нужных версий |
| PLT overhead | Нет | Есть (первый вызов) |
| ASLR безопасность | Хуже (меньше рандомизации) | Лучше |
| Контейнеры (scratch) | Идеал | Нужен OS слой |
| Плагины | Невозможны | Естественны |

## Заключение

Статическая и динамическая компоновка — два подхода с разными компромиссами. Статическая даёт автономность, предсказуемость и простоту развёртывания ценой размера и отсутствия обновлений. Динамическая экономит память при множестве процессов, позволяет обновлять библиотеки без перекомпиляции и реализует паттерн плагинов.

Современная практика склоняется к статической компоновке для изолированных микросервисов и инструментов (Go, Rust), и к динамической для систем с плагинами и разделяемыми компонентами. PLT/GOT остаётся элегантным инженерным решением для lazy binding, хотя для максимальной безопасности рекомендуется now-binding с read-only relocations.

## Литература и ссылки

1. Levine, J. *Linkers and Loaders*. Morgan Kaufmann, 1999. [https://linker.iecc.com/](https://linker.iecc.com/)
2. Drepper, U. *How to Write Shared Libraries*. Red Hat, 2011. [https://www.akkadia.org/drepper/dsohowto.pdf](https://www.akkadia.org/drepper/dsohowto.pdf)
3. ELF-64 Object File Format. [https://refspecs.linuxbase.org/elf/elf.pdf](https://refspecs.linuxbase.org/elf/elf.pdf)
4. GNU ld documentation. [https://sourceware.org/binutils/docs/ld/](https://sourceware.org/binutils/docs/ld/)
5. Linux man page: dlopen(3). [https://man7.org/linux/man-pages/man3/dlopen.3.html](https://man7.org/linux/man-pages/man3/dlopen.3.html)
6. Symbol Versioning. [https://sourceware.org/binutils/docs/ld/VERSION.html](https://sourceware.org/binutils/docs/ld/VERSION.html)
7. Wikipedia: Dynamic linker. [https://en.wikipedia.org/wiki/Dynamic_linker](https://en.wikipedia.org/wiki/Dynamic_linker)
8. Wikipedia: Position-independent code. [https://en.wikipedia.org/wiki/Position-independent_code](https://en.wikipedia.org/wiki/Position-independent_code)
