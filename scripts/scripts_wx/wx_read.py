# -*- coding: utf-8 -*-
"""
微信聊天一键读取（最终版）
  抓取: Windows Graphics Capture 后台无感抓帧（不抢焦点、窗口不闪）
  识别: 移植 goutoujunshi-jev-chat 官方算法（max/4000 + 像素锚点定位 + 颜色判说话人）
  输出: 先原封不动打印带编号原文供核对，再存 记录/窗口读取_<tag>.md / .json
用法:
  python wx_read.py [会话名关键词，默认 微暖] [--tag 标签] [--save-raw]
"""
import sys, io, time, json, argparse
from pathlib import Path
from difflib import SequenceMatcher
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import wxcapture, wxocr

ROOT = Path(r"E:/个人资料/个人资料/xiaoZzhushou")
REC = ROOT / "记录"
REC.mkdir(exist_ok=True)


def pick_session(kw):
    """枚举所有微信主窗，WGC 抓帧读会话名，模糊匹配目标。返回 (hwnd,name,frame)。"""
    mains = [(h, t) for h, t in wxcapture.list_wechat_hwnds() if t == "微信"]
    if not mains:
        raise SystemExit("ERR: 没找到微信主窗口，请先登录并打开微信")
    cands = []
    for hwnd, _ in mains:
        wxcapture.unminimize(hwnd)
        try:
            frame = wxcapture.grab_one(hwnd)
        except Exception as e:
            print(f"  (窗口 {hwnd:#x} 抓取失败: {e})")
            continue
        area = wxocr.chat_area(frame)
        if area is None:
            continue
        x0, ytop, x1, yin, bg, y0 = area
        name = wxocr.read_title(frame[y0:ytop, x0:x0 + 300])
        cands.append((hwnd, name, frame))
        hit = (kw in name) or (len(kw) >= 2 and any(
            SequenceMatcher(None, kw, s).ratio() >= 0.5
            for s in name.replace("+", " ").split() if len(s) >= len(kw) - 1))
        if hit:
            return hwnd, name, frame
    names = ", ".join(n or "(未识别)" for _, n, _ in cands)
    raise SystemExit(f"ERR: 没找到会话名含 {kw!r} 的窗口（当前打开的会话：{names}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", nargs="?", default="微暖")
    ap.add_argument("--tag", default="")
    ap.add_argument("--save-raw", action="store_true", help="同时存原始帧PNG")
    a = ap.parse_args()

    hwnd, name, frame = pick_session(a.keyword)
    area = wxocr.chat_area(frame)
    x0, ytop, x1, yin, bg, y0 = area
    chat = frame[ytop:yin, x0:x1]
    reader = wxocr.Reader()
    lines = reader.read(chat, bg)
    me = sum(1 for w, *_ in lines if w == "me")
    her = sum(1 for w, *_ in lines if w == "her")

    # ---- 先原封不动输出带编号原文（供核对）----
    print("=" * 56)
    print(f"会话：{name}    读取时间：{time.strftime('%Y-%m-%d %H:%M')}")
    print(f"共 {len(lines)} 条（我 {me} / 她 {her}）")
    print("=" * 56)
    for i, (who, _, text, _y) in enumerate(lines, 1):
        tag = "我 " if who == "me" else "她 "
        print(f"{i:>2}. [{tag}] {text}")
    print("=" * 56)
    print("↑ 请核对原文；时间戳/图片/表情系统不转录。确认后我再分析。")

    # ---- 存档 ----
    tag = a.tag or time.strftime("%Y%m%d_%H%M")
    stem = f"窗口读取_{tag}"
    md = [f"# 与{name}聊天·窗口读取 {time.strftime('%Y-%m-%d %H:%M')}",
          f"<!-- WGC无感抓帧+官方OCR算法，共{len(lines)}条：我{me}/她{her}；时间戳不转录 -->", ""]
    for who, _, text, _y in lines:
        md.append(f"**{'我' if who == 'me' else '她'}：** {text}")
        md.append("")
    (REC / f"{stem}.md").write_text("\n".join(md), encoding="utf-8")
    (REC / f"{stem}.json").write_text(json.dumps(
        {"time": time.strftime("%Y-%m-%d %H:%M"), "peer": name,
         "counts": {"我": me, "她": her},
         "messages": [{"sender": "我" if w == "me" else "她", "text": t}
                      for w, _, t, _y in lines]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    if a.save_raw:
        (REC / "raw").mkdir(exist_ok=True)
        from PIL import Image
        Image.fromarray(frame).save(REC / "raw" / f"{stem}.png")
    print(f"已存档：记录/{stem}.md / .json")


if __name__ == "__main__":
    main()
