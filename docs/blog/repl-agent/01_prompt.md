I have a draft blog post about [topic]. The draft is in [path to draft file].

Read the draft carefully — it captures my voice and the ideas I want to convey. Don't rewrite it from scratch; use it as the foundation.

Create 3 audience-specific versions of this post, all sharing the same title:

1. **overview.md** — For engineering leadership. Narrative-driven, minimal code (one snippet at most). Focus on the "why" and architecture decisions. Keep it concise.

2. **developers.md** — For developers evaluating the framework/tool. Some code snippets to illustrate concepts, but focus on what it does and why, not how to implement it step by step. Include links to PRs or repos where relevant.

3. **developers_extended.md** — For hands-on builders who want to use this themselves. Code-heavy with full implementations, data structures, threading models, event types. This is the reference they'll keep open while building.

Guidelines:
- Keep my voice. If the draft is casual, the posts should be casual.
- Don't overstate difficulty or hype things up. If something was straightforward, say so.
- Don't add sections about problems that didn't actually come up during the work.
- Be precise with technical terms — don't conflate different layers of the stack.
- If the example isn't production-ready, say so upfront as a note (use a > blockquote).
- Include links to relevant PRs, repos, or docs at natural points in the text.
- Each post should stand on its own — a reader shouldn't need to read the others.

Write all 3 files to [output directory], then let me review each one. Expect iteration — I'll flag anything that doesn't sound right or isn't accurate.
