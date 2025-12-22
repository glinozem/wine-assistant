"""Manage backups stored in MinIO via the `mc` client (MinIO Client).

Key design goal: work on Windows without relying on `grep/awk/sort` *inside*
`minio/mc` container images (those tools may be absent).

This script is intended to be invoked from the repository root:

  python -m scripts.minio_backups prune --keep 10 \
    --bucket wine-backups --prefix postgres \
    --endpoint http://minio:9000 --user minioadmin --password minioadmin123

It runs `mc` through Docker Compose:
  docker compose -f docker-compose.yml -f docker-compose.storage.yml \
    --profile tools run --rm --entrypoint sh mc -lc "..."

No third-party Python dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from scripts.emit_event import Event, emit


@dataclass(frozen=True)
class McContext:
    endpoint: str
    user: str
    password: str
    bucket: str
    prefix: str
    compose_files: List[str]
    compose_profile: str
    compose_service: str

    def remote_path(self) -> str:
        # MinIO client path format: ALIAS/bucket/prefix
        prefix = (self.prefix or "").strip("/")
        if prefix:
            return f"local/{self.bucket}/{prefix}/"
        return f"local/{self.bucket}/"


def _run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    # Docker/mc output is UTF-8. On Windows default console encoding may be cp1251/cp866,
    # which can raise UnicodeDecodeError when capturing output (progress bars etc.).
    return subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
    )



def run_mc_sh(ctx: McContext, sh_script: str, *, check: bool = True) -> str:
    """Run a shell script inside the `mc` compose service and return stdout."""

    # Use --entrypoint sh to avoid depending on the compose service's entrypoint.
    cmd: List[str] = ["docker", "compose"]
    for f in ctx.compose_files:
        cmd.extend(["-f", f])
    cmd.extend(
        [
            "--profile",
            ctx.compose_profile,
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            ctx.compose_service,
            "-lc",
            sh_script,
        ]
    )

    proc = _run(cmd, check=False)
    if check and proc.returncode != 0:
        # Preserve both streams to make troubleshooting easy.
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)

    # Even when check=False, still return stdout for parsing.
    return proc.stdout


def mc_alias_and(cmd: str, ctx: McContext) -> str:
    """Prepend `mc alias set ...` to a command, returning a shell snippet."""

    # We do NOT suppress alias output here; instead, the JSON parser below ignores
    # non-JSON lines. Keeping output helps debugging if credentials are wrong.
    return (
        f"set -e; "
        f"mc alias set local {ctx.endpoint} {ctx.user} {ctx.password}; "
        f"{cmd}"
    )


def iter_dump_keys_from_json_lines(lines: Iterable[str]) -> List[str]:
    keys: List[str] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        key = obj.get("key") or obj.get("name")
        if not key:
            continue
        # `mc ls --json` sometimes returns keys with trailing '/' for prefixes.
        if key.endswith("/"):
            continue
        if key.endswith(".dump"):
            keys.append(key)
    return keys


def list_remote_dumps(ctx: McContext) -> List[str]:
    out = run_mc_sh(ctx, mc_alias_and(f"mc ls --json {ctx.remote_path()}", ctx), check=True)
    keys = iter_dump_keys_from_json_lines(out.splitlines())
    keys.sort()
    return keys


def prune_remote(
    ctx: McContext,
    keep: int,
    *,
    dry_run: bool = False,
    emit_json: bool = False,
    log_file: Optional[Path] = None,
) -> int:
    keys = list_remote_dumps(ctx)
    count = len(keys)
    print(f"[prune-remote] Found={count} Keep={keep}")

    if emit_json and log_file:
        emit(
            Event(
                level="info",
                service="backup",
                event="prune_remote_started",
                fields={"keep": keep, "found_count": count, "dry_run": dry_run},
            ),
            log_file=log_file,
        )

    if count <= keep:
        print("[prune-remote] Nothing to delete")
        if emit_json and log_file:
            emit(
                Event(
                    level="info",
                    service="backup",
                    event="prune_remote_completed",
                    fields={
                        "keep": keep,
                        "found_count": count,
                        "deleted_count": 0,
                        "kept_count": count,
                        "dry_run": dry_run,
                    },
                ),
                log_file=log_file,
            )
        return 0

    to_delete = keys[: max(0, count - keep)]
    for k in to_delete:
        print(f"[prune-remote] deleting {k}")

    if dry_run:
        print("[prune-remote] dry-run: no deletions performed")
        if emit_json and log_file:
            emit(
                Event(
                    level="info",
                    service="backup",
                    event="prune_remote_completed",
                    fields={
                        "keep": keep,
                        "found_count": count,
                        "deleted_count": len(to_delete),
                        "kept_count": count - len(to_delete),
                        "dry_run": True,
                    },
                ),
                log_file=log_file,
            )
        return 0

    # Delete one-by-one (safe; object count is typically small). No external tools.
    for k in to_delete:
        # Keys are expected to be simple filenames (no spaces). Still, quote defensively.
        remote = f"{ctx.remote_path()}{k}"
        run_mc_sh(ctx, mc_alias_and(f"mc rm '{remote}'", ctx), check=True)

    if emit_json and log_file:
        emit(
            Event(
                level="info",
                service="backup",
                event="prune_remote_completed",
                fields={
                    "keep": keep,
                    "found_count": count,
                    "deleted_count": len(to_delete),
                    "kept_count": count - len(to_delete),
                    "dry_run": False,
                },
            ),
            log_file=log_file,
        )

    return 0

def download_latest(
    ctx: McContext,
    restore_dir: Path,
    dest_name: str,
    *,
    emit_json: bool = False,
    log_file: Optional[Path] = None,
) -> int:
    restore_dir.mkdir(parents=True, exist_ok=True)

    keys = list_remote_dumps(ctx)
    if not keys:
        print("[download-latest] No .dump files found in remote")
        return 2

    latest = keys[-1]
    print(f"[download-latest] latest={latest}")

    if emit_json and log_file:
        emit(
            Event(
                level="info",
                service="backup",
                event="download_latest_started",
                fields={"latest": latest, "dest_name": dest_name},
            ),
            log_file=log_file,
        )

    # Copy into the container-mounted /restore path.
    # In docker-compose.storage.yml the `mc` tools container should mount:
    #   - ./restore_tmp:/restore
    # This keeps host paths out of the container command line.
    cmd = f"mc cp '{ctx.remote_path()}{latest}' '/restore/{dest_name}'"
    run_mc_sh(ctx, mc_alias_and(cmd, ctx), check=True)

    host_path = restore_dir / dest_name
    print(f"[download-latest] downloaded -> {host_path}")

    if emit_json and log_file:
        emit(
            Event(
                level="info",
                service="backup",
                event="download_latest_completed",
                fields={"latest": latest, "dest_name": dest_name, "host_path": str(host_path)},
            ),
            log_file=log_file,
        )

    return 0

def build_ctx_from_args(args: argparse.Namespace) -> McContext:
    prefix = args.prefix or ""
    compose_files = args.compose_files or ["docker-compose.yml", "docker-compose.storage.yml"]
    return McContext(
        endpoint=args.endpoint,
        user=args.user,
        password=args.password,
        bucket=args.bucket,
        prefix=prefix,
        compose_files=compose_files,
        compose_profile=args.compose_profile,
        compose_service=args.compose_service,
    )


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="scripts.minio_backups")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--endpoint", required=True, help="MinIO endpoint reachable from the compose network (e.g. http://minio:9000)")
        sp.add_argument("--user", required=True, help="MinIO access key (root user)")
        sp.add_argument("--password", required=True, help="MinIO secret key (root password)")
        sp.add_argument("--bucket", required=True, help="Bucket name, e.g. wine-backups")
        sp.add_argument("--prefix", default="", help="Prefix inside bucket, e.g. postgres")
        sp.add_argument(
            "--compose-files",
            nargs="*",
            default=["docker-compose.yml", "docker-compose.storage.yml"],
            help="Compose files list (default: docker-compose.yml docker-compose.storage.yml)",
        )
        sp.add_argument("--compose-profile", default="tools", help="Compose profile used for the mc container (default: tools)")
        sp.add_argument("--compose-service", default="mc", help="Compose service name for the mc container (default: mc)")
        sp.add_argument("--emit-json", action="store_true", help="Emit structured JSON events (intended for Promtail/Loki)")
        sp.add_argument("--log-file", default=None, help="If set with --emit-json, append JSONL events to this file")

    sp_list = sub.add_parser("list", help="List remote .dump files")
    add_common(sp_list)

    sp_prune = sub.add_parser("prune", help="Prune remote .dump files, keeping only last N")
    add_common(sp_prune)
    sp_prune.add_argument("--keep", type=int, default=10, help="How many most-recent dumps to keep (default: 10)")
    sp_prune.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting")

    sp_dl = sub.add_parser("download-latest", help="Download the latest remote .dump into restore_dir")
    add_common(sp_dl)
    sp_dl.add_argument("--restore-dir", default="restore_tmp", help="Host restore directory (default: restore_tmp)")
    sp_dl.add_argument("--dest-name", default="remote_latest.dump", help="Filename to save as (default: remote_latest.dump)")

    args = p.parse_args(argv)
    ctx = build_ctx_from_args(args)

    if args.cmd == "list":
        keys = list_remote_dumps(ctx)
        for k in keys:
            print(k)
        return 0

    if args.cmd == "prune":
        return prune_remote(ctx, keep=args.keep, dry_run=args.dry_run, emit_json=args.emit_json, log_file=Path(args.log_file) if args.log_file else None)

    if args.cmd == "download-latest":
        return download_latest(ctx, restore_dir=Path(args.restore_dir), dest_name=args.dest_name, emit_json=args.emit_json, log_file=Path(args.log_file) if args.log_file else None)

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
