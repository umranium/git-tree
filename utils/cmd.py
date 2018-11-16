import subprocess
from typing import List, Iterator


def output(args: List[str], decode_ascii: bool = True, strip: bool = True) -> Iterator[str]:
    process = subprocess.Popen(args, stdout=subprocess.PIPE)
    for line in process.stdout.readlines():
        if decode_ascii:
            line = line.decode('ascii')
        if strip:
            line = line.strip()
        yield line
