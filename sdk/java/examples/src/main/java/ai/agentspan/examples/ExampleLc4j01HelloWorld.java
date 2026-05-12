// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Lc4j 01 — Hello World
 *
 * <p>Java port of <code>sdk/python/examples/langchain/01_hello_world.py</code>.
 * Simplest LangChain4j-style agent with no tools — Agentspan extracts the model
 * and instructions and runs the LLM loop server-side.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Using {@link LangChain4jAgent#from} (extraction mode) — closest analog
 *       to Python's <code>create_agent(llm, tools=[])</code></li>
 *   <li>Running an agent with {@link Agentspan#run}</li>
 *   <li>Basic LLM conversation without any tools</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>{@code AGENTSPAN_LLM_MODEL=openai/gpt-4o} (or any provider supported by the server)</li>
 *   <li>OpenAI/provider key configured in server credentials</li>
 * </ul>
 */
public class ExampleLc4j01HelloWorld {

    public static void main(String[] args) {
        // No tool POJO, no system prompt — matches Python's
        // create_agent(llm, tools=[], name=...) which sends no system message.
        Agent agent = LangChain4jAgent.from(
            "hello_world_agent",
            Settings.LLM_MODEL,
            null
        );

        AgentResult result = Agentspan.run(
            agent,
            "Say hello and tell me a fun fact about Python programming."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
