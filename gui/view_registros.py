# -*- coding: utf-8 -*-
"""
gui/view_registros.py - Registro desde el celular (administrador y conserje).

Izquierda: generar una invitación (QR y enlace) para un residente nuevo, para
que un residente ya registrado capture su rostro, o para una visita.
Derecha: solicitudes recibidas desde los celulares, a la espera de aprobación.
Nada entra al sistema sin que alguien de la administración lo apruebe.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from PIL import ImageTk

import config
from core import cloud, registro_remoto, session
from database import DatabaseManager

BG_DARK  = "#1e1e2e"
BG_PANEL = "#2d2d44"
BG_ITEM  = "#3d3d5c"
FG_GREEN = "#00ff88"
FG_WHITE = "#ffffff"
FG_GRAY  = "#aaaaaa"
FG_WARN  = "#ffaa00"
FG_RED   = "#ff4444"
FG_BLUE  = "#4488ff"

TIPOS = [("Residente nuevo", "residente"),
         ("Solo rostro (residente ya registrado)", "rostro"),
         ("Visita", "visita")]
VIGENCIAS = {"24 horas": 24, "48 horas": 48, "3 días": 72, "7 días": 168}
DESCARGA_CADA_MS = 60_000


class RegistrosView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self._app = app
        self.db = DatabaseManager()
        self._solicitudes: list = []
        self._qr_img = None
        self._build_ui()
        self.after(5000, self._descarga_periodica)

    def _conectar(self) -> bool:
        return self.db.is_connected() or self.db.connect()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = tk.Frame(self, bg=BG_PANEL, height=50)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📱  Registro desde el celular", font=("Segoe UI", 14, "bold"),
                 bg=BG_PANEL, fg=FG_GREEN).pack(side=tk.LEFT, padx=20, pady=10)
        self._estado = tk.Label(top, text="", font=("Segoe UI", 9), bg=BG_PANEL, fg=FG_GRAY)
        self._estado.pack(side=tk.RIGHT, padx=20)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # ── invitación ──
        izq = tk.Frame(body, bg=BG_PANEL, width=380)
        izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        izq.pack_propagate(False)
        tk.Label(izq, text="Nueva invitación", font=("Segoe UI", 12, "bold"), bg=BG_PANEL,
                 fg=FG_GREEN).pack(anchor=tk.W, padx=15, pady=(12, 6))

        self._tipo = tk.StringVar(value="residente")
        for texto, valor in TIPOS:
            tk.Radiobutton(izq, text=texto, variable=self._tipo, value=valor,
                           command=self._cambio_tipo, bg=BG_PANEL, fg=FG_WHITE,
                           selectcolor=BG_ITEM, activebackground=BG_PANEL,
                           font=("Segoe UI", 10)).pack(anchor=tk.W, padx=15)

        f = tk.Frame(izq, bg=BG_PANEL)
        f.pack(fill=tk.X, padx=15, pady=8)
        tk.Label(f, text="Unidad", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky=tk.W, pady=3)
        self._unidad = ttk.Combobox(f, font=("Segoe UI", 10), width=24)
        self._unidad.grid(row=0, column=1, pady=3, padx=(6, 0))
        tk.Label(f, text="Residente", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 9)).grid(
            row=1, column=0, sticky=tk.W, pady=3)
        self._residente = ttk.Combobox(f, font=("Segoe UI", 10), width=24, state=tk.DISABLED)
        self._residente.grid(row=1, column=1, pady=3, padx=(6, 0))
        tk.Label(f, text="Vigencia", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 9)).grid(
            row=2, column=0, sticky=tk.W, pady=3)
        self._vigencia = ttk.Combobox(f, values=list(VIGENCIAS), state="readonly", width=24,
                                      font=("Segoe UI", 10))
        self._vigencia.current(1)
        self._vigencia.grid(row=2, column=1, pady=3, padx=(6, 0))
        self._frecuente = tk.BooleanVar(value=False)
        self._chk_frecuente = tk.Checkbutton(
            f, text="Visita frecuente (sin fecha de término)", variable=self._frecuente,
            bg=BG_PANEL, fg=FG_WHITE, selectcolor=BG_ITEM, activebackground=BG_PANEL,
            font=("Segoe UI", 9), state=tk.DISABLED)
        self._chk_frecuente.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        tk.Button(izq, text="Generar QR", command=self._generar, font=("Segoe UI", 11, "bold"),
                  bg=FG_GREEN, fg="black", relief=tk.FLAT, cursor="hand2").pack(pady=8)
        tk.Label(izq, text="El QR se abre en una ventana aparte, con el enlace\npara copiar "
                           "y mandar por WhatsApp.\nUn solo uso; se abre desde cualquier lugar.",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=FG_GRAY, justify=tk.LEFT).pack(
            anchor=tk.W, padx=15)

        # ── solicitudes ──
        der = tk.Frame(body, bg=BG_PANEL)
        der.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(der, text="Solicitudes por revisar", font=("Segoe UI", 12, "bold"), bg=BG_PANEL,
                 fg=FG_GREEN).pack(anchor=tk.W, padx=12, pady=(12, 4))
        cols = ("fecha", "tipo", "unidad", "nombre", "rut", "detalle")
        self._tree = ttk.Treeview(der, columns=cols, show="headings", height=14)
        for col, hdr, w in [("fecha", "Recibida", 120), ("tipo", "Tipo", 90),
                            ("unidad", "Unidad", 80), ("nombre", "Nombre", 180),
                            ("rut", "RUT", 100), ("detalle", "Detalle", 220)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=12)
        self._tree.bind("<Double-1>", lambda e: self._detalle())

        btns = tk.Frame(der, bg=BG_PANEL)
        btns.pack(fill=tk.X, padx=12, pady=10)
        for texto, cmd, bg in [("✔ Aprobar", self._aprobar, FG_GREEN),
                               ("✖ Rechazar", self._rechazar, FG_RED),
                               ("👁 Ver detalle", self._detalle, BG_ITEM),
                               ("🔄 Revisar nuevos", self._descargar, FG_BLUE),
                               ("👥 Visitas autorizadas", self._autorizadas, BG_ITEM)]:
            tk.Button(btns, text=texto, command=cmd, font=("Segoe UI", 10, "bold"), bg=bg,
                      fg="black" if bg == FG_GREEN else FG_WHITE, relief=tk.FLAT,
                      cursor="hand2", padx=8).pack(side=tk.LEFT, padx=(0, 6))

    # ── invitaciones ──────────────────────────────────────────────────────

    def _cambio_tipo(self):
        self._residente.config(state="readonly" if self._tipo.get() == "rostro" else tk.DISABLED)
        self._chk_frecuente.config(state=tk.NORMAL if self._tipo.get() == "visita" else tk.DISABLED)
        if self._tipo.get() != "visita":
            self._frecuente.set(False)

    def _cargar_listas(self):
        if not self._conectar():
            return
        self._unidades = {u["codigo"]: u["idunidad"] for u in self.db.list_unidades()}
        self._unidad["values"] = list(self._unidades)
        self._residentes = {f"{r['nombres']} {r['apellidos']} ({r['unidad']})": r
                            for r in self.db.list_residentes()}
        self._residente["values"] = list(self._residentes)

    def _generar(self):
        s = session.current
        if s.offline:
            messagebox.showwarning("Sin conexión", "Las invitaciones necesitan conexión con la "
                                                   "nube. Inicie sesión con internet.")
            return
        if not self._conectar():
            messagebox.showerror("Error", "Sin conexión con la base local")
            return
        tipo, idresidente = self._tipo.get(), None
        if tipo == "rostro":
            r = self._residentes.get(self._residente.get())
            if not r:
                messagebox.showwarning("Aviso", "Seleccione el residente")
                return
            if r["tratamiento_bloqueado"]:
                messagebox.showwarning("Bloqueado", "El tratamiento de este titular está bloqueado")
                return
            idunidad, codigo, idresidente, tipo = r["idunidad"], r["unidad"], r["idresidente"], "residente"
        else:
            codigo = self._unidad.get().strip()
            if not codigo:
                messagebox.showwarning("Aviso", "Indique la unidad (por ejemplo «Casa 12»)")
                return
            idunidad = self._unidades.get(codigo) or self.db.get_or_create_unidad(codigo)
        try:
            url = registro_remoto.crear_invitacion(
                self.db, tipo, idunidad, codigo, VIGENCIAS[self._vigencia.get()],
                s.idcuenta, idresidente, frecuente=self._frecuente.get())
        except cloud.CloudError as e:
            messagebox.showerror("Error", f"No se pudo crear la invitación:\n{e}")
            return
        titulo = {"residente": "Registro de residente", "rostro": "Registro de rostro",
                  "visita": "Registro de visita"}[self._tipo.get()]
        if self._frecuente.get():
            titulo += " frecuente"
        self._mostrar_qr(url, f"{titulo} · {codigo}", self._vigencia.get())
        self._cargar_listas()

    def _mostrar_qr(self, url, titulo, vigencia):
        """Ventana aparte, grande y centrada: para escanear en la portería o copiar el enlace."""
        import qrcode
        win = tk.Toplevel(self)
        win.title("Invitación de registro")
        win.configure(bg=BG_PANEL)
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        lado = min(380, int(win.winfo_screenheight() * 0.45))
        img = qrcode.make(url, box_size=8, border=2).get_image().convert("RGB").resize((lado, lado))
        self._qr_img = ImageTk.PhotoImage(img)
        tk.Label(win, text=titulo, font=("Segoe UI", 13, "bold"), bg=BG_PANEL,
                 fg=FG_GREEN).pack(padx=20, pady=(14, 2))
        tk.Label(win, text="Escanee con la cámara del celular", font=("Segoe UI", 10),
                 bg=BG_PANEL, fg=FG_WHITE).pack()
        tk.Label(win, image=self._qr_img, bg="white").pack(padx=20, pady=10)
        url_e = tk.Entry(win, font=("Consolas", 9), bg=BG_ITEM, fg=FG_WHITE, width=52,
                         readonlybackground=BG_ITEM, relief=tk.FLAT, justify=tk.CENTER)
        url_e.insert(0, url)
        url_e.config(state="readonly")
        url_e.pack(padx=20)
        tk.Label(win, text=f"Un solo uso · vence en {vigencia}", font=("Segoe UI", 9),
                 bg=BG_PANEL, fg=FG_GRAY).pack(pady=(4, 0))
        fila = tk.Frame(win, bg=BG_PANEL)
        fila.pack(pady=12)

        def copiar():
            win.clipboard_clear()
            win.clipboard_append(url)
            b.config(text="✔ Copiado")

        b = tk.Button(fila, text="Copiar enlace (WhatsApp)", command=copiar, bg=FG_BLUE,
                      fg=FG_WHITE, font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=8)
        b.pack(side=tk.LEFT, padx=4)
        tk.Button(fila, text="Cerrar", command=win.destroy, bg=BG_ITEM, fg=FG_WHITE,
                  font=("Segoe UI", 10), relief=tk.FLAT, padx=12).pack(side=tk.LEFT, padx=4)
        win.update_idletasks()
        x = (win.winfo_screenwidth() - win.winfo_width()) // 2
        y = max(0, (win.winfo_screenheight() - win.winfo_height()) // 2 - 30)
        win.geometry(f"+{x}+{y}")
        win.lift()
        win.focus_force()

    # ── solicitudes ───────────────────────────────────────────────────────

    def _descargar(self, silencioso=False):
        if session.current is None or session.current.offline or not self._conectar():
            return
        try:
            n = registro_remoto.descargar(self.db)
            self._estado.config(text=f"Nube revisada {self._hora()}" +
                                (f" · {n} nuevo(s)" if n else ""), fg=FG_GRAY)
        except cloud.CloudError as e:
            self._estado.config(text="Sin conexión con la nube", fg=FG_WARN)
            if not silencioso:
                messagebox.showwarning("Sin conexión", str(e))
        self._cargar()

    @staticmethod
    def _hora():
        from datetime import datetime
        return datetime.now().strftime("%H:%M")

    def _descarga_periodica(self):
        try:
            if self.winfo_exists():
                self._descargar(silencioso=True)
        finally:
            self.after(DESCARGA_CADA_MS, self._descarga_periodica)

    def _cargar(self):
        if not self._conectar():
            return
        self._solicitudes = self.db.list_solicitudes_registro("pendiente")
        for r in self._tree.get_children():
            self._tree.delete(r)
        for s in self._solicitudes:
            d = s["datos"]
            if s["tipo"] == "visita":
                tipo = "Visita frec." if s["frecuente"] else "Visita"
                detalle = ("frecuente" if s["frecuente"] else f"llega el {d.get('fecha_visita', '?')}")
                detalle += (f" · {s['fotos']} fotos" if s["fotos"] else "") + \
                           (f" · patente {d['patente']}" if d.get("patente") else "")
                nombre = f"{d.get('nombres', '')} {d.get('apellidos', '')}"
            else:
                tipo = "Rostro" if s["idresidente"] else "Residente"
                nombre = s["residente_existente"] or f"{d.get('nombres', '')} {d.get('apellidos', '')}"
                detalle = f"{s['fotos']} fotos"
                if d.get("vehiculo"):
                    detalle += f" · {d['vehiculo']['tipo']} {d['vehiculo']['patente']}"
            fecha = s["fecha_envio"].strftime("%d/%m %H:%M") if s["fecha_envio"] else "—"
            self._tree.insert("", tk.END, iid=str(s["idsolicitud"]), values=(
                fecha, tipo, s["unidad"], nombre, d.get("rut", "—"), detalle))

    def _sel(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una solicitud")
            return None
        return next(s for s in self._solicitudes if str(s["idsolicitud"]) == sel[0])

    def _aprobar(self):
        s = self._sel()
        if not s:
            return
        cuenta = session.current.idcuenta
        try:
            if s["tipo"] == "visita":
                d = s["datos"]
                cuando = ("como visita frecuente" if s["frecuente"]
                          else f"para el {d.get('fecha_visita')}")
                if not messagebox.askyesno("Aprobar visita",
                                           f"¿Autorizar a {d.get('nombres')} {d.get('apellidos')} "
                                           f"{cuando}?\nLa cámara la reconocerá; el ingreso se "
                                           "registra cuando llegue (👥 Visitas autorizadas)."):
                    return
                self.db.aprobar_solicitud_visita(s["idsolicitud"], cuenta)
            else:
                nombre = s["residente_existente"] or \
                    f"{s['datos'].get('nombres')} {s['datos'].get('apellidos')}"
                if not messagebox.askyesno("Aprobar", f"¿Aprobar el registro de {nombre}?\n"
                                                      "Verifique que sea quien dice ser."):
                    return
                self.db.aprobar_solicitud_residente(s["idsolicitud"], cuenta)
        except ValueError as e:
            messagebox.showerror("No se pudo aprobar", str(e))
            return
        self._cargar()

    def _rechazar(self):
        s = self._sel()
        if not s:
            return
        motivo = simpledialog.askstring("Rechazar", "Motivo (opcional):", parent=self)
        if motivo is None:
            return
        self.db.rechazar_solicitud(s["idsolicitud"], session.current.idcuenta,
                                   (motivo or "").strip()[:300] or None)
        self._cargar()

    def _detalle(self):
        s = self._sel()
        if not s:
            return
        d = s["datos"]
        etiquetas = {"nombres": "Nombres", "apellidos": "Apellidos", "rut": "RUT",
                     "telefono": "Teléfono", "email": "Correo", "fecha_nacimiento": "Nacimiento",
                     "fecha_visita": "Fecha de visita", "patente": "Patente"}
        lineas = [f"Unidad: {s['unidad']}"]
        if s["residente_existente"]:
            lineas.append(f"Residente: {s['residente_existente']} (solo rostro)")
        lineas += [f"{etiquetas[k]}: {v}" for k, v in d.items() if k in etiquetas and v]
        if d.get("vehiculo"):
            v = d["vehiculo"]
            lineas.append(f"Vehículo: {v['tipo']} {v['patente']} "
                          f"{v.get('marca') or ''} {v.get('color') or ''}".strip())
        if s["tipo"] == "residente":
            lineas.append(f"Fotos del rostro: {s['fotos']} (solo se guardan vectores)")
            lineas.append(f"Consentimiento {s['consentimiento_version']} aceptado el "
                          f"{s['consentimiento_fecha']}")
        messagebox.showinfo("Detalle de la solicitud", "\n".join(lineas))

    def _autorizadas(self):
        if self._conectar():
            AutorizadasDialog(self, self.db)

    def on_show(self):
        self._cargar_listas()
        self._descargar(silencioso=True)


class AutorizadasDialog:
    """Visitas autorizadas (ocasionales de hoy en adelante y frecuentes): registrar
    su ingreso cuando llegan, o revocarlas (se borran con su rostro)."""

    def __init__(self, parent, db):
        self._db = db
        w = self._w = tk.Toplevel(parent)
        w.title("Visitas autorizadas")
        w.geometry("820x420")
        w.configure(bg=BG_PANEL)
        w.transient(parent.winfo_toplevel())
        tk.Label(w, text="Visitas autorizadas", font=("Segoe UI", 12, "bold"), bg=BG_PANEL,
                 fg=FG_GREEN).pack(anchor=tk.W, padx=15, pady=(12, 6))
        cols = ("nombre", "rut", "unidad", "tipo", "vigencia", "patente", "rostro")
        self._tree = ttk.Treeview(w, columns=cols, show="headings", height=12)
        for col, hdr, wd in [("nombre", "Nombre", 170), ("rut", "RUT", 95), ("unidad", "Unidad", 90),
                             ("tipo", "Tipo", 80), ("vigencia", "Vigencia", 150),
                             ("patente", "Patente", 70), ("rostro", "Rostro", 60)]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=wd, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=15)
        fila = tk.Frame(w, bg=BG_PANEL)
        fila.pack(fill=tk.X, padx=15, pady=10)
        tk.Button(fila, text="🚪 Registrar ingreso", command=self._ingreso, bg=FG_GREEN,
                  fg="black", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=8).pack(side=tk.LEFT)
        tk.Button(fila, text="✖ Revocar (borra su rostro)", command=self._revocar, bg=FG_RED,
                  fg=FG_WHITE, font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                  padx=8).pack(side=tk.LEFT, padx=6)
        tk.Button(fila, text="Cerrar", command=w.destroy, bg=BG_ITEM, fg=FG_WHITE,
                  font=("Segoe UI", 10), relief=tk.FLAT, padx=10).pack(side=tk.RIGHT)
        self._cargar()
        w.grab_set()

    def _cargar(self):
        self._filas = self._db.list_autorizaciones_visita()
        for r in self._tree.get_children():
            self._tree.delete(r)
        for a in self._filas:
            vig = ("desde " + a["fecha_desde"].strftime("%d/%m/%Y") if a["frecuente"]
                   else a["fecha_desde"].strftime("%d/%m/%Y"))
            self._tree.insert("", tk.END, iid=str(a["idautorizacion"]), values=(
                f"{a['nombres']} {a['apellidos']}", a["rut"], a["unidad"],
                "Frecuente" if a["frecuente"] else "Ocasional", vig, a["patente"] or "—",
                "Sí" if a["plantillas"] else "No"))

    def _sel(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una visita", parent=self._w)
            return None
        return next(a for a in self._filas if str(a["idautorizacion"]) == sel[0])

    def _ingreso(self):
        a = self._sel()
        if not a:
            return
        if messagebox.askyesno("Registrar ingreso", f"¿{a['nombres']} {a['apellidos']} llegó y "
                                                    "mostró su carnet?", parent=self._w):
            self._db.registrar_visita(a["rut"], a["nombres"], a["apellidos"], a["idunidad"],
                                      a["patente"], session.current.idcuenta)
            messagebox.showinfo("Listo", "Ingreso registrado", parent=self._w)

    def _revocar(self):
        a = self._sel()
        if not a:
            return
        if messagebox.askyesno("Revocar", f"¿Revocar la autorización de {a['nombres']} "
                                          f"{a['apellidos']}?\nSe borra su rostro del sistema.",
                               parent=self._w):
            self._db.revocar_autorizacion_visita(a["idautorizacion"])
            self._cargar()
