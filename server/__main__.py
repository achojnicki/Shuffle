from eventlet import wsgi, monkey_patch
from json import loads, dumps
from time import sleep, time
from uuid import uuid4
from random import randint

monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO

from engineio.payload import Payload


import functools


LISTEN_IP='127.0.0.1'
LISTEN_PORT=8080

class socketio_dispatcher:
    def __init__(self, application, socketio):
        self.application=application
        self.socketio=socketio



        self.application.config['SECRET_KEY'] = "asdfghgseresrhygsae"


        self._requests={}
        self._proxies={}
        self._clients={}
        self._tunnels={}

        self.bind_socketio_events()

    def start(self):
        self.socketio.start_background_task(target=self._proxy_checker)
        self.socketio.start_background_task(target=self._client_checker)
        self.socketio.run(self.application, host=LISTEN_IP, port=LISTEN_PORT)

    def _find_proxy(self):
        if len(self._proxies)>0:
            proxies=list(self._proxies.keys())
            return self._proxies[proxies[randint(0,len(proxies)-1)]]

    def _proxy_checker(self):
        while True:
            try:
                for proxy in self._proxies:
                    if self._proxies[proxy]['last_ping']:
                        if time() - self._proxies[proxy]['last_ping']>=2:
                            print('removing proxy', self._proxies[proxy]['sid'])
                            del self._proxies[proxy]
                self.socketio.sleep(0.1)
            except RuntimeError:
                pass

    def _client_checker(self):
        while True:
            try:
                for client in self._clients:
                    if self._clients[client]['last_ping']:
                        if time() - self._clients[client]['last_ping']>=2:
                            print('removing client', self._clients[client]['sid'])
                            del self._clients[client]
                self.socketio.sleep(0.1)
            except RuntimeError:
                pass

    def _connect(self):
        print("connect", request.sid)

    def _proxy_ping(self):
        if request.sid in self._proxies:
            self._proxies[request.sid]['last_ping']=time()
            #print('proxy_ping')
    
    def _client_ping(self):
        if request.sid in self._clients:
            self._clients[request.sid]['last_ping']=time()
            #print('client_ping')

    def _proxy_connect(self):
        self._proxies[request.sid]={"sid": request.sid, "last_ping": None}

        print('proxy_connect', request.sid)

    def _client_connect(self):
        self._clients[request.sid]={"sid": request.sid, "last_ping": None}

        print('client_connect', request.sid)


    def _build_response_message_get(self,request_uuid, request_url, status, server_headers=None, encoding=None, message=None, content=None):
        return {
            "request_uuid": request_uuid,
            "request_url": request_url,
            "status": status,
            "message": message,
            "content": content,
            "encoding": encoding,
            "server_headers":server_headers
        }
    def _build_response_message_post(self,request_uuid, request_url, status,server_headers=None,post_data=None, encoding=None, message=None, content=None):
        return {
            "request_uuid": request_uuid,
            "request_url": request_url,
            "status": status,
            "message": message,
            "content": content,
            "encoding": encoding,
            "server_headers":server_headers,
            "post_data": post_data
        }

    def _build_message_tunnel(self, tunnel_uuid, tunnel_url=None, status=None, content=None):
        return {
            "tunnel_uuid": tunnel_uuid,
            "tunnel_url": tunnel_url,
            "status": status,
            "content": content
        }

    def _client_request_get(self, message):
        self._requests[message['request_uuid']]={
            "request_uuid": message['request_uuid'],
            "request_url": message['request_url'],
            "request_status": "waiting",
            "client_sid": request.sid
        }

        proxy=self._find_proxy()
        if proxy:
            self.socketio.emit('request_get', message, to=proxy['sid'])
        else:
            self.socketio.emit(
                'response',
                 self._build_response_message_get(
                    request_uuid=message['request_uuid'],
                    request_url=message['request_url'],
                    status="Error",
                    message="No avaiable proxy servers"
                 ),
                 to=request.sid)

    def _client_request_post(self, message):
        self._requests[message['request_uuid']]={
            "request_uuid": message['request_uuid'],
            "request_url": message['request_url'],
            "request_status": "waiting",
            "client_sid": request.sid
        }

        proxy=self._find_proxy()
        if proxy:
            self.socketio.emit('request_post', message, to=proxy['sid'])
        else:
            self.socketio.emit(
                'response',
                 self._build_response_message_post(
                    request_uuid=message['request_uuid'],
                    request_url=message['request_url'],
                    status="Error",
                    message="No avaiable proxy servers"
                 ),
                 to=request.sid)
            
    def _proxy_response_get(self, message):
        #print(f'got response: {message}')
        if message['request_uuid'] in self._requests:
            self.socketio.emit(
                'response',
                self._build_response_message_get(
                    request_uuid=message['request_uuid'],
                    request_url=message['request_url'],
                    status="Success",
                    message="Success",
                    content=message['content'],
                    server_headers=message['server_headers']
                    )
                )

    def _proxy_response_post(self, message):
        #print(f'got response: {message}')
        if message['request_uuid'] in self._requests:
            self.socketio.emit(
                'response',
                self._build_response_message_get(
                    request_uuid=message['request_uuid'],
                    request_url=message['request_url'],
                    status="Success",
                    message="Success",
                    content=message['content'],
                    server_headers=message['server_headers'],
                    post_data=message['post_data']
                    )
                )


    def _tunnel_create(self, message):
        print('tunnel_create', message)
        exit_node=self._find_proxy()
        self._tunnels[message['tunnel_uuid']]={
            "tunnel_uuid": message['tunnel_uuid'],
            "tunnel_url": message['tunnel_url'],
            "exit_node": exit_node,
            "client": request.sid
        }

        self.socketio.emit(
            "tunnel_create", 
            self._build_message_tunnel(
                tunnel_uuid=message['tunnel_uuid'],
                tunnel_url=message['tunnel_url']
                ),
            to=exit_node['sid'])

    def _tunnel_send(self, message):
        print('tunnel_send', f"tunnel_uuid: {message['tunnel_uuid']}")
        exit_node=self._tunnels[message['tunnel_uuid']]['exit_node']
        self.socketio.emit(
            "tunnel_send",
            self._build_message_tunnel(
                tunnel_uuid=message['tunnel_uuid'],
                content=message['content']
                ),
            to=exit_node['sid']
            )

    def _tunnel_recv(self, message):
        print('tunnel_recv', f"tunnel_uuid: {message['tunnel_uuid']}")
        client=self._tunnels[message['tunnel_uuid']]['client']

        self.socketio.emit(
            "tunnel_recv",
            self._build_message_tunnel(
                tunnel_uuid=message['tunnel_uuid'],
                content=message['content']
                ),
            to=client
            )

    def _tunnel_close(self, message):
        print('tunnel_close', message)

        if message['tunnel_uuid'] in self._tunnels:
            client=self._tunnels[message['tunnel_uuid']]['client']
            exit_node=self._tunnels[message['tunnel_uuid']]['exit_node']

            self.socketio.emit(
                'tunnel_close',
                self._build_message_tunnel(
                    tunnel_uuid=message['tunnel_uuid']
                    ),
                to=client
                )

            self.socketio.emit(
                'tunnel_close',
                self._build_message_tunnel(
                    tunnel_uuid=message['tunnel_uuid']
                    ),
                to=exit_node['sid']
                )
        

    def bind_socketio_events(self):
        self.socketio.on_event('connect', self._connect, namespace="/")
        self.socketio.on_event('proxy_connect', self._proxy_connect, namespace="/")
        self.socketio.on_event('client_connect', self._client_connect, namespace="/")

        self.socketio.on_event('proxy_ping', self._proxy_ping, namespace="/")
        self.socketio.on_event('client_ping', self._client_ping, namespace="/")

        self.socketio.on_event('client_request_get', self._client_request_get, namespace="/")
        self.socketio.on_event('client_request_post', self._client_request_post, namespace="/")
        self.socketio.on_event('proxy_response_get', self._proxy_response_get, namespace="/")
        self.socketio.on_event('proxy_response_post', self._proxy_response_post, namespace="/")
        
        self.socketio.on_event('tunnel_create', self._tunnel_create, namespace="/")
        self.socketio.on_event('tunnel_send', self._tunnel_send, namespace="/")
        self.socketio.on_event('tunnel_recv', self._tunnel_recv, namespace="/")
        self.socketio.on_event('tunnel_close', self._tunnel_close, namespace="/")





if __name__=="__main__":
    app = Flask(__name__)
    Payload.max_decode_packets = 5000
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        max_http_buffer_size=200 * 1024 * 1024)

    socketio_dispatcher=socketio_dispatcher(app, socketio)
    socketio_dispatcher.start()
