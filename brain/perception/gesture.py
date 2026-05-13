import logging
import math
import time
import os
from typing import Dict, Any, Optional

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    logging.warning("Mediapipe not found. Gesture detection will be disabled.")

class _LandmarkList:
    def __init__(self, lms):
        self.landmark = lms

class _HandsResults:
    def __init__(self, lists):
        self.multi_hand_landmarks = [_LandmarkList(lms) for lms in lists] if lists else []

def _ensure_model(path: str, url: str) -> None:
    try:
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(path):
            import urllib.request
            with urllib.request.urlopen(url, timeout=30) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
    except Exception:
        pass

class GestureDetector:
    def __init__(self):
        self._hands = None
        self._tasks_hand = None
        self._mp_vision = None
        self._gesture_recognizer = None
        self._last_wave: Dict[str, tuple[float, float]] = {}
        self._last_wave_ts = 0.0
        self._sign_seq = []
        self._sign_last = 0.0
        self._sign_rec = _SignAlphabetRecognizer()

    def _ensure(self):
        if not MEDIAPIPE_AVAILABLE:
            return None
            
        if self._hands is not None:
            return self._hands
            
        try:
            sols = getattr(mp, "solutions", None)
            if sols is None:
                try:
                    import mediapipe.solutions as _sols
                    mp.solutions = _sols
                    sols = _sols
                except Exception:
                    try:
                        import mediapipe.python.solutions as _sols_py
                        mp.solutions = _sols_py
                        sols = _sols_py
                    except Exception:
                        sols = None
            if sols is not None:
                self.mp_hands = mp.solutions.hands
                self._hands = self.mp_hands.Hands(
                    static_image_mode=False,
                    max_num_hands=1,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
                return self._hands
        except BaseException as e:
            logging.error(f"Failed to initialize MediaPipe Hands: {e}")
        
        try:
            from mediapipe.tasks import python as mp_python  # type: ignore
            from mediapipe.tasks.python import vision as mp_vision  # type: ignore
            model_dir = os.path.join(os.getcwd(), "data", "mediapipe")
            hand_model = os.path.join(model_dir, "hand_landmarker.task")
            _ensure_model(hand_model, "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task")
            base = mp_python.BaseOptions(model_asset_path=hand_model)
            opts = mp_vision.HandLandmarkerOptions(base_options=base, num_hands=1)
            self._tasks_hand = mp_vision.HandLandmarker.create_from_options(opts)
            self._mp_vision = mp_vision
            return self._tasks_hand
        except BaseException as e:
            logging.error(f"Failed to initialize MediaPipe Tasks Hands: {e}")
            return None
    
    def _ensure_gr(self):
        if self._gesture_recognizer is not None:
            return self._gesture_recognizer
        try:
            from mediapipe.tasks import python as mp_python  # type: ignore
            from mediapipe.tasks.python import vision as mp_vision  # type: ignore
            model_dir = os.path.join(os.getcwd(), "data", "mediapipe")
            gr_model = os.path.join(model_dir, "gesture_recognizer.task")
            _ensure_model(gr_model, "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task")
            base = mp_python.BaseOptions(model_asset_path=gr_model)
            opts = mp_vision.GestureRecognizerOptions(base_options=base, num_hands=1)
            self._gesture_recognizer = mp_vision.GestureRecognizer.create_from_options(opts)
            self._mp_vision = mp_vision
            return self._gesture_recognizer
        except BaseException as e:
            return None
    
    def _map_gesture(self, name: str) -> str:
        m = {
            "Thumb_Up": "نعم",
            "Thumb_Down": "لا",
            "Victory": "حرف V/نصر",
            "ILoveYou": "أحبك",
            "Open_Palm": "كف مفتوح",
            "Closed_Fist": "قبضة",
            "Pointing_Up": "إشارة للأعلى",
        }
        return m.get(name, name)

    def detect(self, frame: Any) -> Optional[Dict[str, str]]:
        """
        Processes a BGR frame and returns simple gesture data used by the planner.
        Returns None or dict with:
        {
            "primary": "wave" | "thumbs_up" | "thumbs_down" | ...
        }
        """
        if frame is None:
            return None
            
        hinst = self._ensure()
        if not hinst:
            return None

        # Convert to RGB
        try:
            try:
                import cv2
                img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception:
                try:
                    import numpy as np
                    if isinstance(frame, np.ndarray) and frame.ndim == 3 and frame.shape[2] == 3:
                        img_rgb = frame[:, :, ::-1].copy()
                    else:
                        return None
                except Exception:
                    return None
            handed = "unknown"
            if self._hands is not None:
                results = self._hands.process(img_rgb)
                if not results or not getattr(results, "multi_hand_landmarks", None):
                    gr = self._ensure_gr()
                    if gr:
                        try:
                            r = gr.recognize(mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb))
                            if r and getattr(r, "gestures", None) and r.gestures:
                                cat = r.gestures[0][0]
                                primary = self._map_gesture(str(getattr(cat, "category_name", "")))
                                if primary:
                                    return {"primary": primary}
                        except BaseException:
                            pass
                    return None
                hand_landmarks = results.multi_hand_landmarks[0]
                if getattr(results, "multi_handedness", None):
                    c = results.multi_handedness[0].classification[0]
                    handed = str(c.label).lower()
                letter = self._sign_rec.classify(hand_landmarks, handed=handed, seq=self._sign_seq)
                if letter:
                    return {"primary": f"حرف: {letter}"}
            elif self._tasks_hand is not None and self._mp_vision is not None:
                img = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
                res = self._tasks_hand.detect(img)
                if not res or not getattr(res, "hand_landmarks", None):
                    gr = self._ensure_gr()
                    if gr:
                        try:
                            r = gr.recognize(img)
                            if r and getattr(r, "gestures", None) and r.gestures:
                                cat = r.gestures[0][0]
                                primary = self._map_gesture(str(getattr(cat, "category_name", "")))
                                if primary:
                                    return {"primary": primary}
                        except BaseException:
                            pass
                    return None
                hand_landmarks = _LandmarkList(res.hand_landmarks[0])
                if getattr(res, "handedness", None):
                    try:
                        c = res.handedness[0].classification[0]
                        handed = str(c.category_name).lower()
                    except Exception:
                        handed = "unknown"
                letter = self._sign_rec.classify(hand_landmarks, handed=handed, seq=self._sign_seq)
                if letter:
                    return {"primary": f"حرف: {letter}"}
            else:
                gr = self._ensure_gr()
                if gr:
                    try:
                        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
                        r = gr.recognize(img)
                        if r and getattr(r, "gestures", None) and r.gestures:
                            cat = r.gestures[0][0]
                            primary = self._map_gesture(str(getattr(cat, "category_name", "")))
                            if primary:
                                return {"primary": primary}
                    except BaseException:
                        pass
                return None
        except Exception as e:
            logging.error(f"MediaPipe process error: {e}")
            return None

        gesture, _ = self._classify(hand_landmarks, handed=handed)
        
        if gesture == "unknown":
            return None
            
        return {
            "primary": gesture
        }

    def close(self) -> None:
        try:
            if self._hands:
                self._hands.close()
        except Exception:
            pass
        self._hands = None
        try:
            if self._tasks_hand:
                self._tasks_hand.close()
        except Exception:
            pass
        self._tasks_hand = None
        try:
            if self._gesture_recognizer:
                self._gesture_recognizer.close()
        except Exception:
            pass
        self._gesture_recognizer = None

class _SignAlphabetRecognizer:
    """ASL alphabet recognizer (all 26 letters) + Arabic sign word detection."""

    def __init__(self):
        self._last_idx = None
        self._path: list[tuple[float, float]] = []
        self._t = 0.0
        self._word_buffer: list[tuple[float, float, float]] = []  # (x, y, timestamp)

    def _finger_states(self, lm: Any) -> dict:
        pts = lm.landmark
        index_up = pts[8].y < pts[6].y
        middle_up = pts[12].y < pts[10].y
        ring_up = pts[16].y < pts[14].y
        pinky_up = pts[20].y < pts[18].y
        thumb_dir = pts[4].x - pts[3].x
        thumb_up = abs(thumb_dir) > 0.04
        # Extra: finger curl ratios for finer discrimination
        index_curl = abs(pts[8].y - pts[5].y)   # tip to mcp
        middle_curl = abs(pts[12].y - pts[9].y)
        ring_curl = abs(pts[16].y - pts[13].y)
        pinky_curl = abs(pts[20].y - pts[17].y)
        thumb_across = pts[4].x < pts[5].x if thumb_dir < 0 else pts[4].x > pts[5].x
        return {
            "thumb": thumb_up, "index": index_up, "middle": middle_up,
            "ring": ring_up, "pinky": pinky_up, "thumb_dir": thumb_dir,
            "index_curl": index_curl, "middle_curl": middle_curl,
            "ring_curl": ring_curl, "pinky_curl": pinky_curl,
            "thumb_across": thumb_across,
        }

    def _distance(self, a: Any, b: Any) -> float:
        dx = a.x - b.x
        dy = a.y - b.y
        return float((dx * dx + dy * dy) ** 0.5)

    def _angle(self, a: Any, b: Any, c: Any) -> float:
        """Angle at point b formed by a-b-c in degrees."""
        import math
        ba = (a.x - b.x, a.y - b.y)
        bc = (c.x - b.x, c.y - b.y)
        dot = ba[0] * bc[0] + ba[1] * bc[1]
        mag_a = math.sqrt(ba[0]**2 + ba[1]**2) or 1e-6
        mag_c = math.sqrt(bc[0]**2 + bc[1]**2) or 1e-6
        cos_angle = max(-1.0, min(1.0, dot / (mag_a * mag_c)))
        return math.degrees(math.acos(cos_angle))

    def _detect_sign_word(self, pts: Any, st: dict, seq: list) -> str | None:
        """Detect common Arabic sign language words via hand trajectory."""
        now = time.time()
        wrist_x, wrist_y = float(pts[0].x), float(pts[0].y)
        self._word_buffer.append((wrist_x, wrist_y, now))
        # Keep last 2 seconds
        self._word_buffer = [(x, y, t) for x, y, t in self._word_buffer if now - t < 2.0]
        if len(self._word_buffer) < 5:
            return None

        xs = [p[0] for p in self._word_buffer]
        ys = [p[1] for p in self._word_buffer]
        dx_total = max(xs) - min(xs)
        dy_total = max(ys) - min(ys)

        # شكراً (Thank you): open palm moves forward from chin
        if st["index"] and st["middle"] and st["ring"] and st["pinky"] and st["thumb"]:
            if dy_total < 0.08 and dx_total < 0.15:
                start_y = self._word_buffer[0][1]
                end_y = self._word_buffer[-1][1]
                if end_y < start_y - 0.03:  # hand moved up (toward camera = forward)
                    return "شكراً"

        # مرحبا (Hello): open palm waving side to side
        if st["index"] and st["middle"] and st["ring"] and st["pinky"]:
            if dx_total > 0.1 and dy_total < 0.08:
                dir_changes = 0
                for i in range(1, len(xs) - 1):
                    if (xs[i] - xs[i-1]) * (xs[i+1] - xs[i]) < 0:
                        dir_changes += 1
                if dir_changes >= 2:
                    return "مرحبا"

        # نعم (Yes): fist nodding down
        if not st["index"] and not st["middle"] and not st["ring"] and not st["pinky"]:
            if dy_total > 0.06 and dx_total < 0.05:
                y_changes = 0
                for i in range(1, len(ys) - 1):
                    if (ys[i] - ys[i-1]) * (ys[i+1] - ys[i]) < 0:
                        y_changes += 1
                if y_changes >= 1:
                    return "نعم"

        # لا (No): index finger wagging side to side
        if st["index"] and not st["middle"] and not st["ring"] and not st["pinky"]:
            if dx_total > 0.08 and dy_total < 0.06:
                dir_changes = 0
                for i in range(1, len(xs) - 1):
                    if (xs[i] - xs[i-1]) * (xs[i+1] - xs[i]) < 0:
                        dir_changes += 1
                if dir_changes >= 2:
                    return "لا"

        # مساعدة (Help): fist on open palm rising
        # أنا (Me): pointing to self (index pointing inward toward chest)
        if st["index"] and not st["middle"] and not st["ring"] and not st["pinky"]:
            tip_x = float(pts[8].x)
            wrist_x_now = float(pts[0].x)
            if abs(tip_x - wrist_x_now) < 0.04 and dy_total < 0.04:
                return "أنا"

        return None

    def classify(self, lm: Any, *, handed: str, seq: list) -> str | None:
        pts = lm.landmark
        st = self._finger_states(lm)
        pinch = self._distance(pts[4], pts[8])

        # ── Try sign word detection first ──
        word = self._detect_sign_word(pts, st, seq)
        if word:
            return word

        # ── ASL Alphabet: all 26 letters ──

        # A: fist with thumb on side
        if not st["index"] and not st["middle"] and not st["ring"] and not st["pinky"] and not st["thumb"]:
            return "A"

        # B: four fingers up, thumb across palm
        if st["index"] and st["middle"] and st["ring"] and st["pinky"] and not st["thumb"]:
            sep_im = abs(pts[8].x - pts[12].x)
            if sep_im < 0.05:
                return "B"

        # C: curved hand (fingers together, thumb apart, like holding a cup)
        if st["thumb"] and st["index"] and st["middle"] and st["ring"] and st["pinky"]:
            curl_avg = (st["index_curl"] + st["middle_curl"] + st["ring_curl"] + st["pinky_curl"]) / 4
            if curl_avg < 0.15 and self._distance(pts[4], pts[8]) > 0.05:
                return "C"

        # D: index up only, no thumb
        if st["index"] and not st["middle"] and not st["ring"] and not st["pinky"] and not st["thumb"]:
            return "D"

        # E: all fingers curled, thumb across
        if not st["index"] and not st["middle"] and not st["ring"] and not st["pinky"] and st["thumb"]:
            if st["thumb_across"]:
                return "E"
            return "S"

        # F: thumb+index pinch, other fingers up
        if pinch < 0.06:
            if st["middle"] and st["ring"] and st["pinky"]:
                return "F"
            if st["middle"] or st["ring"] or st["pinky"]:
                return "F"
            return "O"

        # G: index + thumb pointing sideways
        if st["index"] and not st["middle"] and not st["ring"] and not st["pinky"] and st["thumb"]:
            if abs(pts[8].y - pts[4].y) < 0.06:  # both pointing sideways
                return "G"

        # H: index + middle pointing sideways
        if st["index"] and st["middle"] and not st["ring"] and not st["pinky"] and st["thumb"]:
            if abs(st["thumb_dir"]) < 0.02:
                return "H"
            return "K"

        # I: pinky only up
        if not st["index"] and not st["middle"] and not st["ring"] and st["pinky"] and not st["thumb"]:
            return "I"

        # J: pinky up + downward arc motion (I + motion)
        if not st["index"] and not st["middle"] and not st["ring"] and st["pinky"]:
            seq.append((float(pts[20].x), float(pts[20].y)))
            if len(seq) > 12:
                seq[:] = seq[-12:]
            if len(seq) >= 6:
                dy_sum = sum(seq[i+1][1] - seq[i][1] for i in range(len(seq)-1))
                dx_sum = sum(seq[i+1][0] - seq[i][0] for i in range(len(seq)-1))
                if dy_sum > 0.05 and abs(dx_sum) > 0.03:
                    return "J"
            return "I"

        # K: index + middle + thumb up, middle behind index
        # (handled above with H)

        # L: index + thumb making L shape
        if st["thumb"] and st["index"] and not st["middle"] and not st["ring"] and not st["pinky"]:
            return "L"

        # M: three fingers over thumb (fist, thumb under 3 fingers)
        if not st["index"] and not st["middle"] and not st["ring"] and not st["pinky"]:
            thumb_under = pts[4].y > pts[6].y and pts[4].y > pts[10].y and pts[4].y > pts[14].y
            if thumb_under and self._distance(pts[4], pts[14]) < 0.06:
                return "M"

        # N: two fingers over thumb
        if not st["index"] and not st["middle"] and not st["ring"] and not st["pinky"]:
            thumb_under = pts[4].y > pts[6].y and pts[4].y > pts[10].y
            if thumb_under and self._distance(pts[4], pts[10]) < 0.06:
                return "N"

        # P: like K but pointing down
        if st["index"] and st["middle"] and st["thumb"]:
            if pts[8].y > pts[5].y:  # fingers pointing down
                return "P"

        # Q: like G but pointing down
        if st["index"] and st["thumb"] and not st["middle"]:
            if pts[8].y > pts[5].y and pts[4].y > pts[3].y:
                return "Q"

        # R: index + middle crossed
        if st["index"] and st["middle"] and not st["ring"] and not st["pinky"]:
            cross = abs(pts[8].x - pts[12].x) < 0.02
            if cross:
                return "R"

        # T: thumb between index and middle (fist)
        if not st["index"] and not st["middle"] and not st["ring"] and not st["pinky"]:
            if pts[4].y < pts[6].y and pts[4].y > pts[5].y:
                return "T"

        # U: index + middle up together
        if st["index"] and st["middle"] and not st["ring"] and not st["pinky"] and not st["thumb"]:
            sep = abs(pts[8].x - pts[12].x)
            if sep > 0.06:
                return "V"
            return "U"

        # V: index + middle up apart (handled above)

        # W: index + middle + ring up
        if st["index"] and st["middle"] and st["ring"] and not st["pinky"] and not st["thumb"]:
            return "W"

        # X: index hooked (bent at top joint)
        if not st["middle"] and not st["ring"] and not st["pinky"] and not st["thumb"]:
            if pts[8].y > pts[7].y and pts[7].y < pts[6].y:  # tip below DIP, DIP above PIP
                return "X"

        # Y: thumb + pinky extended
        if st["thumb"] and st["pinky"] and not st["index"] and not st["middle"] and not st["ring"]:
            return "Y"

        # Z: index tracing Z shape (motion-based)
        traj_pt = pts[8]
        seq.append((float(traj_pt.x), float(traj_pt.y)))
        if len(seq) > 15:
            seq[:] = seq[-15:]
        if st["index"] and not st["middle"] and not st["ring"] and not st["pinky"] and not st["thumb"]:
            if len(seq) >= 6:
                dx = [seq[i+1][0] - seq[i][0] for i in range(len(seq)-1)]
                dy = [seq[i+1][1] - seq[i][1] for i in range(len(seq)-1)]
                ch = sum(1 for i in range(len(dx)-1) if (dx[i] * dx[i+1] < 0 or dy[i] * dy[i+1] < 0))
                if ch >= 2 and sum(abs(v) for v in dx + dy) > 0.5:
                    return "Z"

        return None

    def _classify(self, lm: Any, *, handed: str) -> tuple[str, float]:
        pts = lm.landmark
        wrist = pts[0]
        thumb_tip = pts[4]
        index_tip = pts[8]
        middle_tip = pts[12]
        ring_tip = pts[16]
        pinky_tip = pts[20]

        index_pip = pts[6]
        middle_pip = pts[10]
        ring_pip = pts[14]
        pinky_pip = pts[18]

        # Finger states (open/closed)
        index_up = index_tip.y < index_pip.y
        middle_up = middle_tip.y < middle_pip.y
        ring_up = ring_tip.y < ring_pip.y
        pinky_up = pinky_tip.y < pinky_pip.y

        if handed in {"left", "right"}:
            if handed == "right":
                thumb_up = thumb_tip.x < pts[3].x
            else:
                thumb_up = thumb_tip.x > pts[3].x
        else:
            # Fallback simple check
            thumb_up = abs(thumb_tip.x - wrist.x) > 0.05

        extended = {
            "thumb": thumb_up,
            "index": index_up,
            "middle": middle_up,
            "ring": ring_up,
            "pinky": pinky_up,
        }
        ext_count = sum(1 for v in extended.values() if v)

        # Thumbs Up/Down
        if extended["thumb"] and not (extended["index"] or extended["middle"] or extended["ring"] or extended["pinky"]):
            if thumb_tip.y < wrist.y - 0.05:
                return ("thumbs_up", 0.85)
            if thumb_tip.y > wrist.y + 0.05:
                # Basic check, might need refinement for inverted hand
                return ("thumbs_down", 0.85)

        # Pointing
        if extended["index"] and not (extended["middle"] or extended["ring"] or extended["pinky"]):
            return ("pointing", 0.8)

        # Wave / Paper
        if ext_count >= 4:
            if self._is_wave(lm):
                return ("wave", 0.8)
            return ("paper", 0.75) 

        # Rock
        if ext_count <= 1:
            return ("rock", 0.75)

        # Scissors
        if extended["index"] and extended["middle"] and not (extended["ring"] or extended["pinky"]):
            return ("scissors", 0.8)

        return ("unknown", 0.5)

    def _is_wave(self, lm: Any) -> bool:
        now = time.monotonic()
        pts = lm.landmark
        wrist = pts[0]
        key = "wrist"

        prev = self._last_wave.get(key)
        self._last_wave[key] = (float(wrist.x), float(wrist.y))
        if prev is None:
            return False

        dx = abs(float(wrist.x) - float(prev[0]))
        dy = abs(float(wrist.y) - float(prev[1]))
        moved = math.hypot(dx, dy)
        
        # If movement is significant
        if moved < 0.04:
            return False

        # If movement happened recently (oscillating)
        if now - self._last_wave_ts < 0.5:
             # This is a bit simplistic, usually you count oscillations, 
             # but keeping it simple as per original logic copy
            return True
            
        self._last_wave_ts = now
        return True

    def close(self):
        if self._hands:
            self._hands.close()
            self._hands = None
