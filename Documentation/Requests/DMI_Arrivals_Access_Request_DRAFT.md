# DRAFT — Request for documented access to daily market arrivals data (AGMARKNET)

**Status:** draft for the project owner's review. **Not sent.** Placeholders in `[brackets]` must be completed by the sender; nothing in them has been assumed.
**Prepared:** 2026-10-24; revised 2026-10-24 (questions 9–10, sender checklist) · **Related:** `Documentation/Data_Source_Review.md` §5.2, §8.4, §8.10, §9

---

**To:** The Director, Directorate of Marketing and Inspection (DMI), Ministry of Agriculture and Farmers Welfare, Government of India
**Cc:** [AGMARKNET technical contact, if known] · [course supervisor]
**From:** [sender name(s)], [programme / course code], [institution]
**Subject:** Request for documented research access to daily market-level arrivals data on AGMARKNET

Respected Sir/Madam,

We are [student(s)] at [institution], working on a [course / research] project under the supervision of [supervisor name, designation]. The project studies weekly wholesale price behaviour for Onion, Potato and Wheat in Indian agricultural markets, for educational and non-commercial research purposes. It does not provide trading advice and has no commercial use.

**What we already use, and how.** Daily variety-wise prices are obtained through the documented Open Government Data API at data.gov.in (resource "Variety-wise Daily Market Prices Data of Commodity"), with a registered API key and attribution. That resource does not include arrival quantities. Our historical arrivals series ends on 2 February 2024.

**What we are requesting.** Documented, permitted access to **daily market-level arrival quantities** for Onion, Potato and Wheat, ideally from 1 January 2021 (or the earliest available date) to the present. We have observed that the AGMARKNET 2.0 portal displays price and arrival reports. We have **not** used its internal interfaces for bulk retrieval, because we could not find published terms or documentation for them.

**Questions on which we would be grateful for guidance:**
1. **Access method:** is there a documented API, bulk download or data-request procedure for daily arrivals? Is registration or a key required, and are there rate limits?
2. **Licence and permitted use:** under what licence or terms may the data be used for non-commercial research? Are we permitted to retain the data, cite it, and publish aggregate results and derived statistics? What attribution wording is required?
3. **Coverage:** from what date are market-level arrivals available for each commodity? Are there known gaps, for example around the AGMARKNET 2.0 launch (November 2025)?
4. **Units and definitions:** the unit of arrival quantity (tonnes or quintals), and whether arrivals are reported per market and day, per variety, or per grade. Our reading of the portal note is that arrivals are shown "at the commodity level"; is that correct?
5. **Commodity definitions:** how Onion, Potato and Wheat arrivals relate to the varieties and grades reported for prices.
6. **Market identifiers:** whether stable market identifiers are available, and whether a crosswalk exists between pre-2.0 market codes and AGMARKNET 2.0 market identifiers (several markets were renamed, for example "<name> APMC", and some moved to newly created districts).
7. **Update frequency and revisions:** how often arrivals are updated, whether past values are revised, and whether revision dates are recorded.
8. **Data quality notes:** any documented guidance on placeholder or provisional entries, for example very small quantities such as 0.01 t.
9. **Format and schema:** the file format, field definitions (including date convention and missing-value codes) and, if possible, a small sample extract, so that we can validate the data before any use.
10. **Earlier years:** whether market-level arrivals before 2021 are also available through the same documented channel. Our existing series covers 2001 to February 2024, and an overlap would let us check units and definitions consistently.

**Our commitments if access is granted:**
- use only for the stated non-commercial educational and research purpose;
- follow the licence, attribution and rate limits you specify;
- not redistribute raw data beyond what the terms permit;
- record provenance (retrieval date, request parameters, file hashes) for every download;
- share a copy of any report or publication with DMI on request.

Thank you for considering this request. We would be glad to provide any further information.

Yours faithfully,
[name(s)]
[programme, institution]
[email address] · [phone, optional]
[supervisor name and email]

---

## Checklist for the authorised sender (complete before submission)

- [ ] The project owner approves sending, and the supervisor agrees to be named and copied.
- [ ] Every `[bracketed]` field is filled with real, verifiable details: sender name(s), programme or course code, institution, supervisor name, designation and email, contact email. Nothing is left as a placeholder or invented.
- [ ] Confirm the stated purpose is accurate: non-commercial, educational or research; no trading advice; no commercial use.
- [ ] Confirm the current DMI or AGMARKNET contact address from the official sites (dmi.gov.in, agmarknet.gov.in). Use an official channel, not a guessed address.
- [ ] Use the project's or institution's email account, not a personal throwaway address. Keep a copy of the sent message and any reply in the project records.
- [ ] Attach nothing that contains API keys, credentials or downloaded raw data.
- [ ] Record the submission date and any reference number in `Data_Source_Review.md` §8.10 / §9.

## Internal notes (not part of the letter)

- **Do not send** without the owner's approval and the supervisor's agreement.
- **Do not use** the undocumented `api.agmarknet.gov.in/v1/daily-price-arrival/*` endpoints for bulk retrieval while this request is pending (§8.4).

**After lawful access, before any use (Phase 9 rules, reused unchanged where applicable):**
1. **Provenance:** keep raw responses unchanged, with retrieval date, parameters and SHA-256 per file. Keep them in a new `Dataset_Candidates/` folder, separate from the old arrivals.
2. **Units:** confirm tonnes against quintals from the documentation, and against the overlap with the existing 2021-01-01 → 2024-02-02 arrivals (identical markets and dates; paired comparison, never assumed).
3. **AQ-1 v1 rules** (`Code/modelling/arrivals_quality.py`, `arrivals_aq1.py`):
   - classes `ok` / `isolated_spike` / `sustained_shift` / `likely_unit_error` / `likely_unit_error_low` / `likely_unit_error_forward_only`;
   - tiny-value and unit-factor signatures;
   - the Madhya Pradesh 2019–2020 placeholder pattern (0.01 / 0.02 / 0.05 / 0.1 t);
   - the Wheat March–May review variants.
   Flags live in a separate versioned table. A flag is used at a refit only if `aq1_available_from` ≤ the refit, and origin inputs stay on the unflagged view.
4. **Duplicates:** exact and conflicting duplicates per market × date × commodity, using the candidate R03 / type-variant logic; conflicts are never averaged.
5. **Identity:** join by market identifier where provided; otherwise only through approved `candidate-market-map-v1` identities and exact dates; never by price similarity.
6. **Grain:** if arrivals are commodity-level only, features are market × crop × week sums, never assigned to varieties or grades.
