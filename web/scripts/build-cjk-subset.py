#!/usr/bin/env python3
"""生成中文衬线字体子集（思源宋体 → web/public/fonts/NotoSerifSC-Subset-*.woff2）。

为什么需要它：思源宋体完整字库 1.5MB+，而这里只需要"应用真正会显示的字"。
字符来源（四类，缺一不可 —— 少任何一类，页面上就会出现"同一句话两种字体"的拼接）：

  1. web/src/**                  —— 界面固定文案
  2. data/**                     —— 语料/图谱/评测集（页面展示的实体名、会话标题等运行时文本）
  3. backend/app/**              —— 后端中文文案（拒答/安全提示等，会被前端原样展示）
  4. docs/**                     —— 领域词汇补充（中医药术语覆盖面）
  5. jieba 词频表高频汉字缓冲    —— 用户提问与模型回答里的常见字（兜底）

两个字重（400/600）使用**完全相同的字符集**：字重不一致时，浏览器按字重取字会
在"某字重缺字"处掉回系统字体，正是字体拼接的另一个来源。

依赖：fonttools、brotli（pip install fonttools brotli）；jieba 可选（缺省则跳过高频缓冲）。
重新生成：cd web && python scripts/build-cjk-subset.py
"""
import pathlib
import subprocess
import sys
import tempfile
import urllib.request

WEB = pathlib.Path(__file__).resolve().parent.parent
REPO = WEB.parent
OUT_DIR = WEB / "public" / "fonts"
TMP = pathlib.Path(tempfile.gettempdir())

# Fontsource 提供的思源宋体简体静态字重（SIL OFL），按需下载到临时目录
SOURCES = {
    400: "https://cdn.jsdelivr.net/npm/@fontsource/noto-serif-sc@5/files/"
         "noto-serif-sc-chinese-simplified-400-normal.woff2",
    600: "https://cdn.jsdelivr.net/npm/@fontsource/noto-serif-sc@5/files/"
         "noto-serif-sc-chinese-simplified-600-normal.woff2",
}
BUFFER_SIZE = 3000  # 高频汉字缓冲字数
WEIGHTS = (400, 600)

# 覆盖自检：用户反馈过字体拼接的样例必须落在子集内
MUST_CONTAIN = "养阴益胃生津人参党参西洋参补气证型区别各自适合什么本草图谱"


def collect(paths, exts):
    """抽取给定目录下源码/数据里出现的所有 CJK 字符（含中文标点、全角符号）。"""
    chars = set()
    for base in paths:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in exts:
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                chars |= {c for c in text if 0x2E7F < ord(c) < 0x30000}
    return chars


def high_freq_buffer(size):
    """从 jieba 词频表按词频取高频汉字，覆盖用户输入/模型输出的常见字。"""
    try:
        import jieba
    except ImportError:
        print("[warn] 未安装 jieba，跳过高频缓冲（覆盖率会下降）")
        return set()
    words = []
    with (pathlib.Path(jieba.__file__).parent / "dict.txt").open(encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    words.append((int(parts[1]), parts[0]))
                except ValueError:
                    continue
    words.sort(reverse=True)
    buffer = set()
    for _, word in words:
        buffer |= {c for c in word if 0x4DFF < ord(c) < 0x9FFF}
        if len(buffer) >= size:
            break
    return buffer


def subset(src, chars, weight):
    text_file = TMP / f"medirag-cjk-{weight}.txt"
    text_file.write_text("".join(sorted(chars)), encoding="utf-8")
    out = OUT_DIR / f"NotoSerifSC-Subset-{weight}.woff2"
    subprocess.run([sys.executable, "-m", "fontTools.subset", str(src),
                    f"--text-file={text_file}", "--flavor=woff2",
                    f"--output-file={out}", "--layout-features=*", "--no-hinting",
                    "--desubroutinize", "--drop-tables+=DSIG"], check=True)
    return out


def verify(out, chars):
    """用生成结果的 cmap 校验覆盖，避免"以为覆盖了其实没有"。"""
    from fontTools.ttLib import TTFont
    cmap = set()
    with TTFont(out) as font:
        for table in font["cmap"].tables:
            cmap |= set(table.cmap.keys())
    missing = [c for c in MUST_CONTAIN if ord(c) not in cmap]
    return missing


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chars = collect([WEB / "src"], {".vue", ".ts", ".css"})
    chars |= collect([REPO / "data"], {".md", ".json", ".jsonl", ".txt", ".csv"})
    chars |= collect([REPO / "backend" / "app"], {".py", ".md", ".txt"})
    chars |= collect([REPO / "docs"], {".md"})
    chars |= high_freq_buffer(BUFFER_SIZE)
    chars -= set("\n\r\t")
    print(f"[1] 字符集 {len(chars)} 字（两个字重共用同一字符集）")

    for weight in WEIGHTS:
        src = TMP / f"NotoSerifSC-{weight}-src.woff2"
        if not src.exists():
            print(f"[2] 下载 {weight} 字重源字体 ...")
            urllib.request.urlretrieve(SOURCES[weight], src)

        out = subset(src, chars, weight)
        missing = verify(out, chars)
        status = "覆盖校验通过" if not missing else f"缺字: {''.join(missing)}"
        print(f"[3] {out.name}  {out.stat().st_size / 1024:.0f} KB  {status}")
        if missing:
            sys.exit(1)


if __name__ == "__main__":
    main()
