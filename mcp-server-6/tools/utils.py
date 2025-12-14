"""Общие утилиты для инструментов MCP сервера 3."""

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
RETRY_DELAY_BASE = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Rate Limiter для GitHub API
GITHUB_RATE_LIMITER = AsyncLimiter(max_rate=1.0, time_period=1.0)


def _require_env_vars(required_vars: List[str]) -> Dict[str, str]:
    """Проверяет наличие обязательных переменных окружения."""
    missing = []
    env = {}
    
    for var in required_vars:
        value = os.getenv(var)
        if value is None:
            missing.append(var)
        else:
            env[var] = value
    
    if missing:
        raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")
    
    return env


async def retry_github_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    ctx: Optional[Context] = None,
    max_retries: int = MAX_RETRIES,
    **kwargs
) -> httpx.Response:
    """Выполняет запрос к GitHub API с retry механизмом и rate limiting."""
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            async with GITHUB_RATE_LIMITER:
                response = await client.request(method, url, **kwargs)
            
            # Проверка rate limit
            remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
            if remaining < 10 and ctx:
                await ctx.info(f"⚠️ Осталось {remaining} запросов к GitHub API")
            
            # Retry для определенных статусов
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt < max_retries - 1:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    if ctx:
                        await ctx.info(f"⏳ Повторная попытка {attempt + 1}/{max_retries} через {delay:.1f}с")
                    await asyncio.sleep(delay)
                    continue
            
            response.raise_for_status()
            return response
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                if ctx:
                    await ctx.info(f"⏳ Повторная попытка {attempt + 1}/{max_retries} через {delay:.1f}с")
                await asyncio.sleep(delay)
                last_exception = e
                continue
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            if attempt < max_retries - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                if ctx:
                    await ctx.info(f"⏳ Повторная попытка {attempt + 1}/{max_retries} через {delay:.1f}с")
                await asyncio.sleep(delay)
                last_exception = e
                continue
            raise
    
    if last_exception:
        raise last_exception
    raise httpx.HTTPStatusError("All retries exhausted", request=None, response=None)


def create_github_client() -> httpx.AsyncClient:
    """Создает асинхронный HTTP клиент для GitHub API."""
    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MCP-Server-3"
    }
    
    if token:
        headers["Authorization"] = f"token {token}"
    
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers=headers,
        timeout=30.0
    )


async def handle_github_error(e: Exception, ctx: Optional[Context], operation: str) -> None:
    """Обрабатывает ошибки GitHub API и преобразует их в McpError."""
    error_message = str(e)
    
    if isinstance(e, httpx.HTTPStatusError):
        status_code = e.response.status_code if e.response else 0
        
        if status_code == 404:
            error_message = f"Репозиторий или ресурс не найден при {operation}"
        elif status_code == 403:
            error_message = f"Доступ запрещен при {operation}. Проверьте GITHUB_TOKEN и права доступа"
        elif status_code == 401:
            error_message = f"Ошибка аутентификации при {operation}. Проверьте GITHUB_TOKEN"
        elif status_code == 429:
            error_message = f"Превышен лимит запросов к GitHub API при {operation}. Подождите и попробуйте позже"
        else:
            error_message = f"HTTP ошибка {status_code} при {operation}"
        
        if ctx:
            await ctx.error(f"❌ HTTP ошибка при {operation}: {error_message}")
        
        raise McpError(
            ErrorData(
                code=-32603,
                message=error_message
            )
        )
    elif isinstance(e, httpx.TimeoutException):
        error_message = f"Таймаут при {operation}. GitHub API не ответил вовремя"
        if ctx:
            await ctx.error(f"⏱️ {error_message}")
        raise McpError(
            ErrorData(
                code=-32603,
                message=error_message
            )
        )
    elif isinstance(e, httpx.NetworkError):
        error_message = f"Сетевая ошибка при {operation}. Проверьте подключение к интернету"
        if ctx:
            await ctx.error(f"🌐 {error_message}")
        raise McpError(
            ErrorData(
                code=-32603,
                message=error_message
            )
        )
    else:
        if ctx:
            await ctx.error(f"💥 Неожиданная ошибка при {operation}: {error_message}")
        raise McpError(
            ErrorData(
                code=-32603,
                message=f"Неожиданная ошибка: {error_message}"
            )
        )


def parse_github_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Парсит дату из формата GitHub API."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def calculate_days_ago(dt: Optional[datetime]) -> Optional[int]:
    """Вычисляет количество дней назад от текущей даты."""
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return delta.days

