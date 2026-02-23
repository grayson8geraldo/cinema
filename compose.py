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
    video_duration: float,
) -> list[str]:
    """Собирает команду FFmpeg для композитинга (извлечение блика)."""

    w, h = bg_width, bg_height

    # Фильтр-граф:
    # 1. Зацикливаем фон (split=3: для базы, для glare-маски, для извлечения блика)
    # 2. Из фона создаём контрастную ч/б маску (format=gray → curves=strong_contrast)
    #    — яркие блики → белое, всё остальное → чёрное
    # 3. Масштабируем видео, применяем маску экрана → overlay на фон
    # 4. alphamerge фона с glare-маской → извлекаем только яркий блик
    # 5. Накладываем блик поверх композита (overlay, альфа из glare-маски)
    #    screen_opacity контролирует силу блика через масштаб альфа-канала
    filter_complex = (
        f"[0:v]loop=loop=-1:size=32767:start=0,split=3[bg1][bg2][bg3];"
        f"[2:v]loop=loop=-1:size=32767:start=0[mask_loop];"
        f"[bg1]format=gray,curves=strong_contrast[glare_mask];"
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}[scaled_vid];"
        f"[scaled_vid][mask_loop]alphamerge[masked_vid];"
        f"[bg2][masked_vid]overlay=(W-w)/2:(H-h)/2:shortest=1[base_comp];"
        f"[bg3][glare_mask]alphamerge,"
        f"colorchannelmixer=aa={screen_opacity}[glare_only];"
        f"[base_comp][glare_only]overlay=0:0:format=auto[outv]"
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
        video_duration=vid_duration,
    )

    print("Запуск FFmpeg...")
    print(f"  Фон:      {args.bg}")
    print(f"  Маска:    {args.mask}")
    print(f"  Видео:    {args.video}")
    print(f"  Выход:    {args.output}")
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
