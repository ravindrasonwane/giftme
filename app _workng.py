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
from fastapi import FastAPI
from fastapi import UploadFile
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse
from PIL import Image
from pathlib import Path
from fastapi.responses import JSONResponse

# =====================================================
# CONFIGURATION
# =====================================================

BASE_DIR = Path(__file__).parent

UPLOAD_DIR = BASE_DIR / "uploads"
IMAGE_DIR = UPLOAD_DIR / "images"
VIDEO_DIR = UPLOAD_DIR / "videos"
MUSIC_DIR = UPLOAD_DIR / "music"

DATABASE = BASE_DIR / "database.json"

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
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


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
# CREATE GIFT
# =====================================================

@app.post("/gift/create")
async def create_gift(
    

    title: str = Form(...),

    recipient_name: str = Form(...),

    sender_name: str = Form(...),

    description: str = Form(...),

    diary: str = Form("[]"),


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

        "sender": sender_name,

        "description": description,

        "images": image_urls,

        "gallery": gallery_urls,

        "videos": video_urls,

        "music": music_url,

        "diary": diary_entries,

        "created_at": datetime.now().isoformat()

    }


    database = load_database()

    database.append(gift)

    save_database(database)

    # Also append the complete gift ID + data to:
    # data/response.txt
    save_response(gift)

    return {

        "success": True,

        "slug": slug,

        "redirect_url": f"http://127.0.0.1:8000/story/{slug}"

    }


# =====================================================
# GET GIFT
# =====================================================

@app.get("/gift/{slug}")
def get_gift(slug: str):

    database = load_database()

    for gift in database:

        if gift["slug"] == slug:

            return gift

    raise HTTPException(
        404,
        "Gift not found."
    )

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