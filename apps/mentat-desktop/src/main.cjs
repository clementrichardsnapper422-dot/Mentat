const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const APP_ID = 'com.mentat.desktop';
const DEFAULT_GATEWAY_PORT = 18789;
const GATEWAY_START_TIMEOUT_MS = 90_000;
const GATEWAY_POLL_INTERVAL_MS = 750;

let mainWindow = null;
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

function gatewayPortFromConfig(config) {
  const candidate = Number(config?.gatewayPort ?? DEFAULT_GATEWAY_PORT);
  return Number.isInteger(candidate) && candidate > 0 && candidate <= 65535
    ? candidate
    : DEFAULT_GATEWAY_PORT;
}

function gatewayUrl(config) {
  return `http://127.0.0.1:${gatewayPortFromConfig(config)}/`;
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
      timeout: 45_000,
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

function probeGateway(url) {
  return new Promise((resolve) => {
    const request = http.get(url, (response) => {
      response.resume();
      resolve(true);
    });
    request.setTimeout(1500, () => {
      request.destroy();
      resolve(false);
    });
    request.once('error', () => resolve(false));
  });
}

async function waitForGateway(url) {
  const deadline = Date.now() + GATEWAY_START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await probeGateway(url)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, GATEWAY_POLL_INTERVAL_MS));
  }
  return false;
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
    body {
      display: grid;
      place-items: center;
      background: radial-gradient(circle at top, #20264a 0, #0d1020 58%, #080a12 100%);
      color: #f7f7ff;
      font-family: "Segoe UI", system-ui, sans-serif;
    }
    main { text-align: center; padding: 32px; }
    .mark {
      width: 84px;
      height: 84px;
      margin: 0 auto 24px;
      border-radius: 24px;
      display: grid;
      place-items: center;
      font-size: 44px;
      font-weight: 800;
      background: linear-gradient(145deg, #8d7cff, #4d48cc);
      box-shadow: 0 20px 70px rgba(105, 88, 255, 0.35);
    }
    h1 { margin: 0 0 10px; font-size: 30px; }
    p { margin: 0; color: #bec3dc; font-size: 15px; }
    .pulse {
      width: 42px;
      height: 4px;
      border-radius: 99px;
      margin: 22px auto 0;
      background: #8d7cff;
      animation: pulse 1.1s ease-in-out infinite alternate;
    }
    @keyframes pulse { from { opacity: .25; transform: scaleX(.55); } to { opacity: 1; transform: scaleX(1); } }
  </style>
</head>
<body>
  <main>
    <div class="mark">M</div>
    <h1>Mentat</h1>
    <p>${safeMessage}</p>
    <div class="pulse"></div>
  </main>
</body>
</html>`;

  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function createMainWindow() {
  const window = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 900,
    minHeight: 620,
    show: false,
    title: 'Mentat',
    backgroundColor: '#0d1020',
    autoHideMenuBar: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });

  window.once('ready-to-show', () => window.show());
  window.on('closed', () => {
    mainWindow = null;
  });

  return window;
}

async function openGatewayLogs() {
  const paths = getMentatPaths();
  const target = fs.existsSync(paths.errorLogPath) ? paths.errorLogPath : paths.outLogPath;
  if (!fs.existsSync(target)) {
    await dialog.showMessageBox({
      type: 'info',
      title: 'Mentat logs',
      message: 'No Gateway log file exists yet.',
    });
    return;
  }
  const error = await shell.openPath(target);
  if (error) {
    dialog.showErrorBox('Could not open logs', error);
  }
}

function stopGatewayStartedByDesktop() {
  if (!gatewayStartedByDesktop || stoppingGateway) {
    return;
  }
  stoppingGateway = true;
  try {
    runMentatCommand(['stop'], { wait: true });
  } catch {
    // The app is already quitting; failure to stop is surfaced in the normal Mentat logs.
  }
}

async function restartGateway() {
  if (!mainWindow) {
    return;
  }
  await mainWindow.loadURL(loadingPage('Restarting the local Gateway…'));
  try {
    runMentatCommand(['stop'], { wait: true });
    runMentatCommand(['start']);
    gatewayStartedByDesktop = true;
    const config = readMentatConfig();
    const url = gatewayUrl(config);
    if (!(await waitForGateway(url))) {
      throw new Error('The local Gateway did not become ready before the timeout.');
    }
    await loadControlUi(url);
  } catch (error) {
    await showStartupFailure(error);
  }
}

function installMenu() {
  const template = [
    {
      label: 'Mentat',
      submenu: [
        { label: 'Reload', accelerator: 'Ctrl+R', click: () => mainWindow?.reload() },
        { label: 'Restart Gateway', click: () => void restartGateway() },
        { label: 'Open Gateway Logs', click: () => void openGatewayLogs() },
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

  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    if (!isAllowedLocalNavigation(target, url)) {
      void shell.openExternal(target);
    }
    return { action: 'deny' };
  });

  mainWindow.webContents.removeAllListeners('will-navigate');
  mainWindow.webContents.on('will-navigate', (event, target) => {
    if (!isAllowedLocalNavigation(target, url)) {
      event.preventDefault();
      void shell.openExternal(target);
    }
  });

  await mainWindow.loadURL(url);
}

async function showStartupFailure(error) {
  const result = await dialog.showMessageBox({
    type: 'error',
    title: 'Mentat could not start',
    message: 'The Mentat desktop app could not reach the local Gateway.',
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

  await mainWindow.loadURL(loadingPage('Starting the local Gateway…'));

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

  const url = gatewayUrl(config);
  if (!(await probeGateway(url))) {
    try {
      runMentatCommand(['start']);
      gatewayStartedByDesktop = true;
    } catch (error) {
      await showStartupFailure(error);
      return;
    }
  }

  if (!(await waitForGateway(url))) {
    await showStartupFailure(new Error(`Timed out waiting for ${url}`));
    return;
  }

  try {
    await loadControlUi(url);
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
    stopGatewayStartedByDesktop();
  });
}
