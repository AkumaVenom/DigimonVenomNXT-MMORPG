"""Create a clean source+asset ZIP; never package live saves or hosting secrets."""
from pathlib import Path
import argparse
import hashlib
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=('venom','tools','tests','data','assets','docs')
ROOT_NAMES={'README.md','PASSWORD_SETUP_FIX.txt','pytest.ini','.gitignore'}


def package(output:Path):
    files=[p for name in DIRECTORIES for p in (ROOT/name).rglob('*')
           if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    files += [p for p in ROOT.iterdir() if p.is_file() and
              (p.name in ROOT_NAMES or p.suffix=='.bat' or p.name.startswith('requirements'))]
    folded=set()
    for p in files:
        name=p.relative_to(ROOT).as_posix()
        if name.casefold() in folded:
            raise ValueError(f'Windows case-insensitive path collision: {name}')
        folded.add(name.casefold())
        if p.suffix in {'.pem','.key','.sqlite3','.db'}:
            raise ValueError(f'Refusing to package possible secret/live save: {name}')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for path in sorted(files):
            archive.write(path,Path('DigimonVenomNXT')/path.relative_to(ROOT))
    with zipfile.ZipFile(output) as archive:
        corrupt=archive.testzip()
        if corrupt:raise RuntimeError(f'ZIP integrity error: {corrupt}')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    print(f'{output.name}: {len(files)} files, {output.stat().st_size:,} bytes\nSHA256 {digest}')
    return digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();package(args.output.resolve())

if __name__=='__main__':main()
