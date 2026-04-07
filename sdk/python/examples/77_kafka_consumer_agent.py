# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Kafka → Workflow Message Queue bridge — forward Kafka records to a running agent.

Demonstrates:
    - wait_for_message_tool: agent blocks waiting for messages via WMQ
    - A Kafka consumer loop running in a background thread that forwards
      each record to the workflow via runtime.send_message()
    - echo_message: inline tool that prints each received payload

The agent loops forever:
    1. wait_for_message()  — dequeue the next WMQ message (pushed by Kafka consumer)
    2. echo_message()      — echo the value to the console
    3. Back to step 1

Requirements:
    - Kafka broker on localhost:9092 with topic le_random_topic
    - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
    - confluent-kafka  (uv pip install confluent-kafka)
"""

from confluent_kafka import Consumer, KafkaError

from agentspan.agents import Agent, AgentRuntime, tool, wait_for_message_tool
from settings import settings

KAFKA_BOOTSTRAP = "localhost:9092"
KAFKA_TOPIC = "le_random_topic"
KAFKA_GROUP = "agentspan-echo-group"


@tool
def echo_message(value: str, topic: str, offset: int) -> str:
    """Echo a received Kafka record to the console."""
    line = f"[{topic}@{offset}] {value}"
    print(line)
    return line


receive_message = wait_for_message_tool(
    name="wait_for_message",
    description="Wait for the next Kafka record forwarded to this agent.",
)

agent = Agent(
    name="kafka_echo_agent",
    model=settings.llm_model,
    tools=[receive_message, echo_message],
    max_turns=100_000,
    instructions=(
        "You are a Kafka consumer agent that runs forever. "
        "Repeat this cycle indefinitely without stopping: "
        "1. Call wait_for_message to receive the next Kafka record. "
        "2. Call echo_message with the value, topic, and offset from the message payload. "
        "3. Go back to step 1 immediately."
    ),
)


with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Start consuming messages from Kafka.")
    print(f"Agent started: {handle.execution_id}")

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": KAFKA_GROUP,
            "auto.offset.reset": "latest",
        }
    )
    consumer.subscribe([KAFKA_TOPIC])
    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(f"Kafka error: {msg.error()}")
            runtime.send_message(
                handle.execution_id,
                {
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "key": msg.key().decode("utf-8") if msg.key() else None,
                    "value": msg.value().decode("utf-8") if msg.value() else "",
                },
            )
    finally:
        consumer.close()
