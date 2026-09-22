from PIL import Image

path = '/Users/kulacidmyt/Documents/animator/static/v3/assets/distant-park.png'
img = Image.open(path).convert('RGBA')
w, h = img.size
px = img.load()

# 1) stats of watermark region (bottom-left)
import statistics
alphas = [px[x, y][3] for y in range(955, 1024) for x in range(0, 170)]
print('wm region alpha: min', min(alphas), 'max', max(alphas), 'mean', round(statistics.mean(alphas), 1))
# what does the strip look like just right of the watermark?
alphas2 = [px[x, y][3] for y in range(955, 1024) for x in range(180, 350)]
print('ref region alpha: min', min(alphas2), 'max', max(alphas2), 'mean', round(statistics.mean(alphas2), 1))
