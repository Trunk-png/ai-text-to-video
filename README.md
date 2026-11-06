# Pika H3 Flex text-to-video worker

Docker worker theo format `i2i-2.1`, không có UI. Luồng xử lý:

`RabbitMQ -> ComfyUI text-to-video -> tải video tạm -> NSFW hậu kiểm -> MinIO -> RabbitMQ result`

Worker chỉ dùng workflow `workflows/text_to_video.json`, được lấy nguyên bản từ `t2v/workflow_text_only.json`. Không có `demo_app` hoặc web UI.

Video chỉ được upload sau khi moderation thành công. Moderation dùng `nsfw-image-detector==0.1.2`, lấy ngẫu nhiên tối đa 3 frame khác nhau mỗi giây và chặn khi `LOW >= 0.8`. Thứ tự fallback là CUDA bfloat16, CUDA float16, rồi CPU float32.

## Chuẩn bị

```bash
cd /home/aiml03/apps/pika-flex-h3/t2v-2.1
cp .env.example .env
# điền RabbitMQ, Redis và MinIO trong .env
bash host/download_models.sh
bash host/clone_custom_nodes.sh
```

## Chạy

```bash
docker compose build
docker compose up -d
docker compose logs -f ai-worker
```

`nsfw-image-detector` tự tải/cache model mặc định `Freepik/nsfw_image_detector` trong lần khởi tạo đầu tiên, vì vậy container cần truy cập Hugging Face ở lần chạy đầu.

## Request

Publish vào exchange `TEXT_TO_VIDEO_EXCHANGE_REQUEST` với header `type=process_text_to_video`:

```json
{
  "request_id": "715ce788-7ae2-43d6-9025-b25d6bb42082",
  "prompt": "A cinematic aerial shot of a tropical island at sunrise",
  "duration": 5,
  "seed": 123456
}
```

`request_id` và `prompt` là bắt buộc. Prompt chỉ chấp nhận tiếng Anh; ngôn ngữ khác bị chặn trước workflow và trả lỗi `422` với trường `error` là `language not support, only support english`. `duration` tùy chọn, từ 1 đến 15 giây; `seed` tùy chọn.

Result được publish vào exchange `TEXT_TO_VIDEO_EXCHANGE_RESULT`, queue `TEXT_TO_VIDEO_QUEUE_RESULT`. Thành công trả `output_url`; NSFW trả status code 403 và `error.type=nsfw_content_detected`. Nếu moderation lỗi kỹ thuật, worker fail closed và không upload video.

Result giữ cùng envelope với worker `i2i-2.1`: `request_id`, `feature_code`, `created_at`, `metadata`, `status`, `output_url`, `server_information`, `error`, `is_success`, `metric` và `timestamp`. Khi lỗi có thêm `status_code`.

# ai-text-to-video
