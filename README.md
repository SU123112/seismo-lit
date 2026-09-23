# 地震学文献库 · Seismology Literature Hub

自动收录 **Science / Nature / Nature Geoscience** 上与地震学相关的全部论文，按主题分类，供课题组检索与学习。

数据源：[OpenAlex](https://openalex.org)（开放学术图谱，CC0，覆盖 Crossref / PubMed 全量元数据，免费、无需 API Key）。

---

## 一、10 分钟跑起来

```bash
# 1) 抓取元数据（约 1-3 分钟，三刊共 ~7000 条原始记录）
python scripts/fetch_openalex.py

# 2) 过滤 + 分类 + 生成网站数据
python scripts/build_site.py

# 3) 本地预览
cd web && python -m http.server 8000
# 浏览器打开 http://localhost:8000
```

依赖：仅 Python 3.8+ 标准库，**无需 pip install**。

> 直接双击 `web/index.html` 也能看，但部分浏览器会拦截本地 `data.js`，
> 此时页面会提示你改用上面的 `http.server` 方式。

---

## 二、目录结构

```
seismo-lit/
├─ scripts/
│  ├─ fetch_openalex.py     # 第 1 步：抓取原始元数据 → data/raw/*.json
│  └─ build_site.py         # 第 2 步：相关性过滤 + 分类 → web/data.js
├─ data/
│  ├─ raw/                  # 原始抓取结果（可缓存，重跑不会重复下载）
│  └─ papers.json           # 清洗后的完整数据（含摘要、DOI、分类）
└─ web/
   ├─ index.html            # 网站（纯静态，零依赖，可直接部署）
   └─ data.js               # 由 build_site.py 生成，不要手工改
```

---

## 三、分类体系（12 类，支持多标签）

| 类目 | 说明 |
|---|---|
| 震源物理与破裂过程 | 震源参数、破裂动力学、应力降、超剪切 |
| 地球内部结构与地震成像 | 层析成像、接收函数、面波、各向异性、核幔边界 |
| 断层活动、构造变形与大地测量 | 断层带、板块边界、俯冲带、GPS/InSAR |
| 地震目录与统计地震学 | 余震、b 值、ETAS、震级-频度、复发 |
| 诱发地震与流体作用 | 注水、页岩气、水库、地热、采矿诱发 |
| 地震灾害、地震动与工程抗震 | 危险性、GMPE、场地效应、液化、损失 |
| 地震预警与实时监测 | 预警系统、实时处理、快速响应 |
| 慢地震、震颤与断层蠕滑 | 慢滑移、深部震颤、LFE、无震滑动 |
| 行星地震学 | 火星震、月震、InSight |
| 海洋地球物理与海啸 | OBS、海底观测、海啸 |
| 人工智能与地震学方法 | 深度学习拾取、去噪、检测（交叉标签） |
| 观测技术与仪器装备 | 分布式光纤 DAS、台阵、台网、标定 |

分类是**规则打分制**（关键词权重 × 标题/摘要位置加权），一篇论文可同时归入多个类目，
得分最高者为主类目。想调整分类，直接改 `build_site.py` 里的 `CATEGORIES` 词表即可，无需重新抓数据。

---

## 四、想改的地方

| 需求 | 改哪里 |
|---|---|
| 增补期刊（如 Science Advances、Nature Communications） | `fetch_openalex.py` 的 `JOURNALS`，取消对应注释后加参数 `--journal` 单独抓 |
| 调整检索召回词 | `fetch_openalex.py` 的 `SEARCH_TERMS` |
| 收紧/放宽"算不算地震学"的判定 | `build_site.py` 的 `CORE` / `is_seismology()` |
| 新增/修改分类类目 | `build_site.py` 的 `CATEGORIES` |
| 页面配色、标题 | `web/index.html` 顶部 `:root` 变量 |

---

## 五、定期自动更新（推荐）

仓库含 `.github/workflows/update.yml`：每周一自动重跑抓取与建站并发布到 GitHub Pages。
只需把项目推到 GitHub，在仓库 **Settings → Pages** 里选择 `GitHub Actions` 作为 Source 即可。

手动更新数据：本地重跑上面两步，然后推送；或直接在 Actions 页面点 `Run workflow`。
