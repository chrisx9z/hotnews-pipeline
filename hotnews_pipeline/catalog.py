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
        return Path(os.path.relpath(path, output.parent)).as_posix()
    except ValueError:
        return path.as_uri()


def write_catalog(candidates: list[Candidate], output: Path, limit: int = 50) -> Path:
    selected = candidates[:limit]
    cards = []
    for index, candidate in enumerate(selected, 1):
        title = html.escape(candidate.title or "(không có tiêu đề)")
        source = html.escape(candidate.source_url, quote=True)
        video = html.escape(_video_src(candidate.media_path, output), quote=True)
        cards.append(
            f"""<article class='card'><div class='head'><label><input type='checkbox' class='pick' value='{html.escape(candidate.candidate_id, quote=True)}'> Chọn</label><span>#{index} · Hot {candidate.hot_score:.2f}</span></div><h2>{title}</h2><div class='meta'>{html.escape(candidate.platform)} · {candidate.likes:,.0f} likes · {candidate.comments:,.0f} comments · {candidate.shares:,.0f} shares · {html.escape(candidate.published_at)}</div><video controls preload='metadata' src='{video}'></video><div class='links'><a href='{source}' target='_blank'>Mở nguồn</a><code>{html.escape(candidate.media_path)}</code></div></article>"""
        )
    payload = json.dumps([candidate.as_mapping() for candidate in selected], ensure_ascii=False).replace("</", "<\\/")
    document = f"""<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Hot News Catalog</title><style>body{{font:14px system-ui;margin:24px;background:#f5f6f8;color:#17202a}}button{{padding:10px 14px;margin:0 8px 18px 0;cursor:pointer}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px}}.card{{background:white;border:1px solid #ddd;border-radius:12px;padding:14px;box-shadow:0 2px 8px #0001}}.head{{display:flex;justify-content:space-between;color:#555}}h2{{font-size:18px;line-height:1.35}}.meta{{color:#667085;margin:8px 0 12px}}video{{width:100%;max-height:460px;background:#111}}.links{{display:flex;gap:10px;align-items:center;margin-top:10px}}code{{font-size:11px;word-break:break-all;color:#667085}}a{{color:#1261a0}}</style></head><body><h1>Hot News Catalog</h1><p>Chọn video cần Vietsub/TTS, sau đó tải danh sách lựa chọn.</p><button onclick='downloadSelected()'>Tải danh sách đã chọn</button><button onclick='document.querySelectorAll(".pick").forEach(x=>x.checked=true)'>Chọn tất cả</button><button onclick='document.querySelectorAll(".pick").forEach(x=>x.checked=false)'>Bỏ chọn</button><div class='grid'>{''.join(cards)}</div><script>const rows={payload};function downloadSelected(){{const ids=new Set([...document.querySelectorAll('.pick:checked')].map(x=>x.value));const text=rows.filter(x=>ids.has(x.candidate_id)).map(x=>JSON.stringify(x)).join('\\n');const blob=new Blob([text+'\\n'],{{type:'application/jsonl'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='selected-candidates.jsonl';a.click();URL.revokeObjectURL(a.href);}}</script></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output
