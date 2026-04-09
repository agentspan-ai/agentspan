// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.AgentTool;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example 68 — Context Condensation Stress Test
 *
 * <p>An orchestrator agent calls a {@code deep_analyst} sub-agent (via
 * {@link AgentTool#from(Agent)}) once per technology domain. Each sub-agent
 * fetches structured domain data and writes a comprehensive analysis. After
 * roughly 10 sub-agent calls the accumulated history exceeds the configured
 * context window and the server automatically condenses it.
 *
 * <pre>
 * orchestrator
 *   └── AgentTool.from(deep_analyst) × 25 topics
 *         └── fetch_domain_data(domain)
 * </pre>
 *
 * <p>To trigger condensation, add to server's {@code application.properties}:
 * <pre>
 *   agentspan.default-context-window=10000
 * </pre>
 */
public class Example68ContextCondensation {

    private static final Map<String, Map<String, Object>> DOMAIN_DATA = buildDomainData();

    static class AnalystTools {
        @Tool(name = "fetch_domain_data",
              description = "Fetch market data, statistics, and key facts for a technology domain")
        public Map<String, Object> fetchDomainData(String domain) {
            String key = domain.toLowerCase().trim();
            Map<String, Object> found = DOMAIN_DATA.get(key);
            if (found != null) return found;
            for (Map.Entry<String, Map<String, Object>> e : DOMAIN_DATA.entrySet()) {
                if (e.getKey().contains(key) || key.contains(e.getKey())) return e.getValue();
            }
            return Map.of("domain", domain, "market_size", "N/A", "cagr", "Growing",
                "top_players", List.of("Various"), "key_verticals", List.of("Enterprise"),
                "recent_breakthroughs", "Active R&D", "open_challenges", "Scalability");
        }
    }

    public static void main(String[] args) {
        List<ToolDef> analystTools = ToolRegistry.fromInstance(new AnalystTools());

        Agent deepAnalyst = Agent.builder()
            .name("deep_analyst_68")
            .model(Settings.LLM_MODEL)
            .tools(analystTools)
            .instructions(
                "You are an expert technology analyst. When asked to analyse a domain:\n" +
                "1. Call fetch_domain_data to get raw facts.\n" +
                "2. Write a structured analysis covering: Executive Summary, Market Overview, " +
                "Key Players, Use Cases, Recent Breakthroughs, and 5-Year Outlook.\n" +
                "Be specific and reference the data. Minimum 300 words.")
            .build();

        List<String> domains = new ArrayList<>(DOMAIN_DATA.keySet());
        String domainList = String.join(", ", domains);

        Agent orchestrator = Agent.builder()
            .name("research_orchestrator_68")
            .model(Settings.LLM_MODEL)
            .tools(List.of(AgentTool.from(deepAnalyst)))
            .instructions(
                "You are a research director compiling a technology landscape report. " +
                "Process ONE domain per turn — call deep_analyst for exactly ONE domain, " +
                "wait for the result, then call it for the next domain. " +
                "After ALL domains are done, write a 5-bullet cross-domain executive summary.")
            .build();

        AgentResult result = Agentspan.run(orchestrator,
            "Produce comprehensive analyses for each of the following " + domains.size() +
            " technology domains by calling deep_analyst ONCE PER DOMAIN, " +
            "one at a time. Complete all domains, then summarise cross-domain trends. " +
            "Domains: " + domainList + ".");
        result.printResult();

        Agentspan.shutdown();
    }

    private static Map<String, Map<String, Object>> buildDomainData() {
        Map<String, Map<String, Object>> data = new LinkedHashMap<>();
        data.put("machine learning", domain("$158B (2024), $529B by 2030", "22.8%",
            List.of("Google DeepMind", "OpenAI", "Meta AI", "Microsoft", "Hugging Face"),
            List.of("healthcare diagnostics", "fraud detection", "autonomous systems", "NLP"),
            "MoE scaling, test-time compute, multimodal foundation models",
            "interpretability, data efficiency, energy consumption"));
        data.put("large language models", domain("$6.4B (2024), $36B by 2030", "33.2%",
            List.of("OpenAI", "Anthropic", "Google", "Meta", "Mistral"),
            List.of("coding assistants", "enterprise search", "customer support", "document generation"),
            "long-context (1M+ tokens), reasoning models (o1/o3), tool-use chains",
            "factual accuracy, context faithfulness, cost per token"));
        data.put("computer vision", domain("$22B (2024), $86B by 2030", "25.1%",
            List.of("NVIDIA", "Intel", "Qualcomm", "Google", "Amazon Rekognition"),
            List.of("manufacturing QC", "retail analytics", "medical imaging", "surveillance"),
            "vision transformers at scale, video understanding, 3D reconstruction",
            "adversarial robustness, edge deployment, annotation cost"));
        data.put("retrieval-augmented generation", domain("$1.2B (2024), $11B by 2029", "49%",
            List.of("Pinecone", "Weaviate", "Cohere", "LlamaIndex", "LangChain"),
            List.of("enterprise knowledge bases", "legal research", "medical Q&A"),
            "graph RAG, multi-hop retrieval, hybrid BM25+embedding search",
            "retrieval faithfulness, chunking strategy, latency"));
        data.put("autonomous vehicles", domain("$54B (2024), $557B by 2035", "28.5%",
            List.of("Waymo", "Tesla", "Mobileye", "Cruise", "Baidu Apollo"),
            List.of("ride-hailing", "trucking", "last-mile delivery", "mining"),
            "end-to-end neural driving, HD map-free navigation, V2X communication",
            "edge-case handling, liability frameworks, sensor cost"));
        data.put("AI in drug discovery", domain("$1.5B (2024), $9.8B by 2030", "36%",
            List.of("Schrödinger", "Recursion", "Insilico Medicine", "AbSci", "Isomorphic Labs"),
            List.of("target identification", "molecular generation", "clinical trial design"),
            "AlphaFold 3 protein interactions, generative chemistry, digital twins",
            "wet-lab validation bottleneck, data sharing, regulatory acceptance"));
        data.put("federated learning", domain("$180M (2024), $2.8B by 2030", "55%",
            List.of("Google", "Apple", "NVIDIA FLARE", "PySyft", "IBM"),
            List.of("mobile prediction", "healthcare", "financial fraud"),
            "secure aggregation at scale, differential privacy budgets, async FL",
            "communication overhead, data heterogeneity, poisoning attacks"));
        data.put("diffusion models", domain("$3.2B (2024), $18B by 2030", "33%",
            List.of("Stability AI", "Midjourney", "OpenAI DALL-E", "Adobe Firefly", "Runway"),
            List.of("creative content", "drug design", "video synthesis", "3D asset generation"),
            "video diffusion (Sora, Runway), consistency models, latent diffusion",
            "copyright attribution, deepfake misuse, training data consent"));
        data.put("reinforcement learning", domain("$2.1B (2024), $12B by 2030", "29%",
            List.of("Google DeepMind", "OpenAI", "Microsoft", "Cohere", "Hugging Face TRL"),
            List.of("RLHF for LLMs", "game AI", "robotics control", "financial trading"),
            "GRPO for reasoning, RLVR (verifiable rewards), self-play at scale",
            "reward hacking, sample efficiency, sim-to-real transfer"));
        data.put("AI safety and alignment", domain("$500M research funding (2024)", "3× YoY",
            List.of("Anthropic", "DeepMind Safety", "ARC Evals", "Redwood Research", "CAIS"),
            List.of("red-teaming", "constitutional AI", "interpretability", "scalable oversight"),
            "sparse autoencoders for feature circuits, debate as alignment method",
            "specification gaming, power-seeking, deceptive alignment"));
        data.put("multimodal AI", domain("$4.5B (2024), $35B by 2030", "41%",
            List.of("Google Gemini", "OpenAI GPT-4o", "Anthropic Claude", "Meta", "Apple"),
            List.of("visual Q&A", "document intelligence", "video analysis", "audio understanding"),
            "native audio/video tokens, any-to-any models, real-time multimodal agents",
            "cross-modal alignment, evaluation benchmarks, hallucination in vision"));
        data.put("AI chip design", domain("$31B (2024), $120B by 2030", "25%",
            List.of("NVIDIA", "AMD", "Google TPU", "Amazon Trainium", "Cerebras"),
            List.of("training accelerators", "inference at the edge", "neuromorphic chips"),
            "RL-based chip floorplanning, in-memory computing, chiplet interconnects",
            "power density, memory bandwidth wall, software ecosystem fragmentation"));
        return data;
    }

    private static Map<String, Object> domain(String marketSize, String cagr,
            List<String> players, List<String> verticals,
            String breakthroughs, String challenges) {
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("market_size", marketSize);
        d.put("cagr", cagr);
        d.put("top_players", players);
        d.put("key_verticals", verticals);
        d.put("recent_breakthroughs", breakthroughs);
        d.put("open_challenges", challenges);
        return d;
    }
}
