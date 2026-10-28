#!/usr/bin/env python3
"""Independent high-precision replay along recorded engineering event times.

This validates numerical propagation, not all-history/event-order certification.
Requires optional mpmath; the native product has no Python dependency.
"""
import argparse,json,pathlib,time
from fractions import Fraction
import mpmath as mp
def canonical(text):
    _,seconds,tick,subtick=text.split(':')
    return mp.mpf(seconds)+mp.mpf(int(tick,16))/mp.mpf(2)**64+mp.mpf(int(subtick,16))/mp.mpf(2)**128
def main():
    parser=argparse.ArgumentParser();parser.add_argument('trace',type=pathlib.Path);parser.add_argument('output',type=pathlib.Path)
    args=parser.parse_args();start=time.perf_counter();mp.mp.dps=80
    trace=json.loads(args.trace.read_text());segments=trace['segments'];n=len(segments[0]['physical'])
    state=mp.matrix(segments[0]['physical']);maximum=[mp.mpf(0)]*n;scales=[mp.mpf(0)]*n
    roots={e['time_canonical']:e for e in trace['events'] if e.get('kind')=='ROOT'}
    times=[];factor_cache={}
    for index in range(len(segments)-1):
        before,after=segments[index:index+2];dt=canonical(after['at'])-canonical(before['at'])
        operator=mp.matrix(before['matrix'])
        factored=False
        if before['generator']:
            lift=mp.matrix(before['lift']);generator=mp.matrix(before['generator']);reduce=mp.matrix(before['reduce'])
            operator=lift*generator*reduce
            cache_key=json.dumps([before['lift'],before['reduce']],separators=(',',':'))
            if cache_key not in factor_cache:
                s,r=before['lift'],before['reduce'];size=len(r)
                factor_cache[cache_key]=all(sum((Fraction(r[i][k])*Fraction(s[k][j]) for k in range(len(s))),Fraction(0))==int(i==j) for i in range(size) for j in range(size))
            factored=factor_cache[cache_key]
        if dt:
            if factored:
                reduced=reduce*state
                state+=lift*(mp.expm(generator*dt)*reduced-reduced)
            else:state=mp.expm(operator*dt)*state
        for j,actual in enumerate(after['physical']):
            maximum[j]=max(maximum[j],abs(state[j]-mp.mpf(actual)))
            scales[j]=max(scales[j],abs(state[j]),abs(mp.mpf(actual)))
        event=roots.get(after['at'])
        if event and dt and event.get('predicted_events'):
            part=event['predicted_events'][0]['part']
            matching=[g for g in before['guards'] if g['part']==part]
            if matching:
                row=mp.matrix([matching[0]['row']]);value=(row*state)[0];slope=(row*operator*state)[0]
                times.append(abs(value/slope) if slope else mp.inf)
        if (index+1)%100==0:print('replayed',index+1,'segments',flush=True)
    relative=[maximum[j]/max(mp.mpf('1e-30'),scales[j]) for j in range(n-1)]
    result={'native_source_sha256':trace['report']['source_sha256'],'method':'mpmath 80-digit matrix exponential; exact binary64 compiled factors; canonical T128 durations',
        'scope':'independent numerical propagation replay at recorded engineering switching times; no independent exact-event-order or global enclosure proof; no PLECS calibration',
        'segments_checked':len(segments)-1,'roots_checked':len(times),'native_status':trace['report']['status'],
        'max_absolute_error_per_physical_coordinate':[mp.nstr(v,20) for v in maximum[:-1]],
        'max_amplitude_relative_error_per_physical_coordinate':[mp.nstr(v,20) for v in relative],
        'max_root_clock_displacement_estimate_s':mp.nstr(max(times,default=mp.mpf(0)),20),
        'T_atom':trace['report']['T_atom'],'relative_propagation_test_tolerance':2e-6,
        'propagation_test_passed':all(v<mp.mpf('2e-6') for v in relative),'wall_seconds':time.perf_counter()-start}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
    return 0 if result['propagation_test_passed'] else 1
if __name__=='__main__':raise SystemExit(main())
