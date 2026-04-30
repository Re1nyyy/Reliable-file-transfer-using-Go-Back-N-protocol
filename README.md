# Reliable File Transfer Using Go-Back-N Protocol

本项目是一个基于 **Go-Back-N (GBN)** 协议的可靠文件传输实验项目。程序使用 UDP Socket 发送和接收 PDU，在应用层实现序号控制、CRC 校验、累计 ACK、滑动窗口、超时重传、丢包/错误模拟、日志记录和日志分析。

项目支持：

- 单向文件传输
- 全双工文件互传
- PDU 丢失和损坏模拟
- 每个文件传输生成独立日志
- 日志自动分析和图表展示
- 交互式菜单运行
- 已打包的 Windows 可执行文件 `Go-Back-N.exe`

## 项目结构

```text
GBN_Project/
├── Go-Back-N.exe          # PyInstaller 打包后的可执行程序
├── main.py                # 程序入口，交互菜单和运行模式控制
├── gbn_engine.py          # GBN 发送方和接收方核心逻辑
├── pdu.py                 # PDU 定义、打包、解包和 CRC-CCITT 校验
├── analyzer.py            # 日志分析程序
├── config.ini             # 协议和模拟参数配置文件
├── utils/
│   ├── logger.py          # 日志记录模块
│   └── simulator.py       # PDU 丢失和错误模拟模块
├── 1.jpg                  # 测试文件
└── 2.txt                  # 测试文件
```

运行过程中会自动生成：

```text
Receive_Files/             # 接收文件保存目录
gbn_project_*.log          # 每次文件传输生成的日志文件
```

## 功能说明

### 1. PDU 结构

项目自定义 PDU 格式：

```text
+---------+---------+----------+-------------+----------+
| seq_no  | ack_no  | data_len |    data     | checksum |
|  2B     |  2B     |   2B     | 0~4096B     |   2B     |
+---------+---------+----------+-------------+----------+
```

- `seq_no`：数据 PDU 序号
- `ack_no`：ACK 确认号
- `data_len`：数据字段长度
- `data`：文件数据
- `checksum`：CRC-CCITT 校验码

### 2. GBN 协议

发送方维护：

- `base`：当前窗口中最早未确认的 PDU 序号
- `next_seq`：下一个待发送 PDU 序号
- `SWSize`：发送窗口大小
- `Timeout`：超时定时器

接收方维护：

- `expected_seq`：当前期望接收的 PDU 序号

接收方只接收序号等于 `expected_seq` 的 PDU。损坏 PDU 记录为 `DataErr`，乱序 PDU 记录为 `NoErr`。发送方超时后从 `base` 开始执行 Go-Back-N 重传。

发送状态：

- `New`：第一次发送
- `TO`：超时触发的窗口基序号 PDU
- `RT`：同一轮 GBN 回退中被连带重传的 PDU

接收状态：

- `OK`：正确接收
- `DataErr`：CRC 错误或 PDU 损坏
- `NoErr`：序号错误，即乱序 PDU

## 配置文件

配置文件为 `config.ini`。

示例配置：

```ini
[Common]
UDPPort = 43593
LogPath = gbn_project.log

[GBN]
SWSize = 4
InitSeqNo = 1
Timeout = 200
DataSize = 4096

[Simulation]
LostRate = 1.0
ErrorRate = 1.0
```

参数说明：

| 参数          | 说明                             |
| ----------- | ------------------------------ |
| `UDPPort`   | 默认 UDP 监听端口                    |
| `LogPath`   | 日志文件名前缀                        |
| `SWSize`    | 发送窗口大小                         |
| `InitSeqNo` | 初始 PDU 序号                      |
| `Timeout`   | 超时时间，单位毫秒                      |
| `DataSize`  | 每个 PDU 的数据字段大小，单位字节，建议不超过 4096 |
| `LostRate`  | PDU 丢失率，百分比                    |
| `ErrorRate` | PDU 错误率，百分比                    |

## 运行方式

### 方式一：运行可执行文件

Windows 下可以直接运行：

```powershell
.\Go-Back-N.exe
```

程序会进入交互式菜单，依次选择：

1. 本机监听端口：`43593` 或 `43594`
2. 运行模式：仅发送、仅接收、发送并接收
3. 文件路径或接收文件名

### 方式二：使用 Python 运行

如果本机安装了 Python，也可以运行：

```powershell
python main.py
```

这同样会进入交互式菜单。

## 使用示例

### 1. 单向传输

打开两个终端。

终端 1，作为接收端：

```powershell
python main.py 43594 --recv 1.jpg
```

终端 2，作为发送端：

```powershell
python main.py 43593 43594 1.jpg 1.jpg --send-only
```

说明：

- `43593`：发送端本地端口
- `43594`：接收端端口
- 第一个 `1.jpg`：发送文件路径
- 第二个 `1.jpg`：接收端保存文件名，同时用于合并日志

接收文件保存位置：

```text
Receive_Files/Port_43594/1.jpg
```

日志文件：

```text
gbn_project_1.jpg.log
```

### 2. 全双工传输

打开两个终端。

终端 1：

```powershell
python main.py 43593 43594 1.jpg 2.txt
```

终端 2：

```powershell
python main.py 43594 43593 2.txt 1.jpg
```

含义：

- 端口 `43593` 发送 `1.jpg`，同时接收并保存对方发送的 `2.txt`
- 端口 `43594` 发送 `2.txt`，同时接收并保存对方发送的 `1.jpg`

生成日志：

```text
gbn_project_1.jpg.log
gbn_project_2.txt.log
```

每个日志文件包含对应文件传输方向上的 `SEND` 和 `RECV` 记录。

## 日志分析

运行：

```powershell
python analyzer.py
```

程序会自动扫描当前目录下的 `.log` 文件，并提示用户选择要分析的日志。

也可以直接指定日志文件：

```powershell
python analyzer.py gbn_project_1.jpg.log
```

分析指标包括：

- 文件划分 PDU 总数
- 发送端总通信次数
- 超时重传次数 `TO`
- 总重传 PDU 数量 `RT + TO`
- 接收端正确接收数量 `OK`
- 接收端检测到错误数量 `DataErr`
- 接收端乱序丢弃数量 `NoErr`
- 传输总耗时
- PDU 重传率

`analyzer.py` 会使用 `matplotlib` 绘制统计图表。如果本机没有安装 `matplotlib`，可执行：

```powershell
pip install matplotlib
```

## 文件一致性验证

传输完成后，可以使用 PowerShell 验证原文件和接收文件是否完全一致：

```powershell
Get-FileHash .\1.jpg
Get-FileHash .\Receive_Files\Port_43594\1.jpg
```

如果两个 SHA256 值一致，说明文件传输成功且内容完全一致。

## 注意事项

1. 两个节点应使用不同 UDP 端口，例如 `43593` 和 `43594`。
2. 单向发送时，发送端仍需要接收 ACK，因此发送端内部也会启动接收线程。
3. 若使用单向传输，发送端输入的“接收端保存文件名”应与接收端保存文件名一致，便于生成同一个日志文件。
4. `LostRate` 和 `ErrorRate` 越高，重传次数和传输耗时通常越高。
5. GBN 不缓存乱序 PDU，因此窗口越大，在不可靠信道下可能产生更多回退重传。
6. 上传 GitHub 时建议忽略运行生成文件，例如 `Receive_Files/`、`*.log`、`__pycache__/` 等。

## 技术要点

- UDP Socket 编程
- Go-Back-N 滑动窗口协议
- CRC-CCITT 校验
- 累计 ACK
- 超时定时器
- PDU 丢失与损坏模拟
- 多线程接收 ACK / 数据 PDU
- 多进程安全日志写入
- 日志统计分析和图表展示
