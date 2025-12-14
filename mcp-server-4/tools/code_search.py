"""Инструмент для поиска кода в репозитории GitHub."""

from typing import Dict, Any, List, Optional

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
    retry_github_request
)
import time

tracer = trace.get_tracer(__name__)


@mcp.tool(
    name="search_code_in_repository",
    description="""🔍 Ищет код в репозитории GitHub по запросу.

Этот инструмент выполняет поиск кода в репозитории:
- Поиск по тексту запроса
- Фильтрация по языку программирования
- Поиск в конкретных файлах или директориях
- Возвращает контекст найденного кода

Используйте этот инструмент для быстрого поиска функций, классов или фрагментов кода в репозитории.
"""
)
async def search_code_in_repository(
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
    query: str = Field(
        ...,
        description="Поисковый запрос (текст для поиска в коде)",
        examples=["function calculate", "class User", "import requests"]
    ),
    language: Optional[str] = Field(
        default=None,
        description="Язык программирования для фильтрации (опционально)",
        examples=["Python", "JavaScript", "TypeScript"]
    ),
    path: Optional[str] = Field(
        default=None,
        description="Путь к файлу или директории для ограничения поиска (опционально)",
        examples=["src/", "tests/", "main.py"]
    ),
    ctx: Context = None
) -> ToolResult:
    """
    🔍 Ищет код в репозитории GitHub по запросу.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        query: Поисковый запрос
        language: Язык программирования для фильтрации
        path: Путь для ограничения поиска
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат поиска кода
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("search_code_in_repository") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("query", query)
        span.set_attribute("language", language or "all")
        
        await ctx.info("🚀 Начинаем поиск кода в репозитории")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            # Формируем поисковый запрос
            search_query = f"{query} repo:{owner}/{repo}"
            if language:
                search_query += f" language:{language}"
            if path:
                search_query += f" path:{path}"
            
            await ctx.info("📡 Отправляем запрос к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Выполняем поиск через GitHub Code Search API
            search_url = "/search/code"
            params = {
                "q": search_query,
                "per_page": 10  # Ограничиваем результаты
            }
            
            response = await retry_github_request(
                client, "GET", search_url, ctx=ctx, params=params
            )
            search_results = response.json()
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            items = search_results.get("items", [])
            total_count = search_results.get("total_count", 0)
            
            # Форматируем результат
            result_text = f"🔍 Результаты поиска кода в {owner}/{repo}\n\n"
            result_text += f"📊 Найдено результатов: {total_count}\n"
            result_text += f"📝 Показано: {len(items)}\n\n"
            
            if items:
                result_text += f"📄 Найденные файлы:\n"
                for i, item in enumerate(items, 1):
                    file_path = item.get("path", "Unknown")
                    file_name = file_path.split("/")[-1]
                    html_url = item.get("html_url", "")
                    result_text += f"  {i}. {file_name} ({file_path})\n"
                    result_text += f"     🔗 {html_url}\n"
            else:
                result_text += "❌ Результаты не найдены. Попробуйте изменить запрос.\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Поиск кода успешно выполнен")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("total_count", total_count)
            span.set_attribute("results_count", len(items))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "query": query,
                    "total_count": total_count,
                    "results_count": len(items),
                    "results": [
                        {
                            "path": item.get("path"),
                            "name": item.get("name"),
                            "html_url": item.get("html_url"),
                            "repository": item.get("repository", {}).get("full_name")
                        }
                        for item in items
                    ]
                },
                meta={"owner": owner, "repo": repo, "operation": "search_code_in_repository", "query": query}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"поиске кода в {owner}/{repo}")

