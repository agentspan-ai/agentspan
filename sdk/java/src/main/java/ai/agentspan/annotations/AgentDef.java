// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a class as an agent definition.
 *
 * <p>Annotate a class with {@code @AgentDef} to provide metadata for
 * automatic agent discovery and registration.
 *
 * <p>Example:
 * <pre>{@code
 * @AgentDef(name = "weather_agent", model = "openai/gpt-4o",
 *           instructions = "You are a weather assistant.")
 * public class WeatherAgent {
 *     @Tool(description = "Get weather for a city")
 *     public String getWeather(String city) { ... }
 * }
 * }</pre>
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface AgentDef {
    /** Agent name (used as workflow name). */
    String name();

    /** LLM model in "provider/model" format. */
    String model() default "";

    /** System prompt / instructions for the agent. */
    String instructions() default "";
}
