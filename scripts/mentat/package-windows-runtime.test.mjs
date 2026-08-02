import assert from "node:assert/strict";
import test from "node:test";
import { resolvePackageInvocation } from "./package-command.mjs";
import { endpointConfigPaths } from "./runtime-package-layout.mjs";

void test("resolves npm-family launchers on Windows", () => {
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

void test("preserves commands on non-Windows platforms", () => {
  assert.deepEqual(resolvePackageInvocation("pnpm", ["pack"], "linux"), {
    command: "pnpm",
    args: ["pack"],
  });
  assert.deepEqual(resolvePackageInvocation("node", ["--version"], "win32"), {
    command: "node",
    args: ["--version"],
  });
});

void test("derives unique portable endpoint configs from the model registry", () => {
  assert.deepEqual(
    endpointConfigPaths({
      models: [
        { id: "primary", endpoint_config: "infrastructure/vast/a/endpoint.json" },
        { id: "fallback", endpoint_config: "infrastructure\\vast\\b\\endpoint.json" },
        { id: "duplicate", endpoint_config: "infrastructure/vast/a/endpoint.json" },
      ],
    }),
    [
      "infrastructure/vast/a/endpoint.json",
      "infrastructure/vast/b/endpoint.json",
    ],
  );
});

void test("rejects missing or escaping endpoint configs", () => {
  assert.throws(
    () => endpointConfigPaths({ models: [{ id: "missing" }] }),
    /missing endpoint_config/,
  );
  assert.throws(
    () =>
      endpointConfigPaths({
        models: [{ id: "escape", endpoint_config: "../secret.json" }],
      }),
    /must stay inside the runtime/,
  );
  assert.throws(
    () =>
      endpointConfigPaths({
        models: [{ id: "absolute", endpoint_config: "C:\\secret.json" }],
      }),
    /must stay inside the runtime/,
  );
});
