# Docker и Kubernetes: контейнеризация и оркестрация

В 2013 году Solomon Hykes показал на dotCloud пятиминутное демо: `docker run ubuntu echo "hello world"`. Контейнер запустился за секунды. Это изменило индустрию.

До Docker деплой приложения был болью: "работает на моей машине" — классическая проблема. Вы разрабатываете на macOS, в CI Ubuntu 18.04, в проде CentOS 7. Версии Python разные, библиотеки разные, переменные окружения разные. Docker упаковал приложение вместе со всеми зависимостями в единый портативный образ.

Но запуск тысяч контейнеров на сотнях машин — это уже другая задача. Здесь появился Kubernetes.

## Что такое контейнер

Контейнер — это изолированный процесс. Не виртуальная машина — никакого второго ядра, никакого гипервизора. Контейнер использует ядро хостовой машины, но изолирован через два ключевых механизма Linux:

**namespaces** — изолируют видимость:
- `pid` — контейнер видит только свои процессы
- `net` — собственный сетевой стек (свой lo, eth0, IP)
- `mnt` — собственное дерево файловой системы
- `uts` — свой hostname
- `user` — отображение UID/GID
- `ipc` — изолированные очереди сообщений

**cgroups** (control groups) — ограничивают ресурсы:
- CPU: `cpu.shares`, `cpu.quota`
- Memory: `memory.limit_in_bytes`
- I/O: `blkio.weight`
- Network bandwidth

```bash
# Вручную создаём контейнер через Linux API (без Docker)
# Создаём namespace
unshare --pid --fork --mount-proc bash

# Внутри нового namespace — видим только один процесс
ps aux
# PID TTY          TIME CMD
# 1   pts/0    00:00:00 bash
```

Docker — это удобный интерфейс над этими механизмами ядра.

## Docker: архитектура

```
┌─────────────────────────────────────────────────────┐
│                   Docker Client                      │
│               docker build/run/push                  │
└────────────────────────┬────────────────────────────┘
                         │ REST API / Unix socket
                         ▼
┌─────────────────────────────────────────────────────┐
│                  Docker Daemon (dockerd)              │
│                                                     │
│  ┌────────────┐  ┌────────────┐  ┌───────────────┐  │
│  │  Images    │  │ Containers │  │   Networks    │  │
│  │  (layers) │  │(processes) │  │   Volumes     │  │
│  └────────────┘  └────────────┘  └───────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│              containerd (OCI runtime)                │
│                     runc                             │
└─────────────────────────────────────────────────────┘
```

### Union filesystem: слои образов

Docker образ — это стек слоёв (layers). Каждая инструкция в Dockerfile создаёт слой:

```dockerfile
FROM ubuntu:22.04          # layer 1: базовый образ (100MB)
RUN apt-get update         # layer 2: кэш apt (20MB)
RUN apt-get install -y python3  # layer 3: Python (60MB)
COPY requirements.txt .    # layer 4: файл (1KB)
RUN pip install -r requirements.txt  # layer 5: зависимости (50MB)
COPY . .                   # layer 6: ваш код (1MB)
CMD ["python", "app.py"]   # layer 7: метаданные
```

Слои **иммутабельны** и **разделяются** между образами. Если два образа используют одинаковый базовый образ, он хранится один раз.

При запуске контейнера добавляется **tонкий writable layer** поверх read-only слоёв. Это называется **Copy-on-Write (CoW)**.

### Многоэтапная сборка (Multi-stage build)

Одна из самых важных оптимизаций — отделить сборку от runtime:

```dockerfile
# Stage 1: Builder — компилируем приложение
FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
# Кэшируем зависимости отдельно (слой не меняется если go.sum не менялся)
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o server ./cmd/server

# Stage 2: Runtime — только бинарник
FROM scratch  # Полностью пустой образ!
# Или FROM alpine:3.18 если нужны системные утилиты

COPY --from=builder /app/server /server
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

EXPOSE 8080
USER 1000  # Не root!
ENTRYPOINT ["/server"]
```

Результат: образ 10MB вместо 400MB с Go toolchain.

### Best practices для Dockerfile

```dockerfile
FROM python:3.11-slim  # slim, не full

# 1. Запускать не под root
RUN useradd --create-home appuser

WORKDIR /app

# 2. Сначала копировать только зависимости (лучший кэш)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Потом копировать код
COPY --chown=appuser:appuser . .

USER appuser

# 4. HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 5. Явный PORT и сигнал завершения
EXPOSE 8080
STOPSIGNAL SIGTERM

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Docker Compose для локальной разработки

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - .:/app          # Hot reload
      - /app/__pycache__  # Не маунтим кэш
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/mydb
      - REDIS_URL=redis://redis:6379
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d  # Инициализация
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d mydb"]
      interval: 5s
      timeout: 5s
      retries: 5
    
  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

volumes:
  postgres_data:
```

## Kubernetes: оркестрация контейнеров

Kubernetes (k8s, "кибернетика" по-гречески) решает следующие задачи:
- Запуск контейнеров на кластере машин
- Перезапуск упавших контейнеров
- Масштабирование по нагрузке
- Rolling updates без даунтайма
- Service discovery и load balancing
- Управление конфигурацией и секретами

### Архитектура кластера

```
┌──────────────────────────────────────────────────────────────┐
│                    Control Plane                              │
│                                                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  │
│  │  API     │  │  etcd     │  │Scheduler │  │Controller │  │
│  │  Server  │  │(key-value)│  │          │  │ Manager   │  │
│  └──────────┘  └───────────┘  └──────────┘  └───────────┘  │
└──────────────────────────────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
┌───────────────────┐     ┌───────────────────┐
│     Worker Node   │     │     Worker Node   │
│                   │     │                   │
│  ┌─────────────┐  │     │  ┌─────────────┐  │
│  │   kubelet   │  │     │  │   kubelet   │  │
│  └─────────────┘  │     │  └─────────────┘  │
│  ┌─────────────┐  │     │  ┌─────────────┐  │
│  │  kube-proxy │  │     │  │  kube-proxy │  │
│  └─────────────┘  │     │  └─────────────┘  │
│  ┌───┐  ┌───┐     │     │  ┌───┐  ┌───┐     │
│  │Pod│  │Pod│     │     │  │Pod│  │Pod│     │
│  └───┘  └───┘     │     │  └───┘  └───┘     │
└───────────────────┘     └───────────────────┘
```

**Control Plane** (master):
- **API Server**: единая точка входа для всего (kubectl, controllers, nodes)
- **etcd**: распределённое key-value хранилище — "мозг" кластера
- **Scheduler**: выбирает Node для каждого Pod
- **Controller Manager**: наблюдает за состоянием и приближает его к желаемому

**Worker Nodes**:
- **kubelet**: агент на каждой ноде, запускает контейнеры
- **kube-proxy**: сетевые правила для Service
- **Container Runtime**: containerd, CRI-O

### Основные абстракции

**Pod** — минимальная единица в Kubernetes. Один или несколько контейнеров, разделяющих сеть и хранилище:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: payment-pod
  labels:
    app: payment
    version: v1.2.3
spec:
  containers:
  - name: payment
    image: myregistry/payment:1.2.3
    ports:
    - containerPort: 8080
    
    # Ресурсные лимиты — ОБЯЗАТЕЛЬНО указывать
    resources:
      requests:        # Гарантированные ресурсы
        memory: "128Mi"
        cpu: "100m"    # 100 millicores = 0.1 CPU
      limits:          # Максимум
        memory: "256Mi"
        cpu: "500m"
    
    # Пробы здоровья
    livenessProbe:     # Перезапустить если падает
      httpGet:
        path: /health/live
        port: 8080
      initialDelaySeconds: 30
      periodSeconds: 10
      failureThreshold: 3
    
    readinessProbe:    # Трафик только если готов
      httpGet:
        path: /health/ready
        port: 8080
      initialDelaySeconds: 5
      periodSeconds: 5
    
    # Переменные окружения
    env:
    - name: DATABASE_URL
      valueFrom:
        secretKeyRef:
          name: db-secret
          key: url
    - name: LOG_LEVEL
      valueFrom:
        configMapKeyRef:
          name: app-config
          key: log_level
```

**Deployment** — управляет репликами Pod и rolling updates:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: production
spec:
  replicas: 3
  
  selector:
    matchLabels:
      app: payment
  
  # Стратегия обновления
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # +1 лишний pod во время обновления
      maxUnavailable: 0  # 0 недоступных (zero-downtime)
  
  template:
    metadata:
      labels:
        app: payment
        version: "1.2.3"
    spec:
      # Распределение по зонам
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: payment
      
      containers:
      - name: payment
        image: myregistry/payment:1.2.3
        # ... (как выше)
      
      # Graceful shutdown
      terminationGracePeriodSeconds: 60
```

**Service** — стабильный endpoint для Pod-ов (Pod-ы создаются и уничтожаются, меняют IP):

```yaml
apiVersion: v1
kind: Service
metadata:
  name: payment-service
spec:
  selector:
    app: payment  # Выбираем Pod-ы по этому лейблу
  
  ports:
  - name: http
    port: 80           # Порт Service
    targetPort: 8080   # Порт контейнера
  
  type: ClusterIP  # Только внутри кластера
  # type: NodePort — открывает порт на каждой ноде
  # type: LoadBalancer — создаёт облачный балансировщик
```

**Ingress** — HTTP(S) маршрутизация снаружи в кластер:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  tls:
  - hosts:
    - api.example.com
    secretName: api-tls-cert
  
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /api/payments
        pathType: Prefix
        backend:
          service:
            name: payment-service
            port:
              number: 80
      - path: /api/orders
        pathType: Prefix
        backend:
          service:
            name: order-service
            port:
              number: 80
```

### ConfigMap и Secret

```yaml
# ConfigMap — несекретная конфигурация
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  log_level: "info"
  max_connections: "100"
  feature_flags: |
    new_checkout: true
    beta_api: false
  application.yaml: |
    server:
      port: 8080
      timeout: 30s

---
# Secret — зашифрованные данные (base64 в etcd)
apiVersion: v1
kind: Secret
metadata:
  name: db-secret
type: Opaque
stringData:  # stringData автоматически base64-кодирует
  url: "postgresql://user:secretpassword@postgres:5432/mydb"
  password: "secretpassword"
```

Важно: стандартные Kubernetes Secrets хранятся в etcd в base64 (не зашифрованы!). Для production используйте:
- **Sealed Secrets** (Bitnami) — шифрование в Git
- **External Secrets Operator** — интеграция с AWS Secrets Manager, HashiCorp Vault
- **Kubernetes encryption at rest** — шифрование etcd

### Автомасштабирование

**Horizontal Pod Autoscaler (HPA)**:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: payment-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: payment-service
  
  minReplicas: 3
  maxReplicas: 20
  
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  
  # Кастомные метрики (через Prometheus Adapter)
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "1000"
  
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300  # Не уменьшать 5 минут
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
```

**Vertical Pod Autoscaler (VPA)** — автоматически подбирает requests/limits:

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: payment-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: payment-service
  updatePolicy:
    updateMode: "Auto"  # "Off" для рекомендаций без применения
```

### StatefulSet: для stateful приложений

Обычный Deployment не подходит для баз данных — Pod-ы получают случайные имена и не имеют стабильных дисков. StatefulSet решает это:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres  # Headless Service для stable DNS
  replicas: 3
  
  selector:
    matchLabels:
      app: postgres
  
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:16
        ports:
        - containerPort: 5432
        
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
        
        env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name  # postgres-0, postgres-1, postgres-2
  
  # Уникальный PersistentVolume для каждого Pod
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 100Gi
```

Pod-ы получают стабильные имена: `postgres-0`, `postgres-1`, `postgres-2`. DNS: `postgres-0.postgres.namespace.svc.cluster.local`.

### Namespace: изоляция окружений

```yaml
# Создание namespace
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    env: production

---
# ResourceQuota: ограничения для namespace
apiVersion: v1
kind: ResourceQuota
metadata:
  name: production-quota
  namespace: production
spec:
  hard:
    requests.cpu: "20"
    requests.memory: 40Gi
    limits.cpu: "40"
    limits.memory: 80Gi
    pods: "100"

---
# LimitRange: дефолтные limits для Pod-ов без явных limits
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: production
spec:
  limits:
  - default:
      memory: 256Mi
      cpu: 200m
    defaultRequest:
      memory: 128Mi
      cpu: 100m
    type: Container
```

### RBAC: управление доступом

```yaml
# ServiceAccount для приложения
apiVersion: v1
kind: ServiceAccount
metadata:
  name: payment-service
  namespace: production

---
# Role: что можно делать в namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: payment-role
  namespace: production
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]

---
# RoleBinding: привязка Role к ServiceAccount
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payment-rolebinding
  namespace: production
subjects:
- kind: ServiceAccount
  name: payment-service
  namespace: production
roleRef:
  kind: Role
  name: payment-role
  apiGroup: rbac.authorization.k8s.io
```

## Жизненный цикл деплоя

### Helm: пакетный менеджер для Kubernetes

Helm — это "apt/npm для Kubernetes". Позволяет упаковать набор YAML-манифестов в chart и параметризировать их:

```
mychart/
├── Chart.yaml          # Метаданные
├── values.yaml         # Дефолтные значения
├── values-production.yaml  # Переопределения для prod
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── ingress.yaml
    ├── configmap.yaml
    └── hpa.yaml
```

```yaml
# values.yaml
replicaCount: 2
image:
  repository: myregistry/payment
  tag: "latest"
  pullPolicy: IfNotPresent

resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "500m"

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "mychart.fullname" . }}
  labels:
    {{- include "mychart.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
      - name: {{ .Chart.Name }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        resources:
          {{- toYaml .Values.resources | nindent 12 }}
```

```bash
# Установка chart
helm install payment ./mychart -f values-production.yaml -n production

# Обновление
helm upgrade payment ./mychart -f values-production.yaml -n production

# Откат
helm rollback payment 1 -n production

# История
helm history payment -n production
```

### Kustomize: наложение конфигураций

Альтернатива Helm без шаблонов — просто patch-файлы:

```
base/
├── kustomization.yaml
├── deployment.yaml
└── service.yaml

overlays/
├── development/
│   ├── kustomization.yaml
│   └── replica-patch.yaml
└── production/
    ├── kustomization.yaml
    └── replica-patch.yaml
```

```yaml
# overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../../base

images:
- name: payment
  newTag: "1.2.3"

patches:
- path: replica-patch.yaml

# overlays/production/replica-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 5
```

```bash
kubectl apply -k overlays/production/
```

## Networking в Kubernetes

### DNS-based service discovery

Каждый Service получает DNS-запись:
```
payment-service.production.svc.cluster.local
│               │          │   │
Service name    Namespace  │   Domain
                           svc.cluster.local
```

Из пода в том же namespace можно обращаться просто `payment-service:80`.

### NetworkPolicy: файрвол для Pod-ов

По умолчанию все Pod-ы в кластере могут общаться между собой. NetworkPolicy ограничивает это:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-network-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: payment
  
  policyTypes:
  - Ingress
  - Egress
  
  ingress:
  # Разрешаем входящий трафик только от API Gateway
  - from:
    - podSelector:
        matchLabels:
          app: api-gateway
    ports:
    - protocol: TCP
      port: 8080
  
  egress:
  # Разрешаем только к базе и Redis
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
  - to:
    - podSelector:
        matchLabels:
          app: redis
    ports:
    - protocol: TCP
      port: 6379
```

## Производственные практики

### Pod Disruption Budget

Гарантирует минимум доступных Pod-ов при обслуживании нод:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: payment-pdb
spec:
  minAvailable: 2  # Или maxUnavailable: 1
  selector:
    matchLabels:
      app: payment
```

### Init Containers

Запускаются до основного контейнера:

```yaml
spec:
  initContainers:
  # Ждём базу данных
  - name: wait-for-db
    image: busybox:1.35
    command: ['sh', '-c', 
      'until nc -z postgres 5432; do echo waiting for postgres; sleep 2; done']
  
  # Запускаем миграции
  - name: run-migrations
    image: myregistry/payment:1.2.3
    command: ["python", "manage.py", "migrate"]
    env:
    - name: DATABASE_URL
      valueFrom:
        secretKeyRef:
          name: db-secret
          key: url
  
  containers:
  - name: payment
    # ... основной контейнер запускается только после init-контейнеров
```

### Affinity и Tolerations

```yaml
spec:
  # Node Affinity: предпочитаем ноды с SSD
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 1
        preference:
          matchExpressions:
          - key: storage-type
            operator: In
            values: ["ssd"]
    
    # Pod Anti-affinity: не размещать два pod на одном узле
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values: ["payment"]
        topologyKey: kubernetes.io/hostname
  
  # Tolerations: запуск на выделенных нодах с taint
  tolerations:
  - key: "dedicated"
    operator: "Equal"
    value: "payment"
    effect: "NoSchedule"
```

## Debugging и Troubleshooting

Полезные команды для диагностики:

```bash
# Состояние Pod-а
kubectl describe pod payment-service-abc123 -n production

# Логи (с предыдущего запуска при краше)
kubectl logs payment-service-abc123 -n production --previous
kubectl logs -l app=payment -n production --tail=100 -f

# Exec в контейнер
kubectl exec -it payment-service-abc123 -n production -- /bin/sh

# Port-forward для локального тестирования
kubectl port-forward service/payment-service 8080:80 -n production

# Получить события (часто здесь видны проблемы)
kubectl get events -n production --sort-by='.lastTimestamp' | tail -20

# Проверить resource usage
kubectl top pods -n production --sort-by=memory
kubectl top nodes

# Dry-run для проверки манифестов
kubectl apply -f deployment.yaml --dry-run=server

# Diff: что изменится
kubectl diff -f deployment.yaml
```

### Типичные проблемы

**CrashLoopBackOff**: контейнер падает сразу после старта.
```bash
kubectl logs pod-name --previous  # Логи предыдущего запуска
kubectl describe pod pod-name     # Events с причиной краша
```

**ImagePullBackOff**: не может скачать образ.
```bash
kubectl describe pod pod-name  # Смотрим Events — обычно неправильный тег или нет прав к registry
```

**Pending**: Pod не может быть заскеджулен.
```bash
kubectl describe pod pod-name  # Events: Insufficient cpu/memory, или нет нод с нужными lables
kubectl get events -n namespace
```

**OOMKilled**: контейнер убит из-за превышения memory limit.
```bash
kubectl describe pod pod-name  # Reason: OOMKilled
# Решение: увеличить limits или найти утечку памяти
```

## Kubernetes в облаке vs self-hosted

| Аспект | Managed (EKS/GKE/AKS) | Self-hosted (kubeadm) |
|--------|----------------------|----------------------|
| Control Plane | Управляется облаком | Ваша ответственность |
| Upgrades | Частично автоматически | Ручные |
| Стоимость | $150+/месяц за кластер | Только серверы |
| Интеграция с облаком | Нативная | Требует настройки |
| Рекомендуется | Большинство случаев | Жёсткие требования к данным |

Для большинства компаний managed Kubernetes — правильный выбор: меньше операционных забот.

## Безопасность контейнеров

```yaml
# Security Context: ограничения на уровне Pod и Container
spec:
  securityContext:
    runAsNonRoot: true   # Запрещаем root
    runAsUser: 1000
    fsGroup: 2000
    seccompProfile:
      type: RuntimeDefault
  
  containers:
  - name: payment
    securityContext:
      allowPrivilegeEscalation: false  # Запрещаем sudo
      readOnlyRootFilesystem: true     # Иммутабельная FS
      capabilities:
        drop: ["ALL"]                  # Дропаем все capabilities
        add: ["NET_BIND_SERVICE"]      # Добавляем только нужные
```

Дополнительные инструменты безопасности:
- **Falco**: runtime threat detection на основе eBPF
- **Trivy/Snyk**: сканирование образов на уязвимости
- **OPA Gatekeeper**: policy-as-code для admission control
- **Pod Security Admission**: встроенный механизм политик (restricted/baseline/privileged)

## Литература

1. Burns B. et al. **Kubernetes: Up and Running**, 3rd Edition. O'Reilly Media, 2022. — Классическое введение от создателей Kubernetes.

2. Luksa M. **Kubernetes in Action**, 2nd Edition. Manning Publications, 2021. — Самое детальное практическое руководство.

3. **Kubernetes Documentation**. — https://kubernetes.io/docs/

4. Rice L. **Container Security**. O'Reilly Media, 2020. — Глубокое погружение в Linux namespaces, cgroups и безопасность контейнеров.

5. **Docker Documentation: Best practices for writing Dockerfiles**. — https://docs.docker.com/develop/develop-images/dockerfile_best-practices/

6. Hightower K., Burns B., Beda J. **Kubernetes: Up and Running**. O'Reilly Media, 2017. — Оригинальное издание от основателей проекта.

7. **The Twelve-Factor App**. Heroku. — https://12factor.net/ — Принципы, на которых базируется контейнеризация.

8. **CNCF Landscape**. — https://landscape.cncf.io/ — Полный ландшафт cloud-native инструментов вокруг Kubernetes.

9. Huss R. **Helm: The Kubernetes Package Manager**. — https://helm.sh/docs/

10. Brendan Burns et al. **Borg, Omega, and Kubernetes** // ACM Queue, Vol. 14, 2016. — https://queue.acm.org/detail.cfm?id=2898444
