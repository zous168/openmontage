# Ink Theater —— 手绘"会动的画"（创意技能）

> 风格 id：`ink-sketch` · 引擎：`ink-theater/ink-theater.js` · 运行时：HyperFrames（atelier）
> 技法致谢：受 Ian 的 `小黑/Xiaohei` MIT 技能启发。通用化、英文、以运动为先。

**它是什么：** 一个极简的**白底黑墨**世界，一个面无表情的吉祥物通过操作一台荒诞的**低科技装置**来*用身体演绎*一个抽象概念。它不是一份固定的场景目录 —— 而是一套通用方法 + 一个参数化引擎。它以 atelier 模式跑在 `animation` 管线上；它**不是**独立管线。

## 通用方法（概念 → 会动的场景）

从研究 + Xiaohei 构图规则中提炼出的"钥匙"是一个三步隐喻生成器 —— 这件事在 agent 里做，不要写进代码：

1. **抽象概念 → 一个物理动作** —— 卡住、漏出、复利累积、分拣、发酵、推动、下沉、散开。
2. **系统 → 一个低科技物件** —— 压榨机、漏斗、水井、罐子、传送带、梯子、桥、柜子、巨石、闸门、天平。
3. **吉祥物在那个物件上执行那个动作** —— 它摇曲柄 / 推 / 打气 / 盖章 / 捞出来。*如果把吉祥物删掉隐喻依然成立，那它就只是装饰 —— 重做。*

然后把它排布成一整页连续白纸上的若干节拍，配一台摄影机（横摇 / 推近）。

## 挖掘出的原型（选一个，再发明新的具体细节）

| 原型 | 吉祥物动作 | 运动配方 |
|---|---|---|
| **装置** | 操作一台机器（曲柄/杠杆/气泵） | 投料 → 摇曲柄 → 机器运转（蒸汽/仪表） → 产物弹出 |
| **前后负担转移** | 被混乱压垮 → 一个关键动作之后变轻松 | 左侧混乱 → 橙色扫过 → 右侧结构自行组装 |
| **旅程 / 陷阱** | 走在一条路上；掉进坑里或碰到节点 | 路径画出 → 行走 → 坑吞掉 / 节点弹出 → 蓝色的回归闭环 |
| **一变多的扇形** | 把一个源头拆分/切开 | 源头分裂 → 箭头画向 N 个分支 → 每个分支各自动作 |
| **推动 / 惯性** | 把巨石推上坡，它随后滚走 | 缓慢吃力地上坡（power1） → 越过顶点 → 快速滚落（power2.in） |
| **水井 / 打捞** | 把水桶放进噪声里，舀出那颗宝石 | 水桶下降 → 舀取 → 把唯一有价值的那点提上来 |

## 色彩语法（严格）

- **黑** = 结构与吉祥物 · **橙** = **仅**用于流动/箭头 · **红** = 问题/警示 · **蓝** = 理想的终态。
- 纯白纸面，留白 ≥35%，主体占 40–60% 左右。吉祥物面无表情（白点眼睛），绝不卖萌。

## 引擎速查（`InkTheater`）

- 线条：`inkPath(pts)`、`inkRibbon(pts,{width,taper})`（毛笔）。沸腾抖动：`boil(turbEl, tl, {duration})`。
- 运动：`ease.{settle,overshoot,bouncy,soft}`（可安全 seek 的弹簧）—— 弹出用 overshoot，落位用 settle，着地用 bounce。
- 角色：`mascot({x,y,scale})` → `.reachL/.reachR([x,y])`（FABRIK）。通过 GSAP 的 `onUpdate` 跟随移动目标。
- 机械：`parts.{crank,gauge,hopper,slot,lever,box}` —— 自行组合。
- 完整 API + 确定性规则：`ink-theater/README.md`。

## 角色 —— Ink Puppet + 真实动捕（绝不手工调运动）

对于会走路/跳舞等的角色，**不要**手工编写运动（正弦曲线、手摆的关键帧）。使用木偶系统 + **动捕动作库**：

- `InkPuppet.create(mount,{cx,ground,boil})` → `p.drawIn(tl,{start})`（自绘显现）→ `InkPuppet.choreograph(tl, p, [{clip:'walk'},{clip:'dance_spin'},{clip:'wave'}], {start})`。
- **读 `ink-theater/mocap/catalog.json`，为每个节拍挑选合适的动作 —— 要有变化，并且绝不要循环同一个片段**（循环正是让视频显得重复的原因）。目前有 12 个（全部来自 CMU）：walk、run、climb、march、shuffle、jump、kick、sit、wave、twist、dance_spin、dance_glide。
- **目录里没有的动作？** `node ink-theater/mocap/add-motion.mjs <name> <cmu-id|url|path> <category> "<desc>"` —— 它会抓取、转换（自动映射 fair1 / CMU / Mixamo 骨架）、重新打包并更新目录。免费的 CMU 动捕库（`una-dinosauria/cmu-mocap`）有数千条。然后把 `mocap/clips.js` 复制进项目。
- **对话气泡**（角色"说话"）：`InkTheater.balloon(tl, {into, overlay, at, dur, text, mouth:[x,y], center:[x,y], boil})` —— 用 HTML 文本，这样网页字体才会生效。

## ⚠ 不可妥协的几条

- **手写体字体：要嵌入完整字体，而不是 Google Fonts 的 woff2 子集**（`css2` API 的子集缺失 basic-latin → 到处静默回退成衬线体）。在承载字幕/对话气泡的 **HTML 叠加 `<div>`** 上使用随包提供的 `ink-theater/assets/patrickhand.ttf`（`@font-face … format("truetype")`）。不要热链 Google（会破坏确定性）。见 `ink-theater/README.md` → "font gotcha"。
- 确定性：闭式解弹簧、按 seed 步进且脱离时间线的 boil、不用 `repeat:-1`、只用带种子的 PRNG。
- `window.__timelines` 上只挂一条暂停的 `gsap.timeline`。渲染前用 `lint` + `snapshot` 校验（并读一读那张接触印样表）。
- **豁免管线约束**：这是跑在 `animation` / `character-animation` 管线上的 风格 + 引擎 —— **不是** Rule Zero 意义上的管线。不要去找 `.yaml` manifest 而卡住。

## 参考实现

- `projects/ink-theater-reel/` —— 能力展示片。 · `projects/ink-theater-momentum/` —— "Momentum" 故事片（手写体通过 HTML div 实现）。
