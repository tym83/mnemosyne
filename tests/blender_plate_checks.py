"""Run inside Blender with the drawing directory on sys.path; no rendering."""
import sys
sys.path.insert(0, '/work/sheets/kit')
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from bpy_kit import reset, figure, camera
from run_sheet import guard_scene

for orthographic in (True, False):
    reset()
    obj = figure(0, 0, scale=8)
    camera((15, -25, 12), (0, 0, 2), ortho_scale=30 if orthographic else None)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 2700, 1800
    guard_scene(sc)
    bpy.context.view_layer.update()
    pts = [world_to_camera_view(sc, sc.camera, obj.matrix_world @ Vector(c)) for c in obj.bound_box]
    span = max(p.y for p in pts) - min(p.y for p in pts)
    assert span <= 1/15 + 1e-6, span
    print(f'PASS {"orthographic" if orthographic else "perspective"}: height={span:.6f}')

bpy.ops.object.text_add()
try:
    guard_scene(bpy.context.scene)
except ValueError as error:
    assert 'картуше' in str(error)
    print('PASS scene text refused:', error)
else:
    raise AssertionError('Text was accepted')
