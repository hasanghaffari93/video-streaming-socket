import sys
import selectors
import json
import io
import struct
import numpy as np
import cv2
from collections import defaultdict
import copy
import time


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
    

    def __init__(self, selector, sock, addr, request_description, video_shower):

        self.video_shower = video_shower
        
        self.cap_idx = 0

        self.selector = selector
        self.sock = sock
        self.addr = addr

        self._recv_buffer = b""
        self._send_buffer = b""
        
        self.Recieving_Message = Decode_Message()
        self.Sending_Message= Encode_Message()

        self.request_description = request_description
        self.__isRequestSent = False


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
        self.selector.modify(self.sock, events, data=self)

    def _read(self):
        try:
            # Should be ready to read
            data = self.sock.recv(4096)
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        else:
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
        if mask & selectors.EVENT_READ:
            self._read()
            self.process_response()

        if mask & selectors.EVENT_WRITE:
            self.process_request()
            self._write()

    def process_response(self):

        self._recv_buffer, response, response_description, response_type = self.Recieving_Message.decode_message(self._recv_buffer)
        
        if response is not None:

        
            #################################################################
            if response_description["action"] == "HereIsFrame":
                if response_type != "binary":
                    raise TypeError("content-type for action 'HereIsFrame' must be binary")

                if not ("frame-info" in response_description):
                    raise ValueError("frame-info is not in response_description")
                
                print( f"Received message: {len(response)//1000} KB from {self.addr} ")
                
        

                t1 = time.time()


                length = response_description["frame-info"]["length"]


                img_encoded_bytes = response[:length]
                response = response[length:]


                img_encoded = np.frombuffer(img_encoded_bytes, dtype='uint8')
                img_BGR = cv2.imdecode(img_encoded,1)
                
                
                self.video_shower.newFrame(img_BGR, "1")
                

                print("time of getting images:", time.time() - t1)
                            
                        
            else:
                pass

            self.Recieving_Message = Decode_Message()
            self.response = None
            ##################################################################

    def process_request(self):
        if not self.__isRequestSent:

            request_bytes = self.Sending_Message.encode_message(content = b'nothing', 
                                                                content_type = "binary",
                                                                content_encoding = "utf-8",
                                                                content_description = self.request_description)
            self._send_buffer += request_bytes
            self.__isRequestSent = True       
        
        if self.__isRequestSent:
            if not self._send_buffer:
                # Set selector to listen for read events, we're done writing.
                self._set_selector_events_mask("r")


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
