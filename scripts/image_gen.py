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


def generate_carousel(category_id, cat_name, date_str, hook, items, out_dir, prefix):
    """items = [{headline, subtitle, summary_lines, comment, source}] (최대 3).
    반환: [표지경로, 상세1, 상세2, ...] (슬라이드 순서)."""
    paths = []
    cover = os.path.join(out_dir, f"{prefix}_0.jpg")
    render_cover(category_id, cat_name, date_str, hook,
                 [(it["headline"], it.get("subtitle", "")) for it in items], cover)
    paths.append(cover)
    total = len(items)
    for i, it in enumerate(items, 1):
        p = os.path.join(out_dir, f"{prefix}_{i}.jpg")
        render_detail(category_id, cat_name, date_str, i, total,
                      it["headline"], it.get("summary_lines", []),
                      it.get("comment", ""), it.get("source", ""), p)
        paths.append(p)
    return paths


# 하위 호환: 기존 단일 카드 호출용 (dry_run 등에서 사용될 수 있음)
def generate_card(content, category_id, category_name_kr, output_path):
    render_detail(category_id, category_name_kr, "", 1, 1,
                  content.get("headline", ""), content.get("summary_lines", []),
                  content.get("comment", ""), "", output_path)
    return output_path


if __name__ == "__main__":
    items = [
        {"headline": "네이버 스마트스토어 수수료 정책 개편안 공개", "subtitle": "개편안 공개",
         "summary_lines": ["11월부터 결제 수수료 구간 개편 적용", "소규모 판매자 부담 완화 방향", "세부 요율표는 8월 중 공지 예정"],
         "comment": "정산 구조가 바뀌는 만큼 마진 재점검이 필요합니다", "source": "news.example.com"},
        {"headline": "쿠팡, 로켓배송 입점 기준 강화 발표", "subtitle": "강화 발표",
         "summary_lines": ["신규 입점 심사 항목 확대", "품질·배송 지표 미달 시 노출 제한", "기존 셀러도 재평가 대상 포함"],
         "comment": "입점·유지 조건이 까다로워져 대비가 필요합니다", "source": "news.example.com"},
        {"headline": "이커머스 상반기 거래액 전년비 8% 성장", "subtitle": "8% 성장",
         "summary_lines": ["패션·뷰티 카테고리가 성장 견인", "모바일 결제 비중 역대 최고", "하반기 성장률은 둔화 전망"],
         "comment": "성장 카테고리로 상품 구성을 점검할 시점입니다", "source": "news.example.com"},
    ]
    ps = generate_carousel("ecommerce", "이커머스", "2026.07.20",
                           "오늘 셀러가 놓치면 안 될 3가지 핵심 이슈", items, "output", "ecommerce_test")
    print("생성:", ps)
