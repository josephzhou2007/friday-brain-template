---
name: Voice transcripts
description: Handling speech-to-text messages
metadata:
  type: feedback
---
Many messages are dictated. Speech-to-text produces homophone errors on product names
("deep seek" split into words, a tool name heard as a common word) and sometimes cuts off mid-sentence.

**Why:** guessing the missing half of a cut-off instruction leads to doing the wrong thing confidently.

**How to apply:** read names for intent; if a sentence clearly stops early, ask briefly
what the rest was instead of acting on a guess.
