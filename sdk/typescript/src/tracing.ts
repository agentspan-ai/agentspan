/**
 * Check if OpenTelemetry tracing is enabled by looking for
 * OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_SERVICE_NAME env vars.
 */
export function isTracingEnabled(): boolean {
  return (
    typeof process !== "undefined" &&
    process.env != null &&
    (!!process.env.OTEL_EXPORTER_OTLP_ENDPOINT || !!process.env.OTEL_SERVICE_NAME)
  );
}
