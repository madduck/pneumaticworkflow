"""Smoke tests for Compose wiring and SeaweedFS credential rendering."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / 'scripts/seaweedfs-filer-entrypoint.sh'
ACCESS_KEY = 'entry"key\\withé'
SECRET_KEY = 'secret\twith\ncontrol\r\x01$dollar=and=equals'


@pytest.mark.parametrize(
    'compose_file',
    [
        'docker-compose.yml',
        'docker-compose.src.yml',
        'frontend/docker-compose.yml',
    ],
)
@pytest.mark.parametrize('use_defaults', [False, True])
def test_compose_shares_s3_credentials(
    compose_file: str,
    use_defaults: bool,
) -> None:
    """Pass the same credentials to the client and server in each stack."""
    env = {'PATH': os.environ['PATH'], 'COMPOSE_DISABLE_ENV_FILE': '1'}
    if use_defaults:
        access_key = secret_key = 'any-secret-key-will-work'
    else:
        access_key, secret_key = ACCESS_KEY, 'compose-secret=with=equals'
        env['FILE_SEAWEEDFS_S3_ACCESS_KEY'] = access_key
        env['FILE_SEAWEEDFS_S3_SECRET_KEY'] = secret_key
    result = subprocess.run(
        ['docker', 'compose', '-f', compose_file, 'config', '--format=json'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    services = json.loads(result.stdout)['services']
    filer = services['seaweedfs-filer']
    for service in (services['file-service'], filer):
        assert service['environment']['SEAWEEDFS_S3_ACCESS_KEY'] == access_key
        assert service['environment']['SEAWEEDFS_S3_SECRET_KEY'] == secret_key
    assert filer['tmpfs'] == ['/run/seaweedfs-s3:mode=0700']
    assert filer['entrypoint'] == [
        '/bin/sh', '/etc/seaweedfs/filer-entrypoint.sh', '/run/seaweedfs-s3',
    ]
    assert any(
        volume['source'] == str(ENTRYPOINT) and volume['read_only']
        for volume in filer['volumes']
    )


def test_entrypoint_writes_private_json(tmp_path: Path) -> None:
    """Encode credentials as JSON and pass the private file to the filer."""
    result = subprocess.run(
        ['sh', ENTRYPOINT, tmp_path, 'printf', '%s\n', 'filer', '-s3'],
        env={
            'PATH': os.environ['PATH'],
            'SEAWEEDFS_S3_ACCESS_KEY': ACCESS_KEY,
            'SEAWEEDFS_S3_SECRET_KEY': SECRET_KEY,
        },
        capture_output=True,
        text=True,
        check=True,
    )
    command, flag, config_arg = result.stdout.splitlines()
    assert (command, flag) == ('filer', '-s3')
    assert config_arg.startswith('-s3.config=')
    config = Path(config_arg.split('=', 1)[1])
    assert config.parent == tmp_path
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert json.loads(config.read_text(encoding='utf-8')) == {
        'identities': [
            {
                'name': 'file-service',
                'credentials': [
                    {'accessKey': ACCESS_KEY, 'secretKey': SECRET_KEY},
                ],
                'actions': ['Read', 'Write', 'List', 'Tagging', 'Admin'],
            },
        ],
    }


@pytest.mark.parametrize(
    'missing', ['SEAWEEDFS_S3_ACCESS_KEY', 'SEAWEEDFS_S3_SECRET_KEY'],
)
def test_entrypoint_rejects_empty_credentials(
    tmp_path: Path,
    missing: str,
) -> None:
    """Do not launch a filer with an empty access key or secret key."""
    env = {
        'PATH': os.environ['PATH'],
        'SEAWEEDFS_S3_ACCESS_KEY': ACCESS_KEY,
        'SEAWEEDFS_S3_SECRET_KEY': SECRET_KEY,
    }
    env[missing] = ''
    result = subprocess.run(
        ['sh', ENTRYPOINT, tmp_path, 'true'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not list(tmp_path.iterdir())
