"""Reproduce chronological court commits from the retained decision files.

This writes only a new branch in an initialized local repository. It performs
no fetching and writes no existing branch or remote.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess

def stream(source, branch):
    rows=[]; ids=set()
    for path in Path(source).glob('*/*/*.md'):
        if path.name=='README.md': continue
        # Repository files use LF. A checkout may use local CRLF line endings.
        body=path.read_text(encoding='utf8').encode('utf8')
        fields={k:json.loads(v) for k,v in (line.split(': ',1) for line in body.decode('utf8').split('---\n',2)[1].splitlines())}
        assert fields['source_id'] not in ids, fields['source_id']
        ids.add(fields['source_id'])
        rows.append((fields['date'],fields['source_id'],'decisions/'+path.relative_to(source).as_posix(),body,fields))
    for index,(day,source_id,path,body,m) in enumerate(sorted(rows),1):
        name=m['court']+' '+(m['ecli'] or m['docket'])
        email=re.sub('[^a-z0-9]+','-',(m['ecli'] or m['docket']).lower()).strip('-')+'@caselaw.invalid'
        stamp=int(dt.datetime.fromisoformat(day).replace(hour=12,tzinfo=dt.timezone.utc).timestamp())
        trailers=['Kind: court','In-force: '+day,'In-force-basis: decision date in the official decision header','Decided: '+day,'Enacted: '+day,'Court: '+m['court'],'Docket: '+m['docket']]
        if m['ecli']: trailers.append('ECLI: '+m['ecli'])
        if m.get('published'): trailers.append('Published: '+m['published'])
        trailers+=['Source: '+m['source'],'Files: '+path]
        message=(name+'\n\n'+'\n'.join(trailers)+'\n').encode('utf8')
        yield f'commit refs/heads/{branch}\nmark :{index}\nauthor {name} <{email}> {stamp} +0000\ncommitter Lexifina <germany-hamburg-caselaw@lexifina.com> {stamp} +0000\ndata {len(message)}\n'.encode('utf8')+message+b'\n'
        if index>1: yield f'from :{index-1}\n'.encode()
        yield f'M 100644 inline {path}\ndata {len(body)}\n'.encode()+body+b'\n\n'
    yield b'done\n'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',required=True,help='directory containing court/year/decision.md files')
    ap.add_argument('--repo',required=True,help='initialized local target repository')
    ap.add_argument('--branch',default='reproduced-court-history')
    ap.add_argument('--pids',help='append started process IDs to this job log')
    args=ap.parse_args()
    if args.pids:
        with Path(args.pids).open('a') as f: f.write(f'{os.getpid()} court history builder\n')
    env=os.environ.copy(); env.update(GIT_AUTHOR_NAME='Lexifina',GIT_AUTHOR_EMAIL='germany-hamburg-caselaw@lexifina.com',GIT_COMMITTER_NAME='Lexifina',GIT_COMMITTER_EMAIL='germany-hamburg-caselaw@lexifina.com')
    def start(cmd,**kw):
        kw.update(env=env,creationflags=0x08000020 if os.name=='nt' else 0)
        p=subprocess.Popen(cmd,**kw)
        if args.pids:
            with Path(args.pids).open('a') as f: f.write(f'{p.pid} court history git\n')
        return p
    cmd=['git','-c','gc.auto=0','-C',args.repo]
    p=start(cmd+['check-ref-format','--branch',args.branch],stdout=subprocess.PIPE,stderr=subprocess.PIPE); out,err=p.communicate()
    if p.returncode: raise SystemExit(err.decode())
    p=start(cmd+['show-ref','--verify','--quiet','refs/heads/'+args.branch]); p.wait()
    if p.returncode!=1: raise SystemExit('Refusing to write an existing branch')
    p=start(cmd+['fast-import','--quiet','--done'],stdin=subprocess.PIPE)
    for chunk in stream(Path(args.source),args.branch): p.stdin.write(chunk)
    p.stdin.close()
    if p.wait(): raise SystemExit('fast-import failed')
    print('Court history written to new local branch',args.branch)
if __name__=='__main__': main()
