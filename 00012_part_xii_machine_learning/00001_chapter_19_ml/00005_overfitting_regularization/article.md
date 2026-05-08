# Переобучение, регуляризация и кросс-валидация: как оценить модель честно

Представьте студента, который выучил ответы на вопросы прошлых экзаменов наизусть. На тренировочных данных — отличные результаты. На новом экзамене — провал. Это переобучение (overfitting). Борьба с ним — один из центральных вызовов машинного обучения, а честная оценка модели требует строгого протокола работы с данными.

## Bias-Variance Tradeoff

Ошибка модели раскладывается на три компоненты:

```
Ожидаемая ошибка = Bias² + Variance + Irreducible Noise

Bias (смещение): систематическая ошибка модели
  - Слишком простая модель не захватывает паттерны
  - Недообучение (underfitting)
  
Variance (дисперсия): чувствительность к тренировочным данным
  - Слишком сложная модель "запоминает" шум
  - Переобучение (overfitting)
  
Irreducible Noise: шум в данных, снизить нельзя
```

```python
import numpy as np
import matplotlib.pyplot as plt
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline

# Генерируем данные с шумом
np.random.seed(42)
X = np.linspace(0, 2*np.pi, 30)
y = np.sin(X) + np.random.normal(0, 0.3, len(X))

# Три модели разной сложности
degrees = [1, 4, 15]
plt.figure(figsize=(15, 4))

for i, degree in enumerate(degrees):
    model = Pipeline([
        ('poly', PolynomialFeatures(degree)),
        ('lr', LinearRegression())
    ])
    model.fit(X.reshape(-1, 1), y)
    
    X_test = np.linspace(0, 2*np.pi, 300).reshape(-1, 1)
    y_pred = model.predict(X_test)
    
    plt.subplot(1, 3, i+1)
    plt.scatter(X, y, label='Данные')
    plt.plot(X_test, y_pred, 'r-', label=f'Степень {degree}')
    plt.plot(X_test, np.sin(X_test), 'g--', label='Истина')
    
    if degree == 1:
        plt.title('Недообучение\n(High Bias, Low Variance)')
    elif degree == 4:
        plt.title('Оптимально\n(Balanced)')
    else:
        plt.title('Переобучение\n(Low Bias, High Variance)')
    plt.legend()
```

### Кривые обучения

Кривые обучения — первый инструмент диагностики:

```python
from sklearn.model_selection import learning_curve

def plot_learning_curve(model, X, y, cv=5):
    train_sizes, train_scores, val_scores = learning_curve(
        model, X, y,
        train_sizes=np.linspace(0.1, 1.0, 10),
        cv=cv,
        scoring='neg_mean_squared_error',
        n_jobs=-1
    )
    
    # Среднее и стандартное отклонение
    train_mean = -train_scores.mean(axis=1)
    train_std = train_scores.std(axis=1)
    val_mean = -val_scores.mean(axis=1)
    val_std = val_scores.std(axis=1)
    
    plt.fill_between(train_sizes, train_mean-train_std, train_mean+train_std, alpha=0.2)
    plt.plot(train_sizes, train_mean, label='Train MSE')
    
    plt.fill_between(train_sizes, val_mean-val_std, val_mean+val_std, alpha=0.2)
    plt.plot(train_sizes, val_mean, label='Validation MSE')
    
    plt.xlabel('Training set size')
    plt.ylabel('MSE')
    plt.legend()
    
# Диагностика по кривым:
# High train error + High val error → Underfitting (нужна сложнее модель)
# Low train error + High val error  → Overfitting (нужна регуляризация/больше данных)
# Low train error + Low val error   → Хорошо!
```

## Train/Val/Test Split: почему три множества

```
Все данные разделяются на три части:

Training set (60-80%):
  Используется для обучения модели
  
Validation set (10-20%):
  Используется для выбора гиперпараметров
  (learning rate, архитектура, регуляризация)
  
Test set (10-20%):
  Используется ТОЛЬКО для финальной оценки
  Трогается только ОДИН РАЗ
```

**Критический принцип**: тестовый набор должен оставаться нетронутым до финального шага. Любое решение, принятое с учётом тестовых данных (даже косвенно), загрязняет оценку.

```python
from sklearn.model_selection import train_test_split

X, y = load_data()

# Шаг 1: Отделяем test set
X_trainval, X_test, y_trainval, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y  # stratify для классификации
)

# Шаг 2: Делим на train и val
X_train, X_val, y_train, y_val = train_test_split(
    X_trainval, y_trainval, test_size=0.25, random_state=42
    # 0.25 × 0.8 = 0.2 → итого 20% на val
)

print(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

# Шаг 3: Обучаем и настраиваем гиперпараметры, используя только train и val
# Шаг 4: Финальная оценка ТОЛЬКО на test set
```

### Data Leakage: классические ошибки

```python
# ОШИБКА 1: Нормализация до разделения на train/test
scaler = StandardScaler()
X_normalized = scaler.fit_transform(X)  # Использует mean/std из test данных!
X_train, X_test = train_test_split(X_normalized, test_size=0.2)

# ПРАВИЛЬНО:
X_train, X_test = train_test_split(X, test_size=0.2)
scaler = StandardScaler()
X_train_normalized = scaler.fit_transform(X_train)  # fit только на train!
X_test_normalized = scaler.transform(X_test)         # только transform!

# ОШИБКА 2: Feature selection до разделения
selector = SelectKBest(k=10)
X_selected = selector.fit_transform(X, y)  # Смотрит в test labels!
X_train, X_test = train_test_split(X_selected, ...)

# ОШИБКА 3: Одинаковый человек в train и test (дублирующиеся записи)
# Проверяйте дубликаты ДО разделения
```

## K-Fold Cross-Validation

K-fold CV — более надёжная оценка, чем одно разделение:

```python
from sklearn.model_selection import KFold, cross_val_score

kfold = KFold(n_splits=5, shuffle=True, random_state=42)

# Для каждого fold:
# - 80% данных для обучения
# - 20% для валидации
# Всего 5 различных fold'ов, каждый кусочек данных был в val один раз

scores = cross_val_score(
    model, X_trainval, y_trainval,
    cv=kfold,
    scoring='roc_auc'
)
print(f"CV AUC: {scores.mean():.3f} ± {scores.std():.3f}")
```

### Stratified K-Fold

Для несбалансированных классов нужно, чтобы каждый fold сохранял пропорцию классов:

```python
from sklearn.model_selection import StratifiedKFold

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
    X_fold_train, X_fold_val = X[train_idx], X[val_idx]
    y_fold_train, y_fold_val = y[train_idx], y[val_idx]
    
    # Каждый fold содержит ~одинаковое соотношение классов
    print(f"Fold {fold+1}: val class distribution: {np.bincount(y_fold_val)}")
```

### Time Series Split: для временных рядов

Для временных рядов нельзя использовать случайное разделение — будущее не должно использоваться для предсказания прошлого:

```python
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(n_splits=5)

# Схема:
# Fold 1: Train=[1..100],  Val=[101..120]
# Fold 2: Train=[1..120],  Val=[121..140]
# Fold 3: Train=[1..140],  Val=[141..160]
# ...

for train_idx, val_idx in tscv.split(X):
    X_train, X_val = X[train_idx], X[val_idx]
    y_train, y_val = y[train_idx], y[val_idx]
    model.fit(X_train, y_train)
    print(f"Val score: {model.score(X_val, y_val):.3f}")
```

## L1 и L2 регуляризация

### L2 (Ridge): штраф за большие веса

```
J_ridge(θ) = J(θ) + α × Σ θᵢ²
```

Эффект: все веса уменьшаются пропорционально, но не обнуляются. Математически: добавляет $\alpha I$ к $X^\top X$ перед инверсией, делая её стабильной.

```python
from sklearn.linear_model import Ridge, RidgeCV
import numpy as np

# RidgeCV: автоматический подбор α через кросс-валидацию
alphas = np.logspace(-3, 3, 100)
ridge_cv = RidgeCV(alphas=alphas, cv=5, scoring='neg_mean_squared_error')
ridge_cv.fit(X_train, y_train)
print(f"Best alpha: {ridge_cv.alpha_}")

# Визуализация: влияние alpha на веса
ridge_coefs = []
for alpha in alphas:
    ridge = Ridge(alpha=alpha)
    ridge.fit(X_train, y_train)
    ridge_coefs.append(ridge.coef_)

plt.semilogx(alphas, ridge_coefs)
plt.xlabel('Alpha (regularization strength)')
plt.ylabel('Coefficients')
plt.title('Ridge coefficients vs regularization')
```

### L1 (Lasso): автоматический отбор признаков

```
J_lasso(θ) = J(θ) + α × Σ |θᵢ|
```

Эффект: некоторые веса обнуляются точно! Геометрически: контур L1 нормы — "бриллиант" с острыми углами, и оптимум часто попадает в угол (где один из $\theta_i = 0$).

```python
from sklearn.linear_model import Lasso, LassoCV

lasso_cv = LassoCV(alphas=alphas, cv=5, max_iter=10000)
lasso_cv.fit(X_train, y_train)
print(f"Best alpha: {lasso_cv.alpha_}")

lasso = Lasso(alpha=lasso_cv.alpha_)
lasso.fit(X_train, y_train)

# Смотрим на обнулённые признаки
zero_features = np.sum(np.abs(lasso.coef_) < 1e-4)
print(f"Features set to zero: {zero_features}/{len(lasso.coef_)}")
print("Selected features:", feature_names[lasso.coef_ != 0])
```

### Elastic Net: комбинация L1 и L2

```
J_elastic(θ) = J(θ) + α × [ρ × Σ|θᵢ| + (1-ρ)/2 × Σθᵢ²]

ρ — l1_ratio: соотношение L1 и L2
```

Elastic Net полезен при мультиколлинеарности: Lasso выбирает один признак из коррелирующих, Elastic Net может выбрать несколько.

## Dropout

Dropout — случайное "отключение" нейронов во время обучения:

```python
import torch.nn as nn

class RegularizedNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(784, 512)
        self.dropout1 = nn.Dropout(p=0.5)  # 50% нейронов отключаются
        self.fc2 = nn.Linear(512, 256)
        self.dropout2 = nn.Dropout(p=0.3)
        self.fc3 = nn.Linear(256, 10)
    
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = self.dropout1(x)  # Только во время обучения!
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        return self.fc3(x)

# При model.eval(): dropout отключается автоматически
model.eval()  # Inference: нет dropout
with torch.no_grad():
    y_pred = model(X_test)

model.train()  # Обучение: dropout включён
```

Интуиция Dropout: каждый нейрон вынужден научиться работать независимо, т.к. не может рассчитывать на другие. Это эквивалентно обучению ансамбля из 2^N моделей.

## BatchNorm как регуляризатор

BatchNorm не задумывался как регуляризатор, но действует как один:

```python
# BatchNorm добавляет шум: mean/std вычисляются по батчу, 
# что является стохастическим приближением к population stats

# В inference: используются running mean/std (из обучения)
# В training: используются батч mean/std (добавляет шум)

# Это делает BatchNorm несовместимым с очень маленькими батчами
# Для маленьких батчей используйте LayerNorm или GroupNorm
```

## Early Stopping

```python
from torch.utils.tensorboard import SummaryWriter

class EarlyStopping:
    def __init__(self, patience=10, min_delta=1e-4):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_val_loss = float('inf')
    
    def __call__(self, val_loss, model):
        if val_loss < self.best_val_loss - self.min_delta:
            self.best_val_loss = val_loss
            self.counter = 0
            # Сохраняем лучшую модель
            torch.save(model.state_dict(), 'best_model.pth')
        else:
            self.counter += 1
            if self.counter >= self.patience:
                return True  # Остановить!
        return False

early_stopping = EarlyStopping(patience=10)

for epoch in range(1000):
    model.train()
    train_loss = train_epoch(model, train_loader)
    
    model.eval()
    val_loss = evaluate(model, val_loader)
    
    if early_stopping(val_loss, model):
        print(f"Early stopping at epoch {epoch}")
        break

# Загружаем лучшую модель
model.load_state_dict(torch.load('best_model.pth'))
```

## Data Augmentation

Искусственное расширение датасета — эффективная альтернатива регуляризации:

```python
from torchvision import transforms

# Для изображений
train_transform = transforms.Compose([
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.RandomRotation(10),
    transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
    transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                         std=[0.229, 0.224, 0.225])
])

# Для текста (через nlpaug или albumentation)
import nlpaug.augmenter.word as naw
aug = naw.SynonymAug(aug_src='wordnet', lang='eng')
augmented_text = aug.augment("Quick brown fox")

# Для временных рядов
def time_warp(x, sigma=0.2):
    """Случайное ускорение/замедление временного ряда"""
    # ... деформация
```

## Ансамблевые методы

### Bagging: Bootstrap Aggregating

```python
from sklearn.ensemble import BaggingClassifier, RandomForestClassifier

# Random Forest = Bagging + случайный выбор признаков
rf = RandomForestClassifier(
    n_estimators=100,
    max_features='sqrt',  # Случайный subset признаков
    max_depth=None,
    bootstrap=True,       # Выборки с возвращением
    random_state=42
)
rf.fit(X_train, y_train)
print("Feature importances:", rf.feature_importances_)
```

### Boosting: GBM и XGBoost

```python
import xgboost as xgb

model = xgb.XGBClassifier(
    n_estimators=500,
    learning_rate=0.05,
    max_depth=6,
    subsample=0.8,        # Строить каждое дерево на 80% данных
    colsample_bytree=0.8, # Использовать 80% признаков
    reg_alpha=0.1,        # L1 регуляризация листьев
    reg_lambda=1.0,       # L2 регуляризация листьев
    early_stopping_rounds=50,
    eval_metric='auc'
)

model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    verbose=50
)
```

## Итог

Правильная оценка модели и борьба с переобучением — основа надёжного ML:

1. **Bias-Variance**: простые модели страдают от bias, сложные — от variance
2. **Train/Val/Test**: три множества для обучения, настройки, оценки; test — только финально
3. **Data Leakage**: нормализация и feature selection — только на train!
4. **K-Fold CV**: надёжнее одного split; Stratified для несбалансированных классов; TimeSeriesSplit для рядов
5. **L1/L2**: Ridge сжимает веса, Lasso обнуляет; Elastic Net комбинирует
6. **Dropout**: ансамблевый эффект через случайное отключение нейронов
7. **Early Stopping**: останавливаемся при росте val loss
8. **Data Augmentation**: синтетическое расширение датасета

## Литература

1. Geman, S., Bienenstock, E., Doursat, R. (1992). *Neural Networks and the Bias/Variance Dilemma*. Neural Computation, 4(1), 1-58.

2. Hastie, T., Tibshirani, R., Friedman, J. (2009). *The Elements of Statistical Learning*. Springer. https://web.stanford.edu/~hastie/ElemStatLearn/

3. Srivastava, N., et al. (2014). *Dropout: A Simple Way to Prevent Neural Networks from Overfitting*. JMLR, 15(56), 1929-1958.

4. Ioffe, S., Szegedy, C. (2015). *Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift*. ICML 2015. https://arxiv.org/abs/1502.03167

5. Tibshirani, R. (1996). *Regression Shrinkage and Selection via the Lasso*. JRSSB.

6. Zou, H., Hastie, T. (2005). *Regularization and Variable Selection via the Elastic Net*. JRSSB, 67(2).

7. Breiman, L. (2001). *Random Forests*. Machine Learning, 45(1), 5-32.

8. Chen, T., Guestrin, C. (2016). *XGBoost: A Scalable Tree Boosting System*. KDD 2016.

9. Prechelt, L. (1998). *Early Stopping — But When?* In Neural Networks: Tricks of the Trade.

10. Shorten, C., Khoshgoftaar, T.M. (2019). *A Survey on Image Data Augmentation for Deep Learning*. Journal of Big Data.
