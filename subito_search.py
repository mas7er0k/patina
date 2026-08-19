#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
subito_search.py
Скрипт для поиска товаров на сайте Subito.it (Италия) с использованием Playwright.
Результаты сохраняются в Markdown-таблицу и JSON-файл.

Требования:
    pip install playwright
    playwright install chromium
"""

import argparse
import asyncio
import datetime
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

# ---------------------------------------------------------------------------
# Внутренний прокси-сервер (по умолчанию пустой)
# ---------------------------------------------------------------------------
INTERNAL_PROXY = None  # например: "127.0.0.1:8080"

# ---------------------------------------------------------------------------
# User-Agent Chrome 144+ (обновлять по необходимости)
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 "
    "Safari/537.36"
)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------
BASE_URL = "https://www.subito.it"
SEARCH_PATH = "/annunci-italia/vendita/mobili/"
MAX_RESULTS = 50
DEFAULT_TIMEOUT = 30_000  # мс


# ---------------------------------------------------------------------------
# Парсинг аргументов командной строки
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Поиск товаров на Subito.it с сохранением в MD и JSON.",
        epilog=(
            "Примеры:\n"
            '  python subito_search.py "armadio vintage"\n'
            '  python subito_search.py "divano vintage" -proxy 127.0.0.1:8080\n'
            '  python subito_search.py "tavolo vintage" -noproxy\n'
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "query",
        type=str,
        help='Поисковый запрос (например "armadio vintage")',
    )
    parser.add_argument(
        "-proxy",
        type=str,
        default=None,
        metavar="ADDRESS:PORT",
        help=(
            "Явный прокси-сервер в формате ADDRESS:PORT. "
            "Перекрывает внутренний прокси INTERNAL_PROXY."
        ),
    )
    parser.add_argument(
        "-noproxy",
        action="store_true",
        default=False,
        help=(
            "Не использовать прокси-сервер. "
            "Отменяет внутренний прокси INTERNAL_PROXY и флаг -proxy."
        ),
    )
    parser.add_argument(
        "-out",
        type=str,
        default=None,
        metavar="DIR",
        help="Папка для выходных файлов (по умолчанию — текущая рабочая папка)",
    )
    parser.add_argument(
        "-headless",
        action="store_true",
        default=True,
        help="Запуск в headless-режиме (по умолчанию включён)",
    )
    parser.add_argument(
        "-verbose",
        action="store_true",
        default=False,
        help="Подробный вывод в консоль",
    )
    return parser


# ---------------------------------------------------------------------------
# Определение используемого прокси
# ---------------------------------------------------------------------------
def resolve_proxy(cli_proxy: str | None, no_proxy: bool) -> dict | None:
    """
    Возвращает словарь для параметра proxy Playwright или None.

    Приоритет:
      1. -noproxy        →  None  (без прокси)
      2. -proxy ADDRESS   →  override  (перекрывает INTERNAL_PROXY)
      3. INTERNAL_PROXY    →  по умолчанию
    """
    if no_proxy:
        return None

    if cli_proxy is not None:
        return {"server": cli_proxy}

    if INTERNAL_PROXY is not None:
        return {"server": INTERNAL_PROXY}

    return None


# ---------------------------------------------------------------------------
# Генерация имени файла из запроса
# ---------------------------------------------------------------------------
def sanitize_filename(query: str) -> str:
    """Заменяет недопустимые символы на подчёркивание, убираем пробелы."""
    name = query.strip().lower()
    name = re.sub(r"[^\w\s-]", "_", name)
    name = re.sub(r"[\s]+", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name if name else "search"


# ---------------------------------------------------------------------------
# Парсер результатов поиска
# ---------------------------------------------------------------------------
async def parse_results(page, target_count: int = MAX_RESULTS) -> list[dict]:
    """
    Парсит результаты поиска со страницы Subito.it.
    Использует ленивую подгрузку (infinite scroll) для получения всех результатов.
    """
    results = []
    seen_urls = set()

    # Ждём загрузки списка результатов
    try:
        await page.wait_for_selector("ul.results-list li.result-item", timeout=DEFAULT_TIMEOUT)
    except PlaywrightTimeout:
        return results

    # Бесконечная прокрутка до достижения target_count
    while len(results) < target_count:
        current_items = await page.locator("ul.results-list li.result-item").all()

        if not current_items:
            break

        previous_count = len(results)

        for item in current_items:
            try:
                link = item.locator("a.result-box")
                href = await link.get_attribute("href") or ""
                # Полная URL
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = BASE_URL + href

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                title_el = item.locator(".ad-title")
                title = (await title_el.inner_text()).strip() if await title_el.count() else ""

                price_el = item.locator(".price")
                price = (await price_el.inner_text()).strip() if await price_el.count() else ""

                location_el = item.locator(".location")
                location = (await location_el.inner_text()).strip() if await location_el.count() else ""

                if title or price:
                    results.append({
                        "title": title,
                        "price": price,
                        "location": location,
                        "url": href,
                    })

                if len(results) >= target_count:
                    break

            except Exception:
                continue

        # Если новых элементов не появилось — выходим
        if len(results) == previous_count:
            break

        try:
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.5)
        except Exception:
            break

    # Ограничиваем максимум
    return results[:target_count]


# ---------------------------------------------------------------------------
# Поиск на Subito.it
# ---------------------------------------------------------------------------
async def search(query: str, proxy_cfg: dict | None, headless: bool,
                 verbose: bool = False) -> list[dict]:
    """Выполняет поиск и возвращает список результатов."""
    encoded_query = quote(query)
    search_url = f"{BASE_URL}{SEARCH_PATH}?q={encoded_query}"

    if verbose:
        print(f"[INFO]  URL поиска: {search_url}")

    results = []

    # Создаём объект stealth с нужной конфигурацией
    stealth = Stealth(
        # Все обфускации включены по умолчанию, но можно отключить отдельные
        chrome_app=True,           # window.chrome.app
        chrome_csi=True,           # window.csi
        chrome_load_times=True,    # chrome.loadTimes
        chrome_runtime=False,      # window.chrome.runtime (не нужен в headless)
        hairline=True,             # GPU hairline detection
        iframe_content_window=True, # iframe contentWindow
        media_codecs=True,         # mediaCodecs
        navigator_hardware_concurrency=True,  # hardwareConcurrency → 8
        navigator_languages=True,  # languages → it-IT, it, en-US, en
        navigator_permissions=True, # Permissions
        navigator_platform=True,   # platform → Win32
        navigator_plugins=True,    # plugins (5 fake)
        navigator_user_agent=True, # User-Agent (переопределяется ниже)
        navigator_user_agent_data=True,  # navigator.userAgentData
        navigator_vendor=True,     # vendor → Google Inc.
        navigator_webdriver=True,  # navigator.webdriver → undefined
        error_prototype=True,      # Error.prototype.stack
        sec_ch_ua=True,            # Sec-CH-UA headers
        webgl_vendor=True,         # WebGL vendor → Intel/Google
        # Переопределения
        navigator_languages_override=("it-IT", "it", "en-US", "en"),
        navigator_platform_override="Win32",
        navigator_user_agent_override=USER_AGENT,
        sec_ch_ua_override=None,   # auto-generated
        webgl_renderer_override=None,  # auto-generated
        webgl_vendor_override="Intel Inc.",
        init_scripts_only=False,   # применять через add_init_script
        script_logging=False,      # логирование скриптов
    )

    async with async_playwright() as pw:
        launch_opts: dict = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ],
        }

        if proxy_cfg is not None:
            launch_opts["proxy"] = proxy_cfg

        browser = await pw.chromium.launch(**launch_opts)

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            timezone_id="Europe/Rome",
            accept_downloads=False,
        )

        # Применяем stealth-обфускацию к контексту (все страницы наследуют)
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        if verbose:
            page.on("console", lambda msg: print(f"[CONSOLE] {msg.text}"))
            page.on("requestfailed", lambda req: print(f"[FAIL]  {req.url}  [{req.response_status}]"))

        try:
            await page.goto(search_url, timeout=DEFAULT_TIMEOUT, wait_until="domcontentloaded")
            # Ожидаем рендеринга результатов
            await page.wait_for_selector("ul.results-list li.result-item", timeout=DEFAULT_TIMEOUT)
            # Даем время на полную загрузку JS
            await asyncio.sleep(2)

            if verbose:
                print(f"[INFO]  Загружена страница, извлекаем результаты...")

            results = await parse_results(page, target_count=MAX_RESULTS)

        except PlaywrightTimeout as e:
            print(f"[ERROR] Таймаут при загрузке страницы: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] Ошибка при поиске: {e}", file=sys.stderr)
        finally:
            await browser.close()

    return results


# ---------------------------------------------------------------------------
# Сохранение в Markdown
# ---------------------------------------------------------------------------
def save_markdown(query: str, results: list[dict], output_dir: str) -> str:
    """Сохраняет результаты в Markdown-таблицу. Возвращает путь к файлу."""
    safe_name = sanitize_filename(query)
    filename = f"{safe_name}.md"
    filepath = os.path.join(output_dir, filename)

    lines = []
    lines.append(f"# Результаты поиска: {query}\n")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"Дата: {now}  |  Запрос: {query}  |  Найдено: {len(results)}\n")
    lines.append("| # | Title | Price | Location | URL |")
    lines.append("|---|-------|-------|----------|-----|")

    for i, r in enumerate(results, start=1):
        title = r.get("title", "").replace("|", "\\|").replace("\n", " ")
        price = r.get("price", "").replace("|", "\\|")
        location = r.get("location", "").replace("|", "\\|").replace("\n", " ")
        url = r.get("url", "")
        url_text = url[:60] + "..." if len(url) > 60 else url
        lines.append(f"| {i} | {title} | {price} | {location} | [{url_text}]({url}) |")

    content = "\n".join(lines) + "\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[OK]    Markdown сохранён: {filepath}")
    return filepath


# ---------------------------------------------------------------------------
# Сохранение в JSON
# ---------------------------------------------------------------------------
def save_json(query: str, results: list[dict], output_dir: str) -> str:
    """Сохраняет результаты в JSON-файл. Возвращает путь к файлу."""
    safe_name = sanitize_filename(query)
    filename = f"{safe_name}.json"
    filepath = os.path.join(output_dir, filename)

    data = {
        "query": query,
        "total": len(results),
        "results": results,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK]    JSON сохранён:     {filepath}")
    return filepath


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------
async def main_async(args: argparse.Namespace) -> int:
    """Основной асинхронный поток выполнения."""
    query = args.query
    proxy_cfg = resolve_proxy(args.proxy, args.noproxy)

    if proxy_cfg is not None:
        print(f"[INFO]  Прокси: {proxy_cfg['server']}")
    else:
        print("[INFO]  Прокси: отключён (без прокси)")

    output_dir = args.out or os.getcwd()
    os.makedirs(output_dir, exist_ok=True)

    if args.verbose:
        print(f"[INFO]  Папка вывода: {output_dir}")
        print(f"[INFO]  Headless: {args.headless}")
        print(f"[INFO]  User-Agent: {USER_AGENT[:80]}...")

    results = await search(
        query=query,
        proxy_cfg=proxy_cfg,
        headless=args.headless,
        verbose=args.verbose,
    )

    if not results:
        print("[WARN]  Результаты не найдены. Попробуйте изменить запрос или проверить соединение.", file=sys.stderr)
        return 1

    print(f"\n[INFO]  Найдено результатов: {len(results)}\n")

    md_path = save_markdown(query, results, output_dir)
    json_path = save_json(query, results, output_dir)

    # Вывод краткой сводки в консоль
    print(f"\n{'='*70}")
    print(f"  Итог: {len(results)} результат(ов)")
    print(f"    MD: {md_path}")
    print(f"    JSON: {json_path}")
    print(f"{'='*70}\n")

    return 0


def main() -> int:
    """Точка входа."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n[INFO]  Прервано пользователем.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
