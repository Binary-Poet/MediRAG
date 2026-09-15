"""切片器：纯文本 → 带元数据切片（方案 6.1 splitter.py）。

策略：按"页（\\f）"分割；页内按行累积到 ~MAX_CHUNK_CHARS 字符切一片（空行保留为
段落分隔，不作为强制切点）；每片带 doc_name/chapter/page_no/topic 元数据。
page_no 语义：有分页符时=PDF 页号；无分页符时=页内块序号（1 起，来源可追溯）。
"""
MAX_CHUNK_CHARS = 500


def split_text(text: str, doc_name: str, topic: str, base_seq: int = 0) -> list[dict]:
    """返回 [{'chunk_id','title','doc_name','chapter','page_no','topic','text'}, ...]。"""
    chunks: list[dict] = []
    seq = base_seq
    pages = text.split("\f")
    multi_page = len(pages) > 1

    for page_no, page in enumerate(pages, start=1):
        buf: list[str] = []
        size = 0

        def flush() -> None:
            nonlocal seq, buf, size
            body = "\n".join(buf).strip()
            if not body:
                buf, size = [], 0
                return
            chunks.append({
                "chunk_id": f"{doc_name}#{seq:04d}",
                "title": f"{doc_name} 切片 {seq + 1}",
                "doc_name": doc_name,
                "chapter": f"第 {page_no} 页",
                "page_no": page_no if multi_page else (seq - base_seq + 1),
                "topic": topic,
                "text": body,
            })
            seq += 1
            buf, size = [], 0

        for raw in page.split("\n"):
            line = raw.rstrip()
            if not line.strip():
                buf.append("")                      # 空行保留段落分隔，不触发切分
                size += 2                           # 计入 "\n\n" 分隔开销，bounds 内的块
                continue
            if size + len(line) > MAX_CHUNK_CHARS and buf:
                flush()
            buf.append(line)
            size += len(line)
        flush()
    return chunks