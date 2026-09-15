# Nemaplex 数据源说明

站点：**Nemaplex, UC Davis** — http://nemaplex.ucdavis.edu/

本 skill 全部事实性字段（科、目、纲、亚纲、c-p 值、取食类群、功能团代码、属页链接）
来自该站。中文译名、经典体系纲名为本地补充，输出中单独标注。

## 页面结构与 URL 规律

| 用途 | URL | 说明 |
|---|---|---|
| 属索引（6 页） | `IndexFiles/{atob,ctod,etol,mtoo,ptor,stoz}.html` | 全站属级主表，2567 属 |
| 科索引 | `IndexFiles/Index%20to%20FamiliesNew.html` | 292 个科的链接入口 |
| 科菜单页 | `Taxamnus/{code}mnu.htm` | 分类面包屑（纲/亚纲/目/亚目/超科） |
| 属菜单页 | `Taxamnus/{code}mnu.htm` | 同上，属级 |
| 属详情页 | `Taxadata/G{code}.aspx` | 属的详细描述 |
| 功能团汇总（4 张） | `IndexFiles/functguild{bact,fun?,genspecpreds,plant}fdrs.html` | 295 属，属索引的补充 |
| 代码释义 | `IndexFiles/Heading%20Category-{CP%20Classes,Feeding%20Groups,Functional%20Guilds,Putative%20Feeding,Family}.html` | c-p、取食类群、功能团的权威定义 |
| 取食习性 | `Ecology/feeding_habits.htm` | 科级取食习性描述 |
| 分类总览 | `Taxadata/Classes.htm` | 现代 + 经典两套体系的总览 |

## 属索引页的列布局

6 页布局一致，固定 7 列：

```
Genus | Family | Putative Feeding | c-p Group | Feeding Group | Functional Guild | Internal Code
```

**属行判据：首列带斜体标记（`<em>` 或 `<i>`）。**

⚠️ 不要用"内部码非空"当判据。内部码为空的属（Abirovulva、Anguilluloides、Sinanema、
Brevibucca 等）会被丢掉——实测只剩 1692 个属，实际有 2567 个。

提取属名的正则要能容忍连字符和点：

```python
re.match(r"^[A-Za-z][A-Za-z\-'\. ]+$", name)
```

## 科菜单页的分类面包屑

科页里有这样一段纯文本（标签剥掉之后）：

```
Nematoda Chromadorea Chromadoria Chromadorida Chromadorina Chromadoroidea Family Achromadoridae
```

即 `Nematoda <纲> <亚纲> <目> <亚目> <超科> Family <科>`。层级按后缀判：

| 后缀 | 层级 |
|---|---|
| `-ia` | 亚纲 |
| `-ida` | 目 |
| `-ina` | 亚目 |
| `-oidea` | 超科 |

解析正则：

```python
m = re.search(r"Nematoda\s+(.{0,320}?)Family\s+([A-Za-z\-]+)", s)
```

这个后缀规则在 Nemaplex 的科页里是稳定的，适合拿来分类。**只抓 292 次科页就能覆盖
全部 2567 属的纲/目归属**，不必抓 2567 次属页。

科链接的提取正则要放宽，否则只提得到 48 个科：

```python
re.findall(r'<a[^>]+href="([^"]*mnu\.htm)"[^>]*>(.*?)</a>', html, re.S | re.I)
```

## 功能团字段的覆盖率

属索引 2567 属中：

- 有**科名**：2567（全覆盖）
- 有 **c-p 值**：853
- 有**功能团代码**：852
- 有**取食类群码**：852

**空白是常态，不是错误。** 站点对很多属没有给出功能团——填不上就留空，
不要按近缘属外推。输出里注明"站点未给出"。

## 站点自身的拼写错误

源表里有明显的录入错误，读取时按 `data/zh_cn_labels.json` 的 `source_typos` 归一化：

| 站点原文 | 应为 |
|---|---|
| `animal paraqsites` | `animal parasites` |
| `ahimal parasites` | `animal parasites` |
| `marine nemayodes` | `marine nematodes` |
| `narine nematodes` | `marine nematodes` |
| `unkmown` | `unknown` |
| `microbial feefers` | `microbial feeders` |
| `omnivora` | `omnivores` |
| `Predators` | `predators` |
| `bacterial feeders` | `bacteria feeders` |
| `plant feeders?` | `plant feeders` |

归一化之后再进统计，否则同一类群会被拆成两三个键。

## 抓取注意事项

- **限速 0.25 s/请求**，别把对方的服务器打挂。全量冷跑约 300 请求。
- 带正常的 User-Agent，不要伪装成浏览器。
- 全部响应缓存到 `.cache/`（已 gitignore），重跑走缓存，秒级。
- 站点改版时 `python scripts/build_snapshot.py --refresh` 重建快照。
- 缓存文件名规则：`re.sub(r"[^A-Za-z0-9._-]+", "_", url.replace(BASE, ""))[:150]`。
  长 URL 会被截断，注意不同页面别撞名（`Heading%20Category-*` 系列要保住前缀差异）。

## 解析陷阱（都是实际踩过的，重建快照前先读一遍）

这个站点是 Word 导出的静态 HTML，年代久远，写法很不规范。以下每一条都真实导致过数据错误：

### 1. 单字母被拆进独立 `<span>`，用空格替换标签会断词

```html
<span class="auto-style1">C</span><span class="auto-style3">hromadoria</span>
<a href="../Taxadata/Enoplea.HTM">E<font size="4">noplea</font></a>
```

用 `re.sub(r"<[^>]+>", " ", html)`（空格替换）会得到 `C hromadoria`、`E noplea`——
**纲名 Enoplea 直接变成空串，数据静默丢失**。`text_of()` 用空串替换才对。

但也不能全用空串：`</td>` 之间的单元格边界会粘成一个词。正确做法是
**区分内联标签和块级标签**（见 `flow_text()`）：内联标签 → `""`，块级标签 → `" "`。

`plain()` 保留给不需要保词的场景（取 `<title>`、取整页摘要）。

### 2. `<style>` 里的 CSS 会被当成正文

页面开头有一大坨 `.MsoNormal {margin-bottom:.0001pt; ...}`。不先剥掉 `<style>`，
这些 CSS 文本会混进正文，污染所有下游正则。`strip_noise()` 负责剥 `<style>`、
`<script>`、HTML 注释和 Word 的 `<o:p>` 填充。

### 3. 表格嵌套会整体偏移列号

`Taxadata/Classes.htm` 把真正的分类树嵌在布局表里。直接解析外层表，
外层的 `<td>` 会占掉第 0 列，所有 `colspan` 累加出来的列号整体偏移，
导致 `Dorylaimia` 被归到 `Chromadorea`。**只解析叶子表格**（内部不含 `<table>` 的表）。

### 4. 链接文件名不可信，页面可见文字才可信

`Aponidae.aspx` 指向的页面上，科名写的是 `Aponchiidae`（正确的拼法）。
`Actiidae.aspx` 对应的是 `Actinolaimidae`。**提取名称一律用可见文字**，
文件名只作为最后的兜底。

### 5. 属索引不能用"内部码非空"当行判据

内部码为空的属（Abirovulva、Anguilluloides、Sinanema、Brevibucca…）会被丢掉，
实测只剩 1692 个属，实际有 2567 个。判据是**首列带 `<em>` 或 `<i>` 斜体标记**。

### 6. 科链接正则会漏掉绝大多数科

```python
# 错：只提得到 48 个科
r'<a[^>]+href="([^"]+)"[^>]*>([^<]{3,60})</a>'
# 对：292 个科
r'<a[^>]+href="([^"]*mnu\.htm)"[^>]*>(.*?)</a>'   # + re.S | re.I
```

`([^<]{3,60})` 容不下嵌套的 `<font>` / `<span>`，绝大多数链接都带这些标签。

### 7. 取食习性页是段落，不是表格

`Ecology/feeding_habits.htm` 的每个科是一个 `<p>`，格式为
`<b>科名<span style="mso-tab-count:1">&nbsp;…</span>取食习性</b>`。
按 `<p>` 切分、每个段落 `flow_text()` 后按 `^([A-Z][A-Za-z]+idae)\s+(.+)$` 拆。

**不要**用"科名后面跟另一个科名"的跨段落正则会得到一堆
`('Alaimidae', 'Bastianiidae')` 这种垃圾配对。

### 8. 代码释义页有两种形态

| 页面 | 形态 |
|---|---|
| CP Classes、Feeding Groups | 表格，`table` 字段 |
| Functional Guilds、Putative Feeding、Family | **散文定义，没有表格**，`text` 字段 |

对散文页死磕表格解析只会得到 0 行。功能团的权威定义就在散文里：

> Functional Guilds: A combination of feeding habits defined as bacterivores,
> fungivores, predates and omnivores combined with the cp classification.
> A component of Faunal Analysis of the condition of the soil food web.

### 9. 有科页漏写目级

`Aponchiidae` 的面包屑有纲、亚纲、亚目、超科，**就是没有目**
（`Chromadorea Chromadoria Microlaimina Microlaimoidea`）。

`repair_missing_orders()` 的补法：亚目 `-ina` 换成 `-ida`，
且替换结果必须**真实出现在别处**（其它科的面包屑，或 `Classes.htm` 的目清单）才采用。
否则留空并报出来，绝不凭空造一个目。`Aponchiidae` 的 `Microlaimina` → `Microlaimida`
正好能在站点目清单里对上。

## 站点里没有的东西

- **中文名。** 全站只有拉丁学名和英文。中文名 → 拉丁名必须自建字典，
  这是整个流程里**唯一需要人工把关**的环节。
- **分子数据 / 序列。** 本站不做系统发育分析，SSU rDNA 体系只是它的分类骨架。
- **分布记录。** 中国青藏高原土壤这类产地信息站上没有。
- **个体数量、丰度。** 站点是分类学参考，不是生态数据集。
