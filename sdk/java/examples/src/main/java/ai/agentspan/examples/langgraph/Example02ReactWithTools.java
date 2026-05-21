// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import org.bsc.langgraph4j.agentexecutor.AgentExecutor;

import java.time.LocalDate;

/**
 * Example LangGraph 02 — ReAct Agent with Tools using native LangGraph4j SDK.
 *
 * <p>Java port (concepts) of
 * <code>sdk/python/examples/langgraph/02_react_with_tools.py</code>. Builds a
 * real LangGraph4j {@code AgentExecutor.Builder} (a ReAct {@code StateGraph})
 * and hands it straight to {@link Agentspan#run} via the drop-in overload.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Defining tools with native {@link Tool @Tool} on a POJO</li>
 *   <li>Passing the tool POJO straight to
 *       {@link Agentspan#run(AgentExecutor.Builder, String, Object...)} via
 *       the drop-in overload — internally LangGraph4j calls
 *       {@code toolsFromObject(...)}</li>
 *   <li>Calculator, word count, and date utilities</li>
 * </ul>
 */
public class Example02ReactWithTools {

    /** Tool POJO. LangGraph4j discovers @Tool methods via reflection. */
    static class UtilityTools {

        @Tool("Add two integers and return the sum.")
        public String add(@P("a") int a, @P("b") int b) {
            return String.valueOf(a + b);
        }

        @Tool("Count the number of words in the provided text.")
        public String countWords(@P("text") String text) {
            if (text == null || text.trim().isEmpty()) {
                return "0 words";
            }
            int n = text.trim().split("\\s+").length;
            return n + " words";
        }

        @Tool("Return today's date in YYYY-MM-DD format.")
        public String getToday() {
            return LocalDate.now().toString();
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        UtilityTools tools = new UtilityTools();
        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);
        agent.toolsFromObject(tools);

        AgentResult result = Agentspan.run(
                agent,
                "What is 17 + 25? Also count words in 'the quick brown fox jumps'. "
                + "And what is today's date?",
                tools
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
