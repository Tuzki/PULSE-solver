#!/usr/bin/env python3
"""Compare native replay arrays including IEEE bit patterns, without tolerances."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def array_hashes(path):
    # .npy members contain dtype/shape headers and uncompressed numerical bytes.
    # ZIP timestamps/compression cannot affect this comparison.
    rows = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            h = hashlib.sha256()
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(1 << 20), b''):
                    h.update(block)
            rows[name] = {'uncompressed_bytes': archive.getinfo(name).file_size, 'sha256': h.hexdigest()}
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    old, new = array_hashes(a.baseline), array_hashes(a.candidate)
    result = {'baseline': str(a.baseline), 'candidate': str(a.candidate),
              'bitwise_equal': old == new, 'baseline_members': old, 'candidate_members': new}
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    assert old == new, 'Reconstructed waveform arrays differ; inspect evidence'
    print(json.dumps({'bitwise_equal': True, 'members': len(new)}))


if __name__ == '__main__':
    main()
