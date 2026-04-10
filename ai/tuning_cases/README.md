# AI Tuning Cases

이 폴더는 얼굴 분석 오검출/미검출 사례를 모아 반복 점검하기 위한 로컬 테스트셋 폴더입니다.

## 권장 하위 폴더

- `frontal_good`: 정면 얼굴이 잘 보여야 하는 정상 케이스
- `profile_left`: 왼쪽 또는 오른쪽으로 많이 돌아간 얼굴
- `eyes_closed`: 눈을 감고 있는 얼굴
- `occluded`: 마스크, 손, 머리카락 등으로 가려진 얼굴
- `false_positive`: 얼굴이 아닌데 얼굴로 잡히는 케이스
- `false_negative`: 얼굴이 있는데 잘 못 잡는 케이스

## 사용 방법

1. 각 카테고리 폴더에 이미지를 넣습니다.
2. 아래 명령을 실행합니다.

```powershell
.\ai\venv\Scripts\python.exe .\ai\run_tuning_cases.py
```

3. 실행 결과는 `images/tuning_runs/<timestamp>` 아래에 요약 파일로 저장됩니다.
4. 개별 분석 시각화 결과는 `images/analysis` 아래 카테고리 폴더에 저장됩니다.

## 목적

- 규칙 기반 얼굴 분석기의 약한 케이스를 반복 점검
- profile / eyes_closed / occluded에 대한 튜닝 기준 확보
- 향후 딥페이크 판별용 학습 데이터 후보 정리
