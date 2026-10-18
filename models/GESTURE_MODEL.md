# Gesture Recognizer 모델 출처

- 제공: Google MediaPipe.
- 버전: Gesture Recognizer float16 v1, `gesture_recognizer.task`.
- 다운로드 URL과 SHA-256: `gesture_manifest.json`.
- 기능/API 설명: https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer/python
- 공식 모델 카드: https://storage.googleapis.com/mediapipe-assets/gesture_recognizer/model_card_hand_gesture_classification_with_faireness_2022.pdf
- 공식 검증 예제: https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/gesture_recognizer/python/gesture_recognizer.ipynb

앱에서는 CPU VIDEO 모드로 로컬 실행하며 기본 실행 중 모델을 다운로드하지 않습니다.
공식 예제 이미지의 온라인 검증은 `python -m scripts.validate_gestures`를 명시적으로 실행할 때만 수행합니다.
검증 이미지는 메모리에서만 처리하고 모델 분류 결과와 시간 수치만 기록합니다.
