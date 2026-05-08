# WebSockets, SSE, gRPC

## Введение

HTTP/1.1 был разработан как протокол запрос-ответ: клиент спрашивает, сервер отвечает. Эта модель не подходит для задач реального времени — чата, live-обновлений, стриминга ответов LLM, совместного редактирования документов. Традиционное решение — polling (клиент периодически спрашивает «есть что-нибудь новое?») — расточительно и медленно.

Для двунаправленной коммуникации и серверных событий возникли WebSocket, Server-Sent Events (SSE) и gRPC. Каждый занимает свою нишу: WebSocket — для полнодуплексного обмена, SSE — для однонаправленного потока от сервера, gRPC — для высокопроизводительных RPC вызовов между сервисами.

---

## 1. WebSocket

### 1.1 Проблема: HTTP не поддерживает push

До WebSocket применялись обходные решения:

**Short polling**: клиент спрашивает каждые N секунд:
```javascript
// Плохо: много запросов, высокая задержка
setInterval(async () => {
    const r = await fetch('/api/messages');
    const msgs = await r.json();
    updateUI(msgs);
}, 1000);
```

**Long polling**: сервер держит соединение открытым до появления данных:
```javascript
async function longPoll() {
    const r = await fetch('/api/messages?wait=true');  // Сервер ждёт данных
    const msgs = await r.json();
    updateUI(msgs);
    longPoll();  // Сразу запрашиваем снова
}
```

Оба подхода: HTTP overhead, задержка, масштабирование плохое.

### 1.2 WebSocket Handshake

WebSocket (RFC 6455) начинается как HTTP, затем «апгрейдится»:

```http
GET /chat HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
```

Сервер отвечает:
```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

Ключ `Sec-WebSocket-Accept` = Base64(SHA1(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))

После 101 — соединение TCP остаётся открытым, но уже не HTTP. Это WebSocket.

### 1.3 WebSocket фреймы

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├─┬─────────┬─┬───────────────┬───────────────────────────────────┤
│F│ RSV1-3  │M│  Opcode (4)  │ Payload Length (7, 16, or 64 bit) │
│I│         │A│               │                                   │
│N│         │S│               │                                   │
│ │         │K│               │                                   │
└─┴─────────┴─┴───────────────┴───────────────────────────────────┘
```

**Opcodes**:
- `0x0` CONTINUATION: продолжение фрагментированного сообщения
- `0x1` TEXT: UTF-8 текст
- `0x2` BINARY: бинарные данные
- `0x8` CLOSE: закрытие соединения
- `0x9` PING: проверка живости
- `0xA` PONG: ответ на ping

**Маскировка**: клиент → сервер: данные должны быть замаскированы (XOR с 4-байтовым ключом). Сервер → клиент: без маскировки.

### 1.4 WebSocket в Python (websockets)

**Сервер**:
```python
import asyncio
import websockets
import json
from typing import Set

# Множество активных соединений
connected_clients: Set[websockets.WebSocketServerProtocol] = set()

async def handler(websocket: websockets.WebSocketServerProtocol, path: str):
    """Обработчик WebSocket соединения."""
    connected_clients.add(websocket)
    client_id = id(websocket)
    print(f"Client {client_id} connected. Total: {len(connected_clients)}")
    
    try:
        async for message in websocket:
            # Получаем сообщение
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                data = {'text': message}
            
            print(f"From {client_id}: {data}")
            
            # Рассылаем всем подключённым (broadcast)
            broadcast_msg = json.dumps({
                'from': client_id,
                'data': data,
            })
            
            # Отправляем всем кроме отправителя
            await asyncio.gather(*[
                client.send(broadcast_msg)
                for client in connected_clients
                if client != websocket
            ], return_exceptions=True)
            
    except websockets.exceptions.ConnectionClosed:
        print(f"Client {client_id} disconnected")
    finally:
        connected_clients.discard(websocket)

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("WebSocket server running on ws://localhost:8765")
        await asyncio.Future()  # Ждём бесконечно

asyncio.run(main())
```

**Клиент**:
```python
import asyncio
import websockets
import json

async def websocket_client():
    uri = "ws://localhost:8765"
    
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")
        
        # Отправляем сообщения
        await websocket.send(json.dumps({"type": "hello", "text": "World"}))
        
        # Получаем ответы асинхронно
        async for message in websocket:
            data = json.loads(message)
            print(f"Received: {data}")
            
            # Можем ответить
            if data.get('type') == 'ping':
                await websocket.send(json.dumps({"type": "pong"}))

asyncio.run(websocket_client())
```

**JavaScript клиент** (браузер):
```javascript
const ws = new WebSocket('ws://localhost:8765');

ws.onopen = () => {
    console.log('Connected!');
    ws.send(JSON.stringify({type: 'hello', text: 'World'}));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};

ws.onclose = (event) => {
    console.log(`Closed: code=${event.code}, reason=${event.reason}`);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

// Ping/Pong для keepalive
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'ping'}));
    }
}, 30000);
```

### 1.5 Применение WebSocket

- **Чаты и мессенджеры**: Discord, Slack
- **Collaborative editing**: Google Docs real-time
- **Финансовые тикеры**: real-time цены
- **Игры**: multiplayer с минимальной задержкой
- **Мониторинг**: live метрики, логи
- **Совместные инструменты**: figma, miro

---

## 2. Server-Sent Events (SSE)

### 2.1 Концепция

SSE — однонаправленный поток от сервера к клиенту через обычный HTTP. Проще WebSocket, достаточен когда только сервер отправляет данные:

```
Браузер                    Сервер
  |                           |
  |--- GET /events ---------->|  Один HTTP запрос
  |                           |
  |<-- HTTP 200 Content-Type: text/event-stream
  |<-- data: first message\n\n
  |<-- data: second message\n\n   (может пройти долго)
  |<-- event: update\n
  |    data: {"value": 42}\n\n
  |                           |
  |<-- (соединение открыто бесконечно)
```

### 2.2 Формат SSE

```
data: Simple text message\n\n

event: custom-event\n
data: {"key": "value"}\n\n

id: 123\n
data: Message with ID\n\n

retry: 5000\n                     // Переподключиться через 5 сек при обрыве
data: Message with retry hint\n\n
```

- Поле `data:` — данные события
- Поле `event:` — тип события (по умолчанию 'message')
- Поле `id:` — ID события (для восстановления после обрыва)
- Поле `retry:` — таймаут переподключения в мс
- Два `\n` — конец события

### 2.3 SSE сервер на Python (FastAPI)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json
import time

app = FastAPI()

async def event_generator():
    """Генератор событий для SSE."""
    counter = 0
    while True:
        # Форматируем SSE сообщение
        data = json.dumps({"count": counter, "time": time.time()})
        
        # Стандартный формат SSE
        yield f"id: {counter}\n"
        yield f"event: update\n"
        yield f"data: {data}\n"
        yield "\n"  # Пустая строка = конец события
        
        counter += 1
        await asyncio.sleep(1)

@app.get("/events")
async def stream_events():
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Отключить nginx буферизацию
        }
    )

# Стриминг ответа LLM (главный use case 2024):
async def llm_response_generator(prompt: str):
    """Имитация стриминга ответа языковой модели."""
    words = f"This is a streaming response to: {prompt}".split()
    for word in words:
        yield f"data: {json.dumps({'token': word + ' '})}\n\n"
        await asyncio.sleep(0.1)
    yield f"data: [DONE]\n\n"

@app.get("/llm-stream")
async def llm_stream(prompt: str = "Hello"):
    return StreamingResponse(
        llm_response_generator(prompt),
        media_type="text/event-stream"
    )
```

### 2.4 SSE клиент в браузере (EventSource API)

```javascript
// EventSource — встроенный API браузера для SSE
const source = new EventSource('/events');

// Стандартное событие 'message'
source.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};

// Кастомное событие
source.addEventListener('update', (event) => {
    const data = JSON.parse(event.data);
    document.getElementById('counter').textContent = data.count;
});

source.onerror = (error) => {
    console.error('SSE error:', error);
    // EventSource автоматически переподключается!
};

source.onopen = () => {
    console.log('SSE connection opened');
};

// Закрыть соединение
// source.close();

// Стриминг LLM ответа:
async function streamLLM(prompt) {
    const source = new EventSource(`/llm-stream?prompt=${encodeURIComponent(prompt)}`);
    let output = '';
    
    source.addEventListener('message', (event) => {
        if (event.data === '[DONE]') {
            source.close();
            return;
        }
        const token = JSON.parse(event.data).token;
        output += token;
        document.getElementById('output').textContent = output;
    });
}
```

### 2.5 Когда использовать SSE

- **Стриминг LLM ответов** (ChatGPT, Claude используют SSE)
- **Live notifications** (новые сообщения, обновления статуса)
- **Прогресс операций** (загрузка файлов, обработка)
- **Биржевые котировки** (только сервер → клиент)
- **Логи в реальном времени**

**SSE vs WebSocket**:
| | SSE | WebSocket |
|-|-----|-----------|
| Направление | Только сервер → клиент | Двусторонний |
| Протокол | HTTP | Отдельный WS |
| Автопереподключение | Да (встроено) | Нет (нужно писать) |
| Proxy/firewall | Лучше (HTTP) | Сложнее |
| Браузерная поддержка | Отличная | Отличная |

---

## 3. gRPC

### 3.1 Что такое gRPC

gRPC — высокопроизводительный RPC (Remote Procedure Call) фреймворк от Google. Работает поверх HTTP/2, использует Protocol Buffers для сериализации.

**Зачем**: межсервисное взаимодействие в микросервисной архитектуре. По сравнению с REST JSON:
- Быстрее (бинарная сериализация, HTTP/2 мультиплексирование)
- Строгая схема (contract-first)
- Автогенерация клиентского кода для 10+ языков
- Поддержка streaming

### 3.2 Protocol Buffers

Определяем контракт в `.proto` файле:

```protobuf
// user_service.proto
syntax = "proto3";

package user;

option go_package = "./proto/user";

// Сообщение — определение структуры данных
message User {
    int64 id = 1;
    string name = 2;
    string email = 3;
    repeated string roles = 4;  // Список строк
    UserStatus status = 5;
}

enum UserStatus {
    ACTIVE = 0;
    INACTIVE = 1;
    BANNED = 2;
}

message GetUserRequest {
    int64 user_id = 1;
}

message CreateUserRequest {
    string name = 1;
    string email = 2;
}

// Сервис — набор RPC методов
service UserService {
    // Unary RPC (один запрос → один ответ)
    rpc GetUser(GetUserRequest) returns (User);
    
    // Server streaming (один запрос → поток ответов)
    rpc ListUsers(ListUsersRequest) returns (stream User);
    
    // Client streaming (поток запросов → один ответ)
    rpc BulkCreate(stream CreateUserRequest) returns (BulkCreateResponse);
    
    // Bidirectional streaming (поток ↔ поток)
    rpc Chat(stream ChatMessage) returns (stream ChatMessage);
}

message ListUsersRequest {
    int32 page_size = 1;
    string page_token = 2;
}

message BulkCreateResponse {
    int32 created_count = 1;
    repeated string errors = 2;
}

message ChatMessage {
    string user_id = 1;
    string text = 2;
    int64 timestamp = 3;
}
```

### 3.3 gRPC сервер на Python

```python
import grpc
from concurrent import futures
import time
import user_pb2
import user_pb2_grpc

# Имплементация сервиса
class UserServicer(user_pb2_grpc.UserServiceServicer):
    
    def __init__(self):
        # In-memory хранилище (для примера)
        self.users = {
            1: user_pb2.User(id=1, name="Alice", email="alice@example.com"),
            2: user_pb2.User(id=2, name="Bob", email="bob@example.com"),
        }
    
    def GetUser(self, request, context):
        """Unary RPC."""
        user = self.users.get(request.user_id)
        if not user:
            context.abort(grpc.StatusCode.NOT_FOUND, f"User {request.user_id} not found")
        return user
    
    def ListUsers(self, request, context):
        """Server Streaming RPC — генерируем пользователей по одному."""
        page_size = request.page_size or 10
        count = 0
        
        for user in self.users.values():
            if count >= page_size:
                break
            yield user  # Stream!
            count += 1
            time.sleep(0.1)  # Имитируем медленную БД
    
    def BulkCreate(self, request_iterator, context):
        """Client Streaming RPC — принимаем поток запросов."""
        created = 0
        errors = []
        
        for req in request_iterator:
            try:
                new_id = max(self.users.keys()) + 1
                self.users[new_id] = user_pb2.User(
                    id=new_id, name=req.name, email=req.email
                )
                created += 1
            except Exception as e:
                errors.append(str(e))
        
        return user_pb2.BulkCreateResponse(
            created_count=created,
            errors=errors
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    user_pb2_grpc.add_UserServiceServicer_to_server(UserServicer(), server)
    
    # Добавляем TLS (для production):
    # with open('server.key', 'rb') as f: private_key = f.read()
    # with open('server.crt', 'rb') as f: certificate_chain = f.read()
    # server_credentials = grpc.ssl_server_credentials([(private_key, certificate_chain)])
    # server.add_secure_port('[::]:443', server_credentials)
    
    server.add_insecure_port('[::]:50051')
    server.start()
    print("gRPC Server started on port 50051")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
```

### 3.4 gRPC клиент

```python
import grpc
import user_pb2
import user_pb2_grpc

def grpc_client_example():
    # Создаём канал
    channel = grpc.insecure_channel('localhost:50051')
    
    # Для production с TLS:
    # creds = grpc.ssl_channel_credentials()
    # channel = grpc.secure_channel('api.example.com:443', creds)
    
    stub = user_pb2_grpc.UserServiceStub(channel)
    
    # Unary RPC
    try:
        user = stub.GetUser(user_pb2.GetUserRequest(user_id=1))
        print(f"Got user: {user.name}")
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            print("User not found")
    
    # Server Streaming
    print("Listing users:")
    for user in stub.ListUsers(user_pb2.ListUsersRequest(page_size=5)):
        print(f"  - {user.id}: {user.name}")
    
    # Client Streaming
    def create_requests():
        for name, email in [("Charlie", "c@e.com"), ("Dave", "d@e.com")]:
            yield user_pb2.CreateUserRequest(name=name, email=email)
    
    result = stub.BulkCreate(create_requests())
    print(f"Created {result.created_count} users")
    
    channel.close()

grpc_client_example()
```

### 3.5 gRPC vs REST

| Характеристика | REST/JSON | gRPC/Protobuf |
|---------------|-----------|---------------|
| Сериализация | JSON (текст) | Protobuf (бинарный) |
| Производительность | Умеренная | 5-10x быстрее |
| Схема | Опциональная (OpenAPI) | Обязательная |
| Типизация | Слабая (JSON types) | Строгая |
| Streaming | Нет (только SSE/WS) | 4 типа (unary, s-stream, c-stream, bidi) |
| Браузер | Нативно | Нужен grpc-web прокси |
| Дебаггинг | Простой (читаемый JSON) | Сложнее (бинарный) |
| Инструменты | Огромная экосистема | Растущая |

---

## 4. Сравнение всех технологий

| | HTTP Polling | Long Polling | SSE | WebSocket | gRPC Streaming |
|-|-------------|-------------|-----|-----------|---------------|
| Latency | Высокая | Средняя | Низкая | Очень низкая | Очень низкая |
| Overhead | Высокий | Средний | Низкий | Минимальный | Минимальный |
| Направление | C→S→C | C→S→C | S→C | Двусторонний | Все варианты |
| Автопереподключение | N/A | Вручную | Встроено | Вручную | Вручную |
| Browser support | Полная | Полная | Полная | Полная | Через прокси |
| Use case | Редкие обновления | Chat (legacy) | LLM, уведомления | Чат, игры | Микросервисы |

---

## Заключение

Выбор технологии зависит от паттерна коммуникации и аудитории:

**Используйте SSE когда**:
- Только сервер отправляет данные (LLM стриминг, уведомления)
- Нужно простое решение с автопереподключением
- Клиент — браузер

**Используйте WebSocket когда**:
- Двусторонняя коммуникация (чат, совместное редактирование, игры)
- Много мелких быстрых сообщений в обе стороны

**Используйте gRPC когда**:
- Сервис-сервис коммуникация (микросервисы)
- Нужна строгая схема и типизация
- Производительность критична
- Нужен streaming в любом направлении

---

## Литература и источники

1. RFC 6455. The WebSocket Protocol. IETF. https://tools.ietf.org/html/rfc6455
2. W3C Server-Sent Events Specification. https://www.w3.org/TR/eventsource/
3. gRPC Documentation. https://grpc.io/docs/
4. Protocol Buffers Documentation. https://protobuf.dev/
5. MDN Web Docs. WebSockets API. https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
6. MDN Web Docs. EventSource. https://developer.mozilla.org/en-US/docs/Web/API/EventSource
7. websockets Python library. https://websockets.readthedocs.io/
8. FastAPI Documentation. WebSockets. https://fastapi.tiangolo.com/advanced/websockets/
9. Wikipedia. WebSocket. https://en.wikipedia.org/wiki/WebSocket
10. Grigorik, I. (2013). *High Performance Browser Networking*. O'Reilly. https://hpbn.co/
