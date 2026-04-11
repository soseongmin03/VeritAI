# Tuning Guide

## 목적

이 문서는 VeritAI 얼굴 분석기의 튜닝 케이스를 어떤 기준으로 확인하고, 어떤 함수부터 손보면 좋을지 빠르게 판단하기 위한 가이드입니다.

## 기본 확인 순서

1. `images/tuning_runs/<timestamp>/summary.md`에서 전체 결과를 먼저 봅니다.
2. `fail`과 `warn` 케이스를 우선 확인합니다.
3. 자동으로 복사된 리뷰 폴더를 확인합니다.

```text
images/tuning_runs/<timestamp>/review/<bucket>/<rating>/...
```

4. 각 리뷰 폴더 안의 파일을 같이 봅니다.

- `input.*`
- `*_analysis.jpg`
- `*_eye_response.jpg`
- `*_nose_response.jpg`
- `*_mouth_response.jpg`
- `*_analysis.json`
- `case_summary.json`

## 카테고리별 기대 결과

### `frontal_good`

기대:

- 얼굴이 1개 이상 검출
- `pose.label = frontal`
- `quality.detectedPointRatio >= 0.40`이면 `pass`

우선 확인할 필드:

- `pose.label`
- `quality.detectedPointRatio`
- `keypoints.left_eye_center.source`
- `keypoints.right_eye_center.source`
- `keypoints.nose_tip.source`
- `keypoints.mouth_center.source`

주요 보정 함수:

- `detect_eye_candidates`
- `select_eye_configuration`
- `classify_pose`

### `profile_left`

기대:

- 얼굴이 1개 이상 검출
- `pose.label = profile-left`

우선 확인할 필드:

- `pose.label`
- `pose.reason`
- `keypoints.nose_tip`
- `keypoints.mouth_center`
- `quality.detectedPointRatio`

주요 보정 함수:

- `classify_pose`
- `detect_nose_keypoints`
- `detect_mouth_keypoints`
- `stabilize_profile_keypoints`

### `profile_right`

기대:

- 얼굴이 1개 이상 검출
- `pose.label = profile-right`

우선 확인할 필드:

- `pose.label`
- `pose.reason`
- `keypoints.nose_tip`
- `keypoints.mouth_center`
- `quality.detectedPointRatio`

주요 보정 함수:

- `classify_pose`
- `detect_nose_keypoints`
- `detect_mouth_keypoints`
- `stabilize_profile_keypoints`

### `eyes_closed_frontal`

기대:

- 얼굴이 1개 이상 검출
- `pose.label = eyes_closed`가 가장 이상적
- 최소한 `frontal`이면서 `eyeClosureIndex`가 높으면 `warn`

우선 확인할 필드:

- `pose.label`
- `pose.reason`
- `deepfakeFeatures.visibility.eyeClosureIndex`
- `keypoints.left_eye_center`
- `keypoints.right_eye_center`

주요 보정 함수:

- `detect_eye_candidates`
- `classify_pose`
- `stabilize_eyes_closed_keypoints`

### `eyes_closed_profile`

기대:

- 얼굴이 1개 이상 검출
- `pose.label = eyes_closed`면 가장 좋음
- 아니면 `profile-left` 또는 `profile-right`이면서 `eyeClosureIndex`가 의미 있게 높아야 함

우선 확인할 필드:

- `pose.label`
- `pose.reason`
- `deepfakeFeatures.visibility.eyeClosureIndex`
- `keypoints.left_eye_center`
- `keypoints.right_eye_center`

주요 보정 함수:

- `detect_eye_candidates`
- `classify_pose`
- `stabilize_profile_keypoints`

### `eyes_closed_occluded`

기대:

- 얼굴이 1개 이상 검출
- `pose.label = occluded` 또는 `eyes_closed`

우선 확인할 필드:

- `pose.label`
- `quality.detectedPointRatio`
- `deepfakeFeatures.visibility.eyeClosureIndex`

주요 보정 함수:

- `classify_pose`
- `build_keypoints`

### `occluded`

기대:

- 얼굴이 1개 이상 검출
- `pose.label = occluded`

우선 확인할 필드:

- `pose.label`
- `quality.detectedPointRatio`
- `keypoints.*.source`

주요 보정 함수:

- `classify_pose`
- `build_keypoints`

### `false_positive`

기대:

- `faceCount = 0`

주요 보정 함수:

- `detect_faces`
- `non_max_suppression`
- `should_keep_face`

### `false_negative`

기대:

- 얼굴이 있는 이미지면 최소 1개 이상 검출

주요 보정 함수:

- `detect_faces`
- `detect_eye_candidates`
- `detect_nose_keypoints`
- `detect_mouth_keypoints`

## 자주 보는 필드

### `pose`

얼굴 방향 또는 상태 분류 결과입니다.

### `quality.detectedPointRatio`

주요 포인트 중 실제 검출 기반 포인트 비율입니다.

### `deepfakeFeatures.visibility.eyeClosureIndex`

눈 감김 신호 강도입니다.

### `deepfakeFeatures.geometry`

얼굴 구조 비율 계열 feature입니다.

### `deepfakeFeatures.texture`

edge density, noise score 같은 질감 feature입니다.

## 추천 우선순위

1. `false_positive`와 `false_negative`
2. `frontal_good`
3. `profile_left`, `profile_right`
4. `eyes_closed_frontal`, `eyes_closed_profile`
5. `occluded`, `eyes_closed_occluded`

## 실행 명령

```powershell
.\ai\venv\Scripts\python.exe .\ai\run_tuning_cases.py
```
