# IaaS / PaaS / SaaS — где проходит граница ответственности

Облачные вычисления изменили способ построения и эксплуатации программных систем. Однако за словом «облако» скрываются принципиально разные модели предоставления услуг, каждая из которых определяет свой уровень ответственности между провайдером и потребителем. Понимание этих границ критически важно как для архитектурных решений, так и для оценки рисков и затрат.

## Модели облачных услуг: исторический контекст

До появления публичных облаков каждая компания была вынуждена строить и эксплуатировать собственную инфраструктуру. Это означало покупку серверов, аренду стойко-мест в датацентрах, прокладку кабелей, настройку сетевого оборудования, установку операционных систем, баз данных, веб-серверов — и только после всего этого можно было приступать к написанию кода, который создаёт реальную ценность.

Amazon Web Services, запущенный в 2006 году, предложил принципиально новый подход: вычислительные ресурсы как коммунальная услуга. Подобно тому, как мы не строим собственную электростанцию для питания офиса, разработчики получили возможность «подключиться» к вычислительной инфраструктуре по требованию.

Сегодня рынок облачных услуг представлен несколькими принципиально разными моделями:

- **On-premises** — традиционная модель, всё своё
- **IaaS** (Infrastructure as a Service) — инфраструктура как услуга
- **PaaS** (Platform as a Service) — платформа как услуга
- **SaaS** (Software as a Service) — программное обеспечение как услуга
- **FaaS** (Function as a Service) — функция как услуга
- **BaaS** (Backend as a Service) — бэкенд как услуга

## On-Premises: полная ответственность

В модели on-premises организация самостоятельно владеет и управляет всей инфраструктурой от физического оборудования до приложений.

**За что несёт ответственность организация:**
- Физическое здание и помещение для серверов
- Питание и охлаждение
- Физическая безопасность
- Сетевое оборудование (коммутаторы, маршрутизаторы)
- Серверное оборудование
- Гипервизоры и виртуализация
- Операционные системы
- Middleware (базы данных, веб-серверы)
- Runtime (JVM, Node.js, Python)
- Приложение и данные

**Преимущества on-premises:**
- Полный контроль над данными и инфраструктурой
- Предсказуемые затраты при стабильной нагрузке
- Соответствие жёстким регуляторным требованиям (банки, государственные организации)
- Низкая задержка для критичных систем

**Недостатки:**
- Высокие капитальные затраты (CAPEX)
- Необходимость экспертизы по всему стеку
- Медленная масштабируемость
- Риск простоя при отказе оборудования

## IaaS: инфраструктура как услуга

IaaS — это модель, при которой провайдер предоставляет вычислительные ресурсы (серверы, сеть, хранилище) в виртуализированном виде. Пользователь управляет операционной системой и всем, что выше неё.

**Примеры IaaS:**
- Amazon EC2 (Elastic Compute Cloud)
- Google Compute Engine (GCE)
- Microsoft Azure Virtual Machines
- DigitalOcean Droplets
- Hetzner Cloud

**Что управляет провайдер:**
- Физическое оборудование
- Питание и охлаждение
- Сеть (физический уровень)
- Гипервизор

**Что управляет пользователь:**
- Операционная система (установка, обновления, патчи безопасности)
- Middleware
- Runtime
- Приложение
- Данные

```bash
# Пример: запуск EC2 инстанса через AWS CLI
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.micro \
  --key-name my-key-pair \
  --security-group-ids sg-0123456789abcdef0 \
  --subnet-id subnet-0123456789abcdef0

# После запуска — пользователь сам управляет ОС:
ssh -i my-key.pem ubuntu@<public-ip>
sudo apt update && sudo apt upgrade -y
sudo apt install -y nginx postgresql
```

**Аналогия для понимания:** IaaS — это аренда пустой квартиры. Владелец обеспечивает стены, крышу, электричество и водопровод. Вы сами делаете ремонт, закупаете мебель и всё остальное.

**Когда выбирать IaaS:**
- Нужен полный контроль над ОС (специфические ядерные модули, нестандартные конфигурации)
- Существующие лицензии ПО, привязанные к конкретному железу
- Особые требования к безопасности или compliance
- Нужно «поднять» legacy-приложение в облаке с минимальными изменениями

## PaaS: платформа как услуга

PaaS абстрагирует разработчика от управления инфраструктурой и операционной системой. Разработчик просто загружает код или контейнер, а платформа берёт на себя всё остальное.

**Примеры PaaS:**
- Heroku
- Google App Engine
- Railway
- Render
- Fly.io
- AWS Elastic Beanstalk
- Azure App Service

**Что управляет провайдер:**
- Физическое оборудование
- Операционные системы
- Runtime (Node.js, Python, Java, Ruby, Go...)
- Балансировка нагрузки
- Масштабирование (в некоторых PaaS — автоматическое)
- Резервное копирование (частично)

**Что управляет пользователь:**
- Код приложения
- Зависимости (через Gemfile, package.json, requirements.txt)
- Конфигурация приложения
- Данные

```yaml
# Пример Procfile для Heroku (PaaS)
web: gunicorn app:app --workers 4 --bind 0.0.0.0:$PORT

# Деплой одной командой:
# git push heroku main

# Масштабирование также просто:
# heroku ps:scale web=3
```

```yaml
# Пример app.yaml для Google App Engine
runtime: python39
instance_class: F2

automatic_scaling:
  min_instances: 1
  max_instances: 10
  target_cpu_utilization: 0.6

env_variables:
  DATABASE_URL: "postgresql://..."
```

**Аналогия:** PaaS — это аренда меблированной квартиры. Всё оборудование уже есть: мебель, бытовая техника, Wi-Fi. Вы просто живёте и расставляете свои вещи.

**Преимущества PaaS:**
- Быстрый старт — деплой за минуты
- Нет операционной нагрузки по управлению ОС
- Встроенное автоматическое масштабирование
- Интегрированные логи и мониторинг

**Недостатки PaaS:**
- Меньше контроля над средой выполнения
- Vendor lock-in (особенно проприетарные API)
- Стоимость выше IaaS при больших нагрузках
- Ограничения в кастомизации

## SaaS: программное обеспечение как услуга

SaaS — это готовое приложение, доступное через интернет. Пользователь просто использует сервис; он не занимается ни кодом, ни инфраструктурой.

**Примеры SaaS:**
- Gmail / Google Workspace
- Salesforce
- Figma
- Slack
- Zoom
- Notion
- GitHub

**Что управляет провайдер:**
- Абсолютно всё: железо, сети, ОС, код, базы данных, мониторинг, безопасность, обновления

**Что управляет пользователь:**
- Только данные и конфигурация в рамках возможностей приложения

**Аналогия:** SaaS — это отель. Вы просто живёте там: номер убирают, завтрак подают, лампочки меняют без вашего участия.

**Когда имеет смысл SaaS:**
- Commodity-функциональность (электронная почта, CRM, HR-системы)
- Нет ресурсов на разработку и поддержку собственного решения
- Важна скорость внедрения

## Модель разделённой ответственности (Shared Responsibility Model)

Shared responsibility model — концепция, которую ввёл AWS (и которую теперь используют все крупные провайдеры). Суть: безопасность — это совместная ответственность провайдера и клиента.

```
┌─────────────────────────────────────────────────────────┐
│                   Shared Responsibility                   │
├─────────────────┬───────────────┬────────────────────────┤
│     Слой        │   On-prem     │  IaaS  │ PaaS  │ SaaS  │
├─────────────────┼───────────────┼────────┼───────┼───────┤
│ Приложение      │  Клиент       │ Клиент │Клиент │Провайд│
│ Данные          │  Клиент       │ Клиент │Клиент │Клиент │
│ Runtime         │  Клиент       │ Клиент │Провайд│Провайд│
│ Middleware      │  Клиент       │ Клиент │Провайд│Провайд│
│ ОС              │  Клиент       │ Клиент │Провайд│Провайд│
│ Виртуализация   │  Клиент       │Провайд │Провайд│Провайд│
│ Серверы         │  Клиент       │Провайд │Провайд│Провайд│
│ Сеть            │  Клиент       │Провайд │Провайд│Провайд│
│ Датацентр       │  Клиент       │Провайд │Провайд│Провайд│
└─────────────────┴───────────────┴────────┴───────┴───────┘
```

**Практический пример:** При использовании AWS EC2 (IaaS), AWS гарантирует безопасность гипервизора, но патчить ОС — ваша задача. Многие взломы происходят именно потому, что клиенты не понимают эту границу.

## FaaS: функция как услуга

FaaS — ещё более высокий уровень абстракции. Разработчик пишет отдельные функции, которые выполняются по событиям. Нет понятия «сервер» вообще.

**Примеры FaaS:**
- AWS Lambda
- Google Cloud Functions
- Azure Functions
- Cloudflare Workers
- Vercel Edge Functions

```python
# AWS Lambda функция (Python)
import json
import boto3

def lambda_handler(event, context):
    """
    Triggered by API Gateway, S3, SQS, etc.
    No server management needed.
    """
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Обработка загруженного файла
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=bucket, Key=key)
    content = response['Body'].read()
    
    # Обработка...
    result = process_file(content)
    
    return {
        'statusCode': 200,
        'body': json.dumps({'result': result})
    }
```

**Модель оплаты FaaS:** Оплата только за время выполнения функции (в миллисекундах) и количество вызовов. При нуле трафика — оплата нулевая.

**Ограничения FaaS:**
- Cold start latency (первый запуск медленнее из-за инициализации контейнера)
- Ограничения времени выполнения (Lambda — до 15 минут)
- Stateless — нельзя хранить состояние между вызовами
- Сложность дебаггинга и тестирования локально

## BaaS: Backend-as-a-Service

BaaS предоставляет готовые бэкенд-сервисы: базу данных, аутентификацию, хранилище файлов, push-уведомления — через готовый SDK. Фронтенд-разработчик может создать полноценное приложение без написания серверного кода.

**Примеры BaaS:**
- Firebase (Google) — Firestore, Authentication, Storage, Hosting
- Supabase — PostgreSQL + Auth + Storage (open source)
- AWS Amplify
- Appwrite (self-hosted)

```javascript
// Firebase BaaS — запись в базу без серверного кода
import { initializeApp } from 'firebase/app';
import { getFirestore, collection, addDoc } from 'firebase/firestore';
import { getAuth, signInWithEmailAndPassword } from 'firebase/auth';

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const auth = getAuth(app);

// Аутентификация
await signInWithEmailAndPassword(auth, email, password);

// Запись данных — прямо из браузера!
await addDoc(collection(db, 'orders'), {
  userId: auth.currentUser.uid,
  product: 'laptop',
  price: 999,
  createdAt: new Date()
});
```

**Когда BaaS уместен:**
- MVP, прототипы, стартапы
- Мобильные приложения
- Проекты с небольшими командами без бэкенд-экспертизы

## DBaaS: Database-as-a-Service

DBaaS — предоставление управляемых баз данных. Провайдер берёт на себя установку, настройку, резервное копирование, обновление, репликацию и мониторинг БД.

**Примеры DBaaS:**
- Amazon RDS (MySQL, PostgreSQL, MariaDB, Oracle, SQL Server)
- Amazon Aurora
- Google Cloud SQL
- Azure Database for PostgreSQL
- MongoDB Atlas
- PlanetScale (MySQL-совместимая)
- Neon (serverless PostgreSQL)

```python
# Подключение к RDS — идентично обычному PostgreSQL
import psycopg2

conn = psycopg2.connect(
    host="mydb.cluster-xyz.us-east-1.rds.amazonaws.com",
    port=5432,
    database="myapp",
    user="admin",
    password="secret",
    sslmode="require"  # RDS требует SSL
)
```

**Что берёт на себя DBaaS:**
- Установка и настройка СУБД
- Автоматические резервные копии
- Point-in-time recovery
- Failover (переключение на реплику при сбое основного узла)
- Мониторинг и алерты
- Обновления СУБД (с вашего согласия)

## Сравнение стоимости и ответственности

### Сценарий: веб-приложение с 10 000 пользователей

**On-premises:**
- Сервер: $5,000 единовременно + $200/мес (питание, интернет)
- 1 системный администратор: $80,000/год
- Время на настройку: 2 недели
- Ответственность: 100% на вашей команде

**IaaS (AWS EC2):**
- 2x t3.medium: ~$60/мес
- RDS db.t3.small: ~$30/мес
- Итого: ~$90/мес
- DevOps-инженер: нужен (часть времени)
- Ответственность: ОС, middleware, приложение — ваша

**PaaS (Railway/Render):**
- Web service + PostgreSQL: ~$40/мес
- Нет нужды в DevOps
- Ответственность: только код и данные

**FaaS (Lambda + Aurora Serverless):**
- При 100K запросов/день: ~$5-20/мес
- Нет нужды в DevOps
- Ответственность: код функций и данные

> Важно понимать: PaaS и FaaS дешевле не всегда. При высоких нагрузках IaaS с правильной настройкой может быть значительно выгоднее.

## Vendor Lock-in и как с ним бороться

Vendor lock-in — это зависимость от конкретного провайдера, которая делает переход к другому дорогостоящим или практически невозможным.

**Уровни vendor lock-in (от слабого к сильному):**

1. **Инфраструктурный** (EC2, GCE) — переход сложный, но возможный (образ ВМ, Terraform)
2. **Платформенный** (Heroku buildpacks) — средний lock-in
3. **Сервисный** (AWS Lambda + API Gateway + DynamoDB) — высокий lock-in
4. **Данных** (проприетарные форматы) — критический lock-in

**Стратегии снижения vendor lock-in:**

```python
# Плохо: прямая зависимость от AWS SDK
import boto3

def save_file(content, filename):
    s3 = boto3.client('s3')
    s3.put_object(Bucket='my-bucket', Key=filename, Body=content)

# Хорошо: абстракция через интерфейс
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    @abstractmethod
    def save(self, content: bytes, path: str) -> None:
        pass
    
    @abstractmethod
    def load(self, path: str) -> bytes:
        pass

class S3Storage(StorageBackend):
    def save(self, content: bytes, path: str) -> None:
        boto3.client('s3').put_object(
            Bucket='my-bucket', Key=path, Body=content
        )
    
    def load(self, path: str) -> bytes:
        return boto3.client('s3').get_object(
            Bucket='my-bucket', Key=path
        )['Body'].read()

class GCSStorage(StorageBackend):
    def save(self, content: bytes, path: str) -> None:
        from google.cloud import storage
        storage.Client().bucket('my-bucket').blob(path).upload_from_string(content)
    
    def load(self, path: str) -> bytes:
        from google.cloud import storage
        return storage.Client().bucket('my-bucket').blob(path).download_as_bytes()

# Переключение между провайдерами без изменения бизнес-логики
storage: StorageBackend = S3Storage()  # или GCSStorage()
```

**Инструменты для снижения lock-in:**
- **Terraform** — декларативная инфраструктура, поддерживает все major провайдеры
- **Kubernetes** — единый API для оркестрации контейнеров на любом облаке
- **OpenTelemetry** — вендор-нейтральная observability
- **Crossplane** — управление облачными ресурсами через Kubernetes CRD

## Multi-Cloud стратегии

Multi-cloud — использование нескольких облачных провайдеров одновременно. Мотивы различны:

**Зачем multi-cloud:**
1. **Снижение зависимости** — избегание единой точки отказа на уровне провайдера
2. **Ценовая конкуренция** — переговоры с провайдерами (крупные корпорации)
3. **Географические требования** — некоторые облака лучше в конкретных регионах
4. **Регуляторные требования** — данные должны оставаться в определённых юрисдикциях
5. **Лучший сервис** — AWS для вычислений, Cloudflare для CDN, Snowflake для аналитики

**Сложности multi-cloud:**
- Данные дорого перемещать между облаками (egress fees)
- Разная модель IAM, безопасности, сетевая модель
- Операционная сложность — несколько инструментов, несколько обучений
- Inconsistent SLA

```hcl
# Terraform: управление ресурсами в двух облаках одновременно
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Primary: AWS
resource "aws_instance" "primary" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.medium"
}

# Failover: GCP
resource "google_compute_instance" "failover" {
  name         = "failover-instance"
  machine_type = "e2-medium"
  zone         = "us-central1-a"
  
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }
  
  network_interface {
    network = "default"
  }
}
```

## Выбор модели: стартап vs Enterprise

### Стартап (команда 2-5 человек, MVP стадия)

**Рекомендации:**
- PaaS (Railway, Render, Fly.io) для начала — нет DevOps overhead
- Managed database (PlanetScale, Neon, Supabase) — не тратьте время на настройку PostgreSQL
- BaaS (Firebase, Supabase) для аутентификации и файлов
- Cloudflare Workers/Pages для фронтенда и edge логики

**Принцип:** Каждый час инженера стоит дороже $50-100 в месяц на PaaS. Не экономьте на инфраструктуре на ранних стадиях.

### Среднее приложение (команда 10-50 человек, revenue > $1M)

**Рекомендации:**
- IaaS + Kubernetes или managed Kubernetes (EKS, GKE, AKS)
- Managed databases (RDS, Cloud SQL)
- CDN (Cloudflare) для статики
- Начать думать о cost optimization

```python
# Пример: AWS Cost Explorer API для мониторинга затрат
import boto3
from datetime import datetime, timedelta

ce = boto3.client('ce', region_name='us-east-1')

response = ce.get_cost_and_usage(
    TimePeriod={
        'Start': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
        'End': datetime.now().strftime('%Y-%m-%d')
    },
    Granularity='MONTHLY',
    Metrics=['BlendedCost'],
    GroupBy=[
        {'Type': 'DIMENSION', 'Key': 'SERVICE'}
    ]
)

for group in response['ResultsByTime'][0]['Groups']:
    service = group['Keys'][0]
    cost = float(group['Metrics']['BlendedCost']['Amount'])
    if cost > 10:
        print(f"{service}: ${cost:.2f}")
```

### Enterprise (крупная организация, revenue > $100M)

**Рекомендации:**
- Hybrid cloud (часть on-premises, часть облако)
- Multi-cloud для критичных систем
- FinOps команда для оптимизации затрат
- Private contract с cloud provider (скидки 20-40%)
- Compliance и governance инструменты

## FinOps: оптимизация облачных затрат

FinOps (Financial Operations) — это практика управления облачными затратами, объединяющая инженеров, финансистов и бизнес.

**Основные принципы FinOps:**
1. **Видимость** — знай, за что платишь и почему
2. **Оптимизация** — устраняй неиспользуемые ресурсы
3. **Ответственность** — каждая команда несёт ответственность за свои облачные затраты

**Практические инструменты:**

```bash
# Поиск незапущенных EC2 инстансов (расточительство)
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=stopped" \
  --query "Reservations[*].Instances[*].[InstanceId,Tags[?Key=='Name'].Value|[0],LaunchTime]" \
  --output table

# Поиск неприкреплённых EBS томов (платим за них, но не используем)
aws ec2 describe-volumes \
  --filters "Name=status,Values=available" \
  --query "Volumes[*].[VolumeId,Size,CreateTime]" \
  --output table
```

**Стратегии экономии в IaaS:**
- **Reserved Instances / Committed Use** — предоплата на 1-3 года, скидка 30-60%
- **Spot Instances** — незарезервированные мощности со скидкой 70-90%, но могут быть прерваны
- **Rightsizing** — уменьшение размера инстансов под реальную нагрузку
- **Auto Scaling** — масштабирование по расписанию или метрикам
- **Data Transfer** — оптимизация сетевого трафика (egress дорогой)

```python
# Пример AWS Lambda для автоматического выключения dev-серверов ночью
import boto3

def lambda_handler(event, context):
    """Выключаем dev-серверы в 20:00, включаем в 8:00"""
    ec2 = boto3.client('ec2')
    
    # Найти все инстансы с тегом Environment=dev
    instances = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Environment', 'Values': ['dev']},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    
    instance_ids = [
        i['InstanceId']
        for r in instances['Reservations']
        for i in r['Instances']
    ]
    
    if instance_ids:
        ec2.stop_instances(InstanceIds=instance_ids)
        print(f"Остановлено {len(instance_ids)} dev-инстансов")
    
    return {'stopped': instance_ids}
```

## Итоговое сравнение

| Характеристика | On-prem | IaaS | PaaS | FaaS | SaaS |
|----------------|---------|------|------|------|------|
| Контроль | Максимальный | Высокий | Средний | Низкий | Минимальный |
| DevOps нагрузка | Максимальная | Высокая | Низкая | Минимальная | Нет |
| Стоимость при малой нагрузке | Высокая | Средняя | Средняя | Минимальная | Фиксированная |
| Стоимость при высокой нагрузке | Низкая (CAPEX) | Средняя | Высокая | Высокая | Высокая |
| Vendor lock-in | Нет | Низкий | Средний | Высокий | Максимальный |
| Скорость деплоя | Медленная | Быстрая | Очень быстрая | Мгновенная | Нет деплоя |

## Заключение

Выбор модели облачных услуг — это не технический вопрос, это бизнес-решение. Правильный ответ зависит от размера команды, требований к контролю, budget и compliance-требований. 

Для большинства стартапов разумный путь: начать с PaaS/BaaS → перейти на IaaS + managed services по мере роста → оптимизировать через FinOps → рассмотреть гибридную или multi-cloud стратегию для enterprise.

Главный принцип: **никогда не управляй инфраструктурой, если в этом нет конкурентного преимущества.** Ваше конкурентное преимущество — в коде вашего приложения, а не в настройке nginx или PostgreSQL.

## Литература

1. **Amazon Web Services** — «Shared Responsibility Model»: https://aws.amazon.com/compliance/shared-responsibility-model/
2. **NIST SP 800-145** — «The NIST Definition of Cloud Computing» (Peter Mell, Timothy Grance, 2011): https://csrc.nist.gov/publications/detail/sp/800-145/final
3. **Wiggins, Adam** — «The Twelve-Factor App» (2011): https://12factor.net/
4. **Google Cloud** — «Total Cost of Ownership (TCO) calculator»: https://cloud.google.com/tco-calculator
5. **FinOps Foundation** — «Cloud FinOps» (J.R. Storment, Mike Fuller): https://www.finops.org/
6. **Kleppmann, Martin** — «Designing Data-Intensive Applications». O'Reilly Media, 2017. ISBN: 978-1449373320
7. **Fowler, Martin** — «Patterns of Enterprise Application Architecture». Addison-Wesley, 2002. ISBN: 978-0321127426
8. **AWS Well-Architected Framework** — Cost Optimization Pillar: https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html
9. **Gartner** — «Magic Quadrant for Cloud Infrastructure and Platform Services» (ежегодный отчёт): https://www.gartner.com/en/information-technology/insights/cloud-strategy
10. **HashiCorp** — «Terraform Documentation»: https://developer.hashicorp.com/terraform/docs
