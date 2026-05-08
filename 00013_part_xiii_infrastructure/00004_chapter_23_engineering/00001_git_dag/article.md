# Git и DAG коммитов — Git хранит снимки, а не дельты; merge vs rebase и почему это важно

Git — самая распространённая система контроля версий в мире. Большинство разработчиков используют его каждый день, но немногие понимают его внутреннее устройство. Это приводит к страху перед rebase, непониманию merge conflicts, и «магическому» поведению при работе с историей. Разберём Git изнутри — это кардинально меняет понимание инструмента.

## Git как Content-Addressable Filesystem

Фундаментальная идея Git: это контент-адресуемая файловая система с интерфейсом VCS поверх неё. Каждый объект в Git хранится под именем, которое является SHA-1 хешем его содержимого.

```bash
# Создадим простой пример
mkdir git-demo && cd git-demo
git init

# Посмотрим что Git хранит внутри
echo "Hello, Git!" | git hash-object --stdin
# Вывод: 8ab686eafeb1f44702738c8b0f24f2567c36da6b
# Это SHA-1 хеш содержимого файла

# Запишем объект в репозиторий
echo "Hello, Git!" | git hash-object -w --stdin
# Теперь он хранится в .git/objects/8a/b686eafeb1f44702738c8b0f24f2567c36da6b
# Первые 2 символа = подкаталог, остальные 38 = имя файла

# Прочитаем обратно
git cat-file -p 8ab686eafeb1f44702738c8b0f24f2567c36da6b
# Hello, Git!
```

## Четыре типа объектов Git

Git хранит только четыре типа объектов:

### 1. Blob (бинарный объект)

Blob — содержимое файла. Никакого имени файла, только данные.

```bash
# Создадим файл и посмотрим его blob
echo "console.log('hello')" > hello.js
git add hello.js
git cat-file -p $(git ls-files --stage hello.js | awk '{print $2}')
# console.log('hello')

# Два файла с одинаковым содержимым = один blob!
cp hello.js hello_copy.js
git add hello_copy.js
# Git не создаёт второй blob — экономит место
```

### 2. Tree (дерево директорий)

Tree — снимок директории: список blob'ов и subtree'ов с их именами и правами.

```bash
# После коммита: смотрим на tree
git add .
git commit -m "Initial commit"

# Хеш последнего коммита
git log --oneline -1
# abc1234 Initial commit

# Смотрим tree коммита
git cat-file -p HEAD^{tree}
# 100644 blob 8ab686...  hello.js
# 100644 blob 8ab686...  hello_copy.js (тот же blob!)
# 040000 tree def9012...  src/

# Рекурсивно смотрим subtree
git ls-tree -r HEAD
```

### 3. Commit (коммит)

Commit — снимок всего репозитория в конкретный момент.

```bash
# Смотрим raw коммит
git cat-file -p HEAD

# Вывод:
# tree abc123def456...         ← ссылка на root tree
# parent 789012...             ← предыдущий коммит
# author John Doe <j@example.com> 1700000000 +0000
# committer John Doe <j@example.com> 1700000000 +0000
#
# Initial commit
```

**Ключевое понимание:** Коммит не хранит diff! Он хранит ссылку на полный снимок (tree). Когда вы делаете `git diff`, Git вычисляет разницу между двумя снимками на лету.

### 4. Tag (тег)

```bash
# Annotated tag
git tag -a v1.0.0 -m "Release 1.0.0"
git cat-file -p v1.0.0

# Вывод:
# object abc123...  ← ссылка на коммит
# type commit
# tag v1.0.0
# tagger John Doe <j@example.com>
# 
# Release 1.0.0
```

## Как Git хранит «снимки» эффективно

Если каждый коммит — полный снимок, то разве это не расточительно? Нет, по нескольким причинам:

### 1. Shared blobs

```
Репозиторий с двумя коммитами:
  
Commit 1:                    Commit 2 (изменён только file2.txt):
  tree ──→ blob:file1.txt      tree ──→ blob:file1.txt (тот же!)
            blob:file2.txt              blob:NEW_file2.txt
            blob:file3.txt              blob:file3.txt (тот же!)

Git не копирует неизменённые файлы — они ссылаются на те же blob'ы!
```

### 2. Pack Files (сжатие дельтами)

При push или `git gc` Git создаёт packfiles с дельта-компрессией:

```bash
# Посмотреть количество объектов
git count-objects -v
# count: 0          ← объекты в loose формате
# size: 0           ← размер
# in-pack: 1234     ← объекты в pack файлах
# packs: 2

# Запустить gc вручную
git gc

# Pack файлы хранятся в .git/objects/pack/
# pack-abc123.pack - сами данные (дельта-compressed)
# pack-abc123.idx  - индекс для быстрого поиска
```

## DAG коммитов

История коммитов в Git — это **DAG** (Directed Acyclic Graph, направленный ациклический граф).

```
Простая линейная история:
  A ← B ← C ← D  (HEAD)
  
  Каждый коммит указывает на родителя (parent)
  HEAD указывает на последний коммит

После ветвления:
  A ← B ← C ← D  (main)
              ↑
              E ← F  (feature)

Merge commit (два родителя):
  A ← B ← C ← D ← M  (main)
              ↑   ↑↗
              E ← F  (feature)
  
  M (merge commit) имеет двух родителей: D и F
```

```bash
# Визуализация DAG
git log --graph --oneline --all

# Вывод:
# * abc1234 (HEAD -> main) Fix bug
# *   def5678 Merge branch 'feature'
# |\
# | * ghi9012 Add feature
# | * jkl3456 Feature WIP
# * mno7890 Update docs

# Посмотреть родителей конкретного коммита
git cat-file -p def5678
# tree ...
# parent abc1234  ← первый родитель (main)
# parent jkl3456  ← второй родитель (feature)
```

## Ветки и HEAD

**Ветка** в Git — это просто файл, хранящий SHA-1 хеш коммита. Ничего больше.

```bash
# Посмотреть что такое ветка
cat .git/refs/heads/main
# abc123def456...  ← просто хеш последнего коммита

# HEAD: указатель на текущую ветку (или коммит)
cat .git/HEAD
# ref: refs/heads/main  ← обычно ссылка на ветку

# При checkout конкретного коммита (detached HEAD)
git checkout abc123
cat .git/HEAD
# abc123def456...  ← прямо на коммит, не на ветку

# Создание ветки = создание файла с хешем
git branch new-feature
cat .git/refs/heads/new-feature
# abc123...  ← тот же хеш что и main (в момент создания)
```

**Detached HEAD** — состояние, когда HEAD указывает на конкретный коммит, а не на ветку. Коммиты в этом состоянии будут «потеряны» при переключении ветки (но не сразу — reflog хранит их 90 дней).

## Merge: сохранение истории

**Merge** создаёт новый коммит с двумя (или более) родителями. История сохраняется в неизменном виде.

```bash
git checkout main
git merge feature

# Создаётся merge commit:
# git log --graph:
# *   8f9a2c3 Merge branch 'feature'
# |\
# | * 3d4e5f6 Add feature X
# | * 7a8b9c0 Feature X WIP
# * | c1d2e3f Fix critical bug
# |/
# * a1b2c3d Initial commit
```

### Fast-Forward Merge

Если ветка main не продвинулась вперёд с момента создания feature — merge просто переносит указатель:

```bash
# Перед merge:
# main: A ← B
# feature: A ← B ← C ← D

# Fast-forward merge (нет merge commit!):
git merge feature
# main: A ← B ← C ← D (просто переместил указатель)

# Чтобы всегда создавать merge commit:
git merge --no-ff feature
```

### Merge Strategies

```bash
# Ours: при конфликте всегда берём нашу версию
git merge -X ours feature

# Theirs: при конфликте всегда берём их версию
git merge -X theirs feature

# Octopus: merge нескольких веток одновременно (только для нет-конфликтов)
git merge feature-a feature-b feature-c
```

## Rebase: переписывание истории

**Rebase** берёт коммиты с одной ветки и «переигрывает» их поверх другой ветки. История становится линейной.

```bash
# Ситуация:
# main:    A ← B ← C
# feature: A ← B ← D ← E

git checkout feature
git rebase main

# После rebase:
# main:    A ← B ← C
# feature: A ← B ← C ← D' ← E'
# D' и E' — новые коммиты (новые SHA!)

# Теперь fast-forward merge в main:
git checkout main
git merge feature
# A ← B ← C ← D' ← E' (линейная история)
```

**Важно:** rebase создаёт НОВЫЕ коммиты (новые SHA). D' — это не D, хотя изменения те же.

### Механизм rebase изнутри

```bash
# Что делает rebase под капотом:
git checkout feature
git rebase main

# Внутри происходит:
# 1. Находит общего предка (B)
# 2. Сохраняет патчи от B до E (D и E)
# 3. Переключается на main (C)
# 4. Применяет патчи по одному:
#    - Применить D → получить D'
#    - Применить E → получить E'
# 5. Обновить HEAD feature → E'
```

### Interactive Rebase

```bash
# Интерактивный rebase: редактируем историю
git rebase -i HEAD~3  # Редактируем последние 3 коммита

# Открывается редактор:
# pick abc1234 Add feature
# pick def5678 Fix typo  
# pick ghi9012 Add tests

# Операции:
# pick = использовать коммит как есть
# reword = изменить сообщение
# edit = остановиться для редактирования
# squash = объединить с предыдущим (сохранить оба сообщения)
# fixup = объединить с предыдущим (отбросить сообщение)
# drop = удалить коммит

# Практический сценарий: squash "WIP" коммитов перед merge
# Меняем:
# pick abc1234 Add feature
# squash def5678 Fix typo  
# squash ghi9012 Cleanup
# →
# Получаем один коммит "Add feature" с чистой историей
```

## Rebase vs Merge: когда что использовать

```
┌────────────────────────────────────────────────────────────────┐
│                    Merge                                        │
│                                                                │
│ Сохраняет точную историю разработки                            │
│ Показывает когда ветки были созданы и объединены               │
│ Безопасно для публичных/shared веток                           │
│ История: «правдивая», но может быть запутанной                 │
│                                                                │
│ Когда использовать:                                            │
│ - Финальный merge feature branch в main                        │
│ - Когда история должна отражать реальный процесс              │
│ - Публичные ветки (не переписывать!)                           │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                    Rebase                                       │
│                                                                │
│ Создаёт линейную, чистую историю                               │
│ Проще читать git log                                           │
│ Проще делать bisect                                            │
│ НЕ безопасно для публичных веток (изменяет SHA!)               │
│                                                                │
│ Когда использовать:                                            │
│ - Обновить локальную feature branch с main                     │
│ - Очистить WIP коммиты перед code review                      │
│ - Частные (только ваши) ветки                                  │
└────────────────────────────────────────────────────────────────┘
```

**Золотое правило Rebase:** Никогда не делай rebase коммитов, которые уже были запушены в shared репозиторий.

```bash
# Почему опасно:
# Вы: main локально = A ← B ← C
# Коллега: main локально = A ← B ← C

# Вы делаете rebase и force push:
# Ваш main = A ← B' ← C' (новые SHA!)
# git push --force

# Коллега делает git pull:
# Их main = A ← B ← C ← B' ← C' (дублирование!)
# Git не знает что B и B' это "один и тот же" коммит с разными SHA
```

## Cherry-Pick: перенос конкретных коммитов

```bash
# Перенести конкретный коммит с другой ветки
git cherry-pick abc1234

# Несколько коммитов
git cherry-pick abc1234 def5678

# Диапазон коммитов
git cherry-pick abc1234..ghi9012

# Практический сценарий: hotfix
# Ситуация: критический баг исправлен в feature branch,
# нужно срочно перенести фикс в production

git checkout production
git cherry-pick feature~2  # Третий коммит от конца feature
```

## Bisect: бинарный поиск регрессии

```bash
# git bisect: найти коммит, который сломал тест
# Используется бинарный поиск в DAG → O(log n) проверок

git bisect start
git bisect bad HEAD          # Текущая версия плохая
git bisect good v1.0.0       # Версия v1.0.0 была хорошая

# Git проверяет коммит посередине:
# Bisecting: 128 revisions left to test after this (roughly 7 steps)
# [abc1234] Some commit

# Проверяем и сообщаем результат
make test && git bisect good  # или git bisect bad

# Автоматический bisect (если есть скрипт для проверки)
git bisect run ./test.sh

# В итоге Git находит первый "плохой" коммит:
# abc1234 is the first bad commit
```

## Reflog: путь назад

**Reflog** — журнал всех изменений HEAD и веток. Даже "удалённые" коммиты живут 90 дней.

```bash
# Показать историю HEAD
git reflog

# Вывод:
# abc1234 (HEAD -> main) HEAD@{0}: merge feature: Merge made...
# def5678 HEAD@{1}: checkout: moving from feature to main
# ghi9012 HEAD@{2}: commit: Add feature X
# jkl3456 HEAD@{3}: rebase (finish): returning to refs/heads/feature

# Вернуться к предыдущему состоянию (даже после hard reset!)
git checkout HEAD@{3}

# Восстановить "потерянную" ветку
git branch recovered-branch abc1234  # Если знаем SHA
git branch recovered-branch HEAD@{5}  # Через reflog
```

## Pack Files и Delta Compression

```bash
# Как Git сжимает данные при pack:

# До gc: множество loose objects
ls .git/objects/
# 12/ 34/ 56/ ab/ cd/  ← подкаталоги по первым двум символам SHA

# После gc: pack файл
git gc
ls .git/objects/pack/
# pack-abc123.idx    ← индекс для быстрого поиска
# pack-abc123.pack   ← сжатые объекты

# Как работает дельта-компрессия в pack:
# Pack файл хранит базовый объект + дельты к нему
# Например: v1.0 файл + "в v2.0 добавлена строка 42-43"
# Это похоже на diff, но Git решает какие версии использовать как базу

# Статистика pack файла
git verify-pack -v .git/objects/pack/pack-abc123.idx | sort -k 3 -n | tail -20
# Показывает самые большие объекты и уровень сжатия
```

## Практические сценарии

### Scenario 1: Очистка истории перед code review

```bash
# Ваша работа:
# git log --oneline:
# 7g8h9i WIP: trying to fix the bug
# 5e6f7g Another attempt
# 3c4d5e Started fixing bug in auth module
# 1a2b3c Previous clean commit

# Перед push: объединяем в один чистый коммит
git rebase -i HEAD~3

# В редакторе:
# pick 3c4d5e Started fixing bug in auth module
# squash 5e6f7g Another attempt
# squash 7g8h9i WIP: trying to fix the bug

# Итог: один коммит "Fix authentication bug in login module"
```

### Scenario 2: Разрешение конфликтов при rebase

```bash
git checkout feature
git rebase main

# При конфликте:
# CONFLICT (content): Merge conflict in src/auth.py
# error: could not apply abc1234... Add auth feature

# Решаем конфликт в редакторе
# Затем:
git add src/auth.py
git rebase --continue

# Если хотим отменить rebase:
git rebase --abort
```

### Scenario 3: Git Internals — понимание что происходит

```bash
# Проследим полный путь коммита
echo "test content" > newfile.txt
git add newfile.txt

# После git add: объект создан в .git/objects/
git status
# Changes to be committed: new file: newfile.txt

# Смотрим индекс (staging area)
git ls-files --stage
# 100644 abc1234... 0 newfile.txt

git commit -m "Add new file"

# Что создал git commit:
# 1. Новый blob: уже был (создан при git add)
# 2. Новый tree: включает newfile.txt
# 3. Новый commit: указывает на tree и предыдущий commit

# Проверяем
git cat-file -p HEAD
# tree def5678...
# parent ghi9012...  
# author ...
# Add new file

git cat-file -p HEAD^{tree}
# 100644 blob abc1234...  newfile.txt
# 100644 blob ...         other_file.txt
```

## Заключение

Понимание Git изнутри — это не академическое знание. Это практический инструмент:

- Знаешь что blob неизменяем → не боишься rebase (SHA меняется, но данные не теряются)
- Знаешь про reflog → не паникуешь при «потере» коммитов
- Знаешь что ветка — просто указатель → легко манипулируешь ветками
- Знаешь про DAG → понимаешь merge и rebase графически

**Главные правила:**
1. Rebase для личных веток, merge для публичных
2. `--force-with-lease` вместо `--force` (проверяет нет ли чужих коммитов)
3. `git reflog` спасёт от любой ошибки (кроме `git push --force` на shared branch)
4. `git bisect` для поиска регрессий — O(log n) vs O(n)

## Литература

1. **Chacon, Scott; Straub, Ben** — «Pro Git», 2nd ed. (бесплатно онлайн): https://git-scm.com/book/en/v2
2. **Torvalds, Linus** — Git initial announcement (2005): https://lkml.org/lkml/2005/4/6/121
3. **Git Documentation** — «Git Internals - Git Objects»: https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
4. **Git Documentation** — «Git Branching - Rebasing»: https://git-scm.com/book/en/v2/Git-Branching-Rebasing
5. **Atlassian Git Tutorial** — «Merging vs. Rebasing»: https://www.atlassian.com/git/tutorials/merging-vs-rebasing
6. **Fowler, Martin** — «Feature Branch»: https://martinfowler.com/bliki/FeatureBranch.html
7. **Trunk Based Development** — https://trunkbaseddevelopment.com/
8. **GitHub Blog** — «How Git works»: https://github.blog/2020-12-17-commits-are-snapshots-not-diffs/
9. **Julia Evans** — «Git from the inside out»: https://codewords.recurse.com/issues/two/git-from-the-inside-out
10. **Hamano, Junio C.** — «Git for Computer Scientists»: https://eagain.net/articles/git-for-computer-scientists/
