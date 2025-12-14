"""Инструмент для получения метрик здоровья репозитория GitHub."""

from typing import Dict, Any
from datetime import datetime

import httpx
from fastmcp import Context
from mcp.types import TextContent
from opentelemetry import trace
from pydantic import Field

from mcp_instance import mcp
from .utils import (
    ToolResult,
    _require_env_vars,
    create_github_client,
    handle_github_error,
    format_repository_health_text,
    parse_github_datetime,
    calculate_days_ago,
    retry_github_request
)
from .schemas import GetRepositoryHealthInput, RepositoryHealthMetrics
import time

# Импортируем метрики (используем абсолютный импорт из корня сервера)
try:
    from metrics import (
        TOOL_CALLS_TOTAL,
        TOOL_DURATION_SECONDS,
        ACTIVE_REQUESTS,
        ERRORS_TOTAL,
        GITHUB_API_CALLS_TOTAL,
        GITHUB_API_DURATION_SECONDS
    )
except ImportError:
    # Если метрики недоступны, создаем заглушки
    TOOL_CALLS_TOTAL = None
    TOOL_DURATION_SECONDS = None
    ACTIVE_REQUESTS = None
    ERRORS_TOTAL = None
    GITHUB_API_CALLS_TOTAL = None
    GITHUB_API_DURATION_SECONDS = None

tracer = trace.get_tracer(__name__)


@mcp.tool(
    name="get_repository_health",
    description="""📊 Получает метрики здоровья репозитория GitHub.

Этот инструмент анализирует состояние репозитория и предоставляет ключевые метрики:
- Количество открытых issues и pull requests
- Активность (дата последнего коммита)
- Популярность (звезды, форки, наблюдатели)
- Статус репозитория (архивирован, отключен)
- Основной язык программирования

Используйте этот инструмент для мониторинга здоровья репозиториев и выявления проблемных проектов.
"""
)
async def get_repository_health(
    owner: str = Field(
        ...,
        description="Владелец репозитория (username или organization name)",
        examples=["octocat", "microsoft", "facebook"]
    ),
    repo: str = Field(
        ...,
        description="Название репозитория",
        examples=["Hello-World", "vscode", "react"]
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📊 Получает метрики здоровья репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        ctx: Контекст для логирования и отслеживания прогресса
        
    Returns:
        ToolResult: Результат с метриками здоровья репозитория
        
    Raises:
        McpError: При ошибках выполнения
    """
    # Метрики: начало выполнения
    if TOOL_CALLS_TOTAL:
        TOOL_CALLS_TOTAL.labels(tool_name="get_repository_health", status="started").inc()
    if ACTIVE_REQUESTS:
        ACTIVE_REQUESTS.labels(tool_name="get_repository_health").inc()
    start_time = time.time()
    
    with tracer.start_as_current_span("get_repository_health") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        
        await ctx.info("🚀 Начинаем получение метрик здоровья репозитория")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            # Валидация переменных окружения
            env = _require_env_vars(["GITHUB_TOKEN"])
            
            # Этап 1: Подготовка (0-20%)
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            # Этап 2: Получение данных репозитория (20-60%)
            await ctx.info("📡 Отправляем запрос к GitHub API")
            await ctx.report_progress(progress=40, total=100)
            
            async with create_github_client() as client:
                # Получаем основную информацию о репозитории (с retry)
                api_start = time.time()
                repo_response = await retry_github_request(
                    client, "GET", f"/repos/{owner}/{repo}", ctx=ctx
                )
                api_duration = time.time() - api_start
                if GITHUB_API_CALLS_TOTAL:
                    GITHUB_API_CALLS_TOTAL.labels(endpoint="/repos/{owner}/{repo}", status_code=repo_response.status_code).inc()
                if GITHUB_API_DURATION_SECONDS:
                    GITHUB_API_DURATION_SECONDS.labels(endpoint="/repos/{owner}/{repo}").observe(api_duration)
                repo_data = repo_response.json()
                
                await ctx.report_progress(progress=50, total=100)
                
                # Получаем количество открытых issues (без PR)
                issues_response = await client.get(
                    f"/repos/{owner}/{repo}/issues",
                    params={"state": "open", "per_page": 1}
                )
                issues_response.raise_for_status()
                # GitHub API возвращает заголовок Link с общим количеством
                open_issues_count = repo_data.get("open_issues_count", 0)
                
                await ctx.report_progress(progress=60, total=100)
                
                # Получаем количество открытых pull requests через search API (с retry)
                try:
                    search_pr_response = await retry_github_request(
                        client,
                        "GET",
                        f"/search/issues",
                        ctx=ctx,
                        params={
                            "q": f"repo:{owner}/{repo} type:pr state:open",
                            "per_page": 1
                        }
                    )
                    search_pr_data = search_pr_response.json()
                    open_prs_count = search_pr_data.get("total_count", 0)
                except Exception:
                    open_prs_count = 0
                
                await ctx.report_progress(progress=70, total=100)
                
                # Получаем последний коммит (с retry)
                commits_response = await retry_github_request(
                    client,
                    "GET",
                    f"/repos/{owner}/{repo}/commits",
                    ctx=ctx,
                    params={"per_page": 1}
                )
                commits_data = commits_response.json()
                
                last_commit_date = None
                if commits_data:
                    commit = commits_data[0]
                    commit_info = commit.get("commit", {})
                    author_info = commit_info.get("author", {})
                    last_commit_date_str = author_info.get("date")
                    last_commit_date = parse_github_datetime(last_commit_date_str)
                
                await ctx.report_progress(progress=80, total=100)
            
            # Этап 3: Обработка результатов (80-95%)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Вычисляем возраст последнего коммита
            last_commit_age_days = calculate_days_ago(last_commit_date)
            
            # Формируем структурированные данные
            metrics_dict = {
                "owner": owner,
                "repo": repo,
                "open_issues_count": max(0, open_issues_count - open_prs_count),  # Issues без PR
                "open_prs_count": open_prs_count,
                "last_commit_date": last_commit_date.isoformat() if last_commit_date else None,
                "last_commit_age_days": last_commit_age_days,
                "stars_count": repo_data.get("stargazers_count", 0),
                "forks_count": repo_data.get("forks_count", 0),
                "watchers_count": repo_data.get("watchers_count", 0),
                "is_archived": repo_data.get("archived", False),
                "is_disabled": repo_data.get("disabled", False),
                "default_branch": repo_data.get("default_branch", "main"),
                "language": repo_data.get("language"),
                "created_at": parse_github_datetime(repo_data.get("created_at")).isoformat() if repo_data.get("created_at") else None,
                "updated_at": parse_github_datetime(repo_data.get("updated_at")).isoformat() if repo_data.get("updated_at") else None,
                "pushed_at": parse_github_datetime(repo_data.get("pushed_at")).isoformat() if repo_data.get("pushed_at") else None,
            }
            
            # Создаем Pydantic модель для структурированного ответа
            metrics_model = RepositoryHealthMetrics(
                owner=owner,
                repo=repo,
                open_issues_count=max(0, open_issues_count - open_prs_count),
                open_prs_count=open_prs_count,
                last_commit_date=last_commit_date,
                last_commit_age_days=last_commit_age_days,
                stars_count=repo_data.get("stargazers_count", 0),
                forks_count=repo_data.get("forks_count", 0),
                watchers_count=repo_data.get("watchers_count", 0),
                is_archived=repo_data.get("archived", False),
                is_disabled=repo_data.get("disabled", False),
                default_branch=repo_data.get("default_branch", "main"),
                language=repo_data.get("language"),
                created_at=parse_github_datetime(repo_data.get("created_at")) or datetime.now(),
                updated_at=parse_github_datetime(repo_data.get("updated_at")) or datetime.now(),
                pushed_at=parse_github_datetime(repo_data.get("pushed_at"))
            )
            
            await ctx.report_progress(progress=95, total=100)
            
            # Форматируем человекочитаемый текст
            formatted_text = format_repository_health_text(metrics_dict)
            
            await ctx.report_progress(progress=100, total=100)
            await ctx.info("✅ Метрики здоровья репозитория успешно получены")
            
            # Метрики: успешное завершение
            duration = time.time() - start_time
            if TOOL_DURATION_SECONDS:
                TOOL_DURATION_SECONDS.labels(tool_name="get_repository_health").observe(duration)
            if TOOL_CALLS_TOTAL:
                TOOL_CALLS_TOTAL.labels(tool_name="get_repository_health", status="success").inc()
            if ACTIVE_REQUESTS:
                ACTIVE_REQUESTS.labels(tool_name="get_repository_health").dec()
            
            span.set_attribute("success", True)
            span.set_attribute("open_issues", metrics_dict["open_issues_count"])
            span.set_attribute("open_prs", metrics_dict["open_prs_count"])
            span.set_attribute("stars", metrics_dict["stars_count"])
            
            return ToolResult(
                content=[TextContent(type="text", text=formatted_text)],
                structured_content=metrics_model.model_dump(),
                meta={
                    "owner": owner,
                    "repo": repo,
                    "operation": "get_repository_health"
                }
            )
            
        except httpx.HTTPStatusError as e:
            # Метрики: ошибка
            duration = time.time() - start_time
            if TOOL_DURATION_SECONDS:
                TOOL_DURATION_SECONDS.labels(tool_name="get_repository_health").observe(duration)
            if TOOL_CALLS_TOTAL:
                TOOL_CALLS_TOTAL.labels(tool_name="get_repository_health", status="error").inc()
            if ERRORS_TOTAL:
                ERRORS_TOTAL.labels(tool_name="get_repository_health", error_type="HTTPStatusError").inc()
            if ACTIVE_REQUESTS:
                ACTIVE_REQUESTS.labels(tool_name="get_repository_health").dec()
            await handle_github_error(e, ctx, f"получении метрик здоровья репозитория {owner}/{repo}")
        except httpx.TimeoutException as e:
            # Метрики: ошибка
            duration = time.time() - start_time
            if TOOL_DURATION_SECONDS:
                TOOL_DURATION_SECONDS.labels(tool_name="get_repository_health").observe(duration)
            if TOOL_CALLS_TOTAL:
                TOOL_CALLS_TOTAL.labels(tool_name="get_repository_health", status="error").inc()
            if ERRORS_TOTAL:
                ERRORS_TOTAL.labels(tool_name="get_repository_health", error_type="TimeoutException").inc()
            if ACTIVE_REQUESTS:
                ACTIVE_REQUESTS.labels(tool_name="get_repository_health").dec()
            await handle_github_error(e, ctx, f"получении метрик здоровья репозитория {owner}/{repo}")
        except httpx.NetworkError as e:
            # Метрики: ошибка
            duration = time.time() - start_time
            if TOOL_DURATION_SECONDS:
                TOOL_DURATION_SECONDS.labels(tool_name="get_repository_health").observe(duration)
            if TOOL_CALLS_TOTAL:
                TOOL_CALLS_TOTAL.labels(tool_name="get_repository_health", status="error").inc()
            if ERRORS_TOTAL:
                ERRORS_TOTAL.labels(tool_name="get_repository_health", error_type="NetworkError").inc()
            if ACTIVE_REQUESTS:
                ACTIVE_REQUESTS.labels(tool_name="get_repository_health").dec()
            await handle_github_error(e, ctx, f"получении метрик здоровья репозитория {owner}/{repo}")
        except Exception as e:
            # Метрики: ошибка
            duration = time.time() - start_time
            if TOOL_DURATION_SECONDS:
                TOOL_DURATION_SECONDS.labels(tool_name="get_repository_health").observe(duration)
            if TOOL_CALLS_TOTAL:
                TOOL_CALLS_TOTAL.labels(tool_name="get_repository_health", status="error").inc()
            if ERRORS_TOTAL:
                ERRORS_TOTAL.labels(tool_name="get_repository_health", error_type="Exception").inc()
            if ACTIVE_REQUESTS:
                ACTIVE_REQUESTS.labels(tool_name="get_repository_health").dec()
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении метрик здоровья репозитория {owner}/{repo}")

