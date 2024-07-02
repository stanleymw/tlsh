#!/usr/bin/env python3
import socket
import asyncio
import tomllib
import shared
import ssl
import sys
import time
import subprocess

config = None
with open("tlshd.toml", "rb") as config_file:
    config = tomllib.load(config_file)

assert config != None

#ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH, capath=config["auth"]["authorized_certificates"])

ssl_context.load_cert_chain(config["ssl"]["cert"], config["ssl"]["key"])

ssl_context.verify_mode = ssl.CERT_REQUIRED

#ssl_context.load_verify_locations(capath="./authorized_certs/")
#ssl_context.load_verify_locations(cafile="c_cert.pem")

#ssl_context.check_hostname = False
#ssl_context.verify_mode = ssl.CERT_NONE

class Client():
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    async def send(self, data: bytes):
        writer = self.getWriter()
        writer.write(data)
        await writer.drain()

    async def receive(self, size: int):
        return await self.getReader().read(size)

    def getReader(self):
        return self.reader

    def getWriter(self):
        return self.writer

    # returns (ip, port) tuple of the peer
    def getName(self):
        return self.writer.get_extra_info("peername")

    def __str__(self):
        return str(self.getName())

async def proxy_user_to_server(peer, server_writer, tg):
    while (data := await peer.receive(config["bufsize"])):
        # shared.notify(f"Got {len(data)} bytes from {peer}: {data}");

        #shared.notify(f"user -> server: {data}")
        server_writer.write(data)
        await server_writer.drain()
    print("user -> server KILLED!")

    # TODO: change if Python adds support for aborting task group without using internal method
    tg._abort();

async def proxy_server_to_user(peer, server_reader, tg):
    while (data := await server_reader.read(config["bufsize"])):
        # shared.notify(f"Sending {len(data)} bytes back");
        #shared.notify(f"server -> user: {data}")
        await peer.send(data)
    print("server -> user KILLED!")

    # TODO: change if Python adds support for aborting task group without using internal method
    tg._abort();

async def handle_client(reader, writer):
    # This function is called when a new client is connected

    # reader to read data from the client
    # writer to send data to the client
    peer = Client(reader, writer)
    shared.notify(f"New Connection from {peer}")
    shared.notify(f"Peer cert: {writer.get_extra_info('peercert')}")

    # Connect to Bash server for this client
    bash_reader, bash_writer = await asyncio.open_unix_connection("./bash.sock")

    shared.notify("Shell connected!")
    await peer.send(b"[+] Shell connected!\n")

    async with asyncio.TaskGroup() as tg:
        u_to_s = tg.create_task(proxy_user_to_server(peer, bash_writer, tg))
        s_to_u = tg.create_task(proxy_server_to_user(peer, bash_reader, tg))

    shared.notify("Connection closed.")

    writer.close()
    await writer.wait_closed()

async def main():
    # Entrypoint: Start the server and listen for clients
    bind_addr = config["bind"]["ip"]
    bind_port = config["bind"]["port"]

    # Start bash server
    # TODO: define unix socket location in the Config file
    subprocess.Popen(["socat", "UNIX-LISTEN:./bash.sock,reuseaddr,fork", "shell:\"bash -i\",pty,stderr,setsid,sigint,sane"])

    shared.notify("Bash server started")

    server = await asyncio.start_server(
        handle_client, bind_addr, bind_port, ssl=ssl_context)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)

    shared.notify(f'Serving on {addrs}')

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
