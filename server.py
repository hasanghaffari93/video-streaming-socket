import argparse
import socket
import selectors
import traceback

import libserver
from camera import CameraGetterCV2MP
from libserver import CameraHandler



def main(args):
    cam = CameraGetterCV2MP(ID="1", cam_address="http://77.222.181.11:8080/mjpg/video.mjpg")
    # cam_info = CameraInfoArsam()

    sel = selectors.DefaultSelector()


    def accept_wrapper(sock):
        conn, addr = sock.accept()  # Should be ready to read
        print(f"Accepted connection from {addr}")
        conn.setblocking(False)

        message = libserver.Message(sel, conn, addr, cam)
        sel.register(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=message)
        # (HSN) After connection, server would be waiting for a request from client
        # sel.register(conn, selectors.EVENT_READ, data=message)

    # Get the local ip of this device and only other programs (as clients) in this device can connect to this program (as server) 
    # host = socket.gethostbyname(socket.gethostname())

    # This is an ip through which every device (as clients) on the local network via LAN and WIFI can connect to this program (as server)
    host = '0.0.0.0'


    port = args.port


    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Avoid bind() exception: OSError: [Errno 48] Address already in use
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((host, port))
    lsock.listen()
    print(f"Server is listening on {(host, port)}")
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)

    try:

    # """
    # you’ll see that sel.select() is in the driver’s seat. It’s blocking, waiting at 
    # the top of the loop for events. It’s responsible for waking up when read and write 
    # events are ready to be processed on the socket. Which means, indirectly, it’s also 
    # responsible for calling the method .process_events().
    # """

        while True:

            events = sel.select(timeout=None)

            for key, mask in events:

                if key.data is None:
                    # This section would be executed if a client wants to connect
                    accept_wrapper(key.fileobj)
                    
                else:
                    # This section would be executed if a client sends data
                    message = key.data                                                          # message
                    
                    try:
                        # Core:
                        message.process_events(mask)                                            # message


                    except CameraHandler:

                        print("Reseting Cameras!")
                        cam = CameraGetterCV2MP(ID="1", cam_address="http://77.222.181.11:8080/mjpg/video.mjpg")

                        message.close()
                        
                    except:
                        print(
                            f"Main: Error: Exception for {message.addr}:\n"
                            f"{traceback.format_exc()}"
                        )
                        cam = message.cam
                        # cam_info = message.cam_info
                        
                        message.close()
                        

    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")

        
    finally:
        sel.close()



if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--server_loc",
        type=str,
        default="Robokids",
        help="one of Robokids or Company",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=56000,
        help="port of connection",
    )

    args = parser.parse_args()

    main(args)

