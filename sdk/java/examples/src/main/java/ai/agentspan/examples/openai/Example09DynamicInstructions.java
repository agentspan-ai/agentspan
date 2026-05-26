// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * Example OpenAi 09 — Dynamic Instructions
 *
 * <p>Java port of <code>sdk/python/examples/openai/09_dynamic_instructions.py</code>.
 *
 * <p>Demonstrates: instructions computed at build time from the current
 * time-of-day so the agent adopts a cheerful morning / focused afternoon /
 * calm evening persona. A pair of todo-list tools is also wired up.
 *
 * <p>Python parity gap: the Python original passes a callable
 * {@code instructions=get_dynamic_instructions} that the runtime invokes
 * on every turn. The Java {@link OpenAIAgent} builder accepts only a
 * {@code String} for instructions, so we resolve the dynamic prompt once
 * at {@code main()} time — semantically equivalent for a single-shot run.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example09DynamicInstructions {

    static class TodoTools {

        @Tool(name = "get_todo_list", description = "Get the user's current todo list.")
        public String getTodoList() {
            String[] todos = {
                    "Review PR #42 - high priority",
                    "Write unit tests for auth module",
                    "Team standup at 2pm",
                    "Deploy v2.1 to staging",
            };
            StringBuilder sb = new StringBuilder();
            for (String t : todos) {
                if (sb.length() > 0) sb.append("\n");
                sb.append("- ").append(t);
            }
            return sb.toString();
        }

        @Tool(name = "add_todo", description = "Add a new item to the todo list.")
        public String addTodo(String task, String priority) {
            String p = (priority == null || priority.isEmpty()) ? "medium" : priority;
            return "Added to todo list: '" + task + "' (priority: " + p + ")";
        }
    }

    /** Compute time-of-day-driven instructions — mirrors Python's get_dynamic_instructions. */
    static String getDynamicInstructions() {
        LocalDateTime now = LocalDateTime.now();
        int hour = now.getHour();
        String greetingStyle;
        String tone;
        if (hour < 12) {
            greetingStyle = "cheerful morning";
            tone = "energetic and upbeat";
        } else if (hour < 17) {
            greetingStyle = "professional afternoon";
            tone = "focused and efficient";
        } else {
            greetingStyle = "relaxed evening";
            tone = "calm and conversational";
        }
        String timeStr = now.format(DateTimeFormatter.ofPattern("hh:mm a"));
        return "You are a personal assistant with a " + greetingStyle + " style. "
                + "Respond in a " + tone + " tone. "
                + "Current time: " + timeStr + ". "
                + "Always be helpful and use available tools when appropriate.";
    }

    public static void main(String[] args) {
        Agent agent = OpenAIAgent.builder()
                .name("personal_assistant")
                .instructions(getDynamicInstructions())
                .model(Settings.LLM_MODEL)
                .tools(new TodoTools())
                .build();

        AgentResult result = Agentspan.run(
                agent,
                "Show me my todo list and add 'Prepare demo for Friday' as high priority.");
        result.printResult();

        Agentspan.shutdown();
    }
}
