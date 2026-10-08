#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "::error::Deployment failed at line $LINENO (exit $?)." >&2' ERR

fail() { echo "::error::$*" >&2; exit 1; }
[[ ${DEPLOY_PATH:-} = /* && -d $DEPLOY_PATH ]] || fail "DEPLOY_PATH must be an existing absolute directory."
[[ ${EXPECTED_SHA:-} =~ ^[0-9a-f]{40}$ ]] || fail "EXPECTED_SHA must be the full CI-tested commit SHA."
[[ -n ${EXPECTED_REPOSITORY:-} ]] || fail "EXPECTED_REPOSITORY is required."
cd "$DEPLOY_PATH"
[[ $(git rev-parse --show-toplevel) = $(pwd -P) ]] || fail "DEPLOY_PATH must be the repository root."

# Also protects against manual deployments outside GitHub Actions.
exec 9>"$(git rev-parse --git-path dashboard-deploy.lock)"
flock -n 9 || fail "Another deployment is already running for this checkout."
[[ $(git branch --show-current) = main ]] || fail "Server checkout must be on main; detached HEAD is not allowed."
[[ -z $(git status --porcelain) ]] || fail "Server checkout has uncommitted or untracked changes; resolve them before deploying."
origin=$(git remote get-url origin)
case "$origin" in
  "https://github.com/$EXPECTED_REPOSITORY"|"https://github.com/$EXPECTED_REPOSITORY.git"|\
  "git@github.com:$EXPECTED_REPOSITORY"|"git@github.com:$EXPECTED_REPOSITORY.git") ;;
  *) fail "Server origin does not match the workflow repository." ;;
esac
[[ -f .env && -r .env ]] || fail "Server .env is missing or unreadable."
git check-ignore -q .env || fail "Server .env must be ignored by Git."
[[ -z $(git ls-files .env) ]] || fail "Server .env must not be tracked by Git."

git fetch --no-tags origin "$EXPECTED_SHA"
[[ $(git rev-parse FETCH_HEAD) = "$EXPECTED_SHA" ]] || fail "Fetched commit differs from the CI-tested SHA."
[[ -z $(git ls-tree --name-only "$EXPECTED_SHA" -- .env) ]] || fail "The tested commit tracks .env; refusing to overwrite server secrets."
git merge-base --is-ancestor HEAD "$EXPECTED_SHA" || fail "Local main is ahead of or diverged from the tested commit; refusing to roll back or overwrite it."
git merge --ff-only "$EXPECTED_SHA"
[[ $(git rev-parse HEAD) = "$EXPECTED_SHA" ]] || fail "Server HEAD does not match the CI-tested commit."
[[ -z $(git status --porcelain) ]] || fail "Server checkout became dirty during the update."
git check-ignore -q .env || fail "The tested commit must ignore server .env."
[[ -z $(git ls-files .env) ]] || fail "The tested commit must not track server .env."

# Compose parses .env; never source it or print the resolved secret values.
docker compose config --format json | python3 -c '
import json, os, subprocess, sys
def fail(message):
    sys.exit("::error::" + message)
config = json.load(sys.stdin)
project = config["name"]
service = config["services"]["dashboard"]
env = service.get("environment", {})
if not env.get("SECRET_KEY") or not env.get("DB_ADMIN_PASSWORD"):
    fail("Server .env must set SECRET_KEY and DB_ADMIN_PASSWORD.")
port = str(service["ports"][0]["published"])
ids = subprocess.check_output(["docker", "ps", "-aq"], text=True).split()
containers = json.loads(subprocess.check_output(["docker", "inspect", *ids])) if ids else []
own_port = False
for container in containers:
    labels = container["Config"].get("Labels") or {}
    same_project = labels.get("com.docker.compose.project") == project
    own = same_project and os.path.realpath(labels.get("com.docker.compose.project.working_dir", "")) == os.getcwd()
    if same_project and (not own or labels.get("com.docker.compose.service") != "dashboard"):
        fail("Compose project name conflicts with another checkout/service: " + project)
    name = container["Name"].lstrip("/")
    if name in (project + "-dashboard-1", project + "_dashboard_1") and not own:
        fail("Container name conflicts with another project: " + name)
    if not container["State"]["Running"]:
        continue
    for bindings in (container["HostConfig"].get("PortBindings") or {}).values():
        for binding in bindings or []:
            if binding["HostPort"] == port:
                if not own:
                    fail("Host port " + port + " is used by container " + name)
                own_port = True
listeners = subprocess.check_output(["ss", "-H", "-ltn", "sport = :" + port], text=True).strip()
if listeners and not own_port:
    fail("Host port " + port + " is already in use by another process.")
print("Preflight passed for Compose project " + project + ", host port " + port)
'

docker compose build
if ! docker compose up --detach --remove-orphans --wait --wait-timeout 120; then
  docker compose ps
  docker compose logs --tail 100 dashboard
  fail "Container startup/health check failed; inspect the logs above. No automatic rollback was performed."
fi
echo "Deployed tested commit $EXPECTED_SHA successfully."
