"""Detector-level tests that need no TFLite runtime installed."""

import numpy as np

from noro.detector import BodyPosition, MockDetector, position_from_label


def test_position_from_label_maps_known_labels():
    assert position_from_label("supine") is BodyPosition.SUPINE
    assert position_from_label("SIDE") is BodyPosition.SIDE
    assert position_from_label("supine ") is BodyPosition.SUPINE


def test_position_from_label_unknowns_are_safe():
    # 'empty' or anything unseen must map to UNKNOWN, which resets the
    # trigger instead of firing pulses at an empty bed.
    assert position_from_label("empty") is BodyPosition.UNKNOWN
    assert position_from_label("who-knows") is BodyPosition.UNKNOWN
    assert position_from_label("") is BodyPosition.UNKNOWN


def test_mock_detector_cycles_pattern():
    det = MockDetector(pattern=[BodyPosition.SUPINE, BodyPosition.SIDE])
    assert det.classify(None)[0] is BodyPosition.SUPINE
    assert det.classify(None)[0] is BodyPosition.SIDE
    assert det.classify(None)[0] is BodyPosition.SUPINE


def test_mock_default_pattern_shape():
    det = MockDetector()
    assert len(det._pattern) == 10
    assert len(set(det._pattern)) == 2  # contains both positions


def test_tflite_detector_missing_model_gives_actionable_error(tmp_path):
    import pytest

    from noro.detector import TFLiteDetector

    with pytest.raises(FileNotFoundError, match="train_classifier"):
        TFLiteDetector(
            model_path=tmp_path / "model.tflite",
            labels_path=tmp_path / "labels.txt",
        )
