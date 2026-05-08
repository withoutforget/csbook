# Принцип наименьших привилегий и defence in depth

## Введение

Два фундаментальных принципа безопасности — **Principle of Least Privilege (PoLP)** и **Defence in Depth** — определяют архитектуру надёжных систем. Первый говорит: дай компоненту только то, что ему нужно для работы, не больше. Второй: не полагайся на один защитный рубеж — используй несколько слоёв защиты.

Эти принципы применяются на всех уровнях: от Linux-процессов и Docker-контейнеров до разрешений в базах данных и IAM политик в облаке. Разработчик, понимающий эти принципы, строит системы, в которых взлом одного компонента не приводит к полной компрометации.

---

## 1. Принцип наименьших привилегий (PoLP)

### Определение и мотивация

**PoLP** (Principle of Least Privilege, RFC 3552): каждый субъект (пользователь, процесс, программа) должен иметь только минимально необходимые права для выполнения своей функции.

**Мотивация:**
- Уменьшение **attack surface** (поверхности атаки)
- Ограничение последствий компрометации (blast radius)
- Снижение риска случайных ошибок
- Соответствие принципу «fail-safe defaults»

### Применение в Linux

```bash
# Плохо: запуск веб-сервера от root
# Хорошо: выделенный пользователь с минимальными правами

# Создание системного пользователя для сервиса
useradd --system --no-create-home --shell /usr/sbin/nologin nginx_user
id nginx_user  # uid=999, gid=999, groups=999

# Установка прав на файлы
chown nginx_user:nginx_user /var/www/html
chmod 750 /var/www/html

# sudo конфигурация с минимальными правами
# /etc/sudoers.d/deploy_user:
# deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx
# (только этот конкретный сервис, не полный root!)
```

### Linux Capabilities

Традиционная модель Unix: root (UID=0) может всё, остальные ограничены. Это бинарно. Linux **capabilities** разбивают root-права на ~40 отдельных привилегий:

```bash
# Список capabilities
man capabilities  # или capabilities(7)

# Ключевые capabilities:
# CAP_NET_BIND_SERVICE: привязка к портам < 1024 (вместо sudo)
# CAP_CHOWN: изменение владельца файла
# CAP_DAC_OVERRIDE: обход проверки прав доступа
# CAP_SYS_ADMIN: опасный! почти как root
# CAP_NET_ADMIN: сетевые настройки
# CAP_SETUID: изменение UID процесса
# CAP_SYS_PTRACE: трассировка других процессов

# Дать процессу только необходимые capabilities
setcap 'cap_net_bind_service=+ep' /usr/bin/my_webserver
# Теперь сервер может слушать порт 80/443 без root!

# Проверить capabilities исполняемого файла
getcap /usr/bin/ping   # cap_net_raw=ep
getcap /bin/su         # cap_setuid+ep

# Capabilities процесса
cat /proc/$(pidof nginx)/status | grep -E "Cap[A-Za-z]+"
```

```python
import subprocess

def drop_capabilities_example():
    """
    Концептуальный пример: запуск с ограниченными capabilities
    через Python (требует ctypes / prctl)
    """
    import ctypes
    import ctypes.util
    
    PR_CAP_AMBIENT = 47
    PR_CAP_AMBIENT_LOWER = 1
    
    # Для полной реализации нужна библиотека python-prctl
    # pip install python-prctl
    try:
        import prctl
        # Дропаем все capabilities кроме нужных
        prctl.cap_effective.net_bind_service = True
        prctl.cap_permitted.net_bind_service = True
        # Дропаем всё остальное
        for cap in prctl.ALL_CAPS:
            if cap != prctl.CAP_NET_BIND_SERVICE:
                try:
                    setattr(prctl.cap_effective, cap.name.lower(), False)
                    setattr(prctl.cap_permitted, cap.name.lower(), False)
                except:
                    pass
        print("Capabilities ограничены!")
    except ImportError:
        print("prctl не установлен: pip install python-prctl")
```

### seccomp-bpf — ограничение системных вызовов

seccomp (secure computing mode) позволяет ограничить набор разрешённых системных вызовов для процесса:

```python
import ctypes
import struct

# Пример через syscall напрямую
# На практике используйте: pip install seccomp

try:
    import seccomp
    
    # Создаём фильтр: запрещаем всё по умолчанию
    filt = seccomp.SyscallFilter(defaction=seccomp.KILL_PROCESS)
    
    # Разрешаем только необходимые syscalls
    filt.add_rule(seccomp.ALLOW, "read")
    filt.add_rule(seccomp.ALLOW, "write")
    filt.add_rule(seccomp.ALLOW, "open")
    filt.add_rule(seccomp.ALLOW, "close")
    filt.add_rule(seccomp.ALLOW, "exit")
    filt.add_rule(seccomp.ALLOW, "exit_group")
    filt.add_rule(seccomp.ALLOW, "mmap")
    filt.add_rule(seccomp.ALLOW, "brk")
    # ... только необходимые
    
    filt.load()  # Применяем фильтр
    print("seccomp фильтр применён!")
    
except ImportError:
    print("libseccomp не установлен")

# Docker применяет seccomp по умолчанию (блокирует опасные syscalls):
# --security-opt seccomp=default.json
```

### chroot — ограничение файловой системы

```bash
# Создание chroot окружения для nginx
mkdir -p /var/chroot/nginx/{etc,lib,lib64,usr,var,tmp,dev}

# Копируем только нужные файлы
cp /usr/sbin/nginx /var/chroot/nginx/usr/sbin/
# Копируем зависимые библиотеки (ldd)
ldd /usr/sbin/nginx | awk '/\/lib/{print $3}' | xargs -I{} cp {} /var/chroot/nginx/lib/

# Запуск в chroot
chroot /var/chroot/nginx /usr/sbin/nginx

# Более современный вариант: namespaces (контейнеры)
```

---

## 2. Defence in Depth — многоуровневая защита

### Концепция

**Defence in Depth** (глубокая оборона) — принцип из военной стратегии, применённый к информационной безопасности: несколько слоёв защиты, каждый из которых независим от других.

```
Слой 1: Периметр сети (firewall, WAF)
  ↓
Слой 2: Аутентификация (MFA, SSO)
  ↓
Слой 3: Авторизация (RBAC/ABAC)
  ↓
Слой 4: Сетевая сегментация (VLAN, network policies)
  ↓
Слой 5: OS hardening (SELinux, AppArmor, seccomp)
  ↓
Слой 6: Шифрование данных (at-rest, in-transit)
  ↓
Слой 7: Аудит и мониторинг (SIEM, logging)
```

### Attack Surface Reduction

```python
# Принципы уменьшения attack surface:

# 1. Отключите то, что не используется
# Лишние сервисы = лишняя поверхность атаки
def minimal_flask_app():
    from flask import Flask
    app = Flask(__name__)
    
    # Отключить в production:
    # app.run(debug=False)        # debug=True даёт RCE в production!
    # app.config['TESTING'] = False
    # Не включайте неиспользуемые Flask extensions
    
    return app

# 2. Fail-safe defaults
def create_user(data: dict) -> dict:
    """Безопасные дефолты: минимальные права по умолчанию"""
    return {
        "role": data.get("role", "viewer"),  # viewer — минимальные права
        "is_active": True,
        "can_admin": False,  # Явное отключение, не зависит от запроса
        "api_access": False  # По умолчанию нет
    }

# 3. Input validation — не доверяй внешним данным
from pydantic import BaseModel, validator

class TransferRequest(BaseModel):
    to_account: str
    amount: float
    
    @validator('amount')
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        if v > 100000:
            raise ValueError("Amount exceeds maximum")
        return v
    
    @validator('to_account')
    def account_must_be_valid(cls, v):
        import re
        if not re.match(r'^\d{10,20}$', v):
            raise ValueError("Invalid account number")
        return v
```

---

## 3. Zero Trust Network Architecture

```python
class ZeroTrustPolicy:
    """
    Каждый запрос верифицируется независимо от источника
    """
    
    def authorize(self, context: dict) -> bool:
        # 1. Идентификация пользователя верифицирована?
        if not self._verify_identity(context['user_token']):
            return False
        
        # 2. Устройство зарегистрировано и compliant?
        if not self._verify_device(context['device_id']):
            return False
        
        # 3. Сетевой контекст приемлем?
        if not self._verify_network_context(context['ip_address']):
            return False
        
        # 4. Принцип наименьших привилегий для конкретного действия
        if not self._verify_minimal_access(
            context['user_id'],
            context['resource'],
            context['action']
        ):
            return False
        
        # 5. Поведенческий анализ (не аномалия?)
        if not self._verify_behavior(context):
            return False
        
        return True
    
    def _verify_network_context(self, ip: str) -> bool:
        """Нет доверенных сетей — даже офисная сеть проверяется"""
        # Анализ IP репутации, геолокация, VPN обнаружение
        return True  # Упрощение
```

---

## 4. Принцип в Kubernetes

```yaml
# Pod Security Standards — Restricted policy
apiVersion: v1
kind: Pod
metadata:
  name: secure-app
spec:
  securityContext:
    runAsNonRoot: true        # Не root
    runAsUser: 1000           # Конкретный UID
    seccompProfile:
      type: RuntimeDefault    # seccomp профиль
  
  containers:
  - name: app
    image: myapp:latest
    
    securityContext:
      allowPrivilegeEscalation: false  # Нет эскалации привилегий
      readOnlyRootFilesystem: true     # Filesystem только для чтения
      capabilities:
        drop: ["ALL"]          # Дропаем все capabilities
        add: []                # Не добавляем ничего лишнего
    
    resources:
      limits:
        cpu: "200m"            # Ограничение CPU
        memory: "256Mi"        # Ограничение памяти
      requests:
        cpu: "100m"
        memory: "128Mi"
    
    env:
    # Секреты — не в env vars! Используйте Kubernetes Secrets
    # или Vault через CSI driver
    - name: DB_HOST
      valueFrom:
        secretKeyRef:
          name: db-credentials
          key: host
```

---

## 5. Принцип в IAM (AWS)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::my-specific-bucket/*",
      "Condition": {
        "StringEquals": {
          "s3:prefix": ["uploads/", "data/"]
        },
        "Bool": {
          "aws:SecureTransport": "true"
        }
      }
    }
  ]
}
```

Плохая практика: `"Action": ["s3:*"]` или `"Resource": "*"` — это нарушение PoLP.

---

## 6. Разделение обязанностей (Separation of Duties)

```python
class DeploymentSystem:
    """
    Разделение обязанностей: один человек не может
    как писать код, так и деплоить в production
    """
    
    def deploy(self, code_sha: str, environment: str, approver_id: str) -> None:
        # Проверка: кто создал PR не может его же апрувнуть
        pr_author = self._get_pr_author(code_sha)
        if pr_author == approver_id:
            raise PermissionError("PR author cannot approve own deployment")
        
        # Критические действия требуют нескольких апрувалов
        approvals = self._get_approvals(code_sha)
        if environment == "production" and len(approvals) < 2:
            raise PermissionError("Production deploy requires 2 approvals")
        
        # Чувствительные операции требуют 4-eyes principle
        self._execute_deployment(code_sha, environment)
```

---

## 7. Fail-safe Defaults

```python
class ResourceAccessControl:
    """Fail-safe defaults: отказывай по умолчанию"""
    
    def __init__(self):
        self.explicit_grants = set()  # Явные разрешения
    
    def grant(self, user_id: str, resource: str, action: str):
        self.explicit_grants.add((user_id, resource, action))
    
    def check(self, user_id: str, resource: str, action: str) -> bool:
        # DENY BY DEFAULT — нет явного разрешения → отказ
        return (user_id, resource, action) in self.explicit_grants
        # Никакого "разрешить если не запрещено явно"!

# Пример: NGINX конфигурация с deny by default
nginx_config = """
server {
    listen 80;
    
    # Сначала запрещаем всё
    location / {
        deny all;
    }
    
    # Явно разрешаем только нужное
    location /api/ {
        allow all;
        proxy_pass http://backend:8080;
    }
    
    location /static/ {
        allow all;
        root /var/www;
    }
}
"""
```

---

## Заключение

Принципы PoLP и Defence in Depth — не просто теоретические концепции, а практические инструменты снижения риска.

**Ключевые выводы:**
1. **Минимальные привилегии везде:** пользователи, процессы, сервисы, сервисные аккаунты
2. **Capabilities вместо root:** на Linux используйте capabilities для сервисов, требующих ограниченных root-прав
3. **seccomp-bpf:** ограничивает системные вызовы для критических сервисов
4. **Несколько слоёв защиты:** каждый слой независим
5. **Deny by default:** явное разрешение, а не явный запрет
6. **Zero Trust:** не доверять ни внутренним, ни внешним запросам без верификации
7. **В Kubernetes:** используйте Pod Security Standards (restricted policy) для всех рабочих нагрузок

---

## Литература и источники

1. Saltzer, J.H., Schroeder, M.D. (1975). *The Protection of Information in Computer Systems*. https://web.mit.edu/Saltzer/www/publications/protection/
2. NIST SP 800-27. *Engineering Principles for Information Technology Security*. https://csrc.nist.gov/publications/detail/sp/800-27/rev-a/final
3. Linux man page: capabilities(7). https://man7.org/linux/man-pages/man7/capabilities.7.html
4. Linux man page: seccomp(2). https://man7.org/linux/man-pages/man2/seccomp.2.html
5. Kubernetes. *Pod Security Standards*. https://kubernetes.io/docs/concepts/security/pod-security-standards/
6. AWS IAM. *Best practices for AWS Identity and Access Management*. https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
7. NIST SP 800-207. (2020). *Zero Trust Architecture*. https://csrc.nist.gov/publications/detail/sp/800-207/final
8. OWASP. *Access Control Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html
9. Wikipedia: Principle of least privilege. https://en.wikipedia.org/wiki/Principle_of_least_privilege
10. Wikipedia: Defense in depth (computing). https://en.wikipedia.org/wiki/Defense_in_depth_(computing)
