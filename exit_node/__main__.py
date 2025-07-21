from threading import Thread, Event, Lock
import socketio
from time import sleep
from requests import get, post
from base64 import b64encode, b64decode
from select import select

from engineio.payload import Payload
Payload.max_decode_packets = 20000

import socket

SOCKETIO_URL='ws://localhost:8080/socket.io/'


class exit_node:
	def __init__(self, ):
		self._active=True
		self._tunnels={}

		self._lock=Lock()

		self._socketio=socketio.Client(logger=False, engineio_logger=False)

		self._socketio.on('request_get', namespace="/", handler=self.request_get)

		self._socketio.on('tunnel_create', namespace="/", handler=self.create_tunnel)
		self._socketio.on('tunnel_send', namespace="/", handler=self.send_tunel)
		self._socketio.on('tunnel_close', namespace="/", handler=self.close_tunel)
	def connect(self):
		self._socketio.connect(SOCKETIO_URL, wait_timeout=60, retry=True)

		self._socketio.emit('proxy_connect')

	def _ping(self):
		e=Event()
		while self._active:
			#print('ping')
			self._socketio.emit('proxy_ping')
			e.wait(timeout=1)

	def ping(self):
		t=Thread(target=self._ping, args=())
		t.start()

	def start(self):
		self.connect()
		self.ping()
		self.recv_tunnel_loop()
		self._socketio.wait()

	def build_message(self, request_uuid, request_url, content, encoding, server_headers):
		return {
			"request_uuid":request_uuid,
			"request_url": request_url,
			"content": content,
			"encoding": encoding,
			"server_headers": server_headers
			}

	def build_message_tunnel(self, tunnel_uuid, tunnel_url=None, status=None, content=None):
		return {
			"tunnel_uuid": tunnel_uuid,
			"tunnel_url": tunnel_url,
			"status": status,
			"content": content
		}

	def request_get(self, data):
		#print(f'got request, {data}')
		d=get(data['request_url'])
		headers=dict(d.headers)

		if "Content-Encoding" in headers:
			del headers['Content-Encoding']
		if 'Transfer-Encoding' in headers:
			del headers['Transfer-Encoding']
		if 'Connection' in headers and headers['Connection'].lower()=='keep-alive':
			del headers['Connection']

		if 'Content-Length' in headers:
			headers['Content-Length']=len(d.content)

		#print(d.text)

		#print('\n')
		self._socketio.emit(
			'proxy_response_get',
			self.build_message(
				request_uuid=data['request_uuid'],
				request_url=data['request_url'],
				content=b64encode(d.content),
				encoding=d.encoding,
				server_headers=headers
				),
			namespace="/")


	def create_tunnel(self, message):
		print(f'Creating tunnel with address {message['tunnel_url']} {message['tunnel_uuid']}')
		address = message['tunnel_url'].split(':', 1)
		address[1] = int(address[1]) or 443
		connection=socket.create_connection(address, timeout=5)

		self._tunnels[message['tunnel_uuid']]={
			"tunnel_uuid": message['tunnel_uuid'],
			"tunnel_url": message['tunnel_url'],
			"connection": connection
		}


	def recv_tunnel_loop(self):
		t=Thread(target=self._recv_tunnel_loop, args=[])
		t.start()


	def _recv_tunnel_loop(self):
		while self._active:
			try:
				for tunnel in self._tunnels.copy():
					connection=self._tunnels[tunnel]['connection']
					r, w, x = select([connection], [],[connection], 0.00001)
					if x:
						print('Connection exceptional condition', self._tunnels[tunnel]['tunnel_uuid'])
						self._socketio.emit(
							"tunnel_close",
							self.build_message_tunnel(
								tunnel_uuid=tunnel,
								status="Close"
								))
					else:
						if r:
							print('read stream true', self._tunnels[tunnel]['tunnel_uuid'])
							for r_item in r:
								#print(connection, type(connection))
								data=connection.recv(16384)

								if not data:
									print('empty response from socket', self._tunnels[tunnel]['tunnel_uuid'])
									self._socketio.emit(
										"tunnel_close",
										self.build_message_tunnel(
											tunnel_uuid=tunnel,
											))

								else:
									print('sending data to client', self._tunnels[tunnel]['tunnel_uuid'])
									encoded=b64encode(data)
									self._socketio.emit(
										'tunnel_recv',
										self.build_message_tunnel(
											tunnel_uuid=tunnel,
											status="Ok",
											content=encoded))
				#sleep(0.01)
			except Exception as e:
				print('Exception during attempt to read data from socket', self._tunnels[tunnel]['tunnel_uuid'], e)
				#print(e)
				with self._lock:
					if tunnel in self._tunnels:
						self._socketio.emit("tunnel_close",
							self.build_message_tunnel(
								tunnel_uuid=tunnel,
								status="Close"
							))


	def send_tunel(self, message):
		if message['tunnel_uuid'] in self._tunnels:
			print('sending data from client', message['tunnel_uuid'])
			connection=self._tunnels[message['tunnel_uuid']]['connection']
			data=b64decode(message['content'])

			try:
				connection.sendall(data)
			except:
				with self._lock:
					del self._tunnels[message['tunnel_uuid']]
				self._socketio.emit("tunnel_close",
					self.build_message_tunnel(
						tunnel_uuid=message['tunnel_uuid'],
						status="Close"
					))

	def close_tunel(self, message):
		with self._lock:
			if message['tunnel_uuid'] in self._tunnels:
				print('closing connection due to tunnel close signal', message['tunnel_uuid'])
				self._tunnels[message['tunnel_uuid']]['connection'].close()
				del self._tunnels[message['tunnel_uuid']]

if __name__=="__main__":
	app=exit_node()
	app.start()