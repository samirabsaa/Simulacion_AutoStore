import omni.usd
import omni.timeline
import hashlib
from dataclasses import dataclass
from pxr import (
    UsdGeom,
    UsdShade,
    UsdLux,
    Sdf,
    Gf
)

# =====================================================
# 1. CONFIGURACIÓN GLOBAL DE LA ESCENA
# =====================================================
GRID_X = 3
GRID_Y = 3
GRID_Z = 5

CELL_SPACING_X = 500
CELL_SPACING_Y = 700
CELL_SPACING_Z = 600

GRID_USD = r"C:\Users\krono\Downloads\vigasarreglo_.usdc"
TOP_USD = r"C:\Users\krono\Downloads\topeviga.usdc"

# =====================================================
# 2. MODELO DE DATOS Y UTILIDADES
# =====================================================
@dataclass
class Bin:
    bin_id: str
    sku: str
    quantity: int
    x: int
    y: int
    z: int

def sku_to_color(sku):
    h = hashlib.md5(sku.encode()).hexdigest()
    return (int(h[0:2], 16)/255, int(h[2:4], 16)/255, int(h[4:6], 16)/255)

def create_material(stage, material_path, color):
    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, material_path + "/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material

# =====================================================
# 3. ESTRUCTURA DE VIGAS (GRID BUILDER)
# =====================================================
class GridBuilder:
    def __init__(self):
        self.stage = omni.usd.get_context().get_stage()

    def build(self):
        UsdGeom.Xform.Define(self.stage, "/World/Grid")
        for x in range(GRID_X):
            for y in range(GRID_Y):
                for z in range(GRID_Z):
                    path = f"/World/Grid/Cell_{x}_{y}_{z}"
                    prim = self.stage.DefinePrim(path, "Xform")
                    prim.GetReferences().AddReference(GRID_USD)
                    xform = UsdGeom.Xformable(prim)
                    xform.AddTranslateOp().Set(Gf.Vec3d(x * CELL_SPACING_X, y * CELL_SPACING_Y, z * CELL_SPACING_Z))

        top_z = (GRID_Z * CELL_SPACING_Z - 300)
        UsdGeom.Xform.Define(self.stage, "/World/NavigationSurface")
        for x in range(GRID_X):
            for y in range(GRID_Y):
                path = f"/World/NavigationSurface/Top_{x}_{y}"
                prim = self.stage.DefinePrim(path, "Xform")
                prim.GetReferences().AddReference(TOP_USD)
                xform = UsdGeom.Xformable(prim)
                xform.AddTranslateOp().Set(Gf.Vec3d(x * CELL_SPACING_X, y * CELL_SPACING_Y, top_z))

# =====================================================
# 4. GESTOR DE CAJAS (MÚSCULO VISUAL SOLAMENTE)
# =====================================================
class BinManager:
    def __init__(self):
        self.stage = omni.usd.get_context().get_stage()
        self.bins = {}

    # 🛑 LÓGICA ELIMINADA: Ya no hay validaciones LIFO.
    # Ahora M2 le DEBE decir explícitamente en qué "Z" dibujar la caja.
    def add_bin(self, bin_id, x, y, z, sku, quantity=1):
        cell_path = f"/World/Grid/Cell_{x}_{y}_{z}"
        bin_path = f"{cell_path}/Bin"

        prim = self.stage.GetPrimAtPath(bin_path)
        if prim.IsValid() and not prim.IsActive(): prim.SetActive(True)

        cube = UsdGeom.Cube.Define(self.stage, bin_path)
        cube.CreateSizeAttr(1.0)
        
        xform = UsdGeom.Xformable(cube.GetPrim())
        xform.ClearXformOpOrder()
        xform.AddTranslateOp()
        xform.AddScaleOp().Set(Gf.Vec3f(CELL_SPACING_X, CELL_SPACING_Y, CELL_SPACING_Z))

        color = sku_to_color(sku)
        mat_path = f"/World/Materials/{sku}"
        material = UsdShade.Material(self.stage.GetPrimAtPath(mat_path)) if self.stage.GetPrimAtPath(mat_path).IsValid() else create_material(self.stage, mat_path, color)
        UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(material)

        # Registramos visualmente la caja
        self.bins[bin_id] = Bin(bin_id, sku, quantity, x, y, z)
        print(f"✅ CAJA DIBUJADA: '{sku}' en ({x}, {y}, Z={z})")
        return bin_id

# =====================================================
# 5. GESTOR DE ENTORNO E ILUMINACIÓN (TURNOS)
# =====================================================
class EnvironmentManager:
    def __init__(self):
        self.stage = omni.usd.get_context().get_stage()
        self.light_path = "/World/DirectionalLight"
        self._setup_light()

    def _setup_light(self):
        if not self.stage.GetPrimAtPath(self.light_path).IsValid():
            self.light = UsdLux.DistantLight.Define(self.stage, self.light_path)
        else:
            self.light = UsdLux.DistantLight(self.stage.GetPrimAtPath(self.light_path))
            
        xform = UsdGeom.Xformable(self.light)
        xform.ClearXformOpOrder()
        xform.AddRotateXYZOp().Set(Gf.Vec3f(-45.0, 30.0, 0.0))

    def set_shift(self, shift_type):
        shift = shift_type.lower()
        
        if shift == "diurno":
            self.light.CreateColorAttr().Set(Gf.Vec3f(1.0, 0.95, 0.85))
            self.light.CreateIntensityAttr().Set(5000.0) 
            self.light.GetPrim().CreateAttribute("inputs:exposure", Sdf.ValueTypeNames.Float).Set(2.0)
            print("☀️ TURNO DIURNO ACTIVADO: Sol a máxima capacidad.")
            
        elif shift == "nocturno":
            self.light.CreateColorAttr().Set(Gf.Vec3f(0.1, 0.2, 0.6))
            self.light.CreateIntensityAttr().Set(500.0)
            self.light.GetPrim().CreateAttribute("inputs:exposure", Sdf.ValueTypeNames.Float).Set(-3.0)
            print("🌙 TURNO NOCTURNO ACTIVADO: Escena a oscuras.")

# =====================================================
# 6A. ROBOT DE EXTRACCIÓN (OUTBOUND / PICKER)
# =====================================================
class RobotPicker:
    def __init__(self, robot_id="Robot_Alpha"):
        self.stage = omni.usd.get_context().get_stage()
        self.robot_id = robot_id
        self.robot_path = f"/World/{robot_id}"
        self.hook_path = f"{self.robot_path}/Hook"
        
        self.ROBOT_BASE_USD = r"C:\Users\krono\Downloads\robot_base.usdc" 
        self.ROBOT_HOOK_USD = r"C:\Users\krono\Downloads\robot_hook.usdc"
        
        self.GANCHO_DESFASE_X = -500.0  
        self.GANCHO_DESFASE_Y = 0.0   
        self.HOOK_OFFSET_Z = 0.0      
        self.MARGEN_ACOPLE = 20.0     
        self._load_robot_models()

    def _load_robot_models(self):
        if self.stage.GetPrimAtPath(self.robot_path).IsValid(): return
        self.stage.DefinePrim(self.robot_path, "Xform").GetReferences().AddReference(self.ROBOT_BASE_USD)
        hook = self.stage.DefinePrim(self.hook_path, "Xform")
        hook.GetReferences().AddReference(self.ROBOT_HOOK_USD)
        UsdGeom.Xformable(hook).AddRotateXYZOp(opSuffix="rotacion_inicial").Set(Gf.Vec3f(90.0, 0.0, 0.0))

    def animate_picking_cycle(self, start_x, start_y, target_bin_id, bin_manager):
        if target_bin_id not in bin_manager.bins: return
        
        bin_data = bin_manager.bins[target_bin_id]
        bin_prim = self.stage.GetPrimAtPath(f"/World/Grid/Cell_{bin_data.x}_{bin_data.y}_{bin_data.z}/Bin")
        
        z_nav = (GRID_Z * CELL_SPACING_Z) - 300
        cx, cy = bin_data.x * CELL_SPACING_X, bin_data.y * CELL_SPACING_Y
        destino_robot_x = cx - self.GANCHO_DESFASE_X
        destino_robot_y = cy - self.GANCHO_DESFASE_Y
        
        pos_inicio = Gf.Vec3d(start_x, start_y, z_nav)
        pos_destino_xy = Gf.Vec3d(destino_robot_x, destino_robot_y, z_nav)
        pos_puerto_xy = Gf.Vec3d(0, 0, z_nav) 
        
        pos_caja_z = bin_data.z * CELL_SPACING_Z
        dist_descenso = pos_caja_z - (z_nav + self.HOOK_OFFSET_Z) + self.MARGEN_ACOPLE

        rob_trans = next((op for op in UsdGeom.Xformable(self.stage.GetPrimAtPath(self.robot_path)).GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), UsdGeom.Xformable(self.stage.GetPrimAtPath(self.robot_path)).AddTranslateOp())
        hook_trans = next((op for op in UsdGeom.Xformable(self.stage.GetPrimAtPath(self.hook_path)).GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), UsdGeom.Xformable(self.stage.GetPrimAtPath(self.hook_path)).AddTranslateOp())
        bin_trans = next((op for op in UsdGeom.Xformable(bin_prim).GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), None) if bin_prim.IsValid() else None

        f_actual = 1
        rob_trans.Set(pos_inicio, f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)
        
        f_actual += 60  
        rob_trans.Set(Gf.Vec3d(pos_destino_xy[0], pos_inicio[1], z_nav), f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)
        
        f_actual += 60  
        rob_trans.Set(pos_destino_xy, f_actual)
        hook_trans.Set(Gf.Vec3d(0, 0, 0), 1)
        hook_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)

        f_actual += 45  
        hook_trans.Set(Gf.Vec3d(0, 0, dist_descenso), f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, 0), f_actual) 

        frames_ascenso = 45
        for frame in range(1, frames_ascenso + 1):
            t = float(frame) / float(frames_ascenso)
            fk = f_actual + frame
            hook_trans.Set(Gf.Vec3d(0, 0, dist_descenso * (1.0 - t)), fk)
            if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, -dist_descenso * t), fk)

        f_actual += frames_ascenso

        f_actual += 60  
        rob_trans.Set(Gf.Vec3d(pos_destino_xy[0], pos_puerto_xy[1], z_nav), f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(pos_destino_xy[0] - cx, pos_puerto_xy[1] - cy, -dist_descenso), f_actual)

        f_actual += 60  
        rob_trans.Set(pos_puerto_xy, f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(pos_puerto_xy[0] - cx, pos_puerto_xy[1] - cy, -dist_descenso), f_actual)

        self.stage.SetStartTimeCode(1)
        self.stage.SetEndTimeCode(f_actual)

# =====================================================
# 6B. ROBOT DE REPOSICIÓN (INBOUND / RESTOCK)
# =====================================================
class RobotRestock:
    def __init__(self, robot_id="Robot_Beta"):
        self.stage = omni.usd.get_context().get_stage()
        self.robot_id = robot_id
        self.robot_path = f"/World/{robot_id}"
        self.hook_path = f"{self.robot_path}/Hook"
        
        self.ROBOT_BASE_USD = r"C:\Users\krono\Downloads\robot_base.usdc" 
        self.ROBOT_HOOK_USD = r"C:\Users\krono\Downloads\robot_hook.usdc"
        
        self.GANCHO_DESFASE_X = -500.0  
        self.GANCHO_DESFASE_Y = 0.0   
        self.HOOK_OFFSET_Z = 0.0      
        self.MARGEN_ACOPLE = 20.0     
        self._load_robot_models()

    def _load_robot_models(self):
        if self.stage.GetPrimAtPath(self.robot_path).IsValid(): return
        self.stage.DefinePrim(self.robot_path, "Xform").GetReferences().AddReference(self.ROBOT_BASE_USD)
        hook = self.stage.DefinePrim(self.hook_path, "Xform")
        hook.GetReferences().AddReference(self.ROBOT_HOOK_USD)
        UsdGeom.Xformable(hook).AddRotateXYZOp(opSuffix="rotacion_inicial").Set(Gf.Vec3f(90.0, 0.0, 0.0))

    def animate_restock_cycle(self, start_x, start_y, target_bin_id, bin_manager):
        if target_bin_id not in bin_manager.bins: return
        
        bin_data = bin_manager.bins[target_bin_id]
        bin_prim = self.stage.GetPrimAtPath(f"/World/Grid/Cell_{bin_data.x}_{bin_data.y}_{bin_data.z}/Bin")
        
        z_nav = (GRID_Z * CELL_SPACING_Z) - 300
        cx, cy = bin_data.x * CELL_SPACING_X, bin_data.y * CELL_SPACING_Y
        destino_robot_x = cx - self.GANCHO_DESFASE_X
        destino_robot_y = cy - self.GANCHO_DESFASE_Y
        
        pos_inicio = Gf.Vec3d(start_x, start_y, z_nav)
        pos_destino_xy = Gf.Vec3d(destino_robot_x, destino_robot_y, z_nav)
        
        pos_caja_z = bin_data.z * CELL_SPACING_Z
        dist_descenso = pos_caja_z - (z_nav + self.HOOK_OFFSET_Z) + self.MARGEN_ACOPLE

        rob_trans = next((op for op in UsdGeom.Xformable(self.stage.GetPrimAtPath(self.robot_path)).GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), UsdGeom.Xformable(self.stage.GetPrimAtPath(self.robot_path)).AddTranslateOp())
        hook_trans = next((op for op in UsdGeom.Xformable(self.stage.GetPrimAtPath(self.hook_path)).GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), UsdGeom.Xformable(self.stage.GetPrimAtPath(self.hook_path)).AddTranslateOp())
        bin_trans = next((op for op in UsdGeom.Xformable(bin_prim).GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), None) if bin_prim.IsValid() else None

        f_actual = 1
        rob_trans.Set(pos_inicio, f_actual)
        hook_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)
        start_box_x = (pos_inicio[0] + self.GANCHO_DESFASE_X) - cx
        start_box_y = (pos_inicio[1] + self.GANCHO_DESFASE_Y) - cy
        if bin_trans: bin_trans.Set(Gf.Vec3d(start_box_x, start_box_y, -dist_descenso), f_actual)

        f_actual += 60
        pos_mid = Gf.Vec3d(pos_destino_xy[0], pos_inicio[1], z_nav)
        rob_trans.Set(pos_mid, f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, start_box_y, -dist_descenso), f_actual)

        f_actual += 60
        rob_trans.Set(pos_destino_xy, f_actual)
        hook_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, -dist_descenso), f_actual)

        frames_desc = 45
        for frame in range(1, frames_desc + 1):
            t = float(frame) / float(frames_desc)
            fk = f_actual + frame
            hook_trans.Set(Gf.Vec3d(0, 0, dist_descenso * t), fk)
            if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, -dist_descenso * (1.0 - t)), fk)
        f_actual += frames_desc

        frames_asc = 45
        for frame in range(1, frames_asc + 1):
            t = float(frame) / float(frames_asc)
            fk = f_actual + frame
            hook_trans.Set(Gf.Vec3d(0, 0, dist_descenso * (1.0 - t)), fk)
            if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, 0), fk) 
        f_actual += frames_asc

        f_actual += 60
        rob_trans.Set(pos_mid, f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)
        
        f_actual += 60
        rob_trans.Set(pos_inicio, f_actual)
        if bin_trans: bin_trans.Set(Gf.Vec3d(0, 0, 0), f_actual)

        self.stage.SetStartTimeCode(1)
        self.stage.SetEndTimeCode(f_actual)

# =====================================================
# 7. ORQUESTACIÓN PARA PRUEBA
# =====================================================
grid = GridBuilder()
grid.build()
bins = BinManager()
env = EnvironmentManager()

env.set_shift("diurno")

# 🛑 AHORA PASAMOS LA Z EXPLÍCITAMENTE (x, y, z)
id_nueva_caja = bins.add_bin(bin_id="CAJA_TEST_01", x=0, y=0, z=0, sku="IPHONE15")

robot_entrada = RobotRestock("Robot_Inbound")
robot_entrada.animate_restock_cycle(start_x=0, start_y=0, target_bin_id=id_nueva_caja, bin_manager=bins)

timeline = omni.timeline.get_timeline_interface()
timeline.set_start_time(1.0 / 60.0)
timeline.play()
