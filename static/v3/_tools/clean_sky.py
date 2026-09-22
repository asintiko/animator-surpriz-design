from PIL import Image

src = '/Users/kulacidmyt/Documents/animator/static/v3/assets/bg-sky-raw.png'
dst = '/Users/kulacidmyt/Documents/animator/static/v3/assets/bg-sky.jpg'

img = Image.open(src).convert('RGB')
w, h = img.size
# watermark occupies bottom-left ~100px; bottom strip is an empty smooth gradient,
# so crop 100px off the bottom and stretch back - imperceptible on a gradient
img2 = img.crop((0, 0, w, h - 100)).resize((w, h), Image.LANCZOS)
img2.save(dst, quality=92)
print('saved', dst, img2.size)
