"""Compile same-folder C modules declared in a five-zone PULSE netlist."""
import argparse, hashlib, json, os, pathlib, re, subprocess, sys

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def declarations(path):
    section = ''; language = None; current = None; programs = {}; lines = path.read_text(encoding='utf-8-sig').splitlines()
    for raw in lines:
        line = raw.strip()
        if line.startswith('```'):
            language = None if language else line[3:].strip().lower()
            continue
        if language is None:
            if line.startswith('## '): section = line[3:].strip().upper()
            continue
        if section not in ('CODE', '代码域'): continue
        if language == 'c':
            if current is None: raise ValueError('inline C has no PROGRAM')
            programs[current]['inline_source'] += raw + '\n'
        elif language == 'pulse' and line and not line.startswith('*'):
            match = re.fullmatch(r'PROGRAM\s+([A-Za-z_][A-Za-z0-9_]*)\s+(SOURCE=INLINE|SOURCES=(\[.*\]))', line, re.I)
            if not match: raise ValueError('unsupported PROGRAM declaration: ' + line)
            current = match[1]
            if current in programs: raise ValueError('duplicate program ' + current)
            sources = json.loads(match[3]) if match[3] else []
            if match[3] and not sources: raise ValueError('empty source list')
            programs[current] = {'sources': sources, 'inline_source': ''}
    return programs

def main():
    p=argparse.ArgumentParser(); p.add_argument('netlist',type=pathlib.Path)
    p.add_argument('--cc',default=r'D:\codex\tool\pulse-win\w64devkit\bin\gcc.exe')
    a=p.parse_args(); path=a.netlist.resolve(); root=pathlib.Path(__file__).resolve().parents[1]
    destination=path.parent/'.pulse_modules'; destination.mkdir(exist_ok=True)
    sdk=root/'include'; env=os.environ.copy(); env['PATH']=str(pathlib.Path(a.cc).parent)+os.pathsep+env.get('PATH','')
    compiler=subprocess.check_output([a.cc,'--version'],text=True,env=env).splitlines()[0]
    for name,program in declarations(path).items():
        source_paths=[]
        for filename in program['sources']:
            source=pathlib.Path(filename)
            if source.name!=filename or source.suffix!='.c': raise ValueError('same-folder .c names required')
            source_paths.append(path.parent/source)
        if not source_paths:
            if not program['inline_source']: raise ValueError('empty inline code')
            source=destination/(name+'_inline.c'); source.write_text(program['inline_source'],encoding='utf-8'); source_paths.append(source)
        binary=destination/(name+'.dll')
        command=[a.cc,'-std=c11','-O2','-shared','-static-libgcc','-ffp-contract=off','-fno-fast-math',
            '-I',str(sdk),'-I',str(path.parent),*[str(x) for x in source_paths],'-o',str(binary),'-lm']
        subprocess.run(command,env=env,check=True)
        dependencies={sdk/'pulse/software.h',*source_paths}
        # GCC -MM supplies actual local header dependencies, not a guessed list.
        for source in source_paths:
            dep=destination/(name+'_deps.d')
            subprocess.run([a.cc,'-MM','-MT','module','-MF',str(dep),'-I',str(sdk),'-I',str(path.parent),str(source)],env=env,check=True)
            text=dep.read_text().replace('\\\n',' ')
            body=text.split(':',1)[1]
            for token in re.findall(r'(?:\\.|[^\s])+',body):
                token=token.replace('\\ ', ' ').replace('\\#','#')
                candidate=pathlib.Path(token)
                if candidate.is_file(): dependencies.add(candidate.resolve())
        abi=int(re.search(r'#define PULSE_SOFTWARE_ABI (\d+)u',(sdk/'pulse/software.h').read_text()).group(1))
        manifest={'abi':abi,'compiler':compiler,'command':command,'binary_sha256':sha(binary),**program,
          'dependencies':[{'path':str(x.resolve()),'sha256':sha(x)} for x in sorted(dependencies)]}
        pathlib.Path(str(binary)+'.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(name,manifest['binary_sha256'],flush=True)
    return 0
if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,subprocess.CalledProcessError) as e: print(str(e),file=sys.stderr);sys.exit(1)
