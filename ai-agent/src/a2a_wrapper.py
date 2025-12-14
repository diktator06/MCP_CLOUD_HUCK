"""A2A обертки для интеграции MCP инструментов с LangChain агентом."""

import sys
import os
import json
from typing import Optional, Dict, Any, List, Type, ClassVar
import httpx
from langchain.tools import BaseTool
from pydantic import BaseModel, Field, ConfigDict

# Переиспользуемый httpx клиент для предотвращения утечки ресурсов
_shared_httpx_client: Optional[httpx.AsyncClient] = None


async def get_httpx_client() -> httpx.AsyncClient:
    """
    Получает переиспользуемый httpx клиент.
    
    Клиент создается один раз и переиспользуется для всех вызовов MCP инструментов,
    что предотвращает утечку ресурсов и улучшает производительность.
    """
    global _shared_httpx_client
    if _shared_httpx_client is None:
        _shared_httpx_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
    return _shared_httpx_client

# Добавляем путь к mcp-server-1 для импорта схем
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
mcp_server_1_path = os.path.join(project_root, 'mcp-server-1')
if mcp_server_1_path not in sys.path:
    sys.path.insert(0, mcp_server_1_path)

import sys
import os
# Добавляем путь к schemas.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import (
    GetRepositoryHealthInput
    # GetRepositoryIssuesSummaryInput и CompareRepositoriesInput не используются
    # LangChain автоматически генерирует схему из сигнатуры _arun
)


class MCPToolWrapper(BaseTool):
    """Базовый класс для обертки MCP инструментов."""
    
    # Используем model_config для Pydantic v2
    model_config = ConfigDict(extra='allow', arbitrary_types_allowed=True)
    
    server_url: str = Field(default="")
    tool_name: str = Field(default="")
    
    def __init__(self, server_url: str, tool_name: str, **kwargs):
        # Удаляем args_schema из kwargs, если он там есть, чтобы избежать конфликта
        kwargs.pop('args_schema', None)
        super().__init__(**kwargs)
        self.server_url = server_url
        self.tool_name = tool_name
    
    async def _call_mcp_tool(self, arguments: Dict[str, Any]) -> str:
        """
        Вызывает MCP инструмент через HTTP.
        
        Args:
            arguments: Аргументы для инструмента
            
        Returns:
            Текст ответа из ToolResult.content
        """
        try:
            # Используем переиспользуемый клиент вместо создания нового при каждом вызове
            client = await get_httpx_client()
            # MCP серверы используют streamable-http транспорт
            # Формат запроса: POST /mcp с JSON-RPC 2.0
            response = await client.post(
                f"{self.server_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": self.tool_name,
                        "arguments": arguments
                    }
                },
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            
            # Обрабатываем ответ MCP
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                return f"Ошибка MCP: {error_msg}"
            
            # Извлекаем content из ToolResult
            if "result" in result:
                tool_result = result["result"]
                if isinstance(tool_result, dict):
                    # ToolResult имеет структуру: {"content": [...], "structured_content": {...}, "meta": {...}}
                    content = tool_result.get("content", [])
                    if content and isinstance(content, list) and len(content) > 0:
                        # content - это список TextContent объектов
                        first_content = content[0]
                        if isinstance(first_content, dict):
                            return first_content.get("text", str(tool_result))
                        elif isinstance(first_content, str):
                            return first_content
                    # Если content пустой, используем structured_content
                    structured = tool_result.get("structured_content", {})
                    if structured:
                        return json.dumps(structured, ensure_ascii=False, indent=2)
                    return str(tool_result)
                return str(tool_result)
            
            return "Неожиданный формат ответа от MCP сервера"
                
        except httpx.HTTPStatusError as e:
            return f"HTTP ошибка при вызове {self.tool_name}: {e.response.status_code} - {e.response.text[:200]}"
        except httpx.TimeoutException:
            return f"Таймаут при вызове {self.tool_name}. MCP сервер не ответил вовремя."
        except httpx.NetworkError:
            return f"Сетевая ошибка при вызове {self.tool_name}. Проверьте, что MCP сервер запущен."
        except Exception as e:
            return f"Ошибка при вызове {self.tool_name}: {str(e)}"
    
    def _run(self, *args, **kwargs) -> str:
        """Синхронный вызов (не используется, но требуется BaseTool)."""
        import asyncio
        return asyncio.run(self._arun(*args, **kwargs))
    
    async def _arun(self, *args, **kwargs) -> str:
        """
        Асинхронный вызов инструмента.
        
        Этот метод должен быть переопределен в дочерних классах
        с конкретными параметрами для правильной генерации JSON Schema.
        """
        return await self._call_mcp_tool(kwargs)


class GetRepositoryHealthTool(MCPToolWrapper):
    """Обертка для инструмента get_repository_health."""
    
    def __init__(self):
        # Используем переменную окружения или localhost по умолчанию
        server_url = os.getenv("MCP_SERVER_1_URL", "http://localhost:8000")
        description = """📊 Получает метрики здоровья репозитория GitHub.

Используйте этот инструмент для получения информации о:
- Количестве открытых issues и pull requests
- Активности репозитория (дата последнего коммита)
- Популярности (звезды, форки, наблюдатели)
- Статусе репозитория (архивирован, отключен)
- Основном языке программирования

Входные параметры:
- owner: Владелец репозитория (username или organization name)
- repo: Название репозитория

Пример: owner="microsoft", repo="vscode"
"""
        super().__init__(
            server_url=server_url,
            tool_name="get_repository_health",
            name="get_repository_health",
            description=description
        )
    
    async def _arun(self, owner: str, repo: str) -> str:
        """Выполняет запрос к инструменту get_repository_health."""
        arguments = {
            "owner": owner,
            "repo": repo
        }
        return await self._call_mcp_tool(arguments)


# class GetRepositoryIssuesSummaryInput(BaseModel):
    #     """Схема аргументов для get_repository_issues_summary."""
    #     owner: str = Field(description="Владелец репозитория (username или organization name)")
    #     repo: str = Field(description="Название репозитория")
    #     state: Optional[str] = Field(default="open", description="Статус issues ('open', 'closed', 'all')")
    #     labels: Optional[List[str]] = Field(
    #         default=None, 
    #         description="Список labels для фильтрации",
    #         json_schema_extra={
    #             "type": "array",
    #             "items": {"type": "string"}
    #         }
    #     )


# Временно закомментировано для обхода ошибки Pydantic v2
# class GetRepositoryIssuesSummaryTool(MCPToolWrapper):
#     """Обертка для инструмента get_repository_issues_summary."""
#     
#     def __init__(self):
#         # Используем переменную окружения или localhost по умолчанию
#         server_url = os.getenv("MCP_SERVER_1_URL", "http://localhost:8000")
#         description = """📋 Получает сводку по issues репозитория GitHub.
# 
# Используйте этот инструмент для получения информации о:
# - Общем количестве issues (открытых и закрытых)
# - Распределении issues по labels
# - Списке последних issues с деталями
# - Статистике по статусам и приоритетам
# 
# Входные параметры:
# - owner: Владелец репозитория (username или organization name)
# - repo: Название репозитория
# - state: Статус issues ('open', 'closed', 'all') - опционально, по умолчанию 'open'
# - labels: Список labels для фильтрации - опционально
# 
# Пример: owner="microsoft", repo="vscode", state="open"
# """
#         super().__init__(
#             server_url=server_url,
#             tool_name="get_repository_issues_summary",
#             name="get_repository_issues_summary",
#             description=description
#         )
#     
#     async def _arun(
#         self,
#         owner: str,
#         repo: str,
#         state: Optional[str] = "open",
#         labels: Optional[List[str]] = None
#     ) -> str:
#         """Выполняет запрос к инструменту get_repository_issues_summary."""
#         arguments = {
#             "owner": owner,
#             "repo": repo
#         }
#         if state:
#             arguments["state"] = state
#         if labels:
#             arguments["labels"] = labels
#         return await self._call_mcp_tool(arguments)


# class CompareRepositoriesInput(BaseModel):
    #     """Схема аргументов для compare_repositories."""
    #     repositories: List[str] = Field(
    #         description="Список репозиториев в формате ['owner/repo', 'owner2/repo2', ...]",
    #         json_schema_extra={
    #             "type": "array",
    #             "items": {"type": "string"}
    #         }
    #     )
    #     metrics: Optional[List[str]] = Field(
    #         default=None, 
    #         description="Список метрик для сравнения (опционально)",
    #         json_schema_extra={
    #             "type": "array",
    #             "items": {"type": "string"}
    #         }
    #     )


# Временно закомментировано для обхода ошибки Pydantic v2
# class CompareRepositoriesTool(MCPToolWrapper):
#     """Обертка для инструмента compare_repositories."""
#     
#     def __init__(self):
#         # Используем переменную окружения или localhost по умолчанию
#         server_url = os.getenv("MCP_SERVER_2_URL", "http://localhost:8001")
#         description = """📊 Сравнивает метрики нескольких репозиториев GitHub параллельно.
# 
# Используйте этот инструмент для сравнения:
# - Количества звезд, форков, наблюдателей
# - Количества открытых issues и PR
# - Активности (дата последнего коммита)
# - Основного языка программирования
# - Статуса репозиториев
# 
# Инструмент определяет наиболее активный и популярный репозиторий.
# 
# Входные параметры:
# - repositories: Список репозиториев для сравнения. Каждый элемент должен содержать 'owner' и 'repo'
#   Минимум 2, максимум 5 репозиториев.
# - metrics: Список метрик для сравнения - опционально
# 
# Пример: repositories=[{"owner": "microsoft", "repo": "vscode"}, {"owner": "facebook", "repo": "react"}]
# """
#         super().__init__(
#             server_url=server_url,
#             tool_name="compare_repositories",
#             name="compare_repositories",
#             description=description
#         )
#     
#     async def _arun(
#         self,
#         repositories: List[str],
#         metrics: Optional[List[str]] = None
#     ) -> str:
#         """Выполняет запрос к инструменту compare_repositories."""
#         arguments = {
#             "repositories": repositories
#         }
#         if metrics:
#             arguments["metrics"] = metrics
#         return await self._call_mcp_tool(arguments)


class GetRepositoryContributorsTool(MCPToolWrapper):
    """Обертка для инструмента get_repository_contributors."""
    
    def __init__(self):
        # Используем переменную окружения или localhost по умолчанию
        server_url = os.getenv("MCP_SERVER_1_URL", "http://localhost:8000")
        description = """👥 Получает список контрибьюторов репозитория GitHub.

Используйте этот инструмент для получения информации о:
- Списке основных контрибьюторов с количеством коммитов
- Статистике по контрибьюторам
- Информации о топ контрибьюторах
- Общем количестве контрибьюторов

Входные параметры:
- owner: Владелец репозитория (username или organization name)
- repo: Название репозитория
- top_n: Количество топ контрибьюторов для возврата (опционально, по умолчанию 10)

Пример: owner="microsoft", repo="vscode", top_n=10
"""
        super().__init__(
            server_url=server_url,
            tool_name="get_repository_contributors",
            name="get_repository_contributors",
            description=description
        )
    
    async def _arun(self, owner: str, repo: str, top_n: int = 10) -> str:
        """Выполняет запрос к инструменту get_repository_contributors."""
        arguments = {
            "owner": owner,
            "repo": repo,
            "top_n": top_n
        }
        return await self._call_mcp_tool(arguments)


class GetCommitStatisticsTool(MCPToolWrapper):
    """Обертка для инструмента get_commit_statistics."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_3_URL", "http://localhost:8002")
        super().__init__(
            server_url=server_url,
            tool_name="get_commit_statistics",
            name="get_commit_statistics",
            description="""📊 Получает статистику коммитов репозитория GitHub.
Используйте этот инструмент для получения информации о:
- Общем количестве коммитов
- Статистике по периодам (дни, недели, месяцы)
- Активности по дням недели
- Топ авторах коммитов

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- since: Начало периода (опционально, по умолчанию '30 days ago')
- until: Конец периода (опционально, по умолчанию 'now')

Пример: owner="microsoft", repo="vscode"
"""
        )
    
    async def _arun(self, owner: str, repo: str, since: str = "30 days ago", until: str = "now") -> str:
        arguments = {
            "owner": owner,
            "repo": repo,
            "since": since,
            "until": until
        }
        return await self._call_mcp_tool(arguments)


class GetDeveloperActivityTool(MCPToolWrapper):
    """Обертка для инструмента get_developer_activity."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_3_URL", "http://localhost:8002")
        super().__init__(
            server_url=server_url,
            tool_name="get_developer_activity",
            name="get_developer_activity",
            description="""👥 Получает статистику активности разработчиков репозитория GitHub.
Используйте этот инструмент для получения информации о:
- Топ контрибьюторах по количеству коммитов
- Активности по периодам
- Распределении активности между разработчиками

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- top_n: Количество топ разработчиков (опционально, по умолчанию 10)

Пример: owner="microsoft", repo="vscode", top_n=10
"""
        )
    
    async def _arun(self, owner: str, repo: str, top_n: int = 10) -> str:
        arguments = {
            "owner": owner,
            "repo": repo,
            "top_n": top_n
        }
        return await self._call_mcp_tool(arguments)


class GetBranchAnalysisTool(MCPToolWrapper):
    """Обертка для инструмента get_branch_analysis."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_3_URL", "http://localhost:8002")
        super().__init__(
            server_url=server_url,
            tool_name="get_branch_analysis",
            name="get_branch_analysis",
            description="""🌿 Получает анализ веток репозитория GitHub.
Используйте этот инструмент для получения информации о:
- Списке всех веток
- Активных ветках (с недавними коммитами)
- Защищенных ветках
- Мертвых ветках (без активности)

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- days_threshold: Порог дней для определения активной ветки (опционально, по умолчанию 90)

Пример: owner="microsoft", repo="vscode", days_threshold=90
"""
        )
    
    async def _arun(self, owner: str, repo: str, days_threshold: int = 90) -> str:
        arguments = {
            "owner": owner,
            "repo": repo,
            "days_threshold": days_threshold
        }
        return await self._call_mcp_tool(arguments)


class SearchCodeInRepositoryTool(MCPToolWrapper):
    """Обертка для инструмента search_code_in_repository."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_4_URL", "http://localhost:8003")
        super().__init__(
            server_url=server_url,
            tool_name="search_code_in_repository",
            name="search_code_in_repository",
            description="""🔍 Ищет код в репозитории GitHub по запросу.
Используйте этот инструмент для поиска:
- Функций, классов или фрагментов кода
- Кода по текстовому запросу
- Кода с фильтрацией по языку или пути

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- query: Поисковый запрос (текст для поиска)
- language: Язык программирования для фильтрации (опционально)
- path: Путь к файлу или директории (опционально)

Пример: owner="microsoft", repo="vscode", query="function calculate"
"""
        )
    
    async def _arun(
        self,
        owner: str,
        repo: str,
        query: str,
        language: Optional[str] = None,
        path: Optional[str] = None
    ) -> str:
        arguments = {
            "owner": owner,
            "repo": repo,
            "query": query
        }
        if language:
            arguments["language"] = language
        if path:
            arguments["path"] = path
        return await self._call_mcp_tool(arguments)


class GetFileTreeTool(MCPToolWrapper):
    """Обертка для инструмента get_file_tree."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_4_URL", "http://localhost:8003")
        super().__init__(
            server_url=server_url,
            tool_name="get_file_tree",
            name="get_file_tree",
            description="""📁 Получает структуру файлов и директорий репозитория GitHub.
Используйте этот инструмент для получения информации о:
- Дереве файлов и директорий
- Размерах файлов
- Типах файлов
- Основных директориях проекта

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- path: Путь к директории (опционально, по умолчанию корень)
- max_depth: Максимальная глубина дерева (опционально, по умолчанию 2)

Пример: owner="microsoft", repo="vscode", path="src/"
"""
        )
    
    async def _arun(
        self,
        owner: str,
        repo: str,
        path: str = "",
        max_depth: int = 2
    ) -> str:
        arguments = {
            "owner": owner,
            "repo": repo,
            "path": path,
            "max_depth": max_depth
        }
        return await self._call_mcp_tool(arguments)


class AnalyzeDependenciesTool(MCPToolWrapper):
    """Обертка для инструмента analyze_dependencies."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_4_URL", "http://localhost:8003")
        super().__init__(
            server_url=server_url,
            tool_name="analyze_dependencies",
            name="analyze_dependencies",
            description="""📦 Анализирует зависимости репозитория GitHub.
Используйте этот инструмент для получения информации о:
- Зависимостях Python (requirements.txt, pyproject.toml)
- Зависимостях JavaScript/TypeScript (package.json)
- Зависимостях Java (pom.xml, build.gradle)
- Зависимостях Go (go.mod)
- Зависимостях Rust (Cargo.toml)

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория

Пример: owner="microsoft", repo="vscode"
"""
        )
    
    async def _arun(self, owner: str, repo: str) -> str:
        arguments = {
            "owner": owner,
            "repo": repo
        }
        return await self._call_mcp_tool(arguments)


class CheckSecurityAdvisoriesTool(MCPToolWrapper):
    """Обертка для инструмента check_security_advisories."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_5_URL", "http://localhost:8004")
        super().__init__(
            server_url=server_url,
            tool_name="check_security_advisories",
            name="check_security_advisories",
            description="""🔒 Проверяет security advisories репозитория GitHub.
Используйте этот инструмент для проверки безопасности репозитория.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория

Пример: owner="microsoft", repo="vscode"
"""
        )
    
    async def _arun(self, owner: str, repo: str) -> str:
        arguments = {"owner": owner, "repo": repo}
        return await self._call_mcp_tool(arguments)


class AnalyzeDependencyVulnerabilitiesTool(MCPToolWrapper):
    """Обертка для инструмента analyze_dependency_vulnerabilities."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_5_URL", "http://localhost:8004")
        super().__init__(
            server_url=server_url,
            tool_name="analyze_dependency_vulnerabilities",
            name="analyze_dependency_vulnerabilities",
            description="""🛡️ Анализирует уязвимости зависимостей репозитория GitHub.
Используйте этот инструмент для проверки безопасности зависимостей проекта.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория

Пример: owner="microsoft", repo="vscode"
"""
        )
    
    async def _arun(self, owner: str, repo: str) -> str:
        arguments = {"owner": owner, "repo": repo}
        return await self._call_mcp_tool(arguments)


class CheckRepositoryComplianceTool(MCPToolWrapper):
    """Обертка для инструмента check_repository_compliance."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_5_URL", "http://localhost:8004")
        super().__init__(
            server_url=server_url,
            tool_name="check_repository_compliance",
            name="check_repository_compliance",
            description="""✅ Проверяет compliance репозитория GitHub.
Используйте этот инструмент для проверки соответствия репозитория стандартам.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория

Пример: owner="microsoft", repo="vscode"
"""
        )
    
    async def _arun(self, owner: str, repo: str) -> str:
        arguments = {"owner": owner, "repo": repo}
        return await self._call_mcp_tool(arguments)


class GetReleasesSummaryTool(MCPToolWrapper):
    """Обертка для инструмента get_releases_summary."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_6_URL", "http://localhost:8005")
        super().__init__(
            server_url=server_url,
            tool_name="get_releases_summary",
            name="get_releases_summary",
            description="""📦 Получает сводку по релизам репозитория GitHub.
Используйте этот инструмент для анализа релизов и версий проекта.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- limit: Количество релизов (опционально, по умолчанию 10)

Пример: owner="microsoft", repo="vscode", limit=10
"""
        )
    
    async def _arun(self, owner: str, repo: str, limit: int = 10) -> str:
        arguments = {"owner": owner, "repo": repo, "limit": limit}
        return await self._call_mcp_tool(arguments)


class AnalyzeRepositoryTagsTool(MCPToolWrapper):
    """Обертка для инструмента analyze_repository_tags."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_6_URL", "http://localhost:8005")
        super().__init__(
            server_url=server_url,
            tool_name="analyze_repository_tags",
            name="analyze_repository_tags",
            description="""🏷️ Анализирует теги репозитория GitHub.
Используйте этот инструмент для анализа версионирования проекта.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- limit: Количество тегов (опционально, по умолчанию 20)

Пример: owner="microsoft", repo="vscode", limit=20
"""
        )
    
    async def _arun(self, owner: str, repo: str, limit: int = 20) -> str:
        arguments = {"owner": owner, "repo": repo, "limit": limit}
        return await self._call_mcp_tool(arguments)


class CompareReleaseVersionsTool(MCPToolWrapper):
    """Обертка для инструмента compare_release_versions."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_6_URL", "http://localhost:8005")
        super().__init__(
            server_url=server_url,
            tool_name="compare_release_versions",
            name="compare_release_versions",
            description="""📊 Сравнивает версии релизов репозитория GitHub.
Используйте этот инструмент для анализа изменений между версиями проекта.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- version1: Первая версия (опционально)
- version2: Вторая версия (опционально)

Пример: owner="microsoft", repo="vscode"
"""
        )
    
    async def _arun(self, owner: str, repo: str, version1: Optional[str] = None, version2: Optional[str] = None) -> str:
        arguments = {"owner": owner, "repo": repo}
        if version1:
            arguments["version1"] = version1
        if version2:
            arguments["version2"] = version2
        return await self._call_mcp_tool(arguments)


class GetRepositoryWebhooksTool(MCPToolWrapper):
    """Обертка для инструмента get_repository_webhooks."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_7_URL", "http://localhost:8006")
        super().__init__(
            server_url=server_url,
            tool_name="get_repository_webhooks",
            name="get_repository_webhooks",
            description="""🔔 Получает список webhooks репозитория GitHub.
Используйте этот инструмент для анализа интеграций репозитория.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория

Пример: owner="microsoft", repo="vscode"
"""
        )
    
    async def _arun(self, owner: str, repo: str) -> str:
        arguments = {"owner": owner, "repo": repo}
        return await self._call_mcp_tool(arguments)


class AnalyzeRepositoryEventsTool(MCPToolWrapper):
    """Обертка для инструмента analyze_repository_events."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_7_URL", "http://localhost:8006")
        super().__init__(
            server_url=server_url,
            tool_name="analyze_repository_events",
            name="analyze_repository_events",
            description="""📅 Анализирует события репозитория GitHub.
Используйте этот инструмент для анализа активности репозитория через события.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- limit: Количество событий (опционально, по умолчанию 30)

Пример: owner="microsoft", repo="vscode", limit=30
"""
        )
    
    async def _arun(self, owner: str, repo: str, limit: int = 30) -> str:
        arguments = {"owner": owner, "repo": repo, "limit": limit}
        return await self._call_mcp_tool(arguments)


class GetActivityTimelineTool(MCPToolWrapper):
    """Обертка для инструмента get_activity_timeline."""
    
    def __init__(self):
        server_url = os.getenv("MCP_SERVER_7_URL", "http://localhost:8006")
        super().__init__(
            server_url=server_url,
            tool_name="get_activity_timeline",
            name="get_activity_timeline",
            description="""📈 Получает временную линию активности репозитория GitHub.
Используйте этот инструмент для визуализации активности репозитория во времени.

Входные параметры:
- owner: Владелец репозитория
- repo: Название репозитория
- days: Количество дней для анализа (опционально, по умолчанию 30)

Пример: owner="microsoft", repo="vscode", days=30
"""
        )
    
    async def _arun(self, owner: str, repo: str, days: int = 30) -> str:
        arguments = {"owner": owner, "repo": repo, "days": days}
        return await self._call_mcp_tool(arguments)


def create_mcp_tools() -> list:
    """
    Создает список всех MCP инструментов для LangChain агента.
    
    Returns:
        Список LangChain инструментов
    """
    return [
        # Server 1 tools
        GetRepositoryHealthTool(),
        # GetRepositoryIssuesSummaryTool(),  # Временно отключено для обхода ошибки Pydantic
        GetRepositoryContributorsTool(),
        # Server 2 tools
        # CompareRepositoriesTool(),  # Временно отключено для обхода ошибки Pydantic
        # Server 3 tools
        GetCommitStatisticsTool(),
        GetDeveloperActivityTool(),
        GetBranchAnalysisTool(),
        # Server 4 tools
        SearchCodeInRepositoryTool(),
        GetFileTreeTool(),
        AnalyzeDependenciesTool(),
        # Server 5 tools
        CheckSecurityAdvisoriesTool(),
        AnalyzeDependencyVulnerabilitiesTool(),
        CheckRepositoryComplianceTool(),
        # Server 6 tools
        GetReleasesSummaryTool(),
        AnalyzeRepositoryTagsTool(),
        CompareReleaseVersionsTool(),
        # Server 7 tools
        GetRepositoryWebhooksTool(),
        AnalyzeRepositoryEventsTool(),
        GetActivityTimelineTool()
    ]

