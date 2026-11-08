#!/bin/bash
# Builds the kells-letters env on Sonic and downloads the base models. Run once on the login node, from
# ~/scratch/kells-letters. make stops unless the env's folder is named kells-letters, so the env lives at
# ~/scratch/envs/kells-letters. party is installed with --no-deps (environment.yml, top comment): its own
# requirement would downgrade Kraken below the pinned 7.1.1.
# Usage: bash sonic/setup_env.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ENV=$HOME/scratch/envs/kells-letters
PARTY="git+https://github.com/mittagessen/party@c2589b1b515ed690f883c6afaef6c01ce29bf72d"
module load anaconda3/2025.12-1
# download caches in scratch: home's quota is small
export CONDA_PKGS_DIRS=$HOME/scratch/conda-pkgs PIP_CACHE_DIR=$HOME/scratch/pip-cache
# environment.yml's conda layer is only the base Python, from the defaults channel, which asks for its terms of
# service on Sonic: the same Python comes from conda-forge, then the file's pinned pip packages
conda create -y -p "$ENV" -c conda-forge --override-channels python=3.11.18 pip
# Sonic's GPU drivers run CUDA 12.7 at most (sonicgpu9, 4 Nov 2026) and environment.yml's torch is the CUDA 13 build:
# the same torch built for CUDA 12.6, with its own CUDA libraries, and torchvision 0.29.1, the newest built for CUDA 12.6
# (0.29.2 is not). torch goes first, and the file's CUDA packages (nvidia-*, cuda-*: the CUDA 13 build's own) are left
# out, so torch brings its own and nothing pulls in the CUDA 13 build; the test below stops the setup if it did.
"$ENV/bin/pip" install torch==2.14.0+cu126 torchvision==0.29.1+cu126 \
    --index-url https://download.pytorch.org/whl/cu126 --extra-index-url https://pypi.org/simple
sed -n '/^  - pip:/,$p' environment.yml | sed -n 's/^      - //p' | grep -vE "^(party @|torch==|torchvision==|nvidia-|cuda-)" \
    > "$ENV/requirements.txt"
"$ENV/bin/pip" install -r "$ENV/requirements.txt"
"$ENV/bin/pip" check
"$ENV/bin/python" -c "import sys, torch; sys.exit(None if torch.version.cuda == '12.6' else
    f'torch {torch.__version__} is built for CUDA {torch.version.cuda}, not 12.6: Sonic cannot run it')"
"$ENV/bin/pip" install --no-deps "$PARTY"
"$ENV/bin/python" -c "from importlib.metadata import version as v; import kraken, party, torch; print('kraken', v('kraken'), 'party', v('party'), 'torch', torch.__version__, 'CUDA', torch.version.cuda)"
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV"
set -u
KELLS_MODELS=$HOME/scratch/kells-models make models
