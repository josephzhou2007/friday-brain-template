---
name: Confirm before writing
description: Rule for writing new conclusions about the owner into memory
metadata:
  type: feedback
---
New conclusions about the owner (opinions, mistakes, decisions, insights) are shown to the
owner as a proposed change and written only after they agree. Automatic maintenance only
merges, deduplicates, fixes the index and removes expired items; it never adds judgements.

**Why:** an agent that writes its own interpretations of the owner into shared memory
slowly replaces the owner's view of themselves with the agent's guesses, and every other
agent then reads those guesses as facts.

**How to apply:** when something seems worth keeping, end the reply with one line
"Save this? …"; write it if the owner says yes. Purely operational facts (a task is done,
a path changed) can be updated directly.
