#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild the offline Nemaplex snapshot used by this skill.

Data source: Nemaplex, UC Davis (http://nemaplex.ucdavis.edu/)
Everything written to data/ comes from that site. Nothing is guessed.

What this script collects
-------------------------
1. Genus index (6 alphabetical pages)  -> genus / family / putative feeding / c-p / feeding group / functional guild / internal code
2. Family menu pages (one per family)  -> class / subclass / order / suborder / superfamily for each family
3. Category heading pages              -> authoritative definitions of the c-p classes and feeding group codes
4. Feeding habits by family            -> Ecology/feeding_habits.htm
5. Classification overview             -> Taxadata/Classes.htm (modern + classical order lists)

Usage
-----
    python scripts/build_snapshot.py                # use .cache/ where possible
    python scripts/build_snapshot.py --refresh      # ignore cache, re-download everything
    python scripts/build_snapshot.py --only genera  # rebuild a single dataset

Requests are rate limited and cached. A full cold run is roughly 300 requests.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "http://nemaplex.ucdavis.edu/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, ".cache")
UA = "nemaplex-snapshot-builder/1.0 (taxonomy verification; contact: local user)"
DELAY = 0.25
TIMEOUT = 30

GENUS_INDEX_PAGES = ["atob.html", "ctod.html", "etol.html", "mtoo.html", "ptor.html", "stoz.html"]
GLOSSARY_PAGES = {
    "cp_classes": "Heading%20Category-CP%20Classes.html",
    "feeding_groups": "Heading%20Category-Feeding%20Groups.html",
    "functional_guilds": "Heading%20Category-Functional%20Guilds.html",
    "putative_feeding": "Heading%20Category-Putative%20Feeding.html",
    "family": "Heading%20Category-Family.html",
}


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #

def cache_path(url: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", url.replace(BASE, ""))[:150]
    return os.path.join(CACHE_DIR, name)


def fetch(url: str, refresh: bool = False) -> str:
    """Download `url`, caching the body in .cache/. Returns the HTML text."""
    path = cache_path(url)
    if not refresh and os.path.exists(path):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                html = resp.read().decode("utf-8", "ignore")
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            time.sleep(DELAY)
            return html
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # noqa: PERF203
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    print(f"  ! failed {url}: {last_err}", file=sys.stderr)
    return ""


# --------------------------------------------------------------------------- #
# html helpers
# --------------------------------------------------------------------------- #

def rows(html: str) -> list[list[str]]:
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        out.append(re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I))
    return out


def text_of(cell: str) -> str:
    s = re.sub(r"<[^>]+>", "", cell)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


NOISE = re.compile(r"<style.*?</style>|<script.*?</script>|<!--.*?-->|<o:p.*?</o:p>",
                   re.S | re.I)


def strip_noise(html: str) -> str:
    """Drop CSS, scripts, HTML comments and the Word <o:p> padding.

    The site is Word-exported: leaving <style> in place means the CSS text
    ("p.MsoNormal {margin-bottom:.0001pt; ...}") shows up as page content and
    pollutes every downstream regex.
    """
    return NOISE.sub(" ", html)


def plain(html: str) -> str:
    s = re.sub(r"<[^>]+>", " ", strip_noise(html))
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


# Block level tags separate words; everything else is inline formatting.
BLOCK_TAGS = re.compile(
    r"</?(?:tr|td|th|tbody|thead|table|p|div|br|li|ul|ol|dl|dt|dd|h[1-6]|"
    r"center|body|head|html|title|hr|pre|blockquote)[^>]*>", re.I)


def flow_text(html: str) -> str:
    """Tags -> "" for inline markup, " " for block structure.

    This site splits single words across inline spans, e.g.
        <span>C</span><span>hromadoria</span>     ->  Chromadoria
        <a>E<font size="4">noplea</font></a>      ->  Enoplea
    Collapsing every tag to a space (see `plain`) turns those into
    "C hromadoria" and silently drops the rank name. Replacing only block
    tags with a space keeps both the words and the column separations.
    """
    s = BLOCK_TAGS.sub(" ", strip_noise(html))
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def write_json(name: str, payload) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=False)
    size = os.path.getsize(path)
    print(f"  -> data/{name}  ({size:,} bytes)")


def load_json(name: str, default=None):
    """Read a previously written snapshot file, or `default` if absent."""
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# 1. genus index
# --------------------------------------------------------------------------- #

ROMAN_RANKS = ["family", "putative_feeding", "cp", "feeding_group", "functional_guild", "internal_code"]


def build_genus_index(refresh: bool = False) -> dict:
    """Parse the six alphabetical genus index pages.

    Column layout (fixed across all six pages):
        Genus | Family | Putative Feeding | c-p Group | Feeding Group | Functional Guild | Internal Code

    A row is a genus row when its first cell carries an italic marker
    (<em> or <i>). Rows without an internal code (no G####mnu.htm link) are
    still valid genera and must NOT be dropped.
    """
    print("[1/5] genus index")
    genera: dict[str, dict] = {}
    for page in GENUS_INDEX_PAGES:
        html = fetch(BASE + "IndexFiles/" + page, refresh)
        if not html:
            continue
        count = 0
        for cells in rows(html):
            if not cells or not re.search(r"<\s*(em|i)\b", cells[0], re.I):
                continue
            name = text_of(cells[0])
            if len(name) < 3 or not re.match(r"^[A-Za-z][A-Za-z\-'\. ]+$", name):
                continue
            vals = [text_of(c) for c in cells[1:7]]
            while len(vals) < len(ROMAN_RANKS):
                vals.append("")
            rec = dict(zip(ROMAN_RANKS, vals))
            rec["source_page"] = page
            genera.setdefault(name, rec)
            count += 1
        print(f"  {page}: {count} genera")
    print(f"  total genera: {len(genera)}")
    return genera


# --------------------------------------------------------------------------- #
# 2. family -> higher classification
# --------------------------------------------------------------------------- #

SUBCLASS_HINT = re.compile(r"(ia)$")
ORDER_HINT = re.compile(r"(ida)$")
SUBORDER_HINT = re.compile(r"(ina)$")
SUPERFAMILY_HINT = re.compile(r"(oidea)$")

# Ranks whose names do NOT follow the suffix rule, or where the suffix is
# ambiguous, so they are looked up explicitly.
RANK_BY_NAME = {
    "chromadorea": "class",
    "enoplea": "class",
    "chromadoria": "subclass",
    "enoplia": "subclass",
    "dorylaimia": "subclass",
    "rhabditia": "subclass",
    "spiruria": "subclass",
    "diplogastria": "subclass",
    "tylenchia": "subclass",
}

RANK_WORD = re.compile(r"^[A-Za-z][A-Za-z\-']{2,24}$")


def classify_rank(tok: str) -> str:
    key = tok.lower()
    if key in RANK_BY_NAME:
        return RANK_BY_NAME[key]
    # order matters: -oidea before -ina before -ida before -ia
    if tok.endswith("oidea"):
        return "superfamily"
    if tok.endswith("ina"):
        return "suborder"
    if tok.endswith("ida"):
        return "order"
    if tok.endswith("ia"):
        return "subclass"
    return ""


def page_cells(html: str) -> list[str]:
    """All table cells in document order, tags stripped to the EMPTY string.

    Do NOT collapse the page to plain text with a space as the tag replacement:
    the site wraps single letters in their own span, e.g.
        <span>C</span><span>hromadoria</span>   ->  Chromadoria
    and a space-joining pass turns it into "C hromadoria". `text_of` joins with
    "" which is what we want here.
    """
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I):
            out.append(text_of(cell))
    return out


# Second breadcrumb dialect, used by a handful of pages (e.g. Pratylenchidae):
#   "Pratylenchidae Menu Order Rhabditida Sub-order Tylenchina
#    Superfamily Tylenchoidea Family Pratylenchidae Subfamily ..."
# There is no Nematoda row and no class/subclass - those are filled in later
# from the classification tree on Taxadata/Classes.htm.
LABELED_RANKS = {
    "order":       r"(?<![-A-Za-z])Order\s*:?\s+([A-Z][A-Za-z]+)",
    "suborder":    r"Sub-?\s?order\s*:?\s+([A-Z][A-Za-z]+)",
    "superfamily": r"Super-?\s?family\s*:?\s+([A-Z][A-Za-z]+)",
    "family":      r"(?<![-A-Za-z])Family\s*:?\s+([A-Z][A-Za-z]+)",
}

BOX_FAMILY = r"^\s*Family\s*:?\s*(.*)$"


def parse_labeled_breadcrumb(html: str) -> dict | None:
    """Fallback parser for the 'Order X Sub-order Y Family Z' dialect."""
    s = flow_text(html)
    out = {"raw": "", "family": "", "class": "", "subclass": "",
           "order": "", "suborder": "", "superfamily": ""}
    for rank, pat in LABELED_RANKS.items():
        m = re.search(pat, s)
        if m:
            out[rank] = m.group(1)
    out["raw"] = " ".join(f"{k}={v}" for k, v in out.items() if v and k != "raw")
    return out if (out["family"] and out["order"]) else None


CLASSIFICATION_HEAD = re.compile(r"Classification\s*:?", re.I)
FAMILY_TOKEN = re.compile(r"\b([A-Z][A-Za-z\-]{3,}idae)\b")


def parse_dl_breadcrumb(html: str) -> dict | None:
    """Third breadcrumb dialect: the legacy ``.aspx`` family pages.

    These pages are not tables at all. They use <dl>/<dd>/<p> for the first
    three ranks and <div>/<dt> for the rest, and only phylum/class/subclass
    carry a label:

        <h3>Classification:</h3>
        <dl>
          <dd><p>Phylum <a>Nematoda</a></p></dd>
          <dd><p>Class  <a>Chromadorea</a></p></dd>
          <dd><p>Subclass Chromadoria</p></dd>
        </dl>
        <div><dt><a>Rhabditida</a></dt></div>
        <div><dt><a>Spirurina</a></dt></div>
        <dt><a>Heterakoidea</a></dt>
        <dd>Kiwinematidae Inglis &amp; Harris, 1990</dd>

    Order, suborder and superfamily are therefore bare names and can only be
    ranked by their suffix. The slice deliberately stops at the family name:
    below it comes the family description, which names genera and neighbouring
    families and would otherwise be read as more breadcrumb rows.
    """
    clean = strip_noise(html)
    m = CLASSIFICATION_HEAD.search(clean)
    if not m:
        return None
    block = clean[m.end():]
    stop = FAMILY_TOKEN.search(block)
    if stop:
        block = block[:stop.end()]

    out = {"raw": "", "family": "", "class": "", "subclass": "",
           "order": "", "suborder": "", "superfamily": ""}
    seen: list[str] = []
    for tok in flow_text(block).split():
        if not RANK_WORD.match(tok):
            continue
        rank = classify_rank(tok)
        if not rank and tok.endswith("idae"):
            rank = "family"
        if rank and not out[rank]:
            out[rank] = tok
            seen.append(tok)
    out["raw"] = " ".join(seen)
    return out if out["family"] else None


def parse_family_page(html: str) -> dict | None:
    """Parse the classification breadcrumb of a family menu page.

    The usual breadcrumb is a one-cell-per-row table directly under the header:

        Nematoda
        Chromadorea
        Chromadoria
        Chromadorida
        Chromadorina
        Chromadoroidea
        Family Achromadoridae

    Ranks are read by walking cells forward from "Nematoda" while they still
    look like rank names, then the family is taken from the "Family" cell.
    Visible text is preferred over the link target: the hrefs contain typos
    (e.g. Aponidae.aspx for Aponchiidae).

    Pages without a Nematoda row fall back to the labelled dialect, see
    parse_labeled_breadcrumb, and then to the <dl> dialect used by the legacy
    .aspx family pages, see parse_dl_breadcrumb.
    """
    cells = page_cells(html)
    try:
        start = next(i for i, c in enumerate(cells) if c.strip().lower() == "nematoda")
    except StopIteration:
        return parse_labeled_breadcrumb(html) or parse_dl_breadcrumb(html)

    out = {"raw": "", "family": "", "class": "", "subclass": "",
           "order": "", "suborder": "", "superfamily": ""}
    seen: list[str] = []
    for cell in cells[start + 1:]:
        tok = cell.strip()
        if RANK_WORD.match(tok):
            rank = classify_rank(tok)
            if rank:
                if not out[rank]:
                    out[rank] = tok
                seen.append(tok)
                continue
        # first cell that is not a bare rank name ends the breadcrumb
        break

    out["raw"] = " ".join(seen)

    # family: "Family Xxxx" / "Family: Xxxx" / "Family" then the next cell
    for i, cell in enumerate(cells):
        m = re.match(BOX_FAMILY, cell, re.I)
        if not m:
            continue
        name = m.group(1).strip()
        if not name and i + 1 < len(cells):
            name = cells[i + 1].strip()
        name = re.sub(r"^\d+[\.\s]*", "", name)
        if RANK_WORD.match(name):
            out["family"] = name
            break

    if not out["family"]:
        # last resort: the family .aspx link (may be abbreviated - prefer text)
        m = re.search(r'href="[^"]*/([A-Za-z][A-Za-z\-]+)\.aspx"', html, re.I)
        if m:
            out["family"] = m.group(1)

    return out if (out["family"] or out["order"]) else None


FAMILY_HREF = re.compile(r'href="([^"]*(?:mnu\.htm|\.aspx))"', re.I)


def family_index_links(index_html: str) -> dict[str, str]:
    """name -> href for every family on the Index to Families page.

    Read whole <td> cells, not just the anchor text: on this page a few labels
    start OUTSIDE their link, e.g.
        <strong>A<a href="../Taxamnus/Asciidaemnu.htm">scaridiidae</a></strong>
    Taking only the anchor text yields "scaridiidae" and loses the family.
    Working cell-first and dropping anything that is not a single word also
    removes the "Return to Nemaplex Main Menu" navigation link for free.

    Two href flavours are accepted. Almost every family has a modern
    ``Taxamnus/<code>mnu.htm`` menu page, but a legacy handful carries only a
    ``Taxadata/<code>.aspx`` page -- Kiwinematidae is the one case on the
    current site. Matching only ``mnu.htm`` silently drops that family from the
    snapshot, which then makes its genera unresolvable. The same two flavours
    also show up in the genus index's family column (Allgenia, Oonaguntus,
    Xennella), where the *displayed* name is often a source typo that the
    canonical family page spells correctly.
    """
    links: dict[str, str] = {}
    for cell in re.findall(r"<td[^>]*>(.*?)</td>", index_html, re.S | re.I):
        m = FAMILY_HREF.search(cell)
        if not m:
            continue
        name = text_of(cell)
        if not name or " " in name or len(name) < 5 or len(name) > 40:
            continue
        if not name[0].isupper() or not name.isascii():
            continue
        links.setdefault(name, m.group(1))
    return links


def build_family_map(refresh: bool = False) -> tuple[dict, dict]:
    """Crawl one menu page per family to get its class/order breadcrumb."""
    print("[2/5] family -> order/class")
    index_html = fetch(BASE + "IndexFiles/Index%20to%20FamiliesNew.html", refresh)
    if not index_html:
        index_html = fetch(BASE + "IndexFiles/families.html", refresh)

    links = family_index_links(index_html)
    print(f"  family links found: {len(links)}")

    families: dict[str, dict] = {}
    for i, (name, link) in enumerate(sorted(links.items()), 1):
        leaf = link.split("/")[-1]
        folder = "Taxamnus" if leaf.lower().endswith("mnu.htm") else "Taxadata"
        parsed = parse_family_page(fetch(BASE + folder + "/" + leaf, refresh))
        if parsed:
            families[name] = parsed
        else:
            families[name] = {"raw": "", "family": name, "class": "", "subclass": "",
                              "order": "", "suborder": "", "superfamily": ""}
            print(f"  ! no breadcrumb: {name} ({link})")
        if i % 50 == 0:
            print(f"  ... {i}/{len(links)}")
    ok = sum(1 for v in families.values() if v["order"])
    print(f"  families with order resolved: {ok}/{len(families)}")
    return families, links


def fill_missing_class(families: dict, overview: dict) -> int:
    """Fill class / subclass for families whose own page does not state them.

    Some family pages (the 'Order X / Sub-order Y' dialect) omit class and
    subclass entirely. The order -> class mapping is read from the modern
    classification tree on Taxadata/Classes.htm, i.e. still the site's own
    data rather than an inference of ours.
    """
    modern = overview.get("modern") or {}
    order_to_class, order_to_subclass = {}, {}
    for cls, orders in (modern.get("orders_by_class") or {}).items():
        for o in orders:
            order_to_class.setdefault(o, cls)
    for sub, orders in (modern.get("orders_by_subclass") or {}).items():
        for o in orders:
            order_to_subclass.setdefault(o, sub)

    filled = 0
    for v in families.values():
        o = v.get("order")
        if not o:
            continue
        if not v.get("class") and o in order_to_class:
            v["class"] = order_to_class[o]
            v["class_source"] = "inferred-from-order-tree"
            filled += 1
        if not v.get("subclass") and o in order_to_subclass:
            v["subclass"] = order_to_subclass[o]
            v["subclass_source"] = "inferred-from-order-tree"
    return filled


def repair_missing_orders(families: dict, extra_known: set | None = None) -> int:
    """Recover families whose page skips the order rank.

    A few pages list class, subclass, suborder and superfamily but omit the
    order row (e.g. Aponchiidae: ... Chromadoria Microlaimina Microlaimoidea).

    Recovery rule: the suborder is the order name with -ina instead of -ida.
    Only accept the substitution when the resulting name is an order that
    really occurs somewhere else - in another family's breadcrumb, or in the
    order list on Taxadata/Classes.htm. Never invent an order. Anything left
    unresolved keeps order="" and is reported.
    """
    known = {v["order"] for v in families.values() if v["order"]}
    known |= set(extra_known or ())
    fixed, left = [], []
    for name, v in families.items():
        if v["order"] or not v.get("suborder"):
            continue
        sub = v["suborder"]
        guess = sub[:-3] + "ida" if sub.endswith("ina") else ""
        if guess and guess in known:
            v["order"] = guess
            v["order_source"] = "inferred-from-suborder"
            fixed.append(f"{name}: {sub} -> {guess}")
        else:
            v["order_source"] = "missing-on-site"
            left.append(name)
    if fixed:
        print(f"  order recovered from suborder: {len(fixed)}")
        for f in fixed:
            print(f"    {f}")
    if left:
        print(f"  ! order genuinely absent on site: {len(left)} -> {', '.join(left)}")
    return len(fixed)


# --------------------------------------------------------------------------- #
# 2b. family-name normalisation (genus index -> canonical family table)
# --------------------------------------------------------------------------- #

def load_labels() -> dict:
    """Read data/zh_cn_labels.json (hand-maintained, never generated)."""
    path = os.path.join(DATA_DIR, "zh_cn_labels.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def normalise_family_name(raw: str, authority: set[str], aliases: dict) -> tuple[str, str, list[str]]:
    """Map one genus-index family label onto the canonical family table.

    Returns ``(canonical, note, alternatives)``.

    The genus index and the Index to Families page are edited separately, so
    they disagree in three documented ways:

    * plain typos -- ``Crateronematdae`` -> ``Crateronematidae``,
      ``Linhomoiedae`` -> ``Linhomoeidae`` (letters transposed);
    * acknowledged variants -- ``Xennellidae`` -> ``Xenellidae``; the family
      page itself says "Xenellidae (or Xennellidae)" and "Xennellidae De
      Coninck, 1965 (also as Xenellidae)";
    * slash notation for a genus placed in either of two families, e.g.
      ``Hypodontolaimidae/Chromadoridae`` for Chromadorita. The first name is
      taken as primary and the rest is kept in ``family_alternatives`` rather
      than thrown away.

    A final difflib pass at a high cut-off is only a safety net for typos not
    yet registered in ``family_aliases``; it never invents a family that is not
    already in the authority set. Anything still unmatched is returned as-is so
    the caller can report it.
    """
    name = (raw or "").strip()
    alternatives: list[str] = []
    if "/" in name:
        parts = [p.strip() for p in name.split("/") if p.strip()]
        alternatives = parts[1:]
        name = parts[0] if parts else ""

    if not name or name in authority:
        return name, "", alternatives
    if name in aliases and aliases[name] in authority:
        return aliases[name], f"科名按 Nemaplex 分类表归一：{raw} → {aliases[name]}", alternatives
    guess = difflib.get_close_matches(name, sorted(authority), n=1, cutoff=0.9)
    if guess:
        return guess[0], f"科名疑似拼写错误，按最相近科名归一：{raw} → {guess[0]}", alternatives
    return name, "", alternatives


def normalise_genus_families(genera: dict, families: dict, aliases: dict) -> dict:
    """Rewrite genus_index family labels to match family_order_class.json."""
    print("[1b/5] normalise genus family names")
    authority = set(families.keys())
    if not authority:
        print("  ! family table empty, skipped")
        return {}
    stats = {"total": len(genera), "renamed": 0, "composite": 0, "blank": 0, "unmatched": 0}
    unmatched: list[str] = []

    for genus, rec in genera.items():
        raw = rec.get("family", "")
        if not raw:
            stats["blank"] += 1
            continue
        canon, note, alternatives = normalise_family_name(raw, authority, aliases)
        if canon != raw:
            rec["family_raw"] = raw
            rec["family"] = canon
            stats["renamed"] += 1
            print(f"  family normalised: {genus}: {raw} -> {canon}")
        if note:
            rec["family_note"] = note
        if alternatives:
            rec["family_alternatives"] = alternatives
            stats["composite"] += 1
        if rec["family"] not in authority:
            stats["unmatched"] += 1
            unmatched.append(f"{genus} ({rec['family']})")

    print(f"  genera: {stats['total']}, renamed: {stats['renamed']}, "
          f"composite: {stats['composite']}, no family on site: {stats['blank']}")
    if unmatched:
        print(f"  ! family still not in classification table: {len(unmatched)}")
        for u in unmatched:
            print(f"    {u}")
    else:
        print("  every genus with a family resolved to the classification table")
    return stats


# --------------------------------------------------------------------------- #
# 3. code glossaries
# --------------------------------------------------------------------------- #

def build_glossaries(refresh: bool = False) -> dict:
    """Pull the authoritative definitions of the c-p classes and feeding groups.

    Two page shapes occur and both are kept:
      * tabular pages (CP Classes, Feeding Groups) -> `table`, rows as list of cells
      * prose pages (Functional Guilds, Putative Feeding, Family) -> `text`
    """
    print("[3/5] code glossaries")
    out: dict[str, dict] = {}
    for key, page in GLOSSARY_PAGES.items():
        url = BASE + "IndexFiles/" + page
        html = fetch(url, refresh)
        table = []
        for cells in rows(html):
            row = [text_of(c) for c in cells if text_of(c)]
            if row:
                table.append(row)
        header = ""
        m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if m:
            header = text_of(m.group(1))
        body = plain(html)
        if header and body.startswith(header):
            body = body[len(header):].strip()
        out[key] = {"source": url, "title": header, "table": table, "text": body}
        print(f"  {key}: {len(table)} table rows, {len(body)} chars of text")
    return out


def build_feeding_habits(refresh: bool = False) -> dict:
    """Family -> feeding habit, from Ecology/feeding_habits.htm.

    The page is a run of <p> paragraphs, each holding one family followed by
    tab runs and its habit, e.g.
        <p><b>Alaimidae<span style="mso-tab-count:1">&nbsp;...</span>Bacterial-feeding</b></p>
    So: split on <p>, collapse each to flow text, then split name / habit.
    Note the page only covers the plant- and soil-associated families the site
    chose to list - it is not a complete family table.
    """
    print("[4/5] feeding habits by family")
    html = fetch(BASE + "Ecology/feeding_habits.htm", refresh)
    habits: dict[str, str] = {}
    for para in re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I):
        t = flow_text(para)
        m = re.match(r"^([A-Z][A-Za-z]+idae)\s+(\S.*)$", t)
        if m:
            habits.setdefault(m.group(1), m.group(2).strip())
    print(f"  families: {len(habits)}")
    return habits


CELL_RE = re.compile(r"<t[dh]([^>]*)>(.*?)</t[dh]>", re.S | re.I)


def table_grid(table_html: str) -> list[list[tuple[int, int, str, str]]]:
    """Resolve a table into (start_col, colspan, text, link) cells.

    Rowspan is ignored - these trees only use colspan.
    """
    grid = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I):
        col, row = 0, []
        for attrs, body in CELL_RE.findall(tr):
            cs = re.search(r'colspan\s*=\s*"?(\d+)', attrs, re.I)
            span = int(cs.group(1)) if cs else 1
            link = ""
            lm = re.search(r'href="([^"]+mnu\.htm)"', body, re.I)
            if lm:
                link = lm.group(1)
            row.append((col, span, flow_text(body), link))
            col += span
        if row:
            grid.append(row)
    return grid


def parse_tree_table(table_html: str) -> dict:
    """Parse one classification tree from Taxadata/Classes.htm.

    The tree is a fixed-width table using colspan to group columns:

        Nematoda                                  (span the whole table)
        Enoplea (span 4)          Chromadorea (span 2)
        Enoplia(2) Dorylaimia(2)  Chromadoria(2)
        ...      Enoplida          ...  Dorylaimida   ...  Rhabditida

    Grouping is recovered from column positions: an order sits inside the
    subclass column range that contains its column, and a subclass inside the
    class range that contains its own. Deriving it from colspan keeps the tree
    faithful instead of flattening it into one list.
    """
    grid = table_grid(table_html)
    classes: list[tuple[int, int, str]] = []
    subclasses: list[tuple[int, int, str]] = []
    order_cells: list[tuple[int, int, str, str]] = []

    for row in grid:
        toks = [c[2] for c in row if c[2]]
        if toks and all(re.match(r"^[A-Z][a-z]+$", t) for t in toks):
            if len(row) == 2 and not classes and {c[2] for c in row if c[2]} & {
                    "Enoplea", "Chromadorea", "Adenophorea", "Secernentea"}:
                classes = [(c[0], c[1], c[2]) for c in row if c[2]]
                continue
            if not subclasses and all(re.match(r"^[A-Z][a-z]+ia$", t) for t in toks):
                subclasses = [(c[0], c[1], c[2]) for c in row if c[2]]
                continue
        for col, span, text, link in row:
            name = text.lstrip("*").strip(" ;")
            if re.match(r"^[A-Z][a-z]+(?:ida|ea)$", name):
                order_cells.append((col, span, name, link))

    def owner(col: int, groups: list[tuple[int, int, str]]) -> str:
        for start, span, name in groups:
            if start <= col < start + span:
                return name
        return ""

    by_subclass: dict[str, list[str]] = {s[2]: [] for s in subclasses}
    by_class: dict[str, list[str]] = {c[2]: [] for c in classes}
    for col, _, name, _ in order_cells:
        sub = owner(col, subclasses)
        cls = owner(col, classes)
        if sub:
            by_subclass.setdefault(sub, []).append(name)
        if cls:
            by_class.setdefault(cls, []).append(name)

    return {
        "classes": [c[2] for c in classes],
        "subclasses": [s[2] for s in subclasses],
        "subclass_of_class": {s[2]: owner(s[0], classes) for s in subclasses},
        "orders_by_subclass": by_subclass,
        "orders_by_class": by_class,
        "orders": list(dict.fromkeys(o for o in
                                     (c[2] for c in order_cells))),
    }


def leaf_tables(html: str) -> list[str]:
    """Every <table> that contains no nested <table>.

    Taxadata/Classes.htm nests the real classification tree inside a layout
    table. Parsing the outer table shifts every column position (the outer
    cell becomes column 0), which breaks the colspan arithmetic used to group
    orders under their subclass. Working leaf-first avoids that entirely.
    """
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for m in re.finditer(r"<table\b[^>]*>|</table\s*>", html, re.I):
        if m.group(0).lower().startswith("</"):
            if stack:
                spans.append((stack.pop(), m.end()))
        else:
            stack.append(m.start())
    leaves = [sp for sp in spans
              if not any(sp[0] < o[0] and o[1] <= sp[1] for o in spans)]
    leaves.sort()
    return [html[a:b] for a, b in leaves]


def build_classification_overview(refresh: bool = False) -> dict:
    """Modern + classical classification trees, plus the two-class definitions."""
    print("[5/5] classification overview")
    html = fetch(BASE + "Taxadata/Classes.htm", refresh)
    body = strip_noise(html)
    trees = [parse_tree_table(t) for t in leaf_tables(body)]
    # Pick the trees by content, not by position, so a layout tweak cannot
    # silently swap the two systems.
    modern = next((t for t in trees if "Chromadorea" in t["classes"]), {})
    classical = next((t for t in trees if "Adenophorea" in t["classes"]), {})
    return {
        "source": BASE + "Taxadata/Classes.htm",
        "modern": modern,
        "classical": classical,
        "text": plain(html)[:4000],
        "note": "Modern system follows De Ley & Blaxter (SSU rDNA). "
                "Classical system follows Chitwood (1958).",
    }


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild the Nemaplex offline snapshot.")
    ap.add_argument("--refresh", action="store_true", help="ignore cache and re-download")
    ap.add_argument("--only", choices=["genera", "families", "glossary", "habits", "overview"],
                    help="rebuild a single dataset")
    args = ap.parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    started = _dt.datetime.now()
    which = args.only
    meta = {
        "source": "Nemaplex, UC Davis",
        "source_root": BASE,
        "built_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "generator": "scripts/build_snapshot.py",
    }

    genera = {}
    if which in (None, "genera"):
        genera = build_genus_index(args.refresh)

    families, links = {}, {}
    rebuilt_families = False
    if which in (None, "families"):
        families, links = build_family_map(args.refresh)
        rebuilt_families = True
    elif which == "genera":
        # The genus index is normalised against the family table, so load the
        # existing one instead of leaving it empty.
        families = load_json("family_order_class.json", {}) or {}
        links = load_json("family_links.json", {}) or {}

    if which in (None, "glossary"):
        write_json("code_glossaries.json", build_glossaries(args.refresh))

    if which in (None, "habits"):
        write_json("feeding_habits.json", build_feeding_habits(args.refresh))

    overview = {}
    if which in (None, "overview"):
        overview = build_classification_overview(args.refresh)
        write_json("classification_overview.json", overview)

    # Class/order fill-in needs the classification tree from the overview page,
    # so it runs after everything has been collected.
    if rebuilt_families:
        filled = fill_missing_class(families, overview)
        if filled:
            print(f"  class filled from order tree: {filled} families")
        extra = set((overview.get("modern") or {}).get("orders") or [])
        extra |= set((overview.get("classical") or {}).get("orders") or [])
        repair_missing_orders(families, extra)
        write_json("family_order_class.json", families)
        write_json("family_links.json", links)
        meta["family_count"] = len(families)
        meta["family_with_order"] = sum(1 for v in families.values() if v.get("order"))
        meta["family_with_class"] = sum(1 for v in families.values() if v.get("class"))

    # Family names in the genus index are normalised last: the family table has
    # to exist first, otherwise there is nothing to normalise against.
    if genera:
        gstats = normalise_genus_families(genera, families, load_labels().get("family_aliases", {}))
        write_json("genus_index.json", genera)
        meta["genus_count"] = len(genera)
        meta["genus_family_renamed"] = gstats.get("renamed", 0)
        meta["genus_family_unmatched"] = gstats.get("unmatched", 0)
        meta["genus_with_cp"] = sum(1 for v in genera.values() if v.get("cp"))
        meta["genus_with_guild"] = sum(1 for v in genera.values() if v.get("functional_guild"))

    meta_path = os.path.join(DATA_DIR, "_meta.json")
    if os.path.exists(meta_path) and which:
        with open(meta_path, encoding="utf-8") as fh:
            old = json.load(fh)
        old.update({k: v for k, v in meta.items() if k not in ("built_at",)})
        meta = old
    write_json("_meta.json", meta)

    elapsed = (_dt.datetime.now() - started).total_seconds()
    print(f"done in {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
