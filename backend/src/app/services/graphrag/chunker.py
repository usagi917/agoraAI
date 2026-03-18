"""SemanticChunker: 段落・セクション境界でチャンク分割"""

import re


class SemanticChunker:
    def __init__(self, chunk_size: int = 2000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> list[dict]:
        """テキストをセマンティックチャンクに分割する。

        セクション境界（見出し、空行区切り）を優先して分割する。
        """
        if not text.strip():
            return []

        # セクション境界で分割を試みる
        sections = self._split_by_sections(text)

        chunks = []
        current_chunk = ""
        chunk_index = 0

        for section in sections:
            if len(current_chunk) + len(section) <= self.chunk_size:
                current_chunk += section
            else:
                if current_chunk.strip():
                    chunks.append({
                        "index": chunk_index,
                        "text": current_chunk.strip(),
                        "char_start": sum(len(c["text"]) for c in chunks),
                    })
                    chunk_index += 1

                # オーバーラップ部分を保持
                if self.chunk_overlap > 0 and current_chunk:
                    overlap = current_chunk[-self.chunk_overlap:]
                    current_chunk = overlap + section
                else:
                    current_chunk = section

                # セクション自体がchunk_sizeを超える場合は強制分割
                while len(current_chunk) > self.chunk_size:
                    split_point = self._find_split_point(current_chunk, self.chunk_size)
                    chunks.append({
                        "index": chunk_index,
                        "text": current_chunk[:split_point].strip(),
                        "char_start": sum(len(c["text"]) for c in chunks),
                    })
                    chunk_index += 1
                    current_chunk = current_chunk[split_point - self.chunk_overlap:]

        if current_chunk.strip():
            chunks.append({
                "index": chunk_index,
                "text": current_chunk.strip(),
                "char_start": sum(len(c["text"]) for c in chunks),
            })

        return chunks

    def _split_by_sections(self, text: str) -> list[str]:
        """見出しや空行で区切られたセクションに分割する。"""
        # Markdown見出し、空行2つ以上で分割
        pattern = r"(?=\n#{1,3}\s)|(?:\n\n\n+)|(?:\n---+\n)"
        parts = re.split(pattern, text)
        return [p for p in parts if p.strip()]

    def _find_split_point(self, text: str, max_len: int) -> int:
        """文の境界で分割点を見つける。"""
        # max_len以下の最後の文末を探す
        candidates = [
            text.rfind("。", 0, max_len),
            text.rfind(".\n", 0, max_len),
            text.rfind("\n\n", 0, max_len),
            text.rfind("\n", 0, max_len),
        ]
        best = max(c for c in candidates if c > 0) if any(c > 0 for c in candidates) else max_len
        return best + 1
