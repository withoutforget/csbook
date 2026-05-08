# Драйверы и модули ядра

## Введение

Когда вы подключаете USB-флешку, она автоматически появляется в системе. Принтер работает без перезагрузки. Новая видеокарта отображается после установки драйвера. Всё это происходит благодаря **модулям ядра** (kernel modules) — кусочкам кода, которые можно загружать и выгружать из работающего ядра, не перезагружая систему.

Ядро Linux — монолитное: весь код работает в одном адресном пространстве, в привилегированном режиме Ring 0. Добавить поддержку нового устройства можно двумя способами: скомпилировать её прямо в ядро (`=y`) или оформить как загружаемый модуль (`=m`). Второй подход значительно гибче: Ubuntu не нужно включать в ядро драйверы всех тысяч устройств — нужные модули загружаются автоматически при обнаружении устройства.

Написание модулей ядра — совершенно особый вид программирования. Нет стандартной библиотеки C, нет malloc (есть kmalloc), нет printf (есть printk), ошибка приводит к kernel panic, а debugging требует специальных инструментов. Но взамен — полный контроль над аппаратурой и возможность расширять ядро практически неограниченно.

---

## 1. Kernel Space vs User Space

### 1.1 Два мира

```
+─────────────────────────────────────────────────────────────────+
│                    User Space                                    │
│  Process A     Process B     Process C                          │
│  Virtual AS    Virtual AS    Virtual AS                         │
│  (0..3GB)      (0..3GB)      (0..3GB)                          │
│                                                                  │
│  glibc / libpthread / libm...                                   │
│                                                                  │
│         System Call Interface (int 0x80 / syscall)              │
╠═════════════════════════════════════════════════════════════════╣
│                    Kernel Space                                  │
│  VFS  │  Network  │  Memory Manager  │  Scheduler               │
│       │  Stack    │                  │                           │
│  Block │ Socket   │  Page Allocator  │  IRQ Handler             │
│  Layer │ Buffer   │                  │                           │
│                                                                  │
│  Drivers:  USB │ PCI │ Block │ Network │ Character               │
│                                                                  │
│  Architecture (x86/ARM...): HAL                                  │
│                                                                  │
│  Hardware: CPU │ Memory │ PCI Bus │ I/O Ports │ MMIO             │
+─────────────────────────────────────────────────────────────────+
```

**Kernel Space:**
- Ring 0 (x86), EL1/EL3 (ARM)
- Прямой доступ к аппаратуре
- Разделяемое адресное пространство (все ядерные потоки видят одну память)
- Ошибка → kernel panic (нет изоляции от других процессов)
- Нет preemption по умолчанию (в обычном ядре Linux критические секции без вытеснения)

**User Space:**
- Ring 3 / EL0
- Изолированное виртуальное адресное пространство
- Ошибка → SIGSEGV только в данном процессе
- Доступ к аппаратуре — только через системные вызовы

### 1.2 Зачем User Space драйверы?

Не все драйверы должны быть в ядре. Есть альтернативы:

**UIO (Userspace I/O):**
- Ядро предоставляет минимальный framework
- MMIO регионы устройства маппируются в user space
- Обработка прерываний через `/dev/uio0`
- Применение: DPDK (сетевые карты для high performance networking)

```c
// UIO пример:
int fd = open("/dev/uio0", O_RDWR);
void *mmio = mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);
// Теперь можно работать с MMIO регистрами устройства напрямую
```

**FUSE (Filesystem in Userspace):**
- Файловые системы в user space
- libfuse предоставляет API
- Медленнее kernel FS, но безопаснее и проще разрабатывать
- Примеры: sshfs, ntfs-3g, s3fs, encfs

**VFIO (Virtual Function I/O):**
- Назначение PCIe устройства напрямую в VM (hardware passthrough)
- Используется в KVM/QEMU для GPU passthrough

| Характеристика | Kernel Module | UIO/VFIO | FUSE |
|----------------|---------------|----------|------|
| Производительность | Максимальная | Высокая | Средняя |
| Безопасность | Низкая (crash = panic) | Средняя | Высокая |
| Сложность | Высокая | Средняя | Низкая |
| Применение | Все типы устройств | HPC, NIC | ФС |

---

## 2. Hello World — первый модуль ядра

### 2.1 Минимальный модуль

```c
// hello.c — простейший модуль ядра Linux
#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Your Name");
MODULE_DESCRIPTION("A simple Hello World module");
MODULE_VERSION("1.0");

// Функция загрузки модуля (аналог main):
static int __init hello_init(void) {
    printk(KERN_INFO "hello: module loaded!\n");
    return 0;  // 0 = успех, отрицательное = ошибка
}

// Функция выгрузки:
static void __exit hello_exit(void) {
    printk(KERN_INFO "hello: module unloaded!\n");
}

module_init(hello_init);  // зарегистрировать hello_init как init function
module_exit(hello_exit);  // зарегистрировать hello_exit как exit function
```

### 2.2 Makefile для модуля

```makefile
# Makefile
obj-m += hello.o    # hello.o скомпилировать как модуль

# Путь к исходникам ядра:
KDIR := /lib/modules/$(shell uname -r)/build
PWD  := $(shell pwd)

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
```

### 2.3 Компиляция и загрузка

```bash
# Компиляция:
make
# Результат: hello.ko (kernel object)

# Информация о модуле:
modinfo hello.ko
# filename:       /path/hello.ko
# version:        1.0
# description:    A simple Hello World module
# author:         Your Name
# license:        GPL
# depends:
# vermagic:       6.1.0-21-amd64 SMP preempt mod_unload modversions

# Загрузка:
sudo insmod hello.ko

# Просмотр сообщений:
dmesg | tail -3
# [12345.678] hello: module loaded!

# Список загруженных модулей:
lsmod | grep hello
# hello   16384  0   ← имя, размер, число пользователей

# Выгрузка:
sudo rmmod hello
dmesg | tail -1
# [12350.123] hello: module unloaded!

# Постоянная установка (с автозагрузкой):
sudo cp hello.ko /lib/modules/$(uname -r)/extra/
sudo depmod -a
sudo modprobe hello     # загрузить с зависимостями
sudo modprobe -r hello  # выгрузить
```

### 2.4 Параметры модуля

```c
#include <linux/moduleparam.h>

static int num_instances = 1;
static char *device_name = "mydevice";

module_param(num_instances, int, 0644);
MODULE_PARM_DESC(num_instances, "Number of device instances");

module_param(device_name, charp, 0444);
MODULE_PARM_DESC(device_name, "Device name prefix");
```

```bash
# Загрузка с параметрами:
sudo insmod hello.ko num_instances=3 device_name="sensor"

# Просмотр параметров запущенного модуля:
cat /sys/module/hello/parameters/num_instances
# 3
```

---

## 3. Символьные устройства (Character Devices)

### 3.1 Устройства в Unix

В Unix всё — файл. Устройства представлены как файлы в `/dev`:

```bash
ls -la /dev/
# crw-rw---- 1 root dialout 4, 64 /dev/ttyS0     ← символьное устройство
# brw-rw---- 1 root disk    8,  0 /dev/sda        ← блочное устройство
# crw-rw-rw- 1 root root    1,  8 /dev/random     ← символьное
# crw------- 1 root root    5,  1 /dev/console

# Числа (major, minor):
# major = тип устройства (драйвер)
# minor = конкретное устройство данного типа
```

**Символьные устройства** (char devices): поток байт, произвольный доступ невозможен (последовательная передача). Пример: терминал, последовательный порт, /dev/random, /dev/null.

**Блочные устройства** (block devices): произвольный доступ блоками (512, 4096 байт). Пример: HDD, SSD, CD-ROM.

### 3.2 Модуль символьного устройства

```c
// chardev.c — полноценный символьный драйвер
#include <linux/init.h>
#include <linux/module.h>
#include <linux/fs.h>          // file_operations
#include <linux/uaccess.h>     // copy_to_user, copy_from_user
#include <linux/cdev.h>        // cdev API

MODULE_LICENSE("GPL");

#define DEVICE_NAME "chardev"
#define BUFFER_SIZE 1024

static int    major_number;
static char   device_buffer[BUFFER_SIZE];
static size_t buffer_pos = 0;
static struct class  *device_class  = NULL;
static struct device *device_dev    = NULL;
static struct cdev   char_dev;
static dev_t         dev_num;

// Обработчик open():
static int device_open(struct inode *inode, struct file *filp) {
    printk(KERN_INFO "chardev: opened\n");
    return 0;
}

// Обработчик release() (close):
static int device_release(struct inode *inode, struct file *filp) {
    printk(KERN_INFO "chardev: closed\n");
    return 0;
}

// Обработчик read():
static ssize_t device_read(struct file *filp, char __user *buf,
                           size_t count, loff_t *f_pos) {
    ssize_t bytes_read = 0;
    
    if (*f_pos >= buffer_pos)  // нет данных
        return 0;
    
    if (*f_pos + count > buffer_pos)
        count = buffer_pos - *f_pos;
    
    // ВАЖНО: нельзя напрямую копировать из kernel space в user space!
    // copy_to_user безопасно проверяет и копирует:
    if (copy_to_user(buf, device_buffer + *f_pos, count)) {
        return -EFAULT;
    }
    
    *f_pos += count;
    bytes_read = count;
    
    printk(KERN_INFO "chardev: read %zu bytes\n", bytes_read);
    return bytes_read;
}

// Обработчик write():
static ssize_t device_write(struct file *filp, const char __user *buf,
                            size_t count, loff_t *f_pos) {
    if (count > BUFFER_SIZE - buffer_pos)
        count = BUFFER_SIZE - buffer_pos;
    
    // Копируем из user space в kernel space:
    if (copy_from_user(device_buffer + buffer_pos, buf, count)) {
        return -EFAULT;
    }
    
    buffer_pos += count;
    printk(KERN_INFO "chardev: wrote %zu bytes\n", count);
    return count;
}

// Таблица файловых операций:
static struct file_operations fops = {
    .owner   = THIS_MODULE,
    .open    = device_open,
    .release = device_release,
    .read    = device_read,
    .write   = device_write,
};

static int __init chardev_init(void) {
    // Выделить динамический major номер:
    if (alloc_chrdev_region(&dev_num, 0, 1, DEVICE_NAME) < 0) {
        printk(KERN_ERR "chardev: failed to allocate major\n");
        return -1;
    }
    major_number = MAJOR(dev_num);
    
    // Создать class (для udev → автоматически /dev/chardev):
    device_class = class_create(THIS_MODULE, DEVICE_NAME);
    if (IS_ERR(device_class)) {
        unregister_chrdev_region(dev_num, 1);
        return PTR_ERR(device_class);
    }
    
    // Создать device:
    device_dev = device_create(device_class, NULL, dev_num, NULL, DEVICE_NAME);
    if (IS_ERR(device_dev)) {
        class_destroy(device_class);
        unregister_chrdev_region(dev_num, 1);
        return PTR_ERR(device_dev);
    }
    
    // Инициализировать cdev:
    cdev_init(&char_dev, &fops);
    char_dev.owner = THIS_MODULE;
    if (cdev_add(&char_dev, dev_num, 1) < 0) {
        device_destroy(device_class, dev_num);
        class_destroy(device_class);
        unregister_chrdev_region(dev_num, 1);
        return -1;
    }
    
    printk(KERN_INFO "chardev: registered with major=%d\n", major_number);
    return 0;
}

static void __exit chardev_exit(void) {
    cdev_del(&char_dev);
    device_destroy(device_class, dev_num);
    class_destroy(device_class);
    unregister_chrdev_region(dev_num, 1);
    printk(KERN_INFO "chardev: unregistered\n");
}

module_init(chardev_init);
module_exit(chardev_exit);
```

```bash
# После загрузки:
ls -la /dev/chardev
# crw------- 1 root root 247, 0 Jan  1 00:00 /dev/chardev

# Тест:
echo "Hello from userspace" > /dev/chardev
cat /dev/chardev
# Hello from userspace

dmesg | tail -5
# chardev: opened
# chardev: wrote 21 bytes
# chardev: closed
# chardev: opened
# chardev: read 21 bytes
# chardev: closed
```

---

## 4. Взаимодействие с PCI/PCIe устройствами

### 4.1 PCI Device Driver

```c
// pci_driver.c — скелет PCIe драйвера
#include <linux/pci.h>
#include <linux/module.h>

// Таблица поддерживаемых устройств:
static const struct pci_device_id my_pci_tbl[] = {
    { PCI_DEVICE(0x1234, 0x5678) },   // vendor 0x1234, device 0x5678
    { PCI_DEVICE(0xABCD, 0xEF01) },
    { 0 }  // конец таблицы
};
MODULE_DEVICE_TABLE(pci, my_pci_tbl);

// Структура состояния устройства:
struct my_device {
    void __iomem *mmio_base;   // маппированный MMIO
    unsigned long mmio_size;
    int irq;
    struct pci_dev *pdev;
};

// Обработчик прерывания:
static irqreturn_t my_irq_handler(int irq, void *dev_id) {
    struct my_device *dev = (struct my_device *)dev_id;
    
    // Проверить, наше ли это прерывание:
    uint32_t status = ioread32(dev->mmio_base + STATUS_REG);
    if (!(status & IRQ_PENDING))
        return IRQ_NONE;  // не наше — дадим другим обработчикам
    
    // Обработать:
    iowrite32(IRQ_CLEAR, dev->mmio_base + STATUS_REG);  // сбросить флаг
    
    return IRQ_HANDLED;
}

// Инициализация устройства при обнаружении:
static int my_probe(struct pci_dev *pdev, const struct pci_device_id *id) {
    struct my_device *dev;
    int ret;
    
    printk(KERN_INFO "my_driver: found device %04x:%04x\n",
           pdev->vendor, pdev->device);
    
    // Выделить память под нашу структуру:
    dev = devm_kzalloc(&pdev->dev, sizeof(*dev), GFP_KERNEL);
    if (!dev) return -ENOMEM;
    
    dev->pdev = pdev;
    pci_set_drvdata(pdev, dev);
    
    // Включить PCI устройство:
    ret = pci_enable_device(pdev);
    if (ret) return ret;
    
    // Запросить MMIO регион (BAR 0):
    ret = pci_request_regions(pdev, "my_driver");
    if (ret) goto err_disable;
    
    // Маппировать MMIO в kernel virtual address:
    dev->mmio_base = pci_ioremap_bar(pdev, 0);
    if (!dev->mmio_base) { ret = -ENOMEM; goto err_regions; }
    dev->mmio_size = pci_resource_len(pdev, 0);
    
    // Настроить DMA:
    ret = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(64));
    if (ret) { ret = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32)); }
    if (ret) goto err_iounmap;
    
    // Зарегистрировать обработчик прерывания:
    dev->irq = pdev->irq;
    ret = request_irq(dev->irq, my_irq_handler, IRQF_SHARED, "my_driver", dev);
    if (ret) goto err_iounmap;
    
    // Инициализировать устройство:
    pci_set_master(pdev);  // включить bus mastering для DMA
    
    // Записать в MMIO регистры (конфигурация устройства):
    iowrite32(0x01, dev->mmio_base + CONTROL_REG);
    
    return 0;

err_iounmap:
    iounmap(dev->mmio_base);
err_regions:
    pci_release_regions(pdev);
err_disable:
    pci_disable_device(pdev);
    return ret;
}

// Удаление устройства:
static void my_remove(struct pci_dev *pdev) {
    struct my_device *dev = pci_get_drvdata(pdev);
    
    free_irq(dev->irq, dev);
    iounmap(dev->mmio_base);
    pci_release_regions(pdev);
    pci_disable_device(pdev);
    
    printk(KERN_INFO "my_driver: device removed\n");
}

static struct pci_driver my_pci_driver = {
    .name     = "my_driver",
    .id_table = my_pci_tbl,
    .probe    = my_probe,
    .remove   = my_remove,
};

module_pci_driver(my_pci_driver);  // macro: init/exit регистрирует/удаляет драйвер
```

---

## 5. Управление памятью в ядре

### 5.1 Аллокаторы ядра

```c
// В ядре нет malloc/free — используются:

// 1. kmalloc: как malloc, но для kernel (физически непрерывная память):
void *ptr = kmalloc(1024, GFP_KERNEL);   // можно спать при нехватке
void *ptr = kmalloc(1024, GFP_ATOMIC);  // нельзя спать (из ISR/spinlock)
kfree(ptr);

// 2. vzalloc: виртуально непрерывная (физически может быть фрагментирована):
void *ptr = vmalloc(1024 * 1024);  // большие аллокации
vfree(ptr);

// 3. kzalloc: kmalloc + обнуление:
struct my_data *data = kzalloc(sizeof(*data), GFP_KERNEL);

// 4. kmem_cache: slab аллокатор для частых аллокаций одного типа:
struct kmem_cache *cache = kmem_cache_create("my_cache",
                                              sizeof(struct my_obj),
                                              0, SLAB_HWCACHE_ALIGN, NULL);
struct my_obj *obj = kmem_cache_alloc(cache, GFP_KERNEL);
kmem_cache_free(cache, obj);
kmem_cache_destroy(cache);

// 5. alloc_pages: напрямую страницы памяти:
struct page *page = alloc_pages(GFP_KERNEL, 0);  // 2^0 = 1 страница = 4KB
void *vaddr = page_address(page);
free_pages((unsigned long)vaddr, 0);
```

**GFP flags (Get Free Pages):**
- `GFP_KERNEL` — обычная аллокация, может спать, для kernel code
- `GFP_ATOMIC` — не может спать, для прерываний и spinlock контекста
- `GFP_DMA` — память для старых DMA (ниже 16MB, ISA DMA)
- `GFP_NOWAIT` — вернуть NULL если нет немедленно свободной памяти
- `__GFP_ZERO` — обнулить память

### 5.2 DMA Mapping

```c
// DMA coherent (синхронизированная) память:
void *vaddr;
dma_addr_t dma_addr;
vaddr = dma_alloc_coherent(&pdev->dev, PAGE_SIZE, &dma_addr, GFP_KERNEL);
// vaddr — виртуальный адрес для CPU
// dma_addr — физический адрес для DMA контроллера

// Программировать DMA:
my_device_set_dma_address(dev->mmio, dma_addr, PAGE_SIZE);

// Освободить:
dma_free_coherent(&pdev->dev, PAGE_SIZE, vaddr, dma_addr);
```

---

## 6. Синхронизация в ядре

```c
// Мьютекс (может спать — только process context):
#include <linux/mutex.h>
DEFINE_MUTEX(my_mutex);

mutex_lock(&my_mutex);     // блокируется если занят
// критическая секция
mutex_unlock(&my_mutex);

// Spinlock (не может спать — ISR context):
#include <linux/spinlock.h>
DEFINE_SPINLOCK(my_spinlock);
unsigned long flags;

spin_lock_irqsave(&my_spinlock, flags);    // блокирует + отключает прерывания
// критическая секция
spin_unlock_irqrestore(&my_spinlock, flags);

// RCU (Read-Copy-Update) для read-heavy структур:
#include <linux/rcupdate.h>

// Читатель (очень быстро, нет блокировки):
rcu_read_lock();
struct my_data *data = rcu_dereference(global_ptr);
// использовать data
rcu_read_unlock();

// Писатель (медленно, нечасто):
struct my_data *new_data = kmalloc(sizeof(*new_data), GFP_KERNEL);
*new_data = *old_data;  // copy
new_data->field = new_value;
rcu_assign_pointer(global_ptr, new_data);
synchronize_rcu();  // ждём завершения всех читателей
kfree(old_data);
```

---

## 7. Отладка модулей ядра

### 7.1 printk и динамическое включение

```c
// Уровни printk:
printk(KERN_EMERG   "system unusable\n");   // 0
printk(KERN_ALERT   "action needed\n");     // 1
printk(KERN_CRIT    "critical\n");          // 2
printk(KERN_ERR     "error\n");             // 3
printk(KERN_WARNING "warning\n");           // 4
printk(KERN_NOTICE  "notice\n");            // 5
printk(KERN_INFO    "info\n");              // 6
printk(KERN_DEBUG   "debug\n");             // 7

// Современные helper макросы:
pr_info("My module: %s\n", "loaded");
pr_debug("Debug: value = %d\n", val);       // только если DEBUG определён
pr_err("Error: %d\n", ret);

// Для устройств:
dev_info(&pdev->dev, "device found\n");     // добавляет имя устройства
dev_err(&pdev->dev, "initialization failed\n");
```

```bash
# Просмотр:
dmesg -T | tail -20        # с временными метками
dmesg -w                   # следить в реальном времени
journalctl -k -f           # через journald

# Динамическое включение debug:
echo "module my_module +p" > /sys/kernel/debug/dynamic_debug/control
# Включает pr_debug в модуле my_module
```

### 7.2 /proc и /sys для отладки

```c
// Создать /proc/my_module:
#include <linux/proc_fs.h>
#include <linux/seq_file.h>

static int my_proc_show(struct seq_file *m, void *v) {
    seq_printf(m, "status: %d\n", my_status);
    seq_printf(m, "requests: %lu\n", my_counter);
    return 0;
}

static int my_proc_open(struct inode *inode, struct file *file) {
    return single_open(file, my_proc_show, NULL);
}

static const struct proc_ops my_proc_ops = {
    .proc_open    = my_proc_open,
    .proc_read    = seq_read,
    .proc_release = single_release,
};

// В init:
proc_create("my_module", 0, NULL, &my_proc_ops);
// В exit:
remove_proc_entry("my_module", NULL);
```

```bash
cat /proc/my_module
# status: 1
# requests: 42
```

### 7.3 kgdb — отладчик ядра

```bash
# Загрузить ядро с kgdb (параметры):
# kgdboc=ttyS0,115200 kgdbwait

# Подключиться GDB:
gdb vmlinux
(gdb) target remote /dev/ttyS0
(gdb) break my_function
(gdb) continue
```

### 7.4 KASAN (Kernel Address Sanitizer)

```bash
# Компиляция ядра с KASAN:
CONFIG_KASAN=y
CONFIG_KASAN_INLINE=y

# Обнаруживает:
# - use-after-free
# - out-of-bounds access
# - stack overflow

# Пример вывода KASAN:
# BUG: KASAN: use-after-free in module_function+0x34/0x80
# Read of size 8 at addr ffff88... by task mymodule/1234
# Allocated by task 1234:
#   kmalloc ...
# Freed by task 1234:
#   kfree ...
```

---

## 8. Стабильность ABI ядра

### 8.1 "Нет стабильного ABI ядра"

Линус Торвальдс последовательно придерживается позиции: **binary ABI между ядром и модулями нестабильно**. Каждый модуль компилируется под конкретную версию ядра.

Это означает:
- Модуль для ядра 6.1 не загрузится в ядро 6.2 без перекомпиляции
- Проприетарные драйверы (NVIDIA, VMware) имеют wrapper — тонкий GPL слой, адаптирующий API

```bash
# Версия ядра в модуле:
modinfo nvidia.ko | grep vermagic
# vermagic: 6.1.0-21-amd64 SMP preempt mod_unload modversions

# Если vermagic не совпадает с текущим ядром → insmod не загрузит:
# ERROR: could not insert module: version magic '6.0.0' should be '6.1.0'
```

### 8.2 DKMS — Dynamic Kernel Module Support

```bash
# DKMS: автоматическая перекомпиляция при обновлении ядра
# Используется для NVIDIA, VirtualBox, ZFS on Linux и т.д.

# Установить DKMS модуль:
sudo dkms add ./my_module-1.0/
sudo dkms build my_module/1.0
sudo dkms install my_module/1.0

# При обновлении ядра (apt upgrade):
# dkms autoinstall автоматически пересобирает все DKMS модули
```

---

## Заключение

Модули ядра — мощный механизм расширения Linux. Они позволяют поддерживать тысячи различных устройств без раздувания монолитного ядра, а загрузка/выгрузка без перезагрузки — бесценное свойство для серверов.

Написание модулей ядра требует особой дисциплины: нет stdlib, аллокации могут завершиться неудачей, синхронизация должна учитывать прерывания, ошибки приводят к kernel panic. Зато доступны все возможности ядра: прямой доступ к аппаратуре, MMIO, DMA, прерывания.

Для системного программиста понимание драйверной архитектуры объясняет: как /dev файлы связаны с аппаратурой, как работает udev и автоопределение устройств, почему для некоторых устройств нужна перезагрузка (изменение DKMS модуля), как kernel panic связан с багами в драйверах.

---

## Литература и источники

1. Corbet, J., Rubini, A., & Kroah-Hartman, G. (2005). *Linux Device Drivers* (3rd ed.). O'Reilly. — https://lwn.net/Kernel/LDD3/ — свободно доступна онлайн.

2. Love, R. (2010). *Linux Kernel Development* (3rd ed.). Addison-Wesley Professional.

3. Linux Kernel Documentation. *Driver implementer's API guide*. — https://www.kernel.org/doc/html/latest/driver-api/index.html

4. Linux Kernel Documentation. *Writing kernel documentation*. — https://www.kernel.org/doc/html/latest/

5. Wikipedia. *Loadable kernel module*. — https://en.wikipedia.org/wiki/Loadable_kernel_module

6. Linux Foundation. *Linux Driver Template*. — https://github.com/Johannes4Linux/Linux_Driver_Tutorial

7. The Linux Kernel Module Programming Guide. — https://sysprog21.github.io/lkmpg/

8. Torvalds, L. *On stable kernel ABI*. — https://lkml.org/lkml/2012/12/23/75

9. DKMS Framework. — https://github.com/dell/dkms

10. OSDev Wiki. *Writing PCI Drivers*. — https://wiki.osdev.org/PCI
