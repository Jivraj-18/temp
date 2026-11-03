# Demo Script — Unmasking Hidden Risks with OSINT

**Subtitle:** Elevating MSCI's index integrity with Agentic AI
**Demo page:** [`osint.html`](osint.html) · Live: <https://jivraj-18.github.io/temp/demos/osint.html>

> **How to read this script:** the first half is the *why* (talking points for the opening). The second half walks through the **Input page** and the **Result page** in the order you show them on screen.

---

## 1. Opening — why this matters

MSCI's reputation and regulatory compliance hinge on the absolute integrity of its indices. The critical challenge is identifying obscured corporate activities that standard classifications miss.

**The problem.** Companies increasingly use sophisticated tactics to mask controversial or sanctioned operations — from dual-use technologies and localized military applications to complex shadow entities. These hidden activities create regulatory, reputational and financial risk for index inclusions, and they slip past conventional GICS or industry codes.

**The solution — DeepSeek OSINT.** An Agentic AI application, built on large language models, that uncovers these hidden risks. This approach has proven highly effective in Open Source Intelligence (OSINT) and investigation workflows, turning vast datasets into actionable insight.

> Key line: *"It's not just about finding information — it's about understanding and connecting it to reveal hidden risks that traditional methods simply cannot."*

## 2. How it works (three stages)

| Stage | What happens | Why it helps |
|---|---|---|
| **1. Intelligent data ingestion** | The agent continuously monitors and ingests large volumes of unstructured data (public records, leaked documents, web dumps, dark-web forums) from many OSINT channels. | Comprehensive, near real-time coverage beyond traditional data feeds. |
| **2. LLM entity extraction & context** | LLMs identify and extract key entities — names, organizations, locations, IP addresses, dates, relationships — and interpret complex narratives, going well beyond keyword search. | Faster investigation; picks up nuance and connections traditional methods miss. |
| **3. Risk unmasking & synthesis** | The agent cross-references and correlates findings to reveal obscured corporate actions, hidden affiliations and potential sanction violations, presented as clear, prioritized intelligence. | Precise, risk-mitigating insight for MSCI's governance and index-integrity teams. |

---

## 3. Live walkthrough — Input page ("tell it what to find")

| Step | Do | Say / explain |
|---|---|---|
| **1. Enter entity details** | Type the subject's core identifier (name, registration number or other unique ID). | Accuracy here drives the relevance and depth of everything that follows. |
| **2. Select subject type** | Pick the classification — e.g. Individual, Entity, Financial Institution, Vessel, NGO. | Tells the engine which search strategies and data sources to prioritize. |
| **3. Specify location** *(optional)* | Enter a known location, or leave blank. | A location narrows the search; leaving it blank triggers a broader, global analysis. |
| **4. Initiate OSINT scan** | Click to start the scan. | The engine queries integrated sources such as **OpenSanctions**, **ICIJ Offshore Leaks**, **OpenCorporates**, **Equasis** and the **GDELT Project**, then aggregates and analyses the results. |

## 4. Live walkthrough — Result page ("synthesized intelligence for decision-making")

Walk down the result page section by section:

| # | Section | Purpose | What to point out |
|---|---|---|---|
| 1 | **Subject identity & risk profile** | Establishes who/what the subject is and its immediate risk posture. | Confirmed subject type (individual, entity, vessel, bank, NGO…) and the colour-coded risk level: Low / Medium / High / Critical. |
| 2 | **Operational domicile mapping** | Shows the subject's global footprint and regulatory exposure. | All registered, operational and suspected jurisdictions, set against their regulatory environments. |
| 3 | **Intelligence synthesis & typology** | Narrative history of conduct plus a quantitative breakdown of risk categories. | A concise summary of criminal history, litigation and settlements, and the weighting of offence types (e.g. financial crime, regulatory breach). |
| 4 | **Reputational risk (adverse media)** | Evaluates public perception and potential brand damage. | Negative news, blogs and forum content, filtered for derogatory sentiment to gauge severity. |
| 5 | **Regulatory & jurisdictional guidance** | Official stances and compliance requirements from local authorities. | Warnings, sanctions or recommendations from regulators, translated into concrete compliance or mitigation steps. |
| 6 | **Source transparency & verification** | Auditability and independent validation. | Every repository, OSINT API and public record used, with links/citations for each data point. |

---

## 5. Close — way forward

To reach optimal performance, the engine needs further training on complex search parameters — especially **name permutations, aliases and AKAs**, using fuzzy matching. Matching will follow a tiered approach:

1. Primary exact match
2. Secondary exact match
3. Refining category assumptions to minimise both false positives and false negatives
