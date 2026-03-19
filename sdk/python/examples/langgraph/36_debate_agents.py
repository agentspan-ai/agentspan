# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Debate Agents — two agents arguing opposing positions, judged by a third.

Demonstrates:
    - Tools for PRO argument, CON argument, and judging
    - The orchestrating LLM conducts multiple rounds of debate via tool calls
    - Practical use case: pros/cons analysis, brainstorming, red-teaming

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

MAX_ROUNDS = 2


@tool
def argue_pro(topic: str, debate_so_far: str = "") -> str:
    """Make a concise argument IN FAVOUR of the topic (2-3 sentences).

    Args:
        topic: The debate topic.
        debate_so_far: Previous debate turns for context (empty for opening argument).
    """
    if debate_so_far:
        prompt_text = f"Topic: {topic}\n\nDebate so far:\n{debate_so_far}\n\nNow make your argument in favour (2-3 sentences)."
    else:
        prompt_text = f"Topic: {topic}\n\nMake your opening argument in favour of this topic (2-3 sentences)."

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a persuasive debater arguing IN FAVOUR of the given topic. Be concise and compelling."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": prompt_text})
    return f"PRO: {response.content.strip()}"


@tool
def argue_con(topic: str, debate_so_far: str) -> str:
    """Make a concise argument AGAINST the topic (2-3 sentences).

    Args:
        topic: The debate topic.
        debate_so_far: Previous debate turns for context.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a persuasive debater arguing AGAINST the given topic. Be concise and direct."),
        ("human", "Topic: {topic}\n\nDebate so far:\n{debate_so_far}\n\nMake your counter-argument (2-3 sentences)."),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic, "debate_so_far": debate_so_far})
    return f"CON: {response.content.strip()}"


@tool
def judge_debate(topic: str, transcript: str) -> str:
    """Evaluate the full debate transcript and declare a winner with reasoning.

    Returns which side (PRO or CON) made the stronger arguments and why.

    Args:
        topic: The debate topic.
        transcript: Full debate transcript with all turns.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an impartial debate judge. Review the debate transcript and:\n"
            "1. Identify which side made the stronger arguments\n"
            "2. Declare the winner (PRO or CON) and explain why in 2-3 sentences\n"
            "3. Note any logical fallacies or weak points"
        )),
        ("human", "Debate topic: {topic}\n\nTranscript:\n{transcript}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic, "transcript": transcript})
    return f"[JUDGE'S VERDICT]\n{response.content.strip()}"


DEBATE_SYSTEM = f"""You are a debate moderator.

For each debate topic, conduct {MAX_ROUNDS} rounds then judge:
1. Call argue_pro with the topic (no debate_so_far for the opening)
2. Call argue_con with the topic and the PRO argument as debate_so_far
3. Repeat for {MAX_ROUNDS} total rounds (alternating PRO → CON each round)
4. Combine all turns into a transcript and call judge_debate
5. Present the full debate and the judge's verdict

Keep track of all turns to build the transcript.
"""

graph = create_agent(
    llm,
    tools=[argue_pro, argue_con, judge_debate],
    name="debate_agents",
    system_prompt=DEBATE_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Artificial intelligence will create more jobs than it destroys.",
        )
        print(f"Status: {result.status}")
        result.print_result()
