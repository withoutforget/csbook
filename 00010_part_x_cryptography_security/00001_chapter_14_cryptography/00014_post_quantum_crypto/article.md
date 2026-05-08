# Постквантовая криптография: Kyber и Dilithium

## Введение

Большинство современной криптографии с открытым ключом — RSA, ECDSA, ECDH — основана на задачах, для которых нет эффективных классических алгоритмов: факторизации, дискретном логарифме. Однако квантовые компьютеры меняют эту картину: алгоритм Шора, разработанный Питером Шором (Peter Shor) в 1994 году, позволяет решать эти задачи за полиномиальное время на квантовом компьютере.

В 2024 году NIST завершил первый этап стандартизации **постквантовой криптографии** (Post-Quantum Cryptography, PQC) — алгоритмов, устойчивых к квантовым атакам. Новые стандарты: **ML-KEM (CRYSTALS-Kyber)** для обмена ключами и **ML-DSA (CRYSTALS-Dilithium)** для подписей основаны на задачах теории решёток (lattice problems), которые сложны как для классических, так и для квантовых компьютеров.

---

## 1. Квантовая угроза

### Алгоритм Шора (1994)

Алгоритм Шора позволяет квантовому компьютеру факторизовать число N за время O((log N)³), что полиномиально. Это уничтожает RSA.

Аналогично, алгоритм Шора решает задачу дискретного логарифма — уничтожает DSA, ECDSA, DH, ECDH.

**Необходимые ресурсы для атаки на RSA-2048:**
- Теоретически: ~4000 логических кубитов
- Практически (с исправлением ошибок): миллионы физических кубитов
- Текущий рекорд (2024): IBM Eagle — 127 кубитов; IBM Condor — 1121 кубит
- Стабильные вычисления с исправлением ошибок: ещё далеко

**Вывод:** Квантовые компьютеры, способные взломать RSA-2048, появятся через 10-20+ лет. Но действовать нужно сейчас.

### Алгоритм Гровера (1996)

Алгоритм Гровера обеспечивает квадратичное ускорение поиска. Для симметричной криптографии:
- AES-128: эффективная безопасность снижается до 64 бит — небезопасно
- AES-256: эффективная безопасность снижается до 128 бит — **по-прежнему безопасно**
- SHA-256: коллизии за O(2¹²⁸) вместо O(2¹²⁸) — безопасно
- SHA-512: безопасно

**Практический вывод:** Для симметричной криптографии достаточно удвоить длину ключа. AES-256 — постквантово безопасен.

### «Harvest now, decrypt later» (HNDL)

Критическая угроза уже сейчас: государственные акторы и другие организации могут **сейчас** записывать зашифрованный трафик, чтобы расшифровать его **позже**, когда появятся достаточно мощные квантовые компьютеры.

```
2024: Злоумышленник записывает трафик, зашифрованный RSA/ECDH
2034: Появляется квантовый компьютер
2034: Расшифровка записанного трафика

Данные с долгим сроком секретности (государственные тайны,
медицинские записи, финансовые документы) уже под угрозой!
```

---

## 2. Математические основы PQC

### Задача о решётках (Lattice Problems)

Решётка — это дискретное подпространство Rⁿ: множество всех целочисленных линейных комбинаций базисных векторов.

**SVP (Shortest Vector Problem):** Найти кратчайший ненулевой вектор в решётке. Считается NP-hard для квантовых алгоритмов.

**CVP (Closest Vector Problem):** Найти ближайший вектор решётки к заданной точке.

**LWE (Learning With Errors):** Уже рассматривалось в статье о FHE. Лежит в основе Kyber и Dilithium.

### Module-LWE (MLWE)

Kyber и Dilithium используют **Module-LWE** — вариант LWE на кольцах полиномов, что обеспечивает лучший баланс производительности и безопасности:

```
Ring: R_q = Z_q[x] / (x^n + 1)
n = 256 (для ML-KEM-768)
q = 3329

Задача MLWE:
Дано: матрица A (k×k), вектор b = A×s + e
Найти: вектор s (секрет), e (малый шум)

Сложно даже для квантовых компьютеров при достаточно больших параметрах.
```

---

## 3. NIST PQC Стандартизация

В 2016 году NIST начал процесс стандартизации PQC алгоритмов. В 2024 году опубликованы финальные стандарты:

| Стандарт   | Алгоритм          | Тип         | Задача           |
|-----------|-------------------|-------------|-----------------|
| FIPS 203  | ML-KEM (Kyber)    | KEM         | Module-LWE      |
| FIPS 204  | ML-DSA (Dilithium)| Подпись     | Module-LWE      |
| FIPS 205  | SLH-DSA (SPHINCS+)| Подпись     | Hash (stateless) |

**FALCON** (NIST FIPS 206, в процессе) — ещё один алгоритм подписей на решётках.

---

## 4. ML-KEM (CRYSTALS-Kyber) — Обмен ключами

Kyber — это KEM (Key Encapsulation Mechanism): позволяет безопасно передать симметричный ключ по открытому каналу.

### Параметры ML-KEM

| Вариант     | Безопасность | Размер публичного ключа | Шифротекст | Секрет |
|-------------|-------------|------------------------|-----------|--------|
| ML-KEM-512  | 128 бит     | 800 байт               | 768 байт  | 32 байта|
| ML-KEM-768  | 192 бит     | 1184 байта             | 1088 байт | 32 байта|
| ML-KEM-1024 | 256 бит     | 1568 байт              | 1568 байт | 32 байта|

Сравнение с ECDH X25519:
- X25519: публичный ключ 32 байта, shared secret 32 байта
- ML-KEM-768: публичный ключ 1184 байта, шифротекст 1088 байт

Большее размеры — цена за постквантовую безопасность.

### Принцип работы Kyber KEM

**Генерация ключей:**
```
A ← генерируется из seed (матрица k×k полиномов)
(s, e₁) ← малые случайные векторы
t = A × s + e₁ (mod q)  // t = "публичный ключ"
Открытый ключ: (A, t)
Закрытый ключ: s
```

**Encapsulation (отправка ключа):**
```
m ← случайное сообщение (32 байта)
(r, e₂, e₃) ← малые случайные из H(m)
u = A^T × r + e₂  // шифротекст часть 1
v = t^T × r + e₃ + encode(m)  // шифротекст часть 2
K = KDF(m)  // симметричный ключ
Шифротекст: (u, v)
```

**Decapsulation:**
```
m' = decode(v - s^T × u)  // s×u ≈ t^T×r, разница = e
// (ошибки малые → decode работает)
K = KDF(m')
```

```python
# Демонстрация через библиотеку kyber-py
# pip install kyber-py

try:
    from kyber_py.ml_kem import ML_KEM_768
    
    # Генерация ключей
    ek, dk = ML_KEM_768.keygen()
    print(f"ML-KEM-768:")
    print(f"  Публичный ключ (encapsulation key): {len(ek)} байт")
    print(f"  Закрытый ключ (decapsulation key): {len(dk)} байт")
    
    # Encapsulation: отправитель создаёт ключ
    key_sender, ciphertext = ML_KEM_768.enc(ek)
    print(f"  Шифротекст: {len(ciphertext)} байт")
    print(f"  Симметричный ключ (отправитель): {key_sender.hex()[:16]}...")
    
    # Decapsulation: получатель восстанавливает ключ
    key_receiver = ML_KEM_768.dec(dk, ciphertext)
    print(f"  Симметричный ключ (получатель): {key_receiver.hex()[:16]}...")
    print(f"  Ключи совпадают: {key_sender == key_receiver}")
    
except ImportError:
    print("kyber-py не установлен. Установите: pip install kyber-py")
    print("Демонстрация только концептуальная.")

# Использование в TLS (гибридный подход):
# TLS 1.3 + X25519 + ML-KEM-768
# Если один из них взломан — другой защищает
```

### Гибридный подход в TLS

В переходный период используют гибридные схемы:

```
X25519Kyber768 (draft):
  shared_secret = ECDH(X25519) XOR KEM(ML-KEM-768)
  
  Если квантового компьютера нет → безопасность X25519
  Если квантовый компьютер есть → безопасность ML-KEM-768
  Атакующий должен взломать ОБА алгоритма одновременно
```

---

## 5. ML-DSA (CRYSTALS-Dilithium) — Цифровые подписи

Dilithium — алгоритм цифровых подписей на основе Module-LWE.

### Параметры ML-DSA

| Вариант     | Безопасность | Публичный ключ | Подпись   |
|-------------|-------------|----------------|-----------|
| ML-DSA-44   | 128 бит     | 1312 байт      | 2420 байт |
| ML-DSA-65   | 192 бит     | 1952 байта     | 3293 байта|
| ML-DSA-87   | 256 бит     | 2592 байта     | 4595 байт |

Сравнение с Ed25519:
- Ed25519: публичный ключ 32 байта, подпись 64 байта
- ML-DSA-65: публичный ключ 1952 байта, подпись 3293 байта

### Принцип работы Dilithium

Основан на **Fiat-Shamir with Aborts** — неинтерактивная версия Schnorr-подобного ZKP:

```
Подписание (упрощённо):
1. Выбрать случайный mask y
2. Вычислить w = A×y
3. c = H(μ || HighBits(w))  // challenge
4. z = y + c×s₁
5. Если ||z|| или ||LowBits(w - c×s₂)|| слишком большие → abort и повторить
6. Подпись = (z, c)

Верификация:
w' = A×z - c×t
Проверить: c == H(μ || HighBits(w'))
```

Ключевой момент — **abort**: если z раскрыл бы информацию о секрете s — операция повторяется с новым y.

```python
# Демонстрация через dilithium-py
# pip install dilithium-py

try:
    from dilithium_py.ml_dsa import ML_DSA_65
    
    # Генерация ключей
    pk, sk = ML_DSA_65.keygen()
    print(f"ML-DSA-65:")
    print(f"  Публичный ключ: {len(pk)} байт")
    print(f"  Закрытый ключ: {len(sk)} байт")
    
    # Подписание
    message = b"Important document signed with post-quantum signature"
    signature = ML_DSA_65.sign(sk, message)
    print(f"  Подпись: {len(signature)} байт")
    
    # Верификация
    is_valid = ML_DSA_65.verify(pk, message, signature)
    print(f"  Подпись верна: {is_valid}")
    
    # Проверка изменённого сообщения
    is_invalid = ML_DSA_65.verify(pk, b"Tampered document", signature)
    print(f"  Изменённое сообщение: {is_invalid}")  # False
    
except ImportError:
    print("dilithium-py не установлен. Установите: pip install dilithium-py")
```

---

## 6. SLH-DSA (SPHINCS+) — Hash-based Signatures

SPHINCS+ — алгоритм подписей, основанный **только на хеш-функциях**. Это делает его консервативным выбором: безопасность зависит только от безопасности SHA-256 или SHAKE.

### Структура SPHINCS+

SPHINCS+ использует иерархию деревьев подписей:
- WOTS+ (Winternitz One-Time Signatures) — для листьев
- XMSS (eXtended Merkle Signature Scheme) — многоразовые подписи
- HyperTree — несколько уровней XMSS

```
HyperTree (d уровней):
Уровень d: [WOTS+₁][WOTS+₂]...[WOTS+₂ₕ]
              ↑          ↑
           XMSS дерево уровня d-1
               ↑
           XMSS дерево уровня d-2
               ...
               ↑
           Корень = публичный ключ
```

**Параметры SLH-DSA:**

| Вариант          | Безопасность | Публичный ключ | Подпись  |
|-----------------|-------------|----------------|----------|
| SLH-DSA-SHA2-128s| 128 бит    | 32 байта       | 7856 байт|
| SLH-DSA-SHA2-128f| 128 бит    | 32 байта       | 17088 байт|
| SLH-DSA-SHA2-256s| 256 бит    | 64 байта       | 29792 байт|

Большой размер подписи (7-29 KB) — основной недостаток SPHINCS+. Зато нет зависимости от решёточных предположений.

---

## 7. Алгоритмы не вошедшие в стандарт

### SIKE — взломан в 2022

SIKE (Supersingular Isogeny Key Encapsulation) был одним из финалистов NIST. В июле 2022 года исследователи Wouter Castryck и Thomas Decru опубликовали атаку, позволяющую взломать SIKE на обычном компьютере за несколько часов.

Это демонстрирует важность длительного криптоанализа перед принятием стандарта.

### McEliece

Алгоритм Мак-Элиса (1978) — один из старейших алгоритмов на основе теории кодов. Уцелел все атаки за 45 лет. Проблема: очень большие ключи (мегабайты).

```
McEliece-8192128: публичный ключ ~1 МБ, шифротекст 240 байт
Vs ML-KEM-768: публичный ключ 1184 байта, шифротекст 1088 байт
```

---

## 8. Миграция на постквантовые алгоритмы

### Стратегия «crypto agility»

**Crypto agility** — способность системы переключиться на новые алгоритмы без масштабного переписывания:

```python
class CryptoProvider:
    """Абстракция для crypto agility"""
    
    def __init__(self, use_pqc: bool = False):
        self.use_pqc = use_pqc
    
    def generate_keypair(self):
        if self.use_pqc:
            # Постквантовые ключи
            return self._generate_ml_dsa_keys()
        else:
            # Классические ключи
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            priv = Ed25519PrivateKey.generate()
            return priv, priv.public_key()
    
    def kem_encapsulate(self, public_key):
        if self.use_pqc:
            return self._ml_kem_encapsulate(public_key)
        else:
            from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
            eph = X25519PrivateKey.generate()
            shared = eph.exchange(public_key)
            return eph.public_key(), shared
    
    def sign(self, private_key, message: bytes) -> bytes:
        if self.use_pqc:
            return self._ml_dsa_sign(private_key, message)
        else:
            return private_key.sign(message)
```

### Временные рамки миграции (NIST рекомендации)

| Год  | Действие                                        |
|------|------------------------------------------------|
| 2024 | Принять стандарты ML-KEM, ML-DSA, SLH-DSA      |
| 2025 | Начать тестирование и пилотное развёртывание   |
| 2028 | Запустить гибридные схемы в production         |
| 2030 | Завершить миграцию для критических систем      |
| 2035 | Deprecate классические алгоритмы             |

### Google и Cloudflare уже используют

- **Chrome + Google:** X25519Kyber768 для TLS с конца 2023
- **Cloudflare:** X25519Kyber768 для HTTPS
- **Signal:** PQXDH (ML-KEM + X25519) с 2023

---

## 9. Практические примеры миграции

### TLS с гибридными группами

```bash
# Проверить поддержку X25519Kyber768 в OpenSSL 3.2+
openssl s_client -connect google.com:443 -groups X25519Kyber768:prime256v1 \
  -brief 2>&1 | grep "Protocol\|Cipher\|Group"

# curl с явным указанием постквантовой группы
curl --tls13-ciphers TLS_AES_256_GCM_SHA384 \
  --curves X25519Kyber768 https://pq.cloudflareresearch.com/
```

### liboqs — Open Quantum Safe

```bash
# pip install oqs
python3 -c "
import oqs

# ML-KEM (Kyber)
with oqs.KeyEncapsulation('ML-KEM-768') as kem:
    pk = kem.generate_keypair()
    ciphertext, shared_secret_enc = kem.encap_secret(pk)
    shared_secret_dec = kem.decap_secret(ciphertext)
    print('ML-KEM-768:', shared_secret_enc == shared_secret_dec)

# ML-DSA (Dilithium)
with oqs.Signature('ML-DSA-65') as signer:
    pub_key = signer.generate_keypair()
    message = b'Test message'
    signature = signer.sign(message)
    
    with oqs.Signature('ML-DSA-65') as verifier:
        is_valid = verifier.verify(message, signature, pub_key)
        print('ML-DSA-65:', is_valid)
"
```

---

## Заключение

Постквантовая криптография перешла от теории к практике. NIST стандарты ML-KEM и ML-DSA — это инструменты, готовые к использованию.

**Ключевые выводы:**
1. RSA, ECDSA, ECDH уязвимы к квантовым атакам — алгоритм Шора
2. AES-256 и SHA-256+ — постквантово безопасны (алгоритм Гровера лишь удваивает необходимую длину)
3. **HNDL угроза реальна уже сейчас** — зашифрованный трафик может быть расшифрован в будущем
4. **ML-KEM (Kyber)** — замена ECDH/X25519 для обмена ключами
5. **ML-DSA (Dilithium)** — замена ECDSA/Ed25519 для подписей
6. **Гибридный подход** (классический + постквантовый) рекомендован на переходный период
7. SIKE провал 2022 года напоминает о важности тщательного криптоанализа

---

## Литература и источники

1. NIST FIPS 203. (2024). *Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM)*. https://csrc.nist.gov/pubs/fips/203/final
2. NIST FIPS 204. (2024). *Module-Lattice-Based Digital Signature Standard (ML-DSA)*. https://csrc.nist.gov/pubs/fips/204/final
3. NIST FIPS 205. (2024). *Stateless Hash-Based Digital Signature Standard (SLH-DSA)*. https://csrc.nist.gov/pubs/fips/205/final
4. Shor, P.W. (1994). *Algorithms for Quantum Computation: Discrete Logarithms and Factoring*. FOCS 1994. https://ieeexplore.ieee.org/document/365700
5. Grover, L.K. (1996). *A Fast Quantum Mechanical Algorithm for Database Search*. STOC 1996. https://dl.acm.org/doi/10.1145/237814.237866
6. Castryck, W., Decru, T. (2022). *An Efficient Key Recovery Attack on SIDH*. https://eprint.iacr.org/2022/975
7. Bernstein, D.J., Lange, T. (2017). *Post-quantum cryptography*. Nature. https://www.nature.com/articles/nature23461
8. Open Quantum Safe project. https://openquantumsafe.org/
9. NIST PQC project. https://csrc.nist.gov/projects/post-quantum-cryptography
10. Wikipedia: Post-quantum cryptography. https://en.wikipedia.org/wiki/Post-quantum_cryptography
