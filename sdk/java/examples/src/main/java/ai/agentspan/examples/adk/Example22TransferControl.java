// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 22 — Transfer Control
 *
 * <p>Java port of <code>sdk/python/examples/adk/22_transfer_control.py</code>.
 *
 * <p>Demonstrates: restricted agent handoffs. The Python source uses
 * {@code disallow_transfer_to_parent} and {@code disallow_transfer_to_peers}
 * on {@code LlmAgent}. These map to allowedTransitions in the Conductor
 * workflow on the server side. The Java {@link GoogleADKAgent} builder does
 * not expose those flags directly; the role-based intent is documented in
 * each agent's instruction.
 */
public class Example22TransferControl {

    public static void main(String[] args) {
        // Cannot return to coordinator directly (disallow_transfer_to_parent=True)
        Agent specialistA = GoogleADKAgent.builder()
            .name("data_collector")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data collection specialist. Gather relevant data points "
                + "about the topic and pass them to the analyst for analysis. "
                + "You should NOT return to the coordinator directly.")
            .build();

        // Default — can transfer to any agent
        Agent specialistB = GoogleADKAgent.builder()
            .name("analyst")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data analyst. Take the data collected and provide "
                + "a concise analysis with insights. You can transfer to any agent.")
            .build();

        // Cannot transfer to peers (disallow_transfer_to_peers=True)
        Agent specialistC = GoogleADKAgent.builder()
            .name("summarizer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a summarizer. Take the analysis and create a brief "
                + "executive summary. Return the summary to the coordinator. "
                + "Do NOT transfer to other specialists.")
            .build();

        Agent coordinator = GoogleADKAgent.builder()
            .name("research_coordinator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a research coordinator managing a team of specialists:\n"
                + "- data_collector: gathers raw data (cannot return to you directly)\n"
                + "- analyst: analyzes data (can transfer freely)\n"
                + "- summarizer: creates executive summaries (cannot transfer to peers)\n\n"
                + "Route the user's request through the appropriate workflow.")
            .subAgents(specialistA, specialistB, specialistC)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Research the current state of renewable energy adoption worldwide.");
        result.printResult();

        Agentspan.shutdown();
    }
}
