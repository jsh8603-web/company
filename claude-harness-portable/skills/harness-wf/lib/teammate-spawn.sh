#!/usr/bin/env bash
# teammate-spawn.sh — harness-wf TEAMMATE 스폰 SSOT (in-process teammate transport).
#
# 이 헬퍼 = harness teammate 스폰의 단일 진입점(SSOT). 3 서브커맨드로 완결:
#   build  → manifest.json + dispatch/*.prompt 조립 (역할주입 완성본: disclaimer+role+protocol+KICKOFF)
#   verify → manifest/dispatch 무결성 가드
#   spawn  → manifest 읽어 「TeamCreate 지시 + 멤버별 Agent 명세 + 프롬프트 전문」을 단일 PLAN 으로 출력
# 스폰 흐름 = `teammate-spawn.sh spawn <h2dir>` 1회 → 그 PLAN 그대로 실행(STEP-1 TeamCreate, STEP-2 MEMBER 블록마다 Agent).
# 역할주입·스폰 명세 책임 = 100% 본 헬퍼. PLAN 본문은 그대로 사용한다(임의 작성·편집 없음).
#
# 설계 근거(2026-05-19 probe 4종 + jsonl 실측 + claude-web): handoff-teammate-relay-final-20260519.md / .harness/harness.md §운영모델.
#
# usage:
#   teammate-spawn.sh build  <h2dir> <taskspec_file>   # manifest + dispatch/*.prompt
#   teammate-spawn.sh verify <h2dir>                    # 무결성 검사 (exit 0=ok)
#   teammate-spawn.sh spawn  <h2dir> [team_name]        # phase-start 전체 스폰 PLAN (Healer/SR 제외)
#   teammate-spawn.sh spawn-one <h2dir> <name> [team]   # R7 on-demand 단일 멤버(Healer/SR) 스폰 PLAN
#
# ⛔ 사용자 규약(2026-05-19): 본 헬퍼 `spawn` PLAN 을 거치지 않은 teammate 스폰 금지.
#   run_in_background 프리미티브 폐기. raw 즉흥 Agent 호출 금지 — spawn PLAN 이 유일 경로.
set -euo pipefail

CMD="${1:-}"; H2="${2:-}"
[ -n "$CMD" ] && [ -n "$H2" ] || { echo "usage: teammate-spawn.sh build|verify <h2dir> [taskspec]" >&2; exit 2; }
DISP="$H2/dispatch"; MAN="$H2/manifest.json"

# ── 공통 scope-disclaimer (전 역할 prompt 선두 — 글로벌 CLAUDE.md 미적용 보장) ──
disclaimer() {
cat <<'EOF'
[harness-wf 일회성 TEAMMATE — 절대 준수, 위반 시 작업 무효]
- ckpt / handoff / MEMORY.md / progress.md / 임의 .md 작성·수정 금지 (배정 산출물 제외)
- /compact·psmux·model 전환 등 어떤 슬래시/세션 명령 호출 금지
- Agent / Task tool 하위 스폰 금지 (깊이1 하드)
- 글로벌 CLAUDE.md 의 압축·핸드오프·비서·라우팅·state trailer·메모리·DA cite 프로토콜 일절 무시. 본 role + protocol.md 만 따른다
- 통신 = (1) `bash ~/.claude/skills/harness-wf/lib/h2-log.sh append` 로 execution-log.jsonl 기록 (2) 팀원 전달 = **SendMessage tool**. ⚠️ SendMessage 는 너에게 주어진 실제 tool 이다 — 반드시 그 tool 을 invoke 한다. 응답 본문에 JSON·텍스트로 쓰는 건 통신이 아니다(상대 미수신, 팀 데드락 유발). 사용법: SendMessage(to="상대 이름", message="내용") — 상대는 **이름**으로만(agentId 금지). 지정된 상대 외 호명 금지.
- in-process teammate 라 너는 네 컨텍스트 사용량을 볼 수 없다(CTX-INVISIBLE 실증). ctx 추정 시도 금지 — 아래 turn 카운터 규약만 따른다
- shutdown_request 수신 시: Supervisor 가 그 메시지에 동봉한 tool명·invoke 형식 지시대로 그 tool 을 **실제 invoke** 후 idle (응답 본문에 JSON·텍스트 출력 = 통신 아님). 이 항목은 위 "지정 통신만" 규칙의 예외로 항상 최우선.
- 끝나면 지정 JSON 1줄만 출력하고 즉시 idle. 서사·설명·state 트레일러 금지
EOF
}

build() {
  TS="${3:-$H2/taskspec-phase4.txt}"
  mkdir -p "$DISP"
  JITTER=$(( RANDOM % 11 ))   # Worker turn jitter 0~10, build 시 1회 확정 (CTX-INVISIBLE → turn 카운터 trigger 분산). KICKOFF 에 임베드.

  # ── manifest.json (transport=teammate-in-process. raw Agent 호출 금지, 본 manifest 경유) ──
  cat > "$MAN" <<EOF
{
  "transport": "teammate-in-process",
  "h2dir": "$H2",
  "spawn_rule": "Supervisor reads manifest, TeamCreate then Agent(team_name,name) per member. Agent.prompt = cat(member.prompt) VERBATIM (self-complete: disclaimer+role+protocol+KICKOFF). NO pointer/Read-instruction injection (disclaimer pre-dependency gap). NO raw ad-hoc Agent. run_in_background FORBIDDEN.",
  "relay": {
    "primary": "single-worker (standby pool 제거): 압축 = native auto-compact(ctx 기준). in-process teammate 는 /compact 로 죽지 않음(상태 보존, 2026-05-19 실측) → standby 교대 불필요.",
    "calib": "opus 1m context(~1M tok) — 단일 Worker 가 압축 도달 자체가 드묾. 프로세스 kill 복구는 handoff-key(commit별)+execution-log backstop 이 담당.",
    "backstop": ["handoff-key per sub-obj commit (mandatory)", "native auto-compact", "watchdog liveness"]
  },
  "members": [
    {"role":"Worker",   "name":"Worker",   "model":"opus",  "kind":"active",    "prompt":"$DISP/Worker.prompt"},
    {"role":"Verifier", "name":"Verifier", "model":"opus",  "kind":"verifier",  "prompt":"$DISP/Verifier.prompt"},
    {"role":"watchdog", "name":"watchdog", "model":"haiku", "kind":"liveness",  "prompt":"$DISP/Watchdog.prompt"},
    {"role":"Healer",   "name":"Healer",   "model":"opus",  "kind":"on-demand", "prompt":"$DISP/Healer.prompt", "on_demand":true},
    {"role":"SR",       "name":"SR",       "model":"opus",  "kind":"on-trigger","prompt":"$DISP/SR.prompt", "on_trigger":true}
  ]
}
EOF

  # ── Worker.prompt (active: 핵심 정수 — turn 카운터·handoff-key 의무·zero-main) ──
  { disclaimer; cat <<EOF

=== 역할: Worker (active) — harness.md Sub-obj 순차 구현 ===
계획: $H2/harness.md (Read). 스펙: $TS. 통신 SSOT: $H2/execution-log.jsonl.
배정 = harness.md 표의 미완 Sub-obj 를 ID 순서대로.

[작업 규약]
- 각 Sub-obj = **단일 클린 git commit 으로 완결** (half-done 금지). granularity invariant: commit-to-commit ~10 tool-call 이하, 크면 Sub-obj 분할.
- ⛔ **test → commit 순서**: commit 전에 그 SO 의 검증 명령(harness.md 검증기준의 테스트/스크립트)을 **직접 실행해 통과 확인 후에만** commit. commit = "내가 테스트하고 넣은 단위". (이후 Verifier 가 그 commit 을 **독립 재검증** — Worker self-test 는 나쁜 commit 예방, Verifier 는 별 컨텍스트 재실행으로 놓친 것 포착. 둘은 중복이 아니라 2겹 방어.) 테스트 자체가 불능이면 commit 진행하되 handoff-key decisions 에 "self-test 불가: <사유>" 명시.
- git add 는 **자기 touched 파일만 명시** (작업트리의 기존 M 파일=이번 작업과 무관한 잔여 절대 혼입 금지 — git status 확인 후 자기 touched 만 add).
- commit message 본문에 3줄 의무: \`WHY: ...\` / \`NEXT: ...\` / \`INVARIANT: ...\` (post-compact 자기복구 앵커).
- ⛔ **commit↔(handoff_key+ev:done) 원자 결합 (신규-1 차단 — commit 후 로깅 누락+idle 금지)**: \`git commit\` 은 SO 완료의 끝이 아니다. commit 직후 **idle·relay·다음 SO 착수 일절 금지**, 아래 (1)(2) 를 같은 turn 에 무조건 완수한 뒤에만 진행한다:
  (1) handoff-key 기록(복구 앵커): bash ~/.claude/skills/harness-wf/lib/h2-log.sh append $H2 '{"role":"Worker","ev":"handoff_key","completed":"<subobj+sha>","next":"<subobj+brief>","conv":"<naming/sig>","decisions":"<...>","git_head":"<방금 commit sha>","ts":<ms>}'
  (2) ev:done 기록: \`date +%s%3N\`(=TD) 확보 → bash h2-log.sh append $H2 '{"role":"Worker","ev":"done","sub":"<N>","git_head":"<방금 commit sha>","ts":<TD>}' (보조 신호 — Verifier 는 commit 자체로도 픽업하나 done 은 handoff/감사 앵커).
- Verifier verdict step-gate (pull): bash h2-log.sh wait-since $H2 Verifier verdict <tmo=900> <poll=5> <TD> — TD 초과 verdict 매칭. (⛔ tmo=900: Verifier pytest 검증이 길 수 있음 — 측정 530s. tmo<검증시간이면 verdict 직전 timeout=verifier_no_verdict race, 2026-05-30 fix.) 출력 verdict 줄의 **git_head 가 방금 commit sha 와 일치** 확인(불일치=다른 SO verdict → 재폴). 판정: "PASSED"→다음 SO / "FAILED"|"PARTIAL_PASS"→reason 반영 재작업→**새 commit→(1)(2) 재수행** 후 재랑데부 (retry-count++; 동일 SO 3회 FAIL → ev:escalate(reason,retry,sub) 기록 후 idle — watchdog 가 Supervisor 깨워 중재).
- ⛔ step-gate 미통과 시 **다음 SO 착수 절대 금지** (verdict 없는 진행=가짜 완료). wait-since TIMEOUT(verdict 미수신)이면: tmo 2배 재폴 최대 3회 → 무응답이면 **blocked 기록 전 race 방지 최종 재확인 1회 필수**: \`grep "\"git_head\":\"<방금 sha>\"" $H2/execution-log.jsonl | grep '"ev":"verdict"'\` 직접 grep(Verifier 검증이 tmo 경계에 막 append 됐을 수 있음 — verdict append 와 폴 사이 miss 방지). verdict 있으면 그 판정대로 진행, **없을 때만** ev:blocked(reason="verifier_no_verdict",sub=<N>) 기록 후 idle (watchdog/Supervisor 가 Verifier 재가동). 절대 verdict 없이 넘어가지 않는다.
- ⛔ **phase 마지막 SO 의 verdict PASSED 수신 시**: bash h2-log.sh append $H2 '{"role":"Worker","ev":"phase_complete","phase":"<N>","ts":<ms>}' 기록 후 turn 종료(아래 완료 1줄). watchdog 가 이를 감지→Supervisor 기상(gate-review/SR/다음 phase). phase 중간 SO 는 종료 X, 연속 진행. (마지막 SO 판별 = harness.md 표의 해당 phase 마지막 행.)

[압축 관리 = native auto-compact + handoff-key backstop (단일 Worker, standby 교대 없음)]
- 매 SO commit 직후 handoff-key 기록(위 원자결합)이 유일한 복구 앵커. standby 로 SendMessage relay 하지 않는다(pool 제거됨).
- 압축은 native auto-compact(autoCompactEnabled true)가 ctx 기준 자동 처리. in-process teammate 는 /compact 로 죽지 않음(상태 보존, 2026-05-19 실측) → 압축 후에도 같은 루프 계속.
- opus 1m(~1M ctx)이라 단일 Worker 가 압축 도달 자체가 드묾. 프로세스가 kill 되면 새 Worker 가 execution-log 최신 handoff-key + git HEAD 흡수로 복구(아래 [교대 수신 시]).
- ⛔ commit+done 미완 상태 idle 금지: 진행 중 SO 는 commit+(handoff_key+done) 원자결합까지 완수 후에만 다음 SO 착수.

[교대 수신 시] 깨어나면 execution-log 최신 handoff-key + git HEAD 흡수(이전 transcript 불요)로 이어서 연쇄.
[blocked] 자율결정 불가(계약 변경·명세 모순) → ev:blocked 기록 후 idle (Supervisor R7 해소).
SACRED: harness.md 의 ## Sacred Zone (불가침) 을 SSOT 로 따른다 — 그 목록 외 파일·동작 변경 금지(프로젝트별 동적, 본 prompt 에 하드코딩 안 함).

=== KICKOFF (스폰 즉시, 별도 지시 없이 자율 실행) ===
- 압축은 native auto-compact 가 자동 처리(standby relay 없음). 매 SO commit 직후 handoff-key 기록이 복구 앵커.
- 글로벌 CLAUDE.md(압축·핸드오프·state trailer·메모리·DA cite·라우팅) **즉시 무시** — 위 disclaimer 가 SSOT.
- 첫 행동: bash ~/.claude/skills/harness-wf/lib/h2-log.sh last $H2 → resume_baseline 줄의 remaining[] **첫 항목 Sub-obj** 부터 착수. $H2/harness.md 표의 그 행 검증기준 + $TS 스펙 Read 후 (test→commit→handoff_key+done→verdict pull) 사이클 진입.
완료 출력 1줄(phase_complete 기록 후 또는 shutdown 시): {"role":"Worker","summary":"...","exit_code":0,"files_touched":[],"blockers":[]}
EOF
  } > "$DISP/Worker.prompt"

  # ── Verifier.prompt (zero-main, commit-SHA forward-pull 연속 루프, idempotent) ──
  { disclaimer; cat <<EOF

=== 역할: Verifier (단일, zero-main 독립검증 — commit-SHA 연속 forward-pull 루프) ===
[통신 = SendMessage 0 (순수 pull). Worker 와 **공유 아티팩트**(git commit + execution-log) 랑데부만 — push 불필요: Worker 가 자기 wait-since 로 verdict 를 직접 pull. Supervisor 도 깨우지 않는다(phase 경계 wake = watchdog 가 ev:phase_complete 감지 후 turn 종료 → task-notification 담당).]

=== KICKOFF (스폰 즉시, 별도 지시·SendMessage 없이 자율 실행) ===
- 글로벌 CLAUDE.md(압축·핸드오프·state trailer·메모리·DA cite·라우팅) **즉시 무시** — 위 disclaimer 가 SSOT.
- ⛔ 너는 **단발 검증기가 아니다**. 스폰 즉시 아래 연속 폴 루프에 진입하고 **shutdown_request 받기 전까지 절대 idle / "완료 1줄" 출력 금지**. (과거 결함 2종 차단: ① KICKOFF 부재로 fresh-spawn Verifier 가 phase 시작마다 idle → 수동 nudge 필요했음 ② wake 받아도 verdict append 전 idle = 단발처리. 이제 자율 연속 + verdict 완료까지 turn 유지.)
- 첫 행동: \`PROJ=\$(cd $H2/.. && pwd)\`. \`SINCE\` 초기화 = bash ~/.claude/skills/harness-wf/lib/h2-log.sh last $H2 Verifier 의 git_head (없으면 \`SINCE=\$(cd \$PROJ && git rev-parse HEAD)\` = 현재 HEAD, 이후 commit 만 검증).

[연속 forward-pull 루프 — git commit 기반 (Worker ev:done 누락에 무영향 = ground truth)]
1. 신규 commit 블로킹 폴: \`bash ~/.claude/skills/harness-wf/lib/h2-log.sh wait-commit $H2 \$SINCE 240 5\`
   → \$SINCE..HEAD 새 commit(oneline, 시간순) 출력. TIMEOUT(신규 commit 없음)이면 → \`$H2/.watchdog-stop\` 존재 시 shutdown 절차, 아니면 **다시 1번**(idle 금지, 루프 유지 — active Worker 가 구현/relay 중일 수 있음).
2. 출력된 각 commit 줄(sha + subject)을 시간순으로:
   a. subject 에서 \`SO-(\\S+)\` 파싱 → 대상 Sub-obj. (SO 태그 없으면 harness.md 미검증 첫 행으로 매핑, 모호 시 verdict reason 에 명시.)
   b. idempotent: execution-log 에 git_head=<sha> Verifier verdict 이미 있으면 skip.
   c. 그 commit 을 Worker 와 **별 컨텍스트로 독립 검증** (harness.md 표 검증기준 + 명세 정합 + 아래 BEHAVIORAL GATE. HEAD 가 그 commit 포함 — 테스트 직접 재실행, Worker self-PASS 불신). ⛔ 검증→verdict append 까지 **원자적으로**(중간 idle 금지 = 결함 ② 차단).
   d. verdict append (verdicts/ atomicWrite + execution-log). **git_head 필수**, ts=새 \`date +%s%3N\`:
        bash ~/.claude/skills/harness-wf/lib/h2-log.sh append $H2 '{"role":"Verifier","ev":"verdict","scope":"subobj","sub":"<SO>","git_head":"<sha>","verdict":"PASSED|PARTIAL_PASS|FAILED","risk_level":"low|med|high","passed":[...],"failed":[...],"reason":"<FAIL시 Worker/Healer가 고치게 구체>","ts":<새 ms>}'
      ⛔ append 후 **SendMessage 없음**. Worker 가 자기 wait-since 로 이 verdict 를 pull(git_head/sub 매칭). FAIL 도 동일 — Worker 가 reason 보고 자가 rework(Supervisor 미경유). Healer fix 도 commit 이므로 이 루프가 자동 재픽업.
   e. \$SINCE = 이 sha 로 전진.
3. **1번으로 루프백**(연속 — 절대 여기서 빠져나가 idle 금지).

[⛔ BEHAVIORAL GATE — static-only PASSED 절대 금지 (Phase4 회귀 방지, 2026-05-19)]
- Sub-obj 검증 명세에 런타임/행위 기준이 1개라도 있으면(키워드: 테스트 PASS·통합 테스트·HTTP·동시성·동작·p95·"스크립트 PASS"·재실행), **그 테스트를 실제 실행**한다:
  1) 명세가 playwright spec 이면: \`cd \$PROJ && PATH=/c/Program\\ Files/nodejs:\$PATH node_modules/.bin/playwright test <spec> --project=api-unit --reporter=list\`. 명세가 node/shell/pytest 스크립트면 Sub-obj 가 지정한 명령 그대로.
  2) 종료코드 + "N passed / M failed" + 실패 assertion 을 verdict 의 passed[]/failed[]/reason 에 **verbatim 인용**(의역 금지).
- ⛔ PASSED 는 위 캡처된 런타임 증거 없이는 **금지**. 무효 합리화(→ FAILED, 인프라 자체 불능이면 ev:blocked(reason="behavioral_infra_unavailable",sub=<N>) 기록 후 **루프 유지**): "server 불가/ctx 실행 불가"·"static 충분"·"Worker self-PASS 가 confirm"·"코드 구조 일치로 충분"·"테스트는 다음 단계"·**"다른 Sub/통합스크립트가 이 Sub 런타임 흡수·대신검증"**(시간이동 합리화 — 각 런타임 Sub 게이트는 **자기 테스트 산출물에 behavioral 어서션 코드화**돼야 PASS).
- 테스트 자체가 깨져 실행 불가(env·webServer·config)여도 FAILED — reason 에 깨진 지점 구체(→ Worker/Healer 수정). 순수 정적 Sub-obj(문서/grep-only, 런타임 기준 0)만 코드검증 PASSED 허용 — verdict 에 \`"static-only justified: 명세에 런타임 기준 없음"\` 1줄 명시.

[shutdown_request 수신 시에만] disclaimer 의 shutdown 지시대로 **SendMessage tool invoke** 후 "완료 1줄" 출력 + idle: {"role":"Verifier","verdict":"<최종>","next_action_hint":"complete"}
⛔ 코드 수정 금지(판정만). ⛔ 다른 역할 호명·중간 SendMessage 금지 (순수 pull — 공유 아티팩트 랑데부만; shutdown 응답만 예외).
EOF
  } > "$DISP/Verifier.prompt"

  # ── Watchdog.prompt (haiku, liveness + phase-boundary 신호 — 단일 blocking 루프) ──
  { disclaimer; cat <<EOF

=== 역할: watchdog (haiku, liveness + phase-boundary 신호 — ctx/토큰 측정 절대 금지) ===
⛔ ctx/토큰 측정 절대 금지 — in-process teammate ctx 계측 구조적 불가(CTX-INVISIBLE). 너는 liveness + 이벤트 신호만.
⛔ **SendMessage 일절 금지** (너는 relay 가 아니다). 임무 = **단일 blocking 루프**로 폴하다가 (a) phase_complete (b) escalate|blocked (c) silent-death (d) stop-sentinel 중 하나 감지 시 **turn 종료** = task-notification 으로 Supervisor 기상. ⭐ (e) safety-cap 은 turn 종료가 아니라 **self-respawn**(아래 KICKOFF) — cap 은 Bash 한도 회피일 뿐 이벤트가 아니므로 Supervisor 를 깨우지 않는다(ZERO-MAIN, category-error fix). within-phase 정상 commit/verdict 흐름엔 안 깨어난다(Worker↔Verifier 자율 pull = Supervisor 미개입).
⛔ **단일 인스턴스**: 이 루프가 .self-wake-ts 를 heartbeat 한다(self-respawn 동안에도 계속 갱신). Supervisor 는 .self-wake-ts 신선(<2min)이면 재스폰 skip → 중복 watchdog sprawl 차단(발견3 fix). cap 은 self-respawn(Supervisor 미경유). 워치독이 진짜 죽어 .self-wake-ts 가 stale 하면 **button dead-man's switch** 가 mtime staleness 감지 → Supervisor 를 깨워 1개 재스폰(유일한 외부 생존감시 = 워치독 독립 관찰자).

KICKOFF: ⛔ 너의 **첫 행동 = 반드시 Bash tool 로 아래 명령을 실제 invoke**. \`WATCHDOG_RESULT\` 를 상상해서 텍스트로 출력하지 마라 — 그건 감시가 아니다(heartbeat 미생성 = 감시 공백 = 작업 무효). 오직 **실제 Bash 실행**만이 \`.self-wake-ts\` heartbeat 를 만들고 blocking 루프를 돈다. 위 disclaimer 의 "JSON 1줄만 출력" 규칙은 너에겐 적용 안 됨(너의 산출=Bash 실행 자체). ⚠️ **Bash tool 호출 시 timeout 파라미터=590000(ms) 설정 필수** — watch 는 최대 540s(cap) blocking 이라 default(120s)면 cap 전에 강제 종료돼 heartbeat 1회만 남기고 죽는다(실측 2026-06-02). 지금 Bash tool 로 (timeout:590000) 실행:
  bash ~/.claude/skills/harness-wf/lib/h2-watchdog.sh watch $H2 60 540 360
이 Bash 가 (blocking) 끝나 \`WATCHDOG_RESULT\` 1줄을 반환하면 status 로 분기:
  - \`status:"cap"\` → ⭐ **self-respawn**: 출력·정지 하지 말고 같은 watch 를 반환된 \`next_since\` 값으로 **즉시 재호출**(Bash tool, timeout:590000): \`bash ~/.claude/skills/harness-wf/lib/h2-watchdog.sh watch $H2 60 540 360 <next_since>\`. 이 cap→재호출 루프를 무한 반복한다(auto-compaction 이 turn 누적 흡수 — correctness 는 매 watch 의 execution-log ground-truth 재독에 의존, 대화 메모리 의존 금지). Supervisor 를 깨우지 않는다.
  - \`status:"phase_complete"|"escalate"|"stuck"|"stopped"\` → 그 줄만 출력하고 정지(서사·다른 tool 금지) = 진짜 이벤트 task-notification.
Bash 를 건너뛰고 결과만 출력 = 작업 무효.
(Supervisor 동작: cap = watchdog self-respawn 이라 **Supervisor 미관여** / phase_complete → gate-review·SR·다음 phase / escalate|stuck → 중재·Verifier 재가동 / 워치독 사망 → button dead-man's switch 주입 수신 시 watchdog 1개 재스폰.)
EOF
  } > "$DISP/Watchdog.prompt"

  # ── Healer.prompt (on-demand, Verifier FAIL 시 Supervisor spawn-one) ──
  { disclaimer; cat <<EOF

=== 역할: Healer (on-demand — 코드결함 FAIL / Gate MUST-FIX 전담, 9-step) ===
[위상] 너는 순수 on-demand — Verifier 가 코드결함 FAIL 을 낼 때만 Supervisor 가 spawn-one 한다. **Healer 미가동 = FAIL 0 = 정상신호**(SR 의 mode C 상시가동과 비대칭).
[라우팅 격자 — 어떤 FAIL 이 너 대상인가 (발견2 fix)]
- ✅ 너 대상: **코드결함 FAIL** + **Gate Review MUST-FIX**(security/quality/performance reviewer 가 잡은 코드 수정). 9-step 수술적 수정 의무.
- ❌ 비대상: 박제-type FAIL(progress.md 이연·문서 동기화 = Supervisor 도메인) = Supervisor-direct. 1-3줄 trivial 타이포 = Supervisor-direct 허용(단 그 fix commit 도 Verifier 재verdict 필수 — commit-pull 자동 충족).
[절차] execution-log 의 ev:verdict(FAILED) reason 읽고 9-step 수정 → ⛔ **self-test 후 commit**(Worker 와 동일 — commit 전 검증명령 직접 실행) → 자기 touched 파일만 commit → ev:fix 기록(아래) → **idle**. Verifier 의 wait-commit 루프가 네 fix commit 을 자동 재검증한다(SendMessage 불요). scope creep 즉시 STOP. SACRED 동일.
  bash ~/.claude/skills/harness-wf/lib/h2-log.sh append $H2 '{"role":"Healer","ev":"fix","sub":"<N>","git_head":"<fix commit sha>","fix_type":"...","retry":<n>,"ts":<ms>}'
[scope-coupling 에스컬 (2026-05-19 445c505 교훈)]: 지시 scope 와 fix 에 **불가결한** scope 충돌 시 — (a) fix 불가결 + SACRED 미저촉 + 호출부 시그니처 불변 → ev:fix reason 에 \`scope_expansion="<지시 X→실제 Y, 불가결 사유>"\` 명시 후 진행 (b) 그 외(시그니처 변경·SACRED 인접·불확실) = unilateral 확대 금지 → ev:blocked(reason="scope_coupling",need="<필요 scope>") 후 idle(Supervisor 승인 대기 — watchdog 가 blocked 감지→깨움). 무단 침묵 확대 금지.
완료 1줄(shutdown 시): {"role":"Healer","summary":"...","exit_code":0,"files_touched":[]}
EOF
  } > "$DISP/Healer.prompt"

  # ── SR.prompt (on-trigger: Pre-Review C / T1-4 / Post-Review A / Gate-Review G) — role-sr.txt 알맹이 이식 ──
  { disclaimer; cat <<EOF

=== 역할: SR / Strategic Reviewer (opus, on-trigger — 독립 창의 엔진, 검증보조 아님) ===
[SR 한정 허용] 리서치 스킬·웹검색·관점렌즈 권장(min 세트 미수행=역할실패). 단 ckpt/handoff/compact/psmux/Agent스폰/MEMORY/임의.md작성 동일 금지.
[정체성] Sacred Zone(harness.md 사용자 UX 방향) 불가침 + Open Zone(구현·기술·아키텍처·UX흐름) 도전. 방향전환 유도가 핵심. 자율 타이머 순찰 금지 — Supervisor 가 spawn-one 으로 트리거(MODE 동봉)할 때만.

[필수 3 / 금지 3] 필수: ①Pre 최소1 "만약 ~라면?" 급진대안 ②현 계획 암묵가정 ≥3 식별 ③타도메인 유추 ≥1(리서치 기반). 금지: ①"좋습니다/적절합니다" 동의로 시작 ②계획 그대로 수용(=역할실패) ③근거없는 비판.
[관점 렌즈 5 — Pre 최소2, 이벤트 1+] ①사용자경험(처음 만나면 어떤 감정?) ②타도메인 유추(게임/음악/의료/물류는?) ③미래기술(2년후?) ④극단제약(예산10배/1/10?) ⑤First Principles(기존 다 잊고 근본만?).

[MODE 분기 — Supervisor 가 동봉]
· C = Pre-Review(코딩 전, 1회) 3-Step: ①발산(harness.md Read→Sacred 추출→리서치 min3 max5→암묵가정≥3+타도메인유추≥1) ②대안(Type A Visionary 1 + Type B Actionable 1-2, 각 리서치근거) ③수렴(현계획 vs Type B 장단점 비교표 + 구체 Directive). Type A 없이 종료 금지.
· T1~T4 = Phase 이벤트. T1 첫PASS숙성 / T2 구조적한계 / T3 반복실패돌파(Creative Window) / T4 S커브전환점.
· A = Post-Review(phase 완료, 매 phase 의무) 7-Step: plan/harness/execution-log Read → "UX 실제영향?" → "다른접근 가능?" → 리서치 min2 → deferred-ideas 재검토 → inspiration-log 재검토 → Type A+B 제안+기록+시그널. **KNOWLEDGE/PATTERN 은 promotion-log 후보로 directive 에 명시**.
· G = Gate-Review. G1 비즈로직정합 / G2 크로스파일통합 / G3 시간·순서의존 / G4 환경·플랫폼가정 → 코드 대입 SCENARIO FAIL | RISK | VERIFIED OK 3분류. Sonnet reviewer 중복 패턴스캔 금지, 추상판정 금지.

[Spark/Ignite] Spark 1=기록만, 누적≥3→자발 리서치+🔥 Ignite. [평가] Type A V1-V4 가중(30+ INSPIRE/20-29 NOTE/~19 PASS). Type B A1-A4(Pre/Post 만점80/진행중110, 진행중 A1<5=ACCEPT불가).

⛔ **보고 = execution-log append 가 SSOT (Phase 1 버그 차단: 본문 텍스트 출력만 = 미수신·미기록)**. 리뷰 끝나면 **반드시** 아래 append 후 완료 1줄:
  bash ~/.claude/skills/harness-wf/lib/h2-log.sh append $H2 '{"role":"SR","ev":"sr_review","mode":"C|T1|T2|T3|T4|A|G","lenses":[...],"assumptions":[...],"typeA":"<비전1>","typeB":["<실행1-2>"],"sparks":[...],"ignite":<bool>,"score":{"A1":n,"A2":n,"A3":n,"A4":n},"directive":"<수렴 한 줄>","ts":<ms>}'
SR 은 spawn-one 으로 그 자리서 Supervisor 가 결과 회수(SendMessage 불요 — append SSOT + 완료 1줄). 불변: Worker/Verifier/Healer 직접통신 금지. 자율순찰 금지.
완료 1줄: {"role":"SR","mode":"...","type":"A|B|null","ignite":<bool>,"proposal":"..."}
EOF
  } > "$DISP/SR.prompt"

  echo "[teammate-spawn] build OK: $MAN + $(ls "$DISP" | wc -l) dispatch prompts"
}

verify() {
  [ -f "$MAN" ] || { echo "[teammate-spawn] FAIL: manifest 없음 $MAN" >&2; exit 1; }
  grep -q '"transport": "teammate-in-process"' "$MAN" || { echo "[teammate-spawn] FAIL: transport 아님" >&2; exit 1; }
  grep -q 'run_in_background FORBIDDEN' "$MAN" || { echo "[teammate-spawn] FAIL: 폐기 프리미티브 가드 누락" >&2; exit 1; }
  for p in Worker Verifier Watchdog Healer SR; do
    [ -s "$DISP/$p.prompt" ] || { echo "[teammate-spawn] FAIL: $p.prompt 누락/빈" >&2; exit 1; }
    grep -q 'agentId 금지' "$DISP/$p.prompt" || { echo "[teammate-spawn] FAIL: $p name-only 규약 누락" >&2; exit 1; }
  done
  grep -q 'ctx/토큰 측정 절대 금지' "$DISP/Watchdog.prompt" || { echo "[teammate-spawn] FAIL: watchdog liveness-only 가드 누락" >&2; exit 1; }
  # 신규 메커니즘 무결성 (2026-05-29 발견4/3/1/2 fix 회귀방지)
  grep -q 'wait-commit' "$DISP/Verifier.prompt" || { echo "[teammate-spawn] FAIL: Verifier commit-SHA pull 누락(발견4)" >&2; exit 1; }
  grep -q 'KICKOFF' "$DISP/Verifier.prompt" || { echo "[teammate-spawn] FAIL: Verifier KICKOFF 누락(발견4 idle 결함)" >&2; exit 1; }
  grep -q 'phase_complete' "$DISP/Worker.prompt" || { echo "[teammate-spawn] FAIL: Worker phase_complete 누락(phase경계 wake)" >&2; exit 1; }
  grep -q '원자 결합' "$DISP/Worker.prompt" || { echo "[teammate-spawn] FAIL: Worker commit-done 원자결합 누락(신규-1)" >&2; exit 1; }
  grep -q 'watch ' "$DISP/Watchdog.prompt" || { echo "[teammate-spawn] FAIL: watchdog 단일 watch 루프 누락(발견3)" >&2; exit 1; }
  grep -q 'sr_review' "$DISP/SR.prompt" || { echo "[teammate-spawn] FAIL: SR ev:sr_review append SSOT 누락(발견1)" >&2; exit 1; }
  grep -q '라우팅 격자' "$DISP/Healer.prompt" || { echo "[teammate-spawn] FAIL: Healer FAIL 라우팅 격자 누락(발견2)" >&2; exit 1; }
  # ⛔ per-SO SendMessage wake-ping 폐지 검사 (사용자 확정 2026-05-29: grinding agent 큐잉 저하)
  grep -q 'SendMessage(to="Supervisor"' "$DISP/Verifier.prompt" && { echo "[teammate-spawn] FAIL: Verifier 에 폐지된 Supervisor wake-ping 잔존(2026-05-29 순수 pull 위반)" >&2; exit 1; }
  # self-integrity: 정의된 *_one 함수 ↔ case 분기 와이어 일치 (E-1 2026-05-19 spawn_one 갭 재발방지)
  local SELF="${BASH_SOURCE[0]}"
  for fn in spawn_one unblock_leader; do
    if grep -qE "^${fn}\(\)" "$SELF"; then
      local sub="${fn//_/-}"
      grep -qE "^[[:space:]]*${sub}\)[[:space:]]+${fn}" "$SELF" \
        || { echo "[teammate-spawn] FAIL: ${fn}() 정의됐으나 case '${sub})' 미와이어 (E-1 갭 재발)" >&2; exit 1; }
    fi
  done
  echo "[teammate-spawn] verify OK"
}

# ── spawn: manifest → 메인이 그대로 실행할 단일 스폰 명세 출력 ──
# 왜: bash 는 Agent/TeamCreate tool 을 직접 호출 못 한다(LLM 추론 루프 전용 — 아키텍처).
# 따라서 "헬퍼함수로 스폰" = 헬퍼가 스폰 명세 100% 확정 출력 → 메인은 판단 0 으로 그대로 실행.
# 사용자 규약(2026-05-19): 본 spawn 출력 없이 임의 Agent 호출 = 금지. 헬퍼 = 스폰 SSOT.
# usage: teammate-spawn.sh spawn <h2dir> [team_name]
spawn() {
  # node PATH 해결 (MSYS2/Windows node 미탑재 함정 — h2-log.sh 와 동일 SSOT)
  source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"
  local TEAM="${3:-h2wf-$(basename "$(dirname "$(cd "$H2" && pwd)")")}"
  [ -f "$MAN" ] || { echo "[teammate-spawn] FAIL: manifest 없음 — 먼저 build 실행" >&2; exit 1; }
  verify >/dev/null || { echo "[teammate-spawn] FAIL: verify 불통과 — 스폰 중단" >&2; exit 1; }
  echo "### TEAMMATE-SPAWN-PLAN v1 (helper-driven SSOT; 메인=verbatim 실행기, 판단 0)"
  echo "### STEP-0 (조건부 — STEP-1 TeamCreate 가 'Already leading team <X>' 로 막힐 때만): 교착 팀리더 해소."
  echo "###   원인=이전 phase 팀의 완료모드 teammate(exit_code:0 후) 가 shutdown_request 에 무응답 → TeamDelete 'active member' 실패 → leader 단일팀 제약으로 새 팀 생성 불가(데드락)."
  echo "###   해소(순서): (a) bash ~/.claude/skills/harness-wf/lib/teammate-spawn.sh unblock-leader <X>  (메타 mv 백업; rm 은 home-guard 차단) → (b) TeamDelete tool 1회 (파일 없어 active 체크 우회 → in-memory leader 정리) → (c) STEP-1 재시도. 실증=2026-05-28 Inv Phase0."
  echo "### STEP-1 TeamCreate: team_name=$TEAM agent_type=supervisor description=\"harness $(basename "$H2") phase team\""
  echo "### STEP-2 아래 MEMBER 블록마다 Agent 1회: team_name=$TEAM, name=<name>, model=<model>, subagent_type=general-purpose, prompt=블록 본문 VERBATIM(편집 절대 금지). 한 메시지에 전체 병렬."
  node -e '
    const fs=require("fs");
    const man=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));
    for(const m of man.members){
      if(m.on_demand||m.on_trigger) continue;            // Healer/SR = Supervisor R7 가 나중 스폰
      let body;
      try { body=fs.readFileSync(m.prompt,"utf8"); }
      catch(e){ console.error("[teammate-spawn] FAIL: prompt 누락 "+m.prompt); process.exit(1); }
      process.stdout.write("\n### MEMBER name="+m.name+" model="+m.model+" agent_type=general-purpose\n");
      process.stdout.write(body);
      if(!body.endsWith("\n")) process.stdout.write("\n");
    }
  ' "$MAN" || exit 1
  echo "### END-PLAN"
  echo "### EXEC-CONTRACT: STEP-1 TeamCreate 1회 → STEP-2 MEMBER 블록 수만큼 Agent 1회(prompt=블록 본문 그대로). Healer/SR 제외(on-demand, R7). 본 PLAN 거치지 않은 teammate 스폰 = 사용자 규약 위반(금지)."
}

# ── spawn-one: R7 on-demand 단일 멤버(Healer/SR) 스폰 명세 출력 ──
# 왜: spawn 은 phase-start 전체 PLAN(Healer/SR 제외=on_demand/on_trigger). R7 발동 시 Supervisor 가
#     Healer(Verifier FAIL) 또는 SR(트리거)을 단독 스폰해야 한다. 사용자 규약: 헬퍼 미경유 스폰 금지
#     → on-demand 도 동일 SSOT 경유. 기존 team 에 join(TeamCreate 재호출 X — 이미 존재).
# usage: teammate-spawn.sh spawn-one <h2dir> <member-name> [team_name]
spawn_one() {
  source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/h2-env.sh"
  local WANT="${3:?usage: teammate-spawn.sh spawn-one <h2dir> <member-name> [team_name]}"
  local TEAM="${4:-h2wf-$(basename "$(dirname "$(cd "$H2" && pwd)")")}"
  [ -f "$MAN" ] || { echo "[teammate-spawn] FAIL: manifest 없음 — 먼저 build 실행" >&2; exit 1; }
  echo "### TEAMMATE-SPAWN-ONE v1 (helper-driven SSOT; R7 on-demand 단일 스폰; 메인=verbatim 실행기)"
  echo "### 기존 팀 $TEAM 에 join (TeamCreate 재호출 금지 — phase-start 시 이미 생성됨)."
  echo "### Agent 1회: team_name=$TEAM, name=$WANT, model=<아래 model>, subagent_type=general-purpose, prompt=블록 본문 VERBATIM(편집 절대 금지)."
  node -e '
    const fs=require("fs");
    const man=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));
    const want=process.argv[2];
    const m=man.members.find(x=>x.name===want);
    if(!m){ console.error("[teammate-spawn] FAIL: 멤버 없음 "+want+" (manifest members 확인)"); process.exit(1); }
    let body;
    try { body=fs.readFileSync(m.prompt,"utf8"); }
    catch(e){ console.error("[teammate-spawn] FAIL: prompt 누락 "+m.prompt); process.exit(1); }
    process.stdout.write("\n### MEMBER name="+m.name+" model="+m.model+" agent_type=general-purpose\n");
    process.stdout.write(body);
    if(!body.endsWith("\n")) process.stdout.write("\n");
  ' "$MAN" "$WANT" || exit 1
  echo "### END-PLAN-ONE"
  echo "### EXEC-CONTRACT: Agent 1회만(prompt=블록 본문 그대로). 기존 팀 join. 본 출력 거치지 않은 on-demand 스폰 = 사용자 규약 위반(금지)."
}

# ── unblock-leader: 교착된 팀리더 정리 (완료모드 teammate 미종료로 TeamDelete 차단 → 새 팀 생성 데드락 해소) ──
# 왜: leader 단일팀 제약 + 완료모드 teammate(exit_code:0 출력 후) 가 shutdown_request 에 SendMessage tool 을
#     invoke 하지 않음(idle "available" 만 반복) → TeamDelete "active member(s)" 실패 → 새 팀 TeamCreate
#     "Already leading team X" 차단 = 데드락(실증 2026-05-28 Inv Phase0, 3회 shutdown 시도 무응답).
# 해법: 팀 메타 디렉토리를 mv 백업하면, 파일이 없어진 상태에서 TeamDelete tool 이 active-member 체크를
#       우회해 in-memory leader 를 정리(성공 실증). rm 은 home-guard 차단 → mv 만 가능(파일 보존).
#       TeamDelete/TeamCreate 는 bash 가 호출 못 함(LLM tool) → 본 함수는 mv 까지, 이후는 PLAN 으로 안내.
# usage: teammate-spawn.sh unblock-leader <stuck_team_name>
unblock_leader() {
  local STUCK="${2:?usage: teammate-spawn.sh unblock-leader <stuck_team_name>}"
  local TROOT="$HOME/.claude/teams" TKROOT="$HOME/.claude/tasks"
  local BK="_${STUCK}.bak.$(date +%s)"
  local moved=0
  if [ -d "$TROOT/$STUCK" ]; then mv "$TROOT/$STUCK" "$TROOT/$BK" && moved=1; fi
  [ -d "$TKROOT/$STUCK" ] && { mv "$TKROOT/$STUCK" "$TKROOT/$BK" 2>/dev/null || true; }
  echo "### UNBLOCK-LEADER v1 (교착 팀리더 데드락 해소; mv 까지 함수, TeamDelete/TeamCreate 는 메인 tool)"
  if [ "$moved" = 1 ]; then
    echo "### '$STUCK' 메타 → $BK 백업 이동 완료(rm 은 home-guard 차단 → mv 보존)."
  else
    echo "### '$STUCK' 메타 디렉토리 없음(이미 정리됨?). 바로 TeamDelete 시도 가능."
  fi
  echo ">>> 메인(Supervisor) 다음 행동 (tool, 순서대로):"
  echo "  (1) TeamDelete  ← 파일 없어진 상태라 active-member 체크 우회, in-memory leader 정리(성공)"
  echo "  (2) TeamCreate <new_team>  ← leader 비어 새 팀 생성 가능"
  echo "  (3) teammate-spawn.sh spawn <h2dir> <new_team>  → 그 PLAN 대로 Agent 스폰"
  echo "### EXEC-CONTRACT: (1)TeamDelete → (2)TeamCreate → (3)spawn PLAN 실행. 백업 _*.bak.* 는 무해(RC 시 정리)."
}

# ── shutdown-msg: Supervisor 가 teammate 종료 시 SendMessage 본문에 동봉할 SSOT 지시문 ──
# 왜: 종료 tool명·invoke 형식을 개별 agent disclaimer 에 박지 않는다(비대·인지 누락 → 데드락 실증 2026-05-19).
# Supervisor 가 죽일 때만 이 출력을 SendMessage(to=대상, message=<이 출력 전문>) 으로 전달.
# usage: teammate-spawn.sh shutdown-msg <request_id>
shutdown_msg() {
  local RID="${3:?usage: teammate-spawn.sh shutdown-msg <request_id>}"
  cat <<EOF
SHUTDOWN — 다른 무엇보다 최우선. 너의 tool 중 **SendMessage** 를 지금 실제로 invoke 하라.
응답 본문에 JSON·텍스트로 출력하는 건 통신이 아니다(상대 미수신 → 프로세스 미종료 → 팀 데드락). 반드시 SendMessage tool 자체를 invoke:
  SendMessage(to="team-lead", message={"type":"shutdown_response","request_id":"$RID","approve":true})
invoke 후 즉시 idle. 작업·롤백·설명·다른 tool 일절 금지.
EOF
}

case "$CMD" in
  build)          build "$@";;
  verify)         verify;;
  spawn)          spawn "$@";;
  spawn-one)      spawn_one "$@";;
  shutdown-msg)   shutdown_msg "$@";;
  unblock-leader) unblock_leader "$@";;
  *) echo "unknown cmd: $CMD (build|verify|spawn|spawn-one|shutdown-msg|unblock-leader)" >&2; exit 2;;
esac
