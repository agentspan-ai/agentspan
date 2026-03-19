# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Output Validator — validate LLM output and retry until it meets criteria.

Demonstrates:
    - Generating structured JSON output and validating it inside a tool
    - The tool retries automatically if validation fails
    - Practical use case: ensuring the LLM always returns valid JSON

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

MAX_ATTEMPTS = 4
REQUIRED_FIELDS = {"name", "age", "occupation", "hobby"}


@tool
def generate_and_validate_profile(prompt: str) -> str:
    """Generate a fictional person profile as valid JSON and validate it.

    Retries up to 4 times if the output is invalid JSON or missing required fields.
    Required fields: name (string), age (integer), occupation (string), hobby (string).

    Args:
        prompt: Description of the person to generate (e.g., 'a software engineer from Japan').
    """
    validation_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        error_hint = ""
        if validation_error:
            error_hint = f"\n\nPrevious attempt failed validation: {validation_error}. Please fix this."

        gen_prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "Generate a fictional person profile as a JSON object with exactly these fields: "
                "name (string), age (integer), occupation (string), hobby (string). "
                "Return ONLY valid JSON — no markdown, no backticks, no explanation."
                + error_hint
            )),
            ("human", "{prompt}"),
        ])
        chain = gen_prompt | llm
        response = chain.invoke({"prompt": prompt})
        raw = response.content.strip()

        # Strip markdown code fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        # Validate JSON parse
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError as e:
            validation_error = f"JSON parse error: {e}"
            continue

        # Validate required fields
        missing = REQUIRED_FIELDS - set(data.keys())
        if missing:
            validation_error = f"Missing fields: {missing}"
            continue

        # Validate age type
        if not isinstance(data.get("age"), int):
            validation_error = "Field 'age' must be an integer"
            continue

        # Success
        return (
            f"Valid profile generated (attempt {attempt}):\n"
            f"  Name:       {data['name']}\n"
            f"  Age:        {data['age']}\n"
            f"  Occupation: {data['occupation']}\n"
            f"  Hobby:      {data['hobby']}"
        )

    return f"Failed to generate valid output after {MAX_ATTEMPTS} attempts. Last error: {validation_error}"


graph = create_agent(
    llm,
    tools=[generate_and_validate_profile],
    name="output_validator_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Create a fictional software engineer from Japan")
        print(f"Status: {result.status}")
        result.print_result()
