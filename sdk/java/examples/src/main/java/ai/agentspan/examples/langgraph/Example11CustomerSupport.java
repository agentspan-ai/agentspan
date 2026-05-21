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

import java.util.Locale;

/**
 * Example LangGraph 11 — Customer support router with classification + branches.
 *
 * <p>Mirrors <code>sdk/python/examples/langgraph/11_customer_support.py</code>
 * which builds a {@code greet -> classify -> route -> respond} {@code StateGraph}.
 * The LangGraph4j {@code AgentExecutor} pattern expresses this as one greet
 * tool, one classifier, and three branch tools — the LLM does the routing.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Domain-specific multi-step flow (support ticket triage)</li>
 *   <li>Classifier + branch handlers exposed as tools</li>
 *   <li>Sequencing instructions folded into the user message: greet,
 *       classify, respond</li>
 * </ul>
 */
public class Example11CustomerSupport {

    static class SupportTools {

        @Tool("Produce a warm support greeting. Call this FIRST for every ticket.")
        public String greet() {
            return "Hello! Thank you for contacting our support team. "
                    + "I'm here to help you today.";
        }

        @Tool("Classify a customer message. Returns exactly one of: billing, technical, general.")
        public String classify(@P("user_message") String userMessage) {
            String m = userMessage == null ? "" : userMessage.toLowerCase(Locale.ROOT);
            if (m.contains("charge") || m.contains("refund") || m.contains("invoice")
                    || m.contains("bill") || m.contains("payment") || m.contains("subscription")) {
                return "billing";
            }
            if (m.contains("error") || m.contains("crash") || m.contains("bug")
                    || m.contains("not working") || m.contains("broken") || m.contains("install")) {
                return "technical";
            }
            return "general";
        }

        @Tool("Handle a BILLING inquiry. Produces a billing-specialist response.")
        public String handleBilling(@P("user_message") String userMessage) {
            return "[Billing specialist] I'll review your account and walk you through "
                    + "payment options. Regarding: " + userMessage;
        }

        @Tool("Handle a TECHNICAL inquiry. Produces a step-by-step troubleshooting response.")
        public String handleTechnical(@P("user_message") String userMessage) {
            return "[Tech support] Let's troubleshoot step-by-step. Issue: " + userMessage
                    + "\nStep 1: Restart the app. Step 2: Check the logs. Step 3: Reproduce.";
        }

        @Tool("Handle a GENERAL inquiry. Produces a friendly informative response.")
        public String handleGeneral(@P("user_message") String userMessage) {
            return "[Customer service] Happy to help with: " + userMessage
                    + "\nIs there anything else I can do for you?";
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        SupportTools tools = new SupportTools();
        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);
        agent.toolsFromObject(tools);

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
                agent,
                "You are a customer support router. For EVERY incoming message: "
                + "1) call greet, "
                + "2) call classify, "
                + "3) call exactly ONE of handle_billing / handle_technical / handle_general "
                + "based on the classification, "
                + "4) compose a final reply that starts with the greeting and contains the "
                + "handler's response.\n\n"
                + "I was charged twice for my subscription this month and need a refund.",
                tools
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
