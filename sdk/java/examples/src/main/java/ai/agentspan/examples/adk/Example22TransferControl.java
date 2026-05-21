// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 22 — Transfer Control
 *
 * <p>Java port of <code>sdk/python/examples/adk/22_transfer_control.py</code>.
 *
 * <p>Demonstrates: restricted agent handoffs via native ADK's
 * {@code disallowTransferToParent}/{@code disallowTransferToPeers} flags.
 */
public class Example22TransferControl {

    public static void main(String[] args) {
        // Cannot return to coordinator directly (disallow_transfer_to_parent=True)
        LlmAgent specialistA = LlmAgent.builder()
            .name("data_collector")
            .description("Gathers raw data points and forwards them to the analyst (cannot return to parent).")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data collection specialist. Gather relevant data points "
                + "about the topic and pass them to the analyst for analysis. "
                + "You should NOT return to the coordinator directly.")
            .disallowTransferToParent(true)
            .build();

        // Default — can transfer to any coordinator
        LlmAgent specialistB = LlmAgent.builder()
            .name("analyst")
            .description("Analyzes collected data and produces concise insights (free transfer).")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data analyst. Take the data collected and provide "
                + "a concise analysis with insights. You can transfer to any coordinator.")
            .build();

        // Cannot transfer to peers (disallow_transfer_to_peers=True)
        LlmAgent specialistC = LlmAgent.builder()
            .name("summarizer")
            .description("Creates an executive summary and returns to the coordinator (no peer transfer).")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a summarizer. Take the analysis and create a brief "
                + "executive summary. Return the summary to the coordinator. "
                + "Do NOT transfer to other specialists.")
            .disallowTransferToPeers(true)
            .build();

        LlmAgent coordinator = LlmAgent.builder()
            .name("research_coordinator")
            .description("Coordinates a constrained team of collector, analyst, and summarizer specialists.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a research coordinator managing a team of specialists:
                - data_collector: gathers raw data (cannot return to you directly)
                - analyst: analyzes data (can transfer freely)
                - summarizer: creates executive summaries (cannot transfer to peers)

                Route the user's request through the appropriate workflow.
                """)
            .subAgents(specialistA, specialistB, specialistC)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Research the current state of renewable energy adoption worldwide.");
        result.printResult();

        Agentspan.shutdown();
    }
}
