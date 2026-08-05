# 上手引导 —— 元技能

## 何时使用

在新会话中与用户的**第一次交互**、且用户尚未给出具体制作请求时 —— 或者他们的请求很含糊时（"帮我做个视频"、"你能做什么？"、"帮我创作点东西"）。

当用户带着具体、可执行的请求前来时（例如"做一支 60 秒关于黑洞的讲解视频"），跳过本技能。那种情况下直接进入 Rule Zero（确定管线 → preflight → 执行）。用户已经知道自己要什么了。

**本技能把 agent 从被动执行者变成创作伙伴。** 多数用户并不知道有什么可能性。你的任务就是展示给他们看 —— 快、清楚，并附上他们现在就能复制粘贴去试的提示词。

## 协议

### 第 1 步：运行 Preflight 发现

在说任何创意性的话之前，先搞清你手上有什么：

```bash
python -c "
from plugins.openmontage.tools.tool_registry import registry
import json
registry.discover()
envelope = registry.support_envelope()
menu = registry.provider_menu()
print('=== ENVELOPE ===')
print(json.dumps(envelope, indent=2))
print('=== MENU ===')
print(json.dumps(menu, indent=2))
"
```

把输出解析成三桶：

1. **可用** —— `status: AVAILABLE` 的工具
2. **快速解锁** —— `status: UNAVAILABLE` 且 `install_instructions` 只涉及一个环境变量的工具（1 分钟就能修）
3. **硬件解锁** —— 需要 GPU 或本地模型下载的工具

### 第 2 步：判定用户的配置档位

根据发现结果给配置分类：

| 档位 | 有什么可用 | 最合适的管线 |
|------|-----------------|----------------|
| **零 API key** | Piper TTS + Pexels/Pixabay 素材（若已加 key）+ Remotion 和/或 HyperFrames + FFmpeg | 动画讲解（素材库画面 + 免费旁白） |
| **入门** | 一个已配置的图像生成 provider + 免费 TTS + Remotion 和/或 HyperFrames | 动画讲解、Animation（AI 生成画面） |
| **标准** | 图像生成 + TTS + 音乐生成 | 动画讲解、Animation、屏幕演示、Hybrid |
| **完整** | 视频生成 + 图像生成 + 高端 TTS + 音乐 | 全部管线，包括 Cinematic、Avatar、Talking Head |
| **完整 + GPU** | 云端 API + 本地视频生成模型 | 全部管线，并有免费的本地兜底 |

**合成运行时** —— 两者都是一等公民，并在 provider 菜单中作为
各自独立的条目出现。分别报告各自的可用性：

- **Remotion** 需要 Node.js + `npx` + `remotion-composer/` + `node_modules`。
  最适合基于 React 的场景组件（文字卡、数据卡、图表）、
  词级字幕，以及 `TalkingHead` 数字人 composition。
- **HyperFrames** 需要 Node.js ≥ 22 + `npx` + FFmpeg。经由
  `npx @hyperframes/cli` 使用（不需要 checkout monorepo）。最适合
  HTML/CSS/GSAP 动态图形 —— 动态排版、产品宣传片、
  发布短片、网页转视频工作流、registry blocks。

当两者都可用时，在"可以直接开工"摘要里**明确点名两个运行时** ——
而不是只说 "Remotion"。一个全新会话的 agent 若不点名提到 HyperFrames，
就会在 proposal 阶段忘了呈现它；在这里点名，
是为了确立"agent 对运行时中立"这一预期。

若只有一个可用，就在摘要里说明，并提一句另一个能解锁什么。
若两个都不可用，就告诉用户他们只能走 FFmpeg（简单的拼接/修剪），
以及解锁 HTML/React 合成需要什么。

**上手引导阶段不要选定运行时。** 运行时选择发生在
proposal 阶段，也就是 agent 理解了 brief 之后。上手引导期间
你只是在报告能力，不是在做生产决策。
见 `AGENT_GUIDE.md` → "Present Both Composition Runtimes (HARD RULE)"。

### 第 3 步：问候与定位

呈现一份**简短、友好的能力摘要**。**不要**把原始的 provider 菜单倒出来。要把它翻译成平实语言。

**模板（按实际发现结果调整）：**

---

**欢迎使用 OpenMontage！** 我是你的视频制作 agent。在你当前的配置下，我能做这些：

**可以直接开工：**
- [用平实语言列出 2-4 项关键能力，例如"用免费离线 TTS（Piper）生成旁白"、"用弹簧转场、字幕和图表制作动画视频（Remotion）"、"来自 Pexels 的素材片段与图片"]

**可用的管线：** [列出在他们配置下可跑的管线，每条一句话说明]

**快速升级：** [若适用 —— 根据用户缺失的能力和 `provider_menu()` 里的实际安装说明，总结最有价值的 1-2 项解锁。不要把 `FAL_KEY` 或任何 provider 硬编码为默认建议。]

---

**这段呈现的规则：**
- 以"有什么能用"开场，而不是"缺什么"。用户应当感到被赋能，而不是被指出不足。
- 控制在 8-12 行以内。别把人淹了。
- 最多提 2 条快速解锁建议。不要为每一个缺失的 key 唠叨。
- 从注册表读取真实的 `install_instructions` —— 不要硬编码 provider 名或 key 名。

### 第 4 步：给出启动提示词

根据用户档位，呈现 **3 条可以马上用的提示词**。它们应当能与用户的具体配置很好配合，并产出令人印象深刻的结果。

**零 API key 档位的提示词：**

> **现在就试试：** "Make a 45-second animated explainer about why the sky is blue"
>
> 它会调研主题、写脚本、找素材库画面、用 Piper 生成旁白，并合成一支带转场和字幕的动画视频 —— 全程免费。

> **也可以试：** "I have a screen recording of a dashboard workflow — make it a polished product demo with captions and a voiceover" *（Screen Demo 管线）*

> **或者：** "Turn this interview recording into 3 short clips for TikTok and YouTube Shorts" *（Clip Factory 管线）*

**入门档位的提示词（有图像生成）：**

> **试试这个：** "Create an animated explainer about how CRISPR gene editing works, with AI-generated visuals"
>
> 我会用你配置好的图像生成器为每个场景创作定制画面 —— 比素材库视觉冲击力强得多。

> **也可以试：** "Make a short documentary-style video about urban beekeeping — keep it grounded and textural, not flashy" *（Hybrid 管线 —— 源素材 + 生成的补充素材）*

> **或者：** "Create a classroom-ready video teaching photosynthesis to 8th graders — simple, clear, and engaging" *（Explainer 管线 —— 教学模式）*

**完整档位的提示词（有视频生成）：**

> **试试这个：** "Create a cinematic 30-second trailer for a sci-fi concept: humanity receives a warning from 1000 years in the future"
>
> 我会生成真正的动态视频片段、编配配乐，并交付一支成品级电影感预告片。*（Cinematic 管线）*

> **也可以试：** "Make a 60-second avatar spokesperson video announcing a company rebrand" *（Avatar Spokesperson 管线）*

> **或者：** "I recorded a founder update on my webcam — make it feel polished, confident, and premium without looking fake" *（Talking Head 管线）*

**基于参考的提示词（所有档位适用）：**

> **有喜欢的视频？** 贴一个 YouTube 链接，说 "make me something like this"
> —— 我会分析它的风格、节奏和结构，然后给出 2-3 个创意变体
> 供你挑选。支持 YouTube、Shorts、Instagram Reels 和 TikTok。
> 所有分析都在本地免费运行 —— 不需要 API key。

> **有自己的素材？** 丢进一个视频文件，说 "I want to make a video using
> this footage" —— 我会转写它、检测场景，并提出一份剪辑方案。

**提示词建议的规则：**
- 恰好给 3 条提示词。
- 第一条应当是他们的配置所能产出的最惊艳的东西。
- 每条提示词针对不同的管线或风格。
- 附一句简短说明，解释这条提示词为什么适合他们的配置。
- 用引用块格式，让提示词在视觉上突出且便于复制。
- 始终把上面基于参考的提示词包含进去 —— 它们在每个档位都适用。

### 第 5 步：（简要）说明工作流程

给出提示词之后，用 2-3 句总结一下开始之后会发生什么：

"你给我一条提示词之后，我会先用实时网络检索调研这个主题，然后给你几个概念选项和成本估算。你挑一个喜欢的，我就逐阶段制作视频 —— 每一个创意决策点都会请你确认。最终视频会落在 `projects/<name>/renders/`。"

**不要**在这里讲完整架构、三层知识体系或管线内部机制。那是给好奇的人看的 —— 想深入就指向 `AGENT_GUIDE.md`。

### 第 6 步：应对追问

常见问题及回答方式：

**"要花多少钱？"**
- 零 key 路线：$0
- 配置了一个付费图像/视频 provider：视素材数量，通常每支视频 $0.30–$1.50
- 完整配置：多数视频 $1–$3
- 始终补一句："在花任何钱之前，我都会先给你准确的成本估算。"

**"你能做 [某种类型] 吗？"**
- 匹配到一条管线。若能对上，就说明是哪条管线、会用什么工具。
- 若哪条管线都对不上，就如实说 —— 建议最接近的那条，并解释会有什么不同。

**"要多久？"**
- 讲解视频（零 key）：5-15 分钟
- 讲解视频（有图像生成）：10-20 分钟
- 电影感（有视频生成）：20-40 分钟
- "大部分时间花在素材生成上。调研和写脚本阶段很快。"

**"我只想快速试一下"**
- 建议最短的零 key 提示词："试试：'Make a 30-second explainer about why leaves change color.' 它会用免费工具，大约 5 分钟就能完成。"

**"给我看看你能做什么"**
- 指向 README 里的演示视频，然后给出第 4 步的启动提示词。

## 反模式

- **不要把 `support_envelope()` 或 `provider_menu()` 的原始 JSON 倒给用户。** 把它翻译成平实语言。
- **不要罗列每一个工具。** 按能力分组（说"我可以用 FLUX 生成图像"，而不是"我有 flux_image、google_imagen、openai_image、recraft_image……"）。
- **不要主动讲架构**，除非被问到。"agent 优先、指令驱动"对开发者来说很有意思，但用户是来做视频的，不是来研究代码库的。
- **不要为缺失的能力道歉。** 框定为"你现在有这些"，可选地加一句"这里有个快速升级"。绝不要说"很遗憾你没有……"。
- **当用户显得犹豫或还在探索时，不要直接跳到生产。** 花 30 秒帮他们定位，能省下后面 10 分钟的困惑。
- **不要建议需要用户并不具备的工具的提示词。** 每条提示词都必须在他们当前配置下可实现。若某条需要特定的 key，要明确标出来。
