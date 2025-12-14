"""Инструмент для получения списка webhooks репозитория GitHub."""

from typing import Dict, Any, List

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
    name="get_repository_webhooks",
    description="""🔔 Получает список webhooks репозитория GitHub.

Этот инструмент анализирует webhooks репозитория:
- Список всех webhooks
- URL webhooks
- События, на которые настроены webhooks
- Статус webhooks (active/inactive)

Используйте этот инструмент для анализа интеграций репозитория.
"""
)
async def get_repository_webhooks(
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
    🔔 Получает список webhooks репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат со списком webhooks
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_repository_webhooks") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        
        await ctx.info("🚀 Начинаем получение списка webhooks")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем список webhooks
            webhooks_url = f"/repos/{owner}/{repo}/hooks"
            params = {"per_page": 30}
            
            try:
                response = await retry_github_request(
                    client, "GET", webhooks_url, ctx=ctx, params=params
                )
                webhooks = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    # Нет прав на просмотр webhooks
                    webhooks = []
                else:
                    raise
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Форматируем результат
            result_text = f"🔔 Webhooks для {owner}/{repo}\n\n"
            result_text += f"📊 Статистика:\n"
            result_text += f"  - Всего webhooks: {len(webhooks)}\n"
            
            if webhooks:
                result_text += f"\n📋 Список webhooks:\n"
                for i, webhook in enumerate(webhooks[:10], 1):
                    webhook_id = webhook.get("id", "N/A")
                    url = webhook.get("config", {}).get("url", "N/A")
                    active = webhook.get("active", False)
                    events = webhook.get("events", [])
                    status = "✅ Активен" if active else "❌ Неактивен"
                    result_text += f"  {i}. Webhook #{webhook_id} - {status}\n"
                    result_text += f"     URL: {url[:50]}...\n"
                    if events:
                        result_text += f"     События: {', '.join(events[:5])}\n"
            else:
                result_text += f"\n⚠️ Webhooks не найдены или нет прав на просмотр\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Список webhooks успешно получен")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("webhooks_count", len(webhooks))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "total_webhooks": len(webhooks),
                    "webhooks": [
                        {
                            "id": w.get("id"),
                            "url": w.get("config", {}).get("url"),
                            "active": w.get("active", False),
                            "events": w.get("events", [])
                        }
                        for w in webhooks[:10]
                    ]
                },
                meta={"owner": owner, "repo": repo, "operation": "get_repository_webhooks"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении списка webhooks {owner}/{repo}")

