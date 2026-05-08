# Соль, KDF и правильное хранение паролей

## Введение

Хранение паролей — одна из наиболее часто неправильно реализуемых задач в разработке. В базах данных взломанных сервисов регулярно обнаруживают пароли в открытом виде, зашифрованные или хешированные слабыми алгоритмами. Утечка базы данных RockYou (2009) раскрыла 32 миллиона паролей в открытом виде. Утечки LinkedIn (2012) и Adobe (2013) показали миллионы паролей, хешированных MD5 и 3DES без соли.

Правильное хранение паролей — это не просто «применить хеш». Это целая дисциплина с чёткими правилами: использование соли, медленных хеш-функций (KDF), правильных параметров сложности. В этой статье разберём все аспекты: от атак на хеши паролей до современных рекомендаций по использованию Argon2id.

---

## 1. Почему нельзя хранить пароли в открытом виде

Это кажется очевидным, но объяснение важно:

1. **Атака на базу данных:** SQL-инъекция, backup дамп, insecure storage → злоумышленник читает все пароли напрямую
2. **Привилегированные пользователи:** администратор БД видит все пароли
3. **Повторное использование паролей:** 65% пользователей используют один пароль на нескольких сайтах → утечка с одного сайта компрометирует другие

---

## 2. Почему MD5/SHA-256 недостаточно

### Атака с таблицей радуги (Rainbow Table)

Rainbow table — это предвычисленная таблица хешей паролей:

```python
# Злоумышленник заранее вычисляет:
rainbow_table = {
    "5f4dcc3b5aa765d61d8327deb882cf99": "password",
    "21232f297a57a5a743894a0e4a801fc3": "admin",
    "e10adc3949ba59abbe56e057f20f883e": "123456",
    # ... миллиарды строк
}

# Взлом: просто поиск в таблице!
stolen_hash = "5f4dcc3b5aa765d61d8327deb882cf99"
if stolen_hash in rainbow_table:
    print(f"Пароль: {rainbow_table[stolen_hash]}")  # "password"
```

Без соли все одинаковые пароли имеют одинаковые хеши → одна запись в rainbow table ломает тысячи аккаунтов.

### Атака перебором (Dictionary/Brute Force)

Современные GPU могут вычислять миллиарды MD5/SHA256 хешей в секунду:

| Алгоритм  | Скорость (RTX 4090) | Пространство 8-символьных пар.|
|-----------|--------------------|-----------------------------|
| MD5       | ~164 Гхеш/с        | Перебор за секунды-минуты    |
| SHA-1     | ~62 Гхеш/с         | Перебор за минуты            |
| SHA-256   | ~22 Гхеш/с         | Перебор за часы              |
| bcrypt(12)| ~56 Кхеш/с         | Десятки лет                  |
| Argon2id  | ~10 Кхеш/с         | Сотни лет                    |

---

## 3. Соль (Salt)

### Что такое соль

Соль — это случайное значение, уникальное для каждого пользователя, добавляемое к паролю перед хешированием:

```
hash = H(salt || password)
```

Соль:
- **Не секретна** — хранится рядом с хешем в открытом виде
- **Случайна** — минимум 16 байт (128 бит) криптографически случайного материала
- **Уникальна** — разная для каждого пользователя и при каждой смене пароля

### Что даёт соль

1. **Уничтожает rainbow tables:** злоумышленник не может использовать предвычисленные таблицы, так как соль уникальна
2. **Изолирует пользователей:** два пользователя с одинаковым паролем имеют разные хеши
3. **Требует индивидуального перебора:** атакующий должен атаковать каждого пользователя отдельно

```python
import hashlib
import os
import hmac

# НЕПРАВИЛЬНО: без соли
def bad_hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Все "password" → одинаковый хеш
print(bad_hash_password("password"))  # 5f4dcc3b5...
print(bad_hash_password("password"))  # 5f4dcc3b5... (то же самое!)

# НЕМНОГО ЛУЧШЕ: с солью, но SHA-256 всё ещё слишком быстрый
def mediocre_hash_password(password: str) -> tuple[str, str]:
    salt = os.urandom(16).hex()  # Уникальная соль
    hash_val = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt, hash_val

salt1, hash1 = mediocre_hash_password("password")
salt2, hash2 = mediocre_hash_password("password")
print(f"Разные хеши одного пароля: {hash1 != hash2}")  # True
# Но SHA-256 слишком быстрый — GPU может перебирать миллиарды/сек
```

---

## 4. KDF — Key Derivation Functions

KDF (функции вывода ключей) — это специально разработанные **медленные** хеш-функции для паролей. Их медленность — фича, а не баг: сделать перебор нереальным.

### bcrypt

bcrypt разработан Нильсом Провосом (Niels Provos) и Дэвидом Мазьером в 1999 году. Основан на алгоритме Blowfish с дорогостоящей инициализацией ключа.

**Work factor** (cost): параметр `rounds` = 2^cost итераций. При cost=12: 2^12 = 4096 итераций, время ~250 мс на современном CPU.

```python
# pip install bcrypt
import bcrypt
import time

password = "my_secure_password_123!"

# Хеширование (ПРАВИЛЬНО!)
start = time.time()
salt = bcrypt.gensalt(rounds=12)  # cost factor 12
hashed = bcrypt.hashpw(password.encode(), salt)
elapsed = time.time() - start

print(f"bcrypt hash: {hashed.decode()}")
# $2b$12$<22 chars salt><31 chars hash>
print(f"Время хеширования: {elapsed*1000:.0f} мс")  # ~250 мс

# Верификация
is_valid = bcrypt.checkpw(password.encode(), hashed)
print(f"Пароль верен: {is_valid}")

# Неверный пароль
is_invalid = bcrypt.checkpw(b"wrong_password", hashed)
print(f"Неверный пароль: {is_invalid}")  # False

# Анатомия bcrypt хеша: $2b$12$EeX6hSwXhTy3s3NzP2KJxuYX3U6MeSBJFNEJkGbQkDvVusFyq8XmW
# $2b$ = версия алгоритма
# 12$ = cost factor
# Следующие 22 символа = соль (base64)
# Последние 31 символ = хеш
```

**Ограничения bcrypt:**
- Максимальная длина пароля: 72 байта (обрезает более длинные)
- Нет memory-hardness (только CPU-bound)
- На GPU значительно быстрее, чем на CPU (хотя намного медленнее, чем SHA-256)

### scrypt

scrypt разработан Колином Персивалом (Colin Percival) в 2009 году. Ключевое отличие от bcrypt — **memory-hardness**: требует большого количества памяти, что делает атаку на GPU/ASIC значительно дороже.

**Параметры scrypt:**
- `N` — CPU/memory cost (power of 2, обычно 2^14 = 16384 или 2^15)
- `r` — block size (обычно 8)
- `p` — parallelization factor (обычно 1)
- Требуемая память = 128 × N × r байт

При N=2^15, r=8: ~32 МБ памяти на одно вычисление.

```python
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
import os

def scrypt_hash_password(password: str) -> bytes:
    """Хеширование пароля с scrypt"""
    salt = os.urandom(16)
    kdf = Scrypt(
        salt=salt,
        length=32,      # Длина выходного ключа
        n=2**15,        # CPU/memory cost (32 МБ)
        r=8,            # Block size
        p=1             # Parallelization
    )
    key = kdf.derive(password.encode())
    
    # Сохраняем соль вместе с хешем
    return salt + key  # 16 + 32 = 48 байт

def scrypt_verify_password(password: str, stored: bytes) -> bool:
    """Верификация пароля"""
    salt = stored[:16]
    stored_key = stored[16:]
    
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    try:
        kdf.verify(password.encode(), stored_key)
        return True
    except Exception:
        return False

# Пример
hashed = scrypt_hash_password("my_password")
print(f"Верификация: {scrypt_verify_password('my_password', hashed)}")
print(f"Неверный: {scrypt_verify_password('wrong', hashed)}")
```

### Argon2 — победитель PHC

Argon2 победил в Password Hashing Competition (PHC) в 2015 году. Разработан Алексом Бирюковым (Alex Biryukov), Даниелем Дину (Daniel Dinu) и Дмитрием Ховратовичем (Dmitry Khovratovich).

**Три варианта:**
- **Argon2d** — устойчив к атакам на GPU (использует data-dependent memory access)
- **Argon2i** — устойчив к side-channel атакам (data-independent memory access)
- **Argon2id** — гибрид: первый проход Argon2i, остальные Argon2d. **Рекомендован для паролей.**

**Параметры Argon2:**
- `t` — time_cost (число итераций)
- `m` — memory_cost (в кибибайтах, например 65536 = 64 МБ)
- `p` — parallelism (число потоков)
- Рекомендация OWASP: memory ≥ 19 МБ, time ≥ 2, parallelism ≥ 1

```python
# pip install argon2-cffi
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

# Создание хешера с рекомендованными параметрами
ph = PasswordHasher(
    time_cost=2,          # 2 итерации
    memory_cost=65536,    # 64 МБ памяти
    parallelism=2,        # 2 потока
    hash_len=32,          # 32 байта хеша
    salt_len=16           # 16 байт соли
)

# Хеширование
password = "SuperSecretPassword123!"
hashed = ph.hash(password)
print(f"Argon2id хеш: {hashed[:50]}...")
# $argon2id$v=19$m=65536,t=2,p=2$<base64 соль>$<base64 хеш>

# Верификация
try:
    ph.verify(hashed, password)
    print("Пароль верен!")
except VerifyMismatchError:
    print("Неверный пароль!")

# Проверка, нужно ли перехешировать (параметры устарели)
if ph.check_needs_rehash(hashed):
    print("Рекомендуется перехешировать с новыми параметрами")

# Нижегородная реализация с кастомными параметрами
from argon2.low_level import hash_secret, Type, verify_secret

salt = os.urandom(16)
hash_bytes = hash_secret(
    secret=password.encode(),
    salt=salt,
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    type=Type.ID  # Argon2id
)
print(f"Low-level Argon2id: {hash_bytes.hex()[:32]}...")
```

### PBKDF2 — для FIPS окружений

PBKDF2 (RFC 2898) — стандарт NIST/FIPS, одобренный для использования в государственных системах. Медленнее bcrypt/scrypt/Argon2 при тех же ресурсах, но соответствует требованиям FIPS.

```python
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import os

def pbkdf2_hash(password: str, iterations: int = 600_000) -> bytes:
    """PBKDF2-HMAC-SHA256"""
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations  # OWASP рекомендует 600,000 для SHA-256
    )
    key = kdf.derive(password.encode())
    return salt + key

def pbkdf2_verify(password: str, stored: bytes, iterations: int = 600_000) -> bool:
    salt = stored[:16]
    stored_key = stored[16:]
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations
    )
    try:
        kdf.verify(password.encode(), stored_key)
        return True
    except Exception:
        return False
```

---

## 5. Сравнение алгоритмов

| Алгоритм      | Memory-hard | GPU-resistant | FIPS-approved | Рекомендован OWASP |
|---------------|------------|--------------|---------------|-------------------|
| MD5/SHA-256   | Нет        | Нет          | Нет           | Нет (не для паролей)|
| bcrypt        | Нет        | Частично     | Нет           | Да (legacy)       |
| scrypt        | Да         | Да           | Нет           | Да                |
| Argon2id      | Да         | Да           | Нет           | Да (рекомендован) |
| PBKDF2-SHA512 | Нет        | Нет          | Да            | Да (FIPS)         |

---

## 6. Как хранить пароли в production

### Структура хранилища

```python
import json
import os
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

class UserPasswordStore:
    """Пример безопасного хранилища паролей"""
    
    def __init__(self):
        self.ph = PasswordHasher(
            time_cost=2,
            memory_cost=65536,
            parallelism=2
        )
        self.db = {}  # В реальности — база данных
    
    def register_user(self, user_id: str, password: str) -> None:
        """Регистрация пользователя"""
        # Валидация силы пароля
        self._validate_password_strength(password)
        
        # Хеширование с солью (соль встроена в Argon2 хеш)
        password_hash = self.ph.hash(password)
        
        self.db[user_id] = {
            "password_hash": password_hash,
            # НЕ храним открытый пароль
            # НЕ храним промежуточные хеши
        }
    
    def verify_login(self, user_id: str, password: str) -> bool:
        """Проверка пароля при входе"""
        if user_id not in self.db:
            # Не раскрываем существование пользователя
            # Выполняем фиктивное хеширование для защиты от timing attack
            self.ph.hash("dummy_password_for_timing_safety")
            return False
        
        stored_hash = self.db[user_id]["password_hash"]
        
        try:
            self.ph.verify(stored_hash, password)
            
            # Обновление хеша если параметры изменились
            if self.ph.check_needs_rehash(stored_hash):
                self.db[user_id]["password_hash"] = self.ph.hash(password)
                print(f"Хеш обновлён для пользователя {user_id}")
            
            return True
        except VerifyMismatchError:
            return False
    
    def _validate_password_strength(self, password: str) -> None:
        """Минимальные требования к паролю"""
        if len(password) < 12:
            raise ValueError("Пароль должен быть минимум 12 символов")
        # В реальности: проверка на common passwords (HaveIBeenPwned API)
    
    def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> bool:
        """Смена пароля с верификацией старого"""
        if not self.verify_login(user_id, old_password):
            return False
        
        self._validate_password_strength(new_password)
        
        # Новый хеш с новой случайной солью (автоматически в Argon2)
        self.db[user_id]["password_hash"] = self.ph.hash(new_password)
        return True

# Демонстрация
store = UserPasswordStore()

store.register_user("alice", "my_secure_password_123!")
print(f"Вход с верным паролем: {store.verify_login('alice', 'my_secure_password_123!')}")
print(f"Вход с неверным паролем: {store.verify_login('alice', 'wrong_password')}")
print(f"Несуществующий юзер: {store.verify_login('bob', 'any_password')}")
```

### Have I Been Pwned API

```python
import hashlib
import requests

def check_password_pwned(password: str) -> int:
    """Проверить пароль против базы утёкших паролей HaveIBeenPwned"""
    sha1_hash = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix = sha1_hash[:5]
    suffix = sha1_hash[5:]
    
    # k-anonymity модель: отправляем только первые 5 символов хеша
    response = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}")
    
    for line in response.text.splitlines():
        hash_suffix, count = line.split(":")
        if hash_suffix == suffix:
            return int(count)
    
    return 0

# Использование (требует интернет)
# count = check_password_pwned("password123")
# if count > 0:
#     print(f"Пароль встречался в утечках {count} раз!")
# else:
#     print("Пароль не найден в известных утечках")
```

---

## 7. Timing attacks на верификацию паролей

При верификации нельзя использовать обычное сравнение строк:

```python
# НЕПРАВИЛЬНО: время выполнения зависит от количества совпавших байт
def bad_verify(stored_hash: str, provided_hash: str) -> bool:
    return stored_hash == provided_hash  # Timing attack!

# ПРАВИЛЬНО: постоянное время сравнения
import hmac

def good_verify(stored_hash: str, provided_hash: str) -> bool:
    return hmac.compare_digest(stored_hash, provided_hash)
```

Argon2 и bcrypt библиотеки реализуют constant-time comparison внутри — дополнительного сравнения не нужно при использовании их встроенных функций верификации.

---

## 8. Миграция с небезопасных хешей

Если у вас в базе MD5/SHA1 хеши без соли:

```python
# Стратегия постепенной миграции
class LegacyPasswordMigration:
    def __init__(self):
        self.ph = PasswordHasher()
    
    def verify_and_migrate(
        self, user_id: str, password: str,
        legacy_hash: str, new_hash: str | None
    ) -> tuple[bool, str | None]:
        """
        Возвращает (is_valid, new_hash_if_migrated)
        """
        # Если новый хеш уже есть — проверяем его
        if new_hash:
            try:
                self.ph.verify(new_hash, password)
                return True, None
            except Exception:
                return False, None
        
        # Проверяем старый MD5 хеш (плохой!)
        import hashlib
        old_computed = hashlib.md5(password.encode()).hexdigest()
        
        if hmac.compare_digest(old_computed, legacy_hash):
            # Пароль верен — создаём новый Argon2id хеш
            new_argon2_hash = self.ph.hash(password)
            return True, new_argon2_hash  # Сохранить в БД
        
        return False, None
```

---

## Заключение

Правильное хранение паролей защищает пользователей в случае неизбежной утечки базы данных.

Правила:
1. **Никогда не храните пароли в открытом виде** — ни в БД, ни в логах, ни в конфигах
2. **Используйте Argon2id** — это современный стандарт 2024 года. Параметры OWASP: time=2, memory=64MB
3. **Соль генерируется автоматически** в Argon2/bcrypt — не управляйте ею вручную
4. **Для FIPS-окружений** используйте PBKDF2-SHA256 с 600,000+ итераций
5. **Timing-safe сравнение** обязательно при верификации
6. **Проверяйте утёкшие пароли** через HaveIBeenPwned API
7. **Планируйте миграцию** — параметры нужно увеличивать каждые 2-3 года

---

## Литература и источники

1. OWASP. *Password Storage Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
2. RFC 2898. (2000). *PKCS #5: Password-Based Cryptography Specification Version 2.0*. IETF. https://www.rfc-editor.org/rfc/rfc2898
3. Biryukov, A., Dinu, D., Khovratovich, D. (2015). *Argon2: the memory-hard function for password hashing and other applications*. https://www.password-hashing.net/argon2-specs.pdf
4. Percival, C. (2009). *Stronger Key Derivation Via Sequential Memory-Hard Functions (scrypt)*. https://www.tarsnap.com/scrypt/scrypt.pdf
5. Provos, N., Mazières, D. (1999). *A Future-Adaptable Password Scheme (bcrypt)*. USENIX Annual Technical Conference. https://www.usenix.org/legacy/events/usenix99/provos/provos.pdf
6. Hunt, T. *Have I Been Pwned (HIBP)*. https://haveibeenpwned.com/
7. RFC 5869. (2010). *HMAC-based Key Derivation Function (HKDF)*. IETF. https://www.rfc-editor.org/rfc/rfc5869
8. NIST SP 800-63B. *Digital Identity Guidelines: Authentication and Lifecycle Management*. https://pages.nist.gov/800-63-3/sp800-63b.html
9. Wikipedia: Argon2. https://en.wikipedia.org/wiki/Argon2
10. Wikipedia: bcrypt. https://en.wikipedia.org/wiki/Bcrypt
