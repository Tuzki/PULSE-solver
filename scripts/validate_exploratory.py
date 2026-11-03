#!/usr/bin/env python3
"""Exploratory engineering comparison for PULSE Stage C vs D 50 ms A010.

This is intentionally a LOWER bar than Stage C's bit-for-bit acceptance.
It requires complete event-driven simulations, valid PEVT, matching event
sequence and sample time grid, and bounded waveform differences.  It does NOT
certify bit-for-bit numerical equivalence, universal model correctness, or
identity of archive bytes.
"""
from __future__ import annotations
import argparse, importlib.util, json, pathlib, sys


def load_reader(path):
    spec=importlib.util.spec_from_file_location('stage_c_pevt_reader',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def compare(croot, cdir, ddir, replay_c, replay_d, allow_event_mismatch=False):
    import numpy as np
    rc=json.loads((cdir/'simulation_report.json').read_text())
    rd=json.loads((ddir/'simulation_report.json').read_text())
    core=['simulated_seconds','effective_SAVE_DT','effective_T_END','analog_channels','digital_channels']
    metadata_differences={k:[rc.get(k),rd.get(k)] for k in core if rc.get(k)!=rd.get(k)}
    reader=load_reader(croot/'scripts/read_pevt.py')
    c=reader.read(cdir/'out.pevt'); d=reader.read(ddir/'out.pevt')
    cs=reader.summary(c);ds=reader.summary(d)
    ce=c['events'];de=d['events']
    counts={k:{'C':len(c[k]),'D':len(d[k])} for k in ('definitions','matrices','values','instances','states','events','flows','diagnostics')}
    event_exact_len=len(ce)==len(de)
    event_time_differences=sum(a['time']!=b['time'] for a,b in zip(ce,de)) + abs(len(ce)-len(de))
    def time_seconds(event):
        whole,tick,subtick=event['time']
        return whole + tick/(2**64) + subtick/(2**128)
    max_event_time_delta=max((abs(time_seconds(a)-time_seconds(b)) for a,b in zip(ce,de)),default=0.0)
    event_kind_differences=sum(a['kind']!=b['kind'] for a,b in zip(ce,de)) + abs(len(ce)-len(de))
    pevt_valid=(cs['status']=='COMPLETED' and ds['status']=='COMPLETED'
        and cs['last_time_T128']==ds['last_time_T128'])
    def npz_contents(path):
        with np.load(path,allow_pickle=False) as f:return {k:np.asarray(f[k]) for k in f.files}
    x=npz_contents(replay_c/'out.pewave.npz');y=npz_contents(replay_d/'out.pewave.npz')
    channel_rows=[];all_good=True
    if set(x)!=set(y):all_good=False
    for k in sorted(set(x)&set(y)):
        if k=='metadata_json':continue
        a,b=x[k],y[k]
        if a.shape!=b.shape:
            channel_rows.append({'name':k,'shape_C':list(a.shape),'shape_D':list(b.shape),'pass':False})
            all_good=False;continue
        if k=='time':
            ok=bool(np.array_equal(a,b))
            channel_rows.append({'name':k,'pass':ok,'exact_time_grid':ok})
            all_good &=ok;continue
        if a.dtype.kind in 'iu' and b.dtype.kind in 'iu':
            differing=int(np.count_nonzero(a!=b))
            frac=differing/max(1,a.size)
            ok=frac <=1e-4
            channel_rows.append({'name':k,'type':'digital','n':int(a.size),'mismatches':differing,
                                 'mismatch_fraction':frac,'pass':bool(ok)})
        else:
            diff=np.abs(a.astype(np.float64)-b.astype(np.float64))
            scale=max(1.,float(np.max(np.abs(a.astype(np.float64))))) if a.size else 1.
            tol=1e-6+1e-5*scale
            bad=int(np.count_nonzero(diff>tol))
            bad_fraction=bad/max(1,a.size)
            rms=float(np.sqrt(np.mean(diff*diff))) if a.size else 0.
            ok=(bad_fraction<=1e-4 and rms/scale<=1e-5)
            channel_rows.append({'name':k,'type':'analog','n':int(a.size),'max_absolute':float(np.max(diff)) if a.size else 0.,
                                 'rms':rms,'scale':scale,'rms_normalized':rms/scale,
                                 'atol_with_scale':tol,'above_threshold':bad,
                                 'above_threshold_fraction':bad_fraction,'pass':bool(ok)})
        all_good &=bool(ok)
    event_ok=event_exact_len and event_kind_differences==0 and max_event_time_delta<=1e-10
    if allow_event_mismatch:
        event_ok=event_exact_len and event_kind_differences==0
    ok=not metadata_differences and pevt_valid and event_ok and all_good
    return {'status':'PASS_EXPLORATORY_NOT_BITWISE' if ok else 'FAIL_EXPLORATORY',
        'simulation_metadata_differences':metadata_differences,'valid_pevt':pevt_valid,
        'event_sequence':{'C_count':len(ce),'D_count':len(de),'kind_differences':event_kind_differences,
                          'time_differences':event_time_differences,'max_time_delta_seconds':max_event_time_delta,
                          'time_tolerance_seconds':1e-10,'event_pass':event_ok},
        'pevt_record_counts':counts,'channels':channel_rows,'waveform_pass':bool(all_good),
        'tolerances':{'analog_norm_rms_max':1e-5,'analog_bad_fraction_max':1e-4,
                      'analog_sample_threshold':'1e-6+1e-5*max(1,max(abs(Stage C channel)))',
                      'digital_mismatch_fraction_max':1e-4},
        'disclaimer':'Exploratory comparison only; strict Stage C acceptance remains a separate gate.'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--croot',type=pathlib.Path,required=True)
    for arg in ('cdir','ddir','replay-c','replay-d','out'):
        ap.add_argument('--'+arg,type=pathlib.Path,required=True)
    a=ap.parse_args();res=compare(a.croot,a.cdir,a.ddir,a.replay_c,a.replay_d)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(res,indent=2)+'\n')
    print(json.dumps({'status':res['status'],'event_sequence':res['event_sequence'],
                      'waveform_pass':res['waveform_pass']},indent=2))
    return 0 if res['status'].startswith('PASS') else 2
if __name__=='__main__':sys.exit(main())
