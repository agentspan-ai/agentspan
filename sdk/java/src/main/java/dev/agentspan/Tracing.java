// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

/**
 * OpenTelemetry tracing utilities.
 *
 * <p>Tracing only activates if {@code opentelemetry-api} is on the classpath.
 * Otherwise all operations are no-ops.
 *
 * <pre>{@code
 * if (Tracing.isTracingEnabled()) {
 *     System.out.println("OpenTelemetry tracing is active");
 * }
 * }</pre>
 */
public class Tracing {

    private static final boolean HAS_OTEL;

    static {
        boolean detected = false;
        try {
            Class.forName("io.opentelemetry.api.trace.Tracer");
            detected = true;
        } catch (ClassNotFoundException ignored) {}
        HAS_OTEL = detected;
    }

    private Tracing() {}

    /** Returns {@code true} if OpenTelemetry is available and configured on the classpath. */
    public static boolean isTracingEnabled() {
        return HAS_OTEL;
    }
}
