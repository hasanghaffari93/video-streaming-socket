import argparse
import socket
import selectors
import traceback
import libclient
import numpy as np
from camera import VideoShower

from datetime import datetime, timezone, timedelta



def main(args):
    
    sel = selectors.DefaultSelector()

    host = socket.gethostbyname(socket.gethostname()) 

    port = args.port


    request_description = {
        "action": "SendCamFrames",
        "format": "RTSP",
        "address": "http://77.222.181.11:8080/mjpg/video.mjpg",
        "samplingRate": 1,
        "webp": 25
    }


    video_shower = VideoShower()


    def start_connection(host, port, request_description):
        addr = (host, port)
        print(f"Starting connection to {addr}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.connect_ex(addr)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        video_shower.start()
        message = libclient.Message(sel, sock, addr, request_description, video_shower)
    #     message = lib.libclient.Message(sel, sock, addr, request_description, video_shower)       
        sel.register(sock, events, data=message) 


    start_connection(host, port, request_description)

    try:

        while True:

            events = sel.select(timeout=1)

            for key, mask in events:

                message = key.data

                try:

                    message.process_events(mask)

                except Exception:

                    print(
                        f"Main: Error: Exception for {message.addr}:\n"
                        f"{traceback.format_exc()}"
                    )

                    message.close()
                    video_shower.stop()

            # Check for a socket being monitored to continue.
            if not sel.get_map():
                break

    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")

    finally:
        sel.close()




if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--port",
        type=int,
        default=56000,
        help="port of connection",
    )

    parser.add_argument(
        '--cam_ids',
        nargs='+',
        type=int,
        default=[1, 2],
        help='camera IDs'
    )

    args = parser.parse_args()

    main(args)
