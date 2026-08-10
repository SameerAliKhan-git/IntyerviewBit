"""InterviewAce application package.

This file is deliberately present: without it ``app`` is an implicit namespace package,
which allows the same submodule to be imported under two identities with two separate
copies of module-level state. Session analytics live in module-level dicts, so a split
import would silently divide them.
"""
