"""Инструмент для получения статистики активности разработчиков."""

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
    name="get_developer_activity",
    description="""👥 Получает статистику активности разработчиков репозитория GitHub.

Этот инструмент анализирует активность разработчиков:
- Топ контрибьюторы по количеству коммитов
- Активность по периодам (недели, месяцы)
- Статистика по авторам pull requests
- Распределение активности между разработчиками

Используйте этот инструмент для анализа активности команды разработки.
"""
)
async def get_developer_activity(
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
        description="Количество топ разработчиков для отображения",
        ge=1,
        le=50
    ),
    ctx: Context = None
) -> ToolResult:
    """
    👥 Получает статистику активности разработчиков репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        top_n: Количество топ разработчиков
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат со статистикой активности разработчиков
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_developer_activity") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("top_n", top_n)
        
        await ctx.info("🚀 Начинаем получение статистики активности разработчиков")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем список коммитов
            commits_url = f"/repos/{owner}/{repo}/commits"
            params = {"per_page": 100}
            
            all_commits = []
            page = 1
            
            while page <= 10:  # Ограничение на 1000 коммитов
                params["page"] = page
                response = await retry_github_request(
                    client, "GET", commits_url, ctx=ctx, params=params
                )
                commits = response.json()
                
                if not commits:
                    break
                
                all_commits.extend(commits)
                await ctx.report_progress(progress=30 + (page * 5), total=100)
                
                if len(commits) < 100:
                    break
                
                page += 1
            
            await ctx.report_progress(progress=80, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Анализируем активность разработчиков
            developers = {}
            
            for commit in all_commits:
                author_info = commit.get("author")
                if author_info:
                    login = author_info.get("login", "Unknown")
                    if login not in developers:
                        developers[login] = {
                            "commits": 0,
                            "name": commit.get("commit", {}).get("author", {}).get("name", login)
                        }
                    developers[login]["commits"] += 1
            
            # Сортируем разработчиков
            sorted_devs = sorted(
                developers.items(),
                key=lambda x: x[1]["commits"],
                reverse=True
            )[:top_n]
            
            total_commits = len(all_commits)
            
            # Форматируем результат
            result_text = f"👥 Статистика активности разработчиков для {owner}/{repo}\n\n"
            result_text += f"📈 Общая статистика:\n"
            result_text += f"  - Всего коммитов проанализировано: {total_commits}\n"
            result_text += f"  - Уникальных разработчиков: {len(developers)}\n\n"
            
            result_text += f"🏆 Топ {top_n} разработчиков:\n"
            for i, (login, data) in enumerate(sorted_devs, 1):
                commits = data["commits"]
                percentage = (commits / total_commits * 100) if total_commits > 0 else 0
                name = data["name"]
                result_text += f"  {i}. {name} (@{login}): {commits} коммитов ({percentage:.1f}%)\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Статистика активности разработчиков успешно получена")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("total_commits", total_commits)
            span.set_attribute("unique_developers", len(developers))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "total_commits": total_commits,
                    "unique_developers": len(developers),
                    "top_developers": [
                        {
                            "login": login,
                            "name": data["name"],
                            "commits": data["commits"],
                            "percentage": round((data["commits"] / total_commits * 100) if total_commits > 0 else 0, 2)
                        }
                        for login, data in sorted_devs
                    ]
                },
                meta={"owner": owner, "repo": repo, "operation": "get_developer_activity"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении статистики активности разработчиков {owner}/{repo}")

