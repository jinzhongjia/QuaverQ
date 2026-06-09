(() => {
  const VERSION_URL = "/version.json";
  const FALLBACK_DOWNLOAD = "/download";

  const $badge = document.getElementById("version-badge");
  const $mini = document.getElementById("version-mini");
  const $releaseMeta = document.getElementById("release-meta");
  const $downloadBtns = document.querySelectorAll("#download-btn, #download-btn-2");

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return null;
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    let n = bytes;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i += 1;
    }
    return `${n.toFixed(n >= 100 ? 0 : 1)} ${units[i]}`;
  }

  function applyVersion(meta) {
    const version = meta && meta.version ? meta.version : null;
    const url = meta && meta.url ? meta.url : FALLBACK_DOWNLOAD;

    if ($badge) {
      $badge.textContent = version ? `最新版本 ${version}` : "最新版本";
    }
    if ($mini) {
      $mini.textContent = version || "latest";
    }
    if ($releaseMeta) {
      const parts = ["AppImage", "x86_64"];
      const size = meta && formatBytes(meta.size);
      if (size) parts.push(size);
      if (meta && meta.released_at) parts.push(meta.released_at);
      $releaseMeta.textContent = parts.join(" · ");
    }
    $downloadBtns.forEach((btn) => {
      btn.setAttribute("href", url);
    });
  }

  function applyFallback() {
    if ($badge) $badge.textContent = "最新版本";
    if ($mini) $mini.textContent = "latest";
    $downloadBtns.forEach((btn) => {
      btn.setAttribute("href", FALLBACK_DOWNLOAD);
    });
  }

  async function load() {
    applyFallback();
    try {
      const res = await fetch(VERSION_URL, { cache: "no-store" });
      if (!res.ok) throw new Error(`version.json ${res.status}`);
      const data = await res.json();
      applyVersion(data);
    } catch (err) {
      console.warn("[QuaverQ] 拉取 version.json 失败，使用 /download 兜底:", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
