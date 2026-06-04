"""
Face Recognition Engine — MTCNN + FaceNet Pipeline
=====================================================
Detection  : MTCNN  (Multi-task Cascaded CNN)
             → accurate bounding boxes + 5 facial landmarks
Embedding  : FaceNet (InceptionResnetV1, pretrained on VGGFace2)
             → 512-dim L2-normalised embedding vector
Matching   : Cosine Similarity (NumPy)

Install:
    pip install mtcnn facenet-pytorch torch torchvision opencv-python numpy Pillow

Fallback:
    If MTCNN/FaceNet not installed, automatically falls back to
    OpenCV Haar Cascade + HOG embeddings so the app never crashes.
"""

import cv2
import numpy as np
import base64
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# ─── Lazy-load heavy models (loaded once on first use) ────────────────────────

_mtcnn     = None
_facenet   = None
_device    = None
_USE_MTCNN = None   # None = not attempted yet


def _init_models():
    """Try to load MTCNN + FaceNet. Sets _USE_MTCNN = True/False."""
    global _mtcnn, _facenet, _device, _USE_MTCNN

    if _USE_MTCNN is not None:
        return _USE_MTCNN

    try:
        import torch
        from facenet_pytorch import MTCNN, InceptionResnetV1

        _device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"FaceNet device: {_device}")

        _mtcnn = MTCNN(
            image_size=160,
            margin=20,
            min_face_size=40,
            thresholds=[0.6, 0.7, 0.7],
            factor=0.709,
            post_process=True,
            keep_all=True,
            device=_device
        )

        _facenet = InceptionResnetV1(pretrained='vggface2').eval().to(_device)

        _USE_MTCNN = True
        logger.info("MTCNN + FaceNet (VGGFace2) loaded successfully")

    except ImportError as e:
        logger.warning(f"MTCNN/FaceNet not available ({e}). Using OpenCV fallback.")
        _USE_MTCNN = False

    return _USE_MTCNN


# ─── OpenCV fallback cascades ─────────────────────────────────────────────────

_FACE_CASCADE = None
_EYE_CASCADE  = None

def _get_face_cascade():
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        _FACE_CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
    return _FACE_CASCADE

def _get_eye_cascade():
    global _EYE_CASCADE
    if _EYE_CASCADE is None:
        _EYE_CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )
    return _EYE_CASCADE


# ─── Image Utilities ──────────────────────────────────────────────────────────

def decode_image(image_data: str) -> Optional[np.ndarray]:
    try:
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        img_bytes = base64.b64decode(image_data)
        np_arr    = np.frombuffer(img_bytes, np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.error(f"decode_image: {e}")
        return None

def encode_image(frame: np.ndarray, quality: int = 85) -> str:
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode('utf-8')

def frame_to_thumbnail(frame: np.ndarray, size: Tuple[int,int] = (160,160)) -> str:
    return 'data:image/jpeg;base64,' + encode_image(cv2.resize(frame, size), 70)


# ─── Face Detection ───────────────────────────────────────────────────────────

def detect_faces(frame: np.ndarray) -> List[Tuple[int,int,int,int]]:
    """Detect all faces. Uses MTCNN if available, else Haar Cascade."""
    if _init_models():
        return _detect_mtcnn(frame)
    return _detect_haar(frame)


def _detect_mtcnn(frame: np.ndarray) -> List[Tuple[int,int,int,int]]:
    try:
        from PIL import Image
        rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        boxes, probs = _mtcnn.detect(pil_img)

        if boxes is None:
            return []

        results = []
        for box, prob in zip(boxes, probs):
            if prob is None or prob < 0.75:
                continue
            x1, y1, x2, y2 = [int(v) for v in box]
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(frame.shape[1], x2)
            y2 = min(frame.shape[0], y2)
            w, h = x2 - x1, y2 - y1
            if w > 20 and h > 20:
                results.append((x1, y1, w, h))
        return results

    except Exception as e:
        logger.error(f"MTCNN detect error: {e}")
        return _detect_haar(frame)


def _detect_haar(frame: np.ndarray) -> List[Tuple[int,int,int,int]]:
    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = _get_face_cascade().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(40,40)
    )
    return faces.tolist() if len(faces) > 0 else []


def get_landmarks(frame: np.ndarray, face_box: Tuple) -> Optional[List]:
    """Return 5 MTCNN facial landmarks as (x,y) tuples or None."""
    if not _init_models():
        return None
    try:
        from PIL import Image
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        _, _, landmarks = _mtcnn.detect(Image.fromarray(rgb), landmarks=True)
        if landmarks is not None and len(landmarks) > 0:
            return [(int(p[0]), int(p[1])) for p in landmarks[0]]
    except Exception:
        pass
    return None


# ─── Embedding Generation ─────────────────────────────────────────────────────

def extract_face_embedding(frame: np.ndarray,
                            face_box: Tuple) -> Optional[List[float]]:
    """
    Extract embedding vector from a detected face.
    FaceNet  → 512-dim L2-normalised vector  (when available)
    Fallback → 1024-dim HOG histogram vector
    """
    if _init_models():
        return _embed_facenet(frame, face_box)
    return _embed_hog(frame, face_box)


def _embed_facenet(frame: np.ndarray, face_box: Tuple) -> Optional[List[float]]:
    try:
        import torch
        from PIL import Image

        x, y, w, h = face_box
        margin = int(0.2 * max(w, h))
        x1 = max(0, x - margin);  y1 = max(0, y - margin)
        x2 = min(frame.shape[1], x + w + margin)
        y2 = min(frame.shape[0], y + h + margin)

        face_roi = frame[y1:y2, x1:x2]
        if face_roi.size == 0:
            return None

        rgb     = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb).resize((160, 160))

        # Normalise to [-1, 1]
        img_arr = (np.array(pil_img, dtype=np.float32) / 255.0 - 0.5) / 0.5
        tensor  = (torch.tensor(img_arr)
                       .permute(2, 0, 1)
                       .unsqueeze(0)
                       .to(_device))

        with torch.no_grad():
            emb = _facenet(tensor)
            emb = torch.nn.functional.normalize(emb, p=2, dim=1)

        return emb.squeeze().cpu().numpy().tolist()   # list of 512 floats

    except Exception as e:
        logger.error(f"FaceNet embedding error: {e}")
        return _embed_hog(frame, face_box)


def _embed_hog(frame: np.ndarray, face_box: Tuple) -> Optional[List[float]]:
    x, y, w, h = face_box
    margin = int(0.2 * w)
    x1 = max(0, x-margin);  y1 = max(0, y-margin)
    x2 = min(frame.shape[1], x+w+margin)
    y2 = min(frame.shape[0], y+h+margin)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    gray = cv2.equalizeHist(cv2.cvtColor(cv2.resize(roi,(96,96)), cv2.COLOR_BGR2GRAY))
    return _block_histograms(gray)


def _block_histograms(gray: np.ndarray, blocks: int = 8) -> List[float]:
    h, w   = gray.shape
    bh, bw = h // blocks, w // blocks
    feats  = []
    for i in range(blocks):
        for j in range(blocks):
            block = gray[i*bh:(i+1)*bh, j*bw:(j+1)*bw]
            hist, _ = np.histogram(block.flatten(), bins=16, range=(0,256))
            hist = hist.astype(float)
            n = np.linalg.norm(hist)
            if n > 0: hist /= n
            feats.extend(hist.tolist())
    return feats


# ─── Similarity Matching ──────────────────────────────────────────────────────

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    a, b  = np.array(vec1), np.array(vec2)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def match_face(query_embedding: List[float],
               students_data:   List[dict],
               threshold:       float = 0.70) -> Optional[dict]:
    """
    Compare query against every stored embedding.
    threshold=0.70 tuned for 512-dim FaceNet vectors.
    """
    best_score, best_student = -1.0, None

    for student in students_data:
        stored = student.get('embeddings', [])
        if not stored:
            continue
        max_sim = max(cosine_similarity(query_embedding, e) for e in stored)
        if max_sim > best_score:
            best_score, best_student = max_sim, student

    if best_student and best_score >= threshold:
        return {'student': best_student, 'confidence': best_score}
    return None


# ─── Liveness Checker ─────────────────────────────────────────────────────────

class LivenessChecker:
    """Simple blink-based liveness using eye aspect ratio."""

    EAR_THRESHOLD   = 0.25
    FRAMES_REQUIRED = 2

    def __init__(self):
        self._blink_count = 0
        self._consec      = 0
        self._is_live     = False

    def update(self, frame: np.ndarray, face_box: Tuple) -> dict:
        x, y, w, h  = face_box
        face_gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[y:y+h, x:x+w]
        eyes        = _get_eye_cascade().detectMultiScale(
            face_gray, scaleFactor=1.1, minNeighbors=3, minSize=(20,20)
        )
        eyes_ok = len(eyes) >= 2
        ear     = float(eyes[0][3] / (eyes[0][2] + 1e-6)) if eyes_ok else 0.3

        if eyes_ok and ear < self.EAR_THRESHOLD:
            self._consec += 1
        else:
            if self._consec >= self.FRAMES_REQUIRED:
                self._blink_count += 1
                self._is_live = True
            self._consec = 0

        return {'is_live': self._is_live, 'blink_count': self._blink_count,
                'eyes_detected': eyes_ok, 'ear': ear}

    def reset(self):
        self._blink_count = self._consec = 0
        self._is_live = False


# ─── Drawing ──────────────────────────────────────────────────────────────────

def draw_face_overlay(frame: np.ndarray, face_box: Tuple,
                       label: str = '', confidence: float = 0.0,
                       matched: bool = False) -> np.ndarray:
    x, y, w, h   = face_box
    output       = frame.copy()
    color        = (0, 255, 100) if matched else (0, 200, 255)
    corner_len   = min(w, h) // 4

    for (cx, cy, dx, dy) in [(x,y,1,1),(x+w,y,-1,1),(x,y+h,1,-1),(x+w,y+h,-1,-1)]:
        cv2.line(output, (cx,cy), (cx+dx*corner_len, cy), color, 2)
        cv2.line(output, (cx,cy), (cx, cy+dy*corner_len), color, 2)

    # Draw MTCNN landmarks
    lms = get_landmarks(frame, face_box)
    if lms:
        lm_colors = [(0,200,255),(0,200,255),(0,255,200),(255,150,0),(255,150,0)]
        for (lx, ly), lc in zip(lms, lm_colors):
            cv2.circle(output, (lx, ly), 3, lc, -1)

    if label:
        text  = f"{label}  {confidence*100:.1f}%" if confidence else label
        font  = cv2.FONT_HERSHEY_SIMPLEX
        (tw,_),_ = cv2.getTextSize(text, font, 0.6, 1)
        cv2.rectangle(output, (x, y-30), (x+tw+8, y), color, -1)
        cv2.putText(output, text, (x+4, y-8), font, 0.6, (0,0,0), 1)

    return output


def get_engine_info() -> dict:
    """Which engine is active — call from admin dashboard."""
    active = _init_models()
    return {
        'engine':        'MTCNN + FaceNet (VGGFace2)' if active else 'OpenCV Haar + HOG',
        'embedding_dim': 512 if active else 1024,
        'device':        str(_device) if active and _device else 'cpu',
        'mtcnn_active':  active
    }
