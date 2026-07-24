#!/usr/bin/env bash
#
# Set up the Guild AI benchmark environment for Firevolv.
#
# Guild AI 0.9.0 does NOT run on Python 3.12+ (it imports the removed `imp`
# module), so this creates an isolated Python 3.11 conda env named `guild`
# with a pinned, 3.11-compatible dependency set (see requirements-eval.txt).
#
# Usage:
#   ./eval/setup_guild_env.sh          # create env + install deps
#   conda activate guild               # then, in your shell:
#   cd eval && guild run bench corpus_version=v0   # (or v1 / v2)
#   guild compare                      # F1 across corpus versions
#
# Requires: conda (Miniconda/Anaconda) on PATH.
set -euo pipefail

ENV_NAME="guild"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found on PATH. Install Miniconda/Anaconda first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "==> conda env '$ENV_NAME' already exists — reusing it"
else
  echo "==> creating conda env '$ENV_NAME' (Python 3.11)"
  conda create -y -n "$ENV_NAME" python=3.11
fi

echo "==> installing pinned deps from requirements-eval.txt"
conda run -n "$ENV_NAME" python -m pip install -r "$REPO_ROOT/requirements-eval.txt"

echo "==> verifying"
conda run -n "$ENV_NAME" guild --version
conda run -n "$ENV_NAME" python -c "import fastapi, pydantic, sklearn, pkg_resources; print('backend imports OK')"

cat <<EOF

Done. Next:
  conda activate $ENV_NAME
  cd "$REPO_ROOT/eval"
  guild run bench corpus_version=v0    # or v1 / v2
  guild compare                         # the F1-over-versions table

Note: copy .env.example -> .env if you have Pioneer/Actian keys. The benchmark
runs fine WITHOUT them (retrieval fallback path).
EOF
