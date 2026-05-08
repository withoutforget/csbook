# CI/CD, IaC — автоматизация сборки, тестов и инфраструктуры

Два десятилетия назад деплой новой версии приложения был событием: длинные чек-листы, ночные окна обслуживания, несколько инженеров на связи. Сегодня Netflix делает сотни деплоев в день, Amazon — тысячи. Это стало возможным благодаря CI/CD и Infrastructure as Code — двум практикам, которые превратили деплой из рискованного события в рутинную операцию.

## Continuous Integration: частые merge, автоматические тесты

**Continuous Integration (CI)** — практика разработки, при которой все разработчики часто интегрируют свой код в общую ветку (минимум раз в день), а каждая интеграция автоматически проверяется сборкой и тестами.

**Проблема без CI:**
```
Разработчик A работает 2 недели в своей ветке
Разработчик B работает 2 недели в своей ветке

Merge day: "Integration hell"
- Конфликты в сотнях файлов
- Тесты падают, причину понять сложно
- Дни или недели на исправление
```

**С CI:**
```
Разработчик A merge в main каждый день → маленький merge, маленькие конфликты
Разработчик B merge в main каждый день → то же самое

Конфликты находятся сразу, пока контекст свеж
```

## Continuous Delivery vs Continuous Deployment

```
CI → CD (Delivery) → CD (Deployment)

Continuous Integration:
  Каждый push → автоматическая сборка и тесты
  Результат: "Это приложение можно собрать и оно проходит тесты"

Continuous Delivery:
  + Каждое изменение автоматически готово к деплою в production
  Но: ручное нажатие кнопки для actual деплоя
  Результат: "Деплой — простая, безопасная операция"

Continuous Deployment:
  + Каждое изменение, прошедшее тесты, автоматически деплоится
  Результат: "От commit до production — минуты, без участия человека"
```

## Feature Flags: CI с незавершёнными фичами

Как делать CI, если фича требует недели разработки?

```python
# Feature flags: код в main, но фича выключена по умолчанию
from feature_flags import flag

class CheckoutService:
    def process_checkout(self, cart, user):
        # Старый checkout flow
        if flag.is_enabled('new_checkout_flow', user.id):
            # Новый checkout (ещё в разработке, включён только для команды)
            return self._new_checkout_flow(cart, user)
        
        return self._old_checkout_flow(cart, user)

# Конфигурация флагов (например, в LaunchDarkly или Unleash)
# new_checkout_flow:
#   enabled: false  (default)
#   overrides:
#     - user_id: "dev_team"
#       enabled: true
#     - percentage: 5  (5% пользователей для canary)
#       enabled: true
```

**Преимущества feature flags:**
- Незавершённый код в main без риска для пользователей
- Постепенный rollout (1% → 10% → 100%)
- Мгновенный rollback без деплоя (просто выключить флаг)
- A/B тестирование

## Trunk-Based Development

**Trunk-Based Development (TBD)** — практика, при которой все разработчики работают напрямую в main (trunk) или в очень короткоживущих feature branches (< 2 дней).

```
Long-Lived Feature Branches (анти-паттерн):
  main: ─────────────────────────────────────►
                   feature-auth: ─────────────────────────────►
                   (2 недели работы)               ↑
                                              merge war!

Trunk-Based Development:
  main: ──●──────●──────●──────●──────►
            ↑           ↑
          commit1     commit2 (сегодня)
  
  Или короткие ветки (< 2 дней):
  main: ──●──────────────────●──►
              feature: ──●──┘
              (1-2 дня)
```

## CI Pipeline: build → test → lint → security → deploy

```yaml
# GitHub Actions: полный CI/CD pipeline
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # === СТАДИЯ 1: Сборка ===
  build:
    runs-on: ubuntu-latest
    outputs:
      image-tag: ${{ steps.meta.outputs.tags }}
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    
    - name: Login to registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    
    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        tags: |
          type=sha,prefix={{branch}}-
    
    - name: Build and push
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        cache-from: type=gha    # GitHub Actions cache
        cache-to: type=gha,mode=max
  
  # === СТАДИЯ 2: Линтинг ===
  lint:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
        cache: 'pip'
    
    - run: pip install ruff mypy
    
    - name: Ruff (linting + formatting)
      run: ruff check . && ruff format --check .
    
    - name: Mypy (type checking)
      run: mypy src/
  
  # === СТАДИЯ 3: Тесты ===
  test:
    runs-on: ubuntu-latest
    needs: [build]
    
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        options: --health-cmd "redis-cli ping"
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Run unit tests
      run: |
        pip install -r requirements-dev.txt
        pytest tests/unit/ -v --cov=src --cov-report=xml
    
    - name: Run integration tests
      env:
        DATABASE_URL: postgresql://test:test@localhost/test_db
        REDIS_URL: redis://localhost:6379
      run: pytest tests/integration/ -v
    
    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
        minimum_coverage: 80
  
  # === СТАДИЯ 4: Security Scan ===
  security:
    runs-on: ubuntu-latest
    needs: [build]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Trivy vulnerability scan (Docker image)
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: ${{ needs.build.outputs.image-tag }}
        format: 'sarif'
        exit-code: '1'           # Провалить CI при HIGH/CRITICAL уязвимостях
        severity: 'HIGH,CRITICAL'
    
    - name: Dependency audit (Python)
      run: pip-audit -r requirements.txt
    
    - name: SAST (Static Analysis)
      uses: github/codeql-action/analyze@v3
      with:
        languages: python
  
  # === СТАДИЯ 5: Деплой (Staging) ===
  deploy-staging:
    runs-on: ubuntu-latest
    needs: [lint, test, security]
    if: github.ref == 'refs/heads/main'
    environment: staging
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Deploy to Staging
      run: |
        # Обновляем deployment в Kubernetes
        kubectl set image deployment/app \
          app=${{ needs.build.outputs.image-tag }} \
          --namespace=staging
        
        kubectl rollout status deployment/app --namespace=staging --timeout=5m
    
    - name: Run smoke tests
      run: |
        sleep 10  # Ждём готовности
        curl -f https://staging.example.com/health || exit 1
  
  # === СТАДИЯ 6: Деплой (Production) - ручное подтверждение ===
  deploy-production:
    runs-on: ubuntu-latest
    needs: [deploy-staging]
    environment: 
      name: production
      url: https://example.com
    # environment: production требует manual approval в GitHub UI
    
    steps:
    - name: Deploy to Production
      run: |
        kubectl set image deployment/app \
          app=${{ needs.build.outputs.image-tag }} \
          --namespace=production
        
        kubectl rollout status deployment/app --namespace=production --timeout=10m
```

## GitLab CI: альтернативный синтаксис

```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - security
  - deploy

variables:
  DOCKER_IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

build:
  stage: build
  script:
    - docker build -t $DOCKER_IMAGE .
    - docker push $DOCKER_IMAGE
  only:
    - main
    - merge_requests

test:unit:
  stage: test
  services:
    - postgres:16
  variables:
    POSTGRES_DB: test
    POSTGRES_USER: test
    POSTGRES_PASSWORD: test
    DATABASE_URL: "postgresql://test:test@postgres/test"
  script:
    - pip install -r requirements-dev.txt
    - pytest tests/unit/ --junitxml=report.xml
  artifacts:
    reports:
      junit: report.xml

deploy:production:
  stage: deploy
  when: manual     # Ручное подтверждение
  only:
    - main
  script:
    - kubectl set image deployment/app app=$DOCKER_IMAGE
```

## Infrastructure as Code (IaC)

**Infrastructure as Code** — управление инфраструктурой (серверы, сети, базы данных) через код, хранящийся в git. Инфраструктура описывается декларативно или императивно.

### Terraform: декларативный IaC

```hcl
# main.tf — описываем желаемое состояние инфраструктуры

terraform {
  required_version = ">= 1.6"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Backend: храним state в S3 (не в локальном файле!)
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"  # Для distributed locking
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

# VPC и сеть
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {
    Name        = "${var.project}-vpc"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_subnet" "private" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone = var.availability_zones[count.index]
  
  tags = {
    Name = "${var.project}-private-${count.index + 1}"
  }
}

# RDS (Managed PostgreSQL)
resource "aws_db_instance" "main" {
  identifier = "${var.project}-${var.environment}"
  
  engine         = "postgres"
  engine_version = "16.1"
  instance_class = var.db_instance_class
  
  allocated_storage     = 20
  max_allocated_storage = 100  # Auto-scaling storage
  storage_type          = "gp3"
  storage_encrypted     = true
  
  db_name  = var.db_name
  username = var.db_username
  password = var.db_password  # В production: из secrets manager
  
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name
  
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "Mon:04:00-Mon:05:00"
  
  skip_final_snapshot = false
  final_snapshot_identifier = "${var.project}-${var.environment}-final"
  
  deletion_protection = var.environment == "production"
  
  tags = merge(local.common_tags, {Name = "${var.project}-db"})
}

# EKS (Managed Kubernetes)
resource "aws_eks_cluster" "main" {
  name     = "${var.project}-${var.environment}"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "1.29"
  
  vpc_config {
    subnet_ids              = aws_subnet.private[*].id
    endpoint_private_access = true
    endpoint_public_access  = false  # Только через VPN
  }
  
  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

# Output: что нужно другим модулям/пользователям
output "cluster_endpoint" {
  value     = aws_eks_cluster.main.endpoint
  sensitive = false
}

output "db_endpoint" {
  value     = aws_db_instance.main.endpoint
  sensitive = true
}
```

```bash
# Terraform workflow
terraform init     # Инициализация, загрузка провайдеров

terraform plan     # Просмотр изменений (diff!)
# + создать: aws_vpc.main
# ~ изменить: aws_db_instance.main (instance_class: db.t3.micro -> db.t3.small)
# - удалить: aws_security_group.old

terraform apply    # Применить изменения (с подтверждением)

terraform destroy  # Уничтожить всю инфраструктуру (осторожно!)
```

### Идемпотентность IaC

Ключевое свойство Terraform: **идемпотентность**. Повторное применение одного и того же конфига не создаёт дубликатов.

```bash
# Первый apply: создаёт VPC
terraform apply
# + aws_vpc.main created

# Второй apply (без изменений): ничего не делает
terraform apply
# No changes. Your infrastructure matches the configuration.

# Это принципиально отличается от скриптов:
# aws ec2 create-vpc --cidr 10.0.0.0/16
# Повторный вызов создаст ещё один VPC!
```

### State Management в Terraform

```hcl
# Terraform state — JSON файл с текущим состоянием инфраструктуры
# НИКОГДА не редактировать вручную!

# Просмотр state
terraform state list
# aws_vpc.main
# aws_subnet.private[0]
# aws_subnet.private[1]
# aws_db_instance.main

# Просмотр конкретного ресурса
terraform state show aws_db_instance.main

# Проблема: если ресурс создан вне Terraform?
# Решение: import
terraform import aws_vpc.existing vpc-12345678
```

## Pulumi: императивный IaC

```python
# Pulumi: инфраструктура как настоящий код (Python, TypeScript, Go)
import pulumi
import pulumi_aws as aws

# Создаём VPC
vpc = aws.ec2.Vpc(
    "main-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    tags={"Name": "main-vpc", "ManagedBy": "pulumi"}
)

# Суперности Pulumi над Terraform: можно использовать реальный код!
# Создаём 3 подсети в трёх AZ с помощью Python цикла
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]
subnets = [
    aws.ec2.Subnet(
        f"private-subnet-{i}",
        vpc_id=vpc.id,
        cidr_block=f"10.0.{i}.0/24",
        availability_zone=az,
    )
    for i, az in enumerate(availability_zones)
]

# Export: выводим важные значения
pulumi.export("vpc_id", vpc.id)
pulumi.export("subnet_ids", [s.id for s in subnets])
```

## Ansible: конфигурация серверов

```yaml
# playbook.yml — конфигурация серверов
---
- name: Configure application servers
  hosts: app_servers
  become: yes
  
  vars:
    app_user: appuser
    app_dir: /opt/myapp
    node_version: "20.x"
  
  tasks:
    - name: Ensure app user exists
      user:
        name: "{{ app_user }}"
        system: yes
        create_home: yes
        home: "{{ app_dir }}"
    
    - name: Install Node.js repository
      shell: |
        curl -fsSL https://deb.nodesource.com/setup_{{ node_version }} | bash -
      args:
        creates: /etc/apt/sources.list.d/nodesource.list
    
    - name: Install Node.js and dependencies
      apt:
        name:
          - nodejs
          - nginx
          - certbot
        state: present
        update_cache: yes
    
    - name: Configure Nginx
      template:
        src: templates/nginx.conf.j2
        dest: /etc/nginx/sites-available/myapp
        owner: root
        group: root
        mode: '0644'
      notify: restart nginx
    
    - name: Deploy application
      git:
        repo: https://github.com/myorg/myapp.git
        dest: "{{ app_dir }}"
        version: "{{ app_version }}"
        force: yes
      become_user: "{{ app_user }}"
      notify: restart app
  
  handlers:
    - name: restart nginx
      service:
        name: nginx
        state: restarted
    
    - name: restart app
      systemd:
        name: myapp
        state: restarted
        daemon_reload: yes
```

## Тестирование инфраструктуры

### Terratest (Golang)

```go
// terratest/vpc_test.go — тестируем Terraform модуль
package test

import (
    "testing"
    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/gruntwork-io/terratest/modules/aws"
    "github.com/stretchr/testify/assert"
)

func TestVPCModule(t *testing.T) {
    t.Parallel()
    
    awsRegion := "us-east-1"
    
    terraformOptions := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
        TerraformDir: "../modules/vpc",
        Vars: map[string]interface{}{
            "project":     "test",
            "environment": "test",
            "cidr_block":  "10.0.0.0/16",
        },
    })
    
    // Уничтожаем инфраструктуру после теста
    defer terraform.Destroy(t, terraformOptions)
    
    // Создаём инфраструктуру
    terraform.InitAndApply(t, terraformOptions)
    
    // Проверяем результаты
    vpcID := terraform.Output(t, terraformOptions, "vpc_id")
    assert.NotEmpty(t, vpcID)
    
    // Проверяем что VPC действительно создан в AWS
    vpc := aws.GetVpcById(t, vpcID, awsRegion)
    assert.Equal(t, "10.0.0.0/16", aws.GetTagValue(vpc.Tags, "CIDR"))
}
```

### Checkov: статический анализ безопасности IaC

```bash
# Checkov: проверяет Terraform/CloudFormation на уязвимости безопасности
pip install checkov

checkov -d .  # Проверить все Terraform файлы

# Вывод:
# Check: CKV_AWS_2: "Ensure ALB protocol is HTTPS"
# PASSED for resource: aws_lb_listener.https
#
# Check: CKV_AWS_18: "Ensure S3 bucket versioning is enabled"
# FAILED for resource: aws_s3_bucket.data
# Line: 42
```

## GitOps: ArgoCD и Flux

**GitOps** — практика, при которой Git является единственным источником истины для конфигурации и состояния системы.

```yaml
# ArgoCD Application: синхронизируем Kubernetes с Git
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: order-service
  namespace: argocd
spec:
  project: production
  
  source:
    repoURL: https://github.com/myorg/k8s-configs.git
    targetRevision: main
    path: apps/order-service/production
  
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  
  syncPolicy:
    automated:
      prune: true      # Удалять ресурсы, которых нет в Git
      selfHeal: true   # Автоматически восстанавливать изменённые ресурсы
    syncOptions:
    - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        maxDuration: 3m
        factor: 2
```

```
GitOps Flow:

Разработчик push в Git → ArgoCD замечает изменение →
ArgoCD сравнивает Git с кластером → Если diff → Деплоит изменения

Гарантии:
1. Всё что в кластере — есть в Git (полная аудируемость)
2. Никто не может тихо изменить production (всё через PR)
3. Rollback = revert в Git
4. Disaster recovery = пересоздать кластер из Git
```

## Packer: создание образов ВМ

```hcl
# packer.pkr.hcl — создаём AMI с предустановленным ПО
packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "~> 1"
    }
  }
}

source "amazon-ebs" "ubuntu" {
  region        = "us-east-1"
  source_ami_filter {
    filters = {
      name                = "ubuntu/images/*ubuntu-jammy-22.04-amd64-server-*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    owners      = ["099720109477"]  # Canonical
    most_recent = true
  }
  instance_type = "t3.micro"
  ssh_username  = "ubuntu"
  ami_name      = "myapp-{{timestamp}}"
}

build {
  sources = ["source.amazon-ebs.ubuntu"]
  
  provisioner "shell" {
    inline = [
      "sudo apt-get update -y",
      "sudo apt-get install -y docker.io",
      "sudo systemctl enable docker",
    ]
  }
  
  provisioner "ansible" {
    playbook_file = "playbook.yml"
  }
}
```

## Заключение

CI/CD и IaC — это не инструменты, это культура и дисциплина. Ключевые принципы:

**CI/CD:**
- Интегрируй часто, тестируй автоматически
- Каждый коммит должен быть deployable
- Feature flags для незавершённого кода
- Быстрая обратная связь (pipeline < 10 минут — цель)

**IaC:**
- Вся инфраструктура в git — audit trail, reproducibility
- Идемпотентность — повторное применение безопасно
- Разделяй конфигурацию от кода (переменные, secrets)
- Тестируй инфраструктуру (Terratest, Checkov)

Когда CI/CD и IaC работают вместе через GitOps — каждое изменение (кода или инфраструктуры) проходит через git, тестируется автоматически, и деплоится предсказуемо. Это основа modern engineering.

## Литература

1. **Humble, Jez; Farley, David** — «Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation». Addison-Wesley, 2010. ISBN: 978-0321601919
2. **Forsgren, Nicole; Humble, Jez; Kim, Gene** — «Accelerate: The Science of Lean Software and DevOps». IT Revolution Press, 2018. ISBN: 978-1942788331
3. **Kim, Gene et al.** — «The DevOps Handbook». IT Revolution Press, 2016. ISBN: 978-1942788003
4. **HashiCorp** — «Terraform Documentation»: https://developer.hashicorp.com/terraform/docs
5. **GitHub Actions Documentation** — https://docs.github.com/en/actions
6. **Weaveworks** — «GitOps Principles»: https://www.gitops.tech/
7. **ArgoCD Documentation** — https://argo-cd.readthedocs.io/
8. **Ansible Documentation** — https://docs.ansible.com/
9. **Gruntwork** — «Terratest Documentation»: https://terratest.gruntwork.io/docs/
10. **Trunk Based Development** — «Why and How»: https://trunkbaseddevelopment.com/
