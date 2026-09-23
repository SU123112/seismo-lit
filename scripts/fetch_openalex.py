# -*- coding: utf-8 -*-
"""
第 1 步：从 OpenAlex 抓取 Science / Nature / Nature Geoscience 上的地震学相关文献。

OpenAlex 是免费开放的学术元数据 API（无需 Key，注册邮箱可获得更快的 "polite pool"）。
数据来源覆盖 Crossref、PubMed 等，含标题 / 摘要 / 作者 / DOI / 引用数 / 开放获取状态。

用法：
    python fetch_openalex.py                 # 抓取全部期刊
    python fetch_openalex.py --journal science
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://api.openalex.org/works"
MAILTO = os.environ.get("OPENALEX_MAILTO", "seismo-lit@example.com")

# ---------------------------------------------------------------- 期刊配置
# 想扩展期刊，只需在这里加一行（ISSN 可在 https://openalex.org/sources 查）
JOURNALS = {
    "science": {"name": "Science", "issn": "0036-8075"},
    "nature": {"name": "Nature", "issn": "0028-0836"},
    "nature-geoscience": {"name": "Nature Geoscience", "issn": "1752-0894"},
    # 可选扩展（默认不抓，要的话去掉注释）：
    # "science-advances": {"name": "Science Advances", "issn": "2375-2548"},
    # "nature-communications": {"name": "Nature Communications", "issn": "2041-1723"},
    # "nature-reviews-ee": {"name": "Nature Reviews Earth & Environment", "issn": "2662-138X"},
}

# ---------------------------------------------------------------- 检索词
# 第一阶段"宽召回"：只要标题或摘要命中任一关键词就取回来，
# 精确性交给第 2 步的本地打分过滤（宁可多抓，不可漏抓）。
SEARCH_TERMS = [
    "earthquake", "earthquakes", "seismic", "seismology", "seismological",
    "seismicity", "seismogenic", "seismogram", "seismometer", "seismograph",
    "aftershock", "foreshock", "hypocenter", "epicenter",
    "focal mechanism", "moment tensor", "seismic tomography",
    "seismic hazard", "seismic wave", "ground motion", "seismic velocity",
    "seismic anisotropy", "receiver function", "ambient noise",
    "slow slip", "seismic tremor", "megathrust", "earthquake rupture",
    "induced seismicity", "marsquake", "moonquake", "earthquake early warning",
    "fault slip", "core-mantle boundary", "inner core", "seismic imaging",
    "seismic array", "subduction zone earthquake",
]

SELECT = ",".join([
    "id", "doi", "title", "display_name", "publication_year", "publication_date",
    "type", "authorships", "cited_by_count", "open_access",
    "primary_location", "abstract_inverted_index",
    "primary_topic",     # 主主题
    "topics",            # 全部主题（含置信度，用于分类）
    "keywords",          # OpenAlex 抽取的主题词（含置信度）
    "referenced_works_count", "is_retracted",
])


def http_json(url, retries=4):
    """带重试的 GET，返回解析后的 JSON。"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": f"seismo-lit/1.0 (mailto:{MAILTO})",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:                       # noqa: BLE001
            wait = 2 ** attempt
            print(f"    [重试 {attempt + 1}/{retries}] {exc} -> {wait}s 后重试", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"请求失败：{url}")


def fetch_journal(key, cfg, out_path, page_size=200):
    """按游标分页抓取单个期刊的全部命中记录。"""
    search = "|".join(f'"{t}"' if " " in t else t for t in SEARCH_TERMS)
    flt = f"primary_location.source.issn:{cfg['issn']},title_and_abstract.search:{search}"

    params = urllib.parse.urlencode({
        "filter": flt,
        "per-page": page_size,
        "select": SELECT,
        "mailto": MAILTO,
    }, safe="|:,\"'")
    url = f"{API}?{params}&cursor=*"

    records, cursor, page = [], "*", 0
    total = None
    while cursor:
        data = http_json(url.replace("cursor=*", "cursor=" + urllib.parse.quote(cursor)))
        if total is None:
            total = data["meta"]["count"]
            print(f"  {cfg['name']}: 命中 {total} 条，开始抓取…")
        records.extend(data.get("results", []))
        page += 1
        print(f"    第 {page} 页，累计 {len(records)}/{total}")
        cursor = data["meta"].get("next_cursor")
        if not data.get("results"):
            break
        time.sleep(0.25)                                # 对 API 友好一点

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False)
    print(f"  ✓ {cfg['name']} 已保存 {len(records)} 条 -> {out_path}")
    return len(records)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    raw_dir = os.path.join(here, "..", "data", "raw")
    os.makedirs(raw_dir, exist_ok=True)

    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="all", help="science / nature / nature-geoscience / all")
    args = ap.parse_args()

    targets = JOURNALS if args.journal == "all" else {args.journal: JOURNALS[args.journal]}
    grand = 0
    for key, cfg in targets.items():
        out = os.path.join(raw_dir, f"{key}.json")
        grand += fetch_journal(key, cfg, out)
    print(f"\n完成，共抓取 {grand} 条原始记录。")


if __name__ == "__main__":
    main()
