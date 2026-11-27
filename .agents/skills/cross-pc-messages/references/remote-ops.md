# Remote operations between Windows PCs

Lessons from setting up one PC from another over SSH, SMB and agent-mail. Open this file when a message asks
you to act on the other PC directly rather than through the shared folder.

## PowerShell over SSH

- Windows OpenSSH often starts `cmd.exe` as the default shell, so nested quoting breaks. Send scripts as
  `powershell -NoProfile -EncodedCommand <base64 of UTF-16LE text>`.
- Pipe secrets in on **stdin**, never as arguments: arguments show up in process lists and logs.
- PowerShell progress records come back as `#< CLIXML` noise on stderr. That's not an error; set
  `$ProgressPreference = 'SilentlyContinue'` in the script to drop it.

## Long-running processes

- Windows OpenSSH kills the session's child processes on disconnect. For a listener or other long-running
  process, register a scheduled task instead of starting it from the SSH session.
- Build the principal with `New-ScheduledTaskPrincipal -UserId ((whoami).Trim()) -LogonType Interactive`.
  `"$env:USERDOMAIN\$env:USERNAME"` fails over SSH with "No mapping between account names and security IDs".
- A task without a logon trigger doesn't come back after a reboot. Say so in your message, or ask the user
  to add the trigger.

## agent-mail pairing

- Swap fingerprints over a channel you already trust (SSH, in person). Never over agent-mail itself.
- Builds differ in what `trust --file` accepts. Older builds reject the newer `origin`/`agent` keys, so pass
  `{name, signing_key, encryption_key}` only, plus `--fingerprint` and `--endpoint http://<ip>:47832` when
  discovery isn't available.
- A receipt means the other side stored the message, not that an agent read it.

## Files and paths

- Git Bash rewrites UNC paths: `\\host\share` arrives as `\host\share`, and writes land on the local disk.
  Use PowerShell for SMB paths, and read the copy back to confirm it went where you meant.
- `robocopy` exit codes 0–7 are success (1 = files copied). Compare file counts and sizes per path afterwards.
  Watch for tracked repo files it overwrote with different line endings.

## What stays with the user

- Harness hooks may block reading `.env`, `secrets.json` or `~/.ssh/config` even for a presence check, and may
  refuse to generate credentials. Make those steps the user's: a small script they run themselves
  (`! pwsh -File <script>`), which never prints the secret, works well.
- Firewall rules, service installs and anything needing elevation: hand the user one script, scoped to the
  other PC's address, and say what it opens.
