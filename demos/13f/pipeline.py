# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "truststore"]
# ///
"""Rebuild the 13F demo data from SEC EDGAR for a date window.

    uv run pipeline.py --start 2026-10-01 --end 2026-10-15 --cache ./cache --out data.json

Stages (each cached under --cache, so re-runs only fetch what is missing):
  1. fetch    daily form indexes, then every 13F-HR and 13F-HR/A full submission (.txt)
  2. parse    the information table of each filing; parse time covers XML document -> structured rows
  3. amend    each 13F-HR/A matched to the 13F-HR it corrects (same filer, same period), with its stated amendment type
  4. resolve  CUSIP -> FIGI / ticker via OpenFIGI (top-25 holdings of every filing + a random sample for the rate)
No AI is used. Network time is excluded from parse timings.
"""

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import random
import re
import statistics
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import truststore

truststore.inject_into_ssl()   # use the OS certificate store (corporate proxies re-sign TLS)
import httpx  # noqa: E402

UA = {"User-Agent": "13F ingestion demo jivrajsinghs123@gmail.com"}
SEC = "https://www.sec.gov/Archives/"
TOP_N = 25
SAMPLE_N = 2500


class RateLimit:
    """At most `per_sec` calls per second across threads (SEC asks for <= 10/s)."""

    def __init__(self, per_sec):
        self.gap, self.lock, self.next = 1 / per_sec, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            self.next = max(self.next, now)
            delay, self.next = self.next - now, self.next + self.gap
        if delay > 0:
            time.sleep(delay)


sec_rate = RateLimit(8)
client = httpx.Client(headers=UA, timeout=120, follow_redirects=True)


def sec_get(url):
    for attempt in range(5):
        sec_rate.wait()
        try:
            r = client.get(url)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404):
                return None
        except httpx.TransportError:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError(f"failed: {url}")


# --------------------------------------------------------------------------
# 1. fetch
# --------------------------------------------------------------------------

LINE = re.compile(r"^(13F-HR(?:/A)?)\s{2,}(.+?)\s{2,}(\d+)\s{2,}(\d{8})\s{2,}(\S+)\s*$")


def daily_index(day, cache):
    path = cache / "index" / f"form.{day:%Y%m%d}.idx"
    if not path.exists():
        r = sec_get(f"{SEC}edgar/daily-index/{day.year}/QTR{(day.month - 1) // 3 + 1}/form.{day:%Y%m%d}.idx")
        if r is None:
            return []   # weekend, holiday, or not yet published
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(r.text, encoding="utf-8")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(line)
        if m:
            form, company, cik, filed, fname = m.groups()
            out.append({"form": form, "company": company.strip(), "cik": cik, "filed": filed, "path": fname,
                        "accession": Path(fname).stem})
    return out


def fetch_txt(entry, cache):
    path = cache / "filings" / f"{entry['accession']}.txt"
    if not path.exists():
        r = sec_get(SEC + entry["path"])
        if r is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return path


# --------------------------------------------------------------------------
# 2. parse
# --------------------------------------------------------------------------

DOC = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.S)


def header(txt, name):
    m = re.search(rf"^\s*{name}:?\s*(.+)$", txt, re.M)
    return m.group(1).strip() if m else None


def documents(txt):
    for d in DOC.findall(txt):
        typ = re.search(r"<TYPE>([^\n<]+)", d)
        xml = re.search(r"<XML>\s*(.*?)\s*</XML>", d, re.S)
        yield (typ.group(1).strip() if typ else ""), (xml.group(1) if xml else None)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_info_table(xml_text):
    """XML information table -> list of holdings. This is the timed step."""
    rows = []
    for it in ET.fromstring(xml_text):
        if local(it.tag) != "infoTable":
            continue
        row = {"issuer": None, "cusip": None, "value": 0, "shares": 0, "class": None, "put_call": None}
        for el in it.iter():
            t = local(el.tag)
            if t == "nameOfIssuer":
                row["issuer"] = (el.text or "").strip()
            elif t == "titleOfClass":
                row["class"] = (el.text or "").strip()
            elif t == "cusip":
                row["cusip"] = (el.text or "").strip().upper()
            elif t == "value":
                row["value"] = int(float(el.text or 0))
            elif t == "sshPrnamt":
                row["shares"] = int(float(el.text or 0))
            elif t == "putCall":
                row["put_call"] = (el.text or "").strip()
        rows.append(row)
    return rows


def find_text(xml_text, name):
    m = re.search(rf"<(?:\w+:)?{name}>\s*([^<]+?)\s*</(?:\w+:)?{name}>", xml_text or "")
    return m.group(1) if m else None


def parse_filing(entry, path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    # EDGAR acceptance time, US Eastern
    accepted = dt.datetime.strptime(re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", txt).group(1), "%Y%m%d%H%M%S")
    primary, table = None, None
    for typ, xml in documents(txt):
        if typ.startswith("13F-HR") and xml:
            primary = xml
        elif "INFORMATION TABLE" in typ.upper() and xml:
            table = xml
    rec = {
        "accession": entry["accession"], "form": entry["form"], "cik": entry["cik"],
        "filer": header(txt, "COMPANY CONFORMED NAME") or entry["company"],
        "accepted": accepted.isoformat(),
        "period": find_text(primary, "periodOfReport") or header(txt, "CONFORMED PERIOD OF REPORT"),
        "report_type": find_text(primary, "reportType"),
        "amendment_type": find_text(primary, "amendmentType"),
        "stated_total": find_text(primary, "tableValueTotal"),
        "rows": 0, "value": 0, "parse_ms": None, "holdings": [],
    }
    if table:
        t0 = time.perf_counter()
        holdings = parse_info_table(table)
        rec["parse_us"] = (time.perf_counter() - t0) * 1e6
        rec["parse_ms"] = round(rec["parse_us"] / 1000, 2)   # most filings parse in well under 1 ms
        rec["rows"] = len(holdings)
        rec["value"] = sum(h["value"] for h in holdings)
        rec["holdings"] = holdings
    return rec


def period_iso(p):
    """periodOfReport is MM-DD-YYYY in the XML; the header uses YYYYMMDD."""
    if not p:
        return None
    for fmt in ("%m-%d-%Y", "%Y%m%d", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(p, fmt).date().isoformat()
        except ValueError:
            pass
    return p


# --------------------------------------------------------------------------
# 3. amendments -> the original they correct
# --------------------------------------------------------------------------

def submissions(cik, cache):
    path = cache / "submissions" / f"{int(cik):010d}.json"
    if not path.exists():
        sec_rate.wait()
        r = client.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        if r.status_code != 200:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(r.text, encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def find_original(amend, cache):
    sub = submissions(amend["cik"], cache)
    if not sub:
        return None
    rec = sub["filings"]["recent"]
    cands = [
        {"accession": rec["accessionNumber"][i], "filed": rec["filingDate"][i], "period": rec["reportDate"][i]}
        for i in range(len(rec["form"]))
        if rec["form"][i] == "13F-HR" and rec["reportDate"][i] == amend["period"] and rec["filingDate"][i] <= amend["accepted"][:10]
    ]
    if not cands:
        return None
    o = max(cands, key=lambda c: c["filed"])
    cik = int(amend["cik"])
    entry = {"accession": o["accession"], "form": "13F-HR", "cik": amend["cik"], "company": amend["filer"],
             "path": f"edgar/data/{cik}/{o['accession']}.txt"}
    path = fetch_txt(entry, cache)
    if not path:
        return None
    orig = parse_filing(entry, path)
    return {"accession": o["accession"], "filed": o["filed"], "rows": orig["rows"], "value": orig["value"]}


# --------------------------------------------------------------------------
# 4. identifiers
# --------------------------------------------------------------------------

def isin_from_cusip(cusip):
    """US ISIN = 'US' + CUSIP + Luhn-style check digit over the letter-expanded string."""
    s = "".join(str(int(c, 36)) for c in "US" + cusip)
    total = 0
    for i, ch in enumerate(reversed(s)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
        total += d // 10 + d % 10
    return f"US{cusip}{(10 - total % 10) % 10}"


def resolve(cusips, cache):
    path = cache / "openfigi.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    todo = [c for c in sorted(cusips) if c not in known]
    print(f"[resolve] {len(known)} cached, {len(todo)} to query (~{len(todo) / 250:.0f} min)", flush=True)
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        for attempt in range(6):
            r = httpx.post("https://api.openfigi.com/v3/mapping", timeout=60,
                           json=[{"idType": "ID_CUSIP", "idValue": c} for c in batch])
            if r.status_code == 200:
                break
            time.sleep(65 if r.status_code == 429 else 5)
        else:
            raise RuntimeError(f"OpenFIGI failed: {r.status_code}")
        for c, job in zip(batch, r.json()):
            data = job.get("data") or []
            best = next((d for d in data if d.get("exchCode") == "US"), data[0] if data else None)
            known[c] = {"figi": best.get("figi"), "ticker": best.get("ticker"), "exch": best.get("exchCode")} if best else None
        if (i // 10) % 25 == 24:
            path.write_text(json.dumps(known), encoding="utf-8")
            print(f"[resolve] {i + 10}/{len(todo)}", flush=True)
            time.sleep(60)   # 25 requests per minute without an API key
    path.write_text(json.dumps(known), encoding="utf-8")
    return known


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--end", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--cache", type=Path, default=Path("cache"))
    ap.add_argument("--out", type=Path, default=Path("data.json"))
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--cached-ids", action="store_true", help="skip OpenFIGI calls; use only identifiers already in the cache")
    a = ap.parse_args()

    # 1. fetch
    entries, day = [], a.start
    while day <= a.end:
        if day.weekday() < 5:
            entries += daily_index(day, a.cache)
        day += dt.timedelta(days=1)
    print(f"[fetch] {sum(e['form'] == '13F-HR' for e in entries)} 13F-HR, {sum(e['form'] == '13F-HR/A' for e in entries)} 13F-HR/A", flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        paths = list(ex.map(lambda e: fetch_txt(e, a.cache), entries))
    print("[fetch] done", flush=True)

    # 2. parse (sequential, so timings are not disturbed by other threads)
    filings, amends = [], []
    for e, p in zip(entries, paths):
        if not p:
            continue
        rec = parse_filing(e, p)
        rec["period"] = period_iso(rec["period"])
        (filings if e["form"] == "13F-HR" else amends).append(rec)
    parsed = [f for f in filings if f["parse_ms"] is not None]
    holdings_total = sum(f["rows"] for f in parsed)
    parse_s = sum(f["parse_us"] for f in parsed) / 1e6
    print(f"[parse] {len(parsed)} filings, {holdings_total:,} holdings in {parse_s * 1000:.0f} ms", flush=True)

    # 3. amendments
    corrections = []
    for am in amends:
        orig = find_original(am, a.cache)
        corrections.append({k: am[k] for k in ("accession", "filer", "cik", "accepted", "period", "amendment_type", "rows", "value")} | {"original": orig})
    print(f"[amend] {len(corrections)} amendments, {sum(1 for c in corrections if c['original'])} matched to an original", flush=True)

    # 4. identifiers: everything shown on the page + a random sample for an unbiased rate
    distinct = sorted({h["cusip"] for f in parsed for h in f["holdings"] if h["cusip"]})
    rng = random.Random(a.seed)
    sample = rng.sample(distinct, min(SAMPLE_N, len(distinct)))
    shown = {h["cusip"] for f in parsed for h in sorted(f["holdings"], key=lambda h: -h["value"])[:TOP_N] if h["cusip"]}
    if a.cached_ids:   # use only lookups already done; the rest are reported as pending, not as failures
        path = a.cache / "openfigi.json"
        figi = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        sample = [c for c in sample if c in figi]
    else:
        figi = resolve(set(sample) | shown, a.cache)

    def ids(c):
        if c not in figi:
            return {"pending": True}
        x = figi.get(c)
        if not x or not x.get("figi"):
            return {"ticker": None, "figi": None, "isin": None}
        us = x.get("exch") == "US" and c[0].isdigit()
        return {"ticker": x.get("ticker"), "figi": x["figi"], "isin": isin_from_cusip(c) if us else None}

    sample_resolved = sum(1 for c in sample if (figi.get(c) or {}).get("figi"))
    big = max(parsed, key=lambda f: f["rows"])
    out = {
        "window": {"start": a.start.isoformat(), "end": a.end.isoformat()},
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "stats": {
            "filings_in_window": sum(e["form"] == "13F-HR" for e in entries),
            "amendments_in_window": len(amends),
            "filings_parsed": len(parsed),
            "holdings": holdings_total,
            "parse_ms_total": round(parse_s * 1000),
            "holdings_per_second": round(holdings_total / parse_s),
            "us_per_holding": round(parse_s * 1e6 / holdings_total, 1),
            "median_holdings": statistics.median(f["rows"] for f in parsed),
            "largest": {"filer": big["filer"], "rows": big["rows"], "parse_ms": big["parse_ms"]},
            "periods": dict(sorted({p: sum(1 for f in parsed if f["period"] == p) for p in {f["period"] for f in parsed}}.items())),
            "distinct_identifiers": len(distinct),
            "sample_size": len(sample),
            "sample_resolved_pct": round(100 * sample_resolved / len(sample), 1),
            "unresolved_estimate": round(len(distinct) * (1 - sample_resolved / len(sample))),
            "non_us_pct": round(100 * sum(1 for c in distinct if not c[0].isdigit()) / len(distinct), 1),
        },
        "filings": [
            {"accession": f["accession"], "filer": f["filer"], "accepted": f["accepted"], "quarter": f["period"],
             "rows": f["rows"], "value": f["value"], "parse_ms": f["parse_ms"],
             "holdings": [{"issuer": h["issuer"], "cusip": h["cusip"], "value": h["value"], "shares": h["shares"]}
                          for h in sorted(f["holdings"], key=lambda h: -h["value"])[:TOP_N]]}
            for f in sorted(parsed, key=lambda f: f["accepted"])
        ],
        "ids": {c: ids(c) for c in sorted(shown)},
        "corrections": corrections,
    }
    a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"[done] wrote {a.out} ({a.out.stat().st_size / 1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
