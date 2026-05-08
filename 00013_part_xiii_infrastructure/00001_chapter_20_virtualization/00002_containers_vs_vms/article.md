# Контейнеры vs виртуальные машины: namespaces, cgroups и изоляция без отдельного ядра

Docker изменил способ развёртывания приложений. Но как контейнер отличается от виртуальной машины? Почему контейнер запускается за миллисекунды, а VM — за секунды? Почему контейнер занимает мегабайты, а VM — гигабайты? Ответ кроется в механизмах ядра Linux: namespaces и cgroups.

## Ключевое отличие: общее ядро

Виртуальная машина запускает **полноценную ОС** с собственным ядром, изолированным от хоста:

```
Физическое железо
      ↑
  Гипервизор (KVM/ESXi)
  ┌──────────┬──────────┐
  │  VM 1    │  VM 2    │
  │ Ядро 1   │ Ядро 2   │
  │ Ubuntu   │ Windows  │
  │ App 1    │ App 2    │
  └──────────┴──────────┘
```

Контейнер **делит ядро хоста** и использует механизмы изоляции пространства имён:

```
Linux-хост (одно ядро)
      ↑
  Container Runtime (containerd/runc)
  ┌──────────┬──────────┐
  │  cont 1  │  cont 2  │
  │ libc     │ libc     │
  │ App 1    │ App 2    │
  └──────────┴──────────┘
        ↑ общее ядро
```

Это принципиальное различие. Контейнер — это просто **изолированный процесс** на хост-ядре. VM — это виртуальный компьютер с собственным ядром.

Последствия:
- Контейнер Linux не запустится на Windows без виртуализации (WSL2 — это тоже VM)
- Компрометация ядра хоста затрагивает все контейнеры
- Контейнеры легче, быстрее, плотнее упакованы
- Контейнеры не обеспечивают сильную изоляцию безопасности по умолчанию

## Linux Namespaces: изоляция видимости

Namespaces (пространства имён) — механизм ядра Linux, ограничивающий видимость глобальных ресурсов для процесса. Каждый namespace создаёт отдельный "вид" системы.

### Виды namespaces

Сейчас в Linux существует 8 типов namespaces:

**1. PID namespace** — изоляция идентификаторов процессов:

```bash
# В контейнере процессы видят "свои" PID
# Хост видит реальные PID

# Запустить bash в новом PID namespace
unshare --pid --fork bash
echo $$  # 1 — bash думает, что он PID 1

# Но на хосте:
ps aux | grep bash  # Реальный PID, например 45231
```

Процесс с PID 1 в контейнере — как init в системе. Если он умирает, контейнер останавливается.

**2. Network namespace** — изоляция сетевого стека:

```bash
# Создать новый network namespace
ip netns add myns

# Список интерфейсов внутри:
ip netns exec myns ip link
# 1: lo: <LOOPBACK> ...  ← только loopback!

# Создать виртуальную пару (veth pair — как патч-кабель)
ip link add veth0 type veth peer name veth1
ip link set veth1 netns myns

# Настроить адреса
ip addr add 192.168.100.1/24 dev veth0
ip netns exec myns ip addr add 192.168.100.2/24 dev veth1

ip link set veth0 up
ip netns exec myns ip link set veth1 up
ip netns exec myns ip link set lo up

# Теперь можно пинговать
ping 192.168.100.2
```

Каждый контейнер получает свой виртуальный сетевой интерфейс. Docker использует мост (bridge) для соединения контейнеров между собой.

**3. Mount namespace** — изоляция файловой системы:

```bash
# В новом mount namespace можно монтировать что угодно
# без влияния на хост

unshare --mount bash
mount --bind /tmp/mydir /mnt/test  # Видно только внутри namespace
# На хосте /mnt/test не изменится
```

**4. UTS namespace** — изоляция hostname и domainname:

```bash
unshare --uts bash
hostname mycontainer
hostname  # mycontainer
# На хосте hostname не изменился
```

**5. IPC namespace** — изоляция межпроцессного взаимодействия (shared memory, semaphores, message queues).

**6. User namespace** — изоляция UID/GID:

```bash
# Пользователь с UID 1000 на хосте
# становится root (UID 0) внутри namespace

unshare --user --map-root-user bash
id  # uid=0(root) gid=0(root)  ← выглядит как root
cat /proc/self/uid_map  # 0 1000 1  ← маппинг: 0→1000
```

User namespaces — основа rootless containers.

**7. Cgroup namespace** — изоляция видимости иерархии cgroups.

**8. Time namespace** (Linux 5.6+) — изоляция системного времени (CLOCK_REALTIME, CLOCK_MONOTONIC).

### Создание namespace программно

```c
// clone() с флагами namespace
#define _GNU_SOURCE
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int child_func(void *arg) {
    printf("Child PID: %d\n", getpid());  // Всегда 1
    return 0;
}

int main() {
    char stack[1024*1024];
    int flags = CLONE_NEWPID | CLONE_NEWNS | CLONE_NEWNET | SIGCHLD;
    
    pid_t pid = clone(child_func, stack + sizeof(stack), flags, NULL);
    waitpid(pid, NULL, 0);
    return 0;
}
```

```python
# Проверка namespace текущего процесса
import os

for ns in ['cgroup', 'ipc', 'mnt', 'net', 'pid', 'user', 'uts']:
    ns_path = f'/proc/self/ns/{ns}'
    if os.path.exists(ns_path):
        print(f'{ns}: {os.readlink(ns_path)}')
# mnt: mnt:[4026531840]
# net: net:[4026531992]
# pid: pid:[4026531836]
```

## cgroups: ограничение ресурсов

Namespaces изолируют **видимость**. cgroups (Control Groups) ограничивают **потребление ресурсов**: CPU, память, I/O, сеть.

### cgroups v1 vs v2

**cgroups v1** (Linux 2.6.24, 2008): несколько независимых иерархий, по одной на подсистему:

```bash
# Структура cgroups v1
ls /sys/fs/cgroup/
# blkio  cpu  cpuacct  cpuset  devices  freezer  memory  net_cls  pids

# Создать группу и ограничить память
mkdir /sys/fs/cgroup/memory/myapp
echo 256M > /sys/fs/cgroup/memory/myapp/memory.limit_in_bytes
echo $$ > /sys/fs/cgroup/memory/myapp/tasks  # Добавить текущий процесс
```

**cgroups v2** (Linux 4.5, 2016; дефолт в большинстве дистрибутивов с 2020):

```bash
# Единая иерархия, mounted в /sys/fs/cgroup
ls /sys/fs/cgroup/
# cgroup.controllers  cgroup.procs  memory.max  cpu.max  ...

# Создать группу и настроить ресурсы
mkdir /sys/fs/cgroup/myapp
echo "+memory +cpu +io" > /sys/fs/cgroup/cgroup.subtree_control

# Ограничить память: 256 MB
echo 268435456 > /sys/fs/cgroup/myapp/memory.max

# Ограничить CPU: 50% (50000 из 100000 мкс в период)
echo "50000 100000" > /sys/fs/cgroup/myapp/cpu.max

# Ограничить количество процессов
echo 100 > /sys/fs/cgroup/myapp/pids.max

# Добавить процесс
echo $$ > /sys/fs/cgroup/myapp/cgroup.procs
```

### Ключевые контроллеры cgroups v2

```bash
# CPU: ограничение и веса
cat /sys/fs/cgroup/myapp/cpu.max     # "50000 100000" = 50%
cat /sys/fs/cgroup/myapp/cpu.weight  # 100 (дефолт), 1-10000

# Memory: лимиты и статистика
cat /sys/fs/cgroup/myapp/memory.max        # hard limit
cat /sys/fs/cgroup/myapp/memory.high       # soft limit (throttle)
cat /sys/fs/cgroup/myapp/memory.swap.max   # лимит swap
cat /sys/fs/cgroup/myapp/memory.current    # текущее использование

# I/O: throttling
# Ограничить чтение/запись для диска 8:0 (sda)
echo "8:0 rbps=10485760 wbps=10485760" > /sys/fs/cgroup/myapp/io.max
# 10 MB/s read, 10 MB/s write

# PIDs
cat /sys/fs/cgroup/myapp/pids.max     # лимит процессов
cat /sys/fs/cgroup/myapp/pids.current # текущее количество
```

### Docker и cgroups

```bash
# Запустить контейнер с ограничениями ресурсов
docker run -d \
  --memory=256m \           # Лимит памяти
  --memory-swap=256m \      # Нет swap (swap = total - memory)
  --cpus=0.5 \              # 50% одного CPU
  --cpu-shares=512 \        # Относительный приоритет (дефолт 1024)
  --pids-limit=100 \        # Не более 100 процессов
  --blkio-weight=100 \      # Приоритет I/O (10-1000)
  nginx

# Проверить cgroup контейнера
CONTAINER_ID=$(docker ps -q)
cat /sys/fs/cgroup/system.slice/docker-${CONTAINER_ID}.scope/memory.max
```

## Capabilities: тонкое управление привилегиями

Традиционная модель Unix: root = все права, non-root = ограниченные права. Linux capabilities разбивают суперпользовательские привилегии на ~40 атомарных единиц:

```
CAP_NET_ADMIN    — управление сетевыми интерфейсами
CAP_NET_BIND_SERVICE — привязка к портам < 1024
CAP_SYS_ADMIN    — широкий набор административных операций
CAP_SYS_PTRACE   — отладка процессов (ptrace)
CAP_CHOWN        — изменение владельца файлов
CAP_KILL         — отправка сигналов любым процессам
CAP_MKNOD        — создание device files
CAP_SYS_TIME     — изменение системного времени
```

```bash
# Проверить capabilities текущего процесса
cat /proc/self/status | grep Cap
# CapInh: 0000000000000000
# CapPrm: 0000000000000000
# CapEff: 0000000000000000
# CapBnd: 000001ffffffffff
# CapAmb: 0000000000000000

# Декодировать
capsh --decode=000001ffffffffff

# Docker: по умолчанию контейнер получает ограниченный набор
docker run --cap-drop ALL --cap-add NET_BIND_SERVICE nginx
# Убрать все, добавить только нужное

# Добавить все (небезопасно!)
docker run --privileged nginx  # Все capabilities + доступ к устройствам
```

```python
import ctypes
import struct

# Получить capabilities процесса через syscall
def get_capabilities():
    # capget syscall
    CAPGET = 125
    header = struct.pack('II', 0x20080522, 0)  # version, pid=self
    data = struct.pack('II', 0, 0) * 2  # effective, permitted
    
    # В реальном коде использовать libcap
    pass

# Практичнее: использовать subprocess
import subprocess
result = subprocess.run(['capsh', '--print'], capture_output=True, text=True)
print(result.stdout)
```

## seccomp: фильтрация системных вызовов

seccomp (Secure Computing Mode) позволяет ограничить набор syscall, доступных процессу. Атака через системный вызов невозможна, если он заблокирован:

```c
// Пример seccomp-фильтра через libseccomp
#include <seccomp.h>

int main() {
    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_KILL);  // По умолчанию: убить
    
    // Разрешить конкретные syscall
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(read), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(write), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(exit), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(exit_group), 0);
    
    seccomp_load(ctx);
    // Теперь любой другой syscall убьёт процесс
    
    write(1, "Hello, seccomp!\n", 16);
    return 0;
}
```

```bash
# Docker использует seccomp профиль по умолчанию
# Блокирует ~44 syscall из ~380+

# Отключить seccomp (для отладки)
docker run --security-opt seccomp=unconfined nginx

# Применить кастомный профиль
docker run --security-opt seccomp=my-profile.json nginx
```

```json
// Пример seccomp профиля Docker
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": ["read", "write", "open", "close", "stat",
                "fstat", "lstat", "poll", "lseek", "mmap"],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

## OverlayFS: слоёная файловая система

Образы Docker состоят из слоёв. OverlayFS объединяет несколько директорий в единое дерево:

```
Образ nginx:latest:
┌─────────────────────┐  ← upperdir (read-write layer)
│  container-specific │
├─────────────────────┤
│  nginx config layer │  ← lowerdir[0] (read-only)
├─────────────────────┤
│  nginx binary layer │  ← lowerdir[1] (read-only)
├─────────────────────┤
│  ubuntu base layer  │  ← lowerdir[2] (read-only)
└─────────────────────┘
```

```bash
# Пример OverlayFS вручную
mkdir lower upper work merged

echo "base" > lower/file.txt

mount -t overlay overlay \
  -o lowerdir=lower,upperdir=upper,workdir=work \
  merged

# Читаем из нижнего слоя
cat merged/file.txt  # "base"

# Изменяем файл — он копируется в upper (copy-on-write)
echo "modified" > merged/file.txt
cat upper/file.txt  # "modified"
cat lower/file.txt  # "base" — не изменился

# Удаление создаёт whiteout-файл в upper
rm merged/file.txt
ls -la upper/  # .wh.file.txt — маркер удаления
```

### Слои Docker образов

```dockerfile
# Каждая инструкция = новый слой
FROM ubuntu:22.04          # Базовый слой (импортируется)
RUN apt-get update \       # Слой 1 (кешируется)
    && apt-get install -y nginx
COPY nginx.conf /etc/nginx/ # Слой 2
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

```bash
# Просмотр слоёв образа
docker image inspect nginx | jq '.[0].RootFS.Layers'
docker history nginx

# Слои хранятся в
ls /var/lib/docker/overlay2/
```

**Кеширование слоёв**: Docker кеширует каждый слой. Если слой не изменился — пересборка не нужна. Поэтому важно порядок инструкций:

```dockerfile
# ПЛОХО: копируем весь код перед установкой зависимостей
COPY . /app
RUN pip install -r requirements.txt  # Перезапускается при любом изменении кода

# ХОРОШО: сначала зависимости (редко меняются)
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt  # Кеш работает
COPY . /app  # Только этот слой пересобирается при изменении кода
```

## Container Runtime: runc, containerd, CRI-O

Выполнение контейнера — многоуровневый процесс:

```
Kubernetes / Docker CLI
        ↓
containerd или CRI-O  (high-level runtime)
        ↓
runc                  (low-level OCI runtime)
        ↓
Linux kernel (namespaces + cgroups)
```

### OCI (Open Container Initiative)

OCI стандартизирует два компонента:
- **Image Spec**: формат слоёв образа
- **Runtime Spec**: как запускать контейнер (config.json)

```json
// config.json (OCI Runtime Bundle)
{
  "ociVersion": "1.0.2",
  "process": {
    "args": ["/bin/bash"],
    "env": ["PATH=/usr/local/bin:/usr/bin:/bin"],
    "cwd": "/"
  },
  "root": {
    "path": "rootfs",
    "readonly": false
  },
  "linux": {
    "namespaces": [
      {"type": "pid"},
      {"type": "network"},
      {"type": "mount"},
      {"type": "uts"},
      {"type": "ipc"}
    ],
    "resources": {
      "memory": {
        "limit": 268435456
      }
    }
  }
}
```

### runc

**runc** — эталонная реализация OCI Runtime. Написан на Go. Создаёт namespaces и cgroups, запускает процесс:

```bash
# Запустить контейнер с runc напрямую
mkdir -p /mycontainer/rootfs
docker export $(docker create ubuntu) | tar -C /mycontainer/rootfs -xf -

cd /mycontainer
runc spec  # Создать шаблон config.json

# Запустить
runc run mycontainer-id

# Список запущенных контейнеров
runc list

# Kill
runc kill mycontainer-id SIGTERM
runc delete mycontainer-id
```

### containerd

**containerd** — высокоуровневый runtime, управляет:
- Загрузкой образов (pull, push)
- Хранением образов и слоёв
- Выполнением контейнеров (через runc/shim)
- Снимками (snapshots)

```bash
# ctr — CLI для containerd
ctr images pull docker.io/library/nginx:latest
ctr containers create docker.io/library/nginx:latest nginx-container
ctr tasks start nginx-container

# nerdctl — Docker-совместимый CLI для containerd
nerdctl run -d -p 80:80 nginx
nerdctl ps
nerdctl images
```

### CRI-O

CRI-O — легковесный runtime специально для Kubernetes. Реализует CRI (Container Runtime Interface):

```yaml
# Kubernetes Pod использует CRI-O через kubelet
apiVersion: v1
kind: Pod
metadata:
  name: nginx-pod
spec:
  containers:
  - name: nginx
    image: nginx:latest
    resources:
      limits:
        memory: "256Mi"
        cpu: "500m"
```

## Docker Architecture

Docker состоит из нескольких компонентов:

```
docker CLI
    ↓ REST API (UNIX socket: /var/run/docker.sock)
dockerd (Docker daemon)
    ↓
containerd
    ↓
containerd-shim
    ↓
runc → Container Process
```

```bash
# Жизненный цикл Docker контейнера
docker pull nginx              # Скачать образ
docker create nginx            # Создать контейнер (не запускать)
docker start <container_id>    # Запустить
docker pause <container_id>    # Заморозить (SIGSTOP)
docker unpause <container_id>  # Разморозить
docker stop <container_id>     # SIGTERM + SIGKILL через timeout
docker kill <container_id>     # SIGKILL немедленно
docker rm <container_id>       # Удалить

# Или всё вместе
docker run --rm -it nginx bash

# Просмотр процессов внутри контейнера
docker top <container_id>
docker stats  # CPU/memory real-time

# Inspect: все параметры контейнера
docker inspect <container_id> | jq '.[0].HostConfig'
```

### Docker Networking

```bash
# Типы сетей Docker
docker network ls
# bridge  — дефолт, NAT через iptables
# host    — прямо на хост-стеке (нет изоляции)
# none    — нет сети
# overlay — для Docker Swarm/multi-host

# Создать кастомную bridge сеть
docker network create \
  --driver bridge \
  --subnet 172.20.0.0/16 \
  --ip-range 172.20.240.0/20 \
  mynetwork

# Запустить контейнеры в одной сети
docker run -d --network mynetwork --name db postgres
docker run -d --network mynetwork --name app myapp
# app может обращаться к db по имени "db"

# iptables правила Docker
iptables -t nat -L DOCKER
```

### Docker Volumes

```bash
# Типы хранилищ
docker run -v /host/path:/container/path nginx  # Bind mount
docker run -v myvolume:/data nginx               # Named volume
docker run --tmpfs /tmp nginx                    # tmpfs (RAM)

# Управление volumes
docker volume create myvolume
docker volume ls
docker volume inspect myvolume
docker volume rm myvolume

# Backup volume
docker run --rm \
  -v myvolume:/data \
  -v $(pwd):/backup \
  ubuntu tar czf /backup/backup.tar.gz /data
```

## Rootless Containers

Традиционный Docker требует root или группу `docker`, что небезопасно. Rootless containers решают проблему через user namespaces:

```bash
# Установка rootless Docker (Ubuntu)
apt-get install -y docker-ce-rootless-extras
dockerd-rootless-setuptool.sh install

# Запуск
systemctl --user start docker
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock

docker run hello-world  # Работает без sudo!

# Данные хранятся в ~/.local/share/docker/
# Порты < 1024 недоступны по умолчанию
```

```bash
# Podman — rootless по умолчанию
# Не требует daemon
podman run -it ubuntu bash
podman build -t myimage .
podman pod create --name mypod
podman run --pod mypod nginx
```

Rootless использует `newuidmap`/`newgidmap` для маппинга UID в user namespace.

## gVisor и Kata: изоляция уровня VM

Контейнеры делят ядро. Если ядро уязвимо — атакующий получает доступ к хосту. Решения для усиленной изоляции:

### gVisor (Google)

gVisor добавляет слой перехвата syscall:

```
Container Process
      ↓ syscalls
  Sentry (Go userspace kernel)  ← gVisor перехватывает
      ↓ ограниченный набор syscall
  Host Kernel
```

```bash
# Установка gVisor (runsc)
wget https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc
chmod +x runsc
mv runsc /usr/local/bin/

# Регистрация в containerd/Docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "runtimes": {
    "runsc": {
      "path": "/usr/local/bin/runsc"
    }
  }
}
EOF
systemctl restart docker

# Запустить контейнер с gVisor
docker run --runtime=runsc nginx
```

Преимущества: контейнер "видит" не реальное ядро Linux, а упрощённую реализацию на Go. Атака через syscall значительно затруднена.

Недостатки: оверхед производительности (особенно для I/O), не все syscall реализованы.

### Kata Containers

Kata запускает каждый контейнер в лёгкой виртуальной машине с собственным ядром:

```
Container
    ↓
  MicroVM (QEMU/Cloud Hypervisor/Firecracker)  ← собственное ядро
    ↓
  Host Kernel + Hypervisor
```

```bash
# Kata использует virtio-fs для общих файловых систем
# и специальный оптимизированный kernel

# В Kubernetes
apiVersion: v1
kind: Pod
metadata:
  annotations:
    io.kubernetes.cri.untrusted-workload: "true"
spec:
  runtimeClassName: kata-containers
  containers:
  - name: nginx
    image: nginx
```

Kata обеспечивает изоляцию уровня VM при Docker-совместимом интерфейсе. Amazon Firecracker (используется в AWS Lambda) — аналогичный подход.

## Сравнение: VM vs Containers vs gVisor vs Kata

```
┌──────────────┬────────┬───────────┬────────┬──────────┐
│              │ VM     │ Container │ gVisor │ Kata     │
├──────────────┼────────┼───────────┼────────┼──────────┤
│ Изоляция     │ Высокая│ Средняя   │ Высокая│ Высокая  │
│ Производит.  │ ~95%   │ ~99%      │ ~80%   │ ~97%     │
│ Старт        │ секунды│ мс        │ мс     │ ~100мс   │
│ Размер образа│ GB     │ MB        │ MB     │ MB+kernel│
│ Общее ядро   │ Нет    │ Да        │ Частично│ Нет     │
│ Применение   │ Multi- │ Микросерв.│ Untrust│ Untrust  │
│              │ tenancy│ Dev/Prod  │ workld │ workld   │
└──────────────┴────────┴───────────┴────────┴──────────┘
```

## Практические советы по безопасности контейнеров

```dockerfile
# Многоэтапная сборка — минимальный финальный образ
FROM golang:1.21 AS builder
WORKDIR /app
COPY . .
RUN CGO_ENABLED=0 go build -o myapp

FROM scratch  # ← пустой образ!
COPY --from=builder /app/myapp /myapp
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
ENTRYPOINT ["/myapp"]
# Финальный образ: только бинарник + сертификаты ≈ 10 MB
```

```dockerfile
# Запуск от непривилегированного пользователя
FROM ubuntu:22.04
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser  # Не root!
WORKDIR /home/appuser
```

```bash
# Сканирование образа на уязвимости
trivy image nginx:latest
grype nginx:latest

# Проверка конфигурации Docker
docker bench security

# Ограничения безопасности при запуске
docker run \
  --read-only \              # Read-only filesystem
  --tmpfs /tmp \             # tmpfs для временных файлов
  --no-new-privileges \      # Запрет повышения привилегий
  --cap-drop ALL \           # Убрать все capabilities
  --cap-add NET_BIND_SERVICE \ # Добавить только нужные
  --security-opt no-new-privileges:true \
  --security-opt apparmor=docker-default \
  nginx
```

## Итог

Контейнеры и виртуальные машины — разные инструменты с разными компромиссами:

1. **Ядро**: контейнеры делят ядро хоста через namespaces, VM имеют собственное
2. **Namespaces**: pid, net, mnt, uts, ipc, user, cgroup — изолируют видимость ресурсов
3. **cgroups v2**: единая иерархия для ограничения CPU, памяти, I/O, PID
4. **Capabilities**: тонкий контроль привилегий вместо бинарного root/non-root
5. **seccomp**: фильтрация системных вызовов для уменьшения поверхности атаки
6. **OverlayFS**: copy-on-write слои для эффективного хранения образов
7. **runc → containerd → Docker**: стек container runtime с OCI стандартами
8. **Rootless containers**: безопасность через user namespaces без root
9. **gVisor/Kata**: усиленная изоляция для недоверенных нагрузок

## Литература

1. Kerrisk, M. (2013). *Namespaces in operation*. LWN.net series. https://lwn.net/Articles/531114/

2. Docker Inc. *Docker Documentation*. https://docs.docker.com/

3. Open Container Initiative. *OCI Runtime Specification*. https://github.com/opencontainers/runtime-spec

4. Google. *gVisor: Sandboxed Container Runtime*. https://gvisor.dev/docs/

5. Kata Containers. *Kata Containers Architecture*. https://katacontainers.io/docs/

6. Menage, P. (2004). *CGROUPS*. Linux Kernel Documentation. https://www.kernel.org/doc/Documentation/cgroup-v1/cgroups.txt

7. Linux Kernel Documentation. *cgroups v2*. https://www.kernel.org/doc/Documentation/admin-guide/cgroup-v2.rst

8. Bui, T. (2015). *Analysis of Docker Security*. arXiv:1501.02967.

9. Zawinski, J., et al. *runc: CLI tool for spawning and running containers*. https://github.com/opencontainers/runc

10. Red Hat. *A Practical Introduction to Container Security*. https://www.redhat.com/en/blog/container-security-fundamentals
