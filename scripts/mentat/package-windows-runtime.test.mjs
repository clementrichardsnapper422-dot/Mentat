import assert from "node:assert/strict";
import test from "node:test";
import { resolvePackageCommand } from "./package-command.mjs";

test("resolves npm-family launchers on Windows", () => {
  assert.equal(resolvePackageCommand("pnpm", "win32"), "pnpm.cmd");
  assert.equal(resolvePackageCommand("npm", "win32"), "npm.cmd");
});

test("preserves commands on non-Windows platforms", () => {
  assert.equal(resolvePackageCommand("pnpm", "linux"), "pnpm");
  assert.equal(resolvePackageCommand("node", "win32"), "node");
});
