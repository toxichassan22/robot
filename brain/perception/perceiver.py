from __future__ import annotations

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "2"
os.environ["GLOG_logtostderr"] = "0"

import logging
import math
import threading
import time
from typing import Any

from brain.config import BrainConfig
from brain.perception.camera import Camera
from brain.perception.gesture import GestureDetector
from brain.vision.vlm_client import VLMClient, FallbackVLMClient, build_vlm
from brain.types import PerceptionState

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class UnifiedPerceiver:
    def __init__(self, cfg: BrainConfig):
        self.cfg = cfg
        self.camera: Camera | None = None
        self.gesture: GestureDetector | None = None
        self._face_mesh = None
        self._pose = None
        self._frame_i = 0
        self._schedule_i = 0
        self._cached_motion_detected = False
        self._cached_gestures: dict | None = None
        self._cached_vision_desc: str | None = None
        self._cached_vision_data: dict | None = None
        self._cached_face: dict | None = None
        self._cached_pose: dict | None = None
        self._last_motion_ts = 0.0
        self._last_gesture_ts = 0.0
        self._last_face_ts = 0.0
        self._last_pose_ts = 0.0
        self._vlm_lock = threading.Lock()
        self._vlm_inflight = False
        
        if cfg.gesture_detection_enabled:
            # We assume camera is needed if gesture is enabled, or if we want vision features later
            # For now, let's open camera if gesture is enabled.
            # Parse configured resolution if needed, but Camera defaults are usually fine for Pi Camera
            # We could parse "640x480" from cfg.camera_resolution
            width, height = self._parse_resolution(getattr(cfg, "perf_resolution", None) or cfg.camera_resolution)
            if width and height:
                self.camera = Camera(index=0, width=width, height=height, fps=cfg.camera_fps)
            else:
                self.camera = Camera(index=0, fps=cfg.camera_fps)
            self.gesture = GestureDetector()
        
        self.vlm = build_vlm(cfg)
        self.last_vlm_ts = 0.0
        self.prev_gray = None

    def _vlm_interval_s(self) -> float:
        """Cloud-optimised intervals: faster since no local resource pressure."""
        model = str(getattr(self.cfg, "vlm_model", "") or "").strip().lower()
        if "qwen" in model:
            return 3.0   # was 8s — cloud can handle faster
        return 1.0       # was 2s — cloud can handle faster

    def _run_vlm_request(self, image_bytes: bytes, prompt: str, *, blocking: bool) -> str | None:
        acquired = self._vlm_lock.acquire(blocking=blocking)
        if not acquired:
            return self._cached_vision_desc

        self._vlm_inflight = True
        try:
            desc = self.vlm.analyze_image(
                model=self.cfg.vlm_model,
                image_bytes=image_bytes,
                prompt=prompt,
                device=self.cfg.vlm_device,
            )
            if isinstance(desc, str) and desc.strip():
                self._cached_vision_desc = desc.strip()
            self.last_vlm_ts = time.time()
            return self._cached_vision_desc
        finally:
            self._vlm_inflight = False
            try:
                self._vlm_lock.release()
            except RuntimeError:
                pass

    def _schedule_vlm_request(self, image_bytes: bytes, prompt: str, force: bool = False) -> None:
        now = time.time()
        interval = self._vlm_interval_s()
        
        # If no motion has been detected for a while, slow down even more to save resources
        if not self._cached_motion_detected and (now - self._last_motion_ts) > 5.0:
            interval = 10.0 # Scan every 10s if static
            
        # If forced (e.g. sudden motion or direct request), bypass interval
        if self._vlm_inflight or (not force and (now - self.last_vlm_ts) < interval):
            return
            
        self.last_vlm_ts = now

        def fetch_vlm() -> None:
            try:
                self._run_vlm_request(image_bytes, prompt, blocking=False)
            except Exception as inner_e:
                logging.error(f"VLM analysis threaded failed: {inner_e}")

        threading.Thread(target=fetch_vlm, daemon=True).start()

    @staticmethod
    def _parse_resolution(res: str | None) -> tuple[int | None, int | None]:
        if not isinstance(res, str):
            return (None, None)
        raw = res.strip().lower()
        if not raw:
            return (None, None)
        sep = "x" if "x" in raw else ("*" if "*" in raw else None)
        if not sep:
            return (None, None)
        parts = raw.split(sep)
        if len(parts) != 2:
            return (None, None)
        try:
            w = int(parts[0].strip())
            h = int(parts[1].strip())
        except Exception:
            return (None, None)
        if w <= 0 or h <= 0:
            return (None, None)
        return (w, h)

    def start(self):
        if self.camera:
            self.camera.start()

    def _prepare_vlm_frame(self, frame, scale=0.5):
        if not CV2_AVAILABLE or frame is None or not hasattr(frame, "shape"):
            return frame
        try:
            height = int(frame.shape[0])
            width = int(frame.shape[1])
        except Exception:
            return frame
            
        # Use provided scale if it's smaller than auto-scale
        max_edge = max(height, width)
        target_edge = 384 if "qwen" in str(getattr(self.cfg, "vlm_model", "") or "").lower() else 512
        auto_scale = float(target_edge) / float(max_edge) if max_edge > target_edge else 1.0
        
        final_scale = min(scale, auto_scale)
        if final_scale >= 1.0:
            return frame
            
        new_w = max(1, int(round(width * final_scale)))
        new_h = max(1, int(round(height * final_scale)))
        try:
            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        except Exception:
            return frame

    def describe_now(self, prompt: str | None = None, level: int = 2) -> str | None:
        """
        Level 1: General fast description.
        Level 2: High-resolution focused analysis (Reading, details).
        """
        if not self.camera or not CV2_AVAILABLE:
            return self._cached_vision_desc
        frame = self.camera.get_latest_frame()
        if frame is None:
            return self._cached_vision_desc
            
        try:
            # Scale based on level (Level 2 uses higher res if possible)
            scale = 1.0 if level >= 2 else 0.5
            prepared = self._prepare_vlm_frame(frame, scale=scale)
            
            ret, jpg = cv2.imencode(".jpg", prepared)
            if not ret:
                return self._cached_vision_desc
                
            default_prompt = (
                "Describe the scene simply." if level < 2 else
                "In detail: Describe the person, their clothes, objects they are holding, and any visible text."
            )
            
            desc = self._run_vlm_request(
                jpg.tobytes(),
                prompt or default_prompt,
                blocking=True,
            )
            return desc if desc else self._cached_vision_desc
        except Exception as e:
            logging.error(f"Direct VLM describe_now (Level {level}) failed: {e}")
            return self._cached_vision_desc

    def snapshot_jpeg(self) -> bytes | None:
        if not self.camera or not CV2_AVAILABLE:
            return None
        frame = self.camera.get_latest_frame()
        if frame is None:
            return None
        try:
            ret, jpg = cv2.imencode(".jpg", frame)
            if not ret:
                return None
            return jpg.tobytes()
        except Exception:
            return None

    def stop(self):
        if self.camera:
            self.camera.stop()
        if self.gesture and hasattr(self.gesture, "close"):
            self.gesture.close()
        try:
            if self._face_mesh is not None:
                self._face_mesh.close()
        except Exception:
            pass
        try:
            if self._pose is not None:
                self._pose.close()
        except Exception:
            pass

    def _ensure_face_mesh(self):
        if self._face_mesh is not None:
            return self._face_mesh
        try:
            import mediapipe as mp
        except Exception:
            return None
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
            if sols is None:
                return None
            self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
                refine_landmarks=True,
            )
            return self._face_mesh
        except Exception:
            self._face_mesh = None
            return None

    def _ensure_pose(self):
        if self._pose is not None:
            return self._pose
        try:
            import mediapipe as mp
        except Exception:
            return None
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
            if sols is None:
                return None
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            return self._pose
        except Exception:
            self._pose = None
            return None

    @staticmethod
    def _dist(a: Any, b: Any) -> float:
        try:
            dx = float(a.x) - float(b.x)
            dy = float(a.y) - float(b.y)
            return float(math.sqrt(dx * dx + dy * dy))
        except Exception:
            return 0.0

    @classmethod
    def _eye_aspect_ratio(cls, eye_landmarks: list[Any]) -> float:
        try:
            a = cls._dist(eye_landmarks[1], eye_landmarks[5])
            b = cls._dist(eye_landmarks[2], eye_landmarks[4])
            c = cls._dist(eye_landmarks[0], eye_landmarks[3])
            if c <= 0:
                return 0.0
            return float((a + b) / (2.0 * c))
        except Exception:
            return 0.0

    @staticmethod
    def _head_pose(face_landmarks: Any, img_w: int, img_h: int) -> tuple[float, float, float] | None:
        if img_w <= 0 or img_h <= 0:
            return None
        try:
            import numpy as np
        except Exception:
            return None
        try:
            model_points = np.array(
                [
                    (0.0, 0.0, 0.0),
                    (0.0, -330.0, -65.0),
                    (-225.0, 170.0, -135.0),
                    (225.0, 170.0, -135.0),
                    (-150.0, -150.0, -125.0),
                    (150.0, -150.0, -125.0),
                ],
                dtype="double",
            )
            image_points = np.array(
                [
                    (face_landmarks.landmark[1].x * img_w, face_landmarks.landmark[1].y * img_h),
                    (face_landmarks.landmark[152].x * img_w, face_landmarks.landmark[152].y * img_h),
                    (face_landmarks.landmark[33].x * img_w, face_landmarks.landmark[33].y * img_h),
                    (face_landmarks.landmark[263].x * img_w, face_landmarks.landmark[263].y * img_h),
                    (face_landmarks.landmark[61].x * img_w, face_landmarks.landmark[61].y * img_h),
                    (face_landmarks.landmark[291].x * img_w, face_landmarks.landmark[291].y * img_h),
                ],
                dtype="double",
            )
            focal_length = float(img_w)
            center = (img_w / 2.0, img_h / 2.0)
            camera_matrix = np.array(
                [[focal_length, 0, center[0]], [0, focal_length, center[1]], [0, 0, 1]],
                dtype="double",
            )
            dist_coeffs = np.zeros((4, 1))
            success, rotation_vector, _translation_vector = cv2.solvePnP(
                model_points, image_points, camera_matrix, dist_coeffs
            )
            if not success:
                return None
            rmat, _ = cv2.Rodrigues(rotation_vector)
            angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)
            pitch = float(angles[0] * 360.0)
            yaw = float(angles[1] * 360.0)
            roll = float(angles[2] * 360.0)
            return (pitch, yaw, roll)
        except Exception:
            return None

    @staticmethod
    def _classify_color_name(bgr: Any) -> str | None:
        try:
            b, g, r = float(bgr[0]), float(bgr[1]), float(bgr[2])
        except Exception:
            return None
        brightness = (r + g + b) / 3.0
        spread = max(r, g, b) - min(r, g, b)
        if brightness < 45:
            return "أسود"
        if brightness > 220 and spread < 25:
            return "أبيض"
        if spread < 20:
            return "رمادي" if brightness < 190 else "أبيض"
        if r > 150 and g > 120 and b < 110:
            return "أصفر" if abs(r - g) < 35 else "برتقالي"
        if r > 120 and g > 80 and b < 100:
            return "بني"
        if r > g + 35 and r > b + 35:
            if b > 100 and r - b < 70:
                return "موف"
            if g > 95 and r - g < 50:
                return "وردي"
            return "أحمر"
        if g > r + 25 and g > b + 25:
            return "أخضر"
        if b > r + 25 and b > g + 15:
            return "أزرق"
        if r > 100 and b > 100 and g < 110:
            return "موف"
        if r > 175 and g > 150 and b > 120:
            return "بيج"
        return None

    def _estimate_shirt_color(self, frame: Any, face_landmarks: Any, img_w: int, img_h: int) -> str | None:
        try:
            pts = getattr(face_landmarks, "landmark", None)
            if not pts or img_w <= 0 or img_h <= 0:
                return None
            xs = [float(p.x) for p in pts]
            ys = [float(p.y) for p in pts]
            min_x = max(0, int((min(xs) - 0.12) * img_w))
            max_x = min(img_w, int((max(xs) + 0.12) * img_w))
            face_h = max(1, int((max(ys) - min(ys)) * img_h))
            chest_y0 = min(img_h - 1, int(max(ys) * img_h) + int(face_h * 0.15))
            chest_y1 = min(img_h, chest_y0 + max(24, int(face_h * 1.4)))
            if max_x <= min_x or chest_y1 <= chest_y0:
                return None
            roi = frame[chest_y0:chest_y1, min_x:max_x]
            if roi is None or getattr(roi, "size", 0) == 0:
                return None
            mean_bgr = roi.reshape(-1, 3).mean(axis=0)
            return self._classify_color_name(mean_bgr)
        except Exception:
            return None

    # ── Facial feature ratio helpers ──────────────────────────────────────

    @staticmethod
    def _eyebrow_position(pts: Any) -> tuple[float, float]:
        """Return normalised eyebrow height for left and right brows.

        Uses the vertical distance between brow landmarks and eye top,
        divided by face height (nose tip to forehead) for scale‑invariance.
        Higher value → eyebrows raised higher.
        """
        try:
            # Left eyebrow inner (107) vs left eye top (159), right eyebrow inner (336) vs right eye top (386)
            face_h = max(1e-6, abs(float(pts[10].y) - float(pts[152].y)))  # forehead to chin
            l_brow = (float(pts[159].y) - float(pts[107].y)) / face_h
            r_brow = (float(pts[386].y) - float(pts[336].y)) / face_h
            return (l_brow, r_brow)
        except Exception:
            return (0.0, 0.0)

    @staticmethod
    def _eyebrow_furrow(pts: Any) -> float:
        """Return how close the inner eyebrow ends are (furrowing / frowning).

        Lower value → more furrowed (angry/concentrated).
        """
        try:
            return abs(float(pts[107].x) - float(pts[336].x))
        except Exception:
            return 1.0

    @staticmethod
    def _mouth_corner_angle(pts: Any) -> float:
        """Positive → corners up (smile), negative → corners down (sad).

        Measures vertical offset of mouth corners relative to mouth centre.
        """
        try:
            mid_y = (float(pts[13].y) + float(pts[14].y)) / 2.0
            left_corner_y = float(pts[61].y)
            right_corner_y = float(pts[291].y)
            avg_corner_y = (left_corner_y + right_corner_y) / 2.0
            # Corners *below* mid → positive (smile in image coords is inverted)
            # But in normalised coords, lower y = higher on screen.
            # So corners_y < mid_y means corners are above middle → smile
            return mid_y - avg_corner_y  # positive = smile
        except Exception:
            return 0.0

    @staticmethod
    def _cheek_raise(pts: Any) -> float:
        """Detect cheek raise (Duchenne smile indicator).

        Measures how much the cheek pushes up under the eye.
        """
        try:
            # Distance between lower eye (23 left, 253 right) and cheek (234 left, 454 right)
            l_dist = abs(float(pts[23].y) - float(pts[234].y))
            r_dist = abs(float(pts[253].y) - float(pts[454].y))
            face_h = max(1e-6, abs(float(pts[10].y) - float(pts[152].y)))
            return ((l_dist + r_dist) / 2.0) / face_h
        except Exception:
            return 0.0

    @staticmethod
    def _lip_compression(pts: Any) -> float:
        """How compressed the lips are (thin tight lips = anger/determination).

        Returns ratio of lip thickness to face height. Lower = more compressed.
        """
        try:
            face_h = max(1e-6, abs(float(pts[10].y) - float(pts[152].y)))
            upper_inner = pts[13]
            lower_inner = pts[14]
            upper_outer = pts[0]   # top of upper lip
            lower_outer = pts[17]  # bottom of lower lip
            lip_thickness = abs(float(lower_outer.y) - float(upper_outer.y))
            return lip_thickness / face_h
        except Exception:
            return 0.1

    @staticmethod
    def _nose_wrinkle(pts: Any) -> float:
        """Detect nose wrinkle (disgust indicator).

        Measures compression around nose bridge area.
        """
        try:
            # Distance between nose side landmarks (49 left, 279 right)
            nose_width = abs(float(pts[49].x) - float(pts[279].x))
            # Compare with cheek width
            cheek_width = abs(float(pts[234].x) - float(pts[454].x))
            if cheek_width < 1e-6:
                return 0.0
            return nose_width / cheek_width  # lower ratio when nose scrunched
        except Exception:
            return 0.5

    @staticmethod
    def _upper_lip_raise(pts: Any) -> float:
        """Detect upper lip raise (disgust/sneer).

        Measures how much the upper lip is pulled up toward the nose.
        """
        try:
            face_h = max(1e-6, abs(float(pts[10].y) - float(pts[152].y)))
            nose_bottom = float(pts[2].y)
            upper_lip_top = float(pts[0].y)
            gap = abs(upper_lip_top - nose_bottom) / face_h
            return gap  # smaller = more raised
        except Exception:
            return 0.1

    @staticmethod
    def _generate_face_fingerprint(pts: Any) -> str:
        """Create an Ultra-Dense Fingerprint (40+ ratios) for maximum uniqueness."""
        try:
            # References for normalization
            h = max(1e-6, abs(pts[10].y - pts[152].y)) # Total Height
            w = max(1e-6, abs(pts[234].x - pts[454].x)) # Total Width
            mid_z = pts[1].z # Nose tip Z for relative depth
            
            r = []
            # --- 1. Horizontal Slices (5 ratios) ---
            r.append(abs(pts[103].x - pts[332].x) / w) # Forehead width
            r.append(abs(pts[234].x - pts[454].x) / w) # Cheek width
            r.append(abs(pts[132].x - pts[361].x) / w) # Mid-jaw width
            r.append(abs(pts[172].x - pts[397].x) / w) # Lower-jaw width
            r.append(abs(pts[58].x - pts[288].x) / w)   # Mouth-level width

            # --- 2. Vertical Slices (5 ratios) ---
            r.append(abs(pts[10].y - pts[6].y) / h)    # Forehead to nose bridge
            r.append(abs(pts[6].y - pts[1].y) / h)     # Nose bridge to tip
            r.append(abs(pts[1].y - pts[0].y) / h)     # Nose tip to upper lip
            r.append(abs(pts[0].y - pts[17].y) / h)    # Lip thickness ratio
            r.append(abs(pts[17].y - pts[152].y) / h)  # Lower lip to chin

            # --- 3. Detailed Eye & Brow Geometry (14 ratios) ---
            for i, (p1, p2) in enumerate([(33, 133), (160, 144), (158, 153), (362, 263), (385, 373), (387, 380)]):
                 r.append(abs(pts[p1].x - pts[p2].x) / w) # Eye widths
                 r.append(abs(pts[p1].y - pts[p2].y) / h) # Eye heights
            # Brow distance and heights
            r.append(abs(pts[107].x - pts[336].x) / w)
            r.append(abs(pts[107].y - pts[10].y) / h)

            # --- 4. Nose 3D Structure (8 ratios) ---
            r.append(abs(pts[49].x - pts[279].x) / w)  # Base width
            r.append(abs(pts[1].y - pts[2].y) / h)     # Tip to base vertical
            r.append(abs(pts[1].z - pts[10].z) / h)    # Tip prominence
            r.append(abs(pts[2].z - pts[152].z) / h)   # Base depth
            # Side curvature
            r.append(abs(pts[48].x - pts[1].x) / w)
            r.append(abs(pts[278].x - pts[1].x) / w)
            r.append(abs(pts[48].z - pts[1].z) / h)
            r.append(abs(pts[278].z - pts[1].z) / h)

            # --- 5. Jawline Curvature (8 ratios) ---
            # Sampling 4 points on each side of the jaw
            for p in [132, 172, 58, 152]:
                r.append(abs(pts[p].x - pts[1].x) / w)
                r.append(abs(pts[p].y - pts[1].y) / h)

            # Final fingerprint string with 3-decimal precision
            return "-".join([f"{val:.3f}" for val in r])
        except Exception:
            return "unknown"

    def _classify_emotion(self, pts: Any) -> tuple[str, str, float]:
        """Classify facial expression into detailed emotion.

        Returns (emotion_en, emotion_ar, confidence).
        Uses geometric ratios from Face Mesh 468 landmarks.
        """
        # ── Gather all facial metrics ──
        l_eye_indices = [33, 160, 158, 133, 153, 144]
        r_eye_indices = [362, 385, 387, 263, 373, 380]
        l_eye = [pts[i] for i in l_eye_indices]
        r_eye = [pts[i] for i in r_eye_indices]
        ear_l = self._eye_aspect_ratio(l_eye)
        ear_r = self._eye_aspect_ratio(r_eye)
        avg_ear = (ear_l + ear_r) / 2.0

        mouth_h = self._dist(pts[13], pts[14])
        mouth_w = self._dist(pts[61], pts[291])
        mar = float(mouth_h / mouth_w) if mouth_w > 0 else 0.0

        brow_l, brow_r = self._eyebrow_position(pts)
        avg_brow = (brow_l + brow_r) / 2.0
        brow_furrow = self._eyebrow_furrow(pts)
        corner_angle = self._mouth_corner_angle(pts)
        cheek = self._cheek_raise(pts)
        lip_press = self._lip_compression(pts)
        nose_wr = self._nose_wrinkle(pts)
        upper_lip_r = self._upper_lip_raise(pts)

        eyes_wide = avg_ear > 0.32
        eyes_normal = 0.2 <= avg_ear <= 0.32
        eyes_narrow = 0.0 < avg_ear < 0.2
        eyes_closed = avg_ear > 0 and avg_ear < 0.15
        mouth_open = mar > 0.3
        mouth_wide_open = mar > 0.5
        mouth_closed = mar < 0.15
        smiling = corner_angle > 0.008
        frowning = corner_angle < -0.005
        brows_raised = avg_brow > 0.06
        brows_lowered = avg_brow < 0.02
        brows_furrowed = brow_furrow < 0.08
        cheek_raised = cheek < 0.12
        lips_tight = lip_press < 0.06
        upper_lip_raised = upper_lip_r < 0.04

        # ── Scoring system: each emotion gets a score ──
        scores: dict[str, float] = {}

        # 😊 Happy / مبسوط
        s = 0.0
        if smiling: s += 0.35
        if cheek_raised and smiling: s += 0.20
        if corner_angle > 0.015: s += 0.15
        if not brows_furrowed: s += 0.10
        if eyes_normal: s += 0.10
        if mouth_open and smiling: s += 0.10
        scores["happy"] = s

        # 😂 Laughing / بيضحك
        s = 0.0
        if smiling and mouth_open: s += 0.35
        if mouth_wide_open and smiling: s += 0.25
        if cheek_raised: s += 0.15
        if corner_angle > 0.015: s += 0.15
        if eyes_narrow and smiling: s += 0.10  # squinting from laughter
        scores["laughing"] = s

        # 😢 Sad / حزين
        s = 0.0
        if frowning: s += 0.35
        if corner_angle < -0.01: s += 0.20
        if brows_raised and not smiling: s += 0.15  # inner brow raise
        if not mouth_open: s += 0.10
        if eyes_normal and not smiling: s += 0.10
        if avg_brow > 0.05 and frowning: s += 0.10  # oblique eyebrows
        scores["sad"] = s

        # 😮 Surprised / مندهش
        s = 0.0
        if eyes_wide: s += 0.30
        if brows_raised: s += 0.25
        if mouth_open: s += 0.25
        if avg_ear > 0.35: s += 0.10
        if mar > 0.4: s += 0.10
        scores["surprised"] = s

        # 😠 Angry / زعلان
        s = 0.0
        if brows_lowered: s += 0.25
        if brows_furrowed: s += 0.25
        if lips_tight and not smiling: s += 0.20
        if eyes_narrow and not smiling: s += 0.15
        if not mouth_open: s += 0.10
        if corner_angle < 0: s += 0.05
        scores["angry"] = s

        # 🤢 Disgusted / متقزز
        s = 0.0
        if upper_lip_raised: s += 0.30
        if nose_wr < 0.25: s += 0.25
        if frowning: s += 0.15
        if not mouth_wide_open: s += 0.10
        if brows_lowered: s += 0.10
        if eyes_narrow: s += 0.10
        scores["disgusted"] = s

        # 😨 Fearful / خايف
        s = 0.0
        if eyes_wide: s += 0.30
        if brows_raised: s += 0.25
        if mouth_open and not smiling: s += 0.20
        if avg_ear > 0.33: s += 0.10
        if brow_furrow > 0.10: s += 0.05  # brows apart (not furrowed)
        if lips_tight: s += 0.10
        scores["fearful"] = s

        # 😐 Neutral / عادي
        s = 0.0
        if not smiling and not frowning: s += 0.25
        if eyes_normal: s += 0.20
        if not brows_raised and not brows_lowered: s += 0.20
        if mouth_closed: s += 0.15
        if not eyes_wide: s += 0.10
        if abs(corner_angle) < 0.005: s += 0.10
        scores["neutral"] = s

        # 🤔 Thinking / بيفكر
        s = 0.0
        if eyes_narrow and not smiling and not frowning: s += 0.25
        if brows_furrowed and not brows_lowered: s += 0.25
        if mouth_closed: s += 0.15
        if abs(corner_angle) < 0.008: s += 0.15
        if not eyes_wide: s += 0.10
        if not mouth_open: s += 0.10
        scores["thinking"] = s

        # 😏 Smirking / بيتريق
        s = 0.0
        # Asymmetric smile: one corner up, one neutral/down
        try:
            l_corner = float(pts[61].y)
            r_corner = float(pts[291].y)
            mid_y = (float(pts[13].y) + float(pts[14].y)) / 2.0
            l_smile = mid_y - l_corner
            r_smile = mid_y - r_corner
            asymmetry = abs(l_smile - r_smile)
            if asymmetry > 0.008: s += 0.40
            if (l_smile > 0.005) != (r_smile > 0.005): s += 0.25  # one up one down
        except Exception:
            pass
        if not mouth_open: s += 0.15
        if eyes_normal: s += 0.10
        if not brows_raised: s += 0.10
        scores["smirking"] = s

        # 😴 Sleepy / نعسان
        s = 0.0
        if eyes_closed: s += 0.40
        if avg_ear < 0.18 and avg_ear > 0: s += 0.20
        if not smiling: s += 0.10
        if mouth_closed or (mouth_open and not smiling): s += 0.10
        if not brows_raised: s += 0.10
        if not brows_furrowed: s += 0.10
        scores["sleepy"] = s

        # 😤 Frustrated / محبط
        s = 0.0
        if brows_furrowed: s += 0.25
        if lips_tight: s += 0.20
        if frowning: s += 0.15
        if not eyes_wide: s += 0.10
        if brows_lowered: s += 0.15
        if not mouth_open: s += 0.10
        if corner_angle < -0.003: s += 0.05
        scores["frustrated"] = s

        # 🫣 Shy / مكسوف
        s = 0.0
        if smiling and eyes_narrow: s += 0.30  # smiling with slightly closed eyes
        if corner_angle > 0.005 and corner_angle < 0.015: s += 0.20  # small smile
        if not mouth_open: s += 0.15
        if not brows_raised: s += 0.10
        # Head tilted (checked separately via head pose)
        scores["shy"] = min(s, 0.75)

        # 😕 Confused / محتار
        s = 0.0
        # Asymmetric eyebrows
        brow_asym = abs(brow_l - brow_r)
        if brow_asym > 0.02: s += 0.30
        if not smiling and not frowning: s += 0.15
        if mouth_closed or mar < 0.2: s += 0.15
        if eyes_normal: s += 0.10
        if brows_furrowed: s += 0.15
        scores["confused"] = s

        # Arabic labels
        emotion_labels = {
            "happy": "مبسوط",
            "laughing": "بيضحك",
            "sad": "حزين",
            "surprised": "مندهش",
            "angry": "زعلان",
            "disgusted": "متقزز",
            "fearful": "خايف",
            "neutral": "عادي",
            "thinking": "بيفكر",
            "smirking": "بيتريق",
            "sleepy": "نعسان",
            "frustrated": "محبط",
            "shy": "مكسوف",
            "confused": "محتار",
        }

        # Pick the highest scoring emotion
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = scores[best]

        # Require minimum confidence; fallback to neutral
        if confidence < 0.25:
            best = "neutral"
            confidence = scores["neutral"]

        return (best, emotion_labels.get(best, "عادي"), round(confidence, 2))

    def _extract_face_info(self, face_results: Any, img_w: int, img_h: int, frame: Any | None = None) -> dict | None:
        try:
            mfl = getattr(face_results, "multi_face_landmarks", None)
            if not mfl:
                return None
            face_landmarks = mfl[0]
            pts = face_landmarks.landmark

            # ── Eye metrics ──
            left_eye_indices = [33, 160, 158, 133, 153, 144]
            right_eye_indices = [362, 385, 387, 263, 373, 380]
            l_eye = [pts[i] for i in left_eye_indices]
            r_eye = [pts[i] for i in right_eye_indices]
            ear_l = self._eye_aspect_ratio(l_eye)
            ear_r = self._eye_aspect_ratio(r_eye)
            avg_ear = (ear_l + ear_r) / 2.0
            eyes_closed = bool(avg_ear > 0 and avg_ear < 0.15)

            # ── Face identification & Emotion ──
            face_id = self._generate_face_fingerprint(pts)
            emotion_en, emotion_ar, confidence = self._classify_emotion(pts)

            out: dict[str, Any] = {
                "face_id": face_id,
                "emotion": emotion_ar,
                "emotion_en": emotion_en,
                "emotion_confidence": confidence,
                "eyes_closed": eyes_closed,
                "person_present": True,
            }

            # ── Detailed face metrics for debug / VLM context ──
            mouth_h = self._dist(pts[13], pts[14])
            mouth_w = self._dist(pts[61], pts[291])
            mar = float(mouth_h / mouth_w) if mouth_w > 0 else 0.0
            brow_l, brow_r = self._eyebrow_position(pts)
            out["face_metrics"] = {
                "ear": round(avg_ear, 3),
                "mar": round(mar, 3),
                "brow_l": round(brow_l, 3),
                "brow_r": round(brow_r, 3),
                "mouth_corner": round(self._mouth_corner_angle(pts), 4),
                "cheek_raise": round(self._cheek_raise(pts), 3),
                "lip_press": round(self._lip_compression(pts), 3),
            }

            # ── Appearance (shirt color) ──
            if frame is not None:
                shirt_color = self._estimate_shirt_color(frame, face_landmarks, img_w, img_h)
                if shirt_color:
                    out["appearance"] = {"shirt_color": shirt_color}

            # ── Head pose & attention ──
            hp = self._head_pose(face_landmarks, img_w, img_h)
            if hp:
                pitch, yaw, roll = hp
                out["head_pose"] = {"pitch": int(pitch), "yaw": int(yaw), "roll": int(roll)}
                if abs(yaw) < 15 and abs(pitch) < 15:
                    out["attention"] = "بيبص على الروبوت"
                elif yaw > 15:
                    out["attention"] = "بيبص يمين"
                elif yaw < -15:
                    out["attention"] = "بيبص شمال"
                elif pitch > 15:
                    out["attention"] = "بيبص فوق"
                elif pitch < -15:
                    out["attention"] = "بيبص تحت"

                # Shy detection boost: head tilted + small smile
                if abs(roll) > 10 and emotion_en == "shy":
                    out["emotion_confidence"] = min(1.0, confidence + 0.15)

            return out
        except Exception:
            return None

    def _extract_pose_info(self, pose_results: Any) -> dict | None:
        try:
            pl = getattr(pose_results, "pose_landmarks", None)
            if not pl:
                return None
            lm = getattr(pl, "landmark", None)
            if not lm or len(lm) < 17:
                return None

            nose = lm[0]
            left_wrist = lm[15]
            right_wrist = lm[16]
            left_shoulder = lm[11]
            right_shoulder = lm[12]

            action = None
            if left_wrist.y < nose.y and right_wrist.y < nose.y:
                action = "Arms Raised (Cheering?)"
            elif left_wrist.y < nose.y or right_wrist.y < nose.y:
                action = "Waving/Reaching"

            posture = "Upright"
            try:
                shoulder_slope = float(right_shoulder.y) - float(left_shoulder.y)
                if abs(shoulder_slope) > 0.1:
                    posture = "Leaning Sideways"
            except Exception:
                pass

            out: dict[str, Any] = {"posture": posture}
            if action is not None:
                out["action"] = action
            return out
        except Exception:
            return None

    def perceive(
        self, 
        text: str | None = None, 
        sensors: dict | None = None, 
        run_vision: bool = True, 
        run_gesture: bool = True,
        run_vlm: bool = False
    ) -> PerceptionState:
        vision_data = self._cached_vision_data
        gestures_data = self._cached_gestures
        vision_desc = self._cached_vision_desc
        motion_detected = self._cached_motion_detected
        
        if not run_vision or not CV2_AVAILABLE:
            self.prev_gray = None

        if self.camera and run_vision:

            frame = self.camera.get_latest_frame()
            if frame is None:
                self.prev_gray = None

            if frame is not None:
                self._frame_i += 1
                do_process = True
                frame_skip = getattr(self.cfg, "perf_frame_skip", 0)
                try:
                    frame_skip = int(frame_skip)
                except Exception:
                    frame_skip = 0
                if frame_skip > 1 and (self._frame_i % frame_skip != 0):
                    do_process = False

                schedule = getattr(self.cfg, "perf_mediapipe_schedule", None)
                if not isinstance(schedule, tuple) or not schedule:
                    schedule = ("hands", "idle")
                schedule_item = "idle"
                if do_process:
                    try:
                        schedule_item = schedule[self._schedule_i % len(schedule)]
                    except Exception:
                        schedule_item = "idle"
                    self._schedule_i = (self._schedule_i + 1) % max(1, len(schedule))

                now = time.time()

                if do_process:
                    # 1. Motion Detection (Frame Differencing)
                    if CV2_AVAILABLE:
                        try:
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            gray = cv2.GaussianBlur(gray, (21, 21), 0)

                            motion_detected = False
                            if self.prev_gray is None:
                                self.prev_gray = gray
                            else:
                                frame_delta = cv2.absdiff(self.prev_gray, gray)
                                thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
                                thresh = cv2.dilate(thresh, None, iterations=2)
                                contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                                for c in contours:
                                    if cv2.contourArea(c) < 500:
                                        continue
                                    motion_detected = True
                                    break
                                self.prev_gray = gray
                        except Exception:
                            motion_detected = False
                            self.prev_gray = None
                        self._cached_motion_detected = bool(motion_detected)
                        # Only update motion timestamp when motion is actually detected
                        if motion_detected:
                            self._last_motion_ts = now

                    # 2. Gesture Detection
                    if schedule_item == "hands":
                        if self.gesture and run_gesture:
                            try:
                                gestures_data = self.gesture.detect(frame)
                                self._cached_gestures = gestures_data
                                self._last_gesture_ts = now
                            except Exception as e:
                                logging.error(f"Gesture detection failed: {e}")
                                gestures_data = self._cached_gestures

                    if schedule_item == "face":
                        if run_gesture and CV2_AVAILABLE:
                            try:
                                fm = self._ensure_face_mesh()
                                if fm is not None:
                                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                    res = fm.process(frame_rgb)
                                    img_h = int(frame.shape[0]) if hasattr(frame, "shape") else 0
                                    img_w = int(frame.shape[1]) if hasattr(frame, "shape") else 0
                                    face_info = self._extract_face_info(res, img_w, img_h, frame=frame)
                                    self._cached_face = face_info
                                    self._last_face_ts = now
                            except Exception as e:
                                logging.error(f"Face detection failed: {e}")

                    if schedule_item == "pose":
                        if run_gesture and CV2_AVAILABLE:
                            try:
                                pm = self._ensure_pose()
                                if pm is not None:
                                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                    res = pm.process(frame_rgb)
                                    pose_info = self._extract_pose_info(res)
                                    self._cached_pose = pose_info
                                    self._last_pose_ts = now
                            except Exception as e:
                                logging.error(f"Pose detection failed: {e}")

                    if self._cached_face is not None or self._cached_pose is not None:
                        vision_data = {"face": self._cached_face, "pose": self._cached_pose}
                    else:
                        vision_data = None
                    self._cached_vision_data = vision_data

                if CV2_AVAILABLE and run_vlm:
                    try:
                        prepared = self._prepare_vlm_frame(frame)
                        ret, jpg = cv2.imencode(".jpg", prepared)
                        if ret:
                            # If motion just started, FORCE a VLM scan now!
                            force_scan = motion_detected and not getattr(self, "_prev_motion", False)
                            self._prev_motion = motion_detected
                            
                            self._schedule_vlm_request(
                                jpg.tobytes(),
                                "Provide an exhaustive, unrestricted, and highly detailed analysis of this image: Describe the person's facial expressions, micro-expressions, and emotional state in depth; detail their clothing colors, textures, and any visible logos/text; describe the entire environment including background objects and lighting; and perform a deep OCR scan to transcribe every visible letter, number, or symbol no matter how small, to create a complete world-model for an AI brain.",
                                force=force_scan
                            )
                    except Exception as e:
                        logging.error(f"VLM analysis schedule failed: {e}")
                        vision_desc = self._cached_vision_desc
                        # vlm prompt tuned                                                                                           
                if not do_process:
                    motion_detected = self._cached_motion_detected


        if not run_gesture:
            gestures_data = None
            vision_data = None
        if not run_vlm:
            vision_desc = None
        if not run_vision:
            vision_data = None
            motion_detected = False


        return PerceptionState(
            ts_ms=int(time.time() * 1000),
            text=text,
            vision=vision_data,
            sensors=sensors,
            gestures=gestures_data,
            vision_desc=self._cached_vision_desc, # We pull the desc from cache as it populates in background
            motion_detected=motion_detected,
        )
