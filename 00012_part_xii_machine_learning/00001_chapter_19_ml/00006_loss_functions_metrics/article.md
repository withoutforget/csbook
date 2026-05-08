# Loss-функции и метрики: accuracy, precision, recall, F1, ROC-AUC

Выбор правильной функции потерь и метрики оценки — не технический детайл, а архитектурное решение, определяющее, что именно будет оптимизировать ваша модель. Модель с 99% accuracy на задаче обнаружения рака может быть бесполезной. Метрика должна соответствовать бизнес-цели. Функция потерь должна быть дифференцируемой и выпуклой.

## Зачем разные функции потерь

Функция потерь (loss function) — то, что оптимизирует градиентный спуск. Метрика оценки — то, что мы хотим максимизировать/минимизировать на практике. Эти две вещи часто различаются:

```
Задача: Классификация спама
Хотим максимизировать: accuracy или F1
Используем для обучения: Cross-Entropy (дифференцируемая)

Задача: Ранжирование результатов поиска
Хотим максимизировать: NDCG (не дифференцируема)
Используем для обучения: LambdaRank или другой surrogate loss
```

## Регрессионные функции потерь

### MSE (Mean Squared Error)

```
MSE = (1/n) Σ (yᵢ - ŷᵢ)²

Производная: ∂MSE/∂ŷ = -(2/n)(yᵢ - ŷᵢ)
```

Плюсы: выпуклая, дифференцируемая, хорошо работает с нормально распределёнными ошибками.

Минусы: сильно наказывает выбросы (квадрат!).

```python
import numpy as np
import torch
import torch.nn as nn

# NumPy
def mse(y_true, y_pred):
    return np.mean((y_true - y_pred) ** 2)

# PyTorch
criterion = nn.MSELoss()
loss = criterion(y_pred, y_true)
```

### MAE (Mean Absolute Error)

```
MAE = (1/n) Σ |yᵢ - ŷᵢ|

Производная: ±1 (знак ошибки)
```

Плюсы: устойчив к выбросам (линейный, а не квадратичный штраф).
Минусы: недифференцируем в нуле, менее теоретически обоснован.

### Huber Loss: компромисс MSE и MAE

```
Lδ(y, ŷ) = {
    (1/2)(y - ŷ)²           если |y - ŷ| ≤ δ  (квадратичный)
    δ|y - ŷ| - (1/2)δ²      если |y - ŷ| > δ  (линейный)
}
```

Huber Loss квадратичен для малых ошибок (точная оптимизация) и линеен для больших (устойчивость к выбросам):

```python
criterion = nn.HuberLoss(delta=1.0)
loss = criterion(y_pred, y_true)

# Или SmoothL1Loss (Huber с δ=1)
criterion = nn.SmoothL1Loss()
```

### Log-Cosh Loss

```
log-cosh(y, ŷ) = Σ log(cosh(ŷᵢ - yᵢ))
cosh(x) = (eˣ + e⁻ˣ) / 2
```

Дважды дифференцируема (в отличие от Huber), аппроксимирует MAE для больших ошибок и MSE для малых.

## Классификационные функции потерь

### Binary Cross-Entropy (BCE)

```
BCE = -(1/n) Σ [yᵢ log(ŷᵢ) + (1 - yᵢ) log(1 - ŷᵢ)]

Предполагает: ŷ ∈ (0, 1) (вероятности)
```

```python
# Pytorch: сигмоид + BCE вместе (численно стабильнее)
criterion = nn.BCEWithLogitsLoss()  # принимает logits (до sigmoid)!
loss = criterion(logits, targets.float())

# По весам для несбалансированных классов
pos_weight = torch.tensor([n_neg / n_pos])
criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
```

### Categorical Cross-Entropy

```
CCE = -(1/n) Σᵢ Σₖ yᵢₖ log(p̂ᵢₖ)

Для one-hot labels:
CCE = -(1/n) Σᵢ log(p̂ᵢ,true_class)
```

```python
# Стандарт для мультиклассовой классификации
criterion = nn.CrossEntropyLoss()
# Принимает LOGITS (до softmax)! Не вероятности!
loss = criterion(logits, targets)  # targets: class indices (0, 1, 2, ...)

# С весами классов для несбалансированного датасета
class_weights = torch.tensor([1.0, 2.0, 5.0])  # 3 класса, третий редкий
criterion = nn.CrossEntropyLoss(weight=class_weights)
```

### Focal Loss

Focal Loss (Lin et al., RetinaNet 2017) — модификация BCE для сильно несбалансированных задач (например, детекция объектов, где фон ≫ объекты):

```
FL(pₜ) = -α(1 - pₜ)^γ log(pₜ)

pₜ = p для y=1, (1-p) для y=0
(1-pₜ)^γ — фокусирующий множитель
  γ=0: обычная BCE
  γ=2: легко классифицируемые примеры получают маленький вес
```

```python
def focal_loss(logits, targets, alpha=0.25, gamma=2.0):
    p = torch.sigmoid(logits)
    ce_loss = F.binary_cross_entropy_with_logits(logits, targets, reduction='none')
    p_t = p * targets + (1 - p) * (1 - targets)
    
    alpha_t = alpha * targets + (1 - alpha) * (1 - targets)
    focal_weight = alpha_t * (1 - p_t) ** gamma
    
    return (focal_weight * ce_loss).mean()
```

### Hinge Loss (SVM)

```
L(y, ŷ) = max(0, 1 - y × ŷ)

y ∈ {-1, +1}, ŷ — decision score (не вероятность!)
```

Hinge loss используется в SVM: штрафует только "нарушителей margin".

```python
criterion = nn.HingeEmbeddingLoss()
# Или:
loss = torch.clamp(1 - y_true * y_pred, min=0).mean()
```

## Metric Learning: Contrastive и Triplet Loss

Для задач "похожесть/различие" (face recognition, image retrieval):

### Contrastive Loss

```python
def contrastive_loss(emb1, emb2, labels, margin=1.0):
    """
    labels: 1 = похожая пара, 0 = непохожая
    """
    distance = F.pairwise_distance(emb1, emb2)
    
    # Похожие пары: минимизируем расстояние
    pos_loss = labels * distance**2
    
    # Непохожие пары: максимизируем (до margin)
    neg_loss = (1 - labels) * torch.clamp(margin - distance, min=0)**2
    
    return (pos_loss + neg_loss).mean() / 2
```

### Triplet Loss

```python
def triplet_loss(anchor, positive, negative, margin=1.0):
    """
    anchor:   базовый пример
    positive: похожий пример
    negative: непохожий пример
    """
    pos_dist = F.pairwise_distance(anchor, positive)
    neg_dist = F.pairwise_distance(anchor, negative)
    
    # Хотим: dist(a,p) + margin < dist(a,n)
    return torch.clamp(pos_dist - neg_dist + margin, min=0).mean()

# Реальный пример: обучение face embeddings
# Каждый batc содержит тройки: (face_A1, face_A2, face_B)
# face_A1 и face_A2 — один человек, face_B — другой
```

## Метрики классификации

### Confusion Matrix

```
                  Predicted
                  Positive  Negative
Actual  Positive    TP        FN
        Negative    FP        TN

TP = True Positive  (правильно предсказали +)
TN = True Negative  (правильно предсказали -)
FP = False Positive (неправильно предсказали + → ошибка 1 рода)
FN = False Negative (неправильно предсказали - → ошибка 2 рода)
```

### Accuracy

```
Accuracy = (TP + TN) / (TP + TN + FP + FN)
```

**Когда обманывает**: при несбалансированных классах:

```python
# 99% данных — класс 0, 1% — класс 1 (болезнь)
# Модель, всегда предсказывающая 0:
# Accuracy = 99% — отлично! Но ни один больной не найден.

y_true = np.array([0]*99 + [1]*1)
y_pred = np.zeros(100)

from sklearn.metrics import accuracy_score
print(accuracy_score(y_true, y_pred))  # 0.99 — обманчивое значение!
```

### Precision, Recall, F1

```
Precision = TP / (TP + FP)  → Насколько предсказанные + верны?
Recall    = TP / (TP + FN)  → Какую долю реальных + мы нашли?
F1        = 2 × Precision × Recall / (Precision + Recall)

F_β       = (1 + β²) × P × R / (β²P + R)
β=1: равный вес P и R
β=2: R важнее P (β²=4× больший вес recall)
β=0.5: P важнее R
```

```python
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    classification_report, confusion_matrix
)

y_pred = model.predict(X_test)

# Для бинарной классификации
print(f"Precision: {precision_score(y_test, y_pred):.3f}")
print(f"Recall:    {recall_score(y_test, y_pred):.3f}")
print(f"F1:        {f1_score(y_test, y_pred):.3f}")

# Полный отчёт
print(classification_report(y_test, y_pred, 
                             target_names=['Нет болезни', 'Болезнь']))

# Confusion matrix
cm = confusion_matrix(y_test, y_pred)
print(cm)
```

### Micro, Macro, Weighted F1

```python
# Мультиклассовые метрики

# Macro: среднее F1 по классам (одинаковый вес)
f1_macro = f1_score(y_test, y_pred, average='macro')

# Weighted: среднее F1 взвешенное по числу примеров класса
f1_weighted = f1_score(y_test, y_pred, average='weighted')

# Micro: глобальные TP, FP, FN (не разделяя по классам)
f1_micro = f1_score(y_test, y_pred, average='micro')
# Для несбалансированных классов: weighted обычно лучший выбор
```

### ROC Curve и AUC

ROC (Receiver Operating Characteristic) показывает tradeoff между TPR и FPR при изменении порога:

```
TPR = Recall = TP / (TP + FN)  (True Positive Rate)
FPR = FP / (FP + TN)           (False Positive Rate)

Идеальный классификатор: AUC = 1.0 (верхний левый угол)
Случайный: AUC = 0.5 (диагональ)
```

```python
from sklearn.metrics import roc_curve, roc_auc_score
import matplotlib.pyplot as plt

y_prob = model.predict_proba(X_test)[:, 1]  # Вероятности класса 1

fpr, tpr, thresholds = roc_curve(y_test, y_prob)
auc = roc_auc_score(y_test, y_prob)

plt.figure(figsize=(8, 6))
plt.plot(fpr, tpr, 'b-', label=f'ROC (AUC = {auc:.3f})')
plt.plot([0, 1], [0, 1], 'k--', label='Random')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate (Recall)')
plt.title('ROC Curve')
plt.legend()

# Выбор оптимального порога (по индексу Юдена)
optimal_idx = np.argmax(tpr - fpr)
optimal_threshold = thresholds[optimal_idx]
print(f"Optimal threshold: {optimal_threshold:.3f}")
```

AUC интерпретация: вероятность, что случайный положительный пример получит более высокую оценку, чем случайный отрицательный.

### Precision-Recall Curve

При сильном дисбалансе классов ROC-AUC может быть оптимистичным. Precision-Recall кривая честнее:

```python
from sklearn.metrics import precision_recall_curve, average_precision_score

precision, recall, thresholds = precision_recall_curve(y_test, y_prob)
ap = average_precision_score(y_test, y_prob)  # Average Precision

plt.plot(recall, precision, label=f'PR curve (AP={ap:.3f})')
plt.xlabel('Recall')
plt.ylabel('Precision')

# При очень малом классе (1% данных):
# Random classifier: AUC ≈ 0.5 (выглядит неплохо!)
# Random classifier: AP ≈ 0.01 (честно показывает бесполезность)
```

## Метрики для задач компьютерного зрения

### AP и mAP (Detection)

mAP (mean Average Precision) — стандартная метрика для object detection:

```python
# Для каждого класса вычисляем AP:
# 1. Сортируем детекции по confidence (убывание)
# 2. Вычисляем Precision/Recall при каждом пороге
# 3. AP = площадь под PR-кривой

# mAP = среднее AP по всем классам

# IoU (Intersection over Union) используется для matching:
def iou(box1, box2):
    """box = (x1, y1, x2, y2)"""
    x1_i = max(box1[0], box2[0])
    y1_i = max(box1[1], box2[1])
    x2_i = min(box1[2], box2[2])
    y2_i = min(box1[3], box2[3])
    
    intersection = max(0, x2_i-x1_i) * max(0, y2_i-y1_i)
    area1 = (box1[2]-box1[0]) * (box1[3]-box1[1])
    area2 = (box2[2]-box2[0]) * (box2[3]-box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0

# COCO mAP: среднее по IoU порогам [0.5, 0.55, ..., 0.95]
# PASCAL VOC mAP: только при IoU > 0.5
```

## Метрики для NLP

### BLEU Score (Машинный перевод)

```python
from nltk.translate.bleu_score import corpus_bleu

references = [["the quick brown fox"]]  # Эталонный перевод
hypothesis = ["the fast brown fox"]    # Перевод модели

# BLEU-4: n-gram precision для n=1,2,3,4
from nltk.translate.bleu_score import sentence_bleu
score = sentence_bleu(references, hypothesis.split(), 
                      weights=(0.25, 0.25, 0.25, 0.25))
print(f"BLEU-4: {score:.3f}")
```

### ROUGE (Суммаризация)

```python
from rouge_score import rouge_scorer

scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
scores = scorer.score(
    "The quick brown fox jumps over the lazy dog",  # Эталон
    "The fast brown fox leaped over the tired dog"  # Предсказание
)

print(scores['rouge1'])   # Precision, Recall, F1 по unigrams
print(scores['rouge2'])   # По bigrams
print(scores['rougeL'])   # По longest common subsequence
```

## Метрики ранжирования: NDCG

NDCG (Normalized Discounted Cumulative Gain) — для рекомендательных систем и поиска:

```python
import numpy as np

def ndcg(relevances, k=None):
    """
    relevances: [rel1, rel2, ...] в порядке ранжирования
    Значения: 0 (нерелевантно), 1-3 (степень релевантности)
    """
    if k:
        relevances = relevances[:k]
    
    dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(relevances))
    
    # Идеальный DCG (отсортированный по убыванию)
    ideal_relevances = sorted(relevances, reverse=True)
    idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_relevances))
    
    return dcg / idcg if idcg > 0 else 0

# Пример: топ-5 результатов поиска
system_ranking = [3, 0, 1, 2, 1]  # релевантности результатов системы
ideal_ranking  = [3, 2, 1, 1, 0]  # идеальный порядок

print(f"NDCG@5: {ndcg(system_ranking, k=5):.3f}")
print(f"Ideal:  {ndcg(ideal_ranking, k=5):.3f}")  # = 1.0
```

## Как выбрать метрику

| Задача | Ключевая метрика | Когда использовать |
|---|---|---|
| Регрессия (нет выбросов) | MSE, R² | Нормальные данные |
| Регрессия (есть выбросы) | MAE, MAPE | Финансы, временные ряды |
| Бинарная классификация (баланс) | Accuracy, AUC | Сбалансированные классы |
| Бинарная классификация (дисбаланс) | PR-AUC, F1, MCC | Fraud, болезни |
| Мультиклассовая | Weighted F1, Macro F1 | В зависимости от важности классов |
| Object Detection | mAP | COCO, Pascal VOC |
| Перевод | BLEU | MT benchmark |
| Суммаризация | ROUGE | Summarization |
| Ранжирование/Рекомендации | NDCG, MAP | Search, RecSys |

## Итог

1. **Loss = что оптимизируем**; Метрика = что измеряем; часто разные вещи
2. **MSE** — для регрессии без выбросов; **Huber** — с выбросами
3. **Cross-Entropy** — де-факто стандарт для классификации
4. **Focal Loss** — для сильного дисбаланса классов
5. **Accuracy** обманывает при несбалансированных классах → используйте F1, AUC
6. **ROC-AUC** — хорошая мера для бинарной классификации; **PR-AUC** честнее при дисбалансе
7. **mAP, BLEU, ROUGE, NDCG** — специализированные метрики для конкретных задач

## Литература

1. Goodfellow, I., Bengio, Y., Courville, A. (2016). *Deep Learning*. MIT Press. Chapter 6.

2. Lin, T.Y., et al. (2017). *Focal Loss for Dense Object Detection* (RetinaNet). ICCV 2017. https://arxiv.org/abs/1708.02002

3. Fawcett, T. (2006). *An Introduction to ROC Analysis*. Pattern Recognition Letters.

4. Davis, J., Goadrich, M. (2006). *The Relationship Between Precision-Recall and ROC Curves*. ICML 2006.

5. Papineni, K., et al. (2002). *BLEU: a Method for Automatic Evaluation of Machine Translation*. ACL 2002.

6. Lin, C.Y. (2004). *ROUGE: A Package for Automatic Evaluation of Summaries*. ACL Workshop.

7. Järvelin, K., Kekäläinen, J. (2002). *Cumulated Gain-Based Evaluation of IR Techniques*. ACM TOIS.

8. Chicco, D., Jurman, G. (2020). *The advantages of the Matthews correlation coefficient (MCC) over F1 score*. BMC Genomics.

9. Huber, P.J. (1964). *Robust Estimation of a Location Parameter*. The Annals of Mathematical Statistics.

10. Schroff, F., Kalenichenko, D., Philbin, J. (2015). *FaceNet: A Unified Embedding for Face Recognition and Clustering*. CVPR 2015.
