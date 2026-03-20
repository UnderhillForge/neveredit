#!/usr/bin/env zsh

set -e

script_dir=${0:A:h}
venv_python="$script_dir/.venv/bin/python"
app_runner="$script_dir/neveredit/run/neveredit"

if [[ -x "$venv_python" ]]; then
	exec "$venv_python" "$app_runner" --disable_pythonw "$@"
fi

exec python3 "$app_runner" --disable_pythonw "$@"