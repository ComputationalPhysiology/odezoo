#!/usr/bin/env bash
set -e # Exit immediately if a command exits with a non-zero status

chsh -s "$(which zsh)" root || true
if ! command -v starship &> /dev/null; then
  echo "Installing Starship prompt..."
  curl -sS https://starship.rs/install.sh | sh -s -- -y
fi

# The checkout is bind-mounted from the host, so git may see another owner.
git config --global --add safe.directory "$(pwd)"

python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
pre-commit install

echo "Container setup complete!"
