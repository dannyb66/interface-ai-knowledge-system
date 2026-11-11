# Answer-formatting contract

Copied verbatim from `docs/research/03-scoring-levers.md`, section 3.

1. **Lead with the single current value, unit attached, qualifier beside it**: "5.39% APR (60-month, 2024–2027 model years)". Rates always carry "%"; dollar amounts carry "$"; thousands with commas.
2. **Never mention any other number than the ones the question needs**: no superseded values, no other tiers, no "was/now", no "not X", no effective dates, no years, no phone numbers, no page-generation dates. Add the second tier only when the eval expects both (dup-009 expects 7.13 and 7.25).
3. **Never mention other products** in a product question (no "Jump Start", "Share Savings" in a loan answer).
4. **List questions enumerate every required item** with its value in one sentence or bullets; never ask which item the member wants (dup-005, dup-040), never say "in these facts".
5. **Hours/dates/addresses reproduce the site's literal formats**: "8:30 a.m.", "8 a.m.–6 p.m." (space before a.m./p.m., no "8am", no "8:00 a.m."), "12:30 p.m.", "noon", "March 31, 2026" (US long date), "11375 Oldenburg Lane, Galena, IL 61036", phone "800-373-7600" hyphenated. Include both "12:30" and "noon" when schedules differ.
6. **Branch questions answer directly**: give the typical schedule and say "ask which branch"; never request a ZIP code or city first.
7. **URL questions put the full URL in the text**; sources alone do not satisfy must_include.
8. **Refusal**: `confident=False` plus one regex phrase ("isn't listed", "I can't confirm", "please contact a Dupaco …"), no digits unless they appear in the question, no trap phrases ("unable to find", "don't have that detail").
9. **Set confident=False** when the fact is absent from every snapshot or found only in a page type the rules reject; never on an item where a value is being stated (harmless to the scorer, but keep it meaningful for the judge).
10. **sources**: one to three canonical page URLs of the winning fact, normal `https://www.dupaco.com/<path>` form without `#fragment` or `?query`; include the rate-sheet page and the product page when both exist. **conflict_note**: free text, unscored; write it only when the system actually resolved a disagreement.
11. **as_of**: when given, answer from the latest snapshot ≤ as_of and phrase "As of May 2026 … 3.90% APY" without quoting the later value.
12. **Determinism**: canonicalise the question, cache answers, and generate every paraphrase from the same fact record so number sets are identical.

Worked examples (full credit vs zero):

| id | full credit | zero credit |
|---|---|---|
| dup-016 | "5.39% APR for a 60-month auto loan on a 2024–2027 model-year vehicle." src auto-loans page | "Rate was 5.34%, now 5.39% APR." (trap) |
| dup-009 | "30-year fixed: 7.13% rate for loans up to $100,000, up to 7.25% for larger loans." src home-loans | "7.13% (6.037% last quarter)." |
| dup-045 | "0.15% APY on Share Savings balances of $10,000–$24,999.99." | "0.15%; the $25,000+ tier pays 0.20% and the sheet shows 0.30%/0.40% elsewhere." (0.30% trap) |
| dup-054 | "Dupaco's routing number is 273974581." src cash-management | "Routing number: 2739***** (masked)" (`***` trap) |
| dup-073 | "Dupaco has 22 branch offices." | "22 branches now; older pages say 24 branch locations." |
| dup-087 | "Forbes has named Dupaco a Best-in-State credit union for the fifth time." | "…fifth time (2021); fourth in 2020." |
| dup-065 | "Most lobbies are open Mon–Thu 8:30 a.m.–5 p.m., Fri 8:30 a.m.–6 p.m., Sat 8:30 a.m.–12:30 p.m.; ask which branch." | "Please share your ZIP code so I can look up hours." |
| dup-034 | "Platinum Visa 12.50%–19.50% APR; Rewards Visa 15.50%–21.00% APR; Business Platinum Visa 15.50% APR; Business Rewards Visa 20.50% APR." src credit-cards | "Platinum Visa 12.5%, intro 9.9% balance transfer." (trap + incomplete) |
| dup-145 | confident=False, "Dupaco's website does not list a 7/1 ARM rate; it isn't listed. Please contact a mortgage lender." | "I don't know, but the 30-year fixed is 7.13%." |
| dup-006 (as_of 2026-05-31) | "As of May 2026 the 10-month fixed jumbo certificate special paid 3.90% APY." | "3.90% APY, since raised to 4.00%." |
