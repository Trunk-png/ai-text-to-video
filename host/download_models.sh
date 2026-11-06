#!/usr/bin/env bash
set -euo pipefail
MODEL_ROOT="${MODEL_ROOT:-$(cd "$(dirname "$0")/.." && pwd)/data/models}"
download() {
  local folder="$1" url="$2" name="${2##*/}"
  mkdir -p "${MODEL_ROOT}/${folder}"
  curl --fail --location --retry 5 --retry-delay 3 --continue-at - --output "${MODEL_ROOT}/${folder}/${name}" "$url"
}
download diffusion_models https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors
download text_encoders https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
download text_encoders https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors
download vae https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_int8_convrot.safetensors
download loras https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/loras/pika_h3_flex_fl2va_v1_bf16.safetensors

