# OpenMontage 中的素材库取材用法

> 如何有效使用素材图像与素材视频工具 —— 检索词构造、
> provider 选择、授权意识，以及与素材管线的衔接。

## 可用的素材库工具

| 工具 | Provider | 内容 | 成本 | 速率限制 | 适用于 |
|------|----------|---------|------|-----------|----------|
| `pexels_image` | Pexels | 照片 | 免费 | 200/小时 | 高质量摄影，题材多样 |
| `pixabay_image` | Pixabay | 照片、插画、矢量图 | 免费 | 100/分钟 | 按分类筛选，库容量大（500 万+） |
| `pexels_video` | Pexels | 视频片段 | 免费 | 200/小时 | HD/4K 真实世界素材 |
| `pixabay_video` | Pixabay | 视频片段 | 免费 | 100/分钟 | 按分类筛选的视频、动画片段 |

## Provider 选择指南

### 何时用 Pexels
- 需要**高质量摄影**（有策展、专业）
- 需要**视频**（视频库比 Pixabay 更大）
- 想要**按画幅方向筛选**（横/竖/方）
- 想要**按颜色筛选**（匹配 playbook 配色）
- 需要**多语种**结果（28 个区域设置）

### 何时用 Pixabay
- 需要**按分类筛选**（自然、商业、科学等）
- 除照片外还想要**插画或矢量图**
- 想要**编辑精选**的策展结果
- 需要**更高的速率限制**（100/分钟 vs 200/小时）
- 需要**按视频类型筛选**（实拍 vs 动画）

### 决策流程
```
需要素材图像？
├── 需要特定分类（科学、商业等）？ → pixabay_image
├── 需要插画/矢量图？ → pixabay_image
├── 需要颜色匹配？ → pexels_image
└── 普通照片？ → pexels_image（策展质量更高）

需要素材视频？
├── 需要 4K？ → pexels_video（通过 size="large" 支持 4K）
├── 需要动画片段？ → pixabay_video（video_type="animation"）
├── 需要分类筛选？ → pixabay_video
└── 普通素材？ → pexels_video（HD 质量更好）
```

## 输入参数指南

### pexels_image / pexels_video
```python
{
    "query": "city skyline sunset",      # 必填：检索词
    "orientation": "landscape",           # 可选：landscape/portrait/square
    "size": "large",                      # 可选：large/medium/small
    "color": "FF6B35",                    # 可选：不带 # 的十六进制或颜色名
    "per_page": 5,                        # 每页结果数（1-80）
    "download_size": "large2x",           # 图像：original/large2x/large/medium
    "preferred_quality": "hd",            # 视频：hd/sd
    "output_path": "assets/images/s3.jpg" # 保存位置
}
```

### pixabay_image / pixabay_video
```python
{
    "query": "server room",              # 必填：检索词（最多 100 字符）
    "image_type": "photo",               # 图像：all/photo/illustration/vector
    "video_type": "film",                # 视频：all/film/animation
    "orientation": "horizontal",          # all/horizontal/vertical
    "category": "computer",              # 20 个分类之一
    "colors": "blue,gray",              # 逗号分隔的颜色名
    "editors_choice": true,              # 仅取精选高质量
    "safesearch": true,                  # 生产环境一律为 true
    "output_path": "assets/video/s5.mp4" # 保存位置
}
```

## 坑与最佳实践

### 1. Pixabay 的 URL 会过期
Pixabay 的下载 URL 内嵌了会过期的令牌。检索之后**务必立即下载**。工具已自动处理这一点，但绝不要缓存 Pixabay 的 URL 留待以后使用。

### 2. Pixabay 的分辨率上限
标准的 Pixabay API 用户最多拿到宽 1280px 的图像（`largeImageURL`）。完整分辨率需要经过审批的 API 权限。对多数视频制作的叠加用途，1280px 已经够用。

### 3. Pexels 的鉴权头
Pexels 在 `Authorization` 头中直接使用裸 API key（**不是** `Bearer`）。工具已处理这一点，但调试时要知道。

### 4. 检索结果随区域设置而变
Pexels 支持 28 个区域设置。若要检索具有文化特定性的内容，请设置 locale 参数。

### 5. 素材库检索是确定性的
与 AI 生成不同，检索两次 "ocean waves" 会得到相同结果。若第一次的结果不够好，就换关键词 —— 不要用同样的检索词重试。

### 6. 视频的时长筛选
两个素材视频工具都支持 `min_duration` 与 `max_duration` 参数。用它们来避免在只需要 4 秒时下载 30 秒的片段 —— 能省带宽和时间。

## 与素材管线的衔接

素材库工具的接入方式与生成类工具完全相同。在 asset manifest 中：

```json
{
    "id": "broll-s3",
    "type": "image",
    "subtype": "broll",
    "path": "assets/images/broll-s3.jpg",
    "source_tool": "pexels_image",
    "scene_id": "scene-3",
    "cost_usd": 0.00,
    "metadata": {
        "photographer": "Joey Farina",
        "source_url": "https://www.pexels.com/photo/2014422/",
        "license": "Pexels License (free, no attribution required)"
    }
}
```

Edit Director 与 Compose Director 对素材库资源与生成资源一视同仁 —— 它们只是从 manifest 中引用文件路径而已。

## 授权摘要

| Provider | 商用 | 署名 | 限制 |
|----------|---------------|-------------|-------------|
| Pexels | 是，免费 | 不强制（但欢迎） | 不得原样售卖；不得暗示背书 |
| Pixabay | 是，免费 | 不强制 | 不得原样售卖；不得创建竞争性素材库服务 |

两者对 OpenMontage 的所有使用场景都是安全的。没有授权费、没有按次版税、没有署名义务。
