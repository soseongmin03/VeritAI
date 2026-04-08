import os
import uuid
import time
import math
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEBUG_DIR = "debug"
os.makedirs(DEBUG_DIR, exist_ok=True)


def decode_image(contents: bytes):
    np_arr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return img


def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    blurred = cv2.GaussianBlur(equalized, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    return {
        "gray": gray,
        "equalized": equalized,
        "blurred": blurred,
        "edges": edges
    }


def generate_candidate_boxes(preprocessed):
    edges = preprocessed["edges"]

    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        if w < 30 or h < 30:
            continue

        if w > 500 or h > 500:
            continue

        aspect_ratio = w / float(h)
        if aspect_ratio < 0.45 or aspect_ratio > 1.7:
            continue

        area = w * h
        if area < 1200:
            continue

        boxes.append((x, y, w, h))

    return boxes


def compute_symmetry_score(gray, box):
    x, y, w, h = box
    roi = gray[y:y+h, x:x+w]

    if roi.size == 0 or roi.shape[1] < 2:
        return 0.0

    half = roi.shape[1] // 2
    if half == 0:
        return 0.0

    left = roi[:, :half]
    right = roi[:, -half:]
    right_flipped = cv2.flip(right, 1)

    min_width = min(left.shape[1], right_flipped.shape[1])
    left = left[:, :min_width]
    right_flipped = right_flipped[:, :min_width]

    if left.size == 0 or right_flipped.size == 0:
        return 0.0

    diff = np.mean(np.abs(left.astype(np.float32) - right_flipped.astype(np.float32)))
    score = 1.0 - min(diff / 255.0, 1.0)
    return float(score)


def compute_aspect_score(box):
    _, _, w, h = box
    aspect = w / float(h)

    ideal = 0.9
    diff = abs(aspect - ideal)

    score = max(0.0, 1.0 - diff / 0.8)
    return float(score)


def compute_edge_density_score(preprocessed, box):
    edges = preprocessed["edges"]
    x, y, w, h = box

    roi = edges[y:y+h, x:x+w]
    if roi.size == 0:
        return 0.0

    edge_pixels = np.count_nonzero(roi)
    total_pixels = roi.size
    density = edge_pixels / float(total_pixels)

    if density < 0.015:
        return 0.0
    if density > 0.40:
        return 0.0

    center = 0.15
    diff = abs(density - center)
    score = max(0.0, 1.0 - diff / 0.18)
    return float(score)


def extract_face_contour(preprocessed, box):
    gray = preprocessed["equalized"]
    x, y, w, h = box

    roi = gray[y:y+h, x:x+w]
    if roi.size == 0:
        return None

    roi_blur = cv2.GaussianBlur(roi, (5, 5), 0)

    _, thresh = cv2.threshold(
        roi_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    edges = cv2.Canny(roi_blur, 50, 150)

    combined = cv2.bitwise_or(cv2.bitwise_not(thresh), edges)

    kernel = np.ones((3, 3), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    best_contour = None
    best_score = -1.0

    roi_area = w * h
    cx_roi = w / 2.0
    cy_roi = h / 2.0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 0.08 * roi_area:
            continue

        if len(contour) < 5:
            continue

        bx, by, bw, bh = cv2.boundingRect(contour)
        aspect = bw / float(bh) if bh > 0 else 0.0
        if aspect < 0.4 or aspect > 1.8:
            continue

        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue

        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]

        dist = math.sqrt((cx - cx_roi) ** 2 + (cy - cy_roi) ** 2)
        center_score = max(0.0, 1.0 - dist / max(w, h))
        area_score = min(area / roi_area / 0.6, 1.0)

        score = 0.6 * area_score + 0.4 * center_score

        if score > best_score:
            best_score = score
            best_contour = contour

    if best_contour is None:
        return None

    best_contour_global = best_contour.copy()
    best_contour_global[:, 0, 0] += x
    best_contour_global[:, 0, 1] += y

    return best_contour_global


def fit_face_ellipse(contour):
    if contour is None or len(contour) < 5:
        return None
    ellipse = cv2.fitEllipse(contour)
    return ellipse


def compute_oval_score(contour, ellipse):
    if contour is None or ellipse is None:
        return 0.0

    contour_area = cv2.contourArea(contour)
    (_, _), (major_axis, minor_axis), _ = ellipse

    a = major_axis / 2.0
    b = minor_axis / 2.0
    ellipse_area = math.pi * a * b

    if ellipse_area <= 0:
        return 0.0

    ratio = contour_area / ellipse_area
    diff = abs(1.0 - ratio)
    score = max(0.0, 1.0 - diff / 0.7)
    return float(score)


def compute_convexity_score(contour):
    if contour is None:
        return 0.0

    area = cv2.contourArea(contour)
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)

    if hull_area <= 0:
        return 0.0

    score = area / hull_area
    return float(max(0.0, min(score, 1.0)))


def compute_smoothness_score(contour):
    if contour is None:
        return 0.0

    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)

    if perimeter <= 0 or area <= 0:
        return 0.0

    circularity = 4 * math.pi * area / (perimeter * perimeter)
    score = max(0.0, min(circularity / 0.9, 1.0))
    return float(score)


def make_ellipse_mask(shape, ellipse):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    if ellipse is not None:
        cv2.ellipse(mask, ellipse, 255, -1)
    return mask


def crop_mask_with_box(mask, box):
    x, y, w, h = box
    return mask[y:y+h, x:x+w]


def detect_eye_blobs(preprocessed, box, ellipse=None):
    """
    ellipse 내부 + 얼굴 상단 18~50% 영역에서 눈 후보 blob 탐색
    """
    gray = preprocessed["equalized"]
    x, y, w, h = box

    roi = gray[y:y+h, x:x+w]
    if roi.size == 0:
        return []

    full_mask = make_ellipse_mask(gray.shape, ellipse)
    roi_mask = crop_mask_with_box(full_mask, box)

    eye_y1 = int(h * 0.18)
    eye_y2 = int(h * 0.50)
    if eye_y2 <= eye_y1:
        return []

    eye_roi = roi[eye_y1:eye_y2, :]
    eye_mask = roi_mask[eye_y1:eye_y2, :]

    if eye_roi.shape[0] < 10 or eye_roi.shape[1] < 20:
        return []

    eye_roi_masked = cv2.bitwise_and(eye_roi, eye_roi, mask=eye_mask)
    blur = cv2.GaussianBlur(eye_roi_masked, (5, 5), 0)

    _, thresh = cv2.threshold(
        blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    thresh = cv2.bitwise_and(thresh, thresh, mask=eye_mask)

    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blobs = []
    roi_area = max(eye_roi.shape[0] * eye_roi.shape[1], 1)

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 0.002 * roi_area:
            continue
        if area > 0.05 * roi_area:
            continue

        bx, by, bw, bh = cv2.boundingRect(contour)
        if bw < 4 or bh < 3:
            continue

        aspect = bw / float(max(bh, 1))
        if aspect < 1.0 or aspect > 5.0:
            continue

        cx = bx + bw / 2.0
        cy = by + bh / 2.0

        normalized_y = cy / max(eye_roi.shape[0], 1)
        if normalized_y > 0.75:
            continue

        blobs.append({
            "box_local": (bx, by, bw, bh),
            "box_global": (x + bx, y + eye_y1 + by, bw, bh),
            "center_local": (cx, cy),
            "area": area
        })

    return blobs


def compute_eye_scores(preprocessed, box, ellipse=None):
    """
    eyePairScore, singleEyeScore, eyeBoxes 반환
    """
    x, y, w, h = box
    blobs = detect_eye_blobs(preprocessed, box, ellipse)

    if not blobs:
        return 0.0, 0.0, []

    best_single = 0.0
    best_single_box = None

    eye_region_h = max(int(h * 0.50) - int(h * 0.18), 1)

    for blob in blobs:
        bx, by, bw, bh = blob["box_local"]
        cx, cy = blob["center_local"]
        area = blob["area"]

        cx_score = max(0.0, 1.0 - abs(cx - w / 2.0) / (w / 2.0))
        cy_score = max(0.0, 1.0 - abs(cy - (eye_region_h * 0.45)) / max(eye_region_h * 0.45, 1))

        aspect = bw / float(max(bh, 1))
        shape_score = max(0.0, 1.0 - abs(aspect - 2.2) / 2.0)
        area_score = min(area / max((w * h * 0.008), 1), 1.0)

        single_score = (
            0.25 * cx_score +
            0.30 * cy_score +
            0.25 * shape_score +
            0.20 * area_score
        )

        if single_score > best_single:
            best_single = single_score
            best_single_box = blob["box_global"]

    best_pair_score = 0.0
    best_pair_boxes = []

    if len(blobs) >= 2:
        for i in range(len(blobs)):
            for j in range(i + 1, len(blobs)):
                b1 = blobs[i]
                b2 = blobs[j]

                c1x, c1y = b1["center_local"]
                c2x, c2y = b2["center_local"]

                if c1x == c2x:
                    continue

                left = b1 if c1x < c2x else b2
                right = b2 if c1x < c2x else b1

                lx, ly, lw, lh = left["box_local"]
                rx, ry, rw, rh = right["box_local"]

                y_diff = abs((ly + lh / 2.0) - (ry + rh / 2.0))
                y_score = max(0.0, 1.0 - y_diff / max(eye_region_h * 0.20, 1))

                area_ratio = min(left["area"], right["area"]) / max(left["area"], right["area"])
                size_score = area_ratio

                eye_distance = abs((lx + lw / 2.0) - (rx + rw / 2.0))
                normalized_dist = eye_distance / max(w, 1)

                if normalized_dist < 0.18 or normalized_dist > 0.65:
                    dist_score = 0.0
                else:
                    center_dist = 0.34
                    dist_score = max(0.0, 1.0 - abs(normalized_dist - center_dist) / 0.28)

                pair_center_x = ((lx + lw / 2.0) + (rx + rw / 2.0)) / 2.0
                center_x_score = max(
                    0.0,
                    1.0 - abs(pair_center_x - w / 2.0) / (w / 2.0)
                )

                pair_score = (
                    0.32 * y_score +
                    0.28 * size_score +
                    0.25 * dist_score +
                    0.15 * center_x_score
                )

                if pair_score > best_pair_score:
                    best_pair_score = pair_score
                    best_pair_boxes = [left["box_global"], right["box_global"]]

    eye_boxes = best_pair_boxes if best_pair_boxes else ([best_single_box] if best_single_box else [])
    return float(best_pair_score), float(best_single), eye_boxes


def compute_mouth_score(preprocessed, box, ellipse=None):
    """
    ellipse 내부 + 얼굴 하단 62~88% 영역에서 입 후보 탐색
    """
    gray = preprocessed["equalized"]
    x, y, w, h = box

    roi = gray[y:y+h, x:x+w]
    if roi.size == 0:
        return 0.0, []

    full_mask = make_ellipse_mask(gray.shape, ellipse)
    roi_mask = crop_mask_with_box(full_mask, box)

    mouth_y1 = int(h * 0.62)
    mouth_y2 = int(h * 0.88)
    if mouth_y2 <= mouth_y1:
        return 0.0, []

    mouth_roi = roi[mouth_y1:mouth_y2, :]
    mouth_mask = roi_mask[mouth_y1:mouth_y2, :]

    if mouth_roi.shape[0] < 8 or mouth_roi.shape[1] < 20:
        return 0.0, []

    mouth_roi_masked = cv2.bitwise_and(mouth_roi, mouth_roi, mask=mouth_mask)

    blur = cv2.GaussianBlur(mouth_roi_masked, (5, 5), 0)
    _, thresh = cv2.threshold(
        blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    thresh = cv2.bitwise_and(thresh, thresh, mask=mouth_mask)

    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_score = 0.0
    best_box = None

    roi_area = max(mouth_roi.shape[0] * mouth_roi.shape[1], 1)

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 0.002 * roi_area:
            continue
        if area > 0.08 * roi_area:
            continue

        bx, by, bw, bh = cv2.boundingRect(contour)
        if bw < 8 or bh < 3:
            continue

        aspect = bw / float(max(bh, 1))
        if aspect < 1.5 or aspect > 7.0:
            continue

        cx = bx + bw / 2.0
        cy = by + bh / 2.0

        normalized_x = cx / max(w, 1)
        if normalized_x < 0.20 or normalized_x > 0.80:
            continue

        center_x_score = max(0.0, 1.0 - abs(cx - w / 2.0) / (w * 0.35))
        center_y_score = max(0.0, 1.0 - abs(cy - mouth_roi.shape[0] * 0.45) / max(mouth_roi.shape[0] * 0.45, 1))
        shape_score = max(0.0, 1.0 - abs(aspect - 2.8) / 2.8)
        area_score = min(area / max((w * h * 0.006), 1), 1.0)

        score = (
            0.32 * center_x_score +
            0.22 * center_y_score +
            0.26 * shape_score +
            0.20 * area_score
        )

        if score > best_score:
            best_score = score
            best_box = (x + bx, y + mouth_y1 + by, bw, bh)

    mouth_boxes = [best_box] if best_box is not None else []
    return float(best_score), mouth_boxes


def ellipse_to_dict(ellipse):
    if ellipse is None:
        return None

    (cx, cy), (major_axis, minor_axis), angle = ellipse
    return {
        "cx": round(float(cx), 2),
        "cy": round(float(cy), 2),
        "majorAxis": round(float(major_axis), 2),
        "minorAxis": round(float(minor_axis), 2),
        "angle": round(float(angle), 2)
    }


def score_candidate(preprocessed, box):
    gray = preprocessed["equalized"]

    symmetry = compute_symmetry_score(gray, box)
    aspect = compute_aspect_score(box)
    edge_density = compute_edge_density_score(preprocessed, box)

    contour = extract_face_contour(preprocessed, box)
    ellipse = fit_face_ellipse(contour)

    oval_score = compute_oval_score(contour, ellipse)
    convexity = compute_convexity_score(contour)
    smoothness = compute_smoothness_score(contour)

    eye_pair_score, single_eye_score, eye_boxes = compute_eye_scores(preprocessed, box, ellipse)
    mouth_score, mouth_boxes = compute_mouth_score(preprocessed, box, ellipse)

    frontal_score = (
        0.18 * symmetry +
        0.22 * eye_pair_score +
        0.10 * single_eye_score +
        0.12 * mouth_score +
        0.16 * oval_score +
        0.10 * convexity +
        0.06 * smoothness +
        0.06 * aspect
    )

    occluded_score = (
        0.10 * symmetry +
        0.10 * eye_pair_score +
        0.18 * single_eye_score +
        0.05 * mouth_score +
        0.22 * oval_score +
        0.15 * convexity +
        0.12 * smoothness +
        0.08 * aspect
    )

    profile_score = (
        0.05 * symmetry +
        0.05 * eye_pair_score +
        0.20 * single_eye_score +
        0.02 * mouth_score +
        0.22 * oval_score +
        0.16 * convexity +
        0.12 * smoothness +
        0.18 * aspect
    )

    final_score = max(frontal_score, occluded_score, profile_score)

    if final_score == frontal_score:
        face_mode = "frontal"
    elif final_score == occluded_score:
        face_mode = "occluded"
    else:
        face_mode = "profile"

    return {
        "score": float(final_score),
        "faceMode": face_mode,
        "frontalScore": float(frontal_score),
        "occludedScore": float(occluded_score),
        "profileScore": float(profile_score),
        "symmetry": float(symmetry),
        "aspect": float(aspect),
        "edgeDensity": float(edge_density),
        "oval": float(oval_score),
        "convexity": float(convexity),
        "smoothness": float(smoothness),
        "eyePairScore": float(eye_pair_score),
        "singleEyeScore": float(single_eye_score),
        "mouthScore": float(mouth_score),
        "eyeBoxes": eye_boxes,
        "mouthBoxes": mouth_boxes,
        "contour": contour,
        "ellipse": ellipse
    }


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
    if union == 0:
        return 0.0

    return intersection / union


def non_max_suppression(candidates, iou_threshold=0.35):
    if not candidates:
        return []

    candidates = sorted(candidates, key=lambda c: c["score"], reverse=True)
    selected = []

    while candidates:
        current = candidates.pop(0)
        selected.append(current)

        remaining = []
        for candidate in candidates:
            iou = calculate_iou(current["box"], candidate["box"])
            if iou < iou_threshold:
                remaining.append(candidate)

        candidates = remaining

    return selected


def build_faces_output(candidates):
    faces = []
    for candidate in candidates:
        x, y, w, h = candidate["box"]
        faces.append({
            "bbox": {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h)
            },
            "ellipse": ellipse_to_dict(candidate["ellipse"]),
            "score": round(float(candidate["score"]), 4),
            "faceMode": candidate["faceMode"],
            "frontalScore": round(float(candidate["frontalScore"]), 4),
            "occludedScore": round(float(candidate["occludedScore"]), 4),
            "profileScore": round(float(candidate["profileScore"]), 4),
            "symmetry": round(float(candidate["symmetry"]), 4),
            "aspect": round(float(candidate["aspect"]), 4),
            "edgeDensity": round(float(candidate["edgeDensity"]), 4),
            "oval": round(float(candidate["oval"]), 4),
            "convexity": round(float(candidate["convexity"]), 4),
            "smoothness": round(float(candidate["smoothness"]), 4),
            "eyePairScore": round(float(candidate["eyePairScore"]), 4),
            "singleEyeScore": round(float(candidate["singleEyeScore"]), 4),
            "mouthScore": round(float(candidate["mouthScore"]), 4),
            "eyes": [
                {"x": int(ex), "y": int(ey), "w": int(ew), "h": int(eh)}
                for (ex, ey, ew, eh) in candidate.get("eyeBoxes", [])
            ],
            "mouths": [
                {"x": int(mx), "y": int(my), "w": int(mw), "h": int(mh)}
                for (mx, my, mw, mh) in candidate.get("mouthBoxes", [])
            ]
        })
    return faces


def draw_candidate_boxes(image, candidates, output_path):
    canvas = image.copy()

    for idx, candidate in enumerate(candidates):
        x, y, w, h = candidate["box"]
        score = candidate.get("score", 0.0)

        cv2.rectangle(canvas, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(
            canvas,
            f"{idx+1}: {score:.2f}",
            (x, max(y - 8, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            1,
            cv2.LINE_AA
        )

    cv2.putText(
        canvas,
        "All Candidate Boxes",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.imwrite(output_path, canvas)


def draw_final_shapes(image, candidates, output_path):
    canvas = image.copy()

    for idx, candidate in enumerate(candidates):
        x, y, w, h = candidate["box"]
        score = candidate["score"]
        contour = candidate.get("contour")
        ellipse = candidate.get("ellipse")
        eye_boxes = candidate.get("eyeBoxes", [])
        mouth_boxes = candidate.get("mouthBoxes", [])
        face_mode = candidate.get("faceMode", "unknown")

        cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 255), 1)

        if contour is not None:
            cv2.drawContours(canvas, [contour], -1, (0, 255, 0), 2)

        if ellipse is not None:
            cv2.ellipse(canvas, ellipse, (0, 0, 255), 2)

        for (ex, ey, ew, eh) in eye_boxes:
            cv2.rectangle(canvas, (ex, ey), (ex + ew, ey + eh), (255, 0, 255), 2)

        for (mx, my, mw, mh) in mouth_boxes:
            cv2.rectangle(canvas, (mx, my), (mx + mw, my + mh), (0, 165, 255), 2)

        label = f"{idx+1}: {score:.2f} {face_mode}"
        cv2.putText(
            canvas,
            label,
            (x, max(y - 8, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA
        )

    cv2.putText(
        canvas,
        "Final Face Contours / Ellipses / Eyes / Mouth",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.imwrite(output_path, canvas)


def make_debug_paths():
    uid = uuid.uuid4().hex[:12]
    all_candidates_path = os.path.join(DEBUG_DIR, f"{uid}_all_candidates.jpg")
    final_faces_path = os.path.join(DEBUG_DIR, f"{uid}_final_shapes.jpg")
    return all_candidates_path, final_faces_path


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    start = time.time()
    contents = await file.read()

    img = decode_image(contents)

    if img is None:
        return {
            "isDeepfake": False,
            "confidence": 0.0,
            "faceCount": 0,
            "watermarkDetected": False,
            "modelVersion": "custom-face-curve-detector-v1.4b",
            "processingTimeMs": 0,
            "message": "이미지 디코딩 실패",
            "faces": [],
            "debugImages": {}
        }

    max_width = 1280
    if img.shape[1] > max_width:
        ratio = max_width / img.shape[1]
        img = cv2.resize(img, None, fx=ratio, fy=ratio)

    preprocessed = preprocess_image(img)
    candidate_boxes = generate_candidate_boxes(preprocessed)

    all_scored_candidates = []
    passed_candidates = []

    for box in candidate_boxes:
        scores = score_candidate(preprocessed, box)

        candidate_data = {
            "box": box,
            "score": scores["score"],
            "faceMode": scores["faceMode"],
            "frontalScore": scores["frontalScore"],
            "occludedScore": scores["occludedScore"],
            "profileScore": scores["profileScore"],
            "symmetry": scores["symmetry"],
            "aspect": scores["aspect"],
            "edgeDensity": scores["edgeDensity"],
            "oval": scores["oval"],
            "convexity": scores["convexity"],
            "smoothness": scores["smoothness"],
            "eyePairScore": scores["eyePairScore"],
            "singleEyeScore": scores["singleEyeScore"],
            "mouthScore": scores["mouthScore"],
            "eyeBoxes": scores["eyeBoxes"],
            "mouthBoxes": scores["mouthBoxes"],
            "contour": scores["contour"],
            "ellipse": scores["ellipse"]
        }

        all_scored_candidates.append(candidate_data)

        if (
            scores["score"] >= 0.45 and
            scores["oval"] >= 0.10 and
            (scores["convexity"] >= 0.40 or scores["smoothness"] >= 0.18)
        ):
            passed_candidates.append(candidate_data)

    final_candidates = non_max_suppression(passed_candidates, iou_threshold=0.35)
    faces = build_faces_output(final_candidates)

    all_candidates_path, final_faces_path = make_debug_paths()

    draw_candidate_boxes(img, all_scored_candidates, all_candidates_path)
    draw_final_shapes(img, final_candidates, final_faces_path)

    processing_time_ms = int((time.time() - start) * 1000)

    return {
        "isDeepfake": False,
        "confidence": 0.0,
        "faceCount": len(faces),
        "watermarkDetected": False,
        "modelVersion": "custom-face-curve-detector-v1.4b",
        "processingTimeMs": processing_time_ms,
        "message": f"가림/측면 대응 곡면 기반 얼굴 후보 검출 결과: {len(faces)}개",
        "faces": faces,
        "debugImages": {
            "allCandidates": all_candidates_path.replace("\\", "/"),
            "finalShapes": final_faces_path.replace("\\", "/")
        }
    }


@app.get("/")
async def root():
    return {"message": "Custom face curve detector server is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)