# 两套分类体系对照

同一份名录，不同年代的文献给不同的纲和目。输出里**两套都保留**，方便和旧文献对齐。

## 现代体系 — De Ley & Blaxter

基于 SSU rDNA 的系统发育，Nemaplex 现在采用这一套。

```
Nematoda
├── Chromadorea 色矛纲
│   ├── Chromadoria 色矛亚纲
│   │   ├── Chromadorida 色矛目、Desmodorida 链环目、Desmoscolecida 链线目
│   │   ├── Monhysterida 单宫目、Araeolaimida 无咽目、Plectida 绕线目
│   │   └── Microlaimida 微咽目、Isolaimiida 等咽目
│   └── Rhabditia 小杆亚纲
│       └── Rhabditida 小杆目   ← 吸收了经典的垫刃目、滑刃目、双胃目、
│                                 圆线目、蛔目、旋尾目、尖尾目
└── Enoplea 刺嘴纲
    ├── Enoplia 刺嘴亚纲
    │   └── Enoplida 刺嘴目、Triplonchida 三矛目
    ├── Dorylaimia 矛线亚纲
    │   └── Dorylaimida 矛线目、Mononchida 单齿目
    └── Mermithida 索线目、Trichinellida 毛形目、Dioctophymatida 膨结目
```

## 经典体系 — Chitwood (1958)

按尾感器（phasmid）和侧场（lateral field）的有无分纲，旧文献和很多国内教材还在用。

```
Nematoda
├── Adenophorea 无尾感器纲     （= 无尾感器、侧场不发达）
│   └── Enoplida 刺嘴目、Dorylaimida 矛线目、Mononchida 单齿目、
│       Chromadorida 色矛目、Desmodorida 链环目、Desmoscolecida 链线目、
│       Monhysterida 单宫目、Araeolaimida 无咽目、Plectida 绕线目、
│       Trichinellida 毛形目、Mermithida 索线目、Dioctophymatida 膨结目 …
└── Secernentea 尾感器纲       （= 有尾感器、侧场发达）
    └── Tylenchida 垫刃目、Aphelenchida 滑刃目、Rhabditida 小杆目、
        Diplogasterida 双胃目、Strongylida 圆线目、Ascaridida 蛔目、
        Spirurida 旋尾目、Oxyurida 尖尾目、Camallanida 驼形目、
        Drilonematida 蛭线目 …
```

## Tylenchida 去哪了

**这是最容易踩的坑。** 现代体系里 `Tylenchida` **不是目**——它被并进了 `Rhabditida`。
`Aphelenchida` 同理，成了 Rhabditida 下的 Aphelenchina 亚目。

所以：源表写"垫刃目"是**对的**，只是用的经典体系。不要把它报成"与 Nemaplex 不一致"，
而是在备注里说明体系转换：

> 源表纲名 尾感器纲 属经典体系，Nemaplex 现用 Chromadorea

`scripts/lookup.py` 的 `CLASS_ALIASES` 会把两套体系的纲名都认下来，
`CLASSICAL_EQUIV` 负责判定"经典名 ↔ 现代名"是否自洽。

## 经典纲名怎么推出来

站点只给现代体系，经典纲得自己推。规则（见 `scripts/lookup.py`）：

```
目 == Rhabditida  →  Secernentea 尾感器纲
其余目           →  Adenophorea 无尾感器纲
```

理由：现代 `Rhabditida` 恰好吸收了经典体系里 `Secernentea` 的全部目
（垫刃目、滑刃目、双杆目、圆线目、蛔目、旋尾目、尖尾目）；
其余的目都来自 `Adenophorea`。

这是**派生的**，不是站点原文。输出里 `cls_trad` 字段旁边标了来源，
论文里引用时建议说明"经典体系纲名按 Chitwood (1958) 归并规则换算"。

有一处已知的不完全等价：经典 `Adenophorea` 里的色矛目、链环目、单宫目等，
在现代体系里划到了 `Chromadorea` 的 `Chromadoria` 亚纲。也就是说
**"Adenophorea" 和 "Enoplea" 不是同一回事**，前者包含了一部分现代色矛纲的类群。
按上面的规则推出来的经典纲是自洽的，但不要反过来拿现代纲去覆盖经典纲。

## 中文译名的可靠性

`data/zh_cn_labels.json` 的 `orders` 里每条带 `confidence`：

- `standard` — 有通行译名（小杆目、矛线目、垫刃目、色矛目…），可直接用；
- `tentative` — 暂无通行译名，是自拟或暂译（链线目、微咽目、等咽目、海索线目、
  鼠线目、蛭线目、列体目），**投稿前请按您引用的体系复核**。

中文译名不是 Nemaplex 的内容，站上没有中文。所有译名都来自本地对照表。
