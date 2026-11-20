"""哈希工具：文档内容去重与稳定 document_id 生成。

- sha1_hex：短哈希，用于 document_id（与 file_parser 约定一致：doc_ + sha1[:10]）；
- sha256_hex：文件内容去重（与 collector 去重语义一致）。
"""

import hashlib
from typing import Optional, Union

DOCUMENT_ID_PREFIX = "doc_"
DOCUMENT_ID_LENGTH = 10


def sha1_hex(value: Union[str, bytes]) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha1(data).hexdigest()


def sha256_hex(value: Union[str, bytes]) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def document_id(filename: Optional[str], content: Optional[str],
                prefix: str = DOCUMENT_ID_PREFIX,
                length: int = DOCUMENT_ID_LENGTH) -> str:
    """稳定文档 id：filename + content 的 sha1 前缀；两者皆空时由调用方补 uuid。"""
    return prefix + sha1_hex((filename or "") + (content or ""))[:length]
