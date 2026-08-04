# LTX-2 —— 提示词指南

> 来源：[LTX 官方提示词指南](https://docs.ltx.video/api-documentation/prompting-guide)
> 通用词汇表见：`skills/creative/video-gen-prompting.md`

## LTX 专属的 6 要素结构

LTX-2 使用一套清爽、聚焦的提示词结构：

1. **确立镜头** —— 与你的类型相匹配的摄影术语
2. **搭建场景** —— 光照、配色、质感、氛围
3. **描述动作** —— 从头到尾自然流动的动作序列
4. **定义角色** —— 用外形线索（年龄、发型、衣着），不要用抽象标签
5. **镜头运动** —— 说明怎么动、何时动；描述运动**之后**出现了什么。（LTX 严格区分平移/旋转/纯镜头：`dolly` ≠ `zoom`，`pan` ≠ `truck`。选对家族 —— 平移是移动机位，旋转是原地转动，纯镜头只改焦距或焦平面而相机不动。）
6. **描述音频** —— 环境声、音乐、说话或歌唱

### 严格静止镜头规则

如果你写了 "static camera"，那这个镜头就必须**没有**运动、**没有**对焦变化、**没有**变焦。LTX 会照字面理解 "static" —— 在提示词后面再加任何运动动词，要么被忽略，要么产生相机自相矛盾的画面故障。二选一：要么静止，要么单独一个具名的运动。

## LTX 专属技巧

### 描述运动之后的结果
当你描述结果时，LTX 渲染镜头运动会更准确：
- 不要写："Camera pans left"
- 要写："Camera pans left to reveal a bustling market square"

### 音频提示词（LTX-2 独有）
LTX-2 会生成同步音频。使用具体的描述词：

| 类别 | 示例 |
|----------|---------|
| **环境声** | "coffeeshop noise"、"wind and rain"、"forest with birdsong" |
| **人声风格** | "energetic announcer"、"resonant voice with gravitas"、"childlike curiosity" |
| **音量** | "whisper"、"mutter"、"shout"、"scream" |
| **音乐** | "soft acoustic guitar"、"electronic beat building" |

对白放进引号：`The narrator says: "Welcome to the future."`
指定语言/口音：`speaks in British English with a warm tone`

### 风格分类
LTX 把风格归为三个家族：

**动画类**：stop-motion、2D animation、3D animation、claymation、hand-drawn
**风格化**：comic book、cyberpunk、8-bit pixel、surreal、minimalist、painterly
**电影感**：period drama、film noir、fantasy、thriller、documentary、arthouse

## 该避免什么（LTX 专属）

| 避免 | 原因 |
|-------|--------|
| 内心情绪状态（"sad"、"confused"） | 改用视觉线索：眼泪、垮下的肩膀、皱起的眉头 |
| 可读文字与 Logo | 渲染不可靠 |
| 复杂物理（爆炸、飞溅） | 会产生伪影；简单运动没问题 |
| 塞太满的场景 | 太多角色/动作会降低连贯性 |
| 相互冲突的光照描述 | 挑一套方案并坚持到底 |
| 一上来就写复杂 | 逐步搭建：先写简单提示词，再叠加层次 |
| 超过约 80 词的提示词 | LTX-2 超过后会退化。挑出最重要的 5–6 个要素。 |

## LTX 技术备注

- **时长**：每次生成约 5-8 秒
- **音频**：自动生成；写清你想听到什么
- **约 30% 的输出带有伪影** —— 换个 seed 重跑
- **无法渲染可读文字** —— 不要写招牌或标题
- **帧数必须满足** `(n-1) % 8 == 0`：合法帧数为 25、49、73、97、121、161、193

## 示例

```
A wide establishing shot captures a misty morning harbor.
Weathered fishing boats bob gently, their paint peeling in
patches of red and blue. A grey-haired fisherman in a dark
wool peacoat steps onto the dock, carrying a heavy net over
one shoulder. He pauses, looks out at the fog bank, then
walks toward the nearest boat with steady, deliberate steps.
The camera tracks alongside him at waist height, slowly
pushing in as he reaches the boat and tosses the net aboard.
Soft overcast light with a warm break in the clouds near
the horizon. Ambient sound of water lapping, rope creaking,
and distant foghorn.
```
