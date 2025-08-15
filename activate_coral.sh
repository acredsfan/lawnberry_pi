#!/bin/bash
if ! command -v pyenv >/dev/null 2>&1; then
  echo "pyenv is required but not installed." >&2
  exit 1
fi
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
pyenv activate "coral-python39"
exec $SHELL
