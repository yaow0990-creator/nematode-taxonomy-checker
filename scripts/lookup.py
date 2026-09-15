#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 2 + 3 of the pipeline: match a resolved genus name against Nemaplex and
attach the higher classification plus the functional guild.

Step 2  classification   genus -> family -> order / class / subclass
Step 3  functional guild c-p value + feeding group + functional guild code

Everything factual in the output comes from the offline snapshot in data/,
which in turn comes from Nemaplex. The only non-Nemaplex content is the
Chinese labelling in data/zh_cn_labels.json, which is flagged as such.

Input
-----
The JSON produced by scripts/normalize_names.py (step 1).

Output
------
A JSON list of fully populated rows:

    no  cn_in  latin_in            <- as supplied
    latin  latin_nemaplex         <- resolved / as recorded by Nemaplex
    fam_nem  subcls_nem  ord_nem  cls_nem
    ord_cn  cls_cn  subcls_cn     <- Chinese labels
    cls_trad  cls_trad_cn         <- classical (Chitwood) class, derived
    cp  cp_cn  cp_desc
    feeding_group  feeding_group_cn
    functional_guild  functional_guild_cn
    putative_feeding  putative_feeding_cn
    internal_code  genus_url
    verdict  verdict_cn  confidence  note

`verdict` compares the supplied 科/目/纲 with Nemaplex:

    match        源表与 Nemaplex 一致
    corrected    源表与 Nemaplex 不一致，已按 Nemaplex 修正
    partial      部分一致（例如目一致但科不一致）
    not-found    Nemaplex 未收录该属
    unresolved   名称未解析（见 step 1），未做比对
    uncheckable  源表只给了中文科名/中文目名，无法逐字比对

Usage
-----
    python scripts/lookup.py --input out/normalized.json --out out/matched.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

CONF_RANK = {
    "exact": 0,
    "dictionary": 1,
    "cn-conflict": 2,
    "spelling-suspect": 3,
    "unresolved": 4,
}

VERDICT_CN = {
    "match": "一致",
    "corrected": "不一致，已按 Nemaplex 修正",
    "partial": "部分一致",
    "not-found": "Nemaplex 未收录",
    "unresolved": "名称未解析，未比对",
    "uncheckable": "源表未给拉丁科/目名，无法比对",
}

# Order -> classical class. Nemaplex's modern Rhabditida absorbs the classical
# Tylenchida / Aphelenchida / Diplogasterida / Strongylida / Ascaridida /
# Spirurida / Oxyurida, all of which sat in Secernentea (Chitwood 1958);
# every other modern order came from Adenophorea.
CLASSICAL_SECERNENTEA_ORDERS = {"Rhabditida"}

CLASS_ALIASES = {
    # modern
    "chromadorea": "Chromadorea", "色矛纲": "Chromadorea",
    "enoplea": "Enoplea", "刺嘴纲": "Enoplea",
    # classical - kept distinct, we report the difference rather than merging
    "adenophorea": "Adenophorea", "无尾感器纲": "Adenophorea",
    "secernentea": "Secernentea", "尾感器纲": "Secernentea",
}

CLASSICAL_EQUIV = {
    "Chromadorea": "Adenophorea",   # partly; see references/classification_systems.md
    "Enoplea": "Adenophorea",
    "Adenophorea": "Adenophorea",
    "Secernentea": "Secernentea",
}

HAS_CJK = re.compile(r"[\u4e00-\u9fff]")


def load_json(name: str):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# --------------------------------------------------------------------------- #
# Step 2: classification
# --------------------------------------------------------------------------- #

def build_family_lookup() -> tuple[dict, dict]:
    fam_map = load_json("family_order_class.json")
    by_norm = {norm_key(k): k for k in fam_map}
    return fam_map, by_norm


def attach_classification(rec: dict, fam_nem: str, fam_map: dict, by_norm: dict,
                          labels: dict) -> dict:
    """Fill class / subclass / order for a Nemaplex family name."""
    if not fam_nem:
        return rec
    key = fam_nem if fam_nem in fam_map else by_norm.get(norm_key(fam_nem))
    info = fam_map.get(key or "", {})
    rec["fam_nem"] = key or fam_nem
    rec["subcls_nem"] = info.get("subclass", "")
    rec["ord_nem"] = info.get("order", "")
    rec["cls_nem"] = info.get("class", "")
    rec["subord_nem"] = info.get("suborder", "")
    rec["superfam_nem"] = info.get("superfamily", "")
    rec["fam_breadcrumb"] = info.get("raw", "")

    orders = labels.get("orders", {})
    subcls = labels.get("subclasses", {})
    rec["cls_cn"] = labels.get("classes_modern", {}).get(rec["cls_nem"], "")
    rec["subcls_cn"] = subcls.get(rec["subcls_nem"], "")
    o = orders.get(rec["ord_nem"], {})
    rec["ord_cn"] = o.get("cn", "")
    rec["ord_cn_confidence"] = o.get("confidence", "")

    trad = "Secernentea" if rec["ord_nem"] in CLASSICAL_SECERNENTEA_ORDERS else (
        "Adenophorea" if rec["ord_nem"] else "")
    rec["cls_trad"] = trad
    rec["cls_trad_cn"] = labels.get("classes_classical", {}).get(trad, "")
    return rec


# --------------------------------------------------------------------------- #
# Step 3: functional guild
# --------------------------------------------------------------------------- #

def attach_guild(rec: dict, genus: dict, labels: dict) -> dict:
    typos = labels.get("source_typos", {})
    pf_map = labels.get("putative_feeding_cn", {})
    cp_map = labels.get("cp_classes", {})
    fg_map = labels.get("feeding_groups", {})
    letters = labels.get("guild_letters", {})

    pf = (genus.get("putative_feeding") or "").strip()
    pf = typos.get(pf, pf)
    rec["putative_feeding"] = pf
    rec["putative_feeding_cn"] = pf_map.get(pf, "")

    cp = (genus.get("cp") or "").strip()
    rec["cp"] = cp
    cpi = cp_map.get(cp, {})
    rec["cp_cn"] = cpi.get("cn", "")
    rec["cp_desc"] = cpi.get("desc", "")

    fg = (genus.get("feeding_group") or "").strip()
    rec["feeding_group"] = fg
    fgi = fg_map.get(fg, {})
    rec["feeding_group_cn"] = fgi.get("cn", "")
    rec["feeding_group_en"] = fgi.get("en", "")

    guild = (genus.get("functional_guild") or "").strip()
    rec["functional_guild"] = guild
    m = re.match(r"^([A-Za-z]+)\s*(\d?)$", guild)
    if m and m.group(1).lower() in letters:
        letter_cn = letters[m.group(1).lower()]
        num = m.group(2) or cp
        rec["functional_guild_cn"] = f"{letter_cn} c-p{num}" if num else letter_cn
        rec["guild_feed_cn"] = letter_cn
    else:
        rec["functional_guild_cn"] = ""
        rec["guild_feed_cn"] = ""

    rec["internal_code"] = genus.get("internal_code", "")
    if rec["internal_code"]:
        rec["genus_url"] = ("http://nemaplex.ucdavis.edu/Taxadata/"
                            f"{rec['internal_code']}.aspx")

    # A handful of genera sit in a family the genus index spells differently from
    # the classification table (typo, acknowledged variant, or a "A/B" dual
    # placement). The correction happened when the snapshot was built; carry the
    # explanation through so the report can show it instead of hiding it.
    rec["family_alternatives"] = genus.get("family_alternatives", [])
    rec["family_note"] = genus.get("family_note", "")
    return rec


# --------------------------------------------------------------------------- #
# verdict
# --------------------------------------------------------------------------- #

def latinise(name: str, table: dict) -> str:
    """If the supplied value is Chinese, try to map it back to a Latin name."""
    if not name or not HAS_CJK.search(name):
        return name
    for latin, cn in table.items():
        if cn and cn == name:
            return latin
    return ""


def compare(rec: dict, labels: dict) -> None:
    """Compare the supplied 科/目/纲 against Nemaplex.

    Two things are deliberately NOT reported as discrepancies:
      * a classical class name (Adenophorea / Secernentea) that matches the
        classical equivalent of the modern class;
      * a classical order (Tylenchida, Aphelenchida, ...) that the modern
        system folded into Rhabditida.
    Both are system conversions, and get a note instead of a red flag.
    """
    fam_in, ord_in, cls_in = rec.get("fam_in", ""), rec.get("ord_in", ""), rec.get("cls_in", "")
    ord_table = {k: v.get("cn", "") for k, v in labels.get("orders", {}).items()}
    classical_orders = {k for k, v in labels.get("orders", {}).items()
                        if v.get("system") == "classical"}

    if rec.get("family_note"):
        rec["note"] = (rec.get("note") + "；" if rec.get("note") else "") + rec["family_note"]
    if rec.get("family_alternatives"):
        alts = "、".join(rec["family_alternatives"])
        rec["fam_alt"] = alts
        rec["note"] = ((rec.get("note") + "；" if rec.get("note") else "")
                       + f"Nemaplex 属索引另标注该属可置于 {alts}")
    else:
        rec["fam_alt"] = ""

    if not rec.get("latin_nemaplex"):
        rec["verdict"] = "not-found" if not rec.get("latin") else "unresolved"
        rec["verdict_cn"] = VERDICT_CN[rec["verdict"]]
        return

    checks: list[tuple[str, bool, str]] = []
    uncheckable = False

    # --- 科 -----------------------------------------------------------------
    if fam_in and not HAS_CJK.search(fam_in):
        checks.append(("科", fam_in.lower() == (rec.get("fam_nem") or "").lower(), ""))
    elif fam_in:
        uncheckable = True

    # --- 目 -----------------------------------------------------------------
    ord_in_l = latinise(ord_in, ord_table)
    if ord_in and ord_in_l:
        if ord_in_l in classical_orders and rec.get("ord_nem") == "Rhabditida":
            checks.append(("目", True,
                           f"源表目名 {ord_in} 属经典体系，现代体系已并入 Rhabditida 小杆目"))
        else:
            checks.append(("目", ord_in_l.lower() == (rec.get("ord_nem") or "").lower(), ""))
    elif ord_in:
        uncheckable = True

    # --- 纲 -----------------------------------------------------------------
    cls_in_l = CLASS_ALIASES.get(cls_in.strip().lower(), cls_in.strip()) if cls_in else ""
    if cls_in_l:
        ok = cls_in_l == rec.get("cls_nem") or (
            cls_in_l in CLASSICAL_EQUIV and CLASSICAL_EQUIV[cls_in_l] == rec.get("cls_trad"))
        note = ""
        if cls_in_l in ("Adenophorea", "Secernentea") and ok:
            note = (f"源表纲名 {cls_in} 属经典体系，Nemaplex 现用 {rec.get('cls_nem')}"
                    f"（经典体系 {rec.get('cls_trad')}）")
        checks.append(("纲", ok, note))

    if not checks:
        rec["verdict"] = "uncheckable" if uncheckable else "match"
        rec["verdict_cn"] = VERDICT_CN[rec["verdict"]]
        return

    for _, _, note in checks:
        if note:
            rec["note"] = (rec["note"] + "；" if rec.get("note") else "") + note

    bad = [name for name, ok, _ in checks if not ok]
    if not bad:
        rec["verdict"] = "match"
    elif len(bad) == len(checks):
        rec["verdict"] = "corrected"
    else:
        rec["verdict"] = "partial"
    rec["verdict_cn"] = VERDICT_CN[rec["verdict"]]

    if bad:
        parts = []
        for name, ok, _ in checks:
            if ok:
                continue
            if name == "科":
                parts.append(f"科：源 {fam_in} → Nemaplex {rec.get('fam_nem')}")
            elif name == "目":
                parts.append(f"目：源 {ord_in} → Nemaplex {rec.get('ord_nem')}")
            else:
                parts.append(f"纲：源 {cls_in} → Nemaplex {rec.get('cls_nem')}"
                             f"（经典体系 {rec.get('cls_trad')}）")
        rec["note"] = (rec["note"] + "；" if rec.get("note") else "") + "；".join(parts)


def applies(rows: list[dict]) -> tuple[list[dict], dict]:
    genera = load_json("genus_index.json")
    lookup = {k.lower(): k for k in genera}
    index_keys = list(lookup.keys())
    labels = load_json("zh_cn_labels.json")
    fam_map, fam_by_norm = build_family_lookup()

    out = []
    for r in rows:
        rec = dict(r)
        for f in ("fam_nem", "subcls_nem", "ord_nem", "cls_nem", "subord_nem", "superfam_nem",
                  "fam_breadcrumb", "cls_cn", "subcls_cn", "ord_cn", "ord_cn_confidence",
                  "cls_trad", "cls_trad_cn", "cp", "cp_cn", "cp_desc", "feeding_group",
                  "feeding_group_cn", "feeding_group_en", "functional_guild",
                  "functional_guild_cn", "guild_feed_cn", "putative_feeding",
                  "putative_feeding_cn", "internal_code", "genus_url", "family_note",
                  "fam_alt"):
            rec.setdefault(f, "")
        # not a string: the genus-index family-normalisation trail
        rec.setdefault("family_alternatives", [])

        name = rec.get("latin") or ""
        key = lookup.get(name.lower())
        if not key and name:
            close = difflib.get_close_matches(name.lower(), index_keys, n=1, cutoff=0.9)
            key = lookup[close[0]] if close else None
        if key:
            rec["latin_nemaplex"] = key
            attach_classification(rec, genera[key].get("family", ""), fam_map, fam_by_norm, labels)
            attach_guild(rec, genera[key], labels)
        compare(rec, labels)
        out.append(rec)

    stats = {
        "rows": len(out),
        "with_classification": sum(1 for r in out if r["ord_nem"]),
        "with_cp": sum(1 for r in out if r["cp"]),
        "with_guild": sum(1 for r in out if r["functional_guild"]),
        "verdict": {},
        "confidence": {},
        "guild_distribution": {},
    }
    for r in out:
        stats["verdict"][r["verdict"]] = stats["verdict"].get(r["verdict"], 0) + 1
        stats["confidence"][r["confidence"]] = stats["confidence"].get(r["confidence"], 0) + 1
        g = r["functional_guild"]
        if g:
            stats["guild_distribution"][g] = stats["guild_distribution"].get(g, 0) + 1
    return out, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Match genera against the Nemaplex snapshot (steps 2+3).")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "matched.json"))
    args = ap.parse_args()

    for need in ("genus_index.json", "family_order_class.json", "zh_cn_labels.json"):
        if not os.path.exists(os.path.join(DATA, need)):
            print(f"data/{need} is missing - run scripts/build_snapshot.py first", file=sys.stderr)
            return 1

    with open(args.input, encoding="utf-8") as fh:
        rows = json.load(fh)
    out, stats = applies(rows)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(os.path.dirname(args.out), "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1)

    print(f"rows: {stats['rows']} -> {args.out}")
    print(f"  有分类归属: {stats['with_classification']}")
    print(f"  有 c-p 值:  {stats['with_cp']}")
    print(f"  有功能团:   {stats['with_guild']}")
    print("  判定分布: " + ", ".join(f"{k}={v}" for k, v in sorted(stats["verdict"].items())))
    print("  置信分布: " + ", ".join(f"{k}={v}" for k, v in
                                    sorted(stats["confidence"].items(), key=lambda x: CONF_RANK.get(x[0], 99))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
