"""MCP сервер для анализа активности репозиториев GitHub."""

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
PORT = int(os.getenv("PORT", "8002"))
HOST = os.getenv("HOST", "0.0.0.0")

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)


# Инициализация трейсинга
def init_tracing():
    """Инициализация OpenTelemetry для трейсинга."""
    pass


init_tracing()

# Импортируем инструменты
from tools.commit_statistics import get_commit_statistics
from tools.developer_activity import get_developer_activity
from tools.branch_analysis import get_branch_analysis


def main():
    """Запуск MCP сервера с HTTP транспортом."""
    print("=" * 60)
    print("🌐 ЗАПУСК MCP СЕРВЕРА")
    print("=" * 60)
    print(f"🚀 MCP Server: http://{HOST}:{PORT}/mcp")
    print(f"📊 Сервер: GitHub Activity Analytics")
    print(f"🔧 Инструменты:")
    print(f"   - get_commit_statistics")
    print(f"   - get_developer_activity")
    print(f"   - get_branch_analysis")
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

