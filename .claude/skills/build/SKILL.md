---
name: build
description: "Build the current project for this machine's OS: find the project's own build procedure (its AGENTS.md, CLAUDE.md or README commands, a task runner, a release script, or the build line of its .agent/deploy.json), else the ecosystem default (cargo, npm/pnpm, dotnet, uv/pip, go, cmake, make), run it, and report the artifacts, the commit they came from, and their own version output. Use when a task needs a fresh build, when the user asks to build, compile or package a project, or before /deploy. Builds only; installing is /deploy."
capability: "Build a project for the current OS with its own declared procedure and report verified artifacts."
side_effect_level: local_write
approval_required: false
requires_tools: "git; the project's toolchain (cargo, node, dotnet, python/uv, go, cmake, make)."
output_schema: "The commit and whether the tree was clean, the build command and its exit code, each artifact's path, size and version output, and anything not built with the reason."
risk_class: low
---

# Build

`/build` means: **build this project for this OS, the way the project says to.** It writes only build
output (`target/`, `dist/`, `bin/`, `out/` and the like). It never installs, copies to the user's
programs, or touches shortcuts; that is `/deploy`.

How this differs from neighbours:
- `/build` produces and checks artifacts.
- `/deploy` installs a build on this machine, with shortcuts. It starts with `/build`.
- `/test-and-fix` and the project's test command check behaviour; a build doesn't.

## 1. Find the procedure

Use the first that exists, and say which:

1. The `build` entry of `.agent/deploy.json` (see [`../deploy/references/recipe.md`](../deploy/references/recipe.md)).
2. A release or packaging script the project documents, such as `scripts/package_release.py` or a
   platform script like `script/build-windows.ps1`. Prefer it over a bare compile: it knows which
   artifacts belong together.
3. The build command in `AGENTS.md`, `CLAUDE.md`, `.agent/COMMANDS.md` or the README, or a task runner
   target (`make build`, `just build`, a `package.json` `build` script).
4. The ecosystem default, from [`references/build-systems.md`](references/build-systems.md).

A repository with several build systems (a Cargo workspace with a web UI, a Node app with a .NET
service) builds each part its procedure names. Don't guess a combination the project doesn't document.

## 2. Build

- **Note the state first:** `git rev-parse HEAD` and `git status --short`. A dirty tree is fine for a
  local build, but the report says so.
- **Build for this OS and architecture,** in release mode unless the procedure says otherwise.
- **Reuse the project's environment** (its virtualenv, `node_modules`, toolchain pin such as
  `rust-toolchain.toml`). Install dependencies only the documented way (`npm ci`, `uv sync`), and never
  globally.
- **Long builds:** run them with a generous timeout, and don't start a second heavy build of the same
  project at the same time. Shared target folders lock.
- **Never hide the exit code** behind a pipe (`| tail`); record it.

## 3. Check the artifacts

- Every artifact the procedure names exists, with a fresh timestamp.
- Run each executable's own version or help flag (`--version`, `-V`), and quote what it prints. A
  binary that doesn't start isn't built.
- For a GUI, don't launch it here; the version check and a size are enough.

## 4. Report

```markdown
**Built** <project> at <sha> (<clean | dirty: n files>) for <os/arch>: `<command>` exit 0.

| Artifact | Size | Version output |
|---|---|---|
| <path> | <MB> | <first line> |
```

List anything not built, with the reason and the command to build it.
