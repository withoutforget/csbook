# Sandboxing, контейнеры и изоляция

## Введение

Песочница (sandbox) — механизм изоляции, ограничивающий действия кода: его доступ к файловой системе, сети, системным вызовам, другим процессам. Sandboxing применяется везде: в браузерах (каждая вкладка в отдельном процессе с ограниченными правами), в облачных функциях (AWS Lambda, Firecracker), в контейнерах Docker.

Строгость изоляции варьируется от лёгкой (seccomp-bpf) до полной (виртуальная машина). В этой статье рассмотрим технологии sandboxing: от браузерных sandbox до gVisor и Firecracker — и поймём, какой уровень изоляции обеспечивает каждый из них.

---

## 1. Браузерный Sandbox

### Chrome Site Isolation

Chrome использует многопроцессную архитектуру с изоляцией по сайтам (Site Isolation):

```
Browser Process (privileged):
  - UI, сеть, файловая система
  - Управляет всеми renderer processes

Renderer Process per-origin (heavily sandboxed):
  - Выполняет JavaScript, HTML, CSS
  - NO file system access (кроме через Browser Process)
  - NO network access directly
  - NO OS calls напрямую

GPU Process:
  - Только GPU операции
  
Network Process:
  - Только сетевые запросы
```

Взаимодействие через **Mojo IPC** (Inter-Process Communication):
- Renderer не может напрямую вызвать OS API
- Всё через сообщения к Browser Process
- Browser Process проверяет разрешения и выполняет действие

```
Renderer → Mojo IPC → Browser Process → OS API

Атака: Exploiting renderer (RCE в V8 JavaScript engine)
→ Злоумышленник получает код в renderer process
→ Но renderer sandbox не позволяет read/write файлов
→ Нужен второй exploit (sandbox escape) для выхода из sandbox
```

Это объясняет, почему Chrome уязвимости часто идут «в паре»: RCE в renderer + sandbox escape.

### Renderer Sandbox на Windows (LPAC)

На Windows Chrome использует Low Privilege App Container (LPAC) — ограниченный process token без доступа к большинству системных ресурсов.

---

## 2. OS-level Sandboxing

### seccomp-bpf

seccomp-bpf (secure computing mode с BPF фильтром) ограничивает системные вызовы для процесса. Используется Chrome, Docker, OpenSSH, systemd.

```python
# Пример применения seccomp фильтра через Python
# pip install seccomp

try:
    import seccomp
    
    # Создаём allowlist фильтр
    f = seccomp.SyscallFilter(defaction=seccomp.ERRNO(seccomp.errno.EPERM))
    
    # Разрешаем только необходимые syscalls
    allowed = [
        "read", "write", "open", "close", "fstat", "lstat",
        "mmap", "mprotect", "munmap", "brk",
        "exit", "exit_group",
        "getpid", "gettid",
        "clock_gettime", "gettimeofday",
        "futex",          # Mutex
        "rt_sigaction", "rt_sigprocmask",  # Сигналы
        "send", "recv", "connect",  # Сеть (если нужна)
    ]
    
    for syscall in allowed:
        try:
            f.add_rule(seccomp.ALLOW, syscall)
        except:
            pass  # Некоторые могут не существовать на данной платформе
    
    # Применяем фильтр (необратимо!)
    f.load()
    print("seccomp фильтр применён — только разрешённые syscalls!")
    
except ImportError:
    print("seccomp не установлен")
```

### OpenBSD pledge и unveil

OpenBSD предоставляет два уникальных примитива для sandboxing:

```c
// pledge: объявляем, какие системные ресурсы программа будет использовать
// После pledge попытка использовать другие ресурсы → SIGKILL

pledge("stdio rpath inet dns", NULL);
// stdio: базовые I/O операции
// rpath: read-only файловый доступ  
// inet: сетевые соединения
// dns: DNS резолвинг

// unveil: ограничиваем видимость файловой системы
unveil("/etc/ssl/cert.pem", "r");  // Только этот файл, только чтение
unveil("/tmp", "rwc");             // /tmp: read/write/create
unveil(NULL, NULL);                // Заблокировать дальнейшие unveil вызовы
```

Эти примитивы использует OpenSSH, dhclient и многие другие программы в OpenBSD.

---

## 3. Контейнеры Docker — Linux namespaces + cgroups

Контейнеры используют Linux-примитивы для изоляции — это не настоящие VM:

### Linux Namespaces

```
Namespace типы:
pid     - PID 1 внутри контейнера ≠ PID 1 снаружи
net     - Отдельный сетевой стек (интерфейсы, маршрутизация)
mnt     - Отдельная точка монтирования (файловая система)
uts     - Отдельный hostname
ipc     - Отдельная Inter-Process Communication
user    - Маппинг UID/GID (root внутри = не-root снаружи)
cgroup  - Отдельная иерархия cgroup
time    - Отдельные часы (Linux 5.6+)
```

```python
import subprocess
import os

def demonstrate_namespaces():
    """Демонстрация PID namespace"""
    # В контейнере:
    # ps aux → PID 1 = ваш процесс
    # Но реальный PID в host namespace другой
    
    # Показать наш PID в текущем namespace
    print(f"Наш PID (в текущем namespace): {os.getpid()}")
    
    # Показать все процессы (только видимые в нашем namespace)
    result = subprocess.run(['ps', '-ef', '--no-headers'], 
                          capture_output=True, text=True)
    process_count = len(result.stdout.strip().split('\n'))
    print(f"Видимых процессов: {process_count}")
    
    # В Docker контейнере это будет 1-5 процессов,
    # а не 200+ как на хосте

demonstrate_namespaces()
```

### cgroups — ограничение ресурсов

```bash
# cgroups v2 (modern Linux)
# Docker использует cgroups для resource limits

# Пример: ограничение памяти для контейнера
docker run --memory=256m --memory-swap=256m \
           --cpus=0.5 \
           --pids-limit=100 \
           myapp:latest

# Внутри: ядро убьёт процесс при превышении limita
# OOM Killer = Out-Of-Memory Killer

# Просмотр cgroup настроек
cat /sys/fs/cgroup/memory/docker/<id>/memory.limit_in_bytes
cat /sys/fs/cgroup/cpu/docker/<id>/cpu.cfs_quota_us
```

### Уровень изоляции контейнеров vs VM

```
Контейнер Docker:
  ✓ PID, NET, MNT, UTS, IPC namespaces
  ✓ cgroups для resource limits
  ✓ seccomp-bpf по умолчанию (блокирует ~40 опасных syscalls)
  ✓ Отдельная файловая система (overlay fs)
  
  ✗ ОДНО ЯДРО с хостом (отличие от VM!)
  ✗ Kernel vulnerabilities могут привести к container escape
  ✗ User namespace по умолчанию не включён

Примеры container escape CVEs:
  CVE-2019-5736 (runc): перезапись /proc/self/exe → RCE на хосте
  CVE-2020-15257 (Containerd): unix socket доступен → host privilege
  CVE-2022-0847 (Dirty Pipe): Linux kernel bug, пишем в read-only файлы
```

---

## 4. gVisor — пользовательское ядро

gVisor (Google, 2018) — sandbox для контейнеров, реализующий большинство Linux syscalls в **user space**:

```
Без gVisor:
  Container Process → syscall → Linux Kernel → Hardware

С gVisor:
  Container Process → syscall → gVisor Sentry (user-space kernel) 
                                → Gofer (file access) / limited real syscalls
                                → Linux Kernel (минимальный set)
```

**gVisor Sentry** — это user-space ядро на Go, которое:
- Перехватывает все syscalls контейнера через ptrace или KVM
- Обрабатывает их в user space, не пропуская в реальное ядро
- Реализует ~200+ Linux syscalls

**Преимущества gVisor:**
- Kernel vulnerabilities хоста не доступны контейнеру напрямую
- Значительно уменьшенная attack surface реального ядра

**Недостатки gVisor:**
- Overhead ~10-30% на I/O операциях
- Не все syscalls реализованы

```bash
# Установка gVisor
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list
sudo apt-get update && sudo apt-get install -y runsc

# Регистрируем как Docker runtime
# /etc/docker/daemon.json:
# {
#   "runtimes": {
#     "runsc": { "path": "/usr/local/bin/runsc" }
#   }
# }

# Запуск с gVisor
docker run --runtime=runsc myapp:latest

# Google Cloud Run использует gVisor для всех serverless функций
```

---

## 5. Kata Containers — лёгкие VM

Kata Containers запускает каждый контейнер в **отдельной облегчённой виртуальной машине**:

```
Kata Container:
  Host → QEMU/KVM microVM → Minimal Linux Kernel (kata-kernel) → Container

Изоляция: VM-уровень (несколько ядер, hardware виртуализация)
Overhead: ~100-200 мс запуск, ~100 МБ RAM на контейнер
```

Kata Containers используются в OpenStack, Kubernetes (через containerd + kata-shim).

---

## 6. Firecracker — microVM для Serverless

Firecracker разработан Amazon в 2018 году для AWS Lambda и Fargate:

```
Firecracker microVM:
  ✓ KVM-based (hardware virtualization, Intel VT-x/AMD-V)
  ✓ Minimal device model (только virtio net/block + serial port)
  ✓ Запуск за 125 мс (vs ~500 мс для QEMU)
  ✓ ~5 MB RAM overhead на microVM
  ✓ Go + Rust реализация, минимальный TCB

AWS Lambda:
  Каждая Lambda функция = отдельная Firecracker microVM
  Несколько функций могут работать на одном хосте в разных microVMs
  Строгая изоляция между клиентами
```

```python
# Пример использования Firecracker HTTP API
import requests

def create_firecracker_vm(config: dict) -> None:
    """
    Создание Firecracker microVM через Unix socket
    В реальности используется для Lambda, Fargate
    """
    socket_path = "/tmp/firecracker.socket"
    
    # В production Firecracker не использует сеть для management API —
    # только Unix domain socket для безопасности
    
    # Концептуальный пример конфигурации
    machine_config = {
        "vcpu_count": 1,
        "mem_size_mib": 128,    # 128 МБ RAM
        "ht_enabled": False
    }
    
    boot_source = {
        "kernel_image_path": "/path/to/vmlinux",
        "boot_args": "console=ttyS0 noapic reboot=k panic=1 pci=off"
    }
    
    # Монтирование rootfs
    drive = {
        "drive_id": "rootfs",
        "path_on_host": "/path/to/rootfs.ext4",
        "is_root_device": True,
        "is_read_only": False
    }
    
    print(f"Создаём microVM: {machine_config}")
    print(f"Изоляция: hardware VT-x virtualization")
```

---

## 7. Сравнение технологий изоляции

| Технология      | Изоляция           | Overhead   | Применение               |
|----------------|-------------------|------------|--------------------------|
| Docker (default)| Namespace + cgroups| ~1%        | Dev, CI/CD              |
| Docker + seccomp| + syscall filter  | ~1-2%      | Production workloads     |
| gVisor         | User-space kernel  | ~10-30% I/O| Untrusted workloads (GCR)|
| Kata Containers | VM (QEMU + KVM)  | 100-200 мс | Security-sensitive workloads|
| Firecracker    | Hardware microVM  | 125 мс / 5MB| Serverless (Lambda)     |
| VirtualBox/VMware| Full VM         | ~5-10%     | Legacy, Desktop         |

---

## 8. Практические советы

```dockerfile
# Минимальный безопасный Dockerfile
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime

# Создаём непривилегированного пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Копируем только необходимое
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/python3.12 /usr/local/bin/
COPY --chown=appuser:appuser . .

# Readonly filesystem
RUN chmod -R o-w /app

USER appuser

EXPOSE 8000

# Явное указание пользователя
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# Kubernetes SecurityContext
apiVersion: v1
kind: Pod
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault  # Применить seccomp профиль
  
  containers:
  - name: app
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true    # Readonly FS
      capabilities:
        drop:
        - ALL                          # Дропаем всё
    
    volumeMounts:
    - name: tmp
      mountPath: /tmp                  # Отдельный tmp (RW)
    - name: cache
      mountPath: /app/cache
  
  volumes:
  - name: tmp
    emptyDir: {}
  - name: cache
    emptyDir: {}
```

---

## Заключение

Sandboxing — это многоуровневая задача. Нет одного «правильного» решения — выбор зависит от требований к безопасности и приемлемых накладных расходов.

**Ключевые выводы:**
1. **Контейнеры $\neq$ VM**: Docker обеспечивает изоляцию процессов, но не защиту от kernel exploits
2. **gVisor** — хороший выбор для untrusted workloads (serverless), принимаемый overhead
3. **Firecracker** — когда нужна настоящая VM-изоляция с минимальным overhead (serverless)
4. **Не root в контейнерах**: всегда запускайте с `runAsNonRoot: true`
5. **seccomp-bpf + capabilities drop**: обязательно для production контейнеров
6. **Readonly filesystem**: делайте FS readonly + отдельные writable volumes

---

## Литература и источники

1. gVisor. *gVisor: Container Security Isolation*. https://gvisor.dev/docs/
2. Kata Containers. *Architecture Overview*. https://katacontainers.io/docs/
3. Agache, A., et al. (2020). *Firecracker: Lightweight Virtualization for Serverless Applications*. USENIX NSDI 2020. https://www.usenix.org/conference/nsdi20/presentation/agache
4. Chrome. *Security Architecture of Chromium*. https://www.chromium.org/Home/chromium-security/security-architecture-overview/
5. OpenBSD. *pledge(2) man page*. https://man.openbsd.org/pledge
6. Linux man page: seccomp(2). https://man7.org/linux/man-pages/man2/seccomp.2.html
7. Docker. *Docker security*. https://docs.docker.com/engine/security/
8. Kubernetes. *Configure a Security Context for a Pod*. https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
9. Wikipedia: Sandbox (computer security). https://en.wikipedia.org/wiki/Sandbox_(computer_security)
10. CVE-2019-5736 runc container escape. https://nvd.nist.gov/vuln/detail/CVE-2019-5736
