from shutil import ExecError
from signal import raise_signal
import sys
import selectors
import json
import io
import struct
import time
import copy

from camera import ManageFPS, CameraGetterCV2MP, ImageEncoding


class CameraHandler(Exception):
    pass


class Encode_Message:

    def encode_message(self, content, content_type, content_encoding, content_description):
        
        # Input Checker for content_type
        self.__content_types = ["json", "binary"]
        if not (content_type in self.__content_types):
            raise ValueError(f"content_type must be one of {self.__content_types}")

        # Input Checker for content_encoding
        self.content_encodings = ["utf-8"]
        if not (content_encoding in self.content_encodings):
            raise ValueError(f"content_encoding must be one of {self.content_encodings}")

        # Input Checker for content_description
        if type(content_description) is not dict:
            raise ValueError(f"content_description must be dict")

        for reqhdr in ["action"]:
            if reqhdr not in content_description:
                raise ValueError(f"Missing required key in content_description: '{reqhdr}'.")


        self.__content = content
        self.__content_type = content_type
        self.__content_encoding = content_encoding
        self.__content_description = content_description


        if self.__content_type == "json":
            self.__content_bytes = self.__json_encode(self.__content, self.__content_encoding)
        elif self.__content_type == "binary":
            self.__content_bytes = self.__content


        self.__jsonheader = {
            "content-type": self.__content_type,
            "content-encoding": self.__content_encoding,
            "content-length": len(self.__content_bytes),
            "content-description": self.__content_description
        } 

        self.__jsonheader_bytes = self.__json_encode(self.__jsonheader, "utf-8")


        self.__jsonheader_len = len(self.__jsonheader_bytes)
        self.__jsonheader_len_bytes = struct.pack(">L", self.__jsonheader_len)

        self.__message = self.__jsonheader_len_bytes + self.__jsonheader_bytes + self.__content_bytes

        self.__send_buffer = self.__message

        return self.__send_buffer


    def __json_encode(self, obj, encoding):
        # json is text (string)
        # json_str = json.dumps(obj) -->  python object to json string 
        # obj = json.loads(json_str) -->  json string to python object
        # Possible Objects: dict, list, tuple, string, int, float, True, False, None
        # 
        return json.dumps(obj, ensure_ascii=False).encode(encoding)



class Decode_Message:

    def __init__(self):

        self.jsonheader_len = None
        self.jsonheader = None
        self.content = None
        self.content_description = None
        self.content_type = None

    
    def decode_message(self, _recv_buffer):

        _recv_buffer = self.decode_jsonheader_len(_recv_buffer)
        _recv_buffer = self.decode_jsonheader(_recv_buffer)
        _recv_buffer = self.decode_content(_recv_buffer)

        print(
            f"Received {self.jsonheader} "
        )

        return _recv_buffer, self.content, self.content_description, self.content_type

    def decode_jsonheader_len(self, _recv_buffer):

        if self.jsonheader_len is None:
            hdrlen = 4
            if len(_recv_buffer) >= hdrlen:

                jsonheader_len_bytes = _recv_buffer[:hdrlen]
                _recv_buffer = _recv_buffer[hdrlen:]

                self.jsonheader_len = struct.unpack(">L", jsonheader_len_bytes)[0]

        return _recv_buffer

            

    def decode_jsonheader(self, _recv_buffer):

        if self.jsonheader_len is not None:
            if self.jsonheader is None:

                hdrlen = self.jsonheader_len

                if len(_recv_buffer) >= hdrlen:

                    jsonheader_bytes = _recv_buffer[:hdrlen]
                    _recv_buffer = _recv_buffer[hdrlen:]

                    self.jsonheader = self.__json_decode(jsonheader_bytes, "utf-8")

                    for reqhdr in ("content-type", "content-encoding", "content-length", "content-description"):
                        if reqhdr not in self.jsonheader:
                            raise ValueError(f"Missing required header '{reqhdr}'.")

        return _recv_buffer


    def decode_content(self, _recv_buffer):

        if self.jsonheader:
            if self.content is None:

                content_length = self.jsonheader["content-length"]
                self.content_type = self.jsonheader["content-type"]
                self.content_description = self.jsonheader["content-description"]


                if not len(_recv_buffer) >= content_length:
                    return _recv_buffer

                content_bytes = _recv_buffer[:content_length]
                _recv_buffer = _recv_buffer[content_length:]

                if self.content_type == "json":

                    content_encoding = self.jsonheader["content-encoding"]
                    self.content = self.__json_decode(content_bytes, content_encoding)

                elif self.content_type == "binary":
                    self.content = content_bytes
                else:
                    pass

        return _recv_buffer



    def __json_decode(self, json_bytes, encoding): # encoding = "utf-8"
        tiow = io.TextIOWrapper(
            io.BytesIO(json_bytes), encoding=encoding, newline=""
        )
        obj = json.load(tiow)
        tiow.close()
        return obj


 

class Message:

    def __init__(self, selector, sock, addr, cam):

        self.cam = cam
        
        self.selector = selector
        self.sock = sock
        self.addr = addr

        self._recv_buffer = b""
        self._send_buffer = b""

        self.Recieving_Message = Decode_Message()
        self.Sending_Message= Encode_Message()

        self.__isRequestRecieved = False


    def _set_selector_events_mask(self, mode):
        """Set selector to listen for events: mode is 'r', 'w', or 'rw'."""
        if mode == "r":
            events = selectors.EVENT_READ
        elif mode == "w":
            events = selectors.EVENT_WRITE
        elif mode == "rw":
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
        else:
            raise ValueError(f"Invalid events mask mode {mode!r}.")
        # self in data=self means the Message instance itself            
        self.selector.modify(self.sock, events, data=self)                          

    def _read(self):
        try:
            # Should be ready to read
            data = self.sock.recv(4096)
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        else:

            # ToDo: data?
            # Connection is     established and client is     sending data
            # Connection is     established and client is not sending data
            # Connection is not established
            if data:                                                               
                self._recv_buffer += data
            else:
                raise RuntimeError("Peer closed.")

    def _write(self):
        if self._send_buffer:
            print(f"Sending message to {self.addr}")
            try:
                # Should be ready to write
                sent = self.sock.send(self._send_buffer)
            except BlockingIOError:
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                pass
            else:
                self._send_buffer = self._send_buffer[sent:]

    def process_events(self, mask):

        # When a raw message (a request from client) is ready, this line will be run
        if mask & selectors.EVENT_READ:  
            self._read()
            self.process_request()

        # It seems that when EVENT_WRITE is selected, this line will always (?) be run
        if mask & selectors.EVENT_WRITE:
            self.process_response()
            self._write()

    def process_request(self):
        
        self._recv_buffer, request, request_description, request_type = self.Recieving_Message.decode_message(self._recv_buffer)

        if request is not None:

            ##################################################################
            if request_description["action"] == "SendCamFrames":

                if request_type != "binary":
                    raise TypeError("content-type for action 'SendCamFrames' must be binary")


                video_format = request_description["format"]

                if video_format == "RTSP":

                    cam_address = request_description["address"]
                    cam_SR = request_description["samplingRate"]
                    webp = request_description["webp"]


                    # cond1 = True #prev_resolution!=resolution
                    # cond2 = True# prev_cameraFPS!=cameraFPS
                    # cond3 = True #prev_samplingFPS!=samplingFPS
                    # cond4 = True #prev_webp!=webp
                    # cond5 = True #not all([(ID in IDs) for ID in prev_IDs])
                    # cond6 = True #not all([(ID in prev_IDs) for ID in IDs])
                    # cond = cond1 or cond2 or cond3 or cond4 or cond5 or cond6

                    # if cond:

                    print("New Camera Configuration...")

                    try:

                        # info = self.cam_info.get(IDs=IDs,
                        #                         resolution=resolution,
                        #                         showIDs=None,
                        #                         side=self.server_loc)
                        # self.cam.stop()

                        self.cam = CameraGetterCV2MP(ID="1", cam_address="http://77.222.181.11:8080/mjpg/video.mjpg") #Camera()
                        self.cam.start()
                        # self.cam.start(camera_info=info,
                        #             cameraFPS=cameraFPS,
                        #             samplingFPS=samplingFPS,
                        #             loggingTime=30,
                        #             webp=webp)

                        self.manageFPS = ManageFPS(cam_SR)

                    except:
                        print("An Error occured during camera configuration")
                        raise CameraHandler
                
                    # else:
                    #     print("Same Configuration for cameras...")


            else:
                # Other actions
                pass
            ##################################################################

            self.__isRequestRecieved = True
        

    def process_response(self):

        if self.__isRequestRecieved :

            ##################################################################

            if not (self.manageFPS.still_wait()):

                t1 = time.time()
                # areAllCamerasChecked, frames = self.cam.get_frames(encode_and_tobytes=True)
                frameIsAvailable, frame, _ = self.cam.getFrame()
                
                if frameIsAvailable:

                    frame_copy = copy.deepcopy(frame)

                    encoders = ImageEncoding()
                    encoders.start(frame_copy, True, 50)

                    encoders.stop()
                    frame_encoded = encoders.get_encoded()
                
                
                
                    t2 = time.time()

                

                    print("time of getting frames: ", round(t2-t1, 3))
                    
                    content = b''

                    frame_info = {
                        "length": len(frame_encoded)
                    }

                    content = content + frame_encoded

                    
                    content_description = {
                        "action": "HereIsFrame",
                        "frame-info": frame_info
                    }
                    ##################################################################


                    response_bytes = self.Sending_Message.encode_message(content = content, 
                                                                        content_type = "binary",
                                                                        content_encoding = "utf-8",
                                                                        content_description = content_description)

                    self._send_buffer += response_bytes

    
    def close(self):
        print(f"Closing connection to {self.addr}")

        try:
            self.selector.unregister(self.sock)
        except Exception as e:
            print(
                f"Error: selector.unregister() exception for "
                f"{self.addr}: {e!r}"
            )

        try:
            self.sock.close()
        except OSError as e:
            print(f"Error: socket.close() exception for {self.addr}: {e!r}")
        finally:
            # Delete reference to socket object for garbage collection
            self.sock = None

