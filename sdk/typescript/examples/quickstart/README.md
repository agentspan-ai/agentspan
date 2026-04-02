# Quickstart Examples

Minimal examples that define and run agents in a single script.
Use `runtime.run(agent, prompt)` which handles deploy + workers + execution automatically.

Great for learning and prototyping. The main examples now use the same
`runtime.run()` happy path by default and keep deploy/serve as commented
production guidance when you need a long-lived worker process.

```bash
# Run any example:
npx tsx quickstart/01-basic-agent.ts
```
