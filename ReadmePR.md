# 📌 VeritAI PR 정리 문서

## 🧭 문서 목적
이 문서는 현재 PR 기준으로 **무엇이 구현되었는지**, **어떻게 실행하고 확인하는지**, **검사 결과가 어디에 저장되는지**, **아직 남아 있는 기능과 개선 포인트가 무엇인지**를 팀원이 빠르게 이해할 수 있도록 정리한 문서입니다.

---

## 📊 현재 구현 진척도

### 🖥️ 프론트엔드 / 크롬 확장
**약 35%**

- 웹페이지의 `img`, `video` 요소를 감지
- 각 미디어에 검사 버튼 부착
- 이미지 또는 비디오 프레임을 캡처해서 백엔드로 전송
- 검사 결과를 받아 사용자에게 결과 메시지 표시
- DOM 변경, 스크롤, 리사이즈 시 버튼 재부착

### 🗄️ 백엔드 / Spring Boot
**약 50%**

- 파일 업로드 API 구현
- 업로드 파일 저장
- 요청 메타데이터 DB 저장
- AI 서버 호출
- AI 응답 저장
- 요청 상태 `PROCESSING / DONE / FAILED` 관리
- 결과 조회 API 구현

### 🤖 AI 서버 / FastAPI
**약 50%**

- 얼굴 후보 검출
- 얼굴 방향 추정
- 얼굴의 눈/코/입 반응 맵 생성
- 얼굴 keypoint를 `detected / estimated`로 구분하여 저장
- 얼굴 anchor graph 시각화 이미지 생성
- 딥페이크 확장용 feature field 저장
- 학습 데이터 후보 형태의 JSON 저장

---

## ✅ 현재 구현된 주요 기능

### 🖥️ 프론트엔드
- 크롬 확장 프로그램이 현재 페이지의 이미지와 비디오를 탐색합니다.
- 미디어 요소에 검사 버튼을 붙입니다.
- 이미지의 경우 직접 캡처하여 전송합니다.
- 비디오의 경우 현재 보이는 프레임을 캡처하여 전송합니다.
- 백엔드 응답을 받아 검사 결과를 표시합니다.

### 🗄️ 백엔드
- `POST /api/detections`로 파일 업로드를 받습니다.
- 업로드 파일을 로컬에 저장합니다.
- 요청 URL, mediaType, clientType, fileHash, MIME type, file size 등의 메타데이터를 저장합니다.
- AI 서버에 파일을 전달하고 응답을 받습니다.
- AI 응답 전체를 JSON 형태로 보존합니다.
- `GET /api/detections/{requestId}`로 결과 재조회가 가능합니다.

### 🤖 AI
- 얼굴을 찾기 위해 OpenCV cascade 기반 얼굴 후보 검출을 수행합니다.
- 눈 후보를 response map 기반으로 탐색합니다.
- 눈 탐지 결과와 얼굴 에지 분포를 기반으로 `frontal / profile-left / profile-right / occluded / eyes_closed`에 가깝게 pose를 분류합니다.
- 코와 입은 각각 별도의 response map을 기반으로 찾습니다.
- 포인트마다 실제로 반응 맵에서 검출한 경우 `detected`, 근거가 약해 템플릿 기반으로 추정한 경우 `estimated`로 기록합니다.
- 이 결과를 바탕으로 forehead, eye zone, nose, mouth, jaw 영역을 나누고 anchor graph 이미지를 생성합니다.
- 딥페이크 확장을 위해 geometry / texture / visibility 기반 feature를 같이 저장합니다.

---

## 🔍 현재 검사 방식

### 1. 얼굴 감지 방식
- 전체 이미지에서 얼굴 후보 박스를 찾습니다.
- 현재는 OpenCV cascade 기반 얼굴 박스 검출을 사용하고 있습니다.
- 검출된 후보 박스는 score 기반으로 정리하고 중복 박스는 제거합니다.

### 2. 눈 감지 방식
- 얼굴 상단 영역을 기준으로 eye response map을 만듭니다.
- 어두운 수평 구조, 좌우 위치, 크기 비율 등을 점수화합니다.
- 두 개의 눈이 안정적으로 보이면 정면 얼굴 가능성이 높다고 판단합니다.
- 한쪽 눈만 보이면 측면 얼굴 가능성을 높게 봅니다.

### 3. 코 감지 방식
- 얼굴 중앙 세로 영역에서 nose response map을 만듭니다.
- 밝기 변화, 세로 gradient, 중앙 prior를 사용해 코 중심부와 코끝 후보를 찾습니다.

### 4. 입 감지 방식
- 얼굴 하단 영역에서 mouth response map을 만듭니다.
- 어두운 가로 구조와 박스 비율을 이용해 입 중심과 양쪽 입꼬리 후보를 찾습니다.

### 5. 얼굴 방향 분류 방식
- 눈 검출 개수
- 눈의 위치 대칭성
- 얼굴 에지 분포 좌우 차이
- 눈 구조의 납작함 정도

위 정보를 이용해 아래 상태 중 하나로 분류합니다.

- `frontal`
- `profile-left`
- `profile-right`
- `occluded`
- `eyes_closed`

### 6. 영역 분할 방식
아래 주요 포인트를 기준으로 얼굴 구역을 나눕니다.

- `forehead_center`
- `left_eye_center`
- `right_eye_center`
- `nose_bridge_top`
- `nose_tip`
- `mouth_left`
- `mouth_center`
- `mouth_right`
- `chin`

이 포인트들을 연결해서 아래 영역을 시각화합니다.

- forehead
- left_eye_zone
- right_eye_zone
- nose
- mouth
- jaw

---

## 🧪 실행 방법

### 1. AI 서버 실행
프로젝트 루트 기준:

```powershell
.\ai\venv\Scripts\python.exe .\ai\main.py
```

### 2. 백엔드 실행

```powershell
cd .\backend\backend_spring
.\gradlew.bat bootRun
```

### 3. 크롬 확장 실행
- 크롬에서 `chrome://extensions` 접속
- 개발자 모드 활성화
- `압축해제된 확장 프로그램을 로드합니다` 선택
- 프로젝트 루트 폴더 로드

### 4. 검사 확인
- 웹페이지의 이미지 또는 비디오 위의 `🔍` 버튼 클릭
- 백엔드와 AI 서버가 실행 중이어야 정상 동작

---

## 🗂️ 검사 결과 저장 위치

### 📁 루트 저장 폴더
- `images/analysis`
- `images/faces`

### 📁 `images/analysis/overlays`
저장 내용:

- 원본 이미지 위에 얼굴 박스와 기본 검출 결과만 표시한 이미지

파일 예시:

- `xxxx_overlay.jpg`

### 📁 `images/analysis/anchor_maps`
저장 내용:

- 얼굴 anchor graph 시각화 이미지
- forehead / eye / nose / mouth / jaw 영역 표시
- keypoint 표시
- keypoint 약어 표시
- detected / estimated 구분 시각화

파일 예시:

- `xxxx_analysis.jpg`

### 📁 `images/analysis/response_maps/eyes`
저장 내용:

- 눈 탐지를 위한 eye response heatmap 이미지

파일 예시:

- `xxxx_eye_response.jpg`

### 📁 `images/analysis/response_maps/nose`
저장 내용:

- 코 탐지를 위한 nose response heatmap 이미지

파일 예시:

- `xxxx_nose_response.jpg`

### 📁 `images/analysis/response_maps/mouth`
저장 내용:

- 입 탐지를 위한 mouth response heatmap 이미지

파일 예시:

- `xxxx_mouth_response.jpg`

### 📁 `images/analysis/metadata`
저장 내용:

- 전체 분석 결과 JSON
- pose 정보
- bbox
- keypoints
- analysisConnections
- analysisRegions
- quality 점수
- featureSummary
- deepfakeFeatures
- trainingDatasetCandidate
- 생성된 파일 경로 정보

파일 예시:

- `xxxx_analysis.json`

### 📁 `images/faces`
저장 내용:

- 검출된 얼굴 crop 이미지
- 이후 학습 데이터 또는 feature 추출 입력으로 재사용 가능

파일 예시:

- `xxxx_face_1.jpg`

---

## 🧾 JSON 안에 들어가는 주요 데이터

### `bbox`
- 얼굴 박스 위치와 크기

### `pose`
- 얼굴 방향 분류 결과
- `label`, `confidence`, `reason`

### `quality`
- blur
- brightness
- contrast
- detectedPointRatio
- 최종 품질 label

### `keypoints`
- 각 포인트의 좌표
- `source: detected | estimated`
- confidence
- reason

### `analysisConnections`
- 포인트 간 연결 정보

### `analysisRegions`
- 얼굴 내부 영역 분할 정보

### `trainingSample`
- 향후 학습용 데이터셋으로 사용할 수 있도록 정규화한 point 정보

### `deepfakeFeatures`
현재 저장 중인 예시:

- geometry
- texture
- visibility

세부 항목 예시:

- eyeDistanceRatio
- noseMouthRatio
- mouthChinRatio
- centerAxisOffset
- edgeDensity
- noiseScore
- estimatedPointRatio
- eyeVisibility

---

## 🚧 아직 구현되지 않은 기능

### 🖥️ 프론트엔드
- 플러그인 `on / off` 토글
- 팝업 UI
- 실시간 상태 표시
- `프레임 추출 중 > 데이터 전송 중 > 판별 완료` 단계 안내
- 원본 SNS 피드 위 상시 자동 검사
- 최종 결과 경고 배지 오버레이
- 플러그인 설정 화면

### 🗄️ 백엔드
- 메시지 큐 기반 비동기 처리
- 대기열 제어 및 트래픽 완화
- 워커 분리 구조
- 운영용 DB 강화
- 실시간 상태 push
- 실패 재시도 정책

### 🤖 AI
- 실제 딥페이크 판별 모델
- PyTorch / TensorFlow 기반 경량 모델 구축
- 학습 파이프라인
- 비디오 다프레임 판별
- 모델 성능 평가 지표 관리
- 딥페이크 최종 확률 계산 로직

---

## ⚠️ 현재 한계 / 해결해야 할 오류

### 1. 측면 얼굴 정확도 한계
- `profile-left`, `profile-right` 보정은 들어갔지만 아직 완벽하지 않습니다.
- 한쪽 눈만 보이거나 코/입이 많이 가려진 경우 포인트가 흔들릴 수 있습니다.

### 2. 눈 감은 얼굴 처리 한계
- eyes_closed 분류는 일부 반영되어 있으나, 실제 완전 감긴 눈과 반쯤 감긴 눈 구분은 아직 약합니다.

### 3. 코/입 포인트 일부는 여전히 추정값
- response evidence가 약한 경우 `estimated`로 들어갑니다.
- 따라서 모든 포인트가 실제 검출된 landmark 수준 정확도는 아닙니다.

### 4. 비디오 처리 한계
- 현재는 비디오 전체 분석이 아니라 보이는 프레임 캡처 기반입니다.
- 시간축 기반 판단은 아직 없습니다.

### 5. 딥페이크 판별은 아직 미구현
- 현재 AI는 얼굴 분석 및 feature 추출 단계입니다.
- 실제 deepfake / real 분류 모델은 아직 붙지 않았습니다.

### 6. 프론트 UX 미완성
- 현재 결과는 alert 기반이라 사용자 경험이 좋지 않습니다.
- 팝업 기반 진행 상태 표시가 필요합니다.

### 7. 백엔드는 아직 동기 처리
- 현재는 요청이 들어오면 즉시 AI 서버를 호출하는 구조입니다.
- 트래픽이 커지면 병목이 생길 수 있습니다.

---

## 🛠️ 앞으로 우선적으로 개선할 사항

### 1순위
- 크롬 확장 팝업 UI 추가
- on/off 토글 추가
- 실시간 진행 상태 표시 추가

### 2순위
- 백엔드 메시지 큐 기반 비동기 처리로 전환
- 요청 대기열 및 상태 관리 고도화

### 3순위
- AI의 profile 전용 anchor graph 보정 강화
- eyes_closed 보정 강화
- detected / estimated 정확도 개선

### 4순위
- PyTorch 또는 TensorFlow 기반 경량 딥페이크 판별 모델 추가
- 현재 저장되는 `trainingSample`, `deepfakeFeatures`를 활용한 학습 데이터셋 구성

---

## 📎 팀원 확인 포인트

팀원이 이 PR을 볼 때 우선 확인하면 좋은 위치:

- 크롬 확장 동작: `content.js`
- 백엔드 API 흐름: `backend/backend_spring/.../DetectionController.java`
- AI 분석 로직: `ai/main.py`
- 분석 결과 예시: `images/analysis/metadata`, `images/analysis/anchor_maps`

---

## 🎯 현재 PR 한 줄 요약
**브라우저 확장 → 백엔드 → AI 서버**까지의 기본 연동을 완료했고,  
AI 쪽은 **오리지널 pose-aware 얼굴 anchor graph 기반 분석 파이프라인**과  
**시각화 / JSON 저장 구조 / 딥페이크 확장용 feature 저장 구조**까지 구현한 상태입니다.
