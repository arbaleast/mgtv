import os
import requests
import sys # 接受外部传参

# 发送HTTP请求并获取JSON数据
def get_live_url(channel_id):
    url = f'http://mpp.liveapi.mgtv.com/v1/epg/turnplay/getLivePlayUrlMPP?version=PCweb_1.0&platform=1&buss_id=2000001&channel_id={channel_id}'
    # print(channel_id, url)
    response = requests.get(url)
    data = response.json()
    return data.get('data', {}).get('url')

# 更新单个m3u8文件的URL
def update_single_m3u8_file(url, filename):
    m3u8_dir = 'm3u8'
    filepath = os.path.join(m3u8_dir, filename)
    with open(filepath, 'r') as file:
        lines = file.readlines()
    with open(filepath, 'w') as file:
        for line in lines:
            if line.startswith('http'):
                file.write(url + '\n')
            else:
                file.write(line)

# 示例：假设要更新344频道的URL
channel_id = sys.argv[1]
filename = sys.argv[2]

live_url = get_live_url(channel_id)
print(live_url)

if live_url:
    update_single_m3u8_file(live_url, filename)
    # print('文件 {filename} 的URL已更新为：')
    # print(f'{live_url}\n')
else:
    print('未能获取到直播URL, 请检查网络或参数设置。')
