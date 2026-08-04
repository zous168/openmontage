# Seedance 2.0 —— 提示词指南

> Layer 3 权威来源：`.agents/skills/seedance-2-0/SKILL.md`
> 通用词汇表见：`skills/creative/video-gen-prompting.md`

## 何时选 Seedance 2.0

Seedance 2.0（字节跳动 Seed 团队，2026 年 2 月发布）是 OpenMontage 在配置了付费网关（经 `seedance_video` 的 `FAL_KEY`，或 HeyGen Video Agent / Avatar Shots）时，**用于电影感、预告片、先导片、燃向剪辑和运动主导片段的首选高端默认项**。它是全队中唯一同时具备以下全部能力的模型：

- 单次生成即带原生同步音频（对白 + 音效 + 环境声一起出，不是事后同步），
- 单条提示词内完成多镜头生成，
- 导演级镜头控制，
- 由引号内对白驱动的唇形同步，
- 参考图约束生成，最多 9 张图 + 3 段视频 + 3 段音频，
- 跨镜头保持角色身份一致。

发布时在 Artificial Analysis 上 Elo 1269 —— 领先于 Veo 3、Sora 2、Runway Gen-4.5。

只有在确有理由时才不用 Seedance 2.0：预算紧张（改用 `fast` 变体或 LTX）、用户明确偏好（VEO/Sora/Kling），或者别的模型在某种风格上做得更好（写实风景用 VEO，动漫用 Kling）。

## Seedance 2.0 的 8 组件提示词结构

Seedance 对镜头语言、多镜头切分和引号内对白的理解异常字面。使用这个结构 —— 该写的写上，无关的省略：

1. **景别 / 构图** —— 远景定场、中景、特写、荷兰角等
2. **镜头运动** —— 静止、缓慢推近、航拍、手持、弧线、变焦推轨
3. **主体描述** —— 必须跨镜头保持不变的外形细节（身份锚点）
4. **动作节拍** —— 一句一个节拍，多镜头时用 `→` 或明确的 `Shot 1 / Shot 2`
5. **环境 / 场景** —— 地点、年代、天气、时段
6. **光照 / 配色** —— 一个光照构想，选定就坚持
7. **风格 / 调色 / 年代** —— "anamorphic lens, teal-orange grade, 35mm film grain"
8. **音频** —— 环境声、有源声、音乐方向（只描述质感）、用于唇形同步的引号对白

## Seedance 的专属长处

| 能力 | 如何调用 |
|---|---|
| **原生同步音频** | 在提示词里描述声音景观。保持 `generate_audio=true`。 |
| **单次生成多镜头** | 使用 `Shot 1 (...)`、`Shot 2 (...)` 等。各镜头之间保持主体描述一致。 |
| **导演级镜头** | 使用无歧义的术语：`slow dolly-in`、`arc shot`、`Dutch tilt`、`aerial push-in`、`handheld with micro-shake` |
| **由引号对白驱动的唇形同步** | `Character says: "line."` —— 快切镜头上每句 ≤ 约 6 词 |
| **参考图转视频** | 使用 `reference-to-video` 端点；在提示词中为每个素材命名（`Reference 1: hero character — ...`） |
| **角色身份一致性** | 在每个镜头里描述完全相同的外形细节 —— Seedance 以此作为身份锚点 |

## 多镜头范式

> **在每个镜头里逐字重复身份描述。** "the same character" / 代词 / "Aang again" 都不管用。在每个镜头块里逐字重复那 3–6 条可区分的视觉属性。Seedance 处理每个镜头时，就像你是第一次提到它一样。

Seedance 会遵守显式的镜头表：

```
Shot 1 (wide aerial establishing, slow push-in):
Snow-covered Air Temple at dawn, spires catching first orange light.
Wind lifting prayer flags.

Shot 2 (medium, low angle, handheld):
Aang — bald, blue arrow tattoo, orange robes — plants his staff on stone.
He squints into the rising sun.

Shot 3 (extreme close-up, rack focus):
Rack focus from the glowing arrow tattoo on his forehead to the distant peaks.
Aang says: "It's time."

Style: anamorphic lens, teal-orange cinematic grade, 35mm film grain.
Audio: rising orchestral swell with low taiko pulse, wind, distant wingbeats.
```

### 多镜头中的主体转换原语

Seedance 能处理主体进入或退出镜头的四种不同方式。明确点名这个原语，有助于模型在镜头之间构建正确的转换。

- **主体显现**（由相机运动**或**主体运动造成）—— 主体在镜头中途变得可见。
  示例：`Shot 2 (slow truck right): empty corridor at first; the camera trucks right to reveal Aang — bald, blue arrow tattoo, orange robes — pressed flat against the wall.`

- **主体消失** —— 主体通过运动或被遮挡而离开画面。
  示例：`Shot 4 (static wide): Aang — bald, blue arrow tattoo, orange robes — sprints into the temple doorway and is swallowed by shadow; camera holds on the empty threshold.`

- **主体切换**（rack focus / 相机运动）—— 焦点或构图从一个主体转移到另一个。
  示例：`Shot 5 (close-up, rack focus): rack focus from Aang's glowing arrow tattoo in foreground to Sokka — dark hair, blue tunic, boomerang on back — emerging from the mist behind.`

- **复杂交替焦点** —— 焦点在一个镜头内于两个主体之间来回摆动。
  示例：`Shot 7 (medium two-shot, alternating rack focus): focus on Aang — bald, blue arrow tattoo, orange robes — as he speaks, then pulls to Katara — long brown hair, blue water-tribe parka — as she answers, then back to Aang on the final beat.`

## 唇形同步范式

```
Aang says: "I won't run anymore."
Sokka, half a step behind, replies: "Then we fight."
```

- 严格使用 `Character says: "..."` / `Character replies: "..."` —— 口型是以引号内的字符串为准生成的。
- 台词保持简短（快切镜头上 ≤ 6 词）以避免漂移。
- 单人独白时，把镜头保持在说话人身上的近景且静止。

## 参数速查

| 参数 | 指引 |
|---|---|
| `duration` | 主镜头 `5`–`8` 秒，多镜头场景 `10`–`12` 秒，插入镜头 `4` 秒。拿不准就用 `auto`。 |
| `aspect_ratio` | 预告片 `21:9`，广播 `16:9`，Reels/Shorts/TikTok `9:16` |
| `resolution` | 默认 `720p`。`480p` 仅用于成本受限的预览。 |
| `generate_audio` | 保持 `true` —— 同步音频是它的护城河。用不到就在 compose 阶段剥掉。 |
| `model_variant` | 主镜头 + 多镜头 + 镜头调度复杂时用 `standard`。B-roll、预览、延迟敏感任务用 `fast`。 |
| `seed` | 一旦某个镜头构图成立就锁定；用同一个 seed 迭代变体。 |
| `prompt length` | 主镜头 200–400 词；插入镜头 80–150 词。Seedance 是少数几个奖励长而结构化的五要素提示词的模型之一。 |

## 迭代策略

1. **先搭骨架** —— `duration=5`、`fast`、单镜头。确认构图。
2. **锁定 seed** —— 把它记进该片段的 README。
3. **升级到 `standard`** —— 同一个 seed，收紧镜头与光照的措辞。
4. **延长或转多镜头** —— 只在单镜头版本已经干净之后再做。
5. **提升为最终版** —— 把提示词、seed、变体和时长写进 asset manifest，这样 compose 就能重渲染出一致的重拍。

## 该避免什么

| 不要 | 为什么 |
|---|---|
| 一个镜头里四个及以上同时发生的动作 | 运动连贯性会崩。拆成多镜头。 |
| 片段内出现可读文字 / Logo | 文字渲染不可靠。文字交给 Remotion 叠加层处理。 |
| 相互冲突的光照（`bright noon` + `neon night`） | 模型会选一个并忽略另一个。 |
| 在快切镜头上写长对白 | 唇形同步会漂移。 |
| 用 `fast` 变体做慢动作、多镜头或复杂镜头 | 第一次尝试通常就会翻车。改走 `standard`。 |
| 要求 Seedance 生成完整的多乐器配乐 | 音频方向只描述质感；真正的配乐属于 `music` / `pixabay_music` / `elevenlabs`，在 compose 阶段混音。 |
| 无缘由地绕过 `video_selector` | 会丢掉打分、兜底和成本处理。 |

## 集成说明

- **Cinematic 管线：** Seedance 2.0 是默认。21:9、蒙太奇用多镜头，brief 附带视觉手册时用参考图转视频。
- **动画讲解：** 只把 Seedance 2.0 用于定场/氛围/冷开场片段 —— 核心动态图形仍留在 Remotion。
- **屏幕演示 / 播客 / 片段工厂：** 不适合作默认项。仅用于风格化的冷开场。
- **成本核对：** `standard` 10 秒在 fal.ai 上约 $3.03 / 段。`fast` 5 秒约 $1.21。在 proposal 阶段做预算。

## 示例 —— 降世神通预告片主镜头节拍（整支预告 60 秒，这是 7 个镜头中的第 3 个）

```
Shot 1 (wide aerial, slow push-in, 3s):
Snow-covered Air Temple at dawn, spires catching orange light,
prayer flags lifting in wind.

Shot 2 (low angle medium, handheld, 3s):
Aang — bald, blue arrow tattoo on forehead, orange and yellow robes —
plants his staff on weathered stone, squints into the rising sun.

Shot 3 (extreme close-up, rack focus, 3s):
Rack focus from the glowing arrow on his forehead to distant peaks.
Aang says: "It's time."

Lighting: cold blue ambient with warm break on the horizon,
rim light from rising sun.
Style: anamorphic 2.39:1, teal-orange cinematic grade, 35mm film grain,
halation on speculars.
Audio: low taiko drums rising to orchestral swell on Shot 3,
wind through temple, distant wingbeats, leather staff-grip creak.
```

参数：`duration=10`、`aspect_ratio=21:9`、`resolution=720p`、`model_variant=standard`、`generate_audio=true`，在第 2 个镜头之后锁定 seed。
