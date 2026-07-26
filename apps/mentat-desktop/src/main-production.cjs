const electron = require('electron');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { runNoSpendDiagnostic } = require('./no-spend-command.cjs');
const { runNoSpendCli } = require('./no-spend-cli.cjs');

let noSpendRunInProgress = false;
let noSpendMenuItem = null;

function installRoot() {
  const localAppData = process.env.LOCALAPPDATA || electron.app.getPath('appData');
  return path.join(localAppData, 'Mentat');
}

function noSpendReportPath() {
  return path.join(installRoot(), 'state', 'no-spend-acceptance.json');
}

function brokerPort() {
  try {
    const configPath = path.join(installRoot(), 'config', 'config.json');
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8').replace(/^\uFEFF/, ''));
    const value = Number(config.brokerPort || 18890);
    return Number.isInteger(value) && value > 0 && value <= 65535 ? value : 18890;
  } catch {
    return 18890;
  }
}

function adminToken() {
  try {
    return fs.readFileSync(path.join(installRoot(), 'state', 'broker-admin.token'), 'utf8').trim();
  } catch {
    return '';
  }
}

function isBrokerUrl(value) {
  try {
    const candidate = value instanceof URL ? value : new URL(String(value));
    return candidate.protocol === 'http:'
      && candidate.hostname === '127.0.0.1'
      && Number(candidate.port) === brokerPort();
  } catch {
    return false;
  }
}

async function runNoSpendAcceptance() {
  const commandPath = path.join(installRoot(), 'bin', 'mentat.ps1');
  if (!fs.existsSync(commandPath)) {
    await electron.dialog.showMessageBox({
      type: 'error',
      title: 'Mentat diagnostics',
      message: 'The installed Mentat command was not found.',
      detail: 'Run install.cmd from the Mentat repository to repair the installation.',
    });
    return;
  }

  const confirmation = await electron.dialog.showMessageBox({
    type: 'info',
    title: 'Run no-spend diagnostics',
    message: 'Run Mentat’s isolated no-spend acceptance test?',
    detail: 'This uses local fake Vast and model services. It does not read your saved Vast key or start paid compute.',
    buttons: ['Run test', 'Cancel'],
    defaultId: 0,
    cancelId: 1,
    noLink: true,
  });
  if (confirmation.response !== 0) {
    return;
  }

  if (noSpendRunInProgress) {
    return;
  }
  noSpendRunInProgress = true;
  if (noSpendMenuItem) {
    noSpendMenuItem.enabled = false;
  }

  try {
    const diagnostic = await runNoSpendDiagnostic(commandPath, noSpendReportPath());
    const { passed, report, result } = diagnostic;
    const checks = report && Array.isArray(report.checks) ? report.checks : [];
    const passedChecks = checks.filter((item) => item && item.status === 'passed').length;
    const failedChecks = checks.filter((item) => item && item.status === 'failed');

    if (passed) {
      await electron.dialog.showMessageBox({
        type: 'info',
        title: 'Mentat diagnostics passed',
        message: `No-spend acceptance passed (${passedChecks}/${checks.length} checks).`,
        detail: `Paid compute used: no\nReport: ${noSpendReportPath()}`,
        buttons: ['OK', 'Open report'],
        defaultId: 0,
        noLink: true,
      }).then(async ({ response }) => {
        if (response === 1) {
          const error = await electron.shell.openPath(noSpendReportPath());
          if (error) {
            electron.dialog.showErrorBox('Could not open report', error);
          }
        }
      });
      return;
    }

    const commandOutput = String(result.stderr || result.stdout || '').trim().slice(-3000);
    const failureDetail = failedChecks.length
      ? failedChecks.map((item) => `${item.name}: ${item.error || 'failed'}`).join('\n')
      : commandOutput || result.error?.message || 'The diagnostic process did not produce a valid passing report.';
    await electron.dialog.showMessageBox({
      type: 'error',
      title: 'Mentat diagnostics failed',
      message: 'No-spend acceptance did not pass.',
      detail: `${failureDetail}\n\nReport: ${noSpendReportPath()}`,
    });
  } finally {
    noSpendRunInProgress = false;
    if (noSpendMenuItem) {
      noSpendMenuItem.enabled = true;
    }
  }
}

const originalBuildFromTemplate = electron.Menu.buildFromTemplate.bind(electron.Menu);
electron.Menu.buildFromTemplate = function buildMentatProductionMenu(template) {
  const actualTemplate = Array.isArray(template) ? template.map((item) => ({ ...item })) : template;
  if (Array.isArray(actualTemplate)) {
    let target = actualTemplate.find((item) => item && item.label === 'Mentat');
    if (!target) {
      target = { label: 'Diagnostics', submenu: [] };
      actualTemplate.push(target);
    }
    const submenu = Array.isArray(target.submenu) ? [...target.submenu] : [];
    submenu.push(
      { type: 'separator' },
      {
        id: 'mentat-no-spend-diagnostics',
        label: 'Run No-Spend Diagnostics…',
        accelerator: 'CmdOrCtrl+Shift+D',
        enabled: !noSpendRunInProgress,
        click: () => { void runNoSpendAcceptance(); },
      },
    );
    target.submenu = submenu;
  }
  const menu = originalBuildFromTemplate(actualTemplate);
  noSpendMenuItem = menu.getMenuItemById('mentat-no-spend-diagnostics') || noSpendMenuItem;
  return menu;
};

const originalGet = http.get;
http.get = function authenticatedLocalGet(input, options, callback) {
  let actualOptions = options;
  let actualCallback = callback;
  if (typeof options === 'function') {
    actualCallback = options;
    actualOptions = undefined;
  }
  const token = adminToken();
  if (token && isBrokerUrl(input)) {
    actualOptions = {
      ...(actualOptions || {}),
      headers: {
        ...((actualOptions && actualOptions.headers) || {}),
        Authorization: `Bearer ${token}`,
      },
    };
  }
  return originalGet.call(http, input, actualOptions, actualCallback);
};

const originalLoadURL = electron.BrowserWindow.prototype.loadURL;
electron.BrowserWindow.prototype.loadURL = function authenticatedLocalLoadURL(target, options) {
  const token = adminToken();
  let actualOptions = options;
  if (token && isBrokerUrl(target)) {
    try {
      const candidate = new URL(target);
      if (candidate.pathname === '/ui/decisions') {
        const existing = actualOptions && actualOptions.extraHeaders
          ? String(actualOptions.extraHeaders).replace(/\r?\n$/, '') + '\r\n'
          : '';
        actualOptions = {
          ...(actualOptions || {}),
          extraHeaders: `${existing}Authorization: Bearer ${token}\r\n`,
        };
      }
    } catch {
      // The original loadURL reports malformed URLs.
    }
  }
  return originalLoadURL.call(this, target, actualOptions);
};

async function runNonInteractiveDiagnostics() {
  exitNonInteractiveDiagnostics(await runNoSpendCli());
}

function exitNonInteractiveDiagnostics(code) {
  setTimeout(() => process.exit(code), 1000);
  electron.app.exit(code);
}

if (
  process.argv.includes('--diagnostics-no-spend')
  || electron.app.commandLine.hasSwitch('diagnostics-no-spend')
  || process.env.MENTAT_DIAGNOSTICS_NO_SPEND === '1'
) {
  runNonInteractiveDiagnostics().catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    exitNonInteractiveDiagnostics(1);
  });
} else {
  require('./main.cjs');
}
