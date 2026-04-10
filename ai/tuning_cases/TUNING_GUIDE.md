# Tuning Guide

## 목적

이 문서는 VeritAI의 오리지널 얼굴 anchor graph 분석기를 튜닝할 때
어떤 케이스를 어떤 기준으로 확인해야 하는지 정리한 가이드입니다.

---

## 기본 확인 순서

1. `images/tuning_runs/<timestamp>/summary.md` 에서 전체 결과를 먼저 확인합니다.
2. `evaluation` 이 `fail` 또는 `warn` 인 케이스를 우선 봅니다.
3. 자동으로 복사된 리뷰 폴더를 확인합니다.

- `images/tuning_runs/<timestamp>/review/<bucket>/<rating>/...`

4. 각 리뷰 폴더 안에서 아래 파일을 함께 봅니다.

- `input.jpg` 또는 원본 확장자의 입력 이미지
- `*_analysis.jpg`
- `*_eye_response.jpg`
- `*_nose_response.jpg`
- `*_mouth_response.jpg`
- `*_analysis.json`
- `case_summary.json`

5. `pose`, `keypoints`, `quality`, `deepfakeFeatures` 를 같이 비교합니다.

---

## 자동 저장 구조

`run_tuning_cases.py` 실행 시 `warn`, `fail` 케이스는 자동으로 아래 경로에 복사됩니다.

```text
images/tuning_runs/<timestamp>/review/<bucket>/<rating>/<case-name>-<uid>/
```

예시 bucket:

- `false_positive`
- `false_negative`
- `pose_mismatch`
- `eyes_closed_missed`
- `occlusion_missed`
- `missed_face`
- `low_detected_points`
- `review_needed`
- `analysis_failed`

즉, 이제 오검출 이미지를 다시 수동으로 찾지 않아도
실행 결과 폴더 안에서 바로 확인할 수 있습니다.

---

## 카테고리별 기대 결과

### frontal_good

기대값:

- 얼굴이 최소 1개 검출
- `pose.label = frontal`
- `quality.detectedPointRatio >= 0.40`
- 눈, 코, 입 keypoint 중 다수가 `detected`

주로 확인할 필드:

- `pose.label`
- `quality.detectedPointRatio`
- `keypoints.left_eye_center.source`
- `keypoints.right_eye_center.source`
- `keypoints.nose_tip.source`
- `keypoints.mouth_center.source`

문제가 있으면 볼 함수:

- `detect_eye_candidates`
- `select_eye_configuration`
- `classify_pose`

---

### profile_left

기대값:

- 얼굴이 최소 1개 검출
- `pose.label = profile-left`
- 보이는 쪽 눈, 코, 입이 상대적으로 안정적
- 가려진 쪽 포인트는 `estimated` 여도 괜찮음

주로 확인할 필드:

- `pose.label`
- `pose.reason`
- `keypoints.nose_tip`
- `keypoints.mouth_center`
- `keypoints.right_eye_center`
- `quality.detectedPointRatio`

문제가 있으면 볼 함수:

- `classify_pose`
- `detect_nose_keypoints`
- `detect_mouth_keypoints`
- `stabilize_profile_keypoints`

---

### eyes_closed

기대값:

- 얼굴이 최소 1개 검출
- `pose.label = eyes_closed`
- `deepfakeFeatures.visibility.eyeClosureIndex` 가 높음
- 눈 중심점이 과도하게 흔들리지 않음

주로 확인할 필드:

- `pose.label`
- `pose.reason`
- `deepfakeFeatures.visibility.eyeClosureIndex`
- `keypoints.left_eye_center`
- `keypoints.right_eye_center`

문제가 있으면 볼 함수:

- `detect_eye_candidates`
- `classify_pose`
- `stabilize_eyes_closed_keypoints`

---

### occluded

기대값:

- 얼굴이 최소 1개 검출
- `pose.label = occluded`
- `quality.detectedPointRatio` 가 낮아질 수 있음
- 가려진 포인트는 `estimated` 여도 괜찮음

주로 확인할 필드:

- `pose.label`
- `quality.detectedPointRatio`
- `keypoints.*.source`

문제가 있으면 볼 함수:

- `classify_pose`
- `build_keypoints`

---

### false_positive

기대값:

- `faceCount = 0`

문제가 있으면 볼 함수:

- `detect_faces`
- `non_max_suppression`

---

### false_negative

기대값:

- 얼굴이 있는 이미지면 최소 1개는 검출

문제가 있으면 볼 함수:

- `detect_faces`
- `detect_eye_candidates`
- `detect_nose_keypoints`
- `detect_mouth_keypoints`

---

## 자주 보는 필드 설명

### `pose`

얼굴 방향 또는 상태 분류 결과입니다.

### `quality.detectedPointRatio`

전체 주요 포인트 중 실제 검출 기반 포인트 비율입니다.

### `featureSummary`

눈, 코, 입 근거 요약입니다.

### `deepfakeFeatures.geometry`

얼굴 구조 비율 계열 feature 입니다.

### `deepfakeFeatures.texture`

edge density, noise score 같은 질감 계열 feature 입니다.

### `deepfakeFeatures.visibility`

- estimated point 비율
- eye visibility
- eye closure index

---

## 튜닝 우선순위 추천

1. `false_positive` 를 먼저 줄입니다.
2. `false_negative` 를 줄입니다.
3. `frontal_good` 를 안정화합니다.
4. `profile_left`, `eyes_closed`, `occluded` 를 세부 조정합니다.

---

## 실행 명령

```powershell
.\ai\venv\Scripts\python.exe .\ai\run_tuning_cases.py
```

---

## 실전 팁

- 한 번에 규칙을 많이 바꾸지 말고 카테고리 하나씩 조정합니다.
- 수정 후 `summary.md` 의 `pass / warn / fail` 변화만 비교해도 효과를 빠르게 볼 수 있습니다.
- `pose` 가 맞아도 `keypoints` 가 안정적인지는 따로 봐야 합니다.
