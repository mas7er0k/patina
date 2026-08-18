# subito_search.py

## Описание

Скрипт для поиска товаров на сайте **Subito.it** (Италия) с использованием **Playwright** (headless Chromium).
Результаты сохраняются в двух форматах:

- **Markdown** — таблица для удобного чтения
- **JSON** — структурированные данные для обработки

## Особенности

- Поиск в категории «Мебели» (`mobili`)
- Автоматическая прокрутка (infinite scroll) для получения полных результатов
- Максимум **50 результатов** на запрос
- Поддержка прокси-сервера через CLI-флаги
- **Playwright Stealth** — полноценная маскировка под реального пользователя:
  - `navigator.webdriver` → `false`
  - `navigator.userAgent` → Chrome 144
  - `navigator.platform` → `Win32`
  - `navigator.languages` → `it-IT, it, en-US, en`
  - `navigator.plugins` → 3 плагина
  - `window.chrome` → объект с runtime
  - `navigator.hardwareConcurrency` → `8`
  - WebGL vendor → `Intel Inc.`
  - Sec-CH-UA заголовки
  - navigator.userAgentData
- Вывод результатов в текущую папку или указанную директорию

## Установка

### 1. Python 3.10+

Убедитесь, что установлен Python 3.10 или новее:

```powershell
python --version
```

### 2. Зависимости

```powershell
pip install playwright playwright-stealth
```

### 3. Браузер Chromium для Playwright

```powershell
playwright install chromium
```

### 4. Системные зависимости (если требуется)

```powershell
playwright install-deps chromium
```

## Использование

### Базовый запуск

```powershell
python subito_search.py "armadio vintage"
```

### Примеры запросов

```powershell
python subito_search.py "divano usato"
python subito_search.py "tavolo vintage"
python subito_search.py "sedia vintage"
python subito_search.py "libreria usata"
python subito_search.py "comodino antico"
```

### С прокси-сервером (через ключ `-proxy`)

```powershell
python subito_search.py "armadio vintage" -proxy 192.168.1.100:8080
```

### Без прокси (флаг `-noproxy`)

```powershell
python subito_search.py "tavolo vintage" -noproxy
```

### Вывод в указанную папку

```powershell
python subito_search.py "divano vintage" -out D:\output
```

### Подробный режим

```powershell
python subito_search.py "armadio vintage" -verbose
```

## Аргументы командной строки

| Аргумент       | Описание |
|---------------|---------|
| `query`       | Поисковый запрос (обязательный, в кавычках) |
| `-proxy ADRES:PORT` | Явный прокси-сервер (перекрывает внутренний) |
| `-noproxy`    | Отключить любой прокси (внутренний и явный) |
| `-out DIR`    | Папка для выходных файлов |
| `-headless`   | Headless-режим (по умолчанию включён) |
| `-verbose`    | Подробный вывод в консоль |

## Внутренний прокси

В коде существует переменная `INTERNAL_PROXY` (строка 28). Если она задана (например `"127.0.0.1:8080"`),
скрипт будет использовать этот прокси по умолчанию.

**Приоритет прокси:**

1. Флаг `-noproxy` → прокси отключён
2. Ключ `-proxy ADDRESS:PORT` → перекрывает `INTERNAL_PROXY`
3. `INTERNAL_PROXY` в коде → используется по умолчанию
4. Ничего не задано → прокси не используется

## Результат

После запуска в целевой папке создаются два файла:

- `armadio_vintage.md` — таблица в Markdown
- `armadio_vintage.json` — данные в JSON

### Пример Markdown

```markdown
# Результаты поиска: armadio vintage

| # | Title | Price | Location | URL |
|---|-------|-------|----------|-----|
| 1 | Poltrona vintage | 100 € | Ponzano Veneto (TV) | [ссылка](...) |
| 2 | ... | ... | ... | ... |
```

### Пример JSON

```json
{
  "query": "armadio vintage",
  "total": 50,
  "results": [
    {
      "title": "Poltrona vintage",
      "price": "100 €",
      "location": "Ponzano Veneto (TV)",
      "url": "https://www.subito.it/..."
    }
  ]
}
```

## Структура проекта

```
D:\code\
├── subito_search.py    # Основной скрипт
└── subito_readme.md    # Эта инструкция
```

## Ограничения

- Максимум **50 результатов** на страницу
- Subito.it может блокировать запросы (Cloudflare)
- Работает только при наличии Chrome/Chromium в системе
- Требуется активное интернет-соединение

## Решение проблем

### Ошибка `ModuleNotFoundError: No module named 'playwright'`

```powershell
pip install playwright
playwright install chromium
```

### Ошибка `playwright install: command not found`

Убедитесь, что `pip` установлен корректно и PATH настроен:

```powershell
python -m playwright install chromium
```

### Ошибка таймаута / страница не загружается

1. Проверьте интернет-соединение
2. Попробуйте без прокси (добавьте `-noproxy`)
3. Увеличьте таймаут в коде (строка `DEFAULT_TIMEOUT = 30000`)
4. Запустите в не-headless режиме (уберите `-headless`)

### Ошибка `Access Denied` / `403`

Сайт может блокировать IP-адреса. Попробуйте:

1. Использовать прокси (`-proxy 127.0.0.1:8080`)
2. Подождать несколько минут и повторить
3. Запустить на домашнем компьютере

### Ошибка `chromium: command not found`

```powershell
playwright install chromium
```

### Ошибка Code 127 / Chromium не найден

Установите зависимости системы:

```powershell
playwright install-deps chromium
```

## Совместимость

| Параметр         | Значение    |
|-----------------|-------------|
| Python           | 3.9+        |
| Playwright       | 1.40.0+     |
| playwright-stealth | 2.0+      |
| Browser          | Chromium    |
| OS               | Windows 10/11 (PowerShell) |

## Лицензия

Скрипт предоставлен «как есть» для личного использования.
