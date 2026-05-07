from pathlib import Path
import platform
import subprocess


def to_wsl_path(path: Path) -> str:
    raw = str(path.resolve()).replace("\\", "/")

    if len(raw) >= 2 and raw[1] == ":":
        drive = raw[0].lower()
        rest = raw[2:]
        return f"/mnt/{drive}{rest}"

    return raw


def run_ocr(input_pdf: Path, output_pdf: Path) -> bool:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    system_name = platform.system().lower()

    if "windows" in system_name:
        input_wsl = to_wsl_path(input_pdf)
        output_wsl = to_wsl_path(output_pdf)

        cmd = [
            "C:\\Windows\\System32\\wsl.exe",
            "bash",
            "-lc",
            f'/home/loxi1/venvs/ocrpdf/bin/ocrmypdf -l spa --force-ocr "{input_wsl}" "{output_wsl}"',
        ]
    else:
        cmd = [
            "ocrmypdf",
            "-l",
            "spa",
            "--force-ocr",
            str(input_pdf),
            str(output_pdf),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        print("[OCR ERROR STDOUT]")
        print(result.stdout)
        print("[OCR ERROR STDERR]")
        print(result.stderr)
        return False

    return True