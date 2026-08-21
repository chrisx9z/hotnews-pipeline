# Hot News Pipeline

Bộ điều phối local cho luồng MediaCrawler → Whisper → Vietsub/TTS → AI Video Localizer → MP4. Mã nguồn không phụ thuộc API cố định của Localizer; các công cụ local được gọi qua command template trong `config.example.json`.

## Input

`JSONL`, mỗi dòng là một video. Các khóa chính: `platform`, `source_url`, `media_path`, `title`, `author`, `published_at`, `likes`, `comments`, `shares`, `duration_sec`. Bộ đọc cũng nhận một số tên khóa phổ biến của MediaCrawler như `aweme_id`, `note_id`, `liked_count`, `comment_count`, `create_time`.

`config.example.json` chứa command mẫu cho AI Video Localizer. Hãy thay `C:\path\to\AI-Video-Localizer` bằng đường dẫn Localizer trên máy của bạn. Adapter tự tạo `VideoProject` trong thư mục `work\projects` của Localizer, lưu metadata nguồn cạnh project và ghi lại output vào manifest.

## Chạy

```powershell
python -m hotnews_pipeline.pipeline ingest --input examples/crawler.example.jsonl --output ranked.jsonl --max-duration 1800
python -m hotnews_pipeline.pipeline jobs --ranked ranked.jsonl --output-dir jobs --limit 10
python -m hotnews_pipeline.pipeline run --jobs-dir jobs --config config.example.json
```

Có thể chạy thử một video trước: `python -m hotnews_pipeline.pipeline run --jobs-dir jobs-real --config config.example.json --limit 1`. Bỏ `--limit` khi muốn chạy toàn bộ job.

`crawler.example.jsonl` chỉ là cấu trúc mẫu. Trước khi chạy `jobs`/`run`, thay `media_path` bằng đường dẫn video thật đã tải về. Nếu dùng dữ liệu thật, mỗi dòng JSONL cần có ít nhất `media_path`, `source_url` và `title`.

Nếu dùng bản MediaCrawler trong `work\MediaCrawler`, có thể chuẩn hóa trực tiếp JSONL native:

```powershell
python -m hotnews_pipeline.pipeline normalize --crawler-root ..\..\work\MediaCrawler --platform dy --output crawler-real.jsonl
python -m hotnews_pipeline.pipeline ingest --input crawler-real.jsonl --output ranked-real.jsonl --max-duration 1800
```

MediaCrawler phải được chạy với chế độ tải media bật; nếu chỉ lưu metadata thì `media_path` sẽ trống và job sẽ bị chặn.

`jobs` mặc định từ chối `media_path` không tồn tại để tránh chạy nhầm dữ liệu mẫu. Chỉ dùng `--allow-missing-media` khi muốn tạo manifest xem trước.

Để chỉ xem và chọn video trước khi xử lý:

```powershell
python -m hotnews_pipeline.pipeline catalog --ranked ranked-real.jsonl --output hot-catalog.html --limit 50
Invoke-Item hot-catalog.html
```

Trong catalog, chọn video rồi bấm **Tải danh sách đã chọn**. File `selected-candidates.jsonl` tải xuống có thể dùng làm input cho pipeline xử lý sau đó.

Các placeholder được hỗ trợ: `{input}`, `{manifest}`, `{transcript}`, `{vietsub}`, `{tts_audio}`, `{localized_video}`, `{rendered_video}`. Nếu bỏ trống command, stage tương ứng được giữ ở trạng thái `pending` để duyệt hoặc chạy thủ công.

## Hợp đồng Localizer

Localizer nhận đường dẫn `manifest.json`. Manifest chứa candidate, đường dẫn transcript, Vietsub, TTS, video localized và rendered. Hãy đặt command thực tế của phần mềm đã phát triển trước đó vào `commands.localizer`; `commands.vietsub_tts` cũng nhận cùng manifest hoặc có thể gọi một runner riêng. Các command để `null` sẽ giữ stage ở trạng thái `pending`.
