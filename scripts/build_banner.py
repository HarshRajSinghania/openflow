"""Compose the README cover from a Flow-generated image (requires Pillow)."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
TEAL = "#63e5cf"
WHITE = "#f2f5f4"
MUTED = "#a7b8b9"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "assets/flow-showcase/portal.jpg")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/banner.png")
    parser.add_argument(
        "--font-dir", type=Path, default=Path("/usr/share/fonts/truetype/dejavu")
    )
    args = parser.parse_args()
    canvas = Image.new("RGB", (1800, 720), "#0c1418")
    draw = ImageDraw.Draw(canvas)

    def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(str(args.font_dir / name), size)

    for x in range(0, 1800, 60):
        draw.line((x, 0, x, 720), fill="#111f24")
    for y in range(0, 720, 60):
        draw.line((0, y, 1800, y), fill="#111f24")
    draw.line((76, 82, 126, 82), fill=TEAL, width=4)
    draw.text((146, 67), "DO CÓDIGO À CRIAÇÃO", font=font(20, True), fill=TEAL)
    draw.text((70, 172), "OpenFlow", font=font(106, True), fill=WHITE)
    draw.text((78, 321), "Google Flow para seus", font=font(33), fill=WHITE)
    draw.text((78, 368), "agentes e aplicações.", font=font(33), fill=WHITE)
    draw.text((79, 454), "MCP + REST  /  Imagens e vídeos", font=font(21), fill=MUTED)
    draw.rounded_rectangle((78, 524, 345, 569), radius=22, outline="#2e655d", width=1)
    draw.text((98, 534), "Sem instalar extensão", font=font(19), fill=TEAL)
    draw.text((78, 655), "OPEN SOURCE  /  SUA CONTA, SEU FLUXO", font=font(15), fill=MUTED)

    draw.line((687, 405, 808, 405, 842, 371, 894, 371), fill="#327a70", width=2)
    draw.ellipse((801, 398, 815, 412), fill=TEAL)
    draw.polygon(((881, 365), (894, 371), (881, 377)), fill=TEAL)

    with Image.open(args.source) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        # Both panels are crops of one still, not a claim of generated video.
        detail = ImageOps.fit(image, (414, 226), centering=(0.82, 0.7))
        hero = ImageOps.fit(image, (824, 464), centering=(0.7, 0.5))

    draw.rounded_rectangle((1113, 28, 1760, 161), radius=14, fill="#14252b", outline="#28424a")
    draw.text((1140, 50), "AGENTE / APLICAÇÃO", font=font(16, True), fill=TEAL)
    draw.text((1140, 84), 'generate_image(prompt="...")', font=font(21), fill=WHITE)
    draw.text((1140, 119), "preview → confirm → download", font=font(15), fill=MUTED)
    canvas.paste(hero, (908, 186))
    draw.rounded_rectangle((905, 183, 1735, 653), radius=5, outline="#577071", width=2)
    draw.rectangle((926, 204, 1190, 238), fill="#101c21")
    draw.text((939, 211), "CRIADO COM OPENFLOW", font=font(16, True), fill=TEAL)

    draw.rectangle((807, 473, 1237, 715), fill="#0c1418")
    canvas.paste(detail, (815, 481))
    draw.rectangle((813, 479, 1231, 709), outline="#577071", width=2)
    draw.rectangle((829, 662, 1043, 694), fill="#101c21")
    draw.text((840, 669), "NANO BANANA 2.1", font=font(15, True), fill=WHITE)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, optimize=True)
    print(f"Saved {args.output} ({canvas.width} × {canvas.height})")


if __name__ == "__main__":
    main()
