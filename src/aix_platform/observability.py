from __future__ import annotations

import logging
import sys
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, make_asgi_app
import structlog

from .config import Settings


REQUESTS = Counter(
    "aix_http_requests_total",
    "HTTP requests processed by the AIx API",
    ("method", "route", "status"),
)
LATENCY = Histogram(
    "aix_http_request_duration_seconds",
    "HTTP request latency for the AIx API",
    ("method", "route"),
)


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def install_observability(app: FastAPI, settings: Settings) -> None:
    configure_logging(settings)
    logger = structlog.get_logger("aix.api")

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            duration = time.perf_counter() - started
            REQUESTS.labels(request.method, route_path, str(status_code)).inc()
            LATENCY.labels(request.method, route_path).observe(duration)
            logger.info(
                "http_request",
                request_id=request_id,
                method=request.method,
                route=route_path,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
            )

    app.mount("/metrics", make_asgi_app())

    if settings.otlp_endpoint:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from .database import engine

        provider = TracerProvider(
            resource=Resource.create({"service.name": "aix-platform-api"})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine)
