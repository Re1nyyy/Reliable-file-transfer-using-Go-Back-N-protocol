import random

def should_drop(lost_rate):
    """根据丢失率(0-100)决定是否丢包 [cite: 11, 28]"""
    return random.random() * 100 < lost_rate

def should_corrupt(error_rate):
    """根据错误率(0-100)决定是否篡改数据 [cite: 11, 27]"""
    return random.random() * 100 < error_rate

def corrupt_data(raw_data):
    """随机修改一个字节模拟传输错误 """
    data_list = list(raw_data)
    idx = random.randint(0, len(data_list) - 1)
    data_list[idx] ^= 0xFF # 按位取反
    return bytes(data_list)