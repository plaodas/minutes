const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  page.on('console', msg => console.log('CONSOLE', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('PAGEERROR', err.toString()));
  page.on('requestfailed', req => {
    const failure = req.failure();
    console.log('REQFAILED', req.method(), req.url(), failure && failure.errorText ? failure.errorText : '');
  });
  page.on('response', resp => {
    if (resp.status() >= 400) console.log('RESP', resp.status(), resp.url());
  });

  const target = 'http://localhost:8080/#minutes=fdc34395-9760-43e7-a681-ca24abec4710';
  console.log('NAVIGATING', target);
  try {
    await page.goto(target, { waitUntil: 'networkidle', timeout: 30000 });
  } catch (e) {
    console.log('GOTO_ERROR', e.toString());
  }

  try {
    await page.screenshot({ path: 'frontend/dist/debug_screenshot.png', fullPage: true });
    console.log('SCREENSHOT_SAVED frontend/dist/debug_screenshot.png');
  } catch (e) {
    console.log('SCREENSHOT_ERROR', e.toString());
  }

  await browser.close();
  console.log('DONE');
})();
