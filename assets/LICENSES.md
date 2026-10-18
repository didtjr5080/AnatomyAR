# 자산 출처 및 제공 조건

## 해부학 PNG

- 제작일: 2026-10-18.
- 제작 도구: OpenAI 내장 imagegen. 외부 웹 이미지를 복사하지 않았습니다.
- `source/atlas-v1.png`: 최초 생성, 보관용. 런타임에서 사용하지 않습니다.
- `source/atlas-v2.png`: 전완 요골·척골 표현 수정. 중앙/오른쪽 부위 원본.
- `source/atlas-left.png`: 독립적으로 생성한 왼쪽 부위 원본. 광원 방향을 맞추도록 요청했습니다.
- `source/atlas-flex.png`: 양측 상완·허벅지 굽힘 변형 원본. 최초 상완의 잘못된 무릎 같은 형태를 수정한 출력만 사용합니다.
- 프롬프트: `source/prompts.json`, `source/left-prompt.txt`.
- 굽힘 생성·수정 프롬프트: `source/flex-prompts.json`.
- 수정/가공: RGBA 원본의 셀 분리와 투명 여백 축소. 원본 alpha 보존. 런타임 premultiplication, 회전/스케일/부분 affine, 알파 합성.
- 생성 출력은 본 프로젝트의 사용·수정·재배포를 위한 자산으로 제공합니다. 별도의 제3자 3D 모델/사진 라이선스는 적용하지 않았습니다.
- 실제 3D 메시·재질 파일에서 렌더한 자료가 아닙니다. 제공 가능한 편집 원본은 PNG와 프롬프트이며 `.blend`/메시 파일은 없습니다.
- AI 생성 자산의 해부학적 정확성·독점성·권리 보호 가능성을 보증하지 않습니다. 행사 전 시각/해부학 검수 필요.

## MediaPipe 모델

Google 공식 Lite v1 모델. 모델 카드의 LICENSED UNDER: Apache License, Version 2.0.
`models/model_card.pdf`, `models/LICENSE-2.0.txt`, `models/manifest.json`에 출처/라이선스/체크섬을 포함했습니다.
모델을 수정하지 않았습니다.

## 글꼴 및 코드 라이브러리

Windows 맑은 고딕은 설치된 OS에서 읽습니다. 글꼴 파일을 프로젝트에 복사/재배포하지 않습니다.
PySide6/Qt는 설치 패키지의 LGPL/GPL/상용 라이선스 조건을, 나머지 라이브러리는 각 배포물의 LICENSE를 따릅니다.
고정 버전 목록은 `requirements.txt`입니다. 바이너리 패키징을 추가할 때 해당 배포 조건과 고지를 확인해야 합니다.
