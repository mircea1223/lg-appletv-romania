#!/usr/bin/env python3
"""Prepare a local one-shot webOS bundle. Does not contact a television.
Derived loader: throwaway96/slopbro commit 21023d56ca424607bb03d2939609cc658c655fc7.
SPDX-License-Identifier: AGPL-3.0-or-later
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

PINNED_COMMIT = '21023d56ca424607bb03d2939609cc658c655fc7'
UPSTREAM_SHA = {
    'slopbro.py': '1a64f7050b3682ab1ac50a3e2998946a93c07abba0dffca0c4b8afc77403d75f',
    'wwwroot/index.html': '0430d93c45885de73ba5f3e2f32b1e4ef9e713234de818162f0cb8ac20a1ff36',
    'wwwroot/package.json': 'f573657cb5db54fd8b0f724ae69d8f8fd6903ec6ca0f038ce2b47e4f45ef1ef0',
    'COPYING': '0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0',
}
TOOLS = Path(__file__).resolve().parent

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Unexpected upstream template; refusing adaptation')
    return text.replace(before, after, 1)

def load_patch_builder():
    spec = importlib.util.spec_from_file_location('lg_appletv_builder', TOOLS / 'build_patch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def build(args):
    upstream = args.upstream.resolve(strict=True)
    inputs = {}
    for relative, expected in UPSTREAM_SHA.items():
        p = upstream / relative
        if p.is_symlink() or not p.is_file() or upstream not in p.resolve().parents:
            raise ValueError('Invalid pinned source file: ' + relative)
        inputs[relative] = p.read_bytes()
        if digest(inputs[relative]) != expected:
            raise ValueError('Upstream file differs from pinned commit: ' + relative)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Output must be a new directory')
    output = output.resolve()
    if output == upstream or upstream in output.parents:
        raise ValueError('Keep generated bundle outside upstream source')
    operation = args.operation
    stage = '/media/internal/downloads/lg-appletv-ro-' + operation + '-' + uuid.uuid4().hex[:16]
    payloads = {}
    if operation == 'export':
        if args.original or args.cleanup_export or args.archive:
            raise ValueError('Export does not accept original or cleanup inputs')
        plan = {'kind': 'lg-appletv-ro-export-v1', 'appId': 'com.apple.appletv',
                'stage': stage, 'persistentRoot': False}
        template = TOOLS / 'export_original.js'
        receipt = stage + '/result.json'
    else:
        if not args.original:
            raise ValueError('--original is required for apply and restore')
        original = args.original.resolve(strict=True)
        if output == original or original in output.parents:
            raise ValueError('Keep bundle separate from original files')
        builder = load_patch_builder()
        with tempfile.TemporaryDirectory(prefix='lg-appletv-guide-') as temporary:
            generated = Path(temporary) / 'patch'
            manifest = builder.build(original, generated)
            files = []
            for row in manifest['files']:
                name = Path(row['path']).name
                staged = 'payload-' + name
                if operation == 'apply':
                    payloads[staged] = (generated / row['path']).read_bytes()
                    current, final = row['originalSHA256'], row['finalSHA256']
                else:
                    payloads[staged] = (original / row['path']).read_bytes()
                    current, final = row['finalSHA256'], row['originalSHA256']
                files.append({'path': row['path'], 'stagedName': staged,
                              'currentSHA256': current, 'outputSHA256': final})
        plan = {'kind': 'lg-appletv-ro-overlay-v1', 'mode': operation, 'files': files}
        if bool(args.cleanup_export) != bool(args.archive):
            raise ValueError('Use both --cleanup-export and --archive together')
        if args.cleanup_export and operation != 'apply':
            raise ValueError('Export-stage cleanup is only supported during apply')
        if args.cleanup_export:
            meta = json.loads(args.cleanup_export.read_text(encoding='utf-8'))
            remote = meta.get('remoteStage', '')
            if meta.get('operation') != 'export' or not re.fullmatch(
                    r'/media/internal/downloads/lg-appletv-ro-export-[a-f0-9]{16}', remote):
                raise ValueError('Not a generated export bundle manifest')
            if not args.archive.is_file() or args.archive.is_symlink():
                raise ValueError('Expected the locally retrieved original archive')
            plan['cleanupExport'] = {'stage': remote,
                                     'archiveSHA256': digest(args.archive.read_bytes())}
        template = TOOLS / 'overlay_transaction.js'
        receipt = '/media/developer/temp/lg-appletv-ro-' + stage.rsplit('/', 1)[1] + '-result.json'
    raw_plan = (json.dumps(plan, indent=2) + '\n').encode('utf-8')
    source = template.read_text(encoding='utf-8')
    if source.count('__STAGE__') != 1 or source.count('__PLAN_SHA__') != 1:
        raise ValueError('Unexpected root module placeholders')
    source = source.replace('__STAGE__', stage).replace('__PLAN_SHA__', digest(raw_plan))
    launcher = inputs['slopbro.py'].decode('utf-8')
    launcher = replace_once(launcher, 'SHELL_SCRIPT = "autoroot.sh"', 'SHELL_SCRIPT = "transaction.json"')
    before = 'SERVICE_FILES = [\n    "package.json",\n    "main.js",\n]'
    after = 'SERVICE_FILES = ' + json.dumps(['package.json', 'main.js'] + list(payloads), indent=4)
    launcher = replace_once(launcher, before, after)
    page = inputs['wwwroot/index.html'].decode('utf-8')
    page = replace_once(page, "var downloadDir = '/media/internal/downloads';",
                        "var downloadDir = '" + stage + "';")
    artifacts = {'slopbro.py': launcher.encode('utf-8'), 'wwwroot/index.html': page.encode('utf-8'),
                 'wwwroot/package.json': inputs['wwwroot/package.json'],
                 'wwwroot/main.js': source.encode('utf-8'), 'wwwroot/transaction.json': raw_plan,
                 'COPYING': inputs['COPYING']}
    for name, raw in payloads.items():
        artifacts['wwwroot/' + name] = raw
    metadata = {'formatVersion': 1, 'operation': operation, 'remoteStage': stage,
                'receiptRemote': receipt, 'upstreamCommit': PINNED_COMMIT,
                'persistentRoot': False, 'containsLocallyGeneratedAppleResources': bool(payloads),
                'files': {name: digest(raw) for name, raw in artifacts.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    try:
        for name, raw in artifacts.items():
            p = output / name
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('xb') as handle:
                handle.write(raw)
            p.chmod(0o600)
        p = output / 'bundle.json'
        p.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        p.chmod(0o600)
    except BaseException:
        shutil.rmtree(output)
        raise
    return {'status': 'prepared-offline', 'bundle': str(output), 'operation': operation,
            'remoteStage': stage, 'receiptRemote': receipt,
            'warning': 'No TV contact or live validation performed by this preparation command'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['export', 'apply', 'restore'])
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--original', type=Path)
    parser.add_argument('--cleanup-export', type=Path, help='bundle.json of a previous export operation')
    parser.add_argument('--archive', type=Path, help='Downloaded private archive, verified before export-stage cleanup')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), indent=2))
    except (OSError, ValueError, RuntimeError) as error:
        print('Refused: ' + str(error), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
