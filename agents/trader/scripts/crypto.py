#!/usr/bin/env python3
"""永续行情：OKX + Hyperliquid 公共接口（免费、无需 key）。
用法: python3 crypto.py BTC ETH SOL
输出: 每个币种在两家的 价格 / 24h涨跌 / 资金费率 / 成交额，Markdown 表格。
"""
import json, sys, urllib.request

TIMEOUT = 8

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def _get(url, data=None):
    headers = {"User-Agent": UA}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)

def okx(sym):
    inst = f"{sym}-USDT-SWAP"
    try:
        t = _get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}")["data"][0]
        last, open24 = float(t["last"]), float(t["open24h"])
        pct = (last - open24) / open24 * 100 if open24 else 0.0
        try:
            fr = float(_get(f"https://www.okx.com/api/v5/public/funding-rate?instId={inst}")["data"][0]["fundingRate"]) * 100
        except Exception:
            fr = None
        # OKX volCcy24h 是币本位数量，× 价格换算成 USD 名义额，与 HL 口径对齐
        return {"price": last, "pct": pct, "funding": fr, "vol": float(t.get("volCcy24h", 0)) * last}
    except Exception:
        return None

def hl_all():
    meta, ctxs = _get("https://api.hyperliquid.xyz/info",
                      json.dumps({"type": "metaAndAssetCtxs"}).encode())
    out = {}
    for u, c in zip(meta["universe"], ctxs):
        mark, prev = float(c["markPx"]), float(c.get("prevDayPx") or 0)
        out[u["name"].upper()] = {
            "price": mark,
            "pct": (mark - prev) / prev * 100 if prev else 0.0,
            "funding": float(c.get("funding", 0)) * 100,
            "vol": float(c.get("dayNtlVlm", 0)),
        }
    return out

def fmt(v):
    if v is None:
        return "—"
    if v >= 1000:
        return f"{v:,.0f}"
    return f"{v:.4f}".rstrip("0").rstrip(".")

def main(syms):
    hl = {}
    try:
        hl = hl_all()
    except Exception as e:
        print(f"> Hyperliquid 取数失败: {e}\n")
    print("| 币种 | 交易所 | 价格 | 24h% | 资金费率 | 24h成交额(USD) |")
    print("|---|---|---|---|---|---|")
    for s in syms:
        s = s.upper()
        o = okx(s)
        h = hl.get(s)
        if o:
            ofund = f"{o['funding']:+.4f}%" if o['funding'] is not None else '—'
            print(f"| {s} | OKX(8h) | {fmt(o['price'])} | {o['pct']:+.2f}% | "
                  f"{ofund} | {fmt(o['vol'])} |")
        if h:
            print(f"| {s} | HL(1h) | {fmt(h['price'])} | {h['pct']:+.2f}% | "
                  f"{h['funding']:+.4f}% | {fmt(h['vol'])} |")
        if not o and not h:
            print(f"| {s} | — | 两家都没找到该永续 | | | |")

if __name__ == "__main__":
    args = sys.argv[1:] or ["BTC", "ETH", "SOL"]
    main(args)
