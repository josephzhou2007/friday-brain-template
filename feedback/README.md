# feedback/

The owner's feedback about the system itself. `/fb <problem>` in any bot appends a line to
`queue.jsonl`: time, bot, kind, text, status (`open` / `done`). Agents read it to answer
"was that fixed?"; you (or a scheduled maintenance session) work through the open items.
