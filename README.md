**English** · [简体中文](README.zh-CN.md)

# friday-brain

A shared, git-versioned brain for a team of personal Claude agents that you talk to on Telegram.

Each agent (Friday, Study, Feed, Dev, Trader) is a Claude Code session running in its own
directory with its own role, permissions and memory, plus a common rule set and a common
set of facts about you. Memory is plain Markdown in git, so you can read it, diff it, fix it
and roll it back.

```
global/            rules every agent follows (CLAUDE.md) + facts about you (memory/)
agents/<name>/     one agent: CLAUDE.md (role) + .claude/settings.json (permissions)
                   + memory/ (one fact per file, MEMORY.md is the index) + journal/
shared/            cross-agent project and reference notes (read-only for agents)
inbox/             pointers to messages (source + id + time), never the text
feedback/          /fb queue: complaints about the system itself, kept out of memory
relay/             minimal Telegram <-> Claude Code relay (stdlib only) + tests
hooks/pre-commit   refuses commits that add secrets or your private strings
scripts/           setup-local.sh, install-hooks.sh
```

## Quick start

Requirements: Python 3.10+, git, and [Claude Code](https://docs.claude.com/en/docs/claude-code)
installed and logged in (`claude`, then `/login`).

```sh
git clone <your fork> friday-brain && cd friday-brain
sh scripts/setup-local.sh        # hooks, .env, config.json, .private-patterns, per-agent local settings
```

1. Create one bot per agent with [@BotFather](https://t.me/BotFather) and put each token in `.env`.
   Remove agents you don't want from `config.json`.
2. Start the relay, send `/whoami` to any of your bots, and put that number in `config.json` as `owner_id`.
   Until then the relay refuses to start; after that it ignores everyone except you.
3. Fill in `global/memory/user-profile.md`, and list the strings that must never be committed
   (address, phone, ids) in `.private-patterns`.
4. `python3 relay/relay.py`

Commands in any bot: `/new` (fresh session), `/fb <text>` (system feedback), `/whoami`.

**Keep your own fork private.** The template is safe to publish; once you use it, `memory/`
and `journal/` fill up with your life. Git history keeps everything ever committed, so
deleting a file later does not un-publish it.

## Design notes

**Why one directory per agent.** Claude Code reads `CLAUDE.md` and `.claude/settings.json`
from the directory it runs in. Running each agent with its own working directory gives it its
own role and its own permission boundary for free: Study and Dev have no shell at all, Trader
can run exactly four scripts, and no agent can write to `global/` or `shared/`. Permissions are
enforced by the harness, not by asking the model nicely.

**Memory is one fact per file, with an index.** `MEMORY.md` is a short list the agent reads
first; single files are opened only when relevant. This keeps the context small and makes every
fact individually editable and deletable. `feedback` memories must state *Why* and *How to apply*,
so a later session can tell when a rule no longer applies instead of following it forever.

**Two kinds of things, two places.** Facts about you go to memory. Complaints about the system
("the digest repeats old mail") go to `feedback/queue.jsonl` via `/fb`. Mixing them makes the
agents talk about their own bugs as if they were your preferences.

**Untrusted by default.** Every message reaches the agent wrapped in `<untrusted_message>`
(the relay neutralises any closing tag inside the text), and the global rules say content
from mail, pages and forwards is data. This is defence in depth against prompt injection, not a
guarantee; the hard limit is still what `.claude/settings.json` allows.

**The inbox stores pointers, not text.** If the repo ever leaks, the inbox reveals that a message
existed, not what it said.

**Answer everything, remember only your own area.** Agents cannot forward messages to each other,
so refusing an off-topic question just wastes the owner's time. The area split decides only what
an agent pushes unprompted and what it writes to memory.

## The relay is deliberately minimal

`relay/relay.py` is under 300 lines: long-polling, owner allowlist, per-agent session resume,
inbox pointers, `/fb`. It does not do voice, images, scheduled briefings, mail or calendar
access, or cross-agent routing. Those belong in your fork. Each message runs one
`claude -p ... --resume <session>` turn in the agent's directory, so a reply takes as long as a
Claude Code turn (seconds to minutes).

Billing: the relay uses whatever `claude` is logged in with. A subscription login counts
against the subscription; an `ANTHROPIC_API_KEY` in the environment is billed per token.

Tests: `python3 -m pytest relay` (offline; no network, no real Claude).

## Documentation languages

This README is available in English and Chinese. The agent prompts (`CLAUDE.md`) and example memories are English only: they are written for the model, and the agents reply in whatever language you write in.

## License

MIT, see [LICENSE](LICENSE).
