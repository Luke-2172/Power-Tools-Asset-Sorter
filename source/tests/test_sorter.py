import sys,struct,zlib,tempfile,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'app'))
import engine,formats
from safe_io import Cancelled

def sub(tag,data): return tag+struct.pack('<H',len(data))+data
def rec(tag,data,compressed=False):
    flags=0
    if compressed: flags=0x40000;data=struct.pack('<I',len(data))+zlib.compress(data)
    return tag+struct.pack('<IIIII',len(data),flags,0,0,0)+data

def plugin(path,refs=(),master=None,compressed=False):
    data=sub(b'MAST',master.encode()+b'\0') if master else b''
    path.write_bytes(rec(b'TES4',data)+rec(b'STAT',b''.join(sub(b'MODL',r.encode()+b'\0') for r in refs),compressed))

def bsa(path,folder,name,data,compressed=False):
    if compressed: data=struct.pack('<I',len(data))+zlib.compress(data)
    fn=folder.encode()+b'\0';nm=name.encode()+b'\0';offset=36+16+1+len(fn)+16+len(nm)
    path.write_bytes(b'BSA\0'+struct.pack('<8I',104,36,7 if compressed else 3,1,1,len(fn),len(nm),0)+struct.pack('<QII',0,1,52)+bytes([len(fn)])+fn+struct.pack('<QII',0,len(data),offset)+nm+data)

class SorterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.src=self.base/'assets';self.src.mkdir();self.out=self.base/'output';self.esp=self.base/'test.esp';self.game=self.base/'Data';self.game.mkdir()
        self.add('Meshes/mod/thing.nif',b'Gamebryo File Format, Version 20.2.0.7\n'+struct.pack('<I',len(b'textures/mod/test.dds'))+b'textures/mod/test.dds')
        for name in ['test.dds','test_n.dds','unused.dds']:self.add('Textures/mod/'+name,name.encode())
        plugin(self.esp,['mod/thing.nif'],compressed=True)
    def tearDown(self):self.tmp.cleanup()
    def add(self,path,data):
        p=self.src/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p
    def analyze(self,**kw):
        options=dict(exclude_vanilla=False,masters=False);options.update(kw)
        return engine.analyze(self.esp,self.src,self.out,**options)
    def test_dependency_copy_and_originals(self):
        before={p:formats.digest(p) for p in [self.esp,*self.src.rglob('*')] if p.is_file()}
        plan=self.analyze();self.assertEqual(sum(r[2]=='required' for r in plan['rows']),3);self.assertFalse(self.out.exists())
        engine.export(plan);self.assertTrue((self.out/'required/Textures/mod/test_n.dds').exists());self.assertFalse((self.out/'not required').exists());self.assertFalse((self.out/'INCOMPLETE.txt').exists())
        self.assertEqual(before,{p:formats.digest(p) for p in before})
        with self.assertRaises(ValueError):engine.export(plan)
    def test_vanilla_identical_and_modified(self):
        bsa(self.game/'Fallout - Textures.bsa','textures/mod','test.dds',b'test.dds',True)
        plan=self.analyze(game=self.game,exclude_vanilla=True);statuses={str(r[1]):r[2] for r in plan['rows']};self.assertEqual(statuses['Textures/mod/test.dds'],'vanilla')
        self.add('Textures/mod/test.dds',b'custom');plan=self.analyze(game=self.game,exclude_vanilla=True);self.assertEqual(next(r[2] for r in plan['rows'] if str(r[1])=='Textures/mod/test.dds'),'required')
    def test_archive_mesh_dependency(self):
        p=self.src/'Meshes/mod/thing.nif';data=p.read_bytes();p.unlink();bsa(self.game/'Fallout - Meshes.bsa','meshes/mod','thing.nif',data)
        plan=self.analyze(game=self.game);self.assertTrue(any(r[2]=='required' and r[1].name=='test.dds' for r in plan['rows']))
    def test_master_and_missing(self):
        plugin(self.esp,[],master='Parent.esm');plugin(self.base/'Parent.esm',['textures/mod/unused.dds'])
        plan=self.analyze(masters=True);self.assertEqual(len(plan['fingerprints']),2);self.assertTrue(any(r[2]=='required' and r[1].name=='unused.dds' for r in plan['rows']))
        (self.base/'Parent.esm').unlink();self.assertTrue(any('Missing master' in w for w in self.analyze(masters=True)['warnings']))
    def test_extended_and_groups(self):
        value=b'textures/mod/test.dds\0';record=rec(b'TXST',sub(b'XXXX',struct.pack('<I',len(value)))+b'TX00\0\0'+value)
        self.esp.write_bytes(rec(b'TES4',b'')+b'GRUP'+struct.pack('<I',24+len(record))+b'\0'*16+record)
        self.assertIn('textures\\mod\\test.dds',formats.esp_paths(self.esp)[0])
    def test_invalid_and_bomb(self):
        self.esp.write_bytes(rec(b'TES4',b'')+b'bad')
        with self.assertRaises(ValueError):self.analyze()
        with self.assertRaises(ValueError):formats.inflate(zlib.compress(b'x'*100),formats.LIMIT+1)
        for path in ['../bad.dds','textures/../bad.dds','C:/bad.dds','textures/con.dds','textures/x.dds:bad']:
            self.assertIsNone(formats.norm(path))
    def test_roots_links_and_changes(self):
        with self.assertRaises(ValueError):engine.analyze(self.esp,self.src,self.src/'output',exclude_vanilla=False)
        link=self.src/'Textures/link.dds';link.symlink_to(self.esp)
        with self.assertRaises(ValueError):self.analyze()
        link.unlink();plan=self.analyze();self.add('Textures/mod/test.dds',b'changed')
        with self.assertRaises(ValueError):engine.export(plan)
        self.assertTrue((self.out/'INCOMPLETE.txt').exists())
    def test_cancel_and_unused(self):
        stop=threading.Event();stop.set()
        with self.assertRaises(Cancelled):self.analyze(stop=stop)
        plan=self.analyze();engine.export(plan,True);self.assertTrue((self.out/'not required/Textures/mod/unused.dds').exists())
    def test_formula_csv(self):
        self.add('=danger.txt',b'x');plan=self.analyze();engine.export(plan)
        self.assertIn("'=danger.txt",(self.out/'classification.csv').read_text('utf-8-sig'))

if __name__=='__main__':unittest.main()
