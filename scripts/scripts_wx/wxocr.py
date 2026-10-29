# -*- coding: utf-8 -*-
"""
微信4.0 消息区识别 —— 移植自 goutoujunshi-jev-chat 官方 Windows 版
(integrations/jev_windows/app/ocr.py 的成熟实现，版权归原项目 MIT)
- 引擎 max/4000 保留小字分辨率
- chat_area 像素锚点自动定位消息区（不写死比例，适配任意窗口尺寸/独立聊天窗）
- who_said 框内颜色判定：绿底=me / 深字高对比=her / 低对比=gray(时间等) / 图片内字=None
- 同气泡多行按墨高合并，滚动按相似度去重
"""
import difflib
import re
import numpy as np
from rapidocr_onnxruntime import RapidOCR

_ENGINE = None

def engine():
    """全进程单例。det_limit_type 必须 max：默认 min 会把短边压到736，小字直接丢。"""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RapidOCR(intra_op_num_threads=4, det_limit_type="max",
                           det_limit_side_len=4000)
    return _ENGINE


def read_title(header):
    """头部截图→会话名。取最靠上一行里最左的文本；去掉群成员数 (422)。"""
    res, _ = engine()(header, use_cls=False)
    if not res:
        return ""
    first = min(res, key=lambda r: r[0][0][1])
    row = first[0][0][1] + (first[0][2][1] - first[0][0][1])
    text = min((r for r in res if r[0][0][1] < row), key=lambda r: r[0][0][0])[1]
    return re.sub(r"\s*[（(]\d+[)）]\s*$", "", text.strip())


def who_said(chat, box):
    """按 OCR 框里的颜色分类。返回 (me/her/gray/None, 底色, 墨高)。"""
    xs, ys = [p[0] for p in box], [p[1] for p in box]
    reg = chat[int(min(ys)):int(max(ys)), int(min(xs)):int(max(xs))].astype(int)
    if reg.size == 0:
        return None, None, 0
    vals, cnt = np.unique(reg.reshape(-1, 3), axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    if cnt.max() / reg.shape[0] / reg.shape[1] < 0.45:
        # 众数底色占比<45% = 头像/图片/表情包里的字，不是消息
        return None, bg, 0
    diff = np.abs(reg @ [0.299, 0.587, 0.114] - bg @ [0.299, 0.587, 0.114])
    ink_h = best = 0
    for r in (diff > 60).any(axis=1):
        best = best + 1 if r else 0
        ink_h = max(ink_h, best)
    if bg[1] > bg[0] + 40 and bg[1] > bg[2] + 40:
        return "me", bg, ink_h
    return ("her" if diff.max() >= 150 else "gray"), bg, ink_h


def similar(a, b):
    if a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75:
        return True
    return len(a) == len(b) >= 3 and sum(x != y for x, y in zip(a, b)) <= 1


def chat_area(full, header_h=60):
    """像素锚点定位消息列表区 -> (x0,y_top,x1,y_in,面板底色,y0)；认不出 None。"""
    H, W = full.shape[:2]
    right = full[::8, W // 2::8].reshape(-1, 3)
    vals, cnt = np.unique(right, axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    isbg = np.abs(full.astype(int) - bg).sum(-1) <= 6
    col = isbg[H // 4: H * 3 // 4].mean(0)
    x0 = int(np.argmax(col > 0.3))
    x1 = W - int(np.argmax(col[::-1] > 0.3))
    row = isbg[:, x0:x1].mean(1)
    y0 = int(np.argmax(row > 0.9))
    y1 = H - int(np.argmax(row[::-1] > 0.9))
    band = full[y0:y1, x0:x1].astype(int)
    seps = y0 + np.where((band.std(axis=(1, 2)) < 4) & (row[y0:y1] < 0.1))[0]
    seps = [int(s) for i, s in enumerate(seps) if i == 0 or s - seps[i - 1] > 3]
    below = [s for s in seps if s > y0 + 0.45 * (y1 - y0)]
    y_in = below[0] if below else y1
    above = [s for s in seps if y0 + header_h < s < y_in - 50]
    y_top = above[-1] if above else y0 + header_h
    if x1 - x0 < 100 or y_in - y_top < 40:
        return None
    return x0, y_top, x1, y_in, bg, y0


class Reader:
    """一个会话一个 Reader：lh/seen 独立。"""
    def __init__(self):
        self.ocr = engine()
        self.lh = None
        self.seen = []

    def read(self, chat, pane_bg):
        """-> [(who, name, text, y)]，同气泡多行已合并。who∈me/her。"""
        res, _ = self.ocr(chat, use_cls=False)
        W = chat.shape[1]
        name, raw = None, []
        for box, text, _ in sorted(res or [], key=lambda r: r[0][0][1]):
            kind, bg, h = who_said(chat, box)
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            if kind == "gray":
                on_pane = bg is not None and np.abs(bg - pane_bg).sum() <= 6
                if on_pane and box[0][0] < 0.25 * W and len(text) <= 16 \
                        and not re.search("[:：]", text):
                    name = text
                continue
            if kind is None or (self.lh and h < 0.6 * self.lh):
                continue
            raw.append((kind, name if kind == "her" else None, text,
                        box[0][1], box[2][1], h))
        if not self.lh and len(raw) >= 3:
            self.lh = float(np.median([r[5] for r in raw]))
        lines = []
        for who, nm, text, top, bottom, h in raw:
            if lines and lines[-1][0] == who and lines[-1][1] == nm \
                    and top - lines[-1][4] < 0.6 * (self.lh or h):
                lines[-1][2] += text
                lines[-1][4] = bottom
            else:
                lines.append([who, nm, text, top, bottom])
        return [(w, n, t, y) for w, n, t, y, _ in lines]

    def is_seen(self, who, text):
        return any(w == who and similar(t, text) for w, _, t in self.seen)
