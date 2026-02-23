#!/usr/bin/env python3
"""
Скрипт композитинга видео на экран кинотеатра (извлечение блика).

Техника:
  1. Из фона извлекается яркий блик через контрастную маску (format=gray → curves)
  2. Видео накладывается на фон через маску экрана (overlay)
  3. Извлечённый блик накладывается поверх композита (overlay с альфой)

Это создаёт точечный блик только в ярких областях фона, без розовой заливки.

Использование:
  python compose.py --bg cinema_bg.png --mask screen_mask.png --video input_video.mp4 -o output.mp4

Параметры:
  --bg              Фоновое изображение кинозала (9:16, например 1080x1920)
  --mask            Маска экрана (чёрно-белая, того же размера что и фон)
  --video           Исходное видео для наложения
  -o                Выходной файл (по умолчанию: output_cinema.mp4)
  --bitrate         Битрейт выходного видео (по умолчанию: 3500k)
  --screen-opacity  Сила блика 0.0-1.0 (по умолчанию: 0.7)
  --no-audio        Не включать аудиодорожку из видео
  --preview         Создать превью одного кадра (PNG) вместо видео
"""

import argparse
import json
import subprocess
import sys
import shutil
from pathlib import Path


def check_ffmpeg() -> str:
    """Проверяет наличие ffmpeg в системе."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Ошибка: ffmpeg не найден. Установите ffmpeg и повторите.", file=sys.stderr)
        sys.exit(1)
    return ffmpeg


def validate_files(*paths: str) -> None:
    """Проверяет существование входных файлов."""
    for p in paths:
        if not Path(p).is_file():
            print(f"Ошибка: файл не найден: {p}", file=sys.stderr)
            sys.exit(1)


def get_image_size(ffprobe: str, path: str) -> tuple[int, int]:
    """Определяет размер изображения через ffprobe."""
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Ошибка ffprobe для {path}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def get_video_duration(ffprobe: str, path: str) -> float:
    """Определяет длительность видео в секундах через ffprobe."""
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Ошибка ffprobe для {path}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def get_mask_bbox(mask_path: str) -> tuple[int, int, int, int]:
    """Определяет bounding box белой области маски (экрана).

    Возвращает (x, y, width, height) — положение и размер экрана внутри маски.
    """
    from PIL import Image

    img = Image.open(mask_path).convert("L")
    bbox = img.getbbox()  # (left, upper, right, lower) или None
    if not bbox:
        # Маска полностью чёрная — используем весь размер
        w, h = img.size
        return 0, 0, w, h
    left, upper, right, lower = bbox
    return left, upper, right - left, lower - upper


def build_ffmpeg_command(
    ffmpeg: str,
    bg: str,
    mask: str,
    video: str,
    output: str,
    bitrate: str,
    screen_opacity: float,
    include_audio: bool,
    preview: bool,
    bg_width: int,
    bg_height: int,
    screen_x: int,
    screen_y: int,
    screen_w: int,
    screen_h: int,
    video_duration: float,
) -> list[str]:
    """Собирает команду FFmpeg для композитинга (извлечение блика)."""

    w, h = bg_width, bg_height
    sx, sy, sw, sh = screen_x, screen_y, screen_w, screen_h

    # Фильтр-граф:
    # 1. Зацикливаем фон (split=3: для базы, glare-маски, glare-слоя)
    # 2. Масштабируем видео до размера ЭКРАНА, pad до фона в позиции экрана
    # 3. alphamerge с маской экрана — видео видно только в области экрана
    # 4. overlay видео на фон → base
    # 5. Из фона: geq порог яркости >200 → boxblur → glare_mask
    # 6. alphamerge фона с glare_mask → glare_layer (только яркие пиксели фона)
    # 7. blend dodge — блик светит поверх композита
    filter_complex = (
        f"[0:v]loop=loop=-1:size=32767:start=0,split=3[bg1][bg2][bg3];"
        f"[2:v]loop=loop=-1:size=32767:start=0[mask_loop];"
        f"[1:v]scale={sw}:{sh}:force_original_aspect_ratio=decrease,"
        f"pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"format=rgba,pad={w}:{h}:{sx}:{sy}:color=black@0[padded_vid];"
        f"[padded_vid][mask_loop]alphamerge[masked_vid];"
        f"[bg1][masked_vid]overlay=0:0:shortest=1[base];"
        f"[bg2]format=gray,"
        f"geq=lum='if(gt(lum(X,Y),200),255,0)',"
        f"boxblur=10[glare_mask];"
        f"[bg3]format=gray,format=rgba[bg3_neutral];"
        f"[bg3_neutral][glare_mask]alphamerge[glare_layer];"
        f"[base][glare_layer]blend=all_mode=dodge:all_opacity={screen_opacity}[outv]"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i", bg,
        "-i", video,
        "-i", mask,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
    ]

    if include_audio and not preview:
        cmd.extend(["-map", "1:a?"])

    # Ограничиваем длительность выхода длительностью исходного видео
    cmd.extend(["-t", str(video_duration)])

    if preview:
        cmd.extend([
            "-frames:v", "1",
            output,
        ])
    else:
        cmd.extend([
            "-c:v", "libx264",
            "-b:v", bitrate,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output,
        ])

    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Композитинг видео на экран кинотеатра (Screen-режим).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bg", required=True, help="Фоновое изображение кинозала")
    parser.add_argument("--mask", required=True, help="Маска экрана (ч/б)")
    parser.add_argument("--video", required=True, help="Исходное видео")
    parser.add_argument("-o", "--output", default="output_cinema.mp4", help="Выходной файл")
    parser.add_argument("--bitrate", default="3500k", help="Битрейт видео (по умолчанию: 3500k)")
    parser.add_argument(
        "--screen-opacity", type=float, default=0.7,
        help="Сила блика 0.0-1.0 (по умолчанию: 0.7)",
    )
    parser.add_argument("--no-audio", action="store_true", help="Не включать аудио")
    parser.add_argument(
        "--preview", action="store_true",
        help="Создать превью одного кадра (PNG) вместо видео",
    )

    args = parser.parse_args()

    args.screen_opacity = max(0.0, min(1.0, args.screen_opacity))

    ffmpeg = check_ffmpeg()
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        print("Ошибка: ffprobe не найден. Установите ffmpeg и повторите.", file=sys.stderr)
        sys.exit(1)

    validate_files(args.bg, args.mask, args.video)

    bg_w, bg_h = get_image_size(ffprobe, args.bg)
    vid_duration = get_video_duration(ffprobe, args.video)
    sx, sy, sw, sh = get_mask_bbox(args.mask)

    if args.preview and not args.output.lower().endswith(".png"):
        args.output = Path(args.output).stem + "_preview.png"

    cmd = build_ffmpeg_command(
        ffmpeg=ffmpeg,
        bg=args.bg,
        mask=args.mask,
        video=args.video,
        output=args.output,
        bitrate=args.bitrate,
        screen_opacity=args.screen_opacity,
        include_audio=not args.no_audio,
        preview=args.preview,
        bg_width=bg_w,
        bg_height=bg_h,
        screen_x=sx,
        screen_y=sy,
        screen_w=sw,
        screen_h=sh,
        video_duration=vid_duration,
    )

    print("Запуск FFmpeg...")
    print(f"  Фон:      {args.bg}")
    print(f"  Маска:    {args.mask}")
    print(f"  Видео:    {args.video}")
    print(f"  Выход:    {args.output}")
    print(f"  Экран:    {sw}x{sh} @ ({sx},{sy})")
    print(f"  Битрейт:  {args.bitrate}")
    print(f"  Блик:     {args.screen_opacity}")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("Ошибка FFmpeg:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    print(f"Готово! Результат: {args.output}")


if __name__ == "__main__":
    main()
