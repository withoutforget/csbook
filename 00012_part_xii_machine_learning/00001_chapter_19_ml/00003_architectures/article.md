# Архитектуры нейросетей: MLP, CNN, RNN/LSTM, Трансформеры

За 15 лет глубокое обучение прошло путь от простых многослойных перцептронов до трансформеров с триллионами параметров. Каждая архитектура возникла как ответ на конкретную задачу: CNN — для изображений, RNN/LSTM — для последовательностей, трансформеры — для захвата долгосрочных зависимостей. Понимание каждой архитектуры и её мотивации — основа работы в современном ML.

## MLP: многослойный перцептрон

### Архитектура

MLP (Multi-Layer Perceptron) — полносвязная нейросеть: каждый нейрон слоя соединён с каждым нейроном следующего слоя.

```
Входной слой (784 нейрона для MNIST 28×28)
    ↓  W₁ (784 × 256)
Скрытый слой 1 (256 нейронов) → ReLU
    ↓  W₂ (256 × 128)
Скрытый слой 2 (128 нейронов) → ReLU
    ↓  W₃ (128 × 10)
Выходной слой (10 нейронов) → Softmax
```

### Функции активации

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

# ReLU: самая популярная
F.relu(x)          # max(0, x)

# GELU: используется в трансформерах
F.gelu(x)          # x × Φ(x), где Φ — CDF нормального распределения

# Swish/SiLU: x × sigmoid(x)
F.silu(x)          # также называется Swish

# Leaky ReLU: решает dying ReLU
F.leaky_relu(x, negative_slope=0.01)  # max(0.01x, x)

# ELU: exponential linear unit
F.elu(x)           # x если x > 0, e^x - 1 иначе
```

**GELU** (Gaussian Error Linear Unit) стал предпочтительным в современных моделях (GPT, BERT):

```
GELU(x) = x × Φ(x) ≈ 0.5x(1 + tanh(√(2/π)(x + 0.044715x³)))

Преимущество перед ReLU: плавный переход около нуля,
нет "мёртвых нейронов"
```

### BatchNorm и Dropout

```python
class MLP(nn.Module):
    def __init__(self, input_dim, hidden_dims, output_dim, dropout_rate=0.3):
        super().__init__()
        
        layers = []
        dims = [input_dim] + hidden_dims
        
        for i in range(len(dims) - 1):
            layers.extend([
                nn.Linear(dims[i], dims[i+1]),
                nn.BatchNorm1d(dims[i+1]),  # Нормализация по батчу
                nn.ReLU(),
                nn.Dropout(dropout_rate)    # Случайное отключение нейронов
            ])
        
        layers.append(nn.Linear(hidden_dims[-1], output_dim))
        self.network = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.network(x)
```

**BatchNorm**: нормализует входы каждого слоя по батчу → ускоряет обучение, снижает чувствительность к инициализации:

```
μ_B = mean(x over batch)
σ²_B = var(x over batch)
x̂ = (x - μ_B) / √(σ²_B + ε)
y = γx̂ + β    (γ, β — обучаемые параметры)
```

**Dropout**: случайно "отключает" нейроны с вероятностью p — эффективная регуляризация.

## CNN: свёрточные нейросети

### Мотивация: почему не MLP для изображений

Изображение 1000×1000×3 RGB = 3 миллиона входных нейронов. Полносвязный слой → 1000 нейронов потребует 3 × 10⁹ параметров только в первом слое. Это:
1. Слишком много параметров (переобучение)
2. Не использует пространственную структуру изображений

CNN решает это через **локальные связи** и **разделяемые веса**.

### Операция свёртки

```
Изображение 5×5:           Фильтр 3×3:
[[1, 2, 3, 0, 0],          [[1, 0, -1],
 [0, 1, 2, 3, 1],           [1, 0, -1],
 [1, 0, 1, 2, 3],           [1, 0, -1]]
 [2, 1, 0, 1, 2],
 [0, 1, 2, 1, 1]]

Результат (3×3 при padding=0, stride=1):
(сумма поэлементных произведений фильтра со скользящим окном)
```

```python
class ConvBlock(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding)
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)
    
    def forward(self, x):
        return self.relu(self.bn(self.conv(x)))

class SimpleCNN(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        # Feature extraction
        self.features = nn.Sequential(
            ConvBlock(3, 64),           # 224×224×3 → 224×224×64
            ConvBlock(64, 64),
            nn.MaxPool2d(2, 2),         # 224×224 → 112×112
            
            ConvBlock(64, 128),         # 112×112×64 → 112×112×128
            ConvBlock(128, 128),
            nn.MaxPool2d(2, 2),         # 112×112 → 56×56
            
            ConvBlock(128, 256),
            nn.MaxPool2d(2, 2),         # 56×56 → 28×28
        )
        
        # Classifier
        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d((7, 7)),  # Глобальный avg pooling → 7×7
            nn.Flatten(),
            nn.Linear(256 * 7 * 7, 512),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(512, num_classes)
        )
    
    def forward(self, x):
        x = self.features(x)
        return self.classifier(x)
```

### Легендарные архитектуры

**AlexNet (2012)**: 8 слоёв, побил ILSVRC-2012 с большим отрывом.

**VGG (2014)**: идея использовать только 3×3 фильтры:
```python
# VGG16 block: серия 3×3 conv → MaxPool
VGG_blocks = [
    [64, 64],       # block 1
    [128, 128],     # block 2
    [256, 256, 256], # block 3
    [512, 512, 512], # block 4
    [512, 512, 512], # block 5
]
```

**ResNet (2015)**: residual connections решили проблему деградации в глубоких сетях:

```python
class ResidualBlock(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, 3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)
        self.relu = nn.ReLU(inplace=True)
    
    def forward(self, x):
        identity = x  # Сохраняем для skip connection
        
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        
        out += identity  # Skip connection: y = F(x) + x
        return self.relu(out)
```

Идея residual connections: вместо изучения H(x) учим F(x) = H(x) - x (остаток). В крайнем случае F(x) = 0 → identity mapping.

## RNN: рекуррентные нейросети

### Проблема последовательностей

MLP и CNN не учитывают порядок. Для текста, аудио, временных рядов нужна память о предыдущих элементах.

### Базовый RNN

```
h_t = tanh(W_x × x_t + W_h × h_{t-1} + b)
y_t = W_y × h_t + b_y

h_t — hidden state (память)
x_t — текущий вход
```

```python
class SimpleRNN(nn.Module):
    def __init__(self, input_size, hidden_size, output_size):
        super().__init__()
        self.rnn = nn.RNN(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)
    
    def forward(self, x):
        # x: (batch, seq_len, input_size)
        output, h_n = self.rnn(x)
        # output: (batch, seq_len, hidden_size) — выходы всех шагов
        # h_n: (1, batch, hidden_size) — последний hidden state
        
        return self.fc(h_n.squeeze(0))  # Классификация по последнему состоянию
```

### LSTM: Long Short-Term Memory

Базовый RNN страдает от vanishing gradients на длинных последовательностях. LSTM решает это через явную "ячейку памяти" с вентилями.

```
LSTM gates:
f_t = σ(W_f × [h_{t-1}, x_t] + b_f)     # Forget gate: что забыть из памяти
i_t = σ(W_i × [h_{t-1}, x_t] + b_i)     # Input gate: что записать
g_t = tanh(W_g × [h_{t-1}, x_t] + b_g)  # Candidate: что именно записать
o_t = σ(W_o × [h_{t-1}, x_t] + b_o)     # Output gate: что читать из памяти

Cell state (долгосрочная память):
C_t = f_t ⊙ C_{t-1} + i_t ⊙ g_t

Hidden state (краткосрочная):
h_t = o_t ⊙ tanh(C_t)
```

```python
class LSTMClassifier(nn.Module):
    def __init__(self, vocab_size, embed_dim, hidden_size, num_classes, num_layers=2):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(
            embed_dim, hidden_size, 
            num_layers=num_layers,
            batch_first=True,
            dropout=0.3,
            bidirectional=True  # Двунаправленный LSTM
        )
        self.fc = nn.Linear(hidden_size * 2, num_classes)  # × 2 за bidirectional
        self.dropout = nn.Dropout(0.3)
    
    def forward(self, x):
        embedded = self.dropout(self.embedding(x))  # (batch, seq, embed)
        
        output, (h_n, c_n) = self.lstm(embedded)
        # h_n: (num_layers * 2, batch, hidden_size) — bidirectional
        
        # Берём последние hidden states обоих направлений
        h_fwd = h_n[-2, :, :]  # последний слой, прямое направление
        h_bwd = h_n[-1, :, :]  # последний слой, обратное направление
        h = torch.cat([h_fwd, h_bwd], dim=1)
        
        return self.fc(self.dropout(h))
```

### GRU: Gated Recurrent Unit

Упрощённый LSTM с двумя вентилями вместо трёх:

```
z_t = σ(W_z × [h_{t-1}, x_t])  # Update gate
r_t = σ(W_r × [h_{t-1}, x_t])  # Reset gate
h̃_t = tanh(W × [r_t ⊙ h_{t-1}, x_t])  # Candidate hidden state
h_t = (1 - z_t) ⊙ h_{t-1} + z_t ⊙ h̃_t
```

GRU быстрее LSTM, часто даёт сопоставимое качество.

### Seq2Seq модели

Seq2Seq (sequence-to-sequence) — архитектура для задач типа перевод, суммаризация:

```
Encoder:   [Слово1] → [Слово2] → ... → [СловоN] → контекстный вектор c
Decoder:   c → [Слово1'] → [Слово2'] → ... → [EOS]
```

## Механизм Attention

Проблема Seq2Seq: при длинных последовательностях контекстный вектор становится "bottleneck" — невозможно уместить всю информацию в один вектор.

### Базовый Attention

```
На каждом шаге декодера:
1. Вычислить "оценки" с каждым состоянием энкодера: score(hᵢ, s_t)
2. Применить softmax → веса αᵢ
3. Взвешенная сумма состояний энкодера → контекст cₜ = Σ αᵢ hᵢ

Decoder видит разные части input на каждом шаге!
```

### Self-Attention (Scaled Dot-Product)

```python
def scaled_dot_product_attention(Q, K, V, mask=None):
    """
    Q (Query):  (batch, heads, seq_len, d_k)
    K (Key):    (batch, heads, seq_len, d_k)
    V (Value):  (batch, heads, seq_len, d_v)
    """
    d_k = Q.size(-1)
    
    # Скалярное произведение Q × Kᵀ
    scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(d_k)
    
    # Применяем маску (для предотвращения "заглядывания в будущее" в декодере)
    if mask is not None:
        scores = scores.masked_fill(mask == 0, float('-inf'))
    
    # Softmax → веса attention
    weights = F.softmax(scores, dim=-1)
    
    # Взвешенная сумма Values
    return torch.matmul(weights, V), weights
```

## Трансформер: архитектура Vaswani et al. (2017)

Статья "Attention is All You Need" (Vaswani et al., 2017) убрала рекуррентность полностью, заменив её multi-head attention.

### Multi-Head Attention

```python
class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, n_heads):
        super().__init__()
        assert d_model % n_heads == 0
        
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        
        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_o = nn.Linear(d_model, d_model)
    
    def forward(self, Q, K, V, mask=None):
        batch_size = Q.size(0)
        
        # Linear projections + split heads
        def transform(x, W):
            return W(x).view(batch_size, -1, self.n_heads, self.d_k).transpose(1, 2)
        
        Q = transform(Q, self.W_q)  # (batch, heads, seq, d_k)
        K = transform(K, self.W_k)
        V = transform(V, self.W_v)
        
        # Attention
        attn_output, _ = scaled_dot_product_attention(Q, K, V, mask)
        
        # Concat heads
        attn_output = attn_output.transpose(1, 2).contiguous().view(
            batch_size, -1, self.d_model
        )
        return self.W_o(attn_output)
```

### Positional Encoding

Трансформер не имеет встроенного понятия порядка, поэтому добавляем позиционные эмбеддинги:

```python
class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_seq_len=5000, dropout=0.1):
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        
        # Синусоидальное кодирование (из оригинальной статьи)
        pe = torch.zeros(max_seq_len, d_model)
        position = torch.arange(0, max_seq_len).unsqueeze(1).float()
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        
        pe[:, 0::2] = torch.sin(position * div_term)  # чётные
        pe[:, 1::2] = torch.cos(position * div_term)  # нечётные
        
        pe = pe.unsqueeze(0)  # (1, max_seq_len, d_model)
        self.register_buffer('pe', pe)
    
    def forward(self, x):
        x = x + self.pe[:, :x.size(1)]
        return self.dropout(x)
```

### Transformer Block

```python
class TransformerBlock(nn.Module):
    def __init__(self, d_model, n_heads, d_ff, dropout=0.1):
        super().__init__()
        self.attention = MultiHeadAttention(d_model, n_heads)
        self.ff = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_ff, d_model)
        )
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x, mask=None):
        # Self-attention + residual + norm
        attn_out = self.attention(x, x, x, mask)
        x = self.norm1(x + self.dropout(attn_out))  # Pre-norm вариант
        
        # Feed-forward + residual + norm
        ff_out = self.ff(x)
        x = self.norm2(x + self.dropout(ff_out))
        
        return x
```

### BERT vs GPT: Encoder vs Decoder

```
BERT (Bidirectional Encoder):
- Только encoder часть трансформера
- Masked Language Modeling: предсказываем замаскированные токены
- Видит контекст в ОБОИХ направлениях
- Применение: классификация текста, NER, QA

GPT (Generative Pre-trained Transformer):
- Только decoder часть трансформера
- Causal LM: предсказываем следующий токен
- Видит только предыдущий контекст (causal mask)
- Применение: генерация текста, completion
```

### Vision Transformer (ViT)

```python
# Трансформер для изображений: разбиваем на patches
class VisionTransformer(nn.Module):
    def __init__(self, img_size=224, patch_size=16, num_classes=1000,
                 d_model=768, n_heads=12, n_layers=12):
        super().__init__()
        
        self.patch_size = patch_size
        n_patches = (img_size // patch_size) ** 2
        
        # Линейная проекция patches → embeddings
        self.patch_embed = nn.Conv2d(3, d_model, patch_size, stride=patch_size)
        
        # CLS token и positional embeddings
        self.cls_token = nn.Parameter(torch.zeros(1, 1, d_model))
        self.pos_embed = nn.Parameter(torch.zeros(1, n_patches + 1, d_model))
        
        # Transformer blocks
        self.blocks = nn.ModuleList([
            TransformerBlock(d_model, n_heads, d_model * 4)
            for _ in range(n_layers)
        ])
        
        self.norm = nn.LayerNorm(d_model)
        self.head = nn.Linear(d_model, num_classes)
    
    def forward(self, x):
        B = x.shape[0]
        
        # Патчи: (B, C, H, W) → (B, n_patches, d_model)
        x = self.patch_embed(x).flatten(2).transpose(1, 2)
        
        # Добавляем CLS токен
        cls_tokens = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls_tokens, x], dim=1)
        x += self.pos_embed
        
        # Transformer блоки
        for block in self.blocks:
            x = block(x)
        
        x = self.norm(x)
        return self.head(x[:, 0])  # Классификация по CLS токену
```

## Сравнение архитектур

| Архитектура | Входные данные | Параметры | Применение |
|---|---|---|---|
| MLP | Табличные данные | O(n²) на слой | Регрессия, классификация |
| CNN | Изображения, аудио | O(k²×c) на слой | CV, распознавание речи |
| RNN/LSTM | Последовательности | O(h²) на слой | NLP (устарел), временные ряды |
| Transformer | Последовательности, изображения | O(n²×d) | NLP, CV, мультимодальные задачи |

## Итог

Эволюция архитектур отражает развитие задач:

1. **MLP** — фундамент, но не учитывает структуру данных
2. **CNN** — использует пространственную инвариантность через разделяемые веса
3. **LSTM** — научила нейросети "помнить" — первый прорыв в NLP
4. **Transformer** — заменил рекуррентность attention, открыл эру масштабирования
5. **ViT** — перенёс трансформер на изображения, унифицировал архитектуры CV и NLP

## Литература

1. LeCun, Y., Bottou, L., Bengio, Y., Haffner, P. (1998). *Gradient-Based Learning Applied to Document Recognition*. Proceedings of the IEEE.

2. Hochreiter, S., Schmidhuber, J. (1997). *Long Short-Term Memory*. Neural Computation, 9(8), 1735-1780.

3. He, K., Zhang, X., Ren, S., Sun, J. (2016). *Deep Residual Learning for Image Recognition*. CVPR 2016.

4. Vaswani, A., et al. (2017). *Attention Is All You Need*. NeurIPS 2017. https://arxiv.org/abs/1706.03762

5. Devlin, J., Chang, M.W., Lee, K., Toutanova, K. (2019). *BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding*. NAACL 2019.

6. Radford, A., et al. (2019). *Language Models are Unsupervised Multitask Learners* (GPT-2). OpenAI Blog.

7. Dosovitskiy, A., et al. (2021). *An Image is Worth 16×16 Words: Transformers for Image Recognition at Scale* (ViT). ICLR 2021. https://arxiv.org/abs/2010.11929

8. Krizhevsky, A., Sutskever, I., Hinton, G. (2012). *ImageNet Classification with Deep Convolutional Neural Networks* (AlexNet). NeurIPS 2012.

9. Simonyan, K., Zisserman, A. (2015). *Very Deep Convolutional Networks for Large-Scale Image Recognition* (VGG). ICLR 2015.

10. Cho, K., et al. (2014). *Learning Phrase Representations using RNN Encoder-Decoder for Statistical Machine Translation*. EMNLP 2014. (GRU)
