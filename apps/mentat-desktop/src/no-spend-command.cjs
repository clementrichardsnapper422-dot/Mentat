const { spawn } = require('node:child_process');

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

module.exports = { runNoSpendCommand };
