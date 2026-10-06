# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pypdf"]
# ///
"""Extract fundamentals from an annual-report PDF and add the company to companies.json.

    uv run --env-file .env pipeline.py <pdf> <source_url> <slug> \
        --sector Retail --industry "Home improvement retail" [--domain retail] [--country US]

The LLM only *reads* numbers (value, page, verbatim quote). Every ratio is computed here
with a fixed formula, and every extracted number is checked against the PDF's own text layer.

Env: LLMFOUNDRY_API_KEY, LLMFOUNDRY_PROJECT, LLMFOUNDRY_BASE_URL (default llmfoundry.straivedemo.com),
     MODEL (default gemini-3.8-flash).
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
import pypdf

HERE = Path(__file__).parent
DATA_FILE = HERE / "companies.json"
BASE = os.getenv("LLMFOUNDRY_BASE_URL", "https://llmfoundry.straivedemo.com").rstrip("/")
MODEL = os.getenv("MODEL", "gemini-3.8-flash")

# --------------------------------------------------------------------------
# what to extract
# --------------------------------------------------------------------------

RAW_FIELDS = {
    "net_income": "Net income ATTRIBUTABLE TO THE COMPANY (exclude noncontrolling interests), Consolidated Statements of Operations/Income, most recent fiscal year",
    "total_stockholders_equity": "Total shareholders' equity attributable to the company (exclude noncontrolling interests), Consolidated Balance Sheet, most recent fiscal year end",
    "beginning_total_assets": "Total Assets, Consolidated Balance Sheet, PRIOR fiscal year end",
    "ending_total_assets": "Total Assets, Consolidated Balance Sheet, most recent fiscal year end",
    "total_liabilities": "Total Liabilities, Consolidated Balance Sheet, most recent fiscal year end",
    "total_current_assets": "Total Current Assets, Consolidated Balance Sheet",
    "total_current_liabilities": "Total Current Liabilities, Consolidated Balance Sheet",
    "inventory": "Inventory, Consolidated Balance Sheet",
    "cash_and_equivalents": "Cash and Cash Equivalents, Consolidated Balance Sheet",
    "revenue": "Total Revenue / Net Sales, Consolidated Statements of Operations, most recent fiscal year",
    "revenue_prior_year": "Total Revenue / Net Sales, Consolidated Statements of Operations, PRIOR fiscal year (same line as revenue)",
    "cost_of_goods_sold": "Cost of Goods Sold / Cost of Sales / Cost of Merchandise Sold, Consolidated Statements of Operations",
    "operating_income": "Operating Income / Income from Operations, Consolidated Statements of Operations",
    "interest_expense": "Interest Expense, Consolidated Statements of Operations (gross interest expense, not net of interest income, when both are shown)",
    "income_tax_expense": "Income Tax Expense / Provision for Income Taxes, Consolidated Statements of Operations",
    "depreciation_and_amortization": "Depreciation and Amortization, Consolidated Statements of Cash Flows",
    "basic_eps": "Basic Earnings Per Share, Consolidated Statements of Operations",
    "diluted_eps": "Diluted Earnings Per Share, Consolidated Statements of Operations",
    "dividend_per_share": "Dividends declared/paid per share",
    "operating_cash_flow": "Net Cash Provided by Operating Activities, Consolidated Statements of Cash Flows",
    "capital_expenditures": "Purchases of property and equipment / capital expenditures, Consolidated Statements of Cash Flows (report as a positive number)",
    "shares_outstanding": "Shares of common stock outstanding",
    "share_price": "The company's own stock price, if stated anywhere in this document",
    "expected_growth_rate": "A forward-looking earnings growth rate estimate, if the company states one",
    "investment_cost": "Cost of a specific named investment, if the report discusses one",
    "investment_gain": "Gain on that same named investment, if discussed alongside its cost",
    "debt_principal_and_interest_due": "Principal + interest due in the coming year on borrowed-money debt (loans, bonds, credit facility draws)",
}

RETAIL_FIELDS = {
    "sss_net_sales_current": "Same-store (comparable) net sales across all channels, current fiscal year",
    "sss_net_sales_prior": "Same-store (comparable) net sales across all channels, prior fiscal year - same store base as above",
    "retail_store_sss_net_sales_current": "Same-store net sales from physical retail stores only, current fiscal year",
    "retail_store_sss_net_sales_prior": "Same-store net sales from physical retail stores only, prior fiscal year",
    "ecommerce_sss_net_sales_current": "Same-store (comparable) net sales from the e-commerce/direct-to-consumer channel, current fiscal year",
    "ecommerce_sss_net_sales_prior": "Same-store (comparable) net sales from the e-commerce/direct-to-consumer channel, prior fiscal year",
    "exclusive_brand_net_sales": "Net sales from the retailer's own exclusive/proprietary brands",
    "third_party_brand_net_sales": "Net sales from third-party/national brands carried by the retailer",
    "beginning_store_count": "Number of stores open at the start of the fiscal year (a count, not dollars)",
    "ending_store_count": "Number of stores open at the end of the fiscal year (a count, not dollars)",
    "retail_store_net_sales": "Net sales from physical retail stores (all stores, not just comparable), most recent fiscal year",
    "capex_per_new_store": "Average capital expenditure to open one new store, net of landlord/tenant allowances",
    "store_contribution_margin": "Annual store-level contribution margin for a mature/average store (e.g. EBITDAR minus rent), if disclosed",
    "store_occupancy_costs": "Store occupancy costs (rent, utilities, property taxes, common area maintenance) included within cost of goods sold",
    "distribution_freight_costs": "Distribution center and freight/fulfillment costs included within cost of goods sold",
}

# key -> (name, formula, description, unit)   unit: pct | x | usd | eps | yrs
RATIOS = {
    "roe": ("ROE (Return on Equity)", "Net Income / Total Stockholders' Equity", "Measures profitability relative to shareholders' equity. Higher means management is using investor capital more efficiently to generate profit.", "pct"),
    "roa": ("ROA (Return on Assets)", "Net Income / Average Total Assets", "Average Total Assets is (Beginning + Ending Total Assets) / 2. Higher means management is using resources more efficiently to generate earnings.", "pct"),
    "debt_to_equity": ("Debt-to-Equity Ratio", "Total Liabilities / Total Stockholders' Equity", "Measures leverage - how much a company finances its operations with debt versus its own funds. A lower ratio generally indicates greater financial stability.", "x"),
    "current_ratio": ("Current Ratio", "Total Current Assets / Total Current Liabilities", "Measures ability to pay short-term obligations (due within one year) with current assets. Above 1.0 is healthy; 1.5-2.0 is generally considered ideal.", "x"),
    "quick_ratio": ("Quick Ratio (Acid-Test Ratio)", "(Current Assets - Inventory) / Current Liabilities", "Measures ability to pay short-term liabilities with the most liquid assets, excluding inventory. A ratio of 1:1 is considered ideal.", "x"),
    "gross_margin": ("Gross Margin", "(Revenue - Cost of Goods Sold) / Revenue", "Share of revenue left after the direct cost of the goods and services sold. Driven by pricing power and product mix.", "pct"),
    "operating_profit_margin": ("Operating Profit Margin", "Operating Income / Revenue", "Measures core operational efficiency - the percentage of revenue remaining after covering cost of goods sold and operating expenses, before interest and taxes. Higher indicates better profitability.", "pct"),
    "net_profit_margin": ("Net Profit Margin", "Net Income / Revenue", "Share of every dollar of revenue that ends up as profit for shareholders, after all expenses, interest and taxes.", "pct"),
    "ebitda_margin": ("EBITDA Margin", "(Net Income + Interest Expense + Income Tax Expense + Depreciation & Amortization) / Revenue", "Measures operational profitability excluding financing, tax, and non-cash expenses. Higher indicates the business converts more of its core operations into earnings.", "pct"),
    "revenue_growth": ("Revenue Growth (YoY)", "(Revenue - Prior-Year Revenue) / Prior-Year Revenue", "Year-over-year change in total revenue, from the two years shown on the income statement.", "pct"),
    "asset_turnover": ("Asset Turnover", "Revenue / Average Total Assets", "Revenue generated per dollar of assets. High for asset-light or high-volume businesses such as discount retail.", "x"),
    "inventory_turnover": ("Inventory Turnover", "Cost of Goods Sold / Ending Inventory", "How many times inventory is sold through in a year. Higher means leaner stock and faster sell-through.", "x"),
    "operating_cash_flow_margin": ("Operating Cash Flow Margin", "Operating Cash Flow / Revenue", "Cash generated by operations per dollar of revenue - a cash-based check on reported margins.", "pct"),
    "free_cash_flow_margin": ("Free Cash Flow Margin", "(Operating Cash Flow - Capital Expenditures) / Revenue", "Cash left after reinvesting in property and equipment, per dollar of revenue.", "pct"),
    "interest_coverage_ratio": ("Interest Coverage Ratio", "Operating Income / Interest Expense", "Measures ability to pay interest on outstanding debt (uses Operating Income as a proxy for EBIT). Above 2-3 is typically considered good; higher means lower default risk.", "x"),
    "eps": ("Basic EPS", "Reported directly on the Income Statement", "Net income divided by weighted-average shares outstanding, as calculated and disclosed by the company itself.", "eps"),
    "diluted_eps": ("Diluted EPS", "Reported directly on the Income Statement", "Like Basic EPS, but assumes all convertible securities (options, warrants, convertible debt) are exercised - a conservative, usually lower, per-share figure.", "eps"),
    "shareholder_equity": ("Shareholder Equity", "Total Assets - Total Liabilities", "A company's net worth - the residual value belonging to owners after all liabilities are settled. Reported directly on the Balance Sheet.", "usd"),
    "cash_on_hand": ("Cash on Hand", "Reported directly on the Balance Sheet", "Total immediately accessible cash and cash equivalents.", "usd"),
    "dividend_per_share": ("Dividend Per Share", "Reported directly on the financial statements", "The portion of profit paid to shareholders per share owned. 0 if the company does not pay a dividend.", "eps"),
    "pe_ratio": ("Price-to-Earnings (P/E) Ratio", "Share Price / Earnings Per Share (EPS)", "Measures how much investors pay per $1 of earnings. A high ratio may suggest overvaluation or high growth expectations.", "x"),
    "pb_ratio": ("Price-to-Book (P/B) Ratio", "Share Price / Book Value Per Share", "Measures market valuation relative to net asset (book) value. A lower P/B (often < 1) may indicate an undervalued stock.", "x"),
    "peg_ratio": ("Price/Earnings-to-Growth (PEG) Ratio", "P/E Ratio / Expected Earnings Growth Rate (%)", "Divides P/E by expected earnings growth to judge value relative to growth prospects. ~1.0 suggests fair value.", "x"),
    "dividend_yield": ("Dividend Yield", "Annual Dividend Per Share / Share Price", "Annualized cash dividends as a percentage of the share price.", "pct"),
    "roi": ("ROI (Return on Investment)", "Investment Gain / Cost of Investment", "Evaluates profitability and efficiency of a specific investment by comparing its gain to its initial cost. Only computable when the report explicitly discusses a specific investment in these terms.", "pct"),
    "debt_service_ratio": ("Debt Service Ratio", "Operating Cash Flow / (Principal + Interest Payments Due)", "Measures ability to cover debt obligations (principal + interest) with operating cash flow. Above 1.0 is sufficient; 1.25+ is standard for lenders.", "x"),
    "debt_service_coverage_ratio": ("Debt Service Coverage Ratio", "EBITDA / (Principal + Interest Payments Due)", "Measures ability to cover debt obligations with EBITDA. 1.0 is break-even; lenders typically require 1.25+.", "x"),
}

RETAIL_RATIOS = {
    "consolidated_sss_growth": ("Consolidated Same-Store Sales Growth", "(Same-Store Net Sales, Current Year - Same-Store Net Sales, Prior Year) / Same-Store Net Sales, Prior Year", "Retail KPI. Net sales growth from stores open long enough (typically 14+ months) to exclude the effect of new store openings.", "pct"),
    "retail_store_sss": ("Retail Store Same-Store Sales Growth", "(Store SSS Net Sales, Current Period - Store SSS Net Sales, Prior Period) / Store SSS Net Sales, Prior Period", "Retail KPI. Same-store sales growth isolated to the physical retail store channel.", "pct"),
    "ecommerce_sss": ("E-commerce Same-Store Sales Growth", "(E-commerce Net Sales, Current Period - E-commerce Net Sales, Prior Period) / E-commerce Net Sales, Prior Period", "Retail KPI. Same-store sales growth isolated to the e-commerce/direct- to-consumer channel.", "pct"),
    "exclusive_brand_penetration": ("Exclusive Brand Penetration", "Net Sales from Exclusive Brands / Total Net Sales", "Retail KPI. Share of revenue from a retailer's own higher-margin proprietary brands versus third-party/national brands.", "pct"),
    "third_party_brand_penetration": ("Third-Party Brand Penetration", "Net Sales from Third-Party Brands / Total Net Sales", "Retail KPI. Share of revenue from third-party/national brands versus a retailer's own exclusive brands.", "pct"),
    "average_net_revenue_per_store": ("Average Net Revenue Per Store", "Retail Store Net Sales / Average Store Count", "Retail KPI. Average Store Count is (Beginning + Ending Store Count) / 2. Measures individual store productivity.", "usd"),
    "capex_payback_period": ("CapEx Payback Period (Years)", "Initial Capital Expenditure Per New Store / Annual Store-Level Contribution Margin", "Retail KPI. Years needed for a new store's investment to be recovered from its own contribution margin (e.g. EBITDAR minus rent). Shorter is better.", "yrs"),
    "merchandise_margin_rate": ("Merchandise Margin Rate", "(Net Sales - (Cost of Goods Sold - Occupancy and Distribution Costs)) / Net Sales", "Retail KPI. Margin on product sales alone, excluding the store occupancy and distribution/fulfillment costs bundled into Cost of Goods Sold.", "pct"),
    "occupancy_cost_rate": ("Occupancy Cost Rate", "(Store Occupancy Costs + Distribution & Freight/Fulfillment Costs) / Net Sales", "Retail KPI. Operating leverage on fixed retail and distribution infrastructure, as a percentage of net sales.", "pct"),
    "gross_margin_rate": ("Gross Margin Rate", "(Net Sales - Cost of Goods Sold) / Net Sales", "Retail KPI. GAAP gross profit margin after product and store/warehouse occupancy overhead - equals Merchandise Margin Rate minus Occupancy Cost Rate.", "pct"),
}

PER_SHARE = {"basic_eps", "diluted_eps", "dividend_per_share", "share_price"}
COUNTS = {"shares_outstanding", "beginning_store_count", "ending_store_count"}


def build_prompt(retail: bool) -> str:
    fields = {**RAW_FIELDS, **(RETAIL_FIELDS if retail else {})}
    ratios = {**RATIOS, **(RETAIL_RATIOS if retail else {})}
    field_lines = "\n".join(f"- {k}: {v}" for k, v in fields.items())
    ratio_lines = "\n".join(f"- {k}: {v[0]}" for k, v in ratios.items())
    retail_note = (
        "\nSome of the fields and ratios below are retail-domain KPIs (same-store sales, store counts, "
        "brand mix). Only fill them where the document actually discloses them; otherwise leave them null.\n"
        if retail else ""
    )
    return f"""You are extracting facts from a company's annual report for its MOST RECENT fiscal year. You have TWO jobs below. Do no arithmetic yourself either way - only report numbers literally printed in the document, never from outside knowledge.
{retail_note}
Rules that apply throughout:
- Every field is optional. Use value: 0 ONLY when the document EXPLICITLY states a fact equivalent to zero/none (e.g. "we have not declared any cash dividends") - quote that exact statement in source_quote. If the document never discusses a topic, use null - absence of evidence is not zero.
- Match by meaning, not exact wording - filers phrase the same concept differently (e.g. "Shareholders' equity" = "Total stockholders' equity"; "Cost of sales" = "Cost of goods sold").
- When the same figure appears at different precision in different places, use the exact one from the primary financial statement, not a rounded mention elsewhere.
- If a line item is split into sub-components shown separately (e.g. "Interest: Debt ... Finance lease ..."), report their sum and show each component plus the total in source_quote.

JOB 1 - Raw input values. Find these in the CONSOLIDATED financial statements:

{field_lines}

For each raw value, report:
- value: the exact number in whole dollars (if the statement says "in millions", multiply by 1,000,000; "in thousands" by 1,000). Per-share fields (EPS, dividend per share, share price) are already per-share - do not scale them. Counts (shares, stores) are plain counts, scaled only if the document says shares are in thousands/millions.
- as_printed: an exact substring a text search would find on the page, used to jump to this value. If a digit is printed, use it exactly as printed (e.g. "180,942"), BEFORE any unit scaling. If the value is INFERRED from a qualitative statement with no digit printed (e.g. "we have not declared any cash dividends" implying $0), use a short distinctive phrase copied verbatim from source_quote.
- unit_note: the exact nearby text establishing scale, e.g. "in thousands", "in millions", or "whole dollars" if none - verbatim.
- source_page: the PDF page number (1-indexed, counting actual PDF pages, NOT the printed folio) where you found it.
- source_quote: the exact line of text containing this number, quoted verbatim.

JOB 2 - Already-stated ratios. Check whether the document ALREADY states the final value for any of these itself (e.g. in a key-metrics table or MD&A - such as "comparable sales increased 4.5%", "ROIC 25.7%"):

{ratio_lines}

Only report a value if the FINAL ratio is stated as such in the text - never compute it, and never confuse a raw line item with a stated ratio. Percentages are reported as the printed percent number (4.5 for "4.5%"); multiples as the number (2.1 for "2.1x"); years as years. If not explicitly stated, value is null. Report source_page and source_quote for any you find. For same-store/comparable sales growth, prefer the company-wide / total-company figure, and say which segment in source_quote.

Also report company_name (full legal name) and fiscal_year_end (ISO date, e.g. "2025-03-29").

Respond with ONLY valid JSON:
{{
  "company_name": "...",
  "fiscal_year_end": "YYYY-MM-DD",
  "raw_values": {{ "<field>": {{"value": 0, "as_printed": "...", "unit_note": "...", "source_page": 0, "source_quote": "..."}} or null, ... one key per field above }},
  "stated_ratios": {{ "<ratio>": {{"value": 0, "source_page": 0, "source_quote": "..."}} or null, ... one key per ratio above }}
}}"""


# --------------------------------------------------------------------------
# model call
# --------------------------------------------------------------------------

def call_gemini(pdf_bytes: bytes, prompt: str) -> tuple[dict, dict]:
    key = os.environ.get("LLMFOUNDRY_API_KEY")
    if not key:
        sys.exit("LLMFOUNDRY_API_KEY is not set")
    project = os.environ.get("LLMFOUNDRY_PROJECT", "")
    auth = f"Bearer {key}:{project}" if project else f"Bearer {key}"
    body = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf_bytes).decode()}},
            {"text": prompt},
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 65536,
            "thinkingConfig": {"thinkingLevel": "medium"},
        },
    }
    url = f"{BASE}/gemini/v1beta/models/{MODEL}:generateContent"
    last = ""
    for attempt in range(5):
        try:
            r = httpx.post(url, headers={"Authorization": auth}, json=body, timeout=900)
            if r.status_code == 200:
                d = r.json()
                cand = (d.get("candidates") or [{}])[0]
                text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
                if text.strip():
                    return json.loads(text), d.get("usageMetadata", {})
                last = f"empty reply, finish={cand.get('finishReason')}"
            elif r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
            else:
                sys.exit(f"HTTP {r.status_code}: {r.text[:600]}")
        except (httpx.TransportError, json.JSONDecodeError) as e:
            last = f"{type(e).__name__}: {e}"
        wait = 5 * 2 ** attempt
        print(f"  retry in {wait}s ({last})", file=sys.stderr)
        time.sleep(wait)
    sys.exit(f"model call failed: {last}")


# --------------------------------------------------------------------------
# verification against the PDF text layer
# --------------------------------------------------------------------------

def squash(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("—", "-").replace("–", "-")
    return re.sub(r"[\s$]+", "", s).lower()


def verify(raw: dict, pages: list[str]) -> None:
    """Confirm each as_printed string is on its cited page; repair off-by-a-few page numbers."""
    squashed = [squash(p) for p in pages]
    for v in raw.values():
        if not v or v.get("value") is None or not v.get("as_printed"):
            continue
        needle = squash(str(v["as_printed"]))
        quote = squash(v.get("source_quote") or "")
        cited = int(v.get("source_page") or 0)

        def on(p):  # number on page p, preferably with its quote too
            return 1 <= p <= len(pages) and needle in squashed[p - 1]

        if on(cited):
            v["verified"] = True
            continue
        # search outward from the cited page; prefer a page that also has the quoted line
        order = sorted(range(1, len(pages) + 1), key=lambda p: abs(p - cited))
        found = next((p for p in order if on(p) and quote[:40] in squashed[p - 1]), None) \
            or next((p for p in order if on(p) and abs(p - cited) <= 3), None)
        if found:
            v["cited_page"], v["source_page"], v["verified"] = cited, found, True
        elif sums_on_page(v, squashed[cited - 1] if 1 <= cited <= len(pages) else ""):
            v["verified"] = "sum"   # the total isn't printed, but every component is and they add up
        else:
            v["verified"] = False


def sums_on_page(v: dict, page: str) -> bool:
    nums = re.findall(r"\d[\d,]*\.?\d*", v.get("source_quote") or "")
    total = str(v["as_printed"])
    parts = [n for n in nums if n != total]
    try:
        target = float(total.replace(",", ""))
        return len(parts) >= 2 and all(squash(p) in page for p in parts) \
            and abs(sum(float(p.replace(",", "")) for p in parts) - target) < 0.5
    except ValueError:
        return False


# --------------------------------------------------------------------------
# ratios
# --------------------------------------------------------------------------

def fmt(n: float, unit: str) -> str:
    if unit == "pct":
        return f"{n * 100:.2f}%"
    if unit == "x":
        return f"{n:.2f}x"
    if unit == "eps":
        return f"${n:,.2f}"
    if unit == "yrs":
        return f"{n:.1f} yrs"
    return f"${n:,.0f}"


def compute(raw: dict, stated: dict, defs: dict) -> dict:
    def g(k):
        v = raw.get(k)
        return None if not v or v.get("value") is None else float(v["value"])

    def div(a, b):
        return None if a is None or b in (None, 0) else a / b

    def add(*xs):
        return None if any(x is None for x in xs) else sum(xs)

    def sub(a, b):
        return None if a is None or b is None else a - b

    avg_assets = div(add(g("beginning_total_assets"), g("ending_total_assets")), 2)
    # some filers (e.g. Apple) no longer report an interest expense line; treat it as zero for EBITDA
    ebitda = add(g("net_income"), g("interest_expense") or 0, g("income_tax_expense"), g("depreciation_and_amortization"))
    eps = g("basic_eps")
    bvps = div(g("total_stockholders_equity"), g("shares_outstanding"))
    pe = div(g("share_price"), eps)
    avg_stores = div(add(g("beginning_store_count"), g("ending_store_count")), 2)
    occupancy = add(g("store_occupancy_costs"), g("distribution_freight_costs"))

    formulas = {
        "roe": div(g("net_income"), g("total_stockholders_equity")),
        "roa": div(g("net_income"), avg_assets),
        "debt_to_equity": div(g("total_liabilities"), g("total_stockholders_equity")),
        "current_ratio": div(g("total_current_assets"), g("total_current_liabilities")),
        "quick_ratio": div(sub(g("total_current_assets"), g("inventory") or 0), g("total_current_liabilities")),
        "gross_margin": div(sub(g("revenue"), g("cost_of_goods_sold")), g("revenue")),
        "operating_profit_margin": div(g("operating_income"), g("revenue")),
        "net_profit_margin": div(g("net_income"), g("revenue")),
        "ebitda_margin": div(ebitda, g("revenue")),
        "revenue_growth": div(sub(g("revenue"), g("revenue_prior_year")), g("revenue_prior_year")),
        "asset_turnover": div(g("revenue"), avg_assets),
        "inventory_turnover": div(g("cost_of_goods_sold"), g("inventory")),
        "operating_cash_flow_margin": div(g("operating_cash_flow"), g("revenue")),
        "free_cash_flow_margin": div(sub(g("operating_cash_flow"), g("capital_expenditures")), g("revenue")),
        "interest_coverage_ratio": div(g("operating_income"), g("interest_expense")),
        "eps": eps,
        "diluted_eps": g("diluted_eps"),
        "shareholder_equity": g("total_stockholders_equity"),
        "cash_on_hand": g("cash_and_equivalents"),
        "dividend_per_share": g("dividend_per_share"),
        "pe_ratio": pe,
        "pb_ratio": div(g("share_price"), bvps),
        "peg_ratio": div(pe, g("expected_growth_rate")),
        "dividend_yield": div(g("dividend_per_share"), g("share_price")),
        "roi": div(g("investment_gain"), g("investment_cost")),
        "debt_service_ratio": div(g("operating_cash_flow"), g("debt_principal_and_interest_due")),
        "debt_service_coverage_ratio": div(ebitda, g("debt_principal_and_interest_due")),
        "consolidated_sss_growth": div(sub(g("sss_net_sales_current"), g("sss_net_sales_prior")), g("sss_net_sales_prior")),
        "retail_store_sss": div(sub(g("retail_store_sss_net_sales_current"), g("retail_store_sss_net_sales_prior")), g("retail_store_sss_net_sales_prior")),
        "ecommerce_sss": div(sub(g("ecommerce_sss_net_sales_current"), g("ecommerce_sss_net_sales_prior")), g("ecommerce_sss_net_sales_prior")),
        "exclusive_brand_penetration": div(g("exclusive_brand_net_sales"), g("revenue")),
        "third_party_brand_penetration": div(g("third_party_brand_net_sales"), g("revenue")),
        "average_net_revenue_per_store": div(g("retail_store_net_sales"), avg_stores),
        "capex_payback_period": div(g("capex_per_new_store"), g("store_contribution_margin")),
        "merchandise_margin_rate": div(sub(g("revenue"), sub(g("cost_of_goods_sold"), occupancy)), g("revenue")),
        "occupancy_cost_rate": div(occupancy, g("revenue")),
        "gross_margin_rate": div(sub(g("revenue"), g("cost_of_goods_sold")), g("revenue")),
    }

    out = {}
    for key, (name, formula, description, unit) in defs.items():
        number, note = formulas.get(key), ""
        if number is not None:
            note = "Computed from extracted values."
        else:
            s = stated.get(key) or {}
            if s.get("value") is not None:
                number = float(s["value"]) / 100 if unit == "pct" else float(s["value"])
                note = f'Stated directly - p. {s.get("source_page")}: "{s.get("source_quote", "")}"'
        out[key] = {
            "name": name, "formula": formula, "description": description,
            "value": fmt(number, unit) if number is not None else "",
            "number": round(number, 6) if number is not None else None,
            "unit": unit,
            "source_note": note,
        }
    return out


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("source_url")
    ap.add_argument("slug")
    ap.add_argument("--sector", required=True, help='e.g. "Retail"')
    ap.add_argument("--industry", default="", help='e.g. "Home improvement retail"')
    ap.add_argument("--domain", choices=["retail"], default=None, help="also extract domain KPIs")
    ap.add_argument("--country", default="US")
    ap.add_argument("--out", type=Path, default=None, help="write this company's JSON here instead of merging into companies.json")
    a = ap.parse_args()

    pdf_bytes = a.pdf.read_bytes()
    pages = [(p.extract_text() or "") for p in pypdf.PdfReader(a.pdf).pages]
    retail = a.domain == "retail"
    prompt = build_prompt(retail)

    t0 = time.time()
    print(f"[{a.slug}] {len(pages)} pages -> {MODEL}", file=sys.stderr)
    ext, usage = call_gemini(pdf_bytes, prompt)
    raw = {k: ext.get("raw_values", {}).get(k) for k in {**RAW_FIELDS, **(RETAIL_FIELDS if retail else {})}}
    stated = ext.get("stated_ratios") or {}
    verify(raw, pages)

    # Some balance sheets (e.g. Amazon) never print a "Total liabilities" line - derive it, and say so
    ta, eq = raw.get("ending_total_assets"), raw.get("total_stockholders_equity")
    if not (raw.get("total_liabilities") or {}).get("value") and ta and eq and ta.get("value") and eq.get("value"):
        raw["total_liabilities"] = {
            "value": ta["value"] - eq["value"], "derived": True, "unit_note": ta.get("unit_note"),
            "source_quote": "Not printed in the filing - derived as Total Assets minus Total Stockholders' Equity "
                            f"(p. {ta.get('source_page')}). Includes any noncontrolling interests.",
        }

    found = [v for v in raw.values() if v and v.get("value") is not None]
    checked = [v for v in found if "verified" in v]
    unverified = [k for k, v in raw.items() if v and v.get("verified") is False]
    for k in unverified:
        print(f"[{a.slug}] unverified {k}: {raw[k].get('as_printed')!r} p.{raw[k].get('source_page')}", file=sys.stderr)

    company = {
        "company_name": ext.get("company_name"),
        "fiscal_year_end": ext.get("fiscal_year_end"),
        "source_url": a.source_url,
        "country": a.country,
        "sector": a.sector,
        "industry": a.industry,
        "domain": a.domain,
        "raw_values": raw,
        "stated_ratios": {k: v for k, v in stated.items() if v and v.get("value") is not None},
        "ratios": compute(raw, stated, RATIOS),
        "extraction_meta": {
            "model": MODEL,
            "pdf_path": f"pdfs/{a.pdf.name}",
            "pdf_pages": len(pages),
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "thinking_tokens": usage.get("thoughtsTokenCount"),
            "values_found": len(found),
            "values_verified": sum(1 for v in checked if v["verified"]),
            "values_checked": len(checked),
            "unverified_fields": unverified,
            "elapsed_seconds": round(time.time() - t0, 1),
            "prompt": prompt,
        },
    }
    if retail:
        company["domain_ratios"] = compute(raw, stated, RETAIL_RATIOS)

    # sanity: equity should be close to assets - liabilities (gap = noncontrolling interests etc.)
    ta, tl, eq = (raw.get(k) or {} for k in ("ending_total_assets", "total_liabilities", "total_stockholders_equity"))
    if all(x.get("value") for x in (ta, tl, eq)):
        gap = (ta["value"] - tl["value"] - eq["value"]) / ta["value"]
        if abs(gap) > 0.02:
            print(f"[{a.slug}] note: assets - liabilities - equity = {gap:.1%} of assets", file=sys.stderr)

    meta = company["extraction_meta"]
    print(f"[{a.slug}] {meta['values_found']} values, {meta['values_verified']}/{meta['values_checked']} verified "
          f"on page; unverified: {unverified or 'none'}; {meta['elapsed_seconds']}s", file=sys.stderr)

    if a.out:
        a.out.write_text(json.dumps(company, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}
        data[a.slug] = company
        DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
