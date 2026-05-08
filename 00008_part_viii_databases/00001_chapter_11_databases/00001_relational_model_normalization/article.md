# Реляционная модель и нормальные формы

## Введение

В 1970 году Эдгар Кодд (Edgar F. Codd), исследователь IBM, опубликовал статью «A Relational Model of Data for Large Shared Data Banks» — один из самых влиятельных документов в истории информатики. Кодд предложил математически строгую модель для организации данных, основанную на теории множеств и предикатной логике. Эта модель настолько хорошо отражала реальные потребности, что SQL — язык, построенный на её принципах — доминирует в базах данных уже более 50 лет.

Реляционная модель отвечает на фундаментальный вопрос: как организовать данные, чтобы их было легко хранить, модифицировать и запрашивать? Нормализация — процесс организации структуры таблиц для минимизации избыточности и предотвращения аномалий обновления. Понимание нормальных форм позволяет проектировать базы данных, которые легко поддерживать и которые дают правильные ответы.

---

## 1. Основные концепции реляционной модели

### 1.1 Отношение, кортеж, атрибут

**Отношение** (relation) — математически это подмножество декартова произведения доменов. На практике — это таблица.

**Кортеж** (tuple) — строка таблицы. В математическом смысле — упорядоченный набор значений.

**Атрибут** (attribute) — столбец таблицы с именем и доменом (типом данных).

**Домен** — множество допустимых значений атрибута.

```sql
-- Отношение "Employees" (реляция):
-- Атрибуты: id, name, department_id, salary
-- Кортеж: (1, 'Alice', 10, 90000.00)

CREATE TABLE employees (
    id          INTEGER      NOT NULL,
    name        VARCHAR(100) NOT NULL,
    department_id INTEGER    REFERENCES departments(id),
    salary      DECIMAL(10,2),
    hire_date   DATE         NOT NULL,
    PRIMARY KEY (id)         -- Первичный ключ
);
```

### 1.2 Ключи

**Суперключ** (superkey): набор атрибутов, уникально идентифицирующих кортеж.

**Потенциальный ключ** (candidate key): минимальный суперключ (нельзя убрать ни один атрибут без потери уникальности).

**Первичный ключ** (primary key): выбранный потенциальный ключ. NULL не допускается.

**Внешний ключ** (foreign key): атрибут(ы), ссылающиеся на первичный ключ другой таблицы.

```sql
-- Departments имеет первичный ключ id
-- Employees.department_id — внешний ключ → departments.id

CREATE TABLE departments (
    id   INTEGER     PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE employees (
    id            INTEGER     PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    department_id INTEGER     REFERENCES departments(id) ON DELETE SET NULL,
    manager_id    INTEGER     REFERENCES employees(id)  -- Самоссылка!
);
```

### 1.3 Целостность данных

**Целостность сущности**: первичный ключ не может содержать NULL.

**Ссылочная целостность**: значение внешнего ключа должно существовать в referenced таблице (или быть NULL).

**Домейнная целостность**: значения атрибута должны принадлежать домену.

---

## 2. Реляционная алгебра

Кодд определил набор операций над отношениями, составляющих реляционную алгебру. SQL — высокоуровневый язык, реализующий эти операции.

### 2.1 Основные операции

**Select (σ)** — фильтрация строк:
```sql
-- σ(salary > 50000)(employees)
SELECT * FROM employees WHERE salary > 50000;
```

**Project (π)** — выборка столбцов:
```sql
-- π(name, salary)(employees)
SELECT name, salary FROM employees;
```

**Union (∪)** — объединение двух отношений:
```sql
SELECT id, name FROM employees
UNION
SELECT id, name FROM contractors;
```

**Difference (−)** — разность:
```sql
-- Сотрудники, не являющиеся менеджерами
SELECT id FROM employees
EXCEPT
SELECT DISTINCT manager_id FROM employees WHERE manager_id IS NOT NULL;
```

**Intersection (∩)** — пересечение:
```sql
SELECT id FROM full_time_employees
INTERSECT
SELECT id FROM remote_employees;
```

**Cartesian Product (×)** — декартово произведение:
```sql
-- Все пары (сотрудник, отдел)
SELECT e.name, d.name FROM employees e CROSS JOIN departments d;
```

**Join (⋈)** — соединение с условием:
```sql
-- Natural Join (соединение по одинаковым именам атрибутов)
SELECT e.name, d.name 
FROM employees e 
JOIN departments d ON e.department_id = d.id;
```

---

## 3. Функциональные зависимости

**Функциональная зависимость** A → B: значение атрибута(ов) A однозначно определяет значение атрибута(ов) B.

```
employees: (id, name, department_id, salary)
id → name         (id однозначно определяет name)
id → department_id
id → salary
department_id → department_name  (если есть такой атрибут — денормализация!)
{first_name, last_name} → employee_id  (составной ключ)
```

**Тривиальная** FD: A → B, где B ⊆ A (y, x → x — тривиально).

**Транзитивная** FD: A → B и B → C → A → C (транзитивная).

---

## 4. Нормальные формы

Нормализация — процесс приведения схемы к нормальным формам. Каждая NF устраняет определённый класс аномалий.

### 4.1 Аномалии (зачем нормализация нужна)

Рассмотрим ненормализованную таблицу:

```
order_items (без нормализации):
order_id | customer_name | customer_email    | product_id | product_name | quantity | price
---------|---------------|-------------------|------------|--------------|----------|-------
1        | Alice         | alice@example.com | 101        | Widget       | 2        | 9.99
1        | Alice         | alice@example.com | 102        | Gadget       | 1        | 29.99
2        | Bob           | bob@example.com   | 101        | Widget       | 3        | 9.99
```

**Аномалия вставки**: нельзя добавить нового клиента без заказа.

**Аномалия обновления**: если email Алисы изменился — нужно обновить все её строки (а если забудем одну?).

**Аномалия удаления**: если удалим единственный заказ Боба — потеряем информацию о Бобе.

### 4.2 1NF (Первая нормальная форма)

**Требование**: все атрибуты атомарны (нет повторяющихся групп, нет массивов в ячейках).

**Нарушение 1NF**:
```sql
-- ПЛОХО: массив телефонов в одной ячейке
CREATE TABLE contacts (
    id    INTEGER PRIMARY KEY,
    name  VARCHAR(100),
    phones VARCHAR(500)  -- "555-1234, 555-5678" — нарушение!
);
```

**Решение**:
```sql
-- ХОРОШО: отдельная таблица для телефонов
CREATE TABLE contacts (
    id   INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE contact_phones (
    contact_id INTEGER REFERENCES contacts(id),
    phone_type VARCHAR(20),  -- 'mobile', 'home', 'work'
    phone      VARCHAR(20) NOT NULL,
    PRIMARY KEY (contact_id, phone_type)
);
```

### 4.3 2NF (Вторая нормальная форма)

**Требование**: 1NF + нет частичных зависимостей (каждый неключевой атрибут полностью зависит от всего первичного ключа, не от его части).

Актуально только при **составном** первичном ключе.

**Нарушение 2NF**:
```
order_items(order_id, product_id, quantity, product_name, product_price)
PK: (order_id, product_id)

Зависимости:
(order_id, product_id) → quantity    ✓ полная зависимость
product_id → product_name            ✗ частичная! product_name зависит только от части ключа
product_id → product_price           ✗ частичная!
```

**Решение** — выделить независимые данные:
```sql
-- Разделяем на две таблицы
CREATE TABLE products (
    id    INTEGER PRIMARY KEY,
    name  VARCHAR(100),
    price DECIMAL(10,2)
);

CREATE TABLE order_items (
    order_id   INTEGER,
    product_id INTEGER REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
```

### 4.4 3NF (Третья нормальная форма)

**Требование**: 2NF + нет транзитивных зависимостей (неключевой атрибут не зависит от другого неключевого атрибута).

**Нарушение 3NF**:
```
employees(id, name, department_id, department_name, department_location)
PK: id

id → department_id                    ✓
department_id → department_name       ✗ транзитивная! (через неключевой атрибут)
department_id → department_location   ✗ транзитивная!
```

**Решение**:
```sql
CREATE TABLE departments (
    id       INTEGER PRIMARY KEY,
    name     VARCHAR(50) NOT NULL,
    location VARCHAR(100)
);

CREATE TABLE employees (
    id            INTEGER PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    department_id INTEGER REFERENCES departments(id)
    -- Убрали department_name и department_location
);
```

### 4.5 BCNF (Нормальная форма Бойса-Кодда)

**Требование**: более строгая версия 3NF. Каждая нетривиальная FD X → Y: X должен быть суперключом.

BCNF важна при наличии нескольких потенциальных ключей, которые пересекаются:

```
Courses(student, subject, teacher)
teacher → subject  (каждый учитель преподаёт один предмет)
{student, subject} → teacher (студент на предмет имеет одного учителя)

PK: {student, subject}
Но: teacher → subject — зависимость от не-суперключа!

Нарушение BCNF!
```

**Решение**:
```sql
-- Разделяем
CREATE TABLE teacher_subjects (
    teacher INTEGER PRIMARY KEY,
    subject VARCHAR(50)
);

CREATE TABLE student_teachers (
    student INTEGER,
    teacher INTEGER REFERENCES teacher_subjects(teacher),
    PRIMARY KEY (student, teacher)
);
```

### 4.6 4NF и 5NF

**4NF**: нет многозначных зависимостей (A →→ B значит для каждого A есть независимое множество B-значений).

**5NF (Project-Join NF)**: нет join зависимостей (таблицу нельзя разложить на более мелкие без потери информации).

На практике достаточно BCNF для большинства систем.

---

## 5. Пример полного процесса нормализации

Начнём с ненормализованного CSV:

```
order_id | customer_name | email         | city  | items
---------|---------------|---------------|-------|------
1001     | Alice Smith   | a@b.com       | NYC   | Widget(2,$10), Gadget(1,$25)
1002     | Bob Jones     | bob@c.com     | LA    | Widget(1,$10)
1003     | Alice Smith   | a@b.com       | NYC   | Donut(5,$2)
```

**Шаг 1: 0NF → 1NF** (атомизируем items):

```sql
CREATE TABLE unnormalized_orders (
    order_id       INTEGER,
    customer_name  VARCHAR(100),
    email          VARCHAR(100),
    city           VARCHAR(50),
    product_name   VARCHAR(100),
    quantity       INTEGER,
    unit_price     DECIMAL(10,2)
);
-- PK: (order_id, product_name)
```

**Шаг 2: 1NF → 2NF** (устраняем частичные зависимости):

```sql
-- (order_id, product_name) → quantity  ✓
-- order_id → customer_name, email, city ✗ (зависит только от order_id, не от продукта)

CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_name VARCHAR(100),
    email         VARCHAR(100),
    city          VARCHAR(50)
);

CREATE TABLE order_items_2nf (
    order_id     INTEGER REFERENCES orders(order_id),
    product_name VARCHAR(100),
    quantity     INTEGER,
    unit_price   DECIMAL(10,2),
    PRIMARY KEY (order_id, product_name)
);
```

**Шаг 3: 2NF → 3NF** (устраняем транзитивные зависимости):

```sql
-- В orders: email → customer_name? Нет.
-- Но: customer_name + email → city? Нет (у разных Алис может быть разный город)
-- Скорее: customer_id → name, email, city (нужен customer_id как ключ)

CREATE TABLE customers (
    id    INTEGER PRIMARY KEY,
    name  VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    city  VARCHAR(50)
);

CREATE TABLE orders_3nf (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE products (
    id    INTEGER PRIMARY KEY,
    name  VARCHAR(100) NOT NULL,
    price DECIMAL(10,2)  -- базовая цена
);

CREATE TABLE order_items_3nf (
    order_id   INTEGER REFERENCES orders_3nf(id),
    product_id INTEGER REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,  -- цена на момент заказа (может меняться)
    PRIMARY KEY (order_id, product_id)
);
```

---

## 6. Денормализация и её цена

Нормализация — не всегда благо. В аналитических системах и при высоких нагрузках чтения денормализация ускоряет запросы:

```sql
-- Нормализовано: нужен JOIN для получения имени клиента
SELECT o.id, c.name, SUM(oi.quantity * oi.unit_price) as total
FROM orders o
JOIN customers c ON o.customer_id = c.id
JOIN order_items oi ON oi.order_id = o.id
GROUP BY o.id, c.name;

-- Денормализовано: имя клиента хранится в orders
-- + нет JOIN, - риск расхождения данных
SELECT id, customer_name, total_amount FROM orders;
```

**Когда денормализовывать**:
- OLAP/аналитические запросы (агрегация по миллионам строк)
- Read-heavy нагрузка
- Данные меняются редко
- Производительность критична

**Цена денормализации**:
- Избыточность данных
- Аномалии обновления вернутся
- Больше место
- Нужны триггеры или application logic для синхронизации

---

## 7. Реляционная алгебра в Python

```python
from typing import Set, Dict, List, Any

class Relation:
    """Простая реализация реляционной алгебры."""
    
    def __init__(self, attributes: List[str], tuples: List[tuple]):
        self.attributes = attributes
        self.tuples = set(tuples)
    
    def select(self, predicate) -> 'Relation':
        """σ(predicate)(self)"""
        return Relation(
            self.attributes,
            [t for t in self.tuples if predicate(dict(zip(self.attributes, t)))]
        )
    
    def project(self, attrs: List[str]) -> 'Relation':
        """π(attrs)(self)"""
        indices = [self.attributes.index(a) for a in attrs]
        return Relation(
            attrs,
            list(set(tuple(t[i] for i in indices) for t in self.tuples))
        )
    
    def join(self, other: 'Relation', condition) -> 'Relation':
        """⋈(condition)(self, other)"""
        combined_attrs = self.attributes + other.attributes
        result = []
        for t1 in self.tuples:
            for t2 in other.tuples:
                combined = t1 + t2
                row = dict(zip(combined_attrs, combined))
                if condition(row):
                    result.append(combined)
        return Relation(combined_attrs, result)
    
    def union(self, other: 'Relation') -> 'Relation':
        assert self.attributes == other.attributes
        return Relation(self.attributes, list(self.tuples | other.tuples))
    
    def __repr__(self):
        return f"Relation({self.attributes}, {len(self.tuples)} tuples)"

# Пример:
employees = Relation(
    ['id', 'name', 'dept_id'],
    [(1, 'Alice', 10), (2, 'Bob', 20), (3, 'Carol', 10)]
)

departments = Relation(
    ['id', 'name'],
    [(10, 'Engineering'), (20, 'Marketing')]
)

# Получить сотрудников Engineering
result = employees.join(
    departments,
    lambda r: r['dept_id'] == r['id'] and r['name'] == 'Engineering'
).project(['name', 'id'])  # Двусмысленность атрибута id - упрощение

print(result)
```

---

## Заключение

Реляционная модель Кодда — математически строгий фундамент для большинства современных баз данных. Нормализация — инструмент обеспечения целостности данных через устранение избыточности.

**Ключевые выводы**:

1. **Отношение** = таблица, **кортеж** = строка, **атрибут** = столбец с типом.

2. **Первичный ключ** — минимальный уникальный идентификатор. **Внешний ключ** — ссылка на PK другой таблицы.

3. **1NF**: атомарные атрибуты. **2NF**: нет частичных FD. **3NF**: нет транзитивных FD. **BCNF**: каждый детерминант — суперключ.

4. **Денормализация** — осознанный компромисс для производительности чтения. Применяется в OLAP, read-heavy системах.

5. **Аномалии** (вставки, обновления, удаления) — следствие плохого дизайна. Нормализация устраняет их.

---

## Литература и источники

1. Codd, E. F. (1970). A Relational Model of Data for Large Shared Data Banks. *Communications of the ACM*, 13(6), 377-387.
2. Date, C. J. (2003). *An Introduction to Database Systems*, 8th Edition. Addison-Wesley.
3. Ramakrishnan, R., & Gehrke, J. (2003). *Database Management Systems*, 3rd Edition. McGraw-Hill.
4. Kent, W. (1983). A Simple Guide to Five Normal Forms. *Communications of the ACM*, 26(2), 120-125.
5. Silberschatz, A., Korth, H., & Sudarshan, S. (2019). *Database System Concepts*, 7th Edition. McGraw-Hill.
6. Wikipedia. Database normalization. https://en.wikipedia.org/wiki/Database_normalization
7. Wikipedia. Relational model. https://en.wikipedia.org/wiki/Relational_model
8. PostgreSQL Documentation. https://www.postgresql.org/docs/current/
9. Codd, E. F. (1972). Further Normalization of the Data Base Relational Model. *Courant Computer Science Symposia Series 6*.
10. Armstrong, W. W. (1974). Dependency Structures of Data Base Relationships. *IFIP Congress 1974*.
