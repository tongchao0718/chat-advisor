# -*- coding: utf-8 -*-
"""
窗口抓取层 —— 移植自 goutoujunshi-jev-chat 官方 Windows 版
(integrations/jev_windows/app/capture.py，MIT，版权归原项目)
改造：find_wechat_hwnd -> list_wechat_hwnds（支持工微/私微多开枚举）
用 Windows Graphics Capture 盯窗口，帧全程内存；等画面停稳再交帧。
"""
import ctypes
import os
import time

import numpy as np

u32 = ctypes.windll.user32


def _exe_of(pid):
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    buf, size = ctypes.create_unicode_buffer(1024), ctypes.c_uint(1024)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    k32.CloseHandle(h)
    return os.path.basename(buf.value).lower() if ok else ""


def list_wechat_hwnds():
    """所有可见的 Weixin/WeChat 顶层窗口 [(hwnd,title)]，含多开。"""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _exe_of(pid.value) in ("weixin.exe", "wechat.exe"):
            buf = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, buf, 256)
            found.append((hwnd, buf.value))
        return True

    u32.EnumWindows(cb, 0)
    return found


def find_wechat_hwnd():
    wins = list_wechat_hwnds()
    if not wins:
        raise RuntimeError("没找到 Weixin/WeChat 的可见窗口，微信开着吗？")
    return next((h for h, t in wins if t == "微信"), wins[0][0])


def unminimize(hwnd):
    """最小化时无激活还原并压到最底——看着像收着，DWM 照样画，不抢焦点。"""
    if not u32.IsIconic(hwnd):
        return False
    u32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    u32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x13)
    return True


def grab_one(hwnd, timeout=2.5, settle=0.25):
    """抓一个停稳的整帧 (RGB numpy)。WGC 失败抛异常，由调用方回退。"""
    from windows_capture import WindowsCapture

    box = {"frame": None}
    cap = WindowsCapture(window_hwnd=hwnd)

    @cap.event
    def on_frame_arrived(frame, control):
        full = np.ascontiguousarray(frame.frame_buffer[:, :, :3][:, :, ::-1])
        if full.max() != 0:
            box["frame"] = full
        try:
            control.stop()
        except Exception:
            pass

    @cap.event
    def on_closed():
        pass

    ctl = cap.start_free_threaded()
    t0 = time.perf_counter()
    while box["frame"] is None and time.perf_counter() - t0 < timeout:
        time.sleep(0.03)
    try:
        ctl.stop()
    except Exception:
        pass
    if box["frame"] is None:
        raise RuntimeError("WGC 超时未出帧")
    return box["frame"]
