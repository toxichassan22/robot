from types import SimpleNamespace

from brain.perception.gesture import GestureDetector, _LandmarkList


def _pt(x: float, y: float, visibility: float = 1.0):
    return SimpleNamespace(x=x, y=y, visibility=visibility)


def _hand(points: dict[int, tuple[float, float]]) -> _LandmarkList:
    pts = [_pt(0.5, 0.5) for _ in range(21)]
    for idx, xy in points.items():
        pts[idx] = _pt(*xy)
    return _LandmarkList(pts)


def test_detects_two_hand_heart_shortcut():
    detector = GestureDetector()
    left = _hand({
        0: (0.42, 0.72),
        4: (0.49, 0.58),
        8: (0.47, 0.42),
    })
    right = _hand({
        0: (0.58, 0.72),
        4: (0.56, 0.58),
        8: (0.53, 0.42),
    })

    assert detector._detect_two_hand_shortcut([left, right]) == ("heart", 0.9)


def test_detects_single_hand_finger_heart():
    detector = GestureDetector()
    hand = _hand({
        3: (0.46, 0.50),
        4: (0.50, 0.44),
        5: (0.48, 0.55),
        6: (0.48, 0.46),
        8: (0.52, 0.45),
        10: (0.50, 0.45),
        12: (0.50, 0.62),
        14: (0.52, 0.45),
        16: (0.52, 0.62),
        18: (0.54, 0.45),
        20: (0.54, 0.62),
    })

    assert detector._single_hand_shortcut(hand, "right") == ("finger_heart", 0.82)


def test_payload_exposes_sign_alphabet_without_breaking_primary():
    payload = GestureDetector._payload("sign", sign_value="A", hand_count=1)

    assert payload["primary"] == "sign"
    assert payload["sign_alphabet"] == "A"
    assert payload["hand_count"] == 1
