"""Инструмент для анализа зависимостей репозитория GitHub."""

from typing import Dict, Any, List, Optional

import httpx
from fastmcp import Context
from mcp.types import TextContent
from opentelemetry import trace
from pydantic import Field
import json

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
    name="analyze_dependencies",
    description="""📦 Анализирует зависимости репозитория GitHub.

Этот инструмент анализирует зависимости проекта:
- Python: requirements.txt, pyproject.toml, setup.py
- JavaScript/TypeScript: package.json
- Java: pom.xml, build.gradle
- Go: go.mod
- Rust: Cargo.toml

Используйте этот инструмент для анализа зависимостей проекта и выявления используемых библиотек.
"""
)
async def analyze_dependencies(
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
    📦 Анализирует зависимости репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат с анализом зависимостей
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("analyze_dependencies") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        
        await ctx.info("🚀 Начинаем анализ зависимостей репозитория")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запросы к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Список файлов зависимостей для поиска
            dependency_files = [
                "requirements.txt",
                "pyproject.toml",
                "setup.py",
                "package.json",
                "pom.xml",
                "build.gradle",
                "go.mod",
                "Cargo.toml",
                "composer.json",
                "Gemfile"
            ]
            
            found_files = []
            dependencies_data = {}
            
            # Ищем файлы зависимостей
            for dep_file in dependency_files:
                try:
                    file_url = f"/repos/{owner}/{repo}/contents/{dep_file}"
                    response = await retry_github_request(
                        client, "GET", file_url, ctx=ctx
                    )
                    file_data = response.json()
                    
                    if file_data.get("type") == "file":
                        found_files.append(dep_file)
                        
                        # Получаем содержимое файла
                        content = file_data.get("content", "")
                        encoding = file_data.get("encoding", "base64")
                        
                        if encoding == "base64":
                            import base64
                            try:
                                decoded_content = base64.b64decode(content).decode("utf-8")
                                dependencies_data[dep_file] = decoded_content
                            except:
                                pass
                        
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 404:
                        raise
                    continue
                except:
                    continue
                
                await ctx.report_progress(progress=30 + (len(found_files) * 5), total=100)
            
            await ctx.report_progress(progress=70, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Анализируем зависимости
            analysis_result = {}
            
            for file_name, content in dependencies_data.items():
                deps = []
                
                if file_name == "requirements.txt":
                    # Парсим requirements.txt
                    for line in content.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            dep = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
                            if dep:
                                deps.append(dep)
                
                elif file_name == "package.json":
                    # Парсим package.json
                    try:
                        pkg_data = json.loads(content)
                        deps = list(pkg_data.get("dependencies", {}).keys())
                        deps.extend(list(pkg_data.get("devDependencies", {}).keys()))
                    except:
                        pass
                
                elif file_name == "pyproject.toml":
                    # Парсим pyproject.toml (упрощенный)
                    for line in content.split("\n"):
                        if "=" in line and ("==" in line or ">=" in line or "~=" in line):
                            dep = line.split("=")[0].strip()
                            if dep and not dep.startswith("["):
                                deps.append(dep)
                
                if deps:
                    analysis_result[file_name] = {
                        "file": file_name,
                        "dependencies_count": len(deps),
                        "dependencies": deps[:50]  # Ограничиваем до 50
                    }
            
            # Форматируем результат
            result_text = f"📦 Анализ зависимостей для {owner}/{repo}\n\n"
            
            if found_files:
                result_text += f"📄 Найденные файлы зависимостей:\n"
                for file_name in found_files:
                    result_text += f"  - {file_name}\n"
                result_text += "\n"
                
                if analysis_result:
                    result_text += f"📊 Анализ зависимостей:\n"
                    for file_name, data in analysis_result.items():
                        result_text += f"\n  📄 {file_name}:\n"
                        result_text += f"    - Всего зависимостей: {data['dependencies_count']}\n"
                        result_text += f"    - Примеры (топ 10):\n"
                        for dep in data["dependencies"][:10]:
                            result_text += f"      • {dep}\n"
                else:
                    result_text += "⚠️ Не удалось проанализировать зависимости из найденных файлов.\n"
            else:
                result_text += "❌ Файлы зависимостей не найдены в корне репозитория.\n"
                result_text += "   Проверялись файлы: requirements.txt, package.json, pyproject.toml и др.\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Анализ зависимостей успешно выполнен")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("found_files_count", len(found_files))
            span.set_attribute("analyzed_files_count", len(analysis_result))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "found_files": found_files,
                    "analysis": analysis_result,
                    "total_dependencies": sum(
                        data["dependencies_count"] 
                        for data in analysis_result.values()
                    )
                },
                meta={"owner": owner, "repo": repo, "operation": "analyze_dependencies"}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"анализе зависимостей {owner}/{repo}")

