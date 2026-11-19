#!/usr/bin/env python3
"""Pha 2 — công cụ xem ảnh ứng viên (được dùng Pillow; KHÔNG phải validator).

    python tools/review_viewer.py runs/r1007/delivery runs/r1007/candidates.json \
        --out runs/r1007/review --reviewers "Son,Duc,Thai,Thanh,Thuy"
    # rồi mở runs/r1007/review/index.html bằng trình duyệt

Với mỗi ứng viên, vẽ một tấm gồm 3 khung:
  [ảnh đầy đủ + mọi box]  [vùng nghi vấn phóng to, KHÔNG vẽ gì]  [vùng nghi vấn phóng to + box/viền mask]
  - box detection: đỏ (box bị nghi), xám (box khác) — nhãn "det:<lớp>"
  - segment panoptic bị nghi: phủ xanh lơ + viền — nhãn "pan:<lớp>"
Khung giữa để NHÌN VẬT thật mà không bị lớp vẽ che: chính ảnh cho biết nguồn nào sai.

index.html: chia hàng đợi cho từng người, mỗi thẻ có chọn loại lỗi / confirmed / rejected / ghi chú.
Nút "Xuất review_log.csv" ghi file đúng mẫu templates/review_log.csv. Mỗi người xuất phần của mình,
người chốt dùng "Nhập CSV" để gộp rồi xuất bản cuối. Trang KHÔNG điền sẵn kết luận nào:
verdict và ghi chú phải do người xem ảnh viết (RULES.md).
"""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

TYPES = ["class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge"]
FONT_PATHS = ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf"]


def font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def read_boxes(label: Path, classes: dict[int, str], w: int, h: int) -> list[dict]:
    out = []
    if not label.is_file():
        return out
    for n, line in enumerate(label.read_text(encoding="utf-8").splitlines()):
        p = line.split()
        if len(p) < 5:
            continue
        try:
            cid, x, y, bw, bh = int(p[0]), *map(float, p[1:5])
        except ValueError:
            continue
        out.append({"line": n, "class": classes.get(cid, f"?{cid}"),
                    "xyxy": [(x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h]})
    return out


def seg_mask(mask_rgb: Image.Image, sid: int) -> Image.Image:
    """Ảnh 'L' 255 ở pixel thuộc segment sid."""
    r, g, b = mask_rgb.split()
    want = (sid & 255, (sid >> 8) & 255, (sid >> 16) & 255)
    parts = [ch.point(lambda v, t=t: 255 if v == t else 0) for ch, t in zip((r, g, b), want)]
    return ImageChops.multiply(ImageChops.multiply(parts[0], parts[1]), parts[2])


def label(draw: ImageDraw.ImageDraw, xy, text, fill, f):
    x, y = xy
    l, t, r, b = draw.textbbox((x, y), text, font=f)
    y = max(0, y - (b - t) - 4)
    draw.rectangle([x, y, x + (r - l) + 6, y + (b - t) + 4], fill=fill)
    draw.text((x + 3, y + 1), text, fill="white", font=f)


def overlay(img: Image.Image, boxes, hot_lines: set[int], segs: list[tuple[str, Image.Image]], scale: float,
            offset=(0, 0), f=None) -> Image.Image:
    out = img.convert("RGB").copy()
    ox, oy = offset
    # segment: phủ màu + viền
    for name, m in segs:
        tint = Image.new("RGB", out.size, (0, 200, 255))
        out = Image.composite(Image.blend(out, tint, 0.45), out, m)
        edge = m.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
        out.paste((0, 255, 255), mask=edge)
    d = ImageDraw.Draw(out)
    lw = max(2, int(round(2 * scale)))
    for b in boxes:
        x0, y0, x1, y1 = [(v - o) * scale for v, o in zip(b["xyxy"], (ox, oy, ox, oy))]
        hot = b["line"] in hot_lines
        d.rectangle([x0, y0, x1, y1], outline=(255, 40, 40) if hot else (170, 170, 170), width=lw + (1 if hot else 0))
        if hot or f is not None:
            label(d, (max(0, x0), max(0, y0)), f"det:{b['class']}", (200, 30, 30) if hot else (90, 90, 90), f)
    for name, m in segs:
        bb = m.getbbox()
        if bb:
            label(d, (bb[0], min(out.height - 2, bb[3] + 18)), f"pan:{name}", (0, 130, 170), f)
    return out


def render(delivery: Path, cand: dict, classes: dict[int, str], pan_index: dict, out: Path) -> None:
    stem = cand["image"]
    info = pan_index[stem]
    img_path = delivery / "images" / f"{stem}.jpg"
    img = Image.open(img_path).convert("RGB") if img_path.is_file() else Image.new("RGB", (info["width"], info["height"]), (60, 0, 0))
    mask = Image.open(delivery / "masks" / info["mask"]).convert("RGB")
    W, H = img.size
    boxes = read_boxes(delivery / "labels" / f"{stem}.txt", classes, W, H)
    hot_lines, seg_ids, region = set(), {}, []
    for s in cand["signals"]:
        for b in s.get("boxes", []):
            hot_lines.add(b["line"])
            region.append(b["xyxy"])
        for g in s.get("segments", []):
            seg_ids[g["id"]] = g["class"]
            region.append(g["xyxy"])
    segs = [(name, seg_mask(mask, sid)) for sid, name in seg_ids.items()]
    # vùng nghi vấn: hợp của box/segment, nới 30%, tối thiểu 64 px
    x0 = min(r[0] for r in region); y0 = min(r[1] for r in region)
    x1 = max(r[2] for r in region); y1 = max(r[3] for r in region)
    pw, ph = max(64, (x1 - x0)) * 0.3, max(64, (y1 - y0)) * 0.3
    crop = (int(max(0, x0 - pw)), int(max(0, y0 - ph)), int(min(W, x1 + pw)), int(min(H, y1 + ph)))
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    target = 520
    zoom = min(6.0, target / max(cw, ch))
    small_f, big_f = font(13), font(15)

    full_scale = min(1.0, 560 / max(W, H)) if max(W, H) > 560 else min(2.0, 420 / max(W, H))
    full = overlay(img, boxes, hot_lines, segs, 1.0, f=small_f)
    full = full.resize((int(W * full_scale), int(H * full_scale)), Image.LANCZOS)
    fd = ImageDraw.Draw(full)
    fd.rectangle([crop[0] * full_scale, crop[1] * full_scale, crop[2] * full_scale, crop[3] * full_scale], outline=(255, 220, 0), width=2)

    raw = img.crop(crop).resize((int(cw * zoom), int(ch * zoom)), Image.LANCZOS)
    zsegs = [(n, m.crop(crop).resize(raw.size, Image.NEAREST)) for n, m in segs]
    over = overlay(img.crop(crop).resize(raw.size, Image.LANCZOS), boxes, hot_lines, zsegs, zoom,
                   offset=(crop[0], crop[1]), f=big_f)

    pad, head = 10, 30
    tw = full.width + raw.width + over.width + 4 * pad
    th = max(full.height, raw.height) + head + pad
    sheet = Image.new("RGB", (tw, th), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 7), f"{stem}  {W}x{H}   |  1) full   2) zoom x{zoom:.1f} (raw)   3) zoom + det(red) / pan(cyan)",
           fill=(230, 230, 230), font=big_f)
    x = pad
    for part in (full, raw, over):
        sheet.paste(part, (x, head))
        x += part.width + pad
    sheet.save(out, optimize=True)


PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Review %(title)s</title>
<style>
body{font:14px/1.45 system-ui,sans-serif;margin:0;background:#f4f4f6;color:#1c1c22}
header{position:sticky;top:0;background:#1c1c22;color:#fff;padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:2}
header select,header button,header label{font:inherit}
button{padding:5px 10px;border-radius:6px;border:1px solid #888;background:#fff;cursor:pointer}
.card{background:#fff;margin:14px 16px;padding:12px 14px;border-radius:10px;box-shadow:0 1px 3px #0002}
.card.done{border-left:6px solid #2a9d5b}.card.rej{border-left:6px solid #888}
.card img{max-width:100%%;height:auto;display:block;margin:8px 0;cursor:zoom-in}
.why{margin:4px 0;padding-left:18px}.why li{margin:2px 0}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
textarea{width:min(720px,100%%);min-height:46px;font:inherit}
.who{background:#eef;border-radius:4px;padding:1px 6px}.warn{color:#b00;font-size:12px}
.guess{font-family:monospace;background:#f1efe6;padding:1px 5px;border-radius:4px}
</style></head><body>
<header><b>Review %(title)s</b> <span id="prog"></span>
<label>Người xem: <select id="me"></select></label>
<label><input type="checkbox" id="onlyMine"> chỉ hàng đợi của tôi</label>
<label><input type="checkbox" id="onlyTodo"> chỉ ảnh chưa xem</label>
<button id="exp">Xuất review_log.csv</button>
<label><button onclick="document.getElementById('imp').click()">Nhập CSV (gộp)</button><input type="file" id="imp" accept=".csv" multiple hidden></label>
<span id="msg" class="warn"></span></header>
<div style="margin:10px 16px;color:#555">%(nc)d ứng viên. Mở ảnh, nhìn vật, rồi ghi <b>thấy gì</b> (ví dụ "xe tải mui kín, detection ghi car").
Ứng viên hoá ra là lệch tự nhiên → <b>rejected</b> kèm lý do. Ghi chú ≥ 20 ký tự, không chép giống nhau (H3). Bấm vào ảnh để mở ảnh gốc.</div>
<div id="list"></div>
<script>
const C=%(cands)s, R=%(reviewers)s, TYPES=%(types)s, KEY="review:"+%(key)s;
let S={}; try{S=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){S={}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}}
const me=document.getElementById("me");
R.forEach(r=>{const o=document.createElement("option");o.textContent=r;me.appendChild(o)});
try{me.value=localStorage.getItem("review:me")||R[0]}catch(e){}
me.onchange=()=>{try{localStorage.setItem("review:me",me.value)}catch(e){};draw()};
["onlyMine","onlyTodo"].forEach(id=>document.getElementById(id).onchange=draw);
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c])}
function draw(){
 const L=document.getElementById("list");L.innerHTML="";let done=0;
 C.forEach((c,k)=>{const st=S[c.image]||{};if(st.verdict)done++;
  if(document.getElementById("onlyMine").checked&&c.assignee!==me.value)return;
  if(document.getElementById("onlyTodo").checked&&st.verdict)return;
  const d=document.createElement("div");d.className="card"+(st.verdict==="confirmed"?" done":st.verdict==="rejected"?" rej":"");
  const g=c.type.split("|");
  d.innerHTML=`<div class="row"><b>#${k+1} ${esc(c.image)}</b> <span>giao cho <span class="who">${esc(c.assignee)}</span></span>
   <span>máy đoán: <span class="guess">${esc(c.type)}</span> (điểm ${c.score})</span></div>
   <ul class="why">${c.signals.map(s=>`<li><span class="guess">${esc(s.type)}</span> ${esc(s.why)}</li>`).join("")}</ul>
   <a href="${esc(c.orig)}" target="_blank"><img loading="lazy" src="${esc(c.png)}"></a>
   <div class="row"><label>Loại: <select data-f="type"><option value="">—</option>${TYPES.map(t=>`<option ${(st.type||(g.length==1?g[0]:""))===t?"selected":""}>${t}</option>`).join("")}</select></label>
   <label>Kết luận: <select data-f="verdict"><option value="">— chưa xem —</option><option ${st.verdict==="confirmed"?"selected":""}>confirmed</option><option ${st.verdict==="rejected"?"selected":""}>rejected</option></select></label>
   <span>người xem: <b>${esc(st.by||"")}</b></span></div>
   <textarea data-f="note" placeholder="Thấy gì trong ảnh? Nguồn nào đúng, nguồn nào sai?">${esc(st.note||"")}</textarea>
   <div class="warn"></div>`;
  d.querySelectorAll("[data-f]").forEach(el=>el.oninput=el.onchange=()=>{const s=S[c.image]=S[c.image]||{};
    s.type=d.querySelector('[data-f=type]').value;s[el.dataset.f]=el.value;s.by=me.value;save();check(d,s)});
  check(d,st);L.appendChild(d)});
 document.getElementById("prog").textContent=`${done}/${C.length} đã xem`;
}
function check(d,s){const w=[];if(s.verdict&&!s.type)w.push("chưa chọn loại lỗi");
 if(s.verdict&&(s.note||"").trim().length<20)w.push("ghi chú < 20 ký tự");
 const dup=Object.entries(S).filter(([k,v])=>v.note&&v.note.trim()===(s.note||"").trim()).length>1;if(s.note&&dup)w.push("ghi chú trùng ảnh khác");
 d.querySelector(".warn").textContent=w.join(" · ")}
function csvq(v){v=String(v??"");return /[",\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v}
document.getElementById("exp").onclick=()=>{
 const rows=C.filter(c=>S[c.image]&&S[c.image].verdict).map(c=>{const s=S[c.image];
  const note=(s.note||"").trim()+(s.by&&!(s.note||"").includes("[xem: ")?` [xem: ${s.by}]`:"");
  return [c.image,s.type,s.verdict,note]});
 const bad=rows.filter(r=>!r[1]||r[3].length<20);
 document.getElementById("msg").textContent=bad.length?`${bad.length} dòng thiếu loại hoặc ghi chú ngắn`:"";
 const text="image,type,verdict,note\\n"+rows.map(r=>r.map(csvq).join(",")).join("\\n")+"\\n";
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([text],{type:"text/csv"}));
 a.download="review_log.csv";a.click()};
function parseCSV(t){const out=[];let row=[],f="",q=false;for(let i=0;i<t.length;i++){const ch=t[i];
 if(q){if(ch=='"'&&t[i+1]=='"'){f+='"';i++}else if(ch=='"')q=false;else f+=ch}
 else if(ch=='"')q=true;else if(ch==","){row.push(f);f=""}else if(ch=="\\n"||ch=="\\r"){if(ch=="\\r"&&t[i+1]=="\\n")i++;row.push(f);f="";if(row.some(x=>x))out.push(row);row=[]}else f+=ch}
 if(f||row.length){row.push(f);out.push(row)}return out}
document.getElementById("imp").onchange=async e=>{let n=0;for(const file of e.target.files){const rows=parseCSV(await file.text());
 const h=rows.shift();const ix=k=>h.indexOf(k);for(const r of rows){const img=r[ix("image")];if(!img)continue;
  const m=(r[ix("note")]||"").match(/\\[xem: ([^\\]]+)\\]$/);
  S[img]={type:r[ix("type")],verdict:r[ix("verdict")],note:(r[ix("note")]||""),by:m?m[1]:""};n++}}
 save();draw();document.getElementById("msg").textContent=`đã nhập ${n} dòng`};
draw();
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Vẽ ứng viên và tạo trang review")
    ap.add_argument("delivery")
    ap.add_argument("candidates")
    ap.add_argument("--out", required=True, help="thư mục ra (ví dụ runs/r1007/review)")
    ap.add_argument("--reviewers", default="Thai,Thanh,Thuy,Son,Duc", help="tên người xem, cách nhau dấu phẩy")
    args = ap.parse_args()
    delivery, out = Path(args.delivery), Path(args.out)
    (out / "img").mkdir(parents=True, exist_ok=True)
    classes = {}
    for line in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            i, n = line.split(maxsplit=1)
            classes[int(i)] = n.strip()
    pan = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    anns = {a["image_id"]: a for a in pan["annotations"]}
    pan_index = {Path(im["file_name"]).stem: {"width": im["width"], "height": im["height"],
                                              "mask": Path(anns[im["id"]]["file_name"]).name}
                 for im in pan["images"] if im["id"] in anns}
    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))["candidates"]
    reviewers = [r.strip() for r in args.reviewers.split(",") if r.strip()]
    page = []
    for k, c in enumerate(cands):
        png = out / "img" / f"{k + 1:03d}_{c['image']}.png"
        render(delivery, c, classes, pan_index, png)
        page.append({"image": c["image"], "type": c["type"], "score": c["score"], "signals": c["signals"],
                     "assignee": reviewers[k % len(reviewers)], "png": f"img/{png.name}",
                     "orig": os.path.relpath(delivery / "images" / f"{c['image']}.jpg", out).replace(os.sep, "/")})
        print(f"  {k + 1}/{len(cands)} {c['image']} {c['type']}")
    title = str(delivery)
    (out / "index.html").write_text(PAGE % {
        "title": html.escape(title), "nc": len(page),
        "cands": json.dumps(page, ensure_ascii=False).replace("</", "<\\/"),
        "reviewers": json.dumps(reviewers, ensure_ascii=False), "types": json.dumps(TYPES),
        "key": json.dumps(title)}, encoding="utf-8")
    print(f"{len(page)} ứng viên -> {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
