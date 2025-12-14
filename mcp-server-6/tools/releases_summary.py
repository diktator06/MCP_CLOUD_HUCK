"""Инструмент для получения сводки по релизам репозитория GitHub."""

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
    name="get_releases_summary",
    description="""📦 Получает сводку по релизам репозитория GitHub.

Этот инструмент анализирует релизы репозитория:
- Список всех релизов
- Последний релиз
- Статистика по релизам
- Информация о версиях
- Pre-release и draft релизы

Используйте этот инструмент для анализа релизов и версий проекта.
"""
)
async def get_releases_summary(
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
        default=10,
        description="Количество последних релизов для отображения",
        ge=1,
        le=50
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📦 Получает сводку по релизам репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        limit: Количество релизов для отображения
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат со сводкой по релизам
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_releases_summary") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("limit", limit)
        
        await ctx.info("🚀 Начинаем получение сводки по релизам")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем список релизов
            releases_url = f"/repos/{owner}/{repo}/releases"
            params = {"per_page": limit}
            
            response = await retry_github_request(
                client, "GET", releases_url, ctx=ctx, params=params
            )
            releases = response.json()
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Анализируем релизы
            total_releases = len(releases)
            latest_release = releases[0] if releases else None
            
            # Форматируем результат
            result_text = f"📦 Сводка по релизам для {owner}/{repo}\n\n"
            result_text += f"📊 Статистика:\n"
            result_text += f"  - Всего релизов показано: {total_releases}\n"
            
            if latest_release:
                result_text += f"  - Последний релиз: {latest_release.get('tag_name', 'N/A')}\n"
                result_text += f"  - Дата последнего релиза: {latest_release.get('published_at', 'N/A')}\n"
                result_text += f"  - Pre-release: {'Да' if latest_release.get('prerelease', False) else 'Нет'}\n"
                result_text += f"  - Draft: {'Да' if latest_release.get('draft', False) else 'Нет'}\n"
            
            if releases:
                result_text += f"\n📋 Последние релизы:\n"
                for i, release in enumerate(releases[:limit], 1):
                    tag = release.get("tag_name", "N/A")
                    name = release.get("name", tag)
                    published = release.get("published_at", "N/A")
                    prerelease = " (pre-release)" if release.get("prerelease", False) else ""
                    draft = " (draft)" if release.get("draft", False) else ""
                    result_text += f"  {i}. {name} ({tag}){prerelease}{draft}\n"
                    result_text += f"     📅 {published}\n"
            else:
                result_text += f"\n⚠️ Релизы не найдены\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Сводка по релизам успешно получена")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("total_releases", total_releases)
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "total_releases": total_releases,
                    "latest_release": {
                        "tag_name": latest_release.get("tag_name") if latest_release else None,
                        "published_at": latest_release.get("published_at") if latest_release else None,
                        "prerelease": latest_release.get("prerelease", False) if latest_release else False
                    } if latest_release else None,
                    "releases": [
                        {
                            "tag_name": r.get("tag_name"),
                            "name": r.get("name"),
                            "published_at": r.get("published_at"),
                            "prerelease": r.get("prerelease", False),
                            "draft": r.get("draft", False)
                        }
                        for r in releases[:limit]
                    ]
                },
                meta={"owner": owner, "repo": repo, "operation": "get_releases_summary"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении сводки по релизам {owner}/{repo}")

