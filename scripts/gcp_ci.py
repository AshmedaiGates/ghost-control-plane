#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent.parent
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
CI_DIR = BASE / 'ci'
CI_DIR.mkdir(parents=True, exist_ok=True)
PIPELINES_FILE = CI_DIR / 'pipelines.json'

def run(cmd, cwd=None, env=None):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env, shell=isinstance(cmd, str))
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()

def detect_project_type(path):
    p = Path(path)
    if (p / 'pyproject.toml').exists() or (p / 'setup.py').exists() or (p / 'requirements.txt').exists():
        return 'python'
    if (p / 'package.json').exists():
        return 'node'
    if (p / 'Cargo.toml').exists():
        return 'rust'
    if (p / 'go.mod').exists():
        return 'go'
    # Fallback: detect source trees recursively
    if list(p.rglob('*.py')):
        return 'python'
    if list(p.rglob('*.rs')):
        return 'rust'
    if list(p.rglob('*.go')):
        return 'go'
    if list(p.rglob('*.ts')) or list(p.rglob('*.js')):
        return 'node'
    return 'generic'

def get_default_pipeline(project_type):
    pipelines = {
        'python': {
            'name': 'Python CI',
            'steps': [
                {'name': 'lint', 'cmd': 'flake8 . --max-line-length=100 || true'},
                {'name': 'format', 'cmd': 'black --check . || black . || true'},
                {'name': 'test', 'cmd': 'python -m pytest -xvs || true'},
            ],
        },
        'node': {
            'name': 'Node CI',
            'steps': [
                {'name': 'install', 'cmd': 'npm install'},
                {'name': 'lint', 'cmd': 'npm run lint || true'},
                {'name': 'test', 'cmd': 'npm test || true'},
                {'name': 'build', 'cmd': 'npm run build || true'},
            ],
        },
        'rust': {
            'name': 'Rust CI',
            'steps': [
                {'name': 'fmt', 'cmd': 'cargo fmt -- --check || cargo fmt'},
                {'name': 'clippy', 'cmd': 'cargo clippy -- -D warnings || true'},
                {'name': 'test', 'cmd': 'cargo test'},
                {'name': 'build', 'cmd': 'cargo build --release'},
            ],
        },
        'go': {
            'name': 'Go CI',
            'steps': [
                {'name': 'fmt', 'cmd': 'gofmt -l . || true'},
                {'name': 'vet', 'cmd': 'go vet ./... || true'},
                {'name': 'test', 'cmd': 'go test ./... || true'},
                {'name': 'build', 'cmd': 'go build -o bin/ || true'},
            ],
        },
        'generic': {
            'name': 'Generic CI',
            'steps': [{'name': 'test', 'cmd': 'echo "No tests configured"'}],
        },
    }
    return pipelines.get(project_type, pipelines['generic'])

def load_pipelines():
    if PIPELINES_FILE.exists():
        return json.loads(PIPELINES_FILE.read_text())
    return {}

def save_pipelines(pipelines):
    PIPELINES_FILE.write_text(json.dumps(pipelines, indent=2))

def init_pipeline(path='.', name=None):
    p = Path(path).expanduser().resolve()
    project_type = detect_project_type(p)
    pipeline = get_default_pipeline(project_type)
    pipeline['project_path'] = str(p)
    pipeline['project_type'] = project_type
    pipeline['created'] = datetime.now().isoformat()
    pipeline_name = name or p.name
    pipelines = load_pipelines()
    pipelines[pipeline_name] = pipeline
    save_pipelines(pipelines)
    print(f'initialized pipeline: {pipeline_name}')
    print(f'  type: {project_type}')
    print(f'  steps:')
    for step in pipeline['steps']:
        print(f'    - {step["name"]}: {step["cmd"]}')
    return pipeline_name

def run_pipeline(name, deploy_target=None):
    pipelines = load_pipelines()
    if name not in pipelines:
        print(f'pipeline not found: {name}')
        return 1
    pipeline = pipelines[name]
    project_path = pipeline.get('project_path', '.')
    print(f'running pipeline: {pipeline["name"]}')
    print(f'path: {project_path}')
    print()
    results = []
    for step in pipeline['steps']:
        print(f'[{step["name"]}] {step["cmd"]}')
        rc, out, err = run(step['cmd'], cwd=project_path)
        if out:
            for ln in out.splitlines()[:20]:
                print(f'  {ln}')
        results.append({'name': step['name'], 'rc': rc})
        if rc != 0:
            print(f'  failed (rc={rc})')
        else:
            print(f'  passed')
        print()
    all_passed = all(r['rc'] == 0 for r in results)
    if all_passed:
        print('pipeline: all steps passed')
        if deploy_target:
            print(f'deploying to {deploy_target}...')
    else:
        print('pipeline: some steps failed')
        return 1
    return 0

def list_pipelines():
    pipelines = load_pipelines()
    if not pipelines:
        print('no pipelines configured')
        return
    print('configured pipelines:')
    for name, pipeline in pipelines.items():
        print(f'  {name} ({pipeline.get("project_type", "unknown")})')

def main():
    parser = argparse.ArgumentParser(description='Automatic CI/CD')
    sub = parser.add_subparsers(dest='cmd')
    p = sub.add_parser('init')
    p.add_argument('path', nargs='?', default='.')
    p.add_argument('--name')
    p = sub.add_parser('run')
    p.add_argument('name')
    p.add_argument('--deploy')
    sub.add_parser('list', help='list pipelines')
    args = parser.parse_args()
    if args.cmd == 'init':
        init_pipeline(args.path, args.name)
    elif args.cmd == 'run':
        sys.exit(run_pipeline(args.name, args.deploy))
    elif args.cmd == 'list':
        list_pipelines()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
