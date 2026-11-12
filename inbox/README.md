# inbox/ — pointers only

One JSON per line: `{"t": "<ISO time>", "source": "telegram|mail|...", "id": "<id in the source>", "bot": "<agent>", "note": "<short label>"}`.
**Never the message text.** The original stays in its source (Telegram, your mail app, ...).
One file per day: `inbox/YYYY-MM-DD.jsonl`. The reference relay appends one line per message it handles.
