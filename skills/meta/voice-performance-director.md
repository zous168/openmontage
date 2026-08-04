# 配音表演导演

任何管线只要会用 TTS 生成旁白，就使用这个元技能。

目标是让生成的旁白听起来是**被导演过的**，而不只是被念出来的。不要把
表现力留成提示词里一句"自然地读"。要把一份具体的配音表演
计划从脚本一路带到素材生成，然后用样片去验证它。

## 必需契约

每份以旁白为主的脚本都应包含一个顶层 `voice_performance`
对象，并在 schema 允许的地方包含段落级的 `delivery_cues`。

顶层配音表演：

```json
{
  "performance_intent": "Warm, decisive product narrator with human pauses.",
  "pacing_profile": "conversational",
  "energy_curve": "measured hook, warmer middle, more deliberate close",
  "pause_policy": "Use short pauses after setup lines and longer pauses before reversals or important claims.",
  "provider_notes": {
    "openai": "Use instructions for emotional arc and emphasis.",
    "google_tts": "Use SSML input with break tags when the selected voice supports it.",
    "elevenlabs": "Use lower stability and moderate style for expressive narration."
  }
}
```

段落级演绎提示：

```json
{
  "pace": "measured",
  "energy": "curious",
  "emphasis_words": ["not", "process"],
  "pause_before_seconds": 0.2,
  "pause_after_seconds": 0.7,
  "delivery_note": "Set up the contrast, then slow down on the final phrase.",
  "provider_text": "This is not just another tool. <break time=\"0.6s\"/> It is a process."
}
```

## 撰写规则

- 写口语，不要写书面语。多用短句、适度的缩写，以及清晰的标点。
- 把静默当作结构。在转折之前、令人意外的论断之后，以及
  最终结论之前加停顿。
- 停顿标记要有目的。break 太多会显得做作而拖沓。
- 避免 "natural"、"engaging"、"expressive" 这类笼统指示，
  除非它们与确切的语速、重音、停顿或能量提示配对出现。
- 每个段落最好只有一个演绎构想。若一个段落需要三次情绪
  转折，就把它拆开。

## Provider 映射

- OpenAI TTS：发送 `instructions` 时使用 `model: "gpt-4o-mini-tts"`。
  把情绪弧线、节奏、重音和角色写进 `instructions`；输入文本
  保持干净但要有标点。不要给 `tts-1` 或 `tts-1-hd` 发 `instructions`。
- Google TTS：只有在加 break 标签或其他 SSML 时才用
  `input_type: "ssml"`。工具会把它映射到 Google 的 `input.ssml`，并在需要时
  用 `<speak>...</speak>` 包裹。`speaking_rate` 保持在 Google 支持的
  `0.25..2.0` 范围内，pitch 在 `-20..20`。
- ElevenLabs：想要更多变化就调低 `stability`，想要表现力就用中等
  `style`，`speed` 保持在该 provider 的 `0.7..1.2` 范围，并把
  `similarity_boost` 保持得足够高以保住音色。
- 离线/基础音色：依靠标点、更短的句子和显式的
  分段切分，因为 provider 级的情绪控制可能不可用。
- **Piper**：在 `provider_notes` 中设置 `length_scale`（明快的 UGC 典型值为
  **0.92–1.05**；绝不低于 **0.85**）。低于 1.0 的值会加快语速；assets
  阶段**不得**使用比脚本指定的更快的 `length_scale`。

## 可听性下限（硬规则）

旁白必须保持在**正常可听语速**范围内。当音频
长于画面时间线时，去修时间线或删减文案 —— 绝不要把语速压缩到
超出这些界限，除非有用户明确批准，并记录为
`category: downgrade_approval`、`subject: "Narration speech rate"`。

| 控制项 | 允许范围（无需额外批准） | 若超出 |
|---------|-----------------------------------|-------------|
| Piper `length_scale` | **0.85 – 1.25**（优先采用脚本 `provider_notes`） | CRITICAL 级 reviewer 发现 |
| TTS 后的 `atempo` | **0.92 – 1.05** | CRITICAL —— 禁止用于强行适配时间线 |
| 脚本 vs 素材 | 素材**不得**快于脚本的 `provider_notes` | CRITICAL |

**错误做法：** TTS 跑出 14 秒，视频目标 11 秒 → 设 `length_scale=0.66` + 用 atempo 硬凑。
**正确做法：** 把 `edit_decisions` 的 cuts 延长到 14 秒，或缩短脚本，或请用户接受更快的语速。

`lib.production_audit.check_project_voice_listenability()` 会在
`asset_manifest.generation_summary` 中标出违规（例如 `length_scale=0.66`、`atempo fit`）。

## 样片门禁

批量生成旁白之前：

1. 从**最考验表演的那一段**生成样片，而不是自动取
   第一段。
2. 验证音色、语速、停顿、重音和情绪弧线。
3. 若样片听起来很平，就在生成其余部分之前调整
   `voice_performance` 计划或 provider 参数。
4. 把获批的样片路径和 provider 参数记入 asset manifest。

## 失败条件

把这些视为质量失败：

- 以旁白为主的脚本没有 `voice_performance` 计划。
- 段落指示只写了 "read naturally" 或 "expressive"，却没有具体的
  停顿、重音、语速或能量提示。
- 样片获批之后，TTS provider、音色、语速或模型发生了变更，却没有
  重新出一版样片。
- 明明存在结构化的 `provider_text` 或 `delivery_cues`，最终旁白却是从
  原始脚本文本生成的。
