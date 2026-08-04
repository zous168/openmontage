# Animated Drawing —— 用真实动捕让一张给定的画/照片动起来

> 命令：`/animated-drawing` · **路径 A（栅格）。** 姊妹命令：`/ink-art`（矢量，从零创作）。
> 工具：Meta 开源的 **AnimatedDrawings**（github.com/facebookresearch/AnimatedDrawings —— 代码 MIT 许可，仓库已于 2025 年归档）。

**何时使用：** 用户*已经有*一张**人形**角色的画或照片，并希望**那张图**动起来（跳舞 / 走路 / 跳跃 / 挥手）。输出是把原图**形变**去贴合动作后的栅格 **GIF（透明）或 MP4**。若要**从零创作**一个会自己画出来并动起来的矢量涂鸦 → 改用 **`/ink-art`**。

**它做什么：** 自动为图像绑定骨骼（预测一副 16 关节骨架），然后通过对平面纹理做 As-Rigid-As-Possible 网格形变，把一段 BVH 动捕数据重定向到它身上。它只是*让一张已经画好的图动起来* —— **没有边画边显现的自绘揭示效果**（那是 `/ink-art` 的事）。

## 选择角色来源 —— 先问用户（绝不静默复用内置角色）

该工具会给*你喂给它的任何图像*做动画，而它需要一个**画出来的人形**（有头、两条胳膊、两条腿，四肢彼此分开，背景是浅色纯色）。在开工之前，**把下面这些选项呈现给用户**并选定其一（用户手上什么都没有时默认走*生成*这条路）—— 这也正是避免每支视频看起来都是同一个吉祥物的关键：

1. **用户上传一张画** —— 他们自己画的人形涂鸦。效果最好；那是他们的角色。
2. **用户上传一张照片 / 任意图像** —— 先把它**涂鸦化**（`image_selector` 走 img2img，FLUX/Recraft："turn this into a simple child's crayon doodle of a humanoid, full body, plain white bg"）→ 然后再绑定骨骼。（"手绘感"就来自这一步；原始照片形变后会很难看。）
3. **生成一个全新角色** ⭐（推荐的默认项）—— `image_selector`（FLUX/Imagen）：*"a child's crayon drawing of a character, full body, front-facing, A-pose with arms and legs separated, plain white background, no shadow, no text."* 每支视频都独一无二。
4. **取一个素材库角色** —— `pixabay_image` / `pexels_image`，筛选出*纯色背景上画出来的人形*。碰运气（素材库里多数是照片）—— 优先选 #3。

内置的示例角色**仅供演示** —— 不要把它们当作用户的角色交付。选项 1–4 都需要下面提到的**自动绑骨 Docker 服务**；如果它没起来，就如实说明。

## 两种运行模式

**A · 内置角色 + 预设动作 —— 开箱即用，不需要 Docker（已在 Windows 上验证）：**
```bash
git clone --depth 1 https://github.com/facebookresearch/AnimatedDrawings.git && cd AnimatedDrawings
# 该仓库锁定 Python 3.8 + 旧版 wheel；用 uv 来装 3.8：
uv python install 3.8 && uv venv --python 3.8 .venv
uv pip install --python .venv -e .
uv pip install --python .venv "setuptools<81"      # 仓库里 import 了 pkg_resources 却没声明依赖
.venv/Scripts/python -c "from animated_drawings import render; render.start('./examples/config/mvc/export_gif_example.yaml')"
```
CPU 上每段约 10–12 秒，无需 GPU/Docker/模型下载。

**B · 为一张全新的画自动绑骨 —— 重量级（Docker + 约 670 MB 模型、约 16 GB 内存）：**
```bash
python image_to_animation.py drawing.png out_dir    # 检测 → 分割 → 绑骨 → 重定向 → 渲染
```
需要仓库自带的 TorchServe 容器（`docker/`），它会下载 `drawn_humanoid_detector.mar`（311 MB）+ `drawn_humanoid_pose_estimator.mar`（357 MB）。Windows 上：绑骨这一整套只能通过该容器运行（OpenMMLab 实际上只支持 Linux）。

## 输入要求（自动绑骨）
一个画得清晰的**人形**，大致呈 T 形或 A 形姿势（四肢分开、不重叠），置于**浅色纯色背景**上（分割算法是阈值 + 洪水填充），且画面中有且仅有一个人物。

## agent 需要生成的配置（全部是 YAML）
`char_cfg.yaml`（外加 `texture.png`、`mask.png`；由 `image_to_annotations.py` 自动产出）· 一份**动作**配置（bvh + 帧数 + 地平面）· 一份**重定向**配置（BVH 关节 → 骨骼关节；除非骨架不同，否则直接复用内置的 `fair1_ppf` / `cmu1_pfp`）· 一份 **MVC** 配置（`controller.MODE: video_render`、`OUTPUT_VIDEO_PATH`，可选 `WINDOW_DIMENSIONS` / `CLEAR_COLOR` / `BACKGROUND_IMAGE` / `CAMERA_POS`）。

## 预设动作 → 重定向配置（必须与 BVH 骨架匹配）
每个内置 BVH 属于不同的骨架族；用错重定向配置会**直接崩溃**（`ValueError: 'RightArm' is not in list`）。要成对使用：

| 动作 | BVH 目录 | 重定向配置 |
|---|---|---|
| `dab`、`wave_hello`、`jumping`、`zombie` | `bvh/fair1/` | `fair1_ppf` |
| `jumping_jacks` | `bvh/cmu1/` | `cmu1_pfp` |
| `jesse_dance` | `bvh/rokoko/` | `mixamo_fff` |

其他任何 BVH → 需匹配它自己的骨架（或另写一份重定向配置）。用 `end_frame_idx` **给长片段设上限**（`wave_hello` 有 839 帧），否则渲染要跑好几分钟；带地面接触的片段（`dab`、`wave_hello`）渲染速度慢约 8 倍。

## 角色多样性 —— 动画化**用户的**画（解决"总是同一个角色"）
内置角色**仅供演示**。真实使用中，角色就是用户**提供**的那一个 —— 每支视频都不同。若收到"随便给我做个视频"这类没有附图的请求，就**生成一个全新角色**（图像生成："a child's crayon drawing of a …" → 浅色纯背景上的 PNG）并**为它自动绑骨**（走 Docker 路径）→ 每次都是不一样的角色。**绝不要跨视频复用内置角色**，否则每次输出看起来都是同一个吉祥物。

## 合成进 HyperFrames（下半场 —— 做出真正的视频必需）
AnimatedDrawings 只输出会动的角色。要做成一支*视频*（背景、对话气泡、音乐），需要在 HyperFrames 里合成：
- **透明输出：** 在 MVC 配置里设 `view.CLEAR_COLOR: [0,0,0,0]` → 得到透明帧。
- **GIF 在 HyperFrames 的确定性渲染中会卡住不动。** 转成**带 alpha 的 VP9 WebM**：`ffmpeg -i char.gif -c:v libvpx-vp9 -pix_fmt yuva420p char.webm`。（`ffprobe` 会误报为 `yuv420p` —— alpha 通道其实完好。）
- **视频契约（linter 会强制检查 —— 运行 `npm run check`）：** `<video>` 必须是**舞台的直接子元素并带自己的 `id`**，**不能**嵌套在带时序的 `<div>` 里（嵌套会导致**卡住**）；每个片段需要自己的 `data-track-index`；淡出需要在结尾补一条硬性归零 `tl.set(el,{opacity:0})`。
- 文字/**对话气泡** = HTML 叠加 div，使用完整的 `ink-theater/assets/patrickhand.ttf`（参见 ink-theater 的字体坑）。
- **豁免管线约束：** `/animated-drawing` 与 `/ink-art` 是创意入口，不是受 Rule Zero 约束的管线 —— 没有 `.yaml` manifest。

## 输出与如实的局限
GIF（透明）/ MP4（H.264，`avc1`），分辨率由 `WINDOW_DIMENSIONS` 决定（示例为 500×500）。**仅栅格**（形变的是画面像素 —— 放大会看到拉伸的纹理）、**仅支持人形**、**没有边画边显现的效果**、**背景很粗糙**。它是一个让人会心一笑的"你的涂鸦活过来了"的小惊喜；自动绑骨路径背后压着一个 Docker 服务。它不是通用矢量引擎 —— 想要会自己画出来的白底墨线矢量涂鸦，请用 `/ink-art`。

本次评估会话的样例渲染结果：`.tmp/animated-drawings/out/`（`char3_dab.gif`、`char1_zombie.mp4`）。
