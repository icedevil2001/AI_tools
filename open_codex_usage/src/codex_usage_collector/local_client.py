from __future__ import annotations

from pathlib import Path


class LocalSessionClient:
    def __enter__(self) -> "LocalSessionClient":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def list_json_files(self, local_path: str) -> list[str]:
        root = Path(local_path).expanduser()
        if not root.exists() or not root.is_dir():
            return []
        files = [*root.rglob("*.json"), *root.rglob("*.jsonl")]
        return sorted(str(path) for path in files if path.is_file())

    def read_file(self, local_path: str) -> str:
        return Path(local_path).read_text(encoding="utf-8")
