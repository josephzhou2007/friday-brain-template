#!/usr/bin/env python3
"""按时间上色的 Volume Profile（成本分布 · 时间分层版）—— 盘手出图工具 v2。

在普通 Volume Profile 基础上，把近 N 个交易日按时间切成若干段，
颜色由浅到深 = 老钱到新钱，堆叠在每个价格档上。
这样能一眼看出：某个价位的筹码，是最近买的（深）还是很久前买的（浅）——
判断"新钱成本在哪、有没有近期套牢盘、买盘成本是抬升还是下移"。

数据源优先级：Yahoo 现货（美股，日线）→ OKX 永续（含股票永续/加密）。
  - Yahoo 用 query2 + 浏览器UA + 重试；本机代理偶发 429，脚本会自动重试再回退 OKX。

用法:
  python3 volume_profile_recency.py MU              # 近60交易日, 6段
  python3 volume_profile_recency.py NOW --days 60 --bands 6
  python3 volume_profile_recency.py BTC --source okx

输出：PNG（vp_<SYM>_recency.png）+ 一行 JSON 摘要。
"""
import argparse, json, time, urllib.request, datetime
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
OUTDIR = Path(__file__).resolve().parent.parent


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _post(url, payload, timeout=25):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_yahoo(sym, rng="6mo"):
    last_err = None
    for host in ("query2", "query1"):
        for _ in range(3):
            try:
                u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/"
                     f"{sym}?range={rng}&interval=1d")
                d = _get(u)
                r = d["chart"]["result"][0]
                q = r["indicators"]["quote"][0]; ts = r["timestamp"]
                rows = []  # oldest -> newest
                for i in range(len(ts)):
                    lo, hi, cl, vo = q["low"][i], q["high"][i], q["close"][i], q["volume"][i]
                    if None in (lo, hi, cl, vo):
                        continue
                    rows.append((ts[i], lo, hi, cl, vo))
                if rows:
                    return rows, "Yahoo 现货 " + sym
            except Exception as e:
                last_err = e; time.sleep(1.3)
    raise LookupError(f"Yahoo 历史不可用({sym}): {last_err}")


def fetch_okx(sym):
    sym = sym.upper().replace("-USDT-SWAP", "")
    data = _get("https://www.okx.com/api/v5/public/instruments?instType=SWAP")["data"]
    ids = [x["instId"] for x in data]
    inst = f"{sym}-USDT-SWAP"
    if inst not in ids:
        cand = [i for i in ids if i.upper().startswith(sym + "-")]
        if not cand:
            raise LookupError(f"OKX 无 {sym} 永续")
        inst = cand[0]
    c = _get(f"https://www.okx.com/api/v5/market/candles?instId={inst}&bar=1D&limit=300")["data"]
    rows = []  # oldest -> newest
    for r in reversed(c):
        rows.append((int(r[0]) // 1000, float(r[3]), float(r[2]), float(r[4]), float(r[5])))
    return rows, "OKX 永续 " + inst


def build(rows, days, bands, nbins=50):
    rows = rows[-days:]
    N = len(rows)
    per = N / bands
    buckets = [[] for _ in range(bands)]
    for idx, row in enumerate(rows):
        buckets[min(int(idx / per), bands - 1)].append(row)
    lo = min(r[1] for r in rows); hi = max(r[2] for r in rows)
    if hi <= lo:
        hi = lo * 1.001
    step = (hi - lo) / nbins
    edges = [lo + step * i for i in range(nbins + 1)]
    cent = [(edges[i] + edges[i + 1]) / 2 for i in range(nbins)]

    def prof_of(bs):
        p = [0.0] * nbins
        for _t, low, high, _c, vq in bs:
            if high <= low:
                p[min(max(int((low - lo) / step), 0), nbins - 1)] += vq; continue
            for j in range(nbins):
                ov = max(0.0, min(high, edges[j + 1]) - max(low, edges[j]))
                if ov > 0:
                    p[j] += vq * ov / (high - low)
        return p

    profs = [prof_of(b) for b in buckets]
    total = [sum(profs[k][j] for k in range(bands)) for j in range(nbins)]
    poc = cent[max(range(nbins), key=lambda k: total[k])]
    order = sorted(range(nbins), key=lambda k: total[k], reverse=True)
    tot = sum(total) or 1.0; cum = 0.0; va = set()
    for k in order:
        va.add(k); cum += total[k]
        if cum >= 0.7 * tot:
            break
    return {"cent": cent, "profs": profs, "total": total, "buckets": buckets,
            "poc": poc, "va_lo": cent[min(va)], "va_hi": cent[max(va)],
            "step": step, "last": rows[-1][3], "bands": bands}


def plot(sym, R, source, out):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Arial Unicode MS", "DejaVu Sans"]
    from matplotlib.patches import Patch
    cent, profs, step = R["cent"], R["profs"], R["step"]
    bands = R["bands"]; cmap = plt.get_cmap("Blues")
    cols = [cmap(0.25 + 0.6 * k / max(bands - 1, 1)) for k in range(bands)]

    def dlabel(bs):
        if not bs:
            return "—"
        a = datetime.date.fromtimestamp(bs[0][0]); z = datetime.date.fromtimestamp(bs[-1][0])
        return f"{a.month}/{a.day}-{z.month}/{z.day}"
    labels = [dlabel(b) for b in R["buckets"]]

    fig, ax = plt.subplots(figsize=(9, 6.5))
    left = [0.0] * len(cent)
    for k in range(bands):
        ax.barh(cent, profs[k], height=step * 0.9, left=left, color=cols[k], edgecolor="none")
        left = [left[j] + profs[k][j] for j in range(len(cent))]
    mx = max(R["total"]) or 1
    ax.axhline(R["last"], color="#111", lw=1.8, label="Last %.1f" % R["last"])
    ax.axhline(R["poc"], color="#d62728", lw=1.5, ls="--", label="POC %.1f" % R["poc"])
    ax.axhline(R["va_hi"], color="#888", lw=0.8, ls=":"); ax.axhline(R["va_lo"], color="#888", lw=0.8, ls=":")
    ax.text(mx * 0.55, R["va_hi"], "VA high %.1f" % R["va_hi"], fontsize=8, color="#555", va="bottom")
    ax.text(mx * 0.55, R["va_lo"], "VA low %.1f" % R["va_lo"], fontsize=8, color="#555", va="top")
    ax.set_title("%s  Volume Profile by Recency\nlight = older buys  ->  dark = recent buys   (source: %s)"
                 % (sym.upper(), source), fontsize=11)
    ax.set_xlabel("Volume traded"); ax.set_ylabel("Price")
    leg1 = [Patch(facecolor=cols[k], label=labels[k]) for k in range(bands)]
    l1 = ax.legend(handles=leg1, title="time band (old->new)", loc="lower right", fontsize=8, title_fontsize=8)
    ax.add_artist(l1)
    ax.legend(loc="upper right", fontsize=9)
    plt.tight_layout(); plt.savefig(out, dpi=115); plt.close()
    return labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--source", default="auto", choices=["auto", "yahoo", "okx"])
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--bands", type=int, default=6)
    ap.add_argument("--bins", type=int, default=50)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    order = [a.source] if a.source != "auto" else ["yahoo", "okx"]
    rows = source = None; errs = []
    for s in order:
        try:
            rows, source = (fetch_yahoo if s == "yahoo" else fetch_okx)(a.symbol)
            break
        except Exception as e:
            errs.append(f"{s}: {e}")
    if not rows:
        raise SystemExit("拿不到量价历史：\n  " + "\n  ".join(errs))

    R = build(rows, a.days, a.bands, a.bins)
    out = a.out or str(OUTDIR / f"vp_{a.symbol.upper().replace('.', '_')}_recency.png")
    labels = plot(a.symbol, R, source, out)

    nbins = len(R["cent"])
    recent = [R["profs"][-1][j] + R["profs"][-2][j] for j in range(nbins)]
    old = [R["profs"][0][j] + R["profs"][1][j] for j in range(nbins)]
    print(json.dumps({
        "symbol": a.symbol.upper(), "source": source, "days": a.days, "bands": a.bands,
        "last": round(R["last"], 2), "poc": round(R["poc"], 2),
        "value_area": [round(R["va_lo"], 2), round(R["va_hi"], 2)],
        "recent_bucket_peak_price": round(R["cent"][max(range(nbins), key=lambda k: recent[k])], 2),
        "old_bucket_peak_price": round(R["cent"][max(range(nbins), key=lambda k: old[k])], 2),
        "time_bands": labels, "image": out,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
