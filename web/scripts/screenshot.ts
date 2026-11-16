// Headless check of the running app: loads a URL in Chromium, waits until the summary (or an
// error) shows, prints console errors and saves a PNG. Uses the DevTools protocol directly.
// Usage: [KEYS=ArrowRight,...] [NO_FOCUSGROUP=1] node scripts/screenshot.ts <url> <out.png> [width] [height] [js to run first]
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const [url, out, w = '1500', h = '1000', script = ''] = process.argv.slice(2);
const port = 9333;
const browser = spawn(process.env.CHROMIUM ?? 'chromium', [
  '--headless=new', '--disable-gpu', '--no-first-run', `--remote-debugging-port=${port}`,
  `--window-size=${w},${h}`, '--user-data-dir=/tmp/coilcal-screenshot', 'about:blank',
], { stdio: 'ignore' });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

try {
  let target: { webSocketDebuggerUrl: string; type: string } | undefined;
  for (let i = 0; i < 50 && !target; i++) {
    await sleep(200);
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find((t: { type: string }) => t.type === 'page');
    } catch { /* not up yet */ }
  }
  if (!target) throw new Error('chromium did not start');
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r, { once: true }));
  let id = 0;
  const pending = new Map<number, (v: any) => void>();
  ws.addEventListener('message', (e) => {
    const msg = JSON.parse(String(e.data));
    if (msg.id) pending.get(msg.id)?.(msg.result);
    if (msg.method === 'Runtime.exceptionThrown') console.error('exception:', msg.params.exceptionDetails.exception?.description);
    if (msg.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(msg.params.type)) {
      console.error(`console.${msg.params.type}:`, msg.params.args.map((a: any) => a.value ?? a.description).join(' '));
    }
  });
  const send = (method: string, params = {}) =>
    new Promise<any>((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
  const evaluate = async (expression: string) =>
    (await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })).result?.value;

  await send('Runtime.enable');
  await send('Page.enable');
  if (process.env.NO_FOCUSGROUP) {
    // test the fallback: hide native focusgroup support before the app's scripts run
    const source = 'delete HTMLElement.prototype.focusGroup';
    await send('Page.addScriptToEvaluateOnNewDocument', { source });
  }
  await send('Page.navigate', { url });
  const ready = `document.querySelector('.summary:not(.stale)') ? 'ok'
    : document.querySelector('.status.error')?.textContent || ''`;
  let state = '';
  for (let i = 0; i < 100 && !state; i++, await sleep(200)) state = await evaluate(ready);
  if (script) {
    await evaluate(`(async () => { ${script} })()`); // allows await in the script
    await sleep(500); // let the edit's recompute start
    state = '';
    for (let i = 0; i < 100 && !state; i++, await sleep(200)) state = await evaluate(ready);
  }
  // real key presses (KEYS=ArrowRight,Home,...), e.g. to test keyboard navigation
  const codes: Record<string, number> = { ArrowLeft: 37, ArrowRight: 39, Home: 36, End: 35, Tab: 9 };
  for (const key of (process.env.KEYS ?? '').split(',').filter(Boolean)) {
    const k = { key, code: key, windowsVirtualKeyCode: codes[key] ?? 0 };
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', ...k });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', ...k });
    await sleep(100);
  }
  if (process.env.KEYS) {
    console.log('focused:', await evaluate(`document.activeElement?.textContent?.trim()`),
      '| selected:', await evaluate(`document.querySelector('[aria-selected=true]')?.textContent?.trim()`));
  }
  console.log('state:', state || 'timeout', '|', await evaluate(`document.querySelector('.status')?.textContent?.trim()`));
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(out, Buffer.from(shot.data, 'base64'));
  ws.close();
} finally {
  browser.kill();
}
