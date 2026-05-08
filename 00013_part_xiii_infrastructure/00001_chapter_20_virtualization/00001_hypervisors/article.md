# Гипервизоры: KVM, Xen, ESXi — как виртуальные машины делят железо

Облачный сервер, который вы арендуете у AWS или Google Cloud, — это не физическая машина. Это виртуальная машина, работающая на одном из тысяч физических серверов. Технология, делающая это возможным — гипервизор. Понимание его работы объясняет, почему виртуализация изменила IT-индустрию, и помогает принимать правильные решения при проектировании инфраструктуры.

## Зачем нужна виртуализация

До виртуализации: один сервер = одна ОС = одно приложение. Типичная загрузка CPU — 5-15%. Миллионы серверов простаивают.

Виртуализация решает:

1. **Изоляция**: разные клиенты и приложения не мешают друг другу
2. **Эффективность**: один физический сервер = десятки VM = 70-80% загрузки CPU
3. **Портабельность**: VM — это файл; легко перенести или клонировать
4. **Восстановление**: snapshot → откат к рабочему состоянию за секунды
5. **Тестирование**: безопасная среда для экспериментов
6. **Консолидация**: меньше физических серверов = меньше затрат

## Тип 1 vs Тип 2: две модели гипервизоров

### Type 1 (Bare-Metal Hypervisor)

Гипервизор типа 1 работает **напрямую на железе**, без хост-ОС:

```
Physical Hardware
        ↑
   Hypervisor (Type 1)
   ┌─────┬─────┬─────┐
   │ VM1 │ VM2 │ VM3 │  ← гостевые ОС
   └─────┴─────┴─────┘
```

Примеры: VMware ESXi, Microsoft Hyper-V, Xen, KVM (формально — гибрид).

Преимущества: максимальная производительность, нет оверхеда хост-ОС.
Применение: продакшн-серверы, облачные провайдеры.

### Type 2 (Hosted Hypervisor)

Гипервизор типа 2 работает **как приложение** поверх хост-ОС:

```
Physical Hardware
        ↑
   Host OS (Windows/Linux/macOS)
        ↑
   Hypervisor App (Type 2)
   ┌─────┬─────┐
   │ VM1 │ VM2 │  ← гостевые ОС
   └─────┴─────┘
```

Примеры: VirtualBox, VMware Workstation, Parallels Desktop.

Преимущества: легко установить, используется инфраструктура хост-ОС.
Применение: разработка, тестирование, Desktop.

## KVM: ядро Linux как гипервизор

KVM (Kernel-based Virtual Machine) — модуль ядра Linux, превращающий Linux в гипервизор типа 1 (с оговорками — формально гибрид).

### Архитектура KVM

```
Hardware (Intel VT-x / AMD-V)
        ↑
Linux Kernel + KVM module (/dev/kvm)
        ↑
QEMU (userspace) — эмуляция устройств
        ↑
Guest VM (полноценная ОС)
```

**QEMU** (Quick Emulator) работает в userspace и отвечает за эмуляцию устройств (диск, сеть, USB). **KVM** — только для виртуализации CPU и памяти, работает в kernelspace.

### Intel VT-x и AMD-V: аппаратная виртуализация

До 2005 года процессоры не поддерживали виртуализацию аппаратно. Гипервизоры использовали трудоёмкие программные техники (binary translation).

Intel VT-x (VMX) и AMD-V (SVM) добавили специальные режимы процессора:

- **VMX root mode**: гипервизор выполняется с полными правами
- **VMX non-root mode**: гостевая ОС выполняется в изолированном окружении

Привилегированные инструкции в VMX non-root вызывают VM Exit → гипервизор перехватывает и эмулирует → VM Entry возвращает управление гостю.

```bash
# Проверка поддержки виртуализации
grep -E 'vmx|svm' /proc/cpuinfo | head -1
# vmx = Intel VT-x
# svm = AMD-V

# Проверка, загружен ли KVM
lsmod | grep kvm
# kvm_intel или kvm_amd

# Интерфейс KVM
ls /dev/kvm  # Должен существовать
```

### QEMU + KVM: запуск VM

```bash
# Создание образа диска
qemu-img create -f qcow2 ubuntu.qcow2 20G

# Установка ОС
qemu-system-x86_64 \
  -enable-kvm \
  -m 4G \                         # 4 GB RAM
  -cpu host \                      # Использовать возможности хост-CPU
  -smp 4 \                         # 4 виртуальных CPU
  -drive file=ubuntu.qcow2,if=virtio \  # Диск через virtio
  -net nic,model=virtio \          # Сеть через virtio
  -net user \
  -cdrom ubuntu.iso \
  -boot d                          # Загружаться с CD
```

### libvirt: управление KVM

libvirt — универсальный API для управления виртуализацией:

```bash
# Установка
apt-get install libvirt-daemon qemu-kvm virt-manager

# virsh — CLI для libvirt
virsh list --all               # Список всех VM
virsh start myvm               # Запустить VM
virsh shutdown myvm            # Мягкое выключение
virsh destroy myvm             # Принудительное выключение
virsh snapshot-create-as myvm snap1  # Создать снимок
virsh snapshot-revert myvm snap1     # Откатиться к снимку
virsh migrate myvm --live qemu+ssh://otherhost/system  # Live migration

# Определение VM через XML
virsh define ubuntu.xml

# ubuntu.xml
cat > ubuntu.xml << 'EOF'
<domain type='kvm'>
  <name>ubuntu-vm</name>
  <memory unit='GiB'>4</memory>
  <vcpu>4</vcpu>
  <os>
    <type arch='x86_64' machine='pc-q35-6.2'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/><apic/>
  </features>
  <cpu mode='host-model'/>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/ubuntu.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <graphics type='vnc' port='-1' autoport='yes'/>
  </devices>
</domain>
EOF
```

## Xen: паравиртуализация

Xen — один из первых open-source гипервизоров. Использовался в первых версиях Amazon EC2.

### Архитектура Xen

```
Hardware
   ↑
Xen Hypervisor (thin layer)
   ↑──────────────────────────────────
   Domain 0 (Dom0)          DomU (гостевые VM)
   Privileged domain         Unprivileged
   Управляет железом         Изолированные
   ОС: Linux                 ОС: любая
```

**Dom0** — привилегированная виртуальная машина, имеющая доступ к реальным устройствам. Запускает обычный Linux. DomU не имеет прямого доступа к железу — только через Dom0.

### PV vs HVM

**Паравиртуализация (PV)**: гостевая ОС знает, что работает в виртуальной машине, и использует специальные Xen API вместо нативных инструкций. Требует модификации гостевой ОС. Высокая производительность без аппаратной поддержки.

**Полная виртуализация (HVM)**: гостевая ОС не знает, что виртуальная. Использует Intel VT-x/AMD-V. Работает любая ОС (Windows, BSD).

**PVH**: гибрид — паравиртуализированное окружение, но с минимальными изменениями гостевой ОС.

## VMware ESXi

ESXi — проприетарный гипервизор VMware, широко используемый в корпоративной среде:

```
Преимущества ESXi:
- Зрелость и стабильность (с 2001 года)
- vCenter: централизованное управление кластерами
- vMotion: live migration без остановки VM
- DRS: автоматическая балансировка нагрузки
- HA: High Availability — автоматический перезапуск VM при сбое хоста
- Storage vMotion: перемещение дисков без остановки

Недостатки:
- Дорогая лицензия
- Привязка к VMware экосистеме
- В 2023 Broadcom купила VMware и повысила цены
```

## virtio: эффективные виртуальные устройства

Без virtio гипервизор эмулирует реальное железо (e1000 Ethernet, IDE диск). Это медленно.

virtio — стандарт для виртуальных устройств: вместо эмуляции HDD или NIC, гостевая ОС использует виртуальное устройство, оптимизированное для виртуализации:

```
Без virtio:
Guest ↔ IDE driver ↔ IDE emulation (QEMU) ↔ реальный диск
Latency: высокая (много уровней эмуляции)

С virtio:
Guest ↔ virtio-blk driver ↔ virtio-blk backend (QEMU) ↔ реальный диск
Latency: значительно меньше
```

```bash
# Устройства virtio в гостевой ОС:
lspci | grep -i virtio
# 00:03.0 Ethernet controller: Red Hat, Inc. Virtio network device
# 00:04.0 SCSI storage controller: Red Hat, Inc. Virtio block device
```

## Memory Overcommit

Физической RAM на хосте меньше, чем суммарная RAM всех VM. Это называется overcommit:

```
Хост: 128 GB RAM
VM1: 32 GB
VM2: 32 GB
VM3: 32 GB
VM4: 32 GB
Итого: 128 GB ← по максимуму, но VM часто используют меньше

Overcommit 2x:
VM1-8: по 32 GB = 256 GB суммарно
Физически: 128 GB
Работает, если среднее использование < 50%
```

### Balloon driver

Если памяти не хватает, KVM использует balloon driver — виртуальный драйвер в гостевой ОС, который "раздувается", "занимая" память гостя, которую затем гипервизор отдаёт другим VM.

```
Хосту нужна память:
1. Гипервизор просит balloon driver в VM "надуться"
2. Driver выделяет страницы памяти внутри VM (гость думает, что они заняты)
3. Гипервизор получает эти страницы обратно
4. VM немного "не хватает" памяти → начинает использовать swap
```

### KSM: Kernel Same-page Merging

```bash
# KSM: ядро ищет одинаковые страницы памяти в разных VM и мёржит их
# Типичный случай: несколько VM с одной и той же ОС → общие страницы ядра

cat /sys/kernel/mm/ksm/pages_sharing  # Сколько страниц объединено
cat /sys/kernel/mm/ksm/run            # 0=off, 1=on, 2=pause
echo 1 > /sys/kernel/mm/ksm/run      # Включить KSM
```

## IOMMU и VT-d: PCI Passthrough

IOMMU (Input/Output Memory Management Unit) позволяет напрямую передать физическое устройство (GPU, NIC) виртуальной машине:

```bash
# Включение IOMMU (в /etc/default/grub)
GRUB_CMDLINE_LINUX_DEFAULT="intel_iommu=on iommu=pt"

# Привязка устройства к vfio-pci
echo "10de 2204" > /sys/bus/pci/drivers/vfio-pci/new_id  # NVIDIA GPU

# В QEMU: передача GPU в VM
qemu-system-x86_64 \
  -device vfio-pci,host=01:00.0 \   # GPU напрямую в VM!
  ...
```

GPU passthrough позволяет запускать игры или ML-задачи в VM с почти нативной производительностью.

## Live Migration

Live migration — перенос работающей VM с одного физического хоста на другой без прерывания сервиса:

```
1. Начало: гость продолжает работать на хосте A
2. Копирование памяти: грязные страницы копируются на хост B
3. Итерации: копирование "пятна" изменений
4. Suspend момент: очень короткая остановка (10-100 мс)
5. Состояние CPU и устройств: передача на B
6. Возобновление: VM работает на хосте B
7. Очистка: удаление VM с хоста A
```

```bash
# Живая миграция через virsh
virsh migrate --live ubuntu-vm \
  qemu+ssh://192.168.1.2/system \
  --unsafe \
  --timeout 120

# VMware vMotion: GUI-кнопка в vCenter
```

Live migration — ключевая функция для:
- Maintenance без downtime
- Балансировки нагрузки
- Энергосбережения (консолидация на ночь)

## Итог

Гипервизоры трансформировали IT:

1. **Type 1** (bare-metal) — прямой доступ к железу; ESXi, KVM, Xen для продакшна
2. **Type 2** (hosted) — VirtualBox, Workstation для разработки
3. **KVM** — модуль Linux + QEMU; Intel VT-x/AMD-V; стандарт для Linux/Cloud
4. **Xen** — паравиртуализация (PV) и HVM; исторически первый для облаков
5. **ESXi** — корпоративный выбор с богатой экосистемой vSphere
6. **virtio** — паравиртуализированные устройства с высокой производительностью
7. **Memory overcommit + KSM** — эффективное использование физической памяти
8. **IOMMU/VT-d** — PCI passthrough для нативной производительности устройств

## Литература

1. Barham, P., et al. (2003). *Xen and the Art of Virtualization*. SOSP 2003.

2. Kivity, A., et al. (2007). *KVM: the Linux Virtual Machine Monitor*. Linux Symposium 2007.

3. Goldberg, R. (1974). *Survey of Virtual Machine Research*. Computer, 7(6), 34-45.

4. VMware. *vSphere Hypervisor Documentation*. https://docs.vmware.com/en/VMware-vSphere/

5. Red Hat. *Virtualization Deployment and Administration Guide (KVM)*. https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/configuring_and_managing_virtualization/

6. QEMU. *QEMU documentation*. https://www.qemu.org/documentation/

7. Russell, R. (2008). *virtio: Towards a De-Facto Standard For Virtual I/O Devices*. SIGOPS Operating Systems Review.

8. Clark, C., et al. (2005). *Live Migration of Virtual Machines*. NSDI 2005.

9. KVM Wiki. https://www.linux-kvm.org/

10. Intel. *Intel® Virtualization Technology (Intel® VT) for IA-32, Intel® 64 and Intel® Architecture*. https://www.intel.com/content/www/us/en/virtualization/virtualization-technology/intel-virtualization-technology.html
