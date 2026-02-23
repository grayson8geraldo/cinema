#!/usr/bin/env python3
"""
Скрипт композитинга видео на экран кинотеатра.

Накладывает видео на фоновое изображение кинозала с использованием маски,
полупрозрачности и цветокоррекции, имитируя проекцию на экран.

Использование:
  python compose.py --bg cinema_bg.png --mask screen_mask.png --video input_video.mp4 -o output.mp4

Параметры:
  --bg        Фоновое изображение кинозала (9:16, например 1080x1920)
  --mask      Маска экрана (чёрно-белая, того же размера что и фон)
  --video     Исходное видео для наложения
  -o          Выходной файл (по умолчанию: output_cinema.mp4)
  --opacity   Непрозрачность видео 0.0-1.0 (по умолчанию: 0.85)
  --bitrate   Битрейт выходного видео (по умолчанию: 3000k)
  --tone      Тональность цветокоррекции: warm / cold / neutral (по умолчанию: warm)
  --darkness  Степень затемнения: light / medium / heavy (по умолчанию: medium)
  --no-audio  Не включать аудиодорожку из видео
  --preview   Создать превью одного кадра (PNG) вместо видео
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


def get_curves_filter(tone: str, darkness: str) -> str:
    """
    Генерирует фильтр curves для цветокоррекции.

    tone:     warm (тёплый, жёлто-оранжевый свет) / cold (холодный, синеватый) / neutral
    darkness: light / medium / heavy
    """
    # Базовые кривые затемнения (master channel)
    # \: — экранированное двоеточие (разделитель точек кривой),
    # чтобы не конфликтовать с : — разделителем опций FFmpeg
    darkness_curves = {
        "light":  "m=0/0\\:0.5/0.4\\:1/0.85",
        "medium": "m=0/0\\:0.5/0.35\\:1/0.75",
        "heavy":  "m=0/0\\:0.5/0.28\\:1/0.65",
    }

    # Тональные кривые (RGB каналы)
    tone_curves = {
        "warm":    "r=0/0\\:0.5/0.52\\:1/1:b=0/0\\:0.5/0.42\\:1/0.9",
        "cold":    "r=0/0\\:0.5/0.42\\:1/0.9:b=0/0\\:0.5/0.55\\:1/1",
        "neutral": "",
    }

    parts = [darkness_curves.get(darkness, darkness_curves["medium"])]
    tc = tone_curves.get(tone, "")
    if tc:
        parts.append(tc)

    return "curves=" + ":".join(parts)


def build_ffmpeg_command(
    ffmpeg: str,
    bg: str,
    mask: str,
    video: str,
    output: str,
    opacity: float,
    bitrate: str,
    tone: str,
    darkness: str,
    include_audio: bool,
    preview: bool,
    bg_width: int,
    bg_height: int,
    video_duration: float,
) -> list[str]:
    """Собирает команду FFmpeg для композитинга."""

    curves = get_curves_filter(tone, darkness)
    w, h = bg_width, bg_height

    # Фильтр-граф:
    # 1. Масштабируем видео и маску до размера фона
    # 2. Применяем маску (alphamerge) — видео видно только в области экрана
    # 3. Применяем полупрозрачность (colorchannelmixer aa=opacity) и цветокоррекцию
    # 4. Накладываем результат поверх фона
    filter_complex = (
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black[scaled_vid];"
        f"[2:v]scale={w}:{h}[scaled_mask];"
        f"[scaled_vid][scaled_mask]alphamerge[masked_vid];"
        f"[masked_vid]colorchannelmixer=aa={opacity},{curves}[transparent_vid];"
        f"[0:v][transparent_vid]overlay=(W-w)/2:(H-h)/2:shortest=1[outv]"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-loop", "1", "-i", bg,
        "-i", video,
        "-loop", "1", "-i", mask,
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
        description="Композитинг видео на экран кинотеатра.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bg", required=True, help="Фоновое изображение кинозала")
    parser.add_argument("--mask", required=True, help="Маска экрана (ч/б)")
    parser.add_argument("--video", required=True, help="Исходное видео")
    parser.add_argument("-o", "--output", default="output_cinema.mp4", help="Выходной файл")
    parser.add_argument(
        "--opacity", type=float, default=0.85,
        help="Непрозрачность видео 0.0-1.0 (по умолчанию: 0.85)",
    )
    parser.add_argument("--bitrate", default="3000k", help="Битрейт видео (по умолчанию: 3000k)")
    parser.add_argument(
        "--tone", choices=["warm", "cold", "neutral"], default="warm",
        help="Тональность: warm/cold/neutral (по умолчанию: warm)",
    )
    parser.add_argument(
        "--darkness", choices=["light", "medium", "heavy"], default="medium",
        help="Затемнение: light/medium/heavy (по умолчанию: medium)",
    )
    parser.add_argument("--no-audio", action="store_true", help="Не включать аудио")
    parser.add_argument(
        "--preview", action="store_true",
        help="Создать превью одного кадра (PNG) вместо видео",
    )

    args = parser.parse_args()

    if args.opacity < 0.0 or args.opacity > 1.0:
        print("Ошибка: --opacity должен быть в диапазоне 0.0 - 1.0", file=sys.stderr)
        sys.exit(1)

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
        opacity=args.opacity,
        bitrate=args.bitrate,
        tone=args.tone,
        darkness=args.darkness,
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
    print(f"  Прозрачность: {args.opacity}")
    print(f"  Тон:      {args.tone}")
    print(f"  Затемнение:   {args.darkness}")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("Ошибка FFmpeg:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    print(f"Готово! Результат: {args.output}")


if __name__ == "__main__":
    main()
