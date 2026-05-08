# Случайность: PRNG, CSPRNG и почему rand() нельзя в крипте

## Введение

Случайность — один из фундаментальных компонентов безопасности. Ключи шифрования, nonces, соли, токены сессий, CSRF-токены — всё это требует непредсказуемых случайных чисел. Использование неподходящего генератора случайных чисел может сделать всю криптографию бессмысленной: если атакующий может предсказать ваш «случайный» ключ — шифрование бесполезно.

Существует принципиальная разница между **PRNG** (Pseudo-Random Number Generator) — детерминированным алгоритмом, имитирующим случайность, и **CSPRNG** (Cryptographically Secure PRNG) — генератором, случайность которого вычислительно неотличима от истинно случайного. В этой статье мы разберём оба класса, рассмотрим аппаратные генераторы и главные мифы о `/dev/random` в Linux.

---

## 1. PRNG — псевдослучайные генераторы

PRNG — это детерминированный алгоритм, порождающий последовательность чисел, которая выглядит случайной, но полностью определяется начальным значением (seed).

### Свойства PRNG

1. **Детерминированность:** зная seed, можно воспроизвести всю последовательность
2. **Периодичность:** через некоторый (большой) период последовательность повторяется
3. **Статистические свойства:** хорошие PRNG проходят статистические тесты (NIST SP 800-22)
4. **Предсказуемость:** зная достаточно выходных значений, можно определить внутреннее состояние и предсказать будущие

### Linear Congruential Generator (LCG)

Простейший PRNG — основа большинства реализаций `rand()` в C:

```
X[n+1] = (a × X[n] + c) mod m
```

```python
class LCG:
    """Linear Congruential Generator — простейший PRNG"""
    
    def __init__(self, seed: int = 42):
        # Параметры из glibc (C stdlib rand())
        self.a = 1103515245
        self.c = 12345
        self.m = 2**31  # 2^31
        self.state = seed
    
    def rand(self) -> int:
        self.state = (self.a * self.state + self.c) % self.m
        return self.state
    
    def rand_float(self) -> float:
        return self.rand() / self.m

# Демонстрация предсказуемости
rng = LCG(seed=42)
first_10 = [rng.rand() for _ in range(10)]
print(f"Первые 10 значений: {first_10[:5]}...")

# С тем же seed — тот же результат!
rng2 = LCG(seed=42)
same_10 = [rng2.rand() for _ in range(10)]
print(f"То же самое: {first_10 == same_10}")  # True

# Атака: предсказание следующего числа
# Зная X[n], легко найти X[n+1] = (a * X[n] + c) mod m
```

### Mersenne Twister (MT19937)

Python использует **Mersenne Twister** в модуле `random`. Это более качественный PRNG:
- Период: 2^19937 - 1 (огромный)
- Проходит статистические тесты
- Скорость: очень высокая

```python
import random

# Python random — Mersenne Twister
random.seed(42)
values = [random.random() for _ in range(5)]
print(f"random.random(): {values}")

# Предсказуемость: тот же seed → тот же результат
random.seed(42)
same_values = [random.random() for _ in range(5)]
print(f"Совпадают: {values == same_values}")  # True!

# КРИТИЧНО: наблюдая 624 последовательных числа, можно
# полностью восстановить внутреннее состояние MT
# и предсказывать все последующие значения!
```

### Атака на Mersenne Twister

MT имеет состояние 624 × 32-битных слов. После наблюдения 624 последовательных выходов можно восстановить полное состояние:

```python
# Демонстрация концепции (не полная атака)
# Если злоумышленник видит 624 последовательных random.getrandbits(32)
# он может восстановить состояние и предсказать все будущие значения

# Реальный пример: PHP rand() с известным seed (timestamp)
# Злоумышленник знает время создания токена сброса пароля
# → перебирает ~1000 possible seed values → предсказывает токен!
```

---

## 2. CSPRNG — криптографически стойкие генераторы

CSPRNG (Cryptographically Secure Pseudo-Random Number Generator) должен обладать двумя дополнительными свойствами:

1. **Next-bit unpredictability:** зная любое количество предыдущих битов, вычислительно нереализуемо предсказать следующий бит с вероятностью > 50% + ε
2. **State compromise resistance:** даже зная текущее состояние, нельзя восстановить прошлые выходы (backward security)

### /dev/urandom — источник энтропии в Linux

В Linux CSPRNG реализован в ядре. Он собирает энтропию из:
- Прерываний клавиатуры и мыши
- Сетевого трафика
- Прерываний диска
- RDRAND (аппаратный RNG Intel/AMD, если доступен)
- Других источников шума

Пользовательские программы читают случайные байты через:
- `/dev/urandom` — всегда возвращает данные немедленно
- `/dev/random` — блокирует при низкой «энтропии» (старое поведение)
- `getrandom()` системный вызов (Linux 3.17+)

```python
import os

# os.urandom использует /dev/urandom (Unix) или CryptGenRandom (Windows)
random_bytes = os.urandom(32)
print(f"32 случайных байта: {random_bytes.hex()}")

# secrets модуль (Python 3.6+) — специально для криптографии
import secrets

# Случайные байты
token = secrets.token_bytes(32)
print(f"Token bytes: {token.hex()}")

# URL-safe hex token (для API ключей, сессий)
url_token = secrets.token_urlsafe(32)  # 32 байта → 43 символа base64url
print(f"URL token: {url_token}")

# Hex token
hex_token = secrets.token_hex(16)  # 16 байт → 32 hex символа
print(f"Hex token: {hex_token}")

# Случайное целое число (для OTP, PIN)
pin = secrets.randbelow(1000000)  # 0..999999
print(f"6-значный PIN: {str(pin).zfill(6)}")

# Случайный выбор (для lottery, challenge)
alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
code = ''.join(secrets.choice(alphabet) for _ in range(8))
print(f"Случайный код: {code}")
```

### Сравнение random vs secrets

```python
import random
import secrets
import time

# НИКОГДА не используйте для безопасных токенов:
bad_token = '%032x' % random.getrandbits(128)  # PRNG, предсказуем!

# ВСЕГДА используйте для безопасных токенов:
good_token = secrets.token_hex(16)  # CSPRNG, криптографически случаен

# Скорость (примерные числа)
N = 100_000

start = time.perf_counter()
for _ in range(N):
    random.random()
mt_time = time.perf_counter() - start

start = time.perf_counter()
for _ in range(N):
    os.urandom(8)
csprng_time = time.perf_counter() - start

print(f"Mersenne Twister: {mt_time*1000:.0f} мс для {N} чисел")
print(f"os.urandom: {csprng_time*1000:.0f} мс для {N} × 8 байт")
# CSPRNG медленнее, но безопасен
```

---

## 3. Алгоритмы CSPRNG

### ChaCha20-based DRBG

Большинство современных ОС используют ChaCha20 или AES-CTR как основу CSPRNG:

- **Linux (ядро 5.17+):** ChaCha20-based RNG
- **FreeBSD/macOS:** arc4random с ChaCha20
- **Windows:** BCryptGenRandom использует AES-CTR DRBG
- **OpenSSL:** CTR-DRBG (AES-256-CTR)

### HMAC-DRBG

HMAC_DRBG (NIST SP 800-90A) — детерминированный генератор на основе HMAC:

```python
# Концептуальная схема HMAC-DRBG
class HMAC_DRBG:
    """Упрощённая демонстрация HMAC-DRBG"""
    
    def __init__(self, seed: bytes):
        import hmac
        import hashlib
        self.K = bytes(32)  # Key
        self.V = bytes([1] * 32)  # Value
        self._update(seed)
    
    def _update(self, data: bytes = None):
        import hmac
        import hashlib
        
        K, V = self.K, self.V
        
        K = hmac.new(K, V + b'\x00' + (data or b''), hashlib.sha256).digest()
        V = hmac.new(K, V, hashlib.sha256).digest()
        
        if data:
            K = hmac.new(K, V + b'\x01' + data, hashlib.sha256).digest()
            V = hmac.new(K, V, hashlib.sha256).digest()
        
        self.K, self.V = K, V
    
    def generate(self, n_bytes: int) -> bytes:
        import hmac
        import hashlib
        
        result = b''
        while len(result) < n_bytes:
            self.V = hmac.new(self.K, self.V, hashlib.sha256).digest()
            result += self.V
        
        self._update()
        return result[:n_bytes]

# Реальный пример использования из cryptography
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Безопасная генерация ключа через CSPRNG
key = os.urandom(32)  # Ключ AES-256
nonce = os.urandom(12)  # GCM nonce
```

### Intel RDRAND

Intel Ivy Bridge (2012+) и AMD (2015+) имеют встроенный аппаратный RNG **RDRAND**, основанный на кремниевых шумах (thermal noise):

```python
# Проверка поддержки RDRAND
import subprocess

def has_rdrand() -> bool:
    """Проверка поддержки RDRAND"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            return 'rdrand' in f.read()
    except:
        return False

print(f"RDRAND доступен: {has_rdrand()}")

# В Python нет прямого доступа к RDRAND,
# но os.urandom на Linux использует его через ядро
```

**Контроверсия RDRAND:** Некоторые криптографы рекомендуют не доверять RDRAND единственным источником случайности из-за невозможности верифицировать аппаратную реализацию. Современные ОС **смешивают** RDRAND с другими источниками энтропии — это правильный подход.

---

## 4. /dev/random vs /dev/urandom — мифы и реальность

Это исторически запутанная тема.

### Старый миф (до Linux 5.6)

Исторически считалось:
- `/dev/random` — «настоящая» случайность, блокирует если мало энтропии
- `/dev/urandom` — быстрый, не блокирует, но «менее случайный»

Рекомендация «используйте /dev/random для ключей» была распространена, но **неправильна**.

### Современная реальность (Linux 5.17+)

После серии патчей Линуса Торвальдса и обсуждений сообщества:

- **/dev/random и /dev/urandom полностью эквивалентны** с точки зрения безопасности на полностью инициализированной системе
- `/dev/random` больше не блокирует (за исключением момента до полной инициализации при boot)
- `getrandom()` системный вызов — правильный способ запросить случайность в 2024 году

```python
# getrandom() в Python (Linux)
import ctypes

def getrandom(n_bytes: int, flags: int = 0) -> bytes:
    """Вызов getrandom() напрямую"""
    buf = ctypes.create_string_buffer(n_bytes)
    ret = ctypes.cdll.LoadLibrary("libc.so.6").getrandom(buf, n_bytes, flags)
    if ret != n_bytes:
        raise OSError(f"getrandom failed: {ret}")
    return bytes(buf)

# Флаги:
# GRND_RANDOM = 0x02  → использует /dev/random pool (блокирует если мало энтропии)
# GRND_NONBLOCK = 0x01 → не блокирует, возвращает EAGAIN если нет данных

try:
    random_data = getrandom(16)
    print(f"getrandom(16): {random_data.hex()}")
except:
    # На не-Linux системах
    random_data = os.urandom(16)
    print(f"os.urandom(16): {random_data.hex()}")
```

### Что реально использовать

| Контекст            | Правильный вызов         | Неправильно               |
|--------------------|--------------------------|--------------------------|
| Python             | `secrets.token_bytes(n)` | `random.random()`        |
| Python (raw)       | `os.urandom(n)`          | `random.getrandbits(n)`  |
| C                  | `getrandom()` или `/dev/urandom` | `rand()`, `srand(time(0))` |
| Go                 | `crypto/rand.Read()`     | `math/rand.Int()`        |
| Java               | `SecureRandom`           | `java.util.Random`       |
| JavaScript/Node.js | `crypto.randomBytes()`   | `Math.random()`          |

---

## 5. Типичные ошибки

### Слабый seed

```python
import random
import time

# НЕПРАВИЛЬНО: seed из времени — предсказуемо!
bad_seed = int(time.time())
random.seed(bad_seed)
token = random.getrandbits(128)

# Злоумышленник знает примерное время → перебирает N seed значений
# → восстанавливает токен
```

### Неправильное использование random для безопасности

```python
import random
import secrets
import string

# НЕПРАВИЛЬНО: генерация пароля через random
def bad_password_gen(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# ПРАВИЛЬНО: генерация пароля через secrets
def good_password_gen(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    return ''.join(secrets.choice(chars) for _ in range(length))

# НЕПРАВИЛЬНО: токен сессии через random
def bad_session_token() -> str:
    return '%032x' % random.getrandbits(128)

# ПРАВИЛЬНО: токен сессии через secrets
def good_session_token() -> str:
    return secrets.token_urlsafe(32)  # 256 бит, URL-safe base64

# НЕПРАВИЛЬНО: UUID4 через random (если random не сидирован CSPRNG)
# ПРАВИЛЬНО: uuid.uuid4() в Python использует os.urandom — безопасно
import uuid
secure_id = str(uuid.uuid4())
```

### Повторное использование PRNG состояния

```python
# В многопоточных приложениях разные потоки могут получать
# одинаковые "случайные" числа если разделяют состояние PRNG!

# НЕПРАВИЛЬНО: глобальный random в многопоточном коде
# Оба потока могут получить одинаковые nonces!

# ПРАВИЛЬНО: os.urandom / secrets — потокобезопасны
# Системный вызов getrandom() потокобезопасен
```

---

## 6. Entropy pool в браузере

В браузере доступен `crypto.getRandomValues()`:

```javascript
// JavaScript: CSPRNG в браузере и Node.js
const randomBytes = new Uint8Array(16);
crypto.getRandomValues(randomBytes);
console.log(Array.from(randomBytes).map(b => b.toString(16).padStart(2,'0')).join(''));

// Node.js: crypto module
const { randomBytes, randomUUID } = require('crypto');
const token = randomBytes(32).toString('hex');
const uuid = randomUUID();  // UUID4 через CSPRNG

// НЕПРАВИЛЬНО для криптографии:
const bad = Math.random();  // Не CSPRNG!
```

---

## 7. Проверка энтропии системы

```python
# Количество накопленной энтропии (историческое, в современных Linux не критично)
def get_entropy_avail() -> int:
    try:
        with open('/proc/sys/kernel/random/entropy_avail', 'r') as f:
            return int(f.read().strip())
    except FileNotFoundError:
        return -1

print(f"Доступная энтропия: {get_entropy_avail()} бит")
# В современных Linux обычно 256+ бит (pool size)

# Качественный тест: сжатие случайных байт не должно давать уменьшения
import zlib
random_data = os.urandom(10000)
compressed = zlib.compress(random_data)
ratio = len(compressed) / len(random_data)
print(f"Степень сжатия: {ratio:.3f} (< 1.0 = проблема с случайностью)")
# Ожидаемо: ~ 1.001..1.01 (не сжимается)

# Статистические тесты (простой)
def check_uniformity(data: bytes, bucket_count: int = 256) -> float:
    """Проверка равномерного распределения байт"""
    buckets = [0] * bucket_count
    for b in data:
        buckets[b] += 1
    
    expected = len(data) / bucket_count
    chi_squared = sum((c - expected)**2 / expected for c in buckets)
    
    return chi_squared  # Ожидается ~255 ± несколько сотен

chi_sq = check_uniformity(os.urandom(100000))
print(f"Chi-squared (ожидается ~255): {chi_sq:.1f}")
```

---

## Заключение

Качество случайности — критический фактор безопасности криптографических систем.

**Главные правила:**
1. **Никогда** не используйте `random`, `Math.random()`, `rand()` для криптографических целей
2. **Всегда** используйте `secrets` (Python), `crypto/rand` (Go), `SecureRandom` (Java), `crypto.getRandomValues()` (JS)
3. **/dev/urandom безопасен** для криптографии — старый миф о его «небезопасности» давно развеян
4. **Seed из времени** предсказуем — не используйте для безопасных целей
5. **os.urandom() = криптографически безопасно** в Python на всех платформах
6. **RDRAND** безопасен при использовании в комбинации с другими источниками (что делают все ОС)

---

## Литература и источники

1. NIST SP 800-90A. (2015). *Recommendation for Random Number Generation Using Deterministic Random Bit Generators*. https://csrc.nist.gov/publications/detail/sp/800-90a/rev-1/final
2. Eastlake, D., et al. RFC 4086. (2005). *Randomness Requirements for Security*. IETF. https://www.rfc-editor.org/rfc/rfc4086
3. Bernstein, D.J. (2008). *ChaCha, a variant of Salsa20*. https://cr.yp.to/chacha.html
4. Torvalds, L. (2022). *Linux kernel /dev/random patches*. https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/
5. Heninger, N., et al. (2012). *Mining Your Ps and Qs: Detection of Widespread Weak Keys in Network Devices*. USENIX Security 2012. https://factorable.net/
6. Python docs: secrets module. https://docs.python.org/3/library/secrets.html
7. Wikipedia: Cryptographically secure pseudorandom number generator. https://en.wikipedia.org/wiki/Cryptographically_secure_pseudorandom_number_generator
8. Wikipedia: Mersenne Twister. https://en.wikipedia.org/wiki/Mersenne_Twister
9. Kelsey, J., et al. (1998). *Cryptanalytic Attacks on Pseudorandom Number Generators*. Fast Software Encryption 1998.
