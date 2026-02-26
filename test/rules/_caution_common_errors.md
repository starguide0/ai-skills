# 자주 발생하는 오류 패턴 및 주의사항

> 이 파일은 `remind_caution.py` PostToolUse Hook이 자동으로 파싱한다.
> 각 섹션 바로 위에 `<!-- keywords: kw1, kw2 -->` 형식으로 키워드를 지정한다.

---

<!-- keywords: api, stimulus, http, endpoint, curl -->
## API 호출 시 주의사항

- **curl 직접 사용 금지**: `stimulus_executor.py`를 사용해야 함. curl은 결과 파일 생성 안 됨 → hook이 stimulus.json 미존재로 차단
- **절대 경로 필수**: `--output` 인자는 반드시 `{ctx.ticket_folder}/partial_results/TC-{id}_stimulus.json` 형식 (상대경로 CWD 위험)
- **응답 전체 저장 금지**: `verdict_calculator.py`에서 검증 대상 필드만 `--expected`에 지정
- **Content-Type 자동 추가**: stimulus_executor.py가 자동으로 `Content-Type: application/json` 추가. 중복 지정 불필요

---

<!-- keywords: auth, token -->
## 인증 토큰 처리 주의사항

- **auth_body 파일 저장 금지**: loginId/password가 포함된 auth_body는 partial_results/ 및 임의 파일에 저장 금지
- **특수문자 처리**: password에 `!`, `@`, `#` 등 포함 시 echo/printf 대신 반드시 `python3 -c "import json; print(json.dumps(...))"` 사용
- **컨텍스트 압축 후 복원**: `auth_url` → `test/_shared/환경/API_엔드포인트.md`, `auth_body` → `test/_shared/환경/계정.md`에서 재구성
- **토큰 유효기간**: stimulus_executor.py로 인증 후 토큰은 세션 내에서만 유효. 장시간 후 재인증 필요

---

<!-- keywords: query, mcp_postgres, limit -->
## DB 쿼리 주의사항

- **LIMIT 필수**: 운영 DB 쿼리 시 반드시 `LIMIT` 절 추가. 전체 테이블 스캔은 타임아웃 및 부하 발생
- **읽기 전용 MCP**: `mcp__postgres_*__query`는 SELECT만 허용. DML(INSERT/UPDATE/DELETE) 실행 시 오류
- **스키마 prefix 필수**: 테이블명에 스키마 prefix 필요 (예: `public.outbound_order`, `wms.container_lifecycle`)
- **cross-DB 참조 불가**: 각 MCP는 단일 DB에만 연결. wms-outbound 쿼리에서 wms-inventory 테이블 직접 JOIN 불가

---

<!-- keywords: join, inner_join, left_join -->
## JOIN 쿼리 주의사항

- **JOIN 방향 주의**: INNER JOIN은 양쪽에 매칭되는 행만 반환. 매핑이 없는 경우 LEFT JOIN 사용
- **extra_join 타입 구분**:
  - `data_requirement.extra_joins` (tc_spec): 배열 `[]` — 여러 JOIN 절 목록
  - `expected.fields[].extra_join` (tc_spec): 문자열 — 단일 JOIN 절
- **N:M 관계**: JOIN 시 행 수 증가 주의. `DISTINCT` 또는 서브쿼리로 중복 제거 필요

---

<!-- keywords: null, is_null -->
## NULL 처리 주의사항

- **NULL ≠ 빈 문자열**: PostgreSQL에서 `NULL`과 `''`은 다름. `IS NULL` vs `= ''` 구분 필수
- **집계 함수**: `COUNT(*)` vs `COUNT(column)` — NULL이 있는 컬럼은 COUNT에서 제외됨
- **data_requirement.where null**: WHERE 조건이 null이면 `1=1`로 대체 (전체 조회) + WARNING 출력
- **behavioral_check 조건**: `is_null` assert는 필드가 존재하지 않을 때도 PASS 처리됨 (not found = treated as null)

---

<!-- keywords: state, enum -->
## 상태값(enum) 처리 주의사항

- **상태 전이 순서**: 잘못된 상태에서 API 호출 시 400/422 오류. behavioral_check로 사전 검증 필수
- **enum 대소문자**: PostgreSQL enum은 대소문자 구분. `'ACTIVE'` ≠ `'active'`
- **상태 이름 vs 코드**: DB에는 코드(`01`, `CREATED`)가, API 응답에는 이름(`"CREATED"`)이 올 수 있음
- **behavioral_check verdict PASS 조건**: 현재 상태가 테스트 전제조건을 만족하는 경우만 PASS

---

<!-- keywords: timestamp -->
## 타임스탬프 처리 주의사항

- **시간대 주의**: DB는 UTC, 한국 시간 = UTC+9. `created_at > NOW() - INTERVAL '1 hour'` 조건 시 시간대 맞춤 필요
- **millisecond vs second**: API 응답 타임스탬프는 ms 단위일 수 있음 (epoch milliseconds)
- **updated_at 갱신 여부**: 상태 변경 후 `updated_at`이 바뀌는지 검증 쿼리에 포함 권장

---

<!-- keywords: cross_service, outbound, inbound, inventory, job, metadata -->
## 크로스 서비스 DB 쿼리 주의사항

- **서비스별 MCP 분리**: wms-outbound(`mcp__postgres_outbound__query`), wms-inbound(`mcp__postgres_inbound__query`), wms-inventory(`mcp__postgres_inventory__query`), wms-job(`mcp__postgres_job__query`), wms-metadata(`mcp__postgres_metadata__query`)
- **ID 의미 확인**: 동일한 ID가 서비스마다 다른 의미를 가질 수 있음 (`.claude/architecture/data-contracts.json` 참조)
- **Tote 코드 prefix**: TT prefix (예: `TT0000000026496`). container_code 컬럼에 저장
- **외래키 없음**: 마이크로서비스 간 DB 외래키 없음. 애플리케이션 레벨에서만 연계
