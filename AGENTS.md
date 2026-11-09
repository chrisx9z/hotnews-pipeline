# QUY TẮC BẮT BUỘC VỀ TỔ CHỨC FILE & THƯ MỤC DỰ ÁN (WORKSPACE FILE & FOLDER ORGANIZATION RULE)

## 1. NGUYÊN TẮC CỐT LÕI (MANDATORY FOR ALL AGENTS & SUBAGENTS)
Mọi Agent (Antigravity, OpenAI Codex, Claude, Subagents) khi làm việc trên ổ `D:\` và bất kỳ dự án nào trong `D:\Vibe Code` **BẮT BUỘC** phải tuân thủ tuyệt đối các nguyên tắc sau:

1. **CẤM XẢ FILE HOẶC THƯ MỤC RÁC RA `D:\`, `D:\Vibe Code`, HOẶC THƯ MỤC GỐC DỰ ÁN**:
   - **TUYỆT ĐỐI KHÔNG** tạo hoặc để lại các file báo cáo (`.md`, `.csv`, `.json`, `.txt`), gói nén bàn giao (`.zip`), file cài đặt (`.apk`, `.aab`, `.exe`), log test (`.log`, `.utrace`), hoặc script tạm ở ngoài `D:\`, `D:\Vibe Code\`, hay `D:\Vibe Code\Antigravity\`.
   - Khi làm việc trên dự án nào, **100% file và thư mục sinh ra phải nằm bên trong đúng thư mục của dự án đó** (`D:\Vibe Code\<Tên_Dự_Án>\`).

2. **MỌI FILE VÀ THƯ MỤC TẠO MỚI PHẢI ĐẶT TRONG THƯ MỤC CON CÓ TRẬT TỰ LOGIC**:
   Bên trong mỗi dự án `D:\Vibe Code\<Tên_Dự_Án>\`, **TUYỆT ĐỐI KHÔNG** tạo tràn lan các file hoặc **thư mục đợt mới** (`*DELIVERY*`, `*HANDOFF*`, `*SPEC*`, `*REVIEW*`, `*SCREENSHOTS*`, `*LOGS*`, `R1..R12`, `MB01..MB10`, `MEGA*`, `Gate*`, `Phase*`) ngay tại gốc dự án. Mọi file và thư mục mới tạo đều phải gom vào đúng thư mục con chức năng:
   - **Báo cáo, QA, Audit, Acceptance Matrix, Manifest, Evidence** (`.md`, `.csv`, `.json`, `.txt`, thư mục đợt báo cáo) -> đặt vào `reports/` (hoặc `Reports/` / `05_QA_RELEASE/Reports/` / `00_REVIEW/`).
   - **Gói nén bàn giao / Thư mục Delivery / Handoff / Release** (`.zip` và các thư mục `*_DELIVERY`, `*_HANDOFF`) -> đặt vào `releases/` (hoặc `Releases/` / `Builds/Releases/` / `RELEASE/` / `00_REVIEW/Releases/`).
   - **Bản build thực thi** (`.apk`, `.aab`, `.exe`) -> đặt vào `Builds/Android/`, `Builds/Windows/`, hoặc `dist/`.
   - **Tài liệu thiết kế / Đặc tả (`*_SPEC`, Design Kits)** -> đặt vào `docs/` (hoặc `docs/specs/`, `_design_kit/`).
   - **Log kiểm thử / Ảnh chụp màn hình QA (`*_SCREENSHOTS`, `*_LOGS`)** -> đặt vào `qa/`, `logs/`, hoặc `reports/screenshots/`.
   - **Script kiểm thử / công cụ phụ trợ** -> đặt vào `scripts/` hoặc `tools/`.

3. **TỰ ĐỘNG XOÁ FILE & THƯ MỤC CỦA ĐỢT CŨ ĐÃ LỖI THỜI**:
   - Khi hoàn thành một đợt (Batch / Gate / Wave / Round / RC) mới (ví dụ `MB09` thay cho `MB08`, `R11` thay cho `R10`, `G01` thay cho `MEGA08`, `RC11` thay cho `RC10`, `C2J` thay cho `C2I`), **PHẢI XOÁ NGAY** các gói `.zip`, bản `.apk`, file `.blend` checkpoint trung gian, và thư mục báo cáo/delivery của đợt cũ đã lỗi thời.
   - Xoá ngay các thư mục staging tạm (`scratch/`, `temp/`, `tmp/`, `*_extracted/`), các file trace/log dung lượng lớn (`.utrace`, `.dmp`), và file backup tự động (`.blend1`, `.bak`, `.old`) ngay sau khi hoàn tất đóng gói.

4. **CẤM HARDCODE `REPO_ROOT.parent`, `D:\Vibe Code\`, HOẶC ĐƯỜNG DẪN CŨ TRONG SCRIPT (`.py`, `.ps1`, `.bat`)**:
   - Khi viết hoặc chạy các script đóng gói (`package_*.py`, `generate_*_manifest.py`, `pack_*.py`), **TUYỆT ĐỐI KHÔNG** dùng `parent_dir = REPO_ROOT.parent` hay xuất file `.zip` ra `D:\Vibe Code\`. Mọi file `.zip` bắt buộc phải xuất vào `Releases/` (hoặc `Builds/Releases/`, `releases/`, `RELEASE/`, `00_REVIEW/Releases/`).
   - Đường dẫn chuẩn đã cố định:
     - **Phá Giới Giả (Godot)**: `D:\Vibe Code\Pha Gioi Gia\PhaGioiGia_Godot` (TUYỆT ĐỐI KHÔNG tạo lại `D:\Vibe Code\PhaGioiGia_Godot`).
     - **Unity Editors**: `D:\App\UnityEditors` (TUYỆT ĐỐI KHÔNG dùng `D:\UnityEditors`).
     - **Python Venv dùng chung**: `D:\Runtime\.venv` (TUYỆT ĐỐI KHÔNG tạo `D:\.venv`).

---

## 2. BẢNG ÁNH XẠ ĐƯỜNG DẪN CHUẨN CHO CÁC DỰ ÁN (`D:\Vibe Code`)

| Tên Dự Án | Thư Mục Gốc Chính Thức | Nơi Lưu Báo Cáo, Thư Mục Đợt Mới & Gói Bàn Giao (`.zip` / `.apk`) |
| :--- | :--- | :--- |
| **VietFlow** | `D:\Vibe Code\vietflow` | Báo cáo: `reports/` \| Gói `.zip`: `releases/` \| Đặc tả: `docs/specs/` |
| **PartyVerse** | `D:\Vibe Code\PartyVerse` | Báo cáo: `05_QA_RELEASE/Reports/` \| APK: `Builds/Android/` \| Gói `.zip`: `Builds/Releases/` |
| **The 31st Floor** | `D:\Vibe Code\The31stFloor` | Báo cáo: `Reports/` \| APK: `Builds/Android/` \| Handoff: `_handoff/` \| Docs: `Docs/` |
| **Phá Giới Giả (Godot / RealmBreaker)** | `D:\Vibe Code\Pha Gioi Gia\PhaGioiGia_Godot` | Báo cáo: `Reports/` \| Gói `.zip`: `Releases/` \| Design Kit: `_design_kit/` |
| **Phá Giới Giả (Rust / Voxel / Blender)** | `D:\Vibe Code\Pha Gioi Gia` & `D:\Vibe Code\Antigravity\XianxiaBlender` | Scene 3D: `blender/` \| Render: `renders/` \| Docs: `docs/` |
| **Hoạt Hình 2D (Híu Béo / Xuyên Không)** | `D:\Vibe Code\Hoat Hinh 2D` | Báo cáo & Audit: `00_REVIEW/` \| Gói `.zip` & Delivery: `00_REVIEW/Releases/` |
| **Still Alive (SafeCheck)** | `D:\Vibe Code\Still Alive` | Handoff & `.zip`: `Releases/` \| Script: `scripts/` |
| **KamarGO** | `D:\Vibe Code\KamarGO` | Báo cáo QA: `QA/` \| Gói `.zip`: `RELEASE/` \| Store Proof: `STORE/` \| Docs: `docs/` |
| **Kinh Dịch** | `D:\Vibe Code\Kinh Dịch` | Báo cáo: `reports/` \| Release & Delivery: `RELEASE/` \| QA & Logs: `qa/` |
| **Auto SEO GEO** | `D:\Vibe Code\Auto SEO GEO` | Docs & Rules: `docs/` \| Bài xuất bản & Báo cáo: `output/` \| Script: `scripts/` |
| **M Auto Pilot** | `D:\Vibe Code\M-Auto-Pilot` | Bản chạy: `dist/` \| Script: `scripts/` \| Model chung: `D:\Runtime\models` |
| **AI Video Localizer** | `D:\AI-Video-Localizer` | Voice: `voices/` \| Output: `outputs/` |
| **Qwen Image Studio** | `D:\Vibe Code\Qwen Image Studio` | Ảnh xuất: `outputs/` \| Model chung: `D:\Runtime\models\qwen-image-2.1` |
| **Bot Trading** | `D:\Vibe Code\Bot Trading` | Báo cáo: `reports/` \| Log: `logs/` \| Script: `scripts/` |
| **Cut Shorts Video** | `D:\Vibe Code\Cut Shorts Video` | Docs: `docs/` \| Script: `scripts/` |
| **RVC Project** | `D:\Vibe Code\RVC Project` | Docs: `docs/` \| Output: `workspace/` |
