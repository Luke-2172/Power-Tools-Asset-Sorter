"""Build a portable Windows release from this source archive. No downloads."""
from pathlib import Path
import argparse,py_compile,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser()
p.add_argument('--runtime',required=True,help='runtime folder from the matching portable release')
p.add_argument('--zig',default='zig',help='Zig 0.13.0 executable')
p.add_argument('--output',default=str(ROOT/'dist'))
a=p.parse_args()
if sys.version_info[:2]!=(3,13): raise SystemExit('Use CPython 3.13 to match the bundled Windows runtime.')
title='FNV Asset Sorter'
out=Path(a.output).resolve()
if out.exists(): raise SystemExit('Choose a new output folder; this builder never overwrites a previous build.')
rt=Path(a.runtime).resolve()
if not (rt/'pythonw.exe').is_file(): raise SystemExit('The runtime folder must contain pythonw.exe.')
zig=str(Path(shutil.which(a.zig) or a.zig).resolve())
out.mkdir(parents=True);shutil.copytree(rt,out/'runtime');(out/'app').mkdir()
for module in (ROOT/'app').glob('*.py'):
 py_compile.compile(str(module),cfile=str(out/'app'/(module.stem+'.pyc')),dfile=module.name,doraise=True,invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
work=ROOT/'source'
subprocess.run([zig,'rc','/fo','app.res','app.rc'],cwd=work,check=True)
subprocess.run([zig,'cc','-target','x86_64-windows-gnu','-O2','-municode','launcher.c','app.res','-o',str(out/(title+'.exe')),'-luser32','-Wl,--subsystem,windows','-Wl,--dynamicbase','-Wl,--nxcompat'],cwd=work,check=True)
(work/'app.res').unlink(missing_ok=True)
for debug in out.glob('*.pdb'): debug.unlink()
print('Built:',out)
