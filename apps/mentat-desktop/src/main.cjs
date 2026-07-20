const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const APP_ID = 'com.mentat.desktop';
const DEFAULT_GATEWAY_PORT = 18789;
const DEFAULT_BROKER_PORT = 18890;
const GATEWAY_START_TIMEOUT_MS = 90_000;
const BROKER_START_TIMEOUT_MS = 30_000;
const POLL_INTERVAL_MS = 750;

let mainWindow = null;
let decisionWindow = null;
let decisionPollTimer = null;
let gatewayStartedByDesktop = false;
let stoppingGateway = false;

function getMentatInstallRoot() {
  const localAppData = process.env.LOCALAPPDATA || app.getPath('appData');
  return path.join(localAppData, 'Mentat');
}

function getMentatPaths() {
  const installRoot = getMentatInstallRoot();
  return {
    installRoot,
    configPath: path.join(installRoot, 'config', 'config.json'),
    commandPath: path.join(installRoot, 'bin', 'mentat.ps1'),
    outLogPath: path.join(installRoot, 'state', 'gateway.out.log'),
    errorLogPath: path.join(installRoot, 'state', 'gateway.error.log'),
    brokerOutLogPath: path.join(installRoot, 'state', 'broker.out.log'),
    brokerErrorLogPath: path.join(installRoot, 'state', 'broker.error.log'),
  };
}

function readMentatConfig() {
  const { configPath } = getMentatPaths();
  try {
    const raw = fs.readFileSync(configPath, 'utf8').replace(/^\uFEFF/, '');
    return JSON.parse(raw);
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      return null;
    }
    throw new Error(`Could not read Mentat configuration: ${error.message}`);
  }
}

function validPort(candidate, fallback) {
  const value = Number(candidate ?? fallback);
  return Number.isInteger(value) && value > 0 && value <= 65535 ? value : fallback;
}

function gatewayUrl(config) {
  return `http://127.0.0.1:${validPort(config?.gatewayPort, DEFAULT_GATEWAY_PORT)}/`;
}

function brokerUrl(config) {
  return `http://127.0.0.1:${validPort(config?.brokerPort, DEFAULT_BROKER_PORT)}`;
}

function runMentatCommand(args, { wait = false } = {}) {
  const { commandPath } = getMentatPaths();
  if (!fs.existsSync(commandPath)) {
    throw new Error('Mentat command is not installed. Run install.cmd from the Mentat repository first.');
  }

  const powershellArgs = [
    '-NoLogo',
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    commandPath,
    ...args,
  ];

  if (wait) {
    const result = spawnSync('powershell.exe', powershellArgs, {
      windowsHide: true,
      encoding: 'utf8',
      timeout: 180_000,
    });
    if (result.error) {
      throw result.error;
    }
    if (result.status !== 0) {
      const details = (result.stderr || result.stdout || '').trim();
      throw new Error(details || `mentat ${args.join(' ')} failed with exit code ${result.status}`);
    }
    return;
  }

  const child = spawn('powershell.exe', powershellArgs, {
    windowsHide: true,
    detached: true,
    stdio: 'ignore',
  });
  child.unref();
}

function probeUrl(url) {
  return new Promise((resolve) => {
    const request = http.get(url, (response) => {
      response.resume();
      resolve(response.statusCode >= 200 && response.statusCode < 500);
    });
    request.setTimeout(1500, () => {
      request.destroy();
      resolve(false);
    });
    request.once('error', () => resolve(false));
  });
}

async function waitForUrl(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probeUrl(url)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  return false;
}

function getJson(url) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { headers: { Accept: 'application/json' } }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => {
        body += chunk;
      });
      response.on('end', () => {
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(`HTTP ${response.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.setTimeout(2000, () => request.destroy(new Error('request timed out')));
    request.once('error', reject);
  });
}

function isAllowedLocalNavigation(candidate, expectedUrl) {
  try {
    const candidateUrl = new URL(candidate);
    const expected = new URL(expectedUrl);
    return (
      candidateUrl.protocol === expected.protocol &&
      candidateUrl.hostname === expected.hostname &&
      candidateUrl.port === expected.port
    );
  } catch {
    return false;
  }
}

function loadingPage(message) {
  const safeMessage = String(message).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="color-scheme" content="dark">
  <title>Mentat</title>
  <style>
    html, body { height: 100%; margin: 0; }
    body { display:grid; place-items:center; background:radial-gradient(circle at top,#20264a 0,#0d1020 58%,#080a12 100%); color:#f7f7ff; font-family:"Segoe UI",system-ui,sans-serif; }
    main { text-align:center; padding:32px; }
    .mark { width:84px; height:84px; margin:0 auto 24px; border-radius:24px; display:grid; place-items:center; font-size:44px; font-weight:800; background:linear-gradient(145deg,#8d7cff,#4d48cc); box-shadow:0 20px 70px rgba(105,88,255,.35); }
    h1 { margin:0 0 10px; font-size:30px; }
    p { margin:0; color:#bec3dc; font-size:15px; }
    .pulse { width:42px; height:4px; border-radius:99px; margin:22px auto 0; background:#8d7cff; animation:pulse 1.1s ease-in-out infinite alternate; }
    @keyframes pulse { from { opacity:.25; transform:scaleX(.55); } to { opacity:1; transform:scaleX(1); } }
  </style>
</head>
<body><main><div class="mark">M</div><h1>Mentat</h1><p>${safeMessage}</p><div class="pulse"></div></main></body>
</html>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function secureWindowOptions(overrides = {}) {
  return {
    backgroundColor: '#0d1020',
    autoHideMenuBar: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
    ...overrides,
  };
}

function createMainWindow() {
  const window = new BrowserWindow(secureWindowOptions({
    width: 1320,
    height: 860,
    minWidth: 900,
    minHeight: 620,
    show: false,
    title: 'Mentat',
  }));
  window.once('ready-to-show', () => window.show());
  window.on('closed', () => {
    mainWindow = null;
  });
  return window;
}

function configureLocalNavigation(window, allowedUrl) {
  window.webContents.setWindowOpenHandler(({ url: target }) => {
    if (!isAllowedLocalNavigation(target, allowedUrl)) {
      void shell.openExternal(target);
    }
    return { action: 'deny' };
  });
  window.webContents.removeAllListeners('will-navigate');
  window.webContents.on('will-navigate', (event, target) => {
    if (!isAllowedLocalNavigation(target, allowedUrl)) {
      event.preventDefault();
      void shell.openExternal(target);
    }
  });
}

async function openGatewayLogs() {
  const paths = getMentatPaths();
  const candidates = [
    paths.brokerErrorLogPath,
    paths.errorLogPath,
    paths.brokerOutLogPath,
    paths.outLogPath,
  ];
  const target = candidates.find((candidate) => fs.existsSync(candidate));
  if (!target) {
    await dialog.showMessageBox({
      type: 'info',
      title: 'Mentat logs',
      message: 'No Gateway or broker log file exists yet.',
    });
    return;
  }
  const error = await shell.openPath(target);
  if (error) {
    dialog.showErrorBox('Could not open logs', error);
  }
}

async function openDecisionCenter({ focus = true } = {}) {
  const config = readMentatConfig();
  if (!config) {
    return;
  }
  const base = brokerUrl(config);
  const url = `${base}/ui/decisions`;
  if (!(await probeUrl(`${base}/health`))) {
    await dialog.showMessageBox({
      type: 'warning',
      title: 'Mentat broker is not running',
      message: 'Start or restart Mentat before opening Compute Decisions.',
    });
    return;
  }
  if (decisionWindow && !decisionWindow.isDestroyed()) {
    if (focus) {
      decisionWindow.show();
      decisionWindow.focus();
    }
    return;
  }
  decisionWindow = new BrowserWindow(secureWindowOptions({
    width: 1040,
    height: 760,
    minWidth: 760,
    minHeight: 520,
    title: 'Mentat Compute Decisions',
    parent: mainWindow || undefined,
  }));
  configureLocalNavigation(decisionWindow, base);
  decisionWindow.on('closed', () => {
    decisionWindow = null;
  });
  await decisionWindow.loadURL(url);
  if (focus) {
    decisionWindow.show();
    decisionWindow.focus();
  }
}

function startDecisionPolling(config) {
  if (decisionPollTimer) {
    clearInterval(decisionPollTimer);
  }
  const base = brokerUrl(config);
  let lastPendingId = null;
  decisionPollTimer = setInterval(async () => {
    try {
      const data = await getJson(`${base}/v1/decisions?status=pending&limit=1`);
      const pending = Array.isArray(data.decisions) ? data.decisions[0] : null;
      if (!pending) {
        lastPendingId = null;
        return;
      }
      if (pending.id !== lastPendingId) {
        lastPendingId = pending.id;
        await openDecisionCenter({ focus: true });
        decisionWindow?.flashFrame(true);
      }
    } catch {
      // Broker startup and shutdown races are expected; the next poll retries.
    }
  }, 1500);
}

function stopGatewayStartedByDesktop() {
  if (!gatewayStartedByDesktop || stoppingGateway) {
    return;
  }
  stoppingGateway = true;
  try {
    runMentatCommand(['stop'], { wait: true });
  } catch {
    // The app is already quitting; failure is available in the normal logs.
  }
}

async function restartGateway() {
  if (!mainWindow) {
    return;
  }
  await mainWindow.loadURL(loadingPage('Restarting the local Gateway and broker…'));
  try {
    runMentatCommand(['stop'], { wait: true });
    runMentatCommand(['start']);
    gatewayStartedByDesktop = true;
    const config = readMentatConfig();
    const gateway = gatewayUrl(config);
    const broker = brokerUrl(config);
    if (!(await waitForUrl(`${broker}/health`, BROKER_START_TIMEOUT_MS))) {
      throw new Error('The local model broker did not become ready before the timeout.');
    }
    if (!(await waitForUrl(gateway, GATEWAY_START_TIMEOUT_MS))) {
      throw new Error('The local Gateway did not become ready before the timeout.');
    }
    await loadControlUi(gateway);
    startDecisionPolling(config);
  } catch (error) {
    await showStartupFailure(error);
  }
}

function installMenu() {
  const template = [
    {
      label: 'Mentat',
      submenu: [
        { label: 'Compute Decisions', accelerator: 'Ctrl+Shift+D', click: () => void openDecisionCenter() },
        { label: 'Reload', accelerator: 'Ctrl+R', click: () => mainWindow?.reload() },
        { label: 'Restart Gateway and Broker', click: () => void restartGateway() },
        { label: 'Open Logs', click: () => void openGatewayLogs() },
        { type: 'separator' },
        { role: 'quit', label: 'Quit Mentat' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        { role: 'toggleDevTools' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function loadControlUi(url) {
  if (!mainWindow) {
    return;
  }
  configureLocalNavigation(mainWindow, url);
  await mainWindow.loadURL(url);
}

async function showStartupFailure(error) {
  const result = await dialog.showMessageBox({
    type: 'error',
    title: 'Mentat could not start',
    message: 'The Mentat desktop app could not reach the local Gateway and model broker.',
    detail: error?.message || String(error),
    buttons: ['Retry', 'Open Logs', 'Quit'],
    defaultId: 0,
    cancelId: 2,
  });

  if (result.response === 0) {
    await bootstrapMentat();
  } else if (result.response === 1) {
    await openGatewayLogs();
    await showStartupFailure(error);
  } else {
    app.quit();
  }
}

async function bootstrapMentat() {
  if (!mainWindow) {
    return;
  }
  await mainWindow.loadURL(loadingPage('Starting the local Gateway and model broker…'));

  let config;
  try {
    config = readMentatConfig();
  } catch (error) {
    await showStartupFailure(error);
    return;
  }

  if (!config) {
    await dialog.showMessageBox({
      type: 'warning',
      title: 'Mentat setup required',
      message: 'Mentat has not been configured yet.',
      detail: 'Open PowerShell, run “mentat setup”, then launch Mentat again.',
      buttons: ['Close'],
    });
    app.quit();
    return;
  }

  const gateway = gatewayUrl(config);
  const broker = brokerUrl(config);
  const gatewayReady = await probeUrl(gateway);
  const brokerReady = await probeUrl(`${broker}/health`);

  if (!gatewayReady || !brokerReady) {
    try {
      if (gatewayReady && !brokerReady) {
        runMentatCommand(['restart']);
      } else {
        runMentatCommand(['start']);
      }
      gatewayStartedByDesktop = true;
    } catch (error) {
      await showStartupFailure(error);
      return;
    }
  }

  if (!(await waitForUrl(`${broker}/health`, BROKER_START_TIMEOUT_MS))) {
    await showStartupFailure(new Error(`Timed out waiting for ${broker}/health`));
    return;
  }
  if (!(await waitForUrl(gateway, GATEWAY_START_TIMEOUT_MS))) {
    await showStartupFailure(new Error(`Timed out waiting for ${gateway}`));
    return;
  }

  try {
    await loadControlUi(gateway);
    startDecisionPolling(config);
  } catch (error) {
    await showStartupFailure(error);
  }
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(async () => {
    if (process.platform !== 'win32') {
      dialog.showErrorBox('Unsupported platform', 'This Mentat desktop build currently targets Windows.');
      app.quit();
      return;
    }

    app.setAppUserModelId(APP_ID);
    installMenu();
    mainWindow = createMainWindow();
    await bootstrapMentat();
  });

  app.on('window-all-closed', () => {
    app.quit();
  });

  app.on('before-quit', () => {
    if (decisionPollTimer) {
      clearInterval(decisionPollTimer);
      decisionPollTimer = null;
    }
    stopGatewayStartedByDesktop();
  });
}
