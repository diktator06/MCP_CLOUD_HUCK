"""Инструмент для получения временной линии активности репозитория."""

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
    name="get_activity_timeline",
    description="""📈 Получает временную линию активности репозитория GitHub.

Этот инструмент создает временную линию активности:
- События по датам
- График активности
- Пики активности
- Периоды затишья

Используйте этот инструмент для визуализации активности репозитория во времени.
"""
)
async def get_activity_timeline(
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
    days: int = Field(
        default=30,
        description="Количество дней для анализа",
        ge=1,
        le=365
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📈 Получает временную линию активности репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        days: Количество дней для анализа
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат с временной линией активности
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_activity_timeline") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("days", days)
        
        await ctx.info("🚀 Начинаем получение временной линии активности")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем события за период
            events_url = f"/repos/{owner}/{repo}/events"
            params = {"per_page": 100}
            
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
            
            # Фильтруем события по дате
            cutoff_date = datetime.now() - timedelta(days=days)
            recent_events = []
            
            for event in events:
                event_date_str = event.get("created_at")
                if event_date_str:
                    event_date = parse_github_datetime(event_date_str)
                    if event_date and event_date >= cutoff_date:
                        recent_events.append(event)
            
            # Группируем по дням
            events_by_day = {}
            for event in recent_events:
                event_date_str = event.get("created_at")
                if event_date_str:
                    event_date = parse_github_datetime(event_date_str)
                    if event_date:
                        day_key = event_date.strftime("%Y-%m-%d")
                        events_by_day[day_key] = events_by_day.get(day_key, 0) + 1
            
            # Форматируем результат
            result_text = f"📈 Временная линия активности для {owner}/{repo}\n\n"
            result_text += f"📊 Статистика за последние {days} дней:\n"
            result_text += f"  - Всего событий: {len(recent_events)}\n"
            result_text += f"  - Дней с активностью: {len(events_by_day)}\n"
            
            if events_by_day:
                result_text += f"\n📅 Активность по дням (топ 10):\n"
                sorted_days = sorted(events_by_day.items(), key=lambda x: x[1], reverse=True)[:10]
                for day, count in sorted_days:
                    result_text += f"  - {day}: {count} событий\n"
            else:
                result_text += f"\n⚠️ Активность не найдена за указанный период\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Временная линия активности успешно получена")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("recent_events_count", len(recent_events))
            span.set_attribute("active_days", len(events_by_day))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "period_days": days,
                    "total_events": len(recent_events),
                    "active_days": len(events_by_day),
                    "events_by_day": dict(sorted(events_by_day.items(), key=lambda x: x[1], reverse=True)[:10])
                },
                meta={"owner": owner, "repo": repo, "operation": "get_activity_timeline", "days": days}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении временной линии активности {owner}/{repo}")

