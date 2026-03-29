# Kibana 로그 분석 가이드
- **URL**: https://kibana.test.com
- **환경**: prod
- **추천 쿼리**:
  - `message: "*ERROR*"`
  - `traceId: "INC-20260319-001"` (만약 traceId를 알 수 있는 경우)
  - `serviceName: "unknown"`
