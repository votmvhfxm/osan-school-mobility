# 현장 수집 데이터 스키마 (팀 직접 수집, 가점용)

모든 파일 UTF-8 CSV, 좌표는 WGS84(위도 lat, 경도 lon). 현장 GPS 또는 좌표를 제공하는 도구에서 위도·경도를 확인한다. 네이버 지도 배경 표시만으로 좌표 수집 기능이 제공되지는 않으며, 주소 변환은 별도 Geocoding 연동이 필요하다.

## field_photos.csv — 현장 사진
| 열 | 형식 | 예 |
|---|---|---|
| photo_id | 문자열 | P001 |
| taken_at | YYYY-MM-DD HH:MM | 2026-10-16 07:45 |
| lat, lon | 실수 | 37.1912, 127.0701 |
| file | data/field/photos/ 아래 파일명 | P001.jpg |
| issue | 보도없음 / 무신호횡단 / 불법주정차 / 공사구간 / 킥보드방치 / 기타 | 보도없음 |
| note | 자유 기술(관찰 사실만) | 보도 없이 갓길 보행 |

## bus_wait_obs.csv — 등교시간 버스 실측 대기
| 열 | 형식 | 예 |
|---|---|---|
| obs_date | YYYY-MM-DD | 2026-10-16 |
| stop_name | 정류장명 | 세교2지구 ○○ |
| stop_lat, stop_lon | 실수 | |
| route | 노선 번호 | 5-1 |
| arrive_at | HH:MM:SS 정류장 도착 | 07:41:10 |
| board_at | HH:MM:SS 승차(또는 버스 도착) | 07:52:30 |
| crowded | 0/1 만차로 못 탐 | 0 |

## kickboard.csv — 전동킥보드 방치 지점
| 열 | 형식 | 예 |
|---|---|---|
| obs_at | YYYY-MM-DD HH:MM | |
| lat, lon | 실수 | |
| count | 대수 | 3 |
| blocks_sidewalk | 0/1 보도 통행 방해 | 1 |

## survey.csv — 통학 설문 (구글폼 응답 시트를 CSV로 내려받아 열 이름만 맞춰 저장) (문항 원문: docs/survey_form.html)
| 열 | 구글폼 문항 | 형식 |
|---|---|---|
| timestamp | (자동) | |
| respondent | 응답자 | 학생 본인 / 보호자 |
| complex | 사는 단지 | 드롭다운(단지 목록 + 기타) |
| school | 다니는(배정된) 중학교 | 대호중 / 오산중 / 가수중 / 초등학생(예정) |
| grade | 학년 | 초6 / 중1 / 중2 / 중3 |
| mode_am | 등교 수단 | 도보 / 버스 / 자가용 / 자전거·킥보드 / 혼합 |
| time_min_self | 집→교문 실제 걸리는 시간(분) | 숫자 |
| bus_wait_min_self | 버스 이용 시 정류장 평균 대기(분) | 숫자, 미이용 시 공란 |
| bus_full | 만차로 못 탄 경험 | 자주 / 가끔 / 없다 / 미이용 |
| danger_spots | 위험하다고 느끼는 지점 | 체크박스(위험 구간 목록 상위 10~15곳 + 없음) |
| danger_other | 목록에 없는 위험 지점 | 단답(교차로·건물명) |
| detour_yes | 위험 때문에 일부러 돌아가는 길이 있다 | 예 / 아니오 |
| comment | 자유 의견 | 장문 |
개인식별정보(이름·연락처·학번)는 받지 않는다.
