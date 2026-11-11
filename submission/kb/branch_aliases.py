"""Branch aliases grounded by the branch addresses and article headings."""
import re

ALIASES = ((r"\be\.? washington\b", "east washington"),
           (r"\bedgewood(?: road| rd\.?)?\b", "cedar rapids"),
           (r"\bkey west\b", "flint hill"),
           (r"\bdubuque hy-vee\b", "hy-vee"))


def branch_aliases(text):
    for pattern, name in ALIASES:
        text = re.sub(pattern, name, text)
    return text
