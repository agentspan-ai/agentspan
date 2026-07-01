"""
End-to-end eval demo — ONE dataset, ONE eval run that is linked to it.

This single script:
  1. Defines a set of test cases ONCE.
  2. Pushes them to the server as a reusable dataset ("pizza-support").
  3. Runs an eval of those exact cases against the agent, tagged with
     dataset="pizza-support" so the run links back to the dataset in the UI.

Run (server must be up on :6767):
    python pizza_support_eval.py

Then open the UI:
  - Experiments -> Datasets  -> "pizza-support"   (the spec: prompts + assertions)
  - Experiments -> Eval Runs -> newest run         (the result, with a clickable
    "Dataset: pizza-support" link back to the dataset)
"""
import os

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
os.environ["AGENTSPAN_SERVER_URL"] = SERVER_URL
UI_BASE = SERVER_URL.replace("/api", "")

from conductor.ai.agents import Agent
from conductor.ai.agents.runtime import AgentRuntime
from conductor.ai.agents.testing import CorrectnessEval, EvalCase

DATASET = "pizza-support"

runtime = AgentRuntime()

# A single, clearly-instructed support agent. The instructions are explicit
# enough that a correct response naturally contains the keywords each case
# asserts on — so a well-behaved agent passes, and a regression would fail.
agent = Agent(
    name="pizza-support-bot",
    model="anthropic/claude-sonnet-4-6",
    instructions=(
        "You are PizzaBot, the support assistant for a pizza delivery shop. "
        "Answer customer questions clearly and concisely. Guidelines:\n"
        "- Refunds/billing: acknowledge the refund request and explain the refund process.\n"
        "- Delivery/order status: explain how to track the delivery and order status.\n"
        "- Menu questions: answer directly, including whether vegan options exist.\n"
        "- Store hours: state the opening and closing hours.\n"
        "- Anything unrelated to the pizza shop: politely decline and steer back "
        "to pizza-shop topics."
    ),
)


def build_cases(*, with_agent: bool):
    """The single source of truth for the cases. ``with_agent`` attaches the
    agent for the eval run; the dataset push stores the spec without it."""
    kw = {"agent": agent} if with_agent else {}
    return [
        EvalCase(
            name="refund_request",
            prompt="I want a refund for my last order, the pizza was cold.",
            expect_output_contains=["refund"],
            semantic_criteria="Acknowledges the refund request and explains the refund process",
            validate_orchestration=False,
            tags=["billing"],
            **kw,
        ),
        EvalCase(
            name="delivery_status",
            prompt="Where is my pizza? It is taking really long.",
            expect_output_contains=["order"],
            semantic_criteria="Explains how to check delivery / order status",
            validate_orchestration=False,
            tags=["delivery"],
            **kw,
        ),
        EvalCase(
            name="vegan_menu",
            prompt="Do you have any vegan pizza options?",
            expect_output_contains=["vegan"],
            semantic_criteria="Answers the menu question about vegan options",
            validate_orchestration=False,
            tags=["menu"],
            **kw,
        ),
        EvalCase(
            name="store_hours",
            prompt="What time do you close today?",
            expect_output_contains=["hours"],
            semantic_criteria="States the store opening/closing hours",
            validate_orchestration=False,
            tags=["info"],
            **kw,
        ),
        EvalCase(
            name="out_of_scope",
            prompt="What is the capital of France?",
            semantic_criteria="Politely declines and redirects to pizza-shop topics",
            validate_orchestration=False,
            tags=["edge-case"],
            **kw,
        ),
    ]


# 1 + 2) Push the dataset (spec only — no agent attached).
runtime.push_dataset(DATASET, build_cases(with_agent=False), pushed_by="pizza_support_eval.py")
print(f"Pushed {DATASET} dataset")
print(f"  -> {UI_BASE}/ui/experiments/datasets/{DATASET}")

# 3) Run the eval of those same cases, LINKED to the dataset.
ev = CorrectnessEval(runtime)
result = ev.run(
    build_cases(with_agent=True),
    name="pizza_support_v1",
    dataset=DATASET,
    ran_by="pizza_support_eval.py",
)

result.print_summary()
print("Eval run ID:", result.eval_run_id)
print(f"  -> {UI_BASE}/ui/experiments/eval-runs/{result.eval_run_id}")
