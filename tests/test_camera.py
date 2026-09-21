"""FileSource tests: replay of captured nights works on any machine."""

import numpy as np
from PIL import Image

from noro.camera import FileSource


def test_yields_frames_sorted_by_name(tmp_path):
    for name, shade in [("c.jpg", 30), ("a.jpg", 10), ("b.jpg", 20)]:
        Image.fromarray(np.full((24, 32, 3), shade, dtype=np.uint8)).save(tmp_path / name)

    frames = list(FileSource(tmp_path).frames())

    assert [f.name for f in frames] == ["a.jpg", "b.jpg", "c.jpg"]
    assert frames[0].image.shape == (24, 32, 3)
    assert int(frames[0].image.mean()) == 10
    assert all(f.timestamp > 0 for f in frames)


def test_ignores_non_image_files(tmp_path):
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(tmp_path / "x.jpg")
    (tmp_path / "notes.txt").write_text("not an image")
    frames = list(FileSource(tmp_path).frames())
    assert len(frames) == 1
    assert frames[0].name == "x.jpg"


def test_missing_directory_raises(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        FileSource(tmp_path / "nope")


def test_empty_directory_raises_on_iteration(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="no images"):
        list(FileSource(tmp_path).frames())
