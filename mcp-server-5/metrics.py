"""Prometheus метрики для MCP Server 3."""

from prometheus_client import Counter, Histogram, Gauge, start_http_server
import os

# Метрики для инструментов
TOOL_CALLS_TOTAL = Counter(
    "mcp_tool_calls_total",
    "Total number of tool calls",
    ["tool_name", "status"]
)

TOOL_DURATION_SECONDS = Histogram(
    "mcp_tool_duration_seconds",
    "Duration of tool execution in seconds",
    ["tool_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

GITHUB_API_CALLS_TOTAL = Counter(
    "github_api_calls_total",
    "Total number of GitHub API calls",
    ["endpoint", "status_code"]
)

GITHUB_API_DURATION_SECONDS = Histogram(
    "github_api_duration_seconds",
    "Duration of GitHub API calls in seconds",
    ["endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Метрики для активных запросов
ACTIVE_REQUESTS = Gauge(
    "mcp_active_requests",
    "Number of active requests being processed",
    ["tool_name"]
)

# Метрики для ошибок
ERRORS_TOTAL = Counter(
    "mcp_errors_total",
    "Total number of errors",
    ["tool_name", "error_type"]
)


def start_metrics_server(port: int = None):
    """
    Запускает HTTP сервер для экспорта Prometheus метрик.
    
    Args:
        port: Порт для метрик (по умолчанию: PORT + 1000)
    """
    if port is None:
        base_port = int(os.getenv("PORT", "8004"))
        port = base_port + 1000
    
    try:
        start_http_server(port)
        print(f"📊 Prometheus metrics server started on port {port}")
        print(f"   Metrics endpoint: http://0.0.0.0:{port}/metrics")
    except OSError as e:
        print(f"⚠️  Could not start metrics server on port {port}: {e}")

