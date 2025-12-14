"""Инструмент для анализа тегов репозитория GitHub."""

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
import time

tracer = trace.get_tracer(__name__)


@mcp.tool(
    name="analyze_repository_tags",
    description="""🏷️ Анализирует теги репозитория GitHub.

Этот инструмент анализирует теги репозитория:
- Список всех тегов
- Последний тег
- Статистика по тегам
- Паттерны версионирования
- Связь тегов с коммитами

Используйте этот инструмент для анализа версионирования проекта.
"""
)
async def analyze_repository_tags(
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
    limit: int = Field(
        default=20,
        description="Количество последних тегов для отображения",
        ge=1,
        le=100
    ),
    ctx: Context = None
) -> ToolResult:
    """
    🏷️ Анализирует теги репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        limit: Количество тегов для отображения
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат анализа тегов
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("analyze_repository_tags") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("limit", limit)
        
        await ctx.info("🚀 Начинаем анализ тегов репозитория")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем список тегов
            tags_url = f"/repos/{owner}/{repo}/tags"
            params = {"per_page": limit}
            
            response = await retry_github_request(
                client, "GET", tags_url, ctx=ctx, params=params
            )
            tags = response.json()
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Анализируем теги
            total_tags = len(tags)
            latest_tag = tags[0] if tags else None
            
            # Форматируем результат
            result_text = f"🏷️ Анализ тегов для {owner}/{repo}\n\n"
            result_text += f"📊 Статистика:\n"
            result_text += f"  - Всего тегов показано: {total_tags}\n"
            
            if latest_tag:
                result_text += f"  - Последний тег: {latest_tag.get('name', 'N/A')}\n"
                commit_sha = latest_tag.get("commit", {}).get("sha", "N/A")
                result_text += f"  - SHA коммита: {commit_sha[:7] if commit_sha != 'N/A' else 'N/A'}\n"
            
            if tags:
                result_text += f"\n📋 Последние теги:\n"
                for i, tag in enumerate(tags[:limit], 1):
                    tag_name = tag.get("name", "N/A")
                    commit_sha = tag.get("commit", {}).get("sha", "N/A")[:7]
                    result_text += f"  {i}. {tag_name} (commit: {commit_sha})\n"
            else:
                result_text += f"\n⚠️ Теги не найдены\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Анализ тегов успешно выполнен")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("total_tags", total_tags)
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "total_tags": total_tags,
                    "latest_tag": {
                        "name": latest_tag.get("name") if latest_tag else None,
                        "commit_sha": latest_tag.get("commit", {}).get("sha") if latest_tag else None
                    } if latest_tag else None,
                    "tags": [
                        {
                            "name": t.get("name"),
                            "commit_sha": t.get("commit", {}).get("sha")
                        }
                        for t in tags[:limit]
                    ]
                },
                meta={"owner": owner, "repo": repo, "operation": "analyze_repository_tags"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"анализе тегов {owner}/{repo}")

