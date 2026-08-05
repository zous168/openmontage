# 素材导演 —— Documentary Montage 管线

## 何时使用

镜头表已经存在。你现在得真正出去把填满每个槽位的
片段找回来。有两条路径：

### 标准路径：素材库 + CLIP 检索

1. **建素材库** —— 把场景导演的检索词扇出到
   所有可用的素材来源（Pexels、Pixabay Video、Coverr、Mixkit、
   Archive.org、NARA、美国国会图书馆、Pond5 PD、Videvo、NASA、ESA、
   JAXA、NOAA、Dareful、Wikimedia、Unsplash），并下载/嵌入这些候选。
2. **逐槽位选片** —— 用每个槽位的描述对素材库跑 CLIP 检索，
   为每个槽位选出一个胜出者。

最适合：50 个以上槽位的制作、自动化的多样化处理，以及
CLIP 相似度排序确实重要的省心式槽位填充。

### 快速路径：直接检索（推荐用于逐幕制作）

1. **检索并下载** —— 用 `direct_clip_search` 把检索扇出到
   所有可用 provider，每条检索词下载 2-3 个片段。
   不做 CLIP 嵌入、不建素材库索引、没有 .npy 文件。
2. **检视缩略图** —— 浏览抽取出来的缩略图（或用一个
   子 agent），对照槽位描述确认视觉是否匹配。
3. **把片段映射到槽位** —— 基于目视检查，手工把最佳片段
   分配给每个槽位。

最适合：幕与幕之间有用户复看的逐幕制作、快速
迭代、每幕槽位数在 30 以内的制作。

**跨幕复用：** 逐幕制作时，为前面几幕下载的片段
可以填充后面几幕的槽位。把 agent 指向先前下载的目录，
复用那些匹配新槽位描述的片段。这在实际制作中省下了
40-50% 的下载时间。

**并行工作流：** 在 `direct_clip_search` 后台运行的同时，
可以并行生成 TTS 旁白、做音频混音、制作字幕、检索音乐。
这能大幅缩短总制作时间。

**兜底：** 若快速路径在某些槽位上找不到好的视觉匹配，
就只对那些槽位改用 `corpus_builder` + `clip_search`。
两种做法并不互斥。

产出是一份 `asset_manifest`，把每个槽位映射到唯一一个
带完整来源信息的片段。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]` | 槽位描述 + 检索词 + preferred_sources |
| 上游 artifact | `state.artifacts["idea"]["brief"]` | `era_mix`、`sources_allowed`、`music_plan` |
| 工具（快速路径） | `direct_clip_search` | 轻量的多 provider 检索 + 下载 |
| 工具（标准路径） | `corpus_builder` | 用 CLIP 嵌入填充检索索引 |
| 工具（标准路径） | `clip_search` | 按槽位描述给片段排序 |
| 工具（可选） | `music_gen`、用户的 `music_library/` | 配乐铺底 |

## 心智模型

素材库**不是**一个素材仓库。它是一个 agent 按需构建的
检索索引。你不去滚动浏览它 —— 你去查询它。

由此推出三条规则：

1. **先建库，再选片。** 绝不要对一个不包含该槽位检索词族
   候选的素材库调用 `clip_search.rank_for_slot`。
   排序会返回垃圾，你会白白浪费掉这个槽位。
2. **只增不换。** 素材库是只追加的。若某个槽位的
   检索结果很弱，就加更多检索词重建 —— 不要推倒重来。
3. **按槽位选，不是按片段选。** 在最终剪辑里，每个片段只属于
   一个槽位。用 `exclude_ids` 防止重复使用。

## 儿童 / 童话类内容 —— 来源覆盖

当场景方案的 `metadata.tone` 或 `metadata.target_audience`
指向儿童内容（童话、睡前故事、儿童讲解、
动画故事）时，**覆盖常规的来源路由**，只从 Pixabay Video 获取素材。

### 为什么只用 Pixabay Video

Pixabay 的社区库里有数千条 AI 生成的奇幻
动画 —— 发光的森林、被施魔法的风景、神奇生物 ——
由使用 Midjourney/Stable Diffusion 视频工作流的创作者上传。
它们在吸引儿童注意力方面远胜真实素材。
没有其他免费来源在这种风格上有可比的深度。

### 获取规则

1. **锁定来源。** 给**所有**检索词设 `sources: ["pixabay_video"]`。
   不要把真实素材 provider（Pexels、Dareful 等）与
   奇幻片段混用 —— 风格冲突会破坏儿童的沉浸感。

2. **改写检索词。** 场景导演应该已经把槽位描述
   改写成奇幻风格了。若你需要写兜底检索词，就在前面加上
   奇幻关键词：
   - 魔法关键词：`fairy tale`、`fantasy`、`enchanted`、`magical`、
     `glowing`、`dreamy`、`mystical`、`fairy`、`enchanted forest`、
     `magical world`
   - 示例：槽位需要"叶子上的毛毛虫" → 检索词写
     `"fairy tale caterpillar magical forest glowing"`

3. **视觉一致性检查。** 下载之后，确认**所有**
   片段共享 AI 生成的奇幻美学。任何看起来像真实素材的
   片段都要否决 —— 哪怕它的 CLIP 分数更高。
   一段真实片段混进奇幻蒙太奇里，魔法就破了。

4. **兜底。** 若 Pixabay 对某个槽位没有返回奇幻结果，
   先换不同的奇幻关键词改写检索词，再去尝试
   更宽泛的词。每个槽位最多改写两次。若仍然为空，就把
   这个槽位标出来交给用户 —— 不要静默换成真实素材。

## 流程 —— 快速路径（直接检索）

在幕与幕之间有用户复看的逐幕制作中，或总槽位数
在约 30 以内时使用这条路径。

### F1. 后台运行 `direct_clip_search`

在你并行处理旁白/音频/字幕的同时把检索发出去：

```python
direct_clip_search.execute({
    "output_dir": "projects/<name>/assets/video/raw_act2",
    "queries": [
        {"query": "cesium atomic clock laboratory", "slot_id": "slot_01"},
        {"query": "laser beam laboratory optics",   "slot_id": "slot_02"},
        {"query": "satellite dish night sky",        "slot_id": "slot_03"},
        # ... 每个槽位一条
    ],
    "sources": ["pexels", "pixabay_video", "coverr", "mixkit", "archive_org"],  # 或省略以使用全部可用来源
    "clips_per_query": 3,
    "filters": {
        "min_duration": 3,
        "max_duration": 40,
        "orientation": "landscape",
        "min_width": 1280,
    },
})
```

**关键参数：**
- `clips_per_query=3` 是甜点。选择够用，下载够快。
- 省略 `sources` 即自动检索所有可用 provider。
- 设 `skip_existing=true`（默认）以避免重试时重复下载。

### F2. 检视缩略图

浏览 `<output_dir>/thumbnails/` 逐个确认片段。必要时用子 agent
读取缩略图做视觉确认。

对每个槽位，从下载到的这一组里挑出匹配最好的片段。

### F3. 跨幕复用

做第 2-5 幕时，先看看前面几幕的片段，再去
下载新的。各幕之间存在大量主题重叠：

- 实验室素材（显微镜、激光、科研人员）
- 科技镜头（服务器、卫星、电路）
- 自然/抽象素材（山脉、太空、延时）

在跑新检索之前，先把 agent 指向前几幕的目录，把已有片段
映射到新槽位上。

### F4. 用定向检索补缺

若首轮检索之后某些槽位仍然没有好的匹配：
1. 改写检索词（更具体的名词、不同的词汇）。
2. 只对那些检索词跑 `direct_clip_search`。
3. 若仍无匹配，就只对那些特定槽位退回到 `corpus_builder` + `clip_search`。

### F5. 记录 Asset Manifest

格式与标准路径相同（见下面第 9 步）。只是 `source_tool`
字段应为 `"direct_clip_search"` 而不是 `"corpus_builder"`。

---

## 流程 —— 标准路径（素材库 + CLIP 检索）

用于大型制作（50 个以上槽位）、需要自动化的
CLIP 排序时，或者快速路径匹配效果不佳时。

### 1. 确定素材库目录

决定素材库放在哪。约定：

```
projects/<project-name>/corpus/
```

同一个 `corpus_dir` 会传给每一次 `corpus_builder` 和
`clip_search` 调用。素材库在多次运行之间可复用 —— 若
场景导演之后又加了槽位，你可以在同一个素材库上扩充，而不必
从头重建。

### 2. 把检索词扇出到 `corpus_builder`

读 `scene_plan.metadata.slots[]`。把每个槽位的每个 `queries[]` 数组
收集起来。去重。按 `preferred_sources` 分组。

按来源组合，每组调用一次 `corpus_builder.execute(...)`：

```python
# 示例形态。agent 从镜头表构造它。
corpus_builder.execute({
    "corpus_dir": "projects/<name>/corpus",
    "queries": [
        {"query": "raindrop on asphalt slow motion", "kind": "video", "per_source": 8},
        {"query": "wet city street night neon",       "kind": "video", "per_source": 8},
        {"query": "taxi heavy rain yellow",           "kind": "video", "per_source": 6},
        # ... 每个不重复的槽位检索词一条
    ],
    "sources": ["pexels", "archive_org", "wikimedia"],   # 取自 preferred_sources 的并集
    "filters": {
        "min_duration": 3,
        "max_duration": 40,
        "orientation": "landscape",
        "min_width": 1280,
    },
    "max_new_clips": 150,          # 扩大搜索空间
    "thumbs_per_video": 5,
})
```

**扇出的规则：**

- 若 brief 钉死了某个来源，而 `corpus_builder.source_provider_menu`
  说那个来源不可用，就**停下**并把它呈现出来。不要静默地
  退到其余来源。
- 素材库容量按槽位数的 8-12 倍来预算。一支 15 槽位的蒙太奇想要
  约 150 个候选，检索才有真正的选择余地。
- 每条检索词的 `per_source` 取 4-8 通常就够。推到 20 以上
  多半只是增加噪声。
- 若 `era_mix = "vintage"`，就单独跑一次限定在
  `["archive_org"]` 的扇出，并用符合年代的检索词。Prelinger 检索
  很慢 —— 不要把它和现代的 Pexels 批次交织在一起。
- 若任何槽位的 `preferred_sources` 里有 `nasa`，就单跑**一次**
  仅限 `nasa` 的小批次。NASA 很慢，结果也很小众。
- `unsplash` 只有图像。把它当作辅助来源，而不是
  以运动为主的纪录片剪辑的主干。

### 3. 检索之前先给素材库做体检

在把 token 花在逐槽位选片之前，用
`operation=stats` 调一次 `clip_search`：

```python
clip_search.execute({
    "operation": "stats",
    "corpus_dir": "projects/<name>/corpus",
})
```

看 `rows`、`per_source`、`per_kind`、`mean_motion_score`。你要
排查三种失败模式：

- `rows < 50` —— 素材库太小。把它扩大。
- 复古 brief 上 `per_source` 严重倾斜（例如 98% pexels、2% archive_org）
  —— 跑一次定向的 archive_org 扇出。
- `mean_motion_score < 1.0` —— 素材库里全是静态片段，会
  做成幻灯片。换检索词重跑，或在排序时施加
  `motion_min`。

### 4. 逐槽位给候选排序

对 `scene_plan.metadata.slots[]` 中的每个槽位，用
`operation=rank_for_slot` 调用 `clip_search`：

```python
clip_search.execute({
    "operation": "rank_for_slot",
    "corpus_dir": "projects/<name>/corpus",
    "query_text": slot["description"],      # 不是 slot["queries"] —— 描述信息更丰富
    "k": 30 if slot.get("hero") else 12,
    "tag_weight": 0.3,
    "motion_min": 1.5,
    "kind": "video",
    "exclude_ids": already_picked_ids,      # 全局累加器
})
```

要点：

- 使用槽位的 **description**，而不是 queries。描述是
  场景导演写的那串信息丰富的名词加形容词。CLIP
  对它的排序效果好过短检索短语。
- `tag_weight=0.3` 把视觉嵌入（70%）与来源标签嵌入（30%）混合。
  当 Pexels 的 URL 标签很强而视觉通道很嘈杂时提到 0.5。
  对标签是长篇散文的 Prelinger 素材降到 0.15。
- 每次都要把已经锁定到某个槽位的所有片段传进 `exclude_ids`，
  免得同一个"钥匙插门"的片段在两个槽位都胜出。

### 5. 用判断力选片，不要唯分数论

排名第一的结果未必就是对的选择。看看前 3-5 个，
从以下角度逐个判断：

- **年代匹配。** 一个 2022 年的 4K Pexels 镜头，属于一支关于家的
  哀歌式清单蒙太奇吗？也许属于。也许不。
- **运动匹配。** 场景导演的调性表告诉你
  停留会有多长。若这个槽位的停留目标是 4.0 秒，而
  片段只有 2 秒且带一个快速甩镜，它拉不长。
- **构图承接。** 这个片段挨着相邻槽位选中的片段
  时还成立吗？你现在还不知道 —— 但若 slot_02
  是一个雨中屋顶的全景，而 slot_03 排名第一的也是
  雨中屋顶全景，那就改选第 2 名。
- **情绪基调。** CLIP 会很乐意把"夜晚空荡的城市
  人行道"匹配到一个明亮霓虹的拉斯维加斯空镜。那个霓虹镜头对
  哀歌式的 brief 而言是**错的**。0.42 的分数不能压过调性。

**可接受分数的经验值（CLIP ViT-B/32 余弦相似度）：**

- `>= 0.30` —— 强匹配，通常可用。
- `0.22-0.30` —— 说得过去，需要人工判断。
- `< 0.22` —— 素材库里没有你要的东西。去扩充它，
  不要硬选。

### 6. 检索结果弱时就扩充素材库

若某个槽位的最高分低于 0.22，**不要**在一堆烂结果里
挑最好的那个。改为：

1. 改写这个槽位的检索词 —— 可能太抽象，也可能对该年代
   用错了词汇。
2. 只用那些新检索词，为这一个槽位再跑一次
   `corpus_builder.execute(...)`。builder 会跳过索引里已有的片段，
   所以这很便宜。
3. 重新排序。

每个槽位扩充两轮足够了。若三轮都找不到
高于 0.22 的分数，就告诉创意导演：这个槽位在开放素材库中
拍不出来，并建议要么删掉这个槽位，要么让
用户自己提供素材。

### 7. 让相邻选片多样化

一旦每个槽位都有了一个候选，你就得到了一串按时间线顺序排列的
clip_id。视觉上冗余的相邻镜头会毁掉剪辑。对这个列表跑
`clip_search.diversify`：

```python
clip_search.execute({
    "operation": "diversify",
    "corpus_dir": "projects/<name>/corpus",
    "candidate_ids": picked_ids_in_timeline_order,
    "n": len(picked_ids_in_timeline_order),
    "diversity": 0.5,
})
```

若 `diversify` 丢掉了某个片段，它是在告诉你：你的两个选片
在视觉上是一样的。把被丢掉那个槽位重新排序，并把
存活下来的那个"双胞胎"放进 `exclude_ids`。

### 8. 处理音乐方案

读 `brief.music_plan`。**严格**执行创意导演记录的那个方案 ——
不要在这里另发明一个来源：

- **`source=library`**：确认 `music_plan.path` 处的文件存在。
  在 asset manifest 中记为 `type=music`、`subtype=library`。
- **`source=user`**：同上，`subtype=provided`。
- **`source=generated`**：用 brief 中的种子提示词调用指定的
  音乐工具。先出样本，确认情绪之后再批量。记录 provider 和成本。
- **`source=none`**：不要去生成静音。不要因为剪辑感觉单薄就
  塞一首曲子进去。若用户批准了"不要音乐"，就真的不带音乐跑。

**在这个阶段绝不切换音乐来源。** 那属于违反决策
沟通契约 —— 更改音乐模式是重大的制作变更，需要在 proposal 阶段
取得用户批准。

### 9. 记录 Asset Manifest

按规范 schema 为每个槽位产出一个 asset。documentary-montage
专属的字段放在 `metadata` 里：

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "asset_slot_01",
      "type": "video",
      "path": "projects/<name>/corpus/clips/pexels_12345/video.mp4",
      "source_tool": "corpus_builder",
      "scene_id": "slot_01",
      "duration_seconds": 7.2,
      "resolution": "1920x1080",
      "format": "mp4",
      "provider": "pexels",
      "license": "Pexels License (free, no attribution required)",
      "original_url": "https://www.pexels.com/video/12345",
      "subtype": "stock",
      "generation_summary": "Retrieved via CLIP rank for slot 'raindrop on asphalt slow motion...'. Score 0.38."
    },
    {
      "id": "asset_music_bed",
      "type": "music",
      "path": "music_library/dawn_04.mp3",
      "source_tool": "music_library",
      "scene_id": "global",
      "subtype": "library",
      "license": "user-provided"
    }
  ],
  "metadata": {
    "pipeline": "documentary-montage",
    "corpus_dir": "projects/<name>/corpus",
    "corpus_stats": { "rows": 157, "per_source": {"pexels": 98, "archive_org": 52, "nasa": 7} },
    "rejected_picks": [
      {
        "slot_id": "slot_03",
        "clip_id": "pexels_99921",
        "score": 0.41,
        "reason": "wrong era — 2022 4K kitchen, brief is vintage"
      }
    ]
  }
}
```

`rejected_picks` 这份记录很重要。当某个选片感觉不对、
需要取第 2 名时，剪辑导演会去读它。

### 10. 质量门

- 场景方案中的每个槽位都恰好映射到一个素材。
- 每个被选中的片段在 rejected-picks 记录中都有 `score >= 0.22`
  （或者有一条记录在案的"用户批准的覆盖"说明）。
- 没有任何 clip_id 同时作为两个槽位的首选出现。
- `diversify` 在最终列表上跑得干净（没有被丢弃的选片，
  或者所有被丢弃的都已重新补齐）。
- `corpus_stats` 显示 rows 至少是槽位数的 8 倍。
- 音乐素材存在，**或** `music_plan.source = "none"` 且有明确的
  确认说明。
- 对复古 brief，至少 60% 的选片来自 `archive_org`。
- 所有文件路径都能解析。

## 常见陷阱

- **对着空素材库跑 `clip_search.rank_for_slot`。**
  你会得到一个空的 `results` 列表或一个莫名其妙的形状错误。
  建库之后、排序之前，务必先调 `stats`。
- **只按分数选片。** 分数是判断的输入，不是
  判断本身。一支哀歌式作品若塞满了高分的 Pexels HD 阳光镜头，
  无论分数多高都会感觉不对。
- **忘了 `exclude_ids`。** 没有它，同一个惊艳片段会在
  每个槽位都胜出，蒙太奇就变成同一张图的幻灯片。
- **静默替换音乐。** 用户说了"不要"，agent 却因为"剪辑
  感觉单薄"照样生成了。这是重大变更，
  需要批准 —— 见 `skills/pipelines/documentary-montage/executive-producer.md`
  的跨阶段规则。
- **无节制地扩充素材库。** 每个弱槽位扩充两轮
  就是上限。超过之后，开放素材库里多半根本
  没有这段素材，该改的是槽位本身。
- **把槽位的 queries 当作排序文本。** queries 是给素材 API 的
  检索短语；description 才是给 CLIP 的语义文本。它们是
  两回事。要按 description 排序。
- **丢失来源信息。** 每个片段在 manifest 中都必须带上 `provider`、
  `original_url` 和 `license`。这些是任何下游发布步骤
  不可妥协的前提。

## 检索配方

几个经常用到的检索动作：

### "找 N 个我喜欢的这个片段的变体"

```python
clip_search.execute({
    "operation": "find_similar_set",
    "corpus_dir": "projects/<name>/corpus",
    "seed_clip_id": "pexels_12345",
    "n": 5,
    "diversity": 0.4,
    "candidate_pool": 40,
})
```

用于某个槽位想要"再来五个像这样的镜头"时 —— 例如
一份全部以同一基调拍摄的门口编目。

### "我有 20 个候选，缩到 8 个不冗余的选片"

```python
clip_search.execute({
    "operation": "diversify",
    "corpus_dir": "projects/<name>/corpus",
    "candidate_ids": [...],
    "n": 8,
    "diversity": 0.5,
})
```

### "查某个片段的完整元数据"

```python
clip_search.execute({
    "operation": "get",
    "corpus_dir": "projects/<name>/corpus",
    "clip_id": "archive_org_Prelinger_HomeMovies_0042",
})
```

用于剪辑导演在锁定剪辑之前想确认 provider/URL 时。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
