#!/usr/bin/env python3
"""
Test for char_margin_left feature.

This test is adapted from the rejected PR #1173 for pdfminer.six.
It tests that char_margin_left prevents incorrect line merging when
processing left-to-right text.

To run this test:
    python3 -m pytest tests/test_char_margin_left.py -v
    or
    python3 tests/test_char_margin_left.py
"""

import sys
from pathlib import Path

# Add project root and pdfminer.six to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import unittest
import logging
import sys
from unittest.mock import Mock

# Import pytiblegenc first to trigger monkey patching
from pytiblegenc.pdfminer_text_converter import CustomLAParams
# Now import pdfminer after patching is applied
from pdfminer.layout import LTChar, LTLayoutContainer

# Set up logging to see debug messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Print pdfminer.six version info (after imports)
print(f"\n{'='*60}")
print("DEBUG: Checking pdfminer.six and monkey patching status...")


class TestCharMarginLeft(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Print debug info once before all tests."""
        # Print pdfminer.six version info
        try:
            import pdfminer
            pdfminer_version = getattr(pdfminer, '__version__', 'unknown')
            print(f"pdfminer.six version: {pdfminer_version}")
            print(f"pdfminer location: {pdfminer.__file__}")
        except (ImportError, AttributeError) as e:
            print(f"Could not determine pdfminer.six version: {e}")
        
        # Check if monkey patching is active
        try:
            has_patch_flag = hasattr(LTLayoutContainer.group_objects, '_char_margin_left_patched')
            print(f"Monkey patch flag present: {has_patch_flag}")
            
            # Check the ENABLE flag from the module
            try:
                from pytiblegenc.pdfminer_text_converter import _ENABLE_MONKEY_PATCH
                print(f"Monkey patch ENABLE flag: {_ENABLE_MONKEY_PATCH}")
                if not _ENABLE_MONKEY_PATCH:
                    print("  ⚠ WARNING: Monkey patching is DISABLED in code!")
            except (ImportError, AttributeError):
                print("  Could not check ENABLE flag")
            
            if has_patch_flag:
                print("✓ Monkey patching is ACTIVE")
            else:
                print("⚠ Monkey patching is NOT ACTIVE")
                print("  → This means char_margin_left will NOT work!")
        except Exception as e:
            print(f"Could not check monkey patch status: {e}")
        
        # Check if base LAParams supports char_margin_left
        try:
            from pdfminer.layout import LAParams
            test_laparams = LAParams(char_margin=2.0)
            base_has_char_margin_left = hasattr(test_laparams, 'char_margin_left')
            print(f"Base LAParams has char_margin_left: {base_has_char_margin_left}")
            if base_has_char_margin_left:
                print("  → Base pdfminer.six already supports char_margin_left!")
        except Exception as e:
            print(f"Could not check base LAParams: {e}")
            base_has_char_margin_left = False
        
        # Check source code of group_objects
        try:
            import inspect
            source = inspect.getsource(LTLayoutContainer.group_objects)
            if 'char_margin_left' in source:
                print("✓ group_objects source contains 'char_margin_left'")
            else:
                print("⚠ group_objects source does NOT contain 'char_margin_left'")
        except Exception as e:
            print(f"Could not inspect group_objects source: {e}")
        
        print(f"{'='*60}\n")
    
    def test_char_margin_left_prevents_line_wrapping(self):
        """Test that char_margin_left prevents incorrect line merging.
        
        When processing characters sequentially, a character at the far right
        of one line (X=90) followed by a character at the far left of the next
        line (X=10) should not be grouped together when char_margin_left is small,
        even if char_margin is large.
        """
        # Create CustomLAParams with different margins for left vs right
        laparams = CustomLAParams(
            char_margin=1000,      # Very generous for normal text
            char_margin_left=2,    # Strict for leftward jumps
            line_overlap=0.5,
        )
        
        layout = LTLayoutContainer((0, 0, 200, 50))
        
        # Create a mock font
        mock_font = Mock()
        mock_font.fontname = "TestFont"
        mock_font.is_vertical.return_value = False
        mock_font.get_descent.return_value = -0.2
        mock_font.get_height.return_value = 1.0
        
        # Create characters simulating a line wrap scenario
        # IMPORTANT: All characters must be at the SAME Y level to test char_margin_left!
        # If characters are at different Y levels, they will naturally be in different
        # lines regardless of char_margin_left (because halign checks vertical overlap).
        #
        # Scenario: Characters at X=10, 20, ..., 90 (moving right), then a character
        # at X=10 again (simulating line wrap). With char_margin_left=2, the jump from
        # X=90 to X=10 should create a new line.
        
        chars = []
        
        # All characters at the SAME Y level (Y=30) to properly test char_margin_left
        # First part: characters moving right (X=10, 20, ..., 90)
        for i in range(9):
            char = LTChar(
                matrix=(1, 0, 0, 1, 10 + i*10, 30),
                font=mock_font,
                fontsize=10,
                scaling=1,
                rise=0,
                text=chr(65 + i),  # A, B, C, ...
                textwidth=8,
                textdisp=0,
                ncs=None,
                graphicstate=None,
            )
            chars.append(char)
        
        # Second part: characters that would be on the "next line" but at same Y
        # This simulates a line wrap where text continues at X=10 after ending at X=90
        # With char_margin_left=2, this large leftward jump should create a new line
        for i in range(3):
            char = LTChar(
                matrix=(1, 0, 0, 1, 10 + i*10, 30),  # SAME Y=30!
                font=mock_font,
                fontsize=10,
                scaling=1,
                rise=0,
                text=chr(97 + i),  # a, b, c
                textwidth=8,
                textdisp=0,
                ncs=None,
                graphicstate=None,
            )
            chars.append(char)
        
        # Debug: Print input characters
        print(f"\n{'='*60}")
        print("Test: char_margin_left_prevents_line_wrapping")
        print(f"  char_margin={laparams.char_margin}, char_margin_left={laparams.char_margin_left}")
        print(f"  Total input characters: {len(chars)}")
        print("  Input character positions and bounding boxes:")
        for i, char in enumerate(chars):
            has_x1 = hasattr(char, 'x1')
            has_y1 = hasattr(char, 'y1')
            x1_val = char.x1 if has_x1 else 'N/A'
            y1_val = char.y1 if has_y1 else 'N/A'
            width_val = char.width if hasattr(char, 'width') else 'N/A'
            height_val = char.height if hasattr(char, 'height') else 'N/A'
            print(f"    Char {i}: x0={char.x0:.1f}, y0={char.y0:.1f}, "
                  f"x1={x1_val}, y1={y1_val}, width={width_val}, height={height_val}, "
                  f"text='{char.get_text()}'")
        
        # Check if monkey patching is active
        has_patch = hasattr(LTLayoutContainer.group_objects, '_char_margin_left_patched')
        print(f"\n  Monkey patch active: {has_patch}")
        
        # Group the characters into lines with detailed debugging
        print("\n  Grouping characters into lines...")
        print("  Step-by-step analysis of grouping decisions:")
        
        # Manually trace through what group_objects does
        obj0 = None
        for i, obj1 in enumerate(chars):
            if obj0 is not None:
                # Calculate what group_objects would do
                if hasattr(laparams, 'char_margin_left') and obj1.x0 < obj0.x0:
                    char_margin = laparams.char_margin_left
                    margin_type = "char_margin_left"
                else:
                    char_margin = laparams.char_margin
                    margin_type = "char_margin"
                
                # Get bounding box info
                obj0_x1 = obj0.x1 if hasattr(obj0, 'x1') else obj0.x0 + (obj0.width if hasattr(obj0, 'width') else 8)
                obj1_x0 = obj1.x0
                obj0_y0 = obj0.y0
                obj0_y1 = obj0.y1 if hasattr(obj0, 'y1') else obj0.y0 + (obj0.height if hasattr(obj0, 'height') else 10)
                obj1_y0 = obj1.y0
                obj1_y1 = obj1.y1 if hasattr(obj1, 'y1') else obj1.y0 + (obj1.height if hasattr(obj1, 'height') else 10)
                
                is_leftward = obj1.x0 < obj0.x0
                
                voverlap_val = obj0.voverlap(obj1) if obj0.is_voverlap(obj1) else 0
                hdistance_val = obj0.hdistance(obj1)
                min_height = min(obj0.height, obj1.height) if (hasattr(obj0, 'height') and hasattr(obj1, 'height')) else 10
                max_width = max(obj0.width, obj1.width) if (hasattr(obj0, 'width') and hasattr(obj1, 'width')) else 8
                overlap_threshold = min_height * laparams.line_overlap
                distance_threshold = max_width * char_margin
                
                # Manual calculation for debugging
                if is_leftward and hasattr(laparams, 'char_margin_left'):
                    # For leftward: distance from right edge of obj0 to left edge of obj1
                    manual_hdistance = max(0, obj0_x1 - obj1_x0)
                else:
                    # For rightward: distance from right edge of obj0 to left edge of obj1
                    manual_hdistance = max(0, obj1_x0 - obj0_x1)
                manual_voverlap = max(0, min(obj0_y1, obj1_y1) - max(obj0_y0, obj1_y0))
                
                # Calculate what the patched code would do
                if is_leftward and hasattr(laparams, 'char_margin_left'):
                    actual_hdistance = max(0, obj0_x1 - obj1_x0)
                    hdistance_check = actual_hdistance < distance_threshold
                else:
                    hdistance_check = hdistance_val < distance_threshold
                
                halign = (
                    obj0.is_voverlap(obj1)
                    and overlap_threshold < voverlap_val
                    and hdistance_check
                )
                
                print(f"    Transition {i-1}→{i}: obj0.x0={obj0.x0:.1f} (x1≈{obj0_x1:.1f}), obj1.x0={obj1.x0:.1f}")
                print(f"      Direction: {'LEFTWARD' if obj1.x0 < obj0.x0 else 'RIGHTWARD'}")
                print(f"      Using margin: {margin_type}={char_margin}")
                print(f"      obj0 bbox: x0={obj0.x0:.1f}, x1≈{obj0_x1:.1f}, y0={obj0_y0:.1f}, y1≈{obj0_y1:.1f}")
                print(f"      obj1 bbox: x0={obj1_x0:.1f}, y0={obj1_y0:.1f}, y1≈{obj1_y1:.1f}")
                if is_leftward and hasattr(laparams, 'char_margin_left'):
                    print(f"      Manual hdistance (obj0.x1 - obj1.x0, leftward): {manual_hdistance:.3f}")
                    print(f"      Actual hdistance for leftward check: {actual_hdistance:.3f}")
                    print(f"      hdistance check (actual < threshold): {hdistance_check} ({actual_hdistance:.3f} < {distance_threshold:.3f})")
                else:
                    print(f"      Manual hdistance (obj1.x0 - obj0.x1, rightward): {manual_hdistance:.3f}")
                    print(f"      Method hdistance: {hdistance_val:.3f}")
                    print(f"      hdistance check (method < threshold): {hdistance_check} ({hdistance_val:.3f} < {distance_threshold:.3f})")
                print(f"      Manual voverlap: {manual_voverlap:.3f}")
                print(f"      Method voverlap: {voverlap_val:.3f}")
                print(f"      min_height: {min_height:.3f}, max_width: {max_width:.3f}")
                print(f"      voverlap threshold: {overlap_threshold:.3f} (needed: >{overlap_threshold:.3f})")
                print(f"      hdistance threshold: {distance_threshold:.3f}")
                print(f"      halign result: {halign}")
                if not halign:
                    if not obj0.is_voverlap(obj1):
                        print(f"        → NO: No vertical overlap")
                    elif overlap_threshold >= voverlap_val:
                        print(f"        → NO: Vertical overlap too small ({voverlap_val:.3f} <= {overlap_threshold:.3f})")
                    elif not hdistance_check:
                        if is_leftward and hasattr(laparams, 'char_margin_left'):
                            print(f"        → NO: Horizontal distance too large for leftward ({actual_hdistance:.3f} >= {distance_threshold:.3f})")
                        else:
                            print(f"        → NO: Horizontal distance too large ({hdistance_val:.3f} >= {distance_threshold:.3f})")
                        print(f"        → This should create a NEW line!")
                else:
                    print(f"        → YES: Characters will be merged into same line")
            obj0 = obj1
        
        # Now actually group them
        lines = list(layout.group_objects(laparams, chars))
        
        # Debug: Print what we got
        print(f"\n  Result: Number of lines created: {len(lines)}")
        for i, line in enumerate(lines):
            chars_in_line = list(line)
            if chars_in_line:
                first_char = chars_in_line[0]
                last_char = chars_in_line[-1]
                y_positions = set(c.y0 for c in chars_in_line)
                x_positions = [c.x0 for c in chars_in_line]
                print(f"    Line {i}: {len(chars_in_line)} chars")
                print(f"      Y positions: {sorted(y_positions)}")
                print(f"      X range: {min(x_positions):.1f} to {max(x_positions):.1f}")
                print(f"      Text: '{line.get_text()[:50]}'")
                print(f"      First char: x0={first_char.x0:.1f}, y0={first_char.y0:.1f}, text='{first_char.get_text()}'")
                print(f"      Last char: x0={last_char.x0:.1f}, y0={last_char.y0:.1f}, text='{last_char.get_text()}'")
                if len(chars_in_line) <= 10:
                    print(f"      All characters:")
                    for j, c in enumerate(chars_in_line):
                        print(f"        [{j}] x0={c.x0:.1f}, y0={c.y0:.1f}, text='{c.get_text()}'")
                else:
                    print(f"      First 5 characters:")
                    for j, c in enumerate(chars_in_line[:5]):
                        print(f"        [{j}] x0={c.x0:.1f}, y0={c.y0:.1f}, text='{c.get_text()}'")
                    print(f"        ... and {len(chars_in_line) - 5} more")
        
        # Check if characters from different groups ended up in same line
        print(f"\n  Checking if groups are separated:")
        if len(lines) == 1:
            print(f"    ✗ All characters are in ONE line")
            chars_in_line = list(lines[0])
            # Find where the transition happens
            for i in range(len(chars_in_line) - 1):
                if chars_in_line[i].x0 > chars_in_line[i+1].x0:
                    print(f"    Found leftward jump at position {i}→{i+1}: "
                          f"x0={chars_in_line[i].x0:.1f} → {chars_in_line[i+1].x0:.1f}")
                    print(f"    This should have created a new line but didn't!")
        else:
            print(f"    ✓ Characters are in {len(lines)} different lines")
            # Check which characters are in which line
            for i, line in enumerate(lines):
                chars_in_line = list(line)
                char_indices = [chars.index(c) for c in chars_in_line]
                print(f"      Line {i} contains input chars at indices: {char_indices}")
                if i == 0:
                    expected_last = 8  # Last char of first group
                    if max(char_indices) > expected_last:
                        print(f"        ⚠ Line 0 contains chars beyond first group (index {expected_last})")
                if i == 1:
                    expected_first = 9  # First char of second group
                    if min(char_indices) < expected_first:
                        print(f"        ⚠ Line 1 contains chars from first group")
        
        # Analyze the result
        print(f"\n  Analysis:")
        if len(lines) >= 2:
            print(f"    ✓ Got {len(lines)} lines (expected >= 2)")
            # Check if lines are actually separated by Y position
            line_y_positions = []
            for line in lines:
                chars_in_line = list(line)
                if chars_in_line:
                    avg_y = sum(c.y0 for c in chars_in_line) / len(chars_in_line)
                    line_y_positions.append(avg_y)
            if len(set(round(y, 1) for y in line_y_positions)) >= 2:
                print(f"    ✓ Lines are at different Y positions: {[round(y, 1) for y in line_y_positions]}")
            else:
                print(f"    ⚠ Lines are at similar Y positions: {[round(y, 1) for y in line_y_positions]}")
                print(f"    ⚠ This suggests they might be on the same visual line!")
        else:
            print(f"    ✗ Got only {len(lines)} line(s) (expected >= 2)")
            print(f"    ⚠ This means characters from different Y levels were merged!")
        
        # Check if the test scenario is correct
        # For char_margin_left to be tested, all chars should be at the SAME Y level
        input_y_positions = set(c.y0 for c in chars)
        print(f"\n  Test scenario check:")
        print(f"    Input characters at Y positions: {sorted(input_y_positions)}")
        if len(input_y_positions) == 1:
            print(f"    ✓ All characters are at the SAME Y level - test is correct!")
            print(f"    ✓ This will properly test if char_margin_left prevents merging")
            # Check the critical transition: from last char of first group to first char of second group
            if len(chars) >= 10:
                last_first_group = chars[8]  # Last char of first group (X=90)
                first_second_group = chars[9]  # First char of second group (X=10)
                x_jump = first_second_group.x0 - last_first_group.x0
                print(f"    Critical transition: X jump from {last_first_group.x0:.1f} to {first_second_group.x0:.1f} = {x_jump:.1f}")
                if x_jump < 0:
                    print(f"    ✓ Leftward jump detected - char_margin_left should apply")
                else:
                    print(f"    ⚠ No leftward jump - char_margin_left won't be tested")
        else:
            print(f"    ⚠ WARNING: Characters are at DIFFERENT Y levels!")
            print(f"    ⚠ This means they should naturally be in different lines regardless of char_margin_left")
            print(f"    ⚠ The test might be passing for the wrong reason (Y separation, not char_margin_left)")
            print(f"    ⚠ To properly test char_margin_left, all chars should be at the SAME Y level")
        
        # With char_margin_left=2, the large leftward jump from X=90 to X=10
        # should create separate lines IF all chars are at the same Y level
        # Expected: 2 lines if char_margin_left works, 1 line if it doesn't
        print(f"\n  Expected behavior:")
        if len(input_y_positions) == 1:
            print(f"    All chars at same Y level - char_margin_left should prevent merging")
            print(f"    Expected: 2 lines (separated by char_margin_left)")
            print(f"    If monkey patching is NOT active, should get 1 line (all merged)")
            expected_lines_with_patch = 2
            expected_lines_without_patch = 1
        else:
            print(f"    Chars at different Y levels - will naturally be in different lines")
            print(f"    Expected: 2 lines (separated by Y position, not char_margin_left)")
            expected_lines_with_patch = 2
            expected_lines_without_patch = 2  # Will pass regardless
        
        if not has_patch:
            print(f"\n  ⚠ WARNING: Monkey patching is NOT active!")
            if len(input_y_positions) == 1:
                print(f"  ⚠ Test should FAIL (expect 1 line, but checking for >= 2)")
                print(f"  ⚠ If test passes, pdfminer.six may already have char_margin_left support")
            else:
                print(f"  ⚠ But test will pass anyway because chars are at different Y levels")
        
        print(f"{'='*60}\n")
        
        # The assertion: we expect >= 2 lines if char_margin_left is working
        # But if all chars are at same Y and patching is off, we might get 1 line
        if len(input_y_positions) == 1 and not has_patch:
            # This is the real test: with same Y and no patch, should get 1 line (all merged)
            # But we're checking for >= 2, so this should fail
            print(f"  ⚠ TEST LOGIC ISSUE: With same Y and no patch, expect 1 line but checking for >= 2")
            print(f"  ⚠ This test will fail if char_margin_left is NOT working (which is what we want)")
        
        # The actual test: with char_margin_left=2 and a leftward jump of 80 units,
        # the distance threshold should be max(8, 8) * 2 = 16, which is much less than 80
        # So halign should be False and we should get 2 lines
        
        # Calculate expected result
        if len(input_y_positions) == 1 and len(chars) >= 10:
            last_first = chars[8]
            first_second = chars[9]
            hdistance = abs(first_second.x0 - last_first.x1) if hasattr(last_first, 'x1') else abs(first_second.x0 - last_first.x0)
            max_width = max(last_first.width, first_second.width)
            threshold_with_left = max_width * laparams.char_margin_left
            threshold_without_left = max_width * laparams.char_margin
            
            print(f"\n  Final check:")
            print(f"    Distance from last char of group 1 to first char of group 2: {hdistance:.1f}")
            print(f"    Max character width: {max_width:.1f}")
            print(f"    Threshold with char_margin_left={laparams.char_margin_left}: {threshold_with_left:.1f}")
            print(f"    Threshold with char_margin={laparams.char_margin}: {threshold_without_left:.1f}")
            print(f"    Since {hdistance:.1f} > {threshold_with_left:.1f}, should NOT merge (2 lines)")
            if has_patch:
                print(f"    With patching: Expected 2 lines, got {len(lines)}")
            else:
                print(f"    Without patching: Expected 1 line (merged), got {len(lines)}")
        
        print(f"{'='*60}\n")
        
        # Assertion: we expect 2 lines when char_margin_left is working
        self.assertGreaterEqual(len(lines), 2, 
            f"char_margin_left should prevent line wrapping. Got {len(lines)} lines. "
            f"Monkey patch active: {has_patch}. Input Y positions: {sorted(input_y_positions)}. "
            f"With char_margin_left={laparams.char_margin_left}, leftward jump should create new line.")
    
    def test_char_margin_left_defaults_to_char_margin(self):
        """Test that char_margin_left defaults to char_margin for backward compatibility."""
        laparams = CustomLAParams(char_margin=100)
        self.assertEqual(laparams.char_margin_left, 100)
        
    def test_char_margin_left_can_be_set_explicitly(self):
        """Test that char_margin_left can be set to a different value."""
        laparams = CustomLAParams(char_margin=1000, char_margin_left=2)
        self.assertEqual(laparams.char_margin, 1000)
        self.assertEqual(laparams.char_margin_left, 2)


if __name__ == '__main__':
    unittest.main()

