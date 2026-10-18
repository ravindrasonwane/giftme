"""
=========================================================
GiftFlix - Netflix Gift Generator Backend
Version: 1.0
Author: ChatGPT

Run:

pip install fastapi uvicorn python-multipart pillow


file:///D:/BIZZ/Giftflix/PYTHON%20Code/creator.html

uvicorn main:app --reload
=========================================================
"""

import os
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import List
import secrets
import html
import hashlib
import hmac
import base64
import time

import resend
from fastapi import FastAPI
from fastapi import UploadFile
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Request, Body, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse
from PIL import Image
from pathlib import Path
from fastapi.responses import JSONResponse

# =====================================================
# CONFIGURATION
# =====================================================

BASE_DIR = Path(__file__).parent

# =====================================================
# APP / EMAIL CONFIGURATION
# =====================================================

GIFT_BASE_URL = os.getenv(
    "GIFT_BASE_URL",
    "https://giftpixel.in"
)

EMAIL_FROM = "GiftPixel <hello@giftpixel.in>"

# Resend API key is stored locally in:
# config/api_key.txt
API_KEY_FILE = (
    BASE_DIR /
    "config" /
    "api_key.txt"
)


def load_api_key():

    if not API_KEY_FILE.exists():

        raise RuntimeError(
            "API key file not found: "
            f"{API_KEY_FILE}"
        )

    api_key = API_KEY_FILE.read_text(
        encoding="utf-8"
    ).strip()

    if not api_key:

        raise RuntimeError(
            "API key file is empty: "
            f"{API_KEY_FILE}"
        )

    return api_key


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
if not RESEND_API_KEY and API_KEY_FILE.exists():
    try:
        RESEND_API_KEY = load_api_key()
    except RuntimeError:
        RESEND_API_KEY = ""
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


UPLOAD_DIR = BASE_DIR / "uploads"
IMAGE_DIR = UPLOAD_DIR / "images"
VIDEO_DIR = UPLOAD_DIR / "videos"
MUSIC_DIR = UPLOAD_DIR / "music"

DATABASE = BASE_DIR / "database.json"

# A persistent signing secret for short-lived gift-access cookies. Keep this file private.
SESSION_SECRET_FILE = BASE_DIR / ".gift_session_secret"
if not SESSION_SECRET_FILE.exists():
    SESSION_SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
try:
    SESSION_SECRET = SESSION_SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
except OSError as exc:
    raise RuntimeError("Could not read .gift_session_secret") from exc
if len(SESSION_SECRET) < 32:
    raise RuntimeError(".gift_session_secret must contain a strong random secret")
SESSION_COOKIE = "giftpixel_access"
SESSION_TTL_SECONDS = 12 * 60 * 60

# Text file that stores every created GiftFlix response as JSON Lines.
DATA_DIR = BASE_DIR / "data"
RESPONSE_FILE = DATA_DIR / "response.txt"

MAX_IMAGES = 20
MAX_VIDEOS = 10

ALLOWED_IMAGES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
}

ALLOWED_VIDEOS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv"
}

ALLOWED_AUDIO = {
    ".mp3",
    ".wav"
}


# =====================================================
# CREATE FOLDERS
# =====================================================

IMAGE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

if not DATABASE.exists():

    with open(DATABASE, "w") as f:

        json.dump([], f)

# =====================================================
# APP
# =====================================================

app = FastAPI(
    title="GiftFlix API",
    version="1.0"
)
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # Development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Uploads are deliberately NOT mounted as a public static directory.
# Gift media is served through /gift-media/{slug}/{filename}, which checks access.


# =====================================================
# HELPERS
# =====================================================

def load_database():

    with open(DATABASE, "r") as f:

        return json.load(f)


def save_database(data):

    with open(DATABASE, "w") as f:

        json.dump(data, f, indent=4)


def save_response(gift):
    """Append one created gift as a JSON object to data/response.txt."""

    with open(
        RESPONSE_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            json.dumps(
                gift,
                ensure_ascii=False
            ) + "\n"
        )


def hash_gift_password(password: str) -> str:
    """Return a salted PBKDF2 hash; never store the raw password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return "pbkdf2_sha256$310000$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_gift_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, rounds_text, salt_text, digest_text = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds_text))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def make_session_token(slug: str) -> str:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{slug}:{expires}".encode("utf-8")
    signature = hmac.new(SESSION_SECRET, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def session_allows(slug: str, token: str | None) -> bool:
    if not token or "." not in token:
        return False
    try:
        payload_part, signature_part = token.split(".", 1)
        payload = base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
        signature = base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
        expected = hmac.new(SESSION_SECRET, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        token_slug, expires_text = payload.decode("utf-8").rsplit(":", 1)
        return token_slug == slug and int(expires_text) > int(time.time())
    except (ValueError, UnicodeDecodeError):
        return False


def find_gift(slug: str):
    for item in load_database():
        if item.get("slug") == slug:
            return item
    return None


def gift_requires_password(gift: dict) -> bool:
    return bool(gift.get("password_hash"))


def gift_access_allowed(gift: dict, request: Request) -> bool:
    if not gift_requires_password(gift):
        return True
    return session_allows(gift.get("slug", ""), request.cookies.get(SESSION_COOKIE))


def public_gift_payload(gift: dict) -> dict:
    """Remove password hash and rewrite media URLs to guarded endpoints."""
    safe = {k: v for k, v in gift.items() if k != "password_hash"}
    slug = str(gift.get("slug", ""))
    for field in ("images", "gallery", "videos"):
        safe[field] = [media_path_for_gift(slug, item) for item in gift.get(field, [])]
    if gift.get("music"):
        safe["music"] = media_path_for_gift(slug, gift["music"])
    return safe


def media_path_for_gift(slug: str, stored_path: str) -> str:
    filename = Path(str(stored_path)).name
    return f"/gift-media/{slug}/{filename}"


def generate_slug():

    return uuid.uuid4().hex[:8]


def validate_image(filename):

    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_IMAGES:

        raise HTTPException(
            status_code=400,
            detail="Unsupported image type."
        )


def validate_video(filename):

    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_VIDEOS:

        raise HTTPException(
            status_code=400,
            detail="Unsupported video type."
        )


@app.get("/gift/phrases")
async def get_phrases():

    file_path = Path("data/phrases.txt")

    if not file_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "phrases.txt not found"
            }
        )

    content = file_path.read_text(
        encoding="utf-8"
    )

    result = {}

    occasion = None
    section = None

    for raw_line in content.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        # [birthday]
        if line.startswith("[") and line.endswith("]"):

            occasion = line[1:-1].strip()

            result[occasion] = {
                "title": [],
                "description": [],
                "love_letter": []
            }

            section = None

            continue

        # TITLE / DESCRIPTION / LOVE_LETTER
        if line in [
            "TITLE",
            "DESCRIPTION",
            "LOVE_LETTER"
        ]:

            section = line.lower()

            continue

        if occasion and section:

            result[occasion][section].append(line)

    return result

def validate_music(filename):

    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_AUDIO:

        raise HTTPException(
            status_code=400,
            detail="Unsupported music type."
        )


async def save_upload(file: UploadFile, folder: Path):

    filename = f"{uuid.uuid4().hex}{Path(file.filename).suffix}"

    path = folder / filename

    with open(path, "wb") as buffer:

        shutil.copyfileobj(file.file, buffer)

    return str(path.relative_to(BASE_DIR))


# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home():

    with open("templates/landingpage.html", "r", encoding="utf-8") as f:
        html = f.read()

    return HTMLResponse(html)

@app.get("/login", response_class=HTMLResponse)
async def login_page():

    with open("templates/login.html", "r", encoding="utf-8") as f:
        html = f.read()

    return HTMLResponse(html)


@app.get("/loveflix-create", response_class=HTMLResponse)
async def loveflixcreate():
    with open("templates/creator.html", "r", encoding="utf-8") as f:
        html = f.read()

    return HTMLResponse(html)



@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...)
):

    with open("users.txt", "r", encoding="utf-8") as f:

        users = f.readlines()

    for user in users:

        user = user.strip()

        if not user:
            continue

        name, saved_email, phone, saved_password = user.split(",")

        if email.strip().lower() == saved_email.strip().lower() and \
           password == saved_password.strip():

            return RedirectResponse(
                url="/dashboard",
                status_code=303
            )

    # Wrong email/password
    return RedirectResponse(
        url="/login?error=1",
        status_code=303
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():

    with open("templates/dashboard.html", "r", encoding="utf-8") as f:
        html = f.read()

    return HTMLResponse(html)


from fastapi import Query

@app.get("/creategift", response_class=HTMLResponse)
async def creategift(template: str = Query(None)):

    if template == "loveflix":

        with open("templates/creator.html", "r", encoding="utf-8") as f:
            html = f.read()

        return HTMLResponse(html)

    return HTMLResponse("Template not found", status_code=404)


# =====================================================
# EMAIL
# =====================================================

# =====================================================
# CREATE GIFT
# =====================================================

@app.post("/gift/create")
async def create_gift(
    

    title: str = Form(...),

    recipient_name: str = Form(...),

    recipient_email: str = Form(...),

    sender_name: str = Form(...),

    description: str = Form(...),

    occasion: str = Form("special_day"),

    love_letter: str = Form(""),

    diary: str = Form("[]"),

    gift_password: str = Form(""),

    images: List[UploadFile] = File(...),      # 4 profile images

    gallery: List[UploadFile] = File([]),      # Multiple gallery images

    videos: List[UploadFile] = File([]),       # Multiple videos

    music: UploadFile | None = File(None)

):
    

    if len(images) > MAX_IMAGES:

        raise HTTPException(
            400,
            "Maximum 20 images allowed."
        )

    if len(videos) > MAX_VIDEOS:

        raise HTTPException(
            400,
            "Maximum 10 videos allowed."
        )


    slug = generate_slug()



    image_urls = []

    video_urls = []

    gallery_urls = []

    music_url = None

    gift_password = gift_password.strip()
    if gift_password and len(gift_password) < 4:
        raise HTTPException(status_code=400, detail="Gift password must be at least 4 characters.")
    if len(gift_password) > 128:
        raise HTTPException(status_code=400, detail="Gift password must be 128 characters or fewer.")
    
    if gift_password:
        passhash_text = hash_gift_password(gift_password)

    # Save Images

    for image in images:

        validate_image(image.filename)

        url = await save_upload(image, IMAGE_DIR)

        image_urls.append(url)

    # =====================================================
    # SAVE GALLERY IMAGES
    # =====================================================

    for gallery_image in gallery:

        validate_image(gallery_image.filename)

        url = await save_upload(
            gallery_image,
            IMAGE_DIR
        )

        gallery_urls.append(url)

    # Save Videos

    for video in videos:

        validate_video(video.filename)

        url = await save_upload(video, VIDEO_DIR)

        video_urls.append(url)

    # Save Music

    if music:

        validate_music(music.filename)

        music_url = await save_upload(
            music,
            MUSIC_DIR
        )
    diary_entries = json.loads(diary)

    gift = {

        "id": str(uuid.uuid4()),

        "slug": slug,

        "title": title,

        "recipient": recipient_name,

        "recipient_email": recipient_email,

        "sender": sender_name,

        "occasion": occasion,

        "love_letter": love_letter,

        "description": description,

        "images": image_urls,

        "gallery": gallery_urls,

        "videos": video_urls,

        "music": music_url,

        "diary": diary_entries,

        "password_hash" : passhash_text,

        "created_at": datetime.now().isoformat()

    }



    database = load_database()

    database.append(gift)

    save_database(database)

    # Also append the complete gift ID + data to:
    # data/response.txt
    save_response({k: v for k, v in gift.items() if k != "password_hash"})

    gift_url = f"{GIFT_BASE_URL.rstrip('/')}/story/{slug}"

    email_status = "not_sent"
    email_id = None
    email_error = None

    print("\n" + "=" * 60)
    print("📧 EMAIL DELIVERY")
    print("=" * 60)
    print(f"From      : {EMAIL_FROM}")
    print(f"To        : {recipient_email}")
    print(f"Recipient : {recipient_name}")
    print(f"Occasion  : {occasion}")
    print(f"Gift URL  : {gift_url}")
    print("Status    : Sending...")

    try:

        email_result = await send_gift_email(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            sender_name=sender_name,
            gift_url=gift_url,
            occasion=occasion
        )

        email_status = "sent"

        if isinstance(email_result, dict):
            email_id = email_result.get("id")

        print("Status    : ✅ SENT")
        print(f"Email ID  : {email_id}")
        print("Provider  : Resend")
        print("=" * 60 + "\n")

    except Exception as e:

        email_status = "failed"
        email_error = str(e)

        print("Status    : ❌ FAILED")
        print(f"Error     : {email_error}")
        print("Provider  : Resend")
        print("=" * 60 + "\n")

    return {

        "success": True,

        "slug": slug,

        "gift_url": gift_url,

        "redirect_url": gift_url,

        "email_status": email_status,

        "email_id": email_id,

        "email_error": email_error

    }


# =====================================================
# GET GIFT
# =====================================================

@app.get("/gift/{slug}")
def get_gift(slug: str, request: Request):
    gift = find_gift(slug)
    if not gift:
        raise HTTPException(status_code=404, detail="Gift not found.")
    if not gift_access_allowed(gift, request):
        raise HTTPException(status_code=401, detail="This gift is password protected.")
    return public_gift_payload(gift)


@app.post("/gift/{slug}/unlock")
def unlock_gift(slug: str, request: Request, response: Response, payload: dict = Body(...)):
    gift = find_gift(slug)
    if not gift:
        raise HTTPException(status_code=404, detail="Gift not found.")
    if not gift_requires_password(gift):
        return {"success": True, "already_unlocked": True}
    password = payload.get("password", "")
    if not isinstance(password, str) or not verify_gift_password(password, gift["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=make_session_token(slug),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=GIFT_BASE_URL.lower().startswith("https://"),
        samesite="lax",
        path="/",
    )
    return {"success": True}


@app.get("/gift-media/{slug}/{filename}")
def gift_media(slug: str, filename: str, request: Request):
    gift = find_gift(slug)
    if not gift:
        raise HTTPException(status_code=404, detail="Gift not found.")
    if not gift_access_allowed(gift, request):
        raise HTTPException(status_code=401, detail="This gift is password protected.")
    allowed_paths = []
    for field in ("images", "gallery", "videos"):
        allowed_paths.extend(gift.get(field, []))
    if gift.get("music"):
        allowed_paths.append(gift["music"])
    matched = next((item for item in allowed_paths if Path(str(item)).name == filename), None)
    if not matched:
        raise HTTPException(status_code=404, detail="Media not found for this gift.")
    media_path = (BASE_DIR / matched).resolve()
    if not media_path.is_relative_to(BASE_DIR.resolve()) or not media_path.is_file():
        raise HTTPException(status_code=404, detail="Media not found.")
    return FileResponse(media_path)


from fastapi.responses import FileResponse

from fastapi.responses import HTMLResponse
from pathlib import Path

@app.get("/story/{slug}", response_class=HTMLResponse)
async def story(slug: str):

    html_path = Path("templates") / "loveflix.html"

    if not html_path.exists():
        raise HTTPException(status_code=404, detail="loveflix.html not found")

    html = html_path.read_text(encoding="utf-8")

    html = html.replace("__SLUG__", slug)

    return HTMLResponse(content=html)
