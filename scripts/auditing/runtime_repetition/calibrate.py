#!/usr/bin/env python3
import json,os,subprocess
from pathlib import Path
root=Path('/root/cd-repeat-audit-20261104')
for version in ['C','D']:
 v=root/version
 command=['g++','-std=c++20','-O2','-fPIC','-shared',str(Path(__file__).parent/'counters.cpp'),'-I'+str(v),'-I'+str(v/'source/third_party'),'-ldl','-o',str(v/'libcounts.so')]
 subprocess.run(command,check=True)
 source=v/'self-test.cpp'
 source.write_text('''#include "audit.hpp"
#include <cstdlib>
int main(){audit::Scope scope(audit::cli);
void *p=malloc(17),*q=calloc(3,7);p=realloc(p,33);
free(p);free(q);free(nullptr);
unsigned long long key=42;
pa_blob(audit::bind_input_A,&key,sizeof(key),nullptr,0,nullptr,0);
pa_blob(audit::bind_input_A,&key,sizeof(key),nullptr,0,nullptr,0);
++key;pa_blob(audit::bind_input_A,&key,sizeof(key),nullptr,0,nullptr,0);
}''')
 subprocess.run(['g++','-std=c++20','-O0','-fno-builtin',str(source),'-I'+str(v),'-L'+str(v),'-lcounts','-Wl,-rpath,'+str(v),'-o',str(v/'self-test')],check=True)
 env=os.environ.copy();env.update(LD_PRELOAD=str(v/'libcounts.so'),PULSE_COUNT_OUTPUT=str(v/'self-test.json'))
 subprocess.run([str(v/'self-test')],env=env,check=True)
 result=json.loads((v/'self-test.json').read_text())
 row=next(x for x in result['paths'] if x['path']=='outside_scopes/cli')
 assert [x['calls'] for x in row['apis']]==[1,1,1],row
 assert [x['bytes'] for x in row['apis']]==[17,21,33],row
 assert row['free_calls']==3 and row['free_null']==1,row
 assert result['keys']['bind_input_A']['repeats']==1
 assert result['keys']['bind_input_A']['distinct']==2
 assert result['threads']==1 and result['overflow_errors']==0
 print(version,'counter calibration passed',flush=True)
