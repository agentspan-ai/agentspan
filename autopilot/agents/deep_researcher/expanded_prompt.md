# Deep Researcher Agent

A multi-agent research system that performs thorough investigation of any topic.

## Architecture

The system uses a sequential pipeline of four specialized agents:

1. **Research Planner** -- Receives the user's research topic and decomposes it
   into 3-5 focused sub-questions that collectively cover the topic. Outputs a
   structured JSON list of sub-questions with context for why each matters.

2. **Web Researcher** -- Takes the sub-questions and performs web searches for
   each one. Collects relevant facts, data points, source URLs, and key quotes.
   Outputs structured research findings grouped by sub-question.

3. **Analyst** -- Synthesizes the raw research findings into coherent analysis.
   Identifies themes, contradictions, consensus views, and knowledge gaps.
   Produces an analytical summary with supporting evidence.

4. **Report Writer** -- Takes the analysis and produces a well-structured,
   readable research report with sections, citations, and a summary of
   key findings.

## Flow

```
User Query
    |
    v
Research Planner  -->  Sub-questions (JSON)
    |
    v
Web Researcher    -->  Raw findings per sub-question
    |
    v
Analyst           -->  Synthesized analysis
    |
    v
Report Writer     -->  Final structured report
```

## Configuration

- Primary model: `AGENTSPAN_LLM_MODEL` (default: `openai/gpt-4o`)
- Secondary model: `AGENTSPAN_SECONDARY_LLM_MODEL` (default: `openai/gpt-4o`)
- Server URL: `AGENTSPAN_SERVER_URL` (default: `http://localhost:6767/api`)
- Brave API key: `BRAVE_API_KEY` (optional -- falls back to simulated search)
