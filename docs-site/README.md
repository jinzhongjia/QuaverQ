# QuaverQ 官网（静态站）

`docs-site/` 是 QuaverQ 的纯静态介绍页，部署在 [Cloudflare Pages](https://pages.cloudflare.com/)。

## 目录结构

```
docs-site/
├── index.html              # 单页落地页（Hero / 功能 / 下载 / FAQ / Footer）
├── assets/
│   ├── css/style.css       # 全部样式（CSS 变量 + 明暗双主题，prefers-color-scheme）
│   ├── js/version.js       # 运行时拉取 GitHub Releases 最新版本号
│   └── img/logo.svg        # Logo（同步自 assets/io.github.jinzhongjia.quaverq.svg）
├── _headers                # Cloudflare 安全响应头 + 缓存策略
├── _redirects              # 短链：/download → 最新 AppImage 直链
└── README.md               # 本文件
```

## 设计要点

- 纯 HTML + CSS + 一段 JS，**零构建依赖**，本地双击 `index.html` 即可预览
- 颜色 / 排版对齐 `qq-music-design` skill（品牌绿 `#31C27C`，PingFang/Microsoft YaHei 字体栈）
- 明暗双主题通过 `prefers-color-scheme` 自动跟随系统
- 响应式：3 列 → 2 列 → 1 列断点切换

## 版本号自动化

页面加载时 `assets/js/version.js` 会请求 GitHub Releases API：

```
GET https://api.github.com/repos/jinzhongjia/quaverq/releases/latest
```

拉到 `tag_name`（如 `v0.1.0`）后写入页面顶部的版本徽标和下载卡片角标，同时把下载按钮 `href` 替换为该 release 中实际的 AppImage 资源 URL。

兜底逻辑（接口失败 / 限流 / 离线）：

- 徽标显示"最新版本"
- 下载按钮回退到 `/releases/latest/download/QuaverQ-x86_64.AppImage`（GitHub 自动 302 到最新版本对应资源）

成功响应会缓存到 `localStorage` 10 分钟，避免每次访问都打 GitHub API。

## 短链

- `https://<domain>/download` → 最新 AppImage 直链
- `https://<domain>/releases` → GitHub Releases 列表
- `https://<domain>/repo` → 仓库主页
- `https://<domain>/issues` → Issue 列表

## 部署到 Cloudflare Pages

### 方式 A：Git 集成（推荐）

1. 登录 Cloudflare 仪表盘 → **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**
2. 选择 `jinzhongjia/quaverq` 仓库
3. 构建配置：
   - **Framework preset**: `None`
   - **Build command**: 留空
   - **Build output directory**: `docs-site`
   - **Root directory**: `/`（默认）
4. 保存后每次 push 到 `main` 自动重新部署；PR 自动生成预览域名

### 方式 B：手动上传（开发调试用）

```bash
npm i -g wrangler
cd docs-site
wrangler pages deploy . --project-name=quaverq
```

## 本地预览

任意静态服务器即可，例如：

```bash
cd docs-site
python -m http.server 8080
# → http://localhost:8080
```

直接 `file://` 双击 `index.html` 也能看，仅 `_headers` / `_redirects` 在本地无效（这俩是 Cloudflare Pages 平台特性）。

## 待办

- [ ] 补充实际软件截图区块（当前版本未包含截图，避免误用设计参考素材）
- [ ] 接入自定义域名（Cloudflare Pages 仪表盘绑定）
- [ ] 视情况引入轻量站点统计（如 Cloudflare Web Analytics，零侵入）
