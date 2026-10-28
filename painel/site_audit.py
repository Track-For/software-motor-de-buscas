"""Diagnóstico limitado de HTML público, com conexão restrita a IPs públicos."""
import http.client
import ipaddress
import re
from pathlib import Path
import socket
import ssl
import time
import urllib.parse
from html.parser import HTMLParser

LIMIT = 1_000_000


def tls_context():
    context = ssl.create_default_context()
    context.load_verify_locations(str(Path(__file__).with_name('certs') / 'cacert.pem'))
    return context


def public_target(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('Use um endereço público HTTP ou HTTPS, sem credenciais.')
    host = p.hostname.encode('idna').decode('ascii')
    port = p.port or (443 if p.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('O diagnóstico só acessa endereços públicos da internet.')
    return p, host, port, addresses[0]


def fetch(url):
    for _ in range(5):
        p, host, port, address = public_target(url)
        conn = http.client.HTTPConnection(host, port, timeout=7)
        sock = socket.socket(address[0], address[1], address[2])
        sock.settimeout(7)
        try:
            sock.connect(address[4])  # Usa o IP validado, sem nova resolução DNS.
            if p.scheme == 'https':
                sock = tls_context().wrap_socket(sock, server_hostname=host)
            conn.sock = sock
            conn.request('GET', urllib.parse.urlunsplit(('', '', p.path or '/', p.query, '')),
                         headers={'User-Agent': 'Prospecta-SiteCheck/1.0', 'Accept': 'text/html', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Redirecionamento sem destino.')
                url = urllib.parse.urljoin(url, location)
                continue
            raw = response.read(LIMIT+1)
            if len(raw) > LIMIT:
                raise ValueError('Página excede o limite de 1 MB do diagnóstico.')
            content_type = response.getheader('Content-Type', '')
            charset = response.headers.get_content_charset() or 'utf-8'
            try:
                html = raw.decode(charset, 'replace')
            except LookupError:
                html = raw.decode('utf-8', 'replace')
            return response.status, url, content_type, html
        finally:
            conn.close()
            sock.close()
    raise ValueError('Muitos redirecionamentos; verificação inconclusiva.')


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.viewport = self.form = self.whatsapp = False
        self.links, self.words = [], []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.skip += 1
        if tag == 'meta' and (a.get('name') or '').lower() == 'viewport':
            self.viewport = 'width=device-width' in (a.get('content') or '').replace(' ', '').lower()
        if tag == 'form':
            self.form = True
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
            host = (urllib.parse.urlsplit(a['href']).hostname or '').lower()
            if host == 'wa.me' or host == 'whatsapp.com' or host.endswith('.whatsapp.com'):
                self.whatsapp = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip-1)

    def handle_data(self, data):
        if not self.skip:
            self.words.append(data)


def analyze(url):
    result = dict(url=url, verificado_em=time.time(), estado='inconclusivo', verificacoes=[], links=[])
    try:
        status, final, kind, html = fetch(url)
        result.update(url_final=final, http=status)
        if not 200 <= status < 300:
            result['resumo'] = f'A página respondeu HTTP {status}. Verifique no navegador; bloqueios ao diagnóstico não comprovam site fora do ar.'
            return result
        if 'html' not in kind.lower():
            result['resumo'] = 'O endereço não retornou uma página HTML.'
            return result
        page = Page(); page.feed(html)
        words = ' '.join(page.words).strip()
        checks = [('viewport', 'Indicação de adaptação ao celular (meta viewport)', page.viewport),
                  ('formulario', 'Formulário no HTML inicial', page.form),
                  ('whatsapp', 'Link para WhatsApp no HTML inicial', page.whatsapp),
                  ('servicos', 'Texto com referência a serviços ou produtos', bool(re.search(r'servi[çc]os?|produtos?|tratamentos?|cursos?', words, re.I)))]
        result['verificacoes'] = [dict(id=k, nome=n, encontrado=v) for k, n, v in checks]
        origin = urllib.parse.urlsplit(final)
        candidates = []
        for href in page.links:
            link = urllib.parse.urljoin(final, href).split('#')[0]
            dest = urllib.parse.urlsplit(link)
            if dest.scheme in ('http', 'https') and dest.netloc == origin.netloc and link != final and link not in candidates:
                candidates.append(link)
        for link in candidates[:3]:
            try:
                code, _, _, _ = fetch(link)
                result['links'].append({'url': link, 'http': code, 'estado': 'quebrado' if code in (404, 410) else 'ok' if 200 <= code < 300 else 'inconclusivo'})
            except (OSError, ValueError, http.client.HTTPException):
                result['links'].append({'url': link, 'http': None, 'estado': 'inconclusivo'})
        result.update(estado='concluido', resumo='HTML inicial analisado. Sinais ausentes podem ser carregados por JavaScript. Não substitui avaliação visual no celular nem comprova clareza dos serviços.')
    except (OSError, ValueError, http.client.HTTPException) as exc:
        result['resumo'] = 'Não foi possível concluir: '+str(exc)[:250]
    return result
