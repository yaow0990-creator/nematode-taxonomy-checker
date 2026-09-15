# nematode-taxonomy

线虫属级分类与功能团核查工具。给一张**只有名称**的名录，还一张**带完整分类归属和功能团**的核查表。

数据源：**Nemaplex, UC Davis** — http://nemaplex.ucdavis.edu/

## 解决什么问题

手上有一批线虫属名，但只有中文名和拉丁名，没有科/目/纲，也没有 c-p 值和功能团。
以前得一条条去 Nemaplex 上翻。这个工具把这套流程固化成四步流水线：

```
输入                          第1步           第2步          第3步          第4步
中文名 + 拉丁名        →   名称归一化   →   分类匹配   →   功能团匹配   →   导出
（可只给其一）              查字典/纠错      科目纲亚纲      c-p/取食类群     Excel + HTML
```

同时它还是个**核查**工具：如果表里已经写了科/目/纲，会拿去和 Nemaplex 比对，
把不一致的地方标出来，而不是静默覆盖。

## 快速开始

```bash
# 1. 首次使用：建离线快照（约 300 次请求，一次性；之后走本地缓存）
python scripts/build_snapshot.py

# 2. 跑流程
python scripts/run_pipeline.py --input 名录.csv --outdir out

# 中文名走自己的字典（可选，可给多个）
python scripts/run_pipeline.py --input 名录.csv --cn-dict 我的中文名字典.csv
```

产物在 `out/`：

| 文件 | 内容 |
|---|---|
| `线虫分类核查结果.xlsx` | 4 个 sheet：核查结果 / 待人工确认 / 功能团汇总 / 说明 |
| `report.html` | 单文件报告，每个属带 Nemaplex 原页链接 |
| `needs_cn_mapping.csv` | 字典未收录的中文名，填上 `latin` 列后可直接回喂给 `--cn-dict` |

## 输入长什么样

只需中文名和/或拉丁名两列，科/目/纲有就带上（用于比对），没有也行。

| 中文名 | 拉丁名 | 科 | 目 | 纲 |
|---|---|---|---|---|
| 伪垫刃 | Nothotylenchus | | | |
| 垫刃线虫 | | | | |

列名中英文都认（`中文名`/`name_cn`、`拉丁名`/`genus`、`科`/`family`…），
CSV 和 XLSX 都支持。**只给中文名也能跑**——第 1 步会去查你带的字典。

### 中文名字典自带

Nemaplex 只有拉丁名和英文，没有中文名，所以中文名这块站点帮不上忙：**用的人自己带字典**。
放在输入文件同目录叫 `cn_dict.csv` / `中文名字典.csv` 会自动读，也可以用 `--cn-dict` 显式指定。
没命中的会导出成 `needs_cn_mapping.csv`（列结构与字典一致），填好再传回来即可：

```bash
python scripts/run_pipeline.py --input 名录.csv --cn-dict out/needs_cn_mapping.csv
```

示例见 `examples/my_cn_dict.csv`。

## 输出字段

分类归属（现代体系 Chromadorea / Enoplea 与经典体系 Adenophorea / Secernentea 两套都给）、
c-p 值、取食类群码、功能团代码，每个代码都配中文译名。完整字段见
`SKILL.md` 和 Excel 的"说明"页。

## 目录结构

```
scripts/
  build_snapshot.py    重建离线快照（爬 Nemaplex）
  build_cn_dict.py     编译中文名→拉丁名查询表
  normalize_names.py   第 1 步：名称归一化
  lookup.py            第 2、3 步：分类匹配 + 功能团匹配
  export.py            第 4 步：导出 Excel / HTML
  run_pipeline.py      一条命令串起来
data/
  genus_index.json          2567 个属的索引（属→科/c-p/取食类群/功能团）
  family_order_class.json   科→纲/亚纲/目/亚目/超科
  code_glossaries.json      c-p、取食类群的权威定义原文
  zh_cn_labels.json         中文对照表（含译名可靠性标注）
  cn_latin_seed.csv         中文名→拉丁名字典示例种子（非必需，可换用自己的字典）
  cn_latin_genus.json       上者的编译产物
references/
  data_source.md            站点结构、URL 规则、已知坑
  classification_systems.md 现代 vs 经典两套体系，Tylenchida 去哪了
  decision_rules.md         判定规则、置信度分级、什么必须人工确认
examples/
  test_input.csv            混合测试数据（含错拼、只给中文名、只给拉丁名）
  demo_new_genera.csv       一批原表之外的属，演示流程不绑定任何单一名录
  demo_cn_only.csv          只给中文名，演示待填表→回喂闭环
  my_cn_dict.csv            中文名字典模板
```

## 两条硬边界

**一、中文名不推断，由使用者自带。** Nemaplex 全站只有拉丁名和英文，中文名 → 拉丁名
这件事没有权威的自动来源。所以本工具的做法是：你带字典就查字典，没带字典又只给中文名，
就老实标 `unresolved` 并导出待填表，**不会猜一个看着像的拉丁名**。猜错一个属名，
后面整条科/目/纲/功能团链全错，而且看起来很真——比空着危险得多。

**二、查不到就写查不到。** 站点对很多属没有给 c-p 值和功能团（2567 属里只有 853 个有），
空着就是空着，不按近缘属外推。这个工具的定位是 Verifier，不是 Filler。

## 依赖

Python 3.9+（标准库即可；读 XLSX 和写 Excel 需要 `openpyxl`）。

```bash
pip install openpyxl
```

## 数据来源与引用

分类框架与功能团字段全部来自 Nemaplex（UC Davis）。中文译名、经典体系纲名为本地补充，
输出中单独标注。投稿引用时建议同时引用 Nemaplex 出处与您使用的体系文献
（De Ley & Blaxter 现代体系 / Chitwood 1958 经典体系）。
