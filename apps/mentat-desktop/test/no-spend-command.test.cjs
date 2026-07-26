const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const path = require('node:path');
const { PassThrough } = require('node:stream');
const test = require('node:test');

const {
  evaluateNoSpendResult,
  readNoSpendReport,
  runNoSpendCommand,
  runNoSpendDiagnostic,
} = require('../src/no-spend-command.cjs');
const { installRoot, runNoSpendCli } = require('../src/no-spend-cli.cjs');

function fakeChild() {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.signalCode = null;
  child.kill = () => {
    child.signalCode = 'SIGTERM';
    return true;
  };
  return child;
}

test('runs diagnostics asynchronously with credentials cleared', async () => {
  const child = fakeChild();
  let invocation = null;
  const resultPromise = runNoSpendCommand('C:\\Mentat\\bin\\mentat.ps1', {
    env: { KEEP_ME: 'yes', VAST_API_KEY: 'secret' },
    spawnProcess(command, args, options) {
      invocation = { command, args, options };
      return child;
    },
  });

  assert.equal(invocation.command, 'powershell.exe');
  assert.deepEqual(invocation.args.slice(-3), ['C:\\Mentat\\bin\\mentat.ps1', 'test', 'no-spend']);
  assert.equal(invocation.options.env.KEEP_ME, 'yes');
  assert.equal(invocation.options.env.VAST_API_KEY, '');
  assert.equal(invocation.options.env.MENTAT_BROKER_ADMIN_TOKEN, '');

  child.stdout.write('passed');
  child.stdout.end();
  child.emit('close', 0, null);
  const result = await resultPromise;
  assert.equal(result.status, 0);
  assert.equal(result.stdout, 'passed');
  assert.equal(result.timedOut, false);
});

test('terminates and reports a timed-out diagnostic process', async () => {
  const child = fakeChild();
  let killed = false;
  child.kill = () => {
    killed = true;
    child.signalCode = 'SIGTERM';
    return true;
  };

  const result = await runNoSpendCommand('mentat.ps1', {
    timeoutMs: 5,
    spawnProcess: () => child,
  });
  assert.equal(killed, true);
  assert.equal(result.status, null);
  assert.equal(result.timedOut, true);
  assert.match(result.error.message, /timed out/);
});

test('accepts only a successful process and explicit no-spend report', () => {
  assert.equal(
    evaluateNoSpendResult(
      { status: 0 },
      { passed: true, paid_compute_used: false },
    ),
    true,
  );
  assert.equal(
    evaluateNoSpendResult(
      { status: 0 },
      { passed: true, paid_compute_used: true },
    ),
    false,
  );
  assert.equal(
    evaluateNoSpendResult(
      { status: 1 },
      { passed: true, paid_compute_used: false },
    ),
    false,
  );
});

test('reads a BOM-prefixed no-spend report and rejects arrays', () => {
  const report = readNoSpendReport('report.json', {
    readFile: () => '\uFEFF{"passed":true,"paid_compute_used":false}',
  });
  assert.equal(report.passed, true);
  assert.throws(
    () => readNoSpendReport('report.json', { readFile: () => '[]' }),
    /not a JSON object/,
  );
});

test('runs and evaluates the installed diagnostic in one operation', async () => {
  const child = fakeChild();
  const promise = runNoSpendDiagnostic('mentat.ps1', 'report.json', {
    spawnProcess: () => child,
    readFile: () => '{"passed":true,"paid_compute_used":false}',
  });
  child.emit('close', 0, null);
  const diagnostic = await promise;
  assert.equal(diagnostic.passed, true);
  assert.equal(diagnostic.reportError, null);
});

test('runs the packaged desktop CLI against the installed command', async () => {
  const root = 'C:\\Users\\test\\AppData\\Local\\Mentat';
  let invocation = null;
  let output = '';
  const code = await runNoSpendCli({
    installRoot: root,
    output: { write: (value) => { output += value; } },
    runDiagnostic: async (commandPath, reportPath) => {
      invocation = { commandPath, reportPath };
      return {
        passed: true,
        report: { paid_compute_used: false },
        reportError: null,
        result: { status: 0, error: null },
      };
    },
  });

  assert.equal(code, 0);
  assert.deepEqual(invocation, {
    commandPath: path.join(root, 'bin', 'mentat.ps1'),
    reportPath: path.join(root, 'state', 'no-spend-acceptance.json'),
  });
  assert.deepEqual(JSON.parse(output), {
    passed: true,
    paid_compute_used: false,
    report: path.join(root, 'state', 'no-spend-acceptance.json'),
    process_status: 0,
    process_error: null,
    report_error: null,
  });
});

test('requires the installed Windows data root', () => {
  assert.throws(() => installRoot({}), /LOCALAPPDATA is required/);
});
