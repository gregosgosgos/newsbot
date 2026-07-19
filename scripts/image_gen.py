"""
카드뉴스 이미지 생성기 (PIL 기반, 무료).
"""
import os
from PIL import Image, ImageDraw, ImageFont

from config import (
    IMG_WIDTH, IMG_HEIGHT, FONT_BOLD, FONT_REGULAR, FONT_INDEX_KR, CATEGORY_COLORS,
)

MARGIN = 80


def _font(path, size):
    return ImageFont.truetype(path, size, index=FONT_INDEX_KR)


def _wrap_and_draw(draw, text, font, x, y, max_width, fill, line_spacing=1.3):
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        w = draw.textlength(test, font=font)
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)

    line_height = int(font.size * line_spacing)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def generate_card(content: dict, category_id: str, category_name_kr: str, output_path: str) -> str:
    color = CATEGORY_COLORS.get(category_id, "#333333")

    img = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), color="#FFFFFF")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, IMG_WIDTH, 16], fill=color)

    font_label = _font(FONT_BOLD, 34)
    draw.text((MARGIN, 70), f"#{category_name_kr}", font=font_label, fill=color)

    font_headline = _font(FONT_BOLD, 64)
    y = 140
    y = _wrap_and_draw(draw, content["headline"], font_headline, MARGIN, y,
                        IMG_WIDTH - 2 * MARGIN, fill="#111111", line_spacing=1.25)

    y += 30
    draw.line([(MARGIN, y), (IMG_WIDTH - MARGIN, y)], fill="#DDDDDD", width=2)
    y += 50

    font_body = _font(FONT_REGULAR, 42)
    for line in content["summary_lines"]:
        y = _wrap_and_draw(draw, f"· {line}", font_body, MARGIN, y,
                            IMG_WIDTH - 2 * MARGIN, fill="#333333", line_spacing=1.4)
        y += 20

    box_top = IMG_HEIGHT - 260
    draw.rectangle([MARGIN, box_top, IMG_WIDTH - MARGIN, IMG_HEIGHT - 100],
                   fill="#F5F5F5", outline=color, width=3)
    font_comment = _font(FONT_BOLD, 36)
    _wrap_and_draw(draw, content["comment"], font_comment, MARGIN + 30, box_top + 30,
                   IMG_WIDTH - 2 * MARGIN - 60, fill=color, line_spacing=1.3)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "JPEG", quality=90)
    return output_path


if __name__ == "__main__":
    sample_content = {
        "headline": "배달앱 수수료 인하 요구 확산",
        "summary_lines": [
            "자영업자 단체, 배달앱 3사에 공동 요청",
            "7월 19일 성명 발표",
            "업계 반응은 아직 미온적",
        ],
        "comment": "외식업 원가 부담에 직접 영향을 주는 이슈입니다",
    }
    path = generate_card(sample_content, "food_industry", "식품/외식업", "output/test_card.jpg")
    print("생성됨:", path)
