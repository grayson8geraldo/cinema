#!/usr/bin/env python3
"""
Утилита для создания маски экрана кинотеатра.

Создаёт чёрно-белое изображение (маску), где:
  - Белая область (#FFFFFF) = экран кинотеатра (сюда будет наложено видео)
  - Чёрная область (#000000) = всё остальное

Способы задать область экрана:
  1. Через JSON-файл с координатами четырёх углов экрана
  2. Через аргументы командной строки (4 точки: x1,y1 x2,y2 x3,y3 x4,y4)
  3. Через прямоугольник (--rect left,top,right,bottom)

Примеры:
  # Четыре угла (по часовой стрелке сверху-слева):
  python create_mask.py --size 1080x1920 --points 200,400 880,400 880,900 200,900 -o screen_mask.png

  # Прямоугольник:
  python create_mask.py --size 1080x1920 --rect 200,400,880,900 -o screen_mask.png

  # Из JSON-файла:
  python create_mask.py --size 1080x1920 --from-json screen_coords.json -o screen_mask.png
"""

import argparse
import json
import sys
from PIL import Image, ImageDraw


def parse_point(s: str) -> tuple[int, int]:
    """Парсит строку 'x,y' в кортеж (x, y)."""
    parts = s.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Неверный формат точки: '{s}'. Ожидается: x,y")
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        raise argparse.ArgumentTypeError(f"Координаты должны быть целыми числами: '{s}'")


def parse_size(s: str) -> tuple[int, int]:
    """Парсит строку 'WxH' в кортеж (width, height)."""
    parts = s.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Неверный формат размера: '{s}'. Ожидается: WxH (например 1080x1920)")
    try:
        w, h = int(parts[0]), int(parts[1])
        if w <= 0 or h <= 0:
            raise ValueError
        return (w, h)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Размеры должны быть положительными целыми числами: '{s}'")


def parse_rect(s: str) -> list[tuple[int, int]]:
    """Парсит строку 'left,top,right,bottom' в 4 угловые точки."""
    parts = s.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"Неверный формат прямоугольника: '{s}'. Ожидается: left,top,right,bottom"
        )
    try:
        left, top, right, bottom = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Координаты должны быть целыми числами: '{s}'")

    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def create_mask(size: tuple[int, int], polygon: list[tuple[int, int]], output: str) -> None:
    """
    Создаёт маску: чёрное изображение с белым полигоном (область экрана).

    Args:
        size: (width, height) итогового изображения.
        polygon: Список точек (x, y), задающих многоугольник экрана.
        output: Путь для сохранения маски.
    """
    img = Image.new("RGB", size, color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.polygon(polygon, fill=(255, 255, 255))
    img.save(output)
    print(f"Маска сохранена: {output} ({size[0]}x{size[1]})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Создание маски экрана кинотеатра для композитинга.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--size", type=parse_size, default="1080x1920",
        help="Размер изображения WxH (по умолчанию: 1080x1920)",
    )
    parser.add_argument("-o", "--output", default="screen_mask.png", help="Выходной файл маски")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--points", nargs="+", type=parse_point, metavar="X,Y",
        help="Координаты углов экрана (минимум 3 точки). Пример: 200,400 880,400 880,900 200,900",
    )
    group.add_argument(
        "--rect", type=parse_rect, metavar="L,T,R,B",
        help="Прямоугольная область экрана: left,top,right,bottom",
    )
    group.add_argument(
        "--from-json", metavar="FILE",
        help='JSON-файл с ключом "points": [[x1,y1], [x2,y2], ...]',
    )

    args = parser.parse_args()

    if args.points:
        polygon = args.points
    elif args.rect:
        polygon = args.rect
    elif args.from_json:
        try:
            with open(args.from_json, "r") as f:
                data = json.load(f)
            raw_points = data["points"]
            polygon = [(int(p[0]), int(p[1])) for p in raw_points]
        except (FileNotFoundError, KeyError, json.JSONDecodeError, IndexError) as e:
            print(f"Ошибка чтения JSON: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    if len(polygon) < 3:
        print("Необходимо минимум 3 точки для создания маски.", file=sys.stderr)
        sys.exit(1)

    create_mask(args.size, polygon, args.output)


if __name__ == "__main__":
    main()
