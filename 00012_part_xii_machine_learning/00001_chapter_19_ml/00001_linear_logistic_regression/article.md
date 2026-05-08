# Линейная и логистическая регрессия: базовые модели, объясняющие 80% задач

Начинающие в машинном обучении часто спешат изучить нейросети и трансформеры. Но знание линейной и логистической регрессии — фундамент, без которого продвинутые методы не имеют смысла. Эти простые модели интерпретируемы, быстры, и часто дают конкурентоспособные результаты. Более того, понимание их математики — прямой путь к пониманию нейросетей.

## Линейная регрессия

### Задача и гипотеза

Линейная регрессия решает задачу **регрессии**: предсказать вещественное число по набору признаков.

Пример: предсказать цену квартиры по площади, количеству комнат, расстоянию от центра.

Гипотеза (модель):

```
ŷ = θ₀ + θ₁x₁ + θ₂x₂ + ... + θₙxₙ

В матричной форме:
ŷ = Xθ

где X — матрица признаков (n_samples × n_features+1)
    θ — вектор параметров (n_features+1)
    x₀ = 1 (для bias term θ₀)
```

### MSE Loss: функция потерь

Наиболее распространённая функция потерь — Mean Squared Error (MSE):

```
J(θ) = (1/2m) Σᵢ (ŷᵢ - yᵢ)²
     = (1/2m) ||Xθ - y||²

m — количество примеров
yᵢ — истинное значение
ŷᵢ — предсказанное значение
```

Коэффициент 1/2 для удобства при дифференцировании.

### Нормальное уравнение: аналитическое решение

Для линейной регрессии существует точное аналитическое решение:

```
∂J/∂θ = 0
(1/m) Xᵀ(Xθ - y) = 0
XᵀXθ = Xᵀy
θ = (XᵀX)⁻¹ Xᵀy
```

```python
import numpy as np

def normal_equation(X, y):
    """Аналитическое решение линейной регрессии"""
    # Добавляем столбец единиц для bias
    X_b = np.column_stack([np.ones(len(X)), X])
    
    # θ = (XᵀX)⁻¹ Xᵀy
    theta = np.linalg.pinv(X_b.T @ X_b) @ X_b.T @ y
    return theta

# Пример
X = np.array([[50], [75], [100], [150]])  # площадь м²
y = np.array([5000, 7000, 9000, 13000])   # цена тыс. руб.

theta = normal_equation(X, y)
print(f"bias={theta[0]:.0f}, coef={theta[1]:.0f}")
# bias=1000, coef=80 → цена = 1000 + 80 × площадь
```

Нормальное уравнение: O(n³) из-за обращения матрицы. При большом числе признаков (n > 10000) — слишком медленно. Тогда используют градиентный спуск.

### Геометрическая интерпретация

```
Регрессия в пространстве:
- Если 1 признак: линия в 2D
- Если 2 признака: плоскость в 3D
- Если n признаков: гиперплоскость в (n+1)-мерном пространстве

Линейная регрессия находит гиперплоскость, 
минимизирующую среднеквадратичное отклонение точек.
```

### Градиентный спуск для линейной регрессии

```python
def gradient_descent_linear(X, y, learning_rate=0.01, n_iterations=1000):
    """Градиентный спуск для линейной регрессии"""
    m = len(y)
    X_b = np.column_stack([np.ones(m), X])
    theta = np.zeros(X_b.shape[1])
    
    history = []
    for i in range(n_iterations):
        # Предсказание
        y_pred = X_b @ theta
        
        # Ошибка
        error = y_pred - y
        
        # Градиент: ∂J/∂θ = (1/m) Xᵀ(Xθ - y)
        gradient = (1/m) * X_b.T @ error
        
        # Обновление параметров
        theta -= learning_rate * gradient
        
        # Сохраняем loss
        loss = (1/(2*m)) * np.sum(error**2)
        history.append(loss)
    
    return theta, history
```

### Мультиколлинеарность

Проблема: если признаки сильно коррелируют между собой, матрица XᵀX почти вырожденная → нестабильные веса.

```python
import pandas as pd
import seaborn as sns

# Диагностика мультиколлинеарности через корреляционную матрицу
df = pd.DataFrame({'x1': X[:,0], 'x2': X[:,1], 'y': y})
correlation = df.corr()
sns.heatmap(correlation, annot=True)

# Variance Inflation Factor (VIF)
from statsmodels.stats.outliers_influence import variance_inflation_factor
vif = pd.DataFrame()
vif["feature"] = feature_names
vif["VIF"] = [variance_inflation_factor(X, i) for i in range(X.shape[1])]
# VIF > 5-10 указывает на проблему
```

### Ridge и Lasso регуляризация

Регуляризация — добавление штрафа за большие веса для борьбы с переобучением.

**Ridge (L2 регуляризация):**
```
J(θ) = MSE + α × Σ θᵢ²

Решение: θ = (XᵀX + αI)⁻¹ Xᵀy

Свойство: все веса уменьшаются, но не обнуляются
```

**Lasso (L1 регуляризация):**
```
J(θ) = MSE + α × Σ |θᵢ|

Свойство: некоторые веса обнуляются → автоматический отбор признаков!
```

```python
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# Нормализация данных (важно для регуляризации)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2)

# Обычная линейная регрессия
lr = LinearRegression()
lr.fit(X_train, y_train)
print("Linear R²:", lr.score(X_test, y_test))

# Ridge регрессия
ridge = Ridge(alpha=1.0)
ridge.fit(X_train, y_train)
print("Ridge R²:", ridge.score(X_test, y_test))
print("Ridge coefs:", ridge.coef_)

# Lasso регрессия
lasso = Lasso(alpha=0.1)
lasso.fit(X_train, y_train)
print("Lasso R²:", lasso.score(X_test, y_test))
print("Lasso coefs (zeros = excluded features):", lasso.coef_)
```

## Логистическая регрессия

### Задача классификации

Логистическая регрессия решает задачу **бинарной классификации**: предсказать вероятность принадлежности к классу.

Несмотря на название "регрессия", это алгоритм классификации.

### Сигмоида

Ключевое отличие от линейной регрессии — нелинейная функция активации:

```
σ(z) = 1 / (1 + e^(-z))

Свойства:
- σ(z) ∈ (0, 1) — всегда вероятность!
- σ(0) = 0.5
- σ(z) → 1 при z → +∞
- σ(z) → 0 при z → -∞
- σ'(z) = σ(z)(1 - σ(z)) — удобная производная
```

```python
import numpy as np
import matplotlib.pyplot as plt

def sigmoid(z):
    return 1 / (1 + np.exp(-z))

# Гипотеза логистической регрессии
def predict_proba(X, theta):
    z = X @ theta
    return sigmoid(z)
```

### Интерпретация: log-odds

Логистическая регрессия моделирует **log-odds** (логит):

```
P(y=1 | x) = σ(θᵀx)

Это эквивалентно:
log(P(y=1)/P(y=0)) = θᵀx

Интерпретация коэффициента θᵢ:
При увеличении xᵢ на 1, log-odds изменяются на θᵢ
Odds ratio = e^θᵢ
```

```python
from sklearn.linear_model import LogisticRegression

model = LogisticRegression()
model.fit(X_train, y_train)

# Интерпретация коэффициентов
for feature, coef in zip(feature_names, model.coef_[0]):
    odds_ratio = np.exp(coef)
    print(f"{feature}: коэффициент={coef:.3f}, odds ratio={odds_ratio:.3f}")
    # odds ratio > 1: увеличивает вероятность класса 1
    # odds ratio < 1: уменьшает вероятность класса 1
```

### Binary Cross-Entropy Loss

Для классификации используется логарифмическая функция потерь (Binary Cross-Entropy / Log Loss):

```
J(θ) = -(1/m) Σᵢ [yᵢ log(ŷᵢ) + (1-yᵢ) log(1-ŷᵢ)]

Почему не MSE для классификации?
MSE с сигмоидой имеет много локальных минимумов.
Cross-entropy — выпуклая функция, единственный минимум.
```

```python
def binary_cross_entropy(y_true, y_pred):
    """Log Loss"""
    # Клипуем для численной стабильности
    y_pred = np.clip(y_pred, 1e-10, 1 - 1e-10)
    m = len(y_true)
    return -(1/m) * np.sum(
        y_true * np.log(y_pred) + 
        (1 - y_true) * np.log(1 - y_pred)
    )

# Градиент BCE = градиент MSE с сигмоидой (удобно!)
def gradient_logistic(X, y, theta):
    """∂J/∂θ для логистической регрессии"""
    m = len(y)
    y_pred = sigmoid(X @ theta)
    return (1/m) * X.T @ (y_pred - y)
```

### Softmax для мультиклассовой классификации

Для задач с более чем двумя классами используется softmax (обобщение сигмоиды):

```
softmax(z)ₖ = e^zₖ / Σⱼ e^zⱼ

Свойства:
- Все значения в (0, 1)
- Сумма = 1 (вероятности!)
- Большее z → большая вероятность
```

```python
def softmax(z):
    # Вычитаем max для численной стабильности
    z_shifted = z - np.max(z, axis=1, keepdims=True)
    exp_z = np.exp(z_shifted)
    return exp_z / np.sum(exp_z, axis=1, keepdims=True)

# sklearn: мультиклассовая логистическая регрессия
from sklearn.linear_model import LogisticRegression

# solver='lbfgs' поддерживает multinomial
model = LogisticRegression(multi_class='multinomial', solver='lbfgs')
model.fit(X_train, y_train)  # y_train содержит классы 0, 1, 2, ...

# Вероятности всех классов
probas = model.predict_proba(X_test)  # shape (n_samples, n_classes)
```

## ROC Curve и выбор порога

### Threshold и метрики

По умолчанию порог классификации = 0.5. Но иногда нужно его менять:

```python
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.metrics import roc_curve, auc

# Предсказания вероятностей
y_prob = model.predict_proba(X_test)[:, 1]

# При разных порогах:
for threshold in [0.3, 0.5, 0.7]:
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    
    print(f"Порог {threshold}: Precision={precision:.2f}, Recall={recall:.2f}")

# ROC Curve
fpr, tpr, thresholds = roc_curve(y_test, y_prob)
roc_auc = auc(fpr, tpr)

plt.plot(fpr, tpr, label=f'ROC curve (AUC = {roc_auc:.2f})')
plt.plot([0, 1], [0, 1], 'k--')  # random classifier
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Curve')
plt.legend()
```

**AUC (Area Under Curve)**: вероятность, что модель выше оценит случайный положительный пример, чем случайный отрицательный. AUC=0.5 — случайный, AUC=1.0 — идеальный.

### Когда менять порог

```
Медицинская диагностика рака:
  Цель: не пропустить больных (высокий Recall)
  Можно допустить ложные тревоги (ниже Precision)
  → Снизить порог (например, 0.3)

Фильтр спама:
  Цель: не отмечать важные письма как спам (высокий Precision)
  Можно пропустить часть спама (ниже Recall)
  → Повысить порог (например, 0.7)
```

## Feature Engineering и нормализация

### Нормализация признаков

```python
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler

# StandardScaler: (x - mean) / std
# Предполагает нормальное распределение
scaler = StandardScaler()
X_normalized = scaler.fit_transform(X_train)

# MinMaxScaler: (x - min) / (max - min) → [0, 1]
# Чувствителен к выбросам
scaler = MinMaxScaler()

# RobustScaler: (x - median) / IQR
# Устойчив к выбросам
scaler = RobustScaler()

# ВАЖНО: fit только на train, transform на test
X_train_scaled = scaler.fit_transform(X_train)  # fit + transform
X_test_scaled = scaler.transform(X_test)         # только transform!
```

### Полиномиальные признаки

Линейная модель не захватывает нелинейные зависимости. Добавление полиномиальных признаков позволяет моделировать кривые:

```python
from sklearn.preprocessing import PolynomialFeatures

# Добавляем признаки x1², x2², x1*x2
poly = PolynomialFeatures(degree=2, include_bias=False)
X_poly = poly.fit_transform(X)
# Если X имел 2 признака, теперь 5: [x1, x2, x1², x1*x2, x2²]

model = LinearRegression()
model.fit(X_poly, y)
```

## Полный sklearn Pipeline

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, GridSearchCV
from sklearn.datasets import load_breast_cancer

# Загрузка данных
data = load_breast_cancer()
X, y = data.data, data.target
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y)

# Pipeline: нормализация → логистическая регрессия
pipeline = Pipeline([
    ('scaler', StandardScaler()),
    ('classifier', LogisticRegression(max_iter=1000))
])

# Кросс-валидация (5 fold)
cv_scores = cross_val_score(pipeline, X_train, y_train, cv=5, scoring='roc_auc')
print(f"CV AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

# Подбор гиперпараметров
param_grid = {
    'classifier__C': [0.01, 0.1, 1.0, 10.0, 100.0],
    'classifier__penalty': ['l1', 'l2'],
    'classifier__solver': ['liblinear']
}

grid_search = GridSearchCV(pipeline, param_grid, cv=5, scoring='roc_auc')
grid_search.fit(X_train, y_train)

print(f"Best params: {grid_search.best_params_}")
print(f"Best CV AUC: {grid_search.best_score_:.3f}")

# Финальная оценка на test set
best_model = grid_search.best_estimator_
y_prob = best_model.predict_proba(X_test)[:, 1]
test_auc = roc_auc_score(y_test, y_prob)
print(f"Test AUC: {test_auc:.3f}")

# Отчёт
y_pred = best_model.predict(X_test)
print(classification_report(y_test, y_pred, target_names=data.target_names))
```

## Когда линейные модели достаточны

Линейные модели стоит рассмотреть первыми при:

1. **Интерпретируемость важна**: медицина, финансы, юриспруденция
2. **Мало данных**: глубокие модели переобучаются, линейные — нет
3. **Высокая размерность при малом числе примеров**: регрессия с регуляризацией эффективнее нейросетей
4. **Baseline**: всегда начинайте с простой модели — это нижняя граница для более сложных
5. **Признаки уже хорошо описывают данные**: инженерия признаков часть важнее выбора модели

## Итог

1. **Линейная регрессия** — гиперплоскость в пространстве признаков; MSE loss; нормальное уравнение или градиентный спуск
2. **Ridge/Lasso** — регуляризация для борьбы с переобучением и мультиколлинеарностью
3. **Логистическая регрессия** — sigmoid для бинарной классификации; cross-entropy loss
4. **Softmax** — обобщение на мультиклассовую задачу
5. **ROC/AUC** — оценка качества классификатора независимо от порога
6. **Нормализация признаков** — обязательна для регуляризованных и градиентных методов

## Литература

1. Bishop, C.M. (2006). *Pattern Recognition and Machine Learning*. Springer.

2. Hastie, T., Tibshirani, R., Friedman, J. (2009). *The Elements of Statistical Learning, 2nd Edition*. Springer. https://web.stanford.edu/~hastie/ElemStatLearn/

3. James, G., Witten, D., Hastie, T., Tibshirani, R. (2021). *An Introduction to Statistical Learning with Applications in Python*. Springer. https://www.statlearning.com/

4. Murphy, K.P. (2022). *Probabilistic Machine Learning: An Introduction*. MIT Press. https://probml.github.io/pml-book/

5. Géron, A. (2022). *Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow, 3rd Edition*. O'Reilly Media.

6. scikit-learn. *Linear Models documentation*. https://scikit-learn.org/stable/modules/linear_model.html

7. Tibshirani, R. (1996). *Regression Shrinkage and Selection via the Lasso*. Journal of the Royal Statistical Society, Series B, 58(1), 267-288.

8. Fawcett, T. (2006). *An Introduction to ROC Analysis*. Pattern Recognition Letters, 27(8), 861-874.
