#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot entry point: names in -> verified table out.

Runs the four pipeline steps in order.

    input table (中文名 / 拉丁名，可带 科 目 纲)
        -> 1. normalize_names.py   名称归一化 + 中文名查字典
        -> 2. lookup.py            分类匹配（科/目/纲）+ 功能团匹配
        -> 3. export.py            Excel + HTML

Usage
-----
    python scripts/run_pipeline.py --input names.csv
    python scripts/run_pipeline.py --input table.xlsx --sheet Sheet1 --outdir out
    python scripts/run_pipeline.py --input names.csv --skip-normalize   # reuse out/normalized.json

Chinese names are not in Nemaplex at all - bring your own 中文名->拉丁名 table:

    python scripts/run_pipeline.py --input names.csv --cn-dict 我的中文名字典.csv

Or drop a file named `cn_dict.csv` / `中文名字典.csv` next to the input and it is
picked up on its own. Whatever is missing ends up in <outdir>/needs_cn_mapping.csv
in the same layout - fill the `latin` column and pass that file straight back.

The intermediate JSON stays in <outdir>/ so a single step can be re-run without
redoing the rest.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))


def run(script: str, extra: list[str]) -> float:
    cmd = [sys.executable, os.path.join(HERE, script)] + extra
    t0 = time.time()
    print(f"\n=== {script} ===", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode:
        print(f"!! {script} exited with {proc.returncode}", file=sys.stderr)
        raise SystemExit(proc.returncode)
    return time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the full nematode taxonomy pipeline.")
    ap.add_argument("--input", required=True, help="CSV or XLSX with 中文名 and/or 拉丁名")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--outdir", default=os.path.join(ROOT, "out"))
    ap.add_argument("--cutoff", type=float, default=0.86)
    ap.add_argument("--cn-dict", action="append", default=[], metavar="PATH",
                    help="user-supplied 中文名->拉丁名 dictionary (CSV/XLSX/JSON), "
                         "repeatable; later files override earlier ones. "
                         "A file named cn_dict.csv / 中文名字典.csv next to the "
                         "input is picked up automatically.")
    ap.add_argument("--skip-normalize", action="store_true")
    ap.add_argument("--no-html", action="store_true")
    args = ap.parse_args()

    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    normalized = os.path.join(outdir, "normalized.json")
    matched = os.path.join(outdir, "matched.json")

    if not os.path.exists(os.path.join(ROOT, "data", "genus_index.json")):
        print("data/genus_index.json is missing.\n"
              "Run scripts/build_snapshot.py once to build the offline snapshot "
              "(roughly 300 requests to nemaplex.ucdavis.edu).", file=sys.stderr)
        return 1

    if not args.skip_normalize:
        run("normalize_names.py", ["--input", args.input, "--out", normalized,
                                   "--cutoff", str(args.cutoff)]
            + (["--sheet", args.sheet] if args.sheet else [])
            + [x for p in args.cn_dict for x in ("--cn-dict", p)])
    run("lookup.py", ["--input", normalized, "--out", matched])
    run("export.py", ["--input", matched,
                      "--xlsx", os.path.join(outdir, "线虫分类核查结果.xlsx"),
                      "--html", os.path.join(outdir, "report.html")]
        + (["--no-html"] if args.no_html else []))

    # roll the human-review list into the output directory
    src = os.path.join(outdir, "needs_cn_mapping.csv")
    if os.path.exists(src):
        with open(matched, encoding="utf-8") as fh:
            data = json.load(fh)
        pend = [r for r in data if r.get("confidence") == "unresolved" and r.get("cn_in")]
        if pend:
            print(f"\n{len(pend)} 行的中文名还缺拉丁名对应，见 {src}")
            print("  在该文件的 latin 列填好后，直接把同一个文件当字典传回来重跑：")
            print(f"  python scripts/run_pipeline.py --input \"{args.input}\" "
                  f"--cn-dict \"{src}\"")

    print(f"\n全部产物在 {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
