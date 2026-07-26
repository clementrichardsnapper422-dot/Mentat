const { spawn } = require('node:child_process');
const fs = require('node:fs');

const MAX_CAPTURE_CHARS = 64 * 1024;

function appendOutput(current, chunk) {
  return (current + String(chunk)).slice(-MAX_CAPTURE_CHARS);
}

function runNoSpendCommand(commandPath, options = {}) {
  const spawnProcess = options.spawnProcess || spawn;
  const timeoutMs = options.timeoutMs ?? 300_000;
  const baseEnv = options.env || process.env;

  return new Promise((resolve) => {
    let child;
    try {
      child = spawnProcess(
        'powershell.exe',
        [
          '-NoLogo',
          '-NoProfile',
          '-ExecutionPolicy',
          'Bypass',
          '-File',
          commandPath,
          'test',
          'no-spend',
        ],
        {
          windowsHide: true,
          stdio: ['ignore', 'pipe', 'pipe'],
          env: {
            ...baseEnv,
            VAST_API_KEY: '',
            VAST_TEMPLATE_HASH: '',
            MENTAT_BROKER_ADMIN_TOKEN: '',
            MENTAT_BROKER_CLIENT_TOKEN: '',
          },
        },
      );
    } catch (error) {
      resolve({ status: null, signal: null, stdout: '', stderr: '', error, timedOut: false });
      return;
    }

    let stdout = '';
    let stderr = '';
    let settled = false;
    let timedOut = false;

    const finish = (status, signal, error = null) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve({ status, signal, stdout, stderr, error, timedOut });
    };

    child.stdout?.on('data', (chunk) => {
      stdout = appendOutput(stdout, chunk);
    });
    child.stderr?.on('data', (chunk) => {
      stderr = appendOutput(stderr, chunk);
    });
    child.once('error', (error) => {
      finish(null, null, error);
    });
    child.once('close', (status, signal) => {
      finish(status, signal);
    });

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
      finish(null, child.signalCode, new Error(`No-spend diagnostics timed out after ${timeoutMs}ms.`));
    }, timeoutMs);
    timer.unref?.();
  });
}

function readNoSpendReport(reportPath, options = {}) {
  const readFile = options.readFile || fs.readFileSync;
  const raw = readFile(reportPath, 'utf8').replace(/^\uFEFF/, '');
  const report = JSON.parse(raw);
  if (!report || typeof report !== 'object' || Array.isArray(report)) {
    throw new Error('The no-spend report is not a JSON object.');
  }
  return report;
}

function evaluateNoSpendResult(result, report) {
  return result.status === 0
    && report?.passed === true
    && report?.paid_compute_used === false;
}

async function runNoSpendDiagnostic(commandPath, reportPath, options = {}) {
  const result = await runNoSpendCommand(commandPath, options);
  let report = null;
  let reportError = null;
  try {
    report = readNoSpendReport(reportPath, options);
  } catch (error) {
    reportError = error;
  }
  return {
    result,
    report,
    reportError,
    passed: evaluateNoSpendResult(result, report),
  };
}

module.exports = {
  evaluateNoSpendResult,
  readNoSpendReport,
  runNoSpendCommand,
  runNoSpendDiagnostic,
};
