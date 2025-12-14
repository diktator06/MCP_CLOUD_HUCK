"""MCP сервер для мониторинга здоровья репозиториев GitHub."""

# Standard library
import os
from typing import Dict, Any

# Third-party
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv())

from fastmcp import FastMCP, Context
from opentelemetry import trace

# Импортируем единый экземпляр FastMCP
from mcp_instance import mcp
from metrics import start_metrics_server

# Константы
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)


# Инициализация трейсинга
def init_tracing():
    """Инициализация OpenTelemetry для трейсинга."""
    # Базовая инициализация трейсинга
    # При необходимости можно добавить экспортеры (Jaeger, Zipkin и т.д.)
    pass


init_tracing()

# Импортируем инструменты (важно: импорт должен быть после создания mcp)
# Это регистрирует инструменты в экземпляре mcp
from tools.github_health import get_repository_health
from tools.issues_summary import get_repository_issues_summary
from tools.contributors import get_repository_contributors
from tools.contributors import get_repository_contributors


def main():
    """Запуск MCP сервера с HTTP транспортом."""
    print("=" * 60)
    print("🌐 ЗАПУСК MCP СЕРВЕРА")
    print("=" * 60)
    print(f"🚀 MCP Server: http://{HOST}:{PORT}/mcp")
    print(f"📊 Сервер: GitHub Repository Health Monitor")
    print(f"🔧 Инструменты:")
    print(f"   - get_repository_health")
    print(f"   - get_repository_issues_summary")
    print(f"   - get_repository_contributors")
    print(f"📊 Prometheus metrics: http://{HOST}:{PORT + 1000}/metrics")
    print("=" * 60)
    
    # Запускаем Prometheus metrics server
    start_metrics_server()
    
    # Запускаем MCP сервер с streamable-http транспортом
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        stateless_http=True
    )


if __name__ == "__main__":
    main()

