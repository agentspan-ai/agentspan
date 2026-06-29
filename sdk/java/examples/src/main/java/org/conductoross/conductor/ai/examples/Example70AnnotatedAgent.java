// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.annotations.AgentDef;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.model.AgentResult;

/**
 * Example 70 — Annotated Agent
 *
 * <p>Demonstrates defining an agent declaratively with the {@code @AgentDef} method
 * annotation (the Java counterpart of the Python SDK's {@code @agent} decorator).
 * The method body returns the agent's instructions; {@code @Tool} methods on the
 * same class are attached automatically.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o</li>
 * </ul>
 */
public class Example70AnnotatedAgent {

    @Tool(name = "get_weather", description = "Get the current weather for a city")
    public String getWeather(String city) {
        return "Sunny, 72F in " + city;
    }

    @AgentDef(model = "openai/gpt-4o")
    public String weatherbot() {
        return "You are a weather assistant. Use the get_weather tool to answer questions.";
    }

    public static void main(String[] args) {
        AgentRuntime runtime = new AgentRuntime();
        Agent agent = Agent.fromInstance(new Example70AnnotatedAgent(), "weatherbot");

        AgentResult result = runtime.run(agent, "What's the weather in Paris?");
        result.printResult();

        runtime.shutdown();
    }
}
