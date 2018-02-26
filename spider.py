import json
from hashlib import md5
from multiprocessing import Pool
from urllib.parse import urlencode
import chardet
import re
import os
import pymongo
import requests
from bs4 import BeautifulSoup
from requests import RequestException
from config import *

client = pymongo.MongoClient(MONGO_URL, )
db = client[MONGO_DB]


def get_page_index(offset, keyword):
    data = {
        'offset': offset,
        'format': 'json',
        'keyword': keyword,
        'autoload': 'true',
        'count': 20,
        'cur_tab': 3,
        'from': 'gallery'
    }
    url = 'https://www.toutiao.com/search_content/?' + urlencode(data)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        return None
    except RequestException:
        return None


def parse_page_index(html):
    data = json.loads(html)
    if data and 'data' in data.keys():
        for item in data.get('data'):
            yield item.get('article_url')


def get_page_detail(url):
    try:
        response = requests.get(url, allow_redirects=True, timeout=0.5)
        if response.status_code == 200:
            encoding = chardet.detect(response.content)['encoding']
            response.encoding = encoding
            return response.text
        return None
    except RequestException:
        print('请求详情页出错', url)
        return None


def parse_page_detail(html, url):
    soup = BeautifulSoup(html, 'lxml')
    title = soup.select('title')[0].get_text() if soup.select('title') else ''
    print(title)
    html = html.replace('\\\\', '\\')
    html = html.replace(r'\"', '"')
    html = html.replace(r'\/', '/')
    pattern = re.compile(r'gallery: JSON.parse\("(.*?)"\)', re.S)
    result = re.search(pattern, html)
    if result:
        data = json.loads(result.group(1))
        if data and 'sub_images' in data.keys():
            sub_images = data.get('sub_images')
            images = [item.get('url') for item in sub_images]
            for image in images:
                download_image(image, title)
            return {
                'title': title,
                'url': url,
                'images': images
            }


def save_to_mongo(result):
    if db[MONGO_TABLE].insert(result):
        print('存储到MongoDB成功', result)
        return True
    return False


def download_image(url, title):
    print('正在下载', url)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            save_image(response.content, title)
        return None
    except RequestException:
        print('请求图片出错', url)
        return None
    except FileNotFoundError:
        print('保存到本地失败', url)
        return None


def save_image(content, title):
    image_dir = os.getcwd() + os.path.sep + 'images' + os.path.sep + title
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)
    file_path = '{0}{1}{2}.{3}'.format(image_dir, os.path.sep,
                                       md5(content).hexdigest(), 'jpg')
    if not os.path.exists(file_path):
        with open(file_path, 'wb') as f:
            f.write(content)
            f.close()


def main(offset):
    html = get_page_index(offset, KEYWORD)
    if not html:
        return
    for url in parse_page_index(html):
        url = url.replace('group/', 'a')
        html = get_page_detail(url)
        if not html:
            return
        result = parse_page_detail(html, url)
        if result:
            save_to_mongo(result)


if __name__ == '__main__':
    pool = Pool()
    pool.map(main, [offset for offset in range(GROUP_START, GROUP_END + 1, 20)])
