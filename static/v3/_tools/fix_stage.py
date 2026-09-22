from PIL import Image

path = '/Users/kulacidmyt/Documents/animator/static/v3/assets/mid-stage.png'
img = Image.open(path).convert('RGBA')
w, h = img.size
px = img.load()

# sample backdrop colors at a few known backdrop points
for p in [(60, 200), (300, 60), (1200, 60), (1460, 200), (760, 120)]:
    print('sample', p, px[p[0], p[1]])

keyed = 0
# 1) key out the pale-yellow backdrop (uniform fill behind arch/curtains)
for y in range(h):
    for x in range(w):
        r, g, b, a = px[x, y]
        if a == 0:
            continue
        if abs(r - 255) <= 10 and abs(g - 234) <= 14 and abs(b - 163) <= 22:
            px[x, y] = (r, g, b, 0)
            keyed += 1
print('keyed backdrop px:', keyed)

# 2) watermark bottom-left (below curtain hem, transparent pocket)
n = 0
for y in range(935, 1024):
    for x in range(0, 175):
        r, g, b, a = px[x, y]
        if a > 0:
            px[x, y] = (r, g, b, 0)
            n += 1
print('wm px:', n)

# 3) stray navy floor fragments at left/right edges
for rect in [(0, 770, 70, 860), (1470, 920, 1536, 1010)]:
    x0, y0, x1, y1 = rect
    n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (r, g, b, 0)
                n += 1
    print('fragment rect', rect, 'cleared', n)

img.save(path)
print('saved')
