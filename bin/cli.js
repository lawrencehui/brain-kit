#!/usr/bin/env node
// npx create-second-brain [--vault ~/brain] [...install.sh flags]
// Thin wrapper: runs the bundled zsh installer with the same arguments.
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
if (spawnSync("zsh", ["-c", "true"]).status !== 0) {
  console.error("create-second-brain needs zsh (macOS has it; on Linux: apt install zsh).");
  process.exit(1);
}
const r = spawnSync("zsh", [join(root, "install.sh"), ...process.argv.slice(2)], { stdio: "inherit" });
process.exit(r.status ?? 1);
