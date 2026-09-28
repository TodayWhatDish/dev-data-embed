"""개발 서버 포트를 점유 중인 프로세스를 정리한다.

--reload 로 뜬 옛 uvicorn 이 창을 닫아도 남아 포트를 물고 있으면, 새로 띄운 서버가 아니라
그 옛 프로세스가 계속 응답해 코드를 고쳐도 반영이 안 된 것처럼 보인다. 서버 실행 전에 늘 비운다.
lsof 는 Windows 에 없어서 OS 별로 나눈다.

    python scripts/free_port.py 8000
"""

import subprocess
import sys

DEFAULT_PORT = 8000


def _kill_windows(pid: str) -> None:
    """--reload 워커는 부모(리로더)가 죽어도 소켓을 물고 살아남는데, netstat 은 그 소켓을 죽은 부모 PID 로
    보여준다 - 그 PID 만 끄면 아무 일도 안 일어난다. 그래서 그 PID 를 부모로 둔 자식까지 같이 끈다."""
    children = f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"
    subprocess.run(["powershell", "-NoProfile", "-Command", children], capture_output=True)
    subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)


def free_port(port: int = DEFAULT_PORT) -> None:
    if sys.platform == "win32":
        # 한글 Windows 의 netstat 헤더는 cp949 라 디코딩이 깨질 수 있다 - 쓰는 칸(포트·PID)은 ASCII 라 무시해도 된다
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace").stdout
        pids = {line.split()[-1] for line in out.splitlines() if f":{port} " in line and "LISTENING" in line}
        for pid in pids:
            _kill_windows(pid)
    else:
        out = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True).stdout
        pids = set(out.split())
        for pid in pids:
            subprocess.run(["kill", "-9", pid], capture_output=True)
    print(f"포트 {port}: {'정리함 ' + ', '.join(sorted(pids)) if pids else '비어 있음'}")


if __name__ == "__main__":
    free_port(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
