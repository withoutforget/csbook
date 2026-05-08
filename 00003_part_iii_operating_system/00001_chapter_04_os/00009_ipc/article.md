# IPC: пайпы, сокеты, shared memory, сигналы

## Введение

Процессы изолированы — у каждого своё адресное пространство. Как им общаться? IPC (Inter-Process Communication) — набор механизмов ОС для передачи данных и сигнализации между процессами.

В Unix/Linux существует богатый выбор IPC механизмов: пайпы (одно направление, поток байт), Unix domain сокеты (двунаправленные, потоки и датаграммы), разделяемая память (shared memory — fastest!), очереди сообщений, сигналы. Выбор зависит от требований: скорость, удобство, структурированность данных, синхронизация.

---

## 1. Anonymous Pipes (Анонимные пайпы)

### 1.1 Принцип

Пайп — однонаправленный канал: данные пишутся в один конец, читаются из другого:

```c
int pipefd[2];  // [0] = read end, [1] = write end
pipe(pipefd);
// или pipe2(pipefd, O_CLOEXEC) — безопаснее

// В fork: обычно один конец в parent, другой в child:
if (fork() == 0) {
    close(pipefd[0]);    // ребёнок не читает
    write(pipefd[1], "Hello", 5);
    close(pipefd[1]);
    exit(0);
}
close(pipefd[1]);        // родитель не пишет
char buf[16];
ssize_t n = read(pipefd[0], buf, sizeof(buf));
printf("Got: %.*s\n", (int)n, buf);
```

**Буфер пайпа:** в Linux по умолчанию 65536 байт (16 страниц). Запись в полный пайп блокируется. Чтение из пустого пайпа блокируется. Чтение возвращает 0 (EOF) когда все write-end закрыты.

### 1.2 Shell пайплайны

```bash
# Shell: ls | grep .py | wc -l
# Реализация:
pipe(p1)
if (fork() == 0) { dup2(p1[1], 1); execlp("ls", "ls"); }
pipe(p2)
if (fork() == 0) { dup2(p1[0], 0); dup2(p2[1], 1); execlp("grep", "grep", ".py"); }
if (fork() == 0) { dup2(p2[0], 0); execlp("wc", "wc", "-l"); }
# Родитель: закрыть все концы, ждать дочерних
```

### 1.3 Производительность пайпов

```c
// Пропускная способность пайпа через splice():
#include <fcntl.h>

// splice: нулевое копирование данных через pipe (kernel space только)
ssize_t sent = splice(in_fd, NULL, pipefd[1], NULL, 65536, 0);
ssize_t consumed = splice(pipefd[0], NULL, out_fd, NULL, 65536, 0);
// Данные проходят через pipe без копирования в user space
```

```bash
# Бенчмарк пропускной способности:
time dd if=/dev/zero bs=4096 count=1000000 | dd of=/dev/null bs=4096
# ~4-8 GB/s (зависит от ядра и CPU)
```

---

## 2. Named Pipes (FIFO)

```bash
# Именованный пайп — виден в ФС:
mkfifo /tmp/mypipe
ls -la /tmp/mypipe
# prw-r--r-- 1 user group 0 May  8 ... /tmp/mypipe  (p = pipe)

# Один процесс пишет:
echo "Hello from writer" > /tmp/mypipe &   # блокируется до читателя

# Другой читает:
cat /tmp/mypipe
# Hello from writer
```

FIFO полезны для коммуникации между несвязанными процессами (не родитель-дитя).

---

## 3. Unix Domain Sockets

### 3.1 Преимущества над pipes

Unix domain sockets (UDS) — сокеты в UNIX домене (адрес = путь к файлу):

- **Двунаправленные** (в отличие от pipe — одно направление)
- **SOCK_STREAM** (поток байт) или **SOCK_DGRAM** (датаграммы)
- **fd passing**: можно передать открытый файловый дескриптор другому процессу!
- Быстрее TCP loopback (нет сетевого стека overhead)

### 3.2 Пример UDS сервер-клиент

```c
// server.c
#include <sys/socket.h>
#include <sys/un.h>

#define SOCKET_PATH "/tmp/my_socket"

int main() {
    int server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    
    struct sockaddr_un addr;
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path)-1);
    
    unlink(SOCKET_PATH);  // удалить старый сокет
    bind(server_fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(server_fd, 5);
    
    int client_fd = accept(server_fd, NULL, NULL);
    
    char buf[256];
    ssize_t n = recv(client_fd, buf, sizeof(buf), 0);
    printf("Received: %.*s\n", (int)n, buf);
    
    send(client_fd, "ACK", 3, 0);
    
    close(client_fd);
    close(server_fd);
    unlink(SOCKET_PATH);
    return 0;
}
```

```c
// client.c
int client_fd = socket(AF_UNIX, SOCK_STREAM, 0);

struct sockaddr_un addr;
addr.sun_family = AF_UNIX;
strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path)-1);

connect(client_fd, (struct sockaddr*)&addr, sizeof(addr));
send(client_fd, "Hello", 5, 0);

char buf[16];
recv(client_fd, buf, sizeof(buf), 0);
printf("Server replied: %s\n", buf);
close(client_fd);
```

### 3.3 Передача файловых дескрипторов

Уникальная возможность UDS — передача open fd между процессами:

```c
// Отправить fd через UDS (с ancillary data / SCM_RIGHTS):
void send_fd(int socket_fd, int fd_to_send) {
    struct msghdr msg = {0};
    char buf[CMSG_SPACE(sizeof(int))];
    memset(buf, 0, sizeof(buf));
    
    struct iovec io;
    char dummy = 'x';
    io.iov_base = &dummy;
    io.iov_len = 1;
    
    msg.msg_iov = &io;
    msg.msg_iovlen = 1;
    msg.msg_control = buf;
    msg.msg_controllen = sizeof(buf);
    
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg);
    cmsg->cmsg_level = SOL_SOCKET;
    cmsg->cmsg_type = SCM_RIGHTS;
    cmsg->cmsg_len = CMSG_LEN(sizeof(int));
    *((int*)CMSG_DATA(cmsg)) = fd_to_send;
    
    sendmsg(socket_fd, &msg, 0);
}
// Получение аналогично через recvmsg
```

Используется: systemd socket activation (передаёт готовый сокет сервису), sandboxed processes (права без повышения привилегий).

---

## 4. Shared Memory (Разделяемая память)

Самый быстрый IPC: нет копирования — оба процесса видят одну физическую страницу.

### 4.1 POSIX Shared Memory (shm_open)

```c
#include <sys/mman.h>
#include <fcntl.h>

// Process A: создаём и пишем
int fd = shm_open("/my_shared_mem",    // имя (в /dev/shm/)
                  O_CREAT | O_RDWR,
                  0600);
ftruncate(fd, 4096);                   // установить размер

void *ptr = mmap(NULL, 4096,
                 PROT_READ | PROT_WRITE,
                 MAP_SHARED, fd, 0);
close(fd);

strcpy(ptr, "Hello from A!");          // пишем в shared mem

// Process B: читаем
int fd = shm_open("/my_shared_mem", O_RDONLY, 0);
void *ptr = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, 0);
close(fd);
printf("Got: %s\n", (char*)ptr);       // "Hello from A!"

// Удалить (когда больше не нужно):
shm_unlink("/my_shared_mem");
```

```bash
# Просмотр POSIX shared memory:
ls -la /dev/shm/
# -rw------- 1 user group 4096 May  8 ... my_shared_mem
```

### 4.2 System V Shared Memory (shmget)

Более старый API, но встречается в legacy коде:

```c
#include <sys/ipc.h>
#include <sys/shm.h>

// Создать:
key_t key = ftok("/tmp/my_key_file", 'A');  // генерируем ключ из файла
int shmid = shmget(key, 4096, IPC_CREAT | 0600);

// Подключить:
void *ptr = shmat(shmid, NULL, 0);  // NULL = ОС выберет адрес
strcpy(ptr, "Hello!");

// Отключить:
shmdt(ptr);

// Удалить:
shmctl(shmid, IPC_RMID, NULL);
```

```bash
# Просмотр System V shared memory:
ipcs -m
# ------ Shared Memory Segments --------
# key        shmid  owner  perms  bytes  nattch  status
# 0x41234567 12345  user   600    4096   2
```

### 4.3 Синхронизация shared memory

Shared memory не содержит встроенной синхронизации. Нужны дополнительные примитивы:

```c
// POSIX semaphore в shared memory:
#include <semaphore.h>

typedef struct {
    sem_t mutex;
    int   counter;
    char  data[1024];
} SharedData;

// Инициализация:
SharedData *sd = mmap(NULL, sizeof(*sd), PROT_READ|PROT_WRITE,
                      MAP_SHARED|MAP_ANONYMOUS, -1, 0);
sem_init(&sd->mutex, 1, 1);  // 1 = pshared (между процессами), 1 = начальное значение

// Использование:
sem_wait(&sd->mutex);     // lock
sd->counter++;
memcpy(sd->data, new_data, len);
sem_post(&sd->mutex);     // unlock
```

---

## 5. Message Queues (Очереди сообщений)

### 5.1 POSIX Message Queue

```c
#include <mqueue.h>

// Создать/открыть очередь:
struct mq_attr attr = {
    .mq_maxmsg  = 10,   // максимум 10 сообщений в очереди
    .mq_msgsize = 256,  // максимальный размер сообщения
};
mqd_t mq = mq_open("/my_queue", O_CREAT|O_RDWR, 0600, &attr);

// Отправить:
char msg[] = "Hello, message!";
mq_send(mq, msg, strlen(msg)+1, 0 /* priority */);

// Получить:
char buf[256];
unsigned int priority;
mq_receive(mq, buf, sizeof(buf), &priority);
printf("Received: %s (priority %u)\n", buf, priority);

// Очистить:
mq_close(mq);
mq_unlink("/my_queue");
```

```bash
ls -la /dev/mqueue/
# -rw------- 1 user group 80 May  8 ... my_queue
```

**Особенности:**
- Структурированные сообщения (не просто байт-поток)
- Приоритеты (высокоприоритетные сообщения вытесняют в начало)
- Уведомления (mq_notify) при поступлении сообщения
- Ограниченный буфер → write блокируется при полной очереди

---

## 6. Сигналы

### 6.1 Основные сигналы

Сигналы — асинхронные уведомления процессу:

| Сигнал | Номер | Действие по умолчанию | Назначение |
|--------|-------|-----------------------|-----------|
| SIGHUP | 1 | Terminate | Отключение терминала, reload config |
| SIGINT | 2 | Terminate | Ctrl+C |
| SIGQUIT | 3 | Core dump | Ctrl+\ |
| SIGILL | 4 | Core dump | Недопустимая инструкция |
| SIGFPE | 8 | Core dump | Ошибка FP (деление на 0) |
| SIGKILL | 9 | Terminate | Принудительное убийство (нельзя поймать!) |
| SIGSEGV | 11 | Core dump | Нарушение защиты памяти |
| SIGPIPE | 13 | Terminate | Запись в закрытый pipe |
| SIGTERM | 15 | Terminate | Мягкое завершение (можно поймать) |
| SIGCHLD | 17 | Ignore | Дочерний процесс завершился |
| SIGCONT | 18 | Continue | Продолжить остановленный процесс |
| SIGSTOP | 19 | Stop | Остановить (нельзя поймать, как SIGKILL) |
| SIGUSR1 | 10 | Terminate | Пользовательский сигнал 1 |
| SIGUSR2 | 12 | Terminate | Пользовательский сигнал 2 |

### 6.2 Обработчики сигналов

```c
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>

// Простой обработчик:
void sigint_handler(int sig) {
    printf("\nCaught SIGINT (Ctrl+C). Exiting...\n");
    exit(0);
}

// Более безопасный: только signal-safe функции!
volatile sig_atomic_t stop_requested = 0;
void sigterm_handler(int sig) {
    stop_requested = 1;  // атомарная операция — безопасна в обработчике
}

int main() {
    // Установить обработчик через sigaction (предпочтительно):
    struct sigaction sa;
    sa.sa_handler = sigint_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGINT, &sa, NULL);
    
    // Для SIGTERM:
    struct sigaction st;
    st.sa_handler = sigterm_handler;
    sigemptyset(&st.sa_mask);
    st.sa_flags = 0;
    sigaction(SIGTERM, &st, NULL);
    
    while (!stop_requested) {
        // работа...
    }
    
    // Cleanup
    return 0;
}
```

**Signal-safe функции:** в обработчике сигнала можно вызывать только async-signal-safe функции (write, exit, kill, sigprocmask, sem_post и т.д.). `printf`, `malloc`, `free` — НЕ безопасны в обработчике (могут вызвать deadlock через их внутренние мьютексы).

### 6.3 signalfd — сигналы как fd

```c
#include <sys/signalfd.h>

// Конвертировать сигналы в читаемый fd:
sigset_t mask;
sigemptyset(&mask);
sigaddset(&mask, SIGINT);
sigaddset(&mask, SIGTERM);
sigprocmask(SIG_BLOCK, &mask, NULL);  // заблокировать стандартную обработку

int sfd = signalfd(-1, &mask, SFD_CLOEXEC);

// Добавить sfd в epoll:
// ...

// При событии на sfd:
struct signalfd_siginfo si;
read(sfd, &si, sizeof(si));
printf("Got signal %u from PID %u\n", si.ssi_signo, si.ssi_pid);
```

Преимущество signalfd: сигналы обрабатываются в основном event loop (epoll), а не в прерывающем обработчике. Не нужны volatile, async-signal-safe ограничения.

### 6.4 Отправка сигналов

```bash
# Из shell:
kill -SIGTERM 1234     # послать SIGTERM процессу 1234
kill -9 1234           # SIGKILL (немедленное убийство)
kill -SIGUSR1 1234     # пользовательский сигнал
killall firefox        # по имени
pkill -f "python script.py"  # по regex

# Ctrl+C в терминале: SIGINT ко всей группе процессов терминала
# Ctrl+Z: SIGTSTP (stop) к foreground группе
```

```c
// Из кода:
kill(pid, SIGTERM);        // послать сигнал другому процессу
raise(SIGUSR1);            // послать сигнал себе
kill(0, SIGTERM);          // послать всей группе процессов
kill(-1, SIGTERM);         // послать всем процессам (кроме init)
```

---

## 7. Сравнение механизмов IPC

| Механизм | Скорость | Структурированность | Синхронизация | Сложность |
|----------|---------|---------------------|---------------|-----------|
| Anonymous pipe | High | Нет (байт-поток) | Встроена | Низкая |
| Named pipe | High | Нет | Встроена | Низкая |
| Unix socket (stream) | Very high | Нет | Нет | Средняя |
| Unix socket (dgram) | Very high | Датаграммы | Нет | Средняя |
| Shared memory + sem | Максимальная | Любая | Вручную | Высокая |
| POSIX Message Queue | High | Сообщения + приоритет | Встроена | Средняя |
| Signals | Low | Только номер | Нет | Низкая |
| TCP loopback | Medium | Нет | Нет | Высокая |

**Пропускная способность (приблизительно):**
- Shared memory: **~50-100 GB/s** (просто memcpy)
- Unix socket: **~4-8 GB/s**  
- Pipe: **~4-6 GB/s**
- TCP loopback: **~2-4 GB/s**

---

## 8. Практический пример: сервер-воркер через UDS

```python
# Python: server + workers через Unix domain sockets
import os
import socket
import multiprocessing

SOCKET_PATH = '/tmp/worker.sock'

def worker(worker_id):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_PATH)
    
    while True:
        task = sock.recv(256).decode()
        if task == 'quit':
            break
        result = f"Worker {worker_id}: processed '{task}'"
        sock.send(result.encode())
    
    sock.close()

def server():
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass
    
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(SOCKET_PATH)
    server_sock.listen(5)
    
    # Запустить воркеров:
    workers = [multiprocessing.Process(target=worker, args=(i,))
               for i in range(4)]
    [w.start() for w in workers]
    
    # Принять соединения и раздать задачи:
    clients = [server_sock.accept()[0] for _ in workers]
    
    tasks = ['task_A', 'task_B', 'task_C', 'task_D']
    for i, task in enumerate(tasks):
        clients[i % len(clients)].send(task.encode())
        result = clients[i % len(clients)].recv(256).decode()
        print(result)
    
    # Завершить воркеров:
    for c in clients:
        c.send(b'quit')
        c.close()
    
    [w.join() for w in workers]
    server_sock.close()
    os.unlink(SOCKET_PATH)

server()
```

---

## Заключение

IPC — архитектурный выбор с существенными последствиями:

1. **Pipes** — простота. Для shell-подобных pipeline-ов и простой родитель-потомок коммуникации.

2. **Unix domain sockets** — универсальность: двунаправленные, fd passing, хорошая производительность. Стандарт для daemon коммуникации (systemd, D-Bus, databases).

3. **Shared memory** — максимальная скорость. Для высокопроизводительных систем (аудио серверы, видеообработка, брокеры сообщений). Требует тщательной синхронизации.

4. **Сигналы** — уведомления, не данные. Для управления процессами (SIGTERM/SIGKILL), простой сигнализации (SIGUSR1/2).

---

## Литература и источники

1. Kerrisk, M. (2010). *The Linux Programming Interface*. — Главы 44-63: IPC.

2. Stevens, W. R. (1999). *UNIX Network Programming, Vol. 2: Interprocess Communications* (2nd ed.). Prentice Hall.

3. Wikipedia. *Inter-process communication*. — https://en.wikipedia.org/wiki/Inter-process_communication

4. Linux man pages: `man 2 pipe`, `man 7 unix`, `man 2 shmget`, `man 7 signal`, `man 2 signalfd`.

5. POSIX.1-2017. *IPC section*. — https://pubs.opengroup.org/onlinepubs/9699919799/

6. Drepper, U. (2006). *Kernel Scalability Issues with Traditional IPC*. — glibc/nptl technical notes.

7. D-Bus specification. — https://dbus.freedesktop.org/doc/dbus-specification.html

8. Linux Kernel Documentation. *splice(2), sendfile(2)*. — https://man7.org/linux/man-pages/

9. Python documentation. *multiprocessing — Process-based parallelism*. — https://docs.python.org/3/library/multiprocessing.html

10. Barrera, J., et al. *Comparing IPC Performance on Linux*. — https://lwn.net/Articles/
