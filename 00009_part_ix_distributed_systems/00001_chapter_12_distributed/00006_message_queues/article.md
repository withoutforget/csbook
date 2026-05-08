# Очереди сообщений: Kafka, RabbitMQ и паттерны асинхронного взаимодействия

Когда микросервисы общаются напрямую (HTTP/gRPC), они тесно связаны: получатель должен быть доступен в момент отправки, скорость обработки должна совпадать со скоростью поступления запросов, сбой одного сервиса каскадно влияет на других. Очереди сообщений разрывают эту связь. Отправитель кладёт сообщение в очередь и идёт дальше. Получатель обрабатывает в своём темпе. Система продолжает работать, даже если часть компонентов временно недоступна.

Это не просто техническая деталь — это архитектурный принцип, меняющий способ мышления о распределённых системах.

## Что такое брокер сообщений

Брокер сообщений (message broker) — посредник, принимающий сообщения от производителей (producers/publishers) и доставляющий их потребителям (consumers/subscribers). Он решает несколько задач одновременно:

- **Буферизация**: сглаживает пики нагрузки
- **Персистентность**: сообщения не теряются при перезапуске
- **Маршрутизация**: доставка нужным потребителям
- **Гарантии доставки**: at-least-once, at-most-once, exactly-once

Два наиболее популярных решения — RabbitMQ и Apache Kafka — реализуют принципиально разные архитектурные подходы, каждый со своими сильными сторонами.

## RabbitMQ: умный брокер

RabbitMQ построен на протоколе AMQP (Advanced Message Queuing Protocol). Центральная абстракция — **exchange** (точка обмена) и **queue** (очередь).

```
Producer → Exchange → Binding → Queue → Consumer
```

Производитель не знает о очередях напрямую. Он публикует в exchange с routing key. Exchange по правилам (bindings) решает, в какую очередь направить сообщение.

### Типы exchanges

```python
import pika
import json
from datetime import datetime

def get_rabbitmq_connection():
    return pika.BlockingConnection(
        pika.ConnectionParameters(host='localhost')
    )

# Direct Exchange: точное совпадение routing key
def setup_direct_exchange():
    conn = get_rabbitmq_connection()
    channel = conn.channel()
    
    # Объявляем exchange
    channel.exchange_declare(
        exchange='orders',
        exchange_type='direct',
        durable=True  # переживёт перезапуск брокера
    )
    
    # Создаём очереди для разных приоритетов
    for priority in ['high', 'normal', 'low']:
        channel.queue_declare(
            queue=f'orders.{priority}',
            durable=True,  # персистентная очередь
            arguments={
                'x-message-ttl': 3600000,    # TTL 1 час
                'x-dead-letter-exchange': 'orders.dlx'  # DLX для неудавшихся
            }
        )
        channel.queue_bind(
            exchange='orders',
            queue=f'orders.{priority}',
            routing_key=priority  # routing key = имя очереди
        )
    
    return channel

def publish_order(channel, order: dict, priority: str = 'normal'):
    """Опубликовать заказ в нужную очередь по приоритету."""
    channel.basic_publish(
        exchange='orders',
        routing_key=priority,  # direct routing: совпадает с binding
        body=json.dumps(order).encode(),
        properties=pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent,  # сохранить на диск
            content_type='application/json',
            message_id=order.get('id'),  # для дедупликации
            timestamp=int(datetime.now().timestamp())
        )
    )
```

```python
# Topic Exchange: routing key с wildcards (* = одно слово, # = много слов)
def setup_topic_exchange():
    conn = get_rabbitmq_connection()
    channel = conn.channel()
    
    channel.exchange_declare(
        exchange='events',
        exchange_type='topic',
        durable=True
    )
    
    # Подписываемся на все события заказов
    channel.queue_declare(queue='order_events', durable=True)
    channel.queue_bind(
        exchange='events',
        queue='order_events',
        routing_key='order.*'  # order.created, order.shipped, order.cancelled
    )
    
    # Подписываемся на ВСЕ события
    channel.queue_declare(queue='audit_log', durable=True)
    channel.queue_bind(
        exchange='events',
        queue='audit_log',
        routing_key='#'  # все сообщения
    )
    
    # Публикация: routing key = тип события
    def emit_event(event_type: str, data: dict):
        channel.basic_publish(
            exchange='events',
            routing_key=event_type,  # например: 'order.created', 'user.updated'
            body=json.dumps(data).encode(),
            properties=pika.BasicProperties(delivery_mode=2)
        )
    
    return emit_event
```

### Потребители и подтверждения

```python
class RabbitMQConsumer:
    def __init__(self, queue: str, prefetch_count: int = 10):
        self.queue = queue
        self.conn = get_rabbitmq_connection()
        self.channel = self.conn.channel()
        
        # Prefetch: сколько сообщений получить до подтверждения
        # Без этого один медленный consumer заберёт все сообщения
        self.channel.basic_qos(prefetch_count=prefetch_count)
    
    def consume(self, handler):
        """Начать потребление с ручным подтверждением (manual ack)."""
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body.decode())
                handler(message)
                
                # Подтверждаем успешную обработку
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                print(f"Processing failed: {e}")
                
                # Requeue=False: отправить в DLQ, не ставить обратно в очередь
                # Requeue=True: вернуть в начало очереди (осторожно: infinite loop!)
                retry_count = properties.headers.get('x-retry-count', 0) if properties.headers else 0
                
                if retry_count < 3:
                    # Публикуем с увеличенным счётчиком ретраев
                    self.channel.basic_publish(
                        exchange='',
                        routing_key=self.queue,
                        body=body,
                        properties=pika.BasicProperties(
                            delivery_mode=2,
                            headers={'x-retry-count': retry_count + 1},
                            expiration=str(1000 * (2 ** retry_count))  # задержка в мс
                        )
                    )
                
                # Reject без requeue — уйдёт в DLQ
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        self.channel.basic_consume(
            queue=self.queue,
            on_message_callback=callback
        )
        self.channel.start_consuming()
```

### Dead Letter Exchange (DLX)

```python
def setup_with_dlx():
    """Настроить очередь с dead-letter exchange."""
    conn = get_rabbitmq_connection()
    channel = conn.channel()
    
    # Сначала создаём DLX и DLQ
    channel.exchange_declare(exchange='orders.dlx', exchange_type='direct')
    channel.queue_declare(
        queue='orders.dead',
        durable=True,
        arguments={
            'x-message-ttl': 86400000  # Хранить 24 часа для анализа
        }
    )
    channel.queue_bind(
        exchange='orders.dlx',
        queue='orders.dead',
        routing_key='dead'
    )
    
    # Основная очередь с привязкой к DLX
    channel.queue_declare(
        queue='orders.main',
        durable=True,
        arguments={
            'x-dead-letter-exchange': 'orders.dlx',
            'x-dead-letter-routing-key': 'dead',
            'x-message-ttl': 300000  # TTL: 5 минут
        }
    )
```

## Apache Kafka: распределённый журнал

Kafka принципиально отличается от RabbitMQ. Это не «умный брокер с глупыми потребителями», а «тупой брокер с умными потребителями» (по аналогии с Unix philosophy). Kafka — это распределённый лог (append-only журнал).

### Ключевые концепции

```
Topic → Partition 0: [msg1, msg2, msg3, msg4, ...]  (offset 0, 1, 2, 3...)
      → Partition 1: [msg5, msg6, msg7, ...]
      → Partition 2: [msg8, msg9, ...]

Consumer Group A → Consumer 1 reads Partition 0
               → Consumer 2 reads Partition 1
               → Consumer 3 reads Partition 2

Consumer Group B → Single consumer reads ALL partitions
```

**Topic** — логическая категория сообщений. Разбита на **partitions** для параллелизма. Внутри партиции сообщения упорядочены и неизменны. Каждое сообщение имеет **offset** — позицию в партиции.

Потребители сами хранят свой offset — это принципиальное отличие от RabbitMQ. Можно «перемотать» и перечитать сообщения.

### Producer

```python
from confluent_kafka import Producer
from confluent_kafka.serialization import StringSerializer, SerializationContext, MessageField
import json
import uuid

class KafkaOrderProducer:
    def __init__(self, bootstrap_servers: str):
        self.producer = Producer({
            'bootstrap.servers': bootstrap_servers,
            'enable.idempotence': True,     # идемпотентная отправка
            'acks': 'all',                   # подтверждение от всех реплик
            'retries': 10,
            'max.in.flight.requests.per.connection': 5,
            'compression.type': 'snappy',    # компрессия
            'linger.ms': 5,                  # небольшая задержка для батчинга
            'batch.size': 16384,             # размер батча в байтах
        })
    
    def send_order(self, order: dict):
        """Отправить заказ с гарантированным порядком для одного пользователя."""
        order_id = order['id']
        user_id = order['user_id']
        
        # Ключ сообщения определяет партицию
        # Все заказы одного пользователя → одна партиция → гарантированный порядок
        key = user_id.encode('utf-8')
        value = json.dumps(order).encode('utf-8')
        
        # Заголовки для трассировки
        headers = {
            'event_type': b'order.created',
            'correlation_id': str(uuid.uuid4()).encode(),
            'source_service': b'order-service'
        }
        
        self.producer.produce(
            topic='orders',
            key=key,
            value=value,
            headers=list(headers.items()),
            on_delivery=self._delivery_callback
        )
        
        # poll() нужен для обработки callbacks
        self.producer.poll(0)
    
    def _delivery_callback(self, err, msg):
        if err:
            print(f"Message delivery failed: {err}")
            # В production: ретрай, алерт, DLQ
        else:
            print(f"Delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}")
    
    def flush(self):
        """Дождаться отправки всех буферизованных сообщений."""
        self.producer.flush()
    
    def __del__(self):
        self.flush()
```

### Consumer и Consumer Groups

```python
from confluent_kafka import Consumer, KafkaError, TopicPartition
import signal
import sys

class KafkaOrderConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str, topics: list):
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',    # начать с начала при первом запуске
            'enable.auto.commit': False,          # ручной commit
            'max.poll.interval.ms': 300000,       # 5 минут на обработку батча
            'session.timeout.ms': 45000,
            'heartbeat.interval.ms': 3000,
            'isolation.level': 'read_committed',  # только закоммиченные транзакции
        })
        self.consumer.subscribe(topics)
        self.running = True
        
        # Graceful shutdown
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
    
    def run(self, handler):
        """Основной цикл обработки."""
        try:
            while self.running:
                # Батч сообщений
                messages = self.consumer.consume(
                    num_messages=100,
                    timeout=1.0
                )
                
                if not messages:
                    continue
                
                # Группируем по партиции для последовательной обработки
                by_partition = {}
                for msg in messages:
                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue  # достигли конца партиции
                        raise Exception(f"Kafka error: {msg.error()}")
                    
                    key = (msg.topic(), msg.partition())
                    by_partition.setdefault(key, []).append(msg)
                
                # Обрабатываем
                for (topic, partition), msgs in by_partition.items():
                    for msg in msgs:
                        try:
                            value = json.loads(msg.value().decode())
                            handler(value, msg.key(), msg.headers())
                        except Exception as e:
                            print(f"Handler error for offset {msg.offset()}: {e}")
                            # В production: send to DLQ, continue or stop?
                
                # Commit только после успешной обработки всего батча
                self.consumer.commit(asynchronous=False)
        
        finally:
            self.consumer.close()
    
    def _shutdown(self, signum, frame):
        print("Shutting down consumer...")
        self.running = False
    
    def seek_to_beginning(self, topic: str):
        """Перечитать все сообщения с начала (replay)."""
        partitions = self.consumer.assignment()
        for tp in partitions:
            if tp.topic == topic:
                self.consumer.seek(TopicPartition(tp.topic, tp.partition, 0))
```

### Partitioning и порядок сообщений

```python
# Гарантированный порядок: только внутри одной партиции!

# Правило: все связанные сообщения должны иметь один ключ
# Примеры правильных ключей:
# - user_id: все действия пользователя упорядочены
# - order_id: все события одного заказа упорядочены
# - session_id: все события сессии упорядочены

# Антипаттерн: случайный ключ или null ключ
# → round-robin распределение → нет гарантий порядка

class OrderEventProducer:
    def emit(self, event_type: str, order_id: str, data: dict):
        """
        Ключ = order_id обеспечивает:
        1. Все события одного заказа → одна партиция
        2. Порядок событий сохранён
        3. Потребитель видит: created → confirmed → shipped → delivered
        """
        self.producer.produce(
            topic='order-events',
            key=order_id.encode(),        # ключ определяет партицию
            value=json.dumps({
                'event_type': event_type,
                'order_id': order_id,
                **data
            }).encode()
        )
```

### Компакция (Log Compaction)

Kafka поддерживает два режима хранения:

1. **Delete**: сообщения удаляются после retention.ms/retention.bytes
2. **Compact**: хранить только последнее значение для каждого ключа

```python
# Log compaction полезен для «таблиц состояния»
# Пример: topic user-profiles с compaction

# Обновление профиля пользователя
def update_user_profile(user_id: str, profile: dict):
    """
    После compaction в топике останется только последняя версия
    профиля для каждого user_id. Это превращает топик в "таблицу".
    """
    producer.produce(
        topic='user-profiles',
        key=user_id.encode(),
        value=json.dumps(profile).encode()  # None = tombstone (удаление)
    )

def delete_user_profile(user_id: str):
    """Tombstone: value=null означает удаление при compaction."""
    producer.produce(
        topic='user-profiles',
        key=user_id.encode(),
        value=None  # tombstone
    )
```

## Сравнение RabbitMQ и Kafka

| Характеристика | RabbitMQ | Apache Kafka |
|----------------|----------|--------------|
| Парадигма | Push (брокер толкает) | Pull (consumer тянет) |
| Порядок | В пределах очереди | В пределах партиции |
| Хранение | Удаляет после consume | Хранит по retention policy |
| Replay | Нет (по умолчанию) | Да (seek по offset) |
| Масштабирование | Вертикальное | Горизонтальное |
| Задержка | Очень низкая (мкс) | Низкая (мс) |
| Throughput | Средний | Очень высокий (млн/с) |
| Маршрутизация | Гибкая (exchanges) | Простая (topic + partition) |
| Протокол | AMQP | Собственный |
| Экосистема | Plugins, management UI | Kafka Streams, ksqlDB, Connect |

### Когда RabbitMQ

- Сложная маршрутизация сообщений (фанаут, topic routing, headers exchange)
- Низкая задержка критична
- Push-семантика: брокер знает о медленных потребителях
- Приоритеты сообщений
- Традиционные task queues (Celery, Sidekiq)

### Когда Kafka

- Высокий throughput (миллионы сообщений/сек)
- Event sourcing / event streaming
- Audit log (неизменяемый, воспроизводимый)
- Stream processing (Kafka Streams, Flink)
- Интеграция данных между системами
- Replay событий (отладка, восстановление, новые потребители)

## Паттерны использования

### Event Sourcing

Вместо хранения текущего состояния — хранить последовательность событий.

```python
# Event Store на базе Kafka
class EventStore:
    def __init__(self, producer: Producer):
        self.producer = producer
    
    def append(self, aggregate_type: str, aggregate_id: str, 
               event_type: str, data: dict, expected_version: int):
        """
        Сохранить событие в event store.
        expected_version для optimistic concurrency control.
        """
        event = {
            'aggregate_type': aggregate_type,
            'aggregate_id': aggregate_id,
            'event_type': event_type,
            'data': data,
            'timestamp': time.time(),
            'version': expected_version + 1  # следующая версия
        }
        
        # Ключ = aggregate_id: все события одного агрегата в одной партиции
        self.producer.produce(
            topic=f'events.{aggregate_type.lower()}',
            key=aggregate_id.encode(),
            value=json.dumps(event).encode(),
            headers=[('event_type', event_type.encode())]
        )


class OrderAggregate:
    """Восстановление состояния из событий."""
    
    def __init__(self, order_id: str):
        self.order_id = order_id
        self.status = None
        self.items = []
        self.total = 0
        self.version = 0
    
    def apply(self, event: dict):
        """Применить событие к агрегату."""
        event_type = event['event_type']
        data = event['data']
        
        if event_type == 'OrderCreated':
            self.status = 'created'
            self.items = data['items']
            self.total = data['total']
        
        elif event_type == 'OrderConfirmed':
            self.status = 'confirmed'
        
        elif event_type == 'OrderShipped':
            self.status = 'shipped'
            self.tracking_number = data['tracking_number']
        
        elif event_type == 'OrderCancelled':
            self.status = 'cancelled'
            self.cancel_reason = data.get('reason')
        
        self.version = event['version']
    
    @classmethod
    def load(cls, order_id: str, events: list) -> 'OrderAggregate':
        """Восстановить агрегат из истории событий."""
        order = cls(order_id)
        for event in events:
            order.apply(event)
        return order
```

### CQRS (Command Query Responsibility Segregation)

```
Write Side (Commands):          Read Side (Queries):
OrderService → EventStore →     EventHandler → ReadModel (denormalized)
                                                     ↓
                                              Fast queries via API
```

```python
# Write side: только события
class OrderCommandHandler:
    def handle_create_order(self, command: dict):
        order = OrderAggregate(command['order_id'])
        # Валидация бизнес-логики...
        
        self.event_store.append(
            aggregate_type='Order',
            aggregate_id=command['order_id'],
            event_type='OrderCreated',
            data={
                'user_id': command['user_id'],
                'items': command['items'],
                'total': command['total']
            },
            expected_version=0
        )


# Read side: подписывается на события, строит денормализованные таблицы
class OrderReadModelBuilder:
    def __init__(self, consumer: KafkaOrderConsumer, db):
        self.consumer = consumer
        self.db = db
    
    def run(self):
        self.consumer.run(self.handle_event)
    
    def handle_event(self, event: dict, key: bytes, headers):
        event_type = event['event_type']
        order_id = event['aggregate_id']
        
        if event_type == 'OrderCreated':
            # Создаём запись в read-optimized таблице
            self.db.upsert('order_view', {
                'id': order_id,
                'user_id': event['data']['user_id'],
                'status': 'created',
                'total': event['data']['total'],
                'items_count': len(event['data']['items'])
            })
        
        elif event_type == 'OrderShipped':
            self.db.update('order_view',
                where={'id': order_id},
                set={'status': 'shipped',
                     'tracking': event['data']['tracking_number']}
            )
```

### Competing Consumers (рабочие потоки)

```python
# Параллельная обработка одной очереди несколькими воркерами
# RabbitMQ: несколько consumer'ов на одну очередь
# Kafka: несколько consumer'ов в одной consumer group

class WorkerPool:
    """Пул воркеров для параллельной обработки."""
    
    def __init__(self, num_workers: int, queue_name: str):
        self.workers = []
        for i in range(num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(queue_name, i),
                daemon=True
            )
            self.workers.append(worker)
    
    def start(self):
        for w in self.workers:
            w.start()
    
    def _worker_loop(self, queue_name: str, worker_id: int):
        conn = get_rabbitmq_connection()
        channel = conn.channel()
        channel.basic_qos(prefetch_count=1)  # не жадничать
        
        def callback(ch, method, props, body):
            try:
                message = json.loads(body)
                print(f"Worker {worker_id} processing {message.get('id')}")
                
                # Имитация обработки
                self.process_message(message)
                
                ch.basic_ack(delivery_tag=method.delivery_tag)
            
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        channel.basic_consume(queue=queue_name, on_message_callback=callback)
        channel.start_consuming()
    
    def process_message(self, message: dict):
        # Ваша бизнес-логика
        time.sleep(0.1)
```

### Request-Reply через очереди

```python
# Асинхронный RPC через RabbitMQ
import uuid

class RPCClient:
    def __init__(self, channel):
        self.channel = channel
        
        # Эксклюзивная callback-очередь для ответов
        result = channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        self.responses = {}
        
        channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self._on_response
        )
    
    def _on_response(self, ch, method, props, body):
        correlation_id = props.correlation_id
        if correlation_id in self.responses:
            self.responses[correlation_id] = json.loads(body)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    
    def call(self, target_queue: str, request: dict, timeout: float = 30.0) -> dict:
        """Синхронный вызов через очередь."""
        correlation_id = str(uuid.uuid4())
        self.responses[correlation_id] = None
        
        self.channel.basic_publish(
            exchange='',
            routing_key=target_queue,
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=correlation_id,
                expiration=str(int(timeout * 1000))
            ),
            body=json.dumps(request).encode()
        )
        
        # Ожидаем ответа
        deadline = time.time() + timeout
        while self.responses.get(correlation_id) is None:
            if time.time() > deadline:
                raise TimeoutError(f"RPC timeout after {timeout}s")
            self.channel.connection.process_data_events()
            time.sleep(0.01)
        
        return self.responses.pop(correlation_id)


class RPCServer:
    def __init__(self, channel, queue_name: str):
        self.channel = channel
        channel.queue_declare(queue=queue_name, durable=True)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=queue_name, on_message_callback=self._handle)
    
    def _handle(self, ch, method, props, body):
        request = json.loads(body)
        
        try:
            response = self.process(request)
        except Exception as e:
            response = {"error": str(e)}
        
        # Отправляем ответ в reply_to очередь
        ch.basic_publish(
            exchange='',
            routing_key=props.reply_to,
            properties=pika.BasicProperties(
                correlation_id=props.correlation_id
            ),
            body=json.dumps(response).encode()
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)
    
    def process(self, request: dict) -> dict:
        # Ваша бизнес-логика
        return {"result": "ok"}
```

## Kafka Streams: потоковая обработка

```python
# Концептуальный пример Kafka Streams (на Java это KStream API)
# В Python используется faust или confluent-kafka с ручной логикой

import faust

app = faust.App(
    'order-processing',
    broker='kafka://localhost:9092',
    value_serializer='json'
)

orders_topic = app.topic('orders', value_type=dict)
order_stats_topic = app.topic('order-stats', value_type=dict)

@app.agent(orders_topic)
async def process_orders(orders):
    """Stateful stream processing с Faust."""
    async for order in orders:
        # Агрегация: сумма заказов по пользователю
        user_id = order['user_id']
        
        # Обновляем состояние (сохраняется в RocksDB)
        table_key = f"user:{user_id}:total"
        current = await user_stats_table.get(table_key, 0)
        new_total = current + order['total']
        await user_stats_table.set(table_key, new_total)
        
        # Публикуем агрегированную статистику
        await order_stats_topic.send(
            key=user_id,
            value={
                'user_id': user_id,
                'order_total': new_total,
                'last_order_id': order['id'],
                'timestamp': time.time()
            }
        )

user_stats_table = app.Table('user-stats', default=int)
```

## Мониторинг и операционные аспекты

### Ключевые метрики Kafka

```python
# Метрики, которые нужно мониторить в Kafka
KAFKA_METRICS = {
    # Producer метрики
    'producer': [
        'record-send-rate',           # скорость отправки
        'record-error-rate',          # ошибки отправки
        'record-retry-rate',          # ретраи
        'batch-size-avg',             # средний размер батча
        'record-queue-time-avg',      # время в буфере продюсера
    ],
    
    # Consumer метрики
    'consumer': [
        'records-consumed-rate',      # скорость потребления
        'fetch-rate',                 # частота fetch запросов
        'fetch-latency-avg',          # задержка fetch
        'records-lag-max',            # LAG! Самая важная метрика
        'commit-rate',                # частота commit
    ],
    
    # Broker метрики
    'broker': [
        'messages-in-per-sec',        # входящий поток
        'bytes-in-per-sec',           # входящий трафик
        'bytes-out-per-sec',          # исходящий трафик
        'under-replicated-partitions',# партиции без полной репликации (!)
        'active-controller-count',    # должен быть ровно 1
        'request-handler-pool-idle', # загрузка обработчиков
    ]
}

# Consumer lag — отставание потребителя
# lag = latest_offset - committed_offset
# Если lag растёт — потребитель не успевает за производителем!

def check_consumer_lag(admin_client, group_id: str, topic: str) -> dict:
    """Проверить отставание consumer group."""
    consumer_offsets = admin_client.list_consumer_group_offsets([group_id])
    topic_metadata = admin_client.describe_topics([topic])
    
    lags = {}
    for tp, committed in consumer_offsets[group_id].items():
        if tp.topic == topic:
            # latest offset партиции
            high_watermark = get_high_watermark(tp.topic, tp.partition)
            lag = high_watermark - committed.offset
            lags[tp.partition] = lag
    
    return lags
```

### Правила масштабирования

- **Число партиций** должно быть >= числу consumer'ов в group. Иначе часть consumer'ов простаивает.
- **Репликация**: replication.factor=3 для production. Не менее 2 in-sync replicas (min.insync.replicas=2).
- **Retention**: планируйте хранилище. $7\text{ дней} \times \text{throughput} = \text{дисковое пространство}$.

## Практические рекомендации

**Выбор брокера:**
- RabbitMQ для сложной маршрутизации, task queues, низкой задержки
- Kafka для event streaming, высокого throughput, audit log, replay

**Надёжность:**
- Всегда используйте durable queues/topics и persistent messages
- Настройте DLQ/DLX для неудавшихся сообщений
- Мониторьте consumer lag (главная метрика здоровья)

**Идемпотентность:**
- Потребители должны быть идемпотентными
- Добавляйте уникальные message ID
- Implement deduplication at consumer side

**Производительность:**
- Батчинг сообщений критически важен для throughput
- Компрессия (snappy/lz4) для больших payload
- Правильный prefetch_count/max.poll.records

## Заключение

Очереди сообщений фундаментально меняют способ взаимодействия сервисов — от синхронного «спроси и жди» к асинхронному «опубликуй и забудь». Это повышает отказоустойчивость, позволяет масштабировать компоненты независимо и создаёт буфер против пиков нагрузки.

RabbitMQ и Kafka дополняют друг друга. RabbitMQ — когда нужны сложная маршрутизация и низкая задержка. Kafka — когда нужен масштаб, воспроизводимость и обработка потоков данных. Понимание архитектурных различий позволяет выбрать правильный инструмент и эффективно его использовать.

## Литература

1. Kreps, J., Narkhede, N., Rao, J. (2011). **Kafka: a Distributed Messaging System for Log Processing**. *NetDB '11*.
2. Pivotal (2023). **RabbitMQ Documentation**. https://www.rabbitmq.com/documentation.html
3. Confluent (2023). **Apache Kafka Documentation**. https://kafka.apache.org/documentation/
4. Hohpe, G., Woolf, B. (2004). **Enterprise Integration Patterns**. Addison-Wesley.
5. Kleppmann, M. (2017). **Designing Data-Intensive Applications**. O'Reilly. Chapter 11.
6. Vernon, V. (2016). **Domain-Driven Design Distilled**. Addison-Wesley. (Event Sourcing, CQRS)
7. Richardson, C. (2018). **Microservices Patterns**. Manning Publications.
8. Narkhede, N., Shapira, G., Palino, T. (2017). **Kafka: The Definitive Guide**. O'Reilly Media.
9. Young, G. (2010). **CQRS Documents**. https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
10. Stopford, B. (2018). **Designing Event-Driven Systems**. O'Reilly Media (free ebook from Confluent).
