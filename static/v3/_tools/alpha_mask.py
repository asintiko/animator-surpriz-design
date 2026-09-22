import sys
from PIL import Image

src = sys.argv[1]
dst = sys.argv[2]
img = Image.open(src).convert('RGBA')
a = img.getchannel('A')
a.save(dst)
print('mask saved', dst)
