from datetime import datetime, timezone, timedelta
import time
import base64
import requests
from io import BytesIO
import multiprocessing as mp
import os
from pathlib import Path
import cv2
from threading import Thread
from PIL import Image
import numpy as np



class ManageFPS:
    
    def __init__(self, fps=1):


        if (not isinstance(fps, (float, int))) or fps  <= 0:
            raise ValueError("fps must be int or float, and larger than 0")
        
        self.DT = 1 / fps
        self.T1 = time.time()
        
    def still_wait(self):
        
        self.T2 = time.time()
        self.dT = self.T2 - self.T1
        
        if self.dT < self.DT:
            return True
        else:
            self.T1 = self.T2
            return False
        
        
class TimeLoop:
    
    def __init__(self, iteration=20):

        if (not isinstance(iteration, int)) and iteration <= 0:
            raise ValueError("iteration must be a positive integer")
        
        self.__dt_list = []
        self.__t_prev = time.time()
        self.__iteration = iteration
        self.__DT = 0
        self.__FPS = 0
        
    def point(self):
        
        self.__t_curr = time.time()
        self.__dt = self.__t_curr - self.__t_prev
        self.__t_prev = self.__t_curr
        if len(self.__dt_list) == self.__iteration: del self.__dt_list[0]
        self.__dt_list.append(self.__dt)
        self.__DT = sum(self.__dt_list)/len(self.__dt_list)        
        self.__FPS = 1 / self.__DT
        
                
    def get_DT_FPS(self):
        return round(self.__DT, 2), round(self.__FPS, 2)
    
        
class TimeStartStop:
    
    def __init__(self, iteration=20):

        if (not isinstance(iteration, int)) and iteration<=0:
            raise ValueError("iteration must be a positive integer")  

        self.__dt_list = []
        self.__iteration = iteration
        self.__DT = 0
        
    def start(self):
        self.__t_start = time.time()

    def stop(self):
        
        self.__t_stop = time.time()
        self.__dt = self.__t_stop - self.__t_start
        if len(self.__dt_list) == self.__iteration: del self.__dt_list[0]
        self.__dt_list.append(self.__dt)
        self.__DT = sum(self.__dt_list)/len(self.__dt_list)

    
    def getTime(self):
        return round(self.__DT, 2)




def check_time(h1, m1, h2, m2):

    now = datetime.now(timezone.utc)

    t1 = now.replace(hour=h1, minute=m1, second=0)
    t2 = now.replace(hour=h2, minute=m2, second=0)

    if t1 < now < t2:
        return True
    else:
        return False


class WorkingPeriod:
    
    def __init__(self, hour_start=10, hour_stop = 21):


        if (not isinstance(hour_start, int)) or (not isinstance(hour_stop, int)):
            raise ValueError("start and stop hours must be int")

        if hour_start < 0 or hour_start > 23 or hour_stop < 0 or hour_stop > 23:
            raise ValueError("start and stop hours must be between 0 and 23")
        
        self.hour_start = hour_start
        self.hour_stop = hour_stop
        
        
    def NotInTime(self):
        
        hour = datetime.datetime.now(timezone.utc).hour  
        if hour < self.hour_start or hour > self.hour_stop:
            return True

def getDateTime(dateORtime):

    current_time = datetime.datetime.now(timezone.utc)

    year = current_time.year
    month = current_time.month
    day = current_time.day
    hour = current_time.hour
    minute = current_time.minute
    second = current_time.second
    microsecond = current_time.microsecond

    date = str(year) + "." + str(month) + "." + str(day)

    time = str(hour) + "." + str(minute) + "." + str(second) + str(microsecond)
        
    if dateORtime == "date":
        return date
    elif dateORtime == "time":
        return time
    elif dateORtime == "datetime":
        return date + "_" + time
    else:
        raise("dateORtime must be date or time or datetime")


def getDateTimeSTR():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")[2:-4]



class measure_time:
    
    def __init__(self):
        self.points = {}
        
    def start(self, point):
        self.points[point] = {}
        self.points[point]['start'] = time.time()
        
    def stop(self, point):
        self.points[point]['stop'] = time.time()
        
    def show(self):
        
        for point in self.points.keys():
            
            print('Time of ' + point + ' =', round(self.points[point]['stop'] - self.points[point]['start'], 4))
            

class InregratedCameraLogger:
    
    def __init__(self):
        
        self.cameras = {}
        self.log = ''
                
        
    def initialize(self, cam):


        current_DT = self.get_current_DT()
        cam = str(cam)
        
        self.cameras[cam] = {
            "prev_connected_DT": current_DT,
            "prev_disconnected_DT": current_DT,
            "total_connected_period": current_DT-current_DT,
            "total_disconnected_period": current_DT-current_DT,
            "isConnected": False,
            "log": ''
        }
        
        self.add_log('Initialized', cam)
        
    
    def connected(self, cam):
        
        cam = str(cam)
        self.camInCameras(cam)
        
        current_DT = self.get_current_DT()
        
        if not (self.cameras[cam]["isConnected"]):
            
            disconnected_period = current_DT - self.cameras[cam]["prev_disconnected_DT"]
            self.cameras[cam]["total_disconnected_period"] += disconnected_period
            self.cameras[cam]["prev_connected_DT"] = current_DT
            self.add_log('Connected', cam)
            
        self.cameras[cam]["isConnected"] = True
        
    
    def disconnected(self, cam):
        
        cam = str(cam)
        self.camInCameras(cam)
        
        current_DT = self.get_current_DT()
        
        if self.cameras[cam]["isConnected"]:
            
            connected_period = current_DT - self.cameras[cam]["prev_connected_DT"]
            self.cameras[cam]["total_connected_period"] += connected_period
            self.cameras[cam]["prev_disconnected_DT"] = current_DT
            self.add_log('Disconnected', cam)
            
        self.cameras[cam]["isConnected"] = False
        
        
    def terminate(self, cam):
        
        cam = str(cam)
        self.camInCameras(cam)
        
        current_DT = self.get_current_DT()
        
        if self.cameras[cam]["isConnected"]:
            
            connected_period = current_DT - self.cameras[cam]["prev_connected_DT"]
            self.cameras[cam]["total_connected_period"] += connected_period
            
        else:
            
            disconnected_period = current_DT - self.cameras[cam]["prev_disconnected_DT"]
            self.cameras[cam]["total_disconnected_period"] += disconnected_period
            
        text = 'Terminated\n\n' + \
               'Total connected time: ' + str(self.cameras[cam]["total_connected_period"])[:-4] + '\n' + \
               'Total disconnected time: ' + str(self.cameras[cam]["total_disconnected_period"])[:-4] + '\n'
        
        self.add_log(text, cam)
        
        
    def get_current_DT(self):
        return datetime.datetime.now(timezone.utc)
    
    
    def camInCameras(self, cam):
        if not (cam in self.cameras):
            raise Exception("cam is not initialized")

 
        
    def add_log(self, log, cam, show_log=True):
        
        cam = str(cam)
        self.camInCameras(cam)
        
        current_DT = self.get_current_DT()
        
        text = str(current_DT)[:-10] + ' cam ' + cam + ': ' + log
        
        self.log += text
        self.cameras[cam]["log"] += text
        
        if show_log: print(text)
        
    
    def save_log(self):
        pass