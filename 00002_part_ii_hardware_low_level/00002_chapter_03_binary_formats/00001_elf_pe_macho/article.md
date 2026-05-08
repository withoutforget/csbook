# ELF (Linux), PE (Windows), Mach-O (macOS)

## Введение

Когда вы запускаете программу, операционная система должна понять, что это такое: где находится код, где данные, какие библиотеки нужны, с какого адреса начинать выполнение. Вся эта информация хранится в **формате исполняемого файла** — специальной бинарной структуре, которую ОС умеет читать и загружать в память.

Три основных формата: ELF (Executable and Linkable Format) на Linux/Unix, PE (Portable Executable) на Windows, Mach-O на macOS/iOS. Все три решают одну задачу — описать программу для загрузчика ОС, но с разными подходами, унаследованными из разных традиций.

Понимание форматов исполняемых файлов необходимо для: reverse engineering и анализа вредоносного кода, написания компиляторов и линковщиков, понимания динамической линковки и загрузки, отладки сложных проблем с памятью и сегфолтами, security-исследований (buffer overflow, PLT/GOT hijacking).

---

## 1. ELF — Executable and Linkable Format

### 1.1 История и применение

ELF был разработан в AT&T Unix System Laboratories и вошёл в стандарт System V ABI (1992). Сегодня это стандарт для Linux, BSD, Solaris, embedded-систем. ELF используется не только для исполняемых файлов, но и для:
- Разделяемых библиотек (.so)
- Объектных файлов (.o)
- Core dumps
- Kernel modules (.ko)

### 1.2 Структура ELF файла

```
ELF File Layout:
┌─────────────────────────┐ ← offset 0
│      ELF Header         │   52 байта (32-bit) / 64 байта (64-bit)
├─────────────────────────┤
│   Program Header Table  │   Описывает сегменты (для загрузчика)
├─────────────────────────┤
│      Sections           │   .text, .data, .bss, .rodata, ...
│      (содержимое)       │
├─────────────────────────┤
│  Section Header Table   │   Описывает секции (для линковщика)
└─────────────────────────┘ ← конец файла
```

### 1.3 ELF Header

```c
// ELF64 Header (64 байта):
typedef struct {
    uint8_t  e_ident[16];  // Magic: {0x7f,'E','L','F'}, Class, Data, Version...
    uint16_t e_type;       // ET_EXEC, ET_DYN, ET_REL, ET_CORE
    uint16_t e_machine;    // EM_X86_64 (62), EM_ARM (40), EM_AARCH64 (183)
    uint32_t e_version;    // EV_CURRENT = 1
    uint64_t e_entry;      // Точка входа (virtual address)
    uint64_t e_phoff;      // Offset Program Header Table
    uint64_t e_shoff;      // Offset Section Header Table
    uint32_t e_flags;      // Архитектурно-специфичные флаги
    uint16_t e_ehsize;     // Размер ELF Header (64)
    uint16_t e_phentsize;  // Размер одной записи PHT (56)
    uint16_t e_phnum;      // Число записей в PHT
    uint16_t e_shentsize;  // Размер одной записи SHT (64)
    uint16_t e_shnum;      // Число секций
    uint16_t e_shstrndx;   // Индекс секции с именами секций (.shstrtab)
} Elf64_Ehdr;
```

**e_ident магия:**
```
7f 45 4c 46  -- Magic: \x7fELF
02           -- EI_CLASS: 2 = ELFCLASS64 (64-bit)
01           -- EI_DATA: 1 = ELFDATA2LSB (little-endian)
01           -- EI_VERSION: 1 = current
00           -- EI_OSABI: 0 = System V
...
```

**e_type:**
- `ET_REL` (1) — relocatable (объектный файл .o)
- `ET_EXEC` (2) — исполняемый файл (статически слинкован)
- `ET_DYN` (3) — разделяемый объект (.so или PIE executable)
- `ET_CORE` (4) — core dump

### 1.4 Секции (Sections)

Секции — логические единицы содержимого для **линковщика**:

| Секция | Содержимое |
|--------|-----------|
| `.text` | Исполняемый код |
| `.data` | Инициализированные глобальные/статические переменные |
| `.bss` | Неинициализированные данные (Block Started by Symbol) — не занимают место в файле |
| `.rodata` | Константы только для чтения (строковые литералы, const) |
| `.symtab` | Таблица символов (имена функций и переменных) |
| `.strtab` | Строки для .symtab |
| `.shstrtab` | Имена самих секций |
| `.rela.text` | Relocations для .text |
| `.plt` | Procedure Linkage Table (динамическая линковка) |
| `.got` | Global Offset Table |
| `.got.plt` | GOT для PLT |
| `.dynamic` | Информация о динамическом линковщике |
| `.dynsym` | Таблица динамических символов |
| `.dynstr` | Строки для .dynsym |
| `.debug_*` | Отладочная информация DWARF |

```bash
# Просмотр секций:
readelf -S /usr/bin/ls

# Вывод (выбранные секции):
# [ 1] .interp           PROGBITS  ...  /lib64/ld-linux-x86-64.so.2
# [13] .text             PROGBITS  ...  ALLOC EXECINSTR
# [16] .rodata           PROGBITS  ...  ALLOC
# [24] .data             PROGBITS  ...  ALLOC WRITE
# [25] .bss              NOBITS    ...  ALLOC WRITE  ← нет места в файле!
# [29] .symtab           SYMTAB    ...
# [31] .strtab           STRTAB    ...
```

### 1.5 Сегменты (Segments / Program Headers)

Сегменты — физические группы содержимого для **загрузчика ОС**:

```bash
readelf -l /usr/bin/ls

# Elf file type is DYN (Position-Independent Executable file)
# Entry point 0x67d0
# There are 13 program headers, starting at offset 64
#
# Program Headers:
#   Type       Offset   VirtAddr       PhysAddr       FileSiz  MemSiz   Flg  Align
#   PHDR       0x000040 0x000000000040 0x000000000040 0x0002d8 0x0002d8 R    0x8
#   INTERP     0x000318 0x000000000318 0x000000000318 0x00001c 0x00001c R    0x1
#   LOAD       0x000000 0x000000000000 0x000000000000 0x003620 0x003620 R    0x1000
#   LOAD       0x004000 0x000000004000 0x000000004000 0x012011 0x012011 R E  0x1000
#   LOAD       0x016000 0x000000016000 0x000000016000 0x008670 0x008670 R    0x1000
#   LOAD       0x01ef30 0x00000001ff30 0x00000001ff30 0x001280 0x001598 RW   0x1000
#   DYNAMIC    0x01f0f8 0x000000020098 0x000000020098 0x000200 0x000200 RW   0x8
```

Ключевые типы сегментов:
- **LOAD:** загружается в память (флаги R/W/X)
- **INTERP:** путь к dynamic linker (`/lib64/ld-linux-x86-64.so.2`)
- **DYNAMIC:** информация для динамического линковщика
- **GNU_STACK:** указывает права стека (NX bit — нет выполнения)

### 1.6 Таблица символов

```bash
# Все символы:
nm /usr/bin/ls

# Только глобальные символы динамически слинкованной библиотеки:
nm -D /lib/x86_64-linux-gnu/libc.so.6 | head -20

# readelf с детальной информацией:
readelf --syms /usr/bin/cat

# Symbol table '.symtab':
#  Num:    Value          Size Type    Bind   Vis      Ndx Name
#    0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
#    1: 0000000000000318     0 SECTION LOCAL  DEFAULT    1
#   ...
#   49: 0000000000004060   106 FUNC    GLOBAL DEFAULT   14 main
```

**Type:** FUNC (функция), OBJECT (переменная), NOTYPE (метка)  
**Bind:** LOCAL (локальный), GLOBAL (видим для линковщика), WEAK (может быть переопределён)  
**Ndx:** номер секции; UND = undefined (нужен при линковке), ABS = абсолютный

### 1.7 Relocations

Объектные файлы (.o) содержат «заглушки» на адреса, которые неизвестны до линковки:

```bash
# Просмотр relocation-ов:
readelf -r main.o

# Relocation section '.rela.text':
# Offset          Info           Type     Sym. Value    Sym. Name + Addend
# 000000000013  000600000004 R_X86_64_PLT32 0000000000000000 printf - 4
# 000000000029  000500000004 R_X86_64_PLT32 0000000000000000 helper_func - 4
```

При линковке: линковщик находит реальные адреса символов и «патчит» заглушки.

---

## 2. Динамическая линковка: PLT и GOT

### 2.1 Проблема

Разделяемая библиотека (.so) загружается по произвольному адресу (ASLR). Адрес `printf` заранее неизвестен. Нужен механизм «отложенного» определения адресов.

### 2.2 PLT — Procedure Linkage Table

PLT — маленькие функции-«прыгалки» (thunks):

```asm
; Вызов printf из кода:
call printf@plt

; PLT[printf]:
printf@plt:
    jmp *[got.plt + PRINTF_OFFSET]   ; прыгаем по адресу в GOT
    push  <printf_reloc_index>        ; (первый вызов: адрес ещё не resolved)
    jmp  plt[0]                       ; вызываем resolver

; PLT[0] (resolver stub):
    push  *[got.plt + 8]              ; push link map
    jmp   *[got.plt + 16]             ; jmp resolver (_dl_runtime_resolve)
```

### 2.3 GOT — Global Offset Table

GOT — таблица адресов, заполняемая динамическим линковщиком:

```
Изначально: got.plt[printf] → PLT[printf + 6]  (возврат к push инструкции)

Первый вызов printf:
1. PLT[printf]: jmp *got.plt[printf] → попадаем в PLT[printf+6]
2. push reloc_index; jmp PLT[0] → resolver
3. _dl_runtime_resolve: находит реальный printf в libc
4. got.plt[printf] = &libc.printf  (патчит GOT!)
5. Прыгаем на реальный printf

Последующие вызовы:
1. PLT[printf]: jmp *got.plt[printf] → сразу libc.printf (2 инструкции overhead)
```

Это называется **lazy binding** — адреса разрешаются при первом вызове. Можно отключить через `LD_BIND_NOW=1` или `-z now` (eager binding).

### 2.4 GOT Overwrite — атака

GOT.PLT доступен для записи (RW сегмент). Buffer overflow, уязвимость форматной строки или другие уязвимости могут перезаписать запись в GOT и перенаправить вызов библиотечной функции на произвольный код.

Защита: RELRO (RELocation Read-Only):
- Partial RELRO: `.got` становится read-only после инициализации, `.got.plt` — нет
- Full RELRO: и `.got`, и `.got.plt` read-only (требует eager binding)

```bash
# Проверить защиты исполняемого файла:
checksec --file=/usr/bin/ls
# RELRO:    Full RELRO
# STACK CANARY: Canary found
# NX:       NX enabled
# PIE:      PIE enabled
# RPATH:    No RPATH
```

### 2.5 Исследование PLT/GOT

```bash
# Просмотр PLT:
objdump -d -M intel /usr/bin/ls | grep -A5 '<printf@plt>'

# Просмотр GOT:
objdump -R /usr/bin/ls | head -20
# DYNAMIC RELOCATION RECORDS
# OFFSET           TYPE              VALUE
# 0000000000003f28 R_X86_64_GLOB_DAT  __libc_start_main@GLIBC_2.2.5
# ...
# 0000000000004018 R_X86_64_JUMP_SLOT printf@GLIBC_2.2.5
```

---

## 3. PE — Portable Executable (Windows)

### 3.1 История и структура

PE формат разработан Microsoft (1993) на основе COFF (Common Object File Format). Используется для: .exe, .dll, .sys (драйверы), .ocx, .cpl.

```
PE File Layout:
┌─────────────────────────┐
│   MS-DOS Header         │  "MZ" magic, legacy DOS-заглушка
│   DOS Stub (16-bit)     │  "This program cannot be run in DOS mode"
├─────────────────────────┤
│   PE Signature          │  "PE\0\0" (0x50450000)
├─────────────────────────┤
│   COFF File Header      │  Machine, NumSections, TimeDateStamp...
├─────────────────────────┤
│   Optional Header       │  (не опциональный!) AddressOfEntryPoint,
│                         │  ImageBase, Subsystem, Data Directories
├─────────────────────────┤
│   Section Table         │  .text, .data, .rdata, .rsrc...
├─────────────────────────┤
│   Sections (содержимое) │
└─────────────────────────┘
```

### 3.2 PE Header

```c
// IMAGE_FILE_HEADER (COFF):
typedef struct {
    WORD  Machine;              // 0x8664 = AMD64, 0x014c = x86, 0xAA64 = ARM64
    WORD  NumberOfSections;
    DWORD TimeDateStamp;        // Unix timestamp сборки
    DWORD PointerToSymbolTable;
    DWORD NumberOfSymbols;
    WORD  SizeOfOptionalHeader;
    WORD  Characteristics;      // DLL, EXECUTABLE, LARGE_ADDRESS_AWARE...
} IMAGE_FILE_HEADER;

// IMAGE_OPTIONAL_HEADER64 (ключевые поля):
typedef struct {
    WORD  Magic;                // 0x010b = PE32, 0x020b = PE32+
    DWORD AddressOfEntryPoint;  // RVA (относительно ImageBase)
    ULONGLONG ImageBase;        // Предпочтительный адрес загрузки (0x140000000 для EXE)
    DWORD SectionAlignment;     // Выравнивание в памяти (4096 = 0x1000)
    DWORD FileAlignment;        // Выравнивание в файле (512 = 0x200)
    DWORD SizeOfImage;          // Полный размер в памяти
    DWORD SizeOfHeaders;
    DWORD CheckSum;
    WORD  Subsystem;            // 2=GUI, 3=CUI (console)
    WORD  DllCharacteristics;   // NX_COMPAT, DYNAMIC_BASE (ASLR), HIGH_ENTROPY_VA...
    // ...
    // Data Directories (16 штук):
    IMAGE_DATA_DIRECTORY DataDirectory[16];  // Import, Export, Resource, Relocation...
} IMAGE_OPTIONAL_HEADER64;
```

### 3.3 RVA (Relative Virtual Address)

В PE адреса указываются как RVA — относительно `ImageBase`. При загрузке: `Virtual Address = ImageBase + RVA`.

С ASLR (Vista+): ImageBase рандомизируется. В файле адреса — RVA, при загрузке пересчитываются через relocation table (`.reloc` секция).

### 3.4 Import Table и Export Table

**Import Table (IAT/ILT):**

```
kernel32.dll:
  CreateFile → 0x...
  ReadFile   → 0x...
ntdll.dll:
  NtCreateFile → 0x...
```

```c
// IMAGE_IMPORT_DESCRIPTOR:
typedef struct {
    DWORD OriginalFirstThunk;  // RVA → Import Lookup Table (имена)
    DWORD TimeDateStamp;       // 0 = не связан
    DWORD ForwarderChain;
    DWORD Name;                // RVA → имя DLL ("kernel32.dll")
    DWORD FirstThunk;          // RVA → Import Address Table (адреса функций)
} IMAGE_IMPORT_DESCRIPTOR;
```

**Export Table (для DLL):**
```c
typedef struct {
    DWORD Name;            // RVA → имя DLL
    DWORD Base;            // Начальный ordinal
    DWORD NumberOfFunctions;
    DWORD NumberOfNames;
    DWORD AddressOfFunctions;  // RVA → массив RVA функций
    DWORD AddressOfNames;      // RVA → массив RVA строк с именами
    DWORD AddressOfNameOrdinals; // RVA → массив ordinals
} IMAGE_EXPORT_DIRECTORY;
```

### 3.5 PE секции

| Секция | Аналог ELF | Содержимое |
|--------|-----------|-----------|
| `.text` | `.text` | Код |
| `.data` | `.data` | Инициализированные данные |
| `.rdata` | `.rodata` | Read-only данные, import/export tables |
| `.bss` | `.bss` | Неинициализированные данные |
| `.rsrc` | — | Ресурсы: иконки, строки, диалоги |
| `.reloc` | — | Base relocation table (для ASLR) |
| `UPX0`, `UPX1` | — | Упакованные секции (packer) |

```bash
# Анализ PE на Windows (PowerShell):
[System.Reflection.Assembly]::LoadFile("C:\path\to\file.exe")

# dumpbin (Visual Studio):
dumpbin /headers file.exe
dumpbin /imports file.exe
dumpbin /exports file.dll

# На Linux: PE Tools
wine dumpbin /headers file.exe
# или: python-pefile:
pip install pefile
python3 -c "import pefile; pe=pefile.PE('file.exe'); print(pe.dump_info())"
```

---

## 4. Mach-O (macOS/iOS)

### 4.1 Структура Mach-O

Mach-O — формат macOS/iOS, происходит от ядра Mach (CMU). Используется для: Mach-O executable, dylib (.dylib), .o, .bundle, .kext.

```
Mach-O Layout:
┌─────────────────────────┐
│      mach_header        │  magic, cputype, filetype, ncmds
├─────────────────────────┤
│   Load Commands         │  LC_SEGMENT_64, LC_DYLD_INFO, LC_SYMTAB...
│                         │  Описывают содержимое файла
├─────────────────────────┤
│   Segments и Sections   │  __TEXT, __DATA, __LINKEDIT...
└─────────────────────────┘
```

```c
struct mach_header_64 {
    uint32_t magic;      // 0xFEEDFACF = 64-bit Mach-O (little-endian)
                         // 0xCEFAEDFE = big-endian
    cpu_type_t cputype;  // CPU_TYPE_X86_64, CPU_TYPE_ARM64
    cpu_subtype_t cpusubtype;
    uint32_t filetype;   // MH_EXECUTE, MH_DYLIB, MH_BUNDLE
    uint32_t ncmds;      // Число load commands
    uint32_t sizeofcmds; // Суммарный размер load commands
    uint32_t flags;      // MH_PIE, MH_NO_HEAP_EXECUTION...
    uint32_t reserved;
};
```

### 4.2 Universal Binary (Fat Binary)

Уникальная особенность macOS — «толстые» бинарники, содержащие код для нескольких архитектур:

```bash
# Просмотр fat binary:
file /usr/bin/arch
# /usr/bin/arch: Mach-O universal binary with 2 architectures:
# [x86_64:Mach-O 64-bit executable x86_64] [arm64e:Mach-O 64-bit executable arm64e]

lipo -info /usr/bin/ls
# Architectures in the fat file: /usr/bin/ls are: x86_64 arm64e

# Извлечь одну архитектуру:
lipo -thin arm64e -output ls_arm64 /usr/bin/ls
```

### 4.3 Анализ Mach-O

```bash
# otool — основной инструмент анализа:
otool -h /usr/bin/ls           # заголовок
otool -l /usr/bin/ls           # все load commands
otool -L /usr/bin/ls           # зависимые библиотеки (аналог ldd)
otool -tv /usr/bin/ls          # дизассемблирование .text

# Символы:
nm -m /usr/bin/ls              # с Mach-O атрибутами
nm -g /usr/bin/ls              # только глобальные

# Современная альтернатива otool (macOS 12+):
llvm-objdump -macho --all-headers /usr/bin/ls
```

---

## 5. Инструменты анализа бинарных форматов

### 5.1 ELF инструменты

```bash
# readelf — всё о ELF:
readelf -a binary           # всё
readelf -h binary           # только заголовок
readelf -l binary           # program headers (сегменты)
readelf -S binary           # section headers
readelf -s binary           # символы
readelf -r binary           # relocations
readelf -d binary           # dynamic section

# objdump — дизассемблирование и анализ:
objdump -d binary           # дизассемблировать .text
objdump -D binary           # дизассемблировать все секции
objdump -M intel binary     # в синтаксисе Intel
objdump -x binary           # все заголовки
objdump -p binary           # private headers (dynamic info)

# strings — строки в бинарнике:
strings binary | grep -i password   # поиск интересных строк

# xxd / hexdump — сырые байты:
xxd binary | head -20

# ldd — зависимые библиотеки:
ldd /usr/bin/ls
# linux-vdso.so.1 (0x00007ffd...) 
# libselinux.so.1 => /lib/x86_64-linux-gnu/libselinux.so.1
# libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6

# file — определить тип файла по magic bytes:
file binary
# binary: ELF 64-bit LSB pie executable, x86-64, ...
```

### 5.2 Практика: анализ простой программы

```c
// test.c:
#include <stdio.h>
int global_init = 42;
int global_uninit;
const char message[] = "Hello, World!";

int add(int a, int b) { return a + b; }

int main() {
    printf("%s\n", message);
    printf("%d\n", add(3, 4));
    return 0;
}
```

```bash
gcc -o test test.c

# Где что лежит:
readelf -s test | grep -E 'global_init|global_uninit|message|add|main'
# ...
# FUNC    GLOBAL DEFAULT   14 add
# FUNC    GLOBAL DEFAULT   14 main
# OBJECT  GLOBAL DEFAULT   15 global_init   ← в .data (инициализировано)
# OBJECT  GLOBAL DEFAULT   26 global_uninit ← в .bss (не инициализировано)
# OBJECT  GLOBAL DEFAULT   16 message       ← в .rodata

# Размеры секций:
size test
#   text    data     bss     dec     hex filename
#   1234     568      12    1814     716 test
# .bss = 12 байт (4 байта global_uninit + выравнивание)
# .bss не занимает места в файле!

# Дизассемблирование add:
objdump -d -M intel test | grep -A 10 '<add>:'
# add:
#   push   rbp
#   mov    rbp, rsp
#   mov    DWORD PTR [rbp-0x4], edi  ; a
#   mov    DWORD PTR [rbp-0x8], esi  ; b
#   mov    edx, DWORD PTR [rbp-0x4]
#   mov    eax, DWORD PTR [rbp-0x8]
#   add    eax, edx
#   pop    rbp
#   ret
```

---

## 6. Security-аспекты форматов

### 6.1 PIE (Position Independent Executable)

```bash
# Non-PIE: загружается по фиксированному адресу (0x400000 для x86-64)
gcc -no-pie -o test test.c
readelf -h test | grep Type
# Type: EXEC (Executable file)
# Entry: 0x401040  ← фиксированный адрес!

# PIE: может загружаться по любому адресу (ASLR)
gcc -pie -fPIE -o test test.c
readelf -h test | grep Type
# Type: DYN (Position-Independent Executable file)
# Entry: 0x1040  ← RVA, реальный адрес рандомизируется
```

### 6.2 ASLR + PIE

```bash
# Убедиться что ASLR включён:
cat /proc/sys/kernel/randomize_va_space
# 2 = полная рандомизация (включая heap, stack, mmap)

# Без PIE: text сегмент НЕ рандомизируется даже с ASLR:
# ./non-pie: text всегда в 0x400000
# ./pie: text в случайном месте каждый раз

cat /proc/self/maps | grep r-xp  # посмотреть адрес кода
```

### 6.3 Stack Canary, NX, RELRO

```bash
# Проверить все защиты:
checksec --file=/usr/bin/ssh

# Full checksec output:
# [*] '/usr/bin/ssh'
#     Arch:     amd64-64-little
#     RELRO:    Full RELRO     ← GOT защищён от записи
#     Stack:    Canary found   ← canary против stack overflow
#     NX:       NX enabled     ← стек и куча не исполняемые
#     PIE:      PIE enabled    ← ASLR работает
#     FORTIFY:  Enabled        ← _FORTIFY_SOURCE: безопасные версии strcpy и т.д.
```

---

## 7. Сравнение форматов

| Характеристика | ELF | PE | Mach-O |
|---------------|-----|-----|--------|
| ОС | Linux/Unix | Windows | macOS/iOS |
| Magic | `\x7fELF` | `MZ`+`PE\0\0` | `FEEDFACF` |
| Единица загрузки | Сегмент (LOAD) | Секция | Сегмент (`__TEXT`) |
| Динам. линковка | PLT/GOT | IAT | Dyld stub |
| Lazy binding | Да | Нет (всегда eager) | Да |
| Multi-arch | Нет (отдельные файлы) | Нет | Fat binary |
| Debug info | DWARF | PDB (отдельный файл) | DWARF (в файле) |
| Ресурсы | Нет (отдельно) | `.rsrc` секция | `__DATA __const` |
| Инструменты | readelf, objdump | dumpbin, CFF Explorer | otool, MachOView |

---

## Заключение

Форматы исполняемых файлов — это «скелет» любой программы. Их понимание открывает несколько важных возможностей:

1. **Reverse engineering:** readelf/objdump/otool/IDA позволяют исследовать скомпилированный код без исходников.

2. **Безопасность:** понимание PLT/GOT объясняет атаки типа GOT overwrite. Понимание PIE/ASLR/NX помогает понять защиты.

3. **Линковка и загрузка:** знание секций и сегментов помогает отлаживать проблемы с линковкой, undefined symbols, multiple definitions.

4. **Оптимизация:** compiler/linker flags влияют на то, какие секции создаются, где размещаются данные, есть ли отладочная информация.

5. **Написание компиляторов и линковщиков:** понимание relocations и символьных таблиц необходимо для генерации корректного объектного кода.

---

## Литература и источники

1. System V Application Binary Interface. *AMD64 Architecture Processor Supplement*. — https://www.uclibc.org/docs/psABI-x86_64.pdf

2. Wikipedia. *Executable and Linkable Format*. — https://en.wikipedia.org/wiki/Executable_and_Linkable_Format

3. Wikipedia. *Portable Executable*. — https://en.wikipedia.org/wiki/Portable_Executable

4. Wikipedia. *Mach-O*. — https://en.wikipedia.org/wiki/Mach-O

5. Oracle/Sun. *Linker and Libraries Guide*. — https://docs.oracle.com/cd/E26502_01/html/E26507/

6. Microsoft. *PE Format*. — https://docs.microsoft.com/en-us/windows/win32/debug/pe-format

7. Apple. *Mach-O Programming Topics*. — https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/MachOTopics/

8. Lief project: Cross-platform binary analysis library. — https://lief.re/doc/stable/

9. pwntools documentation (CTF/security tool). — https://docs.pwntools.com/en/stable/

10. Phrack Magazine. *ELF Dynamic Linking Internals* (various issues). — http://phrack.org/
