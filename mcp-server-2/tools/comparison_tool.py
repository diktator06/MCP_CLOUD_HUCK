"""Инструмент для сравнения нескольких репозиториев GitHub."""

import asyncio
import sys
import os
from typing import Dict, Any, List
from datetime import datetime, timezone

import httpx
from fastmcp import Context
from mcp.types import TextContent
from opentelemetry import trace
from pydantic import Field

# Добавляем путь к mcp-server-1 для импорта схем
# Вычисляем абсолютный путь к mcp-server-1
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
mcp_server_1_path = os.path.join(project_root, 'mcp-server-1')
if mcp_server_1_path not in sys.path:
    sys.path.insert(0, mcp_server_1_path)

from tools.schemas import CompareRepositoriesInput, RepositoryComparison

from mcp_instance import mcp
from .utils import (
    ToolResult,
    _require_env_vars,
    create_github_client,
    handle_github_error,
    parse_github_datetime,
    calculate_days_ago,
    retry_github_request
)

tracer = trace.get_tracer(__name__)


async def fetch_repository_data(
    client: httpx.AsyncClient,
    owner: str,
    repo: str
) -> Dict[str, Any]:
    """
    Получает данные о репозитории из GitHub API.
    
    Args:
        client: HTTP клиент для GitHub API
        owner: Владелец репозитория
        repo: Название репозитория
        
    Returns:
        Словарь с данными репозитория
        
    Raises:
        httpx.HTTPStatusError: При ошибках API
    """
    # Получаем основную информацию о репозитории (с retry)
    repo_response = await retry_github_request(
        client, "GET", f"/repos/{owner}/{repo}", ctx=None
    )
    repo_data = repo_response.json()
    
    # Получаем количество открытых PR через search API (с retry)
    open_prs_count = 0
    try:
        search_pr_response = await retry_github_request(
            client,
            "GET",
            f"/search/issues",
            ctx=None,
            params={
                "q": f"repo:{owner}/{repo} type:pr state:open",
                "per_page": 1
            }
        )
        search_pr_data = search_pr_response.json()
        open_prs_count = search_pr_data.get("total_count", 0)
    except Exception:
        open_prs_count = 0
    
    # Получаем последний коммит (с retry)
    last_commit_date = None
    try:
        commits_response = await retry_github_request(
            client,
            "GET",
            f"/repos/{owner}/{repo}/commits",
            ctx=None,
            params={"per_page": 1}
        )
        commits_data = commits_response.json()
        
        if commits_data:
            commit = commits_data[0]
            commit_info = commit.get("commit", {})
            author_info = commit_info.get("author", {})
            last_commit_date_str = author_info.get("date")
            last_commit_date = parse_github_datetime(last_commit_date_str)
    except Exception:
        last_commit_date = None
    
    # Вычисляем возраст последнего коммита
    last_commit_age_days = calculate_days_ago(last_commit_date)
    
    # Формируем данные
    return {
        "owner": owner,
        "repo": repo,
        "open_issues_count": max(0, repo_data.get("open_issues_count", 0) - open_prs_count),
        "open_prs_count": open_prs_count,
        "stars_count": repo_data.get("stargazers_count", 0),
        "forks_count": repo_data.get("forks_count", 0),
        "watchers_count": repo_data.get("watchers_count", 0),
        "last_commit_date": last_commit_date.isoformat() if last_commit_date else None,
        "last_commit_age_days": last_commit_age_days,
        "language": repo_data.get("language"),
        "is_archived": repo_data.get("archived", False),
        "is_disabled": repo_data.get("disabled", False),
        "pushed_at": parse_github_datetime(repo_data.get("pushed_at")).isoformat() if repo_data.get("pushed_at") else None,
    }


@mcp.tool(
    name="compare_repositories",
    description="""📊 Сравнивает метрики нескольких репозиториев GitHub параллельно.

Этот инструмент выполняет параллельные запросы к GitHub API для получения и сравнения метрик:
- Количество звезд, форков, наблюдателей
- Количество открытых issues и PR
- Активность (дата последнего коммита)
- Основной язык программирования
- Статус репозитория

Инструмент определяет наиболее активный и популярный репозиторий из списка.

Используйте этот инструмент для сравнения нескольких репозиториев и выявления лучших практик.
"""
)
async def compare_repositories(
    repositories: List[Dict[str, str]] = Field(
        ...,
        description="Список репозиториев для сравнения. Каждый элемент должен содержать 'owner' и 'repo'",
        min_items=2,
        max_items=5,
        examples=[
            [
                {"owner": "octocat", "repo": "Hello-World"},
                {"owner": "microsoft", "repo": "vscode"}
            ]
        ]
    ),
    metrics: List[str] = Field(
        default=None,
        description="Список метрик для сравнения. Если не указан, сравниваются все доступные метрики",
        examples=[["open_issues", "open_prs", "last_commit_age"]]
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📊 Сравнивает метрики нескольких репозиториев GitHub.
    
    Args:
        repositories: Список репозиториев для сравнения (каждый с 'owner' и 'repo')
        metrics: Список метрик для сравнения (опционально)
        ctx: Контекст для логирования и отслеживания прогресса
        
    Returns:
        ToolResult: Результат сравнения репозиториев
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("compare_repositories") as span:
        repo_names = [f"{r.get('owner', '')}/{r.get('repo', '')}" for r in repositories]
        span.set_attribute("repositories", ",".join(repo_names))
        span.set_attribute("count", len(repositories))
        
        await ctx.info("🚀 Начинаем сравнение репозиториев")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            # Валидация переменных окружения
            env = _require_env_vars(["GITHUB_TOKEN"])
            
            # Валидация входных данных
            if len(repositories) < 2:
                raise ValueError("Необходимо указать минимум 2 репозитория для сравнения")
            if len(repositories) > 5:
                raise ValueError("Максимум 5 репозиториев для сравнения")
            
            for repo in repositories:
                if "owner" not in repo or "repo" not in repo:
                    raise ValueError("Каждый репозиторий должен содержать 'owner' и 'repo'")
            
            # Этап 1: Подготовка (0-10%)
            await ctx.info(f"🔧 Подготавливаем параллельные запросы для {len(repositories)} репозиториев")
            await ctx.report_progress(progress=10, total=100)
            
            # Этап 2: Параллельное получение данных (10-80%)
            await ctx.info("📡 Отправляем параллельные запросы к GitHub API")
            await ctx.report_progress(progress=20, total=100)
            
            async with create_github_client() as client:
                # Создаем задачи для параллельного выполнения
                tasks = [
                    fetch_repository_data(client, repo["owner"], repo["repo"])
                    for repo in repositories
                ]
                
                # Выполняем все запросы параллельно
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                await ctx.report_progress(progress=70, total=100)
            
            # Проверяем результаты на ошибки
            repo_data_list = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    repo_name = f"{repositories[i]['owner']}/{repositories[i]['repo']}"
                    await ctx.error(f"❌ Ошибка при получении данных для {repo_name}: {result}")
                    # Продолжаем с другими репозиториями, но помечаем ошибку
                    repo_data_list.append({
                        "owner": repositories[i]["owner"],
                        "repo": repositories[i]["repo"],
                        "error": str(result)
                    })
                else:
                    repo_data_list.append(result)
            
            await ctx.report_progress(progress=80, total=100)
            
            # Этап 3: Анализ и сравнение (80-95%)
            await ctx.info("📄 Анализируем и сравниваем метрики")
            
            # Формируем метрики для сравнения
            comparison_metrics: Dict[str, Dict[str, Any]] = {}
            
            # Метрики для сравнения (если не указаны, используем все)
            metrics_to_compare = metrics or [
                "open_issues",
                "open_prs",
                "stars",
                "forks",
                "watchers",
                "last_commit_age"
            ]
            
            for metric in metrics_to_compare:
                comparison_metrics[metric] = {}
                for repo_data in repo_data_list:
                    if "error" in repo_data:
                        continue
                    
                    repo_key = f"{repo_data['owner']}/{repo_data['repo']}"
                    
                    if metric == "open_issues":
                        comparison_metrics[metric][repo_key] = repo_data.get("open_issues_count", 0)
                    elif metric == "open_prs":
                        comparison_metrics[metric][repo_key] = repo_data.get("open_prs_count", 0)
                    elif metric == "stars":
                        comparison_metrics[metric][repo_key] = repo_data.get("stars_count", 0)
                    elif metric == "forks":
                        comparison_metrics[metric][repo_key] = repo_data.get("forks_count", 0)
                    elif metric == "watchers":
                        comparison_metrics[metric][repo_key] = repo_data.get("watchers_count", 0)
                    elif metric == "last_commit_age":
                        comparison_metrics[metric][repo_key] = repo_data.get("last_commit_age_days") or 9999
            
            # Определяем лидеров по метрикам
            summary: Dict[str, Any] = {}
            
            # Наиболее активный (по последнему коммиту - минимальный возраст)
            if "last_commit_age" in comparison_metrics:
                min_age = min(comparison_metrics["last_commit_age"].values())
                most_active = [
                    repo for repo, age in comparison_metrics["last_commit_age"].items()
                    if age == min_age
                ][0] if comparison_metrics["last_commit_age"] else None
                summary["most_active"] = most_active
            
            # Наиболее популярный (по звездам)
            if "stars" in comparison_metrics:
                max_stars = max(comparison_metrics["stars"].values())
                most_popular = [
                    repo for repo, stars in comparison_metrics["stars"].items()
                    if stars == max_stars
                ][0] if comparison_metrics["stars"] else None
                summary["most_popular"] = most_popular
            
            # Наибольшее количество форков
            if "forks" in comparison_metrics:
                max_forks = max(comparison_metrics["forks"].values())
                most_forked = [
                    repo for repo, forks in comparison_metrics["forks"].items()
                    if forks == max_forks
                ][0] if comparison_metrics["forks"] else None
                summary["most_forked"] = most_forked
            
            await ctx.report_progress(progress=95, total=100)
            
            # Формируем структурированные данные
            comparison_date = datetime.now(timezone.utc)
            
            comparison_dict = {
                "repositories": repositories,
                "comparison_date": comparison_date.isoformat(),
                "metrics": comparison_metrics,
                "summary": summary
            }
            
            # Создаем Pydantic модель для структурированного ответа
            comparison_model = RepositoryComparison(
                repositories=repositories,
                comparison_date=comparison_date,
                metrics=comparison_metrics,
                summary=summary
            )
            
            # Форматируем человекочитаемый текст
            lines = [
                "📊 **Сравнение репозиториев**",
                "",
                f"Сравниваемые репозитории: {', '.join(repo_names)}",
                f"Дата сравнения: {comparison_date.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "",
            ]
            
            # Метрики
            if "open_issues" in comparison_metrics:
                lines.append("🔴 Открытые issues:")
                for repo_name, count in comparison_metrics["open_issues"].items():
                    lines.append(f"  - {repo_name}: {count}")
                lines.append("")
            
            if "open_prs" in comparison_metrics:
                lines.append("🟡 Открытые PR:")
                for repo_name, count in comparison_metrics["open_prs"].items():
                    lines.append(f"  - {repo_name}: {count}")
                lines.append("")
            
            if "stars" in comparison_metrics:
                lines.append("⭐ Звезды:")
                for repo_name, count in comparison_metrics["stars"].items():
                    lines.append(f"  - {repo_name}: {count}")
                lines.append("")
            
            if "forks" in comparison_metrics:
                lines.append("🍴 Форки:")
                for repo_name, count in comparison_metrics["forks"].items():
                    lines.append(f"  - {repo_name}: {count}")
                lines.append("")
            
            if "last_commit_age" in comparison_metrics:
                lines.append("📅 Возраст последнего коммита (дни):")
                for repo_name, age in comparison_metrics["last_commit_age"].items():
                    if age == 9999:
                        lines.append(f"  - {repo_name}: нет данных")
                    else:
                        lines.append(f"  - {repo_name}: {age} дней")
                lines.append("")
            
            # Сводка
            if summary:
                lines.append("📈 Сводка:")
                if "most_active" in summary:
                    lines.append(f"  🏃 Самый активный: {summary['most_active']}")
                if "most_popular" in summary:
                    lines.append(f"  ⭐ Самый популярный: {summary['most_popular']}")
                if "most_forked" in summary:
                    lines.append(f"  🍴 Наибольшее количество форков: {summary['most_forked']}")
            
            formatted_text = "\n".join(lines)
            
            await ctx.report_progress(progress=100, total=100)
            await ctx.info("✅ Сравнение репозиториев успешно завершено")
            
            span.set_attribute("success", True)
            span.set_attribute("repositories_count", len(repositories))
            
            return ToolResult(
                content=[TextContent(type="text", text=formatted_text)],
                structured_content=comparison_model.model_dump(),
                meta={
                    "repositories": repo_names,
                    "operation": "compare_repositories",
                    "metrics_compared": list(comparison_metrics.keys())
                }
            )
            
        except httpx.HTTPStatusError as e:
            await handle_github_error(e, ctx, "сравнении репозиториев")
        except httpx.TimeoutException as e:
            await handle_github_error(e, ctx, "сравнении репозиториев")
        except httpx.NetworkError as e:
            await handle_github_error(e, ctx, "сравнении репозиториев")
        except ValueError as e:
            span.set_attribute("error", str(e))
            await ctx.error(f"❌ Ошибка валидации: {e}")
            from mcp.shared.exceptions import McpError, ErrorData
            raise McpError(
                ErrorData(
                    code=-32602,
                    message=f"Ошибка валидации параметров: {e}"
                )
            )
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, "сравнении репозиториев")

