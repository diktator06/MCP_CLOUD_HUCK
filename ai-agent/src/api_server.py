"""FastAPI сервер для AI агента с поддержкой trace output."""

import os
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv
from structured_logging import get_logger

# Загрузка переменных окружения
load_dotenv(find_dotenv())

import sys

# Добавляем путь к модулям
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from a2a_wrapper import create_mcp_tools
from agent import AgentWithModelSwitch, ModelManager

# Инициализация structured logger
logger = get_logger("ai-agent")

app = FastAPI(title="GitHub AI Analyst API", version="1.0.0")

# CORS middleware для работы с фронтендом
# Исправлено: указаны конкретные домены вместо "*" для безопасности
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://frontend:8501",
        "http://127.0.0.1:8501",
        # Добавить production домены при необходимости
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный экземпляр агента
agent_wrapper: Optional[AgentWithModelSwitch] = None
trace_log: List[Dict[str, Any]] = []


class QueryRequest(BaseModel):
    """Модель запроса для API."""
    query: str
    model_alias: Optional[str] = None


class TraceEntry(BaseModel):
    """Модель записи trace."""
    type: str  # "thought", "tool_call", "observation", "error"
    content: str
    status: Optional[str] = None  # "success", "error", "pending"
    tool_name: Optional[str] = None


class QueryResponse(BaseModel):
    """Модель ответа API."""
    response: str
    trace: List[TraceEntry]
    model_used: str


def log_trace(entry_type: str, content: str, status: Optional[str] = None, tool_name: Optional[str] = None):
    """Добавляет запись в trace лог."""
    trace_log.append({
        "type": entry_type,
        "content": content,
        "status": status,
        "tool_name": tool_name
    })


def clear_trace():
    """Очищает trace лог."""
    trace_log.clear()


@app.on_event("startup")
async def startup_event():
    """Инициализация агента при запуске сервера."""
    global agent_wrapper
    try:
        tools = create_mcp_tools()
        agent_wrapper = AgentWithModelSwitch(tools)
        logger.info(
            "AI Agent initialized successfully",
            tools_count=len(tools),
            current_model=agent_wrapper.get_current_model()
        )
    except Exception as e:
        logger.error(
            "Failed to initialize AI Agent",
            error=str(e),
            error_type=type(e).__name__
        )
        raise


@app.get("/")
async def root():
    """Корневой endpoint."""
    return {
        "service": "GitHub AI Analyst API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """
    Healthcheck endpoint для Docker и мониторинга.
    
    Returns:
        dict: Статус здоровья сервиса
    """
    return {
        "status": "healthy",
        "agent_initialized": agent_wrapper is not None,
        "service": "GitHub AI Analyst API",
        "version": "1.0.0"
    }


@app.get("/api/models")
async def get_models():
    """Возвращает список доступных моделей."""
    manager = ModelManager()
    aliases = manager.get_available_aliases()
    
    # Основные модели с иконками
    model_list = []
    icon_map = {
        "GigaChat": "📧",
        "Sage": "🧠",
        "MiniMax": "⚡",
        "GLM": "📍",
        "GPT-OSS": "🤖",
        "Qwen-Coder": "💻",
        "Qwen-Large": "📊",
        "Qwen-Next": "🚀",
        "T-Lite-1.0": "⚙️",
        "T-Pro-1.0": "👤",
        "T-Pro-2.0": "📷"
    }
    
    primary_aliases = [
        "GigaChat", "Sage", "MiniMax", "GLM", "GPT-OSS",
        "Qwen-Coder", "Qwen-Large", "Qwen-Next",
        "T-Lite-1.0", "T-Pro-1.0", "T-Pro-2.0"
    ]
    
    for alias in primary_aliases:
        if alias in manager.MODEL_ALIASES:
            model_list.append({
                "alias": alias,
                "model": manager.MODEL_ALIASES[alias],
                "icon": icon_map.get(alias, "📄")
            })
    
    return {
        "models": model_list,
        "current_model": agent_wrapper.get_current_model() if agent_wrapper else None
    }


@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Обрабатывает запрос пользователя через AI Agent.
    
    Args:
        request: Запрос с текстом и опциональным алиасом модели
        
    Returns:
        Ответ агента с trace логом
    """
    global agent_wrapper
    
    logger.info(
        "Received query request",
        query_length=len(request.query),
        model_alias=request.model_alias
    )
    
    if agent_wrapper is None:
        logger.error("AI Agent not initialized when processing query")
        raise HTTPException(status_code=500, detail="AI Agent not initialized")
    
    # Очищаем предыдущий trace
    clear_trace()
    
    # Переключаем модель, если указан алиас
    if request.model_alias:
        success, message = agent_wrapper.switch_model(request.model_alias)
        if success:
            logger.info(f"Model switched successfully: {message}", model_alias=request.model_alias)
        # Если модель уже активна или другая ошибка - просто игнорируем, не логируем
    
    current_model = agent_wrapper.get_current_model()
    log_trace("thought", f"Processing query: {request.query}")
    
    try:
        # Выполняем запрос через агента
        log_trace("thought", f"Analyzing query: {request.query}")
        log_trace("thought", "Selecting appropriate tools for the query...")
        
        # Выполняем запрос с обработкой ошибок валидации
        try:
            result = await agent_wrapper.agent.ainvoke({
                "input": request.query
            })
        except Exception as agent_error:
            # Обрабатываем ошибки валидации схемы
            error_str = str(agent_error)
            if "422" in error_str or "Type properties" in error_str or "args.items.type" in error_str:
                log_trace("error", f"Schema validation error: {error_str}", "error")
                # Пытаемся ответить без использования инструментов
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(
                    api_key=os.getenv("API_KEY"),
                    base_url=os.getenv("BASE_URL", "https://foundation-models.api.cloud.ru/v1"),
                    model=current_model,
                    temperature=0.5
                )
                simple_response = await llm.ainvoke(request.query)
                response_text = simple_response.content if hasattr(simple_response, 'content') else str(simple_response)
                log_trace("observation", "Query processed with direct LLM response (tool schema error)", "success")
                
                trace_entries = [
                    TraceEntry(
                        type=entry["type"],
                        content=entry["content"],
                        status=entry.get("status"),
                        tool_name=entry.get("tool_name")
                    )
                    for entry in trace_log
                ]
                
                return QueryResponse(
                    response=response_text,
                    trace=trace_entries,
                    model_used=current_model
                )
            else:
                raise
        
        # Извлекаем ответ
        response_text = result.get("output", "No response generated")
        
        # Извлекаем промежуточные шаги для trace
        intermediate_steps = result.get("intermediate_steps", [])
        for step in intermediate_steps:
            if len(step) >= 2:
                # step[0] - это AgentAction, step[1] - результат
                action = step[0]
                tool_result = step[1]
                
                tool_name = action.tool if hasattr(action, 'tool') else str(action)
                tool_input = action.tool_input if hasattr(action, 'tool_input') else {}
                
                log_trace("tool_call", f"Calling tool: {tool_name} with input: {tool_input}", "success", tool_name)
                log_trace("observation", f"Tool result: {str(tool_result)[:300]}...", "success")
        
        log_trace("observation", "Query processed successfully", "success")
        
        logger.info(
            "Query processed successfully",
            model=current_model,
            response_length=len(response_text),
            trace_entries_count=len(trace_log)
        )
        
        # Формируем trace entries
        trace_entries = [
            TraceEntry(
                type=entry["type"],
                content=entry["content"],
                status=entry.get("status"),
                tool_name=entry.get("tool_name")
            )
            for entry in trace_log
        ]
        
        return QueryResponse(
            response=response_text,
            trace=trace_entries,
            model_used=current_model
        )
        
    except Exception as e:
        error_msg = f"Error processing query: {str(e)}"
        logger.error(
            "Error processing query",
            error=str(e),
            error_type=type(e).__name__,
            model=current_model
        )
        log_trace("error", error_msg, "error")
        
        trace_entries = [
            TraceEntry(
                type=entry["type"],
                content=entry["content"],
                status=entry.get("status"),
                tool_name=entry.get("tool_name")
            )
            for entry in trace_log
        ]
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_msg,
                "trace": [e.dict() for e in trace_entries]
            }
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )

