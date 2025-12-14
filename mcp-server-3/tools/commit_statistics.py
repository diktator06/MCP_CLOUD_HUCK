"""Инструмент для получения статистики коммитов репозитория GitHub."""

from typing import Dict, Any
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
    parse_github_datetime,
    calculate_days_ago
)
import time

tracer = trace.get_tracer(__name__)


@mcp.tool(
    name="get_commit_statistics",
    description="""📊 Получает статистику коммитов репозитория GitHub.

Этот инструмент анализирует активность коммитов в репозитории:
- Общее количество коммитов
- Статистика по периодам (дни, недели, месяцы)
- Активность по дням недели
- Топ авторов коммитов
- График активности за период

Используйте этот инструмент для анализа активности разработки в репозитории.
"""
)
async def get_commit_statistics(
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
    since: str = Field(
        default="30 days ago",
        description="Начало периода для анализа (формат: 'YYYY-MM-DD' или 'N days ago')"
    ),
    until: str = Field(
        default="now",
        description="Конец периода для анализа (формат: 'YYYY-MM-DD' или 'now')"
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📊 Получает статистику коммитов репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        since: Начало периода для анализа
        until: Конец периода для анализа
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат со статистикой коммитов
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_commit_statistics") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("since", since)
        span.set_attribute("until", until)
        
        await ctx.info("🚀 Начинаем получение статистики коммитов")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            # Валидация переменных окружения
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            # Создаем клиент
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            # Парсим даты
            if since == "30 days ago":
                since_date = (datetime.now() - timedelta(days=30)).isoformat()
            else:
                since_date = since
            
            if until == "now":
                until_date = datetime.now().isoformat()
            else:
                until_date = until
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем список коммитов
            commits_url = f"/repos/{owner}/{repo}/commits"
            params = {
                "since": since_date,
                "until": until_date,
                "per_page": 100
            }
            
            all_commits = []
            page = 1
            
            while True:
                params["page"] = page
                response = await retry_github_request(
                    client, "GET", commits_url, ctx=ctx, params=params
                )
                commits = response.json()
                
                if not commits:
                    break
                
                all_commits.extend(commits)
                await ctx.report_progress(progress=30 + (page * 10), total=100)
                
                if len(commits) < 100:
                    break
                
                page += 1
                if page > 10:  # Ограничение на 1000 коммитов
                    break
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Анализируем коммиты
            total_commits = len(all_commits)
            
            # Статистика по авторам
            authors = {}
            for commit in all_commits:
                author = commit.get("commit", {}).get("author", {}).get("name", "Unknown")
                authors[author] = authors.get(author, 0) + 1
            
            # Сортируем авторов
            top_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)[:10]
            
            # Статистика по дням недели
            days_of_week = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}  # Пн-Вс
            for commit in all_commits:
                date_str = commit.get("commit", {}).get("author", {}).get("date")
                if date_str:
                    dt = parse_github_datetime(date_str)
                    if dt:
                        day_of_week = dt.weekday()
                        days_of_week[day_of_week] = days_of_week.get(day_of_week, 0) + 1
            
            day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            day_stats = {day_names[i]: days_of_week[i] for i in range(7)}
            
            # Форматируем результат
            result_text = f"📊 Статистика коммитов для {owner}/{repo}\n\n"
            result_text += f"📈 Общая статистика:\n"
            result_text += f"  - Всего коммитов: {total_commits}\n"
            result_text += f"  - Период: {since} - {until}\n"
            result_text += f"  - Уникальных авторов: {len(authors)}\n\n"
            
            result_text += f"👥 Топ авторов коммитов:\n"
            for i, (author, count) in enumerate(top_authors, 1):
                percentage = (count / total_commits * 100) if total_commits > 0 else 0
                result_text += f"  {i}. {author}: {count} коммитов ({percentage:.1f}%)\n"
            
            result_text += f"\n📅 Активность по дням недели:\n"
            for day, count in sorted(day_stats.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_commits * 100) if total_commits > 0 else 0
                result_text += f"  - {day}: {count} коммитов ({percentage:.1f}%)\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Статистика коммитов успешно получена")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("total_commits", total_commits)
            span.set_attribute("unique_authors", len(authors))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "total_commits": total_commits,
                    "period": {"since": since, "until": until},
                    "unique_authors": len(authors),
                    "top_authors": [{"name": name, "commits": count} for name, count in top_authors],
                    "activity_by_day": day_stats
                },
                meta={"owner": owner, "repo": repo, "operation": "get_commit_statistics"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении статистики коммитов {owner}/{repo}")

