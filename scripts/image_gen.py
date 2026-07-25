"""카드뉴스 렌더러 (PIL) — 프리미엄 다크/글래스 캐러셀.

한 카테고리당 4장 생성: 표지(오늘의 뉴스 3건 요약) + 상세 3장.
시각 요소(그라데이션·글로우·글래스·아이콘)는 전부 코드/에셋으로 고정,
매일 텍스트만 교체되므로 몇 년이 지나도 동일하게 재현된다 (AI 이미지 생성 없음).

폰트는 OS 자동감지: 로컬 Windows=맑은고딕, GitHub Actions(리눅스)=Noto CJK.
숫자=Poppins, 아이콘=Font Awesome.
"""
import os
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import (CATEGORY_COLORS, CATEGORY_HANDLE, CATEGORY_ICONS,
                    ASSETS_DIR, KR_BOLD, KR_REG, KR_INDEX, FA_PATH, NUM_PATH)

W, H = 1080, 1350

# Font Awesome 4.7 글리프
FA_G = {"bullhorn": "", "comment": "", "rocket": "",
        "chart": "", "doc": "", "arrow": "", "chev": "",
        "money": "", "home": "", "heart": "", "gamepad": "",
        "car": "", "plane": "", "child": "", "cutlery": "",
        "flask": "", "leaf": "", "graduation": "", "briefcase": "",
        "gavel": "", "futbol": "", "film": "", "paw": "",
        "shopping": "", "magic": "", "lightbulb": "", "star": ""}


def _kf(bold, size):
    return ImageFont.truetype(KR_BOLD if bold else KR_REG, size, index=KR_INDEX)

def _nf(size):
    return ImageFont.truetype(NUM_PATH, size)

def _fa(size):
    return ImageFont.truetype(FA_PATH, size)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i]-a[i])*t) for i in range(3))

def _tracked(d, text, font, x, y, fill, tr=0.0, anchor=None):
    if anchor:
        d.text((x, y), text, font=font, fill=fill, anchor=anchor); return x
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill); x += d.textlength(ch, font=font)+tr
    return x

def _tw(d, text, font, tr=0.0):
    return sum(d.textlength(c, font=font)+tr for c in text) - (tr if text else 0)

def _wrap(d, text, font, maxw, tr=0.0):
    lines, cur = [], ""
    for ch in text:
        if _tw(d, cur+ch, font, tr) > maxw and cur:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur: lines.append(cur)
    return lines

def _fit(d, text, font, maxw, tr=0.0):
    """maxw를 넘으면 말줄임표(…)로 자른다."""
    if _tw(d, text, font, tr) <= maxw:
        return text
    while text and _tw(d, text+"…", font, tr) > maxw:
        text = text[:-1]
    return text+"…"

def _split_headline(hl, sub):
    """헤드라인 끝이 subtitle과 같으면 두 줄로 분리 (표지 카드 강조용)."""
    if sub and hl.endswith(sub) and len(hl) > len(sub):
        return hl[:-len(sub)].rstrip(), sub
    return hl, (sub or "")

def _bg(top, mid, bot):
    y = np.linspace(0, 1, H)[:, None]
    def ch(i):
        return np.where(y < .5, top[i]+(mid[i]-top[i])*(y/.5),
                        mid[i]+(bot[i]-mid[i])*((y-.5)/.5))
    arr = np.dstack([ch(0), ch(1), ch(2)]).astype(np.uint8)
    return Image.fromarray(np.broadcast_to(arr, (H, W, 3)).copy(), "RGB")

def _glow(img, cx, cy, r, color, strength):
    yy, xx = np.mgrid[0:H, 0:W]
    a = np.clip(1 - np.sqrt((xx-cx)**2+(yy-cy)**2)/r, 0, 1)**2 * strength
    base = np.asarray(img).astype(np.float32)
    for i in range(3):
        base[..., i] += (color[i]-base[..., i]) * a
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")

def _grad_text(target, text, font, x, y, c1, c2, tr=0.0):
    mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask); cx = x
    for ch in text:
        md.text((cx, y), ch, font=font, fill=255); cx += md.textlength(ch, font=font)+tr
    bb = mask.getbbox()
    if not bb: return
    ga = np.zeros((H, W, 3), np.uint8)
    for yy in range(bb[1], bb[3]):
        ga[yy, :] = _lerp(c1, c2, (yy-bb[1])/max(1, bb[3]-bb[1]))
    target.paste(Image.fromarray(ga, "RGB"), (0, 0), mask)

def _glass(img, box, radius=28, alpha=60):
    x0, y0, x1, y1 = box
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    d.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, alpha),
                        outline=(255, 255, 255, 110), width=2)
    d.rounded_rectangle([x0+2, y0+2, x1-2, y0+3], radius=radius, fill=(255, 255, 255, 70))
    img.alpha_composite(ov)

def _grad_round(img, box, radius, c1, c2):
    x0, y0, x1, y1 = [int(round(v)) for v in box]; w, h = x1-x0, y1-y0
    ga = np.zeros((h, w, 3), np.uint8)
    for yy in range(h): ga[yy, :] = _lerp(c1, c2, yy/max(1, h))
    tile = Image.fromarray(ga, "RGB").convert("RGBA")
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w-1, h-1], radius=radius, fill=255)
    img.paste(tile, (x0, y0), m)

def _circle(img, cx, cy, r, color):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
    img.alpha_composite(ov)

def _fa_icon(img, glyph, cx, cy, size, color):
    m = Image.new("L", (W, H), 0); d = ImageDraw.Draw(m); f = _fa(size)
    bb = d.textbbox((0, 0), glyph, font=f)
    d.text((cx-(bb[2]-bb[0])/2-bb[0], cy-(bb[3]-bb[1])/2-bb[1]), glyph, font=f, fill=255)
    col = Image.new("RGBA", (W, H), color+(255,))
    img.paste(col, (0, 0), m)


def _palette(color_hex):
    c = color_hex.lstrip("#"); acc = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
    return acc, (16, 38, 80), (11, 26, 60), (7, 15, 36)


def _hero(img, category_id, acc):
    """카테고리 3D PNG가 있으면 히어로로, 없으면 Font Awesome 폴백."""
    _circle(img, 905, 300, 150, (30, 55, 120, 90))
    path = os.path.join(ASSETS_DIR, f"hero_{category_id}.png")
    if os.path.exists(path):
        hero = Image.open(path).convert("RGBA")
        tw = 340; th = int(hero.height*tw/hero.width)
        hero = hero.resize((tw, th), Image.LANCZOS)
        hx, hy = W-tw-14, 122
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a = hero.split()[3].point(lambda p: int(p*0.45))
        s = Image.new("RGBA", hero.size, (10, 20, 60, 255)); s.putalpha(a)
        sh.paste(s, (hx+14, hy+26), s); sh = sh.filter(ImageFilter.GaussianBlur(18))
        img.alpha_composite(sh); img.alpha_composite(hero, (hx, hy))
    else:
        _fa_icon(img, FA_G["bullhorn"], 905, 290, 190, (120, 160, 255))
        _fa_icon(img, FA_G["comment"], 930, 430, 86, (90, 130, 240))


def render_cover(category_id, cat_name, date_str, hook, headlines_subs, out_path):
    """표지. headlines_subs = [(headline, subtitle), ...] 최대 3건."""
    acc, T, Mid, B = _palette(CATEGORY_COLORS.get(category_id, "#3f7bff"))
    handle = CATEGORY_HANDLE.get(category_id, "@news")
    icons = CATEGORY_ICONS.get(category_id, ["doc", "rocket", "chart"])
    base = _glow(_glow(_bg(T, Mid, B), 900, 60, 720, (70, 120, 255), .55),
                 1080, -20, 520, (120, 90, 255), .30)
    img = base.convert("RGBA"); d = ImageDraw.Draw(img); M = 84

    d.text((M, 74), handle, font=_kf(True, 30), fill=(150, 178, 255))
    d.text((W-M, 90), date_str, font=_kf(False, 30), fill=(128, 150, 200), anchor="rm")

    def spark(cx, cy, r, col):
        k = .16
        d.polygon([(cx, cy-r), (cx+r*k, cy-r*k), (cx+r, cy), (cx+r*k, cy+r*k),
                   (cx, cy+r), (cx-r*k, cy+r*k), (cx-r, cy), (cx-r*k, cy-r*k)], fill=col)
    spark(770, 120, 26, (220, 232, 255)); spark(842, 186, 15, (200, 218, 255))

    _hero(img, category_id, acc)

    TF = _kf(True, 118); TR = -6
    _grad_text(img, "오늘의", TF, M, 150, (240, 245, 255), (150, 180, 255), TR)
    _grad_text(img, cat_name, TF, M, 278, (140, 175, 255), (70, 120, 255), TR)
    x2 = M + _tw(d, cat_name, TF, TR) + 34
    _tracked(d, "뉴스", TF, x2, 278, (255, 255, 255), TR)

    # 후킹 ("N가지 핵심"이 있으면 흰색+언더라인 강조)
    hy = 470; nb = (200, 214, 245); F = _kf(True, 38); Fe = _kf(True, 40)
    m = re.search(r"\d+가지\s*핵심", hook)
    if m:
        pre, seg, post = hook[:m.start()], m.group(), hook[m.end():]
        hx = _tracked(d, pre, F, M, hy, nb, -1.5)
        sx0 = hx; hx = _tracked(d, seg, Fe, hx, hy-1, (255, 255, 255), -1.0)
        d.rounded_rectangle([sx0, hy+50, hx-6, hy+56], radius=3, fill=(96, 150, 255))
        _tracked(d, post, F, hx+4, hy, nb, -1.5)
    else:
        _tracked(d, hook, F, M, hy, nb, -1.5)

    top = 556; ch = 188; gap = 22
    for i, (hl, sub) in enumerate(headlines_subs[:3]):
        y0 = top + i*(ch+gap)
        _glass(img, [M, y0, W-M, y0+ch], radius=30, alpha=60); d = ImageDraw.Draw(img)
        bx = M+34; by = y0+(ch-92)//2
        _grad_round(img, [bx, by, bx+92, by+92], 22, (67, 128, 255), (36, 80, 230))
        d = ImageDraw.Draw(img)
        d.text((bx+47, by+44), str(i+1), font=_nf(56), fill=(255, 255, 255), anchor="mm")
        tx = bx+126; txmax = (W-M-116) - tx   # 우측 아이콘 영역 확보
        l1, l2 = _split_headline(hl, sub)
        CF = _kf(True, 38)
        if l2:
            _tracked(d, _fit(d, l1, CF, txmax, -1.2), CF, tx, y0+30, (255, 255, 255), -1.2)
            _tracked(d, _fit(d, l2, CF, txmax, -1.2), CF, tx, y0+82, (130, 165, 255), -1.2)
        else:
            lines = _wrap(d, l1, CF, txmax, -1.2)[:2]
            oy = y0 + (ch - len(lines)*54)//2
            for ln in lines:
                _tracked(d, ln, CF, tx, oy, (255, 255, 255), -1.2); oy += 54
        icx = W-M-80; icy = y0+ch//2
        _circle(img, icx, icy, 56, (40, 70, 140, 110))
        _fa_icon(img, FA_G.get(icons[i % len(icons)], ""), icx, icy, 60, (150, 185, 255))

    cy0 = H-58-100
    _grad_round(img, [M, cy0, W-M, cy0+100], 50, (47, 91, 255), (74, 134, 255))
    d = ImageDraw.Draw(img); cm = cy0+50
    d.ellipse([M+20, cm-32, M+20+64, cm+32], fill=(255, 255, 255))
    _fa_icon(img, FA_G["arrow"], M+20+32, cm, 36, (47, 91, 255))
    d.text((M+112, cm), "넘겨서 자세히 보기", font=_kf(True, 38), fill=(255, 255, 255), anchor="lm")
    _fa_icon(img, FA_G["chev"], W-M-56, cm, 40, (210, 228, 255))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path


def render_cover_photo(category_id, cat_name, date_str, hook, headlines_subs, photo, out_path):
    """사진 표지 — 그날 대표 뉴스 사진을 전면 배경으로, 하단에 제목·후킹·헤드라인 3건.

    매일 표지 이미지가 달라져 피드에서 시선을 끈다. 사진은 브랜드 네이비로 컬러그레이드.
    좋은 사진이 없을 땐 render_cover(확성기 표지)로 폴백한다(generate_carousel에서 분기).
    """
    acc, T, Mid, B = _palette(CATEGORY_COLORS.get(category_id, "#3f7bff"))
    handle = CATEGORY_HANDLE.get(category_id, "@news")
    ph = _grade_photo(_cover_crop(Image.open(photo).convert("RGB"), W, H))
    # 스크림: 상단 살짝 + 하단 강하게(네이비)로 하단 텍스트 가독 확보
    arr = np.asarray(ph).astype(np.float32)
    yy = np.linspace(0, 1, H)[:, None, None]
    navy = np.array([8, 13, 28], np.float32)
    a_top = np.clip((0.20 - yy) / 0.20, 0, 1) * 0.45
    a_bot = np.clip((yy - 0.30) / 0.34, 0, 1) * 0.90   # 하단 텍스트 영역을 확실히 어둡게
    a = np.clip(a_top + a_bot, 0, 0.97)
    arr = arr * (1 - a) + navy * a
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    img = _glow(img, 150, 1200, 720, acc, 0.15).convert("RGBA")   # 하단 accent 글로우
    d = ImageDraw.Draw(img); M = 84

    d.text((M, 74), handle, font=_kf(True, 30), fill=(226, 236, 255))
    d.text((W-M, 90), date_str, font=_kf(False, 30), fill=(212, 224, 250), anchor="rm")

    TF = _kf(True, 88); TR = -4
    _grad_text(img, "오늘의", TF, M, 612, (240, 245, 255), (150, 180, 255), TR)
    _grad_text(img, cat_name, TF, M, 712, (150, 180, 255), (70, 120, 255), TR)
    d = ImageDraw.Draw(img)
    x2 = M + _tw(d, cat_name, TF, TR) + 30
    _tracked(d, "뉴스", TF, x2, 712, (255, 255, 255), TR)

    hy = 836; nb = (212, 224, 250); F = _kf(True, 36); Fe = _kf(True, 38)
    m = re.search(r"\d+가지\s*핵심", hook)
    if m:
        pre, seg, post = hook[:m.start()], m.group(), hook[m.end():]
        hx = _tracked(d, pre, F, M, hy, nb, -1.5)
        sx0 = hx; hx = _tracked(d, seg, Fe, hx, hy-1, (255, 255, 255), -1.0)
        d.rounded_rectangle([sx0, hy+48, hx-6, hy+54], radius=3, fill=(120, 165, 255))
        _tracked(d, post, F, hx+4, hy, nb, -1.5)
    else:
        _tracked(d, hook, F, M, hy, nb, -1.5)

    ly = 910; CF = _kf(True, 38)
    for i, (hl, sub) in enumerate(headlines_subs[:3]):
        d.text((M, ly-4), str(i+1), font=_nf(38), fill=(132, 172, 255))
        txt = _fit(d, hl, CF, (W-M) - (M+52), -0.5)
        _tracked(d, txt, CF, M+52, ly, (240, 244, 255), -0.5)
        ly += 72

    cy0 = H-58-100
    _grad_round(img, [M, cy0, W-M, cy0+100], 50, (47, 91, 255), (74, 134, 255))
    d = ImageDraw.Draw(img); cm = cy0+50
    d.ellipse([M+20, cm-32, M+20+64, cm+32], fill=(255, 255, 255))
    _fa_icon(img, FA_G["arrow"], M+20+32, cm, 36, (47, 91, 255))
    d.text((M+112, cm), "넘겨서 자세히 보기", font=_kf(True, 38), fill=(255, 255, 255), anchor="lm")
    _fa_icon(img, FA_G["chev"], W-M-56, cm, 40, (210, 228, 255))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path


def render_detail(category_id, cat_name, date_str, idx, total,
                  headline, summary, comment, source, out_path):
    acc, T, Mid, B = _palette(CATEGORY_COLORS.get(category_id, "#3f7bff"))
    handle = CATEGORY_HANDLE.get(category_id, "@news")
    icons = CATEGORY_ICONS.get(category_id, ["doc", "rocket", "chart"])
    icon = icons[(idx-1) % len(icons)]
    ACC = (96, 150, 255)
    base = _glow(_bg(T, Mid, B), 180, 120, 640, (70, 120, 255), .42)
    img = base.convert("RGBA"); d = ImageDraw.Draw(img); M = 84

    pill = f"#{cat_name}"; pw = _tw(d, pill, _kf(True, 34))
    _grad_round(img, [M, 84, M+pw+56, 150], 20, (67, 128, 255), (36, 80, 230)); d = ImageDraw.Draw(img)
    d.text((M+28, 117), pill, font=_kf(True, 34), fill=(255, 255, 255), anchor="lm")
    d.text((W-M, 117), date_str, font=_kf(False, 30), fill=(140, 160, 205), anchor="rm")
    d.text((M, 214), f"NEWS  {idx} / {total}", font=_nf(30), fill=ACC)

    y = 270
    for ln in _wrap(d, headline, _kf(True, 72), W-2*M, -3):
        _tracked(d, ln, _kf(True, 72), M, y, (255, 255, 255), -3); y += int(72*1.2)
    y += 8; d.rounded_rectangle([M, y, M+130, y+9], radius=4, fill=ACC); y += 64

    for s in summary:
        my = y+18; d.ellipse([M, my, M+20, my+20], fill=ACC); tx = M+50
        for ln in _wrap(d, s, _kf(False, 44), W-tx-M, -1):
            _tracked(d, ln, _kf(False, 44), tx, y, (216, 226, 246), -1); y += int(44*1.34)
        y += 26

    cb0 = H-430
    _glass(img, [M, cb0, W-M, cb0+210], radius=26, alpha=52); d = ImageDraw.Draw(img)
    d.rounded_rectangle([M, cb0, M+12, cb0+210], radius=6, fill=ACC)
    _circle(img, W-M-70, cb0+70, 52, (40, 70, 140, 120))
    _fa_icon(img, FA_G.get(icon, ""), W-M-70, cb0+66, 58, (150, 185, 255)); d = ImageDraw.Draw(img)
    d.text((M+44, cb0+42), "이 소식이 왜 중요한가", font=_kf(True, 28), fill=ACC)
    yy = cb0+90
    for ln in _wrap(d, comment, _kf(True, 40), W-2*M-200, -1):
        _tracked(d, ln, _kf(True, 40), M+44, yy, (245, 248, 255), -1); yy += 52

    if source:
        d.text((M, H-150), f"원문: {source}", font=_kf(False, 26), fill=(120, 140, 180))
    d.line([(M, H-104), (W-M, H-104)], fill=(70, 95, 150), width=2)
    d.text((M, H-58), handle, font=_kf(True, 34), fill=(150, 178, 255), anchor="lm")
    tail = "자세한 내용은 다음 장" if idx < total else "팔로우하고 매일 받아보기"
    d.text((W-M, H-58), tail, font=_kf(False, 28), fill=(120, 140, 180), anchor="rm")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path


# ── 설명형 상세 (뉴스 1건 = 2페이지) ────────────────────────────────
_DBG_T, _DBG_M, _DBG_B = (18, 32, 58), (11, 21, 42), (6, 12, 26)  # 차분한 딥네이비
_DBODY = (234, 240, 250)   # 본문 near-white
_DLH = 62

def _lighten(rgb, f):
    return tuple(int(c + (255-c)*f) for c in rgb)

def _wrap_words(d, text, font, maxw):
    """자연 자간(폰트 그대로) 어절 단위 줄바꿈."""
    out = []
    for para in str(text).split("\n"):
        cur = ""
        for w in para.split(" "):
            test = (cur + " " + w).strip()
            if d.textlength(test, font=font) > maxw and cur:
                out.append(cur); cur = w
            else:
                cur = test
            while d.textlength(cur, font=font) > maxw:
                cut = cur
                while d.textlength(cut, font=font) > maxw and len(cut) > 1:
                    cut = cut[:-1]
                out.append(cut); cur = cur[len(cut):]
        out.append(cur)
    return out

def _wrap_balanced(d, text, font, maxw):
    """줄 수는 유지하되 각 줄 길이를 고르게 맞춰 뚝뚝 끊기는 느낌을 줄인다."""
    lines = _wrap_words(d, text, font, maxw)
    n = len(lines)
    if n <= 1:
        return lines
    lo, hi, best = 1, int(maxw), int(maxw)
    while lo <= hi:
        mid = (lo + hi) // 2
        if len(_wrap_words(d, text, font, mid)) <= n:
            best = mid; hi = mid - 1
        else:
            lo = mid + 1
    return _wrap_words(d, text, font, best)

def _para(d, text, font, x, y, maxw, fill, lh=_DLH):
    for ln in _wrap_balanced(d, text, font, maxw):
        d.text((x, y), ln, font=font, fill=fill); y += lh
    return y

def _para_h(d, text, font, maxw, lh=_DLH):
    return len(_wrap_balanced(d, text, font, maxw)) * lh

def _dots(d, x_right, cy, n, cur, acc):
    r = 6; gap = 24
    for i in range(n):
        cx = x_right - (n - 1 - i) * gap
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=acc if i == cur else (66, 86, 126))

def _eyebrow(img, d, M, acc, cat_name, idx, page, npages):
    d.ellipse([M, 90, M+15, 105], fill=acc)
    d.text((M+30, 82), f"{cat_name}   ·   NEWS {idx}", font=_kf(True, 27), fill=(150, 172, 212))
    _dots(d, W-M, 98, npages, page-1, acc)

def _section(d, M, label, y, acc):
    """섹션 라벨 — 얇은 틱 + 톤 낮춘 라벨(살짝 자간)로 템플릿 느낌을 줄이고 부드럽게."""
    d.rounded_rectangle([M, y+5, M+6, y+31], radius=3, fill=acc)
    _tracked(d, label, _kf(True, 30), M+22, y+1, _lighten(acc, 0.32), 0.8)
    return y + 60

_HL_RE = re.compile(r"[0-9][0-9,\.]*\s*(?:억|만|천|조|원|달러|%|퍼센트|명|배|건|개|가지|톤|kg|위|차|년|월|일)")

def _draw_hl(d, line, font, x, y, base, acc):
    """본문 한 줄에서 수치 토큰만 강조색으로 그린다 (에디토리얼 하이라이트)."""
    i = 0
    for m in _HL_RE.finditer(line):
        pre = line[i:m.start()]
        if pre:
            d.text((x, y), pre, font=font, fill=base); x += d.textlength(pre, font=font)
        seg = m.group()
        d.text((x, y), seg, font=font, fill=acc); x += d.textlength(seg, font=font)
        i = m.end()
    if i < len(line):
        d.text((x, y), line[i:], font=font, fill=base)

def _para_hl(d, text, font, x, y, maxw, base, acc, lh=_DLH):
    for ln in _wrap_balanced(d, text, font, maxw):
        _draw_hl(d, ln, font, x, y, base, acc); y += lh
    return y

def _dfoot(d, M, handle, tail):
    d.line([(M, H-104), (W-M, H-104)], fill=(58, 78, 118), width=2)
    d.text((M, H-58), handle, font=_kf(True, 32), fill=(150, 178, 255), anchor="lm")
    d.text((W-M, H-58), tail, font=_kf(False, 27), fill=(120, 140, 180), anchor="rm")

def _dbase(category_id, glow_x):
    cat_color = _palette(CATEGORY_COLORS.get(category_id, "#3f7bff"))[0]
    acc = _lighten(cat_color, 0.42)
    base = _glow(_bg(_DBG_T, _DBG_M, _DBG_B), glow_x, 30, 800, _lighten(cat_color, 0.05), .22)
    return cat_color, acc, base.convert("RGBA")

def _cover_crop(ph, tw, th):
    """이미지를 (tw,th)에 커버-핏(비율 유지, 중앙 크롭)."""
    sr = ph.width / max(1, ph.height); dr = tw / th
    if sr > dr:
        nh = th; nw = max(tw, int(round(th*sr)))
    else:
        nw = tw; nh = max(th, int(round(tw/sr)))
    ph = ph.resize((nw, nh), Image.LANCZOS)
    ox, oy = (nw-tw)//2, (nh-th)//2
    return ph.crop((ox, oy, ox+tw, oy+th))


def _grade_photo(ph):
    """자료사진을 브랜드 네이비 톤으로 은은하게 컬러그레이드해 무드 통일.

    원본이 로고든 스톡이든 현장사진이든, 부분 탈채도 + 루미넌스 기반 네이비 듀오톤을
    살짝 섞어 어떤 사진이 와도 같은 다크 네이비 결로 묶이게 한다.
    """
    arr = np.asarray(ph.convert("RGB")).astype(np.float32)
    gray = arr @ np.array([0.299, 0.587, 0.114], np.float32)
    arr = arr * 0.68 + gray[..., None] * 0.32           # 부분 탈채도
    lum = (gray / 255.0)[..., None]
    dark = np.array([10, 18, 34], np.float32)           # 섀도우 = 딥네이비
    light = np.array([150, 172, 205], np.float32)       # 하이라이트 = 옅은 블루그레이
    duo = dark * (1 - lum) + light * lum
    arr = arr * 0.78 + duo * 0.22                        # 듀오톤 22% 혼합
    arr *= 0.95                                          # 살짝 어둡게
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _is_photographic(im):
    """로고·아이콘·배너 등 '사진 아닌 이미지'를 걸러낸다(진짜 사진이면 True)."""
    try:
        im = im.convert("RGB")
    except Exception:
        return False
    w, h = im.size
    if w < 480 or h < 300:                 # 너무 작으면 저품질/아이콘
        return False
    r = w / h
    if r > 3.2 or r < 0.42:                # 극단 비율 = 배너/세로 아이콘
        return False
    a = np.asarray(im.resize((64, 64))).astype(np.float32)
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    frac_bright = float((a.min(axis=2) > 232).mean())   # 흰/밝은 단색 배경 비율
    sat = float((a.max(axis=2) - a.min(axis=2)).mean())  # 평균 채도
    if frac_bright > 0.42:                 # 흰 배경 로고류
        return False
    if lum.std() < 20:                     # 완전 밋밋한 단색(진짜 사진은 여유롭게 통과)
        return False
    if sat < 12 and lum.std() < 45:        # 채도 거의 없는 도표/텍스트/로고 이미지
        return False
    return True


def _photo_band(img, box, photo_path):
    """기사 대표 이미지를 라운드 밴드로 커버-핏 배치(브랜드 컬러그레이드 + 하단 스크림 + 태그)."""
    x0, y0, x1, y1 = [int(v) for v in box]; tw, th = x1-x0, y1-y0
    try:
        ph = Image.open(photo_path).convert("RGB")
    except Exception:
        return False
    ph = _grade_photo(_cover_crop(ph, tw, th))          # 컬러그레이드(무드 통일)
    # 하단 스크림(아래쪽으로 갈수록 카드 배경에 자연스럽게 녹아들게)
    arr = np.asarray(ph).astype(np.float32)
    yy = np.linspace(0, 1, th)[:, None, None]
    a = np.clip((yy - 0.5) / 0.5, 0, 1) ** 1.4 * 0.72
    arr = arr * (1 - a) + np.array([9, 14, 26], np.float32) * a
    ph = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tw-1, th-1], radius=22, fill=255)
    img.paste(ph, (x0, y0), mask)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle(box, radius=22, outline=(255, 255, 255, 48), width=2)
    img.alpha_composite(ov)
    # '관련 이미지' 태그(좌하단)
    d = ImageDraw.Draw(img); tf = _kf(True, 22); tag = "관련 이미지"
    tgw = int(d.textlength(tag, font=tf)); px, py = x0 + 22, y1 - 50
    _glass(img, [px, py, px + tgw + 34, py + 36], radius=18, alpha=64)
    ImageDraw.Draw(img).text((px + 17, py + 7), tag, font=_kf(True, 22), fill=(224, 232, 246))
    return True

def render_p1(category_id, cat_name, idx, npages, headline, lead, key_stat, photo, out_path):
    """1면 — 사진 + 헤드라인 + 리드(standfirst). 사진이 없으면 헤드라인+수치+리드로 지면을 채운다."""
    cat_color, acc, img = _dbase(category_id, 150)
    d = ImageDraw.Draw(img); M = 88; handle = CATEGORY_HANDLE.get(category_id, "@news")
    _eyebrow(img, d, M, acc, cat_name, idx, 1, npages)
    has_photo = bool(photo) and os.path.exists(photo) and _photo_band(img, [M, 150, W-M, 540], photo)
    d = ImageDraw.Draw(img)
    HF = _kf(True, 60); HLH = int(60*1.28); LF = _kf(False, 37); LLH = 60
    hl_lines = _wrap_words(d, headline, HF, W-2*M)
    lead_lines = _wrap_balanced(d, lead, LF, W-2*M) if lead else []
    show_stat = (not has_photo) and bool(key_stat) and bool(key_stat.get("value"))
    if has_photo:
        y = 602
    else:   # 사진 없음: 헤드라인+수치+리드 블록을 세로 중앙 정렬 → 여백 고르게
        block = len(hl_lines)*HLH + 71 + (140 if show_stat else 0) + (6 + len(lead_lines)*LLH if lead else 0)
        top, bot = 250, H-150
        y = top + max(0, ((bot-top)-block)//2)
    last_w = 0
    for ln in hl_lines:
        _draw_hl(d, ln, HF, M, y, (255, 255, 255), acc)
        last_w = int(d.textlength(ln, font=HF)); y += HLH
    y += 10; d.rounded_rectangle([M, y, M+last_w, y+7], radius=4, fill=acc); y += 54
    if show_stat:   # 사진 없을 때만 수치 히어로
        SF = _kf(True, 92); d.text((M, y), str(key_stat["value"]), font=SF, fill=acc)
        vw = int(d.textlength(str(key_stat["value"]), font=SF))
        d.text((M+vw+24, y+42), str(key_stat.get("label", "")), font=_kf(False, 30), fill=(162, 184, 220))
        y += 140
    if lead:
        y += 6
        _para_hl(d, lead, LF, M, y, W-2*M, _DBODY, acc, LLH)
    _dfoot(d, M, handle, "핵심 짚어보기 →")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path

def render_p2(category_id, cat_name, idx, npages, key_stat, facts, background, out_path):
    """2면 — 핵심 수치(패널) + 핵심 팩트 (+ 배경). 콘텐츠 블록을 세로 중앙에 둬 여백을 고르게."""
    cat_color, acc, img = _dbase(category_id, 930)
    d = ImageDraw.Draw(img); M = 88; handle = CATEGORY_HANDLE.get(category_id, "@news")
    _eyebrow(img, d, M, acc, cat_name, idx, 2, npages)
    FF = _kf(True, 37); FLH = 50; FGAP = 42; fx = M+54; fw = W-fx-M; NF = _nf(36)
    BF = _kf(False, 37); BLH = 58
    flist = facts[:3]
    fact_lines = [_wrap_balanced(d, f, FF, fw) for f in flist]
    bg_lines = _wrap_balanced(d, background, BF, W-2*M) if background else []
    has_stat = bool(key_stat) and bool(key_stat.get("value"))
    STAT_H = 158
    stat_h = (STAT_H + 54) if has_stat else 0
    facts_h = 60 + sum(len(fl)*FLH for fl in fact_lines) + FGAP*max(0, len(fact_lines)-1)
    bg_h = (52 + 60 + len(bg_lines)*BLH) if background else 0
    top, bot = 188, H-150
    y = top + max(0, ((bot-top)-(stat_h+facts_h+bg_h))//2)   # 전체 블록 세로 중앙
    if has_stat:   # 수치 패널 — 절제된 크기
        _glass(img, [M, y, W-M, y+STAT_H], radius=22, alpha=38)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([M, y, M+11, y+STAT_H], radius=6, fill=acc)
        d.text((M+50, y+34), str(key_stat["value"]), font=_kf(True, 62), fill=acc)
        d.text((M+52, y+110), str(key_stat.get("label", "")), font=_kf(False, 28), fill=(172, 192, 224))
        y += STAT_H + 54
    y = _section(d, M, "핵심 팩트", y, acc)
    for k, fl in enumerate(fact_lines, 1):
        d.text((M+2, y+20), str(k), font=NF, fill=acc, anchor="lm")   # 번호를 첫 줄 세로 중앙에 맞춤
        yy = y
        for ln in fl:
            _draw_hl(d, ln, FF, fx, yy, (238, 242, 252), acc); yy += FLH
        y = yy + FGAP
    if background:
        y = y - FGAP + 52
        y = _section(d, M, "배경", y, acc)
        _para_hl(d, background, BF, M, y, W-2*M, _DBODY, acc, BLH)
    _dfoot(d, M, handle, "쉽게 풀면 →" if background else "배경·의미 →")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path

def render_p3(category_id, cat_name, idx, npages, background, simple, why, is_last, out_path):
    """3면 — (배경 +) 쉽게 말하면 + 💡 관전 포인트. 상단부터 채워 '위 공백'을 없앤다."""
    cat_color, acc, img = _dbase(category_id, 150)
    d = ImageDraw.Draw(img); M = 88; handle = CATEGORY_HANDLE.get(category_id, "@news")
    _eyebrow(img, d, M, acc, cat_name, idx, 3, npages)
    SF = _kf(False, 37); SLH = 58; BF = _kf(False, 37); BLH = 58
    HW = _kf(True, 33); LHW = 44; txt_x = M+92; txt_maxw = (W-M) - txt_x
    wlines = _wrap_balanced(d, why, HW, txt_maxw)[:3]
    text_h = (len(wlines)-1)*LHW + 34          # 💡 문구 실제 높이
    box_h = text_h + 64                        # 상하 패딩 32씩
    slines = _wrap_balanced(d, simple, SF, W-2*M)
    if background:   # 배경 + 쉽게 말하면 + 💡 (상단 정렬, 위→아래로 자연스럽게 채움)
        y = 196
        y = _section(d, M, "배경", y, acc)
        y = _para_hl(d, background, BF, M, y, W-2*M, _DBODY, acc, BLH) + 48
        y = _section(d, M, "쉽게 말하면", y, acc)
        for ln in slines:
            _draw_hl(d, ln, SF, M, y, _DBODY, acc); y += SLH
        y += 60
    else:            # 쉽게 말하면 + 💡 만 → 그룹을 세로 중앙에 둬 여백을 위아래로 분산
        simple_h = 60 + len(slines)*SLH
        group = simple_h + 60 + box_h
        top, bot = 200, H-150
        y = top + max(0, ((bot - top) - group) // 2)
        y = _section(d, M, "쉽게 말하면", y, acc)
        for ln in slines:
            _draw_hl(d, ln, SF, M, y, _DBODY, acc); y += SLH
        y += 60
    by = min(y, H - 140 - box_h)               # 💡는 본문 바로 아래(넘치면 하단에 고정)
    _glass(img, [M, by, W-M, by+box_h], radius=24, alpha=52)
    _fa_icon(img, FA_G["lightbulb"], M+44, by+box_h//2, 42, acc)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([M, by, M+12, by+box_h], radius=6, fill=acc)
    ty = by + (box_h - text_h) // 2            # 문구를 박스 세로 중앙에
    for ln in wlines:
        d.text((txt_x, ty), ln, font=HW, fill=(245, 248, 255)); ty += LHW
    _dfoot(d, M, handle, "팔로우하고 매일 받아보기" if is_last else "다음 뉴스 →")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path


def generate_carousel(category_id, cat_name, date_str, hook, items, out_dir, prefix):
    """items = [{headline, subtitle, lead, facts, background, simple, why, source}] (최대 3).
    반환: [표지, 뉴스1-p1, 뉴스1-p2, 뉴스2-p1, ...] (표지 1 + 뉴스별 2장)."""
    paths = []
    cover = os.path.join(out_dir, f"{prefix}_0.jpg")
    heads = [(it["headline"], it.get("subtitle", "")) for it in items]
    # 표지: 좋은 자료사진이 있으면 사진 표지, 없으면 확성기 표지로 폴백
    cover_photo = next((it.get("photo", "") for it in items
                        if it.get("photo") and os.path.exists(it.get("photo", ""))), "")
    if cover_photo:
        render_cover_photo(category_id, cat_name, date_str, hook, heads, cover_photo, cover)
    else:
        render_cover(category_id, cat_name, date_str, hook, heads, cover)
    paths.append(cover)
    total = len(items)
    slide = 0
    for i, it in enumerate(items, 1):
        photo = it.get("photo", "")
        has_photo = bool(photo) and os.path.exists(photo)
        lead = it.get("lead", ""); ks = it.get("key_stat") or {}
        facts = it.get("facts", []); bg = it.get("background", "")
        simple = it.get("simple", ""); why = it.get("why", "")
        def _p():
            nonlocal slide
            slide += 1
            return os.path.join(out_dir, f"{prefix}_{slide}.jpg")
        has_stat = bool(ks.get("value"))
        # P1: 사진 있으면 사진+헤드라인+리드, 없으면 헤드라인+수치+리드(render_p1이 내부 판단)
        p = _p(); render_p1(category_id, cat_name, i, 3, it["headline"], lead, ks, photo, p); paths.append(p)
        # 배경 배치: 사진+수치가 다 있는 흔한 경우엔 3면(상단 채움), 그 외엔 2면(썰렁함 방지)
        if has_photo and has_stat:
            p = _p(); render_p2(category_id, cat_name, i, 3, ks, facts, "", p); paths.append(p)
            p = _p(); render_p3(category_id, cat_name, i, 3, bg, simple, why, i == total, p); paths.append(p)
        else:   # 수치는 P1(사진 없을 때) 또는 없음 → P2는 팩트+배경, P3는 쉽게+💡
            p = _p(); render_p2(category_id, cat_name, i, 3, {}, facts, bg, p); paths.append(p)
            p = _p(); render_p3(category_id, cat_name, i, 3, "", simple, why, i == total, p); paths.append(p)
    return paths


# 하위 호환: 기존 단일 카드 호출용 (dry_run 등에서 사용될 수 있음)
def generate_card(content, category_id, category_name_kr, output_path):
    render_detail(category_id, category_name_kr, "", 1, 1,
                  content.get("headline", ""), content.get("summary_lines", []),
                  content.get("comment", ""), "", output_path)
    return output_path


if __name__ == "__main__":
    items = [
        {"headline": "알리익스프레스, EU 과징금 9300억", "subtitle": "과징금 9300억",
         "lead": "EU 집행위원회가 중국 이커머스 플랫폼 알리익스프레스에 약 9,314억 원의 과징금을 부과했습니다. 위조품과 안전 기준을 못 맞춘 위험 상품이 계속 팔렸는데 이를 제대로 걸러내지 못했다는 이유입니다.",
         "facts": ["과징금 규모: 약 9,314억 원", "제재 주체: EU 집행위원회", "사유: 위험 상품 차단 의무 위반"],
         "background": "EU는 지난해부터 디지털서비스법(DSA)으로 대형 플랫폼에 불법·위험 상품을 빠르게 제거할 의무를 지우고 있습니다. 유럽 이용자가 많은 알리는 핵심 감시 대상이었습니다.",
         "simple": "가짜·위험한 물건 방치를 이유로 판매자가 아닌 '판을 깔아준' 플랫폼이 직접 벌금을 문 첫 사례급 사건입니다. 앞으로 대형 플랫폼은 상품 검수 책임에서 더 자유롭지 못하게 됩니다.",
         "why": "규제 부담이 국내 플랫폼 정책에도 번질지 눈여겨볼 만합니다.",
         "key_stat": {"value": "9,314억 원", "label": "EU가 알리에 부과한 과징금"},
         "photo": "tmpimg/_test_photo.jpg", "source": "news.example.com"},
        {"headline": "쿠팡, 로켓배송 입점 기준 강화", "subtitle": "기준 강화",
         "lead": "쿠팡이 로켓배송 신규 입점 심사 기준을 강화한다고 밝혔습니다. 품질과 배송 지표가 미달하면 노출이 제한되고 기존 셀러도 재평가 대상에 포함됩니다.",
         "facts": ["신규 입점 심사 항목 확대", "지표 미달 시 노출 제한", "기존 셀러도 재평가 대상"],
         "background": "쿠팡은 로켓배송 상품 수가 급증하면서 품질 관리 부담이 커졌습니다. 소비자 신뢰 유지를 위해 입점 문턱을 높이는 흐름입니다.",
         "simple": "이제 로켓배송에 들어가고 유지하려면 품질·배송 성적표가 더 중요해졌다는 뜻입니다.",
         "why": "입점·유지 조건이 까다로워져 사전 대비가 필요합니다.",
         "key_stat": {"value": "3단계", "label": "새로 도입되는 입점 심사 등급"}, "source": "news.example.com"},
        {"headline": "이커머스 상반기 거래액 8% 성장", "subtitle": "8% 성장",
         "lead": "올해 상반기 국내 이커머스 거래액이 전년 대비 8% 늘었습니다. 패션·뷰티가 성장을 견인했고 모바일 결제 비중은 역대 최고를 기록했습니다.",
         "facts": ["거래액 전년비 8% 증가", "패션·뷰티가 성장 견인", "모바일 결제 비중 최고"],
         "background": "고물가 속에서도 온라인 소비는 계속 늘었습니다. 다만 하반기는 성장률이 둔화될 것이라는 전망이 나옵니다.",
         "simple": "시장은 아직 크고 있지만 성장 속도는 점점 완만해지는 국면입니다.",
         "why": "성장 카테고리 중심으로 상품 구성을 점검할 시점입니다.", "source": "news.example.com"},
    ]
    ps = generate_carousel("ecommerce", "이커머스", "2026.07.20",
                           "오늘 셀러가 놓치면 안 될 3가지 핵심 이슈", items, "output", "ecommerce_test")
    print("생성:", ps)
