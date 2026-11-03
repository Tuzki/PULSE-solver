#!/usr/bin/env python3
"""Strict Stage C native PEVT, numerical counters and optional NPZ replay comparison.

This is an offline comparator, NOT a performance benchmark. Running it after
both candidate and baseline simulations is mandatory; it does not launch them.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

HEADER = struct.Struct('<8sHHI')
SECTION = struct.Struct('<IIQQQ32s')


def sha_file(reader):
    digest = hashlib.sha256()
    while block := reader.read(1024 * 1024):
        digest.update(block)
    return digest.hexdigest()


def inspect_pevt(file: Path):
    sections = {}
    with file.open('rb') as stream:
        raw = stream.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError(f'{file}: short header')
        magic, version, count, flags = HEADER.unpack(raw)
        if (magic, version, flags) != (b'PULSEES1', 1, 0) or not 9 <= count <= 10:
            raise ValueError(f'{file}: invalid PEVT version/header')
        for _ in range(count):
            raw = stream.read(SECTION.size)
            if len(raw) != SECTION.size:
                raise ValueError(f'{file}: short section header')
            kind, codec, stored, rawsize, records, expected = SECTION.unpack(raw)
            if kind in sections or not 1 <= kind <= 10 or codec or stored != rawsize:
                raise ValueError(f'{file}: invalid/duplicate section {kind}')
            digest = hashlib.sha256()
            remaining = stored
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError(f'{file}: truncated section {kind}')
                digest.update(chunk)
                remaining -= len(chunk)
            if digest.digest() != expected:
                raise ValueError(f'{file}: corrupt SHA256 in section {kind}')
            sections[kind] = {'records': records, 'payload_sha256': digest.hexdigest(), 'size': stored}
        if stream.read(1):
            raise ValueError(f'{file}: trailing bytes')
    for kind in range(1, 10):
        if kind not in sections:
            raise ValueError(f'{file}: required section {kind} absent')
    return sections


def wave_members(path: Path):
    result = {}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f'{path}: duplicate NPZ member names')
        for item in names:
            if item.endswith('/'):
                continue
            with archive.open(item) as stream:
                digest = sha_file(stream)
            result[item] = digest
    return result


def report(path: Path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('status') != 'COMPLETED':
        raise ValueError(f'{path}: not COMPLETED')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True, help='Baseline out.pevt')
    parser.add_argument('--candidate', type=Path, required=True, help='Stage C out.pevt')
    parser.add_argument('--baseline-report', type=Path)
    parser.add_argument('--candidate-report', type=Path)
    parser.add_argument('--baseline-wave', type=Path, help='Replayed NPZ file from baseline')
    parser.add_argument('--candidate-wave', type=Path, help='Replayed NPZ file from Stage C')
    parser.add_argument('--out', type=Path, help='Write JSON evidence')
    args = parser.parse_args()
    old, new = inspect_pevt(args.baseline), inspect_pevt(args.candidate)
    # Section 1 contains runtime/provenance statistics and may differ.
    simulation = sorted((set(old) | set(new)) - {1})
    differences = [kind for kind in simulation if old.get(kind) != new.get(kind)]
    result = {
        'baseline_pevt': str(args.baseline), 'candidate_pevt': str(args.candidate),
        'baseline_sections': old, 'candidate_sections': new,
        'simulation_sections_identical': not differences,
        'different_simulation_sections': differences,
        'metadata_section_1_identical': old.get(1) == new.get(1),
    }
    if bool(args.baseline_report) != bool(args.candidate_report):
        parser.error('specify both report paths or neither')
    if args.baseline_report:
        a, b = report(args.baseline_report), report(args.candidate_report)
        must_equal = ('transactions', 'root_queries', 'root_failures',
                      'mode_compilations', 'microsteps', 'matrix_exponentials',
                      'event_records_total', 'analog_channels', 'digital_channels',
                      'simulated_seconds', 'effective_SAVE_DT', 'effective_T_END',
                      'T_atom', 'software_final_outputs', 'software_states',
                      'original_equation_cache')
        bad = [key for key in must_equal if key not in a or key not in b or a[key] != b[key]]
        result['report_disagreements'] = bad
        result['report_required_fields'] = list(must_equal)
    if bool(args.baseline_wave) != bool(args.candidate_wave):
        parser.error('specify both replay wave paths or neither')
    if args.baseline_wave:
        a, b = wave_members(args.baseline_wave), wave_members(args.candidate_wave)
        result['waveform_members'] = len(a)
        result['waveform_members_different'] = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        result['all_waveform_bytes_identical'] = not result['waveform_members_different']
    failed = bool(differences or result.get('report_disagreements') or result.get('waveform_members_different'))
    result['status'] = 'FAIL' if failed else 'PASS_SCOPED_COMPARISON'
    body = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(body, encoding='utf-8')
    print(body)
    return int(failed)

if __name__ == '__main__':
    sys.exit(main())
