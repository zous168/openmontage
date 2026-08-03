# Vendored Remotion core

本项目使用的 Remotion 核心包源码（**vendored，非 npm registry 安装**），用于：
版本钉死（4.0.484）、核心源码可修改、Backlot 交互式剪辑深度集成。

> 注意：vendor 覆盖的是 **Remotion 核心闭包**。`@remotion/google-fonts`（纯字体数据）
> 与全部第三方依赖（webpack、mediabunny、@rspack/core 等）仍从 npm registry 安装——
> **首次 `npm install` 仍需联网**；remotion 核心包本身不依赖 registry。

## 来源

| 项 | 值 |
|---|---|
| 上游仓库 | https://github.com/remotion-dev/remotion |
| tag | `v4.0.484` |
| commit | `97b7207325ffb7f338b2139301f46ad52de53eab` |
| 获取日期 | 2026-08-03 |
| 获取方式 | `git clone --depth 1 --branch v4.0.484 --filter=blob:none --sparse` + `sparse-checkout`（仅 17 个包目录 + LICENSE.md） |

## 结构

```
packages/
  core/                        # npm 包名 remotion（Composition、useVideoConfig 等）
  cli/                         # remotion-cli.js 桩 → dist/index.js
  renderer/                    # 子入口 client / pure / error-handling
  bundler/ player/ studio/ studio-server/ studio-shared/
  streaming/ licensing/ media-utils/ canvas-capture/
  web-renderer/ zod-types/ timeline-utils/ media-parser/
  compositor-win32-x64-msvc/   # 纯二进制（ffmpeg/ffprobe/dll），无构建
```

各包目录 = 上游源码（`src/` + `package.json` + `tsconfig.json`）+ 本地构建产物（`dist/`）。
构建/运行闭包之外的包（captions、google-fonts、media、transitions、shapes、paths）未 vendor。

## 构建

```bash
node scripts/build-vendor.mjs   # 仓库根 scripts/，读 vendor.config.json + 各包 package.json 推导入口
npm install                     # 根 workspaces 安装
```

- CJS：esbuild bundle → `dist/index.js`（或 `dist/cjs/index.js`，依各包 package.json 的 main/module）
- ESM：esbuild bundle → `dist/esm/index.mjs`（仅 package.json 有 module 字段的包）
- d.ts：tsc `-d`（仅 package.json 声明 types 的包）
- externals：从各包源码 import 推导（react/react-dom/@remotion 子包等）

产物 `dist/` **提交进 git**——clone 后 `npm install` 即可离线使用，无需重新构建。

## 本地补丁（与上游源码的差异）

| 位置 | 内容 | 原因 |
|---|---|---|
| `vendor-patch.d.ts`（模板，构建脚本复制进**全部 16 个可构建包**的 `src/`） | 声明 `Timer` 类型、`Headers.entries()`、`HTMLCanvasElement`/`OffscreenCanvas` 的 `getContext("2d")` 重载 | 官方用 tsgo（TS 7.0-dev lib）；plain tsc 5.9.3 缺这些类型符号 + 存在 canvas getContext 重载解析 bug。纯类型补丁，零运行时影响 |
| `packages/core/src/log-level-context.tsx` | `import React = require('react')` → `import * as React from 'react'`（含 VENDORED PATCH 注释） | esbuild 会把 import-equals 保留为运行时 `require("react")`，webpack 浏览器 bundle 报 "Dynamic require of react is not supported" |
| 全部包 `package.json` | `catalog:`/`workspace:` 协议 → 精确版本 `4.0.484`；devDependencies 清空 | pnpm catalog 协议 npm 不识别；devDeps 依赖 pnpm workspace 工具链，构建改用仓库根 devDeps |
| 全部包 `tsconfig.json` | 删除 `references` 字段 | 引用未 vendor 的 monorepo 包（media/webcodecs/example-videos 等）会 TS6053 |

`vendor.config.json` 的 `notes` 字段记录补丁原因。**升级上游前先删补丁试编译**，若 lib 已跟上则可删除。

## 升级流程

1. 重新 sparse clone 新 tag 到临时目录
2. 对比 17 个包的 `src/` 差异，替换
3. 删除 `vendor-patch.d.ts` 重试构建；若报错再评估补丁是否仍需要
4. `node scripts/build-vendor.mjs` 重建 dist，跑冒烟渲染回归

## 许可

LICENSE.md 见仓库根（Remotion 公司许可——本项目已按该许可使用 Remotion）。
