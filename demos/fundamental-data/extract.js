// In-browser version of pipeline.py: annual-report PDF -> Gemini (via LLM Foundry) -> numbers checked
// against the PDF's own text layer -> ratios computed with fixed formulas -> saved in this browser.
// The LLM only *reads* numbers (value, page, verbatim quote). Every ratio is computed here.
// Keep RAW_FIELDS / RATIOS / buildPrompt / compute in step with pipeline.py.
(function () {
  const MODEL = "gemini-3.8-flash";
  const LOCAL_KEY = "fundamentals.localCompanies";

  if (window.pdfjsLib) pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

  // ------------------------------------------------------------------------
  // what to extract
  // ------------------------------------------------------------------------

  const RAW_FIELDS = {
    net_income: "Net income ATTRIBUTABLE TO THE COMPANY (exclude noncontrolling interests), Consolidated Statements of Operations/Income, most recent fiscal year",
    total_stockholders_equity: "Total shareholders' equity attributable to the company (exclude noncontrolling interests), Consolidated Balance Sheet, most recent fiscal year end",
    beginning_total_assets: "Total Assets, Consolidated Balance Sheet, PRIOR fiscal year end",
    ending_total_assets: "Total Assets, Consolidated Balance Sheet, most recent fiscal year end",
    total_liabilities: "Total Liabilities, Consolidated Balance Sheet, most recent fiscal year end",
    total_current_assets: "Total Current Assets, Consolidated Balance Sheet",
    total_current_liabilities: "Total Current Liabilities, Consolidated Balance Sheet",
    inventory: "Inventory, Consolidated Balance Sheet",
    cash_and_equivalents: "Cash and Cash Equivalents, Consolidated Balance Sheet",
    revenue: "Total Revenue / Net Sales, Consolidated Statements of Operations, most recent fiscal year",
    revenue_prior_year: "Total Revenue / Net Sales, Consolidated Statements of Operations, PRIOR fiscal year (same line as revenue)",
    cost_of_goods_sold: "Cost of Goods Sold / Cost of Sales / Cost of Merchandise Sold, Consolidated Statements of Operations",
    operating_income: "Operating Income / Income from Operations, Consolidated Statements of Operations",
    interest_expense: "Interest Expense, Consolidated Statements of Operations (gross interest expense, not net of interest income, when both are shown)",
    income_tax_expense: "Income Tax Expense / Provision for Income Taxes, Consolidated Statements of Operations",
    depreciation_and_amortization: "Depreciation and Amortization, Consolidated Statements of Cash Flows",
    basic_eps: "Basic Earnings Per Share, Consolidated Statements of Operations",
    diluted_eps: "Diluted Earnings Per Share, Consolidated Statements of Operations",
    dividend_per_share: "Dividends declared/paid per share",
    operating_cash_flow: "Net Cash Provided by Operating Activities, Consolidated Statements of Cash Flows",
    capital_expenditures: "Purchases of property and equipment / capital expenditures, Consolidated Statements of Cash Flows (report as a positive number)",
    shares_outstanding: "Shares of common stock outstanding",
    share_price: "The company's own stock price, if stated anywhere in this document",
    expected_growth_rate: "A forward-looking earnings growth rate estimate, if the company states one",
    investment_cost: "Cost of a specific named investment, if the report discusses one",
    investment_gain: "Gain on that same named investment, if discussed alongside its cost",
    debt_principal_and_interest_due: "Principal + interest due in the coming year on borrowed-money debt (loans, bonds, credit facility draws)",
  };

  const RETAIL_FIELDS = {
    sss_net_sales_current: "Same-store (comparable) net sales across all channels, current fiscal year",
    sss_net_sales_prior: "Same-store (comparable) net sales across all channels, prior fiscal year - same store base as above",
    retail_store_sss_net_sales_current: "Same-store net sales from physical retail stores only, current fiscal year",
    retail_store_sss_net_sales_prior: "Same-store net sales from physical retail stores only, prior fiscal year",
    ecommerce_sss_net_sales_current: "Same-store (comparable) net sales from the e-commerce/direct-to-consumer channel, current fiscal year",
    ecommerce_sss_net_sales_prior: "Same-store (comparable) net sales from the e-commerce/direct-to-consumer channel, prior fiscal year",
    exclusive_brand_net_sales: "Net sales from the retailer's own exclusive/proprietary brands",
    third_party_brand_net_sales: "Net sales from third-party/national brands carried by the retailer",
    beginning_store_count: "Number of stores open at the start of the fiscal year (a count, not dollars)",
    ending_store_count: "Number of stores open at the end of the fiscal year (a count, not dollars)",
    retail_store_net_sales: "Net sales from physical retail stores (all stores, not just comparable), most recent fiscal year",
    capex_per_new_store: "Average capital expenditure to open one new store, net of landlord/tenant allowances",
    store_contribution_margin: "Annual store-level contribution margin for a mature/average store (e.g. EBITDAR minus rent), if disclosed",
    store_occupancy_costs: "Store occupancy costs (rent, utilities, property taxes, common area maintenance) included within cost of goods sold",
    distribution_freight_costs: "Distribution center and freight/fulfillment costs included within cost of goods sold",
  };

  // key -> [name, formula, description, unit]   unit: pct | x | usd | eps | yrs
  const RATIOS = {
    roe: ["ROE (Return on Equity)", "Net Income / Total Stockholders' Equity", "Measures profitability relative to shareholders' equity. Higher means management is using investor capital more efficiently to generate profit.", "pct"],
    roa: ["ROA (Return on Assets)", "Net Income / Average Total Assets", "Average Total Assets is (Beginning + Ending Total Assets) / 2. Higher means management is using resources more efficiently to generate earnings.", "pct"],
    debt_to_equity: ["Debt-to-Equity Ratio", "Total Liabilities / Total Stockholders' Equity", "Measures leverage - how much a company finances its operations with debt versus its own funds. A lower ratio generally indicates greater financial stability.", "x"],
    current_ratio: ["Current Ratio", "Total Current Assets / Total Current Liabilities", "Measures ability to pay short-term obligations (due within one year) with current assets. Above 1.0 is healthy; 1.5-2.0 is generally considered ideal.", "x"],
    quick_ratio: ["Quick Ratio (Acid-Test Ratio)", "(Current Assets - Inventory) / Current Liabilities", "Measures ability to pay short-term liabilities with the most liquid assets, excluding inventory. A ratio of 1:1 is considered ideal.", "x"],
    gross_margin: ["Gross Margin", "(Revenue - Cost of Goods Sold) / Revenue", "Share of revenue left after the direct cost of the goods and services sold. Driven by pricing power and product mix.", "pct"],
    operating_profit_margin: ["Operating Profit Margin", "Operating Income / Revenue", "Measures core operational efficiency - the percentage of revenue remaining after covering cost of goods sold and operating expenses, before interest and taxes. Higher indicates better profitability.", "pct"],
    net_profit_margin: ["Net Profit Margin", "Net Income / Revenue", "Share of every dollar of revenue that ends up as profit for shareholders, after all expenses, interest and taxes.", "pct"],
    ebitda_margin: ["EBITDA Margin", "(Net Income + Interest Expense + Income Tax Expense + Depreciation & Amortization) / Revenue", "Measures operational profitability excluding financing, tax, and non-cash expenses. Higher indicates the business converts more of its core operations into earnings.", "pct"],
    revenue_growth: ["Revenue Growth (YoY)", "(Revenue - Prior-Year Revenue) / Prior-Year Revenue", "Year-over-year change in total revenue, from the two years shown on the income statement.", "pct"],
    asset_turnover: ["Asset Turnover", "Revenue / Average Total Assets", "Revenue generated per dollar of assets. High for asset-light or high-volume businesses such as discount retail.", "x"],
    inventory_turnover: ["Inventory Turnover", "Cost of Goods Sold / Ending Inventory", "How many times inventory is sold through in a year. Higher means leaner stock and faster sell-through.", "x"],
    operating_cash_flow_margin: ["Operating Cash Flow Margin", "Operating Cash Flow / Revenue", "Cash generated by operations per dollar of revenue - a cash-based check on reported margins.", "pct"],
    free_cash_flow_margin: ["Free Cash Flow Margin", "(Operating Cash Flow - Capital Expenditures) / Revenue", "Cash left after reinvesting in property and equipment, per dollar of revenue.", "pct"],
    interest_coverage_ratio: ["Interest Coverage Ratio", "Operating Income / Interest Expense", "Measures ability to pay interest on outstanding debt (uses Operating Income as a proxy for EBIT). Above 2-3 is typically considered good; higher means lower default risk.", "x"],
    eps: ["Basic EPS", "Reported directly on the Income Statement", "Net income divided by weighted-average shares outstanding, as calculated and disclosed by the company itself.", "eps"],
    diluted_eps: ["Diluted EPS", "Reported directly on the Income Statement", "Like Basic EPS, but assumes all convertible securities (options, warrants, convertible debt) are exercised - a conservative, usually lower, per-share figure.", "eps"],
    shareholder_equity: ["Shareholder Equity", "Total Assets - Total Liabilities", "A company's net worth - the residual value belonging to owners after all liabilities are settled. Reported directly on the Balance Sheet.", "usd"],
    cash_on_hand: ["Cash on Hand", "Reported directly on the Balance Sheet", "Total immediately accessible cash and cash equivalents.", "usd"],
    dividend_per_share: ["Dividend Per Share", "Reported directly on the financial statements", "The portion of profit paid to shareholders per share owned. 0 if the company does not pay a dividend.", "eps"],
    pe_ratio: ["Price-to-Earnings (P/E) Ratio", "Share Price / Earnings Per Share (EPS)", "Measures how much investors pay per $1 of earnings. A high ratio may suggest overvaluation or high growth expectations.", "x"],
    pb_ratio: ["Price-to-Book (P/B) Ratio", "Share Price / Book Value Per Share", "Measures market valuation relative to net asset (book) value. A lower P/B (often < 1) may indicate an undervalued stock.", "x"],
    peg_ratio: ["Price/Earnings-to-Growth (PEG) Ratio", "P/E Ratio / Expected Earnings Growth Rate (%)", "Divides P/E by expected earnings growth to judge value relative to growth prospects. ~1.0 suggests fair value.", "x"],
    dividend_yield: ["Dividend Yield", "Annual Dividend Per Share / Share Price", "Annualized cash dividends as a percentage of the share price.", "pct"],
    roi: ["ROI (Return on Investment)", "Investment Gain / Cost of Investment", "Evaluates profitability and efficiency of a specific investment by comparing its gain to its initial cost. Only computable when the report explicitly discusses a specific investment in these terms.", "pct"],
    debt_service_ratio: ["Debt Service Ratio", "Operating Cash Flow / (Principal + Interest Payments Due)", "Measures ability to cover debt obligations (principal + interest) with operating cash flow. Above 1.0 is sufficient; 1.25+ is standard for lenders.", "x"],
    debt_service_coverage_ratio: ["Debt Service Coverage Ratio", "EBITDA / (Principal + Interest Payments Due)", "Measures ability to cover debt obligations with EBITDA. 1.0 is break-even; lenders typically require 1.25+.", "x"],
  };

  const RETAIL_RATIOS = {
    consolidated_sss_growth: ["Consolidated Same-Store Sales Growth", "(Same-Store Net Sales, Current Year - Same-Store Net Sales, Prior Year) / Same-Store Net Sales, Prior Year", "Retail KPI. Net sales growth from stores open long enough (typically 14+ months) to exclude the effect of new store openings.", "pct"],
    retail_store_sss: ["Retail Store Same-Store Sales Growth", "(Store SSS Net Sales, Current Period - Store SSS Net Sales, Prior Period) / Store SSS Net Sales, Prior Period", "Retail KPI. Same-store sales growth isolated to the physical retail store channel.", "pct"],
    ecommerce_sss: ["E-commerce Same-Store Sales Growth", "(E-commerce Net Sales, Current Period - E-commerce Net Sales, Prior Period) / E-commerce Net Sales, Prior Period", "Retail KPI. Same-store sales growth isolated to the e-commerce/direct- to-consumer channel.", "pct"],
    exclusive_brand_penetration: ["Exclusive Brand Penetration", "Net Sales from Exclusive Brands / Total Net Sales", "Retail KPI. Share of revenue from a retailer's own higher-margin proprietary brands versus third-party/national brands.", "pct"],
    third_party_brand_penetration: ["Third-Party Brand Penetration", "Net Sales from Third-Party Brands / Total Net Sales", "Retail KPI. Share of revenue from third-party/national brands versus a retailer's own exclusive brands.", "pct"],
    average_net_revenue_per_store: ["Average Net Revenue Per Store", "Retail Store Net Sales / Average Store Count", "Retail KPI. Average Store Count is (Beginning + Ending Store Count) / 2. Measures individual store productivity.", "usd"],
    capex_payback_period: ["CapEx Payback Period (Years)", "Initial Capital Expenditure Per New Store / Annual Store-Level Contribution Margin", "Retail KPI. Years needed for a new store's investment to be recovered from its own contribution margin (e.g. EBITDAR minus rent). Shorter is better.", "yrs"],
    merchandise_margin_rate: ["Merchandise Margin Rate", "(Net Sales - (Cost of Goods Sold - Occupancy and Distribution Costs)) / Net Sales", "Retail KPI. Margin on product sales alone, excluding the store occupancy and distribution/fulfillment costs bundled into Cost of Goods Sold.", "pct"],
    occupancy_cost_rate: ["Occupancy Cost Rate", "(Store Occupancy Costs + Distribution & Freight/Fulfillment Costs) / Net Sales", "Retail KPI. Operating leverage on fixed retail and distribution infrastructure, as a percentage of net sales.", "pct"],
    gross_margin_rate: ["Gross Margin Rate", "(Net Sales - Cost of Goods Sold) / Net Sales", "Retail KPI. GAAP gross profit margin after product and store/warehouse occupancy overhead - equals Merchandise Margin Rate minus Occupancy Cost Rate.", "pct"],
  };

  function buildPrompt(retail) {
    const fields = { ...RAW_FIELDS, ...(retail ? RETAIL_FIELDS : {}) };
    const ratios = { ...RATIOS, ...(retail ? RETAIL_RATIOS : {}) };
    const fieldLines = Object.entries(fields).map(([k, v]) => `- ${k}: ${v}`).join("\n");
    const ratioLines = Object.entries(ratios).map(([k, v]) => `- ${k}: ${v[0]}`).join("\n");
    const retailNote = retail
      ? "\nSome of the fields and ratios below are retail-domain KPIs (same-store sales, store counts, brand mix). Only fill them where the document actually discloses them; otherwise leave them null.\n"
      : "";
    return `You are extracting facts from a company's annual report for its MOST RECENT fiscal year. You have TWO jobs below. Do no arithmetic yourself either way - only report numbers literally printed in the document, never from outside knowledge.
${retailNote}
Rules that apply throughout:
- Every field is optional. Use value: 0 ONLY when the document EXPLICITLY states a fact equivalent to zero/none (e.g. "we have not declared any cash dividends") - quote that exact statement in source_quote. If the document never discusses a topic, use null - absence of evidence is not zero.
- Match by meaning, not exact wording - filers phrase the same concept differently (e.g. "Shareholders' equity" = "Total stockholders' equity"; "Cost of sales" = "Cost of goods sold").
- When the same figure appears at different precision in different places, use the exact one from the primary financial statement, not a rounded mention elsewhere.
- If a line item is split into sub-components shown separately (e.g. "Interest: Debt ... Finance lease ..."), report their sum and show each component plus the total in source_quote.

JOB 1 - Raw input values. Find these in the CONSOLIDATED financial statements:

${fieldLines}

For each raw value, report:
- value: the exact number in whole dollars (if the statement says "in millions", multiply by 1,000,000; "in thousands" by 1,000). Per-share fields (EPS, dividend per share, share price) are already per-share - do not scale them. Counts (shares, stores) are plain counts, scaled only if the document says shares are in thousands/millions.
- as_printed: an exact substring a text search would find on the page, used to jump to this value. If a digit is printed, use it exactly as printed (e.g. "180,942"), BEFORE any unit scaling. If the value is INFERRED from a qualitative statement with no digit printed (e.g. "we have not declared any cash dividends" implying $0), use a short distinctive phrase copied verbatim from source_quote.
- unit_note: the exact nearby text establishing scale, e.g. "in thousands", "in millions", or "whole dollars" if none - verbatim.
- source_page: the PDF page number (1-indexed, counting actual PDF pages, NOT the printed folio) where you found it.
- source_quote: the exact line of text containing this number, quoted verbatim.

JOB 2 - Already-stated ratios. Check whether the document ALREADY states the final value for any of these itself (e.g. in a key-metrics table or MD&A - such as "comparable sales increased 4.5%", "ROIC 25.7%"):

${ratioLines}

Only report a value if the FINAL ratio is stated as such in the text - never compute it, and never confuse a raw line item with a stated ratio. Percentages are reported as the printed percent number (4.5 for "4.5%"); multiples as the number (2.1 for "2.1x"); years as years. If not explicitly stated, value is null. Report source_page and source_quote for any you find. For same-store/comparable sales growth, prefer the company-wide / total-company figure, and say which segment in source_quote.

Also report company_name (full legal name) and fiscal_year_end (ISO date, e.g. "2025-03-29").

Respond with ONLY valid JSON:
{
  "company_name": "...",
  "fiscal_year_end": "YYYY-MM-DD",
  "raw_values": { "<field>": {"value": 0, "as_printed": "...", "unit_note": "...", "source_page": 0, "source_quote": "..."} or null, ... one key per field above },
  "stated_ratios": { "<ratio>": {"value": 0, "source_page": 0, "source_quote": "..."} or null, ... one key per ratio above }
}`;
  }

  // ------------------------------------------------------------------------
  // PDF + model call
  // ------------------------------------------------------------------------

  async function readPages(file) {
    const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
    const pages = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const content = await (await pdf.getPage(i)).getTextContent();
      pages.push(content.items.map(it => it.str).join(" "));
    }
    return pages;
  }

  const toBase64 = file => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1]);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  async function callGemini(pdfBase64, prompt) {
    const body = JSON.stringify({
      contents: [{ role: "user", parts: [
        { inline_data: { mime_type: "application/pdf", data: pdfBase64 } },
        { text: prompt },
      ] }],
      generationConfig: { responseMimeType: "application/json", maxOutputTokens: 65536, thinkingConfig: { thinkingLevel: "medium" } },
    });
    let last = "";
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const res = await llmFoundry.fetch(`/gemini/v1beta/models/${MODEL}:generateContent`, { method: "POST", body });
        if (res.ok) {
          const d = await res.json();
          const cand = (d.candidates || [{}])[0];
          const text = ((cand.content || {}).parts || []).filter(p => !p.thought).map(p => p.text || "").join("");
          if (text.trim()) return [JSON.parse(text), d.usageMetadata || {}];
          last = `empty reply, finish=${cand.finishReason}`;
        } else if ([429, 500, 502, 503, 504].includes(res.status)) {
          last = `HTTP ${res.status}`;
        } else {
          throw Object.assign(new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`), { fatal: true });
        }
      } catch (e) {
        if (e.fatal) throw e;
        last = `${e.name}: ${e.message}`;
      }
      await sleep(5000 * 2 ** attempt);
    }
    throw new Error(`model call failed: ${last}`);
  }

  // ------------------------------------------------------------------------
  // verification against the PDF text layer
  // ------------------------------------------------------------------------

  const squash = s => String(s).replace(/[’‘]/g, "'").replace(/[—–]/g, "-").replace(/[\s$]+/g, "").toLowerCase();

  // Confirm each as_printed string is on its cited page; repair off-by-a-few page numbers.
  function verify(raw, pages) {
    const squashed = pages.map(squash);
    for (const v of Object.values(raw)) {
      if (!v || v.value == null || !v.as_printed) continue;
      const needle = squash(v.as_printed);
      const quote = squash(v.source_quote || "");
      const cited = Number(v.source_page) || 0;
      const on = p => p >= 1 && p <= pages.length && squashed[p - 1].includes(needle);
      if (on(cited)) { v.verified = true; continue; }
      // search outward from the cited page; prefer a page that also has the quoted line
      const order = pages.map((_, i) => i + 1).sort((a, b) => Math.abs(a - cited) - Math.abs(b - cited));
      const found = order.find(p => on(p) && squashed[p - 1].includes(quote.slice(0, 40)))
        || order.find(p => on(p) && Math.abs(p - cited) <= 3);
      if (found) Object.assign(v, { cited_page: cited, source_page: found, verified: true });
      else if (sumsOnPage(v, cited >= 1 && cited <= pages.length ? squashed[cited - 1] : "")) v.verified = "sum"; // the total isn't printed, but every component is and they add up
      else v.verified = false;
    }
  }

  function sumsOnPage(v, page) {
    const nums = (v.source_quote || "").match(/\d[\d,]*\.?\d*/g) || [];
    const total = String(v.as_printed);
    const parts = nums.filter(n => n !== total);
    const target = parseFloat(total.replace(/,/g, ""));
    if (isNaN(target)) return false;
    return parts.length >= 2 && parts.every(p => page.includes(squash(p)))
      && Math.abs(parts.reduce((s, p) => s + parseFloat(p.replace(/,/g, "")), 0) - target) < 0.5;
  }

  // ------------------------------------------------------------------------
  // ratios
  // ------------------------------------------------------------------------

  function fmt(n, unit) {
    if (unit === "pct") return `${(n * 100).toFixed(2)}%`;
    if (unit === "x") return `${n.toFixed(2)}x`;
    if (unit === "eps") return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (unit === "yrs") return `${n.toFixed(1)} yrs`;
    return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function compute(raw, stated, defs) {
    const g = k => { const v = raw[k]; return !v || v.value == null ? null : Number(v.value); };
    const div = (a, b) => a == null || b == null || b === 0 ? null : a / b;
    const add = (...xs) => xs.some(x => x == null) ? null : xs.reduce((s, x) => s + x, 0);
    const sub = (a, b) => a == null || b == null ? null : a - b;

    const avgAssets = div(add(g("beginning_total_assets"), g("ending_total_assets")), 2);
    // some filers (e.g. Apple) no longer report an interest expense line; treat it as zero for EBITDA
    const ebitda = add(g("net_income"), g("interest_expense") || 0, g("income_tax_expense"), g("depreciation_and_amortization"));
    const eps = g("basic_eps");
    const bvps = div(g("total_stockholders_equity"), g("shares_outstanding"));
    const pe = div(g("share_price"), eps);
    const avgStores = div(add(g("beginning_store_count"), g("ending_store_count")), 2);
    const occupancy = add(g("store_occupancy_costs"), g("distribution_freight_costs"));

    const formulas = {
      roe: div(g("net_income"), g("total_stockholders_equity")),
      roa: div(g("net_income"), avgAssets),
      debt_to_equity: div(g("total_liabilities"), g("total_stockholders_equity")),
      current_ratio: div(g("total_current_assets"), g("total_current_liabilities")),
      quick_ratio: div(sub(g("total_current_assets"), g("inventory") || 0), g("total_current_liabilities")),
      gross_margin: div(sub(g("revenue"), g("cost_of_goods_sold")), g("revenue")),
      operating_profit_margin: div(g("operating_income"), g("revenue")),
      net_profit_margin: div(g("net_income"), g("revenue")),
      ebitda_margin: div(ebitda, g("revenue")),
      revenue_growth: div(sub(g("revenue"), g("revenue_prior_year")), g("revenue_prior_year")),
      asset_turnover: div(g("revenue"), avgAssets),
      inventory_turnover: div(g("cost_of_goods_sold"), g("inventory")),
      operating_cash_flow_margin: div(g("operating_cash_flow"), g("revenue")),
      free_cash_flow_margin: div(sub(g("operating_cash_flow"), g("capital_expenditures")), g("revenue")),
      interest_coverage_ratio: div(g("operating_income"), g("interest_expense")),
      eps,
      diluted_eps: g("diluted_eps"),
      shareholder_equity: g("total_stockholders_equity"),
      cash_on_hand: g("cash_and_equivalents"),
      dividend_per_share: g("dividend_per_share"),
      pe_ratio: pe,
      pb_ratio: div(g("share_price"), bvps),
      peg_ratio: div(pe, g("expected_growth_rate")),
      dividend_yield: div(g("dividend_per_share"), g("share_price")),
      roi: div(g("investment_gain"), g("investment_cost")),
      debt_service_ratio: div(g("operating_cash_flow"), g("debt_principal_and_interest_due")),
      debt_service_coverage_ratio: div(ebitda, g("debt_principal_and_interest_due")),
      consolidated_sss_growth: div(sub(g("sss_net_sales_current"), g("sss_net_sales_prior")), g("sss_net_sales_prior")),
      retail_store_sss: div(sub(g("retail_store_sss_net_sales_current"), g("retail_store_sss_net_sales_prior")), g("retail_store_sss_net_sales_prior")),
      ecommerce_sss: div(sub(g("ecommerce_sss_net_sales_current"), g("ecommerce_sss_net_sales_prior")), g("ecommerce_sss_net_sales_prior")),
      exclusive_brand_penetration: div(g("exclusive_brand_net_sales"), g("revenue")),
      third_party_brand_penetration: div(g("third_party_brand_net_sales"), g("revenue")),
      average_net_revenue_per_store: div(g("retail_store_net_sales"), avgStores),
      capex_payback_period: div(g("capex_per_new_store"), g("store_contribution_margin")),
      merchandise_margin_rate: div(sub(g("revenue"), sub(g("cost_of_goods_sold"), occupancy)), g("revenue")),
      occupancy_cost_rate: div(occupancy, g("revenue")),
      gross_margin_rate: div(sub(g("revenue"), g("cost_of_goods_sold")), g("revenue")),
    };

    const out = {};
    for (const [key, [name, formula, description, unit]] of Object.entries(defs)) {
      let number = formulas[key] ?? null, note = "";
      if (number != null) note = "Computed from extracted values.";
      else {
        const s = stated[key] || {};
        if (s.value != null) {
          number = unit === "pct" ? Number(s.value) / 100 : Number(s.value);
          note = `Stated directly - p. ${s.source_page}: "${s.source_quote || ""}"`;
        }
      }
      out[key] = {
        name, formula, description,
        value: number != null ? fmt(number, unit) : "",
        number: number != null ? Math.round(number * 1e6) / 1e6 : null,
        unit, source_note: note,
      };
    }
    return out;
  }

  // ------------------------------------------------------------------------
  // storage: company JSON in localStorage, the PDF itself in IndexedDB
  // ------------------------------------------------------------------------

  function loadLocal() {
    try { return JSON.parse(localStorage.getItem(LOCAL_KEY) || "{}"); } catch { return {}; }
  }
  function saveLocal(all) { localStorage.setItem(LOCAL_KEY, JSON.stringify(all)); }

  function idb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open("fundamentals", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("pdfs");
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function idbDo(mode, fn) {
    const db = await idb();
    return new Promise((resolve, reject) => {
      const req = fn(db.transaction("pdfs", mode).objectStore("pdfs"));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  const putPdf = (slug, file) => idbDo("readwrite", s => s.put(file, slug));
  const getPdf = slug => idbDo("readonly", s => s.get(slug)).catch(() => null);
  const deletePdf = slug => idbDo("readwrite", s => s.delete(slug)).catch(() => null);

  function removeLocal(slug) {
    const all = loadLocal();
    delete all[slug];
    saveLocal(all);
    return deletePdf(slug);
  }

  const slugify = s => String(s || "company").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "company";

  // ------------------------------------------------------------------------
  // run the whole flow; onStage(stage, state, detail) drives the progress diagram
  // ------------------------------------------------------------------------

  async function run(file, { sector, industry, domain, sourceUrl, existingSlugs, onStage }) {
    const stage = (id, state, detail) => onStage && onStage(id, state, detail);
    const t0 = Date.now();
    const retail = domain === "retail";

    stage("read", "active", `${(file.size / 1e6).toFixed(1)} MB`);
    const [pages, pdfBase64] = await Promise.all([readPages(file), toBase64(file)]);
    stage("read", "done", `${pages.length} pages · ${(file.size / 1e6).toFixed(1)} MB`);

    stage("model", "active", `${MODEL} reading ${pages.length} pages…`);
    const prompt = buildPrompt(retail);
    const tModel = Date.now();
    const [ext, usage] = await callGemini(pdfBase64, prompt);
    const fieldKeys = Object.keys({ ...RAW_FIELDS, ...(retail ? RETAIL_FIELDS : {}) });
    const raw = Object.fromEntries(fieldKeys.map(k => [k, (ext.raw_values || {})[k] ?? null]));
    const stated = ext.stated_ratios || {};
    const foundCount = Object.values(raw).filter(v => v && v.value != null).length;
    stage("model", "done", `${foundCount} of ${fieldKeys.length} values · ${((Date.now() - tModel) / 1000).toFixed(0)}s`);

    stage("verify", "active", "Searching the text layer…");
    verify(raw, pages);
    // Some balance sheets (e.g. Amazon) never print a "Total liabilities" line - derive it, and say so
    const ta = raw.ending_total_assets, eq = raw.total_stockholders_equity;
    if (!(raw.total_liabilities || {}).value && ta && eq && ta.value && eq.value) {
      raw.total_liabilities = {
        value: ta.value - eq.value, derived: true, unit_note: ta.unit_note,
        source_quote: `Not printed in the filing - derived as Total Assets minus Total Stockholders' Equity (p. ${ta.source_page}). Includes any noncontrolling interests.`,
      };
    }
    const found = Object.values(raw).filter(v => v && v.value != null);
    const checked = found.filter(v => "verified" in v);
    const verifiedCount = checked.filter(v => v.verified).length;
    const unverified = Object.keys(raw).filter(k => raw[k] && raw[k].verified === false);
    stage("verify", "done", `${verifiedCount}/${checked.length} found on the cited page`);

    stage("ratios", "active", "Applying fixed formulas…");
    const ratios = compute(raw, stated, RATIOS);
    const domainRatios = retail ? compute(raw, stated, RETAIL_RATIOS) : null;
    const nRatios = Object.values(ratios).filter(r => r.number != null).length;
    stage("ratios", "done", `${nRatios} of ${Object.keys(RATIOS).length} ratios${domainRatios ? ` + ${Object.values(domainRatios).filter(r => r.number != null).length} retail KPIs` : ""}`);

    stage("save", "active", "Writing to this browser…");
    const base = "local-" + slugify(ext.company_name || file.name.replace(/\.pdf$/i, ""));
    let slug = base;
    for (let i = 2; existingSlugs.includes(slug); i++) slug = `${base}-${i}`;
    const company = {
      company_name: ext.company_name || file.name,
      fiscal_year_end: ext.fiscal_year_end,
      source_url: sourceUrl || "",
      country: "",
      sector, industry, domain: domain || null,
      local: true,
      added_at: new Date().toISOString(),
      raw_values: raw,
      stated_ratios: Object.fromEntries(Object.entries(stated).filter(([, v]) => v && v.value != null)),
      ratios,
      extraction_meta: {
        model: MODEL,
        pdf_name: file.name,
        pdf_pages: pages.length,
        input_tokens: usage.promptTokenCount,
        output_tokens: usage.candidatesTokenCount,
        thinking_tokens: usage.thoughtsTokenCount,
        values_found: found.length,
        values_verified: verifiedCount,
        values_checked: checked.length,
        unverified_fields: unverified,
        elapsed_seconds: Math.round((Date.now() - t0) / 100) / 10,
      },
    };
    if (domainRatios) company.domain_ratios = domainRatios;
    const all = loadLocal();
    all[slug] = company;
    saveLocal(all);
    let pdfStored = true;
    try { await putPdf(slug, file); } catch { pdfStored = false; }
    stage("save", "done", pdfStored ? "Ratios in localStorage · PDF in IndexedDB" : "Ratios in localStorage (PDF not stored)");
    return { slug, company };
  }

  window.fundamentalsPipeline = { MODEL, run, loadLocal, removeLocal, getPdf };
})();
