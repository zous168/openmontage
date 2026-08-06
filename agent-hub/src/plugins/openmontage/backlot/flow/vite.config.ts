import {defineConfig} from "vite";
import {resolve} from "node:path";

// 产物输出到 backlot/ui/flow-dist/ — 由 Backlot 的 StaticFiles mount(/ui)直接服务。
// 稳定文件名(flow.js/flow.css)是为了配合 server.py 的 _ui_html mtime 版本化注入。
export default defineConfig({
  base: "./",
  build: {
    outDir: resolve(__dirname, "../ui/flow-dist"),
    emptyOutDir: true,
    target: "es2022",
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(__dirname, "index.html"),
      output: {
        entryFileNames: "flow.js",
        // 合并后的 CSS 源名是 style.css → 重命名为 flow.css 以匹配 flow.html 的引用
        assetFileNames: (info) =>
          info.names?.some((n) => n.includes("style.css")) ? "flow.css" : "[name][extname]",
      },
    },
  },
});
