---
title: Documentation
description: Agentspan documentation for building production AI agents.
---

# Documentation

**Agentspan is a durable runtime for AI agents. Your code runs in your process. Execution state lives on the server.**

Agentspan is a durable runtime for AI agents. Execution state lives server-side, so crashes, restarts, and deployments do not lose work. Write agents natively or wrap an existing LangGraph, OpenAI Agents SDK, or Google ADK agent in one line.

## Getting Started

- [Why Agentspan](why-agentspan.md) - Why agents fail in production, and how Agentspan solves it.
- [Quickstart](quickstart.md) - Build your first agent in 5 minutes.

## Concepts

- [Agents](concepts/agents.md) - The `Agent` class, parameters, results, and handles.
- [Tools](concepts/tools.md) - `@tool`, `http_tool()`, `api_tool()`, `mcp_tool()`, credentials, and approval-required tools.
- [Multi-Agent Strategies](concepts/multi-agent.md) - Sequential, parallel, handoff, router, and nested agent coordination.
- [Guardrails](concepts/guardrails.md) - Input and output safety, retry, block, and fix behavior.
- [Memory](concepts/memory.md) - Conversation history and semantic search across sessions.
- [Streaming](concepts/streaming.md) - Runtime events, async execution, and HITL with streams.
- [Testing](concepts/testing.md) - `mock_run`, `expect`, record/replay, pytest, and evaluation helpers.

## Deployment

- [Deployment overview](deployment.md) - Local development, Docker, Helm, and Orkes Cloud.
- [Self-hosting](self-hosting.md) - Run Agentspan in your own environment.

## Examples

- [Support Ticket Triage](examples/support-triage.md) - Classify, route, and resolve support tickets.
- [Research Pipeline](examples/research-pipeline.md) - Run sequential research, writing, and editing agents.
- [Batch Document Processor](examples/document-processor.md) - Process multiple documents in parallel.
- [Crash and Resume](examples/crash-resume.md) - Resume durable executions after worker failure.
- [Human in the Loop](examples/human-in-the-loop.md) - Pause execution for human approval.
- [LangGraph Code Review Bot](examples/langgraph.md) - Wrap an existing LangGraph app.
- [OpenAI Agents SDK Customer Support](examples/openai-agents-sdk.md) - Run an OpenAI Agents SDK app through Agentspan.
- [Google ADK Research Assistant](examples/google-adk.md) - Run a Google ADK agent through Agentspan.

## Reference

- [CLI Reference](cli.md) - Commands with exact syntax.
- [LLM Providers](providers.md) - Providers, model strings, and API keys.
- [AI Models](ai-models.md) - Model configuration and supported provider formats.
- [Integrations](integrations.md) - Framework integrations and compatibility notes.
- [Worker Types](worker-types.md) - Python and TypeScript worker models.
