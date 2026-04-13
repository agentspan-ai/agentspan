# Review Notes: REPL Agent Blog Post

## Existing Agentspan blog posts

### AI Agents 101 (Maria)
https://medium.com/agentspan/ai-agents-101-d82a0a0f4274

**Key claims:**
- "A common misconception about AI agents I still hear from a lot of people is that they're only big, complex systems like Claude Code"
- "An agent is just an LLM system that runs in a loop and has a goal given to it by a user"
- Agents have four components: LLM ("the brain"), tools ("the hands"), a loop, and memory

**Issues flagged:**
- The "misconception" claim is backwards. The common take online is that agents are "just wrappers around an LLM" (e.g. https://www.reddit.com/r/AgentsOfAI/comments/1mik3nx/most_ai_agents_today_are_just_glorified_wrappers/). Our REPL post starts from that angle.
- "An agent is an LLM system that runs in a loop" is technically wrong. An agent is the loop. The LLM is one component inside it. The agent *uses* an LLM, it isn't one. This distinction matters — it's our value prop.

### Open-Sourcing Agentspan (launch post)
https://medium.com/agentspan/open-sourcing-agentspan-durable-ai-agents-069adca43315

**Key claims:**
- "The problem isn't the agents. They work beautifully in a demo. The problem is there is nowhere to run them that survives the real world."
- Frames the entire problem as infrastructure/runtime: durability, state, HITL, orchestration, observability.

**Issues flagged:**
- "There is nowhere to run them" is an overstatement. Other frameworks and approaches exist.
- "The problem isn't the agents" is only partially true. Context engineering, tool design, and prompt structure are agent-level problems, not runtime problems.

---

## Coherence issues in our REPL post

### 1. "Not prompting problems" is repeated 5 times across 2 posts

| File | Line | Text |
|---|---|---|
| `01_overview.md` | 33 | "These aren't problems that stronger models solve. They're engineering problems." |
| `01_overview.md` | 45 | "None of these are prompting problems." |
| `01_overview.md` | 111 | "Agent development isn't 'just prompting.'" |
| `02_developers.md` | 43 | "These aren't prompting problems." |
| `02_developers.md` | 183 | "The hard problems in agent development aren't about prompting." |

The point lands the first time. After that it sounds like we're arguing with someone who isn't in the room. Consider keeping it once per post.

### 2. "Demos work, production doesn't" echoes the launch post

- `01_overview.md:39` — "It works wonderfully until you try to run it in production."
- `02_developers.md:36` — "The real challenge isn't the loop—it's what happens when you try to run it in production"

This is essentially the same claim as the launch post's "They work beautifully in a demo." Ours is more measured (we don't say "nowhere to run them"), but a reader who's seen the launch post will read the same argument again, not a deeper one.

### 3. "Infrastructure" framing may be too narrow

The overview conclusion says: "Frameworks like Agentspan exist to handle the infrastructure — durability, message queuing, session isolation, event streaming"

The developers conclusion says: "The hard problems in agent development aren't about prompting. They're about distributed systems"

Both frame Agentspan's value purely as infrastructure. But throughout the post we also show value in tool design (`@tool` decorator), agent definition (compile to workflow), context management (signals), and developer experience. The conclusions undersell the post.

---

## TODO before publishing

- [ ] Reduce "not prompting" repetition to once per post
- [ ] Differentiate from the launch post — our angle is "here's what we learned building something concrete," not "demos don't survive production"
- [ ] Review conclusions — they should reflect the full range of what the post covers, not just infra
