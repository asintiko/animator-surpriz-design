"""Slice a tall screenshot into readable chunks."""
import sys
from PIL import Image

def main():
    src, prefix = sys.argv[1], sys.argv[2]
    chunk_h = int(sys.argv[3]) if len(sys.argv) > 3 else 1500
    target_w = int(sys.argv[4]) if len(sys.argv) > 4 else 1100
    img = Image.open(src)
    w, h = img.size
    n = (h + chunk_h - 1) // chunk_h
    paths = []
    for i in range(n):
        box = (0, i * chunk_h, w, min(h, (i + 1) * chunk_h))
        part = img.crop(box)
        if part.width > target_w:
            ratio = target_w / part.width
            part = part.resize((target_w, int(part.height * ratio)), Image.LANCZOS)
        out = f"{prefix}-{i:02d}.jpg"
        part.convert("RGB").save(out, quality=72)
        paths.append(out)
    print("\n".join(paths))

if __name__ == "__main__":
    main()
