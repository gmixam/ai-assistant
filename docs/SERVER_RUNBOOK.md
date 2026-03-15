# Server Runbook

## Purpose
This runbook defines how to use the shared server safely while it remains resource-constrained.

## Current Server Constraint
- low-memory host
- no assumption of safe parallel live IDE use
- prior OOM history affecting `node` and `vscode-server` workloads
- runtime containers are not currently the primary source of memory pressure

Operational conclusion:
The main risk is development tooling load, especially Remote SSH, extension hosts, language servers, and watchers.

## Golden Rules
- one active live operator at a time
- default to off-server work
- prioritize runtime stability over dev convenience
- avoid unnecessary background tooling on the host

## Before Starting Live Work
1. Check `ops-control/ACTIVE_OWNER.md`.
2. Confirm there is no other live operator.
3. Use the lightest viable toolchain.
4. Open only the repository you need.
5. Disable or avoid unnecessary remote extensions.

## Remote IDE Rules
- Use one VS Code Remote SSH window per active operator.
- Avoid simultaneous use of multiple AI assistant extensions on the remote host.
- Prefer one AI assistant per live session.
- Disable or limit heavyweight extensions if they are not required.
- Close idle terminals and remote windows when done.

## Watcher Rules
- Exclude large/generated directories from file watching and search.
- Avoid running unnecessary watch-mode processes.
- Do not leave `npm dev`, `vite`, `next dev`, `tsc --watch`, or similar processes running unless the task explicitly requires them.
- If watch mode is required, it becomes the only major live dev workload on the server at that time.

## Docker Rules
- Do not change Compose topology without an explicit task.
- Do not assume containers are safe to overload just because current traffic is low.
- If a container becomes a top resource consumer, capture `docker stats` and inspect before changing anything.
- Consider resource limits at the next infrastructure pass, but do not introduce them ad hoc during unrelated work.

## Live Diagnostics Checklist
Safe commands:
- `uptime`
- `free -h`
- `df -h`
- `top -bn1 | head -40`
- `ps aux --sort=-%cpu | head -25`
- `ps aux --sort=-%mem | head -25`
- `docker ps`
- `docker stats --no-stream`
- `journalctl -u ssh -n 100 --no-pager`
- `dmesg -T | grep -i -E "killed process|out of memory|oom"`

## Handoff Procedure
1. Update code and docs.
2. Record ownership state in `ops-control/ACTIVE_OWNER.md`.
3. Share exact commands run and remaining validations.
4. Close the live session if no longer needed.

## Manual Actions Recommended Outside This Repo
- add swap on the server
- reduce remote IDE extensions
- prefer SSH key-only access and reduce brute-force exposure
- plan RAM upgrade before normalizing multi-project live development

## Upgrade Thresholds
Server upgrade or topology change is strongly recommended when:
- two or more projects need regular live development at the same time
- OOM recurs
- Remote SSH remains unstable after reducing extension and watcher load
- smoke checks compete with active editing sessions
