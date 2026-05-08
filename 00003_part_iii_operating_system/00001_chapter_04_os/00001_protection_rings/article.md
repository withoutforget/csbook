# Кольца защиты: kernel space и user space

## Введение

Современные процессоры работают не в единой плоской модели привилегий, где любая инструкция может быть выполнена в любой момент. Вместо этого они реализуют иерархическую модель привилегий, называемую **кольцами защиты** (protection rings). Эта модель — один из фундаментальных механизмов безопасности, обеспечивающих изоляцию операционной системы от пользовательских программ, а виртуальных машин от гостевых операционных систем.

Концепция колец защиты появилась в 1960-х годах в системе Multics и с тех пор стала стандартом для архитектур x86, ARM и большинства современных процессоров. Понимание этого механизма критически важно для системных программистов, разработчиков операционных систем, специалистов по безопасности и всех, кто хочет понять, как компьютер защищает себя от ненадёжного кода.

## Архитектура колец защиты x86

Процессоры архитектуры x86 реализуют четыре уровня привилегий, называемых кольцами: от Ring 0 (наибольшие привилегии) до Ring 3 (наименьшие привилегии). Каждое кольцо определяет, какие инструкции процессора и ресурсы системы доступны исполняемому коду.

```
        ┌─────────────────────────────────────────┐
        │           Ring 0: Kernel                │  ← Ядро ОС
        │  ┌───────────────────────────────────┐  │
        │  │        Ring 1: (не используется)   │  │  ← Зарезервировано
        │  │  ┌─────────────────────────────┐  │  │
        │  │  │   Ring 2: (не используется)  │  │  │  ← Зарезервировано
        │  │  │  ┌───────────────────────┐  │  │  │
        │  │  │  │   Ring 3: User Space  │  │  │  │  ← Пользовательские приложения
        │  │  │  └───────────────────────┘  │  │  │
        │  │  └─────────────────────────────┘  │  │
        │  └───────────────────────────────────┘  │
        └─────────────────────────────────────────┘
```

### Ring 0 — Режим ядра

Ring 0 — наиболее привилегированный уровень. Код, исполняемый в этом кольце, имеет полный доступ к аппаратному обеспечению: может выполнять любые инструкции процессора, читать и записывать в любые адреса памяти, управлять устройствами ввода-вывода, изменять содержимое специальных регистров (CR0, CR3, EFER, MSR), включать и выключать прерывания.

В кольце 0 работает ядро операционной системы — тот код, которому мы безоговорочно доверяем, поскольку ошибка в нём может привести к краху всей системы (kernel panic / BSOD).

Привилегированные инструкции, доступные только в Ring 0:
- `HLT` — остановка процессора
- `LGDT` / `LIDT` — загрузка таблиц дескрипторов
- `MOV CR0` — изменение управляющих регистров
- `IN` / `OUT` — прямой доступ к портам ввода-вывода
- `WRMSR` / `RDMSR` — чтение/запись Model Specific Registers
- `INVLPG` — инвалидация записи TLB

### Ring 3 — Пользовательский режим

Ring 3 — наименее привилегированный уровень. Здесь работают все пользовательские приложения: браузеры, текстовые редакторы, игры, интерпретаторы Python. Код в Ring 3:

- Не может выполнять привилегированные инструкции (получает General Protection Fault — #GP)
- Не может напрямую обращаться к аппаратуре
- Видит только своё виртуальное адресное пространство
- Может обращаться только к памяти, разрешённой таблицами страниц

### Rings 1 и 2 — Неиспользуемые уровни

В реальных ОС кольца 1 и 2 практически не используются. Архитекторы Multics планировали размещать здесь драйверы устройств и подсистемы ОС, но Unix-подобные системы и Windows приняли более простую модель: всё доверенное работает в Ring 0, всё недоверенное — в Ring 3.

## Текущий уровень привилегий (CPL)

Процессор отслеживает текущий уровень привилегий через поле CPL (Current Privilege Level) в регистре CS (Code Segment). Значение CPL — это два младших бита CS:

```c
// Получить текущий CPL в x86-64 (только в Ring 0)
static inline int get_cpl(void) {
    uint16_t cs;
    asm volatile("mov %%cs, %0" : "=r"(cs));
    return cs & 3;  // Два младших бита
}
```

Дескрипторы сегментов и записи в таблицах страниц также содержат поля DPL (Descriptor Privilege Level) и RPL (Requested Privilege Level). Аппаратная защита проверяет: CPL <= DPL для разрешения доступа.

## Почему нужна изоляция

Представьте ситуацию без колец защиты: любая программа могла бы напрямую записать в область ядра, изменить обработчики прерываний или перезаписать адресное пространство другого процесса. Это сделало бы систему полностью незащищённой.

Изоляция обеспечивает несколько ключевых свойств:

**1. Защита целостности ОС.** Пользовательский код не может модифицировать критические структуры данных ядра — таблицы процессов, таблицы страниц, буферный кэш.

**2. Изоляция процессов.** Один процесс не может читать или писать в память другого процесса (если это явно не разрешено через IPC).

**3. Управляемый доступ к ресурсам.** Все запросы к аппаратуре проходят через ядро, которое может применять политики доступа, квоты, аудит.

**4. Отказоустойчивость.** Ошибка в пользовательской программе (сегфолт) не приводит к краху всей системы — ядро просто завершает процесс.

## Переключение колец: системные вызовы

Для выполнения привилегированных операций пользовательский код должен попросить ядро сделать это от его имени. Механизм такого запроса — системный вызов.

### INT 0x80 — Legacy механизм (x86-32)

Первоначально системные вызовы реализовывались через программное прерывание `INT 0x80`. Процессор при получении этого прерывания:

1. Сохраняет текущее состояние (CS, EIP, EFLAGS, SS, ESP) в стек ядра
2. Переключается на Ring 0
3. Загружает обработчик из IDT (Interrupt Descriptor Table)
4. Ядро обрабатывает запрос и вызывает `IRET`
5. `IRET` восстанавливает состояние и возвращает в Ring 3

```c
// Системный вызов write через INT 0x80 (x86-32)
int sys_write_legacy(int fd, const char *buf, size_t count) {
    int result;
    asm volatile(
        "int $0x80"
        : "=a"(result)
        : "a"(4),        // __NR_write = 4
          "b"(fd),
          "c"(buf),
          "d"(count)
        : "memory"
    );
    return result;
}
```

### SYSCALL/SYSRET — Современный механизм (x86-64)

Инструкция `INT 0x80` оказалась медленной из-за проверок и сохранения контекста. В x86-64 появились инструкции `SYSCALL` и `SYSRET`, специально оптимизированные для быстрого переключения колец.

При выполнении `SYSCALL`:
1. Адрес возврата сохраняется в регистре RCX
2. RFLAGS сохраняется в R11
3. RIP загружается из MSR `LSTAR` (адрес обработчика ядра)
4. CS и SS устанавливаются на значения Ring 0 (из MSR `STAR`)
5. Управление передаётся в ядро

При выполнении `SYSRET`:
1. RIP восстанавливается из RCX
2. RFLAGS восстанавливается из R11
3. CS и SS устанавливаются на значения Ring 3

```c
// Прямой системный вызов через SYSCALL (x86-64)
long raw_syscall(long number, long a1, long a2, long a3) {
    long result;
    register long r10 asm("r10") = 0;
    asm volatile(
        "syscall"
        : "=a"(result)
        : "a"(number), "D"(a1), "S"(a2), "d"(a3)
        : "rcx", "r11", "memory"
    );
    return result;
}

// Пример: вывод строки напрямую через системный вызов
void write_direct(const char *msg, size_t len) {
    raw_syscall(1, 1, (long)msg, (long)len);  // sys_write(stdout, msg, len)
}
```

Таблица скорости переключения (приблизительно):
- `SYSCALL/SYSRET`: ~100-200 нс
- `INT 0x80 / IRET`: ~300-500 нс
- Функциональный вызов внутри Ring 3: ~1-5 нс

## Исключения при нарушении привилегий

Когда код пытается нарушить правила привилегий, процессор генерирует аппаратное исключение.

### General Protection Fault (#GP, вектор 13)

Возникает при попытке:
- Выполнить привилегированную инструкцию в Ring 3
- Обратиться к сегменту с недостаточными привилегиями
- Нарушить формат данных (например, не выровненный SSE доступ с флагом AC)

```c
// Этот код в пользовательском приложении вызовет #GP → SIGSEGV
void cause_gp_fault(void) {
    asm volatile("hlt");  // Привилегированная инструкция!
}
```

Ядро перехватывает #GP и посылает процессу сигнал `SIGSEGV` или `SIGILL`.

### Page Fault (#PF, вектор 14) → SIGSEGV

Возникает при обращении к странице памяти без прав доступа:

```c
// Запись в память ядра из пользовательского пространства
void cause_page_fault(void) {
    volatile int *kernel_addr = (int *)0xFFFF800000000000ULL;
    *kernel_addr = 42;  // #PF → SIGSEGV
}
```

```python
# Python версия — демонстрация через ctypes
import ctypes
import signal

def segfault_handler(signum, frame):
    print(f"Получен сигнал {signum} (SIGSEGV)")

signal.signal(signal.SIGSEGV, segfault_handler)

# Попытка записи в нулевой указатель
# ctypes.cast(0, ctypes.POINTER(ctypes.c_int))[0] = 42  # SIGSEGV
```

## Hypervisor и Ring -1 (VMX)

С развитием виртуализации появилась необходимость в ещё одном уровне привилегий, более высоком, чем Ring 0 — ведь гипервизор должен контролировать само ядро гостевой ОС.

Intel реализовал это через **Intel VT-x** (Virtualization Technology for x86) с операцией **VMX** (Virtual Machine eXtensions). Гипервизор работает в режиме **VMX root operation**, который неформально называют Ring -1.

### Как работает VMX

```
┌──────────────────────────────────────────────┐
│         Ring -1: Hypervisor (VMX root)       │
│         KVM, Xen, VMware ESXi, Hyper-V       │
├──────────────────────────────────────────────┤
│              Гостевая ОС                      │
│  ┌──────────────────────────────────────┐    │
│  │    Ring 0: Guest Kernel (VMX non-root)│    │
│  ├──────────────────────────────────────┤    │
│  │    Ring 3: Guest User Space          │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

Ключевые инструкции VMX:
- `VMXON` — включить режим виртуализации
- `VMXOFF` — выключить режим виртуализации
- `VMLAUNCH` — запустить виртуальную машину
- `VMRESUME` — возобновить выполнение VM
- `VMEXIT` — выход из VM в гипервизор (при попытке привилегированных операций)

```c
// Упрощённая схема цикла гипервизора
void hypervisor_loop(struct vmcs *vmcs) {
    while (1) {
        vmresume();  // Передать управление гостевому ядру
        
        // Попали сюда из-за VMEXIT
        uint32_t exit_reason = vmcs_read(VM_EXIT_REASON);
        
        switch (exit_reason) {
            case EXIT_REASON_CPUID:
                handle_cpuid(vmcs);
                break;
            case EXIT_REASON_IO_INSTRUCTION:
                handle_io(vmcs);
                break;
            case EXIT_REASON_MSR_WRITE:
                handle_msr_write(vmcs);
                break;
            // ...
        }
    }
}
```

## ARM Exception Levels (EL0-EL3)

Архитектура ARM AArch64 реализует аналогичную концепцию через **Exception Levels** (EL):

```
EL3: Secure Monitor (TrustZone) — наивысший приоритет
EL2: Hypervisor
EL1: OS Kernel
EL0: User Applications
```

Это прямой аналог x86, но с более явным разделением и поддержкой TrustZone (аппаратная изоляция безопасного мира).

| ARM EL | x86 аналог | Что работает |
|--------|-----------|--------------|
| EL0    | Ring 3    | Пользовательские приложения |
| EL1    | Ring 0    | Ядро ОС |
| EL2    | Ring -1   | Гипервизор |
| EL3    | Нет аналога | TrustZone Secure Monitor |

Переходы между уровнями в ARM:
- EL0 → EL1: через инструкцию `SVC` (Supervisor Call) — аналог SYSCALL
- EL1 → EL2: через `HVC` (Hypervisor Call)
- EL1/EL2 → EL3: через `SMC` (Secure Monitor Call)

```
// ARM64 системный вызов
.global my_write
my_write:
    mov x8, #64        // __NR_write в AArch64
    svc #0             // Exception Level switch EL0 → EL1
    ret
```

## SMEP и SMAP — Защита ядра от пользовательского кода

Даже с кольцами защиты оставался класс атак: если злоумышленник может заставить ядро выполнить код, помещённый в пользовательскую память, или прочитать данные из пользовательской памяти без проверок. Intel ввёл два механизма для защиты от этих атак.

### SMEP — Supervisor Mode Execution Prevention

Бит SMEP в регистре CR4 запрещает ядру (в Ring 0) выполнять код, находящийся в страницах, помеченных как пользовательские (бит U/S в записи таблицы страниц).

```
Без SMEP: Ядро → выполняет shellcode → в пользовательской памяти  [уязвимость!]
С SMEP:   Ядро → попытка выполнить код из Ring 3 → #PF (#GP)       [защита]
```

```c
// Включение SMEP в Linux (arch/x86/kernel/cpu/common.c)
static void setup_smep(struct cpuinfo_x86 *c) {
    if (cpu_has(c, X86_FEATURE_SMEP))
        cr4_set_bits(X86_CR4_SMEP);
}
```

### SMAP — Supervisor Mode Access Prevention

Бит SMAP в CR4 запрещает ядру случайный доступ к пользовательским данным. Для легитимного доступа к пользовательской памяти ядро должно явно установить флаг `AC` в EFLAGS перед копированием:

```c
// Linux: copy_from_user() использует STAC/CLAC
static inline int copy_from_user(void *to, const void *from, unsigned long n) {
    if (access_ok(from, n)) {
        stac();           // SET AC flag — разрешить доступ к user memory
        memcpy(to, from, n);
        clac();           // CLEAR AC flag — запретить обратно
    }
}
```

Проверим поддержку этих функций на реальной машине:

```bash
# Проверка поддержки SMEP и SMAP
grep -m1 'flags' /proc/cpuinfo | tr ' ' '\n' | grep -E 'smep|smap'
# Ожидаемый вывод:
# smep
# smap

# Проверка активных битов CR4 (только из Ring 0, например через dmesg)
dmesg | grep -i "cr4\|smep\|smap"
```

## Что можно делать в user space, что требует kernel

Практическая таблица операций:

| Операция | User Space | Требует Kernel (syscall) |
|----------|-----------|--------------------------|
| Вычисления, логика | Да | Нет |
| Работа с памятью в куче | Да (через malloc) | `brk()`/`mmap()` для расширения |
| Открытие файла | Нет | `open()` syscall |
| Чтение файла | Нет | `read()` syscall |
| Создание процесса | Нет | `fork()`/`execve()` |
| Сетевое соединение | Нет | `socket()`, `connect()` |
| Получение времени | Частично (vDSO) | `clock_gettime()` |
| Запись в /dev/mem | Нет | Требует root + CAP_SYS_RAWIO |
| Изменение прав файла | Нет | `chmod()` syscall |
| Загрузка модуля ядра | Нет | `init_module()` syscall |

## Проверка привилегий на практике

```python
import os
import ctypes

# Получение информации о текущем процессе
print(f"PID: {os.getpid()}")
print(f"UID: {os.getuid()}")
print(f"Эффективный UID: {os.geteuid()}")

# Попытка привилегированной операции
try:
    # Открытие /dev/mem требует root
    fd = os.open('/dev/mem', os.O_RDONLY)
    print("Успех: доступ к /dev/mem")
    os.close(fd)
except PermissionError as e:
    print(f"Отказано (ожидаемо): {e}")

# Стандартная операция в user space
with open('/etc/hostname', 'r') as f:
    print(f"Hostname: {f.read().strip()}")
```

```bash
# Запуск программы и наблюдение за системными вызовами
strace -e trace=open,read,write,mmap ./my_program

# Пример вывода:
# execve("./my_program", ["./my_program"], ...) = 0
# mmap(NULL, 4096, PROT_READ|PROT_WRITE, ...) = 0x7f...
# open("/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3
# read(3, "\177ELF...", 832) = 832
```

## Модули ядра Linux: выход в Ring 0

Разработчики могут писать код для Ring 0 через механизм модулей ядра (Kernel Modules):

```c
// simple_module.c — минимальный модуль ядра (Ring 0)
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Example");

static int __init simple_init(void) {
    // Этот код выполняется в Ring 0!
    printk(KERN_INFO "Module loaded. We are in Ring 0!\n");
    
    // Читаем CR4 — только возможно в Ring 0
    unsigned long cr4;
    asm volatile("mov %%cr4, %0" : "=r"(cr4));
    printk(KERN_INFO "CR4 = 0x%lx\n", cr4);
    
    // Проверяем SMEP (бит 20) и SMAP (бит 21)
    printk(KERN_INFO "SMEP: %s\n", (cr4 & (1UL << 20)) ? "ON" : "OFF");
    printk(KERN_INFO "SMAP: %s\n", (cr4 & (1UL << 21)) ? "ON" : "OFF");
    
    return 0;
}

static void __exit simple_exit(void) {
    printk(KERN_INFO "Module unloaded\n");
}

module_init(simple_init);
module_exit(simple_exit);
```

```bash
# Компиляция и загрузка модуля
make -C /lib/modules/$(uname -r)/build M=$(pwd) modules
sudo insmod simple_module.ko
dmesg | tail -5
sudo rmmod simple_module
```

## Заключение

Кольца защиты — это элегантное аппаратное решение проблемы безопасности и изоляции в многозадачных системах. Архитектура x86 определяет четыре кольца (0-3), из которых реально используются Ring 0 (ядро) и Ring 3 (пользователь). Переключение между ними происходит через системные вызовы (SYSCALL/SYSRET) — контролируемый, быстрый механизм перехода.

С развитием виртуализации появился Ring -1 (VMX/VT-x), где работают гипервизоры. ARM реализует ту же идею через Exception Levels (EL0-EL3). Дополнительные механизмы защиты — SMEP и SMAP — предотвращают атаки, при которых ядро могло быть обманом выполнить или прочитать пользовательский код.

Понимание этой модели необходимо для написания драйверов, гипервизоров, систем безопасности и анализа уязвимостей на уровне привилегий.

## Литература и источники

1. Intel Corporation. *Intel® 64 and IA-32 Architectures Software Developer's Manual, Volume 3A: System Programming Guide, Part 1*. Chapter 5: Protection. Intel, 2024. https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html

2. AMD. *AMD64 Architecture Programmer's Manual, Volume 2: System Programming*. Chapter 4: Segmented Virtual Memory. AMD, 2024. https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/programmer-references/24593.pdf

3. Love, Robert. *Linux Kernel Development*, 3rd Edition. Addison-Wesley, 2010. ISBN: 978-0-672-32946-3.

4. Bovet, Daniel P., and Marco Cesati. *Understanding the Linux Kernel*, 3rd Edition. O'Reilly Media, 2005. ISBN: 978-0-596-00565-8.

5. Silberschatz, Abraham, Peter B. Galvin, and Greg Gagne. *Operating System Concepts*, 10th Edition. Wiley, 2018. ISBN: 978-1-119-32091-3.

6. ARM Limited. *ARM Architecture Reference Manual ARMv8, for ARMv8-A architecture profile*. ARM, 2021. https://developer.arm.com/documentation/ddi0487/latest

7. Drepper, Ulrich. *What Every Programmer Should Know About Memory*. Red Hat, 2007. https://www.akkadia.org/drepper/cpumemory.pdf

8. Kerrisk, Michael. *The Linux Programming Interface*. No Starch Press, 2010. ISBN: 978-1-59327-220-3.

9. Intel Corporation. *Intel Virtualization Technology for IA-32, Intel 64, and Intel Architecture (Intel VT-x)*. Application Note AP-1003, 2012. https://www.intel.com/content/dam/www/public/us/en/documents/white-papers/virtualization-enabling-intel-virtualization-technology-features-and-benefits-paper.pdf

10. Corbet, Jonathan, Alessandro Rubini, and Greg Kroah-Hartman. *Linux Device Drivers*, 3rd Edition. O'Reilly Media, 2005. https://lwn.net/Kernel/LDD3/
