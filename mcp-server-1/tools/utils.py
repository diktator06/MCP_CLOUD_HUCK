"""Общие утилиты для инструментов MCP сервера."""

import os
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone
import httpx
from aiolimiter import AsyncLimiter
from mcp.types import TextContent
from fastmcp.tools.tool import ToolResult
from fastmcp import Context
from mcp.shared.exceptions import McpError, ErrorData

# Константа базового URL GitHub API
BASE_URL = "https://api.github.com"

# Константы для retry механизма
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # Базовая задержка в секундах
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}  # Статусы для retry

# Rate Limiter для GitHub API
# GitHub API лимит: 5000 запросов/час для аутентифицированных пользователей
# Используем консервативный лимит: 4000 запросов/час (≈1.1 запрос/сек)
GITHUB_RATE_LIMITER = AsyncLimiter(max_rate=1.0, time_period=1.0)  # 1 запрос в секунду


def _require_env_vars(required_vars: List[str]) -> Dict[str, str]:
    """
    Проверяет наличие обязательных переменных окружения.
    
    Args:
        required_vars: Список имен обязательных переменных окружения
        
    Returns:
        Словарь с переменными окружения
        
    Raises:
        ValueError: Если какая-то переменная отсутствует
    """
    missing = []
    env = {}
    
    for var in required_vars:
        value = os.getenv(var)
        if value is None:
            missing.append(var)
        else:
            env[var] = value
    
    if missing:
        raise ValueError(
            f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}"
        )
    
    return env


def format_api_error(response_text: str, status_code: int) -> str:
    """
    Форматирует ошибку API для пользователя.
    
    Args:
        response_text: Текст ответа от API
        status_code: HTTP статус код
        
    Returns:
        Отформатированное сообщение об ошибке
    """
    if status_code == 401:
        return "Ошибка аутентификации. Проверьте GITHUB_TOKEN."
    elif status_code == 403:
        return "Доступ запрещен. Проверьте права доступа токена GitHub."
    elif status_code == 404:
        return "Ресурс не найден. Проверьте правильность owner и repo."
    elif status_code == 429:
        return "Превышен лимит запросов к GitHub API. Попробуйте позже."
    elif status_code >= 500:
        return f"Ошибка сервера GitHub API (код {status_code})."
    else:
        return f"Ошибка API: {response_text[:200]}"


def create_github_client(timeout: float = 20.0) -> httpx.AsyncClient:
    """
    Создает асинхронный HTTP-клиент для работы с GitHub API.
    
    Args:
        timeout: Таймаут запросов в секундах
        
    Returns:
        Настроенный AsyncClient для GitHub API
    """
    github_token = os.getenv("GITHUB_TOKEN")
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MCP-GitHub-Health-Monitor/1.0"
    }
    
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers=headers,
        timeout=timeout,
        follow_redirects=True
    )


async def retry_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    ctx: Optional[Context] = None,
    **kwargs
) -> httpx.Response:
    """
    Выполняет HTTP запрос с retry механизмом и rate limiting.
    
    Args:
        client: HTTP клиент
        method: HTTP метод (get, post, etc.)
        url: URL для запроса
        ctx: Контекст для логирования
        **kwargs: Дополнительные параметры для запроса
        
    Returns:
        Response от сервера
        
    Raises:
        httpx.HTTPStatusError: При ошибках после всех попыток
    """
    last_exception = None
    
    for attempt in range(MAX_RETRIES):
        try:
            # Применяем rate limiting
            async with GITHUB_RATE_LIMITER:
                # Выполняем запрос
                response = await client.request(method, url, **kwargs)
                
                # Проверяем, нужно ли делать retry
                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < MAX_RETRIES - 1:
                        # Вычисляем задержку с exponential backoff
                        delay = RETRY_DELAY_BASE * (2 ** attempt)
                        
                        if ctx:
                            await ctx.info(
                                f"⚠️ Получен статус {response.status_code}. "
                                f"Повторная попытка {attempt + 1}/{MAX_RETRIES} через {delay:.1f}с..."
                            )
                        
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Последняя попытка, поднимаем ошибку
                        response.raise_for_status()
                
                # Успешный ответ или не retryable ошибка
                response.raise_for_status()
                return response
                
        except httpx.HTTPStatusError as e:
            last_exception = e
            status_code = e.response.status_code if e.response else 0
            
            # Если это retryable ошибка и есть еще попытки
            if status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                
                if ctx:
                    await ctx.info(
                        f"⚠️ Ошибка {status_code}. "
                        f"Повторная попытка {attempt + 1}/{MAX_RETRIES} через {delay:.1f}с..."
                    )
                
                await asyncio.sleep(delay)
                continue
            else:
                # Не retryable ошибка или последняя попытка
                raise
        
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exception = e
            
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                
                if ctx:
                    await ctx.info(
                        f"⚠️ Сетевая ошибка. "
                        f"Повторная попытка {attempt + 1}/{MAX_RETRIES} через {delay:.1f}с..."
                    )
                
                await asyncio.sleep(delay)
                continue
            else:
                raise
    
    # Если дошли сюда, все попытки исчерпаны
    if last_exception:
        raise last_exception
    
    raise httpx.HTTPStatusError("All retry attempts failed", request=None, response=None)


async def retry_github_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    ctx: Optional[Context] = None,
    max_retries: int = MAX_RETRIES,
    **kwargs
) -> httpx.Response:
    """
    Выполняет запрос к GitHub API с retry механизмом и rate limiting.
    
    Args:
        client: HTTP клиент
        method: HTTP метод (GET, POST, etc.)
        url: URL для запроса
        ctx: Контекст для логирования
        max_retries: Максимальное количество попыток
        **kwargs: Дополнительные параметры для запроса
        
    Returns:
        Response от GitHub API
        
    Raises:
        httpx.HTTPStatusError: При ошибках после всех попыток
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            # Применяем rate limiting
            async with GITHUB_RATE_LIMITER:
                response = await client.request(method, url, **kwargs)
            
            # Проверяем заголовки rate limit
            if "X-RateLimit-Remaining" in response.headers:
                remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
                if remaining < 100 and ctx:
                    await ctx.info(f"⚠️ Осталось {remaining} запросов к GitHub API")
            
            # Если статус код требует retry
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt < max_retries - 1:
                    # Вычисляем задержку с exponential backoff
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    
                    if ctx:
                        await ctx.info(
                            f"⚠️ Получен статус {response.status_code}, "
                            f"повторная попытка {attempt + 1}/{max_retries} через {delay:.1f}с"
                        )
                    
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Последняя попытка, поднимаем ошибку
                    response.raise_for_status()
            
            # Успешный ответ или не retryable ошибка
            response.raise_for_status()
            return response
            
        except httpx.HTTPStatusError as e:
            last_exception = e
            if e.response.status_code in RETRYABLE_STATUS_CODES:
                if attempt < max_retries - 1:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    if ctx:
                        await ctx.info(
                            f"⚠️ HTTP ошибка {e.response.status_code}, "
                            f"повторная попытка {attempt + 1}/{max_retries} через {delay:.1f}с"
                        )
                    await asyncio.sleep(delay)
                    continue
            # Не retryable ошибка или последняя попытка
            raise
            
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                if ctx:
                    await ctx.info(
                        f"⚠️ Сетевая ошибка, повторная попытка {attempt + 1}/{max_retries} через {delay:.1f}с"
                    )
                await asyncio.sleep(delay)
                continue
            raise
    
    # Если все попытки исчерпаны
    if last_exception:
        raise last_exception
    raise httpx.HTTPStatusError("All retries exhausted", request=None, response=None)


async def handle_github_error(
    error: Exception,
    ctx: Optional[Context] = None,
    operation: str = "GitHub API operation"
) -> None:
    """
    Обрабатывает ошибки GitHub API и преобразует их в McpError.
    
    Args:
        error: Исключение, которое нужно обработать
        ctx: Контекст для логирования (опционально)
        operation: Описание операции для сообщения об ошибке
        
    Raises:
        McpError: Преобразованная ошибка в формате MCP
    """
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code if error.response else 0
        response_text = error.response.text if error.response else ""
        
        error_message = format_api_error(response_text, status_code)
        
        if ctx:
            await ctx.error(f"❌ HTTP ошибка при {operation}: {error_message}")
        
        # Определяем код ошибки MCP на основе HTTP статуса
        if status_code == 400:
            error_code = -32602  # Invalid params
        elif status_code == 401:
            error_code = -32602  # Invalid params (неверный токен)
        elif status_code == 403:
            error_code = -32602  # Invalid params (нет доступа)
        elif status_code == 404:
            error_code = -32602  # Invalid params (ресурс не найден)
        elif status_code == 429:
            error_code = -32603  # Internal error (лимит запросов)
        else:
            error_code = -32603  # Internal error
        
        raise McpError(
            ErrorData(
                code=error_code,
                message=f"Не удалось выполнить {operation}.\n\n{error_message}"
            )
        )
    elif isinstance(error, httpx.TimeoutException):
        error_message = f"Таймаут при выполнении {operation}. GitHub API не ответил вовремя."
        if ctx:
            await ctx.error(f"⏱️ {error_message}")
        raise McpError(
            ErrorData(
                code=-32603,
                message=error_message
            )
        )
    elif isinstance(error, httpx.NetworkError):
        error_message = f"Сетевая ошибка при выполнении {operation}. Проверьте подключение к интернету."
        if ctx:
            await ctx.error(f"🌐 {error_message}")
        raise McpError(
            ErrorData(
                code=-32603,
                message=error_message
            )
        )
    else:
        # Общая ошибка
        error_message = f"Неожиданная ошибка при выполнении {operation}: {str(error)}"
        if ctx:
            await ctx.error(f"💥 {error_message}")
        raise McpError(
            ErrorData(
                code=-32603,
                message=error_message
            )
        )


def parse_github_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """
    Парсит строку даты из GitHub API в объект datetime.
    
    Args:
        date_str: Строка даты в формате ISO 8601
        
    Returns:
        Объект datetime или None если строка пустая
    """
    if not date_str:
        return None
    
    try:
        # GitHub API возвращает даты в формате ISO 8601 с Z в конце
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt
    except (ValueError, AttributeError):
        return None


def calculate_days_ago(date: Optional[datetime]) -> Optional[int]:
    """
    Вычисляет количество дней с указанной даты до текущего момента.
    
    Args:
        date: Дата для вычисления
        
    Returns:
        Количество дней или None если дата не указана
    """
    if not date:
        return None
    
    now = datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    
    delta = now - date
    return delta.days


def format_repository_health_text(metrics: Dict) -> str:
    """
    Форматирует метрики здоровья репозитория в человекочитаемый текст.
    
    Args:
        metrics: Словарь с метриками репозитория
        
    Returns:
        Отформатированный текст
    """
    lines = [
        f"📊 **Метрики здоровья репозитория {metrics.get('owner', '')}/{metrics.get('repo', '')}**",
        "",
        f"🔴 Открытые issues: {metrics.get('open_issues_count', 0)}",
        f"🟡 Открытые PR: {metrics.get('open_prs_count', 0)}",
        f"⭐ Звезды: {metrics.get('stars_count', 0)}",
        f"🍴 Форки: {metrics.get('forks_count', 0)}",
        f"👀 Наблюдатели: {metrics.get('watchers_count', 0)}",
    ]
    
    if metrics.get('last_commit_age_days') is not None:
        age = metrics['last_commit_age_days']
        if age == 0:
            lines.append("✅ Последний коммит: сегодня")
        elif age == 1:
            lines.append("✅ Последний коммит: вчера")
        elif age < 7:
            lines.append(f"✅ Последний коммит: {age} дней назад")
        elif age < 30:
            lines.append(f"⚠️ Последний коммит: {age} дней назад")
        else:
            lines.append(f"🔴 Последний коммит: {age} дней назад (неактивен)")
    
    if metrics.get('language'):
        lines.append(f"💻 Язык: {metrics['language']}")
    
    if metrics.get('is_archived'):
        lines.append("📦 Репозиторий архивирован")
    
    if metrics.get('is_disabled'):
        lines.append("🚫 Репозиторий отключен")
    
    return "\n".join(lines)


def format_issues_summary_text(summary: Dict) -> str:
    """
    Форматирует сводку по issues в человекочитаемый текст.
    
    Args:
        summary: Словарь со сводкой по issues
        
    Returns:
        Отформатированный текст
    """
    lines = [
        f"📋 **Сводка по issues репозитория {summary.get('owner', '')}/{summary.get('repo', '')}**",
        "",
        f"📊 Всего issues: {summary.get('total_issues', 0)}",
        f"🟢 Открытые: {summary.get('open_issues', 0)}",
        f"🔴 Закрытые: {summary.get('closed_issues', 0)}",
    ]
    
    if summary.get('issues_by_label'):
        lines.append("")
        lines.append("🏷️ Issues по labels:")
        for label, count in summary['issues_by_label'].items():
            lines.append(f"  - {label}: {count}")
    
    if summary.get('recent_issues'):
        lines.append("")
        lines.append("📝 Последние issues:")
        for issue in summary['recent_issues'][:5]:  # Показываем только первые 5
            state_emoji = "🟢" if issue.get('state') == 'open' else "🔴"
            lines.append(
                f"  {state_emoji} #{issue.get('number', '')}: {issue.get('title', '')[:50]}"
            )
    
    return "\n".join(lines)


def format_comparison_text(comparison: Dict) -> str:
    """
    Форматирует сравнение репозиториев в человекочитаемый текст.
    
    Args:
        comparison: Словарь со сравнением репозиториев
        
    Returns:
        Отформатированный текст
    """
    lines = [
        "📊 **Сравнение репозиториев**",
        "",
    ]
    
    repos = comparison.get('repositories', [])
    metrics = comparison.get('metrics', {})
    summary = comparison.get('summary', {})
    
    # Заголовок с репозиториями
    repo_names = [f"{r.get('owner', '')}/{r.get('repo', '')}" for r in repos]
    lines.append(f"Сравниваемые репозитории: {', '.join(repo_names)}")
    lines.append("")
    
    # Метрики
    if 'open_issues' in metrics:
        lines.append("🔴 Открытые issues:")
        for repo_name, count in metrics['open_issues'].items():
            lines.append(f"  - {repo_name}: {count}")
        lines.append("")
    
    if 'open_prs' in metrics:
        lines.append("🟡 Открытые PR:")
        for repo_name, count in metrics['open_prs'].items():
            lines.append(f"  - {repo_name}: {count}")
        lines.append("")
    
    if 'stars' in metrics:
        lines.append("⭐ Звезды:")
        for repo_name, count in metrics['stars'].items():
            lines.append(f"  - {repo_name}: {count}")
        lines.append("")
    
    # Сводка
    if summary:
        lines.append("📈 Сводка:")
        if 'most_active' in summary:
            lines.append(f"  Самый активный: {summary['most_active']}")
        if 'most_popular' in summary:
            lines.append(f"  Самый популярный: {summary['most_popular']}")
    
    return "\n".join(lines)

