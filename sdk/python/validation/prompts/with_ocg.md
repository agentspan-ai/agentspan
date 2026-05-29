I'm about to add `AGENTSPAN_LOG_LEVEL` to the Python SDK docs in the agentspan-ai/agentspan repo at `~/PycharmProjects/agentspan`. Before I do, I need to understand the business context:

- Who introduced this env var?
- What was the original intent?
- Was it part of a specific feature or customer ask?

Use OCG (Open Context Graph) to answer this. OCG is a codebase knowledge graph at `https://dev.orkescontextgraph.io/api/v1/agent/query`. Auth: `X-Api-Key: $OCG_API_KEY`. Body: `{"query": "<natural language>", "max_results": 10, "traversal_level": 1}`.

Query budget: **3 calls maximum**. Stop after the first call if it returns any plausible result for the question. Only issue follow-up calls when the prior response is completely irrelevant (no usable citations or traversal results). Never invent or fetch other endpoints.

Answer in plain English. Be concise.
