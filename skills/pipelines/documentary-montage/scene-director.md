# 场景导演 —— Documentary Montage 管线

## 何时使用

brief 已经存在。你现在要把一个主题性问题变成
一份具体的**槽位**清单，供检索层去填充。每个槽位既是一个
意图（"黄昏时门口的一个剪影"），也附带能在真实世界
（Pexels/Archive.org/NASA/Wikimedia/Unsplash）里找到它的检索词。

这是整条管线中最有创意的阶段。检索的上限，就是你写的
槽位描述的上限。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["idea"]["brief"]` | 主题性问题、调性、时长、形状 |
| 参考 | `skills/pipelines/documentary-montage/executive-producer.md` | 跨阶段规则 |
| 工具 | 暂无 —— 本阶段是纯规划 | — |

## 心智模型

场景导演的工作**不是**"挑片段"，而是"把这些片段需要是什么样，
描述得足够朴素，好让 CLIP 能找到它们"。

要像堪景师那样思考，而不是像素材库管理员。

- 素材库管理员会说：*"城市雨天蒙太奇，15 个片段"*。
- 堪景师会说：*"蓝调时刻，雨水横着划过公交车窗，
  乘客的脸在柔焦里，红绿交通灯的光透过玻璃
  渗出来"*。

后者才是 CLIP 真正能排序的东西。前者是一个
类别标签，CLIP 匹配起来既弱又不加分辨。

## 流程

### 1. 把形状换算成节拍数

读 brief 的 `duration_seconds` 和 `shape`。据此推导槽位
数量。除非调性另有要求，否则使用这些默认值：

| 调性 | 平均停留 | 每 60 秒的槽位数 |
|------|--------------|---------------|
| elegiac（哀歌） | 4.0 秒 | 约 15 |
| reverent（庄重） | 3.5 秒 | 约 17 |
| dreamlike（梦境） | 3.0 秒 | 约 20 |
| wry（戏谑） | 2.0 秒 | 约 30 |
| urgent（紧迫） | 1.2 秒 | 约 50 |

然后按形状规划弧线：

- **list（清单）**：N 个均匀槽位，没有转折。
- **before/after（前后）**：N/2 个"之前"槽位 + 1 个枢轴槽位 + N/2 个"之后"槽位。
- **three-act（三幕）**：铺陈（30%）→ 转折（40%）→ 释放（30%）。
- **single-image expansion（单意象展开）**：1 个锚定意象 + 围绕它的 N 个变奏。

在写任何槽位之前，先把节拍数写下来。

### 2. 把主题性问题拆解成具体节拍

拿起 brief 里那**一个**主题性问题，用感官语言去回答它。
不要写主题 —— 写质感。

**示例 —— "雨向你展示了这座城市的什么？"**

差的拆解（抽象、无法检索）：

- "确立城市的氛围"
- "被天气困住的那种感觉"
- "雨的普遍性"

好的拆解（具体、可检索）：

- 一滴雨以慢动作打在干燥的沥青上
- 一把伞在门口撑开，能看到一只手
- 霓虹招牌在水洼里倒映成颠倒的样子
- 雨水横划过公交车窗，乘客虚化
- 出租车顶灯在大雨中推出来，长焦
- 排水口吞下落叶与积水，俯拍
- 街边小贩把塑料布拉过果蔬推车
- 钨丝路灯下湿鹅卵石上升起的蒸汽
- 一只儿童雨靴踩进水洼
- 透过雨幕看到的一扇亮着灯的公寓窗

其中每一条都是**一个镜头**。每一条都能被 CLIP 排序。每一条也都是
*同一个想法的不同侧面*，而这正是清单形状的蒙太奇获得分量的原因。

### 3. 写槽位描述

每个槽位都带一个 `description` 字段。这是 CLIP 会去
嵌入并排序的文本。把它写得像一串好的素材标签
—— 名词和形容词，不要表达意图的动词，不要情绪词。

**模板：**

```
<主体>，<动作/姿态>，<环境>，<光照>，<年代/质感提示>
```

**好的：**

- `"a single raindrop hitting dry asphalt, close up, slow motion,
  warm streetlamp glow"`
- `"empty city sidewalk at night after rain, reflected neon,
  handheld, 1970s grain"`
- `"an umbrella opening in a doorway, hand visible, diffused
  afternoon light, shallow focus"`

**差的：**

- `"the feeling of arriving home"` —— 情绪词，没有主体
- `"a warm welcoming moment"` —— 形容词堆砌，没有画面
- `"someone going through a door in a symbolic way"` —— 意图，不是镜头

经验法则：若你无法从这段描述中想象出一张具体的照片，
CLIP 也想象不出来。

### 4. 每个槽位写 2-3 条检索词

槽位描述是 CLIP 用来排序的。检索词是
`corpus_builder` 用来填充候选池的。这是两件不同的活，
所以要分开写。

给每个槽位一个含 2-3 项的 `queries` 数组：

1. **字面检索词** —— 最直接的素材检索短语。就是
   一个 Pexels 用户会打的那种。`"raindrop on asphalt slow motion"`。
2. **侧向检索词** —— 同一想法的另一个角度或尺度。
   `"wet pavement close up"`。
3. **联想检索词**（可选，用于主槽位）—— 一个相邻
   概念，可能带出字面检索词漏掉的质感片段。
   `"first rain city street"`。

对素材检索引擎而言，短检索词胜过长检索词。每条 2-5 个词。
不要填充词。

### 5. 逐槽位指定来源（感知年代）

读 `brief.era_mix`。根据素材实际存放在哪里，为每个槽位分配一个或多个
`preferred_sources`：

| 来源 | 强项 | 何时使用 |
|--------|-----------|----------|
| `pexels` | 现代 HD 素材、干净镜头、人物、城市、自然 | 现代/任意年代的默认项 |
| `pixabay_video` | 庞大的社区库，自然、人物、科技、生活方式 | Pexels 找不到时补缺；宽泛的通用素材 |
| `coverr` | 精选的电影感 B-roll，自然、都市、抽象背景 | 高质量定场镜头、氛围铺垫、现代生活方式 |
| `mixkit` | Envato 精选的 HD/4K，自然、商务、科技 | 有高级感的 B-roll、干净的自然素材，无需署名 |
| `archive_org` | Prelinger 家庭录像、中世纪教育片、1940-1980 年代质感 | 复古、戏谑、梦境，以及任何怀旧内容 |
| `nara` | 美国国家档案馆 —— 二战、冷战、阿波罗、民权、总统 | 美国历史纪录片、军事、政府、太空竞赛 |
| `loc` | 美国国会图书馆 —— 早期电影、新闻片、文化录音 | 1928 年前的公共领域素材、美国历史、民间传统 |
| `pond5_pd` | Pond5 公共领域 —— 一战/二战、早期电影、历史演说 | 档案/复古素材，梅里爱、爱迪生、新闻片 |
| `videvo` | 9 万多条免费片段，自然、航拍、城市、抽象、延时 | 庞大的免费库，以不同贡献者补足 Pexels |
| `nasa` | 轨道看地球、天文、飞行、尺度影像 | 庄重基调，以及任何关于尺度、太空、星球、飞行的内容 |
| `esa` | 欧洲太空任务、哈勃/韦伯影像、地球观测 | 欧洲太空内容，在非美任务上补足 NASA |
| `jaxa` | 日本太空任务、隼鸟号、国际空间站希望号舱、H-IIA 火箭 | 亚洲太空内容，太空探索的独特视角 |
| `noaa` | 深海 ROV 素材、海洋生物、珊瑚礁、天气、飓风 | 海洋/水下、独有的深海内容、天气现象 |
| `dareful` | 精品 4K 自然 —— 山脉、森林、瀑布、延时 | 高质量自然 B-roll、统一的视觉风格、航拍镜头 |
| `wikimedia` | Commons 图片与 CC 视频，公民/纪实/公共活动报道 | 公共空间、地标、抗议、城市质感、教学素材 |
| `unsplash` | 精致的编辑风静图、生活方式、偏产品的摄影 | 动态素材匮乏时的现代静图补充镜头 |

若 `era_mix = "vintage"`，就把槽位偏向 `archive_org`，并用
符合年代的词汇写检索词（用 "commuter"、"housewife"、
"suburb"，而不是 "influencer"、"wfh"、"coworking"）。

若 `era_mix = "any"`，就逐槽位混用来源 —— 由场景导演
根据该节拍的含义决定哪个槽位用哪个来源。

#### 儿童 / 童话类内容

当 brief 的 `tone` 或 `target_audience` 指向儿童
内容（童话、睡前故事、儿童讲解、动画故事）时，
**把视觉策略从真实素材切换为 Pixabay 上 AI 生成的奇幻
片段**。

Pixabay 的社区库里有数千条 AI 生成的奇幻
动画（发光的森林、被施了魔法的风景、神奇生物），
在吸引儿童注意力方面远胜真实素材。

**儿童内容的检索词改写规则：**

| 槽位意图 | 真实素材检索词 | 奇幻化改写 |
|-------------|-------------------|-----------------|
| 花园 / 自然 | `garden flowers morning` | `enchanted fairy tale garden glowing magical` |
| 昆虫 / 生物 | `caterpillar leaf close up` | `fairy tale caterpillar magical forest glowing` |
| 蜕变 / 蛹 | `chrysalis butterfly cocoon` | `magical chrysalis enchanted tree glowing` |
| 蝴蝶 / 飞行 | `butterfly flying sky` | `fantasy butterfly glowing magical wings` |
| 日落 / 风景 | `sunset landscape golden` | `enchanted fantasy landscape magical sunset` |
| 雨 / 天气 | `rain leaves gentle` | `fairy tale rain magical forest enchanted` |
| 夜空 / 星星 | `milky way timelapse` | `fantasy night sky magical stars enchanted` |
| 海洋 / 水 | `river water golden` | `magical underwater world fairy tale` |
| 山脉 / 航拍 | `mountain peaks golden` | `fantasy mountain castle fairy tale magical` |
| 森林 / 树木 | `forest path morning` | `fairy tale mushroom forest glowing enchanted` |

**来源路由：** 给**所有**槽位设 `preferred_sources: ["pixabay_video"]`。
Pixabay 是唯一拥有深厚 AI 生成奇幻库的免费来源。
不要把真实素材与奇幻素材混用 —— 风格冲突会破坏
儿童的沉浸感。

**能带出 AI 奇幻内容的关键词：** `fairy tale`、`fantasy`、
`enchanted`、`magical`、`glowing`、`dreamy`、`mystical`、`fairy`、
`enchanted forest`、`magical world`。

### 6. 标出主槽位

每支蒙太奇都有 2-3 个整件作品所仰赖的槽位：开场
画面、转折、最后一个画面。在槽位元数据里把它们标为 `hero: true`。

主槽位会获得：

- 更长的停留（2-4 秒，而不是该调性的默认值），
- assets 阶段更大的候选池（k=30 而不是 k=10），
- 更多检索词（3 条而不是 2 条）。

### 7. 给 Assets 阶段留出余地

不要写得过死。素材导演的工作是拿候选去与你的
描述做排序。若你既钉死了描述**又**钉死了具体片段，
那你就把素材导演的活干砸了，也提前占用了
它的创意选择空间。

规则：像在电话里向一位调研助理描述那样去描述槽位 ——
具体到能认出来，宽松到还能给你惊喜。

### 8. 记录镜头表

使用 `scene_plan.schema.json` artifact，每个槽位对应一个 `scene`。
对本管线，把 documentary-montage 专属的字段放进每个场景的
`metadata` 里。规范形态：

```json
{
  "version": "1.0",
  "scenes": [
    {
      "id": "slot_01",
      "type": "broll",
      "description": "a single raindrop hitting dry asphalt, close up, slow motion, warm streetlamp glow",
      "start_seconds": 0.0,
      "end_seconds": 3.5,
      "narrative_role": "establish_context",
      "hero_moment": true,
      "texture_keywords": ["wet", "slow motion", "streetlamp"],
      "required_assets": [
        { "type": "video", "description": "raindrop on asphalt", "source": "source" }
      ]
    }
  ],
  "metadata": {
    "pipeline": "documentary-montage",
    "shape": "list",
    "tone": "elegiac",
    "thematic_question": "What does rain show you about a city?",
    "slots": [
      {
        "id": "slot_01",
        "description": "a single raindrop hitting dry asphalt, close up, slow motion, warm streetlamp glow",
        "hero": true,
        "preferred_sources": ["pexels", "archive_org"],
        "queries": [
          "raindrop on asphalt slow motion",
          "wet pavement close up",
          "first rain city street"
        ],
        "min_duration": 3.0,
        "target_hold_seconds": 3.5,
        "era_hint": "any"
      }
    ]
  }
}
```

`scenes[]` 数组用于满足 schema。而素材导演真正会读的是
`metadata.slots[]` 数组 —— 它携带了 `scene_plan.schema.json`
并不了解的、与检索相关的字段（`queries`、`preferred_sources`、`hero`、
`era_hint`）。

### 9. 质量门

- 槽位数量与第 1 步的节拍数算法相符。
- 每个槽位的 `description` 都遵循名词加形容词的模板 ——
  没有情绪词，没有表达意图的动词。
- 每个槽位都有 2-3 条简短检索词（每条不超过 5 个词）。
- 至少有 2 个槽位被标为 `hero`。
- `target_hold_seconds` 之和落在 `brief.duration_seconds` 的 ±10% 以内。
- 若 `era_mix = "vintage"`，至少 60% 的槽位在
  `preferred_sources` 中列出了 `archive_org`。
- `metadata.thematic_question` 与 brief 逐字一致（用来核查
  你没有跑偏）。

## 常见陷阱

- **把槽位描述写成意图而不是画面。** "进门前迟疑的
  那一刻"是剧本提示，不是 CLIP 检索词。"一个女人静静站在
  门廊上，手靠近门把"才是。
- **类别式检索词。** `"home"` 和 `"family"` 匹配一切也匹配不到任何
  东西。要逼出具体名词：门、地垫、钥匙、走廊、鞋。
- **只写一条检索词的槽位。** 第二条检索词是廉价的保险 —— 若
  第一条返回垃圾，素材库里至少还有能用的东西。
- **忘了时长换算。** 90 秒哀歌式约等于 15 个约 6 秒的停留。
  若你写了 40 个槽位，那你无意中起草的是一支
  紧迫风格的作品。
- **在复古 brief 上跳过 `era_hint`。** Pexels 会用 2020 年代的 HD
  素材淹没素材库，把 Prelinger 的材料埋掉。
- **让主题性问题漂移。** 若 brief 说的是"回家"，而你的
  槽位清单里有三个飞机镜头，那这件作品就会变成关于旅行，
  而不是关于家。起草之后回头重读 brief。

## 完整示例 —— "雨中的一分钟"

- 时长：90 秒，哀歌式调性 → 约 15 个槽位，每个约 6 秒。
- 形状：清单（天气 + 城市的编目）。
- 主题性问题："雨向你展示了这座城市的什么？"

槽位草图（缩略）：

1. **主** 一滴雨以慢动作打在干燥沥青上
2. 门口撑开的伞，柔和的午后光
3. 霓虹招牌在水洼里的颠倒倒影，手持
4. 雨水横划过公交车窗，乘客柔焦
5. 出租车顶灯在大雨中推出来，长焦
6. 排水口吞下落叶与积水，俯拍
7. 街边小贩把塑料布拉过果蔬推车
8. 湿鹅卵石小巷，蒸汽升起，钨丝路灯
9. 灰色天空下的屋顶天线，全景
10. 儿童雨靴踩进水洼，低角度
11. **主** 透过雨幕看到的一扇亮灯公寓窗
12. 夜里的雨刮，远处是彩色城市灯光
13. 停放自行车座上凝结的雨珠，微距
14. 车站瓷砖地面上正被水填满的脚印
15. **主** 灰云中透出的第一块蓝天

每个槽位都会拿到：

- 按名词加形容词模板写的 `description`，
- 2-3 条简短检索词（例如槽位 5：`"taxi heavy rain"、"yellow cab
  wet street night"、"city traffic downpour"`），
- `preferred_sources`（槽位 1-6 → pexels+archive_org，槽位 8 →
  用 archive_org 取年代质感，槽位 11 → pexels），
- 槽位 1、11、15 上的 `hero: true`，
- 加总约为 90 的 `target_hold_seconds`。

这就是素材导演将要据以执行检索的 artifact。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
