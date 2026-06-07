# QuaverQ 官网（静态站）

`docs-site/` 是 QuaverQ 的纯静态介绍页，部署到 [Cloudflare Pages](https://pages.cloudflare.com/)。

**主仓库闭源**：本站不暴露源码 / Issue / Release 等任何 GitHub 公开入口；下载产物全部托管在 **Cloudflare R2（自定义域名）**。

## 目录结构

```
docs-site/
├── index.html              # 单页落地页（Hero / 功能 / 下载 / FAQ / 联系 / Footer）
├── version.json            # 当前发行版元数据（版本号 / 文件名 / R2 直链 / 文件大小 / 发布时间）
├── assets/
│   ├── css/style.css       # 全部样式（CSS 变量 + 明暗双主题，prefers-color-scheme）
│   ├── js/version.js       # 运行时拉取同站 /version.json 更新版本徽标 + 下载按钮 href
│   └── img/logo.svg        # Logo（同步自 assets/io.github.jinzhongjia.quaverq.svg）
├── _headers                # Cloudflare 安全响应头 + 缓存策略
├── _redirects              # /download → R2 上的 latest AppImage（302）
└── README.md               # 本文件
```

## 设计要点

- 纯 HTML + CSS + 一段 JS，**零构建依赖**，本地双击 `index.html` 即可预览
- 颜色 / 排版对齐 `qq-music-design` skill（品牌绿 `#31C27C`，PingFang/Microsoft YaHei 字体栈）
- 明暗双主题通过 `prefers-color-scheme` 自动跟随系统
- 响应式：3 列 → 2 列 → 1 列断点切换
- 不出现 GitHub / Issue / 源码 / Release 等公开仓库相关链接

## R2 自定义域名

发行产物托管在 **`cdn.quaverq.nvimer.org`**（Cloudflare R2 自定义域名）。

约定的对象路径：

| 路径 | 用途 |
|---|---|
| `cdn.quaverq.nvimer.org/v<version>/QuaverQ-x86_64.AppImage` | 精确版本归档（不可变） |
| `cdn.quaverq.nvimer.org/latest/QuaverQ-x86_64.AppImage`     | 「最新版」别名，发版时覆盖 |

- `version.json` 的 `url` 字段填精确版本路径，便于客户端追溯
- `_redirects` 的 `/download` 短链指向 `latest/` 别名，方便外部直接分享

## 版本号自动化

页面加载时 `assets/js/version.js` 会 `fetch('/version.json')`，把字段写入页面：

| `version.json` 字段 | 写入位置 |
|---|---|
| `version` | Hero 顶部「最新版本 vX.Y.Z」徽标 + 下载卡片右上角小角标 |
| `url`     | 主下载按钮 `href`（两个 CTA 都会改） |
| `size`    | 下载卡片副标题「AppImage · x86_64 · 38.5 MB」中的体积 |
| `released_at` | 下载卡片副标题中的发布日期 |

**接口失败兜底**（断网、JSON 损坏、文件 404）：版本徽标显示「最新版本」，下载按钮回退到 `/download` 短链（由 `_redirects` 跳转到 R2 上的 latest 路径）。

## 发版流程（手动）

假设要发 `v0.2.0`，桶名为 `quaverq`：

1. 本地或 CI 构建出 AppImage：`uv run python build.py --appimage`
2. 上传到 R2（一份归档、一份覆盖 latest）：
   ```bash
   wrangler r2 object put quaverq/v0.2.0/QuaverQ-x86_64.AppImage --file dist/QuaverQ-x86_64.AppImage
   wrangler r2 object put quaverq/latest/QuaverQ-x86_64.AppImage --file dist/QuaverQ-x86_64.AppImage
   ```
3. 更新 `docs-site/version.json`：
   ```json
   {
     "version": "v0.2.0",
     "filename": "QuaverQ-x86_64.AppImage",
     "url": "https://cdn.quaverq.nvimer.org/v0.2.0/QuaverQ-x86_64.AppImage",
     "size": 40345600,
     "released_at": "2026-06-15"
   }
   ```
4. 重新部署 Pages：
   ```bash
   wrangler pages deploy docs-site --project-name=quaverq
   ```

## 短链

- `https://<pages-domain>/download` → `https://cdn.quaverq.nvimer.org/latest/QuaverQ-x86_64.AppImage`（302）

## 部署到 Cloudflare Pages

仓库闭源，建议用 **手动上传**（不接 Git 集成，避免暴露源码）：

```bash
npm i -g wrangler
wrangler login

# 首次创建项目（仅一次）
wrangler pages project create quaverq --production-branch=main

# 每次部署
wrangler pages deploy docs-site --project-name=quaverq --branch=main
```

也可以本地把 `docs-site/` 打包成 zip 后用 Cloudflare 仪表盘的 **Direct Upload** 拖上去。

## 本地预览

任意静态服务器即可，例如：

```bash
cd docs-site
python -m http.server 8080
# → http://localhost:8080
```

直接 `file://` 双击 `index.html` 也能看，但 `_headers` / `_redirects` 在本地无效（这俩是 Cloudflare Pages 平台特性）。

## 待办

- [ ] 在 Cloudflare R2 桶下创建 `latest/` + 首版 `v0.1.0/` 路径并上传 AppImage
- [ ] 补充实际软件截图区块（当前版本未包含截图，避免误用设计参考素材）
- [ ] 给 Pages 接入自定义域名
- [ ] 视情况引入轻量站点统计（如 Cloudflare Web Analytics，零侵入）
- [ ] 考虑用 Cloudflare Worker 包一层下载入口，做下载量统计 / 防盗链
