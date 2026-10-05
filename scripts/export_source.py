"""Export the current application sources, excluding credentials and build caches."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'app.py', 'mobile_api.py', 'session_security.py', 'apple_identity.py',
    'requirements.txt', 'requirements-dev.txt', 'render.yaml', '.env.example',
    '.gitignore', '.python-version', 'README.md', 'WEB_TO_FLUTTER_APP_SPEC.md',
}
TREES = {'mobile', 'static', 'migrations', 'scripts', 'tests', '.github'}
EXCLUDED_PARTS = {'.git', '.idea', '.dart_tool', 'build', '__pycache__', 'Pods',
                  '.symlinks', '.gradle', 'ephemeral', '.pytest_cache'}
EXCLUDED_NAMES = {'.env', 'local.properties', 'key.properties', 'Generated.xcconfig',
                  'flutter_export_environment.sh', '.flutter-plugins',
                  '.flutter-plugins-dependencies', 'GeneratedPluginRegistrant.java',
                  'Deployment.local.xcconfig'}


def included(path):
    rel = path.relative_to(ROOT)
    return (not any(part in EXCLUDED_PARTS for part in rel.parts)
            and path.name not in EXCLUDED_NAMES
            and not path.name.endswith('.local.json')
            and path.suffix.lower() not in {'.pyc', '.iml', '.jks', '.keystore', '.p12', '.p8', '.pem'})


def main():
    candidates = [ROOT / name for name in FILES]
    for tree in TREES:
        candidates.extend((ROOT / tree).rglob('*'))
    sources = sorted(p for p in candidates if p.is_file() and included(p))
    manifest = {
        'version': '1.0.0+1',
        'baseline_commit': '39173d56af8e642301b1f53adad31a184a19bf1f',
        'status': 'Source validated locally; native builds and staging acceptance pending',
        'files': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sources},
    }
    output = ROOT / 'artifacts' / 'team-parent-mobile-source.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sources:
            archive.write(path, 'qingshan_app/' + path.relative_to(ROOT).as_posix())
        archive.writestr('qingshan_app/release_manifest.json',
                         json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    print(f'{output}: {len(sources)} source files, {output.stat().st_size} bytes')
    print('SHA256:', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
