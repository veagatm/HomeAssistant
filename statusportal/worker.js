// House Status Portal — Cloudflare Worker
// Routes:
//   GET  /            → dashboard (requires auth)
//   GET  /login       → login form
//   POST /login       → set session cookie
//   GET  /logout      → clear session
//   POST /api/heartbeat → receive status from Mac Mini daemon (requires API key)

const SESSION_COOKIE = 'hsp_session';
const SESSION_TTL_HOURS = 24;

// ── Auth helpers ──────────────────────────────────────────────────────────────

function makeSessionToken() {
  const arr = new Uint8Array(32);
  crypto.getRandomValues(arr);
  return Array.from(arr).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function verifySession(request, env) {
  const cookie = request.headers.get('Cookie') || '';
  const match = cookie.match(new RegExp(`${SESSION_COOKIE}=([a-f0-9]{64})`));
  if (!match) return false;
  const stored = await env.HSP_KV.get(`session:${match[1]}`);
  return stored !== null;
}

function loginPage(error = '') {
  return new Response(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>House Status — Login</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f172a; color: #e2e8f0; min-height: 100vh;
           display: flex; align-items: center; justify-content: center; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px;
            padding: 40px; width: 100%; max-width: 360px; }
    h1 { font-size: 1.3rem; margin-bottom: 6px; }
    .sub { color: #64748b; font-size: 0.85rem; margin-bottom: 28px; }
    label { display: block; font-size: 0.8rem; color: #94a3b8;
            text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
    input[type=password] { width: 100%; padding: 10px 14px; background: #0f172a;
      border: 1px solid #334155; border-radius: 8px; color: #e2e8f0;
      font-size: 1rem; outline: none; }
    input[type=password]:focus { border-color: #6366f1; }
    button { margin-top: 20px; width: 100%; padding: 11px;
             background: #6366f1; color: white; border: none;
             border-radius: 8px; font-size: 1rem; cursor: pointer; }
    button:hover { background: #4f46e5; }
    .error { color: #f87171; font-size: 0.85rem; margin-top: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>House Status</h1>
    <p class="sub">example.net</p>
    <form method="POST" action="/login">
      <label>Password</label>
      <input type="password" name="password" autofocus autocomplete="current-password">
      <button type="submit">Sign in</button>
      ${error ? `<p class="error">${error}</p>` : ''}
    </form>
  </div>
</body>
</html>`, { headers: { 'Content-Type': 'text/html' } });
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

function ageLabel(lastSeenISO) {
  if (!lastSeenISO) return 'never';
  const secs = (Date.now() - new Date(lastSeenISO).getTime()) / 1000;
  if (secs < 90) return 'just now';
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  return `${Math.round(secs / 3600)}h ago`;
}

function statusBadge(ok, label) {
  const color = ok ? '#22c55e' : '#ef4444';
  const text  = ok ? 'Online'  : 'Offline';
  return `<span style="color:${color};font-weight:600">${text}</span>`;
}

function deviceCard(device) {
  const ok     = device.online;
  const border = ok ? '#1d4a2f' : '#4a1d1d';
  const bg     = ok ? '#0d2818' : '#1e0c0c';
  const icon   = ok ? '✓' : '✗';
  const iconC  = ok ? '#22c55e' : '#ef4444';
  return `
    <div style="background:${bg};border:1px solid ${border};border-radius:10px;
                padding:18px 20px;display:flex;align-items:center;gap:16px">
      <div style="font-size:1.4rem;color:${iconC};font-weight:700;min-width:24px">${icon}</div>
      <div style="flex:1">
        <div style="font-weight:600;font-size:0.95rem">${device.name}</div>
        <div style="color:#64748b;font-size:0.8rem;margin-top:2px">${device.ip}${device.port ? `:${device.port}` : ''}</div>
        ${device.latency_ms != null && ok ? `<div style="color:#64748b;font-size:0.75rem">${device.latency_ms}ms</div>` : ''}
      </div>
      <div style="text-align:right">
        ${statusBadge(ok)}
      </div>
    </div>`;
}

function dashboard(data) {
  const agentAge = ageLabel(data?.timestamp);
  const agentStale = !data?.timestamp || (Date.now() - new Date(data.timestamp).getTime()) > 3 * 60 * 1000;
  const devices = data?.devices || [];
  const allOnline = devices.every(d => d.online);
  const offlineCount = devices.filter(d => !d.online).length;

  const summaryColor = agentStale ? '#f59e0b' : allOnline ? '#22c55e' : '#ef4444';
  const summaryText  = agentStale
    ? `Agent offline — last report ${agentAge}`
    : allOnline ? 'All systems online' : `${offlineCount} device${offlineCount > 1 ? 's' : ''} offline`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>House Status</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 32px 16px; }
    .wrap { max-width: 640px; margin: 0 auto; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
    h1 { font-size: 1.4rem; }
    .sub { color: #64748b; font-size: 0.8rem; margin-top: 2px; }
    a.logout { color: #64748b; font-size: 0.8rem; text-decoration: none; }
    a.logout:hover { color: #e2e8f0; }
    .summary { border-radius: 10px; padding: 16px 20px; margin-bottom: 24px;
               background: #1e293b; border: 1px solid #334155;
               display: flex; align-items: center; gap: 12px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: ${summaryColor}; flex-shrink: 0; }
    .devices { display: flex; flex-direction: column; gap: 10px; }
    .section-label { font-size: 0.75rem; text-transform: uppercase;
                     letter-spacing: .08em; color: #475569; margin: 20px 0 8px; }
    footer { margin-top: 32px; color: #334155; font-size: 0.75rem; text-align: center; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>House Status</h1>
        <div class="sub">Updated ${agentAge} &nbsp;·&nbsp; auto-refreshes every 60s</div>
      </div>
      <a class="logout" href="/logout">Sign out</a>
    </header>

    <div class="summary">
      <div class="dot" style="background:${summaryColor}"></div>
      <div style="font-weight:600">${summaryText}</div>
    </div>

    <div class="section-label">Network & Infrastructure</div>
    <div class="devices">
      ${devices.filter(d => d.group === 'network').map(deviceCard).join('')}
    </div>

    <div class="section-label">Home Automation</div>
    <div class="devices">
      ${devices.filter(d => d.group === 'ha').map(deviceCard).join('')}
    </div>

    <div class="section-label">Services</div>
    <div class="devices">
      ${devices.filter(d => d.group === 'service').map(deviceCard).join('')}
    </div>

    <footer>example.net &nbsp;·&nbsp; House Status Portal</footer>
  </div>
</body>
</html>`;
}

// ── Main handler ──────────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url  = new URL(request.url);
    const path = url.pathname;

    // ── Heartbeat API (Mac Mini daemon → Worker) ──────────────────────────────
    if (path === '/api/heartbeat' && request.method === 'POST') {
      const apiKey = request.headers.get('X-API-Key');
      if (apiKey !== env.API_KEY) {
        return new Response('Unauthorized', { status: 401 });
      }
      const body = await request.json();
      await env.HSP_KV.put('status', JSON.stringify({ ...body, timestamp: new Date().toISOString() }));
      return new Response('ok');
    }

    // ── Login ─────────────────────────────────────────────────────────────────
    if (path === '/login') {
      if (request.method === 'GET') return loginPage();

      if (request.method === 'POST') {
        const form = await request.formData();
        const pwd  = form.get('password');
        if (pwd !== env.DASHBOARD_PASSWORD) {
          return loginPage('Incorrect password.');
        }
        const token = makeSessionToken();
        await env.HSP_KV.put(`session:${token}`, '1', { expirationTtl: SESSION_TTL_HOURS * 3600 });
        return new Response(null, {
          status: 302,
          headers: {
            Location: '/',
            'Set-Cookie': `${SESSION_COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_TTL_HOURS * 3600}`,
          },
        });
      }
    }

    // ── Logout ────────────────────────────────────────────────────────────────
    if (path === '/logout') {
      return new Response(null, {
        status: 302,
        headers: {
          Location: '/login',
          'Set-Cookie': `${SESSION_COOKIE}=; Path=/; HttpOnly; Secure; Max-Age=0`,
        },
      });
    }

    // ── Dashboard (auth-gated) ────────────────────────────────────────────────
    if (path === '/') {
      const authed = await verifySession(request, env);
      if (!authed) return new Response(null, { status: 302, headers: { Location: '/login' } });

      const raw  = await env.HSP_KV.get('status');
      const data = raw ? JSON.parse(raw) : null;
      return new Response(dashboard(data), { headers: { 'Content-Type': 'text/html' } });
    }

    return new Response('Not found', { status: 404 });
  },
};
