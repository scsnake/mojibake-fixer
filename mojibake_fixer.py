#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mojibake Fixer - Fix Big5 encoding errors (mojibake) in text and DICOM files.

This script can be used in two modes:
1. Text Mode: Directly fix mojibake in text strings
2. DICOM Mode: Fix mojibake in DICOM file tags (requires pydicom)

Usage:
    # Fix plain text (no dependencies)
    python mojibake_fixer.py --text "Rt ANKLE CT (µL³y¼v¾¯)"
    
    # Fix DICOM files (requires pydicom)
    python mojibake_fixer.py /path/to/dicom/folder
    python mojibake_fixer.py /path/to/file.dcm --dry-run
    python mojibake_fixer.py /path/to/input -o /path/to/output
"""

import os
import sys
import argparse

# --- CONFIGURATION ---
# DICOM tags commonly affected by Big5 mojibake
TARGET_TAGS = [
    "PatientName", 
    "StudyDescription", 
    "InstitutionName",
    "PerformingPhysicianName", 
    "ReferringPhysicianName", 
    "SeriesDescription",
    "ProtocolName",
    "OperatorsName"
]


# =============================================================================
# CORE TEXT FIXING FUNCTIONS (No dependencies)
# =============================================================================

def fix_text_encoding(text):
    """
    Attempts to fix Mojibake: 
    Reverses Latin-1 interpretation to bytes, then decodes as Big5.
    
    Enhanced to handle:
    1. Pure Latin-1 mojibake (simple case)
    2. Mixed encoding with replacement characters (U+FFFD)
    3. CP1252 (Windows) to Big5 conversion
    4. Partial/segmented fixes when full decode fails
    
    Args:
        text: Input string that may contain mojibake
        
    Returns:
        Fixed string if mojibake was detected and fixed, None otherwise.
        
    Example:
        >>> fix_text_encoding("µL³y¼v¾¯")
        '無造影劑'
        >>> fix_text_encoding("Rt ANKLE CT (µL³y¼v¾¯)")
        'Rt ANKLE CT (無造影劑)'
    """
    if not text:
        return None
    
    # Optimization: Skip pure ASCII
    if all(ord(c) < 128 for c in text):
        return None
    
    # Check if text has high bytes that look like mojibake
    has_high_bytes = any(128 <= ord(c) < 256 for c in text)
    has_replacement = '\ufffd' in text
    
    if not has_high_bytes and not has_replacement:
        return None
    
    # Strategy 1: Try simple Latin-1 -> Big5 decode
    try:
        raw_bytes = text.encode('latin-1')
        fixed = raw_bytes.decode('big5')
        if fixed != text and _looks_like_valid_cjk(fixed):
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    # Strategy 2: Try CP1252 (Windows) -> Big5 decode
    # CP1252 is a superset of Latin-1 with extra chars in 0x80-0x9F range
    try:
        raw_bytes = text.encode('cp1252', errors='replace')
        fixed = raw_bytes.decode('big5', errors='replace')
        if fixed != text and _looks_like_valid_cjk(fixed) and fixed.count('\ufffd') < text.count('\ufffd'):
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    # Strategy 3: Segment-by-segment approach for mixed content
    # Separate ASCII segments from high-byte segments
    fixed = _fix_text_segmented(text)
    if fixed and fixed != text and _looks_like_valid_cjk(fixed):
        return fixed
    
    return None


def _looks_like_valid_cjk(text):
    """Check if text contains likely valid CJK characters (not just garbage)."""
    if not text:
        return False
    
    cjk_count = 0
    garbage_count = 0
    
    for c in text:
        cp = ord(c)
        # CJK Unified Ideographs and common ranges
        if 0x4E00 <= cp <= 0x9FFF:  # CJK Unified Ideographs
            cjk_count += 1
        elif 0x3400 <= cp <= 0x4DBF:  # CJK Extension A
            cjk_count += 1
        elif 0x3000 <= cp <= 0x303F:  # CJK Symbols and Punctuation
            cjk_count += 1
        elif 0xFF00 <= cp <= 0xFFEF:  # Halfwidth and Fullwidth Forms
            cjk_count += 1
        elif cp == 0xFFFD:  # Replacement character
            garbage_count += 1
        elif 128 <= cp < 256:  # Still has Latin-1 high bytes (unfixed)
            garbage_count += 1
    
    # Consider valid if we have CJK chars and not too much garbage
    return cjk_count > 0 and garbage_count <= len(text) * 0.3


def _fix_text_segmented(text):
    """
    Fix text by processing segments separately.
    
    Splits text at ASCII/high-byte boundaries and tries to decode
    high-byte segments as Big5 while preserving ASCII.
    """
    if not text:
        return None
    
    result = []
    segment = []
    is_high_byte_segment = False
    
    for i, c in enumerate(text):
        char_is_high = ord(c) >= 128
        
        # Detect segment boundary
        if segment and char_is_high != is_high_byte_segment:
            # Process completed segment
            seg_text = ''.join(segment)
            if is_high_byte_segment:
                decoded = _try_decode_segment(seg_text)
                result.append(decoded if decoded else seg_text)
            else:
                result.append(seg_text)
            segment = []
        
        segment.append(c)
        is_high_byte_segment = char_is_high
    
    # Process final segment
    if segment:
        seg_text = ''.join(segment)
        if is_high_byte_segment:
            decoded = _try_decode_segment(seg_text)
            result.append(decoded if decoded else seg_text)
        else:
            result.append(seg_text)
    
    return ''.join(result)


def _try_decode_segment(segment):
    """Try to decode a high-byte segment as Big5."""
    if not segment:
        return None
    
    # Remove replacement characters before trying to decode
    clean_segment = segment.replace('\ufffd', '')
    if not clean_segment:
        return None
    
    # Try Latin-1 -> Big5
    try:
        raw_bytes = clean_segment.encode('latin-1')
        decoded = raw_bytes.decode('big5', errors='replace')
        # Check if we got valid CJK
        if _looks_like_valid_cjk(decoded):
            return decoded
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    # Try CP1252 -> Big5
    try:
        raw_bytes = clean_segment.encode('cp1252', errors='replace')
        decoded = raw_bytes.decode('big5', errors='replace')
        if _looks_like_valid_cjk(decoded):
            return decoded
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    return None


# =============================================================================
# DICOM PROCESSING FUNCTIONS (Dynamic pydicom import)
# =============================================================================

def process_dicom(file_path, output_path=None, dry_run=False, force_check=True):
    """
    Reads a DICOM file, checks for encoding errors, and saves it.
    
    Args:
        file_path (str): Source file path.
        output_path (str, optional): Destination path. If None, overwrites in-place.
        dry_run (bool): If True, prints changes but does not write files.
        force_check (bool): If True, always check for mojibake even if charset 
                           indicates UTF-8. Set False to trust existing charset.
        
    Returns:
        bool: True if file was modified/saved, False otherwise.
    """
    # Dynamic import of pydicom (only when needed)
    try:
        import pydicom
    except ImportError:
        print("Error: pydicom is required for DICOM processing.")
        print("Install with: pip install pydicom")
        return False
    
    try:
        ds = pydicom.dcmread(file_path)
    except Exception as e:
        # Not a valid DICOM or read error
        return False

    # Get current charset
    charset = getattr(ds, "SpecificCharacterSet", "")
    if isinstance(charset, list):
        charset = charset[0] if charset else ""
    
    # Skip only if NOT force_check AND already UTF-8
    # When force_check=True (default), we always examine the fields
    if not force_check and "ISO_IR 192" in str(charset):
        return False

    updated = False
    
    # Check tags for mojibake
    for tag in TARGET_TAGS:
        if hasattr(ds, tag):
            val = getattr(ds, tag)
            # Convert PersonName objects to string for processing
            val_str = str(val)
            
            fixed_val = fix_text_encoding(val_str)
            
            if fixed_val:
                if dry_run:
                    print(f"  [Dry Run] {tag}: {val_str} -> {fixed_val}")
                else:
                    setattr(ds, tag, fixed_val)
                updated = True

    # Save logic
    if updated or (output_path and output_path != file_path):
        if dry_run:
            print(f"  [Dry Run] Would save to: {output_path or file_path}")
            return True

        # Ensure we set the charset so the new chars are read correctly
        ds.SpecificCharacterSet = 'ISO_IR 192'

        # Determine save location
        dest = output_path if output_path else file_path
        
        # Ensure dest dir exists
        dest_dir = os.path.dirname(os.path.abspath(dest))
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        
        ds.save_as(dest)
        return True

    return False


def scan_and_fix(input_path, output_root=None, dry_run=False, force_check=True):
    """
    Main logic to handle file or directory recursion for DICOM files.
    
    Args:
        input_path: File or directory to process
        output_root: Optional output location (if None, modifies in-place)
        dry_run: If True, show what would be done without modifying
        force_check: If True, always check for mojibake even if charset is UTF-8
    """
    input_path = os.path.abspath(input_path)
    
    # CASE 1: Single File
    if os.path.isfile(input_path):
        if output_root:
            # If output is a dir, put file inside. If it looks like a file, use it.
            if os.path.isdir(output_root) or output_root.endswith(os.sep):
                fname = os.path.basename(input_path)
                dest = os.path.join(output_root, fname)
            else:
                dest = output_root
        else:
            dest = None  # In-place
            
        print(f"Processing file: {input_path}")
        modified = process_dicom(input_path, dest, dry_run, force_check)
        if modified:
            print(f"  -> Fixed/Saved")
        else:
            print(f"  -> No changes needed")
        return

    # CASE 2: Directory
    if os.path.isdir(input_path):
        count = 0
        total = 0
        print(f"Scanning directory: {input_path}")
        
        for root, dirs, files in os.walk(input_path):
            for name in files:
                src_file = os.path.join(root, name)
                total += 1
                
                # Determine destination
                dest_file = None
                if output_root:
                    # Calculate relative path to maintain structure
                    rel_path = os.path.relpath(src_file, input_path)
                    dest_file = os.path.join(output_root, rel_path)

                modified = process_dicom(src_file, dest_file, dry_run, force_check)
                if modified:
                    count += 1
                    status = "Dry Run" if dry_run else "Fixed"
                    print(f"[{status}] {name}")
        
        print(f"\nOperation complete. Fixed: {count}/{total} files")
        return

    print(f"Error: Input path not found: {input_path}")


# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fix Big5 Mojibake in text or DICOM files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix plain text (print result to stdout)
  python mojibake_fixer.py --text "Rt ANKLE CT (µL³y¼v¾¯)"
  
  # Fix DICOM files in-place
  python mojibake_fixer.py /path/to/dicom/folder
  
  # Dry run (show what would be fixed)
  python mojibake_fixer.py /path/to/file.dcm --dry-run
  
  # Fix to different output location
  python mojibake_fixer.py /path/to/input -o /path/to/output
  
  # Trust existing charset (skip files marked as UTF-8)
  python mojibake_fixer.py /path/to/folder --trust-charset
"""
    )
    
    # Mutually exclusive: text mode OR file/dir mode
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("input", nargs="?", help="Input DICOM file or directory")
    group.add_argument("-t", "--text", help="Fix mojibake in text string (no pydicom needed)")
    
    # DICOM-specific options
    parser.add_argument("-o", "--output", help="Output file or directory. If omitted, updates IN-PLACE.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without modifying files.")
    parser.add_argument("--trust-charset", action="store_true", 
                        help="Trust existing charset in DICOM. Skip files with ISO_IR 192 (UTF-8).")
    
    args = parser.parse_args()
    
    # TEXT MODE: Just fix the text and print
    if args.text:
        result = fix_text_encoding(args.text)
        if result:
            print(f"Input:  {args.text}")
            print(f"Fixed:  {result}")
        else:
            print(f"No mojibake detected in: {args.text}")
        return
    
    # DICOM MODE: Process files
    if args.input:
        force_check = not args.trust_charset
        scan_and_fix(args.input, args.output, args.dry_run, force_check)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
