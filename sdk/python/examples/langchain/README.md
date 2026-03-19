# LangChain Examples

25 examples demonstrating LangChain integration with Agentspan, covering tools, chains, output parsers, and domain-specific agents.

> **Note:** Modern LangChain (v1.2+) uses `create_agent()` which returns a `CompiledStateGraph` detected by Agentspan as the `langgraph` framework. The distinction between these examples and the `langgraph/` examples is in the LangChain components used (prompt templates, output parsers, LCEL chains, structured output).

## Quick Start

```bash
export AGENTSPAN_SERVER_URL=http://localhost:8080/api
export OPENAI_API_KEY=sk-...

cd sdk/python
uv run python examples/langchain/01_hello_world.py
```

## Examples

### Getting Started (01–05)

| # | File | Topic |
|---|------|-------|
| 01 | `01_hello_world.py` | Basic `create_agent` with no tools |
| 02 | `02_react_with_tools.py` | ReAct agent with multiple `@tool` functions |
| 03 | `03_custom_tools.py` | Typed tool schemas with Pydantic + `StructuredTool` |
| 04 | `04_structured_output.py` | `with_structured_output()` + Pydantic schemas |
| 05 | `05_prompt_templates.py` | `ChatPromptTemplate` and `state_modifier` |

### Conversation & Memory (06–08)

| # | File | Topic |
|---|------|-------|
| 06 | `06_chat_history.py` | Multi-turn history with `session_id` |
| 07 | `07_memory_agent.py` | User profile memory with save/recall tools |
| 08 | `08_multi_tool_agent.py` | Multi-domain tools (time, currency, flights) |

### Utilities & Tools (09–11)

| # | File | Topic |
|---|------|-------|
| 09 | `09_math_calculator.py` | Comprehensive math tools (arithmetic, stats, geometry) |
| 10 | `10_web_search_agent.py` | Simulated web search + page summary tools |
| 11 | `11_code_review_agent.py` | AST-based code quality analysis tools |

### Document & Data (12–15)

| # | File | Topic |
|---|------|-------|
| 12 | `12_document_summarizer.py` | Multi-strategy summarization with `ChatPromptTemplate` chains |
| 13 | `13_customer_service_agent.py` | Empathetic customer support with policy tools |
| 14 | `14_research_assistant.py` | Citation-aware research with paper lookup |
| 15 | `15_data_analyst.py` | Tabular data analysis with aggregation tools |

### Content & Communication (16–18)

| # | File | Topic |
|---|------|-------|
| 16 | `16_content_writer.py` | Multi-format content generation (blog, social, email) |
| 17 | `17_sql_agent.py` | NL→SQL with in-memory SQLite execution |
| 18 | `18_email_drafter.py` | Professional email drafting and reply tools |

### Fact-Checking & Language (19–21)

| # | File | Topic |
|---|------|-------|
| 19 | `19_fact_checker.py` | Claim verification against a knowledge base |
| 20 | `20_translation_agent.py` | Translation + back-translation quality check |
| 21 | `21_sentiment_analysis.py` | Aspect-based sentiment analysis pipeline |

### Classification & Recommendations (22–23)

| # | File | Topic |
|---|------|-------|
| 22 | `22_classification_agent.py` | Multi-label ticket classification + routing |
| 23 | `23_recommendation_agent.py` | Preference-aware book/course recommendations |

### Advanced Patterns (24–25)

| # | File | Topic |
|---|------|-------|
| 24 | `24_output_parsers.py` | `StrOutputParser`, `CommaSeparatedListOutputParser`, `JsonOutputParser` |
| 25 | `25_advanced_orchestration.py` | Complex pipeline: market analysis → report compilation |

## Key LangChain Components Used

### `@tool` and `StructuredTool`
```python
from langchain_core.tools import tool, StructuredTool
from pydantic import BaseModel, Field

class MyInput(BaseModel):
    value: float = Field(description="The value to process")

@tool
def simple_tool(x: str) -> str:
    """Simple tool with string input."""
    return f"Result: {x}"

def complex_fn(value: float) -> str:
    return str(value * 2)

complex_tool = StructuredTool.from_function(
    func=complex_fn,
    name="complex_tool",
    args_schema=MyInput,
)
```

### `ChatPromptTemplate` in tools
```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert. {context}"),
    ("human", "{question}"),
])
chain = prompt | llm | StrOutputParser()
result = chain.invoke({"context": "...", "question": "..."})
```

### `with_structured_output`
```python
from pydantic import BaseModel
class MySchema(BaseModel):
    name: str
    score: int

structured_llm = llm.with_structured_output(MySchema)
result = structured_llm.invoke("Extract from: John scored 95 points")
```

### Session-based memory
```python
with AgentRuntime() as runtime:
    result = runtime.run(graph, "Hello!", session_id="user-42")
```

## Requirements

- Python 3.11+
- `uv` package manager
- `AGENTSPAN_SERVER_URL` — Agentspan server endpoint
- `OPENAI_API_KEY` — OpenAI API key for `ChatOpenAI`
