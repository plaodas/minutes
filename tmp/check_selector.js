const { chromium } = require('playwright');
(async ()=>{
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('http://localhost:5173');
  await page.waitForTimeout(2000);
  const count = await page.evaluate(()=>document.querySelectorAll('[data-testid^="view-history-"]').length);
  console.log('count=',count);
  const html = await page.content();
  console.log('content length', html.length);
  await browser.close();
})();
