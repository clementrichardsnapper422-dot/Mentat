export function resolvePackageInvocation(
  command,
  args,
  platform = process.platform,
  commandShell = process.env.ComSpec || "cmd.exe",
) {
  if (platform === "win32" && (command === "npm" || command === "pnpm")) {
    return {
      command: commandShell,
      args: ["/d", "/s", "/c", `${command}.cmd`, ...args],
    };
  }
  return { command, args };
}
