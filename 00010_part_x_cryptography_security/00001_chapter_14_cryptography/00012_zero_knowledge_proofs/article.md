# Zero-Knowledge Proofs — доказательство без раскрытия секрета

## Введение

Zero-Knowledge Proof (ZKP, доказательство с нулевым разглашением) — один из наиболее удивительных результатов теоретической криптографии. Идея: один участник (prover, доказывающий) убеждает другого участника (verifier, проверяющего) в истинности некоторого утверждения, не раскрывая никакой дополнительной информации, кроме самого факта истинности.

Например: «Я знаю пароль» — без раскрытия пароля. «Эта транзакция корректна» — без раскрытия деталей транзакции. «Мне исполнилось 18 лет» — без раскрытия точной даты рождения. ZKP применяются в криптовалютах (Zcash), блокчейн масштабировании (zkEVM, StarkNet), аутентификации и верификации вычислений.

---

## 1. Интерактивные ZKP — три свойства

### Пещера Али-Бабы (классический пример)

Классический иллюстративный пример: пещера с тайной дверью посередине. Алиса утверждает, что знает секретное слово, открывающее дверь. Как убедить Боба, не раскрывая само слово?

```
       Вход
         |
         A
        / \
Путь L    Путь R
        |
      [ДВЕРЬ] ← открывается секретным словом
```

**Протокол:**
1. Боб стоит у входа и отворачивается
2. Алиса заходит в пещеру и случайно выбирает путь L или R
3. Боб кричит: «Выйди по пути L!» (или R — случайный выбор)
4. Если Алиса знает секрет — она всегда выйдет по нужному пути
5. Если не знает — угадает с вероятностью 1/2

После 20 повторений: вероятность успеха без знания секрета = (1/2)²⁰ ≈ 1/1000000.

### Три свойства ZKP

**1. Completeness (полнота):** Если утверждение истинно и prover честен — verifier убедится с высокой вероятностью.

**2. Soundness (корректность):** Если утверждение ложно — нечестный prover не убедит verifier (кроме пренебрежимо малой вероятности).

**3. Zero-Knowledge (нулевое разглашение):** Verifier не получает никакой информации кроме факта истинности. Формально: существует симулятор, который производит неотличимую от реального протокола «транскрипцию» без знания секрета.

---

## 2. Протокол Шнорра (интерактивный ZKP)

Schnorr протокол (Claus Schnorr, 1989) — классический интерактивный ZKP для знания дискретного логарифма.

**Цель:** Prover знает `x` такое, что `y = g^x mod p`. Доказать это без раскрытия `x`.

**Протокол:**

1. **Commitment:** Prover выбирает случайный `r`, вычисляет `R = g^r mod p`, отправляет R verifier'у
2. **Challenge:** Verifier выбирает случайный `c` (challenge), отправляет c prover'у
3. **Response:** Prover вычисляет `s = r + c×x mod q`, отправляет s verifier'у
4. **Verification:** Verifier проверяет: `g^s == R × y^c mod p`

```python
import random
from sympy import isprime, randprime, primitive_root

class SchnorrProtocol:
    """
    Демонстрационный протокол Шнорра (интерактивный ZKP)
    ТОЛЬКО ДЛЯ ОБРАЗОВАТЕЛЬНЫХ ЦЕЛЕЙ — не для реального использования!
    """
    
    def __init__(self, bits: int = 256):
        # Генерация групповых параметров
        # В реальности используются стандартизированные параметры
        self.p = randprime(2**(bits-1), 2**bits)  # Большое простое
        self.q = (self.p - 1) // 2  # Если p = 2q+1 (safe prime)
        self.g = 2  # Генератор (упрощение)
    
    def generate_keys(self) -> tuple:
        """Генерация ключевой пары"""
        x = random.randint(1, self.q - 1)  # Закрытый ключ
        y = pow(self.g, x, self.p)          # Открытый ключ: y = g^x mod p
        return x, y
    
    def prove(self, x: int, challenge: int) -> tuple:
        """Prover: commitment + response"""
        # Commitment
        r = random.randint(1, self.q - 1)  # Случайный nonce
        R = pow(self.g, r, self.p)          # R = g^r mod p
        
        # Response к challenge
        s = (r + challenge * x) % self.q   # s = r + c*x mod q
        
        return R, s
    
    def verify(self, y: int, R: int, challenge: int, s: int) -> bool:
        """Verifier: проверка proof"""
        # g^s == R * y^c mod p
        lhs = pow(self.g, s, self.p)
        rhs = (R * pow(y, challenge, self.p)) % self.p
        return lhs == rhs

# Демонстрация
schnorr = SchnorrProtocol(bits=128)  # Маленькие числа для скорости

x, y = schnorr.generate_keys()
print(f"Закрытый ключ x: {x}")
print(f"Открытый ключ y=g^x: {y}")

# Интерактивный proof
challenge = random.randint(1, 2**64)  # Verifier's challenge
R, s = schnorr.prove(x, challenge)

# Верификация
is_valid = schnorr.verify(y, R, challenge, s)
print(f"\nProof корректен: {is_valid}")

# Попытка обмана: не знаем x, угадываем R
fake_R = random.randint(1, schnorr.p - 1)
fake_s = random.randint(1, schnorr.q - 1)
is_fake = schnorr.verify(y, fake_R, challenge, fake_s)
print(f"Поддельный proof: {is_fake}")  # False (с очень высокой вероятностью)
```

---

## 3. Неинтерактивные ZKP (Fiat-Shamir heuristic)

Интерактивные ZKP требуют живого участия verifier'а для генерации challenge. Для практических применений нужны **неинтерактивные ZKP** (NIZK).

**Эвристика Фиат-Шамира:** Заменить случайный challenge verifier'а на хеш всех предыдущих сообщений протокола:

```
challenge = H(public_key || commitment || ...)
```

Это превращает интерактивный proof в неинтерактивный, который можно:
- Вычислить один раз
- Передать кому угодно
- Верифицировать без взаимодействия

```python
import hashlib

class SchnorrNIZK:
    """Неинтерактивный Schnorr ZKP через Fiat-Shamir"""
    
    def __init__(self, p: int, g: int, q: int):
        self.p = p
        self.g = g
        self.q = q
    
    def prove(self, x: int, y: int, message: bytes = b"") -> tuple:
        """Создание неинтерактивного proof"""
        import secrets
        
        # Commitment
        r = int.from_bytes(secrets.token_bytes(32), 'big') % self.q
        R = pow(self.g, r, self.p)
        
        # Challenge = H(g || y || R || message) — Fiat-Shamir
        hash_input = (str(self.g) + str(y) + str(R)).encode() + message
        c = int(hashlib.sha256(hash_input).hexdigest(), 16) % self.q
        
        # Response
        s = (r + c * x) % self.q
        
        return R, c, s
    
    def verify(self, y: int, R: int, c: int, s: int, message: bytes = b"") -> bool:
        """Верификация неинтерактивного proof"""
        # Воссоздаём challenge
        hash_input = (str(self.g) + str(y) + str(R)).encode() + message
        expected_c = int(hashlib.sha256(hash_input).hexdigest(), 16) % self.q
        
        if c != expected_c:
            return False
        
        # Проверяем g^s == R * y^c mod p
        lhs = pow(self.g, s, self.p)
        rhs = (R * pow(y, c, self.p)) % self.p
        return lhs == rhs
```

---

## 4. zk-SNARKs

**zk-SNARK** (Zero-Knowledge Succinct Non-interactive ARgument of Knowledge) — мощный класс ZKP с свойствами:

- **Zero-Knowledge:** не раскрывает ничего кроме факта истинности
- **Succinct:** proof очень маленький (константного размера, обычно < 300 байт)
- **Non-interactive:** нет взаимодействия, proof публикуется
- **ARgument of Knowledge:** prover знает witness (секрет)

### Основная идея zk-SNARKs

Произвольное вычисление преобразуется в **algebraic circuit**, которая затем кодируется в **Quadratic Arithmetic Program (QAP)** или R1CS (Rank-1 Constraint System). Это позволяет доказать знание входных данных для любой вычислимой функции.

```
Задача: "Я знаю x такое, что SHA256(x) = 0xABCD..."
                ↓
Алгебраическая схема SHA256 (миллионы ворот)
                ↓
R1CS constraints
                ↓
Полиномиальные обязательства (commitment)
                ↓
Proof (288 байт для Groth16)
```

### Trusted Setup — доверенная инициализация

Большинство zk-SNARK схем (Groth16, PLONK) требуют **trusted setup** — одноразовой инициализации с «токсичными отходами»:

1. Несколько участников независимо генерируют случайные параметры
2. Их произведение = structured reference string (SRS)
3. Индивидуальные случайные числа уничтожаются — «токсичные отходы»
4. Если хотя бы один участник честен — SRS безопасен

Пример: **Zcash Powers of Tau ceremony** (2018) — 87 участников со всего мира.

**zk-STARKs** (Scalable Transparent ARguments of Knowledge) не требуют trusted setup — используют хеш-функции как единственный криптографический примитив.

---

## 5. Практические применения ZKP

### Zcash: анонимные транзакции

Zcash использует zk-SNARKs (Groth16) для «защищённых» транзакций:
- Транзакция скрывает сумму, отправителя и получателя
- ZKP доказывает: 1) Сумма сохраняется (нет создания из ничего), 2) У отправителя есть монеты
- Размер proof: 192 байта, верификация < 10 мс

### zkEVM и Layer 2

zkEVM (Polygon zkEVM, zkSync Era, Scroll) создают ZKP для выполнения EVM транзакций:
- Тысячи транзакций сворачиваются в один proof
- Proof верифицируется в mainnet Ethereum (дёшево)
- Масштабирование: 100-1000× по throughput

### StarkNet (zk-STARKs)

StarkNet использует zk-STARKs:
- Нет trusted setup
- STARK proof больше (~40KB vs 288B для Groth16)
- Быстрее генерация для больших вычислений
- Квантово-устойчив (на основе хеш-функций, а не эллиптических кривых)

### zkLogin (Sui, Mysten Labs)

zkLogin позволяет создать blockchain кошелёк, используя OAuth (Google, Facebook) без раскрытия OAuth токена на блокчейне:

```
1. Пользователь авторизуется через Google → получает JWT
2. Генерируется ZKP: "Я знаю JWT от Google для email X, 
   подписанный публичным ключом Google"
3. В blockchain публикуется только ZKP + хеш email
4. Никаких OAuth токенов в блокчейне
5. Email не раскрывается (только его хеш с солью)
```

---

## 6. Концептуальные примеры

### Верификация возраста без раскрытия даты рождения

```python
import hashlib
import datetime

class AgeProof:
    """
    Концептуальный пример: доказательство достижения 18 лет
    без раскрытия точного возраста
    
    В реальности реализуется через Bulletproofs или zk-SNARKs
    """
    
    @staticmethod
    def create_commitment(birth_year: int, randomness: bytes) -> bytes:
        """Pedersen commitment: commit(birth_year, r)"""
        # Упрощение: в реальности это криптографическое commitment
        data = f"{birth_year}".encode() + randomness
        return hashlib.sha256(data).digest()
    
    @staticmethod
    def prove_over_18(birth_year: int, current_year: int, randomness: bytes) -> dict:
        """
        Создание proof того, что age >= 18
        В реальности: Bulletproof или ZK circuit
        """
        age = current_year - birth_year
        assert age >= 18, "Должно быть >= 18"
        
        commitment = AgeProof.create_commitment(birth_year, randomness)
        
        # В реальном ZKP здесь был бы cryptographic proof
        # что committed value такова, что current_year - value >= 18
        return {
            "commitment": commitment.hex(),
            "current_year": current_year,
            "minimum_age": 18,
            # "proof": <zkp_proof_bytes>  ← в реальной системе
        }
    
    @staticmethod
    def verify_age_proof(proof: dict, commitment: str) -> bool:
        """
        Верификация без знания реального возраста
        В реальности: проверка ZKP
        """
        # Упрощение: в реальности verifier проверяет ZKP
        # не зная birth_year, только commitment
        return proof["commitment"] == commitment

# Пример
randomness = bytes.fromhex("a1b2c3d4" * 8)
birth_year = 1990
current_year = 2024

proof = AgeProof.prove_over_18(birth_year, current_year, randomness)
print(f"Commitment: {proof['commitment'][:16]}...")
print(f"Верификация (только commitment): {AgeProof.verify_age_proof(proof, proof['commitment'])}")
# Verifier знает: age >= 18, но не знает точного года рождения
```

### Schnorr proof в блокчейне (Taproot Bitcoin)

Bitcoin Taproot (BIP 341, 2021) использует Schnorr подписи и **Merkle Abstract Syntax Trees (MAST)**. ZKP аспект: Taproot позволяет скрыть скрипты расходования — verifier знает только что один из скриптов выполнен, но не какой именно.

---

## 7. Текущее состояние и ограничения

### Производительность (2024)

| Система    | Proof generation | Verification | Proof size |
|-----------|-----------------|-------------|-----------|
| Groth16   | Секунды-минуты  | ~10 мс      | 192 байта |
| PLONK     | Секунды         | ~20 мс      | ~1 KB     |
| STARK     | Секунды-минуты  | ~30 мс      | ~40 KB    |
| Bulletproofs| Секунды       | ~100 мс     | ~1 KB     |
| Nova      | Очень быстро   | Быстро      | Малый     |

### Сложность разработки

ZKP схемы требуют программирования на специальных ZK-языках:
- **Circom** (JavaScript-подобный, для Groth16/PLONK)
- **Cairo** (для STARK на StarkNet)
- **Noir** (Rust-подобный, высокоуровневый)
- **RISC Zero** (prove arbitrary Rust code)

---

## 8. Библиотеки и инструменты

```python
# Python: py_ecc, libsnark обёртки
# pip install py_ecc

from py_ecc.bn128 import G1, G2, pairing, multiply, add, neg
import secrets

# Bilinear pairing для zk-SNARK верификации
# e(a*G1, b*G2) == e(G1, G2)^(a*b)

def bilinear_pairing_demo():
    """Проверка свойства билинейного спаривания"""
    a = secrets.randbelow(2**32)
    b = secrets.randbelow(2**32)
    
    # Левая часть: e(a*G1, b*G2)
    aG1 = multiply(G1, a)
    bG2 = multiply(G2, b)
    lhs = pairing(bG2, aG1)
    
    # Правая часть: e(G1, G2)^(ab)
    eG1G2 = pairing(G2, G1)
    rhs = eG1G2 ** (a * b)
    
    print(f"e(a*G1, b*G2) == e(G1,G2)^ab: {lhs == rhs}")

# bilinear_pairing_demo()  # Медленно, для демонстрации
```

---

## Заключение

Zero-Knowledge Proofs — один из наиболее практически применимых результатов теоретической криптографии. За несколько десятилетий от академической концепции они превратились в реальный инструмент блокчейн масштабирования, приватности транзакций и верификации вычислений.

Ключевые применения:
1. **Анонимность в блокчейне** (Zcash, Tornado Cash)
2. **L2 масштабирование** (zkRollups — zkSync, Polygon zkEVM)
3. **Приватная аутентификация** (zkLogin, анонимные credentials)
4. **Верификация ML inference** без раскрытия модели

Для практического использования: используйте готовые библиотеки (snarkjs + circom, Cairo, Noir) — самостоятельная реализация ZKP системы крайне сложна и опасна.

---

## Литература и источники

1. Goldwasser, S., Micali, S., Rackoff, C. (1989). *The Knowledge Complexity of Interactive Proof Systems*. SIAM Journal on Computing. https://epubs.siam.org/doi/10.1137/0218012
2. Schnorr, C.P. (1990). *Efficient Identification and Signatures for Smart Cards*. CRYPTO 1989. https://link.springer.com/chapter/10.1007/0-387-34805-0_22
3. Groth, J. (2016). *On the Size of Pairing-based Non-interactive Arguments*. EUROCRYPT 2016. https://eprint.iacr.org/2016/260
4. Ben-Sasson, E., et al. (2018). *Scalable, transparent, and post-quantum secure computational integrity* (STARKs). https://eprint.iacr.org/2018/046
5. Zcash. *How Zcash Works*. https://z.cash/technology/
6. Gabizon, A., et al. (2019). *PLONK: Permutations over Lagrange-bases for Oecumenical Noninteractive arguments of Knowledge*. https://eprint.iacr.org/2019/953
7. Fiat, A., Shamir, A. (1986). *How to Prove Yourself*. CRYPTO 1986. https://link.springer.com/chapter/10.1007/3-540-47721-7_12
8. Wikipedia: Zero-knowledge proof. https://en.wikipedia.org/wiki/Zero-knowledge_proof
9. snarkjs library. https://github.com/iden3/snarkjs
10. Boneh, D., Shoup, V. *A Graduate Course in Applied Cryptography* (Chapter 20: ZKP). https://toc.cryptobook.us/
