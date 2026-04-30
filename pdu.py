import struct

class PDU:
    # 格式定义: H(unsigned short, 2字节) * 3 + 数据 + H(校验码)
    # 结构：序号(2B) | 确认号(2B) | 数据长度(2B) | 数据(可变) | CRC(2B)
    HEADER_FORMAT = "!HHH" 
    
    def __init__(self, seq_no, ack_no, data=b""):
        self.seq_no = seq_no
        self.ack_no = ack_no
        self.data = data
        self.checksum = 0

    def make_packet(self):
        """将 PDU 打包成二进制字节流"""
        # 先打包头部和数据（不含校验码）
        header = struct.pack(self.HEADER_FORMAT, self.seq_no, self.ack_no, len(self.data))
        packet_without_crc = header + self.data
        # 计算 CRC 
        self.checksum = self.calc_crc(packet_without_crc)
        # 将校验码追加到末尾 (2字节)
        return packet_without_crc + struct.pack("!H", self.checksum)

    @staticmethod
    def calc_crc(data):
        """实现 CRC-CCITT 标准 (多项式 0x1021)"""
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc

    @classmethod
    def decode(cls, raw_data):
        """从二进制流解包"""
        if len(raw_data) < 8: return None # 最小长度：Header(6) + CRC(2)
        
        header_size = struct.calcsize(cls.HEADER_FORMAT)
        header = struct.unpack(cls.HEADER_FORMAT, raw_data[:header_size])
        seq_no, ack_no, data_len = header
        
        data = raw_data[header_size : header_size + data_len]
        received_crc = struct.unpack("!H", raw_data[-2:])[0]
        
        # 验证 CRC 
        if cls.calc_crc(raw_data[:-2]) == received_crc:
            return cls(seq_no, ack_no, data)
        else:
            return "CRC_ERROR"