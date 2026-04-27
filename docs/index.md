---
title: Documentation
description: Agentspan documentation for building durable AI agents.
---

# Documentation

**Agentspan is a durable runtime for AI agents. Your code runs in your process. Execution state lives on the server.**

Agentspan keeps agent execution state server-side so crashes, restarts, and deployments do not lose work. You can define agents directly with the Agentspan Python SDK, or wrap existing LangGraph, OpenAI Agents SDK, and Google ADK agents.

## Getting started

- [Why Agentspan](why-agentspan.md) explains the production failure modes Agentspan is designed around.
- [Quickstart](quickstart.md) walks through installation, server startup, and a first agent run.

## Core concepts

- [Agents](concepts/agents.md) covers the `Agent` class, runtime execution model, results, and handles.
- [Tools](concepts/tools.md) covers `@tool`, `http_tool()`, `api_tool()`, `mcp_tool()`, credentials, and code execution.
- [Multi-Agent Strategies](concepts/multi-agent.md) covers sequential, parallel, handoff, router, and related coordination modes.
- [Guardrails](concepts/guardrails.md) covers input and output validation.
- [Memory](concepts/memory.md) covers conversation and semantic memory.
- [Streaming](concepts/streaming.md) covers runtime events and async execution.
- [Testing](concepts/testing.md) covers deterministic tests, record/replay, and evaluation helpers.

## Examples

- [Support Ticket Triage](examples/support-triage.md)
- [Research Pipeline](examples/research-pipeline.md)
- [Batch Document Processor](examples/document-processor.md)
- [Crash and Resume](examples/crash-resume.md)
- [Human in the Loop](examples/human-in-the-loop.md)
- [LangGraph Code Review Bot](examples/langgraph.md)
- [OpenAI Agents SDK Customer Support](examples/openai-agents-sdk.md)
- [Google ADK Research Assistant](examples/google-adk.md)

## Reference

- [Providers](providers.md)
- [AI Models](ai-models.md)
- [CLI](cli.md)
- [Deployment](deployment.md)
- [Self-Hosting](self-hosting.md)
- [Integrations](integrations.md)
- [Worker Types](worker-types.md)
