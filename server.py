from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlsplit
import json, os, re, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLI = '/usr/local/bin/lark-cli' if Path('/usr/local/bin/lark-cli').exists() else 'lark-cli'
CONFIG_PATH = ROOT / 'config.local.json'
CONFIG = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
BASE_TOKEN = os.environ.get('FEISHU_BASE_TOKEN', CONFIG.get('base_token', ''))
TABLE_ID = os.environ.get('FEISHU_TABLE_ID', CONFIG.get('table_id', ''))
VIEW_ID = os.environ.get('FEISHU_VIEW_ID', CONFIG.get('view_id', ''))
PLATFORMS = {'bilibili.com':'B站','tiktok.com':'TikTok','instagram.com':'Instagram','youtube.com':'YouTube','youtu.be':'YouTube','x.com':'X','twitter.com':'X','douyin.com':'抖音'}

def load():
    if not all((BASE_TOKEN,TABLE_ID,VIEW_ID)): raise RuntimeError('请先配置飞书表格信息。')
    results = []
    with tempfile.TemporaryDirectory(prefix='video-feed-') as tmp:
        offset = 0
        while True:
            out = f'page-{offset}.ndjson'
            cmd = [CLI,'base','+record-list','--base-token',BASE_TOKEN,'--table-id',TABLE_ID,'--view-id',VIEW_ID,'--field-id','标题','--field-id','分享链接','--field-id','视频爆了','--field-id','评论区佐证','--format','ndjson','--output',out,'--offset',str(offset),'--as','user']
            proc = subprocess.run(cmd,cwd=tmp,capture_output=True,text=True,timeout=60)
            if proc.returncode:
                raise RuntimeError('无法读取飞书表格，请检查飞书登录和表格读取权限。')
            meta = json.loads(proc.stdout)
            for line in (Path(tmp)/out).read_text().splitlines():
                row = json.loads(line)
                for url in re.findall(r'https?://[^\s\]\)\u4e00-\u9fff，。]+',row.get('分享链接') or ''):
                    host=(urlsplit(url).hostname or '').lower()
                    platform=next((v for k,v in PLATFORMS.items() if host==k or host.endswith('.'+k)),None)
                    if platform:
                        results.append({'platform':platform,'url':url,'title':row.get('标题') or '视频','stats':row.get('视频爆了') or '', 'comments':row.get('评论区佐证') or ''})
            if not meta.get('has_more'): break
            count=meta.get('records_count',0)
            if not count: raise RuntimeError('飞书返回分页异常，请稍后重试。')
            offset += count
    return results

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        if self.path.split('?')[0]=='/api/videos':
            if self.headers.get('Host','') not in ('127.0.0.1:8765','localhost:8765'):
                self.send_error(403); return
            try:
                body=json.dumps({'items':load()},ensure_ascii=False).encode();code=200
            except Exception as e:
                body=json.dumps({'error':str(e)},ensure_ascii=False).encode();code=502
            self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        elif self.path in ('/','/index.html'):
            super().do_GET()
        else: self.send_error(404)
    def log_message(self,*args): pass

if __name__=='__main__': ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
