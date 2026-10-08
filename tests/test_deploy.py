import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'deploy.sh'


@unittest.skipUnless(os.name == 'posix', 'Deployment targets Linux')
class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.origin, self.repo = root / 'origin', root / 'server'
        self.origin.mkdir()
        self.git(self.origin, 'init', '-b', 'main')
        self.git(self.origin, 'config', 'user.email', 'test@example.invalid')
        self.git(self.origin, 'config', 'user.name', 'CI test')
        (self.origin / '.gitignore').write_text('.env\n')
        self.commit('initial')
        subprocess.run(['git', 'clone', str(self.origin), str(self.repo)], check=True, capture_output=True)
        (self.repo / '.env').write_text('SECRET_KEY=test\nDB_ADMIN_PASSWORD=test\n')
        self.target = self.commit('tested')
        self.commit('newer untested main')
        tools = root / 'bin'
        tools.mkdir()
        git = tools / 'git'
        git.write_text('#!/bin/sh\nif [ "$1 $2 $3" = "remote get-url origin" ]; then\n'
                       '  echo https://github.com/example/dashboard.git\nelse\n'
                       f'  exec {shlex.quote(shutil.which("git"))} "$@"\nfi\n')
        git.chmod(0o755)
        docker = tools / 'docker'
        docker.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if args[:2] == ['compose', 'config']:
    print(json.dumps({'name':'dashboard-test','services':{'dashboard':{'environment':{'SECRET_KEY':'test','DB_ADMIN_PASSWORD':'test'},'ports':[{'published':'54321'}]}}}))
elif args[:2] == ['ps', '-aq']:
    print('other' if os.environ.get('FAKE_CONTAINERS') else '')
elif args[:1] == ['inspect']:
    print(os.environ['FAKE_CONTAINERS'])
else:
    with pathlib.Path('.git/docker-calls').open('a') as f:
        f.write(' '.join(args) + '\\n')
    if os.environ.get('FAIL_BUILD') and args[:2] == ['compose', 'build']: sys.exit(1)
    if os.environ.get('FAIL_UP') and args[:2] == ['compose', 'up']: sys.exit(1)
''')
        docker.chmod(0o755)
        ss = tools / 'ss'
        ss.write_text('#!/bin/sh\nprintf "%s" "${FAKE_LISTENER:-}"\n')
        ss.chmod(0o755)
        self.env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                        DEPLOY_PATH=str(self.repo), EXPECTED_SHA=self.target,
                        EXPECTED_REPOSITORY='example/dashboard')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, path, *args):
        return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.DEVNULL, text=True).strip()

    def commit(self, text):
        (self.origin / 'content').write_text(text)
        self.git(self.origin, 'add', '.')
        self.git(self.origin, 'commit', '-m', text)
        return self.git(self.origin, 'rev-parse', 'HEAD')

    def run_deploy(self, **env):
        return subprocess.run(['bash', str(SCRIPT)], env=dict(self.env, **env), capture_output=True, text=True)

    def assert_blocked(self, phrase, **env):
        result = self.run_deploy(**env)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(phrase, result.stderr)
        self.assertFalse((self.repo / '.git/docker-calls').exists())

    def test_deploys_exact_tested_sha_not_latest_main(self):
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.target)
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'main')
        self.assertIn('compose up --detach --remove-orphans --wait --wait-timeout 120',
                      (self.repo / '.git/docker-calls').read_text())
        self.assertIn('SECRET_KEY=test', (self.repo / '.env').read_text())

    def test_rejects_wrong_branch(self):
        self.git(self.repo, 'switch', '-c', 'other')
        self.assert_blocked('must be on main')

    def test_rejects_dirty_checkout(self):
        (self.repo / 'content').write_text('local changes')
        self.assert_blocked('uncommitted or untracked')

    def test_rejects_concurrent_deployment(self):
        import fcntl
        with (self.repo / '.git/dashboard-deploy.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_blocked('Another deployment')

    def test_rejects_tracked_env_in_incoming_commit(self):
        (self.origin / '.env').write_text('unwanted secret')
        self.git(self.origin, 'add', '--force', '.env')
        target = self.commit('tracked env')
        self.assert_blocked('refusing to overwrite server secrets', EXPECTED_SHA=target)

    def test_rejects_missing_env(self):
        (self.repo / '.env').unlink()
        self.assert_blocked('.env is missing')

    def test_rejects_older_tested_commit(self):
        self.git(self.repo, 'fetch', str(self.origin), 'main')
        self.git(self.repo, 'merge', '--ff-only', 'FETCH_HEAD')
        self.assert_blocked('ahead of or diverged')

    def test_rejects_project_name_collision(self):
        containers = [{'Config':{'Labels':{'com.docker.compose.project':'dashboard-test',
                      'com.docker.compose.project.working_dir':'/some/other/project'}},
                      'Name':'/other','State':{'Running':False}}]
        self.assert_blocked('project name conflicts', FAKE_CONTAINERS=json.dumps(containers))

    def test_accepts_own_running_stack(self):
        containers = [{'Config':{'Labels':{'com.docker.compose.project':'dashboard-test',
                      'com.docker.compose.project.working_dir':str(self.repo),
                      'com.docker.compose.service':'dashboard'}},
                      'Name':'/dashboard-test-dashboard-1','State':{'Running':True},
                      'HostConfig':{'PortBindings':{'5001/tcp':[{'HostPort':'54321'}]}}}]
        result = self.run_deploy(FAKE_CONTAINERS=json.dumps(containers), FAKE_LISTENER='LISTEN')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_port_used_by_another_container(self):
        containers = [{'Config':{'Labels':{}}, 'Name':'/other','State':{'Running':True},
                      'HostConfig':{'PortBindings':{'5001/tcp':[{'HostPort':'54321'}]}}}]
        self.assert_blocked('used by container', FAKE_CONTAINERS=json.dumps(containers))

    def test_rejects_occupied_port(self):
        self.assert_blocked('already in use', FAKE_LISTENER='LISTEN')

    def test_build_failure_does_not_start_container(self):
        result = self.run_deploy(FAIL_BUILD='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('compose up', (self.repo / '.git/docker-calls').read_text())

    def test_health_failure_is_explicit(self):
        result = self.run_deploy(FAIL_UP='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('startup/health check failed', result.stderr)


if __name__ == '__main__':
    unittest.main()
