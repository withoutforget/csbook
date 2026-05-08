# UTC, TAI, локальные часовые пояса и DST: почему нельзя хранить «местное время»

Время кажется простой вещью — мы смотрим на часы и видим, который час. Но для компьютерных систем время является одной из самых коварных концепций. Distributed systems падают из-за рассинхронизации часов. Авиабилеты продаются дважды из-за ошибок с часовыми поясами. Люди пропускают встречи из-за летнего перевода часов. В этой статье мы разберём, как устроено время с точки зрения компьютерных систем — от атомных стандартов до практических рекомендаций для разработчиков.

## Атомное время TAI: абсолютная стабильность

Чтобы понять UTC, нужно сначала понять TAI (International Atomic Time, Международное атомное время). TAI — это наиболее точная система измерения времени, существующая на сегодняшний день.

В основе TAI лежат атомные часы. Атом цезия-133 совершает ровно 9 192 631 770 колебаний в секунду — это число было выбрано в 1967 году при переопределении секунды СИ так, чтобы она максимально точно соответствовала астрономической секунде той эпохи. Сегодня в мире работает более 400 атомных часов в 80 лабораториях, которые управляются Международным бюро мер и весов (BIPM). TAI является взвешенным средним показаний этих часов.

Ключевое свойство TAI: оно **не привязано к вращению Земли**. TAI идёт равномерно, как метроном. Это делает его идеальным для науки, навигации и любых систем, где нужна точная длительность интервалов.

```
TAI — линейная шкала, никогда не корректируется
Начало отсчёта: 1 января 1958 года, 00:00:00
Точность: 10^-16 секунды
```

Проблема TAI в том, что Земля вращается неравномерно — приливное трение, движение ледников, сейсмическая активность постепенно замедляют вращение. Если пользоваться только TAI, то через несколько тысяч лет астрономический полдень (когда солнце в зените) и TAI-полдень разойдутся на часы.

## UTC: компромисс между точностью и астрономией

Coordinated Universal Time (UTC) — это стандарт, который пытается совместить точность атомного времени с привязкой к вращению Земли. UTC определяется через TAI:

```
UTC = TAI - N секунд
```

где N — количество введённых на данный момент «високосных секунд» (leap seconds). По состоянию на 2024 год N = 37, то есть:

```
TAI = UTC + 37 секунд
```

UTC был создан в 1960 году и стандартизирован в современном виде с 1972 года. Именно UTC является де-факто стандартом для всех компьютерных систем, серверов, протоколов интернета.

### Почему UTC, а не GMT?

Часто путают UTC и GMT (Greenwich Mean Time). GMT — исторически более ранний стандарт, основанный на наблюдении за Солнцем из обсерватории в Гринвиче. Формально GMT и UTC отличаются менее чем на секунду, но GMT — это часовой пояс, а UTC — стандарт времени. Для технических систем всегда используйте UTC.

## Unix-время: секунды с начала эпохи

Для компьютеров удобнее всего хранить время в виде единственного числа. Unix timestamp (эпоха POSIX) — это количество секунд, прошедших с 1 января 1970 года 00:00:00 UTC. Это число называют «Unix time» или «POSIX time».

```python
import time
import datetime

# Текущий Unix timestamp
ts = time.time()
print(ts)  # 1715000000.123456

# Конвертация в UTC datetime
dt = datetime.datetime.utcfromtimestamp(ts)
print(dt)  # 2024-05-06 15:33:20
```

**Важная особенность Unix time**: оно намеренно игнорирует високосные секунды. В POSIX-определении каждый день содержит ровно 86400 секунд. Это упрощает работу, но создаёт проблемы при необходимости точного подсчёта интервалов через моменты добавления секунд.

### Проблема 2038 года

Unix time хранится как 32-битное знаковое целое во многих старых системах. Максимальное значение 32-битного int со знаком — 2 147 483 647, что соответствует 19 января 2038 года 03:14:07 UTC. После этого момента переполнение произойдёт и счётчик сбросится в отрицательное число.

```c
// 32-bit проблема
int32_t ts = 2147483647;  // 19 Jan 2038 03:14:07
ts++;  // -2147483648 — катастрофа!

// Решение — 64-bit
int64_t ts64 = 2147483648LL;  // Работает корректно
```

64-битный Unix timestamp покрывает диапазон ±292 миллиарда лет — вполне достаточно.

## Часовые пояса: не просто смещение

Большинство разработчиков думают, что часовой пояс — это просто числовое смещение от UTC: «Москва — UTC+3, Нью-Йорк — UTC-5». Это **опасное упрощение**, которое ведёт к реальным багам.

### Проблема 1: Политические изменения

Часовые пояса — это политические, а не физические конструкции. Правительства меняют их, когда им угодно:

- **Самоа, 2011**: Самоа (не путать с Американским Самоа) пропустила один день — 29 декабря 2011 года. Страна перешла с UTC-11 на UTC+13, чтобы синхронизироваться с Австралией и Новой Зеландией — ключевыми торговыми партнёрами. Жители легли спать 29 декабря вечером... и проснулись 31 декабря утром.

- **Венесуэла, 2007**: Уго Чавес перевёл страну на UTC-4:30 вместо UTC-4, чтобы «дать детям больше утреннего солнца». В 2016 году Венесуэла вернулась на UTC-4.

- **Россия**: До 2014 года Крым жил по UTC+2/UTC+3. После 2014 — по UTC+3/UTC+4. Несколько регионов меняли смещения в 2010-2014 годах.

- **США**: Индиана долго не имела единого стандарта — разные округа жили по разным правилам.

Если хранить время как «UTC+3», при изменении правил придётся пересчитывать всё. Если хранить как UTC + tzid (идентификатор часового пояса), достаточно обновить базу данных часовых поясов.

### Проблема 2: DST (Daylight Saving Time)

DST, или «летнее время» — практика перевода часов на час вперёд летом. Звучит просто, но на практике это источник бесконечных багов.

**Перевод вперёд (spring forward)**: В воскресенье 10 марта 2024 года в 2:00 ночи США переводят часы на 3:00. Это означает, что 2:30 утра в этот день **не существует** в America/New_York. Если запланировать встречу на «2:30 AM 10 марта», что произойдёт?

**Перевод назад (fall back)**: В ноябре в 2:00 ночи часы переводят обратно на 1:00. Это означает, что 1:30 AM существует **дважды** — до и после перевода. Какое из двух?

```python
from zoneinfo import ZoneInfo
from datetime import datetime

tz = ZoneInfo('America/New_York')

# Несуществующее время
dt = datetime(2024, 3, 10, 2, 30, tzinfo=tz)
print(dt)  # Python обработает это, но поведение неочевидно

# Неоднозначное время
dt1 = datetime(2024, 11, 3, 1, 30, tzinfo=tz)
# Это 1:30 до перевода или после?
```

**Реальный баг**: Один из популярных европейских авиаперевозчиков несколько лет назад имел баг в системе бронирования. При переводе часов ночью некоторые рейсы «улетали» до начала продажи мест, что приводило к двойному бронированию.

### IANA tz database: единственный авторитетный источник

IANA Timezone Database (также называемая Olson database, tzdata) — это стандартный источник правил часовых поясов. Она содержит не просто текущие смещения, но **полную историю** каждого часового пояса с 1970 года.

```
# Из базы данных IANA: фрагмент для Europe/Moscow
Zone Europe/Moscow  2:30    -       LMT     1880
                    2:30    Russia  MMT     1930 Jun 21
                    3:00    Russia  MSK     1991 Mar 31 2:00s
                    2:00    Russia  EE%sT   1992 Jan 19 2:00s
                    3:00    Russia  MSK     2011 Mar 27 2:00s
                    4:00    -       MSK     2014 Oct 26 2:00s
                    3:00    -       MSK
```

Видно, как менялось московское время на протяжении истории. Идентификаторы часовых поясов в IANA имеют вид `Region/City`, например:
- `Europe/Moscow`
- `America/New_York`
- `Asia/Tokyo`
- `Pacific/Apia` (Самоа)

Никогда не используйте числовые смещения как идентификаторы часовых поясов! Используйте строковые IANA-идентификаторы.

## Python: правильная работа со временем

Рассмотрим практический код для работы со временем в Python.

### Модуль zoneinfo (Python 3.9+)

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Текущее время UTC
now_utc = datetime.now(timezone.utc)
print(now_utc)  # 2024-05-06 15:33:20.123456+00:00

# Конвертация в московское время
moscow = ZoneInfo('Europe/Moscow')
now_moscow = now_utc.astimezone(moscow)
print(now_moscow)  # 2024-05-06 18:33:20.123456+03:00

# Конвертация в нью-йоркское время
ny = ZoneInfo('America/New_York')
now_ny = now_utc.astimezone(ny)
print(now_ny)  # 2024-05-06 11:33:20.123456-04:00
```

### Naive vs aware datetime

В Python существует критическое различие между "naive" и "aware" объектами datetime:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# НЕПРАВИЛЬНО: naive datetime (без информации о часовом поясе)
naive = datetime(2024, 5, 6, 15, 30)
print(naive.tzinfo)  # None — это опасно!

# ПРАВИЛЬНО: aware datetime с UTC
aware_utc = datetime(2024, 5, 6, 15, 30, tzinfo=timezone.utc)
print(aware_utc.tzinfo)  # UTC

# ПРАВИЛЬНО: aware datetime с часовым поясом
aware_moscow = datetime(2024, 5, 6, 18, 30, tzinfo=ZoneInfo('Europe/Moscow'))
print(aware_moscow.tzinfo)  # Europe/Moscow

# Правильное сравнение
print(aware_utc == aware_moscow)  # False (разные моменты времени)
```

Никогда не используйте naive datetime в production коде! Всегда явно указывайте часовой пояс.

### Хранение времени в базе данных

```python
import psycopg2
from datetime import datetime, timezone

conn = psycopg2.connect(dsn)
cur = conn.cursor()

# НЕПРАВИЛЬНО: хранить "местное" время
local_time = datetime(2024, 5, 6, 18, 30)  # naive — неизвестно, какой пояс
cur.execute("INSERT INTO events (time) VALUES (%s)", (local_time,))

# ПРАВИЛЬНО: хранить UTC
utc_time = datetime(2024, 5, 6, 15, 30, tzinfo=timezone.utc)
cur.execute("INSERT INTO events (time) VALUES (%s)", (utc_time,))

# ЛУЧШЕЕ: хранить UTC + tzid для отображения пользователю
cur.execute(
    "INSERT INTO events (utc_time, user_timezone) VALUES (%s, %s)",
    (utc_time, 'Europe/Moscow')
)
```

### Работа с DST

```python
from datetime import datetime
from zoneinfo import ZoneInfo

ny = ZoneInfo('America/New_York')

# Создание времени в период DST
summer = datetime(2024, 7, 15, 12, 0, tzinfo=ny)
print(summer.utcoffset())  # -04:00 (EDT — летнее время)

winter = datetime(2024, 12, 15, 12, 0, tzinfo=ny)
print(winter.utcoffset())  # -05:00 (EST — стандартное время)

# Проверка, действует ли DST
print(summer.dst())   # 1:00:00 (один час разницы)
print(winter.dst())  # 0:00:00 (DST не действует)
```

### pytz: устаревший, но распространённый

До Python 3.9 широко использовался пакет `pytz`. Он имеет неочевидный API — нужно использовать `localize()` вместо `replace()`:

```python
import pytz
from datetime import datetime

moscow = pytz.timezone('Europe/Moscow')

# НЕПРАВИЛЬНО с pytz
wrong = datetime(2024, 5, 6, 18, 30, tzinfo=moscow)  
# pytz может дать неверный результат при таком использовании!

# ПРАВИЛЬНО с pytz
correct = moscow.localize(datetime(2024, 5, 6, 18, 30))
print(correct)  # 2024-05-06 18:30:00+03:00

# Конвертация
utc_time = correct.astimezone(pytz.utc)
print(utc_time)  # 2024-05-06 15:30:00+00:00
```

Рекомендуется переходить на `zoneinfo` из стандартной библиотеки.

## Ключевые принципы для разработчиков

### Правило 1: Всегда храните UTC

Сервер должен хранить всё время в UTC. Конвертация в местный часовой пояс — задача клиентского кода или слоя представления. Это позволяет:

- Корректно сравнивать времена из разных поясов
- Обрабатывать изменения правил DST без пересчёта данных
- Избежать неоднозначности при переводе часов

### Правило 2: Передавайте tzid вместе со временем

Если нужно сохранить «намерение» пользователя (например, встреча запланирована на 9:00 по московскому времени), храните пару:

```
utc_time: 2024-05-06T06:00:00Z
user_timezone: Europe/Moscow
```

При изменении правил часового пояса можно пересчитать `utc_time`, зная `user_timezone`.

### Правило 3: Используйте ISO 8601 для сериализации

```
# С UTC
2024-05-06T15:30:00Z
2024-05-06T15:30:00+00:00

# С временным поясом
2024-05-06T18:30:00+03:00

# Не делайте так — без указания пояса
2024-05-06T15:30:00  # Какой пояс?
```

### Правило 4: Обновляйте базу данных часовых поясов

IANA tz database регулярно обновляется (несколько раз в год). Всегда держите пакет `tzdata` обновлённым в production:

```bash
# Python
pip install --upgrade tzdata

# Linux
apt-get update && apt-get upgrade tzdata

# Node.js
npm update @date/tz
```

### Правило 5: Форматирование для пользователя

Разные пользователи привыкли к разным форматам дат:
- США: `5/6/2024` (месяц/день/год)
- Европа: `6.5.2024` (день.месяц.год)
- ISO: `2024-05-06` (год-месяц-день)

Для интернационализации используйте библиотеки:

```python
from babel.dates import format_datetime
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

dt = datetime(2024, 5, 6, 15, 30, tzinfo=timezone.utc)
moscow = ZoneInfo('Europe/Moscow')
dt_moscow = dt.astimezone(moscow)

# Форматирование для разных локалей
print(format_datetime(dt_moscow, locale='ru_RU'))  
# 6 мая 2024 г., 18:30:00

print(format_datetime(dt_moscow, locale='en_US'))  
# May 6, 2024, 6:30:00 PM
```

## Типичные баги с временем

### Баг 1: "Встреча в 9 утра" при переводе часов

Пользователь создаёт повторяющееся событие «каждый понедельник в 9:00». Если хранить это как фиксированный UTC-момент, после перевода часов событие сдвинется на час.

**Решение**: Для повторяющихся событий храните «правило» (RRULE в iCalendar): «каждый понедельник в 09:00 Europe/Moscow». При генерации конкретных вхождений рассчитывайте UTC-время согласно текущим правилам.

### Баг 2: Сравнение naive и aware datetime

```python
from datetime import datetime, timezone

naive = datetime(2024, 5, 6, 15, 30)
aware = datetime(2024, 5, 6, 15, 30, tzinfo=timezone.utc)

# Python выбросит TypeError
try:
    result = naive < aware
except TypeError as e:
    print(e)  # can't compare offset-naive and offset-aware datetimes
```

### Баг 3: Парсинг строк без пояса

```python
from datetime import datetime

# Эта строка не содержит информации о поясе
s = "2024-05-06 15:30:00"
dt = datetime.fromisoformat(s)
print(dt.tzinfo)  # None — опасно!

# Правильно: явно указать UTC
from datetime import timezone
dt_utc = dt.replace(tzinfo=timezone.utc)
```

### Баг 4: Логирование в местном времени

Многие системы по умолчанию логируют время в местном поясе сервера. При расследовании инцидентов, когда серверы стоят в разных датацентрах в разных поясах, такие логи сложно сопоставить.

**Решение**: Всегда логируйте в UTC с явной временной меткой ISO 8601:

```python
import logging
from datetime import datetime, timezone

class UTCFormatter(logging.Formatter):
    converter = lambda self, ts: datetime.fromtimestamp(
        ts, tz=timezone.utc
    ).timetuple()

handler = logging.StreamHandler()
handler.setFormatter(UTCFormatter('%(asctime)s UTC %(message)s'))
```

## Экзотические случаи

### Линия перемены дат

Международная линия перемены дат проходит примерно по меридиану 180°. Самоа в 2011 году перепрыгнула через неё, пропустив целый день. Аналогично, Тонга находится к востоку от 180°, но использует UTC+13, то есть формально «опережает» места, расположенные западнее неё географически.

### Отрицательный DST

Лорд-Хау (Lord Howe Island, Австралия) использует смещение UTC+10:30 летом и UTC+11 зимой, то есть DST составляет всего 30 минут. Иран использует UTC+3:30. Непал — UTC+5:45.

### Время до 1970 года

Unix timestamp для дат до 1970 года отрицателен:
```python
from datetime import datetime, timezone

dt = datetime(1969, 7, 20, 20, 17, tzinfo=timezone.utc)  # Луна, Аполлон-11
ts = dt.timestamp()
print(ts)  # -14182980.0 — отрицательное значение
```

## Итог

Работа со временем в компьютерных системах полна неочевидных ловушек. Основные принципы:

1. **TAI** — абсолютно точное атомное время, не привязанное к вращению Земли
2. **UTC** = TAI − 37 с — стандарт для компьютерных систем
3. **Unix time** — секунды с 1970-01-01 00:00:00 UTC, игнорирует високосные секунды
4. **Часовые пояса** — политические конструкции, меняющиеся со временем; используйте IANA-идентификаторы
5. **DST** — создаёт несуществующие и неоднозначные моменты времени
6. **Правило**: всегда храните UTC в БД, tzid отдельно для отображения
7. **Обновляйте** tzdata регулярно

## Литература

1. Klyne, G., Newman, C. (2002). *Date and Time on the Internet: Timestamps*. RFC 3339. IETF. https://tools.ietf.org/html/rfc3339

2. International Earth Rotation and Reference Systems Service (IERS). *Bulletins C and D* — объявления о высокосных секундах. https://www.iers.org/IERS/EN/Publications/Bulletins/bulletins.html

3. IANA Time Zone Database. https://www.iana.org/time-zones

4. Olson, A.D. (1986). *POSIX Timezone data*. Оригинальная база данных часовых поясов.

5. Python Software Foundation. *datetime — Basic date and time types*. Python 3 Documentation. https://docs.python.org/3/library/datetime.html

6. Python Software Foundation. *zoneinfo — IANA time zone support*. Python 3.9+ Documentation. https://docs.python.org/3/library/zoneinfo.html

7. Falsehoods Programmers Believe About Time. (2012). https://infiniteundo.com/post/25326999628/falsehoods-programmers-believe-about-time

8. Kernighan, B.W., Ritchie, D.M. (1988). *The C Programming Language* (2nd ed.). Prentice Hall.

9. The Open Group. *POSIX.1-2017 — System Interfaces: time*. https://pubs.opengroup.org/onlinepubs/9699919799/

10. Eggert, P., Olson, A. (2020). *Theory and pragmatics of the tz code and data*. https://data.iana.org/time-zones/theory.html

11. Sullivan, S. (2012). *Look Before You Leap – The Coming Leap Second and AWS*. AWS Blog. https://aws.amazon.com/blogs/aws/look-before-you-leap-the-coming-leap-second-and-aws/
