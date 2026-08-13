#!/usr/bin/env python3
"""Generate cover.png (1200x630) for og:image / social sharing."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
BG = '#f5f0eb'
CARD = '#ffffff'
TEXT = '#2c2416'
ACCENT = '#8b4513'
MUTED = '#8b7355'

img = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(img)

# Side accent bar
d.rectangle([0, 0, 14, H], fill=ACCENT)

# Decorative circles (subtle, top-right)
d.ellipse([900, -160, 1320, 260], fill='#ece1d2')
d.ellipse([980, 420, 1250, 690], fill='#ece1d2')

# Card plate
card = [80, 110, 1120, 520]
d.rounded_rectangle(card, radius=24, fill=CARD, outline='#e0d5c1', width=2)

font_dir = 'C:/Windows/Fonts/'
def font(size, name='msyh.ttc'):
    path = os.path.join(font_dir, name)
    if not os.path.exists(path):
        path = os.path.join(font_dir, 'simhei.ttf')
    return ImageFont.truetype(path, size)

# Museum emoji is unreliable in PIL fonts — draw a simple pillar icon instead
d.rectangle([120, 200, 260, 420], fill=ACCENT)          # building body
d.rectangle([105, 185, 275, 215], fill=ACCENT)          # pediment
d.rectangle([178, 250, 202, 420], fill=BG)              # door
d.text((120, 300), '文', font=font(44, 'simfang.ttf' if os.path.exists(os.path.join(font_dir, 'simfang.ttf')) else 'msyh.ttc'), fill=ACCENT)

title = '每日文博资讯'
sub = '文博 · 考古 · 博物馆 · 每日推送'
foot = 'zhangheng666.top ｜ 每日早 8:13 自动更新'

d.text((310, 190), title, font=font(96), fill=TEXT)
d.text((315, 340), sub, font=font(44), fill=MUTED)
d.text((315, 430), foot, font=font(28), fill='#b3a68f')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cover.png')
img.save(out, 'PNG', optimize=True)
print('Saved:', out)
