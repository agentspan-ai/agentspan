# Skills

A Skill is a portable, self-contained agent capability stored as a directory. You write a `SKILL.md` file describing the agent's purpose and workflow; the SDK loads it as a fully-configured `Agent` ready to run.

## Skill directory layout

```
my-skill/
├── SKILL.md              # Required — name, description, workflow instructions
├── search-agent.md       # Optional — sub-agent definitions
├── writer-agent.md
└── scripts/              # Optional — scripts the agent can execute
    └── process.py
```

## SKILL.md format

```markdown
---
name: code_review
params:
  language:
    default: java
---

## Overview
Reviews code for bugs, style issues, and security vulnerabilities.

## Workflow
1. Read the code from the user's message.
2. Call the analyse_code tool with the code and language.
3. Return a structured review with severity levels.
```

## Loading a skill

```java
import org.conductoross.conductor.ai.skill.Skill;
import java.nio.file.Paths;

// Load a single skill
Agent reviewAgent = Skill.skill(Paths.get("skills/code-review"), "openai/gpt-4o");

// Override sub-agent models
Agent reviewAgent = Skill.skill(
    Paths.get("skills/code-review"),
    "openai/gpt-4o",
    Map.of("search-agent", "anthropic/claude-sonnet-4-6")  // cheaper model for search
);

// Load all skills from a directory
Map<String, Agent> allSkills = Skill.loadSkills(Paths.get("skills"), "openai/gpt-4o");

// Run a loaded skill
try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(reviewAgent, "Review this Java code: ...");
}
```

## Sub-agent files (`*-agent.md`)

Each `*-agent.md` file defines a sub-agent within the skill:

```markdown
---
name: analyse_code
description: Analyse code for issues
---

You are a code analysis specialist. When given code:
1. Check for common bugs and anti-patterns.
2. Identify security vulnerabilities.
3. Return a JSON list of findings with severity (low/medium/high).
```

## Error handling

```java
import org.conductoross.conductor.ai.skill.SkillLoadError;

try {
    Agent skill = Skill.skill(Paths.get("skills/missing"), "openai/gpt-4o");
} catch (SkillLoadError e) {
    System.err.println("Failed to load skill: " + e.getMessage());
}
```

## Publishing and sharing skills

Skills are plain files — commit them to your repo, share them via Git, or distribute as JARs. The `Skill.skill()` loader accepts any `Path`, including paths inside JARs via `FileSystem`:

```java
// Load a skill bundled inside a JAR on the classpath
try (var fs = FileSystems.newFileSystem(uri, Map.of())) {
    Agent bundledSkill = Skill.skill(fs.getPath("/skills/my-skill"), "openai/gpt-4o");
}
```
