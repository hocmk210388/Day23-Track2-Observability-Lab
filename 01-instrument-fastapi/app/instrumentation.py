"""Prometheus + OTel + structlog wiring.

Single source of truth for the metric/span/log namespace.
"""
from __future__ import annotations

import logging
import os
import sys

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

# ── Prometheus metrics ────────────────────────────────────────
INFERENCE_REQUESTS = Counter(
    "inference_requests_total",
    "Total inference requests",
    ["model", "status"],
)
INFERENCE_LATENCY = Histogram(
    "inference_latency_seconds",
    "Inference end-to-end latency",
    ["model"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)
INFERENCE_ACTIVE = Gauge(
    "inference_active_gauge",
    "In-flight inference requests",
)
INFERENCE_TOKENS = Counter(
    "inference_tokens_total",
    "Tokens processed (input/output)",
    ["model", "direction"],
)
INFERENCE_QUALITY = Gauge(
    "inference_quality_score",
    "Latest eval-as-metric quality score [0,1]",
    ["model"],
)
GPU_UTIL = Gauge(
    "gpu_utilization_percent",
    "Simulated GPU utilization [0,100]",
)

_otel_configured = False


def get_tracer() -> trace.Tracer:
    """Always resolve from the global provider (call after ``setup_otel``).

    ``from instrumentation import tracer`` binds once at import time and does
    *not* update when ``setup_otel`` replaces the provider, which breaks nesting
    with FastAPI auto-instrumentation spans.
    """
    return trace.get_tracer(__name__)


def setup_otel(app: object) -> None:
    """Configure OTLP trace export + FastAPI auto-instrumentation.

    ``app`` must be the FastAPI instance so ``POST /predict`` server spans
    share the same trace context as manual spans (``instrument()`` without
    ``app`` often does not attach middleware to your app).

    Call once after all routes are registered and **before** the ASGI server
    starts accepting traffic — not from ``lifespan``, because
    ``instrument_app`` uses ``add_middleware``, which Starlette forbids after
    startup.
    """
    global _otel_configured
    if _otel_configured:
        return
    _otel_configured = True

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "inference-api"),
            "service.namespace": "aicb",
            "deployment.environment": os.getenv(
                "DEPLOY_ENV",
                "lab",
            ),
        }
    )
    provider = TracerProvider(resource=resource)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor().instrument_app(app)
    _configure_logging()


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=os.getenv("LOG_LEVEL", "INFO"),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def bind_log(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
