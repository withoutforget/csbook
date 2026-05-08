# Аутентификация vs авторизация

## Введение

«Аутентификация» и «авторизация» — два термина, которые часто путают, даже опытные разработчики. Между тем это принципиально разные концепции: первая отвечает на вопрос **«кто ты?»**, вторая — **«что тебе можно?»**. Правильное разграничение этих концепций является основой безопасности любой системы.

**Authentication (AuthN)** — процесс проверки личности: убеждение в том, что человек или система является тем, за кого себя выдаёт. **Authorization (AuthZ)** — процесс определения прав: какие действия и ресурсы доступны аутентифицированному субъекту. В этой статье мы разберём оба процесса, методы аутентификации (пароли, MFA, FIDO2), модели авторизации (RBAC, ABAC) и концепцию Zero Trust.

---

## 1. Authentication — кто ты?

### Факторы аутентификации

Аутентификация основана на трёх категориях факторов:

| Фактор              | Описание                          | Примеры                        |
|--------------------|------------------------------------|-------------------------------|
| Something you know  | Что ты знаешь                     | Пароль, PIN, секретный вопрос  |
| Something you have  | Что у тебя есть                   | Телефон, YubiKey, смарт-карта  |
| Something you are   | Кто ты (биометрия)               | Отпечаток пальца, Face ID      |

**MFA (Multi-Factor Authentication)** — использование двух или более факторов из разных категорий. Один фактор взломан → система ещё защищена.

### Слабые и сильные методы аутентификации

```
СЛАБЫЕ:
- Статический пароль (знаете только вы, но можно украсть/взломать)
- Секретные вопросы (имя кошки легко угадать)
- SMS OTP (SIM swapping атака)

СРЕДНИЕ:
- TOTP (Google Authenticator) — время-зависимый OTP
- Аппаратные TOTP токены

СИЛЬНЫЕ:
- WebAuthn/FIDO2 — cryptographic proof-of-possession
- Смарт-карты с PKI (client certificate TLS)
- Passkeys — phishing-resistant по конструкции
```

---

## 2. TOTP/HOTP — программные аутентификаторы

Уже рассматривались в статье о HMAC. Краткое напоминание:

```python
import hmac
import hashlib
import struct
import time
import base64
import qrcode  # pip install qrcode[pil]

def generate_totp_secret() -> str:
    """Генерация секрета для TOTP"""
    import secrets
    random_bytes = secrets.token_bytes(20)
    return base64.b32encode(random_bytes).decode()

def totp(secret: str, timestamp: float = None) -> str:
    """TOTP (RFC 6238)"""
    key = base64.b32decode(secret.upper())
    t = int((timestamp or time.time()) // 30)
    msg = struct.pack(">Q", t)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    return str(code % 1000000).zfill(6)

def verify_totp(secret: str, user_code: str, window: int = 1) -> bool:
    """Верификация TOTP с временным окном"""
    now = time.time()
    for delta in range(-window, window + 1):
        expected = totp(secret, now + delta * 30)
        if hmac.compare_digest(expected, user_code):
            return True
    return False

secret = generate_totp_secret()
print(f"TOTP Secret: {secret}")
print(f"Current code: {totp(secret)}")
```

### Уязвимости SMS OTP

SMS-коды уязвимы к:
- **SIM Swapping:** злоумышленник переводит ваш номер на свою SIM-карту через социальную инженерию с оператором
- **SS7 атаки:** уязвимости в телефонной инфраструктуре позволяют перехватывать SMS
- **Фишинг в реальном времени:** злоумышленник перенаправляет код с фишингового сайта

**TOTP** надёжнее SMS OTP, но всё равно уязвим к фишингу: злоумышленник может перехватить код в реальном времени.

---

## 3. WebAuthn/FIDO2 — Passkeys

**WebAuthn** (Web Authentication API) и **FIDO2** — современный стандарт аутентификации, основанный на криптографии с открытым ключом.

### Принцип работы

```
Регистрация:
1. Сервер → клиент: challenge
2. Аутентификатор (YubiKey, Face ID, Touch ID) создаёт пару ключей:
   - Закрытый ключ хранится на устройстве (не покидает устройство)
   - Открытый ключ отправляется серверу
3. Сервер хранит открытый ключ, привязанный к пользователю и origin (сайту)

Аутентификация:
1. Сервер → клиент: challenge
2. Аутентификатор подписывает challenge + origin + authenticator data закрытым ключом
3. Сервер проверяет подпись открытым ключом
```

### Phishing-resistant по конструкции

WebAuthn **встраивает origin в подписываемые данные**:

```
Подписываемые данные включают: origin = "https://bank.com"

Если пользователь попал на фишинговый сайт https://bank-fake.com:
  origin в подписи = "https://bank-fake.com"
  Сервер bank.com получает подпись с origin "bank-fake.com"
  Верификация провалится → атака неэффективна!
```

Это принципиальное отличие от TOTP: одноразовый код не привязан к origin и может быть перехвачен фишером.

```python
# WebAuthn реализуется через браузерный JavaScript API
# На сервере используйте библиотеки:
# Python: py_webauthn (pip install webauthn)
# Node.js: @simplewebauthn/server

# Концептуальный пример (серверная сторона)
"""
import webauthn

# Регистрация
registration_options = webauthn.generate_registration_options(
    rp_id="example.com",
    rp_name="Example Corp",
    user_id=b"user123",
    user_name="alice@example.com",
)

# После получения от клиента
registration_verification = webauthn.verify_registration_response(
    credential=<client_response>,
    expected_challenge=registration_options.challenge,
    expected_rp_id="example.com",
    expected_origin="https://example.com",
)

# Аутентификация
authentication_options = webauthn.generate_authentication_options(
    rp_id="example.com",
    allow_credentials=[<stored_credential>],
)

authentication_verification = webauthn.verify_authentication_response(
    credential=<client_response>,
    expected_challenge=authentication_options.challenge,
    expected_rp_id="example.com",
    expected_origin="https://example.com",
    credential_public_key=<stored_public_key>,
    credential_current_sign_count=<stored_count>,
)
"""

# Клиентский JavaScript API
js_example = """
// Регистрация passkey
const credential = await navigator.credentials.create({
    publicKey: {
        challenge: Uint8Array.from(atob(serverChallenge), c => c.charCodeAt(0)),
        rp: { name: "Example", id: "example.com" },
        user: {
            id: Uint8Array.from("user123", c => c.charCodeAt(0)),
            name: "alice@example.com",
            displayName: "Alice"
        },
        pubKeyCredParams: [
            { alg: -7, type: "public-key" },   // ES256
            { alg: -257, type: "public-key" }  // RS256
        ],
        authenticatorSelection: {
            userVerification: "required",  // Биометрия/PIN обязательны
            residentKey: "required"        // Passkey (stored on device)
        }
    }
});

// Аутентификация
const assertion = await navigator.credentials.get({
    publicKey: {
        challenge: Uint8Array.from(atob(serverChallenge), c => c.charCodeAt(0)),
        rpId: "example.com",
        userVerification: "required"
    }
});
"""
print(js_example[:200] + "...")
```

---

## 4. SSO — Single Sign-On

SSO позволяет пользователю аутентифицироваться один раз и получить доступ к множеству сервисов.

```
Без SSO:
  user → app1.com: логин (пароль)
  user → app2.com: логин (тот же пароль?)
  user → app3.com: логин

С SSO:
  user → Identity Provider (IDP): логин (один раз)
  IDP: выдаёт токен
  user → app1.com: токен (нет пароля)
  user → app2.com: токен
  user → app3.com: токен
```

Стандарты SSO: SAML 2.0 (корпоративный), OpenID Connect (веб).

---

## 5. Authorization — что тебе можно?

После успешной аутентификации система должна определить, что именно пользователь может делать.

### ACL — Access Control Lists

Простейшая модель: для каждого ресурса список пользователей и их прав:

```python
class ACL:
    """Access Control List"""
    
    def __init__(self):
        # {resource: {user: set(permissions)}}
        self.permissions = {}
    
    def grant(self, resource: str, user: str, permission: str):
        self.permissions.setdefault(resource, {}).setdefault(user, set()).add(permission)
    
    def check(self, resource: str, user: str, permission: str) -> bool:
        return permission in self.permissions.get(resource, {}).get(user, set())

acl = ACL()
acl.grant("document:123", "alice", "read")
acl.grant("document:123", "alice", "write")
acl.grant("document:123", "bob", "read")

print(acl.check("document:123", "alice", "write"))  # True
print(acl.check("document:123", "bob", "write"))    # False
```

### RBAC — Role-Based Access Control

Пользователи назначаются на роли, роли имеют разрешения. Управлять проще чем ACL при большом числе пользователей:

```python
class RBAC:
    """Role-Based Access Control"""
    
    def __init__(self):
        self.role_permissions = {}  # {role: set(permissions)}
        self.user_roles = {}        # {user: set(roles)}
    
    def define_role(self, role: str, permissions: list):
        self.role_permissions[role] = set(permissions)
    
    def assign_role(self, user: str, role: str):
        self.user_roles.setdefault(user, set()).add(role)
    
    def check(self, user: str, permission: str) -> bool:
        user_roles = self.user_roles.get(user, set())
        for role in user_roles:
            if permission in self.role_permissions.get(role, set()):
                return True
        return False
    
    def get_permissions(self, user: str) -> set:
        result = set()
        for role in self.user_roles.get(user, set()):
            result |= self.role_permissions.get(role, set())
        return result

rbac = RBAC()

# Определение ролей
rbac.define_role("viewer", ["read"])
rbac.define_role("editor", ["read", "write", "create"])
rbac.define_role("admin", ["read", "write", "create", "delete", "manage_users"])

# Назначение ролей
rbac.assign_role("alice", "admin")
rbac.assign_role("bob", "editor")
rbac.assign_role("carol", "viewer")

# Проверки
print(f"Alice can delete: {rbac.check('alice', 'delete')}")    # True
print(f"Bob can delete: {rbac.check('bob', 'delete')}")        # False
print(f"Carol can write: {rbac.check('carol', 'write')}")      # False
print(f"Bob permissions: {rbac.get_permissions('bob')}")
```

### ABAC — Attribute-Based Access Control

ABAC более гибкий: правила основаны на атрибутах пользователя, ресурса, окружения:

```python
from typing import Callable

class ABACPolicy:
    """Attribute-Based Access Control"""
    
    def __init__(self):
        self.policies = []
    
    def add_policy(self, name: str, condition: Callable) -> None:
        """Добавить правило: condition(subject, resource, action, env) -> bool"""
        self.policies.append((name, condition))
    
    def evaluate(self, subject: dict, resource: dict, action: str, env: dict) -> bool:
        """Применить все правила (первое подходящее wins)"""
        for name, condition in self.policies:
            result = condition(subject, resource, action, env)
            if result is not None:
                return result
        return False  # Deny by default

abac = ABACPolicy()

# Правило 1: Admin может всё
abac.add_policy(
    "admin_full_access",
    lambda s, r, a, e: True if s.get("role") == "admin" else None
)

# Правило 2: Пользователь может редактировать только СВОИ документы
abac.add_policy(
    "owner_can_edit",
    lambda s, r, a, e: (
        True if a in ("read", "write") and s.get("user_id") == r.get("owner_id")
        else None
    )
)

# Правило 3: Чтение только в рабочие часы (9-18)
abac.add_policy(
    "business_hours_read",
    lambda s, r, a, e: (
        True if a == "read" and 9 <= e.get("hour", 0) <= 18
        else (False if a == "read" else None)
    )
)

# Тесты
import datetime

alice = {"user_id": "u1", "role": "admin"}
bob = {"user_id": "u2", "role": "user"}
doc = {"doc_id": "d1", "owner_id": "u2"}

env_day = {"hour": 14}    # 14:00 - рабочий час
env_night = {"hour": 22}  # 22:00 - нерабочее время

print(f"Alice (admin) удаляет: {abac.evaluate(alice, doc, 'delete', env_day)}")   # True
print(f"Bob редактирует свой документ: {abac.evaluate(bob, doc, 'write', env_day)}") # True
bob_doc = {"doc_id": "d2", "owner_id": "u99"}
print(f"Bob редактирует чужой документ: {abac.evaluate(bob, bob_doc, 'write', env_day)}") # False
print(f"Bob читает ночью: {abac.evaluate(bob, doc, 'read', env_night)}")           # False
```

### PBAC — Policy-Based AC и ReBAC

**PBAC** (Policy-Based) — решения основаны на детальных политиках (AWS IAM, OPA).

**ReBAC** (Relationship-Based) — авторизация на основе отношений (Google Zanzibar, используется Google Drive, YouTube).

```
Google Zanzibar пример:
  user:alice → owner → folder:home
  folder:home → parent → document:report
  
  Проверка: может ли alice читать document:report?
  alice owner folder:home → alice viewer folder:home (наследование)
  folder:home parent document:report → alice viewer document:report (транзитивность)
```

---

## 6. PAM в Linux

PAM (Pluggable Authentication Modules) — модульная система аутентификации Linux:

```bash
# /etc/pam.d/sshd
auth    required     pam_unix.so         # Проверка пароля
auth    required     pam_google_authenticator.so  # TOTP

# /etc/pam.d/sudo
auth    sufficient   pam_unix.so
auth    required     pam_deny.so

# Проверка настроек
cat /etc/pam.d/common-auth
```

---

## 7. Zero Trust — «никому не доверять»

Традиционная безопасность: периметр («снаружи опасно, внутри безопасно»). После взлома периметра — атакующий двигается по сети свободно.

**Zero Trust** (NIST SP 800-207): «никогда не доверять, всегда проверять»:
- Нет понятия «доверенная внутренняя сеть»
- Каждый запрос аутентифицируется и авторизуется
- Принцип наименьших привилегий
- Непрерывный мониторинг

```python
class ZeroTrustGateway:
    """Концептуальная реализация Zero Trust проверки"""
    
    def check_access(self, request: dict) -> dict:
        result = {
            "allowed": False,
            "factors_checked": []
        }
        
        # 1. Аутентификация пользователя
        if not self._verify_identity(request.get("token")):
            return {**result, "reason": "Authentication failed"}
        result["factors_checked"].append("identity")
        
        # 2. Проверка устройства
        if not self._verify_device(request.get("device_id")):
            return {**result, "reason": "Unregistered device"}
        result["factors_checked"].append("device")
        
        # 3. Авторизация на конкретный ресурс
        if not self._verify_authorization(
            request.get("user_id"),
            request.get("resource"),
            request.get("action")
        ):
            return {**result, "reason": "Not authorized for this resource"}
        result["factors_checked"].append("authorization")
        
        # 4. Контекстные проверки
        if not self._verify_context(request):
            return {**result, "reason": "Suspicious context (location/time)"}
        result["factors_checked"].append("context")
        
        result["allowed"] = True
        return result
    
    def _verify_identity(self, token: str) -> bool:
        # Проверка JWT/session token
        return bool(token)  # Упрощение
    
    def _verify_device(self, device_id: str) -> bool:
        # Проверка зарегистрированного устройства
        trusted_devices = {"device_001", "device_002"}
        return device_id in trusted_devices
    
    def _verify_authorization(self, user_id: str, resource: str, action: str) -> bool:
        return True  # Упрощение — здесь RBAC/ABAC/OPA
    
    def _verify_context(self, request: dict) -> bool:
        # Географическая аномалия, время, скорость и т.д.
        return True  # Упрощение
```

---

## 8. Сравнение моделей авторизации

| Модель  | Простота  | Масштабируемость | Гибкость | Применение                  |
|---------|-----------|-----------------|----------|-----------------------------|
| ACL     | Высокая   | Низкая          | Низкая   | Файловые системы, мелкие приложения|
| RBAC    | Средняя   | Высокая         | Средняя  | Enterprise приложения, Kubernetes|
| ABAC    | Низкая    | Высокая         | Высокая  | AWS IAM, сложные правила    |
| PBAC    | Низкая    | Высокая         | Высокая  | AWS IAM, OPA                |
| ReBAC   | Средняя   | Очень высокая   | Высокая  | Google Drive, GitHub        |

---

## Заключение

Правильное разграничение аутентификации и авторизации — основа безопасной архитектуры.

**Ключевые выводы:**
1. **AuthN** (кто ты?) и **AuthZ** (что можно?) — разные проблемы, решаются разными системами
2. **MFA обязателен** для всех пользователей, особенно с административными правами
3. **Passkeys/WebAuthn** — современный стандарт; лучше чем TOTP из-за phishing-resistance
4. **RBAC** подходит большинству приложений; ABAC — при сложных правилах
5. **Zero Trust** — правильная архитектура для современных систем без периметра
6. **Принцип наименьших привилегий:** каждый компонент имеет только необходимые права

---

## Литература и источники

1. NIST SP 800-207. (2020). *Zero Trust Architecture*. https://csrc.nist.gov/publications/detail/sp/800-207/final
2. NIST SP 800-63B. (2017). *Digital Identity Guidelines: Authentication and Lifecycle Management*. https://pages.nist.gov/800-63-3/sp800-63b.html
3. W3C. *Web Authentication: An API for accessing Public Key Credentials*. https://www.w3.org/TR/webauthn-3/
4. RFC 4226. (2005). *HOTP: An HMAC-Based One-Time Password Algorithm*. https://www.rfc-editor.org/rfc/rfc4226
5. RFC 6238. (2011). *TOTP: Time-Based One-Time Password Algorithm*. https://www.rfc-editor.org/rfc/rfc6238
6. Ferraiolo, D.F., Kuhn, R. (1992). *Role-Based Access Controls*. https://csrc.nist.gov/publications/detail/conference-paper/1992/10/13/role-based-access-controls
7. Zanzibar: Google's Consistent, Global Authorization System. (USENIX ATC 2019). https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/
8. OWASP. *Authentication Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
9. Wikipedia: Multi-factor authentication. https://en.wikipedia.org/wiki/Multi-factor_authentication
10. Wikipedia: Role-based access control. https://en.wikipedia.org/wiki/Role-based_access_control
