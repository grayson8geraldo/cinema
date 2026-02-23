#!/usr/bin/env python3
"""
Веб-интерфейс для композитинга видео на экран кинотеатра.

Запуск:
  python app.py
  Откройте http://localhost:5000

Функциональность:
  - Загрузка фона, маски и видео через браузер
  - Создание маски прямо в интерфейсе (из координат)
  - Настройка параметров: прозрачность, тон, затемнение
  - Предпросмотр одного кадра
  - Скачивание готового видео
"""

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from compose import build_ffmpeg_command
from create_mask import create_mask

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_DIR = Path(__file__).parent / "uploads"
RESULTS_DIR = Path(__file__).parent / "results"

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp"}
ALLOWED_VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def _ensure_dirs():
    UPLOAD_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)


def _find_tool(name: str) -> str:
    """Находит путь к инструменту (ffmpeg/ffprobe), бросает RuntimeError если не найден."""
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} не найден. Установите ffmpeg.")
    return path


def _get_image_size(path: str) -> tuple[int, int]:
    """Определяет размер изображения через ffprobe."""
    ffprobe = _find_tool("ffprobe")
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe ошибка для {path}: {result.stderr}")
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def _get_video_duration(path: str) -> float:
    """Определяет длительность видео через ffprobe."""
    ffprobe = _find_tool("ffprobe")
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe ошибка для {path}: {result.stderr}")
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def _allowed_file(filename: str, extensions: set[str]) -> bool:
    return Path(filename).suffix.lower() in extensions


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    _ensure_dirs()

    job_id = uuid.uuid4().hex[:12]
    job_dir = RESULTS_DIR / job_id
    job_dir.mkdir()

    try:
        # --- Фон ---
        bg_file = request.files.get("bg")
        if not bg_file or not bg_file.filename:
            flash("Загрузите фоновое изображение кинозала.", "error")
            return redirect(url_for("index"))
        if not _allowed_file(bg_file.filename, ALLOWED_IMAGE_EXT):
            flash("Фон: допустимые форматы — PNG, JPG, BMP.", "error")
            return redirect(url_for("index"))
        bg_path = job_dir / ("bg" + Path(bg_file.filename).suffix.lower())
        bg_file.save(bg_path)

        # --- Видео ---
        video_file = request.files.get("video")
        if not video_file or not video_file.filename:
            flash("Загрузите видеофайл.", "error")
            return redirect(url_for("index"))
        if not _allowed_file(video_file.filename, ALLOWED_VIDEO_EXT):
            flash("Видео: допустимые форматы — MP4, AVI, MOV, MKV, WEBM.", "error")
            return redirect(url_for("index"))
        video_path = job_dir / ("video" + Path(video_file.filename).suffix.lower())
        video_file.save(video_path)

        # --- Маска ---
        mask_mode = request.form.get("mask_mode", "upload")
        if mask_mode == "upload":
            mask_file = request.files.get("mask")
            if not mask_file or not mask_file.filename:
                flash("Загрузите маску экрана или создайте из координат.", "error")
                return redirect(url_for("index"))
            if not _allowed_file(mask_file.filename, ALLOWED_IMAGE_EXT):
                flash("Маска: допустимые форматы — PNG, JPG, BMP.", "error")
                return redirect(url_for("index"))
            mask_path = job_dir / ("mask" + Path(mask_file.filename).suffix.lower())
            mask_file.save(mask_path)
        else:
            # Создать маску из координат прямоугольника
            try:
                rect_left = int(request.form.get("rect_left", 0))
                rect_top = int(request.form.get("rect_top", 0))
                rect_right = int(request.form.get("rect_right", 0))
                rect_bottom = int(request.form.get("rect_bottom", 0))
            except (ValueError, TypeError):
                flash("Координаты маски должны быть целыми числами.", "error")
                return redirect(url_for("index"))

            if rect_right <= rect_left or rect_bottom <= rect_top:
                flash("Некорректные координаты прямоугольника маски.", "error")
                return redirect(url_for("index"))

            bg_w, bg_h = _get_image_size(str(bg_path))
            mask_path = job_dir / "mask.png"
            polygon = [
                (rect_left, rect_top),
                (rect_right, rect_top),
                (rect_right, rect_bottom),
                (rect_left, rect_bottom),
            ]
            create_mask((bg_w, bg_h), polygon, str(mask_path))

        # --- Параметры ---
        bitrate = request.form.get("bitrate", "3500k").strip()
        if not bitrate:
            bitrate = "3500k"

        try:
            screen_opacity = float(request.form.get("screen_opacity", 0.7))
        except (ValueError, TypeError):
            screen_opacity = 0.7
        screen_opacity = max(0.0, min(1.0, screen_opacity))

        preview = request.form.get("preview") == "on"
        no_audio = request.form.get("no_audio") == "on"

        # --- Обработка ---
        ffmpeg = _find_tool("ffmpeg")
        bg_w, bg_h = _get_image_size(str(bg_path))
        vid_duration = _get_video_duration(str(video_path))

        if preview:
            output_name = "result.png"
        else:
            output_name = "result.mp4"

        output_path = job_dir / output_name

        cmd = build_ffmpeg_command(
            ffmpeg=ffmpeg,
            bg=str(bg_path),
            mask=str(mask_path),
            video=str(video_path),
            output=str(output_path),
            bitrate=bitrate,
            screen_opacity=screen_opacity,
            include_audio=not no_audio,
            preview=preview,
            bg_width=bg_w,
            bg_height=bg_h,
            video_duration=vid_duration,
        )

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # При ошибке с аудио — повторить без аудио
            if not no_audio and not preview:
                cmd_retry = build_ffmpeg_command(
                    ffmpeg=ffmpeg,
                    bg=str(bg_path),
                    mask=str(mask_path),
                    video=str(video_path),
                    output=str(output_path),
                    bitrate=bitrate,
                    screen_opacity=screen_opacity,
                    include_audio=False,
                    preview=preview,
                    bg_width=bg_w,
                    bg_height=bg_h,
                    video_duration=vid_duration,
                )
                result2 = subprocess.run(cmd_retry, capture_output=True, text=True)
                if result2.returncode == 0:
                    return redirect(url_for("result", job_id=job_id))

            # Показываем последние строки stderr — там суть ошибки
            stderr_lines = result.stderr.strip().splitlines()
            error_tail = "\n".join(stderr_lines[-5:]) if stderr_lines else "Неизвестная ошибка"
            flash(f"Ошибка FFmpeg:\n{error_tail}", "error")
            return redirect(url_for("index"))

        return redirect(url_for("result", job_id=job_id))

    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Непредвиденная ошибка: {e}", "error")
        return redirect(url_for("index"))


@app.route("/result/<job_id>")
def result(job_id):
    job_dir = RESULTS_DIR / job_id
    if not job_dir.is_dir():
        flash("Результат не найден.", "error")
        return redirect(url_for("index"))

    # Определяем тип результата
    result_png = job_dir / "result.png"
    result_mp4 = job_dir / "result.mp4"

    is_preview = result_png.is_file()
    filename = "result.png" if is_preview else "result.mp4"

    return render_template(
        "result.html",
        job_id=job_id,
        is_preview=is_preview,
        filename=filename,
    )


@app.route("/download/<job_id>/<filename>")
def download(job_id, filename):
    job_dir = RESULTS_DIR / job_id
    file_path = job_dir / filename
    if not file_path.is_file():
        flash("Файл не найден.", "error")
        return redirect(url_for("index"))
    return send_file(file_path, as_attachment=True)


@app.route("/preview_image/<job_id>")
def preview_image(job_id):
    """Отдаёт превью-изображение для показа в браузере."""
    file_path = RESULTS_DIR / job_id / "result.png"
    if not file_path.is_file():
        flash("Превью не найдено.", "error")
        return redirect(url_for("index"))
    return send_file(file_path, mimetype="image/png")


if __name__ == "__main__":
    _ensure_dirs()
    app.run(host="0.0.0.0", port=5000, debug=True)
