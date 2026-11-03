#!/usr/bin/env python3
"""Test transactionality, uniqueness, and no-clobber behavior on synthetic anchors.
This is NOT an integration/solver test.
"""
from __future__ import annotations
import tempfile
import pathlib
import apply_stage_d1 as impl

class Collector:
    def __init__(self):self.fragments={}
    def replace(self,path,old,new,label):self.fragments.setdefault(path,[]).append(old)
    def add(self,*args):pass


def run():
    package=pathlib.Path(__file__).resolve().parent.parent
    collector=Collector();impl.patch(collector,package)
    with tempfile.TemporaryDirectory() as tmp:
        root=pathlib.Path(tmp)
        for name,fragments in collector.fragments.items():
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text('\n\n'.join(fragments)+'\n',encoding='utf-8')
        p=impl.Patch(root);impl.patch(p,package)
        d=p.write(dry_run=True)
        assert not (root/'tests/stage_d1_regression.cpp').exists()
        assert len(d['changed_files'])==7,len(d['changed_files'])
        assert len(d['operations'])==13,len(d['operations'])
        p.write(dry_run=False)
        assert (root/'tests/stage_d1_regression.cpp').is_file()
        try:impl.patch(impl.Patch(root),package)
        except RuntimeError:pass
        else:raise AssertionError('duplicate patch did not refuse')
        # Failure in a later anchor must cause zero partial source writes.
        (root/'src/solver_strategy.cpp').write_text('corrupt',encoding='utf-8')
        baseline={name:(root/name).read_bytes() for name in collector.fragments}
        try:impl.patch(impl.Patch(root),package)
        except RuntimeError:pass
        else:raise AssertionError('unexpected source not refused')
        for name, content in baseline.items():assert (root/name).read_bytes()==content
    print('PASS synthetic patch unique anchors, dry-run, atomic preflight and fail-closed')

if __name__=='__main__':run()
