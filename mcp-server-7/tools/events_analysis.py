"""Инструмент для анализа событий репозитория GitHub."""

from typing import Dict, Any, List
from datetime import datetime, timedelta

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
    name="analyze_repository_events",
    description="""📅 Анализирует события репозитория GitHub.

Этот инструмент анализирует события репозитория:
- Список последних событий
- Типы событий (PushEvent, IssuesEvent, PullRequestEvent и т.д.)
- Активность по типам событий
- Временная статистика событий

Используйте этот инструмент для анализа активности репозитория через события.
"""
)
async def analyze_repository_events(
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
        default=30,
        description="Количество последних событий для анализа",
        ge=1,
        le=100
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📅 Анализирует события репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        limit: Количество событий для анализа
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат анализа событий
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("analyze_repository_events") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("limit", limit)
        
        await ctx.info("🚀 Начинаем анализ событий репозитория")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем события репозитория
            events_url = f"/repos/{owner}/{repo}/events"
            params = {"per_page": limit}
            
            try:
                response = await retry_github_request(
                    client, "GET", events_url, ctx=ctx, params=params
                )
                events = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    events = []
                else:
                    raise
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Анализируем события
            event_types = {}
            for event in events:
                event_type = event.get("type", "Unknown")
                event_types[event_type] = event_types.get(event_type, 0) + 1
            
            # Форматируем результат
            result_text = f"📅 Анализ событий для {owner}/{repo}\n\n"
            result_text += f"📊 Статистика:\n"
            result_text += f"  - Всего событий проанализировано: {len(events)}\n"
            result_text += f"  - Уникальных типов событий: {len(event_types)}\n"
            
            if event_types:
                result_text += f"\n📋 Распределение по типам событий:\n"
                for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / len(events) * 100) if events else 0
                    result_text += f"  - {event_type}: {count} ({percentage:.1f}%)\n"
            else:
                result_text += f"\n⚠️ События не найдены\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Анализ событий успешно выполнен")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("total_events", len(events))
            span.set_attribute("event_types_count", len(event_types))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "total_events": len(events),
                    "event_types": event_types,
                    "events_sample": [
                        {
                            "type": e.get("type"),
                            "created_at": e.get("created_at")
                        }
                        for e in events[:10]
                    ]
                },
                meta={"owner": owner, "repo": repo, "operation": "analyze_repository_events"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"анализе событий {owner}/{repo}")

