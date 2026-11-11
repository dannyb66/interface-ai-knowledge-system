"""Keep requested fee operations and wire direction attached to the matched schedule row."""
from __future__ import annotations

import re

WIRE_PRODUCTS = frozenset({"incoming_wire_fee", "domestic_wire_fee", "international_wire_fee"})
# These describe distinct services, not how much the named schedule row costs.
OPERATIONS = frozenset({"recall", "recalled", "recalling", "cancel", "cancelled", "canceled", "cancelling",
    "canceling", "cancellation", "cancellations", "replace", "replacement", "replacing", "reissue", "reissued",
    "reissuance", "refund", "refunded", "refunds", "return", "returned", "reversal", "reverse", "amend",
    "amendment", "trace", "tracing", "investigation", "investigate", "lost", "stolen"})
INCOMING = frozenset({"incoming", "receive", "received", "receiving", "inbound"})
OUTGOING = frozenset({"outgoing", "send", "sending", "sent", "outbound"})


def fee_products(products, words, registry):
    """Return supported fee rows or an empty list when the requested operation is unlisted.

    An operation word remains supported when the selected row explicitly names it (e.g.
    re-keying a box due to a lost key). Incoming direction precedes domestic/international
    origin, while contradictory incoming/outgoing wording conservatively refuses.
    """
    selected = [p for p in products if registry.family(p) == "fees"]
    if not selected:
        return selected
    for pid in selected:
        stated = set(re.findall(r"[a-z]+", registry.display_name(pid).lower()))
        if (words & OPERATIONS) - stated:
            return []
    if WIRE_PRODUCTS & set(selected) and words & INCOMING:
        return [] if words & OUTGOING else ["incoming_wire_fee"]
    return selected
