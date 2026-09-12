# CONTRIBUTIONS

## Flow работы через ветки и Pull Request

Обычно работа идет так:

1. Переключиться на основную ветку:

```bash
git checkout main
```

2. Получить свежие изменения:

```bash
git pull
```

3. Создать новую ветку под свою задачу:

```bash
git checkout -b имя-ветки
```

Пример для первой лабораторной:

```bash
git checkout -b lab1
```

4. Сделать изменения в файлах.

5. Проверить, какие файлы изменились:

```bash
git status
```

6. Добавить изменения в коммит:

```bash
git add .
```

Если нужно добавить конкретный файл:

```bash
git add путь/к/файлу
```

7. Создать коммит:

```bash
git commit -m "Краткое описание изменений"
```

Пример:

```bash
git commit -m "Добавлена лабораторная работа N1"
```

8. Отправить ветку на GitHub:

```bash
git push -u origin имя-ветки
```

Пример:

```bash
git push -u origin lab1
```

9. Создать Pull Request на GitHub:

1. Открыть репозиторий на GitHub.
2. Перейти во вкладку **Pull requests**.
3. Нажать **New pull request**.
4. Выбрать свою ветку как source branch.
5. Выбрать `main` как target branch.
6. Проверить список изменений.
7. Нажать **Create pull request**.

10. После принятия Pull Request переключиться обратно на `main`:

```bash
git checkout main
```

11. Обновить локальную ветку `main`:

```bash
git pull
```

## Flow для новой лабораторной работы

### Для каждой новой лабораторной работы лучше создавать отдельную ветку.
