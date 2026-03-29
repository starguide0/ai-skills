# Postgres MCP 조회 가이드
- **도구**: `postgres_dev_ai` 또는 `postgres_prod_readonly` MCP
- **조회 전략**:
  - `mcp_postgres_dev_ai_query(sql="SELECT * FROM ... LIMIT 10")`
  - 장애 발생 시점 전후의 레코드를 우선 확인하세요.
