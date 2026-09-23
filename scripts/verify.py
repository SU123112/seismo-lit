# -*- coding: utf-8 -*-
"""
第 3 步（质检用，可选）：抽样检查分类与过滤质量。

用法：
    python verify.py              # 概览 + 每类随机抽 3 条
    python verify.py --sample 5   # 每类抽 5 条
    python verify.py --search 汶川
"""
import argparse
import json
import os
import random
from collections import Counter

NAME = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=3)
    ap.add_argument("--search", default="")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.abspath(os.path.join(here, "..", "data", "papers.json"))
    with open(path, encoding="utf-8") as fh:
        papers = json.load(fh)

    with open(os.path.abspath(os.path.join(here, "..", "web", "data.js")), encoding="utf-8") as fh:
        head = fh.readline()
        for line in fh:
            if line.startswith("window.META"):
                meta = json.loads(line[len("window.META = "):].rstrip().rstrip(";"))
                break
    for c in meta["categories"]:
        NAME[c["id"]] = c["name"]

    if args.search:
        key = args.search.lower()
        hits = [p for p in papers if key in (p["title"] + p["abstract"]).lower()]
        print(f"命中 “{args.search}”：{len(hits)} 篇\n")
        for p in hits[:20]:
            print(f"  [{p['year']}] {p['journal']:18s} {p['title'][:95]}")
        return

    print(f"总计 {len(papers)} 篇\n")
    print("== 期刊 ==")
    for j, n in Counter(p["journal"] for p in papers).most_common():
        print(f"  {j:20s} {n:5d}")
    print("\n== 主类目 ==")
    for c, n in Counter(p["cat"] for p in papers).most_common():
        print(f"  {NAME.get(c, c):26s} {n:5d}")
    print("\n== 年份（近 15 年）==")
    yrs = Counter(p["year"] for p in papers if p["year"])
    for y in sorted(yrs)[-15:]:
        print(f"  {y}  {'█' * max(1, yrs[y] // 8)} {yrs[y]}")

    rnd = random.Random(args.seed)
    print(f"\n\n========== 每类随机抽 {args.sample} 条（人工核对分类是否合理） ==========")
    by = {}
    for p in papers:
        by.setdefault(p["cat"], []).append(p)
    for c, items in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"\n--- {NAME.get(c, c)}  ({len(items)} 篇) ---")
        for p in rnd.sample(items, min(args.sample, len(items))):
            print(f"  [{p['year']}] {p['journal']:17s} {p['title'][:88]}")
            print(f"        标签: {' / '.join(NAME.get(x, x) for x in p['cats'])}")


if __name__ == "__main__":
    main()
