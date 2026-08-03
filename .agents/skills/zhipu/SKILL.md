---
name: zhipu
description: ZhipuAI (BigModel / 智谱开放平台) integration — image generation via GLM CogView-4 (cogview-4-250304), CogView-3-Flash, and glm-image. Use when generating images with GLM/CogView models, especially when the image must contain accurate Chinese text.
---

# ZhipuAI (BigModel / 智谱开放平台)

Requires `ZHIPU_API_KEY` in `.env`. Get one at https://bigmodel.cn/usercenter/proj-mgmt/apikeys.

## Current API

**OpenAI-compatible endpoint** — unlike DashScope, no native multimodal-generation path:

```text
POST https://open.bigmodel.cn/api/paas/v4/images/generations
Authorization: Bearer $ZHIPU_API_KEY
```

- Response: `data[0].url` — a **temporary URL valid ~30 days**. The tool downloads it to `output_path`; always pass an explicit output path so the image is stored locally.
- Also returns `content_filter` (role/level safety metadata) — passed through in `result.data`.

## Models

| Model | Quality | Notes |
|---|---|---|
| `cogview-4-250304` (default) | `hd` / `standard` | Recommended. Renders Chinese text in images accurately; ~¥0.06/image at standard |
| `cogview-4` | `hd` / `standard` | Alias of the CogView-4 series |
| `cogview-3-flash` | `standard` | Fast and cheaper |
| `glm-image` | `hd` only | Fixed size 1280x1280; ignores `size` |

## Request Body

```json
{
  "model": "cogview-4-250304",
  "prompt": "一只橘猫戴墨镜的海报，标题写『开源视频工具』",
  "quality": "standard",
  "size": "1024x1024",
  "watermark_enabled": true,
  "user_id": "optional-end-user-id"
}
```

**Size format uses lowercase `x`:** `"1024x1024"` — OpenAI-compatible. **Do NOT use the `*` separator DashScope uses** (`"1024*1024"` would be rejected).

Sizes (cogview-4 series): `1024x1024` (default), `768x1344`, `864x1152`, `1344x768`, `1152x864`, `1440x720`, `720x1440`.

## Chinese Text in Images (Core Strength)

CogView-4 is a Chinese-fluent text-to-image model — it renders **accurate Chinese text inside images** (signs, posters, titles, UI mockups). Prompting rules:

- Write the exact Chinese text you want in the image **verbatim** in the prompt, e.g. `海报标题写『开源视频工具』` or `招牌上写着：天空实验室`.
- Keep the desired text short (a title or a short phrase) — long paragraphs tend to degrade.
- Use `quality: "standard"` for drafts/iterations and `quality: "hd"` for final delivery (hd roughly doubles cost).

## OpenMontage Usage

### Via selector (recommended)

```python
from tools.graphics.image_selector import ImageSelector

result = ImageSelector().execute({
    "preferred_provider": "zhipu",
    "prompt": "科幻风格的棱镜分解白光成彩虹，深蓝夜空背景",
    "output_path": "projects/my-video/assets/images/prism.png",
})
```

### Direct

```python
from tools.graphics.zhipu_image import ZhipuImage

result = ZhipuImage().execute({
    "prompt": "一张科普海报，标题写『为什么天空是蓝色的』",
    "quality": "hd",
    "output_path": "projects/my-video/assets/images/poster.png",
})
```

## Parameters (`zhipu_image`)

- `prompt` (required): text prompt; Chinese understood natively
- `model`: default `cogview-4-250304`
- `quality`: `standard` (default) / `hd` — `glm-image` is hd-only
- `size`: default `"1024x1024"` — **`x` separator, not `*`**; ignored by `glm-image`
- `watermark_enabled`: default `true` — disabling requires signing a disclaimer with ZhipuAI
- `user_id`: optional end-user identifier for billing/audit
- `output_path`: where to save the downloaded image

## Troubleshooting

- **401 auth error:** Verify `ZHIPU_API_KEY` is set and the `Authorization: Bearer $KEY` header is present.
- **Size rejected:** Use `"WxH"` with lowercase `x`, not `*`. Check the enum list above.
- **Watermark can't be disabled:** `watermark_enabled: false` requires a signed disclaimer in your ZhipuAI account (安全管理 → 去水印管理).
- **glm-image ignores size:** glm-image is fixed at 1280x1280.
- **URL expired:** The returned URL is temporary (~30 days). Always pass `output_path` — the tool downloads immediately.
- **429 on cogview-4 series but cogview-3-flash works:** account-level rate limiting on the heavier model (observed 2026-08). Same key succeeds on `cogview-3-flash`; retry later or use the flash model for drafts.

## Safety

Never print or write the API key to logs, metadata, patches, or project artifacts. `.env.example` should contain only empty variable names. The tool's `_safe_error()` method redacts the key from error messages.
