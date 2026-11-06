set dotenv-load := true

build:
    docker compose build

up:
    docker compose up -d

down:
    docker compose down

logs:
    docker compose logs -f ai-worker

models:
    bash host/download_models.sh

