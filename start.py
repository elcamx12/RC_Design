"""
RC_Design 앱 실행 스크립트
- 빈 포트 자동 탐색 (8501~8600)
- 브라우저 자동 열기
- 사용법: python start.py  또는  RC_Design.hta 더블클릭
"""
import os
import sys
import socket
import webbrowser
import threading
import time


def find_free_port(start=8501, end=8600):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    return start


def main():
    port = find_free_port()
    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.py')

    def _open_browser():
        time.sleep(3)
        webbrowser.open(f'http://localhost:{port}')

    threading.Thread(target=_open_browser, daemon=True).start()

    import streamlit.web.cli as stcli
    sys.argv = [
        'streamlit', 'run', app_path,
        f'--server.port={port}',
        '--server.headless=true',
        '--browser.gatherUsageStats=false',
    ]
    stcli.main()


if __name__ == '__main__':
    main()
