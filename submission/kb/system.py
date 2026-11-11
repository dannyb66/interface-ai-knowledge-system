"""The facade the harness talks to: ``ingest`` builds the fact store, ``answer`` reads it, ``explain`` shows the work.

``ingest(snapshot)`` reads every page of one crawl. A page whose raw URL has the shape of an old copy
(``pagetype.legacy_shaped``: a trailing slash, ``/YYYY/MM/``, ``dupacodaily``) and that near-duplicates a canonical
page of the same crawl (``is_legacy_alias``) is typed ``legacy_alias`` and cited by that page's URL; any other page is
typed by ``classify``. ``extract_page`` splits the page into blocks and reads its facts. A page without a url or
markdown, with a url ``urlsplit`` rejects, or one the extractor fails on, is skipped and counted. The facts go into the
store once per crawl (a crawl id seen before is skipped), the store is finalised even when adding fails, the answer
cache is emptied and one warm-up answer builds the lazy tables, so ``answer`` and ``conflicts`` build nothing. The
store orders crawls by ``taken_on`` (an ISO datetime is cut to its date; a crawl without an ISO date is skipped with
one line), so the order of the calls does not matter. One summary line per crawl goes to stdout and its counts stay
in ``ingested``.

``answer(question, as_of)`` parses the question cut to ``max_question_chars`` (``KB-E05`` for an empty, non-text or
over-long one, ``KB-E04`` for a malformed date), looks in the answer cache, then runs ``resolve`` and
``render_with_dropped``. The cache lives until the next ``ingest`` and is keyed by the whole parsed ``Query``: its
``canonical_key`` and ``as_of`` plus the question's words and numbers, which the resolver also reads (a yes/no
verdict, the "personal" filter of a list, the refusal's span), so two questions that share a canonical key never
share an answer. A malformed ``as_of`` bypasses the cache, and every answer handed out is a fresh copy. Any exception
becomes the refusal: the named classes report through ``KB-E06`` once, anything else is logged with the question.

``conflicts()`` copies the curated conflicts list (``kb.conflicts``). Every ingest verifies the curated sources that
name its crawl (quote on the page, value in the quote) and rebuilds the list and its answer-note index; an entry that
fails is reported once (``KB-E07``), and a missing or invalid ``conflicts_curated.json`` leaves both empty. A confident
answer whose first fact has a verified conflict carries that conflict's note in ``conflict_note`` (``with_note``, also
applied before caching); the answer text never changes.
"""
from __future__ import annotations

import dataclasses
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from contract import Answer, Conflict, Snapshot

from . import extract_rules
from .blocks import load_boilerplate
from .compose import product_names, refusal, render_with_dropped
from .config import Config
from .conflicts import ConflictBook, NoteIndex, load_curated, note_index, with_note
from .errors import KBError, warn_once
from .extract_prose import prose_facts
from .extract_fees import extract_fees
from .extract_rules import SourceContext, extract_page, reset_census
from .normalize import canonical_url
from .pagetype import authority_of, classify, is_legacy_alias, legacy_shaped
from .question import Query, parse
from .registry import Registry
from .prose_facts import ProseBook, load_prose
from .resolve import resolve
from .store import FactStore
from .types import Fact, fact_to_dict

_FALLBACK_SPAN = "that"  # the refusal's span when answering itself failed
_WARM_UP = "What is the Share Savings APY?"  # any question will do: answering one builds the lazy tables
_EXPECTED = (KBError, LookupError, RuntimeError, TypeError, ValueError)  # date, store and data failures
_LOG_CHARS = 120  # how much of a question or a value a log line quotes
_CURATED_CONFLICTS = "conflicts_curated.json"  # in config.data_dir

PageText = Tuple[str, str, str, bool]  # (url, markdown, canonical URL, legacy-shaped raw URL)


def _crawl_day(taken_on: object) -> Optional[str]:
    """``taken_on`` as the ``YYYY-MM-DD`` day the store orders crawls by: an ISO date as it is, an ISO datetime cut to
    its date (its first 10 characters; a ``Z`` suffix reads as UTC on every Python), ``None`` for anything else."""
    if not isinstance(taken_on, str):
        return None
    text = taken_on.strip()
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text).date().isoformat()
    except ValueError:
        return None


def _page_text(page: Any) -> Optional[PageText]:
    """The url, markdown, canonical URL and legacy shape of a page; ``None`` when the url or the markdown is missing
    or ``urlsplit`` rejects the url ("Invalid IPv6 URL"), so such a page is skipped and counted, never raised."""
    url, markdown = getattr(page, "url", None), getattr(page, "markdown", None)
    if not (isinstance(url, str) and url.strip() and isinstance(markdown, str)):
        return None
    try:
        return url, markdown, canonical_url(url), legacy_shaped(url)
    except ValueError:
        return None


def _canonical_pages(texts: Iterable[PageText]) -> Dict[str, str]:
    """Canonical URL to markdown for every page whose raw URL is not shaped like an old copy; the first such page in
    crawl order stands for a canonical URL that several share."""
    out: Dict[str, str] = {}
    for _, markdown, canonical, shaped in texts:
        if not shaped:
            out.setdefault(canonical, markdown)
    return out


def _load_book(data_dir: Any) -> ConflictBook:
    """The curated conflicts book; a missing or invalid file prints one stderr line and gives an empty book."""
    path = Path(data_dir) / _CURATED_CONFLICTS
    try:
        return ConflictBook(load_curated(path))
    except Exception as exc:  # a bad data file must not stop the system from answering
        print("kb: {} not loaded ({}: {}): no curated conflicts".format(
            path, type(exc).__name__, str(exc)[:_LOG_CHARS]), file=sys.stderr)
        return ConflictBook(())


def _copy(answer: Answer) -> Answer:
    """A fresh ``Answer`` holding fresh ``Source`` objects: both are mutable, and the cache never hands out its own."""
    return dataclasses.replace(answer, sources=[dataclasses.replace(s) for s in answer.sources])


def _log_failure(exc: Exception, question: object) -> None:
    """The ``KB-E06`` line for a failure outside the named classes, with the question; built from strings only and
    printed every time (``warn_once`` would hide all but the first). Never raises."""
    try:
        asked = question[:_LOG_CHARS] if isinstance(question, str) else "a {} question".format(type(question).__name__)
        detail = "{} ({}) for question {!r}".format(type(exc).__name__, str(exc)[:_LOG_CHARS], asked)
        print(KBError("KB-E06", error=detail), file=sys.stderr)
    except Exception:  # reporting a failure must never become one
        pass


def _ms(start: float, end: float) -> float:
    return round((end - start) * 1000.0, 3)


class KnowledgeSystem:
    """``ingest`` each crawl, then ``answer`` and ``conflicts``; ``store`` and ``registry`` are public for tests and
    ``explain``, and ``ingested`` maps each crawl id to its summary counts."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.registry = Registry.load()
        self.store = FactStore()
        self.ingested: Dict[str, Dict[str, Any]] = {}
        self._boilerplate = load_boilerplate()
        self._answers: Dict[Query, Answer] = {}
        self._book = _load_book(config.data_dir)
        try:
            self._prose_book = ProseBook(load_prose(Path(config.data_dir) / "prose_facts.json", self.registry))
        except (OSError, ValueError) as exc:
            print("kb: prose facts not loaded: {}".format(exc), file=sys.stderr)
            self._prose_book = ProseBook(())
        self._conflicts: List[Conflict] = []  # rebuilt at the end of every ingest, only copied by conflicts()
        self._notes: NoteIndex = {}  # (product_id, attribute) -> verified entries, rebuilt with _conflicts
        self._dropped: Set[str] = set()  # topics already reported with KB-E07

    def ingest(self, snapshot: Snapshot) -> None:
        """Add one crawl's facts, finalise the store, empty the answer cache and warm up (see the module docstring)."""
        start = time.perf_counter()
        snapshot_id = snapshot.snapshot_id
        if snapshot_id in self.ingested:  # adding it again would hold every fact twice
            print("kb: {} is ingested already: skipped".format(snapshot_id), file=sys.stderr)
            return
        day = _crawl_day(snapshot.taken_on)
        if day is None:  # the store orders crawls by this day, so a crawl without one cannot be placed
            taken_on = snapshot.taken_on
            shown = repr(taken_on[:_LOG_CHARS]) if isinstance(taken_on, str) else "of type " + type(taken_on).__name__
            print("kb: {} has taken_on {}, not an ISO date: skipped".format(snapshot_id, shown), file=sys.stderr)
            return
        reset_census()
        pages = list(snapshot.pages or ())
        texts = [_page_text(page) for page in pages]
        canonical_pages = _canonical_pages(text for text in texts if text is not None)
        facts: List[Fact] = []
        skipped: List[str] = []
        for page, text in zip(pages, texts):
            if text is None:
                skipped.append("a page without a usable url or markdown")
                continue
            fetched_at = getattr(page, "fetched_at", None) or day
            try:
                facts.extend(self._page_facts(text, fetched_at, snapshot_id, canonical_pages))
            except Exception as exc:  # one unreadable page must not lose the crawl
                skipped.append("{}: {}".format(text[0][:_LOG_CHARS], type(exc).__name__))
        prose_pages = {}
        needed = self._prose_book.pages_needed(snapshot_id) | self._book.pages_needed(snapshot_id)
        for text in sorted((t for t in texts if t is not None), key=lambda t: (t[3], t[0])):
            if text[2] in needed:
                prose_pages.setdefault(text[2], (text[0], text[1]))
        normalized = {}
        facts.extend(self._prose_book.facts(snapshot_id, prose_pages, normalized))
        try:
            self.store.add(snapshot_id, day, facts)
        finally:
            self.store.finalize()  # never leave the store dirty: in_force() would raise for every question
        self._check_conflicts(snapshot_id, prose_pages, normalized)
        self._answers.clear()
        self._warm_up()
        counts = {"pages": len(pages) - len(skipped), "skipped_pages": len(skipped), "facts": len(facts),
                  "unmapped_rows": len(extract_rules.UNMAPPED), "ignored_rows": extract_rules.IGNORED,
                  "seconds": round(time.perf_counter() - start, 2)}
        self.ingested[snapshot_id] = counts
        print("kb: ingested {} pages={pages} facts={facts} unmapped_rows={unmapped_rows} ignored_rows={ignored_rows} "
              "in {seconds:.2f} s".format(snapshot_id, **counts), flush=True)
        if skipped:
            print("kb: skipped {} pages of {}: {}".format(len(skipped), snapshot_id, "; ".join(skipped[:3])),
                  file=sys.stderr)

    def _page_facts(self, text: PageText, fetched_at: str, snapshot_id: str,
                    canonical_pages: Dict[str, str]) -> List[Fact]:
        """The page typed (``legacy_alias`` for a near-copy of a canonical page, cited by that page's URL) and its
        facts extracted: the rules facts, then the prose facts of a dated article (``prose_facts``)."""
        url, markdown, canonical, _ = text
        alias_of = is_legacy_alias(url, markdown, canonical_pages)
        page_type = "legacy_alias" if alias_of else classify(url, markdown)
        ctx = SourceContext(url, alias_of or canonical, page_type, authority_of(page_type), snapshot_id, fetched_at)
        facts = extract_page(markdown, ctx, self.registry, self._boilerplate)
        from .page_urls import page_url_facts
        return (facts + prose_facts(markdown, ctx, self._boilerplate) + page_url_facts(ctx, self.registry)
                + extract_fees(markdown, ctx, self.registry, self._boilerplate))

    def _check_conflicts(self, snapshot_id: str, source_pages: Dict[str, Tuple[str, str]], normalized: Dict[str, str]) -> None:
        """Verify this crawl's curated conflict sources, rebuild the emitted list and the note index and report each
        newly dropped entry once (``KB-E07``). A needed URL is read from its page whose raw URL is not legacy-shaped,
        else from the first legacy-shaped one. A failure here is only logged: curated data never loses a crawl."""
        try:
            needed = self._book.pages_needed(snapshot_id)
            pages = {url: source_pages[url][1] for url in needed if url in source_pages}
            self._book.observe(snapshot_id, pages, normalized)
            self._conflicts = self._book.emit()
            self._notes = note_index(self._book.verified())
            for topic, why in self._book.dropped(list(self.ingested) + [snapshot_id]):
                if topic not in self._dropped:
                    self._dropped.add(topic)
                    print(KBError("KB-E07", topic=topic, why=why), file=sys.stderr)
        except Exception as exc:  # the crawl's facts are in the store already
            print("kb: curated conflicts of {} not checked: {}".format(snapshot_id, type(exc).__name__),
                  file=sys.stderr)

    def _warm_up(self) -> None:
        """One answer outside the cache plus the composer's names, so the first graded answer finds the
        canonicaliser's phrase table and ``product_names`` built and does no I/O. A failure here is only logged."""
        try:
            render_with_dropped(resolve(self._parse(_WARM_UP, None), self.store, self.registry))
            product_names()
        except Exception as exc:  # answer() has its own guard, and ingest() must not fail on a warm-up
            _log_failure(exc, _WARM_UP)

    def _parse(self, question: object, as_of: object) -> Query:
        """``parse`` with the question cut to ``max_question_chars`` before any regex; ``KB-E05`` for an empty,
        non-text or over-long question (an over-long one is answered from its cut), ``KB-E04`` for a malformed date."""
        limit = self.config.max_question_chars
        if not isinstance(question, str) or not question.strip() or len(question) > limit:
            warn_once("KB-E05", limit=limit)
        crawls = self.store.snapshots()  # the newest crawl's day gives a month written without a year its year
        q = parse(question, as_of, self.registry, limit, reference_date=crawls[-1][1] if crawls else None)
        if q.as_of_error:
            warn_once("KB-E04", value=as_of[:_LOG_CHARS] if isinstance(as_of, str) else as_of)
        return q

    def answer(self, question: Optional[str], as_of: Optional[str] = None) -> Answer:
        """The member-facing answer, from the cache when this exact question was answered since the last ingest;
        never raises (see the module docstring)."""
        try:
            q = self._parse(question, as_of)
            if q.as_of_error:  # before the cache: a malformed date is never served a cached answer
                return render_with_dropped(resolve(q, self.store, self.registry))[0]
            cached = self._answers.get(q)
            if cached is None:
                plan = resolve(q, self.store, self.registry)
                cached = self._answers[q] = with_note(render_with_dropped(plan)[0], plan, self._notes)
            return _copy(cached)
        except _EXPECTED as exc:  # a date, store or data failure
            warn_once("KB-E06", error=type(exc).__name__)
        except Exception as exc:  # the circuit breaker: anything else, logged with the question
            _log_failure(exc, question)
        return refusal(_FALLBACK_SPAN)

    def conflicts(self) -> List[Conflict]:
        """The curated conflicts whose every source verified at ingest, as fresh objects; ``[]`` on any failure."""
        try:
            return [dataclasses.replace(c, values=list(c.values), sources=[dataclasses.replace(s) for s in c.sources])
                    for c in self._conflicts]
        except Exception:  # conflicts() never raises
            return []

    def explain(self, question: Optional[str], as_of: Optional[str] = None) -> Dict[str, Any]:
        """What ``answer`` does with this question, stage by stage, as JSON-ready data with string keys only.

        The same ``_parse``, ``resolve`` and ``render_with_dropped`` run, but the answer cache is bypassed (neither
        read nor filled), so ``timings_ms`` are real. ``candidates`` are the plan's facts in plan order with their
        position as ``rank`` (1 first) and ``winner`` is the first of them, ``None`` for a refusal.
        """
        t0 = time.perf_counter()
        q = self._parse(question, as_of)
        t1 = time.perf_counter()
        plan = resolve(q, self.store, self.registry)
        t2 = time.perf_counter()
        answer, dropped = render_with_dropped(plan)
        t3 = time.perf_counter()
        candidates = [{"rank": i, **fact_to_dict(f)} for i, f in enumerate(plan.facts, 1)]
        return {
            "question": q.raw_span,
            "as_of": q.as_of,
            "as_of_error": q.as_of_error,
            "canonical_key": q.canonical_key,
            "snapshot_id": plan.snapshot_id,
            "candidates": candidates,
            "winner": candidates[0] if candidates else None,
            "answer": answer.text,
            "confident": answer.confident,
            "dropped_sentences": dropped,
            "timings_ms": {"parse": _ms(t0, t1), "resolve": _ms(t1, t2), "render": _ms(t2, t3)},
        }
