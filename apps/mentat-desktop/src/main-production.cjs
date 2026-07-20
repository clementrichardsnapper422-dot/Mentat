const electron = require('electron');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

function installRoot() {
  const localAppData = process.env.LOCALAPPDATA || electron.app.getPath('appData');
  return path.join(localAppData, 'Mentat');
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

require('./main.cjs');
