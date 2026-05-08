# Поисковые движки: Lucene, Elasticsearch и инвертированный индекс

## Введение

Когда пользователь вводит «ноутбук для программирования» в строку поиска, он ожидает найти релевантные результаты — не строки, в которых встречаются именно эти слова в этом порядке. Реляционный оператор `LIKE '%ноутбук%'` не справится с синонимами, морфологией, опечатками и ранжированием по релевантности. Для этого существуют поисковые движки.

Apache Lucene — фундаментальная библиотека поиска, написанная Дугом Каттингом в 1999 году. Elasticsearch (2010) и OpenSearch (2021, форк) строятся поверх Lucene, добавляя распределённость, REST API и богатую экосистему. Понимание устройства Lucene — ключ к правильному использованию любого из этих инструментов.

---

## 1. Инвертированный индекс: фундамент поиска

### 1.1 Прямой vs инвертированный индекс

**Прямой индекс** (forward index): документ → список слов.
```
Doc 1: [ноутбук, программирование, быстрый, SSD]
Doc 2: [ноутбук, игровой, видеокарта, быстрый]
Doc 3: [программирование, Python, курс, быстрый]
```

Для поиска всех документов со словом «ноутбук» нужно просканировать все документы — O(N).

**Инвертированный индекс** (inverted index): слово → список документов.
```
ноутбук:        [Doc1, Doc2]
программирование: [Doc1, Doc3]
быстрый:        [Doc1, Doc2, Doc3]
SSD:            [Doc1]
```

Теперь поиск «ноутбук» → O(1) по хешу термина, результат — готовый posting list.

### 1.2 Структура инвертированного индекса Lucene

Lucene хранит несколько структур данных:

**Term Dictionary**: отсортированный словарь всех терминов с указателем на posting list. Хранится как FST (Finite State Transducer) — сжатый automaton для быстрого поиска.

**Posting List**: для каждого термина — список (docID, frequency, positions[]):
```
term "ноутбук":
  posting: [(docId=1, freq=2, pos=[0,15]), (docId=2, freq=1, pos=[3]), ...]
```

**Doc values**: колоночное хранение для сортировки и агрегаций (аналог columnar storage).

**Stored fields**: исходные значения полей для возврата в результатах поиска.

**Norms**: нормализационный фактор для TF-IDF (влияние длины документа).

```python
# Простая реализация инвертированного индекса на Python
from collections import defaultdict
import re
import math

class InvertedIndex:
    def __init__(self):
        self.index = defaultdict(list)  # term -> [(doc_id, positions)]
        self.docs = {}                  # doc_id -> original text
        self.doc_count = 0
    
    def tokenize(self, text: str) -> list:
        # Простая токенизация: нижний регистр + разбивка по не-буквам
        return re.findall(r'\b[а-яёa-z]+\b', text.lower())
    
    def add_document(self, text: str) -> int:
        doc_id = self.doc_count
        self.doc_count += 1
        self.docs[doc_id] = text
        
        tokens = self.tokenize(text)
        for pos, token in enumerate(tokens):
            # Добавляем позицию вхождения
            if not self.index[token] or self.index[token][-1][0] != doc_id:
                self.index[token].append((doc_id, [pos]))
            else:
                self.index[token][-1][1].append(pos)
        
        return doc_id
    
    def search(self, query: str) -> list:
        tokens = self.tokenize(query)
        if not tokens:
            return []
        
        # Начинаем с posting list первого токена
        result_ids = set(doc_id for doc_id, _ in self.index.get(tokens[0], []))
        
        # Пересечение для AND-семантики
        for token in tokens[1:]:
            token_ids = set(doc_id for doc_id, _ in self.index.get(token, []))
            result_ids &= token_ids
        
        return [self.docs[doc_id] for doc_id in sorted(result_ids)]
    
    def search_with_score(self, query: str) -> list:
        tokens = self.tokenize(query)
        scores = defaultdict(float)
        N = self.doc_count
        
        for token in tokens:
            postings = self.index.get(token, [])
            if not postings:
                continue
            
            df = len(postings)  # document frequency
            idf = math.log(N / df) if df > 0 else 0
            
            for doc_id, positions in postings:
                tf = len(positions)  # term frequency
                tf_idf = math.sqrt(tf) * idf  # BM25 упрощение
                scores[doc_id] += tf_idf
        
        sorted_results = sorted(scores.items(), key=lambda x: -x[1])
        return [(self.docs[doc_id], score) for doc_id, score in sorted_results]

# Использование
idx = InvertedIndex()
idx.add_document("Ноутбук для программирования с SSD и быстрым процессором")
idx.add_document("Игровой ноутбук с мощной видеокартой")
idx.add_document("Курс по программированию на Python")

results = idx.search_with_score("ноутбук программирование")
for text, score in results:
    print(f"Score {score:.2f}: {text}")
```

### 1.3 BM25: алгоритм ранжирования

TF-IDF — классический алгоритм, BM25 (Best Match 25, Robertson & Sparck Jones, 1994) — его улучшенная версия, используемая в Elasticsearch по умолчанию.

```
BM25(q, d) = Σ IDF(qi) × [tf(qi,d) × (k1+1)] / [tf(qi,d) + k1 × (1 - b + b × |d|/avgdl)]

где:
- tf(qi, d) — частота термина qi в документе d
- IDF(qi) = ln((N - df(qi) + 0.5) / (df(qi) + 0.5) + 1)
- |d| — длина документа
- avgdl — средняя длина документа
- k1 ≈ 1.2 (насыщение tf, большие значения = больше влияние частоты)
- b ≈ 0.75 (нормализация длины, 0 = нет нормализации)
```

BM25 улучшает TF-IDF двумя способами:
1. **Насыщение TF**: один термин, встречающийся 100 раз, ценится не в 100 раз больше, чем встречающийся 1 раз
2. **Нормализация длины**: длинный документ не получает незаслуженное преимущество

---

## 2. Анализаторы текста: tokenization pipeline

### 2.1 Цепочка анализа

Перед добавлением в индекс текст проходит цепочку преобразований:

```
"Быстрые коричневые лисы перепрыгнули через ленивых собак"
         │
    CharFilters (HTML strip, mapping)
    "Быстрые коричневые лисы перепрыгнули через ленивых собак"
         │
    Tokenizer (whitespace, standard, N-gram)
    ["Быстрые", "коричневые", "лисы", "перепрыгнули", "через", "ленивых", "собак"]
         │
    TokenFilters (lowercase, stopwords, stemming, synonyms)
    ["быстр", "коричнев", "лис", "перепрыгн", "лениv", "собак"]
    (стоп-слово "через" удалено, применён стемминг)
```

### 2.2 Настройка анализаторов в Elasticsearch

```json
PUT /products
{
  "settings": {
    "analysis": {
      "analyzer": {
        "russian_product_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "char_filter": ["html_strip"],
          "filter": [
            "lowercase",
            "russian_stop",
            "russian_stemmer",
            "product_synonyms"
          ]
        }
      },
      "filter": {
        "russian_stop": {
          "type": "stop",
          "stopwords": "_russian_"
        },
        "russian_stemmer": {
          "type": "stemmer",
          "language": "russian"
        },
        "product_synonyms": {
          "type": "synonym",
          "synonyms": [
            "ноутбук, лэптоп, laptop",
            "смартфон, телефон, мобильный"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "russian_product_analyzer",
        "search_analyzer": "russian_product_analyzer",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "price": { "type": "float" },
      "category": { "type": "keyword" },
      "tags": { "type": "keyword" }
    }
  }
}
```

### 2.3 N-gram анализатор для автодополнения

```json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "autocomplete_analyzer": {
          "tokenizer": "autocomplete_tokenizer",
          "filter": ["lowercase"]
        },
        "autocomplete_search": {
          "tokenizer": "lowercase"
        }
      },
      "tokenizer": {
        "autocomplete_tokenizer": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 10,
          "token_chars": ["letter", "digit"]
        }
      }
    }
  }
}
```

Edge N-gram «ноут» → [«но», «ноу», «ноут»] — позволяет искать по префиксу.

---

## 3. Elasticsearch: распределённый Lucene

### 3.1 Архитектура

Elasticsearch разбивает индекс на **shards** (шарды):
- **Primary shard**: основная копия данных
- **Replica shard**: дополнительные копии для отказоустойчивости

```
Индекс с 3 primary shards и 1 replica:
┌─────────────────────────────────────────┐
│                 Кластер                  │
│                                          │
│  Node 1: [P0][R1][R2]                   │
│  Node 2: [P1][R0][R2]                   │
│  Node 3: [P2][R0][R1]                   │
└─────────────────────────────────────────┘

Документ → hash(routing_key) % num_shards → shard index
```

При поиске: координирующий нод рассылает запрос всем primary shards → собирает top-N результатов → merges и возвращает.

### 3.2 Основные операции через Python клиент

```python
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import json

es = Elasticsearch(['http://localhost:9200'])

# Создание индекса
es.indices.create(
    index='products',
    body={
        'settings': {'number_of_shards': 3, 'number_of_replicas': 1},
        'mappings': {
            'properties': {
                'name': {'type': 'text', 'analyzer': 'russian'},
                'description': {'type': 'text', 'analyzer': 'russian'},
                'price': {'type': 'float'},
                'category': {'type': 'keyword'},
                'tags': {'type': 'keyword'},
                'in_stock': {'type': 'boolean'},
                'created_at': {'type': 'date'}
            }
        }
    }
)

# Пакетная индексация
products = [
    {'_index': 'products', '_id': i, '_source': {
        'name': f'Продукт {i}',
        'price': 100 + i * 10,
        'category': 'electronics' if i % 2 == 0 else 'clothing',
        'tags': ['новинка'] if i < 5 else [],
        'in_stock': True
    }}
    for i in range(100)
]
bulk(es, products)

# Full-text поиск
result = es.search(
    index='products',
    body={
        'query': {
            'multi_match': {
                'query': 'ноутбук программирование',
                'fields': ['name^2', 'description'],  # name в 2 раза важнее
                'type': 'best_fields',
                'fuzziness': 'AUTO'  # толерантность к опечаткам
            }
        },
        'highlight': {
            'fields': {'name': {}, 'description': {}}
        },
        'sort': [
            {'_score': {'order': 'desc'}},
            {'price': {'order': 'asc'}}
        ],
        'from': 0,
        'size': 10
    }
)

for hit in result['hits']['hits']:
    print(f"Score: {hit['_score']:.2f}, {hit['_source']['name']}")
    if 'highlight' in hit:
        print(f"  Highlight: {hit['highlight']}")

# Bool query: комбинация фильтров
result = es.search(
    index='products',
    body={
        'query': {
            'bool': {
                'must': [
                    {'match': {'name': 'ноутбук'}}
                ],
                'filter': [
                    {'term': {'category': 'electronics'}},
                    {'term': {'in_stock': True}},
                    {'range': {'price': {'gte': 500, 'lte': 2000}}}
                ],
                'should': [
                    {'term': {'tags': 'новинка'}}
                ],
                'must_not': [
                    {'term': {'tags': 'уценка'}}
                ]
            }
        }
    }
)
```

### 3.3 Агрегации: аналитика поверх поиска

```python
# Faceted search: фасеты для фильтрации в UI
result = es.search(
    index='products',
    body={
        'query': {'match': {'name': 'ноутбук'}},
        'aggs': {
            'categories': {
                'terms': {'field': 'category', 'size': 10}
            },
            'price_ranges': {
                'range': {
                    'field': 'price',
                    'ranges': [
                        {'to': 500},
                        {'from': 500, 'to': 1000},
                        {'from': 1000, 'to': 2000},
                        {'from': 2000}
                    ]
                }
            },
            'avg_price': {'avg': {'field': 'price'}},
            'price_histogram': {
                'histogram': {'field': 'price', 'interval': 200}
            }
        }
    }
)

# Вывод фасетов
for bucket in result['aggregations']['categories']['buckets']:
    print(f"Категория: {bucket['key']}, кол-во: {bucket['doc_count']}")
```

### 3.4 Fuzzy search и автодополнение

```python
# Поиск с опечатками
result = es.search(
    index='products',
    body={
        'query': {
            'fuzzy': {
                'name': {
                    'value': 'нотбук',  # опечатка
                    'fuzziness': 2,     # максимум 2 правки (Левенштейн)
                    'prefix_length': 3  # первые 3 символа точны
                }
            }
        }
    }
)

# Автодополнение с Completion suggester
es.indices.create(
    index='suggestions',
    body={
        'mappings': {
            'properties': {
                'suggest': {'type': 'completion'}
            }
        }
    }
)

# Индексация подсказок
es.index(index='suggestions', body={
    'suggest': {
        'input': ['ноутбук', 'ноутбук игровой', 'ноутбук для работы'],
        'weight': 10
    }
})

# Получение подсказок
result = es.search(
    index='suggestions',
    body={
        'suggest': {
            'product_suggest': {
                'prefix': 'ноут',
                'completion': {
                    'field': 'suggest',
                    'size': 5,
                    'skip_duplicates': True
                }
            }
        }
    }
)
```

---

## 4. Lucene сегменты: устройство на диске

### 4.1 Сегменты и слияние (merge)

Lucene организует индекс как набор **сегментов** — неизменяемых (immutable) структур данных. Когда буфер записей наполнен, он сбрасывается как новый сегмент. Поиск выполняется по всем сегментам параллельно с последующим объединением результатов.

```
t=0: [Segment 1 (1000 docs)]
t=1: [Segment 1][Segment 2 (500 docs)]
t=2: [Segment 1][Segment 2][Segment 3 (200 docs)]
t=3: Merge → [Segment 4 (1700 docs)]  ← фоновый merge
```

**Преимущества неизменяемости:**
- Нет конкурентных блокировок при чтении
- Файлы сегментов кешируются OS без инвалидации
- Простая реализация репликации (копирование файлов)

**Обработка удалений**: deleted docs помечаются в `.del` файле (bitmap), физически удаляются при merge.

### 4.2 Производительность индексации

```python
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, streaming_bulk
import time

es = Elasticsearch(['http://localhost:9200'],
                   request_timeout=60,
                   max_retries=3)

def bulk_index_generator(n=1_000_000):
    """Генератор документов для потоковой индексации"""
    for i in range(n):
        yield {
            '_index': 'logs',
            '_source': {
                'timestamp': '2024-01-01T00:00:00Z',
                'level': ['INFO', 'WARN', 'ERROR'][i % 3],
                'message': f'Log message number {i}',
                'service': f'service-{i % 10}'
            }
        }

# Оптимизированная пакетная индексация
start = time.time()
success_count = 0
error_count = 0

for ok, response in streaming_bulk(
    es,
    bulk_index_generator(),
    chunk_size=5000,         # 5000 документов за раз
    max_retries=2,
    request_timeout=30
):
    if ok:
        success_count += 1
    else:
        error_count += 1

elapsed = time.time() - start
print(f"Indexed {success_count} docs in {elapsed:.1f}s ({success_count/elapsed:.0f} docs/s)")
```

---

## 5. Семантический поиск и вектора

### 5.1 Ограничения классического поиска

Классический BM25-поиск не понимает семантики:
- «ноутбук» ≠ «лэптоп» (без синонимов)
- «купить телефон» ≠ «смартфон в наличии»
- «python для начинающих» ≠ «курс программирования»

### 5.2 Dense Vector Search в Elasticsearch

Elasticsearch 8+ поддерживает поиск по **dense vectors** (эмбеддингам) с использованием HNSW (Hierarchical Navigable Small World) индекса.

```python
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
import numpy as np

es = Elasticsearch(['http://localhost:9200'])
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# Создание индекса с вектором
es.indices.create(
    index='semantic_products',
    body={
        'mappings': {
            'properties': {
                'name': {'type': 'text'},
                'name_vector': {
                    'type': 'dense_vector',
                    'dims': 384,  # размерность MiniLM
                    'index': True,
                    'similarity': 'cosine'
                }
            }
        }
    }
)

# Индексация с генерацией эмбеддингов
products = [
    "Ноутбук Apple MacBook Pro M3",
    "Игровой лэптоп ASUS ROG",
    "Смартфон Samsung Galaxy S24",
    "Курс Python для начинающих",
    "Книга по программированию на Java"
]

for i, product in enumerate(products):
    vector = model.encode(product).tolist()
    es.index(
        index='semantic_products',
        id=i,
        body={
            'name': product,
            'name_vector': vector
        }
    )

def semantic_search(query: str, top_k: int = 5):
    query_vector = model.encode(query).tolist()
    
    result = es.search(
        index='semantic_products',
        body={
            'knn': {
                'field': 'name_vector',
                'query_vector': query_vector,
                'k': top_k,
                'num_candidates': top_k * 10
            }
        }
    )
    
    return [(h['_source']['name'], h['_score']) 
            for h in result['hits']['hits']]

# Гибридный поиск: BM25 + vector
def hybrid_search(query: str):
    query_vector = model.encode(query).tolist()
    
    result = es.search(
        index='semantic_products',
        body={
            'query': {
                'match': {'name': query}
            },
            'knn': {
                'field': 'name_vector',
                'query_vector': query_vector,
                'k': 10,
                'num_candidates': 50,
                'boost': 0.5  # вес vector score
            }
        }
    )
    return result['hits']['hits']

# "купить ноутбук" найдёт и MacBook, и ASUS ROG
results = semantic_search("купить ноутбук")
for name, score in results:
    print(f"Score: {score:.3f} - {name}")
```

---

## 6. Мониторинг и оптимизация Elasticsearch

### 6.1 Ключевые метрики

```python
# Состояние кластера
health = es.cluster.health()
print(f"Status: {health['status']}, Active shards: {health['active_shards']}")

# Статистика индекса
stats = es.indices.stats(index='products')
idx_stats = stats['indices']['products']['total']
print(f"Docs: {idx_stats['docs']['count']}")
print(f"Store size: {idx_stats['store']['size_in_bytes'] / 1e6:.1f} MB")
print(f"Search queries: {idx_stats['search']['query_total']}")
print(f"Search time: {idx_stats['search']['query_time_in_millis']}ms total")

# Медленные запросы
es.indices.put_settings(
    index='products',
    body={
        'index.search.slowlog.threshold.query.warn': '5s',
        'index.search.slowlog.threshold.query.info': '1s',
        'index.search.slowlog.level': 'info'
    }
)

# Принудительный merge для уменьшения числа сегментов (read-only индексы)
es.indices.forcemerge(index='products', max_num_segments=1)
```

### 6.2 Типичные ошибки и антипаттерны

**Слишком много шардов**: каждый шард — это отдельный Lucene-индекс, overhead на метаданные. Рекомендация: 10-50 GB на шард.

**Поиск по keyword без индекса**: `SELECT * WHERE not_indexed_field = 'value'` → полный скан всех документов.

**Глубокая пагинация**: `from=9990, size=10` → каждый шард возвращает 10000 результатов, координатор обрабатывает `num_shards × 10000`. Используйте `search_after` для cursor-based pagination.

**Частые маленькие индексации**: создают много мелких сегментов. Оптимально: пакеты по 5–15 МБ.

---

## Заключение

Поисковые движки на основе Lucene решают задачи, недоступные реляционным СУБД: полнотекстовый поиск с морфологией, ранжирование по релевантности, фасетный поиск, автодополнение с опечатками.

Ключевые концепции: инвертированный индекс (терм → posting list), анализ текста (tokenizer + filters), BM25 для ранжирования, неизменяемые сегменты Lucene с фоновым merge.

Elasticsearch добавляет к Lucene распределённость через шардирование, богатый DSL для запросов, агрегации (аналитика) и поддержку dense vectors для семантического поиска. Современные системы всё чаще используют гибридный поиск: BM25 + векторные эмбеддинги для оптимального баланса между точностью и семантическим пониманием.

---

## Библиография

1. Manning, C., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press.
2. Robertson, S., & Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. *Foundations and Trends in Information Retrieval*, 3(4), 333–389.
3. McCandless, M., Hatcher, E., & Gospodnetic, O. (2010). *Lucene in Action* (2nd ed.). Manning.
4. Gormley, C., & Tong, Z. (2015). *Elasticsearch: The Definitive Guide*. O'Reilly Media.
5. Karpukhin, V., et al. (2020). Dense Passage Retrieval for Open-Domain Question Answering. *EMNLP 2020*.
6. Malkov, Y.A., & Yashunin, D.A. (2018). Efficient and Robust Approximate Nearest Neighbor Search Using HNSW. *IEEE TPAMI*, 42(4), 824–836.
7. Elastic. (2024). Elasticsearch Documentation. https://www.elastic.co/guide/en/elasticsearch/reference/current/
