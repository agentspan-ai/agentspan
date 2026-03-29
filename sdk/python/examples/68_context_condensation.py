# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Context Condensation Stress Test — orchestrator + sub-agent, history condenses 3+ times.

An orchestrator agent calls a ``deep_analyst`` sub-agent once per technology domain.
The sub-agent fetches raw domain data and writes a comprehensive ~600-word analysis
using the LLM.  Each sub-agent result lands in the orchestrator's conversation
history as a large tool-call output (~800 tokens).  After roughly 10 calls the
accumulated history exceeds the configured context window and the server
automatically condenses it.  This repeats ~3 times across the 25 domains.

Architecture::

    orchestrator
      └── agent_tool(deep_analyst) × 25 topics
            └── fetch_domain_data(domain)  ← structured facts/stats

What to watch in server logs (INFO level)::

    Condensed conversation from 22 to 12 messages (triggered by proactive (exceeds context window))
    Condensed conversation from 22 to 12 messages (triggered by proactive (exceeds context window))
    Condensed conversation from 22 to 12 messages (triggered by proactive (exceeds context window))

Setup — required for condensation to trigger
---------------------------------------------
Add to ``server/src/main/resources/application.properties`` and restart::

    agentspan.default-context-window=10000

Why: gpt-4o-mini has a 128 K context window; 25 × 800-token responses (~20 K
tokens) would not overflow it naturally.  Setting the window to 10 K forces
condensation to fire every ~10 sub-agent calls, giving 3 condensation events
across 25 calls — a realistic simulation of what happens with smaller models or
agents that accumulate very large tool outputs.

Requirements:
    - Conductor server with LLM support + ``agentspan.default-context-window=10000``
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, agent_tool, tool
from settings import settings

# ---------------------------------------------------------------------------
# Tool used by the sub-agent — returns structured domain facts to expand on
# ---------------------------------------------------------------------------

_DOMAIN_DATA = {
    "machine learning": {
        "market_size": "$158B (2024), projected $529B by 2030",
        "cagr": "22.8%",
        "top_players": ["Google DeepMind", "OpenAI", "Meta AI", "Microsoft", "Hugging Face"],
        "key_verticals": ["healthcare diagnostics", "financial fraud detection", "autonomous systems", "NLP"],
        "recent_breakthroughs": "Mixture-of-Experts scaling, test-time compute, multimodal foundation models",
        "open_challenges": "interpretability, data efficiency, energy consumption, hallucination",
        "regulatory_highlights": "EU AI Act risk tiers, US EO 14110, China AIGC regulations",
    },
    "large language models": {
        "market_size": "$6.4B (2024), projected $36B by 2030",
        "cagr": "33.2%",
        "top_players": ["OpenAI", "Anthropic", "Google", "Meta", "Mistral"],
        "key_verticals": ["coding assistants", "enterprise search", "customer support", "document generation"],
        "recent_breakthroughs": "long-context (1M+ tokens), reasoning models (o1/o3), tool-use chains",
        "open_challenges": "factual accuracy, context faithfulness, cost per token, alignment at scale",
        "regulatory_highlights": "watermarking requirements, bias audits, disclosure obligations",
    },
    "retrieval-augmented generation": {
        "market_size": "$1.2B (2024), projected $11B by 2029",
        "cagr": "49%",
        "top_players": ["Pinecone", "Weaviate", "Cohere", "LlamaIndex", "LangChain"],
        "key_verticals": ["enterprise knowledge bases", "legal research", "medical Q&A", "technical support"],
        "recent_breakthroughs": "graph RAG, multi-hop retrieval, hybrid BM25+embedding search",
        "open_challenges": "retrieval faithfulness, chunking strategy, latency, stale data",
        "regulatory_highlights": "data provenance tracking, GDPR right-to-erasure in vector stores",
    },
    "computer vision": {
        "market_size": "$22B (2024), projected $86B by 2030",
        "cagr": "25.1%",
        "top_players": ["NVIDIA", "Intel", "Qualcomm", "Google", "Amazon Rekognition"],
        "key_verticals": ["manufacturing QC", "retail analytics", "medical imaging", "security surveillance"],
        "recent_breakthroughs": "vision transformers at scale, video understanding, 3D scene reconstruction",
        "open_challenges": "adversarial robustness, edge deployment, annotation cost, privacy",
        "regulatory_highlights": "facial recognition bans, biometric data laws (BIPA, GDPR Art. 9)",
    },
    "autonomous vehicles": {
        "market_size": "$54B (2024), projected $557B by 2035",
        "cagr": "28.5%",
        "top_players": ["Waymo", "Tesla", "Mobileye", "Cruise", "Baidu Apollo"],
        "key_verticals": ["ride-hailing", "trucking & logistics", "last-mile delivery", "mining"],
        "recent_breakthroughs": "end-to-end neural driving, HD map-free navigation, V2X communication",
        "open_challenges": "edge-case handling, liability frameworks, sensor cost, public trust",
        "regulatory_highlights": "NHTSA AV framework, EU regulation 2022/2065, state-level AV laws",
    },
    "AI in drug discovery": {
        "market_size": "$1.5B (2024), projected $9.8B by 2030",
        "cagr": "36%",
        "top_players": ["Schrödinger", "Recursion", "Insilico Medicine", "AbSci", "Isomorphic Labs"],
        "key_verticals": ["target identification", "molecular generation", "clinical trial design", "toxicity prediction"],
        "recent_breakthroughs": "AlphaFold 3 protein interactions, generative chemistry, digital twins",
        "open_challenges": "wet-lab validation bottleneck, data sharing, regulatory acceptance of AI evidence",
        "regulatory_highlights": "FDA AI/ML action plan, EMA reflection paper on AI in drug development",
    },
    "federated learning": {
        "market_size": "$180M (2024), projected $2.8B by 2030",
        "cagr": "55%",
        "top_players": ["Google (FL framework)", "Apple", "NVIDIA FLARE", "PySyft (OpenMined)", "IBM"],
        "key_verticals": ["mobile keyboard prediction", "healthcare (NHS FL consortium)", "financial fraud"],
        "recent_breakthroughs": "secure aggregation at scale, differential privacy budgets, asynchronous FL",
        "open_challenges": "communication overhead, data heterogeneity, poisoning attacks, auditability",
        "regulatory_highlights": "GDPR data minimisation alignment, HIPAA distributed training guidance",
    },
    "graph neural networks": {
        "market_size": "$290M (2024), projected $2.1B by 2029",
        "cagr": "48%",
        "top_players": ["Google (GraphCast)", "Meta (PyG)", "Amazon", "Snap", "AstraZeneca"],
        "key_verticals": ["drug-protein interaction", "fraud graph detection", "recommendation systems", "chip design"],
        "recent_breakthroughs": "scalable GNNs (GraphSAGE variants), temporal GNNs, physics-informed GNNs",
        "open_challenges": "over-smoothing, scalability to billion-edge graphs, explainability",
        "regulatory_highlights": "financial graph analytics under MiFID II, GDPR graph inference risks",
    },
    "diffusion models": {
        "market_size": "$3.2B (2024), projected $18B by 2030",
        "cagr": "33%",
        "top_players": ["Stability AI", "Midjourney", "OpenAI (DALL-E)", "Adobe Firefly", "Runway"],
        "key_verticals": ["creative content", "drug design (protein folding)", "video synthesis", "3D asset generation"],
        "recent_breakthroughs": "video diffusion (Sora, Runway), consistency models (10× speedup), latent diffusion",
        "open_challenges": "copyright attribution, deepfake misuse, training data consent, compute cost",
        "regulatory_highlights": "C2PA content provenance standard, EU synthetic media disclosure rules",
    },
    "reinforcement learning": {
        "market_size": "$2.1B (2024), projected $12B by 2030",
        "cagr": "29%",
        "top_players": ["Google DeepMind", "OpenAI", "Microsoft", "Cohere (RLHF)", "Hugging Face TRL"],
        "key_verticals": ["RLHF for LLMs", "game AI", "robotics control", "financial trading", "chip floorplanning"],
        "recent_breakthroughs": "GRPO for reasoning, RLVR (verifiable rewards), self-play at scale",
        "open_challenges": "reward hacking, sample efficiency, sim-to-real transfer, sparse rewards",
        "regulatory_highlights": "gaming regulations (addictive mechanics), algorithmic trading oversight",
    },
    "AI safety and alignment": {
        "market_size": "$500M in dedicated research funding (2024)",
        "cagr": "Rapidly growing — 3× YoY in funding",
        "top_players": ["Anthropic", "DeepMind Safety", "ARC Evals", "Redwood Research", "Center for AI Safety"],
        "key_verticals": ["red-teaming", "constitutional AI", "interpretability", "scalable oversight"],
        "recent_breakthroughs": "sparse autoencoders for feature circuits, debate as alignment method, mechanistic interpretability",
        "open_challenges": "specification gaming, power-seeking behaviour, deceptive alignment, evaluation at frontier",
        "regulatory_highlights": "EU AI Act Art. 9 risk management, US AI Safety Institute, GPAI Code of Practice",
    },
    "natural language processing": {
        "market_size": "$29B (2024), projected $112B by 2030",
        "cagr": "25%",
        "top_players": ["Google", "Meta", "Hugging Face", "Cohere", "AI21 Labs"],
        "key_verticals": ["machine translation", "sentiment analysis", "information extraction", "dialogue systems"],
        "recent_breakthroughs": "instruction tuning, chain-of-thought prompting, mixture of experts",
        "open_challenges": "low-resource languages, commonsense reasoning, negation handling",
        "regulatory_highlights": "accessibility mandates, GDPR NLP inference, bias in hiring NLP",
    },
    "multimodal AI": {
        "market_size": "$4.5B (2024), projected $35B by 2030",
        "cagr": "41%",
        "top_players": ["Google Gemini", "OpenAI GPT-4o", "Anthropic Claude", "Meta LLaMA-Vision", "Apple"],
        "key_verticals": ["visual Q&A", "document intelligence", "video analysis", "audio understanding"],
        "recent_breakthroughs": "native audio/video tokens, any-to-any models, real-time multimodal agents",
        "open_challenges": "cross-modal alignment, evaluation benchmarks, hallucination in vision",
        "regulatory_highlights": "GDPR image/biometric processing, Section 230 and AI-generated media",
    },
    "robotics and embodied AI": {
        "market_size": "$23B (2024), projected $87B by 2030",
        "cagr": "25%",
        "top_players": ["Boston Dynamics", "Figure AI", "1X Technologies", "Agility Robotics", "NVIDIA Jetson"],
        "key_verticals": ["warehouse automation", "surgical robots", "agricultural robots", "humanoid assistants"],
        "recent_breakthroughs": "vision-language-action models (RT-2), dexterous manipulation, whole-body control",
        "open_challenges": "sim-to-real gap, manipulation dexterity, safety certification, cost",
        "regulatory_highlights": "CE marking for robots, ISO 10218 safety, FDA 510(k) for surgical robots",
    },
    "knowledge graphs": {
        "market_size": "$1.1B (2024), projected $5.9B by 2030",
        "cagr": "29%",
        "top_players": ["Neo4j", "Amazon Neptune", "Google Knowledge Graph", "Microsoft Azure Cosmos", "Ontotext"],
        "key_verticals": ["enterprise search", "drug-disease networks", "fraud detection", "recommendation engines"],
        "recent_breakthroughs": "LLM + KG hybrid (GraphRAG), temporal knowledge graphs, neurosymbolic reasoning",
        "open_challenges": "knowledge staleness, incomplete triples, entity disambiguation, scalability",
        "regulatory_highlights": "GDPR right to explanation (KG-based decisions), open government data mandates",
    },
    "AI in climate modelling": {
        "market_size": "$800M (2024), growing rapidly",
        "cagr": "38%",
        "top_players": ["Google DeepMind (GraphCast)", "Huawei Pangu-Weather", "ECMWF", "NVIDIA Earth-2", "IBM"],
        "key_verticals": ["weather forecasting", "climate simulation", "carbon capture optimisation", "renewable energy"],
        "recent_breakthroughs": "10-day weather at 0.25° resolution in <1 min, seasonal El Niño prediction",
        "open_challenges": "extreme event prediction, data assimilation, model uncertainty quantification",
        "regulatory_highlights": "Paris Agreement digital MRV systems, SEC climate disclosure rules",
    },
    "AI ethics and governance": {
        "market_size": "$400M (2024) in dedicated tooling/audit services",
        "cagr": "45%",
        "top_players": ["IBM OpenScale", "Fiddler AI", "Arthur AI", "Credo AI", "Holistic AI"],
        "key_verticals": ["model auditing", "bias detection", "explainability tooling", "regulatory compliance"],
        "recent_breakthroughs": "counterfactual fairness frameworks, differential privacy audits, model cards v2",
        "open_challenges": "fairness metric trade-offs, audit standardisation, adversarial red-teaming at scale",
        "regulatory_highlights": "EU AI Act, NIST AI RMF, NYC Local Law 144, Canada AIDA",
    },
    "foundation models": {
        "market_size": "$13B (2024), projected $89B by 2030",
        "cagr": "37%",
        "top_players": ["OpenAI", "Anthropic", "Google", "Meta", "Mistral", "Cohere"],
        "key_verticals": ["code generation", "scientific research", "creative content", "enterprise automation"],
        "recent_breakthroughs": "1M+ context windows, MoE at trillion parameters, RLVR reasoning chains",
        "open_challenges": "evaluation benchmark saturation, catastrophic forgetting, inference cost",
        "regulatory_highlights": "EU AI Act GPAI obligations, US NIST AI 600-1, compute reporting thresholds",
    },
    "AI in financial forecasting": {
        "market_size": "$12B (2024), projected $46B by 2030",
        "cagr": "25%",
        "top_players": ["Bloomberg AI", "Two Sigma", "Renaissance Technologies", "JPMorgan AI", "Kensho (S&P)"],
        "key_verticals": ["algorithmic trading", "credit scoring", "fraud detection", "risk management"],
        "recent_breakthroughs": "LLMs for earnings call analysis, graph ML for systemic risk, NLP-driven alpha",
        "open_challenges": "distribution shift, regime changes, explainability for regulators, latency",
        "regulatory_highlights": "MiFID II algo trading rules, SR 11-7 model risk guidance, SEC RegAI proposals",
    },
    "AI in education": {
        "market_size": "$5.8B (2024), projected $25B by 2030",
        "cagr": "28%",
        "top_players": ["Khan Academy (Khanmigo)", "Duolingo", "Chegg", "Carnegie Learning", "Coursera"],
        "key_verticals": ["intelligent tutoring", "automated essay grading", "personalised learning paths", "language learning"],
        "recent_breakthroughs": "Socratic dialogue via LLMs, knowledge tracing with transformers, adaptive assessment",
        "open_challenges": "academic integrity, digital equity, teacher displacement fears, evaluation validity",
        "regulatory_highlights": "FERPA data protections, EU GDPR for minors, UNESCO AI education guidelines",
    },
    "neural architecture search": {
        "market_size": "$420M (2024), projected $2.5B by 2030",
        "cagr": "35%",
        "top_players": ["Google (AutoML)", "Microsoft (Azure NNI)", "Huawei (DARTS)", "MIT HAN Lab", "Neural Magic"],
        "key_verticals": ["mobile edge deployment", "chip-aware design", "medical imaging models", "NLP efficiency"],
        "recent_breakthroughs": "once-for-all networks, zero-shot NAS proxy metrics, hardware-aware search",
        "open_challenges": "search cost, transferability across tasks, interpretability of found architectures",
        "regulatory_highlights": "EU energy efficiency requirements for AI systems, green AI initiatives",
    },
    "causal inference with AI": {
        "market_size": "$650M (2024), growing 42% annually",
        "cagr": "42%",
        "top_players": ["Microsoft Research (DoWhy)", "Amazon (CausalML)", "Uber (CausalNLP)", "IBM", "Quantumblack"],
        "key_verticals": ["clinical trial analysis", "A/B test uplift modelling", "policy evaluation", "root cause analysis"],
        "recent_breakthroughs": "LLM-assisted causal graph discovery, double ML, synthetic controls at scale",
        "open_challenges": "unobserved confounders, high-dimensional observational data, evaluation",
        "regulatory_highlights": "FDA causal evidence standards, EMA real-world evidence guidelines",
    },
    "AI-powered cybersecurity": {
        "market_size": "$24B (2024), projected $61B by 2030",
        "cagr": "17%",
        "top_players": ["CrowdStrike", "Darktrace", "SentinelOne", "Palo Alto Networks", "Google Chronicle"],
        "key_verticals": ["threat detection", "vulnerability discovery", "malware classification", "SOC automation"],
        "recent_breakthroughs": "LLM-based code vulnerability scanning, graph ML for lateral movement detection",
        "open_challenges": "adversarial AI evasion, false positive rates, explainability for incident response",
        "regulatory_highlights": "NIS2 Directive, CISA AI cybersecurity guidelines, SEC cyber disclosure rules",
    },
    "AI in supply chain": {
        "market_size": "$7.6B (2024), projected $27B by 2030",
        "cagr": "23%",
        "top_players": ["SAP", "Oracle", "Blue Yonder", "C3.ai", "o9 Solutions"],
        "key_verticals": ["demand forecasting", "inventory optimisation", "supplier risk", "logistics routing"],
        "recent_breakthroughs": "digital twins for end-to-end simulation, generative demand sensing, multi-echelon RL",
        "open_challenges": "data silos across supply chain partners, geopolitical uncertainty, explainability",
        "regulatory_highlights": "EU Supply Chain Act AI provisions, UFLPA forced labour screening",
    },
    "AI chip design": {
        "market_size": "$31B (2024), projected $120B by 2030",
        "cagr": "25%",
        "top_players": ["NVIDIA", "AMD", "Google TPU", "Amazon Trainium", "Cerebras", "Graphcore"],
        "key_verticals": ["training accelerators", "inference at the edge", "neuromorphic chips", "RISC-V AI SoCs"],
        "recent_breakthroughs": "RL-based chip floorplanning (Google), in-memory computing, chiplet interconnects",
        "open_challenges": "power density, memory bandwidth wall, software ecosystem fragmentation",
        "regulatory_highlights": "US CHIPS Act export controls, EU Chips Act, Taiwan Strait supply risk",
    },
}

_DEFAULT_DOMAIN_DATA = {
    "market_size": "Data not available",
    "cagr": "Growing rapidly",
    "top_players": ["Various vendors"],
    "key_verticals": ["Enterprise", "Consumer", "Research"],
    "recent_breakthroughs": "Active research and development",
    "open_challenges": "Scalability, cost, adoption",
    "regulatory_highlights": "Evolving global frameworks",
}


@tool
def fetch_domain_data(domain: str) -> dict:
    """Fetch market data, statistics, and key facts for a technology domain.

    Returns structured data including market size, growth rate, key players,
    verticals, recent breakthroughs, challenges, and regulatory highlights.
    """
    key = domain.lower().strip()
    # Try exact match, then partial match
    if key in _DOMAIN_DATA:
        return _DOMAIN_DATA[key]
    for k, v in _DOMAIN_DATA.items():
        if k in key or key in k:
            return v
    return {**_DEFAULT_DOMAIN_DATA, "domain": domain}


# ---------------------------------------------------------------------------
# Sub-agent: calls fetch_domain_data and writes a comprehensive ~600-word analysis
# ---------------------------------------------------------------------------

deep_analyst = Agent(
    name="deep_analyst_68",
    model=settings.llm_model,
    tools=[fetch_domain_data],
    instructions=(
        "You are an expert technology analyst at a top-tier research firm. "
        "When asked to analyse a domain:\n"
        "1. First call fetch_domain_data to retrieve the raw facts.\n"
        "2. Then write a COMPREHENSIVE, DETAILED analysis structured as follows:\n\n"
        "## Executive Summary\n"
        "A 3-4 sentence overview covering market position and strategic significance.\n\n"
        "## Market Overview\n"
        "Discuss market size, growth trajectory, CAGR drivers, geographic breakdown, "
        "and total addressable market evolution through 2030.\n\n"
        "## Technology Landscape\n"
        "Describe the current state of the technology, key architectural approaches, "
        "maturity levels across sub-segments, and differentiation between players.\n\n"
        "## Key Players & Competitive Dynamics\n"
        "Analyse the top players, their moats, recent strategic moves, and how new "
        "entrants are disrupting incumbents.\n\n"
        "## Use Cases & Industry Applications\n"
        "Detail specific implementations across the key verticals, with concrete "
        "examples and measurable outcomes where available.\n\n"
        "## Recent Breakthroughs & Innovation\n"
        "Explain the significance of each recent breakthrough and how it shifts "
        "the competitive landscape.\n\n"
        "## Challenges & Barriers to Adoption\n"
        "Cover technical, economic, organisational, and societal barriers in depth.\n\n"
        "## Regulatory & Policy Environment\n"
        "Summarise key regulations, their requirements, and business implications.\n\n"
        "## 5-Year Strategic Outlook\n"
        "Project how the domain evolves, which players win, and what inflection "
        "points to watch.\n\n"
        "Be specific, detailed, and rigorous in every section. Use the data from "
        "fetch_domain_data throughout. Minimum 500 words."
    ),
)

# ---------------------------------------------------------------------------
# Orchestrator: calls deep_analyst once per domain, collects all analyses
# ---------------------------------------------------------------------------

DOMAINS = list(_DOMAIN_DATA.keys())  # 25 domains

orchestrator = Agent(
    name="research_orchestrator_68",
    model=settings.llm_model,
    tools=[agent_tool(deep_analyst)],
    instructions=(
        "You are a research director compiling a technology landscape report. "
        "Process ONE domain per turn — call deep_analyst for exactly ONE domain, "
        "wait for the result, then call it for the next domain. "
        "Never call deep_analyst for more than one domain at a time. "
        "Keep a running count of which domains you have completed. "
        "After ALL domains are done, write a 5-bullet cross-domain executive "
        "summary highlighting the most important trends observed across all reports."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.68_context_condensation
        runtime.deploy(orchestrator)
        runtime.serve(orchestrator)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        #     orchestrator,
        #     "Produce comprehensive analyses for each of the following 25 technology domains "
        #     "by calling deep_analyst ONCE PER DOMAIN, one domain at a time (not in parallel). "
        #     "Complete all 25 domains, then summarise cross-domain trends. "
        #     "Domains: " + ", ".join(DOMAINS) + ".",
        # )
        # result.print_result()

