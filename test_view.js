// node test_view.js — thresholds, stale, null, countdown.
const assert = require("assert");
const V = require("./view.js");
const now = Date.parse("2026-10-29T02:00:00+08:00");
const row = (u, upd = "2026-10-29T01:00:00+08:00", reset = "2026-10-30T16:19:00+08:00") =>
  V.viewRow({ service: "grok", name: "Grok 共用池", used_pct: u, reset_at: reset, updated_at: upd, source: "script" }, now);
const cases = [[0, "green"], [69.9, "green"], [70, "yellow"], [89.9, "yellow"], [90, "red"], [96.9, "red"], [97, "stop"], [100, "stop"]];
for (const [u, lv] of cases) assert.strictEqual(row(u).level, lv, `used ${u}`);
assert.strictEqual(row(null).level, "none"); assert.strictEqual(row(null).usedText, "未有數");
assert.strictEqual(row(97).levelText, "停，報 heiman");
assert.strictEqual(row(10, "2026-10-28T01:59:00+08:00").stale, true);   // 24h01m
assert.strictEqual(row(10, "2026-10-28T02:01:00+08:00").stale, false);  // 23h59m
assert.strictEqual(row(10, "2026-10-28T18:00:00Z").stale, false);      // 02:00 HKT = now
assert.strictEqual(V.viewRow({ service: "muse", used_pct: null, reset_at: null, updated_at: null, source: "ai-self" }, now).stale, false);
assert.strictEqual(row(10).reset, "10月30日 16:19 HKT");
assert.strictEqual(row(10).countdown, "仲有 1 日 14 個鐘");
assert.strictEqual(row(10, undefined, "2026-10-29T01:00:00+08:00").countdown, "已過 reset，等更新");
assert.strictEqual(V.fmtHKT("2026-10-29T08:19:00Z"), "10月29日 16:19 HKT");
console.log(`view tests OK (${cases.length + 10} assertions)`);
