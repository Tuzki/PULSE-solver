#!/usr/bin/env python3
"""Independent C ABI/CLI/NPZ integration oracle; test-time Python only."""
import ctypes as C
import os
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILD=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'build'
LIB=BUILD/({'Darwin':'libpulse_solver.dylib','Linux':'libpulse_solver.so','Windows':'pulse_solver.dll'}[platform.system()])
lib=C.CDLL(str(LIB));lib.pulse_abi_version.restype=C.c_uint32
lib.pulse_compile_markdown.argtypes=[C.c_char_p,C.c_size_t,C.POINTER(C.c_void_p)];lib.pulse_compile_markdown.restype=C.c_int
lib.pulse_simulate.argtypes=[C.c_void_p,C.c_void_p,C.c_char_p];lib.pulse_simulate.restype=C.c_int
lib.pulse_get_last_error.argtypes=[C.c_void_p];lib.pulse_get_last_error.restype=C.c_char_p
lib.pulse_report_json.argtypes=[C.c_void_p];lib.pulse_report_json.restype=C.c_char_p
lib.pulse_release_model.argtypes=[C.c_void_p]
class Options(C.Structure):
 _fields_=[('struct_size',C.c_uint32),('abi_version',C.c_uint32),('flags',C.c_uint32),('t_end',C.c_double),('save_dt',C.c_double),('channels',C.c_char_p),('atom_exponent',C.c_int32)]
cases=[]
def check(id,fn):
 try: fn();cases.append({'id':id,'status':'PASS','execution':'EXECUTED'})
 except Exception as e:cases.append({'id':id,'status':'FAIL','execution':'EXECUTED','error':str(e)})
def must(x):
 assert x
text=(ROOT/'tests/fixtures/N05.md').read_bytes();handle=C.c_void_p()
check('ABI_version',lambda:must(lib.pulse_abi_version()==2))
check('ABI_compile',lambda:must(lib.pulse_compile_markdown(text,len(text),C.byref(handle))==0))
def run(name,flags=0,dt=.1,channels=None):
 options=Options(C.sizeof(Options),2,flags,1.,dt,channels,9)
 path=ROOT/'reports/interfaces'/name
 code=lib.pulse_simulate(handle,C.byref(options),str(path).encode())
 assert code==0,lib.pulse_get_last_error(handle).decode()
 result=json.loads(lib.pulse_report_json(handle));assert result['status']=='COMPLETED'
 assert result['parse_seconds']>=0 and result['compile_seconds']>=0
 assert len(result['source_sha256'])==64 and all(c in '0123456789abcdef' for c in result['source_sha256'])
 assert result['model_version']['encoding']=='canonical pulse-netlist-1.1'
 assert result['model_version']['canonical']
 assert result['model_version']['deadline_inputs']
 return path,result
check('ABI_run_default',lambda:run('api_default'))
check('ABI_run_override',lambda:must(run('api_override',3,.2)[1]['effective_SAVE_DT']==.2))
check('ABI_empty_channels',lambda:must(run('api_empty',4,.1,b'')[1]['analog_channels']==[]))
def cli():
 cmd=[str(BUILD/'pulse-solver'),str(ROOT/'tests/fixtures/N05.md'),'--save-dt','.2','--out',str(ROOT/'reports/interfaces/cli_override')]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
check('CLI_run_override',cli)
def compare():
 a=np.load(ROOT/'reports/interfaces/api_override/out.pewave.npz',allow_pickle=False)
 b=np.load(ROOT/'reports/interfaces/cli_override/out.pewave.npz',allow_pickle=False)
 for key in ['time','analog','digital']:assert np.array_equal(a[key],b[key]),key
 ma=json.loads(bytes(a['metadata_json']).decode());mb=json.loads(bytes(b['metadata_json']).decode())
 for key in ['effective_SAVE_DT','T_atom','analog_channels','digital_channels','status']:assert ma[key]==mb[key]
 assert a['time'].dtype==np.dtype('float64') and a['analog'].dtype==np.dtype('float32') and a['digital'].dtype==np.dtype('uint8')
check('A06_CLI_API_equal_config_and_NPZ',compare)
def reuse():
 path,r=run('api_reuse');assert r['transactions']==5
 a=np.load(path/'out.pewave.npz',allow_pickle=False)
 b=np.load(ROOT/'reports/interfaces/api_default/out.pewave.npz',allow_pickle=False)
 assert np.array_equal(a['analog'],b['analog'])
check('ABI_reuse_isolated_state',reuse)
def malformed():
 bad=Options(1,2,0,1.,.1,None,9);assert lib.pulse_simulate(handle,C.byref(bad),b'out')==1
 assert json.loads(lib.pulse_get_last_error(handle))['subcode']=='ABI_VERSION'
 assert json.loads(lib.pulse_report_json(handle))['status']=='STOPPED_ERROR'
check('ABI_bad_struct',malformed)
def bad_model():
 h=C.c_void_p();data=(ROOT/'tests/fixtures/A07_trig_reg.md').read_bytes()
 assert lib.pulse_compile_markdown(data,len(data),C.byref(h))==1
 try:assert json.loads(lib.pulse_get_last_error(h))['subcode']=='TYPE_CONFLICT'
 finally:lib.pulse_release_model(h)
check('ABI_bad_model_diagnostic_and_release',bad_model)
class Request(C.Structure):
 _fields_=[('struct_size',C.c_uint32),('abi_version',C.c_uint32),('netlist_file',C.c_char_p),('t_end',C.c_double),('save_dt',C.c_double),('channels',C.c_char_p)]
lib.pulse_create.argtypes=[C.POINTER(C.c_void_p)];lib.pulse_create.restype=C.c_int
lib.pulse_run.argtypes=[C.c_void_p,C.POINTER(Request)];lib.pulse_run.restype=C.c_int
lib.pulse_destroy.argtypes=[C.c_void_p]
def abi1():
 h=C.c_void_p();assert lib.pulse_create(C.byref(h))==0
 old=os.getcwd();dest=ROOT/'reports/interfaces/abi1';dest.mkdir(parents=True,exist_ok=True)
 try:
  os.chdir(dest);request=Request(C.sizeof(Request),1,str(ROOT/'tests/fixtures/N05.md').encode(),1.,.1,b'*')
  assert lib.pulse_run(h,C.byref(request))==0,lib.pulse_get_last_error(h).decode()
  assert json.loads(lib.pulse_report_json(h))['status']=='COMPLETED'
 finally:os.chdir(old);lib.pulse_destroy(h)
check('ABI1_compatibility',abi1)
def provenance():
 data=(ROOT/'tests/fixtures/TIME_decimal_collision.md').read_bytes()
 data=data.replace(b'EVENT_B B MODE=AT AT=.10000000000000001\n',b'')
 reports=[]
 for i,at in enumerate([b'.1',b'.10000000000000001']):
  buf=data.replace(b'AT=.1\n',b'AT={AT_BASE}\n')
  buf=buf.replace(b'## Parameters\n```pulse\n',b'## Parameters\n```pulse\n.PARAM AT_BASE='+at+b'\n')
  h=C.c_void_p()
  assert lib.pulse_compile_markdown(buf,len(buf),C.byref(h))==0
  try:
   assert lib.pulse_simulate(h,None,str(ROOT/f'reports/interfaces/provenance_{i}').encode())==0
   reports.append(json.loads(lib.pulse_report_json(h)))
  finally:lib.pulse_release_model(h)
 assert reports[0]['model_version']['canonical']==reports[1]['model_version']['canonical']
 assert reports[0]['model_version']!=reports[1]['model_version']
 assert reports[0]['source_sha256']==reports[1]['source_sha256']
check('ABI_model_identity_includes_original_time_inputs',provenance)
lib.pulse_release_model(handle)
report={'binary_sha256':hashlib.sha256(LIB.read_bytes()).hexdigest(),'cases':cases,'failures':sum(c['status']=='FAIL' for c in cases)}
(ROOT/'reports/interface_ledger.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
sys.exit(bool(report['failures']))
