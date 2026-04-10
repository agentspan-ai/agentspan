# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Output Parsers — agent that returns structured data using LangChain output parsers.

Demonstrates:
    - CommaSeparatedListOutputParser for list outputs
    - StructuredOutputParser for multi-field responses
    - Parsing and validating tool outputs

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json

from langchain.agents import create_agent
from langchain_core.output_parsers import CommaSeparatedListOutputParser
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

list_parser = CommaSeparatedListOutputParser()


@tool
def get_ingredients(dish: str) -> str:
    """Return the main ingredients for a dish as a comma-separated list.

    Args:
        dish: The name of the dish.
    """
    ingredients = {
        "pasta carbonara": "spaghetti, guanciale, eggs, pecorino romano, black pepper",
        "caesar salad": "romaine lettuce, croutons, parmesan, caesar dressing, anchovies",
        "chocolate chip cookies": "flour, butter, sugar, eggs, vanilla, chocolate chips, baking soda, salt",
        "chicken curry": "chicken, curry powder, coconut milk, onion, garlic, ginger, tomatoes, spices",
        "guacamole": "avocado, lime juice, cilantro, red onion, jalapeño, salt, tomato",
    }
    return ingredients.get(dish.lower(), f"No recipe found for '{dish}'.")


@tool
def parse_as_list(text: str) -> str:
    """Parse a comma-separated string into a numbered list.

    Args:
        text: Comma-separated values to parse and format.
    """
    try:
        items = list_parser.parse(text)
        return "\n".join(f"{i+1}. {item.strip()}" for i, item in enumerate(items))
    except Exception:
        items = [x.strip() for x in text.split(",")]
        return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))


@tool
def extract_structured_data(text: str) -> str:
    """Extract structured data fields (name, date, amount) from free text.

    Args:
        text: Free-form text potentially containing structured information.
    """
    import re
    result = {}

    # Extract dates (simple patterns)
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b", text)
    if date_match:
        result["date"] = date_match.group(0)

    # Extract amounts
    amount_match = re.search(r"\$[\d,]+(?:\.\d{2})?|\b\d+(?:\.\d{2})?\s*(?:dollars?|USD)\b", text, re.I)
    if amount_match:
        result["amount"] = amount_match.group(0)

    # Extract email
    email_match = re.search(r"\b[\w.+-]+@[\w-]+\.\w{2,}\b", text)
    if email_match:
        result["email"] = email_match.group(0)

    if not result:
        return "No structured data fields (date, amount, email) found in text."
    return json.dumps(result, indent=2)


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_ingredients, parse_as_list, extract_structured_data]

graph = create_agent(
    llm,
    tools=tools,
    name="output_parsers_agent",
    system_prompt=(
        "You are a data extraction and formatting assistant. "
        "Use tools to retrieve, parse, and structure information clearly."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Get the ingredients for pasta carbonara and format them as a numbered list. "
            "Also extract any structured data from: 'Invoice #1234 dated 2025-03-15, amount $249.99, contact billing@example.com'",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.24_output_parsers
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
