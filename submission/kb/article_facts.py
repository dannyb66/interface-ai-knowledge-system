"""Auditable branch contact and count extraction from dated article bodies (Plan A 11b/15)."""
import re

from .types import ClaimType, Fact, make_key

PHONE = re.compile(r"(?i)\bphone number (?:for the (?:[\w.'-]+ )*?(?:branch|learning lab) )?is (?P<phone>\(\d{3}\) \d{3}-\d{4})")
ADDRESS = re.compile(r"(?i)\bbranch is located at (?P<address>.+?),? and the phone number\b")
COUNTS = re.compile(r"(?i)\bit has (?P<emp>(?:more than |over |nearly |about )?[\d,]+) employees and (?P<br>[\d,]+) branch office locations\b")
COUNTIES = re.compile(r"(?i)\bserves residents in (?P<n>[\d,]+) counties throughout (?P<where>[^.]+)")
OPERATES = re.compile(r"(?i)\bnow operates (?P<n>[\d,]+) branches\b")
YEAR = re.compile(r"(?i)^in (?P<y>(?:19|20)\d{2}) alone:?$")
VTO = re.compile(r"(?i)(?P<n>[\d,]+) Dupaco employees used (?:a |a new )?paid benefit in (?P<y>\d{4}) called Volunteer Time Off")
HOURS = re.compile(r"(?i)volunteered (?:a total of )?(?P<n>[\d,]+) hours")


def fact(ctx, pid, attr, text, published, index, quote, qualifiers=None, value=None):
    key = make_key(pid, attr, qualifiers or {})
    return Fact(key, pid, attr, key[2], value, text, "count" if attr == "count" else "text",
                ClaimType.ASSERTION, None, None, published, ctx.source(-1, index, quote), "prose", 1.0)


def branch_contacts(lines, body, ctx, published, branch):
    if not branch:
        return []
    out = []
    for i in range(body[0], body[1] + 1):
        for attr, regex, name in (("phone", PHONE, "phone"), ("address", ADDRESS, "address")):
            m = regex.search(lines[i])
            if m:
                out.append(fact(ctx, "branch", attr, m.group(name).rstrip(","), published, i, lines[i],
                                {"branch_name": branch}))
    return out


def counts(lines, blocks, body, ctx, published):
    out, year = [], None
    tail = {i for block in blocks if block.kind == "about_tail" for i in range(block.start_line - 1, block.end_line)}
    for i in range(body[0], body[1] + 1):
        text = " ".join(lines[i].replace("**", "").replace("__", "").split())
        m = COUNTS.search(text) if i in tail else None
        entries = []
        if m:
            entries += [("employee_count", m["emp"] + " employees", None),
                        ("branch_count", m["br"] + " branch office locations", None)]
        m = COUNTIES.search(text) if i in tail else None
        if m:
            entries.append(("county_count", m["n"] + " counties throughout " + m["where"], None))
        m = OPERATES.search(text)
        if m:
            entries.append(("branch_count", m["n"] + " branches", None))
        if ctx.page_type == "newsroom":
            m = YEAR.match(text)
            if m:
                year = int(m["y"])
            m = VTO.search(text)
            if m:
                entries.append(("vto_users", m["n"] + " Dupaco employees", int(m["y"])))
            m = HOURS.search(text)
            if m and year:
                entries.append(("volunteer_hours", m["n"] + " hours", year))
        for pid, value, scoped in entries:
            number = int(re.search(r"[\d,]+", value).group().replace(",", ""))
            out.append(fact(ctx, pid, "count", value, published, i, lines[i],
                            {"year": scoped} if scoped else {}, number))
    return out
