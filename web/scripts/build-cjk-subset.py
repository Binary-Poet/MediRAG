#!/usr/bin/env python3
"""生成中文衬线字体子集（思源宋体 → web/public/fonts/NotoSerifSC-Subset-*.woff2）。

为什么需要它：思源宋体完整字库 1.5MB+，而这里只需要"应用真正会显示的字"。
字符来源（四类，缺一不可 —— 少任何一类，页面上就会出现"同一句话两种字体"的拼接）：

  1. web/src/**                  —— 界面固定文案
  2. data/**                     —— 语料/图谱/评测集（页面展示的实体名、会话标题等运行时文本）
  3. backend/app/**              —— 后端中文文案（拒答/安全提示等，会被前端原样展示）
  4. docs/**                     —— 领域词汇补充（中医药术语覆盖面）
  5. jieba 词频表高频汉字缓冲    —— 用户提问与模型回答里的常见字（兜底）

发布 500/600 两个字重，两者使用**完全相同的字符集**：字重不一致时，浏览器按字重取字
会在"某字重缺字"处掉回系统字体，正是字体拼接的另一个来源。

为什么正文基准是 500 而不是 400：思源宋体 400 的横画在 14px 下不足 1 个像素，
Windows 灰阶抗锯齿渲染出来又细又虚（实测反馈「太细、看不清」）。500（Medium）
既保住衬线排版的身份，又把笔画撑到可读。500 由 400/600 两个静态母版插值而来
（思源宋体各字重共用同一套轮廓结构，脚本内带兼容性校验），不增加字体下载量：
发布的文件数仍是 2 个，400 只作为插值母版、不再发布。

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

# Fontsource 提供的思源宋体简体静态字重（SIL OFL），按需下载到临时目录。
# 两者都要下载：400 是插值母版，600 既是母版也是发布档。
SOURCES = {
    400: "https://cdn.jsdelivr.net/npm/@fontsource/noto-serif-sc@5/files/"
         "noto-serif-sc-chinese-simplified-400-normal.woff2",
    600: "https://cdn.jsdelivr.net/npm/@fontsource/noto-serif-sc@5/files/"
         "noto-serif-sc-chinese-simplified-600-normal.woff2",
}
BUFFER_SIZE = 3000  # 高频汉字缓冲字数
MASTER_WEIGHTS = (400, 600)  # 需要子集化的静态母版
PUBLISH_WEIGHTS = (600,)     # 直接发布的静态字重（500 由母版插值得到，见 interpolate）
MID_WEIGHT = 500             # 正文基准字重：由 400/600 插值

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


def subset(src, chars, out, flavor="woff2"):
    """按字符集裁出子集：src → out。flavor=None 时输出未压缩 TTF（供插值当母版用）。

    --no-hinting：剥掉 TrueType 指令。三个字重共用同一套处理，保证轮廓结构一致 ——
    这是后面能插值的前提；指令在 Chrome 的 DirectWrite 渲染下也不参与栅格化。
    """
    text_file = TMP / "medirag-cjk-chars.txt"
    text_file.write_text("".join(sorted(chars)), encoding="utf-8")
    cmd = [sys.executable, "-m", "fontTools.subset", str(src),
           f"--text-file={text_file}", f"--output-file={out}",
           "--layout-features=*", "--no-hinting",
           "--desubroutinize", "--drop-tables+=DSIG"]
    if flavor:
        cmd.append(f"--flavor={flavor}")
    subprocess.run(cmd, check=True)
    return out


def strip_tables(path, tags=("BASE", "JSTF")):
    """剥离网页渲染用不到、且会阻塞插值的表。

    BASE（基线坐标）不在 pyftsubset 的默认丢弃列表里，而 varLib 合并它时会以
    UnsupportedFormat 直接失败；它只影响复杂排版引擎的基线对齐，浏览器不读。
    """
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    dropped = [t for t in tags if t in font]
    for tag in dropped:
        del font[tag]
    if dropped:
        font.save(path)
    font.close()
    return dropped


def fingerprint(font):
    """字形结构指纹：轮廓类型 + 每条轮廓的点数 / 组件列表。"""
    glyf = font["glyf"]
    out = {}
    for name in font.getGlyphOrder():
        g = glyf[name]
        if g.isComposite():
            out[name] = ("composite", tuple(c.glyphName for c in g.components))
        elif g.numberOfContours == 0:
            out[name] = ("empty",)
        else:
            _coords, end_pts, _flags = g.getCoordinates(glyf)
            counts, prev = [], -1
            for end in end_pts:
                counts.append(end - prev)
                prev = end
            out[name] = ("simple", tuple(counts))
    return out


def check_compatible(masters):
    """插值前置校验：字形集合与轮廓结构必须一一对应。

    不做这步也能 build，但 varLib 抛出的报错很难读懂；提前失败才能给出可操作的提示。
    """
    from fontTools.ttLib import TTFont

    items = sorted(masters.items())
    with TTFont(items[0][1]) as base_font:
        base = fingerprint(base_font)
    for weight, path in items[1:]:
        with TTFont(path) as font:
            other = fingerprint(font)
        if set(base) != set(other):
            sys.exit(f"[!] {items[0][0]} 与 {weight} 字形集合不一致，无法插值")
        bad = [n for n in base if base[n] != other[n]]
        if bad:
            sys.exit(f"[!] {items[0][0]} 与 {weight} 有 {len(bad)} 个字形结构不兼容，"
                     f"无法插值：{bad[:5]}")
    print(f"[3] 插值兼容性校验通过（{len(base)} 字形）")


def interpolate(masters, target, out):
    """由多个静态母版插值出中间字重：先建可变字体，再在目标轴值上实例化。

    500 字重官方静态档需要联网下载，而思源宋体各字重本就同源（结构一致），
    直接线性插值即可，不额外增加字体下载量。
    """
    from fontTools.designspaceLib import (AxisDescriptor, DesignSpaceDocument,
                                          SourceDescriptor)
    from fontTools.varLib import build as build_vf
    from fontTools.varLib.instancer import instantiateVariableFont

    lo, hi = min(masters), max(masters)
    check_compatible(masters)

    doc = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.name, axis.tag = "Weight", "wght"
    axis.minimum, axis.maximum, axis.default = lo, hi, lo
    doc.addAxis(axis)
    for weight, path in sorted(masters.items()):
        src = SourceDescriptor()
        src.name, src.path, src.location = f"w{weight}", str(path), {"Weight": weight}
        doc.addSource(src)

    vf, _model, _master_fonts = build_vf(doc)
    instantiateVariableFont(vf, {"wght": target}, inplace=True, updateFontNames=False)
    vf["OS/2"].usWeightClass = target  # 内部字重标记与实际档位对齐
    vf.flavor = "woff2"
    vf.save(out)
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
    from fontTools.ttLib import TTFont

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chars = collect([WEB / "src"], {".vue", ".ts", ".css"})
    chars |= collect([REPO / "data"], {".md", ".json", ".jsonl", ".txt", ".csv"})
    chars |= collect([REPO / "backend" / "app"], {".py", ".md", ".txt"})
    chars |= collect([REPO / "docs"], {".md"})
    chars |= high_freq_buffer(BUFFER_SIZE)
    chars -= set("\n\r\t")
    print(f"[1] 字符集 {len(chars)} 字（各字重共用同一字符集）")

    # 先裁出静态母版（未压缩 TTF，插值用）
    masters = {}
    for weight in MASTER_WEIGHTS:
        src = TMP / f"NotoSerifSC-{weight}-src.woff2"
        if not src.exists():
            print(f"[2] 下载 {weight} 字重源字体 ...")
            urllib.request.urlretrieve(SOURCES[weight], src)
        masters[weight] = subset(src, chars, TMP / f"medirag-cjk-master-{weight}.ttf",
                                 flavor=None)
        strip_tables(masters[weight])
    print(f"[2] 母版子集化完成（已剥离 BASE/JSTF）："
          f"{', '.join(str(w) for w in MASTER_WEIGHTS)}")

    outputs = {}
    for weight in PUBLISH_WEIGHTS:
        out = OUT_DIR / f"NotoSerifSC-Subset-{weight}.woff2"
        with TTFont(masters[weight]) as font:  # 母版转 woff2，轮廓不再二次处理
            font.flavor = "woff2"
            font.save(out)
        outputs[weight] = out

    out = OUT_DIR / f"NotoSerifSC-Subset-{MID_WEIGHT}.woff2"
    interpolate(masters, MID_WEIGHT, out)
    outputs[MID_WEIGHT] = out

    # 清掉不再发布的旧档位，避免 public/fonts 里留着没人引用的字体
    stale = [p for p in OUT_DIR.glob("NotoSerifSC-Subset-*.woff2") if p not in outputs.values()]
    for path in stale:
        path.unlink()
        print(f"[4] 移除已弃用字重文件 {path.name}")

    for weight, path in sorted(outputs.items()):
        missing = verify(path, chars)
        status = "覆盖校验通过" if not missing else f"缺字: {''.join(missing)}"
        print(f"[5] {path.name}  {path.stat().st_size / 1024:.0f} KB  {status}")
        if missing:
            sys.exit(1)


if __name__ == "__main__":
    main()
