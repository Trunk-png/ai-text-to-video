FROM nvidia/cuda:13.0.2-cudnn-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 COMFY_HOME=/opt/ComfyUI PORT=8188
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates build-essential ffmpeg libgl1 libglib2.0-0 \
    python3.12 python3.12-venv python3.12-dev && rm -rf /var/lib/apt/lists/*
RUN python3.12 -m venv /opt/py312 && /opt/py312/bin/python -m ensurepip --upgrade && \
    /opt/py312/bin/pip install --upgrade pip setuptools wheel
ENV PATH=/opt/py312/bin:$PATH
WORKDIR /opt
RUN pip install --no-build-isolation torch==2.9.1+cu130 torchvision==0.24.1+cu130 torchaudio==2.9.1+cu130 \
    --extra-index-url https://download.pytorch.org/whl/cu130
ARG COMFY_VERSION=0.37.0
RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    git -C ComfyUI checkout tags/v${COMFY_VERSION}
ARG NSFW_TEXT_COMMIT=fd740ce6789806bf14299d8dad7632d541db0c42
RUN git clone https://github.com/trungnk-png/comfyUI-detect-nsfw-text.git /opt/ComfyUI/custom_nodes/comfyUI-detect-nsfw-text && \
    git -C /opt/ComfyUI/custom_nodes/comfyUI-detect-nsfw-text checkout ${NSFW_TEXT_COMMIT}
WORKDIR /opt/ComfyUI
RUN pip install -r requirements.txt
COPY requirements.txt /tmp/worker-requirements.txt
RUN pip install -r /tmp/worker-requirements.txt
COPY worker.py moderation.py comfyui_client.py queue_handler.py minio_handler.py redis_handler.py ./
COPY workflows/ ./workflows/
COPY docker/start-services.sh /opt/start-services.sh
RUN chmod +x /opt/start-services.sh && mkdir -p upload temp
CMD ["/opt/start-services.sh"]

