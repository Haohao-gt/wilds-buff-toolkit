from PIL import Image, ImageDraw
import os

S = 2048
img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 背景
grad = Image.new('RGB', (1, S))
for y in range(S):
    t = y / (S - 1)
    grad.putpixel((0, y), (int(0x5A + (0x1B - 0x5A) * t),
                           int(0xC2 + (0x5E - 0xC2) * t),
                           int(0xF6 + (0xB8 - 0xF6) * t)))
grad = grad.resize((S, S))
mask = Image.new('L', (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=380, fill=255)
img.paste(grad, (0, 0), mask)
d.rounded_rectangle([18, 18, S - 18, S - 18], radius=365, outline=(255, 255, 255, 235), width=26)
d.rounded_rectangle([44, 44, S - 44, S - 44], radius=345, outline=(11, 46, 82, 210), width=14)

INK = (59, 36, 18, 255)
CREAM = (255, 246, 220, 255)
GOLD = (255, 201, 60, 255)
RED = (229, 72, 46, 255)

# 卡片层（带犄角）
card = Image.new('RGBA', (1500, 1800), (0, 0, 0, 0))
cd = ImageDraw.Draw(card)

# 犄角（在卡片后面，向上外张）
left_horn = [(420, 470), (150, 120), (300, 430), (420, 560)]
right_horn = [(1080, 470), (1350, 120), (1200, 430), (1080, 560)]
for poly in (left_horn, right_horn):
    cd.polygon(poly, fill=CREAM, outline=INK)
    cd.line(poly + [poly[0]], fill=INK, width=26)

# 卡牌
cd.rounded_rectangle([280, 250, 1220, 1560], radius=110, fill=CREAM, outline=INK, width=46)
cd.rounded_rectangle([330, 300, 1170, 1510], radius=86, outline=GOLD, width=22)

# 闪电
bolt = [(760, 470), (560, 880), (720, 880), (620, 1290), (960, 820), (790, 820), (900, 470)]
cd.polygon(bolt, fill=RED, outline=INK)
cd.line(bolt + [bolt[0]], fill=INK, width=26)

card = card.rotate(-10, resample=Image.BICUBIC, expand=True)
cw, ch = card.size
img.alpha_composite(card, ((S - cw) // 2, (S - ch) // 2 - 10))

img = img.resize((512, 512), Image.LANCZOS)
os.makedirs('assets', exist_ok=True)
img.save('assets/logo.png')
img.save('assets/app.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

# 预览 32px
img.resize((32, 32), Image.LANCZOS).resize((256, 256), Image.NEAREST).save('work/logo32_preview.png')
print('ok')
