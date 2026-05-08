# SQL: SELECT, JOIN, GROUP BY, оконные функции

## Введение

SQL (Structured Query Language) — один из самых долгоживущих языков программирования. Разработанный в IBM в начале 1970-х годов Дональдом Чемберлином и Реймондом Бойсом как реализация идей Кодда, он стал стандартом для работы с реляционными базами данных. Несмотря на появление NoSQL, NewSQL и множества специализированных систем, SQL остаётся незаменимым инструментом для любого разработчика.

SQL разделяется на:
- **DDL** (Data Definition Language): CREATE, ALTER, DROP — структура
- **DML** (Data Manipulation Language): SELECT, INSERT, UPDATE, DELETE — данные
- **DCL** (Data Control Language): GRANT, REVOKE — права
- **TCL** (Transaction Control Language): BEGIN, COMMIT, ROLLBACK — транзакции

В этой главе мы сосредоточимся на DML с акцентом на сложные запросы: JOIN-ы всех типов, агрегации, CTE и мощные оконные функции.

---

## 1. Настройка учебной базы данных

```sql
-- Создаём учебную схему
CREATE TABLE departments (
    id   INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    budget DECIMAL(12,2)
);

CREATE TABLE employees (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    manager_id    INTEGER REFERENCES employees(id),
    salary        DECIMAL(10,2) NOT NULL,
    hire_date     DATE NOT NULL,
    title         VARCHAR(50)
);

CREATE TABLE projects (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    start_date  DATE,
    end_date    DATE,
    budget      DECIMAL(12,2)
);

CREATE TABLE employee_projects (
    employee_id INTEGER REFERENCES employees(id),
    project_id  INTEGER REFERENCES projects(id),
    hours       INTEGER NOT NULL,
    PRIMARY KEY (employee_id, project_id)
);

-- Тестовые данные
INSERT INTO departments VALUES (1, 'Engineering', 1000000), (2, 'Marketing', 500000), (3, 'HR', 200000);
INSERT INTO employees (name, department_id, salary, hire_date, title) VALUES
    ('Alice', 1, 120000, '2020-01-15', 'Senior Engineer'),
    ('Bob', 1, 95000, '2021-03-01', 'Engineer'),
    ('Carol', 2, 80000, '2019-06-15', 'Marketing Lead'),
    ('Dave', 2, 70000, '2022-01-01', 'Marketing Analyst'),
    ('Eve', 1, 150000, '2018-05-10', 'Principal Engineer'),
    ('Frank', 3, 65000, '2023-02-01', 'HR Specialist'),
    ('Grace', 1, 110000, '2021-11-15', 'Engineer'),
    ('Henry', NULL, 200000, '2017-01-01', 'CEO');  -- NULL department!
```

---

## 2. SELECT: базовые конструкции

### 2.1 Основной синтаксис

```sql
SELECT 
    [DISTINCT]
    column1, column2, expression AS alias,
    ...
FROM table
[WHERE condition]
[GROUP BY columns]
[HAVING group_condition]
[ORDER BY columns [ASC|DESC]]
[LIMIT n OFFSET m];
```

### 2.2 WHERE — фильтрация

```sql
-- Операторы сравнения
SELECT * FROM employees WHERE salary > 100000;
SELECT * FROM employees WHERE hire_date BETWEEN '2021-01-01' AND '2022-12-31';
SELECT * FROM employees WHERE department_id IN (1, 2);
SELECT * FROM employees WHERE department_id NOT IN (3);
SELECT * FROM employees WHERE department_id IS NULL;
SELECT * FROM employees WHERE name LIKE 'A%';    -- Начинается с A
SELECT * FROM employees WHERE name ILIKE '%alice%';  -- Case-insensitive (PostgreSQL)

-- Составные условия
SELECT * FROM employees 
WHERE salary > 100000 
  AND department_id = 1 
  AND hire_date > '2020-01-01';

-- CASE выражение
SELECT name, salary,
    CASE 
        WHEN salary >= 150000 THEN 'Executive'
        WHEN salary >= 100000 THEN 'Senior'
        WHEN salary >= 70000  THEN 'Mid-level'
        ELSE 'Junior'
    END AS level
FROM employees;
```

### 2.3 GROUP BY и HAVING

```sql
-- Агрегатные функции: COUNT, SUM, AVG, MIN, MAX
SELECT 
    department_id,
    COUNT(*) AS headcount,
    AVG(salary) AS avg_salary,
    MIN(salary) AS min_salary,
    MAX(salary) AS max_salary,
    SUM(salary) AS payroll
FROM employees
WHERE department_id IS NOT NULL
GROUP BY department_id;

-- HAVING — фильтр ПОСЛЕ агрегации (WHERE — до)
SELECT 
    department_id,
    COUNT(*) AS headcount,
    AVG(salary) AS avg_salary
FROM employees
GROUP BY department_id
HAVING COUNT(*) >= 2          -- Только отделы с >=2 сотрудниками
   AND AVG(salary) > 80000;   -- И средней зарплатой >80K

-- Группировка с выражением
SELECT 
    EXTRACT(YEAR FROM hire_date) AS hire_year,
    COUNT(*) AS hires
FROM employees
GROUP BY EXTRACT(YEAR FROM hire_date)
ORDER BY hire_year;
```

---

## 3. JOIN — соединение таблиц

### 3.1 INNER JOIN

Возвращает только строки с совпадением в обеих таблицах:

```sql
SELECT e.name, d.name AS department
FROM employees e
INNER JOIN departments d ON e.department_id = d.id;
-- Henry (CEO с NULL department) и отдел HR без сотрудников НЕ включаются
```

### 3.2 LEFT JOIN (LEFT OUTER JOIN)

Все строки из левой таблицы, NULL для несовпавших из правой:

```sql
SELECT e.name, d.name AS department
FROM employees e
LEFT JOIN departments d ON e.department_id = d.id;
-- Henry (CEO) включён с department = NULL
-- HR department всё ещё не включён (он в правой таблице)
```

### 3.3 RIGHT JOIN

Все строки из правой таблицы, NULL для несовпавших из левой:

```sql
SELECT e.name, d.name AS department
FROM employees e
RIGHT JOIN departments d ON e.department_id = d.id;
-- HR department включён с name = NULL (нет сотрудников)
-- Henry не включён (нет department)
```

### 3.4 FULL OUTER JOIN

Все строки из обеих таблиц:

```sql
SELECT e.name, d.name AS department
FROM employees e
FULL OUTER JOIN departments d ON e.department_id = d.id;
-- Включает: Henry (NULL dept), HR dept (NULL employee)
```

### 3.5 CROSS JOIN

Декартово произведение (все возможные пары):

```sql
-- Все возможные назначения сотрудник-проект
SELECT e.name, p.name AS project
FROM employees e
CROSS JOIN projects p;
-- n_employees × n_projects строк!
```

### 3.6 SELF JOIN

Соединение таблицы с самой собой (для иерархий):

```sql
-- Найти сотрудников и их менеджеров
SELECT 
    e.name AS employee,
    m.name AS manager
FROM employees e
LEFT JOIN employees m ON e.manager_id = m.id;
```

### 3.7 Несколько JOIN-ов

```sql
-- Сотрудники, их отделы и проекты
SELECT 
    e.name AS employee,
    d.name AS department,
    p.name AS project,
    ep.hours
FROM employees e
JOIN departments d ON e.department_id = d.id
JOIN employee_projects ep ON ep.employee_id = e.id
JOIN projects p ON p.id = ep.project_id
WHERE e.department_id = 1
ORDER BY e.name, p.name;
```

### 3.8 Визуализация JOIN-ов

```
A = {1, 2, 3, 4}    B = {3, 4, 5, 6}

INNER: A ∩ B = {3, 4}
LEFT:  A ∪ (A ∩ B) = {1, 2, 3, 4}  (нули для элементов A без пары в B)
RIGHT: (A ∩ B) ∪ B = {3, 4, 5, 6}
FULL:  A ∪ B = {1, 2, 3, 4, 5, 6}
```

---

## 4. Подзапросы

### 4.1 Скалярный подзапрос

```sql
-- Сотрудники, зарабатывающие выше средней зарплаты по компании
SELECT name, salary
FROM employees
WHERE salary > (SELECT AVG(salary) FROM employees);

-- В SELECT
SELECT 
    name,
    salary,
    salary - (SELECT AVG(salary) FROM employees) AS diff_from_avg
FROM employees;
```

### 4.2 Коррелированный подзапрос

Выполняется для каждой строки внешнего запроса:

```sql
-- Сотрудники, зарабатывающие выше среднего по своему отделу
SELECT e1.name, e1.salary, e1.department_id
FROM employees e1
WHERE e1.salary > (
    SELECT AVG(e2.salary)
    FROM employees e2
    WHERE e2.department_id = e1.department_id  -- Корреляция!
);

-- EXISTS — проверка существования
SELECT d.name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.id
    AND e.salary > 100000
);
```

### 4.3 IN vs EXISTS vs JOIN

```sql
-- Три эквивалентных запроса:

-- IN (работает плохо при большом наборе)
SELECT * FROM employees
WHERE department_id IN (SELECT id FROM departments WHERE name = 'Engineering');

-- EXISTS (обычно быстрее чем IN с подзапросом)
SELECT * FROM employees e
WHERE EXISTS (
    SELECT 1 FROM departments d 
    WHERE d.id = e.department_id AND d.name = 'Engineering'
);

-- JOIN (часто самый быстрый, можно использовать индексы)
SELECT e.* FROM employees e
JOIN departments d ON e.department_id = d.id AND d.name = 'Engineering';
```

---

## 5. CTE (Common Table Expressions)

CTE (WITH clause) — именованные временные результирующие наборы. Улучшают читаемость и позволяют рекурсию:

```sql
-- Базовый CTE
WITH dept_stats AS (
    SELECT 
        department_id,
        COUNT(*) AS headcount,
        AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
)
SELECT 
    d.name,
    ds.headcount,
    ROUND(ds.avg_salary, 2) AS avg_salary
FROM departments d
JOIN dept_stats ds ON d.id = ds.department_id;

-- Несколько CTE
WITH 
senior_employees AS (
    SELECT * FROM employees WHERE hire_date < '2021-01-01'
),
dept_averages AS (
    SELECT department_id, AVG(salary) AS avg_sal FROM employees GROUP BY 1
)
SELECT se.name, se.salary, da.avg_sal
FROM senior_employees se
JOIN dept_averages da ON se.department_id = da.department_id
WHERE se.salary > da.avg_sal;
```

### 5.1 Рекурсивный CTE (иерархии)

```sql
-- Организационная иерархия (сотрудник → менеджер → ... → CEO)
WITH RECURSIVE org_chart AS (
    -- Базовый случай: CEO (нет менеджера)
    SELECT 
        id, name, manager_id,
        0 AS level,
        ARRAY[name] AS path
    FROM employees
    WHERE manager_id IS NULL
    
    UNION ALL
    
    -- Рекурсивный случай
    SELECT 
        e.id, e.name, e.manager_id,
        oc.level + 1,
        oc.path || e.name
    FROM employees e
    JOIN org_chart oc ON e.manager_id = oc.id
)
SELECT 
    REPEAT('  ', level) || name AS org_tree,
    level,
    path
FROM org_chart
ORDER BY path;

-- Поиск всех подчинённых менеджера
WITH RECURSIVE subordinates AS (
    SELECT id, name FROM employees WHERE id = 1  -- Начальный менеджер
    
    UNION ALL
    
    SELECT e.id, e.name
    FROM employees e
    JOIN subordinates s ON e.manager_id = s.id
)
SELECT * FROM subordinates;
```

---

## 6. Оконные функции (Window Functions)

Оконные функции — самая мощная особенность современного SQL. Вычисляют значение для каждой строки относительно «окна» (набора строк), не схлопывая результат как GROUP BY.

### 6.1 Синтаксис

```sql
function_name() OVER (
    [PARTITION BY column1, column2]  -- Разделить на группы
    [ORDER BY column3 DESC]          -- Порядок внутри окна
    [ROWS BETWEEN ... AND ...]       -- Размер окна (frame)
)
```

### 6.2 Ранжирующие функции

```sql
SELECT 
    name,
    department_id,
    salary,
    
    -- ROW_NUMBER: уникальный порядковый номер (1, 2, 3, ...)
    ROW_NUMBER() OVER (PARTITION BY department_id ORDER BY salary DESC) AS row_num,
    
    -- RANK: одинаковые значения — одинаковый ранг, пропуски в нумерации
    -- (1, 1, 3) — если двое с первым местом
    RANK() OVER (PARTITION BY department_id ORDER BY salary DESC) AS rank,
    
    -- DENSE_RANK: одинаковые значения — одинаковый ранг, БЕЗ пропусков
    -- (1, 1, 2) — если двое с первым местом
    DENSE_RANK() OVER (PARTITION BY department_id ORDER BY salary DESC) AS dense_rank,
    
    -- NTILE: делит на N групп (квартили, децили)
    NTILE(4) OVER (ORDER BY salary DESC) AS quartile,
    
    -- PERCENT_RANK: относительный ранг (0.0 - 1.0)
    ROUND(PERCENT_RANK() OVER (PARTITION BY department_id ORDER BY salary)::numeric, 3) AS pct_rank,
    
    -- CUME_DIST: кумулятивное распределение (доля строк с <= значением)
    ROUND(CUME_DIST() OVER (PARTITION BY department_id ORDER BY salary)::numeric, 3) AS cum_dist

FROM employees
WHERE department_id IS NOT NULL;
```

### 6.3 Навигационные функции

```sql
SELECT 
    name,
    hire_date,
    salary,
    
    -- LAG: значение предыдущей строки
    LAG(salary, 1, 0) OVER (PARTITION BY department_id ORDER BY hire_date) AS prev_salary,
    
    -- LEAD: значение следующей строки
    LEAD(salary, 1) OVER (PARTITION BY department_id ORDER BY hire_date) AS next_salary,
    
    -- FIRST_VALUE/LAST_VALUE: первое/последнее значение в окне
    FIRST_VALUE(name) OVER (PARTITION BY department_id ORDER BY salary DESC) AS highest_paid,
    LAST_VALUE(name) OVER (
        PARTITION BY department_id ORDER BY salary DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS lowest_paid,
    
    -- NTH_VALUE: N-ое значение в окне
    NTH_VALUE(salary, 2) OVER (
        PARTITION BY department_id ORDER BY salary DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS second_highest_salary

FROM employees
WHERE department_id IS NOT NULL;
```

### 6.4 Агрегатные функции как оконные

```sql
SELECT 
    name,
    department_id,
    salary,
    
    -- Нарастающий итог (running total)
    SUM(salary) OVER (PARTITION BY department_id ORDER BY hire_date) AS running_payroll,
    
    -- Скользящее среднее (3 последних по дате найма)
    AVG(salary) OVER (
        PARTITION BY department_id 
        ORDER BY hire_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3,
    
    -- Доля от суммы отдела
    ROUND(salary / SUM(salary) OVER (PARTITION BY department_id) * 100, 2) AS pct_of_dept,
    
    -- Разница с предыдущим наймом
    salary - LAG(salary) OVER (PARTITION BY department_id ORDER BY hire_date) AS salary_diff,
    
    -- Количество сотрудников в отделе (без GROUP BY!)
    COUNT(*) OVER (PARTITION BY department_id) AS dept_size

FROM employees
WHERE department_id IS NOT NULL
ORDER BY department_id, hire_date;
```

### 6.5 Практический пример: топ-N в каждой группе

```sql
-- Топ-2 самых высокооплачиваемых сотрудника в каждом отделе
WITH ranked AS (
    SELECT 
        name, department_id, salary,
        DENSE_RANK() OVER (PARTITION BY department_id ORDER BY salary DESC) AS dept_rank
    FROM employees
    WHERE department_id IS NOT NULL
)
SELECT name, department_id, salary, dept_rank
FROM ranked
WHERE dept_rank <= 2;
```

---

## 7. EXPLAIN: понимание планов запросов

```sql
-- Базовый план (без выполнения)
EXPLAIN SELECT * FROM employees WHERE department_id = 1;

-- С реальным выполнением
EXPLAIN ANALYZE SELECT * FROM employees WHERE department_id = 1;

-- Формат JSON для программной обработки
EXPLAIN (FORMAT JSON, ANALYZE) 
SELECT e.name, d.name 
FROM employees e JOIN departments d ON e.department_id = d.id;
```

Типичный вывод:
```
Seq Scan on employees  (cost=0.00..1.08 rows=8 width=548) (actual time=0.012..0.019 rows=8 loops=1)
  Filter: (department_id = 1)
  Rows Removed by Filter: 0
Planning Time: 0.123 ms
Execution Time: 0.038 ms
```

Что означает `cost=0.00..1.08`:
- `0.00` — стартовая стоимость (до первой строки)
- `1.08` — общая стоимость (в условных единицах)

Высокая стоимость → кандидат для оптимизации (добавить индекс, перестроить запрос).

---

## 8. DDL: CREATE, ALTER, DROP

```sql
-- Создание таблицы
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    sku         VARCHAR(50) UNIQUE NOT NULL,
    name        VARCHAR(200) NOT NULL,
    price       DECIMAL(10,2) CHECK (price >= 0),
    category_id INTEGER REFERENCES categories(id),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Изменение структуры
ALTER TABLE products ADD COLUMN description TEXT;
ALTER TABLE products ALTER COLUMN name SET NOT NULL;
ALTER TABLE products DROP COLUMN description;
ALTER TABLE products RENAME COLUMN sku TO product_code;

-- Индексы
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_price ON products(price DESC);
CREATE UNIQUE INDEX idx_products_sku ON products(sku);

-- Удаление
DROP TABLE IF EXISTS products CASCADE;  -- CASCADE удалит зависимые объекты
```

---

## 9. DML: INSERT, UPDATE, DELETE, UPSERT

```sql
-- INSERT
INSERT INTO employees (name, department_id, salary, hire_date)
VALUES ('New Employee', 1, 80000, CURRENT_DATE);

-- Multi-row insert
INSERT INTO employees (name, department_id, salary, hire_date)
VALUES 
    ('Alice', 1, 90000, '2024-01-15'),
    ('Bob', 2, 75000, '2024-01-20');

-- INSERT ... SELECT
INSERT INTO employees (name, department_id, salary, hire_date)
SELECT name || ' (copy)', department_id, salary * 0.9, CURRENT_DATE
FROM employees WHERE department_id = 1;

-- UPDATE
UPDATE employees SET salary = salary * 1.1
WHERE department_id = 1 AND hire_date < '2021-01-01';

-- UPDATE с JOIN (PostgreSQL синтаксис)
UPDATE employees e
SET salary = e.salary * 1.15
FROM departments d
WHERE e.department_id = d.id AND d.name = 'Engineering';

-- DELETE
DELETE FROM employees WHERE hire_date > '2023-12-31' AND salary < 70000;

-- UPSERT (INSERT ... ON CONFLICT)
INSERT INTO employees (id, name, salary, hire_date)
VALUES (1, 'Alice Updated', 100000, '2020-01-15')
ON CONFLICT (id) DO UPDATE 
SET name = EXCLUDED.name, salary = EXCLUDED.salary;

-- RETURNING — получить затронутые строки
UPDATE employees SET salary = salary * 1.1 
WHERE department_id = 1
RETURNING id, name, salary;
```

---

## Заключение

SQL — мощный декларативный язык. Вы описываете ЧТО хотите получить, а оптимизатор сам решает КАК это сделать.

**Ключевые выводы**:

1. **JOIN** — соединение по условию. INNER — только совпадения, LEFT — все из левой, FULL — все из обеих.

2. **GROUP BY + HAVING**: GROUP BY группирует, HAVING фильтрует группы (а WHERE — строки до группировки).

3. **CTE** (`WITH`) улучшают читаемость. Рекурсивные CTE — для иерархий и графов.

4. **Оконные функции** — вычисления относительно набора строк без схлопывания. PARTITION BY — группы, ORDER BY — порядок, ROWS/RANGE BETWEEN — размер окна.

5. **EXPLAIN ANALYZE** — всегда проверяйте планы медленных запросов.

---

## Литература и источники

1. PostgreSQL Documentation. SQL Commands. https://www.postgresql.org/docs/current/sql-commands.html
2. PostgreSQL Documentation. Window Functions. https://www.postgresql.org/docs/current/tutorial-window.html
3. Winand, M. (2012). *SQL Performance Explained*. Markus Winand. https://use-the-index-luke.com/
4. Molinaro, A. (2005). *SQL Cookbook*. O'Reilly Media.
5. Itzik Ben-Gan. (2015). *T-SQL Window Functions*. Microsoft Press.
6. Date, C. J. (2003). *An Introduction to Database Systems*, 8th Edition. Addison-Wesley.
7. Mode Analytics SQL Tutorial. https://mode.com/sql-tutorial/
8. SQLZoo. https://sqlzoo.net/
9. Wikipedia. SQL. https://en.wikipedia.org/wiki/SQL
10. Celko, J. (2010). *Joe Celko's SQL for Smarties*, 4th Edition. Morgan Kaufmann.
