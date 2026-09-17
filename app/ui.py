from fastapi.responses import HTMLResponse


PORTFOLIO_UI = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI PR Reviewer</title>
  <meta name="description" content="AI-assisted GitHub pull request review application built with FastAPI, OpenAI, GitHub, and Microsoft Graph.">
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111f;
      --surface: #0c192b;
      --surface-2: #112239;
      --border: #243750;
      --text: #f4f7fb;
      --muted: #9eb0c7;
      --accent: #7dd3fc;
      --accent-2: #a78bfa;
      --success: #5ee7a2;
      --warning: #facc6b;
      --danger: #fb7185;
      --shadow: 0 24px 70px rgba(0, 0, 0, .32);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 18% 0%, rgba(125, 211, 252, .14), transparent 30rem),
        radial-gradient(circle at 88% 8%, rgba(167, 139, 250, .14), transparent 28rem),
        var(--bg);
    }
    a { color: inherit; }
    .shell { width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 56px; }
    .nav { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 58px; }
    .brand { display: flex; align-items: center; gap: 12px; font-weight: 800; letter-spacing: -.02em; }
    .logo {
      width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #07111f; font-weight: 900;
      box-shadow: 0 10px 30px rgba(125, 211, 252, .18);
    }
    .nav-links { display: flex; gap: 10px; }
    .nav-link { color: var(--muted); text-decoration: none; padding: 8px 12px; border-radius: 10px; }
    .nav-link:hover { background: rgba(255,255,255,.05); color: var(--text); }
    .hero { display: grid; grid-template-columns: 1.05fr .95fr; gap: 42px; align-items: center; margin-bottom: 48px; }
    .eyebrow { display: inline-flex; align-items: center; gap: 8px; color: var(--accent); font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; }
    .eyebrow::before { content: ""; width: 18px; height: 2px; background: var(--accent); border-radius: 999px; }
    h1 { margin: 16px 0 18px; font-size: clamp(42px, 6vw, 68px); line-height: .98; letter-spacing: -.055em; }
    .hero-copy { margin: 0; max-width: 650px; color: var(--muted); font-size: 18px; line-height: 1.65; }
    .stack { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 24px; }
    .chip { padding: 7px 10px; border: 1px solid var(--border); border-radius: 999px; color: #bfd0e3; font-size: 12px; background: rgba(255,255,255,.025); }
    .panel {
      border: 1px solid var(--border); background: linear-gradient(180deg, rgba(17,34,57,.92), rgba(9,22,39,.92));
      border-radius: 22px; box-shadow: var(--shadow); overflow: hidden;
    }
    .panel-head { padding: 18px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    .dots { display: flex; gap: 6px; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: #38516f; }
    .terminal { padding: 23px; font: 13px/1.75 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #b9cbe0; min-height: 260px; }
    .terminal .prompt { color: var(--success); }
    .terminal .key { color: var(--accent); }
    .terminal .value { color: #d9c6ff; }
    .terminal .dim { color: #71869f; }
    .workspace { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 22px; align-items: start; }
    .card { border: 1px solid var(--border); background: rgba(12,25,43,.86); border-radius: 20px; padding: 24px; box-shadow: 0 18px 55px rgba(0,0,0,.18); }
    .card h2, .card h3 { margin: 0; letter-spacing: -.025em; }
    .card-sub { color: var(--muted); margin: 8px 0 22px; line-height: 1.55; }
    label { display: block; margin: 16px 0 8px; font-size: 13px; color: #c5d4e5; font-weight: 700; }
    input {
      width: 100%; border: 1px solid var(--border); border-radius: 12px; background: #071424; color: var(--text);
      padding: 13px 14px; font: inherit; outline: none; transition: .18s ease;
    }
    input:focus { border-color: rgba(125,211,252,.7); box-shadow: 0 0 0 3px rgba(125,211,252,.08); }
    .hint { margin-top: 7px; color: #71869f; font-size: 12px; line-height: 1.5; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 22px; }
    button {
      appearance: none; border: 0; cursor: pointer; font: inherit; font-weight: 800; border-radius: 12px; padding: 12px 16px;
      transition: transform .15s ease, opacity .15s ease, background .15s ease;
    }
    button:hover:not(:disabled) { transform: translateY(-1px); }
    button:disabled { opacity: .48; cursor: not-allowed; }
    .primary { background: linear-gradient(135deg, var(--accent), #93c5fd); color: #06101c; }
    .secondary { background: #172a43; color: #d6e4f3; border: 1px solid var(--border); }
    .ghost { background: transparent; color: var(--muted); border: 1px solid var(--border); }
    .security { display: flex; align-items: flex-start; gap: 10px; color: var(--muted); font-size: 12px; line-height: 1.5; margin-top: 18px; }
    .lock { color: var(--success); font-weight: 900; }
    .side-list { display: grid; gap: 15px; margin-top: 20px; }
    .feature { display: grid; grid-template-columns: 34px 1fr; gap: 11px; align-items: start; }
    .feature-icon { width: 34px; height: 34px; border: 1px solid var(--border); border-radius: 10px; display: grid; place-items: center; color: var(--accent); background: #0a1728; font-weight: 800; }
    .feature strong { display: block; font-size: 13px; margin-top: 1px; }
    .feature span { color: var(--muted); font-size: 12px; line-height: 1.45; }
    .status { margin-top: 16px; padding: 11px 12px; border-radius: 11px; border: 1px solid var(--border); color: var(--muted); font-size: 13px; display: none; }
    .status.show { display: block; }
    .status.error { border-color: rgba(251,113,133,.32); color: #fecdd3; background: rgba(251,113,133,.07); }
    .status.ok { border-color: rgba(94,231,162,.3); color: #bbf7d0; background: rgba(94,231,162,.06); }
    #results { display: none; margin-top: 22px; }
    #results.show { display: block; }
    .result-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
    .result-title { font-size: 20px; font-weight: 850; }
    .meta { color: var(--muted); font-size: 13px; margin-top: 5px; }
    .badge { border: 1px solid var(--border); padding: 7px 10px; border-radius: 999px; font-weight: 850; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; white-space: nowrap; }
    .badge.low { color: var(--success); border-color: rgba(94,231,162,.35); background: rgba(94,231,162,.06); }
    .badge.medium { color: var(--warning); border-color: rgba(250,204,107,.35); background: rgba(250,204,107,.06); }
    .badge.high, .badge.critical { color: #fda4af; border-color: rgba(251,113,133,.35); background: rgba(251,113,133,.06); }
    .summary-box { background: #091727; border: 1px solid var(--border); border-radius: 14px; padding: 17px; color: #d7e2ef; line-height: 1.65; }
    .section-title { margin: 24px 0 11px; font-size: 13px; color: #b8caDE; text-transform: uppercase; letter-spacing: .1em; font-weight: 850; }
    .issue-list { display: grid; gap: 11px; }
    .issue { border: 1px solid var(--border); border-radius: 14px; padding: 15px; background: rgba(7,20,36,.72); }
    .issue-head { display: flex; gap: 9px; align-items: center; margin-bottom: 8px; }
    .severity { font-size: 10px; text-transform: uppercase; font-weight: 900; letter-spacing: .08em; color: var(--warning); }
    .issue-title { font-weight: 800; }
    .issue-detail, .issue-rec, .test-item { color: var(--muted); font-size: 13px; line-height: 1.6; }
    .issue-rec { margin-top: 8px; color: #c9d7e7; }
    .file { margin-top: 8px; font: 11px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--accent); }
    .test-list { display: grid; gap: 8px; }
    .test-item { padding: 10px 12px; border-left: 2px solid var(--accent-2); background: rgba(167,139,250,.045); border-radius: 0 9px 9px 0; }
    .recommendation { margin-top: 20px; display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 14px 16px; border-radius: 14px; background: linear-gradient(90deg, rgba(125,211,252,.08), rgba(167,139,250,.07)); border: 1px solid var(--border); }
    .recommendation strong { text-transform: uppercase; letter-spacing: .06em; font-size: 13px; }
    footer { text-align: center; color: #698098; font-size: 12px; margin-top: 42px; line-height: 1.6; }
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(7,17,31,.28); border-top-color: #07111f; border-radius: 50%; animation: spin .75s linear infinite; vertical-align: -2px; margin-right: 8px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (max-width: 860px) {
      .hero, .workspace { grid-template-columns: 1fr; }
      .hero { gap: 28px; }
      .nav { margin-bottom: 38px; }
      .side-card { order: -1; }
    }
    @media (max-width: 560px) {
      .shell { width: min(100% - 20px, 1120px); padding-top: 16px; }
      .nav-links { display: none; }
      .card { padding: 18px; }
      .result-top, .recommendation { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <nav class="nav">
      <div class="brand"><div class="logo">AI</div><span>PR Reviewer</span></div>
      <div class="nav-links">
        <a class="nav-link" href="/docs" target="_blank" rel="noreferrer">API Docs</a>
        <a class="nav-link" href="https://github.com/Khumo-Hub/AI-PR-Reviewer-application" target="_blank" rel="noreferrer">GitHub</a>
      </div>
    </nav>

    <section class="hero">
      <div>
        <span class="eyebrow">AI-assisted code review</span>
        <h1>Review pull requests with an AI second pair of eyes.</h1>
        <p class="hero-copy">A portfolio application that combines GitHub pull-request data, structured AI analysis, FastAPI, secure webhooks, and optional Microsoft Outlook drafting in one workflow.</p>
        <div class="stack">
          <span class="chip">FastAPI</span><span class="chip">GitHub API</span><span class="chip">OpenAI</span><span class="chip">Microsoft Graph</span><span class="chip">OAuth 2.0</span><span class="chip">GitHub Actions</span><span class="chip">Render</span>
        </div>
      </div>
      <div class="panel" aria-label="Example structured review">
        <div class="panel-head"><span style="font-size:12px;color:var(--muted)">structured-review.json</span><div class="dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>
        <div class="terminal"><span class="dim">{</span><br>&nbsp;&nbsp;<span class="key">"risk"</span>: <span class="value">"medium"</span>,<br>&nbsp;&nbsp;<span class="key">"issues"</span>: [<br>&nbsp;&nbsp;&nbsp;&nbsp;{ <span class="key">"severity"</span>: <span class="value">"high"</span>, ... }<br>&nbsp;&nbsp;],<br>&nbsp;&nbsp;<span class="key">"tests_missing"</span>: [ ... ],<br>&nbsp;&nbsp;<span class="key">"recommendation"</span>: <span class="value">"changes_requested"</span><br><span class="dim">}</span><br><br><span class="prompt">✓</span> Human remains in the loop</div>
      </div>
    </section>

    <section class="workspace">
      <div>
        <div class="card">
          <h2>Review a pull request</h2>
          <p class="card-sub">Paste a GitHub pull-request URL. The application fetches the live diff and returns a structured engineering review.</p>
          <label for="prUrl">GitHub pull-request URL</label>
          <input id="prUrl" autocomplete="off" spellcheck="false" placeholder="https://github.com/Khumo-Hub/AI-PR-Reviewer-application/pull/12">
          <label for="apiKey">Review API key</label>
          <input id="apiKey" type="password" autocomplete="off" placeholder="Enter your demo key">
          <div class="hint">The key is used only for this request and is not saved by this page.</div>
          <div class="actions">
            <button id="reviewBtn" class="primary">Run AI Review</button>
            <button id="outlookBtn" class="secondary" disabled>Create Outlook Draft</button>
            <button id="connectBtn" class="ghost">Connect Outlook</button>
          </div>
          <div class="security"><span class="lock">◆</span><span>Protected API endpoints, GitHub webhook signature validation, repository allowlisting, and human-controlled Outlook drafting are built into the backend.</span></div>
          <div id="status" class="status" role="status"></div>
        </div>

        <div id="results" class="card" aria-live="polite"></div>
      </div>

      <aside class="card side-card">
        <h3>What this project demonstrates</h3>
        <p class="card-sub">A small full-stack showcase built around a real software engineering workflow.</p>
        <div class="side-list">
          <div class="feature"><div class="feature-icon">GH</div><div><strong>Live GitHub integration</strong><span>Pull-request metadata and unified diffs are fetched through the GitHub API.</span></div></div>
          <div class="feature"><div class="feature-icon">AI</div><div><strong>Structured AI output</strong><span>Reviews return typed risk, issues, missing tests and a recommendation.</span></div></div>
          <div class="feature"><div class="feature-icon">MS</div><div><strong>Microsoft Graph</strong><span>Delegated OAuth can create a review draft while keeping sending human-controlled.</span></div></div>
          <div class="feature"><div class="feature-icon">CI</div><div><strong>Engineering workflow</strong><span>Automated tests, GitHub Actions, pull-request reviews and cloud deployment.</span></div></div>
        </div>
      </aside>
    </section>

    <footer>AI PR Reviewer · Portfolio V1 · Built to demonstrate API integration, AI engineering, security controls, testing and deployment.</footer>
  </main>

  <script>
    const prUrl = document.getElementById('prUrl');
    const apiKey = document.getElementById('apiKey');
    const reviewBtn = document.getElementById('reviewBtn');
    const outlookBtn = document.getElementById('outlookBtn');
    const connectBtn = document.getElementById('connectBtn');
    const statusBox = document.getElementById('status');
    const results = document.getElementById('results');
    let currentPr = null;

    function parsePrUrl(value) {
      try {
        const url = new URL(value.trim());
        if (url.hostname !== 'github.com') return null;
        const parts = url.pathname.split('/').filter(Boolean);
        if (parts.length !== 4 || parts[2] !== 'pull') return null;
        const number = Number(parts[3]);
        if (!Number.isInteger(number) || number < 1) return null;
        return { owner: parts[0], repo: parts[1], number };
      } catch (_) { return null; }
    }

    function setStatus(message, kind = '') {
      statusBox.textContent = message;
      statusBox.className = 'status show' + (kind ? ' ' + kind : '');
    }

    function clearStatus() {
      statusBox.textContent = '';
      statusBox.className = 'status';
    }

    function text(tag, value, className) {
      const el = document.createElement(tag);
      if (className) el.className = className;
      el.textContent = value ?? '';
      return el;
    }

    function renderReview(payload) {
      results.replaceChildren();
      results.classList.add('show');
      const review = payload.review || {};
      const pr = payload.pull_request || {};

      const top = document.createElement('div');
      top.className = 'result-top';
      const left = document.createElement('div');
      left.append(text('div', pr.title || `Pull Request #${pr.number || currentPr.number}`, 'result-title'));
      left.append(text('div', `${payload.repository || (currentPr.owner + '/' + currentPr.repo)} · PR #${pr.number || currentPr.number}`, 'meta'));
      const risk = text('span', `Risk: ${review.risk || 'unknown'}`, `badge ${(review.risk || '').toLowerCase()}`);
      top.append(left, risk);
      results.append(top);

      results.append(text('div', review.summary || 'No summary returned.', 'summary-box'));

      results.append(text('div', 'Issues', 'section-title'));
      const issues = document.createElement('div');
      issues.className = 'issue-list';
      const issueData = Array.isArray(review.issues) ? review.issues : [];
      if (!issueData.length) {
        issues.append(text('div', 'No issues identified in this review.', 'test-item'));
      } else {
        issueData.forEach(item => {
          const card = document.createElement('div'); card.className = 'issue';
          const head = document.createElement('div'); head.className = 'issue-head';
          head.append(text('span', item.severity || 'issue', 'severity'), text('span', item.title || 'Review issue', 'issue-title'));
          card.append(head, text('div', item.detail || '', 'issue-detail'));
          if (item.recommendation) card.append(text('div', `Recommendation: ${item.recommendation}`, 'issue-rec'));
          if (item.file) card.append(text('div', item.file, 'file'));
          issues.append(card);
        });
      }
      results.append(issues);

      results.append(text('div', 'Tests missing', 'section-title'));
      const tests = document.createElement('div'); tests.className = 'test-list';
      const missing = Array.isArray(review.tests_missing) ? review.tests_missing : [];
      if (!missing.length) tests.append(text('div', 'No additional missing tests identified.', 'test-item'));
      missing.forEach(item => tests.append(text('div', item, 'test-item')));
      results.append(tests);

      const rec = document.createElement('div'); rec.className = 'recommendation';
      rec.append(text('span', 'AI recommendation', 'meta'), text('strong', (review.recommendation || 'manual_review').replaceAll('_', ' ')));
      results.append(rec);
      results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async function apiCall(path, options = {}) {
      const key = apiKey.value.trim();
      if (!key) throw new Error('Enter the Review API key first.');
      const headers = { ...(options.headers || {}), 'X-API-Key': key };
      const response = await fetch(path, { ...options, headers });
      let data = {};
      try { data = await response.json(); } catch (_) {}
      if (!response.ok) throw new Error(data.detail || `Request failed with status ${response.status}`);
      return data;
    }

    reviewBtn.addEventListener('click', async () => {
      clearStatus();
      const parsed = parsePrUrl(prUrl.value);
      if (!parsed) { setStatus('Enter a valid GitHub pull-request URL.', 'error'); return; }
      currentPr = parsed;
      reviewBtn.disabled = true;
      outlookBtn.disabled = true;
      reviewBtn.innerHTML = '<span class="spinner"></span>Reviewing…';
      try {
        const data = await apiCall(`/reviews/${encodeURIComponent(parsed.owner)}/${encodeURIComponent(parsed.repo)}/${parsed.number}`, { method: 'POST' });
        renderReview(data);
        outlookBtn.disabled = false;
        setStatus('Review complete. Outlook drafting is optional.', 'ok');
      } catch (error) {
        setStatus(error.message || 'The review could not be completed.', 'error');
      } finally {
        reviewBtn.disabled = false;
        reviewBtn.textContent = 'Run AI Review';
      }
    });

    outlookBtn.addEventListener('click', async () => {
      if (!currentPr) return;
      outlookBtn.disabled = true;
      outlookBtn.innerHTML = '<span class="spinner"></span>Creating draft…';
      try {
        await apiCall(`/reviews/${encodeURIComponent(currentPr.owner)}/${encodeURIComponent(currentPr.repo)}/${currentPr.number}/outlook-draft`, { method: 'POST' });
        setStatus('Outlook review draft created successfully.', 'ok');
      } catch (error) {
        setStatus(`${error.message || 'Outlook draft could not be created.'} The AI review above is still available.`, 'error');
      } finally {
        outlookBtn.disabled = false;
        outlookBtn.textContent = 'Create Outlook Draft';
      }
    });

    connectBtn.addEventListener('click', async () => {
      connectBtn.disabled = true;
      try {
        const data = await apiCall('/microsoft/connect', { method: 'POST' });
        if (!data.authorization_url) throw new Error('Microsoft authorization URL was not returned.');
        window.location.assign(data.authorization_url);
      } catch (error) {
        setStatus(error.message || 'Unable to start Microsoft connection.', 'error');
        connectBtn.disabled = false;
      }
    });
  </script>
</body>
</html>'''


def portfolio_page() -> HTMLResponse:
    return HTMLResponse(PORTFOLIO_UI)
