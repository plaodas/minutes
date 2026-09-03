#!/usr/bin/env bash
set -eu

usage() {
  echo "Usage: $0 host port [host port ...] -- command [args...]" >&2
  exit 2
}

if [ "$#" -lt 3 ]; then
  usage
fi

# collect host/port pairs until `--`
pairs=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --)
      shift
      break
      ;;
    *)
      if [ "$#" -lt 2 ]; then
        usage
      fi
      pairs+=("$1:$2")
      shift 2
      ;;
  esac
done

if [ ${#pairs[@]} -eq 0 ]; then
  usage
fi

# default timeout per host in seconds
TIMEOUT=${WAIT_FOR_TIMEOUT:-60}

for p in "${pairs[@]}"; do
  host=${p%%:*}
  port=${p##*:}
  echo "Waiting for ${host}:${port} (timeout ${TIMEOUT}s)"
  start=$(date +%s)
  while :; do
    # use bash /dev/tcp check (works in typical images with bash)
    if (</dev/tcp/${host}/${port}) >/dev/null 2>&1; then
      echo "${host}:${port} is available"
      break
    fi
    now=$(date +%s)
    if [ $((now - start)) -ge ${TIMEOUT} ]; then
      echo "Timeout waiting for ${host}:${port}" >&2
      exit 1
    fi
    sleep 1
  done
done

if [ "$#" -eq 0 ]; then
  echo "No command specified after --" >&2
  usage
fi

echo "Starting: $@"
exec "$@"
