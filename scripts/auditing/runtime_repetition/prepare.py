#!/usr/bin/env python3
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
from instrument import Overlay
from refine_paths import refine

def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--version',choices=['C','D'],required=True);a=p.parse_args()
 baseline=Path('/root/pulse-stage-'+a.version.lower()+'-2026110'+('3' if a.version=='C' else '4'))
 root=a.work/a.version;source=root/'source';root.mkdir(parents=True,exist_ok=True)
 for folder in ['src','include','apps','third_party','scripts','tests','examples','benchmarks']:
  shutil.copytree(baseline/folder,source/folder,dirs_exist_ok=True)
 shutil.copyfile(baseline/'CMakeLists.txt',source/'CMakeLists.txt')
 before={}
 for folder in ['src','include','apps']:
  for f in sorted((source/folder).rglob('*')):
   if f.is_file():before[f.relative_to(source).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
 before['CMakeLists.txt']=hashlib.sha256((source/'CMakeLists.txt').read_bytes()).hexdigest()
 (root/'base-source-hashes.json').write_text(json.dumps(before,indent=2)+'\n')
 overlay=Overlay(source).apply(a.version)
 (root/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
 (root/'refined-paths.json').write_text(json.dumps(refine(source),indent=2)+'\n')
 commands=[['g++','-std=c++20','-O2','-fPIC','-shared',str(Path(__file__).parent/'counters.cpp'),'-I'+str(root),'-I'+str(source/'third_party'),'-ldl','-o',str(root/'libcounts.so')],
  ['cmake','-S',str(source),'-B',str(root/'build'),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DBUILD_TESTING=OFF'],
  ['cmake','--build',str(root/'build'),'--target','pulse-solver','--parallel','2']]
 (root/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 for name,command in zip(['counter-build','configure','build'],commands):
  print(a.version,name,flush=True)
  with (root/(name+'.log')).open('w') as f:r=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
  if r.returncode:print((root/(name+'.log')).read_text()[-6000:]);return r.returncode
 print(a.version,'count build ready',flush=True);return 0
if __name__=='__main__':sys.exit(main())
