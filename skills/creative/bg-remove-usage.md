# OpenMontage 中的背景移除用法

> 资料来源：rembg 库文档、U2Net 论文（Qin et al. 2020）、IS-Net 论文
> （Qin et al. 2022）、OpenMontage `tools/bg_remove.py` 的实现

## 速查卡

```
默认模型：       u2net（通用，速度快）
用于人物：       u2net_human_seg（针对人体轮廓优化）
精细边缘：       启用 alpha_matting（头发、毛发、树叶）
输出：           默认为透明 PNG；设置 bg_color 可换成纯色背景
运行时间：       每张图约 1-3 秒（CPU），<0.5 秒（GPU 配 onnxruntime-gpu）
安装：           pip install rembg（CPU） | pip install rembg[gpu]（CUDA）
```

## 何时使用 bg_remove

背景移除属于**素材准备**步骤。在 compose 阶段之前使用它。

- **产品演示 / 电商视频** —— 把产品从干净背景中抠出来
- **合成** —— 把讲述者叠在生成的背景或图表之上
- **封面图制作** —— 为 YouTube 封面做干净的抠图
- **绿幕替换** —— 不需要真绿幕也能达到绿幕效果
- **B-roll 准备** —— 清理原始照片以便作叠加使用

## 模型选择指南

| 模型 | 适用于 | 速度 | 备注 |
|-------|----------|-------|-------|
| `u2net` | 通用物体、产品、场景 | 快 | 默认；全能型 |
| `u2net_human_seg` | 人物、肖像、讲述者 | 快 | 对人体轮廓的遮罩更准确 |
| `isnet-general-use` | 复杂边缘、头发、毛发 | 较慢 | 在精细边界上细节更好 |

**决策规则：** 若主体是人，用 `u2net_human_seg`。若主体有复杂边缘（头发、毛发、枝叶）且你需要最高质量，用 `isnet-general-use`。其他情况用默认的 `u2net`。

## Alpha 抠图（Alpha Matting）

Alpha 抠图通过在边界处计算柔和的透明度来细化边缘遮罩。它能产生更自然的边缘，但处理时间大约翻倍。

| 主体类型 | Alpha 抠图 | 理由 |
|-------------|---------------|--------|
| 头发、毛发、羽毛 | 启用 | 精细的半透明发丝需要柔和边缘 |
| 树叶、树木、草地 | 启用 | 不规则的有机边界能从抠图中受益 |
| 产品、设备 | 关闭 | 边缘是干净的几何形状；抠图没有价值 |
| 文字、Logo、形状 | 关闭 | 这类主体本就应该是硬边缘 |

## 常见工作流

### 1. 讲述者抠图用于合成

把讲述者从背景中抠出来，叠到图表或幻灯片之上。

```
bg_remove(input_path="speaker.png", model="u2net_human_seg")
  --> speaker_nobg.png（透明）
  --> 在 compose 阶段叠加到图表/幻灯片上
```

### 2. 产品单独抠出

抠出产品，并可选地放到品牌色背景上。

```
bg_remove(input_path="product.jpg", model="u2net")
  --> product_nobg.png（透明）

# 或者带品牌背景：
bg_remove(input_path="product.jpg", model="u2net", bg_color="#FFFFFF")
  --> product_nobg.png（白色背景）
```

### 3. 封面图准备

移除背景，放大，然后与文字叠加层合成。

```
bg_remove(input_path="subject.png", model="u2net_human_seg", alpha_matting=True)
  --> subject_nobg.png
  --> 放大 --> 在 compose 阶段与文字叠加层合成
```

### 4. 批量帧处理

为一段合成序列准备多帧时，在进入 compose 阶段之前把所有源帧处理完。

```
对每一个源帧：
    bg_remove(input_path=frame, model="u2net_human_seg")
    --> frame_nobg.png
然后：把所有透明帧合成到背景序列之上
```

## 质量检查清单

进入 compose 阶段之前，逐一核对每个 bg_remove 输出：

- [ ] **边缘质量干净** —— 主体周围没有光晕伪影
- [ ] **精细细节得以保留** —— 头发、手指和细小特征完好
- [ ] **透明度彻底** —— 透明区域内没有残留的背景渗色
- [ ] **主体完整** —— 主体没有任何部分被错误移除
- [ ] **合成测试** —— 叠到目标背景上时，主体融合自然

## 应用到 OpenMontage

在素材准备阶段使用 `bg_remove` 工具时：

1. **任何含人物的画面都用 `u2net_human_seg`** —— 它在人体轮廓周围产生的遮罩比通用模型更贴合
2. **只对边缘复杂的主体启用 `alpha_matting`**，比如头发、毛发或枝叶 —— 边缘干净的主体跳过它以节省处理时间
3. **合成类工作流请输出透明 PNG**（省略 `bg_color`），到 compose 阶段再叠加 —— 这样保留最大灵活性
4. **需要换成纯色背景时，把 `bg_color` 设为** playbook 背景色 token 的值 —— 保持输出与项目风格一致
5. **在 compose 阶段之前处理源帧** —— bg_remove 是素材准备步骤，不是合成期的操作
6. **合成前先在完整分辨率下检查输出边缘** —— 光晕伪影和边缘渗色在成片视频里看得出来，必须尽早发现
