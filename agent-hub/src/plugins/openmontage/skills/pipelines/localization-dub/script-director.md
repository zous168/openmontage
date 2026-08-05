# 脚本导演 —— Localization Dub 管线

## 何时使用

把已获批的本地化 brief 转化成一份有转写稿支撑、可供审校的逐语种脚本包。本阶段应当在生成任何配音音频之前先建立文本上的事实基准。

## 参考输入

- `docs/localization-dubbing-best-practices.md`
- `skills/creative/storytelling.md`

## 流程

### 1. 建立源转写稿的事实基准

从源转写稿出发，修正以下方面的明显错误：

- 人名，
- 术语，
- 说话人归属，
- 数字，
- CTA 措辞。

### 2. 产出可供审校的目标语文案

对每个目标语种，生成可以在合成之前被审校的文本。记录哪些术语应当保持不变。

### 3. 在可行处保留结构

除非译文明显需要另一种节奏策略，否则让段落时序和顺序与源片保持一致。

### 4. 用元数据做本地化管控

推荐的元数据键：

- `source_transcript_status`
- `target_language_sections`
- `glossary_terms`
- `protected_terms`
- `pronunciation_notes`
- `review_status_by_language`

### 5. 质量门

- 源转写稿足够可靠、值得信任，
- 每个计划中的交付物都有对应的目标语文案，
- 术语表中的术语得以保留，
- 这份脚本包能在音频生成之前被审校。

### 生产中途的事实核验

若你在写脚本时遇到不确定之处：
- 在把某个事实性论断写进脚本之前，用 `web_search` 核实它
- 用 `web_search` 找参考图以保证视觉准确性
- 在 decision log 中记录核验：`category="visual_accuracy_check"`

脚本中的每一条事实性论断都应当能追溯到 `research_brief`。
若你做出了调研中没有的论断，就补做调研并补上来源。不要编造统计数字、日期或出处。

## 常见陷阱

- 用未经审校的转写稿去生成音频。
- 让产品名在不同语言之间发生漂移。
- 把译文当成最终时序，却不承认长度会漂移。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
