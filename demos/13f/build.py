# /// script
# requires-python = ">=3.11"
# ///
"""Write pipeline.py output into demo.html: numbers, the filing stream, holdings, identifiers and the tour.

    uv run build.py data.json demo.html
"""

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path


def money(v):
    return f"${v / 1e12:.1f}tn" if v >= 1e12 else f"${v / 1e9:.1f}bn" if v >= 1e9 else f"${v / 1e6:.1f}m"


def n(v):
    return f"{v:,}"


def day(iso):
    return dt.date.fromisoformat(iso[:10]).strftime("%-d %b" if sys.platform != "win32" else "%#d %b")


def replace(page, pattern, new, count=1):
    out, k = re.subn(pattern, lambda _: new, page, count=count, flags=re.S | re.M)
    if k != count:
        raise SystemExit(f"pattern not found: {pattern[:60]}")
    return out


def corrections_summary(cs):
    matched = [c for c in cs if c["original"]]
    typed = lambda t: [c for c in matched if (c["amendment_type"] or "").upper() == t]
    new_h, restate = typed("NEW HOLDINGS"), typed("RESTATEMENT")
    untyped = [c for c in cs if not c["amendment_type"]]
    late = [c for c in matched if (dt.date.fromisoformat(c["accepted"][:10]) - dt.date.fromisoformat(c["original"]["filed"])).days >= 90]
    reach = max(((dt.date.fromisoformat(c["accepted"][:10]) - dt.date.fromisoformat(c["period"])).days / 365.25 for c in matched if c["period"]), default=0)
    example = max(new_h, key=lambda c: c["original"]["value"], default=None)
    return {
        "total": len(cs), "matched": len(matched), "unmatched": len(cs) - len(matched),
        "quarters": len({(c["cik"], c["period"]) for c in matched}),
        "late": len(late), "reach_years": reach,
        "new_holdings": len(new_h), "restatements": len(restate),
        "untyped_pct": 100 * len(untyped) / len(cs) if cs else 0,
        "replace_wrongly_deletes": sum(c["original"]["value"] for c in new_h),
        "add_wrongly_doubles": sum(c["original"]["value"] for c in restate),
        "example": example,
    }


def main():
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    page_path = Path(sys.argv[2])
    page = page_path.read_text(encoding="utf-8")
    s, w, fl = data["stats"], data["window"], data["filings"]
    cs = corrections_summary(data["corrections"])
    window = f"{day(w['start'])} – {day(w['end'])} {w['end'][:4]}"
    periods = s["periods"]
    main_period = max(periods, key=periods.get)
    big = s["largest"]

    page = replace(page, r"<header>.*?</header>", f"""<header>
    <p class="eyebrow">SEC 13F ingestion · live filing season</p>
    <h1>The Q3 2026 filing season so far: parsed, identified, and checked against what changed later.</h1>
    <p class="lede" style="margin-top:.8rem">Every 13F filed with the SEC from {window}, while funds report
      their 30 September positions. Every number below was measured by a script you can run.</p>
    <p style="margin-top:1rem"><button class="btn" id="tstart">Take the guided tour →</button>
      <span class="note" style="margin-left:.6rem">10 steps, about two minutes</span></p>
  </header>""")

    page = replace(page, r'<section id="s-day">.*?</section>', f"""<section id="s-day">
    <h2>The season so far</h2>
    <div class="tiles">
      <div class="tile"><span class="v">{n(s['filings_in_window'])}</span>
        <span class="k">13F filings, {window}</span></div>
      <div class="tile"><span class="v">{n(s['filings_parsed'])}</span>
        <span class="k">parsed here — all of them</span></div>
      <div class="tile"><span class="v">{n(s['holdings'])}</span>
        <span class="k">holdings parsed</span></div>
      <div class="tile good" id="t-parse"><span class="v">{n(s['holdings_per_second'])}</span>
        <span class="k">holdings per second</span></div>
      <div class="tile"><span class="v">{big['parse_ms']} ms</span>
        <span class="k">largest single filing</span></div>
    </div>
    <p class="note">Funds have 45 days after the quarter ends to file, so this is the early part of the
      Q3 2026 season: {n(periods.get(main_period, 0))} of these filings report the quarter ending {main_period}.
      The biggest — {html.escape(big['filer'])}, {n(big['rows'])} holdings — took {big['parse_ms']} ms. We report
      throughput rather than an average per filing because filing sizes are wildly uneven: the median filing
      holds just {s['median_holdings']:.0f} positions. Cost is about {s['us_per_holding']} microseconds per holding.
      Timing covers document to structured rows; it excludes network time, which is the SEC's to control, not ours.</p>
  </section>""")

    page = replace(page, r'(<section id="s-replay">\s*<h2>Replay the season</h2>|<section id="s-replay">\s*<h2>Replay the day</h2>).*?<div id="replay"></div>', f"""<section id="s-replay">
    <h2>Replay the season</h2>
    <p class="note">Watch all {n(len(fl))} filings arrive at their real SEC accepted times. Each one is
      parsed in the time it actually took, and the stream below fills up as they land. Only the clock is sped up.</p>
    <div id="replay"></div>""")

    rows = "\n".join(
        f'<tr data-acc="{f["accession"]}" data-t="{f["accepted"]}"><td class="mono">{f["accepted"][5:10]} {f["accepted"][11:19]}</td>'
        f'<td>{html.escape(f["filer"])}</td><td class="mono">{f["quarter"]}</td><td class="num">{n(f["rows"])}</td>'
        f'<td class="num">{money(f["value"])}</td><td class="num">{f["parse_ms"]:.2f} ms</td></tr>'
        for f in reversed(fl))
    page = re.sub(r'(<section id="s-stream">.*?<tbody>).*?(</tbody>)', lambda m: m.group(1) + rows + m.group(2), page, count=1, flags=re.S)

    page = replace(page, r'<section id="s-gaps">.*?</section>', f"""<section id="s-gaps">
    <h2>Identifier resolution, including what fails</h2>
    <div class="tiles">
      <div class="tile"><span class="v">{n(s['distinct_identifiers'])}</span>
        <span class="k">distinct identifiers</span></div>
      <div class="tile good" id="t-resolve"><span class="v">{s['sample_resolved_pct']}%</span>
        <span class="k">resolved to a FIGI</span></div>
      <div class="tile flag"><span class="v">{n(round(s['sample_size'] * (100 - s['sample_resolved_pct']) / 100))}</span>
        <span class="k">unresolved in the sample</span></div>
      <div class="tile"><span class="v">{s['non_us_pct']}%</span>
        <span class="k">non-US identifiers</span></div>
      <div class="tile flag" id="t-sedol"><span class="v">0</span>
        <span class="k">SEDOLs — licensed</span></div>
    </div>
    <p class="note">Sources: OpenFIGI for FIGI and ticker, and a derived ISIN for US securities. No licence,
      no contract, no vendor fee. The rate is measured on a <strong>random sample of {n(s['sample_size'])}</strong>
      of the {n(s['distinct_identifiers'])} distinct identifiers, deliberately not on the largest holdings — those
      are well-known US securities and would flatter the figure. Most failures are non-US securities, which the free
      sources do not carry. <strong>SEDOL is licensed by LSEG and cannot be supplied this way</strong>; our proposal
      offered it, and that needs correcting.</p>
  </section>""")

    ex = cs["example"]
    if ex:
        gap = (dt.date.fromisoformat(ex["accepted"][:10]) - dt.date.fromisoformat(ex["original"]["filed"])).days
        example_html = f"""<div class="callout" id="s-example">
      <h3>{html.escape(ex['filer'])} — quarter ending {ex['period']}</h3>
      <div class="split">
        <div class="gone"><div class="k">Filed {ex['original']['filed']}</div>
          <div class="v">{n(ex['original']['rows'])} holdings</div></div>
        <div class="arrow">→</div>
        <div><div class="k">Corrected {ex['accepted'][:10]}</div>
          <div class="v">{n(ex['rows'])} holdings</div></div>
      </div>
      <p>The correction says <span class="chip">new holdings</span> — add these, keep the rest. Handle it as a
        replacement, which is the obvious default, and <strong>{money(ex['original']['value'])} of holdings disappear</strong>
        {gap} days after they were first reported.</p>
      <p class="note">Across the window: assuming corrections replace wrongly deletes {money(cs['replace_wrongly_deletes'])};
        assuming they add wrongly double-counts {money(cs['add_wrongly_doubles'])}. One field decides which, and
        {cs['untyped_pct']:.1f}% of corrections do not state it at all.</p>
    </div>"""
        tour_example = f"{ex['filer']} filed {n(ex['original']['rows'])} holdings, then filed again {gap} days later with {n(ex['rows'])}. The second filing adds to the first. Treat it as a replacement and {money(ex['original']['value'])} disappears."
    else:
        example_html = f"""<div class="callout" id="s-example"><h3>Restatements and additions</h3>
      <p>Every correction in this window was a restatement. Treating them as additions would double-count
        {money(cs['add_wrongly_doubles'])}.</p></div>"""
        tour_example = f"Treating restatements as additions would double-count {money(cs['add_wrongly_doubles'])}."

    page = replace(page, r'<section id="s-corrections">.*?</section>', f"""<section id="s-corrections">
    <h2>What happens after a filing is published</h2>
    <p>A filing is not final. Firms return months or years later and change what they already reported. There is
      no corrections feed, no notification, and nothing in the new document says which filing it replaces.</p>
    <div class="tiles">
      <div class="tile"><span class="v">{cs['total']}</span>
        <span class="k">corrections, {window}</span></div>
      <div class="tile flag"><span class="v">{cs['quarters']}</span>
        <span class="k">published quarters changed</span></div>
      <div class="tile"><span class="v">{cs['late']}</span>
        <span class="k">arrived 90+ days late</span></div>
      <div class="tile flag"><span class="v">{cs['reach_years']:.1f} yrs</span>
        <span class="k">furthest reach back</span></div>
    </div>
    {example_html}
  </section>""")

    page = replace(page, r'<section id="s-claim">.*?<ul>.*?</ul>', f"""<section id="s-claim">
    <h2>What this demonstrates</h2>
    <ul>
      <li><strong>Ingestion is fast and provably so</strong> — {n(s['holdings'])} holdings across
        {n(s['filings_parsed'])} filings in {n(s['parse_ms_total'])} ms, about {s['us_per_holding']} microseconds per holding.</li>
      <li><strong>Identifiers resolve at {s['sample_resolved_pct']}% from free sources</strong> on a random sample, with the
        failures published rather than rounded away — and SEDOL, which our proposal promised, cannot be delivered
        without a licence.</li>
      <li><strong>The hard part is time, not parsing.</strong> Holdings history is rewritten after publication. A store
        that records only which quarter a fact belongs to — and not when it was learned — is wrong and cannot tell you so.</li>
      <li><strong>No AI was used anywhere in this pipeline.</strong> The filings are structured XML. Adding a model would
        add cost and risk without adding accuracy.</li>
    </ul>""")

    page = replace(page, r"<footer>.*?</footer>", f"""<footer>
    <p><strong>Method.</strong> All {n(s['filings_in_window'])} 13F-HR filings accepted by SEC EDGAR from {window},
      downloaded and parsed ({n(s['filings_parsed'])} carried a holdings table). Identifiers resolved via OpenFIGI.
      Corrections cover all {cs['total']} 13F-HR/A filings in the same window, each matched to the filing it corrects;
      {cs['unmatched']} had no retrievable original and are excluded from the dollar figures. Generated {data['generated_at'][:10]}.</p>
    <p><strong>Limits.</strong> The Q3 2026 season is still open until 14 November, so these are the early filers.
      US filings only. 13F covers long US-listed equity — no shorts, no non-US listings, no bonds. Amendment chains are
      not modelled. The value figures are gross exposure under each wrong rule, not realised loss.</p>
    <p>Public SEC data throughout. Every figure regenerates from source with <code>uv run pipeline.py</code> and
      <code>uv run build.py</code>.</p>
  </footer>""")

    filings_js = {f["accession"]: {"filer": f["filer"], "quarter": f["quarter"], "rows": f["rows"], "parse_ms": f["parse_ms"],
                                   "holdings": f["holdings"]} for f in fl}
    page = replace(page, r"^const FILINGS = .*?;$", "const FILINGS = " + json.dumps(filings_js, separators=(",", ":")) + ";")
    page = replace(page, r"^const IDS = .*?;$", "const IDS = " + json.dumps(data["ids"], separators=(",", ":")) + ";")

    biggest = max(fl, key=lambda f: f["rows"])
    tour = [
        {"sel": "#s-day", "title": "The live filing season", "body": f"Every US investment firm over $100m must publish what it owns, four times a year. {n(s['filings_in_window'])} filings have arrived so far for the quarter that ended on 30 September. Nothing on this page is simulated."},
        {"sel": "#t-parse", "title": "How fast we turn filings into data", "body": f"{n(s['holdings_per_second'])} holdings a second, measured rather than claimed. The biggest filing here held {n(big['rows'])} positions and took {big['parse_ms']} milliseconds. The documents are clean, structured XML, so this part is genuinely easy — worth knowing before anyone pays for it."},
        {"sel": "#s-stream", "title": "The filings themselves", "body": "Each row is one real filing, newest first, with the time the SEC accepted it on the left and how long we took on the right. You can click any row."},
        {"sel": "#s-inside", "act": "openFiling", "arg": biggest["accession"], "title": "What is inside one filing", "body": "The holdings. Company name, an identifier called a CUSIP, and how much it is worth. This is the raw material."},
        {"sel": "#t-resolve", "title": "Turning identifiers into something usable", "body": f"A CUSIP joins to nothing on its own. We map it to a ticker, a FIGI and an ISIN using free sources. {s['sample_resolved_pct']}% succeed, measured on a random sample of {n(s['sample_size'])} — not on the big famous holdings, which would flatter the number."},
        {"sel": "#s-gaps", "title": "And what does not resolve", "body": f"{n(round(s['sample_size'] * (100 - s['sample_resolved_pct']) / 100))} of that sample resolve to nothing. Most are non-US securities: {s['non_us_pct']}% of identifiers here are foreign, and the free sources simply do not carry them. We show the gap rather than round it away."},
        {"sel": "#t-sedol", "title": "One promise we cannot keep for free", "body": "Our proposal offered SEDOL identifiers. SEDOL is licensed by LSEG and cannot be delivered without a contract. Better said now than at delivery."},
        {"sel": "#s-corrections", "title": "Now the part that is not about speed", "body": f"Firms go back and edit filings they already published. In these two weeks alone, {cs['quarters']} already-published quarters were rewritten, one reaching back {cs['reach_years']:.1f} years. Nothing announces it."},
        {"sel": "#s-example", "title": "Why that is expensive", "body": tour_example},
        {"sel": "#s-claim", "title": "What we are actually claiming", "body": "Speed is easy and we can prove it. Identifiers are mostly solvable and we show what is not. Handling corrections correctly is the hard part, and it is the part that quietly breaks pipelines."},
    ]
    page = replace(page, r"^const TOUR = .*?;$", "const TOUR = " + json.dumps(tour, ensure_ascii=False) + ";")

    page_path.write_text(page, encoding="utf-8")
    print(f"wrote {page_path} ({page_path.stat().st_size / 1e6:.2f} MB): {len(fl)} filings, {len(data['ids'])} identifiers")


if __name__ == "__main__":
    main()
