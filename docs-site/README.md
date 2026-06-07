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

## 发版流程

两种发版路径，按需选用。**仓库闭源**，所以不使用 Pages 的 Git 集成（避免暴露源码）。

### 一次性准备

```bash
npm i -g wrangler
wrangler login

# 首次创建 Pages 项目（仅一次）
wrangler pages project create quaverq --production-branch=main

# 首次创建 R2 桶（仅一次）
wrangler r2 bucket create quaverq
# 然后在 Cloudflare 仪表盘把 cdn.quaverq.nvimer.org 自定义域名绑定到这个桶
```

### 方式 A：本地一键脚本（推荐日常用）

```bash
./scripts/release.sh v0.2.0
```

脚本会按顺序：
1. `uv run python build.py --appimage` 构建 AppImage
2. `wrangler r2 object put` 上传两份（`v0.2.0/` 归档 + `latest/` 覆盖）
3. 改写 `docs-site/version.json`（version / size / released_at / url 全部自动算好）
4. `wrangler pages deploy` 部署静态站

跑完后手动 commit 一下 `version.json` 即可。

可覆盖的环境变量：`R2_BUCKET`（默认 `quaverq`）、`PAGES_PROJECT`（默认 `quaverq`）、`CDN_HOST`（默认 `cdn.quaverq.nvimer.org`）。

### 方式 B：GitHub Actions 自动发版

push 一个 `v*` tag 即触发，或在 Actions 页面手动 workflow_dispatch 输入版本号。配置见 [`.github/workflows/release.yml`](../.github/workflows/release.yml)。

需要预先在仓库 **Settings → Secrets and variables → Actions** 配置：

| Secret | 内容 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | API Token，权限需含 `R2:Edit` + `Pages:Edit`（在 [API Tokens](https://dash.cloudflare.com/profile/api-tokens) 创建） |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账号 ID（仪表盘右下角或任意 R2/Pages 页面 URL 里） |

完整流程：

```bash
git tag v0.2.0
git push origin v0.2.0
# CI 自动跑：构建 → 改 version.json → 上传 R2 ×2 → 部署 Pages
```

⚠️ 注意：CI 在 workspace 内改 `version.json` 但 **不会** commit 回 git 仓库，避免 push 权限污染。tag 发完后建议本地 `git pull` 后 commit 同样的内容到主分支，让仓库的 `version.json` 与线上一致（或者你 `tag` 之前就改好它再 push）。

### 方式 C：仅部署文档（不重建 AppImage）

只改了文案 / 样式时跑：

```bash
./scripts/deploy-docs.sh
```

或直接 `wrangler pages deploy docs-site --project-name=quaverq`。

## 短链

- `https://<pages-domain>/download` → `https://cdn.quaverq.nvimer.org/latest/QuaverQ-x86_64.AppImage`（302）

## 本地预览

任意静态服务器即可，例如：

```bash
cd docs-site
python -m http.server 8080
# → http://localhost:8080
```

直接 `file://` 双击 `index.html` 也能看，但 `_headers` / `_redirects` 在本地无效（这俩是 Cloudflare Pages 平台特性）。

## 待办

- [ ] 在 Cloudflare 创建 R2 桶 `quaverq` 并绑定 `cdn.quaverq.nvimer.org` 自定义域名
- [ ] 在 Cloudflare 创建 Pages 项目 `quaverq`
- [ ] 配置 GitHub Secrets：`CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`
- [ ] 首次跑 `./scripts/release.sh v0.1.0` 把 AppImage 推上 R2
- [ ] 补充实际软件截图区块（当前版本未包含截图，避免误用设计参考素材）
- [ ] 给 Pages 接入自定义域名
- [ ] 视情况引入轻量站点统计（如 Cloudflare Web Analytics，零侵入）
- [ ] 考虑用 Cloudflare Worker 包一层下载入口，做下载量统计 / 防盗链
