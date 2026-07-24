#!/usr/bin/env bash
#
# Set up the Guild AI benchmark environment for Firevolv.
#
# Guild AI 0.9.0 does NOT run on Python 3.12+ (it imports the removed `imp`
# module), so this creates an isolated Python 3.11 conda env named `guild`
# with a pinned, 3.11-compatible dependency set (see requirements-eval.txt).
#
# NAME COLLISION WARNING: the Guild.ai *agent platform* CLI (a different product)
# also installs a `guild` binary — commonly at /opt/homebrew/bin/guild. On many
# machines it sits ahead of the conda env on PATH, so BOTH `conda activate guild`
# and `conda run -n guild` still resolve to that other `guild` (which has no
# `run`/`compare` commands). We therefore call the env's guildai binary by its
# ABSOLUTE path ($GUILD) rather than trusting PATH.
#
# Usage:
#   ./eval/setup_guild_env.sh          # create env + install deps (prints $GUILD)
#   # then run the benchmark with the absolute path this script prints, e.g.:
#   cd eval && "$GUILD" run bench corpus_version=v0   # (or v1 / v2)
#   "$GUILD" compare                   # F1 across corpus versions
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

# Resolve the guildai binary by ABSOLUTE path. Do NOT use `guild` off PATH or
# `conda run -n guild guild`: the Guild.ai agent-platform CLI (a different tool
# with the same name) often shadows both. Deriving the path from the env's
# python interpreter is collision-proof.
ENV_BIN="$(conda run -n "$ENV_NAME" python -c 'import sys, os; print(os.path.dirname(sys.executable))')"
GUILD="$ENV_BIN/guild"

echo "==> verifying"
"$GUILD" --version   # must print a 0.9.x line, NOT the agent-platform version
conda run -n "$ENV_NAME" python -c "import fastapi, pydantic, sklearn, pkg_resources; print('backend imports OK')"

cat <<EOF

Done. The guildai binary for this repo is:
  $GUILD

Run the benchmark with that ABSOLUTE path (PATH may resolve 'guild' to a
different, unrelated CLI — see the header note):
  GUILD="$GUILD"
  cd "$REPO_ROOT/eval"
  "\$GUILD" run bench corpus_version=v0    # or v1 / v2
  "\$GUILD" compare                         # the F1-over-versions table

Note: copy .env.example -> .env if you have Pioneer/Actian keys. The benchmark
runs fine WITHOUT them (retrieval fallback path).
EOF
