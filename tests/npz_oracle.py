#!/usr/bin/env python3
"""Independent test-only ZIP/NPY oracle; NumPy is optional, not a runtime dependency."""
import ast
import json
from pathlib import Path
import struct
import sys
import zipfile

path = Path(sys.argv[1] if len(sys.argv) > 1 else "build/npz_test.npz")
expected = {
    "time": ("<f8", (3,), "d", [0, 0.25, 1]),
    "analog": ("<f4", (3, 2), "f", [1, -1, 2, -2, 3, -3]),
    "digital": ("|u1", (3, 1), "B", [0, 1, 0]),
    "empty": ("<f4", (3, 0), "f", []),
    "scalar": ("<f8", (), "d", [0]),
}
with zipfile.ZipFile(path) as archive:
    assert archive.testzip() is None
    assert set(archive.namelist()) == {key + ".npy" for key in expected} | {"metadata_json.npy"}
    for info in archive.infolist():
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.flag_bits & 0x800  # explicitly UTF-8 names
        data = archive.read(info)
        assert data[:8] == b"\x93NUMPY\x01\x00"
        length, = struct.unpack("<H", data[8:10])
        assert (10 + length) % 64 == 0
        assert data[10 + length - 1] == 10
        header = ast.literal_eval(data[10:10 + length].decode("ascii"))
        assert header["fortran_order"] is False
        payload = data[10 + length:]
        key = info.filename[:-4]
        if key == "metadata_json":
            assert header["descr"] == "|u1"
            assert header["shape"] == (len(payload),)
            assert json.loads(payload.decode("utf-8")) == {"status": "COMPLETED", "label": "测量"}
        else:
            dtype, shape, code, values = expected[key]
            assert header["descr"] == dtype
            assert header["shape"] == shape
            assert list(struct.unpack("<" + code * len(values), payload)) == values
print("PASS independent Python zipfile/NPY/CRC/dtype/shape/value/UTF-8 metadata oracle")
try:
    import numpy as np
except ImportError:
    print("NOT_TESTED NumPy loader (NumPy unavailable)")
else:
    with np.load(path, allow_pickle=False) as arrays:
        for key, (dtype, shape, _, values) in expected.items():
            assert arrays[key].shape == shape
            assert arrays[key].dtype == np.dtype(dtype)
            np.testing.assert_array_equal(arrays[key].ravel(), values)
        assert json.loads(arrays["metadata_json"].tobytes()) == {"status": "COMPLETED", "label": "测量"}
    print("PASS NumPy allow_pickle=False loader")
