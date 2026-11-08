#!/bin/bash
# One reader run start to finish on one L40S (any BASE in config/models.yaml: Kraken's classic reader, PP-OCRv6 or
# party): St Gall fine-tuning from BASE, Kells two folds and final model, the test pages read once, scored (make
# reader). Submit from ~/scratch/kells-letters after sonic/sync.sh and sonic/setup_env.sh:
#   sbatch --export=ALL,BASE=ppocrv6-medium,EXTRA=1 sonic/train_reader.sbatch
#   test job first: sbatch --time=00:30:00 --export=ALL,BASE=ppocrv6-medium,RUN=ppocr-test,OUT=outputs/ppocr-test,STGALL_ARGS="-q fixed -N 1",KELLS_ARGS="--passes 2" sonic/train_reader.sbatch
#SBATCH --job-name=kells-reader
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --constraint=l40s
#SBATCH --account=shared_acc
#SBATCH --cpus-per-task=4               # the 4 data workers every training step uses
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x_%j.out
set -euo pipefail
: "${BASE:?set BASE, a model in config/models.yaml}"
module load anaconda3/2025.12-1
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$HOME/scratch/envs/kells-letters"
set -u
export KELLS_MODELS=$HOME/scratch/kells-models
# party builds its model from two Hugging Face downloads (a timm encoder, bytellama) on every load, hundreds of times a
# run; they are read from Sonic's cache (~/.cache/huggingface, filled by the first party job), never fetched
export HF_HUB_OFFLINE=1
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
make reader BASE="$BASE" ${RUN:+RUN="$RUN"} ${OUT:+OUT="$OUT"} ${EXTRA:+EXTRA="$EXTRA"} \
    STGALL_ARGS="${STGALL_ARGS:-}" KELLS_ARGS="${KELLS_ARGS:-}"
