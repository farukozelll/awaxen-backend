"""
Prometheus Metrics - Application Monitoring

Exposes metrics at /metrics endpoint for Prometheus scraping.
"""
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse
import time

from src.core.config import settings

# === Application Info ===
APP_INFO = Info("awaxen_app", "Awaxen application info")
APP_INFO.info({
    "version": settings.app_version,
    "environment": settings.environment,
})

# === Request Metrics ===
REQUEST_COUNT = Counter(
    "awaxen_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "awaxen_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# === Business Metrics ===
ACTIVE_GATEWAYS = Gauge(
    "awaxen_active_gateways",
    "Number of active gateways",
)

ACTIVE_DEVICES = Gauge(
    "awaxen_active_devices",
    "Number of active devices",
)

RECOMMENDATIONS_CREATED = Counter(
    "awaxen_recommendations_created_total",
    "Total recommendations created",
    ["reason"],
)

COMMANDS_SENT = Counter(
    "awaxen_commands_sent_total",
    "Total commands sent to devices",
    ["action", "status"],
)

TELEMETRY_RECEIVED = Counter(
    "awaxen_telemetry_received_total",
    "Total telemetry data points received",
    ["device_type"],
)

ALARMS_CREATED = Counter(
    "awaxen_alarms_created_total",
    "Total alarms created",
    ["severity"],
)

AWX_REWARDS_GIVEN = Counter(
    "awaxen_awx_rewards_total",
    "Total AWX rewards given",
    ["event_type"],
)

# === SSE Metrics ===
SSE_CONNECTIONS = Gauge(
    "awaxen_sse_connections",
    "Active SSE connections",
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect request metrics."""
    
    async def dispatch(self, request: Request, call_next) -> StarletteResponse:
        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)
        
        # Get endpoint pattern (not the actual path with IDs)
        endpoint = request.url.path
        method = request.method
        
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Record metrics
        REQUEST_COUNT.labels(
            method=method,
            endpoint=endpoint,
            status_code=response.status_code,
        ).inc()
        
        REQUEST_LATENCY.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)
        
        return response


# === Metrics Router ===
router = APIRouter(tags=["Health"])


@router.get("/metrics", include_in_schema=False)
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Scrape this endpoint with Prometheus:
    ```yaml
    scrape_configs:
      - job_name: 'awaxen-backend'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/metrics'
    ```
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# === Helper Functions ===

def record_recommendation(reason: str) -> None:
    """Record a recommendation creation."""
    RECOMMENDATIONS_CREATED.labels(reason=reason).inc()


def record_command(action: str, status: str) -> None:
    """Record a command sent."""
    COMMANDS_SENT.labels(action=action, status=status).inc()


def record_telemetry(device_type: str) -> None:
    """Record telemetry received."""
    TELEMETRY_RECEIVED.labels(device_type=device_type).inc()


def record_alarm(severity: str) -> None:
    """Record alarm creation."""
    ALARMS_CREATED.labels(severity=severity).inc()


def record_reward(event_type: str, amount: int = 1) -> None:
    """Record AWX reward."""
    AWX_REWARDS_GIVEN.labels(event_type=event_type).inc(amount)


def update_gateway_count(count: int) -> None:
    """Update active gateway count."""
    ACTIVE_GATEWAYS.set(count)


def update_device_count(count: int) -> None:
    """Update active device count."""
    ACTIVE_DEVICES.set(count)


def sse_connection_opened() -> None:
    """Record SSE connection opened."""
    SSE_CONNECTIONS.inc()


def sse_connection_closed() -> None:
    """Record SSE connection closed."""
    SSE_CONNECTIONS.dec()
