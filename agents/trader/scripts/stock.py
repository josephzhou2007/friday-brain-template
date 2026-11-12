#!/usr/bin/env python3
"""美股行情：Finnhub 免费接口（需免费 key，从代理 IP 也能稳定访问）。
key 来源: 环境变量 FINNHUB_API_KEY，或仓库根目录 .env（或 $FRIDAY_ENV_FILE）里的同名项。
用法: python3 stock.py NVDA AAPL TSLA
说明: 免费源 Yahoo/Stooq 经本机代理出口 IP 被限流/反爬，故改用 Finnhub。
"""
import json, os, sys, urllib.request, urllib.parse
from pathlib import Path

TIMEOUT = 8
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

def get_key():
    k = os.environ.get("FINNHUB_API_KEY")
    if k:
        return k.strip()
    env = Path(os.environ.get("FRIDAY_ENV_FILE") or Path(__file__).resolve().parents[3] / ".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("FINNHUB_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None

def quote(sym, key):
    q = urllib.parse.urlencode({"symbol": sym, "token": key})
    req = urllib.request.Request(
        f"https://finnhub.io/api/v1/quote?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)

def main(syms):
    key = get_key()
    if not key:
        print("> ⚠️ 未配置 FINNHUB_API_KEY。去 https://finnhub.io 免费注册拿 key，"
              "加到仓库根目录的 .env：FINNHUB_API_KEY=<your key>，即可用。")
        return
    print("| 标的 | 现价 | 当日% | 开盘 | 昨收 | 当日高/低 |")
    print("|---|---|---|---|---|---|")
    for s in syms:
        s = s.upper()
        try:
            d = quote(s, key)
            if not d or d.get("c") in (None, 0):
                print(f"| {s} | 无数据(代码错或非美股?) | | | | |")
                continue
            print(f"| {s} | {d['c']:.2f} | {d.get('dp', 0):+.2f}% | "
                  f"{d.get('o', 0):.2f} | {d.get('pc', 0):.2f} | "
                  f"{d.get('h', 0):.2f}/{d.get('l', 0):.2f} |")
        except Exception as e:
            print(f"| {s} | 取数失败: {e} | | | | |")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法: python3 stock.py NVDA AAPL TSLA")
        sys.exit(1)
    main(args)
