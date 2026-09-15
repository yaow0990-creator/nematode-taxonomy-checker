# 判定规则与置信度分级

## 流程内部的三类判定

### 1. 名称解析置信度（第 1 步产出）

每行一个 `confidence`，决定该不该进"待人工确认"。

| 值 | 什么时候出现 | 是否可直接用 |
|---|---|---|
| `exact` | 拉丁名在 Nemaplex 属索引里直接命中 | ✅ 是 |
| `dictionary` | 靠中文名查字典（使用者自带的，或仓库里的种子）得到拉丁名，且该属在站点存在 | ✅ 是 |
| `cn-conflict` | 表里同时给了中文名和拉丁名，但两者指向不同属 | ❌ 必须人工裁决 |
| `spelling-suspect` | 拉丁名不在索引中，`difflib` 找到了 ≥0.86 的相似项 | ❌ 需人工确认是不是拼错 |
| `unresolved` | 既查不到字典、又无相似候选 | ❌ 需人工补录 |

排序（`CONF_RANK`）：`exact` > `dictionary` > `cn-conflict` > `spelling-suspect` > `unresolved`。

**只有 `exact` 和 `dictionary` 算确定。** 其余全部进 Excel 的"待人工确认"页和报告的
待确认清单，并染黄底（`cn-conflict` 染红底）。

模糊匹配阈值默认 `0.86`，可用 `--cutoff` 调。调低了会把真错拼和不相干的属混在一起，
建议不要低于 `0.84`。

### 2. 源表 vs Nemaplex 的判定（第 2 步产出）

| `verdict` | 中文 | 触发条件 |
|---|---|---|
| `match` | 一致 | 源表给了科/目/纲，且全部与站点一致 |
| `corrected` | 不一致，已按 Nemaplex 修正 | 给出的字段全部不一致 |
| `partial` | 部分一致 | 部分字段一致、部分不一致（备注列出哪些不一致） |
| `not-found` | Nemaplex 未收录 | 属名不在站点索引中 |
| `unresolved` | 名称未解析，未比对 | 第 1 步没定下拉丁名 |
| `uncheckable` | 源表未给拉丁科/目名，无法比对 | 源表只给中文科名/目名 |

**源表只给中文科名或目名时不做逐字比对**（`uncheckable`）。因为站点没有中文，
拿中文去比是拿两套东西比，只会产生假警报。这种情况输出里直接采用 Nemaplex 的值，
并在备注说明"源表未给拉丁名，未比对"。

源表的纲名如果在经典体系里（`Adenophorea` / `Secernentea`），会先换算再判，
换算后一致就算 `match`，不会因为体系不同报成不一致。

### 3. 字段可靠性

| 字段 | 可靠性 | 说明 |
|---|---|---|
| `fam_nem`、`ord_nem`、`cls_nem`、`subcls_nem` | 站点原文 | 科页面包屑解析 |
| `cp`、`feeding_group`、`functional_guild`、`putative_feeding` | 站点原文 | 属索引页 |
| `cp_cn`、`feeding_group_cn`、`functional_guild_cn` | 本地对照表 | 代码→中文 |
| `ord_cn`、`cls_cn`、`subcls_cn` | 本地对照表 | 看 `confidence` 是否 `tentative` |
| `cls_trad` | **派生** | 按归并规则换算，非站点原文 |
| `latin`（来自字典时） | **使用者提供** | 看 `cn_dict_layer` 是哪个文件给的 |
| `genus_url` | 站点原文 | 属详情页链接，可逐条复核 |

## 什么情况必须人工确认

**必须人过一眼的：**

1. `cn-conflict` — 中文名和拉丁名打架。常见于异名、新旧属名混用、中文名一书一译。
2. `spelling-suspect` — 疑似拼错。真实案例：`Criconrmoides`→`Criconemoides`、
   `Enchodelu`→`Enchodelus`、`ChrPradorita`→`Chromadorita`、
   `Diplogsteroides`→`Diplogasteroides`、`Brachyderus`→`Brachydorus`、
   `Odotopharynx`→`Odontopharynx`、`Beleodorus`→`Boleodorus`、
   `Rhabdontolaimus`→`Rhabditolaimus`、`Wilsotylus`→`Wilsonema`、
   `Fudonchulus`→`Judonchulus`。**替换前确认这是错拼，而不是一个真属名。**
3. `unresolved` — 字典没有、相似项也没有。写进 `out/needs_cn_mapping.csv`，填好 `latin` 列后
   可用 `--cn-dict` 回喂，不必改仓库里的种子。
4. `not-found` — 站点没这个属。可能是异名、已废弃属、新描述但站点未更新，
   或者拼错到相似度低于阈值。查一下原始文献再定。
5. `tentative` 的中文译名 — 自拟的目名、纲名，论文里用之前复核一遍。

**不需要人工确认的：**

- 站点某个属没有 c-p 值或功能团 —— 这是站点的覆盖范围问题，留空即可，不要外推。
- 源表用的是经典体系纲名 —— 备注会自动说明，无需处理。

## 反面清单：不要做的事

- **不要按近缘属外推功能团。** "同科的属都是 b1，所以它也填 b1" —— 不行。站点没给就留空。
- **不要静默修正源表。** 覆盖之前先把原值留在 `fam_in` / `ord_in` / `cls_in` 里，
  判定列写明差异。用户需要知道自己的表哪里错了。
- **不要把中文名当成可推断的。** 中文名没有拉丁学名那样的命名法约束，一书一译是常态。
  查不到就是查不到。
- **不要用现有资料补站点没有的字段。** 本 skill 的定位是"Verifier"不是"Filler"。
  用户要的是可复核的核查结果，不是看起来完整的表。

## 中文名字典：由使用者自带，本工具不推断

Nemaplex 全站没有中文名，所以"中文名 → 拉丁名"没有权威的自动来源。本工具的处理原则是
**把字典当外部输入**，而不是内置一份需要维护的权威表：

| 层 | 来源 | 说明 |
|---|---|---|
| 1 | `data/cn_latin_genus.json` | 随仓库的示例种子（180 条），仅作演示与兜底 |
| 2 | 输入文件同目录的 `cn_dict.csv` / `中文名字典.csv` / `<输入名>.dict.csv` | 自动发现，无需参数 |
| 3 | `--cn-dict 路径` | 显式指定，可重复；**后面覆盖前面** |

三层的合并顺序就是上表顺序，所以使用者自己的判断永远压过仓库里的种子。

### 字典文件格式

CSV / XLSX 均可，列名中英文都认（`cn` 或 `中文名`、`latin` 或 `拉丁名`）：

```csv
cn,latin,aliases,confidence,source
伪垫刃,Nothotylenchus,,user-verified,用户提供名录 2026-09
垫刃线虫,Tylenchus,麦线虫属,user-verified,FAO AGROVOC
```

- `aliases` 用 `;` 或 `,` 分隔，**会被注册成可匹配的键**（别名指向同一条目，但不会覆盖
  已有的正式条目）；
- `confidence` 是自由标签，建议 `user-verified` / `user-supplied`。注意别写 `exact`——
  那是流程内部给"站点直接命中"保留的值；
- 带不带"属"字都认（查表时尾部"属"会被去掉）。

### 闭环：待填表 → 字典

字典没命中的中文名会导出到 `<outdir>/needs_cn_mapping.csv`，**列结构与字典文件完全一致**，
唯一的区别是 `latin` 列空着等填，另有一个只读的 `latin_in_table` 列记录源表原本给的拉丁名
（方便判断是"缺映射"还是"源表也错了"）。

```
cn,latin,aliases,confidence,source,latin_in_table,note,no
伞滑刃属,,,user-supplied,,,字典未收录,1
```

填好 `latin` 后，把**同一个文件**当字典传回来即可：

```bash
python scripts/run_pipeline.py --input 名录.csv --cn-dict out/needs_cn_mapping.csv
```

多跑几轮，这份文件自己就长成使用者的字典。注意两点：填在 `latin` 列里（另起列读不到）；
文件存 UTF-8（Excel 另存 CSV 默认不是，会乱码）。

### 写字典前的自检

1. 先在 Nemaplex 属索引里确认这个拉丁属名存在（不存在的话，后面分类匹配同样是空的）；
2. 再确认中文名不是异名混用——如果表里同时给了中文名和拉丁名且两者不符，流程会标
   `cn-conflict` 让你裁决，不会自动站队；
3. 出处写进 `source`，方便别人复核。

### 不要做的事

- **不要把一个中文名硬塞给两个拉丁属。** 一书一译是常态，遇到就分开两条、各自标注来源。
- **不要用模型推断的中文名混进已核条目。** 如果确实要推断，单独放一个文件、单独标
  `model-proposed`，让使用者自己决定要不要用。
- **不要为了"让流程跑通"而随便填一个拉丁名。** 填错的后果是整条科/目/纲/功能团链全错，
  而且看起来很真——比留空危险得多。
