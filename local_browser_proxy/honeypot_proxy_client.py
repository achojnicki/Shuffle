import socketio
from threading import Thread, Lock
from uuid import uuid4
from time import sleep
from pprint import pprint

from base64 import b64encode, b64decode

from engineio.payload import Payload
Payload.max_decode_packets = 20000

class TunnelClosedException(Exception):
	pass


class honeypot_proxy_client:
	def __init__(self):
		self._active=True
		self._url='ws://guiselink.com:8080/socket.io/'

		self._socketio=socketio.Client(logger=False, engineio_logger=False)
		self._socketio.on('response', namespace='/', handler=self._response)

		self._socketio.on('tunnel_recv', namespace='/', handler=self.tunnel_recv_socketio)
		self._socketio.on('tunnel_close', namespace='/', handler=self.tunnel_close_socketio)
		

		self._requests={}
		self._tunnels={}


		self._recv_lock=Lock()

		self.start()

	def _connect(self):
		self._socketio.connect(self._url, wait_timeout=60)

		self._socketio.emit('client_connect')


	def _response(self, message):
		#print('got response')
		self._requests[message['request_uuid']]=message

	def _build_message_get(self, request_url, request_uuid):
		return {"request_url": request_url, "request_uuid":str(request_uuid)}

	def _build_message_post(self, request_url, request_uuid):
		return {
			"request_url": request_url,
			"request_uuid":str(request_uuid),
			"post_data": post_data
			}

	def _build_message_tunnel(self, tunnel_uuid, tunnel_url=None, content=None):
		return {
			"tunnel_uuid": tunnel_uuid,
			"tunnel_url": tunnel_url,
			"content": content
		}

	def _open_HTTPS_connect(self, request_url, request_uuid):
		#print("HTTPS Connect Request")
		#print("Request UUID:",request_uuid)
		#print('Request URL:',request_url)
		#print('---')

		self._socketio.emit(
			'client_https_connect',
			self._build_message_get(
				request_uuid=request_uuid,
				request_url=request_url
				)
			)

	def _send_request_get(self, request_url, request_uuid):
		#print("GET Request")
		#print("Request UUID:",request_uuid)
		#print('Request URL:',request_url)
		#print('---')
		self._socketio.emit(
			'client_request_get',
			self._build_message_get(
				request_uuid=request_uuid,
				request_url=request_url
				)
			)


	def _send_request_post(self, request_url, request_uuid, post_data):
		#print("POST Request")
		#print("Request UUID:",request_uuid)
		#print('Request URL:',request_url)
		#print('---')
		self._socketio.emit(
			'client_request_post',
			self._build_message(
				request_uuid=request_uuid,
				request_url=request_url,
				post_data=post_data
				)
			)

	def _ping(self):
		while 1:
			self._socketio.emit('client_ping')
			sleep(1)

	def start(self):
		self._connect()
		t=Thread(target=self._ping)
		t.start()


	def get(self, address):
		request_uuid=str(uuid4())
		request_url=address

		self._send_request_get(
			request_uuid=request_uuid,
			request_url=request_url
			)
		while True:
			if request_uuid in self._requests:
				#print('ok')
				data=self._requests[request_uuid]
				del self._requests[request_uuid]
				return data
			#sleep(0.1)


	def create_tunel(self, tunnel_uuid, tunnel_url):
		self._tunnels[tunnel_uuid]={
			"tunnel_uuid": tunnel_uuid,
			"tunnel_url": tunnel_url,
			"recv_messages": [],
			"closed": False
		}

		self._socketio.emit(
			"tunnel_create",
			self._build_message_tunnel(
				tunnel_uuid=tunnel_uuid,
				tunnel_url=tunnel_url
				)
			)
		#sleep(0.5)



	def create_relay(self, address):
		tunnel_uuid=str(uuid4())
		tunnel_url=address

		self.create_tunel(
			tunnel_uuid=tunnel_uuid,
			tunnel_url=tunnel_url
			)
		return tunnel_uuid

	def tunnel_send(self, tunnel_uuid, content):
		self._socketio.emit(
			'tunnel_send',
			self._build_message_tunnel(
				tunnel_uuid=tunnel_uuid,
				content=b64encode(content))
			)
	

	def tunnel_recv_socketio(self, message):
		#print('tunnel recv socketio message:', message)
		if message['tunnel_uuid'] in self._tunnels:
			with self._recv_lock:
				self._tunnels[message['tunnel_uuid']]['recv_messages'].append(b64decode(message['content']))
		

	def tunnel_recv(self, tunnel_uuid):
		if tunnel_uuid in self._tunnels:
			messages=self._tunnels[tunnel_uuid]['recv_messages'].copy()
			with self._recv_lock:
				self._tunnels[tunnel_uuid]['recv_messages']=[]

				if self._tunnels[tunnel_uuid]['closed']:
					del self._tunnels[tunnel_uuid]
			return messages
		else:
			raise TunnelClosedException


	def tunnel_close_socketio(self, message):
		if message['tunnel_uuid'] in self._tunnels:
			with self._recv_lock:
				self._tunnels[message['tunnel_uuid']]['closed']=True


	def tunnel_close(self, tunnel_uuid):
		if tunnel_uuid in self._tunnels:
			self._socketio.emit(
				'tunnel_close',
				self._build_message_tunnel(
					tunnel_uuid=tunnel_uuid
				)
			)