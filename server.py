from __future__ import annotations

import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
# Scanned display images shipped with this UI/backend demo package.
# Model features and photographed training/reference images are intentionally omitted.
DECOR_ROOT = ROOT / "demo_data" / "decor_info"
ADMIN_WEB = ROOT / "admin_web"
FONT_ROOT = ROOT / "assets" / "fonts"
PORT = int(os.environ.get("XIAOTE_PORT", "8000"))

sessions: dict[str, dict] = {}
favorites: dict[str, set[str]] = {}
history: dict[str, list[dict]] = {}
events: list[dict] = []
feedback: list[dict] = []
orders: list[dict] = []
training: list[dict] = []
CATEGORY_ALIASES = {
    "木纹": {"木纹", "wood", "wood grain", "woodgrain"},
    "抽象": {"抽象", "abstract"},
    "石纹": {"石纹", "stone", "stone texture"},
    "素色": {"素色", "solid", "plain", "unicolor", "uni color"},
}
BROWSE_ACTIONS = {"view", "browse", "open_pattern", "view_pattern"}
FULL_PATTERN_ID_RE = re.compile(r"^\d{2}-\d{5}-\d{3}$")
SALES_CONTACT = {
    "name": "Xiaote Sales",
    "phone": "+86-000-0000-0000",
    "email": "sales@example.com",
    "wechat": "xiaote-sales",
}


def catalog() -> list[dict]:
    items = []
    for folder in sorted(DECOR_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        info_path = folder / "metadata.json"
        info = {}
        if info_path.exists():
            try:
                info = json.loads(info_path.read_text("utf-8"))
            except Exception:
                info = {}
        items.append(
            {
                "pattern_id": folder.name,
                "code": folder.name,
                "name": info.get("decorName") or folder.name,
                "decor_name": info.get("decorName") or folder.name,
                "texture_name": info.get("textureName") or "",
                "usage_name": info.get("usageName") or "",
                "wood_art_name": info.get("woodArtName") or "",
                "tags": info.get("tags") or [],
                "image_url": f"/api/patterns/{folder.name}/image",
                "has_image": True,
            }
        )
    return items


def category_terms(category: str) -> set[str]:
    raw = (category or "").strip().lower()
    if not raw:
        return set()
    for canonical, aliases in CATEGORY_ALIASES.items():
        lowered = {alias.lower() for alias in aliases}
        if raw == canonical.lower() or raw in lowered:
            return lowered | {canonical.lower()}
    return {raw}


def matches_category(item: dict, category: str = "") -> bool:
    terms = category_terms(category)
    if not terms:
        return True
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("pattern_id", "name", "decor_name", "texture_name", "usage_name", "wood_art_name")
    ).lower()
    tags = " ".join(str(tag) for tag in item.get("tags", [])).lower()
    searchable = f"{haystack} {tags}"
    return any(term and term in searchable for term in terms)


def family_id(pattern_id: str) -> str:
    parts = (pattern_id or "").split("-")
    if len(parts) >= 3:
        return parts[1]
    return ""


def digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def resolve_search_mode(query: str = "", search_mode: str = "auto") -> str:
    requested = (search_mode or "auto").strip().lower()
    if requested in {"exact", "family", "keyword"}:
        return requested
    q = (query or "").strip()
    if not q:
        return "browse"
    if FULL_PATTERN_ID_RE.match(q):
        return "exact"
    if q.isdigit():
        return "family"
    return "keyword"


def keyword_score(item: dict, query: str) -> int:
    q = query.lower()
    name = str(item.get("name") or item.get("decor_name") or "").lower()
    pattern_id = str(item.get("pattern_id", "")).lower()
    descriptors = " ".join(
        str(item.get(key, ""))
        for key in ("texture_name", "usage_name", "wood_art_name")
    ).lower()
    tags = [str(tag).lower() for tag in item.get("tags", [])]
    searchable = " ".join([pattern_id, name, descriptors, " ".join(tags)])
    terms = [term for term in q.split() if term]
    if q == name:
        score = 100
    elif name.startswith(q):
        score = 90
    elif q in name:
        score = 80
    elif any(q == tag for tag in tags):
        score = 70
    elif any(q in tag for tag in tags):
        score = 60
    elif q in descriptors:
        score = 50
    elif q in pattern_id:
        score = 40
    elif terms and all(term in searchable for term in terms):
        score = 30
    else:
        return 0
    if terms:
        score += sum(1 for term in terms if term in name) * 3
        score += sum(1 for term in terms if term in searchable)
    return score


def find_items(query: str = "", limit: int = 5, category: str = "", search_mode: str = "auto") -> list[dict]:
    q = query.strip().lower()
    items = catalog()
    if category:
        items = [item for item in items if matches_category(item, category)]
    result_limit = max(1, min(limit, 50))
    if not q:
        return items[:result_limit]
    exact = [item for item in items if item["pattern_id"].lower() == q]
    if exact:
        return exact[:1]
    mode = resolve_search_mode(q, search_mode)
    if mode == "exact":
        return []
    if mode == "family":
        family = [item for item in items if family_id(item["pattern_id"]).lower() == q]
        if not family:
            query_digits = digits_only(q)
            family = [item for item in items if query_digits and query_digits in digits_only(item["pattern_id"])]
        return family[: min(result_limit, 5)]
    scored = [(keyword_score(item, q), item) for item in items]
    results = [(score, item) for score, item in scored if score > 0]
    results.sort(key=lambda pair: (-pair[0], pair[1]["pattern_id"]))
    return [item for _, item in results[: min(result_limit, 5)]]


def pdf_bytes() -> bytes:
    body = b"BT /F1 20 Tf 72 720 Td (Xiaote Favorite Patterns - Mock PDF) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def jpeg_size(data: bytes) -> tuple[int, int]:
    index = 2
    while index < len(data) - 9:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        length = int.from_bytes(data[index + 2:index + 4], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3}:
            height = int.from_bytes(data[index + 5:index + 7], "big")
            width = int.from_bytes(data[index + 7:index + 9], "big")
            return width, height
        index += 2 + length
    return 1000, 1000


def pattern_pdf_bytes(pattern_id: str) -> bytes:
    item = next((item for item in catalog() if item["pattern_id"] == pattern_id), None)
    image_path = DECOR_ROOT / pattern_id / "bigImage.jpg"
    if not item or not image_path.exists():
        return pdf_bytes()

    image_data = image_path.read_bytes()
    image_width, image_height = jpeg_size(image_data)
    box_width = 470
    box_height = max(260, int(box_width * image_height / max(image_width, 1)))
    if box_height > 470:
        box_height = 470
        box_width = max(260, int(box_height * image_width / max(image_height, 1)))
    image_x = int((612 - box_width) / 2)
    image_y = 235
    safe_name = "".join(ch if ord(ch) < 128 else " " for ch in item.get("name", pattern_id))
    text = f"BT /F1 24 Tf 72 720 Td ({pattern_id}) Tj /F1 18 Tf 0 -32 Td ({safe_name}) Tj ET"
    image_draw = f"q {box_width} 0 0 {box_height} {image_x} {image_y} cm /Im1 Do Q"
    content = (text + "\n" + image_draw).encode("ascii", errors="ignore")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> /XObject << /Im1 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Type /XObject /Subtype /Image /Width {image_width} /Height {image_height} "
            "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length "
        ).encode() + str(len(image_data)).encode() + b" >>\nstream\n" + image_data + b"\nendstream",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


class Handler(BaseHTTPRequestHandler):
    server_version = "XiaoteMock/0.1"

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def json_response(self, data: dict, status: int = 200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def serve_static(self, file_path: Path, root_path: Path):
        try:
            resolved = file_path.resolve()
            root = root_path.resolve()
            if root not in resolved.parents and resolved != root:
                self.send_error(403)
                return
            if not resolved.exists() or not resolved.is_file():
                self.send_error(404)
                return
            data = resolved.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(resolved.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def token(self) -> str:
        header = self.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return header.split(" ", 1)[1]
        return header

    def user(self) -> dict:
        return sessions.get(self.token()) or {"id": "guest", "username": "guest", "role": "visitor"}

    def add_history(self, action: str, pattern_id: str = "", query: str = ""):
        user = self.user()
        records = history.setdefault(user["id"], [])
        if action in BROWSE_ACTIONS and pattern_id:
            records[:] = [
                item
                for item in records
                if not (item.get("pattern_id") == pattern_id and item.get("action") in BROWSE_ACTIONS)
            ]
        records.insert(0, {"id": str(len(events)), "action": action, "pattern_id": pattern_id, "query": query, "created_at": "mock-now"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in {"/admin-web", "/admin-web/"}:
            self.serve_static(ADMIN_WEB / "index.html", ADMIN_WEB)
            return
        if path.startswith("/admin-web/"):
            relative = unquote(path.replace("/admin-web/", "", 1))
            self.serve_static(ADMIN_WEB / relative, ADMIN_WEB)
            return
        if path.startswith("/fonts/"):
            relative = unquote(path.replace("/fonts/", "", 1))
            self.serve_static(FONT_ROOT / relative, FONT_ROOT)
            return
        if path in {"/", "/health"}:
            self.json_response({"status": "ok", "mock": True, "patterns": len(catalog())})
            return
        if path == "/api/patterns":
            query = qs.get("query", [""])[0]
            category = qs.get("category", [""])[0]
            limit = int(qs.get("limit", ["5"])[0])
            search_mode = qs.get("search_mode", ["auto"])[0]
            resolved_mode = resolve_search_mode(query, search_mode)
            items = find_items(query, limit, category, resolved_mode)
            favs = favorites.get(self.user()["id"], set())
            for item in items:
                item["favorited"] = item["pattern_id"] in favs
            self.add_history("search", query=query)
            self.json_response({"items": items, "count": len(items), "search_mode": resolved_mode})
            return
        if path.startswith("/api/patterns/") and path.endswith("/export.pdf"):
            pattern_id = unquote(path.split("/")[3])
            data = pattern_pdf_bytes(pattern_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/api/patterns/") and not path.endswith("/image"):
            pattern_id = unquote(path.split("/")[3])
            item = next((item for item in catalog() if item["pattern_id"] == pattern_id), None)
            if not item:
                self.send_error(404)
                return
            item = dict(item)
            item["favorited"] = pattern_id in favorites.get(self.user()["id"], set())
            self.add_history("view", pattern_id=pattern_id)
            events.append({"event_type": "view_pattern", "pattern_id": pattern_id, "user_id": self.user()["id"]})
            self.json_response({"item": item})
            return
        if path.startswith("/api/patterns/") and path.endswith("/image"):
            pattern_id = unquote(path.split("/")[3])
            image = DECOR_ROOT / pattern_id / "bigImage.jpg"
            if not image.exists():
                self.send_error(404)
                return
            data = image.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(image.name)[0] or "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/favorites":
            user = self.user()
            favs = favorites.get(user["id"], set())
            items = [item for item in catalog() if item["pattern_id"] in favs]
            self.json_response({"items": items, "count": len(items)})
            return
        if path == "/api/favorites/export.pdf":
            data = pdf_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/history":
            user = self.user()
            by_id = {item["pattern_id"]: item for item in catalog()}
            records = [
                item
                for item in history.get(user["id"], [])
                if item.get("pattern_id") and item.get("action") in BROWSE_ACTIONS
            ]
            seen = set()
            items = []
            for record in records:
                pattern_id = record.get("pattern_id")
                if pattern_id in seen or pattern_id not in by_id:
                    continue
                item = dict(by_id[pattern_id])
                item["history_id"] = record["id"]
                item["created_at"] = record["created_at"]
                item["viewed_at"] = record["created_at"]
                item["favorited"] = pattern_id in favorites.get(user["id"], set())
                items.append(item)
                seen.add(pattern_id)
            self.json_response({"items": items, "count": len(items)})
            return
        if path == "/api/admin/summary":
            self.json_response({
                "users": len(sessions),
                "events": len(events),
                "feedback": len(feedback),
                "unmatched": 0,
                "training_data": len(training),
                "sample_orders": len(orders),
                "patterns": len(catalog()),
                "current_user": self.user(),
            })
            return
        if path == "/api/admin/events":
            self.json_response({"items": events[-100:][::-1], "count": len(events)})
            return
        if path == "/api/admin/feedback":
            self.json_response({"items": feedback[-100:][::-1], "count": len(feedback)})
            return
        if path == "/api/admin/unmatched":
            self.json_response({"items": [], "count": 0})
            return
        if path == "/api/admin/training-data":
            self.json_response({"items": training[-100:][::-1], "count": len(training)})
            return
        if path == "/api/admin/sample-orders":
            self.json_response({"items": orders[-100:][::-1], "count": len(orders)})
            return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path in {"/api/auth/register", "/api/auth/login", "/api/auth/wechat-login"}:
            body = self.read_json()
            role = body.get("role") or "visitor"
            token = f"mock-{len(sessions)+1}"
            user = {"id": token, "username": body.get("username") or "wx_mock_user", "role": role, "language": body.get("language") or "zh-CN"}
            sessions[token] = user
            self.json_response({"token": token, "user": user})
            return
        if path == "/recognize":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = b""
            if length:
                raw = self.rfile.read(length)
            body_text = raw.decode("utf-8", errors="ignore")
            category = ""
            for candidate in CATEGORY_ALIASES:
                if candidate in body_text:
                    category = candidate
                    break
            items = find_items("", 10, category)
            top = []
            for index, item in enumerate(items):
                item = dict(item)
                item["confidence"] = round(0.94 - index * 0.02, 2)
                item["confidenceText"] = f"{int(item['confidence'] * 100)}%"
                item["favorited"] = item["pattern_id"] in favorites.get(self.user()["id"], set())
                top.append(item)
            self.add_history("recognition", pattern_id=top[0]["pattern_id"] if top else "")
            if not top:
                self.json_response({"error": "category_no_match", "top_results": [], "all_top_results": [], "threshold": 0.8, "recognition_id": "mock-recognition"})
                return
            self.json_response({"pattern_id": top[0]["pattern_id"], "confidence": top[0]["confidence"], "top_results": top, "all_top_results": top, "threshold": 0.8, "recognition_id": "mock-recognition"})
            return
        if path == "/api/favorites":
            body = self.read_json()
            user = self.user()
            favorites.setdefault(user["id"], set()).add(body.get("pattern_id"))
            self.add_history("favorite", pattern_id=body.get("pattern_id", ""))
            self.json_response({"ok": True})
            return
        if path == "/api/feedback":
            feedback.append(self.read_json())
            self.json_response({"ok": True, "feedback_id": f"mock-feedback-{len(feedback)}"})
            return
        if path == "/api/leads/contact":
            body = self.read_json()
            events.append({"event_type": "lead_contact", "payload": body})
            self.json_response({"lead_id": f"mock-lead-{len(events)}", "contact": SALES_CONTACT})
            return
        if path == "/api/user/preferences":
            body = self.read_json()
            user = self.user()
            user["language"] = body.get("language") or user.get("language") or "zh-CN"
            self.json_response({"user": user})
            return
        if path == "/api/orders/samples":
            orders.append(self.read_json())
            self.json_response({"ok": True, "order_id": f"mock-order-{len(orders)}"})
            return
        if path == "/api/admin/training-data":
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length:
                self.rfile.read(length)
            training.append({"id": f"mock-training-{len(training)+1}"})
            self.json_response({"ok": True, "id": training[-1]["id"]})
            return
        if path == "/api/events":
            body = self.read_json()
            events.append(body)
            if body.get("event_type") in BROWSE_ACTIONS:
                self.add_history(body.get("event_type"), pattern_id=body.get("pattern_id", ""))
            self.json_response({"ok": True, "event_id": f"mock-event-{len(events)}"})
            return
        self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/favorites/"):
            pattern_id = unquote(path.split("/")[3])
            user = self.user()
            favorites.setdefault(user["id"], set()).discard(pattern_id)
            events.append({"event_type": "unfavorite", "pattern_id": pattern_id, "user_id": user["id"]})
            self.json_response({"ok": True})
            return
        self.send_error(404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Xiaote mock backend running on http://127.0.0.1:{PORT}")
    server.serve_forever()
