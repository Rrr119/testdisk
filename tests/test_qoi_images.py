#!/usr/bin/env python3
#
# PhotoRec QOI carving tests.
#
# Builds 10 disk images containing QOI ("Quite OK Image") files in
# various layouts, runs PhotoRec on each image and checks that the
# expected files are carved back byte-for-byte.
#
# Usage: tests/test_qoi_images.py [path-to-photorec]

import glob
import os
import shutil
import struct
import subprocess
import sys
import tempfile

SECTOR = 512


def make_qoi(width, height, channels=3, colorspace=0, rgba=(10, 20, 30, 255)):
    """Generate a valid solid-color QOI file."""
    out = bytearray()
    out += b"qoif"
    out += struct.pack(">II", width, height)
    out += bytes([channels, colorspace])
    out += bytes([0xFF, rgba[0], rgba[1], rgba[2], rgba[3]])  # QOI_OP_RGBA
    remaining = width * height - 1
    while remaining > 0:
        run = min(remaining, 62)
        out.append(0xC0 | (run - 1))  # QOI_OP_RUN
        remaining -= run
    out += b"\x00" * 7 + b"\x01"  # qoi end marker
    return bytes(out)


def align_up(value, alignment=SECTOR):
    return (value + alignment - 1) // alignment * alignment


def build_image(path, size, chunks):
    """Create an image of `size` bytes and write (offset, data) chunks."""
    with open(path, "wb") as f:
        f.truncate(size)
        for offset, data in chunks:
            f.seek(offset)
            f.write(data)


def run_photorec(photorec, image, outdir):
    cmd = [
        photorec, "/d", outdir,
        "/cmd", image,
        "fileopt,everything,disable,qoi,enable,search",
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         timeout=300)
    if res.returncode != 0:
        raise RuntimeError("photorec exited with %d:\n%s"
                           % (res.returncode, res.stdout.decode(errors="replace")))


def recovered_files(outdir):
    files = []
    for session_dir in glob.glob(outdir + ".*"):
        for root, _dirs, names in os.walk(session_dir):
            for name in names:
                if name.endswith(".qoi"):
                    files.append(os.path.join(root, name))
    return sorted(files)


def check(name, image, outdir, expected):
    """expected: list of QOI byte strings that must be recovered."""
    run_photorec(PHOTOREC, image, outdir)
    got = []
    for path in recovered_files(outdir):
        with open(path, "rb") as f:
            got.append(f.read())
    remaining = list(got)
    for want in expected:
        if want in remaining:
            remaining.remove(want)
        else:
            raise AssertionError(
                "%s: expected qoi file (%d bytes, head %r) not found among %s"
                % (name, len(want), want[:16],
                   ["%d bytes" % len(g) for g in got]))
    if remaining:
        raise AssertionError("%s: %d unexpected extra file(s): %s"
                             % (name, len(remaining),
                                ["%d bytes" % len(g) for g in remaining]))


def main():
    global PHOTOREC
    here = os.path.dirname(os.path.abspath(__file__))
    PHOTOREC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        here, "..", "src", "photorec")
    if not os.path.isfile(PHOTOREC):
        sys.exit("photorec binary not found: %s (build it first)" % PHOTOREC)

    qoi_small = make_qoi(64, 48)
    qoi_rgb = make_qoi(32, 32, channels=3, colorspace=0, rgba=(200, 0, 0, 255))
    qoi_rgba = make_qoi(32, 32, channels=4, colorspace=1, rgba=(0, 255, 0, 128))
    qoi_large = make_qoi(1920, 1080, channels=4, colorspace=0)
    qoi_tiny = make_qoi(1, 1, rgba=(1, 2, 3, 255))

    junk = bytes((i * 37 + 11) % 256 for i in range(4096))

    tests = []

    # 1. Single file at the very start of the image
    tests.append(("t01_single_at_start", 4 * 1024 * 1024,
                  [(0, qoi_small)], [qoi_small]))

    # 2. Single file at a 1 MiB sector-aligned offset
    tests.append(("t02_offset_1m", 4 * 1024 * 1024,
                  [(1024 * 1024, qoi_small)], [qoi_small]))

    # 3. Three files at different offsets
    chunks = []
    off = SECTOR
    expected = []
    for data in (qoi_small, qoi_rgb, qoi_rgba):
        chunks.append((off, data))
        expected.append(data)
        off += align_up(len(data)) + SECTOR
    tests.append(("t03_multiple_files", 4 * 1024 * 1024, chunks, expected))

    # 4. RGBA / linear-colorspace variant
    tests.append(("t04_rgba_linear", 4 * 1024 * 1024,
                  [(2 * SECTOR, qoi_rgba)], [qoi_rgba]))

    # 5. Large file spanning many blocks
    tests.append(("t05_large_image", 8 * 1024 * 1024,
                  [(SECTOR, qoi_large)], [qoi_large]))

    # 6. Two files back to back (second on the next sector boundary)
    off2 = align_up(len(qoi_rgb))
    tests.append(("t06_adjacent_files", 4 * 1024 * 1024,
                  [(0, qoi_rgb), (off2, qoi_rgba)],
                  [qoi_rgb, qoi_rgba]))

    # 7. File surrounded by random junk
    tests.append(("t07_junk_around", 4 * 1024 * 1024,
                  [(SECTOR, junk), (3 * SECTOR, qoi_small),
                   (3 * SECTOR + align_up(len(qoi_small)), junk)],
                  [qoi_small]))

    # 8. Five tiny 1x1 files
    chunks = [(i * SECTOR, qoi_tiny) for i in range(1, 6)]
    tests.append(("t08_many_tiny", 4 * 1024 * 1024, chunks, [qoi_tiny] * 5))

    # 9. Fake boot sector (0x55AA signature) followed by a qoi file
    boot = bytearray(SECTOR)
    boot[510:512] = b"\x55\xaa"
    tests.append(("t09_after_boot_sector", 4 * 1024 * 1024,
                  [(0, bytes(boot)), (2 * SECTOR, qoi_small)], [qoi_small]))

    # 10. File ending exactly at the end of the image
    img_size = 1024 * 1024 + len(qoi_small)
    tests.append(("t10_ends_at_image_end", img_size,
                  [(1024 * 1024, qoi_small)], [qoi_small]))

    workdir = tempfile.mkdtemp(prefix="photorec_qoi_test_")
    failures = 0
    try:
        for name, size, chunks, expected in tests:
            tdir = os.path.join(workdir, name)
            os.makedirs(tdir)
            image = os.path.join(tdir, "image.dd")
            outdir = os.path.join(tdir, "recup")
            build_image(image, size, chunks)
            try:
                check(name, image, outdir, expected)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print("FAIL %s: %s" % (name, exc))
            else:
                print("PASS %s" % name)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("%d/%d tests passed" % (len(tests) - failures, len(tests)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
