from pathlib import Path


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]


def patch_workspace() -> None:
    workspace = Path("pnpm-workspace.yaml")
    text = workspace.read_text(encoding="utf-8")
    for stale_rule in (
        '  "axios>agent-base": 7.1.4\n',
        '  "axios>https-proxy-agent": 7.0.6\n',
    ):
        text = text.replace(stale_rule, "")

    marker = "  axios: 1.18.1\n"
    if marker not in text:
        raise SystemExit("Axios workspace authority is missing")
    if "  agent-base: 7.1.4\n" not in text:
        text = text.replace(
            marker,
            marker + "  agent-base: 7.1.4\n  https-proxy-agent: 7.0.6\n",
            1,
        )
    workspace.write_text(text, encoding="utf-8")


def patch_knip() -> None:
    knip = Path("config/knip.config.ts")
    text = knip.read_text(encoding="utf-8")
    entry_marker = '  "apps/android/scripts/build-release-artifacts.ts!",\n'
    entry_replacement = "\n".join(
        [
            '  "apps/android/scripts/build-release-artifacts.ts!",',
            "  // Electron, installer, and no-spend wrappers load these by package metadata",
            "  // or assembled filesystem paths rather than static imports.",
            '  "apps/mentat-desktop/src/main-production.cjs!",',
            '  "apps/mentat-desktop/src/main.cjs!",',
            '  "apps/mentat-desktop/src/no-spend-command.cjs!",',
            '  "apps/mentat-desktop/src/no-spend-cli.cjs!",',
            "  // The standalone desktop package invokes this exact test glob via node --test.",
            '  "apps/mentat-desktop/test/no-spend-command.test.cjs!",',
            "  // Mentat Desktop packaging invokes this helper directly from package.json.",
            '  "scripts/mentat/package-windows-runtime.mjs!",',
            "",
        ]
    )
    if entry_marker not in text:
        raise SystemExit("Knip repository entry marker is missing")
    if "apps/mentat-desktop/src/main-production.cjs!" not in text:
        text = text.replace(entry_marker, entry_replacement, 1)

    dependency_marker = '        "cross-spawn",\n'
    dependency_replacement = "\n".join(
        [
            '        "cross-spawn",',
            "        // Root Knip scans apps/**, but Mentat Desktop is a standalone package",
            "        // whose package.json owns the Electron development dependency.",
            '        "electron",',
            "",
        ]
    )
    if dependency_marker not in text:
        raise SystemExit("Knip dependency-ownership marker is missing")
    if '        "electron",' not in text:
        text = text.replace(dependency_marker, dependency_replacement, 1)
    knip.write_text(text, encoding="utf-8")


COLLECT_CURRENT_OVERRIDES = '''function collectCurrentShrinkwrapOverrides(
  shrinkwrap,
  declaredDependencies = new Set(),
  pnpmLockPackages = readPnpmLockPackages(),
  workspaceOverrideRules = exactOverrideRulesFromOverrides(readWorkspaceOverrides()),
) {
  const packages = shrinkwrap?.packages;
  if (!packages || typeof packages !== "object") {
    return {};
  }
  const versionsByName = new Map();
  for (const [lockPath, metadata] of Object.entries(packages)) {
    if (lockPath === "" || !metadata || typeof metadata !== "object" || !metadata.version) {
      continue;
    }
    const packageName = metadata.name ?? packageNameForLockPath(lockPath);
    const workspaceVersion = packageName ? workspaceOverrideRules[packageName] : undefined;
    if (
      !packageName ||
      declaredDependencies.has(packageName) ||
      !pnpmLockPackages.has(`${packageName}@${metadata.version}`) ||
      (workspaceVersion !== undefined && workspaceVersion !== metadata.version)
    ) {
      continue;
    }
    const versions = versionsByName.get(packageName) ?? new Set();
    versions.add(metadata.version);
    versionsByName.set(packageName, versions);
  }

  const overrides = Object.fromEntries(
    [...versionsByName.entries()]
      .filter(([, versions]) => versions.size === 1)
      .map(([name, versions]) => [name, [...versions][0]])
      .toSorted(([left], [right]) => left.localeCompare(right)),
  );
  const forkedPackageNames = new Set(
    [...versionsByName.entries()].filter(([, versions]) => versions.size > 1).map(([name]) => name),
  );
  const conflicts = new Set();
  for (const [lockPath, metadata] of Object.entries(packages)) {
    if (lockPath === "" || !metadata || typeof metadata !== "object" || !metadata.version) {
      continue;
    }
    const parentName = metadata.name ?? packageNameForLockPath(lockPath);
    const dependencies = metadata.dependencies;
    if (
      !parentName ||
      !dependencies ||
      typeof dependencies !== "object" ||
      Array.isArray(dependencies)
    ) {
      continue;
    }
    const parentSelector = `${parentName}@${metadata.version}`;
    for (const dependencyName of Object.keys(dependencies)) {
      if (!forkedPackageNames.has(dependencyName)) {
        continue;
      }
      const resolved = resolveShrinkwrapDependency(packages, lockPath, dependencyName);
      if (!resolved || !pnpmLockPackages.has(`${dependencyName}@${resolved.version}`)) {
        continue;
      }
      addNestedOverride(overrides, parentSelector, dependencyName, resolved.version, conflicts);
    }
  }
  for (const parentSelector of conflicts) {
    delete overrides[parentSelector];
  }
  return expandScopedOverrideChildren(overrides);
}

'''


NORMALIZE_OVERRIDES = '''function removeViolationPackagePaths(lockfile, violations) {
  const packages = lockfile?.packages;
  if (!packages || typeof packages !== "object") {
    return;
  }
  for (const violation of violations) {
    delete packages[violation.path];
    const subtreePrefix = `${violation.path}/node_modules/`;
    for (const lockPath of Object.keys(packages)) {
      if (lockPath.startsWith(subtreePrefix)) {
        delete packages[lockPath];
      }
    }
  }
}

function scopedOverridesForViolations(shrinkwrapOverrides, violations) {
  const scoped = {};
  for (const violation of violations) {
    const parent = violation.packagePath.at(-2);
    if (!parent) {
      continue;
    }
    const rootSpec = shrinkwrapOverrides[parent.name];
    const rootVersion =
      typeof rootSpec === "string"
        ? rootSpec
        : isPlainObject(rootSpec) && typeof rootSpec["."] === "string"
          ? rootSpec["."]
          : null;
    if (!rootVersion || exactVersionFromOverrideSpec(rootVersion) === null) {
      continue;
    }
    const current = scoped[parent.name];
    const nested = isPlainObject(current) ? current : { ".": rootVersion };
    const existing = nested[violation.packageName];
    if (existing !== undefined && existing !== violation.expectedVersion) {
      throw new Error(
        `conflicting scoped override repair for ${parent.name}>${violation.packageName}`,
      );
    }
    nested[violation.packageName] = violation.expectedVersion;
    scoped[parent.name] = nested;
  }
  return scoped;
}

function normalizeShrinkwrapOverrides(tempDir, shrinkwrapOverrides, npmInstallArgs) {
  const shrinkwrapPath = path.join(tempDir, "npm-shrinkwrap.json");
  const overrideRules = exactOverrideRulesFromOverrides(shrinkwrapOverrides);
  if (Object.keys(overrideRules).length === 0) {
    return;
  }

  const shrinkwrap = JSON.parse(readFileSync(shrinkwrapPath, "utf8"));
  const violations = collectOverrideViolations(shrinkwrap, overrideRules);
  if (violations.length === 0) {
    return;
  }

  const disabled = disableShrinkwrappedOverrideConflictSources(shrinkwrap, overrideRules);
  if (disabled.length === 0) {
    const scopedOverrides = scopedOverridesForViolations(shrinkwrapOverrides, violations);
    if (Object.keys(scopedOverrides).length === 0) {
      throw new Error(
        `generated npm-shrinkwrap.json violates workspace overrides: ${describeOverrideViolations(violations)}`,
      );
    }
    const packageJsonPath = path.join(tempDir, "package.json");
    const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8"));
    packageJson.overrides = mergeOverrides(packageJson.overrides, scopedOverrides, {});
    writeFileSync(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`);
    removeViolationPackagePaths(shrinkwrap, violations);
  }

  // Root overrides can be ignored inside dependency-owned shrinkwraps. Disable
  // explicitly marked embedded shrinkwraps, or derive the narrow parent-scoped
  // override needed for an unmarked conflicting subtree, then let npm rebuild it.
  writeFileSync(shrinkwrapPath, `${JSON.stringify(shrinkwrap, null, 2)}\n`);
  runNpm(npmInstallArgs, tempDir);

  const normalized = JSON.parse(readFileSync(shrinkwrapPath, "utf8"));
  const remaining = collectOverrideViolations(normalized, overrideRules);
  if (remaining.length > 0) {
    const repairLabel =
      disabled.length > 0
        ? `after disabling ${disabled.join(", ")}`
        : "after applying scoped override repair";
    throw new Error(
      `generated npm-shrinkwrap.json violates workspace overrides ${repairLabel}: ${describeOverrideViolations(remaining)}`,
    );
  }
}

'''


UPDATE_OR_CHECK = '''function updateOrCheckPackage(packageDir, check, changedPaths = []) {
  // Existing shrinkwrap topology is advisory, not authoritative: every retained
  // version is filtered through the current pnpm lock and explicit workspace
  // overrides before it is merged with generated policy.
  const generated = generateShrinkwrap(packageDir, {
    useCurrentShrinkwrapOverrides: true,
  });
  const shrinkwrapPath = shrinkwrapPathForPackage(packageDir);
  const label = packageLabel(packageDir);
  if (!check) {
    writeFileSync(shrinkwrapPath, generated);
    return `${label}: npm-shrinkwrap.json updated.`;
  }

  let current;
  try {
    current = readFileSync(shrinkwrapPath, "utf8");
  } catch {
    throw new Error(
      `${label}: npm-shrinkwrap.json is missing. Run \\`pnpm deps:shrinkwrap:generate\\`.`,
    );
  }
  if (current !== generated) {
    throw new Error(
      `${label}: npm-shrinkwrap.json is stale. Run \\`pnpm deps:shrinkwrap:generate\\`.`,
    );
  }
  return `${label}: npm-shrinkwrap.json is current.`;
}

'''


WORKER_PIPELINE = '''async function runPackageWorker(packageDir, check, changedPaths) {
  return await new Promise((resolve, reject) => {
    const worker = new Worker(new URL(import.meta.url), {
      workerData: {
        changedPaths,
        check,
        kind: SHRINKWRAP_WORKER_KIND,
        packageDir,
      },
    });
    const timeoutMs = readPositiveIntEnv(
      "OPENCLAW_NPM_SHRINKWRAP_PACKAGE_TIMEOUT_MS",
      NPM_SHRINKWRAP_PACKAGE_TIMEOUT_MS,
    );
    let settled = false;
    const settle = (callback, value) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      callback(value);
    };
    const timer = setTimeout(() => {
      settle(
        reject,
        new Error(`${packageLabel(packageDir)}: shrinkwrap generation exceeded ${timeoutMs}ms`),
      );
      void worker.terminate();
    }, timeoutMs);

    worker.once("message", (message) => {
      if (message.error) {
        settle(reject, new Error(message.error));
      } else {
        settle(resolve, message.output);
      }
    });
    worker.once("error", (error) => settle(reject, error));
    worker.once("exit", (code) => {
      if (!settled) {
        settle(
          reject,
          new Error(
            code === 0
              ? `${packageLabel(packageDir)}: shrinkwrap worker exited without a result`
              : `${packageLabel(packageDir)}: shrinkwrap worker exited ${code}`,
          ),
        );
      }
    });
  });
}

async function updateOrCheckPackages({ check, changedPaths, jobs, packageDirs }) {
  const outcomes = await pMap(
    packageDirs,
    async (packageDir) => {
      try {
        return { output: await runPackageWorker(packageDir, check, changedPaths) };
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const label = packageLabel(packageDir);
        return {
          error: message.startsWith(`${label}:`) ? message : `${label}: ${message}`,
        };
      }
    },
    { concurrency: jobs, stopOnError: false },
  );

  const errors = [];
  for (const outcome of outcomes) {
    if (outcome.error) {
      errors.push(outcome.error);
    } else {
      process.stdout.write(`${outcome.output}\n`);
    }
  }
  if (errors.length > 0) {
    throw new Error(errors.join("\n"));
  }
}

'''


def patch_generator() -> None:
    generator = Path("scripts/generate-npm-shrinkwrap.mjs")
    text = generator.read_text(encoding="utf-8")

    command_timeout = "const NPM_SHRINKWRAP_COMMAND_TIMEOUT_MS = 10 * 60 * 1000;\n"
    package_timeout = (
        command_timeout
        + "const NPM_SHRINKWRAP_PACKAGE_TIMEOUT_MS = 15 * 60 * 1000;\n"
    )
    if "NPM_SHRINKWRAP_PACKAGE_TIMEOUT_MS" not in text:
        if command_timeout not in text:
            raise SystemExit("Shrinkwrap command-timeout marker is missing")
        text = text.replace(command_timeout, package_timeout, 1)

    text = replace_between(
        text,
        "function collectCurrentShrinkwrapOverrides(",
        "function readCurrentShrinkwrapOverrides(",
        COLLECT_CURRENT_OVERRIDES,
    )
    text = replace_between(
        text,
        "function normalizeShrinkwrapOverrides(",
        "function normalizeNpmVersionDrift(",
        NORMALIZE_OVERRIDES,
    )
    text = replace_between(
        text,
        "function updateOrCheckPackage(",
        "/** @internal Directly tested script implementation detail. */\nexport function resolveShrinkwrapJobs",
        UPDATE_OR_CHECK,
    )
    text = replace_between(
        text,
        "async function runPackageWorker(",
        "async function main()",
        WORKER_PIPELINE,
    )
    generator.write_text(text, encoding="utf-8")


def main() -> None:
    patch_workspace()
    patch_knip()
    patch_generator()


if __name__ == "__main__":
    main()
