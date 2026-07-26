import assert from "node:assert/strict";
import test from "node:test";
import { resolvePackageInvocation } from "./package-command.mjs";

test("resolves npm-family launchers on Windows", () => {
  assert.deepEqual(
    resolvePackageInvocation("pnpm", ["pack", "--silent"], "win32", "cmd.exe"),
    {
      command: "cmd.exe",
      args: ["/d", "/s", "/c", "pnpm.cmd", "pack", "--silent"],
    },
  );
  assert.deepEqual(
    resolvePackageInvocation("npm", ["pack"], "win32", "C:\\Windows\\cmd.exe"),
    {
      command: "C:\\Windows\\cmd.exe",
      args: ["/d", "/s", "/c", "npm.cmd", "pack"],
    },
  );
});

test("preserves commands on non-Windows platforms", () => {
  assert.deepEqual(resolvePackageInvocation("pnpm", ["pack"], "linux"), {
    command: "pnpm",
    args: ["pack"],
  });
  assert.deepEqual(resolvePackageInvocation("node", ["--version"], "win32"), {
    command: "node",
    args: ["--version"],
  });
});
