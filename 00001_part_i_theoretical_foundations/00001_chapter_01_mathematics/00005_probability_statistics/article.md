# Теория вероятностей и статистика: от хеш-таблиц до A/B-тестов

## Введение

Теория вероятностей изучает случайные явления и их закономерности. Статистика — это набор методов для извлечения информации из данных. Для программиста это не академические дисциплины, а рабочие инструменты: хеш-таблицы используют вероятностный анализ, A/B-тесты требуют статистического вывода, алгоритмы ранжирования основаны на байесовском подходе, а системы мониторинга опираются на понимание распределений.

---

## 1. Основные понятия

### Вероятностное пространство

Вероятностное пространство — тройка $(\Omega, \mathcal{F}, P)$:
- $\Omega$ (пространство элементарных событий): множество всех возможных исходов
- $\mathcal{F}$ ($\sigma$-алгебра событий): семейство подмножеств $\Omega$, с которыми работают
- $P$ (вероятностная мера): функция $P : \mathcal{F} \to [0, 1]$, такая что $P(\Omega) = 1$ и $P$ счётно аддитивна

**Пример**: подбрасывание кубика:
- $\Omega = \{1, 2, 3, 4, 5, 6\}$
- $\mathcal{F}$ = все подмножества $\Omega$ ($2^6 = 64$ события)
- $P(\{k\}) = 1/6$ для каждого $k$

### Аксиомы Колмогорова

1. $P(A) \geq 0$ для любого события $A$
2. $P(\Omega) = 1$
3. Если $A_1, A_2, \ldots$ попарно несовместны, то $P(A_1 \cup A_2 \cup \ldots) = P(A_1) + P(A_2) + \ldots$

Из аксиом выводятся все остальные свойства: $P(\varnothing) = 0$, $P(\bar{A}) = 1 - P(A)$, $P(A \cup B) = P(A) + P(B) - P(A \cap B)$.

---

## 2. Условная вероятность и независимость

**Условная вероятность** — вероятность события $A$ при условии, что произошло событие $B$:

$$
P(A \mid B) = \frac{P(A \cap B)}{P(B)} \quad (\text{при } P(B) > 0)
$$

**Независимые события**: $A$ и $B$ независимы, если $P(A \cap B) = P(A) \cdot P(B)$, что эквивалентно $P(A \mid B) = P(A)$.

```python
import numpy as np

# Симуляция: два кубика
np.random.seed(42)
N = 100000
dice1 = np.random.randint(1, 7, N)
dice2 = np.random.randint(1, 7, N)

# P(сумма = 7)
sum7 = np.mean(dice1 + dice2 == 7)
print(f"P(sum=7) ≈ {sum7:.3f}")  # ≈ 0.167 = 6/36

# P(сумма = 7 | первый кубик = 4)
mask = dice1 == 4
conditional = np.mean((dice1 + dice2 == 7)[mask])
print(f"P(sum=7 | dice1=4) ≈ {conditional:.3f}")  # ≈ 1/6 — независимость!
```

### Теорема Байеса

$$
P(A \mid B) = \frac{P(B \mid A) \cdot P(A)}{P(B)}
$$

Это формула обновления убеждений: $P(A)$ — априорная вероятность (prior), $P(A \mid B)$ — апостериорная (posterior), $P(B \mid A) / P(B)$ — отношение правдоподобия.

**Пример**: спам-фильтр. Пусть $P(\text{spam}) = 0.2$, $P(\text{«выиграл»} \mid \text{spam}) = 0.7$, $P(\text{«выиграл»} \mid \overline{\text{spam}}) = 0.1$.

```python
def bayes_update(prior, likelihood_true, likelihood_false):
    """
    prior: P(H) — априорная вероятность гипотезы
    likelihood_true: P(E | H) — вероятность наблюдения при истинной гипотезе
    likelihood_false: P(E | ¬H) — вероятность наблюдения при ложной гипотезе
    """
    p_evidence = likelihood_true * prior + likelihood_false * (1 - prior)
    posterior = likelihood_true * prior / p_evidence
    return posterior

prior_spam = 0.2
p_word_given_spam = 0.7
p_word_given_ham = 0.1

posterior = bayes_update(prior_spam, p_word_given_spam, p_word_given_ham)
print(f"P(spam | слово) ≈ {posterior:.3f}")  # ≈ 0.636

# После второго признака: предполагаем также "бесплатно"
posterior2 = bayes_update(posterior, 0.8, 0.05)
print(f"P(spam | оба слова) ≈ {posterior2:.3f}")  # ≈ 0.961
```

Наивный байесовский классификатор предполагает независимость признаков (отсюда «наивный») и обновляет вероятность класса по каждому признаку последовательно.

---

## 3. Случайные величины и распределения

**Случайная величина** $X$ — функция $X : \Omega \to \mathbb{R}$, отображающая элементарные события в числа.

- **Дискретная случайная величина**: принимает счётное число значений
- **Непрерывная**: принимает значения на непрерывном интервале

### Математическое ожидание

Для дискретной $X$:

$$
E[X] = \sum_i x_i \cdot P(X = x_i)
$$

Для непрерывной $X$:

$$
E[X] = \int x \cdot f(x)\, dx
$$

**Свойства**: $E[aX + b] = a \cdot E[X] + b$; $E[X + Y] = E[X] + E[Y]$ (всегда!).

### Дисперсия

$$
\operatorname{Var}(X) = E\!\left[(X - E[X])^2\right] = E[X^2] - (E[X])^2
$$

Стандартное отклонение: $\sigma = \sqrt{\operatorname{Var}(X)}$.

```python
import numpy as np

# Кубик: дискретная равномерная случайная величина на {1,...,6}
values = np.arange(1, 7)
probabilities = np.ones(6) / 6

expectation = np.sum(values * probabilities)
variance = np.sum((values - expectation)**2 * probabilities)
std = np.sqrt(variance)

print(f"E[X] = {expectation:.2f}")  # 3.5
print(f"Var(X) = {variance:.4f}") # 2.9167
print(f"σ(X) = {std:.4f}")        # 1.7078
```

---

## 4. Ключевые распределения

### Нормальное (Гауссово) распределение

$$
f(x; \mu, \sigma^2) = \frac{1}{\sqrt{2\pi\sigma^2}} \exp\!\left(-\frac{(x-\mu)^2}{2\sigma^2}\right)
$$

Нормальное распределение $N(\mu, \sigma^2)$ — «колокол», симметричный вокруг $\mu$. Центральная предельная теорема объясняет его повсеместность: сумма независимых одинаково распределённых случайных величин с конечной дисперсией стремится к нормальному распределению.

```python
import numpy as np
import matplotlib.pyplot as plt

mu, sigma = 0, 1
samples = np.random.normal(mu, sigma, 10000)

# 68-95-99.7 правило:
print(f"P(|X-μ| < σ) ≈ {np.mean(np.abs(samples) < 1):.3f}")   # ≈ 0.683
print(f"P(|X-μ| < 2σ) ≈ {np.mean(np.abs(samples) < 2):.3f}")  # ≈ 0.955
print(f"P(|X-μ| < 3σ) ≈ {np.mean(np.abs(samples) < 3):.3f}")  # ≈ 0.997
```

**Применение в мониторинге**: если задержка сервиса нормально распределена, выброс более $3\sigma$ — сигнал аномалии. Но реальные задержки часто имеют «тяжёлые хвосты» (heavy-tailed distribution), что делает Z-score ненадёжным.

### Распределение Пуассона

Описывает количество событий за фиксированное время при фиксированной средней интенсивности:

$$
P(X = k; \lambda) = \frac{\lambda^k e^{-\lambda}}{k!}
$$

Применяется для моделирования: числа запросов в API за секунду, числа ошибок в строке кода, числа кликов по рекламе.

```python
from scipy.stats import poisson

lambda_rate = 5  # среднее число запросов в секунду

# Вероятность получить ровно 3 запроса
print(f"P(X=3) = {poisson.pmf(3, lambda_rate):.4f}")  # ≈ 0.1404

# Вероятность получить ≥ 10 запросов (перегрузка)
print(f"P(X≥10) = {1 - poisson.cdf(9, lambda_rate):.4f}")  # ≈ 0.0318
```

### Экспоненциальное распределение

Время между событиями Пуассона. Свойство отсутствия памяти: $P(X > s + t \mid X > s) = P(X > t)$ — «дожившие» не «стареют».

```python
from scipy.stats import expon

mean_time = 0.2  # среднее время между запросами (секунды)
rate = 1 / mean_time  # λ = 5 запросов/с

# Вероятность, что следующий запрос придёт позже 0.5с
print(f"P(T > 0.5) = {expon.sf(0.5, scale=mean_time):.4f}")  # ≈ 0.082
```

---

## 5. Закон больших чисел и центральная предельная теорема

### Закон больших чисел (ЗБЧ)

Для независимых одинаково распределённых $X_1, X_2, \ldots$ с $E[X] = \mu$:

$$
\bar{X}_n = \frac{X_1 + \ldots + X_n}{n} \to \mu \quad \text{при } n \to \infty
$$

**Практическое следствие**: чем больше выборка, тем точнее оценка среднего. Это обоснование статистической силы A/B-тестов.

### Центральная предельная теорема (ЦПТ)

Для ЗБЧ значение $\bar{X}_n$ сходится к $\mu$. ЦПТ описывает **распределение** этого значения:

$$
\frac{\sqrt{n}\,(\bar{X}_n - \mu)}{\sigma} \xrightarrow{d} N(0, 1)
$$

Стандартная ошибка среднего: $\mathrm{SE} = \sigma / \sqrt{n}$.

```python
import numpy as np

# Демонстрация ЦПТ
np.random.seed(42)
N_experiments = 10000
n_samples = 30

# Исходное: экспоненциальное распределение (сильно скошенное)
sample_means = np.array([
    np.random.exponential(scale=1, size=n_samples).mean()
    for _ in range(N_experiments)
])

print(f"Среднее выборочных средних: {sample_means.mean():.3f}")  # ≈ 1.0
print(f"Стд. откл. выборочных средних: {sample_means.std():.3f}")  # ≈ 1/√30 ≈ 0.183

# Распределение sample_means близко к нормальному!
from scipy.stats import normaltest
stat, p_value = normaltest(sample_means)
print(f"p-value теста нормальности: {p_value:.4f}")  # >> 0.05 — нормальное
```

---

## 6. Статистические проверки гипотез

### Концепция p-value

Нулевая гипотеза $H_0$ — «ничего не изменилось» (нет эффекта).

p-value — вероятность наблюдать данные, настолько же или более экстремальные, **если $H_0$ верна**.

Если $p < \alpha$ (обычно $0.05$), отвергаем $H_0$.

**Важно**: p-value — НЕ вероятность того, что $H_0$ верна.

### Z-тест и t-тест

```python
from scipy import stats
import numpy as np

# A/B-тест: сравниваем конверсию двух версий сайта
np.random.seed(42)

# Группа A: конверсия 10%
n_a = 1000
conversions_a = np.random.binomial(1, 0.10, n_a)

# Группа B: конверсия 12%
n_b = 1000
conversions_b = np.random.binomial(1, 0.12, n_b)

# Двухвыборочный z-тест для пропорций
p_a = conversions_a.mean()
p_b = conversions_b.mean()
p_pooled = (conversions_a.sum() + conversions_b.sum()) / (n_a + n_b)

se = np.sqrt(p_pooled * (1 - p_pooled) * (1/n_a + 1/n_b))
z = (p_b - p_a) / se

from scipy.stats import norm
p_value = 2 * (1 - norm.cdf(abs(z)))  # двусторонний

print(f"Конверсия A: {p_a:.3f}")
print(f"Конверсия B: {p_b:.3f}")
print(f"Z-статистика: {z:.3f}")
print(f"p-value: {p_value:.4f}")
print(f"Статистически значимо (α=0.05): {p_value < 0.05}")
```

### Множественные сравнения

Если проверять 20 гипотез при $\alpha = 0.05$, ожидается в среднем 1 ложноположительный результат. Поправки:

- **Бонферрони**: $\alpha_{\text{new}} = \alpha / n$ (консервативная)
- **Бенжамини–Хохберг**: FDR-контроль (более мощная)

```python
from statsmodels.stats.multitest import multipletests

# p-values для 20 гипотез
p_values = [0.001, 0.02, 0.04, 0.08, 0.15, 0.3, 0.5,
            0.01, 0.03, 0.06, 0.1, 0.2, 0.4, 0.6, 0.8,
            0.002, 0.025, 0.07, 0.12, 0.9]

reject, p_corrected, _, _ = multipletests(p_values, method='fdr_bh')
print(f"Гипотезы, отвергнутые после FDR-коррекции: {reject.sum()}")
```

---

## 7. Вероятность и хеш-таблицы

### Парадокс дней рождений

Вероятность, что среди $n$ человек есть двое с одинаковым днём рождения:

$$
P(\exists\,\text{совпадение}) = 1 - \frac{365!}{(365-n)! \cdot 365^n}
$$

При $n = 23$ эта вероятность уже превышает 50%!

```python
def birthday_collision_prob(n, d=365):
    """Вероятность коллизии при n элементах и d возможных значениях"""
    prob_no_collision = 1.0
    for i in range(n):
        prob_no_collision *= (d - i) / d
    return 1 - prob_no_collision

print(f"n=23: {birthday_collision_prob(23):.3f}")  # 0.507
print(f"n=50: {birthday_collision_prob(50):.3f}")  # 0.970
```

Этот парадокс напрямую применим к хеш-таблицам: с $n = O(\sqrt{m})$ элементами в хеш-таблице размера $m$ коллизия **ожидаема**. Это также основа хеш-атак (birthday attack) в криптографии.

### Ожидаемое время до коллизии

Для хеш-таблицы размера $m$, при равномерном распределении хешей, ожидаемое число вставок до первой коллизии $\approx \sqrt{\pi m / 2}$.

---

## 8. Дисперсия, ковариация и корреляция

**Ковариация** двух случайных величин:

$$
\operatorname{Cov}(X, Y) = E\!\left[(X - E[X])(Y - E[Y])\right] = E[XY] - E[X] \cdot E[Y]
$$

**Корреляция Пирсона**: нормированная ковариация:

$$
\rho(X, Y) = \frac{\operatorname{Cov}(X, Y)}{\sigma_X \cdot \sigma_Y} \in [-1, 1]
$$

```python
import numpy as np

np.random.seed(42)
n = 1000

# Сильная положительная корреляция
x = np.random.normal(0, 1, n)
y = 0.8 * x + 0.6 * np.random.normal(0, 1, n)
print(f"Корреляция: {np.corrcoef(x, y)[0,1]:.3f}")  # ≈ 0.8

# Важно: корреляция ≠ причинно-следственная связь!
# Число выпущенных фильмов Николаса Кейджа коррелирует
# с числом утоплений в бассейнах в США — spurious correlation
```

### Матрица ковариаций

Для многомерного вектора $X = (X_1, \ldots, X_n)$ матрица ковариаций $\Sigma$, где $\Sigma_{ij} = \operatorname{Cov}(X_i, X_j)$. Это центральный объект в PCA, многомерном нормальном распределении и гауссовских процессах.

---

## 9. Статистические распределения в мониторинге систем

### Распределение времён отклика

Реальные задержки серверов обычно имеют **лог-нормальное** распределение (если $\ln(X) \sim N(\mu, \sigma^2)$) или **распределение Парето** с тяжёлым хвостом.

Именно поэтому среднее значение задержки (P50) существенно занижает проблему: P99 может быть в 10–100 раз выше.

```python
import numpy as np

np.random.seed(42)
# Симуляция времён отклика (мс) с тяжёлым хвостом
latencies = np.concatenate([
    np.random.exponential(10, 9900),   # 99% быстрых запросов
    np.random.exponential(200, 100)    # 1% медленных запросов
])

percentiles = [50, 90, 95, 99, 99.9]
for p in percentiles:
    print(f"P{p}: {np.percentile(latencies, p):.1f} мс")

# P50: ~7 мс (хорошо!)
# P99: ~150 мс (на два порядка хуже среднего)
# P99.9: ~400 мс (ещё хуже)
```

---

## 10. Вероятность в машинном обучении

Машинное обучение с вероятностной точки зрения — это оценка распределения $P(y \mid x)$ по обучающим данным.

### Максимизация правдоподобия

**Правдоподобие** (likelihood) — вероятность наблюдения обучающих данных при данных параметрах модели:

$$
L(\theta) = P(D \mid \theta) = \prod_i P(x_i \mid \theta)
$$

Максимизируем логарифм правдоподобия (для удобства):

```python
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import norm

# Данные: наблюдения из N(μ, 1)
np.random.seed(42)
true_mu = 3.0
data = np.random.normal(true_mu, 1.0, 100)

# Оценка максимального правдоподобия для μ при известном σ=1
def neg_log_likelihood(mu):
    return -np.sum(norm.logpdf(data, mu, 1.0))

result = minimize_scalar(neg_log_likelihood, bounds=(-10, 10), method='bounded')
print(f"Оценка MLE μ: {result.x:.4f}")  # ≈ 3.0
print(f"Выборочное среднее: {data.mean():.4f}")  # то же самое!
```

### KL-дивергенция и кросс-энтропия

KL-дивергенция — мера «расстояния» между распределениями:

$$
\operatorname{KL}(P \,\|\, Q) = \sum_x P(x) \log \frac{P(x)}{Q(x)}
$$

Кросс-энтропия — функция потерь в классификаторах:

$$
H(P, Q) = -\sum_x P(x) \log Q(x) = H(P) + \operatorname{KL}(P \,\|\, Q)
$$

Минимизация кросс-энтропийных потерь = максимизация правдоподобия.

```python
import numpy as np

def cross_entropy_loss(y_true, y_pred):
    """
    y_true: истинные метки (one-hot)
    y_pred: предсказанные вероятности (после softmax)
    """
    eps = 1e-12
    return -np.mean(np.sum(y_true * np.log(y_pred + eps), axis=1))

# Хорошее предсказание
y_true = np.array([[1, 0, 0], [0, 1, 0]])
y_pred_good = np.array([[0.9, 0.05, 0.05], [0.05, 0.9, 0.05]])
print(f"Хорошее предсказание: {cross_entropy_loss(y_true, y_pred_good):.4f}")  # ≈ 0.11

# Плохое предсказание
y_pred_bad = np.array([[0.1, 0.8, 0.1], [0.6, 0.2, 0.2]])
print(f"Плохое предсказание: {cross_entropy_loss(y_true, y_pred_bad):.4f}")  # >> 1
```

---

## Заключение

Теория вероятностей и статистика критически важны для разработчика в следующих областях:

- **A/B-тесты**: без правильного статистического анализа результаты бессмысленны
- **Мониторинг**: понимание распределений задержек позволяет правильно ставить алерты
- **Хеш-таблицы и криптография**: парадокс дней рождений определяет безопасность
- **Машинное обучение**: вся теория ML основана на вероятностном мышлении
- **Байесовские системы**: спам-фильтры, рекомендательные системы

Ключевой навык — мыслить не отдельными числами, а распределениями. «Среднее время отклика 50 мс» — плохая метрика. «P95 = 100 мс, P99 = 500 мс» — информативная.

---

## Литература и источники

1. Feller, W. (1968). *An Introduction to Probability Theory and Its Applications* (3rd ed.). Wiley. — Классика вероятностной теории.

2. Wasserman, L. (2004). *All of Statistics: A Concise Course in Statistical Inference*. Springer. — Доступно онлайн: https://link.springer.com/book/10.1007/978-0-387-21736-9

3. Bishop, C. M. (2006). *Pattern Recognition and Machine Learning*. Springer. — Вероятностный подход к ML.

4. Gelman, A., et al. (2013). *Bayesian Data Analysis* (3rd ed.). CRC Press. — Байесовский подход. Доступно онлайн: http://www.stat.columbia.edu/~gelman/book/

5. Evans, M., & Rosenthal, J. S. (2010). *Probability and Statistics: The Science of Uncertainty* (2nd ed.). Freeman. Доступно: https://www.utstat.toronto.edu/mikevans/jeffrosenthal/

6. Kohavi, R., Tang, D., & Xu, Y. (2020). *Trustworthy Online Controlled Experiments: A Practical Guide to A/B Testing*. Cambridge University Press. — A/B-тесты в production.

7. Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly. Глава о мониторинге и метриках.
