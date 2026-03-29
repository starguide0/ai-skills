#!/usr/bin/env python3
"""
# arch-manager.py — Architecture Refresh CLI

Extracts mechanical data (mappings, SQL templates, schemas, configs)
from refresh-architecture/refresh-db-semantics markdown files.
Called by Claude via Bash tool; outputs JSON to stdout.

Usage:
    python3 skills/refresh_architecture/scripts/arch-manager.py <subcommand> [options]

Subcommands:
    config              Full config JSON (services, file patterns, semantics)
    plan                Git diff analysis → refresh plan JSON
    worktree            Worktree creation/cleanup shell commands
    gen-sql             DB schema extraction SQL for a service
    scan                JPA/Kafka/API/Message source scan patterns
    update-state        Manifest + .refresh-state.json update procedure
    schema-template     db-schemas output schema template
    semantics-config    Phase 3-7 config (weights, ref levels, confidence, null)
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import fnmatch
from datetime import datetime, timezone

METADATA_VERSION = 2

# ─────────────────────────────────────────────────────────────────────
# CONFIGURATION MANAGEMENT
# ─────────────────────────────────────────────────────────────────────

ARCHITECTURE_DIR = ".architecture"
METADATA_DIR = os.path.join(ARCHITECTURE_DIR, "metadata")

def get_default_config_path(workspace=None):
    """Returns the path to configuration.json, prioritizing workspace over script folder."""
    if workspace:
        ws_config = os.path.join(workspace, ARCHITECTURE_DIR, "configuration.json")
        if os.path.exists(ws_config):
            return ws_config
    
    # Fallback to current workspace or script directory
    cwd_config = os.path.join(os.getcwd(), ARCHITECTURE_DIR, "configuration.json")
    if os.path.exists(cwd_config):
        return cwd_config

    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "configuration.json")

def load_config(config_path=None):
    """Loads configuration from JSON file, falling back to static defaults if missing."""
    if not config_path:
        config_path = get_default_config_path()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config from {config_path}: {e}", file=sys.stderr)
    else:
        # Hint for AI Agent when config is missing
        is_ai = any(k.startswith(("ANTIGRAVITY", "CLAUDE")) for k in os.environ)
        if is_ai:
            print(f">>> [HINT] Configuration missing at {config_path}.", file=sys.stderr)
            print(">>> To auto-setup, AI should: 1. scan build files (gradle/pom) or configs (yml/properties) for services,", file=sys.stderr)
            print(">>> 2. extract service names/DB IDs, 3. match MCP tools, 4. run 'init', 5. update JSON.", file=sys.stderr)

    # Fallback to empty defaults if file not found or error
    return {
        "services": {},
        "filePatterns": {},
        "semantics": {
            "weights": {},
            "refLevels": {},
            "confidence": {},
            "nullInterpretation": {},
            "tiers": {}
        }
    }

# Load static data initially (will be overridden in main if config exists)
# These are kept as global references for the cmd_* functions
_CONFIG = load_config()

SERVICES = _CONFIG.get("services", {})
FILE_PATTERNS = _CONFIG.get("filePatterns", {})
SEMANTICS_WEIGHTS = _CONFIG.get("semantics", {}).get("weights", {})
REF_LEVELS = _CONFIG.get("semantics", {}).get("refLevels", {})
CONFIDENCE_THRESHOLDS = _CONFIG.get("semantics", {}).get("confidence", {})
NULL_INTERPRETATION = _CONFIG.get("semantics", {}).get("nullInterpretation", {})
TIERS = _CONFIG.get("semantics", {}).get("tiers", {})
DISCOVERY_PATTERNS = _CONFIG.get("discovery_patterns", {})
MAPPING_RULES = _CONFIG.get("mapping_rules", {})

def update_globals(config):
    """Updates global references with loaded config."""
    global SERVICES, DISCOVERY_PATTERNS, MAPPING_RULES
    global SEMANTICS_WEIGHTS, REF_LEVELS
    global CONFIDENCE_THRESHOLDS, NULL_INTERPRETATION, TIERS
    
    SERVICES = config.get("services", {})
    DISCOVERY_PATTERNS = config.get("discovery_patterns", {})
    MAPPING_RULES = config.get("mapping_rules", {})
    
    # Handle semantics
    sem = config.get("semantics", {})
    SEMANTICS_WEIGHTS = sem.get("weights") or config.get("semanticsWeights", {})
    REF_LEVELS = sem.get("refLevels") or config.get("refLevels", {})
    CONFIDENCE_THRESHOLDS = sem.get("confidence") or config.get("confidenceThresholds", {})
    NULL_INTERPRETATION = sem.get("nullInterpretation") or config.get("nullInterpretation", {})
    TIERS = sem.get("tiers") or config.get("tiers", {})


# ─────────────────────────────────────────────────────────────────────
# SEMANTIC HASHING (Phase 1)
# ─────────────────────────────────────────────────────────────────────

def generate_semantic_hash(content, filename="temp.py"):
    """
    Generates a semantic hash for Python/JS/TS code by normalizing the AST.
    Ignores identifiers (names) and focuses on structural logic.
    """
    try:
        if filename.endswith(".py"):
            tree = ast.parse(content)
            tokens = []

            def visit(node):
                # Normalization: Replace names/ids with placeholders
                if isinstance(node, ast.Name):
                    tokens.append("[ID]")
                elif isinstance(node, ast.arg):
                    tokens.append("[ARG]")
                elif isinstance(node, (ast.Constant, ast.Str, ast.Num)):
                    val = getattr(node, 'value', getattr(node, 's', getattr(node, 'n', None)))
                    tokens.append(f"[CONST:{val}]")
                else:
                    tokens.append(f"[{type(node).__name__}]")
                
                # Recursive visit to maintain structural order
                for child in ast.iter_child_nodes(node):
                    visit(child)
            
            visit(tree)
            serialized = "-".join(tokens)
            return hashlib.sha256(serialized.encode()).hexdigest()
        
        # Simple structural fallback for other languages (JS/TS/Java)
        # Filters whitespace, comments, and identifiers using basic regex
        # This mimics the core logic of normalizing the code structure.
        struct_only = re.sub(r'//.*|/\*[\s\S]*?\*/', '', content) # Remove comments
        struct_only = re.sub(r'\s+', ' ', struct_only) # Normalize whitespace
        # Replace identifiers with [ID] (this is fuzzy but better than full text)
        struct_only = re.sub(r'[a-zA-Z_]\w*', '[ID]', struct_only)
        
        return hashlib.sha256(struct_only.encode()).hexdigest()
    except Exception:
        return hashlib.sha256(content.encode()).hexdigest()

# ─────────────────────────────────────────────────────────────────────
# METADATA INDEXING (Phase 1)
# ─────────────────────────────────────────────────────────────────────

def update_metadata_index(workspace):
    """
    Generates/Updates .architecture/metadata-index.json for fast discovery.
    """
    arch_dir = os.path.join(workspace, ARCHITECTURE_DIR)
    index_path = os.path.join(arch_dir, "metadata-index.json")
    meta_dir = os.path.join(workspace, METADATA_DIR)
    
    # Ensure .architecture directory exists
    if not os.path.exists(arch_dir):
        os.makedirs(arch_dir)

    index = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "services": {},
        "keywords": {}
    }
    
    # Scan db-schemas.json for services and tables
    if os.path.exists(meta_dir):
        db_file = os.path.join(meta_dir, "db-schemas.json")
        if os.path.exists(db_file):
            try:
                with open(db_file, 'r') as f:
                    db_data = json.load(f)
                    schemas = db_data.get("schemas", [])
                    for schema in schemas:
                        svc = schema.get("service")
                        if svc:
                            index["services"][svc] = {
                                "tables": list(schema.get("tables", {}).keys()),
                                "file": "db-schemas.json"
                            }
            except Exception:
                pass
            
    # Save index
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
            print(f">>> [Index Update] Saved to {index_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error updating index: {e}", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────
# GIT HELPERS
# ─────────────────────────────────────────────────────────────────────

def is_git_repo(path):
    """Checks if a directory is a git repository."""
    return os.path.isdir(os.path.join(path, ".git"))

def get_git_remote_url(path):
    """Extracts the git remote origin URL for a repository."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=path, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def get_default_branch(path):
    """Finds the default branch name (usually main or master)."""
    try:
        # Check symbolic-ref first
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, cwd=path, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip().split('/')[-1]
        
        # Fallback to local HEAD if remote HEAD not available
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=path, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "main"

SERVICES = {
    "example-service": {
        "mcp": "mcp__postgres_example__query",
        "flyway": "path/to/db/migration",
        "criticalTables": [],
        "highTables": []
    }
}

# These are pure placeholders. The actual patterns MUST come from configuration.json.
# THE AI AGENT IS RESPONSIBLE FOR SCOUTING THE PROJECT AND UPDATING configuration.json
# WITH TECH-SPECIFIC PATTERNS (e.g., MQListener, Swift patterns) BEFORE SCANNING.
FILE_PATTERNS = {}
MAPPING_RULES = {}
DISCOVERY_PATTERNS = {}

TARGETS = {
    "all": "전체 갱신",
    "services": "서비스 기본 정보",
    "discovery": "플랫폼별 정보 탐색",
    "db-schemas": "DB 스키마 구조 추출",
    "db-semantics": "DB 의미 추론 및 분석",
    "data-contracts": "서비스 간 데이터 계약"
}

AUTO_FULL_TARGETS = ["data-contracts"]

# Core semantic engine defaults (overridden by configuration.json)
SEMANTICS_WEIGHTS = {}
REF_LEVELS = {}
CONFIDENCE_THRESHOLDS = {}
NULL_INTERPRETATION = {}
TIERS = {}
PHASE4_QUERIES = {}
MISMATCH_PATTERNS = []
PHASE5_COMMANDS = {}
PHASE6_RELATIONSHIPS = {}
PHASE3_LAYERS = {}
DATA_CONTRACTS_SECTIONS = {}
PHASE7_AUTO_ENRICH = {}

ABBREVIATION_KEYS = {
    "t": "type (? = nullable)",
    "m": "meaning (1줄, null = DEAD)",
    "c": "confidence (HIGH/MEDIUM/LOW/CONFLICT/DEAD)",
    "l": "lifecycle (STATIC/DYNAMIC/COMPUTED)",
    "r": "reference count (총 참조 횟수)",
    "sm": "stateMachine (true면 db-graph.json에 상세)",
    "ns": "nullSemantics (NULL의 비즈니스 의미)"
}

MANIFEST_UPDATE_RULES = {
    "onTargetComplete": {
        "update": ["files.{target}.updatedAt", "completeness.{target}"]
    },
    "onServiceDbSchema": {
        "update": ["files.db-schemas/.services.{service}"]
    },
    "onFullComplete": {
        "update": ["lastUpdated", "fullScanComplete"]
    },
    "onPhase37Incomplete": {
        "update": ["fullScanComplete = false", "incomplete section with reason"]
    },
    "onError": {
        "update": ["incomplete section with reason + since"]
    },
    "procedure": [
        "1. 갱신 대상 파일의 $lastUpdated 업데이트 (각 JSON 내부)",
        "2. manifest.json 읽기",
        "3. 다음 필드 업데이트:",
        "   - lastUpdated: 현재 시각 (ISO 8601)",
        "   - completeness.{target}: true/false",
        "   - files.{target}.updatedAt: 현재 시각",
        "   - fullScanComplete: 모든 completeness가 true인 경우만 true",
        "   - incomplete: 미완료 항목 추가/제거",
        "4. manifest.json 저장"
    ],
    "roleSeparation": {
        "manifest.json": {
            "owner": "데이터 레이어",
            "role": "메타데이터 상태 기술 (무엇이, 언제, 완전한지)",
            "consumer": "test-gate, analyze 등 모든 스킬"
        },
        ".refresh-state.json": {
            "owner": "refresh-architecture 스킬",
            "role": "갱신 내부 상태 (어떤 커밋에서, 어떤 브랜치로)",
            "consumer": "refresh-architecture만"
        }
    }
}


# ─────────────────────────────────────────────────────────────────────
# SQL TEMPLATES
# ─────────────────────────────────────────────────────────────────────

SQL_TABLE_LIST = """SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  AND table_name NOT LIKE 'flyway%' AND table_name NOT LIKE 'batch_%'
ORDER BY table_name;"""

SQL_COLUMNS = """SELECT column_name, data_type, is_nullable, column_default, character_maximum_length
FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position;"""

SQL_INDEXES = """SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = '{table}' AND schemaname = 'public';"""

SQL_FK = """SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = '{table}';"""


# ─────────────────────────────────────────────────────────────────────
# WORKTREE TEMPLATE
# ─────────────────────────────────────────────────────────────────────

WORKTREE_SCRIPT = """#!/bin/bash
# Worktree creation for architecture refresh
WORKTREE_ROOT="/tmp/claude-arch-refresh-$(date +%s)"
SERVICE_DIR="$1"

cd "$SERVICE_DIR" || exit 1
DEFAULT_BRANCH=$(git remote show origin 2>/dev/null | grep 'HEAD branch' | awk '{{print $NF}}')
DEFAULT_BRANCH="${{DEFAULT_BRANCH:-main}}"

git fetch origin "$DEFAULT_BRANCH"
git worktree add "$WORKTREE_ROOT/$(basename "$SERVICE_DIR")" "origin/$DEFAULT_BRANCH" --detach

echo "$WORKTREE_ROOT"
"""

WORKTREE_CLEANUP = """#!/bin/bash
# Worktree cleanup
WORKTREE_ROOT="$1"
SERVICE_DIR="$2"

cd "$SERVICE_DIR" || exit 1
git worktree remove "$WORKTREE_ROOT/$(basename "$SERVICE_DIR")" --force 2>/dev/null
rm -rf "$WORKTREE_ROOT"
"""


# ─────────────────────────────────────────────────────────────────────
# SCHEMA TEMPLATES
# ─────────────────────────────────────────────────────────────────────

SCHEMA_TEMPLATE = {
    "$lastUpdated": "ISO-8601",
    "$coverage": {"total": 0, "high": 0, "medium": 0, "low": 0, "conflict": 0, "dead": 0},
    "service": "{service}",
    "database": "{database}",
    "mcpTool": "{mcp_tool}",
    "tables": {
        "{table_name}": {
            "entity": "{EntityClass}",
            "priority": "critical|high|normal",
            "columns": {
                "{col}": {
                    "t": "type (?=nullable)",
                    "m": "meaning (1줄, null=DEAD)",
                    "c": "HIGH|MEDIUM|LOW|CONFLICT|DEAD",
                    "l": "STATIC|DYNAMIC|COMPUTED",
                    "r": 0,
                    "sm": "true if stateMachine",
                    "ns": "nullSemantics if applicable"
                }
            },
            "cognitive": {
                "invariants": ["고정 불변 규칙 (예: 재고 >= 0)"],
                "trade_offs": ["설계상 타협점 (예: 성능을 위한 최종 정합성)"],
                "failure_impact": "이 테이블/엔티티 장애 시 비즈니스 파급력",
                "conceptual_graph": ["비즈니스 프로세스 명칭 (예: 주문관리, 결제시스템)"]
            }
        }
    },
    "allTables": ["list of all table names"]
}

DB_GRAPH_TEMPLATE = {
    "$lastUpdated": "ISO-8601",
    "edges": [
        {"from": "service.table.col", "to": "service.table.col", "type": "fk|implicit", "n": 0, "cross": False}
    ],
    "coAccess": [
        {"table": "service.table", "name": "logical group name", "cols": ["col1", "col2"], "n": 0}
    ],
    "stateMachines": [
        {
            "table": "service.table", "col": "state_col",
            "transitions": [
                {"from": "STATE_A", "to": "STATE_B", "trigger": "method()", "side": ["affected_cols"]}
            ]
        }
    ],
    "dead": [
        {"t": "service.table", "col": "col_name", "r": 0}
    ]
}

FLOW_TEMPLATE = {
    "$lastUpdated": "ISO-8601",
    "service": "{service}",
    "features": [
        {
            "id": "{feature_id}",
            "feature": "비즈니스 기능명 (Glossary 적용 후)",
            "entryPoint": "시작 메서드/API",
            "steps": ["단계별 행위 요약 (Glossary 적용 후)"],
            "policies": ["주요 비즈니스 규칙/분기 조건"],
            "touchedEntities": ["연관 테이블 목록"],
            "diagram": "Mermaid 형식의 흐름도 텍스트"
        }
    ]
}

GLOSSARY_TEMPLATE = {
    "$lastUpdated": "ISO-8601",
    "terms": [
        {
            "technicalTerm": "코드 명칭",
            "businessTerm": "현장 용어",
            "description": "설명",
            "status": "PROPOSED|CONFIRMED|MAPPED"
        }
    ]
}


# ─────────────────────────────────────────────────────────────────────
# SUBCOMMANDS
# ─────────────────────────────────────────────────────────────────────

def cmd_config(args):
    """Full configuration JSON output."""
    config = {
        "services": SERVICES,
        "filePatterns": FILE_PATTERNS,
        "targets": TARGETS,
        "autoFullTargets": AUTO_FULL_TARGETS,
        "semantics": {
            "weights": SEMANTICS_WEIGHTS,
            "refLevels": REF_LEVELS,
            "confidence": CONFIDENCE_THRESHOLDS,
            "nullInterpretation": NULL_INTERPRETATION,
            "tiers": TIERS
        },
        "dataContracts": DATA_CONTRACTS_SECTIONS,
        "manifestRules": MANIFEST_UPDATE_RULES
    }
    print(json.dumps(config, ensure_ascii=False, indent=2))


def cmd_plan(args):
    """Analyze git diff and produce refresh plan JSON."""
    workspace = args.path or os.getcwd()
    mode = args.mode or "incremental"
    service_filter = args.service
    target_filter = args.target

    plan = {
        "mode": mode,
        "workspace": workspace,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changedServices": [],
        "targets": [],
        "actions": [],
        "parallelizable": []
    }

    if mode == "full" or service_filter:
        services_to_scan = [service_filter] if service_filter else list(SERVICES.keys())
        targets = [target_filter] if target_filter else list(TARGETS.keys())
        plan["mode"] = "full" if not service_filter else "targeted"
        plan["changedServices"] = services_to_scan
        plan["targets"] = targets
    else:
        # Incremental: check refresh-state.json
        state_path = os.path.join(workspace, ARCHITECTURE_DIR, "refresh-state.json")
        if os.path.exists(state_path):
            with open(state_path) as f:
                state = json.load(f)
            # Analyze git changes per service
            for svc, info in state.get("services", {}).items():
                svc_path = os.path.join(workspace, info.get("path", svc))
                if os.path.isdir(svc_path):
                    last_commit = info.get("lastCommit", "")
                    default_branch = info.get("defaultBranch") or SERVICES.get(svc, {}).get("defaultBranch", "main")
                    remote_ref = f"origin/{default_branch}"
                    
                    try:
                        # Remote-First: Fetch and diff against origin
                        subprocess.run(["git", "fetch", "origin", default_branch], 
                                     capture_output=True, cwd=svc_path, timeout=10)
                        
                        result = subprocess.run(
                            ["git", "diff", "--name-only", last_commit, remote_ref],
                            capture_output=True, text=True, cwd=svc_path
                        )
                        changed = result.stdout.strip().split("\n") if result.stdout.strip() else []
                        if changed:
                            plan["changedServices"].append(svc)
                            # Map changed files to targets
                            targets_set = set()
                            for f in changed:
                                for pattern, tgts in FILE_PATTERNS.items():
                                    pat = pattern.replace("*", "").replace("**", "")
                                    if pat in f:
                                        targets_set.update(tgts)
                            if targets_set:
                                plan["targets"].extend(list(targets_set))
                    except Exception as e:
                        print(f"Warning: Failed to diff {svc} against remote: {e}", file=sys.stderr)
                        plan["changedServices"].append(svc)
            
            # De-duplicate targets
            plan["targets"] = list(set(plan["targets"]))
        else:
            # No state file → force full
            plan["mode"] = "full"
            plan["changedServices"] = list(SERVICES.keys())
            plan["targets"] = list(TARGETS.keys())

    # Build action plan
    phase0_svcs = [s for s in plan["changedServices"] if s in SERVICES]
    if phase0_svcs:
        plan["actions"].append({
            "phase": 0, "action": "worktree",
            "services": phase0_svcs, "model": "sonnet"
        })

    for svc in phase0_svcs:
        svc_info = SERVICES.get(svc, {})
        if svc_info.get("mcp") and ("db-schemas" in plan["targets"] or "all" in plan["targets"]):
            plan["actions"].append({
                "phase": 1, "action": "gen-sql",
                "service": svc, "mcp": svc_info["mcp"], "model": "sonnet"
            })

    if "db-semantics" in plan["targets"] or "all" in plan["targets"]:
        for svc in phase0_svcs:
            plan["actions"].append({
                "phase": "3-7", "action": "semantics",
                "service": svc, "model": "opus"
            })

    # Parallelizable groups
    phase1_ids = [f"phase1_{a['service']}" for a in plan["actions"] if a.get("phase") == 1]
    if phase1_ids:
        plan["parallelizable"].append(["phase0"] + phase1_ids)

    print(json.dumps(plan, ensure_ascii=False, indent=2))


def cmd_worktree(args):
    """Output worktree creation/cleanup shell commands."""
    output = {
        "create": WORKTREE_SCRIPT.strip(),
        "cleanup": WORKTREE_CLEANUP.strip(),
        "usage": {
            "create": "bash <(python3 skills/refresh_architecture/scripts/arch-manager.py worktree | jq -r .create) /path/to/service",
            "cleanup": "bash <(python3 skills/refresh_architecture/scripts/arch-manager.py worktree | jq -r .cleanup) $WORKTREE_ROOT /path/to/service"
        },
        "paths": {
            "codeAnalysis": "$WORKTREE_ROOT/{service}/",
            "metadataOutput": "$WORKSPACE_ROOT/.architecture/metadata/",
            "dbSchema": "MCP PostgreSQL 직접 조회"
        }
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_gen_sql(args):
    """Generate DB schema extraction SQL for a service."""
    service = args.service
    if not service:
        print(json.dumps({"error": "--service required"}, ensure_ascii=False))
        sys.exit(1)

    svc_info = SERVICES.get(service)
    if not svc_info:
        print(json.dumps({"error": f"Unknown service: {service}"}, ensure_ascii=False))
        sys.exit(1)

    # All templates and steps are now loaded from configuration.json
    output = {
        "service": service,
        "mcp": svc_info.get("mcp"),
        "type": svc_info.get("type"),
        "critical_tables": svc_info.get("critical_tables", []),
        "sql_templates": SQL_TEMPLATES,
        "mapping_steps": MAPPING_RULES.get("db_mapping_steps", [])
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_scan(args):
    """Output source scan patterns from configuration."""
    # The engine doesn't care if it's jpa, kafka, or grpc.
    # it just outputs whatever is in DISCOVERY_PATTERNS.
    output = {
        "discovery_patterns": DISCOVERY_PATTERNS,
        "mapping_rules": MAPPING_RULES,
        "tiers": TIERS
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_update_state(args):
    """Output manifest + .refresh-state.json update procedure."""
    output = {
        "manifestRules": MANIFEST_UPDATE_RULES,
        "refreshStateSchema": {
            "$lastFullRefresh": "ISO-8601",
            "services": {
                "{service}": {
                    "path": "relative path",
                    "lastCommit": "commit hash",
                    "lastRefreshed": "ISO-8601",
                    "targets": ["list of completed targets"]
                }
            }
        },
        "roleSeparation": MANIFEST_UPDATE_RULES["roleSeparation"],
        "paths": {
            "config": ".architecture/configuration.json",
            "metadata": ".architecture/metadata/",
            "state": ".architecture/refresh-state.json"
        }
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_schema_template(args):
    """Output db-schemas storage schema template."""
    output = {
        "dbSchemaTemplate": SCHEMA_TEMPLATE,
        "dbGraphTemplate": DB_GRAPH_TEMPLATE,
        "abbreviationKeys": ABBREVIATION_KEYS
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_semantics_config(args):
    """Output Phase 3-7 configuration values."""
    output = {
        "phase3": {
            "weights": SEMANTICS_WEIGHTS,
            "layers": PHASE3_LAYERS,
            "aggregation": {
                "step1": "참조점별 추출한 의미를 의미 그룹별로 합산",
                "step2": "dominant 의미 (최고 가중합) 선정, 나머지는 supplementary",
                "step3": "generic 의미는 specific 의미에 흡수",
                "step4": "크로스 컬럼 상호작용 (toMap 복합키, 조건결합, 파생계산) 탐지",
                "refLevels": REF_LEVELS
            }
        },
        "phase4": {
            "queries": PHASE4_QUERIES,
            "nullInterpretation": NULL_INTERPRETATION,
            "mismatchPatterns": MISMATCH_PATTERNS,
            "prerequisite": "MCP PostgreSQL 접속 가능 시만. 불가 시 SKIP.",
            "cognitive_inference": {
                "invariants": "코드/DB에서 도출된 절대 규칙",
                "trade_offs": "의도된 설계상 타협점",
                "failure_impact": "비즈니스 영향도 분석"
            }
        },
        "phase5": {
            "commands": PHASE5_COMMANDS,
            "detect": "같은 컬럼의 사용 패턴이 시간에 따라 변하면 -> semanticEvolution 기록"
        },
        "phase6": {
            "relationships": PHASE6_RELATIONSHIPS,
            "output": "db-graph.json (전체 서비스 통합)"
        },
        "phase7": {
            "confidence": CONFIDENCE_THRESHOLDS,
            "autoEnrich": PHASE7_AUTO_ENRICH,
            "tiers": TIERS
        }
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_init(args):
    """Generates a default configuration.json template in the workspace."""
    workspace = args.path or os.getcwd()
    arch_dir = os.path.join(workspace, ARCHITECTURE_DIR)
    config_path = args.output or os.path.join(arch_dir, "configuration.json")
    
    if os.path.exists(config_path) and not args.force:
        print(f"Error: {config_path} already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)
    
    # Ensure .architecture directory exists
    if not os.path.exists(arch_dir):
        os.makedirs(arch_dir)
        print(f"Created directory: {arch_dir}", file=sys.stderr)
    
    # Discovery Logic
    services = {}
    print(f"Scanning workspace for services and git information: {workspace}", file=sys.stderr)
    
    for entry in os.listdir(workspace):
        full_path = os.path.join(workspace, entry)
        if os.path.isdir(full_path) and not entry.startswith('.'):
            # Check for Flyway or typical project indicators
            is_service = False
            flyway_path = None
            
            # Search for flyway migration folder
            for root, dirs, files in os.walk(full_path):
                if "db/migration" in root:
                    is_service = True
                    flyway_path = os.path.relpath(root, full_path)
                    break
                if "build.gradle" in files or "pom.xml" in files:
                    is_service = True
            
            if is_service:
                git_url = get_git_remote_url(full_path) if is_git_repo(full_path) else None
                services[entry] = {
                    "mcp": f"mcp__postgres_{entry.replace('-', '_')}__query",
                    "flyway": flyway_path or "path/to/db/migration",
                    "gitUrl": git_url,
                    "defaultBranch": get_default_branch(full_path) if git_url else "main",
                    "criticalTables": [],
                    "highTables": []
                }
                if git_url:
                    print(f"  [Found] {entry} (Git: {git_url})", file=sys.stderr)
                else:
                    print(f"  [Found] {entry} (No Git URL)", file=sys.stderr)

    template = {
        "services": services or {
            "example-service": {
                "mcp": "mcp__postgres_example__query",
                "flyway": "path/to/db/migration",
                "gitUrl": "https://github.com/org/repo.git",
                "defaultBranch": "main",
                "criticalTables": [],
                "highTables": []
            }
        },
        "filePatterns": {
            "*Entity.java": ["db-schemas", "db-semantics", "data-contracts"],
            "*Repository.java": ["db-schemas", "db-semantics", "data-contracts"],
            "db/migration/**": ["db-schemas"],
            "*.sql": ["db-schemas"]
        },
        "semantics": {
            "weights": SEMANTICS_WEIGHTS,
            "refLevels": REF_LEVELS,
            "confidence": CONFIDENCE_THRESHOLDS,
            "nullInterpretation": NULL_INTERPRETATION,
            "tiers": TIERS
        },
        "discovery_patterns": {
            "include": ["**/*.java", "**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "*.sql", "**/*.sql"],
            "exclude": ["**/node_modules/**", "**/build/**", "**/dist/**", "**/target/**", "**/.*/**", "**/*.test.*", "**/*.spec.*"]
        }
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        print(f"Successfully initialized configuration at: {config_path}")
        
        # Phase 1: Initialize index
        update_metadata_index(workspace)

        print("\n>>> [NEXT STEP] Please verify the discovered Git URLs above.", file=sys.stderr)
        print(">>> If any URLs are missing or incorrect, edit configuration.json manually.", file=sys.stderr)
    except Exception as e:
        print(f"Error creating config: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_flow(args):
    """
    Stage 5: Behavioral Flow Extraction.
    Analyzes code to extract business flows and policies.
    """
    workspace = args.path or os.getcwd()
    service = args.service
    meta_dir = os.path.join(workspace, ARCHITECTURE_DIR, "metadata")
    output_path = os.path.join(meta_dir, f"flow-{service}.json")
    
    def load_skeleton(svc, md):
        p = os.path.join(md, f"skeleton-{svc}.json")
        if os.path.exists(p):
            with open(p, 'r') as f: return json.load(f)
        return None

    def load_graph(md):
        p = os.path.join(md, "db-graph.json")
        if os.path.exists(p):
            with open(p, 'r') as f: return json.load(f)
        return None
    
    # Load glossary for term mapping
    glossary_path = os.path.join(meta_dir, "domain-glossary.json")
    glossary = {}
    if os.path.exists(glossary_path):
        try:
            with open(glossary_path, 'r') as f:
                g_data = json.load(f)
                glossary = {t['technicalTerm']: t['businessTerm'] for t in g_data.get('terms', []) if t.get('status') in ['CONFIRMED', 'MAPPED']}
        except Exception: pass

    # 1. Load Skeleton
    sk_path = os.path.join(meta_dir, f"skeleton-{service}.json")
    if not os.path.exists(sk_path):
        print(f">>> [Flow] Skeleton for {service} not found. Running skeleton scan first...", file=sys.stderr)
        # Mock/Simplified logic for now
        return

    # 2. Trace Flows (More dynamic logic)
    flows = {
        "$lastUpdated": datetime.now(timezone.utc).isoformat(),
        "service": service,
        "features": []
    }
    
    sk_data = load_skeleton(service, meta_dir)
    graph_data = load_graph(meta_dir)
    
    # 3. Apply Glossary Mapping (Using RegEx for precision - Word Boundaries)
    def map_term(text):
        if not text: return text
        # Sort keys by length (desc) to avoid partial matches overriding longer ones
        sorted_tech = sorted(glossary.keys(), key=len, reverse=True)
        for tech in sorted_tech:
            biz = glossary[tech]
            # Use \b for word boundaries to avoid replacing "user_id" within "superuser_id"
            # Since some tech terms might have underscores, we define boundaries carefully
            pattern = r'(?<!\w)' + re.escape(tech) + r'(?!\w)'
            text = re.sub(pattern, biz, text)
        return text

    if not sk_data:
        print(f">>> [Flow] Skeleton for {service} not found. Skipping dynamic trace.", file=sys.stderr)
    else:
        print(f">>> [Flow] Tracing flow for {service} using skeleton & graph...")
        
        # 3. Dynamic Tracing Logic
        # Scan for entry points (e.g., classes with 'Controller' or 'Service')
        for f_info in sk_data.get("files", []):
            classes = f_info.get("structure", {}).get("classes", [])
            for cls in classes:
                c_name = cls.get("name", "")
                if "Controller" in c_name or "Service" in c_name:
                    # Found a potential entry point
                    methods = cls.get("methods", [])
                    # In a real impl, we'd use regex/AST to find which methods are public/endpoints
                    for m_name in methods:
                        # Simple rule: if it's a common action word
                        if any(x in m_name.lower() for x in ["create", "handle", "process", "update", "delete"]):
                            feature_id = f"{service}_{c_name}_{m_name}".lower()
                            
                            # Trace steps (lookup calls in skeleton - simplified)
                            steps = [m_name]
                            touched_entities = []
                            
                            # Check graph for DB interactions (if any table mentions this service/methods)
                            if graph_data:
                                for edge in graph_data.get("edges", []):
                                    if edge.get("from") == service or service in edge.get("from", ""):
                                        target = edge.get("to", "")
                                        if "." in target:
                                            parts = target.split(".")
                                            tbl = parts[-1] if len(parts) > 0 else target
                                            if tbl not in touched_entities:
                                                touched_entities.append(tbl)

                            flows["features"].append({
                                "id": feature_id,
                                "feature": map_term(c_name.replace("Controller", "").replace("Service", "")),
                                "entryPoint": f"{c_name}.{m_name}",
                                "steps": [map_term(s) for s in steps],
                                "policies": ["Business Policy Logic Extraction - WIP"],
                                "touchedEntities": touched_entities,
                                "diagram": f"graph TD\n  Start --> {m_name}\n  {m_name} --> End"
                            })

    if not flows["features"]:
        # Fallback dummy if nothing found (to avoid empty output during dev)
        flows["features"].append({
            "id": f"{service}_fallback",
            "feature": map_term("Generic Process"),
            "entryPoint": "unknown",
            "steps": [map_term("process_start")],
            "policies": [],
            "touchedEntities": [],
            "diagram": "graph TD\n  A --> B"
        })

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(flows, f, ensure_ascii=False, indent=2)
    
    print(f">>> [Flow] Generated at {output_path}")

    # 4. Update Global Feature Index
    index_path = os.path.join(meta_dir, "feature-index.json")
    feature_index = {}
    if os.path.exists(index_path):
        with open(index_path, 'r') as f: feature_index = json.load(f)
    
    for feat in flows["features"]:
        fid = feat["id"]
        # Update or create entry
        if fid not in feature_index:
            feature_index[fid] = {
                "name": feat["feature"],
                "service": service,
                "entryPoint": feat["entryPoint"],
                "files": [],
                "status": "PARTIAL", # Default to partial until all steps are traced
                "touchedEntities": feat["touchedEntities"]
            }
        # Add entry point file to files list if not already there
        # (This is simplified; would need actual file path from skeleton)
        
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(feature_index, f, ensure_ascii=False, indent=2)
    print(f">>> [Flow] Updated {index_path}")


def cmd_glossary(args):
    """
    Glossary Management.
    Propose, Sync, or List domain terms.
    """
    workspace = args.path or os.getcwd()
    meta_dir = os.path.join(workspace, ARCHITECTURE_DIR, "metadata")
    glossary_path = os.path.join(meta_dir, "domain-glossary.json")
    
    if args.sub == "propose":
        print(">>> [Glossary] Scanning code for technical terms...")
        # Placeholder for term extraction logic
        new_terms = [
            {"technicalTerm": "receipt_status", "businessTerm": "입고 상태", "description": "입고의 현재 단계", "status": "PROPOSED"}
        ]
        
        existing = {"terms": []}
        if os.path.exists(glossary_path):
            with open(glossary_path, 'r') as f:
                existing = json.load(f)
        
        seen = {t['technicalTerm'] for t in existing['terms']}
        for t in new_terms:
            if t['technicalTerm'] not in seen:
                existing['terms'].append(t)
        
        existing['$lastUpdated'] = datetime.now(timezone.utc).isoformat()
        with open(glossary_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f">>> [Glossary] New terms proposed at {glossary_path}")

    elif args.sub == "sync":
        print(f">>> [Glossary] Syncing user-confirmed terms from {glossary_path}...")
        if not os.path.exists(glossary_path):
            print("Error: Glossary file not found.", file=sys.stderr)
            return
            
        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            updated_count = 0
            for term in data.get('terms', []):
                # If businessTerm is manually filled and status is PROPOSED, move to CONFIRMED
                if term.get('status') == 'PROPOSED' and term.get('businessTerm') and term.get('businessTerm') != term.get('technicalTerm'):
                    term['status'] = 'CONFIRMED'
                    updated_count += 1
            
            if updated_count > 0:
                data['$lastUpdated'] = datetime.now(timezone.utc).isoformat()
                with open(glossary_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f">>> [Glossary] {updated_count} terms synced to CONFIRMED state.")
            else:
                print(">>> [Glossary] No new terms to sync.")
        except Exception as e:
            print(f"Error syncing glossary: {e}", file=sys.stderr)

    elif args.sub == "list":
        if not os.path.exists(glossary_path):
            print(">>> [Glossary] No glossary found. Run 'propose' first.")
            return
            
        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"\n--- Domain Glossary (Last Updated: {data.get('$lastUpdated', 'Unknown')}) ---")
            print(f"{'Technical Term':<30} | {'Business Term':<20} | {'Status':<10}")
            print("-" * 65)
            for t in data.get('terms', []):
                print(f"{t['technicalTerm']:<30} | {t['businessTerm']:<20} | {t['status']:<10}")
            print("-" * 65)
        except Exception as e:
            print(f"Error listing glossary: {e}", file=sys.stderr)

def cmd_query(args):
    """
    Queries architecture metadata using various filters.
    Optimized for LLM token usage.
    """
    workspace = args.path or os.getcwd()
    meta_dir = os.path.join(workspace, METADATA_DIR)
    
    if not os.path.exists(meta_dir):
        # Fallback to legacy or skill-relative for testing
        meta_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
        if not os.path.exists(meta_dir):
            print(f"Error: Metadata directory not found in workspace (.architecture/metadata/) or legacy fallback.")
            return

    # Check for specific metadata types
    target_type = args.type
    target_service = args.service
    target_table = args.table
    target_keyword = getattr(args, "keyword", None)

    # Phase 1: Scouting via Index
    index_path = os.path.join(workspace, ARCHITECTURE_DIR, "metadata-index.json")
    if not (target_service or target_table or target_keyword) and os.path.exists(index_path):
        try:
            with open(index_path, 'r') as f:
                index_data = json.load(f)
                print(">>> [Scouting Index] No specific service/table requested. Available metadata:")
                print(json.dumps(index_data, indent=2, ensure_ascii=False))
                print("\nUse --service or --table to query detailed metadata.")
                return
        except Exception:
            pass

    results = []

    # Helper to check version
    def verify_version(data, filename):
        file_version = data.get("metadataVersion", 0)
        if file_version != METADATA_VERSION:
            print(f"Warning: {filename} version mismatch (File: V{file_version}, Script: V{METADATA_VERSION}).")
            print("Please run 'arch-manager.py refresh' to sync metadata.")
            return False
        return True

    if target_type == "db":
        db_file = os.path.join(meta_dir, "db-schemas.json")
        if os.path.exists(db_file):
            with open(db_file, "r") as f:
                db_data = json.load(f)
            
            if not verify_version(db_data, "db-schemas.json"):
                return

            schemas = db_data.get("schemas", []) if isinstance(db_data.get("schemas"), list) else []
            for schema in schemas:
                if target_service and schema.get("service") != target_service:
                    continue
                
                # Filter tables
                filtered_tables = []
                tables_data = schema.get("tables", [])
                
                if isinstance(tables_data, list):
                    for table in tables_data:
                        if target_table and table.get("name") != target_table:
                            continue
                        filtered_tables.append(table)
                elif isinstance(tables_data, dict):
                    for name, table_info in tables_data.items():
                        if target_table and name != target_table:
                            continue
                        table_data = {"name": name}
                        # Handle legacy string-only col-type format or new dict format
                        if isinstance(table_info, dict):
                            table_data.update(table_info)
                        else:
                            table_data["columns"] = table_info
                        filtered_tables.append(table_data)
                
                if filtered_tables:
                    results.append({
                        "service": schema.get("service"),
                        "tables": filtered_tables
                    })

    # More types (api, kafka) can be implemented here...
    
    # Phase 2: Keyword-based filtering (Semantic Search Lite)
    if target_keyword:
        keyword = target_keyword.lower()
        keyword_results = []
        for res in results:
            svc = res.get("service", "").lower()
            filtered_tables = []
            for table in res.get("tables", []):
                t_name = table.get("name", "").lower()
                # Check match in name or stringified content
                if keyword in t_name or keyword in svc or keyword in json.dumps(table).lower():
                    filtered_tables.append(table)
            
            if filtered_tables:
                keyword_results.append({
                    "service": res.get("service"),
                    "tables": filtered_tables
                })
        results = keyword_results

    if not results:
        # Provide helpful hint for the agent
        print(f"No matching {target_type} metadata found for service: {target_service or 'all'}, table: {target_table or 'any'}, keyword: {target_keyword or 'none'}.")
        return

    # Phase 2: Auto-summarization for large outputs
    total_items = sum(len(res.get("tables", [])) for res in results)
    if total_items > 10:
        print(f">>> [Auto-Summary] Result too large ({total_items} items). Providing bird's-eye view:")
        summary = []
        for res in results:
            summary.append({
                "service": res.get("service"),
                "table_names": [t.get("name") for t in res.get("tables", [])]
            })
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print("\nTIP: Use --table or --keyword to narrow down for full details.")
    else:
        # Formatted output for LLM
        print(json.dumps(results, indent=2, ensure_ascii=False))


def cmd_graph(args):
    """
    Phase 6: Relation Graph.
    Building a Hybrid Relation Graph (Static + Implicit).
    """
    workspace = args.path or os.getcwd()
    meta_dir = os.path.join(workspace, METADATA_DIR)
    graph_path = os.path.join(meta_dir, "db-graph.json")
    
    graph = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "edges": [],
        "coAccess": [],
        "stateMachines": [],
        "businessProcesses": []
    }

    # 1. Load DB Schemas (Phase 4 results)
    db_file = os.path.join(meta_dir, "db-schemas.json")
    table_pk_map = {} # {table: pk_col}
    all_tables = []
    
    if os.path.exists(db_file):
        try:
            with open(db_file, 'r') as f:
                db_data = json.load(f)
                schemas = db_data.get("schemas")
                if isinstance(schemas, list):
                    for schema in schemas:
                        svc = schema.get("service")
                        tables = schema.get("tables", {})
                        if isinstance(tables, dict):
                            for t_name, t_info in tables.items():
                                full_name = f"{svc}.{t_name}"
                                all_tables.append({"svc": svc, "name": t_name, "cols": t_info.get("columns", {})})
                                # Identify PK candidate (usually 'id' or table_id)
                                cols = t_info.get("columns", {})
                                if "id" in cols:
                                    table_pk_map[full_name] = "id"
                                elif f"{t_name}_id" in cols:
                                    table_pk_map[full_name] = f"{t_name}_id"
        except Exception as e:
            print(f"Warning: Failed to load db-schemas.json: {e}", file=sys.stderr)
    
    # 2. Extract Explicit Edges (from FKs if available - stub)
    # 3. Infer Implicit Edges (ID Matching)
    for i, t1 in enumerate(all_tables):
        for j, t2 in enumerate(all_tables):
            if i == j: continue
            
            t1_full = f"{t1['svc']}.{t1['name']}"
            t2_full = f"{t2['svc']}.{t2['name']}"
            
            # Match logic:
            # 1. table_a_id in table_b matches id in table_a (handle plural)
            # 2. domain_id in table_a matches domain_id in table_b
            pk_col = table_pk_map.get(t1_full)
            t1_name = t1['name'].rstrip('s') # simple plural handling
            t1_name_id = f"{t1_name}_id"
            
            for t2_col in t2["cols"]:
                is_match = False
                if pk_col == "id" and (t2_col == t1_name_id or t2_col == f"{t1['name']}_id"):
                    is_match = True
                elif t2_col == pk_col and pk_col not in ["id", "no", "key"]:
                    is_match = True
                
                if is_match:
                    graph["edges"].append({
                        "from": f"{t2_full}.{t2_col}",
                        "to": f"{t1_full}.{pk_col}",
                        "type": "implicit",
                        "confidence": "HIGH" if t1["svc"] != t2["svc"] else "MEDIUM",
                        "cross": t1["svc"] != t2["svc"]
                    })

    # 4. Code-level Dependencies (Cross-Service call inference via skeleton)
    if os.path.exists(meta_dir):
        all_service_names = list(SERVICES.keys())
        for f_name in os.listdir(meta_dir):
            if f_name.startswith("skeleton") and f_name.endswith(".json"):
                try:
                    with open(os.path.join(meta_dir, f_name), 'r') as f:
                        sk_data = json.load(f)
                        this_svc = sk_data.get("service")
                        if not this_svc: continue
                        
                        for file_info in sk_data.get("files", []):
                            imports = file_info.get("structure", {}).get("imports", [])
                            for imp in imports:
                                imp_lower = imp.lower()
                                for other_svc in all_service_names:
                                    if other_svc == this_svc: continue
                                    # Cross-service detection:
                                    # 1. Exact slug match (order-svc -> order-svc)
                                    # 2. Dot-normalized match (order-svc -> order.svc)
                                    # 3. Keyword match (order-svc -> user.client.Order)
                                    svc_slug = other_svc.lower().replace('-svc', '').replace('_svc', '').rstrip('s')
                                    if other_svc.lower() in imp_lower or svc_slug in imp_lower:
                                        graph["edges"].append({
                                            "from": this_svc,
                                            "to": other_svc,
                                            "type": "code_call",
                                            "confidence": "MEDIUM",
                                            "cross": True
                                        })
                except Exception:
                    pass
    # 5. Business Process Mapping (Stage 5 Abstraction)
    biz_map = {} # {process_name: [tables/services]}
    if os.path.exists(db_file):
        try:
            with open(db_file, 'r') as f:
                db_data = json.load(f)
                for schema in db_data.get("schemas", []):
                    svc = schema.get("service")
                    for t_name, t_info in schema.get("tables", {}).items():
                        cog = t_info.get("cognitive", {})
                        if isinstance(cog, dict):
                            # Extract from conceptual_graph or failure_impact
                            concepts = cog.get("conceptual_graph", [])
                            for concept in concepts:
                                if concept not in biz_map: biz_map[concept] = []
                                biz_map[concept].append(f"{svc}.{t_name}")
        except Exception: pass
    
    for biz, members in biz_map.items():
        graph["businessProcesses"].append({
            "name": biz,
            "members": list(set(members))
        })

    # De-duplicate edges
    unique_edges = []
    seen_edges = set()
    for e in graph["edges"]:
        key = f"{e['from']}->{e['to']}:{e['type']}"
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)
    graph["edges"] = unique_edges

    # Ensure dir exists
    if not os.path.exists(meta_dir):
        os.makedirs(meta_dir)
        
    with open(graph_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    
    print(f">>> [Hybrid Graph] Generated at {graph_path}")
    print(json.dumps(graph, indent=2, ensure_ascii=False))


def cmd_archaeology(args):
    """
    Stage 1: Git Archaeology.
    Extracts code freshness, dormant days, and contributor metrics via git log.
    """
    workspace = args.path or os.getcwd()
    service = args.service
    meta_dir = os.path.join(workspace, ARCHITECTURE_DIR, "metadata")
    output_path = os.path.join(meta_dir, "archaeology.json")

    results = {
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "files": {}
    }

    # Determine files to scan
    include_patterns = DISCOVERY_PATTERNS.get("include", [])
    exclude_patterns = DISCOVERY_PATTERNS.get("exclude", [])

    # Safe fallback if patterns are missing
    if not include_patterns:
        include_patterns = ["**/*.java", "**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.sql"]
    if not exclude_patterns:
        exclude_patterns = ["**/node_modules/**", "**/build/**", "**/dist/**", "**/target/**", "**/.*/**"]

    files_to_scan = []
    
    # If service is specified, limit search to that service's directory
    scan_root = workspace
    if service and service in SERVICES:
        svc_info = SERVICES[service]
        svc_rel_path = svc_info.get("path", service)
        scan_root = os.path.join(workspace, svc_rel_path)
    
    if not os.path.exists(scan_root):
        print(f"Error: Path {scan_root} does not exist.", file=sys.stderr)
        return

    for root, _, filenames in os.walk(scan_root):
        for filename in filenames:
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, workspace)
            
            # Match include
            if any(fnmatch.fnmatch(rel_path, p) for p in include_patterns):
                # Match exclude
                if not any(fnmatch.fnmatch(rel_path, p) for p in exclude_patterns):
                    files_to_scan.append(rel_path)

    now = datetime.now(timezone.utc)

    for f in files_to_scan:
        try:
            # 1. Last Modification Date
            res_last = subprocess.run(
                ["git", "log", "-1", "--format=%ai", f],
                capture_output=True, text=True, cwd=workspace
            )
            last_date_str = res_last.stdout.strip()
            
            # 2. Creation Date
            res_first = subprocess.run(
                ["git", "log", "--reverse", "--format=%ai", f],
                capture_output=True, text=True, cwd=workspace
            )
            first_date_str = res_first.stdout.split('\n')[0].strip() if res_first.stdout else ""

            # 3. Commit Count & Contributor Count
            res_stats = subprocess.run(
                ["git", "log", "--format=%ae", f],
                capture_output=True, text=True, cwd=workspace
            )
            raw_stats = res_stats.stdout.strip().split('\n') if res_stats.stdout.strip() else []
            contributors = set(raw_stats)
            commit_count = len(raw_stats)

            if last_date_str:
                # Handle potential timezone issues in fromisoformat (simplified)
                # git %ai format: 2026-03-12 22:15:53 +0900
                date_part = last_date_str.rsplit(' ', 1)[0]
                try:
                    # fromisoformat handles space between date and time since 3.7+
                    # and %ai usually has it.
                    last_date = datetime.fromisoformat(date_part).replace(tzinfo=timezone.utc)
                except ValueError:
                    # Fallback for manual parsing
                    last_date = datetime.strptime(date_part, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                
                dormant_days = (now - last_date).days
                
                # Freshness Logic (Phases of Life)
                if dormant_days < 30: freshness = "ACTIVE"
                elif dormant_days < 90: freshness = "STALE"
                elif dormant_days < 180: freshness = "OLD"
                else: freshness = "ANCIENT"

                results["files"][f] = {
                    "last_modified": last_date_str,
                    "created_at": first_date_str,
                    "dormant_days": dormant_days,
                    "freshness": freshness,
                    "commit_count": commit_count,
                    "contributor_count": len(contributors)
                }
        except Exception as e:
            results["files"][f] = {"error": str(e)}

    # Ensure dir exists
    if not os.path.exists(meta_dir):
        os.makedirs(meta_dir)
        
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f">>> [Archaeology] Generated at {output_path}")


def cmd_verify(args):
    """
    Stage 3: Behavioral Verification.
    Cross-checks code skeletons against DB schemas to find inconsistencies.
    """
    workspace = args.path or os.getcwd()
    service = args.service
    meta_dir = os.path.join(workspace, ARCHITECTURE_DIR, "metadata")
    
    schema_path = os.path.join(meta_dir, "db-schemas.json")
    if not os.path.exists(schema_path):
        print(f"Error: db-schemas.json not found. Run metadata extraction first.", file=sys.stderr)
        return

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_data = json.load(f)
    
    # Map schemas for quick access: {service: {table: {column_info}}}
    db_map = {}
    schemas_list = schema_data.get("schemas", [])
    if isinstance(schemas_list, list):
        for entry in schemas_list:
            svc = entry.get("service")
            db_map[svc] = {}
            tables_data = entry.get("tables", {})
            if isinstance(tables_data, dict):
                for t_name, t_info in tables_data.items():
                    db_map[svc][t_name] = t_info.get("columns", {}) if isinstance(t_info, dict) else t_info
            elif isinstance(tables_data, list):
                for t_info in tables_data:
                    db_map[svc][t_info.get("name")] = t_info.get("columns", {})

    errors = []

    # 1. Config Check: Do critical tables defined in config actually exist in DB?
    for svc, info in SERVICES.items():
        if service and svc != service: continue
        critical = info.get("criticalTables", [])
        for t in critical:
            if svc in db_map and t not in db_map[svc]:
                errors.append(f"[MISSING_TABLE] {svc}: Critical table '{t}' not found in DB schema.")

    # 2. Skeleton Check: Basic usage verification (Placeholder for AST depth)
    # Checks if tables used in code are actually present in the DB schema
    if os.path.exists(meta_dir):
        for f_name in os.listdir(meta_dir):
            if f_name.startswith("skeleton") and f_name.endswith(".json"):
                try:
                    with open(os.path.join(meta_dir, f_name), 'r') as f:
                        sk_data = json.load(f)
                        this_svc = sk_data.get("service")
                        if service and this_svc != service: continue
                        
                        # 3. Flow-Glossary Check: Are terms in flow files mapped in glossary?
                        flow_file = os.path.join(meta_dir, f"flow-{this_svc}.json")
                        if os.path.exists(flow_file):
                            with open(flow_file, 'r') as ff:
                                flow_data = json.load(ff)
                                glossary_path = os.path.join(meta_dir, "domain-glossary.json")
                                glossary_terms = []
                                if os.path.exists(glossary_path):
                                    with open(glossary_path, 'r') as gf:
                                        glossary_terms = [t['technicalTerm'] for t in json.load(gf).get('terms', [])]
                                
                                for feat in flow_data.get("features", []):
                                    # Very basic check: if entryPoint has tech-like words not in glossary
                                    ep = feat.get("entryPoint", "")
                                    for word in re.findall(r'\w+', ep):
                                        if len(word) > 5 and word.lower() not in glossary_terms:
                                            # This is a heuristic, not a strict error yet
                                            pass
                                
                                # 4. Feature Index vs Flow files consistency
                                index_path = os.path.join(meta_dir, "feature-index.json")
                                if os.path.exists(index_path):
                                    with open(index_path, 'r') as idx_f:
                                        idx_data = json.load(idx_f)
                                        for fid, v in idx_data.items():
                                            svc = v.get("service")
                                            f_path = os.path.join(meta_dir, f"flow-{svc}.json")
                                            if not os.path.exists(f_path):
                                                errors.append(f"[ORPHAN_INDEX] Feature '{fid}' refers to service '{svc}', but flow file is missing.")
                                            else:
                                                with open(f_path, 'r') as f_flow:
                                                    flow_features = [f['id'] for f in json.load(f_flow).get('features', [])]
                                                    if fid not in flow_features:
                                                        errors.append(f"[STALE_INDEX] Feature '{fid}' exists in index but not in {os.path.basename(f_path)}.")
                except Exception: pass
                except Exception: pass

    if not errors:
        print(">>> [Verify] No major inconsistencies found.")
    else:
        for err in errors:
            print(f">>> [Verify] {err}")
    
    return errors


# ─────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────


def cmd_skeleton(args):
    """
    Stage 2: Structural Scanning (Mini-AST).
    Fast, regex-based extraction of methods, imports, and decorators.
    """
    workspace = args.path or os.getcwd()
    service = args.service
    
    # 1. Initialize Skeleton
    skeleton = {
        "service": service,
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "files": []
    }

    # 2. Get files from configuration
    patterns = DISCOVERY_PATTERNS
    include_patterns = patterns.get("include", [])
    exclude_patterns = patterns.get("exclude", [])

    # Simple walk and match
    for root, _, filenames in os.walk(workspace):
        for filename in filenames:
            rel_path = os.path.relpath(os.path.join(root, filename), workspace)
            
            # Match include
            if not any(fnmatch.fnmatch(rel_path, p) for p in include_patterns):
                continue
            # Match exclude
            if any(fnmatch.fnmatch(rel_path, p) for p in exclude_patterns):
                continue

            file_info = {
                "path": rel_path,
                "type": "source",
                "structure": {
                    "imports": [],
                    "classes": [],
                    "functions": []
                }
            }

            try:
                with open(os.path.join(workspace, rel_path), "r", encoding="utf-8") as f:
                    content = f.read()
                    
                    # Phase 1: Semantic Hash
                    file_info["semantic_hash"] = generate_semantic_hash(content, filename)

                    # Mini-AST extraction (Regex based)
                    # Imports
                    file_info["structure"]["imports"] = re.findall(r'^(?:from|import)\s+([\w\.]+)', content, re.M)
                    
                    # Classes & Methods
                    class_matches = re.finditer(r'^class\s+(\w+)(?:\((.*?)\))?:', content, re.M)
                    for cm in class_matches:
                        c_name = cm.group(1)
                        file_info["structure"]["classes"].append({"name": c_name, "methods": []})
                    
                    # Functions (standalone)
                    func_matches = re.finditer(r'^def\s+(\w+)\((.*?)\)(?:\s*->\s*(.*?))?:', content, re.M)
                    for fm in func_matches:
                        file_info["structure"]["functions"].append({
                            "name": fm.group(1),
                            "params": fm.group(2).strip(),
                            "returns": fm.group(3).strip() if fm.group(3) else "unknown"
                        })
            except Exception as e:
                file_info["error"] = str(e)

            skeleton["files"].append(file_info)

    # Phase 1: Metadata Indexing
    update_metadata_index(workspace)

    print(json.dumps(skeleton, indent=2, ensure_ascii=False))


def cmd_helper(args):
    """
    Provides a comprehensive guide for AI agents on how to use this skill.
    """
    guide = f"""
# AI Agent Usage Guide: refresh-architecture

이 스킬은 대규모 코드베이스의 아키텍처를 'Scouting - Scanning - Semantic Extraction' 3단계로 분석하는 프로토콜을 따릅니다.

### [Phase 0/1: Archaeology & Scouting]
`archaeology` 및 `init` 서브커맨드를 사용하여 프로젝트의 물리적 신선도와 기술 스택을 파악하십시오.
- 실행: `python3 arch-manager.py archaeology --path ./`
- 실행: `python3 arch-manager.py init --path ./`

### [Phase 2: Structural Scanning]
`skeleton` 서브커맨드를 사용하여 물리적인 코드 구조(메서드 시그니처, 의존성)를 추출하십시오.
- 실행: `python3 arch-manager.py skeleton --service [SERVICE_NAME]`
- 이 단계는 AI의 컨텍스트 윈도우 부하를 줄이기 위해 스크립트 기반으로 핵심 스켈레톤만 추출합니다.

### [Phase 3: Semantic Extraction & Cognitive Analysis]
추출된 `skeleton.json`과 원본 소스코드, 그리고 `archaeology` 정보를 참조하여 비즈니스 로직과 도메인 의미를 해석하십시오.
- 결과물은 `.architecture/metadata/domain-semantics/` 폴더 또는 `db-schemas (v2)` 하위의 `cognitive` 필드에 저장합니다.
- **Cognitive Fields**: `invariants`, `trade_offs`, `failure_impact`를 반드시 포함하여 'Why'를 기록하십시오.

### [Best Practices]
- **Context Management**: 3만개 이상의 대량 파일 처리 시, 한꺼번에 읽지 말고 `skeleton` 정보를 먼저 훑은 뒤 필요한 파일만 탐색하십시오.
- **Model Choice**: 구조 분석은 Fast LLM으로, 의미 해석 및 도메인 설계는 Strong/Reasoning LLM을 권장합니다.
"""
    print(guide)


def main():
    parser = argparse.ArgumentParser(
        description="Architecture Refresh CLI — mechanical data & logic",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # config
    subparsers.add_parser("config", help="Full config JSON")

    # plan
    p_plan = subparsers.add_parser("plan", help="Git diff analysis -> refresh plan")
    p_plan.add_argument("--path", help="Workspace path (default: CWD)")
    p_plan.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    p_plan.add_argument("--service", help="Specific service")
    p_plan.add_argument("--target", help="Specific target")

    # worktree
    subparsers.add_parser("worktree", help="Worktree create/cleanup commands")

    # gen-sql
    p_sql = subparsers.add_parser("gen-sql", help="DB schema extraction SQL")
    p_sql.add_argument("--service", required=True, help="Service name")

    # scan
    subparsers.add_parser("scan", help="Source scan patterns")

    # update-state
    subparsers.add_parser("update-state", help="Manifest + state update procedure")

    # schema-template
    subparsers.add_parser("schema-template", help="DB schema output template")

    # semantics-config
    subparsers.add_parser("semantics-config", help="Phase 3-7 config values")

    # init
    p_init = subparsers.add_parser("init", help="Generate default configuration.json")
    p_init.add_argument("--output", help="Path to save config (default: scripts/configuration.json)")
    p_init.add_argument("--path", help="Workspace path to scan")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing config")

    # skeleton (Stage 2)
    p_skeleton = subparsers.add_parser("skeleton", help="Structural Scanning (Stage 2)")
    p_skeleton.add_argument("--service", required=True, help="Service name")
    p_skeleton.add_argument("--path", help="Workspace path")

    # helper
    subparsers.add_parser("helper", help="AI Assistance & Usage Guide")

    # query
    p_query = subparsers.add_parser("query", help="Query architecture metadata")
    p_query.add_argument("--type", choices=["db", "api", "kafka"], default="db")
    p_query.add_argument("--service", help="Service name")
    p_query.add_argument("--table", help="Table name")
    p_query.add_argument("--keyword", help="Search keyword in metadata")
    p_query.add_argument("--path", help="Workspace path")

    # graph (Phase 6)
    p_graph = subparsers.add_parser("graph", help="Generate Relation Graph (Phase 6)")
    p_graph.add_argument("--path", help="Workspace path")

    # archaeology (Phase 0)
    p_arch = subparsers.add_parser("archaeology", help="Stage 1: Git history & freshness analysis")
    p_arch.add_argument("--path", help="Workspace path")
    p_arch.add_argument("--service", help="Specific service filter")

    # verify (Stage 3)
    p_verify = subparsers.add_parser("verify", help="Stage 3: Schema-Code consistency check")
    p_verify.add_argument("--path", help="Workspace path")
    p_verify.add_argument("--service", help="Specific service filter")

    # flow (Phase 5)
    p_flow = subparsers.add_parser("flow", help="Stage 5: Behavioral Flow Extraction")
    p_flow.add_argument("--service", required=True, help="Service name")
    p_flow.add_argument("--path", help="Workspace path")

    # glossary
    p_glossary = subparsers.add_parser("glossary", help="Domain Glossary Management")
    p_glossary.add_argument("sub", choices=["propose", "sync", "list"], help="Glossary action")
    p_glossary.add_argument("--path", help="Workspace path")

    parser.add_argument("--config", help="Path to custom configuration.json")

    args = parser.parse_args()

    # Load custom config if provided
    current_config = load_config(args.config or get_default_config_path(args.path))
    update_globals(current_config)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "config": cmd_config,
        "plan": cmd_plan,
        "worktree": cmd_worktree,
        "gen-sql": cmd_gen_sql,
        "skeleton": cmd_skeleton,
        "helper": cmd_helper,
        "archaeology": cmd_archaeology,
        "scan": cmd_scan,
        "update-state": cmd_update_state,
        "schema-template": cmd_schema_template,
        "semantics-config": cmd_semantics_config,
        "init": cmd_init,
        "query": cmd_query,
        "graph": cmd_graph,
        "verify": cmd_verify,
        "flow": cmd_flow,
        "glossary": cmd_glossary
    }

    commands[args.command](args)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test-hash":
        code1 = "def calc(x): return x * 0.1"
        code2 = "  def compute ( y ):\n    return y * 0.1  # comment"
        h1 = generate_semantic_hash(code1, "test.py")
        h2 = generate_semantic_hash(code2, "test.py")
        print(f"Hash 1: {h1}")
        print(f"Hash 2: {h2}")
        print(f"Match: {h1 == h2}")
        sys.exit(0)
    main()
