# CLI resolution and host context

Use when a Windows CLI upgrade appears ineffective, an npm launcher is blocked, a fix disappears
in another terminal, or authentication/model availability differs between execution contexts.

## Identify the command the user actually runs

1. Identify the affected shell and host application. Windows Terminal is a host; its tabs can run
   Command Prompt, PowerShell 5.1, PowerShell 7, or another shell. Do not assume one shell covers all.
2. In the affected PowerShell session, inspect resolution before reinstalling. For example:

   ```powershell
   Get-Command codex -All | Select-Object CommandType, Source, Definition
   where.exe codex
   npm.cmd prefix -g
   npm.cmd list -g @openai/codex --depth=0
   ```

   `where.exe` finds PATH launchers; it does not reveal a PowerShell function or alias that wins
   command resolution. Inspect only the matching definition and relevant profile lines. Check
   the profile paths for the actual PowerShell version; 5.1 and 7 can load different profiles.
3. Compare the resolved command with the intended installation by invoking its absolute path.
   Package-manager, desktop-app, and extension-bundled executables can be independent installs.
   An upgrade to one does not prove the user is launching that copy.
4. If PowerShell blocks an npm `.ps1` launcher, invoke the matching `.cmd` launcher to diagnose
   the installation without changing execution policy. If the user needs the bare command,
   treat this as a diagnostic workaround until persistent command resolution is verified.

Why: a profile function can force an old executable even when npm and PATH point at a newer copy.

## Fix and verify persistence at the right scope

- Distinguish a session-only alias, a shell profile, persistent user/machine PATH, and the
  environment inherited by an already-running terminal host. A temporary alias is not a durable fix.
- If a profile function is responsible, back up the profile and change only the matching function.
  Preserve its intentional arguments. A PowerShell profile change does not configure Command
  Prompt or Git Bash, and a profile cannot provide persistence if the shell refuses to load it.
- Inspect persistent PATH and earlier matching launchers before editing PATH. Do not change it
  when it already resolves correctly. Execution-policy changes remain a separate owner decision;
  do not relax policy as an automatic launcher fix.
- Open a fresh session with the user's normal startup configuration and run the bare command's
  version check. A `-NoProfile` shell only isolates profile behavior; it cannot prove a profile fix.
  For Command Prompt use `where codex` and `codex --version`; for Git Bash use `type -a codex`
  and `codex --version`. Verify every affected shell, reporting which ones were actually tested.
- If an existing host retains old environment values, restart that host when the user is ready.
  Do not terminate active sessions to force a refresh.

Why: a working absolute path or one modified session does not establish persistent bare-command use.

## Separate local isolation from account or catalog state

1. For a login or catalog mismatch, compare the executable, shell, CLI home, and execution context
   used by the failing check with the user's working session. A sandbox can expose a different
   environment or credential-store access; its result alone does not establish host login state.
2. Use the CLI's supported status and catalog commands. If isolation prevents a representative
   check, request the normal authorized host check or give the user the exact command. Do not read,
   print, copy, or relocate credential files or tokens, and do not bypass a denied check.
3. Separate installed version, bundled catalog, refreshed authenticated catalog, and the catalog
   already loaded by a running session. For Codex-specific commands and model names, use the
   OpenAI Docs skill and verify flags against the installed CLI's help.
4. Report only what the evidence proves: a model listed in a catalog is not proof of a successful
   inference request. A running picker may need a new session after a catalog refresh. Do not
   force a catalog override or change model defaults merely to make an unavailable model appear.

Why: isolation and stale session state can resemble missing authentication or model access.
