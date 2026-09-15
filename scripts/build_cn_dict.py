#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile data/cn_latin_seed.csv into data/cn_latin_genus.json.

Why a separate compile step
---------------------------
Chinese genus names are NOT available on Nemaplex (the site is Latin/English
only). The Chinese-to-Latin mapping is therefore a curated asset that has to be
maintained by hand. Keeping it as a CSV makes it reviewable in Excel; this
script turns it into a lookup table with normalised keys.

Key normalisation
-----------------
Both "伪垫刃属" and "伪垫刃" resolve to the same entry, so a table written with
or without the trailing 属 still matches. Latin keys are case-insensitive.

Usage
-----
    python scripts/build_cn_dict.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "cn_latin_seed.csv")
JSON_PATH = os.path.join(ROOT, "data", "cn_latin_genus.json")


def norm_cn(name: str) -> str:
    """Strip whitespace and a trailing 属 so both forms match."""
    s = re.sub(r"\s+", "", name or "")
    if s.endswith("属"):
        s = s[:-1]
    return s


def main() -> int:
    if not os.path.exists(CSV_PATH):
        print(f"missing {CSV_PATH}", file=sys.stderr)
        return 1

    entries: dict[str, dict] = {}
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            cn = (row.get("cn") or "").strip()
            latin = (row.get("latin") or "").strip()
            if not cn or not latin:
                continue
            aliases = [a.strip() for a in (row.get("aliases") or "").split(";") if a.strip()]
            conf = (row.get("confidence") or "curated").strip()
            source = (row.get("source") or "").strip()
            key = norm_cn(cn)
            entries.setdefault(key, {
                "cn_full": cn,
                "latin": latin,
                "aliases": aliases,
                "confidence": conf,
                "source": source,
            })
            # the bare stem is an extra alias of the same entry
            if key != cn:
                entries[key]["also_written_as"] = cn

    payload = {
        "_note": "中文属名 -> 拉丁属名 字典。由 scripts/build_cn_dict.py 从 cn_latin_seed.csv 编译。"
                 "confidence=seed-verified 表示人工核对过；任何由模型推断补充的条目必须标 "
                 "model-proposed 并在使用前人工确认。",
        "_count": len(entries),
        "entries": entries,
    }
    with open(JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    by_conf: dict[str, int] = {}
    for v in entries.values():
        by_conf[v["confidence"]] = by_conf.get(v["confidence"], 0) + 1
    print(f"{JSON_PATH}: {len(entries)} entries")
    for k, v in sorted(by_conf.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
