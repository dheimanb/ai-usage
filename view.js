// Pure render logic for index.html (also loaded by test_view.js in node).
(function (root) {
  const HOUR = 3600e3;
  const STALE_MS = 24 * HOUR;

  // Thresholds from PRD v4 §5: 70% 慳住用, 90% 只做急嘢, 剩 3% 停.
  function level(used) {
    if (used === null || used === undefined || Number.isNaN(used)) return "none";
    if (used >= 97) return "stop";
    if (used >= 90) return "red";
    if (used >= 70) return "yellow";
    return "green";
  }
  const LEVEL_TEXT = { none: "未有數", green: "正常", yellow: "慳住用", red: "只做急嘢", stop: "停，報 heiman" };

  function isStale(updatedAt, now) {
    if (!updatedAt) return false;
    const t = Date.parse(updatedAt);
    return Number.isNaN(t) ? true : now - t > STALE_MS;
  }

  function fmtHKT(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    // fixed +08:00, no Intl dependency
    const h = new Date(d.getTime() + 8 * HOUR);
    const p = (n) => String(n).padStart(2, "0");
    return `${h.getUTCMonth() + 1}月${h.getUTCDate()}日 ${p(h.getUTCHours())}:${p(h.getUTCMinutes())} HKT`;
  }

  function countdown(iso, now) {
    if (!iso) return "";
    const ms = Date.parse(iso) - now;
    if (Number.isNaN(ms)) return "";
    if (ms <= 0) return "已過 reset，等更新";
    const d = Math.floor(ms / (24 * HOUR)), h = Math.floor((ms % (24 * HOUR)) / HOUR), m = Math.floor((ms % HOUR) / 60e3);
    if (d > 0) return `仲有 ${d} 日 ${h} 個鐘`;
    if (h > 0) return `仲有 ${h} 個鐘 ${m} 分`;
    return `仲有 ${m} 分鐘`;
  }

  function ago(iso, now) {
    if (!iso) return "未更新過";
    const ms = now - Date.parse(iso);
    if (Number.isNaN(ms)) return "時間錯";
    if (ms < 60e3) return "啱啱";
    if (ms < HOUR) return `${Math.floor(ms / 60e3)} 分鐘前`;
    if (ms < 24 * HOUR) return `${Math.floor(ms / HOUR)} 個鐘前`;
    return `${Math.floor(ms / (24 * HOUR))} 日前`;
  }

  function viewRow(r, now) {
    const used = typeof r.used_pct === "number" ? r.used_pct : null;
    const lv = level(used);
    return {
      service: r.service,
      name: r.name || r.service,
      level: lv,
      levelText: LEVEL_TEXT[lv],
      usedText: used === null ? "未有數" : `${used.toFixed(1)}%`,
      leftText: used === null ? "" : `剩 ${(100 - used).toFixed(1)}%`,
      barPct: used === null ? 0 : Math.max(0, Math.min(100, used)),
      reset: fmtHKT(r.reset_at),
      countdown: countdown(r.reset_at, now),
      updated: r.updated_at ? `${fmtHKT(r.updated_at)}（${ago(r.updated_at, now)}）` : "未更新過",
      stale: isStale(r.updated_at, now),
      source: r.source === "ai-self" ? "AI 自報" : "script",
    };
  }

  const api = { level, isStale, fmtHKT, countdown, ago, viewRow, LEVEL_TEXT };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.UsageView = api;
})(this);
