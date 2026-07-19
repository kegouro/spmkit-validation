"""Exportador ASCII para Gwyddion.

Gwyddion puede importar matrices de texto ASCII puro y luego se le asignan las 
dimensiones físicas manualmente. Este módulo automatiza la conversión del phantom a .asc.
"""
import numpy as np
from pathlib import Path


def export_npz_to_asc(npz_path: Path, output_dir: Path) -> None:
    """Convierte observed.npz en observed.asc y observed_metadata.txt."""
    data = np.load(npz_path)
    z_data = data["z_data"]
    x_size_m = data["x_size_m"][0]
    y_size_m = data["y_size_m"][0]
    z_unit = data["z_unit"][0]
    
    # Exportar ASCII de la matriz (tab-separated)
    asc_path = output_dir / "observed.asc"
    np.savetxt(asc_path, z_data, delimiter="\t")
    
    # Exportar metadatos para que el operador sepa qué ingresar en la GUI
    meta_path = output_dir / "observed_metadata.txt"
    with meta_path.open("w", encoding="utf-8") as f:
        f.write("=== METADATOS PARA GWYDDION (Import ASCII) ===\n")
        f.write(f"Ancho (Width) X: {x_size_m} m\n")
        f.write(f"Alto (Height) Y: {y_size_m} m\n")
        f.write(f"Unidad Z: {z_unit}\n")
        f.write(f"Resolucion: {z_data.shape[1]} x {z_data.shape[0]} px\n")
        f.write("\nEn 'Data Scale', introduce el Width y Height exactamente como aparecen arriba.\n")
