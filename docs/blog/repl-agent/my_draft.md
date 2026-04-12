I’ve heard people say that agents like Claude Code or Codex are “just wrappers around an LLM.”

If you oversimplify things… yeah, that’s not entirely wrong, kind of like saying software development is just input → processing → output, IYKWIM.

<!-- TODO: use an agent loop image -->

In practice, there’s a lot more engineering behind it.

You need to:

* provide tools the agent can actually use  
* pass the right context at the right time  
* manage interactions over time (what people now call *context engineering*)  
* and orchestrate all of this in a reliable way

That’s where frameworks come in.

There are quite a few out there. I’m part of the team building Agentspan, and through both developing it and using it, I’ve learned a lot. This post walks through one of my contributions: a coding agent with a terminal UI (inspired by tools like Claude Code), built with Agentspan and powered by Conductor OSS. I found it particularly interesting because it brings together several of the things I’ve been working on.

It’s not meant to be a production-ready replacement for those tools. But it *is* a concrete, working example that shows what’s really going on under the hood—and how you can build something similar yourself.

## What is an Agent, really?

At a high level, an agent is just a loop:

1. Take input (user message, signal, state)  
2. Decide what to do next  
3. Optionally call a tool  
4. Repeat

The real challenge is not the loop—it’s how you:

* expose capabilities (tools)  
* orchestrate execution  
* handle state over time

That’s exactly what Agentspan helps with.

---

## Context

LLMs are stateless, so every step depends on the context you send.

In this example, context is simply:

* conversation history  
* available tools  
* previous outputs

There’s a whole space around “context engineering,” but that’s not the focus here. The key idea is: the agent’s behavior is entirely driven by what you pass in each step.

---

## Tools: giving the agent real capabilities

Without tools, an agent is just a chatbot.

Tools are what make it useful.

In Agentspan, a tool is just a function:

```py
@tool
def reply_to_user(message: str) -> str:
```

That gets exposed to the LLM as something it can call.

Under the hood:

* tools map to Conductor tasks  
* the agent decides when to call them  
* execution happens outside the LLM

This separation is key:

* the LLM decides *what* to do  
* the system handles *how* it gets done

---

## Durable execution

With Agentspan, the agent loop becomes a Conductor workflow.

That gives you:

* durability (state is persisted)  
* observability (you can inspect every step)  
* control (pause, resume, retry)

This is where Agentspan becomes really interesting—it’s not just helping you define the agent, it’s giving you a reliable execution model.

In contrast, building an agent as an in-process loop might work depending on the use case, but it comes with limitations:

* if the process dies, execution is lost  
* visibility is limited  
* retries and recovery need to be handled manually

---

## Changes in Conductor (WMQ)

To support this properly, I made some changes in Conductor (WMQ-related).

(You can check the PR in the OSS repo for details.)

The goal was to make sure the agent loop behaves correctly under:

* retries  
* async execution  
* distributed workers

Without this, things break in subtle ways:

* duplicated work  
* missed signals  
* inconsistent state

This is where building agents stops being “just prompting” and starts looking like distributed systems engineering.

---

## Signaling the agent

Another key piece is how you interact with a running agent.

Instead of restarting it, you send signals:

* new user input  
* external events  
* control instructions

These signals update the workflow and become part of the next iteration.

So the loop becomes:

* wait for signal  
* update state  
* continue

This makes the agent:

* reactive  
* interruptible  
* long-lived

---

## The example: coding agent with a terminal UI

This example is a coding agent with a terminal UI, inspired by tools like Claude Code.

What it does:

* accepts user input  
* decides what to do  
* calls tools to execute actions  
* streams responses back

Under the hood:

* each step runs as a workflow  
* tools are Conductor tasks  
* state is persisted across steps

So if the process dies:

* execution is still there  
* you can resume it  
* you can inspect exactly what happened

---

## Closing

This example isn’t meant to be production-ready.

It’s meant to show:

* how agents actually work  
* how Agentspan structures them  
* how durability and orchestration fit into the picture

And honestly, building it was just fun.

---

