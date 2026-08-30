const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const requests = [];
  page.on('request', r => {
    requests.push({ id: r._requestId || r.url(), url: r.url(), method: r.method(), type: r.resourceType(), timestamp: Date.now(), status: null, statusText: null });
  });
  page.on('response', async resp => {
    try {
      const url = resp.url();
      const status = resp.status();
      const entry = requests.find(e => e.url === url && e.status === null);
      if (entry) { entry.status = status; entry.statusText = resp.statusText(); }
      else requests.push({ url, method: resp.request().method(), type: resp.request().resourceType(), timestamp: Date.now(), status, statusText: resp.statusText() });
      if (status >= 400) console.log('BAD_RESP', status, url);
    } catch (e) { console.log('RESP_ERR', e.toString()); }
  });
  page.on('requestfailed', req => {
    const url = req.url();
    const failure = req.failure() || {};
    console.log('REQFAILED', req.method(), url, failure.errorText || '');
    requests.push({ url, method: req.method(), type: req.resourceType(), timestamp: Date.now(), status: 'FAILED', statusText: failure.errorText || '' });
  });
  page.on('console', m => console.log('CONSOLE', m.type(), m.text()));
  page.on('pageerror', e => console.log('PAGEERROR', e.toString()));

  const target = 'http://localhost:8080/#minutes=fdc34395-9760-43e7-a681-ca24abec4710';
  console.log('NAV', target);
  try {
    await page.goto(target, { waitUntil: 'networkidle', timeout: 30000 });
  } catch (e) {
    console.log('GOTO_ERROR', e.toString());
  }

  // wait a bit for SW / dynamic loads
  await page.waitForTimeout(2000);

  const outPath = 'frontend/dist/network_log.json';
  fs.writeFileSync(outPath, JSON.stringify(requests, null, 2));
  console.log('WROTE', outPath, 'entries:', requests.length);

  try { await page.screenshot({ path: 'frontend/dist/debug_full.png', fullPage: true }); console.log('SHOT saved'); } catch (e) { console.log('SHOT_ERR', e.toString()); }

  await browser.close();
})();
