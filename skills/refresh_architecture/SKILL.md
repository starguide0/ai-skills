---
name: refresh-architecture
description: 프로젝트의 아키텍처 메타데이터를 실제 코드베이스를 분석하여 갱신합니다. (.architecture/ 전용 폴더 관리)
user-invocable: true
disable-model-invocation: true
allowed-tools:
  - run_command, Bash, Bash(git:*)
  - list_dir, Glob
  - view_file, Read
  - write_to_file, Write
  - multi_replace_file_content, replace_file_content, Edit
  - grep_search, Grep
  - search_web, WebSearch
---

# 🏗️ 아키텍처 갱신 (Architecture Refresh)

프로젝트의 아키텍처 메타데이터를 실제 코드베이스와 DB 스키마를 분석하여 갱신합니다. 모든 결과물은 프로젝트 루트의 `.architecture/` 폴더에 저장됩니다. 이 스킬은 service metadata를 생성하고, CLI 질의 인터페이스를 제공하는 구현체입니다.

## 🛠️ 분석 절차 (`/refresh-architecture`)

사용자님의 지시에 따라 아래 단계를 순차적으로 실행합니다:

1. **Phase 1: Scouting (`init`)**
   - `.architecture/configuration.json`이 없으면 생성하고 기술 스택을 파악합니다.
   
2. **Phase 2: Scanning (`skeleton`)**
   - 이 스킬의 `scripts/arch-manager.py`를 사용하여 물리적인 코드 구조(Mini-AST)를 추출하여 `.architecture/metadata/skeleton.json`에 저장합니다.
   - 스크립트 경로: `$CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py`
   - 결과적으로 프로젝트는 file provider(`.architecture/`)와 cli provider(`arch-manager.py`)를 함께 갖게 됩니다.

3. **Phase 3-7: Semantic Extraction & Flow Analysis**
   - 추출된 구조와 소스코드를 참조하여 비즈니스 로직과 도메인 의미를 해석합니다.
   - **Behavioral Flow Extraction**: `arch-manager.py flow`를 사용하여 진입점부터의 호출 체인과 비즈니스 정책(분기)을 추출하고 Mermaid 다이어그램을 생성합니다.
   - **Domain Glossary Mapping**: `arch-manager.py glossary`를 통해 기술 용어를 현장(Field) 용어로 변환하여 인덱싱 품질을 높입니다.
   - 결과물은 `.architecture/metadata/` 폴더에 `flow-*.json`, `domain-glossary.json` 등으로 저장됩니다.

4. **Phase 8: Sync (`update-state`)**
   - 최종 분석 상태와 커밋 해시를 `.architecture/refresh-state.json`에 기록합니다.

---

## 🔍 데이터 탐색 가이드 (Discovery Guide for AI)

대규모 프로젝트에서 모든 메타데이터를 읽는 것은 비효율적입니다. 아래의 **'Pull-based'** 전략을 따르십시오:

1. **Scouting (전체 요약 확인)**:
   - `python3 $CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py query` (인자 없이 실행)
   - `.architecture/metadata-index.json` 정보를 읽어 프로젝트에 어떤 서비스와 테이블이 있는지 한눈에 파악합니다.

2. **Targeted Query (상세 정보 추출)**:
   - 특정 서비스나 테이블의 스키마가 필요할 때만 `--service` 또는 `--table` 옵션을 사용합니다.
   - 예: `python3 $CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py query --service order-svc --table orders`

3. **Behavioral Flow Analysis (기능 흐름 분석)**:
   - 특정 기능의 비즈니스 로직과 정책 분기를 나열하려면 `flow`를 사용하십시오.
   - 예: `python3 $CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py flow --service order-svc`

4. **Glossary Management (용어집 관리)**:
   - 코드의 기술 용어를 비즈니스 용어로 매핑하거나 제안하려면 `glossary`를 사용하십시오.
   - 예 (용어 추출 제안): `python3 $CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py glossary propose`
   - 예 (용어 목록 확인): `python3 $CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py glossary list`

5. **Handling Auto-Summary**:
   - 결과가 너무 많으면 자동으로 요약 정보만 반환됩니다. 이 경우 `--table` 또는 `--keyword`를 더 정밀하게 사용하여 데이터를 좁히십시오.

---

> [!NOTE]
> 이 명령은 현재 `.architecture/` 표준 경로를 기준으로 작동합니다. 모든 데이터는 지정된 `.architecture/` 하위 경로에서만 관리됩니다.
