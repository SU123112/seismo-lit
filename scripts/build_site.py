# -*- coding: utf-8 -*-
"""
第 2 步：清洗 + 地震学主题分类 + 生成网站数据。

⚠ 关键背景：Nature / Science 约 74% 的文章在 OpenAlex 上没有摘要
   （出版商未向 Crossref 提交摘要），因此不能只靠摘要做关键词分类。
   本脚本采用「三层信号」联合打分：

     ① 标题关键词      —— 权重 ×3（所有文章都有标题，最可靠）
     ② 摘要关键词      —— 权重 ×1（仅约 1/4 文章有摘要）
     ③ OpenAlex 主题词 —— 权重 ×2（topic / keywords，覆盖 100% 文章）

用法：
    python build_site.py                  # 生成网站数据
    python build_site.py --dump-dropped   # 额外导出被过滤掉的样本，便于核对
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date

# =====================================================================
# 一、相关性判定：剔除"蹭词"的非地震学文章
# =====================================================================
CORE = [
    r"earthquakes?", r"seismic", r"seismolog\w*", r"seismicit\w*", r"seismogenic",
    r"seismograms?", r"seismometers?", r"seismographs?", r"aftershocks?", r"foreshocks?",
    r"hypocent\w+", r"epicent\w+", r"focal mechanisms?", r"moment tensors?",
    r"marsquakes?", r"moonquakes?", r"megathrust", r"receiver functions?",
    r"slow slip", r"seismic tremor", r"tectonic tremor", r"earthquake rupture",
    r"ground motions?", r"seismic hazard", r"seismic tomography", r"earthquake early warning",
    r"subduction zone earthquake", r"tectonic tremor",
]
CORE_RE = re.compile("|".join(CORE), re.I)

NEGATIVE = [
    r"seismic (shift|change|shake-?up)\b(?!.*(earthquake|fault|wave))",
    r"political earthquake",
]


def is_seismology(title, abstract, topic_text):
    """判定是否真的属于地震学：标题命中 / 摘要+主题词合计命中 ≥2 个不同信号。"""
    for pat in NEGATIVE:
        if re.search(pat, title or "", re.I):
            return False
    t_hits = len(set(m.group(0).lower() for m in CORE_RE.finditer(title or "")))
    a_hits = len(set(m.group(0).lower() for m in CORE_RE.finditer(abstract or "")))
    p_hits = len(set(m.group(0).lower() for m in CORE_RE.finditer(topic_text or "")))
    return t_hits >= 1 or (a_hits + p_hits) >= 2


# =====================================================================
# 二、分类体系（12 类，支持多标签）
# =====================================================================
CATEGORIES = [
    {
        "id": "source", "name": "震源物理与破裂过程",
        "desc": "震源参数、断层破裂动力学、应力降、超剪切破裂、实验室地震",
        "keywords": {
            r"focal mechanism": 6, r"moment tensor": 6, r"source time function": 6,
            r"rupture (directivity|velocity|front|propagation|dynamics)": 6,
            r"dynamic rupture": 6, r"supershear": 6, r"stress drop": 5,
            r"earthquake source": 6, r"source (parameter|inversion|model)": 4,
            r"radiated energy": 5, r"slip (distribution|inversion|patch|deficit)": 4,
            r"corner frequency": 5, r"earthquake nucleation": 6, r"rupture": 3,
            r"seismic moment": 5, r"asperit\w+": 4, r"earthquake cycle": 5,
            r"frictional (rupture|sliding|motion|instabilit)": 5, r"laboratory earthquake": 6,
            r"source (depth|mechanism|scaling)": 4, r"brittle failure": 3,
            r"fault roughness|nucleation of": 4, r"foreshock.*(nucleat|precursor)": 5,
        },
    },
    {
        "id": "structure", "name": "地球内部结构与地震成像",
        "desc": "层析成像、接收函数、面波、各向异性、核幔边界、岩石圈结构",
        "keywords": {
            r"tomograph\w+": 6, r"receiver function": 7, r"surface wave": 5,
            r"body wave": 4, r"anisotrop\w+": 4, r"shear[- ]wave splitting": 5,
            r"low[- ]velocity (zone|layer|anomal)": 5, r"core[- ]mantle boundary": 7,
            r"inner core": 7, r"outer core": 6, r"mantle": 4, r"discontinuity": 5,
            r"seismic velocity": 4, r"velocity (model|structure)": 4,
            r"crustal (structure|thickness|root)": 5, r"moho": 6,
            r"lithospher\w+": 5, r"attenuation": 3, r"seismic scatter\w*": 4,
            r"full[- ]waveform inversion": 6, r"seismic imaging": 6, r"ambient noise": 5,
            r"seismic wave": 5, r"reflection (seismic|profile|image)": 4,
            r"deep earth|earth'?s interior": 6, r"normal mode": 6, r"wave propagation": 4,
            r"seismic (data|record)\w*": 3, r"array (analysis|technique)": 3,
        },
    },
    {
        "id": "tectonics", "name": "断层活动、构造变形与大地测量",
        "desc": "断层带、板块边界、俯冲带、GPS/InSAR 形变、震间闭锁与应变累积",
        "keywords": {
            r"fault (zone|system|scarp|geometry|slip|structure|valley)": 5,
            r"plate boundary": 6, r"subduction": 5, r"transform fault": 6,
            r"mid[- ]ocean ridge": 5, r"rifting|rift (zone|valley|system)": 5,
            r"strike[- ]slip": 5, r"thrust fault": 5, r"normal fault": 4,
            r"tectonic": 3, r"geodetic|geodesy": 4, r"insar": 6, r"interseismic": 7,
            r"locking|coupling": 3, r"strain (accumulation|rate|localization)": 4,
            r"surface deformation|crustal deformation": 5, r"continental collision": 5,
            r"fault (creep|friction|maturity|reactivat)": 4, r"kinematic": 3,
            r"slip rate": 5, r"migration of (deformation|strain)": 3, r"orogen": 4,
        },
    },
    {
        "id": "catalog", "name": "地震目录与统计地震学",
        "desc": "余震序列、b 值、ETAS 模型、震级-频度关系、地震丛集与复发规律",
        "keywords": {
            r"aftershock": 6, r"foreshock": 5, r"b[- ]value": 7,
            r"gutenberg[- ]richter": 7, r"\bETAS\b": 7, r"clustering": 4,
            r"magnitude[- ]frequency": 6, r"earthquake catalog\w*": 6, r"declustering": 7,
            r"omori": 6, r"recurrence (interval|time)": 5, r"mainshock": 6,
            r"earthquake swarm": 6, r"seismicity (pattern|rate|sequence|migration)": 5,
            r"earthquake (statistic|forecast|predict|probability)": 6, r"seismicity": 4,
            r"catalog(ue)?": 3, r"earthquake sequence": 5, r"temporal (clustering|pattern)": 3,
        },
    },
    {
        "id": "induced", "name": "诱发地震与流体作用",
        "desc": "注水、页岩气、水库、地热、采矿诱发地震，孔隙压与断层活化",
        "keywords": {
            r"induced seismicity": 9, r"injection[- ]induced": 8, r"wastewater": 5,
            r"hydraulic fracturing|fracking": 7, r"reservoir[- ]induced": 8,
            r"geothermal": 5, r"mining[- ]induced": 6, r"pore (pressure|fluid)": 5,
            r"anthropogenic": 4, r"(carbon capture|CO2 storage)": 4,
            r"fluid (injection|migration|pressure)": 6, r"fault (reactivation|activation)": 6,
            r"induced earthquake": 9, r"fluid injection": 7, r"aquifer (injection|recharge)": 4,
            r"seismicity (induced|triggered) by": 8, r"depletion[- ]induced": 6,
        },
    },
    {
        "id": "hazard", "name": "地震灾害、地震动与工程抗震",
        "desc": "地震危险性、地震动预测、场地效应、液化、滑坡与灾害损失评估",
        "keywords": {
            r"seismic hazard": 8, r"hazard (assessment|map|model|analysis)": 5,
            r"ground motion": 7, r"\bGMPE\b|ground[- ]motion (model|prediction|simulation)": 7,
            r"peak ground": 7, r"macroseismic|intensity (map|scale)": 4, r"shaking": 4,
            r"liquefaction": 7, r"earthquake[- ](induced |triggered )?(landslide|collapse|avalanche)": 6,
            r"structural damage|building (damage|collapse|response)": 5,
            r"seismic (risk|design|code|vulnerability|resistance|performance)": 6,
            r"site (effect|amplification|response)": 5, r"casualt\w+|fatalit\w+": 4,
            r"tsunami hazard": 3, r"loss (estimation|model|assessment)": 4,
            r"resilience": 3, r"earthquake (impact|damage|disaster|destruction)": 5,
            r"seismic retrofit|earthquake engineering": 7, r"sediment flux|riverbed": 3,
        },
    },
    {
        "id": "warning", "name": "地震预警与实时监测",
        "desc": "地震预警系统、实时处理、快速响应与自动检测",
        "keywords": {
            r"early warning": 8, r"shakealert": 9, r"real[- ]time (detection|monitoring|processing|system)": 7,
            r"rapid (response|magnitude|estimation)": 4, r"(alert|warning) system": 6,
            r"earthquake detection": 6, r"onsite warning": 7, r"nowcast": 3,
            r"(earthquake|seismic) (response|emergency)": 4, r"back[- ]projection": 4,
            r"finite[- ]fault (rapid )?": 3, r"warning (time|lead)": 5,
        },
    },
    {
        "id": "slow", "name": "慢地震、震颤与断层蠕滑",
        "desc": "慢滑移事件、深部震颤、低频地震、无震滑动与蠕滑",
        "keywords": {
            r"slow slip": 9, r"slow earthquake": 9, r"tectonic tremor|seismic tremor": 8,
            r"low[- ]frequency earthquake": 8, r"\bLFE\b": 7, r"aseismic": 6,
            r"episodic tremor": 9, r"creep (event|front|rate|deformation)": 4,
            r"silent earthquake": 9, r"deep (tremor|slip)": 7, r"slow (rupture|fault|deformation)": 5,
            r"transient (slip|deformation)": 5, r"afterslip": 7,
        },
    },
    {
        "id": "planetary", "name": "行星地震学",
        "desc": "火星、月球及其他天体的地震活动与内部结构探测",
        "keywords": {
            r"marsquake": 10, r"moonquake": 10, r"insight (mission|lander|seismometer)": 6,
            r"\bSEIS\b": 5, r"planetary seismolog\w*": 9,
            r"apollo (seismic|passive|program)": 8, r"seismic (activity|event|data) (on|from) (mars|the moon|venus)": 9,
            r"venusquake|europ\w+": 8, r"icy moon|titan": 4, r"moon": 2, r"mars": 2,
            r"seismicity of (mars|the moon|venus)": 9,
        },
    },
    {
        "id": "ocean", "name": "海洋地球物理与海啸",
        "desc": "海底地震观测、海啸生成与传播、大洋转换断层与洋中脊",
        "keywords": {
            r"tsunami": 8, r"ocean[- ]bottom seismometer": 9, r"\bOBS\b": 5,
            r"seafloor (seismic|pressure|deformation)": 7, r"offshore": 3,
            r"marine (seismic|geophysical|geolog)": 5, r"sea level|tide gauge": 3,
            r"oceanic (crust|lithosphere|mantle)": 4, r"trench": 3,
            r"hydrothermal|black smoker": 4, r"submarine cable": 4,
        },
    },
    {
        "id": "ai", "name": "人工智能与地震学方法",
        "desc": "深度学习震相拾取、去噪、地震检测与波形生成（交叉标签）",
        "keywords": {
            r"machine learning": 7, r"deep learning": 7, r"neural network": 7,
            r"transformer": 5, r"phase (picking|detection|association)": 7, r"denois\w+": 5,
            r"autoencoder|convolutional|generative adversarial": 6, r"transfer learning": 6,
            r"self[- ]supervised": 6, r"foundation model": 6, r"graph neural": 6,
            r"artificial intelligence": 6, r"deep neural": 6, r"deep[- ]learning": 7,
            r"machine[- ]learning": 7,
        },
    },
    {
        "id": "instrument", "name": "观测技术与仪器装备",
        "desc": "分布式光纤、地震台阵、台网建设、仪器标定与野外部署",
        "keywords": {
            r"distributed acoustic sensing": 9, r"\bDAS\b": 6, r"fiber[- ]optic": 7,
            r"seismic (array|network|station|observatory)": 6,
            r"seismic instrument\w*": 7, r"deployment of": 3, r"borehole": 4,
            r"(instrument )?calibration": 3, r"broadband seism\w*": 6,
            r"sensor (network|technology|array)": 5, r"accelerometer|smartphone": 4,
            r"new (seismic )?(array|network|dataset)": 5, r"data (quality|acquisition)": 3,
        },
    },
]

COMPILED = [
    (c["id"], [(re.compile(p, re.I), w) for p, w in c["keywords"].items()])
    for c in CATEGORIES
]

# =====================================================================
# 三、OpenAlex 主题 / 关键词 → 类目（覆盖 100% 文章，弥补摘要缺失）
# =====================================================================
TOPIC_RULES = [
    (r"induced (seismicity|earthquake)|fluid injection|hydraulic fractur|shale gas|"
     r"geothermal energy|geothermal system|carbon (capture|sequestration)|"
     r"wastewater|unconventional (oil|gas)", "induced", 8),
    (r"earthquake (early )?warning|onsite warning|seismic monitor", "warning", 7),
    (r"earthquake detection|seismic (source|phase) (detection|picking)|"
     r"earthquake (location|monitoring)|seismicity (monitoring|detection)", "warning", 5),
    (r"seismic hazard|earthquake (hazard|risk|engineering|impact)|ground motion|"
     r"seismic (performance|design|resistance|vulnerability)|structural (engineering|damage)|"
     r"liquefaction|disaster (management|response|resilience|risk|preparedness)|"
     r"earthquake (disaster|damage|loss)|tsunami (hazard|warning|risk)", "hazard", 7),
    (r"landslide|rockfall|rock fall|debris flow|mass wasting|slope (stability|failure)", "hazard", 5),
    (r"tsunami|marine geology|ocean (bottom|crust|floor)|seafloor|submarine", "ocean", 6),
    (r"seismic (imaging|inversion|tomograph)|seismic waves?|wave propagation|"
     r"seismic (velocity|attenuation|anisotropy)|mantle|earth'?s (interior|core)|"
     r"core[- ]mantle|lithospher|crustal (structure|thickness)|high[- ]pressure geophysics|"
     r"normal mode|receiver function|geophysics and sensor", "structure", 6),
    (r"tectonic|fault|subduction|plate (boundary|tectonic|motion)|geodynam|rifting|rift|"
     r"geodesy|geodetic|crustal deformation|continental (collision|rift)|orogen|"
     r"seismic (reflection|refraction) (profile|survey)|basin (evolution|formation)", "tectonics", 5),
    (r"aftershock|seismicity (pattern|statistic|rate)|statistical seismolog|"
     r"earthquake (statistics|forecast|prediction|probability|catalog)|"
     r"earthquake (sequence|swarm)|magnitude[- ]frequency|recurrence", "catalog", 7),
    (r"seismic (source|moment|rupture)|earthquake (source|rupture|cycle|nucleation)|"
     r"fault (rupture|slip|mechanics|friction)|dynamic rupture|stress drop", "source", 7),
    (r"slow (slip|earthquake)|tectonic tremor|episodic tremor|low[- ]frequency earthquake|"
     r"aseismic|fault creep", "slow", 8),
    (r"\bmars\b|marsquake|\bmoon\b|moonquake|planetary|venus|icy moon|insight mission", "planetary", 6),
    (r"machine learning|deep learning|neural network|artificial intelligence|"
     r"computer vision|data[- ]driven", "ai", 5),
    (r"distributed acoustic sensing|\bDAS\b|fiber[- ]optic|instrumentation|"
     r"sensor (network|technology|array)|seismic (network|array|station)", "instrument", 6),
]
TOPIC_RULES = [(re.compile(p, re.I), cid, w) for p, cid, w in TOPIC_RULES]

GENERIC_TOPICS = re.compile(
    r"^seismology and earthquake studies$|^earthquake and tectonic studies$|"
    r"^earthquake detection and analysis$|^seismic waves and analysis$",
    re.I,
)

# 文献类型 → 中文
TYPE_LABEL = {
    "article": "研究论文", "review": "综述", "letter": "快报",
    "editorial": "社论/评论", "news": "新闻", "paratext": "栏目信息",
    "erratum": "更正", "book-chapter": "书章", "book-review": "书评",
    "book": "专著", "preprint": "预印本", "report": "报告",
    "conference-abstract": "会议摘要", "conference-paper": "会议论文",
    "dissertation": "学位论文", "dataset": "数据集", "peer-review": "同行评议",
    "retraction": "撤稿", "other": "其他",
}


# =====================================================================
# 四、工具函数
# =====================================================================
def rebuild_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return re.sub(r"\s+", " ", " ".join(pos[k] for k in sorted(pos))).strip()


def trim(text, limit=760):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    p = cut.rfind(". ")
    return (cut[: p + 1] if p > limit * 0.55 else cut) + "…"


def topic_texts(rec):
    """取出该文章的全部 OpenAlex 主题与关键词文本。"""
    out = []
    for t in (rec.get("topics") or []):
        if t.get("display_name"):
            out.append(t["display_name"])
    pt = (rec.get("primary_topic") or {}).get("display_name")
    if pt and pt not in out:
        out.append(pt)
    for k in (rec.get("keywords") or []):
        if k.get("display_name"):
            out.append(k["display_name"])
    return out


def score_categories(title, abstract, topics):
    """三层信号联合打分，返回 (主类目, 多标签, 分数字典, 命中依据)。"""
    scores = defaultdict(float)
    why = defaultdict(list)

    # ① 标题
    for cid, kws in COMPILED:
        for rx, w in kws:
            if rx.search(title):
                scores[cid] += w * 3
                why[cid].append("题:" + rx.pattern[:22])
    # ② 摘要
    for cid, kws in COMPILED:
        for rx, w in kws:
            n = len(rx.findall(abstract))
            if n:
                scores[cid] += w * min(n, 3)
                why[cid].append("摘:" + rx.pattern[:22])
    # ③ OpenAlex 主题 / 关键词
    for t in topics:
        if GENERIC_TOPICS.match(t):
            continue
        for rx, cid, w in TOPIC_RULES:
            if rx.search(t):
                scores[cid] += w * 2
                why[cid].append("题标:" + t[:26])
                break

    if not scores:
        return "general", ["general"], {}, {}

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top = ranked[0][1]
    labels = [cid for cid, s in ranked if s >= max(9, top * 0.4)][:4]
    return ranked[0][0], labels, dict(scores), {k: v[:3] for k, v in why.items()}


# =====================================================================
# 五、主流程
# =====================================================================
NAME_OF = {c["id"]: c["name"] for c in CATEGORIES}
NAME_OF["general"] = "综合、新闻与观点"

JOURNAL_LABEL = {"Science": "Science", "Nature": "Nature", "Nature Geoscience": "Nature Geoscience"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-dropped", action="store_true", help="导出被过滤的样本用于核对")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, ".."))
    raw_dir = os.path.join(root, "data", "raw")
    web_dir = os.path.join(root, "web")

    seen, papers, dropped = set(), [], []
    stats = Counter()

    for fn in sorted(os.listdir(raw_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(raw_dir, fn), encoding="utf-8") as fh:
            records = json.load(fh)
        print(f"读取 {fn}: {len(records)} 条")
        stats[f"原始:{fn.replace('.json','')}"] = len(records)

        for r in records:
            doi = (r.get("doi") or "").lower().replace("https://doi.org/", "")
            key = doi or r.get("id")
            title = (r.get("title") or r.get("display_name") or "").strip()
            if not key or key in seen:
                stats["剔除:重复"] += 1
                continue
            if not title:
                stats["剔除:无标题"] += 1
                continue

            abstract = rebuild_abstract(r.get("abstract_inverted_index"))
            topics = topic_texts(r)
            topic_str = " | ".join(topics)

            if not is_seismology(title, abstract, topic_str):
                stats["剔除:非地震学"] += 1
                if args.dump_dropped:
                    dropped.append({"title": title, "journal": fn, "topic": topic_str[:160]})
                continue
            seen.add(key)

            src = (r.get("primary_location") or {}).get("source") or {}
            journal = JOURNAL_LABEL.get(src.get("display_name"), src.get("display_name") or "Unknown")
            primary, labels, scores, why = score_categories(title, abstract, topics)

            authors = [ (a.get("author") or {}).get("display_name")
                        for a in (r.get("authorships") or []) ]
            authors = [a for a in authors if a]
            oa = r.get("open_access") or {}
            rtype = r.get("type") or "article"

            papers.append({
                "id": r.get("id", "").rsplit("/", 1)[-1],
                "doi": doi,
                "title": title,
                "year": r.get("publication_year"),
                "date": r.get("publication_date") or "",
                "journal": journal,
                "type": rtype,
                "type_cn": TYPE_LABEL.get(rtype, rtype),
                "research": rtype in ("article", "review", "letter"),
                "authors": authors,
                "first_author": authors[0] if authors else "",
                "n_authors": len(authors),
                "cited": r.get("cited_by_count") or 0,
                "oa": bool(oa.get("is_oa")),
                "oa_url": oa.get("oa_url") or "",
                "topic": (r.get("primary_topic") or {}).get("display_name") or "",
                "cat": primary,
                "cats": labels,
                "score": round(scores.get(primary, 0), 1),
                "why": why.get(primary, []),
                "abstract": trim(abstract),
                "has_abstract": bool(abstract),
            })

    papers.sort(key=lambda p: (-(p["year"] or 0), -(p["cited"] or 0)))
    print(f"\n过滤后保留：{len(papers)} 篇（剔除 {stats['剔除:非地震学']} 篇非地震学、"
          f"{stats['剔除:重复']} 篇重复）")
    n_abs = sum(1 for p in papers if p["has_abstract"])
    print(f"其中有摘要 {n_abs} 篇（{n_abs*100//max(len(papers),1)}%）")

    cc = Counter(p["cat"] for p in papers)
    print("\n分类分布：")
    for cid, n in cc.most_common():
        print(f"  {NAME_OF.get(cid, cid):26s} {n:5d}  ({n*100//len(papers)}%)")
    print("\n文献类型：")
    for t, n in Counter(p["type_cn"] for p in papers).most_common():
        print(f"  {t:10s} {n:5d}")

    # ---------------- 输出 ----------------
    os.makedirs(web_dir, exist_ok=True)
    with open(os.path.join(root, "data", "papers.json"), "w", encoding="utf-8") as fh:
        json.dump(papers, fh, ensure_ascii=False, indent=1)

    years = Counter(p["year"] for p in papers if p["year"])
    meta = {
        "generated": date.today().isoformat(),
        "total": len(papers),
        "with_abstract": n_abs,
        "years": sorted(years.items()),
        "categories": [{"id": c["id"], "name": c["name"], "desc": c["desc"],
                        "count": cc.get(c["id"], 0)} for c in CATEGORIES]
                      + [{"id": "general", "name": "综合、新闻与观点",
                          "desc": "标题信息有限或属于新闻/点评类文章",
                          "count": cc.get("general", 0)}],
        "journals": sorted(Counter(p["journal"] for p in papers).items()),
        "types": sorted(Counter(p["type_cn"] for p in papers).items(),
                        key=lambda kv: -kv[1]),
    }

    with open(os.path.join(web_dir, "data.js"), "w", encoding="utf-8") as fh:
        fh.write("// 自动生成，请勿手工编辑。由 scripts/build_site.py 产出。\n")
        fh.write("window.META = " + json.dumps(meta, ensure_ascii=False) + ";\n")
        fh.write("window.PAPERS = " + json.dumps(papers, ensure_ascii=False) + ";\n")

    if args.dump_dropped:
        with open(os.path.join(root, "data", "dropped.json"), "w", encoding="utf-8") as fh:
            json.dump(dropped, fh, ensure_ascii=False, indent=1)
        print(f"已导出 {len(dropped)} 条被剔除样本 -> data/dropped.json")

    size = os.path.getsize(os.path.join(web_dir, "data.js")) / 1024 / 1024
    print(f"\n✓ 已生成 web/data.js（{size:.1f} MB）与 data/papers.json")


if __name__ == "__main__":
    main()
