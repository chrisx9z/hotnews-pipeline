# Hot News Pipeline (`hotnews_pipeline` v0.2.0)

Bộ điều phối tự động hoá luồng **MediaCrawler (Douyin / Xiaohongshu / Bilibili / Kuaishou / Weibo) → Chuẩn hoá & Chấm điểm độ nóng → Duyệt chọn qua Catalog HTML → AI Video Localizer (Whisper + Dịch Vietsub + VieNeu-TTS + Ducking/Mastering) → MP4 hoàn chỉnh**.

---

## 1. Kiến trúc & Điểm mới bản v0.2.0

1. **Tương thích MediaCrawler mới nhất (`NanmiCoder/MediaCrawler` 2026-11)**:
   - Hỗ trợ đồng thời cấu trúc thư mục media mới (`data/{dy|xhs|bili|ks|wb}/media/{id}/video.mp4`, `001_live.mp4` từ `DOWNLOAD_LIVE_PHOTO=True`) và cấu trúc cũ (`data/{platform}/videos/{id}/`).
   - Hỗ trợ thêm nền tảng **Bilibili (`bili`)** cạnh Douyin (`dy`), Xiaohongshu (`xhs`), Kuaishou (`ks`), Weibo (`wb`).
   - Tự động gắn phiên Chrome CDP đang đăng nhập sẵn (bỏ qua bước quét lại QR khi trình duyệt đã có cookie đăng nhập trên Douyin/Xiaohongshu/Bilibili).
   - Tự động đo `duration_sec` thật từ file `.mp4` qua `ffprobe` khi JSONL của MediaCrawler không trả thời lượng.
2. **Chấm điểm & Khử trùng lặp thông minh (`ranking.py`, `pipeline.py`)**:
   - Công thức điểm kết hợp `likes`, `collects` (lượt lưu), `comments`, `shares`, `views`, hệ số độ mới (`freshness` bán rã 18h), hệ số thời lượng phù hợp Shorts/Reels (`15s–180s`), và điểm cộng từ khoá chủ đề (`--keywords`).
   - Khử trùng lặp theo `source_url`, đường dẫn `media_path`, và tiêu đề chuẩn hoá xuyên nền tảng (tránh xử lý lại cùng 1 video đăng chéo trên Douyin và Xiaohongshu).
   - Cho phép loại trừ các video đã chạy xong ở đợt trước qua `--exclude-jobs-dir`.
3. **Catalog duyệt chọn trực quan (`hot-catalog.html`)**:
   - Tìm kiếm tức thời theo tiêu đề / tác giả / hashtag, lọc theo nền tảng, lọc chỉ hiện video đã có `.mp4` trên đĩa, sắp xếp theo Điểm nóng / Mới nhất / Lượt tim / Lượt share / Thời lượng.
   - Tích hợp nút **Tải danh sách đã chọn (`selected-candidates.jsonl`)** và **Copy lệnh chạy Localizer (`run-selected`)**.
4. **Đồng bộ `AI-Video-Localizer` mới nhất (`D:\AI-Video-Localizer`)**:
   - Tự động nhận diện `D:\AI-Video-Localizer` và kích hoạt `workflow_profile = "basic"`, `basic_gap_recheck = True`, `tts_fit_to_subtitle_slot = True` (`tts_max_fit_speed = 1.15`), `audio_mode = "custom"` (`original_volume_percent = 27`), cùng kiểm tra `voice_presence_check` ở file xuất.

---

## 2. Quy trình vận hành nhanh

### Bước 1: Crawl video từ Douyin / Xiaohongshu / Bilibili (hoặc chuẩn hoá dữ liệu đã tải)

```powershell
# Cách 1: Gọi trực tiếp lệnh crawl + normalize tích hợp
python -m hotnews_pipeline.pipeline crawl `
  --crawler-root work\MediaCrawler `
  --platform dy `
  --keywords "机器人,AI大模型" `
  --output work\crawler-real.jsonl

# Cách 2: Chỉ chuẩn hoá dữ liệu MediaCrawler đã tải sẵn (1 nền tảng hoặc tất cả nền tảng)
python -m hotnews_pipeline.pipeline normalize `
  --crawler-root work\MediaCrawler `
  --platform all `
  --all-files `
  --output work\crawler-real.jsonl
```

### Bước 2: Lọc, khử trùng lặp và xếp hạng độ nóng (`ingest`)

```powershell
python -m hotnews_pipeline.pipeline ingest `
  --input work\crawler-real.jsonl `
  --output work\ranked-real.jsonl `
  --min-duration 5 `
  --max-duration 1800 `
  --require-media `
  --exclude-jobs-dir work\jobs-real
```

### Bước 3: Mở bảng Catalog HTML để xem trước & tích chọn video muốn Việt hoá

```powershell
python -m hotnews_pipeline.pipeline catalog `
  --ranked work\ranked-real.jsonl `
  --output work\hot-catalog.html `
  --limit 50
Invoke-Item work\hot-catalog.html
```

Sau khi tích chọn các video ưng ý và bấm **Tải danh sách đã chọn** (`selected-candidates.jsonl`):

### Bước 4: Chạy Việt hoá tự động qua `AI-Video-Localizer`

```powershell
# Chạy một lệnh duy nhất từ file selected-candidates.jsonl đã chọn:
python -m hotnews_pipeline.pipeline run-selected `
  --selected "$HOME\Downloads\selected-candidates.jsonl" `
  --jobs-dir work\jobs-selected `
  --config config.example.json

# Kiểm tra trạng thái các job:
python -m hotnews_pipeline.pipeline status --jobs-dir work\jobs-selected
```
