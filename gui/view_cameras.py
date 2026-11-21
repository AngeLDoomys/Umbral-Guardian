# -*- coding: utf-8 -*-
"""
gui/view_cameras.py - Gestión de cámaras y zonas de acceso (almacenadas en la BD).
Añadir, editar, probar y eliminar cámaras.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from core.camera_manager import CameraManager, CameraConfig, TIPOS_FUENTE, _parse_source
from core import session

BG_DARK  = "#1e1e2e"
BG_PANEL = "#2d2d44"
BG_ITEM  = "#3d3d5c"
FG_GREEN = "#00ff88"
FG_WHITE = "#ffffff"
FG_GRAY  = "#aaaaaa"
FG_WARN  = "#ffaa00"
FG_RED   = "#ff4444"
FG_BLUE  = "#4488ff"


class CamerasView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self._mgr = CameraManager()
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📷  Cámaras y zonas de acceso",
                 font=("Segoe UI", 14, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        list_frame = tk.Frame(body, bg=BG_PANEL)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        tk.Label(list_frame, text="Cámaras configuradas",
                 font=("Segoe UI", 11, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            pady=10, padx=10, anchor=tk.W)

        cols = ("id", "name", "zona", "type", "source", "enabled")
        self._tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=14)
        for col, hdr, w in [
            ("id", "ID", 50), ("name", "Nombre", 150), ("zona", "Zona", 140),
            ("type", "Tipo", 70), ("source", "Fuente", 220), ("enabled", "Activa", 60),
        ]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=10)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        btn_row = tk.Frame(list_frame, bg=BG_PANEL)
        btn_row.pack(fill=tk.X, padx=10, pady=10)
        for text, cmd, bg in [
            ("+ Añadir", self._add_dialog, FG_GREEN),
            ("✎ Editar", self._edit_dialog, FG_BLUE),
            ("🗑 Eliminar", self._delete, FG_RED),
            ("✔ Probar", self._test_source, FG_WARN),
        ]:
            tk.Button(btn_row, text=text, command=cmd, font=("Segoe UI", 10, "bold"),
                      bg=bg, fg="black" if bg == FG_GREEN else FG_WHITE,
                      width=10, cursor="hand2", relief=tk.FLAT).pack(
                side=tk.LEFT, padx=4)

        self._detail_frame = tk.Frame(body, bg=BG_PANEL, width=300)
        self._detail_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self._detail_frame.pack_propagate(False)

        tk.Label(self._detail_frame, text="Detalle",
                 font=("Segoe UI", 11, "bold"), bg=BG_PANEL, fg=FG_GREEN).pack(
            pady=10, padx=15, anchor=tk.W)

        self._detail_text = tk.Text(self._detail_frame, font=("Consolas", 10),
                                    bg=BG_ITEM, fg=FG_WHITE, state=tk.DISABLED,
                                    relief=tk.FLAT, width=34)
        self._detail_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._load_list()

    # ── list ──────────────────────────────────────────────────────────────

    def _load_list(self):
        self._mgr.load()
        for row in self._tree.get_children():
            self._tree.delete(row)
        for cam in self._mgr.cameras:
            self._tree.insert("", tk.END, iid=cam.id, values=(
                cam.id, cam.name, cam.zona, cam.type,
                str(cam.source), "Sí" if cam.enabled else "No",
            ))

    def _on_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        cam = self._mgr.get_by_id(sel[0])
        if not cam:
            return
        info = (
            f"ID:         {cam.id}\n"
            f"Nombre:     {cam.name}\n"
            f"Zona:       {cam.zona}\n"
            f"Tipo:       {cam.type}\n"
            f"Fuente:     {cam.source}\n"
            f"Fuente alta:{' ' + cam.source_hi if cam.source_hi else ' — (un solo canal)'}\n"
            f"Resolución: {cam.resolution[0]}×{cam.resolution[1]}\n"
            f"FPS:        {cam.fps}\n"
            f"Activa:     {'Sí' if cam.enabled else 'No'}\n"
        )
        self._detail_text.config(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert("1.0", info)
        self._detail_text.config(state=tk.DISABLED)

    # ── CRUD dialogs ──────────────────────────────────────────────────────

    def _add_dialog(self):
        s = session.current
        if s and s.max_camaras and len(self._mgr.cameras) >= s.max_camaras:
            messagebox.showwarning(
                "Límite del plan",
                f"El plan {s.plan} permite {s.max_camaras} cámaras.\n"
                "Contacte al proveedor para cambiar de plan.")
            return
        self._open_form_dialog(None)

    def _edit_dialog(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una cámara")
            return
        self._open_form_dialog(self._mgr.get_by_id(sel[0]))

    def _open_form_dialog(self, cam: CameraConfig = None):
        dlg = tk.Toplevel(self)
        dlg.title("Agregar cámara" if cam is None else "Editar cámara")
        dlg.geometry("500x600")
        dlg.configure(bg=BG_PANEL)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        fields = {}

        def label(text):
            tk.Label(dlg, text=text, font=("Segoe UI", 10), bg=BG_PANEL, fg=FG_WHITE,
                     anchor=tk.W).pack(fill=tk.X, padx=20, pady=(5, 0))

        def row(text, default=""):
            label(text)
            e = tk.Entry(dlg, font=("Segoe UI", 10), bg=BG_ITEM,
                         fg=FG_WHITE, insertbackground=FG_WHITE)
            e.insert(0, str(default))
            e.pack(fill=tk.X, padx=20)
            return e

        label("Tipo:")
        type_var = tk.StringVar(value=cam.type if cam else "rtsp")
        ttk.Combobox(dlg, textvariable=type_var, values=TIPOS_FUENTE,
                     state="readonly", font=("Segoe UI", 10)).pack(fill=tk.X, padx=20)

        label("Zona de acceso (elija o escriba una nueva):")
        zona_var = tk.StringVar(value=cam.zona if cam else "Acceso principal")
        ttk.Combobox(dlg, textvariable=zona_var,
                     values=[z["nombre"] for z in self._mgr.zonas()],
                     font=("Segoe UI", 10)).pack(fill=tk.X, padx=20)

        fields["name"]   = row("Nombre:", cam.name if cam else "Cámara nueva")
        fields["source"] = row("Fuente (índice USB o URL; en RTSP doble, el substream de baja):",
                               cam.source if cam else "")
        fields["source_hi"] = row("Fuente alta resolución (opcional, RTSP canal principal):",
                                  (cam.source_hi or "") if cam else "")
        fields["res_w"]  = row("Ancho px:", cam.resolution[0] if cam else 1280)
        fields["res_h"]  = row("Alto px:", cam.resolution[1] if cam else 720)
        fields["fps"]    = row("FPS:", cam.fps if cam else 30)

        enabled_var = tk.BooleanVar(value=cam.enabled if cam else True)
        tk.Checkbutton(dlg, text="Activa", variable=enabled_var,
                       bg=BG_PANEL, fg=FG_WHITE, selectcolor=BG_ITEM,
                       activebackground=BG_PANEL, font=("Segoe UI", 10)).pack(
            anchor=tk.W, padx=20, pady=5)

        def save():
            tipo = type_var.get()
            src = _parse_source(fields["source"].get().strip(), tipo)
            zona = zona_var.get().strip()
            if src == "" or not zona:
                messagebox.showerror("Error", "Fuente y zona son obligatorias", parent=dlg)
                return
            try:
                w, h = int(fields["res_w"].get()), int(fields["res_h"].get())
                fps = int(fields["fps"].get())
            except ValueError:
                messagebox.showerror("Error", "Ancho, alto y FPS deben ser numéricos", parent=dlg)
                return
            data = CameraConfig(
                id=cam.id if cam else "", name=fields["name"].get().strip() or "Cámara",
                source=src, type=tipo, enabled=enabled_var.get(),
                resolution=[w, h], fps=fps,
                source_hi=fields["source_hi"].get().strip() or None,
            )
            try:
                if cam is None:
                    self._mgr.add(data, zona)
                else:
                    self._mgr.update(data, zona)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=dlg)
                return
            dlg.destroy()
            self._load_list()
            self._app.notify_cameras_changed()

        tk.Button(dlg, text="Guardar", command=save,
                  font=("Segoe UI", 11, "bold"), bg=FG_GREEN, fg="black",
                  width=18, cursor="hand2", relief=tk.FLAT).pack(pady=15)

    def _delete(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una cámara")
            return
        if messagebox.askyesno("Confirmar",
                               "¿Eliminar la cámara seleccionada?\n"
                               "También se borrará su historial de detecciones."):
            self._mgr.remove(sel[0])
            self._load_list()
            self._app.notify_cameras_changed()

    def _test_source(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una cámara")
            return
        cam = self._mgr.get_by_id(sel[0])
        if cam:
            results = [(cam.source, CameraManager.test_source(cam.source))]
            if cam.source_hi:
                results.append((cam.source_hi, CameraManager.test_source(cam.source_hi)))
            msg = "\n".join(f"{'✅' if ok else '❌'} '{src}' {'accesible' if ok else 'no se puede abrir'}"
                            for src, ok in results)
            if all(ok for _, ok in results):
                messagebox.showinfo("Resultado", msg)
            else:
                messagebox.showerror("Resultado", msg)

    def on_show(self):
        self._load_list()
