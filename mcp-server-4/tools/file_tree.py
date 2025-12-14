"""Инструмент для получения структуры файлов репозитория GitHub."""

from typing import Dict, Any, List, Optional

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
    name="get_file_tree",
    description="""📁 Получает структуру файлов и директорий репозитория GitHub.

Этот инструмент анализирует структуру репозитория:
- Дерево файлов и директорий
- Размеры файлов
- Типы файлов
- Основные директории проекта

Используйте этот инструмент для анализа архитектуры репозитория и понимания структуры проекта.
"""
)
async def get_file_tree(
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
    path: str = Field(
        default="",
        description="Путь к директории для анализа (пустая строка = корень репозитория)",
        examples=["", "src/", "tests/", "docs/"]
    ),
    max_depth: int = Field(
        default=2,
        description="Максимальная глубина дерева для отображения",
        ge=1,
        le=5
    ),
    ctx: Context = None
) -> ToolResult:
    """
    📁 Получает структуру файлов и директорий репозитория GitHub.
    
    Args:
        owner: Владелец репозитория
        repo: Название репозитория
        path: Путь к директории
        max_depth: Максимальная глубина дерева
        ctx: Контекст для логирования
        
    Returns:
        ToolResult: Результат со структурой файлов
        
    Raises:
        McpError: При ошибках выполнения
    """
    with tracer.start_as_current_span("get_file_tree") as span:
        span.set_attribute("owner", owner)
        span.set_attribute("repo", repo)
        span.set_attribute("path", path or "root")
        span.set_attribute("max_depth", max_depth)
        
        await ctx.info("🚀 Начинаем получение структуры файлов")
        await ctx.report_progress(progress=0, total=100)
        
        try:
            _require_env_vars(["GITHUB_TOKEN"])
            await ctx.report_progress(progress=10, total=100)
            
            client = create_github_client()
            await ctx.info(f"🔧 Подготавливаем запрос для {owner}/{repo}")
            await ctx.report_progress(progress=20, total=100)
            
            await ctx.info("📡 Отправляем запрос к GitHub API")
            await ctx.report_progress(progress=30, total=100)
            
            # Получаем содержимое директории
            contents_url = f"/repos/{owner}/{repo}/contents/{path}" if path else f"/repos/{owner}/{repo}/contents"
            
            response = await retry_github_request(
                client, "GET", contents_url, ctx=ctx
            )
            contents = response.json()
            
            await ctx.report_progress(progress=60, total=100)
            await ctx.info("📄 Обрабатываем полученные результаты")
            
            # Обрабатываем содержимое
            if not isinstance(contents, list):
                contents = [contents]
            
            directories = []
            files = []
            
            for item in contents:
                item_type = item.get("type")
                name = item.get("name", "")
                size = item.get("size", 0)
                
                if item_type == "dir":
                    directories.append({"name": name, "path": item.get("path", "")})
                elif item_type == "file":
                    files.append({
                        "name": name,
                        "size": size,
                        "path": item.get("path", ""),
                        "type": item.get("type", "file")
                    })
            
            # Сортируем
            directories.sort(key=lambda x: x["name"])
            files.sort(key=lambda x: x["name"])
            
            # Форматируем результат
            result_text = f"📁 Структура файлов для {owner}/{repo}\n"
            if path:
                result_text += f"📂 Путь: {path}\n"
            result_text += "\n"
            
            result_text += f"📊 Статистика:\n"
            result_text += f"  - Директорий: {len(directories)}\n"
            result_text += f"  - Файлов: {len(files)}\n\n"
            
            if directories:
                result_text += f"📂 Директории:\n"
                for dir_info in directories[:20]:  # Показываем первые 20
                    result_text += f"  - {dir_info['name']}/\n"
            
            if files:
                result_text += f"\n📄 Файлы:\n"
                for file_info in files[:30]:  # Показываем первые 30
                    size_kb = file_info["size"] / 1024 if file_info["size"] > 0 else 0
                    size_str = f"{size_kb:.1f} KB" if size_kb > 0 else "<1 KB"
                    result_text += f"  - {file_info['name']} ({size_str})\n"
            
            await ctx.report_progress(progress=95, total=100)
            await ctx.info("✅ Структура файлов успешно получена")
            await ctx.report_progress(progress=100, total=100)
            
            span.set_attribute("directories_count", len(directories))
            span.set_attribute("files_count", len(files))
            span.set_attribute("success", True)
            
            return ToolResult(
                content=[TextContent(type="text", text=result_text)],
                structured_content={
                    "path": path or "root",
                    "directories_count": len(directories),
                    "files_count": len(files),
                    "directories": directories[:20],
                    "files": files[:30]
                },
                meta={"owner": owner, "repo": repo, "operation": "get_file_tree", "path": path}
            )
            
        except Exception as e:
            span.set_attribute("error", str(e))
            await handle_github_error(e, ctx, f"получении структуры файлов {owner}/{repo}")

