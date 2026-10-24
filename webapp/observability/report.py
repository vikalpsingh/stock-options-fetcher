"""Offline usage reports. Zero observations never prove dead code."""
import argparse,csv,json
from pathlib import Path
from .inventory import analyse,write_csv

def report(source,output,root=Path('.')):
    output.mkdir(parents=True,exist_ok=True)
    data=analyse(root);counts={};modules={};bad=0
    for path in source.glob('*.jsonl'):
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                e=json.loads(line)
                if e.get('event')!='FUNCTION_USED':continue
                key=e['identifier'];row=counts.setdefault(key,dict(identifier=key,count=0,success=0,failure=0,last_seen='',sampled=False))
                row['count']+=int(e.get('count',1));row['success']+=e.get('status')=='SUCCESS';row['failure']+=e.get('status')=='FAILURE'
                row['last_seen']=max(row['last_seen'],e.get('timestamp',''));row['sampled']|=e.get('sample_rate',1)<1
                modules[e['module']]=modules.get(e['module'],0)+int(e.get('count',1))
            except (ValueError,KeyError,TypeError):bad+=1
    write_csv(output/'function_usage_report.csv',list(counts.values()))
    write_csv(output/'module_usage_report.csv',[dict(module=k,count=v) for k,v in modules.items()])
    candidates=[dict(identifier=f['identifier'],classification='PROTECTED' if f['classification']=='SAFETY CRITICAL' else 'UNOBSERVED / UNKNOWN',confidence='INSUFFICIENT EVIDENCE',possible_calls=f['calls']) for f in data['functions'] if f['identifier'] not in counts and f['classification']!='TEST ONLY']
    write_csv(output/'possible_dead_code.csv',candidates)
    write_csv(output/'unused_imports.csv',[r for r in data['imports'] if r['possibly_unused']])
    write_csv(output/'refactoring_priority.csv',sorted([m for m in data['modules'] if not m['test_only']],key=lambda m:m['bytes'],reverse=True))
    (output/'usage_summary.md').write_text(f'# Usage summary\nObserved {len(counts)} functions in {len(modules)} modules; {bad} malformed records ignored.\nCounts are observations, not sampling-adjusted totals. MODULE_LOADED is recorded lazily at first instrumented call. Uninstrumented functions have unknown coverage. Rotations/queue drops/process exits can lose events.\nRequire 30–60 days covering market, expiry, recovery and scheduler cycles; rare paths need longer. No HIGH CONFIDENCE removal candidates assigned automatically. Review static callers, registrations and tests before proposing archival; explicit approval required.\n',encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report(args.input,args.output)
