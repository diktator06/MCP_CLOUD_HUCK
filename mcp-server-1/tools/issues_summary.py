"""Инструмент для получения сводки по issues репозитория GitHub."""

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
    format_issues_summary_text,
    parse_github_datetime,
    retry_github_request
)
from .schemas import (
    GetRepositoryIssuesSummaryInput,
    RepositoryIssuesSummary,
    IssueSummary
)

tracer = trace.get_tracer(__name__)


@mcp.tool(
    name="get_repository_issues_summary",
    description="""📋 Получает сводку по issues репозитория GitHub.

Этот инструмент анализирует issues репозитория и предоставляет:
- Общее количество issues (открытых и закрытых)
- Распределение issues по labels
- Список последних issues с деталями
- Статистику по статусам и приоритетам

Используйте этот инструмент для мониторинга проблем и задач в репозитории.
"""
)
async def get_repository_issues_summary(
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
    state: str = Field(
        default="open",
        description="Статус issues: 'open', 'closed', или 'all'",
        examples=["open", "closed", "all"]
    ),
    labels: List[str] = Field(
        default=None,
        description="Список labels для фильтрации issues",
        examples=[["bug", "enhancement"]]
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📋 Получает сводку по issues репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        state: Статус issues ('open', 'closed', 'all')
        labels: Список labels для фильтрации (опционально)
        ctx: Контекст для логирования и отслеживания прогресса
        
    Returns:
        ToolResult: Результат со сводкой по issues
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_repository_issues_summary") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("state", state)
        
        await ctx.info("🚀 Начинаем получение сводки по issues")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            # Валидация переменных окружения
            env = _require_env_vars(["GITHUB_TOKEN"])
            
            # Валидация параметра state
            if state not in ["open", "closed", "all"]:
                raise ValueError(f"Недопустимое значение state: {state}. Допустимые значения: 'open', 'closed', 'all'")
            
            # Этап 1: Подготовка (0-20%)
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            # Этап 2: Получение данных issues (20-70%)
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            async with create_github_client() as client:
                # Параметры запроса
                params = {
                    "state": state,
                    "per_page": 100,  # Максимум для одного запроса
                    "sort": "updated",
                    "direction": "desc"
                }
                
                if labels:
                    # GitHub API поддерживает фильтрацию по labels через параметр labels
                    params["labels"] = ",".join(labels)
                
                # Получаем issues (без PR)
                all_issues = []
                page = 1
                
                while True:
                    params["page"] = page
                    issues_response = await retry_github_request(
                        client,
                        "GET",
                        f"/repos/{owner}/{repo}/issues",
                        ctx=ctx,
                        params=params
                    )
                    issues_data = issues_response.json()
                    
                    # Фильтруем PR (у них есть поле pull_request)
                    issues_only = [issue for issue in issues_data if "pull_request" not in issue]
                    all_issues.extend(issues_only)
                    
                    # Проверяем, есть ли еще страницы
                    if len(issues_data) < 100:
                        break
                    
                    page += 1
                    if page > 10:  # Ограничение для безопасности
                        break
                    
                    await ctx.report_progress(progress=30 + (page * 3), total=100)
                
                await ctx.report_progress(progress=60, total=100)
                
                # Получаем общую статистику через search API
                open_issues_count = 0
                closed_issues_count = 0
                
                try:
                    # Открытые issues (с retry)
                    search_open_response = await retry_github_request(
                        client,
                        "GET",
                        f"/search/issues",
                        ctx=ctx,
                        params={
                            "q": f"repo:{owner}/{repo} type:issue state:open",
                            "per_page": 1
                        }
                    )
                    search_open_data = search_open_response.json()
                    open_issues_count = search_open_data.get("total_count", 0)
                    
                    # Закрытые issues (с retry)
                    search_closed_response = await retry_github_request(
                        client,
                        "GET",
                        f"/search/issues",
                        ctx=ctx,
                        params={
                            "q": f"repo:{owner}/{repo} type:issue state:closed",
                            "per_page": 1
                        }
                    )
                    search_closed_data = search_closed_response.json()
                    closed_issues_count = search_closed_data.get("total_count", 0)
                except Exception:
                    # Если search API недоступен, вычисляем из полученных данных
                    open_issues = [i for i in all_issues if i.get("state") == "open"]
                    closed_issues = [i for i in all_issues if i.get("state") == "closed"]
                    open_issues_count = len(open_issues)
                    closed_issues_count = len(closed_issues)
                
                await ctx.report_progress(progress=70, total=100)
            
            # Этап 3: Обработка результатов (70-95%)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Подсчет issues по labels
            issues_by_label: Dict[str, int] = {}
            for issue in all_issues:
                issue_labels = issue.get("labels", [])
                for label in issue_labels:
                    label_name = label.get("name", "")
                    if label_name:
                        issues_by_label[label_name] = issues_by_label.get(label_name, 0) + 1
            
            # Подсчет issues по приоритетам (если есть labels с приоритетами)
            issues_by_priority: Dict[str, int] = {}
            priority_labels = ["priority: critical", "priority: high", "priority: medium", "priority: low"]
            for issue in all_issues:
                issue_labels = [label.get("name", "").lower() for label in issue.get("labels", [])]
                for priority in priority_labels:
                    if priority in issue_labels:
                        priority_key = priority.split(":")[-1].strip()
                        issues_by_priority[priority_key] = issues_by_priority.get(priority_key, 0) + 1
                        break
            
            # Формируем список последних issues (максимум 10)
            recent_issues_list: List[IssueSummary] = []
            for issue in all_issues[:10]:
                issue_labels = [label.get("name", "") for label in issue.get("labels", [])]
                assignees = issue.get("assignees", [])
                
                issue_summary = IssueSummary(
                    number=issue.get("number", 0),
                    title=issue.get("title", ""),
                    state=issue.get("state", "open"),
                    labels=issue_labels,
                    created_at=parse_github_datetime(issue.get("created_at")) or datetime.now(),
                    updated_at=parse_github_datetime(issue.get("updated_at")) or datetime.now(),
                    comments_count=issue.get("comments", 0),
                    assignees_count=len(assignees)
                )
                recent_issues_list.append(issue_summary)
            
            await ctx.report_progress(progress=90, total=100)
            
            # Формируем структурированные данные
            summary_dict = {
                "owner": owner,
                "repo": repo,
                "total_issues": open_issues_count + closed_issues_count,
                "open_issues": open_issues_count,
                "closed_issues": closed_issues_count,
                "issues_by_label": issues_by_label,
                "issues_by_priority": issues_by_priority,
                "recent_issues": [issue.model_dump() for issue in recent_issues_list]
            }
            
            # Создаем Pydantic модель для структурированного ответа
            summary_model = RepositoryIssuesSummary(
                owner=owner,
                repo=repo,
                total_issues=open_issues_count + closed_issues_count,
                open_issues=open_issues_count,
                closed_issues=closed_issues_count,
                issues_by_label=issues_by_label,
                issues_by_priority=issues_by_priority,
                recent_issues=recent_issues_list
            )
            
            await ctx.report_progress(progress=95, total=100)
            
            # Форматируем человекочитаемый текст
            formatted_text = format_issues_summary_text(summary_dict)
            
            await ctx.report_progress(progress=100, total=100)
            await ctx.info("✅ Сводка по issues успешно получена")
            
            span.set_attribute("success", True)
            span.set_attribute("total_issues", summary_dict["total_issues"])
            span.set_attribute("open_issues", summary_dict["open_issues"])
            span.set_attribute("closed_issues", summary_dict["closed_issues"])
            
            return ToolResult(
                content=[TextContent(type="text", text=formatted_text)],
                structured_content=summary_model.model_dump(),
                meta={
                    "owner": owner,
                    "repo": repo,
                    "state": state,
                    "operation": "get_repository_issues_summary"
                }
            )
            
        except httpx.HTTPStatusError as e:
            await handle_github_error(e, ctx, f"получении сводки по issues репозитория {owner}/{repo}")
        except httpx.TimeoutException as e:
            await handle_github_error(e, ctx, f"получении сводки по issues репозитория {owner}/{repo}")
        except httpx.NetworkError as e:
            await handle_github_error(e, ctx, f"получении сводки по issues репозитория {owner}/{repo}")
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
            await handle_github_error(e, ctx, f"получении сводки по issues репозитория {owner}/{repo}")

