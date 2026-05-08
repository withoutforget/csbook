# Системные вызовы: мостик между user space и ядром

## Введение

Каждый раз, когда программа открывает файл, отправляет пакет по сети или создаёт новый процесс, она обращается к операционной системе с просьбой выполнить привилегированную операцию. Этот механизм обращения называется **системным вызовом** (system call, syscall).

Системные вызовы — это строго определённый интерфейс между пользовательским кодом (Ring 3) и ядром операционной системы (Ring 0). Они выполняют роль API операционной системы: вместо того чтобы программы напрямую обращались к оборудованию, они запрашивают ядро предоставить нужные услуги. Ядро проверяет права, выполняет операцию и возвращает результат.

Понимание системных вызовов необходимо для системного программирования, оптимизации производительности, отладки и анализа безопасности. В этой статье мы рассмотрим, как устроен механизм системных вызовов, как ядро Linux их обрабатывает, и как разработчику наблюдать и использовать эти вызовы.

## Что такое системный вызов

Системный вызов — это запрос от пользовательской программы к ядру ОС на выполнение операции, требующей привилегий Ring 0. По своей форме это похоже на обычный вызов функции, но механизм совершенно иной.

При обычном вызове функции:
```
prog → CALL инструкция → функция в той же памяти → RET → prog
```

При системном вызове:
```
prog → SYSCALL инструкция → переключение в Ring 0 → ядро обрабатывает → SYSRET → Ring 3 → prog
```

Каждый системный вызов идентифицируется числом — **номером системного вызова** (syscall number). На x86-64 Linux этот номер передаётся в регистре `RAX`, а аргументы — в регистрах `RDI`, `RSI`, `RDX`, `R10`, `R8`, `R9` (до 6 аргументов).

## Инструкция SYSCALL в x86-64

Современный механизм системных вызовов в x86-64 основан на инструкции `SYSCALL`, появившейся в AMD K6 и стандартизированной в AMD64:

```
Пользовательское пространство (Ring 3):
1. RAX ← номер syscall
2. RDI, RSI, RDX, R10, R8, R9 ← аргументы
3. SYSCALL

Процессор (аппаратно):
4. RCX ← RIP (адрес возврата)
5. R11 ← RFLAGS
6. RIP ← MSR_LSTAR (адрес точки входа в ядро)
7. CS, SS ← значения из MSR_STAR (Ring 0 сегменты)

Ядро (Ring 0):
8. Сохраняет регистры пользователя
9. Вызывает sys_call_table[RAX](RDI, RSI, RDX, R10, R8, R9)
10. Результат в RAX
11. SYSRET

Процессор (аппаратно):
12. RIP ← RCX (адрес возврата в user space)
13. RFLAGS ← R11
14. CS, SS ← значения Ring 3
```

Полный пример прямого системного вызова на ассемблере x86-64:

```asm
; hello_syscall.asm — прямые системные вызовы без libc
section .data
    msg db "Hello, kernel!", 10
    msg_len equ $ - msg

section .text
    global _start

_start:
    ; write(1, msg, msg_len)
    mov rax, 1          ; __NR_write = 1
    mov rdi, 1          ; fd = stdout
    mov rsi, msg        ; buf = msg
    mov rdx, msg_len    ; count = msg_len
    syscall
    
    ; exit(0)
    mov rax, 60         ; __NR_exit = 60
    mov rdi, 0          ; status = 0
    syscall
```

```bash
# Компиляция и запуск
nasm -f elf64 hello_syscall.asm -o hello_syscall.o
ld hello_syscall.o -o hello_syscall
./hello_syscall
# Вывод: Hello, kernel!
```

## Legacy механизм: INT 0x80 (x86-32)

До появления `SYSCALL` в 32-битных системах использовалось программное прерывание `INT 0x80`. Этот механизм медленнее, потому что требует прохождения через IDT (Interrupt Descriptor Table) с множеством проверок:

```c
// 32-битный системный вызов write через INT 0x80
// EAX = номер syscall, EBX/ECX/EDX = аргументы
static inline long __syscall32(long num, long arg1, long arg2, long arg3) {
    long result;
    asm volatile(
        "int $0x80"
        : "=a"(result)
        : "a"(num), "b"(arg1), "c"(arg2), "d"(arg3)
        : "memory"
    );
    return result;
}

// Пример: write(1, "Hi\n", 3)
__syscall32(4, 1, (long)"Hi\n", 3);   // __NR_write = 4 в x86-32
```

INT 0x80 до сих пор поддерживается в 64-битных ядрах Linux для запуска 32-битных программ (через layer compatibility), но настоятельно не рекомендуется для новых разработок.

## Таблица системных вызовов (sys_call_table)

В ядре Linux все системные вызовы регистрируются в массиве указателей на функции — `sys_call_table`. Эта таблица инициализируется при загрузке ядра:

```c
// arch/x86/entry/syscall_64.c (упрощённо)
asmlinkage const sys_call_ptr_t sys_call_table[] = {
    [0]  = sys_read,
    [1]  = sys_write,
    [2]  = sys_open,
    [3]  = sys_close,
    [4]  = sys_stat,
    [5]  = sys_fstat,
    // ... и так до конца
    [334] = sys_rseq,
};
```

Входная точка (`entry_SYSCALL_64` в `arch/x86/entry/entry_64.S`) сохраняет регистры, проверяет номер вызова и делегирует в таблицу:

```c
// Упрощённая логика entry_SYSCALL_64
void entry_SYSCALL_64(struct pt_regs *regs) {
    long nr = regs->orig_ax;
    
    if (nr < NR_syscalls && sys_call_table[nr] != NULL) {
        regs->ax = sys_call_table[nr](regs->di, regs->si,
                                       regs->dx, regs->r10,
                                       regs->r8, regs->r9);
    } else {
        regs->ax = -ENOSYS;  // Неизвестный системный вызов
    }
}
```

Полный список системных вызовов Linux можно найти в `/usr/include/asm/unistd_64.h` или в таблице syscall:

```bash
# Просмотр таблицы системных вызовов
cat /usr/include/x86_64-linux-gnu/asm/unistd_64.h | head -30

# Альтернатива через ausyscall
ausyscall --dump | head -20
```

## Ключевые системные вызовы

### open, read, write, close — Работа с файлами

```c
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>

int main(void) {
    // open(pathname, flags, mode) → fd
    int fd = open("/tmp/test.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) { perror("open"); return 1; }
    
    // write(fd, buf, count) → bytes_written
    const char *msg = "Hello, syscall world!\n";
    ssize_t written = write(fd, msg, 22);
    printf("Записано: %zd байт\n", written);
    
    // close(fd)
    close(fd);
    
    // Теперь читаем
    fd = open("/tmp/test.txt", O_RDONLY);
    char buf[128] = {0};
    
    // read(fd, buf, count) → bytes_read
    ssize_t n = read(fd, buf, sizeof(buf) - 1);
    printf("Прочитано %zd байт: %s", n, buf);
    
    close(fd);
    return 0;
}
```

### mmap — Отображение памяти

```c
#include <sys/mman.h>
#include <fcntl.h>

// Выделить анонимную память (аналог malloc, но через mmap)
void *anonymous_mmap(size_t size) {
    void *ptr = mmap(
        NULL,               // Адрес — выбирает ядро
        size,               // Размер
        PROT_READ | PROT_WRITE,  // Права: чтение + запись
        MAP_PRIVATE | MAP_ANONYMOUS, // Анонимная, приватная
        -1,                 // fd не нужен для анонимного mmap
        0                   // Смещение
    );
    if (ptr == MAP_FAILED) return NULL;
    return ptr;
}

// Отобразить файл в память
void *file_mmap(const char *path, size_t *size) {
    int fd = open(path, O_RDONLY);
    struct stat st;
    fstat(fd, &st);
    *size = st.st_size;
    
    void *ptr = mmap(NULL, *size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);  // fd можно закрыть сразу после mmap!
    return ptr;
}
```

### brk — Управление кучей

```c
#include <unistd.h>

// brk() устанавливает верхнюю границу сегмента данных
// malloc() использует brk() и mmap() для выделения памяти

void demo_brk(void) {
    void *current_brk = sbrk(0);    // Получить текущую границу
    printf("Текущий brk: %p\n", current_brk);
    
    // Расширить кучу на 4096 байт
    void *old_brk = sbrk(4096);
    printf("Старый brk: %p, новый brk: %p\n", old_brk, sbrk(0));
    
    // Вернуть память
    brk(old_brk);
}
```

### exit и exit_group

```c
// exit() → только текущий поток
// exit_group() → все потоки процесса (вызывается через _exit())

#include <unistd.h>
#include <stdlib.h>

// Корректное завершение через libc (вызывает atexit handlers, flush буферов)
exit(0);

// Прямое завершение через syscall (без cleanup)
_exit(0);  // → системный вызов exit_group()
```

## strace: наблюдение за системными вызовами

`strace` — незаменимый инструмент для отладки и изучения системных вызовов. Он перехватывает все вызовы и выводит их с аргументами и результатами:

```bash
# Базовое использование
strace ls /tmp

# Фильтрация по конкретным вызовам
strace -e trace=open,openat,read,write cat /etc/hostname

# Пример вывода:
# openat(AT_FDCWD, "/etc/hostname", O_RDONLY) = 3
# read(3, "myhost\n", 4096)                   = 7
# write(1, "myhost\n", 7)                     = 7
# close(3)                                    = 0

# Статистика вызовов (количество и время)
strace -c ls /tmp
# % time     seconds  usecs/call     calls    errors syscall
# ------ ----------- ----------- --------- --------- --------
#  28.00    0.000123          15         8           mmap
#  22.00    0.000097          12         8           read

# Трассировка работающего процесса по PID
strace -p $(pgrep firefox)

# Запись в файл
strace -o /tmp/strace.log python3 my_script.py
```

Практический пример использования strace для понимания работы программы:

```bash
# Что делает команда при запуске?
strace -e trace=execve,open,openat python3 -c "import json"
# execve("/usr/bin/python3", ["python3", "-c", "import json"], ...)
# openat(AT_FDCWD, "/usr/lib/python3.x/json/__init__.py", ...) = ...
```

## libc как обёртка над системными вызовами

В реальном коде программисты редко вызывают системные вызовы напрямую. Вместо этого используется **стандартная библиотека C (libc)** — glibc в Linux, которая предоставляет обёртки с удобным C-интерфейсом:

```
Код программиста → fopen() → glibc → open() syscall → ядро
Код программиста → printf() → glibc → write() syscall → ядро
Код программиста → malloc() → glibc → brk()/mmap() → ядро
```

glibc добавляет:
- Буферизацию ввода-вывода (FILE* буфер в stdio)
- Управление ошибками через errno
- Портируемость (один API на разных POSIX системах)
- Удобные абстракции (FILE* вместо raw fd)

```c
// Сравнение: libc vs прямой syscall
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>

// Через libc (буферизованный ввод-вывод)
void write_via_libc(const char *msg) {
    FILE *f = fopen("/tmp/out.txt", "w");
    fprintf(f, "%s\n", msg);  // Буферизуется в памяти
    fclose(f);                // Здесь вызывается write() + close()
}

// Прямой системный вызов
void write_via_syscall(const char *msg) {
    int fd = open("/tmp/out.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    write(fd, msg, strlen(msg));  // Немедленно в ядро
    write(fd, "\n", 1);
    close(fd);
}
```

## Стоимость системного вызова

Системный вызов — относительно дорогая операция по сравнению с обычным вызовом функции. Рассмотрим, что происходит при каждом syscall:

1. **Переключение контекста Ring 3 → Ring 0**: сохранение регистров, переключение стека
2. **Переключение страничных таблиц** (в некоторых конфигурациях — KPTI)
3. **Инвалидация TLB** (в KPTI-системах)
4. **Выполнение кода ядра**
5. **Обратный переключение Ring 0 → Ring 3**

Типичные задержки (приблизительно, зависят от CPU и конфигурации):

| Операция | Время |
|----------|-------|
| Функциональный вызов (Ring 3) | ~1-3 нс |
| Простой syscall (без KPTI) | ~100-200 нс |
| Syscall с KPTI (Meltdown mitigation) | ~200-400 нс |
| Системный вызов с блокировкой (I/O) | Мс - секунды |

```c
// Бенчмарк стоимости системного вызова
#include <time.h>
#include <unistd.h>
#include <stdio.h>

#define ITERATIONS 1000000

int main(void) {
    struct timespec start, end;
    
    clock_gettime(CLOCK_MONOTONIC, &start);
    
    for (int i = 0; i < ITERATIONS; i++) {
        // getpid() — самый простой syscall
        getpid();
    }
    
    clock_gettime(CLOCK_MONOTONIC, &end);
    
    long ns = (end.tv_sec - start.tv_sec) * 1e9 + 
              (end.tv_nsec - start.tv_nsec);
    printf("Среднее время syscall: %ld нс\n", ns / ITERATIONS);
    return 0;
}
```

## vDSO — Системные вызовы без перехода в ядро

Для системных вызовов, которые ядро может безопасно выполнить без реального переключения привилегий, Linux предоставляет механизм **vDSO** (virtual Dynamic Shared Object).

vDSO — это небольшая динамическая библиотека, которую ядро отображает в адресное пространство каждого пользовательского процесса. Она содержит реализации нескольких syscall, которые могут выполняться прямо в Ring 3, читая данные из специальной разделяемой страницы памяти, которую ядро обновляет.

```bash
# Просмотр vDSO в процессе
cat /proc/self/maps | grep vdso
# 7fff8a3d0000-7fff8a3d2000 r-xp 00000000 00:00 0  [vdso]

# Дамп и анализ vDSO
python3 -c "
import re
with open('/proc/self/maps') as f:
    for line in f:
        if 'vdso' in line:
            print(line.strip())
"
```

Системные вызовы, ускоренные через vDSO:
- `clock_gettime()` — самый важный, используется тысячи раз в секунду
- `gettimeofday()` — устаревший, но популярный
- `time()` — текущее время
- `getcpu()` — номер текущего CPU

```c
#include <time.h>
#include <stdio.h>

// clock_gettime() использует vDSO — НЕТ перехода в Ring 0!
// Ядро обновляет страницу vvar с временем, программа читает её напрямую
void demo_vdso(void) {
    struct timespec ts;
    // Этот вызов обрабатывается в Ring 3 через vDSO:
    clock_gettime(CLOCK_REALTIME, &ts);
    printf("Время: %ld.%09ld\n", ts.tv_sec, ts.tv_nsec);
}
```

Сравнение производительности:

```bash
# Бенчмарк: clock_gettime (vDSO) vs getpid (реальный syscall)
gcc -O2 -o bench bench.c
./bench
# clock_gettime (vDSO): ~8 нс за вызов
# getpid (syscall):     ~150 нс за вызов
```

Ускорение в ~20 раз! Это критически важно для приложений, часто читающих время (логирование, метрики, трассировка).

## Примеры на Python

Python предоставляет доступ к системным вызовам через модуль `os` и `ctypes`:

```python
import os
import sys
import ctypes

# ===== Стандартные операции с файлами через os =====

# os.open() → прямой аналог open() syscall (возвращает fd, не FILE*)
fd = os.open('/tmp/test_syscall.txt', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)

# os.write() → прямой аналог write() syscall
data = b"Hello from Python syscall interface!\n"
written = os.write(fd, data)
print(f"Записано байт: {written}")

# os.close() → close() syscall
os.close(fd)

# Чтение
fd = os.open('/tmp/test_syscall.txt', os.O_RDONLY)
content = os.read(fd, 1024)
print(f"Прочитано: {content.decode()}", end='')
os.close(fd)

# ===== Информация о процессе =====
print(f"PID: {os.getpid()}")
print(f"PPID: {os.getppid()}")
print(f"CWD: {os.getcwd()}")
print(f"UID/GID: {os.getuid()}/{os.getgid()}")

# ===== mmap через Python =====
import mmap

# Создаём файл и отображаем в память
with open('/tmp/mmap_test.bin', 'w+b') as f:
    f.write(b'\x00' * 4096)  # Инициализируем нулями
    
    # MAP_SHARED — изменения видны в файле
    mm = mmap.mmap(f.fileno(), 4096, access=mmap.ACCESS_WRITE)
    
    mm[0:13] = b"Hello, mmap! "
    mm.flush()  # Сбросить в файл
    
    print(f"Из mmap: {mm[0:13]}")
    mm.close()

# ===== Прямой вызов syscall через ctypes =====
libc = ctypes.CDLL(None)  # Загрузить текущий libc

# Вызов getpid напрямую
pid = libc.getpid()
print(f"getpid() через ctypes: {pid}")

# Получить номер syscall для текущей платформы
SYS_getpid = 39  # x86-64 Linux
libc.syscall.restype = ctypes.c_long
result = libc.syscall(SYS_getpid)
print(f"syscall(SYS_getpid) = {result}")
```

## Системные вызовы для управления процессами

```python
import os
import sys

# fork() — создание дочернего процесса
pid = os.fork()

if pid == 0:
    # Дочерний процесс
    print(f"Дочерний процесс: PID={os.getpid()}, PPID={os.getppid()}")
    os._exit(0)  # _exit() — прямой syscall exit_group(), без cleanup
else:
    # Родительский процесс
    print(f"Родительский: PID={os.getpid()}, создан дочерний PID={pid}")
    child_pid, status = os.waitpid(pid, 0)  # wait4() syscall
    print(f"Дочерний {child_pid} завершился со статусом {os.WEXITSTATUS(status)}")
```

```python
import subprocess

# Более безопасный способ через subprocess (использует fork + execve)
result = subprocess.run(
    ['ls', '-la', '/tmp'],
    capture_output=True,
    text=True
)
print(result.stdout[:200])
print(f"Код возврата: {result.returncode}")
```

## Перехват системных вызовов: seccomp

Linux позволяет ограничивать набор системных вызовов, доступных процессу, через механизм **seccomp** (Secure Computing). Это используется в контейнерах (Docker), браузерах (Chrome sandbox) и других системах безопасности:

```python
# Демонстрация seccomp через ctypes (только Linux)
import ctypes
import struct
import os

# seccomp(SECCOMP_SET_MODE_STRICT, 0, NULL)
# В строгом режиме доступны только read, write, _exit, sigreturn
SECCOMP_SET_MODE_STRICT = 0
PR_SET_SECCOMP = 22

libc = ctypes.CDLL(None)

# Обычно используется через libseccomp или docker --security-opt
# Здесь просто демонстрация механизма
print("seccomp доступен через prctl(PR_SET_SECCOMP, ...)")
print(f"Текущий PID: {os.getpid()}")
```

```bash
# Просмотр seccomp фильтра процесса
grep Seccomp /proc/self/status
# Seccomp: 0  (0 = выключен, 1 = strict, 2 = filter)

# Запуск с seccomp фильтром через systemd-run
systemd-run --scope -p SystemCallFilter="read write exit" ./program
```

## Обработка ошибок системных вызовов

Системные вызовы сигнализируют об ошибках через `errno`. При ошибке вызов возвращает `-1` (или `-errno` в пространстве ядра), а `errno` устанавливается в код ошибки:

```c
#include <errno.h>
#include <string.h>
#include <fcntl.h>

void handle_syscall_errors(void) {
    int fd = open("/nonexistent/file", O_RDONLY);
    
    if (fd == -1) {
        // errno содержит код ошибки
        printf("Ошибка: %d (%s)\n", errno, strerror(errno));
        // Вывод: Ошибка: 2 (No such file or directory)
        
        switch (errno) {
            case ENOENT:  printf("Файл не найден\n"); break;
            case EACCES:  printf("Нет прав доступа\n"); break;
            case EMFILE:  printf("Слишком много открытых файлов\n"); break;
            default:      printf("Другая ошибка\n"); break;
        }
    }
}
```

```python
import os
import errno

try:
    fd = os.open('/nonexistent', os.O_RDONLY)
except OSError as e:
    print(f"OSError: {e.errno} ({e.strerror})")
    if e.errno == errno.ENOENT:
        print("Файл не существует")
    elif e.errno == errno.EACCES:
        print("Нет прав доступа")
```

## Интересные и редко используемые системные вызовы

```bash
# Список всех системных вызовов в текущем ядре
python3 -c "
import ctypes
libc = ctypes.CDLL(None)
# Попытка вызвать несуществующий syscall
libc.syscall.restype = ctypes.c_long
result = libc.syscall(9999)  # ENOSYS
import ctypes
print('ENOSYS (нет такого syscall):', result == -1)
"

# Интересные системные вызовы:
# getrandom() — криптографически безопасные случайные числа
python3 -c "import os; print(os.urandom(16).hex())"

# memfd_create() — создать безымянный файл в памяти
# pidfd_open() — файловый дескриптор для процесса (pidfd)
# io_uring_setup() — асинхронный I/O (современная альтернатива epoll)
```

## Заключение

Системные вызовы — это фундаментальный механизм, обеспечивающий безопасное взаимодействие пользовательских программ с ядром. Они реализуют строгую границу между привилегированным и непривилегированным кодом.

Ключевые идеи:
- На x86-64 системные вызовы реализованы через инструкцию `SYSCALL/SYSRET`, значительно быстрее устаревшего `INT 0x80`
- Каждый вызов идентифицируется числом и диспетчеризуется через `sys_call_table`
- libc (glibc) предоставляет удобные обёртки с буферизацией и обработкой ошибок
- Стоимость syscall — сотни наносекунд; для горячих путей используется vDSO
- `strace` — незаменимый инструмент для наблюдения за системными вызовами
- seccomp позволяет ограничить набор доступных вызовов для повышения безопасности

## Литература и источники

1. Kerrisk, Michael. *The Linux Programming Interface*. No Starch Press, 2010. Chapters 3-4: System Programming Concepts, File I/O. ISBN: 978-1-59327-220-3.

2. Bovet, Daniel P., and Marco Cesati. *Understanding the Linux Kernel*, 3rd Edition. O'Reilly Media, 2005. Chapter 10: System Calls. ISBN: 978-0-596-00565-8.

3. Intel Corporation. *Intel® 64 and IA-32 Architectures Software Developer's Manual, Volume 2B*. SYSCALL/SYSRET instruction reference. Intel, 2024.

4. Love, Robert. *Linux System Programming*, 2nd Edition. O'Reilly Media, 2013. ISBN: 978-1-449-33953-1.

5. Drepper, Ulrich. *The Anatomy of a System Call*. LWN.net, 2011. https://lwn.net/Articles/604515/

6. Corbet, Jonathan. *On vsyscalls and the vDSO*. LWN.net, 2011. https://lwn.net/Articles/446528/

7. Linux Kernel Documentation. *syscall(2) man page*. https://man7.org/linux/man-pages/man2/syscall.2.html

8. Matz, Michael, et al. *System V Application Binary Interface: AMD64 Architecture Processor Supplement*. Version 1.0, 2023. https://gitlab.com/x86-psABIs/x86-64-ABI

9. Gregg, Brendan. *Systems Performance: Enterprise and the Cloud*, 2nd Edition. Addison-Wesley, 2020. Chapter 5: Applications. ISBN: 978-0-13-682015-4.

10. Kroah-Hartman, Greg. *Linux Kernel in a Nutshell*. O'Reilly Media, 2006. https://www.kroah.com/lkn/
