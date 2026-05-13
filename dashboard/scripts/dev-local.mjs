import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const scriptDir = path.dirname(scriptPath);
const runnerPath = path.join(scriptDir, "run-local.mjs");
const children = new Set();
let shuttingDown = false;

function stopAll(signal = "SIGTERM") {
  for (const child of children) {
    try {
      child.kill(signal);
    } catch {
      // Ignore already-exited children.
    }
  }
}

function launch(task) {
  const child = spawn(process.execPath, [runnerPath, task], {
    stdio: "inherit",
    shell: false,
    windowsHide: false,
  });

  children.add(child);

  child.on("error", (error) => {
    console.error(error.message);
    if (!shuttingDown) {
      shuttingDown = true;
      stopAll("SIGTERM");
      process.exit(1);
    }
  });

  child.on("exit", (code, signal) => {
    children.delete(child);
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    stopAll("SIGTERM");
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 1);
  });
}

for (const signal of ["SIGINT", "SIGTERM", "SIGBREAK"]) {
  process.on(signal, () => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    stopAll(signal);
    setTimeout(() => process.exit(0), 250);
  });
}

function isPortOpen(port, host = "127.0.0.1", timeoutMs = 400) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ port, host });

    const finish = (result) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(result);
    };

    socket.setTimeout(timeoutMs);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
  });
}

launch("client:dev");
console.log("Waiting for Brain backend to start on port 8000...");
