#!/usr/bin/env python3
"""Verify a private TV export and extract static files into a NEW directory.
SPDX-License-Identifier: AGPL-3.0-or-later
"""
import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath

APP = 'media/cryptofs/apps/usr/palm/applications/com.apple.appletv'
IMAGES = 'media/cryptofs/apps/usr/palm/data/images/com.apple.appletv'
STATIC = [APP + '/AppleTV', APP + '/appinfo.json', APP + '/res', APP + '/lib', IMAGES]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--result',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        result=json.loads(args.result.read_text(encoding='utf-8'))
        if result.get('status')!='success' or result.get('kind')!='lg-appletv-ro-export-v1':
            raise ValueError('Export has no successful receipt')
        hasher=hashlib.sha256()
        with args.archive.open('rb') as handle:
            for data in iter(lambda:handle.read(1024*1024),b''):hasher.update(data)
        if hasher.hexdigest()!=result.get('archiveSHA256'):
            raise ValueError('Archive SHA256 differs from TV receipt')
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('Choose a new output directory')
        with tarfile.open(args.archive,'r:') as archive:
            members=archive.getmembers()
            seen=set()
            for member in members:
                p=PurePosixPath(member.name)
                normalized=str(p)
                if p.is_absolute() or '..' in p.parts or normalized in seen:
                    raise ValueError('Unsafe or repeated archive path')
                seen.add(normalized)
                if not any(normalized==root or normalized.startswith(root+'/') for root in STATIC):
                    raise ValueError('Archive contains a nonstatic or unexpected path: '+normalized)
                if not (member.isfile() or member.isdir()):
                    raise ValueError('Links or special archive members are not accepted')
            if not {APP+'/AppleTV',APP+'/appinfo.json',APP+'/res/app.js',APP+'/res/main.js',APP+'/res/4239.js'}.issubset(seen):
                raise ValueError('Archive lacks required original resources')
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.mkdir(mode=0o700)
            try:
                for member in members:
                    destination=args.output.joinpath(*PurePosixPath(member.name).parts)
                    if member.isdir():destination.mkdir(mode=0o700,parents=True,exist_ok=True)
                    else:
                        destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                        with archive.extractfile(member) as source,destination.open('xb') as target:
                            shutil.copyfileobj(source,target)
                        destination.chmod(0o600)
            except BaseException:
                shutil.rmtree(args.output)
                raise
        print(json.dumps({'status':'verified-and-extracted','archiveSHA256':hasher.hexdigest(),
                          'originalApplicationFolder':str((args.output/APP).resolve())},indent=2))
    except (OSError,ValueError,tarfile.TarError) as error:
        parser.exit(1,'Refused: '+str(error)+'\n')

if __name__=='__main__':main()
