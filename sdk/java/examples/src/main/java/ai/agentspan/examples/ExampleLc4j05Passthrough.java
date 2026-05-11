// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.service.AiServices;

/**
 * Example Lc4j 05 — LangChain4j passthrough mode.
 *
 * <p>Demonstrates wrapping a fully-formed LangChain4j {@code AiServices} agent
 * (with its own {@link OpenAiChatModel} + tools) so that Agentspan orchestrates
 * it as a single Conductor worker — without extracting its model or tools
 * server-side.
 *
 * <p>How the loop runs in passthrough mode:
 * <ul>
 *   <li><b>LangChain4j runs client-side.</b> The {@code AiServices}-built
 *       {@code Assistant} interface drives its own tool-call loop against
 *       OpenAI using your {@code OPENAI_API_KEY}. Agentspan never sees the
 *       model name or your tools.</li>
 *   <li><b>Agentspan orchestrates one worker task.</b> The compiled workflow
 *       has exactly one worker (no {@code LLM_CHAT_COMPLETE} tasks). That
 *       worker is polled by the SDK, which calls {@code assistant.chat(prompt)}
 *       and ships the answer back to the server.</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>{@code OPENAI_API_KEY} exported — the LangChain4j model needs it
 *       client-side. Without it the OpenAiChatModel build will fail.</li>
 *   <li>langchain4j + langchain4j-open-ai on the classpath
 *       (see examples/build.gradle)</li>
 * </ul>
 */
public class ExampleLc4j05Passthrough {

    // ── LangChain4j tool class — unchanged from any existing codebase ─────────

    static class CalculatorTools {
        @Tool(name = "add", value = "Add two numbers")
        public double add(double a, double b) { return a + b; }

        @Tool(name = "multiply", value = "Multiply two numbers")
        public double multiply(double a, double b) { return a * b; }
    }

    // ── Plain AiServices interface — LangChain4j synthesises the impl ─────────

    interface Assistant {
        String chat(String userMessage);
    }

    public static void main(String[] args) {
        // 1) Build a LangChain4j ChatModel client-side. This object holds your
        //    OpenAI key and is never sent to Agentspan.
        OpenAiChatModel model = OpenAiChatModel.builder()
                .apiKey(System.getenv("OPENAI_API_KEY"))
                .modelName("gpt-4o")
                .build();

        // 2) Build the LangChain4j AiServices agent. LangChain4j will drive
        //    the tool-call loop client-side using `model` + `CalculatorTools`.
        Assistant assistant = AiServices.builder(Assistant.class)
                .chatModel(model)
                .tools(new CalculatorTools())
                .build();

        // 3) Bridge into Agentspan via passthrough. The Agentspan workflow will
        //    have exactly one worker task — when scheduled, the SDK invokes the
        //    lambda which delegates to assistant.chat(...). LangChain4j handles
        //    everything else (planning, tool invocation, final answer).
        Agent agent = LangChain4jAgent.passthrough(
                "lc4j_passthrough_05",
                prompt -> assistant.chat(prompt)
        );

        System.out.println("Agent: " + agent.getName());
        System.out.println("Framework: " + agent.getFramework());
        System.out.println("Tools (workers wrapping the LangChain4j agent): "
                + agent.getTools().size());

        // 4) Run it. The server schedules just the passthrough worker; no
        //    server-side LLM call is made.
        AgentResult result = Agentspan.run(agent, "What is 7 + 8, then multiply that by 3?");
        result.printResult();

        Agentspan.shutdown();
    }
}
