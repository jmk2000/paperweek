"""HTTPS subscription download with vetted DNS answers and pinned connections.

No environment proxy, cookie jar, authentication forwarding or automatic
redirects. Each connection uses a prevalidated IP while TLS validates the
original hostname. Run in a short-lived subprocess to bound DNS and wall time.
"""
from __future__ import annotations
import base64
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit
import zlib
from .ical_parser import ICalError, MAX_BYTES
from .sources import normalise_url


def public_address(value):
    try:
        ip = ipaddress.ip_address(value)
        return ip.is_global and not ip.is_multicast and not ip.is_unspecified and not (isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo))
    except ValueError:
        return False


def resolve(host):
    rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ips = list(dict.fromkeys(row[4][0] for row in rows))
    if not ips or len(ips) > 32 or not all(public_address(ip) for ip in ips):
        raise ICalError('Feed destination resolves to a blocked address. Only public HTTPS calendars are permitted.')
    return ips


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        # Use an explicit numeric sockaddr: no second DNS lookup after validation.
        family = socket.AF_INET6 if ':' in self.ip else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.ip, 443))
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def read_body(response, connection, deadline):
    raw_length = response.getheader('Content-Length', '')
    if raw_length and (not raw_length.isdigit() or int(raw_length) > MAX_BYTES):
        raise ICalError('Calendar download exceeds the 2 MiB limit.')
    encoding = response.getheader('Content-Encoding', 'identity').lower().strip()
    if encoding not in ('identity', '', 'gzip'):
        raise ICalError('Unsupported feed compression. Supply an uncompressed or gzip iCalendar feed.')
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == 'gzip' else None
    chunks, size, wire = [], 0, 0
    while True:
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise ICalError('Feed download timed out; previous data retained.')
        if connection.sock:
            connection.sock.settimeout(min(8, remaining))
        block = response.read(65536)
        if not block:
            break
        wire += len(block)
        if wire > MAX_BYTES:
            raise ICalError('Calendar download exceeds the 2 MiB limit.')
        if inflater:
            block = inflater.decompress(block, MAX_BYTES-size+1)
        size += len(block)
        if size > MAX_BYTES or (inflater and inflater.unconsumed_tail):
            raise ICalError('Expanded calendar exceeds the 2 MiB limit.')
        chunks.append(block)
    if raw_length and wire != int(raw_length):
        raise ICalError('Incomplete calendar download; previous data retained.')
    if inflater and (not inflater.eof or inflater.unused_data):
        raise ICalError('Truncated or concatenated gzip feed was rejected.')
    return b''.join(chunks)


def download(url, etag='', modified='', resolver=resolve, connection_factory=PinnedHTTPS):
    deadline = time.monotonic()+20
    try:
        url = normalise_url(url)
        headers = {'Accept':'text/calendar, text/plain;q=0.8', 'Accept-Encoding':'gzip',
                   'User-Agent':'Paperweek/0.5 calendar subscriber', 'Connection':'close'}
        # Validators are private opaque provider data, bounded and never logged.
        for name, value in [('If-None-Match', etag), ('If-Modified-Since', modified)]:
            if value and len(value) <= 512 and not any(ord(c)<32 or ord(c)==127 for c in value):
                headers[name] = value
        visited = set()
        for hop in range(4):
            if url in visited:
                raise ICalError('Calendar redirect loop.')
            visited.add(url)
            u = urlsplit(url)
            ips = resolver(u.hostname)
            # Recheck even if a custom resolver is injected. HTTP adapters cannot
            # accidentally bypass the security policy by returning a LAN address.
            if not ips or not all(public_address(ip) for ip in ips):
                raise ICalError('Calendar resolved to a blocked network address.')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise ICalError('Feed request timed out.')
            conn = connection_factory(u.hostname, ips[0], min(8, remaining))
            try:
                path = u.path + ('?' + u.query if u.query else '')
                conn.request('GET', path, headers=headers)
                response = conn.getresponse()
                status = response.status
                if status in (301, 302, 303, 307, 308):
                    target = response.getheader('Location', '')
                    if not target or hop == 3:
                        raise ICalError('Too many redirects or missing redirect destination.')
                    new = normalise_url(urljoin(url, target))
                    if urlsplit(new).netloc != u.netloc:
                        headers.pop('If-None-Match', None); headers.pop('If-Modified-Since', None)
                    url = new
                    continue
                if status == 304:
                    return {'notModified':True}
                if status in (401, 403):
                    raise ICalError('Feed access denied. Check the private subscription URL; login pages and password-based feeds are not supported.')
                if status in (404, 410):
                    raise ICalError('Feed no longer exists or its private link has expired.')
                if status != 200:
                    raise ICalError('Feed provider returned an unsuccessful response; retry scheduled.')
                data = read_body(response, conn, deadline)
                return {'notModified':False, 'data':base64.b64encode(data).decode('ascii'),
                        'etag':response.getheader('ETag', '')[:512],
                        'modified':response.getheader('Last-Modified', '')[:512]}
            finally:
                conn.close()
        raise ICalError('Feed could not be downloaded.')
    except ICalError:
        raise
    except Exception:
        raise ICalError('Could not securely download the calendar. Check DNS, TLS, connectivity and the subscription address.') from None
