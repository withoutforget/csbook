# BIOS/UEFI, Bootloader, Kernel Boot

## Введение

Вы нажимаете кнопку включения компьютера. Экран черный. Проходит секунда, другая — и появляется логин. Что произошло за это время? Оказывается, между нажатием кнопки питания и готовностью ОС к работе происходит целая цепочка событий, каждое из которых критически важно: POST, инициализация чипсета, загрузчик bootloader, распаковка ядра, инициализация подсистем, запуск init. Неверный шаг на любом из этапов — и система не загрузится.

Процесс загрузки — это один из немногих моментов, когда граница между аппаратурой и программным обеспечением особенно размыта. BIOS/UEFI — программа, «вшитая» в чип на материнской плате. Bootloader — специальная программа, которая загружает ядро ОС. Они работают в специальных режимах процессора (Real Mode, Protected Mode, Long Mode), используют прямой доступ к оборудованию и должны работать без поддержки ОС — ведь её ещё нет.

---

## 1. Legacy BIOS

### 1.1 История и принцип

BIOS (Basic Input/Output System) появился в CP/M (1975) и был адаптирован для IBM PC (1981). Фактически это была первая «прошивка» для персональных компьютеров. До появления UEFI (2000-е) BIOS правил безраздельно более 20 лет.

**POST (Power-On Self-Test):**

При включении питания CPU начинает выполнение с фиксированного адреса: `0xFFFF0` (16MB - 16 байт в x86 16-bit real mode, в реальности маппируется на ROM BIOS). Здесь находится `jmp` инструкция на начало POST.

POST проверяет:
1. CPU и кеш (базовые тесты регистров)
2. Чипсет и шины
3. RAM (тест памяти — «считаем, пишем, читаем»)
4. Видеокарту (инициализируется первой — для вывода ошибок)
5. Периферию: клавиатура, диски, USB

Ошибки POST сигнализируются POST-кодами (числа, выводимые на специальный порт 0x80), или звуковыми сигналами (beep codes), или сообщениями на экране.

### 1.2 Инициализация оборудования

После POST, BIOS инициализирует устройства через «Option ROM»:
- Каждое устройство (например, SCSI-контроллер) может иметь ROM с кодом инициализации
- BIOS сканирует PCI шину и запускает Option ROM для каждого найденного устройства
- Графическая карта → инициализируется первой, выводит логотип
- Сетевая карта → может предложить загрузку по сети (PXE boot)

### 1.3 MBR и первый шаг загрузки

После инициализации BIOS должен передать управление операционной системе. Для этого он читает **первый сектор** загрузочного диска — **MBR (Master Boot Record)**, ровно 512 байт:

```
MBR Layout (512 байт):
+--------+-----+-------------------------------------------------------+
| Offset | Len | Содержимое                                            |
+--------+-----+-------------------------------------------------------+
|      0 | 446 | Bootloader Code (первая стадия)                       |
|    446 |  64 | Partition Table (4 записи × 16 байт каждая)           |
|    510 |   2 | Boot Signature: 0x55 0xAA (magic bytes)               |
+--------+-----+-------------------------------------------------------+
```

**Partition Table Entry (16 байт):**
```c
struct partition_entry {
    uint8_t  status;          // 0x80 = bootable, 0x00 = not
    uint8_t  chs_begin[3];    // CHS начала (legacy)
    uint8_t  type;            // тип ФС: 0x83 = Linux, 0x07 = NTFS, 0x0B = FAT32
    uint8_t  chs_end[3];      // CHS конца (legacy)
    uint32_t lba_begin;       // LBA адрес начала (используется сейчас)
    uint32_t sector_count;    // Число секторов
};
```

BIOS загружает MBR по адресу `0x7C00`, проверяет сигнатуру `0x55 0xAA`, и передаёт управление (jmp 0x7C00).

**Ограничения MBR:**
- Таблица из 4 разделов
- Максимальный размер диска: 2 ТБ (32-bit LBA, 512-байтные сектора)
- Нет подписей, нет верификации — любой код

### 1.4 GRUB: Stagеd загрузка

446 байт — слишком мало для полноценного bootloader. GRUB (GRand Unified Bootloader) решает это через многоступенчатую загрузку:

**Stage 1 (446 байт в MBR):**
- Находит активный раздел или Stage 1.5 в gap между MBR и первым разделом
- Загружает Stage 1.5 или Stage 2

**Stage 1.5 (32 КБ, в disk gap):**
- Знает о нескольких файловых системах (ext2/3/4, FAT, Btrfs...)
- Загружает Stage 2 уже как файл с файловой системы

**Stage 2 (несколько МБ, на ФС):**
- Полноценный GRUB: меню выбора ОС, конфигурация, командная строка
- Загружает ядро Linux (`vmlinuz-*`) и initrd
- Передаёт параметры ядру

```bash
# Структура GRUB:
ls /boot/grub/
# grub.cfg   i386-pc/  fonts/  locale/  ...

# Основной конфигурационный файл:
cat /boot/grub/grub.cfg | head -50

# Типичная запись menuentry:
# menuentry 'Ubuntu 22.04 LTS' --class ubuntu {
#   linux  /vmlinuz-6.1.0 root=/dev/sda1 quiet splash
#   initrd /initrd.img-6.1.0
# }
```

---

## 2. UEFI — Unified Extensible Firmware Interface

### 2.1 Почему UEFI пришёл на смену BIOS

К 2000-м годам ограничения BIOS стали критическими:
- 2 ТБ лимит дисков (серверы нужна большая ёмкость)
- 4 раздела MBR
- 16-bit real mode — нет 64-bit кода в firmware
- Нет безопасности загрузки (Secure Boot)
- Slow POST (проверка COM-портов, флоппи-дисков в 2010?)
- Плохой API: int 13h, int 10h — устаревшие прерывания

Intel начал разрабатывать EFI (Extensible Firmware Interface) в 1998 для Itanium. В 2005 был создан альянс UEFI (Intel, AMD, Microsoft, Apple, ARM...), стандарт публично доступен.

### 2.2 UEFI Boot Process

```
Power On
    │
    ▼
Security Phase (SEC)
    │  Инициализация CPU, кеша как RAM (CAR: Cache-As-RAM)
    │  Проверка подписи PEI firmware
    ▼
Pre-EFI Initialization (PEI)
    │  Инициализация RAM (memory training — подбор параметров DDR)
    │  Инициализация чипсета
    │  Запуск DXE IPL (Image Program Loader)
    ▼
Driver eXecution Environment (DXE)
    │  Инициализация всего оборудования через EFI drivers
    │  Строится EFI System Table, Boot Services, Runtime Services
    │  Загружаются опциональные ROM (Option ROMs)
    ▼
Boot Device Selection (BDS)
    │  Проверяет NVRAM список загрузочных устройств (Boot0001, Boot0002...)
    │  Для каждого устройства: ищет EFI partition, запускает EFI приложение
    │  или Compatibility Support Module (CSM) для legacy BIOS загрузки
    ▼
Runtime Services
    │  После передачи управления ОС, часть UEFI остаётся (Runtime Services)
    │  Доступны для ОС: GetTime/SetTime, GetVariable/SetVariable,
    │  UpdateCapsule (firmware update), ResetSystem
    ▼
ОС загружена
```

### 2.3 GPT — GUID Partition Table

UEFI требует GPT вместо MBR:

```
GPT Layout:
+-------------+------+------------------------------------------+
| LBA 0       |  512 | Protective MBR (для backward compat)     |
+-------------+------+------------------------------------------+
| LBA 1       |  512 | Primary GPT Header                       |
+-------------+------+------------------------------------------+
| LBA 2-33    | 16KB | Partition Entries (128 записей × 128 байт)|
+-------------+------+------------------------------------------+
| LBA 34...   |  ... | Partition Data (разделы)                 |
+-------------+------+------------------------------------------+
| LBA -33..-2 | 16KB | Backup Partition Entries                 |
+-------------+------+------------------------------------------+
| LBA -1      |  512 | Backup GPT Header                        |
+-------------+------+------------------------------------------+
```

**GPT Header:**
```c
struct gpt_header {
    char     signature[8];       // "EFI PART"
    uint32_t revision;           // 0x00010000
    uint32_t header_size;        // 92 байта
    uint32_t header_crc32;       // CRC32 заголовка
    uint32_t reserved;
    uint64_t my_lba;             // LBA этого заголовка (1)
    uint64_t alternate_lba;      // LBA backup header (последний LBA)
    uint64_t first_usable_lba;   // Начало доступных разделов (34)
    uint64_t last_usable_lba;    // Конец доступных разделов
    uint8_t  disk_guid[16];      // GUID диска (уникальный)
    uint64_t partition_entry_lba;// LBA таблицы разделов (2)
    uint32_t num_partitions;     // Число записей (128)
    uint32_t partition_entry_size; // 128 байт
    uint32_t partition_crc32;    // CRC32 таблицы разделов
};
```

**GPT Partition Entry (128 байт):**
```c
struct gpt_partition {
    uint8_t  type_guid[16];    // Тип раздела (EFI System = C12A7328-...)
    uint8_t  partition_guid[16]; // Уникальный GUID раздела
    uint64_t first_lba;
    uint64_t last_lba;
    uint64_t attributes;       // bit 2 = Required Partition
    uint16_t name[36];         // UTF-16 имя
};
```

Важные Type GUID:
- `C12A7328-F81F-11D2-BA4B-00A0C93EC93B` — EFI System Partition (ESP)
- `0FC63DAF-8483-4772-8E79-3D69D8477DE4` — Linux filesystem data
- `E3C9E316-0B5C-4DB8-817D-F92DF00215AE` — Microsoft Reserved
- `EBD0A0A2-B9E5-4433-87C0-68B6B72699C7` — Microsoft Basic Data

**Преимущества GPT:**
- 128 разделов (vs 4 в MBR)
- Диски до 9.4 ZB (18 EB с 512-байтными секторами)
- Backup GPT header и таблица в конце диска
- CRC32 проверка целостности
- GUID для идентификации

### 2.4 EFI System Partition (ESP)

Специальный раздел в формате FAT32 — общий для всех ОС на системе:

```
ESP структура:
/EFI/
  /BOOT/
    BOOTX64.EFI   ← fallback bootloader (загружается если нет записей в NVRAM)
  /ubuntu/
    grubx64.efi   ← GRUB для Ubuntu
    shimx64.efi   ← shim для Secure Boot
  /Microsoft/
    Boot/
      bootmgfw.efi ← Windows Boot Manager
  /apple/
    ...
```

Размер ESP: обычно 100-512 МБ. Точка монтирования в Linux: `/boot/efi`.

### 2.5 UEFI Shell и приложения

UEFI поддерживает полноценную среду выполнения EFI-приложений (написанных на C):

```c
// Простое Hello World UEFI приложение (EDK2):
#include <Uefi.h>
#include <Library/UefiApplicationEntryPoint.h>
#include <Library/UefiLib.h>

EFI_STATUS EFIAPI UefiMain(
    IN EFI_HANDLE        ImageHandle,
    IN EFI_SYSTEM_TABLE *SystemTable
) {
    Print(L"Hello, UEFI World!\n");
    
    // Boot Services:
    SystemTable->BootServices->Stall(3000000);  // пауза 3 секунды
    
    return EFI_SUCCESS;
}
```

### 2.6 UEFI Variables (NVRAM)

UEFI хранит конфигурацию в NVRAM (энергонезависимая память):

```bash
# Linux: просмотр и изменение UEFI переменных:
efibootmgr -v   # список загрузочных записей

# Вывод:
# BootCurrent: 0002
# Timeout: 0 seconds
# BootOrder: 0002,0000,0001
# Boot0000* Windows Boot Manager  HD(2,GPT,...)File(\EFI\MICROSOFT\BOOT\BOOTMGFW.EFI)
# Boot0001* UEFI Firmware         ...
# Boot0002* ubuntu                HD(1,GPT,...)File(\EFI\ubuntu\shimx64.efi)

# Добавить запись:
efibootmgr --create --disk /dev/sda --part 1 --loader /EFI/ubuntu/grubx64.efi \
           --label "Ubuntu" --unicode

# Изменить порядок загрузки:
efibootmgr --bootorder 0002,0000

# Прямой доступ к переменным:
ls /sys/firmware/efi/efivars/
cat /sys/firmware/efi/efivars/BootOrder-*
```

---

## 3. Secure Boot

### 3.1 Принцип

Secure Boot — механизм UEFI, гарантирующий что загружается только подписанный bootloader. Предотвращает руткиты, замену bootloader вредоносным кодом.

```
UEFI → проверяет подпись EFI приложения → если OK → загружает
                                         → если не OK → отказывает
```

**Ключи Secure Boot:**
- **PK (Platform Key):** мастер-ключ производителя OEM (один)
- **KEK (Key Exchange Key):** ключи обновления баз данных (Microsoft, OEM)
- **db (Authorized Signatures Database):** хеши/сертификаты разрешённых загрузчиков
- **dbx (Forbidden Signatures Database):** отозванные сертификаты

### 3.2 Shim — мост для Linux

Microsoft подписала «shim» — маленькую EFI программу, которая содержит сертификат дистрибутива Linux и умеет проверять подписи GRUB:

```
UEFI → shimx64.efi (подписан Microsoft) → проверяет grubx64.efi (подписан Canonical/Fedora/...)
→ GRUB → проверяет vmlinuz (подписан дистрибутивом) → ядро загружается
```

### 3.3 Secure Boot и Linux

```bash
# Проверить статус Secure Boot:
mokutil --sb-state
# SecureBoot enabled

# Проверить, подписан ли загрузчик:
sbverify --cert /usr/share/ca-certificates/mozilla/Microsoft_Root_Certificate_Authority_2011.crt \
         /boot/efi/EFI/ubuntu/shimx64.efi

# Добавить свой ключ (MOK = Machine Owner Key):
mokutil --import my_certificate.der
# При перезагрузке появится запрос подтверждения на экране UEFI
```

---

## 4. GRUB как UEFI Bootloader

### 4.1 GRUB в UEFI режиме

В UEFI режиме GRUB устанавливается как EFI-приложение в ESP:

```
/boot/efi/EFI/ubuntu/
  grubx64.efi   ← основной GRUB (64-bit x86)
  shimx64.efi   ← shim (для Secure Boot)
  grub.cfg      ← конфигурация

/boot/
  grub/
    grub.cfg    ← основной конфиг, symlink или copy
  vmlinuz-6.1.0-*    ← сжатое ядро
  initrd.img-6.1.0-* ← initial RAM disk
```

### 4.2 GRUB конфигурация

```bash
# /etc/default/grub:
GRUB_DEFAULT=0
GRUB_TIMEOUT=5
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
GRUB_CMDLINE_LINUX=""

# Параметры ядра (примеры):
# root=/dev/sda1           ← корневой раздел
# ro                        ← смонтировать root read-only поначалу
# quiet splash              ← меньше вывода, splash screen
# nomodeset                 ← без KMS (проблемы с GPU)
# mem=4G                    ← ограничить память
# init=/bin/sh              ← аварийная оболочка вместо init
# acpi=off                  ← выключить ACPI
# iommu=on                  ← включить IOMMU (для VT-d/AMD-Vi)
# selinux=0                 ← выключить SELinux

# Regenerate grub.cfg:
sudo update-grub
# или:
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

---

## 5. Загрузка ядра Linux

### 5.1 Что такое vmlinuz

```bash
file /boot/vmlinuz-$(uname -r)
# /boot/vmlinuz-6.1.0-...: Linux kernel x86 boot executable bzImage,
# version 6.1.0-..., RO-rootFS, swap_dev 0x12, Normal VGA

# bzImage = big zImage: ядро сжатое (gzip/lzma/xz/zstd) + самораспаковщик
# Структура:
# - Real-mode kernel (first 512+ bytes) — устаревший setup code
# - Protected-mode setup.bin
# - Compressed kernel.gz/xz/zstd
```

### 5.2 Передача управления ядру из GRUB

```
GRUB:
1. Загружает vmlinuz в память (обычно 0x100000)
2. Загружает initrd.img (initial ramdisk)
3. Читает kernel command line (из grub.cfg)
4. Заполняет boot_params структуру:
   struct boot_params {
       uint8_t  screen_info[64];
       uint8_t  apm_bios_info[20];
       uint8_t  tboot_addr[8];
       uint8_t  ist_info[16];
       ...
       uint64_t acpi_rsdp_addr;  // адрес ACPI таблиц
       struct setup_header hdr;  // параметры ядра
       uint32_t edd_mbr_sig_buffer[16];
       ...
   };
5. Переходит на точку входа ядра:
   jmp kernel_entry   // arch/x86/boot/compressed/head_64.S
```

### 5.3 Стадии запуска ядра

```
vmlinuz Entry (arch/x86/boot/compressed/head_64.S):
│
├─ Verifica magic (LINUX_MAGIC_SIGNATURE)
├─ Decompress kernel (extract_kernel → zstd/lzma/gzip)
│
▼
arch/x86/kernel/head_64.S (распакованное ядро):
│
├─ Инициализация сегментов, GDT, IDT
├─ Переключение в Long Mode (64-bit)
├─ Установка page tables (identity mapping)
├─ Вызов start_kernel()
│
▼
init/main.c: start_kernel():
│
├─ lockdep_init()          — инициализация lock dependency tracking
├─ set_task_stack_end_magic()
├─ smp_setup_processor_id()
├─ debug_objects_early_init()
├─ boot_init_stack_canary()
├─ cgroup_init_early()
├─ local_irq_disable()     — выключаем прерывания
├─ early_boot_irqs_disabled = true
├─ boot_cpu_init()         — текущий CPU онлайн
├─ page_address_init()
├─ setup_arch(&command_line) — архитектурная инициализация, memory map
│   ├─ parse_early_param()
│   ├─ early_ioremap_init()
│   ├─ e820__memory_setup() — карта физической памяти
│   ├─ acpi_boot_table_init()
│   └─ ...
├─ mm_init()               — менеджер памяти
├─ sched_init()            — планировщик
├─ preempt_disable()
├─ idr_init_cache()
├─ rcu_init()              — Read-Copy-Update
├─ trace_init()
├─ radix_tree_init()
├─ early_irq_init()
├─ init_IRQ()
├─ tick_init()
├─ rcu_init_nohz()
├─ init_timers()
├─ hrtimers_init()
├─ softirq_init()
├─ timekeeping_init()
├─ time_init()
├─ perf_event_init()
├─ profile_init()
├─ call_function_init()
├─ local_irq_enable()      — включаем прерывания
├─ kmem_cache_init_late()
├─ console_init()          — ← теперь есть консоль!
├─ lockdep_init()
├─ locking_selftest()
├─ mem_encrypt_init()
├─ kmemleak_init()
├─ setup_per_cpu_pageset()
├─ numa_policy_init()
├─ late_time_init()
├─ calibrate_delay()       — BogoMIPS
├─ pid_idr_init()
├─ anon_vma_init()
├─ thread_stack_cache_init()
├─ cred_init()
├─ fork_init()             — fork infrastructure
├─ proc_caches_init()
├─ uts_ns_init()
├─ key_init()
├─ security_init()         — LSM (SELinux/AppArmor/etc)
├─ dbg_late_init()
├─ net_ns_init()
├─ vfs_caches_init()       — VFS (Virtual File System)
├─ pagecache_init()
├─ signals_init()
├─ seq_file_init()
├─ proc_root_init()
├─ nsfs_init()
├─ cpuset_init()
├─ cgroup_init()
├─ taskstats_init_early()
├─ delayacct_init()
├─ kernel_debug_init()
└─ rest_init()
    ├─ kernel_thread(kernel_init) → PID 1 (init)
    ├─ kernel_thread(kthreadd)    → PID 2 (kthreadd - родитель всех kthread)
    └─ cpu_startup_entry(CPUHP_ONLINE) → idle thread (PID 0)
```

### 5.4 initramfs (Initial RAM Filesystem)

```bash
# initrd — временная корневая файловая система в RAM
# Нужна потому что ядро не знает заранее: SCSI, NVMe, LVM, LUKS, RAID...

# Формат: cpio архив + сжатие (gzip/xz/zstd)
# Просмотр содержимого:
mkdir /tmp/initrd-extract
cd /tmp/initrd-extract
zcat /boot/initrd.img-$(uname -r) | cpio -id

ls
# bin/  conf/  etc/  init  lib/  lib64/  run/  sbin/  scripts/  usr/

# Ключевой файл: /init (обычно скрипт busybox)
head -30 init
# #!/bin/sh
# # ...
# # Mount /proc, /sys, /dev
# # Load kernel modules (SCSI drivers, filesystem modules)
# # Find and mount real root
# # switch_root /root /sbin/init
```

**Процесс initramfs:**
1. Ядро распаковывает cpio архив в tmpfs
2. Выполняет `/init` скрипт
3. Скрипт: монтирует /proc, /sys, /dev/pts
4. Загружает модули ядра (cryptsetup, lvm2, mdadm, virtio...)
5. Находит реальный корневой раздел (возможно расшифровывает LUKS)
6. Монтирует реальный /root
7. `switch_root /real_root /sbin/init` — меняет корень и запускает init

### 5.5 kernel_init → /sbin/init

```c
// Ядро пытается запустить init:
static const char * const argv_init[] = { "init", NULL, };
static const char * const envp_init[] = { "HOME=/", "TERM=linux", NULL, };

static int __ref kernel_init(void *unused) {
    // ...
    if (execute_command) {
        // kernel command line: init=/path/to/init
        ret = run_init_process(execute_command);
    }
    
    // По умолчанию пробуем несколько мест:
    if (!try_to_run_init_process("/sbin/init") ||
        !try_to_run_init_process("/etc/init") ||
        !try_to_run_init_process("/bin/init") ||
        !try_to_run_init_process("/bin/sh"))
        return 0;
    
    panic("No working init found. Try passing init= option to kernel.");
}
```

На современных системах `/sbin/init` → systemd (или SysVinit, OpenRC, runit...).

---

## 6. Systemd — современный init

```bash
# PID 1 = systemd
ps 1
# PID TTY      STAT   TIME COMMAND
#   1 ?        Ss     2:17 /usr/lib/systemd/systemd --system --deserialize ...

# Просмотр boot log:
journalctl -b --no-pager | head -50

# Время загрузки по стадиям:
systemd-analyze
# Startup finished in:
# firmware: 3.071s
# loader:   1.020s (GRUB)
# kernel:   1.854s
# userspace: 8.432s
# Total: 14.377s

systemd-analyze blame   # какой сервис сколько занял
systemd-analyze plot > boot.svg   # SVG граф загрузки
```

---

## 7. Диагностика проблем загрузки

### 7.1 GRUB Emergency Shell

```
# Если GRUB не может найти конфиг:
error: unknown filesystem
Entering rescue mode...
grub rescue> 

# Ручная загрузка:
grub rescue> ls                    # показать найденные разделы
grub rescue> ls (hd0,gpt2)/        # содержимое раздела
grub rescue> set root=(hd0,gpt2)
grub rescue> linux /vmlinuz root=/dev/sda2
grub rescue> initrd /initrd.img
grub rescue> boot
```

### 7.2 Kernel panic

```
# Типичные kernel panic:
# "VFS: Unable to mount root fs on unknown-block(0,0)"
# → неверный параметр root=, драйвер ФС не загружен (initrd проблема)

# "Kernel panic - not syncing: No init found"
# → /sbin/init повреждён или неверный init=

# Загрузка с параметрами отладки:
# В GRUB меню: нажать 'e', добавить параметры:
linux /vmlinuz root=/dev/sda1 ro systemd.log_level=debug systemd.log_target=console
```

---

## Заключение

Путь от нажатия кнопки питания до логина занимает 10-30 секунд, но включает сотни шагов: инициализация CPU, тест памяти, инициализация UEFI/BIOS, загрузка bootloader, декомпрессия ядра, инициализация десятков подсистем, монтирование initramfs, переход к реальному корню, запуск userspace.

Каждый этап — потенциальная точка отказа. Понимание процесса загрузки позволяет:
- Диагностировать и исправлять незагружающиеся системы
- Настраивать Secure Boot для безопасных систем
- Оптимизировать время загрузки (systemd-analyze)
- Добавлять параметры ядра для специфичных требований
- Понимать архитектуру initramfs и загрузчика

---

## Литература и источники

1. UEFI Forum. *UEFI Specification 2.10*. — https://uefi.org/specs/UEFI/2.10/

2. Wikipedia. *BIOS*. — https://en.wikipedia.org/wiki/BIOS

3. Wikipedia. *UEFI*. — https://en.wikipedia.org/wiki/UEFI

4. Wikipedia. *GUID Partition Table*. — https://en.wikipedia.org/wiki/GUID_Partition_Table

5. GNU GRUB Manual. — https://www.gnu.org/software/grub/manual/grub/grub.html

6. Linux Kernel Documentation. *The Linux/x86 Boot Protocol*. — https://www.kernel.org/doc/html/latest/x86/boot.html

7. Linux Kernel Documentation. *initramfs/initrd*. — https://www.kernel.org/doc/html/latest/filesystems/ramfs-rootfs-initramfs.html

8. OSDev Wiki. *UEFI*. — https://wiki.osdev.org/UEFI

9. OSDev Wiki. *Master Boot Record*. — https://wiki.osdev.org/MBR_(x86)

10. systemd documentation. *Boot process*. — https://www.freedesktop.org/software/systemd/man/bootup.html
