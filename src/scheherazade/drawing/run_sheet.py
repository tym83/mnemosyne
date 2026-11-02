"""Blender entry point: blender -b -P run_sheet.py -- script.py out.png [width height samples]

Runs an artist's sheet script with the kit in scope and renders it; if
the script does not call render() itself, the sheet is drawn at the end.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy_kit  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
script, out = args[0], args[1]
size = [int(x) for x in args[2:5]] if len(args) >= 5 else [1800, 1200, 96]
called = {"render": False}


def render(path=None, width=None, height=None, samples=None, **kw):
    called["render"] = True
    bpy_kit.render(out, width or size[0], height or size[1], samples or size[2], **kw)


scope = {k: getattr(bpy_kit, k) for k in dir(bpy_kit) if not k.startswith("_")}
scope.update(render=render, OUT=out)
exec(compile(Path(script).read_text(), script, "exec"), scope)
if not called["render"]:
    render()
