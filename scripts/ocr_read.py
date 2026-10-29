# -*- coding: utf-8 -*-
"""
本地离线 OCR 读图脚本（隐私不出本机）
用法:
    uv run --with rapidocr-onnxruntime python ocr_read.py 图片路径
输出:
    1. 终端按阅读顺序打印识别文字（上→下，左→右）
    2. 在图片同目录生成 同名_ocr.txt
"""
import sys
from pathlib import Path


def order_lines(items):
    """items: [(box(4点), text, score)] -> 按行聚类、从上到下从左到右排序"""
    rows = []
    for box, text, score in items:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        rows.append((sum(ys) / 4, sum(xs) / 4, (max(ys) - min(ys)), text.strip(), score))
    rows.sort(key=lambda r: (r[0], r[1]))
    lines, cur_y, cur_h = [], None, 0
    for y, x, h, text, score in rows:
        if not text:
            continue
        if cur_y is None or abs(y - cur_y) > max(cur_h, h) * 0.6:
            lines.append([])
            cur_y, cur_h = y, h
        lines[-1].append((x, text, score))
        cur_y = (cur_y * (len(lines[-1]) - 1) + y) / len(lines[-1])
    out = []
    for line in lines:
        line.sort(key=lambda r: r[0])
        out.append(" ".join(t for _, t, _ in line))
    return out


def main():
    if len(sys.argv) < 2:
        print("用法: python ocr_read.py 图片路径 [图片路径2 ...]")
        sys.exit(1)

    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        print("缺少依赖，请用: uv run --with rapidocr-onnxruntime python ocr_read.py 图片")
        sys.exit(2)

    engine = RapidOCR()
    for arg in sys.argv[1:]:
        img = Path(str(arg).strip('"'))
        if not img.exists():
            print(f"[跳过] 找不到文件: {img}")
            continue
        result, _ = engine(str(img))
        if not result:
            print(f"[{img.name}] 没识别到文字")
            continue
        lines = order_lines(result)
        text = "\n".join(lines)
        out_txt = img.with_name(img.stem + "_ocr.txt")
        out_txt.write_text(text, encoding="utf-8")
        print(f"===== {img.name}（{len(lines)} 行）=====")
        print(text)
        print(f"\n[已保存] {out_txt}\n")


if __name__ == "__main__":
    main()
