# Эмбеддинги: превращение слов, изображений и чего угодно в векторы

"Король" минус "мужчина" плюс "женщина" равно "королева" — эта знаменитая аналогия из word2vec стала символом идеи эмбеддингов. Эмбеддинг — это отображение любого объекта (слова, изображения, пользователя, товара) в точку в многомерном векторном пространстве таким образом, что семантически похожие объекты оказываются близко. Эта простая идея лежит в основе современного поиска, рекомендаций и языковых моделей.

## Что такое эмбеддинг

До эмбеддингов для работы с текстом использовали one-hot векторы:

```
Словарь: ["кот", "кошка", "собака", "рыба"]
"кот"    → [1, 0, 0, 0]
"кошка"  → [0, 1, 0, 0]
"собака" → [0, 0, 1, 0]
"рыба"   → [0, 0, 0, 1]
```

Проблемы one-hot:
1. Размер = размер словаря (100K+) — огромные векторы
2. Все векторы ортогональны: cos("кот", "кошка") = 0 — нет семантики
3. Нет обобщения: "кот" и "кошка" совершенно разные для модели

Эмбеддинг решает это: отображение в плотное пространство меньшей размерности:

```python
import numpy as np

# Эмбеддинги слов (d=4 для иллюстрации, на практике 100-1000)
embeddings = {
    "кот":    np.array([ 0.8,  0.3, -0.2, 0.5]),
    "кошка":  np.array([ 0.7,  0.4, -0.1, 0.6]),  # близко к "кот"
    "собака": np.array([ 0.6,  0.2,  0.1, 0.3]),  # близко к "кот", "кошка"
    "рыба":   np.array([-0.1, -0.3,  0.9, 0.1]),  # далеко от животных
    "король": np.array([ 0.1,  0.8,  0.2, 0.7]),
    "мужчина":np.array([ 0.3,  0.1,  0.6, 0.2]),
    "женщина":np.array([ 0.2,  0.1,  0.7, 0.5]),
}

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

print(cosine_similarity(embeddings["кот"], embeddings["кошка"]))  # ~0.99 (близко)
print(cosine_similarity(embeddings["кот"], embeddings["рыба"]))   # ~0.1 (далеко)
```

## Word2Vec: обучение через предсказание контекста

Word2Vec (Mikolov et al., 2013) — революционный метод получения word embeddings через самообучение на текстовом корпусе.

### Skip-gram: предсказываем контекст по слову

Дано центральное слово → предсказать окружающие слова:

```
"Быстрая [коричневая] лиса прыгнула"
           центральное слово

Предсказываем:
"Быстрая" при условии "коричневая"
"лиса" при условии "коричневая"
(window=1)
```

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

class SkipGram(nn.Module):
    def __init__(self, vocab_size, embedding_dim):
        super().__init__()
        # Две матрицы эмбеддингов: для "центра" и "контекста"
        self.embeddings = nn.Embedding(vocab_size, embedding_dim)
        self.context_embeddings = nn.Embedding(vocab_size, embedding_dim)
    
    def forward(self, center, context):
        """
        center:  (batch,) — индексы центральных слов
        context: (batch,) — индексы контекстных слов
        """
        center_embed = self.embeddings(center)    # (batch, d)
        context_embed = self.context_embeddings(context)  # (batch, d)
        
        # Скалярное произведение → логит
        score = torch.sum(center_embed * context_embed, dim=1)  # (batch,)
        return score

# Negative Sampling: для эффективного обучения
def negative_sampling_loss(pos_score, neg_scores):
    """
    pos_score: оценка для реальных пар (центр, контекст)
    neg_scores: оценки для случайных отрицательных пар
    """
    pos_loss = F.logsigmoid(pos_score).mean()
    neg_loss = F.logsigmoid(-neg_scores).mean()
    return -(pos_loss + neg_loss)
```

### CBOW: предсказываем слово по контексту

Обратная задача: дан контекст → предсказать центральное слово. CBOW немного быстрее, Skip-gram лучше для редких слов.

### Аналогии через арифметику векторов

```python
from gensim.models import Word2Vec, KeyedVectors

# Загружаем предобученные векторы
word_vectors = KeyedVectors.load_word2vec_format('GoogleNews-vectors.bin', binary=True)

# Аналогии
result = word_vectors.most_similar(
    positive=['king', 'woman'], 
    negative=['man'], 
    topn=1
)
print(result)  # [('queen', 0.7118)]

# Семантические кластеры
similar_words = word_vectors.most_similar('cat', topn=5)
print(similar_words)  # [('cats', 0.82), ('kitten', 0.77), ('feline', 0.73), ...]
```

### Интерпретация геометрии

```
Векторы позволяют "думать" о словах геометрически:

Страны и столицы:
Москва - Россия + Германия ≈ Берлин

Глагольные формы:
walking - walk + swim ≈ swimming

Род:
doctor - man + woman ≈ nurse (хотя это демонстрирует и bias!)
```

## GloVe: глобальная статистика совместной встречаемости

GloVe (Global Vectors for Word Representation, Stanford 2014) использует глобальную статистику корпуса, а не локальный контекст:

```
Матрица совместной встречаемости X:
X[i][j] = сколько раз слово j появляется в контексте слова i

Objective: w_i · w̃_j + b_i + b̃_j = log(X_{ij})

Идея: скалярное произведение эмбеддингов должно соответствовать
логарифму частоты совместного появления слов.
```

GloVe часто чуть лучше word2vec на задачах аналогий и семантического сходства благодаря явному использованию глобальной статистики.

## FastText: символьные n-граммы

FastText (Facebook, 2016) расширяет word2vec, представляя слово как набор символьных n-грамм:

```
"король" → ["<ко", "кор", "оро", "рол", "оль", "ль>", "<король>"]
(с угловыми скобками для начала и конца)

Эмбеддинг слова = среднее эмбеддингов всех n-грамм
```

Преимущества FastText:
1. Работает с редкими словами (по частям)
2. Может работать с опечатками
3. Легко расширяется на новые слова (OOV — out of vocabulary)

```python
import fasttext

# Обучение
model = fasttext.train_unsupervised('text.txt', model='skipgram', dim=100)

# Эмбеддинг слова (включая OOV!)
vector = model.get_word_vector("непереводимый")  # незнакомое слово → OK!

# Схожие слова
model.get_nearest_neighbors("программирование", k=5)
```

## Контекстуальные эмбеддинги: ELMo и BERT

Главная проблема word2vec/GloVe: **одно слово — один вектор**. Но "банк" в "банк реки" и "банк денег" — разные значения!

### ELMo: Embeddings from Language Models

```
ELMo обучается на задаче LM:
- Двунаправленный LSTM
- Предсказывает следующее и предыдущее слово
- Эмбеддинг = взвешенная сумма всех слоёв LSTM

"банк" в "берег банка реки" → другой вектор, чем
"банк" в "счёт в банке"
```

### BERT: Bidirectional Encoder Representations from Transformers

```python
from transformers import BertTokenizer, BertModel
import torch

tokenizer = BertTokenizer.from_pretrained('bert-base-multilingual-cased')
model = BertModel.from_pretrained('bert-base-multilingual-cased')
model.eval()

# Контекстуальные эмбеддинги
sentence1 = "Я иду в банк за деньгами"
sentence2 = "Мы сидели на берегу реки у банка"

with torch.no_grad():
    for sentence in [sentence1, sentence2]:
        inputs = tokenizer(sentence, return_tensors='pt')
        outputs = model(**inputs)
        
        # last_hidden_state: (1, seq_len, 768)
        last_hidden = outputs.last_hidden_state
        
        # Находим токен "банк" / "банка"
        tokens = tokenizer.tokenize(sentence)
        print(f"Tokens: {tokens}")
        # Эмбеддинги "банк" будут разными в обоих предложениях!
```

## Sentence Embeddings: Sentence-BERT

Для семантического поиска нужны эмбеддинги предложений. BERT плохо работает "из коробки" для этого — нужна дообучение.

Sentence-BERT (SBERT) дообучает BERT с сиамской сетью на задаче семантического сходства:

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')

sentences = [
    "Кот сидит на подоконнике",
    "Кошка находится у окна",
    "Пёс бегает во дворе"
]

embeddings = model.encode(sentences)  # (3, 768)

# Семантическое сходство
sim_matrix = cosine_similarity(embeddings)
print(sim_matrix)
# [[1.00, 0.89, 0.23],   ← "Кот" и "Кошка" очень похожи
#  [0.89, 1.00, 0.19],
#  [0.23, 0.19, 1.00]]
```

## Image Embeddings: CLIP

CLIP (Contrastive Language-Image Pre-Training, OpenAI 2021) — модель, связывающая изображения и текст в одно пространство:

```python
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel

model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

# Изображение и текстовые описания
image = Image.open("cat.jpg")
texts = ["фотография кота", "изображение собаки", "пейзаж с горами"]

inputs = processor(text=texts, images=image, return_tensors="pt", padding=True)
outputs = model(**inputs)

# Сходство изображения с каждым текстом
logits_per_image = outputs.logits_per_image  # (1, 3)
probs = logits_per_image.softmax(dim=1)
print(probs)  # [0.85, 0.12, 0.03] — скорее всего это кот
```

CLIP обучался на 400M пар (текст, изображение) из интернета через contrastive learning: похожие пары → близкие векторы.

## Операции над эмбеддингами

### Косинусное сходство

```python
def cosine_similarity(a, b):
    """Мера сходства: 1 = идентичны, 0 = ортогональны, -1 = противоположны"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# В PyTorch
import torch.nn.functional as F
sim = F.cosine_similarity(tensor_a.unsqueeze(0), tensor_b.unsqueeze(0))
```

### Поиск ближайших соседей

```python
import faiss
import numpy as np

# Создаём индекс для быстрого поиска
d = 768  # размерность эмбеддингов
index = faiss.IndexFlatL2(d)  # L2 расстояние

# Добавляем эмбеддинги
corpus_embeddings = model.encode(corpus_sentences)
index.add(corpus_embeddings.astype('float32'))

# Поиск по запросу
query_embedding = model.encode(["поиск по смыслу"]).astype('float32')
k = 5
distances, indices = index.search(query_embedding, k)

for i, idx in enumerate(indices[0]):
    print(f"{distances[0][i]:.3f}: {corpus_sentences[idx]}")
```

### Визуализация через t-SNE/UMAP

```python
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt

# t-SNE: визуализация высокоразмерных данных в 2D/3D
# Сохраняет локальную структуру (похожие объекты рядом)
tsne = TSNE(n_components=2, random_state=42, perplexity=30)
embeddings_2d = tsne.fit_transform(high_dim_embeddings)

# Визуализация по категориям
plt.figure(figsize=(12, 8))
for category in categories:
    mask = (labels == category)
    plt.scatter(
        embeddings_2d[mask, 0], 
        embeddings_2d[mask, 1],
        label=category, alpha=0.7
    )
plt.legend()
plt.title('t-SNE визуализация word embeddings')

# UMAP: быстрее t-SNE, лучше сохраняет глобальную структуру
from umap import UMAP
reducer = UMAP(n_components=2, random_state=42)
embeddings_2d_umap = reducer.fit_transform(high_dim_embeddings)
```

## Эмбеддинги в рекомендательных системах

```python
import torch
import torch.nn as nn

class CollaborativeFilteringEmbedding(nn.Module):
    """Matrix Factorization через эмбеддинги"""
    def __init__(self, n_users, n_items, embedding_dim=64):
        super().__init__()
        self.user_embedding = nn.Embedding(n_users, embedding_dim)
        self.item_embedding = nn.Embedding(n_items, embedding_dim)
        
        # Смещения для пользователей и товаров
        self.user_bias = nn.Embedding(n_users, 1)
        self.item_bias = nn.Embedding(n_items, 1)
        self.global_bias = nn.Parameter(torch.zeros(1))
        
        # Инициализация
        nn.init.normal_(self.user_embedding.weight, std=0.01)
        nn.init.normal_(self.item_embedding.weight, std=0.01)
    
    def forward(self, user_ids, item_ids):
        user_embed = self.user_embedding(user_ids)   # (batch, d)
        item_embed = self.item_embedding(item_ids)   # (batch, d)
        
        # Скалярное произведение (предсказанный рейтинг)
        dot = (user_embed * item_embed).sum(dim=1)   # (batch,)
        
        bias = (self.user_bias(user_ids).squeeze() + 
                self.item_bias(item_ids).squeeze() + 
                self.global_bias)
        
        return dot + bias

# Обучение на данных (user_id, item_id, rating)
model = CollaborativeFilteringEmbedding(n_users=10000, n_items=50000)
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
criterion = nn.MSELoss()

for user, item, rating in dataloader:
    pred = model(user, item)
    loss = criterion(pred, rating.float())
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
```

## Fine-tuning эмбеддингов

```python
from transformers import AutoModel, AutoTokenizer
import torch.nn as nn

class SentenceClassifier(nn.Module):
    def __init__(self, model_name, num_classes):
        super().__init__()
        self.bert = AutoModel.from_pretrained(model_name)
        self.classifier = nn.Linear(768, num_classes)
        self.dropout = nn.Dropout(0.1)
    
    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        
        # CLS токен как представление предложения
        cls_output = outputs.last_hidden_state[:, 0, :]  # (batch, 768)
        
        return self.classifier(self.dropout(cls_output))

# Fine-tuning с замороженным BERT (только классификатор)
model = SentenceClassifier('bert-base-multilingual-cased', num_classes=5)

# Первые N эпох: заморозить BERT, обучать только голову
for param in model.bert.parameters():
    param.requires_grad = False

# Потом: разморозить нижние слои
for param in model.bert.encoder.layer[-4:].parameters():
    param.requires_grad = True
```

## Итог

Эмбеддинги — универсальный язык для машинного обучения:

1. **Word2Vec** — обучение через предсказание контекста (skip-gram/CBOW)
2. **GloVe** — глобальная статистика совместной встречаемости
3. **FastText** — символьные n-граммы для обработки OOV и редких слов
4. **BERT** — контекстуальные эмбеддинги, разные векторы для разных значений
5. **Sentence-BERT** — дообученный BERT для семантического поиска
6. **CLIP** — совместное пространство для изображений и текста
7. **Косинусное сходство + FAISS** — эффективный поиск ближайших соседей

## Литература

1. Mikolov, T., et al. (2013). *Efficient Estimation of Word Representations in Vector Space*. ICLR 2013. https://arxiv.org/abs/1301.3781

2. Pennington, J., Socher, R., Manning, C. (2014). *GloVe: Global Vectors for Word Representation*. EMNLP 2014. https://nlp.stanford.edu/projects/glove/

3. Bojanowski, P., et al. (2017). *Enriching Word Vectors with Subword Information* (FastText). TACL 2017. https://arxiv.org/abs/1607.04606

4. Peters, M., et al. (2018). *Deep Contextualized Word Representations* (ELMo). NAACL 2018. https://arxiv.org/abs/1802.05365

5. Devlin, J., et al. (2019). *BERT: Pre-training of Deep Bidirectional Transformers*. NAACL 2019. https://arxiv.org/abs/1810.04805

6. Reimers, N., Gurevych, I. (2019). *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks*. EMNLP 2019. https://arxiv.org/abs/1908.10084

7. Radford, A., et al. (2021). *Learning Transferable Visual Models From Natural Language Supervision* (CLIP). ICML 2021. https://arxiv.org/abs/2103.00020

8. Mikolov, T., et al. (2013). *Linguistic Regularities in Continuous Space Word Representations*. NAACL 2013.

9. van der Maaten, L., Hinton, G. (2008). *Visualizing Data using t-SNE*. JMLR, 9, 2579-2605.

10. McInnes, L., Healy, J., Melville, J. (2018). *UMAP: Uniform Manifold Approximation and Projection*. https://arxiv.org/abs/1802.03426
