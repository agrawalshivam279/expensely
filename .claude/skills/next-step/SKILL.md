---
name: next-step
description: Suggests the next feature to build based on the Spendly roadmap and completed specs. Use after shipping a feature to decide what to work on next.
---

You are helping a student decide what to build next in the Spendly expense tracker project.

## What to do

1. List all spec files in `.claude/specs/` to see which steps exist.
2. Check `git log --oneline` to see which steps have been merged to main.
3. Cross-reference: find the lowest-numbered spec whose feature has NOT yet been shipped (i.e., no matching commit on main).
4. Read that spec file in full.
5. Report back in this format:

---
**Next step: `<step_number>-<feature_slug>`**

**What you'll build:** <one sentence from the spec overview>

**Key things to implement:**
- <bullet from Routes section>
- <bullet from Files to change section>
- <bullet from Definition of done — pick the most important 2–3>

**To get started:** run `/create-spec <step_number> <feature description>`
---

If all specs are shipped, say so and suggest the user think about what new feature to add next (delete expense, analytics, budget limits, etc.).
