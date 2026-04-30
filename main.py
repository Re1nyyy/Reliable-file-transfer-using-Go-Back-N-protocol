import configparser
import os
import sys
import threading

from gbn_engine import GBNSender, GBNReceiver
from utils.logger import GBNLogger


SEND_ONLY_FLAG = "--send-only"
RECV_ONLY_FLAGS = {"--recv", "-r"}
DEFAULT_PORT_CHOICES = (43593, 43594)


def make_transfer_log_path(raw_log_path, file_path):
    base, ext = os.path.splitext(raw_log_path)
    file_name = os.path.basename(file_path)
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in file_name)
    return f"{base}_{safe_name}{ext}"


def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists("config.ini"):
        print("[ERROR] 找不到 config.ini 配置文件")
        return None
    config.read("config.ini", encoding="utf-8")
    return config


def prompt_choice(title, choices):
    print(title)
    for idx, (label, _) in enumerate(choices, start=1):
        print(f"{idx}. {label}")

    while True:
        selected = input("请选择序号: ").strip()
        if selected.isdigit():
            index = int(selected) - 1
            if 0 <= index < len(choices):
                return choices[index][1]
        print("输入无效，请重新选择。")


def prompt_text(label, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def interactive_args(default_port):
    local_port = prompt_choice(
        "\n请选择本机监听端口:",
        [(str(port), port) for port in DEFAULT_PORT_CHOICES],
    )

    mode = prompt_choice(
        "\n请选择运行模式:",
        [
            ("仅发送", "send-only"),
            ("仅接收", "recv-only"),
            ("发送并接收（全双工）", "duplex"),
        ],
    )

    if mode == "recv-only":
        recv_filename = prompt_text("请输入接收后保存的文件名", f"recv_at_{local_port}.bin")
        return [str(local_port), "--recv", recv_filename]

    default_target = DEFAULT_PORT_CHOICES[1] if local_port == DEFAULT_PORT_CHOICES[0] else DEFAULT_PORT_CHOICES[0]
    target_port = prompt_choice(
        "\n请选择对方端口:",
        [(str(port), port) for port in DEFAULT_PORT_CHOICES if port != local_port]
        or [(str(default_target), default_target)],
    )
    file_path = prompt_text("请输入要发送的文件路径")
    while not file_path:
        print("发送文件路径不能为空。")
        file_path = prompt_text("请输入要发送的文件路径")

    if mode == "send-only":
        recv_filename = prompt_text("请输入接收端保存的文件名（用于合并日志）", os.path.basename(file_path))
        return [str(local_port), str(target_port), file_path, recv_filename, SEND_ONLY_FLAG]

    recv_filename = prompt_text("请输入接收后保存的文件名", f"recv_at_{local_port}.bin")
    return [str(local_port), str(target_port), file_path, recv_filename]


def build_receiver(local_port, recv_filename, raw_log_path, lost_rate, error_rate, init_seq, logger=None):
    save_dir = os.path.join("Receive_Files", f"Port_{local_port}")
    full_save_path = os.path.join(save_dir, recv_filename)

    recv_logger = logger
    if recv_logger is None:
        recv_log_path = make_transfer_log_path(raw_log_path, recv_filename)
        recv_logger = GBNLogger(recv_log_path, reset=False)
        print(f"[LOG] 接收文件日志: {recv_log_path}")

    receiver = GBNReceiver(
        listen_ip="127.0.0.1",
        listen_port=local_port,
        lost_rate=lost_rate,
        error_rate=error_rate,
        logger=recv_logger,
        init_seq=init_seq,
    )
    return receiver, full_save_path


def run_node():
    config = load_config()
    if config is None:
        return

    default_port = config.getint("Common", "UDPPort")
    raw_log_path = config.get("Common", "LogPath")
    sw_size = config.getint("GBN", "SWSize")
    init_seq = config.getint("GBN", "InitSeqNo")
    timeout_ms = config.getfloat("GBN", "Timeout")
    data_size = config.getint("GBN", "DataSize")
    lost_rate = config.getfloat("Simulation", "LostRate")
    error_rate = config.getfloat("Simulation", "ErrorRate")

    args = sys.argv[1:]
    if not args:
        args = interactive_args(default_port)

    send_only = SEND_ONLY_FLAG in args
    args = [arg for arg in args if arg != SEND_ONLY_FLAG]

    local_port = int(args[0]) if len(args) >= 1 else default_port

    # Receive-only mode:
    #   python main.py 43594 --recv 1.docx
    #   python main.py 43594
    if len(args) < 3 or (len(args) >= 2 and args[1] in RECV_ONLY_FLAGS):
        if len(args) >= 2 and args[1] in RECV_ONLY_FLAGS:
            recv_filename = args[2] if len(args) >= 3 else f"recv_at_{local_port}.bin"
        else:
            recv_filename = f"recv_at_{local_port}.bin"

        receiver, full_save_path = build_receiver(
            local_port, recv_filename, raw_log_path, lost_rate, error_rate, init_seq
        )

        print("\n--- [GBN 接收模式] ---")
        print(f"监听 UDP 端口: {local_port}")
        print(f"文件保存路径: {full_save_path}")
        try:
            receiver.start_receive(full_save_path)
        except KeyboardInterrupt:
            print("\n[INFO] 接收端手动关闭")
        return

    # Send mode:
    #   one-way: python main.py 43593 43594 1.docx 1.docx --send-only
    #   duplex:  python main.py 43593 43594 1.docx 2.docx
    target_port = int(args[1])
    file_path = args[2]
    if len(args) >= 4:
        recv_filename = args[3]
    elif send_only:
        recv_filename = os.path.basename(file_path)
    else:
        recv_filename = f"recv_at_{local_port}.bin"

    send_log_name = recv_filename if send_only else file_path
    send_log_path = make_transfer_log_path(raw_log_path, send_log_name)
    send_logger = GBNLogger(send_log_path, reset=True)
    print(f"[LOG] 发送文件日志: {send_log_path}")

    receiver_logger = send_logger if send_only else None
    receiver, full_save_path = build_receiver(
        local_port, recv_filename, raw_log_path, lost_rate, error_rate, init_seq, logger=receiver_logger
    )

    sender = GBNSender(
        socket_obj=receiver.socket,
        target_ip="127.0.0.1",
        target_port=target_port,
        window_size=sw_size,
        timeout=timeout_ms,
        lost_rate=lost_rate,
        error_rate=error_rate,
        logger=send_logger,
        init_seq=init_seq,
        data_size=data_size,
    )

    recv_thread = threading.Thread(target=receiver.start_receive, args=(full_save_path, sender))
    recv_thread.start()

    print("\n--- [GBN 单向发送模式] ---" if send_only else "\n--- [GBN 全双工模式] ---")

    if sender.load_file(file_path):
        sender.run_send()

        if send_only:
            receiver.is_running = False
            recv_thread.join(timeout=2.0)
            print("\n[SYSTEM] 单向传输完成，程序退出")
        else:
            print("\n[SENDER] 我方发送完成，等待对方结束...")
            try:
                recv_thread.join()
            except KeyboardInterrupt:
                print("\n[WARNING] 用户手动中断")
            print("\n[SYSTEM] 双方传输完成，程序退出")
    else:
        receiver.is_running = False
        recv_thread.join(timeout=2.0)
        print(f"[ERROR] 无法读取文件 '{file_path}'")


if __name__ == "__main__":
    interactive_mode = len(sys.argv) == 1
    run_node()
    if interactive_mode:
        input("\n按 Enter 键退出...")
