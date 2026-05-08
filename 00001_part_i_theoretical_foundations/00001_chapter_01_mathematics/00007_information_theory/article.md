# Теория информации: энтропия Шеннона и кодирование

## Введение

Теория информации — математическая дисциплина, созданная Клодом Шенноном в 1948 году в статье «A Mathematical Theory of Communication». Она изучает фундаментальные пределы хранения, передачи и обработки информации. Для разработчика это основа понимания сжатия данных (gzip, zstd, Brotli), вероятностных структур данных (Bloom filter), кодирования с исправлением ошибок (RAID, QR-коды), а также машинного обучения (кросс-энтропия как функция потерь).

---

## 1. Информация и неожиданность

Ключевая идея Шеннона: **информация — это мера неожиданности**. Чем менее вероятно событие, тем больше информации оно несёт, если происходит.

Если событие x происходит с вероятностью P(x), то его **самоинформация** (количество информации):

```
I(x) = -log₂(P(x))  [бит]
```

- P(x) = 1 (событие достоверное): I(x) = 0 — никакой новой информации
- P(x) = 1/2: I(x) = 1 бит — одно бинарное решение
- P(x) = 1/8: I(x) = 3 бита — три бинарных решения

```python
import math

def self_information(probability, base=2):
    """Количество информации события с данной вероятностью"""
    return -math.log(probability, base)

# Примеры
print(f"P=1:    {self_information(1.0):.2f} бит")    # 0.00
print(f"P=1/2:  {self_information(0.5):.2f} бит")    # 1.00
print(f"P=1/4:  {self_information(0.25):.2f} бит")   # 2.00
print(f"P=1/8:  {self_information(0.125):.2f} бит")  # 3.00
print(f"P=1/6:  {self_information(1/6):.2f} бит")    # 2.58 (результат кубика)
```

---

## 2. Энтропия Шеннона

Энтропия H — это ожидаемое количество информации на символ для дискретного источника с распределением P:

```
H(X) = -Σ P(xᵢ) × log₂(P(xᵢ))
```

Это среднее количество бит, необходимых для кодирования одного символа из источника.

```python
def entropy(probabilities):
    """Энтропия Шеннона для распределения вероятностей"""
    return -sum(p * math.log2(p) for p in probabilities if p > 0)

# Равномерное распределение: максимальная энтропия
uniform_4 = [0.25, 0.25, 0.25, 0.25]
print(f"Равномерное (4 символа): {entropy(uniform_4):.3f} бит")  # 2.0

# Неравномерное: меньше энтропия
biased = [0.9, 0.05, 0.03, 0.02]
print(f"Скошенное распределение: {entropy(biased):.3f} бит")  # ≈ 0.53

# Одно событие достоверно: нулевая энтропия
certain = [1.0, 0.0, 0.0]
print(f"Достоверное событие: {entropy(certain):.3f} бит")  # 0.0
```

### Свойства энтропии

1. **H ≥ 0**: энтропия неотрицательна
2. **H = 0**: только если одно событие имеет вероятность 1
3. **Максимум**: H достигает максимума log₂(n) при равномерном распределении по n событиям
4. **Аддитивность**: для независимых X и Y: H(X, Y) = H(X) + H(Y)

```python
# Демонстрация свойств
n_values = [2, 4, 8, 16, 256]
for n in n_values:
    uniform = [1/n] * n
    h = entropy(uniform)
    print(f"n={n:3d}: H={h:.2f} (log₂({n})={math.log2(n):.2f})")
```

---

## 3. Пределы сжатия: теорема Шеннона

**Теорема об источнике кодирования (First Shannon Theorem)**: невозможно сжать источник до менее чем H(X) бит на символ без потерь. Более формально: длина оптимального кода L удовлетворяет:

```
H(X) ≤ L < H(X) + 1
```

Это нижняя граница для любого алгоритма сжатия без потерь!

```python
# Проверка: текст на английском vs случайные данные
import collections

def text_entropy(text):
    freq = collections.Counter(text)
    total = len(text)
    probs = [count / total for count in freq.values()]
    return entropy(probs)

english_text = "the quick brown fox jumps over the lazy dog"
random_text = "".join([chr(i) for i in range(256)] * (len(english_text) // 256 + 1))[:len(english_text)]

print(f"Энтропия английского: {text_entropy(english_text):.2f} бит/символ")
print(f"Энтропия случайного:  {text_entropy(random_text):.2f} бит/символ")

# Реальное сжатие
import zlib, sys

data_en = english_text.encode()
data_rnd = random_text[:len(english_text)].encode()

ratio_en = len(zlib.compress(data_en)) / len(data_en)
ratio_rnd = len(zlib.compress(data_rnd)) / len(data_rnd)

print(f"Коэффициент сжатия английского: {ratio_en:.2f}")  # < 1
print(f"Коэффициент сжатия случайного:  {ratio_rnd:.2f}")  # ≈ 1
```

---

## 4. Коды Хаффмана

Код Хаффмана — оптимальный (по длине кодового слова) префиксный код для заданного распределения символов. Это жадный алгоритм на основе приоритетной очереди.

```python
import heapq
from collections import defaultdict

def huffman_code(frequencies):
    """
    Строит коды Хаффмана для символов с заданными частотами.
    """
    # Создаём кучу из (частота, символ)
    heap = [[freq, symbol] for symbol, freq in frequencies.items()]
    heapq.heapify(heap)
    
    # Строим дерево
    while len(heap) > 1:
        lo = heapq.heappop(heap)
        hi = heapq.heappop(heap)
        for item in lo[2:]:
            item[1] = '0' + item[1]
        for item in hi[2:]:
            item[1] = '1' + item[1]
        heapq.heappush(heap, [lo[0] + hi[0]] + lo[1:] + hi[1:])
    
    return sorted(heap[0][1:], key=lambda p: (len(p[-1]), p))

def huffman_encode_decode(text):
    """Полный цикл кодирования/декодирования Хаффмана"""
    freq = collections.Counter(text)
    
    # Строим дерево через кучу
    heap = [[w, [sym, ""]] for sym, w in freq.items()]
    heapq.heapify(heap)
    
    while len(heap) > 1:
        lo = heapq.heappop(heap)
        hi = heapq.heappop(heap)
        for pair in lo[1:]:
            pair[1] = '0' + pair[1]
        for pair in hi[1:]:
            pair[1] = '1' + pair[1]
        heapq.heappush(heap, [lo[0] + hi[0]] + lo[1:] + hi[1:])
    
    codes = {sym: code for sym, code in heap[0][1:]}
    encoded = ''.join(codes[c] for c in text)
    
    # Декодирование (строим обратный словарь)
    reverse = {v: k for k, v in codes.items()}
    current = ''
    decoded = ''
    for bit in encoded:
        current += bit
        if current in reverse:
            decoded += reverse[current]
            current = ''
    
    return codes, encoded, decoded

text = "abracadabra"
codes, encoded, decoded = huffman_encode_decode(text)

print("\nКоды Хаффмана:")
for sym, code in sorted(codes.items()):
    print(f"  '{sym}': {code} ({len(code)} бит)")

print(f"\nОригинал: {text!r}")
print(f"Закодировано: {encoded}")
print(f"Длина закодированного: {len(encoded)} бит")
print(f"ASCII (8 бит/символ): {len(text) * 8} бит")
print(f"Сжатие: {len(encoded) / (len(text) * 8):.2f}x")
print(f"Декодировано: {decoded!r}")
print(f"Корректность: {text == decoded}")
```

### Оптимальность кода Хаффмана

Код Хаффмана даёт среднюю длину кода L, удовлетворяющую H(X) ≤ L < H(X) + 1. Арифметическое кодирование может приблизиться вплотную к H(X), но за счёт большей вычислительной сложности.

---

## 5. Взаимная информация

Взаимная информация I(X; Y) — количество информации об X, которую несёт Y:

```
I(X; Y) = H(X) - H(X | Y) = H(Y) - H(Y | X)
        = Σₓ Σᵧ P(x, y) × log₂(P(x, y) / (P(x) × P(y)))
```

Если X и Y независимы: I(X; Y) = 0 — знание Y ничего не говорит о X.

```python
import numpy as np

def mutual_information(joint_prob_matrix):
    """
    joint_prob_matrix[i][j] = P(X=i, Y=j)
    """
    px = joint_prob_matrix.sum(axis=1)
    py = joint_prob_matrix.sum(axis=0)
    
    mi = 0.0
    for i in range(len(px)):
        for j in range(len(py)):
            pxy = joint_prob_matrix[i, j]
            if pxy > 0 and px[i] > 0 and py[j] > 0:
                mi += pxy * np.log2(pxy / (px[i] * py[j]))
    return mi

# Полная зависимость (X = Y)
joint_full = np.array([[0.5, 0.0],
                       [0.0, 0.5]])
print(f"I(X;Y) при X=Y: {mutual_information(joint_full):.3f}")  # = H(X) = 1.0

# Независимость
joint_indep = np.array([[0.25, 0.25],
                        [0.25, 0.25]])
print(f"I(X;Y) при независимости: {mutual_information(joint_indep):.3f}")  # 0.0
```

Взаимная информация используется в машинном обучении для выбора признаков (feature selection) — признак с большей взаимной информацией с целевой переменной более информативен.

---

## 6. Пропускная способность канала

**Теорема Шеннона о пропускной способности канала**: максимальная скорость надёжной передачи информации через канал с шумом:

```
C = max_{P(X)} I(X; Y)  [бит/использование канала]
```

Для Гауссова канала с шириной полосы B и отношением сигнал/шум SNR:

```
C = B × log₂(1 + SNR)  [бит/с]
```

Это принципиальный предел — никакое кодирование не может превысить его.

```python
def shannon_capacity(bandwidth_hz, snr_linear):
    """
    bandwidth_hz: ширина полосы в Гц
    snr_linear: SNR (не в дБ, а в разах)
    Возвращает пропускную способность в бит/с
    """
    return bandwidth_hz * math.log2(1 + snr_linear)

# WiFi 802.11ac: полоса 80 МГц, SNR = 25 дБ (≈ 316)
bw = 80e6  # 80 МГц
snr_db = 25
snr = 10 ** (snr_db / 10)

capacity = shannon_capacity(bw, snr)
print(f"Теоретический предел: {capacity / 1e6:.0f} Мбит/с")  # ≈ 660 Мбит/с

# Реальный WiFi 802.11ac: до 433 Мбит/с (эффективность ~65%)
```

---

## 7. KL-дивергенция и кросс-энтропия

**KL-дивергенция** (Kullback–Leibler divergence) — асимметричная мера «расстояния» между распределениями:

```
KL(P || Q) = Σ P(x) × log₂(P(x) / Q(x))
```

KL(P || Q) ≥ 0, равна 0 только если P = Q. Не симметрична: KL(P||Q) ≠ KL(Q||P).

**Кросс-энтропия**:

```
H(P, Q) = -Σ P(x) × log₂(Q(x)) = H(P) + KL(P || Q)
```

```python
import numpy as np

def kl_divergence(p, q, eps=1e-12):
    """KL(P || Q) — насколько Q отличается от P"""
    p, q = np.array(p), np.array(q)
    return np.sum(p * np.log2((p + eps) / (q + eps)))

def cross_entropy(p, q, eps=1e-12):
    """H(P, Q) — стоимость кодирования P с помощью Q"""
    p, q = np.array(p), np.array(q)
    return -np.sum(p * np.log2(q + eps))

# Истинное распределение
p = np.array([0.4, 0.4, 0.1, 0.1])

# Хорошее приближение
q_good = np.array([0.35, 0.45, 0.12, 0.08])

# Плохое приближение (равномерное)
q_bad = np.array([0.25, 0.25, 0.25, 0.25])

print(f"H(P) = {entropy(p):.4f}")                    # ≈ 1.72
print(f"KL(P||Q_good) = {kl_divergence(p, q_good):.4f}")  # мало
print(f"KL(P||Q_bad)  = {kl_divergence(p, q_bad):.4f}")   # больше
print(f"H(P, Q_good) = {cross_entropy(p, q_good):.4f}")
print(f"H(P, Q_bad)  = {cross_entropy(p, q_bad):.4f}")    # = H(P) + KL
```

В машинном обучении кросс-энтропийная функция потерь измеряет, насколько предсказанное распределение Q отличается от истинного P. Минимизация кросс-энтропии = минимизация KL-дивергенции (при фиксированном P).

---

## 8. Теория кодирования с исправлением ошибок

**Теорема Шеннона (вторая)**: для канала с пропускной способностью C можно передавать информацию со скоростью R < C с вероятностью ошибки, сколь угодно близкой к нулю, используя коды достаточной длины.

### Расстояние Хэмминга

Расстояние Хэмминга между двумя строками — количество позиций, в которых они различаются:

```python
def hamming_distance(a, b):
    return sum(x != y for x, y in zip(a, b))

print(hamming_distance("10110", "10011"))  # 3 — три различия
print(hamming_distance("karolin", "kathrin"))  # 3
```

Код с минимальным расстоянием Хэмминга d_min может:
- Обнаруживать до d_min - 1 ошибок
- Исправлять до ⌊(d_min - 1) / 2⌋ ошибок

### Код Хэмминга (7, 4)

Кодирует 4 бита данных в 7 бит кода, исправляет 1 ошибку:

```python
import numpy as np

# Порождающая матрица кода Хэмминга(7,4)
G = np.array([
    [1, 0, 0, 0, 1, 1, 0],
    [0, 1, 0, 0, 1, 0, 1],
    [0, 0, 1, 0, 0, 1, 1],
    [0, 0, 0, 1, 1, 1, 1]
], dtype=int)

# Матрица проверки чётности
H_check = np.array([
    [1, 1, 0, 1, 1, 0, 0],
    [1, 0, 1, 1, 0, 1, 0],
    [0, 1, 1, 1, 0, 0, 1]
], dtype=int)

def hamming_encode(data_bits):
    """Кодирование 4 бит данных в 7 бит кода"""
    data = np.array(data_bits)
    codeword = (data @ G) % 2
    return codeword

def hamming_decode(received):
    """Декодирование и исправление одиночной ошибки"""
    r = np.array(received)
    syndrome = (H_check @ r) % 2
    error_pos = int(''.join(map(str, syndrome)), 2) - 1
    
    if error_pos >= 0:
        corrected = r.copy()
        corrected[error_pos] ^= 1
        print(f"Ошибка исправлена на позиции {error_pos + 1}")
        return corrected[:4]
    else:
        return r[:4]

data = [1, 0, 1, 1]
encoded = hamming_encode(data)
print(f"Данные:   {data}")
print(f"Кодовое слово: {encoded.tolist()}")

# Вводим ошибку в позицию 3
received = encoded.copy()
received[2] ^= 1
print(f"Получено: {received.tolist()} (ошибка на позиции 3)")

decoded = hamming_decode(received)
print(f"Декодировано: {decoded.tolist()}")
print(f"Корректно: {data == decoded.tolist()}")
```

---

## 9. Энтропия и деревья решений

В машинном обучении энтропия используется как критерий разбиения в деревьях решений (алгоритм ID3):

```python
def information_gain(parent_labels, child_groups):
    """
    Прирост информации от разбиения на группы.
    parent_labels: метки до разбиения
    child_groups: список групп меток после разбиения
    """
    def label_entropy(labels):
        counts = collections.Counter(labels)
        total = len(labels)
        return entropy([c/total for c in counts.values()])
    
    parent_entropy = label_entropy(parent_labels)
    n_total = len(parent_labels)
    
    weighted_child_entropy = sum(
        len(group) / n_total * label_entropy(group)
        for group in child_groups
    )
    
    return parent_entropy - weighted_child_entropy

# Пример: признак "погода" предсказывает "игру в теннис"
all_labels = ['+', '+', '-', '+', '-', '-', '-', '+', '+', '+', '-', '+', '+', '-']
# Разбиение по признаку "ветер": слабый/сильный
weak_wind  = ['+', '+', '+', '-', '+', '-', '+']  # 4+ / 3-
strong_wind = ['-', '+', '-', '-', '+', '-', '+']  # 3+ / 4-

ig = information_gain(all_labels, [weak_wind, strong_wind])
print(f"Прирост информации от 'ветер': {ig:.4f}")
```

Выбирается признак с максимальным приростом информации.

---

## Заключение

Теория информации устанавливает **фундаментальные пределы** в вычислениях:

- **Нижняя граница сжатия**: нельзя сжать ниже энтропии источника
- **Верхняя граница скорости передачи**: нельзя превысить пропускную способность канала
- **Оптимальное кодирование**: код Хаффмана, арифметическое кодирование
- **Функции потерь**: кросс-энтропия = минимизация KL-дивергенции

Энтропия Шеннона — одно из величайших открытий XX века: простая формула, измеряющая количество информации, стала основой всей цифровой революции.

---

## Литература и источники

1. Shannon, C. E. (1948). A mathematical theory of communication. *Bell System Technical Journal*, 27(3), 379–423. — Оригинальная статья. Доступно: https://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf

2. Cover, T. M., & Thomas, J. A. (2006). *Elements of Information Theory* (2nd ed.). Wiley. — Стандартный учебник.

3. MacKay, D. J. C. (2003). *Information Theory, Inference, and Learning Algorithms*. Cambridge University Press. Доступно онлайн: http://www.inference.org.uk/mackay/itila/

4. Blahut, R. E. (2010). *Principles and Practice of Information Theory*. Addison-Wesley.

5. Huffman, D. A. (1952). A method for the construction of minimum-redundancy codes. *Proceedings of the IRE*, 40(9), 1098–1101. — Оригинальная статья об алгоритме Хаффмана.

6. Hamming, R. W. (1950). Error detecting and error correcting codes. *Bell System Technical Journal*, 29(2), 147–160. — Коды Хэмминга.

7. Kullback, S., & Leibler, R. A. (1951). On information and sufficiency. *Annals of Mathematical Statistics*, 22(1), 79–86. — KL-дивергенция.
