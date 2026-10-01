"""Copy-only static dependency sorter. No plugin writes, deletion, or network access."""
from pathlib import Path
from collections import deque, Counter
import os, re, io, shutil
from formats import esp_paths, paths, norm, BSA, OFFICIAL, bounded_read, digest
from safe_io import roots, reject_links, is_link, atomic_write, SafeCSV, Cancelled

NOTICE=('Static dependency scan, not an in-game guarantee. Full master records are scanned conservatively; '
        'this is not a load-order or FormID resolver. Dynamic script paths, generated voice/FaceGen/LOD and '
        'external mod dependencies may need manual review. Unreferenced does not mean safe to delete. '
        'Only byte-identical official textures are excluded as vanilla; modified replacers are retained. '
        'Keep originals and test the required folder in game.')

def check(stop):
    if stop is not None and stop.is_set(): raise Cancelled('Cancelled. Any partial output is not a finished result.')

def inventory(source,stop):
    found={}
    def fail(e): raise e
    for directory,dirs,files in os.walk(source,followlinks=False,onerror=fail):
        check(stop)
        for n in dirs+files:
            p=Path(directory)/n
            if is_link(p): raise ValueError('Linked file/folder is not supported: '+str(p))
        for n in files:
            p=Path(directory)/n
            if not p.is_file(): raise ValueError('Non-regular input file: '+str(p))
            rel=p.relative_to(source); key=str(rel).replace('/','\\').lower()
            if key in found: raise ValueError('Case-insensitive duplicate input path: '+key)
            if norm(key) is None: raise ValueError('Unsafe Windows asset path: '+key)
            st=p.stat(); found[key]=(p,rel,st.st_size,st.st_mtime_ns)
    return found

def analyze(plugin,source,output,game='',exclude_vanilla=True,conservative=True,masters=True,stop=None,log=lambda s:None):
    source,output=roots(source,output); plugin=Path(plugin).absolute(); reject_links(plugin)
    if not plugin.is_file() or plugin.suffix.lower() not in ('.esp','.esm'): raise ValueError('Choose an ESP or ESM plugin')
    if output.exists() and any(output.iterdir()): raise ValueError('Choose a new or empty output folder')
    if plugin==output or output in plugin.parents: raise ValueError('Output cannot contain the selected plugin')
    data=None
    if game:
        data=Path(game).absolute(); reject_links(data)
        if (data/'Data').is_dir(): data=data/'Data'
        if not data.is_dir(): raise ValueError('Game/Data folder does not exist')
    if exclude_vanilla and data is None: raise ValueError('Select the game or Data folder to identify vanilla textures, or turn off vanilla exclusion')
    if data and (output==data or output in data.parents or data in output.parents): raise ValueError('Output must be outside the game Data folder')
    log('Indexing input folder...'); inv=inventory(source,stop)
    if not inv: raise ValueError('Input folder contains no files')
    if not any(k.startswith(('meshes\\','textures\\','sound\\','music\\','video\\')) for k in inv): raise ValueError('Select a folder containing Meshes, Textures, Sound, Music or Video folders')
    needed=set(); reasons={}; warnings=[]; fingerprints={}; plugins=deque([plugin]); seen=set()
    while plugins:
        check(stop); p=plugins.popleft(); reject_links(p); identity=str(p.resolve()).casefold()
        if identity in seen: continue
        if len(seen)>=256: raise ValueError('Master chain exceeds 256 plugins')
        seen.add(identity); log('Reading '+p.name+'...'); before=digest(p)
        names=[]; refs,stats,scripts=esp_paths(p,names,stop)
        if digest(p)!=before: raise ValueError('Plugin changed during scan: '+str(p))
        fingerprints[p]=before
        for k in refs: needed.add(k); reasons.setdefault(k,'Plugin reference: '+p.name)
        for script in scripts:
            for s in re.findall(r'"([^"\r\n]+\.(?:nif|dds|tga|bmp|kf|wav|ogg|mp3|bik))"',script,re.I):
                k=norm(s)
                if k: needed.add(k); reasons.setdefault(k,'Script reference: '+p.name)
        if scripts: warnings.append(p.name+': script source present; dynamically constructed paths cannot be resolved.')
        if masters:
            for name in names:
                if '/' in name or '\\' in name or ':' in name or Path(name).suffix.lower() not in ('.esp','.esm'): raise ValueError('Unsafe master filename in plugin')
                resolved=None
                for folder in [p.parent,*([data] if data else [])]:
                    matches=[q for q in folder.iterdir() if q.name.casefold()==name.casefold()]
                    if len(matches)>1: raise ValueError('Ambiguous master filename: '+name)
                    if matches: resolved=matches[0]; break
                if resolved: plugins.append(resolved)
                else: warnings.append('Missing master: '+name+'; inherited assets may be missed.')
    archives={}; archive_names=[]
    if data:
        log('Indexing official mesh/texture archives...')
        for p in sorted(data.iterdir()):
            check(stop)
            if OFFICIAL.fullmatch(p.name):
                a=BSA(p); archive_names.append(p.name)
                for k in a.entries: archives.setdefault(k,[]).append(a)
        if exclude_vanilla and not any(n.lower().startswith('fallout - textures') for n in archive_names): raise ValueError('No official Fallout texture BSA found; vanilla exclusion cannot be verified')
    if conservative:
        for k in inv:
            if any(s in k for s in ('\\facegen\\','\\facegendata\\','\\characters\\','\\lod\\')) or k.endswith(('.kf','.egm','.egt','.tri')) or not k.startswith(('meshes\\','textures\\')):
                needed.add(k); reasons.setdefault(k,'Conservative retention: generated, character, animation or other asset')
            elif k in archives:
                needed.add(k); reasons.setdefault(k,'Conservative retention: official-path replacer')
    queue=deque(sorted(needed)); visited=set()
    log('Following mesh and texture dependencies...')
    while queue:
        check(stop); k=queue.popleft()
        if k in visited: continue
        visited.add(k)
        if not k.endswith('.nif'): continue
        if k in inv: blob=bounded_read(inv[k][0])
        elif k in archives: blob=archives[k][-1].read(k)
        else: continue
        if not blob.startswith((b'Gamebryo File Format',b'NetImmerse File Format')): raise ValueError('Unsupported or corrupt NIF: '+k)
        for ref in paths(blob):
            if ref not in needed: needed.add(ref); reasons[ref]='Mesh dependency: '+k; queue.append(ref)
    for k in list(needed):
        if k.endswith('.dds') and not k[:-4].endswith(('_n','_g','_m','_s','_em')):
            for suffix in ('_n.dds','_g.dds','_m.dds','_s.dds','_em.dds'):
                companion=k[:-4]+suffix
                if companion in inv: needed.add(companion); reasons.setdefault(companion,'Possible shader companion: '+k)
        if k.endswith(('.ogg','.wav','.mp3')) and k[:-4]+'.lip' in inv:
            companion=k[:-4]+'.lip';needed.add(companion);reasons.setdefault(companion,'Matching lip-sync file: '+k)
    rows=[]
    for i,(k,(p,rel,size,stamp)) in enumerate(sorted(inv.items())):
        check(stop)
        if i%250==0: log('Classifying file '+str(i+1)+' / '+str(len(inv)))
        status='required' if k in needed else 'not required'; reason=reasons.get(k,'No static reference found; review before deleting')
        if exclude_vanilla and k.startswith('textures\\') and k in archives:
            local=bounded_read(p)
            if any(local==a.read(k) for a in archives[k]): status='vanilla'; reason='Byte-identical to official game/DLC texture'
            elif conservative: status='required'; reason='Modified official-path texture; possible replacer'
        rows.append((p,rel,status,reason,size,stamp))
    missing=[(k,reasons.get(k,'')) for k in sorted(needed-set(inv)-set(archives))]
    if missing: warnings.append(str(len(missing))+' references were not found in input or official archives; see missing-references.csv.')
    for p,h in fingerprints.items():
        if digest(p)!=h: raise ValueError('Plugin changed during scan: '+str(p))
    return dict(source=source,output=output,rows=rows,missing=missing,warnings=warnings,fingerprints=fingerprints,archives=archive_names)

def export(plan,copy_unused=False,stop=None,log=lambda s:None):
    source,output=roots(plan['source'],plan['output']); check(stop)
    if output.exists() and any(output.iterdir()): raise ValueError('Output is no longer empty; choose a new folder')
    for p,h in plan['fingerprints'].items():
        reject_links(p)
        if digest(p)!=h: raise ValueError('Plugin changed since preview; scan again')
    selected=[r for r in plan['rows'] if r[2]=='required' or copy_unused]
    parent=output
    while not parent.exists(): parent=parent.parent
    if shutil.disk_usage(parent).free<sum(r[4] for r in selected)+32*1024*1024: raise ValueError('Insufficient disk space for selected copies')
    output.mkdir(parents=True,exist_ok=True)
    marker=output/'INCOMPLETE.txt'; atomic_write(marker,data=b'Incomplete export. Do not use until SUMMARY.txt confirms completion. Originals are unchanged.')
    (output/'required').mkdir()
    for i,(p,rel,status,reason,size,stamp) in enumerate(selected,1):
        check(stop); reject_links(p); st=p.stat()
        if st.st_size!=size or st.st_mtime_ns!=stamp: raise ValueError('Input changed since scan: '+str(rel))
        dest=output/('required' if status=='required' else 'not required')/rel
        atomic_write(dest,source=p)
        st=p.stat()
        if st.st_size!=size or st.st_mtime_ns!=stamp: raise ValueError('Input changed while copying: '+str(rel))
        log('Copied '+str(i)+' / '+str(len(selected))+': '+str(rel))
    for p,h in plan['fingerprints'].items():
        if digest(p)!=h: raise ValueError('Plugin changed during copy')
    def report(name,headers,rows):
        stream=io.StringIO(newline='');w=SafeCSV(stream);w.writerow(headers)
        for row in rows: w.writerow(row)
        atomic_write(output/name,data=stream.getvalue().encode('utf-8-sig'))
    report('classification.csv',['Path','Classification','Reason','Bytes'],[(str(r[1]),r[2],r[3],r[4]) for r in plan['rows']])
    report('missing-references.csv',['Path','Reason'],plan['missing'])
    counts=Counter(r[2] for r in plan['rows'])
    summary='FNV Asset Sorter 1.0 — COMPLETE\n\n'+str(dict(counts))+'\n\n'+NOTICE+'\n\nWarnings:\n'+'\n'.join(plan['warnings'])+'\n\nPlugin SHA256:\n'+'\n'.join(str(p)+' '+h for p,h in plan['fingerprints'].items())
    check(stop);atomic_write(output/'SUMMARY.txt',data=summary.encode('utf-8'));marker.unlink()
    return output
