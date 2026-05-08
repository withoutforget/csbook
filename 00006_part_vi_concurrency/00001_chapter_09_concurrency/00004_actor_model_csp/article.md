# Actor model, CSP и каналы

## Введение

Традиционная многопоточность строится на разделяемой памяти и мьютексах: потоки видят одни и те же данные, и синхронизируются через блокировки. Этот подход работает, но порождает классические проблемы — deadlock, livelock, race conditions — которые крайне сложно обнаружить и воспроизвести. По мере роста системы сложность управления разделяемым состоянием растёт нелинейно.

Существуют два фундаментальных альтернативных подхода, устраняющих проблему разделяемого состояния. **Actor model** (модель акторов), предложенная Карлом Хьюиттом в 1973 году: акторы — изолированные единицы с приватным состоянием, общающиеся исключительно через асинхронные сообщения. **CSP** (Communicating Sequential Processes), формализованный Тони Хоаром в 1978 году: независимые процессы, синхронизирующиеся через каналы.

Оба подхода реализуют один принцип, выраженный знаменитой фразой из документации Go: *«Don't communicate by sharing memory; share memory by communicating»*. В этой главе мы разберём оба подхода, их реализации в реальных языках, и научимся выбирать между ними.

---

## 1. Actor Model

### 1.1 Концепция

Актор — это вычислительная единица с тремя характеристиками:
- **Приватное состояние** — никто не может напрямую прочитать или изменить
- **Почтовый ящик (mailbox)** — очередь входящих сообщений
- **Поведение** — реакция на сообщения

При получении сообщения актор может:
1. Создать новых акторов
2. Отправить сообщения другим акторам
3. Изменить своё поведение (состояние) для обработки следующего сообщения

Нет прямого вызова методов, нет разделяемой памяти, нет мьютексов.

### 1.2 Erlang/Elixir — классическая реализация

Erlang (1986, Ericsson) был создан для телекоммуникационных систем с требованием 99.9999999% uptime (менее 31 мс простоя в год). Модель акторов — основа языка.

```elixir
# Elixir

defmodule BankAccount do
  # Актор — это GenServer (Generic Server)
  use GenServer

  # API (client-side)
  def start_link(initial_balance) do
    GenServer.start_link(__MODULE__, initial_balance)
  end

  def deposit(pid, amount) do
    GenServer.cast(pid, {:deposit, amount})  # асинхронно
  end

  def withdraw(pid, amount) do
    GenServer.call(pid, {:withdraw, amount})  # синхронно — ждём ответа
  end

  def balance(pid) do
    GenServer.call(pid, :balance)
  end

  # Server callbacks (server-side — выполняются в процессе актора)
  @impl true
  def init(initial_balance) do
    {:ok, %{balance: initial_balance}}  # приватное состояние
  end

  @impl true
  def handle_cast({:deposit, amount}, state) do
    new_balance = state.balance + amount
    {:noreply, %{state | balance: new_balance}}
  end

  @impl true
  def handle_call({:withdraw, amount}, _from, state) do
    if state.balance >= amount do
      {:reply, {:ok, amount}, %{state | balance: state.balance - amount}}
    else
      {:reply, {:error, :insufficient_funds}, state}
    end
  end

  @impl true
  def handle_call(:balance, _from, state) do
    {:reply, state.balance, state}
  end
end

# Использование
{:ok, account} = BankAccount.start_link(1000)
BankAccount.deposit(account, 500)
{:ok, _} = BankAccount.withdraw(account, 200)
balance = BankAccount.balance(account)  # 1300
```

### 1.3 Supervision Trees — отказоустойчивость

Ключевая особенность Erlang/Elixir — философия «let it crash»: вместо сложной обработки ошибок, актор просто падает, а Supervisor автоматически перезапускает его:

```elixir
defmodule MyApp.Supervisor do
  use Supervisor

  def start_link(_init_arg) do
    Supervisor.start_link(__MODULE__, :ok, name: __MODULE__)
  end

  def init(:ok) do
    children = [
      # Если DatabaseWorker упадёт — перезапустить только его
      {DatabaseWorker, []},
      # Если CacheWorker упадёт — перезапустить только его
      {CacheWorker, []},
      # Если упадут 3 раза за 5 секунд — остановить всё дерево
      {WebHandler, []}
    ]

    opts = [
      strategy: :one_for_one,  # :one_for_one | :one_for_all | :rest_for_one
      max_restarts: 3,
      max_seconds: 5
    ]

    Supervisor.init(children, opts)
  end
end
```

Дерево супервизоров — иерархическая структура восстановления. Сбой на любом уровне изолирован и обрабатывается ближайшим супервизором.

### 1.4 Akka — акторы на JVM

```scala
// Scala + Akka
import akka.actor.typed._
import akka.actor.typed.scaladsl._

object Counter {
  sealed trait Command
  case class Increment(replyTo: ActorRef[Int]) extends Command
  case object GetValue extends Command
  case class GetResponse(value: Int)

  def apply(): Behavior[Command] = counting(0)

  private def counting(count: Int): Behavior[Command] =
    Behaviors.receiveMessage {
      case Increment(replyTo) =>
        val newCount = count + 1
        replyTo ! newCount
        counting(newCount)  // Новое поведение с новым состоянием
    }
}

// Запуск
val system = ActorSystem(Counter(), "counter-system")
// system ! Counter.Increment(...)
```

---

## 2. CSP (Communicating Sequential Processes)

### 2.1 Концепция

Тони Хоар в 1978 году предложил формальный язык для описания параллельных взаимодействий. Ключевые идеи:
- **Процессы** независимы и не разделяют память
- **Каналы** — именованные точки встречи для синхронизации
- Взаимодействие через канал — синхронное (оба должны быть готовы)

Разница с Actor model:
- В CSP **каналы именованы**, акторы анонимны
- CSP — синхронная передача (sender ждёт receiver), Actor — асинхронный mailbox
- CSP — акцент на структуре взаимодействия, Actor — на акторах как объектах

### 2.2 Go — goroutines и channels

Go — ближайшая к оригинальной идее Хоара реализация CSP в промышленном языке.

**Goroutine** — легковесный поток, управляемый Go runtime (M:N scheduling). Стартует со стека 2 КБ, масштабируется по необходимости:

```go
package main

import (
    "fmt"
    "sync"
)

func main() {
    var wg sync.WaitGroup
    
    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            fmt.Printf("Goroutine %d\n", id)
        }(i)
    }
    // 1000 горутин = ~2-8 МБ (vs ~8 ГБ для 1000 потоков ОС)
    wg.Wait()
}
```

**Channel** — типизированный канал:

```go
ch := make(chan int)        // unbuffered — синхронный
ch := make(chan int, 10)    // buffered — асинхронный, буфер 10
ch := make(chan<- int)      // send-only
ch := make(<-chan int)      // receive-only
```

### 2.3 Небуферизованные каналы — точка встречи

```go
package main

import "fmt"

func sum(nums []int, result chan<- int) {
    total := 0
    for _, n := range nums {
        total += n
    }
    result <- total  // Ждём, пока кто-то получит
}

func main() {
    nums := []int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
    result := make(chan int)  // Небуферизованный
    
    // Параллельно суммируем два среза
    go sum(nums[:5], result)
    go sum(nums[5:], result)
    
    x, y := <-result, <-result  // Получаем два значения
    fmt.Println(x + y)           // 55
}
```

### 2.4 Pipeline паттерн

```go
package main

import "fmt"

// Генератор чисел
func generate(nums ...int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for _, n := range nums {
            out <- n
        }
    }()
    return out
}

// Возводит в квадрат
func square(in <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for n := range in {
            out <- n * n
        }
    }()
    return out
}

// Фильтр — только чётные
func filter(in <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for n := range in {
            if n%2 == 0 {
                out <- n
            }
        }
    }()
    return out
}

func main() {
    // Пайплайн: generate → square → filter → print
    c := generate(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    c = square(c)
    c = filter(c)
    
    for v := range c {
        fmt.Println(v) // 4, 16, 36, 64, 100
    }
}
```

### 2.5 Select — мультиплексирование каналов

`select` позволяет ожидать события на нескольких каналах:

```go
package main

import (
    "fmt"
    "time"
)

func main() {
    ch1 := make(chan string)
    ch2 := make(chan string)
    
    go func() {
        time.Sleep(1 * time.Second)
        ch1 <- "from ch1"
    }()
    
    go func() {
        time.Sleep(2 * time.Second)
        ch2 <- "from ch2"
    }()
    
    // Ждём от любого канала, два раза
    for i := 0; i < 2; i++ {
        select {
        case msg := <-ch1:
            fmt.Println("Received:", msg)
        case msg := <-ch2:
            fmt.Println("Received:", msg)
        case <-time.After(3 * time.Second):
            fmt.Println("Timeout!")
        }
    }
}
```

**Таймаут через select**:

```go
func fetchWithTimeout(url string) (string, error) {
    resultCh := make(chan string, 1)
    errorCh := make(chan error, 1)
    
    go func() {
        resp, err := http.Get(url)
        if err != nil {
            errorCh <- err
            return
        }
        defer resp.Body.Close()
        body, _ := io.ReadAll(resp.Body)
        resultCh <- string(body)
    }()
    
    select {
    case result := <-resultCh:
        return result, nil
    case err := <-errorCh:
        return "", err
    case <-time.After(5 * time.Second):
        return "", fmt.Errorf("timeout after 5s")
    }
}
```

### 2.6 Fan-out и Fan-in

```go
// Fan-out: один producer → несколько workers
func fanOut(input <-chan int, numWorkers int) []<-chan int {
    outputs := make([]<-chan int, numWorkers)
    for i := 0; i < numWorkers; i++ {
        outputs[i] = worker(input)
    }
    return outputs
}

func worker(input <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for n := range input {
            out <- heavyCompute(n)
        }
    }()
    return out
}

// Fan-in: несколько sources → один channel
func merge(channels ...<-chan int) <-chan int {
    var wg sync.WaitGroup
    merged := make(chan int)
    
    output := func(c <-chan int) {
        defer wg.Done()
        for v := range c {
            merged <- v
        }
    }
    
    wg.Add(len(channels))
    for _, c := range channels {
        go output(c)
    }
    
    go func() {
        wg.Wait()
        close(merged)
    }()
    
    return merged
}
```

---

## 3. Сравнение Actor Model и CSP

| Характеристика | Actor Model | CSP (Go channels) |
|---------------|-------------|-------------------|
| Направление | Актор → Актор | Через именованный канал |
| Буферизация | Mailbox (обычно буферизован) | Может быть unbuffered |
| Синхронность | Асинхронная отправка | Синхронная (unbuffered) |
| Именование | Акторы имеют PID/ref | Каналы именованы |
| Отказоустойчивость | Supervision trees (Erlang) | Требует дополнительного кода |
| Состояние | Приватное у актора | Передаётся через каналы |
| Язык | Erlang, Elixir, Akka, Pony | Go, CSP-подобные |

### 3.1 Когда Actor Model

- Распределённые системы (акторы на разных машинах)
- Высокая отказоустойчивость (Supervision trees)
- Задачи типа «много объектов с состоянием» (игровые сущности, пользователи)
- Erlang/OTP для телекома, Akka для enterprise Java/Scala

### 3.2 Когда CSP/Go channels

- Пайплайны обработки данных
- Координация goroutines внутри одного процесса
- Задачи с явными точками синхронизации
- Когда важна простота и читаемость

---

## 4. Go: Практические паттерны

### 4.1 Done channel для отмены

```go
func longRunningTask(done <-chan struct{}, data <-chan int) <-chan int {
    results := make(chan int)
    go func() {
        defer close(results)
        for {
            select {
            case <-done:  // Получили сигнал отмены
                return
            case n, ok := <-data:
                if !ok {
                    return
                }
                results <- process(n)
            }
        }
    }()
    return results
}

// Использование
done := make(chan struct{})
data := generateData()
results := longRunningTask(done, data)

// Отменяем через 5 секунд
go func() {
    time.Sleep(5 * time.Second)
    close(done)  // Закрытие канала рассылает сигнал всем читателям
}()
```

### 4.2 Context — стандартный способ отмены в Go

```go
import (
    "context"
    "time"
)

func fetchData(ctx context.Context, url string) ([]byte, error) {
    req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
    if err != nil {
        return nil, err
    }
    
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, err  // ctx.Err() если отменён
    }
    defer resp.Body.Close()
    return io.ReadAll(resp.Body)
}

func main() {
    // Создаём context с таймаутом
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()  // Освобождаем ресурсы при любом выходе
    
    data, err := fetchData(ctx, "https://api.example.com/data")
    if err != nil {
        if ctx.Err() == context.DeadlineExceeded {
            fmt.Println("Request timed out")
        }
        return
    }
    fmt.Println(string(data))
}
```

### 4.3 Worker Pool

```go
package main

import (
    "fmt"
    "sync"
)

type Job struct {
    ID   int
    Data string
}

type Result struct {
    JobID  int
    Output string
}

func workerPool(numWorkers int, jobs <-chan Job, results chan<- Result) {
    var wg sync.WaitGroup
    
    for i := 0; i < numWorkers; i++ {
        wg.Add(1)
        go func(workerID int) {
            defer wg.Done()
            for job := range jobs {
                // Обрабатываем задание
                output := processJob(job)
                results <- Result{JobID: job.ID, Output: output}
            }
        }(i)
    }
    
    // Закрываем results когда все workers завершили
    go func() {
        wg.Wait()
        close(results)
    }()
}

func main() {
    jobs := make(chan Job, 100)
    results := make(chan Result, 100)
    
    // Запускаем пул из 5 workers
    go workerPool(5, jobs, results)
    
    // Отправляем работу
    for i := 0; i < 20; i++ {
        jobs <- Job{ID: i, Data: fmt.Sprintf("task-%d", i)}
    }
    close(jobs)  // Сигнализируем об окончании работы
    
    // Собираем результаты
    for r := range results {
        fmt.Printf("Job %d: %s\n", r.JobID, r.Output)
    }
}
```

---

## 5. Сравнение с mutex-based подходом

```go
// Вариант 1: Mutex-based
type SafeMap struct {
    mu sync.RWMutex
    m  map[string]int
}

func (sm *SafeMap) Get(key string) (int, bool) {
    sm.mu.RLock()
    defer sm.mu.RUnlock()
    v, ok := sm.m[key]
    return v, ok
}

func (sm *SafeMap) Set(key string, value int) {
    sm.mu.Lock()
    defer sm.mu.Unlock()
    sm.m[key] = value
}

// Вариант 2: Channel-based (Actor-style)
type MapRequest struct {
    key   string
    value int
    get   bool
    reply chan interface{}
}

type SafeMapActor struct {
    requests chan MapRequest
    m        map[string]int
}

func (a *SafeMapActor) run() {
    for req := range a.requests {
        if req.get {
            v, ok := a.m[req.key]
            if ok {
                req.reply <- v
            } else {
                req.reply <- nil
            }
        } else {
            a.m[req.key] = req.value
            req.reply <- nil
        }
    }
}

func (a *SafeMapActor) Get(key string) (int, bool) {
    reply := make(chan interface{}, 1)
    a.requests <- MapRequest{key: key, get: true, reply: reply}
    v := <-reply
    if v == nil {
        return 0, false
    }
    return v.(int), true
}
```

**Что лучше?** Зависит от паттерна доступа:
- Много параллельных чтений, редкие записи → `sync.RWMutex` (меньше overhead)
- Много операций на сложном состоянии → Actor/channel (проще рассуждать)
- Простые счётчики → `sync/atomic` (минимальный overhead)

---

## 6. Erlang/Elixir в production: пример чат-сервера

```elixir
defmodule ChatRoom do
  use GenServer

  # Каждая комната — отдельный актор
  def start_link(room_name) do
    GenServer.start_link(__MODULE__, %{name: room_name, users: %{}, messages: []},
                         name: {:global, {:room, room_name}})
  end

  # Клиентское API
  def join(room, user_pid, username) do
    GenServer.call({:global, {:room, room}}, {:join, user_pid, username})
  end

  def send_message(room, username, text) do
    GenServer.cast({:global, {:room, room}}, {:message, username, text})
  end

  # Серверные коллбеки
  def handle_call({:join, user_pid, username}, _from, state) do
    # Мониторим пользователя — узнаем если он отключится
    ref = Process.monitor(user_pid)
    new_users = Map.put(state.users, ref, {user_pid, username})
    {:reply, :ok, %{state | users: new_users}}
  end

  def handle_cast({:message, username, text}, state) do
    msg = %{from: username, text: text, time: DateTime.utc_now()}
    # Рассылаем всем пользователям комнаты
    Enum.each(state.users, fn {_ref, {pid, _name}} ->
      send(pid, {:new_message, msg})
    end)
    {:noreply, %{state | messages: [msg | state.messages]}}
  end

  # Обрабатываем отключение пользователя
  def handle_info({:DOWN, ref, :process, _pid, _reason}, state) do
    new_users = Map.delete(state.users, ref)
    {:noreply, %{state | users: new_users}}
  end
end
```

---

## Заключение

Actor model и CSP — два мощных подхода к конкурентности, устраняющих проблему разделяемой памяти. Оба реализуют принцип «общайся через сообщения, а не через память».

**Практические выводы**:

1. **Actor Model** (Erlang, Elixir, Akka): лучший выбор для высоконагруженных, отказоустойчивых систем с богатым состоянием. Supervision trees делают восстановление после ошибок декларативным.

2. **CSP/Go channels**: идеально для пайплайнов и координации горутин внутри одного процесса. Простота и явность.

3. **Unbuffered channels** — точка синхронизации. **Buffered channels** — декуплинг producer и consumer.

4. **`select`** — мощный инструмент для неблокирующего ожидания нескольких каналов одновременно.

5. **Mutex vs channels**: не религия, а инженерный выбор. Mutex хорош для simple shared state, channels — для координации и пайплайнов.

---

## Литература и источники

1. Hewitt, C., Bishop, P., Steiger, R. (1973). A universal modular ACTOR formalism for artificial intelligence. *IJCAI '73 Proceedings*.
2. Hoare, C. A. R. (1978). Communicating sequential processes. *Communications of the ACM*, 21(8), 666-677.
3. Hoare, C. A. R. (1985). *Communicating Sequential Processes*. Prentice Hall. https://www.cs.cmu.edu/~crary/819-f09/Hoare78.pdf
4. Armstrong, J. (2003). *Making Reliable Distributed Systems in the Presence of Software Errors*. Royal Institute of Technology, Stockholm. (Erlang thesis)
5. Go Blog. Share Memory By Communicating. https://go.dev/blog/codelab-share
6. Go Documentation. Effective Go — Concurrency. https://go.dev/doc/effective_go#concurrency
7. Akka Documentation. https://akka.io/docs/
8. Elixir Documentation. GenServer. https://hexdocs.pm/elixir/GenServer.html
9. Wikipedia. Actor model. https://en.wikipedia.org/wiki/Actor_model
10. Donovan, A., & Kernighan, B. (2015). *The Go Programming Language*. Addison-Wesley.
