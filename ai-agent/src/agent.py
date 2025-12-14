"""LangChain агент для работы с MCP инструментами GitHub."""

import os
from typing import List, Optional
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool


class ModelManager:
    """Менеджер моделей Evolution Foundation Models."""
    
    # Список доступных моделей (11 моделей Evolution Foundation Models)
    AVAILABLE_MODELS = [
        "GigaChat/GigaChat-2-Max",
        "ai-sage/GigaChat3-10B-A1.8B",
        "MiniMaxAI/MiniMax-M2",
        "zai-org/GLM-4.6",
        "openai/gpt-oss-120b",
        "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-Next-80B-A3B-Instruct",
        "t-tech/T-lite-it-1.0",
        "t-tech/T-pro-it-1.0",
        "t-tech/T-pro-it-2.0"
    ]
    
    # Рекомендуемые модели по категориям
    RECOMMENDED_MODELS = {
        "default": "Qwen/Qwen3-Next-80B-A3B-Instruct",
        "coding": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "large": "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "gigachat": "GigaChat/GigaChat-2-Max",
        "t-pro": "t-tech/T-pro-it-2.0"
    }
    
    # Упрощенные алиасы для пользователей (11 моделей)
    MODEL_ALIASES = {
        "GigaChat": "GigaChat/GigaChat-2-Max",
        "Sage": "ai-sage/GigaChat3-10B-A1.8B",
        "MiniMax": "MiniMaxAI/MiniMax-M2",
        "GLM": "zai-org/GLM-4.6",
        "GPT-OSS": "openai/gpt-oss-120b",
        "Qwen-Coder": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "Qwen-Large": "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen-Next": "Qwen/Qwen3-Next-80B-A3B-Instruct",
        "T-Lite-1.0": "t-tech/T-lite-it-1.0",
        "T-Pro-1.0": "t-tech/T-pro-it-1.0",
        "T-Pro-2.0": "t-tech/T-pro-it-2.0",
        # Дополнительные алиасы для обратной совместимости
        "default": "Qwen/Qwen3-Next-80B-A3B-Instruct",
        "coding": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "large": "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "T-Pro": "t-tech/T-pro-it-2.0",
        "T-Lite": "t-tech/T-lite-it-1.0",
        "T-Pro-1": "t-tech/T-pro-it-1.0",
        "GigaChat3": "ai-sage/GigaChat3-10B-A1.8B"
    }
    
    def __init__(self):
        """Инициализация ModelManager."""
        self.current_model = None
        self.api_key = os.getenv("API_KEY")
        self.base_url = os.getenv("BASE_URL", "https://foundation-models.api.cloud.ru/v1")
    
    def get_model(self, model_name: Optional[str] = None) -> str:
        """
        Получает имя модели для использования.
        
        Args:
            model_name: Имя модели или None для использования модели по умолчанию
            
        Returns:
            Имя модели для использования
        """
        if model_name:
            if model_name in self.AVAILABLE_MODELS:
                return model_name
            elif model_name in self.RECOMMENDED_MODELS:
                return self.RECOMMENDED_MODELS[model_name]
            else:
                print(f"⚠️ Модель {model_name} не найдена. Используется модель по умолчанию.")
                return self.RECOMMENDED_MODELS["default"]
        
        # Используем модель из переменных окружения или по умолчанию
        default_model = os.getenv("DEFAULT_MODEL", self.RECOMMENDED_MODELS["default"])
        return default_model
    
    def list_models(self) -> List[str]:
        """
        Возвращает список доступных моделей.
        
        Returns:
            Список имен моделей
        """
        return self.AVAILABLE_MODELS
    
    def get_recommended_models(self) -> dict:
        """
        Возвращает словарь рекомендуемых моделей по категориям.
        
        Returns:
            Словарь с рекомендуемыми моделями
        """
        return self.RECOMMENDED_MODELS
    
    def resolve_alias(self, alias: str) -> Optional[str]:
        """
        Разрешает упрощенный алиас в полное имя модели.
        
        Args:
            alias: Упрощенный алиас модели (например, "GigaChat", "Qwen-Next")
            
        Returns:
            Полное имя модели или None, если алиас не найден
        """
        alias_upper = alias.strip()
        # Проверяем точное совпадение (с учетом регистра)
        if alias_upper in self.MODEL_ALIASES:
            return self.MODEL_ALIASES[alias_upper]
        # Проверяем без учета регистра
        alias_lower = alias_upper.lower()
        for key, value in self.MODEL_ALIASES.items():
            if key.lower() == alias_lower:
                return value
        return None
    
    def get_available_aliases(self) -> List[str]:
        """
        Возвращает список доступных алиасов моделей.
        
        Returns:
            Список алиасов
        """
        return list(self.MODEL_ALIASES.keys())


def create_llm(model_name: Optional[str] = None, temperature: float = 0.5) -> ChatOpenAI:
    """
    Создает экземпляр LLM для Evolution Foundation Models.
    
    Args:
        model_name: Имя модели (опционально)
        temperature: Температура для генерации (по умолчанию 0.5)
        
    Returns:
        Настроенный ChatOpenAI клиент
    """
    model_manager = ModelManager()
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL", "https://foundation-models.api.cloud.ru/v1")
    
    if not api_key:
        raise ValueError("API_KEY не найден в переменных окружения")
    
    selected_model = model_manager.get_model(model_name)
    
    llm = ChatOpenAI(
        model=selected_model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=2500,
        presence_penalty=0,
        top_p=0.95
    )
    
    return llm


def create_agent(tools: List[BaseTool], model_name: Optional[str] = None) -> AgentExecutor:
    """
    Создает LangChain агента с MCP инструментами.
    
    Args:
        tools: Список LangChain инструментов (MCP обертки)
        model_name: Имя модели для использования (опционально)
        
    Returns:
        AgentExecutor: Исполнитель агента
    """
    # Создаем LLM
    llm = create_llm(model_name=model_name)
    
    # Промпт для агента
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """Ты полезный AI-ассистент для анализа репозиториев GitHub.

Твоя задача - помогать пользователям получать информацию о репозиториях GitHub через доступные инструменты.

Доступные инструменты:
1. get_repository_health - получение метрик здоровья репозитория
2. get_repository_issues_summary - получение сводки по issues репозитория
3. get_repository_contributors - получение списка контрибьюторов репозитория
4. compare_repositories - сравнение нескольких репозиториев
5. get_commit_statistics - статистика коммитов репозитория
6. get_developer_activity - активность разработчиков
7. get_branch_analysis - анализ веток репозитория
8. search_code_in_repository - поиск кода в репозитории
9. get_file_tree - структура файлов репозитория
10. analyze_dependencies - анализ зависимостей проекта
11. check_security_advisories - проверка security advisories
12. analyze_dependency_vulnerabilities - анализ уязвимостей зависимостей
13. check_repository_compliance - проверка compliance репозитория
14. get_releases_summary - сводка по релизам репозитория
15. analyze_repository_tags - анализ тегов репозитория
16. compare_release_versions - сравнение версий релизов
17. get_repository_webhooks - список webhooks репозитория
18. analyze_repository_events - анализ событий репозитория
19. get_activity_timeline - временная линия активности репозитория

Инструкции:
- Используй инструменты для получения актуальной информации
- Отвечай на русском языке, если пользователь задает вопросы на русском
- Форматируй ответы в удобочитаемом виде
- Если пользователь спрашивает о репозитории, используй соответствующий инструмент
- Если нужно сравнить репозитории, используй compare_repositories
- Всегда проверяй правильность формата owner/repo перед вызовом инструментов

Будь полезным и информативным в своих ответах."""
        ),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Создаем агента с функциями OpenAI
    # Обрабатываем ошибки валидации схемы инструментов
    try:
        agent = create_openai_functions_agent(llm, tools, prompt)
    except Exception as e:
        error_str = str(e)
        if "422" in error_str or "Type properties" in error_str or "args.items.type" in error_str:
            # Если ошибка валидации схемы, фильтруем проблемные инструменты
            print(f"⚠️ Ошибка валидации схемы инструментов: {error_str}")
            print("Попытка создать агента без проблемных инструментов...")
            # Пробуем создать агента без инструментов с List типами
            filtered_tools = [t for t in tools if t.name not in ["get_repository_issues_summary", "compare_repositories"]]
            if filtered_tools:
                agent = create_openai_functions_agent(llm, filtered_tools, prompt)
            else:
                # Если все инструменты проблемные, создаем агента без инструментов
                agent = create_openai_functions_agent(llm, [], prompt)
        else:
            raise
    
    # Создаем исполнитель агента
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10,
        return_intermediate_steps=True  # Включаем для trace в API
    )
    
    return agent_executor


def create_agent_with_model_switch(
    tools: List[BaseTool],
    model_name: Optional[str] = None
) -> tuple[AgentExecutor, ModelManager]:
    """
    Создает агента с возможностью переключения модели.
    
    Args:
        tools: Список LangChain инструментов
        model_name: Имя модели для использования (опционально)
        
    Returns:
        Кортеж (AgentExecutor, ModelManager)
    """
    model_manager = ModelManager()
    agent = create_agent(tools, model_name=model_name)
    return agent, model_manager


class AgentWithModelSwitch:
    """
    Обертка для AgentExecutor с поддержкой динамического переключения моделей.
    """
    
    def __init__(self, tools: List[BaseTool], initial_model: Optional[str] = None):
        """
        Инициализация агента с поддержкой переключения моделей.
        
        Args:
            tools: Список LangChain инструментов
            initial_model: Начальная модель (опционально)
        """
        self.tools = tools
        self.model_manager = ModelManager()
        self.current_model = self.model_manager.get_model(initial_model)
        self.agent = create_agent(tools, model_name=self.current_model)
    
    def switch_model(self, model_alias: str) -> tuple[bool, str]:
        """
        Переключает модель агента.
        
        Args:
            model_alias: Алиас модели для переключения
            
        Returns:
            Кортеж (успех, сообщение)
        """
        # Разрешаем алиас в полное имя модели
        resolved_model = self.model_manager.resolve_alias(model_alias)
        
        if not resolved_model:
            aliases = self.model_manager.get_available_aliases()
            return False, f"Неизвестный алиас: {model_alias}. Доступные: {', '.join(aliases)}"
        
        if resolved_model == self.current_model:
            return False, f"Модель {resolved_model} уже активна"
        
        try:
            # Переинициализируем агента с новой моделью
            self.agent = create_agent(self.tools, model_name=resolved_model)
            self.current_model = resolved_model
            return True, f"Модель успешно переключена на: {resolved_model}"
        except Exception as e:
            return False, f"Ошибка при переключении модели: {str(e)}"
    
    def get_current_model(self) -> str:
        """Возвращает текущую модель."""
        return self.current_model
    
    def invoke(self, input_data: dict):
        """Вызывает агента (прокси метод)."""
        return self.agent.invoke(input_data)
    
    async def ainvoke(self, input_data: dict):
        """Асинхронно вызывает агента (прокси метод)."""
        return await self.agent.ainvoke(input_data)

