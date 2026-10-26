"""OpenTelemetry tracing.

Every API request, LLM call, triage, retrieval and graph step becomes a span. Spans are always
kept in SQLite (GET /traces shows the latest requests as a tree) and, if OTLP_ENDPOINT is set,
also exported to any OpenTelemetry backend (Jaeger, Grafana Tempo, Langfuse ...).

Privacy: span attributes hold ids, model names, counts, token usage and timings, never mail
text, because traces are often shipped to other systems.
"""
import json
import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (BatchSpanProcessor, SimpleSpanProcessor, SpanExporter,
                                            SpanExportResult)

from app import db
from app.config import settings

log = logging.getLogger("mailpilot.tracing")
OUR_SCOPES = ("mailpilot", "opentelemetry.instrumentation.fastapi")
tracer = trace.get_tracer("mailpilot")
_provider: TracerProvider | None = None


class SQLiteSpanExporter(SpanExporter):
    """Stores our own spans (not those of libraries such as Chroma) for GET /traces."""

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        rows = []
        for s in spans:
            scope = s.instrumentation_scope.name if s.instrumentation_scope else ""
            if not scope.startswith(OUR_SCOPES):
                continue
            rows.append((
                format(s.context.trace_id, "032x"), format(s.context.span_id, "016x"),
                format(s.parent.span_id, "016x") if s.parent else None, s.name,
                s.start_time, (s.end_time - s.start_time) / 1e6 if s.end_time else 0.0,
                s.status.status_code.name,
                json.dumps({k: v for k, v in (s.attributes or {}).items()}, default=str),
            ))
        try:
            db.save_spans(rows)
        except Exception as e:  # tracing must never break the app
            log.warning("could not store spans: %s", e)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def setup_tracing(app=None) -> None:
    """Install the tracer provider once per process; instrument the FastAPI app if given."""
    global _provider
    if _provider is None:
        _provider = TracerProvider(resource=Resource.create({"service.name": "mailpilot"}))
        _provider.add_span_processor(SimpleSpanProcessor(SQLiteSpanExporter()))
        if settings.otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)))
        trace.set_tracer_provider(_provider)
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app, tracer_provider=_provider,
                                           excluded_urls="health,metrics,traces,triage/status")


def span(name: str, **attributes):
    """Context manager for a span: `with span("triage", mail_id=m.id) as s: s.set_attribute(...)`."""
    return tracer.start_as_current_span(
        name, attributes={k: v for k, v in attributes.items() if v is not None})
