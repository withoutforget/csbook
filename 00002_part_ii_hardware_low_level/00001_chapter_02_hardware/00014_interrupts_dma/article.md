# Прерывания и DMA

## Введение

Представьте, что вы читаете книгу, и вам нужно дождаться закипания чайника. Есть два подхода: periodically check (периодически смотреть на чайник) или поставить свисток (чайник сам уведомит вас). Первый подход называется polling (опрос), второй — interrupt (прерывание). Именно разница между ними определяет, как процессор взаимодействует с внешними устройствами.

Прерывания — один из фундаментальных механизмов операционных систем. Без прерываний процессор был бы вынужден постоянно опрашивать каждое устройство — клавиатуру, сетевую карту, диск. Это расточительно и неэффективно. Прерывания позволяют процессору заниматься полезной работой, получая уведомление от устройства только тогда, когда происходит событие.

DMA (Direct Memory Access) дополняет механизм прерываний: вместо того чтобы процессор копировал данные байт за байтом между устройством и памятью, специальный контроллер DMA делает это самостоятельно, освобождая CPU для других задач. Без DMA передача 4 МБ данных с диска заняла бы миллионы процессорных тактов вместо того, чтобы выполниться «в фоне».

---

## 1. Polling vs Interrupts

### 1.1 Polling (Опрос)

При polling процессор сам проверяет состояние устройства через регулярные промежутки или в цикле:

```c
// Polling: ожидание данных от UART (последовательный порт)
char uart_receive_polling(void) {
    // Читаем регистр статуса UART пока данные не готовы:
    while ((UART_STATUS_REG & UART_RX_READY) == 0) {
        // Активное ожидание — CPU ничем другим не занят!
    }
    return UART_DATA_REG;  // Читаем данные
}
```

**Плюсы polling:**
- Минимальная задержка (immediate response)
- Простота реализации
- Предсказуемое время отклика

**Минусы polling:**
- CPU полностью занят ожиданием
- Неэффективно для редких событий
- При опросе множества устройств — масштабирование плохое

Polling используется: встроенные системы с жёсткими временными требованиями (real-time), сетевые карты с очень высоким трафиком (DPDK — Data Plane Development Kit: лучше poll 10 Gbps NIC, чем получать 10 млн прерываний/сек), в спинлоках.

### 1.2 Interrupt-Driven I/O

```c
// С прерываниями:
// 1. Инициируем операцию
uart_start_receive();       // говорим UART: когда придут данные — прерви меня

// 2. CPU занимается чем-то другим
do_useful_work();

// 3. Когда данные пришли — UART подаёт сигнал на линию IRQ
// CPU прерывает текущую работу и вызывает обработчик:
void __attribute__((interrupt)) uart_irq_handler(void) {
    char c = UART_DATA_REG;
    buffer_push(&rx_buffer, c);
    // Подтверждаем прерывание (ACK):
    UART_STATUS_REG = UART_RX_ACK;
}
```

**Плюсы прерываний:**
- CPU свободен пока устройство работает
- Масштабируется на много устройств
- Общая цель ОС: CPU должен быть занят полезной работой, а не ожиданием

---

## 2. Типы прерываний

### 2.1 Аппаратные прерывания (Hardware Interrupts)

Генерируются внешними устройствами через линии IRQ (Interrupt Request):

- **Клавиатура/мышь:** нажатие клавиши → IRQ1 (legacy PS/2)
- **Таймер:** системный таймер (IRQ0) генерирует прерывание ~100-1000 раз/сек (HZ)
- **Сетевая карта:** пришёл пакет → прерывание
- **Диск:** операция завершена → прерывание
- **USB-контроллер:** подключено устройство

Аппаратные прерывания бывают:
- **Маскируемые (maskable):** можно временно заблокировать (`cli` на x86)
- **Немаскируемые (NMI, Non-Maskable Interrupt):** всегда обрабатываются. Используются для критических ошибок памяти (hardware ECC), watchdog таймеров.

### 2.2 Программные прерывания (Software Interrupts / Трапы)

Генерируются инструкцией CPU:

```asm
; x86: int 0x80 — старый способ системных вызовов Linux:
mov eax, 1    ; syscall number: exit
mov ebx, 0    ; exit code
int 0x80      ; software interrupt → ядро обрабатывает

; Modern x86-64: syscall инструкция (быстрее int 0x80):
mov rax, 60   ; exit
xor rdi, rdi  ; exit code 0
syscall
```

### 2.3 Исключения (Exceptions / Faults/Traps/Aborts)

Генерируются самим процессором при ошибочной операции:

| Тип | Номер (x86) | Причина | Поведение |
|-----|-------------|---------|-----------|
| Divide by Zero | #DE (0) | DIV/IDIV на ноль | Fault |
| Debug | #DB (1) | Breakpoint | Trap |
| Breakpoint | #BP (3) | INT3 | Trap |
| Overflow | #OF (4) | INTO при флаге OF | Trap |
| Invalid Opcode | #UD (6) | Неизвестная инструкция | Fault |
| Device Not Available | #NM (7) | FPU не инициализирован | Fault |
| Double Fault | #DF (8) | Ошибка при обработке исключения | Abort |
| General Protection Fault | #GP (13) | Нарушение привилегий | Fault |
| Page Fault | #PF (14) | Обращение к недействительной странице | Fault |
| Floating Point | #MF (16) | Ошибка FPU | Fault |
| SIMD FP Exception | #XM (19) | SSE/AVX ошибка | Fault |

**Fault:** ядро сохраняет RIP инструкции, вызвавшей исключение. После обработки — повторное выполнение той же инструкции (например, page fault → OS выделяет страницу → повторное обращение успешно).

**Trap:** ядро сохраняет RIP следующей инструкции. После обработки — выполнение продолжается со следующей инструкции.

**Abort:** невосстановимая ошибка. Double fault → обычно означает kernel panic.

---

## 3. IDT — Interrupt Descriptor Table

### 3.1 Структура IDT

На x86-64, Interrupt Descriptor Table (IDT) — массив из 256 дескрипторов, каждый указывает на обработчик (Interrupt Service Routine, ISR):

```c
// Структура одного дескриптора IDT (16 байт в 64-битном режиме):
struct idt_entry {
    uint16_t offset_low;    // Биты 0-15 адреса обработчика
    uint16_t selector;      // Сегментный селектор (0x08 = code segment)
    uint8_t  ist;           // Interrupt Stack Table index (0 = не используется)
    uint8_t  type_attr;     // Тип: 0x8E = interrupt gate, 0xEF = trap gate
    uint16_t offset_mid;    // Биты 16-31 адреса обработчика
    uint32_t offset_high;   // Биты 32-63 адреса обработчика
    uint32_t zero;          // Зарезервировано
} __attribute__((packed));

struct idt_entry idt[256];

// Установка обработчика:
void set_idt_entry(int num, void (*handler)()) {
    uint64_t addr = (uint64_t)handler;
    idt[num].offset_low  = addr & 0xFFFF;
    idt[num].selector    = 0x08;     // kernel code segment
    idt[num].type_attr   = 0x8E;     // interrupt gate, ring 0
    idt[num].offset_mid  = (addr >> 16) & 0xFFFF;
    idt[num].offset_high = (addr >> 32) & 0xFFFFFFFF;
    idt[num].zero        = 0;
}

// Загрузка IDT:
struct {
    uint16_t limit;
    uint64_t base;
} __attribute__((packed)) idtr = {
    .limit = sizeof(idt) - 1,
    .base  = (uint64_t)idt
};
lidt(&idtr);  // инструкция LIDT
```

### 3.2 Interrupt Gate vs Trap Gate

**Interrupt Gate:** при вызове автоматически устанавливает IF=0 (маскирует прерывания). Используется для обработчиков прерываний — чтобы прерывание не прерывало само себя.

**Trap Gate:** не изменяет IF. Используется для исключений (page fault, system calls через `int`) — другие прерывания могут произойти во время обработки.

### 3.3 Что происходит при прерывании

```
1. CPU получает сигнал на IRQ линии (или INT инструкцию, или исключение)
2. CPU проверяет IF (Interrupt Flag) — если сброшен и не NMI → игнорировать
3. CPU переключается в Ring 0 (если был в Ring 3)
4. CPU сохраняет на стек: SS, RSP, RFLAGS, CS, RIP (и error code для некоторых)
5. CPU загружает из IDT[vector]: новый CS:RIP (адрес обработчика)
6. CPU переключает RSP на kernel stack
7. ISR выполняется
8. ISR выполняет IRET (interrupt return)
   IRET: восстанавливает RIP, CS, RFLAGS, RSP, SS с стека
9. Продолжается выполнение прерванной программы
```

---

## 4. APIC — Advanced Programmable Interrupt Controller

### 4.1 Legacy PIC (8259A)

Исторически (до 1990-х) использовался контроллер прерываний Intel 8259A:
- 8 IRQ-линий (два каскадированных = 15 линий: IRQ0-IRQ7 master, IRQ8-IRQ15 slave)
- IRQ0 = таймер, IRQ1 = клавиатура, IRQ3/4 = COM порты, IRQ6 = дискета...
- Фиксированные приоритеты, сложная настройка

### 4.2 APIC Architecture

Современные системы используют APIC (Advanced PIC):

**Local APIC (LAPIC):** на каждом ядре CPU. Управляет:
- Прерываниями от устройств (маршрутизированными через I/O APIC)
- Inter-Processor Interrupts (IPI) — от других ядер
- Локальным таймером (APIC Timer)
- Performance monitoring counter-ами

**I/O APIC:** один на системную плату. Принимает прерывания от устройств и маршрутизирует их на конкретные ядра через системную шину.

```
[Device] → [I/O APIC] → [System Bus] → [LAPIC on Core 0]
                                      → [LAPIC on Core 1]
                                      → [LAPIC on Core N]
```

### 4.3 MSI/MSI-X (Message Signaled Interrupts)

Современные PCIe устройства используют MSI вместо традиционных IRQ-линий:
- Устройство пишет в специальный адрес памяти (Message Address) определённое значение (Message Data)
- CPU/APIC интерпретирует это как прерывание
- Позволяет иметь до 2048 прерываний на устройство (MSI-X)
- Устраняет проблему shared IRQ (несколько устройств на одной линии)

```
# Список MSI-X прерываний NIC в Linux:
cat /proc/interrupts | grep eth0
# 26:     0    0    0  IR-PCI-MSI-0000:02:00.0-edge eth0-rx-0
# 27:     0    0    0  IR-PCI-MSI-0000:02:00.0-edge eth0-rx-1
# ...
# (каждая очередь RX/TX имеет свой вектор → можно привязать к разным ядрам)
```

### 4.4 Affinity прерываний

```bash
# Просмотр привязки прерываний к ядрам:
cat /proc/irq/26/smp_affinity_list  # в битах: 0 = ядро 0

# Привязать IRQ 26 к ядру 2:
echo 4 > /proc/irq/26/smp_affinity  # бitmask: 4 = 0b100 = ядро 2

# Автоматическая балансировка:
systemctl start irqbalance
```

---

## 5. Обработка прерываний в Linux Kernel

### 5.1 Top Half / Bottom Half

Ключевое ограничение обработчика прерываний в Linux: он выполняется с отключёнными прерываниями данного вектора, не может спать, должен быть максимально коротким.

Решение: разделить обработку на две части.

**Top Half (Верхняя половина):** выполняется непосредственно в ISR.
- Минимально необходимое: подтвердить прерывание, сохранить данные из буфера устройства, запланировать bottom half.
- Не может спать.
- Другие прерывания возможны (interrupt gate не маскирует другие).

**Bottom Half (Нижняя половина):** выполняется позже, когда прерывания разрешены.
- Медленная обработка: TCP/IP стек, дисковый I/O, запись в файлы.
- Может спать (если использует workqueue).

Механизмы bottom half в Linux:

| Механизм | Контекст | Может спать? | Применение |
|----------|----------|-------------|------------|
| softirq | обработчик прерывания | Нет | Сети (NET_RX_SOFTIRQ), блок-устройства |
| tasklet | softirq | Нет | Простые bottom halves |
| workqueue | kernel thread | **Да** | Сложная работа, нужна память |
| threaded IRQ | kernel thread | **Да** | Современные драйверы |

```c
// Пример: регистрация обработчика прерывания в Linux:
#include <linux/interrupt.h>

// Top half:
static irqreturn_t my_irq_handler(int irq, void *dev_id) {
    struct my_device *dev = (struct my_device *)dev_id;
    
    // Быстро: читаем данные из регистров устройства
    dev->rx_data = read_device_register(dev);
    dev->rx_len  = read_device_length(dev);
    
    // Подтверждаем прерывание устройству:
    write_device_register(dev, IRQ_ACK);
    
    // Планируем bottom half (tasklet):
    tasklet_schedule(&dev->rx_tasklet);
    
    return IRQ_HANDLED;
}

// Bottom half:
static void my_rx_tasklet(unsigned long data) {
    struct my_device *dev = (struct my_device *)data;
    // Медленная обработка: запись в буфер, уведомление процессов...
    process_received_data(dev->rx_data, dev->rx_len);
}

// Инициализация:
DECLARE_TASKLET(rx_tasklet, my_rx_tasklet, (unsigned long)dev);

// Регистрация:
request_irq(dev->irq,         // номер IRQ
            my_irq_handler,   // обработчик
            IRQF_SHARED,      // флаги (shared IRQ)
            "my_driver",      // имя
            dev);             // данные для обработчика
```

### 5.2 Системные вызовы как прерывания

На x86-64 системный вызов через `syscall` — фактически специальная инструкция, похожая на программное прерывание:

```
Process (Ring 3): syscall инструкция
  → CPU переключается в Ring 0
  → RIP = MSR[LSTAR] (адрес entry_SYSCALL_64 в Linux)
  → Ядро обрабатывает, возвращает результат в RAX
  → sysret — возврат в Ring 3
```

Обычные прерывания (IRQ от устройств) медленнее syscall на ~10-20 нс из-за разного механизма переключения контекста.

---

## 6. DMA — Direct Memory Access

### 6.1 Без DMA: CPU-controlled I/O

Без DMA, при передаче данных с диска в RAM, процессор:
1. Отправляет команду диску: «читай сектор X»
2. Ждёт прерывания «данные готовы»
3. В обработчике: читает данные из регистра данных диска (8/16/32 бита за раз)
4. Записывает в память
5. Повторяет шаги 3-4 для каждого слова данных

Для передачи 4 KB: 4096/4 = 1024 итерации read-write. Каждая итерация — несколько инструкций. CPU полностью занят копированием.

### 6.2 С DMA: CPU-less data transfer

```
Без DMA:
CPU → читает из порта диска → записывает в RAM → повторяет N раз

С DMA:
CPU → настраивает DMA контроллер (src: диск, dst: адрес RAM, len: 4096) → продолжает работу
DMA контроллер → независимо от CPU копирует данные диск→RAM
DMA контроллер → по завершении генерирует прерывание CPU
CPU → получает прерывание «DMA завершён» → использует данные
```

Процессор занят только настройкой (несколько инструкций) и обработкой финального прерывания. Копирование — без участия CPU.

### 6.3 DMA Controller Hardware

```
System Bus:
┌──────────┐   ┌──────────────┐   ┌────────────┐
│   CPU    │   │DMA Controller│   │   Memory   │
│          │──▶│  ┌──────────┐│   │            │
│          │   │  │ Src Addr ││◀──│            │
│          │   │  │ Dst Addr ││──▶│            │
│          │   │  │ Length   ││   │            │
│          │   │  │ Status   ││   └────────────┘
└──────────┘   │  └──────────┘│
               └──────────────┘
                      ▲
                      │ DMA Request
               ┌──────┴───────┐
               │   Device     │
               │ (HDD, NIC,   │
               │  USB, etc.)  │
               └──────────────┘
```

**Регистры DMA контроллера:**
- **Source Address Register:** откуда копировать (физический адрес или адрес I/O порта)
- **Destination Address Register:** куда копировать (адрес физической памяти)
- **Count Register:** сколько байт/слов передать
- **Control Register:** направление, ширина шины, режим (block/single/demand)
- **Status Register:** завершено, ошибка, активно

### 6.4 Scatter-Gather DMA

Современные устройства поддерживают scatter-gather: передача не одного непрерывного буфера, а списка (scatter-gather list) из множества буферов:

```c
// Linux: scatter-gather DMA
#include <linux/dma-mapping.h>
#include <linux/scatterlist.h>

struct scatterlist sg[4];  // 4 буфера

// Инициализация scatter-gather списка:
sg_init_table(sg, 4);
sg_set_buf(&sg[0], buf0, len0);
sg_set_buf(&sg[1], buf1, len1);
sg_set_buf(&sg[2], buf2, len2);
sg_set_buf(&sg[3], buf3, len3);

// Маппирование для DMA:
int nents = dma_map_sg(dev, sg, 4, DMA_FROM_DEVICE);

// Теперь sg[i].dma_address — физический адрес для DMA
for (int i = 0; i < nents; i++) {
    setup_dma_descriptor(sg[i].dma_address, sg[i].length);
}

// После завершения DMA:
dma_unmap_sg(dev, sg, 4, DMA_FROM_DEVICE);
```

Это позволяет NIC напрямую записывать заголовки пакетов и данные в разные буферы (нулевое копирование, zero-copy).

---

## 7. Примеры: как работают конкретные устройства

### 7.1 Сетевая карта (NIC)

**Приём пакета:**

```
1. Драйвер при инициализации:
   - Создаёт кольцо дескрипторов RX (RX Descriptor Ring)
   - Каждый дескриптор = физический адрес буфера (2KB) в памяти
   - Записывает адрес кольца и размер в регистры NIC

2. Приходит пакет:
   - NIC получает байты через физический интерфейс
   - NIC берёт следующий дескриптор из RX Ring
   - DMA: NIC копирует пакет в буфер, указанный в дескрипторе
   - NIC помечает дескриптор "заполнен"
   - NIC генерирует прерывание MSI-X

3. Linux top half (net_rx_action):
   - Видит заполненные дескрипторы
   - Создаёт sk_buff (socket buffer) с указателем на данные
   - Передаёт в сетевой стек (NAPI poll)

4. Сетевой стек обрабатывает sk_buff:
   - Ethernet → IP → TCP → сокет → приложение
```

**NAPI (New API) — избегаем interrupt storms:**

```c
// При очень высоком трафике: много прерываний → overhead
// NAPI: при первом прерывании отключаем дальнейшие прерывания NIC
// и переходим в polling режим (обрабатываем пачку пакетов)
// После обработки N пакетов или при пустой очереди — снова включаем прерывания

static int my_napi_poll(struct napi_struct *napi, int budget) {
    int work_done = 0;
    
    while (work_done < budget && rx_ring_has_packets()) {
        struct sk_buff *skb = get_next_packet();
        netif_receive_skb(skb);   // передать в сетевой стек
        work_done++;
    }
    
    if (work_done < budget) {
        napi_complete(napi);           // обработали всё — выключить polling
        enable_nic_interrupts();       // снова разрешить прерывания NIC
    }
    
    return work_done;
}
```

### 7.2 Жёсткий диск (HDD/SSD)

**NVMe (современный SSD):**

```
1. Driver создаёт Submission Queue (SQ) и Completion Queue (CQ)
2. Запрос чтения:
   - Driver помещает команду в SQ: {opcode: Read, LBA, length, PRP список}
   - PRP (Physical Region Page) список = scatter-gather для данных
   - Запись в doorbell register NVMe: «есть новая команда»
3. NVMe контроллер читает из SQ, выполняет:
   - Flash → DMA → RAM (по PRP адресам)
4. По завершении: запись в CQ + MSI-X прерывание
5. Драйвер читает CQ, освобождает буферы, уведомляет блочный уровень
```

**io_uring (Linux 5.1+) — почти zero-overhead I/O:**

```c
#include <liburing.h>

struct io_uring ring;
io_uring_queue_init(256, &ring, 0);  // 256 записей в очереди

// Асинхронное чтение без системного вызова для каждого I/O:
struct io_uring_sqe *sqe = io_uring_get_sqe(&ring);
io_uring_prep_read(sqe, fd, buf, len, offset);
sqe->user_data = (uint64_t)ctx;

io_uring_submit(&ring);  // один syscall для пакета операций

// ... CPU делает другую работу ...

struct io_uring_cqe *cqe;
io_uring_wait_cqe(&ring, &cqe);  // ждём завершения
// Или io_uring_peek_cqe для non-blocking check
```

### 7.3 Таймер (Timer Interrupt)

Системный таймер — основа планировщика ОС:

```
Linux: CONFIG_HZ=250 (типично)
Таймерное прерывание: 250 раз/сек = каждые 4 мс

При каждом timer interrupt:
1. do_timer() — обновить jiffies (счётчик тиков)
2. update_process_times() — обновить CPU-time текущего процесса
3. scheduler_tick() — проверить, пора ли вытеснить текущий процесс
4. run_local_timers() — выполнить истёкшие software timers
5. profile_tick() — профилировщик

Tickless kernel (CONFIG_NO_HZ_IDLE):
- Если ядро простаивает → таймер останавливается
- Следующее прерывание — только когда нужен реальный wakeup
- Экономия энергии на серверах/ноутбуках
```

---

## 8. Interrupt Latency и Real-Time системы

### 8.1 Источники задержки прерываний

```
IRQ signal → ... → ISR starts:

1. Hardware latency: распространение сигнала, APIC routing (~1-2 µs)
2. CPU pipeline flush: текущая инструкция должна завершиться
3. IF check: прерывания разрешены?
4. Context save: RFLAGS, CS, RIP → stack
5. IDT lookup + jump to ISR
6. ISR prologue: сохранение регистров (push rbx, push rbp, ...)

Типичная total interrupt latency на обычном Linux: 50-100 µs
С CONFIG_PREEMPT_RT патчем (Real-Time Linux): < 50 µs (99-percentile)
```

### 8.2 Latency в Linux (PREEMPT_RT)

Обычный Linux kernel — «preemptible at user/kernel boundary», но не в большинстве кода ядра. Real-Time патч делает ядро полностью вытесняемым:

```bash
# Проверить тип ядра:
uname -r
# 6.1.0-rt7 — RT ядро

# Измерить max interrupt latency:
cyclictest -p 99 -t 1 -n -i 1000 -l 100000
# Параметры: приоритет 99, 1 поток, nanosleep, период 1мс, 100000 итераций
# Вывод: T: 0 (123456) I:1000 C:100000 Min:2 Act:5 Max:28 (µs)
# Max latency 28 µs — приемлемо для большинства industrial RT задач
```

---

## 9. Связь прерываний с планировщиком

### 9.1 Wakeup от прерывания

```c
// Типичная схема: процесс ждёт данных от устройства
// 1. Процесс:
ssize_t result = read(fd, buf, len);
// → системный вызов → блокируется (TASK_INTERRUPTIBLE)
// → планировщик переключает на другой процесс

// 2. Устройство завершает I/O → ISR:
static irqreturn_t device_irq_handler(int irq, void *dev) {
    // ...обработка...
    wake_up(&dev->wait_queue);  // разбудить ожидающий процесс!
    return IRQ_HANDLED;
}

// 3. wake_up → планировщик помечает процесс TASK_RUNNING
// → при следующем context switch → возврат в read() с данными
```

### 9.2 Interrupt Coalescing

Сетевые карты поддерживают «прерывание через N пакетов» (interrupt coalescing):

```bash
# ethtool: настройка coalescing для eth0
ethtool -C eth0 rx-usecs 100    # не чаще одного прерывания каждые 100 µs
ethtool -C eth0 rx-frames 64    # или при накоплении 64 пакетов

# Компромисс: больше coalescing → выше throughput, но больше latency
# Меньше coalescing → ниже latency, но больше CPU overhead
```

---

## Заключение

Прерывания и DMA — два фундаментальных механизма, без которых современные ОС были бы невозможны:

**Прерывания** позволяют CPU не тратить время на ожидание медленных устройств. Иерархия (IRQ → APIC → IDT → ISR → top/bottom half) обеспечивает эффективную и безопасную обработку асинхронных событий.

**DMA** освобождает CPU от механического копирования данных между устройствами и памятью. Scatter-gather DMA и нулевое копирование позволяют сетевым стекам обрабатывать 100 Gbps без перегрузки CPU.

Для программиста системного уровня эти знания важны при:
- Написании драйверов (регистрация ISR, настройка DMA, буферы ring)
- Тюнинге производительности (affinity IRQ, NAPI, interrupt coalescing)
- Real-time системах (latency требования, PREEMPT_RT)
- Понимании почему I/O операции блокируют поток (системный вызов → блокировка → wakeup от ISR)

---

## Литература и источники

1. Linux Kernel Documentation. *Interrupt handling*. — https://www.kernel.org/doc/html/latest/core-api/genericirq.html

2. Corbet, J., Rubini, A., & Kroah-Hartman, G. (2005). *Linux Device Drivers* (3rd ed.). O'Reilly. — https://lwn.net/Kernel/LDD3/ (free online)

3. Intel Corporation. (2024). *Intel® 64 and IA-32 Architectures Software Developer's Manual, Vol. 3A: Chapter 6 — Interrupt and Exception Handling*. — https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html

4. Wikipedia. *Direct memory access*. — https://en.wikipedia.org/wiki/Direct_memory_access

5. Wikipedia. *Advanced Programmable Interrupt Controller*. — https://en.wikipedia.org/wiki/Advanced_Programmable_Interrupt_Controller

6. NVM Express. *NVM Express Base Specification 2.0*. — https://nvmexpress.org/specifications/

7. Axboe, J. (2019). *Efficient IO with io_uring*. — https://kernel.dk/io_uring.pdf

8. Linux NAPI documentation. — https://www.kernel.org/doc/html/latest/networking/napi.html

9. Torvalds, L., et al. Linux Kernel Source: `arch/x86/entry/entry_64.S` — точка входа прерываний x86-64.

10. OSDev Wiki. *Interrupts*. — https://wiki.osdev.org/Interrupts
