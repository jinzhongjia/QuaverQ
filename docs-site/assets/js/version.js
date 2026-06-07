(() => {
  const REPO = "jinzhongjia/quaverq";
  const API = `https://api.github.com/repos/${REPO}/releases/latest`;
  const LATEST_ASSET_URL = `https://github.com/${REPO}/releases/latest/download/QuaverQ-x86_64.AppImage`;
  const CACHE_KEY = "quaverq:latest-release";
  const CACHE_TTL_MS = 10 * 60 * 1000;

  const $badge = document.getElementById("version-badge");
  const $mini = document.getElementById("version-mini");
  const $downloadBtns = document.querySelectorAll("#download-btn, #download-btn-2");

  function applyVersion(tagName, assetUrl) {
    const label = tagName ? `最新版本 ${tagName}` : "最新版本";
    if ($badge) $badge.textContent = label;
    if ($mini) $mini.textContent = tagName || "latest";
    $downloadBtns.forEach((btn) => {
      btn.setAttribute("href", assetUrl);
    });
  }

  function applyFallback() {
    if ($badge) $badge.textContent = "最新版本";
    if ($mini) $mini.textContent = "latest";
    $downloadBtns.forEach((btn) => {
      btn.setAttribute("href", LATEST_ASSET_URL);
    });
  }

  function pickAssetUrl(release) {
    if (!release || !Array.isArray(release.assets)) return LATEST_ASSET_URL;
    const appImage = release.assets.find((a) => a.name && a.name.endsWith(".AppImage"));
    return appImage ? appImage.browser_download_url : LATEST_ASSET_URL;
  }

  function readCache() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return null;
      if (Date.now() - parsed.ts > CACHE_TTL_MS) return null;
      return parsed.data;
    } catch {
      return null;
    }
  }

  function writeCache(data) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data }));
    } catch {
      /* quota / privacy mode — ignore */
    }
  }

  async function load() {
    applyFallback();
    const cached = readCache();
    if (cached) {
      applyVersion(cached.tag_name, pickAssetUrl(cached));
    }
    try {
      const res = await fetch(API, {
        headers: { Accept: "application/vnd.github+json" },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`GitHub API ${res.status}`);
      const data = await res.json();
      writeCache({ tag_name: data.tag_name, assets: data.assets });
      applyVersion(data.tag_name, pickAssetUrl(data));
    } catch (err) {
      console.warn("[QuaverQ] 拉取最新版本失败，使用 latest 直链兜底:", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
