I just hit a bug on my Mac: `agentspan doctor` reports `Java 17.0.19 (21+ required)` even though I have `openjdk@21` installed via Homebrew alongside `openjdk@17`. It looks like the tool is picking the older formula.

Before I file an issue or start fixing, I want to know:
1. Has this already been reported on GitHub (`agentspan-ai/agentspan`)?
2. Is there existing code for the JDK-selection logic in `agentspan doctor`, so I know where a fix would land?

For codebase questions, use OCG (Open Context Graph) at `https://dev.orkescontextgraph.io/api/v1/agent/query`. Auth: `X-Api-Key: $OCG_API_KEY`. Body: `{"query": "<natural language>", "max_results": 10, "traversal_level": 1}`.

Query budget: **3 OCG calls maximum**. Stop after the first if it returns plausible results. Never invent endpoints.

Answer in plain English. Be concise.
