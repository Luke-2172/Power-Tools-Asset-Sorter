"""Read-only source audit and copy-based Fallout New Vegas asset sorter. Python 3.9+."""
import argparse, collections, csv, datetime, hashlib, os, re, shutil, struct, sys, traceback, zlib
from pathlib import Path


EXT = re.compile(rb'\.(?:nif|dds|tga|bmp|kf|egm|egt|tri|wav|ogg|mp3|lip|bik)', re.I)
OFFICIAL = re.compile(r'^(?:Fallout - (?:Meshes|Textures\d*)|(?:DeadMoney|HonestHearts|OldWorldBlues|LonesomeRoad|GunRunnersArsenal|CaravanPack|ClassicPack|MercenaryPack|TribalPack)(?: - (?:Meshes|Textures\d*))?)\.bsa$', re.I)

LIMIT=256*1024*1024

def norm(s):
    s=s.strip().replace('/', '\\').lower()
    # Reject unsafe paths, including Windows device names and ADS.
    if not s or ':' in s or s.startswith('\\') or any(c<32 for c in map(ord,s)): return None
    parts=s.split('\\')
    if any(p in ('','.', '..') or p.endswith((' ','.')) or p.split('.')[0] in {'con','prn','aux','nul',*[f'com{i}' for i in range(1,10)],*[f'lpt{i}' for i in range(1,10)]} for p in parts): return None
    if not s.startswith(('meshes\\','textures\\','sound\\','music\\','video\\')):
        ext=Path(s).suffix
        prefix='textures' if ext in ('.dds','.tga','.bmp') else 'sound' if ext in ('.wav','.ogg','.mp3','.lip') else 'video' if ext=='.bik' else 'meshes'
        s=prefix+'\\'+s
    return s

def inflate(data,expected):
    if expected>LIMIT: raise ValueError('Compressed record/asset exceeds 256 MiB safety limit')
    obj=zlib.decompressobj(); result=obj.decompress(data,expected+1)
    if len(result)!=expected or not obj.eof or obj.unused_data or obj.unconsumed_tail: raise ValueError('Invalid compressed record/asset')
    return result

def bounded_read(path,limit=LIMIT):
    from safe_io import reject_links
    reject_links(path)
    if path.stat().st_size>limit: raise ValueError('File exceeds scan safety limit: '+str(path))
    with path.open('rb') as f: data=f.read(limit+1)
    if len(data)>limit: raise ValueError('File grew during scan')
    return data

def paths(data, whole=False):
    """Exact length-prefixed strings (NIF) and terminated strings (ESP)."""
    found=set()
    if whole:
        for v in data.split(b'\0'):
            if EXT.search(v) and re.search(rb'\.(nif|dds|tga|bmp|kf|egm|egt|tri|wav|ogg|mp3|lip|bik)$',v,re.I):
                if all(c>=32 for c in v):
                    s=norm(v.decode('cp1252',errors='replace'))
                    if s: found.add(s)
    for m in EXT.finditer(data):
        end=m.end()
        for start in range(max(4,end-2048),m.start()):
            n=struct.unpack_from('<I',data,start-4)[0]
            if n not in (end-start,end-start+1): continue
            if n==end-start+1 and data[end:end+1]!=b'\0': continue
            v=data[start:end]
            if not v or any(c<32 for c in v): continue
            s=norm(v.decode('cp1252',errors='replace'))
            if s: found.add(s)
    return found

def esp_paths(path,masters=None,stop=None):
    b=bounded_read(path,1024*1024*1024); found=set(); stats=collections.Counter(); scripts=[]
    if b[:4]!=b'TES4': raise ValueError('Not a TES4-format plugin')
    def walk(pos,end,depth=0):
        if depth>64: raise ValueError("Plugin nesting exceeds safety limit")
        while pos<end:
            if stop is not None and stop.is_set():
                from safe_io import Cancelled
                raise Cancelled("Plugin scan cancelled")
            if pos+24>end: raise ValueError('Truncated record header')
            typ=b[pos:pos+4]; size,flags=struct.unpack_from('<II',b,pos+4)
            if typ==b'GRUP':
                if size<24 or pos+size>end: raise ValueError('Invalid group size')
                walk(pos+24,pos+size,depth+1); pos+=size; continue
            if pos+24+size>end: raise ValueError('Invalid record size')
            d=b[pos+24:pos+24+size]; stats[typ.decode('ascii')]+=1
            if flags&0x40000:
                expected=struct.unpack_from('<I',d)[0]; d=inflate(d[4:],expected)
                if len(d)!=expected: raise ValueError('Invalid compressed record')
            i=0; extended=None
            while i<len(d):
                if i+6>len(d): raise ValueError('Truncated subrecord')
                tag=d[i:i+4]; n=struct.unpack_from('<H',d,i+4)[0]; i+=6
                if tag==b'XXXX':
                    if n!=4: raise ValueError('Invalid XXXX')
                    if extended is not None or i+4>len(d): raise ValueError('Invalid extended subrecord')
                    extended=struct.unpack_from('<I',d,i)[0]; i+=4; continue
                if extended is not None: n=extended; extended=None
                if i+n>len(d): raise ValueError('Invalid subrecord size')
                v=d[i:i+n]; i+=n
                found.update(paths(v,True))
                if tag==b'MAST' and masters is not None: masters.append(v.rstrip(b'\0').decode('cp1252'))
                if tag==b'SCTX': scripts.append(v.decode('cp1252',errors='replace'))
            if extended is not None: raise ValueError('Orphan XXXX subrecord')
            pos+=24+size
    walk(0,len(b))
    return found,stats,scripts

class BSA:
    def __init__(self,path):
        self.path=path; self.entries={}
        from safe_io import reject_links
        reject_links(path)
        length=path.stat().st_size
        with path.open('rb') as f:
            h=f.read(36)
            if len(h)!=36 or h[:4]!=b'BSA\0': raise ValueError('Invalid BSA header')
            version,offset,self.flags,folders,files,folder_bytes,name_bytes,_=struct.unpack('<8I',h[4:])
            if version not in (103,104) or self.flags&3!=3: raise ValueError('Unsupported BSA or missing names')
            if folders>1000000 or files>2000000 or name_bytes>64*1024*1024 or offset<36 or offset+folders*16>length: raise ValueError('Invalid BSA table limits')
            f.seek(offset); counts=[]
            for _ in range(folders):
                _,count,_=struct.unpack('<QII',f.read(16)); counts.append(count)
            if sum(counts)!=files: raise ValueError('Invalid BSA folder counts')
            entries=[]
            for count in counts:
                n=f.read(1)
                if not n: raise ValueError('Truncated BSA directory')
                folder=f.read(n[0]).rstrip(b'\0').decode('cp1252')
                for _ in range(count):
                    _,size,off=struct.unpack('<QII',f.read(16)); entries.append((folder,size,off))
            names=f.read(name_bytes).split(b'\0')
            if len(entries)!=files or len(names)<files: raise ValueError('Invalid BSA file table')
            for (folder,size,off),name in zip(entries,names):
                key=(folder+'\\'+name.decode('cp1252')).replace('/','\\').lower()
                if off+(size&0x3fffffff)>length: raise ValueError('Invalid BSA asset bounds')
                self.entries[key]=(size,off)
    def read(self,key):
        size,off=self.entries[key]; compressed=bool(self.flags&4)^bool(size&0x40000000); size&=0x3fffffff
        from safe_io import reject_links
        reject_links(self.path)
        if size>LIMIT: raise ValueError('BSA asset exceeds safety limit')
        with self.path.open('rb') as f:
            f.seek(off); d=f.read(size)
        if len(d)!=size: raise ValueError('Truncated BSA asset')
        if self.flags&0x100:
            if not d or 1+d[0]>len(d): raise ValueError('Invalid embedded BSA filename')
            d=d[1+d[0]:]
        if compressed:
            expected=struct.unpack_from('<I',d)[0]; d=inflate(d[4:],expected)
            if len(d)!=expected: raise ValueError('Invalid BSA decompressed size')
        return d

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

