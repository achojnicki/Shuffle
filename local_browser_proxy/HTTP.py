from honeypot_proxy_client import honeypot_proxy_client, TunnelClosedException
from base64 import b64decode
from select import select
from time import sleep


import http.server
import socketserver

LISTEN_ADDR='localhost'
LISTEN_PORT=8082

proxy=honeypot_proxy_client()

# Define the handler for the proxy
class SimpleHTTPProxy(http.server.BaseHTTPRequestHandler):
    """def do_GET(self):
        # Extract the URL from the request
        target_url = self.path        
        # Make a request to the target server
        response = proxy.get(target_url)

        # Forward the response back to the client
        self.send_response(200)
        #for header, value in response.headers.items():
        #    self.send_header(header, value)
        for header in response['server_headers']:
            print('\t',header,response['server_headers'][header])
            self.send_header(header, response['server_headers'][header])
        self.end_headers()

        data=b64decode(response['content'])
        self.wfile.write(data)"""

    """def do_POST(self):
        length = int(self.headers.get('content-length'))
        field_data = self.rfile.read(length)
        fields = parse.parse_qs(str(field_data,"UTF-8"))

        print(fields)"""

    def do_CONNECT(self):
        address=self.path
        tunnel_uuid=proxy.create_relay(self.path)
        sleep(0.1)
        self.connect_relay(tunnel_uuid)

        
    def connect_relay(self, tunnel_uuid):
        self.send_response(200, 'Connection Established')
        self.end_headers()

        self.close_connection = 0

        while not self.close_connection:
            r, w, x = select([self.connection], [], [self.connection], 0.00001)
            if x:
                self.close_connection=1
                break
            if r:
                for r_item in r:
                    try:
                        data = self.connection.recv(16384)
                        if not data:
                            self.close_connection = 1
                            break
                        else:
                            proxy.tunnel_send(tunnel_uuid, content=data)
                    except:
                        self.close_connection=1
                        break

            try:
                recv_data=proxy.tunnel_recv(tunnel_uuid)

            except TunnelClosedException:
                break
        
            for d in recv_data:
                #print('data', d)
                try:
                    self.wfile.write(d)
                    self.wfile.flush()
                except:
                    self.close_connection=1

        proxy.tunnel_close(tunnel_uuid)

def run_proxy_server():
    with socketserver.ThreadingTCPServer((LISTEN_ADDR, LISTEN_PORT), SimpleHTTPProxy) as httpd:
        print(f"Serving HTTP proxy on port {LISTEN_PORT}...")
        httpd.serve_forever()

if __name__ == "__main__":
    run_proxy_server()

