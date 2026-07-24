"""
Pluggable JSON blob storage.

Two backends, selected by environment:
  - GCSStorage   when GCS_BUCKET is set (production — persistent, shared across instances)
  - LocalStorage otherwise            (dev/tests — a directory on disk)

Keys are '/'-separated paths (e.g. "routes/admin/<id>.json"). This is the persistence
layer for saved routes; the same interface can later back a shared analysis cache.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any, List, Optional


class Storage:
    def read_json(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def write_json(self, key: str, value: Any) -> None:
        raise NotImplementedError

    def list(self, prefix: str) -> List[str]:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self, base: pathlib.Path):
        self.base = pathlib.Path(base)

    def _p(self, key: str) -> pathlib.Path:
        return self.base / key

    def read_json(self, key: str) -> Optional[Any]:
        p = self._p(key)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def write_json(self, key: str, value: Any) -> None:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding="utf-8")

    def list(self, prefix: str) -> List[str]:
        base = self._p(prefix)
        if not base.exists():
            return []
        return sorted(
            str(f.relative_to(self.base)).replace("\\", "/")
            for f in base.rglob("*.json")
        )

    def delete(self, key: str) -> bool:
        p = self._p(key)
        if p.exists():
            p.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._p(key).exists()


class GCSStorage(Storage):
    def __init__(self, bucket_name: str, prefix: str = ""):
        from google.cloud import storage as gcs  # lazy — only needed in prod

        self._client = gcs.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._prefix = prefix

    def _blob(self, key: str):
        return self._bucket.blob(self._prefix + key)

    def read_json(self, key: str) -> Optional[Any]:
        b = self._blob(key)
        if not b.exists():
            return None
        return json.loads(b.download_as_text())

    def write_json(self, key: str, value: Any) -> None:
        self._blob(key).upload_from_string(
            json.dumps(value), content_type="application/json"
        )

    def list(self, prefix: str) -> List[str]:
        n = len(self._prefix)
        return sorted(
            bl.name[n:]
            for bl in self._client.list_blobs(self._bucket, prefix=self._prefix + prefix)
            if bl.name.endswith(".json")
        )

    def delete(self, key: str) -> bool:
        b = self._blob(key)
        if b.exists():
            b.delete()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._blob(key).exists()


def get_storage() -> Storage:
    bucket = os.getenv("GCS_BUCKET")
    if bucket:
        return GCSStorage(bucket, prefix=os.getenv("GCS_PREFIX", ""))
    base = os.getenv("STORAGE_DIR")
    base_path = pathlib.Path(base) if base else pathlib.Path(__file__).parent / "data"
    return LocalStorage(base_path)
