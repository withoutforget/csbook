# Векторные базы данных и приближённый поиск ближайших соседей: основа RAG

Представьте библиотеку с миллионом книг. Вам нужно найти книги, похожие по содержанию на заданную — не по названию, а по смыслу. Простой перебор займёт часы. Именно эту задачу решают векторные базы данных с алгоритмами ANN (Approximate Nearest Neighbor). Сегодня это основа семантического поиска, рекомендаций и RAG-систем для LLM.

## Почему точный поиск ближайших соседей не работает

Точный поиск ближайших соседей (Exact KNN) прост: для каждого запроса вычислить расстояние до всех N векторов в базе и вернуть топ-K ближайших.

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def exact_knn(query_vector, database, k=5):
    """Точный поиск: O(N × d)"""
    similarities = cosine_similarity(
        query_vector.reshape(1, -1), 
        database
    )[0]
    top_k_idx = np.argsort(similarities)[-k:][::-1]
    return top_k_idx, similarities[top_k_idx]

# Производительность:
# N = 1M векторов, d = 768 (BERT)
# Одна операция: 1M × 768 × float_ops ≈ 1.5 секунды на CPU
# При 100 запросов/с: 150 CPU в постоянной нагрузке!
```

При росте базы до миллиардов векторов (как в Pinterest, Spotify, Facebook) точный поиск становится нереальным. Нужен компромисс: **ANN (Approximate Nearest Neighbor)** — результаты близкие к точным, но в тысячи раз быстрее.

## LSH: Locality-Sensitive Hashing

LSH (Locality-Sensitive Hashing) — идея: похожие векторы с высокой вероятностью попадают в один "хэш-бакет".

```python
import numpy as np

class LSHIndex:
    def __init__(self, dim, n_hash_tables=10, hash_size=8):
        """
        n_hash_tables: количество хэш-таблиц (больше = точнее, медленнее)
        hash_size: количество бит в хэше (больше = меньше коллизий)
        """
        self.hash_tables = []
        self.projections = []
        
        for _ in range(n_hash_tables):
            # Случайные гиперплоскости для хэширования
            projection = np.random.randn(hash_size, dim)
            self.projections.append(projection)
            self.hash_tables.append({})
    
    def _hash(self, vector, projection):
        """Хэш через случайные проекции"""
        projections = projection @ vector  # (hash_size,)
        return tuple((projections > 0).astype(int))
    
    def add(self, vector, item_id):
        for i, (proj, table) in enumerate(zip(self.projections, self.hash_tables)):
            h = self._hash(vector, proj)
            if h not in table:
                table[h] = []
            table[h].append(item_id)
    
    def query(self, query_vector, k=5):
        """Поиск кандидатов из тех же бакетов"""
        candidates = set()
        for proj, table in zip(self.projections, self.hash_tables):
            h = self._hash(query_vector, proj)
            if h in table:
                candidates.update(table[h])
        return list(candidates)  # Затем точный поиск среди кандидатов
```

Проблема LSH: сложно настроить для высокой точности. HNSW вытеснил LSH в большинстве приложений.

## HNSW: Hierarchical Navigable Small World

HNSW (Hierarchical Navigable Small World, Malkov & Yashunin, 2016) — наиболее эффективный алгоритм ANN на практике. Идея вдохновлена феноменом "шести рукопожатий": любые два человека связаны через цепочку из ~6 знакомств.

### Структура HNSW

```
Уровень 2 (мало узлов, длинные связи):
  A ──────────── B ─────────────── C

Уровень 1 (больше узлов, средние связи):
  A ──── D ──── B ──── E ──── C ──── F

Уровень 0 (все узлы, короткие связи):
  A ─ G ─ D ─ H ─ B ─ I ─ E ─ J ─ C ─ K ─ F
```

Поиск начинается с верхнего уровня (грубое приближение) и спускается вниз (уточнение).

```python
# HNSW реализован в hnswlib (C++ с Python bindings)
import hnswlib
import numpy as np

dim = 768  # Размерность вектора
n_elements = 1_000_000  # Количество элементов

# Создание индекса
index = hnswlib.Index(space='cosine', dim=dim)
index.init_index(
    max_elements=n_elements,
    ef_construction=200,  # Точность при построении (выше = точнее, но дольше)
    M=16                   # Количество двунаправленных связей на уровень
)

# Добавление векторов
embeddings = np.random.rand(n_elements, dim).astype('float32')
labels = np.arange(n_elements)
index.add_items(embeddings, labels)

# Настройка точности при поиске
index.set_ef(50)  # ef >= k; выше = точнее, но медленнее

# Поиск K ближайших
query = np.random.rand(1, dim).astype('float32')
k = 10

labels_result, distances = index.knn_query(query, k=k)
print(f"Top-{k} neighbours: {labels_result}")
print(f"Distances: {distances}")

# Сохранение/загрузка индекса
index.save_index("hnsw_index.bin")
index_loaded = hnswlib.Index(space='cosine', dim=dim)
index_loaded.load_index("hnsw_index.bin", max_elements=n_elements)
```

### Параметры HNSW

| Параметр | Описание | Влияние |
|---|---|---|
| M | Количество связей | Больше = лучше recall, больше памяти |
| ef_construction | Точность построения | Больше = лучше индекс, дольше строится |
| ef (поиска) | Кандидаты при поиске | Больше = точнее, медленнее |

```
Типичные значения:
M = 16-64
ef_construction = 100-400
ef = 50-500 (зависит от требований recall)
```

## FAISS: библиотека Meta для ANN

FAISS (Facebook AI Similarity Search) — открытая библиотека для эффективного поиска в плотных векторных пространствах. Поддерживает CPU и GPU.

### Типы индексов FAISS

```python
import faiss
import numpy as np

d = 768       # Размерность
n = 1_000_000 # Количество векторов

vectors = np.random.rand(n, d).astype('float32')
faiss.normalize_L2(vectors)  # Для cosine similarity нормализуем → L2 distance = 2(1-cos)

# 1. IndexFlatL2: точный поиск (baseline, медленно)
index_flat = faiss.IndexFlatL2(d)
index_flat.add(vectors)
# Хорошо для N < 100K, требует O(N×d) памяти

# 2. IndexIVFFlat: IVF + точный поиск в кластерах
# Обучение: k-means разделяет векторы на nlist кластеров
nlist = 1024  # Количество кластеров
quantizer = faiss.IndexFlatL2(d)
index_ivf = faiss.IndexIVFFlat(quantizer, d, nlist)
index_ivf.train(vectors)  # Обязательно!
index_ivf.add(vectors)
index_ivf.nprobe = 10  # Искать в 10 ближайших кластерах (точность/скорость)

# 3. IndexIVFPQ: IVF + Product Quantization (сжатие)
# Экономит память в 32x и более!
M_pq = 8   # Количество субпространств
nbits = 8  # Бит на субпространство (256 центроидов)
index_ivfpq = faiss.IndexIVFPQ(quantizer, d, nlist, M_pq, nbits)
index_ivfpq.train(vectors)
index_ivfpq.add(vectors)
# Вектор 768×4 байт = 3072 байт → 8 байт (в 384 раза меньше!)

# 4. IndexHNSWFlat: HNSW в FAISS
index_hnsw = faiss.IndexHNSWFlat(d, 32)  # M=32
index_hnsw.add(vectors)
# Нет train(), работает сразу

# Поиск
k = 10
query = np.random.rand(1, d).astype('float32')
faiss.normalize_L2(query)

distances, indices = index_flat.search(query, k)
print(f"Nearest neighbours: {indices}")
print(f"Distances: {distances}")
```

### Product Quantization: сжатие векторов

```
Вектор 768-мерный делится на M=8 субпространств по 96 измерений.
Каждое субпространство: 256 центроидов (8 бит).

Хранение оригинального вектора: 768 × 4 байт = 3072 байт
После PQ: 8 × 1 байт = 8 байт (в 384 раза меньше!)

Для 1 миллиарда векторов:
Без PQ: 3072 GB ≈ 3 TB RAM
С PQ:   8 GB RAM (помещается!)
```

### GPU-ускорение FAISS

```python
# FAISS с GPU
res = faiss.StandardGpuResources()  # Ресурсы GPU
gpu_index = faiss.index_cpu_to_gpu(res, 0, index_flat)

# Поиск на GPU (в 10-100x быстрее CPU)
distances, indices = gpu_index.search(queries, k)

# Все GPU
gpu_index = faiss.index_cpu_to_all_gpus(index_flat)
```

## ScaNN: Google's Scalable Nearest Neighbors

ScaNN (Scalable Nearest Neighbors) — разработка Google, показывающая лучшее соотношение recall/скорость на многих бенчмарках:

```python
import scann

searcher = scann.scann_ops_pybind.builder(
    database_vectors,    # float32 array (N, d)
    num_neighbors=10,
    distance_measure="dot_product"
).tree(
    num_leaves=2000,           # ~sqrt(N)
    num_leaves_to_search=100   # nprobe аналог
).score_ah(
    2,               # AH = asymmetric hashing
    anisotropic_quantization_threshold=0.2
).reorder(100).build()

neighbours, distances = searcher.search(query_vector, final_num_neighbors=10)
```

## pgvector: PostgreSQL расширение

pgvector добавляет тип `vector` и операторы поиска прямо в PostgreSQL:

```sql
-- Установка расширения
CREATE EXTENSION IF NOT EXISTS vector;

-- Создание таблицы с вектором
CREATE TABLE documents (
    id        BIGSERIAL PRIMARY KEY,
    content   TEXT,
    embedding VECTOR(1536)  -- OpenAI ada-002 размерность
);

-- Индекс для ANN поиска (HNSW)
CREATE INDEX ON documents 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Индекс IVFFlat
CREATE INDEX ON documents 
USING ivfflat (embedding vector_l2_ops) 
WITH (lists = 100);

-- Поиск K ближайших соседей
SELECT 
    id, 
    content,
    embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM documents
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;

-- Операторы:
-- <=>  cosine distance
-- <->  L2 (Euclidean) distance
-- <#>  negative inner product (dot product для нормализованных)
```

```python
# Python: psycopg2 + pgvector
import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np

conn = psycopg2.connect(dsn)
register_vector(conn)

# Вставка вектора
embedding = np.array([0.1, 0.2, ...])  # float32
with conn.cursor() as cur:
    cur.execute(
        "INSERT INTO documents (content, embedding) VALUES (%s, %s)",
        ("Текст документа", embedding)
    )

# Поиск
query_embedding = np.array([0.15, 0.18, ...])
with conn.cursor() as cur:
    cur.execute(
        "SELECT id, content, 1-(embedding <=> %s) AS similarity "
        "FROM documents ORDER BY embedding <=> %s LIMIT %s",
        (query_embedding, query_embedding, 5)
    )
    results = cur.fetchall()
```

## Managed Vector Databases

### Основные решения

**Pinecone**: полностью управляемый, облачный, REST API:

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="YOUR_API_KEY")

# Создание индекса
pc.create_index(
    name="documents",
    dimension=1536,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)

index = pc.Index("documents")

# Upsert
index.upsert(vectors=[
    ("doc1", embedding1, {"text": "...", "source": "wiki"}),
    ("doc2", embedding2, {"text": "...", "source": "book"}),
])

# Query
results = index.query(
    vector=query_embedding, 
    top_k=5,
    include_metadata=True,
    filter={"source": {"$eq": "wiki"}}  # Метаданные-фильтрация
)
```

**Weaviate**: open-source с богатым функционалом:

```python
import weaviate

client = weaviate.Client("http://localhost:8080")

# Семантический поиск
result = client.query.get(
    "Document", ["text", "source"]
).with_near_text({
    "concepts": ["машинное обучение"],
    "certainty": 0.7
}).with_limit(5).do()
```

**Qdrant**: open-source, Rust, гибкий:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

client = QdrantClient("localhost", port=6333)

client.create_collection(
    "documents",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
)

client.upsert(
    collection_name="documents",
    points=[
        PointStruct(id=1, vector=embedding1, payload={"text": "..."}),
    ]
)

results = client.search(
    collection_name="documents",
    query_vector=query_embedding,
    limit=5
)
```

**Chroma**: минималистичный, отлично для прототипирования:

```python
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("documents")

collection.add(
    documents=["Текст 1", "Текст 2"],
    embeddings=[emb1, emb2],
    ids=["id1", "id2"]
)

results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5
)
```

## RAG: Retrieval-Augmented Generation

RAG (Retrieval-Augmented Generation) — архитектура для "заземления" LLM на актуальных данных. Векторная БД — сердце RAG:

```python
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain.text_splitter import RecursiveCharacterTextSplitter

# === PIPELINE INGESTION (один раз) ===

# 1. Загрузка документов
documents = load_documents("./knowledge_base/")

# 2. Разбивка на чанки
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)
chunks = text_splitter.split_documents(documents)

# 3. Создание эмбеддингов и сохранение в векторной БД
embeddings = OpenAIEmbeddings()
vectordb = Chroma.from_documents(
    chunks, 
    embeddings,
    persist_directory="./chroma_db"
)

# === PIPELINE QUERY (каждый запрос) ===

# 1. Эмбеддинг запроса
# 2. ANN поиск в векторной БД → топ-K релевантных чанков
# 3. Формирование промпта: контекст из документов + вопрос пользователя
# 4. LLM генерирует ответ на основе контекста

llm = ChatOpenAI(model="gpt-4o", temperature=0)
retriever = vectordb.as_retriever(
    search_type="mmr",  # Maximum Marginal Relevance: diversity + relevance
    search_kwargs={"k": 5, "fetch_k": 20}
)

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=retriever,
    return_source_documents=True
)

result = qa_chain.invoke({"query": "Как работает HNSW?"})
print(result["result"])
print("Sources:", [doc.metadata["source"] for doc in result["source_documents"]])
```

### Типичная RAG архитектура

```
Вопрос пользователя
        ↓
[Embedding Model] (e.g. text-embedding-3-small)
        ↓
[Query Vector]
        ↓
[Vector DB] ─── ANN поиск ───► [Топ-K чанков] ──┐
                                                   │
                                                   ↓
Вопрос пользователя ──────────────────────► [LLM Prompt]
                                                   │
                                                   ↓
                                            [Ответ LLM]
```

## Сравнение решений

| Решение | Тип | Алгоритм | Масштаб | Применение |
|---|---|---|---|---|
| FAISS | Библиотека | IVF, HNSW, PQ | Миллиарды | ML прод., офлайн |
| hnswlib | Библиотека | HNSW | Миллионы | Python проекты |
| ScaNN | Библиотека | AH+Tree | Миллиарды | Google продукты |
| pgvector | PostgreSQL ext | HNSW, IVF | Миллионы | Уже есть Postgres |
| Pinecone | Cloud SaaS | Проприетарный | Миллиарды | Без devops |
| Weaviate | Open-source | HNSW | Миллиарды | Гибкий поиск |
| Qdrant | Open-source | HNSW | Миллиарды | Rust, фильтрация |
| Chroma | Open-source | HNSW (hnswlib) | Миллионы | Прототипирование |

## Итог

ANN и векторные БД — инфраструктура семантического поиска эпохи LLM:

1. **Точный KNN** — $O(N \times d)$, неэффективен при N > 100K
2. **HNSW** — лучший recall/latency на практике; граф с иерархией уровней
3. **FAISS** — библиотека Meta с GPU-ускорением; IVF, PQ для миллиардов векторов
4. **Product Quantization** — сжатие в 100-400 раз с ~5% потери recall
5. **pgvector** — если уже используется PostgreSQL
6. **Managed DB** (Pinecone, Weaviate, Qdrant) — для production без DevOps векторного хранилища
7. **RAG** — embed query → ANN search → LLM с контекстом

## Литература

1. Malkov, Y.A., Yashunin, D.A. (2018). *Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs*. IEEE TPAMI. https://arxiv.org/abs/1603.09320

2. Johnson, J., Douze, M., Jégou, H. (2019). *Billion-scale similarity search with GPUs*. IEEE Transactions on Big Data. https://arxiv.org/abs/1702.08734

3. Guo, R., et al. (2020). *Accelerating Large-Scale Inference with Anisotropic Vector Quantization* (ScaNN). ICML 2020. https://arxiv.org/abs/1908.10396

4. Jégou, H., Douze, M., Schmid, C. (2011). *Product Quantization for Nearest Neighbor Search*. IEEE TPAMI.

5. Lewis, P., et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS 2020. https://arxiv.org/abs/2005.11401

6. FAISS documentation. https://faiss.ai/

7. pgvector. *Open-source vector similarity search for Postgres*. https://github.com/pgvector/pgvector

8. Qdrant documentation. https://qdrant.tech/documentation/

9. Pinecone. *Vector database guide*. https://www.pinecone.io/learn/vector-database/

10. LangChain. *Retrieval documentation*. https://python.langchain.com/docs/modules/data_connection/
