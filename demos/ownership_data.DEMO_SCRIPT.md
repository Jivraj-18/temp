# Demo Script — Institutional Holdings & Beneficial Ownership Profiles

**Demo page:** [`ownership_data.html`](ownership_data.html) · Live: <https://jivraj-18.github.io/temp/demos/ownership_data.html>
**Run time:** ~6 minutes · **Nine steps** (matches the page's guided tour, Step 1 of 9 … Step 9 of 9)

> **How to read this script:** each step has a **Do** line (what to click on screen) and a **Say** line (what to tell the audience). Read the *Say* text as-is or paraphrase it.

---

### Step 1 — One profile, two kinds of disclosure

**Do:** Point to the two main data sections shown side by side.

**Say:**
> "Welcome to the core profile view. Here, we present institutional 13F holdings and Schedule 13D/G beneficial ownership side by side for a single issuer. Crucially, these data streams are never added together. Because each dataset originates from completely different filing types with distinct compliance rules, keeping them separate prevents double-counting and maintains data integrity."

### Step 2 — Pick an issuer

**Do:** Open the issuer dropdown and select **Genco Shipping**. Point to the rows that appear.

**Say:**
> "Selecting a specific issuer immediately aligns the entire profile. Let's look at Genco Shipping. Notice how every table below instantly filters to this selection, pulling in eight distinct 13D/G observations across the original filing and all subsequent amendments."

### Step 3 — Replay how the profile was built

**Do:** Use the **Replay** control and scrub from December 2023 to June 2026.

**Say:**
> "To understand our data's evolution, we use the Replay feature. This reconstructs the profile chronologically based on when the SEC officially accepted each filing — spanning from December 2023 to June 2026. This ensures you only ever see what was factually known at that exact point in time."

### Step 4 — What is asserted, and what is not

**Do:** Point to a verified "safe row", then contrast it with a flagged diagnostic row that has empty value fields.

**Say:**
> "Transparency is vital. Verified 'safe rows' are fully backed by source provenance and confidently asserted. Conversely, any record that fails our strict automated checks remains visible as a diagnostic tool for review, ensuring no unverified values are accidentally claimed."

### Step 5 — 13F institutional holdings

**Do:** Scroll to the **13F Institutional Holdings** table and highlight a chain of amended rows.

**Say:**
> "Moving to institutional positions, the platform tracks reported positions through resolved 13F chains — intelligently capturing amendments and corrections. A position is only officially asserted once its complete historical chain is fully resolved by the engine."

### Step 6 — Evidence for every value

**Do:** Expand an evidence row to show the metadata panel and the SEC link.

**Say:**
> "Every single value on this page is fully auditable. By opening an evidence row, you can view the raw text, the normalized value, source file, selector coordinates, byte ranges, and its unique SHA-256 hash. We also provide a direct link straight to the official SEC filing for manual verification."

### Step 7 — When each fact became known

**Do:** Point to the **SEC Acceptance Time** column.

**Say:**
> "We don't overwrite history. By tracking the exact SEC acceptance time, we log precisely when a fact became market knowledge. Amendments and corrections are preserved as independent events, giving you a flawless audit trail of how information unfolded."

### Step 8 — Kept apart on purpose

**Do:** Point to the group observations section and highlight a record flagged for review.

**Say:**
> "To avoid misleading aggregations, group observations are never blended into an individual's total ownership. If a record requires an analyst's eye, it explicitly lists the reasons and required next steps, keeping unverified figures safe from exposure."

### Step 9 — The boundary of the claim

**Do:** Scroll to the scope / disclaimer banner at the bottom.

**Say:**
> "Finally, we believe in defining our guardrails. This view is a bounded pilot, not a global, SEC-wide dataset or a declaration of absolute ownership. The platform states these boundaries outright, leaving no room for assumptions."
