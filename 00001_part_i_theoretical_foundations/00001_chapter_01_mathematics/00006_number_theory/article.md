# Теория чисел: модулярная арифметика, простые числа и RSA

## Введение

Теория чисел — раздел математики, изучающий свойства целых чисел. Долгое время она считалась «чистой математикой» без практических приложений. Всё изменилось с появлением компьютерной криптографии: алгоритм RSA, шифрование в TLS, цифровые подписи — всё это прямые приложения теории чисел. Без понимания модулярной арифметики и свойств простых чисел невозможно осмысленно работать с криптографическими примитивами.

---

## 1. Делимость и НОД

Целое число a делится на b (b | a), если существует целое c такое, что a = b × c.

### Алгоритм Евклида

НОД(a, b) — наибольший общий делитель, основан на свойстве: НОД(a, b) = НОД(b, a mod b).

```python
def gcd(a, b):
    while b:
        a, b = b, a % b
    return a

# Расширенный алгоритм Евклида: gcd + коэффициенты Безу
def extended_gcd(a, b):
    """Находит x, y такие что a*x + b*y = gcd(a,b)"""
    if b == 0:
        return a, 1, 0
    g, x, y = extended_gcd(b, a % b)
    return g, y, x - (a // b) * y

g, x, y = extended_gcd(35, 15)
print(f"gcd(35, 15) = {g}")       # 5
print(f"35*{x} + 15*{y} = {g}")  # 35*1 + 15*(-2) = 5
print(35 * x + 15 * y)           # 5

print(gcd(48, 18))  # 6
print(gcd(100, 75)) # 25
```

Алгоритм Евклида имеет сложность O(log(min(a, b))) — очень быстро. Расширенный алгоритм критически важен для вычисления мультипликативного обратного в модулярной арифметике.

### НОК (наименьшее общее кратное)

```python
def lcm(a, b):
    return abs(a * b) // gcd(a, b)

print(lcm(4, 6))  # 12
print(lcm(21, 14))  # 42
```

---

## 2. Модулярная арифметика

В модулярной арифметике все вычисления выполняются «по модулю» n. Два числа называются сравнимыми по модулю n, если их разность делится на n:

```
a ≡ b (mod n) ⟺ n | (a - b)
```

### Базовые операции

```python
n = 17

# Сложение: (a + b) mod n
print((13 + 9) % n)    # 5

# Умножение: (a * b) mod n
print((13 * 9) % n)    # (117) mod 17 = 15

# Отрицание: -a mod n = n - (a mod n)
print((-13) % n)       # 4 (в Python % всегда неотрицателен)

# Возведение в степень: быстрое (log n итераций)
print(pow(3, 100, n))  # 3^100 mod 17 — мгновенно!
```

Встроенная функция `pow(base, exp, mod)` в Python реализует быстрое возведение в степень по модулю — это незаменимо в криптографии.

### Мультипликативное обратное

Обратный элемент a⁻¹ по модулю n — такое число, что a × a⁻¹ ≡ 1 (mod n).

Он существует тогда и только тогда, когда gcd(a, n) = 1 (a и n взаимно просты).

```python
def mod_inverse(a, n):
    """Мультипликативное обратное a по модулю n через расширенный алгоритм Евклида"""
    g, x, _ = extended_gcd(a % n, n)
    if g != 1:
        raise ValueError("Обратного не существует (не взаимно просты)")
    return x % n

print(mod_inverse(3, 7))    # 5, так как 3*5 = 15 ≡ 1 (mod 7)
print(mod_inverse(17, 3120)) # используется в RSA
```

---

## 3. Простые числа

Натуральное число p > 1 называется простым, если его единственные делители — 1 и p.

### Теорема о бесконечности простых чисел (Евклид)

Простых чисел бесконечно много.

**Доказательство**: Предположим, что p₁, p₂, ..., pₙ — все простые числа. Рассмотрим N = p₁ × p₂ × ... × pₙ + 1. Число N не делится ни на одно из pᵢ (даёт остаток 1). Следовательно, у N есть простой делитель, не входящий в наш список — противоречие. ∎

### Решето Эратосфена

```python
def sieve_of_eratosthenes(limit):
    """Находит все простые числа до limit за O(n log log n)"""
    is_prime = bytearray([1]) * (limit + 1)
    is_prime[0] = is_prime[1] = 0
    
    for i in range(2, int(limit**0.5) + 1):
        if is_prime[i]:
            # Отмечаем все кратные i*i, i*(i+1), ...
            is_prime[i*i::i] = bytearray(len(is_prime[i*i::i]))
    
    return [i for i, prime in enumerate(is_prime) if prime]

primes = sieve_of_eratosthenes(100)
print(primes)
# [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
#  53, 59, 61, 67, 71, 73, 79, 83, 89, 97]
```

### Теорема о распределении простых чисел

Количество простых чисел до n: π(n) ≈ n / ln(n) (при больших n).

Практическое следствие: среди 1024-битных чисел примерно каждое ln(2^1024) ≈ 710-е число — простое. Это делает генерацию больших простых чисел для RSA практичной задачей.

### Тест Миллера–Рабина

Детерминированная проверка простоты больших чисел — дорогостоящая. На практике используют вероятностный тест Миллера–Рабина:

```python
import random

def miller_rabin(n, k=10):
    """
    Вероятностный тест простоты.
    Возвращает False (составное) или True (вероятно простое).
    Вероятность ошибки: ≤ (1/4)^k
    """
    if n < 2:
        return False
    if n == 2 or n == 3:
        return True
    if n % 2 == 0:
        return False
    
    # Представляем n-1 как 2^r * d
    r, d = 0, n - 1
    while d % 2 == 0:
        r += 1
        d //= 2
    
    for _ in range(k):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        
        if x == 1 or x == n - 1:
            continue
        
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False  # Составное
    
    return True  # Вероятно простое

# Тестирование
test_numbers = [2, 3, 17, 97, 100, 1009, 1000003]
for n in test_numbers:
    print(f"{n}: {'простое' if miller_rabin(n) else 'составное'}")
```

При k = 40 итерациях вероятность ложноположительного результата менее 2^(-80) — достаточно для криптографических целей.

---

## 4. Малая теорема Ферма и теорема Эйлера

### Малая теорема Ферма

Если p — простое, a не делится на p, то:

```
aᵖ⁻¹ ≡ 1 (mod p)
```

```python
p = 17
for a in range(1, p):
    assert pow(a, p - 1, p) == 1, f"Ошибка для a={a}"
print("Малая теорема Ферма подтверждена для p=17")
```

Это основа тестов простоты (тест Ферма — более слабая версия) и вычисления обратных элементов: a⁻¹ ≡ a^(p-2) (mod p).

### Функция Эйлера

φ(n) (функция Эйлера, totient function) — количество чисел от 1 до n, взаимно простых с n.

```
φ(p) = p - 1          для простого p
φ(pᵏ) = pᵏ - pᵏ⁻¹   для простой степени
φ(mn) = φ(m)×φ(n)    если gcd(m, n) = 1
```

**Теорема Эйлера**: если gcd(a, n) = 1, то a^φ(n) ≡ 1 (mod n).

```python
def euler_totient(n):
    result = n
    p = 2
    while p * p <= n:
        if n % p == 0:
            while n % p == 0:
                n //= p
            result -= result // p
        p += 1
    if n > 1:
        result -= result // n
    return result

print(euler_totient(12))   # 4 (1, 5, 7, 11)
print(euler_totient(17))   # 16 (все числа 1..16)
print(euler_totient(3*5))  # 8 = φ(3)×φ(5) = 2×4
```

---

## 5. Китайская теорема об остатках

Если m₁, m₂, ..., mₙ попарно взаимно просты, то система:
```
x ≡ a₁ (mod m₁)
x ≡ a₂ (mod m₂)
...
x ≡ aₙ (mod mₙ)
```

имеет единственное решение по модулю M = m₁ × m₂ × ... × mₙ.

```python
def crt(remainders, moduli):
    """Китайская теорема об остатках"""
    M = 1
    for m in moduli:
        M *= m
    
    x = 0
    for a, m in zip(remainders, moduli):
        Mi = M // m
        yi = mod_inverse(Mi, m)
        x += a * Mi * yi
    
    return x % M

# x ≡ 2 (mod 3), x ≡ 3 (mod 5), x ≡ 2 (mod 7)
solution = crt([2, 3, 2], [3, 5, 7])
print(solution)  # 23
print(23 % 3, 23 % 5, 23 % 7)  # 2 3 2 ✓
```

КТО используется в оптимизации RSA: вычисление с маленькими ключами p и q быстрее, чем с большим n = p×q.

---

## 6. Алгоритм RSA

RSA (Rivest–Shamir–Adleman, 1977) — асимметричная криптосистема, безопасность которой основана на вычислительной трудности факторизации больших чисел.

### Генерация ключей

```python
def generate_rsa_keypair(bits=512):
    """
    Упрощённая демонстрация RSA.
    Реальный RSA использует 2048+ бит и padding OAEP.
    """
    # 1. Выбираем два больших простых числа p и q
    def generate_prime(bits):
        while True:
            p = random.getrandbits(bits) | (1 << (bits - 1)) | 1  # нечётное
            if miller_rabin(p, k=20):
                return p
    
    p = generate_prime(bits // 2)
    q = generate_prime(bits // 2)
    
    # 2. Вычисляем n = p*q и φ(n) = (p-1)*(q-1)
    n = p * q
    phi_n = (p - 1) * (q - 1)
    
    # 3. Выбираем открытую экспоненту e (обычно 65537)
    e = 65537
    assert gcd(e, phi_n) == 1
    
    # 4. Вычисляем секретную экспоненту d: e*d ≡ 1 (mod φ(n))
    d = mod_inverse(e, phi_n)
    
    public_key = (n, e)
    private_key = (n, d)
    return public_key, private_key, p, q

def rsa_encrypt(message, public_key):
    n, e = public_key
    return pow(message, e, n)

def rsa_decrypt(ciphertext, private_key):
    n, d = private_key
    return pow(ciphertext, d, n)

# Демонстрация (с маленькими числами для наглядности)
# В реальности нужно 2048+ бит
pub, priv, p, q = generate_rsa_keypair(bits=128)
n, e = pub
n2, d = priv

message = 42
ciphertext = rsa_encrypt(message, pub)
decrypted = rsa_decrypt(ciphertext, priv)
print(f"Сообщение: {message}")
print(f"Зашифровано: {ciphertext}")
print(f"Расшифровано: {decrypted}")
print(f"Корректно: {message == decrypted}")
```

### Математика RSA

**Шифрование**: c = m^e mod n  
**Расшифровка**: m = c^d mod n

Корректность: c^d = (m^e)^d = m^(ed) ≡ m (mod n), потому что ed ≡ 1 (mod φ(n)), а по теореме Эйлера m^φ(n) ≡ 1 (mod n).

**Безопасность**: зная n и e, найти d практически невозможно без знания φ(n), а φ(n) нельзя вычислить без факторизации n. Лучшие алгоритмы факторизации (GNFS) требуют субэкспоненциального времени.

---

## 7. Дискретный логарифм

Дискретный логарифм — задача нахождения x в уравнении:

```
gˣ ≡ h (mod p)
```

при известных g, h, p. Вычислительно сложна (лучшие алгоритмы — субэкспоненциальные), на этом основана безопасность Диффи–Хеллмана и ECDSA.

```python
# Наивный алгоритм (только для учебных примеров)
def discrete_log_naive(g, h, p):
    """Находит x: g^x ≡ h (mod p)"""
    power = 1
    for x in range(p):
        if power == h:
            return x
        power = (power * g) % p
    return None  # не найден

# Baby-step Giant-step (за O(√p) шагов)
def discrete_log_bsgs(g, h, p):
    """Алгоритм «большой шаг — маленький шаг»"""
    m = int(p**0.5) + 1
    
    # Baby steps: вычисляем g^j для j = 0..m-1
    table = {}
    gj = 1
    for j in range(m):
        table[gj] = j
        gj = (gj * g) % p
    
    # Giant steps: g^(-m) mod p
    g_inv_m = pow(g, p - 1 - m, p)
    
    gamma = h
    for i in range(m):
        if gamma in table:
            return i * m + table[gamma]
        gamma = (gamma * g_inv_m) % p
    
    return None

p, g = 23, 5
x = 6
h = pow(g, x, p)  # 5^6 mod 23 = 8
print(f"g^{x} mod {p} = {h}")
print(f"BSGS нашёл x = {discrete_log_bsgs(g, h, p)}")  # 6
```

---

## 8. Элементарные хеш-функции и теория чисел

Полиномиальный хеш строки использует теорию чисел:

```python
def polynomial_hash(s, base=31, mod=10**9 + 7):
    """
    Хеш строки как числа в позиционной системе счисления с основанием base,
    по модулю большого простого числа mod.
    """
    h = 0
    power = 1
    for c in s:
        h = (h + ord(c) * power) % mod
        power = (power * base) % mod
    return h

# Правило хорошего модуля: большое простое число
# Большое — меньше коллизий
# Простое — обеспечивает равномерность распределения

print(polynomial_hash("hello"))
print(polynomial_hash("world"))
print(polynomial_hash("hello") == polynomial_hash("world"))  # False (вероятно)
```

Выбор mod как большого простого числа (10^9 + 7, 10^9 + 9, 2^61 - 1) — прямое применение теории чисел.

---

## Заключение

Теория чисел из «чистой математики» превратилась в краеугольный камень информационной безопасности:

- **RSA**: безопасность = сложность факторизации
- **Diffie–Hellman**: безопасность = сложность дискретного логарифма  
- **Хеш-функции**: распределение по простым модулям
- **Хеш-таблицы**: выбор размера как простого числа снижает кластеризацию
- **Тест Миллера–Рабина**: практически используется в криптографических библиотеках

Каждый вызов `pow(a, b, n)` в Python — это быстрое возведение в степень по модулю с лежащей в основе теоремой Ферма.

---

## Литература и источники

1. Hardy, G. H., & Wright, E. M. (2008). *An Introduction to the Theory of Numbers* (6th ed.). Oxford University Press. — Классика теории чисел.

2. Rivest, R. L., Shamir, A., & Adleman, L. (1978). A method for obtaining digital signatures and public-key cryptosystems. *Communications of the ACM*, 21(2), 120–126. — Оригинальная статья RSA.

3. Shoup, V. (2008). *A Computational Introduction to Number Theory and Algebra* (2nd ed.). Cambridge University Press. Доступно онлайн: https://www.shoup.net/ntb/

4. Hoffstein, J., Pipher, J., & Silverman, J. H. (2008). *An Introduction to Mathematical Cryptography*. Springer. — Теория чисел в криптографии.

5. Menezes, A. J., van Oorschot, P. C., & Vanstone, S. A. (1996). *Handbook of Applied Cryptography*. CRC Press. Доступно онлайн: https://cacr.uwaterloo.ca/hac/

6. Miller, G. L. (1976). Riemann's hypothesis and tests for primality. *Journal of Computer and System Sciences*, 13(3), 300–317. — Тест простоты.

7. Rabin, M. O. (1980). Probabilistic algorithm for testing primality. *Journal of Number Theory*, 12(1), 128–138. — Вероятностный тест Миллера–Рабина.
