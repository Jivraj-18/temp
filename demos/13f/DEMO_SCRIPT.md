# Demo Script — 13F Filings Workflow

**Demo page:** [`demo.html`](demo.html) · Live: <https://jivraj-18.github.io/temp/demos/13f/demo.html>
**Run time:** ~5 minutes · **Three phases, nine steps**

> **How to read this script:** each phase has a **Do** line (what to click on screen) and a **Say** line (what to tell the audience). Read the *Say* text as-is or paraphrase it.

---

## Phase 1 — Ingestion & scale (Steps 1–3)

**Do:** Open the 13F Filings dashboard, point to the main metrics banner, then click the live **Filings Log**.

**Say:**
> "Welcome to the 13F Workflow engine. What you see here is not a simulation. We are looking at a real, high-volume SEC deadline day featuring 1,730 US investment firms filing simultaneously. Our engine scales to ingest 51,316 holdings per second. To put that in perspective, look at this single filing with 3,704 positions — our platform processed it from raw XML to structured data in exactly 69 milliseconds. If I click any row in this live SEC log, you can instantly see its timestamp and exact run duration."

## Phase 2 — Identifier resolution (Steps 4–7)

**Do:** Click a filing row to expand **Filing Details**, then scroll to the **Identifier Mapping** section.

**Say:**
> "Let's dive into data quality. Here are the raw holdings, showing company name, CUSIP, and values. Our automated open-source mapping engine instantly cross-references these to Tickers, FIGIs, and ISINs, achieving an 83.9% success rate on a 2,500-holding sample. We believe in complete transparency, so we explicitly flag the remaining 16.1% unresolved records — primarily foreign securities unsupported by open datasets. Furthermore, we cleanly isolate SEDOL fields, noting that these require active LSEG licensing to unlock, preventing downstream compliance risks for your firm."

## Phase 3 — Edge cases & core value (Steps 8–9)

**Do:** Switch to the **Amendments & Corrections** view, showing an initial filing next to its amendment.

**Say:**
> "Finally, let's talk about real-world messy data. Firms frequently submit amendments. Here, an initial filing of 3,982 holdings was followed by an 80-holding amendment. Traditional parsers often overwrite or corrupt the initial data. Our system uses stateful matching logic to seamlessly merge the correction, preventing data loss. The bottom line: this platform delivers unmatched ingestion speed, absolute transparency in entity resolution, and bulletproof handling of complex regulatory corrections."

---

## Key numbers to remember

| Metric | Value |
|---|---|
| Ingestion throughput | 51,316 holdings / second |
| XML processing time | 69 ms for a 3,704-position filing |
| Open-source identifier resolution | 83.9% success (2,500-holding sample) |
| Unresolved (flagged, not hidden) | 16.1% — mostly foreign securities |
| Amendment handling | Multi-version automated reconciliation |
