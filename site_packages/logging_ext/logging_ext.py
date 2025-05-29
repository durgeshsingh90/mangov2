import logging
import logging.handlers
import colorlog
import os
import datetime
import copy
import pika
import pprint
import json
AUDIT = 15
logging.addLevelName(AUDIT, "AUDIT")

class LoggerMgr:
    logger_dict = {}
    @classmethod
    def add_logger(cls, logger_name):
        if logger_name not in LoggerMgr.logger_dict:
            LoggerMgr.logger_dict[logger_name] = Logger(logger_name)
            return True
        else:
            return False

    @classmethod
    def remove_logger(cls, logger_name):
        if logger_name in LoggerMgr.logger_dict:
            del LoggerMgr.logger_dict[logger_name]
            return True
        else:
            return False

    @classmethod
    def logger_exist(cls, logger_name):
        if logger_name not in LoggerMgr.logger_dict:
            return False
        else:
            return True

    @classmethod
    def get_logger(cls, logger_name):
        if logger_name not in LoggerMgr.logger_dict:
            return None
        else:
            return LoggerMgr.logger_dict[logger_name]

    @classmethod
    def log(cls, logger_name, log_level, msg):
        if logger_name not in LoggerMgr.logger_dict:
            return False
        else:
            LoggerMgr.logger_dict[logger_name].log(log_level, msg)
            return True

    @classmethod
    def enable(cls, logger_name):
        if logger_name not in LoggerMgr.logger_dict:
            return False
        else:
            LoggerMgr.logger_dict[logger_name].enable()
            return True

    @classmethod
    def disable(cls, logger_name):
        if logger_name not in LoggerMgr.logger_dict:
            return False
        else:
            LoggerMgr.logger_dict[logger_name].disable()
            return True

    @classmethod
    def set_log_level(cls, logger_name, log_level):
        if logger_name not in LoggerMgr.logger_dict:
            return False
        else:
            LoggerMgr.logger_dict[logger_name].set_log_level(log_level)
            return True


class RabbitMqHandler(logging.Handler):
    """
     A handler that acts as a RabbitMQ publisher
     Requires the kombu module.

     Example setup::

        handler = RabbitMQHandler('amqp://guest:guest@localhost//', queue='my_log')
    """
    def __init__(self, host="localhost", virtual_host = "/" , routing_key='logging'):
        logging.Handler.__init__(self)
        self._routing_key = routing_key
        self._host = host
        self._virtual_host = virtual_host

        self._connection = None

        #self.channel.queue_declare(queue=routing_key)

    def connect(self):

        self._connection = pika.BlockingConnection(pika.ConnectionParameters(host=self._host,
                                                                             virtual_host=self._virtual_host,
                                                                             heartbeat=600))
        self._channel = self._connection.channel()

    def emit(self, record):
        json_rec =\
            {"created": datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f'),
             "message": record.msg,
             "level": record.levelname}

        try:
            self._channel.basic_publish(exchange='', routing_key=self._routing_key, body=json.dumps(json_rec))
        except pika.exceptions.StreamLostError as e:
            self.connect()
            self._channel.basic_publish(exchange='', routing_key=self._routing_key, body=json.dumps(json_rec))


    def close(self):
        if self._connection is not None:
            self._connection.close()


class Logger:
    def __init__(self, logger_name):
        self._logger = logging.getLogger(logger_name)
        self._enabled = True
        self._buff = {}

    def add_rotating_file_handler(self, log_filename, log_format='%(ts)s : %(levelname)s : %(message)s' + "\x1e", max_bytes=5000000, backup_count=10):
        log_dir = os.path.dirname(log_filename)

        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)

        rotating_file_handler = logging.handlers.RotatingFileHandler(log_filename, mode='w', maxBytes=max_bytes, backupCount=backup_count)
        rotating_file_handler.setFormatter(logging.Formatter(log_format))

        self._logger.addHandler(rotating_file_handler)
        return True

    def add_file_handler(self, log_filename, log_format='%(ts)s : %(levelname)s : %(message)s' + "\x1e"):
        log_dir = os.path.dirname(log_filename)

        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(logging.Formatter(log_format))

        self._logger.addHandler(file_handler)
        return True

    def add_stream_handler(self, log_format='%(ts)s : %(levelname)s : %(message)s'):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(log_format))

        self._logger.addHandler(stream_handler)
        return True

    def add_rabbit_mq_handler(self, log_format='%(ts)s : %(levelname)s : %(message)s', host="localhost", virtual_host="/", routing_key="logging"):
        rabbit_mq_handler = RabbitMqHandler(host=host, virtual_host=virtual_host, routing_key=routing_key)
        rabbit_mq_handler.setFormatter(logging.Formatter(log_format))
        try:
            rabbit_mq_handler.connect()
        except pika.exceptions.AMQPConnectionError:
            return False
        else:
            self._logger.addHandler(rabbit_mq_handler)
            return True

    def add_color_stream_handler(self, log_format='%(bold_yellow)s%(ts)s%(reset)s : %(log_color)s%(levelname)s%(reset)s : %(message)s'):
        stream_handler = colorlog.StreamHandler()
        stream_handler.setFormatter(colorlog.ColoredFormatter(log_format, log_colors={  "DEBUG": "white",
                                                                                        'AUDIT': "bold_purple",
                                                                                        "INFO": "bold_cyan",
                                                                                        "WARNING": "bold_yellow,bg_white",
                                                                                        "ERROR": "bold_red,bg_white",
                                                                                        "CRITICAL": "bold_yellow,bg_bold_red",
                                                                                        }))

        self._logger.addHandler(stream_handler)
        return True


    def set_log_level(self, log_level):
        self._logger.setLevel(log_level)

    def log(self, log_level, msg, extra={}):
        if self._enabled:
            extra = copy.deepcopy(extra)
            if "ts" not in extra:
                extra["ts"] = datetime.datetime.now()

            self._logger.log(log_level, msg, extra=extra)


    def add_to_buff(self, log_level, msg, buff_id = "__master_log_buff_", extra={}):
        if buff_id not in self._buff:
            self._buff[buff_id] = []

        extra = copy.deepcopy(extra)
        if "ts" not in extra:
            extra["ts"] =  datetime.datetime.now()

        self._buff[buff_id].append([msg, log_level, extra])

    def flush_buff(self, buff_id = "__master_log_buff_"):
        if buff_id in self._buff:
            for msg, log_level, extra in self._buff[buff_id]:
                self.log(log_level, msg, extra)

            self.del_buff(buff_id)

    def del_buff(self, buff_id = "__master_log_buff_"):
        if buff_id in self._buff:
            del self._buff[buff_id]

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def close(self):
        for h in self._logger.handlers:
            h.close()