import asyncio
import codecs
import json
import logging
from typing import List

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class TxnSender:

    def __init__(self,
                 ip: str,
                 port: int,
                 requests: [],
                 len_ind: [],
                 local_addr=None,
                 max_log_msgs_shown: int = 0,
                 log_msg_size: int = 200,
                 tps: int = 0.05,
                 wait_after: int = 60):
        # ip, port = socket
        self._ip = ip
        self._port = port
        self._local_addr = local_addr
        self._reader = None
        self._writer = None
        self._requests = requests
        self._len_ind = len_ind
        self._responses = []
        self._delay = 1 / tps
        self._wait_after = wait_after
        self._log_msg_size = log_msg_size
        self._max_log_msgs_shown = max_log_msgs_shown
        self._current_msgs_shown: List[int, int] = [0, 0]  # (rcvd, sent) numbers
        self._rcvd_msgs: int = 0
        self._sent_msgs: int = 0
        self._schemer = None
        self._de037 = None
        self._received_res = False

    async def _connect(self) -> bool:

        try:
            self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(self._ip,
                                                                                        self._port,
                                                                                        local_addr = self._local_addr),
                                                                timeout=5.0)

        except ConnectionRefusedError as e:
            logging.error(f'ERROR: Not able to connect to {self._ip}:{self._port}. Connection refused.')
            return False
        except asyncio.exceptions.TimeoutError:
            logging.error(f"ERROR: Not able to connect to {self._ip}:{self._port}. Timeout")
        except OSError as e:
            if e.errno == 22:
                logging.error(f'ERROR: Not able to connect to {self._ip}:{self._port}. The network location cannot be reached.')
                return False
            if e.errno == 10048:
                logging.error(f'ERROR: Not able to connect to {self._ip}:{self._port}. Error while attempting to bind on local address ( only one usage of each socket address (protocol/network address/port) is normally permitted).')
                return False
            if e.errno == 10049:
                logging.error(f'ERROR: Not able to connect to {self._ip}:{self._port}. Error while attempting to bind on local address (the address is not valid in its context).')
                return False
            if e.errno == 98:
                logging.error(f' Not able to connect to {self._ip}:{self._port}. Error while attempting to bind on local address (address already in use).')
                return False
            else:
                logging.error("ELSE ERROR")
                raise e
        except Exception as e:
            logging.error("ANOTHER ERROR")

        logging.info(f'Connected to {self._ip}:{self._port}')
        return True

    async def _recv_msg_loop(self) -> None:
        while True and not self._received_res:
            if "prfx" in self._len_ind:
                expected_prfx = b""
                if self._len_ind["prfx"]["format"] == "hex":
                    expected_prfx = bytes.fromhex(self._len_ind["prfx"]["value"])
                elif self._len_ind["prfx"]["format"] == "ascii":
                    expected_prfx = self._len_ind["prfx"]["value"].encode()
                else:
                    pass

                prfx = await self._reader.read(len(expected_prfx))
                if expected_prfx != prfx:
                    logging.error(f'ERROR: Unexpected prefix received: {prfx}')
                    break

            if self._len_ind["type"] == "binary":
                expected_size = int.from_bytes(await self._reader.read(self._len_ind["len"]), byteorder='big')
            if self._len_ind["type"] == "ascii":
                expected_size = int((await self._reader.read(self._len_ind["len"])).decode())
            if self._len_ind["type"] == "ebcdic":
                expected_size = int(codecs.decode(await self._reader.read(self._len_ind["len"]), "cp500"))
            if "add" in self._len_ind:
                expected_size += self._len_ind["add"]

            if "ignore" in self._len_ind and self._len_ind["ignore"]:
                ignore = self._len_ind["ignore"]

                ignored = await self._reader.read(ignore)
                while len(ignored) < ignore:
                    ignored = ignored + await self._reader.read(ignore - len(ignored))

            msg: bytes = await self._reader.read(expected_size)

            while len(msg) < expected_size:
                msg = msg + await self._reader.read(expected_size - len(msg))

            if "end_of_text" in self._len_ind and self._len_ind["end_of_text"] == True:
                etx = await self._reader.read(1)

            if len(msg) > 0:

                self._responses.append(msg)
                try:
                    decoded_msg: str = msg.decode()
                except UnicodeDecodeError:
                    decoded_msg: str = msg.hex()

                self._match_msg(msg)

                if self._current_msgs_shown[0] < self._max_log_msgs_shown and self._log_msg_size != 0:
                    self._current_msgs_shown[0] += 1
                    decoded_msg_len: int = len(decoded_msg)
                    msg_truncated: bool = decoded_msg_len > self._log_msg_size
                    print_msg: str = f'Rcvd: {decoded_msg[0:min(self._log_msg_size, decoded_msg_len)]}'
                    if msg_truncated:
                        print_msg = print_msg + "..."
                    logging.debug(print_msg)
                self._rcvd_msgs += 1

                if self._received_res:
                    logging.info("matched")


    def _match_msg(self, msg):
        m = msg
        msg_de037 = ""
        try:
            j = self._schemer.parse(m, "OMNIPAY")
            logging.error(j)
            msg_de037 = j[0]["data_elements"]["DE037"]
            logging.info(f"rq 37: {self._de037}")
            logging.info(f"rs 37: {msg_de037}")
        except Exception as e:
            logging.error(str(e))

        if msg_de037 == self._de037:
            logging.info("tranasction matched")
            self._received_res = True


    async def _send_msg(self, msg: bytes) -> None:
        clean_msg_len = len(msg)
        etx = b''
        ignore_part = b''
        prfx = b''

        logging.debug(f"{self._len_ind}")
        if "add" in self._len_ind:
            clean_msg_len -= self._len_ind["add"]

        if self._len_ind["type"] == "binary":
            msg_len = clean_msg_len.to_bytes(self._len_ind["len"], byteorder='big')
        if self._len_ind["type"] == "ascii":
            msg_len = str(clean_msg_len).zfill(self._len_ind["len"]).encode()
        if self._len_ind["type"] == "ebcdic":
            msg_len = codecs.encode(str(clean_msg_len).zfill(self._len_ind["len"]), "cp500")

        if "ignore" in self._len_ind:
            ignore_part = b'\00' * self._len_ind["ignore"]

        if "prfx" in self._len_ind:
            if self._len_ind["prfx"]["format"] == "hex":
                prfx = bytes.fromhex(self._len_ind["prfx"]["value"])
            elif self._len_ind["prfx"]["format"] == "ascii":
                prfx = self._len_ind["prfx"]["value"].encode()

        if "end_of_text" in self._len_ind and self._len_ind["end_of_text"] == True:
            etx = b'\03'

        self._writer.write(prfx + msg_len + ignore_part + msg + etx)
        await self._writer.drain()

        try:
            decoded_msg: str = msg.decode()
        except UnicodeDecodeError:
            decoded_msg: str = msg.hex()

        if self._current_msgs_shown[1] < self._max_log_msgs_shown and self._log_msg_size != 0:
            self._current_msgs_shown[1] += 1
            decoded_msg_len: int = len(decoded_msg)
            msg_truncated: bool = decoded_msg_len > self._log_msg_size
            print_msg: str = f'Sent: {decoded_msg[0:min(self._log_msg_size, decoded_msg_len)]}'
            if msg_truncated:
                print_msg = print_msg + "..."
            logging.debug(print_msg)
        self._sent_msgs += 1

    async def _send_msgs(self) -> None:
        if not self._writer:
            if await self._connect():
                read_task = asyncio.ensure_future(self._recv_msg_loop())

                for rq in self._requests:
                    await asyncio.sleep(self._delay)
                    await self._send_msg(rq)

                if self._max_log_msgs_shown <= self._current_msgs_shown[1] or self._log_msg_size == 0:
                    logging.debug(" *** Maximum number of messages shown on log has been hit *** ")
                logging.debug(f'All messages sent. Waiting {self._wait_after} seconds for responses')

                try:
                    logging.info("waiting")
                    await asyncio.wait_for(read_task, self._wait_after)
                except asyncio.TimeoutError:
                    self._writer.close()
                    try:
                            #
                            #   Requried due to Python 3.6 compatibility (StreamWriter.wait_closed not supported in Python 3.6)
                            #
                        await self._writer.wait_closed()
                    except AttributeError:
                        pass

                    pad_count = max(len(str(self._rcvd_msgs)), len(str(self._sent_msgs)))
                    logging.debug(f' |----------------------------{("-" * pad_count)}| ')
                    logging.debug(f' |--- All Rcvd: {self._rcvd_msgs} messages. ---| ')
                    logging.debug(f' |--- All Sent: {self._sent_msgs} messages. ---| ')
                    logging.debug(f' |----------------------------{("-" * pad_count)}| ')
                    logging.debug(f'Listening at {self._ip}:{self._port} stopped')


                try:
                    logging.info("reading")
                    await read_task
                except asyncio.CancelledError:
                    pass

    def run(self, s) -> List[str]:
        self._schemer = s
        r = self._requests[0]
        try:
            j = s.parse(r, "OMNIPAY")
            self._de037 = j[0]["data_elements"]["DE037"]
        except Exception as e:
            logging.error('RUN ERROR'+str(e))

        asyncio.run(self._send_msgs())
        
        logging.info('run completed')
        logging.info(self._responses)

        self._reader = None
        self._writer = None
        logging.info('run completed 2')
        return self._responses


if __name__ == "__main__":

    try:
        config_file = "config.json"
        with open(config_file, "r") as json_file:
            config = json.load(json_file)
    except FileNotFoundError:
        logging.error(f"ERROR:  Not able to find {config_file}.")
        exit()

    # ------ check input values ------

    if "ip" not in config:
        logging.error("ERROR: ip value has to be specified in config.json.")
        exit()

    if "port" not in config:
        logging.error("ERROR: port number has to be specified in config.json.")
        exit()

    if "local_ip" in config:
        if "local_port" not in config:
            config["local_port"] = 0

        config["local_addr"] = (config["local_ip"], config["local_port"])

        del config["local_ip"]
        del config["local_port"]
    else:
        if "local_port" in config:
            logging.error("WARNING: local_port ignored. local_port is only usable together with local_ip. ")
            del config["local_port"]


    # ------ handle input_file and merge it with requests ------
    all_requests = []

    if "requests" in config and config["requests"]:
        for req in config["requests"]:
            if len(str(req)) > 1:
                all_requests.append(bytes.fromhex(req))

    if "input_file" in config and config["input_file"]:
        with open(config["input_file"], "r") as input_file:
            for i in input_file:
                if i.strip() == "":
                    continue
                all_requests.append(bytes.fromhex(i.strip()))

    if not all_requests:
        logging.error("ERROR: Requests and input_file are both empty.")
        exit()

    # ----------------------------------------------------------

    del config["input_file"]
    config["requests"] = all_requests

    len_ind = config["len_ind"]
    if type(len_ind) == str:
        with open("len_ind_cnfg.json", "r") as f:
            config["len_ind"] = json.load(f)[len_ind]["len_ind"]

    t = TxnSender(**config)
    t.run()

