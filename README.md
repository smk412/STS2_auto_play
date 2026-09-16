# STS2 Auto Play

Slay the Spire 2의 공개된 전투 정보만 사용해 행동을 추천하는 초기 Rule AI입니다.

기본 모드에서는 게임 행동을 실행하지 않습니다. 로컬 STS2MCP 브리지에서 상태를 읽고,
숨겨진 순서 정보를 제거한 뒤 다음 행동 하나를 JSON으로 추천합니다. 명시적인 옵션을
사용하면 추천한 행동 한 번만 실행할 수 있습니다.

## 실행

STS2와 STS2MCP 모드를 실행한 상태에서 저장소 루트에서 다음 명령을 사용합니다.

```powershell
$env:PYTHONPATH = "src"
python -m sts2_auto_play.cli
```

추천한 행동 하나만 실제 게임에 적용하려면 명시적으로 실행 옵션을 사용합니다.

```powershell
python -m sts2_auto_play.cli --execute
```

현재 전투 하나를 끝날 때까지 자동 실행하려면 다음 옵션을 사용합니다.

```powershell
python -m sts2_auto_play.cli --auto-combat
```

## 현재 범위

- 단일 플레이어 전투
- 플레이어 턴의 카드 사용 또는 턴 종료 추천
- 체력, 방어도, 에너지, 손패, 적의 공개 의도 활용
- 뽑기 더미의 실제 배열 순서 제거
- 기본 실행은 추천 전용이며, `--execute` 사용 시 한 행동만 실행
- 행동 전 상태가 달라지면 실행 취소
- 한 번 실행한 뒤 프로세스 종료(자동 반복 없음)
- `--auto-combat`에서만 전투 종료까지 반복 실행
- 자동 전투는 최대 100행동, 상태 안정화, 동일 상태 반복 감지 후 안전 중단
- 실행 기록은 숨겨진 원본 상태를 제외하고 `logs/combat-*.jsonl`에 저장
- 아이언클래드의 타격, 수비, 강타 효과를 카드 ID 기반으로 계산
- 현재 에너지 안에서 즉시 처치 가능한 공격 순서를 방어보다 우선
- 취약 피해와 다수 적의 처치 가능 여부를 판단에 반영

## 주요 구조

- `client.py`: STS2MCP 상태 조회와 행동 전송
- `observation.py`: 공개 정보만 남기는 Fair Observation 변환
- `card_effects.py`: 지원 카드의 피해, 방어도, 상태 효과 수치
- `rule_agent.py`: 즉시 처치, 방어, 공격 우선순위 판단
- `combat_runner.py`: 상태 안정화와 전투 종료까지의 반복 실행
