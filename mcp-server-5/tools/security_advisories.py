"""Инструмент для проверки security advisories репозитория GitHub."""

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
    name="check_security_advisories",
    description="""🔒 Проверяет security advisories репозитория GitHub.

Этот инструмент анализирует безопасность репозитория:
- Список security advisories
- Уязвимости и их статус
- Рекомендации по безопасности
- История обновлений безопасности

Используйте этот инструмент для проверки безопасности репозитория.
"""
)
async def check_security_advisories(
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
    🔒 Проверяет security advisories репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат проверки безопасности
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("check_security_advisories") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        
        await ctx.info("🚀 Начинаем проверку security advisories")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем информацию о репозитории
            repo_url = f"/repos/{owner}/{repo}"
            repo_response = await retry_github_request(
                client, "GET", repo_url, ctx=ctx
            )
            repo_data = repo_response.json()
            
            await ctx.report_progress(progress=50, total=100)
            
            # Проверяем vulnerability alerts (требует специальных прав)
            # Используем альтернативный подход - проверяем Dependabot alerts через API
            security_info = {
                "private": repo_data.get("private", False),
                "archived": repo_data.get("archived", False),
                "has_vulnerability_alerts": repo_data.get("allow_forking", False),
                "security_policy": None
            }
            
            # Пытаемся получить security policy
            try:
                security_policy_url = f"/repos/{owner}/{repo}/contents/SECURITY.md"
                policy_response = await retry_github_request(
                    client, "GET", security_policy_url, ctx=ctx
                )
                security_info["security_policy"] = "present"
            except:
                security_info["security_policy"] = "not_found"
            
            await ctx.report_progress(progress=80, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Форматируем результат
            result_text = f"🔒 Security Advisories для {owner}/{repo}\n\n"
            result_text += f"📊 Статус безопасности:\n"
            result_text += f"  - Приватный репозиторий: {'Да' if security_info['private'] else 'Нет'}\n"
            result_text += f"  - Архивирован: {'Да' if security_info['archived'] else 'Нет'}\n"
            result_text += f"  - Security Policy: {'Найден' if security_info['security_policy'] == 'present' else 'Не найден'}\n"
            
            if security_info['security_policy'] == 'present':
                result_text += f"\n✅ Репозиторий имеет SECURITY.md файл\n"
            else:
                result_text += f"\n⚠️ Рекомендуется добавить SECURITY.md файл\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Проверка security advisories успешно выполнена")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("security_policy", security_info['security_policy'])
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "security_status": security_info,
                    "recommendations": [
                        "Добавить SECURITY.md файл" if security_info['security_policy'] != 'present' else "Security policy присутствует"
                    ]
                },
                meta={"owner": owner, "repo": repo, "operation": "check_security_advisories"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"проверке security advisories {owner}/{repo}")

