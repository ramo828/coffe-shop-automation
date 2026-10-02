#!/usr/bin/env python3
"""
Generate crisp, genuine PNG assets for avatars and shortcuts.
"""
import os
import math
from PIL import Image, ImageDraw, ImageFont

def make_squircle_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask

def create_gradient_bg(size, color1, color2):
    """Create a vertical gradient image."""
    base = Image.new("RGBA", (size, size), color1)
    top = Image.new("RGBA", (size, size), color2)
    mask = Image.new("L", (size, size))
    for y in range(size):
        alpha = int(255 * (y / size))
        for x in range(size):
            mask.putpixel((x, y), alpha)
    base.paste(top, (0, 0), mask)
    return base

def draw_squircle_icon(filename, bg1, bg2, icon_type, label=None):
    size = 256
    img = create_gradient_bg(size, bg1, bg2)
    draw = ImageDraw.Draw(img)

    # Apply squircle mask for smooth iOS style border
    mask = make_squircle_mask(size, 56)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask)
    draw = ImageDraw.Draw(output)

    # Subtle inner border for iOS depth
    draw.rounded_rectangle((1, 1, size-2, size-2), radius=56, outline=(255, 255, 255, 40), width=2)

    cx, cy = size // 2, size // 2

    # Draw specific icon types
    if icon_type == "espresso":
        # Cup body
        draw.ellipse([cx - 45, cy + 10, cx + 45, cy + 45], fill=(240, 240, 245))
        draw.rectangle([cx - 45, cy - 15, cx + 45, cy + 25], fill=(240, 240, 245))
        # Handle
        draw.arc([cx + 30, cy - 10, cx + 65, cy + 25], 270, 90, fill=(240, 240, 245), width=8)
        # Espresso crema inside cup
        draw.ellipse([cx - 40, cy - 22, cx + 40, cy - 5], fill=(180, 83, 9))
        draw.ellipse([cx - 25, cy - 18, cx + 25, cy - 9], fill=(217, 119, 6))
        # Saucer
        draw.ellipse([cx - 65, cy + 35, cx + 65, cy + 50], fill=(220, 220, 225))
        # Steam lines
        for offset in [-18, 0, 18]:
            draw.arc([cx + offset - 8, cy - 55, cx + offset + 8, cy - 30], 180, 0, fill=(255, 255, 255, 180), width=4)

    elif icon_type == "cappuccino":
        # Round bowl cup
        draw.ellipse([cx - 55, cy + 15, cx + 55, cy + 48], fill=(255, 255, 255))
        draw.rectangle([cx - 55, cy - 12, cx + 55, cy + 30], fill=(255, 255, 255))
        # Saucer
        draw.ellipse([cx - 75, cy + 40, cx + 75, cy + 56], fill=(230, 230, 235))
        # Handle
        draw.arc([cx + 40, cy - 5, cx + 75, cy + 30], 270, 90, fill=(255, 255, 255), width=8)
        # Foam top
        draw.ellipse([cx - 50, cy - 20, cx + 50, cy - 2], fill=(250, 245, 240))
        # Latte art heart
        draw.ellipse([cx - 16, cy - 18, cx, cy - 8], fill=(180, 83, 9))
        draw.ellipse([cx, cy - 18, cx + 16, cy - 8], fill=(180, 83, 9))
        draw.polygon([(cx - 15, cy - 13), (cx + 15, cy - 13), (cx, cy - 4)], fill=(180, 83, 9))

    elif icon_type == "latte":
        # Tall glass
        pts = [(cx - 35, cy - 40), (cx + 35, cy - 40), (cx + 25, cy + 48), (cx - 25, cy + 48)]
        draw.polygon(pts, fill=(255, 255, 255, 90), outline=(255, 255, 255, 200), width=3)
        # Layers inside glass
        draw.polygon([(cx - 26, cy + 20), (cx + 26, cy + 20), (cx + 24, cy + 45), (cx - 24, cy + 45)], fill=(245, 240, 235))
        draw.polygon([(cx - 30, cy - 8), (cx + 30, cy - 8), (cx + 26, cy + 20), (cx - 26, cy + 20)], fill=(180, 83, 9))
        draw.polygon([(cx - 33, cy - 35), (cx + 33, cy - 35), (cx + 30, cy - 8), (cx - 30, cy - 8)], fill=(250, 245, 240))

    elif icon_type == "americano":
        # Mug
        draw.rounded_rectangle([cx - 45, cy - 35, cx + 45, cy + 45], radius=12, fill=(30, 41, 59), outline=(255, 255, 255, 220), width=4)
        draw.arc([cx + 35, cy - 15, cx + 70, cy + 25], 270, 90, fill=(255, 255, 255, 220), width=6)
        # Dark coffee fill
        draw.ellipse([cx - 38, cy - 30, cx + 38, cy - 15], fill=(90, 40, 15))
        # Steam
        for offset in [-14, 14]:
            draw.arc([cx + offset - 8, cy - 65, cx + offset + 8, cy - 40], 180, 0, fill=(255, 255, 255, 180), width=4)

    elif icon_type == "cold_brew":
        # Tall plastic tumbler
        pts = [(cx - 38, cy - 35), (cx + 38, cy - 35), (cx + 26, cy + 50), (cx - 26, cy + 50)]
        draw.polygon(pts, fill=(120, 53, 15), outline=(255, 255, 255, 220), width=3)
        # Lid
        draw.rounded_rectangle([cx - 42, cy - 43, cx + 42, cy - 35], radius=4, fill=(255, 255, 255, 220))
        # Green Straw
        draw.line([cx + 10, cy - 70, cx + 8, cy + 40], fill=(34, 197, 94), width=6)
        # Ice cubes
        draw.rectangle([cx - 18, cy - 15, cx - 2, cy + 2], outline=(255, 255, 255, 180), width=3)
        draw.rectangle([cx + 5, cy - 5, cx + 20, cy + 12], outline=(255, 255, 255, 180), width=3)

    elif icon_type == "frappe":
        # Cup with dome lid
        pts = [(cx - 36, cy - 25), (cx + 36, cy - 25), (cx + 25, cy + 50), (cx - 25, cy + 50)]
        draw.polygon(pts, fill=(202, 138, 4), outline=(255, 255, 255, 220), width=3)
        # Dome lid
        draw.arc([cx - 38, cy - 55, cx + 38, cy - 15], 180, 360, fill=(255, 255, 255, 200), width=4)
        # Whipped cream & caramel drizzle
        draw.ellipse([cx - 28, cy - 45, cx + 28, cy - 20], fill=(255, 255, 255))
        draw.arc([cx - 20, cy - 40, cx + 20, cy - 25], 0, 180, fill=(180, 83, 9), width=3)
        # Straw
        draw.line([cx + 5, cy - 72, cx + 2, cy + 20], fill=(239, 68, 68), width=5)

    elif icon_type == "tea":
        # Ceramic cup & leaf
        draw.ellipse([cx - 45, cy + 10, cx + 45, cy + 42], fill=(255, 255, 255))
        draw.rectangle([cx - 45, cy - 15, cx + 45, cy + 25], fill=(255, 255, 255))
        draw.arc([cx + 30, cy - 10, cx + 60, cy + 22], 270, 90, fill=(255, 255, 255), width=7)
        draw.ellipse([cx - 62, cy + 34, cx + 62, cy + 48], fill=(230, 230, 235))
        # Green tea liquor
        draw.ellipse([cx - 38, cy - 20, cx + 38, cy - 7], fill=(101, 163, 13))
        # Tea leaf tag
        draw.ellipse([cx - 15, cy - 48, cx + 15, cy - 28], fill=(34, 197, 94))
        draw.line([cx, cy - 28, cx, cy - 15], fill=(255, 255, 255, 180), width=2)

    elif icon_type == "croissant":
        # Crescent croissant
        draw.ellipse([cx - 60, cy - 25, cx + 60, cy + 30], fill=(217, 119, 6))
        draw.ellipse([cx - 45, cy - 35, cx + 45, cy + 15], fill=(bg1[0], bg1[1], bg1[2]))
        draw.arc([cx - 35, cy - 10, cx - 15, cy + 20], 30, 150, fill=(180, 83, 9), width=3)
        draw.arc([cx - 10, cy - 15, cx + 10, cy + 25], 30, 150, fill=(180, 83, 9), width=4)
        draw.arc([cx + 15, cy - 10, cx + 35, cy + 20], 30, 150, fill=(180, 83, 9), width=3)

    elif icon_type == "dessert":
        # Cake slice
        pts = [(cx - 55, cy + 25), (cx + 50, cy + 35), (cx + 20, cy - 35)]
        draw.polygon(pts, fill=(254, 243, 199), outline=(180, 83, 9), width=3)
        draw.ellipse([cx + 10, cy - 45, cx + 25, cy - 30], fill=(225, 29, 72))
        draw.line([(cx - 45, cy + 10), (cx + 42, cy + 18)], fill=(120, 53, 15), width=5)

    elif icon_type == "sandwich":
        # Triangle sandwich / Panini
        pts = [(cx - 50, cy + 30), (cx + 50, cy + 30), (cx, cy - 40)]
        draw.polygon(pts, fill=(245, 158, 11), outline=(180, 83, 9), width=3)
        draw.line([(cx - 35, cy + 15), (cx + 35, cy + 15)], fill=(34, 197, 94), width=6)
        draw.line([(cx - 20, cy), (cx + 20, cy)], fill=(234, 179, 8), width=5)

    elif icon_type == "juice":
        # Fresh juice glass with orange slice
        pts = [(cx - 32, cy - 25), (cx + 32, cy - 25), (cx + 22, cy + 45), (cx - 22, cy + 45)]
        draw.polygon(pts, fill=(249, 115, 22), outline=(255, 255, 255, 220), width=3)
        draw.chord([cx + 15, cy - 45, cx + 45, cy - 15], 0, 180, fill=(234, 88, 12), outline=(255, 255, 255), width=2)
        draw.line([cx - 5, cy - 65, cx - 12, cy + 35], fill=(59, 130, 246), width=5)

    elif icon_type == "avatar":
        # Avatar head & shoulders
        draw.ellipse([cx - 42, cy - 58, cx + 42, cy + 22], fill=(255, 255, 255))
        draw.chord([cx - 75, cy + 36, cx + 75, cy + 150], 180, 360, fill=(255, 255, 255))
        if label:
            draw.rounded_rectangle([cx - 42, cy + 25, cx + 42, cy + 55], radius=8, fill=(15, 23, 42, 230), outline=(255, 255, 255, 120), width=2)

    else:
        # Default Illy coffee cup
        draw.ellipse([cx - 48, cy + 10, cx + 48, cy + 42], fill=(200, 16, 46))
        draw.rectangle([cx - 48, cy - 15, cx + 48, cy + 25], fill=(200, 16, 46))
        draw.arc([cx + 32, cy - 10, cx + 65, cy + 22], 270, 90, fill=(200, 16, 46), width=8)
        draw.ellipse([cx - 40, cy - 22, cx + 40, cy - 7], fill=(255, 255, 255))
        draw.ellipse([cx - 34, cy - 20, cx + 34, cy - 9], fill=(69, 26, 3))
        draw.ellipse([cx - 68, cy + 34, cx + 68, cy + 50], fill=(200, 16, 46))

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    output.save(filename, "PNG")
    print(f"Generated PNG: {filename}")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "app", "static")
    avatars_dir = os.path.join(static_dir, "avatars")
    icons_dir = os.path.join(static_dir, "images", "icons")
    images_dir = os.path.join(static_dir, "images")

    os.makedirs(avatars_dir, exist_ok=True)
    os.makedirs(icons_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    # 1. Generate Avatars
    avatars = [
        ("dev.png", (15, 23, 42), (30, 41, 59), "avatar", "DEV"),
        ("admin_1.png", (127, 29, 29), (185, 28, 28), "avatar", "ADM"),
        ("admin_2.png", (30, 58, 138), (29, 78, 216), "avatar", "MGR"),
        ("barista_1.png", (180, 83, 9), (217, 119, 6), "avatar", "BAR1"),
        ("barista_2.png", (190, 18, 60), (225, 29, 72), "avatar", "BAR2"),
        ("barista_3.png", (15, 118, 110), (13, 148, 136), "avatar", "BAR3"),
    ]
    for fn, c1, c2, itype, lbl in avatars:
        path = os.path.join(avatars_dir, fn)
        draw_squircle_icon(path, c1, c2, itype, lbl)

    # 2. Generate Drink/Food Preset Icons
    presets = [
        ("espresso.png", (120, 53, 15), (180, 83, 9), "espresso"),
        ("cappuccino.png", (146, 64, 14), (202, 138, 4), "cappuccino"),
        ("latte.png", (113, 63, 18), (161, 98, 7), "latte"),
        ("americano.png", (30, 41, 59), (51, 65, 85), "americano"),
        ("cold_brew.png", (15, 23, 42), (69, 26, 3), "cold_brew"),
        ("frappe.png", (133, 77, 14), (202, 138, 4), "frappe"),
        ("tea.png", (22, 101, 52), (34, 197, 94), "tea"),
        ("croissant.png", (180, 83, 9), (245, 158, 11), "croissant"),
        ("dessert.png", (159, 18, 57), (225, 29, 72), "dessert"),
        ("sandwich.png", (161, 98, 7), (217, 119, 6), "sandwich"),
        ("juice.png", (194, 65, 12), (249, 115, 22), "juice"),
        ("default.png", (153, 27, 27), (225, 29, 72), "default"),
    ]
    for fn, c1, c2, itype in presets:
        path = os.path.join(icons_dir, fn)
        draw_squircle_icon(path, c1, c2, itype)

    # Coffee default
    draw_squircle_icon(os.path.join(images_dir, "coffee_default.png"), (153, 27, 27), (225, 29, 72), "default")

if __name__ == "__main__":
    main()
