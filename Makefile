# Использование:
#   make up
#   make check
#   make logs
#   make down
#   make migrate
#   make reset
#
# Можно переопределить интерпретатор:
#   make PS=pwsh check

PS ?= powershell
PSFLAGS = -NoProfile -ExecutionPolicy Bypass -File

.PHONY: up check logs down migrate reset dbshell

up:
	$(PS) $(PSFLAGS) docs/dev-checklist.ps1 -Task Up

check:
	$(PS) $(PSFLAGS) docs/dev-checklist.ps1 -Task Check

logs:
	$(PS) $(PSFLAGS) docs/dev-checklist.ps1 -Task Logs

down:
	$(PS) $(PSFLAGS) docs/dev-checklist.ps1 -Task Down

migrate:
	$(PS) $(PSFLAGS) docs/dev-checklist.ps1 -Task Migrate

reset:
	$(PS) $(PSFLAGS) docs/dev-checklist.ps1 -Task Reset

dbshell:
	$(PS) $(PSFLAGS) docs/dev-checklist.ps1 -Task DbShell
