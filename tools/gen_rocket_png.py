from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    out = Path("app/static/icons/rocket.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    w = h = 256
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    accent = (99, 102, 241, 255)  # #6366F1
    accent2 = (165, 180, 252, 255)  # #A5B4FC
    near_white = (241, 245, 249, 255)  # #F1F5F9
    stroke_dark = (15, 23, 42, 180)  # subtle outline

    # Rocket body
    body_bbox = (92, 52, 164, 188)
    d.rounded_rectangle(body_bbox, radius=34, fill=accent, outline=stroke_dark, width=3)

    # Nose cone
    nose = [(128, 36), (168, 72), (88, 72)]
    d.polygon(nose, fill=accent2)
    d.line(nose + [nose[0]], fill=stroke_dark, width=3)

    # Fins
    left_fin = [(92, 150), (58, 190), (92, 190)]
    right_fin = [(164, 150), (164, 190), (198, 190)]
    d.polygon(left_fin, fill=accent2)
    d.polygon(right_fin, fill=accent2)
    d.line(left_fin + [left_fin[0]], fill=stroke_dark, width=3)
    d.line(right_fin + [right_fin[0]], fill=stroke_dark, width=3)

    # Window
    win_center = (128, 118)
    win_r = 16
    d.ellipse(
        (
            win_center[0] - win_r,
            win_center[1] - win_r,
            win_center[0] + win_r,
            win_center[1] + win_r,
        ),
        fill=near_white,
        outline=stroke_dark,
        width=3,
    )

    # Body highlight stripe
    highlight = (108, 78, 122, 180)
    d.rounded_rectangle(highlight, radius=10, fill=(255, 255, 255, 60))

    # Flame
    flame_outer = [(128, 210), (154, 196), (142, 236), (128, 248), (114, 236), (102, 196)]
    flame_inner = [(128, 216), (144, 206), (136, 232), (128, 240), (120, 232), (112, 206)]
    d.polygon(flame_outer, fill=(251, 191, 36, 220))  # amber
    d.polygon(flame_inner, fill=(253, 230, 138, 230))

    img.save(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

