# Векторные базы данных: семантический поиск и ANN-алгоритмы

## Введение

Языковые модели (LLM), системы рекомендаций, поиск изображений по содержимому, обнаружение аномалий — всё это работает с **эмбеддингами** (embeddings): плотными векторами в пространстве высокой размерности, где семантически близкие объекты расположены рядом.

Поиск «похожих» векторов — задача Approximate Nearest Neighbor Search (ANN). Точный поиск ближайшего соседа в 1536-мерном пространстве среди 100 миллионов векторов требует $O(N \times D)$ операций — неприемлемо медленно. Векторные СУБД решают эту задачу с помощью специализированных индексов: HNSW, IVF, PQ и их комбинаций.

---

## 1. Эмбеддинги: числовое представление смысла

### 1.1 Что такое эмбеддинг

Эмбеддинг — это функция отображения объекта (текст, изображение, аудио) в вектор фиксированной размерности, при котором похожие объекты имеют похожие векторы (малое косинусное расстояние или евклидово расстояние).

```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# Три семантически близких предложения
texts = [
    "Как купить билет на самолёт?",
    "Бронирование авиабилетов онлайн",
    "Заказ перелёта через интернет",
    "Как приготовить борщ?",  # семантически далёкое
]

embeddings = model.encode(texts)
print(f"Shape: {embeddings.shape}")  # (4, 384)

# Косинусное сходство
def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

for i in range(1, 4):
    sim = cosine_similarity(embeddings[0], embeddings[i])
    print(f"Similarity('{texts[0]}', '{texts[i]}'): {sim:.3f}")
# Сходство с похожими фразами: ~0.85-0.92
# Сходство с борщом: ~0.15-0.25
```

### 1.2 Типы эмбеддингов

| Тип | Модель | Размерность | Применение |
|-----|--------|-------------|------------|
| Текстовые | text-embedding-3-small (OpenAI) | 1536 | Семантический поиск, RAG |
| Многоязычные | paraphrase-multilingual-MiniLM | 384 | Поиск на разных языках |
| Изображения | CLIP (OpenAI) | 512 | Поиск по изображениям |
| Мультимодальные | CLIP, ImageBind | 512+ | Текст $\leftrightarrow$ изображение |
| Граф | Node2Vec, GraphSAGE | 128 | Рекомендации |
| Код | CodeBERT | 768 | Поиск по коду |

---

## 2. ANN-алгоритмы: поиск ближайших соседей

### 2.1 Проблема точного поиска

Точный поиск k-ближайших соседей (k-NN) в N-мерном пространстве:
- Брутфорс: $O(N \times D)$ — для 1M векторов $\times$ 1536 dim = 1.5 млрд операций
- При N=100M и D=1536 → секунды на запрос. Неприемлемо.

Approximate Nearest Neighbor (ANN) жертвует точностью ради скорости: вместо гарантированного ближайшего соседа находит 95-99% правильных результатов за миллисекунды.

### 2.2 IVF (Inverted File Index)

IVF разбивает пространство на кластеры (Voronoi cells) через k-means:

```
Шаг 1: k-means clustering → centroids c₁, c₂, ..., cₖ
Шаг 2: Каждый вектор → ближайший centroid → добавляется в его список (posting list)
Шаг 3: При поиске:
  a) найти nprobe ближайших centroids к запросу
  b) перебрать только posting lists этих centroids
  c) вернуть top-k
```

```python
import faiss
import numpy as np

# Генерация данных
d = 128        # размерность
nb = 1_000_000 # база данных
nq = 100       # число запросов

np.random.seed(1234)
xb = np.random.random((nb, d)).astype('float32')
xq = np.random.random((nq, d)).astype('float32')

# IVF индекс
nlist = 100  # количество кластеров
quantizer = faiss.IndexFlatL2(d)  # точный поиск для centroids
index = faiss.IndexIVFFlat(quantizer, d, nlist)

# Тренировка (k-means для нахождения centroids)
index.train(xb)

# Добавление векторов
index.add(xb)
print(f"Index contains {index.ntotal} vectors")

# Поиск: nprobe — сколько кластеров проверяем (качество vs скорость)
index.nprobe = 10  # проверяем 10% кластеров из 100

k = 5  # топ-5 результатов
distances, indices = index.search(xq, k)
print(f"Search results shape: {indices.shape}")  # (100, 5)
```

### 2.3 HNSW (Hierarchical Navigable Small World)

HNSW (Malkov & Yashunin, 2018) — наиболее популярный ANN-алгоритм. Строит иерархический граф из нескольких уровней:

```
Уровень 2 (разреженный): длинные связи, быстрый навигация
    [5]---[12]---[33]---[78]
     
Уровень 1 (средний):
    [2]-[5]-[8]-[12]-[18]-[25]-[33]-[47]-[56]-[78]

Уровень 0 (плотный): все N векторов
    [1][2][3]...[5]...[8]...[12]...[N]
```

**Поиск**: начинаем с верхнего уровня, переходим вниз жадно (greedy), финальный поиск — на нижнем уровне.

**Параметры:**
- `M` — число связей на уровень 0 (16-64, больше = лучше качество, больше памяти)
- `ef_construction` — размер dynamic candidate list при построении (200-500)
- `ef_search` — размер при поиске (32-512, больше = лучше качество)

```python
import faiss
import numpy as np
import time

d = 128
nb = 500_000

xb = np.random.random((nb, d)).astype('float32')
xq = np.random.random((1000, d)).astype('float32')

# HNSW индекс
M = 32  # связей на уровне
index = faiss.IndexHNSWFlat(d, M)
index.hnsw.efConstruction = 200

# Добавление (строит граф во время add)
start = time.time()
index.add(xb)
build_time = time.time() - start
print(f"Build time: {build_time:.1f}s")

# Поиск
index.hnsw.efSearch = 64
start = time.time()
k = 10
D, I = index.search(xq, k)
search_time = time.time() - start

print(f"Search time: {search_time*1000:.1f}ms for {len(xq)} queries")
print(f"QPS: {len(xq)/search_time:.0f}")

# Сравнение с точным поиском для оценки recall
flat_index = faiss.IndexFlatL2(d)
flat_index.add(xb)
_, I_exact = flat_index.search(xq[:100], k)

recall = sum(
    len(set(I[i]) & set(I_exact[i])) / k
    for i in range(100)
) / 100
print(f"Recall@{k}: {recall:.3f}")  # обычно 0.95-0.99
```

### 2.4 PQ (Product Quantization): сжатие векторов

Product Quantization сжимает 128-dim float32 вектор (512 байт) до 64 байт (8x сжатие):

1. Разбить 128-dim на 16 подпространств по 8 dim
2. Для каждого подпространства: 256 centroids (8 бит)
3. Вектор → 16 чисел по 8 бит = 16 байт

Поиск с PQ использует предвычисленные таблицы расстояний → очень быстро.

```python
# IVFPQ: IVF + Product Quantization
nlist = 256   # кластеров
m = 8         # подпространств PQ
bits = 8      # бит на субвектор

index = faiss.IndexIVFPQ(quantizer, d, nlist, m, bits)
index.train(xb)
index.add(xb)
index.nprobe = 32

# Потребление памяти: 
# HNSW: nb * d * 4 bytes + nb * M * 2 * 4 bytes
# IVFPQ: nb * m * (bits/8) bytes = nb * 8 bytes для d=128, m=8, bits=8
memory_hnsw = nb * d * 4 + nb * M * 2 * 4
memory_pq = nb * m * (bits // 8)
print(f"HNSW memory: {memory_hnsw/1e6:.0f} MB")
print(f"IVF-PQ memory: {memory_pq/1e6:.0f} MB")
print(f"Compression: {memory_hnsw/memory_pq:.0f}x")
```

---

## 3. Pgvector: векторный поиск в PostgreSQL

### 3.1 Установка и использование

pgvector — расширение PostgreSQL, добавляющее тип vector и HNSW/IVF индексы:

```sql
-- Установка расширения
CREATE EXTENSION IF NOT EXISTS vector;

-- Таблица с эмбеддингами
CREATE TABLE documents (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(1536),  -- OpenAI text-embedding-3-small
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    metadata    JSONB
);

-- HNSW индекс для приблизительного поиска (рекомендуется)
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- IVFFlat альтернатива
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Семантический поиск: найти топ-5 похожих документов
SELECT 
    id,
    title,
    1 - (embedding <=> '[0.1, 0.2, ...]'::vector) AS similarity
FROM documents
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector  -- <=> косинусное расстояние
LIMIT 5;

-- Операторы:
-- <-> евклидово расстояние (L2)
-- <#> внутреннее произведение (с отрицанием)
-- <=> косинусное расстояние

-- Гибридный поиск: полнотекстовый + векторный
SELECT 
    id,
    title,
    ts_rank(to_tsvector('russian', content), query) AS text_score,
    1 - (embedding <=> %s::vector) AS vector_score,
    ts_rank(...) * 0.3 + (1 - (embedding <=> %s::vector)) * 0.7 AS hybrid_score
FROM documents, plainto_tsquery('russian', 'поиск документов') AS query
WHERE to_tsvector('russian', content) @@ query
   OR embedding <=> %s::vector < 0.3
ORDER BY hybrid_score DESC
LIMIT 10;
```

### 3.2 Python интеграция с OpenAI

```python
import openai
import psycopg2
from psycopg2.extras import execute_values
import json

client = openai.OpenAI()

def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def store_document(conn, title: str, content: str, metadata: dict = None):
    embedding = get_embedding(content)
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO documents (title, content, embedding, metadata)
            VALUES (%s, %s, %s::vector, %s)
            RETURNING id
        """, (title, content, embedding, json.dumps(metadata or {})))
        doc_id = cur.fetchone()[0]
    conn.commit()
    return doc_id

def semantic_search(conn, query: str, top_k: int = 5, min_similarity: float = 0.7):
    query_embedding = get_embedding(query)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                id,
                title,
                content,
                1 - (embedding <=> %s::vector) AS similarity,
                metadata
            FROM documents
            WHERE 1 - (embedding <=> %s::vector) > %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, min_similarity, 
               query_embedding, top_k))
        
        results = cur.fetchall()
    
    return [
        {
            'id': row[0],
            'title': row[1],
            'content': row[2][:200] + '...',
            'similarity': float(row[3]),
            'metadata': row[4]
        }
        for row in results
    ]

# RAG (Retrieval-Augmented Generation) паттерн
def rag_answer(conn, question: str) -> str:
    # 1. Найти релевантные документы
    relevant_docs = semantic_search(conn, question, top_k=3)
    
    if not relevant_docs:
        return "Не нашёл релевантной информации в базе знаний."
    
    # 2. Сформировать контекст
    context = "\n\n".join([
        f"[{doc['title']}]\n{doc['content']}"
        for doc in relevant_docs
    ])
    
    # 3. Запрос к LLM с контекстом
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {
                "role": "system",
                "content": "Отвечай на вопросы только на основе предоставленного контекста."
            },
            {
                "role": "user",
                "content": f"Контекст:\n{context}\n\nВопрос: {question}"
            }
        ]
    )
    
    return response.choices[0].message.content
```

---

## 4. Специализированные векторные СУБД

### 4.1 Pinecone

Pinecone — managed cloud vector DB с serverless архитектурой:

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-api-key")

# Создание индекса
pc.create_index(
    name="documents",
    dimension=1536,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)

index = pc.Index("documents")

# Вставка векторов
vectors = [
    ("doc-001", embedding_1, {"title": "Introduction to ML", "category": "tech"}),
    ("doc-002", embedding_2, {"title": "Python Basics", "category": "programming"}),
]
index.upsert(vectors=vectors)

# Поиск с фильтрацией по метаданным
results = index.query(
    vector=query_embedding,
    top_k=5,
    filter={"category": {"$eq": "tech"}},
    include_metadata=True
)

for match in results.matches:
    print(f"Score: {match.score:.3f}, Title: {match.metadata['title']}")
```

### 4.2 Weaviate: векторная СУБД с GraphQL

```python
import weaviate
from weaviate.classes.config import Configure, Property, DataType

client = weaviate.connect_to_local()

# Создание коллекции с настройкой векторизатора
client.collections.create(
    name="Article",
    vectorizer_config=Configure.Vectorizer.text2vec_openai(),  # авто-эмбеддинги
    properties=[
        Property(name="title", data_type=DataType.TEXT),
        Property(name="content", data_type=DataType.TEXT),
        Property(name="category", data_type=DataType.TEXT),
    ]
)

collection = client.collections.get("Article")

# Вставка (Weaviate автоматически создаёт эмбеддинг)
collection.data.insert({
    "title": "Векторные базы данных",
    "content": "HNSW, IVF и другие алгоритмы ANN...",
    "category": "databases"
})

# Семантический поиск
result = collection.query.near_text(
    query="поиск похожих документов",
    limit=5,
    return_metadata=weaviate.classes.query.MetadataQuery(score=True)
)

for obj in result.objects:
    print(f"Score: {obj.metadata.score:.3f} - {obj.properties['title']}")

# Гибридный поиск (BM25 + vector)
result = collection.query.hybrid(
    query="векторный поиск ANN",
    limit=5,
    alpha=0.5  # 0=BM25, 1=vector, 0.5=50/50
)
```

### 4.3 Qdrant: высокопроизводительная векторная СУБД на Rust

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, 
    FieldCondition, MatchValue, SearchRequest
)
import numpy as np

client = QdrantClient(url="http://localhost:6333")

# Создание коллекции с HNSW
client.recreate_collection(
    collection_name="articles",
    vectors_config=VectorParams(
        size=384,  # MiniLM размерность
        distance=Distance.COSINE,
        hnsw_config={
            "m": 16,
            "ef_construct": 100,
            "full_scan_threshold": 10000
        }
    )
)

# Вставка векторов с payload
points = [
    PointStruct(
        id=i,
        vector=np.random.random(384).tolist(),
        payload={
            "title": f"Article {i}",
            "category": "tech" if i % 2 == 0 else "science",
            "views": i * 100,
            "published_at": "2024-01-15"
        }
    )
    for i in range(10000)
]

client.upsert(collection_name="articles", points=points)

# Поиск с фильтрацией по payload
query_vector = np.random.random(384).tolist()
results = client.search(
    collection_name="articles",
    query_vector=query_vector,
    query_filter=Filter(
        must=[
            FieldCondition(key="category", match=MatchValue(value="tech")),
            FieldCondition(key="views", range={"gte": 500})
        ]
    ),
    limit=10,
    with_payload=True
)

for r in results:
    print(f"ID: {r.id}, Score: {r.score:.3f}, Title: {r.payload['title']}")

# Scroll API для пагинации без деградации
scroll_results, next_offset = client.scroll(
    collection_name="articles",
    scroll_filter=Filter(must=[
        FieldCondition(key="category", match=MatchValue(value="tech"))
    ]),
    limit=100,
    offset=None  # начало
)
```

---

## 5. Сравнение векторных СУБД

| Параметр | pgvector | Pinecone | Weaviate | Qdrant | Milvus |
|---------|---------|---------|---------|-------|-------|
| Тип | PostgreSQL ext | Managed cloud | Self/Cloud | Self/Cloud | Self/Cloud |
| Язык реализации | C | ? | Go | Rust | Go/C++ |
| Алгоритмы | HNSW, IVFFlat | HNSW | HNSW | HNSW | HNSW, IVF, PQ |
| Фильтрация | SQL | Metadata filters | GraphQL | Payload filters | Expressions |
| Гибридный поиск | Через SQL | Нет | Да (alpha) | Да | Да |
| Масштабирование | Вертикальное | Авто | Горизонтальное | Горизонтальное | Горизонтальное |
| Лучший для | Существующий PG | Managed, быстрый старт | Мультимодальный | Производительность | Большой масштаб |

---

## 6. Производительность и выбор параметров

### 6.1 Метрики качества ANN

**Recall@k**: доля правильных ближайших соседей среди топ-k результатов:
```
Recall@10 = |ANN top-10 ∩ Exact top-10| / 10
```

**QPS (Queries Per Second)**: пропускная способность поиска.

Типичная кривая компромисса:
```
Recall  QPS
  99%   1,000
  97%   5,000
  95%   15,000
  90%   50,000
```

### 6.2 Бенчмарки ANN

Стандартный бенчмарк: [ann-benchmarks.com](http://ann-benchmarks.com) — сравнивает все алгоритмы на стандартных датасетах.

```python
# Пример оценки recall и QPS
import faiss
import numpy as np
import time

def evaluate_index(index, xb, xq, k=10, exact_index=None):
    if exact_index is None:
        exact_index = faiss.IndexFlatL2(xb.shape[1])
        exact_index.add(xb)
    
    # Точные результаты
    _, I_exact = exact_index.search(xq, k)
    
    # Приблизительные результаты
    start = time.perf_counter()
    _, I_approx = index.search(xq, k)
    elapsed = time.perf_counter() - start
    
    # Recall@k
    recalls = [
        len(set(I_approx[i]) & set(I_exact[i])) / k
        for i in range(len(xq))
    ]
    
    return {
        'recall': np.mean(recalls),
        'qps': len(xq) / elapsed,
        'latency_ms': elapsed * 1000 / len(xq)
    }
```

---

## Заключение

Векторные базы данных — необходимый инструмент эпохи больших языковых моделей и систем рекомендаций. Ключевые концепции: эмбеддинги кодируют семантику в числовые векторы; HNSW и IVF позволяют находить приблизительных ближайших соседей за миллисекунды среди миллионов векторов; Product Quantization сжимает векторы в 8-16x при приемлемой потере качества.

Для небольших проектов с существующим PostgreSQL — pgvector даёт 90% функциональности без новой инфраструктуры. Для высоконагруженных систем с миллиардами векторов — Milvus или Qdrant с горизонтальным масштабированием. RAG (Retrieval-Augmented Generation) — ключевой паттерн, где векторная СУБД служит «внешней памятью» LLM.

---

## Библиография

1. Malkov, Y.A., & Yashunin, D.A. (2018). Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 42(4), 824–836.
2. Jégou, H., Douze, M., & Schmid, C. (2011). Product Quantization for Nearest Neighbor Search. *IEEE TPAMI*, 33(1), 117–128.
3. Johnson, J., Douze, M., & Jégou, H. (2019). Billion-Scale Similarity Search with GPUs. *IEEE Transactions on Big Data*, 7(3).
4. Wang, J., et al. (2021). A Comprehensive Survey and Experimental Comparison of Graph-Based Approximate Nearest Neighbor Search. *VLDB 2021*.
5. Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*.
6. pgvector. (2021). Open-source vector similarity search for Postgres. https://github.com/pgvector/pgvector
7. ANN Benchmarks. (2024). Benchmarking Approximate Nearest Neighbor Algorithms. http://ann-benchmarks.com/
