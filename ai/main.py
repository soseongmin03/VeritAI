import json
import math
import os
import time
import uuid

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
ANALYSIS_DIR = os.path.join(IMAGES_DIR, "analysis")
FACE_CROP_DIR = os.path.join(IMAGES_DIR, "faces")
OVERLAY_DIR = os.path.join(ANALYSIS_DIR, "overlays")
ANCHOR_MAP_DIR = os.path.join(ANALYSIS_DIR, "anchor_maps")
METADATA_DIR = os.path.join(ANALYSIS_DIR, "metadata")
RESPONSE_MAP_DIR = os.path.join(ANALYSIS_DIR, "response_maps")
EYE_RESPONSE_DIR = os.path.join(RESPONSE_MAP_DIR, "eyes")
NOSE_RESPONSE_DIR = os.path.join(RESPONSE_MAP_DIR, "nose")
MOUTH_RESPONSE_DIR = os.path.join(RESPONSE_MAP_DIR, "mouth")
for directory in (
    IMAGES_DIR,
    ANALYSIS_DIR,
    FACE_CROP_DIR,
    OVERLAY_DIR,
    ANCHOR_MAP_DIR,
    METADATA_DIR,
    RESPONSE_MAP_DIR,
    EYE_RESPONSE_DIR,
    NOSE_RESPONSE_DIR,
    MOUTH_RESPONSE_DIR,
):
    os.makedirs(directory, exist_ok=True)

CASCADE_BASE = cv2.data.haarcascades
FACE_CASCADES = {
    "frontal": cv2.CascadeClassifier(os.path.join(CASCADE_BASE, "haarcascade_frontalface_default.xml")),
    "frontal_alt": cv2.CascadeClassifier(os.path.join(CASCADE_BASE, "haarcascade_frontalface_alt2.xml")),
    "profile": cv2.CascadeClassifier(os.path.join(CASCADE_BASE, "haarcascade_profileface.xml")),
}
REGION_COLORS = {
    "forehead": (78, 121, 255),
    "left_eye_zone": (92, 200, 255),
    "right_eye_zone": (92, 200, 255),
    "nose": (60, 214, 196),
    "mouth": (92, 112, 255),
    "jaw": (255, 189, 89),
}
TRAINING_POINT_ORDER = [
    "forehead_center",
    "left_eye_center",
    "right_eye_center",
    "nose_bridge_top",
    "nose_tip",
    "mouth_left",
    "mouth_center",
    "mouth_right",
    "chin",
]
POINT_LABELS = {
    "forehead_center": "F",
    "left_eye_center": "LE",
    "right_eye_center": "RE",
    "nose_bridge_top": "NB",
    "nose_tip": "NT",
    "mouth_left": "ML",
    "mouth_center": "MC",
    "mouth_right": "MR",
    "chin": "C",
}


def normalize_path(path):
    return path.replace("\\", "/")


def decode_image(contents: bytes):
    np_arr = np.frombuffer(contents, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    blurred = cv2.GaussianBlur(equalized, (5, 5), 0)
    grad_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    return {"gray": gray, "equalized": equalized, "blurred": blurred, "gradX": grad_x, "gradY": grad_y}


def make_debug_paths():
    uid = uuid.uuid4().hex[:12]
    return uid, {
        "overlay": os.path.join(OVERLAY_DIR, f"{uid}_overlay.jpg"),
        "analysisMap": os.path.join(ANCHOR_MAP_DIR, f"{uid}_analysis.jpg"),
        "eyeResponse": os.path.join(EYE_RESPONSE_DIR, f"{uid}_eye_response.jpg"),
        "noseResponse": os.path.join(NOSE_RESPONSE_DIR, f"{uid}_nose_response.jpg"),
        "mouthResponse": os.path.join(MOUTH_RESPONSE_DIR, f"{uid}_mouth_response.jpg"),
        "metadata": os.path.join(METADATA_DIR, f"{uid}_analysis.json"),
    }


def expand_box(box, image_shape, scale=0.18):
    x, y, w, h = box
    pad_w = int(w * scale)
    pad_h = int(h * scale)
    x1 = max(x - pad_w, 0)
    y1 = max(y - pad_h, 0)
    x2 = min(x + w + pad_w, image_shape[1])
    y2 = min(y + h + pad_h, image_shape[0])
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))


def calculate_iou(box1, box2):
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    xa = max(x1, x2)
    ya = max(y1, y2)
    xb = min(x1 + w1, x2 + w2)
    yb = min(y1 + h1, y2 + h2)
    inter_w = max(0, xb - xa)
    inter_h = max(0, yb - ya)
    intersection = inter_w * inter_h
    union = w1 * h1 + w2 * h2 - intersection
    if union <= 0:
        return 0.0
    return intersection / float(union)


def non_max_suppression(candidates, iou_threshold=0.35):
    if not candidates:
        return []
    remaining = sorted(candidates, key=lambda item: item["score"], reverse=True)
    selected = []
    while remaining:
        current = remaining.pop(0)
        selected.append(current)
        remaining = [candidate for candidate in remaining if calculate_iou(current["box"], candidate["box"]) < iou_threshold]
    return selected


def normalize_weight(weight, fallback=0.58):
    if weight is None:
        return fallback
    clamped = max(float(weight), 0.0)
    return float(max(0.0, min(1.0, 1.0 - math.exp(-clamped / 10.0))))


def normalize_response(response):
    response = response.astype(np.float32)
    response -= float(np.min(response))
    max_value = float(np.max(response))
    if max_value > 1e-6:
        response /= max_value
    return response


def detect_with_cascade(cascade, image, flipped=False):
    if cascade.empty():
        return []
    min_size = (max(40, image.shape[1] // 16), max(40, image.shape[0] // 16))
    try:
        boxes, _, weights = cascade.detectMultiScale3(
            image, scaleFactor=1.08, minNeighbors=5, minSize=min_size, outputRejectLevels=True
        )
        weight_list = list(weights) if weights is not None else []
    except Exception:
        boxes = cascade.detectMultiScale(image, scaleFactor=1.08, minNeighbors=5, minSize=min_size)
        weight_list = []
    image_width = image.shape[1]
    candidates = []
    for index, (x, y, w, h) in enumerate(boxes):
        if w < 40 or h < 40:
            continue
        if flipped:
            x = image_width - (x + w)
        weight = weight_list[index] if index < len(weight_list) else None
        candidates.append({"box": (int(x), int(y), int(w), int(h)), "rawWeight": None if weight is None else float(weight)})
    return candidates


def detect_faces(preprocessed):
    image = preprocessed["equalized"]
    flipped = cv2.flip(image, 1)
    candidates = []
    for detector_name, cascade in FACE_CASCADES.items():
        if detector_name == "profile":
            boxes = detect_with_cascade(cascade, image) + detect_with_cascade(cascade, flipped, flipped=True)
        else:
            boxes = detect_with_cascade(cascade, image)
        for candidate in boxes:
            candidate["detector"] = detector_name
            candidate["score"] = normalize_weight(candidate["rawWeight"], fallback=0.62 if detector_name.startswith("frontal") else 0.55)
            candidates.append(candidate)
    return non_max_suppression(candidates, iou_threshold=0.28)


def build_eye_response(face_gray):
    h, w = face_gray.shape[:2]
    upper = face_gray[: max(int(h * 0.52), 1), :]
    blackhat = cv2.morphologyEx(upper, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 5)))
    grad_x = normalize_response(np.abs(cv2.Sobel(upper, cv2.CV_32F, 1, 0, ksize=3)))
    dark = normalize_response(blackhat)
    x_coords = np.linspace(0.0, 1.0, w, dtype=np.float32)
    y_coords = np.linspace(0.0, 1.0, upper.shape[0], dtype=np.float32)
    x_prior = 1.0 - np.abs(x_coords - 0.5) * 0.75
    y_prior = 1.0 - np.abs(y_coords - 0.42) / 0.42
    prior = np.clip(np.outer(y_prior, x_prior), 0.0, 1.0)
    response = normalize_response((0.58 * dark + 0.42 * grad_x) * prior)
    full_map = np.zeros_like(face_gray, dtype=np.float32)
    full_map[: upper.shape[0], :] = response
    return full_map


def build_nose_response(face_gray):
    h, w = face_gray.shape[:2]
    y1 = int(h * 0.20)
    y2 = max(y1 + 1, int(h * 0.82))
    mid = face_gray[y1:y2, :]
    tophat = cv2.morphologyEx(mid, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    vertical = normalize_response(np.abs(cv2.Sobel(mid, cv2.CV_32F, 0, 1, ksize=3)))
    bright = normalize_response(mid.astype(np.float32))
    x_coords = np.linspace(0.0, 1.0, w, dtype=np.float32)
    y_coords = np.linspace(0.0, 1.0, mid.shape[0], dtype=np.float32)
    x_prior = 1.0 - np.abs(x_coords - 0.5) / 0.5
    y_prior = 1.0 - np.abs(y_coords - 0.60) / 0.60
    prior = np.clip(np.outer(y_prior, x_prior), 0.0, 1.0)
    response = normalize_response((0.45 * normalize_response(tophat) + 0.30 * bright + 0.25 * vertical) * prior)
    full_map = np.zeros_like(face_gray, dtype=np.float32)
    full_map[y1:y2, :] = response
    return full_map


def build_mouth_response(face_gray):
    h, w = face_gray.shape[:2]
    y1 = int(h * 0.58)
    y2 = max(y1 + 1, int(h * 0.92))
    lower = face_gray[y1:y2, :]
    blackhat = cv2.morphologyEx(lower, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5)))
    horizontal = normalize_response(np.abs(cv2.Sobel(lower, cv2.CV_32F, 1, 0, ksize=3)))
    dark = normalize_response(blackhat)
    x_coords = np.linspace(0.0, 1.0, w, dtype=np.float32)
    y_coords = np.linspace(0.0, 1.0, lower.shape[0], dtype=np.float32)
    x_prior = 1.0 - np.abs(x_coords - 0.5) / 0.65
    y_prior = 1.0 - np.abs(y_coords - 0.52) / 0.52
    prior = np.clip(np.outer(y_prior, x_prior), 0.0, 1.0)
    response = normalize_response((0.64 * dark + 0.36 * horizontal) * prior)
    full_map = np.zeros_like(face_gray, dtype=np.float32)
    full_map[y1:y2, :] = response
    return full_map


def contour_boxes(response_map, threshold=0.46):
    thresholded = np.uint8(np.clip(response_map * 255.0, 0, 255))
    _, binary = cv2.threshold(thresholded, int(255 * threshold), 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [cv2.boundingRect(contour) for contour in contours]


def mean_response(response_map, box):
    x, y, w, h = box
    roi = response_map[y : y + h, x : x + w]
    if roi.size == 0:
        return 0.0
    return float(np.mean(roi))


def detect_eye_candidates(face_gray):
    response_map = build_eye_response(face_gray)
    h, w = face_gray.shape[:2]
    candidates = []
    for x, y, bw, bh in contour_boxes(response_map, threshold=0.42):
        if bw < max(10, w // 12) or bh < max(4, h // 28) or y > int(h * 0.56):
            continue
        aspect = bw / float(max(bh, 1))
        area_ratio = (bw * bh) / float(max(w * h, 1))
        if aspect < 1.2 or aspect > 6.5 or area_ratio < 0.003 or area_ratio > 0.08:
            continue
        cx = x + bw / 2.0
        cy = y + bh / 2.0
        x_center_score = max(0.0, 1.0 - abs(cx / max(w, 1) - 0.5) / 0.5)
        y_center_score = max(0.0, 1.0 - abs(cy / max(h, 1) - 0.38) / 0.24)
        darkness_score = mean_response(response_map, (x, y, bw, bh))
        shape_score = max(0.0, 1.0 - abs(aspect - 2.8) / 3.5)
        confidence = float(max(0.0, min(1.0, 0.45 * darkness_score + 0.25 * shape_score + 0.20 * y_center_score + 0.10 * x_center_score)))
        candidates.append({"box": (int(x), int(y), int(bw), int(bh)), "center": (float(cx), float(cy)), "confidence": confidence, "aspect": float(aspect), "reason": f"eye_response={darkness_score:.3f}, aspect={aspect:.2f}"})
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    return response_map, candidates


def select_eye_configuration(face_gray, candidates):
    h, w = face_gray.shape[:2]
    if not candidates:
        return [], 0.0, "no-eye-candidate"
    best_pair = None
    best_pair_score = 0.0
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            first, second = candidates[i], candidates[j]
            left, right = sorted([first, second], key=lambda item: item["center"][0])
            horizontal_gap = (right["center"][0] - left["center"][0]) / max(w, 1)
            vertical_gap = abs(right["center"][1] - left["center"][1]) / max(h, 1)
            left_area = left["box"][2] * left["box"][3]
            right_area = right["box"][2] * right["box"][3]
            size_ratio = min(left_area, right_area) / max(left_area, right_area, 1)
            pair_score = 0.40 * (left["confidence"] + right["confidence"]) / 2.0 + 0.20 * size_ratio + 0.25 * max(0.0, 1.0 - abs(horizontal_gap - 0.32) / 0.25) + 0.15 * max(0.0, 1.0 - vertical_gap / 0.15)
            if pair_score > best_pair_score:
                best_pair = [left, right]
                best_pair_score = pair_score
    if best_pair is not None and best_pair_score >= 0.45:
        return best_pair, float(min(1.0, best_pair_score)), "pair-detected"
    best_single = candidates[0]
    return [best_single], float(best_single["confidence"]), "single-eye-detected"


def build_face_edge_profile(face_gray):
    edges = cv2.Canny(face_gray, 60, 140)
    h, w = face_gray.shape[:2]
    left_energy = float(np.count_nonzero(edges[:, : w // 2])) / max(1, (w // 2) * h)
    right_energy = float(np.count_nonzero(edges[:, w // 2 :])) / max(1, (w - w // 2) * h)
    edge_density = float(np.count_nonzero(edges)) / float(max(edges.size, 1))
    return {
        "leftEnergy": left_energy,
        "rightEnergy": right_energy,
        "edgeDensity": edge_density,
    }


def classify_pose(eye_selection, eye_quality, face_gray, edge_profile=None):
    if edge_profile is None:
        edge_profile = build_face_edge_profile(face_gray)
    left_energy = edge_profile["leftEnergy"]
    right_energy = edge_profile["rightEnergy"]
    asymmetry = right_energy - left_energy
    if len(eye_selection) >= 2:
        avg_aspect = sum(eye["aspect"] for eye in eye_selection) / len(eye_selection)
        avg_conf = sum(eye["confidence"] for eye in eye_selection) / len(eye_selection)
        if avg_aspect >= 3.6 and avg_conf < 0.72:
            return "eyes_closed", 0.62 + min(0.20, avg_aspect / 10.0), "paired-flat-eye-structures"
        symmetry_gap = abs(eye_selection[0]["center"][1] - eye_selection[1]["center"][1]) / max(face_gray.shape[0], 1)
        if symmetry_gap < 0.10:
            return "frontal", min(1.0, 0.55 + eye_quality * 0.40), "paired-eye-symmetry"
        return "occluded", 0.48, "paired-eyes-but-low-symmetry"
    if len(eye_selection) == 1:
        eye_x = eye_selection[0]["center"][0] / max(face_gray.shape[1], 1)
        if eye_x >= 0.5:
            return "profile-left", 0.58 + eye_quality * 0.25, "single-eye-right-half"
        return "profile-right", 0.58 + eye_quality * 0.25, "single-eye-left-half"
    if asymmetry > 0.010:
        return "profile-left", 0.46, "edge-energy-right-dominant"
    if asymmetry < -0.010:
        return "profile-right", 0.46, "edge-energy-left-dominant"
    return "occluded", 0.38, "insufficient-eye-evidence"


def make_keypoint(name, point, source, confidence, reason):
    return {"name": name, "x": int(point[0]), "y": int(point[1]), "source": source, "confidence": round(float(max(0.0, min(1.0, confidence))), 4), "reason": reason}


def point_xy(keypoint):
    return int(keypoint["x"]), int(keypoint["y"])


def estimate_point(bbox, rx, ry):
    x, y, w, h = bbox
    px = clamp(int(round(x + w * rx)), x, x + w)
    py = clamp(int(round(y + h * ry)), y, y + h)
    return px, py


def global_box(local_box, bbox):
    x, y, _, _ = bbox
    lx, ly, lw, lh = local_box
    return {"x": int(x + lx), "y": int(y + ly), "w": int(lw), "h": int(lh)}


def detect_nose_keypoints(face_gray, bbox, pose):
    response_map = build_nose_response(face_gray)
    h, w = face_gray.shape[:2]
    row_start = int(h * 0.34)
    row_end = max(row_start + 1, int(h * 0.80))
    rows = response_map[row_start:row_end, :]
    if rows.size == 0:
        rows = response_map
        row_start = 0
    y_indices, x_indices = np.indices(rows.shape)
    center_prior = 1.0 - np.abs((x_indices / max(w - 1, 1)) - 0.5) / 0.5
    if pose == "profile-left":
        center_prior = 0.35 + 0.65 * (x_indices / max(w - 1, 1))
    elif pose == "profile-right":
        center_prior = 0.35 + 0.65 * (1.0 - (x_indices / max(w - 1, 1)))
    weighted = rows * np.clip(center_prior, 0.0, 1.0)
    best_index = int(np.argmax(weighted))
    tip_rel_y, tip_x = np.unravel_index(best_index, weighted.shape)
    tip_y = tip_rel_y + row_start
    tip_conf = float(rows[tip_rel_y, tip_x])
    bridge_x = tip_x
    bridge_y = max(int(h * 0.42), 0)
    bridge_roi = response_map[max(0, bridge_y - 2) : min(h, bridge_y + 3), max(0, tip_x - 2) : min(w, tip_x + 3)]
    bridge_conf = float(np.mean(bridge_roi)) if bridge_roi.size else 0.0
    nose_tip = make_keypoint(
        "nose_tip",
        estimate_point(bbox, tip_x / max(w, 1), tip_y / max(h, 1)),
        "detected" if tip_conf >= 0.24 else "estimated",
        tip_conf if tip_conf >= 0.24 else 0.42,
        f"nose_response_tip={tip_conf:.3f}, pose={pose}",
    )
    bridge_source = "detected" if bridge_conf >= 0.18 else "estimated"
    nose_bridge_top = make_keypoint(
        "nose_bridge_top",
        estimate_point(bbox, bridge_x / max(w, 1), bridge_y / max(h, 1)),
        bridge_source,
        bridge_conf if bridge_source == "detected" else 0.38,
        f"nose_bridge_response={bridge_conf:.3f}",
    )
    return response_map, nose_bridge_top, nose_tip


def detect_mouth_keypoints(face_gray, bbox, pose):
    response_map = build_mouth_response(face_gray)
    h, w = face_gray.shape[:2]
    boxes = contour_boxes(response_map, threshold=0.40)
    best = None
    best_score = 0.0
    for local_box in boxes:
        x, y, bw, bh = local_box
        if bw < max(16, w // 8) or bh < max(4, h // 30):
            continue
        aspect = bw / float(max(bh, 1))
        area_ratio = (bw * bh) / float(max(w * h, 1))
        if aspect < 1.3 or aspect > 9.0 or area_ratio < 0.006 or area_ratio > 0.14:
            continue
        cx = x + bw / 2.0
        cy = y + bh / 2.0
        x_score = max(0.0, 1.0 - abs(cx / max(w, 1) - 0.5) / 0.55)
        y_score = max(0.0, 1.0 - abs(cy / max(h, 1) - 0.77) / 0.25)
        response_score = mean_response(response_map, local_box)
        shape_score = max(0.0, 1.0 - abs(aspect - 3.0) / 4.0)
        score = 0.45 * response_score + 0.25 * x_score + 0.15 * y_score + 0.15 * shape_score
        if score > best_score:
            best = local_box
            best_score = score
    if best is None:
        return (
            response_map,
            None,
            make_keypoint("mouth_left", estimate_point(bbox, 0.34, 0.77), "estimated", 0.24, "fallback-mouth-left"),
            make_keypoint("mouth_center", estimate_point(bbox, 0.50, 0.77), "estimated", 0.28, "fallback-mouth-center"),
            make_keypoint("mouth_right", estimate_point(bbox, 0.66, 0.77), "estimated", 0.24, "fallback-mouth-right"),
        )
    x, y, bw, bh = best
    center = estimate_point(bbox, (x + bw / 2.0) / max(w, 1), (y + bh / 2.0) / max(h, 1))
    left = estimate_point(bbox, x / max(w, 1), (y + bh / 2.0) / max(h, 1))
    right = estimate_point(bbox, (x + bw) / max(w, 1), (y + bh / 2.0) / max(h, 1))
    mouth_center = make_keypoint("mouth_center", center, "detected", best_score, f"mouth_response={best_score:.3f}")
    left_source = "detected" if pose in {"frontal", "eyes_closed", "occluded"} else "estimated"
    right_source = left_source
    if pose == "profile-left":
        left_source = "estimated"
    if pose == "profile-right":
        right_source = "estimated"
    mouth_left = make_keypoint("mouth_left", left, left_source, best_score * (0.88 if left_source == "detected" else 0.42), f"mouth_left_from_blob={left_source}")
    mouth_right = make_keypoint("mouth_right", right, right_source, best_score * (0.88 if right_source == "detected" else 0.42), f"mouth_right_from_blob={right_source}")
    return response_map, best, mouth_left, mouth_center, mouth_right


def build_keypoints(bbox, pose, eye_selection, nose_bridge_top, nose_tip, mouth_left, mouth_center, mouth_right):
    keypoints = {}
    if len(eye_selection) >= 2:
        left_eye, right_eye = sorted(eye_selection, key=lambda item: item["center"][0])
        keypoints["left_eye_center"] = make_keypoint("left_eye_center", estimate_point(bbox, left_eye["center"][0] / bbox[2], left_eye["center"][1] / bbox[3]), "detected", left_eye["confidence"], left_eye["reason"])
        keypoints["right_eye_center"] = make_keypoint("right_eye_center", estimate_point(bbox, right_eye["center"][0] / bbox[2], right_eye["center"][1] / bbox[3]), "detected", right_eye["confidence"], right_eye["reason"])
    elif len(eye_selection) == 1:
        only_eye = eye_selection[0]
        detected_eye = make_keypoint("detected_eye", estimate_point(bbox, only_eye["center"][0] / bbox[2], only_eye["center"][1] / bbox[3]), "detected", only_eye["confidence"], only_eye["reason"])
        if pose == "profile-left":
            keypoints["left_eye_center"] = make_keypoint("left_eye_center", estimate_point(bbox, 0.34, 0.40), "estimated", 0.24, "profile-left-hidden-eye")
            keypoints["right_eye_center"] = {**detected_eye, "name": "right_eye_center"}
        else:
            keypoints["left_eye_center"] = {**detected_eye, "name": "left_eye_center"}
            keypoints["right_eye_center"] = make_keypoint("right_eye_center", estimate_point(bbox, 0.66, 0.40), "estimated", 0.24, "profile-right-hidden-eye")
    else:
        keypoints["left_eye_center"] = make_keypoint("left_eye_center", estimate_point(bbox, 0.34, 0.40), "estimated", 0.18, "no-eye-detection")
        keypoints["right_eye_center"] = make_keypoint("right_eye_center", estimate_point(bbox, 0.66, 0.40), "estimated", 0.18, "no-eye-detection")

    keypoints["nose_bridge_top"] = nose_bridge_top
    keypoints["nose_tip"] = nose_tip
    keypoints["mouth_left"] = mouth_left
    keypoints["mouth_center"] = mouth_center
    keypoints["mouth_right"] = mouth_right

    forehead_center = estimate_point(bbox, 0.50, 0.10)
    chin = estimate_point(bbox, 0.50, 0.96)
    if pose == "profile-left":
        forehead_center = estimate_point(bbox, 0.56, 0.12)
        chin = estimate_point(bbox, 0.48, 0.96)
    elif pose == "profile-right":
        forehead_center = estimate_point(bbox, 0.44, 0.12)
        chin = estimate_point(bbox, 0.52, 0.96)
    keypoints["forehead_center"] = make_keypoint("forehead_center", forehead_center, "estimated", 0.36, f"{pose}-forehead-template")
    keypoints["chin"] = make_keypoint("chin", chin, "estimated", 0.34, f"{pose}-chin-template")
    stabilize_profile_keypoints(bbox, pose, keypoints)
    return keypoints


def stabilize_profile_keypoints(bbox, pose, keypoints):
    if pose not in {"profile-left", "profile-right"}:
        return

    x, y, w, h = bbox
    nose_tip_x = keypoints["nose_tip"]["x"]
    mouth_center_x = keypoints["mouth_center"]["x"]
    visible_side = "right" if pose == "profile-left" else "left"

    if visible_side == "right":
        keypoints["right_eye_center"]["x"] = clamp(keypoints["right_eye_center"]["x"], int(x + w * 0.48), x + w)
        keypoints["left_eye_center"]["x"] = clamp(keypoints["left_eye_center"]["x"], x, int(x + w * 0.44))
        keypoints["mouth_right"]["x"] = max(keypoints["mouth_right"]["x"], mouth_center_x)
        keypoints["mouth_left"]["x"] = min(keypoints["mouth_left"]["x"], mouth_center_x - max(4, int(w * 0.06)))
        keypoints["nose_bridge_top"]["x"] = max(keypoints["nose_bridge_top"]["x"], int((nose_tip_x + keypoints["right_eye_center"]["x"]) / 2))
    else:
        keypoints["left_eye_center"]["x"] = clamp(keypoints["left_eye_center"]["x"], x, int(x + w * 0.52))
        keypoints["right_eye_center"]["x"] = clamp(keypoints["right_eye_center"]["x"], int(x + w * 0.56), x + w)
        keypoints["mouth_left"]["x"] = min(keypoints["mouth_left"]["x"], mouth_center_x)
        keypoints["mouth_right"]["x"] = max(keypoints["mouth_right"]["x"], mouth_center_x + max(4, int(w * 0.06)))
        keypoints["nose_bridge_top"]["x"] = min(keypoints["nose_bridge_top"]["x"], int((nose_tip_x + keypoints["left_eye_center"]["x"]) / 2))

    keypoints["mouth_center"]["y"] = clamp(keypoints["mouth_center"]["y"], int(y + h * 0.68), int(y + h * 0.86))
    keypoints["nose_tip"]["y"] = clamp(keypoints["nose_tip"]["y"], int(y + h * 0.48), int(y + h * 0.74))
    keypoints["chin"]["y"] = max(keypoints["chin"]["y"], int(y + h * 0.88))


def compute_noise_score(face_gray):
    denoised = cv2.GaussianBlur(face_gray, (5, 5), 0)
    residual = cv2.absdiff(face_gray, denoised)
    return float(np.mean(residual) / 255.0)


def distance(point_a, point_b):
    return math.sqrt((point_a["x"] - point_b["x"]) ** 2 + (point_a["y"] - point_b["y"]) ** 2)


def compute_deepfake_features(face_gray, bbox, keypoints, pose_label, eye_selection, edge_density):
    w = max(float(bbox[2]), 1.0)
    h = max(float(bbox[3]), 1.0)
    left_eye = keypoints["left_eye_center"]
    right_eye = keypoints["right_eye_center"]
    nose_tip = keypoints["nose_tip"]
    mouth_center = keypoints["mouth_center"]
    chin = keypoints["chin"]
    forehead = keypoints["forehead_center"]

    eye_distance_ratio = round(distance(left_eye, right_eye) / w, 4)
    nose_mouth_ratio = round(distance(nose_tip, mouth_center) / h, 4)
    mouth_chin_ratio = round(distance(mouth_center, chin) / h, 4)
    face_vertical_ratio = round(distance(forehead, chin) / h, 4)
    center_axis_offset = round(abs(nose_tip["x"] - (bbox[0] + w / 2.0)) / w, 4)
    estimated_ratio = round(sum(1 for keypoint in keypoints.values() if keypoint["source"] != "detected") / float(max(len(keypoints), 1)), 4)
    eye_balance = round(abs(left_eye["y"] - right_eye["y"]) / h, 4)
    edge_density = round(float(edge_density), 4)
    noise_score = round(compute_noise_score(face_gray), 4)
    eye_visibility = round(len(eye_selection) / 2.0, 4)

    return {
        "geometry": {
            "eyeDistanceRatio": eye_distance_ratio,
            "noseMouthRatio": nose_mouth_ratio,
            "mouthChinRatio": mouth_chin_ratio,
            "faceVerticalRatio": face_vertical_ratio,
            "centerAxisOffset": center_axis_offset,
            "eyeBalance": eye_balance,
        },
        "texture": {
            "edgeDensity": edge_density,
            "noiseScore": noise_score,
        },
        "visibility": {
            "estimatedPointRatio": estimated_ratio,
            "eyeVisibility": eye_visibility,
            "poseLabel": pose_label,
        },
    }


def build_connections():
    return [
        ("forehead_center", "left_eye_center"),
        ("forehead_center", "right_eye_center"),
        ("left_eye_center", "nose_bridge_top"),
        ("right_eye_center", "nose_bridge_top"),
        ("nose_bridge_top", "nose_tip"),
        ("nose_tip", "mouth_center"),
        ("mouth_left", "mouth_center"),
        ("mouth_center", "mouth_right"),
        ("mouth_left", "chin"),
        ("mouth_right", "chin"),
    ]


def build_regions(bbox, keypoints):
    left_eye = point_xy(keypoints["left_eye_center"])
    right_eye = point_xy(keypoints["right_eye_center"])
    forehead = point_xy(keypoints["forehead_center"])
    nose_bridge = point_xy(keypoints["nose_bridge_top"])
    nose_tip = point_xy(keypoints["nose_tip"])
    mouth_left = point_xy(keypoints["mouth_left"])
    mouth_center = point_xy(keypoints["mouth_center"])
    mouth_right = point_xy(keypoints["mouth_right"])
    chin = point_xy(keypoints["chin"])
    jaw_left = estimate_point(bbox, 0.18, 0.86)
    jaw_right = estimate_point(bbox, 0.82, 0.86)
    return [
        {"name": "forehead", "color": REGION_COLORS["forehead"], "points": [estimate_point(bbox, 0.18, 0.20), forehead, estimate_point(bbox, 0.82, 0.20), right_eye, left_eye]},
        {"name": "left_eye_zone", "color": REGION_COLORS["left_eye_zone"], "points": [estimate_point(bbox, 0.16, 0.30), left_eye, nose_bridge, estimate_point(bbox, 0.26, 0.55)]},
        {"name": "right_eye_zone", "color": REGION_COLORS["right_eye_zone"], "points": [estimate_point(bbox, 0.84, 0.30), right_eye, nose_bridge, estimate_point(bbox, 0.74, 0.55)]},
        {"name": "nose", "color": REGION_COLORS["nose"], "points": [left_eye, nose_bridge, right_eye, nose_tip]},
        {"name": "mouth", "color": REGION_COLORS["mouth"], "points": [mouth_left, mouth_center, mouth_right, nose_tip]},
        {"name": "jaw", "color": REGION_COLORS["jaw"], "points": [jaw_left, mouth_left, mouth_center, mouth_right, jaw_right, chin]},
    ]


def serialize_regions(regions):
    return [{"name": region["name"], "color": list(region["color"]), "points": [{"x": int(point[0]), "y": int(point[1])} for point in region["points"]]} for region in regions]


def serialize_connections(connections):
    return [{"from": start, "to": end} for start, end in connections]


def build_training_sample(face):
    bbox = face["bbox"]
    width = max(float(bbox["w"]), 1.0)
    height = max(float(bbox["h"]), 1.0)
    left = float(bbox["x"])
    top = float(bbox["y"])
    normalized_points = {}
    source_mask = {}
    for point_name in TRAINING_POINT_ORDER:
        keypoint = face["keypoints"][point_name]
        normalized_points[point_name] = {"x": round((keypoint["x"] - left) / width, 4), "y": round((keypoint["y"] - top) / height, 4), "confidence": keypoint["confidence"]}
        source_mask[point_name] = keypoint["source"]
    return {
        "poseLabel": face["pose"]["label"],
        "bboxNormalized": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "pointsNormalized": normalized_points,
        "pointSources": source_mask,
        "qualityLabel": face["quality"]["label"],
        "qualityScore": face["quality"]["score"],
        "deepfakeFeatures": face.get("deepfakeFeatures", {}),
    }


def save_face_crop(image, request_uid, face_index, box):
    x, y, w, h = expand_box(box, image.shape, scale=0.20)
    face_crop = image[y : y + h, x : x + w]
    if face_crop.size == 0:
        return None
    crop_path = os.path.join(FACE_CROP_DIR, f"{request_uid}_face_{face_index + 1}.jpg")
    cv2.imwrite(crop_path, face_crop)
    return normalize_path(crop_path)


def compute_blur_score(face_gray):
    variance = cv2.Laplacian(face_gray, cv2.CV_64F).var()
    return round(float(max(0.0, min(1.0, variance / 220.0))), 4)


def compute_brightness_score(face_gray):
    mean_value = float(np.mean(face_gray))
    deviation = abs(mean_value - 128.0)
    return round(float(max(0.0, min(1.0, 1.0 - deviation / 128.0))), 4)


def compute_contrast_score(face_gray):
    std_value = float(np.std(face_gray))
    return round(float(max(0.0, min(1.0, std_value / 72.0))), 4)


def classify_quality(blur_score, brightness_score, contrast_score, pose_confidence, detected_ratio, face_size):
    weighted_score = 0.28 * blur_score + 0.18 * brightness_score + 0.18 * contrast_score + 0.18 * pose_confidence + 0.10 * detected_ratio + 0.08 * min(1.0, face_size / 220.0)
    if weighted_score >= 0.72:
        return "good", round(weighted_score, 4)
    if weighted_score >= 0.48:
        return "usable", round(weighted_score, 4)
    return "poor", round(weighted_score, 4)


def build_face_output(image, preprocessed, candidates, request_uid):
    faces = []
    debug_maps = {"eye": [], "nose": [], "mouth": []}
    for index, candidate in enumerate(candidates):
        x, y, w, h = candidate["box"]
        face_gray = preprocessed["equalized"][y : y + h, x : x + w]
        if face_gray.size == 0:
            continue
        eye_response, eye_candidates = detect_eye_candidates(face_gray)
        eye_selection, eye_quality, eye_reason = select_eye_configuration(face_gray, eye_candidates)
        edge_profile = build_face_edge_profile(face_gray)
        pose_label, pose_confidence, pose_reason = classify_pose(eye_selection, eye_quality, face_gray, edge_profile)
        nose_response, nose_bridge_top, nose_tip = detect_nose_keypoints(face_gray, (x, y, w, h), pose_label)
        mouth_response, _, mouth_left, mouth_center, mouth_right = detect_mouth_keypoints(face_gray, (x, y, w, h), pose_label)
        keypoints = build_keypoints((x, y, w, h), pose_label, eye_selection, nose_bridge_top, nose_tip, mouth_left, mouth_center, mouth_right)
        detected_points = sum(1 for keypoint in keypoints.values() if keypoint["source"] == "detected")
        detected_ratio = detected_points / float(max(len(keypoints), 1))
        blur_score = compute_blur_score(face_gray)
        brightness_score = compute_brightness_score(face_gray)
        contrast_score = compute_contrast_score(face_gray)
        quality_label, quality_score = classify_quality(blur_score, brightness_score, contrast_score, pose_confidence, detected_ratio, min(w, h))
        connections = build_connections()
        regions = build_regions((x, y, w, h), keypoints)
        deepfake_features = compute_deepfake_features(
            face_gray,
            (x, y, w, h),
            keypoints,
            pose_label,
            eye_selection,
            edge_profile["edgeDensity"],
        )
        face = {
            "bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
            "detector": candidate["detector"],
            "score": round(float(candidate["score"]), 4),
            "detectionConfidence": round(float(candidate["score"]), 4),
            "pose": {"label": pose_label, "confidence": round(float(pose_confidence), 4), "reason": pose_reason},
            "faceMode": pose_label,
            "quality": {"label": quality_label, "score": quality_score, "blur": blur_score, "brightness": brightness_score, "contrast": contrast_score, "detectedPointRatio": round(float(detected_ratio), 4)},
            "eyes": [global_box(eye["box"], (x, y, w, h)) for eye in eye_selection],
            "keypoints": keypoints,
            "analysisConnections": serialize_connections(connections),
            "analysisRegions": serialize_regions(regions),
            "cropPath": save_face_crop(image, request_uid, index, candidate["box"]),
            "trainingSample": None,
            "featureSummary": {"eyeEvidence": round(float(eye_quality), 4), "eyeReason": eye_reason, "noseEvidence": nose_tip["confidence"], "mouthEvidence": mouth_center["confidence"]},
            "deepfakeFeatures": deepfake_features,
        }
        face["trainingSample"] = build_training_sample(face)
        faces.append(face)
        debug_maps["eye"].append({"bbox": face["bbox"], "response": eye_response})
        debug_maps["nose"].append({"bbox": face["bbox"], "response": nose_response})
        debug_maps["mouth"].append({"bbox": face["bbox"], "response": mouth_response})
    return faces, debug_maps


def draw_face_overlay(image, faces, output_path):
    canvas = image.copy()
    for index, face in enumerate(faces):
        bbox = face["bbox"]
        x = bbox["x"]
        y = bbox["y"]
        w = bbox["w"]
        h = bbox["h"]
        color = (0, 200, 0) if face["quality"]["label"] != "poor" else (0, 165, 255)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
        cv2.putText(canvas, f"{index + 1}: {face['pose']['label']} {face['detectionConfidence']:.2f}", (x, max(y - 8, 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        for eye in face["eyes"]:
            cv2.rectangle(canvas, (eye["x"], eye["y"]), (eye["x"] + eye["w"], eye["y"] + eye["h"]), (255, 0, 255), 1)
    cv2.putText(canvas, "Detected Face Boxes", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(output_path, canvas)


def draw_response_map(image, debug_maps, output_path, title):
    canvas = image.copy()
    overlay = canvas.copy()
    for item in debug_maps:
        bbox = item["bbox"]
        x = bbox["x"]
        y = bbox["y"]
        w = bbox["w"]
        h = bbox["h"]
        response = item["response"]
        if response.size == 0:
            continue
        heat = np.uint8(np.clip(response * 255.0, 0, 255))
        heat = cv2.applyColorMap(heat, cv2.COLORMAP_JET)
        roi = overlay[y : y + h, x : x + w]
        if roi.shape[:2] != heat.shape[:2]:
            heat = cv2.resize(heat, (roi.shape[1], roi.shape[0]))
        overlay[y : y + h, x : x + w] = cv2.addWeighted(roi, 0.35, heat, 0.65, 0)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (255, 255, 255), 1)
    canvas = cv2.addWeighted(overlay, 0.85, canvas, 0.15, 0)
    cv2.putText(canvas, title, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(output_path, canvas)


def draw_panel_text(canvas, lines, start_x, start_y, color=(235, 235, 235), line_gap=18):
    y = start_y
    for line in lines:
        cv2.putText(canvas, str(line), (start_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
        y += line_gap
    return y


def draw_analysis_map(image, faces, output_path):
    image_h, image_w = image.shape[:2]
    panel_width = 430
    canvas = np.full((image_h, image_w + panel_width, 3), 18, dtype=np.uint8)
    canvas[:, :image_w] = image.copy()
    overlay = canvas[:, :image_w].copy()
    for face in faces:
        for region in face.get("analysisRegions", []):
            pts = np.array([[point["x"], point["y"]] for point in region["points"]], dtype=np.int32)
            if len(pts) >= 3:
                cv2.fillPoly(overlay, [pts], tuple(region["color"]))
    canvas[:, :image_w] = cv2.addWeighted(overlay, 0.18, canvas[:, :image_w], 0.82, 0)
    for index, face in enumerate(faces):
        bbox = face["bbox"]
        x = bbox["x"]
        y = bbox["y"]
        w = bbox["w"]
        h = bbox["h"]
        cv2.rectangle(canvas[:, :image_w], (x, y), (x + w, y + h), (0, 255, 255), 2)
        keypoints = face["keypoints"]
        for connection in face["analysisConnections"]:
            start = keypoints.get(connection["from"])
            end = keypoints.get(connection["to"])
            if start and end:
                cv2.line(canvas[:, :image_w], point_xy(start), point_xy(end), (255, 180, 80), 1, cv2.LINE_AA)
        for keypoint in keypoints.values():
            color = (0, 255, 120) if keypoint["source"] == "detected" else (0, 180, 255)
            cv2.circle(canvas[:, :image_w], point_xy(keypoint), 4, color, -1, cv2.LINE_AA)
            cv2.circle(canvas[:, :image_w], point_xy(keypoint), 5, (255, 255, 255), 1, cv2.LINE_AA)
            label = POINT_LABELS.get(keypoint["name"], keypoint["name"][:2].upper())
            cv2.putText(
                canvas[:, :image_w],
                label,
                (keypoint["x"] + 6, max(keypoint["y"] - 4, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        cv2.putText(canvas[:, :image_w], f"Face {index + 1} | {face['pose']['label']}", (x, max(y - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    panel_x = image_w + 18
    y = draw_panel_text(canvas, ["VeritAI Original Anchor Graph", "Detected points = green", "Estimated points = orange", "", "Legend"], panel_x, 30, color=(255, 255, 255))
    for region_name, color in REGION_COLORS.items():
        cv2.rectangle(canvas, (panel_x, y - 10), (panel_x + 14, y + 4), color, -1)
        y = draw_panel_text(canvas, [region_name], panel_x + 24, y)
    if not faces:
        draw_panel_text(canvas, ["", "No faces detected.", "Try a larger, front-facing face image."], panel_x, y + 12)
        cv2.imwrite(output_path, canvas)
        return
    for index, face in enumerate(faces):
        quality = face["quality"]
        pose = face["pose"]
        y = draw_panel_text(canvas, ["", f"[Face {index + 1}]", f"detector={face['detector']}", f"pose={pose['label']} ({pose['confidence']:.4f})", f"quality={quality['label']} ({quality['score']:.4f})", f"detectedPointRatio={quality['detectedPointRatio']:.4f}", f"eye={face['featureSummary']['eyeEvidence']:.4f}", f"nose={face['featureSummary']['noseEvidence']:.4f}", f"mouth={face['featureSummary']['mouthEvidence']:.4f}", f"edgeDensity={face['deepfakeFeatures']['texture']['edgeDensity']:.4f}", f"noiseScore={face['deepfakeFeatures']['texture']['noiseScore']:.4f}"], panel_x, y + 8)
        point_lines = [f"{point_name}: ({face['keypoints'][point_name]['x']},{face['keypoints'][point_name]['y']}) {face['keypoints'][point_name]['source']} {face['keypoints'][point_name]['confidence']:.2f}" for point_name in TRAINING_POINT_ORDER]
        y = draw_panel_text(canvas, point_lines, panel_x + 10, y, color=(210, 210, 210), line_gap=17)
    cv2.imwrite(output_path, canvas)


def save_debug_metadata(request_uid, faces, debug_paths):
    payload = {
        "requestUid": request_uid,
        "pipeline": {"name": "veritai-pose-aware-anchor-graph", "version": "v1", "description": "Original pose-aware facial anchor graph with detected/estimated keypoint separation."},
        "outputStructure": {
            "overlays": "images/analysis/overlays",
            "anchorMaps": "images/analysis/anchor_maps",
            "metadata": "images/analysis/metadata",
            "eyeResponses": "images/analysis/response_maps/eyes",
            "noseResponses": "images/analysis/response_maps/nose",
            "mouthResponses": "images/analysis/response_maps/mouth",
        },
        "faceCount": len(faces),
        "faces": faces,
        "generatedFiles": {key: normalize_path(path) for key, path in debug_paths.items()},
        "trainingDatasetCandidate": [face["trainingSample"] for face in faces],
    }
    with open(debug_paths["metadata"], "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    start = time.time()
    contents = await file.read()
    img = decode_image(contents)
    if img is None:
        return {"isDeepfake": False, "confidence": 0.0, "faceCount": 0, "watermarkDetected": False, "modelVersion": "veritai-pose-aware-anchor-graph-v1", "processingTimeMs": 0, "message": "이미지 디코딩에 실패했습니다.", "faces": [], "debugImages": {}}
    max_width = 1280
    if img.shape[1] > max_width:
        ratio = max_width / img.shape[1]
        img = cv2.resize(img, None, fx=ratio, fy=ratio)
    request_uid, debug_paths = make_debug_paths()
    preprocessed = preprocess_image(img)
    candidates = detect_faces(preprocessed)
    faces, debug_maps = build_face_output(img, preprocessed, candidates, request_uid)
    draw_face_overlay(img, faces, debug_paths["overlay"])
    draw_analysis_map(img, faces, debug_paths["analysisMap"])
    draw_response_map(img, debug_maps["eye"], debug_paths["eyeResponse"], "Eye Response Map")
    draw_response_map(img, debug_maps["nose"], debug_paths["noseResponse"], "Nose Response Map")
    draw_response_map(img, debug_maps["mouth"], debug_paths["mouthResponse"], "Mouth Response Map")
    save_debug_metadata(request_uid, faces, debug_paths)
    processing_time_ms = int((time.time() - start) * 1000)
    ready_faces = [face for face in faces if face["quality"]["label"] != "poor"]
    confidence = round(sum(face["detectionConfidence"] for face in faces) / len(faces), 4) if faces else 0.0
    return {"isDeepfake": False, "confidence": confidence, "faceCount": len(faces), "watermarkDetected": False, "modelVersion": "veritai-pose-aware-anchor-graph-v1", "processingTimeMs": processing_time_ms, "message": f"얼굴 {len(faces)}개를 검출했고, 그중 분석에 바로 활용 가능한 품질의 얼굴은 {len(ready_faces)}개입니다.", "faces": faces, "debugImages": {key: normalize_path(path) for key, path in debug_paths.items()}}


@app.get("/")
async def root():
    return {"message": "VeritAI original anchor graph server is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
