"""V6 rainfall-only experiment entry point."""
import argparse
from pathlib import Path

from common import DEFAULT_OUTPUT
from experiment import build,verify

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','verify'])
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    if args.command=='build':build(args.output)
    else:print(verify(args.output))
