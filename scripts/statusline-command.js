#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const os = require('os');

const CACHE_TTL = 60;
const BAR_W = 10;
const CREDS = path.join(os.homedir(), '.claude', '.credentials.json');
const CACHE = path.join(os.tmpdir(), 'claude-usage-cache.json');

const bar = (pct) => {
  const f = Math.max(0, Math.min(BAR_W, Math.round((pct / 100) * BAR_W)));
  return '\u2588'.repeat(f) + '\u2591'.repeat(BAR_W - f);
};

const shortNum = (n) => {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return String(n);
};

const normPct = (v) => {
  if (v == null || v === '') return null;
  const n = Number(v);
  return isNaN(n) ? null : n <= 1 ? n * 100 : n;
};

const fmtTime = (iso) => {
  if (!iso) return '?';
  try { return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }); }
  catch { return '?'; }
};

const fmtDate = (iso) => {
  if (!iso) return '?';
  try { return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); }
  catch { return '?'; }
};

async function getRL() {
  let token;
  try {
    const o = JSON.parse(fs.readFileSync(CREDS, 'utf8')).claudeAiOauth;
    if (!o?.accessToken || (o.expiresAt && Date.now() >= o.expiresAt)) return null;
    token = o.accessToken;
  } catch { return null; }

  let data = null;
  try {
    const age = (Date.now() - fs.statSync(CACHE).mtimeMs) / 1000;
    if (age < CACHE_TTL) data = JSON.parse(fs.readFileSync(CACHE, 'utf8'));
  } catch {}

  if (!data) {
    try {
      const r = await fetch('https://api.anthropic.com/api/oauth/usage', {
        headers: { 'Authorization': `Bearer ${token}`, 'anthropic-beta': 'oauth-2025-04-20' },
        signal: AbortSignal.timeout(5000),
      });
      if (r.ok) { data = await r.json(); fs.writeFileSync(CACHE, JSON.stringify(data)); }
    } catch {}
  }
  if (!data) return null;

  const d = data.rate_limits || data;
  const fh = d.five_hour || {}, sd = d.seven_day || {};
  return {
    fh: { pct: normPct(fh.utilization ?? fh.used_percentage), rst: fh.resets_at },
    sd: { pct: normPct(sd.utilization ?? sd.used_percentage), rst: sd.resets_at },
  };
}

async function main() {
  let input = {};
  try { input = JSON.parse(fs.readFileSync(0, 'utf8')); } catch {}

  const cw = input.context_window || {};
  const u = cw.current_usage || {};
  const ctxUsed = u.input_tokens || 0;
  const ctxLimit = cw.context_window_size || 0;
  const ctxPct = cw.used_percentage || 0;
  const model = input.model?.display_name || 'Claude';

  const rl = await getRL();

  // Line 1: rate limits
  let line1;
  if (rl?.fh.pct != null) {
    const f = rl.fh, s = rl.sd;
    const sPct = s.pct != null ? `${Math.round(s.pct)}%` : 'N/A';
    const sBar = s.pct != null ? bar(s.pct) : '\u2591'.repeat(BAR_W);
    line1 = `5h ${bar(f.pct)} ${Math.round(f.pct)}% \u21bb${fmtTime(f.rst)} \u2502 7d ${sBar} ${sPct} \u21bb${fmtDate(s.rst)}`;
  } else {
    const e = '\u2591'.repeat(BAR_W);
    line1 = `5h ${e} N/A \u2502 7d ${e} N/A`;
  }

  // Line 2: context
  const line2 = `${model} \u2502 CTX ${bar(ctxPct)} ${Math.round(ctxPct)}% ${shortNum(ctxUsed)}/${shortNum(ctxLimit)}`;

  process.stdout.write(`${line1}\n${line2}`);
}

main().catch(() => process.stdout.write('err'));
