# Twelve-Factor App и стратегии деплоя: blue-green и canary

В 2011 году команда Heroku опубликовала методологию под названием "The Twelve-Factor App". Это был ответ на реальные проблемы, с которыми они столкнулись, управляя сотнями тысяч приложений: неконсистентность между окружениями, сложность масштабирования, хрупкие деплои.

Двенадцать факторов — это не догма и не стандарт. Это набор практик, которые делают приложение:
- Переносимым между окружениями
- Масштабируемым горизонтально
- Удобным для деплоя в облаке
- Понятным для новых разработчиков в команде

## Методология Twelve-Factor

### Фактор I: Кодовая база (Codebase)

**Одно приложение — один репозиторий. Один репозиторий — много деплоев.**

```
Один репозиторий:
  ├── Деплой в development (ветка main, последний коммит)
  ├── Деплой в staging (ветка main, коммит от вчера)
  └── Деплой в production (ветка main, коммит от прошлой недели)
```

Если несколько приложений используют один код — это общая библиотека, которая должна быть вынесена в отдельный пакет. Если один репозиторий порождает несколько приложений — это нарушение фактора.

Monorepo (один репозиторий, несколько сервисов) — допустим, если каждый сервис деплоится независимо.

### Фактор II: Зависимости (Dependencies)

**Явно декларируйте и изолируйте зависимости.**

```python
# requirements.txt или pyproject.toml — явная декларация
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.104.0"
sqlalchemy = "^2.0.23"
pydantic = "^2.5.0"

# НЕ полагайтесь на системные библиотеки
# ПЛОХО: предполагаем, что в системе установлен imagemagick
import subprocess
subprocess.run(["convert", "input.jpg", "output.png"])

# ХОРОШО: явная зависимость
from PIL import Image  # Pillow в requirements.txt
```

```dockerfile
# Docker изолирует зависимости от системы
FROM python:3.11-slim

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Всё включено в образ
```

### Фактор III: Конфигурация (Config)

**Конфигурация хранится в переменных окружения, не в коде.**

Конфигурация — это всё, что различается между окружениями: адреса БД, API-ключи, feature flags.

```python
# ПЛОХО: конфигурация в коде
class Config:
    DATABASE_URL = "postgresql://user:pass@localhost/mydb"
    SECRET_KEY = "my-secret-key"
    DEBUG = True

# ПЛОХО: конфиг-файлы в репозитории
# config/production.yml — нельзя коммитить секреты!
```

```python
# ХОРОШО: всё из переменных окружения
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str  # Обязательно: упадёт если не установлено
    secret_key: str
    debug: bool = False
    max_connections: int = 10
    allowed_hosts: list[str] = ["localhost"]
    
    class Config:
        env_file = ".env"  # Для локальной разработки
        env_file_encoding = "utf-8"

settings = Settings()

# .env (не коммитим в git!)
# DATABASE_URL=postgresql://user:pass@localhost/mydb
# SECRET_KEY=dev-secret-key-not-for-production
# DEBUG=true
```

```bash
# В production — переменные окружения напрямую
export DATABASE_URL="postgresql://user:$(vault read -field=password secret/db)@prod-db:5432/mydb"
export SECRET_KEY="$(vault read -field=secret secret/app)"
```

Тест: можно ли опубликовать код без страха раскрыть секреты? Если да — конфиг правильно вынесен из кода.

### Фактор IV: Сторонние сервисы (Backing Services)

**Обращайтесь к сторонним сервисам (базам данных, очередям, кэшам) как к ресурсам, подключаемым через URL.**

Смена PostgreSQL на Amazon RDS не должна требовать изменения кода — только изменения `DATABASE_URL`.

```python
# ХОРОШО: все backing services через абстракцию URL
from sqlalchemy import create_engine
from redis import Redis
import boto3

# Можно менять provider без изменения кода
db = create_engine(os.environ["DATABASE_URL"])
cache = Redis.from_url(os.environ["REDIS_URL"])
storage = boto3.client("s3",
    endpoint_url=os.environ.get("S3_ENDPOINT_URL")  # LocalStack для тестов
)
```

### Фактор V: Сборка, релиз, запуск (Build, release, run)

**Строго разделяйте стадии сборки и запуска.**

```
Код → [Сборка] → Артефакт → [Релиз] → Релиз = артефакт + конфиг → [Запуск] → Процессы
```

```yaml
# GitHub Actions: явное разделение стадий
jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: myregistry/app:${{ github.sha }}
  
  deploy-staging:
    needs: build
    steps:
      - name: Deploy to staging
        run: |
          # Release = image + staging config
          helm upgrade app ./chart \
            --set image.tag=${{ github.sha }} \
            --values values-staging.yaml
  
  deploy-production:
    needs: deploy-staging
    environment: production  # Требует ручного подтверждения
    steps:
      - name: Deploy to production
        run: |
          helm upgrade app ./chart \
            --set image.tag=${{ github.sha }} \
            --values values-production.yaml
```

Важно: каждый релиз имеет неизменяемый ID (SHA коммита или timestamp). Нельзя изменить уже запущенный релиз — только создать новый.

### Фактор VI: Процессы (Processes)

**Приложение выполняется как один или несколько stateless-процессов.**

Процессы не хранят состояние. Данные — в backing services (PostgreSQL, Redis).

```python
# ПЛОХО: состояние в памяти процесса
class SessionManager:
    _sessions: dict = {}  # Хранится в одном процессе!
    
    def create_session(self, user_id: int) -> str:
        token = generate_token()
        self._sessions[token] = user_id  # Пропадёт при рестарте!
        return token

# ХОРОШО: состояние в Redis
import redis

class SessionManager:
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client
    
    def create_session(self, user_id: int) -> str:
        token = generate_token()
        # Сессия выживает при рестарте процесса
        self._redis.setex(f"session:{token}", 86400, str(user_id))
        return token
    
    def get_user_id(self, token: str) -> int | None:
        value = self._redis.get(f"session:{token}")
        return int(value) if value else None
```

Sticky sessions (маршрутизация пользователя всегда к одному серверу) — нарушение этого фактора.

### Фактор VII: Привязка портов (Port Binding)

**Приложение самодостаточно и принимает трафик через порт.**

Приложение не зависит от внешнего веб-сервера (Apache, Nginx) для запуска. Оно само встраивает HTTP-сервер.

```python
# FastAPI/Uvicorn — самодостаточный сервер
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
```

```go
// Go HTTP сервер встроен в стандартную библиотеку
func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }
    
    mux := http.NewServeMux()
    mux.HandleFunc("/", handler)
    
    log.Fatal(http.ListenAndServe(":"+port, mux))
}
```

### Фактор VIII: Параллелизм (Concurrency)

**Масштабируйтесь горизонтально через процессы.**

Twelve-Factor приложение масштабируется добавлением инстансов (горизонтальное), а не увеличением ресурсов одного сервера (вертикальное).

```
Process types:
  web: обрабатывает HTTP (5 инстансов)
  worker: обрабатывает очередь (10 инстансов)
  scheduler: запускает cron-задачи (1 инстанс)
```

```yaml
# Kubernetes HPA — автоматическое горизонтальное масштабирование
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  scaleTargetRef:
    name: web-deployment
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        averageUtilization: 70
```

### Фактор IX: Утилизируемость (Disposability)

**Быстрый запуск и graceful shutdown.**

```python
import signal
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: инициализация
    await db.connect()
    await cache.connect()
    
    yield  # Приложение работает
    
    # Shutdown: graceful завершение
    # 1. Перестать принимать новые запросы (kubelet отправит SIGTERM)
    # 2. Закончить обработку текущих запросов
    # 3. Закрыть соединения
    await asyncio.sleep(5)  # Даём время LB убрать из ротации
    await db.close()
    await cache.close()

app = FastAPI(lifespan=lifespan)

# Для воркеров очереди — graceful shutdown
class Worker:
    def __init__(self):
        self._running = True
        signal.signal(signal.SIGTERM, self._handle_sigterm)
    
    def _handle_sigterm(self, signum, frame):
        print("SIGTERM received, finishing current task...")
        self._running = False
    
    async def run(self):
        async for message in queue.consume():
            if not self._running:
                # Вернуть сообщение в очередь
                await message.nack()
                break
            
            await self.process(message)
            await message.ack()
```

Быстрый старт важен для:
- Масштабирования под нагрузкой (новые инстансы должны быть готовы быстро)
- Rolling update (новые поды заменяют старые)
- Восстановления после сбоев

### Фактор X: Паритет dev/prod (Dev/prod parity)

**Development, staging и production должны быть как можно ближе друг к другу.**

```yaml
# docker-compose.yml — те же backing services что и в prod
services:
  app:
    build: .
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
  
  postgres:
    image: postgres:16  # Та же версия что и в prod!
    
  redis:
    image: redis:7      # Та же версия что и в prod!
```

Классические расхождения, приводящие к "works on my machine":
- SQLite в dev, PostgreSQL в prod → разный SQL-диалект
- Локальная файловая система в dev, S3 в prod → разная семантика
- Одна реплика в dev, кластер в prod → проблемы с конкурентным доступом

### Фактор XI: Логи (Logs)

**Рассматривайте логи как потоки событий.**

Приложение не должно управлять ротацией логов или записью в файлы. Оно пишет в stdout/stderr, а среда выполнения (Kubernetes, systemd, Docker) перехватывает и отправляет по назначению.

```python
import logging
import sys

# Все логи в stdout в JSON
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(message)s'
)
```

```yaml
# Kubernetes автоматически собирает stdout/stderr
# Fluentd/Promtail пересылает в Loki/Elasticsearch
containers:
- name: app
  # Не нужно настраивать логирование в файл
  # Просто пишем в stdout
```

### Фактор XII: Административные процессы (Admin processes)

**Запускайте административные/управленческие задачи как одноразовые процессы.**

```bash
# Миграции БД — одноразовый процесс
kubectl run migrations --image=myapp:1.2.3 \
  --restart=Never \
  -- python manage.py migrate

# Или через Kubernetes Job
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate-1.2.3
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: migrate
        image: myregistry/app:1.2.3
        command: ["python", "manage.py", "migrate"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
  backoffLimit: 3
```

## Стратегии деплоя: как обновлять без даунтайма

### Проблема: классический деплой

Старый подход: остановить приложение → задеплоить новую версию → запустить. Минуты даунтайма при каждом деплое.

Современные системы требуют zero-downtime deployment. Для этого есть несколько стратегий.

### Recreate: самый простой (с даунтаймом)

Убить все старые инстансы → запустить новые. Даунтайм есть, но подходит для несовместимых изменений БД или когда это допустимо.

```yaml
# Kubernetes
strategy:
  type: Recreate
```

### Rolling Update: постепенная замена

Заменяем старые поды новыми постепенно. Zero-downtime, но в момент деплоя работают обе версии.

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1          # Создаём +1 новый под
    maxUnavailable: 0    # 0 старых удаляем до готовности нового
```

Временно работают обе версии → API должен быть обратно совместим.

### Blue-Green Deployment

**Два идентичных окружения: Blue (текущий prod) и Green (новая версия).**

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │                              │
    ┌─────────▼──────────┐        ┌─────────▼──────────┐
    │    Blue (v1.0)     │        │    Green (v1.1)     │
    │  ████████████████  │        │  ████████████████  │
    │    3 replicas      │        │    3 replicas      │
    │    ACTIVE          │        │    STANDBY         │
    └────────────────────┘        └────────────────────┘
```

Процесс:
1. Текущая версия (blue) получает весь трафик
2. Деплоим новую версию (green), трафик не идёт
3. Тестируем green
4. Переключаем балансировщик: весь трафик → green
5. Blue остаётся как резерв для быстрого отката

```bash
# Реализация через Kubernetes Service selector

# Текущий state: сервис указывает на blue
kubectl get service app-service -o yaml
# spec:
#   selector:
#     app: my-app
#     version: blue  # ← Трафик идёт на blue

# Деплоим green
kubectl apply -f deployment-green.yaml

# Ждём готовности
kubectl rollout status deployment/app-green

# Запускаем smoke tests
./run-smoke-tests.sh https://green.internal.example.com

# Переключаем трафик
kubectl patch service app-service -p '{"spec":{"selector":{"version":"green"}}}'

# Если что-то пошло не так — откат за секунды
kubectl patch service app-service -p '{"spec":{"selector":{"version":"blue"}}}'
```

```yaml
# Полная реализация blue-green через Helm
# values.yaml
activeColor: blue  # Переменная для переключения

---
# templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}
spec:
  selector:
    app: {{ .Release.Name }}
    color: {{ .Values.activeColor }}
  ports:
  - port: 80
    targetPort: 8080

---
# templates/deployment-blue.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-blue
spec:
  replicas: {{ if eq .Values.activeColor "blue" }}3{{ else }}0{{ end }}
  selector:
    matchLabels:
      app: {{ .Release.Name }}
      color: blue
  # ...

---
# templates/deployment-green.yaml  
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-green
spec:
  replicas: {{ if eq .Values.activeColor "green" }}3{{ else }}0{{ end }}
  selector:
    matchLabels:
      app: {{ .Release.Name }}
      color: green
```

**Преимущества blue-green:**
- Мгновенный откат (просто переключить балансировщик)
- Легкое тестирование перед переключением
- Нет переходного периода с двумя версиями

**Недостатки:**
- Требует двойных ресурсов (оба окружения работают одновременно)
- Сложнее с базами данных (обе версии должны работать с одной БД)
- Не подходит для постепенного тестирования

### Canary Release: постепенное развёртывание

Canary (канарейка) — отсылка к шахтёрам, которые брали канарейку в шахту: если газ, птица умрёт первой.

**Идея**: направить небольшой процент трафика на новую версию, постепенно увеличивая.

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │ 95%                    5%   │
    ┌─────────▼──────────┐        ┌─────────▼──────────┐
    │    Stable (v1.0)   │        │   Canary (v1.1)    │
    │    9 replicas      │        │    1 replica       │
    └────────────────────┘        └────────────────────┘
```

#### Canary через Nginx Ingress

```yaml
# ingress-stable.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-stable
  annotations:
    nginx.ingress.kubernetes.io/canary: "false"
spec:
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /
        backend:
          service:
            name: app-stable
            port: {number: 80}

---
# ingress-canary.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-canary
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "5"  # 5% трафика
    # Или по заголовку:
    # nginx.ingress.kubernetes.io/canary-by-header: "X-Canary"
    # nginx.ingress.kubernetes.io/canary-by-header-value: "true"
spec:
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /
        backend:
          service:
            name: app-canary
            port: {number: 80}
```

```bash
# Скрипт постепенного увеличения процента
for weight in 5 10 25 50 75 100; do
    echo "Setting canary weight to ${weight}%"
    
    kubectl annotate ingress app-canary \
        nginx.ingress.kubernetes.io/canary-weight="${weight}" \
        --overwrite
    
    # Ждём и проверяем метрики
    sleep 300  # 5 минут
    
    # Проверяем error rate канареи
    error_rate=$(promtool query instant \
        'sum(rate(http_requests_total{version="canary",status=~"5.."}[5m])) / sum(rate(http_requests_total{version="canary"}[5m]))' \
        | grep value | awk '{print $2}')
    
    if (( $(echo "$error_rate > 0.01" | bc -l) )); then
        echo "Error rate ${error_rate} exceeds 1%, rolling back!"
        kubectl annotate ingress app-canary \
            nginx.ingress.kubernetes.io/canary-weight="0" \
            --overwrite
        exit 1
    fi
    
    echo "Error rate ${error_rate} OK, continuing..."
done

echo "Canary deployment successful! Switching all traffic..."
# Обновляем stable deployment и убираем canary
```

#### Canary через Argo Rollouts

Argo Rollouts — специализированный контроллер для продвинутых стратегий деплоя:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: payment-service
spec:
  replicas: 10
  selector:
    matchLabels:
      app: payment
  
  strategy:
    canary:
      # Шаги с автоматической паузой и ручным подтверждением
      steps:
      - setWeight: 5        # 5% трафика на canary
      - pause: {duration: 5m}  # Ждём 5 минут
      
      - setWeight: 20
      - pause: {duration: 10m}
      
      - setWeight: 50
      - pause: {}           # Ручное подтверждение (!!)
      
      - setWeight: 100
      
      # Автоматический анализ метрик
      analysis:
        templates:
        - templateName: success-rate
        startingStep: 1
        args:
        - name: service-name
          value: payment-service
      
      # Anti-affinity: canary на отдельных нодах
      canaryMetadata:
        annotations:
          role: canary
        labels:
          role: canary
      stableMetadata:
        annotations:
          role: stable
        labels:
          role: stable

---
# AnalysisTemplate: когда автоматически откатывать
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  args:
  - name: service-name
  
  metrics:
  - name: success-rate
    interval: 1m
    successCondition: result[0] >= 0.99  # 99% успешных запросов
    failureLimit: 3
    provider:
      prometheus:
        address: http://prometheus:9090
        query: |
          sum(rate(http_requests_total{
            service="{{args.service-name}}",
            status!~"5.."
          }[5m])) 
          / 
          sum(rate(http_requests_total{
            service="{{args.service-name}}"
          }[5m]))
```

### Feature Flags: деплой без релиза

Feature flags (флаги функций) позволяют деплоить код в prod, но не включать его для пользователей. Это разделяет "деплой" и "релиз".

```python
from launchdarkly_client import LDClient, Context

class FeatureFlag:
    def __init__(self, client: LDClient):
        self._client = client
    
    def is_enabled(self, flag_key: str, user_id: int) -> bool:
        context = Context.builder(str(user_id)).build()
        return self._client.variation(flag_key, context, False)
    
    def get_variant(self, flag_key: str, user_id: int) -> str:
        context = Context.builder(str(user_id)).build()
        return self._client.variation(flag_key, context, "control")

# Использование
flags = FeatureFlag(ld_client)

@app.post("/api/checkout")
async def checkout(user_id: int, cart: Cart):
    if flags.is_enabled("new-checkout-flow", user_id):
        # Новый код — видят только 5% пользователей
        return await new_checkout_flow(cart)
    else:
        # Старый код — видят 95%
        return await old_checkout_flow(cart)
```

**Типы флагов:**
- **Release flags**: включить фичу для % пользователей (canary через код)
- **Experiment flags**: A/B тестирование
- **Ops flags**: аварийное отключение ("kill switch")
- **Permission flags**: доступ для определённых пользователей/групп

```python
# Kill switch — быстрое отключение проблемной фичи без деплоя
@app.middleware("http")
async def circuit_breaker_middleware(request: Request, call_next):
    if flags.is_enabled("maintenance-mode", 0):
        return JSONResponse(
            {"error": "Service temporarily unavailable"},
            status_code=503
        )
    return await call_next(request)
```

## Database migrations при деплое

Самая сложная часть zero-downtime деплоя — изменения схемы БД. Обе версии приложения (старая и новая) должны работать с одной БД.

**Expand-Contract паттерн:**

```
1. Expand: добавляем новое поле (обе версии работают)
2. Migrate: переносим данные в новое поле
3. Contract: удаляем старое поле (после полного деплоя новой версии)
```

```sql
-- Шаг 1: Expand (совместимо с v1 и v2)
-- НЕЛЬЗЯ: ALTER TABLE users RENAME COLUMN email TO email_address;
-- v1 всё ещё читает 'email', v2 ждёт 'email_address'

-- ПРАВИЛЬНО: Добавляем новую колонку
ALTER TABLE users ADD COLUMN email_address VARCHAR(255);

-- Шаг 2: Деплоим v2 (пишет в обе колонки)
-- UPDATE users SET email_address = email WHERE email_address IS NULL;

-- Шаг 3: Contract (после полного перехода на v2)
ALTER TABLE users DROP COLUMN email;

-- Не добавляйте NOT NULL без DEFAULT в один шаг!
-- ПЛОХО (блокирует таблицу):
-- ALTER TABLE orders ADD COLUMN status VARCHAR(20) NOT NULL;

-- ХОРОШО (3 миграции):
-- 1. ADD COLUMN status VARCHAR(20) DEFAULT 'pending';
-- 2. UPDATE orders SET status = 'pending' WHERE status IS NULL;
-- 3. ALTER COLUMN status SET NOT NULL;
```

## Чеклист для production deployment

```bash
#!/bin/bash
# Pre-deployment checklist

echo "=== Pre-deployment checks ==="

# 1. Все тесты зелёные
pytest && echo "✓ Tests passed" || exit 1

# 2. Нет конфликтов с prod конфигом
diff <(kubectl get configmap app-config -o yaml) configs/configmap.yaml \
  && echo "✓ Config unchanged" \
  || echo "⚠ Config will change"

# 3. Есть plan для отката
echo "✓ Rollback: helm rollback app $(helm history app -n prod --max 1 -o json | jq '.[].revision')"

# 4. Оповестить команду
curl -X POST $SLACK_WEBHOOK -d '{"text": "Deploying version '$VERSION' to production"}'

# 5. Проверить error budget
error_budget=$(curl -s prometheus:9090/api/v1/query \
  -G --data-urlencode 'query=error_budget_remaining{service="app"}' \
  | jq -r '.data.result[0].value[1]')

if (( $(echo "$error_budget < 10" | bc -l) )); then
  echo "⚠ Error budget < 10%. Consider postponing deploy."
  read -p "Continue? (yes/no): " confirm
  [[ $confirm != "yes" ]] && exit 1
fi

echo "=== Starting deployment ==="
```

## Литература

1. **The Twelve-Factor App**. Wiggins A. Heroku, 2011. — https://12factor.net/ — Оригинальная методология.

2. Richardson C. **Microservices Patterns**. Manning Publications, 2018. — Главы о деплое и migration паттернах.

3. **Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation**. Humble J., Farley D. Addison-Wesley, 2010.

4. **Argo Rollouts Documentation**. — https://argoproj.github.io/rollouts/

5. **Kubernetes Documentation: Deployments**. — https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

6. Forsgren N., Humble J., Kim G. **Accelerate: The Science of Lean Software and DevOps**. IT Revolution Press, 2018. — Исследование практик CI/CD и их влияния на производительность.

7. Hodgson P. **Feature Toggles (aka Feature Flags)**. Martin Fowler's Blog, 2017. — https://martinfowler.com/articles/feature-toggles.html

8. **LaunchDarkly Documentation: Feature flags best practices**. — https://docs.launchdarkly.com/

9. Lardinois F. **Blue-Green Deployments on AWS**. AWS Blog, 2017.

10. **Google SRE Book: Release Engineering**. — https://sre.google/sre-book/release-engineering/
