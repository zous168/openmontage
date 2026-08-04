# OpenMontage 中的人脸修复用法

> 资料来源：CodeFormer 论文（Zhou et al. 2022）、GFPGAN 文档、Real-ESRGAN 上采样文档、
> 位于 `skills/creative/enhancement-strategy.md` 的现有 Layer 2 技能

## 速查卡

```
默认模型：       CodeFormer，fidelity 0.5
备选：           GFPGAN（更快，可控性更差）
fidelity 范围：  0 = 最大程度的质量增强，1 = 最大程度忠于输入
背景上采样：     启用后同时放大背景（Real-ESRGAN）
处理顺序：       face_restore 在 face_enhance 之前 —— 先修复，后打磨
```

## 关键区分 —— face_restore vs face_enhance

| 工具 | 作用 | 何时使用 |
|------|-------------|-------------|
| `face_enhance` | FFmpeg 滤镜链 —— 皮肤柔化、色彩平衡、锐化 | 质量尚可、只需打磨的素材 |
| `face_restore` | AI 模型重建 —— 重建已劣化的面部细节 | 质量很差的素材：模糊、压缩失真、低分辨率人脸 |

**决策规则：** 若人脸可辨认、只是需要打磨，用 `face_enhance`。若人脸已劣化、模糊，或压缩到难以辨认，用 `face_restore`。

## 模型选择

| 模型 | 优势 | fidelity 控制 | 速度 |
|-------|----------|------------------|-------|
| CodeFormer | 质量更好、保持身份特征、可控 | 有（0-1 滑杆） | 较慢 |
| GFPGAN | 基线不错、更简单 | 无 | 较快 |

### fidelity 调节（仅 CodeFormer）

| fidelity | 效果 | 使用场景 |
|----------|--------|----------|
| 0.0 | 最大程度增强 —— 视觉质量最佳，但可能改变身份特征 | 已无法辨认的人脸、艺术用途 |
| 0.3 | 强力修复 —— 适合严重劣化的人脸 | 老素材、严重压缩失真 |
| 0.5 | 平衡（默认）—— 修复与身份保持兼顾 | 通用修复 |
| 0.7 | 保守 —— 轻度清理，强力保持身份特征 | 摄像头素材、轻度劣化 |
| 1.0 | 几乎不变 —— 基本等同于直通 | 测试、对照基准 |

## 常见工作流

### 1. 老素材修复

```
face_restore（fidelity 0.3）→ color_grade → compose
```

对人脸严重劣化的档案/复古素材做重度修复。

### 2. 摄像头素材清理

```
face_restore（fidelity 0.7）→ face_enhance（talking_head_standard）→ compose
```

轻度修复后再打磨 —— 最适合现代但画质不佳的摄像头素材。

### 3. 低分辨率人脸 + 背景放大

```
face_restore（bg_upsampler=true）→ compose
```

当人脸和背景都需要改善时的一步式修复。

### 4. 档案照片用于口播人像

```
face_restore → talking_head 工具（SadTalker）
```

在把源人脸图像喂进口播人像动画管线之前先做修复。

## 质量检查清单

在接受 face_restore 的输出之前，逐项确认：

- [ ] 修复后的人脸比输入更锐利、更干净
- [ ] 身份特征得以保留 —— 仍能认出是同一个人
- [ ] 没有幻觉出来的特征（多余的眼睛、错误的皮肤纹理、牙齿伪影）
- [ ] 皮肤纹理自然，不像塑料/过度磨皮
- [ ] 逐帧一致（用于视频时）—— 不会在修复/未修复的画质之间闪烁

## 应用到 OpenMontage

使用 `face_restore` 工具时：

1. 在处理链中**把 face_restore 放在 face_enhance 之前** —— 先修复，后打磨
2. **从 fidelity 0.5 开始**，再根据目视检查调整
3. **口播人像管线遇到劣质源素材时**，在 assets 阶段应用 face_restore
4. **只在人脸和背景都需要改善时才启用 `bg_upsampler`**
5. **绝不要对本来就不错的素材使用 face_restore** —— 它可能引入细微伪影
6. **把输入与输出并排比较** —— 人脸应当能被认出是同一个人
7. **处理整段视频之前，先抽取关键帧测试 face_restore 参数**
