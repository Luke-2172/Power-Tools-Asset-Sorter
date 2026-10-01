"""Shared defensive filesystem/report helpers. No command shells or network access."""
from pathlib import Path
import csv, os, shutil, stat, tempfile

class Cancelled(Exception): pass

def is_link(path):
    try:
        s=Path(path).lstat()
        return stat.S_ISLNK(s.st_mode) or bool(getattr(s,'st_file_attributes',0)&0x400)
    except FileNotFoundError: return False

def reject_links(path):
    path=Path(os.path.abspath(path))
    for p in [path,*path.parents]:
        if is_link(p): raise ValueError('Symbolic links/junctions are not processed: '+str(p))

def scan(root,suffix,recursive=True,stop=None):
    root=Path(root); reject_links(root); files=[]
    def scan_error(exc): raise exc
    for directory,dirs,names in os.walk(root,followlinks=False,onerror=scan_error):
        if stop is not None and stop.is_set(): raise Cancelled('Scan cancelled')
        for name in dirs:
            if is_link(Path(directory)/name): raise ValueError('Linked folder found; remove it from the input selection: '+str(Path(directory)/name))
        for name in names:
            p=Path(directory)/name
            if p.suffix.lower()==suffix:
                reject_links(p)
                if not p.is_file(): continue
                files.append(p)
        if not recursive: dirs[:]=[]
    return sorted(files,key=lambda p:str(p).casefold())

def roots(source,output):
    source,output=Path(source).absolute(),Path(output).absolute()
    reject_links(source); reject_links(output)
    source,output=source.resolve(),output.resolve()
    if not source.is_dir(): raise ValueError('Choose an existing input folder')
    if source==output or source in output.parents or output in source.parents:
        raise ValueError('Select separate input and output folders; neither may contain the other')
    return source,output

def atomic_publish(temp,dest):
    temp,dest=Path(temp),Path(dest); reject_links(dest)
    if os.name=='nt':
        # Windows rename is atomic and refuses an existing destination.
        os.rename(temp,dest)
    else:
        os.link(temp,dest,follow_symlinks=False); temp.unlink()

def atomic_write(dest,data=None,source=None):
    dest=Path(dest); reject_links(dest); dest.parent.mkdir(parents=True,exist_ok=True); reject_links(dest)
    if source is not None: reject_links(source)
    size=len(data) if data is not None else Path(source).stat().st_size
    if shutil.disk_usage(dest.parent).free < size+16*1024*1024: raise OSError('Insufficient free disk space')
    fd,name=tempfile.mkstemp(prefix='.fnv-',suffix='.partial',dir=dest.parent); tmp=Path(name)
    try:
        with os.fdopen(fd,'wb') as out:
            if data is not None: out.write(data)
            else:
                with Path(source).open('rb') as inp: shutil.copyfileobj(inp,out,1024*1024)
            out.flush(); os.fsync(out.fileno())
        atomic_publish(tmp,dest)
    finally: tmp.unlink(missing_ok=True)

def cell(value):
    if isinstance(value,str) and (value[:1] in ('\t','\r','\n') or value.lstrip().startswith(('=','+','-','@'))): return "'"+value
    return value

class SafeCSV:
    def __init__(self,file): self.writer=csv.writer(file)
    def writerow(self,row): self.writer.writerow([cell(x) for x in row])
