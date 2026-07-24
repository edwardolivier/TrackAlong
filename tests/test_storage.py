"""LocalStorage backend roundtrip (the GCS backend is exercised only in prod)."""
from storage import LocalStorage


def test_local_storage_roundtrip(tmp_path):
    s = LocalStorage(tmp_path)

    assert s.read_json("routes/u/x.json") is None
    assert s.exists("routes/u/x.json") is False

    s.write_json("routes/u/x.json", {"id": "x", "n": 1})
    assert s.exists("routes/u/x.json") is True
    assert s.read_json("routes/u/x.json") == {"id": "x", "n": 1}

    s.write_json("routes/u/y.json", {"id": "y"})
    listed = s.list("routes/u/")
    assert "routes/u/x.json" in listed and "routes/u/y.json" in listed

    # Listing is scoped by prefix (other users not included).
    s.write_json("routes/other/z.json", {"id": "z"})
    assert s.list("routes/u/") == ["routes/u/x.json", "routes/u/y.json"]

    assert s.delete("routes/u/x.json") is True
    assert s.delete("routes/u/x.json") is False   # already gone
    assert s.read_json("routes/u/x.json") is None
