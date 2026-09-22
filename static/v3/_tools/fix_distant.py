from PIL import Image

path = '/Users/kulacidmyt/Documents/animator/static/v3/assets/distant-park.png'
img = Image.open(path).convert('RGBA')
w, h = img.size
px = img.load()

cleared = 0
# 1) unwanted sun circles, upper-left (surrounding sky is transparent)
for y in range(90, 390):
    for x in range(70, 440):
        r, g, b, a = px[x, y]
        if a > 0:
            px[x, y] = (r, g, b, 0)
            cleared += 1

# 2) watermark region bottom-left (sits in a transparent pocket)
for y in range(945, 1024):
    for x in range(0, 175):
        r, g, b, a = px[x, y]
        if a > 0:
            px[x, y] = (r, g, b, 0)
            cleared += 1

img.save(path)
print('cleared px:', cleared)
