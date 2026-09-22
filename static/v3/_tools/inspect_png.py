import sys
from PIL import Image

path = sys.argv[1]
img = Image.open(path).convert('RGBA')
w, h = img.size
print('size', w, h)
px = img.load()

# check corners alpha
for name, (x, y) in {'TL': (2, 2), 'TR': (w-3, 2), 'BL': (2, h-3), 'BR': (w-3, h-3), 'center-top': (w//2, 5)}.items():
    print(name, px[x, y])

# scan for near-white / near-black opaque pixels (halo check)
import collections
halo_w = halo_b = 0
opaque = 0
for y in range(0, h, 4):
    for x in range(0, w, 4):
        r, g, b, a = px[x, y]
        if a > 200:
            opaque += 1
            if r > 240 and g > 240 and b > 240:
                halo_w += 1
            if r < 15 and g < 15 and b < 15:
                halo_b += 1
print('opaque samples', opaque, 'near-white', halo_w, 'near-black', halo_b)
