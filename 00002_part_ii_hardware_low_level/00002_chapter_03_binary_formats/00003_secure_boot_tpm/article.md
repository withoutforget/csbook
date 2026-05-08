# Secure Boot, TPM — цепочка доверия

## Введение

В 2011 году Стакс (Stuxnet) — один из первых известных государственных кибероружий — использовал буткит для сокрытия своего присутствия в системе. Буткит заменял загрузочный код на диске, загружался раньше антивируса и был практически невидим для ОС. Именно для противодействия таким угрозам разработаны Secure Boot и TPM.

Традиционно: кто может записать на диск — тот контролирует, что загрузится. Если злоумышленник имеет физический доступ или повышенные привилегии — он может заменить загрузчик. Secure Boot создаёт «цепочку доверия» (chain of trust): от аппаратуры к прошивке к загрузчику к ядру ОС. Каждое звено верифицируется предыдущим.

TPM (Trusted Platform Module) — аппаратный криптографический сопроцессор, который хранит ключи и измерения состояния системы. В связке Secure Boot + TPM: TPM фиксирует что именно было загружено, и система может доказать своё состояние удалённой стороне.

---

## 1. TPM — Trusted Platform Module

### 1.1 Что такое TPM

TPM — специализированный микроконтроллер на материнской плате (или интегрированный в CPU), выполняющий криптографические операции:

- Генерация случайных чисел (RNG)
- Хранение ключей шифрования (RSA, ECC, AES)
- Вычисление и хранение хешей измерений (SHA-1, SHA-256)
- Шифрование/подписывание с ключами, которые никогда не покидают TPM
- Attestation (удалённое подтверждение состояния)

**Спецификации:**
- **TPM 1.2** (2003): RSA-2048, SHA-1
- **TPM 2.0** (2014): RSA/ECC, SHA-256, AES, гибкая алгоритмическая поддержка

Windows 11 требует TPM 2.0. Linux поддерживает TPM 1.2 и 2.0 через `tpm_tis` драйвер.

```bash
# Проверить наличие и версию TPM:
cat /sys/class/tpm/tpm0/tpm_version_major
# 2

# Подробная информация:
tpm2_getcap properties-fixed | grep TPMSpecification
# TPM_PT_SPEC_LEVEL: 0x00000000
# TPM_PT_SPEC_REVISION: 116
# TPM_PT_SPEC_DAY_OF_YEAR: 303
# TPM_PT_SPEC_YEAR: 2016

# На Windows:
Get-WmiObject -Namespace root/cimv2/Security/MicrosoftTpm -Class Win32_Tpm
```

### 1.2 PCR — Platform Configuration Registers

Главная уникальная функция TPM — **PCR (Platform Configuration Registers)**. Это 24 регистра (в TPM 2.0), в которые нельзя напрямую записать — можно только «расширить» (extend):

```
PCR[n] = Hash(PCR[n] || new_measurement)
```

Расширение необратимо (hash-функция): из текущего значения PCR невозможно получить предыдущее. Это позволяет строить «журнал измерений»: каждый компонент записывает своё состояние в PCR и эта запись неизменна.

**Стандартное распределение PCR (TPM 2.0, x86):**

| PCR | Что измеряется |
|-----|---------------|
| 0 | UEFI firmware (код) |
| 1 | UEFI firmware (данные, конфиг) |
| 2 | UEFI Option ROM (extension ROM) |
| 3 | UEFI Option ROM данные |
| 4 | MBR/GPT, загрузочная запись |
| 5 | GPT/partition table |
| 6 | Resume events |
| 7 | Secure Boot state |
| 8-9 | GRUB: конфигурация, команды |
| 10 | iPXE, IMA (Integrity Measurement Architecture) |
| 11-15 | Для ОС (systemd-boot, BitLocker) |
| 16 | Debug |
| 23 | Application support |

```bash
# Прочитать значения PCR:
tpm2_pcrread sha256
# sha256 :
#   0 : 0x9F86D081884C7D659A2FEAA0C55AD015A3BF4F1B2B0B822CD15D6C15B0F00A08
#   1 : 0x2E7AB5A5B5C1B66B2EB90B...
#   4 : 0x0000000000000000000000... (если нет загрузчика в этом boot)
```

Если хотя бы один компонент изменился (другая версия GRUB, другое ядро, другая конфигурация) — значение соответствующего PCR изменится. Это позволяет обнаружить несанкционированные изменения.

### 1.3 TPM Keys — хранение ключей

TPM может создавать ключи двух типов:

**Persistent keys (постоянные):**
- Хранятся в NVRAM TPM
- Остаются после перезагрузки
- Идентифицируются handles (например, 0x81000001)

**Transient keys (временные):**
- Создаются при загрузке из «seed»
- Не хранятся явно — воссоздаются при необходимости

**Primary keys:**
Создаются из primary seed (random значение, хранимое в TPM):
```
Primary Seed → KDF → Primary Key
```

**Child keys:**
Создаются под primary key, «запечатаны» (sealed) в PCR значения:
```
createprimary → parent_key
create (under parent) → child_key (sealed to PCR[7], PCR[11])
```

Sealed key можно расшифровать только если PCR значения соответствуют тем, что были при создании. Если загрузчик изменился — PCR изменится — ключ не расшифруется!

### 1.4 TPM Sealing — привязка ключей к состоянию

```bash
# Создать primary key:
tpm2_createprimary -C e -g sha256 -G rsa -c primary.ctx

# Создать sealed data (ключ шифрования, sealed к PCR 7):
echo -n "my_secret_key" | \
  tpm2_create -C primary.ctx \
              -i - \
              -u sealed.pub \
              -r sealed.priv \
              -L "pcr:sha256:7"

# Расшифровать (только если PCR[7] совпадает!):
tpm2_load -C primary.ctx -u sealed.pub -r sealed.priv -c sealed.ctx
tpm2_unseal -c sealed.ctx -p pcr:sha256:7
# my_secret_key  ← только если PCR[7] не изменился!
```

### 1.5 TPM Attestation

Attestation — механизм, позволяющий доказать удалённой стороне, что система находится в определённом состоянии:

```
Remote Verifier                    Local Machine (с TPM)
     │                                      │
     │── "докажи что у тебя PCR[7]=X" ──→  │
     │                                      │── tpm2_quote: PCR значения
     │                                      │   + подпись TPM Attestation Key
     │                                      │   + Attestation Identity Cert
     │←── quote_blob + signature ──────────│
     │
     │── верифицирует подпись TPM cert
     │── проверяет PCR значения
     │── OK: система не скомпрометирована ✓
```

Применение: Microsoft Azure Attestation, Google Confidential Computing, TPM-based BYOD enrollment.

---

## 2. Secure Boot

### 2.1 Компоненты Secure Boot

**PKI (Public Key Infrastructure) в UEFI:**

```
Platform Key (PK) [OEM/производитель]
    ↓ подписывает
Key Exchange Key (KEK) [Microsoft, OEM]
    ↓ используется для обновления
Authorized Signatures DB (db)  ← хеши/сертификаты разрешённых
                                   загрузчиков (shimx64.efi, bootmgfw.efi)
Forbidden Signatures DB (dbx)  ← отозванные (Boothole CVE-2020-10713,
                                   и другие уязвимые загрузчики)
```

```bash
# Просмотр баз данных Secure Boot:
mokutil --db   # Authorized
mokutil --dbx  # Forbidden
mokutil --kek  # KEK
mokutil --pk   # PK

# Проверить статус:
mokutil --sb-state
# SecureBoot enabled
```

### 2.2 Процесс верификации

```
UEFI (firmware) — содержит db, dbx, KEK, PK в NVRAM
│
├─ Загружает EFI приложение (shimx64.efi или bootmgfw.efi)
├─ Вычисляет hash или проверяет подпись
├─ Сравнивает с db (разрешено?) и dbx (запрещено?)
│
If OK:
├─ Shim загружается
├─ Shim проверяет подпись GRUB (своим встроенным сертификатом)
│
If OK:
├─ GRUB загружается
├─ GRUB проверяет подпись ядра
│
If OK:
└─ Ядро загружается
```

### 2.3 Boothole (CVE-2020-10713)

В 2020 году исследователи Eclypsium обнаружили buffer overflow в GRUB2 в парсере файла `grub.cfg`. Несмотря на Secure Boot, атакующий с правами root мог:
1. Модифицировать `/boot/grub/grub.cfg` (не подписан!)
2. GRUB читал его и выполнял малформированный config
3. Выполнение произвольного кода → обход Secure Boot

Исправление: подписывать grub.cfg ИЛИ усилить обработку ошибок в парсере. Microsoft и Linux дистрибутивы отозвали уязвимые версии shim/GRUB и добавили их хеши в dbx.

Это показывает: Secure Boot — не панацея, а один уровень защиты.

### 2.4 Настройка Secure Boot для пользовательских ключей

```bash
# 1. Сгенерировать свои ключи:
openssl req -new -x509 -newkey rsa:2048 -keyout PK.key \
            -out PK.crt -days 3650 -subj "/CN=My PK/"
openssl req -new -x509 -newkey rsa:2048 -keyout KEK.key \
            -out KEK.crt -days 3650 -subj "/CN=My KEK/"
openssl req -new -x509 -newkey rsa:2048 -keyout db.key \
            -out db.crt -days 3650 -subj "/CN=My DB/"

# 2. Подписать загрузчик:
sbsign --key db.key --cert db.crt --output shimx64.efi.signed shimx64.efi

# 3. Создать EFI Signature Lists:
cert-to-efi-sig-list -g "$(uuidgen)" PK.crt PK.esl
cert-to-efi-sig-list -g "$(uuidgen)" KEK.crt KEK.esl
cert-to-efi-sig-list -g "$(uuidgen)" db.crt db.esl

# 4. Подписать ESL файлы:
sign-efi-sig-list -k PK.key -c PK.crt PK PK.esl PK.auth
sign-efi-sig-list -k PK.key -c PK.crt KEK KEK.esl KEK.auth
sign-efi-sig-list -k KEK.key -c KEK.crt db db.esl db.auth

# 5. Загрузить в UEFI (через efi-updatevar или через UEFI Setup):
efi-updatevar -e -f db.auth db
efi-updatevar -e -f KEK.auth KEK
efi-updatevar -f PK.auth PK   # Установка PK активирует Secure Boot
```

---

## 3. Цепочка доверия (Chain of Trust)

### 3.1 Полная цепочка Secure Boot + TPM

```
Hardware (ROM) → UEFI Firmware
                  │
                  ├─ PCR[0] = Hash(UEFI firmware)
                  ├─ PCR[7] = Hash(Secure Boot state + db/dbx)
                  │
                  ├─ Верифицирует shim (подпись vs db)
                  │
              Shim (подписан Microsoft)
                  │
                  ├─ PCR[4] += Hash(shim)
                  │
                  ├─ Верифицирует GRUB (своим сертификатом)
                  │
              GRUB
                  │
                  ├─ PCR[8] = Hash(grub.cfg команды)
                  ├─ PCR[9] = Hash(grub.cfg файлы)
                  │
                  ├─ Верифицирует ядро (подпись vs shim DB)
                  │
              Linux Kernel
                  │
                  ├─ PCR[11] = Hash(kernel + cmdline) [systemd-stub]
                  │
                  ├─ IMA (Integrity Measurement Architecture):
                  │   PCR[10] += Hash(каждый исполняемый файл, lib)
                  │
              Userspace
                  │
                  └─ TPM содержит PCR значения всей загрузки
                     → BitLocker/LUKS sealed key:
                       только если PCR правильные → ключ доступен
```

### 3.2 BitLocker + TPM (Windows)

BitLocker использует TPM для:

1. **Хранение Volume Master Key (VMK):** VMK зашифрован и запечатан в TPM с привязкой к PCR значениям.

2. **Автоматическая разблокировка:** при загрузке TPM проверяет PCR — если всё совпадает (тот же firmware, та же конфигурация Secure Boot), отдаёт VMK → диск расшифровывается автоматически.

3. **Защита от физического доступа:** вытащить диск из компьютера → нет TPM → PCR не вычислены → VMK не доступен.

```
Структура BitLocker:
Full Volume Encryption Key (FVEK) → шифрует данные
                                    ↑
             Volume Master Key (VMK) → шифрует FVEK
                  ↑
    TPM Sealed Key (привязан к PCR 0,2,4,7,11)
    + Recovery Password (48-цифровой, хранится у пользователя)
    + PIN (опционально)
```

### 3.3 LUKS + TPM (Linux)

```bash
# systemd-cryptenroll: привязать LUKS к TPM
systemd-cryptenroll /dev/sda1 \
    --tpm2-device=auto \
    --tpm2-pcrs=0+7+11  # PCR 0 (firmware), 7 (Secure Boot), 11 (UKI)
# Создаёт TPM-sealed LUKS keyslot

# При загрузке: если PCR 0+7+11 совпадают → TPM автоматически отдаёт ключ
# Нужен также recovery password для случаев обновления firmware

# Проверить текущие slots:
cryptsetup luksDump /dev/sda1
```

---

## 4. Measured Boot и Remote Attestation

### 4.1 Measured Boot

Measured Boot — расширение Secure Boot: вместо просто «разрешить или заблокировать» каждый компонент **измеряется** (хеш записывается в PCR) даже если он не верифицируется.

Это позволяет:
- Обнаружить изменение любого компонента загрузки
- Удалённо доказать состояние машины (attestation)

**Linux IMA (Integrity Measurement Architecture):**
```bash
# IMA измеряет все исполняемые файлы, библиотеки, конфиги
# при их первом открытии:
cat /sys/kernel/security/ima/ascii_runtime_measurements | head -5
# 10 <hash> ima-ng sha256:<hash> /usr/bin/ls
# 10 <hash> ima-ng sha256:<hash> /lib/x86_64-linux-gnu/libc.so.6
# ...
# PCR[10] = chain of hashes of all loaded programs
```

### 4.2 Remote Attestation Flow

```
         Client (машина с TPM)           Server (Attestation Service)
              │                                    │
              │ 1. Запрос на attestation           │
              │←────────────────────────────────── │
              │                                    │
              │ 2. tpm2_quote:                      │
              │    - PCR значения [0..23]           │
              │    - UEFI EventLog (детали)         │
              │    - подписано AIK (Attestation     │
              │      Identity Key) от TPM           │
              │─────────────────────────────────→  │
              │                                    │
              │                          3. Верифицирует:
              │                             - подпись AIK (TPM cert)
              │                             - PCR значения vs expected
              │                             - EventLog согласован?
              │                                    │
              │ 4. Attestation Token (JWT/CWT)      │
              │←────────────────────────────────── │
              │                                    │
              └── использует Token для доступа к ресурсам
```

### 4.3 Практические применения

**Azure Attestation:**
```
Azure VM with vTPM → Azure Attestation Service
"Докажи что это Ubuntu 22.04 с конкретным ядром и без изменённых компонентов"
→ Attestation Token → доступ к Azure Key Vault с ключами шифрования
```

**Kubernetes TLS Bootstrap с TPM:**
Новый узел при первой загрузке доказывает своё состояние control plane через TPM attestation → получает сертификат → присоединяется к кластеру.

---

## 5. Критика и ограничения

### 5.1 Критика Secure Boot

**Монополия Microsoft:** Большинство OEM поставляют компьютеры с только Microsoft KEK, что фактически означает: только Microsoft может добавить сертификаты в db. Linux дистрибутивы должны платить Microsoft за подписание shim.

**Shim backdoor для загрузки неподписанного кода:** MOK (Machine Owner Key) позволяет добавить собственные сертификаты, обходя Microsoft. Удобно для разработчиков, но снижает безопасность.

**Не защищает от:** вредоносного кода в ОС (только до момента загрузки), BIOS-level руткитов если ключи PK скомпрометированы, уязвимостей в самом UEFI (BootHole, LoJax — UEFI rootkit).

```bash
# Полностью отключить Secure Boot из UEFI Setup:
# → система загружается, но без защиты

# Или использовать mokutil для временного отключения:
mokutil --disable-validation
# При перезагрузке: MokManager предложит подтвердить
```

### 5.2 Уязвимость BlackLotus (2023)

BlackLotus — первый известный UEFI bootkit, обходящий Secure Boot на fully patched Windows 11:

1. Использует UEFI vulnerability CVE-2022-21894 (старая уязвимость в shim)
2. Откатывается к уязвимой версии Windows Boot Manager
3. Инфицирует ESP
4. Загружается каждый раз до Windows, не обнаруживается антивирусом

Исправление: обновление dbx для отзыва уязвимых загрузчиков. Но миллионы устаревших систем с не обновлённым dbx остаются уязвимы.

---

## 6. Практическая работа с TPM в Linux

### 6.1 Базовые команды tpm2-tools

```bash
# Установка:
apt install tpm2-tools

# Информация о TPM:
tpm2_getcap properties-fixed

# Список постоянных объектов:
tpm2_getcap handles-persistent

# Создать случайные данные:
tpm2_getrandom 16 --hex

# Простое хранилище ключей:
# 1. Создать первичный ключ (endorsement hierarchy):
tpm2_createprimary -C e -c ek.ctx

# 2. Создать Storage Root Key:
tpm2_createprimary -C o -g sha256 -G rsa -c srk.ctx

# 3. Сделать его постоянным:
tpm2_evictcontrol -C o -c srk.ctx 0x81000001

# 4. Создать seal object с данными:
echo "my secret" | \
  tpm2_create -C 0x81000001 \
              -g sha256 -G keyedhash \
              -i - \
              -u seal.pub -r seal.priv

# 5. Unseal:
tpm2_load -C 0x81000001 -u seal.pub -r seal.priv -c seal.ctx
tpm2_unseal -c seal.ctx
```

### 6.2 Шифрование файлов с помощью TPM

```bash
# Использование TPM для защиты ключа шифрования:
# 1. Создать AES ключ в TPM:
tpm2_createprimary -C e -g sha256 -G ecc -c primary.ctx
tpm2_create -C primary.ctx \
            -g sha256 -G aes \
            -u aes.pub -r aes.priv

tpm2_load -C primary.ctx -u aes.pub -r aes.priv -c aes.ctx

# 2. Зашифровать файл (TPM симметричное шифрование):
tpm2_encryptdecrypt -c aes.ctx -o encrypted.bin plaintext.txt

# 3. Расшифровать:
tpm2_encryptdecrypt -c aes.ctx -d -o decrypted.txt encrypted.bin
```

### 6.3 TPM для SSH ключей (tpm2-pkcs11)

```bash
# Хранение SSH private key в TPM:
apt install tpm2-pkcs11-tools

# Инициализация:
tpm2_ptool init

# Создать token:
tpm2_ptool addtoken --pid=1 --sopin=mysopin --userpin=mypin --label=mytoken

# Создать ключ:
tpm2_ptool addkey --label=mytoken --userpin=mypin --algorithm=rsa2048

# Получить публичный ключ для ~/.ssh/authorized_keys:
ssh-keygen -D /usr/lib/x86_64-linux-gnu/libtpm2_pkcs11.so.0

# SSH с TPM ключом:
ssh -I /usr/lib/x86_64-linux-gnu/libtpm2_pkcs11.so.0 user@server
```

---

## Заключение

Secure Boot и TPM формируют аппаратный фундамент безопасности современных систем. Их связка решает ключевую проблему: как доверять программному обеспечению, если мы не контролируем весь путь от кремния до приложения?

Цепочка доверия: ROM → UEFI Firmware → Shim → GRUB → Kernel — каждое звено верифицируется предыдущим, и TPM документирует это через PCR. BitLocker, LUKS с TPM используют это для «прозрачного» шифрования: ключ доступен только если система в известном состоянии.

Для разработчиков и системных администраторов:
- **Всегда включайте Secure Boot** на production-машинах
- **TPM + полное шифрование диска** — стандарт для ноутбуков с корпоративными данными
- **Следите за dbx обновлениями** — отозванные уязвимые загрузчики могут использоваться атакующими
- **Remote Attestation** — строительный блок Zero Trust Architecture

---

## Литература и источники

1. TCG (Trusted Computing Group). *TPM 2.0 Library Specification*. — https://trustedcomputinggroup.org/resource/tpm-library-specification/

2. UEFI Forum. *UEFI Specification 2.10, Section 7.3: Secure Boot*. — https://uefi.org/specs/UEFI/2.10/07_Services_Boot_Services.html

3. Wikipedia. *Trusted Platform Module*. — https://en.wikipedia.org/wiki/Trusted_Platform_Module

4. Wikipedia. *UEFI Secure Boot*. — https://en.wikipedia.org/wiki/UEFI#Secure_boot

5. Matrosov, A., et al. (2023). *BlackLotus UEFI Bootkit*. ESET Research. — https://www.welivesecurity.com/2023/03/01/blacklotus-uefi-bootkit-myth-confirmed/

6. Eclypsium. (2020). *There's a Hole in the Boot: BootHole / CVE-2020-10713*. — https://eclypsium.com/2020/07/29/theres-a-hole-in-the-boot/

7. Microsoft. *BitLocker Overview*. — https://docs.microsoft.com/en-us/windows/security/information-protection/bitlocker/bitlocker-overview

8. systemd. *systemd-cryptenroll(1)*. — https://www.freedesktop.org/software/systemd/man/systemd-cryptenroll.html

9. tpm2-tools documentation. — https://tpm2-tools.readthedocs.io/en/latest/

10. Linux Kernel Documentation. *Integrity Measurement Architecture*. — https://www.kernel.org/doc/html/latest/security/IMA-templates.html
