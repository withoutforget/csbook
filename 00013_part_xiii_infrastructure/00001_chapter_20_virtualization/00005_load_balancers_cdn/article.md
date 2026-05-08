# Load Balancers L4 vs L7, CDN, Anycast — как трафик распределяется по миру

Когда ваш сервис становится популярным, один сервер перестаёт справляться с нагрузкой. Но даже если бы он справлялся — что произойдёт при его отказе? Именно здесь вступают в игру балансировщики нагрузки, сети доставки контента и anycast-маршрутизация. Эти технологии обеспечивают масштабируемость, отказоустойчивость и глобальное присутствие крупнейших сервисов в интернете.

## Зачем нужна балансировка нагрузки

Представьте популярный интернет-магазин в период распродажи. Тысячи пользователей одновременно открывают страницы, добавляют товары в корзину, оформляют заказы. Один сервер физически не может обработать все эти запросы одновременно.

**Проблемы, которые решает балансировщик:**

1. **Масштабируемость** — распределение нагрузки между несколькими серверами
2. **Отказоустойчивость** — если один сервер падает, трафик автоматически перенаправляется на другие
3. **Техническое обслуживание** — можно обновлять серверы по одному без простоя сервиса
4. **Географическое распределение** — направление пользователя на ближайший сервер

```
       Пользователи
           │
    ┌──────▼──────┐
    │  Load       │
    │  Balancer   │
    └──┬────┬─────┘
       │    │    │
    ┌──▼─┐ ┌▼──┐ ┌▼──┐
    │App │ │App│ │App│
    │ 1  │ │ 2 │ │ 3 │
    └────┘ └───┘ └───┘
```

## L4 балансировка: транспортный уровень

L4 балансировщик работает на 4-м уровне модели OSI — транспортном. Он видит только IP-адреса, порты и протокол (TCP/UDP), но не содержимое запроса.

**Как работает L4 балансировка:**

Когда клиент устанавливает TCP-соединение, L4 балансировщик:
1. Получает SYN-пакет от клиента
2. Выбирает сервер по алгоритму балансировки
3. Прозрачно проксирует или перенаправляет соединение на выбранный backend

Существует два основных режима работы:
- **NAT (Network Address Translation)** — балансировщик изменяет destination IP в пакетах
- **DSR (Direct Server Return)** — ответные пакеты идут напрямую от сервера к клиенту, минуя балансировщик

```
# Пример: iptables для простейшего L4 балансировщика (DNAT)
# Перенаправляем входящие TCP соединения на порт 80 на два backend сервера

# Создаём ipset с backend серверами
ipset create backends hash:ip,port

# Добавляем backend серверы
ipset add backends 192.168.1.10,tcp:8080
ipset add backends 192.168.1.11,tcp:8080

# DNAT правило (упрощённо — в реальности нужна stateful логика)
iptables -t nat -A PREROUTING \
  -p tcp --dport 80 \
  -m statistic --mode random --probability 0.5 \
  -j DNAT --to-destination 192.168.1.10:8080

iptables -t nat -A PREROUTING \
  -p tcp --dport 80 \
  -j DNAT --to-destination 192.168.1.11:8080
```

**Когда использовать L4:**
- Очень высокая производительность (миллионы соединений)
- Не HTTP трафик: SMTP, FTP, базы данных, игровые серверы
- Когда содержимое запроса не нужно для маршрутизации
- AWS Network Load Balancer (NLB) — типичный пример L4

**Характеристики L4:**
- Минимальная задержка (нет необходимости читать тело запроса)
- Не может маршрутизировать на основе URL, заголовков, куков
- Не может выполнять SSL termination (без дополнительной конфигурации)
- Производительность: десятки миллионов пакетов в секунду

## L7 балансировка: прикладной уровень

L7 балансировщик понимает прикладной протокол — HTTP, HTTPS, gRPC. Он может принимать решения о маршрутизации на основе содержимого запроса.

**Возможности L7 балансировщика:**
- Маршрутизация по URL-пути (`/api/*` → один сервис, `/static/*` → другой)
- Маршрутизация по HTTP-заголовкам (например, `Host:` для virtual hosting)
- Cookie-based routing (sticky sessions)
- Canary deployments (10% трафика на новую версию)
- SSL/TLS termination
- WebSocket поддержка
- Сжатие, кеширование, модификация запросов/ответов
- Rate limiting, WAF (Web Application Firewall)

```nginx
# Nginx L7 балансировщик — пример конфигурации

upstream api_backend {
    # Алгоритм: least connections (меньше активных соединений = больше трафика)
    least_conn;
    
    server 192.168.1.10:8080 weight=3;  # Этот сервер получает больше трафика
    server 192.168.1.11:8080 weight=1;
    server 192.168.1.12:8080 backup;    # Backup: включается если остальные недоступны
    
    keepalive 32;  # Пул постоянных соединений к backend
}

upstream static_backend {
    server 192.168.1.20:8080;
    server 192.168.1.21:8080;
}

server {
    listen 443 ssl http2;
    server_name example.com;
    
    # TLS termination — расшифруем здесь, к backend идём по HTTP
    ssl_certificate /etc/ssl/certs/example.com.pem;
    ssl_certificate_key /etc/ssl/private/example.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    # Routing по URL path
    location /api/ {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }
    
    location /static/ {
        proxy_pass http://static_backend;
        proxy_cache_valid 200 1h;  # Кешируем ответы 1 час
    }
    
    # Canary: 10% трафика на новую версию
    location /checkout/ {
        # Используем $cookie для sticky sessions
        if ($cookie_beta_user = "1") {
            proxy_pass http://checkout_v2;
            break;
        }
        
        # Случайно 10% → новая версия
        set $upstream checkout_v1;
        if ($request_id ~* "^[0-9]") {
            set $upstream checkout_v2;
        }
        proxy_pass http://$upstream;
    }
}
```

**Примеры L7 балансировщиков:**
- **Nginx** — самый популярный, огромная экосистема
- **HAProxy** — высокопроизводительный, отлично для TCP и HTTP
- **AWS ALB (Application Load Balancer)** — managed L7 в AWS
- **Traefik** — динамическая конфигурация, нативная интеграция с Docker/Kubernetes
- **Envoy** — высокопроизводительный proxy, основа service mesh

## Алгоритмы балансировки

### Round Robin
Запросы распределяются по серверам по очереди: 1 → 2 → 3 → 1 → 2 → 3...

```python
class RoundRobinBalancer:
    def __init__(self, servers: list[str]):
        self.servers = servers
        self.current = 0
    
    def next_server(self) -> str:
        server = self.servers[self.current]
        self.current = (self.current + 1) % len(self.servers)
        return server

# Weighted Round Robin
class WeightedRoundRobin:
    def __init__(self, servers: list[tuple[str, int]]):
        # Расширяем список по весам
        self.servers = []
        for server, weight in servers:
            self.servers.extend([server] * weight)
        self.current = 0
    
    def next_server(self) -> str:
        server = self.servers[self.current]
        self.current = (self.current + 1) % len(self.servers)
        return server

# Пример:
balancer = WeightedRoundRobin([
    ("server1:8080", 3),  # Получит 3/5 запросов
    ("server2:8080", 2),  # Получит 2/5 запросов
])
```

**Проблема Round Robin:** не учитывает реальную нагрузку. Если один запрос занимает 1 мс, а другой — 10 секунд, один сервер может оказаться перегружен.

### Least Connections
Новый запрос отправляется на сервер с наименьшим количеством активных соединений.

```python
import threading
from dataclasses import dataclass, field

@dataclass
class Server:
    address: str
    active_connections: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def acquire(self):
        with self._lock:
            self.active_connections += 1
    
    def release(self):
        with self._lock:
            self.active_connections -= 1

class LeastConnectionsBalancer:
    def __init__(self, servers: list[str]):
        self.servers = [Server(addr) for addr in servers]
    
    def next_server(self) -> Server:
        return min(self.servers, key=lambda s: s.active_connections)
```

**Когда использовать:** запросы существенно различаются по времени обработки (например, видеотранскодирование).

### IP Hash
Сервер выбирается на основе хеша от IP-адреса клиента. Один клиент всегда попадает на один сервер.

```python
import hashlib

class IPHashBalancer:
    def __init__(self, servers: list[str]):
        self.servers = servers
    
    def next_server(self, client_ip: str) -> str:
        # Консистентный хеш: один IP всегда → один сервер
        hash_value = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        return self.servers[hash_value % len(self.servers)]
```

**Применение:** когда нужна сессионная привязка без куков (например, WebSocket).

**Проблема:** если добавить или удалить сервер — распределение полностью меняется. Для этого используют Consistent Hashing (описан в разделе о распределённых системах).

### Random / Power of Two Choices
Простой рандом работает удивительно хорошо. «Power of Two Choices» — улучшение: берём двух случайных кандидатов и выбираем того, у кого меньше соединений.

```python
import random

class PowerOfTwoChoices:
    def __init__(self, servers: list[Server]):
        self.servers = servers
    
    def next_server(self) -> Server:
        # Берём двух случайных кандидатов
        a, b = random.sample(self.servers, 2)
        # Выбираем менее нагруженного
        return a if a.active_connections <= b.active_connections else b
```

Математически доказано, что этот алгоритм приводит к распределению O(log log n) против O(log n) у случайного выбора.

## Health Checks

Балансировщик должен знать, какие серверы работают. Для этого используются health checks.

```yaml
# HAProxy конфигурация с health checks
backend api_servers
    balance roundrobin
    
    option httpchk GET /health
    http-check expect status 200
    
    # Активный health check: каждые 2 секунды
    server app1 192.168.1.10:8080 check inter 2s fall 3 rise 2
    #   fall 3: считать недоступным после 3 подряд неудачных проверок
    #   rise 2: считать доступным после 2 подряд успешных проверок
    server app2 192.168.1.11:8080 check inter 2s fall 3 rise 2
    server app3 192.168.1.12:8080 check inter 2s fall 3 rise 2
```

```python
# Endpoint /health в приложении
from flask import Flask, jsonify
import psycopg2

app = Flask(__name__)

@app.route('/health')
def health():
    """Health check endpoint для балансировщика."""
    checks = {}
    
    # Проверяем подключение к БД
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=2)
        conn.close()
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {e}'
    
    # Проверяем Redis
    try:
        redis_client.ping()
        checks['redis'] = 'ok'
    except Exception as e:
        checks['redis'] = f'error: {e}'
    
    all_ok = all(v == 'ok' for v in checks.values())
    status_code = 200 if all_ok else 503
    
    return jsonify({
        'status': 'healthy' if all_ok else 'unhealthy',
        'checks': checks
    }), status_code
```

## Sticky Sessions

Sticky sessions (липкие сессии) обеспечивают, что все запросы от одного пользователя попадают на один backend сервер. Это нужно, если состояние сессии хранится в памяти сервера (хотя лучшая практика — хранить сессии в Redis).

```nginx
# Nginx sticky sessions через cookie
upstream backend {
    sticky cookie srv_id expires=1h path=/;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
}
# Nginx добавит cookie srv_id с ID сервера.
# Повторный запрос с этим куком → попадёт на тот же сервер.
```

**Проблемы sticky sessions:**
- При падении сервера — пользователь теряет сессию
- Неравномерное распределение (один сервер может получить "тяжёлых" пользователей)
- Усложняет горизонтальное масштабирование

**Рекомендация:** Лучше делать stateless приложения, хранить сессии в Redis, и не нужны sticky sessions вообще.

## CDN: Content Delivery Network

CDN — это глобально распределённая сеть серверов, цель которой — доставить контент пользователю с минимальной задержкой, обслуживая его с ближайшего сервера.

### Архитектура CDN

```
          Пользователь в Берлине
                    │
            DNS запрос example.com
                    │
             DNS сервер CDN
                    │
         Отвечает IP ближайшего PoP
                    │
         ┌──────────▼──────────┐
         │  Frankfurt PoP      │
         │  (Point of Presence)│
         │  ┌───────────────┐  │
         │  │  Edge Server  │  │
         │  │  Cache: HIT   │  │
         │  └───────────────┘  │
         └─────────────────────┘
                 Или при Cache MISS:
                    │
           ┌────────▼────────┐
           │  Origin Server  │
           │  (ваш сервер)   │
           └─────────────────┘
```

**PoP (Point of Presence)** — точка присутствия CDN. Cloudflare имеет более 300 PoP по всему миру, Akamai — более 4000.

### Кеширование в CDN

```
# Заголовки HTTP для управления кешированием на CDN

# Кешировать 1 час на CDN, 10 минут в браузере
Cache-Control: public, s-maxage=3600, max-age=600

# Не кешировать вообще (для API ответов с персональными данными)
Cache-Control: private, no-store

# Кешировать, но всегда перепроверять у origin
Cache-Control: public, no-cache

# Stale-while-revalidate: отдавать старый кеш пока обновляем фоново
Cache-Control: public, max-age=3600, stale-while-revalidate=86400
```

```javascript
// Cloudflare Workers: пример настройки кеша на edge
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Статические ресурсы — кешируем долго
    if (url.pathname.startsWith('/static/')) {
      const response = await fetch(request);
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Cache-Control', 'public, max-age=31536000');
      return newResponse;
    }
    
    // API — не кешируем
    if (url.pathname.startsWith('/api/')) {
      return fetch(request);
    }
    
    // HTML страницы — кешируем с короткой жизнью
    const cacheKey = new Request(url.toString(), request);
    const cache = caches.default;
    
    let response = await cache.match(cacheKey);
    if (!response) {
      response = await fetch(request);
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Cache-Control', 'public, max-age=300');
      // Кладём в кеш асинхронно
      event.waitUntil(cache.put(cacheKey, newResponse.clone()));
      response = newResponse;
    }
    
    return response;
  }
}
```

### Cache Invalidation

Cache invalidation — одна из двух сложнейших проблем в CS (вторая — придумать названия переменных). Как убрать устаревший контент из CDN?

**Методы инвалидации:**

1. **TTL (Time to Live)** — контент автоматически удаляется через заданное время
2. **Purge API** — явный запрос к CDN на удаление конкретного URL
3. **Surrogate Keys / Cache Tags** — теги для инвалидации групп ресурсов

```bash
# Cloudflare API: инвалидация конкретных URL
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
  -H "Authorization: Bearer ${CF_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "files": [
      "https://example.com/index.html",
      "https://example.com/products/123"
    ]
  }'

# Инвалидация по тегам (Cloudflare Enterprise, Fastly)
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
  -H "Authorization: Bearer ${CF_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"tags": ["product-123", "category-electronics"]}'
```

```python
# При обновлении продукта в БД — инвалидируем кеш
def update_product(product_id: int, new_data: dict):
    # Обновляем БД
    db.execute(
        "UPDATE products SET ... WHERE id = ?",
        (product_id,)
    )
    
    # Инвалидируем CDN кеш
    cloudflare.purge_cache(urls=[
        f"https://example.com/products/{product_id}",
        f"https://example.com/api/products/{product_id}",
        "https://example.com/products/"  # Список продуктов тоже устарел
    ])
```

### Популярные CDN провайдеры

| Провайдер | PoP | Особенности |
|-----------|-----|-------------|
| Cloudflare | 300+ | Лучшие DDoS protection, Workers, бесплатный план |
| Fastly | 90+ | Instant purge (<150ms), VCL конфигурация |
| Akamai | 4000+ | Самый большой, enterprise, высокая цена |
| AWS CloudFront | 450+ | Интеграция с AWS сервисами |
| Bunny CDN | 110+ | Доступный, хорошее соотношение цена/качество |

## Anycast: один IP — много серверов

Anycast — технология маршрутизации, при которой один и тот же IP-адрес объявляется множеством серверов в разных точках мира. BGP (Border Gateway Protocol) направляет пользователя к ближайшему серверу с этим IP.

```
IP: 1.1.1.1 (Cloudflare DNS)
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           ▼           ▼
 Frankfurt   New York    Singapore
 1.1.1.1    1.1.1.1     1.1.1.1
    ▲           ▲           ▲
    │           │           │
 Европа      Америка      Азия
 (пользователи попадают на ближайший PoP по BGP)
```

**Как работает Anycast через BGP:**
1. Несколько серверов анонсируют один IP-адрес в BGP
2. Интернет-провайдеры (AS) обновляют свои таблицы маршрутизации
3. Трафик автоматически идёт по кратчайшему пути (обычно = ближайший физически)

**Применение Anycast:**
- **DNS** — 1.1.1.1 (Cloudflare), 8.8.8.8 (Google) — DNS-запрос идёт на ближайший сервер
- **CDN** — Cloudflare, Akamai используют anycast для edge серверов
- **DDoS митигация** — атака распределяется по всем PoP, не перегружая один

**Отличие от обычного DNS-балансировки:**
- DNS возвращает разные IP для разных регионов (GeoDNS)
- Anycast: один IP, маршрутизация на уровне сети

## TLS Termination

TLS termination (или SSL termination) — расшифровка HTTPS трафика на балансировщике, а не на backend серверах.

```
Клиент ──[HTTPS]──→ Load Balancer ──[HTTP]──→ Backend
                   (TLS termination)
```

**Преимущества:**
- Backend серверы не тратят CPU на криптографию
- Управление сертификатами в одном месте
- Centralised TLS policy (версии, шифры, HSTS)

**TLS re-encryption (end-to-end TLS):**

```
Клиент ──[HTTPS]──→ Load Balancer ──[HTTPS]──→ Backend
                   (TLS re-encrypt)
```

Для compliance требований (PCI DSS, HIPAA) трафик должен быть зашифрован end-to-end.

```nginx
# Nginx: TLS termination + проксирование по HTTP на backend
server {
    listen 443 ssl http2;
    
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    
    # Современные настройки TLS
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;
    
    # Проксируем на backend по HTTP
    location / {
        proxy_pass http://backend_servers;
        proxy_set_header X-Forwarded-Proto https;  # Сообщаем backend что пришли по HTTPS
    }
}
```

## HAProxy: высокопроизводительный балансировщик

HAProxy — один из самых производительных L4/L7 балансировщиков. Используется в Instagram, GitHub, Stack Overflow.

```haproxy
# haproxy.cfg — полный пример конфигурации

global
    maxconn 50000
    log /dev/log local0
    
defaults
    mode http
    timeout connect 5s
    timeout client  30s
    timeout server  30s
    option httplog
    option dontlognull
    option redispatch  # При падении сервера повторить запрос на другом
    retries 3

# Статистика HAProxy (веб-интерфейс)
listen stats
    bind :8404
    stats enable
    stats uri /stats
    stats refresh 10s

# Frontend: принимаем входящие соединения
frontend http_front
    bind *:80
    # Redirect HTTP -> HTTPS
    redirect scheme https code 301 if !{ ssl_fc }

frontend https_front
    bind *:443 ssl crt /etc/ssl/certs/example.com.pem
    
    # ACL (Access Control List) для маршрутизации
    acl is_api path_beg /api/
    acl is_static path_beg /static/
    
    use_backend api_backend if is_api
    use_backend static_backend if is_static
    default_backend web_backend

# Backend серверы
backend web_backend
    balance leastconn
    
    option httpchk GET /health
    http-check expect status 200
    
    server web1 192.168.1.10:8080 check
    server web2 192.168.1.11:8080 check
    server web3 192.168.1.12:8080 check

backend api_backend
    balance roundrobin
    
    # Sticky sessions через cookie
    cookie SERVERID insert indirect nocache
    
    server api1 192.168.1.20:8080 check cookie api1
    server api2 192.168.1.21:8080 check cookie api2

backend static_backend
    balance uri  # По URI hash — одинаковые URL → один сервер (для кеша)
    server static1 192.168.1.30:8080 check
    server static2 192.168.1.31:8080 check
```

## AWS ALB и NLB: managed балансировщики

AWS предоставляет два основных managed балансировщика:

**Application Load Balancer (ALB)** — L7:
- HTTP/HTTPS/WebSocket/gRPC
- Path-based и host-based routing
- Интеграция с AWS WAF, Cognito
- Поддержка Lambda targets

**Network Load Balancer (NLB)** — L4:
- TCP/UDP/TLS
- Экстремальная производительность (миллионы запросов/сек)
- Статический IP (важно для whitelist у клиентов)
- Ultra-low latency

```hcl
# Terraform: создание ALB с несколькими target groups

resource "aws_lb" "main" {
  name               = "main-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 100
  
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_target_group" "api" {
  name     = "api-tg"
  port     = 8080
  protocol = "HTTP"
  vpc_id   = var.vpc_id
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/health"
    matcher             = "200"
  }
}
```

## Полная картина: как запрос путешествует по миру

Рассмотрим реальный путь запроса пользователя из Токио к сервису, хостящемуся в США:

```
1. Пользователь (Токио) вводит example.com в браузере

2. DNS-запрос:
   Browser → ISP DNS → Root DNS → .com DNS → Cloudflare DNS
   Cloudflare anycast DNS → отвечает IP ближайшего PoP
   (Токийский PoP: 104.21.x.x)

3. TCP + TLS handshake:
   Browser → Cloudflare Tokyo PoP
   [TLS termination на edge]
   Задержка: ~5ms (внутри Токио)

4. HTTP запрос на edge:
   Cloudflare проверяет кеш → Cache MISS
   Cloudflare устанавливает соединение к origin через Anycast backbone
   (Argo Smart Routing: умный маршрут через сеть Cloudflare)

5. Origin запрос:
   Cloudflare Tokyo → Cloudflare backbone → Cloudflare US PoP → AWS ALB
   Задержка backbone: ~80ms (оптимизированный маршрут vs ~130ms через обычный интернет)

6. AWS ALB:
   L7 routing: /api/* → API target group
   Health check: выбирает здоровый инстанс
   Проксирует запрос на EC2

7. Ответ:
   EC2 → ALB → Cloudflare US → backbone → Cloudflare Tokyo → Пользователь
   Cloudflare кешируeт ответ для последующих запросов

Итоговая задержка: ~100ms
Без CDN: ~200ms (прямой TCP к US серверу)
```

## Заключение

Балансировщики нагрузки, CDN и anycast — не просто оптимизации производительности. Это фундаментальные механизмы, обеспечивающие масштабируемость, отказоустойчивость и глобальное присутствие современных интернет-сервисов.

**Ключевые принципы:**
- L4 — для максимальной производительности и нон-HTTP трафика
- L7 — для умной маршрутизации, безопасности и наблюдаемости
- CDN — для статического контента и уменьшения задержки
- Anycast — для DNS, DDoS-защиты, глобально распределённых сервисов

Правильно настроенная система балансировки — это невидимая инфраструктура, которую пользователи никогда не замечают, но без которой ни один крупный сервис не работал бы.

## Литература

1. **Gregg, Brendan** — «Systems Performance: Enterprise and the Cloud», 2nd ed. Pearson, 2020. ISBN: 978-0136820154
2. **HAProxy Documentation** — «HAProxy Configuration Manual»: https://www.haproxy.org/download/2.8/doc/configuration.txt
3. **Nginx Documentation** — «Nginx Load Balancing»: https://docs.nginx.com/nginx/admin-guide/load-balancer/
4. **AWS Documentation** — «How Elastic Load Balancing works»: https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/how-elastic-load-balancing-works.html
5. **Cloudflare Blog** — «Cloudflare's Anycast Network»: https://blog.cloudflare.com/
6. **RFC 4786** — «Operation of Anycast Services» (J. Abley, K. Lindqvist): https://www.rfc-editor.org/rfc/rfc4786
7. **Mitzenmacher, Michael** — «The Power of Two Choices in Randomized Load Balancing». IEEE Transactions on Parallel and Distributed Systems, 2001
8. **Atul Adya et al.** — «Fast Distributed Transactions» — фоновое чтение о принципах маршрутизации в распределённых системах
9. **Fastly Documentation** — «Caching best practices»: https://developer.fastly.com/learning/concepts/cache-freshness/
10. **RFC 2616** — «Hypertext Transfer Protocol — HTTP/1.1», §13 Caching: https://www.rfc-editor.org/rfc/rfc2616
