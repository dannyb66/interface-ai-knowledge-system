"""Bind each written term to its local product noun and flags."""
from . import lexicon as lx
from .normalize import number_word


def mentions(toks, hits, default, segment):
    terms, consumed = [], set()
    units = {"month", "months", "mo", "mos", "year", "years", "yr", "yrs"}
    for i, token in enumerate(toks):
        if i in consumed:
            continue
        number = int(token) if token.isdigit() and len(token) <= 3 else number_word(token)
        if number is None:
            continue
        end = i + 1
        if number in range(20, 100, 10) and end + 1 < len(toks) and toks[end + 1] in units:
            ones = number_word(toks[end])
            if ones is not None and 0 < ones < 10:
                number += ones
                consumed.add(end)
                end += 1
        if end < len(toks) and toks[end] in ("and", "or") and end + 2 < len(toks):
            end += 2
        if end < len(toks) and toks[end] in units:
            terms.append((i, number * (12 if toks[end].startswith("y") else 1)))
    if len(terms) < 2:
        return ()
    nouns = [(start, kind, target) for start, _, (kind, target) in hits if kind in lx.PRODUCT_KINDS]
    out = []
    for index, (start, term) in enumerate(terms):
        end = terms[index + 1][0] if index + 1 < len(terms) else len(toks)
        local = set(toks[start:end])
        noun = next((n for n in nouns if n[0] > start), nouns[-1] if nouns else None)
        pid = default
        if noun:
            _, kind, target = noun
            pid = lx.FAMILY_IDS[target][segment == "business"] if kind == "family" else target
        if pid in ("cert_regular", "business_cert_regular") and ("special" in local or "specials" in local or default in ("cert_special", "business_cert_special")):
            pid = "business_cert_special" if segment == "business" else "cert_special"
        item = {"product_id": pid, "term_months": term}
        if pid in lx.MORTGAGE_IDS:
            local_tokens = toks[start:end]
            unpriced = next((name for name, phrase in lx.UNPRICED_PROGRAMS
                             if any(tuple(local_tokens[j:j + len(phrase)]) == phrase for j in range(len(local_tokens)))), None)
            if "arm" in local:
                unpriced = "arm"
            if unpriced:
                item["program"] = unpriced
        for flag in ("jumbo", "special"):
            if flag in local or flag + "s" in local:
                item[flag] = True
        if "regular" in local:
            item["special"] = False
        out.append(tuple(sorted(item.items())))
    return tuple(out)
