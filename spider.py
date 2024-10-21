import requests
import logging
import inspect
import os
# from Crypto.Cipher import AES
import subprocess
# import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


class Logger:
    def __init__(self, log_file='app.log'):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8')
            ]
        )

    def log_message(self, level, message):
        # 获取调用 log_message 的上一级函数名
        current_function = inspect.stack()[2][3]
        # 创建日志信息
        log_msg = f"{current_function} - {message}"
        # 根据日志级别记录日志
        if level == "debug":
            logging.debug(log_msg)
        elif level == "info":
            logging.info(log_msg)
        elif level == "warning":
            logging.warning(log_msg)
        elif level == "error":
            logging.error(log_msg)
        elif level == "critical":
            logging.critical(log_msg)


class CourseManager:
    def __init__(self, logger):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        })
        self.logger = logger
        # 预留的属性
        self.id = None
        self.current_dir = None
        self.key = None

    def log_message(self, level, message):
        # 直接调用 Logger 的 log_message 方法
        self.logger.log_message(level, message)

    def login(self, username, password):
        try:
            login_url = 'http://www.wshenan.com/client/userLogin.saction'
            payload = {
                "username": username,
                "pwd": password
            }
            resp = self.session.post(login_url, data=payload)
            if resp.status_code == 200:
                response_data = resp.json()
                # 获取课程时需要传入用户ID
                self.id = response_data.get('id')
                self.log_message('info', resp.text)
            else:
                self.log_message('error', resp.text)
        except Exception as e:
            self.log_message('error', f"Failed: {e}")

        self.key = self.session.get(
            'https://wshenan.s3.cn-northwest-1.amazonaws.com.cn/MU/video.key').text
        self.log_message('info', f'[key] self.key')

    def add_cookie(self, kv: dict):
        """预留方法，用于添加cookie

        Args:
            kv (dict): cookie的键值对
        """
        self.session.cookies.set(**kv)
        self.log_message('info', str(kv))

    def get_courses_list(self, pageSize=100):
        """获取课程列表

        Args:
            pageSize (int, optional): 每页课程数量. Defaults to 100.

        Returns:
            dict: 课程列表
        """
        courses_url = 'http://www.wshenan.com/client/queryCoursesByPage.saction'
        payload = {
            "env": "",
            "type": "",
            "level": "",
            "page": "1",
            "pageSize": str(pageSize)
        }
        resp = self.session.post(courses_url, data=payload)
        self.log_message('info', resp.text)
        return resp.json()

    def get_course_detail(self, course_id: int):
        """获取课程详情

        Args:
            course_id (int): 课程ID

        Returns:
            dict: 课程详情信息
        """
        if self.id is None:
            self.log_message('error', "用户ID不可用")
            return None

        course_detail_url = 'http://www.wshenan.com/client/getCourseDetail.saction'
        payload = {
            "outlineId": course_id,
            "userId": self.id
        }
        resp = self.session.post(course_detail_url, data=payload)
        self.log_message('info', resp.text)
        for courseinfo in resp.json().get('courseList'):
            if courseinfo.get('type') == 1:
                print(courseinfo.get('name'))
            else:
                print('\t' + f'[{courseinfo.get('id')}]' +
                      courseinfo.get('name'))
        return resp.json()

    def get_m3u8(self, video_list: dict, video_ids: list):
        """获取m3u8文件
        这段代码可以拿去喂狗
        """

        # 下载 video_ids 对应的 m3u8 文件到本地
        for downid in video_ids:
            for id in video_list['courseList']:
                if str(downid) == str(id.get('id')):
                    video_m3u8_url = id.get('video')
                    video_name = id.get('name')
                    video_info = id
                    break
            m3u8_content = self.session.get(video_m3u8_url)
            self.log_message('info', f'Download .m3u8 {video_info}')
            with open(f'{self.current_dir}/{video_name}.m3u8', 'wb') as f:
                f.write(m3u8_content.content)

            # 妈的气死我了 写错了
            # ts_files = []
            # baseurl = video_m3u8_url.rsplit('/', 1)[0]
            # for line in m3u8_content.content.splitlines():
            #     if line.endswith('.ts'):
            #         ts_files.append(baseurl + '/' + line)

    # ffmpeg 转 m3u8 为 mp4
    def convert_m3u8_to_mp4(self, m3u8_file_path: str, output_file_path: str, save_path=None):
        if save_path is None:
            save_path = self.current_dir
        # 判断url后缀
        file_end = m3u8_file_path.rsplit('.')[-1]
        file_end = file_end.strip('"')
        if file_end != 'm3u8':
            print('\n'*20)
            print('='*20)
            print(f'不支持下载未加密的{file_end}视频，因为代码是这样写的，只能下m3u8')
            os._exit(0)
        try:
            self.log_message('info',
                             f'Start Convert {m3u8_file_path} to {output_file_path}')
            command = ['ffmpeg', '-i',
                       m3u8_file_path, '-c', 'copy',
                       f'{save_path}/{output_file_path}'
                       ]
            self.log_message('info', command)

            subprocess.run(command, check=True)
        except Exception as e:
            self.log_message('error',
                             f'Convert {m3u8_file_path} to {output_file_path} failed: {e}')

    def convert_multiple_m3u8(self, m3u8_videos: dict, max_workers: int = 4):
        # if save_path is None:
        #     save_path = self.current_dir
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_video = {
                executor.submit(self.convert_m3u8_to_mp4, m3u8_file, output_file): (m3u8_file, output_file)
                for m3u8_file, output_file in m3u8_videos.items()
            }

            for future in as_completed(future_to_video):
                m3u8_file, output_file = future_to_video[future]
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(
                        f'ffmpeg {m3u8_file} to {output_file}: {e}'
                    )


if __name__ == "__main__":
    logger = Logger()
    manager = CourseManager(logger)
    user = input('账号：')
    pw = input('密码：')
    manager.login(user, pw)
    courses_list = manager.get_courses_list()
    for lesson in courses_list['rows']:
        print(f'{lesson["id"]},{lesson["name"]}')
    print('='*20)
    course_id = int(input('请选择课程ID：'))
    for lesson in courses_list['rows']:
        if lesson['id'] == course_id:
            manager.current_dir = lesson['name']
            os.makedirs(lesson['name'], exist_ok=True)
            if not os.path.exists(lesson['name']):  # 判断文件夹是否存在
                os.makedirs(lesson['name'])
            break

    print('\n'*20)
    video_list = manager.get_course_detail(course_id)
    print('='*30)
    print('已获取课程列表，输入需要下载的课程ID号，多个ID号用英文逗号隔开，全部下载输入A')
    print('例如：3,4,5,7-13,104-150,178')
    select_id = input('输入需下载的课程ID号（全部下载输入A）：')
    if select_id != 'A':
        if input('是否全部下载？ (Y)/n') == 'n':
            input('你必须全部下载！ [Enter]')

    # print(video_list)
    download_dict = {}
    # 连接一下视频名和章节名
    for c1 in video_list['courseList']:
        if c1['type'] == 0:
            for c2 in video_list['courseList']:
                if c1['pId'] == c2['id']:
                    download_dict[f"{c1['video']}"] = f'{c2["name"]}_{c1["name"]}.mp4'
    manager.convert_multiple_m3u8(download_dict)