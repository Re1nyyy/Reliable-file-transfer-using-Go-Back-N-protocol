import os
import sys
import time
import matplotlib.pyplot as plt

class GBNAnalyzer:
    def __init__(self, log_file):
        self.log_file = log_file
        self.send_stats = {
            "total_pdu_sent": 0,    
            "unique_pdu_count": 0,  
            "timeout_count": 0,     
            "retrans_count": 0,     
            "new_count": 0,         
            "start_time": None,
            "end_time": None
        }
        self.recv_stats = {
            "total_recv_count": 0,
            "ok_count": 0,          
            "data_err_count": 0,    
            "no_err_count": 0       
        }
        self.unique_seqs = set()

    def parse(self):
        if not os.path.exists(self.log_file):
            print(f"错误: 找不到日志文件 {self.log_file}")
            return False

        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("Time") or "SYSTEM" in line or "WINDOW" in line:
                    continue
                
                parts = line.split(',') # 仅用逗号分割
                if len(parts) < 3: continue
                
                timestamp_str = parts[0].strip()
                event_type = parts[1].strip()
                
                # 将剩余部分重新组合为一个 details 字符串
                details = ','.join(parts[2:])

                try:
                    t = self._convert_time(timestamp_str)
                    if self.send_stats["start_time"] is None: 
                        self.send_stats["start_time"] = t
                    self.send_stats["end_time"] = t
                except ValueError:
                    continue

                if event_type == "SEND":
                    self._process_send(details)
                elif event_type == "RECV":
                    self._process_recv(details)

        self.send_stats["unique_pdu_count"] = len(self.unique_seqs)
        return True

    def _convert_time(self, t_str):
        h, m, s = map(int, t_str.split(':'))
        return h * 3600 + m * 60 + s

    def _process_send(self, details):
        self.send_stats["total_pdu_sent"] += 1
        
        # 手动提取键值对，绝对安全地防止空格问题
        # details 的样子类似于: " 21, pdu_to_send=5, status=TO, ackedNo=4"
        data = {}
        for item in details.split(','):
            if '=' in item:
                k, v = item.split('=', 1)
                data[k.strip()] = v.strip()
        
        seq_str = data.get("pdu_to_send", "-1")
        status = data.get("status", "")

        try:
            seq = int(seq_str)
            if seq != -1: 
                self.unique_seqs.add(seq)
        except ValueError:
            pass
        
        if status == "New":
            self.send_stats["new_count"] += 1
        elif status == "TO":
            self.send_stats["timeout_count"] += 1
            self.send_stats["retrans_count"] += 1
        elif status == "RT":
            self.send_stats["retrans_count"] += 1

    def _process_recv(self, details):
        self.recv_stats["total_recv_count"] += 1
        
        data = {}
        for item in details.split(','):
            if '=' in item:
                k, v = item.split('=', 1)
                data[k.strip()] = v.strip()
                
        status = data.get("status", "")

        if status == "OK":
            self.recv_stats["ok_count"] += 1
        elif status == "DataErr":
            self.recv_stats["data_err_count"] += 1
        elif status == "NoErr":
            self.recv_stats["no_err_count"] += 1

    def report(self):
        duration = self.send_stats["end_time"] - self.send_stats["start_time"]
        # 处理所有事件发生在一秒内导致耗时为负或 0 的情况
        if duration < 0: duration = 0 
        
        retrans_rate = (self.send_stats["retrans_count"] / self.send_stats["total_pdu_sent"]) * 100 if self.send_stats["total_pdu_sent"] > 0 else 0
        
        print("\n" + "="*50)
        print(f"GBN 通信效率分析报告")
        print(f"日志文件: {self.log_file}")
        print("="*50)
        print(f"1. 文件划分 PDU 总数:      {self.send_stats['unique_pdu_count']}")
        print(f"2. 发送端总通信次数:       {self.send_stats['total_pdu_sent']}")
        print(f"3. 超时重传次数 (TO):      {self.send_stats['timeout_count']}")
        print(f"4. 总重传 PDU 数量 (RT+TO): {self.send_stats['retrans_count']}")
        print(f"5. 接收端正确接收 (OK):    {self.recv_stats['ok_count']}")
        print(f"6. 接收端检测到错误:       {self.recv_stats['data_err_count']}")
        print(f"7. 接收端乱序丢弃:         {self.recv_stats['no_err_count']}")
        print(f"8. 传输总耗时:             {duration} 秒")
        print(f"9. PDU 重传率:             {retrans_rate:.2f}%")
        print("-" * 50)
        print("分析结论：")
        if retrans_rate > 20:
            print("结论：重传率较高，建议检查超时值是否过短或窗口是否过大。")
        else:
            print("结论：通信效率良好，参数配置与网络状况匹配。")
        print("="*50)

    def plot_summary(self):
        labels = ['总发送量', '新数据包', '重传数量', '超时次数']
        values = [
            self.send_stats['total_pdu_sent'], 
            self.send_stats['new_count'], 
            self.send_stats['retrans_count'], 
            self.send_stats['timeout_count']
        ]

        # 解决 matplotlib 中文显示问题
        plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
        plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

        plt.figure(figsize=(10, 6))
        plt.bar(labels, values, color=['#3498db', '#2ecc71', '#f39c12', '#e74c3c'])
        plt.title(f"GBN 性能指标分析\n{os.path.basename(self.log_file)}")
        plt.ylabel("PDU 数量")
        for i, v in enumerate(values):
            plt.text(i, v + 0.5, str(v), ha='center', fontweight='bold')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.show()


def choose_log_file():
    log_files = sorted(
        [name for name in os.listdir(".") if os.path.isfile(name) and name.lower().endswith(".log")],
        key=lambda name: os.path.getmtime(name),
        reverse=True,
    )

    if not log_files:
        print("[错误] 当前目录下没有找到 .log 日志文件")
        return None

    print("\n请选择要分析的日志文件:")
    for index, name in enumerate(log_files, start=1):
        size = os.path.getsize(name)
        mtime = os.path.getmtime(name)
        time_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        print(f"{index}. {name}  ({size} bytes, {time_text})")

    while True:
        selected = input("请输入序号: ").strip()
        if selected.isdigit():
            index = int(selected) - 1
            if 0 <= index < len(log_files):
                return log_files[index]
        print("输入无效，请重新选择。")


if __name__ == "__main__":
    log_path = sys.argv[1] if len(sys.argv) > 1 else choose_log_file()
    
    if log_path and os.path.exists(log_path):
        analyzer = GBNAnalyzer(log_path)
        if analyzer.parse():
            analyzer.report()
            analyzer.plot_summary()
    else:
        print(f"[错误] 找不到日志文件: {log_path}")
