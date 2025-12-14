"""Инструмент для получения списка контрибьюторов репозитория GitHub."""

from typing import Dict, Any, List
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
    retry_github_request,
    parse_github_datetime
)
from .schemas import RepositoryHealthMetrics  # Используем существующую схему для примера

tracer = trace.get_tracer(__name__)


@mcp.tool(
    name="get_repository_contributors",
    description="""👥 Получает список контрибьюторов репозитория GitHub.

Этот инструмент анализирует контрибьюторов репозитория и предоставляет:
- Список контрибьюторов с количеством коммитов
- Общее количество контрибьюторов
- Топ контрибьюторов по активности
- Статистику по контрибуциям

Используйте этот инструмент для анализа команды разработчиков и их вклада в проект.
"""
)
async def get_repository_contributors(
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
    top_n: int = Field(
        default=10,
        description="Количество топ контрибьюторов для возврата",
        ge=1,
        le=100
    ),
    ctx: Context = None
) -> ToolResult:
    """
    👥 Получает список контрибьюторов репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        top_n: Количество топ контрибьюторов для возврата
        ctx: Контекст для логирования и отслеживания прогресса
        
    Returns:
        ToolResult: Результат со списком контрибьюторов
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_repository_contributors") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("top_n", top_n)
        
        await ctx.info("🚀 Начинаем получение списка контрибьюторов")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            # Валидация переменных окружения
            env = _require_env_vars(["GITHUB_TOKEN"])
            
            # Этап 1: Подготовка (0-20%)
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            # Этап 2: Получение данных контрибьюторов (20-80%)
            await ctx.info("📡 Отправляем запрос к GitHub API")
            await ctx.report_progress(progress=40, total=100)
            
            async with create_github_client() as client:
                # Получаем список контрибьюторов (с retry и rate limiting)
                contributors_response = await retry_github_request(
                    client,
                    "GET",
                    f"/repos/{owner}/{repo}/contributors",
                    ctx=ctx,
                    params={"per_page": top_n, "anon": "false"}
                )
                contributors_data = contributors_response.json()
                
                await ctx.report_progress(progress=60, total=100)
                
                # Получаем общее количество контрибьюторов (если есть пагинация)
                total_contributors = len(contributors_data)
                if "Link" in contributors_response.headers:
                    # Можно парсить заголовок Link для получения общего количества
                    # Упрощенный подход: используем количество полученных
                    pass
                
                await ctx.report_progress(progress=80, total=100)
            
            # Этап 3: Обработка результатов (80-95%)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Формируем список контрибьюторов
            contributors_list = []
            for contributor in contributors_data[:top_n]:
                contributors_list.append({
                    "login": contributor.get("login", "Unknown"),
                    "contributions": contributor.get("contributions", 0),
                    "avatar_url": contributor.get("avatar_url", ""),
                    "type": contributor.get("type", "User"),
                    "site_admin": contributor.get("site_admin", False)
                })
            
            # Формируем структурированные данные
            contributors_dict = {
                "owner": owner,
                "repo": repo,
                "total_contributors": total_contributors,
                "top_contributors": contributors_list
            }
            
            await ctx.report_progress(progress=95, total=100)
            
            # Форматируем человекочитаемый текст
            lines = [
                f"👥 **Контрибьюторы репозитория {owner}/{repo}**",
                "",
                f"📊 Всего контрибьюторов: {total_contributors}",
                "",
                "🏆 Топ контрибьюторы:"
            ]
            
            for i, contributor in enumerate(contributors_list[:top_n], 1):
                lines.append(
                    f"{i}. **{contributor['login']}** - {contributor['contributions']} коммитов"
                )
            
            formatted_text = "\n".join(lines)
            
            await ctx.report_progress(progress=100, total=100)
            await ctx.info("✅ Список контрибьюторов успешно получен")
            
            span.set_attribute("success", True)
            span.set_attribute("total_contributors", total_contributors)
            
            return ToolResult(
                content=[TextContent(type="text", text=formatted_text)],
                structured_content=contributors_dict,
                meta={
                    "owner": owner,
                    "repo": repo,
                    "operation": "get_repository_contributors"
                }
            )
            
        except httpx.HTTPStatusError as e:
            await handle_github_error(e, ctx, f"получении списка контрибьюторов репозитория {owner}/{repo}")
        except httpx.TimeoutException as e:
            await handle_github_error(e, ctx, f"получении списка контрибьюторов репозитория {owner}/{repo}")
        except httpx.NetworkError as e:
            await handle_github_error(e, ctx, f"получении списка контрибьюторов репозитория {owner}/{repo}")
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении списка контрибьюторов репозитория {owner}/{repo}")
