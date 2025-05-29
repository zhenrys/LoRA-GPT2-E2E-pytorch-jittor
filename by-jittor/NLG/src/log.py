import logging
import os
from datetime import datetime

class Logger:
    def __init__(self):
        self.logger=None
        self.log_dir = "logs"
        os.makedirs(self.log_dir, exist_ok=True)
        self.filename=""
    def log(self,text):
        # print(text)
        self.logger.info(text)

    def register(self,filename):
        self.filename=os.path.join(self.log_dir, f"{filename}.log")
        print(self.filename)
        logging.basicConfig(
            format='%(message)s - %(asctime)s - %(name)s',
            level=logging.INFO,
            handlers = [
                logging.FileHandler(self.filename),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)