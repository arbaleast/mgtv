import subprocess


def generate_m3u8_stream_with_info(urls, info_list):
    if len(urls) != len(info_list):
        raise ValueError("URLs and info list should have the same length")

    m3u8_content = "#EXTM3U x-tvg-url=\"https://mirror.ghproxy.com/https://raw.githubusercontent.com/arbaleast/mgtv/main/mgtv.xml\"\n"
    for index, (url, info) in enumerate(zip(urls, info_list)):
        tvg_id = info.get("tvg-id", "")
        tvg_name = info.get("tvg-name", "")
        tvg_logo = info.get("tvg-logo", "")
        m3u8_content += f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-logo="{tvg_logo}" group-title=\"湖南\",{tvg_name} \n{url}\n'

    with open("mgtv.m3u", "w") as file:
        file.write(m3u8_content)


stream_info_list = [
    {
        "tvg-id": "280",
        "tvg-name": "湖南经视",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/hnjs.png",
        "filename": "hn01.m3u8",
    },
    {
        "tvg-id": "346",
        "tvg-name": "湖南都市",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/hnds.png",
        "filename": "hn02.m3u8",
    },
    {
        "tvg-id": "484",
        "tvg-name": "湖南电视剧",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/hndsj.png",
        "filename": "hn03.m3u8",
    },
    {
        "tvg-id": "261",
        "tvg-name": "湖南公共",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/hngg.png",
        "filename": "hn04.m3u8",
    },
    {
        "tvg-id": "229",
        "tvg-name": "湖南国际",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/hngj.png",
        "filename": "hn05.m3u8",
    },
    {
        "tvg-id": "344",
        "tvg-name": "湖南娱乐",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/hnyl.png",
        "filename": "hn06.m3u8",
    },
    {
        "tvg-id": "267",
        "tvg-name": "快乐购",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/hnklg.png",
        "filename": "hn07.m3u8",
    },
    {
        "tvg-id": "578",
        "tvg-name": "茶频道",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/cpd.png",
        "filename": "hn08.m3u8",
    },
    {
        "tvg-id": "316",
        "tvg-name": "金鹰纪实",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/jyjs.png",
        "filename": "hn09.m3u8",
    },
    {
        "tvg-id": "287",
        "tvg-name": "金鹰卡通",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/jykt.png",
        "filename": "hn10.m3u8",
    },
    {
        "tvg-id": "218",
        "tvg-name": "快乐垂钓",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/klcd.png",
        "filename": "hn11.m3u8",
    },
    {
        "tvg-id": "329",
        "tvg-name": "先锋乒羽",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/xfpy.png",
        "filename": "hn12.m3u8",
    },
    {
        "tvg-id": "269",
        "tvg-name": "长沙新闻",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/csxw.png",
        "filename": "hn13.m3u8",
    },
    {
        "tvg-id": "254",
        "tvg-name": "长沙政法",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/cszf.png",
        "filename": "hn14.m3u8",
    },
    {
        "tvg-id": "230",
        "tvg-name": "长沙女性",
        "tvg-logo": "https://cdn.jsdelivr.net/gh/arbaleast/mgtv@main/logo/csnx.png",
        "filename": "hn15.m3u8",
    },
]


# 示例 URL 列表和信息列表
def generate_live_stream_urls(stream_info_list):
    live_stream_urls = []
    for stream_info in stream_info_list:
        tvg_id = stream_info.get("tvg-id")
        filename = stream_info.get("filename")
        # 调用另一个脚本，传入 tvg-id 参数
        process = subprocess.Popen(
            ["python", "src/utils/update_url.py", tvg_id, filename],
            stdout=subprocess.PIPE,
        )
        output, error = process.communicate()
        # 输出中应该包含直播流链接，你可以根据实际情况进行解析
        live_stream_url = output.decode("utf-8").strip()
        live_stream_urls.append(live_stream_url)
    return live_stream_urls


# 示例调用
live_stream_urls = generate_live_stream_urls(stream_info_list)
print(live_stream_urls)

generate_m3u8_stream_with_info(live_stream_urls, stream_info_list)

print("mgtv.m3u8文件已生成。")
