#!/usr/bin/env python3
"""Minimal reference relay: Telegram bots  <->  Claude Code sessions in agents/<name>/.

One Telegram bot per agent. Each incoming message from the owner is wrapped as
untrusted data, handed to `claude -p` running inside that agent's directory (so
the agent's CLAUDE.md, .claude/settings.json and memory/ apply), and the reply
is sent back. The Claude session id is kept per agent, so the conversation
continues across messages until you send /new.

Standard library only. Run from the repo root:

    cp config.example.json config.json      # edit owner_id and bot names
    cp .env.example .env                      # put the bot tokens in .env
    python3 relay/relay.py

Commands (in any bot):
    /new          start a fresh Claude session for this bot
    /fb <text>    append feedback about the system to feedback/queue.jsonl
    /whoami       show your Telegram user id (works for anyone; nothing else does)

This is deliberately small. It does not do voice, images, scheduled messages,
or cross-bot routing; add those in your own fork.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".state"                 # gitignored: session ids, poll offsets
TG_LIMIT = 4096                             # Telegram's max message length
CLAUDE_TIMEOUT = int(os.environ.get("RELAY_CLAUDE_TIMEOUT", "600"))


# ---------------------------------------------------------------- config / env

def load_env(path: Path) -> None:
    """Read KEY=VALUE lines into os.environ without overriding real env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text())
    if not isinstance(cfg.get("owner_id"), int) or cfg["owner_id"] <= 0:
        raise SystemExit("config.json: owner_id must be your numeric Telegram user id (send /whoami to a bot)")
    for b in cfg.get("bots", []):
        if not (ROOT / "agents" / b["agent"] / "CLAUDE.md").exists():
            raise SystemExit(f"config.json: agents/{b['agent']}/CLAUDE.md not found")
        if not os.environ.get(b["token_env"]):
            raise SystemExit(f"{b['token_env']} is not set (put it in .env)")
    return cfg


# ---------------------------------------------------------------- small helpers

def wrap_untrusted(text: str, source: str = "telegram") -> str:
    """Wrap user-supplied text so the agent treats it as data.

    A message that itself contains the closing tag could otherwise end the
    wrapper early and smuggle text outside it, so the tag is neutralised
    inside the content (prompt-injection hygiene, not a security boundary
    on its own: the agent's CLAUDE.md rules are what actually matter).
    """
    safe = text.replace("</untrusted_message", "<\\/untrusted_message")
    return f'<untrusted_message source="{source}">\n{safe}\n</untrusted_message>'


def chunks(text: str, limit: int = TG_LIMIT) -> list[str]:
    """Split on paragraph/line boundaries where possible, hard-cut otherwise."""
    text = text.strip() or "(empty reply)"
    out = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    out.append(text)
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


class JsonStore:
    """Tiny thread-safe JSON dict on disk (session ids, poll offsets)."""

    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        self.data = json.loads(path.read_text()) if path.exists() else {}

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def set(self, key, value) -> None:
        with self.lock:
            if value is None:
                self.data.pop(key, None)
            else:
                self.data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2))
            tmp.replace(self.path)          # atomic: never a half-written file


# ---------------------------------------------------------------- Telegram

class Telegram:
    def __init__(self, token: str, http=None):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.http = http or self._http

    @staticmethod
    def _http(url: str, payload: dict, timeout: float) -> dict:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    def call(self, method: str, timeout: float = 70, **payload) -> dict:
        res = self.http(self.base + method, payload, timeout)
        if not res.get("ok"):
            raise RuntimeError(f"telegram {method}: {res.get('description')}")
        return res["result"]

    def send(self, chat_id: int, text: str) -> None:
        for part in chunks(text):
            self.call("sendMessage", timeout=30, chat_id=chat_id, text=part)


# ---------------------------------------------------------------- Claude

def run_claude(agent_dir: Path, prompt: str, session_id: str | None) -> tuple[str, str | None]:
    """Run one turn of `claude -p` in agent_dir; return (reply, session_id)."""
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if session_id:
        cmd += ["--resume", session_id]
    p = subprocess.run(cmd, cwd=agent_dir, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT)
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude exited {p.returncode}: {(p.stderr or p.stdout)[-500:]}")
    if out.get("is_error") or out.get("subtype") not in (None, "success"):
        raise RuntimeError(f"claude error: {str(out.get('result') or out)[:500]}")
    return out.get("result") or "", out.get("session_id")


# ---------------------------------------------------------------- one bot

class Bot:
    def __init__(self, name: str, agent: str, tg: Telegram, owner_id: int,
                 sessions: JsonStore, offsets: JsonStore, claude=run_claude, root: Path = ROOT):
        self.name, self.agent, self.tg, self.owner_id = name, agent, tg, owner_id
        self.sessions, self.offsets, self.claude, self.root = sessions, offsets, claude, root
        self.agent_dir = root / "agents" / agent

    def handle(self, update: dict) -> None:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return
        chat_id, user = msg["chat"]["id"], msg.get("from", {}).get("id")
        text = msg.get("text") or msg.get("caption") or ""

        if text.strip() == "/whoami":                       # the only thing strangers get
            self.tg.send(chat_id, f"Your Telegram user id: {user}")
            return
        if user != self.owner_id or msg["chat"].get("type") != "private":
            print(f"[{self.name}] ignored message from {user}", file=sys.stderr)
            return                                           # silent: don't confirm the bot exists

        append_jsonl(self.root / "inbox" / f"{datetime.now().date()}.jsonl",
                     {"t": now_iso(), "source": "telegram", "id": f"{chat_id}:{msg['message_id']}",
                      "bot": self.name, "note": ""})        # a pointer, never the message text

        if text.strip() == "/new":
            self.sessions.set(self.name, None)
            self.tg.send(chat_id, "New session.")
            return
        if text.startswith("/fb"):
            body = text[3:].strip()
            if not body:
                self.tg.send(chat_id, "Usage: /fb <what is wrong or what you want changed>")
                return
            append_jsonl(self.root / "feedback" / "queue.jsonl",
                         {"t": now_iso(), "bot": self.name, "kind": "fb", "text": body, "status": "open"})
            self.tg.send(chat_id, "Noted in feedback/queue.jsonl.")
            return
        if not text:
            self.tg.send(chat_id, "This relay only handles text for now.")
            return

        self.tg.call("sendChatAction", timeout=10, chat_id=chat_id, action="typing")
        prompt = wrap_untrusted(text)
        sid = self.sessions.get(self.name)
        try:
            reply, new_sid = self.claude(self.agent_dir, prompt, sid)
        except Exception as e:
            if sid:                                          # a stale session is the usual cause
                self.sessions.set(self.name, None)
                try:
                    reply, new_sid = self.claude(self.agent_dir, prompt, None)
                except Exception as e2:
                    self.tg.send(chat_id, f"⚠️ {e2}")
                    return
                reply = "(previous session could not be resumed; started a new one)\n\n" + reply
            else:
                self.tg.send(chat_id, f"⚠️ {e}")
                return
        if new_sid:
            self.sessions.set(self.name, new_sid)
        self.tg.send(chat_id, reply)

    def poll_forever(self) -> None:
        print(f"[{self.name}] polling -> agents/{self.agent}")
        while True:
            try:
                offset = self.offsets.get(self.name, 0)
                for upd in self.tg.call("getUpdates", offset=offset, timeout=50,
                                        allowed_updates=["message", "edited_message"]):
                    # advance first: a message that crashes the handler is not retried forever
                    self.offsets.set(self.name, upd["update_id"] + 1)
                    try:
                        self.handle(upd)
                    except Exception as e:
                        print(f"[{self.name}] handler error: {e}", file=sys.stderr)
            except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
                print(f"[{self.name}] poll error: {e}; retrying in 5s", file=sys.stderr)
                time.sleep(5)


def main() -> None:
    load_env(Path(os.environ.get("FRIDAY_ENV_FILE") or ROOT / ".env"))
    cfg = load_config(Path(os.environ.get("RELAY_CONFIG") or ROOT / "config.json"))
    sessions, offsets = JsonStore(STATE_DIR / "sessions.json"), JsonStore(STATE_DIR / "offsets.json")
    threads = []
    for b in cfg["bots"]:
        bot = Bot(b["name"], b["agent"], Telegram(os.environ[b["token_env"]]), cfg["owner_id"], sessions, offsets)
        t = threading.Thread(target=bot.poll_forever, name=b["name"], daemon=True)
        t.start()
        threads.append(t)
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
