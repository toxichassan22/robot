import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const workspaceRoot = path.resolve(path.dirname(scriptPath), "..");
const viteBin = path.join(workspaceRoot, "node_modules", "vite", "bin", "vite.js");
const tscBin = path.join(workspaceRoot, "node_modules", "typescript", "lib", "tsc.js");
const eslintBin = path.join(workspaceRoot, "node_modules", "eslint", "bin", "eslint.js");
const jestBin = path.join(workspaceRoot, "node_modules", "jest", "bin", "jest.js");
const pythonPathKey = "PYTHONPATH";
const pythonPathSep = process.platform === "win32" ? ";" : ":";

function prependPythonPath(env) {
  const sdRoot = path.resolve(workspaceRoot, "..", "..", "sd");
  const existing = String(env[pythonPathKey] || "").trim();
  return {
    ...env,
    [pythonPathKey]: existing ? `${sdRoot}${pythonPathSep}${existing}` : sdRoot,
  };
}

function run(command, args, extraEnv = process.env) {
  const child = spawn(command, args, {
    cwd: workspaceRoot,
    env: extraEnv,
    stdio: "inherit",
    shell: false,
    windowsHide: false,
  });

  child.on("error", (error) => {
    console.error(error.message);
    process.exit(1);
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 1);
  });
}

switch (process.argv[2]) {
  case "client:dev":
    run(process.execPath, [viteBin, "--host", "0.0.0.0", "--config", "frontend/vite.config.ts"]);
    break;
  case "build":
    run(process.execPath, [viteBin, "--config", "frontend/vite.config.ts", "build"]);
    break;
  case "preview":
    run(process.execPath, [viteBin, "preview", "--host", "0.0.0.0", "--config", "frontend/vite.config.ts"]);
    break;
  case "check":
    run(process.execPath, [tscBin, "--noEmit", "-p", "tsconfig.json"]);
    break;
  case "lint":
    run(process.execPath, [eslintBin, "."]);
    break;
  case "test":
    run(process.execPath, [jestBin]);
    break;
  case "server:dev":
    run(process.env.PYTHON || "python", ["-m", "brain.pi5.web_ui_backend.main"], prependPythonPath(process.env));
    break;
  default:
    console.error(`Unknown task: ${String(process.argv[2] || "")}`);
    process.exit(1);
}
