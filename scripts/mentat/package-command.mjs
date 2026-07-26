export function resolvePackageCommand(command, platform = process.platform) {
  if (platform === "win32" && (command === "npm" || command === "pnpm")) {
    return `${command}.cmd`;
  }
  return command;
}
