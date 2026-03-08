# neveredit

`neveredit` is an editor and resource toolset for **Neverwinter Nights (NWN)** modules and assets.

This repository contains the legacy codebase plus ongoing compatibility and rendering-fidelity updates for modern Python/Linux environments.

## What It Includes

- GUI map and asset editor (`run/neveredit`)
- Standalone script editor (`run/neverscript`)
- Command-line resource tool (`run/nevercommand`)
- Parsers/loaders for NWN formats (`GFF`, `ERF`, `2DA`, `MDL`, `TLK`, `TGA`, `DDS`, `PLT`, etc.)

## Current Status

The project has recently been updated for modern runtimes and improved rendering quality, including:

- Python 3 compatibility fixes across core file/game/ui layers
- wxPython Phoenix event/API migration work
- Improved map rendering stability on Linux
- Better texture/material support (`DDS`, secondary texture channels)
- Initial skinning and PLT tint fidelity improvements for creatures

## Quick Start (From Source)

From this folder (`neveredit/`):

```bash
# Create/activate your virtual environment as needed, then:
./run/neveredit --devel
```

If you are on Wayland and hit GL/wx issues, try:

```bash
GDK_BACKEND=x11 ./run/neveredit --devel
```

Standalone script editor:

```bash
./run/neverscript --devel
```

## Command-Line Tool

`nevercommand` can inspect and extract NWN resources.

Examples:

```bash
./run/nevercommand lookup NSS
./run/nevercommand -m path/to/module.mod print module.ifo
./run/nevercommand -o script.nss get nw_d2_gwiz02.nss
./run/nevercommand strref 13
./run/nevercommand extract path/to/file.erf
```

## Configuration Notes

- NWN install path is resolved via preferences/runtime config.
- NWN:EE layouts are supported (including `data/` key-file layouts).
- Missing `nwntools.nsscompiler` only affects script compilation, not general editor startup.

## Project Layout (High Level)

- `file/` - binary/text resource format readers
- `game/` - gameplay object abstractions and resource management
- `ui/` - wx/OpenGL UI and editors
- `run/` - launcher scripts
- `util/` - utility modules and diagnostics

## Legacy Docs

Older plaintext docs are still present and useful:

- `README`
- `README.commandline`
- `README.scripteditor`

## Credits

See `AUTHORS` and legacy `README` for original project credits and acknowledgements.
