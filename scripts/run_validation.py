#!/usr/bin/env python3
"""Native V1.2pre execution ledger; Python is a test harness, never the solver."""
import argparse, hashlib, json, pathlib, platform, subprocess, time

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1])
    parser.add_argument('--suite',choices=['compatibility','historical','pf','all'],default='all')
    parser.add_argument('--max-transactions',type=int,default=0,help='Explicit per-case cap; 0 means unlimited')
    parser.add_argument('--out',type=pathlib.Path,help='Separate output directory; preserves earlier validation results')
    parser.add_argument('--build-dir',type=pathlib.Path,help='Native CMake build directory')
    args=parser.parse_args();root=args.project.resolve()
    build=args.build_dir.resolve() if args.build_dir else root/('build' if platform.system() == 'Windows' else 'build-linux')
    binary=build/('pulse-solver.exe' if platform.system() == 'Windows' else 'pulse-solver')
    destination=args.out.resolve() if args.out else root/'reports/validation';destination.mkdir(parents=True,exist_ok=True)
    ledger={'platform':platform.platform(),'machine':platform.machine(),'suite':args.suite,'checks':[],'cases':[]}
    def save(): (destination/f'{args.suite}_ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
    if args.suite in ('compatibility','all'):
        command=['ctest','--test-dir',str(build),'--output-on-failure']
        start=time.perf_counter();result=subprocess.run(command,text=True,capture_output=True,timeout=120)
        (destination/'ctest.log').write_text(result.stdout+result.stderr)
        ledger['checks'].append({'name':'ctest','command':command,'returncode':result.returncode,'wall_seconds':time.perf_counter()-start})
        print('CTEST',result.returncode,flush=True);save()
    paths=[]
    if args.suite in ('historical','all'):
        paths+=sorted((root/'tests/regression').glob('*.md'))
    if args.suite in ('pf','all'):
        names=['buck_ccm_pf','buck_dcm_pf','boost_ccm_pf','boost_dcm_pf','BuckLong_pf','rectifier_pf','llc_pf','llc_100cycles_pf']
        paths+=[root/'tests/cr002/fixtures'/f'{name}.md' for name in names]
    for fixture in paths:
        out=destination/fixture.stem
        command=[str(binary),str(fixture),'--out',str(out),'--max-transactions',str(args.max_transactions)]
        entry={'case':fixture.stem,'command':command,'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
               'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
        start=time.perf_counter()
        try:
            result=subprocess.run(command,text=True,capture_output=True,timeout=120)
            entry['returncode']=result.returncode
            out.mkdir(parents=True,exist_ok=True)
            (out/'stdout.json').write_text(result.stdout);(out/'stderr.txt').write_text(result.stderr)
            report=out/'simulation_report.json'
            if report.exists():
                r=json.loads(report.read_text())
                for key in ['status','source_sha256','simulated_seconds','effective_T_END','T_atom','transactions','mode_compilations','root_queries','root_failures','run_seconds','diagnostic']:
                    entry[key]=r.get(key)
            else:entry['status']='NO_RUN_REPORT'
        except subprocess.TimeoutExpired:
            entry['status']='TIMEOUT';entry['returncode']=None
        entry['wall_seconds']=time.perf_counter()-start
        ledger['cases'].append(entry);save()
        print(entry['case'],entry['status'],entry.get('simulated_seconds'),round(entry['wall_seconds'],3),entry.get('diagnostic'),flush=True)
    return 0 if all(x.get('returncode')==0 for x in ledger['checks']+ledger['cases']) else 1

if __name__=='__main__':raise SystemExit(main())
