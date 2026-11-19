#!/usr/bin/env python3
"""Validator luật cho một lô bàn giao (Pha 1).

Giao diện cố định:

    python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

Nguyên tắc (xem RULES.md, docs/DELIVERY.md):
  - CHỈ đọc thư mục delivery được truyền vào. Không đọc _private/, data_source/,
    annotation COCO gốc. Không dùng mạng.
  - Chỉ thư viện chuẩn Python, cộng `scripts/pngutil.py` (đọc PNG).
  - errors.json CHỈ chứa 9 loại lỗi luật. 5 loại lỗi gán nhãn không chứng minh
    được bằng một file, nên chỉ ghi vào candidates.json để người trong nhóm mở ảnh xác nhận.

Cách đo từng loại (chi tiết ở hàm tương ứng, comment ngay tại chỗ):
  missing_image          manifest có ảnh nhưng thiếu file trên đĩa
  wrong_hash            sha256 tự tính của file khác giá trị trong manifest
  invalid_class         class_id trong labels/ ngoài khoảng 0..79
  bbox_out_of_bounds    box (đổi sang pixel) tràn ra ngoài ảnh
  duplicate_box         hai box cùng lớp, cùng kích thước, lệch tối đa 1-2 pixel
  scene_leak            một scene_id có ảnh ở cả train và val
  guideline_mismatch    guideline ảnh khác guideline ghi ở job của nó
  invalid_category_id   category_id của segment không có trong categories
  thing_overlap         area khai nhiều hơn số pixel thật của segment trong mask
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from itertools import combinations
from pathlib import Path

# Cho phép import pngutil của repo (scripts/pngutil.py) mà không cài gì thêm.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402

# ---------------------------------------------------------------------------
# Ngưỡng. Tất cả đều lấy từ đặc tả của inject_release.py / docs/DELIVERY.md,
# không gắn với seed hay tên ảnh cụ thể nào.
# ---------------------------------------------------------------------------

# Số lớp detection hợp lệ: classes.txt có 80 dòng, class_id chạy 0..79.
# Đọc từ classes.txt nếu có, fallback 80 nếu file hỏng/mất.
DEFAULT_NUM_CLASSES = 80

# Chênh lệch pixel cho phép giữa hai box cùng lớp để coi là "lặp".
# inject_release.py dịch box đúng 1-2 pixel (rng.choice([-2,-1,1,2])).
# Dùng biên an toàn: chấp nhận tới 2 px lệch tâm, 1 px lệch kích thước.
DUP_SHIFT_PX = 2.5          # lệch tâm (px)
DUP_SIZE_PX = 1.0           # lệch kích thước w/h (px)

# Ngưỡng tràn mép ảnh (px). Box COCO tự nhiên chạm mép đúng tới sai số float
# (~1e-13 px); box lỗi gài tràn 2-8% chiều rộng ảnh (>= 8 px trên ảnh 640px).
# 0.01 px là ranh giới an toàn: bỏ qua nhiễu float, vẫn bắt được lỗi thật.
OOB_EPS_PX = 0.01

# Ngưỡng ghép box detection <-> segment panoptic (chỉ dùng cho candidates.json).
# Ghép bằng IoU bbox (bỏ qua segment iscrowd vì chúng chồng nhau nhiều),
# rồi dùng pixel mask để đo độ khớp thật sự.
CAND_MIN_IOU = 0.3          # mặc định giữa bbox box và bbox segment
CAND_MIN_FRAC = 0.5         # tỉ lệ pixel segment phải nằm trong box để coi là khớp
CAND_MERGE_MAX_BOX_IOU = 0.3  # hai box cùng lớp chồng nhau mạnh thì là MỘT vật bị gán
                              # box hai lần, không phải hai vật bị gộp thành một segment
CAND_MIN_SEGMENT_AREA = 1024  # segment nhỏ hơn ngần này thì khó nhìn bằng mắt
CAND_DRIFT_MIN_IOU = 0.5     # box phải còn chồm lên vật thì mới gọi là "lệch"
CAND_DRIFT_MAX_FRAC = 0.6    # box bỏ sót quá nhiều pixel của vật thì mới đáng nghi


# ---------------------------------------------------------------------------
# Tiện ích đọc file
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """sha256 trên BYTES của file. Phải đọc ở chế độ 'rb' (như RULES.md nhắc),
    nếu đọc ở chế độ text sẽ bị đổi newline và sinh hash sai."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Nạp dữ liệu lô
# ---------------------------------------------------------------------------

class Delivery:
    """Bọc các file của một thư mục delivery và trả lời các câu hỏi về lô."""

    def __init__(self, root: Path):
        self.root = root
        self.manifest = read_json(root / "manifest.json")
        self.items = self.manifest.get("items", {})
        self.metadata = read_json(root / "metadata.json").get("items", [])
        self.panoptic = read_json(root / "panoptic.json")

        # Danh sách class detection: id -> tên lớp (để ghép với panoptic theo TÊN).
        self.class_name = self._read_classes()
        self.num_classes = len(self.class_name) or DEFAULT_NUM_CLASSES

        # guideline theo job: job_id -> guideline version.
        self.job_guideline = self._read_jobs()

        # metadata theo tên ảnh (không có đuôi).
        self.meta_by_image = {row["image"]: row for row in self.metadata}

        # Kích thước ảnh theo tên ảnh, lấy từ panoptic.json (nguồn duy nhất
        # trong delivery có kích thước pixel thật của ảnh).
        self.size_by_image = {}
        for image in self.panoptic.get("images", []):
            stem = Path(image["file_name"]).stem
            self.size_by_image[stem] = (image["width"], image["height"])

        # category_id -> thông tin category; tập id hợp lệ để so invalid_category_id.
        self.categories = {c["id"]: c for c in self.panoptic.get("categories", [])}
        self.thing_ids = {c["id"] for c in self.panoptic.get("categories", []) if c.get("isthing")}

        # Annotation panoptic theo tên ảnh.
        self.segments_by_image = {}
        for ann in self.panoptic.get("annotations", []):
            stem = Path(ann["file_name"]).stem
            self.segments_by_image[stem] = ann.get("segments_info", [])

        # Tên lớp panoptic theo category_id, và category_id theo tên lớp.
        self.category_name = {cid: c["name"] for cid, c in self.categories.items()}
        self.category_by_name = {c["name"]: cid for cid, c in self.categories.items()}

    def _read_classes(self) -> dict[int, str]:
        """classes.txt: mỗi dòng 'class_id tên_lớp'."""
        path = self.root / "classes.txt"
        out: dict[int, str] = {}
        if not path.is_file():
            return out
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            try:
                out[int(parts[0])] = parts[1].strip()
            except ValueError:
                continue
        return out

    def _read_jobs(self) -> dict[str, str]:
        """jobs.csv: job_id, annotator, reviewer, guideline.

        Guideline của một ảnh phải lấy theo JOB, không lấy theo ảnh: chính
        guideline ghi ở ảnh là thứ có thể sai (đó là lỗi guideline_mismatch)."""
        path = self.root / "jobs.csv"
        out: dict[str, str] = {}
        if not path.is_file():
            return out
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                job_id = (row.get("job_id") or "").strip()
                if job_id:
                    out[job_id] = (row.get("guideline") or "").strip()
        return out

    def image_size(self, stem: str):
        """(width, height) của ảnh. Trả về None nếu không biết."""
        return self.size_by_image.get(stem)

    def label_path(self, stem: str) -> Path:
        item = self.items.get(stem)
        if item and item.get("label"):
            return self.root / item["label"]
        return self.root / "labels" / (stem + ".txt")

    def mask_path(self, stem: str) -> Path:
        item = self.items.get(stem)
        if item and item.get("mask"):
            return self.root / item["mask"]
        return self.root / "masks" / (stem + ".png")

    def image_path(self, stem: str) -> Path:
        item = self.items.get(stem)
        if item and item.get("image"):
            return self.root / item["image"]
        return self.root / "images" / (stem + ".jpg")


# ---------------------------------------------------------------------------
# Luật detection
# ---------------------------------------------------------------------------

def read_yolo_boxes(path: Path):
    """Đọc nhãn YOLO. Mỗi dòng: 'class_id x_center y_center width height'
    (tọa độ chuẩn hoá 0..1). Trả về list (class_id, xc, yc, w, h).

    Dòng hỏng (số trường sai, số không parse được) bị bỏ qua: validator
    không tự kết luận lỗi gán nhãn cho những trường hợp này."""
    boxes = []
    if not path.is_file():
        return boxes
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            continue
        try:
            class_id = int(parts[0])
            xc, yc, w, h = (float(v) for v in parts[1:5])
        except ValueError:
            continue
        boxes.append((class_id, xc, yc, w, h))
    return boxes


def to_pixel_box(box, width: int, height: int):
    """Đổi box YOLO (chuẩn hoá) sang pixel, trả về (x1, y1, x2, y2).

    Box YOLO là tâm + kích thước, cùng toạ độ chuẩn hoá theo chiều rộng/cao
    ảnh, nên nhân riêng từng trục."""
    _, xc, yc, w, h = box
    return ((xc - w / 2) * width, (yc - h / 2) * height,
            (xc + w / 2) * width, (yc + h / 2) * height)


def check_missing_image(delivery: Delivery):
    """missing_image: manifest có ảnh nhưng thiếu file trên đĩa.

    Trong manifest mỗi mục ghi đường dẫn tới file ảnh. Nếu file đó không tồn
    tại (bị xoá lúc chuyển lô) thì lô giao đi không đủ ảnh."""
    found = []
    for stem in delivery.items:
        if not delivery.image_path(stem).is_file():
            found.append(stem)
    return found


def check_wrong_hash(delivery: Delivery):
    """wrong_hash: sha256 ghi trong manifest không phải của file đó.

    Tự tính sha256 trên bytes của file rồi so với giá trị manifest. Không
    kiểm tra "64 ký tự hex" vì lỗi gài dùng hash HỢP LỆ của một ảnh khác."""
    found = []
    for stem, item in delivery.items.items():
        for key, path in (("image_sha256", delivery.image_path(stem)),
                          ("label_sha256", delivery.label_path(stem)),
                          ("mask_sha256", delivery.mask_path(stem))):
            declared = item.get(key)
            if declared is None:
                continue
            if not path.is_file():
                continue          # thiếu file là lỗi missing_image, không phải wrong_hash
            if sha256_file(path) != declared:
                found.append(stem)
                break             # một ảnh mang nhiều nhất một lỗi
    return found


def check_invalid_class(delivery: Delivery):
    """invalid_class: class_id trong nhãn YOLO ngoài khoảng 0..79.

    Ngưỡng lấy từ classes.txt (80 lớp, id 0..79) và từ docs/DELIVERY.md
    ("Detection đánh số lớp 0-79")."""
    found = []
    for stem in delivery.items:
        boxes = read_yolo_boxes(delivery.label_path(stem))
        if any(not (0 <= class_id < delivery.num_classes) for class_id, *_ in boxes):
            found.append(stem)
    return found


def check_bbox_out_of_bounds(delivery: Delivery):
    """bbox_out_of_bounds: box tràn ra ngoài ảnh.

    So với KÍCH THƯỚC ẢNH THẬT (panoptic.json), không dùng ngưỡng làm tròn.
    Lý do chọn ngưỡng OOB_EPS_PX = 0.01 px: box COCO tự nhiên hay chạm mép
    ảnh, và do số thực 6 chữ số trong file YOLO, mép đó lệch vài 1e-13 px;
    ngưỡng này bỏ qua nhiễu đó. Lỗi thật thì tràn 2-8% chiều rộng ảnh
    (>= 8 px), cách xa ngưỡng."""
    found = []
    for stem in delivery.items:
        size = delivery.image_size(stem)
        if size is None:
            continue
        width, height = size
        for box in read_yolo_boxes(delivery.label_path(stem)):
            x1, y1, x2, y2 = to_pixel_box(box, width, height)
            overflow = (max(0.0, -x1) + max(0.0, x2 - width)
                        + max(0.0, -y1) + max(0.0, y2 - height))
            if overflow > OOB_EPS_PX:
                found.append(stem)
                break
    return found


def check_duplicate_box(delivery: Delivery):
    """duplicate_box: một box bị lặp.

    Tiêu chí (theo docs/DELIVERY.md): CÙNG lớp, CÙNG kích thước, lệch 1-2 pixel.

    Vì sao KHÔNG dùng ngưỡng IoU thấp: COCO có cặp box cùng lớp chồng nhau
    tự nhiên tới IoU ~0.66 (đo được ở lô 1007: 0.7976, 0.7035, 0.6897...).
    Box lặp lại do lỗi gài thì khác ở chỗ KÍCH THƯỚC GIỐNG HỆT nhau và
    tâm lệch đúng 1-2 pixel. Vì vậy ta so đặc điểm, không so giao nhau:
      - cùng class_id
      - |Δw| <= 1 px và |Δh| <= 1 px   (cùng kích thước)
      - |Δcenter_x| <= 2.5 px và |Δcenter_y| <= 2.5 px  (lệch tối đa 1-2 px)
    Cặp tự nhiên ở trên có kích thước khác nhau rõ rệt nên không bị nhận nhầm."""
    found = []
    for stem in delivery.items:
        size = delivery.image_size(stem)
        if size is None:
            continue
        width, height = size
        pixels = []
        for class_id, xc, yc, w, h in read_yolo_boxes(delivery.label_path(stem)):
            pixels.append((class_id, xc * width, yc * height, w * width, h * height))
        duplicated = False
        for i in range(len(pixels)):
            if duplicated:
                break
            ci, cxi, cyi, wi, hi = pixels[i]
            for j in range(i + 1, len(pixels)):
                cj, cxj, cyj, wj, hj = pixels[j]
                if ci != cj:
                    continue
                if (abs(wi - wj) > DUP_SIZE_PX or abs(hi - hj) > DUP_SIZE_PX):
                    continue
                if abs(cxi - cxj) > DUP_SHIFT_PX or abs(cyi - cyj) > DUP_SHIFT_PX:
                    continue
                duplicated = True
                break
        if duplicated:
            found.append(stem)
    return found


# ---------------------------------------------------------------------------
# Luật metadata
# ---------------------------------------------------------------------------

def check_scene_leak(delivery: Delivery):
    """scene_leak: một scene_id có ảnh ở CẢ train và val.

    Target của lỗi này là scene_id (không phải tên ảnh) vì cảnh là đơn vị
    bị rò sang split: sửa thì phải đưa cả cảnh về một split."""
    splits_by_scene: dict[str, set[str]] = {}
    for row in delivery.metadata:
        scene = row.get("scene_id")
        split = row.get("split")
        if scene is None or split is None:
            continue
        splits_by_scene.setdefault(scene, set()).add(split)
    return sorted(scene for scene, splits in splits_by_scene.items() if len(splits) > 1)


def check_guideline_mismatch(delivery: Delivery):
    """guideline_mismatch: guideline ghi ở ảnh khác guideline ghi ở job.

    Guideline chuẩn là guideline của JOB (jobs.csv). Guideline ghi trong
    metadata.json là dữ liệu bị nghi, nên so hai bên với nhau."""
    found = []
    for row in delivery.metadata:
        image = row.get("image")
        job_id = row.get("job_id")
        image_guideline = row.get("guideline_version")
        if image is None or job_id is None:
            continue
        job_guideline = delivery.job_guideline.get(job_id)
        if job_guideline is None:
            continue
        if image_guideline != job_guideline:
            found.append(image)
    return found


# ---------------------------------------------------------------------------
# Luật panoptic
# ---------------------------------------------------------------------------

def check_invalid_category_id(delivery: Delivery):
    """invalid_category_id: category_id của segment không có trong categories.

    Danh sách categories của COCO panoptic KHÔNG liên tục (id chạy 1..200
    nhưng chỉ có 133 id thật, 67 id là khoảng trống). Lỗi gài chính là chọn
    một id nằm trong khoảng trống đó. Vì vậy phải so với TẬP ID CÓ THẬT,
    không so id nằm trong một khoảng số."""
    found = []
    for stem, segments in delivery.segments_by_image.items():
        for segment in segments:
            if segment.get("category_id") not in delivery.categories:
                found.append(stem)
                break
    return found


def count_segment_pixels(mask_path: Path):
    """Đếm pixel thật của từng segment trong mask PNG panoptic.

    Dùng pngutil.read_rgb để đọc PNG (không viết lại bộ giải nén PNG).
    Segment id = R + G*256 + B*65536; id 0 là nền nên bỏ qua.
    Trả về dict {segment_id: số pixel}."""
    width, _height, pixels = pngutil.read_rgb(mask_path)
    counts: dict[int, int] = {}
    for index in range(0, len(pixels), 3):
        segment_id = pngutil.segment_id(pixels, index)
        if segment_id:
            counts[segment_id] = counts.get(segment_id, 0) + 1
    return counts


def check_thing_overlap(delivery: Delivery):
    """thing_overlap: area khai NHIỀU HƠN số pixel thật của segment.

    Khi một vật khác đè lên segment, một phần pixel của segment biến mất
    khỏi mask nhưng trường `area` vẫn giữ số cũ -> area > pixel thật.

    Vì sao so > (chứ không phải khác):
    - Segment bị vật khác ĐÈ lên: mất pixel -> area > thật.  <- đây là lỗi cần bắt
    - Segment lấp chỗ trống của vật khác: có thể tăng pixel -> area < thật,
      và đó không phải lỗi 'bị đè'.
    Ngưỡng: chỉ báo lỗi khi chênh lệch >= 1 px (tránh sai số float khi
    area được làm tròn)."""
    found = []
    for stem, segments in delivery.segments_by_image.items():
        mask = delivery.mask_path(stem)
        if not mask.is_file():
            continue
        try:
            counts = count_segment_pixels(mask)
        except (ValueError, OSError):
            continue
        for segment in segments:
            if segment.get("iscrowd"):
                continue           # segment crowd không phải vật thể riêng
            declared = segment.get("area")
            if declared is None:
                continue
            real = counts.get(segment.get("id"), 0)
            if declared - real >= 1:
                found.append(stem)
                break
    return found


# ---------------------------------------------------------------------------
# Ứng viên lỗi gán nhãn (chỉ để người trong nhóm mở ảnh xác nhận)
# ---------------------------------------------------------------------------

def box_iou(a, b) -> float:
    """IoU của hai bbox pixel (x1, y1, x2, y2)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = ix * iy
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return intersection / (area_a + area_b - intersection) if area_a + area_b > 0 else 0.0


def build_pixel_index(mask_width: int, pixels: bytearray):
    """Gom pixel theo segment: {segment_id: [(x, y), ...]}.

    Dùng để đếm pixel của một segment có nằm trong một box hay không, mà không
    phải quét lại toàn bộ mask cho mỗi cặp box-segment. Gom theo segment từ
    đầu để mỗi cặp chỉ duyệt pixel của đúng segment đó."""
    index: dict[int, list[tuple[int, int]]] = {}
    for position in range(0, len(pixels), 3):
        segment_id = pngutil.segment_id(pixels, position)
        if not segment_id:
            continue
        pixel = position // 3
        index.setdefault(segment_id, []).append((pixel % mask_width, pixel // mask_width))
    return index


def pixel_fraction(pixel_index, segment_id, box):
    """Tỉ lệ pixel của segment nằm trong box (None nếu không có pixel index).

    Tín hiệu mạnh hơn IoU bbox: IoU cao không bảo đảm mask nằm trong box,
    còn tỉ lệ pixel thì đo thẳng mối quan hệ giữa mask và box."""
    if pixel_index is None:
        return None
    points = pixel_index.get(segment_id)
    if not points:
        return None
    inside = 0
    for x, y in points:
        if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
            inside += 1
    return inside / len(points)


def build_candidates(delivery: Delivery):
    """Sinh ỨNG VIÊN lỗi gán nhãn.

    ============================================================
    CẢNH BÁO: đây CHỈ là ứng viên, KHÔNG phải kết luận.
    Validator không đưa các loại này vào errors.json. Người trong nhóm
    phải MỞ ẢNH và tự quyết định là `confirmed` hay `rejected`, rồi ghi vào
    review_log.csv. Lô sạch cũng sinh ra ứng viên vì COCO vốn lệch giữa
    nguồn detection và nguồn panoptic (vật bị che, vùng crowd), nên không
    kỳ vọng danh sách này rỗng.
    ============================================================

    Cách ghép (theo GUIDE.md Pha 2):
      1. Đổi box YOLO sang pixel.
      2. Ghép mỗi box với segment thing có IoU bbox cao nhất (bỏ qua segment
         iscrowd vì chúng là vùng chồng lớn, ghép vào gây nhiễu).
      3. Tính tỉ lệ pixel của segment nằm TRONG box: đây là tín hiệu đáng tin
         hơn IoU bbox, vì box lệch thì một phần pixel segment rơi ra ngoài.

    Các dấu hiệu sinh ứng viên:
      - class_swap / category_swap: box và segment khớp vị trí nhưng khác lớp.
      - bbox_drift: box lệch so với segment cùng lớp (ít pixel nằm trong box).
      - missing_box: segment thing đáng kể không có box nào đủ lớn để phủ.
      - instance_merge: một segment phủ nhiều box cùng lớp."""
    candidates = []
    detection_names = set(delivery.class_name.values())
    for stem in sorted(delivery.items):
        size = delivery.image_size(stem)
        if size is None:
            continue
        width, height = size
        boxes = read_yolo_boxes(delivery.label_path(stem))
        segments = delivery.segments_by_image.get(stem, [])
        if not boxes or not segments:
            continue

        # Box sang pixel.
        pixel_boxes = []
        for class_id, xc, yc, w, h in boxes:
            x1, y1, x2, y2 = to_pixel_box((class_id, xc, yc, w, h), width, height)
            pixel_boxes.append({
                "class_id": class_id,
                "name": delivery.class_name.get(class_id, str(class_id)),
                "box": (x1, y1, x2, y2),
            })

        # Segment THỰC kèm bbox và tên lớp.
        # Chỉ giữ segment isthing: detection chỉ gán box cho vật thể, còn
        # segment "stuff" (wall, sky, floor...) không có box nào tương ứng nên
        # nếu giữ lại sẽ sinh hàng loạt ứng viên missing_box giả.
        # Đồng thời bỏ segment iscrowd: đó là vùng gộp nhiều vật, ghép vào
        # box nào cũng sai.
        usable = []
        for segment in segments:
            if segment.get("iscrowd"):
                continue
            category_id = segment.get("category_id")
            if category_id not in delivery.categories:
                continue
            if category_id not in delivery.thing_ids:
                continue
            bbox = segment.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            bx, by, bw, bh = bbox
            usable.append({
                "id": segment.get("id"),
                "name": delivery.category_name.get(category_id, str(category_id)),
                "box": (bx, by, bx + bw, by + bh),
                "area": float(segment.get("area") or 0),
            })
        if not usable:
            continue

        # Pixel thật của từng segment, để đo độ phủ của box.
        mask = delivery.mask_path(stem)
        pixel_index = None
        if mask.is_file():
            try:
                mask_width, _h, pixels = pngutil.read_rgb(mask)
                pixel_index = build_pixel_index(mask_width, pixels)
            except (ValueError, OSError):
                pixel_index = None

        # Ghép: mỗi box lấy segment thing có IoU bbox cao nhất.
        pair_for_box = {}
        for index, box in enumerate(pixel_boxes):
            best = None
            best_iou = CAND_MIN_IOU
            for segment in usable:
                overlap = box_iou(box["box"], segment["box"])
                if overlap > best_iou:
                    best_iou = overlap
                    best = segment
            if best is not None:
                pair_for_box[index] = (best, best_iou)

        for index, (segment, overlap) in pair_for_box.items():
            box = pixel_boxes[index]
            inside = pixel_fraction(pixel_index, segment["id"], box["box"])
            if box["name"] == segment["name"]:
                # Cùng lớp: box có ôm hết segment không?
                #
                # Bộ lọc 2 điều kiện cho bbox_drift:
                #   (a) IoU bbox >= CAND_DRIFT_MIN_IOU: box PHẢI vẫn chồm lên
                #       vật. Cặp box-segment khớp tệ (IoU thấp) là ghép nhầm,
                #       không phải box lệch, và đó là nhiễu tự nhiên của COCO.
                #   (b) pixel segment nằm trong box < CAND_DRIFT_MAX_FRAC: box
                #       phải BỎ SÓT một phần đáng kể pixel của vật.
                # Nếu chỉ dùng (b) thì lô sạch bị nhiễu nặng (đo được 29 cặp
                # cùng lớp có pixfrac < 0.5 trên 50 ảnh sạch, phần lớn là ghép
                # nhầm chứ không phải lệch). Thêm (a) thì lô sạch còn 1 cặp.
                if (overlap >= CAND_DRIFT_MIN_IOU
                        and inside is not None and inside < CAND_DRIFT_MAX_FRAC):
                    candidates.append({
                        "type": "bbox_drift",
                        "target": stem,
                        "reason": ("box detection lớp '%s' chồm lên segment cùng lớp (IoU bbox %.2f) "
                                   "nhưng chỉ chiếm %.0f%% pixel của vật; box có thể lệch khỏi vật" % (
                                       box["name"], overlap, inside * 100)),
                    })
            else:
                # Khác lớp: một trong hai nguồn ghi sai lớp. Validator KHÔNG
                # biết nguồn nào sai, nên ghi loại ứng viên theo nguồn PANOPTIC
                # bị lệch (category_swap) và nói rõ trong lý do rằng detection
                # có thể là bên sai (class_swap). Người xem ảnh mới quyết định
                # bên nào đúng rồi mới đổi loại khi ghi review_log.csv.
                kind = "category_swap" if segment["name"] in detection_names else "class_swap"
                candidates.append({
                    "type": kind,
                    "target": stem,
                    "reason": ("box detection ghi lớp '%s' nhưng segment panoptic ghi '%s' "
                               "(IoU bbox %.2f, %.0f%% pixel segment nằm trong box); "
                               "mở ảnh xem nguồn nào đúng: nếu detection sai thì là "
                               "class_swap, nếu panoptic sai thì là category_swap" % (
                                   box["name"], segment["name"], overlap,
                                   (inside or 0.0) * 100)),
                })

        # missing_box: segment thing đáng kể mà không box nào phủ được.
        for segment in usable:
            if segment["area"] < CAND_MIN_SEGMENT_AREA:
                continue          # segment nhỏ thì bỏ qua (dưới ngưỡng nhìn thấy)
            covered = False
            for box in pixel_boxes:
                overlap = box_iou(box["box"], segment["box"])
                if overlap < CAND_MIN_IOU:
                    continue
                inside = pixel_fraction(pixel_index, segment["id"], box["box"])
                if inside is not None and inside >= CAND_MIN_FRAC:
                    covered = True
                    break
            if not covered:
                candidates.append({
                    "type": "missing_box",
                    "target": stem,
                    "reason": ("segment panoptic lớp '%s' diện tích %d px không có box detection nào phủ được"
                               % (segment["name"], int(segment["area"]))),
                })

        # instance_merge: một segment phủ nhiều box cùng lớp.
        # Bổ sung điều kiện "hai box đó không chồng lên nhau": nếu hai box
        # cùng lớp chồng mạnh lên nhau (IoU giữa chúng cao) thì đó là MỘT
        # vật bị gán box hai lần, không phải hai vật bị gộp. Ngược lại, nếu
        # segment phủ được hai box tách rời nhau thì đáng nghi hai vật cùng lớp
        # đã bị gộp làm một segment.
        for segment in usable:
            hits = []
            for index, box in enumerate(pixel_boxes):
                if box["name"] != segment["name"]:
                    continue
                overlap = box_iou(box["box"], segment["box"])
                if overlap < CAND_MIN_IOU:
                    continue
                inside = pixel_fraction(pixel_index, segment["id"], box["box"])
                if inside is not None and inside >= CAND_MIN_FRAC:
                    hits.append(index)
            if len(hits) < 2:
                continue
            # Mọi cặp trong `hits` phải là hai box TÁCH rời (không chồng nhau).
            distinct = all(
                box_iou(pixel_boxes[a]["box"], pixel_boxes[b]["box"]) <= CAND_MERGE_MAX_BOX_IOU
                for a, b in combinations(hits, 2))
            if distinct:
                candidates.append({
                    "type": "instance_merge",
                    "target": stem,
                    "reason": ("segment panoptic lớp '%s' phủ trọn %d box detection cùng lớp "
                               "và các box đó không chồng lên nhau; "
                               "có thể hai vật cùng lớp bị gộp làm một" % (
                                   segment["name"], len(hits))),
                })
    return candidates


# ---------------------------------------------------------------------------
# Chạy
# ---------------------------------------------------------------------------

def collect_rule_errors(delivery: Delivery):
    """Chạy 9 luật, trả về list cặp (type, target).

    Mỗi ảnh mang nhiều nhất một lỗi, và mỗi cặp (type, target) chỉ xuất
    hiện một lần. Vì vậy, nếu một ảnh bị nhiều luật bắt, chỉ giữ lại luật
    đầu tiên theo thứ tự ưu tiên bên dưới (luật file trước, rồi nhãn, rồi
    metadata, rồi panoptic) để khớp với cách lô được chấm."""
    groups = [
        ("missing_image", check_missing_image(delivery)),
        ("wrong_hash", check_wrong_hash(delivery)),
        ("invalid_class", check_invalid_class(delivery)),
        ("bbox_out_of_bounds", check_bbox_out_of_bounds(delivery)),
        ("duplicate_box", check_duplicate_box(delivery)),
        ("guideline_mismatch", check_guideline_mismatch(delivery)),
        ("invalid_category_id", check_invalid_category_id(delivery)),
        ("thing_overlap", check_thing_overlap(delivery)),
    ]

    errors = []
    claimed: set[str] = set()
    for kind, targets in groups:
        for target in targets:
            if target in claimed:
                continue          # ảnh này đã mang một lỗi khác rồi
            claimed.add(target)
            errors.append((kind, target))

    # scene_leak đứng riêng: target là scene_id, không phải tên ảnh, nên không
    # cạnh tranh "một lỗi mỗi ảnh" với các luật khác.
    for scene in check_scene_leak(delivery):
        errors.append(("scene_leak", scene))

    return errors


def sort_errors(errors):
    """Sắp xếp cố định để kết quả lặp lại được.

    Thứ tự: nhóm loại (theo bảng trong docs/DELIVERY.md) rồi tên target."""
    order = ["missing_image", "wrong_hash", "invalid_class", "bbox_out_of_bounds",
             "duplicate_box", "scene_leak", "guideline_mismatch",
             "invalid_category_id", "thing_overlap"]
    rank = {kind: index for index, kind in enumerate(order)}
    return sorted(errors, key=lambda pair: (rank.get(pair[0], len(rank)), pair[1]))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bắt lỗi luật trong một thư mục delivery (chỉ đọc, không ghi vào lô).")
    parser.add_argument("delivery", help="thư mục delivery cần kiểm tra")
    parser.add_argument("--out", required=True, help="nơi ghi errors.json")
    parser.add_argument("--candidates", help="nơi ghi candidates.json (ứng viên lỗi gán nhãn)")
    args = parser.parse_args()

    root = Path(args.delivery)
    if not root.is_dir():
        raise SystemExit(f"Không thấy thư mục delivery: {root}")

    delivery = Delivery(root)
    errors = sort_errors(collect_rule_errors(delivery))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"errors": [{"type": kind, "target": target} for kind, target in errors]},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(f"wrote {out_path} ({len(errors)} rule errors)")

    if args.candidates:
        candidates = build_candidates(delivery)
        cand_path = Path(args.candidates)
        cand_path.parent.mkdir(parents=True, exist_ok=True)
        cand_path.write_text(
            json.dumps({"candidates": candidates}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(f"wrote {cand_path} ({len(candidates)} candidates - xem ảnh để xác nhận)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
