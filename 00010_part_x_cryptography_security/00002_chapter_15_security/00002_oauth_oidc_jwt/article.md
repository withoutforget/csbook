# OAuth 2.0, OIDC и JWT

## Введение

Когда вы нажимаете «Войти через Google» или «Подключить к GitHub», в действие вступает **OAuth 2.0** — протокол делегирования доступа. Он позволяет приложениям получать ограниченный доступ к ресурсам пользователя без того, чтобы пользователь передавал свои credentials (пароль) приложению.

**OpenID Connect (OIDC)** надстраивается над OAuth 2.0 и добавляет аутентификацию: теперь приложение знает не только что у него есть доступ, но и кто именно вошёл. **JWT** (JSON Web Token) — это формат токена, который часто используется в этих протоколах.

Это критически важная область: неправильная реализация OAuth 2.0 ведёт к серьёзным уязвимостям — OAuth misconfiguration находится в OWASP Top 10. В этой статье разберём все аспекты подробно.

---

## 1. OAuth 2.0 — делегирование доступа

### Роли в OAuth 2.0

| Роль                    | Описание                                            |
|------------------------|-----------------------------------------------------|
| Resource Owner         | Пользователь, владеющий данными                    |
| Client                 | Приложение, запрашивающее доступ                   |
| Authorization Server   | Выдаёт токены (Google, GitHub, Okta)               |
| Resource Server        | API с защищёнными данными                          |

### Токены OAuth 2.0

- **Access Token** — даёт доступ к API. Короткий срок жизни (15 мин — 1 час)
- **Refresh Token** — для получения нового access token. Длинный срок жизни (дни-месяцы)
- **Authorization Code** — промежуточный, одноразовый, обменивается на access token

---

## 2. Authorization Code Flow + PKCE

**Authorization Code Flow с PKCE** (Proof Key for Code Exchange) — рекомендованный flow для web приложений, мобильных и SPA.

### Полная схема

```
Пользователь → Приложение: «Войти через Google»

Шаг 1: Redirect to Authorization Server
  Приложение генерирует:
    code_verifier = random(43-128 chars)
    code_challenge = base64url(SHA256(code_verifier))
  
  Redirect → https://accounts.google.com/o/oauth2/v2/auth?
    client_id=<app_id>
    redirect_uri=https://app.com/callback
    response_type=code
    scope=openid email profile
    state=<random_anti_csrf_token>
    code_challenge=<base64url_sha256_of_verifier>
    code_challenge_method=S256

Шаг 2: User Authenticates + Consents
  Пользователь логинится в Google
  Google показывает: «app.com хочет получить доступ к вашему email»
  Пользователь нажимает «Разрешить»

Шаг 3: Authorization Code Redirect
  Google → redirect → https://app.com/callback?
    code=<authorization_code>  (действует ~10 минут, одноразовый)
    state=<same_state_value>   (для CSRF защиты)

Шаг 4: Code Exchange (на backend)
  POST https://oauth2.googleapis.com/token
    grant_type=authorization_code
    code=<authorization_code>
    redirect_uri=https://app.com/callback
    client_id=<app_id>
    client_secret=<app_secret>
    code_verifier=<original_verifier>  (PKCE)
  
  Response:
    access_token=<jwt_or_opaque_token>
    token_type=Bearer
    expires_in=3600
    refresh_token=<refresh_token>
    id_token=<oidc_jwt>  (если scope включал openid)

Шаг 5: API Call с токеном
  GET https://api.example.com/data
    Authorization: Bearer <access_token>
```

### Зачем PKCE

PKCE защищает от атаки перехвата authorization code:

```
Без PKCE:
  Атакующий перехватывает authorization code в redirect
  Меняет redirect_uri → получает токены!

С PKCE:
  code_verifier хранится только у клиента
  code_challenge = SHA256(code_verifier) передаётся на Authorization Server
  При обмене code на token нужен оригинальный code_verifier
  Перехваченный code без verifier бесполезен!
```

```python
import secrets
import hashlib
import base64
import urllib.parse

def generate_pkce_pair() -> tuple[str, str]:
    """Генерация PKCE code_verifier и code_challenge"""
    # code_verifier: 32 случайных байта в base64url (43-128 символов)
    code_verifier = secrets.token_urlsafe(32)  # 43 символа
    
    # code_challenge = BASE64URL(SHA256(code_verifier))
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
    
    return code_verifier, code_challenge

def build_authorization_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    code_challenge: str,
    state: str
) -> str:
    """Построение URL для редиректа на Authorization Server"""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    return f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"

# Генерация PKCE
code_verifier, code_challenge = generate_pkce_pair()
state = secrets.token_urlsafe(16)  # Anti-CSRF

print(f"code_verifier: {code_verifier[:16]}...")
print(f"code_challenge: {code_challenge[:16]}...")
print(f"state: {state}")

auth_url = build_authorization_url(
    "https://accounts.google.com/o/oauth2/v2/auth",
    client_id="my_app_client_id",
    redirect_uri="https://myapp.com/callback",
    scope="openid email profile",
    code_challenge=code_challenge,
    state=state
)
print(f"\nAuthorization URL:\n{auth_url[:80]}...")
```

### Обмен кода на токен

```python
import httpx  # pip install httpx

async def exchange_code_for_token(
    token_endpoint: str,
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str
) -> dict:
    """Обмен authorization code на access token"""
    
    async with httpx.AsyncClient() as client:
        response = await client.post(token_endpoint, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": code_verifier  # PKCE!
        })
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.text}")
        
        return response.json()
        # Возвращает: {access_token, token_type, expires_in, refresh_token, id_token}
```

---

## 3. Client Credentials Flow

Для machine-to-machine (M2M) взаимодействия, без участия пользователя:

```python
async def get_client_credentials_token(
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    scope: str
) -> str:
    """Client Credentials Flow: для сервисов, не пользователей"""
    
    async with httpx.AsyncClient() as client:
        response = await client.post(token_endpoint, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope
        })
        
        return response.json()["access_token"]

# Применение: cron job, backend service, микросервис
# Каждые N минут обновляем токен (он короткоживущий)
```

### Device Flow

Для устройств без браузера (TV, CLI):

```
1. Устройство → AS: POST /device/code
2. AS → Устройство: {device_code, user_code, verification_uri}
3. Устройство показывает: «Перейдите на example.com/activate и введите: ABCD-1234»
4. Устройство опрашивает: POST /token?device_code=... каждые 5 секунд
5. Пользователь вводит user_code в браузере на другом устройстве
6. AS → Устройство: {access_token}
```

---

## 4. OpenID Connect (OIDC)

OIDC — это слой аутентификации поверх OAuth 2.0. Добавляет:

1. **id_token** — JWT с информацией о пользователе
2. **UserInfo Endpoint** — API для получения данных пользователя
3. **Discovery Document** — JSON с конфигурацией провайдера (`/.well-known/openid-configuration`)
4. **Стандартные claims:** sub, name, email, picture

### Проверка id_token

```python
import jwt  # pip install PyJWT
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx

def validate_id_token(id_token: str, provider_url: str, client_id: str) -> dict:
    """
    Валидация OIDC id_token
    """
    # 1. Получить публичные ключи провайдера
    discovery = httpx.get(f"{provider_url}/.well-known/openid-configuration").json()
    jwks_uri = discovery["jwks_uri"]
    jwks = httpx.get(jwks_uri).json()
    
    # 2. Декодировать header (без верификации) для получения kid
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    
    # 3. Найти подходящий ключ в JWKS
    from jwt.algorithms import RSAAlgorithm
    for key in jwks["keys"]:
        if key.get("kid") == kid:
            public_key = RSAAlgorithm.from_jwk(key)
            break
    else:
        raise ValueError(f"Key {kid} not found in JWKS")
    
    # 4. Верифицировать подпись и claims
    payload = jwt.decode(
        id_token,
        key=public_key,
        algorithms=["RS256"],
        audience=client_id,      # Проверяем что токен выдан для нашего приложения
        issuer=provider_url       # Проверяем издателя
    )
    
    return payload
    # Возвращает: {sub, iss, aud, exp, iat, name, email, picture, ...}
```

---

## 5. JWT — JSON Web Token

### Структура JWT

JWT состоит из трёх частей, разделённых точками:
```
header.payload.signature
```

```python
import base64
import json
import hmac
import hashlib
import time

def decode_jwt_parts(token: str) -> tuple:
    """Декодирование JWT (без верификации)"""
    parts = token.split(".")
    
    def b64url_decode(s):
        padding = 4 - len(s) % 4
        return base64.urlsafe_b64decode(s + '=' * padding)
    
    header = json.loads(b64url_decode(parts[0]))
    payload = json.loads(b64url_decode(parts[1]))
    signature = b64url_decode(parts[2])
    
    return header, payload, signature

# Пример JWT
example_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIiwiZXhwIjoxNzM1Njg5NjAwLCJpYXQiOjE3MDQxNTM2MDAsInJvbGUiOiJhZG1pbiJ9.signature_here"

# Стандартные claims в JWT payload:
jwt_claims = {
    "sub": "user123",          # Subject (ID пользователя)
    "iss": "https://auth.example.com",  # Issuer
    "aud": "my_api",           # Audience (для кого)
    "exp": int(time.time()) + 3600,  # Expiration
    "iat": int(time.time()),   # Issued At
    "jti": "unique-token-id",  # JWT ID (для отзыва)
    
    # Кастомные claims:
    "email": "user@example.com",
    "roles": ["admin", "editor"],
    "tenant_id": "org_123"
}
```

### JWT как Access Token vs Session Cookie

| Аспект          | JWT Access Token       | Server-side Session    |
|----------------|------------------------|------------------------|
| Хранение        | Клиент (localStorage, memory) | Сервер + cookie|
| Stateless       | Да                     | Нет                   |
| Отзыв           | Трудно (до истечения)  | Легко (удалить из БД) |
| Масштабирование | Легко (нет shared state)| Требует shared storage |
| Размер          | Большой (~1 KB)        | Маленький (~32 байт cookie) |
| Безопасность    | Риск XSS (localStorage)| Риск CSRF (cookie)    |

---

## 6. Проблемы JWT и уязвимости

### Алгоритм «none» (CVE-2015)

```python
# УЯЗВИМОСТЬ: Алгоритм "none"
# Некоторые старые JWT библиотеки принимали alg=none
# Атакующий создаёт: {"alg": "none"}.{"sub": "admin"}.

# ПРАВИЛЬНАЯ ЗАЩИТА: Явно указывайте допустимые алгоритмы
import jwt

def validate_jwt_secure(token: str, secret: bytes) -> dict:
    """Безопасная валидация JWT"""
    # ОБЯЗАТЕЛЬНО указать допустимые алгоритмы!
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],  # Только явно разрешённые
        # algorithms=["none"] НЕ ВКЛЮЧАЙТЕ никогда!
    )
```

### RS256 vs HS256 confusion attack

```python
# УЯЗВИМОСТЬ: Confusion attack
# Атакующий берёт RS256 токен
# Подменяет alg на HS256
# Подписывает ПУБЛИЧНЫМ ключом (который открытый!)
# Некоторые серверы принимают pubkey как HMAC ключ

# ЗАЩИТА:
def validate_jwt_by_alg(token: str, rsa_public_key, hmac_secret: bytes) -> dict:
    header = jwt.get_unverified_header(token)
    alg = header.get("alg")
    
    if alg == "RS256":
        return jwt.decode(token, rsa_public_key, algorithms=["RS256"])
    elif alg == "HS256":
        return jwt.decode(token, hmac_secret, algorithms=["HS256"])
    else:
        raise ValueError(f"Unsupported algorithm: {alg}")
    
    # НЕ делайте: algorithms=["RS256", "HS256"] в одном вызове
    # Это открывает confusion attack!
```

### Revocation — отзыв JWT

JWT stateless — сервер не хранит список токенов. Отозвать токен до истечения срока — нетривиально:

```python
import redis
from datetime import datetime, timedelta

class JWTRevocationList:
    """Список отозванных JWT через Redis"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def revoke(self, jti: str, expires_at: datetime) -> None:
        """Отозвать токен по JTI"""
        ttl = int((expires_at - datetime.utcnow()).total_seconds())
        if ttl > 0:
            self.redis.setex(f"revoked:{jti}", ttl, "1")
    
    def is_revoked(self, jti: str) -> bool:
        """Проверить, отозван ли токен"""
        return self.redis.exists(f"revoked:{jti}") > 0

# Рекомендация: используйте JTI (JWT ID) claim во всех токенах
# При logout — добавляйте JTI в список отозванных до истечения срока
```

---

## 7. Refresh Token Rotation

```python
class RefreshTokenStore:
    """
    Rotation стратегия для refresh tokens:
    при каждом обновлении старый токен инвалидируется,
    выдаётся новый
    """
    
    def __init__(self):
        self.tokens = {}  # {token: {user_id, family, created_at}}
        self.used_tokens = set()  # Использованные токены (защита от replay)
    
    def issue_token(self, user_id: str, family: str = None) -> str:
        """Выдача нового refresh token"""
        import secrets
        token = secrets.token_urlsafe(32)
        if family is None:
            family = secrets.token_urlsafe(8)
        
        self.tokens[token] = {
            "user_id": user_id,
            "family": family,
            "created_at": time.time()
        }
        return token
    
    def rotate(self, old_token: str) -> tuple[str, str]:
        """
        Rotation: инвалидировать старый, выдать новый.
        Если старый уже использован → подозрение на компрометацию!
        """
        if old_token in self.used_tokens:
            # Token reuse detected! Возможная компрометация
            token_data = self.tokens.get(old_token, {})
            family = token_data.get("family")
            
            # Отзываем ВСЕ токены этого семейства
            self._revoke_family(family)
            raise SecurityException("Token reuse detected - all sessions terminated")
        
        if old_token not in self.tokens:
            raise ValueError("Invalid refresh token")
        
        token_data = self.tokens[old_token]
        
        # Помечаем старый как использованный
        self.used_tokens.add(old_token)
        
        # Выдаём новый из того же семейства
        new_token = self.issue_token(token_data["user_id"], token_data["family"])
        access_token = self._generate_access_token(token_data["user_id"])
        
        return access_token, new_token
    
    def _revoke_family(self, family: str):
        """Отозвать все токены семейства"""
        to_revoke = [t for t, d in self.tokens.items() if d.get("family") == family]
        for token in to_revoke:
            del self.tokens[token]
    
    def _generate_access_token(self, user_id: str) -> str:
        return f"access_token_for_{user_id}_{int(time.time())}"

class SecurityException(Exception):
    pass
```

---

## 8. Хранение токенов в браузере

```javascript
// БЕЗОПАСНЫЕ способы хранения access tokens:

// 1. Memory only (НЕ localStorage) — лучшая безопасность от XSS
// Теряется при обновлении страницы
let accessToken = null;

// 2. Session Storage — только для текущей вкладки
sessionStorage.setItem('access_token', token);

// 3. HttpOnly cookie (для refresh token)
// Сервер устанавливает: Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Strict
// JavaScript не может прочитать HttpOnly cookie → защита от XSS

// НЕБЕЗОПАСНО: localStorage
// localStorage.setItem('access_token', token);  // XSS читает всё!
```

---

## Заключение

OAuth 2.0, OIDC и JWT образуют экосистему делегированной аутентификации и авторизации в современных приложениях.

**Ключевые выводы:**
1. **OAuth 2.0 — не аутентификация**, только делегирование доступа. Для аутентификации нужен OIDC поверх
2. **Authorization Code + PKCE** — единственный рекомендованный flow для public clients
3. **Implicit Flow** устарел и небезопасен — не используйте
4. **alg=none** атака — явно указывайте допустимые алгоритмы
5. **Refresh Token Rotation** защищает от кражи refresh tokens
6. **Не храните токены в localStorage** — используйте HttpOnly cookies или memory
7. **state параметр** защищает от CSRF в OAuth flow

---

## Литература и источники

1. RFC 6749. (2012). *The OAuth 2.0 Authorization Framework*. IETF. https://www.rfc-editor.org/rfc/rfc6749
2. RFC 7636. (2015). *Proof Key for Code Exchange by OAuth Public Clients (PKCE)*. IETF. https://www.rfc-editor.org/rfc/rfc7636
3. RFC 7519. (2015). *JSON Web Token (JWT)*. IETF. https://www.rfc-editor.org/rfc/rfc7519
4. OpenID Connect Core 1.0. https://openid.net/specs/openid-connect-core-1_0.html
5. RFC 8628. (2019). *OAuth 2.0 Device Authorization Grant*. IETF. https://www.rfc-editor.org/rfc/rfc8628
6. OAuth 2.0 Security Best Current Practice. https://www.rfc-editor.org/rfc/rfc9700
7. OWASP. *JSON Web Token Security Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
8. Auth0. *OAuth 2.0 and OpenID Connect Overview*. https://auth0.com/docs/get-started/identity-fundamentals/authentication-and-authorization
9. Wikipedia: OAuth. https://en.wikipedia.org/wiki/OAuth
10. Wikipedia: OpenID Connect. https://en.wikipedia.org/wiki/OpenID_Connect
