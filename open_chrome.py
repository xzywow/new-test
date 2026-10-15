"""Open ordinary Chrome with its own existing profiles; no automation attachment."""
import argparse
import re
import subprocess
from chrome_diagnostics import find_chrome
from dianxiaomi_reader import source_identity


def open_existing_chrome(product_url=None, profile=None):
    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError('未找到 Google Chrome，请先安装桌面版 Chrome。')
    command = [str(chrome)]
    if profile:
        # Internal directory name, NOT Google account name, email or full path.
        if not re.fullmatch(r'Default|Profile [1-9][0-9]*', profile):
            raise ValueError('配置目录只支持 Default 或 Profile 1 等名称。')
        command.append('--profile-directory=' + profile)
    if product_url:
        source, product_id = source_identity(product_url)
        if not product_id or not source.startswith('https://'):
            raise ValueError('请提供 HTTPS 速卖通商品详情链接。')
        command.append(source)
    else:
        command.append('chrome://newtab/')
    # No custom user-data-dir, debugging port, profile copying or login inspection.
    subprocess.Popen(command)


def main():
    parser = argparse.ArgumentParser(description='打开日常 Chrome，沿用 Chrome 自己保存的账号与插件')
    parser.add_argument('--product-url')
    parser.add_argument('--profile', help='可选：chrome://version 的个人资料路径末尾，如 Default 或 Profile 1')
    args = parser.parse_args()
    try:
        open_existing_chrome(args.product_url, args.profile)
    except (RuntimeError, ValueError, OSError) as error:
        print('打开失败：', str(error))
        return 1
    print('已发送打开请求，请在 Chrome 中确认右上角账号。')
    print('未指定 --profile 时由 Chrome 选择已有资料；若账号不对，请手动切换。')
    print('此模式不接管浏览器、不读取登录状态；请手动使用官方插件采集一个商品。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
