# Архитектура фон Неймана и Гарвардская архитектура

## Введение

Современный компьютер — это реализация абстрактной модели. Два основных конкурирующих подхода к организации взаимодействия процессора и памяти — архитектура фон Неймана (1945) и Гарвардская архитектура (1944) — заложили фундамент, на котором построены все современные компьютерные системы.

---

## 1. Архитектура фон Неймана

В 1945 году Джон фон Нейман сформулировал принципы устройства компьютера в докладе «First Draft of a Report on the EDVAC». Эти принципы фундаментальны:

1. **Единая память** для программ и данных
2. **Последовательное выполнение**: инструкции читаются и выполняются по одной
3. **Хранимая программа**: программа находится в той же памяти, что и данные
4. **Двоичная логика**: всё кодируется в двоичной форме
5. **Программный счётчик (PC)**: специальный регистр, указывающий на следующую инструкцию

```
┌─────────────┐    Шина адреса/данных/управления    ┌──────────┐
│             │◄──────────────────────────────────►│          │
│   CPU       │                                     │ Память   │
│  ┌───────┐  │                                     │ (RAM)    │
│  │  ALU  │  │                                     │          │
│  └───────┘  │                                     │ Код      │
│  ┌───────┐  │                                     │ Данные   │
│  │Регис. │  │                                     │ Стек     │
│  └───────┘  │                                     │          │
└─────────────┘                                     └──────────┘
```

### Фон Нейманновское узкое место (bottleneck)

Ключевое ограничение: **одна шина** соединяет CPU и память. Процессор не может одновременно читать инструкцию и оперировать данными. Это ограничение производительности называется **фон Нейманновским узким местом** (Von Neumann bottleneck).

```python
# Симуляция простой фон-нейманновской машины
class VonNeumannMachine:
    """
    Упрощённая модель фон Нейманновской машины.
    Инструкции и данные в одной памяти.
    """
    
    def __init__(self, memory_size=256):
        self.memory = [0] * memory_size  # Единая память для кода и данных
        self.registers = {'A': 0, 'B': 0, 'PC': 0, 'SP': memory_size - 1}
        self.running = True
    
    def load_program(self, program, start_addr=0):
        """Загружаем программу в память"""
        for i, instruction in enumerate(program):
            self.memory[start_addr + i] = instruction
    
    def fetch(self):
        """Fetch: читаем инструкцию по PC"""
        instruction = self.memory[self.registers['PC']]
        self.registers['PC'] += 1
        return instruction
    
    def decode_execute(self, instruction):
        """Decode + Execute: интерпретируем инструкцию"""
        opcode = (instruction >> 12) & 0xF  # Старшие 4 бита — opcode
        operand = instruction & 0xFFF        # Младшие 12 бит — операнд
        
        if opcode == 0:   # HALT
            self.running = False
        elif opcode == 1: # LOAD A, [addr]
            self.registers['A'] = self.memory[operand]
        elif opcode == 2: # STORE [addr], A
            self.memory[operand] = self.registers['A']
        elif opcode == 3: # ADD A, [addr]
            self.registers['A'] += self.memory[operand]
        elif opcode == 4: # JUMP addr
            self.registers['PC'] = operand
    
    def run(self, max_cycles=1000):
        """Цикл fetch-decode-execute"""
        cycles = 0
        while self.running and cycles < max_cycles:
            instruction = self.fetch()     # Fetch
            self.decode_execute(instruction)  # Decode + Execute
            cycles += 1
        return cycles

# Программа: сложить числа в ячейках 100 и 101, записать результат в 102
machine = VonNeumannMachine()
machine.memory[100] = 10   # Данные
machine.memory[101] = 20   # Данные

# Код (упрощённый ассемблер):
# LOAD A, [100]  : A = mem[100] = 10
# ADD A, [101]   : A = A + mem[101] = 30
# STORE [102], A : mem[102] = A = 30
# HALT
program = [
    (1 << 12) | 100,  # LOAD A, 100
    (3 << 12) | 101,  # ADD A, 101
    (2 << 12) | 102,  # STORE 102, A
    (0 << 12) | 0,    # HALT
]
machine.load_program(program, start_addr=0)
machine.run()
print(f"Результат: {machine.memory[102]}")  # 30
```

---

## 2. Гарвардская архитектура

Гарвардская архитектура использует **разные шины и физически разделённые хранилища** для программ (инструкций) и данных.

```
┌─────────┐  Шина инструкций   ┌──────────────┐
│         │◄──────────────────►│ Память       │
│   CPU   │                    │ инструкций   │
│         │  Шина данных        └──────────────┘
│         │◄──────────────────►┌──────────────┐
└─────────┘                    │ Память       │
                               │ данных       │
                               └──────────────┘
```

Преимущества:
- Можно **одновременно** читать инструкцию и читать/писать данные
- Нет конфликтов на шине между кодом и данными
- Разные технологии памяти для кода (ROM/Flash) и данных (RAM)

Применяется в:
- **Микроконтроллеры** (AVR, PIC, ARM Cortex-M): Flash для кода, SRAM для данных
- **DSP-процессоры**: раздельные шины для конвейерной обработки сигналов
- **GPU**: отдельная структура для инструкций шейдеров и данных вершин

---

## 3. Модифицированная Гарвардская архитектура

Современные процессоры используют **модифицированную Гарвардскую архитектуру**: единое адресное пространство (фон Нейманн), но раздельные **кеши** для инструкций и данных.

```
            ┌──────────────────────────────────┐
            │              CPU                 │
            │  ┌──────────┐  ┌──────────────┐  │
            │  │  I-Cache │  │    D-Cache   │  │
            │  │(инструкц)│  │   (данные)   │  │
            │  └────┬─────┘  └──────┬───────┘  │
            │       └────────┬───────┘          │
            └────────────────┼──────────────────┘
                             │ Общая шина памяти
                        ┌────┴────┐
                        │   RAM   │
                        │(единое  │
                        │простр-во│
                        └─────────┘
```

```python
# Симуляция модифицированной Гарвардской архитектуры
class ModifiedHarvardCPU:
    """
    Единое адресное пространство, но раздельные I-cache и D-cache.
    """
    
    def __init__(self):
        self.ram = [0] * 65536          # Единая RAM (64K)
        self.icache = {}                 # Кеш инструкций (read-only)
        self.dcache = {}                 # Кеш данных
        self.icache_hits = 0
        self.dcache_hits = 0
        self.ram_accesses = 0
    
    def fetch_instruction(self, addr):
        """Fetch через I-Cache"""
        if addr in self.icache:
            self.icache_hits += 1
            return self.icache[addr]
        self.ram_accesses += 1
        value = self.ram[addr]
        self.icache[addr] = value        # Заполняем I-cache
        return value
    
    def read_data(self, addr):
        """Чтение данных через D-Cache"""
        if addr in self.dcache:
            self.dcache_hits += 1
            return self.dcache[addr]
        self.ram_accesses += 1
        value = self.ram[addr]
        self.dcache[addr] = value        # Заполняем D-cache
        return value
    
    def write_data(self, addr, value):
        """Запись данных (write-through в D-Cache)"""
        self.dcache[addr] = value
        self.ram[addr] = value           # Write-through в RAM
    
    def print_stats(self):
        total_icache = self.icache_hits + self.ram_accesses
        print(f"I-Cache hit rate: {self.icache_hits / max(1, total_icache):.1%}")
        print(f"RAM accesses: {self.ram_accesses}")

cpu = ModifiedHarvardCPU()

# Загружаем код в RAM
program_code = [0x01, 0x02, 0x03, 0x04]
for i, code in enumerate(program_code):
    cpu.ram[i] = code

# Симулируем 3 итерации цикла (повторное выполнение тех же инструкций)
for iteration in range(3):
    for addr in range(len(program_code)):
        cpu.fetch_instruction(addr)    # После 1-й итерации — кеш-хиты

cpu.print_stats()
```

---

## 4. Цикл fetch-decode-execute

Основа работы любого процессора — цикл выполнения инструкции:

```
1. FETCH    → Прочитать инструкцию из памяти по адресу PC
2. DECODE   → Определить тип операции и операнды
3. EXECUTE  → Выполнить операцию в ALU
4. MEMORY   → Обратиться к памяти (если нужно load/store)
5. WRITEBACK→ Записать результат в регистр
6. PC++     → Перейти к следующей инструкции (или по адресу перехода)
```

```python
class InstructionCycle:
    """Полный цикл выполнения инструкции (5-stage pipeline)"""
    
    STAGES = ['FETCH', 'DECODE', 'EXECUTE', 'MEMORY', 'WRITEBACK']
    
    def __init__(self):
        self.stage_times = {s: 0 for s in self.STAGES}
    
    def execute_instruction(self, instruction_type):
        """
        Моделирует время выполнения каждого этапа.
        instruction_type: 'alu', 'load', 'store', 'branch'
        """
        times = {
            'FETCH': 1,
            'DECODE': 1,
            'EXECUTE': 1,
            'MEMORY': 1 if instruction_type in ('load', 'store') else 0,
            'WRITEBACK': 1 if instruction_type != 'store' else 0,
        }
        total = sum(times.values())
        return total, times

# Сравнение без и с конвейером
n = 4  # Количество инструкций

# Без конвейера: инструкции выполняются последовательно
instructions = ['alu', 'load', 'alu', 'store']
total_no_pipeline = sum(execute_instruction(i)[0] for i in instructions
                        for execute_instruction in [InstructionCycle().execute_instruction])

# С конвейером (идеальный случай):
# После n инструкций: n + (stages - 1) тактов
stages = 5
total_pipeline = stages + (n - 1)  # Первая инструкция проходит все этапы

print(f"Без конвейера: {n * stages} тактов")  # 20
print(f"С конвейером:  {total_pipeline} тактов")  # 8
print(f"Ускорение: {n * stages / total_pipeline:.1f}x")  # 2.5x
```

---

## 5. Регистры и их роль

Регистры — это небольшое количество очень быстрой памяти внутри CPU. Они принципиально быстрее RAM:

| Уровень | Время доступа | Размер |
|---|---|---|
| Регистры | ~0 тактов | 32–512 штук $\times$ 8 байт |
| L1-кеш | 4–5 тактов | 32–64 КБ |
| L2-кеш | 12–20 тактов | 256 КБ – 1 МБ |
| L3-кеш | 30–60 тактов | 8–32 МБ |
| RAM | 200–400 тактов | ГБ |
| SSD | ~100 000 тактов | ТБ |

```python
# Практическое следствие: держите горячие данные в регистрах
# Компилятор делает это через register allocation

# Плохо: частый доступ к памяти
def sum_array_bad(arr):
    """Каждое обращение к result — потенциально к памяти"""
    result = [0]  # Список в heap, не регистр
    for x in arr:
        result[0] += x
    return result[0]

# Хорошо: локальная переменная — кандидат на регистр
def sum_array_good(arr):
    """Компилятор скорее всего поместит total в регистр"""
    total = 0  # Локальная переменная
    for x in arr:
        total += x
    return total

import timeit
arr = list(range(10**6))
print(timeit.timeit(lambda: sum_array_bad(arr), number=10))
print(timeit.timeit(lambda: sum_array_good(arr), number=10))
```

---

## 6. CISC vs RISC: архитектурные стратегии

### CISC (Complex Instruction Set Computing)

Много сложных инструкций, переменная длина инструкций, много режимов адресации. Пример: x86 (Intel/AMD).

Преимущества:
- Высокая плотность кода (программы занимают меньше байт)
- Обратная совместимость с программами 40-летней давности

### RISC (Reduced Instruction Set Computing)

Мало простых инструкций, фиксированная длина, load/store архитектура. Пример: ARM, RISC-V, MIPS.

Преимущества:
- Проще реализовать конвейер
- Меньше площадь кристалла (или больше регистров/кешей)
- Лучше масштабируется

```python
# x86 CISC: одна инструкция может делать много
# PUSH reg: 1) читает reg, 2) вычитает из ESP, 3) пишет в [ESP]
# Это три операции в одной инструкции

# RISC-V: три отдельные инструкции
# SUB sp, sp, 4    ; esp -= 4
# SW reg, 0(sp)    ; [sp] = reg
# (загрузка reg из памяти — отдельно)

# Современная реальность: x86 внутри декодирует инструкции в RISC-подобные «micro-ops»
# Внешне CISC, внутри RISC
```

---

## 7. Архитектура памяти: Stack и Heap

Адресное пространство процесса делится на сегменты:

```
Высокие адреса
┌──────────────────┐
│      Stack       │ ← растёт вниз (к меньшим адресам)
│ (стек вызовов)   │
├──────────────────┤
│                  │
│   Свободное      │
│   пространство   │
│                  │
├──────────────────┤
│      Heap        │ ← растёт вверх (к большим адресам)
│ (динамические    │
│  данные)         │
├──────────────────┤
│      BSS         │ (неинициализированные глобальные)
├──────────────────┤
│      Data        │ (инициализированные глобальные)
├──────────────────┤
│      Text        │ (машинный код)
└──────────────────┘
Низкие адреса
```

```python
import sys

# Фрейм стека создаётся при вызове функции
def show_frame_info():
    import inspect
    frame = inspect.currentframe()
    print(f"Функция: {frame.f_code.co_name}")
    print(f"Локальные переменные: {list(frame.f_locals.keys())}")

def outer():
    local_var = 42
    show_frame_info()
    
outer()

# sys.getrecursionlimit() — лимит глубины стека
print(f"Лимит рекурсии Python: {sys.getrecursionlimit()}")  # 1000

# Переполнение стека (Stack Overflow):
try:
    def infinite_recursion():
        return infinite_recursion()
    infinite_recursion()
except RecursionError as e:
    print(f"Stack overflow! {e}")
```

---

## 8. Практические следствия для программирования

### Принцип локальности

Фон Нейманновская архитектура с кешами эффективна только при **пространственной и временной локальности** доступа к памяти:

```python
import time
import numpy as np

n = 1000
matrix = np.random.rand(n, n)

# Пространственная локальность: доступ по строкам (row-major) — быстро
start = time.perf_counter()
row_sum = np.sum(matrix, axis=1)  # Читаем строки — кеш-дружественно
print(f"По строкам: {time.perf_counter() - start:.4f}с")

# Плохая локальность: доступ по столбцам — медленно
start = time.perf_counter()
col_sum = np.sum(matrix, axis=0)  # Читаем столбцы — cache miss!
print(f"По столбцам: {time.perf_counter() - start:.4f}с")

# Транспонирование для улучшения локальности
matrix_T = matrix.T.copy()  # Создаём физически строки из столбцов
start = time.perf_counter()
col_sum2 = np.sum(matrix_T, axis=1)  # Теперь строки!
print(f"После транспонирования: {time.perf_counter() - start:.4f}с")
```

---

## Заключение

Архитектура фон Неймана и её модификации определяют фундаментальные характеристики вычислительных систем:

- **Единая память** → возможность загружать произвольные программы, но узкое место на шине
- **Гарвардская архитектура** → параллельный доступ к коду и данным, широко в embedded
- **Модифицированная Гарвардская** → лучшее из обоих миров (раздельные кеши, единое адресное пространство)
- **Локальность доступа** → следствие архитектуры кешей, критична для производительности

Каждый раз, когда компилятор размещает переменную в регистре или когда ваш код даёт 100x ускорение просто от смены порядка обхода массива — это прямое следствие архитектуры, которую описал фон Нейман в 1945 году.

---

## Литература и источники

1. von Neumann, J. (1945). *First Draft of a Report on the EDVAC*. Moore School of Electrical Engineering, University of Pennsylvania. — Оригинальный документ.

2. Patterson, D. A., & Hennessy, J. L. (2017). *Computer Organization and Design RISC-V Edition*. Morgan Kaufmann. — Классика архитектуры компьютеров.

3. Hennessy, J. L., & Patterson, D. A. (2019). *Computer Architecture: A Quantitative Approach* (6th ed.). Morgan Kaufmann.

4. Tanenbaum, A. S. (2012). *Structured Computer Organization* (6th ed.). Pearson.

5. Drepper, U. (2007). What every programmer should know about memory. LWN. https://lwm.net/articles/250967 — Исчерпывающее руководство по иерархии памяти.

6. Aho, A. V., et al. (2006). *Compilers: Principles, Techniques, and Tools* (2nd ed.). Addison-Wesley. — Register allocation в компиляторах.
