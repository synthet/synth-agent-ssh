# Deploy recipe: `.agent/deploy.json`

A small file in the project that holds only what `/deploy` can't work out by itself. Build, test and
lint commands stay where the project documents them (`AGENTS.md`, `.agent/COMMANDS.md`); repeat a
`build` line here only when deploying needs a different command.

```json
{
  "app": "acme-files",
  "deploy": "local",
  "verified": false,
  "build": "python scripts/package_release.py",
  "procedure": null,
  "artifacts_dir": "dist/acme-files-{version}-windows-x64",
  "install_name": "acme-files",
  "executables": [
    {"file": "acme-files.exe", "kind": "gui", "version_args": ["--version"]},
    {"file": "acmef.exe", "kind": "cli", "version_args": ["--version"], "on_path": true}
  ],
  "shortcuts": [
    {"name": "Acme Files", "target": "acme-files.exe", "icon": "assets/icon.ico", "icon_name": "acme-files-gui.ico"},
    {"name": "Acme Files (terminal)", "target": "acmef.exe", "icon": "assets/icon-tui.ico", "icon_name": "acme-files-tui.ico"}
  ],
  "stop": [],
  "os": ["windows"]
}
```

| Field | Meaning |
|---|---|
| `deploy` | `"local"`, or `"none"` with a `"reason"` (library, bot hosted elsewhere, deployed by its own pipeline) |
| `verified` | `true` once `/deploy` has run with this recipe on this OS; `false` for a recipe written from the docs only |
| `build` | optional; overrides the build command from the project's docs |
| `procedure` | optional; a script or doc section to follow instead of the generic install, such as a cutover runbook |
| `artifacts_dir` | where the build leaves the files to install; `{version}` expands from the project's version source |
| `install_name` | the install folder's name (defaults to `app`) |
| `executables` | each with `kind` (`gui`, `cli`, `service`), the version flag, and `on_path` for CLI tools that get a launcher in the PATH folder |
| `shortcuts` | desktop shortcuts: name, target executable, the icon file in the repo, and its installed file name |
| `stop` | processes, tasks or services the user approved stopping (not changing) before an install, with the command for each |
| `os` | the OSes this recipe was written for |

## Install locations

| OS | Install folder | PATH folder | Shortcuts and icons |
|---|---|---|---|
| Windows | `%LOCALAPPDATA%\Programs\<install_name>` | `%USERPROFILE%\.local\bin` | `.lnk` on the Desktop (`[Environment]::GetFolderPath('Desktop')`); icons in `%LOCALAPPDATA%\SynthIcons` |
| macOS | `~/Applications/<App>.app` for an app bundle, else `~/.local/opt/<install_name>` | `~/.local/bin` | the app bundle in `~/Applications`; no Desktop alias unless the recipe asks |
| Linux | `~/.local/opt/<install_name>` | `~/.local/bin` | `~/.local/share/applications/<install_name>.desktop`, icon in `~/.local/share/icons` |

On Windows, set a shortcut with `WScript.Shell` (`CreateShortcut`, then `TargetPath`,
`WorkingDirectory`, `IconLocation = "<icon>,0"`, `Save()`), and read it back with `CreateShortcut`
again. First back up the old `.lnk`, icon and PATH launcher into this run's folder,
`deploy-backup-<install_name>-<yyyyMMdd-HHmmss>` next to the icons, as in step 6 of the skill.
