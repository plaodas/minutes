const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const target = 'http://localhost:8080/#minutes=fdc34395-9760-43e7-a681-ca24abec4710';
  await page.goto(target, { waitUntil: 'networkidle' });
  const rootHtml = await page.$eval('#root', el => el.innerHTML);
  const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const rootBg = await page.evaluate(() => {
    const el = document.getElementById('root');
    return el ? getComputedStyle(el).backgroundColor : null;
  });
  console.log('BODY_BG', bodyBg);
  console.log('ROOT_BG', rootBg);
  console.log('ROOT_HTML_SNIPPET', rootHtml.slice(0, 1000));
  await page.screenshot({ path: 'frontend/frontend/dist/debug_dom.png', fullPage: true });
  console.log('SHOT debug_dom.png saved');
  await browser.close();
})();
