"""Copy local 880 sources into the repository's cloud-ready data tree."""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_and_verify(source: Path, target: Path, patterns: tuple[str, ...]) -> int:
    if not source.is_dir():
        raise SystemExit(f"源目录不存在：{source}")
    target.mkdir(parents=True, exist_ok=True)
    files = sorted({path for pattern in patterns for path in source.glob(pattern) if path.is_file()})
    for src in files:
        dst = target / src.name
        shutil.copy2(src, dst)
        if sha256(src) != sha256(dst):
            raise SystemExit(f"复制校验失败：{src.name}")
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="将本地 880 数据归档到仓库 data/ 目录")
    parser.add_argument("--metadata-source", type=Path, default=Path(r"D:\桌面\考点"))
    parser.add_argument("--problems-source", type=Path, default=Path(r"D:\桌面\原题目"))
    args = parser.parse_args()
    metadata_count = copy_and_verify(
        args.metadata_source, PROJECT_ROOT / "data" / "metadata", ("*.json",)
    )
    problem_count = copy_and_verify(
        args.problems_source, PROJECT_ROOT / "data" / "problems", ("*.md", "*.markdown")
    )
    print(f"归档完成：{metadata_count} 个 JSON，{problem_count} 个 Markdown。")


if __name__ == "__main__":
    main()
