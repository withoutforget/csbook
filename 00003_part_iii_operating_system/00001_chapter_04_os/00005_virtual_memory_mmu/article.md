# Виртуальная память, страницы, MMU, TLB

## Введение

В 1960-х годах программисты вручную управляли физической памятью: «моя программа занимает адреса с 0x1000 по 0x8000». Запустить две программы одновременно было сложно — они могли занять одни и те же адреса. Появление виртуальной памяти революционизировало программирование: теперь каждый процесс «думает», что он один в системе и имеет доступ ко всему адресному пространству.

Виртуальная память — это абстракция: каждый процесс имеет собственное виртуальное адресное пространство. Адрес 0x400000 в процессе A и адрес 0x400000 в процессе B — это разные физические адреса. MMU (Memory Management Unit) аппаратно транслирует виртуальные адреса в физические при каждом обращении к памяти. TLB (Translation Lookaside Buffer) кеширует переводы для скорости.

Виртуальная память обеспечивает: изоляцию процессов, позволяет программам быть больше RAM, упрощает загрузку и компоновку программ, лежит в основе механизма mmap (файлы как память).

---

## 1. Зачем нужна виртуальная память

### 1.1 Проблемы без виртуальной памяти

**Проблема 1: Конкуренция за адреса.**
Если каждый процесс использует физические адреса, два процесса, скомпилированные с одинаковыми базовыми адресами, не могут работать одновременно.

**Проблема 2: Фрагментация.**
После запуска и завершения нескольких программ память фрагментируется — много маленьких «дырок», но нет большого непрерывного куска для новой программы.

**Проблема 3: Безопасность.**
Один процесс может читать/записывать память другого процесса или ядра.

**Проблема 4: Размер программ.**
Программа не может быть больше физической памяти.

Виртуальная память решает все эти проблемы.

### 1.2 Принцип виртуальной памяти

```
Process A:              MMU Translation:         Physical Memory:
Virtual: 0x400000  ──┐                          ┌─ 0x100000 [Code A]
Virtual: 0x401000  ──┤─── Page Table A ─────────┤─ 0x101000 [Data A]
                      │                          │
Process B:            │                          │
Virtual: 0x400000  ──┐│                         │
Virtual: 0x401000  ──┤┴── Page Table B ─────────┤─ 0x200000 [Code B]
                                                 └─ 0x201000 [Data B]
```

Процессы A и B используют одинаковые виртуальные адреса (0x400000), но они маппируются на разные физические страницы. Полная изоляция.

---

## 2. Страницы и Page Table

### 2.1 Размер страницы

Память делится на блоки фиксированного размера — страницы. Стандартный размер: **4 KB (4096 байт)** на x86/ARM.

Почему 4 KB? Компромисс:
- Маленькие страницы → меньше внутренняя фрагментация (вы запросили 1 байт, не потратили 4MB)
- Большие страницы → меньше записей в page table, TLB эффективнее

**Huge Pages:**
- x86: 2 MB (large pages) и 1 GB (huge pages)
- Linux: **Transparent Huge Pages (THP)** — ядро автоматически объединяет страницы
- Применение: базы данных, HPC — уменьшают TLB miss rate

```bash
# Статус THP:
cat /sys/kernel/mm/transparent_hugepage/enabled
# [always] madvise never

# Выделить huge pages явно:
#include <sys/mman.h>
void *ptr = mmap(NULL, 2*1024*1024,
                 PROT_READ|PROT_WRITE,
                 MAP_PRIVATE|MAP_ANONYMOUS|MAP_HUGETLB,
                 -1, 0);
```

### 2.2 Page Table Entry (PTE)

Каждая запись в page table описывает одну страницу:

```
x86-64 Page Table Entry (64 бит):
Бит 0:    Present (P) — страница загружена в RAM
Бит 1:    Read/Write (R/W) — 0=read-only, 1=writable
Бит 2:    User/Supervisor (U/S) — 0=kernel-only, 1=user доступ
Бит 3:    Write Through (PWT) — cache write policy
Бит 4:    Cache Disable (PCD) — отключить кеш для страницы
Бит 5:    Accessed (A) — установлен MMU при первом обращении
Бит 6:    Dirty (D) — установлен MMU при записи
Бит 7:    Page Size (PS) — 1 для huge pages
Бит 8:    Global (G) — страница не вытесняется из TLB при смене CR3
Биты 9-11: Available — для ОС
Биты 12-51: Physical Page Frame Number (PFNP) — физический адрес
Биты 52-62: Available — для ОС
Бит 63:    No-Execute (NX/XD) — запрет выполнения (NX бит)
```

NX бит — ключевой элемент безопасности: страницы с данными не могут исполняться. Предотвращает атаки «shellcode в стек».

### 2.3 Многоуровневые Page Tables

Для 64-битного адресного пространства (2^64 = 18 экзабайт) страничная таблица размером 2^52 записей × 8 байт = 32 ПБ — нереально.

Решение — **многоуровневые page tables** (hierarchical paging):

**x86-64: 4-уровневые page tables:**

```
Virtual Address (48 бит используется):
[63..48]: знаковое расширение (canonical address)
[47..39]: PML4 index (9 бит, 512 записей)
[38..30]: PDPT index (9 бит, 512 записей)
[29..21]: PD index   (9 бит, 512 записей)
[20..12]: PT index   (9 бит, 512 записей)
[11..0]:  Page offset (12 бит = 4096 байт)

Трансляция:
CR3 (физический адрес PML4)
    │
    └─► PML4[VA[47..39]] → физический адрес PDPT
                               │
                               └─► PDPT[VA[38..30]] → PD
                                           │
                                           └─► PD[VA[29..21]] → PT
                                                       │
                                                       └─► PT[VA[20..12]] → Physical Page
                                                               + VA[11..0] = физический адрес байта
```

**5-уровневые page tables (x86-64, LA57):**
Поддерживаются с Cascade Lake (Intel 2019). Добавляет PML5 уровень → 57-bit virtual addresses → 128 ПБ адресного пространства. Linux поддерживает с 4.14.

**Размер page table:**

Каждый уровень — 512 записей × 8 байт = 4 KB (одна страница).
Для типичного процесса с несколькими гигабайтами памяти — несколько сотен KB на page tables.
Важно: страницы page table выделяются **по требованию** — не нужно хранить все 512^4 записей.

### 2.4 Трансляция адресов — пример

```python
# Python: разбор виртуального адреса x86-64
def parse_va(va):
    # Маски для каждого поля:
    offset  =  va & 0xFFF           # биты 11..0
    pt_idx  = (va >> 12) & 0x1FF   # биты 20..12
    pd_idx  = (va >> 21) & 0x1FF   # биты 29..21
    pdpt_idx= (va >> 30) & 0x1FF   # биты 38..30
    pml4_idx= (va >> 39) & 0x1FF   # биты 47..39
    
    print(f"VA = 0x{va:016X}")
    print(f"  PML4 index: {pml4_idx} (0x{pml4_idx:03X})")
    print(f"  PDPT index: {pdpt_idx} (0x{pdpt_idx:03X})")
    print(f"  PD   index: {pd_idx}   (0x{pd_idx:03X})")
    print(f"  PT   index: {pt_idx}   (0x{pt_idx:03X})")
    print(f"  Offset:     {offset} (0x{offset:03X})")

parse_va(0x00007FFF_ABCD_1234)
# VA = 0x00007FFFABCD1234
#   PML4 index: 255 (0x0FF)
#   PDPT index: 510 (0x1FE)
#   PD   index: 214 (0x0D6)
#   PT   index: 205 (0x0CD)
#   Offset:     564 (0x234)
```

---

## 3. MMU — Memory Management Unit

### 3.1 Роль MMU

MMU — аппаратный блок внутри CPU (или как отдельный чип в старых системах). Выполняет трансляцию адресов при **каждом** обращении к памяти:

- Загрузка инструкции (fetch): virtual IP → physical address
- Загрузка данных (load): virtual EA → physical address
- Запись данных (store): virtual EA → physical address

MMU также:
- Проверяет права доступа (U/S, R/W, NX) → Page Fault при нарушении
- Устанавливает биты Accessed и Dirty в PTE
- Управляет TLB

### 3.2 Page Fault

Page Fault — исключение #14 на x86, генерируемое MMU при:

1. **Present=0:** страница не в RAM (swap или не выделена) → ОС загружает страницу
2. **Нарушение прав:** запись в read-only, выполнение non-executable, user access to kernel → SIGSEGV или kernel bug
3. **Non-canonical address:** биты 63..48 не являются знаковым расширением → General Protection Fault

**Обработка page fault в Linux:**

```
MMU: exception #14 → ядро
ядро: do_page_fault() → __do_fault()
          │
          ├─ Найти VMA (Virtual Memory Area) по адресу
          │   vm_area_struct: {vm_start, vm_end, vm_flags, vm_file...}
          │
          ├─ Если нет VMA → SIGSEGV (invalid address)
          │
          ├─ Если VMA есть, проверить права (SIGSEGV если нарушение)
          │
          ├─ Определить тип page fault:
          │   ├─ Anonymous: выделить физическую страницу, заполнить нулями
          │   ├─ File-backed: прочитать из файла (mmap'd file)
          │   ├─ CoW: скопировать shared страницу
          │   └─ Swap: загрузить из swap
          │
          └─ Установить PTE, добавить в TLB, повторить инструкцию
```

### 3.3 /proc/self/maps — анализ адресного пространства

```bash
# Просмотр VMA (Virtual Memory Areas) процесса:
cat /proc/self/maps

# addr_start-addr_end  perms offset dev inode  path
# 55e8f4600000-55e8f4602000 r--p 00000000 08:01 123456 /bin/cat    ← ELF header
# 55e8f4602000-55e8f4607000 r-xp 00002000 08:01 123456 /bin/cat    ← .text (execute)
# 55e8f4607000-55e8f460a000 r--p 00007000 08:01 123456 /bin/cat    ← .rodata (read-only)
# 55e8f460b000-55e8f460c000 r--p 0000a000 08:01 123456 /bin/cat    ← .data (RW, пока COW)
# 55e8f460c000-55e8f460d000 rw-p 0000b000 08:01 123456 /bin/cat    ← .data (RW, private)
# 55e8f4892000-55e8f48b3000 rw-p 00000000 00:00 0 [heap]           ← heap
# 7f8c5d400000-7f8c5d428000 r--p 00000000 08:01 999001 libc.so.6   ← libc read-only
# 7f8c5d428000-7f8c5d5b0000 r-xp 00028000 08:01 999001 libc.so.6   ← libc code
# ...
# 7ffef5000000-7ffef5021000 rw-p 00000000 00:00 0 [stack]          ← stack
# 7ffef50fe000-7ffef5100000 r--p 00000000 00:00 0 [vvar]           ← kernel vars
# 7ffef5100000-7ffef5101000 r-xp 00000000 00:00 0 [vdso]           ← vDSO
```

**Флаги в perms:**
- `r` — read, `w` — write, `x` — execute, `p` — private (CoW), `s` — shared

### 3.4 mmap — файлы как память

```c
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

// Маппирование файла в память:
int fd = open("large_file.bin", O_RDONLY);
struct stat st;
fstat(fd, &st);

// MAP_SHARED: изменения видны другим / записываются в файл
// MAP_PRIVATE: изменения локальны (CoW) / файл не изменяется
void *data = mmap(NULL,             // ОС выберет адрес
                  st.st_size,       // размер
                  PROT_READ,        // права
                  MAP_SHARED,       // тип маппинга
                  fd,               // файловый дескриптор
                  0);               // offset в файле

// Теперь data[0], data[1]... — байты файла
// Ядро загружает страницы по требованию (demand paging!)
// Никакого явного чтения не нужно!

// Освободить:
munmap(data, st.st_size);
close(fd);
```

**Применения mmap:**
- Загрузка больших файлов без явного чтения
- IPC через MAP_SHARED + общий файл
- SQLite, PostgreSQL используют mmap для чтения данных
- Загрузчик ELF использует mmap для загрузки программы

---

## 4. TLB — Translation Lookaside Buffer

### 4.1 Проблема: каждое обращение = 4 обращения к памяти

Трансляция виртуального адреса через 4-уровневую page table требует 4 обращений к памяти (PML4, PDPT, PD, PT). Это в 4 раза медленнее!

Решение: TLB — кеш трансляций:

```
TLB Entry:
  Key:   {PCID, Virtual Page Number}
  Value: {Physical Page Frame Number, Protection bits (U/S, R/W, NX), Global}

TLB Hit:  VPN → PFN за 1 цикл
TLB Miss: 4 обращения к памяти → TLB fill → продолжение
```

### 4.2 TLB организация

Типичная организация TLB на современных процессорах:

| | L1 iTLB | L1 dTLB | L2 STLB |
|-|---------|---------|---------|
| Intel Skylake | 128 entries (4-way) | 64 entries (4-way) | 1536 entries (12-way) |
| AMD Zen 4 | 64 entries | 72 entries | 2048 entries |
| Huge Pages | 8 entries (2MB) | 32 entries (2MB) | 1024 entries (2MB) |

L1 TLB Miss → L2 STLB (Shared TLB). STLB Miss → page table walk (аппаратный).

### 4.3 TLB Miss

```bash
# Измерить TLB miss rate:
perf stat -e dTLB-loads,dTLB-load-misses,iTLB-loads,iTLB-load-misses ./program

# Пример вывода:
#  1,000,000,000   dTLB-loads
#        500,000   dTLB-load-misses    # 0.05% miss rate — хорошо
#                                      # > 1% — стоит применить huge pages

# TLB miss penalty: ~10-100 ns (страничная таблица в кеше) или 200+ ns (в RAM)
```

### 4.4 TLB Shootdown

При изменении page table (munmap, mprotect) — нужно инвалидировать TLB на всех ядрах, которые могли кешировать устаревшие записи:

1. CPU A: модифицирует PTE (munmap)
2. CPU A: посылает IPI (Inter-Processor Interrupt) всем CPU B, C, D
3. CPU B, C, D: выполняют `invlpg` или `invpcid` → инвалидируют запись в TLB
4. CPU A: завершает munmap

TLB shootdown — дорогая операция (IPI = прерывание каждому ядру). При частых munmap на многоядерных системах может стать узким местом.

```bash
# Счётчик TLB shootdowns:
cat /proc/interrupts | grep TLB
# TLB:  12345 23456 34567 45678  TLB shootdowns
```

### 4.5 PCID — Process Context ID

```
Без PCID: смена CR3 (context switch) → flush весь TLB
С PCID: каждый address space получает 12-битный ID
        TLB записи помечены {PCID, VPN}
        Смена CR3 НЕ очищает TLB — сохраняем записи другого процесса!

mov cr3, new_cr3 | (1 << 63)   # бит 63 = "не сбрасывать TLB"
```

Linux использует PCID с 4.14+. Экономия: уменьшает количество TLB miss после context switch.

---

## 5. Практика: анализ использования памяти

### 5.1 /proc/PID/status и /proc/PID/smaps

```bash
# Сводка по памяти:
cat /proc/self/status | grep -E 'VmSize|VmRSS|VmPeak'
# VmPeak:   234567 kB  ← пиковый виртуальный размер
# VmSize:   123456 kB  ← текущий виртуальный размер
# VmRSS:     45678 kB  ← Resident Set Size (реально в RAM)
# VmData:    12345 kB  ← .data + heap
# VmStk:       512 kB  ← stack

# Детальная информация по каждому VMA:
cat /proc/self/smaps | head -30
# 55e8f4600000-55e8f4602000 r--p 00000000 08:01 ... /bin/cat
# Size:               8 kB   ← виртуальный размер
# KernelPageSize:     4 kB
# MMUPageSize:        4 kB
# Rss:                8 kB   ← в RAM
# Pss:                4 kB   ← Proportional SS (разделённые страницы / процессов)
# Shared_Clean:       8 kB   ← разделяемые чистые (от файла)
# Shared_Dirty:       0 kB
# Private_Clean:      0 kB
# Private_Dirty:      0 kB
```

### 5.2 pmap

```bash
# Удобный вывод карты памяти:
pmap -x $(pgrep firefox) | head -30
# Address   Kbytes     RSS   Dirty Mode  Mapping
# 55a1000      4       4       0 r--p  firefox
# 55a2000    480     480       0 r-xp  firefox  ← .text
# ...
# Total:   12345678  456789  12345
```

### 5.3 valgrind massif — heap profiler

```bash
# Профилирование heap:
valgrind --tool=massif ./program
ms_print massif.out.* | head -50
# График использования heap во времени
```

---

## 6. Виртуальная память в Linux: детали реализации

### 6.1 VMA и vm_area_struct

```c
// Каждый регион адресного пространства описывается VMA:
struct vm_area_struct {
    struct mm_struct *vm_mm;     // обратная ссылка на процесс
    unsigned long vm_start;      // начало виртуального диапазона
    unsigned long vm_end;        // конец
    unsigned long vm_flags;      // VM_READ, VM_WRITE, VM_EXEC, VM_SHARED...
    
    const struct vm_operations_struct *vm_ops;  // fault handler и др.
    
    // Если memory-mapped file:
    struct file     *vm_file;    // ссылка на файл
    unsigned long    vm_pgoff;   // смещение в файле (в страницах)
    
    // Linked list для поиска:
    struct rb_node  vm_rb;       // в red-black tree mm->mm_rb
};
```

### 6.2 mprotect — изменение прав страниц

```c
#include <sys/mman.h>

// Сделать страницу исполняемой (JIT компиляторы):
void *code_page = mmap(NULL, 4096, PROT_READ|PROT_WRITE,
                       MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);

// Записать машинный код:
unsigned char shellcode[] = {
    0x48, 0x31, 0xc0,  // xor rax, rax
    0xc3               // ret
};
memcpy(code_page, shellcode, sizeof(shellcode));

// Сделать исполняемой (нельзя иметь WRITE+EXEC одновременно на строгих системах):
mprotect(code_page, 4096, PROT_READ|PROT_EXEC);

// Вызвать:
typedef long (*func_t)(void);
func_t f = (func_t)code_page;
long result = f();
```

### 6.3 ASLR — Address Space Layout Randomization

```bash
# ASLR рандомизирует базовые адреса при загрузке:
cat /proc/sys/kernel/randomize_va_space
# 2 = full ASLR (heap, stack, mmap, vDSO, vsyscall)

# Проверить ASLR в действии:
for i in {1..3}; do
    grep -m1 "stack" /proc/self/maps | awk '{print $1}'
done
# 7fff3a600000-7fff3a621000
# 7ffd8b300000-7ffd8b321000  ← другой адрес каждый раз!
# 7fffa9200000-7fffa9221000

# Отключить ASLR для одного процесса (для debugging):
setarch $(uname -m) --addr-no-randomize ./program
```

---

## Заключение

Виртуальная память — одна из важнейших абстракций в computing. Благодаря ей:

1. **Изоляция:** каждый процесс имеет своё адресное пространство. Ошибка в одном — не уничтожает другой.

2. **Demand paging:** страницы загружаются только при первом обращении. Можно «выделить» 10 GB, реально использовав 100 MB.

3. **Разделение библиотек:** libc загружается один раз в физическую память, но все процессы видят её по своим виртуальным адресам.

4. **mmap:** файлы как память. Ядро управляет кешированием и загрузкой — программисту не нужно явно читать.

5. **ASLR:** рандомизация адресов предотвращает атаки переполнения буфера, которые полагаются на фиксированные адреса.

TLB — критически важный элемент производительности. При многих случайных обращениях к памяти (large hash tables, graphs, pointer-chasing) TLB misses становятся узким местом. Huge pages (2MB) в 512 раз эффективнее используют TLB.

---

## Литература и источники

1. Drepper, U. (2007). *What Every Programmer Should Know About Memory*. — https://people.freebsd.org/~lstewart/articles/cpumemory.pdf

2. Kerrisk, M. (2010). *The Linux Programming Interface*. No Starch Press. — Главы 49-50: Virtual Memory Operations.

3. Bovet, D. P., & Cesati, M. (2005). *Understanding the Linux Kernel* (3rd ed.). O'Reilly. — Глава 2: Memory Addressing.

4. Wikipedia. *Virtual memory*. — https://en.wikipedia.org/wiki/Virtual_memory

5. Wikipedia. *Translation lookaside buffer*. — https://en.wikipedia.org/wiki/Translation_lookaside_buffer

6. Wikipedia. *Page table*. — https://en.wikipedia.org/wiki/Page_table

7. Intel. *Intel® 64 and IA-32 Architectures Software Developer's Manual, Vol. 3A: Chapter 4 — Paging*. — https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html

8. Linux Kernel Documentation. *Memory Management*. — https://www.kernel.org/doc/html/latest/admin-guide/mm/index.html

9. Gorman, M. (2004). *Understanding the Linux Virtual Memory Manager*. Prentice Hall. — https://www.kernel.org/doc/gorman/

10. Linux. `/proc/[pid]/maps` documentation. — https://man7.org/linux/man-pages/man5/proc.5.html
