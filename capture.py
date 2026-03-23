import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 11000))

data = b""
while True:
    chunk = sock.recv(4096)
    data += chunk
    if b"\n" in data:
        line, data = data.split(b"\n", 1)
        state = json.loads(line)
        print(state)