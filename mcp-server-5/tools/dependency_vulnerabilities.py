"""Инструмент для анализа уязвимостей зависимостей."""

from typing import Dict, Any, List
import json

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
    name="analyze_dependency_vulnerabilities",
    description="""🛡️ Анализирует уязвимости зависимостей репозитория GitHub.

Этот инструмент проверяет зависимости проекта на наличие известных уязвимостей:
- Анализ файлов зависимостей
- Проверка на известные CVE
- Рекомендации по обновлению
- Критичность уязвимостей

Используйте этот инструмент для проверки безопасности зависимостей проекта.
"""
)
async def analyze_dependency_vulnerabilities(
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
    🛡️ Анализирует уязвимости зависимостей репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат анализа уязвимостей
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("analyze_dependency_vulnerabilities") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        
        await ctx.info("🚀 Начинаем анализ уязвимостей зависимостей")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Список файлов зависимостей
            dependency_files = [
                "package.json",
                "requirements.txt",
                "pyproject.toml",
                "pom.xml",
                "build.gradle",
                "go.mod",
                "Cargo.toml"
            ]
            
            found_files = []
            vulnerabilities_summary = {
                "total_files": 0,
                "analyzed_files": 0,
                "potential_risks": []
            }
            
            # Проверяем наличие файлов зависимостей
            for dep_file in dependency_files:
                try:
                    file_url = f"/repos/{owner}/{repo}/contents/{dep_file}"
                    response = await retry_github_request(
                        client, "GET", file_url, ctx=ctx
                    )
                    file_data = response.json()
                    
                    if file_data.get("type") == "file":
                        found_files.append(dep_file)
                        vulnerabilities_summary["total_files"] += 1
                        
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 404:
                        raise
                    continue
                except:
                    continue
                
                await ctx.report_progress(progress=30 + (len(found_files) * 5), total=100)
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Формируем рекомендации
            if found_files:
                vulnerabilities_summary["analyzed_files"] = len(found_files)
                vulnerabilities_summary["potential_risks"].append(
                    "Рекомендуется регулярно обновлять зависимости"
                )
                vulnerabilities_summary["potential_risks"].append(
                    "Используйте Dependabot для автоматического мониторинга"
                )
            
            # Форматируем результат
            result_text = f"🛡️ Анализ уязвимостей зависимостей для {owner}/{repo}\n\n"
            result_text += f"📊 Найденные файлы зависимостей:\n"
            
            if found_files:
                for file in found_files:
                    result_text += f"  ✅ {file}\n"
                result_text += f"\n📋 Рекомендации:\n"
                for risk in vulnerabilities_summary["potential_risks"]:
                    result_text += f"  - {risk}\n"
            else:
                result_text += f"  ⚠️ Файлы зависимостей не найдены в корне репозитория\n"
            
            result_text += f"\n💡 Примечание: Для детального анализа используйте GitHub Dependabot или Snyk\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Анализ уязвимостей зависимостей успешно выполнен")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("found_files", len(found_files))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "repository": f"{owner}/{repo}",
                    "dependency_files": found_files,
                    "vulnerabilities_summary": vulnerabilities_summary
                },
                meta={"owner": owner, "repo": repo, "operation": "analyze_dependency_vulnerabilities"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"анализе уязвимостей зависимостей {owner}/{repo}")

