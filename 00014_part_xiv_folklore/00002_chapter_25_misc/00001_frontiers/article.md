# Горизонты Computer Science: от квантовых компьютеров до формальных методов

Computer Science — живая наука. В то время как одни области стабилизировались и стали инженерной дисциплиной, другие находятся на переднем крае: здесь теория встречается с практикой, где новые идеи ломают старые парадигмы.

В этой статье — обзор нескольких таких горизонтов: областей, которые сегодня либо трансформируют индустрию, либо обещают сделать это в ближайшие годы. Это не исчерпывающий обзор — каждой теме можно посвятить книгу. Цель — показать карту: что существует, как связано, и куда смотреть.

## Формальные методы и верификация программ

### Проблема корректности программ

Дейкстра сказал: "Тестирование может показать наличие ошибок, но не их отсутствие." Ни тысяча тестов, ни идеальное покрытие не гарантируют отсутствие ошибок — они лишь говорят, что *эти конкретные сценарии* прошли.

**Формальная верификация** — математическое доказательство того, что программа соответствует спецификации.

### TLA+

TLA+ (Temporal Logic of Actions, Leslie Lamport, 1994) — язык для формальной спецификации и верификации систем. Не верификация кода — верификация *алгоритма* или *протокола*.

Amazon использует TLA+ для верификации DynamoDB, S3, EBS. Они обнаружили реальные баги в своих распределённых алгоритмах, которые тестирование не находило.

```tla
(* Спецификация банковского перевода *)
VARIABLES alice_balance, bob_balance, processing

TypeInvariant ==
  /\ alice_balance >= 0
  /\ bob_balance >= 0

Init ==
  /\ alice_balance = 100
  /\ bob_balance = 50
  /\ processing = FALSE

Transfer(amount) ==
  /\ ~processing
  /\ alice_balance >= amount
  /\ processing' = TRUE
  /\ alice_balance' = alice_balance - amount
  /\ bob_balance' = bob_balance + amount
  /\ processing' = FALSE

(* Инвариант: сумма не меняется *)
MoneyConservation == alice_balance + bob_balance = 150
```

TLC Model Checker проверяет все возможные состояния: если инвариант нарушается — находит контрпример.

### Coq и Proof Assistants

**Coq** — интерактивный помощник в доказательстве теорем. Весь компилятор ML **CompCert** написан на Coq и формально верифицирован: доказано, что он не вводит ошибок в скомпилированный код.

```coq
(* Теорема: сложение коммутативно для натуральных чисел *)
Theorem add_comm : forall n m : nat,
  n + m = m + n.
Proof.
  intros n m.
  induction n as [| n' IHn'].
  - simpl. rewrite <- plus_n_O. reflexivity.
  - simpl. rewrite -> IHn'. rewrite -> plus_n_Sm. reflexivity.
Qed.
```

**Lean 4** — современный proof assistant с более удобным синтаксисом, активно используется в математическом сообществе.

### Rust: типы как формальная спецификация

Система типов Rust с borrow checker — это форма формальной верификации, встроенная в компилятор:

```rust
fn main() {
    let s1 = String::from("hello");
    
    // Компилятор ДОКАЗЫВАЕТ в compile-time:
    // - s1 не используется после передачи
    // - Нет data races в concurrent коде
    // - Нет null pointer dereference
    // - Нет use-after-free
    
    let s2 = s1;  // s1 moved, теперь принадлежит s2
    
    // println!("{}", s1);  // Ошибка компиляции! s1 уже перемещён
    println!("{}", s2);     // OK
}

// Это формальная гарантия: если код компилируется — нет memory safety bugs
```

Borrow checker реализует упрощённую версию линейных типов (linear types), позволяя доказывать свойства безопасности памяти в compile time.

## CRDT: совместное редактирование без конфликтов

### Проблема

Google Docs, Figma, VS Code Live Share — все позволяют нескольким пользователям одновременно редактировать документ. Как разрешать конфликты, когда двое одновременно редактируют одно место?

Наивный подход — Last Write Wins — теряет данные.

### Operational Transformation (OT)

Google Docs использует OT (Operational Transformation): каждая операция трансформируется с учётом конкурентных операций.

```
Документ: "hello"

Пользователь A: insert("_world", position=5) → "hello_world"
Пользователь B одновременно: delete(position=0, length=1) → "ello"

После трансформации:
  A получает операцию B: delete(0,1) → применяем после "hello_world" → "ello_world"  
  B получает операцию A: insert("_world", position=4) → "ello_world"

Результат консистентен!
```

OT сложен в реализации, особенно для трёх и более участников одновременно.

### CRDT (Conflict-free Replicated Data Types)

CRDT — математически корректные структуры данных, где конфликты невозможны по определению.

Ключевое свойство: **strong eventual consistency** — любые два узла, получившие одинаковый набор операций, будут в одинаковом состоянии (независимо от порядка операций).

**Типы CRDT**:
- G-Counter (Grow-only Counter): только инкремент
- PN-Counter: инкремент и декремент через два G-Counter
- G-Set (Grow-only Set): только добавление
- 2P-Set: добавление и удаление через два G-Set
- LWW-Element-Set: Last Write Wins с timestamp
- OR-Set (Observed-Remove Set): удаление по уникальному тегу
- RGA (Replicated Growable Array): для текстовых документов

```python
# OR-Set CRDT: Set с поддержкой удаления

import uuid
from typing import TypeVar

T = TypeVar('T')

class ORSet:
    """
    Observed-Remove Set.
    Каждый элемент помечен уникальным тегом.
    Удаление удаляет конкретный тег, не весь элемент.
    """
    def __init__(self):
        # Хранимые: (элемент, тег)
        self._added: set = set()
        self._removed: set = set()
    
    def add(self, element: T) -> None:
        """Добавляем элемент с уникальным тегом."""
        tag = uuid.uuid4()
        self._added.add((element, tag))
    
    def remove(self, element: T) -> None:
        """Удаляем все текущие теги элемента."""
        tags_to_remove = {tag for (e, tag) in self._added if e == element}
        self._removed.update(tags_to_remove)
    
    def contains(self, element: T) -> bool:
        """Элемент есть если есть хоть один живой тег."""
        active = self._added - {(e, t) for (e, t) in self._added if t in self._removed}
        return any(e == element for (e, _) in active)
    
    def merge(self, other: 'ORSet') -> 'ORSet':
        """Merge двух реплик — детерминированный результат."""
        result = ORSet()
        result._added = self._added | other._added  # Union
        result._removed = self._removed | other._removed  # Union
        return result

# Демонстрация concurrent операций
replica_a = ORSet()
replica_b = ORSet()

# Оба знают об элементе "apple"
tag = uuid.uuid4()
replica_a._added.add(("apple", tag))
replica_b._added.add(("apple", tag))

# A добавляет "apple" снова (новый тег)
replica_a.add("apple")

# B удаляет "apple"
replica_b.remove("apple")

# Merge: A выиграл — у него есть тег которого нет в removed
merged = replica_a.merge(replica_b)
print(merged.contains("apple"))  # True! Новый тег A "выжил"
```

**Yjs** (JavaScript CRDT), **Automerge** — реальные библиотеки для совместного редактирования на основе CRDT.

## P2P сети и DHT

### BitTorrent и Distributed Hash Table

Классическая клиент-серверная архитектура имеет центральную точку отказа. P2P распределяет данные между участниками.

**DHT** (Distributed Hash Table) — распределённая хэш-таблица: ключ → узел, который хранит значение. Не один узел — каждый ключ "принадлежит" определённому диапазону.

Алгоритм **Kademlia** (2002, используется в BitTorrent, Ethereum, IPFS):

```python
# Kademlia: расстояние между ключами = XOR
def kademlia_distance(node_id: int, key: int) -> int:
    """XOR-расстояние в Kademlia."""
    return node_id ^ key

# Ближайший к key узел — тот, у которого минимальное XOR-расстояние
# Это создаёт логарифмическую сложность поиска: O(log N)

# k-bucket: каждый узел хранит несколько узлов для каждого 
# "расстояния" (бита XOR-расстояния)
```

**IPFS** (InterPlanetary File System) использует CID (Content Identifier) — SHA256 хэш содержимого:

```python
import hashlib
import json

def compute_cid(data: bytes) -> str:
    """Content-addressed identifier (упрощённо)."""
    digest = hashlib.sha256(data).hexdigest()
    return f"Qm{digest[:44]}"  # IPFS-подобный формат

# Уникальный адрес = хэш содержимого
# Если содержимое не изменилось — адрес не изменился
# Нельзя изменить файл, не изменив его адрес
data = b"Hello, decentralized world!"
cid = compute_cid(data)
print(f"CID: {cid}")
```

## Streaming и обработка потоков данных

### Проблема batch vs streaming

Традиционно: ETL (Extract, Transform, Load) — ночной batch-процесс. Обрабатываем данные вчерашнего дня сегодня.

Для бизнеса в реальном времени (fraud detection, personalization, monitoring) нужна обработка за миллисекунды.

### Apache Kafka как основа потоковой архитектуры

Kafka — распределённый журнал событий (event log). Записи хранятся неизменяемо, потребители читают с произвольного offset:

```python
from confluent_kafka import Producer, Consumer

# Продюсер: записываем события в Kafka
producer = Producer({'bootstrap.servers': 'kafka:9092'})

def order_created(order_id: str, user_id: int, amount: float):
    event = {
        "event_type": "order.created",
        "order_id": order_id,
        "user_id": user_id,
        "amount": amount,
        "timestamp": datetime.utcnow().isoformat()
    }
    producer.produce(
        topic='orders',
        key=order_id,    # Ключ гарантирует порядок для одного заказа
        value=json.dumps(event).encode(),
        callback=lambda err, msg: logger.error(err) if err else None
    )
    producer.flush()

# Потребитель: обрабатываем события
consumer = Consumer({
    'bootstrap.servers': 'kafka:9092',
    'group.id': 'fraud-detection',
    'auto.offset.reset': 'earliest'
})
consumer.subscribe(['orders'])

while True:
    msg = consumer.poll(timeout=1.0)
    if msg is None:
        continue
    event = json.loads(msg.value())
    check_for_fraud(event)
```

### Apache Flink: stateful stream processing

Flink — фреймворк для потоковой обработки с поддержкой состояния:

```python
# Flink Python API (PyFlink)
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table import StreamTableEnvironment

env = StreamExecutionEnvironment.get_execution_environment()
t_env = StreamTableEnvironment.create(env)

# Fraud detection: найти подозрительные транзакции
# (3+ транзакции с одного IP за 1 минуту)
t_env.execute_sql("""
    CREATE TABLE transactions (
        user_id BIGINT,
        ip_address VARCHAR,
        amount DECIMAL(10,2),
        event_time TIMESTAMP(3),
        WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
    ) WITH (
        'connector' = 'kafka',
        'topic' = 'transactions',
        'format' = 'json'
    )
""")

suspicious = t_env.execute_sql("""
    SELECT ip_address, COUNT(*) as tx_count, SUM(amount) as total_amount
    FROM transactions
    GROUP BY ip_address, TUMBLE(event_time, INTERVAL '1' MINUTE)
    HAVING COUNT(*) >= 3
""")
```

### Lambda и Kappa архитектуры

**Lambda Architecture** (Nathan Marz): batch layer (Hadoop MapReduce для исторических данных) + speed layer (Kafka Streams для real-time) + serving layer (merges оба).

**Kappa Architecture** (Jay Kreps): только streaming layer. Исторические данные — просто события в прошлом. Переобработка — переиграть Kafka топик с начала.

Kappa проще. Сегодня предпочтительна для большинства случаев.

## Встроенные системы и RTOS

### Мир без ОС

Embedded-системы часто работают "на голом железе" (bare metal) или с минимальной RTOS:

```c
// Bare metal: прямое управление регистрами (ARM Cortex-M)
#include "stm32f4xx.h"

int main(void) {
    // Включаем тактирование GPIO порта A
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    
    // Конфигурируем PA5 как output (LED)
    GPIOA->MODER |= GPIO_MODER_MODER5_0;
    GPIOA->MODER &= ~GPIO_MODER_MODER5_1;
    
    while (1) {
        // Мигаем LED
        GPIOA->ODR ^= (1 << 5);
        
        // Задержка (busy-wait — плохо, но просто)
        for (volatile int i = 0; i < 1000000; i++);
    }
}
```

### RTOS: FreeRTOS

FreeRTOS — самая популярная open-source RTOS для микроконтроллеров:

```c
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

QueueHandle_t sensor_queue;

// Task 1: считываем датчик каждые 100ms (higher priority)
void vSensorTask(void *pvParameters) {
    SensorData_t data;
    while (1) {
        data.temperature = read_temperature();
        data.humidity = read_humidity();
        data.timestamp = xTaskGetTickCount();
        
        // Не ждём если очередь заполнена (pdMS_TO_TICKS(0) = не блокироваться)
        xQueueSend(sensor_queue, &data, pdMS_TO_TICKS(0));
        
        vTaskDelay(pdMS_TO_TICKS(100));  // Ждём 100ms
    }
}

// Task 2: отправляем данные через UART
void vTransmitTask(void *pvParameters) {
    SensorData_t data;
    while (1) {
        // Блокируемся до появления данных в очереди
        if (xQueueReceive(sensor_queue, &data, portMAX_DELAY) == pdTRUE) {
            char buf[64];
            sprintf(buf, "T:%.1f H:%.1f\r\n", data.temperature, data.humidity);
            uart_transmit(buf, strlen(buf));
        }
    }
}

int main(void) {
    sensor_queue = xQueueCreate(10, sizeof(SensorData_t));
    
    xTaskCreate(vSensorTask, "Sensor", 128, NULL, 2, NULL);    // Priority 2
    xTaskCreate(vTransmitTask, "Transmit", 256, NULL, 1, NULL); // Priority 1
    
    vTaskStartScheduler();  // Запускаем RTOS scheduler
    // Сюда не вернёмся
}
```

**Детерминизм** — ключевое свойство RTOS. В медицинском оборудовании, автомобилях (ABS, airbag) задержка должна быть гарантированной. "Real-time" не значит "быстро" — значит "предсказуемо за максимальное время".

## Big Data: MapReduce и его потомки

### MapReduce

Google MapReduce (2004) — абстракция для параллельной обработки огромных данных на кластере.

```python
# Подсчёт слов — классический пример MapReduce

# Map: входной документ → пары (слово, 1)
def map_function(document_id: str, text: str):
    words = text.lower().split()
    for word in words:
        yield (word, 1)

# Reduce: сворачиваем все (слово, [1, 1, 1, ...]) → (слово, count)
def reduce_function(word: str, counts: list[int]):
    return (word, sum(counts))

# Hadoop/Spark делают это на тысячах машин
```

**Apache Spark** — следующее поколение: in-memory вычисления (в 100x быстрее Hadoop MapReduce), поддержка SQL, ML, streaming:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum, window

spark = SparkSession.builder \
    .appName("OrderAnalytics") \
    .getOrCreate()

# Загружаем данные (могут быть петабайты)
orders = spark.read.parquet("s3://data/orders/")

# Lazy evaluation: план построен, но не выполнен
result = orders \
    .filter(col("status") == "completed") \
    .groupBy("product_category") \
    .agg(
        count("*").alias("order_count"),
        sum("total_amount").alias("revenue")
    ) \
    .orderBy(col("revenue").desc())

# Выполняется только здесь — Spark оптимизирует план
result.show(20)

# Или пишем обратно в S3
result.write.parquet("s3://results/category_analytics/")
```

### Колоночные хранилища

Для аналитических запросов (OLAP) колоночное хранилище в разы эффективнее строчного (OLTP):

```
Строчное хранение (PostgreSQL):
Row 1: [id=1, name="Alice", country="US", amount=100]
Row 2: [id=2, name="Bob", country="UK", amount=200]

Запрос: SELECT SUM(amount) FROM orders WHERE country = "US"
Читает: ВСЕ поля ВСЕХ строк, хотя нужны только country и amount

Колоночное хранение (ClickHouse, Parquet):
Column id:      [1, 2, 3, ...]
Column name:    ["Alice", "Bob", ...]
Column country: ["US", "UK", "US", ...]  ← читаем только это
Column amount:  [100, 200, 150, ...]     ← и это

+ Отличное сжатие (одинаковые значения в одном столбце)
+ SIMD операции над колонками
```

**ClickHouse** (Яндекс, 2016) — колоночная СУБД для аналитики в реальном времени. 100 миллиардов строк, запросы за секунды.

## SSA и компиляторы: LLVM

### SSA (Static Single Assignment)

**SSA** (Static Single Assignment) — форма представления кода в компиляторе, где каждая переменная присваивается ровно один раз.

```
Обычный код:          SSA форма:
x = 1                 x₁ = 1
x = x + 2            x₂ = x₁ + 2
y = x * 3            y₁ = x₂ * 3
if cond:             if cond:
    x = x + 1           x₃ = x₂ + 1
y = x + y            x₄ = φ(x₃, x₂)   ← φ-функция: "одно из"
                     y₂ = x₄ + y₁
```

Зачем? SSA упрощает многие оптимизации:
- **Constant propagation**: если x₁ = 1, заменить все x₁ на 1
- **Dead code elimination**: если x₃ никогда не используется — удалить присваивание
- **Register allocation**: граф зависимостей очевиден

### LLVM: модульный компилятор

**LLVM** (Low Level Virtual Machine) — набор компиляторных инфраструктур.

```
Clang (C/C++) ┐
Rust          ├→ [Frontend → LLVM IR] → [Optimizer] → [Backend → машинный код]
Swift         ┘
Julia

LLVM IR — промежуточное представление в SSA-форме
```

LLVM IR (Intermediate Representation):
```llvm
; Функция на LLVM IR (SSA-форма)
define i32 @factorial(i32 %n) {
entry:
  %cmp = icmp eq i32 %n, 0
  br i1 %cmp, label %base_case, label %recursive

base_case:
  ret i32 1

recursive:
  %n_minus_1 = sub i32 %n, 1
  %sub_result = call i32 @factorial(i32 %n_minus_1)
  %result = mul i32 %n, %sub_result
  ret i32 %result
}
```

Rust, Swift, Julia, Kotlin Native, Zig — все используют LLVM для генерации кода. LLVM обеспечивает оптимизации (inlining, loop unrolling, vectorization) и поддержку множества архитектур (x86, ARM, RISC-V, WebAssembly).

## Квантовые вычисления: практические основы

### Модели квантовых вычислений

**Gate-based quantum computing** (IBM, Google, Rigetti): квантовые вентили (аналоги логических вентилей) применяются к кубитам.

**Quantum annealing** (D-Wave): решение задач оптимизации через минимизацию квантового гамильтониана. Менее универсален, но доступнее сейчас.

**Measurement-based** и **topological** — альтернативные модели.

### Ключевые концепции

**Суперпозиция**: кубит |ψ⟩ = α|0⟩ + β|1⟩, где |α|² + |β|² = 1.

**Запутанность** (Entanglement): состояние двух кубитов нельзя описать независимо.

**Интерференция**: усиление правильных ответов, погашение неправильных.

**Декогерентность**: взаимодействие с окружением разрушает квантовое состояние. Главный враг квантовых компьютеров.

### Qiskit: программирование квантовых компьютеров

```python
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import execute, Aer
from qiskit.visualization import plot_histogram

# Схема суперпозиции и измерения
qr = QuantumRegister(1, 'q')
cr = ClassicalRegister(1, 'c')
circuit = QuantumCircuit(qr, cr)

# Ворота Адамара: |0⟩ → (|0⟩ + |1⟩)/√2
circuit.h(qr[0])  # Суперпозиция

circuit.measure(qr[0], cr[0])  # Измерение (коллапс суперпозиции)

# Симуляция
simulator = Aer.get_backend('qasm_simulator')
job = execute(circuit, simulator, shots=1000)
result = job.result()
counts = result.get_counts()
print(counts)  # {'0': ~500, '1': ~500} — равновероятно!

# Алгоритм Гровера (поиск в неструктурированных данных)
# Квадратичное ускорение: O(√N) vs O(N) классически
from qiskit.algorithms import Grover, AmplificationProblem
from qiskit.circuit.library import PhaseOracle

oracle = PhaseOracle('(a & b) | c')  # Ищем a=1, b=1 или c=1
problem = AmplificationProblem(oracle)
grover = Grover(quantum_instance=simulator)
result = grover.amplify(problem)
```

### Квантовое превосходство и реальные задачи

Квантовые алгоритмы с доказанным преимуществом:
- **Шор**: факторизация за O((log N)³) vs классический O(exp((log N)^(1/3)))
- **Гровер**: поиск O(√N) vs O(N)
- **Квантовая симуляция**: молекулярная химия, разработка материалов

Практические применения (пока): оптимизация (logistics, finance), квантовая химия (разработка лекарств), криптография (QKD — Quantum Key Distribution).

Ограничения сегодня: ~1000 "шумных" кубитов (NISQ). Для запуска алгоритма Шора для RSA-2048 нужно ~4000 логических кубитов = ~4 миллиона физических с квантовой коррекцией ошибок. Это горизонт 10+ лет.

## Роботика и автономные системы

### ROS (Robot Operating System)

ROS — не операционная система, а middleware для роботов: pub-sub взаимодействие между узлами (нодами).

```python
# ROS 2 Python нода для управления роботом-манипулятором
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from geometry_msgs.msg import Twist

class ArmController(Node):
    def __init__(self):
        super().__init__('arm_controller')
        
        # Подписка на состояние суставов
        self.subscription = self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_callback,
            10
        )
        
        # Публикуем команды для контроллера
        self.publisher = self.create_publisher(
            Twist,
            '/cmd_vel',
            10
        )
        
        # Таймер для управления
        self.timer = self.create_timer(0.1, self.control_loop)
        self.current_joints = None
    
    def joint_callback(self, msg: JointState):
        self.current_joints = msg.position
    
    def control_loop(self):
        if self.current_joints is None:
            return
        
        # Вычисляем target velocity через inverse kinematics
        cmd = Twist()
        cmd.linear.x = compute_velocity(self.current_joints)
        self.publisher.publish(cmd)

def main():
    rclpy.init()
    controller = ArmController()
    rclpy.spin(controller)
    rclpy.shutdown()
```

### SLAM и Autonomous Navigation

**SLAM** (Simultaneous Localization and Mapping): робот строит карту окружения и одновременно определяет своё положение.

Современный стек для autonomous driving:
- LiDAR (точечные облака) + Camera + Radar → Sensor fusion
- Extended Kalman Filter или Particle Filter → Localization
- Occupancy grid или 3D map → Mapping
- A*, RRT (Rapidly-exploring Random Tree) → Path planning
- MPC (Model Predictive Control) → Motion execution

## DSP: обработка сигналов

### Преобразование Фурье и FFT

Дискретное Преобразование Фурье (DFT) — преобразование сигнала из временного домена в частотный. Вычислительная сложность: O(N²).

**FFT** (Fast Fourier Transform, Cooley-Tukey, 1965) — O(N log N).

```python
import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq

# Синтезируем сигнал из двух частот
sample_rate = 1000  # Гц
duration = 1.0      # секунд
t = np.linspace(0, duration, int(sample_rate * duration))

# Сигнал: 50 Гц + 120 Гц
signal = (
    np.sin(2 * np.pi * 50 * t) + 
    0.5 * np.sin(2 * np.pi * 120 * t)
)

# FFT: извлекаем частоты
frequencies = fftfreq(len(signal), 1/sample_rate)
amplitudes = np.abs(fft(signal))

# Видим пики на 50 Гц и 120 Гц
positive_freq_mask = frequencies >= 0
print(f"Dominant frequencies: {frequencies[positive_freq_mask][np.argsort(amplitudes[positive_freq_mask])[-5:]]}")
```

FFT используется везде: MP3/AAC (MDCT), JPEG (DCT), LTE/5G (OFDM), радары, медицинская визуализация (МРТ, ЭЭГ).

### Фильтры: FIR и IIR

```python
from scipy.signal import butter, filtfilt, firwin

# IIR фильтр Баттерворта: низкочастотный фильтр 100 Гц
b, a = butter(N=5, Wn=100, btype='low', fs=sample_rate)
filtered_iir = filtfilt(b, a, signal)  # Zero-phase filtering

# FIR фильтр: точный фазовый отклик
numtaps = 101  # Нечётное число
b_fir = firwin(numtaps, 100, fs=sample_rate)
filtered_fir = np.convolve(signal, b_fir, mode='same')
```

## Горизонты: что будет дальше

Несколько тенденций, которые определят Computer Science следующих 10 лет:

**Нейросимволические системы**: объединение нейросетей (обучение из данных) и символьных методов (логика, планирование). AlphaCode, Copilot — ранние примеры.

**Квантово-классические гибриды**: NISQ алгоритмы для оптимизации, запущенные на реальных IBM Quantum системах уже сейчас.

**Нейроморфные чипы**: Intel Loihi, IBM TrueNorth — спайковые нейронные сети для edge AI при минимальном потреблении.

**Пространственные вычисления**: Apple Vision Pro, Meta Quest — требуют новых парадигм UI, real-time 3D рендеринга, spatial audio.

**WebAssembly вне браузера**: WASI (WebAssembly System Interface) превращает WASM в универсальный container без Docker, работающий везде.

```rust
// Rust → WebAssembly: universal executable
#[no_mangle]
pub extern "C" fn greet(name: *const u8, len: u32) -> u32 {
    // Работает в браузере, Node.js, Cloudflare Workers, на сервере
    let name = unsafe { 
        std::str::from_utf8(std::slice::from_raw_parts(name, len as usize)).unwrap()
    };
    println!("Hello, {}!", name);
    0
}
```

**Formal verification в mainstream**: Дедуктивная верификация (Dafny, F*) выходит за пределы академии. Amazon уже верифицирует сетевые протоколы. Microsoft использует Dafny для критического кода.

## Литература

1. Lamport L. **Specifying Systems: The TLA+ Language and Tools for Hardware and Software Engineers**. Addison-Wesley, 2002. — TLA+ от автора.

2. Bertot Y., Castéran P. **Interactive Theorem Proving and Program Development: Coq'Art**. Springer, 2004.

3. Shapiro M. et al. **Conflict-free Replicated Data Types** // SSS 2011.

4. Dean J., Ghemawat S. **MapReduce: Simplified Data Processing on Large Clusters** // OSDI, 2004.

5. Lattner C., Adve V. **LLVM: A Compilation Framework for Lifelong Program Analysis** // CGO, 2004.

6. Zaharia M. et al. **Apache Spark: A Unified Engine for Big Data Processing** // CACM, 2016.

7. Shor P. **Algorithms for Quantum Computation: Discrete Logarithms and Factoring** // FOCS, 1994.

8. Quigley M. et al. **ROS: An Open-Source Robot Operating System** // ICRA Workshop, 2009.

9. Cooley J., Tukey J. **An Algorithm for the Machine Calculation of Complex Fourier Series** // Mathematics of Computation, 1965.

10. Brachmann E. et al. **DSAC: Learning 6DoF Camera Localization without 3D Points** // CVPR, 2017. — Пример современной SLAM-системы.

11. Preskill J. **Quantum Computing in the NISQ Era and Beyond** // Quantum, 2018. — https://quantum-journal.org/papers/q-2018-08-06-79/
