# Serverless и FaaS: AWS Lambda и масштабирование до нуля

Вы написали функцию обработки изображений. Она запускается тысячу раз в день. Нужен ли вам сервер 24/7? С serverless — нет. Функция работает только во время выполнения. В остальное время она не потребляет ресурсы и не стоит денег. Это и есть serverless: платите только за реальное использование.

## Что такое Serverless

Serverless — это не отсутствие серверов. Серверы есть, но вы о них не думаете. Провайдер управляет:
- Выделением и освобождением ресурсов
- Масштабированием: от 0 до 10 000 одновременных выполнений
- Обновлением ОС и runtime
- Балансировкой нагрузки и отказоустойчивостью

Вы управляете только **кодом функции** и **событием**, которое её запускает.

Serverless охватывает несколько моделей:

```
BaaS (Backend as a Service):
  Auth, Database, Storage — готовые сервисы
  Примеры: Firebase, Auth0, Supabase

FaaS (Function as a Service):
  Ваш код в облаке, запускается по событию
  Примеры: AWS Lambda, Google Cloud Functions, Azure Functions

Serverless Containers:
  Контейнеры без управления кластером
  Примеры: AWS Fargate, Google Cloud Run, Azure Container Instances
```

В этой статье — фокус на **FaaS**.

## FaaS модель

Функция FaaS — это небольшой кусок кода с определённым интерфейсом:

```python
# AWS Lambda функция (Python)
def handler(event, context):
    # event — входящие данные (dict)
    # context — метаданные выполнения
    
    print(f"Function name: {context.function_name}")
    print(f"Remaining time: {context.get_remaining_time_in_millis()}ms")
    
    name = event.get('name', 'World')
    return {
        'statusCode': 200,
        'body': f'Hello, {name}!'
    }
```

```javascript
// AWS Lambda (Node.js)
export const handler = async (event, context) => {
    console.log('Event:', JSON.stringify(event));
    
    return {
        statusCode: 200,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'Hello from Lambda!' })
    };
};
```

```go
// AWS Lambda (Go)
package main

import (
    "context"
    "fmt"
    "github.com/aws/aws-lambda-go/lambda"
)

type Event struct {
    Name string `json:"name"`
}

func handler(ctx context.Context, event Event) (string, error) {
    return fmt.Sprintf("Hello, %s!", event.Name), nil
}

func main() {
    lambda.Start(handler)
}
```

## AWS Lambda: основы

AWS Lambda — самый популярный FaaS сервис. Запущен в 2014 году.

### Поддерживаемые runtime

```
Официальные: Python 3.8-3.12, Node.js 18/20/22, Java 8/11/17/21,
             .NET 6/8, Ruby 3.2, Go 1.x

Custom Runtime: любой язык через bootstrap исполняемый файл
Container: Docker образ до 10 GB
```

### Пример: простой HTTP API через API Gateway

```python
import json
import boto3
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('Users')

def handler(event, context):
    method = event['httpMethod']
    path = event['path']
    
    if method == 'GET' and path == '/users':
        response = table.scan()
        users = response['Items']
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(users)
        }
    
    elif method == 'POST' and path == '/users':
        body = json.loads(event['body'])
        user = {
            'id': str(datetime.now().timestamp()),
            'name': body['name'],
            'email': body['email']
        }
        table.put_item(Item=user)
        return {
            'statusCode': 201,
            'body': json.dumps(user)
        }
    
    return {'statusCode': 404, 'body': 'Not Found'}
```

```yaml
# serverless.yml (Serverless Framework)
service: users-api

provider:
  name: aws
  runtime: python3.12
  region: us-east-1
  environment:
    TABLE_NAME: !Ref UsersTable
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - dynamodb:GetItem
            - dynamodb:PutItem
            - dynamodb:Scan
          Resource: !GetAtt UsersTable.Arn

functions:
  usersHandler:
    handler: handler.handler
    events:
      - http:
          path: /users
          method: ANY
      - http:
          path: /users/{id}
          method: ANY

resources:
  Resources:
    UsersTable:
      Type: AWS::DynamoDB::Table
      Properties:
        TableName: Users
        BillingMode: PAY_PER_REQUEST
        AttributeDefinitions:
          - AttributeName: id
            AttributeType: S
        KeySchema:
          - AttributeName: id
            KeyType: HASH
```

## Cold Start и Warm Start

Это критически важная характеристика Lambda. Когда функция запрашивается:

### Cold Start (первый запуск или масштабирование)

```
1. Скачать код функции (zip или образ)
2. Запустить новый execution environment
3. Инициализировать runtime (Python, JVM, Node.js)
4. Выполнить код инициализации вне handler (import, глобальные переменные)
5. Вызвать handler() — выполнить функцию
```

Задержки cold start:
```
Python/Node.js: 100-500 мс
Java (JVM):     1-5 секунд (JVM тяжелая!)
Go:             100-300 мс
Container image: 1-10+ секунд
```

### Warm Start (повторное использование)

После первого вызова Lambda сохраняет execution environment "тёплым" ~5-15 минут:

```
Повторный запрос → сразу handler() ← 1-10 мс задержки
```

```python
import boto3
import time

# Инициализация ВНЕ handler — выполняется только при cold start
print("Cold start: initializing...")
s3_client = boto3.client('s3')  # Подключение при cold start
db_connection = create_db_connection()  # Создать один раз

def handler(event, context):
    # Warm start: db_connection уже готово
    start = time.time()
    
    result = db_connection.query("SELECT ...")
    
    latency = (time.time() - start) * 1000
    print(f"Handler took {latency:.1f}ms")
    
    return {'result': result}
```

### Борьба с cold start

```python
# 1. Provisioned Concurrency — предварительно "разогретые" инстанции
# В serverless.yml:
# provisionedConcurrency: 5  ← всегда 5 разогретых инстанций

# 2. Lambda Warming — регулярные пинги (костыль)
import boto3

def warmer(event, context):
    if event.get('source') == 'warmup':
        print("Warming up, no cold start!")
        return {'warmed': True}
    # Реальная логика
    return handle_real_request(event)

# EventBridge правило: каждые 5 минут вызывает функцию
```

```python
# 3. Snap Start (Java Lambda) — снимок инициализированной JVM
# В CDK:
# snap_start=SnapStartConf.ON_PUBLISHED_VERSIONS
```

```python
# 4. Оптимизация: минимизировать cold start
# - Использовать Python/Node.js вместо Java
# - Минимальные зависимости (zip < 1MB быстрее загружается)
# - Lazy loading: импортировать только нужное

def handler(event, context):
    # Ленивый импорт — только когда нужно
    if event['type'] == 'image':
        from PIL import Image  # Импорт только здесь
        process_image(event)
```

## Event-driven вызов

Lambda запускается событиями из множества источников:

```
API Gateway / ALB    → HTTP запросы
S3                   → загрузка/удаление файлов
DynamoDB Streams     → изменения в таблице
SQS / SNS / EventBridge → сообщения и события
Kinesis              → потоковые данные
CloudWatch Events    → расписание (cron)
Cognito              → аутентификация
IoT Core             → IoT сообщения
Step Functions       → workflow оркестрация
```

```python
# Обработка S3 событий
def s3_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        size = record['s3']['object']['size']
        
        print(f"New file: s3://{bucket}/{key} ({size} bytes)")
        process_file(bucket, key)

# Обработка SQS очереди
def sqs_handler(event, context):
    processed = []
    failed = []
    
    for record in event['Records']:
        message_id = record['messageId']
        body = json.loads(record['body'])
        
        try:
            process_message(body)
            processed.append(message_id)
        except Exception as e:
            print(f"Failed {message_id}: {e}")
            failed.append({'itemIdentifier': message_id})
    
    # Вернуть failed для повторной обработки
    return {'batchItemFailures': failed}

# Scheduled: каждый час
def scheduled_handler(event, context):
    # EventBridge cron: "rate(1 hour)" или "cron(0 * * * ? *)"
    print(f"Running at: {event['time']}")
    cleanup_old_records()
```

## Billing модель

AWS Lambda: **оплата за вызов и за GB-секунду**:

```
Цены (us-east-1, 2024):
- Запросы: $0.20 за 1 миллион запросов
- Длительность: $0.0000166667 за GB-секунду

Пример расчёта:
- 1 000 000 вызовов в месяц
- Каждый занимает 200 мс
- Memory: 512 MB (= 0.5 GB)

Стоимость запросов: 1,000,000 × $0.20/1,000,000 = $0.20
Стоимость вычислений: 1,000,000 × 0.2с × 0.5 GB × $0.0000166667/GB-с = $1.67

Итого: ~$1.87/месяц

Бесплатный уровень:
- 1 000 000 запросов в месяц
- 400 000 GB-секунд в месяц
```

```python
# Оптимизация стоимости
# 1. Уменьшить время выполнения
import concurrent.futures

def handler(event, context):
    # Параллельные запросы вместо последовательных
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_item, item_id)
                   for item_id in event['item_ids']]
        results = [f.result() for f in futures]
    return results

# 2. Правильный выбор memory
# Больше memory → больше CPU → быстрее → может быть дешевле!
# 128 MB, 500 мс, $X  vs  1024 MB, 50 мс, < $X (в 10 раз быстрее, в 8 раз дороже/сек)
# Тест с AWS Lambda Power Tuning
```

## Stateless природа и ограничения

Lambda функции **stateless** — между вызовами состояние не сохраняется (кроме warm start кеша, что ненадёжно):

```python
# НЕПРАВИЛЬНО: глобальный счётчик (ненадёжно!)
counter = 0

def handler(event, context):
    global counter
    counter += 1  # При масштабировании у каждого instance свой counter!
    return {'count': counter}

# ПРАВИЛЬНО: внешнее хранилище
import boto3

dynamodb = boto3.client('dynamodb')

def handler(event, context):
    response = dynamodb.update_item(
        TableName='Counters',
        Key={'id': {'S': 'requests'}},
        UpdateExpression='ADD #count :val',
        ExpressionAttributeNames={'#count': 'count'},
        ExpressionAttributeValues={':val': {'N': '1'}},
        ReturnValues='UPDATED_NEW'
    )
    return {'count': int(response['Attributes']['count']['N'])}
```

### Ограничения AWS Lambda

```
Timeout:               максимум 15 минут
Memory:                128 MB – 10 GB
Ephemeral storage (/tmp): 512 MB – 10 GB
Payload (sync):        6 MB request / 6 MB response
Payload (async):       256 KB
Deployment package:    50 MB zip / 250 MB unzipped / 10 GB container
Concurrent executions: 1000 по умолчанию (увеличивается по запросу)
File descriptors:      1024
Threads/processes:     1024
```

```python
# Обход ограничения timeout через Step Functions
# Для длинных задач — использовать orchestration:

import boto3
import json

stepfunctions = boto3.client('stepfunctions')

def start_long_task(event, context):
    execution = stepfunctions.start_execution(
        stateMachineArn='arn:aws:states:us-east-1:123:stateMachine:LongTask',
        input=json.dumps(event)
    )
    return {'executionArn': execution['executionArn']}
```

## Google Cloud Functions, Azure Functions

```python
# Google Cloud Functions (Python)
import functions_framework
from flask import Request

@functions_framework.http
def hello_http(request: Request):
    request_json = request.get_json(silent=True)
    name = (request_json or {}).get('name', 'World')
    return f'Hello, {name}!'

# Deployment
# gcloud functions deploy hello_http \
#   --runtime python312 \
#   --trigger-http \
#   --allow-unauthenticated
```

```csharp
// Azure Functions (C#)
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using System.Net;

public class HelloFunction
{
    [Function("HelloFunction")]
    public HttpResponseData Run(
        [HttpTrigger(AuthorizationLevel.Function, "get", "post")] 
        HttpRequestData req,
        FunctionContext executionContext)
    {
        var response = req.CreateResponse(HttpStatusCode.OK);
        response.Headers.Add("Content-Type", "text/plain");
        response.WriteString("Hello from Azure Functions!");
        return response;
    }
}
```

## Serverless Framework, SAM, CDK

### Serverless Framework

```yaml
# serverless.yml — мультиоблачный
service: image-processor

provider:
  name: aws
  runtime: python3.12
  region: eu-west-1
  memorySize: 1024
  timeout: 30

plugins:
  - serverless-python-requirements

custom:
  pythonRequirements:
    dockerizePip: true
    layer: true

functions:
  processImage:
    handler: src/handler.process_image
    layers:
      - !Ref PythonRequirementsLambdaLayer
    events:
      - s3:
          bucket: uploads-bucket
          event: s3:ObjectCreated:*
          rules:
            - prefix: uploads/
            - suffix: .jpg
    environment:
      OUTPUT_BUCKET: processed-bucket

resources:
  Resources:
    UploadsBucket:
      Type: AWS::S3::Bucket
      Properties:
        BucketName: uploads-bucket
    ProcessedBucket:
      Type: AWS::S3::Bucket
      Properties:
        BucketName: processed-bucket
```

### AWS SAM (Serverless Application Model)

```yaml
# template.yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Globals:
  Function:
    Timeout: 30
    MemorySize: 512
    Runtime: python3.12
    Environment:
      Variables:
        STAGE: !Ref Stage

Parameters:
  Stage:
    Type: String
    Default: dev

Resources:
  ProcessImageFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: handler.process_image
      Policies:
        - S3ReadPolicy:
            BucketName: !Ref UploadsBucket
        - S3WritePolicy:
            BucketName: !Ref ProcessedBucket
      Events:
        S3Upload:
          Type: S3
          Properties:
            Bucket: !Ref UploadsBucket
            Events: s3:ObjectCreated:*

  UploadsBucket:
    Type: AWS::S3::Bucket

  ProcessedBucket:
    Type: AWS::S3::Bucket

Outputs:
  UploadsBucketName:
    Value: !Ref UploadsBucket
```

```bash
# SAM команды
sam init                    # Создать новый проект
sam build                   # Собрать артефакты
sam local invoke            # Запустить локально
sam local start-api         # Локальный API Gateway
sam deploy --guided         # Деплой в AWS
sam logs -n ProcessImageFunction --tail  # Логи в реальном времени
```

### AWS CDK (Cloud Development Kit)

```python
# cdk_stack.py — инфраструктура как код на Python
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_iam as iam,
    Duration,
)
from constructs import Construct

class ImageProcessorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # S3 buckets
        uploads_bucket = s3.Bucket(self, "UploadsBucket",
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(30)
                )
            ]
        )
        
        processed_bucket = s3.Bucket(self, "ProcessedBucket")

        # Lambda function
        process_fn = lambda_.Function(self, "ProcessImageFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.process_image",
            code=lambda_.Code.from_asset("src"),
            memory_size=1024,
            timeout=Duration.seconds(30),
            environment={
                "OUTPUT_BUCKET": processed_bucket.bucket_name,
            }
        )

        # Permissions
        uploads_bucket.grant_read(process_fn)
        processed_bucket.grant_write(process_fn)

        # S3 trigger
        uploads_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(process_fn)
        )
```

```bash
# CDK команды
cdk init app --language python
cdk synth            # Сгенерировать CloudFormation
cdk diff             # Что изменится
cdk deploy           # Развернуть
cdk destroy          # Удалить
```

## Edge Computing: Cloudflare Workers

Cloudflare Workers — serverless runtime, выполняющийся не в централизованных регионах, а **на ~300 edge-серверах по всему миру**. Запрос выполняется на ближайшем к пользователю сервере.

```javascript
// Cloudflare Worker (JavaScript)
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // Кеширование на edge
    const cache = caches.default;
    const cacheKey = new Request(url.toString(), request);
    const cachedResponse = await cache.match(cacheKey);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Обработка запроса
    const response = await handleRequest(request, env);
    
    // Сохранить в кеш на 60 секунд
    ctx.waitUntil(cache.put(cacheKey,
      response.clone()));
    
    return response;
  }
};

async function handleRequest(request, env) {
  const { pathname } = new URL(request.url);
  
  if (pathname.startsWith('/api/')) {
    // Workers KV для хранения данных
    const data = await env.MY_KV.get('key', 'json');
    return Response.json(data);
  }
  
  return new Response('Hello from the edge!', {
    headers: { 'Content-Type': 'text/plain' }
  });
}
```

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.js"
compatibility_date = "2024-01-01"

[[kv_namespaces]]
binding = "MY_KV"
id = "abc123"

[[r2_buckets]]
binding = "MY_BUCKET"
bucket_name = "my-r2-bucket"

[vars]
ENVIRONMENT = "production"
```

### Особенности Workers

- **V8 Isolates**: не Node.js, не Docker. Каждый worker запускается в V8 Isolate — изолированный JavaScript контекст за ~0.5 мс холодного старта
- **No Node.js API**: нет fs, nет net. Только Web APIs
- **CPU limit**: 10 мс CPU на бесплатном тарифе, 30 с на платном
- **Workers KV**: eventually consistent key-value хранилище
- **Durable Objects**: stateful workers с сильной консистентностью
- **R2**: объектное хранилище (совместимость с S3 API, без egress fees)

```javascript
// Durable Object: stateful edge computing
export class Counter {
  constructor(state, env) {
    this.state = state;
  }

  async fetch(request) {
    let count = (await this.state.storage.get('count')) || 0;
    count++;
    await this.state.storage.put('count', count);
    return Response.json({ count });
  }
}

export default {
  async fetch(request, env) {
    // Каждый пользователь получает собственный Counter instance
    const userId = request.headers.get('X-User-Id');
    const id = env.COUNTER.idFromName(userId);
    const stub = env.COUNTER.get(id);
    return stub.fetch(request);
  }
};
```

## Практический пример: Image Processing Pipeline

Полный пример: пользователь загружает фото → Lambda изменяет размер → результат в S3:

```python
# src/handler.py
import boto3
import io
import json
import logging
from PIL import Image

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')

# Инициализация вне handler (кешируется при warm start)
SIZES = {
    'thumbnail': (150, 150),
    'medium': (800, 600),
    'large': (1920, 1080),
}

def process_image(event, context):
    """Обработчик S3 событий — создаёт несколько размеров изображения."""
    
    results = []
    
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        logger.info(f"Processing: s3://{bucket}/{key}")
        
        try:
            # Скачать оригинал
            response = s3.get_object(Bucket=bucket, Key=key)
            image_data = response['Body'].read()
            
            # Открыть изображение
            image = Image.open(io.BytesIO(image_data))
            
            # Конвертировать в RGB (если RGBA/P)
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            
            original_format = image.format or 'JPEG'
            
            output_results = []
            
            for size_name, (width, height) in SIZES.items():
                # Создать копию и изменить размер
                resized = image.copy()
                resized.thumbnail((width, height), Image.LANCZOS)
                
                # Сохранить в буфер
                buffer = io.BytesIO()
                resized.save(buffer, format='WEBP', quality=85)
                buffer.seek(0)
                
                # Построить ключ для output
                file_name = key.split('/')[-1].rsplit('.', 1)[0]
                output_key = f"processed/{file_name}/{size_name}.webp"
                output_bucket = "processed-images"
                
                # Загрузить результат
                s3.put_object(
                    Bucket=output_bucket,
                    Key=output_key,
                    Body=buffer,
                    ContentType='image/webp',
                    Metadata={
                        'original-key': key,
                        'size': size_name,
                        'width': str(resized.width),
                        'height': str(resized.height),
                    }
                )
                
                output_results.append({
                    'size': size_name,
                    'key': output_key,
                    'width': resized.width,
                    'height': resized.height,
                })
                
                logger.info(f"Created {size_name}: {resized.width}x{resized.height}")
            
            results.append({
                'original': key,
                'outputs': output_results,
                'status': 'success'
            })
            
        except Exception as e:
            logger.error(f"Error processing {key}: {e}", exc_info=True)
            results.append({
                'original': key,
                'status': 'error',
                'error': str(e)
            })
    
    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
```

```python
# tests/test_handler.py
import json
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import io

from src.handler import process_image

@pytest.fixture
def s3_event():
    return {
        'Records': [{
            's3': {
                'bucket': {'name': 'uploads-bucket'},
                'object': {'key': 'uploads/photo.jpg', 'size': 12345}
            }
        }]
    }

@pytest.fixture
def mock_image_bytes():
    img = Image.new('RGB', (2000, 1500), color='blue')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf.read()

def test_process_image_success(s3_event, mock_image_bytes):
    with patch('src.handler.s3') as mock_s3:
        mock_s3.get_object.return_value = {
            'Body': io.BytesIO(mock_image_bytes)
        }
        mock_s3.put_object.return_value = {}
        
        result = process_image(s3_event, MagicMock())
        
        body = json.loads(result['body'])
        assert result['statusCode'] == 200
        assert len(body) == 1
        assert body[0]['status'] == 'success'
        assert len(body[0]['outputs']) == 3  # thumbnail, medium, large
        
        # Проверить вызовы put_object
        assert mock_s3.put_object.call_count == 3
```

## Паттерны и антипаттерны

### Паттерны

```python
# 1. Fan-out/Fan-in через SQS
def coordinator(event, context):
    """Разбить большую задачу на подзадачи."""
    sqs = boto3.client('sqs')
    items = event['items']  # [1000 элементов]
    
    # Отправить батчами по 10 в SQS
    for i in range(0, len(items), 10):
        batch = items[i:i+10]
        sqs.send_message(
            QueueUrl=os.environ['QUEUE_URL'],
            MessageBody=json.dumps({'batch': batch})
        )

def worker(event, context):
    """Обработать батч из SQS."""
    for record in event['Records']:
        batch = json.loads(record['body'])['batch']
        for item in batch:
            process_item(item)
```

```python
# 2. Idempotency — защита от повторных вызовов
import hashlib

def handler(event, context):
    # Создать идемпотентный ключ
    request_id = event.get('requestId') or context.aws_request_id
    
    dynamodb = boto3.client('dynamodb')
    
    # Проверить, не обрабатывался ли уже этот запрос
    try:
        dynamodb.put_item(
            TableName='ProcessedRequests',
            Item={'request_id': {'S': request_id}},
            ConditionExpression='attribute_not_exists(request_id)'
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:
        print(f"Already processed: {request_id}")
        return {'status': 'already_processed'}
    
    # Обработать
    result = do_work(event)
    return result
```

### Антипаттерны

```python
# АНТИПАТТЕРН: длинные операции
def bad_handler(event, context):
    # 15+ минут? Это не для Lambda
    for i in range(1_000_000):
        expensive_operation(i)  # Превысит timeout

# ЛУЧШЕ: Step Functions + Lambda (каждый шаг < 15 минут)

# АНТИПАТТЕРН: лямбда вызывает лямбду синхронно
def orchestrator(event, context):
    lambda_client = boto3.client('lambda')
    # Синхронный вызов: оба держат открытыми connections
    response = lambda_client.invoke(
        FunctionName='worker',
        InvocationType='RequestResponse'  # Блокирующий!
    )

# ЛУЧШЕ: асинхронный вызов или SQS
lambda_client.invoke(
    FunctionName='worker',
    InvocationType='Event'  # Fire-and-forget
)

# ИЛИ: Step Functions для оркестрации
```

## Мониторинг и отладка

```python
# AWS Lambda Powertools (рекомендуемый подход)
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ImageProcessor")

@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event: dict, context: LambdaContext):
    with tracer.provider.in_subsegment("## process"):
        metrics.add_metric(
            name="ImagesProcessed",
            unit=MetricUnit.Count,
            value=len(event['Records'])
        )
        
        logger.info("Processing images", extra={
            "count": len(event['Records'])
        })
        
        result = process_images(event)
        
        logger.info("Processing complete", extra={
            "result": result
        })
        
        return result
```

```bash
# CloudWatch Insights запросы для анализа
fields @timestamp, @message, @requestId
| filter @message like /ERROR/
| sort @timestamp desc
| limit 100

# Стоимость и duration
filter @type = "REPORT"
| stats avg(Duration), max(Duration), sum(BilledDuration), count()
by bin(1h)
```

## Итог

Serverless и FaaS трансформируют разработку бэкенда:

1. **Serverless** = без управления серверами; провайдер занимается инфраструктурой
2. **FaaS** = функция запускается по событию; масштабирование от 0 до $\infty$
3. **Cold/Warm start** = первый запуск медленнее; оптимизация через Provisioned Concurrency
4. **Stateless** = нет состояния между вызовами; используйте DynamoDB/Redis/S3
5. **Event-driven** = S3, SQS, API Gateway, Kinesis, Schedule — богатая экосистема триггеров
6. **Billing per use** = платите только за реальные вызовы и миллисекунды CPU
7. **Инструменты** = Serverless Framework, SAM, CDK — IaC для serverless
8. **Edge Computing** = Cloudflare Workers (V8 Isolates) $\approx$ 0 мс cold start на ближайшем PoP
9. **Ограничения** = 15 минут timeout, stateless; не подходит для long-running задач

## Литература

1. AWS. *AWS Lambda Documentation*. https://docs.aws.amazon.com/lambda/

2. Sbarski, P. (2017). *Serverless Architectures on AWS*. Manning Publications.

3. Stigler, M., Marek, W. (2021). *Beginning Serverless Computing*. Apress.

4. Roberts, M., Chapin, J. (2019). *What is Serverless?* O'Reilly Media.

5. Cloudflare. *Cloudflare Workers Documentation*. https://developers.cloudflare.com/workers/

6. Google Cloud. *Cloud Functions Documentation*. https://cloud.google.com/functions/docs

7. Microsoft Azure. *Azure Functions Documentation*. https://docs.microsoft.com/en-us/azure/azure-functions/

8. Serverless Framework. *Serverless Framework Documentation*. https://www.serverless.com/framework/docs

9. AWS. *AWS Serverless Application Model (SAM) Developer Guide*. https://docs.aws.amazon.com/serverless-application-model/

10. Fowler, M. (2016). *Serverless Architectures*. https://martinfowler.com/articles/serverless.html

11. Lloyd, W., et al. (2018). *Serverless Computing: An Investigation of Factors Influencing Microservice Performance*. IEEE International Conference on Cloud Engineering.
