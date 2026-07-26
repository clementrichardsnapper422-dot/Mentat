const path = require('node:path');
const { runNoSpendDiagnostic } = require('./no-spend-command.cjs');

function installRoot(env = process.env) {
  if (!env.LOCALAPPDATA) {
    throw new Error('LOCALAPPDATA is required for installed Mentat diagnostics.');
  }
  return path.join(env.LOCALAPPDATA, 'Mentat');
}

async function runNoSpendCli(options = {}) {
  const root = options.installRoot || installRoot(options.env);
  const commandPath = path.join(root, 'bin', 'mentat.ps1');
  const reportPath = path.join(root, 'state', 'no-spend-acceptance.json');
  const runDiagnostic = options.runDiagnostic || runNoSpendDiagnostic;
  const diagnostic = await runDiagnostic(commandPath, reportPath);
  const summary = {
    passed: diagnostic.passed,
    paid_compute_used: diagnostic.report?.paid_compute_used ?? null,
    report: reportPath,
    process_status: diagnostic.result.status,
    process_error: diagnostic.result.error?.message || null,
    report_error: diagnostic.reportError?.message || null,
  };
  (options.output || process.stdout).write(`${JSON.stringify(summary)}\n`);
  return diagnostic.passed ? 0 : 1;
}

if (require.main === module) {
  runNoSpendCli()
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error) => {
      process.stderr.write(`${error.stack || error}\n`);
      process.exitCode = 1;
    });
}

module.exports = { installRoot, runNoSpendCli };
