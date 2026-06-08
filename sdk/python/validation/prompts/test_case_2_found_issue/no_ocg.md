I just hit a bug on my Mac: `agentspan doctor` reports `Java 17.0.19 (21+ required)` even though I have `openjdk@21` installed via Homebrew alongside `openjdk@17`. It looks like the tool is picking the older formula.

Before I file an issue or start fixing, I want to know:
1. Has this already been reported on GitHub (`agentspan-ai/agentspan`)?
2. Is there existing code for the JDK-selection logic in `agentspan doctor`, so I know where a fix would land?

The local checkout is at `~/PycharmProjects/agentspan`.

Answer in plain English. Be concise.
