#!/usr/bin/env python3
"""
Тест веб-интерфейса: загрузка файлов и обработка через Flask test client.
"""

import subprocess
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

TEST_DIR = Path(__file__).parent / "test_data"
TEST_W, TEST_H = 360, 640
SCREEN_LEFT, SCREEN_TOP = 60, 130
SCREEN_RIGHT, SCREEN_BOTTOM = 300, 300


def ensure_test_data():
    """Создаёт тестовые данные если их нет."""
    TEST_DIR.mkdir(exist_ok=True)

    bg_path = TEST_DIR / "cinema_bg.png"
    if not bg_path.is_file():
        img = Image.new("RGB", (TEST_W, TEST_H), color=(30, 25, 35))
        draw = ImageDraw.Draw(img)
        draw.rectangle([SCREEN_LEFT, SCREEN_TOP, SCREEN_RIGHT, SCREEN_BOTTOM],
                        fill=(80, 80, 90))
        img.save(bg_path)

    mask_path = TEST_DIR / "screen_mask.png"
    if not mask_path.is_file():
        img = Image.new("RGB", (TEST_W, TEST_H), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([SCREEN_LEFT, SCREEN_TOP, SCREEN_RIGHT, SCREEN_BOTTOM],
                        fill=(255, 255, 255))
        img.save(mask_path)

    video_path = TEST_DIR / "test_video.mp4"
    if not video_path.is_file():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            f"color=c=blue:size={TEST_W}x{TEST_H}:duration=1:rate=12",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(video_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    return bg_path, mask_path, video_path


def test_index_page():
    """Тест: главная страница загружается."""
    from app import app

    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Cinema Composer" in resp.data.decode()
        print("  OK: главная страница")


def test_process_with_uploaded_mask():
    """Тест: загрузка фона, маски и видео → получаем превью."""
    from app import app

    bg_path, mask_path, video_path = ensure_test_data()

    with app.test_client() as client:
        data = {
            "bg": (open(bg_path, "rb"), "cinema_bg.png"),
            "mask": (open(mask_path, "rb"), "screen_mask.png"),
            "video": (open(video_path, "rb"), "test_video.mp4"),
            "mask_mode": "upload",
            "opacity": "0.85",
            "tone": "warm",
            "darkness": "medium",
            "bitrate": "3000k",
            "preview": "on",
        }
        resp = client.post("/process", data=data, content_type="multipart/form-data",
                           follow_redirects=False)
        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"
        location = resp.headers.get("Location", "")
        assert "/result/" in location, f"Expected redirect to /result/, got {location}"

        # Следуем по редиректу
        resp2 = client.get(location)
        assert resp2.status_code == 200
        body = resp2.data.decode()
        assert "Готово" in body
        assert "result.png" in body
        print("  OK: обработка с загруженной маской (превью)")


def test_process_with_generated_mask():
    """Тест: создание маски из координат → получаем превью."""
    from app import app

    bg_path, _, video_path = ensure_test_data()

    with app.test_client() as client:
        data = {
            "bg": (open(bg_path, "rb"), "cinema_bg.png"),
            "video": (open(video_path, "rb"), "test_video.mp4"),
            "mask_mode": "create",
            "rect_left": str(SCREEN_LEFT),
            "rect_top": str(SCREEN_TOP),
            "rect_right": str(SCREEN_RIGHT),
            "rect_bottom": str(SCREEN_BOTTOM),
            "opacity": "0.7",
            "tone": "cold",
            "darkness": "heavy",
            "bitrate": "2000k",
            "preview": "on",
        }
        resp = client.post("/process", data=data, content_type="multipart/form-data",
                           follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "/result/" in location

        resp2 = client.get(location)
        assert resp2.status_code == 200
        assert "Готово" in resp2.data.decode()
        print("  OK: обработка с маской из координат (превью)")


def test_process_video_output():
    """Тест: создание видео (не превью)."""
    from app import app

    bg_path, mask_path, video_path = ensure_test_data()

    with app.test_client() as client:
        data = {
            "bg": (open(bg_path, "rb"), "cinema_bg.png"),
            "mask": (open(mask_path, "rb"), "screen_mask.png"),
            "video": (open(video_path, "rb"), "test_video.mp4"),
            "mask_mode": "upload",
            "opacity": "0.85",
            "tone": "neutral",
            "darkness": "light",
            "bitrate": "3000k",
            "no_audio": "on",
        }
        resp = client.post("/process", data=data, content_type="multipart/form-data",
                           follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "/result/" in location

        resp2 = client.get(location)
        assert resp2.status_code == 200
        body = resp2.data.decode()
        assert "Готово" in body
        assert "result.mp4" in body
        print("  OK: обработка видео")


def test_download():
    """Тест: скачивание файла результата."""
    from app import app

    bg_path, mask_path, video_path = ensure_test_data()

    with app.test_client() as client:
        data = {
            "bg": (open(bg_path, "rb"), "cinema_bg.png"),
            "mask": (open(mask_path, "rb"), "screen_mask.png"),
            "video": (open(video_path, "rb"), "test_video.mp4"),
            "mask_mode": "upload",
            "opacity": "0.85",
            "tone": "warm",
            "darkness": "medium",
            "bitrate": "3000k",
            "preview": "on",
        }
        resp = client.post("/process", data=data, content_type="multipart/form-data",
                           follow_redirects=False)
        location = resp.headers.get("Location", "")
        job_id = location.rstrip("/").split("/")[-1]

        resp_dl = client.get(f"/download/{job_id}/result.png")
        assert resp_dl.status_code == 200
        assert len(resp_dl.data) > 100
        print("  OK: скачивание файла")


def test_missing_files():
    """Тест: отсутствие обязательных файлов → ошибка."""
    from app import app

    with app.test_client() as client:
        # Без фона
        resp = client.post("/process", data={
            "mask_mode": "upload",
        }, content_type="multipart/form-data", follow_redirects=True)
        assert resp.status_code == 200
        assert "Загрузите фоновое изображение" in resp.data.decode()
        print("  OK: валидация отсутствующих файлов")


def main():
    print("=" * 50)
    print("Тесты веб-интерфейса")
    print("=" * 50)

    print("\nТест 1: Главная страница")
    test_index_page()

    print("\nТест 2: Обработка с загруженной маской")
    test_process_with_uploaded_mask()

    print("\nТест 3: Обработка с маской из координат")
    test_process_with_generated_mask()

    print("\nТест 4: Создание видео")
    test_process_video_output()

    print("\nТест 5: Скачивание файла")
    test_download()

    print("\nТест 6: Валидация")
    test_missing_files()

    print("\n" + "=" * 50)
    print("Все тесты веб-интерфейса пройдены!")


if __name__ == "__main__":
    main()
