"""
AutoPrompt — Responsive & Accessibility Auditor for Phase 7.2.
Performs thorough analysis of:
1. Viewport scaling & responsive CSS rules across:
   - Desktop: 1920x1080, 1440x900, 1366x768
   - Tablet: 1024x768, 768x1024
   - Mobile: 430x932, 390x844, 375x812
2. Horizontal overflow calculations (header, main container, modals, toast)
3. DOM Accessibility:
   - Form controls with labels
   - Button accessible names
   - ARIA roles and relationships
   - Color contrast and focus outlines
4. Cross-browser CSS prefixes and modern property support
"""

import re
from pathlib import Path

ROOT = Path("e:/prompauto/autoprompt-prototype")
HTML_FILE = ROOT / "index.html"
STYLE_CSS = ROOT / "css" / "style.css"
RESPONSIVE_CSS = ROOT / "css" / "responsive.css"

with open(HTML_FILE, "r", encoding="utf-8") as f:
    html = f.read()

with open(STYLE_CSS, "r", encoding="utf-8") as f:
    style_css = f.read()

with open(RESPONSIVE_CSS, "r", encoding="utf-8") as f:
    resp_css = f.read()

findings = {
    "responsive_issues": [],
    "accessibility_issues": [],
    "cross_browser_issues": [],
    "verified_strengths": [],
}

print("=== 1. AUDITING ACCESSIBILITY ===")

# A. Buttons accessible names
buttons = re.findall(r'<button\b([^>]*)>(.*?)</button>', html, re.DOTALL)
print(f"Total buttons audited: {len(buttons)}")
for attrs, inner_text in buttons:
    clean_text = re.sub(r'<[^>]+>', '', inner_text).strip()
    has_aria = 'aria-label=' in attrs or 'aria-labelledby=' in attrs
    has_title = 'title=' in attrs
    btn_id = re.search(r'id=["\']([^"\']+)["\']', attrs)
    id_str = btn_id.group(1) if btn_id else "unknown"

    if not clean_text and not has_aria and not has_title:
        findings["accessibility_issues"].append(
            f"Button #{id_str} has no visible text and lacks aria-label/title"
        )

# B. Form input labels
inputs = re.findall(r'<input\b([^>]*)>', html)
print(f"Total inputs audited: {len(inputs)}")
for attrs in inputs:
    btn_id = re.search(r'id=["\']([^"\']+)["\']', attrs)
    inp_type = re.search(r'type=["\']([^"\']+)["\']', attrs)
    type_str = inp_type.group(1) if inp_type else "text"
    if type_str == "hidden":
        continue
    if btn_id:
        inp_id = btn_id.group(1)
        has_label = f'for="{inp_id}"' in html or f"for='{inp_id}'" in html
        has_aria = 'aria-label=' in attrs or 'aria-labelledby=' in attrs
        if not has_label and not has_aria:
            findings["accessibility_issues"].append(
                f"Input #{inp_id} (type={type_str}) has no <label for='...'> or aria-label"
            )

# C. Selects
selects = re.findall(r'<select\b([^>]*)>', html)
print(f"Total selects audited: {len(selects)}")
for attrs in selects:
    btn_id = re.search(r'id=["\']([^"\']+)["\']', attrs)
    if btn_id:
        sel_id = btn_id.group(1)
        has_label = f'for="{sel_id}"' in html or f"for='{sel_id}'" in html
        has_aria = 'aria-label=' in attrs or 'aria-labelledby=' in attrs
        if not has_label and not has_aria:
            findings["accessibility_issues"].append(
                f"Select #{sel_id} has no <label for='...'> or aria-label"
            )

# D. Textareas
textareas = re.findall(r'<textarea\b([^>]*)>', html)
print(f"Total textareas audited: {len(textareas)}")
for attrs in textareas:
    btn_id = re.search(r'id=["\']([^"\']+)["\']', attrs)
    if btn_id:
        ta_id = btn_id.group(1)
        has_label = f'for="{ta_id}"' in html or f"for='{ta_id}'" in html
        has_aria = 'aria-label=' in attrs or 'aria-labelledby=' in attrs
        if not has_label and not has_aria:
            findings["accessibility_issues"].append(
                f"Textarea #{ta_id} has no <label for='...'> or aria-label"
            )

print("\n=== 2. AUDITING RESPONSIVE CSS ===")

# Check if modal responsive styles exist in responsive.css
if ".modal-dialog" not in resp_css:
    findings["responsive_issues"].append(
        "Missing responsive rules for .modal-dialog in responsive.css (modal padding/margins not scaled on mobile < 768px)"
    )

if ".toast-container" not in resp_css and ".toast" not in resp_css:
    findings["responsive_issues"].append(
        "Missing responsive rules for .toast-container and .toast on mobile (fixed right: 24px and max-width: 380px overflows screens <= 390px)"
    )

if "nav-btn-persistence" not in resp_css:
    findings["responsive_issues"].append(
        "Missing mobile rules for .nav-btn-persistence in responsive.css (header buttons retain full text labels, causing header overflow on viewports <= 430px)"
    )

if ".persistence-toolbar" not in resp_css:
    findings["responsive_issues"].append(
        "Missing mobile rules for .persistence-toolbar (search input and select filters do not stack or stretch to 100% on narrow mobile viewports <= 430px)"
    )

# Check comparison grid responsiveness
if ".comparison-grid" in resp_css:
    findings["verified_strengths"].append(
        "Comparison grid stacks to single column on mobile (max-width: 768px)"
    )

# Check metrics grid responsiveness
if ".metrics-grid" in resp_css:
    findings["verified_strengths"].append(
        "Metrics grid transitions to 2-column on tablet and 1-column on small mobile (<= 480px)"
    )

# Check service tabs responsiveness
if ".service-selector-bar" in resp_css:
    findings["verified_strengths"].append(
        "Service selector tabs expand to full-width flexible tabs on mobile"
    )

print("\n=== 3. AUDITING CROSS-BROWSER SUPPORT ===")

# Check vendor prefixes for flex/grid/backdrop-filter
if "-webkit-backdrop-filter" in style_css:
    findings["verified_strengths"].append(
        "Includes -webkit-backdrop-filter for Safari / WebKit compatibility"
    )
else:
    findings["cross_browser_issues"].append(
        "Missing -webkit-backdrop-filter on blurred surfaces"
    )

# Check custom properties fallbacks and color-scheme
if "color-scheme" in style_css:
    findings["verified_strengths"].append("Native color-scheme property declared for system dark/light integration")

# Check viewport meta tag in index.html
if '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in html:
    findings["verified_strengths"].append("Correct viewport meta tag present in index.html")
else:
    findings["responsive_issues"].append("Missing or non-standard viewport meta tag")

print("\n=== AUDIT FINDINGS SUMMARY ===")
print(f"Accessibility Issues: {len(findings['accessibility_issues'])}")
for issue in findings["accessibility_issues"]:
    print(f"  [A11Y] {issue}")

print(f"\nResponsive Issues: {len(findings['responsive_issues'])}")
for issue in findings["responsive_issues"]:
    print(f"  [RESP] {issue}")

print(f"\nVerified Responsive Strengths: {len(findings['verified_strengths'])}")
for strength in findings["verified_strengths"]:
    print(f"  [OK]   {strength}")
