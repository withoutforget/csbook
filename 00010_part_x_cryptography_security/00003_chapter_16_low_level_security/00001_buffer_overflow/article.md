# Переполнение буфера и атаки на стек

## Введение

В ноябре 1988 года 23-летний аспирант Корнелльского университета Роберт Таппан Моррис запустил самореплицирующуюся программу, которая за несколько часов парализовала около 6000 компьютеров — примерно 10% тогдашнего Интернета. «Червь Морриса» использовал несколько уязвимостей одновременно, но ключевой из них было **переполнение буфера** в программе `fingerd`. Ущерб составил от 100 000 до 10 000 000 долларов. Это был первый масштабный компьютерный инцидент в истории.

Переполнение буфера (buffer overflow) по-прежнему остаётся в десятке наиболее опасных уязвимостей спустя 35 лет. CWE-119 (Improper Restriction of Operations within the Bounds of a Memory Buffer) стабильно входит в топ CWE списка MITRE. Понимание механики этой атаки — обязательный элемент знаний любого разработчика, работающего с системным кодом.

---

## 1. Стек вызовов и его устройство

Чтобы понять переполнение буфера, нужно понимать структуру стека вызовов во время исполнения функции.

### Как работает стек

В архитектуре x86-64 стек растёт вниз (от старших адресов к младшим). При вызове функции процессор помещает на стек:

1. **Аргументы функции** (часть — через регистры в x86-64: rdi, rsi, rdx, rcx, r8, r9; остальные — через стек)
2. **Адрес возврата** (return address) — адрес следующей инструкции в вызывающей функции
3. **Сохранённый rbp** (base pointer вызывающей функции)
4. **Локальные переменные** функции, включая буферы

```
+------------------+  ← высокие адреса
|   аргументы      |
+------------------+
|  адрес возврата  |  ← сохранённый RIP
+------------------+
|  сохранённый RBP |
+------------------+  ← rbp указывает сюда
|  локальные var   |
|  ...             |
|  буфер[256]      |  ← начало буфера (низкий адрес)
+------------------+  ← низкие адреса (rsp — вершина стека)
```

Ключевое наблюдение: **буфер находится ниже адреса возврата в памяти**. Запись за границу буфера в направлении роста индексов (вверх по адресам) перезапишет сначала локальные переменные, затем сохранённый rbp, затем **адрес возврата**.

### Классический пример уязвимого кода на C

```c
#include <stdio.h>
#include <string.h>

// УЯЗВИМАЯ ФУНКЦИЯ — никогда не используйте так!
void vulnerable_function(char *input) {
    char buffer[64];  // Буфер на стеке, 64 байта
    
    // gets() не проверяет длину — уязвима по определению!
    // Функция удалена из C11 за опасность
    gets(buffer);  // Читает до '\n' или EOF — без ограничений!
    
    // strcpy() тоже не проверяет длину
    strcpy(buffer, input);  // Копирует пока не встретит '\0'
    
    printf("Input: %s\n", buffer);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Usage: %s <input>\n", argv[0]);
        return 1;
    }
    vulnerable_function(argv[1]);
    return 0;
}
```

Если `input` содержит более 64 байт, запись выйдет за пределы `buffer` и перезапишет смежные области стека.

---

## 2. Механика эксплойта: шаги атаки

### Шаг 1: Определение смещения

Атакующий должен найти точное смещение от начала буфера до адреса возврата. Инструменты:

```bash
# Генерация циклического паттерна (pwntools)
python3 -c "from pwn import cyclic; print(cyclic(200).decode())"
# aaaaaaaabaaaaaaacaaaaaaadaaaaaaaeaaaaaaafaaaaaaagaaa...

# После краша программы:
# (gdb) x/gx $rsp  → 0x6161616161616166 ('aaaaaaaaf')
# python3 -c "from pwn import cyclic_find; print(cyclic_find(0x6161616161616166))"
# → 72 (смещение до адреса возврата)
```

### Шаг 2: Контроль адреса возврата

```c
// Предположим: буфер 64 байта + 8 байт сохранённого rbp = 72 байта до ret addr
// Компоновка payload:
// [64 байта буфер] + [8 байт rbp] + [8 байт новый адрес возврата]

// В Python (pwntools):
from pwn import *

offset = 72  # смещение до ret addr
ret_addr = 0xdeadbeef  # адрес shellcode или функции

payload = b'A' * offset          # заполнить буфер и rbp
payload += p64(ret_addr)         # перезаписать адрес возврата (little-endian)

# При исполнении функция вернётся на 0xdeadbeef вместо легитимного адреса
```

### Шаг 3: Shellcode

Классический стек-смашинг предполагает размещение исполняемого кода прямо в буфере:

```c
// x86-64 Linux shellcode — execve("/bin/sh", NULL, NULL)
// Длина: 27 байт
unsigned char shellcode[] = {
    0x48, 0x31, 0xd2,              // xor    rdx, rdx
    0x48, 0x31, 0xf6,              // xor    rsi, rsi
    0x48, 0xbb, 0x2f, 0x62, 0x69,  // mov    rbx, '/bin/sh\0'
    0x6e, 0x2f, 0x73, 0x68, 0x00,
    0x53,                          // push   rbx
    0x48, 0x89, 0xe7,              // mov    rdi, rsp
    0xb8, 0x3b, 0x00, 0x00, 0x00,  // mov    eax, 59 (SYS_execve)
    0x0f, 0x05                     // syscall
};
// payload = shellcode + padding + [адрес начала shellcode в стеке]
```

---

## 3. Функции-виновники и их безопасные альтернативы

Ряд функций стандартной библиотеки C исторически стал источником переполнений буфера:

| Опасная функция | Проблема | Безопасная замена |
|-----------------|----------|-------------------|
| `gets(buf)` | Нет ограничения на длину | `fgets(buf, size, stdin)` |
| `strcpy(dst, src)` | Копирует без ограничений | `strncpy(dst, src, n)` или `strlcpy(dst, src, n)` |
| `strcat(dst, src)` | Нет проверки размера dst | `strncat(dst, src, n)` или `strlcat(dst, src, n)` |
| `sprintf(buf, fmt, ...)` | Неограниченная запись | `snprintf(buf, size, fmt, ...)` |
| `scanf("%s", buf)` | Нет ограничения | `scanf("%63s", buf)` (с явным размером) |
| `vsprintf` | Как sprintf | `vsnprintf` |

```c
#include <stdio.h>
#include <string.h>
#include <bsd/string.h>  // для strlcpy/strlcat на Linux

// ПРАВИЛЬНЫЙ вариант
void safe_function(const char *input) {
    char buffer[64];
    
    // strncpy: копирует n байт, но НЕ гарантирует нуль-терминатор!
    strncpy(buffer, input, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\0';  // явный нуль-терминатор
    
    // strlcpy: всегда нуль-терминирует, возвращает длину src
    // (BSD функция, требует -lbsd на Linux)
    size_t result = strlcpy(buffer, input, sizeof(buffer));
    if (result >= sizeof(buffer)) {
        // Обрезание! Обработать ошибку
        fprintf(stderr, "Input truncated\n");
        return;
    }
    
    // snprintf для форматированного вывода
    char message[128];
    int written = snprintf(message, sizeof(message), 
                          "Input was: %s", buffer);
    if (written >= (int)sizeof(message)) {
        fprintf(stderr, "Message truncated\n");
    }
    
    printf("%s\n", message);
}

// Ещё лучше — использовать динамическую память
#include <stdlib.h>
char* safe_copy(const char *input) {
    size_t len = strlen(input);
    char *result = malloc(len + 1);
    if (!result) return NULL;
    memcpy(result, input, len + 1);
    return result;  // вызывающий код должен free()
}
```

### strlcpy vs strncpy — ключевые различия

```c
// strncpy: ОПАСНАЯ ловушка
char buf[8];
strncpy(buf, "Hello, World!", 8);
// buf = {'H','e','l','l','o',',',' ','W'} — без нуль-терминатора!
// printf("%s", buf) — неопределённое поведение

// strlcpy: безопасная семантика
strlcpy(buf, "Hello, World!", sizeof(buf));
// buf = "Hello, " — всегда нуль-терминировано
```

---

## 4. Переполнение кучи (Heap Overflow)

Не только стек подвержен переполнениям. Динамически выделяемые буферы в куче также могут быть переполнены.

```c
#include <stdlib.h>
#include <string.h>

typedef struct {
    char name[32];
    void (*callback)(void);  // указатель на функцию!
} UserRecord;

void admin_action(void) {
    printf("ADMIN: executing privileged action!\n");
    system("/bin/sh");  // в реальном эксплойте
}

void normal_action(void) {
    printf("Normal user action\n");
}

// Уязвимый код
void process_input(const char *name, size_t name_len) {
    UserRecord *record = malloc(sizeof(UserRecord));
    record->callback = normal_action;
    
    // Если name_len > 32 — запись перезапишет callback!
    memcpy(record->name, name, name_len);  // нет проверки!
    
    record->callback();  // Вызов: теперь вызовет что угодно
    free(record);
}

// Атака:
// name = "A" * 32 + адрес_admin_action (в little-endian)
// callback будет перезаписан адресом admin_action
```

### Структура кучи glibc (ptmalloc2)

Каждый выделенный блок в glibc имеет заголовок:

```
+-------------------+
| size | prev_size  |  ← metadata (16 байт в 64-bit)
+-------------------+  ← malloc() возвращает указатель сюда
|  данные           |
|  ...              |
+-------------------+
| size следующего   |  ← metadata следующего блока
```

Переполнение одного блока может испортить метаданные следующего, что при `free()` приводит к запуску произвольного кода через механизм `unlink`.

---

## 5. Heap Spray — атака распылением кучи

Heap spray — техника повышения надёжности эксплойта при нестабильных адресах:

```c
// Концепция heap spray в C
// Атакующий выделяет много блоков, заполненных NOP-слайдом + shellcode
// Цель: сделать так, чтобы любой адрес попал в shellcode

// Псевдокод атаки через браузерный JavaScript (исторически):
// for (var i = 0; i < 200; i++) {
//     heap[i] = NOP_SLED + SHELLCODE;  // каждый блок ~1MB
// }
// Перезаписать указатель на любой адрес в диапазоне 0x08000000-0x0a000000
// Вероятность попасть в NOP sled очень высока

// На C — концептуальный пример
#include <stdlib.h>
#define NOP 0x90
#define SPRAY_COUNT 1000
#define SPRAY_SIZE  (1024 * 1024)  // 1 MB каждый

void heap_spray_demo(unsigned char *shellcode, size_t sc_len) {
    unsigned char *spray[SPRAY_COUNT];
    
    for (int i = 0; i < SPRAY_COUNT; i++) {
        spray[i] = malloc(SPRAY_SIZE);
        if (!spray[i]) break;
        
        // Заполняем NOP-слайдом
        memset(spray[i], NOP, SPRAY_SIZE - sc_len);
        // Копируем shellcode в конец
        memcpy(spray[i] + SPRAY_SIZE - sc_len, shellcode, sc_len);
    }
    // Теперь куча заполнена shellcode в предсказуемых адресах
}
```

---

## 6. Реальный случай: Heartbleed (CVE-2014-0160)

Heartbleed — одна из самых известных уязвимостей переполнения буфера в истории. Найдена в OpenSSL в апреле 2014 года, существовала с декабря 2011.

### Механика уязвимости

Heartbleed — это **heap read overflow** (переполнение при чтении, не записи). Уязвимость находилась в реализации расширения TLS Heartbeat (RFC 6520).

```c
// Упрощённый уязвимый код из OpenSSL (dl/ssl/t1_lib.c)
// Реальный код: https://github.com/openssl/openssl/blob/OpenSSL_1_0_1f/ssl/t1_lib.c

int tls1_process_heartbeat(SSL *s) {
    unsigned char *p = &s->s3->rrec.data[0];
    unsigned short hbtype;
    unsigned int payload;
    
    // Тип heartbeat (1 = request, 2 = response)
    hbtype = *p++;
    
    // Читаем длину payload ИЗ ПАКЕТА — без проверки!
    n2s(p, payload);  // payload = значение из сети (до 65535)
    
    // Выделяем буфер для ответа
    unsigned char *buffer = OPENSSL_malloc(1 + 2 + payload + padding);
    unsigned char *bp = buffer;
    
    // УЯЗВИМОСТЬ: копируем payload байт из входного пакета,
    // но не проверяем, что в пакете реально есть столько данных!
    // p может указывать на данные пакета, а payload = 65535,
    // тогда как реальных данных в пакете может быть 0
    memcpy(bp, p, payload);  // читаем за пределы пакета!
    
    // Возвращаем ответ — который содержит данные из heap!
    // (приватные ключи, пароли, куки сессий...)
    
    return 0;
}

// ИСПРАВЛЕННЫЙ код (OpenSSL 1.0.1g):
int tls1_process_heartbeat_fixed(SSL *s) {
    unsigned char *p = &s->s3->rrec.data[0];
    unsigned short hbtype;
    unsigned int payload;
    unsigned int padding = 16;
    
    hbtype = *p++;
    n2s(p, payload);
    
    // КЛЮЧЕВАЯ ПРОВЕРКА: убеждаемся, что пакет реально содержит payload байт
    if (1 + 2 + payload + padding > s->s3->rrec.length) {
        return 0;  // Пакет некорректен — отбросить
    }
    
    // Теперь безопасно копировать
    unsigned char *buffer = OPENSSL_malloc(1 + 2 + payload + padding);
    unsigned char *bp = buffer;
    memcpy(bp, p, payload);
    
    return 0;
}
```

### Масштаб последствий

- Затронуто ~17% защищённых веб-сайтов Интернета
- Уязвимость позволяла читать приватный ключ сервера (возможность MITM атак)
- Пользовательские данные: куки сессий, пароли — всё в памяти процесса
- Патч появился через 2 часа после публикации, но обновление всех систем заняло месяцы

---

## 7. Пример на C: полная демонстрация

Ниже — учебный пример, демонстрирующий проблему и решение (компилируйте с отключёнными защитами только в изолированной среде):

```c
// Файл: overflow_demo.c
// Компиляция БЕЗ защит (для демонстрации):
// gcc -o vuln overflow_demo.c -fno-stack-protector -z execstack -no-pie
//
// Компиляция С защитами (правильно):
// gcc -o safe overflow_demo.c -fstack-protector-strong -D_FORTIFY_SOURCE=2 -pie -fPIE

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// ===== УЯЗВИМЫЕ ФУНКЦИИ =====

void secret_function(void) {
    printf("[!] Секретная функция вызвана!\n");
    // В реальном эксплойте здесь был бы shell
}

void vulnerable_echo(void) {
    char buffer[64];
    printf("Введите строку: ");
    gets(buffer);   // ОПАСНО! Удалена из C11
    printf("Вы ввели: %s\n", buffer);
}

// ===== БЕЗОПАСНЫЕ ФУНКЦИИ =====

void safe_echo(void) {
    char buffer[64];
    printf("Введите строку: ");
    
    // fgets с явным ограничением размера
    if (fgets(buffer, sizeof(buffer), stdin) == NULL) {
        perror("fgets");
        return;
    }
    
    // Убираем '\n' если есть
    size_t len = strlen(buffer);
    if (len > 0 && buffer[len-1] == '\n') {
        buffer[len-1] = '\0';
    }
    
    printf("Вы ввели: %s\n", buffer);
}

// ===== ПАРСИНГ ВХОДНЫХ ДАННЫХ =====

// Уязвимый парсер пакетов
typedef struct {
    uint16_t length;
    char data[256];
} Packet;

// Небезопасно: length не проверяется
void process_packet_unsafe(const uint8_t *raw, size_t raw_size) {
    Packet pkt;
    uint16_t claimed_length = *(uint16_t *)raw;
    
    // Копируем claimed_length байт, но в data есть только 256!
    memcpy(pkt.data, raw + 2, claimed_length);  // переполнение!
    
    printf("Processed %u bytes\n", claimed_length);
}

// Безопасно: всегда проверяем claimed vs actual
void process_packet_safe(const uint8_t *raw, size_t raw_size) {
    if (raw_size < 2) {
        fprintf(stderr, "Packet too short\n");
        return;
    }
    
    uint16_t claimed_length = *(uint16_t *)raw;
    
    // 1. Проверка claimed_length vs буфер назначения
    if (claimed_length > 256) {
        fprintf(stderr, "Length %u exceeds buffer\n", claimed_length);
        return;
    }
    
    // 2. Проверка claimed_length vs реальный размер пакета
    if (2 + (size_t)claimed_length > raw_size) {
        fprintf(stderr, "Truncated packet\n");
        return;
    }
    
    Packet pkt;
    memcpy(pkt.data, raw + 2, claimed_length);
    pkt.length = claimed_length;
    
    printf("Processed %u bytes safely\n", claimed_length);
}

int main(void) {
    printf("Address of secret_function: %p\n", (void *)secret_function);
    printf("safe_echo demo:\n");
    safe_echo();
    return 0;
}
```

---

## 8. Инструменты обнаружения

### AddressSanitizer (ASan)

```bash
# Компиляция с ASan
gcc -fsanitize=address -fno-omit-frame-pointer -g -o program program.c
# или clang:
clang -fsanitize=address -g -o program program.c

# При переполнении ASan немедленно прерывает программу с диагностикой:
# ==12345==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x7fff...
# READ of size 100 at 0x7fff... thread T0
#     #0 0x401234 in vulnerable_function overflow_demo.c:15
#     ...
# SUMMARY: AddressSanitizer: stack-buffer-overflow
```

```python
# Запуск программы с ASan из Python
import subprocess
import os

def run_with_asan(binary_path: str, input_data: bytes) -> dict:
    """Запускает бинарник с ASan и возвращает результат"""
    env = os.environ.copy()
    env['ASAN_OPTIONS'] = 'halt_on_error=1:symbolize=1'
    
    result = subprocess.run(
        [binary_path],
        input=input_data,
        capture_output=True,
        env=env,
        timeout=10
    )
    
    return {
        'stdout': result.stdout.decode(errors='replace'),
        'stderr': result.stderr.decode(errors='replace'),
        'returncode': result.returncode,
        'crashed': result.returncode != 0
    }
```

### Valgrind

```bash
# Проверка на утечки памяти и переполнения
valgrind --tool=memcheck --leak-check=full \
         --show-leak-kinds=all \
         --track-origins=yes \
         ./program

# Valgrind обнаружит:
# Invalid write of size 1 — запись за пределы выделенной памяти
# Invalid read of size 1 — чтение за пределы
# Use of uninitialised value — использование неинициализированных данных
```

### Static Analysis (clang-tidy, cppcheck)

```bash
# clang-tidy — статический анализатор
clang-tidy program.c --checks='cppcoreguidelines-*,clang-analyzer-*'

# cppcheck — быстрый статический анализ
cppcheck --enable=all --inconclusive program.c

# Пример вывода:
# [program.c:15]: (error) Buffer is accessed out of bounds: buffer
# [program.c:23]: (warning) Return value of function gets() is not used
```

---

## 9. Безопасные паттерны в C

### Принцип безопасного буферного ввода-вывода

```c
#include <stdio.h>
#include <string.h>
#include <errno.h>

// Надёжная функция чтения строки
// Возвращает количество прочитанных байт или -1 при ошибке
ssize_t safe_readline(char *buf, size_t buf_size, FILE *stream) {
    if (!buf || buf_size == 0) return -1;
    
    if (!fgets(buf, (int)buf_size, stream)) {
        if (ferror(stream)) return -1;
        return 0;  // EOF
    }
    
    size_t len = strlen(buf);
    
    // Проверка усечения: если последний символ не '\n', строка была усечена
    if (len == buf_size - 1 && buf[len-1] != '\n') {
        // Сбрасываем остаток строки из потока
        int c;
        while ((c = fgetc(stream)) != '\n' && c != EOF);
        errno = EOVERFLOW;
        return -1;  // Сообщаем об усечении
    }
    
    // Убираем '\n'
    if (len > 0 && buf[len-1] == '\n') {
        buf[--len] = '\0';
    }
    
    return (ssize_t)len;
}

// Безопасное конкатенирование (как strlcat)
size_t safe_concat(char *dst, const char *src, size_t dst_size) {
    size_t dst_len = strnlen(dst, dst_size);
    
    if (dst_len == dst_size) {
        return dst_size + strlen(src);  // Буфер уже полон
    }
    
    size_t src_len = strlen(src);
    size_t copy_len = dst_size - dst_len - 1;  // место с учётом '\0'
    
    if (copy_len > src_len) copy_len = src_len;
    
    memcpy(dst + dst_len, src, copy_len);
    dst[dst_len + copy_len] = '\0';
    
    return dst_len + src_len;  // Как strlcat: возвращает желаемую длину
}

// Безопасная сериализация пакета
typedef struct {
    uint8_t  type;
    uint16_t payload_len;
    uint8_t  payload[1024];
} SafePacket;

// Сборка пакета с проверками
int build_packet(SafePacket *pkt, uint8_t type, 
                 const void *data, size_t data_len) {
    if (!pkt || !data) return -1;
    
    // Проверяем вместимость
    if (data_len > sizeof(pkt->payload)) {
        return -1;  // Данные не помещаются
    }
    
    pkt->type = type;
    pkt->payload_len = (uint16_t)data_len;
    memcpy(pkt->payload, data, data_len);
    
    return 0;
}

// Парсинг пакета с проверками
int parse_packet(const uint8_t *raw, size_t raw_size, SafePacket *out) {
    // Минимальный размер: 1 (type) + 2 (len) = 3 байта
    if (!raw || !out || raw_size < 3) return -1;
    
    out->type = raw[0];
    
    // Читаем длину (big-endian)
    uint16_t claimed = (uint16_t)((raw[1] << 8) | raw[2]);
    
    // 1. Проверка: claimed_len <= размер поля payload
    if (claimed > sizeof(out->payload)) {
        return -1;
    }
    
    // 2. Проверка: пакет действительно содержит столько данных
    if ((size_t)(3 + claimed) > raw_size) {
        return -1;
    }
    
    out->payload_len = claimed;
    memcpy(out->payload, raw + 3, claimed);
    
    return 0;
}
```

---

## 10. Автоматизированный поиск уязвимостей: базовый фаззер

```c
// simple_fuzzer.c — минималистичный фаззер для тестирования функций
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// Функция под тестированием
extern int parse_packet(const uint8_t *raw, size_t raw_size, void *out);

#define ITERATIONS  100000
#define MAX_SIZE    2048

void fuzz_parse_packet(void) {
    srand(time(NULL));
    uint8_t raw[MAX_SIZE];
    uint8_t out[2048];
    
    int crashes = 0;
    int iterations = 0;
    
    printf("Fuzzing parse_packet...\n");
    
    for (int i = 0; i < ITERATIONS; i++) {
        // Генерируем случайный ввод
        size_t size = rand() % MAX_SIZE;
        for (size_t j = 0; j < size; j++) {
            raw[j] = rand() % 256;
        }
        
        // Интересные граничные случаи:
        // - Объявленная длина > реального размера пакета
        if (size >= 3) {
            uint16_t big_len = (uint16_t)(size * 2);  // Больше реального!
            raw[1] = (big_len >> 8) & 0xFF;
            raw[2] = big_len & 0xFF;
        }
        
        // Вызов функции (с ASan поймает переполнение)
        int result = parse_packet(raw, size, out);
        iterations++;
        
        // В реальном фаззере: проверяем возврат из функции,
        // мониторим SIGSEGV через setjmp/longjmp или fork()
    }
    
    printf("Completed %d iterations, %d crashes\n", iterations, crashes);
}
```

---

## 11. Сравнение языков: C vs Rust vs Go

| Аспект | C | Rust | Go |
|--------|---|------|-----|
| Проверки границ массива | Нет (UB) | Да (panic в debug, проверено) | Да (panic) |
| Безопасность строк | Нет (ручная) | Yes (гарантировано типами) | Да (runtime) |
| Управление памятью | Ручное | Ownership/borrow checker | GC |
| Buffer overflow | Возможен | Невозможен | Невозможен |
| Use-after-free | Возможен | Невозможен | Невозможен |
| Производительность | Максимальная | Сопоставима с C | Чуть хуже C |
| Unsafe код | Всегда | Явный блок `unsafe {}` | Пакет `unsafe` |

```rust
// Rust: переполнение буфера невозможно без unsafe
fn safe_in_rust(input: &str) -> String {
    let mut buffer = String::with_capacity(64);
    
    // Берём только первые 64 байта — без паники
    let truncated = &input[..input.len().min(64)];
    buffer.push_str(truncated);
    
    buffer  // Никакого UB
}

// В Rust массивы проверяются на границы:
fn index_demo() {
    let arr = [1, 2, 3, 4, 5];
    let i = 10;
    // arr[i] — паника в runtime, но НЕ UB и не запуск чужого кода!
    // "thread 'main' panicked at 'index out of bounds: the len is 5 but the index is 10'"
    
    // Безопасный вариант:
    if let Some(val) = arr.get(i) {
        println!("Value: {}", val);
    } else {
        println!("Index out of bounds");
    }
}
```

```go
// Go: переполнение тоже невозможно
func safeInGo(input string) string {
    const maxLen = 64
    if len(input) > maxLen {
        return input[:maxLen]  // Срез, не копирование за границу
    }
    return input
}

// Слайсы Go всегда проверяют границы:
func indexDemo() {
    arr := []int{1, 2, 3}
    // arr[10] — panic: runtime error: index out of range [10] with length 3
    // Не UB, программа просто падает предсказуемо
}
```

---

## 12. Исторические примеры эксплойтов

| Год | Уязвимость | Программа | Тип | Последствия |
|-----|-----------|-----------|-----|-------------|
| 1988 | Morris Worm | fingerd | Stack overflow (gets) | 6000 машин, 1-10M$ |
| 1995 | Sendmail | sendmail | Heap overflow | Remote root |
| 1998 | CVE-1999-0046 | IMAP | Stack overflow | Worm |
| 2003 | MS Blaster | RPC | Heap overflow | 2M+ машин |
| 2004 | CVE-2004-0230 | Linux kernel | Off-by-one | Local root |
| 2008 | CVE-2008-4250 | MS Server | Stack overflow | Conficker worm |
| 2014 | Heartbleed | OpenSSL | Heap read overflow | Утечка приватных ключей |
| 2021 | CVE-2021-3156 | sudo | Heap overflow | Local root везде |
| 2022 | CVE-2022-0847 | Linux kernel | Dirty Pipe | Local root |

---

## Заключение

Переполнение буфера — старейший класс уязвимостей в системном программировании, но не утративший актуальности. Его понимание обязательно для:

**Для разработчика на C/C++:**
1. Использовать `fgets`, `snprintf`, `strlcpy` вместо опасных функций
2. Проверять **все** user-supplied длины: claimed vs available vs buffer size
3. Компилировать с `-fstack-protector-strong`, `-D_FORTIFY_SOURCE=2`
4. Использовать ASan/Valgrind в разработке
5. Рассмотреть переход на Rust для нового системного кода

**Для всех разработчиков:**
1. Понимать, почему C-код требует особого внимания при code review
2. Знать, что языки с memory safety (Rust, Go, Java, Python) не имеют этого класса уязвимостей
3. Использовать статический анализ в CI/CD для C/C++ кода

---

## Литература и источники

1. Aleph One. (1996). *Smashing The Stack For Fun And Profit*. Phrack Magazine, Issue 49. http://phrack.org/issues/49/14.html
2. Seacord, R.C. (2013). *Secure Coding in C and C++, 2nd Edition*. Addison-Wesley. SEI Series in Software Engineering.
3. CVE-2014-0160 (Heartbleed). https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2014-0160
4. Morris, R.T. (1988). The Morris Internet Worm. *A Tour of the Worm* by Donn Seeley. https://www.cs.utah.edu/flux/papers/worm-usenix89.pdf
5. CWE-119: Improper Restriction of Operations within the Bounds of a Memory Buffer. MITRE. https://cwe.mitre.org/data/definitions/119.html
6. NIST. Buffer Overflow Vulnerabilities. https://www.nist.gov/publications/buffer-overflows
7. Linux man page: strlcpy(3bsd). https://man7.org/linux/man-pages/man3/strlcpy.3bsd.html
8. GNU C Library: Fortified Functions. https://www.gnu.org/software/libc/manual/html_node/Source-Fortification.html
9. AddressSanitizer documentation. https://clang.llvm.org/docs/AddressSanitizer.html
10. Valgrind User Manual. https://valgrind.org/docs/manual/manual.html
