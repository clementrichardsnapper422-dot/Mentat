import path from "node:path";

export function endpointConfigPaths(registry) {
  if (!Array.isArray(registry?.models) || registry.models.length === 0) {
    throw new Error("Model registry must declare at least one model.");
  }

  const endpointPaths = registry.models.map((model, index) => {
    const configuredPath = model?.endpoint_config;
    if (typeof configuredPath !== "string" || configuredPath.trim() === "") {
      throw new Error(
        `Model registry entry ${model?.id || index} is missing endpoint_config.`,
      );
    }

    const portablePath = configuredPath.replaceAll("\\", "/");
    const normalizedPath = path.posix.normalize(portablePath);
    if (
      path.posix.isAbsolute(normalizedPath) ||
      path.win32.isAbsolute(configuredPath) ||
      normalizedPath === ".." ||
      normalizedPath.startsWith("../")
    ) {
      throw new Error(
        `Model registry endpoint_config must stay inside the runtime: ${configuredPath}`,
      );
    }
    return normalizedPath;
  });

  return [...new Set(endpointPaths)];
}
