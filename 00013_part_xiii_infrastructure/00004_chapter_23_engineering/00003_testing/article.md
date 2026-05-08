# Тесты: unit, integration, e2e, property-based, fuzzing

«Код без тестов — устаревший код», — написал Майкл Фезерс. Тесты — это не только проверка правильности, это документация намерений, сеть безопасности при рефакторинге, и способ мышления о коде. Разные типы тестов решают разные задачи, и понимание их различий позволяет строить эффективную тестовую стратегию.

## Тестовая пирамида

**Test Pyramid** (тестовая пирамида) Майка Кона — концептуальная модель, описывающая оптимальное соотношение типов тестов:

```
         /───────────────\
        /   E2E Tests     \      Мало, медленные, хрупкие
       /─────────────────\
      / Integration Tests  \    Среднее количество
     /─────────────────────\
    /     Unit Tests         \   Много, быстрые, надёжные
   /─────────────────────────\
```

**Принцип:** Чем выше в пирамиде — тем меньше тестов, тем они медленнее и дороже в поддержке.

```
Уровень          Скорость    Стоимость написания    Стоимость поддержки
Unit tests       ~1ms        Низкая                 Низкая
Integration      ~100ms      Средняя                Средняя
E2E tests        ~5-30s      Высокая                Высокая (хрупкие!)
```

## Unit Tests: быстро, изолированно

**Unit tests** проверяют одну единицу поведения (функцию, метод, класс) в изоляции от зависимостей.

```python
# Что тестируют unit tests: бизнес-логику без зависимостей

from decimal import Decimal
from unittest.mock import Mock, patch
import pytest

class PricingService:
    def __init__(self, tax_rate_repo, promo_repo):
        self._tax_repo = tax_rate_repo
        self._promo_repo = promo_repo
    
    def calculate_total(
        self, 
        base_price: Decimal, 
        country: str,
        promo_code: str = None
    ) -> Decimal:
        tax_rate = self._tax_repo.get_rate(country)
        total = base_price * (1 + tax_rate)
        
        if promo_code:
            discount = self._promo_repo.get_discount(promo_code)
            total = total * (1 - discount)
        
        return total.quantize(Decimal("0.01"))

# Unit test: мокаем все зависимости
class TestPricingService:
    
    def setup_method(self):
        self.tax_repo = Mock()
        self.promo_repo = Mock()
        self.service = PricingService(self.tax_repo, self.promo_repo)
    
    def test_calculate_total_with_tax(self):
        # Arrange
        self.tax_repo.get_rate.return_value = Decimal("0.20")  # 20% VAT
        price = Decimal("100.00")
        
        # Act
        result = self.service.calculate_total(price, "DE")
        
        # Assert
        assert result == Decimal("120.00")
        self.tax_repo.get_rate.assert_called_once_with("DE")
    
    def test_calculate_total_with_promo(self):
        self.tax_repo.get_rate.return_value = Decimal("0.20")
        self.promo_repo.get_discount.return_value = Decimal("0.10")  # 10% off
        
        result = self.service.calculate_total(Decimal("100.00"), "DE", "SAVE10")
        
        # 100 * 1.20 * 0.90 = 108.00
        assert result == Decimal("108.00")
    
    def test_promo_repo_not_called_without_code(self):
        self.tax_repo.get_rate.return_value = Decimal("0.00")
        
        self.service.calculate_total(Decimal("100.00"), "US")
        
        self.promo_repo.get_discount.assert_not_called()
    
    def test_raises_when_country_not_found(self):
        self.tax_repo.get_rate.side_effect = KeyError("Country not found")
        
        with pytest.raises(KeyError, match="Country not found"):
            self.service.calculate_total(Decimal("100.00"), "XX")
```

**Ключевые принципы unit tests:**
- **Fast** — должны работать за миллисекунды
- **Isolated** — никакой реальной БД, HTTP, файловой системы
- **Repeatable** — одинаковый результат при каждом запуске
- **Self-validating** — pass или fail, никакой ручной интерпретации

## Mocks, Stubs и Fakes

```python
# Mock: объект с проверяемыми вызовами
mock_repo = Mock()
mock_repo.find_by_id(123)
mock_repo.find_by_id.assert_called_once_with(123)  # Проверяем вызов

# Stub: заменяет реализацию, возвращает предопределённые данные
stub_repo = Mock()
stub_repo.find_by_id.return_value = {"id": 123, "name": "Alice"}
# Нас не интересует что stub_repo был вызван — нам важны данные

# Fake: упрощённая, но рабочая реализация
class FakeOrderRepository:
    """Настоящая реализация, но в памяти — для тестов."""
    def __init__(self):
        self._storage = {}
    
    def save(self, order):
        self._storage[order.id] = order
    
    def find_by_id(self, order_id):
        return self._storage.get(order_id)
    
    def find_all(self):
        return list(self._storage.values())

# Fake лучше Mock когда логика взаимодействия сложная
# Mock лучше когда нужно проверить конкретные вызовы
```

## Integration Tests: реальные зависимости

**Integration tests** проверяют взаимодействие компонентов с реальными зависимостями (базой данных, Redis, внешними сервисами).

```python
# pytest + pytest-docker-compose для реальных зависимостей
# conftest.py

import pytest
import psycopg2
import time

@pytest.fixture(scope="session")
def postgres_connection():
    """Запускает PostgreSQL и возвращает соединение."""
    import subprocess
    
    # Запускаем контейнер (или используем уже запущенный в CI)
    subprocess.run(
        ["docker", "run", "-d", "--name", "test-postgres",
         "-e", "POSTGRES_PASSWORD=test",
         "-e", "POSTGRES_DB=testdb",
         "-p", "5433:5432",
         "postgres:16"],
        check=True
    )
    
    # Ждём готовности
    for _ in range(30):
        try:
            conn = psycopg2.connect(
                host="localhost", port=5433,
                database="testdb", user="postgres", password="test"
            )
            yield conn
            conn.close()
            subprocess.run(["docker", "rm", "-f", "test-postgres"])
            return
        except psycopg2.OperationalError:
            time.sleep(1)
    
    raise RuntimeError("PostgreSQL не запустился")

@pytest.fixture
def db_with_schema(postgres_connection):
    """Создаёт схему и откатывает после теста."""
    cursor = postgres_connection.cursor()
    
    # Создаём таблицы
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id UUID PRIMARY KEY,
            customer_id UUID NOT NULL,
            total DECIMAL(10,2) NOT NULL,
            status VARCHAR(50) NOT NULL
        )
    """)
    postgres_connection.commit()
    
    yield postgres_connection
    
    # Откатываем после теста (не удаляем данные между тестами)
    cursor.execute("TRUNCATE orders CASCADE")
    postgres_connection.commit()

# Integration test
class TestOrderRepository:
    def test_save_and_find(self, db_with_schema):
        from uuid import uuid4
        from decimal import Decimal
        
        repo = PostgresOrderRepository(db_with_schema)
        
        order = Order(
            id=uuid4(),
            customer_id=uuid4(),
            total=Decimal("99.99"),
            status="pending"
        )
        
        # Сохраняем в реальной БД
        repo.save(order)
        
        # Читаем из реальной БД
        found = repo.find_by_id(order.id)
        
        assert found is not None
        assert found.total == Decimal("99.99")
        assert found.status == "pending"
    
    def test_find_returns_none_for_unknown_id(self, db_with_schema):
        from uuid import uuid4
        repo = PostgresOrderRepository(db_with_schema)
        
        result = repo.find_by_id(uuid4())
        
        assert result is None
```

### Docker Compose для Integration Tests

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: testdb
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d testdb"]
      interval: 5s
      timeout: 5s
      retries: 10
  
  redis:
    image: redis:7
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
  
  elasticsearch:
    image: elasticsearch:8.10.0
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
    ports:
      - "9201:9200"
```

```bash
# Запуск integration tests
docker-compose -f docker-compose.test.yml up -d --wait
pytest tests/integration/ -v
docker-compose -f docker-compose.test.yml down
```

## E2E Tests: от пользователя до базы данных

**End-to-End (E2E) tests** тестируют полный пользовательский сценарий через реальный UI или API.

### Playwright (E2E для web)

```python
# pip install playwright pytest-playwright
# playwright install chromium

import pytest
from playwright.sync_api import Page, expect

@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()

class TestCheckoutFlow:
    def test_user_can_place_order(self, page: Page):
        # Шаг 1: Открываем каталог
        page.goto("https://staging.myapp.com/products")
        
        # Шаг 2: Добавляем товар в корзину
        page.click('[data-testid="product-123-add-to-cart"]')
        
        # Проверяем обновление счётчика корзины
        expect(page.locator('[data-testid="cart-count"]')).to_have_text("1")
        
        # Шаг 3: Переходим к checkout
        page.click('[data-testid="checkout-btn"]')
        
        # Шаг 4: Заполняем форму
        page.fill('[name="email"]', "test@example.com")
        page.fill('[name="card-number"]', "4242424242424242")
        page.fill('[name="expiry"]', "12/25")
        page.fill('[name="cvv"]', "123")
        
        # Шаг 5: Подтверждаем заказ
        page.click('[data-testid="place-order-btn"]')
        
        # Шаг 6: Проверяем успешное оформление
        expect(page.locator('[data-testid="order-confirmation"]')).to_be_visible()
        expect(page.locator('[data-testid="order-id"]')).to_contain_text("ORD-")
    
    def test_checkout_shows_error_for_invalid_card(self, page: Page):
        page.goto("https://staging.myapp.com/checkout")
        page.fill('[name="card-number"]', "1111111111111111")
        page.click('[data-testid="place-order-btn"]')
        
        expect(page.locator('[data-testid="error-message"]')).to_contain_text(
            "Invalid card number"
        )
```

**Проблемы E2E тестов:**
- **Хрупкость** — зависят от UI, который часто меняется
- **Медленность** — каждый тест занимает секунды или десятки секунд
- **Сложность отладки** — трудно найти причину падения
- **Flakiness** — нестабильные из-за timing issues

## Property-Based Testing: генерация тестов из инвариантов

**Property-based testing** вместо написания конкретных примеров описывает **свойства** (инварианты), которые должны выполняться для всех возможных входных данных. Фреймворк генерирует сотни тестовых случаев автоматически.

### Hypothesis (Python)

```python
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Пример 1: сортировка
from typing import List

def my_sort(lst: List[int]) -> List[int]:
    return sorted(lst)

@given(st.lists(st.integers()))
def test_sort_properties(lst):
    result = my_sort(lst)
    
    # Свойство 1: Результат той же длины
    assert len(result) == len(lst)
    
    # Свойство 2: Результат содержит те же элементы
    assert sorted(result) == sorted(lst)  # эквивалентно: Counter(result) == Counter(lst)
    
    # Свойство 3: Результат отсортирован
    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1]

# Пример 2: парсинг JSON (round-trip)
import json

@given(st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children)
))
def test_json_roundtrip(value):
    """JSON сериализация/десериализация должна быть идемпотентной."""
    serialized = json.dumps(value)
    deserialized = json.loads(serialized)
    assert deserialized == value

# Пример 3: математические свойства
from decimal import Decimal

@given(
    st.decimals(min_value=Decimal("0"), max_value=Decimal("10000"), places=2),
    st.decimals(min_value=Decimal("0"), max_value=Decimal("1"), places=2)
)
def test_discount_properties(price, discount_rate):
    assume(price > 0)  # Исключаем нулевые цены
    
    discounted = price * (1 - discount_rate)
    
    # Скидка не может увеличить цену
    assert discounted <= price
    
    # Скидка не может сделать цену отрицательной
    assert discounted >= 0
    
    # 0% скидка = без изменений
    assert price * (1 - Decimal("0")) == price

# Пример 4: нахождение граничных случаев
@given(st.integers(min_value=1, max_value=100))
@settings(max_examples=500)  # Запустить 500 примеров
def test_pagination_invariants(page_size):
    total_items = 100
    
    pages = get_pages(total_items, page_size)
    
    # Все элементы должны быть показаны ровно один раз
    all_items = [item for page in pages for item in page]
    assert len(all_items) == total_items
    assert set(all_items) == set(range(total_items))

# Hypothesis автоматически находит минимальный failing case:
# Если функция падает на [1, 2, 3], Hypothesis найдёт что падает на [1, 2]
# и даже [1] — это называется "shrinking"
```

### QuickCheck (Haskell, оригинал)

```haskell
-- property-based testing в Haskell (оригинал QuickCheck)
import Test.QuickCheck

prop_reverseLength :: [Int] -> Bool
prop_reverseLength xs = length (reverse xs) == length xs

prop_reverseReverse :: [Int] -> Bool
prop_reverseReverse xs = reverse (reverse xs) == xs

main :: IO ()
main = do
  quickCheck prop_reverseLength
  quickCheck prop_reverseReverse
-- QuickCheck сгенерирует 100 случайных списков и проверит оба свойства
```

### PropEr (Erlang/Elixir)

```elixir
# PropEr/ExCheck в Elixir
use ExUnitProperties

property "list reversing is its own inverse" do
  check all list <- list_of(integer()) do
    assert Enum.reverse(Enum.reverse(list)) == list
  end
end
```

## Fuzzing: случайные входные данные для поиска crashes

**Fuzzing** — автоматизированное тестирование путём подачи случайных/полуслучайных входных данных. Цель: найти crashes, зависания, memory corruption, security vulnerabilities.

### Go Fuzzing (встроенный в Go 1.18+)

```go
// parsing_test.go
package parser

import (
    "testing"
    "unicode/utf8"
)

// Обычный unit test для ориентиров
func TestParseCommand(t *testing.T) {
    tests := []struct {
        input string
        want  Command
    }{
        {"GET /api/users", Command{Method: "GET", Path: "/api/users"}},
        {"POST /api/users", Command{Method: "POST", Path: "/api/users"}},
    }
    
    for _, tc := range tests {
        got, err := ParseCommand(tc.input)
        if err != nil {
            t.Errorf("ParseCommand(%q) error: %v", tc.input, err)
        }
        if got != tc.want {
            t.Errorf("ParseCommand(%q) = %v, want %v", tc.input, got, tc.want)
        }
    }
}

// Fuzz test: ищем panics и crashes
func FuzzParseCommand(f *testing.F) {
    // Seed corpus: начальные примеры
    f.Add("GET /api/users")
    f.Add("POST /api/users")
    f.Add("")
    f.Add("INVALID")
    f.Add("GET")
    
    f.Fuzz(func(t *testing.T, input string) {
        // Проверяем что ParseCommand не паникует на любом input
        cmd, err := ParseCommand(input)
        
        // Если нет ошибки, результат должен быть валидным
        if err == nil {
            // Инварианты: метод не должен быть пустым
            if cmd.Method == "" {
                t.Errorf("ParseCommand(%q) returned empty method without error", input)
            }
            // Путь должен начинаться с /
            if len(cmd.Path) > 0 && cmd.Path[0] != '/' {
                t.Errorf("ParseCommand(%q) path doesn't start with /: %q", input, cmd.Path)
            }
        }
        
        // Дополнительно: проверяем что входные данные — валидный UTF-8
        // (не наше, но полезно проверить)
        _ = utf8.ValidString(input)
    })
}
```

```bash
# Запуск fuzzing (будет продолжаться пока не найдёт баг или не остановить)
go test -fuzz=FuzzParseCommand -fuzztime=60s

# Если найден баг — создаётся файл в testdata/fuzz/FuzzParseCommand/
# corpus/, который воспроизводит его

# Запуск только seed corpus (для CI)
go test -run=FuzzParseCommand ./...
```

### libFuzzer (C/C++)

```c
// parser_fuzzer.c
#include <stdint.h>
#include <stddef.h>
#include "my_parser.h"

// Точка входа для libFuzzer
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // libFuzzer вызывает эту функцию с разными data
    
    // Создаём null-terminated строку
    char *input = malloc(size + 1);
    if (!input) return 0;
    memcpy(input, data, size);
    input[size] = '\0';
    
    // Тестируем парсер
    ParsedCommand *cmd = parse_command(input);
    if (cmd) {
        free_command(cmd);
    }
    
    free(input);
    return 0;
}
```

```bash
# Компиляция с ASan + libFuzzer
clang -fsanitize=address,fuzzer -g parser.c parser_fuzzer.c -o fuzzer

# Запуск
./fuzzer -max_total_time=60  # 60 секунд

# При нахождении бага: crash-xxxx файл с минимальным воспроизведением
./fuzzer crash-1234567890abcdef
```

### AFL++ (American Fuzzy Lop)

```bash
# AFL: coverage-guided fuzzing
# Компиляция с AFL инструментацией
AFL_HARDEN=1 afl-clang-fast -o parser_afl parser.c

# Запуск фаззинга
mkdir input_corpus output
echo "GET /api" > input_corpus/seed1
afl-fuzz -i input_corpus -o output -- ./parser_afl @@
# @@ = путь к входному файлу (AFL будет мутировать его)
```

## Mutation Testing: проверка качества тестов

**Mutation testing** — метод оценки качества тестов. Инструмент вносит небольшие изменения (мутации) в код и проверяет, падают ли тесты.

```python
# Оригинальный код:
def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True

# Мутации которые создаёт инструмент:
# Мутация 1: < заменяется на <=
if n <= 2:  # УБИТО тестом test_2_is_prime? Если нет — плохой тест
    return False

# Мутация 2: return False заменяется на return True
    return True  # Должен упасть тест

# Мутация 3: n ** 0.5 заменяется на n ** 0
for i in range(2, int(n ** 0) + 1):  # Должен упасть
```

```bash
# Python: mutmut
pip install mutmut

mutmut run --paths-to-mutate=src/ --runner="python -m pytest tests/unit/"

# Результат:
# Killed mutants: 45/50 (90%)  ← хорошо
# Surviving mutants: 5/50 (10%) ← эти мутации не были поймал тестами

mutmut show 23  # Посмотреть выжившую мутацию #23
mutmut apply 23  # Применить мутацию для изучения
```

## Snapshot Testing

```python
# Snapshot testing: сохраняем ожидаемый вывод в файл
# Полезно для UI компонентов, JSON ответов API

import json
import pytest

class TestAPIResponses:
    def test_product_response(self, client, snapshot):
        response = client.get("/api/products/123")
        
        # При первом запуске: создаёт snapshot файл
        # При последующих: сравнивает с сохранённым
        snapshot.assert_match(
            json.dumps(response.json(), indent=2, sort_keys=True),
            "product_123_response.json"
        )

# Снапшот файл (хранится в git):
# tests/snapshots/product_123_response.json
# {
#   "id": 123,
#   "name": "Widget",
#   "price": "9.99"
# }

# При изменении API ответа: обновляем снапшот
# pytest --snapshot-update
```

## Contract Testing: Pact для микросервисов

**Contract tests** проверяют совместимость интерфейсов между сервисами без запуска обоих одновременно.

```python
# Consumer side (OrderService потребляет InventoryService API)
import pytest
from pact import Consumer, Provider

@pytest.fixture
def pact():
    return Consumer('OrderService').has_pact_with(
        Provider('InventoryService'),
        host_name='localhost',
        port=1234,
        pact_dir='./pacts'
    )

def test_get_stock_level(pact):
    expected_stock = {'productId': '123', 'quantity': 50}
    
    (pact
     .given("Product 123 has 50 units in stock")
     .upon_receiving("a request for product 123 stock")
     .with_request('GET', '/api/inventory/123')
     .will_respond_with(200, body=expected_stock))
    
    with pact:
        # Вызываем наш код, который обращается к mock provider
        from order_service import check_availability
        result = check_availability('123')
        
        assert result == 50

# Provider side (InventoryService проверяет что выполняет контракт)
# pytest --pact-verify --pact-provider-states-setup=http://localhost:5000
```

## TDD и BDD

```python
# TDD (Test-Driven Development): тест → красный → зелёный → рефакторинг
# Red → Green → Refactor

# Шаг 1: Пишем тест (Red)
def test_shopping_cart_total():
    cart = ShoppingCart()
    cart.add_item(Product("Widget", Decimal("9.99")), quantity=2)
    
    assert cart.total() == Decimal("19.98")  # Тест падает: ShoppingCart не существует

# Шаг 2: Минимальная реализация (Green)
class ShoppingCart:
    def __init__(self):
        self._items = []
    
    def add_item(self, product, quantity=1):
        self._items.append((product, quantity))
    
    def total(self):
        return sum(p.price * q for p, q in self._items)

# Шаг 3: Рефакторинг (без изменения поведения)

# BDD (Behavior-Driven Development): тесты на языке бизнеса
# pip install pytest-bdd

# features/checkout.feature (Gherkin)
'''
Feature: Shopping cart checkout
  
  Scenario: Calculate total with single item
    Given I have an empty shopping cart
    When I add 2 "Widget" items at 9.99 each
    Then the cart total should be 19.98
  
  Scenario: Apply coupon discount
    Given I have a cart with "Widget" item at 9.99
    When I apply coupon "SAVE10" for 10% off
    Then the cart total should be 8.99
'''

# tests/test_checkout.py
from pytest_bdd import given, when, then, parsers, scenarios

scenarios('features/checkout.feature')

@given("I have an empty shopping cart")
def empty_cart():
    return ShoppingCart()

@when(parsers.parse('I add {quantity:d} "{name}" items at {price:f} each'))
def add_items(empty_cart, quantity, name, price):
    product = Product(name, Decimal(str(price)))
    empty_cart.add_item(product, quantity)

@then(parsers.parse('the cart total should be {expected:f}'))
def check_total(empty_cart, expected):
    assert empty_cart.total() == Decimal(str(expected))
```

## Заключение

Разные типы тестов дополняют друг друга:

- **Unit tests** — быстрые, проверяют бизнес-логику в изоляции. Должно быть много.
- **Integration tests** — проверяют что компоненты работают вместе. Умеренное количество.
- **E2E tests** — проверяют полные пользовательские сценарии. Мало и только для критичных путей.
- **Property-based** — автоматически находят граничные случаи из инвариантов.
- **Fuzzing** — находит crashes и security issues в парсерах и сложной логике.
- **Mutation testing** — проверяет качество самих тестов.

**Ключевые принципы:**
1. Следуй тестовой пирамиде — больше unit, меньше E2E
2. Тест должен быть читаем как документация намерений
3. Быстрые тесты запускаются чаще → находят проблемы раньше
4. Property-based тесты заменяют многие ручные примеры
5. Fuzzing обязателен для всего что парсит внешние данные

## Литература

1. **Feathers, Michael C.** — «Working Effectively with Legacy Code». Prentice Hall, 2004. ISBN: 978-0131177055
2. **Beck, Kent** — «Test-Driven Development: By Example». Addison-Wesley, 2003. ISBN: 978-0321146533
3. **Khorikov, Vladimir** — «Unit Testing: Principles, Practices, and Patterns». Manning, 2020. ISBN: 978-1617296277
4. **Hypothesis Documentation** — https://hypothesis.readthedocs.io/
5. **Go Fuzzing Documentation** — https://go.dev/doc/security/fuzz
6. **AFL++ Documentation** — https://aflplus.plus/
7. **Claessen, Koen; Hughes, John** — «QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs». ICFP 2000
8. **Playwright Documentation** — https://playwright.dev/python/
9. **Pact Documentation** — «Contract Testing»: https://docs.pact.io/
10. **Cohn, Mike** — «Succeeding with Agile». Addison-Wesley, 2009. ISBN: 978-0321579362
