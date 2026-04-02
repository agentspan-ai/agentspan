# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Document Summarizer — agent that chunks and summarizes long documents.

Demonstrates:
    - Splitting text into chunks for processing
    - Extracting key themes and entities from text
    - Generating executive summaries

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def split_into_chunks(text: str, chunk_size: int = 200) -> str:
    """Split a document into chunks of approximately chunk_size words.

    Args:
        text: The full document text.
        chunk_size: Target words per chunk (default 200).
    """
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return f"Split into {len(chunks)} chunk(s).\nChunk 1 preview: {chunks[0][:150]}..." if chunks else "Empty document."


@tool
def count_sentences(text: str) -> str:
    """Count sentences and estimate reading time for a document.

    Args:
        text: The document text to analyze.
    """
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    words = len(text.split())
    reading_time = max(1, words // 200)
    return f"Sentences: {len(sentences)}, Words: {words}, Estimated reading time: ~{reading_time} minute(s)."


@tool
def extract_key_sentences(text: str, n: int = 3) -> str:
    """Extract the n most informative sentences from a document.

    Selects sentences that are long enough to be informative.

    Args:
        text: The document text.
        n: Number of key sentences to extract (default 3).
    """
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if len(s.strip()) > 40]
    selected = sentences[:n]
    if not selected:
        return "No long enough sentences found."
    return "\n".join(f"{i+1}. {s}." for i, s in enumerate(selected))


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [split_into_chunks, count_sentences, extract_key_sentences]

graph = create_agent(
    llm,
    tools=tools,
    name="document_summarizer_agent",
    system_prompt=(
        "You are a document analysis assistant. Use tools to analyze document structure, "
        "then synthesize a concise summary with key takeaways."
    ),
)

SAMPLE_DOCUMENT = """
Artificial intelligence is transforming industries at an unprecedented pace. Machine learning
algorithms can now diagnose diseases with accuracy rivaling specialists. Natural language
processing has enabled chatbots and virtual assistants that handle millions of customer
interactions daily. Computer vision systems inspect manufactured goods, detect security
threats, and enable self-driving vehicles. The economic impact is estimated at trillions
of dollars over the next decade. However, these advances also raise concerns about job
displacement, algorithmic bias, and the concentration of AI capabilities in a few large
corporations. Governments worldwide are drafting regulations to ensure AI is developed
safely and equitably. Researchers emphasize that explainability — the ability to understand
why an AI made a decision — is critical for trust and accountability. The field of AI ethics
has grown substantially, attracting philosophers, sociologists, and legal scholars alongside
computer scientists.
"""

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Analyze and summarize this document:\n\n{SAMPLE_DOCUMENT}",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.12_document_summarizer
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
