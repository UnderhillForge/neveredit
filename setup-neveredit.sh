#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
APP_DIR="$REPO_ROOT/neveredit"
VENV_DIR="$REPO_ROOT/.venv"
PYTHON_CMD="${PYTHON:-python3}"

print_step() {
  printf '\n[setup] %s\n' "$1"
}

die() {
  printf '\n[setup] ERROR: %s\n' "$1" >&2
  exit 1
}

if [[ ! -d "$APP_DIR" ]]; then
  die "Could not find neveredit source folder at $APP_DIR"
fi

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  die "Python command '$PYTHON_CMD' was not found. Install Python 3."
fi

if [[ "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./setup-neveredit.sh [--recreate-venv]

Options:
  --recreate-venv   Remove and rebuild .venv from scratch.
  --help            Show this help.

Environment:
  PYTHON=/path/to/python3  Use a specific Python executable.
EOF
  exit 0
fi

if [[ "${1:-}" == "--recreate-venv" ]]; then
  print_step "Removing existing virtual environment"
  rm -rf "$VENV_DIR"
fi

print_step "Creating virtual environment at $VENV_DIR"
"$PYTHON_CMD" -m venv "$VENV_DIR"

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

print_step "Upgrading pip/setuptools/wheel"
"$VENV_PY" -m pip install --upgrade pip setuptools wheel

print_step "Installing core Python dependencies"
"$VENV_PIP" install numpy Pillow PyOpenGL PyOpenGL_accelerate

if [[ ! -e "$APP_DIR/.venv" ]]; then
  print_step "Linking $APP_DIR/.venv to project virtual environment"
  ln -s ../.venv "$APP_DIR/.venv"
fi

print_step "Installing wxPython"
if ! "$VENV_PY" -c "import wx" >/dev/null 2>&1; then
  if ! "$VENV_PIP" install wxPython; then
    OS_NAME="$(uname -s)"
    printf '\n[setup] wxPython installation failed.\n' >&2
    if [[ "$OS_NAME" == "Linux" ]]; then
      cat >&2 <<'EOF'
[setup] Linux hint:
  Install GTK and wx build/runtime packages, then rerun setup.
  Ubuntu/Debian example:
    sudo apt-get update
    sudo apt-get install -y libgtk-3-dev libglib2.0-dev libjpeg-dev libpng-dev libtiff-dev libnotify-dev freeglut3-dev
EOF
    elif [[ "$OS_NAME" == "Darwin" ]]; then
      cat >&2 <<'EOF'
[setup] macOS hint:
  Ensure Xcode Command Line Tools are installed:
    xcode-select --install
  Then rerun this script.
EOF
    fi
    exit 1
  fi
fi

print_step "Verifying imports"
if ! "$VENV_PY" - <<'PY'
import importlib
import sys

required = ["numpy", "PIL", "OpenGL", "wx"]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)

if missing:
    print("Missing imports: " + ", ".join(missing))
    sys.exit(1)
PY
then
  die "Dependency verification failed"
fi

cat <<EOF

[setup] Success. neveredit is ready.

Run with:
  $VENV_PY $APP_DIR/run/neveredit --disable_pythonw

Optional helper (macOS):
  $REPO_ROOT/run-mac.sh

EOF
