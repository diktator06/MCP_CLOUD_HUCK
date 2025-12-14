"""Инструмент для проверки compliance репозитория GitHub."""

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
    name="check_repository_compliance",
    description="""✅ Проверяет compliance репозитория GitHub.

Этот инструмент проверяет соответствие репозитория стандартам:
- Наличие LICENSE файла
- Наличие README файла
- Наличие CONTRIBUTING файла
- Наличие CODE_OF_CONDUCT файла
- Наличие SECURITY.md файла
- Настройки репозитория

Используйте этот инструмент для проверки соответствия репозитория стандартам разработки.
"""
)
async def check_repository_compliance(
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
    ✅ Проверяет compliance репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат проверки compliance
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("check_repository_compliance") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        
        await ctx.info("🚀 Начинаем проверку compliance репозитория")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Список файлов для проверки
            compliance_files = [
                "LICENSE",
                "LICENSE.md",
                "LICENSE.txt",
                "README.md",
                "README.rst",
                "CONTRIBUTING.md",
                "CODE_OF_CONDUCT.md",
                "SECURITY.md"
            ]
            
            found_files = {}
            missing_files = []
            
            # Проверяем наличие файлов
            for file_name in compliance_files:
                try:
                    file_url = f"/repos/{owner}/{repo}/contents/{file_name}"
                    response = await retry_github_request(
                        client, "GET", file_url, ctx=ctx
                    )
                    file_data = response.json()
                    
                    if file_data.get("type") == "file":
                        base_name = file_name.split(".")[0]
                        if base_name not in found_files:
                            found_files[base_name] = file_name
                        
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        base_name = file_name.split(".")[0]
                        if base_name not in found_files and base_name not in missing_files:
                            missing_files.append(base_name)
                    else:
                        raise
                    continue
                except:
                    continue
                
                await ctx.report_progress(progress=30 + (len(found_files) * 8), total=100)
            
            # Получаем информацию о репозитории
            repo_url = f"/repos/{owner}/{repo}"
            repo_response = await retry_github_request(
                client, "GET", repo_url, ctx=ctx
            )
            repo_data = repo_response.json()
            
            await ctx.report_progress(progress=80, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Форматируем результат
            result_text = f"✅ Compliance проверка для {owner}/{repo}\n\n"
            result_text += f"📊 Статус файлов:\n"
            
            required_files = ["LICENSE", "README", "CONTRIBUTING", "CODE_OF_CONDUCT", "SECURITY"]
            compliance_score = 0
            
            for req_file in required_files:
                if req_file in found_files:
                    result_text += f"  ✅ {req_file}: Найден ({found_files[req_file]})\n"
                    compliance_score += 1
                else:
                    result_text += f"  ❌ {req_file}: Отсутствует\n"
            
            result_text += f"\n📈 Compliance Score: {compliance_score}/{len(required_files)} ({compliance_score * 100 // len(required_files)}%)\n"
            
            if compliance_score < len(required_files):
                result_text += f"\n⚠️ Рекомендации:\n"
                for missing in missing_files:
                    if missing in required_files:
                        result_text += f"  - Добавить {missing} файл\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Проверка compliance успешно выполнена")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("compliance_score", compliance_score)
            span.set_attribute("found_files_count", len(found_files))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "compliance_score": compliance_score,
                    "max_score": len(required_files),
                    "found_files": list(found_files.keys()),
                    "missing_files": missing_files,
                    "percentage": round(compliance_score * 100 / len(required_files), 2)
                },
                meta={"owner": owner, "repo": repo, "operation": "check_repository_compliance"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"проверке compliance {owner}/{repo}")

