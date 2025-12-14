"""Streamlit фронтенд для MCP Cloud.ru с темным дизайном, точно соответствующим макету."""

import streamlit as st
import requests
import json
import os
from typing import List, Dict, Any
import time
from functools import wraps

# Настройка страницы
st.set_page_config(
    page_title="MCP Cloud.ru",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# API URL
API_URL = os.getenv("API_URL", "http://ai-agent:8000")

# Кастомный CSS для точного соответствия макету
CUSTOM_CSS = """
<style>
    /* Основной темный фон */
    .stApp {
        background: #0a0a0a;
        color: #ffffff;
    }
    
    /* Геометрический паттерн на фоне основной области */
    .main .block-container {
        background-image: 
            linear-gradient(0deg, rgba(0, 191, 255, 0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 191, 255, 0.05) 1px, transparent 1px);
        background-size: 50px 50px;
        background-position: 0 0;
    }
    
    /* Боковая панель - темный фон */
    section[data-testid="stSidebar"] {
        background-color: #1a1a2e;
    }
    
    /* EZDEL TECH - неоновый синий заголовок */
    .ezdel-tech {
        color: #00BFFF;
        text-shadow: 0 0 10px #00BFFF, 0 0 20px #00BFFF, 0 0 30px #00BFFF;
        font-size: 2rem;
        font-weight: bold;
        letter-spacing: 3px;
        text-align: center;
        padding: 1.5rem 0;
    }
    
    /* Заголовок "Select LLM Model" */
    .model-selector-title {
        color: #ffffff;
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 1rem;
    }
    
    /* Стилизованный dropdown для моделей */
    .model-dropdown {
        background-color: #2a2a3e;
        border: 1px solid #3a3a4e;
        border-radius: 5px;
        padding: 0.5rem;
        color: #ffffff;
        width: 100%;
    }
    
    /* Placeholder button - темное серое поле */
    .placeholder-button {
        background-color: #2a2a3e;
        border: 1px solid #3a3a4e;
        border-radius: 5px;
        padding: 0.75rem;
        width: 100%;
        margin: 1rem 0;
        min-height: 40px;
    }
    
    /* Ссылка "For settings" */
    .settings-link {
        color: #00BFFF;
        text-decoration: none;
        text-align: center;
        display: block;
        padding: 1rem 0;
        font-size: 0.9rem;
    }
    
    .settings-link:hover {
        color: #0099CC;
        text-decoration: underline;
    }
    
    /* Заголовок "MCP Cloud.ru" */
    .main-title {
        color: #00BFFF;
        text-shadow: 0 0 10px #00BFFF, 0 0 20px #00BFFF;
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
        padding: 1rem 0;
    }
    
    /* Поле ввода запроса */
    .query-input-container {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 1.5rem;
    }
    
    .stTextInput>div>div>input {
        background-color: #2a2a3e;
        color: #ffffff;
        border: 1px solid #3a3a4e;
        border-radius: 5px;
        padding: 0.75rem;
    }
    
    .stTextInput>div>div>input:focus {
        border-color: #00BFFF;
        box-shadow: 0 0 10px rgba(0, 191, 255, 0.3);
    }
    
    /* Кнопка Analyze - синяя, не красная */
    .stButton>button {
        background-color: #00BFFF !important;
        color: white !important;
        border: none !important;
        border-radius: 5px !important;
        padding: 0.75rem 2rem !important;
        font-weight: bold !important;
        box-shadow: 0 0 10px rgba(0, 191, 255, 0.5) !important;
        white-space: nowrap !important;
    }
    
    .stButton>button:hover {
        background-color: #0099CC !important;
        box-shadow: 0 0 20px rgba(0, 191, 255, 0.8) !important;
    }
    
    /* Принудительно синий цвет для primary кнопок */
    button[kind="primary"] {
        background-color: #00BFFF !important;
        color: white !important;
    }
    
    button[kind="primary"]:hover {
        background-color: #0099CC !important;
    }
    
    /* Информационное окно */
    .info-box {
        background-color: #1a2a3e;
        border-left: 4px solid #00BFFF;
        padding: 1rem;
        border-radius: 5px;
        margin-top: 2rem;
    }
    
    .info-icon {
        color: #00BFFF;
        font-size: 1.2rem;
        margin-right: 0.5rem;
    }
    
    /* Trace блоки */
    .trace-block {
        background-color: #1a1a2e;
        border-left: 3px solid #00BFFF;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 5px;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
    }
    
    .trace-thought {
        border-left-color: #00BFFF;
    }
    
    .trace-success {
        border-left-color: #00ff00;
    }
    
    .trace-error {
        border-left-color: #ff0000;
    }
    
    /* Скрываем только footer */
    footer {visibility: hidden;}
    
    /* КРИТИЧНО: Header и кнопка sidebar ДОЛЖНЫ быть видны */
    header {visibility: visible !important;}
    
    /* Кнопка открытия sidebar (☰) - ОБЯЗАТЕЛЬНО видна */
    button[data-testid="baseButton-header"] {
        visibility: visible !important;
        display: block !important;
        opacity: 1 !important;
    }
    
    /* Все кнопки в header должны быть видны */
    [data-testid="stHeader"] button {
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* Декоративный элемент меню должен быть виден */
    [data-testid="stHeader"] [data-testid="stDecoration"] {
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* Sidebar должен быть доступен */
    [data-testid="stSidebar"] {
        visibility: visible !important;
    }
    
    /* Кнопка закрытия/открытия sidebar */
    [data-testid="stSidebar"] [data-testid="collapsedControl"] {
        visibility: visible !important;
    }
    
    /* Стили для selectbox моделей - делаем похожим на radio buttons */
    .stSelectbox>div>div>select {
        background-color: #2a2a3e !important;
        color: #ffffff !important;
        border: 1px solid #3a3a4e !important;
        border-radius: 5px !important;
    }
    
    /* Стили для выбранной модели - голубая подсветка */
    .stSelectbox>div>div>select:focus {
        border-color: #00BFFF !important;
        box-shadow: 0 0 10px rgba(0, 191, 255, 0.3) !important;
    }
    
    /* Декоративный элемент в правом нижнем углу */
    .decorative-element {
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        width: 60px;
        height: 60px;
        background: radial-gradient(circle, rgba(0, 191, 255, 0.3) 0%, transparent 70%);
        border: 2px solid rgba(0, 191, 255, 0.5);
        border-radius: 50%;
        box-shadow: 0 0 20px rgba(0, 191, 255, 0.5);
        z-index: 1;
        pointer-events: none;
    }
    
    .decorative-element::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 40px;
        height: 40px;
        background: radial-gradient(circle, rgba(0, 191, 255, 0.5) 0%, transparent 70%);
        border-radius: 50%;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Инициализация session state для истории разговора
if "history" not in st.session_state:
    st.session_state.history = []


def retry_request(max_retries=3, backoff_factor=1.0):
    """
    Декоратор для повторных попыток запросов с exponential backoff.
    
    Args:
        max_retries: Максимальное количество попыток
        backoff_factor: Базовый множитель для задержки между попытками
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor * (2 ** attempt)
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                except Exception as e:
                    # Для других исключений не делаем retry
                    raise
            # Если все попытки исчерпаны
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


def get_models():
    """Получает список доступных моделей из API."""
    try:
        response = requests.get(f"{API_URL}/api/models", timeout=5)
        if response.status_code == 200:
            return response.json()
        return {"models": [], "current_model": None}
    except Exception as e:
        return {"models": [], "current_model": None}


@retry_request(max_retries=3, backoff_factor=1.0)
def process_query(query: str, model_alias: str = None):
    """Отправляет запрос в API и возвращает результат."""
    payload = {"query": query}
    if model_alias:
        payload["model_alias"] = model_alias
    
    response = requests.post(
        f"{API_URL}/api/query",
        json=payload,
        timeout=60
    )
    
    # Обрабатываем ошибки более детально
    if response.status_code != 200:
            try:
                error_data = response.json()
                error_detail = error_data.get("detail", {})
                if isinstance(error_detail, dict):
                    error_msg = error_detail.get("error", str(error_detail))
                    trace = error_detail.get("trace", [])
                    return {
                        "error": error_msg,
                        "trace": trace,
                        "response": None
                    }
                else:
                    return {
                        "error": str(error_detail),
                        "trace": [],
                        "response": None
                    }
            except:
                return {
                    "error": f"HTTP {response.status_code}: {response.text[:200]}",
                    "trace": [],
                    "response": None
                }
    
    return response.json()


def validate_api_response(data: Dict[str, Any]) -> bool:
    """
    Валидирует структуру ответа API.
    
    Args:
        data: Данные ответа от API
        
    Returns:
        True если структура корректна, False иначе
    """
    if not isinstance(data, dict):
        return False
    
    # Проверяем наличие обязательных полей для успешного ответа
    if "error" not in data:
        # Успешный ответ должен содержать response и trace
        if "response" not in data:
            return False
        if "trace" not in data:
            return False
        if not isinstance(data.get("trace"), list):
            return False
    else:
        # Ответ с ошибкой должен содержать error и trace
        if "trace" not in data:
            return False
        if not isinstance(data.get("trace"), list):
            return False
    
    return True


def process_query_with_error_handling(query: str, model_alias: str = None):
    """
    Обертка для process_query с обработкой ошибок retry и валидацией ответа.
    
    Retry механизм обрабатывает только Timeout и ConnectionError,
    остальные ошибки возвращаются как есть.
    Валидация проверяет структуру ответа перед возвратом.
    """
    try:
        result = process_query(query, model_alias)
        
        # Валидация ответа API
        if not validate_api_response(result):
            return {
                "error": "Получен некорректный формат ответа от сервера",
                "trace": [],
                "response": None
            }
        
        return result
    except requests.exceptions.Timeout:
        return {
            "error": "Превышено время ожидания ответа от сервера после нескольких попыток",
            "trace": [],
            "response": None
        }
    except requests.exceptions.ConnectionError:
        return {
            "error": "Не удалось подключиться к серверу после нескольких попыток. Проверьте, что AI Agent запущен.",
            "trace": [],
            "response": None
        }
    except requests.exceptions.RequestException as e:
        return {
            "error": f"Ошибка при отправке запроса: {str(e)}",
            "trace": [],
            "response": None
        }
    except Exception as e:
        return {
            "error": f"Неожиданная ошибка: {str(e)}",
            "trace": [],
            "response": None
        }


def render_trace_entry(entry: Dict[str, Any]):
    """Отрисовывает одну запись trace в точном соответствии с мокапом."""
    entry_type = entry.get("type", "info")
    content = entry.get("content", "")
    status = entry.get("status", "")
    tool_name = entry.get("tool_name", "")
    
    # Определяем иконку и цвет согласно мокапу (точное соответствие описанию)
    if entry_type == "thought":
        icon = "💡"  # Голубая иконка мысли
        css_class = "trace-thought"
        label = "Thought"
        border_color = "#00BFFF"  # Голубая граница
    elif entry_type == "tool_call":
        if status == "success":
            icon = "✓"  # Зеленая галочка для успеха
            css_class = "trace-success"
            border_color = "#00ff00"  # Зеленая граница
        else:
            icon = "✗"  # Красный крестик для ошибки
            css_class = "trace-error"
            border_color = "#ff0000"  # Красная граница
        label = "Tool Call"
    elif entry_type == "observation":
        icon = "✓"  # Зеленая галочка
        css_class = "trace-success"
        label = "Observation"
        border_color = "#00ff00"  # Зеленая граница
    elif entry_type == "error":
        icon = "✗"  # Красный крестик
        css_class = "trace-error"
        label = "Error"
        border_color = "#ff0000"  # Красная граница
    else:
        icon = "ℹ️"
        css_class = "trace-block"
        label = entry_type.upper()
        border_color = "#00BFFF"
    
    # Формируем текст (точно как в мокапе)
    display_text = content
    if tool_name and entry_type == "tool_call":
        display_text = f"Calling tool: {tool_name}\n{content}"
    
    # Отрисовываем блок в точном соответствии с мокапом
    # Фон: #1a1a2e, граница: 3px, padding: 1rem, margin: 0.5rem, моноширинный шрифт 0.9rem
    st.markdown(
        f"""
        <div style="background-color: #1a1a2e; border-left: 3px solid {border_color}; padding: 1rem; margin: 0.5rem 0; border-radius: 5px; font-family: 'Courier New', monospace; font-size: 0.9rem;">
            <strong style="color: #00BFFF;">{label}:</strong> {icon}<br>
            <span style="color: #ffffff; white-space: pre-wrap;">{display_text}</span>
        </div>
        """,
        unsafe_allow_html=True
    )


# БОКОВАЯ ПАНЕЛЬ
with st.sidebar:
    # EZDEL TECH логотип
    st.markdown(
        '<div class="ezdel-tech">EZDEL TECH</div>',
        unsafe_allow_html=True
    )
    
    st.markdown("---")
    
    # Заголовок "Select LLM Model"
    st.markdown(
        '<div class="model-selector-title">Select LLM Model</div>',
        unsafe_allow_html=True
    )
    
    # Получаем модели
    models_data = get_models()
    models = models_data.get("models", [])
    current_model = models_data.get("current_model", "")
    
    if models:
        # Формируем список для selectbox с иконками
        model_options = []
        model_aliases = []
        
        for model in models:
            icon = model.get("icon", "🤖")
            alias = model.get("alias", "Unknown")
            model_options.append(f"{icon} {alias}")
            model_aliases.append(alias)
        
        # Находим текущую выбранную модель
        selected_index = 0
        for i, model in enumerate(models):
            if model.get("model") == current_model:
                selected_index = i
                break
        
        # Dropdown для выбора модели
        selected_model_display = st.selectbox(
            "Выберите модель:",
            model_options,
            index=selected_index,
            label_visibility="collapsed",
            key="model_selector"
        )
        
        # Извлекаем алиас из выбранной модели
        if " " in selected_model_display:
            selected_alias = selected_model_display.split(" ", 1)[1]
        else:
            selected_alias = model_aliases[selected_index] if selected_index < len(model_aliases) else None
        
        st.markdown("---")
        
        # Placeholder button - темное серое поле (поле ввода в sidebar)
        st.markdown(
            '<div class="placeholder-button"></div>',
            unsafe_allow_html=True
        )
        
        st.markdown("---")
        
        # Ссылка "For settings"
        st.markdown(
            '<div class="settings-link"><a href="#" style="color: #00BFFF; text-decoration: none;">For settings</a></div>',
            unsafe_allow_html=True
        )
    else:
        st.warning("Не удалось загрузить список моделей")
        selected_alias = None

# ОСНОВНАЯ ОБЛАСТЬ
# Заголовок "MCP Cloud.ru" (подтверждено пользователем)
st.markdown(
    '<h1 class="main-title">MCP Cloud.ru</h1>',
    unsafe_allow_html=True
)

# Поле ввода запроса и кнопка Analyze
col1, col2 = st.columns([4, 1])

with col1:
    user_query = st.text_input(
        "Enter your query...",
        key="query_input",
        label_visibility="collapsed",
        placeholder="Enter your query..."
    )

with col2:
    analyze_button = st.button("Analyze", type="primary", use_container_width=True)

# Область для статуса загрузки
status_placeholder = st.empty()

# Обработка запроса
if analyze_button and user_query:
    # Показываем статус загрузки
    with status_placeholder.container():
        st.markdown(
            """
            <div style="text-align: center; padding: 1.5rem;">
                <p style="color: #00BFFF; font-size: 1.2rem; text-shadow: 0 0 10px #00BFFF;">
                    AI Agent is thinking...
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        spinner = st.spinner("Processing...")
    
    with spinner:
        # Отправляем запрос (с retry механизмом)
        result = process_query_with_error_handling(user_query, selected_alias if selected_alias else None)
    
    # Очищаем статус
    status_placeholder.empty()
    
    if result:
        # Проверяем наличие ошибки
        if result.get("error"):
            # Добавляем в историю даже ошибки
            st.session_state.history.append({
                "user_query": user_query,
                "ai_response": result
            })
        else:
            # Добавляем успешный ответ в историю
            st.session_state.history.append({
                "user_query": user_query,
                "ai_response": result
            })
    else:
        # Добавляем ошибку в историю
        error_result = {
            "error": "Не удалось получить ответ от AI Agent",
            "trace": [],
            "response": None
        }
        st.session_state.history.append({
            "user_query": user_query,
            "ai_response": error_result
        })
    
    # После добавления в историю, перезагружаем страницу для отображения обновленной истории
    st.rerun()

# Отображение истории разговора (в стиле мокапа - без заголовка, сразу trace log)
if st.session_state.history:
    for idx, turn in enumerate(st.session_state.history):
        user_query = turn.get("user_query", "")
        ai_response = turn.get("ai_response", {})
        
        # Отображаем trace log сразу (как в мокапе - без заголовка "User Query")
        # Проверяем наличие ошибки
        if ai_response.get("error"):
            # Отображаем trace, если есть
            trace = ai_response.get("trace", [])
            if trace:
                for entry in trace:
                    render_trace_entry(entry)
            
            # Отображаем ошибку
            st.error(f"❌ {ai_response.get('error')}")
        else:
            # Отображаем trace log (как в мокапе - последовательно, без дополнительных заголовков)
            trace = ai_response.get("trace", [])
            if trace:
                for entry in trace:
                    render_trace_entry(entry)
            
            # Отображаем финальный ответ
            response_text = ai_response.get("response", "No response")
            model_used = ai_response.get("model_used", "Unknown")
            
            if response_text and response_text != "No response":
                # Отображаем финальный ответ AI
                st.markdown(
                    f"""
                    <div style="background-color: #1a1a2e; padding: 1.5rem; border-radius: 5px; margin-top: 1rem; border-left: 4px solid #00ff00;">
                        <h3 style="color: #00BFFF; margin-top: 0;">🤖 Response</h3>
                        <div style="color: #ffffff; white-space: pre-wrap;">{response_text}</div>
                        <p style="color: #888; font-style: italic; margin-top: 1rem; margin-bottom: 0;">Model used: {model_used}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# Информационное окно
st.markdown(
    """
    <div class="info-box">
        <span class="info-icon">ℹ️</span>
        <strong>MCP Cloud.ru</strong> - AI-ассистент для анализа репозиториев GitHub на базе Model Context Protocol и Cloud.ru Evolution Foundation Models. 
        Используйте естественный язык для запросов о репозиториях, их метриках и анализе.
    </div>
    """,
    unsafe_allow_html=True
)

# Декоративный элемент в правом нижнем углу (как в мокапе)
st.markdown(
    """
    <div class="decorative-element"></div>
    """,
    unsafe_allow_html=True
)
