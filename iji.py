# -*- coding: utf-8 -*-
__author__ = 'Yuanzhou Qiu'

import os, re, sys, cgi, json, urllib, datetime, types, mimetypes, threading, functools, logging, traceback
from toDict import Dict

try:
	from cStringIO import StringIO
except ImportError:
	from StringIO import StringIO

ctx = threading.local()

def _to_str(s):
	if isinstance(s, str):
		return s
	if isinstance(s, unicode):
		return s.encode('utf-8')
	return str(s)

def _to_unicode(s, encoding='utf-8'):
	return s.decode(encoding)

def _quote(s, encoding='utf-8'):
	if isinstance(s, unicode):
		s = s.encode(encoding)
	return urllib.quote(s)

def _unquote(s, encoding='utf-8'):
	return urllib.unquote(s).decode(encoding)

class MultipartFile(object):
	def __init__(self, storage):
		self.filename = _to_unicode(storage.filename)
		self.file = storage.file

class Request(object):
	def __init__(self, env):
		self._env = env

	def _parse_input(self):
		def _convert(item):
			if isinstance(item, list):
				return [_to_unicode(i.value) for i in item]
			if item.filename:
				return MultipartFile(item)
			return _to_unicode(item.value)

		fs = cgi.FieldStorage(fp=self._env['wsgi.input'], environ=self._env, keep_blank_values=True)
		inputs = dict()
		for key in fs:
			inputs[key] = _convert(fs[key])
		return inputs

	def _get_raw_input(self):
		if not hasattr(self, '_raw_input'):
			self._raw_input = self._parse_input()
		return self._raw_input

	def __getitem__(self, key):
		r = self._get_raw_input()[key]
		if isinstance(r, list):
			return r[0]
		return r

	def get(self, key, default=None):
		r = self._get_raw_input().get(key, default)
		if isinstance(r, list):
			return r[0]
		return r

	def gets(self, key):
		r = self._get_raw_input()[key]
		if isinstance(r, list):
			return r[:]
		return [r]

	def input(self, **kw):
		copy = Dict(**kw)
		raw = self._get_raw_input()
		for k, v in raw.iteritems():
			copy[k] = v[0] if isinstance(v, list) else v
		return copy

	def get_body(self):
		fp = self._env['wsgi.input']
		return fp.read()

	def get_json(self):
		form = cgi.FieldStorage(fp=self._env['wsgi.input'], environ=self._env)
		req_str = form.value
		return Dict(**json.loads(req_str))

	@property
	def remote_addr(self):
		return self._env.get('REMOTE_ADDR', '0.0.0.0')

	@property
	def document_root(self):
		return self._env.get('DOCUMENT_ROOT', '')

	@property
	def query_string(self):
		return self._env.get('QUERY_STRING', '')

	@property
	def environ(self):
		return self._env

	@property
	def request_method(self):
		return self._env['REQUEST_METHOD']

	@property
	def path_info(self):
		return urllib.unquote(self._env.get('PATH_INFO', ''))

	@property
	def host(self):
		return self._env.get('HTTP_HOST', '')

	def _get_headers(self):
		if not hasattr(self, '_headers'):
			hdrs = {}
			for k, v in self._env.iteritems():
				if k.startswith('HTTP_'):
					hdrs[k[5:].replace('_', '-').upper()] = v.decode('utf-8')
			self._headers = hdrs
		return self._headers

	@property
	def headers(self):
		return dict(**self._get_headers())

	def header(self, header, default=None):
		return self._get_headers().get(header.upper(), default)

	def _get_cookies(self):
		if not hasattr(self, '_cookies'):
			cookies = {}
			cookie_str = self._env.get('HTTP_COOKIE')
			if cookie_str:
				for c in cookie_str.split(';'):
					pos = c.find('=')
					if pos > 0:
						cookies[c[:pos].strip()] = _unquote(c[pos+1:])
			self._cookies = cookies
		return self._cookies

	@property
	def cookies(self):
		return Dict(**self._get_cookies())

	def cookie(self, name, default=None):
		return self._get_cookies().get(name, default)

_timeDelta_zero = datetime.timedelta(0)
_re_tz = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')

class UTC(datetime.tzinfo):
	def __init__(self, utc):
		utc = str(utc.strip().upper())
		mt = _re_tz.match(utc)
		if mt:
			minus = mt.group(1) == '-'
			h = int(mt.group(2))
			m = int(mt.group(3))
			if minus:
				h, m = (-h), (-m)
			self._utcoffset = datetime.timedelta(hours=h, minutes=m)
			self._tzname = 'UTC%s' % utc
		else:
			raise ValueError('bad utc time zone')
	def utcoffset(self, dt):
		return self._utcoffset
	def dst(self, dt):
		return _timeDelta_zero
	def tzname(self, dt):
		return self._tzname
	def __str__(self):
		return 'UTC tzinfo object (%s)' % self._tzname
	__repr__ = __str__

UTC_0 = UTC('+00:00')

from response_headers import response_headers as _response_headers
from response_statuses import response_statuses as _response_statuses

_re_response_status = re.compile(r'^\d\d\d(\ [\w\ ]+)?$')
_response_header_dict = dict(zip(map(lambda x: x.upper(), _response_headers), _response_headers))
_header_x_powered_by = ('X-Powered-By', 'ijiLIB/1.0')

class Response(object):
	def __init__(self):
		self._status = '200 OK'
		self._headers = {'CONTENT-TYPE': 'text/html; charset=utf-8'}

	@property
	def headers(self):
		L = [(_response_header_dict.get(k, k), v) for k, v in self._headers.iteritems()]
		if hasattr(self, '_cookies'):
			for v in self._cookies.itervalues():
				L.append(('Set-Cookie', v))
		L.append(_header_x_powered_by)
		return L

	def header(self, name):
		key = name.upper()
		if not key in _response_header_dict:
			key = name
		return self._headers.get(key)

	def unset_header(self, name):
		key = name.upper()
		if not key in _response_header_dict:
			key = name
		if key in self._headers:
			del self._headers[key]

	def set_header(self, name, value):
		key = name.upper()
		if not key in _response_header_dict:
			key = name
		self._headers[key] = _to_str(value)

	@property
	def content_type(self):
		return self.header('CONTENT-TYPE')
	@content_type.setter
	def content_type(self, value):
		if value:
			self.set_header('CONTENT-TYPE', value)
		else:
			self.unset_header('CONTENT-TYPE')

	@property
	def content_length(self):
		return self.header('CONTENT-TYPE')
	@content_length.setter
	def content_length(self, value):
		self.set_header('CONTENT-TYPE', str(value))

	def delete_cookie(self, name):
		self.set_cookie(name, '__deleted__', expires=0)

	def set_cookie(self, name, value, max_age=None, expires=None, path='/', domain=None, secure=False, http_only=True):
		if not hasattr(self, '_cookies'):
			self._cookies = {}
		L = ['%s=%s' % (_quote(name), _quote(value))]
		if expires is not None:
			if isinstance(expires, (float, int, long)):
				L.append('Expires=%s' % datetime.datetime.fromtimestamp(expires, UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
			if isinstance(expires, (datetime.date, datetime.datetime)):
				L.append('Expires=%s' % expires.astimezone(UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
		elif isinstance(max_age, (int, long)):
			L.append('Max-Age=%d' % max_age)
		L.append('Path=%s' % path)
		if domain:
			L.append('Domain=%s' % domain)
		if secure:
			L.append('Secure')
		if http_only:
			L.append('HttpOnly')
		self._cookies[name] = '; '.join(L)

	def unset_cookie(self, name):
		if hasattr(self, '_cookies'):
			if name in self._cookies:
				del self._cookies[name]

	@property
	def status_code(self):
		return int(self._status[:3])

	@property
	def status(self):
		return self._status
	@status.setter
	def status(self, value):
		if isinstance(value, (int, long)):
			if value >= 100 and value <= 999:
				st = _response_statuses.get(value, '')
				if st:
					self._status = '%d %s' % (value, st)
				else:
					self._status = str(value)
			else:
				raise ValueError('Bad response code: %d' % value)
		elif isinstance(value, basestring):
			if isinstance(value, unicode):
				value = value.encode('utf-8')
			if _re_response_status.match(value):
				self._status = value
			else:
				raise ValueError('Bad response code: %s' % value)
		else:
			raise TypeError('Bad type of response code.')

class HttpError(Exception):
	def __init__(self, code):
		super(HttpError, self).__init__()
		self.status = '%d %s' % (code, _response_statuses[code])

	def header(self, name, value):
		if not hasattr(self, '_headers'):
			self._headers = [_header_x_powered_by]
		self._headers.append((name, value))

	@property
	def headers(self):
		if hasattr(self, '_headers'):
			return self._headers
		return []

	def __str__(self):
		return self.status

	__repr__ = __str__

class RedirectError(HttpError):
	def __init__(self, code, location):
		super(RedirectError, self).__init__(code)
		self.location = location

	def __str__(self):
		return '%s, %s' % (self.status, self.location)

	__repr__ = __str__

def badrequest():
	return HttpError(400)

def unauthorized():
	return HttpError(401)

def forbidden():
	return HttpError(403)

def notfound():
	return HttpError(404)

def conflict():
	return HttpError(409)

def internalerror():
	return HttpError(500)

def redirect(location):
	return RedirectError(301, location)

def found(location):
	return RedirectError(302, location)

def seeother(location):
	return RedirectError(303, location)

def get(path):
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__ = 'GET'
		return func
	return _decorator

def post(path):
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__ = 'POST'
		return func
	return _decorator

def put(path):
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__ = 'PUT'
		return func
	return _decorator

def delete(path):
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__ = 'DELETE'
		return func
	return _decorator

_re_route = re.compile(r'(\:[a-zA-Z_]\w*)')

def _build_regex(path):
	var_list = []
	is_var = False
	re_list = ['^']
	for v in _re_route.split(path):
		if is_var:
			var_name = v[1:]
			var_list.append(var_name)
			re_list.append(r'(?P<%s>[^\/]+)' % var_name)
		else:
			s = ''
			for ch in v:
				if ch >= '0' and ch <= '9':
					s = s + ch
				elif ch >= 'a' and ch <= 'z':
					s = s + ch
				elif ch >= 'A' and ch <= 'Z':
					s = s + ch
				else:
					s = s + '\\' + ch
			re_list.append(s)
		is_var = not is_var
	re_list.append('$')
	return ''.join(re_list)

class Route(object):
	def __init__(self, func):
		self.func = func
		self.method = func.__web_method__
		self.path = func.__web_route__
		self.is_static = _re_route.search(self.path) is None
		if not self.is_static:
			self.route = re.compile(_build_regex(self.path))

	def match(self, req_url):
		m = self.route.match(req_url)
		if m:
			return m.groups()
		return None

	def __call__(self, *args):
		return self.func(*args)

	def __str__(self):
		if self.is_static:
			return 'Route(static,%s,path=%s)' % (self.method, self.path)
		return 'Route(dynamic,%s,paht=%s)' % (self.method, self.path)

	__repr__ = __str__

def _static_file_generator(fpath):
	BLOCK_SIZE = 8192
	with open(fpath, 'rb') as f:
		block = f.read(BLOCK_SIZE)
		while block:
			yield block
			block = f.read(BLOCK_SIZE)

class StaticFileRoute(object):
	def __init__(self):
		self.method = 'GET'
		self.is_static = False
		self.route = re.compile('^/static/(.+)$')

	def match(self, url):
		if url.startswith('/static/'):
			return (url[1:], )
		return None

	def __call__(self, *args):
		fpath = os.path.join(ctx.application.document_root, args[0])
		if not os.path.isfile(fpath):
			raise notfound()
		fext = os.path.splitext(fpath)[1]
		ctx.response.content_type = mimetypes.types_map.get(fext.lower(), 'application/octet-stream')
		return _static_file_generator(fpath)

class Template(object):
	def __init__(self, template_name, **kw):
		self.template_name = template_name
		self.model = dict(**kw)

class TemplateEngine(object):
	def __call__(self, path, model):
		return '<!-- override this method to render template -->'

class Jinja2TemplateEngine(TemplateEngine):
	def __init__(self, templ_dir, **kw):
		from jinja2 import Environment, FileSystemLoader
		if not 'autoescape' in kw:
			kw['autoescape'] = True
		self._env = Environment(loader=FileSystemLoader(templ_dir), **kw)

	def add_filter(self, name, filter_fn):
		self._env.filters[name] = filter_fn

	def __call__(self, path, model):
		return self._env.get_template(path).render(**model).encode('utf-8')

def view(path):
	def _decorator(func):
		@functools.wraps(func)
		def _wrapper(*args, **kw):
			r = func(*args, **kw)
			if isinstance(r, dict):
				return Template(path, **r)
			raise ValueError('Except return a dict when using @view() decorator.')
		return _wrapper
	return _decorator

_re_interceptor_starts_with = re.compile(r'^([^\*\?]+)\*?$')
_re_interceptor_ends_with = re.compile(r'^\*([^\*\?]+)$')

def _build_pattern_fn(pattern):
	m = _re_interceptor_starts_with.match(pattern)
	if m:
		return lambda p: p.startswith(m.group(1))
	m = _re_interceptor_ends_with.match(pattern)
	if m:
		return lambda p: p.endswith(m.group(1))
	raise ValueError('Invalid pattern definition in interceptor.')

def interceptor(pattern='/'):
	def _decorator(func):
		func.__interceptor__ = _build_pattern_fn(pattern)
		return func
	return _decorator

def _build_interceptor_fn(ince_fn, next):
	def _wrapper():
		if ince_fn.__interceptor__(ctx.request.path_info):
			return ince_fn(next)
		else:
			return next()
	return _wrapper

def _build_interceptor_chain(last_fn, *interceptors):
	L = list(interceptors)
	L.reverse()
	ls_fn = last_fn
	for ince_fn in L:
		ls_fn = _build_interceptor_fn(ince_fn, ls_fn)
	return ls_fn

def _load_module(module_name):
	last_dot = module_name.rfind('.')
	if last_dot == (-1):
		return __import__(module_name, globals(), locals())
	from_module = module_name[:last_dot]
	import_module = module_name[last_dot+1:]
	m = __import__(from_module, globals(), locals(), [import_module])
	return getattr(m, import_module)

class WSGIApplication(object):
	def __init__(self, document_root=None, **kw):
		self._document_root = document_root
		self._running = False
		self._template_engine = None
		self._interceptors = []
		self._get_static = {}
		self._post_static = {}
		self._put_static = {}
		self._delete_static = {}
		self._get_dynamic = []
		self._post_dynamic = []
		self._put_dynamic = []
		self._delete_dynamic = []

	def _check_not_running(self):
		if self._running:
			raise RuntimeError('Cannot modify when application running..')

	@property
	def template_engine(self):
		return self._template_engine
	@template_engine.setter
	def template_engine(self, engine):
		self._check_not_running()
		self._template_engine = engine

	def add_module(self, mod):
		self._check_not_running()
		m = mod if type(mod) == types.ModuleType else _load_module(mod)
		for att in dir(m):
			fn = getattr(m, att)
			if callable(fn) and hasattr(fn, '__web_method__') and hasattr(fn, '__web_route__'):
				self.add_url(fn)

	def add_url(self, func):
		self._check_not_running()
		route = Route(func)
		if route.is_static:
			if route.method == 'GET':
				self._get_static[route.path] = route
			if route.method == 'POST':
				self._post_static[route.path] = route
			if route.method == 'PUT':
				self._put_static[route.path] = route
			if route.method == 'DELETE':
				self._delete_static[route.path] = route
		else:
			if route.method == 'GET':
				self._get_dynamic.append(route)
			if route.method == 'POST':
				self._post_dynamic.append(route)
			if route.method == 'PUT':
				self._put_dynamic.append(route)
			if route.method == 'DELETE':
				self._delete_dynamic.append(route)
		logging.info('Add route: %s' % str(route))

	def add_interceptor(self, func):
		self._check_not_running()
		self._interceptors.append(func)
		logging.info('Add interceptor: %s' % str(func))

	def run(self, host='127.0.0.1', port=9002):
		from wsgiref.simple_server import make_server
		logging.info('application (%s) will start at %s:%s...' % (self._document_root, host, port))
		server = make_server(host, port, self.get_wsgi_app(debug=True))
		server.serve_forever()

	def get_wsgi_app(self, debug=False):
		self._check_not_running()
		if debug:
			self._get_dynamic.append(StaticFileRoute())
		self._running = True
		_application = Dict(document_root=self._document_root)

		def route_fn():
			request_method = ctx.request.request_method
			path_info = ctx.request.path_info
			if request_method == 'GET':
				fn = self._get_static.get(path_info, None)
				if fn:
					return fn()
				for fn in self._get_dynamic:
					args = fn.match(path_info)
					if args:
						return fn(*args)
				raise notfound()
			if  request_method == 'POST':
				fn = self._post_static.get(path_info, None)
				if fn:
					return fn()
				for fn in self._post_dynamic:
					args = fn.match(path_info)
					if args:
						return fn(*args)
				raise notfound()
			if request_method == 'PUT':
				fn = self._put_static.get(path_info, None)
				if fn:
					return fn()
				for fn in self._put_dynamic:
					args = fn.match(path_info)
					if args:
						return fn(*args)
				raise notfound()
			if request_method == 'DELETE':
				fn = self._delete_static.get(path_info, None)
				if fn:
					return fn()
				for fn in self._delete_dynamic:
					args = fn.match(path_info)
					if args:
						return fn(*args)
				raise notfound()
			raise badrequest()

		fn_exe = _build_interceptor_chain(route_fn, *self._interceptors)

		def wsgi(env, start_response):
			ctx.application = _application
			ctx.request = Request(env)
			response = ctx.response = Response()
			try:
				r = fn_exe()
				if isinstance(r, Template):
					r = self._template_engine(r.template_name, r.model)
				if isinstance(r, unicode):
					r = r.encode('utf-8')
				if r is None:
					r = []
				start_response(response.status, response.headers)
				return r
			except RedirectError, e:
				response.set_header('Location', e.location)
				start_response(e.status, response.headers)
				return []
			except HttpError, e:
				start_response(e.status, response.headers)
				return ['<html><body><h1>', e.status, '</h1></body></html>']
			except Exception, e:
				logging.exception(e)
				if not debug:
					start_response('500 Internal Server Error', [])
					return ['<html><body><h1>500 Internal Server Error</h1></body></html>']
				exc_type, exc_value, exc_traceback = sys.exc_info()
				fp = StringIO()
				traceback.print_exception(exc_type, exc_value, exc_traceback, file=fp)
				stacks = fp.getvalue()
				fp.close()
				start_response('500 Internal Server Error', [])
				return [
					r'''<html><body><h1>500 Internal Server Error</h1><div style="font-family:Monaco, Menlo, Consolas, 'Courier New', monospace;"><pre>''',
					stacks.replace('<', '&lt;').replace('>', '&gt;'),
					'</pre></div></body></html>'
				]
			finally:
				del ctx.application
				del ctx.request
				del ctx.response

		return wsgi