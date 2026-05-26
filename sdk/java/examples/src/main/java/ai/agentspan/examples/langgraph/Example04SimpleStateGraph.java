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

/**
 * Example LangGraph 04 — Simple state graph pattern: validate -> refine -> answer.
 *
 * <p>Conceptually mirrors <code>sdk/python/examples/langgraph/04_simple_stategraph.py</code>
 * which builds a 3-node {@code StateGraph<State>} pipeline. In the LangGraph4j
 * agent-executor + Agentspan pattern, multi-node pipelines are most cleanly
 * expressed by giving the ReAct loop a small set of pipeline-stage tools and
 * letting the LLM walk through them in order — the agent still produces the
 * same query -> refined -> answer flow as the Python pipeline.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Modeling a multi-stage pipeline as ordered tools</li>
 *   <li>Tool-sequencing instructions folded into the user message
 *       (validate -> refine -> answer)</li>
 *   <li>Building the LangGraph4j {@code AgentExecutor.Builder} and handing it
 *       straight to {@link Agentspan#run}</li>
 * </ul>
 */
public class Example04SimpleStateGraph {

    static class PipelineTools {

        @Tool("Stage 1: Validate the raw user query, trim whitespace, "
                + "and return a clean query. Call this FIRST.")
        public String validateQuery(@P("query") String query) {
            String q = query == null ? "" : query.trim();
            if (q.isEmpty()) q = "What can you help me with?";
            return "VALIDATED: " + q;
        }

        @Tool("Stage 2: Rewrite a validated query to be more specific. "
                + "Call this AFTER validate_query.")
        public String refineQuery(@P("validated_query") String validatedQuery) {
            // Trivial deterministic refinement — the LLM does most of the rewording
            // upstream; this tool just records that refinement happened.
            return "REFINED: " + validatedQuery.replace("VALIDATED: ", "");
        }

        @Tool("Stage 3: Record the final answer to the refined query. "
                + "Call this LAST with the answer you produced.")
        public String recordAnswer(@P("answer") String answer) {
            return "ANSWER RECORDED: " + answer;
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        PipelineTools tools = new PipelineTools();
        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);
        agent.toolsFromObject(tools);

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
                agent,
                "You implement a three-stage query pipeline. "
                + "ALWAYS call validate_query first, then refine_query, then "
                + "compose your final answer and finally call record_answer. "
                + "Return the final user-facing text after record_answer succeeds.\n\n"
                + "  Tell me about Java   ",
                tools);
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
