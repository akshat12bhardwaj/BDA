"""
Reusable, transparent crop-name normalization and matching utilities.

Phase 1 found that exact-string crop-name matching under-counts true overlap
between the mandi filenames, the APY `crop_name` column, and the Agri Market
`Commodity` column (e.g. "Arhar (Tur-Red Gram)(Whole)" vs
"Arhar (Tur/Red Gram)(Whole)"). This module implements a deterministic,
explainable normalization + token-overlap matching process instead of
opaque fuzzy-string matching, plus a small, explicitly documented manual
alias table for domain-knowledge cases the automatic process cannot safely
resolve on its own (e.g. Rice vs Paddy, which are related but distinct
commodities and must never be silently merged).
"""

from __future__ import annotations

import re

# Tokens that carry no discriminating information about which crop is meant
# (processing state / descriptive filler words), excluded from token-overlap
# comparison so e.g. "Cashewnut Raw" and "Cashewnut Processed" still share
# their meaningful anchor token "cashewnut".
STOPWORDS = {
    "whole", "raw", "dry", "green", "other", "local", "processed", "seed",
    "seeds", "oil", "dal", "split", "the", "and", "of", "loose", "cut", "veg",
    "vegetable",
    # Generic crop-category words that cause false positive matches between
    # unrelated crops if used alone as the "shared token" (e.g. "gram" alone
    # would otherwise match "Alasande Gram" to "Moong(Green Gram)").
    "gram", "pea", "peas", "bean", "beans", "pulses", "nut", "nuts", "fruit",
    "fruits", "melon",
}

# Explicit, justified aliases for cases where automatic normalization/token
# overlap either fails or would be unsafe to infer automatically. Each entry
# records WHY the alias is or is not applied — see crop_matching_notes().
MANUAL_ALIAS_NOTES = {
    ("rice", "paddy(dhan)(common)"): (
        "NOT MERGED. APY 'Rice' production statistics conventionally measure "
        "paddy (unmilled) output, so it is agronomically closer to mandi "
        "'Paddy(Dhan)(Common)' than to mandi 'Rice' (a milled market "
        "product). Because Rice and Paddy are traded as distinct commodities "
        "with different prices, they are kept as separate candidates; this "
        "note exists so a future phase does not accidentally conflate them."
    ),
    ("cotton(lint)", "cotton"): (
        "MERGED. 'Lint' is the marketable fibre form of raw cotton; APY "
        "reports cotton production in lint-equivalent terms, so APY "
        "'Cotton(Lint)' is treated as the production counterpart of mandi "
        "'Cotton'."
    ),
    ("jowar", "jowar(sorghum)"): (
        "MERGED. 'Jowar' and 'Sorghum' are the same crop (Hindi/English "
        "names for the same species); the mandi filename simply includes "
        "both names."
    ),
    ("arhar/tur", "arhar (tur-red gram)(whole)"): (
        "MERGED. Same crop; APY uses the short form 'Arhar/Tur', mandi uses "
        "the fully expanded commodity description."
    ),
    ("moong(green gram)", "green gram (moong)(whole)"): (
        "MERGED. Same crop, word order and punctuation differ only."
    ),
    ("rapeseed &mustard", "mustard"): (
        "MERGED. Rapeseed and mustard are reported jointly as one APY crop "
        "category; the mandi 'Mustard' commodity is treated as the "
        "market-side counterpart, acknowledging APY's figure may include "
        "some rapeseed volume."
    ),
    ("bhindi", "bhindi(ladies finger)"): (
        "MERGED. Same crop (okra); mandi filename adds the English synonym."
    ),
    ("gram", "bengal gram(gram)(whole)"): (
        "MERGED WITH CAUTION. APY 'Gram' most commonly refers to Bengal "
        "gram/chickpea in Indian agricultural statistics; treated as "
        "equivalent to mandi 'Bengal Gram(Gram)(Whole)', but this is a "
        "judgment call, not a certainty, and is flagged for review if this "
        "crop is shortlisted."
    ),
    ("cowpea(lobia)", "cowpea (lobia-karamani)"): (
        "MERGED. Same crop, punctuation/formatting differs only."
    ),
}


def normalize(name: str) -> str:
    """Deterministic normalization: lowercase, strip descriptive punctuation, collapse spaces."""
    s = name.strip().lower()
    s = re.sub(r"[\(\)/,&\-\.]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(norm_name: str) -> set[str]:
    """Meaningful tokens (length >= 3, stopwords removed) for overlap comparison."""
    return {t for t in norm_name.split() if len(t) >= 3 and t not in STOPWORDS}


def match_status(mandi_name: str, other_name: str) -> tuple[str, str]:
    """
    Compare one mandi crop name against one APY/Agri-Market crop name.
    Returns (status, method) where status in
    {"exact", "token_overlap", "no_match"}.
    """
    m_norm, o_norm = normalize(mandi_name), normalize(other_name)
    if m_norm == o_norm:
        return "exact", "normalized string equality"

    m_tok, o_tok = tokens(m_norm), tokens(o_norm)
    if m_tok and o_tok and (m_tok & o_tok):
        shared = ", ".join(sorted(m_tok & o_tok))
        return "token_overlap", f"shared token(s): {shared}"

    return "no_match", "no normalized or token overlap"
