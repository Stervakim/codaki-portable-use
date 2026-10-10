"""Root-only Unix IPC for an already authenticated phone transport."""
import json,os,socket,stat
from pathlib import Path
from .engine import UseError
SOCKET='/data/adb/codaki-portable-use/state/portable.sock'
def receive(connection,limit=1024*1024):
    data=bytearray()
    while len(data)<=limit:
        chunk=connection.recv(min(65536,limit+1-len(data)))
        if not chunk:break
        data.extend(chunk)
        if b'\n' in chunk:break
    if len(data)>limit or b'\n' not in data:raise ValueError('Invalid IPC framing')
    return json.loads(bytes(data).split(b'\n',1)[0])
def dispatch(engine,request):
    if not isinstance(request,dict) or set(request)!={'op','args','request_id'}:return {'error':'Expected op,args,request_id','code':'REJECTED'}
    try:return engine.execute(request['op'],request['args'],request['request_id'])
    except UseError as e:return {'error':str(e),'code':e.code}
def serve(engine,stop_event,path=SOCKET):
    if os.geteuid()!=0:raise UseError('Phone IPC requires root')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.parent.chmod(0o700)
    if path.exists():
        if not stat.S_ISSOCK(path.lstat().st_mode):raise UseError('Unsafe socket path')
        path.unlink()
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        listener.bind(str(path));path.chmod(0o600);listener.listen(4);listener.settimeout(.5)
        while not stop_event.is_set():
            engine.expire()
            try:connection,_=listener.accept()
            except socket.timeout:continue
            with connection:
                connection.settimeout(40)
                try:out=dispatch(engine,receive(connection))
                except (ValueError,TypeError,KeyError,socket.timeout):out={'error':'Malformed IPC request','code':'REJECTED'}
                try:connection.sendall((json.dumps(out,ensure_ascii=False)+'\n').encode())
                except (BrokenPipeError,ConnectionResetError):pass
    finally:listener.close();path.unlink(missing_ok=True)
def call(request,path=SOCKET):
    if os.geteuid()!=0:raise UseError('Phone IPC requires root')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(40);connection.connect(path)
        connection.sendall((json.dumps(request,ensure_ascii=False)+'\n').encode())
        return receive(connection,4*1024*1024)
def main():
    import sys
    print(json.dumps(call(json.load(sys.stdin)),ensure_ascii=False))
if __name__=='__main__':main()
