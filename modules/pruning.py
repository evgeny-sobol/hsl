"""Orphan .txt pruning: remove generated .txt files whose source .hsl/.include
is gone, honouring `!`-negation patterns from .gitignore so hand-kept files stay.
"""
import os
import fnmatch


def _collect_unignore_patterns(target_folder):
    """Gather negation patterns (lines starting with '!') from every .gitignore
    under target_folder. Returns a list of (dir, pattern) so a pattern is matched
    relative to the .gitignore that declares it, mirroring git's scoping."""
    patterns = []
    for root, _dirs, files in os.walk(target_folder):
        if '.gitignore' not in files:
            continue
        try:
            with open(os.path.join(root, '.gitignore'), 'r', encoding='utf-8-sig') as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for line in lines:
            s = line.strip()
            if s.startswith('!') and len(s) > 1:
                patterns.append((root, s[1:].strip().lstrip('/')))
    return patterns


def _is_protected(txt_path, patterns):
    """True if txt_path matches any '!' unignore pattern, matched both against
    its basename and its path relative to the declaring .gitignore's directory."""
    base = os.path.basename(txt_path)
    for pdir, pat in patterns:
        if fnmatch.fnmatch(base, pat):
            return True
        rel = os.path.relpath(txt_path, pdir).replace(os.sep, '/')
        if fnmatch.fnmatch(rel, pat):
            return True
    return False


def prune_orphan_txt(target_folder):
    """Delete .txt files that have no sibling .hsl or .include source, unless the
    .txt is protected by a '!' rule in a .gitignore. Returns the count removed."""
    patterns = _collect_unignore_patterns(target_folder)
    removed = 0
    for root, _dirs, files in os.walk(target_folder):
        stems = {f.rsplit('.', 1)[0] for f in files
                 if f.endswith('.hsl') or f.endswith('.include')}
        for f in files:
            if not f.endswith('.txt'):
                continue
            if f[:-4] in stems:
                continue
            txt_path = os.path.join(root, f)
            if _is_protected(txt_path, patterns):
                continue
            try:
                os.remove(txt_path)
                print(f"Removed orphan: {os.path.relpath(txt_path, target_folder)}")
                removed += 1
            except OSError as e:
                print(f"  Could not remove {txt_path}: {e}")
    return removed
