"""Инструмент для анализа веток репозитория GitHub."""

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
    parse_github_datetime,
    calculate_days_ago
)
import time

tracer = trace.get_tracer(__name__)


@mcp.tool(
    name="get_branch_analysis",
    description="""🌿 Получает анализ веток репозитория GitHub.

Этот инструмент анализирует структуру веток репозитория:
- Список всех веток
- Активные ветки (с недавними коммитами)
- Защищенные ветки
- Мертвые ветки (без активности)
- Статистика по веткам

Используйте этот инструмент для анализа структуры репозитория и выявления неиспользуемых веток.
"""
)
async def get_branch_analysis(
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
    days_threshold: int = Field(
        default=90,
        description="Порог дней для определения активной ветки",
        ge=1,
        le=365
    ),
    ctx: Context = None
) -> ToolResult:
    """
    🌿 Получает анализ веток репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        days_threshold: Порог дней для определения активной ветки
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат с анализом веток
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_branch_analysis") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("days_threshold", days_threshold)
        
        await ctx.info("🚀 Начинаем анализ веток репозитория")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем список веток
            branches_url = f"/repos/{owner}/{repo}/branches"
            params = {"per_page": 100}
            
            all_branches = []
            page = 1
            
            while True:
                params["page"] = page
                response = await retry_github_request(
                    client, "GET", branches_url, ctx=ctx, params=params
                )
                branches = response.json()
                
                if not branches:
                    break
                
                all_branches.extend(branches)
                await ctx.report_progress(progress=30 + (page * 10), total=100)
                
                if len(branches) < 100:
                    break
                
                page += 1
                if page > 10:
                    break
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Получаем информацию о защищенных ветках
            protected_branches_url = f"/repos/{owner}/{repo}/branches"
            protected_branches = set()
            
            for branch in all_branches[:20]:  # Проверяем первые 20 веток
                branch_name = branch.get("name")
                if branch_name:
                    try:
                        branch_info = await retry_github_request(
                            client, "GET", f"{protected_branches_url}/{branch_name}", ctx=ctx
                        )
                        branch_data = branch_info.json()
                        if branch_data.get("protected", False):
                            protected_branches.add(branch_name)
                    except:
                        pass
            
            await ctx.report_progress(progress=85, total=100)
            
            # Анализируем ветки
            active_branches = []
            inactive_branches = []
            
            for branch in all_branches:
                branch_name = branch.get("name")
                commit_info = branch.get("commit", {})
                commit_date_str = commit_info.get("commit", {}).get("author", {}).get("date")
                
                is_protected = branch_name in protected_branches
                
                if commit_date_str:
                    commit_date = parse_github_datetime(commit_date_str)
                    days_ago = calculate_days_ago(commit_date)
                    
                    branch_data = {
                        "name": branch_name,
                        "protected": is_protected,
                        "last_commit_days_ago": days_ago,
                        "sha": commit_info.get("sha", "")[:7]
                    }
                    
                    if days_ago is not None and days_ago <= days_threshold:
                        active_branches.append(branch_data)
                    else:
                        inactive_branches.append(branch_data)
            
            # Сортируем по активности
            active_branches.sort(key=lambda x: x.get("last_commit_days_ago", 999))
            inactive_branches.sort(key=lambda x: x.get("last_commit_days_ago", 999), reverse=True)
            
            # Форматируем результат
            result_text = f"🌿 Анализ веток для {owner}/{repo}\n\n"
            result_text += f"📈 Общая статистика:\n"
            result_text += f"  - Всего веток: {len(all_branches)}\n"
            result_text += f"  - Активных веток (≤{days_threshold} дней): {len(active_branches)}\n"
            result_text += f"  - Неактивных веток (>{days_threshold} дней): {len(inactive_branches)}\n"
            result_text += f"  - Защищенных веток: {len(protected_branches)}\n\n"
            
            if active_branches:
                result_text += f"✅ Активные ветки (топ 10):\n"
                for branch in active_branches[:10]:
                    days = branch.get("last_commit_days_ago", "N/A")
                    protected = "🔒" if branch.get("protected") else ""
                    result_text += f"  - {branch['name']} {protected} (последний коммит: {days} дн. назад)\n"
            
            if inactive_branches:
                result_text += f"\n⚠️ Неактивные ветки (топ 5):\n"
                for branch in inactive_branches[:5]:
                    days = branch.get("last_commit_days_ago", "N/A")
                    result_text += f"  - {branch['name']} (последний коммит: {days} дн. назад)\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Анализ веток успешно выполнен")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("total_branches", len(all_branches))
            span.set_attribute("active_branches", len(active_branches))
            span.set_attribute("protected_branches", len(protected_branches))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "total_branches": len(all_branches),
                    "active_branches_count": len(active_branches),
                    "inactive_branches_count": len(inactive_branches),
                    "protected_branches_count": len(protected_branches),
                    "active_branches": active_branches[:10],
                    "inactive_branches": inactive_branches[:5],
                    "protected_branches": list(protected_branches)
                },
                meta={"owner": owner, "repo": repo, "operation": "get_branch_analysis", "days_threshold": days_threshold}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"анализе веток {owner}/{repo}")

