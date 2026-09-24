import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent
GENERATED_DIR = BASE_DIR / "generated"

GENERATED_DIR.mkdir(exist_ok=True)


def create_story_folder(
    slug: str,
    title: str,
    recipient: str,
    sender: str,
    description: str,
    image_paths: list,
    video_paths: list,
    music_path: str | None,
):

    story_dir = GENERATED_DIR / slug

    images_dir = story_dir / "images"
    videos_dir = story_dir / "videos"
    music_dir = story_dir / "music"

    images_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)
    music_dir.mkdir(parents=True, exist_ok=True)

    saved_images = []

    for image in image_paths:

        source = BASE_DIR / image

        destination = images_dir / source.name

        shutil.copy2(source, destination)

        saved_images.append(
            f"images/{source.name}"
        )

    saved_videos = []

    for video in video_paths:

        source = BASE_DIR / video

        destination = videos_dir / source.name

        shutil.copy2(source, destination)

        saved_videos.append(
            f"videos/{source.name}"
        )

    saved_music = None

    if music_path:

        source = BASE_DIR / music_path

        destination = music_dir / source.name

        shutil.copy2(source, destination)

        saved_music = f"music/{source.name}"

    story = {

        "title": title,

        "recipient": recipient,

        "sender": sender,

        "description": description,

        "banner": saved_images[0] if saved_images else "",

        "loginProfiles": saved_images[:4],

        "gallery": saved_images,

        "videos": saved_videos,

        "music": saved_music,

        "episodes": [],

        "timeline": [],

        "loveLetter": "",

        "guestMessages": []

    }

    with open(
        story_dir / "story.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            story,
            f,
            indent=4,
            ensure_ascii=False
        )

    return story_dir