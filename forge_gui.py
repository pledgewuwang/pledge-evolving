"""
pledge-evolving Windows GUI — 最粗档桌面交互界面
零依赖，纯 tkinter（Python 3.10+ 自带），双击即用。

用法：
    python forge_gui.py          # 直接运行
    pythonw forge_gui.py        # 无控制台窗口

功能：
    - 输入任务，一键运行 forge run
    - 选择策略（economy / balanced / premium）
    - 实时输出日志
    - selftest / doctor 快捷按钮
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
from pathlib import Path

# ---------- 常量 ----------
WINDOW_SIZE = "780x560"
MIN_SIZE = (640, 400)
MAX_LOG_LINES = 1000
FLUSH_THRESHOLD = 20  # 批量刷新阈值

# ---------- 颜色 ----------
BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
BTN_BG = "#313244"
BTN_FG = "#cdd6f4"
ERR_FG = "#f38ba8"
LOG_BG = "#11111b"
LOG_FG = "#a6adc8"


# ---------- 路径探测 ----------
def _find_run_py() -> Path | None:
    """多策略定位 run.py：同目录 → 环境变量 → 向上查找 3 层。"""
    here = Path(__file__).resolve().parent
    # ① 同目录
    candidate = here / "run.py"
    if candidate.is_file():
        return candidate
    # ② 环境变量（非空才走）
    forge_repo = os.environ.get("FORGE_REPO", "").strip()
    if forge_repo:
        env_repo = Path(forge_repo)
        if env_repo.is_dir():
            candidate = env_repo / "run.py"
            if candidate.is_file():
                return candidate
    # ③ 向上查找 3 层
    for p in [here.parent, here.parent.parent, here.parent.parent.parent]:
        candidate = p / "run.py"
        if candidate.is_file():
            return candidate
    return None


RUN_PY = _find_run_py()
if RUN_PY is None:
    raise RuntimeError(
        "找不到 run.py：请设置 FORGE_REPO 环境变量，"
        "或将 forge_gui.py 放在 run.py 同目录"
    )
FORGE_REPO = RUN_PY.parent


class ForgeApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("pledge-evolving GUI")
        self.root.geometry(WINDOW_SIZE)
        self.root.configure(bg=BG)
        self.root.minsize(*MIN_SIZE)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._running = False
        self._proc: subprocess.Popen | None = None

        self._build_ui()

    # ── UI ──────────────────────────────────────────────
    def _build_ui(self):
        # 顶部：策略选择
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill=tk.X, padx=12, pady=(10, 4))

        tk.Label(top, text="策略:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        self.strategy_var = tk.StringVar(value="balanced")
        for s in ("economy", "balanced", "premium"):
            tk.Radiobutton(
                top, text=s, variable=self.strategy_var, value=s,
                bg=BG, fg=FG, selectcolor=BTN_BG, activebackground=BG,
                activeforeground=ACCENT, font=("Segoe UI", 10),
            ).pack(side=tk.LEFT, padx=6)

        # 任务输入
        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill=tk.X, padx=12, pady=4)

        tk.Label(mid, text="任务:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        self.task_entry = tk.Entry(mid, bg=LOG_BG, fg=FG, insertbackground=FG,
                                   font=("Consolas", 11), relief=tk.FLAT)
        self.task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0), ipady=4)
        self.task_entry.bind("<Return>", lambda e: self._run_task())

        # 按钮行
        btns = tk.Frame(self.root, bg=BG)
        btns.pack(fill=tk.X, padx=12, pady=4)

        self.run_btn = tk.Button(btns, text="▶ 运行", bg=ACCENT, fg="#1e1e2e",
                                 font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                                 command=self._run_task, cursor="hand2")
        self.run_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = tk.Button(btns, text="■ 停止", bg=ERR_FG, fg="#1e1e2e",
                                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                                  command=self._stop, state=tk.DISABLED, cursor="hand2")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 16))

        tk.Button(btns, text="selftest", bg=BTN_BG, fg=BTN_FG,
                  font=("Segoe UI", 9), relief=tk.FLAT,
                  command=lambda: self._run_cmd(["selftest"]), cursor="hand2").pack(side=tk.LEFT, padx=4)

        tk.Button(btns, text="doctor", bg=BTN_BG, fg=BTN_FG,
                  font=("Segoe UI", 9), relief=tk.FLAT,
                  command=lambda: self._run_cmd(["doctor"]), cursor="hand2").pack(side=tk.LEFT, padx=4)

        tk.Button(btns, text="清空", bg=BTN_BG, fg=BTN_FG,
                  font=("Segoe UI", 9), relief=tk.FLAT,
                  command=self._clear_log, cursor="hand2").pack(side=tk.RIGHT)

        # 日志输出
        self.log = scrolledtext.ScrolledText(
            self.root, bg=LOG_BG, fg=LOG_FG, insertbackground=FG,
            font=("Consolas", 10), relief=tk.FLAT, wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, bg=BG, fg=LOG_FG,
                 font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X, padx=12, pady=(0, 4))

    # ── 日志 ────────────────────────────────────────────
    def _append(self, text: str, tag: str = ""):
        self.log.configure(state=tk.NORMAL)
        # 行数上限裁剪（off-by-one 修复：+1 确保精确保留 MAX_LOG_LINES 行）
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.log.delete("1.0", f"{line_count - MAX_LOG_LINES + 1}.0")
        self.log.insert(tk.END, text, tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    # ── 执行 ────────────────────────────────────────────
    def _run_task(self):
        task = self.task_entry.get().strip()
        if not task:
            messagebox.showwarning("提示", "请输入任务内容")
            return
        strategy = self.strategy_var.get()
        cmd = [sys.executable, str(RUN_PY), "run", task, "--strategy", strategy]
        self._run_cmd(cmd, full_command=True)

    def _run_cmd(self, args: list[str], full_command: bool = False):
        if self._running:
            return
        if not RUN_PY.is_file():
            messagebox.showerror("错误", f"找不到 run.py\n{RUN_PY}")
            return

        if full_command:
            cmd = args
        else:
            cmd = [sys.executable, str(RUN_PY)] + args

        self._running = True
        self.run_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        # 状态栏显示 run.py 之后的完整子命令（含任务和策略）
        run_py_idx = next((i for i, v in enumerate(cmd) if v == str(RUN_PY)), -1)
        status_text = " ".join(cmd[run_py_idx + 1:]) if run_py_idx >= 0 else " ".join(cmd)
        self.status_var.set(f"运行中: {status_text}")

        self._clear_log()
        self._append(f"$ {' '.join(cmd)}\n\n")

        threading.Thread(target=self._exec, args=(cmd,), daemon=True).start()

    def _exec(self, cmd: list[str]):
        try:
            kwargs: dict = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8-sig",
                cwd=str(FORGE_REPO),
                bufsize=1,
            )
            if sys.platform == "win32":
                kwargs["creationflags"] = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_NO_WINDOW
                )
            self._proc = subprocess.Popen(cmd, **kwargs)

            # 批量刷新：累积行，定期写入 UI
            buffer: list[str] = []
            for line in self._proc.stdout:
                buffer.append(line)
                if len(buffer) >= FLUSH_THRESHOLD:
                    self.root.after(0, self._append, "".join(buffer))
                    buffer.clear()
            if buffer:
                self.root.after(0, self._append, "".join(buffer))

            rc = self._proc.wait()
            tag = "" if rc == 0 else "err"
            self.root.after(0, self._append, f"\n[退出码: {rc}]\n", tag)
            self.root.after(0, self.status_var.set, f"完成 (exit {rc})")
        except Exception as e:
            self.root.after(0, self._append, f"\n[错误: {e}]\n", "err")
            self.root.after(0, self.status_var.set, "出错")
        finally:
            self._running = False
            self._proc = None
            self.root.after(0, lambda: self.run_btn.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_btn.configure(state=tk.DISABLED))

    def _stop(self):
        if self._proc and self._proc.poll() is None:
            if sys.platform == "win32":
                try:
                    self._proc.send_signal(signal.CTRL_BREAK_EVENT)
                    self._proc.wait(timeout=3)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        self._proc.terminate()
                    except Exception:
                        pass  # 进程已消失
            else:
                self._proc.terminate()
            self._append("\n[已终止]\n", "err")
            self.status_var.set("已停止")

    def _on_close(self):
        """关闭窗口时停止子进程，避免孤儿。"""
        if self._running and self._proc:
            self._stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    # Windows DPI 适配
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = ForgeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
