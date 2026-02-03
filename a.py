#!/usr/bin/env python3
from __future__ import annotations

import io
import re
import sys
from pathlib import Path
import tokenize

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

def strip_ru_comments_from_file(path: Path) -> bool:
    src = path.read_bytes()
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(src).readline))
    except tokenize.TokenError:
        
        return False

    changed = False
    out_tokens = []

    for tok in tokens:
        if tok.type == tokenize.COMMENT and CYRILLIC_RE.search(tok.string):
            
            out_tokens.append(tokenize.TokenInfo(tok.type, "", tok.start, tok.end, tok.line))
            changed = True
        else:
            out_tokens.append(tok)

    new_src = tokenize.untokenize(out_tokens)

    
    if isinstance(new_src, str):
        new_bytes = new_src.encode("utf-8")
    else:
        new_bytes = new_src

    if changed and new_bytes != src:
        path.write_bytes(new_bytes)
        return True
    return False

def main(root: str = ".") -> int:
    root_path = Path(root)
    py_files = [p for p in root_path.rglob("*.py") if ".venv" not in p.parts and ".git" not in p.parts]

    touched = 0
    for p in py_files:
        if strip_ru_comments_from_file(p):
            touched += 1

    print(f"Done. Updated files: {touched}/{len(py_files)}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
