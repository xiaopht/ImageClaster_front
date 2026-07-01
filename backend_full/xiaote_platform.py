from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import pymysql
    import pymysql.cursors
except ImportError:  # Local development can keep using SQLite without PyMySQL installed.
    pymysql = None


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PLATFORM_DIR = DATA_DIR / "platform"
UPLOAD_DIR = PLATFORM_DIR / "uploads"
FEEDBACK_DIR = PLATFORM_DIR / "feedback_images"
TRAINING_DIR = PLATFORM_DIR / "training_uploads"
THUMBNAIL_DIR = PLATFORM_DIR / "pattern_thumbnails"
DB_PATH = PLATFORM_DIR / "xiaote_platform.sqlite3"
PLATFORM_DATABASE_URL = os.getenv("XIAOTE_PLATFORM_DATABASE_URL", "").strip()
DECOR_ROOT = BASE_DIR / "frontpart" / "frontpart" / "public" / "decor_info"
REFERENCE_FALLBACK_ROOT = DATA_DIR / "reference_data"

MATCH_DISPLAY_THRESHOLD = float(os.getenv("XIAOTE_MATCH_DISPLAY_THRESHOLD", "0.80"))
SESSION_DAYS = int(os.getenv("XIAOTE_SESSION_DAYS", "30"))
ROLE_CODE = os.getenv("XIAOTE_ROLE_CODE", "xiaote-internal-test")
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "").strip()
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "").strip()
ALLOW_DEV_PHONE_LOGIN = os.getenv("XIAOTE_ALLOW_DEV_PHONE_LOGIN", "false").strip().lower() in {"1", "true", "yes"}
SALES_CONTACT = {
    "name": os.getenv("XIAOTE_SALES_NAME", "Xiaote Sales"),
    "phone": os.getenv("XIAOTE_SALES_PHONE", "+86-000-0000-0000"),
    "email": os.getenv("XIAOTE_SALES_EMAIL", "sales@example.com"),
    "wechat": os.getenv("XIAOTE_SALES_WECHAT", "xiaote-sales"),
}
THUMBNAIL_MAX_SIZE = (520, 720)
THUMBNAIL_QUALITY = int(os.getenv("XIAOTE_THUMBNAIL_JPEG_QUALITY", "82"))
OSS_READ_ENABLED = os.getenv("XIAOTE_OSS_READ_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
OSS_BUCKET = os.getenv("OSS_BUCKET", "").strip()
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "oss-cn-shanghai.aliyuncs.com").strip().replace("https://", "").replace("http://", "").strip("/")
OSS_INTERNAL_ENDPOINT = os.getenv("OSS_INTERNAL_ENDPOINT", "oss-cn-shanghai-internal.aliyuncs.com").strip().replace("https://", "").replace("http://", "").strip("/")
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "").strip()
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "").strip()
OSS_DECOR_PREFIX = os.getenv("XIAOTE_OSS_DECOR_PREFIX", "ecs-backend/decor_info").strip("/")
OSS_THUMB_PREFIX = os.getenv("XIAOTE_OSS_THUMB_PREFIX", "ecs-backend/platform/pattern_thumbnails").strip("/")
OSS_LOCAL_FALLBACK = os.getenv("XIAOTE_OSS_LOCAL_FALLBACK", "true").strip().lower() in {"1", "true", "yes"}

router = APIRouter(prefix="/api", tags=["xiaote-platform"])

_catalog_cache: Optional[Dict[str, Dict[str, Any]]] = None
_initialized = False
_wechat_access_token = ""
_wechat_access_token_expires_at = 0.0
LOGIN_POLICY_EMPLOYEE_ONLY = "employee_only"
LOGIN_POLICY_OPEN = "open"
LOGIN_POLICY_KEY = "login_policy"
BROWSE_HISTORY_ACTIONS = ("view", "browse", "open_pattern", "view_pattern")
CATEGORY_ALIASES = {
    "木纹": {"木纹", "wood", "wood grain", "woodgrain"},
    "抽象": {"抽象", "abstract"},
    "石纹": {"石纹", "stone", "stone texture"},
    "素色": {"素色", "solid", "plain", "unicolor", "uni color"},
}
NO_AUXILIARY_CATEGORIES = {"", "不使用", "不使用辅助", "none", "no auxiliary", "off"}


def utc_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def utc_after(days: int) -> str:
    return (dt.datetime.utcnow() + dt.timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def normalize_login_policy(value: Optional[str]) -> str:
    return LOGIN_POLICY_OPEN if value == LOGIN_POLICY_OPEN else LOGIN_POLICY_EMPLOYEE_ONLY


def platform_db_is_mysql() -> bool:
    return PLATFORM_DATABASE_URL.startswith(("mysql://", "mysql+pymysql://"))


def mysql_params_from_url(url: str) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise RuntimeError("XIAOTE_PLATFORM_DATABASE_URL must start with mysql+pymysql:// or mysql://")
    query = urllib.parse.parse_qs(parsed.query)
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": urllib.parse.unquote(parsed.username or ""),
        "password": urllib.parse.unquote(parsed.password or ""),
        "database": (parsed.path or "").lstrip("/"),
        "charset": query.get("charset", ["utf8mb4"])[0],
        "cursorclass": pymysql.cursors.DictCursor if pymysql else None,
        "autocommit": False,
    }


class MySQLConnection:
    def __init__(self, raw: Any):
        self.raw = raw

    def execute(self, sql: str, params: Iterable[Any] = ()):
        cursor = self.raw.cursor()
        cursor.execute(self._translate_sql(sql), tuple(params or ()))
        return cursor

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()

    @staticmethod
    def _translate_sql(sql: str) -> str:
        return sql.replace("?", "%s")


def db_integrity_errors() -> Tuple[type, ...]:
    errors: Tuple[type, ...] = (sqlite3.IntegrityError,)
    if pymysql is not None:
        errors = errors + (pymysql.err.IntegrityError,)
    return errors


@contextmanager
def db_connection():
    PLATFORM_DIR.mkdir(parents=True, exist_ok=True)
    if platform_db_is_mysql():
        if pymysql is None:
            raise RuntimeError("PyMySQL is required when XIAOTE_PLATFORM_DATABASE_URL points to MySQL")
        conn = MySQLConnection(pymysql.connect(**mysql_params_from_url(PLATFORM_DATABASE_URL)))
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_app_setting(key: str, default: str, conn: Optional[sqlite3.Connection] = None) -> str:
    def read(active_conn: sqlite3.Connection) -> str:
        column = "setting_key" if platform_db_is_mysql() else "key"
        row = active_conn.execute(f"SELECT value FROM app_settings WHERE {column} = ?", (key,)).fetchone()
        return row["value"] if row else default

    try:
        if conn is not None:
            return read(conn)
        with db_connection() as own_conn:
            return read(own_conn)
    except Exception:
        return default


def get_login_policy(conn: Optional[sqlite3.Connection] = None) -> str:
    return normalize_login_policy(get_app_setting(LOGIN_POLICY_KEY, LOGIN_POLICY_EMPLOYEE_ONLY, conn))


def set_login_policy(conn: sqlite3.Connection, policy: str, updated_by: Optional[str] = None) -> str:
    normalized = normalize_login_policy(policy)
    if platform_db_is_mysql():
        conn.execute(
            """
            INSERT INTO app_settings(setting_key, value, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = VALUES(updated_at), updated_by = VALUES(updated_by)
            """,
            (LOGIN_POLICY_KEY, normalized, utc_now(), updated_by),
        )
    else:
        conn.execute(
            """
            INSERT INTO app_settings(key, value, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by
            """,
            (LOGIN_POLICY_KEY, normalized, utc_now(), updated_by),
        )
    return normalized


def init_mysql_platform(conn: MySQLConnection) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(191) NOT NULL UNIQUE,
            phone VARCHAR(32) UNIQUE,
            email VARCHAR(255),
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'visitor',
            language VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
            created_at VARCHAR(32) NOT NULL,
            last_login_at VARCHAR(32),
            wechat_openid VARCHAR(191) UNIQUE,
            status VARCHAR(32) NOT NULL DEFAULT 'active'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token VARCHAR(191) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            created_at VARCHAR(32) NOT NULL,
            expires_at VARCHAR(32) NOT NULL,
            INDEX idx_sessions_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64),
            event_type VARCHAR(64) NOT NULL,
            pattern_id VARCHAR(128),
            payload_json LONGTEXT,
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_events_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS history (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            action VARCHAR(64) NOT NULL,
            query TEXT,
            pattern_id VARCHAR(128),
            payload_json LONGTEXT,
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_history_user_created (user_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS favorites (
            user_id VARCHAR(64) NOT NULL,
            pattern_id VARCHAR(128) NOT NULL,
            created_at VARCHAR(32) NOT NULL,
            PRIMARY KEY(user_id, pattern_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64),
            recognition_id VARCHAR(128),
            pattern_id VARCHAR(128),
            verdict VARCHAR(64) NOT NULL,
            correct_pattern_id VARCHAR(128),
            note TEXT,
            image_path TEXT,
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_feedback_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS unmatched_records (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64),
            image_path TEXT,
            top_results_json LONGTEXT,
            reason TEXT,
            category VARCHAR(64),
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_unmatched_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS leads (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64),
            answers_json LONGTEXT NOT NULL,
            contact_json LONGTEXT NOT NULL,
            created_at VARCHAR(32) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS service_leads (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64),
            phone VARCHAR(32),
            profession_id VARCHAR(64),
            profession_label VARCHAR(255),
            region_id VARCHAR(64),
            region_label VARCHAR(255),
            contact_json LONGTEXT NOT NULL,
            messages_json LONGTEXT NOT NULL,
            language VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
            source VARCHAR(64) NOT NULL DEFAULT 'service_chat',
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_service_leads_created (created_at),
            INDEX idx_service_leads_user_created (user_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS training_data (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64),
            pattern_id VARCHAR(128),
            category VARCHAR(64),
            image_path TEXT NOT NULL,
            note TEXT,
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_training_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS sample_orders (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            pattern_id VARCHAR(128) NOT NULL,
            quantity INT NOT NULL DEFAULT 1,
            note TEXT,
            status VARCHAR(64) NOT NULL DEFAULT 'created',
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_sample_orders_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS managed_users (
            id VARCHAR(64) PRIMARY KEY,
            phone VARCHAR(32) NOT NULL UNIQUE,
            display_name VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'employee',
            enabled TINYINT NOT NULL DEFAULT 1,
            note TEXT,
            user_id VARCHAR(64),
            created_at VARCHAR(32) NOT NULL,
            updated_at VARCHAR(32) NOT NULL,
            INDEX idx_managed_users_phone (phone)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS phone_login_attempts (
            id VARCHAR(64) PRIMARY KEY,
            phone VARCHAR(32) NOT NULL,
            openid_hash VARCHAR(64),
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            attempt_count INT NOT NULL DEFAULT 1,
            first_attempt_at VARCHAR(32) NOT NULL,
            last_attempt_at VARCHAR(32) NOT NULL,
            reviewed_by VARCHAR(64),
            reviewed_at VARCHAR(32),
            note TEXT,
            INDEX idx_phone_attempts_status_last (status, last_attempt_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key VARCHAR(191) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at VARCHAR(32) NOT NULL,
            updated_by VARCHAR(64)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ]
    for statement in statements:
        conn.execute(statement)
    set_login_policy(conn, get_login_policy(conn))


def init_platform() -> None:
    global _initialized
    PLATFORM_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    with db_connection() as conn:
        if platform_db_is_mysql():
            init_mysql_platform(conn)
            _initialized = True
            return

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                phone TEXT,
                email TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'visitor',
                language TEXT NOT NULL DEFAULT 'zh-CN',
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                event_type TEXT NOT NULL,
                pattern_id TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                query TEXT,
                pattern_id TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS favorites (
                user_id TEXT NOT NULL,
                pattern_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id, pattern_id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                recognition_id TEXT,
                pattern_id TEXT,
                verdict TEXT NOT NULL,
                correct_pattern_id TEXT,
                note TEXT,
                image_path TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unmatched_records (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                image_path TEXT,
                top_results_json TEXT,
                reason TEXT,
                category TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                answers_json TEXT NOT NULL,
                contact_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS service_leads (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                phone TEXT,
                profession_id TEXT,
                profession_label TEXT,
                region_id TEXT,
                region_label TEXT,
                contact_json TEXT NOT NULL,
                messages_json TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'zh-CN',
                source TEXT NOT NULL DEFAULT 'service_chat',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS training_data (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                pattern_id TEXT,
                category TEXT,
                image_path TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sample_orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                pattern_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                status TEXT NOT NULL DEFAULT 'created',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS managed_users (
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                enabled INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                user_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS phone_login_attempts (
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                openid_hash TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 1,
                first_attempt_at TEXT NOT NULL,
                last_attempt_at TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TEXT,
                note TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_history_user_created ON history(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_unmatched_created ON unmatched_records(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_service_leads_created ON service_leads(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_service_leads_user_created ON service_leads(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_training_created ON training_data(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sample_orders_created ON sample_orders(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_managed_users_phone ON managed_users(phone);
            CREATE INDEX IF NOT EXISTS idx_phone_attempts_status_last ON phone_login_attempts(status, last_attempt_at DESC);
            """
        )

        conn.execute(
            "INSERT OR IGNORE INTO app_settings(key, value, updated_at) VALUES (?, ?, ?)",
            (LOGIN_POLICY_KEY, LOGIN_POLICY_EMPLOYEE_ONLY, utc_now()),
        )

        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "wechat_openid" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN wechat_openid TEXT")
        if "status" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique ON users(phone) WHERE phone IS NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_openid_unique ON users(wechat_openid) WHERE wechat_openid IS NOT NULL")

    _initialized = True


def ensure_platform() -> None:
    if not _initialized:
        init_platform()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 120000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, rounds_text, salt_hex, digest_hex = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(rounds_text),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    if not re.fullmatch(r"1\d{10}", digits):
        raise HTTPException(status_code=400, detail="Invalid mobile phone number")
    return digits


def wechat_json(url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"WeChat service unavailable: {type(error).__name__}")
    if result.get("errcode") not in (None, 0):
        raise HTTPException(status_code=502, detail=f"WeChat API error {result.get('errcode')}: {result.get('errmsg', '')}")
    return result


def require_wechat_credentials() -> None:
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise HTTPException(status_code=503, detail="WeChat phone login is not configured")


def wechat_access_token() -> str:
    global _wechat_access_token, _wechat_access_token_expires_at
    require_wechat_credentials()
    if _wechat_access_token and time.time() < _wechat_access_token_expires_at - 120:
        return _wechat_access_token
    result = wechat_json(
        "https://api.weixin.qq.com/cgi-bin/stable_token",
        {"grant_type": "client_credential", "appid": WECHAT_APP_ID, "secret": WECHAT_APP_SECRET, "force_refresh": False},
    )
    token = result.get("access_token") or ""
    if not token:
        raise HTTPException(status_code=502, detail="WeChat access token missing")
    _wechat_access_token = token
    _wechat_access_token_expires_at = time.time() + int(result.get("expires_in") or 7200)
    return token


def exchange_wechat_phone(phone_code: str, dev_phone: Optional[str] = None) -> str:
    if ALLOW_DEV_PHONE_LOGIN and dev_phone:
        return normalize_phone(dev_phone)
    if not phone_code:
        raise HTTPException(status_code=400, detail="WeChat phone code is required")
    token = urllib.parse.quote(wechat_access_token(), safe="")
    result = wechat_json(
        f"https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token={token}",
        {"code": phone_code},
    )
    phone_info = result.get("phone_info") or {}
    return normalize_phone(phone_info.get("purePhoneNumber") or phone_info.get("phoneNumber") or "")


def exchange_wechat_openid(login_code: str, dev_openid: Optional[str] = None) -> str:
    if ALLOW_DEV_PHONE_LOGIN and dev_openid:
        return dev_openid.strip()
    require_wechat_credentials()
    if not login_code:
        raise HTTPException(status_code=400, detail="WeChat login code is required")
    params = urllib.parse.urlencode({
        "appid": WECHAT_APP_ID,
        "secret": WECHAT_APP_SECRET,
        "js_code": login_code,
        "grant_type": "authorization_code",
    })
    result = wechat_json(f"https://api.weixin.qq.com/sns/jscode2session?{params}")
    openid = result.get("openid") or ""
    if not openid:
        raise HTTPException(status_code=502, detail="WeChat OpenID missing")
    return openid


def record_phone_login_attempt(conn: sqlite3.Connection, phone: str, openid: str, note: str = "") -> str:
    now = utc_now()
    row = conn.execute(
        "SELECT * FROM phone_login_attempts WHERE phone = ? AND status = 'pending' ORDER BY last_attempt_at DESC LIMIT 1",
        (phone,),
    ).fetchone()
    openid_hash = hashlib.sha256(openid.encode("utf-8")).hexdigest()[:24] if openid else None
    if row:
        conn.execute(
            "UPDATE phone_login_attempts SET attempt_count = attempt_count + 1, last_attempt_at = ?, openid_hash = ?, note = ? WHERE id = ?",
            (now, openid_hash, note, row["id"]),
        )
        return row["id"]
    attempt_id = uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO phone_login_attempts(id, phone, openid_hash, status, attempt_count, first_attempt_at, last_attempt_at, note)
        VALUES (?, ?, ?, 'pending', 1, ?, ?, ?)
        """,
        (attempt_id, phone, openid_hash, now, now, note),
    )
    return attempt_id


def upsert_managed_user_record(
    conn: sqlite3.Connection,
    phone: str,
    display_name: str,
    role: str,
    enabled: bool,
    note: Optional[str] = None,
) -> sqlite3.Row:
    now = utc_now()
    existing = conn.execute("SELECT * FROM managed_users WHERE phone = ?", (phone,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE managed_users SET display_name = ?, role = ?, enabled = ?, note = ?, updated_at = ? WHERE id = ?",
            (display_name.strip(), role, int(enabled), note, now, existing["id"]),
        )
        managed_id = existing["id"]
    else:
        managed_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO managed_users(id, phone, display_name, role, enabled, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (managed_id, phone, display_name.strip(), role, int(enabled), note, now, now),
        )
    linked_user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    if linked_user:
        status = "active" if enabled else "disabled"
        conn.execute("UPDATE users SET role = ?, status = ? WHERE id = ?", (role, status, linked_user["id"]))
        conn.execute("UPDATE managed_users SET user_id = ? WHERE id = ?", (linked_user["id"], managed_id))
        if not enabled:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (linked_user["id"],))
    return conn.execute("SELECT * FROM managed_users WHERE id = ?", (managed_id,)).fetchone()


def upsert_backend_account(
    conn: sqlite3.Connection,
    phone: str,
    username: str,
    password: str,
    role: str,
) -> sqlite3.Row:
    normalized_username = username.strip()
    if not normalized_username:
        raise HTTPException(status_code=400, detail="Backend username is required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Backend password must be at least 8 characters")

    existing = conn.execute(
        "SELECT * FROM users WHERE username = ? OR phone = ? ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END LIMIT 1",
        (normalized_username, phone, normalized_username),
    ).fetchone()
    password_hash = hash_password(password)
    if existing:
        conn.execute(
            """
            UPDATE users
            SET username = ?, phone = ?, password_hash = ?, role = ?, language = COALESCE(language, 'zh-CN'), status = 'active'
            WHERE id = ?
            """,
            (normalized_username, phone, password_hash, role, existing["id"]),
        )
        user_id = existing["id"]
    else:
        user_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO users(id, username, phone, password_hash, role, language, created_at, status)
            VALUES (?, ?, ?, ?, ?, 'zh-CN', ?, 'active')
            """,
            (user_id, normalized_username, phone, password_hash, role, utc_now()),
        )
    conn.execute("UPDATE managed_users SET user_id = ?, updated_at = ? WHERE phone = ?", (user_id, utc_now(), phone))
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def public_user(row: sqlite3.Row, login_policy: Optional[str] = None) -> Dict[str, Any]:
    policy = normalize_login_policy(login_policy or get_login_policy())
    return {
        "id": row["id"],
        "username": row["username"],
        "phone": row["phone"],
        "email": row["email"],
        "role": row["role"],
        "language": row["language"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
        "status": row["status"] if "status" in row.keys() else "active",
        "access_mode": policy,
        "is_guest": policy == LOGIN_POLICY_OPEN,
    }


def token_from_headers(authorization: Optional[str], x_user_token: Optional[str] = None) -> Optional[str]:
    if x_user_token:
        return x_user_token.strip()
    if not authorization:
        return None
    value = authorization.strip()
    parts = value.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return value or None


def user_from_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    ensure_platform()
    with db_connection() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
        if not session:
            return None
        if session["expires_at"] < utc_now():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if user and "status" in user.keys() and user["status"] != "active":
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
            return None
        return public_user(user, get_login_policy(conn)) if user else None


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
    x_user_token: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    return user_from_token(token_from_headers(authorization, x_user_token))


def get_current_user(user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def require_roles(roles: Iterable[str]):
    allowed = set(roles)

    def dependency(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Permission denied")
        return user

    return dependency


def get_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    return user_from_token(
        token_from_headers(
            request.headers.get("authorization"),
            request.headers.get("x-user-token"),
        )
    )


def create_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, utc_now(), utc_after(SESSION_DAYS)),
    )
    return token


def load_json_file(path: Path) -> Dict[str, Any]:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return json.loads(path.read_text(encoding=encoding))
        except UnicodeDecodeError:
            continue
        except Exception:
            return {}
    return {}


def image_for_pattern(pattern_dir: Path, pattern_id: str) -> Optional[Path]:
    preferred = pattern_dir / f"{pattern_id}.jpg"
    if preferred.exists():
        return preferred
    for suffix in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        matches = list(pattern_dir.glob(suffix))
        if matches:
            return matches[0]
    return None


def safe_thumbnail_name(pattern_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", pattern_id or "pattern")


def ensure_pattern_thumbnail(pattern_id: str, item: Dict[str, Any]) -> Path:
    source = Path(item.get("_image_path") or "")
    if not source.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    thumb_path = THUMBNAIL_DIR / f"{safe_thumbnail_name(pattern_id)}.jpg"
    if thumb_path.exists() and thumb_path.stat().st_mtime >= source.stat().st_mtime:
        return thumb_path

    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    resample_lanczos = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail(THUMBNAIL_MAX_SIZE, resample_lanczos)
        img.save(thumb_path, "JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
    return thumb_path


def oss_configured() -> bool:
    return bool(OSS_READ_ENABLED and OSS_BUCKET and OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET)


def oss_key_from_local_path(local_path: str, root: Path, prefix: str) -> Optional[str]:
    try:
        relative = Path(local_path).resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return None
    return f"{prefix}/{relative}" if prefix else relative


def oss_thumbnail_key(pattern_id: str) -> str:
    name = safe_thumbnail_name(pattern_id)
    return f"{OSS_THUMB_PREFIX}/{name}.jpg" if OSS_THUMB_PREFIX else f"{name}.jpg"


def oss_signed_request(method: str, key: str, endpoint: str) -> urllib.request.Request:
    date_text = dt.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    canonical = f"{method}\n\n\n{date_text}\n/{OSS_BUCKET}/{key}"
    signature = base64.b64encode(
        hmac.new(OSS_ACCESS_KEY_SECRET.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    quoted_key = "/".join(urllib.parse.quote(part, safe="") for part in key.split("/"))
    url = f"https://{OSS_BUCKET}.{endpoint}/{quoted_key}"
    return urllib.request.Request(url, method=method, headers={
        "Date": date_text,
        "Authorization": f"OSS {OSS_ACCESS_KEY_ID}:{signature}",
    })


def oss_get_object(key: str) -> Tuple[bytes, str]:
    if not oss_configured():
        raise RuntimeError("OSS image reading is not configured")
    endpoints = [value for value in (OSS_INTERNAL_ENDPOINT, OSS_ENDPOINT) if value]
    last_error: Optional[Exception] = None
    for endpoint in dict.fromkeys(endpoints):
        try:
            request = oss_signed_request("GET", key, endpoint)
            with urllib.request.urlopen(request, timeout=12) as response:
                content_type = response.headers.get("Content-Type") or mimetypes.guess_type(key)[0] or "application/octet-stream"
                return response.read(), content_type
        except Exception as error:
            last_error = error
    raise RuntimeError(f"OSS object read failed: {type(last_error).__name__ if last_error else 'unknown'}")


def oss_or_local_file_response(
    key: Optional[str],
    local_path: str,
    media_type: Optional[str] = None,
) -> Response:
    headers = {"Cache-Control": "public, max-age=604800"}
    if key and oss_configured():
        try:
            data, content_type = oss_get_object(key)
            return Response(
                content=data,
                media_type=media_type or content_type,
                headers={**headers, "X-Image-Source": "oss"},
            )
        except Exception:
            if not OSS_LOCAL_FALLBACK:
                raise HTTPException(status_code=502, detail="OSS image unavailable")
    return FileResponse(local_path, media_type=media_type, headers={**headers, "X-Image-Source": "local"})


def catalog_item(pattern_dir: Path, pattern_id: str, source: str) -> Optional[Dict[str, Any]]:
    info = load_json_file(pattern_dir / "info.json")
    if not info:
        info = load_json_file(pattern_dir / "metadata.json")
    image_path = image_for_pattern(pattern_dir, pattern_id)
    if not image_path:
        return None
    name = info.get("decorName") or pattern_id
    return {
        "pattern_id": pattern_id,
        "code": pattern_id,
        "name": name,
        "decor_name": name,
        "texture_name": info.get("textureName") or "",
        "usage_name": info.get("usageName") or "",
        "wood_art_name": info.get("woodArtName") or "",
        "tags": info.get("tags") or [],
        "image_url": f"/api/patterns/{pattern_id}/thumbnail",
        "thumbnail_url": f"/api/patterns/{pattern_id}/thumbnail",
        "full_image_url": f"/api/patterns/{pattern_id}/image",
        "has_image": True,
        "catalog_source": source,
        "_image_path": str(image_path),
        "_oss_image_key": oss_key_from_local_path(str(image_path), DECOR_ROOT, OSS_DECOR_PREFIX) if source == "published" else None,
        "_oss_thumbnail_key": oss_thumbnail_key(pattern_id) if source == "published" else None,
    }


def get_pattern_catalog(force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
    global _catalog_cache
    if _catalog_cache is not None and not force_reload:
        return _catalog_cache

    catalog: Dict[str, Dict[str, Any]] = {}
    if DECOR_ROOT.exists():
        for pattern_dir in sorted(p for p in DECOR_ROOT.iterdir() if p.is_dir()):
            pattern_id = pattern_dir.name
            item = catalog_item(pattern_dir, pattern_id, "published")
            if item:
                catalog[pattern_id] = item

    # Keep model classes displayable during local validation when only labeled
    # reference photos exist. Official catalog images always take precedence.
    if REFERENCE_FALLBACK_ROOT.exists():
        for pattern_dir in sorted(p for p in REFERENCE_FALLBACK_ROOT.iterdir() if p.is_dir()):
            pattern_id = pattern_dir.name
            if pattern_id in catalog:
                continue
            item = catalog_item(pattern_dir, pattern_id, "reference_fallback")
            if item:
                catalog[pattern_id] = item

    _catalog_cache = catalog
    return catalog


def public_pattern(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def attach_pattern_info(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    catalog = get_pattern_catalog()
    enriched = []
    for result in results:
        pattern_id = result.get("pattern_id")
        item = dict(result)
        if pattern_id in catalog:
            item.update(public_pattern(catalog[pattern_id]))
        enriched.append(item)
    return enriched


def normalize_category_filter(category: str = "") -> str:
    """Treat the explicit no-auxiliary option as an unrestricted candidate set."""
    raw = (category or "").strip()
    if raw.lower() in NO_AUXILIARY_CATEGORIES:
        return ""
    return raw


def category_terms(category: str) -> set[str]:
    raw = normalize_category_filter(category).lower()
    if not raw:
        return set()
    for canonical, aliases in CATEGORY_ALIASES.items():
        lowered = {alias.lower() for alias in aliases}
        if raw == canonical.lower() or raw in lowered:
            return lowered | {canonical.lower()}
    return {raw}


def pattern_matches_category(item: Dict[str, Any], category: str = "") -> bool:
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


def filter_pattern_results(results: List[Dict[str, Any]], category: str = "") -> List[Dict[str, Any]]:
    category_filter = normalize_category_filter(category)
    if not category_filter:
        return results
    catalog = get_pattern_catalog()
    filtered = []
    for result in results:
        item = catalog.get(result.get("pattern_id"))
        if item and pattern_matches_category(item, category_filter):
            filtered.append(result)
    return filtered


def save_uploaded_image(file_bytes: bytes, filename: Optional[str]) -> Optional[str]:
    ensure_platform()
    suffix = Path(filename or "image.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    name = f"{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex}{suffix}"
    path = UPLOAD_DIR / name
    path.write_bytes(file_bytes)
    return str(path)


def save_training_image(file_bytes: bytes, filename: Optional[str]) -> Optional[str]:
    ensure_platform()
    suffix = Path(filename or "image.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    name = f"{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex}{suffix}"
    path = TRAINING_DIR / name
    path.write_bytes(file_bytes)
    return str(path)


def save_base64_image(image_base64: Optional[str]) -> Optional[str]:
    if not image_base64:
        return None
    ensure_platform()
    try:
        data = image_base64
        if "," in data:
            data = data.split(",", 1)[1]
        image_bytes = base64.b64decode(data)
        path = FEEDBACK_DIR / f"{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex}.jpg"
        path.write_bytes(image_bytes)
        return str(path)
    except Exception:
        return None


def record_event(
    event_type: str,
    user_id: Optional[str] = None,
    pattern_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    ensure_platform()
    event_id = uuid.uuid4().hex
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO events(id, user_id, event_type, pattern_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, user_id, event_type, pattern_id, json_dumps(payload or {}), utc_now()),
        )
    return event_id


def add_history(
    user_id: str,
    action: str,
    query: Optional[str] = None,
    pattern_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    ensure_platform()
    with db_connection() as conn:
        if action in BROWSE_HISTORY_ACTIONS and pattern_id:
            placeholders = ",".join("?" for _ in BROWSE_HISTORY_ACTIONS)
            conn.execute(
                f"""
                DELETE FROM history
                WHERE user_id = ? AND pattern_id = ? AND action IN ({placeholders})
                """,
                (user_id, pattern_id, *BROWSE_HISTORY_ACTIONS),
            )
        conn.execute(
            """
            INSERT INTO history(id, user_id, action, query, pattern_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, user_id, action, query, pattern_id, json_dumps(payload or {}), utc_now()),
        )


def record_recognition_result(
    request: Request,
    image_path: Optional[str],
    all_top_results: List[Dict[str, Any]],
    visible_results: List[Dict[str, Any]],
    status: str,
    reason: str,
    category: Optional[str] = None,
    threshold: Optional[float] = None,
) -> Optional[str]:
    try:
        user = get_user_from_request(request)
        recognition_id = uuid.uuid4().hex
        payload = {
            "status": status,
            "reason": reason,
            "threshold": MATCH_DISPLAY_THRESHOLD if threshold is None else threshold,
            "visible_results": visible_results,
            "all_top_results": all_top_results,
        }
        record_event("recognition", user["id"] if user else None, None, payload)
        if user:
            add_history(
                user["id"],
                "recognition",
                pattern_id=visible_results[0]["pattern_id"] if visible_results else None,
                payload=payload,
            )
        if status != "matched":
            with db_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO unmatched_records(id, user_id, image_path, top_results_json, reason, category, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        recognition_id,
                        user["id"] if user else None,
                        image_path,
                        json_dumps(all_top_results),
                        reason,
                        category,
                        utc_now(),
                    ),
                )
        return recognition_id
    except Exception:
        return None


def row_payload(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    for key in list(data.keys()):
        if key.endswith("_json"):
            data[key[:-5]] = json_loads(data.pop(key), {})
    return data


def favorite_ids_for_user(user_id: Optional[str]) -> set[str]:
    if not user_id:
        return set()
    with db_connection() as conn:
        rows = conn.execute("SELECT pattern_id FROM favorites WHERE user_id = ?", (user_id,)).fetchall()
    return {row["pattern_id"] for row in rows}


FULL_PATTERN_ID_RE = re.compile(r"^\d{2}-\d{5}-\d{3}$")


def pattern_family_id(pattern_id: str) -> str:
    parts = (pattern_id or "").split("-")
    if len(parts) >= 3:
        return parts[1]
    return ""


def digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def resolve_pattern_search_mode(query: str = "", search_mode: str = "auto") -> str:
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


def keyword_score(item: Dict[str, Any], query: str) -> int:
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


def find_patterns(
    query: str = "",
    category: str = "",
    limit: int = 10,
    search_mode: str = "auto",
) -> List[Dict[str, Any]]:
    category_filter = normalize_category_filter(category)
    catalog = [
        item
        for item in get_pattern_catalog().values()
        if pattern_matches_category(item, category_filter)
    ]
    q = (query or "").strip().lower()
    mode = resolve_pattern_search_mode(q, search_mode)
    result_limit = max(1, min(limit, 50))

    if not q:
        results = sorted(catalog, key=lambda item: item["pattern_id"])
        return [public_pattern(item) for item in results[:result_limit]]

    exact = [item for item in catalog if item["pattern_id"].lower() == q]
    if exact:
        return [public_pattern(exact[0])]
    if mode == "exact":
        return []

    if mode == "family":
        family_results = [item for item in catalog if pattern_family_id(item["pattern_id"]).lower() == q]
        if not family_results:
            query_digits = digits_only(q)
            family_results = [
                item
                for item in catalog
                if query_digits and query_digits in digits_only(item["pattern_id"])
            ]
        family_results.sort(key=lambda item: item["pattern_id"])
        return [public_pattern(item) for item in family_results[: min(result_limit, 5)]]

    scored = [(keyword_score(item, q), item) for item in catalog]
    results = [(score, item) for score, item in scored if score > 0]
    results.sort(key=lambda pair: (-pair[0], pair[1]["pattern_id"]))
    return [public_pattern(item) for _, item in results[: min(result_limit, 5)]]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str = "visitor"
    access_code: Optional[str] = None
    language: str = Field(default="zh-CN", pattern="^(zh-CN|en-US|de-DE)$")


class LoginRequest(BaseModel):
    username: str
    password: str


class WechatLoginRequest(BaseModel):
    code: str
    dev_openid: Optional[str] = None
    nickname: Optional[str] = None
    role: str = "visitor"
    access_code: Optional[str] = None
    language: str = Field(default="zh-CN", pattern="^(zh-CN|en-US|de-DE)$")


class WechatPhoneLoginRequest(BaseModel):
    phone_code: str = ""
    login_code: str = ""
    dev_phone: Optional[str] = None
    dev_openid: Optional[str] = None
    language: str = Field(default="zh-CN", pattern="^(zh-CN|en-US|de-DE)$")


class ManagedUserRequest(BaseModel):
    phone: str
    display_name: str = Field(min_length=1, max_length=64)
    role: str = Field(default="employee", pattern="^(employee|sales|admin)$")
    enabled: bool = True
    note: Optional[str] = Field(default=None, max_length=500)
    admin_password: Optional[str] = Field(default=None, max_length=128)


class PhoneAttemptDecisionRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=64)
    role: str = Field(default="employee", pattern="^(employee|sales|admin)$")
    note: Optional[str] = Field(default=None, max_length=500)


class LoginPolicyRequest(BaseModel):
    policy: str = Field(pattern="^(employee_only|open)$")


class FavoriteRequest(BaseModel):
    pattern_id: str


class FeedbackRequest(BaseModel):
    verdict: str = Field(pattern="^(accurate|inaccurate)$")
    pattern_id: Optional[str] = None
    correct_pattern_id: Optional[str] = None
    recognition_id: Optional[str] = None
    note: Optional[str] = None
    image_base64: Optional[str] = None


class EventRequest(BaseModel):
    event_type: str
    pattern_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class LeadRequest(BaseModel):
    industry: str
    region: str
    project_type: Optional[str] = None
    volume: Optional[str] = None
    note: Optional[str] = None


class ServiceLeadRequest(BaseModel):
    profession_id: str = Field(min_length=1, max_length=16)
    profession_label: str = Field(min_length=1, max_length=120)
    region_id: str = Field(min_length=1, max_length=16)
    region_label: str = Field(min_length=1, max_length=120)
    contact: Dict[str, Any] = Field(default_factory=dict)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    language: str = Field(default="zh-CN", pattern="^(zh-CN|en-US|de-DE)$")
    source: str = Field(default="service_chat", max_length=64)


class PreferencesRequest(BaseModel):
    language: str = Field(pattern="^(zh-CN|en-US|de-DE)$")


class SampleOrderRequest(BaseModel):
    pattern_id: str
    quantity: int = Field(default=1, ge=1, le=99)
    note: Optional[str] = None


@router.post("/auth/register")
async def register_user(body: RegisterRequest):
    ensure_platform()
    role = body.role if body.role in {"employee", "sales", "admin"} else "employee"
    if body.access_code != ROLE_CODE:
        raise HTTPException(status_code=403, detail="Invalid internal access code")

    user_id = uuid.uuid4().hex
    with db_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users(id, username, phone, email, password_hash, role, language, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    body.username.strip(),
                    body.phone,
                    body.email,
                    hash_password(body.password),
                    role,
                    body.language,
                    utc_now(),
                ),
            )
        except db_integrity_errors():
            raise HTTPException(status_code=409, detail="Username already exists")
        token = create_session(conn, user_id)
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    record_event("register", user_id, payload={"role": role})
    return {"token": token, "user": public_user(user)}


@router.post("/auth/login")
async def login_user(body: LoginRequest):
    ensure_platform()
    with db_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (body.username.strip(),)).fetchone()
        if not user or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if "status" in user.keys() and user["status"] != "active":
            raise HTTPException(status_code=403, detail="Account disabled")
        token = create_session(conn, user["id"])
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user["id"]))
        refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()

    record_event("login", user["id"])
    return {"token": token, "user": public_user(refreshed, LOGIN_POLICY_EMPLOYEE_ONLY)}


@router.post("/auth/wechat-login")
async def wechat_login(body: WechatLoginRequest):
    ensure_platform()
    if not ALLOW_DEV_PHONE_LOGIN:
        raise HTTPException(status_code=403, detail="Phone authorization is required")
    role = body.role if body.role in {"visitor", "sales", "admin"} else "visitor"
    if role != "visitor" and body.access_code != ROLE_CODE:
        raise HTTPException(status_code=403, detail="Invalid internal access code")

    local_identity = body.dev_openid or body.code
    openid_stub = hashlib.sha256(local_identity.encode("utf-8")).hexdigest()[:16]
    username = f"wx_{openid_stub}"
    with db_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            conn.execute(
                """
                INSERT INTO users(id, username, password_hash, role, language, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, username, hash_password(secrets.token_urlsafe(24)), role, body.language, utc_now()),
            )
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        elif user["language"] != body.language:
            conn.execute("UPDATE users SET language = ? WHERE id = ?", (body.language, user["id"]))
        token = create_session(conn, user["id"])
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user["id"]))
        refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()

    record_event("wechat_login", refreshed["id"], payload={"nickname": body.nickname})
    return {"token": token, "user": public_user(refreshed, LOGIN_POLICY_EMPLOYEE_ONLY)}


@router.post("/auth/wechat-phone-login")
async def wechat_phone_login(body: WechatPhoneLoginRequest):
    ensure_platform()
    phone = exchange_wechat_phone(body.phone_code, body.dev_phone)
    openid = exchange_wechat_openid(body.login_code, body.dev_openid)
    blocked_attempt_id: Optional[str] = None

    with db_connection() as conn:
        login_policy = get_login_policy(conn)
        if login_policy == LOGIN_POLICY_OPEN:
            user = conn.execute("SELECT * FROM users WHERE wechat_openid = ?", (openid,)).fetchone()
            if not user:
                openid_stub = hashlib.sha256(openid.encode("utf-8")).hexdigest()[:16]
                username = f"wx_guest_{openid_stub}"
                suffix = 1
                while conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                    suffix += 1
                    username = f"wx_guest_{openid_stub}_{suffix}"
                user_id = uuid.uuid4().hex
                conn.execute(
                    """
                    INSERT INTO users(id, username, password_hash, role, language, created_at, wechat_openid, status)
                    VALUES (?, ?, ?, 'visitor', ?, ?, ?, 'active')
                    """,
                    (
                        user_id,
                        username,
                        hash_password(secrets.token_urlsafe(32)),
                        body.language,
                        utc_now(),
                        openid,
                    ),
                )
                user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            else:
                conn.execute(
                    "UPDATE users SET language = ?, status = 'active' WHERE id = ?",
                    (body.language, user["id"]),
                )
            token = create_session(conn, user["id"])
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user["id"]))
            refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
            conn.execute(
                """
                INSERT INTO events(id, user_id, event_type, pattern_id, payload_json, created_at)
                VALUES (?, ?, 'wechat_phone_guest_login', NULL, ?, ?)
                """,
                (uuid.uuid4().hex, refreshed["id"], json_dumps({"phone_suffix": phone[-4:]}), utc_now()),
            )
            return {"token": token, "user": public_user(refreshed, login_policy)}

        managed = conn.execute("SELECT * FROM managed_users WHERE phone = ?", (phone,)).fetchone()
        if not managed or not bool(managed["enabled"]):
            blocked_attempt_id = record_phone_login_attempt(
                conn,
                phone,
                openid,
                "phone_not_configured" if not managed else "phone_disabled",
            )
        else:
            openid_user = conn.execute("SELECT * FROM users WHERE wechat_openid = ?", (openid,)).fetchone()
            phone_user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            if openid_user and phone_user and openid_user["id"] != phone_user["id"]:
                if openid_user["role"] == "visitor" and not openid_user["phone"]:
                    conn.execute(
                        "UPDATE users SET wechat_openid = NULL, status = 'merged' WHERE id = ?",
                        (openid_user["id"],),
                    )
                    user = phone_user
                else:
                    raise HTTPException(status_code=409, detail="WeChat account and phone are bound to different users")
            else:
                user = phone_user or openid_user
            if not user:
                username_base = f"{managed['display_name'].strip()}_{phone[-4:]}"
                username = username_base
                suffix = 1
                while conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                    suffix += 1
                    username = f"{username_base}_{suffix}"
                user_id = uuid.uuid4().hex
                conn.execute(
                    """
                    INSERT INTO users(id, username, phone, password_hash, role, language, created_at, wechat_openid, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        user_id,
                        username,
                        phone,
                        hash_password(secrets.token_urlsafe(32)),
                        managed["role"],
                        body.language,
                        utc_now(),
                        openid,
                    ),
                )
                user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            else:
                conn.execute(
                    "UPDATE users SET phone = ?, wechat_openid = ?, role = ?, language = ?, status = 'active' WHERE id = ?",
                    (phone, openid, managed["role"], body.language, user["id"]),
                )
            conn.execute("UPDATE managed_users SET user_id = ?, updated_at = ? WHERE id = ?", (user["id"], utc_now(), managed["id"]))
            conn.execute(
                "UPDATE phone_login_attempts SET status = 'approved', reviewed_at = ? WHERE phone = ? AND status = 'pending'",
                (utc_now(), phone),
            )
            token = create_session(conn, user["id"])
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user["id"]))
            refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()

    if blocked_attempt_id:
        record_event("blocked_phone_login", payload={"attempt_id": blocked_attempt_id, "phone_suffix": phone[-4:]})
        raise HTTPException(status_code=403, detail="该手机号尚未获得访问权限，登录申请已提交给管理员")

    record_event("wechat_phone_login", refreshed["id"], payload={"phone_suffix": phone[-4:]})
    return {"token": token, "user": public_user(refreshed, LOGIN_POLICY_EMPLOYEE_ONLY)}


@router.get("/auth/me")
async def read_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user": user}


@router.post("/user/preferences")
async def update_preferences(body: PreferencesRequest, user: Dict[str, Any] = Depends(get_current_user)):
    with db_connection() as conn:
        conn.execute("UPDATE users SET language = ? WHERE id = ?", (body.language, user["id"]))
        refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    record_event("update_preferences", user["id"], payload={"language": body.language})
    return {"user": public_user(refreshed)}


@router.get("/privacy")
async def privacy_notice():
    return {
        "permissions": [
            {"key": "camera", "purpose": "Take a photo for pattern recognition."},
            {"key": "album", "purpose": "Select a saved photo for pattern recognition."},
            {"key": "storage", "purpose": "Save exported favorite PDF files for preview or sharing."},
        ],
        "data": [
            "Recognition images may be saved for internal test review and algorithm improvement.",
            "Search, browse, favorite, feedback, and lead forms are recorded for service optimization.",
        ],
    }


@router.get("/patterns")
async def search_patterns(
    query: str = "",
    category: str = "",
    limit: int = 10,
    search_mode: str = "auto",
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    resolved_mode = resolve_pattern_search_mode(query, search_mode)
    category_filter = normalize_category_filter(category)
    results = find_patterns(query=query, category=category_filter, limit=limit, search_mode=resolved_mode)
    if user:
        favorited = favorite_ids_for_user(user["id"])
        for item in results:
            item["favorited"] = item["pattern_id"] in favorited
    if user:
        add_history(user["id"], "search", query=query, payload={"category": category_filter, "search_mode": resolved_mode, "count": len(results)})
    record_event("search", user["id"] if user else None, payload={"query": query, "category": category_filter, "search_mode": resolved_mode, "count": len(results)})
    return {"items": results, "count": len(results), "search_mode": resolved_mode}


@router.get("/patterns/{pattern_id}")
async def read_pattern(pattern_id: str, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    catalog = get_pattern_catalog()
    item = catalog.get(pattern_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pattern not found")
    public = public_pattern(item)
    if user:
        add_history(user["id"], "view", pattern_id=pattern_id)
        public["favorited"] = pattern_id in favorite_ids_for_user(user["id"])
    record_event("view_pattern", user["id"] if user else None, pattern_id=pattern_id)
    return {"item": public}


@router.get("/patterns/{pattern_id}/image")
async def read_pattern_image(pattern_id: str):
    item = get_pattern_catalog().get(pattern_id)
    if not item or not item.get("_image_path"):
        raise HTTPException(status_code=404, detail="Image not found")
    return oss_or_local_file_response(item.get("_oss_image_key"), item["_image_path"])


@router.get("/patterns/{pattern_id}/thumbnail")
async def read_pattern_thumbnail(pattern_id: str):
    item = get_pattern_catalog().get(pattern_id)
    if not item or not item.get("_image_path"):
        raise HTTPException(status_code=404, detail="Image not found")
    thumb_path = ensure_pattern_thumbnail(pattern_id, item)
    return oss_or_local_file_response(item.get("_oss_thumbnail_key"), str(thumb_path), media_type="image/jpeg")


@router.post("/favorites")
async def add_favorite(body: FavoriteRequest, user: Dict[str, Any] = Depends(get_current_user)):
    if body.pattern_id not in get_pattern_catalog():
        raise HTTPException(status_code=404, detail="Pattern not found")
    with db_connection() as conn:
        insert_sql = (
            "INSERT IGNORE INTO favorites(user_id, pattern_id, created_at) VALUES (?, ?, ?)"
            if platform_db_is_mysql()
            else "INSERT OR IGNORE INTO favorites(user_id, pattern_id, created_at) VALUES (?, ?, ?)"
        )
        conn.execute(
            insert_sql,
            (user["id"], body.pattern_id, utc_now()),
        )
    add_history(user["id"], "favorite", pattern_id=body.pattern_id)
    record_event("favorite", user["id"], pattern_id=body.pattern_id)
    return {"ok": True}


@router.delete("/favorites/{pattern_id}")
async def remove_favorite(pattern_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    with db_connection() as conn:
        conn.execute("DELETE FROM favorites WHERE user_id = ? AND pattern_id = ?", (user["id"], pattern_id))
    record_event("unfavorite", user["id"], pattern_id=pattern_id)
    return {"ok": True}


@router.get("/favorites")
async def list_favorites(user: Dict[str, Any] = Depends(get_current_user)):
    catalog = get_pattern_catalog()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT pattern_id, created_at FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
    items = []
    for row in rows:
        item = catalog.get(row["pattern_id"])
        if item:
            public = public_pattern(item)
            public["favorited_at"] = row["created_at"]
            items.append(public)
    return {"items": items, "count": len(items)}


def load_font(size: int) -> Any:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for font_path in candidates:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_favorites_pdf(user: Dict[str, Any], items: List[Dict[str, Any]]) -> bytes:
    width, height = 1240, 1754
    margin = 80
    row_height = 230
    pages: List[Image.Image] = []
    title_font = load_font(42)
    heading_font = load_font(26)
    body_font = load_font(22)
    small_font = load_font(18)

    def new_page(page_index: int):
        page = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(page)
        draw.text((margin, 52), "Xiaote Favorite Patterns", fill="#111827", font=title_font)
        draw.text((margin, 112), f"User: {user['username']}    Exported: {utc_now()}", fill="#475569", font=small_font)
        draw.line((margin, 155, width - margin, 155), fill="#d1d5db", width=2)
        draw.text((margin, height - 70), f"Page {page_index}", fill="#6b7280", font=small_font)
        return page, draw, 190

    page, draw, y = new_page(1)
    page_index = 1
    if not items:
        draw.text((margin, y), "No favorite patterns yet.", fill="#374151", font=body_font)
    for item in items:
        if y + row_height > height - 110:
            pages.append(page)
            page_index += 1
            page, draw, y = new_page(page_index)

        draw.rounded_rectangle((margin, y, width - margin, y + row_height - 25), radius=16, outline="#d1d5db", width=2)
        image_path = item.get("_image_path")
        if image_path and Path(image_path).exists():
            try:
                thumb = Image.open(image_path).convert("RGB")
                thumb.thumbnail((260, 170))
                draw.rectangle((margin + 24, y + 24, margin + 284, y + 194), fill="#f3f4f6")
                page.paste(thumb, (margin + 24, y + 24))
            except Exception:
                draw.rectangle((margin + 24, y + 24, margin + 284, y + 194), fill="#f3f4f6")
        else:
            draw.rectangle((margin + 24, y + 24, margin + 284, y + 194), fill="#f3f4f6")

        x = margin + 320
        draw.text((x, y + 26), item.get("pattern_id", ""), fill="#111827", font=heading_font)
        draw.text((x, y + 70), f"Name: {item.get('name') or '-'}", fill="#334155", font=body_font)
        draw.text((x, y + 106), f"Texture: {item.get('texture_name') or '-'}", fill="#334155", font=body_font)
        draw.text((x, y + 142), f"Usage: {item.get('usage_name') or '-'}", fill="#334155", font=body_font)
        draw.text(
            (x, y + 178),
            f"Sales: {SALES_CONTACT['name']} / {SALES_CONTACT['phone']} / {SALES_CONTACT['wechat']}",
            fill="#0f766e",
            font=small_font,
        )
        y += row_height

    pages.append(page)
    output = io.BytesIO()
    pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    return output.getvalue()


def generate_pattern_pdf(user: Dict[str, Any], item: Dict[str, Any]) -> bytes:
    width, height = 1240, 1754
    margin = 82
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    title_font = load_font(56)
    heading_font = load_font(34)
    body_font = load_font(28)
    small_font = load_font(22)

    draw.text((margin, 62), "schattdecor Vision", fill="#111827", font=title_font)
    draw.text((margin, 140), f"Pattern PDF    Exported: {utc_now()}", fill="#64748b", font=small_font)
    draw.line((margin, 190, width - margin, 190), fill="#d1d5db", width=2)

    image_box = (margin, 250, width - margin, 1110)
    draw.rounded_rectangle(image_box, radius=24, outline="#d1d5db", width=2)
    image_path = item.get("_image_path")
    if image_path and Path(image_path).exists():
        try:
            source = Image.open(image_path).convert("RGB")
            source.thumbnail((image_box[2] - image_box[0] - 8, image_box[3] - image_box[1] - 8))
            x = image_box[0] + (image_box[2] - image_box[0] - source.width) // 2
            y = image_box[1] + (image_box[3] - image_box[1] - source.height) // 2
            page.paste(source, (x, y))
        except Exception:
            draw.rectangle((image_box[0] + 4, image_box[1] + 4, image_box[2] - 4, image_box[3] - 4), fill="#f1f5f9")
    else:
        draw.rectangle((image_box[0] + 4, image_box[1] + 4, image_box[2] - 4, image_box[3] - 4), fill="#f1f5f9")

    y = 1180
    draw.text((margin, y), item.get("name") or item.get("decor_name") or item.get("pattern_id", ""), fill="#111827", font=heading_font)
    y += 58
    draw.text((margin, y), f"Code: {item.get('pattern_id', '-')}", fill="#334155", font=body_font)
    y += 46
    draw.text((margin, y), f"Texture: {item.get('texture_name') or '-'}", fill="#334155", font=body_font)
    y += 46
    draw.text((margin, y), f"Usage: {item.get('usage_name') or '-'}", fill="#334155", font=body_font)
    y += 46
    draw.text((margin, y), f"Wood type: {item.get('wood_art_name') or '-'}", fill="#334155", font=body_font)
    y += 72
    draw.text((margin, y), f"User: {user['username']}", fill="#64748b", font=small_font)
    draw.text(
        (margin, height - 92),
        f"Sales: {SALES_CONTACT['name']} / {SALES_CONTACT['phone']} / {SALES_CONTACT['wechat']}",
        fill="#0f766e",
        font=small_font,
    )

    output = io.BytesIO()
    page.save(output, format="PDF", resolution=150.0)
    return output.getvalue()


@router.get("/patterns/{pattern_id}/export.pdf")
async def export_pattern_pdf(pattern_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    item = get_pattern_catalog().get(pattern_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pattern not found")
    pdf_bytes = generate_pattern_pdf(user, item)
    record_event("export_pattern_pdf", user["id"], pattern_id=pattern_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pattern_id}.pdf"'},
    )


@router.get("/favorites/export.pdf")
async def export_favorites_pdf(user: Dict[str, Any] = Depends(get_current_user)):
    catalog = get_pattern_catalog()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT pattern_id, created_at FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
    items = []
    for row in rows:
        item = catalog.get(row["pattern_id"])
        if item:
            merged = dict(item)
            merged["favorited_at"] = row["created_at"]
            items.append(merged)
    pdf_bytes = generate_favorites_pdf(user, items)
    record_event("export_favorites_pdf", user["id"], payload={"count": len(items)})
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="xiaote-favorites.pdf"'},
    )


@router.post("/feedback")
async def create_feedback(body: FeedbackRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    ensure_platform()
    image_path = save_base64_image(body.image_base64)
    feedback_id = uuid.uuid4().hex
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO feedback(id, user_id, recognition_id, pattern_id, verdict, correct_pattern_id, note, image_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                user["id"] if user else None,
                body.recognition_id,
                body.pattern_id,
                body.verdict,
                body.correct_pattern_id,
                body.note,
                image_path,
                utc_now(),
            ),
        )
    record_event(
        "feedback",
        user["id"] if user else None,
        body.pattern_id,
        {"verdict": body.verdict, "correct_pattern_id": body.correct_pattern_id, "recognition_id": body.recognition_id},
    )
    return {"ok": True, "feedback_id": feedback_id}


@router.post("/events")
async def create_event(body: EventRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    event_id = record_event(body.event_type, user["id"] if user else None, body.pattern_id, body.payload)
    if user and body.event_type in set(BROWSE_HISTORY_ACTIONS) | {"jump_sample"}:
        add_history(user["id"], body.event_type, pattern_id=body.pattern_id, payload=body.payload)
    return {"ok": True, "event_id": event_id}


@router.get("/history")
async def list_history(user: Dict[str, Any] = Depends(get_current_user), limit: int = 50):
    catalog = get_pattern_catalog()
    with db_connection() as conn:
        placeholders = ",".join("?" for _ in BROWSE_HISTORY_ACTIONS)
        rows = conn.execute(
            f"""
            SELECT * FROM history
            WHERE user_id = ? AND pattern_id IS NOT NULL AND action IN ({placeholders})
            ORDER BY created_at DESC LIMIT ?
            """,
            (user["id"], *BROWSE_HISTORY_ACTIONS, max(1, min(limit, 200))),
        ).fetchall()
        favorite_rows = conn.execute(
            "SELECT pattern_id FROM favorites WHERE user_id = ?",
            (user["id"],),
        ).fetchall()

    favorited = {row["pattern_id"] for row in favorite_rows}
    seen = set()
    items = []
    for row in rows:
        pattern_id = row["pattern_id"]
        if not pattern_id or pattern_id in seen:
            continue
        item = catalog.get(pattern_id)
        if not item:
            continue
        public = public_pattern(item)
        public["history_id"] = row["id"]
        public["viewed_at"] = row["created_at"]
        public["created_at"] = row["created_at"]
        public["favorited"] = pattern_id in favorited
        items.append(public)
        seen.add(pattern_id)
    return {"items": items, "count": len(items)}


@router.post("/leads/contact")
async def create_lead(body: LeadRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    lead_id = uuid.uuid4().hex
    answers = body.model_dump()
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO leads(id, user_id, answers_json, contact_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (lead_id, user["id"] if user else None, json_dumps(answers), json_dumps(SALES_CONTACT), utc_now()),
        )
    record_event("lead_contact", user["id"] if user else None, payload=answers)
    return {"lead_id": lead_id, "contact": SALES_CONTACT}


@router.post("/service/leads")
async def create_service_lead(body: ServiceLeadRequest, user: Dict[str, Any] = Depends(get_current_user)):
    lead_id = uuid.uuid4().hex
    contact = body.contact or SALES_CONTACT
    messages = body.messages[:100]
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO service_leads(
                id, user_id, phone, profession_id, profession_label, region_id, region_label,
                contact_json, messages_json, language, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                user["id"],
                user.get("phone"),
                body.profession_id,
                body.profession_label,
                body.region_id,
                body.region_label,
                json_dumps(contact),
                json_dumps(messages),
                body.language,
                body.source or "service_chat",
                utc_now(),
            ),
        )
    record_event(
        "service_lead",
        user["id"],
        payload={
            "lead_id": lead_id,
            "profession_id": body.profession_id,
            "profession_label": body.profession_label,
            "region_id": body.region_id,
            "region_label": body.region_label,
            "source": body.source,
        },
    )
    return {"ok": True, "lead_id": lead_id, "contact": contact}


@router.post("/orders/samples")
async def create_sample_order(
    body: SampleOrderRequest,
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
):
    if body.pattern_id not in get_pattern_catalog():
        raise HTTPException(status_code=404, detail="Pattern not found")
    order_id = uuid.uuid4().hex
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO sample_orders(id, user_id, pattern_id, quantity, note, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, user["id"], body.pattern_id, body.quantity, body.note, "created", utc_now()),
        )
    add_history(user["id"], "sample_order", pattern_id=body.pattern_id, payload={"quantity": body.quantity})
    record_event("sample_order", user["id"], body.pattern_id, {"quantity": body.quantity})
    return {"ok": True, "order_id": order_id}


@router.get("/admin/summary")
async def admin_summary(user: Dict[str, Any] = Depends(require_roles({"sales", "admin"}))):
    with db_connection() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        events = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        feedback = conn.execute("SELECT COUNT(*) AS c FROM feedback").fetchone()["c"]
        unmatched = conn.execute("SELECT COUNT(*) AS c FROM unmatched_records").fetchone()["c"]
        service_leads = conn.execute("SELECT COUNT(*) AS c FROM service_leads").fetchone()["c"]
        training = conn.execute("SELECT COUNT(*) AS c FROM training_data").fetchone()["c"]
        sample_orders = conn.execute("SELECT COUNT(*) AS c FROM sample_orders").fetchone()["c"]
        managed_users = conn.execute("SELECT COUNT(*) AS c FROM managed_users WHERE enabled = 1").fetchone()["c"]
        pending_phone_logins = conn.execute("SELECT COUNT(*) AS c FROM phone_login_attempts WHERE status = 'pending'").fetchone()["c"]
        login_policy = get_login_policy(conn)
    return {
        "users": users,
        "events": events,
        "feedback": feedback,
        "unmatched": unmatched,
        "service_leads": service_leads,
        "training_data": training,
        "sample_orders": sample_orders,
        "managed_users": managed_users,
        "pending_phone_logins": pending_phone_logins,
        "patterns": len(get_pattern_catalog()),
        "current_user": user,
        "login_policy": login_policy,
    }


@router.get("/admin/patterns")
async def admin_patterns(
    query: str = "",
    category: str = "",
    family: str = "",
    offset: int = 0,
    limit: int = 60,
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
):
    category_filter = normalize_category_filter(category)
    q = (query or "").strip().lower()
    family_filter = (family or "").strip().lower()
    catalog = [
        item
        for item in get_pattern_catalog().values()
        if pattern_matches_category(item, category_filter)
    ]
    if family_filter:
        catalog = [
            item
            for item in catalog
            if (pattern_family_id(item.get("pattern_id", "")) or item.get("pattern_id", "")).lower() == family_filter
        ]

    grouped_view = not q and not family_filter
    if grouped_view:
        family_counts: Dict[str, int] = {}
        for item in catalog:
            family_id = pattern_family_id(item.get("pattern_id", "")) or item.get("pattern_id", "")
            family_counts[family_id] = family_counts.get(family_id, 0) + 1

        covers: Dict[str, Dict[str, Any]] = {}
        for item in sorted(catalog, key=lambda value: value["pattern_id"]):
            family_id = pattern_family_id(item.get("pattern_id", "")) or item.get("pattern_id", "")
            if family_id in covers:
                continue
            cover = dict(public_pattern(item))
            cover["family_id"] = family_id
            cover["family_count"] = family_counts.get(family_id, 1)
            cover["is_family_cover"] = True
            covers[family_id] = cover
        visible_items = list(covers.values())
    elif q:
        scored = [(keyword_score(item, q), item) for item in catalog]
        matched = [item for score, item in scored if score > 0]
        matched.sort(key=lambda item: (-keyword_score(item, q), item["pattern_id"]))
        visible_items = [public_pattern(item) for item in matched]
    else:
        catalog.sort(key=lambda item: item["pattern_id"])
        visible_items = [public_pattern(item) for item in catalog]

    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 120))
    page_items = visible_items[safe_offset : safe_offset + safe_limit]
    return {
        "items": page_items,
        "count": len(page_items),
        "total": len(visible_items),
        "offset": safe_offset,
        "limit": safe_limit,
        "view_mode": "families" if grouped_view else "patterns",
        "family": family_filter,
    }


@router.get("/admin/login-policy")
async def admin_get_login_policy(user: Dict[str, Any] = Depends(require_roles({"admin"}))):
    with db_connection() as conn:
        policy = get_login_policy(conn)
    return {"policy": policy}


@router.post("/admin/login-policy")
async def admin_set_login_policy(
    body: LoginPolicyRequest,
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
):
    with db_connection() as conn:
        policy = set_login_policy(conn, body.policy, user["id"])
    record_event("admin_login_policy_update", user["id"], payload={"policy": policy})
    return {"policy": policy}


@router.get("/admin/managed-users")
async def admin_managed_users(
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
    limit: int = 500,
):
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT managed_users.*, users.username AS backend_username, users.status AS backend_status
            FROM managed_users
            LEFT JOIN users ON users.id = managed_users.user_id
            ORDER BY managed_users.enabled DESC, managed_users.updated_at DESC LIMIT ?
            """,
            (max(1, min(limit, 1000)),),
        ).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


@router.post("/admin/managed-users")
async def admin_upsert_managed_user(
    body: ManagedUserRequest,
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
):
    phone = normalize_phone(body.phone)
    if body.role == "admin":
        username = phone
        password = body.admin_password or ""
        with db_connection() as conn:
            existing = conn.execute("SELECT * FROM managed_users WHERE phone = ?", (phone,)).fetchone()
            linked_user = None
            if existing and existing["user_id"]:
                linked_user = conn.execute("SELECT * FROM users WHERE id = ?", (existing["user_id"],)).fetchone()
            elif existing:
                linked_user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        if not linked_user and not password:
            raise HTTPException(status_code=400, detail="Backend admin password is required")

    with db_connection() as conn:
        row = upsert_managed_user_record(conn, phone, body.display_name, body.role, body.enabled, body.note)
        backend_user = None
        if body.role == "admin" and body.enabled:
            if body.admin_password:
                backend_user = upsert_backend_account(conn, phone, username, body.admin_password, "admin")
            else:
                linked_user = conn.execute("SELECT * FROM users WHERE id = ? OR phone = ?", (row["user_id"], phone)).fetchone()
                if linked_user:
                    conn.execute(
                        "UPDATE users SET username = ?, phone = ?, role = 'admin', status = 'active' WHERE id = ?",
                        (username, phone, linked_user["id"]),
                    )
                    conn.execute("UPDATE managed_users SET user_id = ? WHERE id = ?", (linked_user["id"], row["id"]))
                    backend_user = conn.execute("SELECT * FROM users WHERE id = ?", (linked_user["id"],)).fetchone()
                else:
                    raise HTTPException(status_code=400, detail="Backend admin password is required")
        if body.enabled:
            conn.execute(
                "UPDATE phone_login_attempts SET status = 'approved', reviewed_by = ?, reviewed_at = ? WHERE phone = ? AND status = 'pending'",
                (user["id"], utc_now(), phone),
            )
        refreshed = conn.execute(
            """
            SELECT managed_users.*, users.username AS backend_username, users.status AS backend_status
            FROM managed_users
            LEFT JOIN users ON users.id = managed_users.user_id
            WHERE managed_users.phone = ?
            """,
            (phone,),
        ).fetchone()
    record_event(
        "admin_managed_user_upsert",
        user["id"],
        payload={"phone_suffix": phone[-4:], "role": body.role, "enabled": body.enabled, "backend_account": bool(backend_user)},
    )
    return {"item": dict(refreshed)}


@router.delete("/admin/managed-users/{phone}")
async def admin_disable_managed_user(
    phone: str,
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
):
    normalized = normalize_phone(phone)
    with db_connection() as conn:
        existing = conn.execute("SELECT * FROM managed_users WHERE phone = ?", (normalized,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Managed user not found")
        row = upsert_managed_user_record(
            conn,
            normalized,
            existing["display_name"],
            existing["role"],
            False,
            existing["note"],
        )
    record_event("admin_managed_user_disable", user["id"], payload={"phone_suffix": normalized[-4:]})
    return {"item": dict(row)}


@router.delete("/admin/managed-users/{phone}/permanent")
async def admin_delete_managed_user(
    phone: str,
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
):
    normalized = normalize_phone(phone)
    with db_connection() as conn:
        existing = conn.execute("SELECT * FROM managed_users WHERE phone = ?", (normalized,)).fetchone()
        linked_user = None
        if existing and existing["user_id"]:
            linked_user = conn.execute("SELECT * FROM users WHERE id = ?", (existing["user_id"],)).fetchone()
        if not linked_user:
            linked_user = conn.execute("SELECT * FROM users WHERE phone = ?", (normalized,)).fetchone()
        if not existing and not linked_user:
            raise HTTPException(status_code=404, detail="Managed user not found")
        if linked_user and linked_user["id"] == user["id"]:
            raise HTTPException(status_code=400, detail="Cannot delete the current admin account")
        if linked_user and linked_user["role"] == "admin":
            active_admin_count = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND status = 'active'"
            ).fetchone()["c"]
            if active_admin_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot delete the last active admin account")

        target_user_id = linked_user["id"] if linked_user else None
        if target_user_id:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (target_user_id,))
            conn.execute("DELETE FROM favorites WHERE user_id = ?", (target_user_id,))
            conn.execute("DELETE FROM history WHERE user_id = ?", (target_user_id,))
            conn.execute("DELETE FROM sample_orders WHERE user_id = ?", (target_user_id,))
            conn.execute("UPDATE events SET user_id = NULL WHERE user_id = ?", (target_user_id,))
            conn.execute("UPDATE feedback SET user_id = NULL WHERE user_id = ?", (target_user_id,))
            conn.execute("UPDATE unmatched_records SET user_id = NULL WHERE user_id = ?", (target_user_id,))
            conn.execute("UPDATE leads SET user_id = NULL WHERE user_id = ?", (target_user_id,))
            conn.execute("UPDATE service_leads SET user_id = NULL WHERE user_id = ?", (target_user_id,))
            conn.execute("UPDATE training_data SET user_id = NULL WHERE user_id = ?", (target_user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
        conn.execute("DELETE FROM managed_users WHERE phone = ?", (normalized,))
        conn.execute("DELETE FROM phone_login_attempts WHERE phone = ?", (normalized,))
    record_event("admin_managed_user_delete", user["id"], payload={"phone_suffix": normalized[-4:]})
    return {"ok": True, "phone": normalized}


@router.get("/admin/phone-login-attempts")
async def admin_phone_login_attempts(
    status: str = "pending",
    limit: int = 500,
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
):
    status_filter = status if status in {"pending", "approved", "rejected", "all"} else "pending"
    with db_connection() as conn:
        if status_filter == "all":
            rows = conn.execute(
                "SELECT * FROM phone_login_attempts ORDER BY last_attempt_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM phone_login_attempts WHERE status = ? ORDER BY last_attempt_at DESC LIMIT ?",
                (status_filter, max(1, min(limit, 1000))),
            ).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


@router.post("/admin/phone-login-attempts/{attempt_id}/approve")
async def admin_approve_phone_attempt(
    attempt_id: str,
    body: PhoneAttemptDecisionRequest,
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
):
    with db_connection() as conn:
        attempt = conn.execute("SELECT * FROM phone_login_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if not attempt:
            raise HTTPException(status_code=404, detail="Phone login attempt not found")
        display_name = (body.display_name or f"员工{attempt['phone'][-4:]}").strip()
        managed = upsert_managed_user_record(conn, attempt["phone"], display_name, body.role, True, body.note)
        conn.execute(
            "UPDATE phone_login_attempts SET status = 'approved', reviewed_by = ?, reviewed_at = ?, note = ? WHERE id = ?",
            (user["id"], utc_now(), body.note, attempt_id),
        )
    record_event("admin_phone_attempt_approve", user["id"], payload={"attempt_id": attempt_id, "phone_suffix": attempt["phone"][-4:]})
    return {"item": dict(managed)}


@router.post("/admin/phone-login-attempts/{attempt_id}/reject")
async def admin_reject_phone_attempt(
    attempt_id: str,
    body: PhoneAttemptDecisionRequest,
    user: Dict[str, Any] = Depends(require_roles({"admin"})),
):
    with db_connection() as conn:
        attempt = conn.execute("SELECT * FROM phone_login_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if not attempt:
            raise HTTPException(status_code=404, detail="Phone login attempt not found")
        conn.execute(
            "UPDATE phone_login_attempts SET status = 'rejected', reviewed_by = ?, reviewed_at = ?, note = ? WHERE id = ?",
            (user["id"], utc_now(), body.note, attempt_id),
        )
    record_event("admin_phone_attempt_reject", user["id"], payload={"attempt_id": attempt_id, "phone_suffix": attempt["phone"][-4:]})
    return {"ok": True}


@router.get("/admin/events")
async def admin_events(
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
    limit: int = 100,
):
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {"items": [row_payload(row) for row in rows], "count": len(rows)}


@router.get("/admin/feedback")
async def admin_feedback(
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
    limit: int = 100,
):
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


@router.get("/admin/unmatched")
async def admin_unmatched(
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
    limit: int = 100,
):
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM unmatched_records ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {"items": [row_payload(row) for row in rows], "count": len(rows)}


@router.get("/admin/service-leads")
async def admin_service_leads(
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
    limit: int = 100,
):
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT service_leads.*, users.username AS username, users.role AS user_role
            FROM service_leads
            LEFT JOIN users ON users.id = service_leads.user_id
            ORDER BY service_leads.created_at DESC LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {"items": [row_payload(row) for row in rows], "count": len(rows)}


@router.get("/admin/training-data")
async def list_training_data(
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
    limit: int = 100,
):
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM training_data ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


@router.get("/admin/image-preview")
async def admin_image_preview(
    path: str,
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
):
    ensure_platform()
    candidate = Path(path).expanduser().resolve()
    allowed_roots = tuple(root.resolve() for root in (UPLOAD_DIR, FEEDBACK_DIR, TRAINING_DIR))
    if not candidate.is_file() or not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(str(candidate))


@router.get("/admin/sample-orders")
async def list_sample_orders(
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
    limit: int = 100,
):
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sample_orders ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


@router.post("/admin/training-data")
async def upload_training_data(
    pattern_id: str = Form(""),
    category: str = Form(""),
    note: str = Form(""),
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(require_roles({"sales", "admin"})),
):
    file_bytes = await file.read()
    image_path = save_training_image(file_bytes, file.filename)
    item_id = uuid.uuid4().hex
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO training_data(id, user_id, pattern_id, category, image_path, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (item_id, user["id"], pattern_id or None, category or None, image_path, note or None, utc_now()),
        )
    record_event("training_upload", user["id"], pattern_id or None, {"category": category, "note": note})
    return {"ok": True, "id": item_id, "image_path": image_path}


@router.get("/admin/ui", response_class=HTMLResponse)
async def admin_ui():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Xiaote Admin</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; color: #111827; background: #f8fafc; }
    main { max-width: 1040px; margin: 0 auto; }
    input, button { font: inherit; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 6px; }
    button { background: #0f766e; color: white; border: 0; cursor: pointer; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 20px 0; }
    .card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
    pre { white-space: pre-wrap; background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 8px; overflow: auto; }
  </style>
</head>
<body>
  <main>
    <h1>Xiaote Admin</h1>
    <p>Paste a sales/admin bearer token to inspect behavior data, feedback, unmatched records, and training uploads.</p>
    <input id="token" placeholder="Bearer token" style="width: min(720px, 100%);" />
    <button onclick="loadAll()">Load</button>
    <section id="summary" class="grid"></section>
    <h2>Latest Data</h2>
    <pre id="output">No data loaded.</pre>
  </main>
  <script>
    async function api(path) {
      const token = document.getElementById('token').value.trim();
      const res = await fetch(path, { headers: { Authorization: 'Bearer ' + token } });
      if (!res.ok) throw new Error(path + ' ' + res.status + ': ' + await res.text());
      return res.json();
    }
    async function loadAll() {
      try {
        const [summary, events, feedback, unmatched, training, sampleOrders] = await Promise.all([
          api('/api/admin/summary'),
          api('/api/admin/events?limit=20'),
          api('/api/admin/feedback?limit=20'),
          api('/api/admin/unmatched?limit=20'),
          api('/api/admin/training-data?limit=20'),
          api('/api/admin/sample-orders?limit=20')
        ]);
        document.getElementById('summary').innerHTML = Object.entries(summary)
          .filter(([_, value]) => typeof value !== 'object')
          .map(([key, value]) => `<div class="card"><strong>${key}</strong><br>${value}</div>`)
          .join('');
        document.getElementById('output').textContent = JSON.stringify({ events, feedback, unmatched, training, sampleOrders }, null, 2);
      } catch (error) {
        document.getElementById('output').textContent = error.message;
      }
    }
  </script>
</body>
</html>
"""
