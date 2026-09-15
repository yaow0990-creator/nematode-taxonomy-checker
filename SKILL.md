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
2. **中文名由使用者自带。** Nemaplex 全站只有拉丁名和英文，一个中文都不收录。所以"中文名 → 拉丁名"
   这件事站点帮不上忙，本 skill 也**不做推断**：用的人自己带一份字典进来（`--cn-dict`），
   或者就只给拉丁名。字典没命中的，导出成待填表，填好再喂回来，**绝不静默填入**。
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

# 中文名走自己的字典（可给多个，后面的覆盖前面的）
python scripts/run_pipeline.py --input 名录.csv --cn-dict 我的中文名字典.csv

# 分步跑（中间产物留在 out/，某一步改了不用重跑全部）
python scripts/normalize_names.py --input 名录.csv --out out/normalized.json
python scripts/lookup.py --input out/normalized.json --out out/matched.json
python scripts/export.py --input out/matched.json
```

### 中文名怎么进来

Nemaplex 不收录中文名，所以这一步**必须由使用者提供**。三种方式，优先级从低到高：

1. skill 自带的小种子字典 `data/cn_latin_genus.json`（180 条，仅作示例与兜底）
2. 放在输入文件同目录的 `cn_dict.csv` / `中文名字典.csv` / `<输入文件名>.dict.csv` —— 自动读取
3. `--cn-dict 路径` 显式指定，可重复，后一个文件覆盖前一个

字典文件（CSV / XLSX / 编译好的 JSON 都行）的列：

| 列 | 必需 | 说明 |
|---|---|---|
| `cn` 或 `中文名` | ✔ | 中文属名，带不带"属"字都认 |
| `latin` 或 `拉丁名` | ✔ | 对应拉丁属名 |
| `aliases` | | 同一属的其他中文叫法，`;` 或 `,` 分隔，**也会被当作可匹配的键** |
| `confidence` | | 自填标签，如 `user-verified` |
| `source` | | 出处，方便日后复核 |

**兜底闭环**：字典没命中的中文名会导出成 `out/needs_cn_mapping.csv`，**列结构与字典文件完全一致**。
在 `latin` 列填上，然后把同一个文件当字典传回来重跑即可：

```bash
python scripts/run_pipeline.py --input 名录.csv --cn-dict out/needs_cn_mapping.csv
```

多跑几轮，这份文件自己就长成你的字典了。

### 输入格式

CSV 或 XLSX，表头可用的列名（中英文都认）：

| 用途 | 可用列名 | 必需 |
|---|---|---|
| 中文属名 | 中文名 / 中文属名 / 中文 / name_cn | 二选一 |
| 拉丁属名 | 拉丁名 / 属名 / genus / latin | 二选一 |
| 已有科 | 科 / 科名 / family | 可选 |
| 已有目 | 目 / order | 可选 |
| 已有纲 | 纲 / class | 可选 |

**只给中文名和拉丁名就够了**——这正是第 1 步存在的意义。只给中文名时，结果完全取决于
你带的字典；只给拉丁名时不需要任何字典（站点索引里就有）。

### 输出

| 文件 | 内容 |
|---|---|
| `out/线虫分类核查结果.xlsx` | 4 个 sheet：核查结果 / 待人工确认 / 功能团汇总 / 说明 |
| `out/report.html` | 单文件报告：概览卡片、分布表、待确认清单、全部结果 |
| `out/normalized.json` | 第 1 步中间产物，名称解析结果 + 置信度 |
| `out/matched.json` | 第 2、3 步中间产物，全字段 |
| `out/needs_cn_mapping.csv` | 字典未收录的中文名，**等您填 `latin` 列**；填好后可直接当 `--cn-dict` 输入 |

## 流程四步

### 第 1 步 · 名称归一化 — `scripts/normalize_names.py`

1. **给了拉丁名** → 在属索引里核。核不到就用 `difflib` 提 3 个最近邻，标 `spelling-suspect`
   （真实场景里 `Criconrmoides`、`Enchodelu`、`Diplogsteroides` 这类错拼一整片）。
2. **给了中文名** → 查字典（自带种子 + 自动发现的同目录字典 + `--cn-dict`，后者覆盖前者）。
   尾部"属"字会被去掉，所以"伪垫刃属"和"伪垫刃"都能命中；`aliases` 列里的别名同样可命中。
3. **中文名没命中** → 按字典文件格式写进 `out/needs_cn_mapping.csv`，`latin` 列留空。不编。
   填好后把该文件用 `--cn-dict` 传回来即可完成闭环。
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

## 关于中文名（边界说清）

**本 skill 不负责产生中文名。** 中文名的权威性取决于使用者引用的资料，不在站点里，
也不在模型的知识里。所以：

- 用的人自己带字典 → 中文名这条路就通；
- 不带字典、只给中文名 → 会老实标 `unresolved`，列出待填表，**不会猜一个看着像的拉丁名**。
  猜错一个属名，后面整条科/目/纲/功能团链全是错的，而且看起来很真，比空着危险得多；
- 不带字典、只给拉丁名 → 完全不受影响（站点索引里就有）。

`data/cn_latin_seed.csv` 只是示例种子（180 条，来自一次真实名录核查），**不是**必须维护的资产。
想把它当长期字典用，可继续按 `cn, latin, aliases, confidence, source` 追加，再编译：

```bash
python scripts/build_cn_dict.py
```

但更推荐用 `--cn-dict` 外挂，这样每个人各带各的字典，仓库里这份种子保持干净。
`latin` 写进去之前建议先在站点属索引里确认该属存在。`aliases` 填同一属的其他中文叫法
（如"松材线虫属"与"伞滑刃属"）。

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
- **待填表就填在 `latin` 列里，别加列。** `out/needs_cn_mapping.csv` 的列名与字典文件一致，
  是为了直接回喂。另起一列或改表头，`--cn-dict` 就读不到了。文件存为 UTF-8（Excel 另存 CSV 默认
  不是，会乱码）。
- **`aliases` 是能匹配的键，不只是备注。** 别名与正名指向同一条目；但别名**不会**覆盖已有的
  正式条目，避免把别的属挤掉。

## 参考文件

- `references/data_source.md` — 站点结构、URL 规律、字段布局、**9 条解析陷阱**
- `references/classification_systems.md` — 现代体系 vs 经典体系，Tylenchida 去哪了
- `references/decision_rules.md` — 判定规则、置信度分级、什么情况必须人工确认
