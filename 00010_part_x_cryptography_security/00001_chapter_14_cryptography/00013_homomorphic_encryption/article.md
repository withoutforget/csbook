# Гомоморфное шифрование — вычисления на зашифрованных данных

## Введение

Обычное шифрование защищает данные «в покое» (at rest) и «в пути» (in transit), но для обработки данные необходимо расшифровать. Это создаёт дилемму: если вы отправляете зашифрованные медицинские записи в облако для обработки — облачный провайдер должен их расшифровать. Если доверие к провайдеру ограничено — это неприемлемо.

**Гомоморфное шифрование** (Homomorphic Encryption, HE) решает эту задачу принципиально иначе: вычисления выполняются прямо на зашифрованных данных, результат расшифровывается только владельцем данных. Облачный провайдер видит только зашифрованные входы и зашифрованный результат — никакого доступа к реальным данным.

Это открывает возможности для приватного машинного обучения, приватных медицинских расчётов, блокчейн приложений и многого другого. Однако за революционные возможности приходится платить значительной вычислительной стоимостью.

---

## 1. Математическая идея

### Гомоморфизм

Математически: функция шифрования `E` является гомоморфной относительно операции `⊕`, если:

```
E(a) ⊕ E(b) = E(a + b)
```

То есть: операция над шифротекстами соответствует операции над открытыми текстами.

### Частично гомоморфные схемы (Partial HE)

Некоторые классические схемы случайно оказались гомоморфными:

**RSA (мультипликативно гомоморфен):**
```
E(m₁) × E(m₂) = m₁ᵉ × m₂ᵉ = (m₁ × m₂)ᵉ = E(m₁ × m₂) mod n
```

```python
# Демонстрация мультипликативного гомоморфизма RSA
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import rsa_crt_iqmp, rsa_crt_dmp1, rsa_crt_dmq1

def rsa_raw_encrypt(m: int, e: int, n: int) -> int:
    """RSA шифрование без padding (только для демонстрации!)"""
    return pow(m, e, n)

def rsa_raw_decrypt(c: int, d: int, n: int) -> int:
    """RSA расшифровка без padding"""
    return pow(c, d, n)

# Простые параметры для демонстрации
p, q = 61, 53
n = p * q  # 3233
phi = (p-1) * (q-1)  # 3120
e = 17
d = pow(e, -1, phi)  # 2753

m1, m2 = 7, 11
c1 = rsa_raw_encrypt(m1, e, n)
c2 = rsa_raw_encrypt(m2, e, n)

# Гомоморфное умножение
c_product = (c1 * c2) % n
decrypted_product = rsa_raw_decrypt(c_product, d, n)

print(f"m1 = {m1}, m2 = {m2}")
print(f"E(m1) × E(m2) = {c_product}")
print(f"D(E(m1) × E(m2)) = {decrypted_product}")
print(f"m1 × m2 = {m1 * m2}")
print(f"Гомоморфное умножение верно: {decrypted_product == (m1 * m2)}")
```

**Paillier (аддитивно гомоморфен):**
```
E(m₁) × E(m₂) mod n² = E(m₁ + m₂)
E(m)^k mod n² = E(k × m)
```

```python
# Схема Paillier — аддитивно гомоморфная
import math

class PaillierCryptosystem:
    """Упрощённая реализация криптосистемы Пайе"""
    
    def __init__(self, bits: int = 256):
        from sympy import randprime
        # Генерация ключей
        p = randprime(2**(bits//2-1), 2**(bits//2))
        q = randprime(2**(bits//2-1), 2**(bits//2))
        while p == q:
            q = randprime(2**(bits//2-1), 2**(bits//2))
        
        self.n = p * q
        self.n2 = self.n ** 2
        self.g = self.n + 1  # Упрощение: g = n+1
        self.lambda_ = math.lcm(p-1, q-1)
        self.mu = pow(self.lambda_, -1, self.n)
    
    def encrypt(self, m: int) -> int:
        import random
        r = random.randint(1, self.n - 1)
        while math.gcd(r, self.n) != 1:
            r = random.randint(1, self.n - 1)
        
        c = (pow(self.g, m, self.n2) * pow(r, self.n, self.n2)) % self.n2
        return c
    
    def decrypt(self, c: int) -> int:
        def L(u):
            return (u - 1) // self.n
        
        m = (L(pow(c, self.lambda_, self.n2)) * self.mu) % self.n
        return m
    
    def add(self, c1: int, c2: int) -> int:
        """Гомоморфное сложение"""
        return (c1 * c2) % self.n2
    
    def multiply_by_scalar(self, c: int, k: int) -> int:
        """Умножение зашифрованного значения на открытую константу"""
        return pow(c, k, self.n2)

# Демонстрация
paillier = PaillierCryptosystem(bits=128)  # Маленькие числа для скорости

a, b = 100, 250
ea = paillier.encrypt(a)
eb = paillier.encrypt(b)

# Гомоморфное сложение
ec = paillier.add(ea, eb)
result = paillier.decrypt(ec)
print(f"a + b = {a} + {b} = {a + b}")
print(f"Decrypt(E(a) × E(b)) = {result}")
print(f"Гомоморфное сложение верно: {result == a + b}")

# Умножение на скаляр
k = 5
ec_scaled = paillier.multiply_by_scalar(ea, k)
result_scaled = paillier.decrypt(ec_scaled)
print(f"\nk × a = {k} × {a} = {k * a}")
print(f"Decrypt(E(a)^k) = {result_scaled}")
print(f"Гомоморфное умножение на скаляр верно: {result_scaled == k * a}")

# Применение: голосование
def private_vote_counting():
    """Приватный подсчёт голосов без раскрытия индивидуальных"""
    votes = [1, 0, 1, 1, 0, 1, 0, 1]  # 1 = за, 0 = против
    
    encrypted_votes = [paillier.encrypt(v) for v in votes]
    
    # Сервер суммирует зашифрованные голоса
    total_encrypted = encrypted_votes[0]
    for ev in encrypted_votes[1:]:
        total_encrypted = paillier.add(total_encrypted, ev)
    
    # Только организатор расшифровывает итог
    total = paillier.decrypt(total_encrypted)
    print(f"\nПодсчёт голосов: {sum(votes)} 'за' из {len(votes)}")
    print(f"Гомоморфный результат: {total} 'за'")

private_vote_counting()
```

---

## 2. Полностью гомоморфное шифрование (FHE)

### История: Craig Gentry 2009

Главной проблемой до 2009 года было то, что все гомоморфные схемы поддерживали только один вид операций (сложение ИЛИ умножение), но не оба вместе. Для произвольных вычислений нужны обе операции.

Крейг Гентри (Craig Gentry) в своей диссертации 2009 года показал первую конструкцию **полностью гомоморфного шифрования** (FHE — Fully Homomorphic Encryption):
- Поддерживает как сложение, так и умножение над зашифрованными данными
- Следовательно, поддерживает произвольные вычисления (булевы схемы)

Ключевая идея — **bootstrapping**: в HE операции накапливают «шум» в шифротексте. Когда шума слишком много — расшифровка становится невозможной. Gentry показал, как «обновить» шифротекст (уменьшить шум), применив к нему операцию расшифровки гомоморфно.

### Основные схемы FHE

**BFV (Brakerski/Fan-Vercauteren):**
- Работает с целыми числами по модулю `t`
- Хорошо для точных целочисленных вычислений
- Используется в Microsoft SEAL

**BGV (Brakerski-Gentry-Vaikuntanathan):**
- Похожа на BFV, другое управление шумом
- Широко применяется в практических системах

**CKKS (Cheon-Kim-Kim-Song):**
- Работает с **приближёнными** числами с плавающей точкой
- Идеальна для ML: нейронные сети, статистика
- Потеря точности ~10⁻¹⁰ — приемлемо для ML
- Используется в HElib, OpenFHE, Microsoft SEAL

**TFHE (Fast Fully Homomorphic Encryption over the Torus):**
- Очень быстрый bootstrapping (~13 мс на ядро)
- Хорошо для булевых схем
- Используется в Concrete (Zama)

---

## 3. Математическая основа: Learning With Errors (LWE)

Безопасность большинства FHE схем основана на задаче **Learning With Errors (LWE)**, предложенной Оддом Регевым (Oded Regev) в 2005 году:

**Задача:** По матрице A, векторам b = As + e (mod q), где s — секрет, e — малый случайный «шум» — восстановить s.

Без шума: `b = As mod q` — тривиально решается линейной алгеброй.  
С шумом: задача вычислительно сложна, даже квантовые алгоритмы не дают существенного ускорения.

**RLWE (Ring LWE)** — вариант на кольцах полиномов, обеспечивающий лучшую производительность при той же безопасности.

```
Шифрование в BFV (концептуально):
c = ([q/t] × m + e + A × r, -A^T × r + e') mod q
где m = plaintext, r = random, e, e' = small error
```

---

## 4. Bootstrapping и шум

Каждая гомоморфная операция добавляет «шум» к шифротексту. Шум ограничен: если он превышает порог — расшифровка невозможна.

**Multiplicative depth** — количество умножений без bootstrapping. Например, для нейронной сети глубины 10 нужна мультипликативная глубина ~10-20.

**Bootstrapping** — «обновление» шифротекста для уменьшения шума. Это очень дорогая операция (секунды-минуты), поэтому её стараются избегать или проводить редко.

```
Схема вычислений с FHE:
[Encrypt inputs]
     ↓
[Level 5: много шума ещё позволяет]
[Level 4]
[Level 3]
[Level 2]  ← если нужно больше уровней → bootstrapping (дорого!)
[Level 1]
     ↓
[Decrypt result]
```

---

## 5. Производительность FHE в 2024

FHE по-прежнему значительно медленнее обычных вычислений:

| Операция         | Открытый текст | FHE (CKKS, CPU) | Замедление |
|-----------------|----------------|-----------------|-----------|
| Сложение float   | 1 нс           | ~1 мкс          | 1000×     |
| Умножение float  | 1 нс           | ~10 мкс         | 10000×    |
| Bootstrapping   | N/A            | ~1 сек          | —         |
| Нейронная сеть (simple) | ~10 мс | ~10 мин        | 60000×    |

На GPU и специализированных ускорителях (Intel HEXL, специализированные FPGA/ASIC):
- 10-100× ускорение по сравнению с CPU
- Это всё равно в 100-1000× медленнее обычных вычислений

Для ограниченных задач (частично гомоморфные операции) производительность значительно выше.

---

## 6. Практические применения

### Приватный ML Inference

Клиент зашифровывает данные → сервер выполняет ML inference на зашифрованных данных → возвращает зашифрованный результат → клиент расшифровывает.

```python
# Концептуальный пример приватного dot product (скалярного произведения)
# Используется в приватном ML (линейный слой нейросети)

class SimpleHEDotProduct:
    """
    Концептуальная демонстрация гомоморфного скалярного произведения
    Используя аддитивную гомоморфность Paillier
    """
    
    def __init__(self):
        self.paillier = PaillierCryptosystem(bits=256)
    
    def client_encrypt_input(self, x: list) -> list:
        """Клиент шифрует входной вектор"""
        return [self.paillier.encrypt(int(xi * 1000)) for xi in x]
        # Умножаем на 1000 для работы с целыми числами
    
    def server_compute(self, encrypted_x: list, plaintext_weights: list) -> int:
        """
        Сервер вычисляет dot product над зашифрованными данными.
        Веса модели — открытые (сервер их знает).
        Только входные данные зашифрованы.
        """
        result = self.paillier.encrypt(0)  # Зашифрованный 0
        
        for enc_xi, wi in zip(encrypted_x, plaintext_weights):
            # wi * E(xi) = E(wi * xi)  (умножение зашифрованного на скаляр)
            scaled = self.paillier.multiply_by_scalar(enc_xi, int(wi * 1000))
            # Сложение: result += wi * xi
            result = self.paillier.add(result, scaled)
        
        return result
    
    def client_decrypt_result(self, encrypted_result: int) -> float:
        """Клиент расшифровывает результат"""
        raw = self.paillier.decrypt(encrypted_result)
        return raw / (1000 * 1000)  # Убираем оба масштабирования

# Демонстрация (маленькие числа для скорости)
he_dot = SimpleHEDotProduct()

input_data = [2.5, 1.0, 3.7]      # Приватные данные пользователя
model_weights = [0.5, 2.0, -1.0]  # Веса модели (публичные)

expected = sum(x * w for x, w in zip(input_data, model_weights))
print(f"Ожидаемое dot product: {expected}")

# Клиент шифрует данные
enc_input = he_dot.client_encrypt_input(input_data)
print("Данные зашифрованы, отправлены на сервер...")

# Сервер вычисляет на зашифрованных данных
enc_result = he_dot.server_compute(enc_input, model_weights)
print(f"Сервер вернул зашифрованный результат")

# Клиент расшифровывает
result = he_dot.client_decrypt_result(enc_result)
print(f"Приватное dot product: {result:.4f} (ожидалось: {expected:.4f})")
```

### Приватные медицинские запросы

```python
def private_statistics_demo():
    """
    Больница хочет посчитать статистику по пациентам,
    не раскрывая индивидуальные данные сервису аналитики
    """
    paillier = PaillierCryptosystem(bits=256)
    
    # Данные пациентов (конфиденциальные)
    patient_ages = [45, 32, 67, 28, 55, 41, 73, 38]
    
    print(f"Реальные данные (конфиденциальные): {patient_ages}")
    print(f"Реальное среднее: {sum(patient_ages)/len(patient_ages):.1f}")
    
    # Шифрование
    encrypted_ages = [paillier.encrypt(age) for age in patient_ages]
    print("\nДанные зашифрованы, отправлены аналитику...")
    
    # Аналитик считает сумму (гомоморфно!)
    total_encrypted = encrypted_ages[0]
    for ea in encrypted_ages[1:]:
        total_encrypted = paillier.add(total_encrypted, ea)
    
    # Больница расшифровывает только сумму
    total = paillier.decrypt(total_encrypted)
    average = total / len(patient_ages)
    
    print(f"Гомоморфная сумма: {total}")
    print(f"Среднее: {average:.1f}")
    print("Аналитик не видел индивидуальных возрастов!")

private_statistics_demo()
```

---

## 7. Библиотеки FHE

### Microsoft SEAL

```bash
# Python обёртка
pip install tenseal

python3 -c "
import tenseal as ts

# Создание CKKS контекста (для ML)
context = ts.context(
    ts.SCHEME_TYPE.CKKS,
    poly_modulus_degree=8192,
    coeff_mod_bit_sizes=[60, 40, 40, 60]
)
context.generate_galois_keys()
context.global_scale = 2**40

# Шифрование
plain = [1.5, 2.0, 3.5]
encrypted = ts.ckks_vector(context, plain)

# Гомоморфные операции
result = encrypted + encrypted  # 2*plain
decrypted = result.decrypt()
print(f'2×{plain} = {[round(x, 2) for x in decrypted]}')
"
```

### OpenFHE

OpenFHE (preемник PALISADE) — открытая реализация CKKS, BFV, BGV, TFHE от Duality Technologies:

```python
# pip install openfhe
# Концептуальный пример
"""
import openfhe as fhe

# CKKS схема
parameters = fhe.CCParamsCKKSRNS()
parameters.SetMultiplicativeDepth(5)
parameters.SetScalingModSize(50)
parameters.SetBatchSize(8)

cc = fhe.GenCryptoContext(parameters)
cc.Enable(fhe.PKESchemeFeature.PKE)
cc.Enable(fhe.PKESchemeFeature.KEYSWITCH)
cc.Enable(fhe.PKESchemeFeature.LEVELEDSHE)

keys = cc.KeyGen()
cc.EvalMultKeyGen(keys.secretKey)

# Шифрование
x = [1.0, 2.0, 3.0, 4.0]
ptxt = cc.MakeCKKSPackedPlaintext(x)
ctxt = cc.Encrypt(keys.publicKey, ptxt)

# Гомоморфное умножение само на себя (x²)
ctxt_sq = cc.EvalMult(ctxt, ctxt)

# Расшифровка
result = cc.Decrypt(keys.secretKey, ctxt_sq)
print(result.GetRealPackedValue()[:4])  # [1, 4, 9, 16]
"""
```

---

## Заключение

Гомоморфное шифрование — технология, открывающая принципиально новые возможности приватных вычислений. Однако она требует баланса между функциональностью и производительностью.

**Текущее состояние (2024):**
- Частично гомоморфные схемы (Paillier, ElGamal) — практически применимы уже сейчас для ограниченных задач (агрегация, голосование)
- FHE — пригодна для производства в ограниченных сценариях (несложные ML inference задачи)
- Активные исследования по оптимизации: FPGA/ASIC ускорители, улучшение bootstrapping
- Компании активно используют FHE: Microsoft (Azure), Google (Private Join and Compute), Zama

**Когда использовать:**
- Есть требование never-decrypt данные (медицина, финансы, государственные)
- Latency не критична
- Нужны относительно простые операции

---

## Литература и источники

1. Gentry, C. (2009). *A Fully Homomorphic Encryption Scheme*. Stanford Ph.D. thesis. https://crypto.stanford.edu/craig/craig-thesis.pdf
2. Brakerski, Z., Vaikuntanathan, V. (2011). *Fully Homomorphic Encryption from Ring-LWE and Security for Key Dependent Messages*. CRYPTO 2011. https://eprint.iacr.org/2011/277
3. Cheon, J.H., et al. (2017). *Homomorphic Encryption for Arithmetic of Approximate Numbers (CKKS)*. ASIACRYPT 2017. https://eprint.iacr.org/2016/421
4. Regev, O. (2005). *On Lattices, Learning with Errors, Random Linear Codes, and Cryptography*. STOC 2005. https://cims.nyu.edu/~regev/papers/qcrypto.pdf
5. Microsoft SEAL. *Simple Encrypted Arithmetic Library*. https://github.com/microsoft/SEAL
6. OpenFHE. https://www.openfhe.org/
7. TenSEAL (Python SEAL wrapper). https://github.com/OpenMined/TenSEAL
8. Wikipedia: Homomorphic encryption. https://en.wikipedia.org/wiki/Homomorphic_encryption
9. Halevi, S. (2017). *Homomorphic Encryption* (survey). https://link.springer.com/chapter/10.1007/978-3-319-57048-8_5
