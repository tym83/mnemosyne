"""Blender entry point: run_sheet.py -- script.py source.png [width height samples].

Kit renders are guarded; scripts must leave raw bpy render calls to the runner. Custom staffage
must be tagged with obj['staffage'] = True (or named figure/silhouette/staffage).
"""
import sys
import ast
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy_kit  # noqa: E402
import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402


def guard_scene(scene):
    """Reject scene lettering and constrain evaluated staffage in camera space."""
    texts = [o.name for o in scene.objects if o.type == "FONT"]
    if texts:
        raise ValueError("Текст внутри сцены запрещён; подписи только в картуше: " + ", ".join(texts))
    if scene.camera is None:
        raise ValueError("Нужна камера")
    for obj in scene.objects:
        is_figure = obj.get("staffage") or any(word in obj.name.lower() for word in
                                             ("figure", "staffage", "silhouette"))
        if not is_figure or obj.type != "MESH" or obj.hide_render:
            continue
        for _ in range(12):
            bpy.context.view_layer.update()
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            points = [world_to_camera_view(scene, scene.camera, evaluated.matrix_world @ Vector(c))
                      for c in evaluated.bound_box]
            if max(p.z for p in points) <= 0:
                break
            span = max(p.y for p in points) - min(p.y for p in points)
            if span <= 1 / 15 + 1e-6:
                break
            obj.scale *= min(0.95, (1 / 15) / span * 0.98)
            print(f"STAFFAGE: scaled {obj.name}, projected height was {span:.5f}")
        else:
            raise ValueError(f"Не удалось уменьшить стаффаж: {obj.name}")


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    script, out = args[:2]
    size = [int(x) for x in args[2:5]] if len(args) >= 5 else [2700, 1800, 96]
    called = False
    original = bpy_kit.render

    def render(path=None, width=None, height=None, samples=None, **kw):
        nonlocal called
        called = True
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y = size[:2]
        scene.render.resolution_percentage = 100
        guard_scene(scene)
        original(out, *size, **kw)

    # reset() loads factory settings; register the guard after script construction
    # for the usual path, and also wrap the kit entry point for explicit renders.
    bpy_kit.render = render
    scope = {k: getattr(bpy_kit, k) for k in dir(bpy_kit) if not k.startswith("_")}
    scope.update(render=render, OUT=out)
    source = Path(script).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "render":
            if ast.unparse(node.func) != "bpy_kit.render":
                raise ValueError("Не вызывай bpy render напрямую; лист рисует станок после проверки сцены.")
    exec(compile(tree, script, "exec"), scope)
    guard_scene(bpy.context.scene)
    if not called:
        render()


if __name__ == "__main__":
    main()
