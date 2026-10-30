"""Gera o ícone do JARVIS (assets/jarvis.ico) sem depender de arquivos externos."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SIZE = 512


def build_icon() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = SIZE // 2

    # Placa de fundo
    draw.rounded_rectangle(
        (10, 10, SIZE - 10, SIZE - 10),
        radius=112,
        fill=(4, 12, 24, 255),
        outline=(28, 104, 178, 255),
        width=7,
    )

    # Anéis do reator
    for radius, width, color in (
        (196, 10, (62, 166, 255, 235)),
        (156, 4, (86, 225, 255, 190)),
        (108, 8, (62, 166, 255, 230)),
    ):
        draw.ellipse(
            (center - radius, center - radius, center + radius, center + radius),
            outline=color,
            width=width,
        )

    # Marcações radiais
    for index in range(24):
        angle = index * math.tau / 24
        inner, outer = 210, 232
        draw.line(
            (
                center + inner * math.cos(angle),
                center + inner * math.sin(angle),
                center + outer * math.cos(angle),
                center + outer * math.sin(angle),
            ),
            fill=(86, 225, 255, 170),
            width=5,
        )

    # Núcleo luminoso
    for radius, color in (
        (78, (12, 58, 100, 255)),
        (62, (22, 116, 176, 255)),
        (46, (54, 190, 236, 255)),
        (30, (170, 244, 255, 255)),
        (16, (238, 253, 255, 255)),
    ):
        draw.ellipse(
            (center - radius, center - radius, center + radius, center + radius),
            fill=color,
        )

    # Reflexo superior
    draw.ellipse(
        (center - 26, center - 34, center - 4, center - 12),
        fill=(255, 255, 255, 120),
    )
    return image


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    image = build_icon()
    target = ASSETS / "jarvis.ico"
    image.save(
        target,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    image.save(ASSETS / "jarvis.png", format="PNG")
    print(f"Ícone gerado em {target}")


if __name__ == "__main__":
    main()
