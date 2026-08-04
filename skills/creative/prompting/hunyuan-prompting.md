# HunyuanVideo 1.5 —— 提示词指南

> 来源：[腾讯提示词手册](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/assets/HunyuanVideo_1_5_Prompt_Handbook_EN.md)
> 通用词汇表见：`skills/creative/video-gen-prompting.md`

**字数：** Hunyuan 1.5 在 80–200 词时表现良好；写 400 词的长文并不会带来回报。

## HunyuanVideo 提示词公式

### 文生视频
```
Subject + Motion + Scene + [Shot Type] + [Camera Movement] + [Lighting] + [Style] + [Atmosphere]
```

### 图生视频
```
Subject Motion Dynamics + Scene Motion Dynamics + [Camera Movement]
```

做 I2V 时，重点描述**运动**，不是外观（外观由图像提供）。

## HunyuanVideo 的专属长处

### 用光照塑造氛围
腾讯强调：**"光是氛围的灵魂。"**

从多个维度描述光照：
- **风格**：soft、hard、neon、ambient
- **方向**：side-lit、backlit、overhead、underlighting
- **质感**：harsh spotlight、diffuse glow
- **阴影**：long dramatic shadows、soft shadow edges
- **色温**：golden hour warmth、cool daylight blue
- **反射**：wet surface reflections、metallic glints

### 镜头运动库

| 运动 | 类型 | HunyuanVideo 提示词 |
|----------|------|-------------------|
| 升降 / 垂直移机 | 平移（垂直） | "camera rises vertically" |
| 横移 / 跟踪 | 平移（水平） | "camera tracks left alongside subject" |
| 推近 | 平移（推） | "camera pushes forward toward subject" |
| 拉远 | 平移（拉） | "camera pulls back from subject" |
| 横摇 | 旋转（偏航） | "camera pans right across the scene" |
| 纵摇 | 旋转（俯仰） | "camera tilts upward to follow the rocket" |
| 滚转 | 旋转（Z 轴 / 荷兰角） | "camera rolls clockwise into a Dutch tilt" |
| 环绕 | 圆周 | "camera orbits around subject" |
| 跟随 | 锁定 | "camera follows subject from behind" |
| 变焦 | 纯镜头（焦距） | "camera slowly zooms in on the figure" |
| Rack focus | 纯镜头（焦平面，快速切换） | "rack focus from the foreground bottle to the figure in the background" |
| Pull focus | 纯镜头（焦平面，渐进） | "camera shifts focus from foreground X to background Y" |
| 静止 | 固定 | "static camera, no movement" |

### 动态景深镜头要同时标注起点和终点的焦平面

对于对焦会变化的镜头，把两个端点都写出来对 Hunyuan 有帮助。写清焦点从哪里开始**以及**落到哪里 —— 不要让其中一端只靠隐含。

示例："shallow DoF; focus on the foreground bottle at start; focus pulls to the figure in the background by end."

缺了任一端点，Hunyuan 往往会退回深焦，或者停在错误的焦平面上。

### 风格关键词

**写实 / 电影感**：
- Film noir、hard sci-fi、cinematic photography
- Period drama、war documentary、nature documentary

**动画 / 插画**：
- 2D animation、Japanese anime
- Watercolor painting、Chinese ink wash
- Low-poly 3D、pixel art

## I2V 最佳实践

使用图生视频时，输入图像已经定义了外观。你的提示词应当**只**描述：
1. 主体如何运动
2. 环境如何变化
3. 镜头运动

**好的 I2V 提示词**："The woman's hair blows in the wind as she turns to face the camera. Leaves scatter across the path. Camera slowly dollies in."

**差的 I2V 提示词**："A beautiful woman in a red dress standing in a forest" —— 这只是在重复图像里已经有的东西。

### 按时间顺序排列运动

按时间顺序描述运动；若发生多个动作，就把它们分开写（"first the camera pans right, then tilts upward"）。Hunyuan 会按提示词中出现的顺序执行运动 —— 把两个动作塞进同一个从句，会导致其中一个被丢掉或被混合。

## 示例（T2V）

```
A young woman in a flowing white dress walks barefoot along
a deserted beach at golden hour. She trails her hand through
the shallow surf, leaving ripples. Her hair catches the warm
side-light from the setting sun. Medium tracking shot, camera
follows alongside at knee height. Soft golden lighting with
long shadows stretching toward the camera. Cinematic
photography style, shallow depth of field. Peaceful,
contemplative atmosphere.
```

## 示例（I2V）

```
The cat stretches lazily, then leaps from the windowsill
to the floor. Dust motes scatter in the shaft of light.
Camera remains static, slight rack focus from window to
landing spot.
```
