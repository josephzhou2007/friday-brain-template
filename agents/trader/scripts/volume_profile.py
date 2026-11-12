#!/usr/bin/env python3
"""三源成本分布图 (Volume Profile) —— 盘手标准出图工具。

对任意标的，按优先级在三个来源找"带成交量的历史K线"，据此算成本分布：
  1. OKX 永续    (<SYM>-USDT-SWAP)   —— 股票永续 + 加密，量价历史完整，首选
  2. Hyperliquid (candleSnapshot)     —— 仅加密币
  3. 正规交易所   (Yahoo chart JSON)    —— 美股/韩股等现货历史；本机代理常被 429 限流

输出：
  - 一张 PNG：横向成交量分布 + POC(主力成本) + 价值区70% + 现价线
  - 一行 JSON 摘要（现价/POC/价值区/现价相对POC/用了哪个源/资金费率）

用法:
  python3 volume_profile.py SKHYNIX            # 自动挑源
  python3 volume_profile.py MSFT --source okx
  python3 volume_profile.py BTC  --source hl
  python3 volume_profile.py ASST --source yahoo --yahoo-sym ASST
  python3 volume_profile.py 000660.KS --source yahoo --yahoo-sym 000660.KS

说明：
  - HL 只有加密；股票请走 OKX 或 Yahoo。
  - Yahoo 若 429，脚本会明确报"历史不可用"，不会假装出图。
  - POC = 成交最密集价位 ≈ 市场平均成本；价值区 = 70% 成交发生的价格带。
"""
import argparse, json, sys, time, urllib.request, urllib.parse
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
OUTDIR = Path(__file__).resolve().parent.parent


def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _post(url, payload, timeout=20):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ---------- 数据源：返回 [(low, high, close, vol_quote), ...] 最新在前 ----------

def _okx_instid(sym):
    """在 OKX SWAP 里找匹配的 instId。先精确 <SYM>-USDT-SWAP，再模糊。"""
    sym = sym.upper().replace("-USDT-SWAP", "")
    data = _get("https://www.okx.com/api/v5/public/instruments?instType=SWAP")["data"]
    ids = [x["instId"] for x in data]
    exact = f"{sym}-USDT-SWAP"
    if exact in ids:
        return exact
    cand = [i for i in ids if i.upper().startswith(sym + "-") or sym in i.upper()]
    return cand[0] if cand else None


def src_okx(sym, metric="qty"):
    inst = _okx_instid(sym)
    if not inst:
        raise LookupError(f"OKX 无 {sym} 永续")
    c = _get(f"https://www.okx.com/api/v5/market/candles?instId={inst}&bar=1H&limit=300")["data"]
    # r: [ts,o,h,l,c,vol(张),volCcy(基础),volCcyQuote(USDT),confirm]
    wi = 5 if metric == "qty" else 7
    bars = [(float(r[3]), float(r[2]), float(r[4]), float(r[wi])) for r in c]  # l,h,c,weight
    t = _get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}")["data"][0]
    meta = {"inst": inst, "open24h": float(t["open24h"]), "last": float(t["last"])}
    try:
        f = _get(f"https://www.okx.com/api/v5/public/funding-rate?instId={inst}")["data"][0]
        meta["funding_8h_pct"] = float(f["fundingRate"]) * 100
    except Exception:
        meta["funding_8h_pct"] = None
    return bars, meta, "OKX 永续 " + inst


def src_hl(sym, metric="qty"):
    sym = sym.upper()
    meta = _post("https://api.hyperliquid.xyz/info", {"type": "meta"})
    coins = [u["name"] for u in meta["universe"]]
    if sym not in coins:
        raise LookupError(f"HL 无 {sym}（HL 仅加密）")
    end = int(time.time() * 1000)
    start = end - 300 * 3600 * 1000
    c = _post("https://api.hyperliquid.xyz/info",
              {"type": "candleSnapshot",
               "req": {"coin": sym, "interval": "1h", "startTime": start, "endTime": end}})
    c = list(reversed(c))  # 最新在前
    # x['v'] = 基础成交量(币数); qty=币数, value=币数*收盘≈USD
    bars = [(float(x["l"]), float(x["h"]), float(x["c"]),
             float(x["v"]) if metric == "qty" else float(x["v"]) * float(x["c"])) for x in c]
    m = {"inst": sym, "last": bars[0][2], "open24h": bars[min(23, len(bars) - 1)][2],
         "funding_8h_pct": None}
    return bars, m, "Hyperliquid " + sym


def src_yahoo(sym, yahoo_sym=None, metric="qty"):
    s = yahoo_sym or sym
    last_err = None
    for host in ("query1", "query2"):
        for attempt in range(2):
            try:
                u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/"
                     f"{urllib.parse.quote(s)}?range=6mo&interval=1d")
                d = _get(u)
                r = d["chart"]["result"][0]
                q = r["indicators"]["quote"][0]
                ts = r["timestamp"]
                bars = []
                for i in range(len(ts) - 1, -1, -1):
                    lo, hi, cl, vo = q["low"][i], q["high"][i], q["close"][i], q["volume"][i]
                    if None in (lo, hi, cl, vo):
                        continue
                    bars.append((lo, hi, cl, vo if metric == "qty" else vo * cl))
                if bars:
                    m = {"inst": s, "last": bars[0][2], "open24h": bars[1][2] if len(bars) > 1 else bars[0][2],
                         "funding_8h_pct": None}
                    return bars, m, "Yahoo 现货 " + s
            except Exception as e:
                last_err = e
                time.sleep(1.2)
    raise LookupError(f"Yahoo 历史不可用({s}): {last_err}")


# ---------- 成本分布计算 ----------

def volume_profile(bars, nbins=50):
    lows = [b[0] for b in bars]; highs = [b[1] for b in bars]
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        hi = lo * 1.001
    step = (hi - lo) / nbins
    edges = [lo + step * i for i in range(nbins + 1)]
    cent = [(edges[i] + edges[i + 1]) / 2 for i in range(nbins)]
    prof = [0.0] * nbins
    for low, high, _c, vq in bars:
        if high <= low:
            j = min(max(int((low - lo) / step), 0), nbins - 1)
            prof[j] += vq
            continue
        for j in range(nbins):
            ov = max(0.0, min(high, edges[j + 1]) - max(low, edges[j]))
            if ov > 0:
                prof[j] += vq * ov / (high - low)
    poc_i = max(range(nbins), key=lambda k: prof[k])
    poc = cent[poc_i]
    order = sorted(range(nbins), key=lambda k: prof[k], reverse=True)
    tot = sum(prof) or 1.0
    cum = 0.0; va = set()
    for k in order:
        va.add(k); cum += prof[k]
        if cum >= 0.7 * tot:
            break
    va_lo = cent[min(va)]; va_hi = cent[max(va)]
    return {"cent": cent, "prof": prof, "va": va, "poc": poc,
            "va_lo": va_lo, "va_hi": va_hi, "lo": lo, "hi": hi, "step": step}


def plot(sym, vp, meta, source, out, metric="qty"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Arial Unicode MS", "DejaVu Sans"]
    last = meta["last"]
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["#e0563b" if k in vp["va"] else "#cccccc" for k in range(len(vp["cent"]))]
    ax.barh(vp["cent"], vp["prof"], height=vp["step"] * 0.9, color=colors)
    ax.axhline(last, color="#1f77b4", lw=2, label="Last %.4g" % last)
    ax.axhline(vp["poc"], color="#d62728", lw=1.6, ls="--", label="POC (avg cost) %.4g" % vp["poc"])
    ax.axhline(vp["va_hi"], color="#888", lw=0.9, ls=":")
    ax.axhline(vp["va_lo"], color="#888", lw=0.9, ls=":")
    ax.set_title("%s  Volume Profile / Cost Basis\nsource: %s" % (sym.upper(), source), fontsize=11)
    xl = "Volume traded (contracts/qty)" if metric == "qty" else "Traded value by price"
    ax.set_xlabel(xl); ax.set_ylabel("Price")
    ax.text(max(vp["prof"]) * 0.5, vp["va_hi"], "VA high %.4g" % vp["va_hi"], fontsize=8, color="#555", va="bottom")
    ax.text(max(vp["prof"]) * 0.5, vp["va_lo"], "VA low %.4g" % vp["va_lo"], fontsize=8, color="#555", va="top")
    ax.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    plt.savefig(out, dpi=110)
    plt.close()


def src_naver(sym, naver_sym=None, metric="qty"):
    """韩国主板(KRX)历史，Naver 金融。sym 用6位代码，如 000660(海力士)。"""
    code = (naver_sym or sym).upper().replace(".KS", "").replace(".KQ", "")
    import re
    u = (f"https://api.finance.naver.com/siseJson.naver?symbol={code}"
         f"&requestType=1&startTime=20260101&endTime=20301231&timeframe=day")
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://finance.naver.com/"})
    txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    rows = re.findall(r"\[([^\[\]]+)\]", txt)
    bars = []
    for r in rows:
        parts = [p.strip().strip("'\"") for p in r.split(",")]
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        o, h, l, c, v = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
        bars.append((l, h, c, v if metric == "qty" else v * c))
    if not bars:
        raise LookupError(f"Naver 无 {code} 数据")
    bars.reverse()  # 最新在前
    m = {"inst": "KRX:" + code, "last": bars[0][2],
         "open24h": bars[1][2] if len(bars) > 1 else bars[0][2], "funding_8h_pct": None}
    return bars, m, "Naver 韩国主板 " + code


SOURCES = {"okx": src_okx, "hl": src_hl, "yahoo": src_yahoo, "naver": src_naver}


def resolve(sym, source, yahoo_sym, naver_sym, metric):
    order = [source] if source != "auto" else ["okx", "hl", "yahoo"]
    errs = []
    for s in order:
        try:
            if s == "yahoo":
                return src_yahoo(sym, yahoo_sym, metric)
            if s == "naver":
                return src_naver(sym, naver_sym, metric)
            return SOURCES[s](sym, metric)
        except Exception as e:
            errs.append(f"{s}: {e}")
    raise SystemExit("所有源都拿不到量价历史：\n  " + "\n  ".join(errs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--source", default="auto", choices=["auto", "okx", "hl", "yahoo", "naver"])
    ap.add_argument("--yahoo-sym", default=None, help="Yahoo 代码，如 000660.KS / ASST")
    ap.add_argument("--naver-sym", default=None, help="韩股6位代码，如 000660")
    ap.add_argument("--bins", type=int, default=50)
    ap.add_argument("--metric", default="qty", choices=["qty", "value"],
                    help="qty=按成交量(张数,默认,直观) / value=按成交额(USDT)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    bars, meta, source = resolve(a.symbol, a.source, a.yahoo_sym, a.naver_sym, a.metric)
    vp = volume_profile(bars, a.bins)
    out = a.out or str(OUTDIR / f"vp_{a.symbol.upper().replace('.', '_')}.png")
    plot(a.symbol, vp, meta, source, out, a.metric)

    last = meta["last"]
    summary = {
        "symbol": a.symbol.upper(),
        "source": source,
        "bars": len(bars),
        "last": round(last, 4),
        "poc": round(vp["poc"], 4),
        "value_area": [round(vp["va_lo"], 4), round(vp["va_hi"], 4)],
        "last_vs_poc_pct": round((last / vp["poc"] - 1) * 100, 2),
        "funding_8h_pct": meta.get("funding_8h_pct"),
        "image": out,
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
