# 전체 단지 수집 및 정기 갱신
기존 저장본은 K-APT 목록 110개, 지도용 complexes.csv 86개입니다.
기존 코드는 좌표 변환 실패 단지를 제외했습니다. 당시 오류 로그가 없어 트래픽 초과였는지는 확정할 수 없습니다.

## 수정 동작
totalCount까지 페이지 수집, 반복 페이지/조기 종료 검출, 429/일시적 서버/네트워크 오류 최대 5회 재시도,
도로명 실패 시 지번 주소 조회, 성공 상세/좌표 체크포인트 저장과 재실행 이어받기를 지원합니다.
전체 좌표가 확인되어야 complexes.csv를 교체합니다.
data/apartments_fetch_status.json에 전체/성공/누락 및 이유를 기록합니다.
완료 후 다음 실행은 API를 다시 조회합니다. API 인증키 자체를 갱신하는 기능은 아닙니다.

## 로컬 실행
루트 .env에 DATA_GO_KR_KEY와 VWORLD_API_KEY를 설정합니다.
python scripts/fetch_apartments.py 성공 후 python scripts/build_index.py를 실행해야 화면도 갱신됩니다.
필요 패키지: pip install pandas geopandas osmnx scikit-learn requests
일일 한도 초과는 할당량 회복 후 재실행해야 합니다.
주소 오류·API에 없는 신규 단지는 수동 확인/원천 정정이 필요합니다.
K-APT가 제공하지 않는 비의무관리·미등록 공동주택까지 이 API만으로 보장할 수 없습니다.
complexes_pending.csv의 수동 후보는 K-APT 목록과 별개이며 임의 합성하지 않습니다.

## GitHub 자동 갱신
Settings → Secrets and variables → Actions → Repository secrets에
DATA_GO_KR_KEY와 VWORLD_API_KEY를 등록합니다. 목록/기본정보 양쪽 활용 승인이 필요합니다.
키는 코드에 커밋하지 마세요.
Actions → Refresh apartment and commute data → Run workflow로 실행할 수 있습니다.
매주 월요일 한국시간 04:17에 예약되며 GitHub 사정에 따라 지연될 수 있습니다.
성공 시 단지와 기존 보행망/학교/버스 자료를 사용한 통학 결과를 refreshed-data artifact로 남깁니다.
반복 실행의 자동 커밋은 별도 승인 전까지 비활성입니다.
실패 시 화면용 결과를 내보내지 않고 체크포인트를 캐시에 저장하며 보고서를 artifact로 남깁니다.
캐시가 소실되면 처음부터 다시 조회합니다.
브랜치 보호 또는 Actions 쓰기 제한이 있으면 직접 push가 실패할 수 있습니다.
예약 실행은 기본 브랜치에서 작동하며 공개 저장소 장기 비활성 시 중지될 수 있습니다.

현재 예약 수집 범위는 공동주택, 버스 정류장·노선과 통학 분석입니다. 학교·도로망·사고 자료는 기존 저장본입니다.
버스 API 캐시는 24시간 후 재조회합니다. 일부 API가 실패하면 기존 정상 항목을 보존하며 data/raw/bus.json의 collection에 실패 건수를 기록합니다.
각 데이터원의 승인과 별도 검증 없이 전체 원천의 자동갱신을 보장하지 않습니다.

## 실제 수집 검증 (2026-10-23)
로컬 .env를 사용한 실제 수집에서 K-APT 110개 중 110개 좌표를 확보했습니다.
학교알리미 키는 미설정이므로 기존 학교 자료를 사용합니다.
API 키와 체크포인트, 로컬 패키지, 로그는 커밋하지 않습니다.
경량 index-lite.json도 상세 데이터와 같은 계산에서 생성하며, 브라우저에서 캐시 재검증을 요청합니다.
GitHub 예약 수집에 필요한 Secrets는 로컬 .env와 별개입니다. 로컬 키를 GitHub에 자동 업로드하지 않습니다.

## 보안과 로컬 미리보기
.env 및 .env.* (샘플 제외), 실행 패키지(.runtime), 캐시·로그·체크포인트는 Git에서 제외됩니다.
.vercelignore는 웹 화면과 공개 분석 파일만 허용하므로 원본 자료·비밀파일은 업로드 대상에서 제외됩니다.
로컬 서버는 python serve.py로 실행하며 .env, .git, 원본 경로는 404로 차단됩니다.
지도용 web/config.js에는 공개 Client ID만 허용하며 비밀키는 넣지 않습니다.

이번 실제 검증에서 버스 정류장 414개와 노선 상세 131개를 수집했고 실패 호출은 0건입니다.
예약 작업 결과는 공개 분석 파일만 artifact로 내보내며 공동주택 상세 원본은 포함하지 않습니다.
학교 및 사고 정보는 이번 갱신에 포함되지 않습니다. KOROAD_API_KEY를 넣는 것만으로
기존 공공데이터포털용 사고 수집기가 기관 직접발급 API로 전환되지는 않습니다.
