const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const test = require('node:test');

const { runNoSpendCommand } = require('../src/no-spend-command.cjs');

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
