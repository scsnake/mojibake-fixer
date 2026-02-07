# Mojibake Fixer for Big5

A Python utility to correct text encoding errors ("mojibake") that occur when Big5-encoded strings (Traditional Chinese) are incorrectly decoded as Latin-1 or CP1252.

## Problem Solved

Common legacy systems (like some DICOM modalities or HL7 engines) may transmit Big5 characters as raw bytes without specifying the correct charset. Modern systems often interpret these bytes as single-byte Western encodings:

- **IS0-8859-1 (Latin-1)**: The most common fallback. Big5 bytes become garbled text like `µL³y¼v¾¯`.
- **Windows-1252 (CP1252)**: Similar to Latin-1 but handles bytes 0x80-0x9F (control characters) differently.

This script reverses the incorrect decoding and re-interprets the underlying bytes as Big5.

## Supported Charset Combinations

This tool specifically targets **Big5 (Traditional Chinese)** mojibake arising from these misinterpretations:

1.  **Latin-1 -> Big5**
    - Source bytes were Big5.
    - Incorrectly decoded as ISO-8859-1.
    - Solution: `text.encode('latin-1').decode('big5')`

2.  **CP1252 -> Big5**
    - Source bytes were Big5.
    - Incorrectly decoded as Windows-1252 (often happens on Windows systems).
    - Solution: `text.encode('cp1252').decode('big5')`
    - Handles replacement characters (``) by attempting to salvage readable segments.

3.  **Mixed Encoding (Partial Mojibake)**
    - Strings containing valid ASCII mixed with mojibake.
    - Example: `Rt ANKLE CT (µL³y¼v¾¯)` -> `Rt ANKLE CT (無造影劑)`
    - *Features*: Segment-by-segment processing to fix only the garbled parts without damaging ASCII text.

> [!NOTE]
> This tool does **not** handle other mojibake types (e.g., UTF-8 interpreted as Latin-1, Shim-JIS, GBK, etc.). It is optimized strictly for Big5 recovery.

## Usage

### As a Command Line Tool

**1. Fix simple text string:**
No dependencies required.
```bash
python mojibake_fixer.py --text "Rt ANKLE CT (µL³y¼v¾¯)"
# Output: Rt ANKLE CT (無造影劑)
```

**2. Fix DICOM files:**
Requires `pydicom`. Fixes specific tags (PatientName, StudyDescription, etc.) in-place.
```bash
# Install dependency first
pip install pydicom

# Process a single file (dry run to see changes first)
python mojibake_fixer.py path/to/study.dcm --dry-run

# Process entire directory recursively
python mojibake_fixer.py path/to/dicom_folder/

# Force re-check (ignore existing UTF-8 charset tag)
python mojibake_fixer.py path/to/dicom_folder/ --trust-charset=False
```

### As a Python Library

import `fix_text_encoding` for string conversion or `process_dicom` for file handling.

```python
from mojibake_fixer import fix_text_encoding

# Simple fix
broken = "µL³y¼v¾¯"
fixed = fix_text_encoding(broken)
print(fixed)  # 無造影劑

# It returns None if no fix is needed or possible
print(fix_text_encoding("Hello World"))  # None
```

## Dependencies

- **Standard Library only** for text fixing mode.
- **`pydicom`** required only for DICOM file processing mode.
