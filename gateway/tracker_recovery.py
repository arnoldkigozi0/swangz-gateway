"""Sanitised DNS/history diagnostics. Never loads credentials or connects to the old database."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from datetime import datetime, timezone

HOST=re.compile(r'https://([a-z0-9-]+\.supabase\.co)',re.I)

def diagnose(repo,configs=()):
    refs=set(); commits=subprocess.check_output(['git','log','--format=%H','--','index.html'],cwd=repo,text=True).splitlines()
    for sha in commits:
        source=subprocess.check_output(['git','show',sha+':index.html'],cwd=repo,text=True)
        refs.update(h.lower() for h in HOST.findall(source))
    local=set();inspected=0
    for path in configs:
        file=Path(path)
        if file.is_file():
            local.update(h.lower() for h in HOST.findall(file.read_text(errors='replace')));inspected+=1
    current=os.environ.get('TRACKER_SUPABASE_URL','')
    local.update(h.lower() for h in HOST.findall(current))
    placeholders=len([h for h in refs|local if h.split('.')[0] and set(h.split('.')[0])=={'x'}])
    refs={h for h in refs if set(h.split('.')[0])!={'x'}}
    local={h for h in local if set(h.split('.')[0])!={'x'}}
    hosts=[]
    for host in sorted(refs|local):
        try:
            addresses=sorted({r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
            hosts.append({'hostname':host,'resolves':True,'addresses':addresses})
        except socket.gaierror as exc:
            hosts.append({'hostname':host,'resolves':False,'dns_error':exc.errno})
    return {'checked_at':datetime.now(timezone.utc).isoformat(),'placeholder_hosts_ignored':placeholders,'source_revisions':len(commits),'local_configuration_files_inspected':inspected,
            'hosts':hosts,'credential_configured':bool(os.environ.get('TRACKER_SUPABASE_SERVICE_KEY')),'authenticated_access_attempted':False,
            'conclusion':'DNS failure establishes endpoint unavailability, not deletion. Recovery requires project-owner dashboard confirmation or an authorised backup. Browser-cache recovery remains partial until reconciled.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repository',required=True);parser.add_argument('--config',action='append',default=[]);parser.add_argument('--summary',required=True)
    args=parser.parse_args();data=diagnose(args.repository,args.config)
    fd=os.open(args.summary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as output:json.dump(data,output,indent=2)
    print(json.dumps(data))

if __name__=='__main__':main()
