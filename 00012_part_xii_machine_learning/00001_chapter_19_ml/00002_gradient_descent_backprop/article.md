# Градиентный спуск и обратное распространение ошибки: как нейросети учатся

Нейросеть — это просто функция с миллионами параметров. Обучение — это нахождение таких значений параметров, при которых функция потерь минимальна. Но как найти минимум в миллиардномерном пространстве? Ответ: градиентный спуск, управляемый обратным распространением ошибки. Эта статья демистифицирует процесс "обучения" нейросетей от интуиции до конкретного кода.

## Функция потерь как ландшафт

Представьте функцию потерь J(θ) как горный ландшафт, где оси — это параметры модели θ, а высота — значение потерь. Наша цель — найти долину (глобальный или хороший локальный минимум).

Для двух параметров это буквально трёхмерная поверхность. Для миллиарда параметров — миллиардномерное пространство, визуализировать которое невозможно, но математика остаётся той же.

```python
import numpy as np
import matplotlib.pyplot as plt

# Простая квадратичная функция потерь (для иллюстрации)
def loss(theta0, theta1, X, y):
    m = len(y)
    y_pred = theta0 + theta1 * X
    return (1/(2*m)) * np.sum((y_pred - y)**2)

# Визуализация поверхности потерь
theta0_range = np.linspace(-10, 10, 100)
theta1_range = np.linspace(-10, 10, 100)
T0, T1 = np.meshgrid(theta0_range, theta1_range)

X = np.array([1, 2, 3, 4, 5])
y = np.array([2, 4, 5, 4, 5])

Z = np.vectorize(lambda t0, t1: loss(t0, t1, X, y))(T0, T1)

fig = plt.figure(figsize=(12, 5))
ax1 = fig.add_subplot(121, projection='3d')
ax1.plot_surface(T0, T1, Z, cmap='viridis', alpha=0.8)
ax1.set_xlabel('θ₀'), ax1.set_ylabel('θ₁'), ax1.set_zlabel('J(θ)')
```

## Градиент: направление наибольшего роста

Градиент функции потерь ∇J(θ) — это вектор частных производных по каждому параметру:

```
∇J(θ) = [∂J/∂θ₀, ∂J/∂θ₁, ..., ∂J/∂θₙ]
```

Ключевое свойство: градиент указывает в направлении **наибольшего роста** функции. Значит, чтобы двигаться к минимуму, нужно идти в противоположном направлении.

```
Обновление параметров:
θ = θ - α × ∇J(θ)

α — learning rate (скорость обучения)
```

## Виды градиентного спуска

### Batch Gradient Descent

Вычисляет градиент по **всем** обучающим примерам:

```python
def batch_gradient_descent(X, y, learning_rate=0.01, n_epochs=1000):
    m, n = X.shape
    theta = np.zeros(n)
    
    for epoch in range(n_epochs):
        # Градиент по всем примерам
        y_pred = X @ theta
        gradient = (1/m) * X.T @ (y_pred - y)
        theta -= learning_rate * gradient
    
    return theta
```

Плюсы: стабильные обновления, гарантированная сходимость для выпуклых функций.
Минусы: медленно для больших датасетов (вычислять градиент по 1M примеров на каждом шаге!).

### Stochastic Gradient Descent (SGD)

Вычисляет градиент по **одному** примеру:

```python
def sgd(X, y, learning_rate=0.01, n_epochs=50):
    m, n = X.shape
    theta = np.zeros(n)
    
    for epoch in range(n_epochs):
        # Перемешиваем данные
        indices = np.random.permutation(m)
        
        for i in indices:
            xi = X[i:i+1]  # (1, n)
            yi = y[i:i+1]  # (1,)
            
            y_pred = xi @ theta
            gradient = xi.T @ (y_pred - yi)  # Градиент по 1 примеру
            theta -= learning_rate * gradient
    
    return theta
```

Плюсы: быстро, может выйти из локальных минимумов (шум помогает!).
Минусы: нестабильная траектория, сложно выбрать learning rate.

### Mini-batch Gradient Descent

Компромисс — градиент по мини-пакету (32, 64, 128, 256 примеров):

```python
def mini_batch_gd(X, y, batch_size=32, learning_rate=0.01, n_epochs=100):
    m, n = X.shape
    theta = np.zeros(n)
    
    for epoch in range(n_epochs):
        indices = np.random.permutation(m)
        X_shuffled, y_shuffled = X[indices], y[indices]
        
        for i in range(0, m, batch_size):
            X_batch = X_shuffled[i:i+batch_size]
            y_batch = y_shuffled[i:i+batch_size]
            
            y_pred = X_batch @ theta
            gradient = (1/len(y_batch)) * X_batch.T @ (y_pred - y_batch)
            theta -= learning_rate * gradient
    
    return theta
```

Размер батча влияет на обобщение: меньшие батчи дают лучшую обобщающую способность (больше шума → неявная регуляризация), но более нестабильны.

## Проблемы SGD и методы их решения

### Seddle Points (сёдельные точки)

В высокоразмерных пространствах "сёдла" (точки с нулевым градиентом, но не минимум) гораздо чаще, чем локальные минимумы. Однако на практике они не такая большая проблема, как думали раньше.

### Ravines (ущелья)

Поверхность потерь часто имеет форму ущелья: быстро изменяется в одном направлении, медленно — в другом. SGD "прыгает" по стенкам и медленно продвигается вперёд.

### Momentum: ускорение через инерцию

```python
def sgd_with_momentum(X, y, lr=0.01, momentum=0.9, n_epochs=100):
    """Polyak Momentum"""
    theta = np.zeros(X.shape[1])
    velocity = np.zeros_like(theta)
    
    for epoch in range(n_epochs):
        for batch in get_batches(X, y):
            X_b, y_b = batch
            gradient = compute_gradient(X_b, y_b, theta)
            
            # Обновление с инерцией
            velocity = momentum * velocity - lr * gradient
            theta += velocity
    
    return theta

# Nesterov Accelerated Gradient (NAG) — смотрит вперёд
def nag(X, y, lr=0.01, momentum=0.9):
    theta = np.zeros(X.shape[1])
    velocity = np.zeros_like(theta)
    
    for epoch in range(n_epochs):
        for X_b, y_b in get_batches(X, y):
            # Смотрим в направлении momentum
            theta_lookahead = theta + momentum * velocity
            gradient = compute_gradient(X_b, y_b, theta_lookahead)
            
            velocity = momentum * velocity - lr * gradient
            theta += velocity
```

### AdaGrad: адаптивный learning rate

```python
def adagrad(X, y, lr=0.01, eps=1e-8):
    """Адаптивный lr: часто обновляемые признаки получают меньший lr"""
    theta = np.zeros(X.shape[1])
    G = np.zeros_like(theta)  # Сумма квадратов градиентов
    
    for X_b, y_b in get_batches(X, y):
        g = compute_gradient(X_b, y_b, theta)
        G += g**2  # Накапливаем квадраты
        theta -= lr * g / (np.sqrt(G) + eps)
    
    # Проблема: G только растёт → lr → 0, обучение останавливается
    return theta
```

### RMSProp: экспоненциальное скользящее среднее

```python
def rmsprop(X, y, lr=0.001, rho=0.9, eps=1e-8):
    """Исправляет проблему AdaGrad через экспоненциальное скользящее среднее"""
    theta = np.zeros(X.shape[1])
    E_g2 = np.zeros_like(theta)
    
    for X_b, y_b in get_batches(X, y):
        g = compute_gradient(X_b, y_b, theta)
        E_g2 = rho * E_g2 + (1 - rho) * g**2  # Экспоненциальное скользящее среднее
        theta -= lr * g / (np.sqrt(E_g2) + eps)
    
    return theta
```

### Adam: Adaptive Moment Estimation

Adam — самый популярный оптимизатор в глубоком обучении. Комбинирует Momentum и RMSProp:

```python
def adam(X, y, lr=0.001, beta1=0.9, beta2=0.999, eps=1e-8, n_epochs=100):
    """Adam optimizer"""
    theta = np.zeros(X.shape[1])
    m = np.zeros_like(theta)   # First moment (momentum)
    v = np.zeros_like(theta)   # Second moment (velocity)
    t = 0  # Timestep
    
    for epoch in range(n_epochs):
        for X_b, y_b in get_batches(X, y):
            t += 1
            g = compute_gradient(X_b, y_b, theta)
            
            # Обновление моментов
            m = beta1 * m + (1 - beta1) * g           # Первый момент
            v = beta2 * v + (1 - beta2) * g**2        # Второй момент
            
            # Bias correction (важно в начале обучения)
            m_hat = m / (1 - beta1**t)
            v_hat = v / (1 - beta2**t)
            
            # Обновление параметров
            theta -= lr * m_hat / (np.sqrt(v_hat) + eps)
    
    return theta
```

### Learning Rate Scheduling

```python
from torch.optim.lr_scheduler import StepLR, CosineAnnealingLR, OneCycleLR

optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Step decay: снижаем lr каждые N эпох
scheduler = StepLR(optimizer, step_size=30, gamma=0.1)

# Cosine annealing: плавное снижение lr по косинусу
scheduler = CosineAnnealingLR(optimizer, T_max=100)

# OneCycle: быстро нарастает, потом убывает (очень эффективен)
scheduler = OneCycleLR(optimizer, max_lr=0.01, 
                        steps_per_epoch=len(train_loader), 
                        epochs=100)

# В цикле обучения
for epoch in range(n_epochs):
    for batch in train_loader:
        optimizer.zero_grad()
        loss = model(batch)
        loss.backward()
        optimizer.step()
    
    scheduler.step()  # Обновляем lr каждую эпоху
```

## Backpropagation: цепное правило через граф вычислений

Backpropagation — алгоритм эффективного вычисления градиентов в нейросети через применение цепного правила.

### Chain Rule (цепное правило)

```
d/dx f(g(x)) = f'(g(x)) × g'(x)

Или для функции нескольких переменных:
∂L/∂x = Σⱼ (∂L/∂yⱼ) × (∂yⱼ/∂x)
```

### Computation Graph

Нейросеть можно представить как направленный граф вычислений. Каждый узел — операция. Ребра — потоки данных.

```
Forward pass (слева направо):
x → [Linear: xW+b] → z → [ReLU: max(0,z)] → a → [Loss: MSE(a,y)] → L

Backward pass (справа налево):
∂L/∂a = 2(a-y)/m
∂L/∂z = ∂L/∂a × ∂a/∂z = ∂L/∂a × ReLU'(z)
∂L/∂W = ∂L/∂z × ∂z/∂W = ∂L/∂z × xᵀ
∂L/∂b = ∂L/∂z × ∂z/∂b = ∂L/∂z
∂L/∂x = ∂L/∂z × ∂z/∂x = ∂L/∂z × Wᵀ
```

### Ручное вычисление backprop

Реализуем двухслойную нейросеть с нуля:

```python
import numpy as np

class TwoLayerNetwork:
    def __init__(self, n_input, n_hidden, n_output):
        # Xavier initialization
        self.W1 = np.random.randn(n_input, n_hidden) * np.sqrt(2.0 / n_input)
        self.b1 = np.zeros(n_hidden)
        self.W2 = np.random.randn(n_hidden, n_output) * np.sqrt(2.0 / n_hidden)
        self.b2 = np.zeros(n_output)
    
    def relu(self, x):
        return np.maximum(0, x)
    
    def relu_backward(self, dout, cache):
        """Градиент ReLU: 1 если x > 0, иначе 0"""
        x = cache
        return dout * (x > 0)
    
    def softmax(self, x):
        exp_x = np.exp(x - x.max(axis=1, keepdims=True))
        return exp_x / exp_x.sum(axis=1, keepdims=True)
    
    def forward(self, X):
        """Forward pass: сохраняем промежуточные значения для backward"""
        # Слой 1: Linear → ReLU
        self.z1 = X @ self.W1 + self.b1
        self.a1 = self.relu(self.z1)
        self.X = X
        
        # Слой 2: Linear → Softmax
        self.z2 = self.a1 @ self.W2 + self.b2
        self.a2 = self.softmax(self.z2)
        
        return self.a2
    
    def compute_loss(self, y_pred, y_true):
        """Cross-entropy loss"""
        m = len(y_true)
        # Извлекаем вероятности правильных классов
        correct_probs = y_pred[np.arange(m), y_true]
        return -np.mean(np.log(correct_probs + 1e-10))
    
    def backward(self, y_true):
        """Backward pass: вычисляем градиенты"""
        m = len(y_true)
        
        # Градиент softmax + cross-entropy loss (удобная формула)
        dz2 = self.a2.copy()
        dz2[np.arange(m), y_true] -= 1
        dz2 /= m
        
        # Градиенты W2, b2
        dW2 = self.a1.T @ dz2                    # (n_hidden, n_output)
        db2 = np.sum(dz2, axis=0)                 # (n_output,)
        
        # Backprop через слой 2
        da1 = dz2 @ self.W2.T                     # (m, n_hidden)
        
        # Backprop через ReLU
        dz1 = da1 * (self.z1 > 0)                # chain rule через ReLU
        
        # Градиенты W1, b1
        dW1 = self.X.T @ dz1                      # (n_input, n_hidden)
        db1 = np.sum(dz1, axis=0)                 # (n_hidden,)
        
        return {'W1': dW1, 'b1': db1, 'W2': dW2, 'b2': db2}
    
    def update_params(self, grads, lr=0.01):
        self.W1 -= lr * grads['W1']
        self.b1 -= lr * grads['b1']
        self.W2 -= lr * grads['W2']
        self.b2 -= lr * grads['b2']

# Обучение
net = TwoLayerNetwork(784, 256, 10)  # MNIST: 28×28=784 → 256 → 10

for epoch in range(100):
    # Forward pass
    y_pred = net.forward(X_train_batch)
    loss = net.compute_loss(y_pred, y_train_batch)
    
    # Backward pass
    grads = net.backward(y_train_batch)
    
    # Обновление параметров
    net.update_params(grads, lr=0.01)
    
    if epoch % 10 == 0:
        print(f"Epoch {epoch}, Loss: {loss:.4f}")
```

### Численная проверка градиентов (Gradient Check)

Чтобы убедиться, что backprop реализован правильно:

```python
def numerical_gradient(f, x, eps=1e-5):
    """Аппроксимация градиента центральными разностями"""
    grad = np.zeros_like(x)
    
    it = np.nditer(x, flags=['multi_index'])
    while not it.finished:
        idx = it.multi_index
        old_val = x[idx]
        
        x[idx] = old_val + eps
        f_plus = f(x)
        
        x[idx] = old_val - eps
        f_minus = f(x)
        
        grad[idx] = (f_plus - f_minus) / (2 * eps)
        
        x[idx] = old_val
        it.iternext()
    
    return grad

def gradient_check(model, X, y):
    """Сравниваем аналитический и численный градиенты"""
    def loss_fn(W1_flat):
        model.W1 = W1_flat.reshape(model.W1.shape)
        y_pred = model.forward(X)
        return model.compute_loss(y_pred, y)
    
    y_pred = model.forward(X)
    grads = model.backward(y)
    
    W1_flat = model.W1.flatten()
    numerical_grad = numerical_gradient(loss_fn, W1_flat)
    analytical_grad = grads['W1'].flatten()
    
    diff = np.linalg.norm(analytical_grad - numerical_grad)
    norm = np.linalg.norm(analytical_grad) + np.linalg.norm(numerical_grad)
    relative_error = diff / norm
    
    print(f"Relative error: {relative_error:.2e}")
    # Ожидаем < 1e-5: если больше — баг в backprop!
```

## Vanishing и Exploding Gradients

### Проблема: градиенты исчезают

В глубоких сетях градиент умножается на производную активации на каждом слое. Если производные < 1, градиент экспоненциально уменьшается к входным слоям → ранние слои почти не обучаются.

```python
# Sigmoid'a: производная = σ(x)(1-σ(x)) <= 0.25
# При 100 слоях: 0.25^100 ≈ 10^-60 — фактически ноль!

# ReLU решает проблему: производная = 1 (для x > 0)
# Но страдает от "dying ReLU": нейрон может "умереть"

# Решения:
# 1. ReLU вместо sigmoid
# 2. Residual connections (ResNet)
# 3. Careful initialization (Xavier, Kaiming)
# 4. Batch Normalization
# 5. Gradient clipping
```

### Gradient Clipping

```python
# Для взрывного роста градиентов
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

# В цикле обучения:
optimizer.zero_grad()
loss.backward()
torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)  # Обрезаем
optimizer.step()
```

### Инициализация весов

```python
import torch.nn as nn

# Xavier/Glorot: для sigmoid/tanh
nn.init.xavier_uniform_(layer.weight)
# Дисперсия = 2 / (fan_in + fan_out)

# Kaiming/He: для ReLU
nn.init.kaiming_uniform_(layer.weight, mode='fan_in', nonlinearity='relu')
# Дисперсия = 2 / fan_in
```

## PyTorch: autograd под капотом

PyTorch реализует backprop через автоматическое дифференцирование (autograd):

```python
import torch
import torch.nn as nn
import torch.optim as optim

class SimpleNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(784, 256)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(256, 10)
    
    def forward(self, x):
        x = self.relu(self.fc1(x))
        return self.fc2(x)

model = SimpleNet()
optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss()

for epoch in range(100):
    for X_batch, y_batch in dataloader:
        # Forward pass
        y_pred = model(X_batch)
        loss = criterion(y_pred, y_batch)
        
        # Backward pass (PyTorch строит граф автоматически!)
        optimizer.zero_grad()  # Обнуляем предыдущие градиенты
        loss.backward()        # Вычисляем градиенты через autograd
        optimizer.step()       # Обновляем параметры
```

`loss.backward()` автоматически проходит по computation graph и вычисляет ∂L/∂θ для каждого параметра. PyTorch хранит граф в памяти во время forward pass, чтобы использовать его в backward.

## Итог

Ключевые концепции обучения нейросетей:

1. **Функция потерь** — измеряет расхождение между предсказаниями и истиной
2. **Градиент** — вектор, указывающий направление наибольшего роста (идём в обратном направлении)
3. **Mini-batch SGD** — обновляем параметры на мини-пакетах для баланса скорости и стабильности
4. **Adam** — адаптивный оптимизатор с моментом, де-факто стандарт
5. **Backpropagation** — chain rule через computation graph для эффективного вычисления всех градиентов
6. **Vanishing gradients** — проблема глубоких сетей; решается ReLU, BatchNorm, residual connections

## Литература

1. Goodfellow, I., Bengio, Y., Courville, A. (2016). *Deep Learning*. MIT Press. https://www.deeplearningbook.org/

2. Rumelhart, D., Hinton, G., Williams, R. (1986). *Learning Representations by Back-propagating Errors*. Nature, 323, 533-536.

3. Kingma, D., Ba, J. (2015). *Adam: A Method for Stochastic Optimization*. ICLR 2015. https://arxiv.org/abs/1412.6980

4. Glorot, X., Bengio, Y. (2010). *Understanding the Difficulty of Training Deep Feedforward Neural Networks*. AISTATS 2010.

5. He, K., Zhang, X., Ren, S., Sun, J. (2015). *Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification*. ICCV 2015.

6. Bengio, Y., Simard, P., Frasconi, P. (1994). *Learning Long-Term Dependencies with Gradient Descent is Difficult*. IEEE Transactions on Neural Networks.

7. Nesterov, Y. (1983). *A method of solving a convex programming problem with convergence rate O(1/k²)*. Soviet Mathematics Doklady.

8. PyTorch. *Autograd Mechanics*. https://pytorch.org/docs/stable/notes/autograd.html

9. Duchi, J., Hazan, E., Singer, Y. (2011). *Adaptive Subgradient Methods for Online Learning and Stochastic Optimization*. JMLR.

10. Smith, L.N. (2018). *A Disciplined Approach to Neural Network Hyper-Parameters*. https://arxiv.org/abs/1803.09820
