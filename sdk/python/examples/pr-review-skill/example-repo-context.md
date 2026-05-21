# PR Review Context — <repo name>

Copy this file to `.agentspan/pr-review-context.md` in your repository.
The PR reviewer skill will automatically inject it into every review bundle.
Keep it under 3,000 characters.

---

## Architecture

<describe the layers — e.g. Controller → Service → Repository>
<list key modules and what they own>

## Patterns to enforce

- <pattern 1 — e.g. every new API endpoint must have an integration test>
- <pattern 2 — e.g. all database queries go through the Repository layer, never from Controller>
- <pattern 3>

## Known gotchas

- <thing that has caused real bugs before — e.g. forgetting to flush the cache after write>
- <footgun 2>

## Testing conventions

- <where unit tests live, e.g. src/test/java/...>
- <what coverage is expected — e.g. every public service method needs a unit test>
- <mocking approach — e.g. use MockBean for Spring beans, never hit real DB in unit tests>

## Out of scope for AI review

- <files or directories the reviewer should not flag — e.g. generated protobuf files in src/generated/>
