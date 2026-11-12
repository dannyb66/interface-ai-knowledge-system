"""The question canonicaliser's slot, superlative, url-cue, keyword-intent and attribute helpers (``question.py``).

``question.parse`` calls ``keyword_intent``, ``slots`` and ``attribute`` and shares ``seq`` and the ``Hit`` alias;
its module docstring holds the contract they implement. They read word tokens and the ``norm_text`` question through
the ``lexicon`` vocabulary and the ``normalize`` question readers; ``normalize`` never imports this module.
"""
from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from . import lexicon as lx
from .normalize import bare_branch, branch_name, model_year_range, passive_used_to, question_amount, year_back
from .conditions import query_conditions
from .prose_questions import information_attribute, information_intent, serving_cutoff

__all__ = ["Hit", "asks_opening", "attribute", "keyword_intent", "seq", "slots", "superlative", "url_cue"]

Hit = Tuple[str, str]


def year_slot(text: str) -> Optional[int]:
    """An explicit count year, excluding years inside full question date mentions."""
    for pattern in (lx.NUM_DATE_RE, lx.YEAR_MONTH_RE, lx.MONTH_RE):
        text = pattern.sub(lambda match: " " * len(match.group()), text)
    match = re.search(r"\b(?:in|during|for|of)\s+((?:19|20)\d{2})\b", text)
    return int(match.group(1)) if match else None


def fix_typo(token: str, words: Mapping[str, str]) -> str:
    """Correct one deletion, insertion, substitution or transposition only when unique."""
    if token in words or len(token) < 4:
        return token
    deleted = {token[:i] + token[i + 1:] for i in range(len(token))}
    candidates = []
    for word in words:
        if len(word) < 5 or abs(len(word) - len(token)) > 1:
            continue
        drops = {word[:i] + word[i + 1:] for i in range(len(word))}
        mismatches = [i for i, (a, b) in enumerate(zip(word, token)) if a != b]
        same_length = len(word) == len(token) and (len(mismatches) == 1 or len(mismatches) == 2
            and mismatches[1] == mismatches[0] + 1 and word[mismatches[0]:mismatches[1] + 1] == token[mismatches[0]:mismatches[1] + 1][::-1])
        if word in deleted or token in drops or same_length:
            candidates.append(word)
    return candidates[0] if len(candidates) == 1 else token


def lexicon_words(value):
    """Every syntax word, including nested phrase tuples, is protected from product-name typo repair."""
    if isinstance(value, str):
        return set(re.findall(r"[a-z]+", value.lower()))
    if isinstance(value, dict):
        return set().union(*(lexicon_words(v) for v in list(value) + list(value.values())))
    if isinstance(value, (tuple, list, set, frozenset)):
        return set().union(*(lexicon_words(v) for v in value))
    return set()


def seq(toks: Sequence[str], *seqs: Tuple[str, ...]) -> bool:
    """Whether any of ``seqs`` occurs in ``toks`` as consecutive tokens."""
    return any(tuple(toks[i:i + len(q)]) == q for q in seqs for i in range(len(toks) - len(q) + 1))


def url_cue(toks: Sequence[str], words: FrozenSet[str], rated: bool,
            possessive: FrozenSet[int] = frozenset(), branded: FrozenSet[int] = frozenset()) -> bool:
    """A url question by the rules at ``lexicon.URL_WORDS``; ``rated``: the question has an explicit rate word;
    ``possessive``: the indices of the words written with a possessive 's, which name a source and claim no url;
    ``branded``: the indices of the words right after a skipped brand word ("on Dupaco's site" is no bare "on site")."""
    if seq(toks, ("which", "page"), ("what", "page")) or (seq(toks, ("where", "can", "i", "see")) and "online" in words):
        return True
    def before(i: int) -> int:  # the index of the first word before ``i`` that is no URL_FILLER word, else -1
        j = i - 1
        while j >= 0 and toks[j] in lx.URL_FILLER:
            j -= 1
        return j
    def word(i: int) -> str:
        return toks[i] if 0 <= i < len(toks) else ""
    def bare_page(i: int) -> bool:  # "On the rates page, ...": a url noun only when asked or "page that ..." (SE2)
        return toks[i] in ("page", "pages") and word(i - 1) != "web"
    def source(i: int) -> bool:  # "the website's rate", "the web page's APR": the noun at ``i`` ends possessive
        return i in possessive or (tuple(toks[i:i + 2]) in lx.URL_SEQS and i + 1 in possessive)
    def where_on(i: int) -> bool:  # "Where('s) ... on the website('s) ...?" (F4); a bare "on site" is a place (F3)
        return word(before(i)) == "on" and ("where" in words or "wheres" in words) and not (
            toks[i] in ("site", "sites") and word(i - 1) == "on" and i not in branded)
    nouns = [i for i, t in enumerate(toks) if (t in lx.URL_WORDS or tuple(toks[i:i + 2]) in lx.URL_SEQS) and not (
        source(i) or (bare_page(i) and word(before(i)) not in lx.URL_ASKERS and word(i + 1) not in lx.PAGE_FOLLOWERS))]
    if any(t in lx.SITE_WORDS and (where_on(i) or not source(i) and ((
            word(before(i)) in lx.URL_ASKERS and word(i + 1) in lx.SITE_ASKED_NEXT) or (
            word(before(i)) in ("what", "which") and word(i + 1) in lx.SITE_VERBS)))
           for i, t in enumerate(toks)) or any(word(before(i)) in lx.URL_ASKERS for i in nouns):
        return True  # "Where on the website ...?", "What website has ...?" (SE3), "Which page ...?", "Give me the link"
    return bool(nouns) and not (words & lx.SAY_VERBS and (rated or words & {"phone", "telephone"}))


def asks_opening(toks: Sequence[str], words: FrozenSet[str], ctx: bool) -> bool:
    """An opening-hours question with no hours word (Task 12 review, I2): "when" and a present-tense asking verb
    (``lexicon.OPEN_ASKERS``), then "open" with no object after it, asked of a branch, "you" or Dupaco (``ctx``: branch
    context or a brand word): "When are your branches open?", "When does Dupaco open?"; "When can I come in?" at the
    end or beside branch context; or "open" beside "same time(s)" ("Do all branches open and close at the same
    time?"). Never "when ... close", which asks a closure date ("When does the Hy-Vee branch close?": status)."""
    at = next((i for i, t in enumerate(toks) if t in ("when", "whens")), len(toks))
    verb = "is" if toks[at:at + 1] == ["whens"] else " ".join(toks[at + 1:at + 2])  # "When's" reads "when is"
    if verb in lx.OPEN_ASKERS and (ctx or "you" in words) and any(
            toks[i] == "open" and " ".join(toks[i + 1:i + 2]) not in lx.OPEN_OBJECTS for i in range(at + 1, len(toks))):
        return True
    come = seq(toks, ("when", "can", "i", "come", "in")) and (ctx or toks[-1] == "in")
    return come or ("open" in words and seq(toks, ("same", "time"), ("same", "times")))


def keyword_intent(toks: Sequence[str], words: FrozenSet[str], dates: Sequence[str], branch_ctx: bool,
                   quiet: FrozenSet[int] = frozenset(), rated: bool = False,
                   possessive: FrozenSet[int] = frozenset(), branded: FrozenSet[int] = frozenset(),
                   named: bool = False) -> str:
    """The keyword intent, else ``""``; ``named``: a bare branch name in a question with no product word ("Is Hy-Vee
    still open?"), which is branch context for the status cue alone (Task 13), never for hours, address or count."""
    ctoks = ["" if i in quiet else t for i, t in enumerate(toks)]  # "before it changed" is no change cue
    cue = any(t in lx.CHANGE_WORDS and (i == 0 or ctoks[i - 1] not in lx.MODALS) for i, t in enumerate(ctoks))
    if "happens" in words and not rated and not words & (lx.CHANGE_WORDS - {"happens"}):
        cue = False  # present process wording is not a historical change
    if len(set(dates)) > 1 or not seq(ctoks, *lx.CHANGE_BLOCK) and (
            cue or seq(ctoks, *lx.UPDOWN) or (dates and words & lx.COMPARE_WORDS)):
        return "change"
    if words & {"routing", "aba"}:
        return "routing"
    if url_cue(toks, words, rated, possessive, branded):
        return "url"
    if (seq(toks, ("how", "many")) and "points" not in words) or (seq(toks, ("number", "of")) and not words & lx.NUMBER_NOUNS):
        return "count"
    if (words & {"update", "updating"} or seq(toks, ("change", "my"))) and words & lx.UPDATE_WHAT:
        return "phone"  # updating the member's own details goes to the contact route (controller ruling, dup-060)
    address_words = words & lx.ADDRESS_WORDS
    if "address" in address_words and any(t == "address" and i and (
            toks[i - 1] == "to" or (set(toks[max(0, i - 4):i]) & {"can", "could", "may", "might", "will", "would"}
            and not set(toks[max(0, i - 4):i]) & {"give", "show", "tell", "find", "confirm", "provide", "verify"}))
            for i, t in enumerate(toks)):
        address_words = address_words - {"address"}  # address a problem is a verb, not a postal location
    if (address_words and "email" not in words) or "wheres" in words or (
            branch_ctx and seq(toks, ("where", "is"), ("where", "are"))):
        return "address"
    lobby = bool(words & lx.LOBBY_WORDS) or seq(toks, *lx.DRIVE_SEQS)  # beside a phone word it asks the phone
    if words & {"fax", "email"} and not words & lx.REPLY_WORDS:
        return ""
    lost_device = bool(words & {"lost", "stolen", "losing"}) and bool(words & {"wallet", "device", "phone"})
    procedure = seq(toks, *lx.HOWTO_SEQS) or seq(toks, ("what", "should", "i", "do"), ("what", "do", "i", "do"))
    if lost_device and procedure and not words & {"call", "contact", "number", "telephone"}:
        return "how_to"
    if words & lx.PHONE_WORDS and not words & (lx.HOURS_WORDS | lx.REPLY_WORDS):
        return "phone"
    if (words & lx.HOURS_WORDS or (lobby and not words & lx.PHONE_WORDS) or words & lx.REPLY_WORDS
            or seq(toks, ("what", "time")) or (words & lx.DAY_WORDS and (branch_ctx or words & {"open", "close"}))
            or asks_opening(toks, words, branch_ctx or bool(branded))):
        return "hours"
    if words & lx.PHONE_WORDS:
        return "phone"
    closure = any(t in lx.STATUS_WORDS and tuple(toks[i:i + 2]) not in lx.NOT_STATUS_PAIRS for i, t in enumerate(toks))
    if (branch_ctx or named) and (closure or seq(toks, ("still", "open"))
                                  or ("open" in words and toks[0] in ("is", "are", "was", "were"))):
        return "status"
    return "how_to" if seq(toks, *lx.HOWTO_SEQS) else ""


def superlative(toks: Sequence[str], hits: Sequence[Tuple[int, int, Hit]],
                published: FrozenSet[str]) -> Optional[str]:
    """``highest``/``lowest`` by the controller rulings spelled out at ``lexicon.RATE_SUPERLATIVES``: the one beside
    a rate word wins, else the first counted."""
    kind_at = {j: hit[0] for start, size, hit in hits for j in range(start, start + size)}
    starts = {start: hit for start, _, hit in hits}
    rate_asked = any(kind == "attribute" and target in lx.RATE_ATTRS for _, _, (kind, target) in hits)
    in_phrase = {j for start, size, hit in hits if hit[0] == "attribute" and size > 1
                 for j in range(start, start + size)}  # "least I can deposit to open" names a requirement
    found: List[Tuple[bool, str]] = []  # (beside a rate word, direction) of every counted superlative, in order
    for i, t in enumerate(toks):
        if i in in_phrase or (i > 0 and (toks[i - 1], t) in lx.NOT_SUPERLATIVE_PAIRS):
            continue  # "at least $1,000", "at most $5,000": a bound on an amount
        if t not in lx.RATE_SUPERLATIVES and not (t in lx.OTHER_SUPERLATIVES and (t != "most" or rate_asked)):
            continue
        j = i + 1
        while j < len(toks) and (kind_at.get(j) in lx.PRODUCT_KINDS or toks[j] in lx.SUPERLATIVE_FILLER):
            j += 1  # skip product words and fillers: "highest Share Savings APY", "the cheapest auto loan rate"
        hit = starts.get(j, ("", ""))
        beside_rate = hit[0] == "attribute" and hit[1] in lx.RATE_ATTRS
        if t in lx.RATE_SUPERLATIVES:
            if i > 0 and toks[i - 1].isdigit():
                continue  # "$1,000 minimum": the word qualifies an amount, not the rate
            if t in lx.ADJACENT_SUPERLATIVES:
                if not beside_rate:
                    continue  # "the minimum for a certificate": minimum/maximum need a rate word ("minimum APY")
            elif j < len(toks) and (toks[j] in lx.AMOUNT_NOUNS or toks[j] in lx.NON_RATE_NOUNS
                                    or tuple(toks[j:j + 2]) in lx.NON_RATE_PAIRS):
                continue  # "lowest balance", "highest deposit", "highest credit limit": not the rate
            elif t == "top" and toks[i + 1:i + 2] == ["of"]:
                continue  # "top of the range": not a superlative
            direction = lx.RATE_SUPERLATIVES[t]
        else:
            direction = lx.OTHER_SUPERLATIVES[t]  # counts wherever it stands; beside a rate word it can win
        if direction == "best":
            direction = "lowest" if published & {"apr", "rate"} and "apy" not in published else "highest"  # best loan
        found.append((beside_rate, direction))
    # the word beside the rate wins ("the highest credit score ... the lowest APR"), else the first counted
    return next((direction for beside_rate, direction in found if beside_rate), found[0][1] if found else None)


def slots(s: str, toks: Sequence[str], words: FrozenSet[str], pid: Optional[str], published: FrozenSet[str],
          hits: Sequence[Tuple[int, int, Hit]], segment: str, arm: bool, term: Optional[Tuple[int, bool, bool]],
          named_branch: bool) -> Dict[str, Any]:
    slots: Dict[str, Any] = {"segment": segment, "superlative": superlative(toks, hits, published)}
    if "fee" in published:
        slots.update(query_conditions(s))
    slots["term_months"] = term[0] if term else None
    slots["amount"] = question_amount(s)
    vehicle_years = [i for i, t in enumerate(toks) if len(t) == 4 and t.isdigit() and 1980 <= int(t) <= 2099 and (
        " ".join(toks[i + 1:i + 2]) in lx.VEHICLE_WORDS or " ".join(toks[max(0, i - 2):i]) == "model year")]
    slots["model_year"] = int(toks[vehicle_years[0]]) if vehicle_years else None  # "2026 car", "model year 2026"
    slots["model_year_range"] = model_year_range(toks, vehicle_years[0]) if vehicle_years else None  # "2024-2027" (N2)
    slots["latest_model_year"] = True if seq(toks, ("newest", "model", "year"), ("latest", "model", "year"),
                                             ("newest", "model", "years"), ("latest", "model", "years")) else None
    slots["year_back"] = True if year_back(toks) else None  # "in the previous year": the resolver dates it (N4)
    unpriced = "arm" if arm else next((name for name, phrase in lx.UNPRICED_PROGRAMS if seq(toks, phrase)), None)
    if unpriced and pid in lx.MORTGAGE_IDS:
        slots["program"] = unpriced  # the ARM and the other programs no fact carries refuse (W3)
    elif pid in ("ira_cert", "ira_variable"):
        slots["program"] = next((t for t in toks if t in ("roth", "traditional")), None)
    elif pid in lx.MORTGAGE_IDS:
        slots["program"] = "purchase" if pid == "mortgage_purchase" else "refi"
    if pid in ("cert_special", "business_cert_special") or (pid == "ira_cert" and words & {"special", "specials"}):
        slots["special"] = True
    if "jumbo" in words:  # any product (the resolver's contract): one without jumbo rows refuses
        slots["jumbo"] = True
    if "regular" in words and pid in ("cert_regular", "cert_special", "ira_cert", "business_cert_regular", "business_cert_special"):
        slots["special"] = False
    if lx.AFTER_INTRO_RE.search(s):
        slots["intro"] = False  # "after the intro period": the standard rate (I5)
    elif words & lx.INTRO_WORDS or seq(toks, ("balance", "transfer")):
        slots["intro"] = True
    elif pid in ("platinum_visa", "heloc") and words & {"standard", "ongoing", "regular"}:
        slots["intro"] = False
    if pid == "branch":  # a branch question binds a bare name too: "What are the lobby hours in Waukee?"
        slots["branch_name"] = branch_name(s) or bare_branch(s)
    elif named_branch and pid not in lx.CONTEXT:  # "the savings rate at the Galena branch"
        slots["branch_name"] = branch_name(s)
    if pid == "branch":
        day = next((t for t in toks if t in lx.DAY_WORDS), None)
        slots["day"] = day[:-1] if day and day.endswith("ys") else day
    return {name: value for name, value in slots.items() if value is not None}


def attribute(intent: str, attrs: FrozenSet[str], toks: Sequence[str], words: FrozenSet[str],
              published: FrozenSet[str], slots: Dict[str, Any], reply: bool,
              requirement: Optional[str]) -> Optional[str]:
    if intent in lx.INTENT_ATTRIBUTE:
        if intent == "count" and "count" not in published and published == frozenset({"description"}):
            return "description"
        return lx.INTENT_ATTRIBUTE[intent]
    if intent == "hours":
        if words & lx.OTHER_HOURS_WORDS or seq(toks, *lx.OTHER_HOURS_SEQS):
            return "other_hours"  # holiday, ATM, customer-service hours ...: no fact carries them, so they refuse
        return "reply_hours" if reply else "driveup_hours" if seq(toks, *lx.DRIVE_SEQS) else "lobby_hours"
    if intent == "status":
        if "branch_name" not in slots and "branch" in words and "branches" not in words:
            return "other_hours"
        if "branch_name" not in slots and (not words & lx.STATUS_WORDS or words & lx.CLOSURE_DATE_WORDS
                                          or words & lx.OTHER_HOURS_WORDS or seq(toks, *lx.OTHER_HOURS_SEQS)):
            return "other_hours"  # "Is the branch open today?", "When does the branch close?": no closure asked
        return "closure_date" if words & lx.CLOSURE_DATE_WORDS else "status"
    if intent == "value" and "branch_name" in slots and "alternatives" in published and (
            words & lx.ALTERNATIVE_WORDS or seq(toks, *lx.ALTERNATIVE_SEQS)):
        return "alternatives"  # where a named branch's members can go instead (Task 13); a financial product never
    if seq(toks, ("how", "long")) and words & lx.INTRO_WORDS:
        return "intro_term"  # how long an intro rate lasts: no fact carries it (W4)
    chosen = requirement or ("url" if "url" in attrs else next((a for a in lx.ATTR_PRIORITY if a in attrs), None))
    chosen = information_attribute(chosen, attrs, toks, words, published, slots)
    if chosen is None and "eligibility" in published and "who" in words and words & {"join", "qualifies", "apply", "eligible"}:
        chosen = "eligibility"
    if chosen is None and "eligibility" in published and (
            words & {"who", "which"} and words & {"use", "access", "participate"}
            or words & {"must", "require", "requires", "required", "need"} and words & {"membership", "member"}):
        chosen = "eligibility"
    if chosen is None and published == frozenset({"fee"}) and intent in ("value", "yes_no"):
        chosen = "fee"
    if chosen == "earning_rate" and "apy" in published:
        chosen = "rate"  # a deposit's earning rate is its APY
    opening = bool(words & lx.REQUIRE_VERBS) and seq(toks, ("to", "open"))  # "What is required to open ...?"
    purpose = (any(passive_used_to(toks, i) for i in range(len(toks)))
               or bool(words & {"purpose", "purposeful", "designed", "intended", "suitable", "goals", "benefits"})
               or seq(toks, ("how", "does"), ("how", "do"), ("what", "does", "it", "do")))
    if chosen is None:
        if words & {"routing", "aba"}:  # "Has the routing number changed?"
            chosen = "routing_number"
        elif intent == "how_to" and "online" in words:
            chosen = "url"
        elif published & lx.RATE_ATTRS and not purpose and (
                intent == "change" or slots.get("program") == "arm" or words & lx.RATE_VERBS or seq(toks, ("how", "much"))
                or any(k in slots for k in lx.TIER_SLOTS) or (not opening and (
                    intent == "list" or (intent == "value" and words & lx.OFFER_WORDS)))):
            chosen = "rate"  # with no attribute word a list, or a value question with an offer word, asks the rate
        elif "description" in published:
            chosen = "description"
    if chosen == "rate":  # the product's published rate column; unpublished stays "rate" for the resolver to refuse
        chosen = next((a for a in ("rate", "apy", "apr") if a in published), "rate")
    return chosen
