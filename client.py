#!/usr/bin/env python3
import asyncio
import aioconsole
import argparse
import pathlib
import contextlib
import socket
import ssl
import shared
import threading
import termios
import sys

parser = argparse.ArgumentParser(
                    prog='tlsh',
                    description='tlsh Client',
                    epilog='Created by stanleymw')

parser.add_argument('hostname')

parser.add_argument('certificate', type=pathlib.Path)
parser.add_argument('key', type=pathlib.Path)

parser.add_argument("-p", "--port", type=int, default = 3750)
args = parser.parse_args()
print(args)

ssl_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)

ssl_context.load_cert_chain(str(args.certificate), str(args.key))
ssl_context.load_verify_locations(cafile="LocalCA/ca_cert.pem") # TODO: let client specify localCA

# Self Signed certificate
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_REQUIRED

@contextlib.contextmanager
def raw_mode(file):
    old_attrs = termios.tcgetattr(file.fileno())
    new_attrs = old_attrs[:]
    new_attrs[3] = new_attrs[3] & ~(termios.ECHO | termios.ICANON)
    try:
        termios.tcsetattr(file.fileno(), termios.TCSADRAIN, new_attrs)
        yield
    finally:
        termios.tcsetattr(file.fileno(), termios.TCSADRAIN, old_attrs)

async def printReads(reader, astdout):
    while (data := await reader.read(8192)):
        #shared.notify(f"Received: {data.decode()}")
        astdout.write(data)
        await astdout.drain()
        #sys.stdout.buffer.write(data)
        #sys.stdout.flush()

async def sendMessage(writer, astdin):
    while True:
        #msg = await aioconsole.ainput("")
        msg = await astdin.read(1)
        if (writer.is_closing()):
            return
        writer.write(msg)
        await writer.drain()

async def main():
    # Create Connection
    reader, writer = await asyncio.open_connection(
        args.hostname, args.port, ssl=ssl_context)
    shared.notify("Connection opened!")

    # Start Send Loop
    # Start Read Loop
    astdin, astdout = await aioconsole.get_standard_streams()

    await asyncio.gather(sendMessage(writer, astdin), printReads(reader, astdout))

    shared.notify("Closing connection")
    writer.close()
    await writer.wait_closed()

if __name__ == "__main__":
    with raw_mode(sys.stdin):
        asyncio.run(main())
