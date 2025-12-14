"""Точка входа для AI агента с демонстрацией работы."""

import os
import asyncio
from dotenv import load_dotenv, find_dotenv

# Загрузка переменных окружения
load_dotenv(find_dotenv())

from a2a_wrapper import create_mcp_tools
from agent import create_agent, ModelManager, AgentWithModelSwitch


def print_separator():
    """Печатает разделитель для лучшей читаемости."""
    print("\n" + "=" * 80 + "\n")


def print_demo_header(title: str):
    """Печатает заголовок демонстрации."""
    print_separator()
    print(f"🎯 {title}")
    print_separator()


def display_status(agent_wrapper: AgentWithModelSwitch):
    """
    Отображает текущий статус агента.
    
    Args:
        agent_wrapper: Обертка агента с поддержкой переключения моделей
    """
    print_separator()
    print(f"📊 Текущая модель: {agent_wrapper.get_current_model()}")
    print_separator()


def switch_model_interactively(agent_wrapper: AgentWithModelSwitch) -> bool:
    """
    Интерактивное переключение модели с пронумерованным списком всех 11 моделей.
    
    Args:
        agent_wrapper: Обертка агента с поддержкой переключения моделей
        
    Returns:
        True если модель была переключена, False если операция отменена
    """
    print_separator()
    print("🔄 ПЕРЕКЛЮЧЕНИЕ МОДЕЛИ")
    print_separator()
    
    # Получаем список основных алиасов (11 моделей)
    # Фильтруем только основные алиасы, исключая дополнительные для обратной совместимости
    all_aliases = agent_wrapper.model_manager.get_available_aliases()
    primary_aliases = [
        "GigaChat", "Sage", "MiniMax", "GLM", "GPT-OSS",
        "Qwen-Coder", "Qwen-Large", "Qwen-Next",
        "T-Lite-1.0", "T-Pro-1.0", "T-Pro-2.0"
    ]
    
    # Фильтруем только те, которые существуют в MODEL_ALIASES
    available_primary_aliases = [
        alias for alias in primary_aliases 
        if alias in agent_wrapper.model_manager.MODEL_ALIASES
    ]
    
    current_model = agent_wrapper.get_current_model()
    
    # Находим текущий алиас
    current_alias = None
    for alias, model_path in agent_wrapper.model_manager.MODEL_ALIASES.items():
        if model_path == current_model:
            # Предпочитаем основной алиас, если есть
            if alias in available_primary_aliases:
                current_alias = alias
                break
            elif current_alias is None:
                current_alias = alias
    
    # Выводим пронумерованный список всех 11 моделей
    print("Доступные модели (Evolution Foundation Models):")
    print("  0. ❌ Отмена (оставить текущую модель)")
    
    for i, alias in enumerate(available_primary_aliases, 1):
        model_path = agent_wrapper.model_manager.MODEL_ALIASES[alias]
        marker = " ← текущая" if alias == current_alias else ""
        print(f"  {i:2d}. {alias:15s} -> {model_path}{marker}")
    
    print_separator()
    
    # Запрашиваем выбор пользователя
    try:
        choice = input("Выберите модель (введите номер или 0 для отмены): ").strip()
        
        # Отмена
        if not choice or choice == "0":
            print("❌ Переключение модели отменено")
            print(f"📊 Текущая модель осталась: {current_model}")
            return False
        
        # Парсим номер
        try:
            choice_num = int(choice)
        except ValueError:
            # Если не число, пытаемся использовать как алиас напрямую
            print(f"\n🔄 Попытка переключения на алиас: {choice}")
            success, message = agent_wrapper.switch_model(choice)
            if success:
                print(f"✅ {message}")
                display_status(agent_wrapper)
                return True
            else:
                print(f"❌ {message}")
                return False
        
        # Проверяем диапазон
        if choice_num < 1 or choice_num > len(available_primary_aliases):
            print(f"❌ Неверный номер. Выберите от 0 до {len(available_primary_aliases)}")
            return False
        
        # Получаем выбранный алиас
        selected_alias = available_primary_aliases[choice_num - 1]
        selected_model = agent_wrapper.model_manager.MODEL_ALIASES[selected_alias]
        
        # Проверяем, не выбрана ли уже текущая модель
        if selected_model == current_model:
            print(f"⚠️ Модель {selected_model} уже активна")
            return False
        
        # Переключаем модель
        print(f"\n🔄 Переключение на: {selected_model}")
        print("⏳ Переинициализация агента...\n")
        
        success, message = agent_wrapper.switch_model(selected_alias)
        
        if success:
            print(f"✅ {message}")
            display_status(agent_wrapper)
            return True
        else:
            print(f"❌ {message}")
            return False
            
    except KeyboardInterrupt:
        print("\n❌ Переключение модели отменено пользователем")
        return False
    except Exception as e:
        print(f"\n❌ Ошибка при переключении модели: {str(e)}")
        return False


async def run_agent_query(agent, query: str, description: str):
    """
    Выполняет запрос к агенту и выводит результат.
    
    Args:
        agent: AgentExecutor для выполнения запросов
        query: Текст запроса
        description: Описание демонстрации
    """
    print(f"📝 Запрос: {query}")
    print(f"📋 Описание: {description}")
    print("\n🤖 Ответ агента:\n")
    
    try:
        result = agent.invoke({"input": query})
        print(result.get("output", "Нет ответа"))
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
    
    print_separator()


async def main():
    """Главная функция с демонстрацией работы агента."""
    print("=" * 80)
    print("🚀 ЗАПУСК AI АГЕНТА ДЛЯ АНАЛИЗА РЕПОЗИТОРИЕВ GITHUB")
    print("=" * 80)
    
    # Проверка переменных окружения
    api_key = os.getenv("API_KEY")
    if not api_key:
        print("❌ ОШИБКА: API_KEY не найден в переменных окружения")
        print("Убедитесь, что файл .env существует и содержит API_KEY")
        return
    
    print(f"✅ API Key загружен: {api_key[:20]}...")
    print(f"✅ Base URL: {os.getenv('BASE_URL', 'https://foundation-models.api.cloud.ru/v1')}")
    print(f"✅ Default Model: {os.getenv('DEFAULT_MODEL', 'Qwen/Qwen3-Next-80B-A3B-Instruct')}")
    
    print_separator()
    
    # Создание инструментов
    print("🔧 Создание MCP инструментов...")
    try:
        tools = create_mcp_tools()
        print(f"✅ Создано инструментов: {len(tools)}")
        for tool in tools:
            print(f"   - {tool.name}")
    except Exception as e:
        print(f"❌ Ошибка при создании инструментов: {e}")
        return
    
    print_separator()
    
    # Создание агента с поддержкой переключения моделей
    print("🤖 Создание LangChain агента...")
    try:
        agent_wrapper = AgentWithModelSwitch(tools)
        print("✅ Агент успешно создан")
    except Exception as e:
        print(f"❌ Ошибка при создании агента: {e}")
        return
    
    print_separator()
    
    # Информация о ModelManager
    print("📊 Информация о ModelManager:")
    print(f"   Доступно моделей: {len(agent_wrapper.model_manager.AVAILABLE_MODELS)}")
    print(f"   Текущая модель: {agent_wrapper.get_current_model()}")
    print(f"   Доступные алиасы для переключения:")
    aliases = agent_wrapper.model_manager.get_available_aliases()
    for alias in aliases[:10]:  # Показываем первые 10
        model_path = agent_wrapper.model_manager.MODEL_ALIASES[alias]
        print(f"     - {alias} -> {model_path}")
    if len(aliases) > 10:
        print(f"     ... и еще {len(aliases) - 10} алиасов")
    
    print_separator()
    
    # Демонстрация работы
    print("🎬 НАЧАЛО ДЕМОНСТРАЦИИ")
    print_separator()
    
    # Демонстрация 1: Успешный вызов инструмента 1 (Server 1)
    print_demo_header("ДЕМОНСТРАЦИЯ 1: Получение метрик здоровья репозитория")
    await run_agent_query(
        agent_wrapper,
        "What is the health status of langchain-ai/langchain?",
        "Успешный вызов инструмента get_repository_health для репозитория langchain-ai/langchain"
    )
    
    # Демонстрация 2: Успешный вызов инструмента 2 (Server 2)
    print_demo_header("ДЕМОНСТРАЦИЯ 2: Сравнение репозиториев")
    await run_agent_query(
        agent_wrapper,
        "Compare langchain-ai/langchain and openai/openai-python repositories",
        "Успешный вызов инструмента compare_repositories для сравнения двух репозиториев"
    )
    
    # Демонстрация 3: Обработка ошибок
    print_demo_header("ДЕМОНСТРАЦИЯ 3: Обработка ошибок (несуществующий репозиторий)")
    await run_agent_query(
        agent_wrapper,
        "What is the health of non-existent-user/repo-123?",
        "Обработка ошибки при попытке получить метрики несуществующего репозитория"
    )
    
    # Демонстрация 4: Дополнительный запрос на русском
    print_demo_header("ДЕМОНСТРАЦИЯ 4: Запрос на русском языке")
    await run_agent_query(
        agent_wrapper,
        "Получи сводку по issues репозитория microsoft/vscode",
        "Демонстрация работы с русским языком и инструментом get_repository_issues_summary"
    )
    
    print_separator()
    print("✅ ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА")
    print_separator()
    
    # Интерактивный режим
    print("💬 ИНТЕРАКТИВНЫЙ РЕЖИМ")
    print("Введите запрос для агента (или 'exit' для выхода):")
    print("💡 Команды:")
    print("   /model или /switch - интерактивное переключение модели")
    print("   [SET_MODEL: <ALIAS>] - быстрое переключение по алиасу")
    print("   exit/quit/выход - выход")
    print_separator()
    
    display_status(agent_wrapper)
    
    while True:
        try:
            user_input = input("Вы: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'выход']:
                print("\n👋 До свидания!")
                break
            
            if not user_input:
                continue
            
            # Проверка команды интерактивного переключения модели
            if user_input.lower() in ['/model', '/switch', '/модель']:
                switch_model_interactively(agent_wrapper)
                continue
            
            # Проверка команды быстрого переключения модели
            if user_input.startswith("[SET_MODEL:") and user_input.endswith("]"):
                # Извлекаем алиас модели
                alias = user_input[11:-1].strip()  # Убираем "[SET_MODEL:" и "]"
                
                print(f"\n🔄 Попытка переключения модели на алиас: {alias}")
                print("⏳ Переинициализация агента...\n")
                
                # Используем метод switch_model из AgentWithModelSwitch
                success, message = agent_wrapper.switch_model(alias)
                
                if success:
                    print(f"✅ {message}")
                    display_status(agent_wrapper)
                else:
                    print(f"❌ {message}")
                    if "Неизвестный алиас" in message:
                        print("\n📋 Доступные алиасы:")
                        aliases = agent_wrapper.model_manager.get_available_aliases()
                        for i, alias_name in enumerate(aliases, 1):
                            model_path = agent_wrapper.model_manager.MODEL_ALIASES[alias_name]
                            print(f"   {i}. {alias_name} -> {model_path}")
                
                print_separator()
                continue
            
            print("\n🤖 Агент обрабатывает запрос...\n")
            result = agent_wrapper.invoke({"input": user_input})
            print(f"\n🤖 Ответ: {result.get('output', 'Нет ответа')}\n")
            print_separator()
            
        except KeyboardInterrupt:
            print("\n\n👋 Прервано пользователем. До свидания!")
            break
        except Exception as e:
            print(f"\n❌ Ошибка: {str(e)}\n")
            print_separator()


if __name__ == "__main__":
    # Запускаем главную функцию
    import asyncio
    asyncio.run(main())

