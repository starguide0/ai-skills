# 테스트 결과 근거 작성 가이드라인

> 테스트 스킬에서 Pass/Fail 결과에 대한 논리적 근거를 제공하여 개발자의 신뢰와 이해를 높입니다.

## 🎯 목적

1. **투명성**: 왜 Pass/Fail인지 명확한 증거 제공
2. **재현성**: 개발자가 동일한 검증을 직접 수행 가능
3. **디버깅**: Fail 시 근본 원인을 빠르게 파악
4. **신뢰성**: 테스트 결과에 대한 신뢰도 향상

---

## ✅ Pass 근거 작성 규칙

### 규칙 1: 기대값과 실제값을 명시

❌ **나쁜 예**
```markdown
TC-001: 데이터 생성 확인
결과: ✅ PASS
```

✅ **좋은 예**
```markdown
TC-001: 자식 엔티티 3개 생성 확인
결과: ✅ PASS

**[Pass 근거]**
1. ✅ 데이터 생성 확인
   - 기대: child_entity 3개 생성
   - 실제: 3개 생성 확인
   - 증거:
     ```sql
     SELECT COUNT(*) FROM child_entity
     WHERE parent_entity_id = 'PARENT-001'
     -- 결과: 3
     ```
```

### 규칙 2: 검증 쿼리 또는 API 응답 포함

✅ **DB 검증 예시**
```markdown
2. ✅ 수량 검증
   - 기대: ITEM-A: 5개, ITEM-B: 3개
   - 실제: ITEM-A: 5개, ITEM-B: 3개
   - 증거:
     ```sql
     SELECT item_id, quantity
     FROM child_entity
     WHERE parent_entity_id = 'PARENT-001'
     ORDER BY item_id

     | item_id | quantity |
     |---------|----------|
     | ITEM-A  | 5        |
     | ITEM-B  | 3        |
     ```
```

✅ **API 검증 예시**
```markdown
3. ✅ API 응답 검증
   - 기대: HTTP 200, entityCode 반환
   - 실제: 200 OK, entityCode: "ENTITY-001"
   - 증거:
     ```json
     POST /api/entities/assign
     Response: {
       "status": "success",
       "entityCode": "ENTITY-001",
       "itemCount": 3
     }
     ```
```

### 규칙 3: 사이드이펙트 검증

✅ **사이드이펙트 검증 예시**
```markdown
4. ✅ 수량 증가 확인
   - 기대: processed_quantity 증가 (0 → 8)
   - 실제: 0 → 8 증가 확인
   - 증거:
     ```sql
     -- 변경 전
     SELECT processed_quantity
     FROM source_entity
     WHERE source_entity_id = 'SOURCE-001'
     -- 결과: 0

     -- 변경 후 (재조회)
     -- 결과: 8
     ```
```

### 규칙 4: 타임스탬프 및 상태 전이

✅ **상태 전이 검증 예시**
```markdown
5. ✅ 상태 전이 정상
   - 기대: entity_state: NULL → ASSIGNED
   - 실제: ASSIGNED 확인
   - 타임스탬프: 2026-02-12 10:15:23+09
   - 이벤트: ENTITY_ASSIGNED
```

---

## ❌ Fail 근거 작성 규칙

### 규칙 1: 불일치 명확히 표시

✅ **좋은 예**
```markdown
TC-002: 수량 부족 시 예외 발생 확인
결과: ❌ FAIL

**[Fail 근거]**
1. ❌ 예외 미발생
   - 기대: InsufficientQuantityException 발생
   - 실제: 정상 처리 (200 OK)
   - 차이: 예외 핸들링 로직 누락 추정
```

### 규칙 2: 실패 지점 및 단계 명시

✅ **좋은 예**
```markdown
2. ❌ Step 3에서 실패
   - 단계: API 호출 (POST /api/resources/allocate)
   - 액션: ITEM-C 8개 할당 요청 (가용: 5개)
   - 에러: 예외 미발생, 잘못된 할당 진행
   - 로그:
     ```
     2026-02-12 10:15:23 INFO  ResourceService - Allocating 8 units
     2026-02-12 10:15:23 ERROR ResourceService - Available: 5, Required: 8
     2026-02-12 10:15:23 WARN  ResourceService - Insufficient resources but proceeding (BUG!)
     ```
```

### 규칙 3: 근본 원인 추정

✅ **좋은 예**
```markdown
**[근본 원인 분석]**
- 의심 코드: ResourceService.java:245
  ```java
  // 현재 코드 (추정)
  public void allocate(String itemId, int quantity) {
      // 수량 체크 로직 누락!
      resourceRepository.updateQuantity(itemId, quantity);
  }
  ```

- 문제: 가용량 부족 검증 로직 누락
- 재현 조건:
  1. available_quantity < required_quantity
  2. allocate() 호출 시 검증 없이 진행
```

### 규칙 4: 증거 자료 첨부

✅ **좋은 예**
```markdown
**[증거 자료]**
1. DB 상태 (실패 시점)
   ```sql
   SELECT * FROM source_entity
   WHERE item_id = 'ITEM-C'

   | item_id | quantity | processed_quantity |
   |---------|----------|--------------------|
   | ITEM-C  | 5        | 8 (잘못된 값!)    |
   ```

2. API 요청/응답
   ```
   POST /api/resources/allocate
   Request: { "itemId": "ITEM-C", "quantity": 8 }
   Response: 200 OK (예외 발생해야 함!)
   ```

3. 로그 파일
   - 경로: logs/{service-name}-{date}.log
   - 라인: 1523-1530
```

### 규칙 5: 개발자 액션 가이드

✅ **좋은 예**
```markdown
**[개발자 액션]**
1. 🔍 확인 필요
   - ResourceService.java:245 allocate() 메서드
   - 가용량 부족 검증 로직 존재 여부 확인

2. 🛠️ 수정 제안
   ```java
   public void allocate(String itemId, int quantity) {
       int available = getAvailableQuantity(itemId);
       if (available < quantity) {
           throw new InsufficientQuantityException(
               "Available: " + available + ", Required: " + quantity
           );
       }
       resourceRepository.updateQuantity(itemId, quantity);
   }
   ```

3. 📝 후속 조치
   - 단위 테스트 추가: ResourceServiceTest
   - 통합 테스트 추가: 가용량 부족 시나리오
   - 관련 티켓: PROJ-12345 업데이트
```

---

## 📊 근거 수준 (Level of Evidence)

### Level 1: 기본 (최소 요구)
- ✅ 기대값 vs 실제값
- ✅ Pass/Fail 판정 기준

### Level 2: 표준 (권장)
- ✅ Level 1 +
- ✅ 검증 쿼리 또는 API 응답
- ✅ 사이드이펙트 1개 이상 확인

### Level 3: 상세 (복잡한 TC)
- ✅ Level 2 +
- ✅ 타임스탬프 및 상태 전이
- ✅ 연쇄 영향 확인 (Kafka, 다른 테이블 등)
- ✅ 로그 증거

### Level 4: 전문가 (Fail 시 필수)
- ✅ Level 3 +
- ✅ 근본 원인 분석
- ✅ 코드 레벨 추정
- ✅ 재현 조건 명시
- ✅ 개발자 액션 가이드

---

## 🎯 테스트 케이스별 권장 레벨

| TC 유형 | 권장 레벨 | 예시 |
|---------|-----------|------|
| 단순 CRUD | Level 1-2 | 데이터 생성/조회 |
| 비즈니스 로직 | Level 2-3 | 상태 전이, 수량 계산 |
| 복잡한 흐름 | Level 3 | 다단계 프로세스 |
| **Fail 케이스** | **Level 4** | 모든 실패 케이스 |
| 크리티컬 TC | Level 3-4 | 수량 차감, 금액 계산 |

---

## 📝 템플릿

### Pass 템플릿
```markdown
TC-XXX: {테스트 케이스 명}
결과: ✅ PASS

**[Pass 근거]**
1. ✅ {검증 항목 1}
   - 기대: {expected}
   - 실제: {actual}
   - 증거: {query or response}

2. ✅ {검증 항목 2}
   - 기대: {expected}
   - 실제: {actual}
   - 증거: {query or response}

3. ✅ 사이드이펙트 검증
   - 항목: {affected_table/field}
   - 변경: {before} → {after}
   - 증거: {query}

**[검증 방법]**
- {verification method}
```

### Fail 템플릿
```markdown
TC-XXX: {테스트 케이스 명}
결과: ❌ FAIL

**[Fail 근거]**
1. ❌ {불일치 항목}
   - 기대: {expected}
   - 실제: {actual}
   - 차이: {diff}

2. ❌ 실패 단계
   - 단계: Step {N}
   - 액션: {action}
   - 에러: {error message}

**[근본 원인 분석]**
- 의심 코드: {file:line}
- 문제: {issue description}
- 재현 조건: {reproduction steps}

**[증거 자료]**
- DB 상태: {query result}
- API 응답: {response}
- 로그: {log excerpt}

**[개발자 액션]**
1. 🔍 확인 필요: {files/methods}
2. 🛠️ 수정 제안: {suggestion}
3. 📝 후속 조치: {follow-up tasks}
```

---

## 🚨 주의사항

### DO ✅
- 모든 검증 항목에 증거 제공
- Fail 시 Level 4 근거 필수
- 쿼리 결과는 표 형식으로 보기 좋게 정리
- 타임스탬프는 timezone 포함 (KST +09)
- 개발자가 재현 가능한 정보 제공

### DON'T ❌
- "정상 동작함" 같은 모호한 표현
- 증거 없이 Pass/Fail 판정
- 에러 메시지 생략
- 코드 추정 없이 "버그인 것 같다"
- 개발자에게 "직접 확인해보세요"

---

## 💡 자동화 팁

### 검증 쿼리 템플릿

```sql
-- 생성 확인
SELECT COUNT(*) as count FROM {table}
WHERE {condition}
-- 기대: count = {N}

-- 값 검증
SELECT {columns} FROM {table}
WHERE {condition}
-- 기대: {expected_values}

-- 변경 전후 비교
SELECT
    '{before}' as checkpoint,
    {columns}
FROM {table}
WHERE {condition}
-- 변경 전 실행

-- (작업 수행)

SELECT
    '{after}' as checkpoint,
    {columns}
FROM {table}
WHERE {condition}
-- 변경 후 실행, before와 비교
```

---

## 📚 실제 예시

[test-evidence-examples.md](test/_shared/rule/examples/test-evidence-examples.md) 참조

---

**중요**: 테스트 스킬은 이 가이드라인을 따라 모든 TC에 대해 근거 기반 결과를 생성해야 합니다.
