# Build systems: defaults

Use these only when the project documents nothing better (step 1 of the skill).

| Marker | Release build for this OS | Artifacts | Version check |
|---|---|---|---|
| `Cargo.toml` | `cargo build --release` (add `-p <crate>` for one binary; `--workspace` only when every member builds on this OS) | `target/release/<bin>` (`.exe` on Windows) | `<bin> --version` |
| `package.json` + `pnpm-lock.yaml` | `pnpm install --frozen-lockfile`, then `pnpm build` | the `build` script's output (`dist/`, `out/`, `release/`) | the packaged app's version, or `package.json` `version` |
| `package.json` + `package-lock.json` | `npm ci`, then `npm run build` | as above | as above |
| Electron (`electron-builder`, `electron-forge`) | the project's `dist`/`make` script | `dist/` or `out/make/` installers or unpacked folders | the unpacked exe's file version |
| `*.sln` / `*.csproj` | `dotnet publish -c Release -r <rid>` (`win-x64`, `osx-arm64`, `linux-x64`), or `dotnet build -c Release` for libraries | `bin/Release/<tfm>/<rid>/publish/` | `<exe> --version` where the app has one, else the assembly's file version |
| `pyproject.toml` with `uv.lock` | `uv build` for a package; `uv sync` for an app run from source | `dist/*.whl`, or the entry point in `.venv` | `uv run <entry> --version` |
| `pyproject.toml` (pip) | `python -m build` | `dist/` | as above |
| `go.mod` | `go build -o bin/ ./...` | `bin/` | `<bin> version` or `--version` |
| `CMakeLists.txt` | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release`, then `cmake --build build --config Release` | `build/` (`build/Release/` with multi-config generators) | `<bin> --version` |
| `Makefile` / `justfile` / `Taskfile.yml` | the `build` (or `release`) target | as the target says | as the target says |

The framework's `scripts/detect_commands.py` (`--target <dir> --stack <stack>`) applies the same rules
to a checkout and prints the BUILD, TEST and LINT commands it found.
