---
name: test-evidence
description: This skill should be used when the user asks about "테스트 근거", "test evidence", "Pass/Fail 근거", "test result quality", "how to write test results", "테스트 결과 작성법", discusses test documentation standards, verification methods, or asks "어떻게 써야 해", "뭘 포함해야 해" regarding test results.

Parameters: None (guidance/reference skill)

version: 1.1.0
---

# Test Evidence Skill

## Purpose

테스트 결과 작성 시 Pass/Fail 근거를 논리적이고 투명하게 작성하는 방법을 안내합니다.

> 핵심 원칙: "개발자가 당신의 근거만 보고 버그를 재현하고 수정할 수 있어야 한다."

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| (없음) | - | - | 이 스킬은 참조/가이드 스킬로, 데이터 입력을 받지 않음 |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| Pass/Fail 근거 작성 가이드라인 | test-reporter, test-run | 참조용 가이드라인 (데이터 전달 아님) |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- Level 1-4 근거 수준 정의
- 테스트 유형별 증거 형식 (DB Before/After, 모바일 API 시뮬레이션, UI 캡쳐)
- Best Practices (DO/DON'T 규칙)
- 자가 점검 질문 (투명성, 재현성, 실행성)

---

## 3가지 질문 (자가 점검)

근거 작성 후 스스로에게 물어보세요:

1. **투명성**: 내 근거를 보고 누구나 같은 결론에 도달하는가?
2. **재현성**: 개발자가 내 증거로 직접 검증할 수 있는가?
3. **실행성**: Fail 시, 개발자가 즉시 수정 작업에 착수할 수 있는가?

---

## 상세 가이드라인 참조

- `.claude/skills/test/rules/_guidelines_test_evidence.md` — Pass/Fail 근거 규칙, Level 1-4 수준, 템플릿, 유형별 증거 형식, Best Practices
- `test/examples/test-evidence-examples.md` — 프로젝트별 실제 예시
