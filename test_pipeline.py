#!/usr/bin/env python3
"""
Интеграционный тест: создаёт тестовые данные и проверяет пайплайн.
Использует уменьшенное разрешение (360x640) для быстрого прохождения.
"""

import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw

TEST_DIR = Path(__file__).parent / "test_data"
TEST_W, TEST_H = 360, 640

# Координаты «экрана» в тестовом разрешении
SCREEN_LEFT, SCREEN_TOP = 60, 130
SCREEN_RIGHT, SCREEN_BOTTOM = 300, 300


def create_test_bg():
    """Создаёт тестовый фон кинозала."""
    img = Image.new("RGB", (TEST_W, TEST_H), color=(30, 25, 35))
    draw = ImageDraw.Draw(img)
    draw.rectangle([SCREEN_LEFT, SCREEN_TOP, SCREEN_RIGHT, SCREEN_BOTTOM], fill=(80, 80, 90))
    draw.rectangle([100, 145, 260, 165], fill=(180, 180, 200))  # блик
    for row in range(2):
        for col in range(5):
            x = 30 + col * 65
            y = 420 + row * 80
            draw.rounded_rectangle([x, y, x + 40, y + 50], radius=5, fill=(60, 30, 30))
    path = TEST_DIR / "cinema_bg.png"
    img.save(path)
    print(f"  Тестовый фон: {path}")
    return path


def create_test_video():
    """Создаёт короткое тестовое видео (1 сек) через ffmpeg."""
    path = TEST_DIR / "test_video.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"color=c=blue:size={TEST_W}x{TEST_H}:duration=1:rate=12",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    print(f"  Тестовое видео: {path}")
    return path


def test_create_mask():
    """Тест создания маски через --rect."""
    mask_path = TEST_DIR / "screen_mask.png"
    cmd = [
        sys.executable, "create_mask.py",
        "--size", f"{TEST_W}x{TEST_H}",
        "--rect", f"{SCREEN_LEFT},{SCREEN_TOP},{SCREEN_RIGHT},{SCREEN_BOTTOM}",
        "-o", str(mask_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"create_mask.py failed: {result.stderr}"

    img = Image.open(mask_path)
    assert img.size == (TEST_W, TEST_H), f"Wrong mask size: {img.size}"

    mid_x = (SCREEN_LEFT + SCREEN_RIGHT) // 2
    mid_y = (SCREEN_TOP + SCREEN_BOTTOM) // 2
    pixel = img.getpixel((mid_x, mid_y))
    assert pixel == (255, 255, 255), f"Pixel in screen area should be white, got {pixel}"

    pixel = img.getpixel((5, 5))
    assert pixel == (0, 0, 0), f"Pixel outside screen should be black, got {pixel}"

    print("  OK")
    return mask_path


def test_create_mask_from_points():
    """Тест создания маски через --points."""
    mask_path = TEST_DIR / "screen_mask_points.png"
    cmd = [
        sys.executable, "create_mask.py",
        "--size", f"{TEST_W}x{TEST_H}",
        "--points",
        f"{SCREEN_LEFT},{SCREEN_TOP}",
        f"{SCREEN_RIGHT},{SCREEN_TOP}",
        f"{SCREEN_RIGHT},{SCREEN_BOTTOM}",
        f"{SCREEN_LEFT},{SCREEN_BOTTOM}",
        "-o", str(mask_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"create_mask.py --points failed: {result.stderr}"
    print("  OK")


def test_create_mask_from_json():
    """Тест создания маски через --from-json."""
    import json

    json_path = TEST_DIR / "screen_coords.json"
    with open(json_path, "w") as f:
        json.dump({
            "points": [
                [SCREEN_LEFT, SCREEN_TOP],
                [SCREEN_RIGHT, SCREEN_TOP],
                [SCREEN_RIGHT, SCREEN_BOTTOM],
                [SCREEN_LEFT, SCREEN_BOTTOM],
            ]
        }, f)

    mask_path = TEST_DIR / "screen_mask_json.png"
    cmd = [
        sys.executable, "create_mask.py",
        "--size", f"{TEST_W}x{TEST_H}",
        "--from-json", str(json_path),
        "-o", str(mask_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"create_mask.py --from-json failed: {result.stderr}"
    print("  OK")


def test_compose():
    """Тест полного пайплайна композитинга."""
    bg_path = create_test_bg()
    video_path = create_test_video()
    mask_path = TEST_DIR / "screen_mask.png"
    output_path = TEST_DIR / "output_cinema.mp4"

    cmd = [
        sys.executable, "compose.py",
        "--bg", str(bg_path),
        "--mask", str(mask_path),
        "--video", str(video_path),
        "-o", str(output_path),
        "--opacity", "0.85",
        "--tone", "warm",
        "--darkness", "medium",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"compose.py failed: {result.stderr}\n{result.stdout}"

    assert output_path.is_file(), "Output video was not created"
    assert output_path.stat().st_size > 1000, "Output video is suspiciously small"
    print(f"  OK ({output_path.stat().st_size} bytes)")


def test_compose_preview():
    """Тест создания превью."""
    bg_path = TEST_DIR / "cinema_bg.png"
    mask_path = TEST_DIR / "screen_mask.png"
    video_path = TEST_DIR / "test_video.mp4"
    output_path = TEST_DIR / "preview.png"

    cmd = [
        sys.executable, "compose.py",
        "--bg", str(bg_path),
        "--mask", str(mask_path),
        "--video", str(video_path),
        "-o", str(output_path),
        "--preview",
        "--tone", "cold",
        "--darkness", "heavy",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"compose.py --preview failed: {result.stderr}\n{result.stdout}"

    assert output_path.is_file(), "Preview image was not created"
    img = Image.open(output_path)
    assert img.size == (TEST_W, TEST_H), f"Wrong preview size: {img.size}"
    print("  OK")


def test_compose_tones():
    """Тест всех комбинаций тональности и затемнения."""
    bg_path = TEST_DIR / "cinema_bg.png"
    mask_path = TEST_DIR / "screen_mask.png"
    video_path = TEST_DIR / "test_video.mp4"

    for tone in ["warm", "cold", "neutral"]:
        for darkness in ["light", "medium", "heavy"]:
            output_path = TEST_DIR / f"output_{tone}_{darkness}.mp4"
            cmd = [
                sys.executable, "compose.py",
                "--bg", str(bg_path),
                "--mask", str(mask_path),
                "--video", str(video_path),
                "-o", str(output_path),
                "--tone", tone,
                "--darkness", darkness,
                "--no-audio",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, (
                f"compose.py --tone {tone} --darkness {darkness} failed: "
                f"{result.stderr}\n{result.stdout}"
            )
            assert output_path.is_file()
            print(f"  {tone}/{darkness}: OK")


def main():
    TEST_DIR.mkdir(exist_ok=True)

    print("=" * 50)
    print("Тест 1: Маска (--rect)")
    test_create_mask()

    print("Тест 2: Маска (--points)")
    test_create_mask_from_points()

    print("Тест 3: Маска (--from-json)")
    test_create_mask_from_json()

    print("Тест 4: Композитинг видео")
    test_compose()

    print("Тест 5: Превью (один кадр)")
    test_compose_preview()

    print("Тест 6: Все тональности и затемнения")
    test_compose_tones()

    print("=" * 50)
    print("Все тесты пройдены!")


if __name__ == "__main__":
    main()
