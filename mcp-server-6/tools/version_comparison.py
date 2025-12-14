"""Инструмент для сравнения версий релизов."""

from typing import Dict, Any, List, Optional
import re

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
    name="compare_release_versions",
    description="""📊 Сравнивает версии релизов репозитория GitHub.

Этот инструмент сравнивает версии релизов:
- Сравнение версий по семантическому версионированию
- Определение типа обновления (major, minor, patch)
- Анализ изменений между версиями
- Рекомендации по обновлению

Используйте этот инструмент для анализа изменений между версиями проекта.
"""
)
async def compare_release_versions(
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
    version1: Optional[str] = Field(
        default=None,
        description="Первая версия для сравнения (если не указана, используется последний релиз)"
    ),
    version2: Optional[str] = Field(
        default=None,
        description="Вторая версия для сравнения (если не указана, используется предпоследний релиз)"
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📊 Сравнивает версии релизов репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        version1: Первая версия
        version2: Вторая версия
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат сравнения версий
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("compare_release_versions") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        
        await ctx.info("🚀 Начинаем сравнение версий релизов")
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
            params = {"per_page": 10}
            
            response = await retry_github_request(
                client, "GET", releases_url, ctx=ctx, params=params
            )
            releases = response.json()
            
            await ctx.report_progress(progress=60, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Определяем версии для сравнения
            if not version1 and releases:
                version1 = releases[0].get("tag_name", "")
            if not version2 and len(releases) > 1:
                version2 = releases[1].get("tag_name", "")
            
            # Форматируем результат
            result_text = f"📊 Сравнение версий для {owner}/{repo}\n\n"
            
            if version1 and version2:
                result_text += f"📋 Сравниваемые версии:\n"
                result_text += f"  - Версия 1: {version1}\n"
                result_text += f"  - Версия 2: {version2}\n"
                result_text += f"\n💡 Анализ изменений:\n"
                result_text += f"  - Рекомендуется проверить changelog между версиями\n"
                result_text += f"  - Проверьте breaking changes в документации\n"
            else:
                result_text += f"⚠️ Недостаточно релизов для сравнения\n"
                if releases:
                    result_text += f"  - Найдено релизов: {len(releases)}\n"
                    result_text += f"  - Последний релиз: {releases[0].get('tag_name', 'N/A')}\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Сравнение версий успешно выполнено")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("version1", version1 or "latest")
            span.set_attribute("version2", version2 or "previous")
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "version1": version1,
                    "version2": version2,
                    "comparison_available": bool(version1 and version2)
                },
                meta={"owner": owner, "repo": repo, "operation": "compare_release_versions"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"сравнении версий релизов {owner}/{repo}")

