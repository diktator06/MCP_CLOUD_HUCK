"""MCP сервер для анализа webhooks и событий репозиториев GitHub."""

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
PORT = int(os.getenv("PORT", "8006"))
HOST = os.getenv("HOST", "0.0.0.0")

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)


# Инициализация трейсинга
def init_tracing():
    """Инициализация OpenTelemetry для трейсинга."""
    pass


init_tracing()

# Импортируем инструменты
from tools.webhooks_list import get_repository_webhooks
from tools.events_analysis import analyze_repository_events
from tools.activity_timeline import get_activity_timeline


def main():
    """Запуск MCP сервера с HTTP транспортом."""
    print("=" * 60)
    print("🌐 ЗАПУСК MCP СЕРВЕРА")
    print("=" * 60)
    print(f"🚀 MCP Server: http://{HOST}:{PORT}/mcp")
    print(f"📊 Сервер: GitHub Webhooks & Events")
    print(f"🔧 Инструменты:")
    print(f"   - get_repository_webhooks")
    print(f"   - analyze_repository_events")
    print(f"   - get_activity_timeline")
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

