# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Customer Support Router — create_agent with category-specific response tools.

Demonstrates:
    - Using create_agent with a system prompt that directs routing behaviour
    - Tools for billing, technical, and general support handlers
    - The LLM classifies and routes to the right tool server-side

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def handle_billing(user_message: str) -> str:
    """Handle a billing-related customer inquiry.

    Provides empathetic billing support, explains payment options, and offers
    to review the account. Use this for payment, invoice, charge, or refund questions.

    Args:
        user_message: The customer's billing question or complaint.
    """
    return (
        f"Hello! Thank you for contacting our support team. I'm here to help you today.\n\n"
        f"I understand you have a billing concern. I sincerely apologize for any confusion "
        f"with your account. Our billing team can review your charges and process any eligible "
        f"refunds within 3-5 business days. You can also update your payment method anytime "
        f"in your account settings. Is there anything specific about your invoice I can clarify?"
    )


@tool
def handle_technical(user_message: str) -> str:
    """Handle a technical support inquiry with step-by-step troubleshooting guidance.

    Use this for software bugs, connectivity issues, configuration problems,
    or any technical malfunction.

    Args:
        user_message: The customer's technical issue or error description.
    """
    return (
        f"Hello! Thank you for contacting our support team. I'm here to help you today.\n\n"
        f"I can see you're experiencing a technical issue. Let's work through this together:\n"
        f"1. First, try clearing your browser cache and cookies, then reload the page.\n"
        f"2. If the issue persists, log out and log back in to refresh your session.\n"
        f"3. Check our status page at status.example.com for any known outages.\n"
        f"4. If none of these work, please share your error message or screenshot "
        f"and I'll escalate to our engineering team immediately."
    )


@tool
def handle_general(user_message: str) -> str:
    """Handle a general customer inquiry with friendly, helpful guidance.

    Use this for account questions, feature inquiries, onboarding help,
    or any question that doesn't fit billing or technical categories.

    Args:
        user_message: The customer's general question or request.
    """
    return (
        f"Hello! Thank you for contacting our support team. I'm here to help you today.\n\n"
        f"Great question! I'm happy to help you with that. Our platform offers a wide range "
        f"of features designed to make your experience seamless. If you need help with account "
        f"settings, feature setup, or have any other questions, please don't hesitate to ask. "
        f"I'm here to assist! Is there anything else I can help you with today?"
    )


CS_SYSTEM = """You are a friendly and empathetic customer service representative.

When a customer contacts you:
1. Classify their inquiry as billing, technical, or general
2. Call the matching handler tool:
   - Payment/invoice/charge/refund issues → handle_billing
   - Software bugs/errors/connectivity issues → handle_technical
   - Everything else → handle_general
3. Return the handler's response directly to the customer.
"""

graph = create_agent(
    llm,
    tools=[handle_billing, handle_technical, handle_general],
    name="customer_support",
    system_prompt=CS_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "I was charged twice for my subscription this month and need a refund.",
        )
        print(f"Status: {result.status}")
        result.print_result()
