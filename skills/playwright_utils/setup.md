### Step 1: Playwright 설치 및 버전 확인
- `playwright --version` 명령어를 실행하여 설치 여부와 현재 버전을 확인합니다. (Python 패키지가 시스템 PATH에 등록된 경우)
- 만약 명령어를 찾을 수 없다면 `python3 -m playwright --version`으로 재시도합니다.

### Step 2: 결과 판정 및 설치/업데이트
1. **미설치된 경우**:
   - `pip3 install playwright` → `playwright install --with-deps` 순서로 신규 설치를 수행합니다.
   - **중요**: 프로젝트 루트에 `node_modules`가 생성되지 않도록 반드시 Python 패키지 방식을 따릅니다.
   - 완료 후 `CREATED` 상태를 반환합니다.

2. **설치되어 있으나 업데이트/복구가 필요한 경우**:
   - 브라우저 바이너리 불일치나 수동 복구 요청 시 `playwright install`을 다시 실행하여 환경을 동기화합니다.
   - 필요 시 `pip3 install -U playwright`를 통해 최신 버전으로 업데이트를 시도할 수 있습니다.
   - 완료 후 `UPDATED` 또는 `READY`를 반환합니다.

3. **정상 설치 및 최신 상태인 경우**:
   - `READY` 상태를 반환합니다.

### Step 3: 실패 시 대응
- 설치 과정에서 오류 발생 시 `NOT_READY`를 반환하고 수동 조치를 요청합니다.
