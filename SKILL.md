---
name: nematode-taxonomy
description: 线虫（nematode）属级分类与功能团核查。输入一张只有属级名称的表（中文名 + 拉丁名，可带科/目/纲），自动补全科、目、纲（现代 + 经典两套体系）以及 Nemaplex 的功能团字段（c-p 值、取食类群、功能团代码）。当用户提到线虫分类核查、线虫属名核对、科属归属、c-p 值、功能团、functional guild、取食类群，或要给一份线虫名录补全分类信息时使用本 skill。数据源为 Nemaplex（UC Davis）。
agent_created: true
---

# 线虫分类与功能团核查

## 这个 skill 干什么

把一张**只有名称**的线虫属名录，变成一张**带完整分类归属和功能团**的核查表。

```
输入                                   输出
中文名 + 拉丁名（可只给其一）           科 / 亚纲 / 目 / 纲（现代体系）
（可选：已有的科/目/纲，用于比对）      纲（经典体系 Chitwood 1958）
                                      c-p 值 + 取食类群 + 功能团代码（含中文）
                                      判定结论 + 差异说明 + 待人工确认清单
```

数据源是 **Nemaplex, UC Davis**（http://nemaplex.ucdavis.edu/）。分类归属、c-p 值、
取食类群、功能团代码全部来自该站，不做推断。站上没有的东西（中文译名、经典体系纲名）
在本地对照表里，并且在输出中明确标注为"非站点内容"。

## 四条不可动摇的规则

1. **站点说什么就是什么。** 分类与功能团字段不允许模型"猜一个合理的"。查不到就写查不到。
2. **中文名是唯一需要人工把关的环节。** Nemaplex 全站只有拉丁名。中文名 → 拉丁名靠本地字典
   `data/cn_latin_seed.csv`；字典没命中的，写进 `out/needs_cn_mapping.csv` 让人补，**绝不静默填入**。
3. **源表和站点不一致时，两边都留着。** 输出里同时有"源表值"和"Nemaplex 值"，判定列写明差异。
   不做静默覆盖。
4. **不确定的分级标出来。** 每行都有 `confidence`，低于 `dictionary` 的一律进"待人工确认"页。

## 首次使用

需要先建离线快照（约 300 次请求，一次性）：

```bash
python scripts/build_snapshot.py
```

快照落在 `data/`，含 2500+ 属的完整索引和 290+ 科的分类面包屑。
之后每次核查都读本地快照，不再联网。站点改版时 `--refresh` 重建。

## 日常使用

```bash
# 一条命令跑完全流程
python scripts/run_pipeline.py --input 名录.csv --outdir out

# Excel 输入也行
python scripts/run_pipeline.py --input 名录.xlsx --sheet Sheet1

# 分步跑（中间产物留在 out/，某一步改了不用重跑全部）
python scripts/normalize_names.py --input 名录.csv --out out/normalized.json
python scripts/lookup.py --input out/normalized.json --out out/matched.json
python scripts/export.py --input out/matched.json
```

### 输入格式

CSV 或 XLSX，表头可用的列名（中英文都认）：

| 用途 | 可用列名 | 必需 |
|---|---|---|
| 中文属名 | 中文名 / 中文属名 / 中文 / name_cn | 二选一 |
| 拉丁属名 | 拉丁名 / 属名 / genus / latin | 二选一 |
| 已有科 | 科 / 科名 / family | 可选 |
| 已有目 | 目 / order | 可选 |
| 已有纲 | 纲 / class | 可选 |

**只给中文名和拉丁名就够了**——这正是第 1 步存在的意义。

### 输出

| 文件 | 内容 |
|---|---|
| `out/线虫分类核查结果.xlsx` | 4 个 sheet：核查结果 / 待人工确认 / 功能团汇总 / 说明 |
| `out/report.html` | 单文件报告：概览卡片、分布表、待确认清单、全部结果 |
| `out/normalized.json` | 第 1 步中间产物，名称解析结果 + 置信度 |
| `out/matched.json` | 第 2、3 步中间产物，全字段 |
| `out/needs_cn_mapping.csv` | 字典未收录的中文名，**等您补** |

## 流程四步

### 第 1 步 · 名称归一化 — `scripts/normalize_names.py`

1. **给了拉丁名** → 在属索引里核。核不到就用 `difflib` 提 3 个最近邻，标 `spelling-suspect`
   （真实场景里 `Criconrmoides`、`Enchodelu`、`Diplogsteroides` 这类错拼一整片）。
2. **给了中文名** → 查 `data/cn_latin_genus.json`（由 `data/cn_latin_seed.csv` 编译）。
   尾部"属"字会被去掉，所以"伪垫刃属"和"伪垫刃"都能命中。
3. **中文名没命中** → 写进 `out/needs_cn_mapping.csv`，留空位等人工填。不编。
4. **两个都给了但对不上** → 标 `cn-conflict`，人工裁决，不覆盖。

置信度分级（`exact` > `dictionary` > `cn-conflict` > `spelling-suspect` > `unresolved`）。

### 第 2 步 · 分类匹配 — `scripts/lookup.py`

属 → 科 → 目/纲/亚纲，走两步：

- 属索引页给出每个属的**科**（2567 属全部有科名）；
- 科菜单页的分类面包屑给出**纲/亚纲/目/亚目/超科**。层级按后缀判：
  `-ia`=亚纲、`-ida`=目、`-ina`=亚目、`-oidea`=超科。这一条规则在这份数据里是稳定的。

只抓 292 次科页，不抓 2567 次属页，快得多。

**同时输出两套体系**：现代（Chromadorea 色矛纲 / Enoplea 刺嘴纲，Tylenchida 已并入
Rhabditida）和经典（Chitwood 1958：Adenophorea / Secernentea）。经典纲的推法见
`references/classification_systems.md`。

### 第 3 步 · 功能团匹配 — 同 `scripts/lookup.py`

属索引页本身带 5 个功能团相关列，全部收进来并配中文：

| 字段 | 例 | 中文 |
|---|---|---|
| `cp` | `3` | 中间型（世代较长、对干扰更敏感） |
| `feeding_group` | `2` | 菌丝取食（真菌食） |
| `functional_guild` | `f2` | 真菌食 c-p2 |
| `putative_feeding` | `fungus feeders` | 真菌食 |

站点源表自身有拼写错误（`animal paraqsites`、`unkmown`、`marine nemayodes`…），
读取时按 `zh_cn_labels.json` 的 `source_typos` 归一化，避免污染下游统计。

覆盖率：2567 属中 853 个有 c-p 值、852 个有功能团。**不是每个属都有**——没有就留空，
写"站点未给出"，不外推。

### 第 4 步 · 导出 — `scripts/export.py`

Excel 的"说明"页写清字段释义、置信度分级、两套体系差异、c-p 与取食类群的完整定义原文出处。
报告里所有链接都指向对应的 Nemaplex 属页，方便逐条复核。

## 中文名字典怎么扩

`data/cn_latin_seed.csv` 现在 180 行（176 条已核，4 条未解决）。扩充方式：

1. 跑完流程后看 `out/needs_cn_mapping.csv`，把拉丁名补上；
2. 追加到 `data/cn_latin_seed.csv`（列：`cn, latin, aliases, confidence, source`）；
3. 重编译：

```bash
python scripts/build_cn_dict.py
```

`latin` 建议先在该站的属索引里确认存在，再写进去。`aliases` 填同一属的其他中文叫法
（如"垫刃线虫属"和"麦线虫属"）。

## 判定列的含义

| 判定 | 含义 |
|---|---|
| 一致 | 源表科/目/纲与 Nemaplex 一致 |
| 不一致，已按 Nemaplex 修正 | 不符，输出采用 Nemaplex 值，备注列出差异 |
| 部分一致 | 部分字段一致，备注列出不一致的那几项 |
| Nemaplex 未收录 | 属名不在站点索引中（可能是异名、已废弃属，或拼错到无法匹配） |
| 名称未解析，未比对 | 第 1 步没定下拉丁名 |
| 源表未给拉丁科/目名，无法比对 | 源表只给中文科名/目名，不做逐字比对 |

## 常见坑

站点是 Word 导出的静态 HTML，写法不规范。以下每条都真实导致过数据错误——
完整分析和修法见 `references/data_source.md` 的「解析陷阱」。

- **别用空格替换标签。** 站点把单字母拆进独立 `<span>`（`C` + `hromadoria`），
  空格替换会得到 `C hromadoria`，`E noplea` → **纲名整个丢失**。
  用 `flow_text()`：内联标签→`""`，块级标签→`" "`。
- **先剥 `<style>`。** 否则 CSS 文本（`.MsoNormal {margin-bottom:.0001pt; …}`）
  会当成正文混进结果。
- **嵌套表格会偏移列号。** 分类树嵌在布局表里，解析外层表会让
  `Dorylaimia` 归到 `Chromadorea`。只解析叶子表格。
- **链接文件名不可信。** `Aponidae.aspx` 页面上写的是 `Aponchiidae`（正确的）。
  提取名称用可见文字，文件名只兜底。
- **别用"有内部码"当属行判据。** 内部码为空的属（Abirovulva、Anguilluloides、Sinanema、
  Brevibucca 等）会被丢掉，1692 个属取代 2567 个。判据是首列带 `<em>`/`<i>` 斜体标记。
- **科链接正则要放宽。** `<a[^>]+href="([^"]*mnu\.htm)"[^>]*>(.*?)</a>` 配 `re.S|re.I`，
  否则只提得到 48 个科（应该 292 个）。
- **取食习性页是段落不是表格。** 按 `<p>` 切分再拆"科名 + 习性"，跨段落正则会产生
  `('Alaimidae','Bastianiidae')` 这种垃圾配对。
- **释义页有两种形态。** CP Classes / Feeding Groups 是表格；
  Functional Guilds / Putative Feeding / Family 是**散文**，没有表格。
- **有科页漏写目级。** 如 `Aponchiidae`。补法：亚目 `-ina`→`-ida`，
  且结果必须真实出现在别处才采用，否则留空并报出。
- **Tylenchida 不是目。** 现代体系里它并入 Rhabditida。用户表里写"垫刃目"是对的，
  那是经典体系——`lookup.py` 会识别成体系换算而不是不一致，备注里说明即可。
- **中文译名要复核。** 目名里 `Desmoscolecida`、`Microlaimida`、`Isolaimiida` 等标了
  `tentative`（暂无通行译名），投稿前按用户引用的体系再核一遍。

## 参考文件

- `references/data_source.md` — 站点结构、URL 规律、字段布局、**9 条解析陷阱**
- `references/classification_systems.md` — 现代体系 vs 经典体系，Tylenchida 去哪了
- `references/decision_rules.md` — 判定规则、置信度分级、什么情况必须人工确认
