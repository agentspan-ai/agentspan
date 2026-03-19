# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Output Parsers — using LangChain output parsers inside tool functions.

Demonstrates:
    - StrOutputParser for clean string extraction
    - CommaSeparatedListOutputParser for list output
    - JsonOutputParser with Pydantic schema
    - How output parsers improve reliability of LLM-structured data
    - Practical use case: structured data extraction pipeline

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import List

from pydantic import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser, CommaSeparatedListOutputParser, JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Parsers ───────────────────────────────────────────────────────────────────

str_parser = StrOutputParser()
list_parser = CommaSeparatedListOutputParser()


class ProductReview(BaseModel):
    product_name: str = Field(description="Name of the product")
    overall_score: int = Field(description="Overall score from 1-10")
    pros: List[str] = Field(description="List of positive aspects")
    cons: List[str] = Field(description="List of negative aspects")
    recommendation: str = Field(description="Buy/Skip/Wait recommendation")


json_parser = JsonOutputParser(pydantic_object=ProductReview)


# ── Tools using parsers ───────────────────────────────────────────────────────

@tool
def extract_keywords_list(text: str, max_keywords: int = 10) -> str:
    """Extract keywords from text as a clean comma-separated list.

    Uses CommaSeparatedListOutputParser for reliable list extraction.

    Args:
        text: Text to extract keywords from.
        max_keywords: Maximum number of keywords to return.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"Extract the {max_keywords} most important keywords from the text. {list_parser.get_format_instructions()}"),
        ("human", "{text}"),
    ])
    chain = prompt | llm | list_parser
    keywords = chain.invoke({"text": text})
    return f"Keywords: {', '.join(keywords[:max_keywords])}"


@tool
def clean_text_extraction(text: str, instruction: str) -> str:
    """Apply a transformation instruction to text and return a clean string result.

    Uses StrOutputParser to extract clean text without markup.

    Args:
        text: Input text to transform.
        instruction: Transformation instruction (e.g., 'extract the main question', 'rephrase formally').
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Follow the instruction precisely. Return only the result, no explanation."),
        ("human", "Instruction: {instruction}\n\nText: {text}"),
    ])
    chain = prompt | llm | str_parser
    result = chain.invoke({"text": text, "instruction": instruction})
    return result.strip()


@tool
def parse_product_review(review_text: str, product_name: str) -> str:
    """Parse a product review into structured fields using JSON output parser.

    Extracts: score, pros, cons, and recommendation.

    Args:
        review_text: The full review text to parse.
        product_name: Name of the product being reviewed.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"Parse the review for '{product_name}' into structured JSON. {json_parser.get_format_instructions()}"),
        ("human", "{review}"),
    ])
    chain = prompt | llm | json_parser
    try:
        result = chain.invoke({"review": review_text})
        if isinstance(result, dict):
            pros_str = "\n".join(f"  + {p}" for p in result.get("pros", []))
            cons_str = "\n".join(f"  - {c}" for c in result.get("cons", []))
            return (
                f"Parsed review for {result.get('product_name', product_name)}:\n"
                f"Score: {result.get('overall_score', 'N/A')}/10\n"
                f"Pros:\n{pros_str}\n"
                f"Cons:\n{cons_str}\n"
                f"Recommendation: {result.get('recommendation', 'N/A')}"
            )
        return str(result)
    except Exception as e:
        return f"Parse error: {e}"


PARSER_SYSTEM = """You are a text processing assistant.
When processing text:
1. Use appropriate parsers for each task (keyword extraction, clean text, structured reviews)
2. Apply transformations as requested
3. Present results clearly and consistently
"""

graph = create_agent(
    llm,
    tools=[extract_keywords_list, clean_text_extraction, parse_product_review],
    name="output_parsers_agent",
    system_prompt=PARSER_SYSTEM,
)

SAMPLE_REVIEW = """
I've been using the Sony WH-1000XM5 headphones for three months and have mixed feelings.
The noise cancellation is absolutely world-class — I can work in a busy coffee shop without
any distraction. Sound quality is superb with rich bass and clear highs. Battery life is
fantastic at 30+ hours.

However, the build quality is disappointingly plasticky for a $400 headphone. The case is
bulky and the touch controls are overly sensitive. The microphone quality is mediocre for
calls. Overall I'd give it a 7.5/10 — great for music listening but not ideal for the price.
"""

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Extract keywords and parse the structured review from this text:\n\n{SAMPLE_REVIEW}\n\n"
            f"Product name: Sony WH-1000XM5",
        )
        print(f"Status: {result.status}")
        result.print_result()
