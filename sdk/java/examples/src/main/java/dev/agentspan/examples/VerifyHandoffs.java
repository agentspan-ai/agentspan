package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.enums.EventType;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentEvent;
import dev.agentspan.model.AgentStream;

public class VerifyHandoffs {
    public static void main(String[] args) throws Exception {
        Agent techSupport = Agent.builder().name("tech_support").model(Settings.LLM_MODEL)
            .instructions("You are a technical support specialist. Help troubleshoot technical issues.")
            .build();
        Agent billingSupport = Agent.builder().name("billing_support").model(Settings.LLM_MODEL)
            .instructions("You are a billing support specialist. Help with payment issues.")
            .build();
        Agent generalSupport = Agent.builder().name("general_support").model(Settings.LLM_MODEL)
            .instructions("You are general customer support. Handle general inquiries.")
            .build();
        Agent orchestrator = Agent.builder().name("support_orchestrator").model(Settings.LLM_MODEL)
            .instructions("Route to: 'tech_support' for technical issues, 'billing_support' for payments, 'general_support' otherwise.")
            .agents(techSupport, billingSupport, generalSupport)
            .strategy(Strategy.HANDOFF).build();

        String[][] tests = {
            {"Technical Issue", "My software keeps crashing when I try to export files. Error 0x80004005"},
            {"Billing Issue",   "I was charged twice for my subscription this month"},
            {"General Query",   "What are your business hours?"}
        };

        try (AgentRuntime runtime = new AgentRuntime()) {
            for (String[] test : tests) {
                System.out.println("\n=== " + test[0] + " ===");
                System.out.println("Input: " + test[1]);
                System.out.println("Expected handoff: " + (test[0].contains("Technical") ? "tech_support" : test[0].contains("Billing") ? "billing_support" : "general_support"));
                System.out.print("Actual events:   ");

                AgentStream stream = runtime.stream(orchestrator, test[1]);
                boolean handoffSeen = false;
                for (AgentEvent event : stream) {
                    if (event.getType() == EventType.HANDOFF) {
                        String target = event.getTarget();
                        // Filter out internal router sub-workflows, show only real agent handoffs
                        if (!target.contains("_router")) {
                            System.out.print("HANDOFF -> " + target + " ");
                            handoffSeen = true;
                        }
                    } else if (event.getType() == EventType.THINKING) {
                        System.out.print("[" + event.getContent() + "] ");
                    } else if (event.getType() == EventType.DONE) {
                        if (!handoffSeen) System.out.print("NO HANDOFF - direct answer");
                        System.out.println();
                    }
                }
            }
        }
    }
}
