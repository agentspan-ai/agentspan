package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.enums.EventType;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentEvent;
import ai.agentspan.model.AgentStream;

public class VerifyRouting {
    public static void main(String[] args) throws Exception {
        Agent pythonExpert = Agent.builder().name("python_expert").model(Settings.LLM_MODEL)
            .instructions("You are a Python expert.").build();
        Agent javaExpert = Agent.builder().name("java_expert").model(Settings.LLM_MODEL)
            .instructions("You are a Java expert.").build();
        Agent sqlExpert = Agent.builder().name("sql_expert").model(Settings.LLM_MODEL)
            .instructions("You are a SQL expert.").build();
        Agent router = Agent.builder().name("lang_router").model(Settings.LLM_MODEL)
            .instructions("Select: 'python_expert', 'java_expert', or 'sql_expert'. Respond ONLY with the agent name.")
            .build();
        Agent codingAssistant = Agent.builder().name("coding_assistant").model(Settings.LLM_MODEL)
            .instructions("Route coding questions to the appropriate expert.")
            .agents(pythonExpert, javaExpert, sqlExpert)
            .strategy(Strategy.ROUTER).router(router).build();

        String[] questions = {
            "How do I use list comprehensions in Python?",
            "How do I write a SQL query for top 10 customers by revenue?"
        };

        try (AgentRuntime runtime = new AgentRuntime()) {
            for (String q : questions) {
                System.out.println("\n>>> Question: " + q);
                AgentStream stream = runtime.stream(codingAssistant, q);
                for (AgentEvent event : stream) {
                    if (event.getType() == EventType.HANDOFF) {
                        System.out.println("  [HANDOFF] -> " + event.getTarget());
                    } else if (event.getType() == EventType.THINKING) {
                        System.out.println("  [THINKING] " + event.getContent());
                    } else if (event.getType() == EventType.DONE) {
                        System.out.println("  [DONE]");
                    }
                }
            }
        }
    }
}
