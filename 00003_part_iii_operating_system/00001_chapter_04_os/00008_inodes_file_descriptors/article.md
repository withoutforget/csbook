# inode, дескрипторы файлов

## Введение

«Файл — это не имя» — одна из самых важных концепций Unix. Имя файла — это просто метка в каталоге, указывающая на inode. inode — это настоящий файл: структура данных, содержащая метаданные и указатели на блоки данных. Файл может иметь несколько имён (hard links), файл существует пока хотя бы одно имя или открытый дескриптор на него ссылается.

Файловый дескриптор (file descriptor, fd) — целое число, представляющее открытый файл в контексте процесса. Когда вы открываете файл — ядро создаёт запись в таблице открытых файлов, возвращает fd. Все операции (read, write, seek, close) работают через этот fd. Стандартные дескрипторы 0, 1, 2 (stdin, stdout, stderr) — это просто специальные fd, открытые при запуске.

---

## 1. inode

### 1.1 Структура inode

inode (index node) — структура на диске, содержащая метаданные файла:

```c
// Упрощённый ext2/ext4 inode (на диске, 256 байт):
struct ext4_inode {
    uint16_t i_mode;        // Тип файла + права (S_IFREG, S_IFDIR, rwxrwxrwx)
    uint16_t i_uid;         // User ID владельца
    uint32_t i_size_lo;     // Размер файла (нижние 32 бита)
    uint32_t i_atime;       // Время последнего доступа (access)
    uint32_t i_ctime;       // Время последнего изменения inode (change)
    uint32_t i_mtime;       // Время последнего изменения содержимого (modify)
    uint32_t i_dtime;       // Время удаления
    uint16_t i_gid;         // Group ID
    uint16_t i_links_count; // Счётчик жёстких ссылок
    uint32_t i_blocks_lo;   // Число занятых 512-байтных блоков
    uint32_t i_flags;       // EXT4_EXTENTS_FL, EXT4_HUGE_FILE_FL...
    
    // Указатели на блоки данных:
    // В старых ext2/3: 15 блочных указателей (direct, indirect, ...)
    // В ext4: дерево экстентов:
    uint8_t  i_block[60];   // 15 блочных указателей или дерево экстентов
    
    uint32_t i_generation;  // NFS file version
    uint32_t i_file_acl_lo; // File ACL блок
    uint32_t i_size_high;   // Размер файла (верхние 32 бита) — для файлов > 4 GB
    
    // ... дополнительные поля ext4
};
```

**Что inode НЕ содержит:**
- **Имя файла** (оно в каталоге!)
- **Содержимое файла** (только указатели на блоки)

```bash
# Посмотреть inode номер:
ls -i filename
# 1234567 filename

stat filename
# File: filename
# Size: 1234       Blocks: 8        IO Block: 4096   regular file
# Device: fd01h    Inode: 1234567   Links: 1
# Access: 2025-05-08 10:30:00.000000000
# Modify: 2025-05-08 10:25:00.000000000
# Change: 2025-05-08 10:25:00.000000000

# Просмотр содержимого inode (на уровне ФС):
debugfs /dev/sda1
debugfs: stat <1234567>
# Inode: 1234567   Type: regular    Mode:  0644   Flags: 0x80000
# Generation: 3456789   Version: 0x00000001:00000000
# User:  1000   Group:  1000   Project:     0   Size: 1234
# Links: 1   Blockcount: 8
# Fragment:  Address: 0    Number: 0    Size: 0
# extents:
#  (0-0):98765432/1
```

### 1.2 inode номера

Каждый inode имеет уникальный номер в рамках ФС. Некоторые зарезервированы:

```
inode 0:   зарезервирован
inode 1:   список плохих блоков (ext4)
inode 2:   root директория "/"
inode 3-7: зарезервированы ext4 (журнал, потерянные файлы и т.д.)
inode 8+:  обычные файлы и директории
```

---

## 2. Hard Links и Symbolic Links

### 2.1 Hard Links (Жёсткие ссылки)

Запись в каталоге — это пара (имя → inode номер). Несколько имён могут указывать на один inode:

```bash
# Создать hard link:
ln original.txt hardlink.txt

ls -li
# 1234567 -rw-r--r-- 2 user group 1234 ... original.txt
# 1234567 -rw-r--r-- 2 user group 1234 ... hardlink.txt
# ↑ одинаковый inode!                 ↑ Links: 2

# Удалить original — файл остаётся:
rm original.txt
# hardlink.txt ещё доступен, Links: 1

# Файл удаляется только когда Links: 0 И нет открытых fd
```

**Ограничения hard links:**
- Только в рамках одной ФС (разные inode namespaces на разных ФС)
- Нельзя на директории (во избежание циклов, кроме . и ..)

### 2.2 Symbolic Links (Символические ссылки)

Символическая ссылка — файл особого типа, содержащий текстовый путь к другому файлу:

```bash
# Создать символическую ссылку:
ln -s /path/to/original symlink

ls -la symlink
# lrwxrwxrwx 1 user group 18 ... symlink -> /path/to/original

# symlink имеет СВОЙ inode (другой тип файла: l)
# При обращении к symlink: ядро читает путь из него и перенаправляет

# Если original удалён → broken symlink:
ls -la symlink
# lrwxrwxrwx 1 ... symlink -> /path/to/original  ← существует
cat symlink
# cat: symlink: No such file or directory  ← но original нет
```

| Характеристика | Hard Link | Symbolic Link |
|---------------|-----------|---------------|
| Тип | Запись в каталоге | Отдельный inode типа l |
| Разные ФС | Нет | Да |
| На директории | Нет | Да |
| Broken link | Невозможен | Возможен |
| При удалении original | Файл остаётся | Ссылка «ломается» |
| Права доступа | У inode | Всегда lrwxrwxrwx |

---

## 3. Файловые дескрипторы

### 3.1 Три таблицы

```
Процесс A:                Kernel:                    Inodes on disk:
FD Table:            Open File Table (OFT):
fd 0 ─────────────▶ [entry: offset=0, flags=O_RDONLY, ────────▶ inode 1234 (stdin → /dev/pts/0)
fd 1 ─────────────▶ [entry: offset=0, flags=O_WRONLY, ────────▶ inode 5678 (stdout → /dev/pts/0)
fd 2 ─────────────▶ [entry: offset=0, flags=O_WRONLY, ────────▶ inode 5678 (stderr → /dev/pts/0)
fd 3 ─────────────▶ [entry: offset=1024, flags=O_RDWR, ───────▶ inode 9012 (/home/user/file.txt)
fd 4 ─────────────▶ [entry: offset=0, flags=O_RDONLY, ────────▶ inode 3456 (/lib/libc.so.6)

Процесс B:
fd 3 ─────────────▶ [entry: offset=512, flags=O_RDWR, ────────▶ inode 9012 (та же file.txt!)
                    ↑ другая запись в OFT, свой offset!
```

**FD Table (File Descriptor Table):** per-process, индексируется числом fd. Указывает на запись в OFT.

**Open File Table (OFT):** shared для всей системы. Содержит: текущую позицию (offset), флаги (O_RDONLY, O_WRONLY...), указатель на inode.

**Inode Table / VFS inode cache:** in-memory кеш inode-ов.

### 3.2 Стандартные дескрипторы

```
fd 0 = STDIN_FILENO  — стандартный ввод
fd 1 = STDOUT_FILENO — стандартный вывод
fd 2 = STDERR_FILENO — стандартный вывод ошибок

Новые fd выделяются начиная с 3 (наименьший свободный).
```

```c
// Перенаправление вывода программно (как shell делает >):
int fd = open("output.txt", O_WRONLY|O_CREAT|O_TRUNC, 0644);
dup2(fd, STDOUT_FILENO);  // теперь fd 1 → output.txt
close(fd);
// После этого: printf → output.txt вместо терминала
```

### 3.3 open() flags

```c
#include <fcntl.h>

int fd = open("file.txt", flags, mode);

// Access mode (обязательно одно из):
O_RDONLY     // только чтение
O_WRONLY     // только запись
O_RDWR       // чтение и запись

// File creation flags (необязательные):
O_CREAT      // создать если не существует
O_EXCL       // ошибка если файл уже существует (с O_CREAT)
O_TRUNC      // очистить при открытии
O_APPEND     // всегда писать в конец (атомарно!)

// I/O flags:
O_SYNC       // sync: запись не вернётся пока не записано на диск
O_DSYNC      // data sync: только данные (не метаданные)
O_DIRECT     // обойти page cache (прямой I/O)
O_NONBLOCK   // не блокироваться при открытии pipes/device
O_CLOEXEC    // закрыть при exec() (защита утечки fd)
```

### 3.4 Inheritance при fork

```c
// Fork дублирует FD Table:
pid_t pid = fork();
// Дочерний получает КОПИЮ FD Table родителя
// Но указатели в OFT — SHARED (один offset!)

// Проблема: оба процесса используют один offset в OFT
// Случайный interleaving записей в файл

// Решение: O_CLOEXEC или явный close() в дочернем
// O_CLOEXEC: при exec() fd автоматически закрывается
int fd = open("file", O_RDONLY | O_CLOEXEC);

// После fork, перед exec:
if (pid == 0) {
    close(fd);  // дочерний не нуждается в этом fd
    execvp(cmd, args);
}
```

### 3.5 /proc/PID/fd

```bash
# Просмотр открытых fd процесса:
ls -la /proc/1234/fd
# lrwx------ 1 user group 64 ... 0 -> /dev/pts/0
# lrwx------ 1 user group 64 ... 1 -> /dev/pts/0
# lrwx------ 1 user group 64 ... 2 -> /dev/pts/0
# lr-x------ 1 user group 64 ... 3 -> /home/user/file.txt
# lrwx------ 1 user group 64 ... 4 -> socket:[56789]
# lr-x------ 1 user group 64 ... 5 -> pipe:[12345]

# Сводка через lsof:
lsof -p 1234
# COMMAND  PID  USER  FD  TYPE   DEVICE  SIZE/OFF   NODE NAME
# bash    1234  user  cwd DIR    8,1    4096       123  /home/user
# bash    1234  user  txt REG    8,1    1037976    456  /usr/bin/bash
# bash    1234  user  mem REG    8,1    2012312    789  /lib/x86_64.../libc.so.6
# bash    1234  user  0u  CHR    136,0  0t0         3  /dev/pts/0
# bash    1234  user  1u  CHR    136,0  0t0         3  /dev/pts/0
# bash    1234  user  2u  CHR    136,0  0t0         3  /dev/pts/0
```

---

## 4. Специальные файлы

### 4.1 Всё — файл

В Unix философии «всё — файл». Разные типы:

```
Тип     | S_IFMT bits | ls символ | Примеры
--------+-------------+-----------+--------------------------------
regular | S_IFREG     | -         | /etc/passwd, /bin/ls
directory| S_IFDIR    | d         | /home, /etc
symlink | S_IFLNK     | l         | /etc/localtime -> /usr/share/zoneinfo/UTC
block   | S_IFBLK     | b         | /dev/sda, /dev/nvme0n1
char    | S_IFCHR     | c         | /dev/null, /dev/tty, /dev/random
pipe    | S_IFIFO     | p         | mkfifo mypipe
socket  | S_IFSOCK    | s         | /run/systemd/notify
```

```c
// Определить тип файла:
struct stat st;
stat("path", &st);

if (S_ISREG(st.st_mode))  printf("regular\n");
if (S_ISDIR(st.st_mode))  printf("directory\n");
if (S_ISLNK(st.st_mode))  printf("symlink\n");
if (S_ISBLK(st.st_mode))  printf("block device\n");
if (S_ISCHR(st.st_mode))  printf("char device\n");
if (S_ISFIFO(st.st_mode)) printf("pipe\n");
if (S_ISSOCK(st.st_mode)) printf("socket\n");
```

### 4.2 /dev/null и /dev/zero

```bash
# /dev/null: чёрная дыра — всё записанное игнорируется, чтение возвращает EOF
cat large_file.txt > /dev/null        # игнорировать вывод
./noisy_program 2>/dev/null           # игнорировать stderr

# /dev/zero: бесконечный источник нулей
dd if=/dev/zero of=zeros.bin bs=1M count=100  # создать 100 MB нулей

# /dev/full: имитирует полный диск (всегда ENOSPC)
echo test > /dev/full
# bash: /dev/full: No space left on device

# /dev/urandom: случайные байты (псевдослучайные, достаточно быстрые)
head -c 16 /dev/urandom | xxd
# 00000000: a3b2 c1d0 e4f5 1234 5678 9abc def0 abcd  ...

# /dev/random: «истинно» случайные (блокируется при нехватке энтропии)
# В Linux 5.6+ эквивалентен /dev/urandom
```

---

## 5. Директории

### 5.1 Директория как специальный файл

Директория — это файл особого типа, содержащий список записей (имя → inode):

```c
// Структура записи в ext4 директории:
struct ext4_dir_entry_2 {
    uint32_t inode;       // номер inode
    uint16_t rec_len;     // длина этой записи (для перехода к следующей)
    uint8_t  name_len;    // длина имени
    uint8_t  file_type;   // EXT2_FT_REG_FILE, EXT2_FT_DIR, ...
    char     name[];      // имя файла (не null-terminated в структуре!)
};
```

```bash
# Чтение содержимого директории (через opendir/readdir):
ls -la /home/user/
# . → inode 2345678 (сама директория)
# .. → inode 1234567 (родительская директория)
# .bashrc → inode 3456789
# Documents → inode 4567890

# Жёсткая ссылка /./ означает: links count директории = 2 + число поддиректорий
# (каждая поддиректория имеет ".." ссылку на родителя)
stat /home/user/
# Links: 15 (13 поддиректорий + "." + parent's entry)
```

### 5.2 Операции с директориями

```c
#include <dirent.h>

DIR *dp = opendir("/home/user");
struct dirent *entry;

while ((entry = readdir(dp)) != NULL) {
    printf("inode=%-10lu type=%d name=%s\n",
           entry->d_ino, entry->d_type, entry->d_name);
}
closedir(dp);

// entry->d_type:
// DT_REG  = regular file
// DT_DIR  = directory
// DT_LNK  = symlink
// DT_CHR  = char device
// DT_BLK  = block device
// DT_FIFO = named pipe
// DT_SOCK = socket
// DT_UNKNOWN = unknown (некоторые ФС не знают тип без stat())
```

---

## 6. File Descriptor Tricks

### 6.1 dup и dup2

```c
// dup: создать дубликат fd (в наименьший свободный)
int fd = open("file.txt", O_RDONLY);
int fd2 = dup(fd);   // fd2 → тот же файл, тот же offset в OFT

// dup2: перенаправить fd2 на тот же файл что fd
int fd = open("output.txt", O_WRONLY|O_CREAT|O_TRUNC, 0644);
dup2(fd, STDOUT_FILENO);  // stdout → output.txt
close(fd);
printf("This goes to output.txt\n");  // via stdout = fd 1

// dup3 (Linux): dup2 + O_CLOEXEC атомарно:
dup3(fd, new_fd, O_CLOEXEC);
```

### 6.2 Pipe — связать процессы через fd

```c
int pipefd[2];  // pipefd[0] = read end, pipefd[1] = write end
pipe(pipefd);

if (fork() == 0) {
    // Дочерний: пишет в pipe
    close(pipefd[0]);           // закрыть read end
    dup2(pipefd[1], STDOUT_FILENO);  // stdout → pipe write
    close(pipefd[1]);
    execlp("ls", "ls", "-la", NULL);  // вывод ls → pipe
}

// Родительский: читает из pipe
close(pipefd[1]);           // закрыть write end
char buf[4096];
ssize_t n = read(pipefd[0], buf, sizeof(buf));
printf("Received: %.*s\n", (int)n, buf);
```

### 6.3 sendfile — zero-copy

```c
#include <sys/sendfile.h>

// Копирование файла без user space буфера:
int in_fd = open("source.bin", O_RDONLY);
int out_fd = open("dest.bin", O_WRONLY|O_CREAT|O_TRUNC, 0644);

struct stat st;
fstat(in_fd, &st);

off_t offset = 0;
sendfile(out_fd, in_fd, &offset, st.st_size);
// Данные идут из page cache прямо в socket buffer или другой fd
// Никакого копирования в user space!
```

### 6.4 epoll — эффективный мониторинг множества fd

```c
#include <sys/epoll.h>

int epfd = epoll_create1(0);

// Добавить fd в мониторинг:
struct epoll_event ev;
ev.events = EPOLLIN | EPOLLET;  // event: есть данные для чтения, edge-triggered
ev.data.fd = socket_fd;
epoll_ctl(epfd, EPOLL_CTL_ADD, socket_fd, &ev);

// Ожидать событий:
struct epoll_event events[64];
int n = epoll_wait(epfd, events, 64, -1);  // -1 = без таймаута
for (int i = 0; i < n; i++) {
    if (events[i].events & EPOLLIN) {
        handle_read(events[i].data.fd);
    }
}
```

epoll масштабируется до миллионов fd (в отличие от `select` с O(n) проверкой).

---

## 7. Пример: "ls -l" изнутри

```python
import os
import stat
import pwd
import grp
from datetime import datetime

def my_ls(path):
    entries = os.listdir(path)
    for name in sorted(entries):
        full_path = os.path.join(path, name)
        st = os.lstat(full_path)  # lstat не следует по symlinks
        
        # Тип и права:
        mode = stat.filemode(st.st_mode)
        
        # Число ссылок:
        nlink = st.st_nlink
        
        # Владелец и группа:
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group = str(st.st_gid)
        
        # Размер:
        size = st.st_size
        
        # Время изменения:
        mtime = datetime.fromtimestamp(st.st_mtime).strftime('%b %d %H:%M')
        
        # Для symlink — добавить цель:
        extra = ''
        if stat.S_ISLNK(st.st_mode):
            extra = f' -> {os.readlink(full_path)}'
        
        print(f"{mode} {nlink:3} {owner:8} {group:8} {size:8} {mtime} {name}{extra}")

my_ls('/tmp')
```

---

## Заключение

inode и file descriptors — фундаментальные абстракции Unix:

1. **inode** отделяет имя файла от его содержимого. Файл «живёт» пока есть хотя бы одна ссылка (hard link) или открытый fd.

2. **Hard links** — несколько имён для одного inode. Дешёвы, но ограничены одной ФС.

3. **Symbolic links** — гибкие ссылки через путь. Могут быть broken.

4. **FD Table** — per-process, **OFT** — shared. fork() дублирует FD Table, но записи в OFT разделяются (общий offset!).

5. **O_CLOEXEC** — хорошая практика: fd, не нужные в дочернем процессе после exec, должны закрываться автоматически.

---

## Литература и источники

1. Kerrisk, M. (2010). *The Linux Programming Interface*. — Главы 4-5: File I/O, Directories and Links.

2. Wikipedia. *inode*. — https://en.wikipedia.org/wiki/Inode

3. Wikipedia. *File descriptor*. — https://en.wikipedia.org/wiki/File_descriptor

4. Linux man pages: `man 2 open`, `man 2 stat`, `man 2 dup2`, `man 2 epoll_wait`.

5. Stevens, W. R. (2005). *Unix Network Programming, Vol. 1* (3rd ed.). — Глава 6: I/O Multiplexing.

6. Ritchie, D. M. (1984). *The Evolution of the Unix Time-sharing System*. AT&T Bell Laboratories Technical Journal. — https://www.bell-labs.com/usr/dmr/www/hist.html

7. Bovet & Cesati. *Understanding the Linux Kernel* (3rd ed.). — Глава 12: VFS.

8. Linux source. `fs/ext4/inode.c`, `fs/namei.c`. — https://github.com/torvalds/linux

9. The Open Group. *POSIX.1-2017: open, dup2, stat*. — https://pubs.opengroup.org/onlinepubs/9699919799/

10. lsof manual. — https://man7.org/linux/man-pages/man8/lsof.8.html
