# AI Tuning Cases

VeritAI 얼굴 분석기의 오검출, 포즈 오분류, 눈 감김 실패 사례를 반복적으로 점검하기 위한 입력 폴더입니다.

## 폴더 구조

- `frontal_good`
  정면 얼굴이며 정상적으로 잘 잡혀야 하는 기준 샘플
- `profile_left`
  화면 기준 왼쪽 방향 profile 얼굴
- `profile_right`
  화면 기준 오른쪽 방향 profile 얼굴
- `eyes_closed_frontal`
  정면에 가깝고 눈을 감은 얼굴
- `eyes_closed_profile`
  profile에 가깝고 눈을 감은 얼굴
- `eyes_closed_occluded`
  눈 감김과 가림이 함께 있는 복합 케이스
- `occluded`
  마스크, 머리카락, 손, 프레임 잘림 등으로 일부가 가려진 얼굴
- `false_positive`
  얼굴이 아닌데 얼굴로 잘못 검출되는 사례
- `false_negative`
  얼굴이 있는데 검출하지 못하는 사례

## 넣어야 하는 파일

- 원본 입력 이미지만 넣습니다.
- `*.jpg`, `*.jpeg`, `*.png`, `*.webp`, `*.bmp`를 권장합니다.
- 아래 산출물은 넣지 않습니다.
  - `*_analysis.jpg`
  - `*_overlay.jpg`
  - `*_response.jpg`
  - `case_summary.json`

## 파일명 권장 규칙

실패 이유가 보이도록 이름을 짓는 것이 좋습니다.

예시:

- `profile_left_mask_01.jpg`
- `eyes_closed_frontal_shadow_02.jpg`
- `false_positive_cartoon_01.png`
- `false_negative_small_face_03.jpg`

## 수집 체크리스트

- 정면인데 `frontal`로 안 잡히는 이미지
- 측면인데 방향이 뒤집히는 이미지
- 눈을 감았는데 `eyes_closed`로 안 잡히는 이미지
- 가림이 심한데 `occluded`로 안 잡히는 이미지
- 얼굴이 아닌데 얼굴로 잡히는 이미지
- 얼굴이 있는데 아예 못 잡는 이미지

## 실행 방법

```powershell
.\ai\venv\Scripts\python.exe .\ai\run_tuning_cases.py
```

## 결과 저장 위치

- 실행 요약: `images/tuning_runs/<timestamp>/summary.json`
- 실행 리포트: `images/tuning_runs/<timestamp>/summary.md`
- 리뷰용 복사본: `images/tuning_runs/<timestamp>/review/...`
- 개별 분석 산출물:
  - `images/analysis/overlays`
  - `images/analysis/anchor_maps`
  - `images/analysis/metadata`
  - `images/analysis/response_maps/eyes`
  - `images/analysis/response_maps/nose`
  - `images/analysis/response_maps/mouth`
