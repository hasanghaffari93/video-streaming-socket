from threading import Thread
import cv2
import datetime
import time
import numpy as np
import queue
import os
import pytz
import copy
import logging
from PIL import Image 
import multiprocessing as mp
from utils import check_time, ManageFPS, TimeLoop, TimeStartStop



class ImageEncoding:

    def __init__(self):

        self.__img = np.array([])
        self.__newFrameIsAvailable = False
        self.__webp = 0
        self.__encoded = False
        self.__img_encoded_bytes = b''


    def start(self, img, newFrameIsAvailable, webp):

        if not isinstance(newFrameIsAvailable, bool):
            raise ValueError("newFrameIsAvailable must be a boolian")

        if (not isinstance(webp, int)) or webp<=0:
            raise ValueError("webp must be a positive integer")

        if not isinstance(img, np.ndarray):
            raise ValueError("img must be a numpy array")

        self.__img = img
        self.__newFrameIsAvailable = newFrameIsAvailable
        self.__webp = webp

        self.__t = Thread(target=self.__run, args=())
        self.__t.start()
        
    
    def stop(self):
        if not self.__encoded:
            self.__t.join()

    def get_encoded(self):
        if not self.__encoded:
            raise Exception
        return self.__img_encoded_bytes

    def __run(self):

        if self.__newFrameIsAvailable:
            # Takes long
            encode_param = [cv2.IMWRITE_WEBP_QUALITY, self.__webp]
            result, img_encoded = cv2.imencode(".webp", self.__img, encode_param)  # imgencode is an one axis uint-8 numpy array
            # img_encoded = np.array(img_encoded)
            self.__img_encoded_bytes = img_encoded.tobytes()  # it is b'...'

        else:
            self.__img_encoded_bytes = b''
        self.__encoded = True


class CameraGetterCV2MP:

    def __init__(self, ID, cam_address=0, fps=60, grab=False, loggingTime=5):

        if (not isinstance(fps, (int, float))) and fps <= 0:
            raise ValueError("fps must be a positive integer or float")

        if not isinstance(grab, bool):
            raise ValueError("grab must be a boolian")
        
        self.cam_address = cam_address
        self.grab = grab
        self.fps = fps
        self.ID = ID
        self.loggingTime = loggingTime

        # Variables
        self.frame_q = mp.Queue(1)
        self.cam_fps = mp.Queue(1)
        self.event = mp.Event()


    def start(self): 
        self.t = mp.Process(target=self.run, args=())
        self.t.start()
                            
        
    def run(self):

        connected = False
        print("INFO: Cam", self.ID, "initilized")

        cap = cv2.VideoCapture(self.cam_address)
        
        # manageFPSforLog = ManageFPS(fps = 1 / self.loggingTime) 
        manageFPS = ManageFPS(self.fps)
        
        timeLoop = TimeLoop()
        
        while True:

            # if not(manageFPSforLog.still_wait()):
                # _, FPS = timeLoop.get_DT_FPS()
                # print("INFO: Real FPS of Cam", self.ID, ":", str(FPS))       
            
            if manageFPS.still_wait():
                continue
            
            if not (cap.isOpened()):
                if connected:
                    connected = False
                    print("INFO: Cam", self.ID, "disconnected")  
                cap.release()
                cap = cv2.VideoCapture(self.cam_address)
                continue

                
            if self.grab: cap.grab()
                
            ret, frame = cap.read()
            
            if not ret:
                if connected:
                    connected = False
                    print("INFO: Cam", self.ID, "disconnected")   

                cap.release()
                cap = cv2.VideoCapture(self.cam_address)
                continue

            if not connected:
                connected = True
                print("INFO: Cam", self.ID, "connected")

            timeLoop.point()

            if self.frame_q.empty() and self.cam_fps.empty():
                self.frame_q.put(frame)
                _, FPS = timeLoop.get_DT_FPS()
                self.cam_fps.put(FPS)

            if self.event.is_set():
                break

        cap.release()
            
         
    def getFrame(self):
        if self.frame_q.full() and self.cam_fps.full():
            return True, self.frame_q.get(), self.cam_fps.get()
        else:
            return False, np.array([]), None

    def stop(self):
        self.event.set()
        self.t.terminate()
        self.t.join(2)
        self.t.kill()
        self.t.close()

        self.frame_q.close()
        self.cam_fps.close()

        self.frame_q.cancel_join_thread()
        self.cam_fps.cancel_join_thread()     



class VideoShower:

    def __init__(self):

        # Queue
        self.__q = mp.Queue(60)
        self.__stop_signal = mp.Queue(1)
        

    def start(self):
        # Set Thread
        self.__t = mp.Process(target=self.__show, args=())
        self.__t.start()

    def __show(self):

        while True:

            if not self.__q.empty():

                (frame, ID) = self.__q.get()
                    
                cv2.namedWindow(ID, cv2.WINDOW_NORMAL)
                cv2.imshow(ID, frame)
                cv2.waitKey(1)
            
            if cv2.waitKey(1)== 27:
                self.__stopped = True

            if self.__stop_signal.full():
                if self.__stop_signal.get():
                    break

        cv2.destroyAllWindows()
                    

    def newFrame(self, frame, ID):
        if self.__q.full():
            logging.warning('Not enough processing resources! Queue is full in Video Shower!')
            tmp = self.__q.get()
        self.__q.put((frame, ID))   

        
    def isStopped(self):
        return self.__stopped
        
    def stop(self):

        if self.__stop_signal.empty():
            self.__stop_signal.put(True)
            self.__t.join()
            

