import os
import socket
import threading
import time
from pdu import PDU
from utils.simulator import should_drop, should_corrupt, corrupt_data

FIN_ACK_NO = 65535


# ==================== 发送方 ====================
class GBNSender:
    def __init__(self, socket_obj, target_ip, target_port, window_size, timeout, lost_rate, error_rate, logger, init_seq, data_size):
        self.socket = socket_obj
        self.target_addr = (target_ip, target_port)

        self.window_size = window_size
        self.timeout = timeout / 1000.0
        self.lost_rate = lost_rate
        self.error_rate = error_rate
        self.logger = logger
        self.data_size = data_size

        self.init_seq = init_seq
        self.base = init_seq
        self.next_seq = init_seq
        self.packets = []

        self.timer = None
        self.is_running = True
        self.lock = threading.Lock()

        self.retrans_count = 0
        self.max_retrans = 20
        self.last_timeout_base = -1

        # ⭐ 新增：发送计数
        self.send_count = 0

    def _start_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(self.timeout, self._handle_timeout)
        self.timer.start()

    def _stop_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def _handle_timeout(self):
        with self.lock:
            if not self.is_running:
                return

            if self.base == self.last_timeout_base:
                self.retrans_count += 1
            else:
                self.retrans_count = 1
                self.last_timeout_base = self.base

            if self.retrans_count > self.max_retrans:
                print("\n[FATAL] 连续重传失败，停止发送。")
                self.is_running = False
                return

            # ⭐ 超时重传：标记为 TO
            for i in range(self.base, self.next_seq):
                pdu = self.packets[i - self.init_seq]

                self.send_count += 1
                acked = self.base - 1
                status = "TO" if i == self.base else "RT"
                log_line = f"{self.send_count}, pdu_to_send={pdu.seq_no}, status={status}, ackedNo={acked}"
                self.logger.log("SEND", log_line)

                packet = pdu.make_packet()
                if should_drop(self.lost_rate):
                    continue
                if should_corrupt(self.error_rate):
                    packet = corrupt_data(packet)
                self.socket.sendto(packet, self.target_addr)

            self._start_timer()

    def _physical_send(self, pdu, is_retrans=False):
        packet = pdu.make_packet()

        self.send_count += 1
        acked = self.base - 1
        status = "RT" if is_retrans else "New"

        # 丢包
        if should_drop(self.lost_rate):
            log_line = f"{self.send_count}, pdu_to_send={pdu.seq_no}, status={status}, ackedNo={acked}"
            self.logger.log("SEND", log_line)
            return

        # 错误
        if should_corrupt(self.error_rate):
            packet = corrupt_data(packet)
            log_line = f"{self.send_count}, pdu_to_send={pdu.seq_no}, status={status}, ackedNo={acked}"
        else:
            log_line = f"{self.send_count}, pdu_to_send={pdu.seq_no}, status={status}, ackedNo={acked}"

        self.logger.log("SEND", log_line)
        self.socket.sendto(packet, self.target_addr)

    def handle_incoming_ack(self, ack_pdu):
        if ack_pdu != "CRC_ERROR" and ack_pdu:
            with self.lock:
                if ack_pdu.ack_no == FIN_ACK_NO:
                    return

                if ack_pdu.ack_no >= self.base:
                    self.base = ack_pdu.ack_no + 1
                    self.retrans_count = 0

                    if self.base == self.next_seq:
                        self._stop_timer()
                    else:
                        self._start_timer()

    def load_file(self, file_path):
        if not os.path.exists(file_path):
            print(f"Error: File {file_path} not found.")
            return False

        with open(file_path, 'rb') as f:
            seq = self.init_seq
            while True:
                data = f.read(self.data_size)
                if not data:
                    break
                self.packets.append(PDU(seq_no=seq, ack_no=0, data=data))
                seq += 1

        print(f"文件加载完成: {len(self.packets)} 个包")
        return True

    def run_send(self):
        total_target = self.init_seq + len(self.packets)

        while self.is_running and self.base < total_target:
            with self.lock:
                while self.next_seq < self.base + self.window_size and self.next_seq < total_target:
                    pdu = self.packets[self.next_seq - self.init_seq]

                    if self.base == self.next_seq:
                        self._start_timer()

                    self._physical_send(pdu, is_retrans=False)
                    self.next_seq += 1

            time.sleep(0.002)

        self._stop_timer()

        if self.base >= total_target:
            print("--- 数据发送完成 ---")

        # FIN
        fin_pdu = PDU(seq_no=0, ack_no=FIN_ACK_NO, data=b"")
        for _ in range(5):
            self.socket.sendto(fin_pdu.make_packet(), self.target_addr)

        self.is_running = False


# ==================== 接收方 ====================
class GBNReceiver:
    def __init__(self, listen_ip, listen_port, lost_rate, error_rate, logger, init_seq):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((listen_ip, listen_port))

        self.expected_seq = init_seq
        self.init_seq = init_seq
        self.lost_rate = lost_rate
        self.error_rate = error_rate
        self.logger = logger

        self.is_running = True
        self.remote_finished = False

        # ⭐ 接收计数
        self.recv_count = 0

    def start_receive(self, save_path, sender_instance=None):
        self.is_running = True

        self.socket.settimeout(1.0)
        f = None

        try:
            while self.is_running:
                try:
                    raw_data, addr = self.socket.recvfrom(8192)
                except socket.timeout:
                    if self.remote_finished and (sender_instance is None or not sender_instance.is_running):
                        print("\n[INFO] 双方传输完成，安全退出")
                        break
                    continue
                except ConnectionResetError:
                    continue

                # 丢包
                pdu = PDU.decode(raw_data)

                # CRC 错误
                if pdu == "CRC_ERROR" or pdu is None:
                    self.recv_count += 1
                    log_line = f"{self.recv_count}, pdu_exp={self.expected_seq}, pdu_recv=-1, status=DataErr"
                    self.logger.log("RECV", log_line)
                    continue

                # FIN
                if pdu.ack_no == FIN_ACK_NO:
                    print("\n[INFO] 收到对方 FIN")
                    self.remote_finished = True
                    continue

                # ACK 不记录
                if len(pdu.data) == 0:
                    if sender_instance:
                        sender_instance.handle_incoming_ack(pdu)
                    continue

                # 正确
                if pdu.seq_no == self.expected_seq:
                    self.recv_count += 1
                    log_line = f"{self.recv_count}, pdu_exp={self.expected_seq}, pdu_recv={pdu.seq_no}, status=OK"
                    self.logger.log("RECV", log_line)

                    if f is None:
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        f = open(save_path, 'wb')
                        print(f"\n开始接收文件 -> {save_path}")

                    f.write(pdu.data)
                    f.flush()

                    ack_pdu = PDU(seq_no=0, ack_no=self.expected_seq)
                    self.socket.sendto(ack_pdu.make_packet(), addr)

                    self.expected_seq += 1

                else:
                    # 乱序
                    self.recv_count += 1
                    log_line = f"{self.recv_count}, pdu_exp={self.expected_seq}, pdu_recv={pdu.seq_no}, status=NoErr"
                    self.logger.log("RECV", log_line)

                    ack_pdu = PDU(seq_no=0, ack_no=self.expected_seq - 1)
                    self.socket.sendto(ack_pdu.make_packet(), addr)

        finally:
            if f:
                f.close()
                print("=== 文件接收完成 ===")

            self.is_running = False
