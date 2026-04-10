# 🕐 2026-04-10 오후 1시 이후 변경사항 정리

> 기준 시각: **2026-04-10 13:00**
>
> 이 문서는 오늘 **2026년 4월 10일 오후 1시 이후** 현재 워크스페이스 기준으로 반영된 변경사항을 따로 정리한 문서입니다.

---

## 📌 한눈에 보기

오늘 오후 1시 이후에는 크게 네 가지 축의 작업이 진행되었습니다.

1. AI 튜닝 케이스 구조 추가
2. 오검출 리뷰 자동 저장 기능 추가
3. 문서 보강
4. 프론트 / AI 경량화 및 정리

---

## ✅ 변경사항 상세

## 1. AI 튜닝 케이스 폴더 구조 추가

추가 시각:
- `2026-04-10 13:21` 전후

추가된 폴더:
- [ai/tuning_cases/frontal_good](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/frontal_good)
- [ai/tuning_cases/profile_left](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/profile_left)
- [ai/tuning_cases/eyes_closed](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/eyes_closed)
- [ai/tuning_cases/occluded](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/occluded)
- [ai/tuning_cases/false_positive](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/false_positive)
- [ai/tuning_cases/false_negative](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/false_negative)

의미:
- 케이스별로 실패 유형을 나눠 넣고 반복 튜닝할 수 있는 구조를 만들었습니다.
- 이제 정면 얼굴, 측면 얼굴, 눈 감은 얼굴, 가림 얼굴, 오검출, 미검출을 분리해서 테스트할 수 있습니다.

---

## 2. 튜닝 실행 스크립트 및 결과 요약 구조 추가

추가 시각:
- `2026-04-10 13:22` 전후

관련 파일:
- [ai/run_tuning_cases.py](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/run_tuning_cases.py)
- [images/tuning_runs](C:/Users/Administrator/VeritAI-Project/VeritAI/images/tuning_runs)

추가된 내용:
- 튜닝 케이스 폴더의 이미지를 일괄 분석할 수 있는 배치 스크립트 추가
- 실행 시 `summary.json`, `summary.md` 생성
- 케이스별 `pass / warn / fail` 기준 반영

생성 결과 예시:
- [images/tuning_runs/20260410_132218/summary.md](C:/Users/Administrator/VeritAI-Project/VeritAI/images/tuning_runs/20260410_132218/summary.md)

의미:
- 수동으로 이미지 하나씩 검사하지 않아도 되고,
- 어떤 유형에서 오검출이 많이 나는지 카테고리별로 확인할 수 있게 되었습니다.

---

## 3. 튜닝 가이드 문서 추가

추가 시각:
- `2026-04-10 13:36`

관련 파일:
- [ai/tuning_cases/TUNING_GUIDE.md](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/TUNING_GUIDE.md)

추가된 내용:
- `frontal_good`, `profile_left`, `eyes_closed`, `occluded`, `false_positive`, `false_negative` 별 기대 결과 정리
- 어떤 JSON 필드를 봐야 하는지 정리
- 어떤 함수부터 수정해야 하는지 정리
- `warn`, `fail` 리뷰 폴더 구조 설명 추가

의미:
- 튜닝 기준이 사람마다 달라지지 않도록 문서화했습니다.
- 팀원이 바로 같은 기준으로 오검출을 볼 수 있습니다.

---

## 4. 오검출 리뷰 자동 저장 기능 추가

추가 시각:
- `2026-04-10 13:36` 전후

관련 파일:
- [ai/run_tuning_cases.py](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/run_tuning_cases.py)

핵심 변경:
- `warn`, `fail` 케이스를 자동으로 리뷰 폴더에 복사 저장
- `bucket` 단위로 유형 분류

리뷰 저장 구조:

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

폴더 안에 저장되는 파일:
- 원본 입력 이미지
- `*_analysis.jpg`
- `*_eye_response.jpg`
- `*_nose_response.jpg`
- `*_mouth_response.jpg`
- `*_analysis.json`
- `case_summary.json`

의미:
- 오검출 사례를 사람이 다시 찾지 않아도 되도록 개선했습니다.
- 실패 케이스 분석 효율이 크게 좋아졌습니다.

---

## 5. 프론트엔드 경량화

변경 시각:
- [content.js](C:/Users/Administrator/VeritAI-Project/VeritAI/content.js) `2026-04-10 13:55`
- [background.js](C:/Users/Administrator/VeritAI-Project/VeritAI/background.js) `2026-04-10 13:55`

핵심 변경:
- `content.js` 전체 정리
- 깨진 문자열 정리
- 불필요한 `WeakSet` 제거
- `MutationObserver + scroll + resize` 에서 즉시 전체 스캔하던 구조를 `requestAnimationFrame` 기반 스케줄링으로 변경
- `attributes: true` 감시 제거
- 네트워크 주소와 결과 요약 로직 정리
- `background.js` 에서 불필요한 분기와 깨진 에러 문구 정리

의미:
- 페이지 변화가 많은 SNS 피드에서 버튼 재부착 비용을 줄였습니다.
- 유지보수하기 쉬운 구조로 바뀌었습니다.

---

## 6. AI 연산 경량화

변경 시각:
- [ai/main.py](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/main.py) `2026-04-10 13:55`

핵심 변경:
- 얼굴마다 중복 계산되던 edge 기반 연산을 `edge_profile` 로 묶어 재사용
- pose 분류와 deepfake feature 계산에서 같은 edge 정보를 공유하도록 변경

의미:
- 얼굴당 중복 `Canny` 연산이 줄어들어 추후 다중 얼굴 이미지에서 조금 더 가벼워졌습니다.
- 기능 결과는 유지하면서 계산 낭비를 줄였습니다.

---

## 7. 오늘 기준 확인된 실행 상태

확인된 내용:
- 백엔드 `compileJava` 통과
- manifest 파싱 정상
- 프론트와 AI 파일 구조 연결 정상

환경 이슈:
- 백엔드 `gradlew test` 는 현재 Gradle 캐시 접근 권한 문제로 환경에 따라 실패 가능
- AI `venv` 실행기는 일부 환경에서 실행 문제 점검 필요

의미:
- 코드 반영은 되었지만,
- end-to-end 전체 실행 확인은 로컬 실행 환경 상태에 따라 추가 점검이 필요합니다.

---

## 📂 오늘 이후 새로 중요해진 경로

- [ai/tuning_cases](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases)
- [ai/tuning_cases/TUNING_GUIDE.md](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/tuning_cases/TUNING_GUIDE.md)
- [ai/run_tuning_cases.py](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/run_tuning_cases.py)
- [images/tuning_runs](C:/Users/Administrator/VeritAI-Project/VeritAI/images/tuning_runs)
- [content.js](C:/Users/Administrator/VeritAI-Project/VeritAI/content.js)
- [background.js](C:/Users/Administrator/VeritAI-Project/VeritAI/background.js)
- [ai/main.py](C:/Users/Administrator/VeritAI-Project/VeritAI/ai/main.py)

---

## 📝 요약

오늘 **2026-04-10** 변경의 핵심은
기존 얼굴 분석 기능을 단순 실행 수준에서 끝내지 않고,

- 실패 케이스를 분류하고
- 반복 튜닝할 수 있게 만들고
- 리뷰 산출물을 자동으로 모으고
- 프론트와 AI의 불필요한 비용을 줄이는 쪽으로 확장했다는 점입니다.

즉, 오늘 작업은 기능 추가 자체도 있지만
**“개발자가 더 빠르게 오검출을 잡을 수 있는 구조”를 만든 것**에 의미가 큽니다.
