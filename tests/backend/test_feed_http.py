"""Offline security tests: injected DNS and HTTPS transport, no provider calls."""
import base64
import gzip
import io
import socket
import time
from types import SimpleNamespace
import pytest
from backend.feed_http import download, read_body, resolve, public_address, PinnedHTTPS
from backend.ical_parser import ICalError, MAX_BYTES

URL='https://calendar.example.net/feed.ics?key=fixture-only'
PUBLIC='93.184.216.34'
DATA=b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n'

class Response:
    def __init__(self, status=200, body=DATA, headers=None):
        self.status=status;self.body=io.BytesIO(body);self.headers=headers or {}
    def getheader(self,key,default=None):return self.headers.get(key,default)
    def read(self,size):return self.body.read(size)

class Transport:
    def __init__(self,responses):self.responses=list(responses);self.requests=[];self.closed=0
    def __call__(self,host,ip,timeout):
        parent=self
        class Connection:
            sock=None
            def request(self,method,path,headers):parent.requests.append((host,ip,method,path,dict(headers)))
            def getresponse(self):return parent.responses.pop(0)
            def close(self):parent.closed+=1
        return Connection()

def get(responses,url=URL,resolver=lambda host:[PUBLIC],**kwargs):
    transport=Transport(responses)
    result=download(url,resolver=resolver,connection_factory=transport,**kwargs)
    return result,transport

def test_pins_vetted_ip_https_host_and_does_not_pass_auth():
    r,t=get([Response(headers={'ETag':'"one"','Last-Modified':'Sat, 05 Sep 2026 12:00:00 GMT'})])
    assert base64.b64decode(r['data'])==DATA and r['etag']=='"one"'
    host,ip,method,path,headers=t.requests[0]
    assert (host,ip,method,path)==('calendar.example.net',PUBLIC,'GET','/feed.ics?key=fixture-only')
    assert 'Authorization' not in headers and 'Cookie' not in headers
    assert t.closed==1

@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','192.168.1.1','169.254.169.254','100.64.1.1','0.0.0.0','224.0.0.1','::1','fe80::1','fc00::1','::ffff:93.184.216.34','2002:5db8:d822::1'])
def test_blocks_every_nonpublic_or_tunnelling_destination(ip):
    assert not public_address(ip)
    with pytest.raises(ICalError):get([],resolver=lambda host:[ip])

def test_mixed_dns_answer_is_rejected(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',(PUBLIC,443)),(0,0,0,'',('10.0.0.1',443))])
    with pytest.raises(ICalError):resolve('calendar.example.net')

def test_resolver_deduplicates_global_answers(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',(PUBLIC,443))]*3)
    assert resolve('calendar.example.net')==[PUBLIC]

@pytest.mark.parametrize('location',['http://calendar.example.net/x','https://127.0.0.1/x','file:///etc/passwd','https://example.net:8443/x'])
def test_redirect_protocol_ports_and_literal_private_rejected(location):
    with pytest.raises(ICalError):get([Response(302,headers={'Location':location})])

def test_redirect_private_dns_rechecked():
    seen=[]
    def resolver(host):seen.append(host);return [PUBLIC] if len(seen)==1 else ['10.0.0.1']
    with pytest.raises(ICalError):get([Response(302,headers={'Location':'https://private.example.net/calendar'})],resolver=resolver)
    assert len(seen)==2

def test_cross_origin_redirect_drops_validators_but_same_origin_keeps():
    _,t=get([Response(302,headers={'Location':'/new'}),Response(302,headers={'Location':'https://other.example.net/new'}),Response()],etag='"opaque"',modified='fixture')
    assert t.requests[0][4]['If-None-Match']=='"opaque"'
    assert t.requests[1][4]['If-None-Match']=='"opaque"'
    assert 'If-None-Match' not in t.requests[2][4] and 'If-Modified-Since' not in t.requests[2][4]
    assert t.closed==3

def test_no_injected_headers():
    _,t=get([Response()],etag='unsafe\r\nAuthorization: x',modified='x'*513)
    assert 'If-None-Match' not in t.requests[0][4] and 'If-Modified-Since' not in t.requests[0][4]

def test_304_and_status_errors_and_loops():
    assert get([Response(304)])[0]=={'notModified':True}
    for status in (401,403,404,410,429,500):
        with pytest.raises(ICalError):get([Response(status,body=b'private provider details')])
    with pytest.raises(ICalError,match='loop'):get([Response(302,headers={'Location':URL})])
    with pytest.raises(ICalError,match='Too many'):
        get([Response(302,headers={'Location':'/path'+str(i)}) for i in range(4)])

def test_gzip_and_complete_content_length():
    compressed=gzip.compress(DATA)
    r,_=get([Response(body=compressed,headers={'Content-Encoding':'gzip','Content-Length':str(len(compressed))})])
    assert base64.b64decode(r['data'])==DATA
    with pytest.raises(ICalError,match='Incomplete'):
        get([Response(headers={'Content-Length':str(len(DATA)+1)})])

@pytest.mark.parametrize('headers,body',[
    ({'Content-Length':str(MAX_BYTES+1)},b''),
    ({'Content-Length':'unknown'},b''),
    ({'Content-Encoding':'br'},DATA),
    ({},b'x'*(MAX_BYTES+1)),
    ({'Content-Encoding':'gzip'},gzip.compress(b'x'*(MAX_BYTES+1))),
    ({'Content-Encoding':'gzip'},gzip.compress(DATA)[:-3]),
    ({'Content-Encoding':'gzip'},gzip.compress(DATA)+gzip.compress(DATA)),
])
def test_download_size_compression_integrity_limits(headers,body):
    with pytest.raises(ICalError):get([Response(headers=headers,body=body)])

def test_deadline_and_error_redaction():
    with pytest.raises(ICalError,match='timed out'):read_body(Response(),SimpleNamespace(sock=None),time.monotonic()-1)
    def bad(host):raise RuntimeError(URL+' private response')
    with pytest.raises(ICalError) as exc:get([],resolver=bad)
    assert URL not in str(exc.value) and 'fixture-only' not in str(exc.value)

def test_socket_pin_no_second_dns_and_tls_server_name(monkeypatch):
    calls=[]
    class Socket:
        def settimeout(self,v):pass
        def connect(self,v):calls.append(('connect',v))
        def close(self):calls.append(('close',))
    sock=Socket()
    monkeypatch.setattr(socket,'socket',lambda *args:sock)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:pytest.fail('second DNS lookup'))
    conn=PinnedHTTPS('calendar.example.net',PUBLIC,8)
    conn._context=SimpleNamespace(wrap_socket=lambda s,server_hostname:(calls.append(('tls',server_hostname)) or s))
    conn.connect()
    assert calls==[('connect',(PUBLIC,443)),('tls','calendar.example.net')]
