#!/usr/bin/env python3
"""按 Git tree 逐文件拉取 server/ 到 /opt/veyra/server（绕开 git 传输）。

本机网络实测：
  - github.com 的 git 传输      1~8 KB/s（46MB 仓库 sparse checkout 要几十分钟）
  - api.github.com blob 接口    ~100 KB/s，但单个响应超过 ~480KB 会被掐断（IncompleteRead）；
                                且 base64 多 33% 流量
  - cdn.jsdelivr.net/gh/…@sha  ~120 KB/s，可绕开 480KB 上限（4.3 秒拿完 503KB 的 webui.html）

所以：先用 jsDelivr 取文件内容（sha 固定的不可变地址），失败或内容校验不符再退回 API blob。
本地文件先算 git blob sha1 比对，一致直接跳过——大文件不用每次部署重下。

用法：
    GITHUB_SHA=<sha> GITHUB_REPOSITORY=owner/repo GITHUB_TOKEN=<token> python3 sync-server.py
可选环境变量：
    DEST        目标目录，默认 /opt/veyra/server
    PREFIX      仓库里对应 DEST 的目录前缀，默认 server/
    EXTRA_PATHS 额外要拉的文件（逗号分隔，写进 DEST 下的同名相对路径）
    RETRIES     单文件重试次数，默认 6
    OFFLINE_CDN 设 1 则不用 jsDelivr，只走 API
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

API = 'https://api.github.com'
CDN = 'https://cdn.jsdelivr.net/gh'
REPO = os.environ['GITHUB_REPOSITORY']
SHA = os.environ['GITHUB_SHA']
TOKEN = os.environ['GITHUB_TOKEN']
DEST = os.environ.get('DEST', '/opt/veyra/server')
PREFIX = os.environ.get('PREFIX', 'server/')
EXTRA = [p.strip() for p in os.environ.get('EXTRA_PATHS', '').split(',') if p.strip()]
RETRIES = int(os.environ.get('RETRIES', '6'))
USE_CDN = os.environ.get('OFFLINE_CDN', '0') != '1'


def fetch(url, accept, attempts=RETRIES):
    """取一个 URL 的完整字节；长度对不上就重试（GitHub 边缘会中途掐断）。"""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            headers = {'User-Agent': 'veyra-deploy', 'Accept': accept}
            if url.startswith(API):
                headers['Authorization'] = 'Bearer ' + TOKEN
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=180) as response:
                body = response.read()
                expected = response.headers.get('Content-Length')
            if expected is not None and len(body) != int(expected):
                raise IOError(f'只收到 {len(body)}/{expected} 字节')
            return body
        except Exception as error:  # noqa: BLE001 - 网络抖动一律重试
            last = error
            wait = min(2 ** attempt, 20)
            print(f'  重试 {attempt}/{attempts}（{error}），{wait}s 后再来', file=sys.stderr)
            time.sleep(wait)
    raise IOError(f'{url} 重试 {attempts} 次仍失败: {last}')


def git_blob_sha1(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def local_matches(path, blob_sha):
    if not os.path.isfile(path):
        return False
    with open(path, 'rb') as handle:
        return git_blob_sha1(handle.read()) == blob_sha


def blob_bytes(path, blob_sha):
    """按优先级取文件内容，返回校验通过的字节。"""
    errors = []
    if USE_CDN:
        try:
            data = fetch(f'{CDN}/{REPO}@{SHA}/{path}', 'application/octet-stream')
            if git_blob_sha1(data) == blob_sha:
                return data
            errors.append(f'jsDelivr 内容校验不符（{len(data)} 字节）')
        except Exception as error:  # noqa: BLE001
            errors.append(f'jsDelivr: {error}')
    try:
        data = fetch(f'{API}/repos/{REPO}/git/blobs/{blob_sha}', 'application/vnd.github.raw')
        if git_blob_sha1(data) == blob_sha:
            return data
        errors.append(f'API 内容校验不符（{len(data)} 字节）')
    except Exception as error:  # noqa: BLE001
        errors.append(f'API: {error}')
    raise IOError(f'{path} 取不到正确内容 → ' + '；'.join(errors))


def main():
    commit = json.loads(fetch(f'{API}/repos/{REPO}/git/commits/{SHA}', 'application/vnd.github+json'))
    tree = json.loads(fetch(f'{API}/repos/{REPO}/git/trees/{commit["tree"]["sha"]}?recursive=1',
                            'application/vnd.github+json'))
    entries = [e for e in tree['tree']
               if e['type'] == 'blob' and (e['path'].startswith(PREFIX) or e['path'] in EXTRA)]
    if not entries:
        print('没匹配到任何文件，检查 PREFIX/EXTRA_PATHS', file=sys.stderr)
        return 1

    written = skipped = 0
    for entry in entries:
        path = entry['path']
        relative = path[len(PREFIX):] if path.startswith(PREFIX) else os.path.join('_extra', os.path.basename(path))
        target = os.path.join(DEST, relative)
        if local_matches(target, entry['sha']):
            skipped += 1
            print(f'跳过（未变）{path}')
            continue
        data = blob_bytes(path, entry['sha'])
        os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
        with open(target, 'wb') as handle:
            handle.write(data)
        if entry.get('mode') == '100755':
            os.chmod(target, 0o755)
        written += 1
        print(f'{path} -> {target} ({len(data)} bytes)')

    print(f'写入 {written} 个，跳过 {skipped} 个，目标 {DEST}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
