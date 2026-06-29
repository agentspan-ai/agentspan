# Termination Conditions

Termination conditions stop a multi-agent loop before it hits `maxTurns`. They are particularly useful in swarm and conversation patterns where you don't know upfront how many turns are needed.

## Available conditions

### MaxMessageTermination

Stop after a fixed number of messages:

```java
import org.conductoross.conductor.ai.termination.MaxMessageTermination;

Agent agent = Agent.builder()
    .termination(MaxMessageTermination.of(10))
    .build();
```

### StopMessageTermination

Stop when the agent outputs a specific string:

```java
import org.conductoross.conductor.ai.termination.StopMessageTermination;

Agent agent = Agent.builder()
    .termination(StopMessageTermination.of("TASK_COMPLETE"))
    .build();
```

Instruct the agent in its system prompt:

```
When you have finished the task, output exactly: TASK_COMPLETE
```

### TextMentionTermination

Stop when the output mentions specific text (optionally case-sensitive):

```java
import org.conductoross.conductor.ai.termination.TextMentionTermination;

// Case-insensitive (default)
TextMentionTermination.of("done")

// Case-sensitive
TextMentionTermination.of("DONE", true)
```

### TokenUsageTermination

Stop when cumulative token usage exceeds a limit — useful for cost control:

```java
import org.conductoross.conductor.ai.termination.TokenUsageTermination;

// Stop after 50,000 total tokens
Agent agent = Agent.builder()
    .termination(TokenUsageTermination.ofTotal(50_000))
    .build();
```

## Composing conditions

Chain conditions with `and()` / `or()`:

```java
// Stop when BOTH are true: max 20 messages AND output contains "DONE"
TerminationCondition both = MaxMessageTermination.of(20)
    .and(StopMessageTermination.of("DONE"));

// Stop when EITHER is true: max 20 messages OR output contains "DONE"
TerminationCondition either = MaxMessageTermination.of(20)
    .or(StopMessageTermination.of("DONE"));

Agent agent = Agent.builder()
    .termination(either)
    .build();
```
