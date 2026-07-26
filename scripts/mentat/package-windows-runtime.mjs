#!/usr/bin/env node

import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const ARTIFACT_DIR = path.join(ROOT_DIR, ".artifacts", "mentat-windows-runtime");
const STAGING_DIR = path.join(ARTIFACT_DIR, "staging");
const PAYLOAD_DIR = path.join(ARTIFACT_DIR, "payload");
const TARBALL_DIR = path.join(ARTIFACT_DIR, "package");
const TARBALL_NAME = "openclaw.tgz";

function run(command, args, cwd = ROOT_DIR) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: process.env,
      stdio: "inherit",
      windowsHide: true,
    });
    child.once("error", reject);
    child.once("close", (code, signal) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} exited with ${signal || code}.`));
    });
  });
}

async function copyDirectory(source, destination) {
  await fs.cp(source, destination, { recursive: true, force: true });
}

async function assertFiles(root, relativePaths) {
  for (const relativePath of relativePaths) {
    const target = path.join(root, relativePath);
    const stat = await fs.stat(target).catch(() => null);
    if (!stat?.isFile()) {
      throw new Error(`Packaged runtime component is missing: ${relativePath}`);
    }
  }
}

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, "utf8"));
}

async function gitCommit() {
  const output = [];
  await new Promise((resolve, reject) => {
    const command = process.platform === "win32" ? "git.exe" : "git";
    const child = spawn(command, ["rev-parse", "HEAD"], {
      cwd: ROOT_DIR,
      stdio: ["ignore", "pipe", "inherit"],
      windowsHide: true,
    });
    child.stdout.on("data", (chunk) => output.push(chunk));
    child.once("error", reject);
    child.once("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`git rev-parse exited with ${code}.`));
    });
  });
  return Buffer.concat(output).toString("utf8").trim();
}

async function main() {
  if (process.platform !== "win32") {
    throw new Error("The Mentat runtime must be packaged on Windows.");
  }
  if (!process.env.npm_execpath) {
    throw new Error("npm_execpath is missing. Run this script through npm.");
  }

  await fs.rm(STAGING_DIR, { recursive: true, force: true });
  await fs.rm(TARBALL_DIR, { recursive: true, force: true });
  await fs.mkdir(STAGING_DIR, { recursive: true });
  await fs.mkdir(TARBALL_DIR, { recursive: true });

  await run(process.execPath, [
    path.join(ROOT_DIR, "scripts", "package-openclaw-for-docker.mjs"),
    "--allow-unreleased-changelog",
    "--output-dir",
    TARBALL_DIR,
    "--output-name",
    TARBALL_NAME,
  ]);

  const openClawPrefix = path.join(STAGING_DIR, "openclaw");
  await run(process.execPath, [
    process.env.npm_execpath,
    "install",
    "--global",
    "--prefix",
    openClawPrefix,
    "--no-audit",
    "--no-fund",
    path.join(TARBALL_DIR, TARBALL_NAME),
  ]);

  await fs.mkdir(path.join(STAGING_DIR, "node"), { recursive: true });
  await fs.copyFile(process.execPath, path.join(STAGING_DIR, "node", "node.exe"));
  await copyDirectory(
    path.join(ROOT_DIR, "scripts", "mentat"),
    path.join(STAGING_DIR, "scripts", "mentat"),
  );
  await copyDirectory(
    path.join(ROOT_DIR, "services", "model-broker", "mentat_broker"),
    path.join(STAGING_DIR, "services", "model-broker", "mentat_broker"),
  );
  await fs.copyFile(
    path.join(ROOT_DIR, "services", "model-broker", "pyproject.toml"),
    path.join(STAGING_DIR, "services", "model-broker", "pyproject.toml"),
  );
  await fs.mkdir(path.join(STAGING_DIR, "config"), { recursive: true });
  await fs.copyFile(
    path.join(ROOT_DIR, "config", "model-registry.json"),
    path.join(STAGING_DIR, "config", "model-registry.json"),
  );

  const desktopPackage = await readJson(
    path.join(ROOT_DIR, "apps", "mentat-desktop", "package.json"),
  );
  const openClawPackage = await readJson(path.join(ROOT_DIR, "package.json"));
  const manifest = {
    schema_version: 1,
    product: "Mentat",
    version: desktopPackage.version,
    openclaw_version: openClawPackage.version,
    node_version: process.version,
    source_commit: await gitCommit(),
    openclaw_entry: "openclaw/node_modules/openclaw/openclaw.mjs",
  };
  await fs.writeFile(
    path.join(STAGING_DIR, "runtime-manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );

  await assertFiles(STAGING_DIR, [
    "runtime-manifest.json",
    "node/node.exe",
    "openclaw/node_modules/openclaw/openclaw.mjs",
    "scripts/mentat/runtime.ps1",
    "scripts/mentat/mentat.ps1",
    "scripts/mentat/doctor.ps1",
    "scripts/mentat/launch.ps1",
    "scripts/mentat/broker.py",
    "scripts/mentat/testing/no_spend_acceptance.py",
    "services/model-broker/mentat_broker/__init__.py",
    "services/model-broker/pyproject.toml",
    "config/model-registry.json",
  ]);

  await fs.rm(PAYLOAD_DIR, { recursive: true, force: true });
  await fs.rename(STAGING_DIR, PAYLOAD_DIR);
  process.stdout.write(`${PAYLOAD_DIR}\n`);
}

await main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
