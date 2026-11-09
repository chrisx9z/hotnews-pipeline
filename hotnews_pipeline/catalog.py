from __future__ import annotations

import html
import json
import os
from pathlib import Path

from .models import Candidate


def _video_src(media_path: str, output: Path) -> str:
    if not media_path:
        return ""
    path = Path(media_path).resolve()
    try:
        return Path(os.path.relpath(path, output.parent.resolve())).as_posix()
    except ValueError:
        return path.as_uri()


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "N/A"
    total = int(round(seconds))
    mins, secs = divmod(total, 60)
    if mins >= 60:
        hours, mins = divmod(mins, 60)
        return f"{hours:d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def write_catalog(candidates: list[Candidate], output: Path, limit: int = 50) -> Path:
    selected = candidates[:limit]
    cards = []
    platforms = sorted({c.platform for c in selected if c.platform})
    for index, candidate in enumerate(selected, 1):
        title = html.escape(candidate.title or "(không có tiêu đề)")
        author = html.escape(candidate.author or "ẩn danh")
        source = html.escape(candidate.source_url, quote=True)
        video = html.escape(_video_src(candidate.media_path, output), quote=True)
        has_media = "1" if (candidate.media_path and Path(candidate.media_path).exists()) else "0"
        duration_label = _format_duration(candidate.duration_sec)
        tags_html = "".join(
            f"<span class='tag'>#{html.escape(tag)}</span>"
            for tag in candidate.tags[:6]
        )
        if candidate.source_keyword:
            tags_html = f"<span class='tag kw'>🔍 {html.escape(candidate.source_keyword)}</span>" + tags_html
        search_blob = html.escape(
            f"{candidate.title} {candidate.description} {candidate.author} {candidate.source_keyword} {' '.join(candidate.tags)}".lower(),
            quote=True,
        )
        extra_metrics = []
        if candidate.collects > 0:
            extra_metrics.append(f"⭐ {candidate.collects:,.0f} lưu")
        if candidate.views > 0:
            extra_metrics.append(f"👁️ {candidate.views:,.0f} xem")
        extra_str = (" · " + " · ".join(extra_metrics)) if extra_metrics else ""
        cards.append(
            f"""<article class='card' data-id='{html.escape(candidate.candidate_id, quote=True)}' data-platform='{html.escape(candidate.platform, quote=True)}' data-has-media='{has_media}' data-hot='{candidate.hot_score:.4f}' data-likes='{candidate.likes:.0f}' data-shares='{candidate.shares:.0f}' data-duration='{candidate.duration_sec:.1f}' data-published='{html.escape(candidate.published_at, quote=True)}' data-search='{search_blob}'>
<div class='head'>
  <label class='pick-label'><input type='checkbox' class='pick' value='{html.escape(candidate.candidate_id, quote=True)}' onchange='updateSelectionCount()'> Chọn</label>
  <div class='badges'>
    <span class='badge platform'>{html.escape(candidate.platform.upper())}</span>
    <span class='badge duration'>⏱ {duration_label}</span>
    <span class='badge hot'>#{index} · 🔥 {candidate.hot_score:.2f}</span>
  </div>
</div>
<h2>{title}</h2>
<div class='meta'>👤 {author} · 👍 {candidate.likes:,.0f} likes · 💬 {candidate.comments:,.0f} comments · ↗️ {candidate.shares:,.0f} shares{extra_str}<br><small>🕒 {html.escape(candidate.published_at)}</small></div>
{f"<div class='tags'>{tags_html}</div>" if tags_html else ""}
<video controls preload='metadata' src='{video}'></video>
<div class='links'><a href='{source}' target='_blank' rel='noopener'>🔗 Mở nguồn gốc</a><code>{html.escape(candidate.media_path or '(chưa có file video)')}</code></div>
</article>"""
        )

    platform_options = "".join(
        f"<option value='{html.escape(p, quote=True)}'>{html.escape(p.upper())}</option>"
        for p in platforms
    )
    payload = json.dumps([candidate.as_mapping() for candidate in selected], ensure_ascii=False).replace("</", "<\\/")
    document = f"""<!doctype html><html lang='vi'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Hot News China Catalog</title><style>
body{{font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;background:#f4f6f9;color:#17202a}}
header{{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px}}
h1{{margin:0;font-size:24px}}
.toolbar{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:#fff;padding:12px 16px;border-radius:12px;border:1px solid #dfe3e8;margin-bottom:18px;box-shadow:0 1px 4px #0000000a}}
.toolbar input[type='search'],.toolbar select{{padding:8px 12px;border:1px solid #cbd2d9;border-radius:8px;font-size:13px}}
.toolbar input[type='search']{{min-width:240px;flex:1}}
button{{padding:9px 14px;border:1px solid #cbd2d9;border-radius:8px;background:#fff;cursor:pointer;font-weight:600;font-size:13px;transition:all .15s}}
button:hover{{background:#f0f4f8}}
button.primary{{background:#0f62fe;color:#fff;border-color:#0f62fe}}
button.primary:hover{{background:#0043ce}}
.counter{{font-weight:700;color:#0f62fe;padding:0 8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px}}
.card{{background:#fff;border:1px solid #dfe3e8;border-radius:12px;padding:14px;box-shadow:0 2px 8px #0000000c;display:flex;flex-direction:column}}
.card.selected{{border-color:#0f62fe;box-shadow:0 0 0 2px #0f62fe33}}
.head{{display:flex;justify-content:space-between;align-items:center;gap:8px;color:#555}}
.pick-label{{font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px}}
.badges{{display:flex;gap:6px;flex-wrap:wrap}}
.badge{{font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;background:#eef2f6;color:#344054}}
.badge.platform{{background:#e0f2fe;color:#0369a1}}
.badge.duration{{background:#f3e8ff;color:#6b21a8}}
.badge.hot{{background:#ffedd5;color:#c2410c}}
h2{{font-size:16px;line-height:1.38;margin:10px 0 6px}}
.meta{{color:#475467;font-size:13px;margin:4px 0 10px}}
.tags{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}}
.tag{{font-size:11px;background:#f2f4f7;color:#344054;padding:2px 8px;border-radius:6px}}
.tag.kw{{background:#dcfce7;color:#15803d;font-weight:600}}
video{{width:100%;max-height:460px;background:#0b0f19;border-radius:8px;margin-top:auto}}
.links{{display:flex;gap:10px;align-items:center;margin-top:10px;justify-content:space-between}}
code{{font-size:11px;word-break:break-all;color:#667085;background:#f8f9fa;padding:3px 6px;border-radius:4px}}
a{{color:#0f62fe;text-decoration:none;font-weight:600;white-space:nowrap}}
a:hover{{text-decoration:underline}}
</style></head><body>
<header>
  <div>
    <h1>🔥 Hot News China Catalog ({len(selected)} video)</h1>
    <p style='margin:4px 0 0;color:#475467'>Xem trước video tin nóng, lọc theo nền tảng/từ khóa, chọn video cần Vietsub + TTS rồi tải <code>selected-candidates.jsonl</code>.</p>
  </div>
  <div class='counter' id='selCount'>Đã chọn: 0 / {len(selected)}</div>
</header>
<div class='toolbar'>
  <input id='searchInput' type='search' placeholder='Tìm theo tiêu đề, tác giả, hashtag, từ khóa...' oninput='applyFilters()'>
  <select id='platformSelect' onchange='applyFilters()'>
    <option value=''>Tất cả nền tảng</option>
    {platform_options}
  </select>
  <select id='sortSelect' onchange='applyFilters()'>
    <option value='hot'>Sắp xếp: Điểm Hot giảm dần</option>
    <option value='newest'>Sắp xếp: Mới nhất</option>
    <option value='likes'>Sắp xếp: Lượt thích cao nhất</option>
    <option value='shares'>Sắp xếp: Lượt chia sẻ cao nhất</option>
    <option value='duration'>Sắp xếp: Thời lượng ngắn → dài</option>
  </select>
  <button class='primary' onclick='downloadSelected()'>⬇ Tải danh sách đã chọn</button>
  <button onclick='copyRunCommand()'>📋 Copy lệnh chạy Localizer</button>
  <button onclick='toggleVisible(true)'>Chọn tất cả đang lọc</button>
  <button onclick='toggleVisible(false)'>Bỏ chọn</button>
</div>
<div class='grid' id='cardGrid'>{''.join(cards)}</div>
<script>
const rows={payload};
function updateSelectionCount(){{
  const picks=[...document.querySelectorAll('.pick')];
  const checked=picks.filter(x=>x.checked);
  picks.forEach(x=>x.closest('.card').classList.toggle('selected',x.checked));
  document.getElementById('selCount').textContent=`Đã chọn: ${{checked.length}} / ${{rows.length}}`;
}}
function toggleVisible(state){{
  document.querySelectorAll('.card').forEach(card=>{{
    if(card.style.display!=='none'){{
      const cb=card.querySelector('.pick');
      if(cb) cb.checked=state;
    }}
  }});
  updateSelectionCount();
}}
function applyFilters(){{
  const q=(document.getElementById('searchInput').value||'').trim().toLowerCase();
  const plat=document.getElementById('platformSelect').value;
  const sortBy=document.getElementById('sortSelect').value;
  const grid=document.getElementById('cardGrid');
  const cards=[...grid.querySelectorAll('.card')];
  cards.forEach(c=>{{
    const matchQ=!q||(c.dataset.search||'').includes(q);
    const matchP=!plat||c.dataset.platform===plat;
    c.style.display=(matchQ&&matchP)?'':'none';
  }});
  cards.sort((a,b)=>{{
    if(sortBy==='likes') return parseFloat(b.dataset.likes)-parseFloat(a.dataset.likes);
    if(sortBy==='shares') return parseFloat(b.dataset.shares)-parseFloat(a.dataset.shares);
    if(sortBy==='duration') return (parseFloat(a.dataset.duration)||99999)-(parseFloat(b.dataset.duration)||99999);
    if(sortBy==='newest') return (b.dataset.published||'').localeCompare(a.dataset.published||'');
    return parseFloat(b.dataset.hot)-parseFloat(a.dataset.hot);
  }});
  cards.forEach(c=>grid.appendChild(c));
}}
function downloadSelected(){{
  const ids=new Set([...document.querySelectorAll('.pick:checked')].map(x=>x.value));
  if(!ids.size){{alert('Vui lòng tích chọn ít nhất 1 video trước khi tải!');return;}}
  const text=rows.filter(x=>ids.has(x.candidate_id)).map(x=>JSON.stringify(x)).join('\\n');
  const blob=new Blob([text+'\\n'],{{type:'application/jsonl'}});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='selected-candidates.jsonl';
  a.click();
  URL.revokeObjectURL(a.href);
}}
function copyRunCommand(){{
  const cmd='python -m hotnews_pipeline.pipeline run-selected --selected selected-candidates.jsonl --jobs-dir jobs-selected --config config.example.json';
  navigator.clipboard.writeText(cmd).then(()=>alert('Đã copy lệnh PowerShell:\\n\\n'+cmd));
}}
</script></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output
