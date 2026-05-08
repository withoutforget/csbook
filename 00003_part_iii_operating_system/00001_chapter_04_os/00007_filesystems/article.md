# Файловые системы (ext4, NTFS, APFS, ZFS)

## Введение

Файловая система — это то, как данные организованы на диске. Когда вы сохраняете файл, ФС решает: в какие именно блоки диска записать данные, как связать имя файла с этими блоками, где хранить метаданные (размер, права, время). При чтении — обратный процесс. Выбор файловой системы влияет на производительность, надёжность, возможность восстановления после сбоя.

Современные ФС решают задачи гораздо сложнее простого «хранение файлов»: журналирование (гарантии целостности при сбое питания), Copy-on-Write (атомарные снапшоты), сквозные контрольные суммы (обнаружение тихой порчи данных), дедупликация, сжатие. Сравнение ext4, NTFS, APFS и ZFS — это сравнение разных философий проектирования.

---

## 1. Физическое хранение: блоки и суперблок

### 1.1 Блоки и инодовая структура

Любая ФС делит дисковое пространство на блоки (обычно 4 KB). Каждый файл занимает один или несколько блоков. Метаданные (имя, размер, время, права) хранятся отдельно от данных — в inode (index node).

**Суперблок (Superblock):** первый блок ФС, содержащий:
- Magic number (тип ФС)
- Размер блока (1/2/4/8 KB)
- Число блоков и свободных блоков
- Число inode и свободных inode
- Время последнего монтирования/проверки
- Состояние (чистое/грязное)

```bash
# Просмотр суперблока ext4:
sudo tune2fs -l /dev/sda1
# Filesystem magic number:  0xEF53
# Block count:              30769152
# Free blocks:              15234567
# Inode count:              7700096
# Free inodes:              7234512
# Block size:               4096
# Last mounted on:          /
# Last write time:          Thu May  8 10:23:45 2025
```

### 1.2 Block Groups (ext4)

ext4 делит диск на **block groups** — независимые регионы:

```
Диск:
[Block Group 0][Block Group 1][Block Group 2]...

Каждый Block Group содержит:
- Superblock (copy, только в первых нескольких)
- Group Descriptor
- Block Bitmap (1 бит/блок: занят или свободен)
- Inode Bitmap
- Inode Table (inode записи)
- Data Blocks (реальные данные)
```

Выгода: файл и его inode в одной группе → меньше перемещений головки HDD → быстрее.

---

## 2. ext4 (Linux)

### 2.1 Journaling (Журналирование)

Без журналирования: при сбое питания в середине записи ФС остаётся в несогласованном состоянии. Восстановление — долгий `fsck`.

**Journaling:** перед изменением ФС записываем намерение в журнал (journal). После полной записи — помечаем транзакцию завершённой. При сбое — воспроизводим незавершённые транзакции.

ext4 поддерживает три режима журналирования:

| Режим | Что журналируется | Скорость | Надёжность |
|-------|-------------------|---------|-----------|
| `writeback` | Только метаданные (без порядка) | Высокая | Данные могут быть устаревшими после сбоя |
| `ordered` (default) | Метаданные + данные записываются до метаданных | Средняя | Хорошая |
| `journal` | Метаданные + данные | Низкая | Максимальная |

```bash
# Посмотреть режим журналирования:
tune2fs -l /dev/sda1 | grep "Default mount"
# Default mount options:    user_xattr acl

# Монтирование с явным указанием режима:
mount -o data=journal /dev/sda1 /mnt
```

### 2.2 Extents (Экстенты)

Старые ФС хранили адреса блоков файла как массив (block pointer array). Для большого файла нужно много косвенных блоков.

ext4 использует **extents** — описание непрерывных диапазонов блоков:

```c
struct ext4_extent {
    uint32_t ee_block;    // первый логический блок файла
    uint16_t ee_len;      // число блоков в экстенте
    uint16_t ee_start_hi; // физический начальный блок (старшие биты)
    uint32_t ee_start_lo; // физический начальный блок (младшие биты)
};

// Дерево экстентов: i_block в inode хранит корень B-tree экстентов
```

Один экстент может описать до 32768 непрерывных блоков (128 MB). Для последовательно записанного файла — достаточно 1-2 экстентов вместо тысяч указателей.

### 2.3 Производительность ext4

```bash
# Создать большой файл и измерить скорость:
dd if=/dev/zero of=/tmp/test_write bs=1M count=1024 oflag=direct
# (direct: без page cache, измеряем реальную скорость диска)
# 1073741824 bytes (1.1 GB, 1.0 GiB) copied, 2.5 s, 429 MB/s

# Скорость чтения:
dd if=/tmp/test_write of=/dev/null bs=1M iflag=direct
# 1073741824 bytes, 1.3 s, 826 MB/s (NVMe SSD)

# Дефрагментация (обычно не нужна с ext4):
e4defrag /dev/sda1
```

---

## 3. NTFS (Windows)

### 3.1 MFT — Master File Table

NTFS хранит всё в **MFT (Master File Table)** — таблице записей о файлах:

- Каждый файл/директория = одна или несколько MFT-записей (1 KB каждая)
- Маленькие файлы (< 700 байт) хранятся прямо в MFT-записи (resident attributes)
- Большие файлы → MFT запись содержит VCN→LCN mapping (аналог экстентов)

```
MFT Record (1024 байт):
+---------+--------------------+
| Header  | Attributes ...    |
+---------+--------------------+

Стандартные атрибуты:
$STANDARD_INFORMATION: MAC times, flags (read-only, hidden...)
$FILE_NAME: имя файла (Unicode), родительский каталог
$DATA: данные файла (resident для малых файлов)
$INDEX_ROOT: содержимое директории (для директорий)
$SECURITY_DESCRIPTOR: ACL (права доступа)
```

### 3.2 B-tree в NTFS

Директории в NTFS организованы как B+-tree (индексы NTFS):

```
Директория /Windows/:
           [M]
          /   \
        [G-L] [N-Z]
       /  |  \   ...
    [G] [H-I] [J-L]
```

Поиск файла в директории с 100,000 файлами: O(log n) вместо O(n) для линейного поиска. NTFS обязательно использует B-tree для больших директорий.

### 3.3 Journaling в NTFS

NTFS использует журналирование метаданных (похоже на ext4 ordered mode):

```
$LogFile: журнал транзакций NTFS
$UsnJrnl: USN (Update Sequence Number) журнал — log всех изменений файлов
          Используется Windows Backup, антивирусами, поиском
```

```cmd
# Включить/выключить USN журнал:
fsutil usn createjournal m=1000 a=100 C:
fsutil usn queryjournal C:
```

---

## 4. ZFS (Oracle/OpenZFS)

ZFS — наиболее технически совершенная файловая система, созданная Sun Microsystems.

### 4.1 Copy-on-Write (CoW)

ZFS **никогда не перезаписывает** существующие данные. Любая запись:
1. Записывает новые данные в новое место
2. Обновляет метаданные (в новом месте)
3. Атомарно переключает корень дерева

```
До записи:     [Root A] → [Block B] → [Data 1]
               Обновление Data 1:
               [Root A'] → [Block B'] → [Data 2]  (новые записи)
                                       [Data 1]   (старые блоки — для snapshots!)
После commit:  [Root A'] — активный
               [Root A]  — может использоваться снапшотами или быть освобождён
```

**Последствия CoW:**
- **Атомарность:** нет journal нужен — незавершённая запись просто не переключает корень
- **Снапшоты** бесплатны: просто держать ссылку на старый корень
- **Нет defrагментации** — записи всегда последовательны (но нужна периодическая переорганизация)

### 4.2 Снапшоты и клоны

```bash
# Создать снапшот (мгновенно!):
zfs snapshot pool/dataset@snapshot_name

# Список снапшотов:
zfs list -t snapshot pool/dataset

# Откат к снапшоту:
zfs rollback pool/dataset@snapshot_name

# Клон (writable snapshot — CoW от снапшота):
zfs clone pool/dataset@snapshot_name pool/dataset_clone

# Пространство, занятое снапшотами:
zfs list -o space pool/dataset
# NAME             AVAIL  USED  USEDSNAP  USEDDS  ...
# pool/dataset     100G   20G    5G        15G    ...
```

### 4.3 Checksums и самовосстановление

ZFS вычисляет контрольную сумму для **каждого** блока данных (и метаданных). При чтении — проверяет. Обнаружение тихой порчи (silent data corruption):

```bash
# Scrub — проверить весь пул на наличие ошибок:
zpool scrub mypool

# Статус после scrub:
zpool status
#   pool: mypool
#  state: ONLINE
# status: Some supported features are not enabled on the pool.
#   scan: scrub repaired 0B in 00:02:34 with 0 errors on Thu May  8 12:34:56 2025
# config:
#   NAME        STATE     READ WRITE CKSUM
#   mypool      ONLINE       0     0     0
#     sda       ONLINE       0     0     0
#     sdb       ONLINE       0     0     0
```

При обнаружении ошибки и наличии зеркала/RAIDZ — ZFS автоматически восстанавливает данные из рабочей копии.

### 4.4 RAIDZ

ZFS реализует аналог RAID прямо в файловой системе:

| RAIDZ | Аналог | Устойчивость | Overhead |
|-------|--------|-------------|---------|
| RAIDZ1 | RAID-5 | 1 диск | 1 диск/группа |
| RAIDZ2 | RAID-6 | 2 диска | 2 диска/группа |
| RAIDZ3 | — | 3 диска | 3 диска/группа |
| Mirror | RAID-1 | N-1 диска | N× overhead |

```bash
# Создать пул с RAIDZ2 (6 дисков, терпит 2 отказа):
zpool create mypool raidz2 sda sdb sdc sdd sde sdf

# Добавить зеркалированный кеш (ZIL — ZFS Intent Log):
zpool add mypool log mirror sda1 sdb1

# Добавить кеш для чтения (L2ARC):
zpool add mypool cache sdc1
```

### 4.5 Сжатие и дедупликация

```bash
# Включить сжатие lz4 (очень быстрое):
zfs set compression=lz4 pool/dataset

# Включить zstd (лучшее сжатие, чуть медленнее):
zfs set compression=zstd pool/dataset

# Статистика сжатия:
zfs get compressratio pool/dataset
# pool/dataset  compressratio  2.34x  local

# Дедупликация (требует МНОГО RAM: ~5 GB на 1 TB):
zfs set dedup=on pool/dataset
zpool status -D  # статистика дедупликации
```

---

## 5. APFS (Apple)

### 5.1 Особенности APFS

APFS (Apple File System) разработан Apple для macOS/iOS (2017):

**CoW + Snapshots:** как ZFS — снапшоты бесплатны, Time Machine использует их.

**Cloning файлов:** `cp` в APFS — мгновенная операция! Создаётся CoW-клон, реальное копирование данных происходит только при изменении:

```bash
# Мгновенное клонирование большого файла:
cp --reflink=auto large_file.iso copy.iso  # на APFS

# На Linux btrfs (аналог):
cp --reflink=always source.txt dest.txt
```

**APFS Volumes:** несколько томов в одном контейнере, разделяющих пространство:

```
APFS Container (весь раздел 500 GB)
├── APFS Volume: "Macintosh HD" (System) — read-only
├── APFS Volume: "Macintosh HD - Data" — writable
├── APFS Volume: "Preboot" — загрузчик
├── APFS Volume: "Recovery" — восстановление
└── APFS Volume: "VM" — swap файл
```

---

## 6. Btrfs (Linux)

Btrfs (B-tree File System) — попытка создать «ZFS для Linux»:

```bash
# Создать btrfs:
mkfs.btrfs -L mydata /dev/sda

# Снапшоты:
btrfs subvolume snapshot /data /data_snap

# Сжатие:
mount -o compress=zstd /dev/sda /data

# RAID:
mkfs.btrfs -m raid1 -d raid1 /dev/sda /dev/sdb  # RAID-1 для meta и data

# Scrub:
btrfs scrub start /data

# Статус:
btrfs filesystem df /data
btrfs filesystem usage /data
```

---

## 7. FUSE — Filesystem in User Space

FUSE позволяет писать ФС в user space:

```python
# Python FUSE: минимальная in-memory filesystem
from fuse import FUSE, FuseOSError, Operations
import errno
import os

class MemoryFS(Operations):
    def __init__(self):
        self.files = {}
        self.data = {}
        self.fd = 0
        now = time()
        self.files['/'] = {
            'st_mode': (stat.S_IFDIR | 0o755),
            'st_nlink': 2,
            'st_size': 0,
            'st_atime': now, 'st_mtime': now, 'st_ctime': now,
        }
    
    def getattr(self, path, fh=None):
        if path not in self.files:
            raise FuseOSError(errno.ENOENT)
        return self.files[path]
    
    def read(self, path, length, offset, fh):
        return self.data[path][offset:offset+length]
    
    def write(self, path, data, offset, fh):
        old = self.data.get(path, b'')
        self.data[path] = old[:offset] + data + old[offset+len(data):]
        self.files[path]['st_size'] = len(self.data[path])
        return len(data)

if __name__ == '__main__':
    FUSE(MemoryFS(), '/mnt/memfs', foreground=True)
```

Популярные FUSE ФС: `sshfs` (удалённые файлы через SSH), `ntfs-3g` (NTFS на Linux), `s3fs` (Amazon S3 как ФС), `encfs` (шифрованная ФС).

---

## 8. Сравнение файловых систем

| Характеристика | ext4 | NTFS | APFS | ZFS | Btrfs |
|---------------|------|------|------|-----|-------|
| ОС | Linux | Windows | macOS/iOS | Linux, FreeBSD | Linux |
| CoW | Нет | Нет | Да | Да | Да |
| Снапшоты | Нет (LVM) | VSS | Да | Да | Да |
| Журналирование | Да | Да | Да | Нет (CoW) | Да |
| Checksums | Нет | Нет | Да (метаданные) | Да (всё) | Да |
| RAID | Нет (mdadm) | Spaces | APFS RAID | Да | Да |
| Сжатие | Нет | Нет | Нет | Да | Да |
| Дедупликация | Нет | ReFS | Нет | Да | Нет |
| Макс. размер тома | 1 EB | 16 EB | 8 EB | 256 ZB | 16 EB |
| Макс. размер файла | 16 TB | 16 TB | 8 EB | 16 EB | 16 EB |
| Зрелость | Высокая | Высокая | Средняя | Высокая | Средняя |

---

## Заключение

Выбор файловой системы — важное архитектурное решение:

- **ext4** — надёжная рабочая лошадка для Linux. Хороша для большинства задач, проста, стабильна.
- **NTFS** — стандарт Windows, хорошо интегрирован с Windows Security, поддерживает ACL.
- **APFS** — оптимизирован для SSD и Flash (iOS устройства), отличные снапшоты.
- **ZFS** — для серверов где критичны целостность данных, снапшоты, масштабируемость. Требует больше RAM.
- **Btrfs** — перспективная Linux ФС, но историческая нестабильность RAID-5/6 вызывала опасения.

---

## Литература и источники

1. Wikipedia. *ext4*. — https://en.wikipedia.org/wiki/Ext4

2. Wikipedia. *NTFS*. — https://en.wikipedia.org/wiki/NTFS

3. Wikipedia. *ZFS*. — https://en.wikipedia.org/wiki/ZFS

4. Apple. *Apple File System Reference*. — https://developer.apple.com/support/downloads/Apple-File-System-Reference.pdf

5. OpenZFS Documentation. — https://openzfs.github.io/openzfs-docs/

6. Linux Kernel Documentation. *The ext4 filesystem*. — https://www.kernel.org/doc/html/latest/filesystems/ext4/

7. Bovet, D. P., & Cesati, M. (2005). *Understanding the Linux Kernel* (3rd ed.). — Глава 18: VFS.

8. Wikipedia. *FUSE (computing)*. — https://en.wikipedia.org/wiki/Filesystem_in_Userspace

9. Oracle. *ZFS Administration Guide*. — https://docs.oracle.com/cd/E26505_01/html/E37384/

10. Btrfs Wiki. — https://btrfs.wiki.kernel.org/
