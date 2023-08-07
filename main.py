import traceback
from time import time, sleep
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from pathlib import Path
import winreg

Headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}


def get_windows_proxy():
    try:
        # 打开 Windows 注册表项
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')

        # 获取代理开关状态
        proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')

        if proxy_enable:
            # 获取代理地址和端口号
            proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
            return proxy_server
        else:
            return None

    except Exception as e:
        print("获取 Windows 系统代理失败：", e)
        return None


# 获取系统代理
proxy = get_windows_proxy()
if proxy:
    proxy = {
        "http": proxy,
        "https": proxy,
    }
else:
    proxy = {
        "http": None,
        "https": None,
    }


class DownloadTask:
    def __init__(self, url, block_nums, file_name=None, save_path=None):
        # 初始化参数
        self.divisional_ranges = []
        self.url = url
        self.blockNums = block_nums
        self.every_process = []
        self.total_process = 0

        # 获取文件大小
        head = requests.head(self.url, headers=Headers, proxies=proxy).headers
        self.fileSize = int(head["content-length"])
        print(self.fileSize)

        # 获取文件名
        if not file_name:
            try:
                self.fileName = head["content-disposition"]
                print(self.fileName)
            except KeyError:
                # 处理没有文件名的情况
                # print(f"KeyError:{err}")
                self.fileName = Path(url).name
                print(self.fileName)
            except Exception as e:
                # 什么都 Get 不到的情况
                # TODO Report
                traceback.print_exc()
                content_type = head["content-type"].split('/')[-1]
                self.fileName = f"downloaded_file{int(time())}.{content_type}"
                # print(file_name)
        else:
            self.fileName = file_name

        # 判断路径是否存在并创建路径
        if not save_path:
            self.savePath = Path(__file__)
            self.savePath = self.savePath.parent
            # print(save_path)
        else:
            try:
                self.savePath = Path(save_path)
                if not self.savePath.exists():
                    self.savePath.mkdir()
            except:
                # TODO 路径不对就别干了
                return

        # 文件绝对路径(合并file_name和save_path)
        self.fileResolve = self.savePath / self.fileName
        self.fileInfoResolve = Path(self.savePath / f"~${self.fileName}")
        print(f"绝对路径:{self.fileResolve}")

    def calc_divisional_range(self):
        step = self.fileSize // self.blockNums  # 每块大小
        # print(f"Step:{step}")

        arr = list(range(0, self.fileSize, step))

        # 否则线程数可能会不按预期地少一个
        if self.fileSize % self.blockNums == 0:
            arr.append(self.fileSize)

        # print(f"Arr:{arr}")
        step_list = []
        for i in range(len(arr) - 1):
            s_pos, e_pos = arr[i], arr[i + 1] - 1
            step_list.append([s_pos, e_pos])
        step_list[-1][-1] = self.fileSize - 1
        # print(f"StepList:{step_list}")
        return step_list

    def download_worker(self, number, s_pos, e_pos):
        download_headers = {"Range": f"bytes={s_pos}-{e_pos}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}
        res = requests.get(self.url, headers=download_headers, proxies=proxy, stream=True, timeout=60)
        with open(self.fileResolve, "rb+") as f:
            f.seek(s_pos)
            for chunk in res.iter_content(chunk_size=65536):  # iter_content 的单位是字节, 即每64K写一次文件
                if chunk:
                    f.write(chunk)
                    self.every_process[number] += 65536

        self.every_process[number] = 0

    def __get_readable_size(self, size):
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        unit_index = 0
        K = 1024.0
        while size >= K:
            size = size / K
            unit_index += 1
        return "%.2f %s" % (size, units[unit_index])

    def download_minitor(self):
        p = self.calc_divisional_range()
        l = 0

        while self.total_process != self.fileSize:
            _ = ""
            t = 0
            self.total_process = self.fileResolve.stat().st_size
            # 写入记录文件
            with open(self.fileInfoResolve, "w+") as f:
                try:
                    # print(self.divisional_ranges, self.every_process)
                    for n in range(self.blockNums):
                        _ += f"{str(self.divisional_ranges[n][0] + self.every_process[n])}|{self.divisional_ranges[n][1]}\n"
                    # print(_)
                    f.write(_)
                    f.flush()
                    # 计算速度
                    for i, o in enumerate(self.every_process):
                        k = p[i][0]
                        u = self.divisional_ranges[i][0]
                        t += (o+u) - k
                    # print(f"Debug,l:{l},t:{self.total_process}")
                    speed = self.__get_readable_size(t - l)
                    # 打印信息
                    print("\r",f"P:{round(t / self.fileSize, 2)}, {t}|{self.fileSize}", speed , end="",flush=True)
                    f.close()
                    l = t
                    sleep(1)  # 每 N 秒检测一次
                except Exception as e:
                    print(e)

        print("\nFinished!")

    def start(self):
        # 开始下载
        if self.fileSize:
            if not self.fileInfoResolve.exists():  # 不存在记录文件的话就从头下载
                # 计算每个分块
                self.divisional_ranges = self.calc_divisional_range()
                # 创建空文件
                with open(self.fileResolve, "wb") as f:
                    pass
                # # 创建记录文件
                # with open(self.fileInfoResolve, "wb") as f:
                #     pass
                # # 隐藏记录文件
                #
                # 创建线程池
                with ThreadPoolExecutor() as p:
                    futures = []
                    for number, _ in enumerate(self.divisional_ranges, start=0):
                        s_pos = _[0]
                        e_pos = _[1]
                        self.every_process.append(0)
                        print(number, s_pos, e_pos)
                        futures.append(p.submit(self.download_worker, number, s_pos, e_pos))
                    # 增加检测线程
                    futures.append(p.submit(self.download_minitor))
                    # 等待所有任务执行完毕
                    as_completed(futures)
                    # 删除记录文件
                    try:
                        Path.unlink(self.fileInfoResolve)
                    except:
                        pass

            else:# 记录文件存在，断点续传
                with open(self.fileInfoResolve, "r") as f:
                    with ThreadPoolExecutor() as p:
                        futures = []
                        for number, i in enumerate(f.readlines()):
                            i = i.split("|")
                            s_pos = int(i[0])
                            e_pos = int(i[1][:-1])  # 去掉最后的\n
                            self.divisional_ranges.append([s_pos, e_pos])
                            self.every_process.append(0)
                            print("断点续传:", number, s_pos, e_pos)
                            futures.append(p.submit(self.download_worker, number, s_pos, e_pos))
                        # 关闭文件，以防万一
                        f.close()
                        # 增加检测线程
                        futures.append(p.submit(self.download_minitor))
                        # 等待所有任务执行完毕
                        as_completed(futures)
                        # 删除记录文件
                        try:
                            Path.unlink(self.fileInfoResolve)
                        except:
                            pass


# Url = "https://download.jetbrains.com.cn/python/pycharm-professional-2023.1.1.exe"
Url = "https://dldir1.qq.com/qqfile/qq/QQNT/342b8a70/QQ9.9.1.15489_x64.exe"
task = DownloadTask(Url, 8)
task.start()
# task.download_minitor()
