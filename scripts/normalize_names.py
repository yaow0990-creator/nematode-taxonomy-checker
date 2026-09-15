#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 1 of the pipeline: turn a name-only table into resolvable Latin genus names.

Input
-----
A CSV/XLSX whose columns may be some subset of:
    中文名 | 拉丁名 | 科 | 目 | 纲
Only 中文名 and/or 拉丁名 are required. Rows that also carry 科/目/纲 are
passed through untouched so step 2 can check them.

What it does
------------
1.  Latin name given      -> normalise, verify against the Nemaplex genus index.
                             If absent, propose near matches (difflib) and mark
                             the row as a suspected spelling error.
2.  Chinese name given    -> resolve through the Chinese-name dictionary.
                             Nemaplex has no Chinese names at all, so this
                             mapping is NOT something the site can supply: it is
                             whatever the user brings. Supply your own with
                             --cn-dict (see "Chinese-name dictionary" below).
3.  Unresolved Chinese    -> written to <outdir>/needs_cn_mapping.csv in exactly
                             the dictionary file layout, so you fill in the
                             `latin` column and hand the same file straight back
                             with --cn-dict. Nothing is invented here.
4.  Both given            -> cross-checked; disagreement is flagged rather than
                             silently overwritten.

Every row gets a `confidence` label. Anything below `dictionary` is a
proposal, not a fact, and is surfaced in the output as 待人工确认.

Chinese-name dictionary
-----------------------
Three layers, lowest to highest priority:

1.  data/cn_latin_genus.json   the small seed shipped with the skill
2.  auto-discovered file       "<input-stem>.dict.csv", "cn_dict.csv" or
                               "中文名字典.csv" sitting next to the input file
3.  --cn-dict PATH             explicit, repeatable, wins over everything

Layers 2 and 3 accept CSV/XLSX (columns 中文名/cn and 拉丁名/latin, optional
aliases/confidence/source) as well as the compiled JSON format. A later layer
overrides an earlier one for the same Chinese name, so a user's own verdict
always beats the seed.

Usage
-----
    python scripts/normalize_names.py --input names.csv --out out/normalized.json
    python scripts/normalize_names.py --input table.xlsx --sheet Sheet1
    python scripts/normalize_names.py --input names.csv --cn-dict my_dict.csv
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

CN_KEYS = ["中文名", "中文属名", "中文", "chinese", "cn", "name_cn"]
LAT_KEYS = ["拉丁名", "拉丁属名", "属名", "拉丁", "latin", "genus", "name_latin"]
FAM_KEYS = ["科", "科名", "科拉丁", "family"]
ORD_KEYS = ["目", "目名", "order"]
CLS_KEYS = ["纲", "纲名", "class"]

# Dictionary files use the same column families, plus a couple of aliases that
# only ever show up in hand-maintained sheets.
DICT_CN_KEYS = CN_KEYS + ["中文名（可留空）"]
DICT_LAT_KEYS = LAT_KEYS + ["latin_proposed", "拉丁名（请填写）"]

DICT_AUTO_NAMES = ["cn_dict.csv", "cn_dict.xlsx", "中文名字典.csv", "中文名字典.xlsx",
                   "cn_latin.csv", "cn_latin.xlsx"]

CONF_RANK = {
    "exact": 0,
    "dictionary": 1,
    "cn-conflict": 2,
    "spelling-suspect": 3,
    "unresolved": 4,
}


def load_json(name: str):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def norm_latin(s: str) -> str:
    s = (s or "").strip().strip(".").replace("　", " ")
    s = re.sub(r"\s+", " ", s)
    return s[:1].upper() + s[1:] if s else s


def norm_cn(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    return s[:-1] if s.endswith("属") else s


def pick(row: dict, keys: list[str]) -> str:
    lowered = {re.sub(r"\s+", "", str(k)).lower(): v for k, v in row.items() if k is not None}
    for k in keys:
        v = lowered.get(re.sub(r"\s+", "", k).lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def read_rows(path: str, sheet: str | None = None) -> list[dict]:
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook  # optional dependency
        wb = load_workbook(path, data_only=True)
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        header = [c.value for c in ws[1]]
        out = []
        for r in ws.iter_rows(min_row=2, values_only=True):
            if all(v in (None, "") for v in r):
                continue
            out.append({header[i]: r[i] for i in range(min(len(header), len(r)))})
        return out
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_user_dict(path: str) -> dict[str, dict]:
    """Read one user-supplied Chinese-name dictionary.

    Accepts the compiled JSON form ({"entries": {...}}) or a flat CSV/XLSX with
    中文名/cn + 拉丁名/latin columns. Rows without a Latin name are skipped:
    they are still-unanswered entries, not data.
    """
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        entries = payload.get("entries", payload) if isinstance(payload, dict) else {}
        out: dict[str, dict] = {}
        for k, v in entries.items():
            if isinstance(v, dict) and v.get("latin"):
                out[norm_cn(k)] = {
                    "cn_full": v.get("cn_full", k),
                    "latin": v["latin"],
                    "aliases": v.get("aliases") or [],
                    "confidence": v.get("confidence", "user-supplied"),
                    "source": v.get("source", ""),
                }
        return out

    out = {}
    for row in read_rows(path):
        cn = pick(row, DICT_CN_KEYS)
        latin = pick(row, DICT_LAT_KEYS)
        if not cn or not latin:
            continue
        key = norm_cn(cn)
        out[key] = {
            "cn_full": cn,
            "latin": norm_latin(latin),
            "aliases": [a.strip() for a in re.split(r"[;；,，]", str(row.get("aliases") or "")) if a.strip()],
            "confidence": (str(row.get("confidence") or "").strip() or "user-supplied"),
            "source": str(row.get("source") or "").strip(),
        }
    return out


def discover_dicts(input_path: str, extra: list[str]) -> list[str]:
    """Auto-found dictionaries next to the input file, then explicit --cn-dict.

    Order matters: resolve() merges in sequence, so the returned order is the
    override order (last wins).
    """
    found: list[str] = []
    d = os.path.dirname(os.path.abspath(input_path))
    stem = os.path.splitext(os.path.basename(input_path))[0]
    for name in [f"{stem}.dict.csv", f"{stem}.dict.xlsx"] + DICT_AUTO_NAMES:
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            found.append(cand)
    for p in extra:
        ap = os.path.abspath(p)
        if not os.path.exists(ap):
            raise SystemExit(f"--cn-dict 指定的文件不存在: {p}")
        found.append(ap)
    return found


def resolve(rows: list[dict], fuzzy_cutoff: float = 0.86,
            dict_paths: list[str] | None = None) -> tuple[list[dict], list[dict], dict[str, int]]:
    genera = load_json("genus_index.json")
    cn_dict = dict(load_json("cn_latin_genus.json")["entries"])
    origins = {"seed": len(cn_dict)}

    for p in dict_paths or []:
        user = load_user_dict(p)
        for k in user:
            origins[p] = origins.get(p, 0) + 1
        for v in user.values():
            v["layer"] = os.path.basename(p)
        cn_dict.update(user)          # user always overrides the seed
    for v in cn_dict.values():
        v.setdefault("layer", "seed")

    # Alternates are the same genus under another Chinese name - register them
    # as keys too, so "松材线虫属" reaches the entry filed under "伞滑刃属".
    # Never overwrite a real entry with an alias.
    for key, entry in list(cn_dict.items()):
        for a in entry.get("aliases") or []:
            k = norm_cn(a)
            if k and k not in cn_dict:
                cn_dict[k] = entry
    lookup = {k.lower(): k for k in genera}
    index_keys = list(lookup.keys())

    out: list[dict] = []
    unresolved: list[dict] = []

    for i, row in enumerate(rows, start=1):
        cn_in = pick(row, CN_KEYS)
        lat_in = pick(row, LAT_KEYS)
        rec = {
            "no": i,
            "cn_in": cn_in,
            "latin_in": lat_in,
            "latin": "",
            "latin_nemaplex": "",
            "confidence": "unresolved",
            "cn_dict_layer": "",
            "note": "",
            "fam_in": pick(row, FAM_KEYS),
            "ord_in": pick(row, ORD_KEYS),
            "cls_in": pick(row, CLS_KEYS),
        }

        # --- 1. Latin name supplied: verify directly -------------------------
        if lat_in:
            cand = norm_latin(lat_in)
            hit = lookup.get(cand.lower())
            if hit:
                rec["latin"] = rec["latin_nemaplex"] = hit
                rec["confidence"] = "exact"
            else:
                close = difflib.get_close_matches(cand.lower(), index_keys, n=3, cutoff=fuzzy_cutoff)
                if close:
                    best = lookup[close[0]]
                    rec["latin"] = best
                    rec["latin_nemaplex"] = best
                    rec["confidence"] = "spelling-suspect"
                    rec["note"] = (f"拉丁名 {cand} 未收录，疑似拼写错误；"
                                   f"最接近 {best}"
                                   + (f"，其他候选：{', '.join(lookup[c] for c in close[1:])}" if len(close) > 1 else ""))
                else:
                    rec["latin"] = cand
                    rec["confidence"] = "unresolved"
                    rec["note"] = f"拉丁名 {cand} 未收录于 Nemaplex，且无相近候选"

        # --- 2./3. Chinese name: resolve through the dictionary layers -------
        if cn_in:
            entry = cn_dict.get(norm_cn(cn_in))
            if entry:
                dict_latin = entry["latin"]
                rec["cn_dict_layer"] = entry.get("layer", "")
                if rec["latin"] and rec["latin"].lower() != dict_latin.lower():
                    rec["confidence"] = "cn-conflict"
                    rec["note"] = (rec["note"] + "；" if rec["note"] else "") + \
                        f"中文名对应字典值为 {dict_latin}，与表内拉丁名不一致，请人工裁决"
                else:
                    rec["latin"] = dict_latin
                    if not rec["latin_nemaplex"]:
                        rec["latin_nemaplex"] = lookup.get(dict_latin.lower(), dict_latin)
                    if rec["confidence"] in ("unresolved",):
                        rec["confidence"] = "dictionary"
                    if entry.get("confidence") == "seed-unresolved":
                        rec["note"] = (rec["note"] + "；" if rec["note"] else "") + \
                            "该属在 Nemaplex 中无对应记录（种子标为未解决）"
            else:
                if not rec["latin"]:
                    rec["note"] = f"中文名「{cn_in}」不在字典中，需人工补拉丁名"
                else:
                    rec["note"] = (rec["note"] + "；" if rec["note"] else "") + \
                        f"中文名「{cn_in}」不在字典中，已按表内拉丁名处理"
                # Anything that did not reach `exact` still needs the Chinese
                # name mapped by hand - the Latin name is not trustworthy either.
                if rec["confidence"] != "exact":
                    unresolved.append({
                        "no": i, "cn": cn_in, "latin_in_table": lat_in,
                        "note": "字典未收录" + ("，拉丁名未在 Nemaplex 命中" if lat_in else ""),
                    })

        if not rec["latin"] and not cn_in and not lat_in:
            rec["note"] = "空行或名称列缺失"
        out.append(rec)

    return out, unresolved, origins


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalise nematode genus names (step 1).")
    ap.add_argument("--input", required=True)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "normalized.json"))
    ap.add_argument("--cutoff", type=float, default=0.86)
    ap.add_argument("--cn-dict", action="append", default=[], metavar="PATH",
                    help="user-supplied 中文名->拉丁名 dictionary (CSV/XLSX/JSON), "
                         "repeatable; later files override earlier ones")
    args = ap.parse_args()

    if not os.path.exists(os.path.join(DATA, "genus_index.json")):
        print("data/genus_index.json is missing - run scripts/build_snapshot.py first", file=sys.stderr)
        return 1

    dict_paths = discover_dicts(args.input, args.cn_dict)
    rows = read_rows(args.input, args.sheet)
    resolved, unresolved, origins = resolve(rows, args.cutoff, dict_paths)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(resolved, fh, ensure_ascii=False, indent=1)

    # Written in the dictionary file layout on purpose: fill the `latin` column
    # and pass this very file back with --cn-dict on the next run.
    pending = os.path.join(os.path.dirname(args.out), "needs_cn_mapping.csv")
    if unresolved:
        with open(pending, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["cn", "latin", "aliases", "confidence",
                                               "source", "latin_in_table", "note", "no"])
            w.writeheader()
            for u in unresolved:
                w.writerow({
                    "cn": u["cn"], "latin": "", "aliases": "",
                    "confidence": "user-supplied", "source": "",
                    "latin_in_table": u.get("latin_in_table", ""),
                    "note": u["note"], "no": u["no"],
                })

    counts: dict[str, int] = {}
    for r in resolved:
        counts[r["confidence"]] = counts.get(r["confidence"], 0) + 1
    print(f"rows: {len(resolved)} -> {args.out}")
    for k in sorted(counts, key=lambda x: CONF_RANK.get(x, 99)):
        print(f"  {k}: {counts[k]}")
    print(f"中文字典: seed={origins.get('seed', 0)}" +
          ("".join(f" + {os.path.basename(p)}={origins[p]}" for p in dict_paths) if dict_paths
           else "  (未加载外部字典，可用 --cn-dict 指定)"))
    if unresolved:
        print(f"\n待补中文名映射: {len(unresolved)} -> {pending}")
        print(f"  在 latin 列填好后直接重跑："
              f"  python scripts/run_pipeline.py --input {args.input} --cn-dict \"{pending}\"")
    flagged = [r for r in resolved if r["confidence"] in ("spelling-suspect", "cn-conflict", "unresolved")]
    if flagged:
        print("需人工确认的行:")
        for r in flagged[:20]:
            print(f"  [{r['no']}] {r['cn_in']} / {r['latin_in']} -> {r['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
