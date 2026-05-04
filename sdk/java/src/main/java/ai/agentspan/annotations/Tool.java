// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a method as an agent tool.
 *
 * <p>Use this annotation on methods in a class to register them as callable tools
 * for an agent. Use {@link ai.agentspan.internal.ToolRegistry#fromInstance(Object)}
 * to discover all annotated methods.
 *
 * <p>Example:
 * <pre>{@code
 * public class WeatherTools {
 *     @Tool(name = "get_weather", description = "Get weather for a city")
 *     public String getWeather(String city) {
 *         return "Sunny, 72F in " + city;
 *     }
 * }
 * }</pre>
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Tool {
    /** Tool name. Defaults to method name if not specified. */
    String name() default "";

    /** Human-readable description of what the tool does. */
    String description() default "";

    /** If true, the tool requires human approval before execution. */
    boolean approvalRequired() default false;

    /** If true, the tool is served externally (not by this SDK). */
    boolean external() default false;

    /** Maximum execution time in seconds. 0 means no explicit timeout (server default applies). */
    int timeoutSeconds() default 0;

    /** Credential environment variable names required by this tool. */
    String[] credentials() default {};
}
