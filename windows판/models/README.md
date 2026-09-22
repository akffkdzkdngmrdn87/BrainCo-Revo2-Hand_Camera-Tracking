# models — MediaPipe 손 랜드마크 모델

이 폴더에는 **파일이 커밋되어 있지 않습니다.** `hand_landmarker.task` 는 7.8MB 이고
구글이 공식 배포하므로, 저장소에 복사본을 두는 대신 내려받게 했습니다.

## 내려받기

`../설치.sh` 가 자동으로 처리합니다. 직접 받으려면:

```bash
curl -L -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

## 이 모델이 왜 별도 파일인가

MediaPipe 는 2023-03-01 자로 레거시 Solutions API(`mp.solutions.hands`) 지원을 종료하고
**Tasks API** 로 이관했습니다. Tasks API 는 모델 가중치를 라이브러리에 내장하지 않고
`.task` 파일로 분리합니다. 따라서 `pip install mediapipe` 만으로는 동작하지 않으며,
이 파일이 반드시 필요합니다.

| 항목 | 값 |
|---|---|
| 파일명 | `hand_landmarker.task` |
| 크기 | 약 7.8 MB |
| 정밀도 | float16 |
| 출력 | 손 21개 관절 3D 좌표 + 좌우 판별 |
| 배포 | Google AI Edge — https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker |
